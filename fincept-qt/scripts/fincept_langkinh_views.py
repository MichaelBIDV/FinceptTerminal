#!/usr/bin/env python3
"""
Fincept Terminal — Lăng kính cấu trúc cổ đông & FFT: dựng "trang" (blocks) cho 6 view quét FFT của LangKinhPanel.
Định dạng/khối dùng chung ở fincept_langkinh_base.py; CỔNG + chủ thể ở fincept_langkinh_chuthe.py; chữ cố định ở
fincept_langkinh_texts.py (tên được nhập lại ở đây để fincept_langkinh.py dùng `V.<tên>` như cũ).
Stdlib only; Python 3.11 và 3.14. KHÔNG tính lại công thức CONTRACT §2 (bridge goi_fft.py đã tính) — chỉ xếp hạng,
đếm, định dạng. Mọi chữ cố định là chữ của hợp đồng / phương pháp, không phải văn xuôi sinh mỗi lần chạy.
"""
import re
from datetime import date

import fincept_langkinh_texts as T
from fincept_langkinh_base import *  # noqa: F401,F403 — nhập lại cho fincept_langkinh.py (V.so, V.dm, …)
from fincept_langkinh_base import (BUCKET_NHAN, BUCKET_TEN, CO, LOP_TEN, O2N_MAU, VIEN, P, bac_ro, bang, boi,
                                   cat_chuoi, chip_mau, cot, dm, dm_tag, dm_tip, dmy, dong, ds_chu, ff_hien, fftp, g,
                                   ghi, gia, lech_thoi, mau_bar, mau_dau, mau_o8, mau_pct, ms, ngay, phang, phu_ro, pp,
                                   pt, so, so_bo, so_num, the, tile_pct, trung_vi, ve)
from fincept_langkinh_chuthe import bac_yeu, cong_ro, ct_of, dem_nhan, loai_chu_the, note_cong


# ───────────────────────────── 1 · tongquan ─────────────────────────────

COT_PHIEN = [cot("ma", "Mã", "left"), cot("gia", "Giá"), cot("chg", "%"), cot("kl", "KL"), cot("x20", "×20d"),
             cot("fftd", "FFT ngày"), cot("ma4", "FFT 4w"), cot("boi", "Bội số"), cot("pct", "pct3Y")]


def dong_phien(c, s):
    m = c.ma[s]
    ph, tu = m.get("phien") or {}, m.get("tuan") or {}
    lt, ltip = lech_thoi(m, c.lk)
    return dong({"ma": s, "gia": gia(ph.get("close")), "chg": pt(ph.get("chg"), 2, True), "kl": so(ph.get("vol"), 0),
                 "x20": boi(ph.get("vol_x20")), "fftd": fftp(ph.get("fft_d")), "ma4": fftp(tu.get("ma4")),
                 "boi": boi(ph.get("boi_so")), "pct": pp(tu.get("pct3y"))},
                sort={"gia": so_num(ph.get("close")), "chg": so_num(ph.get("chg")), "kl": so_num(ph.get("vol")),
                      "x20": so_num(ph.get("vol_x20")), "fftd": so_num(ph.get("fft_d")),
                      "ma4": so_num(tu.get("ma4")), "boi": so_num(ph.get("boi_so")), "pct": so_num(tu.get("pct3y"))},
                mau={"chg": mau_dau(ph.get("chg")), "pct": mau_pct(tu.get("pct3y")), "gia": "warn" if lt else ""},
                tag={"ma": dm_tag(m), "gia": lt}, tip={"gia": ltip}, vien="warn" if lt else "", link=s)


def ds_lech(c, ds=None):
    """Mã cũ / chờ CA (lech_thoi) trong rổ — không vào đếm, xếp hạng, ma trận, scatter."""
    return [s for s in (c.members if ds is None else ds) if lech_thoi(c.ma[s], c.lk)[0]]


def lech_chu(c, ds):
    return "; ".join("%s %s" % (s, lech_thoi(c.ma[s], c.lk)[0]) for s in ds)


def dem_ro(c):
    """Đếm rổ: ưu tiên số của bridge (thi_truong); dự phòng đếm tại chỗ, bỏ mã cũ / chờ CA."""
    tt = g(c.lk, "thi_truong", c.scope) or {}
    lech = ds_lech(c)
    bk = [g(c.ma, s, "tuan", "bucket") for s in c.members if s not in lech]
    pc = [g(c.ma, s, "tuan", "pct3y") for s in c.members if s not in lech]

    def lay(k, fb):
        return so_num(tt.get(k)) if so_num(tt.get(k)) is not None else fb
    return {"cc": lay("n_can_cung", bk.count("can_cung")), "pp": lay("n_phan_phoi", bk.count("phan_phoi")),
            "nd": lay("n_co_du_lieu", sum(1 for x in pc if so_num(x) is not None)),
            "tv": lay("n_thanh_vien", len(c.members)), "tvi": lay("trung_vi_pct3y", trung_vi(pc))}


def the_mfft(k, tt, v, s, hang=False):
    """Tile Market FFT: luôn kèm 'n/N mã có FF'; độ phủ < 0,8 → mau warn + câu cảnh báo (B5).
    `hang` = giá trị là percentile/số đếm → bậc bac_hang; ngược lại mức → bac_muc (R1, bac_ro)."""
    n, tong, thieu_ = phu_ro(tt)
    s += " · %s/%s mã có FF" % (pp(n), pp(tong))
    if thieu_:
        s += " — " + T.PHU_THIEU
    return the(k, v, s, "warn" if thieu_ else mau_bar(tt.get("pct3y")), bac_ro(tt, hang))


def tiles_dem(cd, k_bn, duoi_bn):
    """Tile Bùng nổ / Đặc lại: số đếm theo luật mã hoá trên mốc quan sát = EST (D0.1: luật Claude mã hoá từ lời tác giả),
    không mượn bậc cấp tệp; số W37 (dem.w37, SS-T3) đặt cạnh khi bridge có. Bậc không mạnh hơn mã yếu nhất."""
    dem, mau = cd.get("dem") or {}, cd.get("mau") or 30
    w37 = dem.get("w37")
    ma = {s: v for s, v in (cd.get("ma") or {}).items() if isinstance(v, dict)}
    out = []
    for key, k, luat, duoi, mau_ in (("bung_no", k_bn, "D3.3", duoi_bn, "amber"),
                                     ("dac_lai", "ĐẶC LẠI Ở ĐÁY 2N", "D3.4", T.CD_DAC_LAI, "info")):
        b0 = dem.get("bac").get(key) if isinstance(dem.get("bac"), dict) else dem.get("bac")
        bac = bac_yeu([b0 or "EST", "EST"] + [v.get("bac") for v in ma.values() if v.get("lop") == key])
        s = "(%s · mốc quan sát, luật %s)" % (bac, luat)
        n37 = w37.get(key) if isinstance(w37, dict) else (w37 if key == "bung_no" else None)
        if so_num(n37) is not None:
            s += " · W37: %s/%s (%s)" % (pp(n37), pp(mau), (w37.get("bac") if isinstance(w37, dict) else None) or "SS-T3")
        out.append(the(k, "%s/%s" % (pp(dem.get(key)), pp(mau)), s + " · " + duoi, mau_, bac))
    return out


def v_tongquan(c):
    sc, lk = c.scope, c.lk
    ph = lk.get("phien") or {}
    nph = ph.get("ngay") or lk.get("phien_cuoi")
    sb = so_bo(lk)
    vni = ph.get("vnindex") or {}
    tiles = [the("VN-INDEX · PHIÊN %s%s" % (dm(nph), sb), so(vni.get("dong"), 2),
                 "%s · %s điểm" % (pt(vni.get("chg_pct"), 2, True), so(vni.get("chg_diem"), 2, True)),
                 mau_dau(vni.get("chg_pct")), vni.get("bac") or "")]
    lech = ds_lech(c)
    hom = [s for s in c.members if s not in lech and so_num(g(c.ma, s, "phien", "chg")) is not None
           and (not nph or g(c.ma, s, "phien", "ngay") == nph)]
    tang = sum(1 for s in hom if c.ma[s]["phien"]["chg"] > 0)
    giam = sum(1 for s in hom if c.ma[s]["phien"]["chg"] < 0)
    s_ = "tăng %d · giảm %d · đứng %d" % (tang, giam, len(hom) - tang - giam)
    if len(hom) + len(lech) < len(c.members):
        s_ += " · %d mã thiếu phiên" % (len(c.members) - len(hom) - len(lech))
    if lech:
        s_ += " · %d mã cũ/chờ CA (loại khỏi đếm)" % len(lech)
    rt = ph.get("do_rong_tt") or {}
    if rt:
        s_ += " · toàn TT %s/%s/%s trên %s (%s)" % (pp(rt.get("tang")), pp(rt.get("giam")), pp(rt.get("dung")),
                                                     pp(rt.get("tong")), rt.get("nguon") or CO)
    tiles.append(the("ĐỘ RỘNG PHIÊN · %s" % sc, "%d/%d" % (tang, len(hom)), s_,
                     "bull" if tang > giam else ("bear" if giam > tang else "dim"), "FACT-T2"))
    tt = g(lk, "thi_truong", sc) or {}
    tiles.append(the_mfft("MARKET FFT %s · TB 4 TUẦN" % sc, tt, fftp(tt.get("ma4")),
                          "%s 3Y · toàn dải %s · 4 tuần trước %s" % (P(tt.get("pct3y")), P(tt.get("pall")),
                                                                      P(tt.get("pct3y_4t_truoc")))))
    kia = "VN100" if sc == "VN30" else "VN30"
    tk = g(lk, "thi_truong", kia) or {}
    tiles.append(the_mfft("MARKET FFT %s · VỊ TRÍ 3Y" % kia, tk, P(tk.get("pct3y")),
                          "toàn dải %s · 4 tuần trước %s · chỉ so percentile, không so mức" % (
                              P(tk.get("pall")), P(tk.get("pct3y_4t_truoc"))), hang=True))
    d = dem_ro(c)
    ds = "%s thành viên · %s mã có pct 3Y" % (pp(d["tv"]), pp(d["nd"]))
    tiles += [the("CẠN CUNG ≤P20 (3Y)", "%s/%s" % (pp(d["cc"]), pp(d["nd"])), ds, "bull", "FACT-T2"),
              the("PHÂN PHỐI ≥P75 (3Y)", "%s/%s" % (pp(d["pp"]), pp(d["nd"])), ds, "bear", "FACT-T2"),
              the("TRUNG VỊ PCT 3Y · %s" % sc, P(d["tvi"]), ds, mau_bar(d["tvi"]), "FACT-T2")]
    cd = c.cd
    if cd:
        tiles += tiles_dem(cd, "CỔ ĐÔNG BÙNG NỔ ≥+50% TỪ ĐÁY 2N", "tệp Toàn Vũ %s · mẫu gốc /%s" % (
            dmy(cd.get("ngay_tep")), pp(cd.get("mau") or 30)))
    else:
        tiles += [the("CỔ ĐÔNG BÙNG NỔ ≥+50% TỪ ĐÁY 2N", CO, "[CẦN DATA] chưa có fft_codong.json", "dim", ""),
                  the("ĐẶC LẠI Ở ĐÁY 2N", CO, "[CẦN DATA] chưa có fft_codong.json", "dim", "")]
    bc = g(c.cong, "boi_canh") or {}
    tiles.append(the("REGIME HUB · NGỮ CẢNH", "%s · %s" % (bc.get("regime") or CO, so(bc.get("score"), 1)),
                     "trend/breadth kỹ thuật, không phải chu kỳ tiền · %s" % (bc.get("luc") or CO), "dim",
                     bc.get("bac") or "EST"))
    theo_chg = sorted(hom, key=lambda s: (-abs(c.ma[s]["phien"]["chg"]), s))
    vol = sorted([s for s in c.members if s not in lech and so_num(g(c.ma, s, "phien", "vol_x20")) is not None
                  and (not nph or g(c.ma, s, "phien", "ngay") == nph)],
                 key=lambda s: (-c.ma[s]["phien"]["vol_x20"], s))
    b1 = bang("bien_dong", "Biến động giá mạnh nhất", COT_PHIEN, [dong_phien(c, s) for s in theo_chg[:10]],
              "phiên %s%s · |Δ%%| lớn nhất trong %d mã có dữ liệu" % (dm(nph), sb, len(hom)), T.MUC_EST)
    b2 = bang("dot_bien_kl", "Đột biến khối lượng", COT_PHIEN, [dong_phien(c, s) for s in vol[:10]],
              "phiên %s%s · ×20d = KL phiên ÷ TB KL 20 phiên liền trước" % (dm(nph), sb),
              "Bội số = FFT ngày ÷ FFT TB 4 tuần. " + T.MUC_EST)
    doc_ = ghi("Quy tắc đọc", T.QUY_TAC_DOC, "Tĩnh", "dim")
    ds_ = theo_chg + [s for s in c.members if s not in hom]
    return {"title": "Tổng quan phiên %s%s · %s" % (dmy(nph), sb, sc),
            "sub": "Pillar V · FFT tuần kết thúc %s%s · %d mã trong rổ" % (
                dm(g(lk, "tuan", "week_end")), dang_do(lk), len(c.members)),
            "blocks": [note_cong(c, cong_ro(c)), {"type": "tiles", "items": tiles}, b1, b2, doc_],
            "data": phang(bang("", "", COT_PHIEN, [dong_phien(c, s) for s in ds_]))}


def dang_do(lk):
    t = lk.get("tuan") or {}
    return " (dở dang — %s phiên)" % pp(t.get("so_phien_tuan")) if t.get("do_dang") else ""


# ───────────────────────────── 2 · bangquet ─────────────────────────────

COT_BQ = [cot("ma", "Mã", "left"), cot("gia", "Giá"), cot("chg", "%ngày"), cot("ma4", "FFT 4w"), cot("f8", "8w"),
          cot("f26", "26w"), cot("f52", "52w"), cot("p10", "P10 3Y"), cot("p90", "P90 3Y"), cot("xp", "×P10"),
          cot("vt", "Vị trí trong 3 năm", "left", "bar"), cot("pall", "Pall"), cot("o8", "Ô 8 tuần", "left", "tag"),
          cot("r52", "52w"), cot("r2y", "2Y"), cot("dv", "ΔVol 2Y"), cot("ff", "FF")]


def dong_bq(c, s):
    m = c.ma[s]
    tu, ph, ff = m.get("tuan") or {}, m.get("phien") or {}, m.get("ff") or {}
    close = ph.get("close") if so_num(ph.get("close")) is not None else tu.get("close")
    dv = so_num(tu.get("vol_drop_2y"))
    vt = so_num(tu.get("vi_tri"))
    cff, ctu = co_du_lieu(m)
    fh = ff_hien(ff)  # % FF = mẫu số FFT (ff_cp ÷ issue_share), không phải % VCI làm tròn
    fcanh = bool(cff) or fh["canh"]
    lt, ltip = lech_thoi(m, c.lk)
    return dong({"ma": s, "gia": gia(close), "chg": pt(ph.get("chg"), 2, True), "ma4": fftp(tu.get("ma4")),
                 "f8": fftp(tu.get("fft_8w")), "f26": fftp(tu.get("fft_26w")), "f52": fftp(tu.get("fft_52w")),
                 "p10": fftp(tu.get("p10_3y")), "p90": fftp(tu.get("p90_3y")), "xp": boi(tu.get("x_p10")),
                 "vt": pp(tu.get("pct3y")), "pall": pp(tu.get("pall")), "o8": tu.get("o8") or CO,
                 "r52": pt(tu.get("ret_52w"), 0, True), "r2y": pt(tu.get("ret_2y"), 0, True),
                 "dv": pt(dv, 0, True), "ff": pt(fh["p"], fh["nd"])},
                sort={"gia": so_num(close), "chg": so_num(ph.get("chg")), "ma4": so_num(tu.get("ma4")),
                      "f8": so_num(tu.get("fft_8w")), "f26": so_num(tu.get("fft_26w")),
                      "f52": so_num(tu.get("fft_52w")), "p10": so_num(tu.get("p10_3y")),
                      "p90": so_num(tu.get("p90_3y")), "xp": so_num(tu.get("x_p10")),
                      "vt": so_num(tu.get("pct3y")), "pall": so_num(tu.get("pall")),
                      "r52": so_num(tu.get("ret_52w")), "r2y": so_num(tu.get("ret_2y")), "dv": dv,
                      "ff": round(fh["p"], 4) if fh["p"] is not None else None},
                mau={"chg": mau_dau(ph.get("chg")), "o8": mau_o8(tu), "r52": mau_dau(tu.get("ret_52w")),
                     "dv": "" if dv is None else ("bull" if dv > 0 else "bear"), "ff": "warn" if fcanh else "",
                     "gia": "warn" if lt else ""},
                tag={"ma": dm_tag(m), "ff": "⚠" if fcanh else "", "xp": "⚠" if ctu else "", "gia": lt},
                bar={"vt": {"frac": vt, "mau": mau_bar(tu.get("pct3y"))} if vt is not None else None},
                vien="warn" if lt else VIEN.get(tu.get("bucket"), ""), link=s,
                tip={"ma": dm_tip(m), "ff": "; ".join(x for x in [fh["tip"]] + cff if x), "xp": "; ".join(ctu),
                     "gia": ltip})


def xep(c, key, desc=False):
    """Sắp theo tuan.<key>; mã cũ / chờ CA và mã thiếu số ra cuối (không vào thứ hạng)."""
    lech = ds_lech(c)
    co = [s for s in c.members if s not in lech and so_num(g(c.ma, s, "tuan", key)) is not None]
    co.sort(key=lambda s: ((-1 if desc else 1) * c.ma[s]["tuan"][key], s))
    return co + [s for s in c.members if s not in co]


def thieu(c):
    ds = ["%s (%s)" % (s, c.ma[s]["loi"]) for s in c.members if c.ma[s].get("loi")]
    lech = ds_lech(c)
    return ((" Thiếu dữ liệu: %s." % "; ".join(ds)) if ds else "") + (
        " Dữ liệu cũ / chờ CA (tag, xuống cuối, loại khỏi đếm): %s." % lech_chu(c, lech) if lech else "")


def co_du_lieu(m):
    """Cờ dữ liệu của mã → (cờ free float: I3 ff.canh_bao + R3 canh_bao mã, cờ cửa sổ tuần: I4 tuan.canh_bao)."""
    return ds_chu(g(m, "ff", "canh_bao")) + ds_chu(m.get("canh_bao")), ds_chu(g(m, "tuan", "canh_bao"))


def co_nhom(c, ds):
    """Gom mã theo nguyên văn cờ (EST); tỷ lệ riêng từng mã '(×1,80)' của I3 tách ra cạnh tên mã."""
    nhom = {}
    for s in ds:
        for x in sum(co_du_lieu(c.ma[s]), []):
            m = re.search(r"\s*\((×[\d.,]+)\)", x)
            nhom.setdefault(x[:m.start()] + x[m.end():] if m else x, []).append(s + (" " + m.group(1) if m else ""))
    return nhom


def co_caption(c):
    """Caption: mã gắn cờ dữ liệu (EST) + mã có danh mục mâu thuẫn nguồn (R10, tag '*')."""
    nhom = co_nhom(c, c.members)
    out = (" Cờ dữ liệu ⚠ (EST): %s." % "; ".join("%s — %s" % (x, ", ".join(v)) for x, v in nhom.items())
           if nhom else "")
    xd = ["%s (%s)" % (s, dm_tip(c.ma[s])) for s in c.members if dm_tip(c.ma[s])]
    return out + (" Tag * = %s." % "; ".join(xd) if xd else "")


def v_bangquet(c):
    sc, lk = c.scope, c.lk
    key = "pct3y" if sc == "VN30" else "x_p10"
    rows = [dong_bq(c, s) for s in xep(c, key)]
    t = lk.get("tuan") or {}
    cap = ("ΔVol 2Y dương = khối lượng đã co lại so với 2 năm trước (dấu hiệu lock); âm = khối lượng phình ra. "
           "8w/26w/52w = FFT TB 4 tuần ở 8/26/52 tuần trước. P10/P90 3Y = phân vị cuộn 156 tuần của FFT tuần thô; "
           "Pall = percentile toàn dải 2020→ (v1.7 gốc 2010→: [CẦN DATA] trước 2020). " + T.MUC_EST)
    if t.get("do_dang"):
        cap += " Tuần %s dở dang — %s phiên; TB 4 tuần đã gồm tuần dở dang." % (dm(t.get("week_end")),
                                                                                pp(t.get("so_phien_tuan")))
    b = bang("bangquet", "Bảng quét — %s · %d mã" % (sc, len(rows)), COT_BQ, rows,
             "Sắp %s · vạch trái: xanh = cạn cung ≤P20 · đỏ = phân phối ≥P75 · xám = giữa" % (
                 "pct 3Y tăng dần" if sc == "VN30" else "×P10 tăng dần (khối B)"), cap + thieu(c) + co_caption(c))
    return {"title": "Bảng quét FFT — %s" % sc,
            "sub": "Tuần kết thúc %s%s · phiên %s%s" % (dm(t.get("week_end")), dang_do(lk),
                                                         dmy(g(lk, "phien", "ngay") or lk.get("phien_cuoi")), so_bo(lk)),
            "blocks": [b], "data": phang(b)}


# ───────────────────────────── 3 · matran ─────────────────────────────

MX_O = {("up", 0): ("Markup có retail", "Đầu sóng thì tốt; nếu FFT > P90 và Δ cổ đông tăng ⇒ Pattern A (đỉnh). "
                    "Không mua đuổi."),
        ("up", 1): ("Phân phối / đổi chủ", "Hàng được đẩy ra khi giá giảm. Phân biệt \"tháo hàng\" với \"đổi chủ\" "
                    "bằng Pillar III + GUO."),
        ("down", 0): ("Bo cung — markup không vol", "Vùng lý tưởng: float đã lock, giá lên không cần thanh khoản. "
                      "Kiểm tra chủ DN có động cơ giữ giá không."),
        ("down", 1): ("Tích luỹ / cạn cung", "Hoặc đang gom xong chờ markup, hoặc \"mất hút thanh khoản\" sau khi "
                      "sập — phân biệt bằng ý đồ chủ thể."),
        ("flat", 0): ("Chưa có tín hiệu.", ""), ("flat", 1): ("Chưa có tín hiệu.", "")}
MX_HANG = (("up", "FFT ↑"), ("down", "FFT ↓"), ("flat", "FFT ↔"))


def v_matran(c):
    o, bo, lech = {}, [], ds_lech(c)
    for s in xep(c, "pct3y"):
        tu = g(c.ma, s, "tuan") or {}
        f, gg = tu.get("o8_fft"), tu.get("o8_gia")
        if s in lech:
            continue
        if f not in ("up", "down", "flat") or gg not in ("up", "down", "flat"):
            bo.append(s)
            continue
        o.setdefault((f, 0 if gg == "up" else 1), []).append(
            {"ma": s, "v": pp(tu.get("pct3y")), "mau": chip_mau(c.ma[s])})
    rows = [{"label": nhan, "cells": [{"title": MX_O[(k, j)][0], "note": MX_O[(k, j)][1], "chips": o.get((k, j), [])}
                                      for j in (0, 1)]} for k, nhan in MX_HANG]
    blocks = [{"type": "matrix", "cols": ["Giá ↑", "Giá ↓ / đi ngang"], "rows": rows},
              ghi("Quy ước", "Ô 8 tuần là quy ước pipeline Cowork (±5% FFT, ±1% giá so 8 tuần trước), không có trong "
                  "v1.7 bản cuối. Giá ↔ xếp vào cột phải cho cả ba hàng. Chip: số = pct 3Y · cam = danh mục · "
                  "xanh = watchlist; sắp pct 3Y tăng dần.<br><b>M:718</b> “" + T.M718 + "”", "Quy ước", "dim")]
    if bo:
        blocks.append(ghi("Không xếp được", "Thiếu Ô 8 tuần: %s." % ", ".join(bo), "", "warn"))
    if lech:
        blocks.append(ghi("Dữ liệu cũ / chờ CA — không xếp", "Ô 8 tuần của các mã này không cùng kỳ / cùng cơ sở giá "
                          "với rổ: %s." % ", ".join("%s (%s)" % (s, lech_thoi(c.ma[s], c.lk)[0]) for s in lech),
                          "", "warn"))
    data = [{"01 Mã": s, "02 Ô 8 tuần": g(c.ma, s, "tuan", "o8") or CO, "03 pct3Y": pp(g(c.ma, s, "tuan", "pct3y"))}
            for s in xep(c, "pct3y")]
    return {"title": "Ma trận FFT × Giá — %s" % c.scope,
            "sub": "Ô 8 tuần: TB 4 tuần FFT và giá so 8 tuần trước · %d/%d mã xếp được" % (
                len(c.members) - len(bo) - len(lech), len(c.members)), "blocks": blocks, "data": data}


# ───────────────────────────── 4 · bocung ─────────────────────────────

COT_BC = [cot("ma", "Mã", "left"), cot("d2", "ΔFFT 2N"), cot("g2", "Giá 2N"), cot("d1", "ΔFFT 1N (EST)"),
          cot("g1", "Giá 1N"), cot("pct", "P 3Y"), cot("ct", "Chủ thể", "left")]


def dong_bc(c, s):
    m = c.ma[s]
    b = m.get("bocung") or {}
    return dong({"ma": s, "d2": tile_pct(b.get("dfft_2n")), "g2": tile_pct(b.get("dgia_2n")),
                 "d1": tile_pct(b.get("dfft_1n")), "g1": tile_pct(b.get("dgia_1n")),
                 "pct": pp(g(m, "tuan", "pct3y")), "ct": ct_bc(c, s)},
                sort={"d2": so_num(b.get("dfft_2n")), "g2": so_num(b.get("dgia_2n")), "d1": so_num(b.get("dfft_1n")),
                      "g1": so_num(b.get("dgia_1n")), "pct": so_num(g(m, "tuan", "pct3y"))},
                mau={"g2": mau_dau(b.get("dgia_2n")), "g1": mau_dau(b.get("dgia_1n"))},
                tag={"ma": dm_tag(m)}, link=s)


def ct_bc(c, s):
    """D6.6 — 'nhãn · bậc'; xung đột '⚠ xung đột'; chưa nhãn '—' (không bao giờ 'trung tính')."""
    ct = ct_of(c, s)
    if ct.get("xung_dot"):
        return "⚠ xung đột"
    n = loai_chu_the(ct.get("nhan"))
    return (n + (" · " + ct["bac"] if ct.get("bac") else "")) if n else CO


def v_bocung(c):
    lech = ds_lech(c)
    co = [s for s in c.members if s not in lech and so_num(g(c.ma, s, "bocung", "dfft_2n")) is not None
          and so_num(g(c.ma, s, "bocung", "dgia_2n")) is not None]
    pts = [{"x": round(c.ma[s]["bocung"]["dfft_2n"] * 100, 2), "y": round(c.ma[s]["bocung"]["dgia_2n"] * 100, 2),
            "label": s, "mau": O2N_MAU.get(c.ma[s]["bocung"].get("o_2n"), "dim")} for s in co]
    sc = {"type": "scatter", "title": "Bo cung 2 năm — ΔFFT 2N × Δ giá 2N · %s" % c.scope,
          "sub": "%d/%d mã đủ 130 tuần%s · xanh = BO CUNG · đỏ = XẢ HÀNG · xám = còn lại" % (
              len(co), len(c.members), " · loại cũ/chờ CA: " + lech_chu(c, lech) if lech else ""),
          "height": 380, "x_label": "ΔFFT 2N (%)", "y_label": "Δ giá 2N (%)", "points": pts,
          "quadrants": {"tl": "BO CUNG · giá ↑ FFT ↓", "br": "XẢ HÀNG · giá ↓ FFT ↑", "tr": "SÓNG THƯỜNG",
                        "bl": "[CẦN DATA]"}}
    o2n = lambda s: g(c.ma, s, "bocung", "o_2n")  # noqa: E731
    bo = sorted([s for s in co if o2n(s) == "BO CUNG"], key=lambda s: (c.ma[s]["bocung"]["dfft_2n"], s))[:12]
    xa = sorted([s for s in co if o2n(s) == "XẢ HÀNG"], key=lambda s: (-c.ma[s]["bocung"]["dfft_2n"], s))[:12]
    note = ghi("Công thức (v1.7 [M]:218–240)",
               "ΔFFT 2N = TB FFT tuần 26 tuần gần nhất ÷ TB FFT tuần cùng 26 tuần của 2 năm trước − 1; "
               "Δ giá 2N = giá tuần này ÷ giá 104 tuần trước − 1. 1N (EST) chỉ để xác nhận.<br>"
               "Ô trái–dưới: bản gốc không định danh — cấm tự đặt tên.", "Phương pháp", "dim")
    b1 = bang("bo_cung", "Bo cung — giá ↑ FFT ↓ (top 12)", COT_BC, [dong_bc(c, s) for s in bo], "sắp ΔFFT 2N tăng dần")
    b2 = bang("xa_hang", "Xả hàng — giá ↓ FFT ↑ (top 12)", COT_BC, [dong_bc(c, s) for s in xa], "sắp ΔFFT 2N giảm dần")
    tat = bang("", "", COT_BC, [dong_bc(c, s) for s in sorted(co, key=lambda s: (c.ma[s]["bocung"]["dfft_2n"], s))])
    return {"title": "Bo cung 2N — %s" % c.scope, "sub": "Chu trình: cổ bo cung = FFT giảm trong khi giá tăng",
            "blocks": [sc, b1, b2, note], "data": phang(tat)}


# ───────────────────────────── 5 · xephang ─────────────────────────────

def bk_ten(b):
    return BUCKET_TEN.get(b, CO)


def v_xephang(c):
    t = lambda s, k: g(c.ma, s, "tuan", k)  # noqa: E731
    lech = ds_lech(c)
    co = [s for s in c.members if s not in lech and so_num(t(s, "pct3y")) is not None]
    can = sorted(co, key=lambda s: (t(s, "pct3y"), s))[:10]
    phan = sorted(co, key=lambda s: (-t(s, "pct3y"), s))[:10]
    lech = sorted([s for s in co if (so_num(t(s, "lech_cua_so")) or 0) < 0],
                  key=lambda s: (t(s, "lech_cua_so"), s))[:10]
    fmt = lambda s: "%s P%s (all P%s · ×P10 %s)" % (s, pp(t(s, "pct3y")), pp(t(s, "pall")), boi(t(s, "x_p10")))  # noqa
    dt = c.lk.get("doi_trang_thai") or {}
    ds = [d for d in (dt.get("ds") or []) if isinstance(d, dict) and d.get("ma") in c.members]
    # Danh sách rỗng → rows [] (C++ đánh số MỌI hàng rồi tự vẽ "—" khi 0 hàng); lý do giữ chỗ nằm ở tiêu đề,
    # không thành hàng "1. (chưa có …)".
    doi_tt = "Đổi trạng thái vs tuần trước"
    if not dt.get("tuan_truoc"):
        doi, doi_tt = [], doi_tt + " · chưa có ảnh chụp tuần trước"
    elif not ds:
        doi, doi_tt = [], doi_tt + " · không mã nào đổi lớp FFT (P3Y) / Ô 8 tuần"
    else:
        doi = ["%s %s → %s · P%s → P%s%s" % (d["ma"], bk_ten(d.get("bucket_truoc")), bk_ten(d.get("bucket")),
                                             pp(d.get("pct3y_truoc")), pp(d.get("pct3y")),
                                             " · %s → %s" % (d.get("o8_truoc") or CO, d.get("o8") or CO)
                                             if d.get("o8_truoc") != d.get("o8") else "") for d in ds]
    lists = {"type": "lists", "items": [
        {"title": "Cạn cung nhất · P 3 năm", "rows": [fmt(s) for s in can], "mau": "bull"},
        {"title": "Phân phối nhất · P 3 năm", "rows": [fmt(s) for s in phan], "mau": "bear"},
        {"title": "Lệch cửa sổ lớn nhất · 3Y thấp hơn all",
         "rows": ["%s 3Y P%s vs all P%s (%s)" % (s, pp(t(s, "pct3y")), pp(t(s, "pall")), so(t(s, "lech_cua_so"), 0))
                  for s in lech], "mau": "amber"},
        {"title": doi_tt, "rows": doi, "mau": "info"}]}
    cols = [cot("ma", "Mã", "left"), cot("bt", BUCKET_NHAN + " tuần trước", "left"), cot("b", BUCKET_NHAN, "left"),
            cot("ot", "Ô 8 tuần trước", "left"), cot("o", "Ô 8 tuần", "left"), cot("pt", "pct3Y trước"),
            cot("p", "pct3Y"), cot("xp", "×P10")]
    rows = [dong({"ma": d["ma"], "bt": bk_ten(d.get("bucket_truoc")), "b": bk_ten(d.get("bucket")),
                  "ot": d.get("o8_truoc") or CO, "o": d.get("o8") or CO, "pt": pp(d.get("pct3y_truoc")),
                  "p": pp(d.get("pct3y")), "xp": boi(t(d["ma"], "x_p10"))},
                 sort={"pt": so_num(d.get("pct3y_truoc")), "p": so_num(d.get("pct3y")), "xp": so_num(t(d["ma"], "x_p10"))},
                 mau={"b": VIEN.get(d.get("bucket"), "")}, tag={"ma": dm_tag(c.ma[d["ma"]])}, link=d["ma"]) for d in ds]
    d = dem_nhan(c)
    cap = T.XH_CAPTION.format(n=d["N"] - d["a"] - d["b"] - d["k"], N=d["N"])
    b = bang("doi_trang_thai", "Đổi trạng thái chi tiết", cols, rows,
             "so ảnh chụp tuần %s" % dmy(dt.get("tuan_truoc")) if dt.get("tuan_truoc") else "chưa có ảnh chụp tuần trước",
             " ".join(x for x in (cap, str(dt.get("ghi_chu") or ""), "Loại khỏi xếp hạng (cũ / chờ CA): %s." %
                                  lech_chu(c, lech) if lech else "") if x))
    cols_d = [cot("ma", "Mã", "left"), cot("p", "pct3Y"), cot("pa", "Pall"), cot("l", "Lệch cửa sổ"),
              cot("xp", "×P10"), cot("b", BUCKET_NHAN, "left")]
    data = phang(bang("", "", cols_d, [{"ma": s, "p": pp(t(s, "pct3y")), "pa": pp(t(s, "pall")),
                                        "l": so(t(s, "lech_cua_so"), 0, True), "xp": boi(t(s, "x_p10")),
                                        "b": bk_ten(t(s, "bucket"))} for s in xep(c, "pct3y")]))
    return {"title": "Xếp hạng percentile — %s" % c.scope,
            "sub": "%s · pct 3Y = vị trí TB 4 tuần trong 156 tuần FFT thô (0 = cạn nhất) · lệch cửa sổ = P3Y − Pall" % cap,
            "blocks": [lists, b], "data": data}


# ───────────────────────────── 6 · thitruong ─────────────────────────────

def tiles_ro(b, tt):
    n, tong, _ = phu_ro(tt)
    return [the("%s · MARKET FFT TUẦN" % b, fftp(tt.get("mfft")), "tuần kết thúc %s · %s tuần từ 2020" % (
                dm(tt.get("week_end")), pp(tt.get("n_tuan"))), "", bac_ro(tt, False)),
            the_mfft("%s · TB 4 TUẦN" % b, tt, fftp(tt.get("ma4")), "%s 3Y · toàn dải %s · 4 tuần trước %s" % (
                P(tt.get("pct3y")), P(tt.get("pall")), P(tt.get("pct3y_4t_truoc")))),
            the("%s · P10 / P90 3Y" % b, "%s / %s" % (fftp(tt.get("p10_3y")), fftp(tt.get("p90_3y"))),
                "cửa sổ %s tuần" % pp(tt.get("n_3y")), "", bac_ro(tt, False)),
            the_mfft("%s · SỐ MÃ CÓ FF" % b, tt, "%s/%s" % (pp(n), pp(tong)),
                     "trung vị pct 3Y %s · cạn cung %s · phân phối %s · %s mã có pct 3Y" % (
                         P(tt.get("trung_vi_pct3y")), pp(tt.get("n_can_cung")), pp(tt.get("n_phan_phoi")),
                         pp(tt.get("n_co_du_lieu"))), hang=True)]


# ───────────────────────────── dải P10/P90 + chú thích chart (DELTA v3 · V3.2–V3.4) ─────────────────────────────
# Chỉ ĐỊNH VỊ điểm trên chuỗi bridge đã tính (so ma4 với p10/p90 cuộn cùng tuần, tìm max/min) — không tính lại công
# thức §2. Chữ chú thích là mẫu cố định, không văn xuôi, không khuyến nghị.

GOP_MS = 6 * 7 * 86400000  # V3.4.2 — sự kiện cùng loại cách sự kiện trước < 6 tuần thì bỏ
MAX_VAO, VAO_UU_TIEN_1 = 8, 4  # giữ ≤8 lần vào vùng gần nhất; 4 lần gần nhất có nhãn ưu tiên 1
# QA hình v3: vào lại CÙNG vùng ≤13 tuần sau lần vào đã có nhãn → chỉ marker + tooltip (uu_tien 3), tránh cụm nhãn
# "Vào vùng …" lặp khi TB4 dao động quanh ngưỡng.
TACH_NHAN_MS = 13 * 7 * 86400000
VUNG = {"duoi": ("Vào vùng cạn cung", "Rời vùng cạn cung", "tri_down", "bull", "below"),
        "tren": ("Vào vùng phân phối", "Rời vùng phân phối", "tri_up", "bear", "above")}


def band(name, mau, y_lo=None, y_hi=None, alpha=0.16):
    """V3.2 — series style 'band': vùng giữa y_lo và y_hi; thiếu y_lo → lo_min (đáy trục), thiếu y_hi → hi_max."""
    b = {"name": name, "style": "band", "axis": "left", "mau": mau, "alpha": alpha,
         "lo_min": y_lo is None, "hi_max": y_hi is None}
    if y_lo is not None:
        b["y_lo"] = y_lo
    if y_hi is not None:
        b["y_hi"] = y_hi
    return b


def dai_p(y):
    """V3.4.1 — hai dải thay hai đường 'P10 3Y'/'P90 3Y' (chuỗi cuộn của bridge). Dải ≥P90 kéo tới đỉnh trục nên
    phủ phần lớn vùng vẽ (cả vùng giá trục phải) → tô nhạt hơn dải ≤P10 để line và giá vẫn nổi."""
    return [band("Vùng cạn cung (≤P10 3Y)", "bull", y_hi=y.get("p10", [])),
            band("Vùng phân phối (≥P90 3Y)", "bear", y_lo=y.get("p90", []), alpha=0.10)]


def thang(s):
    """'2026-09-18' / '2026-09' → '09/2026'."""
    d = ngay(s) or ngay(str(s or "")[:7] + "-01")
    return d.strftime("%m/%Y") if d else CO


def diem(x, y, text, sub="", tip="", marker="dot", mau="dim", pos="above", uu_tien=2, axis="left"):
    return {"kind": "point", "x": x, "y": y, "axis": axis, "marker": marker, "mau": mau, "text": text, "sub": sub,
            "tip": tip, "pos": pos, "uu_tien": uu_tien}


def tip_tuan(t, y, i):
    """'tuần dd/mm/yyyy · TB4 … · P10 … · P90 … · giá …' — thành phần không có trong chuỗi thì bỏ."""
    v = {k: (y.get(k) or [None] * len(t))[i] for k in ("m", "p10", "p90", "c")}
    p = ["tuần %s" % dmy(t[i]), "TB4 %s" % fftp(v["m"])]
    p += ["%s %s" % (k.upper(), fftp(v[k])) for k in ("p10", "p90") if v[k] is not None]
    return " · ".join(p + (["giá %s" % gia(v["c"])] if v["c"] is not None else []))


def su_kien_vung(x, t, y):
    """V3.4.2 — vào/rời vùng theo TB4 so P10/P90 cuộn cùng tuần: duoi (ma4 ≤ p10) · tren (ma4 ≥ p90) · giua.
    Rời vùng Z rồi vào lại Z trong < 6 tuần = vẫn ở trong vùng (gộp, bỏ cả hai); sau đó bỏ sự kiện cùng loại cách sự
    kiện trước < 6 tuần. Giữ ≤8 lần vào gần nhất (4 gần nhất ưu tiên 1) + lần rời tương ứng (ưu tiên 3); lần vào lại
    cùng vùng ≤13 tuần sau lần vào có nhãn trước đó chỉ còn marker + tooltip (ưu tiên 3)."""
    m, lo, hi = (y.get(k) or [None] * len(t) for k in ("m", "p10", "p90"))
    raw, prev = [], None
    for i in range(len(t)):
        if m[i] is None or lo[i] is None or hi[i] is None:
            continue
        st = "duoi" if m[i] <= lo[i] else ("tren" if m[i] >= hi[i] else "giua")
        if prev is not None and st != prev:
            raw.append((i, "vao", st) if st in VUNG else (i, "roi", prev))
        prev = st
    gop = []
    for e in raw:
        if e[1] == "vao" and gop and gop[-1][1:] == ("roi", e[2]) and x[e[0]] - x[gop[-1][0]] < GOP_MS:
            gop.pop()
            continue
        gop.append(e)
    ev, cuoi = [], {}
    for e in gop:
        if e[1:] in cuoi and x[e[0]] - x[cuoi[e[1:]]] < GOP_MS:
            continue
        cuoi[e[1:]] = e[0]
        ev.append(e)
    vao = [k for k, e in enumerate(ev) if e[1] == "vao"][-MAX_VAO:]
    sat, truoc = set(), {}  # sat = lần vào lại cùng vùng ≤13 tuần sau lần vào có nhãn trước đó
    for k in vao:
        i, _, z = ev[k]
        if z in truoc and x[i] - x[truoc[z]] <= TACH_NHAN_MS:
            sat.add(k)
        else:
            truoc[z] = i
    out = []
    for r, k in enumerate(reversed(vao)):
        i, _, z = ev[k]
        ten_vao, ten_roi, mk, mau, pos = VUNG[z]
        out.append(diem(x[i], m[i], ten_vao, thang(t[i]), ten_vao + " · " + tip_tuan(t, y, i), mk, mau, pos,
                        3 if k in sat else (1 if r < VAO_UU_TIEN_1 else 2)))
        for j, loai, z2 in ev[k + 1:]:
            if (loai, z2) == ("vao", z):
                break
            if (loai, z2) == ("roi", z):
                out.append(diem(x[j], m[j], ten_roi, thang(t[j]), ten_roi + " · " + tip_tuan(t, y, j), "dot", "dim",
                                "above", 3))
                break
    return out


def diem_nay(x, t, y, text, sub, nhan=""):
    """V3.4.3 — điểm hiện tại (tuần cuối có TB4): thoi amber, nhãn bên trái, ưu tiên 1."""
    m = y.get("m") or []
    i = next((k for k in range(len(m) - 1, -1, -1) if m[k] is not None), None)
    if i is None or i >= len(x):
        return []
    return [diem(x[i], m[i], text, sub, (nhan + " · " if nhan else "") + tip_tuan(t, y, i), "diamond", "amber",
                 "left", 1)]


def nay_ro(b, x, t, y, tt, ngan=False):
    """Điểm hiện tại của Market FFT rổ b (tt = thi_truong.<b>); ngan → chart Zoom (hai rổ chung trục)."""
    return diem_nay(x, t, y, "%s: TB4 %s · %s/3Y" % ("%s nay" % b if ngan else "Nay", fftp(tt.get("ma4")),
                                                     P(tt.get("pct3y"))),
                    "toàn dải %s" % P(tt.get("pall")) if ngan else "P10 %s · P90 %s · toàn dải %s" % (
                        fftp(tt.get("p10_3y")), fftp(tt.get("p90_3y")), P(tt.get("pall"))), b)


def ann_chuoi(x, t, y, tu, bc):
    """Chart FFT × Giá của mã: điểm hiện tại · vào/rời vùng (V3.4.2–3) · đỉnh/đáy giá 2N (V3.4.4) · hai cửa sổ bo cung
    2N (V3.4.5, bỏ khi thiếu dữ liệu 2N)."""
    out = diem_nay(x, t, y, "Nay: TB4 %s · %s/3Y" % (fftp(tu.get("ma4")), P(tu.get("pct3y"))),
                   "×P10 %s · Lớp FFT: %s" % (so(tu.get("x_p10"), 2), BUCKET_TEN.get(tu.get("bucket"), CO)),
                   "tuần dở dang %s phiên" % pp(tu.get("so_phien_tuan")) if tu.get("do_dang") else "")
    out += su_kien_vung(x, t, y)
    c = y.get("c") or []
    n = len(c)
    w = [i for i in range(n - 104, n) if c[i] is not None] if n >= 104 else []
    if w:
        for i, ten, pos in ((max(w, key=c.__getitem__), "cao", "above"), (min(w, key=c.__getitem__), "thấp", "below")):
            out.append(diem(x[i], c[i], "%s giá 2N %s" % ("Đỉnh" if ten == "cao" else "Đáy", gia(c[i])), thang(t[i]),
                            "Giá đóng cửa tuần %s nhất trong 104 tuần gần nhất (giá điều chỉnh) · tuần %s" % (
                                ten, dmy(t[i])), "dot", "dim", pos, 2, "right"))
    if n >= 130 and so_num(bc.get("dfft_2n")) is not None:
        tip = ("Bo cung 2N (v1.7 [M]:218–240): ΔFFT 2N = TB FFT tuần 26 tuần gần (t−25…t) ÷ TB FFT tuần nền "
               "(t−129…t−104) − 1 · Giá 2N = giá t ÷ giá t−104 − 1 · ΔFFT 2N %s · Giá 2N %s · Ô: %s (v1.7)" % (
                   tile_pct(bc.get("dfft_2n")), tile_pct(bc.get("dgia_2n")), bc.get("o_2n") or CO))
        out += [{"kind": "xband", "x0": x[a], "x1": x[b], "mau": "amber", "alpha": 0.06, "text": ten, "tip": tip}
                for a, b, ten in ((n - 26, n - 1, "26 tuần gần"), (n - 130, n - 105, "Nền 2N trước"))]
    return out


# ── cổ đông (Toàn Vũ): mốc QUAN SÁT, Δ so mốc quan sát liền trước (V3.4.6–10) ──

NGUONG_CD = 0.20  # |Δ cổ đông| giữa hai mốc quan sát liền nhau thì gắn chú thích


def ms_ky(ky):
    """'2025-06' → epoch ms ngày 01/06/2025 (trục x của chart cổ đông); kỳ hỏng → None."""
    m = re.match(r"(\d{4})-(\d{2})", str(ky or ""))
    try:
        return ms(date(int(m.group(1)), int(m.group(2)), 1)) if m else None
    except ValueError:
        return None


def thang_so(ky):
    return int(ky[:4]) * 12 + int(ky[5:7])


def quan_sat_cd(moc):
    """Mốc QUAN SÁT theo kỳ (tệp cũ chưa phân kiểu mốc: mốc không nội suy)."""
    co_kieu = any(m.get("kieu") for m in moc)
    return [m for m in moc if so_num(m.get("co_dong")) is not None and ms_ky(m.get("ky")) is not None and
            (m.get("kieu") == "quan_sat" if co_kieu else not m.get("noi_suy"))]


def bien_dong_cd(moc):
    """[(mốc, mốc quan sát liền trước, Δ)] — mốc nội suy/chép không tính."""
    q = quan_sat_cd(sorted([m for m in moc if isinstance(m, dict)], key=lambda m: str(m.get("ky"))))
    return [(b, a, b["co_dong"] / a["co_dong"] - 1) for a, b in zip(q, q[1:]) if a["co_dong"] > 0]


def vline_cd(cdm, x0, x1):
    """V3.4.6 — vạch dọc trên chart FFT × Giá tại mốc quan sát có |Δ| ≥ 20% (tối đa 6 mốc lớn nhất trong khung)."""
    ev = [e for e in bien_dong_cd(g(cdm, "moc") or []) if abs(e[2]) >= NGUONG_CD and x0 <= ms_ky(e[0]["ky"]) <= x1]
    ev = sorted(sorted(ev, key=lambda e: -abs(e[2]))[:6], key=lambda e: e[0]["ky"])
    return [{"kind": "vline", "x": ms_ky(b["ky"]), "mau": "cyan", "text": "CĐ %s" % tile_pct(d, 0), "sub": thang(b["ky"]),
             "tip": "Số cổ đông %s → %s (%s) · kỳ %s → %s · Toàn Vũ SS-T3, bậc mã %s · mốc nội suy không tính" % (
                 so(a["co_dong"], 0), so(b["co_dong"], 0), tile_pct(d, 0), a["ky"], b["ky"], cdm.get("bac") or CO),
             "style": "dash", "uu_tien": 2} for b, a, d in ev]


def ann_codong(cdm):
    """V3.4.7–9 — chart 'Số cổ đông × giá mốc': mốc cuối (CF / lớp) · đỉnh/đáy 2N (cửa sổ 24 tháng trên mốc quan sát,
    neo = mốc quan sát cuối như fft_codong) · Δ ≥20% (hoặc top-5 |Δ|). Hai chú thích trùng một mốc → gộp một nhãn."""
    moc = sorted([m for m in g(cdm, "moc") or [] if isinstance(m, dict) and ms_ky(m.get("ky")) is not None and
                  so_num(m.get("co_dong")) is not None], key=lambda m: m["ky"])
    if not moc:
        return []
    bac, out, theo = cdm.get("bac") or CO, [], {}

    def them(m, a):
        cu = theo.get(id(m))
        if cu is None:
            theo[id(m)] = a
            out.append(a)
            return
        cu["sub"] = " · ".join(s for s in (cu["sub"], a["text"]) if s)
        cu["tip"] = " | ".join(s for s in (cu["tip"], a["tip"]) if s)
        cu["uu_tien"] = min(cu["uu_tien"], a["uu_tien"])
        hang_mk = ("none", "dot", "diamond", "tri_down", "tri_up")  # tam giác Δ cổ đông thắng chấm đỉnh/đáy
        if hang_mk.index(a["marker"]) > hang_mk.index(cu["marker"]):
            cu["marker"] = a["marker"]
            if cu["mau"] == "dim":  # chấm đỉnh/đáy trung tính nhận màu của tam giác Δ (amber tăng · cyan giảm)
                cu["mau"] = a["mau"]

    q = quan_sat_cd(moc)
    while len(q) >= 2 and q[-1]["co_dong"] == q[-2]["co_dong"]:
        q.pop()  # đuôi trùng số (CF) — neo là mốc quan sát cuối có số mới
    cuoi, cf, lop = moc[-1], int(so_num(cdm.get("cf_so_ky")) or 0), cdm.get("lop")
    if cf >= 2:
        them(cuoi, diem(ms_ky(cuoi["ky"]), cuoi["co_dong"], "CF×%d — chưa có số mới" % cf,
                        "mốc quan sát cuối %s" % thang(cdm.get("ky_quan_sat_cuoi")),
                        "Số cổ đông mốc cuối bằng mốc trước %d kỳ — chưa có số mới (không phải 'không đổi'); không tính "
                        "Δ kỳ cuối, không tính k · bậc %s" % (cf, bac), "none", "warn", "left", 1))
    goc = (q[-1] if q else None) if cf >= 2 else cuoi
    if lop in LOP_TEN and goc is not None:
        k, oc = so_num(cdm.get("k_cuoi")), cdm.get("o_cap")
        them(goc, diem(ms_ky(goc["ky"]), goc["co_dong"],
                       "Bùng nổ %s từ đáy 2N" % tile_pct(cdm.get("vs_day"), 0) if lop == "bung_no" else "Đặc lại ở đáy 2N",
                       "k %s · %s" % (so(k, 0), cdm.get("k_nhan") or CO) if k is not None else thang(goc["ky"]),
                       "%s · vs đáy 2N %s · vs đỉnh 2N %s (mốc quan sát) · bậc %s%s" % (
                           LOP_TEN[lop], tile_pct(cdm.get("vs_day")), tile_pct(cdm.get("vs_dinh")), bac,
                           " · Ô cặp cuối: %s" % oc if oc and oc != CO else ""),
                       "none", "amber" if lop == "bung_no" else "cyan", "left", 1))
    win = [m for m in q if thang_so(m["ky"]) >= thang_so(q[-1]["ky"]) - 24] if q else []
    if len(win) >= 2:
        for m, ten in ((max(win, key=lambda v: v["co_dong"]), "Đỉnh"), (min(win, key=lambda v: v["co_dong"]), "Đáy")):
            them(m, diem(ms_ky(m["ky"]), m["co_dong"], "%s CĐ 2N %s" % (ten, so(m["co_dong"], 0)), thang(m["ky"]),
                         "%s số cổ đông trong cửa sổ 2N (mốc quan sát %s → %s) · bậc %s" % (
                             ten, win[0]["ky"], win[-1]["ky"], bac), "dot", "dim", "above", 2))
    ev = [e for e in bien_dong_cd(moc) if e[2] != 0]
    lon = [e for e in ev if abs(e[2]) >= NGUONG_CD] or sorted(ev, key=lambda e: -abs(e[2]))[:5]
    hang = {id(e[0]): r for r, e in enumerate(sorted(lon, key=lambda e: -abs(e[2])))}
    for b, a, d in sorted(lon, key=lambda e: e[0]["ky"]):
        gb = gia(so_num(b.get("gia")))
        them(b, diem(ms_ky(b["ky"]), b["co_dong"], "%s CĐ" % tile_pct(d, 0), "%s · giá %s" % (thang(b["ky"]), gb),
                     "Số cổ đông %s → %s (%s) · kỳ %s → %s · giá mốc %s đồng (danh nghĩa, chưa điều chỉnh CA) · "
                     "Toàn Vũ, bậc %s" % (so(a["co_dong"], 0), so(b["co_dong"], 0), tile_pct(d, 0), a["ky"], b["ky"],
                                          gb, bac),
                     "tri_up" if d > 0 else "tri_down", "amber" if d > 0 else "cyan", "above",
                     2 if hang[id(b)] < 4 else 3))
    return out


def chart_ro(b, doc, mau_tb4, tt=None):
    x, t, y = cat_chuoi(doc)
    return {"type": "chart", "kind": "line", "title": "Market FFT %s — tuần" % b,
            "sub": "Σ KL tuần ÷ Σ free float (thành viên hiện tại có FF) · dải ≤P10 / ≥P90 3Y cuộn · %s → %s" % (
                dmy(t[0] if t else None), dmy(t[-1] if t else None)),
            "height": 640, "x": x, "left": {"label": "Market FFT %/tuần", "min": 0},
            "series": dai_p(y) + [ve("FFT tuần", "left", "thin", "dim", y.get("f", [])),
                                  ve("TB 4 tuần", "left", "line", mau_tb4, y.get("m", []))],
            "annotations": nay_ro(b, x, t, y, tt or {}) + su_kien_vung(x, t, y)}


def v_thitruong(c):
    blocks, tiles, thieu_ = [], [], []
    for b in ("VN30", "VN100"):
        tiles += tiles_ro(b, g(c.lk, "thi_truong", b) or {})
    blocks.append({"type": "tiles", "items": tiles})
    docs = {b: c.chuoi("_" + b) for b in ("VN100", "VN30")}
    for b, mau in (("VN100", "amber"), ("VN30", "info")):
        if docs[b]:
            blocks.append(chart_ro(b, docs[b], mau, g(c.lk, "thi_truong", b) or {}))
        else:
            thieu_.append("fft_chuoi/_%s.json" % b)
    if docs["VN100"] and docs["VN30"]:
        x, t, y = cat_chuoi(docs["VN100"], 157)
        m30 = dict(zip(docs["VN30"].get("t") or [], docs["VN30"].get("m") or []))
        y30 = {"m": [so_num(m30.get(d)) for d in t]}
        # Hai rổ chung trục: chỉ điểm hiện tại của mỗi rổ (không dải/sự kiện — dải của một rổ trên chart hai rổ
        # dễ bị đọc thành so mức VN30 với VN100).
        blocks.append({"type": "chart", "kind": "line", "title": "Zoom 3 năm — VN100 vs VN30, TB 4 tuần",
                       "sub": "157 tuần gần nhất · mỗi rổ đọc theo percentile của chính nó, không so mức",
                       "height": 600, "x": x, "left": {"label": "TB 4 tuần %/tuần", "min": 0},
                       "series": [ve("VN100 · TB 4 tuần", "left", "line", "amber", y.get("m", [])),
                                  ve("VN30 · TB 4 tuần", "left", "line", "info", y30["m"])],
                       "annotations": nay_ro("VN100", x, t, {"m": y.get("m", [])}, g(c.lk, "thi_truong", "VN100") or {},
                                             True) +
                                      nay_ro("VN30", x, t, y30, g(c.lk, "thi_truong", "VN30") or {}, True)})
    if thieu_:
        blocks.append(ghi("Thiếu chuỗi", "Chưa có %s — chạy `python3 goi_fft.py fft_langkinh` trong "
                          "_System/fincept_bridge." % ", ".join(thieu_), "Thiếu", "warn"))
    blocks.append(ghi("Cảnh báo cố định", "Rổ hiện tại áp ngược — percentile lịch sử không cùng mẫu khi thành phần rổ "
                      "đổi (DATA_SOURCES #5).<br>Chỉ so percentile giữa VN30 và VN100, không so mức.<br>Market FFT = "
                      "Σ KL ÷ Σ free float (trọng số free float), không phải trung bình/trung vị FFT từng mã "
                      "(v1.7 [M]:94–112).<br>" + T.R5 + "<br>" + T.MUC_EST, "Bắt buộc", "warn"))
    cols = [cot("b", "Rổ", "left"), cot("w", "Tuần"), cot("f", "Market FFT (EST)"), cot("m", "TB 4 tuần (EST)"),
            cot("p10", "P10 3Y (EST)"), cot("p90", "P90 3Y (EST)"), cot("p", "pct3Y"), cot("pa", "Pall"),
            cot("p4", "pct3Y 4 tuần trước"), cot("n", "Số mã có FF")]
    rows = []
    for b in ("VN30", "VN100"):
        tt = g(c.lk, "thi_truong", b) or {}
        rows.append({"b": b, "w": dmy(tt.get("week_end")), "f": fftp(tt.get("mfft")), "m": fftp(tt.get("ma4")),
                     "p10": fftp(tt.get("p10_3y")), "p90": fftp(tt.get("p90_3y")), "p": pp(tt.get("pct3y")),
                     "pa": pp(tt.get("pall")), "p4": pp(tt.get("pct3y_4t_truoc")),
                     "n": "%s/%s" % tuple(pp(x) for x in phu_ro(tt)[:2])})
    return {"title": "Market FFT — VN30 · VN100", "sub": "Pillar V · chuỗi tuần của chính rổ, trọng số free float",
            "blocks": blocks, "data": phang(bang("", "", cols, rows))}
