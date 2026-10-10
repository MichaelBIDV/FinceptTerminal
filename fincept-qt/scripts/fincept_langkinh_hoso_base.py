#!/usr/bin/env python3
"""
Fincept Terminal — Hồ sơ Lăng Kính: định dạng nguyên tử So, bậc bằng chứng, khung trang dùng chung cho
fincept_langkinh_hoso.py (view hoso), fincept_langkinh_hoso_ro.py (matran5 · sigma · rrg) và fincept_langkinh_mauhinh.py;
kèm bảng trigger 3 cột (D2). Tách để mỗi tệp ≤ 800 dòng.
Chỉ định dạng — không tính lại công thức; thiếu số → "[CẦN DATA] — g" và ghi vào sổ CẦN DATA của trang.
Stdlib only; Python 3.11 và 3.14.
"""
import glob
import html
import json
import os
import re
import zlib
from datetime import datetime

from fincept_langkinh_base import CO, cot, dm, dmy, dong, g, ms, ngay, pp, pt, so, so_num

SCOPES = ("VN30", "VN100", "VN200")
RE_MA = re.compile(r"^[A-Z0-9]{2,10}$")
BAC = {"FACT-T1": 0, "FACT-T2": 1, "SS-T3": 2, "NEWS": 3, "EST": 4, "UNVERIFIED": 5}
CU_GIO = 26
N_TUAN_3Y = 156
N_PHIEN_NN = 63
GOI_Y = "hồ sơ %s chưa được dựng — builder lk_hoso dựng khi cache Vietcap của mã này đủ các nguồn"
TAG_MAU = {"FACT-T1": "up", "FACT-T2": "blue", "SS-T3": "violet", "NEWS": "grey", "EST": "amber", "UNVERIFIED": "down"}
GOC_MAU = {"Leading": "up", "Weakening": "amber", "Lagging": "down", "Improving": "blue"}
CHI_SO = {"pe": "P/E", "pb": "P/B"}
K_NHAN = {"retail": "retail", "vung_xam": "vùng xám", "tay_to": "tay to"}
# 'thoat_6t' KHÔNG gọi là "thoát": đọc nhầm thành lời thoát vị thế cạnh hàng tác giả "thoát hết" (a1).
VWAP_NHAN = {"kep_nong": ("Kẹp nông VWAP", "amber", "dưới cả ba cụm VWAP, cụm xa nhất cách ≤ 6%"),
             "kep_sau": ("Kẹp sâu VWAP", "down", "dưới cả ba cụm VWAP, có cụm cách > 6%"),
             "thoat_6t": ("Trên VWAP 6T", "blue", "trên VWAP 6T, dưới VWAP 12T và 24T"),
             "tren_cum": ("Trên cả ba cụm VWAP", "up", "trên cả ba cụm VWAP")}
# Màu cố định theo mã (Artifact: VCB blue · MSN violet · FPT amber) — mã khác băm ổn định, không theo vị trí rổ.
MAU_CO_DINH = {"VCB": "blue", "MSN": "violet", "FPT": "amber"}
MAU_BAM = ("up", "blue", "violet", "amber", "down", "grey")
RE_PATTERN = re.compile(r"(Pattern [A-D]|phân phối)(?!\?)")
# Khoá can_data của builder/view → chữ người đọc (không in khoá mã lên trang).
KHOA_PHAN = {"gia": "Giá", "fft": "FFT", "vwap": "VWAP", "codong": "Cổ đông", "chuthe": "Chủ thể", "ngoai": "Sở hữu ngoại",
             "tudoanh": "Tự doanh", "sigma": "Vùng giá σ", "rrg": "RRG", "co_phan": "Cổ phần", "cong": "CỔNG",
             "trigger": "Kiểm tự động", "nguon": "Nguồn", "vnindex": "VN-Index", "pe_vni": "P/E VN-Index",
             "pb_vni": "P/B VN-Index", "exvin3": "P/E ex-Vin3", "ty_trong_vin": "Tỷ trọng họ Vin",
             "do_rong_dinh_gia": "Độ rộng định giá", "thanh_khoan": "Thanh khoản VN-Index", "dong_ho": "Ba đồng hồ",
             "mauhinh": "Mẫu hình NTH"}
KHOA_LA = {"px": "giá", "ma4": "trung bình 4 tuần", "ma4_tho": "trung bình 4 tuần (thô)", "chuoi": "chuỗi", "cap": "cặp mốc",
           "moc": "mốc", "noi_bo": "giao dịch nội bộ", "nhan": "nhãn", "hien": "hiện tại", "day": "đáy", "dinh": "đỉnh",
           "dau_63": "đầu 63 phiên", "cuoi_63": "cuối 63 phiên", "room": "room còn lại", "tran": "trần sở hữu",
           "ff": "free float", "bctn": "theo BCTN", "vci": "theo Vietcap", "chuan_hoa": "chuẩn hoá", "hien_tai": "hiện tại",
           "muc": "chu kỳ tiền", "x": "tỷ số", "z": "z", "dai": "dải giá", "d_pct": "Δ%", "k": "hệ số k", "dgia": "Δ giá",
           "tuan_ftse": "tuần FTSE", "pct3y": "percentile 3 năm", "rong_20": "ròng 20 phiên", "rong_63": "ròng 63 phiên",
           "ytd": "từ đầu năm", "tu_dong": "mẫu chưa chấm", "co_cau": "cơ cấu sở hữu", "pct3y_tb4": "percentile 3 năm"}
KIEU_MOC = {"so_tron": "số tròn — Δ chỉ ở mức hướng, không xác nhận pattern",
            "chep": "chép lại (CF) — không tính Δ, không phải 'không đổi'", "noi_suy": "nội suy — chỉ để vẽ"}


# ───────────────────────────── đọc tệp · định dạng ─────────────────────────────

def doc(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def e(s):
    return html.escape(str(s), quote=False)


RE_THE = re.compile(r"</?(?:b|i|em|strong|code|br|tag)(?:\s[^<>]*)?/?>", re.I)


def tron(s):
    """html-lite → chữ thuần cho ô bảng: chỉ bỏ thẻ html-lite (b, i, code, br, tag…) — chữ thuần như
    "APT < 2.000 … giảm > 40%" giữ nguyên."""
    return html.unescape(RE_THE.sub("", str(s or ""))).strip()


# Tên trường vendor/khoá máy còn sót trong chữ builder → chữ người đọc (can_data, keynote, ghi chú).
TU_MAY = ((r"\bforeignOwnedPercentage\b", "tỷ lệ sở hữu ngoại"), (r"\bforeignOwned\b", "số cp nước ngoài"),
          (r"\btotalShares\b", "tổng cp lưu hành"), (r"\bproprietary-history\b", "chuỗi tự doanh"),
          (r"\bclosePriceAdjusted\b", "giá điều chỉnh"), (r"\bfreeFloatPercentage\b", "tỷ lệ free float"),
          (r"\bnav_unverified\b", "cờ chưa xác minh"), (r"\bthuc_hien/sau\b", "khối lượng thực hiện/số sau giao dịch"),
          (r"\bpct3y\b", "percentile 3 năm"), (r"\bpall\b", "percentile toàn dải"), (r"\bchu_the\b", "nhãn chủ thể"),
          (r"\bngay_tep\b", "ngày tệp"), (r"\bexerciseRatio\b", "tỷ lệ thực hiện"))


def viet(s):
    """Chữ tự do của builder → kiểu Việt: ngày ISO → dd/mm/yyyy, kỳ 'YYYY-MM' → mm/yyyy, 'null' → 'trống', tên trường
    máy → chữ người đọc, dấu trừ trước số → U+2212 (builder mới đã sạch — lọc lại vô hại cho bản cũ)."""
    s = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", r"\3/\2/\1", str(s or ""))
    for a, b in TU_MAY:
        s = re.sub(a, b, s)
    s = re.sub(r"\b((?:19|20)\d{2})-(0[1-9]|1[0-2])\b", r"\2/\1", s)
    s = re.sub(r"\s*→\s*null\b", " → để trống", s)
    s = re.sub(r"\bnull\b", "trống", s)
    return re.sub(r"(^|[\s(])-(?=\d)", "\\1\u2212", s)


def khoa_ten(k):
    """'FPT.codong.cap' → 'FPT · Cổ đông · cặp mốc'; khoá lạ → giữ phần cuối, bỏ gạch dưới."""
    phan = [x for x in str(k or "").replace("/", ".").split(".") if x]
    out = []
    if phan and RE_MA.match(phan[0]) and phan[0] not in KHOA_PHAN:
        out.append(phan.pop(0))
    if phan:
        out.append(KHOA_PHAN.get(phan[0], phan[0].replace("_", " ")))
        out += [KHOA_LA.get(x, x.replace("_", " ")) for x in phan[1:]]
    return " · ".join(out) or "Mục"


def hau_to(text, tv):
    """Luật 0.3 / Hard Rule #16: ngoài 30 mã Toàn Vũ → '?' sau mọi 'Pattern X' và 'phân phối' (không nhân đôi)."""
    return text if tv or not text else RE_PATTERN.sub(r"\1?", str(text))


def mau_ma(ma):
    return MAU_CO_DINH.get(ma) or MAU_BAM[zlib.crc32(str(ma).encode("utf-8")) % len(MAU_BAM)]


def gv(o):
    return so_num(o.get("v")) if isinstance(o, dict) else so_num(o)


def moc_so(o):
    """{v: So, ngay} → (So, ngày)."""
    return (o.get("v"), o.get("ngay")) if isinstance(o, dict) and isinstance(o.get("v"), dict) else (o, None)


def gk(v):
    """Giá nghìn đồng kiểu Artifact: 58,9 · 75,37 · 54,0."""
    s = so(v, 2)
    return s[:-1] if s != CO and "," in s and s.endswith("0") else s


def cp_(v, dau=False):
    a = abs(v)
    if a >= 1e9:
        return so(v / 1e9, 2, dau) + " tỷ cp"
    return so(v / 1e6, 1, dau) + " triệu cp" if a >= 1e6 else so(v, 0, dau) + " cp"


def ty_(v, dau=False):
    return so(v, 0 if abs(v) >= 100 else 1, dau) + " tỷ"


def fmt(v, u, dau=False, nd=None):
    if u == "nghin_dong":
        return gk(v)
    if u == "%":
        return pt(v, 2 if nd is None else nd, dau)
    if u == "%tuan":
        return pt(v, 3)
    if u == "x":
        return so(v, 2 if nd is None else nd) + "×"
    if u == "sigma":
        return so(v, 2, True) + "σ"
    if u == "cp":
        return cp_(v, dau)
    if u == "ty_dong":
        return ty_(v, dau)
    if u == "tuan":
        return pp(v) + " tuần"
    if u == "thang":
        return so(v, 1) + " tháng"
    return so(v, 2 if nd is None else nd, dau)  # điểm chỉ số và đơn vị lạ


def tag(b, nhan=""):
    return '<tag b="%s">%s</tag>' % (e(b or "CẦN DATA"), e(nhan or b or "CẦN DATA"))


def yeu(*bs):
    """Bậc yếu nhất trong các bậc đã biết (nhiều số chung một ô → ô mang bậc yếu nhất)."""
    ds = [b for b in bs if b in BAC]
    return max(ds, key=BAC.get) if ds else ""


def ha_bac(o, bac="EST", ghi_chu=None):
    """D3 — hạ bậc nguyên tử về tối đa `bac`; bậc đã thấp hơn giữ nguyên."""
    if not isinstance(o, dict) or BAC.get(o.get("b"), 9) >= BAC[bac]:
        return o
    return dict(o, b=bac, g=ghi_chu or o.get("g"))


def ky_s(ky):
    m = re.match(r"(\d{4})-(\d{2})", str(ky or ""))
    return "%s/%s" % (m.group(2), m.group(1)) if m else CO


def ky_ms(ky):
    d = ngay(str(ky or "")[:7] + "-01")
    return ms(d) if d else None


def ms_s(s):
    d = ngay(s)
    return ms(d) if d else None


def pd_nhan(nd, ngan=False):
    tg = str(nd.get("tac_gia") or "không rõ tác giả").split(" · ")[0]
    return ("Phán đoán %s" % dm(nd.get("ngay"))) if ngan else "Phán đoán %s · %s" % (dmy(nd.get("ngay")), tg)


def pd_tuoi(nd, now):
    d = ngay(nd.get("ngay"))
    return "%d ngày tuổi" % (now.date() - d).days if d else "không rõ ngày"


def ten_pattern(pat, tv):
    """'B' → 'Pattern B' ('Pattern B?' ngoài 30 mã Toàn Vũ). Chưa phân loại không phải tên pattern → không hậu tố."""
    goc = str(pat or "").rstrip("?")
    if goc in ("", "chua_ro"):
        return "chưa phân loại pattern"
    return "Pattern " + goc + ("?" if not tv or str(pat).endswith("?") else "")


def trong_tv(hs):
    """30 mã Toàn Vũ = mã builder nhận mốc fft_codong; nhãn pattern có '?' hoặc không có mốc → ngoài (bảo thủ)."""
    cd = hs.get("codong") or {}
    return cd.get("trang_thai") == "ok" and not str(g(cd, "pattern", "nhan") or "").endswith("?")


def tuoi_tep(tao_luc, now):
    try:
        moc = datetime.strptime(str(tao_luc or "")[:16].replace("T", " "), "%Y-%m-%d %H:%M")
    except ValueError:
        return None, "không rõ lúc dựng"
    gio = (now - moc).total_seconds() / 3600
    if gio > CU_GIO:
        return gio, "HỒ SƠ CŨ %d giờ (dựng %s)" % (int(gio), moc.strftime("%d/%m %H:%M"))
    tr = "%d phút trước" % max(0, int(gio * 60)) if gio < 1 else "%d giờ trước" % int(gio)
    return gio, "hồ sơ dựng %s · %s" % (moc.strftime("%d/%m %H:%M"), tr)


def dong_b(d):
    """CỔNG layout hoso: phần trong ngoặc đầu tiên in <b> (mono amber)."""
    s = e(d or "CỔNG: [CẦN DATA — thiếu dòng CỔNG]")
    return re.sub(r"^(CỔNG:\s*)(\[[^\]]*\])", r"\1<b>\2</b>", s, count=1)


def kpi(k, v, s, b="", mau=""):
    return {"k": k, "v": v, "s": s, "b": b, "mau": mau}


def sec(block, eyebrow, title, sub="", b=""):
    """Gắn đầu mục kiểu Artifact (eyebrow · claim-title · sub) cho một block."""
    block.update({"eyebrow": eyebrow, "title": title, "sub": sub})
    if b:
        block["b"] = b
    return block


def note_can(t, extra=()):
    """Note [CẦN DATA] gom can_data của builder + ô thiếu gặp khi in. Khử trùng theo khoá: bản của builder (đứng
    trước) thắng bản view; nhãn khoá là chữ người đọc (khoa_ten), lý do qua viet()."""
    seen, dong_ = set(), []
    for k, ly in list(extra) + t.thieu:
        if k in seen or "cong" in str(k or "").replace("/", ".").split(".")[:2]:
            continue  # CỔNG (kể cả chu kỳ tiền [CẦN DATA]) chỉ ở dải CỔNG trên cùng — một lần mỗi trang
        seen.add(k)
        dong_.append("• <b>%s</b> — %s" % (e(khoa_ten(k)), e(viet(ly))))
    if not dong_:
        return None
    return {"type": "note", "pill": "CẦN DATA", "mau": "bear", "title": "[CẦN DATA] · %d mục" % len(dong_),
            "text": "<br>".join(dong_)}


def rows_kpi(items):
    return [{"01 Mục": it.get("k", ""), "02 Giá trị": it.get("v") or "[CẦN DATA]", "03 Ghi chú": it.get("s", ""),
             "04 Bậc": it.get("b", "")} for it in items]


class Trang:
    """Một lần dựng trang: ngữ cảnh + sổ [CẦN DATA] của các ô thiếu số."""

    def __init__(self, c):
        self.c, self.now = c, c.now
        self.goc = os.path.dirname(os.path.normpath(c.dir))
        self.hs_dir = os.path.join(c.dir, "lk_hoso")
        self.thieu = []
        self.cfg = doc(os.path.join(self.goc, "lk_cauhinh.json")) or {}
        self.nd_tep = g(doc(os.path.join(self.goc, "lk_nhan_dinh.json")), "muc") or {}
        self.idx = doc(os.path.join(self.hs_dir, "_index.json")) or {}

    def s(self, o, khoa, dau=False, nd=None):
        v = gv(o)
        return self.can(o, khoa) if v is None else fmt(v, o.get("u") if isinstance(o, dict) else None, dau, nd)

    def can(self, o, khoa):
        ly = str((o.get("g") if isinstance(o, dict) else None) or "không có trong hồ sơ")
        ly = viet(re.sub(r"^\[?CẦN DATA\]?\s*[—-]?\s*", "", ly).strip(" []")) or "không có trong hồ sơ"
        self.thieu.append((khoa, ly))
        return "[CẦN DATA] — " + ly

    def kpi_so(self, k, o, khoa, s, dau=False, nd=None, mau=""):
        if gv(o) is None:
            return {"k": k, "v": None, "s": self.can(o, khoa)}
        return kpi(k, fmt(gv(o), o.get("u"), dau, nd), s, o.get("b") or "", mau)

    def co_ho_so(self):
        ds = [x.get("ma") for x in self.idx.get("ma") or [] if isinstance(x, dict)]
        ds = ds or [os.path.basename(p)[:-5] for p in glob.glob(os.path.join(self.hs_dir, "[A-Z0-9]*.json"))]
        return sorted(m for m in ds if isinstance(m, str) and RE_MA.match(m))

    def ho_so(self, ma):
        return doc(os.path.join(self.hs_dir, ma + ".json")) if RE_MA.match(ma or "") else None

    def nd(self, ma, hs=None):
        """Lớp phán đoán: tệp lk_nhan_dinh.json (nguồn gốc) trước, bản chép trong hồ sơ sau; phải có tác giả + ngày."""
        x = self.nd_tep.get(ma) if isinstance(self.nd_tep.get(ma), dict) else (hs or {}).get("nhan_dinh")
        return x if isinstance(x, dict) and x.get("tac_gia") and x.get("ngay") else None

    def ro(self, scope):
        """(mã có hồ sơ trong rổ, mã trong rổ chưa có hồ sơ) — rổ theo fft_langkinh.ma.nhom."""
        co = set(self.co_ho_so())
        tv = self.c.members or sorted(co)
        return [m for m in tv if m in co], [m for m in tv if m not in co]


def nav_so(hs):
    n = hs.get("nav") if isinstance(hs.get("nav"), dict) else {}
    return ha_bac(n, "EST", "sổ danh mục nội bộ, SKILL daily %s" % dm(n.get("t")))


def nav_nhan(hs):
    """Nhãn danh mục cho dòng eyebrow. Tỷ trọng UNVERIFIED (sổ gắn nav_unverified — spec §8) không in số lên đầu
    trang: UNVERIFIED = không dùng cho quyết định; số vẫn ở chip nguồn."""
    n, ro = nav_so(hs), hs.get("ro") or []
    if gv(n) is not None and n.get("b") == "UNVERIFIED":
        return "trong sổ danh mục (tỷ trọng chưa xác minh)"
    if gv(n) is not None:
        return "%s%% NAV (%s)" % (pp(gv(n)), n.get("b") or "EST")
    if n.get("watch") or "WATCH" in ro:
        return "watch-list"
    return "avoid-list" if n.get("avoid") or "AVOID" in ro else "ngoài danh mục"


KHONG_DUNG_SIGMA = "không dùng được (σ lớn so với μ)"


def doi_nhan(sg):
    """'đổi P/E → P/B (P/E μ − σ ≤ 0)' khi builder dùng dự phòng P/B (lk_hoso.phan_sigma); không đổi → ''."""
    d = sg.get("doi_chi_so") if isinstance(sg.get("doi_chi_so"), dict) else None
    if not d:
        return ""
    return "đổi %s → %s (%s μ − σ ≤ 0)" % (CHI_SO.get(d.get("tu"), d.get("tu")), CHI_SO.get(d.get("sang"), d.get("sang")),
                                          CHI_SO.get(d.get("tu"), d.get("tu")))


def sigma_hong(sg):
    """Dải σ không dùng được khi builder gắn dung_duoc = false (P/E μ − σ ≤ 0 và P/B cũng hỏng), hoặc μ − 2σ ≤ 0, hoặc
    σ > μ/2 (P/E các năm lãi mỏng kéo μ, σ lên — KSV, VJC)."""
    if sg.get("dung_duoc") is False:
        return True
    mu, sd = gv(sg.get("mu")), gv(sg.get("sd"))
    return mu is not None and sd is not None and (mu - 2 * sd <= 0 or sd > mu / 2)


def sigma_numline(t, hs, ma):
    """Thước σ một mã. Dải hỏng (sigma_hong) → tiêu đề/sub ghi 'không dùng được', chỉ phát mức giá > 0 (mức ≤ 0 là
    giá không thể có — bỏ, không phải thiếu số). Giá theo nghìn đồng như phần còn lại của trang."""
    sg = hs.get("sigma") or {}
    dai, cs = sg.get("dai") or {}, CHI_SO.get(sg.get("chi_so"), str(sg.get("chi_so") or "").upper())
    hong = sigma_hong(sg)
    ngan = {}
    for k in ("c2", "c1", "f", "r1", "r2"):
        v = gv(dai.get(k))
        if v is None:
            t.can(dai.get(k), ma + ".sigma.dai." + k)
        ngan[k] = round(v, 3) if v is not None and v > 0 else None
    px = gv(sg.get("px"))
    hhp = g(sg, "hhp", "z")
    sub = "%s %s (%s, %s) · μ %s · σ %s (winsorize P1/P99, EST) · %s phiên %s–%s%s" % (
        cs, t.s(sg.get("x"), ma + ".sigma.x"), g(sg, "x", "b") or CO, dm(g(sg, "x", "t")), so(gv(sg.get("mu")), 2),
        so(gv(sg.get("sd")), 2), so(sg.get("n_phien"), 0), dmy(sg.get("tu")), dmy(sg.get("den")),
        " · HHP z %s (thước khác, chỉ tham chiếu)" % so(gv(hhp), 2, True) if gv(hhp) is not None else "")
    if isinstance(sg.get("doi_chi_so"), dict):
        sub += " · %s (EST)" % doi_nhan(sg)
    if hong:
        sub += " · dải %s: chỉ vẽ mức giá dương" % KHONG_DUNG_SIGMA
    return {"type": "numline", "mode": "sigma", "title": "%s · %s%s" % (ma, cs, " · " + KHONG_DUNG_SIGMA if hong else ""),
            "sub": sub, "b": "EST", "px": round(px, 3) if px is not None else None, **ngan,
            "s": t.s(sg.get("z"), ma + ".sigma.z"), "m": "%s %s" % (cs, t.s(sg.get("x"), ma + ".sigma.x"))}


def sigma_cach(t, sg, ma):
    """'tới μ +x% · tới −1σ +y%' (EST) — −1σ ≤ 0 hoặc dải hỏng → '[CẦN DATA] — −1σ âm'."""
    if sigma_hong(sg):
        return "dải " + KHONG_DUNG_SIGMA + " — không đọc khoảng cách tới μ, −1σ"
    tm = "tới μ %s" % t.s(sg.get("toi_mu"), ma + ".sigma.toi_mu", True, 1)
    c1 = gv(g(sg, "dai", "c1"))
    if c1 is not None and c1 <= 0:
        return tm + " · tới −1σ [CẦN DATA] — −1σ âm"
    return tm + " · tới −1σ %s" % t.s(sg.get("toi_c1"), ma + ".sigma.toi_c1", True, 1)


def chips_nguon(nguon, extra=()):
    """nguon{khoá: {url, lay_luc, du_lieu_toi, n, bac, trang_thai, loi}} → chip; nguồn tổng hợp (HHP, fft_langkinh)
    không mang `bac` → EST."""
    items = []
    for k, n in (nguon or {}).items():
        if not isinstance(n, dict):
            continue
        tt, du = n.get("trang_thai"), n.get("du_lieu_toi") or n.get("as_of") or n.get("cap_nhat")
        text = "%s · dữ liệu tới %s" % (viet(k), dmy(du) if ngay(du) else (du or "ảnh chụp, không có ngày dữ liệu"))
        if so_num(n.get("n")) is not None:
            text += " · %s dòng" % so(n["n"], 0)
        if n.get("lay_luc") or n.get("generated"):
            text += " · lấy %s" % (dm(n["lay_luc"]) if n.get("lay_luc") else
                                   viet(str(n["generated"]).replace(" ICT", "")).replace("/2026 ", " "))
        b = n.get("bac") or ("EST" if k.startswith(("hhp", "fft_langkinh")) else "FACT-T2")
        if tt == "cu":
            text += " · CŨ"
        elif tt == "loi":
            text += " · LỖI: %s" % (n.get("loi") or "không rõ")
        items.append({"b": b, "text": text})
    return items + list(extra)


# ───────────────────────────── trigger (D2) — bảng 3 cột như Artifact ─────────────────────────────

# Nhãn trung tính cho dòng kiểm tự động (D2): (loại = tả điều kiện, hàm ý = nghĩa với lăng kính). Dấu '?' chỉ còn
# MỘT nghĩa trên trang: hậu tố Hard Rule #16 (ngoài 30 mã Toàn Vũ, hau_to) — không câu nào kết thúc bằng '?'.
TU_DONG = {
    "xac_nhan_B": ("FFT cạn (≤P20 3Y) + giữ đáy 52T + cổ đông kỳ kế giảm",
                   "Đủ ba vế để xét Pattern B — chưa phải xác nhận"),
    "thoat_kep": ("Đóng tuần vượt VWAP 12T + FFT tuần > P75 3Y",
                  "Giá rời cụm VWAP 12T khi thanh khoản cao — đọc lại Pillar II"),
    "them_lai": ("FFT cạn (≤P20 3Y) + vượt VWAP 6T", "Đủ điều kiện để xét Pattern B — cần Δ cổ đông kỳ kế để xác nhận"),
    "chu_the_kich_hoat": ("Sự kiện huy động vốn có ngày (sau mốc nhận định; chưa có nhận định: 12 tháng)",
                          "Chủ thể có lịch huy động vốn — đọc lại nhãn «cần / không cần thị trường»"),
    "phu_dinh_phan_phoi": ("Thủng đáy 52T + FFT 4T ≥ P90 3Y",
                           "Làn thanh khoản mới trên nền thủng — kiểm Δ cổ đông trước khi gọi là phân phối (Hard Rule #16)"),
    "phu_dinh_day_ngoai": ("Thủng đáy 52T hoặc sở hữu ngoại thủng đáy cũ",
                           "Nền giá hoặc nền sở hữu ngoại bị phá — đọc lại pha và Pillar III/IV"),
    "can_xac_minh": ("Mốc cổ đông cuối chưa quan sát · GD nội bộ chưa có kết quả",
                     "Pillar I/III còn số chờ — chưa đủ để xác nhận pattern"),
    "xac_nhan_dao_chieu": ("NN vượt ngưỡng tác giả + FFT 4T ≤ P50 3Y + đóng tuần > VWAP 12T",
                           "Đủ các vế tác giả đặt cho «xác nhận đảo chiều»"),
    "ban_vao_suc_manh": ("Giá trong vùng tác giả đặt + FFT tuần ≥ P90 3Y", "Vùng giá tác giả đặt gặp thanh khoản ≥ P90 3Y"),
    "stop_15": ("Đóng tuần dưới giá vốn tác giả khai −15%", "Giá chạm mốc −15% so với giá vốn tác giả khai"),
    "stop_20": ("Đóng tuần dưới giá vốn tác giả khai −20%", "Giá chạm mốc −20% so với giá vốn tác giả khai"),
    "phu_dinh_thesis": ("Vế cơ bản phủ định (nhập tay)", "Máy không kiểm — chờ nhập tay"),
}
FACT = {"gia.px": "giá", "gia.dong_tuan": "đóng tuần", "gia.day_52w_truoc": "đáy 52T trước", "vwap.v6": "VWAP 6T",
        "vwap.v12": "VWAP 12T", "fft.ma4": "FFT 4T", "fft.ma4_tang": "FFT 4T đang tăng", "fft.fw_tuan": "FFT tuần",
        "fft.p20_3y": "P20 3Y", "fft.p50_3y": "P50 3Y", "fft.p75_3y": "P75 3Y", "fft.p90_3y": "P90 3Y",
        "ngoai.hien": "sở hữu ngoại", "ngoai.day_truoc": "đáy sở hữu ngoại cũ",
        "codong.moc_ke_tiep_giam": "cổ đông kỳ kế tiếp giảm", "codong.moc_cuoi_chua_quan_sat": "mốc cổ đông cuối chưa quan sát",
        "chuthe.noi_bo_chua_ket_qua": "GD nội bộ chưa có kết quả",
        "chuthe.su_kien_von_co_ngay": "sự kiện huy động vốn có ngày",
        "vithe.gia_von": "giá vốn tác giả khai", "tham_so.ngoai_xac_nhan_pct": "ngưỡng NN tác giả",
        "tham_so.vung_gia_ban_lo": "cận dưới vùng tác giả", "tham_so.vung_gia_ban_hi": "cận trên vùng tác giả",
        "thesis.phu_dinh_co_ban": "vế cơ bản nhập tay"}
OP = {"<": ("<", lambda a, b: a < b), "<=": ("≤", lambda a, b: a <= b), ">": (">", lambda a, b: a > b),
      ">=": ("≥", lambda a, b: a >= b)}
RE_DK = re.compile(r"^\s*([\w.]+)\s*(<=|>=|<|>)\s*([\w.]+)(?:\s*\*\s*([\d.]+))?\s*$")
DAU_DK = {True: "✓", False: "✗", None: "(thiếu số)"}


def fact_s(k, v):
    if v is None:
        return "[CẦN DATA]"
    if isinstance(v, bool):
        return "có" if v else "không"
    if not isinstance(v, (int, float)):
        return e(v)
    if k.startswith(("gia.", "vwap.", "vithe.", "tham_so.vung_gia")):
        return gk(v)
    if k.startswith("fft."):
        return pt(v, 3)
    return pt(v, 2) if k.startswith(("ngoai.", "tham_so.ngoai")) else so(v, 2)


def dk_text(mau, ng):
    """Mẫu lk_cauhinh + giá trị fact lúc builder chấm → từng vế kèm dấu đúng/sai của CHÍNH số đã ghi (a1: không in
    bất đẳng thức sai như một khẳng định). Trạng thái cả dòng vẫn là của builder."""
    out = []
    for s in mau.get("dieu_kien") or []:
        m = RE_DK.match(s)
        if not m:
            k = s.strip()
            v = ng.get(k)
            out.append("%s: %s %s" % (FACT.get(k, k), fact_s(k, v), DAU_DK[v if isinstance(v, bool) else None]))
            continue
        a, op, b, nhan = m.groups()
        so_hang = re.fullmatch(r"[\d.]+", b) is not None
        va, vb = ng.get(a), float(b) if so_hang else ng.get(b + ("*" + nhan if nhan else ""))
        lb = "" if so_hang else FACT.get(b, b) + (" × %s =" % so(float(nhan), 2) if nhan else "") + " "
        dung = OP[op][1](va, vb) if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else None
        out.append("%s %s %s %s%s %s" % (FACT.get(a, a), fact_s(a, va), OP[op][0], lb, fact_s(b, vb), DAU_DK[dung]))
    return (" · hoặc · " if mau.get("logic") == "any" else " · ").join(out)


def dong_tu_dong(hs):
    """Dòng kiểm tự động: `trigger_tu_dong` (nếu có) · dòng `trigger` không tác giả (builder D2; dòng tác giả ở
    `trigger_phan_doan`) · hoặc phần chấm máy (chi_tiet) của dòng tác giả ở builder cũ. Trả [(mau_id, trang_thai,
    nguong)], khử trùng theo mau_id. Nhãn/hàm ý hiển thị lấy từ TU_DONG (một luật hiển thị cho mọi bản builder)."""
    tr = hs.get("trigger_tu_dong")
    if isinstance(tr, list):
        src = [(r.get("mau_id"), r.get("trang_thai"), r.get("nguong") or {}) for r in tr if isinstance(r, dict)]
    else:
        tr = [r for r in hs.get("trigger") or [] if isinstance(r, dict)]
        src = [(r.get("mau_id"), r.get("trang_thai"), r.get("nguong") or {}) for r in tr if not r.get("tac_gia")]
        if not src:
            src = [(x.get("mau_id"), x.get("trang_thai"), r.get("nguong") or {}) for r in tr
                   for x in r.get("chi_tiet") or [] if isinstance(x, dict)]
    seen, out = set(), []
    for mid, tt, ng in src:
        if isinstance(mid, str) and mid not in seen:
            seen.add(mid)
            out.append((mid, tt, ng))
    return out


def hang_nhom(loai, dk, hy, mau):
    """Hàng đầu nhóm của bảng 3 cột (Qt chưa có dòng gộp cột): chữ hoa ở cột 1, vạch trái màu nhóm."""
    return dong({"loai": loai, "dk": dk, "hy": hy}, mau={"loai": mau, "dk": "dim", "hy": "dim"}, vien=mau)


def b_trigger(t, hs, nd):
    """Trigger kiểu Artifact: 3 cột (Loại tín hiệu | Điều kiện kiểm được | Hàm ý), hai nhóm có hàng đầu nhóm:
    (1) ảnh chụp tác giả — nguyên văn, không chấm sống; (2) kiểm tự động EST — trạng thái là tiền tố [CHƯA] /
    [ĐẠT · CỔNG dừng] / [CẦN DATA] ở cột Loại (màu theo trạng thái), lý do dài ở tooltip ô."""
    mau = {m.get("id"): m for m in t.cfg.get("trigger_mau") or [] if isinstance(m, dict)}
    dung, tv, rows = bool(g(hs, "cong", "dung")), trong_tv(hs), []
    tp = hs.get("trigger_phan_doan") if isinstance(hs.get("trigger_phan_doan"), dict) else {}
    nd_tg = nd if (nd or {}).get("trigger") else (tp if tp.get("tac_gia") and tp.get("ngay") else None)
    dong_tg = [r for r in (nd_tg or {}).get("trigger") or (nd_tg or {}).get("dong") or [] if isinstance(r, dict)]
    if dong_tg:
        rows.append(hang_nhom(pd_nhan(nd_tg).upper(), "Ảnh chụp nguyên văn — không chấm trạng thái sống",
                              pd_tuoi(nd_tg, t.now), "violet"))
        rows += [dong({"loai": tron(r.get("loai")), "dk": tron(r.get("dieu_kien")), "hy": tron(r.get("ham_y"))},
                      mau={"loai": "bear" if r.get("mau") == "down" else ""}) for r in dong_tg]
    dem, tu = {"dat": 0, "chua": 0, "CAN_DATA": 0}, dong_tu_dong(hs)
    if tu:
        rows.append(hang_nhom("KIỂM TỰ ĐỘNG · EST · TUẦN %s" % dm(hs.get("tuan_cuoi")),
                              "Điều kiện trung tính trên số của hồ sơ — không phải khuyến nghị",
                              "CỔNG sống DỪNG: «đạt» không kết luận" if dung else "đo lường", "amber"))
    for mid, tt, ng in tu:
        m = mau.get(mid) or {}
        loai, hy = TU_DONG.get(mid, (m.get("loai_trung_tinh") or m.get("loai") or mid,
                                     m.get("ham_y_lang_kinh") or m.get("ham_y_trang_thai") or CO))
        tip = {}
        if tt == "dat":
            pre, mu = ("[ĐẠT · CỔNG dừng]" if dung else "[ĐẠT]"), "warn"
            tip["loai"] = "đạt (CỔNG đang dừng — không kết luận)" if dung else "đạt"
        elif tt == "chua":
            pre, mu = "[CHƯA]", ""
        else:
            thieu = [FACT.get(k, k) for k, v in ng.items() if v is None] or ["vế không kiểm máy được"]
            pre, mu, tt = "[CẦN DATA]", "bear", "CAN_DATA"
            tip["loai"] = "thiếu " + ", ".join(thieu)
            t.thieu.append(("trigger." + mid, "thiếu " + ", ".join(thieu)))
        dem[tt] = dem.get(tt, 0) + 1
        rows.append(dong({"loai": "%s %s" % (pre, hau_to(loai, tv)), "dk": dk_text(m, ng) if m else CO,
                          "hy": hau_to(hy, tv)}, mau={"loai": mu}, tip=tip))
    chua_cham = [k for k, m in mau.items() if m.get("ap_dung") == "moi_ma" and k not in {x[0] for x in tu}]
    if tu and chua_cham:
        t.thieu.append(("trigger.tu_dong", "builder chưa chấm mẫu " + ", ".join(chua_cham)))
    tit = ("%d dòng tác giả · " % len(dong_tg) if dong_tg else "") + "%d kiểm tự động: %d đạt · %d chưa · %d CẦN DATA" % (
        len(tu), dem["dat"], dem["chua"], dem["CAN_DATA"])
    cap = ("✓/✗ ở từng vế là phép so của chính số builder ghi lúc chấm; trạng thái dòng là của builder. Tên pattern "
           "ngoài 30 mã Toàn Vũ mang hậu tố ? (Hard Rule #16).")
    blk = {"type": "table", "wrap": True, "row_link": False, "caption": cap, "rows": rows,
           "cols": [cot("loai", "Loại tín hiệu", "left"), cot("dk", "Điều kiện kiểm được", "left"),
                    cot("hy", "Hàm ý", "left")]}
    return sec(blk, "Trigger · điều kiện kiểm được → hàm ý", tit)  # trạng thái CỔNG: dải trên cùng + hàng đầu nhóm
