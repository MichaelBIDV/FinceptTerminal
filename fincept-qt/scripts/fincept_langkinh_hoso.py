#!/usr/bin/env python3
"""
Fincept Terminal — Hồ sơ Lăng Kính tầm Artifact (LK_HOSO_SPEC §5–6 · BLOCK CONTRACT v2) cho LangKinhPanel.

Chỉ ĐỌC: data/lk_hoso/<MÃ>.json, data/lk_hoso/_index.json, data/lk_thitruong.json (builder lk_hoso.py dựng sẵn) và
lk_nhan_dinh.json, lk_cauhinh.json ở thư mục bridge (cha của data/). Không gọi mạng, không tính lại công thức: mọi con số
in từ nguyên tử So của builder (định dạng Việt 1.234,5 · dấu trừ U+2212); thiếu → "[CẦN DATA] — g" + mục CẦN DATA.
View: hoso <MÃ> · matran5 [MÃ,MÃ,…|rổ] · sigma [rổ] · rrg [rổ]; payload `layout: "hoso"`. Mục «Mẫu hình NTH» (thấu kính
giá SS-T3, fincept_langkinh_mauhinh.khoi_ho_so) đứng SAU năm pillar và VWAP — proxy giá/KL xếp sau Δ cổ đông (HR #16).
Luật (quyết định D2/D3 của phiên chính 23/09):
- Lớp phán đoán chỉ hiện khi có tác giả + ngày, là ảnh chụp "Phán đoán 21/09/2026 · Synthesis L3", không chấm sống.
- Dòng tự động = kiểm dữ liệu trung tính: nhãn tả điều kiện, hàm ý tả nghĩa với lăng kính, không lời mua/bán, không
  tỷ trọng; tên pattern ngoài 30 mã Toàn Vũ mang hậu tố '?'; CỔNG đang dừng thì 'đạt' kèm "không kết luận".
- Bậc tối đa EST cho nav, P/E ex-Vin3 và khoảng cách đáy hoảng loạn (engine HHP), số cổ phần mô hình hoá.
- Polish 23/09: đầu mã chỉ số sống (giá mang bậc), chữ tác giả sang dải riêng có tác giả + ngày + tuổi; k hiển thị = k_tho
  (spec §8), k quy cp hiện tại là dòng phụ; mốc cổ đông là block 'cotmoc'; sở hữu ngoại 63 phiên = 64 điểm từ dau_63.
Stdlib only; Python 3.11 và 3.14.
"""
import fincept_langkinh_chuthe as CT
from fincept_langkinh_base import CO, P, dm, dmy, g, ngay, pp, pt, so, so_num
from fincept_langkinh_hoso_base import (CHI_SO, GOI_Y, K_NHAN, KIEU_MOC, N_PHIEN_NN, N_TUAN_3Y, RE_MA, SCOPES,  # noqa: F401
                                        TAG_MAU, VWAP_NHAN, Trang, b_trigger, chips_nguon, cp_, doi_nhan, dong_b, e, gk, gv,
                                        hau_to, kpi, ky_ms, ky_s, moc_so, ms_s, nav_nhan, nav_so, note_can, pd_nhan, pd_tuoi,
                                        rows_kpi, sec, sigma_cach, sigma_numline, tag, ten_pattern, trong_tv, tuoi_tep,
                                        viet, yeu)
from fincept_langkinh_hoso_ro import v_matran5, v_rrg, v_sigma  # noqa: F401 — 4 view hồ sơ vào qua tệp này
try:  # Mẫu hình NTH — tệp mới; bundle chưa có thì hồ sơ vẫn chạy, chỉ thiếu mục NTH (và view mauhinh báo lỗi rõ)
    import fincept_langkinh_mauhinh as MH
except ImportError:
    MH = None

# ───────────────────────────── hoso · đầu mã + KPI ─────────────────────────────

def tieu_de_may(hs):
    """Một dòng trạng thái thuần số — không từ đánh giá."""
    gia, fft = hs.get("gia") or {}, hs.get("fft") or {}
    phan = []
    if gv(gia.get("tu_dinh_52w")) is not None:
        phan.append("%s từ đỉnh 52 tuần" % pt(gv(gia["tu_dinh_52w"]), 1, True))
    if gv(fft.get("pct3y")) is not None:
        phan.append("FFT 4 tuần %s ba năm · %s toàn dải" % (P(gv(fft["pct3y"])), P(gv(fft.get("pall")))))
    vw = VWAP_NHAN.get(g(hs, "vwap", "nhan"))
    if vw:
        phan.append("giá " + vw[2])
    return "; ".join(phan) or "[CẦN DATA] — hồ sơ chưa có giá và FFT"


def pd_dau(nd, now):
    """Dấu tác giả dùng chung: 'Phán đoán 21/09/2026 · Synthesis L3 · 2 ngày tuổi' (a1: tác giả + ngày + tuổi)."""
    return "%s · %s" % (pd_nhan(nd), pd_tuoi(nd, now))


def chu_the_may(hs, nd):
    """Nhãn chủ thể máy (fft_langkinh) kèm ngày; cũ hơn nhận định tác giả → ghi rõ 'chỉ đối chiếu'."""
    ct = g(hs, "chuthe", "nhan") or {}
    if not ct.get("v"):
        return "chủ thể [CẦN DATA]"
    s = "chủ thể máy «%s» (%s · %s)" % (ct["v"], ct.get("b") or "EST", dmy(ct.get("t")))
    if nd and ngay(ct.get("t")) and ngay(nd.get("ngay")) and ngay(ct["t"]) < ngay(nd["ngay"]):
        s += " — cũ hơn nhận định %s, chỉ đối chiếu" % dm(nd["ngay"])
    return s


def b_tkhead(t, hs, nd):
    """Đầu mã CHỈ số sống (a1): giá kèm bậc, pill máy; mọi chữ tác giả sang dải riêng b_tac_gia ngay dưới."""
    gia, ng = hs.get("gia") or {}, hs.get("ngoai") or {}
    tv, pills = trong_tv(hs), []
    pat = str(g(hs, "codong", "pattern", "nhan") or "")
    if pat.rstrip("?") in ("A", "B", "C", "D"):
        pills.append({"text": ten_pattern(pat, tv), "mau": "grey"})
    vw = VWAP_NHAN.get(g(hs, "vwap", "nhan"))
    if vw:
        pills.append({"text": vw[0], "mau": vw[1]})
    tran, hien, room = gv(ng.get("tran")), gv(ng.get("hien")), gv(ng.get("room"))
    if tran is not None and tran > 0 and hien is not None and room is not None and tran - hien < 2:
        pills.append({"text": "Room ngoại còn %s" % cp_(room), "mau": "down" if tran - hien < 0.5 else "amber"})
    cong = chu_the_may(hs, nd)  # CỔNG sống chỉ ở dải CỔNG trên cùng (một lần mỗi trang — nth_a3_design low #9)
    px = gia.get("px")
    return {"type": "tkhead", "ma": hs.get("ma"), "eyebrow": " · ".join(x for x in (hs.get("ten"), hs.get("nganh"),
                                                                                    nav_nhan(hs)) if x),
            "tieu_de": tieu_de_may(hs), "px": t.s(px, "gia.px") if gv(px) is None else gk(gv(px)),
            "b": g(gia, "px", "b") or ("FACT-T2" if gv(px) is not None else ""),
            "chg": pt(gv(gia.get("chg_1d")), 2, True), "pills": pills, "cong_ma": cong}


def b_tac_gia(t, hs, nd):
    """Dải phán đoán tác giả (ảnh chụp) ngay dưới đầu mã: tiêu đề, pill pha và dòng CỔNG mã của tác giả — mở đầu
    bằng tác giả + ngày + tuổi; CỔNG sống ghi kèm để không đọc dòng tác giả như trạng thái hiện tại."""
    if not nd:
        return None
    dau = pd_dau(nd, t.now)
    pha = " · ".join(e(p["text"]) for p in nd.get("pha") or [] if isinstance(p, dict) and p.get("text"))
    dong_ = []
    if nd.get("tieu_de"):
        dong_.append("<b>%s</b>" % e(nd["tieu_de"]))
    if pha:
        dong_.append("Pha theo tác giả: %s" % pha)
    if nd.get("cong_ma"):
        dong_.append("%s — %s" % (e(dau), e(nd["cong_ma"])))
    dong_.append("Các dòng trên là ảnh chụp lúc viết, không chấm lại theo số hôm nay — trạng thái sống ở dải CỔNG "
                 "trên cùng.")
    return {"type": "note", "pill": pd_nhan(nd, ngan=True), "mau": "dim", "title": dau + " — ảnh chụp",
            "text": "<br>".join(dong_)}


def b_kpis(t, hs):
    """Dải KPI: mỗi ô MỘT dòng phụ ngắn (a2); chi tiết (giá bảng, thô, tuần dở dang, room/trần) ở tooltip `tip`."""
    gia, fft, ng = hs.get("gia") or {}, hs.get("fft") or {}, hs.get("ngoai") or {}
    tip1 = ["Giá điều chỉnh Vietcap, phiên %s" % dmy(g(gia, "px", "t"))]
    if gv(gia.get("bang")) is not None:
        tip1.append("Giá bảng sơ bộ %s: %s (KHO vnstock, tách khỏi chuỗi Vietcap)" % (dm(g(gia, "bang", "t")),
                                                                                    gk(gv(gia["bang"]))))
    it = [dict(t.kpi_so("Giá · phiên %s" % dm(g(gia, "px", "t")), gia.get("px"), "gia.px",
                        "YTD %s" % t.s(gia.get("ytd"), "gia.ytd", True, 1)), tip="\n".join(tip1))]
    dinh, nd_ = moc_so(gia.get("dinh_52w"))
    day, nday = moc_so(gia.get("day_52w"))
    dls, ndls = moc_so(gia.get("dinh_ls"))
    tip2 = ["Đáy 52 tuần %s (%s)" % (t.s(day, "gia.day_52w"), dmy(nday))]
    if gv(dls) is not None and ndls != nd_:
        tip2.append("Từ đỉnh lịch sử %s (%s): %s" % (gk(gv(dls)), dmy(ndls), pt(gv(gia.get("tu_dinh_ls")), 1, True)))
    tdv = gv(gia.get("tu_dinh_52w"))
    it.append(dict(t.kpi_so("Từ đỉnh 52 tuần", gia.get("tu_dinh_52w"), "gia.tu_dinh_52w",
                            "đỉnh %s (%s)" % (gk(gv(dinh)), dm(nd_)), True, 1,
                            "bad" if tdv is not None and tdv < 0 else ""), tip="\n".join(tip2)))
    dd = fft.get("tuan_do_dang") or hs.get("tuan_do_dang") or {}
    tip3 = ["Mức FFT tuyệt đối là EST (ff ảnh chụp coi là hằng)", "Thô (mẫu số cp tuần đóng): %s" %
            t.s(fft.get("ma4_tho"), "fft.ma4_tho")]
    if gv(dd.get("fw")) is not None:
        tip3.append("Tuần %s dở dang %s (%s phiên) — ngoài thống kê" % (dm(dd.get("week_end")), pt(gv(dd["fw"]), 3),
                                                                        pp(dd.get("days"))))
    it.append(dict(t.kpi_so("FFT 4 tuần", fft.get("ma4"), "fft.ma4", "tuần đóng %s" % dm(g(fft, "ma4", "t"))),
                   tip="\n".join(tip3)))
    p3, pa, lech = gv(fft.get("pct3y")), gv(fft.get("pall")), gv(fft.get("lech"))
    if p3 is None:
        it.append({"k": "Percentile 3Y · toàn dải", "v": None, "s": t.can(fft.get("pct3y"), "fft.pct3y")})
    else:
        s4 = "lệch %s điểm%s" % (so(lech, 0, True), " — nêu cả hai cửa sổ" if lech is not None and abs(lech) >= 25 else "")
        it.append(dict(kpi("Percentile 3Y · toàn dải", "%s · %s" % (P(p3), P(pa)), s4, yeu(g(fft, "pct3y", "b"),
                           g(fft, "pall", "b")), "amb" if lech is not None and abs(lech) >= 25 else ""),
                       tip="Thô: %s · %s" % (P(gv(fft.get("pct3y_tho"))), P(gv(fft.get("pall_tho"))))))
    x10, x90 = fft.get("x_p10"), fft.get("x_p90")
    if gv(x10) is None or gv(x90) is None:
        it.append({"k": "× P10 · × P90 (3Y)", "v": None, "s": t.can(x10 if gv(x10) is None else x90, "fft.x_p10")})
    else:
        it.append(dict(kpi("× P10 · × P90 (3Y)", "%s · %s" % (so(gv(x10), 2), so(gv(x90), 2)),
                           "P10 %s · P90 %s" % (pt(gv(fft.get("p10_3y")), 3), pt(gv(fft.get("p90_3y")), 3)),
                           yeu(x10.get("b"), x90.get("b"))),
                       tip="%s trong cửa sổ 3 năm" % t.s(fft.get("n_tuan_3y"), "fft.n_tuan_3y")))
    day_nn, nday_nn = moc_so(ng.get("day"))
    tran = gv(ng.get("tran"))
    tip6 = ["Đáy %d phiên %s (%s)" % (N_PHIEN_NN, t.s(day_nn, "ngoai.day"), dmy(nday_nn)),
            "Số cp nước ngoài của vendor trễ khoảng 1–2 phiên so với giao dịch — so sánh bằng số cp"]
    if tran is not None and tran > 0:
        tip6.append("Room còn %s · trần %s" % (t.s(ng.get("room"), "ngoai.room"), t.s(ng.get("tran"), "ngoai.tran", nd=0)))
    it.append(dict(t.kpi_so("Sở hữu ngoại", ng.get("hien"), "ngoai.hien", "phiên %s · đáy 63 phiên %s" % (
        dm(g(ng, "hien", "t")), t.s(day_nn, "ngoai.day"))), tip="\n".join(tip6)))
    return {"type": "kpis", "items": it}


# ───────────────────────────── hoso · biểu đồ ─────────────────────────────

def cat(ch, k, n0, n):
    arr = ch.get(k) if isinstance(ch.get(k), list) else []
    return [so_num(arr[i]) if i < len(arr) else None for i in range(n0, n)]


def chuoi_d(pd):
    """Tuần fw ≥ 2× nền liền nhau (cách ≤ 7 ngày) gộp thành một đợt — một nhãn cho cả đợt thay vì mỗi tuần một chip."""
    runs = []
    for x in sorted((x for x in pd if ngay(x.get("tuan"))), key=lambda x: x["tuan"]):
        if runs and (ngay(x["tuan"]) - ngay(runs[-1][-1]["tuan"])).days <= 7:
            runs[-1].append(x)
        else:
            runs.append([x])
    return runs


def ca_nhan(ev):
    s, tl = str(ev.get("su_kien") or ""), so_num(ev.get("ty_le"))
    loai = "Cổ tức CP" if "Cổ tức" in s else ("Thưởng CP" if "thưởng" in s.lower() else "Phát hành")
    return "%s %s" % (loai, pt(tl * 100, 0 if tl and (tl * 100).is_integer() else 1)) if tl else loai


def b_fft(t, hs):
    fft = hs.get("fft") or {}
    ch = fft.get("chuoi") or {}
    ts = [x for x in ch.get("t") or [] if ngay(x)]
    if not ts:
        return {"type": "note", "mau": "bear", "pill": "CẦN DATA", "title": "FFT 4 tuần",
                "text": e(t.can(fft.get("ma4"), "fft.chuoi"))}
    n = len(ts)
    n0 = max(0, n - N_TUAN_3Y)
    x, x0, x1 = ts[n0:], ts[n0], ts[-1]
    f, p90 = cat(ch, "f", n0, n), cat(ch, "p90", n0, n)
    ser = [{"name": "Giá điều chỉnh", "style": "thin", "axis": "right", "mau": "ink2", "y": cat(ch, "c", n0, n)},
           {"name": "P10 3Y", "style": "dash", "mau": "up", "y": cat(ch, "p10", n0, n)},
           {"name": "P90 3Y", "style": "dash", "mau": "down", "y": p90},
           {"name": "FFT 4T thô", "style": "dash", "mau": "amber", "alpha": 0.55, "y": cat(ch, "fn", n0, n)},
           {"name": "FFT 4T chuẩn hoá", "style": "line", "mau": "amber", "y": f}]
    ann, tv = [], trong_tv(hs)
    for ev in g(hs, "co_phan", "lich") or []:
        d, tl = ev.get("hieu_luc"), so_num(ev.get("ty_le"))
        if d and x0 <= d <= x1 and tl and tl >= 0.01 and ms_s(d):
            ann.append({"kind": "vline", "x": ms_s(d), "text": ca_nhan(ev), "mau": "dim", "style": "dot", "uu_tien": 1,
                        "tip": "%s · hiệu lực %s · %s" % (ev.get("su_kien") or "", dmy(d), ev.get("b") or "")})
    dinh, d_dinh = moc_so(g(hs, "gia", "dinh_52w"))
    runs = chuoi_d([x for x in fft.get("pattern_d") or [] if x0 <= str(x.get("tuan") or "") <= x1])
    gan_dinh = next((r for r in runs if d_dinh and abs((ngay(r[0]["tuan"]) - ngay(d_dinh)).days) <= 14), None)
    ve_d = hau_to("fw ≥ 2× nền 12 tuần (vế đọc được của Pattern D) · EST", tv)
    for r in runs:
        tip = "%s: %s" % (ve_d, " · ".join("%s ×%s" % (dm(x["tuan"]), so(x.get("boi"), 1)) for x in r))
        if r is gan_dinh:
            continue
        ann.append({"kind": "xband", "x0": ms_s(r[0]["tuan"]) - 3 * 86400000, "x1": ms_s(r[-1]["tuan"]) + 3 * 86400000,
                    "text": "D×%d (max ×%s)" % (len(r), so(max(so_num(x.get("boi")) or 0 for x in r), 1)), "mau": "info",
                    "alpha": 0.10, "uu_tien": 2, "tip": tip})
    for ten, k in (("Đỉnh 52T", "dinh_52w"), ("Đáy 52T", "day_52w")):
        so_, d = moc_so(g(hs, "gia", k))
        if d and x0 <= d <= x1 and gv(so_) is not None:
            txt = "%s %s" % (ten, gk(gv(so_)))
            if k == "dinh_52w" and gan_dinh:
                txt += " · D×%d" % len(gan_dinh)
            ann.append({"kind": "vline", "x": ms_s(d), "text": txt, "mau": "dim", "style": "dot", "uu_tien": 1,
                        **({"tip": "%s: %s" % (ve_d, " · ".join("%s ×%s" % (dm(x["tuan"]), so(x.get("boi"), 1))
                                                              for x in gan_dinh))} if k == "dinh_52w" and gan_dinh else {})})
    if f and f[-1] is not None:
        ann.append({"kind": "point", "x": ms_s(x1), "y": f[-1], "marker": "dot", "text": pt(f[-1], 3), "pos": "left",
                    "mau": "amber", "uu_tien": 1})
    p10 = cat(ch, "p10", n0, n)
    for ten, arr, mau in (("P90", p90, "bear"), ("P10", p10, "bull")):
        if arr and arr[-1] is not None:
            ann.append({"kind": "point", "x": ms_s(x1), "y": arr[-1], "marker": "none", "text": "%s %s" % (
                ten, pt(arr[-1], 3)), "pos": "left", "mau": mau, "uu_tien": 2})
    dd = fft.get("tuan_do_dang") or {}
    sub = "Vietcap price-history · %d tuần tới %s · mức FFT tuyệt đối EST (ff %s, ảnh chụp coi là hằng)" % (
        len(x), dmy(x1), t.s(fft.get("ff"), "fft.ff", nd=0))
    if dd.get("week_end"):
        sub += " · tuần %s dở dang %s phiên — ngoài thống kê" % (dm(dd["week_end"]), pp(dd.get("days")))
    blk = {"type": "chart", "x": x, "left": {"label": "FFT %/tuần", "min": 0}, "right": {"label": "Giá (nghìn đ)"},
           "series": ser, "annotations": ann,
           "legend": [{"text": "FFT 4T chuẩn hoá (trục trái)", "mau": "amber"},
                      {"text": "FFT 4T thô — cp tuần đóng", "mau": "amber", "dash": True},
                      {"text": "P10 3Y", "mau": "up", "dash": True}, {"text": "P90 3Y", "mau": "down", "dash": True},
                      {"text": "Giá điều chỉnh (trục phải)", "mau": "ink2"}] +
                     ([{"text": hau_to("Đợt fw ≥ 2× nền 12 tuần (vế Pattern D, EST)", tv), "mau": "blue"}] if runs else [])}
    tit = "FFT 4 tuần %s (mức EST) — %s ba năm, %s toàn dải" % (pt(gv(fft.get("ma4")), 3), P(gv(fft.get("pct3y"))),
                                                                P(gv(fft.get("pall"))))
    return sec(blk, "Pillar V · FFT", tit, sub, "EST")


def k_chu(p):
    """Hệ số k hiển thị (spec §8): k_tho (KL khớp thô ÷ Δ cổ đông ròng, như Artifact) là số CHÍNH; k quy cp hiện tại
    là dòng phụ. → (chữ chính, chữ phụ, nhãn k_tho) — thiếu k_tho thì '[CẦN DATA]'."""
    kt, k = gv(p.get("k_tho")), gv(p.get("k"))
    chinh = "k %s nghìn" % so(kt / 1000, 1) if kt is not None else "k [CẦN DATA]"
    phu = "k quy cp hiện tại %s nghìn" % so(k / 1000, 1) if k is not None else ""
    return chinh, phu, K_NHAN.get(p.get("nhan_k_tho") or p.get("nhan_k"), p.get("nhan_k_tho") or p.get("nhan_k") or CO)


def b_cotmoc(t, hs):
    """Pillar I — mốc cổ đông kiểu holdChart của Artifact: block 'cotmoc' (cột rời theo mốc, màu theo bậc; CF/số
    tròn vẽ rỗng). Nội suy không vẽ (chỉ để nối hình ở tệp Toàn Vũ). Không mốc nào → None (lý do vào sổ CẦN DATA)."""
    cd = hs.get("codong") or {}
    moc = [m for m in cd.get("moc") or [] if m.get("kieu") in ("quan_sat", "so_tron", "chep") and ky_ms(m.get("ky"))
           and so_num(m.get("v")) is not None]
    if not moc:
        t.thieu.append(("codong.moc", viet(g(cd, "pattern", "ly_do") or "không có mốc cổ đông quan sát")))
        return None
    nam = int(moc[-1]["ky"][:4])
    moc = [m for m in moc if int(m["ky"][:4]) >= nam - 4]
    vi = {m["ky"]: i for i, m in enumerate(moc) if m.get("kieu") == "quan_sat" and not m.get("cf")}
    items = [{"ky": ky_s(m["ky"]), "v": so_num(m["v"]), "b": m.get("b") or "SS-T3", "kieu": m.get("kieu"),
              "cf": bool(m.get("cf")), "so_tron": m.get("kieu") == "so_tron"} for m in moc]
    vi.update({m["ky"]: i for i, m in enumerate(moc) if m["ky"] not in vi})
    cap = []
    for p in cd.get("cap") or []:
        if p.get("tu") not in vi or p.get("den") not in vi or p.get("trang_thai") not in ("ok", "chi_huong"):
            continue
        if p["trang_thai"] == "chi_huong":
            txt = "chỉ hướng · %s — số tròn, không tính Δ/k" % {"tang": "tăng", "giam": "giảm"}.get(p.get("huong"), "—")
        else:
            chinh, phu, nhan = k_chu(p)
            txt = " · ".join(x for x in ("%s" % t.s(p.get("d_pct"), "codong.cap.d_pct", True, 1), chinh, nhan, phu,
                                         "giá %s" % t.s(p.get("dgia"), "codong.cap.dgia", True, 1)) if x)
        cap.append({"i_tu": vi[p["tu"]], "i_den": vi[p["den"]], "text": txt})
    qs = [m for m in moc if m.get("kieu") == "quan_sat" and not m.get("cf")]
    tit = ("Cổ đông %s (%s)" % (so(qs[-1]["v"], 0), ky_s(qs[-1]["ky"])) if qs else "Số cổ đông theo mốc")
    return {"type": "cotmoc", "title": tit, "b": "SS-T3", "items": items, "cap": cap,
            "sub": "%s · màu = bậc · CF/số tròn vẽ rỗng, nội suy không vẽ · k = KL khớp thô ÷ Δ cổ đông ròng "
                   "(cp/cổ đông, EST); k quy cp hiện tại là dòng phụ" % viet(cd.get("nguon_moc") or "Toàn Vũ")}


def b_ngoai_chart(t, hs):
    """Sở hữu ngoại 63 phiên = 64 điểm từ điểm neo dau_63 (cùng cửa sổ với Δ và đáy của builder). Chuỗi phẳng (trần
    0% hoặc biên < 0,01 điểm) → None: không có gì để vẽ, số nằm ở KPI."""
    ng = hs.get("ngoai") or {}
    ch = ng.get("chuoi") or {}
    ts = ch.get("t") or []
    neo = g(ng, "dau_63", "t")
    n0 = ts.index(neo) if neo in ts else max(0, len(ts) - N_PHIEN_NN - 1)
    x, y = ts[n0:], cat(ch, "pct", n0, len(ts))
    co = [(v, d) for v, d in zip(y, x) if v is not None]
    if not co:
        t.can(ng.get("hien"), "ngoai.chuoi")
        return None
    tran = gv(ng.get("tran"))
    if (tran is not None and tran <= 0) or max(v for v, _ in co) - min(v for v, _ in co) < 0.01:
        return None
    vmin, dmin = min(co)
    ann = [{"kind": "point", "x": ms_s(dmin), "y": vmin, "marker": "dot", "text": "đáy %s (%s)" % (pt(vmin, 2), dm(dmin)),
            "pos": "below", "mau": "bear", "uu_tien": 1},
           {"kind": "point", "x": ms_s(co[-1][1]), "y": co[-1][0], "marker": "dot", "text": pt(co[-1][0], 2), "pos": "left",
            "mau": "info", "uu_tien": 1}]
    return {"type": "chart", "title": "Sở hữu ngoại %d phiên" % (len(x) - 1), "height": 300, "x": x,
            "left": {"label": "%"}, "b": "FACT-T2",
            "sub": "Vietcap tỷ lệ sở hữu ngoại %s → %s · %% theo mẫu số room; số cp của vendor trễ ~1–2 phiên — so "
                   "sánh bằng số cp" % (dm(x[0]), dmy(x[-1])),
            "series": [{"name": "vùng", "style": "band", "lo_min": True, "y_hi": y, "mau": "blue", "alpha": 0.14},
                       {"name": "Sở hữu ngoại %", "style": "line", "mau": "blue", "y": y}],
            "annotations": ann, "legend": [{"text": "Sở hữu ngoại % (mẫu số room) · FACT-T2", "mau": "blue"}]}


# ───────────────────────────── hoso · năm pillar (máy viết từ số) ─────────────────────────────

def p_I(t, hs):
    cd = hs.get("codong") or {}
    if cd.get("trang_thai") != "ok":
        ly = viet(g(cd, "pattern", "ly_do") or "không có mốc cổ đông")
        t.thieu.append(("codong.moc", ly))
        paras = ["[CẦN DATA] — %s." % e(ly)]
        cc = cd.get("co_cau") or {}
        if gv(cc.get("state")) is not None or gv(cc.get("foreign")) is not None:
            paras.append("Cơ cấu sở hữu (Vietcap, ảnh chụp %s): Nhà nước %s · nước ngoài %s · khác %s · HĐQT/BGĐ %s · "
                         "tổ chức %s %s." % tuple([dm(g(cc, "state", "t_lay"))] + [t.s(cc.get(k), "codong.co_cau." + k)
                                                   for k in ("state", "foreign", "other", "bod", "institution")] +
                                                  [tag("FACT-T2", "FACT-T2 · ảnh chụp")]))
        return paras
    v_ky = {m.get("ky"): so_num(m.get("v")) for m in cd.get("moc") or []}
    ok = [p for p in cd.get("cap") or [] if p.get("trang_thai") == "ok"]
    paras = []
    for p in ok[-2:][::-1]:
        chinh, phu, nhan = k_chu(p)
        paras.append("Cặp mốc %s → %s: %s → %s cổ đông (%s) %s; %s cp/cổ đông ròng (KL khớp thô) — nhãn «%s» %s%s; "
                     "giá %s %s." % (
                         ky_s(p["tu"]), ky_s(p["den"]), so(v_ky.get(p["tu"]), 0), so(v_ky.get(p["den"]), 0),
                         t.s(p.get("d_pct"), "codong.cap.d_pct", True, 1), tag(g(p, "d_pct", "b")), chinh, nhan, tag("EST"),
                         " (%s)" % phu if phu else "", t.s(p.get("dgia"), "codong.cap.dgia", True, 1),
                         tag(g(p, "dgia", "b") or "FACT-T2")))
    moc = cd.get("moc") or []
    if moc and moc[-1].get("kieu") != "quan_sat":
        m = moc[-1]
        paras.append("Mốc cuối %s = %s là %s %s." % (ky_s(m.get("ky")), so(m.get("v"), 0),
                                                    KIEU_MOC.get(m.get("kieu"), m.get("kieu")), tag(m.get("b"))))
    dem = {k: sum(1 for m in moc if m.get("kieu") == k) for k in ("quan_sat", "noi_suy", "chep", "so_tron")}
    paras.append("%d mốc quan sát · %d nội suy (chỉ vẽ) · %d chép · %d số tròn. Phân loại pattern của máy: %s — %s." % (
        dem["quan_sat"], dem["noi_suy"], dem["chep"], dem["so_tron"], e(ten_pattern(g(cd, "pattern", "nhan"),
                                                                                   trong_tv(hs))),
        e(viet(g(cd, "pattern", "ly_do") or "không ghi lý do"))))
    return paras


def p_II(t, hs):
    vw, px = hs.get("vwap") or {}, g(hs, "gia", "px")
    nh = VWAP_NHAN.get(vw.get("nhan"))
    mo_ta = (nh[0] if nh[0].lower() == nh[2].lower() else "%s — %s" % (nh[0], nh[2])) if nh else "[CẦN DATA] — thiếu nhãn"
    paras = ["Giá %s so với VWAP 6T %s (%s), 12T %s (%s), 24T %s (%s) %s. Nhãn VWAP: <b>%s</b>. Dải 52 tuần %s–%s." % (
        t.s(px, "gia.px"), t.s(vw.get("v6"), "vwap.v6"), t.s(vw.get("kc6"), "vwap.kc6", True, 1),
        t.s(vw.get("v12"), "vwap.v12"), t.s(vw.get("kc12"), "vwap.kc12", True, 1), t.s(vw.get("v24"), "vwap.v24"),
        t.s(vw.get("kc24"), "vwap.kc24", True, 1), tag("EST", "EST · KL quy cp hiện tại"), e(mo_ta),
        t.s(vw.get("lo52"), "vwap.lo52"), t.s(vw.get("hi52"), "vwap.hi52"))]
    for n in vw.get("neo") or []:
        if isinstance(n, dict):
            paras.append("Neo tác giả %s → %s: %s." % (dmy(n.get("tu")), dmy(n.get("den")), e(n.get("ly_do") or CO)))
    return paras


def p_III(t, hs):
    ct, cd = hs.get("chuthe") or {}, hs.get("codong") or {}
    paras = []
    lon = sorted([x for x in cd.get("lon") or [] if gv(x.get("pct")) is not None], key=lambda x: -gv(x["pct"]))[:4]
    if lon:
        paras.append("Cổ đông lớn (Vietcap shareholder): %s %s." % (" · ".join(
            "%s %s (%s)" % (e(x.get("ten")), pt(gv(x["pct"]), 2), dm(x.get("ngay"))) for x in lon), tag("FACT-T2")))
    nh = ct.get("nhan") if isinstance(ct.get("nhan"), dict) else {}
    paras.append("Nhãn chủ thể trong fft_langkinh: %s %s." % (
        "«%s» ngày %s" % (e(nh["v"]), dmy(nh.get("t"))) if nh.get("v") else t.can(nh, "chuthe.nhan"),
        tag(nh.get("b") or "EST")))
    nb = [x for x in ct.get("noi_bo") or [] if isinstance(x, dict)]
    xong = sorted([x for x in nb if x.get("trang_thai") == "da_xong"], key=lambda x: str(x.get("ngay")))
    cho = sorted([x for x in nb if str(x.get("trang_thai") or "").startswith("dang_ky")], key=lambda x: str(x.get("ngay")))
    if xong:
        x = xong[-1]
        paras.append("GD nội bộ gần nhất đã có kết quả: %s — %s%s %s %s cp, sau GD %s cp %s." % (
            dmy(x.get("ngay")), e(x.get("nguoi") or CO), " (%s)" % e(x["chuc_vu"]) if x.get("chuc_vu") else "",
            e(str(x.get("hanh_dong") or "").lower()), so(abs(so_num(x.get("thuc_hien")) or 0), 0), so(x.get("sau"), 0),
            tag("FACT-T2")))
    if cho:
        x = cho[-1]
        d_den = ngay(hs.get("den") or hs.get("phien_cuoi"))
        moc12 = d_den.replace(year=d_den.year - 1).isoformat() if d_den and not (d_den.month == 2 and d_den.day == 29) \
            else None
        n12 = sum(1 for y in cho if moc12 and str(y.get("ngay") or "") >= moc12)
        t.thieu.append(("chuthe.noi_bo", "%d đăng ký GD nội bộ chưa có kết quả" % len(cho)))
        paras.append("%d đăng ký chưa có kết quả trong 24 tháng (%d trong 12 tháng — cửa sổ của kiểm tự động); gần nhất "
                     "%s — %s đăng ký %s %s cp: khối lượng thực hiện [CẦN DATA] — chưa có kết quả %s." % (
                         len(cho), n12, dmy(x.get("ngay")), e(x.get("nguoi") or CO),
                         e(str(x.get("hanh_dong") or "").lower()), so(x.get("dang_ky"), 0), tag("FACT-T2")))
    sk = sorted([x for x in ct.get("su_kien_von") or [] if x.get("trang_thai") in ("mo_hinh", "niem_yet")],
                key=lambda x: str(x.get("gdkhq") or x.get("cong_bo")))
    if sk:
        x = sk[-1]
        paras.append("Sự kiện vốn gần nhất: %s (công bố %s%s) %s." % (e(x.get("tieu_de") or CO), dmy(x.get("cong_bo")),
                                                                    ", GDKHQ " + dmy(x["gdkhq"]) if x.get("gdkhq") else "",
                                                                    tag("FACT-T2")))
    qh = ct.get("quan_he") or {}
    if qh.get("con") or qh.get("lien_ket"):
        paras.append("Quan hệ (ảnh chụp %s): %d công ty con · %d liên kết %s." % (
            dm(qh.get("t_lay")), len(qh.get("con") or []), len(qh.get("lien_ket") or []), tag("FACT-T2")))
    return paras


def p_IV(t, hs):
    ng, td = hs.get("ngoai") or {}, hs.get("tudoanh") or {}
    r20, r63 = ng.get("rong_20") or {}, ng.get("rong_63") or {}
    paras = ["Sở hữu ngoại %s (%s) → %s (%s); đáy %d phiên %s ngày %s %s. Δ số cp NN 63 phiên %s, giá trị ròng %s; "
             "20 phiên %s / %s %s." % (
                 t.s(ng.get("dau_63"), "ngoai.dau_63"), dm(g(ng, "dau_63", "t")), t.s(ng.get("cuoi_63"), "ngoai.cuoi_63"),
                 dm(g(ng, "cuoi_63", "t")), N_PHIEN_NN, t.s(moc_so(ng.get("day"))[0], "ngoai.day"),
                 dm(moc_so(ng.get("day"))[1]), tag("FACT-T2"), t.s(r63.get("cp"), "ngoai.rong_63.cp", True),
                 t.s(r63.get("ty"), "ngoai.rong_63.ty", True), t.s(r20.get("cp"), "ngoai.rong_20.cp", True),
                 t.s(r20.get("ty"), "ngoai.rong_20.ty", True), tag("FACT-T2"))]
    if "sự kiện vốn" in str(g(r20, "cp", "g") or ""):
        paras.append("Cửa sổ có sự kiện vốn — Δ số cp gồm cp thưởng/phát hành, không phải mua ròng; đọc giá trị ròng (tỷ).")
    paras.append("Tự doanh ròng 20 phiên %s · 63 phiên %s · từ đầu năm %s %s." % (
        t.s(td.get("rong_20"), "tudoanh.rong_20", True), t.s(td.get("rong_63"), "tudoanh.rong_63", True),
        t.s(td.get("ytd"), "tudoanh.ytd", True), tag("FACT-T2")))
    return paras


def p_V(t, hs):
    f = hs.get("fft") or {}
    o8, bc, d1 = f.get("o8") or {}, f.get("bocung_2n") or {}, f.get("d_1n") or {}
    paras = ["FFT 4 tuần %s %s — %s theo 3 năm (%s), %s toàn dải (%s) %s; lệch %s điểm." % (
        t.s(f.get("ma4"), "fft.ma4"), tag("EST", "EST · mức tuyệt đối"), P(gv(f.get("pct3y"))), t.s(f.get("n_tuan_3y"), "fft.n_tuan_3y"),
        P(gv(f.get("pall"))), t.s(f.get("n_tuan_all"), "fft.n_tuan_all"), tag("FACT-T2", "FACT-T2 · hạng"),
        so(gv(f.get("lech")), 0, True)),
        "Ô 8 tuần: FFT %s, giá %s — góc «%s». Bo cung 2 năm: FFT %s (thô %s), giá %s — góc «%s». Một năm: FFT %s, "
        "giá %s %s." % (t.s(o8.get("dfft"), "fft.o8.dfft", True, 1), t.s(o8.get("dgia"), "fft.o8.dgia", True, 1),
                        e(o8.get("goc") or CO), t.s(bc.get("dfft"), "fft.bocung_2n.dfft", True, 1),
                        t.s(bc.get("dfft_tho"), "fft.bocung_2n.dfft_tho", True, 1),
                        t.s(bc.get("dgia"), "fft.bocung_2n.dgia", True, 1), e(bc.get("goc") or CO),
                        t.s(d1.get("dfft"), "fft.d_1n.dfft", True, 1), t.s(d1.get("dgia"), "fft.d_1n.dgia", True, 1),
                        tag("EST", "EST · ΔFFT"))]
    pd = f.get("pattern_d") or []
    paras.append(hau_to("Tuần fw ≥ 2× nền 12 tuần (vế đọc được của Pattern D, 12 tháng gần nhất): %s %s." % (
        " · ".join("%s (×%s)" % (dmy(x.get("tuan")), so(x.get("boi"), 2)) for x in pd) if pd else "không có",
        tag("EST", "EST · vế giá/KL")), trong_tv(hs)))
    return paras


PILLARS = (("Pillar I", "Δ cổ đông · hệ số k", p_I), ("Pillar II", "VWAP cụm 6/12/24T", p_II),
           ("Pillar III", "Ý đồ chủ thể", p_III), ("Pillar IV", "Khối ngoại · tự doanh", p_IV),
           ("Pillar V", "FFT · bo cung", p_V))


def b_pillars(t, hs, nd):
    tg = {x.get("lab"): x for x in (nd or {}).get("pillars") or [] if isinstance(x, dict)}
    items, n_tg = [], 0
    for lab, sub, fn in PILLARS:
        a = tg.get(lab)
        if a and a.get("paras"):
            n_tg += 1
            items.append({"lab": lab, "sub": "%s · %s%s" % (a.get("sub") or sub, pd_nhan(nd, ngan=True),
                                                            " · mức FFT tuyệt đối EST" if lab == "Pillar V" else ""),
                          "paras": a["paras"]})
        else:
            items.append({"lab": lab, "sub": sub + " · máy đọc số", "paras": fn(t, hs)})
    if n_tg:
        tit = "Năm pillar — %s" % pd_nhan(nd)
        sub = ("Đoạn có ngày là chữ nguyên văn của tác giả (%s; số là số lúc viết, không phải số sống; mức FFT tuyệt "
               "đối trong đoạn là EST, percentile là FACT-T2). Pillar không có chữ tác giả do máy viết từ số, không có "
               "nhận định." % pd_tuoi(nd, t.now))
    else:
        tit = "Năm pillar đọc từ số của hồ sơ"
        sub = "Máy viết từ số — chỉ số liệu và định nghĩa, không có nhận định; bậc ghi ở từng thẻ."
    return sec({"type": "pillars", "items": items}, "Năm pillar · v1.7", tit, sub)


# ───────────────────────────── hoso · σ · keynote · nguồn ─────────────────────────────

def b_hang_I_IV(t, hs):
    """Pillar I (cột mốc cổ đông) + Pillar IV (sở hữu ngoại 63 phiên). Khối nào không có gì để vẽ thì bỏ (lý do ở
    sổ CẦN DATA/KPI) — không đặt note cao bằng biểu đồ bên cạnh (a2)."""
    ds = [x for x in (b_cotmoc(t, hs), b_ngoai_chart(t, hs)) if x]
    co_v = [m for m in g(hs, "codong", "moc") or [] if m.get("kieu") == "quan_sat" and not m.get("cf")]
    tit = "Cổ đông %s (%s) · sở hữu ngoại %s" % (so(co_v[-1].get("v"), 0) if co_v else "[CẦN DATA]",
                                               ky_s(co_v[-1].get("ky")) if co_v else "ngoài 30 mã Toàn Vũ",
                                               t.s(g(hs, "ngoai", "hien"), "ngoai.hien"))
    if not ds:
        return sec({"type": "note", "pill": "CẦN DATA", "mau": "bear", "title": "Không có chuỗi để vẽ",
                    "text": "Mốc cổ đông và chuỗi sở hữu ngoại đều trống hoặc phẳng — số ở KPI và sổ CẦN DATA."},
                   "Pillar I · IV — cổ đông và khối ngoại", tit)
    blk = ds[0] if len(ds) == 1 else {"type": "row", "items": ds}
    return sec(blk, "Pillar I · IV — cổ đông và khối ngoại", tit)


def b_sigma(t, hs, ma):
    sg = hs.get("sigma") or {}
    nl = sigma_numline(t, hs, ma)
    tit = "%s %s · %s so với trung bình %s phiên · %s" % (
        CHI_SO.get(sg.get("chi_so"), "σ") + (" (%s)" % doi_nhan(sg) if doi_nhan(sg) else ""), t.s(sg.get("x"), "sigma.x"),
        t.s(sg.get("z"), "sigma.z"), so(sg.get("n_phien"), 0), sigma_cach(t, sg, ma))
    return sec(nl, "Vùng giá σ · Vietcap ratio-daily", tit,
               nl.get("sub", "") + ". Dải trong không gian giá: base = giá ÷ tỷ số, ngưỡng = base × (μ ± kσ) — μ, σ "
                                   "của chính mã (EST); khoảng cách tới μ và −1σ là EST.", "EST")


def b_keynote(hs):
    ks = [k for k in hs.get("keynote_tu_dong") or [] if isinstance(k, dict)]
    if not ks:
        return None
    tv = trong_tv(hs)
    items = [{"id": "M%d" % (i + 1), "pill": k.get("b") or "EST", "pill_mau": TAG_MAU.get(k.get("b"), "grey"),
              "tieu_de": hau_to(viet(k.get("tieu_de") or CO), tv), "noi_dung": e(hau_to(viet(k.get("noi_dung")), tv))}
             for i, k in enumerate(ks)]
    return sec({"type": "cards", "variant": "keynote", "items": items}, "Kiểm dữ liệu · máy tự sinh",
               "%d điểm phải đọc kèm số" % len(items),
               "Chỉ kiểm dữ liệu (CF, nội suy, lệch chuẩn hoá, độ tươi, hai cửa sổ) — không có ý kiến đầu tư.")


def b_chips(t, hs, nd):
    ex = []
    if g(hs, "codong", "trang_thai") == "ok":
        ex.append({"b": "SS-T3", "text": "%s — mốc cổ đông; nội suy chỉ vẽ" % viet(g(hs, "codong", "nguon_moc"))})
    ex.append({"b": "EST", "text": "fft_langkinh — CỔNG (%s) và nhãn chủ thể máy" % viet(g(hs, "cong", "as_of") or CO)})
    n = nav_so(hs)
    if gv(n) is not None:
        ex.append({"b": n.get("b") or "EST", "text": "Tỷ trọng NAV — %s" % viet(n.get("g") or "danh mục nội bộ")})
    if gv(g(hs, "gia", "bang")) is not None:
        ex.append({"b": "FACT-T2", "text": "KHO vnstock gia_moi — giá bảng sơ bộ %s, tách khỏi chuỗi Vietcap" %
                   dm(g(hs, "gia", "bang", "t_lay") or g(hs, "gia", "bang", "t"))})
    if g(hs, "sigma", "hhp"):
        ex.append({"b": "EST", "text": "Engine HHP (hhp_vn100_valuation.json) — σ tham chiếu, thước khác"})
    if nd:
        ex.append({"b": "EST", "text": "Lớp phán đoán: %s — %s" % (pd_nhan(nd), nd.get("nguon_url") or "lk_nhan_dinh.json")})
    return sec({"type": "chips", "items": chips_nguon(hs.get("nguon"), ex)}, "Nguồn", "Nguồn của hồ sơ",
               "Màu tag = bậc bằng chứng (luật §0.2) · 'dữ liệu tới' = ngày dữ liệu của chính nguồn")


# ───────────────────────────── view · hoso ─────────────────────────────

def trang_thieu_ho_so(t, ma, ly):
    m = g(t.c.ma, ma) or {}
    blocks = [{"type": "tkhead", "ma": ma, "eyebrow": " · ".join(x for x in (m.get("ten"), m.get("nganh")) if x) or ma,
               "tieu_de": "[CẦN DATA] — chưa có hồ sơ Lăng Kính", "px": "[CẦN DATA]", "chg": "", "pills": [],
               "cong_ma": "[CẦN DATA] — hồ sơ chưa dựng"},
              {"type": "note", "pill": "CẦN DATA", "mau": "bear", "title": "Chưa có hồ sơ %s" % ma,
               "text": "%s.<br>%s. Hồ sơ đang có: %s." % (e(ly), e(GOI_Y % ma),
                                                          e(", ".join(t.co_ho_so()) or "không có"))}]
    return {"title": "Hồ sơ %s — [CẦN DATA]" % ma, "sub": ly, "blocks": blocks,
            "data": [{"01 Mục": "Hồ sơ %s" % ma, "02 Giá trị": "[CẦN DATA]", "03 Ghi chú": ly}],
            "tickers": t.co_ho_so(), "cong": CT.cong_ma(t.c, ma),
            "payload": {"layout": "hoso", "as_of": "", "tuoi": "chưa có hồ sơ"}}


def v_hoso(c):
    t = Trang(c)
    ma = c.scope if c.scope not in SCOPES and RE_MA.match(c.scope or "") else "FPT"
    c.scope, c.members = ma, [ma]
    hs = t.ho_so(ma)
    if hs is None:
        return trang_thieu_ho_so(t, ma, "Không đọc được data/lk_hoso/%s.json" % ma)
    nd = t.nd(ma, hs)
    kp = b_kpis(t, hs)
    vw, px = hs.get("vwap") or {}, g(hs, "gia", "px")
    kc = {k: (round(gv(vw.get(k)) / 100, 6) if gv(vw.get(k)) is not None else None) for k in ("kc6", "kc12", "kc24")}
    nh = VWAP_NHAN.get(vw.get("nhan"))
    b_vw = sec({"type": "numline", "mode": "vwap", "px": gv(px), "v6": gv(vw.get("v6")), "v12": gv(vw.get("v12")),
                "v24": gv(vw.get("v24")), "lo": gv(vw.get("lo52")), "hi": gv(vw.get("hi52")), "nhan": vw.get("nhan"), **kc},
               "Pillar II · VWAP cụm 6/12/24T", "Giá %s — %s" % (t.s(px, "gia.px"), nh[2] if nh else "[CẦN DATA] nhãn VWAP"),
               "Giá điều chỉnh · KL quy về số cp hiện tại · Vietcap price-history tới %s" % dmy(g(vw, "v6", "t")), "EST")
    blocks = [b_tkhead(t, hs, nd), b_tac_gia(t, hs, nd), kp, b_fft(t, hs), b_pillars(t, hs, nd), b_hang_I_IV(t, hs), b_vw]
    if MH is not None:
        blocks += MH.khoi_ho_so(t, ma, hs)
    if nd and (nd.get("marks") or nd.get("munger")):
        box = [{"tieu_de": x.get("tieu_de") or CO, "noi_dung": x.get("noi_dung") or "", "inv": inv}
               for x, inv in ((nd.get("marks"), False), (nd.get("munger"), True)) if isinstance(x, dict)]
        blocks.append(sec({"type": "cards", "variant": "box", "items": box}, pd_nhan(nd), "Tư duy bậc hai và nghịch đảo",
                          "Chữ nguyên văn của tác giả — %s, ảnh chụp; số là số lúc viết." % pd_dau(nd, t.now)))
    blocks += [b_trigger(t, hs, nd), b_sigma(t, hs, ma), b_keynote(hs), b_chips(t, hs, nd)]
    can = [(x.get("khoa"), viet(x.get("ly_do"))) for x in hs.get("can_data") or [] if isinstance(x, dict)]
    blocks.append(note_can(t, can))
    _, tuoi = tuoi_tep(hs.get("tao_luc"), t.now)
    sub = "Lăng Kính cấu trúc cổ đông · Vietcap IQ tới phiên %s · tuần FFT đóng %s" % (dmy(hs.get("phien_cuoi")),
                                                                                  dmy(hs.get("tuan_cuoi")))
    cong = CT.cong_ma(c, ma)
    cong["dong"] = dong_b(cong.get("dong"))
    return {"title": "Hồ sơ %s — %s" % (ma, hs.get("ten") or ma), "sub": sub, "blocks": [b for b in blocks if b],
            "data": rows_kpi(kp["items"]), "tickers": t.co_ho_so(), "cong": cong,
            "payload": {"layout": "hoso", "as_of": "phiên %s · tuần %s" % (dmy(hs.get("phien_cuoi")), dm(hs.get("tuan_cuoi"))),
                        "tuoi": tuoi}}
