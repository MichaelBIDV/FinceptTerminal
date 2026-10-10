"""
chaebol_map_data_codong2_dong: phần dòng tiền (spec codong_v2 §5.4) của P2 data_price, tách khỏi
chaebol_map_data_codong2_gia.py vì giới hạn 800 dòng. Tab dùng qua `import chaebol_map_data_codong2_gia as P`
(P.flow_window, P.flow_windows, P.yearly_flows, P.deal_weekly_spikes, P.deal_sessions, P.cost_estimate).

NN ròng (tổng khớp + thoả thuận; tách chỉ khi cột Matched/Deal có số ≥ 90% phiên), tự doanh và phần dư −(NN + TD) CHỈ trên
phiên có bản ghi tự doanh, thoả thuận (tỷ trọng, premium, tuần đột biến theo trung vị các tuần CÓ thoả thuận), phiên
thoả thuận lớn đối chiếu cửa sổ nội bộ ±5 phiên, giá vốn ước (thoả thuận nếu khớp KL, ngược lại VWAP khớp).
CHỈ ĐỌC; stdlib; không mạng; không ghi tệp.
"""
from __future__ import annotations

import bisect
import statistics
from datetime import date, timedelta

from chaebol_map_data_codong2_gia import (WHY_NO_VC, _agg, _base, _dfo, _env, _lastv, _monday, _num,
                                          _pct, _sig_tk, _src, _td_vals)
from chaebol_map_data_nen import EST, T2, UNV, _finite, _memo, can_data, ddmmyyyy, iso, lui_thang

__all__ = ["SPIKE_RULE", "SPIKE_X", "SPIKE_SHARE", "SPLIT_MIN", "flow_window", "flow_windows", "yearly_flows",
           "deal_weekly_spikes", "deal_sessions", "cost_estimate"]

SPIKE_X, SPIKE_SHARE = 5.0, 20.0      # ≥ 5 × trung vị tuần có thoả thuận và tỷ trọng ≥ 20%
SPLIT_MIN = 0.9                       # NN tách khớp/TT cần cột Matched/Deal có số ≥ 90% phiên của cửa sổ
SPIKE_RULE = ("tuần đột biến: GT thoả thuận ≥ 5 × trung vị GT các tuần CÓ thoả thuận trong cửa sổ và tỷ trọng thoả "
              "thuận/GTGD ≥ 20%")
WIN_ORDER = ("20p", "63p", "ytd", "1y", "3y", "all")
WHY_PREM_ALL = "tỷ số hai bình quân trên nhiều năm không so được"


def _day_after(d: str) -> str:
    return (date.fromisoformat(d) + timedelta(days=1)).isoformat()


# ───────────────────────────── cửa sổ dòng tiền ─────────────────────────────

def _split(b: dict, g: dict, src: str, d1: str):
    if g["n"] and g["sp_n"] >= SPLIT_MIN * g["n"]:
        return {"khop": _num(g["sp_khop"], T2, d1, f"{b['base']}.foreignNetValueMatched", "đ"),
                "tt": _num(g["sp_tt"], T2, d1, f"{b['base']}.foreignNetValueDeal", "đ")}
    return can_data(f"chờ --day-du (mới {b['sp_total']} phiên có số)", src, d1, "đ")


def _deal_vals(b: dict, g: dict, src: str, d1: str) -> dict:
    """Premium = (Σ GT TT ÷ Σ KL TT quy đổi) ÷ (Σ GT khớp ÷ Σ KL khớp quy đổi) − 1: KL quy về số cp hiện hành trước khi
    chia nên cửa sổ cắt qua GDKHQ không trộn giá danh nghĩa hai phía sự kiện."""
    tot = g["dval"] + g["mval"]
    dp = g["dval"] / g["dvol"] if g["dvol"] > 0 else None
    mp = g["mval"] / g["mvol_m"] if g["mvol_m"] > 0 else None
    return {"dval": _num(g["dval"], T2, d1, src, "đ"),
            "deal_share": _pct(g["dval"] / tot * 100 if tot > 0 else None, EST, d1, src, "GT thoả thuận / (thoả thuận "
                               "+ khớp)", why="không có giao dịch trong cửa sổ", sign=False),
            "premium": _pct((dp / mp - 1) * 100 if dp and mp else None, UNV if g["pre"] else EST, d1, src,
                            "giá TT bình quân / giá khớp bình quân − 1, KL quy về số cp hiện hành",
                            why="không có thoả thuận trong cửa sổ")}


def _flow_v(b: dict, g: dict, d0: str, d1: str) -> dict:
    src, srct = _src(b), _src(b, True)
    tconv = UNV if g["pre"] else EST
    td, du = _td_vals(b, g, srct, d1)
    out = {"d0": d0, "d1": d1, "n": g["n"],
           "nn_vol": _num(g["nn_vol"] if g["nn_n"] else None, tconv, d1, src, "cp", "cp quy đổi về số cp hiện hành",
                          why="không có số khối ngoại trong cửa sổ"),
           "nn_val": _num(g["nn_val"] if g["nn_n"] else None, T2, d1, src, "đ", why="không có số khối ngoại trong cửa sổ"),
           "nn_split": _split(b, g, src, d1), "d_fo_pp": _dfo(b, d0, d1), "td_val": td,
           "td_vol": (can_data(td.note, srct, d1, "cp") if td.can else
                      _num(g["td_vol"], tconv, d1, srct, "cp", "cp quy đổi")),
           "td_cover": [g["td_k"], g["n"]], "du_val": du, "du_cover": g["du_k"]}
    out.update(_deal_vals(b, g, src, d1))
    return out


def flow_window(tk: str, d0: str, d1: str) -> dict:
    """Dòng tiền trên phiên ngày trong [d0, d1] (spec §5.4). Không vc_lk → ok False "chưa nạp vc_lk"."""
    d0, d1 = iso(d0), iso(d1)
    return _memo(("cd2p", "flow_window", tk, d0, d1), _sig_tk(tk), lambda: _build_flow(tk, d0, d1))


def _build_flow(tk: str, d0: str, d1: str) -> dict:
    b = _base(tk)
    if not b or not b["vc"]:
        return _env(False, WHY_NO_VC)
    a, z = bisect.bisect_left(b["dates"], d0), b["ph"].at(d1)
    if a > z:
        return _env(False, "không có phiên trong cửa sổ", d0=d0, d1=d1, n=0)
    g = _agg(b, a, z)
    return _env(True, tier=T2, asof=b["dates"][z], src=_src(b, True), note=f"phiên {ddmmyyyy(b['dates'][a])} → "
                f"{ddmmyyyy(b['dates'][z])}", **_flow_v(b, g, d0, d1))


def _win_bounds(b: dict, today: str) -> dict:
    D, n = b["dates"], b["n"]
    d1 = D[-1]
    return {"20p": D[max(n - 20, 0)], "63p": D[max(n - 63, 0)], "ytd": f"{iso(today)[:4]}-01-01",
            "1y": _day_after(lui_thang(d1, 12)), "3y": _day_after(lui_thang(d1, 36)), "all": D[0]}


def flow_windows(tk: str, today: str) -> dict:
    """Sáu cửa sổ: 20/63 phiên cuối, từ 01/01 năm hiện tại, 1 và 3 năm lịch tới phiên cuối, toàn dải."""
    b = _base(tk)
    if not b or not b["vc"]:
        return _env(False, WHY_NO_VC, win={}, order=list(WIN_ORDER), all_from=None)
    d1 = b["dates"][-1]
    win = {k: flow_window(tk, d0, d1) for k, d0 in _win_bounds(b, today).items()}
    if win["all"].get("ok"):          # bản sao: flow_window memo dùng chung, không sửa tại chỗ
        win["all"] = {**win["all"], "premium": can_data(WHY_PREM_ALL, _src(b), d1, "%")}
    return _env(True, tier=T2, asof=d1, src=_src(b, True), win=win, order=list(WIN_ORDER), all_from=b["dates"][0])


def _year_row(b: dict, y: str, ix: list) -> dict:
    D, C = b["dates"], b["C"]
    src = _src(b)
    c0, j0 = next(((C[i], i) for i in ix if _finite(C[i])), (None, -1))
    c1, j1 = _lastv(C, ix)
    g = _agg(b, ix[0], ix[-1])
    td, _ = _td_vals(b, g, _src(b, True), D[ix[-1]])
    return {"year": int(y), "open": _num(c0, T2, D[j0] if j0 >= 0 else None, src, "đ", "đóng điều chỉnh phiên đầu năm", 1),
            "close": _num(c1, T2, D[j1] if j1 >= 0 else None, src, "đ", "đóng điều chỉnh phiên cuối năm", 1),
            "chg_pct": _pct((c1 / c0 - 1) * 100 if c0 and c1 else None, EST, D[ix[-1]], src, "từ đóng phiên đầu năm"),
            "nn_val": _num(g["nn_val"] if g["nn_n"] else None, T2, D[ix[-1]], src, "đ"), "td_val": td,
            "dval": _num(g["dval"], T2, D[ix[-1]], src, "đ")}


def yearly_flows(tk: str) -> dict:
    """Theo năm từ năm niêm yết: đóng đầu/cuối năm (giá điều chỉnh), %, NN ròng, TD ròng, GT thoả thuận."""
    b = _base(tk)
    if not b or not b["vc"]:
        return _env(False, WHY_NO_VC, rows=[])
    ys: dict = {}
    for i, d in enumerate(b["dates"]):
        ys.setdefault(d[:4], []).append(i)
    return _env(True, tier=T2, asof=b["dates"][-1], src=_src(b, True), rows=[_year_row(b, y, ix) for y, ix in ys.items()])


# ───────────────────────────── thoả thuận ─────────────────────────────

def _deal_weeks(b: dict, d0: str, d1: str) -> list:
    wk: dict = {}
    for i in range(bisect.bisect_left(b["dates"], d0), b["ph"].at(d1) + 1):
        w = wk.setdefault(_monday(b["dates"][i]), [0.0, 0.0])
        w[0] += b["DG"][i] if _finite(b["DG"][i]) else 0.0
        w[1] += b["G"][i] if _finite(b["G"][i]) else 0.0
    return sorted(wk.items())


def deal_weekly_spikes(tk: str, d0: str | None = None, d1: str | None = None, years: int = 3) -> dict:
    """Tuần thoả thuận đột biến (spec §5.4): mặc định `years` năm tới phiên cuối; d0/d1 ghi đè."""
    b = _base(tk)
    if not b or not b["vc"]:
        return _env(False, WHY_NO_VC, rule=SPIKE_RULE, median=can_data(WHY_NO_VC), n_weeks=0, n_deal_weeks=0, weeks=[],
                    n_52w=0)
    d1 = iso(d1) or b["dates"][-1]
    d0 = iso(d0) or lui_thang(d1, 12 * years)
    return _memo(("cd2p", "deal_weekly_spikes", tk, d0, d1), _sig_tk(tk), lambda: _build_spikes(b, d0, d1))


def _build_spikes(b: dict, d0: str, d1: str) -> dict:
    wk, src = _deal_weeks(b, d0, d1), _src(b)
    dw = [v[0] for _, v in wk if v[0] > 0]
    base = dict(rule=SPIKE_RULE, n_weeks=len(wk), n_deal_weeks=len(dw), d0=d0, d1=d1)
    if not dw:
        return _env(True, tier=EST, asof=d1, src=src, median=can_data("không có tuần thoả thuận trong cửa sổ", src),
                    weeks=[], n_52w=0, **base)
    med = statistics.median(dw)
    spikes = [{"w": w, "dval": dv, "share": dv / (dv + mv) * 100, "x_med": dv / med} for w, (dv, mv) in wk
              if dv >= SPIKE_X * med and dv / (dv + mv) * 100 >= SPIKE_SHARE]
    cut = (date.fromisoformat(_monday(d1)) - timedelta(weeks=51)).isoformat()
    return _env(True, tier=EST, asof=d1, src=src, note=f"tuần ISO {ddmmyyyy(wk[0][0])} → {ddmmyyyy(wk[-1][0])}",
                median=_num(med, EST, d1, src, "đ", "trung vị GT thoả thuận các tuần có thoả thuận"),
                weeks=sorted(spikes, key=lambda x: x["w"], reverse=True),
                n_52w=sum(1 for x in spikes if x["w"] >= cut), **base)


def _match_rows(b: dict, i: int, windows: list) -> list:
    out = []
    for w in windows or []:
        s, e = iso(w.get("start") or w.get("end")), iso(w.get("end") or w.get("start"))
        if not s:
            continue
        lo, hi = bisect.bisect_left(b["dates"], s) - 5, b["ph"].at(e) + 5
        if lo <= i <= hi:
            out.append(w.get("row"))
    return out


def _session_row(b: dict, i: int, windows: list) -> dict:
    D, src = b["dates"], _src(b)
    dv, dg, k, g = b["DV"][i], b["DG"][i], b["K"][i], b["G"][i]
    dp = dg / dv if _finite(dg) and dv else None
    mv = g / k if _finite(g) and _finite(k) and k > 0 else None
    return {"date": D[i], "dvol": dv, "dval": dg,
            "dprice": _num(dp, T2, D[i], f"{b['base']}.totalDealValue ÷ totalDealVolume", "đ", "giá danh nghĩa", 1),
            "mvwap": _num(mv, EST, D[i], f"{b['base']}.totalMatchValue ÷ totalMatchVolume", "đ", "VWAP khớp phiên", 1),
            "premium": _pct((dp / mv - 1) * 100 if dp and mv else None, EST, D[i], src),
            "match": _match_rows(b, i, windows)}


def deal_sessions(tk: str, years: int = 3, top: int = 10, windows: list | None = None) -> dict:
    """`top` phiên thoả thuận lớn nhất (GT) trong `years` năm; match = id dòng nội bộ có cửa sổ ±5 phiên chứa phiên."""
    b = _base(tk)
    if not b or not b["vc"]:
        return _env(False, WHY_NO_VC, rows=[])
    D = b["dates"]
    a = bisect.bisect_left(D, _day_after(lui_thang(D[-1], 12 * years)))
    ix = [i for i in range(a, b["n"]) if _finite(b["DV"][i]) and b["DV"][i] > 0 and _finite(b["DG"][i])]
    ix = sorted(ix, key=lambda i: (-b["DG"][i], D[i]))[:top]
    return _env(True, tier=T2, asof=D[-1], src=_src(b), note=f"{years} năm tới {ddmmyyyy(D[-1])}; khớp nội bộ ±5 phiên",
                rows=[_session_row(b, i, windows) for i in ix])


# ───────────────────────────── giá vốn ước ─────────────────────────────

def _fadj(b: dict, i: int):
    c, r = b["C"][i], b["CP"][i]
    return c / r if _finite(c) and _finite(r) and r > 0 else None


def _cost_one(b: dict, r: dict, px) -> dict:
    D, src = b["dates"], _src(b)
    s, e = iso(r.get("start") or r.get("end")), iso(r.get("end") or r.get("start"))
    a, z = (bisect.bisect_left(D, s), b["ph"].at(e)) if s else (1, 0)
    base = {"row": r.get("row"), "px": px}
    if a > z:
        cd = can_data("không có phiên trong cửa sổ giao dịch", src)
        return {**base, "method": None, "price": cd, "price_nominal": None, "gap_pct": cd}
    ix = range(a, z + 1)
    dv = sum(b["DV"][i] for i in ix if _finite(b["DV"][i]) and b["DV"][i] > 0)
    qty = r.get("qty")
    if _finite(qty) and qty > 0 and 0.9 * qty <= dv <= 1.1 * qty:
        dg = [(b["DG"][i], b["DV"][i], _fadj(b, i)) for i in ix if _finite(b["DV"][i]) and b["DV"][i] > 0]
        nom = sum(x[0] for x in dg) / dv
        adj = sum(x[0] * x[2] for x in dg if x[2]) / sum(x[1] for x in dg if x[2]) if any(x[2] for x in dg) else None
        price = _num(adj, EST, D[z], src, "đ", "giá thoả thuận danh nghĩa × (đóng điều chỉnh / đóng)", 1)
        nominal, method = _num(nom, T2, D[z], f"{b['base']}.totalDealValue ÷ totalDealVolume", "đ", nd=1), "tt"
    else:
        kg = [(b["G"][i] * _fadj(b, i), b["K"][i]) for i in ix if _finite(b["K"][i]) and b["K"][i] > 0
              and _finite(b["G"][i]) and _fadj(b, i)]
        v = sum(x[0] for x in kg) / sum(x[1] for x in kg) if kg else None
        price = _num(v, EST, D[z], src, "đ", "giả định khớp lệnh: VWAP khớp theo giá điều chỉnh", 1,
                     why="không có phiên khớp trong cửa sổ")
        nominal, method = None, "khop"
    gap = (px.value / price.value - 1) * 100 if not px.can and not price.can and price.value else None
    return {**base, "method": method, "price": price, "price_nominal": nominal, "gap_pct": _pct(gap, EST, D[-1], src)}


def cost_estimate(tk: str, rows: list) -> list:
    """Giá vốn ước từng dòng nội bộ (O đã LOẠI dòng chuyển giao): "tt" khi Σ KL thoả thuận trong [start, end] ∈
    [0.9, 1.1] × qty (giá thoả thuận quy về giá điều chỉnh), ngược lại "khop" (VWAP khớp, giả định); < 1 phiên → [CẦN DATA]."""
    b = _base(tk)
    if not b or not b["vc"]:
        cd = can_data(WHY_NO_VC)
        return [{"row": r.get("row"), "method": None, "price": cd, "price_nominal": None, "px": cd, "gap_pct": cd}
                for r in rows or []]
    pv, j = _lastv(b["C"], range(b["n"]))
    px = _num(pv, T2, b["dates"][j] if j >= 0 else None, f"{b['base']}.closePriceAdjusted", "đ", nd=1)
    return [_cost_one(b, r, px) for r in rows or []]
