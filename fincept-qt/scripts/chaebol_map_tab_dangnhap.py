#!/usr/bin/env python3
"""
chaebol_map_tab_dangnhap: khối hiển thị dữ liệu Vietcap IQ lấy bằng phiên ĐÃ ĐĂNG NHẬP (chaebol_map_data_dangnhap),
dùng chung cho tab VIETCAP IQ (Tổng quan, Quỹ) và tab Cấu trúc cổ đông. Chỉ mode live.

Bậc: số thực tế của vendor T2; năm F của Lợi nhuận KD và "dự phóng năm nay" của KQKD là dự phóng Vietcap, T3. Quỹ:
tổng nhóm quỹ Vietcap theo dõi theo tháng, T2; kỳ có số mã quỹ nắm < 70% trung vị các kỳ bị đánh dấu "chưa đủ quỹ nộp".
"""
from __future__ import annotations

import statistics

import chaebol_map_data_dangnhap as L
from chaebol_map_dom import C, F_MONO, can_data, h, tier, to_fixed, to_locale
from chaebol_map_shell import Card

DASH = "-"
S_TABLE = {"width": "100%", "borderCollapse": "collapse", "fontFamily": F_MONO, "fontSize": 10.5}
S_TH = {"padding": "7px 8px", "textAlign": "right", "color": C.inkD, "fontWeight": 600, "fontSize": 9,
        "letterSpacing": ".08em", "borderBottom": "1px solid " + C.rule, "whiteSpace": "nowrap"}
S_TD = {"padding": "6px 8px", "textAlign": "right", "color": C.ink, "whiteSpace": "nowrap"}
S_TDL = {**S_TD, "textAlign": "left"}
S_SRC = {"fontSize": 9.5, "color": C.inkD, "fontFamily": F_MONO, "lineHeight": 1.7, "marginTop": 8}
EARN = (("revenue", "Doanh thu (tỷ)", "ty"), ("revenueGrowth", "Tăng trưởng doanh thu", "pct"),
        ("NPATMI", "LNST cổ đông mẹ (tỷ)", "ty"), ("NPATMIGrowth", "Tăng trưởng LNST", "pct"),
        ("eps", "EPS (đồng)", "n0"), ("EPSGrowth", "Tăng trưởng EPS", "pct"), ("roe", "ROE", "pct"),
        ("roa", "ROA", "pct"), ("pe", "P/E", "x"), ("pb", "P/B", "x"), ("dividendYield", "Tỷ suất cổ tức", "pct"))
KQ_TEN = {"revenue": "Doanh thu (tỷ)", "revenueGrowth": "Tăng trưởng doanh thu", "npatMi": "LNST cổ đông mẹ (tỷ)",
          "npatMiGrowth": "Tăng trưởng LNST", "grossProfit": "Lãi gộp (tỷ)", "eps": "EPS (đồng)",
          "operatingProfit": "LN hoạt động (tỷ)", "preTaxProfit": "LN trước thuế (tỷ)", "epsGrowth": "Tăng trưởng EPS",
          "roe": "ROE", "roa": "ROA", "pe": "P/E", "pb": "P/B"}
KQ_GIA_TRI = ("prevYearValue", "currentYearForecastValue", "currentYearCumulativeValue", "percentOfCurrentYear")


def _fmt(v, u):
    if v is None:
        return DASH
    if u == "ty":
        return to_locale(v, max_frac=0)
    if u == "pct":
        return to_fixed(v * 100, 1) + "%"
    if u == "x":
        return to_fixed(v, 2)
    return to_locale(v, max_frac=0)


def _col(v):
    return C.inkM if v is None else (C.forest if v > 0 else (C.vermillion if v < 0 else C.inkD))


def _table(heads, rows, left=1):
    th = [h("th", None, x, cls={**S_TH, "textAlign": "left"} if i < left else S_TH) for i, x in enumerate(heads)]
    tr = [h("tr", None, *[h("td", None, c, cls=S_TDL if i < left else S_TD) for i, c in enumerate(r)],
            cls={"borderBottom": "1px solid " + C.rule + "60"}) for r in rows]
    return h("div", {"overflowX": "auto"}, h("table", None, h("thead", None, h("tr", None, *th)),
                                             h("tbody", None, *tr), cls=S_TABLE))


def loi_nhuan_kd(tk, off=False):
    """Bảng Lợi nhuận KD 2023 → TTM → 2026F/2027F (đăng nhập). None nếu chưa có hoặc lớp dữ liệu tắt (off)."""
    f = {"ok": False} if off else L.financial_data(tk)
    if not f["ok"]:
        return None
    cols, du = f["cot"], f["du"]
    heads = ["Lợi nhuận KD"] + [h("span", {"color": C.gold if c.endswith("F") else C.inkD}, c) for c in cols]
    def cell(v, c, u):
        t = _fmt(v, u)
        return [t, tier("T3", f["lay"])] if c.endswith("F") and v is not None else t
    rows = [[[lbl, tier("T2", f["lay"])]] + [cell((du.get(k) or {}).get(c), c, u) for c in cols]
            for k, lbl, u in EARN if du.get(k)]
    return Card(_table(heads, rows),
                h("div", S_SRC, "Nguồn: Vietcap IQ financial-data, lấy bằng phiên đăng nhập của người dùng ngày ",
                  f["lay"] or "?", ". Năm thực tế và TTM ", tier("T2", f["lay"]), " · cột F là dự phóng của Vietcap ",
                  tier("T3", f["lay"]), ", không phải kế hoạch doanh nghiệp."), key="dangnhap.lnkd." + tk)


def kqkd_so_du_phong(tk, off=False):
    """KQKD luỹ kế năm nay so dự phóng năm của Vietcap (earning-result, đăng nhập)."""
    e = {"ok": False} if off else L.earning_result(tk)
    if not e["ok"]:
        return None
    ex = e["extras"]
    nam, luy = ex.get("currentYear"), ex.get("cumulativeQuarter")
    rows = []
    for r in e["rows"]:
        k = r.get("name")
        if all(r.get(f) in (None, 0) for f in KQ_GIA_TRI):     # vendor trả 0 cho chỉ số không áp dụng → bỏ hàng
            continue
        pct = k and k.endswith("Growth")
        u = "pct" if pct else ("n0" if k == "eps" else "tyvnd")
        fm = (lambda v: _fmt(v, "pct")) if pct else ((lambda v: DASH if v is None else to_locale(v / 1e9, max_frac=0))
                                                     if u == "tyvnd" else (lambda v: _fmt(v, "n0")))
        p = r.get("percentOfCurrentYear")
        fc = r.get("currentYearForecastValue")
        rows.append([[KQ_TEN.get(k, k), tier("T2", e["lay"])], fm(r.get("prevYearValue")),
                     [fm(fc), tier("T3", e["lay"])] if fc is not None else DASH,
                     fm(r.get("currentYearCumulativeValue")),
                     h("span", {"color": C.forest if p and p >= 0.75 else C.ink}, to_fixed(p * 100, 1) + "%")
                     if p is not None else DASH])
    return Card(_table(["Chỉ tiêu", "Năm %s" % ((nam or 0) - 1), "Dự phóng %s (Vietcap)" % nam, "Luỹ kế %s" % (luy or ""),
                        "% so dự phóng"], rows),
                h("div", S_SRC, "Nguồn: Vietcap IQ earning-result (phiên đăng nhập, lấy ", e["lay"] or "?",
                  "). Luỹ kế và năm trước ", tier("T2", e["lay"]), " · dự phóng năm là của Vietcap ",
                  tier("T3", e["lay"]), ". % so dự phóng cao giữa năm nghĩa là dự phóng đang thấp hơn thực tế, không "
                  "phải dấu hiệu hành động."), key="dangnhap.kqkd." + tk)


def _thieu(rows):
    ns = [r["so_ma_trong_ky"] for r in rows if r.get("so_ma_trong_ky")]
    med = statistics.median(ns) if ns else 0
    return {r["ky"] for r in rows if med and (r.get("so_ma_trong_ky") or 0) < 0.7 * med}


def _spark(rows, thieu):
    pts = [(r["ky"], r["pct"]) for r in reversed(rows) if r.get("pct") is not None and r["ky"] not in thieu]
    if len(pts) < 3:
        return None
    W, H, P = 600, 90, 6
    vs = [p for _, p in pts]
    lo, hi = min(vs), max(vs)
    hi = hi if hi > lo else lo + 1e-9
    X = lambda i: P + (W - 2 * P) * i / (len(pts) - 1)  # noqa: E731
    Y = lambda v: P + (H - 2 * P) * (1 - (v - lo) / (hi - lo))  # noqa: E731
    d = "M" + " L".join("%.1f %.1f" % (X(i), Y(v)) for i, (_, v) in enumerate(pts))
    lab = lambda x, y, t, a: h("text", None, t, a={"x": x, "y": y, "fontSize": 9, "fill": C.inkD,  # noqa: E731
                                                  "fontFamily": "IBM Plex Mono", "textAnchor": a})
    return h("svg", {"display": "block", "background": C.bg, "borderRadius": 3, "marginBottom": 10},
             h("path", None, a={"d": d, "fill": "none", "stroke": C.gold, "strokeWidth": 1.5}),
             lab(P, H - 1, pts[0][0], "start"), lab(W - P, H - 1, pts[-1][0], "end"),
             lab(W - P, Y(vs[-1]) - 4, to_fixed(vs[-1] * 100, 2) + "%", "end"),
             lab(P, 10, "đỉnh " + to_fixed(hi * 100, 2) + "%", "start"),
             a={"viewBox": "0 0 %d %d" % (W, H), "width": "100%", "height": "auto"})


def quy(tk, off=False, compact=False):
    """Quỹ nắm giữ theo tháng (nhóm quỹ Vietcap theo dõi, phiên đăng nhập). compact: 12 kỳ, 7 cột (tab codong)."""
    if off:
        return None
    f = L.funds(tk)
    if not f["ok"]:
        return Card(h("p", {"fontSize": 11, "color": C.inkD, "margin": 0}, "Nhóm quỹ Vietcap theo dõi ",
                      can_data(f.get("ly_do") or "không có số"), "."), key="dangnhap.quy." + tk)
    rows, thieu = f["rows"], _thieu(f["rows"])
    wins = ("1M", "3M", "1Y") if compact else L.CUA_SO
    body = []
    for r in rows[:12] if compact else rows:
        d = r["delta"]
        flag = r["ky"] in thieu
        body.append([[h("span", {"color": C.vermillion if flag else C.ink}, r["ky"] + (" (chưa đủ quỹ nộp)" if flag else "")),
                      tier("T2", f["lay"])],
                     _fmt(r["so_quy"], "n0"), _fmt(r["kl"], "n0"),
                     to_fixed(r["pct"] * 100, 2) + "%" if r["pct"] is not None else DASH,
                     *([] if compact else [to_locale(r["gia_tri"] / 1e9, max_frac=0) if r["gia_tri"] is not None else DASH]),
                     *[h("span", {"color": _col(d[w][0])}, _fmt(d[w][0], "n0")) for w in wins]])
    heads = (["Kỳ", "Số quỹ", "KL nắm (cp)", "% tổng cp"] + ([] if compact else ["Giá trị (tỷ)"])
             + ["Δ %s (cp)" % w for w in wins])
    return Card(None if compact else _spark(rows, thieu), _table(heads, body),
                h("div", S_SRC, "Nguồn: Vietcap IQ funds/holding theo tháng (tổng nhóm quỹ Vietcap theo dõi, phiên "
                  "đăng nhập, lấy ", f["lay"] or "?", ") ", tier("T2", f["lay"]), ". Đường vàng: % tổng cp do nhóm quỹ "
                  "nắm, bỏ kỳ chưa đủ quỹ nộp. Δ là thay đổi số cp của cả nhóm quỹ, đã gồm quỹ vào/ra danh sách; đây là "
                  "tín hiệu tổ chức, không phải chủ thể. Chi tiết từng quỹ ", can_data("chưa lấy theo từng quỹ"), "."),
                key="dangnhap.quy." + tk)
