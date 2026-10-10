"""
chaebol_map_data_codong2_ydo: phần tách của P1 data_owner (codong v2), re-export qua chaebol_map_data_codong2.

§4.5 cổ đông lớn, cơ cấu, quan hệ, quỹ · §4.6 Toàn Vũ (Pillar I) · §4.7 sự kiện vốn, ĐHCĐ, dòng thời gian, nguồn ý đồ ·
§4.8 bảng tổng 109 mã (chỉ số, không nhãn). Chỉ đọc kho; không mạng, không ghi tệp. Hàm cần dòng nội bộ / nhóm chủ thể
nhập trễ chaebol_map_data_codong2 bên trong hàm (tránh vòng nhập).
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from chaebol_map_data_nen import *  # noqa: F401,F403
from chaebol_map_data_nen import _finite
from chaebol_map_data_gia import price_history, share_events
from chaebol_map_data_langkinh import lk_atom, lk_hoso, tv30
from chaebol_map_data_sohuu import capital_events, relationships, top_holders
from chaebol_map_data_tailieu import facts_for

ISS_KIND = (("Trả Cổ tức bằng Cổ phiếu", "co_tuc_cp", "khong_thu"), ("Cổ phiếu thưởng", "thuong", "khong_thu"),
            ("Phát hành cho CBCNV", "esop", "esop"), ("Phát hành riêng lẻ", "rieng_le", "thu_tien"),
            ("Quyền mua CP cho Cổ đông hiện hữu", "quyen_mua", "thu_tien"),
            ("Phát hành rộng rãi qua đấu giá", "dau_gia", "thu_tien"),
            ("Chuyển từ trái phiếu chuyển đổi", "chuyen_doi", "khong_thu"), ("Phát hành cho trái chủ", "chuyen_doi", "khong_thu"),
            ("Phát hành để sáp nhập", "sap_nhap", "khong_thu"))
SUMMARY_COLS = (("nb_rong_12t", EST), ("dk_mo", T2), ("tt_dot_bien_52t", EST), ("d_nn_1y_pp", T2),
                ("fft_pct3y", None), ("fft_pall", None), ("codong_qs", T3), ("quy_n", T2))
PRE2010_WHY = "events-v2/events-all chỉ từ 01/01/2010; chờ nạp lại fromDate = ngày niêm yết"
WHY_EVALL = "events-all chưa nạp cho mã này"
WHY_FUND_DETAIL = "chi tiết từng quỹ cần đăng nhập Vietcap IQ"
_CC_FIELDS = ("dong_co", "diem_gay", "buc_tranh", "thau_tom", "muc_dich_keo", "doi_co_dong", "noi_bo_tom_tat",
              "cau_hoi_mo_chi_tiet")

__all__ = [
    "holder_table", "holder_delta", "structure_bars", "relationship_view", "fund_view", "codong_full", "codong_delta",
    "match_flip", "ISS_KIND", "capital_actions", "agm_events", "timeline", "intent_sources", "SUMMARY_COLS",
    "summary_row", "summary_rows", "PRE2010_WHY", "WHY_EVALL", "WHY_FUND_DETAIL",
]


def _env(ok, why=None, tier=None, asof=None, src=None, note=None, **kw) -> dict:
    return {"ok": ok, "why": why, "tier": tier, "asof": asof, "src": src, "note": note, **kw}


def _vq(x, tier, asof, src, note=None, unit="cp") -> V:
    return V(x, js_locale(x, 0), tier, asof, src, note, unit)


def _vp(x, tier, asof, src, note=None, unit="%") -> V:
    return V(x, js_fixed(x, 2) + ("%" if unit == "%" else ""), tier, asof, src, note, unit)


def _vn(n, tier, asof, src, note=None) -> V:
    return V(n, js_locale(n, 0), tier, asof, src, note, None)


def _why_vc(tk: str, ep: str) -> str:
    from chaebol_map_data_codong2 import _why_vc as w
    return w(tk, ep)


def _month_end(ky: str) -> str:
    y, m = int(ky[:4]), int(ky[5:7])
    return (date(y + m // 12, m % 12 + 1, 1) - timedelta(days=1)).isoformat()


def _sgn(x) -> int:
    return (x > 0) - (x < 0)


# ───────────────────────────── 4.5 cổ đông lớn, cơ cấu, quan hệ, quỹ ─────────────────────────────

def _holder_group(tk: str, name: str, kind: str):
    from chaebol_map_data_codong2 import _owner_key_for_name, _seed_match, group_map
    o = _owner_key_for_name(tk, name or "", kind)
    g = group_map(tk).get(o["key"]) or _seed_match(tk, o)
    return g["group"] if g else None


def _holder_row(tk: str, r: dict, fresh_from: str, today: str, qn: dict, src: str) -> dict:
    from chaebol_map_data_codong2 import norm_name
    pub, q, p = iso(r.get("publicDate")), r.get("quantity"), r.get("percentage")
    kind = "person" if r.get("ownerType") == "INDIVIDUAL" else "org"
    fresh = bool(pub and pub >= fresh_from)
    age = (date.fromisoformat(today) - date.fromisoformat(pub)).days / 30.44 if pub else None
    return {"name": r.get("ownerName"), "name_en": r.get("ownerNameEn"), "code": r.get("ownerCode"), "kind": kind,
            "position": r.get("positionName"), "public": pub, "fresh": fresh,
            "old12": age is not None and age > OLD_MONTHS,
            "qty": _vq(q, T2, pub, f"{src}.quantity") if _finite(q) else can_data("quantity trống", src),
            "qty_now": qn.get(r.get("ownerCode")) if fresh else None,
            "pct": _vp(p * 100, T2, pub, f"{src}.percentage") if _finite(p) else can_data("percentage trống", src),
            "group": _holder_group(tk, r.get("ownerName"), kind), "_n": norm_name(r.get("ownerName"))}


def _conc(rows: list, period: str) -> dict:
    fr = sorted((r for r in rows if r["fresh"] and not r["pct"].can), key=lambda r: -r["pct"].value)
    ps = [r["pct"].value for r in fr]
    src, note = "Σ % dòng cổ đông kỳ mới", "chỉ tính trên dòng kỳ mới"

    def v(x, unit="%"):
        return _vp(x, EST, period, src, note, unit)
    return {"top1": v(sum(ps[:1])), "top3": v(sum(ps[:3])), "top5": v(sum(ps[:5])),
            "hhi": V(sum(x * x for x in ps), js_locale(sum(x * x for x in ps), 0), EST, period, src, note, "điểm"),
            "pct_person": v(sum(r["pct"].value for r in fr if r["kind"] == "person")),
            "pct_org": v(sum(r["pct"].value for r in fr if r["kind"] == "org"))}


def holder_table(tk: str, today: str) -> dict:
    """MỌI dòng sổ cổ đông vc_lk (không cắt top), % giảm dần; tập trung và SL quy đổi CHỈ trên dòng kỳ mới."""
    from chaebol_map_data_codong2 import FRESH_DAYS
    meta, raw = vc(tk, "shareholder")
    src = f"vc_lk/{tk}/shareholder"
    if not isinstance(raw, list) or not raw:
        return _env(False, _why_vc(tk, "shareholder"), tier=T2, src=src, rows=[], n=0, n_fresh=0, n_old=0, n_dup=0)
    pubs = [iso(r.get("publicDate")) for r in raw if r.get("publicDate")]
    period = max(pubs) if pubs else None
    fresh_from = (date.fromisoformat(period) - timedelta(days=FRESH_DAYS)).isoformat() if period else "9999-12-31"
    th = top_holders(tk, None, "qty_now").value or []
    qn = {h["code"]: h["qty_now"] for h in th if h.get("code")}
    rows = [_holder_row(tk, r, fresh_from, today, qn, src) for r in raw]
    rows.sort(key=lambda r: (-(r["pct"].value or 0), str(r["name"])))
    names = Counter(r["_n"] for r in rows)
    codes: dict = {}
    for r in rows:
        codes.setdefault(r["_n"], set()).add(r["code"])
    out = [{**{k: v for k, v in r.items() if k != "_n"}, "rank": i, "dup": names[r["_n"]] > 1 and len(codes[r["_n"]]) > 1}
           for i, r in enumerate(rows, 1)]
    nf = sum(1 for r in out if r["fresh"])
    return _env(True, tier=T2, asof=(meta or {}).get("du_lieu_toi"), src=src, rows=out, period=period,
                fresh_from=fresh_from, n=len(out), n_fresh=nf, n_old=len(out) - nf, n_dup=sum(1 for r in out if r["dup"]),
                conc=_conc(out, period), lay_luc=(meta or {}).get("lay_luc"))


def holder_delta(tk: str) -> dict:
    """Δ cổ đông lớn giữa hai ảnh chụp vc_lk_lichsu gần nhất (cần ≥2 ảnh)."""
    d = bridge() / "state" / "vc_lk_lichsu" / tk / "shareholder"
    files = sorted(d.glob("*.json")) if d.exists() else []
    src = f"vc_lk_lichsu/{tk}/shareholder"
    if len(files) < 2:
        dd = f" ({ddmmyyyy(files[-1].stem)})" if files else ""
        return _env(False, f"mới có {len(files)} ảnh chụp vc_lk_lichsu{dd}; Δ cần ≥2", tier=T2, src=src, rows=[])
    snaps = []
    for p in files[-2:]:
        rows = (read_json(p, quiet=True) or {}).get("du_lieu") or []
        snaps.append({(r.get("ownerCode") or r.get("ownerName")): r for r in rows if isinstance(r, dict)})
    d0, d1 = files[-2].stem, files[-1].stem
    out = []
    for k in sorted(set(snaps[0]) | set(snaps[1]), key=str):
        a, b = snaps[0].get(k), snaps[1].get(k)
        q0, q1 = (a or {}).get("quantity"), (b or {}).get("quantity")
        if _finite(q0) and _finite(q1) and q0 == q1:
            continue
        both = _finite(q0) and _finite(q1)
        out.append({"name": (b or a).get("ownerName"), "code": (b or a).get("ownerCode"),
                    "qty0": _vq(q0, T2, d0, src) if _finite(q0) else can_data("không có ở ảnh chụp trước", src, d0),
                    "qty1": _vq(q1, T2, d1, src) if _finite(q1) else can_data("không có ở ảnh chụp sau", src, d1),
                    "d_qty": _vq(q1 - q0, EST, d1, src) if both else can_data("chỉ có ở một ảnh chụp", src, d1)})
    out.sort(key=lambda r: (r["d_qty"].can, -abs(r["d_qty"].value or 0)))
    return _env(True, tier=T2, asof=d1, src=src, d0=d0, d1=d1, rows=out)


def _snap_pct(x, src) -> V:
    note = "ảnh chụp; vendor không ghi ngày dữ liệu"
    return _vp(x * 100, T2, None, src, note) if _finite(x) else can_data("trường trống", src)


def structure_bars(tk: str) -> dict:
    """Hai thanh cơ cấu: (1) Nhà nước / Nước ngoài / Khác (≈100%); (2) HĐQT, Tổ chức: lát CHỒNG LẤN, không cộng vào (1)."""
    meta, s = vc(tk, "shareholder-structure")
    src = f"vc_lk/{tk}/shareholder-structure"
    if not isinstance(s, dict):
        return _env(False, _why_vc(tk, "shareholder-structure"), tier=T2, src=src)
    _, det = vc(tk, "details")
    det = det if isinstance(det, dict) else {}
    bar1 = [{"k": k, "label": lb, "pct": _snap_pct(s.get(f), f"{src}.{f}")} for k, lb, f in
            (("state", "Nhà nước", "statePercentage"), ("foreign", "Nước ngoài", "foreignPercentage"),
             ("other", "Khác", "otherPercentage"))]
    bar2 = [{"k": k, "label": lb, "pct": _snap_pct(s.get(f), f"{src}.{f}")} for k, lb, f in
            (("bod", "HĐQT", "bodPercentage"), ("institution", "Tổ chức", "institutionPercentage"))]
    ts = s.get("totalShares")
    return _env(True, tier=T2, src=src, note="bar2 là lát chồng lấn, không cộng thành 100%", bar1=bar1,
                sum1=sum(b["pct"].value for b in bar1 if not b["pct"].can), bar2=bar2,
                free_float=_snap_pct(det.get("freeFloatPercentage"), f"vc_lk/{tk}/details.freeFloatPercentage"),
                fol=_snap_pct(det.get("maximumForeignPercentage"), f"vc_lk/{tk}/details.maximumForeignPercentage"),
                total_shares=_vq(ts, T2, None, f"{src}.totalShares") if _finite(ts) else can_data("totalShares trống", src),
                data_date={"text": "vendor không ghi ngày dữ liệu", "tier": UNV}, lay_luc=(meta or {}).get("lay_luc"))


def relationship_view(tk: str, top: int = 15) -> dict:
    """Công ty con/liên kết: mọi liên kết có mã niêm yết + top theo %; bỏ % = 0; thời điểm UNVERIFIED."""
    src = f"vc_lk/{tk}/relationship"
    if not isinstance(vc(tk, "relationship")[1], dict):
        return _env(False, _why_vc(tk, "relationship"), tier=T2, src=src, listed=[], top=[], n_sub=0, n_aff=0)
    r = relationships(tk)
    keep = {"subsidiaries": [], "affiliates": []}
    for grp in keep:
        for x in r.get(grp) or []:
            if not x["pct"].can and x["pct"].value >= 0.005:
                keep[grp].append({"name": x["name"], "ticker": x["ticker"], "pct": x["pct"], "kind": grp})
    allx = sorted(keep["subsidiaries"] + keep["affiliates"], key=lambda x: (-x["pct"].value, str(x["name"])))
    return _env(True, tier=T2, asof=None, src=src, listed=[x for x in allx if x["ticker"]], top=allx[:top],
                n_sub=len(keep["subsidiaries"]), n_aff=len(keep["affiliates"]),
                time_note="thời điểm UNVERIFIED (vendor không ghi ngày)", lay_luc=r.get("t_lay"))


def _net_start(asof: str, k: str) -> str:
    return f"{int(asof[:4]) - 1}-12-31" if k == "ytd" else lui_thang(asof, {"m1": 1, "m3": 3, "m6": 6, "y1": 12}[k])


def _fund_net(tk: str, t: dict, asof: str, src: str) -> dict:
    out = {}
    for k in ("m1", "m3", "m6", "ytd", "y1"):
        x = ((t.get("net_change") or {}).get(k) or {}).get("shares")
        evs = share_events(tk, _net_start(asof, k), asof)
        note = (f"cắt qua GDKHQ {' và '.join(ddmmyyyy(e['date']) for e in evs)}, chưa quy đổi" if evs else None)
        out[k] = _vq(x, T2, asof, f"{src}.net_change.{k}.shares", note) if _finite(x) else can_data("trống", src)
    return out


def _fund_hist(tk: str):
    base = sys_dir() / "smart_money" / "history"
    snaps = []
    for p in sorted(base.glob("*/aggregate.json")) if base.exists() else []:
        d = read_json(p, quiet=True) or {}
        if d.get("as_of"):
            snaps.append((iso(d["as_of"]), p.parent.name, (d.get("tickers") or {}).get(tk)))
    snaps.sort(key=lambda s: s[0])
    if len(snaps) < 2 or not snaps[-1][2] or not snaps[-2][2]:
        return None
    (d0, k0, a), (d1, k1, b) = snaps[-2], snaps[-1]
    h0, h1 = a.get("shares_held"), b.get("shares_held")
    if not (_finite(h0) and _finite(h1)):
        return None
    f = 1.0
    for e in share_events(tk, d0, d1):
        f *= e["factor"]
    s0, s1 = f"smart_money/history/{k0}/aggregate.json", f"smart_money/history/{k1}/aggregate.json"
    n0, n1 = (int(x["num_funds"]) if _finite(x.get("num_funds")) else None for x in (a, b))
    src = f"{s1} − {s0} × hệ số GDKHQ"
    delta = (_vq(h1 - h0 * f, EST, d1, src, "quy đổi theo share_events; cùng số quỹ hai kỳ") if n0 is not None and n0 == n1
             else can_data(f"tập quỹ đổi {n0 if n0 is not None else '?'}→{n1 if n1 is not None else '?'}, hiệu hai ảnh "
                           "không phải giao dịch", src, d1))
    return {"d0": d0, "d1": d1, "held0": _vq(h0, T2, d0, s0), "held1": _vq(h1, T2, d1, s1), "factor": f,
            "delta_now": delta, "n_funds0": n0, "n_funds1": n1}


def fund_view(tk: str) -> dict:
    """Quỹ (fund_holdings aggregate, số cp; KHÔNG dùng value_bn) + Δ giữa hai kỳ smart_money quy đổi GDKHQ."""
    ag = read_json(sys_dir() / "fund_holdings" / "aggregate.json", quiet=True) or {}
    asof, src = iso(ag.get("as_of")), "fund_holdings/aggregate.json"
    t = (ag.get("tickers") or {}).get(tk)
    if not isinstance(t, dict):
        why = f"fund_holdings chưa có mã này (kỳ {ddmmyyyy(asof)})" if asof else "chưa có fund_holdings/aggregate.json"
        return _env(False, why, tier=T2, asof=asof, src=src, note="tín hiệu quỹ, không phải chủ thể")
    h, p, n = t.get("shares_held"), t.get("pct_outstanding"), t.get("num_funds")
    return _env(True, tier=T2, asof=asof, src=src, note="tín hiệu quỹ, không phải chủ thể",
                held=_vq(h, T2, asof, f"{src}.shares_held") if _finite(h) else can_data("trống", src),
                pct_out=_vp(p * 100, T2, asof, f"{src}.pct_outstanding") if _finite(p) else can_data("trống", src),
                n_funds=_vn(int(n), T2, asof, f"{src}.num_funds") if _finite(n) else can_data("trống", src),
                net=_fund_net(tk, t, asof, src), hist=_fund_hist(tk), detail_why=WHY_FUND_DETAIL)


# ───────────────────────────── 4.6 Toàn Vũ (Pillar I) ─────────────────────────────

def codong_full(tk: str) -> dict:
    """Mọi mốc số cổ đông Toàn Vũ (bậc TỪNG mốc) + cặp k (bậc từng atom); chỉ 30 mã TV30; không lọc năm."""
    from chaebol_map_data_codong2 import ESOP_NOTE, HIERARCHY_TEXT, THIN_MAX_QS, WHY_NO_TV
    if tk not in tv30():
        return _env(False, WHY_NO_TV, src=f"lk_hoso/{tk}.codong", moc=[], cap=[], n_moc=0, n_qs=0, thin=False)
    cd = (lk_hoso(tk) or {}).get("codong") or {}
    if cd.get("trang_thai") != "ok" or not cd.get("moc"):
        return _env(False, "chưa có lk_hoso" if lk_hoso(tk) is None else WHY_NO_TV, src=f"lk_hoso/{tk}.codong",
                    moc=[], cap=[], n_moc=0, n_qs=0, thin=False)
    src = cd.get("nguon_moc") or f"lk_hoso/{tk}.codong.moc"
    moc = [{"ky": m["ky"], "end": _month_end(m["ky"]), "v": m.get("v"), "kieu": m.get("kieu"), "cf": bool(m.get("cf")),
            "tier": m.get("b"), "usable": m.get("kieu") == "quan_sat"} for m in cd["moc"]]
    kieu = {m["ky"]: m["kieu"] for m in moc}
    cap = [{"tu": c.get("tu"), "den": c.get("den"), "trang_thai": c.get("trang_thai"),
            "d_pct": lk_atom(c.get("d_pct"), f"lk_hoso/{tk}.codong.cap.d_pct"),
            "k": lk_atom(c.get("k"), f"lk_hoso/{tk}.codong.cap.k"), "nhan_k": c.get("nhan_k"),
            "usable": c.get("trang_thai") == "ok" and kieu.get(c.get("tu")) == "quan_sat"
            and kieu.get(c.get("den")) == "quan_sat"} for c in cd.get("cap") or []]
    n_qs = sum(1 for m in moc if m["usable"])
    return _env(True, tier=T3, asof=moc[-1]["end"], src=src, moc=moc, n_moc=len(moc), n_qs=n_qs,
                thin=n_qs <= THIN_MAX_QS, n_kieu=dict(Counter(m["kieu"] for m in moc)), cap=cap,
                hierarchy=HIERARCHY_TEXT, esop_note=ESOP_NOTE)


def codong_delta(tk: str, d0: str, d1: str) -> V:
    """Δ% số cổ đông giữa mốc đầu và cuối trong [d0, d1]: ưu tiên hai mốc quan sát (SS-T3); thiếu → mốc nội suy (EST).
    Không bao giờ dùng mốc chép (CF) hay số tròn."""
    cf = codong_full(tk)
    if not cf["ok"]:
        return can_data(cf["why"], cf["src"])
    inw = [m for m in cf["moc"] if d0 <= m["end"] <= d1 and m["kieu"] in ("quan_sat", "noi_suy") and m["v"]]
    qs = [m for m in inw if m["kieu"] == "quan_sat"]
    a, b = (qs[0], qs[-1]) if len(qs) >= 2 else (inw[0], inw[-1]) if len(inw) >= 2 else (None, None)
    if a is None or a is b:
        return can_data("không đủ 2 mốc trong đoạn", cf["src"])
    x = (b["v"] / a["v"] - 1) * 100
    both = a["kieu"] == b["kieu"] == "quan_sat"
    return _vp(x, a["tier"] if both else EST, b["end"], cf["src"], None if both else "có mốc nội suy")


def _mf_row(c: dict, fl: dict) -> dict:
    dc, du = c["d_pct"], fl.get("du_val") or can_data("thiếu phần dư")
    if c["den"] < "2019-01":
        ket, why = "KHONG_RO", "tự doanh vc_lk chỉ từ 02/01/2019"
    elif du.can or not du.value:
        ket, why = "KHONG_RO", du.note or "phần dư bằng 0"
    elif dc.can or abs(dc.value) < 1:
        ket, why = "KHONG_RO", "|Δ cổ đông| < 1%"
    else:
        ket, why = ("MATCH" if _sgn(dc.value) == _sgn(du.value) else "FLIP"), None
    return {"tu": c["tu"], "den": c["den"], "d_codong": dc, "du": du,
            "d_fo_pp": fl.get("d_fo_pp") or can_data("thiếu Δ%NN"), "nn_vol": fl.get("nn_vol") or can_data("thiếu NN"),
            "ket": ket, "why": why}


def match_flip(tk: str, flow_of) -> dict:
    """Δ cổ đông (cặp usable) × phần dư CN+TC = −(NN+TD) của P.flow_window: MATCH / FLIP / KHONG_RO (so sánh dữ liệu)."""
    cf = codong_full(tk)
    if not cf["ok"]:
        return _env(False, cf["why"], tier=EST, src=cf["src"], rows=[])
    rows = []
    for c in (c for c in cf["cap"] if c["usable"]):
        try:
            fl = flow_of(_month_end(c["tu"]), _month_end(c["den"])) or {}
        except Exception as e:  # noqa: BLE001  (lỗi phía P2 không làm vỡ bảng)
            warn(f"codong2 match_flip {tk} {c['tu']}→{c['den']}: {e}")
            fl = {}
        rows.append(_mf_row(c, fl))
    return _env(True, tier=EST, asof=cf["asof"], src=f"{cf['src']} × flow_window", rows=rows,
                note="nhãn so sánh dữ liệu, không phải tín hiệu")


# ───────────────────────────── 4.7 sự kiện vốn, ĐHCĐ, dòng thời gian, nguồn ý đồ ─────────────────────────────

def _classify(e: dict):
    code, title = e.get("code"), str(e.get("title") or "")
    if code == "DIV":
        return "co_tuc_tien", "co_tuc_tien"
    if code == "AIS":
        return "niem_yet_them", "niem_yet_them"
    if code == "ISS":
        for needle, sub, kind in ISS_KIND:
            if needle.lower() in title.lower():
                return kind, sub
    return "khac", "khac"


def _listing(tk: str):
    _, det = vc(tk, "details")
    li = iso(det.get("listingDate")) if isinstance(det, dict) else None
    if li:
        return li
    ph = price_history(tk)
    return ph.dates[0] if ph is not None and len(ph) else None


def capital_actions(tk: str, today: str, months: int = 24) -> dict:
    """Sự kiện vốn events-v2 phân loại thu tiền / ESOP / không thu tiền / cổ tức tiền; đếm trong `months` tháng."""
    li = _listing(tk)
    pre = bool(li and li < "2010-01-01")
    base = {"pre2010": pre, "pre2010_why": PRE2010_WHY if pre else None}
    ce = capital_events(tk)
    src = f"vc_lk/{tk}/events-v2"
    if ce.can:
        return _env(False, _why_vc(tk, "events-v2"), tier=T2, src=src, items=[],
                    counts=dict.fromkeys(("thu_tien", "esop", "khong_thu", "co_tuc_tien"), 0), **base)
    items = []
    for e in ce.value:
        kind, sub = _classify(e)
        items.append({"date": e.get("effective"), "code": e.get("code"), "kind": kind, "sub": sub, "ratio": e.get("ratio"),
                      "title": e.get("title")})
    items.sort(key=lambda it: it["date"] or "", reverse=True)
    cut = lui_thang(today, months)
    counts = {k: sum(1 for it in items if it["kind"] == k and cut <= (it["date"] or "") <= today)
              for k in ("thu_tien", "esop", "khong_thu", "co_tuc_tien")}
    return _env(True, tier=T2, asof=ce.asof, src=src, items=items, counts=counts, window=f"{months}T", **base)


def _ev_all(tk: str):
    meta, rows = vc(tk, "events-all")
    return (meta or {}), (rows if isinstance(rows, list) else None)


def agm_events(tk: str, today: str) -> dict:
    """ĐHCĐ (AGME/AGMR/EGME) từ events-all: mục giảm dần theo ngày, sắp tới (≥ hôm nay), lần gần nhất đã họp."""
    meta, rows = _ev_all(tk)
    src = f"vc_lk/{tk}/events-all"
    if rows is None:
        return _env(False, WHY_EVALL if (vc_dir() / tk).exists() else "chưa nạp vc_lk", tier=T2, src=src, items=[],
                    upcoming=[], last=None)
    items = [{"date": iso(r.get("displayDate1")) or iso(r.get("issueDate")), "code": r.get("eventCode"),
              "title": r.get("eventTitleVi"), "record": iso(r.get("recordDate"))}
             for r in rows if r.get("eventCode") in ("AGME", "AGMR", "EGME")]
    items = sorted((it for it in items if it["date"]), key=lambda it: it["date"], reverse=True)
    return _env(True, tier=T2, asof=meta.get("du_lieu_toi"), src=src, items=items,
                upcoming=sorted((it for it in items if it["date"] >= today), key=lambda it: it["date"]),
                last=next((it for it in items if it["date"] < today), None))


def _tl_rows(tk: str, today: str) -> list:
    from chaebol_map_data_codong2 import insider_rows
    out = [{"date": it["date"], "kind": "von", "code": it["code"], "title": it["title"], "qty": None,
            "ratio": it["ratio"], "status": None, "tier": T2} for it in capital_actions(tk, today)["items"]]
    out += [{"date": it["date"], "kind": "dhcd", "code": it["code"], "title": it["title"], "qty": None, "ratio": None,
             "status": None, "tier": T2} for it in agm_events(tk, today)["items"]]
    _, ev = _ev_all(tk)
    out += [{"date": iso(r.get("displayDate1")) or iso(r.get("publicDate")), "kind": "khac", "code": r.get("eventCode"),
             "title": r.get("eventTitleVi"), "qty": None, "ratio": None, "status": None, "tier": T2}
            for r in ev or [] if r.get("eventCode") in ("MOVE", "NLIS", "SUSP", "MA")]
    for r in insider_rows(tk, today)["rows"]:
        if r["status"] == "da_xong" and r["valid"] and r["acq_now"]:
            q = _vq(r["side"] * r["acq_now"], r["acq_tier"], r["date"], f"vc_lk/{tk}/insider-transaction", "cp quy đổi")
            out.append({"date": r["date"], "kind": "noi_bo", "code": r["code"], "title": r["title"], "qty": q,
                        "ratio": None, "status": "chuyen_giao" if r["pair"] else "da_xong", "tier": r["acq_tier"]})
        elif r["status"] == "dang_ky" and (r["end"] or "") >= today and r["register"]:
            q = _vq(r["register"], T2, r["public"], f"vc_lk/{tk}/insider-transaction.shareRegister", "KL đăng ký")
            out.append({"date": r["date"], "kind": "dang_ky_mo", "code": r["code"], "title": r["title"], "qty": q,
                        "ratio": None, "status": "dang_ky", "tier": T2})
    return [r for r in out if r["date"]]


def _years(rows: list) -> list:
    by: dict = {}
    for r in rows:
        by.setdefault(int(r["date"][:4]), []).append(r)
    out = []
    for y in sorted(by, reverse=True):
        rs = by[y]
        top = sorted(rs, key=lambda r: -(abs(r["qty"].value) if r["qty"] is not None and not r["qty"].can
                                         else (r["ratio"] or 0) * 1e9))[:3]
        out.append({"year": y, "counts": dict(Counter(r["kind"] for r in rs)), "top3": [r["title"] for r in top]})
    return out


def timeline(tk: str, today: str, months_full: int = 24, cap_rows: int = 60) -> dict:
    """Dòng thời gian: ≤months_full tháng đầy đủ (≤cap_rows dòng, giảm dần) + phần cũ gộp theo năm."""
    rows = sorted(_tl_rows(tk, today), key=lambda r: (r["date"], r["kind"]), reverse=True)
    cut = lui_thang(today, months_full)
    recent = [r for r in rows if r["date"] >= cut]
    full, rest = recent[:cap_rows], recent[cap_rows:] + [r for r in rows if r["date"] < cut]
    ca = capital_actions(tk, today)
    ok = bool(rows) or ca["ok"]
    return _env(ok, None if ok else ca["why"], tier=T2, asof=today, src=f"vc_lk/{tk} (events-v2, events-all, insider)",
                rows=full, years=_years(rest), pre2010_why=ca["pre2010_why"])


def _cc_items(o: dict) -> list:
    out = []
    for f in _CC_FIELDS:
        x = o.get(f)
        for it in (x if isinstance(x, list) else [x]):
            if isinstance(it, dict) and it.get("text") and it.get("bac") and it.get("nguon"):
                out.append({"field": f, "text": it["text"], "tier": it["bac"], "src": _src(it["nguon"]),
                            "unv": it["bac"] == UNV})
    return out


def _src(n) -> str:
    return " | ".join(str(x) for x in n) if isinstance(n, list) else str(n)


def _cauchuyen_view(tk: str) -> dict:
    d = read_json(bridge() / "fft_cauchuyen.json", quiet=True) or {}
    o = (d.get("ma") or {}).get(tk)
    if not isinstance(o, dict):
        return _env(False, "fft_cauchuyen chưa có mã này", src="fft_cauchuyen.json", items=[], events=[],
                    muc_dich_keo=None, thau_tom=None, n_unv=0, asof=d.get("cap_nhat"))
    items = _cc_items(o)
    evs = [{"id": e.get("id"), "date": iso(e.get("ngay")), "loai": e.get("loai"), "chu_the": e.get("chu_the"),
            "text": e.get("mo_ta"), "tier": e.get("bac"),
            "window": ({"tu": iso(e["cua_so"].get("tu")), "den": iso(e["cua_so"].get("den"))}
                       if isinstance(e.get("cua_so"), dict) else None)}
           for e in o.get("su_kien") or [] if isinstance(e, dict) and e.get("bac") and e.get("nguon")]
    one = {f: next(({"text": i["text"], "tier": i["tier"], "src": i["src"]} for i in items if i["field"] == f), None)
           for f in ("muc_dich_keo", "thau_tom")}
    return _env(True, tier=None, asof=d.get("cap_nhat"), src=f"fft_cauchuyen.json#ma.{tk}", items=items, events=evs,
                n_unv=sum(1 for i in items if i["unv"]), **one)


def _owner_intent(tk: str) -> list:
    d = read_json(sys_dir() / "early_detection" / "owner_intent.json", quiet=True) or {}
    b = (d.get("by_ticker") or {}).get(tk) or {}
    evs = b.get("events") if isinstance(b, dict) else b
    return [{"date": iso(e.get("date")), "approx": bool(e.get("date_approx")), "title": e.get("title"),
             "detail": e.get("detail"), "tier": T3 if e.get("verified") else UNV}
            for e in evs or [] if isinstance(e, dict) and e.get("auto") is False]


def _nq(tk: str):
    d = read_json(sys_dir() / "openclaw_hdcv" / "data" / "nq68_nq79.json", quiet=True) or {}
    t = (d.get("tier_a") or {}).get(tk)
    if not isinstance(t, dict):
        return None
    return {"nq": t.get("nq"), "chaebol": t.get("chaebol"), "founder": t.get("founder"),
            "as_of": iso((d.get("_meta") or {}).get("as_of")) or "2026-05-23", "tier": EST,
            "src": "openclaw_hdcv/data/nq68_nq79.json#tier_a"}


def intent_sources(tk: str) -> dict:
    """Nguồn ý đồ theo bậc TỪNG mục: nhãn chủ thể, fft_cauchuyen (bỏ tieu_de), vùng gom, owner_intent tuyển chọn,
    khung NQ (không score/phase/verdict), dữ kiện facts_f*."""
    from chaebol_map_data_codong2 import chu_the_label
    ma = ((read_json(bridge() / "data" / "fft_langkinh.json", quiet=True) or {}).get("ma") or {}).get(tk) or {}
    vg = (ma.get("cau_chuyen") or {}).get("vung_gia_gom")
    facts = [{"text": f.get("noi_dung"), "tier": f.get("bac"), "asof": iso(f.get("ngay")),
              "src": f.get("nguon") or f"{f.get('file')}#{f.get('id')}"} for f in facts_for(ma=tk)]
    return {"chu_the": chu_the_label(tk), "cauchuyen": _cauchuyen_view(tk), "vung_gom": vg,
            "owner_intent": _owner_intent(tk), "nq": _nq(tk), "facts": facts}


# ───────────────────────────── 4.8 bảng tổng 109 mã ─────────────────────────────

def _pv(price: dict, k: str) -> V:
    x = (price or {}).get(k)
    return x if isinstance(x, V) else can_data("chưa có số giá/dòng tiền cho mã này")


def summary_row(tk: str, price: dict, today: str, groups: dict) -> dict:
    """Một dòng bảng tổng: chỉ V hoặc None (không chuỗi nhãn)."""
    from chaebol_map_data_codong2 import insider_net, insider_yearly
    nb = insider_net(tk, lui_thang(today, 12), today, today, by="group")
    yr = insider_yearly(tk, today)
    cf, fv = codong_full(tk), fund_view(tk)
    src = f"vc_lk/{tk}/insider-transaction"
    return {"tk": tk, "nhom": (groups.get("grp") or {}).get(tk), "vc": bool((groups.get("has_vc") or {}).get(tk)),
            "lk": bool((groups.get("has_lk") or {}).get(tk)), "tuan": (price or {}).get("weeks"),
            "den": (price or {}).get("den"), "nb_rong_12t": nb["net_pct"],
            "dk_mo": _vn(len(yr["open"]), T2, today, src) if yr["ok"] else can_data(yr["why"], src),
            "tt_dot_bien_52t": _pv(price, "deal_spikes_52w"), "d_nn_1y_pp": _pv(price, "d_fo_1y_pp"),
            "fft_pct3y": _pv(price, "fft_pct3y"), "fft_pall": _pv(price, "fft_pall"),
            "codong_qs": _vn(cf["n_qs"], T3, cf["asof"], cf["src"], f"{cf['n_qs']}/{cf['n_moc']} mốc quan sát")
            if cf["ok"] else None,
            "quy_n": fv["n_funds"] if fv["ok"] else None}


def summary_rows(order: list, price_fn, today: str, groups: dict) -> list:
    """Bảng tổng đúng thứ tự `order`; price_fn(tk, today) → dict P.price_summary (lỗi → ô [CẦN DATA] + cảnh báo)."""
    out = []
    for tk in order:
        try:
            price = price_fn(tk, today) if price_fn else {}
        except Exception as e:  # noqa: BLE001  (một mã lỗi không làm vỡ bảng)
            warn(f"codong2 summary {tk}: price_fn lỗi {e}")
            price = {}
        out.append(summary_row(tk, price, today, groups))
    return out
