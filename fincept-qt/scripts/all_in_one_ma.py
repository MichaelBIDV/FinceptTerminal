#!/usr/bin/env python3
"""all_in_one_ma.py, các ô của một mã cho tab ALL-IN-ONE (gọi từ all_in_one.py ma --ma MÃ).

Mỗi hàm o_*() đọc đúng tệp state của MỘT tab gốc (chỉ đọc), định dạng số kiểu Việt, gắn bậc bằng chứng và
trả một ô aio/1 (xem all_in_one.o). Thiếu nguồn → ô trạng thái "thieu" kèm ghi chú [CẦN DATA], không bịa số.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

import all_in_one as A
from all_in_one import (CAN, EST, T1, T2, T3, UNV, bang, bieu_do, canh_bao, cell, chips, ddmm, doan, mau_sign, nfc,
                        num, o, o_so, read_json, tile, trang_thai, tuoi_ngay, vn, zone_mau)

VC = A.BRIDGE / "state" / "vc_lk"
VC_DN = A.BRIDGE / "state" / "vc_iq_dangnhap"


def v(x):
    """Giá trị của ô bằng chứng {v,u,t,b,n} hoặc số trần."""
    return num(x)


def vt(x):
    return (x or {}).get("t") if isinstance(x, dict) else None


def vc(tk, ep, dang_nhap=False):
    d = read_json((VC_DN if dang_nhap else VC) / tk / f"{ep}.json")
    return (d.get("meta") or {}, d.get("du_lieu")) if isinstance(d, dict) else ({}, None)


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def iso_ms(d):
    try:
        y, m, dd = (int(p) for p in str(d)[:10].split("-"))
        return int(datetime(y, m, dd, tzinfo=timezone.utc).timestamp() * 1000)
    except (ValueError, TypeError):
        return None


def hband(y, text, mau, w):
    if y is None:
        return None
    return {"kind": "hband", "y0": y - w, "y1": y + w, "mau": mau, "alpha": 0.55, "text": text, "uu_tien": 2}


def cut(s, n):
    s = nfc(s)
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def ty(x):
    """Tỷ đồng."""
    return vn(x, 0)


# ───────────────────────────── 1 · hồ sơ ─────────────────────────────

def sc(x, k):
    """num(x) × k, hoặc None khi thiếu (không biến thiếu thành 0)."""
    n = num(x)
    return None if n is None else n * k


def jp(*parts, sep=" · "):
    """Nối các phần có nội dung; tất cả trống → '' (để tile() hiện [CẦN DATA])."""
    return sep.join(x for x in parts if x)


def anh_chup(meta):
    return f"ảnh chụp {ddmm(meta.get('lay_luc'), False)}" if meta.get("lay_luc") else "ảnh chụp, không rõ ngày"


def o_ho_so(tk, ten, nganh, san, ro_list, nhom_chb, q, h):
    dmeta, det = vc(tk, "details")
    det = det if isinstance(det, dict) else {}
    gia = q.get("gia")
    live = (q.get("nguon") or "").startswith("vci")
    cp = h.get("co_phan") or {}
    shares = v(cp.get("hien_tai"))
    if shares is None and num(det.get("marketCap")) and num(det.get("currentPrice")):
        shares = num(det.get("marketCap")) / num(det.get("currentPrice"))
    if shares is None:
        shares = num(det.get("issueShare"))
    g = h.get("gia") or {}
    hi52, lo52 = v((g.get("dinh_52w") or {}).get("v")), v((g.get("day_52w") or {}).get("v"))
    if hi52 is not None and lo52 is not None:
        t52 = tile("Cao / thấp 52T (đóng cửa đc)", f"{vn(hi52, 1)} / {vn(lo52, 1)}",
                   f"tới {ddmm(h.get('phien_cuoi'), False)} · từ đỉnh 52T {vn(g.get('tu_dinh_52w'), 1, True, '%')} · "
                   f"từ đỉnh lịch sử {vn(g.get('tu_dinh_ls'), 1, True, '%')}", None, T2)
    else:
        hd, ld = sc(det.get("highestPrice1Year"), 1 / 1000), sc(det.get("lowestPrice1Year"), 1 / 1000)
        t52 = tile("Cao / thấp 52T (trong phiên)", f"{vn(hd, 1)} / {vn(ld, 1)}" if hd is not None and ld is not None else "",
                   f"Vietcap details, {anh_chup(dmeta)}", None, T2)
    nn = v((h.get("ngoai") or {}).get("hien"))
    room = v((h.get("ngoai") or {}).get("room"))
    nn_phu = f"room còn {vn(room, 0)} cp" if room is not None else ""
    if nn is None:
        nn = sc(det.get("foreignerPercentage"), 100)
        nn_phu = f"Vietcap details, {anh_chup(dmeta)}"
    tran = sc(det.get("maximumForeignPercentage"), 100)
    tp = num(det.get("targetPrice"))
    upside = (tp / gia - 1) * 100 if tp and gia else None
    gt_tb = sc(det.get("averageMatchValue1Month"), 1 / 1e9)
    gt_txt = ("" if gt_tb is None else f"GT TB {vn(gt_tb * 1000, 1)} triệu/phiên" if gt_tb < 0.01
              else f"GT TB {vn(gt_tb, 2 if gt_tb < 10 else 0)} tỷ/phiên")
    ff_o = (h.get("fft") or {}).get("ff") or {}
    ff = v(ff_o)
    ff_phu = f"Vietcap freeFloatPercentage, ảnh chụp {ddmm(ff_o.get('t_lay'), False)}" if ff is not None else ""
    if ff is None:
        ff = sc(det.get("freeFloatPercentage"), 100)
        ff_phu = f"Vietcap details, {anh_chup(dmeta)}" if ff is not None else ""
    tiles = [
        tile((f"Giá bảng · {ddmm(q.get('luc'), False)} {str(q.get('luc') or '')[11:16]}" if live
              else f"Đóng phiên Vietcap · {ddmm(q.get('luc'), False)}"), vn(gia, 0),
             f"{vn(q.get('pct'), 2, True, '%')} so tham chiếu {vn(q.get('tham_chieu'), 0)} · KL {vn(q.get('kl'), 0)}",
             mau_sign(q.get("pct"), 0.05), T2, live=live),
        tile("Vốn hoá (tỷ)", vn(shares * gia / 1e9, 0) if shares and gia else "", "số cp lưu hành × giá ô bên", None, T2),
        tile("CP lưu hành", vn(shares, 0), f"tới {ddmm(vt(cp.get('hien_tai')))}" if vt(cp.get("hien_tai")) else
             f"Vietcap details, {anh_chup(dmeta)}", None, T2),
        tile("Free float", vn(ff, 1, suffix="%") if ff is not None else "", ff_phu, None, T2),
        tile("NN sở hữu / trần", (f"{vn(nn, 2, suffix='%')} / {vn(tran, 0, suffix='%')}" if nn is not None else ""), nn_phu,
             None, T2),
        tile("KL TB 1 tháng", vn(det.get("averageMatchVolume1Month"), 0),
             jp(gt_txt, anh_chup(dmeta)), None, T2),
        t52,
        tile(f"Vietcap: {det.get('rating') or CAN}", vn(tp, 0) if tp else "",
             jp(f"TP · upside {vn(upside, 1, True, '%')} so giá ô đầu" if upside is not None else "",
                det.get("analyst") or "", f"ngày TP {det.get('ratingAsOf')}" if det.get("ratingAsOf") else ""),
             "vang" if tp else None, T3),
    ]
    sub = " · ".join(x for x in [san, nganh, " · ".join(A.RO_NHAN[r] for r in ro_list),
                                 nhom_chb if nhom_chb and not nhom_chb.startswith("KHÁC") else "",
                                 f"NAV {vn((h.get('nav') or {}).get('v'), 0)}%" if (h.get("nav") or {}).get("v") else ""] if x)
    canh = []
    try:
        tp_age = (date.today() - datetime.strptime(det.get("ratingAsOf") or "", "%d-%b-%y").date()).days
    except ValueError:
        tp_age = None
    if tp_age and tp_age > 180:
        canh.append(f"TP Vietcap cập nhật {det.get('ratingAsOf')} ({tp_age} ngày), quá cũ để xếp hạng theo upside.")
    d_age = tuoi_ngay(dmeta.get("lay_luc"))
    if d_age is not None and d_age > 7:
        canh.append(f"Ảnh chụp Vietcap details đã {d_age} ngày (thanh khoản, TP, trần NN).")
    if not live and gia is not None:
        canh.append("Mã không có trên bảng giá vnstore (thường là HNX/UPCOM): giá là đóng phiên cuối của Vietcap price-history.")
    if q.get("truoc_gdkhq"):
        canh.append(f"Phiên cuối của Vietcap nằm TRƯỚC ngày GDKHQ: giá điều chỉnh của chính phiên đó là "
                    f"{vn(q['truoc_gdkhq'], 0)}, tham chiếu phiên sau sẽ thấp hơn giá đang hiện.")
    if q.get("cu"):
        canh.append(f"Giá Vietcap dừng ở {ddmm(q.get('ngay'))}, cũ hơn bảng giá phiên {ddmm(A.NGAY_BANG)}.")
    if not h:
        canh.append(f"Chưa có hồ sơ Lăng kính lk_hoso/{tk}.json: free float, FFT, chủ thể, pha để trống.")
    stale = q.get("cu") or (not live and tuoi_ngay(q.get("luc")) not in (None,) and (tuoi_ngay(q.get("luc")) or 0) > 5)
    return o("ho_so", f"{tk} · {ten}", [o_so(tiles, 4), canh_bao("Lưu ý", canh)], 12, sub, "chaebol_map",
             "Chaebol map · Vietcap IQ", T2, "cu" if stale else trang_thai(q.get("luc"), 3 if live else 5))


# ───────────────────────────── 2 · giá ─────────────────────────────

def o_gia(tk, h, sau, san="", co_chart=True):
    meta, ph = vc(tk, "price-history")
    if not isinstance(ph, dict) or not ph.get("hang"):
        return o("gia", "Giá điều chỉnh toàn chuỗi", pha_khoi(sau), 8, "Giá + VWAP", "langkinh", "Lăng kính FFT",
                 ghi_chu=f"{CAN} chưa có vc_lk/{tk}/price-history.json")
    cot = ph["cot"]
    i_d, i_c = cot.index("tradingDate"), cot.index("closePriceAdjusted")
    i_raw = cot.index("closePrice") if "closePrice" in cot else None
    i_ref = cot.index("referencePrice") if "referencePrice" in cot else None
    tuan, last = {}, None
    for r in ph["hang"]:
        d, c = r[i_d], num(r[i_c])
        if not d or c is None:
            continue
        y, w, _ = date.fromisoformat(d[:10]).isocalendar()
        tuan[(y, w)] = (d[:10], c / 1000)
        if i_raw is not None and num(r[i_raw]) is not None:
            last = r
    pts = [tuan[k] for k in sorted(tuan)]
    xs, ys = [p[0] for p in pts], [round(p[1], 3) for p in pts]
    vw = h.get("vwap") or {}
    px = ys[-1] if ys else None
    w = (px or 50) * 0.0015
    ann = [a for a in [hband(v(vw.get("v6")), f"VWAP 6T {vn(vw.get('v6'), 1)}", "bull", w),
                       hband(v(vw.get("v12")), f"VWAP 12T {vn(vw.get('v12'), 1)}", "amber", w),
                       hband(v(vw.get("v24")), f"VWAP 24T {vn(vw.get('v24'), 1)}", "bear", w)] if a]
    g = h.get("gia") or {}
    for key, nhan, mk, mau in (("dinh_ls", "Đỉnh lịch sử", "tri_down", "bear"), ("day_52w", "Đáy 52T", "tri_up", "bull")):
        e = g.get(key) or {}
        ms, yv = iso_ms(e.get("ngay")), v(e.get("v"))
        if ms and yv is not None:
            ann.append({"kind": "point", "x": ms, "y": yv, "marker": mk, "pos": "above" if mk == "tri_down" else "below",
                        "text": f"{nhan} {vn(yv, 1)}", "mau": mau, "uu_tien": 1,
                        "tip": f"{nhan} {vn(yv, 1)} nghìn đồng ngày {ddmm(e.get('ngay'))}"})
    upcom = san == "UPCOM"
    ten_chuoi = "Giá điều chỉnh Vietcap (UPCOM: theo giá bình quân phiên)" if upcom else "Đóng cửa tuần (điều chỉnh)"
    block = {"x": xs, "left": {"label": "nghìn đồng (điều chỉnh)"}, "series": [
        {"name": ten_chuoi, "y": ys, "style": "line", "mau": "amber"}], "annotations": ann}
    if last is not None:
        c_raw, c_ref = num(last[i_raw]), (num(last[i_ref]) if i_ref is not None else None)
        t_last = tile(f"Đóng phiên {ddmm(last[i_d], False)}", vn(c_raw / 1000, 1),
                      f"{vn((c_raw / c_ref - 1) * 100, 2, True, '%')} so tham chiếu" if c_raw and c_ref else "giá thô Vietcap",
                      mau_sign((c_raw / c_ref - 1) * 100 if c_raw and c_ref else None, 0.05), T2)
    else:
        t_last = tile("Đóng phiên cuối", "", "", None, T2)
    vw_t = vt(vw.get("v6"))
    tiles = [
        t_last,
        tile("So VWAP 6T / 12T / 24T", f"{vn(vw.get('kc6'), 1, True, '%')} / {vn(vw.get('kc12'), 1, True, '%')} / "
                                       f"{vn(vw.get('kc24'), 1, True, '%')}" if num(vw.get("kc6")) is not None else "",
             f"tính tới {ddmm(vw_t, False)} · nhãn {vw.get('nhan') or '—'}" if vw_t else "cần hồ sơ Lăng kính", None, EST),
        tile("Từ đáy 52T: mã / VN-Index", f"{vn((g.get('tu_day') or {}).get('ma'), 1, True, '%')} / "
                                         f"{vn((g.get('tu_day') or {}).get('chiso'), 1, True, '%')}" if g.get("tu_day") else "",
             jp(f"đáy {ddmm((g.get('tu_day') or {}).get('ngay_day'))}" if (g.get("tu_day") or {}).get("ngay_day") else "",
                f"YTD {vn(g.get('ytd'), 1, True, '%')} tới {ddmm(h.get('phien_cuoi'), False)}"
                if num(g.get("ytd")) is not None else ""), None, T2),
        tile("RRG so VN-Index", (h.get("rrg") or {}).get("goc") or "", f"tuần {ddmm((h.get('rrg') or {}).get('t_cuoi'))}",
             None, EST),
    ]
    return o("gia", "Giá điều chỉnh toàn chuỗi + VWAP 6T/12T/24T", [
        bieu_do("Giá điều chỉnh tuần (UPCOM: theo giá bình quân phiên)" if upcom else "Giá đóng cửa tuần, điều chỉnh quyền", block, f"{len(xs)} tuần · {ddmm(xs[0])} → {ddmm(xs[-1])} · vạch ngang = VWAP cụm (EST)",
                "vc_lk price-history.closePriceAdjusted" + (" (UPCOM: = averagePrice điều chỉnh)" if upcom else "")
                + " · VWAP: Lăng kính lk_hoso", f"{T2} {EST}", 300) if co_chart else None,
        o_so(tiles, 4)] + pha_khoi(sau), 8, "Giá + phase", "langkinh", "Lăng kính FFT", T2,
        trang_thai(meta.get("du_lieu_toi"), 4))


# ───────────────────────────── 3 · định giá ─────────────────────────────

def sigma_phu(x):
    """'15,67x · μ 40,20 · σ 29,17 · TRUNG TÍNH' chỉ với phần có số."""
    return jp(f"{vn(x.get('now'), 2)}x" if num(x.get("now")) is not None else "",
              f"μ {vn(x.get('mean'), 2)}" if num(x.get("mean")) is not None else "",
              f"σ {vn(x.get('sd'), 2)}" if num(x.get("sd")) is not None else "", x.get("zone") or "")


def _src_nhan(src):
    if src == "vietcap" or (isinstance(src, dict) and "vietcap" in src.values()):
        return "Vietcap"
    if src == "spg":
        return "S&P CapIQ"
    return str(src) if src else "không rõ"


def _hhp_chart_block(r, chon):
    ch = ((r or {}).get(chon) or {}).get("chart") or {}
    price = ch.get("price") or []
    if not price:
        return None
    xs = [iso(p[0]) for p in price]

    def col(key):
        mp = {p[0]: p[1] for p in ch.get(key) or []}
        return [mp.get(p[0]) for p in price]
    return {"x": xs, "left": {"label": "nghìn đồng"}, "series": [
        {"name": "±1σ", "style": "band", "y_lo": col("cheap1"), "y_hi": col("rich1"), "mau": "grey", "alpha": 0.16},
        {"name": "Giá hợp lý (μ)", "y": col("fair"), "style": "dash", "mau": "blue"},
        {"name": "Giá điều chỉnh", "y": [p[1] for p in price], "style": "line", "mau": "amber"}]}


def _band_rows(get_band, gia):
    rows = []
    for k, nhan, mau in (("cheap2", "−2σ", "xanh"), ("cheap1", "−1σ", "xanh"), ("fair", "μ (hợp lý)", None),
                         ("rich1", "+1σ", "do"), ("rich2", "+2σ", "do")):
        bv = get_band(k)
        if bv is not None and bv <= 0:
            rows.append([cell(nhan, mau, mono=False, dam=True), cell("suy biến", "xam"), cell("")])
            continue
        rows.append([cell(nhan, mau, mono=False, dam=True), cell(vn(bv, 0)),
                     cell(vn((bv / gia - 1) * 100, 1, True, "%") if bv and gia else "")])
    return rows


def o_dinh_gia(tk, q, sau, co_chart=True):
    hv = (A.hhp_all().get("by_ticker") or {}).get(tk) or {}
    try:
        import hhp_valuation as H  # noqa: PLC0415 (26 ms)
        r = H.build_ticker(H.data_dir(), tk)
    except Exception:  # noqa: BLE001, mã ngoài chuỗi HHP
        r = None
    gia = q.get("gia") or num(hv.get("price_now"))
    if not hv:
        pe_r, pb_r = (r or {}).get("pe") or {}, (r or {}).get("pb") or {}
        if pe_r.get("sigma") is None and pb_r.get("sigma") is None:
            return o("dinh_gia", "Định giá HHP", [], 4, "Định giá", "hhp_valuation", "Định giá HHP",
                     ghi_chu=f"{CAN} mã ngoài bảng HHP (hhp_vn100_valuation) và chưa có chuỗi hhp_vn100_series; cần đưa mã "
                             "vào vũ trụ của engine HHP.")
        def cv(x):  # cùng luật "dao động lớn" của tab HHP: σ/μ ≥ 0,6 thì dải kém tin cậy
            return (num(x.get("sd")) or 0) / num(x.get("mean")) if num(x.get("mean")) else 9.0
        chon = "pe" if pe_r.get("sigma") is not None else "pb"
        if chon == "pe" and pb_r.get("sigma") is not None and cv(pe_r) >= 0.6 > cv(pb_r):
            chon = "pb"
        tiles = [tile(f"{'P/E' if m == 'pe' else 'P/B'} σ", vn(x.get("sigma"), 2, True, "σ"),
                      jp(sigma_phu(x), "dải kém tin cậy" if cv(x) >= 0.6 else "", "thước đo ngành chưa chấm"),
                      zone_mau(x.get("zone")) if m == chon else None, EST)
                 for m, x in (("pe", pe_r), ("pb", pb_r)) if x.get("sigma") is not None]
        ch = (r.get(chon) or {}).get("chart") or {}

        def last_band(k):
            pts = ch.get(k) or []
            return pts[-1][1] * 1000 if pts and pts[-1][1] is not None else None
        khoi = [o_so(tiles, 2)]
        blk = _hhp_chart_block(r, chon) if co_chart else None
        if blk:
            khoi.append(bieu_do("Dải σ HHP trong không gian giá", blk, "Engine HHP chạy riêng cho mã (ngoài bảng VN100)",
                                "engine HHP · hhp_valuation.build_ticker", EST, 220))
        khoi.append(bang(["Vùng giá " + ("P/B" if chon == "pb" else "P/E"), "Giá (đồng)", "so giá"],
                         _band_rows(last_band, gia), f"Điểm cuối dải σ của engine · {ddmm(r.get(chon, {}).get('as_of'))}",
                         can_phai=[1, 2]))
        return o("dinh_gia", "Định giá HHP · σ P/E, P/B (engine riêng)", khoi, 4, "Định giá", "hhp_valuation",
                 "Định giá HHP", EST, "cu" if trang_thai((r.get(chon) or {}).get("as_of"), 4) == "du" else
                 trang_thai((r.get(chon) or {}).get("as_of"), 4),
                 "mã ngoài bảng HHP chính, engine chạy riêng: độ tin cậy và thước đo ngành chưa chấm")
    hh = (sau or {}).get("hhp") or {}
    chon = hh.get("thuoc_do") or ("pb" if (hv.get("pb") or {}).get("reliable") and not (hv.get("pe") or {}).get("reliable") else "pe")
    fw = hv.get("forward") or {}
    cq = fw.get("capiq") or hv.get("capiq") or {}
    if num(cq.get("tp_med")) is None and num(cq.get("tp")) is None:
        cq = {}  # khung capiq toàn null (chỉ có khoá exported/ttm) → coi như không có
    src = _src_nhan(fw.get("src"))
    tiles = []
    for m in ("pe", "pb"):
        x = hv.get(m) or {}
        nm = "P/E" if m == "pe" else "P/B"
        tiles.append(tile(f"{nm} σ{' · thước đo ngành' if m == chon else ''}", vn(x.get("sigma"), 2, True, "σ"),
                          jp(sigma_phu(x), "" if x.get("reliable") or not x else "dải kém tin cậy"),
                          zone_mau(x.get("zone")) if m == chon else None, EST))
    pe_fw = " / ".join(vn(fw.get(k), 1) for k in ("pe", "pe2") if fw.get(k) is not None)
    phu_fw = [f"P/B {vn(fw.get('pb'), 2)}" if fw.get("pb") is not None else "",
              f"ROE {vn(fw.get('roe'), 1)}%" if fw.get("roe") is not None else "", f"nguồn {src}"]
    if pe_fw or fw.get("pb") is not None:
        tiles.append(tile("P/E forward " + ("2026F / 2027F" if fw.get("pe2") is not None else "2026F"), pe_fw,
                          " · ".join(x for x in phu_fw if x), None, T3))
    if cq:
        tiles.append(tile("CapIQ đồng thuận", vn(cq.get("tp_med") or cq.get("tp"), 0),
                          f"{cq.get('n_tp') or '?'} TP · {cq.get('rec') or ''} · thấp/cao {vn(cq.get('tp_low'), 0)}/"
                          f"{vn(cq.get('tp_high'), 0)} · {ddmm(cq.get('tp_date'))}", None, T3))
    elif fw.get("tp"):
        tiles.append(tile(f"TP forward ({src})", vn(fw.get("tp"), 0) if fw.get("tp") else "",
                          f"upside {vn(fw.get('upside_pct'), 1, True, '%')}" if fw.get("upside_pct") is not None else "", None, T3))
    band = hh.get("band") or {}
    xb = hv.get(chon) or {}
    khoi = [o_so(tiles, 2),
            bang(["Vùng giá " + ("P/B" if chon == "pb" else "P/E"), "Giá (đồng)", "so giá bảng"],
                 _band_rows(lambda k: num(band.get(k)) or num(xb.get(f"band_{k}")), gia),
                 f"Dải σ trên lịch sử của chính mã (phương pháp Huỳnh Hoàng Phương) · {ddmm(xb.get('ratio_date'))}",
                 can_phai=[1, 2])]
    blk = _hhp_chart_block(r, chon) if co_chart else None
    if blk:
        khoi.insert(1, bieu_do("Dải σ HHP trong không gian giá",
                               blk, f"Dải {chon.upper().replace('PE', 'P/E').replace('PB', 'P/B')} ±1σ trong không gian giá",
                               "engine HHP · hhp_valuation.build_ticker", EST, 220))
    return o("dinh_gia", "Định giá HHP · σ P/E, P/B, forward", khoi, 4, "Định giá", "hhp_valuation", "Định giá HHP",
             EST, trang_thai(xb.get("ratio_date"), 4))


# ───────────────────────────── 4 · KQKD + dự phóng ─────────────────────────────

KQ_DONG = [("revenue", "Doanh thu (tỷ)", "ty"), ("revenueGrowth", "Tăng trưởng doanh thu", "pct"),
           ("NPATMI", "LNST cổ đông mẹ (tỷ)", "ty"), ("NPATMIGrowth", "Tăng trưởng LNST", "pct"),
           ("eps", "EPS (đồng)", "dong"), ("EPSGrowth", "Tăng trưởng EPS", "pct"), ("roe", "ROE", "pct"),
           ("roa", "ROA", "pct"), ("pe", "P/E", "x"), ("pb", "P/B", "x"), ("dividendYield", "Tỷ suất cổ tức", "pct")]
# vietcap_fundamentals income: dòng theo ngành (DN thường · ngân hàng · chứng khoán), lấy dòng đầu tiên có số
FUND_DT = ("Doanh thu thuần", "Thu nhập lãi thuần", "Doanh thu thuần về hoạt động kinh doanh", "DOANH THU HOẠT ĐỘNG")
FUND_LN = ("Lợi nhuận của Cổ đông của Công ty mẹ", "Cổ đông của Công ty mẹ", "LỢI NHUẬN KẾ TOÁN SAU THUẾ",
           "Lợi nhuận sau thuế")


def fmt_kq(x, kieu):
    if kieu == "ty":
        return vn(x, 0)
    if kieu == "pct":
        return vn((num(x) * 100) if num(x) is not None else None, 1, suffix="%")
    if kieu == "x":
        return "n.m." if num(x) is not None and num(x) <= 0 else vn(x, 2)
    return vn(x, 0)


def _kq_fundamentals(tk):
    """Năm thực tế từ vietcap_live/vietcap_fundamentals.json (FACT-T2) khi chưa có bản Vietcap đăng nhập."""
    d = read_json(A.SYS_DIR / "vietcap_live" / "vietcap_fundamentals.json") or {}
    inc = (((d.get("by_ticker") or {}).get(tk) or {}).get("financials") or {}).get("income") or {}
    if not isinstance(inc, dict) or not inc:
        return None
    yrs = sorted(inc)

    def line(row, keys):
        for k in keys:
            if num((row or {}).get(k)) is not None:
                return k, num(row[k])
        return None, None
    dt_k, ln_k = line(inc[yrs[-1]], FUND_DT)[0], line(inc[yrs[-1]], FUND_LN)[0]
    if not dt_k and not ln_k:
        return None
    dong = []
    for key, nhan in ((dt_k, f"{dt_k} (tỷ)"), (ln_k, f"{ln_k} (tỷ)")):
        if key:
            dong.append([cell(nhan, mono=False)] + [cell(vn(sc((inc[y] or {}).get(key), 1 / 1e9), 0)) for y in yrs])
    return bang(["Chỉ tiêu"] + yrs, dong, f"vietcap_live/vietcap_fundamentals.json (FACT-T2), dựng "
                f"{ddmm(d.get('generated_at'))}. Chỉ năm thực tế, chưa có dự phóng: bộ ghi Vietcap đăng nhập chưa chạy "
                "cho mã này.", can_phai=list(range(1, len(yrs) + 1))), d.get("generated_at")


def _kq_earning(tk):
    er_meta, er = vc(tk, "earning-result", True)
    if not (isinstance(er, dict) and er.get("earningData")):
        return None
    ex = er.get("extras") or {}
    rows = []
    for e in er["earningData"]:
        nm = e.get("name")
        if nm not in ("revenue", "npatMi", "revenueGrowth", "npatMiGrowth"):
            continue
        is_g = "Growth" in nm
        f = (lambda x: vn((num(x) or 0) * 100, 1, suffix="%") if num(x) is not None else "") if is_g else \
            (lambda x: vn((num(x) or 0) / 1e9, 0) if num(x) is not None else "")
        pct = num(e.get("percentOfCurrentYear"))
        rows.append([cell({"revenue": "Doanh thu (tỷ)", "npatMi": "LNST cổ đông mẹ (tỷ)", "revenueGrowth": "Tăng trưởng DT",
                           "npatMiGrowth": "Tăng trưởng LNST"}[nm], mono=False),
                     cell(f(e.get("prevYearValue"))), cell(f(e.get("currentYearForecastValue")), "vang"),
                     cell(f(e.get("currentYearCumulativeValue"))),
                     cell(vn(pct * 100, 1, suffix="%") if pct is not None else "", "xanh" if (pct or 0) > 0.75 else None)])
    if not rows:
        return None
    co_du_phong = any(num(e.get("currentYearForecastValue")) is not None for e in er["earningData"]
                      if e.get("name") in ("revenue", "npatMi", "revenueGrowth", "npatMiGrowth"))
    if not co_du_phong:  # mã Vietcap không phủ: bỏ hai cột dự phóng trống
        rows = [[r[0], r[1], r[3]] for r in rows]
        return bang(["Chỉ tiêu", "Năm trước", f"Luỹ kế {ex.get('cumulativeQuarter') or ''}"], rows,
                    "Endpoint earning-result của Vietcap (tách khỏi bảng năm); Vietcap không có dự phóng cho mã này.",
                    can_phai=[1, 2]), er_meta.get("lay_luc")
    return bang(["Chỉ tiêu", "Năm trước", f"Dự phóng {ex.get('currentYear') or ''} (Vietcap)",
                 f"Luỹ kế {ex.get('cumulativeQuarter') or ''}", "% so dự phóng"], rows,
                "Endpoint earning-result của Vietcap (tách khỏi bảng năm, có thể lệch nhẹ). % so dự phóng cao giữa năm "
                "nghĩa là dự phóng đang thấp hơn thực tế, không phải dấu hiệu hành động.", can_phai=[1, 2, 3, 4]), er_meta.get("lay_luc")


def o_kqkd(tk):
    meta, fd = vc(tk, "financial-data", True)
    nguon = "Vietcap IQ (phiên đăng nhập)"
    if not isinstance(fd, dict) or not any(isinstance(fd.get(k), dict) and fd[k] for k, _, _ in KQ_DONG):
        meta, fd = vc(tk, "financial-data")
        nguon = "Vietcap IQ (chưa đăng nhập)"
    co_fd = isinstance(fd, dict) and isinstance(fd.get("revenue"), dict) and \
        any(x is not None for x in (fd.get("revenue") or {}).values())
    khoi, moc = [], meta.get("lay_luc")
    if co_fd:
        ky_all = list(fd["revenue"].keys())
        # cột F của mã không có dự phóng: Vietcap chép P/E, P/B TTM sang → coi là trống
        rong_f = {k for k in ky_all if "F" in k and num((fd.get("revenue") or {}).get(k)) is None
                  and num((fd.get("NPATMI") or {}).get(k)) is None}
        ky = [k for k in ky_all if k not in rong_f]
        dong = []
        for key, nhan, kieu in KQ_DONG:
            row = fd.get(key) or {}
            if not isinstance(row, dict) or not row:
                continue
            dong.append([cell(nhan, mono=False)] + [cell(fmt_kq(row.get(k), kieu), "vang" if "F" in k else
                                                         (mau_sign(row.get(k), 0) if kieu == "pct" and "Growth" in key else None))
                                                    for k in ky])
        khoi.append(bang(["Chỉ tiêu"] + [f"{k} · Vietcap" if "F" in k else k for k in ky], dong,
                         f"{nguon}, lấy {ddmm(meta.get('lay_luc'))}. Năm thực tế và TTM FACT-T2 · cột F là dự phóng của "
                         "Vietcap SS-T3, không phải kế hoạch doanh nghiệp"
                         + (" · Vietcap không có dự phóng cho mã này." if rong_f and len(rong_f) == len([k for k in ky_all if "F" in k])
                            else (f" · Vietcap chưa có dự phóng {', '.join(sorted(rong_f))}." if rong_f else ".")),
                         can_phai=list(range(1, len(ky) + 1))))
        np_ = fd.get("NPATMI") or {}
        if np_:
            khoi.append(bieu_do("LNST cổ đông mẹ theo năm (tỷ)", {"loai": "cot", "huong": "doc", "nhan": ky,
                                     "series": [{"name": "LNST cổ đông mẹ (tỷ)", "y": [num(np_.get(k)) for k in ky], "mau": "lam",
                                                 "mau_tung": ["vang" if "F" in k else None for k in ky]}],
                                     "gia_tri": True, "dv": "", "so_le": 0},
                                "Vàng = dự phóng Vietcap", nguon, f"{T2} {T3}", 200))
    else:
        fb = _kq_fundamentals(tk)
        if fb:
            khoi.append(fb[0])
            moc = fb[1]
    er = _kq_earning(tk)
    if er:
        khoi.append(er[0])
        moc = moc or er[1]
    return o("kqkd", "KQKD + dự phóng (Vietcap IQ)", khoi, 7, "Lợi nhuận KD", "chaebol_map", "Chaebol map · Vietcap IQ",
             f"{T2} {T3}", (trang_thai(moc, 10) if moc else "cu") if khoi else "thieu",
             f"{CAN} chưa có KQKD: bộ ghi Vietcap đăng nhập (vciq_dangnhap_nap.py) chưa lấy financial-data/earning-result "
             f"cho {tk} và vietcap_fundamentals không có mã này." if not khoi else "")


# ───────────────────────────── 5 · P/E × LS (Toàn Vũ) ─────────────────────────────

def o_pe_tv(tk, tv):
    if not tv:
        return o("pe_tv", "P/E × lãi suất · luật Toàn Vũ", [], 5, "P/E×LS TV", "toanvu_pe", "P/E×LS TV",
                 ghi_chu=f"{CAN} mã không có trong bộ Bloomberg của Toàn Vũ")
    cur = tv.get("hien_tai") or {}
    c = tv.get("chuoi") or {}
    xs = c.get("x") or []
    i0 = max(0, len(xs) - 260)
    if not any(num(v) is not None for v in (c.get("pe") or [])[i0:]):
        return o("pe_tv", "P/E × lãi suất · luật Toàn Vũ", [], 5, "P/E×LS TV", "toanvu_pe", "P/E×LS TV",
                 ghi_chu=f"{CAN} chuỗi P/E Bloomberg 5 năm của {tk} không có điểm hữu hạn nào (lỗ hoặc thiếu)")
    def pv(x, nd=1):
        return vn(x, nd) if num(x) is not None else CAN
    kh = cur.get("kich_hoat")
    block = {"x": xs[i0:], "left": {"label": "P/E (lần)", "min": 0}, "series": [
        {"name": "P10–P90 250 phiên", "style": "band", "y_lo": (c.get("p10") or [])[i0:], "y_hi": (c.get("p90") or [])[i0:],
         "mau": "grey", "alpha": 0.18},
        {"name": "Ngưỡng rẻ theo luật TV", "y": (c.get("pe_nguong") or [])[i0:], "style": "dash", "mau": "amber"},
        {"name": "P/E trailing", "y": (c.get("pe") or [])[i0:], "style": "line", "mau": "ink"}]}
    tiles = [
        tile(f"P/E · {ddmm(cur.get('ngay'), False)}", vn(cur.get("pe"), 2, suffix="x"),
             f"EY {vn(cur.get('ey'), 2)}% · EPS ngầm {vn(cur.get('eps_ngam'), 0)}", None, T2),
        tile("Percentile / ngưỡng", f"P{pv(cur.get('pct'))} / P{pv(cur.get('nguong'))}", f"LS {vn(cur.get('ls'))}%", None, EST),
        tile("Luật TV", "KÍCH HOẠT" if kh else ("KHÔNG" if kh is False else CAN),
             f"P/E < {pv(cur.get('pe_nguong'), 2)}x ↔ giá < {pv(cur.get('gia_nguong'), 0)}"
             if num(cur.get("pe_nguong")) is not None else "", "vang" if kh else "xam", T3),
        tile("ERP mã", vn(cur.get("erp"), 2, True, " điểm"), f"hướng LS 6T: {cur.get('huong_ls') or ''}",
             mau_sign(cur.get("erp"), 0.5), EST),
    ]
    return o("pe_tv", "P/E × lãi suất · luật Toàn Vũ", [
        bieu_do("P/E so với vùng rẻ theo luật TV", block, "5 năm gần nhất (tuần). Đường cam: P/E tại percentile ngưỡng (đổi theo LS).",
                "Bloomberg PE_RATIO · FiinProX LS · luật TV", f"{T2} {EST}", 230),
        o_so(tiles, 2),
        doan("Kiểm định của Hội đồng: trễ EPS 45 ngày cho đúng lúc thị trường biết thì luật hết lợi thế trên toàn rổ; "
             "đọc như một vùng tham chiếu, không phải tín hiệu.", "xam")], 5, "P/E×LS TV", "toanvu_pe", "P/E×LS TV",
        f"{T3} {EST}", trang_thai(cur.get("ngay"), 5) if num(cur.get("pe")) is not None else "cu",
        "" if num(cur.get("pe")) is not None else "Bloomberg không có P/E phiên gần nhất (lỗ hoặc thiếu)")


# ───────────────────────────── 6 · FFT + dòng tiền ─────────────────────────────

def o_fft(tk, h):
    f = h.get("fft") or {}
    if not f or not (f.get("chuoi") or {}).get("t"):
        return o("fft", "Lăng kính FFT", [], 6, "Cổ đông + FFT", "langkinh", "Lăng kính FFT",
                 ghi_chu=f"{CAN} chưa có lk_hoso/{tk}.json" if not h else
                 f"{CAN} lk_hoso/{tk}.json có nhưng chuỗi FFT tuần rỗng (thiếu free float hoặc khối lượng)")
    c = f.get("chuoi") or {}
    t = c.get("t") or []
    i0 = max(0, len(t) - 156)
    block = {"x": t[i0:], "left": {"label": "% free float / tuần", "min": 0}, "right": {"label": "giá (nghìn đồng)"},
             "series": [
                 {"name": "FFT tuần", "y": (c.get("fw") or [])[i0:], "style": "thin", "mau": "grey"},
                 {"name": "TB 4 tuần", "y": (c.get("f") or [])[i0:], "style": "line", "mau": "up"},
                 {"name": "P10 3Y", "y": (c.get("p10") or [])[i0:], "style": "dash", "mau": "blue"},
                 {"name": "P90 3Y", "y": (c.get("p90") or [])[i0:], "style": "dash", "mau": "down"},
                 {"name": "Giá đóng tuần", "y": (c.get("c") or [])[i0:], "style": "line", "mau": "amber", "axis": "right"}]}
    ng, td = h.get("ngoai") or {}, h.get("tudoanh") or {}
    ct = h.get("chuthe") or {}
    pha = h.get("pha") or {}
    tiles = [
        tile("FFT pct 3Y · toàn dải", f"P{vn(f.get('pct3y'), 0)} · P{vn(f.get('pall'), 0)}",
             f"lệch {vn(f.get('lech'), 0, True)} điểm, đọc cả hai cửa sổ", None, T2),
        tile("TB 4 tuần ÷ P10 3Y", vn(f.get("x_p10"), 2, suffix="×"),
             f"TB4 {vn(f.get('ma4'), 3)}% · P10 {vn(f.get('p10_3y'), 3)}% · P90 {vn(f.get('p90_3y'), 3)}%", None, EST),
        tile("Chủ thể cần thị trường?", nfc(((ct.get("nhan") or {}).get("v"))), "nhãn tĩnh, chưa chấm lại", None, T3),
        tile("Pha (tác giả)", pha.get("nhan") or "", jp(pha.get("phu") or "", ddmm(pha.get("ngay"))), None, T3),
        tile("NN ròng 20 / 63 phiên (cp)", jp(vn(((ng.get('rong_20') or {}).get('cp')), 0, True),
                                             vn(((ng.get('rong_63') or {}).get('cp')), 0, True), sep=" / "),
             jp(f"YTD {vn(((ng.get('ytd') or {}).get('cp')), 0, True)}" if num((ng.get("ytd") or {}).get("cp")) is not None else "",
                f"sở hữu {vn(ng.get('hien'), 2)}%" if num(ng.get("hien")) is not None else ""),
             mau_sign(((ng.get("rong_20") or {}).get("cp")), 0), T2),
        tile("Tự doanh ròng 20 / 63 phiên (tỷ)", jp(vn(td.get('rong_20'), 1, True), vn(td.get('rong_63'), 1, True), sep=" / "),
             f"YTD {vn(td.get('ytd'), 1, True)} tỷ" if num(td.get("ytd")) is not None else "không có bản ghi tự doanh",
             mau_sign(td.get("rong_20"), 0), T2),
    ]
    return o("fft", "Lăng kính FFT · dòng tiền", [
        bieu_do("FFT tuần so với dải P10/P90 3Y", block, "3 năm gần nhất. FFT là proxy: im lặng không có nghĩa là không phân phối (v1.7 §4).",
                "vc_lk price-history.totalMatchVolume ÷ (ff × cp) · Lăng kính lk_hoso", EST, 230),
        o_so(tiles, 3), canh_bao("Cảnh báo dữ liệu FFT", (f.get("canh_bao") or [])[:3])],
        6, "Cổ đông + FFT", "langkinh", "Lăng kính FFT", f"{T2} {EST}", trang_thai(c.get("t_cuoi"), 9))


# ───────────────────────────── 7 · cổ đông ─────────────────────────────

def o_co_dong(tk, h):
    cd = h.get("codong") or {}
    cc = cd.get("co_cau") or {}
    lk_lay = max((x.get("t_lay") or "" for x in cc.values() if isinstance(x, dict)), default="")
    ss_meta, ss = vc(tk, "shareholder-structure")
    ss = ss[0] if isinstance(ss, list) and ss else ss
    vc_moi = isinstance(ss, dict) and (ss_meta.get("lay_luc") or "") > lk_lay
    nguon_cc = f"Lăng kính lk_hoso, ảnh chụp {ddmm(lk_lay, False)}"
    if vc_moi:  # ảnh chụp Vietcap mới hơn bản Lăng kính → dùng thẳng
        cc = {"foreign": sc(ss.get("foreignPercentage"), 100), "state": sc(ss.get("statePercentage"), 100),
              "bod": sc(ss.get("bodPercentage"), 100), "other": sc(ss.get("otherPercentage"), 100)}
        nguon_cc = f"Vietcap shareholder-structure, ảnh chụp {ddmm(ss_meta.get('lay_luc'), False)}"
    tiles = [tile(nhan, vn(cc.get(k), 2, suffix="%"), nguon_cc if k != "bod" else "nằm trong các nhóm bên cạnh, không cộng thêm",
                  None, T2)
             for k, nhan in (("foreign", "Nước ngoài"), ("state", "Nhà nước"), ("other", "Khác"), ("bod", "Trong đó HĐQT / BĐH"))
             if num(cc.get(k)) is not None]
    lon = [[cell(cut(x.get("ten"), 46), mono=False), cell(x.get("loai") or "", mono=False),
            cell(vn(x.get("pct"), 2, suffix="%")), cell(vn(x.get("sl"), 0)), cell(ddmm(x.get("ngay")))]
           for x in (cd.get("lon") or [])[:8]] if not vc_moi else []
    ngay_lon = lk_lay or (cd.get("lon") or [{}])[0].get("ngay")
    if not lon:  # chưa có hồ sơ Lăng kính, hoặc Vietcap mới hơn → đọc thẳng Vietcap shareholder
        _, sh = vc(tk, "shareholder")
        sh = sorted([x for x in (sh or []) if isinstance(x, dict)], key=lambda x: -(num(x.get("percentage")) or 0))[:8]
        lon = [[cell(cut(x.get("ownerName"), 46), mono=False), cell(x.get("ownerType") or "", mono=False),
                cell(vn((num(x.get("percentage")) or 0) * 100, 2, suffix="%")), cell(vn(x.get("quantity"), 0)),
                cell(ddmm(x.get("publicDate")))] for x in sh]
        sh_meta, _ = vc(tk, "shareholder")
        ngay_lon = sh_meta.get("lay_luc") or max((x.get("publicDate") or "" for x in sh), default=None)
    moc = [[cell(m.get("ky")), cell(vn(m.get("v"), 0), dam=True), cell(m.get("kieu") or "", "vang" if m.get("cf") else None),
            cell(m.get("b") or "")] for m in (cd.get("moc") or [])[-6:]][::-1]
    con = ((h.get("chuthe") or {}).get("quan_he") or {}).get("con") or []
    khoi = [o_so(tiles, 4) if tiles else None,
            bang(["Cổ đông lớn", "Loại", "Sở hữu", "Số cp", "Ngày"], lon, "Vietcap shareholder (FACT-T2)", can_phai=[2, 3])
            if lon else None,
            bang(["Kỳ", "Số cổ đông", "Kiểu mốc", "Bậc"], moc,
                 f"{cd.get('nguon_moc') or 'fft_codong'} · CF/số tròn bị hạ một bậc (v1.7 §3.4)", can_phai=[1]) if moc else None,
            chips([(T2, f"{x.get('ten')} {vn(x.get('pct'), 1)}%" + (f" ({x['ma']})" if x.get("ma") else "")) for x in con[:8]])
            if con else None]
    return o("co_dong", "Cấu trúc cổ đông", khoi, 6, "Cổ đông", "chaebol_map", "Chaebol map · cấu trúc cổ đông",
             f"{T2} {T3}", trang_thai(ngay_lon, 200))


def o_noi_bo(tk, h):
    ct = h.get("chuthe") or {}
    nb_src = sorted(ct.get("noi_bo") or [], key=lambda x: x.get("ngay") or "", reverse=True)
    nb_nguon = "Vietcap insider-transaction qua Lăng kính · 'Mua' có thể là thực hiện quyền/ESOP (P/E×LS TV đã tách khỏi ròng)"
    if not nb_src:  # chưa có trong hồ sơ Lăng kính → đọc thẳng Vietcap (cửa sổ ~24 tháng như Lăng kính)
        _, it = vc(tk, "insider-transaction")
        cut_d = f"{date.today().year - 2}-{date.today():%m-%d}"
        nb_src = sorted([{"ngay": (x.get("displayDate2") or x.get("endDate") or x.get("startDate") or "")[:10],
                          "nguoi": x.get("traderNameVi") or "",
                          "chuc_vu": x.get("traderPositionVi") or "",
                          "hanh_dong": x.get("actionTypeVi") or "",
                          "thuc_hien": num(x.get("shareAcquire")) if num(x.get("shareAcquire")) is not None
                          else num(x.get("shareRegister"))}
                         for x in (it or []) if isinstance(x, dict)], key=lambda x: x["ngay"], reverse=True)
        nb_src = [x for x in nb_src if x["ngay"] >= cut_d]
        nb_nguon = "Vietcap insider-transaction (đọc thẳng, 24 tháng gần nhất; KL = shareAcquire, chưa xong thì = đăng ký)"
    nb = [[cell(ddmm(x.get("ngay"))), cell(cut(x.get("nguoi"), 26), mono=False), cell(cut(x.get("chuc_vu"), 30), mono=False),
           cell(cut(x.get("hanh_dong") or "", 24), "xanh" if x.get("hanh_dong") == "Mua" else
                ("do" if x.get("hanh_dong") == "Bán" else None), mono=False),
           cell(vn(x.get("thuc_hien") or x.get("dang_ky"), 0))] for x in nb_src[:7]]
    sk_src = sorted(ct.get("su_kien_von") or [], key=lambda x: x.get("cong_bo") or "", reverse=True)
    sk = [[cell(ddmm(x.get("cong_bo"))), cell(x.get("loai") or ""), cell(cut(x.get("tieu_de"), 70), mono=False)]
          for x in sk_src[:5]]
    _, fh = vc(tk, "funds-holding", True)
    khoi = []
    if isinstance(fh, list) and fh:
        # kỳ mới nhất thường chưa đủ quỹ nộp báo cáo: lấy kỳ gần nhất có số mã ≥ 80% kỳ đầy đủ nhất
        top = max((num(r.get("so_ma_trong_ky")) or 0) for r in fh if isinstance(r, dict))
        x = next((r for r in fh if isinstance(r, dict) and (num(r.get("so_ma_trong_ky")) or 0) >= 0.8 * top), fh[0])
        ch = x.get("percentHoldingChange") or {}
        khoi.append(o_so([
            tile(f"Nhóm quỹ Vietcap theo dõi · {x.get('ky')}", vn(x.get("quantity"), 0),
                 f"{vn((num(x.get('percentHoldingPerTotalShares')) or 0) * 100, 2)}% số cp · {x.get('totalFundHolding')} quỹ", None, T2),
            tile("Δ cp 1T / 3T / YTD", f"{vn((ch.get('1M') or {}).get('volume'), 0, True)} / {vn((ch.get('3M') or {}).get('volume'), 0, True)}"
                                       f" / {vn((ch.get('YTD') or {}).get('volume'), 0, True)}",
                 "kỳ mới nhất có thể chưa đủ quỹ nộp báo cáo", mau_sign((ch.get("1M") or {}).get("volume"), 0), T2)], 2))
    if nb:
        khoi.append(bang(["Ngày", "Người", "Chức vụ", "Hành động", "KL"], nb, nb_nguon, can_phai=[4]))
    if sk:
        khoi.append(bang(["Công bố", "Loại", "Sự kiện vốn"], sk, "Vietcap events-v2 (FACT-T2)"))
    moc = [(nb_src or [{}])[0].get("ngay"), (sk_src or [{}])[0].get("cong_bo")]
    if isinstance(fh, list) and fh and khoi:
        moc.append(f"{x.get('ky')}-01" if x.get("ky") else None)
    moc = max((str(m)[:10] for m in moc if m), default=None)
    tt = trang_thai(moc, 200) if moc else "cu"
    return o("noi_bo", "Nội bộ · quỹ · sự kiện vốn", khoi, 6, "Chủ thể", "deepfa", "DEEP FA", T2, tt)


# ───────────────────────────── 8 · pha giá ─────────────────────────────

def pha_khoi(sau):
    """Bảng pha giá zigzag 25% của P/E×LS TV, đặt trong ô Giá + phase."""
    pha = (sau or {}).get("pha") or []
    rows = []
    for p in pha[-7:][::-1]:
        rows.append([cell(f"{ddmm(p.get('tu'))} → {ddmm(p.get('den'))}" + (" ·" if p.get("dang_chay") else ""), mono=True),
                     cell(vn(p.get("r"), 0, True, "%"), mau_sign(p.get("r"), 0)),
                     cell(vn(p.get("eps_pct"), 0, True, "%")), cell(vn(p.get("pe_pct"), 0, True, "%")),
                     cell(p.get("kieu") or "", "xanh" if "Tăng" in (p.get("kieu") or "") else "vang", pill=True, mono=False),
                     cell(vn(p.get("vuot_vni"), 0, True)), cell(f"{vn(p.get('ls0'), 1)}→{vn(p.get('ls1'), 1)}")])
    if not rows:
        return []
    return [bang(["Pha giá: giá = EPS × P/E", "Giá", "EPS", "P/E", "Động lực", "Vượt VNI", "LS"], rows,
                 "Mỗi pha kết thúc khi giá đảo chiều ≥ 25%; '·' = pha đang chạy. EPS ngầm = giá ÷ P/E trailing (EST) · "
                 "nguồn P/E×LS TV.", can_phai=[1, 2, 3, 5])]


# ───────────────────────────── 9 · DEEP FA ─────────────────────────────

def memo_moi_nhat(tk):
    d = A.VAULT / "BaoCao_VN30"
    best = None
    for p in d.glob(f"{tk}_*.md"):
        m = re.match(rf"{tk}_(\d\d)-(\d\d)-(\d{{4}})\.md$", p.name)
        if m:
            dt = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if best is None or dt > best[0]:
                best = (dt, p)
    return best


def md_plain(s):
    s = re.sub(r"\*\*|__|`|^#+\s*|^>\s*", "", s.strip())
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)


def md_section(text, head_re):
    m = re.search(head_re, text, re.M)
    if not m:
        return ""
    rest = text[m.end():]
    n = re.search(r"^## ", rest, re.M)
    return rest[:n.start()] if n else rest


def o_deepfa(tk, h):
    best = memo_moi_nhat(tk)
    khoi = []
    tt, ngay = "thieu", None
    if best:
        ngay, p = best
        text = p.read_text(encoding="utf-8", errors="replace")
        first = md_plain(text.splitlines()[0]) if text else ""
        state = re.search(r"State [A-D][^*(·]*", first)
        th = [md_plain(x) for x in md_section(text, r"^## §1").split("\n\n") if x.strip()]
        cond = [md_plain(x) for x in md_section(text, r"^## §7").splitlines() if x.strip() and not x.startswith("---")]
        tuoi = (date.today() - ngay).days
        tt = "cu" if tuoi > 90 else "du"
        khoi.append(o_so([
            tile("Memo DEEP FA", ngay.strftime("%d/%m/%Y"), f"{tuoi} ngày" + (", quá hạn 90 ngày, cần regen" if tuoi > 90 else ""),
                 "do" if tuoi > 90 else None, UNV if tuoi > 90 else EST),
            tile("State", state.group(0).strip() if state else CAN, "nhãn của memo, không phải verdict", None, EST)], 2))
        if th:
            khoi.append(doan(cut(" ".join(th[:2]), 1100), the=True, tieu_de="§1 Thesis (trích memo, nguyên văn rút gọn)"))
        if cond:
            khoi.append({"kieu": "danh_sach", "muc": [{"so": str(i + 1), "tieu_de": "", "text": cut(c, 260), "tags": []}
                                                      for i, c in enumerate(cond[:7])]})
    edi = ((read_json(A.SYS_DIR / "early_detection" / "edi_index.json") or {}).get("by_ticker") or {}).get(tk) or {}
    fund = ((read_json(A.SYS_DIR / "fund_holdings" / "fund_intent_signals.json") or {}).get("signals") or {})
    fund = fund.get(tk) if isinstance(fund, dict) else None
    t2 = []
    if edi:
        t2.append(tile("EDI leading", f"{edi.get('edi')} · {edi.get('lead_status') or ''}",
                       ("LATE, edge đã chuyển sang FA/TA · " if edi.get("late_flag") else "") + ", ".join((edi.get("drivers") or [])[:2]),
                       None, EST))
    if isinstance(fund, dict):
        nc = fund.get("net_change") or {}
        t2.append(tile("Quỹ mở (Excel universe)", f"{vn((nc.get('m1') or {}).get('shares'), 0, True)} cp 1T",
                       f"{vn(fund.get('num_funds'), 0)} quỹ · {vn((num(fund.get('pct_outstanding')) or 0) * 100, 2)}% số cp · "
                       "chưa tách ETF/quỹ chủ động → không gán ACCUMULATION/DISTRIBUTION", None, T2))
    if t2:
        khoi.append(o_so(t2, 2))
    return o("deepfa", "DEEP FA · thesis & điều kiện falsifiable", khoi, 7, "Deep FA", "deepfa", "DEEP FA",
             EST, (tt if best else "cu") if khoi else "thieu",
             f"{CAN} chưa có memo BaoCao_VN30/{tk}_*.md" if not best else f"memo {ngay.strftime('%d/%m/%Y')}")


# ───────────────────────────── 10 · Hội đồng ─────────────────────────────

def o_hoi_dong(tk, sau):
    hd = A.toanvu("hoi_dong", tk) or {}
    bc = (sau or {}).get("bang_chung") or {}
    khoi = []
    if bc.get("chieu"):
        khoi.append(o_so([tile("Bằng chứng 6 chiều", f"{bc.get('nhan') or ''} ({vn(bc.get('diem'), 0, True)})",
                               "cộng phiếu ủng hộ − phản biện, không phải nhãn mua/bán", None, EST)], 1))
        khoi.append(bang(["Chiều", "Phiếu", "Nội dung", "Bậc"],
                         [[cell(c.get("k") or "", dam=True), cell({1: "ỦNG HỘ", -1: "PHẢN BIỆN"}.get(c.get("s"), "CHỜ"),
                                                                 {1: "xanh", -1: "do"}.get(c.get("s"), "xam"), pill=True),
                           cell(cut(c.get("t"), 80), mono=False), cell(c.get("bac") or "")] for c in bc["chieu"]]))
    if hd.get("tom_tat"):
        khoi.append(doan(cut(hd["tom_tat"], 900), the=True, tieu_de=f"Hội đồng · {ddmm(hd.get('ngay'))}"))
    if bc.get("xac_nhan") or bc.get("diem_gay"):
        khoi.append(bang(["", ""], [[cell("Xác nhận", "xanh", dam=True, mono=False), cell(bc.get("xac_nhan") or "", mono=False)],
                                    [cell("Điểm gãy", "do", dam=True, mono=False), cell(bc.get("diem_gay") or "", mono=False)]]))
    return o("hoi_dong", "Hội đồng · bằng chứng & điểm gãy", khoi, 5, "Synthesis", "toanvu_pe", "P/E×LS TV", EST,
             trang_thai(hd.get("ngay") or (sau or {}).get("phien"), 10))


# ───────────────────────────── 11 · research ─────────────────────────────

def o_research(tk, hv_row):
    rows = []
    hsc = (read_json(A.SYS_DIR / "hsc_research" / "chuoi.json") or {}).get("khuyen_nghi") or {}
    for x in hsc.get(tk) or []:
        rows.append((x.get("ngay_bc"), "HSC", x))
    bbg = (read_json(A.SYS_DIR / "bbg_research" / "chuoi.json") or {}).get("khuyen_nghi") or {}
    for k, lst in bbg.items():
        if k.split("·")[0] == tk:
            for x in lst or []:
                rows.append((x.get("ngay_bc"), x.get("to_chuc") or k.split("·")[-1], x))
    rows.sort(key=lambda r: r[0] or "", reverse=True)
    dong = [[cell(ddmm(d)), cell(org, mono=False, dam=True), cell(x.get("xep_hang") or x.get("chuan") or "", pill=True,
                                                                  mau={"MUA": "xanh", "BÁN": "do"}.get(x.get("chuan"), "vang")),
             cell(vn(x.get("muc_tieu"), 0)), cell(vn(x.get("upside"), 1, True, "%")), cell(cut(x.get("tieu_de"), 70), mono=False)]
            for d, org, x in rows[:8]]
    _, an = vc(tk, "analysis")
    vci = [[cell(ddmm(a.get("date"))), cell("Vietcap", mono=False, dam=True), cell(""), cell(""), cell(""),
            cell(cut(a.get("name"), 90), mono=False)] for a in (an or [])[:4] if isinstance(a, dict)]
    fc = (hv_row or {}).get("fa_catalyst") or {}
    nguon_fc = "hhp_vn100_valuation.fa_catalyst"
    if not (fc.get("rec") or fc.get("tp") or fc.get("latest")):  # khung rỗng/ngoài bảng HHP → fa_enrichment
        x = (((read_json(A.SYS_DIR / "fa_enrichment" / "fa_by_ticker.json") or {}).get("by_ticker") or {}).get(tk) or {})
        if x:
            fc = {"rec": x.get("rec"), "tp": x.get("tp"), "consensus": x.get("consensus"), "n_reports": x.get("n_reports"),
                  "net_revisions": x.get("net_revisions"), "latest": x.get("latest_catalyst") or {}}
            nguon_fc = "fa_enrichment/fa_by_ticker.json"
    lt = fc.get("latest") or {}
    khoi = []
    gia_now = num(hv_row.get("price_now")) if hv_row else None
    tp_fc = num(fc.get("tp"))
    tp_la = bool(tp_fc and gia_now and not (0.33 < tp_fc / gia_now < 3))  # TP corpus không ngày, lệch giá quá xa
    if fc and (fc.get("rec") or fc.get("tp")):
        khoi.append(o_so([tile("Đồng thuận broker (corpus)",
                               " · ".join(x for x in [fc.get("rec") or "", f"TP {vn(fc.get('tp'), 0)}" if fc.get("tp") else ""] if x),
                               jp(f"{fc.get('n_reports')} báo cáo" if fc.get("n_reports") else "", fc.get("consensus") or "",
                                  f"net revisions {vn(fc.get('net_revisions'), 0, True)}"
                                  if num(fc.get("net_revisions")) is not None else "", nguon_fc)
                               + (" · TP corpus không rõ ngày, lệch giá hiện tại quá xa: đừng đọc như upside" if tp_la else ""),
                               "xam" if tp_la else None, T3)], 1))
    if dong or vci:
        khoi.append(bang(["Ngày", "Tổ chức", "Xếp hạng", "TP", "Upside lúc ra", "Tiêu đề"], dong + vci,
                         "HSC/BBG: bản gốc Drive (SS-T3) · Vietcap: danh sách báo cáo phân tích. Upside tính theo giá ngày ra báo cáo.",
                         can_phai=[3, 4]))
    if lt:
        khoi.append(doan(f"Mới nhất trong corpus: {lt.get('source')} {ddmm(lt.get('date'))}, {lt.get('title')}", "xam"))
    moc = max((str(m)[:10] for m in [rows[0][0] if rows else None, (an or [{}])[0].get("date") if vci else None,
                                      lt.get("date")] if m), default=None)
    return o("research", "Research · HSC · BBG · Vietcap", khoi, 12, "Báo cáo phân tích", "hsc_research", "HSC Research",
             T3, trang_thai(moc, 30) if moc else ("cu" if khoi else "thieu"))


# ───────────────────────────── 12 · tin + sự kiện ─────────────────────────────

LOAI_TIN = {"mua": ("MUA", "xanh"), "ban": ("BÁN", "do"), "phat_hanh": ("PHÁT HÀNH", "vang"), "khac": ("KHÁC", "xam"),
            "dang_ky_mua": ("ĐK MUA", "xanh"), "dang_ky_ban": ("ĐK BÁN", "do"), "tang_von": ("TĂNG VỐN", "vang"),
            "chuyen_nhuong": ("CHUYỂN NHƯỢNG", "lam"), "cam_co": ("CẦM CỐ", "do"), "phap_ly": ("PHÁP LÝ", "do"),
            "thau_tom": ("THÂU TÓM", "tim"), "dau_gia": ("ĐẤU GIÁ", "lam")}


def o_tin(tk):
    ft = ((read_json(A.BRIDGE / "data" / "fft_tin.json") or {}).get("ma") or {}).get(tk) or {}
    ev_all = ft.get("su_kien") or []
    nguon_ev = "Lớp tin tự động fft_tin của Lăng kính (giao dịch nội bộ Vietcap không có KL/giá thực hiện)"
    if not ev_all:  # mã ngoài VN100 của fft_tin: kho tin v2 cùng lược đồ
        ev_all = [i for i in ((read_json(A.BRIDGE / "state" / "kho_fft_tin_v2.json") or {}).get("items") or [])
                  if isinstance(i, dict) and i.get("ma") == tk]
        nguon_ev = "Kho tin fft_tin v2 (state/kho_fft_tin_v2.json); dòng UNVERIFIED là tin báo, không dùng cho quyết định"
    ev = sorted(ev_all, key=lambda e: e.get("ngay") or "", reverse=True)[:6]
    _, news = vc(tk, "news")
    news = sorted([n for n in (news or []) if isinstance(n, dict)], key=lambda n: n.get("publicDate") or "", reverse=True)[:8]
    khoi = []
    if news:
        khoi.append(bang(["Ngày", "Tin (Vietcap)"], [[cell(ddmm(n.get("publicDate"))), cell(cut(n.get("newsTitle"), 110), mono=False)]
                                                     for n in news], "Vietcap news · tiêu đề, nguồn FiinGroup/CBTT"))
    if ev:
        khoi.append(bang(["Ngày", "Loại", "Sự kiện chủ thể", "Bậc"],
                         [[cell(ddmm(e.get("ngay"))), cell(LOAI_TIN.get(e.get("loai"), ((e.get("loai") or "").replace("_", " ").upper(), None))[0],
                                                          LOAI_TIN.get(e.get("loai"), ("", "xam"))[1], pill=True),
                           cell(cut(e.get("mo_ta"), 100), mono=False), cell(e.get("bac") or "")] for e in ev],
                         nguon_ev))
    _, e2 = vc(tk, "events-v2")
    e2 = sorted([x for x in (e2 or []) if isinstance(x, dict)], key=lambda x: x.get("publicDate") or "", reverse=True)[:5]
    MA_SK = {"DIV": ("CỔ TỨC", "xanh"), "ISS": ("PHÁT HÀNH", "vang"), "AIS": ("NIÊM YẾT BS", "vang")}
    if e2:
        khoi.append(bang(["Ngày", "Loại", "Sự kiện (Vietcap events)"],
                         [[cell(ddmm(x.get("publicDate"))), cell(MA_SK.get(x.get("eventCode"), (x.get("eventCode") or "", "xam"))[0],
                                                                 MA_SK.get(x.get("eventCode"), ("", "xam"))[1], pill=True),
                           cell(cut(x.get("eventTitleVi") or x.get("eventNameVi") or "", 100), mono=False)] for x in e2],
                         "Vietcap events-v2 (FACT-T2)"))
    newest = max((str(m)[:10] for m in [news[0].get("publicDate") if news else None, ev[0].get("ngay") if ev else None,
                                        e2[0].get("publicDate") if e2 else None] if m), default=None)
    return o("tin", "Tin + sự kiện", khoi, 6, "Tin + filing", "langkinh", "Lăng kính FFT", T2, trang_thai(newest, 30))


# ───────────────────────────── 13 · nhận định + trigger ─────────────────────────────

def o_nhan_dinh(tk, h):
    nd = h.get("nhan_dinh") or {}
    tp = h.get("trigger_phan_doan") or {}
    tr = h.get("trigger") or []
    khoi = []
    if nd.get("tieu_de"):
        khoi.append(chips([(T3, x.get("text")) for x in (nd.get("pha") or [])]))
        khoi.append(doan(f"{nd.get('tieu_de')}, {nd.get('eyebrow') or ''}", the=True,
                         tieu_de=f"Nhận định có tác giả · {nd.get('tac_gia') or ''} · {ddmm(nd.get('ngay'))}"))
    if tp.get("dong"):
        khoi.append(bang(["Phán đoán", "Điều kiện", "Hàm ý"],
                         [[cell(d.get("loai") or "", {"down": "do", "up": "xanh"}.get(d.get("mau")), dam=True, mono=False),
                           cell(d.get("dieu_kien") or "", mono=False), cell(d.get("ham_y") or "", mono=False)] for d in tp["dong"]],
                         f"{tp.get('nhan') or ''} · {tp.get('tuoi_ngay') or '?'} ngày"
                         + (" · ĐÓNG BĂNG: mốc giá viết theo dữ liệu lúc đó, không chấm lại khi CỔNG DỪNG" if tp.get("dong_bang") else "")))
    if tr:
        khoi.append(bang(["Trigger dữ liệu", "Trạng thái", "Hàm ý"],
                         [[cell(t.get("loai") or "", mono=False), cell(t.get("trang_thai_hien") or t.get("trang_thai") or "",
                                                                      "xanh" if (t.get("trang_thai_hien") or "") == "dat" else "xam", pill=True),
                           cell(t.get("ham_y") or "", mono=False)] for t in tr[:7]],
                         "Kiểm dữ liệu trung tính, chỉ mô tả điều kiện, không phải tín hiệu (EST)"))
    return o("nhan_dinh", "Phán đoán · trigger", khoi, 12, "Nhận định có tác giả", "langkinh", "Lăng kính FFT",
             f"{T3} {EST}", trang_thai(nd.get("ngay") or (tr[0].get("t") if tr else None), 21))


# ───────────────────────────── 14 · Chaebol Reflex ─────────────────────────────

def o_reflex(tk):
    """Ô Chaebol Reflex (tab msn_reflex) cho mọi mã thuộc registry knowledge_os/chaebol_reflex/nhom.json (32 nhóm);
    nội dung do chaebol_reflex_trang.o_aio dựng (vai trò trong nhóm, mẹ ÷ LT, tín hiệu, sự kiện, Hội đồng). Mã ngoài
    registry → None."""
    try:
        import chaebol_reflex_trang as CRT
        r = CRT.o_aio(tk)
    except Exception as exc:  # engine lỗi: ô báo thiếu, lưới vẫn dựng
        return o("reflex", "Chaebol Reflex", [], 12, "Casebook · độ trễ mẹ–con", "msn_reflex", "Chaebol Reflex",
                 ghi_chu=f"{CAN} engine Chaebol Reflex lỗi: {type(exc).__name__}: {exc}")
    if not r:
        return None
    return o("reflex", r.get("tieu_de") or "Chaebol Reflex", r.get("khoi") or [], r.get("cot") or 12,
             r.get("eyebrow") or "Casebook · độ trễ mẹ–con", r.get("tab") or "msn_reflex",
             r.get("tab_nhan") or "Chaebol Reflex", r.get("tier") or EST, trang_thai(r.get("trang_thai_ngay"), 14))


# ───────────────────────────── 15 · nguồn ─────────────────────────────

def o_nguon(tk, h, grid):
    rows = []
    for k, n in ((h.get("nguon") or {}).items()):
        t = n.get("du_lieu_toi") or n.get("lay_luc")
        rows.append([cell(f"vc_lk · {k}", mono=True), cell(ddmm(t)), cell(vn(tuoi_ngay(t), 0)),
                     cell(n.get("trang_thai") or "", "xanh" if n.get("trang_thai") == "ok" else "vang", pill=True),
                     cell(n.get("bac") or "")])
    thieu = [x["tieu_de"] for x in grid if x["trang_thai"] == "thieu"]
    cu = [x["tieu_de"] for x in grid if x["trang_thai"] == "cu"]
    can = [f"{c.get('khoa')}: {c.get('ly_do')}" for c in (h.get("can_data") or [])]
    return o("nguon", "Sổ nguồn của mã · tuổi dữ liệu", [
        canh_bao("Ô thiếu dữ liệu", thieu, "do"), canh_bao("Ô dữ liệu cũ", cu),
        bang(["Nguồn", "Dữ liệu tới", "Tuổi (ngày)", "Trạng thái", "Bậc"], rows[:14],
             f"Lăng kính lk_hoso/{tk}.json tạo {str(h.get('tao_luc') or '')[:16]}", can_phai=[2]) if rows else None,
        canh_bao("[CẦN DATA] lăng kính ghi nhận", can[:6], "xam")], 12, "Audit", "so_nguon", "Sổ nguồn", EST, "du")


# ───────────────────────────── lắp lưới ─────────────────────────────

def build(tk, ten, nganh, san, ro_list, nhom_chb, q, U=None):
    import all_in_one_mo_rong as MR  # noqa: PLC0415 (lượt 4: Chaebol chart, HHP đầy đủ, ERP, pha, Soros, Reflex)
    import all_in_one_solenh as SL  # noqa: PLC0415
    h = A.lk_hoso(tk) or {}
    warnings = []
    if not h:
        warnings.append(f"Chưa có lk_hoso/{tk}.json (Lăng kính), các ô FFT, cổ đông, nội bộ, phán đoán sẽ trống.")
    tv = A.toanvu("ma", tk)
    sau = A.toanvu("sau", tk)
    hv_row = (A.hhp_all().get("by_ticker") or {}).get(tk) or {}
    cb = MR.chaebol_data(tk)
    r_hhp, e_hhp = MR.hhp_data(tk)
    tvp, e_tv = MR.tv_page(tk)
    S = MR.an_toan
    o_chb = S("chaebol_chart", "Chart Infographic (Chaebol MAP)", MR.o_chaebol_chart, tk, cb, warnings=warnings)
    o_hhp = S("hhp_full", "Định giá HHP · đầy đủ", MR.o_hhp_full, tk, r_hhp, e_hhp, sau, warnings=warnings)
    pha = S("pe_pha_gia", "Các pha EPS × P/E", MR.o_pe_pha, tk, tvp, e_tv, warnings=warnings)
    grid = [
        o_ho_so(tk, ten, nganh, san, ro_list, nhom_chb, q, h),
        o_gia(tk, h, sau, san, o_chb["trang_thai"] == "thieu"), o_dinh_gia(tk, q, sau, o_hhp["trang_thai"] == "thieu"),
        o_chb, o_hhp,
        o_kqkd(tk), o_pe_tv(tk, tv),
        S("pe_erp", "EY so với lãi suất tiền gửi", MR.o_pe_erp, tk, tvp, e_tv, tv, warnings=warnings),
        *(pha if isinstance(pha, list) else [pha]),
        S("soros", "Soros mô phỏng", MR.o_soros, tk, r_hhp, cb, warnings=warnings),
        S("solenh", "Sổ lệnh · lái gom / lái xả", SL.o_solenh, tk, U or A.load_universe()[0], warnings=warnings),
        o_fft(tk, h), o_co_dong(tk, h),
        o_noi_bo(tk, h), o_tin(tk),
        o_deepfa(tk, h), o_hoi_dong(tk, sau),
        o_research(tk, hv_row),
        o_nhan_dinh(tk, h), o_reflex(tk), *MR.o_reflex_mo_rong(tk, warnings),
    ]
    grid = [g for g in grid if g]
    grid.append(o_nguon(tk, h, grid))
    return grid, warnings, h


def csv_for(tk, grid):
    """CSV của trang mã: mỗi ô số (o_so) một dòng."""
    rows = []
    for g in grid:
        for b in g["khoi"]:
            if b.get("kieu") == "o_so":
                for t in b["o"]:
                    rows.append([tk, g["tieu_de"], t["nhan"], t["gia_tri"], t["phu"], t["tier"]])
    return {"columns": ["ma", "o", "chi_so", "gia_tri", "ghi_chu", "bac"], "rows": rows}
