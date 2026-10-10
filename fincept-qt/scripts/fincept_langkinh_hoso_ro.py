#!/usr/bin/env python3
"""
Fincept Terminal — Hồ sơ Lăng Kính, view nhiều mã (layout "hoso"): matran5 [MÃ,MÃ,…|rổ] · sigma [rổ] · rrg [rổ].

Chỉ đọc data/lk_hoso/*.json, data/lk_thitruong.json, lk_nhan_dinh.json (muc._thi_truong), lk_cauhinh.json. Không
tính lại số — xếp, đếm, định dạng. Phần sống là số của builder; lớp phán đoán (keynote, hội đồng, hành động,
pre-mortem, rigor) là ảnh chụp có tác giả + ngày, không chấm lại. Bậc D3: ex-Vin3, tỷ trọng họ Vin và khoảng cách đáy
hoảng loạn tối đa EST. Stdlib only; Python 3.11 và 3.14.
"""
import os
import re

import fincept_langkinh_chuthe as CT
from fincept_langkinh_base import CO, P, cot, dm, dmy, dong, g, ngay, pp, pt, so
from fincept_langkinh_hoso_base import (CHI_SO, GOC_MAU, K_NHAN, RE_MA, SCOPES, VWAP_NHAN, Trang, chips_nguon, doc,
                                        dong_b, e, fmt, gk, gv, ha_bac, kpi, ky_s, mau_ma, moc_so, note_can, pd_nhan,
                                        pd_tuoi, sec, sigma_hong, sigma_numline, tron, viet, yeu)
from fincept_langkinh_hoso_base import KHONG_DUNG_SIGMA as KHONG_DUNG
TT_DH = {"no": "CHƯA", "near": "GẦN ĐỦ", "yes": "ĐỦ"}
D3 = "engine HHP (tổng hợp) — tối đa EST (D3)"
LOP = (("pha", "Pha hiện tại · phán đoán"), ("I", "I · Δ cổ đông"), ("II", "II · VWAP 6/12/24T"), ("III", "III · Chủ thể"),
       ("IV", "IV · Khối ngoại 63 phiên"), ("V", "V · FFT 4 tuần"), ("V8", "V · Ô 8 tuần · góc 2 năm"),
       ("sigma", "σ · Vietcap ratio-daily"), ("rrg", "RRG xấp xỉ vs VN-Index"))


def note_thieu_hs(thieu, ro):
    if not thieu:
        return None
    return {"type": "note", "pill": "CẦN DATA", "mau": "bear", "title": "%d mã %s chưa có hồ sơ" % (len(thieu), ro),
            "text": "[CẦN DATA] — chưa có hồ sơ Lăng Kính cho: %s.<br>Builder lk_hoso dựng hồ sơ khi cache Vietcap của "
                    "từng mã đủ các nguồn; trang này tự có số khi hồ sơ xuất hiện." % e(", ".join(thieu))}


LENH = "Ảnh chụp của tác giả, không phải lệnh — trạng thái CỔNG sống ở dải trên cùng"


def dau_pd(t, nd):
    """Dấu tác giả dùng chung: 'Phán đoán 21/09/2026 · Synthesis L3 · 2 ngày tuổi'."""
    return "%s · %s" % (pd_nhan(nd), pd_tuoi(nd, t.now))


def sec_pd(block, t, nd, key, eyebrow, title="", lenh=False):
    """Khối phán đoán có tác giả: đầu mục của Artifact + dòng tác giả/ngày/tuổi, ảnh chụp. lenh=True (bảng hành
    động/tổng hợp): thêm dòng CỔNG sống DỪNG — đọc như ảnh chụp, không như lệnh hôm nay (a1)."""
    tm = g(nd, "tieu_de_muc", key) or {}
    sub = "%s — ảnh chụp, không cập nhật theo dữ liệu sống" % dau_pd(t, nd)
    if lenh:
        sub = LENH + ". " + sub
    return sec(block, tm.get("eyebrow") or eyebrow, tm.get("tieu_de") or title or eyebrow,
               sub + (". " + tron(tm["dan"]) if tm.get("dan") else ""))


# ───────────────────────────── matran5 · thị trường ─────────────────────────────

def z_kpi(t, k, blk, khoa, them=""):
    x, z = blk.get("x"), blk.get("z")
    if gv(x) is None or gv(z) is None:
        return {"k": k, "v": None, "s": t.can(x if gv(x) is None else z, khoa)}
    s = "%s (%s) · μ %s · σ %s%s · tới %s%s" % (fmt(gv(x), "x"), x.get("b") or CO, so(gv(blk.get("mu")), 2),
                                                so(gv(blk.get("sd")), 2), " · %s phiên từ %s" % (
                                                    so(blk.get("n_phien"), 0), dmy(blk.get("tu")))
                                                if blk.get("n_phien") else "", dm(blk.get("t") or x.get("t")), them)
    return kpi(k, fmt(gv(z), "sigma"), s, yeu(x.get("b"), z.get("b")))


def b_thitruong(t, tt):
    vn = tt.get("vnindex") or {}
    ex = {k: ha_bac(v, "EST", D3) for k, v in (tt.get("exvin3") or {}).items()}
    dinh, ndinh = moc_so(vn.get("dinh"))
    day, nday = moc_so(vn.get("day"))
    s1 = "%s phiên · đỉnh 52T %s (%s) %s · đáy %s (%s) %s" % (
        t.s(vn.get("chg_1d"), "vnindex.chg_1d", True), t.s(dinh, "vnindex.dinh"), dm(ndinh),
        t.s(vn.get("tu_dinh"), "vnindex.tu_dinh", True, 1), t.s(day, "vnindex.day"), dm(nday),
        t.s(vn.get("tu_day"), "vnindex.tu_day", True, 1))
    it = [t.kpi_so("VN-Index · %s" % dm(g(vn, "px", "t")), vn.get("px"), "vnindex.px", s1),
          z_kpi(t, "P/E VN-Index · z", tt.get("pe_vni") or {}, "pe_vni"),
          z_kpi(t, "P/B VN-Index · z", tt.get("pb_vni") or {}, "pb_vni"),
          z_kpi(t, "P/E ex-Vin3 · z", ex, "exvin3", " · μ/σ của engine HHP")]
    tv = ha_bac(g(tt, "ty_trong_vin", "v"), "EST", D3)
    it.append(t.kpi_so("Tỷ trọng họ Vin", tv, "ty_trong_vin", "VIC + VHM + VRE / vốn hoá VN-Index · engine HHP"))
    dr = tt.get("do_rong_dinh_gia") or {}
    if dr.get("n_pe"):
        it.append(kpi("Độ rộng định giá · P/E · P/B", "%s/%s · %s/%s" % (pp(dr.get("re_pe")), pp(dr.get("n_pe")),
                                                                          pp(dr.get("re_pb")), pp(dr.get("n_pb"))),
                      "số mã z ≤ %sσ · mẫu %s mã có hồ sơ — KHÔNG phải toàn thị trường" % (
                          so(dr.get("nguong"), 1), pp(len(dr.get("mau") or []))), dr.get("b") or "EST", "amb"))
    else:
        it.append({"k": "Độ rộng định giá", "v": None, "s": t.can(dr, "do_rong_dinh_gia")})
    tk = tt.get("thanh_khoan") or {}
    if gv(tk.get("pct3y_tb4")) is None:
        it.append({"k": "Thanh khoản VN-Index", "v": None, "s": t.can(tk.get("pct3y_tb4"), "thanh_khoan.pct3y_tb4")})
    else:
        it.append(kpi("Thanh khoản VN-Index", "%s · %s" % (P(gv(tk["pct3y_tb4"])), P(gv(tk.get("pall_tb4")))),
                      "KL khớp TB 4 tuần tới %s · 3 năm · toàn dải (%s)" % (dm(g(tk, "pct3y_tb4", "t")),
                                                                         g(tk, "pall_tb4", "g") or CO),
                      yeu(g(tk, "pct3y_tb4", "b"), g(tk, "pall_tb4", "b"))))
    tit = "VN-Index %s · %s từ đỉnh 52 tuần · P/E %s (%s)" % (t.s(vn.get("px"), "vnindex.px"),
                                                             t.s(vn.get("tu_dinh"), "vnindex.tu_dinh", True, 1),
                                                             t.s(g(tt, "pe_vni", "x"), "pe_vni.x"),
                                                             t.s(g(tt, "pe_vni", "z"), "pe_vni.z"))
    return sec({"type": "kpis", "items": it}, "Bối cảnh · thị trường tới %s" % dmy(g(vn, "px", "t")), tit,
               "Vietcap gap-chart + ratio-daily (z: 10 năm winsorize P1/P99, EST) · ex-Vin3 và tỷ trọng họ Vin từ engine "
               "HHP (EST)")


def b_dongho(t, tt, nd):
    dh, items, trang = tt.get("dong_ho") or {}, [], []
    tg = dh.get("thoi_gian") or {}
    sl = tg.get("so_lieu") or {}
    dinh, ndinh = moc_so(sl.get("dinh"))
    day, nday = moc_so(sl.get("day"))
    tc = " · ".join("%s tháng (%s)" % (x.get("thang"), x.get("nam")) for x in sl.get("tham_chieu_thang") or [])
    dg = dh.get("dinh_gia") or {}
    sd = dg.get("so_lieu") or {}
    kc = [x for x in sd.get("khoang_cach") or [] if isinstance(x, dict)]
    dt = dh.get("dong_tien") or {}
    tk = g(dt, "so_lieu", "thanh_khoan_pct3y_tb4")
    spec = (("THỜI GIAN", tg, "%s từ đỉnh · %s từ đỉnh tới đáy" % (t.s(sl.get("thang_tu_dinh"), "dong_ho.thang_tu_dinh"),
                                                                   t.s(sl.get("thang_dinh_toi_day"), "dong_ho.dinh_toi_day")),
             ["Đỉnh 52T %s ngày %s, đáy %s ngày %s <tag b=\"FACT-T2\">FACT-T2</tag>." % (
                 t.s(dinh, "dong_ho.dinh"), dmy(ndinh), t.s(day, "dong_ho.day"), dmy(nday)),
              "Nhịp tham chiếu: %s. Luật: %s." % (e(tc or CO), e(sl.get("luat") or CO))]),
            ("ĐỊNH GIÁ", dg, "P/E ex-Vin3 %s" % t.s(ha_bac(sd.get("exvin3"), "EST", D3), "dong_ho.exvin3"),
             ["Cách các đáy hoảng loạn: %s <tag b=\"EST\">EST · engine HHP</tag>." % " · ".join(
                 "%s %s×%s: %s" % (e(x.get("ten")), so(x.get("pe"), 2),
                                   "" if x.get("ngay") and dmy(x["ngay"]) in str(x.get("ten")) else
                                   " (%s)" % (dmy(x.get("ngay")) if x.get("ngay") else "không ngày"),
                                   t.s(ha_bac(x.get("cach"), "EST", D3), "dong_ho.khoang_cach", True, 1)) for x in kc),
              "Luật: %s." % e(sd.get("luat") or CO)]),
            ("DÒNG TIỀN", dt, "Thanh khoản TB 4 tuần %s ba năm" % (P(gv(tk)) if gv(tk) is not None else
                                                                    t.can(tk, "dong_ho.thanh_khoan")),
             ["Luật: %s." % e(g(dt, "so_lieu", "luat") or CO)]))
    for ten, x, tieu, nd_ in spec:
        st = x.get("trang_thai")
        trang.append("%s %s" % (ten.lower(), TT_DH.get(st, "CẦN DATA").lower()))
        items.append({"pill": "%s · %s" % (ten, TT_DH.get(st, "CẦN DATA")), "pill_mau": st if st in TT_DH else "bad",
                      "tieu_de": tieu, "noi_dung": nd_})
    sub = "Luật chấm của builder (EST); không kết luận đáy khi CỔNG dừng (dải CỔNG trên cùng)."
    if nd and nd.get("dong_ho"):
        sub += " Bản tác giả %s: %s." % (dm(nd.get("ngay")), " · ".join(str(x.get("pill") or CO) for x in nd["dong_ho"]))
    return sec({"type": "cards", "variant": "clock", "items": items}, "Khung ba chiếc đồng hồ · luật EST",
               ("Đồng hồ " + " · ".join(trang)).capitalize(), sub)


# ───────────────────────────── matran5 · ma trận ─────────────────────────────

def chu_the_o(hs, nd):
    """Ô 'III · Chủ thể' (a1 high): nhãn tác giả có ngày đứng trước; nhãn máy luôn kèm NGÀY, cũ hơn nhận định thì ghi
    'chỉ đối chiếu' — không bao giờ trình bày nhãn máy cũ như số sống."""
    ct = g(hs, "chuthe", "nhan") or {}
    may = ("máy «%s» (%s · %s)" % (ct["v"], ct.get("b") or "EST", dmy(ct.get("t"))) if ct.get("v")
           else "máy [CẦN DATA]")
    if not nd:
        return "chủ thể " + may
    tg = nd.get("chu_the") or g(nd, "pha_ma_tran", "chu_the")
    tg = tg.get("text") if isinstance(tg, dict) else tg
    if not tg:
        m = re.search(r"chủ thể\s+([^·(;]+)", str(nd.get("cong_ma") or ""))
        tg = m.group(1).strip().lower() if m else None
    cu = ngay(ct.get("t")) and ngay(nd.get("ngay")) and ngay(ct["t"]) < ngay(nd["ngay"])
    s = "chủ thể «%s» (%s)" % (tg, pd_nhan(nd, ngan=True)) if tg else "chủ thể tác giả [CẦN DATA]"
    return s + " · " + may + (" — cũ hơn nhận định, chỉ đối chiếu" if cu else "")


def o_ma(t, ma, hs, nd):
    """Chín ô ma trận của một mã, từ hồ sơ sống (hàng pha là phán đoán có ngày)."""
    cd, vw, ng, f = hs.get("codong") or {}, hs.get("vwap") or {}, hs.get("ngoai") or {}, hs.get("fft") or {}
    o = {}
    pm = (nd or {}).get("pha_ma_tran") or {}
    pha = [p.get("text") for p in pm.get("pills") or [] if p.get("text")] + ([pm["text"]] if pm.get("text") else [])
    o["pha"] = ("%s%s\n(%s)" % (" · ".join(pha), " — " + pm["phu"] if pm.get("phu") else "", dau_pd(t, nd))
                if pha else "— chưa có nhận định; máy không gán pha")
    ok = [p for p in cd.get("cap") or [] if p.get("trang_thai") == "ok"]
    if ok:  # k chính = k_tho (spec §8, như Artifact); k quy cp hiện tại là dòng phụ
        p = ok[-1]
        kt, k = gv(p.get("k_tho")), gv(p.get("k"))
        nhan = p.get("nhan_k_tho") or p.get("nhan_k")
        o["I"] = "%s (%s→%s) · k %s nghìn → %s · giá %s%s" % (
            t.s(p.get("d_pct"), ma + ".codong.d_pct", True, 1), ky_s(p.get("tu")), ky_s(p.get("den")),
            so(kt / 1000, 1) if kt is not None else "[CẦN DATA]", K_NHAN.get(nhan, nhan or CO),
            t.s(p.get("dgia"), ma + ".codong.dgia", True, 1),
            "\n(k quy cp hiện tại %s nghìn)" % so(k / 1000, 1) if k is not None else "")
    else:
        o["I"] = "[CẦN DATA] — %s" % (g(cd, "pattern", "ly_do") or "không có cặp mốc quan sát")
        t.thieu.append((ma + ".codong", g(cd, "pattern", "ly_do") or "không có cặp mốc quan sát"))
    nh = VWAP_NHAN.get(vw.get("nhan"))
    o["II"] = "%s / %s / %s · %s" % (t.s(vw.get("kc6"), ma + ".vwap.kc6", True, 1), t.s(vw.get("kc12"), ma + ".vwap.kc12",
                                                                                     True, 1),
                                     t.s(vw.get("kc24"), ma + ".vwap.kc24", True, 1), nh[0] if nh else CO)
    lon = sorted([x for x in cd.get("lon") or [] if gv(x.get("pct")) is not None], key=lambda x: -gv(x["pct"]))[:2]
    o["III"] = "%s\n%s" % (" · ".join("%s %s" % (x.get("ten"), pt(gv(x["pct"]), 2)) for x in lon) or CO,
                           chu_the_o(hs, nd))
    day, nday = moc_so(ng.get("day"))
    o["IV"] = "%s → %s · ròng %s\nđáy %s (%s)" % (t.s(ng.get("dau_63"), ma + ".ngoai.dau_63"),
                                                t.s(ng.get("cuoi_63"), ma + ".ngoai.cuoi_63"),
                                                t.s(g(ng, "rong_63", "ty"), ma + ".ngoai.rong_63", True),
                                                t.s(day, ma + ".ngoai.day"), dm(nday))
    lech = gv(f.get("lech"))
    o["V"] = "%s (mức EST) · %s / %s (FACT-T2)%s · tuần %s" % (
        t.s(f.get("ma4"), ma + ".fft.ma4"), P(gv(f.get("pct3y"))), P(gv(f.get("pall"))),
        " · lệch %s" % so(lech, 0, True) if lech is not None and abs(lech) >= 25 else "", dm(g(f, "ma4", "t")))
    o8, bc = f.get("o8") or {}, f.get("bocung_2n") or {}
    o["V8"] = "ô 8T «%s» (FFT %s, giá %s) · 2N «%s»" % (o8.get("goc") or CO, t.s(o8.get("dfft"), ma + ".fft.o8", True, 1),
                                                        t.s(o8.get("dgia"), ma + ".fft.o8.dgia", True, 1), bc.get("goc") or CO)
    sg = hs.get("sigma") or {}
    o["sigma"] = "%s %s · %s" % (CHI_SO.get(sg.get("chi_so"), "σ"), t.s(sg.get("x"), ma + ".sigma.x"),
                                 t.s(sg.get("z"), ma + ".sigma.z"))
    rr = hs.get("rrg") or {}
    o["rrg"] = "%s (tuần %s)" % (rr.get("goc") or "[CẦN DATA]", dm(rr.get("t_cuoi")))
    return o


def b_matran(t, mas, hs, nds):
    o = {m: o_ma(t, m, hs[m], nds.get(m)) for m in mas}
    rows = [dong(dict({"lop": ten}, **{m: o[m].get(k, CO) for m in mas}), mau={"lop": "dim"}) for k, ten in LOP]
    blk = {"type": "table", "wrap": True, "row_link": False, "rows": rows,
           "cols": [cot("lop", "Lớp", "left")] + [cot(m, m, "left") for m in mas],
           "caption": "Hàng «Pha» và nhãn chủ thể tác giả ở hàng III là phán đoán có tác giả + ngày (ảnh chụp); nhãn chủ "
                      "thể máy luôn kèm ngày của nó; các ô còn lại là số sống của hồ sơ. Mức FFT tuyệt đối là EST, "
                      "percentile FACT-T2 — không so mức FFT giữa các mã."}
    return sec(blk, "Tổng hợp 5 pillar · v1.7", "Ma trận 5 pillar — %s trên cùng một khung" % " · ".join(mas),
               "Dựng từ hồ sơ sống, dữ liệu tới phiên %s." % dmy(g(hs[mas[0]], "phien_cuoi")) if mas else "")


def ruler_items(t, mas, hs, tt, mau_theo=None):
    """Thước σ chung: nhãn CHỈ là mã (Qt xử lý chồng nhãn; chỉ số P/E|P/B của từng mã ở sub/thẻ σ). Màu cố định theo
    mã (mau_ma) hoặc theo z (mau_theo); mã có dải σ hỏng (σ lớn so với μ) vẽ grey. VN-Index P/E, P/B cùng thước
    ratio-daily. Ex-Vin3 (engine HHP) KHÔNG ở đây — thước khác (Q2), xem ruler_hhp. → (items, mã dải hỏng)."""
    it, hong = [], []
    for m in mas:
        sg = hs[m].get("sigma") or {}
        z = gv(sg.get("z"))
        if z is None:
            t.can(sg.get("z"), m + ".sigma.z")
            continue
        if sigma_hong(sg):
            hong.append(m)
        it.append([m, round(z, 3), "grey" if m in hong else (mau_theo(z) if mau_theo else mau_ma(m))])
    for ten, k in (("VNI P/E", "pe_vni"), ("VNI P/B", "pb_vni")):
        z = gv(g(tt, k, "z"))
        if z is not None:
            it.append([ten, round(z, 3), "ink2"])
    return it, hong


def ruler_hhp(tt):
    """Ex-Vin3 P/E trên thước riêng của engine HHP (Q2: không trộn thước với ratio-daily)."""
    ex = {k: ha_bac(v, "EST", D3) for k, v in (tt.get("exvin3") or {}).items() if isinstance(v, dict)}
    z = gv(ex.get("z"))
    if z is None:
        return None
    return sec({"type": "numline", "mode": "ruler", "items": [["Ex-Vin3 P/E", round(z, 3), "ink2"]]},
               "Thước HHP · tham chiếu riêng", "Ex-Vin3 P/E %s theo μ/σ của engine HHP" % fmt(z, "sigma"),
               "Engine HHP (tổng hợp, EST) — thước khác với Vietcap ratio-daily, chỉ đặt cạnh để tham chiếu", "EST")


def b_ruler(t, it, hong, eyebrow, sub):
    """Tiêu đề đếm chỉ mã có dải σ dùng được; mã dải hỏng kể riêng (z của chúng không đọc như rẻ/đắt)."""
    ma_z = [(a, z) for a, z, _ in it if RE_MA.match(a) and a not in hong]
    duoi, tren = sum(1 for _, z in ma_z if z <= -1), sum(1 for _, z in ma_z if z >= 1)
    tit = ("Thước σ — %d/%d mã dưới −1σ · %d trên +1σ%s" % (duoi, len(ma_z), tren, " · %d mã dải không dùng được" %
                                                          len(hong) if hong else "")) if it else "[CẦN DATA]"
    if hong:
        sub += " · dải %s: %s (vẽ grey, không đếm)" % (KHONG_DUNG, ", ".join(hong))
    return sec({"type": "numline", "mode": "ruler", "items": it}, eyebrow, tit, sub, "EST")


def b_rrg(t, mas, hs, theo_goc):
    ser, dem = [], {}
    for m in mas:
        rr = hs[m].get("rrg") or {}
        if not rr.get("duoi"):
            t.can(rr, m + ".rrg")
            continue
        goc = rr.get("goc")
        dem[goc] = dem.get(goc, 0) + 1
        ser.append({"ma": m, "mau": GOC_MAU.get(goc, "grey") if theo_goc else mau_ma(m),
                    "duoi": rr["duoi"], "goc": goc})  # tuần cuối nằm ở t_cuoi của block, không lặp trong chú giải
    t_cuoi = max((g(hs[m], "rrg", "t_cuoi") or "" for m in mas), default="")
    n = next((g(hs[m], "rrg", "n") for m in mas if g(hs[m], "rrg", "n")), "rrg_engine")
    tit = " · ".join("%s %d" % (k, dem[k]) for k in ("Leading", "Improving", "Weakening", "Lagging") if dem.get(k))
    blk = {"type": "rrg", "series": ser, "t_cuoi": t_cuoi}
    return sec(blk, "Luân chuyển tương đối · tuần · so với VN-Index", tit or "[CẦN DATA] — không có đuôi RRG",
               "Xấp xỉ JdK (%s), đuôi 8 tuần tới %s — ước lượng EST, không phải Optuma.%s Bấm mã để mở hồ sơ." % (
                   n, dmy(t_cuoi), " Màu = góc hiện tại." if theo_goc else ""), "EST")


# ───────────────────────────── matran5 · lớp phán đoán thị trường ─────────────────────────────

def b_phan_doan(t, nd):
    if not nd:
        return []
    out = []
    kn = [k for k in nd.get("keynotes") or [] if isinstance(k, dict)]
    if kn:
        out.append(sec_pd({"type": "cards", "variant": "keynote", "items": [
            {"id": k.get("id"), "tieu_de": k.get("tieu_de"), "noi_dung": k.get("noi_dung")} for k in kn]},
            t, nd, "keynotes", "Keynotes"))
    hd = nd.get("hoi_dong") or {}
    cv = [x for x in hd.get("co_van") or [] if isinstance(x, dict)]
    if cv:
        out.append(sec_pd({"type": "cards", "variant": "box", "items": [
            {"pill": x.get("vung") or "", "pill_mau": "bad" if "Kill" in str(x.get("vung")) else "info",
             "tieu_de": "%s · %s" % (x.get("ten") or CO, x.get("vai") or CO),
             "noi_dung": list(x.get("paras") or []) + ([x["ket_qua"]] if x.get("ket_qua") else [])} for x in cv]},
            t, nd, "hoidong", "Hội đồng cố vấn"))
    th = [x for x in hd.get("tong_hop") or [] if isinstance(x, dict)]
    if th:
        def tp(x, k):
            v = x.get(k)
            return "%s (%s)" % (v.get("text"), v.get("phu")) if isinstance(v, dict) and v.get("phu") else (
                v.get("text") if isinstance(v, dict) else v)
        # 4 cột (vừa 880px): điểm chấm gộp một ô, tỷ trọng gộp một ô mang bậc EST (D3 — sổ nội bộ, lúc viết).
        rows = [dong({"ma": x.get("ma"),
                      "cham": "Conviction %s\nDeath 18T %s · bất đối xứng %s" % (
                          tp(x, "conviction_6d") or CO, x.get("death_18t") or CO, tp(x, "asymmetry") or CO),
                      "tt": "hiện %s · trần Kelly %s (EST, lúc viết)" % (x.get("hien") or CO, x.get("tran_kelly") or CO),
                      "kl": "%s — %s" % (g(x, "ket_luan", "pill"), g(x, "ket_luan", "text"))}) for x in th]
        out.append(sec({"type": "table", "wrap": True, "row_link": False, "rows": rows,
                        "caption": tron(hd.get("ghi_chu")),
                        "cols": [cot("ma", "Mã", "left"), cot("cham", "Chấm điểm", "left"),
                                 cot("tt", "Tỷ trọng", "left"), cot("kl", "Kết luận của tác giả", "left")]},
                       "Hội đồng · tổng hợp theo mã", "Tổng hợp theo mã — %s" % dau_pd(t, nd),
                       LENH + ". Tỷ trọng là số trong sổ nội bộ lúc viết (EST)."))
    hdg = [x for x in nd.get("hanh_dong") or [] if isinstance(x, dict)]
    if hdg:
        out.append(sec_pd({"type": "table", "wrap": True, "row_link": False, "rows": [
            dong({k: tron(x.get(k)) for k in ("ma", "hanh_dong", "khi_nao", "stop_phu_dinh", "theo_doi")}) for x in hdg],
            "cols": [cot("ma", "Mã", "left"), cot("hanh_dong", "Việc", "left"), cot("khi_nao", "Khi nào", "left"),
                     cot("stop_phu_dinh", "Stop / phủ định", "left"), cot("theo_doi", "Theo dõi", "left")]},
            t, nd, "hanhdong", "Bảng hành động của tác giả", lenh=True))
    pm = [x for x in nd.get("pre_mortem") or [] if isinstance(x, dict)]
    if pm:
        out.append(sec_pd({"type": "cards", "variant": "premortem", "items": [
            {"id": x.get("id"), "tieu_de": x.get("tieu_de"), "noi_dung": x.get("noi_dung")} for x in pm]},
            t, nd, "premortem", "Pre-mortem"))
    rg = nd.get("rigor") or {}
    if rg.get("hang"):
        out.append(sec_pd({"type": "table", "wrap": True, "row_link": False, "caption": "Tổng %s" % (rg.get("tong") or CO),
                           "rows": [dong({k: tron(x.get(k)) for k in ("chieu", "diem", "ly_do")}) for x in rg["hang"]],
                           "cols": [cot("chieu", "Chiều", "left"), cot("diem", "Điểm", "right"),
                                    cot("ly_do", "Lý do", "left")]}, t, nd, "rigor", "Tự chấm rigor 6D"))
    if rg.get("backlog"):
        out.append({"type": "table", "title": "Backlog của tác giả — %s" % dau_pd(t, nd), "wrap": True, "row_link": False,
                    "rows": [dong({k: tron(x.get(k)) for k in ("viec", "uu_tien", "chu")}) for x in rg["backlog"]],
                    "cols": [cot("viec", "Việc", "left"), cot("uu_tien", "Ưu tiên", "left"), cot("chu", "Chủ", "left")]})
    return out


def v_matran5(c):
    t = Trang(c)
    tt = doc(os.path.join(c.dir, "lk_thitruong.json"))
    arg = (c.scope or "").strip()
    if arg and arg not in SCOPES:
        mas = [x for x in re.split(r"[,;\s]+", arg) if RE_MA.match(x)][:6]
    else:
        mas = [str(m) for m in (t.cfg.get("matran5_mac_dinh") or g(tt, "matran5", "ma") or ["FPT", "VCB", "MSN"])
               if RE_MA.match(str(m))]
    hs = {m: t.ho_so(m) for m in mas}
    co, thieu = [m for m in mas if hs[m]], [m for m in mas if not hs[m]]
    c.scope, c.members = " · ".join(mas), mas
    nd = t.nd("_thi_truong", {"nhan_dinh": (tt or {}).get("nhan_dinh")})
    blocks = []
    if tt:
        blocks.append(b_thitruong(t, tt))
        if nd and g(nd, "cong", "dong"):
            blocks.append({"type": "note", "pill": pd_nhan(nd, ngan=True), "mau": "dim",
                           "title": "Dòng CỔNG của tác giả — %s — chỉ đối chiếu; CỔNG sống ở dải trên" % dau_pd(t, nd),
                           "text": "%s<br>%s" % (g(nd, "cong", "dong_lite") or e(g(nd, "cong", "dong")),
                                                 g(nd, "cong", "noi_dung") or "")})
        blocks.append(b_dongho(t, tt, nd))
    else:
        blocks.append({"type": "note", "pill": "CẦN DATA", "mau": "bear", "title": "Chưa có lk_thitruong.json",
                       "text": "[CẦN DATA] — chưa có tệp thị trường của builder lk_hoso (dựng cùng lượt hồ sơ)."})
    pd = b_phan_doan(t, nd)
    blocks += pd[:1]  # keynotes đứng trước ma trận như Artifact
    if co:
        nds = {m: t.nd(m, hs[m]) for m in co}
        it, hong = ruler_items(t, co, hs, tt or {})
        blocks += [b_matran(t, co, hs, nds),
                   b_ruler(t, it, hong, "Vùng giá σ · Vietcap ratio-daily",
                           "z = (x − μ)/σ trên chuỗi 10 năm winsorize P1/P99 (EST) · %s" % " · ".join(
                               "%s %s" % (m, CHI_SO.get(g(hs[m], "sigma", "chi_so"), "σ")) for m in co)),
                   ruler_hhp(tt or {}), b_rrg(t, co, hs, False)]
    blocks += pd[1:]
    blocks += [note_thieu_hs(thieu, "trong ma trận"),
               sec({"type": "chips", "items": chips_nguon((tt or {}).get("nguon"))}, "Nguồn", "Nguồn của trang thị trường",
                   "Màu tag = bậc bằng chứng · 'dữ liệu tới' = ngày dữ liệu của chính nguồn") if tt else None,
               note_can(t, [(x.get("khoa"), viet(x.get("ly_do"))) for x in (tt or {}).get("can_data") or []
                            if isinstance(x, dict)])]
    rows = []
    tbl = next((b for b in blocks if b and b.get("type") == "table" and b.get("eyebrow") == "Tổng hợp 5 pillar · v1.7"), None)
    if tbl:
        rows = [{"%02d %s" % (i + 1, cc["label"]): r.get(cc["key"], "") for i, cc in enumerate(tbl["cols"])}
                for r in tbl["rows"]]
    cong = CT.cong_ro(c)
    cong["dong"] = dong_b(cong.get("dong"))
    return {"title": "Ma trận 5 pillar — %s" % " · ".join(mas), "blocks": [b for b in blocks if b],
            "sub": "Lăng Kính cấu trúc cổ đông · hồ sơ Vietcap IQ · thị trường tới %s" % dmy(g(tt, "vnindex", "px", "t")),
            "data": rows or [{"01 Mục": "Ma trận 5 pillar", "02 Giá trị": "[CẦN DATA] — chưa có hồ sơ"}],
            "tickers": co, "cong": cong,
            "payload": {"layout": "hoso", "as_of": "phiên %s" % dmy(g(tt, "vnindex", "px", "t")),
                        "tuoi": "thị trường dựng %s" % dm((tt or {}).get("tao_luc")) if tt else "chưa có lk_thitruong"}}


# ───────────────────────────── sigma · rrg theo rổ ─────────────────────────────

def _ro(c):
    t = Trang(c)
    scope = c.scope if c.scope in SCOPES else "VN30"
    mas, thieu = t.ro(scope)
    hs = {m: t.ho_so(m) for m in mas}
    mas = [m for m in mas if hs[m]]
    return t, scope, mas, thieu, hs


def v_sigma(c):
    t, scope, mas, thieu, hs = _ro(c)
    tt = doc(os.path.join(c.dir, "lk_thitruong.json")) or {}
    xep = sorted([m for m in mas if gv(g(hs[m], "sigma", "z")) is not None], key=lambda m: gv(hs[m]["sigma"]["z"]))
    it, hong = ruler_items(t, xep, hs, tt, lambda z: "up" if z <= -1 else ("down" if z >= 1 else "blue"))
    doi = [m for m in xep if isinstance(g(hs[m], "sigma", "doi_chi_so"), dict)]
    ruler = b_ruler(t, it, hong, "Vùng giá σ · Vietcap ratio-daily · %s" % scope,
                    "Ngân hàng + MSN dùng P/B, còn lại P/E (lk_cauhinh.sigma)%s · z trên chuỗi 10 năm winsorize P1/P99 "
                    "(EST)" % ("; %d mã P/E μ − σ ≤ 0 đổi sang P/B (%s)" % (len(doi), ", ".join(doi)) if doi else ""))
    nl = [sigma_numline(t, hs[m], m) for m in xep]
    hang = [{"type": "row", "items": nl[i:i + 2]} for i in range(0, len(nl), 2)]
    rows = []
    for m in xep:
        sg, dai = hs[m]["sigma"], hs[m]["sigma"].get("dai") or {}
        rows.append({"01 Mã": m, "02 Chỉ số": CHI_SO.get(sg.get("chi_so"), CO), "03 Tỷ số": fmt(gv(sg.get("x")) or 0, "x"),
                     "04 z": fmt(gv(sg["z"]), "sigma"), "05 μ": so(gv(sg.get("mu")), 2), "06 σ": so(gv(sg.get("sd")), 2),
                     "07 Giá": gk(gv(sg.get("px"))), **{"%02d %s" % (8 + i, ten): gk(gv(dai.get(k))) for i, (k, ten) in
                                                       enumerate((("c2", "−2σ"), ("c1", "−1σ"), ("f", "μ giá"),
                                                                  ("r1", "+1σ"), ("r2", "+2σ")))},
                     "13 Bậc": "x FACT-T2 · dải EST"})
    for m in mas:
        if m not in xep:
            t.can(g(hs[m], "sigma", "z"), m + ".sigma.z")
    blocks = [ruler, ruler_hhp(tt)] + hang + [note_thieu_hs(thieu, scope), note_can(t)]
    cong = CT.cong_ro(c)
    cong["dong"] = dong_b(cong.get("dong"))
    return {"title": "Vùng giá σ — %s" % scope, "sub": "%d mã có hồ sơ · xếp theo z tăng dần" % len(xep),
            "blocks": [b for b in blocks if b], "tickers": mas, "cong": cong,
            "data": rows or [{"01 Mục": "Vùng giá σ %s" % scope, "02 Giá trị": "[CẦN DATA] — chưa có hồ sơ"}],
            "payload": {"layout": "hoso", "as_of": "phiên %s" % dmy(max((g(hs[m], "sigma", "den") or "" for m in mas),
                                                                     default="")), "tuoi": "%d mã" % len(mas)}}


def v_rrg(c):
    t, scope, mas, thieu, hs = _ro(c)
    b = b_rrg(t, mas, hs, True)
    rows = []
    for m in mas:
        rr = hs[m].get("rrg") or {}
        d = (rr.get("duoi") or [[None, None]])[-1]
        rows.append(dong({"ma": m, "goc": rr.get("goc") or "[CẦN DATA]", "x": so(d[0], 2), "y": so(d[1], 2),
                          "t": dmy(rr.get("t_cuoi"))}, mau={"goc": {"Leading": "bull", "Lagging": "bear",
                                                                   "Weakening": "warn", "Improving": "info"}.get(rr.get("goc"), "dim")},
                         link=m))
    tbl = {"type": "table", "title": "Góc RRG theo mã — bấm để mở hồ sơ", "row_link": True, "rows": rows, "b": "EST",
           "sub": "RS-Ratio · RS-Momentum điểm cuối của đuôi (EST)",
           "cols": [cot("ma", "Mã", "left"), cot("goc", "Góc", "left"), cot("x", "RS-Ratio"), cot("y", "RS-Momentum"),
                    cot("t", "Tuần cuối", "left")]}
    cong = CT.cong_ro(c)
    cong["dong"] = dong_b(cong.get("dong"))
    return {"title": "RRG vs VN-Index — %s" % scope, "sub": "%d mã có hồ sơ" % len(mas),
            "blocks": [x for x in (b, tbl, note_thieu_hs(thieu, scope), note_can(t)) if x], "tickers": mas, "cong": cong,
            "data": [{"01 Mã": r["ma"], "02 Góc": r["goc"], "03 RS-Ratio": r["x"], "04 RS-Momentum": r["y"],
                      "05 Tuần": r["t"]} for r in rows] or [{"01 Mục": "RRG %s" % scope, "02 Giá trị": "[CẦN DATA]"}],
            "payload": {"layout": "hoso", "as_of": "tuần %s" % dmy(b.get("t_cuoi")), "tuoi": "%d mã" % len(mas)}}
