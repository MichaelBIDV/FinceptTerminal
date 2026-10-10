"""
chaebol_map_data_dongtien — dòng tiền: NN (khớp + thoả thuận), tự doanh, FlowBar 4 kênh, Σ rổ theo tuần.

Tách từ chaebol_map_data.py (27/09/2026). Sau 08/05/2026 chỉ NN + tự doanh là kênh thật (DESIGN §6.5).
"""
from __future__ import annotations

from chaebol_map_data_nen import *  # noqa: F401,F403
from chaebol_map_data_gia import (_prop, _prop_map, _psrc, _share_events_all, _share_mult, price_history,
                                  share_basis_note, share_events, weekly_ohlcv)
from chaebol_map_data_langkinh import basket

__all__ = [
    "_win", "_basis", "_vol_text", "foreign_net", "prop_net", "flow4", "nqs_flow", "basket_weekly_flow",
]


# ───────────────────────────── dòng tiền ─────────────────────────────

def _win(ph: Cols, n: int, end):
    b = ph.at(end)
    return max(0, b - n + 1), b


def _basis(ph: Cols, a: int, adjust: bool):
    """(sự kiện chia cp sau phiên a, hệ số theo phiên | None). adjust=False hoặc không có sự kiện → ([], None)."""
    evs = [e for e in _share_events_all(ph) if e["i"] > a] if adjust else []
    return evs, (_share_mult(ph) if evs else None)


def _vol_text(x: float, u: str) -> str:
    return js_locale(x / (1e6 if u == "cp" else 1e9), 2) + (" M cp" if u == "cp" else " tỷ")


def foreign_net(tk: str, n: int = 60, end=None, adjust: bool = False) -> dict:
    """NN ròng (khớp + thoả thuận) n phiên tới end: vol (cp), val (đồng). FACT-T2 (tổng vendor).
    V.asof = phiên CUỐI trong cửa sổ thực có số (DESIGN §9 — không phải phiên cuối price-history); trả thêm n_co
    (số phiên có số NN) và last (ngày đó). Phiên vắng không điền 0. adjust=True: KL phiên trước GDKHQ chia/thưởng/
    quyền mua cp quy về số cp hiện hành (share_events, hệ số min(Δcp, 1/bước)) → EST + chú thích; val không đổi."""
    ph = price_history(tk)
    if not ph or not len(ph):
        c = can_data(f"không có vc_lk/{tk}/price-history")
        return {"vol": c, "val": c, "n": 0, "n_co": 0, "last": None}
    a, b = _win(ph, n, end)
    evs, M = _basis(ph, a, adjust)
    NV = ph.col("foreignNetVolumeTotal")
    co = [i for i in range(a, b + 1) if _finite(NV[i])]
    out = {"n": b - a + 1, "n_co": len(co), "last": ph.dates[co[-1]] if co else None, "from": ph.dates[a],
           "to": ph.dates[b]}
    for k, f, u in (("vol", "foreignNetVolumeTotal", "cp"), ("val", "foreignNetValueTotal", "đ")):
        col = ph.col(f)
        ix = [i for i in range(a, b + 1) if _finite(col[i])]
        conv = M is not None and u == "cp"
        s = _sum(col[i] * M[i] for i in ix) if conv else _sum(col[a:b + 1])
        note = f"{b - a + 1} phiên {ddmmyyyy(ph.dates[a])}→{ddmmyyyy(ph.dates[b])}"
        if len(ix) < b - a + 1:
            note += f"; {len(ix)}/{b - a + 1} phiên có số (phiên vắng không điền 0)"
        out[k] = (V(s, _vol_text(s, u), EST if conv else T2, ph.dates[ix[-1]], _psrc(tk, f),
                    note + (f"; {share_basis_note(evs)}" if conv else ""), u)
                  if s is not None else can_data(f"{tk}: {f} trống trong cửa sổ", _psrc(tk, f)))
    if adjust:
        out["adj"] = [(e["date"], e["factor"]) for e in evs]
    return out


def prop_net(tk: str, n: int = 60, end=None, kind: str = "total", adjust: bool = False) -> dict:
    """Tự doanh ròng trong đúng cửa sổ n phiên của price-history. Phiên không có bản ghi KHÔNG điền 0:
    trả tổng các phiên có bản ghi + n_co; complete=False khi thiếu phiên (tự doanh chậm 1–3 phiên).
    V.asof = ngày bản ghi tự doanh CUỐI trong cửa sổ (DESIGN §9), cũng trả ở `last`. adjust=True như foreign_net."""
    ph = price_history(tk)
    if not ph or not len(ph):
        c = can_data(f"không có vc_lk/{tk}/price-history")
        return {"vol": c, "val": c, "n": 0, "n_co": 0, "complete": False, "last": None}
    a, b = _win(ph, n, end)
    evs, M = _basis(ph, a, adjust)
    pm = _prop_map(tk, kind)
    got = [(i, pm[ph.dates[i]]) for i in range(a, b + 1) if ph.dates[i] in pm]
    src = f"vc_lk/{tk}/proprietary-history." + ("totalMatchTradeNet*" if kind == "khop" else "totalTradeNet*")
    pr = _prop(tk)
    note = (f"{len(got)}/{b - a + 1} phiên có bản ghi tự doanh ({ddmmyyyy(ph.dates[a])}→{ddmmyyyy(ph.dates[b])}); "
            f"phiên vắng không điền 0; dữ liệu tự doanh tới {ddmmyyyy(pr.dates[-1]) if pr and len(pr) else '—'}")
    out = {"n": b - a + 1, "n_co": len(got), "complete": len(got) == b - a + 1, "from": ph.dates[a], "to": ph.dates[b],
           "last": ph.dates[got[-1][0]] if got else None}
    for k, j, u in (("vol", 0, "cp"), ("val", 1, "đ")):
        conv = M is not None and u == "cp"
        s = _sum((t[j] * M[i] if conv and _finite(t[j]) else t[j]) for i, t in got)
        at = next((ph.dates[i] for i, t in reversed(got) if _finite(t[j])), None)
        out[k] = (V(s, _vol_text(s, u), EST if conv else T2, at, src,
                    note + (f"; {share_basis_note(evs)}" if conv else ""), u) if s is not None else can_data(note, src))
    if adjust:
        out["adj"] = [(e["date"], e["factor"]) for e in evs]
    return out


def flow4(tk: str, n: int = 60, end=None, adjust: bool = False) -> dict:
    """FlowBar 4 kênh (triệu cp): nn (khớp + thoả thuận), td (KHỚP, như FiinTrade) thật (FACT-T2); ca, tc
    [CẦN DATA]; du = −(nn+td) EST (phần dư, không phải kênh thật); sig [CẦN DATA] cho cửa sổ mới (DESIGN §6.5).
    nn và td mang asof RIÊNG (ngày cuối thực có số của từng kênh); trả thêm nn_n_co/nn_last, td_n_co/td_last
    (tự doanh chậm 1–3 phiên, thưa). adjust=True: KL quy về số cp hiện hành (foreign_net/prop_net)."""
    fn, pn = foreign_net(tk, n, end, adjust=adjust), prop_net(tk, n, end, kind="khop", adjust=adjust)
    out = {"n": fn.get("n"), "from": fn.get("from"), "to": fn.get("to"),
           "nn_n_co": fn.get("n_co"), "nn_last": fn.get("last"), "td_n_co": pn.get("n_co"), "td_last": pn.get("last"),
           "ca": can_data("không có nguồn kênh Cá nhân sau 08/05/2026 (nqs_flow.ca = 0 giả)"),
           "tc": can_data("không có nguồn kênh Tổ chức trong nước sau 08/05/2026"),
           "sig": can_data("tín hiệu BULL/BEAR 4 kênh không tính lại được (thiếu ca/tc)")}
    for k, src in (("nn", fn), ("td", pn)):
        v = src["vol"]
        nt = v.note if k == "td" else f"{v.note}; gồm thoả thuận (tách khớp bị fetcher cắt)"
        out[k] = V(v.value / 1e6, js_fixed(v.value / 1e6, 1), v.tier, v.asof, v.src, nt, "M cp") if not v.can else v
    if not out["nn"].can and not out["td"].can:
        du = -(out["nn"].value + out["td"].value)
        out["du"] = V(du, js_fixed(du, 1), EST, min(out["nn"].asof, out["td"].asof), "−(nn+td)",
                      "phần dư, không phải kênh thật", "M cp")
    else:
        out["du"] = can_data("thiếu nn hoặc td")
    if adjust:
        out["adj"] = fn.get("adj") or []
    return out


def nqs_flow(tk: str) -> dict:
    """alpha_spine/nqs_flow.json: chỉ nn, td thật (tỷ đồng); ca/tc [CẦN DATA] (ca = 0 lấp giả, tc = phần dư)."""
    d = read_json(sys_dir() / "alpha_spine" / "nqs_flow.json", quiet=True) or {}
    r = (d.get("by_ticker") or {}).get(tk)
    if not r:
        c = can_data(f"nqs_flow không có {tk}")
        return {"nn": c, "td": c, "ca": c, "tc": c}
    note = (f"{d.get('source')}; cửa sổ ghi {d.get('window_sessions')} phiên nhưng n={r.get('n')} (tự mâu thuẫn); "
            f"sinh {d.get('generated_at')}")
    asof = iso(f"{r.get('as_of')}/{str(d.get('generated_at', ''))[:4]}") if r.get("as_of") else None
    out = {k: V(r.get(k), js_locale(r.get(k), 2) + " tỷ", T3, asof, f"alpha_spine/nqs_flow.json.{k}", note, "tỷ đ")
           for k in ("nn", "td") if _finite(r.get(k))}
    out["ca"] = can_data("nqs_flow.ca = 0 ở mọi mã (endpoint không trả kênh cá nhân)")
    out["tc"] = can_data("nqs_flow.tc = −(nn+ca+td) là phần dư, không phải số đo")
    return out


def basket_weekly_flow(basket_name: str = "VN30", start=None, end=None, adjust: bool = False) -> V:
    """Ước NN/TD tuần cấp rổ = Σ các mã có cache (EST). VN30/VN100 = rổ HIỆN HÀNH (vnstore.ma.nhom);
    VNINDEX = cổ phiếu HOSE trong vnstore.ma có thư mục vc_lk (độ phủ ghi trong note). Nạp nhiều tệp (~2–3 s).
    Mỗi tuần có nn_last / td_last = phiên cuối trong tuần có số NN / bản ghi tự doanh ở ÍT NHẤT một mã (DESIGN §9 —
    tự doanh chậm 1–3 phiên). adjust=True: KL từng mã quy về số cp hiện hành qua GDKHQ chia/thưởng/quyền mua
    (weekly_ohlcv(adjust=True), cùng thuật toán share_events) — không quy đổi thì cộng KL thô hai cơ sở."""
    if basket_name == "VNINDEX":
        mem = [r[0] for r in db_query("SELECT symbol FROM ma WHERE san='HOSE' AND loai='stock' ORDER BY symbol")]
    else:
        mem = basket(basket_name).value or []
    have = [t for t in mem if (vc_dir() / t / "price-history.json").exists()]
    if not have:
        return can_data(f"không có mã nào của rổ {basket_name} trong vc_lk")
    agg: dict = {}
    conv = []
    for tk in have:
        w = weekly_ohlcv(tk, start, end, vwap=False, adjust=adjust)
        if adjust and not w.can and w.value and share_events(tk, w.value[0]["monday"]):
            conv.append(tk)
        for r in (w.value or []) if not w.can else []:
            g = agg.setdefault(r["monday"], {"monday": r["monday"], "week_end": r["week_end"], "nn_vol": 0.0,
                                              "nn_val": 0.0, "td_vol": 0.0, "td_val": 0.0, "td_khop_vol": 0.0,
                                              "td_khop_val": 0.0, "n_ma": 0, "n_td": 0, "nn_last": None,
                                              "td_last": None})
            g["week_end"] = max(g["week_end"], r["week_end"])
            for f in ("nn_last", "td_last"):
                if r.get(f) and (g[f] is None or r[f] > g[f]):
                    g[f] = r[f]
            g["n_ma"] += 1
            g["nn_vol"] += r["nn_vol"] or 0.0
            g["nn_val"] += r["nn_val"] or 0.0
            if r["td_n"]:
                g["n_td"] += 1
                for f in ("td_vol", "td_val", "td_khop_vol", "td_khop_val"):
                    g[f] += r[f] or 0.0
    rows = [agg[k] for k in sorted(agg)]
    return V(rows, None, EST, rows[-1]["week_end"] if rows else None, f"Σ vc_lk/<mã>/price-history + proprietary ({basket_name})",
             f"độ phủ {len(have)}/{len(mem)} mã; rổ hiện hành áp cho mọi tuần (không có rổ lịch sử); "
             "ca/tc [CẦN DATA]" + ((f"; KL quy về số cp hiện hành qua GDKHQ chia/thưởng/quyền mua ở {len(conv)} mã"
                                   f"{': ' + ', '.join(conv) if conv else ''}") if adjust else ""), "cp/đ")
