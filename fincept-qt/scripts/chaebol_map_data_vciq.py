#!/usr/bin/env python3
"""
chaebol_map_data_vciq, đọc cache Vietcap IQ (state/vc_lk) cho tab "★ VIETCAP IQ" của chaebol_map. CHỈ ĐỌC.

Mỗi hàm trả dict thuần (số thô + ngày + nguồn); tab tự gắn nhãn bậc. Đọc cột theo TÊN (DESIGN §9). Không có tệp →
{"ok": False, "ly_do": ...}. Endpoint lấy bởi vc_lk_fetch.py (bổ sung 05/10/2026): events-all, fs-*, fs-metrics,
statistics-financial, short-financial, valuation, price-earnings, technical, peers, analysis, news, news-detail,
financial-data/earning-result (null khi không đăng nhập), VNINDEX/search-bar, VNINDEX/coverage-universe.

Khung thời gian Thống kê: D/W/M/Q/Y gộp từ phiên ngày; nhãn kỳ = phiên ĐẦU TIÊN của kỳ (khớp cách Vietcap ghi: tuần có
nghỉ lễ 31/08–02/09/2026 mang nhãn 03/09/2026; năm 2026 mang nhãn 05/01/2026). Tổng của kỳ chỉ tính khi MỌI phiên
trong kỳ có số; thiếu một phiên → None (hiển thị "-").
"""
from __future__ import annotations

from datetime import date

from chaebol_map_data_nen import vc

TF = (("D", "Ngày"), ("W", "Tuần"), ("M", "Tháng"), ("Q", "Quý"), ("Y", "Năm"))
TF_ROWS = {"D": 15, "W": 12, "M": 12, "Q": 12, "Y": 20}
EV_GROUPS = (("dividend", "Trả cổ tức - Phát hành thêm", ("DIV", "ISS")),
             ("shareholder", "GD cổ đông lớn & cổ đông nội bộ", ("DDIND", "DDINS", "DDRP", "DDALL")),
             ("agm", "Đại hội cổ đông", ("AGME", "AGMR", "EGME")),
             ("other", "Sự kiện khác", ("AIS", "MA", "MOVE", "NLIS", "OTHE", "RETU", "SUSP")))
FS_SECTIONS = (("fs-income", "INCOME_STATEMENT", "Kết quả kinh doanh"),
               ("fs-balance", "BALANCE_SHEET", "Bảng cân đối kế toán"),
               ("fs-cashflow", "CASH_FLOW", "Lưu chuyển tiền tệ"),
               ("fs-note", "NOTE", "Thuyết minh"))


def _d(s) -> str | None:
    return str(s)[:10] if s else None


def meta(tk: str, ep: str) -> dict:
    m, du = vc(tk, ep)
    if m is None:
        return {"co_tep": False, "ly_do": f"chưa có state/vc_lk/{tk}/{ep}.json"}
    return {"co_tep": du is not None, "lay_luc": m.get("lay_luc"), "toi": m.get("du_lieu_toi"), "n": m.get("n"),
            "t_lay": (m.get("t_lay") or m.get("lay_luc") or "")[:10] or None, "tu_som": m.get("tu_som")}


def _rows(tk: str, ep: str) -> list[dict]:
    """Bản ghi list[dict] bất kể dạng cột/bản ghi."""
    _, du = vc(tk, ep)
    if isinstance(du, dict) and "cot" in du:
        return [dict(zip(du["cot"], h)) for h in du.get("hang") or []]
    return du if isinstance(du, list) else []


# ───────────────────────────── hồ sơ ─────────────────────────────

def coverage_row(tk: str) -> dict | None:
    _, du = vc("VNINDEX", "coverage-universe")
    return next((x for x in du or [] if isinstance(x, dict) and x.get("ticker") == tk), None)


def search_row(tk: str) -> dict | None:
    _, du = vc("VNINDEX", "search-bar")
    return next((x for x in du or [] if isinstance(x, dict) and x.get("code") == tk), None)


def profile(tk: str) -> dict:
    m, det = vc(tk, "details")
    det = det if isinstance(det, dict) else {}
    sb = search_row(tk) or {}
    st = vc(tk, "shareholder-structure")[1] or {}
    rows = _rows(tk, "price-history")
    last = rows[-1] if rows else {}
    icb = [((sb.get(f"icbLv{i}") or {}).get("name")) for i in (1, 2, 3, 4)]
    return {"ok": bool(det or rows), "ten": det.get("viOrganName") or sb.get("name"),
            "ten_ngan": det.get("viOrganShortName") or sb.get("shortName"), "san": sb.get("floor"),
            "nganh": [x for x in icb if x], "niem_yet": _d(det.get("listingDate")),
            "gia": last.get("closePrice"), "gia_ngay": _d(last.get("tradingDate")),
            "doi_pct": _chg(rows, len(rows) - 1, 1), "von_hoa": _mcap_last(rows),
            "cp_luu_hanh": _last_nn(rows, "totalShares"), "free_float": det.get("freeFloatPercentage"),
            "nn_so_huu": _last_nn(rows, "foreignOwnedPercentage"), "room_nn": det.get("maximumForeignPercentage"),
            "nha_nuoc": st.get("statePercentage"), "hdqt": st.get("bodPercentage"),
            "to_chuc": st.get("institutionPercentage"), "kl_tb_1t": det.get("averageMatchVolume1Month"),
            "cao_1y": det.get("highestPrice1Year"), "thap_1y": det.get("lowestPrice1Year"),
            "rating": det.get("rating"), "tp": det.get("targetPrice"), "upside": det.get("upsideToTargetPercent"),
            "rating_ngay": _d(det.get("ratingAsOf")), "analyst": det.get("analyst"),
            "t_lay": ((m or {}).get("t_lay") or (m or {}).get("lay_luc") or "")[:10] or None,
            "profile": det.get("profile")}


def _last_nn(rows: list[dict], k: str):
    """(giá trị, ngày) khác None gần nhất, DESIGN §9 bẫy phiên mới thiếu số."""
    for r in reversed(rows):
        if r.get(k) is not None:
            return r[k], _d(r.get("tradingDate"))
    return None, None


def _mcap_last(rows: list[dict]):
    """(vốn hoá, ngày) = giá đóng phiên cuối × số cp gần nhất có số; thiếu thì marketCap gần nhất (như bảng Thống kê)."""
    sh, _ = _last_nn(rows, "totalShares")
    if rows and rows[-1].get("closePrice") and sh:
        return rows[-1]["closePrice"] * sh, _d(rows[-1].get("tradingDate"))
    return _last_nn(rows, "marketCap")


def _chg(rows: list[dict], i: int, back: int):
    if i - back < 0:
        return None
    a, b = rows[i].get("closePriceAdjusted"), rows[i - back].get("closePriceAdjusted")
    return (a / b - 1) * 100 if a and b else None


# ───────────────────────────── Thống kê D/W/M/Q/Y ─────────────────────────────

def _key(d: str, tf: str):
    y, m, dd = int(d[:4]), int(d[5:7]), int(d[8:10])
    if tf == "D":
        return d
    if tf == "W":
        iy, iw, _ = date(y, m, dd).isocalendar()
        return (iy, iw)
    if tf == "M":
        return (y, m)
    if tf == "Q":
        return (y, (m - 1) // 3)
    return y


def _groups(rows: list[dict], tf: str) -> list[list[dict]]:
    out, cur, ck = [], [], None
    for r in rows:
        d = _d(r.get("tradingDate"))
        if not d:
            continue
        k = _key(d, tf)
        if k != ck and cur:
            out.append(cur)
            cur = []
        ck = k
        cur.append(r)
    if cur:
        out.append(cur)
    return out


def _sum_all(g: list[dict], k: str):
    xs = [r.get(k) for r in g]
    return None if any(x is None for x in xs) else sum(xs)


GIA_COT = ("thay_doi", "thay_doi_pct", "dong", "mo", "cao", "thap", "kl_khop", "gt_khop", "kl_tt", "gt_tt", "kl",
           "gt", "chua_khop_mua", "chua_khop_ban", "von_hoa")
NN_COT = ("rong_kl", "rong_gt", "mua_kl", "mua_gt", "ban_kl", "ban_gt", "khop_rong_kl", "khop_rong_gt", "tt_rong_kl",
          "tt_rong_gt", "so_huu_pct", "room_con")
CC_COT = ("chua_khop_mua", "chua_khop_ban", "lenh_mua", "lenh_ban", "kl_dat_mua", "kl_dat_ban", "kltb_mua",
          "kltb_ban", "chenh_lech")
TD_COT = ("rong_kl", "rong_gt", "mua_kl", "mua_gt", "ban_kl", "ban_gt", "khop_rong_kl", "khop_rong_gt", "tt_rong_kl",
          "tt_rong_gt")


def _gia(g, prev):
    a, b = g[-1], prev[-1] if prev else None
    pa, pb = a.get("closePriceAdjusted"), (b or {}).get("closePriceAdjusted")
    pct = (pa / pb - 1) * 100 if pa and pb else None
    close = a.get("closePrice")
    return {"thay_doi": close - close / (1 + pct / 100) if close and pct is not None else None, "thay_doi_pct": pct,
            "dong": close, "mo": g[0].get("openPrice"),
            "cao": max((r["highestPrice"] for r in g if r.get("highestPrice") is not None), default=None),
            "thap": min((r["lowestPrice"] for r in g if r.get("lowestPrice") is not None), default=None),
            "kl_khop": _sum_all(g, "totalMatchVolume"), "gt_khop": _sum_all(g, "totalMatchValue"),
            "kl_tt": _sum_all(g, "totalDealVolume"), "gt_tt": _sum_all(g, "totalDealValue"),
            "kl": _sum_all(g, "totalVolume"), "gt": _sum_all(g, "totalValue"),
            "chua_khop_mua": _sum_all(g, "totalBuyUnmatchedVolume"),
            "chua_khop_ban": _sum_all(g, "totalSellUnmatchedVolume"), "von_hoa": _mcap(g)}


def _mcap(g):
    """Vốn hoá cuối kỳ = giá đóng phiên cuối × số cp gần nhất có số (như Vietcap; marketCap phiên mới hay thiếu)."""
    sh = g[-1].get("_sh")
    c = g[-1].get("closePrice")
    return c * sh if c and sh else _last_nn(g, "marketCap")[0]


def _nn(g, prev):
    a = g[-1]
    return {"rong_kl": _sum_all(g, "foreignNetVolumeTotal"), "rong_gt": _sum_all(g, "foreignNetValueTotal"),
            "mua_kl": _sum_all(g, "foreignBuyVolumeTotal"), "mua_gt": _sum_all(g, "foreignBuyValueTotal"),
            "ban_kl": _sum_all(g, "foreignSellVolumeTotal"), "ban_gt": _sum_all(g, "foreignSellValueTotal"),
            "khop_rong_kl": _sum_all(g, "foreignNetVolumeMatched"), "khop_rong_gt": _sum_all(g, "foreignNetValueMatched"),
            "tt_rong_kl": _sum_all(g, "foreignNetVolumeDeal"), "tt_rong_gt": _sum_all(g, "foreignNetValueDeal"),
            "so_huu_pct": _last_nn(g, "foreignOwnedPercentage")[0], "room_con": a.get("foreignCurrentRoom")}


def _cc(g, prev):
    bm, sm = _sum_all(g, "totalBuyTrade"), _sum_all(g, "totalSellTrade")
    bv, sv = _sum_all(g, "totalBuyTradeVolume"), _sum_all(g, "totalSellTradeVolume")
    return {"chua_khop_mua": _sum_all(g, "totalBuyUnmatchedVolume"),
            "chua_khop_ban": _sum_all(g, "totalSellUnmatchedVolume"), "lenh_mua": bm, "lenh_ban": sm,
            "kl_dat_mua": bv, "kl_dat_ban": sv, "kltb_mua": bv / bm if bv is not None and bm else None,
            "kltb_ban": sv / sm if sv is not None and sm else None,
            "chenh_lech": bv - sv if bv is not None and sv is not None else None}


def _td(g, prev):
    return {"rong_kl": _sum_all(g, "totalTradeNetVolume"), "rong_gt": _sum_all(g, "totalTradeNetValue"),
            "mua_kl": _sum_all(g, "totalBuyTradeVolume"), "mua_gt": _sum_all(g, "totalBuyTradeValue"),
            "ban_kl": _sum_all(g, "totalSellTradeVolume"), "ban_gt": _sum_all(g, "totalSellTradeValue"),
            "khop_rong_kl": _sum_all(g, "totalMatchTradeNetVolume"),
            "khop_rong_gt": _sum_all(g, "totalMatchTradeNetValue"),
            "tt_rong_kl": _sum_all(g, "totalDealTradeNetVolume"), "tt_rong_gt": _sum_all(g, "totalDealTradeNetValue")}


KIND = {"gia": ("price-history", GIA_COT, _gia), "nn": ("price-history", NN_COT, _nn),
        "cc": ("price-history", CC_COT, _cc), "td": ("proprietary-history", TD_COT, _td)}


def stats(tk: str, kind: str, tf: str, n: int | None = None) -> dict:
    """Bảng Thống kê một loại × một khung: {"cot", "rows": [{"ky": dd, **giá trị}], "n_ky", "tu", "toi", "tong"}.
    rows mới nhất trước; "tong"/"tb" = tổng/trung bình trên CÁC KỲ HIỂN THỊ (như dòng Tổng/Trung bình của Vietcap)."""
    ep, cot, fn = KIND[kind]
    rows = [r for r in _rows(tk, ep) if _d(r.get("tradingDate"))]
    rows.sort(key=lambda r: r["tradingDate"])
    sh = None
    for r in rows:                                  # số cp mang tiếp qua phiên vendor bỏ trống (DESIGN §9)
        sh = r.get("totalShares") if r.get("totalShares") is not None else sh
        r["_sh"] = sh
    if not rows:
        return {"ok": False, "ly_do": f"chưa có {ep} cho {tk}", "cot": cot, "rows": []}
    gs = _groups(rows, tf)
    out = [dict(ky=_d(g[0]["tradingDate"]), **fn(g, gs[i - 1] if i else None)) for i, g in enumerate(gs)]
    n = n or TF_ROWS[tf]
    shown = out[-n:][::-1]
    tong = {c: (sum(r[c] for r in shown) if shown and all(r[c] is not None for r in shown) else None)
            for c in cot if c.endswith(("_kl", "_gt")) or c in ("kl", "gt", "kl_khop", "gt_khop", "kl_tt", "gt_tt")
            or c.startswith(("chua_khop", "lenh_", "kl_dat_"))}
    return {"ok": True, "cot": cot, "rows": shown, "n_ky": len(out), "tu": _d(rows[0]["tradingDate"]),
            "toi": _d(rows[-1]["tradingDate"]), "tong": tong, "ep": ep, **meta(tk, ep)}


def insider(tk: str, n: int = 40) -> dict:
    rows = sorted(_rows(tk, "insider-transaction"), key=lambda r: str(r.get("publicDate") or ""), reverse=True)
    out = [{"ten": r.get("traderNameVi") or r.get("traderOrganNameVi") or r.get("eventTitleVi"),
            "chuc_vu": r.get("traderPositionVi") or r.get("roleNameVi"), "loai": r.get("actionTypeVi"),
            "dang_ky": r.get("shareRegister"), "truoc": r.get("shareBeforeTrade"), "thuc_hien": r.get("shareAcquire"),
            "sau": r.get("shareAfterTrade"), "thong_bao": _d(r.get("publicDate")), "bat_dau": _d(r.get("startDate")),
            "ket_thuc": _d(r.get("endDate")), "trang_thai": r.get("tradeStatusVi"), "nguon": r.get("sourceUrlVi")}
           for r in rows]
    return {"ok": bool(rows), "rows": out[:n], "n": len(out), **meta(tk, "insider-transaction")}


# ───────────────────────────── tài chính ─────────────────────────────

def fin(tk: str, ep: str, per: str = "year", n: int = 8) -> dict:
    """BCTC một bảng: {"ky": [nhãn], "rows": [(level, tên, [giá trị VND])], "cong_bo": ngày CB mới nhất}."""
    sec = next((s for e, s, _ in FS_SECTIONS if e == ep), None)
    _, du = vc(tk, ep)
    _, mt = vc(tk, "fs-metrics")
    if not isinstance(du, dict) or not isinstance(mt, dict):
        return {"ok": False, "ly_do": f"chưa có {ep}/fs-metrics cho {tk}"}
    recs = du.get("years" if per == "year" else "quarters") or []
    recs = sorted(recs, key=lambda r: (r.get("yearReport") or 0, r.get("lengthReport") or 0))[-n:]
    ky = [str(r.get("yearReport")) if per == "year" else "Q%s %s" % (r.get("lengthReport"), r.get("yearReport"))
          for r in recs]
    rows = []
    for f in mt.get(sec) or []:
        k = str(f.get("field") or "").lower()
        vals = [r.get(k) for r in recs]
        if any(v not in (None, 0) for v in vals):
            rows.append((int(f.get("level") or 1), f.get("titleVi") or f.get("titleEn") or k, vals))
    cb = max((_d(r.get("publicDate")) or "" for r in recs), default="") or None
    return {"ok": bool(rows), "ky": ky, "rows": rows, "cong_bo": cb, **meta(tk, ep)}


RATIO_ROWS = (("pe", "P/E", "x"), ("pb", "P/B", "x"), ("ps", "P/S", "x"), ("evToEbitda", "EV/EBITDA", "x"),
              ("roe", "ROE", "%"), ("roa", "ROA", "%"), ("roic", "ROIC", "%"), ("grossMargin", "Biên gộp", "%"),
              ("ebitMargin", "Biên EBIT", "%"), ("afterTaxProfitMargin", "Biên LN sau thuế", "%"),
              ("netInterestMargin", "NIM", "%"), ("npl", "Nợ xấu (NPL)", "%"), ("casaRatio", "CASA", "%"),
              ("cir", "CIR", "%"), ("car", "CAR", "%"), ("ldrLoanDepositRatio", "LDR", "%"),
              ("debtToEquity", "Nợ vay/VCSH", "x"), ("currentRatio", "Thanh toán hiện hành", "x"),
              ("quickRatio", "Thanh toán nhanh", "x"), ("dividendYield", "Tỷ suất cổ tức", "%"),
              ("cashCycle", "Chu kỳ tiền (ngày)", "n"))


def ratios(tk: str, n: int = 8) -> dict:
    rs = sorted(_rows(tk, "statistics-financial"), key=lambda r: (r.get("yearReport") or 0, r.get("quarter") or 0))
    rs = rs[-n:]
    ky = ["Q%s %s" % (r.get("quarter"), r.get("yearReport")) for r in rs]
    rows = [(lbl, u, [r.get(k) for r in rs]) for k, lbl, u in RATIO_ROWS if any(r.get(k) is not None for r in rs)]
    return {"ok": bool(rows), "ky": ky, "rows": rows, **meta(tk, "statistics-financial")}


EARN_ROWS = (("revenue", "Doanh thu (tỷ)", "ty"), ("revenueGrowth", "Tăng trưởng DT", "%"),
             ("NPATMI", "LNST cổ đông mẹ (tỷ)", "ty"), ("NPATMIGrowth", "Tăng trưởng LNST", "%"),
             ("eps", "EPS (VND)", "n"), ("EPSGrowth", "Tăng trưởng EPS", "%"), ("roe", "ROE", "%"),
             ("roa", "ROA", "%"), ("pe", "P/E", "x"), ("pb", "P/B", "x"), ("dividendYield", "Tỷ suất cổ tức", "%"))


def earnings(tk: str) -> dict:
    """Khối Lợi nhuận KD (financial-data): năm F = dự phóng Vietcap (SS-T3). Mọi ô null ⇒ bị khoá khi chưa đăng nhập."""
    _, du = vc(tk, "financial-data")
    if not isinstance(du, dict):
        return {"ok": False, "ly_do": "chưa lấy financial-data"}
    cols = list((du.get("revenue") or {}).keys())
    rows = [(lbl, u, [((du.get(k) or {}).get(c)) for c in cols]) for k, lbl, u in EARN_ROWS]
    khoa = all(v is None for _, _, vs in rows for v in vs)
    return {"ok": not khoa, "khoa_dang_nhap": khoa, "cot": cols, "rows": rows, **meta(tk, "financial-data")}


def annual_from_fs(tk: str) -> dict:
    """Thay khối Lợi nhuận KD khi bị khoá: năm thực tế từ fs-income (DT thuần, LNST cổ đông mẹ), FACT-T2."""
    _, du = vc(tk, "fs-income")
    _, mt = vc(tk, "fs-metrics")
    if not isinstance(du, dict) or not isinstance(mt, dict):
        return {"ok": False}
    fld = {}
    for f in mt.get("INCOME_STATEMENT") or []:
        t = str(f.get("titleVi") or "").lower()
        k = str(f.get("field") or "").lower()
        if "doanh thu thuần" in t and "dt" not in fld:
            fld["dt"] = k
        if ("cổ đông của công ty mẹ" in t or "cổ đông công ty mẹ" in t) and "ln" not in fld:
            fld["ln"] = k
    ys = sorted(du.get("years") or [], key=lambda r: r.get("yearReport") or 0)[-6:]
    rows = []
    for key, lbl in (("dt", "Doanh thu thuần (tỷ)"), ("ln", "LNST cổ đông mẹ (tỷ)")):
        if key in fld:
            vals = [r.get(fld[key]) for r in ys]
            rows.append((lbl, vals, [(v / p - 1) * 100 if v is not None and p not in (None, 0) else None
                                     for p, v in zip([None] + vals[:-1], vals)]))
    return {"ok": bool(rows), "ky": [str(r.get("yearReport")) for r in ys], "rows": rows, **meta(tk, "fs-income")}


def valuation(tk: str) -> dict:
    _, du = vc(tk, "valuation")
    if not isinstance(du, dict):
        return {"ok": False}
    pe = {x.get("year"): x.get("value") for x in du.get("pe") or []}
    pb = {x.get("year"): x.get("value") for x in du.get("pb") or []}
    ys = sorted(set(pe) | set(pb), key=lambda y: y or 0)
    return {"ok": bool(ys), "nam": ys, "pe": [pe.get(y) for y in ys], "pb": [pb.get(y) for y in ys],
            **meta(tk, "valuation")}


# ───────────────────────────── tin, sự kiện, báo cáo ─────────────────────────────

def events(tk: str, n: int = 40) -> dict:
    rows = _rows(tk, "events-all")
    src = "events-all"
    if not rows:                                   # chưa có events-all → dùng events-v2 (chỉ DIV/ISS/AIS)
        rows, src = _rows(tk, "events-v2"), "events-v2"
    out = {}
    for gid, lbl, codes in EV_GROUPS:
        g = sorted((r for r in rows if r.get("eventCode") in codes),
                   key=lambda r: str(r.get("publicDate") or r.get("displayDate1") or ""), reverse=True)
        out[gid] = {"ten": lbl, "n": len(g), "rows": [{
            "cong_bo": _d(r.get("publicDate")), "thuc_hien": _d(r.get("exrightDate") or r.get("startDate")
                                                               or r.get("issueDate") or r.get("displayDate1")),
            "ma_sk": r.get("eventCode"), "ten": r.get("eventTitleVi") or r.get("eventNameVi"),
            "loai": r.get("actionTypeVi"), "ty_le": r.get("exerciseRatio"), "tien": r.get("valuePerShare"),
            "dkcc": _d(r.get("recordDate")), "thanh_toan": _d(r.get("payoutDate")),
            "ket_thuc": _d(r.get("endDate"))} for r in g[:n]]}
    return {"ok": bool(rows), "nguon": src, "groups": out, **meta(tk, src)}


def news(tk: str, n: int = 60) -> dict:
    rows = sorted(_rows(tk, "news"), key=lambda r: str(r.get("publicDate") or ""), reverse=True)
    _, det = vc(tk, "news-detail")
    det = det if isinstance(det, dict) else {}
    out = [{"ngay": str(r.get("publicDate") or "")[:16], "tieu_de": r.get("newsTitle"), "id": r.get("id"),
            "cbtt": str(r.get("newsTitle") or "").startswith(tk + ":"),
            "tep": (det.get(r.get("id")) or {}).get("tep_dinh_kem") or [],
            "nguon": (det.get(r.get("id")) or {}).get("newsSourceLink")} for r in rows]
    return {"ok": bool(rows), "rows": out[:n], "n": len(out), "n_cbtt": sum(1 for x in out if x["cbtt"]),
            "n_tep": sum(len(x["tep"]) for x in out), "n_chi_tiet": len(det),
            "dau": out[-1]["ngay"][:10] if out else None, **meta(tk, "news")}


def analysis(tk: str, n: int = 30) -> dict:
    rows = sorted(_rows(tk, "analysis"), key=lambda r: str(r.get("date") or ""), reverse=True)
    out = [{"ngay": _d(r.get("date")), "ten": str(r.get("name") or "").strip(), "loai": r.get("pageName")}
           for r in rows]
    return {"ok": bool(rows), "rows": out[:n], "n": len(out), **meta(tk, "analysis")}


def technical(tk: str) -> dict:
    _, du = vc(tk, "technical")
    if not isinstance(du, dict):
        return {"ok": False}
    return {"ok": True, "tong": du.get("gaugeSummary") or {}, "ma": du.get("gaugeMovingAverage") or {},
            "osc": du.get("gaugeOscillator") or {}, "ma_rows": du.get("movingAverages") or [],
            "osc_rows": du.get("oscillators") or [], "pivot": du.get("pivot") or {}, "gia": du.get("price"),
            **meta(tk, "technical")}


def peers(tk: str) -> dict:
    _, du = vc(tk, "peers")
    rows = sorted((x for x in du or [] if isinstance(x, dict)), key=lambda x: -(x.get("stockReturn") or -9))
    return {"ok": bool(rows), "rows": rows, **meta(tk, "peers")}


def holders(tk: str) -> dict:
    rows = sorted(_rows(tk, "shareholder"), key=lambda r: -(r.get("quantity") or 0))
    _, rel = vc(tk, "relationship")
    rel = rel if isinstance(rel, dict) else {}
    st = vc(tk, "shareholder-structure")[1] or {}
    return {"ok": bool(rows), "rows": [{
        "ten": r.get("ownerName"), "chuc_vu": r.get("positionName"), "loai": r.get("ownerType"),
        "sl": r.get("quantity"), "pct": r.get("percentage"), "ngay": _d(r.get("publicDate") or r.get("updateDate"))}
        for r in rows], "co_cau": st,
        "con": [{"ten": x.get("rightOrganNameVi"), "ma": x.get("rightTicker") or None, "pct": x.get("ownedPercentage"),
                 "sl": x.get("ownedQuantity")} for x in rel.get("subsidiaries") or []],
        "lien_ket": [{"ten": x.get("rightOrganNameVi"), "ma": x.get("rightTicker") or None,
                      "pct": x.get("ownedPercentage"), "sl": x.get("ownedQuantity")} for x in rel.get("affiliates") or []],
        **meta(tk, "shareholder")}


def price_series(tk: str, max_pts: int = 700) -> dict:
    """Giá đóng cửa ĐÃ ĐIỀU CHỈNH toàn chuỗi (lấy thưa tới max_pts điểm, giữ điểm cuối) cho biểu đồ dài nhất."""
    rows = sorted((r for r in _rows(tk, "price-history") if r.get("closePriceAdjusted")),
                  key=lambda r: r["tradingDate"])
    if not rows:
        return {"ok": False}
    step = max(1, len(rows) // max_pts)
    pts = rows[::step]
    if pts[-1] is not rows[-1]:
        pts.append(rows[-1])
    return {"ok": True, "pts": [(_d(r["tradingDate"]), r["closePriceAdjusted"]) for r in pts], "n": len(rows),
            "tu": _d(rows[0]["tradingDate"]), "toi": _d(rows[-1]["tradingDate"])}


# ───────────────────────────── vũ trụ + độ phủ ─────────────────────────────

CODONG_48 = ("VIC VHM STB MSN MSR NVL GEX GEE VIX VJC VCI DGC GEL PC1 CTD VRE VPL FPT BID CTG TCB MBB VPB VCB ACB "
             "TPB SHB LPB SSB VIB MWG HPG GAS PLX BSR VNM SAB VTP VGI GVR BVH HDB VPI SSI HCM GMD HAH BCM").split()
_TK_KEYS = ("tk", "ticker", "t", "sym", "symbol", "ma", "tickers", "tks", "code")


def universe(v21: dict, vn30: list) -> list[str]:
    """VN30 hiện hành ∪ 48 mã codong ∪ mọi mã niêm yết được nêu trong hằng V21 (khoá tk/ticker/…)."""
    from chaebol_map_data_nen import db_query
    listed = {r[0] for r in db_query("SELECT symbol FROM ma")}
    found: set[str] = set()

    def walk(o):
        if isinstance(o, dict):
            for k, x in o.items():
                if k in _TK_KEYS:
                    for s in (x if isinstance(x, list) else [x]):
                        if isinstance(s, str) and s in listed:
                            found.add(s)
                walk(x)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(v21 or {})
    found |= set(vn30) | set(CODONG_48)
    return sorted(found)


COVER_EPS = (("price-history", "Giá ngày"), ("proprietary-history", "Tự doanh"), ("insider-transaction", "Nội bộ"),
             ("shareholder", "Cổ đông"), ("events-all", "Sự kiện (16 mã)"), ("news", "Tin tức"),
             ("news-detail", "Chi tiết tin + PDF"), ("fs-income", "BCTC"), ("statistics-financial", "Chỉ số"),
             ("analysis", "Báo cáo PT"), ("technical", "Kỹ thuật"), ("financial-data", "LN KD dự phóng"))


def coverage(tks: list[str]) -> list[dict]:
    """Độ phủ cache từng endpoint trên vũ trụ: số mã có tệp, lấy gần nhất, dữ liệu tới (max)."""
    out = []
    for ep, lbl in COVER_EPS:
        have, lay, toi = [], [], []
        for t in tks:
            m = meta(t, ep)
            if m.get("lay_luc"):
                have.append(t)
                lay.append(m["lay_luc"])
                if m.get("toi"):
                    toi.append(m["toi"])
        if ep == "financial-data":            # khối khoá đăng nhập: đếm theo state/vc_iq_dangnhap (phiên của người dùng)
            import chaebol_map_data_dangnhap as DN
            fd = {t: DN.financial_data(t) for t in tks}
            have = [t for t in tks if fd[t].get("ok")]
            lay = [fd[t]["lay"] for t in have if fd[t].get("lay")]
        out.append({"ep": ep, "ten": lbl, "co": len(have), "tong": len(tks), "thieu": [t for t in tks if t not in have],
                    "lay_moi": max(lay)[:16] if lay else None, "lay_cu": min(lay)[:16] if lay else None,
                    "toi": max(toi) if toi else None})
    return out
