#!/usr/bin/env python3
"""
Fincept Terminal — SGI FA data service (Trạm Quan Trắc Vĩ Mô, phương pháp Lê Chí Phúc / SGI).

Feeds src/screens/sgi_fa/SgiFaPanel through EconomicsService / PythonRunner. Stdlib only;
runs on Python 3.9+. Makes NO network calls (never dulieukinhte.com/api/internal/*).

Three layers:
  1. Issue — one signed weekly JSON per kỳ (schema "sgi_ky/1"), passed through verbatim.
  2. Engine — recomputes deep-macro-sgi SKILL §7 (composites → regime → cash band → overrides)
     and §5 (bottom conditions) from the issue's own block scores, and audits the issue's claims.
  3. Live — overlays local data (series store, bridge JSON, vnstore SQLite). Issue numbers stay
     the issue's; live numbers carry their own date, source and tier. Nothing is overwritten.

Inputs (read-only; env overrides are used by the tests):
    SGI_ISSUE_DIR     ~/SECOND BRAIN-OBSIDIAN/_System/knowledge_os/sgi_ky      <YYYY-MM-DD>.json
    SGI_BRIDGE_DIR    ~/SECOND BRAIN-OBSIDIAN/_System/fincept_bridge
                        data/wd_vimo_raw.json  [{chi_tieu, ky, ngay_iso, gia_tri, ky_truoc, don_vi, nguon}]
                        data/bang_vimo.json    {"bang", "dong": [{chi_tieu, gia_tri, ghi_chu}]}
                        data/tpcp_vn.json      {nhan, du_lieu_moi_nhat, canh_bao, ky_han: {"10Y": [[d, v]]}}
    SGI_WIDATA_STORE  ~/SECOND BRAIN-OBSIDIAN/_System/superdash_v2/output/widata_series_store.json
                        {generated_at, canvases: {<id>: {series: [{t: epoch_ms, v}]}}}
                        epoch = 00:00 Vietnam time → date = (t + 7 h) read in UTC
    SGI_VNSTORE_DB    <SGI_BRIDGE_DIR>/vnstore/vn_store.db   (nen_ngay, ma; opened mode=ro)
    SGI_TODAY         test hook only: fixes "today" (YYYY-MM-DD) for staleness

USAGE
    python3 sgi_fa.py overview [YYYY-MM-DD]     default = newest issue
    python3 sgi_fa.py issues

OUTPUT — exactly ONE compact JSON object on stdout (UTF-8, ensure_ascii=False). Non-finite
numbers are emitted as null. Exit code 0 even on errors. Every display string is Vietnamese;
numbers meant for display arrive pre-formatted ("*_txt": decimal comma, thousands dot, minus
"−", explicit "+" where the sign matters). Missing values display as "[CẦN DATA]".

Top-level errors (only these two replace the payload):
    {"error": "<Vietnamese message incl. what to do>", "error_code": "BAD_ARGS" | "INTERNAL"}
A missing / unreadable issue is NOT fatal: overview returns issue:null, engine:null, the live
layer, and meta.issue_error = {"error_code": "NO_ISSUE" | "BAD_ISSUE", "error": str}.

1) issues → {"issues": ["2026-09-20", ...] newest first, "issue_dir": str}

2) overview →
{
 "meta": {"generated": "2026-09-23T17:40:00+07:00", "script_version": "1.0",
          "issue_dir": str, "issue_file": str|null, "issues": [ky...] newest first,
          "ky": "2026-09-20"|null, "ky_sau": str|null, "du_lieu_den": str|null,
          "age_days": int|null, "stale": bool (age_days > 10 OR today > ky_sau + 3 days),
          "stale_text": "" | "BẢN TUẦN CŨ 12 ngày — kỳ 27/09 chưa có",
          "issue_error": null | {"error_code", "error"},
          "warnings": [str]   (missing sources, data traps hit),
          "sources_live": [{"ten", "duong_dan", "as_of", "tier", "ok": bool, "ghi_chu"}]},
 "gate": {"gia_tien": "tiền đắt"|"tiền rẻ"|"chưa kết luận (TIỀN và CHI PHÍ ngược chiều)"|"[CẦN DATA]",
          "chu_the": "không áp dụng — khung vĩ mô", "playbook": regime name | "[CẦN DATA]",
          "text": "CỔNG: tiền đắt · chủ thể không áp dụng (khung vĩ mô) · playbook SIẾT",
          "tier": "EST — suy từ điểm bản tuần", "co_so": "TIỀN −2 · CHI PHÍ −4,5 (bản tuần 20/09)"},
 "issue": the issue object verbatim | null,
 "engine": {
   "khoi": [{"id", "ten", "diem": num|null, "diem_txt": "+1"|"0"|"[CẦN DATA]", "to_hop": "TIỀN",
             "mo_rong": bool, "n_den", "n_do", "n_vang", "n_xanh", "n_xam"}],
   "to_hop": [{"ten", "khoi": [1, 2, 5], "he_so": 2.0, "gia_tri": num|null, "gia_tri_txt",
               "bien": 12, "bien_txt": "±12", "truoc": num|null, "truoc_txt": str, "delta_txt": "▲4"|"▼1,5"|"—"|"",
               "cong_thuc": "(0 + 0 − 1) × 2 = −2", "mo_rong": bool, "mau": "xanh"|"do"|"xam"}]
             order: TIỀN, CHI PHÍ, GIÁ TRỊ, ĐỘ RỘNG (mo_rong, never used for the regime), ĐẦU CƠ,
   "day": {"dat", "mot_phan", "chua", "can_data", "tong", "txt": "0/4 ĐẠT · 1 MỘT PHẦN",
           "ban_tuan_ghi": "1/4"|null, "nhat_quan": bool|null, "luat": str, "ghi_chu": str},
   "che_do": {"ten": "SIẾT"|…|"NGOÀI BẢNG §7"|"[CẦN DATA]", "dai": [35, 50]|null, "dai_txt": "35–50%"|"",
              "hanh_dong": str, "dong": 1..5|null, "ly_giai": str, "ngoai_bang": bool,
              "ghi_chu_bien": "+4 thuộc dòng 1–2 theo thứ tự bảng"},
   "ban_tuan_che_do": str|null, "khop": bool|null,
   "tien_mat": {"de_xuat": num|null, "hien_tai": num|null, "trong_dai": bool|null,
                "min_override": num|null, "max_san": num|null, "txt": "15% → 33%",
                "lech_txt": "dưới biên dưới 2 điểm"|…, "ly_do": [str]},
   "override": [{"id": 1..5, "ten", "trang_thai": "KÍCH HOẠT"|"KHÔNG"|"[CẦN DATA]"|"THÔNG TIN",
                 "co_so", "hieu_luc", "min_tien_mat": 30|50|null}],
   "kiem": [{"muc", "ok": bool, "text"}]      (audit lines; ok:false = the issue contradicts itself/§7)
 } | null,
 "live": {
   "tiles": [{"nhan", "gia_tri", "ky": "22/09/2026", "ghi_chu", "mau": "xanh"|"vang"|"do"|"xam",
              "tier", "nguon"}],
   "do_rong": {"universe": "VN100 · 96 mã ≥400 phiên", "n", "loai_bo", "ngay", "n_ma200", "n_ma50",
               "tren_ma200", "tren_ma200_txt", "tren_ma50", "tren_ma50_txt", "vni_ytd_txt",
               "trung_vi_ytd_txt", "chenh_dpt_txt", "danh_bai_250_txt", "deu_vs_vni_12t_txt",
               "ban_tuan": {"tren_ma200": str, "universe": str, "ky": str, and when the issue states them
                            "tren_ma50", "vni_ytd", "trung_vi_ytd", "chenh_dpt", "danh_bai_250",
                            "deu_vs_vni_12t" (display strings from the issue's chi_so)} | null,
               "tier": "EST", "ghi_chu"} | null
 },
 "nguong": [issue nguong_dao_chieu row + (only when row.live is set and data exists)
            "live_v", "live_txt", "live_trang_thai": "CHẠM"|"CHƯA"|null, "live_nguon", "live_tier",
            "live_ghi_chu"]
           + LAST, when an issue loaded: the engine's §5.4 LTT card (id "ltt", "nguon_hang": "engine",
             nhom says it is not the issue's; same keys, ghi_chu multi-line). live.tiles[0] is its summary tile.
 "ltt": {"tin_hieu": [{"ma": "T1".."T4", "ten", "trang_thai": "ĐẠT"|"MỘT PHẦN"|"CHƯA"|"[CẦN DATA]",
                       "chi_tiet": [str]}],
         "trang_thai", "bat": bool (T1 and T2 ĐẠT), "ket": str, "xac_nhan": 0..2 (T3/T4 ĐẠT),
         "cua_so": str (SBV refinancing-rate window)} | null
         — SKILL §5.4 "lãi suất thôi tăng" (giả thuyết, The Alliance Research): informational only, never
           read by §7. Sources: WiChart lines in the series store (series_multi: wc-lshuy "13 tháng",
           wc-hllai "LS qua đêm"/"… 2 tuần", wc-lsdh "Lãi suất tái cấp vốn", wc-vncctm "Cán cân thương mại")
           + the issue's chi_so ls_huy_dong_6_12t_cao (this and earlier issues), lnh_6t_bq_thang,
           khoi_ngoai_tuan_ty.
 "neo": [{"chi_bao", "nhom": "VN"|"NGOÀI", "hien_tai", "ky", "den", "tier", "lanh_manh", "canh_bao", "dinh",
          "nguon_hien_tai": "bản tuần"|"live"|"", "live_hien_tai"?: str, "live_ky"?: str}]
          (issue neo_hien_tai first; live fills only anchors with a live value — LS qua đêm, US10Y,
           US2Y − Fed funds; when both exist the issue value stays and live_* is added),
 "charts": [{"id", "tieu_de", "chu_thich", "nguon", "tier", "block": LkLineChart block}]
           ids: my_lai_suat, tpcp_vn_my, tin_dung_huy_dong, ty_gia, du_tru, do_rong, vni_vs_deu
           (a chart whose data is missing is skipped with a warning). Block: "x" ISO dates,
           "series" [{"name", "y", "style", "mau", "axis"?, "alpha"?, "y_lo"/"y_hi" for bands}],
           "left"/"right" axis {"label"}, "annotations" with x in epoch ms (UTC midnight).
 "csv": {"columns": ["Mục", "Chỉ báo", "Giá trị", "Kỳ", "Đèn/Trạng thái", "Nhãn", "Ghi chú"],
         "rows": [[str × 7]]}   (block lights + composites + regime + thresholds + anchors + live tiles)
}
"""

from __future__ import annotations

import bisect
import json
import math
import os
import re
import sqlite3
import statistics
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone

SCRIPT_VERSION = "1.1"
ICT = timezone(timedelta(hours=7), "ICT")
EPOCH = date(1970, 1, 1)
SYS_DIR = os.path.join(os.path.expanduser("~"), "SECOND BRAIN-OBSIDIAN", "_System")
CAN = "[CẦN DATA]"
MINUS = "−"

USAGE = "Dùng: sgi_fa.py overview [YYYY-MM-DD] | sgi_fa.py issues"
ISSUE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
DISCLAIMER_PORTFOLIO = "Bản tuần của chủ hệ — tham khảo, KHÔNG phải khuyến nghị."

STALE_DAYS = 10
STALE_GRACE_DAYS = 3
JUMP_LIMIT = 0.35           # single-session |return| above this = unadjusted corporate action
MIN_SESSIONS = 400          # breadth universe: VN100 members with at least this many sessions
WASHOUT_GAP_WEEKS = 4     # weeks back above 30% that still belong to the same washout episode
MIN_BREADTH_N = 20          # fewer valid symbols than this → breadth point is null
DEPOSIT_BREAK = date(2025, 10, 1)   # NHNN reclassification / method change (M2, deposits)
# First month whose YoY compares new-method to new-method levels again (break + 12 months).
DEPOSIT_BREAK_END = date(2026, 10, 1)
VN_CLOSE_HOUR = 15          # HOSE closes 14:45 (ATC); a store written earlier holds that day's intraday print

# Composite definitions (SKILL §7 + the issue's block-8 extension). Output order = artifact order.
TO_HOP = (
    {"ten": "TIỀN", "khoi": (1, 2, 5), "he_so": 2.0, "bien": 12, "mo_rong": False},
    {"ten": "CHI PHÍ", "khoi": (3, 4), "he_so": 1.5, "bien": 6, "mo_rong": False},
    {"ten": "GIÁ TRỊ", "khoi": (6,), "he_so": 1.5, "bien": 3, "mo_rong": False},
    {"ten": "ĐỘ RỘNG", "khoi": (8,), "he_so": 1.5, "bien": 3, "mo_rong": True},
    {"ten": "ĐẦU CƠ", "khoi": (7,), "he_so": 1.0, "bien": 2, "mo_rong": False},
)
MO_RONG_NOTE = "mở rộng của bản tuần, không có trong SKILL §7 — không dùng để xếp chế độ"

# Regime table rows (SKILL §7), evaluated first-match in this order.
CHE_DO = {
    1: ("MỞ RỘNG", (5, 15), "Giải ngân tối đa"),
    2: ("HƯNG PHẤN", (20, 35), "Giữ, siết stop, không mở vị thế mới"),
    3: ("TÍCH LŨY", (30, 50), "Mua từng phần, chỉ mã rủi ro đã pricing in"),
    4: ("SIẾT", (35, 50), "Xoay trục, ưu tiên giảm nợ vay, tích trữ thanh khoản"),
    5: ("CHUYỂN TIẾP", (25, 40), "Vị thế mới ≤3% NAV"),
}
NGOAI_BANG = "NGOÀI BẢNG §7"
GHI_CHU_BIEN = "+4 thuộc dòng 1–2 theo thứ tự bảng"

DAY_STATES = ("ĐẠT", "MỘT PHẦN", "CHƯA")

# §4 anchor table — verbatim copy of NEO / NEO_NGOAI in fincept_bridge/goi_vimo.py.
NEO = [
    ("LDR thuần", "85%", ">110%", "115% = đỉnh chu kỳ trước, cuối 2010"),
    ("Vay liên NH / tổng huy động", "<10%", ">15% hệ thống", ">30% ở NHTMCP nhỏ"),
    ("Giao dịch interbank/ngày", "—", "tăng nhanh", "800k–1,1 triệu tỷ (×5 trong 3 năm)"),
    ("LS qua đêm liên NH", "<3%", ">5%", "vượt đỉnh 10/2022 = ngang 2008, 2011"),
    ("Chênh LS liên NH 6th − qua đêm", "<200bp", "300–500bp", ">600bp = khan hiếm kỳ hạn"),
    ("Dự trữ ngoại hối", ">3 tháng NK", "<3 tháng (dưới IMF)", "2 tháng = tương tự cuối 2010"),
    ("Chênh tỷ giá tự do vs chính thức", "≤0 (hiếm, rất tốt)", ">3%", "6% = lớn nhất từ 2011"),
    ("Nhập siêu lũy kế / dự trữ", "xuất siêu", ">5%", "10% = mức 2010 và 2011"),
    ("CPI vs LS tái cấp vốn", "CPI thấp hơn", "tiệm cận", "CPI vượt = hiếm trong 15 năm"),
    ("Tín dụng/GDP", "<120%", "140%", ">150%"),
    ("Nợ hộ gia đình/GDP", "<40%", ">60%", "65% (từ <20% năm 2010)"),
    ("Giá nhà / năm thu nhập", "10–15", "20", "25–30 — hàng cao nhất thế giới"),
    ("LS huy động 6–12T", "<6%", "8–9%", "10% = ngưỡng chuyển tâm lý sang sợ hãi"),
    ("LS TPDN bất động sản", "<10%", "13%", "18%"),
    ("LS vay mua nhà sau ân hạn", "5–7%", "11–12%", "13–16% thả nổi"),
    ("Margin / vốn hoá", "<3%", "4%", "5% kỷ lục"),
    ("Margin / free float", "<8%", ">10%", ">14% — Hàn Quốc 3,2% đã vỡ"),
    ("Tiền mặt NĐT / margin", ">0,5", "<0,33", "<0,25 = thấp lịch sử"),
    ("Thanh khoản khớp lệnh", "—", "giảm 50% từ đỉnh", "giảm 70%, <15 nghìn tỷ/phiên"),
    ("Sở hữu nước ngoài", ">20% (2021)", "<15%", "<13%"),
    ("Lợi tức cho thuê BĐS", ">5%", "3–4%", "2–3% = hết lý do nắm giữ"),
]
NEO_NGOAI = [
    ("US10Y", "—", "—", "vượt đỉnh 2023"),
    ("US2Y − Fed funds", "—", "—", "vượt 0,5 điểm % = thị trường đòi thêm lãi suất"),
    ("DXY", "—", "—", "vượt 100"),
    ("S&P 500 P/E", "—", "—", "25–26x"),
    ("ISM Prices Paid", "—", "—", ">70 = lạm phát chi phí nhập khẩu"),
]

# Series store ids and their evidence tiers.
SID_US10Y, SID_US2Y, SID_FED = "wc-usbond", "wc-usbond2", "wc-usfed"
SID_CREDIT, SID_DEPOSIT, SID_FX_RES = "wc-tdcn", "wc-tienguivn", "wc-sbvfx"
SID_USDVND, SID_VCB_SELL, SID_VNI = "vnm-usdvnd", "wc-vn-usd-sell", "wc-vnindex"
# Multi-line WiChart canvases (series_multi; names truncated by the API — matched by prefix).
SID_LSHUY, SID_LNH, SID_LSDH, SID_TRADE = "wc-lshuy", "wc-hllai", "wc-lsdh", "wc-vncctm"
SRC_FRED = "FRED qua kho WiData"
SRC_WICHART = "NHNN/GSO qua WiChart (VietnamBiz)"
SRC_MSN = "vnstock/MSN — tỷ giá chính thức, không phải chợ đen"
NOTE_DEPOSIT_BREAK = "NHNN đổi phương pháp — YoY tiền gửi vắt qua điểm gãy, không so được"
NOTE_MSN = "tỷ giá MSN, không phải chợ đen — chỉ tham chiếu"


class SgiError(Exception):
    """A user-facing failure, emitted as {"error": message, "error_code": code}."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# ── Generic helpers ──────────────────────────────────────────────────────────


def finite(v):
    """Number → float if finite, else None (bools are not numbers here)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def clean(obj):
    """Deep copy with every non-finite float replaced by None (strict JSON)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    return obj


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def nfc(s):
    return unicodedata.normalize("NFC", s).strip() if isinstance(s, str) else ""


def fmt_vn(v, dec=2, sign=False, fixed=False):
    """Vietnamese number: 4.96→"4,96", -4.5→"−4,5", 1.5 (sign)→"+1,5", 2700→"2.700".

    dec = max decimals (trailing zeros trimmed unless fixed). None/non-finite → "[CẦN DATA]".
    """
    f = finite(v)
    if f is None:
        return CAN
    s = "%.*f" % (dec, abs(f))
    if not fixed and "." in s:
        s = s.rstrip("0").rstrip(".")
    whole, _, frac = s.partition(".")
    grouped = ""
    while len(whole) > 3:
        grouped = "." + whole[-3:] + grouped
        whole = whole[:-3]
    body = whole + grouped + ("," + frac if frac else "")
    if float(s) == 0.0:
        return body
    if f < 0:
        return MINUS + body
    return ("+" + body) if sign else body


def parse_day(value):
    """"2026-09-18…" → date, else None."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    head = value[:10]
    if len(head) != 10 or head[4] != "-" or head[7] != "-":
        return None
    try:
        return date.fromisoformat(head)  # far faster than strptime over ~165k candles
    except ValueError:
        return None


def parse_stamp(value):
    """ISO timestamp → aware datetime in Vietnam time (naive = Vietnam time), else None."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=ICT) if dt.tzinfo is None else dt.astimezone(ICT)


def deposit_straddles(d):
    """Deposit / M2 YoY dated in 10/2025 … 9/2026 compares across the NHNN break — not comparable."""
    return DEPOSIT_BREAK <= d < DEPOSIT_BREAK_END


def usd_bn(v, unit, default="tr USD"):
    """USD amount → billions by its unit label ("tr/triệu USD" = millions, "tỷ USD" = billions).
    An absent label means the documented default; an unknown one → None (never guess a factor)."""
    u = (nfc(unit) or default).lower()
    if "usd" not in u:
        return None
    if "tỷ" in u:
        return v
    if u.startswith("tr"):
        return v / 1000.0
    return None


def ddmm(d):
    return "%02d/%02d" % (d.day, d.month) if d else ""


def ddmmyyyy(d):
    return "%02d/%02d/%d" % (d.day, d.month, d.year) if d else ""


def day_ms(d):
    """Date → epoch ms at UTC midnight (annotation x contract)."""
    return (d - EPOCH).days * 86400000


def store_day(t_ms):
    """Series-store epoch (00:00 Vietnam time) → calendar date."""
    return EPOCH + timedelta(milliseconds=t_ms + 7 * 3600 * 1000)


def today():
    forced = parse_day(os.environ.get("SGI_TODAY", "").strip())
    return forced or datetime.now(ICT).date()


def env_path(name, default):
    v = os.environ.get(name, "").strip()
    return os.path.expanduser(v) if v else default


def paths():
    bridge = env_path("SGI_BRIDGE_DIR", os.path.join(SYS_DIR, "fincept_bridge"))
    return {
        "issue_dir": env_path("SGI_ISSUE_DIR", os.path.join(SYS_DIR, "knowledge_os", "sgi_ky")),
        "bridge": bridge,
        "store": env_path("SGI_WIDATA_STORE",
                          os.path.join(SYS_DIR, "superdash_v2", "output", "widata_series_store.json")),
        "vnstore": env_path("SGI_VNSTORE_DB", os.path.join(bridge, "vnstore", "vn_store.db")),
        "wd_vimo": os.path.join(bridge, "data", "wd_vimo_raw.json"),
        "bang_vimo": os.path.join(bridge, "data", "bang_vimo.json"),
        "tpcp": os.path.join(bridge, "data", "tpcp_vn.json"),
    }


# ── Issue ────────────────────────────────────────────────────────────────────


def list_issues(idir):
    try:
        names = os.listdir(idir)
    except OSError:
        return []
    out = [n[:-5] for n in names if n.endswith(".json") and ISSUE_RE.fullmatch(n[:-5]) and parse_day(n[:-5])]
    return sorted(out, reverse=True)


def load_issue(idir, issues, ky):
    """(issue dict | None, file path | None, issue_error | None)."""
    if ky is None:
        if not issues:
            return None, None, {"error_code": "NO_ISSUE",
                                "error": "Chưa có bản tuần nào trong %s — ghi bản tuần sgi_ky/1 "
                                         "(<YYYY-MM-DD>.json) rồi bấm FETCH." % idir}
        ky = issues[0]
    path = os.path.join(idir, ky + ".json")
    if not os.path.isfile(path):
        return None, None, {"error_code": "NO_ISSUE",
                            "error": "Không có bản tuần kỳ %s trong %s — chọn kỳ khác hoặc ghi tệp %s.json."
                                     % (ky, idir, ky)}
    try:
        issue = load_json(path)
    except (OSError, ValueError) as exc:
        return None, path, {"error_code": "BAD_ISSUE",
                            "error": "Không đọc được %s (%s) — sửa JSON rồi FETCH lại." % (path, exc)}
    if not isinstance(issue, dict):
        return None, path, {"error_code": "BAD_ISSUE", "error": "%s không phải JSON object." % path}
    if issue.get("schema") != "sgi_ky/1":
        return None, path, {"error_code": "BAD_ISSUE",
                            "error": "%s sai schema (%r, cần \"sgi_ky/1\")." % (path, issue.get("schema"))}
    if not isinstance(issue.get("khoi"), list):
        return None, path, {"error_code": "BAD_ISSUE", "error": "%s thiếu mảng \"khoi\"." % path}
    return issue, path, None


def as_dict(v):
    return v if isinstance(v, dict) else {}


def as_list(v):
    return v if isinstance(v, list) else []


def chi_so_v(issue, key):
    return finite(as_dict(as_dict(issue.get("chi_so")).get(key)).get("v"))


# ── Engine (SKILL §5, §7) ────────────────────────────────────────────────────


def norm_mau(m):
    """Light colour → xanh | vang | do | xam (accents / artifact dot classes tolerated)."""
    s = unicodedata.normalize("NFD", nfc(m).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return {"xanh": "xanh", "g": "xanh", "vang": "vang", "a": "vang", "do": "do", "r": "do"}.get(s, "xam")


def block_scores(issue):
    """{id: score|None} for 1..8 plus the block dicts by id."""
    by_id = {}
    for b in as_list(issue.get("khoi")):
        if isinstance(b, dict) and isinstance(b.get("id"), int) and not isinstance(b.get("id"), bool):
            by_id[b["id"]] = b
    return {i: finite(as_dict(by_id.get(i)).get("diem")) for i in range(1, 9)}, by_id


def join_terms(vals):
    out = ""
    for i, v in enumerate(vals):
        if i == 0:
            out = fmt_vn(v)
        else:
            out += (" %s %s" % (MINUS if v < 0 else "+", fmt_vn(abs(v))))
    return out


def composite(defn, k, prev):
    members = [k[i] for i in defn["khoi"]]
    he_so_txt = fmt_vn(defn["he_so"])
    out = {"ten": defn["ten"], "khoi": list(defn["khoi"]), "he_so": defn["he_so"], "bien": defn["bien"],
           "bien_txt": "±%d" % defn["bien"], "mo_rong": defn["mo_rong"]}
    if any(v is None for v in members):
        miss = ", ".join("khối %d" % i for i in defn["khoi"] if k[i] is None)
        val, formula = None, "%s thiếu điểm → %s" % (miss, CAN)
    else:
        raw = sum(members) * defn["he_so"]
        val = max(-defn["bien"], min(defn["bien"], raw))
        terms = join_terms(members)
        lhs = ("(%s)" % terms) if len(members) > 1 else terms
        formula = "%s × %s = %s" % (lhs, he_so_txt, fmt_vn(raw, sign=True))
        if val != raw:
            formula += " → chặn ở %s" % fmt_vn(val, sign=True)
    truoc = finite(prev.get(defn["ten"]))
    delta = ""
    if val is not None and truoc is not None:
        d = val - truoc
        delta = "▲" + fmt_vn(d) if d > 0 else ("▼" + fmt_vn(-d) if d < 0 else "—")
    out.update({
        "gia_tri": val, "gia_tri_txt": fmt_vn(val, sign=True), "truoc": truoc,
        "truoc_txt": fmt_vn(truoc, sign=True) if truoc is not None else "",
        "delta_txt": delta, "cong_thuc": formula,
        "mau": "xam" if val is None or val == 0 else ("xanh" if val > 0 else "do"),
    })
    if defn["mo_rong"]:
        out["ghi_chu"] = MO_RONG_NOTE
    return out


def bottom_conditions(issue):
    conds = [c for c in as_list(issue.get("dieu_kien_day")) if isinstance(c, dict)]
    counts = {s: 0 for s in DAY_STATES}
    can_data = 0
    for c in conds:
        st = nfc(c.get("trang_thai")).upper()
        if st in counts:
            counts[st] += 1
        else:
            can_data += 1
    tong = max(4, len(conds))
    can_data += max(0, 4 - len(conds))         # absent condition slots are unknown, not "CHƯA"
    d = counts["ĐẠT"]
    txt = "%d/4 ĐẠT" % d
    if counts["MỘT PHẦN"]:
        txt += " · %d MỘT PHẦN" % counts["MỘT PHẦN"]
    if can_data:
        txt += " · %d %s" % (can_data, CAN)
    ghi = as_dict(issue.get("verdict")).get("dieu_kien_day_ghi")
    ghi = nfc(ghi) or None
    printed = None
    if ghi:
        m = re.match(r"\s*(\d+)\s*/\s*4", ghi)
        printed = int(m.group(1)) if m else None
    nhat_quan, ghi_chu = None, ""
    if printed is not None:
        nhat_quan = printed == d
        if not nhat_quan:
            if d == 0:
                what = "không điều kiện nào ĐẠT"
            else:
                what = "chỉ %d điều kiện ĐẠT" % d if d < printed else "có %d điều kiện ĐẠT" % d
            ghi_chu = "Bản tuần ghi %s nhưng %s" % (ghi, what)
            if counts["MỘT PHẦN"]:
                ghi_chu += " — %d MỘT PHẦN" % counts["MỘT PHẦN"]
            ghi_chu += "; §5 chỉ đếm ĐẠT"
        else:
            ghi_chu = "Khớp: bản tuần ghi %s" % ghi
    elif ghi:
        ghi_chu = "Không đọc được số điều kiện bản tuần ghi (%r)" % ghi
    return {"dat": d, "mot_phan": counts["MỘT PHẦN"], "chua": counts["CHƯA"], "can_data": can_data,
            "tong": tong, "txt": txt, "ban_tuan_ghi": ghi, "nhat_quan": nhat_quan,
            "luat": bottom_rule(d), "ghi_chu": ghi_chu}


def bottom_rule(d):
    if d < 2:
        return "Dưới 2/4 — không mua mới bất kể conviction bottom-up"
    if d == 2:
        return "2/4 — chưa đủ 3/4, chưa giải ngân theo nhịp"
    if d == 3:
        return "3/4 — giải ngân theo nhịp"
    return "4/4 — giải ngân quy mô lớn"


def regime_row(t, v, d):
    """First matching §7 row (1..5), or a string naming the table hole."""
    if t >= 4 and v >= 0 and d >= 3:
        return 1
    if t >= 4 and v < 0:
        return 2
    if t < 0 and v >= 1.5 and d >= 3:
        return 3
    if t < 0 and d < 3:
        return 4
    if 0 <= t < 4:
        return 5
    if t >= 4:
        return "hole_up"        # T ≥ 4 & V ≥ 0 & d < 3
    return "hole_down"          # T < 0 & V < 1,5 & d ≥ 3


def regime(t, v, day):
    base = {"ghi_chu_bien": GHI_CHU_BIEN, "ngoai_bang": False}
    if t is None or v is None:
        miss = " và ".join(n for n, x in (("TIỀN", t), ("GIÁ TRỊ", v)) if x is None)
        return {**base, "ten": CAN, "dai": None, "dai_txt": "", "hanh_dong": "", "dong": None,
                "ly_giai": "%s thiếu điểm → không xếp chế độ" % miss}
    lo, hi = day["dat"], day["dat"] + day["can_data"]
    row = regime_row(t, v, lo)
    if regime_row(t, v, hi) != row:
        return {**base, "ten": CAN, "dai": None, "dai_txt": "", "hanh_dong": "", "dong": None,
                "ly_giai": "Chế độ phụ thuộc %d điều kiện đáy chưa có dữ liệu (%d–%d/4 ĐẠT)"
                           % (day["can_data"], lo, min(4, hi))}
    tt, vt, dt = fmt_vn(t, sign=True), fmt_vn(v, sign=True), "%d/4 điều kiện đáy ĐẠT" % lo
    if isinstance(row, str):
        if row == "hole_up":
            why = ("TIỀN %s ≥ +4 và GIÁ TRỊ %s ≥ 0 nhưng %s < 3/4: dòng 1 cần ≥3/4, dòng 2 cần GIÁ TRỊ < 0"
                   % (tt, vt, dt))
        else:
            why = ("TIỀN %s < 0 và %s ≥ 3/4 nhưng GIÁ TRỊ %s < +1,5: dòng 3 cần GIÁ TRỊ ≥ +1,5, dòng 4 cần <3/4"
                   % (tt, dt, vt))
        return {**base, "ten": NGOAI_BANG, "dai": None, "dai_txt": "", "hanh_dong": "", "dong": None,
                "ngoai_bang": True, "ly_giai": why + " — bảng §7 không có dòng cho tổ hợp này; không đoán chế độ"}
    name, band, action = CHE_DO[row]
    why = {
        1: "TIỀN %s ≥ +4, GIÁ TRỊ %s ≥ 0 và %s ≥ 3/4" % (tt, vt, dt),
        2: "TIỀN %s ≥ +4 và GIÁ TRỊ %s < 0" % (tt, vt),
        3: "TIỀN %s < 0, GIÁ TRỊ %s ≥ +1,5 và %s ≥ 3/4" % (tt, vt, dt),
        4: "TIỀN %s < 0 và %s < 3/4" % (tt, dt),
        5: "TIỀN %s trong 0…+4" % tt,
    }[row]
    return {**base, "ten": name, "dai": list(band), "dai_txt": "%d–%d%%" % band, "hanh_dong": action,
            "dong": row, "ly_giai": "%s → dòng %d · %s" % (why, row, name)}


def overrides(issue, che_do, by_id):
    out = []
    name = che_do["ten"]
    if name == CAN:
        st1 = CAN
    else:
        st1 = "KÍCH HOẠT" if name == "SIẾT" else "KHÔNG"
    out.append({"id": 1, "ten": "Chế độ SIẾT", "trang_thai": st1,
                "co_so": "Chế độ engine: %s" % name,
                "hieu_luc": "conviction bottom-up hạ 1 bậc; không vị thế mới >3% NAV kể cả 5/5",
                "min_tien_mat": None})

    lights = [x for x in as_list(as_dict(by_id.get(1)).get("den")) if isinstance(x, dict)]
    if not lights:
        st2, co2 = CAN, "Khối ① không có đèn trong bản tuần"
    else:
        n_do = sum(1 for x in lights if norm_mau(x.get("mau")) == "do")
        st2 = "KÍCH HOẠT" if n_do >= 3 else "KHÔNG"
        co2 = "%d đèn đỏ / %d đèn khối ①" % (n_do, len(lights))
    out.append({"id": 2, "ten": "≥3 đèn đỏ khối ①", "trang_thai": st2, "co_so": co2,
                "hieu_luc": "Hard Rule 7 — sell first, ask questions later; được phá sàn cổ phiếu 50% "
                            "khi viết lại luận điểm bằng văn bản, có ngày",
                "min_tien_mat": None})

    cpi, rate = chi_so_v(issue, "cpi_yoy"), chi_so_v(issue, "ls_tai_cap_von")
    if cpi is None or rate is None:
        st3, co3 = CAN, "Thiếu %s trong chi_so" % " / ".join(
            k for k, x in (("cpi_yoy", cpi), ("ls_tai_cap_von", rate)) if x is None)
    else:
        st3 = "KÍCH HOẠT" if cpi > rate else "KHÔNG"
        ky = nfc(as_dict(as_dict(issue.get("chi_so")).get("cpi_yoy")).get("ky"))
        co3 = "CPI %s%%%s %s LS tái cấp vốn %s%%" % (
            fmt_vn(cpi), (" (%s)" % ky) if ky else "", ">" if cpi > rate else "≤", fmt_vn(rate))
    out.append({"id": 3, "ten": "CPI > lãi suất tái cấp vốn", "trang_thai": st3, "co_so": co3,
                "hieu_luc": "tiền mặt tối thiểu 30%", "min_tien_mat": 30})

    dep = chi_so_v(issue, "ls_huy_dong_6_12t_cao")
    if dep is None:
        st4, co4 = CAN, "Thiếu ls_huy_dong_6_12t_cao trong chi_so"
    else:
        st4 = "KÍCH HOẠT" if dep > 10 else "KHÔNG"
        co4 = "LS huy động 6–12T cao nhất %s%% %s 10%%" % (fmt_vn(dep), ">" if dep > 10 else "≤")
    out.append({"id": 4, "ten": "LS tiền gửi 6–12T > 10%", "trang_thai": st4, "co_so": co4,
                "hieu_luc": "tiền mặt tối thiểu 50%; ngưỡng chuyển pha tâm lý", "min_tien_mat": 50})

    out.append({"id": 5, "ten": "Quyền M13 / Kill Zone", "trang_thai": "THÔNG TIN", "co_so": "Luôn áp dụng",
                "hieu_luc": "M13 được quyền ép bán, không được quyền ép mua; Kill Zone giữ quyền veto.",
                "min_tien_mat": None})
    return out


def cash_audit(verdict, che_do, ovr):
    tm = as_dict(verdict.get("tien_mat"))
    de_xuat, hien_tai = finite(tm.get("de_xuat")), finite(tm.get("hien_tai"))
    mins = [o["min_tien_mat"] for o in ovr if o["trang_thai"] == "KÍCH HOẠT" and o["min_tien_mat"]]
    min_ovr = max(mins) if mins else None
    san = finite(verdict.get("san_co_phieu"))
    san = 50.0 if san is None else san
    rule2 = next(o for o in ovr if o["id"] == 2)
    max_san = None if rule2["trang_thai"] == "KÍCH HOẠT" else 100.0 - san
    band = che_do.get("dai")
    trong, lech = None, ""
    if de_xuat is None:
        lech = "bản tuần không ghi tỷ trọng tiền mặt đề xuất"
    elif not band:
        lech = "chế độ không có dải (%s)" % che_do["ten"]
    else:
        lo, hi = band
        trong = lo <= de_xuat <= hi
        if de_xuat < lo:
            lech = "dưới biên dưới %s điểm" % fmt_vn(lo - de_xuat)
        elif de_xuat > hi:
            lech = "trên biên trên %s điểm" % fmt_vn(de_xuat - hi)
        else:
            lech = "trong dải %s" % che_do["dai_txt"]
    ly_do = [nfc(x) for x in as_list(verdict.get("ly_do_tien_mat")) if nfc(x)] if trong is False else []
    txt = "%s → %s" % tuple(fmt_vn(v) + "%" if v is not None else CAN for v in (hien_tai, de_xuat))
    return {"de_xuat": de_xuat, "hien_tai": hien_tai, "trong_dai": trong, "min_override": min_ovr,
            "max_san": max_san, "san_co_phieu": san, "txt": txt, "lech_txt": lech, "ly_do": ly_do}


def pct_txt(v, dec=1):
    """Fixed-decimal percentage for computed ratios: 27.8→"27,8%", 50→"50,0%"."""
    return fmt_vn(v, dec, fixed=True) + "%" if finite(v) is not None else CAN


def portfolio_col_label(issue, idx, default):
    """Printed header of portfolio column `idx` (danh_muc.cot, issue v7+), else `default`."""
    cot = as_list(as_dict(issue.get("danh_muc")).get("cot"))
    label = nfc(cot[idx]) if len(cot) > idx and isinstance(cot[idx], str) else ""
    return label.strip() or default


def printed_composites_line(issue, to_hop):
    """Audit line comparing the composites the issue PRINTS (issue v7+ "to_hop") with the engine's."""
    printed = {nfc(r.get("ten")): finite(r.get("gia_tri"))
               for r in as_list(issue.get("to_hop")) if isinstance(r, dict)}
    if not printed:
        return None
    lech = []
    for c in to_hop:
        p = printed.get(c["ten"])
        if p is None or c["gia_tri"] is None:
            continue
        if abs(p - c["gia_tri"]) > 1e-9:
            lech.append("%s in %s, engine %s" % (c["ten"], fmt_vn(p, sign=True), c["gia_tri_txt"]))
    if lech:
        return {"muc": "Tổ hợp in", "ok": False, "text": "Tổ hợp bản tuần in LỆCH engine: " + "; ".join(lech)}
    return {"muc": "Tổ hợp in", "ok": True, "text": "Tổ hợp bản tuần in khớp engine (%d mục)" % len(printed)}


def portfolio_check(issue, de_xuat):
    rows = [r for r in as_list(as_dict(issue.get("danh_muc")).get("dong")) if isinstance(r, dict)]
    if not rows:
        return None
    nums = [finite(r.get("de_xuat")) for r in rows]
    skipped = sum(1 for n in nums if n is None)
    total = sum(n for n in nums if n is not None)
    has_cash = any("TIỀN MẶT" in nfc(r.get("ma")).upper() for r in rows)
    note = ""
    if not has_cash and de_xuat is not None:
        total += de_xuat
        note = " (cộng tiền mặt đề xuất %s%%)" % fmt_vn(de_xuat)
    ok = abs(total - 100.0) <= 1.0
    text = "Tổng đề xuất danh mục %s%%%s" % (fmt_vn(total, 1), note)
    text += " — khớp 100%" if ok else " — lệch %s điểm so với 100%%" % fmt_vn(total - 100.0, 1, sign=True)
    if not ok:
        # Say where the gap sits: the stock rows alone, and whether the current column has it too.
        eq = sum(n for r, n in zip(rows, nums) if n is not None and "TIỀN MẶT" not in nfc(r.get("ma")).upper())
        co_phieu = finite(as_dict(issue.get("verdict")).get("co_phieu"))
        text += "; các dòng cổ phiếu cộng %s%%" % fmt_vn(eq, 1)
        if co_phieu is not None and abs(eq - co_phieu) < 0.5:
            text += " = cổ phiếu bản tuần ghi"
        cur = [finite(r.get("hien_tai")) for r in rows]
        if all(c is not None for c in cur) and abs(sum(cur) - 100.0) > 1.0:
            # Since issue v7 the "hien_tai" column is printed as "Kỳ trước" — name it as the issue does.
            text += "; cột %s cũng cộng %s%%" % (portfolio_col_label(issue, 1, "hiện tại").lower(), fmt_vn(sum(cur), 1))
    if skipped:
        text += "; %d dòng không có số đề xuất" % skipped
    return {"muc": "Danh mục", "ok": ok, "text": text}


def audits(issue, k, day, che_do, cash, ovr):
    verdict = as_dict(issue.get("verdict"))
    lines = []
    printed = nfc(verdict.get("che_do")) or None
    if printed is not None:
        khop = printed.upper() == che_do["ten"].upper()
        lines.append({"muc": "Chế độ", "ok": khop,
                      "text": "Engine §7 cho %s — %s bản tuần%s" % (
                          che_do["ten"], "khớp" if khop else "LỆCH", "" if khop else " (ghi %s)" % printed)})
    for i in range(1, 9):
        if k[i] is not None and not -2 <= k[i] <= 2:
            lines.append({"muc": "Khối %d" % i, "ok": False,
                          "text": "Điểm khối %d = %s nằm ngoài −2…+2" % (i, fmt_vn(k[i], sign=True))})
    if day["ban_tuan_ghi"] is not None:
        lines.append({"muc": "Điều kiện đáy", "ok": bool(day["nhat_quan"]), "text": day["ghi_chu"]})
    x = cash["de_xuat"]
    if x is not None:
        if cash["trong_dai"] is not None:
            text = "Đề xuất %s%% %s của %s (%s)" % (fmt_vn(x), cash["lech_txt"], che_do["ten"], che_do["dai_txt"])
            if cash["trong_dai"] is False and cash["ly_do"]:
                text += " — lý do bản tuần: " + "; ".join(cash["ly_do"])
            elif cash["trong_dai"] is False:
                text += " — bản tuần không ghi lý do"
            lines.append({"muc": "Tiền mặt · dải chế độ", "ok": cash["trong_dai"], "text": text})
        if cash["min_override"] is not None:
            ids = ", ".join("#%d" % o["id"] for o in ovr
                            if o["trang_thai"] == "KÍCH HOẠT" and o["min_tien_mat"])
            ok = x >= cash["min_override"]
            lines.append({"muc": "Tiền mặt · override", "ok": ok,
                          "text": "%s%% %s tối thiểu %s%% (override %s)" % (
                              fmt_vn(x), "≥" if ok else "<", fmt_vn(cash["min_override"]), ids)})
        if cash["max_san"] is not None:
            ok = x <= cash["max_san"]
            lines.append({"muc": "Tiền mặt · sàn cổ phiếu", "ok": ok,
                          "text": "%s%% %s trần %s%% (sàn cổ phiếu %s%% NAV)" % (
                              fmt_vn(x), "≤" if ok else ">", fmt_vn(cash["max_san"]), fmt_vn(cash["san_co_phieu"]))})
        co_phieu = finite(verdict.get("co_phieu"))
        if co_phieu is not None:
            eq = 100.0 - x
            ok = abs(eq - co_phieu) < 0.5
            text = "100 − %s = %s%% cổ phiếu" % (fmt_vn(x), fmt_vn(eq))
            text += " — khớp bản tuần" if ok else " nhưng bản tuần ghi cổ phiếu %s%% — lệch %s điểm" % (
                fmt_vn(co_phieu), fmt_vn(abs(eq - co_phieu)))
            lines.append({"muc": "Cổ phiếu", "ok": ok, "text": text})
        pc = portfolio_check(issue, x)
        if pc:
            lines.append(pc)
    rule2 = override_2_line(issue, k, cash, ovr)
    if rule2:
        lines.append(rule2)
    if k[8] is not None:
        lines.append({"muc": "ĐỘ RỘNG", "ok": True, "text": "ĐỘ RỘNG là " + MO_RONG_NOTE})
    return lines


RULE7_WORDS = ("hard rule 7", "sell first", "override #2", "override 2")


def override_2_line(issue, k, cash, ovr):
    """Audit line when override #2 fires: it lifts the equity floor the issue may still lean on."""
    r2 = next((o for o in ovr if o["id"] == 2), None)
    if not r2 or r2["trang_thai"] != "KÍCH HOẠT":
        return None
    text = "Override #2 kích hoạt (%s) — Hard Rule 7; sàn cổ phiếu %s%% NAV không còn giới hạn tiền mặt" % (
        r2["co_so"], fmt_vn(cash["san_co_phieu"]))
    if k[1] is not None and k[1] >= 0:
        text += "; khối ① vẫn chấm %s" % fmt_vn(k[1], sign=True)
    if any("sàn cổ phiếu" in x.lower() for x in cash["ly_do"]):
        text += "; bản tuần vẫn viện dẫn sàn cổ phiếu làm lý do giữ tiền mặt dưới dải"
    blob = json.dumps(issue, ensure_ascii=False).lower()
    if not any(w in blob for w in RULE7_WORDS):
        text += "; bản tuần không nhắc override này"
    return {"muc": "Override #2", "ok": False, "text": text}


def build_engine(issue):
    k, by_id = block_scores(issue)
    prev = as_dict(issue.get("to_hop_truoc"))
    to_hop = [composite(d, k, prev) for d in TO_HOP]
    member_of = {i: d["ten"] for d in TO_HOP for i in d["khoi"]}
    khoi = []
    for i in range(1, 9):
        b = as_dict(by_id.get(i))
        lights = [norm_mau(x.get("mau")) for x in as_list(b.get("den")) if isinstance(x, dict)]
        khoi.append({"id": i, "ten": nfc(b.get("ten")) or ("Khối %d" % i), "diem": k[i],
                     "diem_txt": fmt_vn(k[i], sign=True), "to_hop": member_of[i],
                     "mo_rong": i == 8 or bool(b.get("mo_rong")), "n_den": len(lights),
                     "n_do": lights.count("do"), "n_vang": lights.count("vang"),
                     "n_xanh": lights.count("xanh"), "n_xam": lights.count("xam")})
    comp = {c["ten"]: c["gia_tri"] for c in to_hop}
    day = bottom_conditions(issue)
    che_do = regime(comp["TIỀN"], comp["GIÁ TRỊ"], day)
    ovr = overrides(issue, che_do, by_id)
    verdict = as_dict(issue.get("verdict"))
    cash = cash_audit(verdict, che_do, ovr)
    printed = nfc(verdict.get("che_do")) or None
    kiem = audits(issue, k, day, che_do, cash, ovr)
    tc = printed_composites_line(issue, to_hop)
    if tc:
        kiem.insert(1, tc)
    return {
        "khoi": khoi, "to_hop": to_hop, "day": day, "che_do": che_do,
        "ban_tuan_che_do": printed,
        "khop": (printed.upper() == che_do["ten"].upper()) if printed else None,
        "tien_mat": cash, "override": ovr,
        "kiem": kiem,
    }


def build_gate(engine, issue):
    base = {"chu_the": "không áp dụng — khung vĩ mô", "tier": "EST — suy từ điểm bản tuần"}
    if engine is None:
        return {**base, "gia_tien": CAN, "playbook": CAN,
                "text": "CỔNG: %s · chủ thể không áp dụng (khung vĩ mô) · playbook %s" % (CAN, CAN),
                "co_so": "Chưa có bản tuần"}
    comp = {c["ten"]: c["gia_tri"] for c in engine["to_hop"]}
    t, c = comp["TIỀN"], comp["CHI PHÍ"]
    if t is None or c is None:
        gia = CAN
    elif t < 0 and c < 0:
        gia = "tiền đắt"
    elif t > 0 and c > 0:
        gia = "tiền rẻ"
    else:
        gia = "chưa kết luận (TIỀN và CHI PHÍ ngược chiều)"
    play = engine["che_do"]["ten"]
    ky = parse_day(issue.get("ky"))
    return {**base, "gia_tien": gia, "playbook": play,
            "text": "CỔNG: %s · chủ thể không áp dụng (khung vĩ mô) · playbook %s" % (gia, play),
            "co_so": "TIỀN %s · CHI PHÍ %s (bản tuần %s)" % (fmt_vn(t, sign=True), fmt_vn(c, sign=True), ddmm(ky))}


# ── Live sources ─────────────────────────────────────────────────────────────


def store_points(raw):
    """Series-store points [{t, v}] → [(date, value)] ascending, finite only, one value per day (last wins)."""
    dedup = {}
    for p in as_list(raw):
        if not isinstance(p, dict):
            continue
        t, v = finite(p.get("t")), finite(p.get("v"))
        if t is not None and v is not None:
            dedup[store_day(int(t))] = v
    return sorted(dedup.items())


class Live:
    """Lazy, fault-tolerant access to the local live sources; records warnings + source rows."""

    def __init__(self, p, warnings):
        self.p = p
        self.warnings = warnings
        self.sources = []
        self._cache = {}
        self.bang_day = None        # date printed in bang_vimo's header, when parseable
        self.store_gen = None       # series store generated_at, in Vietnam time
        self._store = self._load_store()
        self.vimo = self._load_vimo()
        self.bang = self._load_bang()
        self.tpcp = self._load_tpcp()
        self.db = self._open_db()

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None

    def _src(self, ten, path, as_of, tier, ok, note=""):
        self.sources.append({"ten": ten, "duong_dan": path, "as_of": as_of, "tier": tier, "ok": ok,
                             "ghi_chu": note})

    def _read(self, path, ten, tier):
        if not os.path.isfile(path):
            self.warnings.append("Thiếu nguồn live %s (%s)" % (ten, path))
            self._src(ten, path, None, tier, False, "không có tệp")
            return None
        try:
            return load_json(path)
        except (OSError, ValueError) as exc:
            self.warnings.append("Không đọc được %s (%s)" % (path, exc))
            self._src(ten, path, None, tier, False, "lỗi đọc: %s" % exc)
            return None

    def _load_store(self):
        ten, tier = "Kho chuỗi WiData/FRED", "FACT-T1 (FRED) · FACT-T2 (WiChart, vnstock)"
        raw = self._read(self.p["store"], ten, tier)
        if raw is None:
            return {}
        canv = raw.get("canvases") if isinstance(raw, dict) else None
        if not isinstance(canv, dict):
            self._src(ten, self.p["store"], None, tier, False, "không có canvases")
            return {}
        gen = raw.get("generated_at")
        self.store_gen = parse_stamp(gen)
        self._src(ten, self.p["store"], gen[:10] if isinstance(gen, str) else None, tier, True,
                  "wc-cpicom là CPI bình quân luỹ kế — không dùng làm CPI YoY")
        return canv

    def _load_vimo(self):
        ten = "Vĩ mô VN mới nhất (wd_vimo_raw)"
        raw = self._read(self.p["wd_vimo"], ten, "FACT-T2")
        out = {}
        for r in as_list(raw):
            if isinstance(r, dict) and isinstance(r.get("chi_tieu"), str):
                out[nfc(r["chi_tieu"])] = r
        if raw is not None:
            days = [parse_day(r.get("ngay_iso")) for r in out.values()]
            days = [d for d in days if d]
            self._src(ten, self.p["wd_vimo"], max(days).isoformat() if days else None, "FACT-T2", bool(out))
        return out

    def _load_bang(self):
        ten = "Định giá HHP (bang_vimo)"
        raw = self._read(self.p["bang_vimo"], ten, "EST")
        out = {}
        for r in as_list(as_dict(raw).get("dong")):
            if isinstance(r, dict) and isinstance(r.get("chi_tieu"), str):
                out[nfc(r["chi_tieu"])] = r
        if raw is not None:
            mdate = datetime.fromtimestamp(os.path.getmtime(self.p["bang_vimo"]), tz=ICT).date()
            head = nfc(as_dict(raw).get("bang"))
            # The header ends in "… 17:28 23/09" (no year): take the file's year, one back if that is future.
            m = re.search(r"(\d{1,2})/(\d{1,2})$", head)
            if m:
                try:
                    d = date(mdate.year, int(m.group(2)), int(m.group(1)))
                    self.bang_day = d if d <= mdate else date(d.year - 1, d.month, d.day)
                except ValueError:
                    pass
            self._src(ten, self.p["bang_vimo"], mdate.isoformat(), "EST", bool(out), head)
        return out

    def _load_tpcp(self):
        ten = "Đường cong TPCP VN (HNX)"
        raw = self._read(self.p["tpcp"], ten, "FACT-T2")
        if not isinstance(raw, dict):
            return None
        tier = nfc(raw.get("nhan")) or "FACT-T2"
        self._src(ten, self.p["tpcp"], raw.get("du_lieu_moi_nhat"), tier, True, "mô hình par yield của HNX")
        return raw

    def _open_db(self):
        path = self.p["vnstore"]
        ten = "Kho giá vnstore"
        if not os.path.isfile(path):
            self.warnings.append("Thiếu kho giá vnstore (%s) — không tính độ rộng" % path)
            self._src(ten, path, None, "FACT-T2", False, "không có tệp")
            return None
        con = None
        for mode in ("mode=ro", "immutable=1"):
            try:
                con = sqlite3.connect("file:%s?%s" % (path, mode), uri=True)
                last = con.execute("SELECT MAX(ngay) FROM nen_ngay").fetchone()[0]
                self._src(ten, path, last, "FACT-T2", True, "giá đóng cửa chưa điều chỉnh; độ rộng tự tính = EST")
                return con
            except sqlite3.Error as exc:
                err = exc
                if con is not None:
                    con.close()
                    con = None
        self.warnings.append("Không mở được vnstore (%s)" % err)
        self._src(ten, path, None, "FACT-T2", False, "lỗi mở: %s" % err)
        return None

    def series(self, sid, pct=False):
        """[(date, value)] ascending, finite values only; fraction % series scaled to %."""
        key = (sid, pct)
        if key not in self._cache:
            self._cache[key] = self._series(sid, pct)
        return self._cache[key]

    def _series(self, sid, pct):
        out = store_points(as_dict(self._store.get(sid)).get("series"))
        if pct and out and max(abs(v) for _, v in out) <= 1.5:
            out = [(d, v * 100.0) for d, v in out]
        return out

    def multi(self, sid, prefix):
        """[(date, value)] of the series_multi line whose name starts with `prefix`, else []."""
        key = (sid, "multi", prefix)
        if key not in self._cache:
            pts = []
            for line in as_list(as_dict(self._store.get(sid)).get("series_multi")):
                if isinstance(line, dict) and nfc(line.get("name")).startswith(prefix):
                    pts = store_points(line.get("series"))
                    break
            self._cache[key] = pts
        return self._cache[key]

    def vn_close_series(self, sid):
        """A VN session series without points dated on/after the store's own day when the store was written
        before the close — those are intraday prints, not closes."""
        pts = self.series(sid)
        g = self.store_gen
        if g is None or g.hour >= VN_CLOSE_HOUR:
            return pts
        return [p for p in pts if p[0] < g.date()]

    def unit(self, sid):
        return nfc(as_dict(self._store.get(sid)).get("unit"))

    def tpcp_series(self, tenor="10Y"):
        rows = as_list(as_dict(as_dict(self.tpcp).get("ky_han")).get(tenor))
        out = []
        for r in rows:
            if isinstance(r, (list, tuple)) and len(r) >= 2:
                d, v = parse_day(r[0]), finite(r[1])
                if d and v is not None:
                    out.append((d, v))
        return sorted(out)


def asof(pts, d, max_gap_days=None):
    """Last (date, value) at or before d (optionally within max_gap_days), else None."""
    if not pts:
        return None
    i = bisect.bisect_right(pts, (d, float("inf"))) - 1
    if i < 0:
        return None
    if max_gap_days is not None and (d - pts[i][0]).days > max_gap_days:
        return None
    return pts[i]


def change_12m(pts):
    """(date, %change vs ~365 days earlier) for each point with a base within 7 days."""
    out = []
    for d, v in pts:
        base = asof(pts, d - timedelta(days=365), max_gap_days=7)
        if base and base[1]:
            out.append((d, (v / base[1] - 1.0) * 100.0))
    return out


# ── Live tiles, thresholds, anchors ──────────────────────────────────────────


def issue_note(issue, key, unit="%", dec=2):
    cs = as_dict(as_dict(as_dict(issue).get("chi_so")).get(key))
    v = finite(cs.get("v"))
    if v is None:
        return ""
    return "bản tuần %s%s%s" % (fmt_vn(v, dec), unit, (" (%s)" % ky_txt(cs.get("ky"))) if nfc(cs.get("ky")) else "")


def ky_txt(ky):
    """Issue period string for display: ISO dates → dd/mm/yyyy, anything else verbatim."""
    d = parse_day(ky) if ISSUE_RE.fullmatch(nfc(ky)) else None
    return ddmmyyyy(d) if d else nfc(ky)


def join_notes(*parts):
    return " · ".join(p for p in parts if p)


def vimo_ky(r):
    """Display period of a wd_vimo_raw row from ngay_iso + tan_suat ("23/09/2026", "T8/2026", "Q2/2026")."""
    r = as_dict(r)
    d = parse_day(r.get("ngay_iso"))
    freq = nfc(r.get("tan_suat"))
    if d is None or freq not in ("ngay", "thang", "quy"):
        return nfc(r.get("ky"))
    if freq == "ngay":
        return ddmmyyyy(d)
    if freq == "thang":
        return "T%d/%d" % (d.month, d.year)
    return "Q%d/%d" % ((d.month - 1) // 3 + 1, d.year)


def vn_numbers(text):
    """Re-punctuate ASCII numbers in a passthrough note: "-1.28σ" → "−1,28σ"."""
    text = re.sub(r"(?<![\w.,])-(?=\d)", MINUS, nfc(text))
    return re.sub(r"(?<=\d)\.(?=\d)", ",", text)


def us10y_peak_2023(us10):
    vals = [v for d, v in us10 if d.year == 2023]
    return max(vals) if vals else None


def us10y_colour(v, peak):
    return "do" if peak is not None and v > peak else ("xanh" if v < 4.5 else "vang")


def closes_above(pts, level, days=30):
    """Sessions in the last `days` calendar days that closed above `level`."""
    if not pts or level is None:
        return []
    start = pts[-1][0] - timedelta(days=days)
    return [(d, v) for d, v in pts if d > start and v > level]


def fred_vs_issue(pts, issue, key, name):
    """Note when the issue's dated FRED number differs from FRED on that same date (≥1,5bp), else ""."""
    cs = as_dict(as_dict(as_dict(issue).get("chi_so")).get(key))
    v, d = finite(cs.get("v")), parse_day(cs.get("ky"))
    got = asof(pts, d, 0) if v is not None and d else None
    if not got or abs(got[1] - v) < 0.015:
        return ""
    note = "FRED %s ngày %s: %s%% — bản tuần ghi %s%% (lệch %s bp)" % (
        name, ddmm(d), fmt_vn(got[1]), fmt_vn(v), fmt_vn((v - got[1]) * 100, 0, sign=True))
    same = [x for x, y in pts if 0 < abs((x - d).days) <= 4 and abs(y - v) < 0.005]
    if same:
        note += "; %s%% là số FRED ngày %s" % (fmt_vn(v), ", ".join(ddmm(x) for x in same))
    return note


def fed_last_change(fed):
    """(date, delta) of the last Fed target change in the series, else None."""
    for i in range(len(fed) - 1, 0, -1):
        if fed[i][1] != fed[i - 1][1]:
            return fed[i][0], fed[i][1] - fed[i - 1][1]
    return None


def tile(nhan, gia_tri, d, ghi_chu, mau, tier, nguon):
    return {"nhan": nhan, "gia_tri": gia_tri, "ky": ddmmyyyy(d) if isinstance(d, date) else (d or ""),
            "ghi_chu": ghi_chu, "mau": mau, "tier": tier, "nguon": nguon}


def vimo_tile(live, issue, key, nhan, issue_key, unit="%", mau="xam", extra="", tier="FACT-T2"):
    r = live.vimo.get(key)
    v = finite(as_dict(r).get("gia_tri"))
    if v is None:
        return None
    prev = finite(r.get("ky_truoc"))
    note = join_notes(extra, "kỳ trước %s%s" % (fmt_vn(prev), unit) if prev is not None else "",
                      issue_note(issue, issue_key, unit) if issue_key else "")
    return tile(nhan, fmt_vn(v) + unit, vimo_ky(r), note, mau, tier, nfc(r.get("nguon")))


def build_tiles(live, issue):
    tiles = []
    us10, us2, fed = live.series(SID_US10Y), live.series(SID_US2Y), live.series(SID_FED)
    if us10:
        d, v = us10[-1]
        peak = us10y_peak_2023(us10)
        above = closes_above(us10, peak)
        above_txt = ""
        if above:
            above_txt = "đóng cửa trên đỉnh 2023 %d phiên trong 30 ngày: %s" % (
                len(above), ", ".join("%s %s%%" % (ddmm(x), fmt_vn(y, 2, fixed=True)) for x, y in above))
            live.warnings.append("US10Y " + above_txt + " (neo ngoài: vượt đỉnh 2023)")
        fred_note = fred_vs_issue(us10, issue, "us10y", "US10Y")
        if fred_note:
            live.warnings.append(fred_note)
        tiles.append(tile("US 10Y", fmt_vn(v) + "%", d,
                          join_notes(issue_note(issue, "us10y"),
                                     "đỉnh 2023 %s%%" % fmt_vn(peak) if peak is not None else "",
                                     above_txt, fred_note),
                          us10y_colour(v, peak), "FACT-T1", SRC_FRED))
    if us2:
        d, v = us2[-1]
        fred_note = fred_vs_issue(us2, issue, "us2y", "US2Y")
        if fred_note:
            live.warnings.append(fred_note)
        tiles.append(tile("US 2Y", fmt_vn(v) + "%", d, join_notes(issue_note(issue, "us2y"), fred_note),
                          "xam", "FACT-T1", SRC_FRED))
    if fed:
        d, v = fed[-1]
        ch = fed_last_change(fed)
        note = ""
        if ch:
            note = "đổi %sbp, hiệu lực %s (FRED)" % (fmt_vn(ch[1] * 100, 0, sign=True), ddmmyyyy(ch[0]))
        tiles.append(tile("Fed funds (trần)", fmt_vn(v) + "%", d, join_notes(note, issue_note(issue, "fed_tren")),
                          "xam", "FACT-T1", SRC_FRED))
    if us2 and fed:
        d, v2 = us2[-1]
        f = asof(fed, d)
        if f:
            gap = v2 - f[1]
            tiles.append(tile("US2Y − Fed trần", fmt_vn(gap, sign=True) + " điểm %", d,
                              "neo ngoài: vượt 0,5 điểm % = thị trường đòi thêm lãi suất",
                              "do" if gap > 0.5 else "xam", "FACT-T1", SRC_FRED))
    vn10 = live.tpcp_series("10Y")
    if vn10:
        d, v = vn10[-1]
        note = ""
        u = asof(us10, d, max_gap_days=5)
        if u:
            note = "chênh US10Y %s bp" % fmt_vn((v - u[1]) * 100, 0, sign=True)
        tiles.append(tile("TPCP VN 10Y", fmt_vn(v) + "%", d, join_notes(note, "mô hình par yield HNX"),
                          "xam", nfc(as_dict(live.tpcp).get("nhan")) or "FACT-T2", "HNX qua tpcp_vn"))
    fx = live.series(SID_USDVND)
    if fx:
        d, v = fx[-1]
        ch = change_12m(fx)
        chg = ch[-1][1] if ch and ch[-1][0] == d else None
        own = issue_note(issue, "vnd_12t_pct", "%", 1)
        if own:
            black = "chợ đen" in nfc(as_dict(as_dict(as_dict(issue).get("chi_so")).get("vnd_12t_pct")).get("ghi_chu"))
            own = own.replace("bản tuần", "bản tuần 12T" + (" theo chợ đen" if black else ""))
        note = join_notes("12T %s%%" % fmt_vn(chg, 1, sign=True) if chg is not None else "", own, NOTE_MSN)
        tiles.append(tile("USD/VND (MSN)", fmt_vn(v, 0), d, note,
                          "do" if chg is not None and chg > 8 else "xam", "FACT-T2", SRC_MSN))
    vcb = live.series(SID_VCB_SELL)
    if vcb:
        d, v = vcb[-1]
        tiles.append(tile("USD/VND VCB bán ra", fmt_vn(v, 0), d, "tỷ giá NHTM niêm yết", "xam", "FACT-T2",
                          "Vietcombank qua kho WiData"))
    cpi_mau, cpi_extra = "xam", ""
    rate = chi_so_v(issue, "ls_tai_cap_von") if issue else None
    cpi_v = finite(as_dict(live.vimo.get("CPI YoY")).get("gia_tri"))
    if rate is not None and cpi_v is not None:
        cpi_mau = "do" if cpi_v > rate else "xam"
        cpi_extra = "%s LS tái cấp vốn %s%% (bản tuần)" % ("vượt" if cpi_v > rate else "dưới", fmt_vn(rate))
    dep_day = parse_day(as_dict(live.vimo.get("Huy động YoY")).get("ngay_iso"))
    dep_note = NOTE_DEPOSIT_BREAK if dep_day and deposit_straddles(dep_day) else ""
    # A deposit YoY that straddles the NHNN break is a naive ratio across two methods, not the
    # published number (NHNN only publishes YTD there) — it cannot keep the source's FACT tier.
    dep_tier = "UNVERIFIED" if dep_note else "FACT-T2"
    for args in (("CPI YoY", "CPI YoY", "cpi_yoy", "%", cpi_mau, cpi_extra, "FACT-T2"),
                 ("Tín dụng YoY", "Tín dụng YoY", None, "%", "xam", "", "FACT-T2"),
                 ("Huy động YoY", "Huy động YoY", None, "%", "xam", dep_note, dep_tier)):
        t = vimo_tile(live, issue, *args)
        if t:
            tiles.append(t)
    lnh = finite(as_dict(live.vimo.get("LNH qua đêm")).get("gia_tri"))
    if lnh is not None:
        t = vimo_tile(live, issue, "LNH qua đêm", "LNH qua đêm", "lnh_qua_dem", "%",
                      "xanh" if lnh < 3 else ("do" if lnh > 5 else "vang"),
                      "neo §4: <3% lành mạnh, >5% cảnh báo; biến chính sách — stress thật ở kỳ hạn 3–6T")
        tiles.append(t)
    omo = as_dict(live.vimo.get("OMO ròng"))
    if finite(omo.get("gia_tri")) is not None:
        prev = finite(omo.get("ky_truoc"))
        tiles.append(tile("OMO ròng", fmt_vn(omo["gia_tri"]) + " tỷ đ", vimo_ky(omo),
                          "kỳ trước %s tỷ đ" % fmt_vn(prev) if prev is not None else "", "xam", "FACT-T2",
                          nfc(omo.get("nguon"))))
    res = as_dict(live.vimo.get("Dự trữ ngoại hối"))
    if finite(res.get("gia_tri")) is not None:
        bn = usd_bn(res["gia_tri"], res.get("don_vi"))
        if bn is None:
            live.warnings.append("Dự trữ ngoại hối (wd_vimo_raw): đơn vị %r không rõ — bỏ ô" % res.get("don_vi"))
        else:
            tiles.append(tile("Dự trữ ngoại hối", fmt_vn(bn, 1) + " tỷ USD", vimo_ky(res),
                              "mức tuyệt đối — chưa quy tháng nhập khẩu", "xam", "FACT-T2", nfc(res.get("nguon"))))
    for key, nhan in (("P/E toàn phần", "P/E toàn phần"), ("P/E ex-Vin", "P/E ex-Vin")):
        r = live.bang.get(key)
        v = finite(as_dict(r).get("gia_tri"))
        if v is not None:
            tiles.append(tile(nhan, fmt_vn(v) + "x", live.bang_day, vn_numbers(r.get("ghi_chu")), "xam", "EST",
                              "HHP qua bang_vimo"))
    return tiles


def compare(v, phep, muc):
    ops = {"<": v < muc, "<=": v <= muc, "≤": v <= muc, ">": v > muc, ">=": v >= muc, "≥": v >= muc}
    return ops.get(phep)


def live_threshold_value(live, kind):
    """(value, date, source, tier, note) for a threshold's live key, else None."""
    if kind == "us10y":
        s = live.series(SID_US10Y)
        if s:
            return s[-1][1], s[-1][0], SRC_FRED, "FACT-T1", ""
    elif kind == "vnd_12t":
        ch = change_12m(live.series(SID_USDVND))
        if ch:
            return ch[-1][1], ch[-1][0], SRC_MSN, "FACT-T2", NOTE_MSN
    elif kind == "cpi_yoy":
        r = as_dict(live.vimo.get("CPI YoY"))
        v = finite(r.get("gia_tri"))
        if v is not None:
            return v, parse_day(r.get("ngay_iso")), nfc(r.get("nguon")) or SRC_WICHART, "FACT-T2", ""
    return None


def build_thresholds(live, issue):
    out = []
    for row in as_list(as_dict(issue).get("nguong_dao_chieu")):
        if not isinstance(row, dict):
            continue
        r = dict(row)
        kind = row.get("live")
        got = live_threshold_value(live, kind) if isinstance(kind, str) else None
        if got:
            v, d, src, tier, note = got
            muc = finite(row.get("muc"))
            hit = compare(v, nfc(row.get("phep")), muc) if muc is not None else None
            if kind == "cpi_yoy":
                when = "T%d/%d" % (d.month, d.year) if d else ""
            else:
                when = ddmm(d)
            unit = "% 12T" if kind == "vnd_12t" else "%"
            notes = [note, fred_vs_issue(live.series(SID_US10Y), issue, "us10y", "US10Y") if kind == "us10y" else ""]
            keo = nfc(row.get("keo_dai"))
            # "12 tháng" on the VND row is the horizon of the 12-month change itself, not a duration.
            if keo and not (kind == "vnd_12t" and re.fullmatch(r"12\s*tháng", keo)):
                notes.append("chỉ kiểm mức tức thời, chưa kiểm độ dài \"%s\"" % nfc(row.get("keo_dai")))
            if hit is None:
                notes.append("không đọc được phép so / mức ngưỡng")
            r.update({"live_v": round(v, 4),
                      "live_txt": "%s%s (%s)" % (fmt_vn(v, 2, sign=kind == "vnd_12t"), unit, when),
                      "live_trang_thai": None if hit is None else ("CHẠM" if hit else "CHƯA"),
                      "live_nguon": src, "live_tier": tier, "live_ghi_chu": join_notes(*notes)})
        out.append(r)
    return out


# ── §5.4 LTT — "lãi suất thôi tăng" (giả thuyết, nguồn ⑤ The Alliance Research) ────────
# Engine-made, informational only: never feeds §7 (regime, cash band, overrides). Definitions are the
# real-time ones of SKILL §5.4 — no look-ahead: a peak counts only once two readings stay under it.

LTT_NHOM = "MÁY ĐO · §5.4 giả thuyết — không phải của bản tuần, không vào §7"
LTT_SRC = "WiChart (VietnamBiz) qua kho WiData"
LTT_WINDOW = 12          # readings a new high is judged against
LTT_SHORT, LTT_LONG = 20, 60   # interbank sessions: recent vs base mean


def monthly_last(pts):
    """[(date, v)] → [(first of month, last value of that month)] ascending."""
    out = {}
    for d, v in pts:
        out[(d.year, d.month)] = v
    return [(date(y, m, 1), v) for (y, m), v in sorted(out.items())]


def no_new_high(vals, window=LTT_WINDOW):
    """Readings oldest→newest → (state, peak or None). ĐẠT = the last two readings both stay at or under
    the high of the `window` readings before them; CHƯA = one of them set a new high."""
    if len(vals) < 2:
        return CAN, None
    prior = vals[-(window + 1):-1]
    if vals[-1] > max(prior):
        return "CHƯA", vals[-1]
    if len(vals) < 3:
        return CAN, max(prior)
    peak = max(vals[-(window + 2):-2])
    if vals[-2] > peak:
        return "CHƯA", vals[-2]
    return "ĐẠT", peak


def combine_all(states):
    """Every leg must hold: any CHƯA → CHƯA; all ĐẠT → ĐẠT; otherwise data is missing."""
    if "CHƯA" in states:
        return "CHƯA"
    return "ĐẠT" if states and all(s == "ĐẠT" for s in states) else CAN


def combine_some(states):
    """Partial credit: all ĐẠT → ĐẠT; some ĐẠT → MỘT PHẦN; none but a CHƯA → CHƯA; else missing."""
    if states and all(s == "ĐẠT" for s in states):
        return "ĐẠT"
    if "ĐẠT" in states:
        return "MỘT PHẦN"
    return "CHƯA" if "CHƯA" in states else CAN


def issue_history(idir, issues, ky, key, n=8):
    """[(ky, v)] oldest→newest of chi_so[key].v over the issues dated ≤ `ky` (the issue being shown)."""
    out = []
    for k in sorted(x for x in issues if ky and x <= ky)[-n:]:
        try:
            iss = load_json(os.path.join(idir, k + ".json"))
        except (OSError, ValueError):
            continue
        if isinstance(iss, dict) and iss.get("schema") == "sgi_ky/1":
            v = chi_so_v(iss, key)
            if v is not None:
                out.append((k, v))
    return out


def ltt_t1(live, hist):
    """T1 — deposit rates stop making highs, on BOTH the big-bank posted 13M rate and the market top."""
    lines, states = [], []
    mon = monthly_last(live.multi(SID_LSHUY, "13 tháng"))
    now = today()
    if mon and (mon[-1][0].year, mon[-1][0].month) == (now.year, now.month):
        mon = mon[:-1]   # the running month is not a reading yet
    mon = mon[-(LTT_WINDOW + 2):]
    if mon:
        st, peak = no_new_high([v for _, v in mon])
        top = max(mon, key=lambda x: x[1])
        lines.append("niêm yết 13T NHTM lớn %s%% (T%d/%d) — đỉnh %d kỳ %s%% (T%d/%d): %s" % (
            fmt_vn(mon[-1][1]), mon[-1][0].month, mon[-1][0].year, len(mon), fmt_vn(top[1]),
            top[0].month, top[0].year, st))
        states.append(st)
    else:
        lines.append("niêm yết 13T NHTM lớn: kho chưa có chuỗi wc-lshuy")
        states.append(CAN)
    if hist:
        st, _ = no_new_high([v for _, v in hist])
        lines.append("mức thị trường cao nhất (bản tuần): %s — %s" % (
            " → ".join("%s%% (%s)" % (fmt_vn(v), ddmm(parse_day(k))) for k, v in hist[-4:]), st))
        states.append(st)
    else:
        lines.append("mức thị trường cao nhất: bản tuần không ghi ls_huy_dong_6_12t_cao")
        states.append(CAN)
    state = combine_all(states)
    if states == ["ĐẠT", "CHƯA"]:
        lines.append("niêm yết đứng yên không có nghĩa là thôi tăng — lãi suất đang tăng ở biểu ưu đãi")
    return {"ma": "T1", "ten": "Huy động thôi lập đỉnh", "trang_thai": state, "chi_tiet": lines}


def month_avgs(cs):
    """Monthly averages printed in a chi_so entry ("T7 8,23% · T8 7,94% · T9 8,05%"), oldest→newest."""
    out = [(int(m), float(v.replace(",", "."))) for m, v in
           re.findall(r"T(\d{1,2})\s+(\d+(?:[.,]\d+)?)\s*%", nfc(cs.get("ghi_chu")))]
    m = re.match(r"T(\d{1,2})/", nfc(cs.get("ky")))
    v = finite(cs.get("v"))
    if m and v is not None and (not out or out[-1][0] != int(m.group(1))):
        out.append((int(m.group(1)), v))
    return out


def ltt_t2(live, issue):
    """T2 — interbank cools: overnight and 2-week recent mean under base mean, and 6M monthly average down."""
    lines, states, last = [], [], None
    for prefix, name in (("LS qua đêm", "qua đêm"), ("LS liên ngân hàng kỳ hạn 2 tuần", "2 tuần")):
        pts = live.multi(SID_LNH, prefix)
        if len(pts) < LTT_LONG:
            lines.append("%s: kho chưa đủ %d phiên" % (name, LTT_LONG))
            states.append(CAN)
            continue
        short = sum(v for _, v in pts[-LTT_SHORT:]) / LTT_SHORT
        base = sum(v for _, v in pts[-LTT_LONG:]) / LTT_LONG
        st = "ĐẠT" if short < base else "CHƯA"
        lines.append("%s TB%d %s%% %s TB%d %s%% (phiên cuối %s%% ngày %s): %s" % (
            name, LTT_SHORT, fmt_vn(short), "<" if short < base else "≥", LTT_LONG, fmt_vn(base),
            fmt_vn(pts[-1][1]), ddmm(pts[-1][0]), st))
        states.append(st)
        if name == "qua đêm":
            last = (pts[-1], short, base)
    avgs = month_avgs(as_dict(as_dict(as_dict(issue).get("chi_so")).get("lnh_6t_bq_thang")))
    if len(avgs) >= 2:
        (m0, v0), (m1, v1) = avgs[-2], avgs[-1]
        st = "ĐẠT" if v1 < v0 else "CHƯA"
        lines.append("6T bình quân tháng (bản tuần) T%d %s%% %s T%d %s%%: %s" % (
            m1, fmt_vn(v1), "<" if v1 < v0 else "≥", m0, fmt_vn(v0), st))
        states.append(st)
    else:
        lines.append("6T bình quân tháng: bản tuần không ghi lnh_6t_bq_thang — kỳ hạn mới là nơi stress thật")
        states.append(CAN)
    return {"ma": "T2", "ten": "Liên NH hạ nhiệt", "trang_thai": combine_some(states), "chi_tiet": lines}, last


def ltt_t3(live):
    """T3 — USD comes home: the latest monthly trade balance is a surplus."""
    pts = live.multi(SID_TRADE, "Cán cân thương mại")
    if not pts:
        return {"ma": "T3", "ten": "USD về (cán cân)", "trang_thai": CAN,
                "chi_tiet": ["kho chưa có chuỗi cán cân thương mại wc-vncctm"]}
    d, v = pts[-1]
    worst = min(pts[-6:], key=lambda x: x[1])
    line = "cán cân T%d/%d %s tỷ USD" % (d.month, d.year, fmt_vn(v / 1000.0, 2, sign=True))
    if worst[1] < v:
        line += "; 6 tháng qua thấp nhất %s tỷ (T%d)" % (fmt_vn(worst[1] / 1000.0, 2, sign=True), worst[0].month)
    return {"ma": "T3", "ten": "USD về (cán cân)", "trang_thai": "ĐẠT" if v >= 0 else "CHƯA", "chi_tiet": [line]}


def ltt_t4(issue):
    """T4 — foreigners buy again: the issue's latest week is a net buy."""
    cs = as_dict(as_dict(as_dict(issue).get("chi_so")).get("khoi_ngoai_tuan_ty"))
    v = finite(cs.get("v"))
    if v is None:
        return {"ma": "T4", "ten": "Ngoại mua ròng", "trang_thai": CAN,
                "chi_tiet": ["bản tuần không ghi khoi_ngoai_tuan_ty"]}
    return {"ma": "T4", "ten": "Ngoại mua ròng", "trang_thai": "ĐẠT" if v > 0 else "CHƯA",
            "chi_tiet": ["tuần %s: %s tỷ đồng (bộ đếm 4 tuần ở thẻ ngưỡng của bản tuần là bản chặt)" % (
                nfc(cs.get("ky")) or "?", fmt_vn(v, 0, sign=True))]}


def ltt_window(live):
    """Where the cycle sits against the SBV policy (refinancing) rate: last hike / first cut."""
    pts = live.multi(SID_LSDH, "Lãi suất tái cấp vốn")
    if not pts:
        return "kho chưa có chuỗi lãi suất điều hành wc-lsdh — không định vị được cửa sổ đáy"
    changes = [(pts[i][0], pts[i][1] - pts[i - 1][1]) for i in range(1, len(pts)) if pts[i][1] != pts[i - 1][1]]
    if not changes:
        return ("tái cấp vốn %s%% không đổi từ %s (đầu chuỗi kho) — chu kỳ này NHNN chưa tăng lãi suất điều "
                "hành; neo \"sau lần tăng cuối, trước lần giảm đầu\" không áp dụng" % (
                    fmt_vn(pts[-1][1]), ddmmyyyy(pts[0][0])))
    d, delta = changes[-1]
    if delta > 0:
        return "lần tăng tái cấp vốn gần nhất %s (%s bp) — cửa sổ đáy mở tới lần giảm đầu" % (
            ddmmyyyy(d), fmt_vn(delta * 100, 0, sign=True))
    return "đã có lần giảm tái cấp vốn %s (%s bp) — đã ra khỏi cửa sổ \"trước lần giảm đầu\"" % (
        ddmmyyyy(d), fmt_vn(delta * 100, 0, sign=True))


def build_ltt(live, issue, hist):
    """§5.4 monitor: {"tin_hieu", "trang_thai", "bat", "ket", "cua_so", "the" (threshold card), "o" (tile)}."""
    t1 = ltt_t1(live, hist)
    t2, last_on = ltt_t2(live, issue)
    t3, t4 = ltt_t3(live), ltt_t4(issue)
    on = t1["trang_thai"] == "ĐẠT" and t2["trang_thai"] == "ĐẠT"
    core = (t1["trang_thai"], t2["trang_thai"])
    if on:
        state = "ĐẠT"
    elif any(s in ("ĐẠT", "MỘT PHẦN") for s in core):
        state = "MỘT PHẦN"
    elif all(s == CAN for s in core):
        state = CAN
    else:
        state = "CHƯA"
    xac_nhan = sum(1 for x in (t3, t4) if x["trang_thai"] == "ĐẠT")
    if on:
        ket = ("LTT BẬT — đủ điều kiện XÉT điểm chiến thuật §5.2: vị thế ≤3% NAV, có stop. Không đổi chế độ, "
               "dải tiền mặt hay override §7; năm 2008 LTT bật đúng mà vẫn mất 36%.")
    else:
        ket = "LTT CHƯA BẬT (cần T1 và T2 cùng ĐẠT) — giữ nguyên §7."
    ket += " Xác nhận dòng tiền (T3/T4, \"bốn tin tích cực\" của Alliance): %d/2." % xac_nhan
    cua_so = ltt_window(live)
    sigs = [t1, t2, t3, t4]
    hien_tai = " · ".join("%s %s" % (x["ma"], x["trang_thai"]) for x in sigs)
    if all(s in ("ĐẠT", "MỘT PHẦN") for s in core):
        huong = "dung"
    elif all(s == "CHƯA" for s in core):
        huong = "nguoc"
    else:
        huong = "chua_ro"
    notes = [ket]
    for x in sigs:
        notes.append("%s %s — %s: %s" % (x["ma"], x["ten"], x["trang_thai"], "; ".join(x["chi_tiet"])))
    notes.append("Giả thuyết §5.4 (The Alliance Research, backtest 2008/2011/2022): đáy chu kỳ nằm sau lần "
                 "tăng điều hành cuối, trước lần giảm đầu (2/3 chu kỳ); vào sớm ở \"thôi tăng\" không được trả "
                 "công (+1đpt trung vị) và năm 2008 thủng −36%.")
    card = {"id": "ltt", "nhom": LTT_NHOM, "ten": "Lãi suất thôi tăng (LTT) — bật khi T1 và T2 cùng ĐẠT",
            "trang_thai": state, "huong": huong, "hien_tai": hien_tai, "keo_dai": "",
            "ghi_chu": "\n".join(notes), "nguon_hang": "engine"}
    ky = None
    if last_on:
        (d, v), short, base = last_on
        ky = d
        card.update({"live_txt": "qua đêm %s%% (%s) · TB%d %s%% / TB%d %s%%" % (
                         fmt_vn(v), ddmm(d), LTT_SHORT, fmt_vn(short), LTT_LONG, fmt_vn(base)),
                     "live_trang_thai": None, "live_nguon": LTT_SRC, "live_tier": "FACT-T2 · chấm EST",
                     "live_ghi_chu": cua_so})
    else:
        card["ghi_chu"] += "\n" + cua_so
    mau = {"ĐẠT": "xanh", "MỘT PHẦN": "vang", "CHƯA": "do"}.get(state, "xam")
    tile_ = tile("LTT §5.4 (giả thuyết)", "BẬT" if on else "CHƯA BẬT", ky or "",
                 join_notes(hien_tai, "xác nhận dòng tiền %d/2" % xac_nhan, cua_so), mau, "EST",
                 "engine sgi_fa · " + LTT_SRC)
    return {"tin_hieu": sigs, "trang_thai": state, "bat": on, "ket": ket, "xac_nhan": xac_nhan,
            "cua_so": cua_so, "the": card, "o": tile_}


def live_anchors(live):
    out = {}
    lnh = as_dict(live.vimo.get("LNH qua đêm"))
    v = finite(lnh.get("gia_tri"))
    if v is not None:
        out["LS qua đêm liên NH"] = {"gia_tri": fmt_vn(v) + "%", "ky": vimo_ky(lnh),
                                     "den": "xanh" if v < 3 else ("do" if v > 5 else "vang"), "tier": "FACT-T2"}
    us10, us2, fed = live.series(SID_US10Y), live.series(SID_US2Y), live.series(SID_FED)
    if us10:
        d, v = us10[-1]
        peak = us10y_peak_2023(us10)
        out["US10Y"] = {"gia_tri": fmt_vn(v) + "%" + (" (đỉnh 2023 %s%%)" % fmt_vn(peak) if peak else ""),
                        "ky": ddmmyyyy(d), "den": us10y_colour(v, peak), "tier": "FACT-T1"}
    if us2 and fed:
        d, v2 = us2[-1]
        f = asof(fed, d)
        if f:
            gap = v2 - f[1]
            out["US2Y − Fed funds"] = {"gia_tri": fmt_vn(gap, sign=True) + " điểm %", "ky": ddmmyyyy(d),
                                       "den": "do" if gap > 0.5 else "xam", "tier": "FACT-T1"}
    return out


def build_anchors(live, issue):
    given = as_dict(as_dict(issue).get("neo_hien_tai"))
    lv = live_anchors(live)
    out = []
    for nhom, table in (("VN", NEO), ("NGOÀI", NEO_NGOAI)):
        for name, lm, cb, dc in table:
            row = {"chi_bao": name, "nhom": nhom, "lanh_manh": lm, "canh_bao": cb, "dinh": dc}
            src = as_dict(given.get(name))
            live_v = lv.get(name)
            if nfc(src.get("gia_tri")) or finite(src.get("gia_tri")) is not None:
                gv = src.get("gia_tri")
                row.update({"hien_tai": nfc(gv) if isinstance(gv, str) else fmt_vn(gv),
                            "ky": ky_txt(src.get("ky")), "den": norm_mau(src.get("den")),
                            "tier": nfc(src.get("tier")) or CAN, "nguon_hien_tai": "bản tuần"})
                if live_v:
                    row["live_hien_tai"] = live_v["gia_tri"]
                    row["live_ky"] = live_v["ky"]
            elif live_v:
                row.update({"hien_tai": live_v["gia_tri"], "ky": live_v["ky"], "den": live_v["den"],
                            "tier": live_v["tier"], "nguon_hien_tai": "live"})
            else:
                row.update({"hien_tai": CAN, "ky": "", "den": "xam", "tier": CAN, "nguon_hien_tai": ""})
            out.append(row)
    return out


# ── Breadth (vnstore) ────────────────────────────────────────────────────────


def load_universe(con):
    """({symbol: [(date, close)]}, [(date, close)] VN-Index or [])."""
    syms = [r[0] for r in con.execute("SELECT symbol FROM ma WHERE nhom LIKE '%VN100%'")]
    syms = [s for s in syms if s]
    data = {}
    if syms:
        marks = ",".join("?" * len(syms))
        for sym, ngay, dong in con.execute(
                "SELECT symbol, ngay, dong FROM nen_ngay WHERE symbol IN (%s) ORDER BY symbol, ngay" % marks, syms):
            d, v = parse_day(ngay), finite(dong)
            if d and v is not None and v > 0:
                data.setdefault(sym, []).append((d, v))
    data = {s: pts for s, pts in data.items() if len(pts) >= MIN_SESSIONS}
    vni = []
    for ngay, dong in con.execute("SELECT ngay, dong FROM nen_ngay WHERE symbol = 'VNINDEX' ORDER BY ngay"):
        d, v = parse_day(ngay), finite(dong)
        if d and v is not None and v > 0:
            vni.append((d, v))
    return data, vni


def jump_prefix(closes):
    """pref[i] = number of |return| > JUMP_LIMIT among returns ending at sessions 1..i."""
    pref = [0] * len(closes)
    for i in range(1, len(closes)):
        pref[i] = pref[i - 1] + (1 if abs(closes[i] / closes[i - 1] - 1.0) > JUMP_LIMIT else 0)
    return pref


def above_ma_flags(closes, pref, n):
    """Per session: True/False close > MA(n), None when too short or a jump sits inside the window."""
    out = [None] * len(closes)
    acc = 0.0
    for i, c in enumerate(closes):
        acc += c
        if i >= n:
            acc -= closes[i - n]
        if i >= n - 1 and pref[i] - pref[i - n + 1] == 0:
            out[i] = c > acc / n
    return out


def breadth_history(data, dates):
    """{n: [pct|None per date]} for MA200 / MA50, plus the count of valid symbols per date."""
    res = {200: [], 50: []}
    counts = {200: [], 50: []}
    prepared = []
    for pts in data.values():
        ds = [d for d, _ in pts]
        cl = [c for _, c in pts]
        pref = jump_prefix(cl)
        prepared.append((ds, {200: above_ma_flags(cl, pref, 200), 50: above_ma_flags(cl, pref, 50)}))
    for d in dates:
        tally = {200: [0, 0], 50: [0, 0]}
        for ds, flags in prepared:
            i = bisect.bisect_right(ds, d) - 1
            if i < 0 or (d - ds[i]).days > 7:
                continue
            for n in (200, 50):
                f = flags[n][i]
                if f is not None:
                    tally[n][1] += 1
                    tally[n][0] += 1 if f else 0
        for n in (200, 50):
            up, tot = tally[n]
            res[n].append(up * 100.0 / tot if tot >= MIN_BREADTH_N else None)
            counts[n].append(tot)
    return res, counts


def week_ends(dates):
    """Last session of each ISO week."""
    out = []
    for d in dates:
        if out and out[-1].isocalendar()[:2] == d.isocalendar()[:2]:
            out[-1] = d
        else:
            out.append(d)
    return out


def window_ret(pts_by_day, d0, d1):
    a, b = pts_by_day.get(d0), pts_by_day.get(d1)
    return (b / a - 1.0) * 100.0 if a and b else None


def vni_cross_check(vni, other, tol=0.003):
    """Note when the last VN-Index close both sources share differs by more than `tol`, else ""."""
    ref = dict(other)
    for d, v in reversed(vni):
        w = ref.get(d)
        if w:
            if abs(v / w - 1.0) <= tol:
                return ""
            return "VN-Index %s: vnstore %s vs kho WiData %s (lệch %s%%) — YTD và bình quân đều dùng vnstore" % (
                ddmmyyyy(d), fmt_vn(v), fmt_vn(w), fmt_vn((v / w - 1.0) * 100, 1, sign=True, fixed=True))
    return ""


def build_breadth(live, issue):
    """(do_rong dict | None, weekly history, ew-vs-vni data) — all from vnstore."""
    if live.db is None:
        return None, None, None
    try:
        data, vni = load_universe(live.db)
    except sqlite3.Error as exc:
        live.warnings.append("Lỗi đọc vnstore (%s) — bỏ độ rộng" % exc)
        return None, None, None
    if not data:
        live.warnings.append("vnstore không có mã VN100 nào đủ %d phiên — bỏ độ rộng" % MIN_SESSIONS)
        return None, None, None
    if len(vni) < 253:
        store_vni = live.vn_close_series(SID_VNI)
        if len(store_vni) > len(vni):
            vni = store_vni
            live.warnings.append("VN-Index lấy từ kho WiData (vnstore thiếu VNINDEX)")
    vni_note = vni_cross_check(vni, live.vn_close_series(SID_VNI))
    if vni_note:
        live.warnings.append(vni_note)
    all_days = sorted({d for pts in data.values() for d, _ in pts})
    last = all_days[-1]
    hist_days = [d for d in week_ends(all_days) if d >= last - timedelta(days=5 * 365)]
    if not hist_days or hist_days[-1] != last:
        hist_days.append(last)
    hist, _ = breadth_history(data, hist_days)
    snap, snap_n = breadth_history(data, [last])

    # Relative metrics: one needed window (≥253 sessions and the whole YTD span) on the VN-Index calendar.
    cal = [d for d, _ in vni if d <= last] if vni else all_days
    prev_year = [d for d in cal if d.year < last.year]
    ytd_base = prev_year[-1] if prev_year else None
    need = 253
    if ytd_base:
        need = max(need, len(cal) - cal.index(ytd_base))
    window = cal[-need:] if len(cal) >= need else cal
    w0 = window[0]
    kept, dropped = {}, 0
    for sym, pts in data.items():
        seg = [(d, c) for d, c in pts if w0 <= d <= last]
        cl = [c for _, c in seg]
        if any(abs(cl[i] / cl[i - 1] - 1.0) > JUMP_LIMIT for i in range(1, len(cl))):
            dropped += 1
            continue
        kept[sym] = dict(seg)
    vni_by = dict(vni)
    out = {"n": len(kept), "loai_bo": dropped, "ngay": last.isoformat(),
           "universe": "VN100 · %d mã ≥%d phiên" % (len(data), MIN_SESSIONS),
           "n_ma200": snap_n[200][0], "n_ma50": snap_n[50][0],
           "tren_ma200": snap[200][0], "tren_ma200_txt": pct_txt(snap[200][0]),
           "tren_ma50": snap[50][0], "tren_ma50_txt": pct_txt(snap[50][0]),
           "tier": "EST"}
    vni_ytd = window_ret(vni_by, ytd_base, last) if ytd_base else None
    ytds = [window_ret(p, ytd_base, last) for p in kept.values()] if ytd_base else []
    ytds = [x for x in ytds if x is not None]
    med = statistics.median(ytds) if ytds else None
    out["vni_ytd_txt"] = fmt_vn(vni_ytd, 1, sign=True, fixed=True) + "%" if vni_ytd is not None else CAN
    out["trung_vi_ytd_txt"] = fmt_vn(med, 1, sign=True, fixed=True) + "%" if med is not None else CAN
    out["chenh_dpt_txt"] = ((fmt_vn(vni_ytd - med, 1, fixed=True) + " đpt")
                            if vni_ytd is not None and med is not None else CAN)
    d250 = cal[-251] if len(cal) >= 251 else None
    beat = None
    if d250 and vni_by.get(d250):
        vr = window_ret(vni_by, d250, last)
        rs = [window_ret(p, d250, last) for p in kept.values()]
        rs = [x for x in rs if x is not None]
        if vr is not None and rs:
            beat = sum(1 for x in rs if x > vr) * 100.0 / len(rs)
    out["danh_bai_250_txt"] = pct_txt(beat)
    ew = ew_vs_vni(kept, vni, cal[-253:] if len(cal) >= 253 else [])
    gap = (ew["deu"][-1] - ew["vni"][-1]) if ew else None
    # Gap of the two rebased-100 lines = difference of 12-month returns, in percentage points.
    out["deu_vs_vni_12t_txt"] = fmt_vn(gap, 1, sign=True, fixed=True) + " đpt" if gap is not None else CAN
    out["ban_tuan"] = issue_breadth(issue)
    notes = ["tự tính trên kho vnstore — không phải số công bố",
             "loại %d mã có phiên |biến động| >35%% trong cửa sổ %d phiên (nghi chưa điều chỉnh quyền)"
             % (dropped, len(window)),
             "MA200/MA50 loại theo từng cửa sổ trung bình"]
    if vni_note:
        notes.append(vni_note)
    out["ghi_chu"] = "; ".join(notes)
    hist_out = {"x": hist_days, 200: hist[200], 50: hist[50]}
    return out, hist_out, ew


def ew_vs_vni(kept, vni, days):
    """Equal-weight index (mean of daily returns) vs VN-Index, both rebased 100 over `days`."""
    if len(days) < 2:
        return None
    vni_by = dict(vni)
    if not all(vni_by.get(d) for d in (days[0], days[-1])):
        return None
    deu, vv = [100.0], [100.0]
    for a, b in zip(days, days[1:]):
        rets = [p[b] / p[a] - 1.0 for p in kept.values() if p.get(a) and p.get(b)]
        deu.append(deu[-1] * (1.0 + (sum(rets) / len(rets) if rets else 0.0)))
        vv.append(vni_by[b] / vni_by[days[0]] * 100.0 if vni_by.get(b) else None)
    return {"x": days, "deu": deu, "vni": vv}


# Issue chi_so keys for its own breadth numbers → do_rong.ban_tuan keys (shown beside the live ones).
BAN_TUAN_DO_RONG = (
    ("do_rong_tren_ma200_pct", "tren_ma200", "%", False),
    ("do_rong_tren_ma50_pct", "tren_ma50", "%", False),
    ("vni_ytd_pct", "vni_ytd", "%", True),
    ("trung_vi_ytd_pct", "trung_vi_ytd", "%", True),
    ("chenh_chi_so_trung_vi_dpt", "chenh_dpt", " đpt", False),
    ("danh_bai_chi_so_250p_pct", "danh_bai_250", "%", False),
    ("binh_quan_deu_vs_von_hoa_12t_pct", "deu_vs_vni_12t", "%", True),
)


def issue_breadth(issue):
    """The issue's own breadth figures (its universe, its date) — never merged with the live ones."""
    if not issue:
        return None
    chi_so = as_dict(issue.get("chi_so"))
    out, uni, ky = {}, "", ""
    for key, name, unit, signed in BAN_TUAN_DO_RONG:
        cs = as_dict(chi_so.get(key))
        v = finite(cs.get("v"))
        if v is None:
            continue
        out[name] = fmt_vn(v, 1 if round(v, 1) == v else 2, sign=signed, fixed=True) + unit
        uni = uni or nfc(cs.get("ghi_chu"))
        ky = ky or ky_txt(cs.get("ky"))
    if "tren_ma200" not in out:
        for t in as_list(issue.get("tiles")):
            if isinstance(t, dict) and "MA200" in nfc(t.get("nhan")).upper() and nfc(t.get("gia_tri")):
                out["tren_ma200"] = nfc(t.get("gia_tri"))
                break
    if not out:
        return None
    out.setdefault("tren_ma200", CAN)
    out["universe"] = uni
    out["ky"] = ky
    return out


# ── Charts (LkLineChart blocks) ──────────────────────────────────────────────


def iso(ds):
    return [d.isoformat() for d in ds]


def rnd(v, n=4):
    return round(v, n) if v is not None else None


def point(d, y, text, sub="", mau="info", pos="above", uu_tien=1, marker="dot", axis=None, tip=""):
    a = {"kind": "point", "x": day_ms(d), "y": rnd(y), "text": text, "sub": sub, "tip": tip or text,
         "mau": mau, "marker": marker, "pos": pos, "uu_tien": uu_tien}
    if axis:
        a["axis"] = axis
    return a


def chart(cid, tieu_de, chu_thich, nguon, tier, block):
    return {"id": cid, "tieu_de": tieu_de, "chu_thich": chu_thich, "nguon": nguon, "tier": tier, "block": block}


def chart_rates(live, issue=None):
    us10, us2, fed = live.series(SID_US10Y), live.series(SID_US2Y), live.series(SID_FED)
    if not us10:
        return None
    last = us10[-1][0]
    xs = [d for d, _ in us10 if d >= last - timedelta(days=3 * 365)]
    d10 = dict(us10)
    y2 = [(asof(us2, d, 0) or (None, None))[1] for d in xs]
    yf = [(asof(fed, d, 10) or (None, None))[1] for d in xs]
    ann = [{"kind": "hband", "y0": 0, "y1": 4.5, "text": "Ngưỡng đảo chiều US10Y <4,5%", "mau": "bull",
            "alpha": 0.10},
           point(last, d10[last], "US10Y %s%%" % fmt_vn(d10[last]), ddmmyyyy(last), "bear")]
    ch = fed_last_change(fed)
    if ch and ch[0] >= xs[0]:
        eff = ch[0]
        tip = "Trần Fed funds đổi hiệu lực %s (FRED DFEDTARU)" % ddmmyyyy(eff)
        # FRED dates the target from its effective day, the day after the FOMC decision. Mark the decision
        # day the issue states when it sits just before the FRED date.
        dec = parse_day(as_dict(as_dict(as_dict(issue).get("chi_so")).get("fed_tren")).get("ky"))
        at = dec if dec and 0 < (eff - dec).days <= 3 else eff
        if at != eff:
            tip = "FOMC quyết định %s (bản tuần) · FRED DFEDTARU ghi hiệu lực %s" % (ddmmyyyy(at), ddmmyyyy(eff))
        ann.append({"kind": "vline", "x": day_ms(at),
                    "text": "Fed %sbp" % fmt_vn(ch[1] * 100, 0, sign=True),
                    "tip": tip, "mau": "warn", "style": "dash"})
    block = {"x": iso(xs),
             "series": [{"name": "US10Y", "y": [d10[d] for d in xs], "style": "line", "mau": "bear"},
                        {"name": "US2Y", "y": y2, "style": "thin", "mau": "amber"},
                        {"name": "Fed funds (trần)", "y": yf, "style": "dash", "mau": "dim"}],
             "left": {"label": "%/năm"}, "annotations": ann}
    return chart("my_lai_suat", "Lãi suất Mỹ — US10Y, US2Y, Fed funds (3 năm)",
                 "Dải xanh: vùng ngưỡng đảo chiều US10Y <4,5% của bản tuần. Fed là bậc thang trần mục tiêu.",
                 SRC_FRED, "FACT-T1", block)


def chart_vn_us(live):
    vn10, us10 = live.tpcp_series("10Y"), live.series(SID_US10Y)
    if not vn10 or not us10:
        return None
    last = vn10[-1][0]
    xs = [d for d, _ in vn10 if d >= last - timedelta(days=5 * 365)]
    dvn = dict(vn10)
    yu = [(asof(us10, d, 5) or (None, None))[1] for d in xs]
    spread = [rnd(dvn[d] - u) if u is not None else None for d, u in zip(xs, yu)]
    ann = [point(last, dvn[last], "VN10Y %s%%" % fmt_vn(dvn[last]), ddmmyyyy(last), "info")]
    if yu[-1] is not None:
        ann.append(point(last, yu[-1], "US10Y %s%%" % fmt_vn(yu[-1]), "", "bear", pos="below", uu_tien=2))
    if spread[-1] is not None:
        ann.append(point(last, spread[-1], "Chênh %s bp" % fmt_vn(spread[-1] * 100, 0, sign=True), "", "amber",
                         pos="right", uu_tien=2, axis="right"))
    warns = [nfc(w) for w in as_list(as_dict(live.tpcp).get("canh_bao")) if nfc(w)]
    block = {"x": iso(xs),
             "series": [{"name": "TPCP VN 10Y", "y": [dvn[d] for d in xs], "style": "line", "mau": "info"},
                        {"name": "US10Y", "y": yu, "style": "line", "mau": "bear"},
                        {"name": "Chênh VN10Y − US10Y", "y": spread, "style": "thin", "mau": "amber",
                         "axis": "right"}],
             "left": {"label": "%/năm"}, "right": {"label": "điểm %"}, "annotations": ann}
    return chart("tpcp_vn_my", "TPCP VN 10Y vs US10Y (5 năm)", " ".join(warns),
                 "HNX (par yield) · FRED", nfc(as_dict(live.tpcp).get("nhan")) or "FACT-T2", block)


def chart_credit(live, warnings):
    cr, dep = live.series(SID_CREDIT, pct=True), live.series(SID_DEPOSIT, pct=True)
    if not cr:
        return None
    start = date(2018, 1, 1)
    dc, dd = dict(cr), dict(dep)
    xs = sorted(d for d in set(dc) | set(dd) if d >= start)
    if not any(dc.get(d) is not None for d in xs):
        return None
    yc = [dc.get(d) for d in xs]
    yd = [None if deposit_straddles(d) else dd.get(d) for d in xs]
    if any(deposit_straddles(d) for d in dd):
        warnings.append("Huy động YoY từ 10/2025 vắt qua điểm gãy NHNN — đặt null trên biểu đồ, không tính khe")
    lo = [rnd(b) if a is not None and b is not None and a > b else None for a, b in zip(yc, yd)]
    hi = [rnd(a) if a is not None and b is not None and a > b else None for a, b in zip(yc, yd)]
    ann = [{"kind": "vline", "x": day_ms(DEPOSIT_BREAK), "text": "Gãy chuỗi NHNN 10/2025",
            "tip": NOTE_DEPOSIT_BREAK, "mau": "warn", "style": "dash"}]
    last_c = max(d for d in xs if dc.get(d) is not None)
    ann.append(point(last_c, dc[last_c], "Tín dụng %s%%" % fmt_vn(dc[last_c], 1), "T%d/%d" % (
        last_c.month, last_c.year), "bear"))
    dep_ok = [d for d, v in zip(xs, yd) if v is not None]
    if dep_ok:
        d = dep_ok[-1]
        ann.append(point(d, dd[d], "Huy động %s%%" % fmt_vn(dd[d], 1), "T%d/%d%s" % (
            d.month, d.year, " — điểm cuối trước gãy" if d < DEPOSIT_BREAK else ""), "info", pos="below", uu_tien=2))
    block = {"x": iso(xs),
             "series": [{"name": "Khe tín dụng − huy động", "style": "band", "y_lo": lo, "y_hi": hi,
                         "mau": "bear", "alpha": 0.12},
                        {"name": "Tín dụng YoY", "y": [rnd(v) for v in yc], "style": "line", "mau": "bear"},
                        {"name": "Huy động YoY", "y": [rnd(v) for v in yd], "style": "line", "mau": "info"}],
             "left": {"label": "% YoY"}, "annotations": ann}
    return chart("tin_dung_huy_dong", "Tín dụng vs huy động — tăng trưởng YoY (từ 2018)",
                 "Từ 10/2025 NHNN đổi phương pháp: YoY tiền gửi T10/2025–T9/2026 vắt qua điểm gãy, không so được — "
                 "chuỗi huy động để trống và không tính khe qua điểm gãy. Tín dụng không bị ảnh hưởng.",
                 SRC_WICHART, "FACT-T2", block)


def chart_fx(live):
    fx = live.series(SID_USDVND)
    if not fx:
        return None
    last = fx[-1][0]
    xs = [d for d, _ in fx if d >= last - timedelta(days=3 * 365)]
    dfx = dict(fx)
    chg = dict(change_12m(fx))
    yc = [rnd(chg.get(d), 3) for d in xs]
    top = max([v for v in yc if v is not None] + [8.0]) + 1.0
    ann = [{"kind": "hband", "y0": 8, "y1": rnd(top, 2), "text": "VND mất giá >8%/12T — ngưỡng 5", "mau": "bear",
            "alpha": 0.10, "axis": "right"},
           point(last, dfx[last], "USD/VND %s" % fmt_vn(dfx[last], 0), ddmmyyyy(last), "info")]
    if chg.get(last) is not None:
        ann.append(point(last, chg[last], "12T %s%%" % fmt_vn(chg[last], 1, sign=True), "", "amber",
                         pos="below", uu_tien=2, axis="right"))
    block = {"x": iso(xs),
             "series": [{"name": "USD/VND (MSN)", "y": [dfx[d] for d in xs], "style": "line", "mau": "info"},
                        {"name": "Thay đổi 12 tháng", "y": yc, "style": "thin", "mau": "amber", "axis": "right"}],
             "left": {"label": "VND/USD"}, "right": {"label": "% 12T (dương = VND mất giá)"}, "annotations": ann}
    return chart("ty_gia", "USD/VND và tốc độ mất giá 12 tháng (3 năm)",
                 "Tỷ giá vnstock/MSN là tỷ giá chính thức — KHÔNG phải chợ đen; ngưỡng chợ đen của bản tuần "
                 "chỉ có trong bản tuần.", SRC_MSN, "FACT-T2", block)


def chart_reserves(live, warnings):
    unit = live.unit(SID_FX_RES)
    if live.series(SID_FX_RES) and usd_bn(1.0, unit) is None:
        warnings.append("Dự trữ ngoại hối (%s): đơn vị %r không rõ — bỏ biểu đồ" % (SID_FX_RES, unit))
        return None
    res = [(d, usd_bn(v, unit)) for d, v in live.series(SID_FX_RES) if d >= date(2018, 1, 1)]
    if not res:
        return None
    d, v = res[-1]
    block = {"x": iso([x for x, _ in res]),
             "series": [{"name": "Dự trữ ngoại hối", "y": [rnd(y, 3) for _, y in res], "style": "line",
                         "mau": "cyan"}],
             "left": {"label": "tỷ USD"},
             "annotations": [point(d, v, "%s tỷ USD" % fmt_vn(v, 1), "T%d/%d" % (d.month, d.year), "cyan")]}
    return chart("du_tru", "Dự trữ ngoại hối (từ 2018)",
                 "Chỉ là mức tuyệt đối — số tháng nhập khẩu (neo §4) không tính ở đây.", SRC_WICHART,
                 "FACT-T2", block)


def washout_lows(xs, ys, limit=30.0, gap=WASHOUT_GAP_WEEKS):
    """(date, value) of the lowest point of each washout episode (runs below `limit`; a stretch of
    at most `gap` points back above the limit does not end the episode)."""
    out, best, above = [], None, 0
    for d, v in zip(xs, ys):
        if v is not None and v < limit:
            above = 0
            if best is None or v < best[1]:
                best = (d, v)
        elif best is not None:
            above += 1
            if above > gap:
                out.append(best)
                best, above = None, 0
    if best is not None:
        out.append(best)
    return out


def chart_breadth(hist, do_rong):
    if not hist or not any(v is not None for v in hist[200]):
        return None
    xs = hist["x"]
    ann = [{"kind": "hband", "y0": 0, "y1": 30, "text": "Washout <30%", "mau": "bear", "alpha": 0.10},
           {"kind": "hband", "y0": 70, "y1": 100, "text": "Hưng phấn >70%", "mau": "warn", "alpha": 0.08}]
    last_v = hist[200][-1]
    if last_v is not None:
        ann.append(point(xs[-1], last_v, "Trên MA200 %s" % pct_txt(last_v), ddmmyyyy(xs[-1]), "info"))
    for d, v in washout_lows(xs, hist[200]):
        if d == xs[-1]:
            continue
        ann.append(point(d, v, pct_txt(v), "đáy washout %s" % ddmmyyyy(d), "bear", pos="below", uu_tien=3,
                         marker="diamond"))
    block = {"x": iso(xs),
             "series": [{"name": "% trên MA200", "y": [rnd(v, 2) for v in hist[200]], "style": "line",
                         "mau": "info"},
                        {"name": "% trên MA50", "y": [rnd(v, 2) for v in hist[50]], "style": "thin", "mau": "dim"}],
             "left": {"label": "% số mã", "min": 0, "max": 100}, "annotations": ann}
    return chart("do_rong", "Độ rộng — % mã trên MA200 / MA50 (tuần, 5 năm)",
                 "%s · %s." % (do_rong["universe"], do_rong["ghi_chu"]), "vnstore (VCI/VnDirect)", "EST", block)


def chart_ew(ew):
    if not ew:
        return None
    xs = ew["x"]
    gap = ew["deu"][-1] - ew["vni"][-1] if ew["vni"][-1] is not None else None
    ann = []
    if gap is not None:
        ann.append(point(xs[-1], ew["deu"][-1], "Bình quân đều %s đpt vs VN-Index" % fmt_vn(gap, 1, sign=True),
                         ddmmyyyy(xs[-1]), "bear" if gap < 0 else "bull", pos="below"))
        ann.append(point(xs[-1], ew["vni"][-1], "VN-Index %s" % fmt_vn(ew["vni"][-1], 1), "", "info",
                         uu_tien=2))
    block = {"x": iso(xs),
             "series": [{"name": "VN-Index (rebase 100)", "y": [rnd(v, 3) for v in ew["vni"]], "style": "line",
                         "mau": "info"},
                        {"name": "Bình quân đều rổ (rebase 100)", "y": [rnd(v, 3) for v in ew["deu"]],
                         "style": "line", "mau": "amber"}],
             "left": {"label": "rebase 100"}, "annotations": ann}
    return chart("vni_vs_deu", "VN-Index vs bình quân đều rổ VN100 (252 phiên)",
                 "Chỉ số bình quân đều = trung bình cộng lợi suất ngày của rổ (đã loại mã có phiên >35%). "
                 "Chênh = hiệu lợi suất 252 phiên, điểm phần trăm. Tự tính — EST.", "vnstore (VCI/VnDirect)", "EST", block)


def build_charts(live, hist, do_rong, ew, warnings, issue=None):
    specs = (("my_lai_suat", lambda: chart_rates(live, issue)),
             ("tpcp_vn_my", lambda: chart_vn_us(live)),
             ("tin_dung_huy_dong", lambda: chart_credit(live, warnings)),
             ("ty_gia", lambda: chart_fx(live)),
             ("du_tru", lambda: chart_reserves(live, warnings)),
             ("do_rong", lambda: chart_breadth(hist, do_rong)),
             ("vni_vs_deu", lambda: chart_ew(ew)))
    out = []
    for cid, fn in specs:
        c = fn()
        if c is None:
            warnings.append("Bỏ biểu đồ %s — thiếu dữ liệu" % cid)
        else:
            out.append(c)
    return out


# ── CSV ──────────────────────────────────────────────────────────────────────

CSV_COLUMNS = ["Mục", "Chỉ báo", "Giá trị", "Kỳ", "Đèn/Trạng thái", "Nhãn", "Ghi chú"]
MAU_TXT = {"xanh": "xanh", "vang": "vàng", "do": "đỏ", "xam": "xám"}


def s(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return fmt_vn(v)
    return str(v)


def build_csv(issue, engine, nguong, neo, tiles):
    rows = []
    ky = s(as_dict(issue).get("ky"))
    if issue:
        _, by_id = block_scores(issue)
        for i in range(1, 9):
            b = as_dict(by_id.get(i))
            if not b:
                continue
            muc = "Khối %d — %s" % (i, nfc(b.get("ten")))
            diem = finite(b.get("diem"))
            rows.append([muc, "Điểm khối", fmt_vn(diem, sign=True), ky, "", "bản tuần", nfc(b.get("doi_ky_nay"))])
            for x in as_list(b.get("den")):
                if isinstance(x, dict):
                    rows.append([muc, nfc(x.get("text")), "", ky, MAU_TXT[norm_mau(x.get("mau"))], "bản tuần", ""])
    if engine:
        for c in engine["to_hop"]:
            rows.append(["Tổ hợp §7", c["ten"], c["gia_tri_txt"], ky, MAU_TXT[c["mau"]], "EST — engine",
                         c["cong_thuc"] + ("; " + c["ghi_chu"] if c.get("ghi_chu") else "")])
        cd = engine["che_do"]
        rows.append(["Chế độ §7", "Engine", cd["ten"], ky,
                     "khớp" if engine["khop"] else ("lệch" if engine["khop"] is False else ""),
                     "EST — engine", cd["ly_giai"]])
        for o in engine["override"]:
            rows.append(["Override §7", "#%d %s" % (o["id"], o["ten"]), o["hieu_luc"], ky, o["trang_thai"],
                         "EST — engine", o["co_so"]])
        for a in engine["kiem"]:
            rows.append(["Kiểm bản tuần", a["muc"], "", ky, "ĐẠT" if a["ok"] else "LỆCH", "EST — engine", a["text"]])
    for r in nguong:
        rows.append(["Ngưỡng đảo chiều", s(r.get("ten")), s(r.get("hien_tai")), ky, s(r.get("trang_thai")),
                     "EST — engine §5.4" if r.get("nguon_hang") == "engine" else "bản tuần", join_notes(s(r.get("live_txt")) and "live " + s(r.get("live_txt")),
                                            s(r.get("live_trang_thai")), s(r.get("ghi_chu")))])
    for r in neo:
        rows.append(["Neo §4", r["chi_bao"], r["hien_tai"], r["ky"], MAU_TXT.get(r["den"], r["den"]), r["tier"],
                     "lành mạnh %s · cảnh báo %s · đỉnh %s" % (r["lanh_manh"], r["canh_bao"], r["dinh"])])
    for t in tiles:
        rows.append(["Live", t["nhan"], t["gia_tri"], t["ky"], MAU_TXT.get(t["mau"], t["mau"]), t["tier"],
                     join_notes(t["ghi_chu"], t["nguon"])])
    return {"columns": CSV_COLUMNS, "rows": rows}


# ── Overview ─────────────────────────────────────────────────────────────────


def staleness(issue):
    ky, ky_sau = parse_day(issue.get("ky")), parse_day(issue.get("ky_sau"))
    now = today()
    if ky is None:
        return None, False, ""
    age = (now - ky).days
    stale = age > STALE_DAYS or (ky_sau is not None and now > ky_sau + timedelta(days=STALE_GRACE_DAYS))
    text = ""
    if stale:
        text = "BẢN TUẦN CŨ %d ngày" % age
        if ky_sau is not None:
            text += " — kỳ %s chưa có" % ddmm(ky_sau)
    return age, stale, text


def build_overview(ky_arg):
    p = paths()
    warnings = []
    issues = list_issues(p["issue_dir"])
    issue, ipath, ierr = load_issue(p["issue_dir"], issues, ky_arg)
    if ierr:
        warnings.append(ierr["error"])
    live = Live(p, warnings)
    try:
        engine = build_engine(issue) if issue else None
        do_rong, hist, ew = build_breadth(live, issue)
        tiles = build_tiles(live, issue)
        nguong = build_thresholds(live, issue)
        ltt = None
        if issue:
            ls_hist = issue_history(p["issue_dir"], issues, s(issue.get("ky")), "ls_huy_dong_6_12t_cao",
                                    n=LTT_WINDOW + 2)
            ltt = build_ltt(live, issue, ls_hist)
            nguong.append(ltt["the"])
            tiles.insert(0, ltt["o"])
        neo = build_anchors(live, issue)
        charts = build_charts(live, hist, do_rong, ew, warnings, issue)
    finally:
        live.close()
    age, stale, stale_text = staleness(issue) if issue else (None, False, "")
    iss = as_dict(issue)
    meta = {"generated": datetime.now(ICT).isoformat(timespec="seconds"), "script_version": SCRIPT_VERSION,
            "issue_dir": p["issue_dir"], "issue_file": ipath, "issues": issues,
            "ky": iss.get("ky"), "ky_sau": iss.get("ky_sau"), "du_lieu_den": iss.get("du_lieu_den"),
            "age_days": age, "stale": stale, "stale_text": stale_text, "issue_error": ierr,
            "disclaimer_danh_muc": DISCLAIMER_PORTFOLIO,
            "warnings": warnings, "sources_live": live.sources}
    return {"meta": meta, "gate": build_gate(engine, iss), "issue": issue, "engine": engine,
            "live": {"tiles": tiles, "do_rong": do_rong}, "nguong": nguong, "neo": neo, "charts": charts,
            "ltt": {k: v for k, v in ltt.items() if k not in ("the", "o")} if ltt else None,
            "csv": build_csv(issue, engine, nguong, neo, tiles)}


# ── CLI ──────────────────────────────────────────────────────────────────────


def run(argv):
    if len(argv) < 2:
        raise SgiError("BAD_ARGS", "Thiếu lệnh. " + USAGE)
    cmd = argv[1].strip().lower()
    if cmd == "issues":
        if len(argv) > 2:
            raise SgiError("BAD_ARGS", "Lệnh issues không nhận tham số. " + USAGE)
        idir = paths()["issue_dir"]
        return {"issues": list_issues(idir), "issue_dir": idir}
    if cmd == "overview":
        if len(argv) > 3:
            raise SgiError("BAD_ARGS", "Thừa tham số. " + USAGE)
        ky = None
        if len(argv) == 3:
            ky = argv[2].strip()
            if not ISSUE_RE.fullmatch(ky) or parse_day(ky) is None:
                raise SgiError("BAD_ARGS", "Kỳ không hợp lệ: %r (cần YYYY-MM-DD). %s" % (argv[2], USAGE))
        return build_overview(ky)
    raise SgiError("BAD_ARGS", "Lệnh không hỗ trợ: %r. %s" % (argv[1], USAGE))


def emit(obj):
    text = json.dumps(clean(obj), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    buf = getattr(sys.stdout, "buffer", None)
    if buf is not None:
        buf.write(text.encode("utf-8") + b"\n")
        buf.flush()
    else:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()


def main(argv=None):
    argv = sys.argv if argv is None else argv
    try:
        out = run(argv)
    except SgiError as exc:
        out = {"error": exc.message, "error_code": exc.code}
    except Exception as exc:  # never let a traceback replace the JSON envelope
        out = {"error": "Lỗi nội bộ sgi_fa.py: %s: %s" % (type(exc).__name__, exc), "error_code": "INTERNAL"}
    emit(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
