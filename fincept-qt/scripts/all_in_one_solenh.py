#!/usr/bin/env python3
"""all_in_one_solenh.py, sổ lệnh "lái gom / lái xả" cho ALL-IN-ONE (phương pháp Thầy Hải + pipeline V5).

Phương pháp (hai tệp người dùng gửi 10/10/2026: thay_hai_ly_thuyet_toan_tap.html, v5_detailed_backtest_pipeline.html):
  Hệ số 2 (HS2) = KL trung bình mỗi lệnh BÁN ÷ KL trung bình mỗi lệnh MUA của phiên
                = averageSellTradeVolume ÷ averageBuyTradeVolume (Vietcap price-history, FACT-T2).
  HS2 < 0,8 → phiên "lái gom ngầm"; HS2 > 1,5 → phiên "lái xả"; HS2 > 1,5 liên tục 4–5 phiên = phân phối ngầm.
  Mẫu nến (luật đo được, giá điều chỉnh; khớp 20/20 ngày phát hiện của V5 trong 04/09–09/10/2026):
    N5 rút chân   (min(o,c)−l)/(h−l) > 0,60 và l ≤ đóng phiên trước × 0,98
    N3 đỏ đặc     c<o, thân ≥ 0,65 biên, đóng ≤ 10% biên tính từ đáy, giảm ≥ 1,5%
    N6 đột tử     mở gap lên, đóng ≤ 15% biên tính từ đáy, c<o, KL ≥ 1,4 × TB20
    CB cánh bướm  đỉnh ≥ 0,98 × đỉnh 20 phiên trước nhưng KL < 0,75 × TB20 (chạm đỉnh cũ, rỗng ruột)
    BV bình vôi   KL ≥ 5 × TB20
Giới hạn đã kiểm (khảo sát 10/10): số gom/xả, HS2 trung bình và "Cầu A1" của V5 KHÔNG tái lập được từ dữ liệu
ngày Vietcap; HS2 Vietcap có trung vị ≈1,45 trên VN200 nên ngưỡng tuyệt đối 0,8/1,5 xếp đa số phiên vào "xả" →
bảng kèm phân vị HS2 cắt ngang VN200. Hệ số 4 (thực khớp bán ÷ mua) luôn = 1 trên dữ liệu ngày; Cầu A1 không có
định nghĩa đo được → [CẦN DATA]. Phân loại chỉ mô tả dữ liệu (EST), không phải lệnh mua/bán (CỔNG v1.7 DỪNG).

Cache: fincept_bridge/state/all_in_one/solenh.json, theo từng mã (lần đầu ~6 s cho 229 mã, sau đó chỉ tính mã có
price-history mới).
"""
from __future__ import annotations

import json
import os
import statistics
from datetime import datetime, timezone

import all_in_one as A
from all_in_one import (CAN, EST, T2, UNV, bang, bieu_do, canh_bao, cell, ddmm, doan, nfc, num, o, o_so, read_json,
                        tile, vn)

VC = A.BRIDGE / "state" / "vc_lk"
CACHE = A.BRIDGE / "state" / "all_in_one" / "solenh.json"
V5_REF = A.BRIDGE / "data" / "all_in_one" / "v5_2026-10-09.json"
WIN = 25          # "cả tháng" của V5 ≈ 25 phiên
MIN_N = 15        # số phiên có sổ lệnh tối thiểu để xếp hạng
KEEP = 60         # phiên giữ trong cache cho biểu đồ
GOM, XA = 0.8, 1.5
CHUOI_XA = 4      # HS2 > 1,5 liên tục ≥ 4 phiên = phân phối ngầm (luật Thầy Hải)
TOP = 10
LO_TOI_THIEU = 100    # KL TB mỗi lệnh dưới 1 lô (100 cp) = lệnh lẻ / phiên không khớp: HS2 suy biến, bỏ phiên
GAP_TOI_THIEU = 0.1   # % mở cửa trên tham chiếu (giá thô) để tính là "mở gap lên" của Nến 6
CAN_BANG = 0.10       # |gom − xả| ÷ số phiên dưới 10% → "CÂN" (không gắn nghiêng)
PHU_TOI_THIEU = 0.9   # phiên vào cửa sổ chung khi ≥ 90% mã có sổ lệnh
MAU_NEN = {"N3": "Nến 3 (đỏ đặc ép cắt lỗ)", "N5": "Nến 5 (rút chân)", "N6": "Nến 6 (đột tử)",
           "CB": "Cánh bướm lệch (chạm đỉnh, KL thấp)", "BV": "Lệnh bình vôi (KL ≥ 5× TB20)"}
SCHEMA = "aio_solenh/3"
EYEBROW, TAB, TAB_NHAN = "Sổ lệnh · Toàn Vũ / V5 · Thầy Hải", "langkinh", "Lăng kính FFT"


def _ms(d):
    try:
        y, m, dd = (int(p) for p in str(d)[:10].split("-"))
        return int(datetime(y, m, dd, tzinfo=timezone.utc).timestamp() * 1000)
    except (ValueError, TypeError):
        return None


# ───────────────────────────── tính một mã ─────────────────────────────

def _rows(tk):
    du = (read_json(VC / tk / "price-history.json") or {}).get("du_lieu") or {}
    if not isinstance(du, dict) or not du.get("hang"):
        return []
    rows = [dict(zip(du["cot"], r)) for r in du["hang"]]
    rows = [r for r in rows if r.get("tradingDate") and num(r.get("closePriceAdjusted"))]
    rows.sort(key=lambda r: r["tradingDate"])
    return rows


def _adj(r):
    """(mở, cao, thấp, đóng) điều chỉnh quyền; giá mở suy theo tỷ lệ đóng điều chỉnh ÷ đóng thô, kẹp vào [thấp, cao]."""
    c_raw, c = num(r.get("closePrice")), num(r.get("closePriceAdjusted"))
    f = c / c_raw if c_raw else 1.0
    op = (num(r.get("openPrice")) or c_raw or c) * f
    h = num(r.get("highestPriceAdjusted")) or max(op, c)
    lo = num(r.get("lowestPriceAdjusted")) or min(op, c)
    return min(max(op, lo), h), h, lo, c


def _gap(r, op, pc):
    """% mở cửa so tham chiếu, trên giá thô (không nhiễu hệ số điều chỉnh); thiếu tham chiếu thì dùng giá điều chỉnh."""
    o_raw, ref = num(r.get("openPrice")), num(r.get("referencePrice"))
    return (o_raw / ref - 1) * 100 if o_raw and ref else (op / pc - 1) * 100


def _mau(rows, i):
    """Mẫu nến của phiên i (cần 20 phiên trước để có TB20 và đỉnh 20 phiên)."""
    if i < 20:
        return []
    op, h, lo, c = _adj(rows[i])
    pc = num(rows[i - 1].get("closePriceAdjusted"))
    prev = [num(r.get("totalMatchVolume")) or 0 for r in rows[i - 20:i]]
    ma20 = sum(prev) / len(prev)
    vr = (num(rows[i].get("totalMatchVolume")) or 0) / ma20 if ma20 else 0
    out = ["BV"] if ma20 and vr >= 5 else []
    rng = h - lo
    if rng <= 0 or not pc:
        return out
    hi20 = max(num(r.get("highestPriceAdjusted")) or 0 for r in rows[i - 20:i])
    pos, body, low = (c - lo) / rng, abs(c - op) / rng, (min(op, c) - lo) / rng
    chg, gap = (c / pc - 1) * 100, _gap(rows[i], op, pc)
    if low > 0.60 and lo <= pc * 0.98:
        out.append("N5")
    if c < op and body >= 0.65 and pos <= 0.10 and chg <= -1.5:
        out.append("N3")
    if gap > GAP_TOI_THIEU and pos <= 0.15 and c < op and vr >= 1.4:
        out.append("N6")
    if hi20 and h >= hi20 * 0.98 and vr < 0.75:
        out.append("CB")
    return out


def tinh_ma(tk, rows=None):
    """{tk, phien:[{d, c (nghìn đồng, điều chỉnh), hs2 | None, mau[]}] (≤ KEEP phiên cuối), cap_nhat} | None."""
    rows = rows if rows is not None else _rows(tk)
    if not rows:
        return None
    out = []
    for i in range(max(0, len(rows) - KEEP), len(rows)):
        r = rows[i]
        b, s = num(r.get("averageBuyTradeVolume")), num(r.get("averageSellTradeVolume"))
        khop = num(r.get("totalMatchVolume")) or 0
        ok = khop > 0 and b and s and min(b, s) >= LO_TOI_THIEU
        out.append({"d": r["tradingDate"][:10], "c": round(num(r.get("closePriceAdjusted")) / 1000, 3),
                    "hs2": round(s / b, 3) if ok else None, "mau": _mau(rows, i)})
    return {"tk": tk, "phien": out, "cap_nhat": rows[-1]["tradingDate"][:10]}


def thong_ke(x, ngay=None):
    """Thống kê trên các phiên thuộc `ngay` (danh sách ngày tham chiếu), mặc định WIN phiên cuối của chính mã:
    n, gom, xa, hs2_tb, chuoi_xa, mau {loại: [ngày]}, o {ngày: G|X|·|?}, tu, den."""
    ph = (x or {}).get("phien") or []
    if ngay:
        tap = set(ngay)
        ph = [p for p in ph if p["d"] in tap]
    else:
        ph = ph[-WIN:]
    co = [p for p in ph if p["hs2"] is not None]
    hs = [p["hs2"] for p in co]
    run = best = 0
    for p in ph:
        run = run + 1 if (p["hs2"] or 0) > XA else 0
        best = max(best, run)
    mau = {}
    for p in ph:
        for m in p["mau"]:
            mau.setdefault(m, []).append(p["d"])
    return {"n": len(hs), "gom": sum(1 for v in hs if v < GOM), "xa": sum(1 for v in hs if v > XA),
            "hs2_tb": statistics.fmean(hs) if hs else None, "chuoi_xa": best, "mau": mau,
            "o": {p["d"]: (("G" if p["hs2"] < GOM else "X" if p["hs2"] > XA else "·") if p["hs2"] is not None else "?")
                  for p in ph},
            "tu": co[0]["d"] if co else None, "den": co[-1]["d"] if co else None}


# ───────────────────────────── cache ─────────────────────────────

def _mtime(t):
    try:
        return os.stat(VC / t / "price-history.json").st_mtime
    except OSError:
        return 0.0


def load_cache(tks):
    """{tk: tinh_ma(tk)} cho các mã (mã không có price-history vắng mặt). Cache theo từng mã: chỉ tính lại mã có
    price-history mới hơn lần tính trước (fetcher vc_lk đang chạy cũng không làm dựng lại cả vũ trụ)."""
    c = read_json(CACHE)
    c = c if isinstance(c, dict) and c.get("schema") == SCHEMA else {}
    ma, mt = dict(c.get("ma") or {}), dict(c.get("mt") or {})
    doi = False
    for t in sorted(set(tks)):
        m = _mtime(t)
        if t in mt and m and mt[t] >= m:
            continue
        if not m and t not in ma and mt.get(t) == 0:
            continue  # vẫn chưa có tệp: không ghi lại cache mỗi lượt
        x = tinh_ma(t)
        if x:
            ma[t] = x
        else:
            ma.pop(t, None)
        mt[t], doi = m, True
    if doi:
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            tmp = CACHE.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps({"schema": SCHEMA, "mt": mt, "ma": ma,
                                       "tao_luc": datetime.now().isoformat(timespec="seconds")},
                                      ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp, CACHE)
        except OSError:
            pass  # cache chỉ để nhanh; không ghi được thì lần sau tính lại
    return {t: ma[t] for t in set(tks) if t in ma}


def ngay_tham_chieu(cache, tks=None):
    """Cửa sổ ngày chung → {"ngay": [...], "du_phu": bool, "cho": [...]}.
    Lấy các phiên của mã cập nhật muộn nhất; bỏ các phiên MỚI NHẤT có sổ lệnh cho < PHU_TOI_THIEU số mã của `tks`
    (fetcher vc_lk đang chạy dở: "cho" = đang cập nhật), rồi lùi về trước chừng nào mỗi phiên còn đủ độ phủ, tối đa
    WIN phiên. Vietcap chỉ trả averageBuy/SellTradeVolume cho 118 mã từ 21/09/2026 nên đoạn chung hiện ngắn hơn 25 phiên;
    fetch lại vc_lk thì tự nới. Đoạn chung < MIN_N phiên → WIN phiên cuối, du_phu = False (ô không được ghi ≥ 90%)."""
    best = max(cache.values(), key=lambda x: (x["cap_nhat"], len(x["phien"])), default=None)
    ngay = [p["d"] for p in (best or {}).get("phien", [])]
    pool = [cache[t] for t in (tks if tks is not None else cache) if t in cache]
    cov = dict.fromkeys(ngay, 0)
    for x in pool:
        for p in x["phien"]:
            if p["d"] in cov and p["hs2"] is not None:
                cov[p["d"]] += 1
    du = [cov[d] >= PHU_TOI_THIEU * len(pool) for d in ngay]
    j = len(ngay)
    while j > 0 and not du[j - 1]:
        j -= 1
    k = j
    while k > 0 and du[k - 1] and j - k < WIN:
        k -= 1
    if j - k >= MIN_N:
        return {"ngay": ngay[k:j], "du_phu": True, "cho": ngay[j:]}
    return {"ngay": ngay[-WIN:], "du_phu": False, "cho": []}


def phan_vi(v, vals):
    vals = [x for x in vals if x is not None]
    if v is None or not vals:
        return None
    return 100.0 * sum(1 for x in vals if x <= v) / len(vals)


_TV30 = None


def tv30():
    """30 mã Toàn Vũ (lk_hoso/_index.json "toan_vu", dự phòng fft_codong.json), như chaebol_map_data_langkinh.tv30."""
    global _TV30
    if _TV30 is None:
        ix = read_json(A.BRIDGE / "data" / "lk_hoso" / "_index.json") or {}
        _TV30 = set(ix.get("toan_vu") or ((read_json(A.BRIDGE / "data" / "fft_codong.json") or {}).get("ma") or {}).keys())
    return _TV30


def hoi(tk):
    """Hậu tố '?' cho nhãn mẫu hình của mã ngoài 30 mã Toàn Vũ (CLAUDE.md §6 luật 4)."""
    return "" if tk in tv30() else "?"


# ───────────────────────────── biểu đồ ─────────────────────────────

def chart_ma(tk, x, cao=260, tieu_de=None, ngay=None):
    """Giá đóng cửa điều chỉnh 60 phiên + ▲ phiên HS2 < 0,8, ▼ phiên HS2 > 1,5, ◆ mẫu nến; HS2 trục phải; dải mờ =
    cửa sổ được đếm (ngay)."""
    ph = (x or {}).get("phien") or []
    if len(ph) < 5:
        return None
    q = hoi(tk)
    ann = []
    if ngay:
        ann.append({"kind": "xband", "x0": _ms(ngay[0]), "x1": _ms(ngay[-1]), "mau": "info", "alpha": 0.06,
                    "text": f"cửa sổ đếm {len(ngay)} phiên", "uu_tien": 3})
    for p in ph:
        ms, hs = _ms(p["d"]), p["hs2"]
        if hs is not None and hs < GOM:
            ann.append({"kind": "point", "x": ms, "y": p["c"], "marker": "tri_up", "pos": "below", "mau": "bull",
                        "uu_tien": 2, "tip": f"{ddmm(p['d'])} · lái gom ngầm{q} | HS2 {vn(hs, 3)} < 0,8 (luật Thầy Hải)"
                                             f" | đóng {vn(p['c'], 2)}"})
        elif hs is not None and hs > XA:
            ann.append({"kind": "point", "x": ms, "y": p["c"], "marker": "tri_down", "pos": "above", "mau": "bear",
                        "uu_tien": 2, "tip": f"{ddmm(p['d'])} · lái xả{q} | HS2 {vn(hs, 3)} > 1,5 (luật Thầy Hải)"
                                             f" | đóng {vn(p['c'], 2)}"})
        for m in p["mau"]:
            ann.append({"kind": "point", "x": ms, "y": p["c"], "marker": "diamond", "mau": "warn", "uu_tien": 3,
                        "text": m + q, "tip": f"{ddmm(p['d'])} · {MAU_NEN.get(m, m)}{q}"})
    for y, t in ((GOM, "0,8 gom"), (XA, "1,5 xả")):
        ann.append({"kind": "hband", "y0": y - 0.01, "y1": y + 0.01, "axis": "right", "mau": "dim", "alpha": 0.6,
                    "text": t, "uu_tien": 2})
    block = {"x": [p["d"] for p in ph], "left": {"label": "giá đc (nghìn đồng)"}, "right": {"label": "HS2", "min": 0},
             "series": [{"name": "HS2 = TB lệnh bán ÷ TB lệnh mua", "y": [p["hs2"] for p in ph], "style": "bar",
                         "mau": "grey", "alpha": 0.35, "axis": "right"},
                        {"name": "Giá đóng cửa (điều chỉnh)", "y": [p["c"] for p in ph], "style": "line", "mau": "amber"}],
             "annotations": ann}
    return bieu_do(tieu_de or f"{tk} · {len(ph)} phiên · ▲ gom ▼ xả ◆ mẫu nến", block,
                   "▲ phiên HS2 < 0,8 · ▼ phiên HS2 > 1,5 (ngưỡng luật Thầy Hải) · ◆ mẫu nến theo luật đo được; cột xám = "
                   "HS2 (trục phải, vạch 0,8 và 1,5); dải mờ = các phiên được đếm. Rê chuột lên ký hiệu để xem ngày và số."
                   + (" Mã ngoài 30 mã Toàn Vũ: nhãn mang hậu tố '?'." if q else ""),
                   "Vietcap price-history (averageSell/BuyTradeVolume, giá điều chỉnh)", f"{T2} {EST}", cao)


# ───────────────────────────── ô cho trang mã ─────────────────────────────

def o_solenh(tk, U):
    x = tinh_ma(tk)
    if not x:
        return o("solenh", "Sổ lệnh · lái gom / lái xả", [], 12, EYEBROW, TAB, TAB_NHAN,
                 ghi_chu=f"{CAN} chưa có vc_lk/{tk}/price-history.json")
    cache = load_cache(set(U["VN200"]) | {tk})
    w = ngay_tham_chieu(cache, U["VN200"])
    chung = w["ngay"]
    st = thong_ke(x, chung)
    vals = [v["hs2_tb"] for v in (thong_ke(cache[t], chung) for t in U["VN200"] if t in cache) if v["n"] >= MIN_N]
    pct = phan_vi(st["hs2_tb"], vals) if st["n"] >= MIN_N else None
    med = statistics.median(vals) if vals else None
    q = hoi(tk)
    mau_txt = "; ".join(f"{MAU_NEN[m].split(' (')[0]}{q} {', '.join(ddmm(d, False) for d in ds[-3:])}"
                        for m, ds in sorted(st["mau"].items())) or "không có"
    tiles = [
        tile(f"Phiên gom / xả · {st['n']}/{len(chung)} phiên có sổ lệnh", f"{st['gom']} / {st['xa']}",
             f"cửa sổ chung {ddmm(chung[0], False)}→{ddmm(chung[-1], False)} như bảng rổ · gom HS2 < 0,8 · xả HS2 > 1,5"
             if chung else "", None, EST),
        tile("HS2 trung bình", vn(st["hs2_tb"], 2),
             f"phân vị {vn(pct, 0)} trên VN200 cùng cửa sổ (thấp = nghiêng gom) · trung vị VN200 {vn(med, 2)}"
             if pct is not None else "chưa đủ phiên để xếp",
             "xanh" if pct is not None and pct <= 20 else ("do" if pct is not None and pct >= 80 else None), EST),
        tile("Chuỗi HS2 > 1,5 dài nhất", f"{st['chuoi_xa']} phiên",
             "ngưỡng luật Thầy Hải: 4 phiên liên tục" + (" · đã chạm ngưỡng" if st["chuoi_xa"] >= CHUOI_XA else ""),
             "do" if st["chuoi_xa"] >= CHUOI_XA else None, EST),
        tile("Mẫu nến trong cửa sổ", str(sum(len(v) for v in st["mau"].values())), mau_txt, None, EST),
    ]
    canh = [f"HS2 Vietcap có trung vị {vn(med, 2)} trên VN200 trong cửa sổ này: ngưỡng tuyệt đối 0,8 / 1,5 xếp nhiều "
            "phiên vào 'xả', nên đọc kèm phân vị." if med is not None else ""]
    if st["n"] < MIN_N:
        canh.append(f"Chỉ {st['n']}/{len(chung)} phiên của cửa sổ có sổ lệnh cho mã này; không xếp hạng.")
    if not w["du_phu"]:
        canh.append(f"Chưa có đoạn ≥ {MIN_N} phiên mà ≥ 90% VN200 có sổ lệnh: dùng {len(chung)} phiên cuối.")
    if w["cho"]:
        canh.append(f"Phiên {', '.join(ddmm(d, False) for d in w['cho'])} đang cập nhật (dưới 90% mã có sổ lệnh), chưa tính.")
    if q:
        canh.append("Mã ngoài 30 mã Toàn Vũ: nhãn mẫu hình mang hậu tố '?' (CLAUDE.md §6 luật 4).")
    return o("solenh", "Sổ lệnh · lái gom / lái xả (HS2 + mẫu nến)", [
        o_so(tiles, 4), chart_ma(tk, x, 280, ngay=chung), canh_bao("Lưu ý", canh),
        doan("Phân loại mô tả dữ liệu sổ lệnh ngày (EST), không phải lệnh mua/bán; CỔNG v1.7 đang DỪNG. "
             "Hệ số 4 và Cầu A1 cần dữ liệu trong phiên: [CẦN DATA].", "xam")],
        12, EYEBROW, TAB, TAB_NHAN, f"{T2} {EST}", A.trang_thai(st["den"] or x["cap_nhat"], 4))


# ───────────────────────────── ô cho bảng rổ ─────────────────────────────

def xep_hang(mas, cache, ngay):
    """([(tk, st)] đủ phiên, sắp theo (gom − xả) ÷ số phiên có sổ lệnh giảm dần rồi HS2 TB tăng dần, [tk thiếu phiên])."""
    ok, thieu = [], []
    for t in mas:
        st = thong_ke(cache[t], ngay) if t in cache else None
        if not st or st["n"] < MIN_N:
            thieu.append(t)
        else:
            ok.append((t, st))
    ok.sort(key=lambda p: (-(p[1]["gom"] - p[1]["xa"]) / p[1]["n"], p[1]["hs2_tb"]))
    return ok, thieu


def nghieng(tk, st):
    """(nhãn, màu): GOM / XẢ khi |gom − xả| ÷ số phiên ≥ CAN_BANG, ngược lại CÂN; mã ngoài 30 mã TV thêm '?'."""
    d = (st["gom"] - st["xa"]) / st["n"] if st["n"] else 0
    if abs(d) < CAN_BANG:
        return "CÂN", "xam"
    return ("GOM" + hoi(tk), "xanh") if d > 0 else ("XẢ" + hoi(tk), "do")


def _hang_row(t, st, pct, ngay):
    nh, mau = nghieng(t, st)
    mau_dau = ", ".join(f"{m}{hoi(t)} {ddmm(ds[0], False)}" for m, ds in sorted(st["mau"].items()))
    row = [cell(t, "vang", dam=True), cell(nh, mau, pill=True), cell(str(st["n"])),
           cell(str(st["gom"]), "xanh" if st["gom"] else None), cell(str(st["xa"]), "do" if st["xa"] else None),
           cell(str(st["chuoi_xa"]), "do" if st["chuoi_xa"] >= CHUOI_XA else None),
           cell(vn(st["hs2_tb"], 2)), cell(vn(pct, 0))]
    for d in ngay:
        c = st["o"].get(d, "")
        row.append(cell(c, {"G": "xanh", "X": "do", "?": "xam"}.get(c)))  # không tip: dấu [i] làm bảng 25 cột rối
    row.append(cell(mau_dau, mono=False))
    return row


def _ds(xx):
    return ", ".join(xx[:12]) + ("…" if len(xx) > 12 else "")


def tiles_bang(ro, U, ten):
    """Các ô xếp hạng gom/xả cho trang rổ VN30 / VN100 / VN200, đặt ĐẦU trang (trước tóm tắt rổ)."""
    if ro not in ("VN30", "VN100", "VN200"):
        return []
    cache = load_cache(set(U["VN200"]) | set(U[ro]))
    w = ngay_tham_chieu(cache, U["VN200"])
    ngay = w["ngay"]
    ok, thieu = xep_hang(U[ro], cache, ngay)
    tieu_de = f"Bảng xếp hạng gom / xả theo sổ lệnh · {ro} (Toàn Vũ · V5 · phương pháp Thầy Hải)"
    if not ok or not ngay:
        return [o("sl_xep_hang", tieu_de, [], 12, EYEBROW, TAB, TAB_NHAN,
                  ghi_chu=f"{CAN} chưa đủ {MIN_N} phiên sổ lệnh cho mã nào của {ro}")]
    vals = [st["hs2_tb"] for _, st in xep_hang(U["VN200"], cache, ngay)[0]]
    ca_ro = ro == "VN30" or len(ok) <= 2 * TOP
    if ca_ro:
        top_gom, top_xa, xep = ok[:3], list(reversed(ok[-3:])), ok
    else:
        top_gom, top_xa = ok[:TOP], list(reversed(ok[-TOP:]))
        xep = top_gom + ok[-TOP:]   # bảng và cột theo thứ hạng: dòng cuối = nghiêng xả nhất
    rows = [_hang_row(t, st, phan_vi(st["hs2_tb"], vals), ngay) for t, st in xep]
    cot = (["Mã", "Nghiêng", "Phiên SL", "Gom", "Xả", "Chuỗi xả", "HS2 TB", "Pct VN200"] + [ddmm(d, False) for d in ngay]
           + ["Mẫu nến (lần đầu)"])
    hs_ro = [st["hs2_tb"] for _, st in ok]
    xa_dai = [t for t, st in ok if st["chuoi_xa"] >= CHUOI_XA]
    co_n6 = [t for t, st in ok if "N6" in st["mau"]]
    co_bv = [t for t, st in ok if "BV" in st["mau"]]
    phu_cs = (f"mỗi phiên có sổ lệnh cho ≥ 90% VN200 · {len(ok)}/{len(U[ro])} mã đủ ≥ {MIN_N} phiên"
              + ("" if len(ngay) >= WIN else f" · đủ {WIN} phiên khi vc_lk có sổ lệnh từ đầu tháng")) if w["du_phu"] else (
        f"chưa có đoạn ≥ {MIN_N} phiên đủ độ phủ 90%: dùng {len(ngay)} phiên cuối, số phiên có sổ lệnh mỗi mã khác nhau")
    if w["cho"]:
        phu_cs += f" · phiên {', '.join(ddmm(d, False) for d in w['cho'])} đang cập nhật, chưa tính"
    tiles = [
        tile(f"Cửa sổ chung {len(ngay)} phiên", f"{ddmm(ngay[0], False)}→{ddmm(ngay[-1], False)}", phu_cs, None, T2),
        tile("HS2 trung vị của rổ", vn(statistics.median(hs_ro), 2),
             f"trung vị VN200 {vn(statistics.median(vals), 2)}: ngưỡng 0,8 / 1,5 xếp nhiều phiên vào 'xả'" if vals else "",
             None, EST),
        tile(f"Chuỗi HS2 > 1,5 ≥ {CHUOI_XA} phiên", f"{len(xa_dai)} mã", _ds(xa_dai), "do" if xa_dai else None, EST),
        tile("Nến 6 (đột tử) trong cửa sổ", f"{len(co_n6)} mã", _ds(co_n6), None, EST),
        tile("Lệnh bình vôi (KL ≥ 5× TB20)", f"{len(co_bv)} mã", _ds(co_bv), None, EST),
    ]
    diem = [round((st["gom"] - st["xa"]) / st["n"] * 100) for _, st in xep]
    cot_chart = bieu_do(
        "Gom − xả (% số phiên có sổ lệnh) · " + ("cả rổ" if ca_ro else f"Top {TOP} nghiêng gom và Top {TOP} nghiêng xả"),
        {"loai": "cot", "huong": "doc", "nhan": [t for t, _ in xep],
         "series": [{"name": "% phiên gom − % phiên xả", "y": diem, "mau": "lam",
                     "mau_tung": ["xanh" if d >= CAN_BANG * 100 else ("do" if d <= -CAN_BANG * 100 else "xam")
                                  for d in diem]}],
         "gia_tri": True, "so_le": 0, "dau": True, "dv": "%"},
        "Mỗi cột = (số phiên HS2 < 0,8 − số phiên HS2 > 1,5) ÷ số phiên có sổ lệnh trong cửa sổ; xám = chênh dưới 10%.",
        "Vietcap price-history", f"{T2} {EST}", 240)
    grid = [o("sl_xep_hang", tieu_de, [
        o_so(tiles, 5), cot_chart,
        bang(cot, rows, "G = phiên HS2 < 0,8 · X = phiên HS2 > 1,5 · · = trung tính · ? = không có sổ lệnh hợp lệ phiên đó "
                        "(Vietcap chưa trả, không khớp lệnh, hoặc KL TB mỗi lệnh dưới 1 lô) · trống = mã không giao dịch. "
                        "Nghiêng = GOM / XẢ khi chênh ≥ 10% số phiên, còn lại CÂN; mã ngoài 30 mã Toàn Vũ mang hậu tố '?'. "
                        "Xếp theo (gom − xả) ÷ phiên có sổ lệnh rồi HS2 TB. Pct VN200: phân vị HS2 TB cắt ngang VN200 cùng "
                        "cửa sổ (thấp = nghiêng gom). Mẫu nến: N3 đỏ đặc · N5 rút chân · N6 đột tử · CB cánh bướm lệch · "
                        "BV bình vôi, kèm ngày lần đầu trong cửa sổ.", can_phai=[2, 3, 4, 5, 6, 7]),
        canh_bao("Phương pháp và giới hạn", [
            "HS2 = KL TB lệnh bán ÷ KL TB lệnh mua mỗi phiên (Vietcap averageSell/BuyTradeVolume); ngưỡng 0,8 / 1,5 "
            "và luật 4–5 phiên liên tục theo tài liệu Thầy Hải.",
            "Số gom/xả, HS2 TB và Cầu A1 của báo cáo V5 KHÔNG tái lập được từ dữ liệu ngày Vietcap (đối chiếu ở ô cuối); "
            "Hệ số 4 và Cầu A1: [CẦN DATA] (cần dữ liệu trong phiên).",
            f"Mã thiếu phiên sổ lệnh (không xếp): {_ds(thieu)}" if thieu else "",
            "Nghiêng GOM/XẢ là mô tả dữ liệu (EST), không phải lệnh mua/bán; CỔNG v1.7 đang DỪNG."], "vang")],
        12, EYEBROW, TAB, TAB_NHAN, f"{T2} {EST}", A.trang_thai(ngay[-1], 4))]
    for nh, lst in (("gom", top_gom[:3]), ("xả", top_xa[:3])):
        for t, st in lst:
            grid.append(o(f"sl_{t}", f"{t} · nghiêng {nh}{hoi(t)} · {st['gom']} gom / {st['xa']} xả trên {st['n']} phiên",
                          [chart_ma(t, cache.get(t), 240, f"{t} · {nfc(ten.get(t, ''))[:40]}", ngay)], 4,
                          f"Top 3 nghiêng {nh}", TAB, TAB_NHAN, f"{T2} {EST}", A.trang_thai(st["den"], 4)))
    v5 = o_v5(U[ro], cache)
    if v5:
        grid.append(v5)
    return grid


def o_v5(mas, cache):
    ref = read_json(V5_REF) or {}
    w0, w1 = ((ref.get("cua_so") or []) + [None, None])[:2]
    rows = []
    for r in ref.get("ma") or []:
        t = r.get("tk")
        if t not in mas:
            continue
        ph = [p for p in (cache.get(t) or {}).get("phien", []) if w0 and w1 and w0 <= p["d"] <= w1]
        hs = [p["hs2"] for p in ph if p["hs2"] is not None]
        g, x = sum(1 for v in hs if v < GOM), sum(1 for v in hs if v > XA)
        rows.append([cell(t, "vang", dam=True), cell(nfc(r.get("grp")), mono=False),
                     cell(f"{r.get('gom')} / {r.get('xa')}"), cell(vn(r.get("hs2"), 2)), cell(vn(r.get("a1"), 1, suffix="%")),
                     cell(f"{g} / {x}" if hs else "", "xam" if hs and len(hs) < 20 else None,
                          tip=f"{len(hs)} phiên có sổ lệnh trong cửa sổ V5" if hs else None),
                     cell(vn(statistics.fmean(hs), 2) if hs else ""), cell(CAN, "xam"),
                     cell(nfc(r.get("pats")), mono=False), cell(ddmm(r.get("date")))])
    if not rows:
        return None
    return o("sl_v5", f"Đối chiếu báo cáo V5 ({ddmm(w0, False)}–{ddmm(w1, False)}) với dữ liệu Vietcap", [bang(
        ["Mã", "Nhóm V5", "V5 gom/xả", "V5 HS2", "V5 Cầu A1", "Vietcap gom/xả", "Vietcap HS2", "Cầu A1", "V5 mẫu hình",
         "V5 ngày"], rows,
        "Cột V5 chép nguyên văn báo cáo (UNVERIFIED). Cột Vietcap tính lại cùng cửa sổ từ price-history; chữ xám = mã "
        "Vietcap thiếu sổ lệnh phần đầu cửa sổ. Mẫu nến của V5 tái lập được 20/20 ngày bằng luật đo được; số phiên "
        "gom/xả và HS2 thì không, nên V5 có thể dùng nguồn sổ lệnh khác (trong phiên).", can_phai=[3, 4, 6]),
        doan("Nhãn hành động trong V5 không được chép vào đây.", "xam")],
        12, "Đối chiếu", TAB, TAB_NHAN, UNV, "cu")
