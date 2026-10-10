#!/usr/bin/env python3
"""
Fincept Terminal — Lăng kính: lớp "Câu chuyện chủ thể" (CONTRACT_DELTA V4.0–V4.4).

Chỉ HIỂN THỊ bản tuyển chọn `ma.<mã>.cau_chuyen` mà bridge (fft_cauchuyen.py) đã kiểm hợp lệ và tính vùng giá:
không viết nhận định, không nâng bậc, không tính lại VWAP / lệch so giá nay. Dựng:
  · block `story` (thẻ infographic: chủ thể · động cơ · điểm gãy · thước vùng giá) và `timeline` (dòng thời gian);
  · chú thích chart FFT × Giá: vạch dọc từng sự kiện, dải ngang vùng gom (trục giá), thoi tại (ngày, vùng giá);
  · view `cauchuyen` theo rổ VN30/VN100.
Màu sự kiện theo loại: gom/thâu tóm/đấu giá = cyan · bán = amber · phát hành/tăng vốn = info · pháp lý/cầm cố = warn ·
khác = dim — KHÔNG bao giờ bull/bear (tránh ngụ ý mua/bán). Mục UNVERIFIED hiển thị kèm "không dùng cho quyết định";
mục thiếu nguồn không hiển thị (V4.0: không truy được → không đưa vào). Mọi khoá tuỳ chọn — thiếu lớp thì trả rỗng /
[CẦN DATA]. Stdlib only; Python 3.11 và 3.14.
"""
import html
from datetime import date, datetime, timedelta, timezone

from fincept_langkinh_base import (CO, bang, cot, dm_tag, dmy, ds_chu, g, gia, ghi, ms, ngay, phang, pp, so, so_num,
                                   the)
from fincept_langkinh_chuthe import BAC_THU_TU, bac_yeu, cong_dung
from fincept_langkinh_views import diem, thang

TAM_DUNG = "tạm dùng dữ liệu sẵn có, chưa nghiên cứu web mới"
KHONG_QD = "không dùng cho quyết định"
CONG_DUNG = "CỔNG chưa xác định — không kết luận per-mã"
# loại sự kiện (V4.1) → (động từ hiển thị, màu mốc V4.3)
LOAI = {"mua": ("mua", "cyan"), "dang_ky_mua": ("đăng ký mua", "cyan"), "thau_tom": ("thâu tóm", "cyan"),
        "dau_gia": ("đấu giá", "cyan"), "ban": ("bán", "amber"), "dang_ky_ban": ("đăng ký bán", "amber"),
        "phat_hanh": ("phát hành", "info"), "tang_von": ("tăng vốn", "info"), "phap_ly": ("pháp lý", "warn"),
        "cam_co": ("cầm cố", "warn"), "chuyen_nhuong": ("chuyển nhượng", "dim"), "khac": ("sự kiện khác", "dim")}
GIAO_DICH = ("mua", "dang_ky_mua", "thau_tom", "dau_gia", "ban", "dang_ky_ban", "chuyen_nhuong")  # thiếu giá = CẦN DATA
MAX_VLINE, VLINE_UU_TIEN_1 = 8, 4  # ≤8 sự kiện gần nhất trên chart; 4 gần nhất có nhãn ưu tiên 1
TOI_DA_CHU_THICH = 28
MAX_TL_RO = 20  # dòng thời gian gộp của rổ
# Sự kiện TỰ ĐỘNG (job fft_tin, cờ `tu_dong`): chỉ lấp chỗ trống, không lấn bản tuyển chọn
MAX_TD_TL = 12                   # dòng thời gian một mã: ≤12 sự kiện tự động mới nhất
MAX_TD_THOI = 4                  # thoi vùng giá: ≤4 sự kiện tự động mới nhất
MAX_TD_RO, TD_RO_NGAY = 8, 30    # dòng thời gian rổ: ≤8 sự kiện tự động FACT-T1/T2 trong 30 ngày
TD_BANG_NGAY = 90                # bảng view cauchuyen: sự kiện tự động trong 90 ngày
LOAI_TD_CHART = ("dang_ky_mua", "dang_ky_ban", "mua", "ban", "phat_hanh", "tang_von", "chuyen_nhuong", "cam_co")
ICT = timezone(timedelta(hours=7))
TT_MAU = {"LIVE": "info", "STALE": "amber", "DEAD": "warn", "MANUAL": "dim"}
TEN_NGUON = {"vc_iq360": "GD nội bộ 360 · Vietcap", "vc_noibo": "GD nội bộ 14 ngày · Vietcap", "vc_su_kien": "ISS · ĐHĐCĐ · Vietcap", "sz_su_kien": "ĐHCĐ · PH · Simplize",
             "vnf": "PDF gốc · VN_Filings", "sz_noibo_cu": "Insider · Simplize", "vc_tin_bao": "Tin báo theo mã"}
HE_QUA = {"vc_iq360": "giao dịch nội bộ có khối lượng (đăng ký và đã thực hiện) đứng yên — tệp 360 chạy tay, "
                      "không có lịch tự động",
          "vc_noibo": "đăng ký giao dịch nội bộ/cổ đông lớn mới có thể thiếu",
          "vc_su_kien": "sự kiện ĐHĐCĐ/phát hành có thể thiếu (mã rỗng do bị chặn tần suất; ~20 mã VN100 ngoài vũ trụ "
                        "collector)",
          "sz_su_kien": "ĐKCC ĐHCĐ/phát hành kèm PDF có thể thiếu (collector chỉ 28 mã)",
          "vnf": "NQ ĐHĐCĐ/HĐQT, BCTN mới chưa về máy",
          "sz_noibo_cu": "khối lượng + giá GD nội bộ sau 18/05/2026 [CẦN DATA]",
          "vc_tin_bao": "tin báo mới có thể thiếu (UNVERIFIED, chỉ để theo dõi)"}
V5 = (("buc_tranh", "Bức tranh tổng thể"), ("thau_tom", "Ai đang thâu tóm"), ("muc_dich_keo", "Mục đích kéo giá"),
      ("doi_co_dong", "Đổi cổ đông"), ("noi_bo_tom_tat", "Nội bộ gần nhất"))
LUAT = (
    "Tạm dùng dữ liệu sẵn có, chưa nghiên cứu web mới — chỉ tài liệu/dữ liệu đã có trên máy; không dùng tệp hệ BERI.",
    "Mỗi mục mang đúng một bậc: FACT-T1 (CBTT/BCTC gốc) > FACT-T2 (vendor: Vietcap ISS, CapIQ, VCI) > SS-T3 (Toàn Vũ, "
    "sell-side, báo cáo HĐCV/Cowork dựa nguồn) > EST (tự ước, có ghi logic) > UNVERIFIED (một nguồn báo chí, digest "
    "LLM, không truy được) — UNVERIFIED chỉ để theo dõi, không dùng cho quyết định.",
    "Mỗi mục có nguồn (tệp:dòng hoặc tệp + khoá JSON); không truy được → không đưa vào.",
    "Vùng giá sự kiện: nguồn nêu giá → giá nguồn (bậc của nguồn); nguồn chỉ nêu cửa sổ thời gian → EST = VWAP "
    "(Σ close·KL ÷ Σ KL, giá điều chỉnh CA từ KHO) + dải P25–P75 của close trong cửa sổ; không có cả hai → "
    "[CẦN DATA] vùng giá.",
    "Vùng gom ước tính (cấp mã, EST) = gộp các sự kiện gom/thâu tóm/đấu giá có vùng giá, trừ UNVERIFIED; lệch = giá "
    "đóng cửa phiên cuối ÷ VWAP gộp − 1.",
    "Động cơ và điểm gãy viết trung tính, có nguồn; điểm gãy là điều kiện kiểm được. Không phải khuyến nghị mua/bán.",
    "Sự kiện [tự động] (job fft_tin, 10 phút/lượt) đọc nguồn trên máy: Vietcap IQ (đăng ký GD nội bộ, ISS, ĐHĐCĐ), "
    "Simplize (ĐKCC kèm PDF), VN_Filings (NQ gốc), tin báo (UNVERIFIED). Bản tuyển chọn luôn thắng khi trùng. ĐĂNG KÝ "
    "chưa phải đã giao dịch — vùng giá cửa sổ là giả định; sự kiện tự động không góp vào vùng gom.")


def e(s):
    return html.escape(str(s), quote=False)


def chu(v):
    return v.strip() if isinstance(v, str) else ""


def bac_of(x):
    """Bậc hợp lệ của một mục; thiếu/sai → UNVERIFIED (không bao giờ nâng bậc)."""
    b = x.get("bac") if isinstance(x, dict) else None
    return b if b in BAC_THU_TU else "UNVERIFIED"


def kqd(text, bac):
    """Mục UNVERIFIED luôn mang 'không dùng cho quyết định' ngay trong chữ hiển thị."""
    if bac != "UNVERIFIED":
        return text
    return "%s · %s" % (text, KHONG_QD) if text and text != CO else KHONG_QD


def sl(n, ngan=False):
    """Số cổ phần: 5.000.000 → '5 tr cp' (ngan: '5tr') · 2.500.000 → '2,5 tr cp' · 250.000 → '250 nghìn cp'."""
    n = so_num(n)
    if n is None or n <= 0:
        return ""
    for chia, dai, gon in ((1e6, " tr cp", "tr"), (1e3, " nghìn cp", "k")):
        if n >= chia:
            v = n / chia
            return so(v, 0 if v >= 100 or float(round(v, 1)).is_integer() else 1) + (gon if ngan else dai)
    return so(n, 0) + ("" if ngan else " cp")


def ngan_ten(s, toi_da=14):
    s = chu(s)
    if len(s) <= toi_da:
        return s
    cat = s[:toi_da].rsplit(" ", 1)[0] if " " in s[:toi_da] else s[:toi_da]
    return cat.rstrip(" ,·(-") + "…"


def k_range(lo, hi):
    """58.000–64.000 → '58–64k' · 43.800–46.900 → '43,8–46,9k'."""
    a, b = lo / 1000.0, hi / 1000.0
    nd = 0 if float(round(a, 1)).is_integer() and float(round(b, 1)).is_integer() else 1
    return "%s–%sk" % (so(a, nd), so(b, nd))


# ───────────────────────────── đọc lớp câu chuyện (chỉ hiển thị) ─────────────────────────────

def cc_of(c, s):
    cc = g(c.ma, s, "cau_chuyen")
    return cc if isinstance(cc, dict) else {}


def nguon_cc(c):
    n = g(c.lk, "nguon", "cau_chuyen")
    return n if isinstance(n, dict) else {}


def _ds(cc, k):
    v = cc.get(k)
    return v if isinstance(v, list) else []


def chu_the_ds(cc):
    """→ (chip chủ thể hiển thị được, số mục bỏ vì thiếu tên/nguồn)."""
    ok, bo = [], 0
    for x in _ds(cc, "chu_the"):
        if not (isinstance(x, dict) and chu(x.get("ten")) and chu(x.get("nguon"))):
            bo += 1
            continue
        b = bac_of(x)
        ok.append({"ten": chu(x["ten"]), "vai_tro": kqd(chu(x.get("vai_tro")) or CO, b),
                   "so_huu": chu(x.get("so_huu")) or CO, "bac": b,
                   "tip": kqd("nguồn: %s · bậc %s" % (chu(x["nguon"]), b), b)})
    return ok, bo


def su_kien(cc, s):
    """Sự kiện có nguồn → [{sym, d (date|None), uoc, loai, bac, e}]. Thiếu ngày → mép cuối cửa sổ, đánh dấu ước."""
    out = []
    for x in _ds(cc, "su_kien"):
        if not isinstance(x, dict) or not chu(x.get("nguon")):
            continue
        d, uoc = ngay(x.get("ngay")), bool(x.get("ngay_uoc"))
        if d is None:
            d = ngay(g(x, "cua_so", "den"))
            uoc = uoc or d is not None
        out.append({"sym": s, "d": d, "uoc": uoc, "loai": x.get("loai") if x.get("loai") in LOAI else "khac",
                    "bac": bac_of(x), "e": x, "td": bool(x.get("tu_dong"))})
    return out


def sap(evs):
    """Ngày giảm dần; sự kiện không rõ ngày xuống cuối."""
    return sorted(evs, key=lambda v: (v["d"] is not None, v["d"] or date.min, v["sym"], chu(v["e"].get("id"))),
                  reverse=True)


def co_cau_chuyen(cc):
    """Có câu chuyện TUYỂN CHỌN — khối `chi_tu_dong` (chỉ sự kiện tự động) không tính."""
    if cc.get("chi_tu_dong"):
        return False
    return bool(chu(cc.get("tieu_de")) or any(not v["td"] for v in su_kien(cc, "")) or chu_the_ds(cc)[0]
                or isinstance(cc.get("dong_co"), dict))


def co_tu_dong(cc):
    return any(v["td"] for v in su_kien(cc, ""))


# ───────────────────────────── độ tươi nguồn tin (job fft_tin) — tuổi tính LÚC MỞ ─────────────────────────────

def nguon_tin(c):
    ds = nguon_cc(c).get("nguon_tin")
    return [n for n in ds if isinstance(n, dict)] if isinstance(ds, list) else []


def tuoi_gio(n, now):
    try:
        m = datetime.fromisoformat(str(n.get("moi_nhat")))
    except (TypeError, ValueError):
        return None
    return (now - (m if m.tzinfo else m.replace(tzinfo=ICT))).total_seconds() / 3600


def trang_thai_nay(n, now):
    """Luật src3.md §2.7: DEAD khi lỗi/chết/không có mốc/tuổi > 4×ngưỡng · STALE khi tuổi > ngưỡng · còn lại LIVE."""
    t, ng = tuoi_gio(n, now), so_num(n.get("nguong_gio"))
    if n.get("loi") or n.get("chet") or t is None or ng is None or t > 4 * ng:
        return "DEAD"
    return "STALE" if t > ng else "LIVE"


def tuoi_chu(t):
    if t is None:
        return CO
    if t < 1:
        return "%d phút" % max(0, round(t * 60))
    return "%s giờ" % so(t, 1) if t < 48 else "%s ngày" % so(t / 24, 1)


def _ten_nguon(n):
    return TEN_NGUON.get(n.get("id"), chu(n.get("id")) or CO)


def khoi_nguon_tin(c, now=None):
    """View cauchuyen: tiles ĐỘ TƯƠI NGUỒN TIN (mỗi nguồn một thẻ + thẻ lúc dựng) + note cảnh báo nguồn STALE/DEAD."""
    ds = nguon_tin(c)
    if not ds:
        return []
    now = now or datetime.now(ICT)
    td = nguon_cc(c).get("tu_dong") if isinstance(nguon_cc(c).get("tu_dong"), dict) else {}
    tiles, xau = [], []
    for n in ds:
        tt = trang_thai_nay(n, now)
        tiles.append(the(_ten_nguon(n).upper(), tuoi_chu(tuoi_gio(n, now)), "%s · %s · phủ %s" % (
            tt, n.get("bac") or CO, n.get("phu_vn100") or CO), TT_MAU[tt], ""))
        if tt != "LIVE":
            ly = chu(n.get("chet")) or chu(n.get("loi")) or "tuổi %s > ngưỡng %s giờ" % (
                tuoi_chu(tuoi_gio(n, now)), so(n.get("nguong_gio"), 0))
            xau.append("<b>%s</b> — %s: %s. Hệ quả: %s." % (e(_ten_nguon(n)), tt, e(ly), e(HE_QUA.get(n.get("id"), CO))))
    tiles.append(the("LỚP TỰ ĐỘNG DỰNG", chu(td.get("cap_nhat")) or CO, "fft_tin · %s sự kiện · %s mã · %s bị bản "
                     "tuyển chọn thay" % (pp(td.get("n_su_kien")), pp(td.get("n_ma")), pp(td.get("n_bi_an"))), "dim", ""))
    out = [{"type": "tiles", "title": "Độ tươi nguồn tin — tuổi tính lúc mở", "items": tiles}]
    if xau:
        out.append(ghi("Nguồn tin chưa LIVE", "<br>".join(xau), "Nguồn", "warn"))
    return out


def dong_nguon_tin(c, now=None):
    """View chuoi: một dòng độ tươi nguồn tin dưới dòng thời gian."""
    ds = nguon_tin(c)
    if not ds:
        return None
    now = now or datetime.now(ICT)
    tt = [(n, trang_thai_nay(n, now)) for n in ds]
    return ghi("Độ tươi nguồn tin (tính lúc mở)", " · ".join("%s %s <b>%s</b>" % (
        e(_ten_nguon(n)), e(tuoi_chu(tuoi_gio(n, now))), t) for n, t in tt), "Nguồn",
        "amber" if any(t != "LIVE" for _, t in tt) else "dim")


def nguon_tin_rows(c, now=None):
    """View nguon: mỗi nguồn tin một hàng (Thành phần, Nguồn, Bậc, Mốc dữ liệu, Độ phủ)."""
    now = now or datetime.now(ICT)
    return [("Tin tự động · %s" % _ten_nguon(n), chu(n.get("tep")) or CO, n.get("bac") or CO,
             "%s · tuổi %s" % (chu(n.get("moi_nhat"))[:16].replace("T", " ") or CO, tuoi_chu(tuoi_gio(n, now))),
             " · ".join(t for t in (trang_thai_nay(n, now), "phủ %s" % (n.get("phu_vn100") or CO),
                                    "%s sự kiện" % pp(n.get("n_su_kien")), chu(n.get("lich")),
                                    chu(n.get("chet")) or chu(n.get("loi")), chu(n.get("ghi_chu"))) if t))
            for n in nguon_tin(c)]


def sections_v5(cc):
    """DELTA V5.1 — mục 'Bức tranh tổng thể'… của thẻ story; thiếu chữ → bỏ mục (bridge đã kiểm bậc/nguồn)."""
    out = []
    for k, t in V5:
        x = cc.get(k)
        if not (isinstance(x, dict) and chu(x.get("text"))):
            continue
        b = bac_of(x)
        ng = x.get("nguon")
        ng = "; ".join(chu(n) for n in ng if chu(n)) if isinstance(ng, list) else chu(ng)
        out.append({"title": t, "text": kqd(chu(x["text"]), b), "bac": b,
                    "tip": kqd("nguồn: %s · bậc %s" % (ng or CO, b), b)})
    return out


def dem_bac(evs, du=False):
    d = {b: sum(1 for v in evs if v["bac"] == b) for b in BAC_THU_TU}
    return " · ".join("%s %d" % (b, d[b]) for b in BAC_THU_TU if du or d[b])


def vung_ev(x, loai):
    """Vùng giá một sự kiện → (chữ hiển thị, tung độ cho thoi | None, chữ tooltip)."""
    vg = x.get("vung_gia") if isinstance(x.get("vung_gia"), dict) else {}
    logic = chu(vg.get("logic"))
    if so_num(vg.get("gia")) is not None:
        b = bac_of(vg)
        return "%s (%s)" % (gia(vg["gia"]), b), vg["gia"], "giá nguồn %s (%s)%s" % (
            gia(vg["gia"]), b, " · " + logic if logic else "")
    if so_num(vg.get("vwap")) is not None:
        b = bac_of(vg)
        p = (" · P25–P75 %s–%s" % (gia(vg["p25"]), gia(vg["p75"]))
             if so_num(vg.get("p25")) is not None and so_num(vg.get("p75")) is not None else "")
        tip = "VWAP ~%s%s · min–max %s–%s · %s phiên %s → %s (%s)%s" % (
            gia(vg["vwap"]), p, gia(vg.get("lo")), gia(vg.get("hi")), pp(vg.get("n_phien")), dmy(vg.get("tu")),
            dmy(vg.get("den")), b, " · " + logic if logic else "")
        return "~%s (%s)%s" % (gia(vg["vwap"]), b, p), vg["vwap"], tip
    ly = chu(x.get("vung_gia_ly_do")) or chu(vg.get("ly_do")) or chu(vg.get("loi"))
    if "chưa diễn ra" in ly:  # đăng ký có cửa sổ ở tương lai — không phải thiếu dữ liệu
        return "cửa sổ chưa diễn ra", None, ly
    if loai in GIAO_DICH:
        return "[CẦN DATA] vùng giá", None, ly or "[CẦN DATA] vùng giá — nguồn không nêu cửa sổ/giá"
    return CO, None, ly


def vung_ma(c, s, cc):
    """Thước vùng giá của thẻ story = `vung_gia_gom` của bridge (không tính lại); thiếu lo/hi → None."""
    gom = cc.get("vung_gia_gom")
    if not isinstance(gom, dict) or so_num(gom.get("lo")) is None or so_num(gom.get("hi")) is None:
        return None
    m = c.ma.get(s) or {}
    nay = next((v for v in (so_num(gom.get("nay")), so_num(g(m, "phien", "close")), so_num(g(m, "tuan", "close")))
                if v is not None), None)
    ids = ", ".join(str(x) for x in gom.get("su_kien") or [] if isinstance(x, (str, int)))
    logic = " · ".join(t for t in (chu(gom.get("logic")), "sự kiện góp: " + ids if ids else "",
                                   "giá nay = đóng cửa %s" % dmy(gom["ngay_nay"]) if gom.get("ngay_nay") else "") if t)
    return {"lo": min(gom["lo"], gom["hi"]), "hi": max(gom["lo"], gom["hi"]), "vwap": so_num(gom.get("vwap")),
            "nay": nay, "lech_pct": so_num(gom.get("lech_nay_pct")),
            "bac": gom["bac"] if gom.get("bac") in BAC_THU_TU else "EST", "nhan": "Vùng gom ước tính", "logic": logic}


# ───────────────────────────── block story · timeline ─────────────────────────────

def muc_tl(ev, ro=False):
    """Một mục dòng thời gian (V4.3); ro = dòng thời gian gộp của rổ (chủ thể mang tiền tố mã + link)."""
    x, b = ev["e"], ev["bac"]
    dt, mau = LOAI[ev["loai"]]
    q = sl(x.get("so_luong_cp"))
    gchu, _, gtip = vung_ev(x, ev["loai"])
    ten = chu(x.get("chu_the")) or ("(nguồn không nêu chủ thể)" if ev.get("td") else "[CẦN DATA] chủ thể")
    cs = x.get("cua_so") if isinstance(x.get("cua_so"), dict) else {}
    tip = " · ".join(t for t in (
        "nguồn: " + chu(x.get("nguon")), "bậc " + b, "id " + chu(x.get("id")) if chu(x.get("id")) else "",
        "cửa sổ nguồn %s → %s" % (dmy(cs.get("tu")), dmy(cs.get("den"))) if cs.get("tu") else "", gtip,
        "ngày ước" if ev["uoc"] else "", "tự động (job fft_tin)" if ev.get("td") else "",
        "tệp/link: " + chu(x.get("link")) if chu(x.get("link")) else "") if t)
    it = {"ngay": dmy(ev["d"]), "ngay_uoc": ev["uoc"], "chu_the": "%s · %s" % (ev["sym"], ten) if ro else ten,
          "hanh_dong": dt[0].upper() + dt[1:] + (" " + q if q else ""), "mo_ta": kqd(chu(x.get("mo_ta")), b),
          "gia": gchu, "bac": b, "mau": mau, "tip": kqd(tip, b)}
    if ro:
        it["link"] = ev["sym"]
    return it


def khoi_story(c, s):
    cc, m = cc_of(c, s), c.ma.get(s) or {}
    evs = su_kien(cc, s)
    cts, bo = chu_the_ds(cc)
    bo += sum(1 for x in _ds(cc, "su_kien") if not isinstance(x, dict) or not chu(x.get("nguon")))
    dc = cc.get("dong_co")
    if isinstance(dc, dict) and chu(dc.get("text")) and chu(dc.get("nguon")):
        b = bac_of(dc)
        dong_co = {"text": kqd(chu(dc["text"]), b), "bac": b,
                   "tip": kqd("nguồn: %s · bậc %s" % (chu(dc["nguon"]), b), b)}
    else:
        bo += 1 if isinstance(dc, dict) else 0
        dong_co = {"text": "[CẦN DATA] động cơ — chưa có trong nguồn đã tuyển", "bac": "", "tip": ""}
    dg = cc.get("diem_gay")
    diem_gay = {"text": kqd(chu(dg["text"]), bac_of(dg)), "bac": bac_of(dg)} if isinstance(dg, dict) and chu(
        dg.get("text")) else None
    canh = ds_chu(cc.get("canh_bao"))
    if bo:
        canh.append("%d mục thiếu tên/nguồn — không hiển thị (V4.0: không truy được → không đưa vào)" % bo)
    n_unv = sum(1 for b in [x["bac"] for x in cts] + [v["bac"] for v in evs] + [dong_co["bac"]] +
                ([diem_gay["bac"]] if diem_gay else []) if b == "UNVERIFIED")
    if n_unv:
        canh.append("%d mục UNVERIFIED — chỉ để theo dõi, %s" % (n_unv, KHONG_QD))
    if cong_dung(c.cong):
        canh.append(CONG_DUNG)
    tc = [v for v in evs if not v["td"]]
    ncc, dem = nguon_cc(c), dem_bac(tc)
    sub = " · ".join(t for t in (chu(m.get("ten")), "danh mục " + dm_tag(m) if dm_tag(m) else "",
                                 "%d sự kiện%s" % (len(tc), " (%s)" % dem if dem else ""),
                                 "+%d tự động" % (len(evs) - len(tc)) if len(evs) > len(tc) else "",
                                 "tệp %s" % dmy(ncc["cap_nhat"]) if ncc.get("cap_nhat") else "", TAM_DUNG) if t)
    return {"type": "story", "ma": s, "tieu_de": chu(cc.get("tieu_de")) or "[CẦN DATA] tiêu đề câu chuyện", "sub": sub,
            "chu_the": cts, "dong_co": dong_co, "vung_gia": vung_ma(c, s, cc), "diem_gay": diem_gay,
            "cau_hoi_mo": ds_chu(cc.get("cau_hoi_mo")), "canh_bao": canh, "link": s, "sections": sections_v5(cc)}


def khoi_chuoi(c, s):
    """View `chuoi` (V4.4 + fft_tin): story (chỉ khi có bản tuyển chọn) · timeline gộp (tuyển chọn + ≤12 sự kiện tự
    động mới nhất) · dòng độ tươi nguồn tin. Không có câu chuyện lẫn sự kiện tự động → []."""
    cc = cc_of(c, s)
    evs = sap(su_kien(cc, s))
    tc, td = [v for v in evs if not v["td"]], [v for v in evs if v["td"]]
    co = co_cau_chuyen(cc)
    if not co and not td:
        return []
    out = [khoi_story(c, s)] if co else [ghi(
        "Chưa có câu chuyện tuyển chọn — %s" % s,
        "Chỉ có %d sự kiện tự động từ nguồn trên máy (job fft_tin). Chủ thể · động cơ · điểm gãy [CẦN DATA] — "
        "không tự suy từ sự kiện." % len(td), "Tự động", "dim")]
    items = sap(tc + td[:MAX_TD_TL])
    if items:
        out.append({"type": "timeline", "title": "Dòng thời gian — %s" % s,
                    "sub": "%d sự kiện%s · ngày giảm dần · ~ = ngày ước · bậc theo từng mục · %s" % (
                        len(tc), " + %d/%d tự động mới nhất" % (min(len(td), MAX_TD_TL), len(td)) if td else "",
                        TAM_DUNG), "items": [muc_tl(v) for v in items]})
    dn = dong_nguon_tin(c)
    if dn:
        out.append(dn)
    return out


# ───────────────────────────── chú thích chart FFT × Giá ─────────────────────────────

def ann_chuoi(c, s, x0, x1):
    """V4.4 — vạch dọc cho ≤8 sự kiện gần nhất trong khung trục (4 gần nhất ưu tiên 1), thoi tại (ngày, vùng giá sự
    kiện) trên trục giá (chỉ marker + tooltip), dải ngang vùng gom (trục phải) khi có `vung_gia_gom`."""
    cc = cc_of(c, s)
    out = []
    trong = [v for v in su_kien(cc, s) if v["d"] and x0 <= ms(v["d"]) <= x1]
    tc = sap([v for v in trong if not v["td"]])[:MAX_VLINE] if co_cau_chuyen(cc) else []
    td = sap([v for v in trong if v["td"] and v["loai"] in LOAI_TD_CHART])[:MAX_VLINE - len(tc)]
    # tuyển chọn trước (4 mới nhất ưu tiên 1); tự động chỉ lấp chỗ trống, ưu tiên 2, thoi cho ≤4 mục mới nhất
    for r, v in enumerate(tc + td):
        x, xm, la_td = v["e"], ms(v["d"]), r >= len(tc)
        dt, mau = LOAI[v["loai"]]
        ten, q = chu(x.get("chu_the")) or ("" if la_td else "[CẦN DATA] chủ thể"), sl(x.get("so_luong_cp"))
        tl = so_num(x.get("ty_le_pct"))
        if la_td and not ten:  # sự kiện tự động không nêu chủ thể: nhãn = hành động + tỉ lệ (vd "phát hành 0,7%")
            q = q or ("%s%%" % so(tl, 1 if tl < 10 else 0) if tl is not None else "")
        sub = ("~" if v["uoc"] else "") + thang(v["d"].isoformat()) + (" · UNVERIFIED" if v["bac"] == "UNVERIFIED"
                                                                        else "") + (" · tự động" if la_td else "")
        gchu, y, gtip = vung_ev(x, v["loai"])
        tip = " · ".join(t for t in (
            "%s %s%s" % (ten, dt, " " + q if q else ""), dmy(v["d"]) + (" (ước)" if v["uoc"] else ""),
            chu(x.get("mo_ta")), "giá " + gchu if gchu != CO else "", "bậc " + v["bac"],
            "nguồn: " + chu(x.get("nguon"))) if t)
        out.append({"kind": "vline", "x": xm, "mau": mau,
                    "text": " ".join(t for t in (ngan_ten(ten), dt, sl(x.get("so_luong_cp"), True) or q) if t),
                    "sub": sub, "tip": kqd(tip, v["bac"]), "style": "dot",
                    "uu_tien": 1 if r < VLINE_UU_TIEN_1 and not la_td else 2})
        if y is not None and (not la_td or r - len(tc) < MAX_TD_THOI):
            out.append(diem(xm, y, gchu.split(" · ")[0], sub, kqd("Vùng giá sự kiện · %s · %s" % (tip, gtip), v["bac"]),
                            "diamond", mau, "above", 3, "right"))
    vg = vung_ma(c, s, cc)
    if vg and vg["hi"] > vg["lo"]:
        out.append({"kind": "hband", "y0": vg["lo"], "y1": vg["hi"], "axis": "right", "mau": "amber", "alpha": 0.14,
                    "text": "%s %s (%s)" % (vg["nhan"], k_range(vg["lo"], vg["hi"]), vg["bac"]),
                    "tip": "%s %s–%s · VWAP %s · nay %s (%s so VWAP) · %s · %s" % (
                        vg["nhan"], gia(vg["lo"]), gia(vg["hi"]), gia(vg["vwap"]), gia(vg["nay"]),
                        so(vg["lech_pct"], 1, True) + "%" if vg["lech_pct"] is not None else CO, vg["bac"], vg["logic"]),
                    "uu_tien": 1})
    return out


def chu_thich_sub(ann):
    """Mệnh đề cho phụ đề chart FFT × Giá — chỉ nêu lớp thực sự có mặt."""
    k = {a.get("kind") for a in ann} | {a.get("marker") for a in ann}
    return "".join(t for c, t in (("vline", " · vạch dọc = sự kiện chủ thể"),
                                   ("diamond", " · thoi = vùng giá sự kiện"),
                                   ("hband", " · dải ngang = vùng gom ước tính (EST)")) if c in k)


def gioi_han(ann, them=(), toi_da=TOI_DA_CHU_THICH):
    """Tổng chú thích/chart ≤ toi_da (V4.4): bỏ trước ưu tiên 3 rồi 2, cũ trước; cùng hạng thì giữ lớp câu chuyện
    (`them`) trước; dải hband/xband (không mang uu_tien) coi như ưu tiên 1. Giữ nguyên thứ tự gốc."""
    if len(ann) <= toi_da:
        return ann
    ids = {id(a) for a in them}

    def moi(a):
        v = a.get("x", a.get("x1"))
        return v if isinstance(v, (int, float)) else float("inf")

    hang = sorted(range(len(ann)), key=lambda i: (ann[i].get("uu_tien", 1), id(ann[i]) not in ids, -moi(ann[i])))
    giu = set(hang[:toi_da])
    return [a for i, a in enumerate(ann) if i in giu]


# ───────────────────────────── 12 · cauchuyen ─────────────────────────────

COT_CC = [cot("ma", "Mã", "left"), cot("ngay", "Ngày", "left"), cot("ct", "Chủ thể", "left"),
          cot("hd", "Hành động", "left"), cot("gia", "Giá / vùng giá", "left"), cot("mo", "Mô tả", "left"),
          cot("bac", "Bậc", "left"), cot("ng", "Nguồn", "left")]


def v_cauchuyen(c):
    sc, n = c.scope, len(c.members)
    ncc = nguon_cc(c)
    co = [s for s in c.members if co_cau_chuyen(cc_of(c, s))]
    chua = [s for s in c.members if s not in co]
    evs = [v for s in co for v in su_kien(cc_of(c, s), s) if not v["td"]]
    evs_td = [v for s in c.members for v in su_kien(cc_of(c, s), s) if v["td"]]
    chi_td = [s for s in chua if co_tu_dong(cc_of(c, s))]
    hom_nay = date.today()
    vg = {s: vung_ma(c, s, cc_of(c, s)) for s in co}
    lech = {s: g(vg, s, "lech_pct") for s in co}
    ds = sorted(co, key=lambda s: (0 if so_num(g(c.ma, s, "dm", "nav")) else 1,
                                   -abs(lech[s]) if lech[s] is not None else float("inf"), s))
    n_unv, n_vg = sum(1 for v in evs if v["bac"] == "UNVERIFIED"), sum(1 for s in co if vg[s])
    tiles = [
        the("MÃ CÓ CÂU CHUYỆN", "%d/%d" % (len(co), n), "rổ %s · %s%s" % (
            sc, "toàn tệp %s mã · " % pp(ncc.get("n_ma")) if ncc else "", TAM_DUNG) if ncc or co else
            "[CẦN DATA] bridge chưa xuất lớp câu chuyện", "info" if co else "dim", ""),
        the("SỰ KIỆN THEO BẬC", str(len(evs)), dem_bac(evs, True) + (" · UNVERIFIED %s" % KHONG_QD if n_unv else ""),
            "warn" if n_unv else "", bac_yeu([v["bac"] for v in evs])),
        the("VÙNG GIÁ GOM", "%d/%d" % (n_vg, len(co)), "VWAP cửa sổ / giá nguồn gộp · lệch = giá nay ÷ VWAP − 1",
            "amber" if n_vg else "dim", "EST"),
        the("TỆP TUYỂN CHỌN", dmy(ncc["cap_nhat"]) if ncc.get("cap_nhat") else CO, " · ".join(t for t in (
            str(ncc.get("tep") or "").rsplit("/", 1)[-1], "phiên bản %s" % pp(ncc.get("phien_ban"))
            if so_num(ncc.get("phien_ban")) is not None else "", "%s sự kiện toàn tệp" % pp(ncc["n_su_kien"])
            if so_num(ncc.get("n_su_kien")) is not None else "") if t)
            or "fft_cauchuyen.json", "", ""),
        the("MÃ CHỈ CÓ SỰ KIỆN TỰ ĐỘNG", "%d/%d" % (len(chi_td), n), "%d sự kiện tự động trong rổ · job fft_tin · chưa "
            "có câu chuyện tuyển chọn" % len(evs_td), "dim", "")]
    blocks = [ghi("Luật bằng chứng — lớp câu chuyện (V4.0)", "<br>".join(e(x) for x in LUAT), "Bắt buộc", "info"),
              {"type": "tiles", "items": tiles}] + khoi_nguon_tin(c)
    loi = ds_chu(ncc.get("loi"))
    if not co:
        blocks.append(ghi("Chưa có lớp câu chuyện", "<br>".join(
            ["[CẦN DATA] chưa có mã nào trong rổ %s mang câu chuyện%s — chờ bản tuyển chọn fft_cauchuyen.json và goi_fft "
             "chạy lại." % (sc, "" if ncc else " (fft_langkinh.json chưa có nguon.cau_chuyen)")] +
            [e(x) for x in loi[:12]]), "Thiếu", "warn"))
    elif loi:
        blocks.append(ghi("Lỗi tệp tuyển chọn", "<br>".join(e(x) for x in loi[:12]) +
                          ("<br>… +%d lỗi khác" % (len(loi) - 12) if len(loi) > 12 else ""), "Kiểm", "warn"))
    blocks += [khoi_story(c, s) for s in ds]
    tl = sap([v for v in evs if v["d"]])[:MAX_TL_RO]
    tl_td = sap([v for v in evs_td if v["d"] and v["bac"] in ("FACT-T1", "FACT-T2")
                 and 0 <= (hom_nay - v["d"]).days <= TD_RO_NGAY])[:MAX_TD_RO]
    if tl or tl_td:
        blocks.append({"type": "timeline", "title": "Dòng thời gian gộp — %s" % sc,
                       "sub": "%d/%d sự kiện tuyển chọn mới nhất%s · ngày giảm dần · ~ = ngày ước · bấm mục để mở mã" % (
                           len(tl), len(evs), " + %d tự động FACT %d ngày gần nhất" % (len(tl_td), TD_RO_NGAY)
                           if tl_td else ""), "items": [muc_tl(v, True) for v in sap(tl + tl_td)]})
    if chua:
        blocks.append(ghi("Chưa có câu chuyện", "[CẦN DATA] %d mã chưa có câu chuyện tuyển chọn: %s.%s" % (
            len(chua), ", ".join(chua), " Trong đó %d mã đã có sự kiện tự động (mở mã để xem dòng thời gian)." % len(chi_td)
            if chi_td else ""), "Thiếu", "dim"))
    rows = [{"ma": v["sym"], "ngay": ("~" if v["uoc"] else "") + dmy(v["d"]), "ct": chu(v["e"].get("chu_the")) or CO,
             "hd": muc_tl(v)["hanh_dong"], "gia": vung_ev(v["e"], v["loai"])[0],
             "mo": kqd(chu(v["e"].get("mo_ta")), v["bac"]), "bac": v["bac"], "ng": chu(v["e"].get("nguon"))}
            for v in sap(evs + [v for v in evs_td if v["d"] and 0 <= (hom_nay - v["d"]).days <= TD_BANG_NGAY])]
    rows += [{"ma": s, "ngay": CO, "ct": CO, "hd": CO, "gia": CO, "mo": "[CẦN DATA] chưa có câu chuyện", "bac": "",
              "ng": CO} for s in chua]
    return {"title": "Câu chuyện chủ thể — %s" % sc,
            "sub": "Tuyển chọn thủ công + sự kiện tự động (fft_tin) · %s%s · bậc theo từng mục · không phải khuyến nghị" % (
                TAM_DUNG, " · tệp %s" % dmy(ncc["cap_nhat"]) if ncc.get("cap_nhat") else ""),
            "blocks": blocks, "data": phang(bang("", "", COT_CC, rows))}
