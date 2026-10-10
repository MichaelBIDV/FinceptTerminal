"""
chaebol_map_data_codong2_gia, P2 data_price của tab codong v2 (mode live, 109 mã).

Số cp + hệ số quy đổi (kể cả trước ngày đầu có totalShares), chuỗi tuần toàn dải, VWAP trọng số số cp, zigzag cơ học,
VWAP neo, định vị hiện tại, SMR, checklist định lượng, tóm tắt cho bảng tổng. Dòng tiền theo cửa sổ (spec §5.4) nằm ở
chaebol_map_data_codong2_dong.py và được re-export tại đây (P.flow_window, ...) qua __getattr__.

Hợp đồng: chaebol_map_spec/codong_v2_spec.md §2 (V, gói _env, bậc theo nguồn) và §5. CHỈ ĐỌC vc_lk (cột theo TÊN),
lk_hoso, vnstore (mode=ro qua chaebol_map_data_gia); stdlib; không mạng; không ghi tệp.
Kết quả memo theo mtime (nen._memo, khoá ("cd2p", hàm, mã, ...)) nên dùng chung giữa các lần gọi: KHÔNG sửa tại chỗ.
"""
from __future__ import annotations

import bisect
from datetime import date, timedelta

from chaebol_map_data_codong2_fo import FO_SPIKE_PP, FO_SPIKE_RUN, _despike_fo, _impossible_fo  # noqa: F401
from chaebol_map_data_gia import _adj_col, _index_cols, _prop_map, _share_events_all, _steps, adj_fix, price_history
from chaebol_map_data_langkinh import lk_atom, lk_hoso
from chaebol_map_data_nen import (EST, T2, UNV, V, _db_path, _finite, _last, _memo, _sig, _sum, bridge, can_data,
                                  ddmmyyyy, iso, js_fixed, js_locale, lui_thang, pct_text, vc_dir)

_DONG = ("SPIKE_RULE", "flow_window", "flow_windows", "yearly_flows", "deal_weekly_spikes", "deal_sessions",
         "cost_estimate")
__all__ = ["PRE_STEP_MIN", "ZIG_PCT", "TD_FROM", "WHY_NO_VC", "WHY_NO_LK", "WHY_TD", "ZIG_RULE", "pre_share_steps",
           "shares_series", "mult_now", "mult_at", "shares_at", "weekly_full", "cum_series", "rs_weekly", "fft_view",
           "zigzag", "segment_stats", "anchored_vwap", "position_now", "smr_view", "checklist", "price_summary", *_DONG]

PRE_STEP_MIN = 1.10            # 1/bước giá ≥ 1.10 trước ts_start → coi là chia/thưởng (suy, UNV)
ZIG_PCT = 0.18
TD_FROM = "2019-01-02"         # proprietary-history vc_lk bắt đầu
VWAP_MONTHS = (6, 12, 24)
WHY_NO_VC = "chưa nạp vc_lk"
WHY_NO_LK = "chưa có lk_hoso"
WHY_TD = "tự doanh vc_lk chỉ từ 02/01/2019"
ZIG_RULE = "zigzag cơ học 18% trên giá đóng tuần điều chỉnh; không phải pha"
_VC_ONLY = ("vol_raw", "val", "dvol", "dval", "nn_vol", "nn_val", "td_val", "td_vol", "td_n", "fo", "fo_d", "fol",
            "room", "v6", "v12", "v24")


def __getattr__(name):
    """Re-export §5.4 (dòng tiền) từ _dong, nhập trễ để _dong được phép nhập module này ở đầu tệp."""
    if name in _DONG:
        import chaebol_map_data_codong2_dong as _d
        return getattr(_d, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _env(ok, why=None, tier=None, asof=None, src=None, note=None, **kw) -> dict:
    return {"ok": ok, "why": why, "tier": tier, "asof": asof, "src": src, "note": note, **kw}


def _num(x, tier, asof, src, unit, note=None, nd=0, why="không có số") -> V:
    """V số (text en-US); x không hữu hạn → [CẦN DATA](why)."""
    if not _finite(x):
        return can_data(why, src, asof, unit)
    return V(x, js_locale(x, nd), tier, asof, src, note, unit)


def _pct(x, tier, asof, src, note=None, nd=2, why="không có số", unit="%", sign=True) -> V:
    """V phần trăm / điểm %: sign=True cho mức thay đổi (+1.25%), False cho mức (3.08%); thiếu → [CẦN DATA](why)."""
    if not _finite(x):
        return can_data(why, src, asof, unit)
    txt = (pct_text(x, nd, sign) if unit == "%" else
           ("+" if sign and x > 0 else "") + js_fixed(x, nd) + " điểm %")
    return V(x, txt, tier, asof, src, note, unit)


def _monday(d: str) -> str:
    dd = date.fromisoformat(d[:10])
    return (dd - timedelta(days=dd.weekday())).isoformat()


def _weeks(dates: list) -> list:
    """[(thứ Hai ISO, [chỉ số phiên])], tuần ISO, theo thứ tự phiên."""
    out: list = []
    for i, d in enumerate(dates):
        mon = _monday(d)
        if out and out[-1][0] == mon:
            out[-1][1].append(i)
        else:
            out.append((mon, [i]))
    return out


def _lastv(vals, ix) -> tuple:
    """(giá trị, chỉ số) hữu hạn cuối cùng trong danh sách chỉ số ix; không có → (None, -1)."""
    for i in reversed(ix):
        if _finite(vals[i]):
            return vals[i], i
    return None, -1


# ───────────────────────────── gói dữ liệu phiên theo mã (memo) ─────────────────────────────

def _paths(tk: str) -> tuple:
    d = vc_dir() / tk
    return d / "price-history.json", d / "proprietary-history.json", d / "details.json"


def _sig_tk(tk: str, *extra) -> tuple:
    ps = tuple(_sig(p) for p in _paths(tk))
    return ps + ((_sig(_db_path()),) if ps[0] is None else ()) + tuple(_sig(p) for p in extra)


def _pre_steps(ph, ts_i) -> list:
    """Bước giá điều chỉnh có ngày < ts_start và 1/bước ≥ PRE_STEP_MIN (chia/thưởng suy từ giá, UNV)."""
    end = (len(ph) if ts_i is None else ts_i) - 1
    return [{"date": d, "i": ph.at(d), "factor": 1 / st, "step": st, "inferred": True}
            for d, st in _steps(ph, 0, end, "") if st and 1 / st >= PRE_STEP_MIN]


def _shares(S0: list, ts_i, pre: list) -> list:
    """Số cp từng phiên: từ ts_start = totalShares bỏ gai một phiên + ffill (như gia._shares_filled); trước ts_start
    = s(ts_start) / Π hệ số các pre-step có chỉ số phiên > i."""
    n, s = len(S0), [None] * len(S0)
    if ts_i is None:
        return s
    raw = list(S0)
    for i in range(1, n - 1):
        if raw[i] is not None and raw[i - 1] is not None and raw[i - 1] == raw[i + 1] and raw[i] != raw[i - 1]:
            raw[i] = raw[i - 1]
    last = None
    for i in range(ts_i, n):
        s[i] = last = raw[i] if raw[i] else last
    fac, cur = {e["i"]: e["factor"] for e in pre}, s[ts_i]
    for i in range(ts_i - 1, -1, -1):
        cur = cur / fac.get(i + 1, 1.0)
        s[i] = cur
    return s


def _mult(n: int, evs: list) -> list:
    """m[i] = Π hệ số các sự kiện có chỉ số phiên > i (KL_i × m[i] = cp hiện hành)."""
    f: dict = {}
    for i, x in evs:
        f[i] = f.get(i, 1.0) * x
    m, p = [1.0] * n, 1.0
    for i in range(n - 1, -1, -1):
        m[i] = p
        p *= f.get(i, 1.0)
    return m


def _prefix(b: dict) -> tuple:
    """Tổng tiền tố Σ(closeAdj·KL/s_d), Σ(KL/s_d): cùng công thức gia._vwap_prep nhưng s_d = shares_series."""
    pa, pb = [0.0], [0.0]
    for c, k, s in zip(b["C"], b["K"], b["s"]):
        w = (k / s if s else k) if _finite(c) and _finite(k) and k > 0 else 0.0
        pa.append(pa[-1] + (c * w if w else 0.0))
        pb.append(pb[-1] + w)
    return pa, pb


def _col100(ph, name: str) -> list:
    return [x * 100 if _finite(x) else None for x in ph.col(name)]


def _cols(ph, vcb: bool) -> dict:
    c = {k: _adj_col(ph, f"{n}PriceAdjusted") for k, n in (("O", "open"), ("H", "highest"), ("L", "lowest"),
                                                            ("C", "close"))}
    c.update(CP=ph.col("closePrice"), K=ph.col("totalMatchVolume"), G=ph.col("totalMatchValue"),
             DV=ph.col("totalDealVolume"), DG=ph.col("totalDealValue"), NV=ph.col("foreignNetVolumeTotal"),
             NG=ph.col("foreignNetValueTotal"), CR=ph.col("foreignCurrentRoom"), S0=ph.col("totalShares"),
             FO=_col100(ph, "foreignOwnedPercentage") if vcb else [None] * len(ph),
             FOL=_col100(ph, "foreignRoomPercentage") if vcb else [None] * len(ph),
             SK=ph.col("foreignNetValueMatched"), ST=ph.col("foreignNetValueDeal"))
    return c


def _build_base(tk: str):
    ph = price_history(tk)
    if ph is None or not len(ph):
        return None
    vcb, n = str(ph.base).startswith("vc_lk"), len(ph)
    S0 = ph.col("totalShares")
    ts_i = next((i for i, x in enumerate(S0) if _finite(x) and x > 0), None) if vcb else None
    pre = _pre_steps(ph, ts_i) if vcb else []
    evs = [(e["i"], e["factor"]) for e in pre] + ([(e["i"], e["factor"]) for e in _share_events_all(ph)] if vcb else [])
    b = {"tk": tk, "ph": ph, "vc": vcb, "n": n, "dates": ph.dates, "base": ph.base, "ts_i": ts_i, "pre": pre,
         "ts_start": ph.dates[ts_i] if ts_i is not None else None, "s": _shares(S0, ts_i, pre) if vcb else [None] * n,
         "m": _mult(n, evs), "td": _prop_map(tk) if vcb else {}, "fix": adj_fix(tk) if vcb else None, **_cols(ph, vcb)}
    b["td_first"] = min(b["td"]) if b["td"] else None
    b["FO"], b["FOL"], spk = _despike_fo(b["FO"], b["FOL"])
    b["fo_spikes"] = [b["dates"][i] for i in spk]
    b["pa"], b["pb"] = _prefix(b)
    b["sp_total"] = sum(1 for x, y in zip(b["SK"], b["ST"]) if _finite(x) and _finite(y))
    return b


def _base(tk: str):
    """Gói dữ liệu phiên của mã (None nếu không có giá). Memo theo mtime price-history/proprietary/details."""
    return _memo(("cd2p", "_base", tk), _sig_tk(tk), lambda: _build_base(tk))


def _is_pre(b: dict, i: int) -> bool:
    return bool(b["vc"]) and (b["ts_i"] is None or i < b["ts_i"])


def _vw(b: dict, a: int, z: int):
    den = b["pb"][z + 1] - b["pb"][a]
    return (b["pa"][z + 1] - b["pa"][a]) / den if den > 0 else None


def _vw_months(b: dict, z: int, months: int):
    a = bisect.bisect_right(b["dates"], lui_thang(b["dates"][z], months))
    return _vw(b, a, z)


def _src(b: dict, td: bool = False) -> str:
    return str(b["base"]) + (f" + vc_lk/{b['tk']}/proprietary-history" if td and b["td"] else "")


# ───────────────────────────── §5.1 số cổ phần và hệ số quy đổi ─────────────────────────────

def pre_share_steps(tk: str) -> list:
    """[{"date","factor": 1/bước,"step","inferred": True,"i"}]: bước giá ≥ PRE_STEP_MIN trước ts_start (VIC/HPG/REE F5)."""
    b = _base(tk)
    return [dict(e) for e in b["pre"]] if b else []


def shares_series(tk: str) -> dict:
    b = _base(tk)
    if not b or not b["vc"]:
        return _env(False, WHY_NO_VC)
    ts = b["ts_start"]
    note = (f"từ {ddmmyyyy(ts)}: totalShares bỏ gai một phiên rồi điền tiếp (T2); trước đó suy từ bước giá ≥ 10% (U)"
            if ts else "vendor không có totalShares; mọi số cp là suy (U)")
    return _env(True, tier=T2, asof=b["dates"][-1], src=f"{b['base']}.totalShares", note=note, dates=b["dates"],
                s=b["s"], ts_start=ts, pre=[dict(e) for e in b["pre"]], tier_pre=UNV)


def mult_now(tk: str) -> list:
    b = _base(tk)
    return list(b["m"]) if b else []


def mult_at(tk: str, d) -> float:
    """Hệ số quy KL ngày d về cp hiện hành = m[phiên cuối ≤ d], CÙNG hệ số weekly_full (gồm bước giá suy trước ts_start)."""
    b = _base(tk)
    if not b or not d:
        return 1.0
    return b["m"][max(b["ph"].at(d), 0)]


def shares_at(tk: str, d) -> tuple:
    """(số cp phiên cuối ≤ d theo shares_series, bậc T2 từ ts_start | U khi suy từ bước giá); không có → (None, None)."""
    b = _base(tk)
    i = b["ph"].at(d) if b and b["vc"] and d else -1
    if i < 0 or not b["s"][i]:
        return None, None
    return b["s"][i], UNV if _is_pre(b, i) else T2


# ───────────────────────────── §5.2 chuỗi tuần toàn dải ─────────────────────────────

def _room(b: dict, ix: list):
    for i in reversed(ix):
        cr, s = b["CR"][i], b["S0"][i]
        if _finite(cr) and _finite(s) and cr > 0 and s > 0:
            return cr / s * 100
    return None


def _wrow_vc(b: dict, ix: list) -> dict:
    D, m, K, z = b["dates"], b["m"], b["K"], ix[-1]
    tdi = [(i,) + tuple(b["td"][D[i]]) for i in ix if D[i] in b["td"]]
    fo, jf = _lastv(b["FO"], ix)
    r = {"vol_raw": _sum(K[i] for i in ix), "val": _sum(b["G"][i] for i in ix),
         "dvol": _sum(b["DV"][i] * m[i] for i in ix if _finite(b["DV"][i])), "dval": _sum(b["DG"][i] for i in ix),
         "nn_vol": _sum(b["NV"][i] * m[i] for i in ix if _finite(b["NV"][i])), "nn_val": _sum(b["NG"][i] for i in ix),
         "td_val": _sum(t[2] for t in tdi), "td_vol": _sum(t[1] * m[t[0]] for t in tdi if _finite(t[1])),
         "td_n": len(tdi), "fo": fo, "fo_d": D[jf] if fo is not None else None, "fol": _lastv(b["FOL"], ix)[0],
         "room": _room(b, ix), "pre": _is_pre(b, z)}
    r.update({f"v{n}": _vw_months(b, z, n) for n in VWAP_MONTHS})
    return r


def _wrow(b: dict, mon: str, ix: list, last: bool) -> dict:
    D, z, H, L = b["dates"], ix[-1], b["H"], b["L"]
    fri = (date.fromisoformat(mon) + timedelta(days=4)).isoformat()
    r = {"w": mon, "we": D[z], "n": len(ix), "partial": last and fri > D[z],
         "o": next((b["O"][i] for i in ix if _finite(b["O"][i])), None),
         "h": max((H[i] for i in ix if _finite(H[i])), default=None),
         "l": min((L[i] for i in ix if _finite(L[i])), default=None), "c": _lastv(b["C"], ix)[0],
         "vol": _sum(b["K"][i] * b["m"][i] for i in ix if _finite(b["K"][i]))}
    r.update(_wrow_vc(b, ix) if b["vc"] else {**dict.fromkeys(_VC_ONLY), "pre": False})
    return r


def _build_weekly(tk: str) -> dict:
    b = _base(tk)
    if not b:
        return _env(False, WHY_NO_VC)
    groups = _weeks(b["dates"])
    rows = [_wrow(b, mon, ix, k == len(groups) - 1) for k, (mon, ix) in enumerate(groups)]
    ts = b["ts_start"]
    if b["vc"]:
        note = ("giá điều chỉnh vendor (T2); KL, NN, TD quy về số cp hiện hành (E); tự doanh chỉ trên phiên có bản ghi"
                + (f"; trước {ddmmyyyy(ts)} số cp suy từ bước giá ≥ 10% (U)" if ts and b["ts_i"] > 0 else ""))
    else:
        note = "dự phòng vnstore.nen_ngay: trộn giá điều chỉnh và giá bảng thô; không có NN, TD, số cp (U)"
    return _env(True, tier=T2 if b["vc"] else UNV, asof=b["dates"][-1], src=_src(b, True), note=note,
                base="vc_lk" if b["vc"] else "vnstore", listing=b["dates"][0], first_week=rows[0]["w"],
                n_weeks=len(rows), ts_start=ts, pre_steps=[dict(e) for e in b["pre"]], fix=b["fix"],
                fo_spikes=list(b["fo_spikes"]),
                tier_px=T2 if b["vc"] else UNV, tier_conv=EST, tier_pre=UNV, rows=rows)


def weekly_full(tk: str) -> dict:
    """Chuỗi tuần ISO từ phiên niêm yết (spec §5.2). Memo theo mã; KHÔNG sửa tại chỗ."""
    return _memo(("cd2p", "weekly_full", tk), _sig_tk(tk), lambda: _build_weekly(tk))


def cum_series(tk: str) -> dict:
    """NN ròng cộng dồn (cp quy đổi, E) và TD ròng cộng dồn (đồng, T2, chỉ tuần có bản ghi) theo rows của weekly_full."""
    w = weekly_full(tk)
    if not w["ok"] or w["base"] != "vc_lk":
        return _env(False, w["why"] or WHY_NO_VC)
    nn, td, a, t = [], [], None, None
    for r in w["rows"]:
        if r["nn_vol"] is not None:
            a = (a or 0.0) + r["nn_vol"]
        if r["td_val"] is not None:
            t = (t or 0.0) + r["td_val"]
        nn.append(a)
        td.append(t)
    b = _base(tk)
    return _env(True, tier=EST, asof=w["asof"], src=w["src"], note="NN cp quy đổi (E); TD đồng (T2), tuần không có "
                "bản ghi không cộng", nn_cum=nn, td_cum=td, td_from=b["td_first"])


def _build_rs(tk: str) -> dict:
    w = weekly_full(tk)
    if not w["ok"]:
        return _env(False, w["why"])
    idx, src = _index_cols("VNINDEX")
    rrg = (lk_hoso(tk) or {}).get("rrg")
    rrg = ({"goc": rrg.get("goc"), "t_cuoi": iso(rrg.get("t_cuoi")), "n_tuan": rrg.get("n_tuan"), "tier": rrg.get("b"),
            "src": rrg.get("n")} if isinstance(rrg, dict) else None)
    if not idx or not len(idx):
        return _env(False, "không có chuỗi VNINDEX", rrg=rrg)
    IC, rs = idx.col("c"), []
    for r in w["rows"]:
        j = idx.at(r["we"])
        x = _last(IC, j)[0] if j >= 0 else None
        rs.append(r["c"] / x if _finite(r["c"]) and _finite(x) and x > 0 else None)
    return _env(True, tier=EST, asof=w["asof"], src=src, note=f"giá đóng tuần điều chỉnh / VNINDEX đóng phiên cuối ≤ "
                f"cuối tuần; VNINDEX từ {ddmmyyyy(idx.dates[0])}", rs=rs, rrg=rrg)


def rs_weekly(tk: str) -> dict:
    extra = (vc_dir() / "VNINDEX" / "gap-chart.json", bridge() / "data" / "lk_hoso" / f"{tk}.json")
    return _memo(("cd2p", "rs_weekly", tk), _sig_tk(tk, *extra), lambda: _build_rs(tk))


def _fl(x):
    return float(x) if _finite(x) else None


def fft_view(tk: str) -> dict:
    """Chuỗi FFT tuần của lk_hoso (T6 → thứ Hai cùng tuần ISO), TB trượt 4 tuần tự tính (E), atom giữ nguyên bậc."""
    hs = lk_hoso(tk)
    if hs is None:
        return _env(False, WHY_NO_LK)
    f = hs.get("fft") or {}
    ch = f.get("chuoi") or {}
    t = [iso(x) for x in ch.get("t") or []]
    if not t:
        return _env(False, "lk_hoso chưa có chuỗi FFT")
    n, src = len(t), f"lk_hoso/{tk}.fft"
    fw, p10, p90 = ([_fl(x) for x in (list(ch.get(k) or []) + [None] * n)[:n]] for k in ("fw", "p10", "p90"))
    ma4 = [sum(fw[i - 3:i + 1]) / 4 if i >= 3 and all(x is not None for x in fw[i - 3:i + 1]) else None
           for i in range(n)]
    out = _env(True, tier=EST, asof=iso(ch.get("t_cuoi")) or t[-1], src=src, t=t,
               note="chuỗi FFT tuần (T6) của lk_hoso: mức chỉ để vẽ, đọc theo percentile 3Y và toàn dải",
               w=[_monday(x) for x in t], fw=fw, p10=p10, p90=p90, ma4=ma4,
               ma4_now=lk_atom(f.get("ma4"), f"{src}.ma4"), canh_bao=list(f.get("canh_bao") or []),
               pattern_d=[dict(x) for x in f.get("pattern_d") or [] if isinstance(x, dict)])
    out.update({k: lk_atom(f.get(k), f"{src}.{k}") for k in ("pct3y", "pall", "p10_3y", "p90_3y", "lech")})
    out["from"] = t[0]
    return out


# ───────────────────────────── §5.3 zigzag, đoạn, VWAP neo ─────────────────────────────

def _zig_pivots(cs: list, pct: float) -> list:
    """cs = [(i, c)] (c > 0). Điểm xoay đầu = phần tử đầu; hướng chưa xác định tới khi |c/c_xoay − 1| ≥ pct; sau đó
    theo dõi cực trị, đảo chiều ≥ pct tính từ cực trị → chốt điểm xoay tại cực trị."""
    piv, dirn, ext = [cs[0]], 0, None
    for i, c in cs[1:]:
        if dirn == 0:
            if abs(c / piv[0][1] - 1) >= pct:
                dirn, ext = (1 if c > piv[0][1] else -1), (i, c)
            continue
        if (c - ext[1]) * dirn > 0:
            ext = (i, c)
        elif (c / ext[1] - 1) * -dirn >= pct:
            piv.append(ext)
            dirn, ext = -dirn, (i, c)
    return piv


def _build_zig(tk: str, pct: float) -> dict:
    w = weekly_full(tk)
    if not w["ok"]:
        return _env(False, w["why"], rule=ZIG_RULE, segments=[])
    rows = w["rows"]
    cs = [(i, r["c"]) for i, r in enumerate(rows) if _finite(r["c"]) and r["c"] > 0]
    if len(cs) < 2:
        return _env(False, "chưa đủ 2 tuần có giá", rule=ZIG_RULE, segments=[])
    pts = _zig_pivots(cs, pct) + [cs[-1]]
    segs = []
    for k in range(len(pts) - 1):
        (i0, p0), (i1, p1) = pts[k], pts[k + 1]
        if i1 == i0:
            continue
        segs.append({"i0": i0, "i1": i1, "d0": rows[i0]["we"], "d1": rows[i1]["we"], "weeks": i1 - i0, "p0": p0,
                     "p1": p1, "chg_pct": (p1 / p0 - 1) * 100, "dir": "len" if p1 >= p0 else "xuong",
                     "open": k == len(pts) - 2})
    return _env(True, tier=EST, asof=w["asof"], src=w["src"], note=ZIG_RULE, rule=ZIG_RULE, segments=segs)


def zigzag(tk: str, pct: float = ZIG_PCT) -> dict:
    """Đoạn giá cơ học trên giá đóng tuần điều chỉnh (tất định). Đoạn đã chốt luân phiên hướng và |chg_pct| ≥ pct·100."""
    return _memo(("cd2p", "zigzag", tk, pct), _sig_tk(tk), lambda: _build_zig(tk, pct))


def _seg_range(b: dict, rows: list, sg: dict) -> tuple:
    """Chỉ số phiên (a, z) của đoạn: sau phiên cuối tuần i0 (đoạn đầu: từ phiên đầu) tới phiên cuối tuần i1."""
    a = 0 if sg["i0"] == 0 else bisect.bisect_right(b["dates"], rows[sg["i0"]]["we"])
    return a, b["ph"].at(rows[sg["i1"]]["we"])


def _seg_one(b: dict, rows: list, sg: dict, prev_vol) -> dict:
    a, z = _seg_range(b, rows, sg)
    g, d1 = _agg(b, a, z), b["dates"][z]
    wk = rows[sg["i0"] + (0 if sg["i0"] == 0 else 1):sg["i1"] + 1]
    vol_w = g["vol"] / len(wk) if wk and g["vol_n"] else None
    t_vol = UNV if g["pre"] else EST
    src, srct = _src(b), _src(b, True)
    td, du = _td_vals(b, g, srct, d1)
    return {"vol_w": _num(vol_w, t_vol, d1, src, "cp/tuần", "TB KL khớp quy đổi mỗi tuần"),
            "d_vol_pct": _pct((vol_w / prev_vol - 1) * 100 if vol_w and prev_vol else None, t_vol, d1, src,
                              why="không có đoạn trước"),
            "d_fo_pp": _dfo(b, b["dates"][max(a - 1, 0)], d1), "nn_vol": _num(g["nn_vol"] if g["nn_n"] else None,
                                                                              t_vol, d1, src, "cp"),
            "nn_val": _num(g["nn_val"] if g["nn_n"] else None, T2, d1, src, "đ"), "td_val": td,
            "td_cover": f"{sum(1 for r in wk if r['td_n'])}/{len(wk)} tuần",
            "dval": _num(g["dval"], T2, d1, src, "đ"), "du_val": du, "pre": g["pre"], "vol_w_raw": vol_w}


def segment_stats(tk: str, segments: list) -> list:
    """Thống kê từng đoạn zigzag (spec §5.3): KL/tuần, Δ%NN, NN, TD (chỉ phiên có bản ghi), thoả thuận, phần dư."""
    b, w = _base(tk), weekly_full(tk)
    if not b or not b["vc"] or not w["ok"]:
        return []
    out, prev = [], None
    for sg in segments:
        st = _seg_one(b, w["rows"], sg, prev)
        prev = st.pop("vol_w_raw")
        out.append(st)
    return out


def _anchor_auto(b: dict) -> list:
    D, C = b["dates"], b["C"]
    fin = [i for i in range(b["n"]) if _finite(C[i])]
    if not fin:
        return []
    ath = max(fin, key=lambda i: (C[i], -i))
    moc = (date.fromisoformat(D[-1]) - timedelta(days=364)).isoformat()
    lo = [i for i in fin if D[i] > moc]
    out = [{"id": "ath", "label": "đỉnh lịch sử (đóng cửa điều chỉnh)", "date": D[ath]}]
    if lo:
        out.append({"id": "low52", "label": "đáy 52 tuần (đóng cửa điều chỉnh)",
                    "date": D[min(lo, key=lambda i: (C[i], -i))]})
    return out


def anchored_vwap(tk: str, anchors: list, auto: bool = True) -> list:
    """VWAP phiên ngày từ ngày neo tới phiên cuối, trọng số KL/s_d (cùng công thức §5.2); px = đóng điều chỉnh cuối."""
    b = _base(tk)
    if not b or not b["vc"]:
        return []
    D, z, src = b["dates"], b["n"] - 1, f"{b['base']} (Σ closeAdj·KL/cp ÷ Σ KL/cp)"
    pxv, jz = _lastv(b["C"], range(b["n"]))
    px = _num(pxv, T2, D[jz] if jz >= 0 else None, f"{b['base']}.closePriceAdjusted", "đ", nd=1)
    out = []
    for a in [dict(x) for x in anchors or [] if isinstance(x, dict) and x.get("date")] + (_anchor_auto(b) if auto else []):
        i = bisect.bisect_left(D, iso(a["date"]))
        v = _vw(b, i, z) if i <= z else None
        tier = UNV if _is_pre(b, i) else EST
        out.append({"id": a.get("id"), "label": a.get("label"), "date": iso(a["date"]),
                    "vwap": _num(v, tier, D[z], src, "đ", f"từ phiên {ddmmyyyy(D[i])}" if v else None, 1,
                                 why="ngày neo sau phiên cuối"),
                    "px": px, "gap_pct": _pct((px.value / v - 1) * 100 if v and not px.can else None, EST, D[z], src),
                    "sessions": max(z - i + 1, 0)})
    return out


# ───────────────────────────── tổng theo phiên (dùng chung với _dong) ─────────────────────────────

def _agg_add(o: dict, b: dict, i: int) -> None:
    m, K, DV, NG, NV = b["m"][i], b["K"][i], b["DV"][i], b["NG"][i], b["NV"][i]
    if _finite(K):
        o["vol"] += K * m
        o["vol_n"] += 1
        if K > 0 and _finite(b["G"][i]):
            o["mvol"] += K
            o["mvol_m"] += K * m
            o["mval"] += b["G"][i]
    if _finite(DV) and DV > 0:
        o["dvol"] += DV * m
        o["dvol_raw"] += DV
    o["dval"] += b["DG"][i] if _finite(b["DG"][i]) else 0.0
    if _finite(NG) or _finite(NV):
        o["nn_n"] += 1
        o["nn_val"] += NG if _finite(NG) else 0.0
        o["nn_vol"] += NV * m if _finite(NV) else 0.0
    if _finite(b["SK"][i]) and _finite(b["ST"][i]):
        o["sp_n"] += 1
        o["sp_khop"] += b["SK"][i]
        o["sp_tt"] += b["ST"][i]


def _agg_td(o: dict, b: dict, i: int) -> None:
    rec = b["td"].get(b["dates"][i])
    if rec is None:
        return
    tv, tg = rec
    o["td_k"] += 1
    o["td_val"] += tg if _finite(tg) else 0.0
    o["td_vol"] += tv * b["m"][i] if _finite(tv) else 0.0
    if _finite(tg) and _finite(b["NG"][i]):
        o["du_k"] += 1
        o["du_val"] -= b["NG"][i] + tg


def _agg(b: dict, a: int, z: int) -> dict:
    """Tổng trên phiên [a, z] (chỉ số). TD và phần dư −(NN + TD) chỉ cộng trên phiên có bản ghi tự doanh."""
    o = dict.fromkeys(("vol", "mvol", "mvol_m", "mval", "dvol", "dvol_raw", "dval", "nn_val", "nn_vol", "sp_khop", "sp_tt",
                       "td_val", "td_vol", "du_val"), 0.0)
    o.update(dict.fromkeys(("vol_n", "nn_n", "sp_n", "td_k", "du_k"), 0))
    o.update(n=max(z - a + 1, 0), a=a, z=z, pre=a <= z and _is_pre(b, a))
    for i in range(a, z + 1):
        _agg_add(o, b, i)
        _agg_td(o, b, i)
    return o


def _td_vals(b: dict, g: dict, src: str, d1: str) -> tuple:
    """(td_val, du_val) của một khối tổng: cửa sổ bắt đầu trước 02/01/2019 → TD [CẦN DATA]; phần dư chỉ trên phiên TD."""
    if g["n"] <= 0:
        c = can_data("không có phiên trong cửa sổ", src)
        return c, c
    early = b["dates"][g["a"]] < TD_FROM
    why = WHY_TD if early else "chưa nạp tự doanh vc_lk" if not b["td"] else "không có bản ghi tự doanh trong cửa sổ"
    td = (can_data(why, src, d1, "đ") if early or not g["td_k"] else
          _num(g["td_val"], T2, d1, src, "đ", f"{g['td_k']}/{g['n']} phiên có bản ghi tự doanh"))
    du = (_num(g["du_val"], EST, d1, src, "đ", f"phần dư −(NN + TD) trên {g['du_k']} phiên có bản ghi tự doanh; "
               "không phải kênh thật") if g["du_k"] else can_data(why, src, d1, "đ"))
    return td, du


def _fo_at(b: dict, d: str) -> tuple:
    """(%NN, chỉ số) của phiên cuối CÓ số ≤ d."""
    return _last(b["FO"], b["ph"].at(d))


def _dfo(b: dict, d0: str, d1: str) -> V:
    """Δ%NN (điểm %, T2) = %NN(phiên cuối có số ≤ d1) − %NN(phiên cuối có số ≤ d0)."""
    src = f"{b['base']}.foreignOwnedPercentage"
    (f1, j1), (f0, j0) = _fo_at(b, d1), _fo_at(b, d0)
    if f1 is None or f0 is None or j1 <= j0:
        return can_data("không có %NN mới trong cửa sổ", src, None, "điểm %")
    D = b["dates"]
    return _pct(f1 - f0, T2, D[j1], src, f"{js_fixed(f0, 2)}% ({ddmmyyyy(D[j0])}) → {js_fixed(f1, 2)}% "
                f"({ddmmyyyy(D[j1])})", unit="điểm %")


# ───────────────────────────── §5.5 định vị, SMR, checklist, tóm tắt ─────────────────────────────

def _pos_price(b: dict) -> dict:
    D, C, n = b["dates"], b["C"], b["n"]
    srca = f"{b['base']}.closePriceAdjusted"
    pv, j = _lastv(b["CP"], range(n))
    av, ja = _lastv(C, range(n))
    out = {"px": _num(pv, T2, D[j] if j >= 0 else None, f"{b['base']}.closePrice", "đ", nd=1),
           "px_adj": _num(av, T2, D[ja] if ja >= 0 else None, srca, "đ", nd=1)}
    for mo in VWAP_MONTHS:
        v = _vw_months(b, ja, mo) if ja >= 0 else None
        out[f"vs_v{mo}"] = _pct((av / v - 1) * 100 if v and av else None, EST, D[ja] if ja >= 0 else None,
                                f"{b['base']} (VWAP {mo} tháng, trọng số KL/số cp)")
    fin = [i for i in range(n) if _finite(C[i])]
    cd = can_data("không có giá đóng điều chỉnh", srca, None, "đ")
    out.update(ath=cd, vs_ath=cd, hi52=cd, lo52=cd)
    if fin:
        k = max(fin, key=lambda i: (C[i], -i))
        note = "đóng cửa điều chỉnh cao nhất toàn dải" + ("; chuỗi điều chỉnh vendor đã tự sửa" if b["fix"] else "")
        out["ath"] = _num(C[k], EST if b["fix"] else T2, D[k], srca, "đ", note, 1)
        out["vs_ath"] = _pct((av / C[k] - 1) * 100, EST, D[ja], srca)
        moc = (date.fromisoformat(D[ja]) - timedelta(days=364)).isoformat()
        lo = [i for i in fin if moc < D[i] <= D[ja]]
        hi_i, lo_i = max(lo, key=lambda i: (C[i], -i)), min(lo, key=lambda i: (C[i], -i))
        out["hi52"] = _num(C[hi_i], T2, D[hi_i], srca, "đ", "đỉnh đóng cửa 52 tuần", 1)
        out["lo52"] = _num(C[lo_i], T2, D[lo_i], srca, "đ", "đáy đóng cửa 52 tuần", 1)
    return out


def _pos_foreign(b: dict) -> dict:
    D, n, FO = b["dates"], b["n"], b["FO"]
    src = f"{b['base']}.foreignOwnedPercentage"
    fo, j = _lastv(FO, range(n))
    out = {"fo": _pct(fo, T2, D[j] if j >= 0 else None, src, "phiên cuối có số", sign=False)}
    fin = [i for i in range(n) if _finite(FO[i])]
    out["fo_peak"] = out["vs_fo_peak_pp"] = can_data("không có %NN", src)
    if fin:
        k = max(fin, key=lambda i: (FO[i], -i))
        sp = b["fo_spikes"]
        out["fo_peak"] = _pct(FO[k], T2, D[k], src, "%NN cao nhất toàn dải" + (
            f"; đã bỏ {len(sp)} phiên gai vendor (lệch > 3 điểm % rồi trở lại trong ≤ 10 phiên)" if sp else ""), sign=False)
        out["vs_fo_peak_pp"] = _pct(fo - FO[k], T2, D[j], src, unit="điểm %")
    fol, jl = _lastv(b["FOL"], range(n))
    out["fol"] = _pct(fol, T2, D[jl] if jl >= 0 else None, f"{b['base']}.foreignRoomPercentage", sign=False)
    rz = next((i for i in range(n - 1, -1, -1) if _room(b, [i]) is not None), None)
    out["room_pct"] = _pct(_room(b, [rz]) if rz is not None else None, EST, D[rz] if rz is not None else None,
                           f"{b['base']}.foreignCurrentRoom ÷ totalShares", "room còn lại / số cp", sign=False)
    z = next((i for i in range(n - 1, -1, -1) if _finite(b["K"][i]) and b["K"][i] > 0 and _finite(b["G"][i])
              and _finite(b["CP"][i])), None)
    x = (b["CP"][z] / (b["G"][z] / b["K"][z]) - 1) * 100 if z is not None else None
    out["close_vs_vwap_day"] = _pct(x, EST, D[z] if z is not None else None, f"{b['base']}.closePrice ÷ "
                                    "(totalMatchValue ÷ totalMatchVolume)", "đóng cửa so VWAP khớp phiên")
    return out


def position_now(tk: str) -> dict:
    """Định vị hiện tại (spec §5.5): giá, so VWAP 6/12/24T, so đỉnh lịch sử, 52 tuần, %NN (phiên cuối CÓ số), room."""
    b = _base(tk)
    if not b or not b["vc"]:
        return _env(False, WHY_NO_VC)
    out = _env(True, tier=T2, asof=b["dates"][-1], src=b["base"], weeks=len(_weeks(b["dates"])),
               listing=b["dates"][0])
    out.update(_pos_price(b))
    out.update(_pos_foreign(b))
    return out


def _smr_rows(b: dict, ok: set) -> list:
    ph, rows = b["ph"], []
    AB, AS = ph.col("averageBuyTradeVolume"), ph.col("averageSellTradeVolume")
    BU, SU = ph.col("totalBuyUnmatchedVolume"), ph.col("totalSellUnmatchedVolume")
    for mon, ix in _weeks(b["dates"]):
        jx = [i for i in ix if i in ok]
        if not jx:
            continue
        sb, ss = sum(AB[i] for i in jx) / len(jx), sum(AS[i] for i in jx) / len(jx)
        rows.append({"w": mon, "smr": sb / ss if ss else None, "buy_unmatched": _sum(BU[i] for i in jx),
                     "sell_unmatched": _sum(SU[i] for i in jx)})
    return rows


def smr_view(tk: str, min_sessions: int = 120) -> dict:
    """TB KL lệnh mua / TB KL lệnh bán theo tuần; cần ≥ min_sessions phiên có cả hai cột (sau --day-du)."""
    b = _base(tk)
    if not b or not b["vc"]:
        return _env(False, WHY_NO_VC)
    ph = b["ph"]
    AB, AS = ph.col("averageBuyTradeVolume"), ph.col("averageSellTradeVolume")
    ok = {i for i in range(b["n"]) if _finite(AB[i]) and _finite(AS[i]) and AS[i] > 0}
    if len(ok) < min_sessions:
        return _env(False, f"chờ --day-du (mới {len(ok)} phiên có số)")
    return _env(True, tier=EST, asof=b["dates"][max(ok)], src=f"{b['base']}.averageBuyTradeVolume/"
                "averageSellTradeVolume", note=f"{len(ok)} phiên có số", rows=_smr_rows(b, ok))


def _ck(id_: str, text: str, ok, value: V, tier) -> dict:
    """Mục checklist: ok None hoặc value thiếu → "can"; chữ trung tính, không kèm hành động."""
    state = "can" if ok is None or value.can else ("dat" if ok else "chua")
    return {"id": id_, "text": text, "state": state, "value": value, "tier": None if state == "can" else tier}


def _ck_nn(b: dict) -> dict:
    src = f"{b['base']}.foreignNetValueTotal"
    ix = [i for i in range(b["n"]) if _finite(b["NG"][i])]
    if len(ix) < 4:
        return _ck("nn_ban_4p", "Khối ngoại bán ròng 4 phiên liên tiếp", None, can_data("chưa đủ 4 phiên có số NN", src),
                   T2)
    k = 0
    while k < len(ix) and b["NG"][ix[-1 - k]] < 0:
        k += 1
    v = _num(k, T2, b["dates"][ix[-1]], src, "phiên", "số phiên bán ròng liên tiếp tới phiên cuối có số")
    return _ck("nn_ban_4p", "Khối ngoại bán ròng 4 phiên liên tiếp", k >= 4, v, T2)


def _ck_week(rows: list, src: str) -> list:
    done = [r for r in rows if not r["partial"]]
    out, txt = [], "KL khớp tuần gần nhất > 2 lần TB 12 tuần trước"
    prev = [r["vol"] for r in done[-13:-1] if _finite(r["vol"])]
    if len(done) >= 13 and len(prev) == 12 and _finite(done[-1]["vol"]) and sum(prev) > 0:
        x = done[-1]["vol"] / (sum(prev) / 12)
        out.append(_ck("kl_gap_2x", txt, x > 2, _num(x, EST, done[-1]["we"], src, "lần", nd=2), EST))
    else:
        out.append(_ck("kl_gap_2x", txt, None, can_data("chưa đủ 13 tuần có KL", src), EST))
    r = rows[-1] if rows else {}
    vs = [r.get(f"v{n}") for n in VWAP_MONTHS]
    have = _finite(r.get("c")) and all(_finite(v) for v in vs)
    for id_, txt, f in (("tren_3vwap", "Giá đóng tuần trên cả ba VWAP 6/12/24 tháng", lambda c, v: c > v),
                        ("duoi_3vwap", "Giá đóng tuần dưới cả ba VWAP 6/12/24 tháng", lambda c, v: c < v)):
        val = _num(r["c"], T2, r["we"], src, "đ", "giá đóng tuần cuối", 1) if have else can_data("thiếu VWAP", src)
        out.append(_ck(id_, txt, all(f(r["c"], v) for v in vs) if have else None, val, EST))
    return out


def _ck_fft(tk: str) -> list:
    f = (lk_hoso(tk) or {}).get("fft") or {}
    src = f"lk_hoso/{tk}.fft"
    a = {k: lk_atom(f.get(k), f"{src}.{k}") for k in ("ma4", "p10_3y", "p90_3y", "x_p10", "x_p90")}
    out = []
    for id_, txt, ref, x, cmp in (("fft_can", "FFT TB 4 tuần ≤ P10 3Y", "p10_3y", "x_p10", lambda m, p: m <= p),
                                  ("fft_cao", "FFT TB 4 tuần ≥ P90 3Y", "p90_3y", "x_p90", lambda m, p: m >= p)):
        ok = None if a["ma4"].can or a[ref].can else cmp(a["ma4"].value, a[ref].value)
        val = a[x] if f else can_data(WHY_NO_LK, src)
        out.append(_ck(id_, txt, ok, val, val.tier or a["ma4"].tier))
    return out


def _ck_fo20(b: dict) -> dict:
    src, txt = f"{b['base']}.foreignOwnedPercentage", "%NN đổi ≥ 0.5 điểm % trong 20 phiên"
    f1, j1 = _lastv(b["FO"], range(b["n"]))
    f0, j0 = _last(b["FO"], j1 - 20) if j1 >= 20 else (None, -1)
    if f1 is None or f0 is None:
        return _ck("fo_20p", txt, None, can_data("chưa đủ 20 phiên có %NN", src), T2)
    v = _pct(f1 - f0, T2, b["dates"][j1], src, f"so phiên {ddmmyyyy(b['dates'][j0])}", unit="điểm %")
    return _ck("fo_20p", txt, abs(f1 - f0) >= 0.5, v, T2)


def checklist(tk: str, insider_recent_n: int | None = None) -> dict:
    """Checklist định lượng tự chấm (spec §5.5): state ∈ dat|chua|can; chữ trung tính, KHÔNG kèm hành động."""
    b, w = _base(tk), weekly_full(tk)
    src = f"vc_lk/{tk}/insider-transaction"
    nb = (can_data("chưa có số giao dịch nội bộ 30 ngày", src) if insider_recent_n is None else
          _num(insider_recent_n, T2, None, src, "dòng", "giao dịch nội bộ đã thực hiện trong 30 ngày"))
    items = [_ck("noi_bo_30n", "Có giao dịch nội bộ đã thực hiện trong 30 ngày",
                 None if insider_recent_n is None else insider_recent_n > 0, nb, T2)] + _ck_fft(tk)
    if not b or not b["vc"]:
        cd = can_data(WHY_NO_VC)
        items += [_ck(i, t, None, cd, None) for i, t in (
            ("nn_ban_4p", "Khối ngoại bán ròng 4 phiên liên tiếp"),
            ("kl_gap_2x", "KL khớp tuần gần nhất > 2 lần TB 12 tuần trước"),
            ("tren_3vwap", "Giá đóng tuần trên cả ba VWAP 6/12/24 tháng"),
            ("duoi_3vwap", "Giá đóng tuần dưới cả ba VWAP 6/12/24 tháng"),
            ("tt_4t", "Có tuần thoả thuận đột biến trong 4 tuần gần nhất"),
            ("fo_20p", "%NN đổi ≥ 0.5 điểm % trong 20 phiên"))]
        return _env(False, WHY_NO_VC, items=items)
    from chaebol_map_data_codong2_dong import deal_weekly_spikes
    sp, rows = deal_weekly_spikes(tk), w["rows"]
    last4 = rows[-4]["w"] if len(rows) >= 4 else rows[0]["w"]
    k = sum(1 for x in sp.get("weeks") or [] if x["w"] >= last4)
    items += [_ck_nn(b)] + _ck_week(rows, _src(b)) + [
        _ck("tt_4t", "Có tuần thoả thuận đột biến trong 4 tuần gần nhất", k > 0 if sp["ok"] else None,
            _num(k, EST, b["dates"][-1], _src(b), "tuần", sp.get("rule")) if sp["ok"] else can_data(sp["why"]), EST),
        _ck_fo20(b)]
    return _env(True, tier=EST, asof=b["dates"][-1], src=_src(b, True), items=items)


def price_summary(tk: str, today: str) -> dict:
    """Số giá/dòng tiền cho bảng tổng 109 mã (O.summary_row): chỉ V hoặc số đếm, không nhãn."""
    from chaebol_map_data_codong2_dong import deal_weekly_spikes, flow_windows
    w = weekly_full(tk)
    f = (lk_hoso(tk) or {}).get("fft") or {}
    src = f"lk_hoso/{tk}.fft"
    fw = flow_windows(tk, today)
    sp = deal_weekly_spikes(tk)
    d_fo = fw["win"]["1y"]["d_fo_pp"] if fw["ok"] and fw["win"]["1y"]["ok"] else can_data(fw.get("why") or WHY_NO_VC)
    return {"weeks": w["n_weeks"] if w["ok"] else None, "den": w["asof"] if w["ok"] else None, "d_fo_1y_pp": d_fo,
            "deal_spikes_52w": (_num(sp["n_52w"], EST, sp["asof"], sp["src"], "tuần", sp["rule"]) if sp["ok"]
                                else can_data(sp["why"])),
            "fft_pct3y": lk_atom(f.get("pct3y"), f"{src}.pct3y") if f else can_data(WHY_NO_LK, src),
            "fft_pall": lk_atom(f.get("pall"), f"{src}.pall") if f else can_data(WHY_NO_LK, src)}
