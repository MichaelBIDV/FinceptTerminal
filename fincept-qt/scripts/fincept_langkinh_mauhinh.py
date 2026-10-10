#!/usr/bin/env python3
"""
Fincept Terminal — Mẫu hình giá Nguyễn Trần Hải (thấu kính NTH) cho LangKinhPanel, layout "hoso".

Chỉ ĐỌC: data/lk_mauhinh/<MÃ>.json + data/lk_mauhinh/_tong.json (engine mẫu hình dựng — hợp đồng lk_mauhinh/1 và
lk_mauhinh_tong/1), data/lk_hoso/<MÃ>.json (tên/ngành nếu có), state/vc_lk/<MÃ>/price-history.json (giá điều chỉnh để
vẽ — dự phòng gap-chart.json). Env LK_MAUHINH_DIR đổi thư mục mẫu hình (fixture khi engine chưa chạy). Không gọi mạng,
không nhận diện lại: mọi trạng thái, neo, hộp, điều kiện là của engine; view chỉ xếp, đếm, định dạng và kiểm luật hiển thị.
View: mauhinh [VN30|VN100|VN200] → trang vũ trụ; mauhinh <MÃ> → trang mã. khoi_ho_so(t, ma, hs) → mục của hồ sơ.
Luật bằng chứng (METHODOLOGY v1.7 §3.8):
- Cả thấu kính SS-T3. Nhận diện chỉ từ giá/KL → tên mang hậu tố '?'. Không ghi đè Δ cổ đông thật, không đổi A/B/C/D.
- Trăng soi bóng nước chỉ bỏ '?' khi có Δ cổ đông thật (30 mã Toàn Vũ, mốc không CF, không số tròn); ngoài tập đó →
  'Trăng soi bóng nước? — thiếu Pillar I'.
- Xác suất tác giả (Điền hồ 65–75%, Gờ giảm tốc 70–80%) = SS-T3, quan sát ở nước ngoài, chưa kiểm ở VN.
- Tham số 'TG P…' chỉ khi bản ghi nói; còn lại EST (số của skill không có trong bản ghi cũng là EST).
- Không lời mua/bán: engine chỉ nói 'điểm gãy của thesis là …'; chữ engine có từ hành động → ẩn + [CẦN DATA].
- Không nhìn trước: tu ≤ «Hình thành · biết lúc» ≤ «Trạng thái từ» ≤ phiên cuối; lệch → [CẦN DATA].
Thiết kế 23/09 (nth_a3_design): hai nhãn ngày thống nhất («Hình thành · biết lúc» / «Trạng thái từ» — đọc được engine
cũ lẫn engine có trang_thai_tu); một đơn vị giá trên trang mã (nghìn đồng, chuỗi điều chỉnh — chữ engine theo đồng được
đổi); trang vũ trụ: sơ đồ 8 hình trước, rồi 8 nhóm bảng theo mẫu, kiểm định với ví dụ tác giả cuối; hộp engine trên chart
là một series có tên (dải tô) + một mục chú giải mỗi hộp; lịch sử thêm Số phiên + Biến động (EST, không phải xác suất).
Sửa 24/09 (final_ar + final_ad): Biến động tô theo hướng luận điểm engine ghi (thiếu → xám); «Giữ (phiên)» + «Đóng vì»;
tiêu đề lịch sử nói bảng cho thấy gì; bảng vũ trụ một dòng mỗi mã mỗi mẫu (+n thẻ, max_rows 25); cảnh báo phân bổ đầu
trang vũ trụ; lời vị thế trong chữ engine đổi sang chữ trung tính (trung_tinh), sót lại thì ẩn.
Stdlib only; Python 3.11 và 3.14.
"""
import bisect
import math
import os
import re
from collections import Counter

import fincept_langkinh_chuthe as CT
from fincept_langkinh_base import CO, cot, dm, dmy, dong, g, ms, ngay, pt, so, so_num
from fincept_langkinh_hoso_base import (RE_MA, SCOPES, Trang, doc, dong_b, e, gk, hau_to, note_can, sec, trong_tv,
                                        tuoi_tep, viet)
from fincept_langkinh_mauhinh_chu import (HUONG_CHU, MAU, NHAN_HT, NHAN_TTT, NOTE_GIO_LUA, NOTE_LUAT, PHIEN_DAU,  # noqa
                                          SO_DO, SONG, TEN, RE_NGHIN, THU_TU_TT, TT, canh_bao_pb, cot_lich_su, dg_gon,
                                          doi_chu_dong, doi_gia_cau, dong_vi, huong_thesis, ket_qua, mau_bien_dong,
                                          nganh_ngan, ngay_hinh_thanh, ngay_trang_thai, nhan_ca, note_phan_bo, so_viet,
                                          tach_hq, thay_so, tieu_lich_su, trung_tinh, dem_phan_bo, dem_hoi_quy)

N_BIEN = 40  # phiên vẽ thêm trước/sau cửa sổ mẫu (EST — chỉ để nhìn bối cảnh)
CHI_SO = ("VNINDEX",)  # engine quét chỉ số theo ĐIỂM (gap-chart) — không chia 1000, không gọi là giá nghìn đ
MAU_HOP = ("blue", "violet", "grey")  # màu hộp engine trên chart (tránh amber = giá, down = mức gãy)
MAX_DONG = 25  # bảng vũ trụ mỗi mẫu: hiện 25 dòng đầu, còn lại sau nút «Hiện thêm N dòng» (LkTableBlock max_rows)
# Lời hành động / vị thế trong chữ engine (§7.7 spec engine, final_ar #3) — whitelist cụm mô tả: "lệnh mua", "bên mua",
# "bên bán", ngành "Bán lẻ". Chạy SAU trung_tinh: chữ vị thế đã biết được đổi trước, sót lại thì ẩn.
RE_HANH_DONG = re.compile(r"(?<!lệnh )(?<!bên )\b(?:mua|bán)\b(?! lẻ)|\b(?:gom|xả|chốt lời|cắt lỗ|dừng lỗ|giải ngân|tất tay|"
                          r"all[- ]in|vào lệnh|đặt lệnh|đã bắt|giá vào|mức cắt|vị thế|mất hàng|đã đầu tư)\b", re.I)
RE_NGUON_TG = re.compile(r"^\s*TG\s+(P\d.*)$")
CAP_KQ = ("Giữ (phiên) = số phiên thẻ mở, từ «%s» tới phiên engine đóng thẻ; Biến động = giá điều chỉnh đóng cửa hai "
          "phiên đó (Vietcap, FACT-T2), engine đã ghi số đo kết quả thì dùng số của engine. Màu Biến động theo hướng luận "
          "điểm engine ghi: thesis giảm thì số âm là xanh (đi đúng hướng), thesis tăng thì số dương là xanh; engine chưa "
          "ghi hướng → xám. Thống kê trong mẫu (EST), không phải xác suất, không phải kết quả giao dịch." % NHAN_HT)
# Tên điều kiện có số ≥ 1000 KHÔNG phải mức giá (Δ cổ đông, KL, độ dài hộp theo phiên) — không đổi sang nghìn đồng.
RE_KHONG_GIA = re.compile(r"cổ đông|\bKL\b|độ dài|\(phiên", re.I)


# ───────────────────────────── đọc tệp ─────────────────────────────

def thu_muc(t):
    return os.environ.get("LK_MAUHINH_DIR") or os.path.join(t.c.dir, "lk_mauhinh")


def doc_mh(t, ma):
    return doc(os.path.join(thu_muc(t), ma + ".json")) if RE_MA.match(ma or "") else None


def doc_gia(t, ma):
    """Giá đóng cửa theo phiên [(ngày, điều chỉnh nghìn đ, bảng nghìn đ)] từ cache Vietcap (chỉ đọc) và nhãn nguồn.
    Chỉ số (CHI_SO): điểm, giữ nguyên thang."""
    goc = os.path.join(t.goc, "state", "vc_lk", ma)
    chia = 1.0 if ma in CHI_SO else 1000.0
    for ep, k_dc, k_bang in (("price-history", "closePriceAdjusted", "closePrice"), ("gap-chart", "c", "c")):
        d = doc(os.path.join(goc, ep + ".json"))
        du = (d or {}).get("du_lieu")
        if not isinstance(du, dict) or not isinstance(du.get("cot"), list):
            continue
        cot_ = du["cot"]
        if "tradingDate" not in cot_ or k_dc not in cot_:
            continue
        i_d, i_a, i_b = cot_.index("tradingDate"), cot_.index(k_dc), cot_.index(k_bang)
        rows = []
        for h in du.get("hang") or []:
            d0, a, b = str(h[i_d])[:10], so_num(h[i_a]), so_num(h[i_b])
            if ngay(d0) and a:
                rows.append((d0, a / chia, (b or a) / chia))
        if rows:
            rows.sort()
            return rows, {"ep": ep, **((d or {}).get("meta") or {})}
    return [], {}


# ───────────────────────────── luật hiển thị ─────────────────────────────

def nhan_an_toan(m, tv30):
    """Tên hiển thị theo luật bằng chứng — engine đã gắn '?' thì giữ; thiếu thì view gắn (giá/KL → '?')."""
    ten = str(m.get("nhan") or TEN.get(m.get("id")) or m.get("ten") or CO)
    if m.get("id") == "trang_soi":
        if not tv30:
            return ten if "?" in ten else "%s? — thiếu Pillar I" % ten
        return ten
    return ten if "?" in ten else ten + "?"


def sach(s):
    """Chữ engine cho ô bảng / tooltip: lời vị thế đã biết → chữ trung tính; còn lời hành động → ẩn (không ghi sổ)."""
    s = trung_tinh(viet(s or ""))
    return "[CẦN DATA] — chữ của engine có từ hành động, đã ẩn" if RE_HANH_DONG.search(s) else s


def sach_chu(s, t, khoa):
    """Chữ engine: lời vị thế đã biết → chữ trung tính; còn lời hành động → ẩn + sổ CẦN DATA."""
    s = trung_tinh(viet(s or ""))
    if RE_HANH_DONG.search(s):
        t.thieu.append((khoa, "chữ của engine có từ hành động — đã ẩn, chờ engine viết lại dạng «điểm gãy của thesis là …»"))
        return "[CẦN DATA] — chữ của engine có từ hành động, đã ẩn"
    return s


def muc_chu(v, ma):
    """Một mức giá đã quy về nghìn đồng điều chỉnh (VN-Index: điểm) → '55,98 nghìn đ' / '1.094,30 điểm' — khoảng
    trắng không ngắt (NBSP) để ô bảng 880px không tách số khỏi đơn vị."""
    return "%s\u00a0điểm" % so(v, 2) if ma in CHI_SO else "%s\u00a0nghìn\u00a0đ" % gk(v)


class Thang:
    """Thang giá của một trang mã: f(v, ngày) → nghìn đồng điều chỉnh (chỉ số: điểm); nd(v) = f tại phiên cuối (mức
    engine đều theo chuỗi điều chỉnh tới phiên cuối); dong = engine ghi theo ĐỒNG → chữ engine cần đổi."""

    def __init__(self, quy, t_cuoi, ma, px=None):
        self.f, self.don, self.chon = quy
        self.t_cuoi, self.ma, self.px = t_cuoi, ma, px
        self.dong = str(self.chon).startswith("dong") and ma not in CHI_SO

    def nd(self, v):
        return self.f(v, self.t_cuoi)

    def chu(self, s):
        return doi_chu_dong(s) if self.dong else str(s or "")

    def cau_gia(self, s):
        if self.ma in CHI_SO:
            return doi_gia_cau(s, chi_so=True)
        return doi_gia_cau(s) if self.dong else str(s or "")

    def la_gia(self, x, ten="", rng=None):
        """Số x (thang engine) là MỨC GIÁ? > 0, ≥ 1000, tên điều kiện không phải cổ đông/KL/số phiên, và nằm trong
        [min/4, max×4] các mức neo/hộp của chính thẻ (thẻ dài: giá xa giá hiện tại) — không có thì so giá đóng cửa."""
        if x < 1000 or RE_KHONG_GIA.search(ten or ""):
            return False
        if rng:
            return rng[0] / 4 <= x <= rng[1] * 4
        return bool(self.px) and 0.25 < self.nd(x) / self.px < 4


def diem_gay_chu(m, t, ma, th=None):
    """'Điểm gãy của thesis là …' — mức của engine (đồng, chuỗi điều chỉnh) đổi ngay trong câu sang nghìn đồng."""
    dg = m.get("diem_gay") if isinstance(m.get("diem_gay"), dict) else {}
    mo = sach_chu(dg.get("mo_ta"), t, "%s.mauhinh.diem_gay" % ma)
    if not mo:
        return "[CẦN DATA] — engine chưa ghi điểm gãy"
    if not mo.lower().startswith(PHIEN_DAU.lower()):
        mo = "%s %s" % (PHIEN_DAU, mo[0].lower() + mo[1:])
    mo = mo[0].upper() + mo[1:]
    muc = so_num(dg.get("muc"))
    if muc is not None and th is not None:
        moi = muc_chu(th.nd(muc), ma)
        mo = thay_so(mo, muc, moi) or ("%s (mức %s)" % (mo, moi) if moi not in mo else mo)
    elif muc is not None:
        mo += " (mức %s)" % so(muc, 2)
    if th is not None:
        mo = th.cau_gia(mo)
    return mo + (" · nguồn %s" % nguon_chu(dg.get("nguon")) if dg.get("nguon") else "")


def nguon_chu(n):
    """Nguồn tham số của engine → chữ người đọc, GIỮ phần giải thích: 'TG P2:620-623 · …' → 'Tác giả (SS-T3) · P2:620-623
    · …'; 'EST proxy · …' → 'EST · proxy (khác đại lượng tác giả) · …'; 'EST · …' giữ nguyên; nguồn khác (skill SK§3 …)
    → 'EST (… — không truy được trong bản ghi)'."""
    s = sach(str(n or "").strip())
    if s.startswith("[CẦN DATA]"):
        return s
    m = RE_NGUON_TG.match(s)
    if m:
        return "Tác giả (SS-T3) · %s" % m.group(1)
    if s.upper().startswith("EST PROXY"):
        return "EST · proxy (khác đại lượng tác giả)" + s[len("EST proxy"):]
    if s.upper().startswith("EST") or not s:
        return s or "EST"
    return "EST (%s — không truy được trong bản ghi)" % s


def xs_chu(m):
    x = m.get("xac_suat_tg") if isinstance(m.get("xac_suat_tg"), dict) else None
    if not x or not x.get("v"):
        return "Tác giả không nêu xác suất bằng số cho mẫu này."
    return "%s · %s · %s" % (x["v"], x.get("b") or "SS-T3", x.get("g") or "quan sát thị trường nước ngoài, chưa kiểm VN")


def kiem_biet_luc(m, t, ma, t_cuoi):
    """tu ≤ Hình thành · biết lúc ≤ Trạng thái từ ≤ phiên cuối — lệch là dấu hiệu nhìn trước hoặc dữ liệu hỏng."""
    khoa = "%s.mauhinh.%s" % (ma, m.get("id"))
    tu, ht, ttt, cuoi = ngay(m.get("tu")), ngay(ngay_hinh_thanh(m)), ngay(ngay_trang_thai(m)), ngay(t_cuoi)
    if ht is None:
        t.thieu.append((khoa, "thiếu ngày «%s»" % NHAN_HT))
        return
    moc = [x for x in (tu, ht, ttt, cuoi) if x is not None]
    if moc != sorted(moc):
        t.thieu.append((khoa, "thứ tự ngày lệch (mẫu từ %s · %s %s · %s %s · phiên cuối %s) — nghi nhìn trước" % (
            dmy(m.get("tu")), NHAN_HT.lower(), dmy(ngay_hinh_thanh(m)), NHAN_TTT.lower(), dmy(ngay_trang_thai(m)),
            dmy(t_cuoi))))


def ngay_nhan(m):
    """Chữ hai ngày của một thẻ: 'Hình thành · biết lúc dd/mm/yyyy · Trạng thái từ dd/mm/yyyy' (bỏ vế sau khi thẻ còn
    đang hình thành và hai ngày trùng)."""
    ht, ttt = ngay_hinh_thanh(m), ngay_trang_thai(m)
    s = "%s %s" % (NHAN_HT, dmy(ht))
    if ttt and (ttt != ht or m.get("trang_thai") != "dang_hinh_thanh"):
        s += " · %s %s" % (NHAN_TTT, dmy(ttt))
    return s


def so_ngay(s):
    d = ngay(s)
    return int(d.strftime("%Y%m%d")) if d else 0


def tt_pill(tt):
    ten, mau = TT.get(tt, (tt or CO, "grey"))
    return ten, mau


def so_do_item(ma_id, ten=None, trang_thai="", ghi_chu=None):
    sd = SO_DO.get(ma_id)
    if not sd:
        return None
    return {"id": ma_id, "ten": e(ten or TEN.get(ma_id, ma_id)), "trang_thai": trang_thai, "diem": sd["diem"],
            "nhan": sd["nhan"], "hop": sd["hop"],
            "ghi_chu": ghi_chu if ghi_chu is not None else "%s <i>(%s)</i>" % (e(sd["nhan_dien"]), e(sd["nguon"]))}


# ───────────────────────────── quy đổi thang giá của engine ─────────────────────────────

def bo_quy_doi(ds_mau, gia):
    """Engine ghi giá theo thang nào (đồng hay nghìn đồng · giá bảng hay điều chỉnh)? Chọn thang khớp nhất với giá đóng
    cửa tại ngày của các điểm neo; → (hàm (v, ngày) → nghìn đồng điều chỉnh, hàm v → nghìn đồng theo thang engine)."""
    ngays = [d for d, _, _ in gia]
    theo = {d: (a, b) for d, a, b in gia}

    def tai(d):
        i = bisect.bisect_right(ngays, str(d)[:10]) - 1
        return theo[ngays[i]] if i >= 0 else (theo[ngays[0]] if ngays else (None, None))

    def he(d):
        a, b = tai(d)
        return a / b if a and b else 1.0

    cach = {"nghin_dc": (lambda v, d: v, 1.0), "dong_dc": (lambda v, d: v / 1000.0, 1000.0),
            "nghin_bang": (lambda v, d: v * he(d), 1.0), "dong_bang": (lambda v, d: v / 1000.0 * he(d), 1000.0)}
    mau = [(so_num(n.get("gia")), n.get("ngay")) for m in ds_mau for n in m.get("diem_neo") or []
           if isinstance(n, dict) and so_num(n.get("gia")) and ngay(n.get("ngay"))]
    chon = "nghin_bang"
    if mau and gia:
        def loi(k):
            ds = sorted(abs(math.log(max(1e-9, cach[k][0](v, d)) / max(1e-9, tai(d)[0]))) for v, d in mau)
            return ds[len(ds) // 2]
        chon = min(cach, key=loi)
    elif gia:
        tv = sorted(so_num(h.get(k)) for m in ds_mau for h in m.get("hop") or [] for k in ("lo", "hi")
                    if isinstance(h, dict) and so_num(h.get(k)))
        chon = "dong_bang" if tv and tv[len(tv) // 2] > 50 * sorted(a for _, a, _ in gia)[len(gia) // 2] else chon
    f, chia = cach[chon]
    return f, (lambda v: v / chia), chon


# ───────────────────────────── trang mã ─────────────────────────────

def ms_ms(s):
    d = ngay(s)
    return ms(d) if d else None


def hop_chart(h, j, x, f):
    """Một hộp engine → (series có tên — dải tô [tu, den] × [lo, hi], hoặc vạch đứt khi lo = hi —, mục chú giải, nhãn
    tên trên góc hộp). Hộp ngoài khung vẽ → None."""
    if not isinstance(h, dict) or not ngay(h.get("tu")) or not ngay(h.get("den")):
        return None
    lo, hi = so_num(h.get("lo")), so_num(h.get("hi"))
    trong = [h["tu"] <= d <= h["den"] for d in x]
    if not any(trong) or (lo is None and hi is None):
        return None
    ten, mau = sach(h.get("ten") or "Hộp"), MAU_HOP[j % len(MAU_HOP)]
    if lo is not None and hi is not None and hi > lo:
        s = {"name": ten, "style": "band", "mau": mau, "alpha": 0.13,
             "y_lo": [round(f(lo, d), 3) if k else None for d, k in zip(x, trong)],
             "y_hi": [round(f(hi, d), 3) if k else None for d, k in zip(x, trong)]}
        y_nhan = s["y_hi"]
    else:
        v = hi if hi is not None else lo
        s = {"name": ten, "style": "dash", "mau": mau, "y": [round(f(v, d), 3) if k else None for d, k in zip(x, trong)]}
        y_nhan = s["y"]
    i0 = trong.index(True)
    lo_s = gk(f(lo, x[i0])) if lo is not None else CO
    hi_s = gk(f(hi, x[i0])) if hi is not None else CO
    ann = {"kind": "point", "x": ms_ms(x[i0]), "y": y_nhan[i0], "marker": "none", "text": ten, "pos": "above",
           "mau": mau, "uu_tien": 2, "tip": "%s (engine, EST) · %s → %s · %s–%s" % (ten, dmy(h["tu"]), dmy(h["den"]),
                                                                                     lo_s, hi_s)}
    return s, {"text": "%s · EST" % ten, "mau": mau, "dash": True}, ann


def chart_mau(t, m, gia, th, chi_so=False):
    """Giá điều chỉnh quanh cửa sổ mẫu ±N_BIEN phiên; neo (marker/vline, ngày ghi trên nhãn); mỗi hộp một series có
    tên + một mục chú giải; mức gãy vẽ từ phiên «Hình thành · biết lúc» (trước đó mức chưa tồn tại)."""
    ngays = [d for d, _, _ in gia if d <= (th.t_cuoi or "9999")]
    if not ngays or not ngay(m.get("tu")):
        return {"type": "note", "pill": "CẦN DATA", "mau": "bear", "title": "Không có chuỗi giá để vẽ",
                "text": "[CẦN DATA] — thiếu giá Vietcap của mã hoặc ngày bắt đầu mẫu."}
    f = th.f
    i0 = max(0, bisect.bisect_left(ngays, m["tu"]) - N_BIEN)
    i1 = min(len(ngays), bisect.bisect_right(ngays, m.get("den") or ngays[-1]) + N_BIEN)
    x = ngays[i0:i1]
    y = [round(a, 3) for d, a, _ in gia[i0:i1]]
    ms_ = {d: i for i, d in enumerate(x)}
    ser = [{"name": "VN-Index" if chi_so else "Giá điều chỉnh", "style": "line", "mau": "amber", "y": y}]
    leg = [{"text": "VN-Index đóng cửa (điểm) · FACT-T2" if chi_so else "Giá điều chỉnh (nghìn đ) · FACT-T2",
            "mau": "amber"}]
    ann = []
    for j, h in enumerate(m.get("hop") or []):
        kq = hop_chart(h, j, x, f)
        if kq:
            ser.append(kq[0])
            leg.append(kq[1])
            ann.append(kq[2])
    ht = ngay_hinh_thanh(m) or m.get("tu")
    muc = so_num(g(m, "diem_gay", "muc"))
    if muc is not None:
        v = round(f(muc, x[-1]), 3)
        ser.append({"name": "Mức gãy", "style": "dash", "mau": "down", "y": [v if d >= ht else None for d in x]})
        leg.append({"text": "Mức gãy %s · EST" % muc_chu(v, "VNINDEX" if chi_so else ""), "mau": "down", "dash": True})
    co_ht = False
    for n in m.get("diem_neo") or []:
        if not isinstance(n, dict) or n.get("ngay") not in ms_:
            continue
        v = so_num(n.get("gia"))
        tip = th.chu(sach(n.get("mo_ta") or ""))
        if n.get("loai") == "vline":
            la_ht = str(n.get("ten") or "").startswith("Hình thành")
            co_ht = co_ht or la_ht
            txt = "%s %s" % (NHAN_HT, dm(n["ngay"])) if la_ht else "%s · %s" % (n.get("ten") or CO, dm(n["ngay"]))
            ann.append({"kind": "vline", "x": ms_ms(n["ngay"]), "text": txt, "mau": "dim", "style": "dot", "uu_tien": 1,
                        "tip": tip})
        else:
            txt = "%s%s" % (n.get("ten") or CO, " · %s%s" % (gk(th.don(v)), " (giá bảng)" if th.chon.endswith("bang")
                                                            else "") if v is not None else "")
            ann.append({"kind": "point", "x": ms_ms(n["ngay"]), "y": y[ms_[n["ngay"]]], "marker": "dot", "text": txt,
                        "pos": "above", "mau": "amber", "uu_tien": 1, "tip": tip})
    if not co_ht and ht in ms_:
        ann.append({"kind": "vline", "x": ms_ms(ht), "text": "%s %s" % (NHAN_HT, dm(ht)), "mau": "dim", "style": "dash",
                    "uu_tien": 2, "tip": "phiên đầu tiên đủ dữ liệu để nhận ra mẫu (không nhìn trước)"})
    return {"type": "chart", "x": x, "left": {"label": "Điểm" if chi_so else "Giá (nghìn đ)"}, "series": ser,
            "annotations": ann, "legend": leg, "height": 320}


def khoang_the(m):
    """(min, max) các mức giá neo + hộp của một thẻ, thang engine — để nhận ra số nào trong bảng điều kiện là giá."""
    v = [so_num(n.get("gia")) for n in m.get("diem_neo") or [] if isinstance(n, dict)]
    v += [so_num(h.get(k)) for h in m.get("hop") or [] if isinstance(h, dict) for k in ("lo", "hi")]
    v = [x for x in v if x and x > 0]
    return (min(v), max(v)) if v else None


def bang_dk(m, th):
    rows, rng = [], khoang_the(m)
    for d in m.get("dieu_kien") or []:
        if not isinstance(d, dict):
            continue
        dat = d.get("dat")
        thieu = "CẦN DATA" in "%s %s" % (d.get("nguon") or "", d.get("nguong") or "")
        chu, mau = ("đạt", "up") if dat is True else (("chưa", "grey") if dat is False else (
            ("CẦN DATA", "down") if thieu else ("tham chiếu", "grey")))
        ten = sach(d.get("ten") or CO)
        rows.append(dong({"ten": ten, "dat": chu, "gt": gia_tri(d.get("gia_tri"), d.get("nguong"), th, ten, rng),
                          "ng": gia_tri(d.get("nguong"), None, th, ten, rng), "nguon": nguon_chu(d.get("nguon"))},
                         mau={"dat": mau}))
    if not rows:
        return None
    return {"type": "table", "wrap": True, "row_link": False, "rows": rows,
            "caption": "Nguồn tham số: «Tác giả · P…» là ngưỡng bản ghi nói (SS-T3); EST là lựa chọn của engine; proxy "
                       "là đại lượng khác với đại lượng tác giả dùng. Mức giá: %s." % (
                           "điểm VN-Index" if th.ma in CHI_SO else "nghìn đồng trên chuỗi điều chỉnh"),
            "cols": [cot("ten", "Điều kiện", "left"), cot("dat", "Đạt", "left", "tag"), cot("gt", "Giá trị"),
                     cot("ng", "Ngưỡng"), cot("nguon", "Nguồn tham số", "left")]}


def gia_tri(v, nguong=None, th=None, ten="", rng=None):
    """Giá trị điều kiện của engine: mức giá (Thang.la_gia) → nghìn đồng điều chỉnh / điểm; tỷ lệ
    (ngưỡng có '%', |v| ≤ 5) → %; bội (ngưỡng có '×') → ×; số khác kiểu Việt; chữ qua viet() + đổi thang đồng."""
    if isinstance(v, bool):
        return "có" if v else "không"
    x, ng = so_num(v), str(nguong or "")
    if x is not None:
        if th is not None and th.la_gia(x, ten, rng):
            return muc_chu(th.nd(x), th.ma)
        if "%" in ng and abs(x) <= 5 and not float(x).is_integer():
            return pt(x * 100, 1, x < 0 or "+" in ng)
        if float(x).is_integer():
            s_ = so(x, 0)
        else:
            s_ = so(x, 2 if abs(x) < 100 else 1)
            s_ = s_.rstrip("0").rstrip(",") if "," in s_ else s_
        return s_ + ("×" if "×" in ng and abs(x) < 100 else "")
    if v in (None, ""):
        return CO
    if th is None:
        return sach(v)
    s = th.chu(sach(v))
    if th.dong or th.ma in CHI_SO:  # '> 61.612' (ngưỡng 'Rời nền giá') — số trong chữ cũng là mức giá khi la_gia
        s = RE_NGHIN.sub(lambda m: muc_chu(th.nd(so_viet(m.group(1))), th.ma) if th.la_gia(
            so_viet(m.group(1)), ten, rng) else m.group(0), s)
    return s


def khoi_mau(t, ma, m, gia, th, tv30):
    """Một mẫu đang theo dõi: biểu đồ giá + hình lý tưởng + điểm gãy/xác suất + bảng điều kiện."""
    kiem_biet_luc(m, t, ma, th.t_cuoi)
    nhan = nhan_an_toan(m, tv30)
    tt, _ = tt_pill(m.get("trang_thai"))
    tit = "%s — %s · mẫu từ %s · %s" % (nhan, tt, dmy(m.get("tu")), ngay_nhan(m))
    out = [sec(chart_mau(t, m, gia, th, ma in CHI_SO), "Mẫu hình NTH · %s" % TEN.get(m.get("id"), CO), tit,
               "%s Vietcap (FACT-T2) · neo, hộp, trạng thái do engine (EST) · cả thấu kính SS-T3" % (
                   "VN-Index đóng cửa" if ma in CHI_SO else "Giá điều chỉnh, nghìn đồng"), "SS-T3")]
    sd = so_do_item(m.get("id"), nhan, m.get("trang_thai") or "")
    the_ = {"type": "cards", "variant": "box", "items": [
        {"pill": "EST", "pill_mau": "amber", "tieu_de": "Điểm gãy của thesis", "noi_dung": e(diem_gay_chu(m, t, ma, th))},
        {"pill": "SS-T3", "pill_mau": "violet", "tieu_de": "Xác suất theo tác giả", "noi_dung": e(xs_chu(m))},
        {"pill": "SS-T3", "pill_mau": "violet", "tieu_de": "Tác giả nói gì",
         "noi_dung": "%s <i>(%s)</i><br>%s" % (e(SO_DO.get(m.get("id"), {}).get("nhan_dien", CO)),
                                              e(SO_DO.get(m.get("id"), {}).get("nguon", CO)),
                                              e(SO_DO.get(m.get("id"), {}).get("luu_y", "")))}]}
    items = [x for x in ({"type": "sodo", "items": [sd]} if sd else None, the_) if x]
    out.append({"type": "row", "items": items})
    dk = bang_dk(m, th)
    if dk:
        g_ = re.sub(r"\bmo_ta\b", "mô tả điểm neo", hau_to(sach_chu(m.get("g"), t, "%s.mauhinh.g" % ma), tv30))
        dk["caption"] += (" Ghi chú engine: %s." % th.chu(g_).rstrip(".")) if g_ else ""
        out.append(dk)
    return out


def bang_lich_su(ls, tv30, t, ma, gia, th):
    """Thẻ đã đóng: Giữ (phiên) + Biến động (màu theo hướng luận điểm engine ghi) + Đóng vì (engine; thiếu → suy từ
    trạng thái) + điểm gãy gọn (nguồn ở tooltip)."""
    rows = []
    for m in sorted([x for x in ls or [] if isinstance(x, dict)], key=lambda x: str(ngay_hinh_thanh(x) or ""),
                    reverse=True):
        tt, mau = tt_pill(m.get("trang_thai"))
        n, bd, nguon = ket_qua(m, gia)
        huong = huong_thesis(m)
        dv, dv_engine = dong_vi(m)
        dg = g(m, "diem_gay", "mo_ta")
        dg_chu, dg_tip = dg_gon(diem_gay_chu(m, t, ma, th) if dg and not RE_HANH_DONG.search(trung_tinh(viet(dg))) else (
            "[CẦN DATA] — chữ engine đã ẩn" if dg else "[CẦN DATA] — engine chưa ghi điểm gãy"))
        rows.append(dong({"mau": nhan_an_toan(m, tv30), "tt": tt, "ht": dmy(ngay_hinh_thanh(m)),
                          "ttt": dmy(ngay_trang_thai(m)), "giu": so(n, 0) if n is not None else CO,
                          "bd": pt(bd, 1, True) if bd is not None else CO, "dv": dv, "dg": dg_chu},
                         sort={"ht": so_ngay(ngay_hinh_thanh(m)), "ttt": so_ngay(ngay_trang_thai(m)), "giu": n, "bd": bd},
                         mau={"tt": mau, "bd": mau_bien_dong(bd, huong)},
                         tip={"mau": "mẫu từ %s" % dmy(m.get("tu")),
                              "giu": "số phiên thẻ mở: từ «%s» tới phiên engine đóng thẻ %s" % (NHAN_HT, dmy(m.get("den"))),
                              "bd": "%s · %s · EST, %s" % (HUONG_CHU[huong], nguon,
                                                           g(m, "ket_qua", "g") or "thống kê trong mẫu"),
                              "dv": " · ".join(x for x in (
                                  "engine ghi" if dv_engine else "view suy từ trạng thái (engine chưa ghi lý do đóng)",
                                  sach(g(m, "ket_qua", "ha_bac") or "")) if x),
                              "dg": dg_tip}))
    return rows


def dem_song(ds):
    """(đang theo dõi, vừa đóng): engine để cả thẻ vừa gãy/hết hiệu lực trong danh sách hiện hành 'mau'."""
    n = sum(1 for m in ds if isinstance(m, dict) and m.get("trang_thai") in SONG)
    return n, sum(1 for m in ds if isinstance(m, dict)) - n


def the_mh(mh):
    return sorted([m for m in (mh or {}).get("mau") or [] if isinstance(m, dict)],
                  key=lambda m: (THU_TU_TT.get(m.get("trang_thai"), 9), -so_ngay(ngay_trang_thai(m))))


def trang_ma(c, t, ma):
    mh = doc_mh(t, ma)
    hs = t.ho_so(ma) or {}
    lk = g(c.ma, ma) or {}
    ten, nganh = (mh or {}).get("ten") or hs.get("ten") or lk.get("ten"), (mh or {}).get("nganh") or hs.get("nganh")
    tv30 = bool((mh or {}).get("tv30")) if mh else trong_tv(hs)
    gia, gmeta = doc_gia(t, ma)
    t_cuoi = (mh or {}).get("t_cuoi") or (gia[-1][0] if gia else None)
    gia = [r for r in gia if r[0] <= (t_cuoi or "9999")]
    cong = CT.cong_ma(c, ma)
    cong["dong"] = dong_b(cong.get("dong"))
    mau = the_mh(mh)
    pills = [{"text": nhan_an_toan(m, tv30), "mau": tt_pill(m.get("trang_thai"))[1]} for m in mau[:4]]
    px, chg = (gia[-1][2], (gia[-1][1] / gia[-2][1] - 1) * 100 if len(gia) > 1 else None) if gia else (None, None)
    tv_nhan = None if ma in CHI_SO else ("30 mã Toàn Vũ" if tv30 else "ngoài 30 mã Toàn Vũ")
    song, dong_ = dem_song(mau)
    head = {"type": "tkhead", "ma": ma, "eyebrow": " · ".join(x for x in (ten, nganh, tv_nhan) if x),
            "tieu_de": ("%d mẫu hình đang theo dõi%s · %d đã đóng trong 5 năm" % (
                song, " · %d vừa đóng" % dong_ if dong_ else "", len((mh or {}).get("lich_su") or []))
                if mh else "[CẦN DATA] — engine mẫu hình chưa quét mã này"),
            "px": gk(px) if px is not None else "[CẦN DATA]", "b": "FACT-T2" if px is not None else "",
            "chg": pt(chg, 2, True) if chg is not None else "", "pills": pills,
            "cong_ma": "Thấu kính NTH là proxy giá/KL (SS-T3) · mức giá: %s" % (
                "điểm" if ma in CHI_SO else "nghìn đồng trên chuỗi điều chỉnh")}
    blocks = [head]
    if not mh:
        t.thieu.append(("%s.mauhinh" % ma, "engine mẫu hình chưa có tệp của mã này (lk_mauhinh/%s.json)" % ma))
        blocks.append({"type": "note", "pill": "SS-T3", "mau": "dim", "title": "Luật bằng chứng của thấu kính NTH",
                       "text": NOTE_LUAT})
    else:
        th = Thang(bo_quy_doi(list(mau) + list(mh.get("lich_su") or []), gia), t_cuoi, ma,
                   gia[-1][1] if gia else None)
        for m in mau:
            blocks += khoi_mau(t, ma, m, gia, th, tv30)
        if not mau:
            blocks.append(sec({"type": "note", "pill": "SS-T3", "mau": "dim", "title": "Không có mẫu đang theo dõi",
                               "text": "Engine quét tới phiên %s: không có mẫu hình đang hình thành hoặc xác nhận." %
                                       dmy(t_cuoi)}, "Mẫu hình NTH", "Không có mẫu hình đang theo dõi"))
        rows = bang_lich_su(mh.get("lich_su"), tv30, t, ma, gia, th)
        if rows:
            tit, sub = tieu_lich_su(mh.get("lich_su"))
            blocks.append(sec({"type": "table", "wrap": True, "row_link": False, "rows": rows, "caption": CAP_KQ,
                               "cols": cot_lich_su()}, "Lịch sử 5 năm · mẫu đã đóng", tit, sub, "EST"))
        t.thieu += [("%s.mauhinh.%d" % (ma, i + 1), sach(x))
                    for i, x in enumerate(x for x in mh.get("can_data") or [] if isinstance(x, str))]
    blocks.append(sec({"type": "chips", "items": chips_mh(mh, gmeta, gia, ma)}, "Nguồn", "Nguồn của trang mẫu hình",
                      "Màu tag = bậc bằng chứng · 'dữ liệu tới' = ngày dữ liệu của chính nguồn"))
    blocks.append(note_can(t))
    _, tuoi = tuoi_tep((mh or {}).get("tao_luc"), t.now)
    return {"title": "Mẫu hình NTH — %s" % ma, "sub": "Thấu kính Nguyễn Trần Hải · %s Vietcap tới %s" % (
                "VN-Index" if ma in CHI_SO else "giá", dmy(t_cuoi)),
            "blocks": [b for b in blocks if b], "tickers": [ma], "cong": cong,
            "data": [{"01 Mẫu hình": nhan_an_toan(m, tv30), "02 Trạng thái": tt_pill(m.get("trang_thai"))[0],
                      "03 Hình thành": dmy(ngay_hinh_thanh(m)), "04 Trạng thái từ": dmy(ngay_trang_thai(m))}
                     for m in mau]
                    or [{"01 Mục": "Mẫu hình %s" % ma, "02 Giá trị": "không có mẫu đang theo dõi" if mh else "[CẦN DATA]"}],
            "payload": {"layout": "hoso", "as_of": "phiên %s" % dmy(t_cuoi), "tuoi": tuoi if mh else "chưa có tệp mẫu hình"}}


def chips_mh(mh, gmeta, gia, ma=None):
    it = []
    if gia:
        it.append({"b": "FACT-T2", "text": "Vietcap %s — %s tới %s · %s phiên" % (
            gmeta.get("ep") or "price-history", "VN-Index đóng cửa (điểm)" if ma in CHI_SO else "giá điều chỉnh",
            dmy(gia[-1][0]), so(len(gia), 0))})
    if mh:
        it.append({"b": "EST", "text": "Engine mẫu hình (lk_mauhinh) — dựng %s · neo, hộp, trạng thái, tham số EST" % (
            viet(str(mh.get("tao_luc") or CO)[:16].replace("T", " ")))})
    it.append({"b": "SS-T3", "text": "Nguyễn Trần Hải — bản ghi P1 (15/05/2026), P2 (22/05/2026), P3 Khắc kỷ (ngày EST "
                                     "29/05/2026); ASR, trích theo dòng"})
    return it


# ───────────────────────────── trang vũ trụ ─────────────────────────────

class KhoThe:
    """Ngày «Hình thành · biết lúc» cho dòng _tong.bang: engine mới (có trang_thai_tu) → biet_luc của chính dòng;
    engine cũ → đọc thẻ trùng (id, tu, trạng thái, biet_luc) trong tệp mã (đọc mỗi mã một lần)."""

    def __init__(self, t):
        self.t, self.tep = t, {}

    def hinh_thanh(self, ma, m):
        if "trang_thai_tu" in m:
            return m.get("biet_luc")
        if ma not in self.tep:
            self.tep[ma] = doc_mh(self.t, ma) or {}
        khop = (m.get("id"), m.get("tu"), m.get("trang_thai"), m.get("biet_luc"))
        for x in (self.tep[ma].get("mau") or []) + (self.tep[ma].get("lich_su") or []):
            if isinstance(x, dict) and (x.get("id"), x.get("tu"), x.get("trang_thai"), x.get("biet_luc")) == khop:
                return ngay_hinh_thanh(x)
        return m.get("biet_luc")


def bang_nhom(k, ds, kho):
    """Bảng gọn một mẫu, MỘT dòng mỗi mã: thẻ đang theo dõi mới nhất (không có thì thẻ vừa đóng mới nhất — theo «Hình
    thành · biết lúc», rồi «Trạng thái từ»); thẻ khác cùng mẫu của mã → cột «Thẻ khác» '+n thẻ' + tooltip. Mã · Trạng
    thái · Hình thành · Trạng thái từ · Ngành (ngắn); xếp trạng thái rồi «Trạng thái từ» mới nhất; max_rows 25. Nhãn khác
    tên nhóm (Trăng soi thiếu Pillar I, CF) → thêm cột, không bỏ chữ của luật bằng chứng."""
    goc = TEN[k] + "?"
    theo = {}
    for r in ds:
        theo.setdefault(r[0]["ma"], []).append(r)
    chon = []
    for ma, rs in theo.items():
        rs = sorted(rs, key=lambda r: (r[1].get("trang_thai") in SONG, so_ngay(kho.hinh_thanh(ma, r[1])),
                                       so_ngay(ngay_trang_thai(r[1]))), reverse=True)
        chon.append((rs[0], rs[1:]))
    rows = []
    for (x, m, nhan), khac in sorted(chon, key=lambda c: (THU_TU_TT.get(c[0][1].get("trang_thai"), 9),
                                                          -so_ngay(ngay_trang_thai(c[0][1])), c[0][0]["ma"])):
        tt, mau = tt_pill(m.get("trang_thai"))
        ht = kho.hinh_thanh(x["ma"], m)
        if nhan.startswith(goc):
            phu = nhan[len(goc):].strip(" —")
        elif nhan.startswith(TEN[k]):  # engine bỏ '?' — chỉ Trăng soi có Δ cổ đông thật (luật bằng chứng)
            phu = "có Δ cổ đông thật — bỏ «?»" if k == "trang_soi" else (nhan[len(TEN[k]):].strip(" —") or "không «?»")
        else:
            phu = nhan
        phu = phu.replace("thiếu Pillar I", "thiếu") if k == "trang_soi" else phu
        tip_khac = "; ".join("%s · %s %s → %s %s" % (tt_pill(y.get("trang_thai"))[0], NHAN_HT.lower(),
                                                   dmy(kho.hinh_thanh(x["ma"], y)), NHAN_TTT.lower(),
                                                   dmy(ngay_trang_thai(y))) for _, y, _ in khac)
        rows.append(dong({"ma": x["ma"], "tt": tt, "ht": dmy(ht), "ttt": dmy(ngay_trang_thai(m)),
                          "ng": nganh_ngan(x.get("nganh")), "them": "+%d thẻ" % len(khac) if khac else CO,
                          "phu": phu or CO},
                         sort={"ht": so_ngay(ht), "ttt": so_ngay(ngay_trang_thai(m)), "them": len(khac)}, mau={"tt": mau},
                         link=x["ma"],
                         tip={"ma": "%s · %s · mẫu từ %s" % (x.get("ten") or x["ma"], x.get("nganh") or CO,
                                                            dmy(m.get("tu"))), "ng": x.get("nganh") or "",
                              "them": ("Thẻ khác cùng mẫu: " + tip_khac) if khac else ""}))
    cols = [cot("ma", "Mã", "left"), cot("tt", "Trạng thái", "left", "tag"), cot("ht", "Hình thành", "left"),
            cot("ttt", NHAN_TTT, "left"), cot("ng", "Ngành", "left")]
    for khoa, nhan_cot in (("them", "Thẻ khác"), ("phu", "Pillar I" if k == "trang_soi" else "Nhãn")):
        if any(r[khoa] != CO for r in rows):
            cols.append(cot(khoa, nhan_cot, "left"))
        else:
            for r in rows:
                r.pop(khoa, None)
    return {"type": "table", "wrap": True, "row_link": True, "rows": rows, "cols": cols, "max_rows": MAX_DONG}


def trang_vu_tru(c, t, scope):
    tong = doc(os.path.join(thu_muc(t), "_tong.json"))
    bang = [x for x in (tong or {}).get("bang") or [] if isinstance(x, dict) and RE_MA.match(str(x.get("ma") or ""))]
    if scope != "VN200":
        tv = set(c.members or [])
        bang = [x for x in bang if scope in (x.get("ro") or []) or x.get("ma") in tv]
    nhom = {k: [] for k, _ in MAU}
    for x in bang:
        for m in x.get("mau") or []:
            if isinstance(m, dict) and m.get("id") in nhom and m.get("trang_thai") in TT:
                # _tong.bang không mang tv30: chỉ khi engine gọi Trăng soi KHÔNG '?' mới đọc tệp mã để kiểm Toàn Vũ
                tv30 = bool((doc_mh(t, x["ma"]) or {}).get("tv30")) if (
                    m.get("id") == "trang_soi" and "?" not in str(m.get("nhan") or "")) else False
                nhom[m["id"]].append((x, m, nhan_an_toan(m, tv30)))
    ma_song = {x["ma"] for ds in nhom.values() for x, m, _ in ds if m.get("trang_thai") in SONG}
    n_song = sum(1 for ds in nhom.values() for _, m, _ in ds if m.get("trang_thai") in SONG)
    blocks = []
    if not tong:
        t.thieu.append(("mauhinh", "chưa có kết quả engine mẫu hình (lk_mauhinh/_tong.json)"))
    tieu = ("%s thẻ đang theo dõi trên %s mã · quét %s mã" % (so(n_song, 0), so(len(ma_song), 0), so(len(bang), 0))
            if tong else "[CẦN DATA] — engine mẫu hình chưa chạy")
    ma_mau = {k: {x["ma"] for x, m, _ in nhom[k] if m.get("trang_thai") in SONG} for k, _ in MAU}
    if tong:
        blocks.append(note_phan_bo(canh_bao_pb(tong.get("canh_bao_phan_bo"), *dem_phan_bo(nhom, bang, CHI_SO),
                                               tong.get("cum_ngay")), scope))
    sd = []
    for k, ten in MAU:
        ds = nhom[k]
        d = Counter(m.get("trang_thai") for _, m, _ in ds)
        song = d["dang_hinh_thanh"] + d["xac_nhan"]
        dem = ("<b>%d mã · %d thẻ đang theo dõi</b> (%d hình thành · %d xác nhận)%s<br>" % (
            len(ma_mau[k]), song, d["dang_hinh_thanh"], d["xac_nhan"],
            " · %d vừa đóng" % (len(ds) - song) if len(ds) > song else "") if tong else "")
        sdo = SO_DO[k]
        sd.append(so_do_item(k, ten, "", "%s%s <i>(%s)</i>" % (dem, e(sdo["nhan_dien"]), e(sdo["nguon"]))))
    blocks.append(sec({"type": "sodo", "items": sd}, "Thấu kính NTH · hình giá · %s" % scope, tieu,
                      "Tám hình lý tưởng theo lời tác giả (hình vẽ tay, không phải chuỗi giá; trích ngắn, dẫn dòng "
                      "P1/P2/P3) · đếm thẻ của engine (EST) tới phiên %s · %s mã có thẻ đang theo dõi / %s mã quét" % (
                          dmy((tong or {}).get("t_cuoi")), so(len(ma_song), 0), so(len(bang), 0)), "SS-T3"))
    if tong:
        kho, nhom_b = KhoThe(t), []
        for k, ten in MAU:
            ds = nhom[k]
            d = Counter(m.get("trang_thai") for _, m, _ in ds)
            song = d["dang_hinh_thanh"] + d["xac_nhan"]
            tit = "%s — %d mã · %d thẻ đang theo dõi" % (ten + "?", len(ma_mau[k]), song)
            eb = "Mẫu hình NTH · %s" % ten
            if not ds:
                nhom_b.append(sec({"type": "note", "pill": "SS-T3", "mau": "dim", "title": "Không có thẻ",
                                   "text": "Engine không có thẻ %s đang theo dõi hoặc vừa đóng trong rổ %s." % (
                                       e(ten), scope)}, eb, "%s — 0 thẻ" % (ten + "?")))
                continue
            bn = bang_nhom(k, ds, kho)
            nhom_b.append(sec(bn, eb, tit,
                              "Thẻ: %d hình thành · %d xác nhận%s · mỗi mã một dòng (thẻ đang theo dõi mới nhất), «Thẻ "
                              "khác» = thẻ khác cùng mẫu · xếp: xác nhận → hình thành → vừa đóng, rồi «%s» mới nhất%s · "
                              "nhấp đúp mã để mở trang mẫu hình" % (
                                  d["dang_hinh_thanh"], d["xac_nhan"],
                                  " · %d vừa đóng" % (len(ds) - song) if len(ds) > song else "", NHAN_TTT,
                                  " · hiện %d dòng đầu, bấm «Hiện thêm … dòng» để xem hết %d mã" % (
                                      MAX_DONG, len(bn["rows"])) if len(bn["rows"]) > MAX_DONG else ""), "SS-T3"))
        # một cột: hàng đôi (row) làm ô ngắn kéo giãn theo ô dài (đầu mục bị giãn, thẻ trống) — thử 23/09, bỏ
        blocks += nhom_b
    blocks.append({"type": "note", "pill": "SS-T3", "mau": "dim", "title": "Luật bằng chứng của thấu kính NTH",
                   "text": NOTE_LUAT + "<br>• " + e(NOTE_GIO_LUA)})
    blocks.append(note_can(t))
    hq = [(k, v) for k, v in (((tong or {}).get("hoi_quy") or {}).items()) if isinstance(v, dict)]
    if hq:
        blocks.append(bang_hoi_quy(hq, (tong or {}).get("hoi_quy_dem")))
    cong = CT.cong_ro(c)
    cong["dong"] = dong_b(cong.get("dong"))
    _, tuoi = tuoi_tep((tong or {}).get("tao_luc"), t.now)
    return {"title": "Mẫu hình NTH — %s" % scope, "blocks": [b for b in blocks if b],
            "sub": "Thấu kính Nguyễn Trần Hải · %s thẻ đang theo dõi trên %s mã · quét %s mã · tới phiên %s" % (
                so(n_song, 0), so(len(ma_song), 0), so(len(bang), 0), dmy((tong or {}).get("t_cuoi"))),
            "tickers": sorted({x["ma"] for x in bang}), "cong": cong,
            "data": [{"01 Mã": x["ma"], "02 Mẫu hình": " · ".join(nhan_an_toan(m, False) for m in x.get("mau") or []
                                                                    if isinstance(m, dict))}
                     for x in bang] or [{"01 Mục": "Mẫu hình NTH %s" % scope, "02 Giá trị": "[CẦN DATA]"}],
            "payload": {"layout": "hoso", "as_of": "phiên %s" % dmy((tong or {}).get("t_cuoi")),
                        "tuoi": tuoi if tong else "chưa có kết quả engine"}}


def bang_hoi_quy(hq, dem=None):
    """Kiểm định với ví dụ của tác giả (chữ người đọc); tiêu đề đếm ca NGOÀI mẫu, ca trong mẫu xám, xếp cuối."""
    (n_dat, n, tm), rows = dem_hoi_quy(hq, dem), []
    for k, v in sorted(hq, key=lambda kv: kv[0] in tm):  # sorted ổn định: ca trong mẫu xuống cuối, giữ thứ tự còn lại
        ky, thay, dan = (trung_tinh(x) for x in tach_hq(v.get("ghi_chu")))
        dat, trong = bool(v.get("dat")), k in tm
        kv = "Kỳ vọng: %s\nEngine: %s" % (ky, thay) if thay != CO else ky  # engine mới có thể ghi một câu liền
        tip_dat = ("ca trong mẫu — %s; không vào tổng đạt" % (tm[k] or v.get("trong_mau")) if trong else
                   "trượt — lý do ghi ở cột bên (luật EST giữ nguyên)" if "KỲ VỌNG TRƯỢT" in thay.upper() else "")
        rows.append(dong({"ca": viet(v.get("ten")) if v.get("ten") else nhan_ca(k),
                          "dat": ("đạt" if dat else "trượt") + (" · trong mẫu" if trong else ""), "kv": kv},
                         mau={"dat": "grey" if trong else "up" if dat else "down"},
                         tip={"ca": "Dẫn dòng: %s" % dan if dan else "", "dat": tip_dat}))
    tit = "%d/%d ca ngoài mẫu đạt%s — ngưỡng đóng băng trước khi chạy" % (
        n_dat, n, " · %d ca trong mẫu, không tính" % len(tm) if tm else "")
    return sec({"type": "table", "wrap": True, "row_link": False, "rows": rows,
                "caption": "Kỳ vọng ghi và đóng băng trước khi chạy; trượt thì ghi lại, không vặn ngưỡng cho khớp "
                           "(nth_engine_spec §10b). Một ca đạt là khớp trong mẫu của chính tác giả, không phải bằng chứng "
                           "ngoài mẫu. Ca «trong mẫu» là ví dụ đã dùng để chọn ngưỡng EST — không tính vào tổng đạt.",
                "cols": [cot("ca", "Ca · ví dụ của tác giả", "left"), cot("dat", "Kết quả", "left", "tag"),
                         cot("kv", "Kỳ vọng → engine thấy", "left")]},
               "Kiểm định với ví dụ của tác giả", tit, "Nghiệm thu engine (EST) · cả thấu kính SS-T3", "EST")


def v_mauhinh(c):
    t = Trang(c)
    arg = (c.scope or "").strip().upper()
    if arg in SCOPES or not arg:
        return trang_vu_tru(c, t, arg or "VN200")
    if not RE_MA.match(arg):
        arg = "FPT"
    c.scope, c.members = arg, [arg]
    return trang_ma(c, t, arg)


# ───────────────────────────── mục trong hồ sơ ─────────────────────────────

def khoi_ho_so(t, ma, hs):
    """Mục 'Mẫu hình NTH' của hồ sơ: bảng gọn + hình lý tưởng (một hình mỗi mẫu) của các mẫu đang theo dõi. Thiếu tệp
    engine → chỉ một dòng ở sổ CẦN DATA (không block). Không đưa vào pill đầu mã, trigger, ma trận 5 pillar hay
    codong.pattern. Mức giá: nghìn đồng trên chuỗi điều chỉnh như phần còn lại của hồ sơ."""
    mh = doc_mh(t, ma)
    if not mh:
        t.thieu.append(("mauhinh", "engine mẫu hình chưa quét mã này — mục «Mẫu hình NTH» chưa hiện"))
        return []
    tv30 = bool(mh.get("tv30"))
    mau = the_mh(mh)
    eb = "Thấu kính NTH · hình giá (SS-T3 · proxy giá/KL)"
    if not mau:
        return [sec({"type": "note", "pill": "SS-T3", "mau": "dim", "title": "Không có mẫu đang theo dõi",
                     "text": "Engine quét tới phiên %s: không có mẫu hình đang hình thành hoặc xác nhận." %
                             dmy(mh.get("t_cuoi"))}, eb, "Không có mẫu hình NTH đang theo dõi")]
    for m in mau:
        kiem_biet_luc(m, t, ma, mh.get("t_cuoi"))
    gia = doc_gia(t, ma)[0]
    gia = [r for r in gia if r[0] <= (mh.get("t_cuoi") or "9999")]
    th = Thang(bo_quy_doi(mau, gia), mh.get("t_cuoi"), ma, gia[-1][1] if gia else None)
    rows = [dong({"mau": nhan_an_toan(m, tv30), "tt": tt_pill(m.get("trang_thai"))[0],
                  "ht": dmy(ngay_hinh_thanh(m)), "ttt": dmy(ngay_trang_thai(m)), "dg": diem_gay_chu(m, t, ma, th)},
                 mau={"tt": tt_pill(m.get("trang_thai"))[1]}, tip={"mau": "mẫu từ %s" % dmy(m.get("tu"))})
            for m in mau]
    dem = Counter((nhan_an_toan(m, tv30), tt_pill(m.get("trang_thai"))[0]) for m in mau)
    tit = " · ".join("%s%s (%s)" % (n, " ×%d" % k if k > 1 else "", tt) for (n, tt), k in list(dem.items())[:3])
    bang = sec({"type": "table", "wrap": True, "row_link": False, "rows": rows,
                "cols": [cot("mau", "Mẫu hình", "left"), cot("tt", "Trạng thái", "left", "tag"),
                         cot("ht", "Hình thành", "left"), cot("ttt", NHAN_TTT, "left"),
                         cot("dg", "Điểm gãy của thesis", "left")]},
               eb, tit, "Không ghi đè Δ cổ đông, không đổi nhãn A/B/C/D — đọc sau năm pillar. Mức giá nghìn đồng trên "
                        "chuỗi điều chỉnh. Biểu đồ từng mẫu ở view «Mẫu hình NTH» (mauhinh %s). Engine quét tới %s." % (
                            ma, dmy(mh.get("t_cuoi"))), "SS-T3")
    da, sd = set(), []
    for m in mau:  # một hình lý tưởng mỗi mẫu (hai thẻ cùng mẫu không vẽ hai hình giống hệt)
        if m.get("id") in da:
            continue
        da.add(m.get("id"))
        k = sum(1 for x in mau if x.get("id") == m.get("id"))
        x = so_do_item(m.get("id"), nhan_an_toan(m, tv30) + (" ×%d" % k if k > 1 else ""), m.get("trang_thai") or "")
        if x:
            sd.append(x)
    return [bang] + ([{"type": "sodo", "title": "Hình lý tưởng của các mẫu đang theo dõi", "b": "SS-T3",
                       "sub": "Hình vẽ theo mô tả của tác giả — không phải chuỗi giá của %s" % ma, "items": sd}]
                     if sd else [])
