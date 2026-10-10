#!/usr/bin/env python3
"""
Fincept Terminal — chữ tĩnh và bộ đổi chữ của view mẫu hình NTH (fincept_langkinh_mauhinh.py). Tách riêng để mỗi tệp
≤ 800 dòng. Không đọc tệp, không gọi mạng.
- MAU/TEN/TT: tám mẫu và bốn trạng thái của engine; SO_DO: hình lý tưởng + dòng nhận diện của tác giả (dẫn dòng P1/P2/P3).
- ngay_hinh_thanh / ngay_trang_thai: hai ngày của một thẻ, đọc được cả engine cũ (biet_luc = ngày đổi trạng thái cuối,
  ngày hình thành nằm ở vline 'Hình thành…') lẫn engine mới (biet_luc = ngày hình thành, thêm trang_thai_tu).
- doi_chu_dong: chữ engine ghi giá theo ĐỒNG ('giá bảng 111.300', 'DIF −5.012 → −2.140') → nghìn đồng như trục chart.
- viet_hq / nhan_ca / tach_hq: ghi chú hồi quy của engine (repr Python, số chấm thập phân, ngày ISO) → chữ người đọc.
- ket_qua: Giữ (phiên) + Biến động của thẻ đã đóng (engine `ket_qua` trước; thiếu → đếm trên giá điều chỉnh);
  huong_thesis/mau_bien_dong: màu theo hướng luận điểm engine ghi (thiếu → xám); dong_vi: «Đóng vì» (engine trước, thiếu
  → suy từ trạng thái); tieu_lich_su: tiêu đề bảng lịch sử nói bảng cho thấy gì.
- trung_tinh: lời vị thế trong chữ engine ('đáy đã bắt', 'giá vào', 'vùng giá đã đầu tư', 'mất hàng') → chữ trung tính.
- canh_bao_pb: cảnh báo phân bổ (_tong.canh_bao_phan_bo của engine; thiếu → view đếm từ _tong.bang) + cụm ngày neo
  (_tong.cum_ngay).
Stdlib only; Python 3.11 và 3.14.
"""
import bisect
import html
import re
from collections import Counter

from fincept_langkinh_base import CO, cot, dmy, ngay, pt, so, so_num

MAU = (("ngua_dut_day", "Ngựa đứt dây"), ("chan_cau", "Chân cầu"), ("dien_ho", "Điền hồ"), ("mu_sat", "Mũ sắt"),
       ("go_giam_toc", "Gờ giảm tốc"), ("z_xoay", "Z xoay"), ("trang_soi", "Trăng soi bóng nước"),
       ("dam_lay", "Chất tải đầm lầy"))
TEN = dict(MAU)
TT = {"dang_hinh_thanh": ("đang hình thành", "amber"), "xac_nhan": ("xác nhận", "up"), "gay": ("gãy", "down"),
      "het_hieu_luc": ("hết hiệu lực", "grey")}
THU_TU_TT = {"xac_nhan": 0, "dang_hinh_thanh": 1, "gay": 2, "het_hieu_luc": 3}
SONG = ("dang_hinh_thanh", "xac_nhan")
NHAN_HT = "Hình thành · biết lúc"  # phiên đầu đủ dữ liệu để nhận ra mẫu — một nhãn cho mọi chỗ trên trang
NHAN_TTT = "Trạng thái từ"  # phiên trạng thái hiện tại bắt đầu
PHIEN_DAU = "Điểm gãy của thesis là"

NOTE_LUAT = ("• Cả thấu kính là <b>SS-T3</b> (lời Nguyễn Trần Hải, bản ghi ASR). Engine nhận diện chỉ từ giá/KL nên tên "
             "mẫu luôn mang hậu tố <b>?</b>.<br>• Không ghi đè Δ cổ đông thật, không đổi nhãn A/B/C/D của Lăng Kính "
             "(Hard Rule #16); không kết luận «có/không phân phối» từ hình giá.<br>• Trăng soi bóng nước chỉ bỏ «?» khi có "
             "Δ cổ đông thật (30 mã Toàn Vũ, mốc không CF, không số tròn); còn lại «Trăng soi bóng nước? — thiếu Pillar "
             "I».<br>• Xác suất của tác giả (Điền hồ 65–75%, Gờ giảm tốc 70–80%) là quan sát ở nước ngoài, không cỡ mẫu, "
             "chưa kiểm ở VN; các mẫu khác tác giả không nêu số.<br>• Tham số ghi «Tác giả · P…» chỉ khi bản ghi nói; "
             "còn lại là EST của engine (kể cả số của skill không có trong bản ghi).<br>• «Hình thành · biết lúc» = phiên "
             "đầu tiên đủ dữ liệu để nhận ra mẫu — không dùng dữ liệu sau ngày đó; «Trạng thái từ» = phiên trạng thái "
             "hiện tại (xác nhận, gãy, hết hiệu lực) bắt đầu.<br>• Mọi mức giá trên trang mã là nghìn đồng trên chuỗi giá "
             "điều chỉnh Vietcap (FACT-T2); «giá bảng» là giá chưa điều chỉnh, cùng đơn vị nghìn đồng. VN-Index tính "
             "bằng điểm.<br>• Không có lời khuyến nghị giao dịch — engine chỉ nói «điểm gãy của thesis là …»; quy tắc "
             "rủi ro riêng của tác giả (7% của Mũ sắt, 12–15% của Z xoay) chỉ ghi tham chiếu, engine không áp.")
NOTE_GIO_LUA = ("«Gió lùa khai mộ» chỉ có tên, do người dẫn nhắc (P2:1186-1189); tác giả không định nghĩa ở đâu trong "
                "P1–P3 → [CẦN DATA], không cài thành mẫu hình.")

# Hình lý tưởng (0..1, y = 1 là đỉnh khung như trục giá) + dòng nhận diện của tác giả (trích ngắn, dẫn dòng bản ghi P1/P2/P3
# ở langkinh_ai/sources/) — theo nth_engine_spec §6 và nth_inventory; đã sửa theo phản biện: ×5 là của tốc độ lệnh,
# 7% của Mũ sắt là quy tắc rủi ro riêng của tác giả (không đo từ đỉnh), mức điền của Điền hồ là mức ngày tin xấu, không
# vẽ dải 5–7% của Z xoay. 24/09: bỏ lời vị thế (final_ar #3).
SO_DO = {
    "ngua_dut_day": {
        "diem": [[0, .30], [.1, .26], [.2, .31], [.3, .25], [.4, .29], [.5, .24], [.56, .27], [.6, .45], [.7, .50],
                 [.8, .58], [.9, .66], [1, .78]],
        "nhan": [{"i": 7, "text": "phiên khởi điểm"}, {"i": 5, "text": "đáy nền"}],
        "hop": [{"x0": 0, "x1": .56, "y0": .22, "y1": .33, "text": "nền đi ngang"},
                {"x0": 0, "x1": 1, "y0": .185, "y1": .205, "text": "gãy ≈ −7% dưới đáy"}],
        "nhan_dien": "Sau giai đoạn đi ngang chán nản hoặc đi xuống, một phiên đổi đột ngột cả giá, khối lượng và góc "
                     "tăng — tác giả gọi là «phiên khởi điểm»; so cùng dòng ngành, cùng trạng thái thị trường.",
        "nguon": "P1:807-822 · P2:600-716",
        "luu_y": "«5 lần trung bình 20 phiên» tác giả áp cho tốc độ lệnh cùng khung giờ (P2:620-623) — đo bằng KL ngày "
                 "chỉ là proxy EST. Gãy khi phá đáy khoảng 7% (P2:714-716)."},
    "chan_cau": {
        "diem": [[0, .95], [.15, .80], [.32, .60], [.38, .40], [.45, .52], [.56, .18], [.62, .35], [.70, .55],
                 [.8, .62], [1, .70]],
        "nhan": [{"i": 3, "text": "hộp 1 · hỏng"}, {"i": 5, "text": "hộp 2 · phân kỳ MACD"},
                 {"i": 7, "text": "vượt nhịp rơi cuối"}],
        "hop": [{"x0": .34, "x1": .42, "y0": .36, "y1": .46, "text": ""},
                {"x0": .52, "x1": .60, "y0": .14, "y1": .24, "text": ""}],
        "nhan_dien": "Sau đợt giảm dài, giá rơi dữ dội; hộp đầu giống chân cầu nhưng hỏng, hộp sau thành khi MACD «đã "
                     "không phá xuống nữa» và khối lượng tăng vọt.",
        "nguon": "P1:791-803 · P2:382-472, 552-573",
        "luu_y": "Hoàn thành khi giá vượt nhịp rơi mạnh nhất cuối cùng (P2:453-455); ở mức thị trường tác giả thêm RSI "
                 "dưới 30 (P2:558-565)."},
    "dien_ho": {
        "diem": [[0, .80], [.25, .82], [.30, .72], [.38, .40], [.50, .62], [.58, .76], [.7, .88], [1, .92]],
        "nhan": [{"i": 2, "text": "ngày tin xấu"}, {"i": 3, "text": "đáy hồ (rơi ≥30%)"},
                 {"i": 5, "text": "điền lại mức ngày tin xấu"}],
        "hop": [{"x0": .28, "x1": 1, "y0": .71, "y1": .73, "text": "mức ngày tin xấu"}],
        "nhan_dien": "Tin xấu đột ngột làm giá lõm sâu — nhịp rơi thường từ 30% trở lên — rồi giá được kéo lên mạnh, "
                     "«điền lại cùng bằng cái ngày có tin xấu».",
        "nguon": "P1:840-866 · P2:895-998",
        "luu_y": "Xác suất 65–75% là quan sát của tác giả ở Thái Lan, Trung Quốc, Indonesia, Mỹ, Đức (P2:965-973) — "
                 "SS-T3, chưa kiểm ở VN."},
    "mu_sat": {
        "diem": [[0, .30], [.2, .31], [.40, .80], [.55, .60], [.70, .31], [.85, .28], [1, .31]],
        "nhan": [{"i": 2, "text": "đỉnh mũ"}, {"i": 4, "text": "về chân nền"}],
        "hop": [{"x0": 0, "x1": 1, "y0": .29, "y1": .31, "text": "chân nền"},
                {"x0": .45, "x1": .62, "y0": .58, "y1": .64, "text": "TB mũ"}],
        "nhan_dien": "Giá dựng đứng khi có tin tích cực, sườn trái kéo rất nhanh với khối lượng rất lớn, rồi «về lại "
                     "đúng chân nền» — hai cạnh mũ bằng nhau.",
        "nguon": "P1:740-760 · P2:205-298",
        "luu_y": "Mốc 7% là quy tắc rủi ro riêng của tác giả theo O'Neil (P2:219-225) — không đo từ đỉnh, engine không "
                 "áp. Về hoặc phá nền thì chuyển sang theo dõi Trăng soi bóng nước (P2:239-243)."},
    "go_giam_toc": {
        "diem": [[0, .10], [.35, .70], [.40, .78], [.45, .63], [.52, .77], [.58, .62], [.65, .76], [.72, .63],
                 [.78, .75], [.85, .85], [1, .95]],
        "nhan": [{"i": 2, "text": "chạm 1"}, {"i": 8, "text": "chạm cuối · cung cạn"}, {"i": 9, "text": "vượt gờ"}],
        "hop": [{"x0": .36, "x1": .80, "y0": .61, "y1": .79, "text": "biên gờ"}],
        "nhan_dien": "Sau đợt tăng dài với phần trăm lớn, giá lên rồi xuống lặp lại trong một biên; tin cậy khi lực "
                     "cung ở các lần chạm đỉnh cạn dần; vượt gờ thì tốc độ tăng trở lại.",
        "nguon": "P2:1027-1116",
        "luu_y": "Xác suất 70–80% là quan sát của tác giả ở Thái Lan và Mỹ (P2:1112-1116) — SS-T3, chưa kiểm ở VN. Tác "
                 "giả không nêu điểm gãy riêng."},
    "z_xoay": {
        "diem": [[0, .15], [.30, .50], [.38, .46], [.46, .54], [.54, .46], [.62, .54], [.70, .48], [.72, .58], [1, .93]],
        "nhan": [{"i": 0, "text": "A"}, {"i": 1, "text": "B · hết cạnh 1"}, {"i": 7, "text": "C · vào cạnh 3"},
                 {"i": 8, "text": "D"}],
        "hop": [{"x0": .30, "x1": .70, "y0": .45, "y1": .55, "text": "cạnh 2 (gờ)"}],
        "nhan_dien": "Cạnh 1 tăng, gờ giảm tốc là cạnh 2 nằm ngang, cạnh 3 «gần như có tỉ lệ bằng nhau» với cạnh 1; "
                     "cạnh 2 càng dài càng tin cậy.",
        "nguon": "P2:1117-1185",
        "luu_y": "Hỏng khi đi ngang rồi về chân nền cạnh 1 — thành Mũ sắt (P2:1169-1185). Tác giả không nêu xác suất "
                 "bằng số."},
    "trang_soi": {
        "diem": [[0, .30], [.18, .85], [.30, .35], [.40, .20], [.55, .30], [.7, .40], [.85, .48], [1, .55]],
        "nhan": [{"i": 1, "text": "mũ sắt"}, {"i": 3, "text": "đáy sau mũ"}, {"i": 7, "text": "nhịp lên chậm"}],
        "hop": [{"x0": .42, "x1": 1, "y0": .04, "y1": .13, "text": "cần Δ cổ đông giảm"}],
        "nhan_dien": "Sau Mũ sắt, giá từ từ đi lên, nhịp chậm và ngắn; tác giả xác nhận bằng báo cáo «cổ đông tăng "
                     "hay giảm đi».",
        "nguon": "P2:239-243, 1186-1272",
        "luu_y": "Không có Δ cổ đông thật (Pillar I) thì không gọi tên: ngoài 30 mã Toàn Vũ, mốc CF hoặc số tròn → "
                 "«Trăng soi bóng nước? — thiếu Pillar I»."},
    "dam_lay": {
        "diem": [[0, .90], [.08, .70], [.12, .78], [.22, .58], [.26, .64], [.38, .46], [.42, .51], [.55, .34],
                 [.59, .38], [.72, .24], [.76, .27], [.9, .20], [1, .22]],
        "nhan": [{"i": 1, "text": "CC1 ✗"}, {"i": 3, "text": "CC2 ✗"}, {"i": 5, "text": "CC3 ✗"},
                 {"i": 7, "text": "CC4 ✗"}],
        "hop": [],
        "nhan_dien": "Giá «cứ từ từ nó lún xuống»: xuống, hồi rồi xuống; đáy sau thấp hơn đáy trước, thanh khoản cạn "
                     "dần; chân cầu, gờ giảm tốc, phân kỳ MACD đều thất bại.",
        "nguon": "P2:57-62 · P3 @5300-24000",
        "luu_y": "Tác giả không nêu mức kết thúc mẫu bằng số; AMD phải qua 4 lần chân cầu (P3 @19066). P3 là bản Whisper chưa "
                 "đối chiếu phụ đề, ngày phát sóng EST 29/05/2026."},
}

# Ngành (ICB Vietcap trong lk_vutru) → nhãn ngắn cho cột bảng 880px; ngành lạ → cắt ở ' và ' / ' & '.
NGANH_NGAN = {"Bất động sản": "BĐS", "Xây dựng và Vật liệu": "Xây dựng", "Hàng & Dịch vụ Công nghiệp": "Công nghiệp",
              "Dịch vụ tài chính": "DV tài chính", "Thực phẩm và đồ uống": "Thực phẩm",
              "Điện, nước & xăng dầu khí đốt": "Tiện ích", "Tài nguyên Cơ bản": "Tài nguyên",
              "Du lịch và Giải trí": "Du lịch", "Công nghệ Thông tin": "CNTT", "Ô tô và phụ tùng": "Ô tô",
              "Hàng cá nhân & Gia dụng": "Gia dụng"}


def nganh_ngan(s):
    s = str(s or "").strip()
    if not s:
        return CO
    return NGANH_NGAN.get(s) or re.split(r"\s+(?:và|&)\s+|,\s*", s)[0]


# ───────────────────────────── hai ngày của một thẻ ─────────────────────────────

def ngay_hinh_thanh(m):
    """«Hình thành · biết lúc»: engine mới (có khoá trang_thai_tu) → biet_luc; engine cũ (biet_luc = ngày đổi trạng thái
    cuối) → ngày vline 'Hình thành…' trong diem_neo; thiếu cả hai → biet_luc."""
    if "trang_thai_tu" in m:
        return m.get("biet_luc")
    return next((n.get("ngay") for n in m.get("diem_neo") or [] if isinstance(n, dict) and n.get("loai") == "vline"
                 and str(n.get("ten") or "").startswith("Hình thành")), None) or m.get("biet_luc")


def ngay_trang_thai(m):
    """«Trạng thái từ»: engine mới → trang_thai_tu (trống → biet_luc); engine cũ → biet_luc."""
    return (m.get("trang_thai_tu") or m.get("biet_luc")) if "trang_thai_tu" in m else m.get("biet_luc")


# ───────────────────────────── số kiểu Việt · đổi thang đồng → nghìn đồng ─────────────────────────────

def so_viet(s):
    """'−5.012' / '-40,19' / '111.300' → số (kiểu Việt: '.' nghìn, ',' thập phân); lỗi → None."""
    try:
        return float(str(s).replace("−", "-").replace(".", "").replace(",", "."))
    except ValueError:
        return None


def gk_(v):
    """Giá nghìn đồng kiểu Artifact (55,98 · 106,1) — như fincept_langkinh_hoso_base.gk."""
    s = so(v, 2)
    return s[:-1] if s != CO and "," in s and s.endswith("0") else s


SO_V = r"[−-]?\d[\d.]*(?:,\d+)?"
RE_GIA_BANG = re.compile(r"(giá bảng\s*≈?\s*)(%s)(?!\s*nghìn)" % SO_V)
RE_DIF = re.compile(r"(DIF\s+)(%s)(\s*(?:→|>|<|≥|≤)\s*)(%s)" % (SO_V, SO_V))


def doi_chu_dong(s):
    """Chữ engine ghi giá theo ĐỒNG → nghìn đồng (một đơn vị trên trang mã): 'giá bảng 111.300' → 'giá bảng 111,3
    nghìn đ'; 'DIF −5.012 → −2.140' (MACD cùng đơn vị giá) → 'DIF −5,01 → −2,14 (nghìn đ)'."""
    def bang(m):
        v = so_viet(m.group(2))
        return m.group(0) if v is None else "%s%s\u00a0nghìn\u00a0đ" % (m.group(1), gk_(v / 1000.0))

    def dif(m):
        a, b = so_viet(m.group(2)), so_viet(m.group(4))
        if a is None or b is None:
            return m.group(0)
        return "%s%s%s%s (nghìn\u00a0đ)" % (m.group(1), so(a / 1000.0, 2), m.group(3), so(b / 1000.0, 2))
    return RE_DIF.sub(dif, RE_GIA_BANG.sub(bang, str(s or "")))


RE_NGHIN = re.compile(r"(?<![\d.,])([1-9]\d{0,2}(?:\.\d{3})+)(?![\d]|[.,]\d)(?!\s*(?:nghìn|phiên|cp|người|%))")


def doi_gia_cau(s, chi_so=False):
    """Câu điểm gãy của engine (mọi số có dấu chấm nghìn là MỨC GIÁ: '= 71.808', 'chân cạnh 1 (57.194)', 'L* = 40.400')
    → cổ phiếu: đồng → nghìn đồng (kèm doi_chu_dong); chỉ số: giữ số, thêm 'điểm'. Chỉ dùng cho câu điểm gãy."""
    if chi_so:
        return RE_NGHIN.sub(lambda m: "%s\u00a0điểm" % m.group(1), str(s or ""))
    s = doi_chu_dong(s)
    return RE_NGHIN.sub(lambda m: "%s\u00a0nghìn\u00a0đ" % gk_(so_viet(m.group(1)) / 1000.0), s)


def thay_so(chu, v, moi):
    """Thay đúng số v (kiểu Việt, 0 hoặc 2 chữ số lẻ — engine in giá cổ phiếu theo đồng, chỉ số theo điểm có lẻ) trong câu
    bằng `moi`; không có → None. Biên số: không dính chữ số khác."""
    for nd in (0, 2, 1):
        pat = re.compile(r"(?<![\d.,])%s(?![\d]|[.,]\d)" % re.escape(so(v, nd)))
        if pat.search(chu):
            return pat.sub(moi, chu, count=1)
    return None


# ───────────────────────────── kiểm định với ví dụ của tác giả: chữ engine → chữ người đọc ─────────────────────────────

TEN_TT_MAY = {"dang_hinh_thanh": "đang hình thành", "xac_nhan": "xác nhận", "het_hieu_luc": "hết hiệu lực", "gay": "gãy"}
TU_CA = (("go_giam_toc", "Gờ giảm tốc"), ("chan_cau", "Chân cầu"), ("dien_ho", "Điền hồ"), ("mu_sat", "Mũ sắt"),
         ("z_xoay", "Z xoay"), ("trang_soi", "Trăng soi bóng nước"), ("dam_lay", "Chất tải đầm lầy"),
         ("ngua", "Ngựa đứt dây"), ("day_hai", "đáy hai"), ("hop_100_phien", "hộp cạnh 2 ≥ 100 phiên"),
         ("phien", "phiên"), ("covid", "Covid 2020"), ("dau", "đầu"))
TU_KHONG_MA = {w for k, _ in TU_CA for w in k.split("_")}


def _ngay_dmy(y, m, d=None):
    return "%s/%s/%s" % (d, m, y) if d else "%s/%s" % (m, y)


def nhan_ca(khoa):
    """'vnindex_chan_cau_2022_11' → 'VN-Index · Chân cầu · 11/2022'; 'mu_sat_dau_2026_BID' → 'BID · Mũ sắt · đầu
    2026'; 'shb_phien_07_07_2025' → 'SHB · phiên 07/07/2025'; 'vre_dien_ho_covid' → 'VRE · Điền hồ · Covid 2020'."""
    tok = str(khoa or "").split("_")
    cuoi = []
    while tok and tok[-1].isupper() and len(tok[-1]) >= 3:  # mã viết hoa ở cuối khoá
        cuoi.insert(0, tok.pop())
    ma = []
    while tok and (tok[0] == "vnindex" or (len(tok[0]) == 3 and tok[0].isalpha() and tok[0] not in TU_KHONG_MA)):
        x = tok.pop(0)
        ma.append("VN-Index" if x == "vnindex" else x.upper())
    than, ten = "_%s_" % "_".join(tok), []
    for k, t in TU_CA:
        if "_%s_" % k in than:
            than = than.replace("_%s_" % k, "_", 1)
            ten.append(t)
    so_ = [x for x in than.split("_") if x.isdigit()]
    if len(so_) == 3 and len(so_[2]) == 4:
        ngay = _ngay_dmy(so_[2], so_[1], so_[0])
    elif len(so_) == 2 and len(so_[0]) == 4 and len(so_[1]) == 2:
        ngay = _ngay_dmy(so_[0], so_[1])
    else:
        ngay = "–".join(so_)
    for tien_to in ("đầu", "phiên"):  # 'đầu 2026', 'phiên 07/07/2025' — chữ chỉ thời điểm đứng cạnh ngày
        if tien_to in ten and ngay:
            ten.remove(tien_to)
            ngay = "%s %s" % (tien_to, ngay)
    if "Covid 2020" in ten:
        ten.remove("Covid 2020")
        ngay = " ".join(x for x in ("Covid 2020", ngay) if x)
    return " · ".join(x for x in (", ".join(ma + cuoi), " ".join(ten), ngay) if x) or str(khoa or "")


def _so_anh(m):
    """Một số kiểu Anh (chấm thập phân / phẩy nghìn) → kiểu Việt; số kiểu Việt đã có ('21.600') giữ nguyên."""
    dau, tok = m.group(1), m.group(2)
    if re.fullmatch(r"\d{1,3}(?:,\d{3}){2,}", tok):  # 249,760,712 — phẩy nghìn kiểu Anh
        return dau + tok.replace(",", ".")
    if "," in tok or re.fullmatch(r"[1-9]\d{0,2}(?:\.\d{3})+", tok):  # '40,19', '21.600' — đã kiểu Việt
        return dau + tok
    if "." in tok:
        b = tok.split(".", 1)[1]
        return so(float(dau + tok), 0 if set(b) <= {"0"} else len(b))
    if len(tok) >= 5:  # số nguyên dài: 24922 → 24.922 (năm 4 chữ số giữ nguyên)
        return so(float(dau + tok), 0)
    return dau + tok


RE_SO_ANH = re.compile(r"(?<![\w@:.,\-])(-?)(\d+(?:[.,]\d+)*)(?![\d]|[.,]\d)")
RE_TUPLE = re.compile(r"\((-?\d+(?:\.\d+)?),\s*'(\d{4})-(\d{2})-(\d{2})'\)")


def viet_hq(s):
    """Ghi chú hồi quy của engine → chữ người đọc: True/False/None → có/không/—, trạng thái máy → chữ, khoảng ngày ISO
    ('2022-11-07..25', '2025-12..2026-04') → dd/mm/yyyy, số kiểu Anh → kiểu Việt, 'RSI min' → 'RSI thấp nhất'."""
    s = RE_TUPLE.sub(lambda m: "%s (%s/%s/%s)" % (m.group(1), m.group(4), m.group(3), m.group(2)), str(s or ""))
    s = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\.\.(\d{4})-(\d{2})-(\d{2})\b", r"\3/\2/\1–\6/\5/\4", s)
    s = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\.\.(\d{2})-(\d{2})\b", r"\3/\2–\5/\4/\1", s)
    s = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\.\.(\d{2})\b", r"\3–\4/\2/\1", s)
    s = re.sub(r"\b(\d{4})-(\d{2})\.\.(\d{4})-(\d{2})\b", r"\2/\1–\4/\3", s)
    s = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", r"\3/\2/\1", s)
    s = re.sub(r"\bTrue\b", "có", re.sub(r"\bFalse\b", "không", re.sub(r"\bNone\b", CO, s)))
    s = re.sub(r"\b(%s)\b" % "|".join(TEN_TT_MAY), lambda m: TEN_TT_MAY[m.group(1)], s)
    s = s.replace("RSI min", "RSI thấp nhất").replace("ret60", "lợi suất 60 phiên trước")
    return RE_SO_ANH.sub(lambda m: _so_anh(m), s).replace(" -", " −").replace("(-", "(−")


def tach_hq(gc):
    """'kỳ vọng — engine thấy [dẫn dòng]' → (kỳ vọng, engine thấy, dẫn dòng) đã qua viet_hq."""
    s = str(gc or "").strip()
    dan = ""
    m = re.search(r"\s*\[([^\[\]]*)\]\s*$", s)
    if m:
        dan, s = m.group(1), s[:m.start()]
    cat = next((i for i in (m.start() for m in re.finditer(" — ", s)) if s[:i].count("'") % 2 == 0), None)
    ky, thay = (s, "") if cat is None else (s[:cat], s[cat + 3:])  # ' — ' đầu tiên NGOÀI ngoặc '…'
    return viet_hq(ky).strip(), viet_hq(thay).strip() or CO, dan


def dem_hoi_quy(hq, dem=None):
    """Bảng kiểm định (lead 24/09): (số ca ngoài mẫu đạt, số ca ngoài mẫu, {id ca trong mẫu: lý do}) — _tong.hoi_quy_dem của engine trước; thiếu →
    đếm trên hq bỏ ca có cờ trong_mau (engine cũ không có cờ nào → đếm hết)."""
    dem = dem if isinstance(dem, dict) else {}
    ng = dem.get("ngoai_mau") if isinstance(dem.get("ngoai_mau"), dict) else {}
    tm = {x.get("id"): str(x.get("g") or "") for x in dem.get("trong_mau") or [] if isinstance(x, dict)}
    if so_num(ng.get("dat")) is not None and so_num(ng.get("n")) is not None:
        return int(ng["dat"]), int(ng["n"]), tm
    tm = {k: str(v.get("trong_mau")) for k, v in hq if v.get("trong_mau")}
    ngoai = [v for k, v in hq if k not in tm]
    return sum(1 for v in ngoai if v.get("dat")), len(ngoai), tm


# ── kết quả thẻ đã đóng: Giữ (phiên) + Biến động (engine `ket_qua` trước; thiếu → đếm trên giá điều chỉnh)

KQ_N = ("so_phien", "n_phien", "phien")
KQ_BD = ("bien_dong", "bien_dong_pct", "thay_doi", "thay_doi_pct", "loi_suat", "ret", "pct")


def _phang(o, tien=""):
    """{'gia': {'pct': 1}} → {'gia_pct': 1, 'pct': 1}; nguyên tử So {v, u} giữ nguyên để đọc đơn vị."""
    out = {}
    for k, v in (o or {}).items():
        if isinstance(v, dict) and "v" not in v:
            for k2, v2 in _phang(v).items():
                out.setdefault(k2, v2)
                out.setdefault("%s_%s" % (k, k2), v2)
        else:
            out.setdefault(k, v)
    return out


def _lay_kq(kq, keys):
    for k in keys:
        v = kq.get(k)
        u = v.get("u") if isinstance(v, dict) else None
        x = so_num(v.get("v")) if isinstance(v, dict) else so_num(v)
        if x is not None:
            return x, k, u
    return None, None, None


def dem_gia(gia, a, b):
    """(số phiên, % giá điều chỉnh) từ phiên a tới phiên b trên chuỗi giá; thiếu → (None, None)."""
    ngays = [d for d, _, _ in gia]
    if not ngays or not ngay(a) or not ngay(b) or b < a:
        return None, None
    i, j = bisect.bisect_left(ngays, a), bisect.bisect_right(ngays, b) - 1
    if i >= len(ngays) or j < i:
        return None, None
    return j - i, (gia[j][1] / gia[i][1] - 1) * 100 if gia[i][1] else None


def ket_qua(m, gia):
    """(số phiên, biến động %, nguồn chữ) của một thẻ ĐÃ ĐÓNG: `ket_qua` của engine (khoá/đơn vị lạ vẫn đọc: phân số hay
    % chọn theo cỡ khớp với giá) — thiếu → đếm trên giá điều chỉnh từ «Hình thành · biết lúc» tới phiên thẻ đóng (den)."""
    n_g, p_g = dem_gia(gia, ngay_hinh_thanh(m), m.get("den") or ngay_trang_thai(m))
    kq = _phang(m.get("ket_qua")) if isinstance(m.get("ket_qua"), dict) else {}
    n, _, _ = _lay_kq(kq, KQ_N)
    bd, k, u = _lay_kq(kq, KQ_BD)
    if bd is not None:
        if u == "%" or k.endswith("_pct") or k == "pct":
            pass
        elif p_g is not None:
            bd = min((bd, bd * 100), key=lambda c: abs(c - p_g))
        elif abs(bd) <= 1.5:
            bd *= 100
    if n is None and bd is None:
        return n_g, p_g, "view đếm trên giá điều chỉnh (engine chưa ghi số đo kết quả)"
    return (n if n is not None else n_g), (bd if bd is not None else p_g), "số đo kết quả của engine"


# ── hướng luận điểm · lý do đóng · tiêu đề bảng lịch sử (final_ad HIGH + MEDIUM, 24/09)

HUONG_GIAM = {"giam", "giảm", "down", "short", "bear", "xuong", "xuống", "am", "âm"}
HUONG_TANG = {"tang", "tăng", "up", "long", "bull", "len", "lên", "duong", "dương"}


def huong_thesis(m):
    """Hướng luận điểm engine ghi — ket_qua.huong_thesis (hoặc khoá cùng tên trên thẻ): 'giam' | 'tang'; thiếu / lạ →
    None (view không tự đoán hướng: màu Biến động khi đó là xám)."""
    kq = m.get("ket_qua") if isinstance(m.get("ket_qua"), dict) else {}
    for v in (kq.get("huong_thesis"), m.get("huong_thesis")):
        v = v.get("v") if isinstance(v, dict) else v
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if v:
                return "giam" if v < 0 else "tang"
            continue
        s = str(v or "").strip().lower()
        if s in HUONG_GIAM:
            return "giam"
        if s in HUONG_TANG:
            return "tang"
    return None


def mau_bien_dong(bd, huong):
    """Màu ô Biến động theo hướng luận điểm: đi đúng hướng thesis → 'up', ngược → 'down'; chưa biết hướng hoặc 0 →
    'grey'; không có số → ''. Thesis giảm (Mũ sắt, Chất tải đầm lầy): số âm là đúng hướng."""
    if bd is None:
        return ""
    if huong not in ("giam", "tang") or not bd:
        return "grey"
    return "up" if (bd < 0) == (huong == "giam") else "down"


DONG_VI_MA = {"gay": "gãy", "het_hieu_luc": "hết hiệu lực", "xac_nhan": "hết hạn giữ sau xác nhận (EST)",
              "het_han": "hết hạn giữ sau xác nhận (EST)", "het_han_giu": "hết hạn giữ sau xác nhận (EST)",
              "han_giu": "hết hạn giữ sau xác nhận (EST)"}
TEN_BUOC = {"gay": "Gãy", "het_hieu_luc": "Hết hiệu lực"}  # tên vline engine đặt khi đổi sang trạng thái đóng


def dong_vi(m):
    """(chữ «Đóng vì», engine ghi?) — ket_qua.dong_vi của engine (chữ, mã máy, hoặc {mo_ta|chu|ma}) trước; engine cũ →
    view suy: gãy / hết hiệu lực + lý do ở vline đổi trạng thái của engine; xác nhận → đóng theo hạn giữ (luật EST)."""
    kq = m.get("ket_qua") if isinstance(m.get("ket_qua"), dict) else {}
    v = kq.get("dong_vi", m.get("dong_vi"))
    if isinstance(v, dict):
        v = v.get("mo_ta") or v.get("chu") or v.get("text") or v.get("g") or v.get("ma") or v.get("v")
    s = str(v or "").strip()
    tt = m.get("trang_thai")
    ly = next((str(n.get("mo_ta") or "") for n in reversed(m.get("diem_neo") or []) if isinstance(n, dict)
               and n.get("loai") == "vline" and n.get("ten") == TEN_BUOC.get(tt)), "")
    if s:
        if re.fullmatch(r"[a-z0-9_]+", s):
            s = DONG_VI_MA.get(s) or s.replace("_", " ")
        if tt in TEN_BUOC and s == TT[tt][0] and ly:  # engine chỉ ghi tên trạng thái → thêm lý do ở vline của engine
            s = "%s: %s" % (s, ly)
        return trung_tinh(s), True
    if tt in TEN_BUOC:
        return trung_tinh("%s: %s" % (TT[tt][0], ly) if ly else TT[tt][0]), False
    if tt == "xac_nhan":
        return "đóng theo hạn giữ sau xác nhận (luật EST của engine)", False
    return CO, False


HUONG_CHU = {"giam": "thesis giảm — số âm là đi đúng hướng luận điểm", "tang": "thesis tăng — số dương là đi đúng "
             "hướng luận điểm", None: "engine chưa ghi hướng luận điểm — màu xám, không đọc xanh/đỏ"}


def cot_lich_su():
    """Cột bảng lịch sử thẻ đã đóng (trang mã)."""
    return [cot("mau", "Mẫu hình", "left"), cot("tt", "Trạng thái", "left", "tag"), cot("ht", "Hình thành", "left"),
            cot("ttt", NHAN_TTT, "left"), cot("giu", "Giữ (phiên)"), cot("bd", "Biến động (theo hướng luận điểm)"),
            cot("dv", "Đóng vì", "left"), cot("dg", "Điểm gãy của thesis", "left")]


def dg_gon(s):
    """Ô «Điểm gãy của thesis» của bảng lịch sử: bỏ tiền tố cột đã nói, tách nguồn sang tooltip → (chữ, tooltip)."""
    s = re.sub(r"^%s\s*" % re.escape(PHIEN_DAU), "", str(s or ""))
    s = s[:1].upper() + s[1:]
    chu, _, ng = s.partition(" · nguồn ")
    return chu, ("nguồn " + ng) if ng else ""


def tieu_lich_su(ls):
    """(tiêu đề, dòng phụ) của bảng lịch sử — nói bảng cho thấy gì: đếm theo trạng thái đóng; thẻ xác nhận đóng theo hạn
    giữ cố định của engine nên độ dài có sàn; số là thống kê trong mẫu (EST), không phải xác suất."""
    ds = [m for m in ls or [] if isinstance(m, dict)]
    d = Counter(m.get("trang_thai") for m in ds)
    phan = ["%d %s" % (d[k], TT[k][0]) for k in ("gay", "xac_nhan", "het_hieu_luc") if d[k]]
    tit = "%d mẫu đã đóng%s" % (len(ds), "".join(" · " + x for x in phan))
    sub = ("Engine đóng thẻ đã xác nhận khi hết một hạn giữ cố định (luật EST — lý do từng thẻ ở cột «Đóng vì»), nên "
           "«Giữ (phiên)» của thẻ xác nhận có sàn, không đo độ dài trend. Biến động là thống kê trong mẫu (EST), không "
           "phải xác suất, không phải kết quả giao dịch.")
    return tit, sub


# ── lời vị thế → chữ trung tính (final_ar #3, luật §0.5): chữ engine cũ còn 'đáy đã bắt', 'giá vào', 'vùng giá đã đầu
# tư', 'mất hàng' → đổi ngay trong view (engine cũ lẫn mới); sót lại thì RE_HANH_DONG của view ẩn cả câu.

QUY_TAC_TG = "quy tắc rủi ro riêng của tác giả%s — engine không áp, không đo từ đỉnh"
TRUNG_TINH = (
    (re.compile(r"[−-]?7% tính từ vùng giá đã đầu tư(?: \(sách O'Neil\))?(?:, không tính từ đỉnh)?"),
     QUY_TAC_TG % " (sách O'Neil)"),
    (re.compile(r"rơi 12–15% tính từ giá vào(?:, 'nếu dài hạn')?(?: — không tính từ đỉnh)?"),
     QUY_TAC_TG % " ('nếu dài hạn')"),
    (re.compile(r"người chơi biên hộp mất hàng"), "nhóm giao dịch ở biên hộp"),
    (re.compile(r"\bđáy đã bắt\b"), "đáy hộp đáy"),
    (re.compile(r"\bbắt tốt\b"), "chạy tốt"),
    (re.compile(r"\bđiểm thoát\b"), "mức kết thúc mẫu"),  # đầm lầy: tác giả không nêu mức kết thúc — không phải lệnh
)


def trung_tinh(s):
    """Chữ engine → chữ không mang lời vị thế (mức vẫn là mức của engine, chỉ đổi cách gọi)."""
    s = str(s or "")
    for p, moi in TRUNG_TINH:
        s = p.sub(moi, s)
    return s


# ── cảnh báo phân bổ (final_ar MEDIUM #6): tỷ lệ mã có thẻ đang theo dõi theo mẫu > 25% số mã quét = bộ quét chưa đủ
# chọn lọc. Engine ghi `_tong.canh_bao_phan_bo`; engine cũ chưa có → view đếm từ _tong.bang.

NGUONG_PB = 25.0  # % số mã quét (EST)


def _phan_tram(v, ti_le=None):
    """Tỷ lệ engine → %: phân số (≤ 1) hay % chọn theo tỷ lệ đếm được nếu có; thiếu → tỷ lệ đếm."""
    x = so_num(v)
    if x is None:
        return ti_le
    if ti_le is not None:
        return min((x, x * 100.0), key=lambda c: abs(c - ti_le))
    return x * 100.0 if abs(x) <= 1.0 else x


def _chu_cum(x):
    """Một cụm ngày neo của engine → chữ ('Chân cầu?: 34 mã neo trong 20/07/2026–28/07/2026 · …')."""
    if isinstance(x, str):
        return x.strip() or None
    if not isinstance(x, dict):
        return None
    ten = TEN.get(x.get("id") or x.get("mau"))
    n = so_num(x.get("n_ma"))
    tu, den = x.get("tu") or x.get("ngay"), x.get("den")
    khoang = "%s%s" % (dmy(tu), "–" + dmy(den) if den and den != tu else "") if tu else ""
    s = "%s%s%s" % ("%s?: " % ten if ten else "", "%s mã" % so(n, 0) if n is not None else "",
                    " neo trong %s" % khoang if khoang else "")
    g_ = str(x.get("g") or x.get("mo_ta") or "").strip()
    s = "%s%s" % (s, " · " + g_ if g_ and s else g_)
    return s or None


def dem_phan_bo(nhom, bang, chi_so):
    """View đếm cho cảnh báo phân bổ khi engine chưa ghi: ({id: (số mã có thẻ đang theo dõi, số thẻ)}, số mã quét) —
    mẫu số là mã cổ phiếu (chỉ số như VN-Index không tính), như engine. nhom = {id: [(dòng _tong.bang, thẻ, nhãn)]}."""
    dem = {k: (len({x["ma"] for x, m, _ in ds if m.get("trang_thai") in SONG and x["ma"] not in chi_so}),
               sum(1 for x, m, _ in ds if m.get("trang_thai") in SONG and x["ma"] not in chi_so))
           for k, ds in nhom.items()}
    return dem, sum(1 for x in bang if x.get("ma") not in chi_so)


def canh_bao_pb(cb, dem, n_quet, cum_ngay=None):
    """Cảnh báo phân bổ → {dong[{id, n_ma, n_the, mau_so, pct, vuot}], cum[chữ], nguong (%), nguon 'engine'|'view', g}.
    cum_ngay = _tong.cum_ngay của engine (danh sách cụm ngày neo, riêng khỏi canh_bao_phan_bo) → thêm vào cum.
    cb = _tong.canh_bao_phan_bo: hợp đồng engine = danh sách CHỈ các mẫu vượt {id, ten, n_ma, n_the, mau_so (mã cổ
    phiếu), pct (%)} — [] nghĩa là không mẫu nào vượt; cũng đọc dict theo mẫu / dict có danh sách con + nguong +
    cum_ngay. cb None (engine cũ chưa ghi) → view đếm: dem = {id: (số mã có thẻ đang theo dõi, số thẻ)}, n_quet = số mã
    cổ phiếu quét."""
    nguong, cum, g_, ms_chung, con = NGUONG_PB, [], "", None, None
    if isinstance(cb, dict):
        nguong = _phan_tram(cb.get("nguong")) or NGUONG_PB
        ms_chung = next((so_num(cb[k]) for k in ("n_quet", "mau_so", "n_ma_quet") if so_num(cb.get(k))), None)
        g_ = str(cb.get("g") or "").strip()
        cum = [c for c in (_chu_cum(x) for x in (cb.get("cum_ngay") or cb.get("cum") or [])) if c]
        con = next((cb[k] for k in ("mau", "theo_mau", "ds", "dong", "items") if isinstance(cb.get(k), (list, dict))),
                   None)
        if con is None:
            con = {k: v for k, v in cb.items() if k in TEN and isinstance(v, dict)}
    elif isinstance(cb, list):
        con = cb
    cum += [c for c in (_chu_cum(x) for x in (cum_ngay if isinstance(cum_ngay, list) else [])) if c]
    items = ([dict(v, id=k) for k, v in con.items() if isinstance(v, dict)] if isinstance(con, dict)
             else [x for x in con or [] if isinstance(x, dict)])
    dong_ = []
    for x in items:
        k = x.get("id") or x.get("mau")
        if k not in TEN:
            continue
        n_ma = so_num(x.get("n_ma"))
        ms_ = next((so_num(x[q]) for q in ("n_quet", "mau_so") if so_num(x.get(q))), None) or ms_chung
        pct = _phan_tram(x.get("pct"), n_ma * 100.0 / ms_ if n_ma is not None and ms_ else None)
        v = x.get("vuot_25", x.get("vuot"))
        dong_.append({"id": k, "n_ma": n_ma, "n_the": so_num(x.get("n_the")), "mau_so": ms_, "pct": pct,
                      "vuot": v if isinstance(v, bool) else (pct is not None and pct > nguong)})
    if dong_ or isinstance(cb, (list, dict)):
        return {"dong": dong_, "cum": cum, "nguong": nguong, "nguon": "engine", "g": g_}
    for k, _ in MAU:
        n_ma, n_the = (dem or {}).get(k, (0, 0))
        pct = n_ma * 100.0 / n_quet if n_quet else None
        dong_.append({"id": k, "n_ma": n_ma, "n_the": n_the, "mau_so": n_quet, "pct": pct,
                      "vuot": pct is not None and pct > nguong})
    return {"dong": dong_, "cum": cum, "nguong": nguong, "nguon": "view", "g": g_}


def note_phan_bo(pb, scope):
    """Note cảnh báo phân bổ đầu trang vũ trụ (pb = canh_bao_pb): tỷ lệ mã có thẻ đang theo dõi theo mẫu; > 25% số mã
    quét = bộ quét chưa đủ chọn lọc, không phải tín hiệu mạnh hơn. Thấu kính SS-T3; ngưỡng và luật đếm EST."""
    def e(x):
        return html.escape(str(x), quote=False)
    ng = pt(pb["nguong"], 0)
    ds = sorted(pb["dong"], key=lambda x: -(x["pct"] or 0))
    vuot = [x for x in ds if x["vuot"]]

    def mot(x):
        s = "%s %s%s mã%s (%s)" % (TEN[x["id"]] + "?", so(x["n_ma"], 0), "/%s" % so(x["mau_so"], 0) if x["mau_so"] else "",
                                   " · %s thẻ" % so(x["n_the"], 0) if x.get("n_the") is not None else "",
                                   pt(x["pct"], 1) if x["pct"] is not None else CO)
        return "<b>%s</b>" % e(s) if x["vuot"] else e(s)
    nguon = ("engine mẫu hình (chỉ liệt kê mẫu vượt ngưỡng; mẫu số là mã cổ phiếu engine quét%s)" % (
        "" if scope == "VN200" else ", toàn vũ trụ chứ không riêng rổ %s" % scope)
             if pb["nguon"] == "engine" else
             "view tự đếm trên bảng thẻ rổ %s, không tính VN-Index — engine chưa ghi cảnh báo phân bổ" % scope)
    text = ("Tỷ lệ mã có thẻ đang theo dõi, theo từng mẫu. Trên %s số mã cổ phiếu quét nghĩa là bộ quét chưa đủ chọn lọc "
            "(ngưỡng lỏng, hoặc một đợt thị trường đếm thành nhiều thẻ) — không phải tín hiệu mạnh hơn; đọc bảng của mẫu "
            "đó với độ tin thấp hơn.<br>%s" % (ng, " · ".join(mot(x) for x in ds) if ds else
                                                   "Engine: không mẫu nào vượt ngưỡng."))
    if pb["cum"]:
        text += "<br>Cụm ngày neo (một sự kiện thị trường, không phải nhiều tín hiệu độc lập): %s" % " · ".join(
            e(c) for c in pb["cum"])
    if pb.get("g"):
        text += "<br>%s" % e(trung_tinh(pb["g"]))
    text += "<br>Thấu kính SS-T3; ngưỡng %s và luật đếm là EST · nguồn: %s." % (ng, nguon)
    tit = ("Cảnh báo phân bổ — %d/%d mẫu có thẻ ở hơn %s số mã cổ phiếu quét" % (len(vuot), len(MAU), ng) if vuot else
           "Phân bổ thẻ theo mẫu — không mẫu nào có thẻ ở hơn %s số mã cổ phiếu quét" % ng)
    return {"type": "note", "pill": "EST", "mau": "bear" if vuot else "dim", "title": tit, "text": text}
