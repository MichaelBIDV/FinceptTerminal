#!/usr/bin/env python3
"""
Fincept Terminal — Sổ nguồn data service (tab "so_nguon", sổ tài sản dữ liệu của toàn app).

Thin tab script over the bridge core fincept_bridge/so_nguon.py (audit, refresh plan, detached runner).
Feeds src/screens/so_nguon/SoNguonPanel through EconomicsService / PythonRunner and shapes the WHOLE page
as a "vnblocks/1" document (key list: scripts/msn_reflex.py docstring, renderer src/screens/vnblocks/).
Stdlib only; Python 3.9+. This script makes NO network calls itself: `lam_moi` only asks the core to spawn
its detached runner, which runs one normal goi_nguon cycle (its Vietcap jobs keep their own DEN_HAN) plus the
due, vetted producers (Vietcap only through lk_lich / vc_lk_fetch, never dulieukinhte.com/api/internal/).

Two layers, never mixed:
  A — nguồn gốc (launchpad/songuon_registry.json, hand-written, read-only): two separate tables, one per
      evidence scale — he=ck (FACT-T1 > FACT-T2 > SS-T3 > EST > UNVERIFIED) and he=beri (T1..T4).
  B — tài sản dữ liệu (fincept_bridge/so_nguon_dangky.py): freshness measured by the core's audit.
Audit counts, ages and run steps are measurements of this machine's files, not market numbers: they carry
no evidence tier. The "Bậc" column is the tier of the data an asset holds (BERI-scale values are marked).

Inputs:
    SO_NGUON_BRIDGE   ~/SECOND BRAIN-OBSIDIAN/_System/fincept_bridge — must contain so_nguon.py; the core
                      reads its own SO_NGUON_* variables (SYS, HOME, REPO, AGENTS, DRY …), tests set them.

USAGE
    python3 so_nguon_tab.py overview     audit + current run status → page (read-only; < 3 s)
    python3 so_nguon_tab.py lam_moi      FETCH: start ONE detached refresh run, then the overview
    python3 so_nguon_tab.py trang_thai   run status only (polled every 3 s while run.dang_chay)

OUTPUT — exactly ONE compact JSON object on stdout (UTF-8, ensure_ascii=False), exit code 0 even on errors.
Top-level errors replace the payload:
    {"error": "<Vietnamese message incl. what to do>",
     "error_code": "NO_BRIDGE" | "BAD_ARGS" | "RUN_FAILED" | "INTERNAL"}

overview / lam_moi →
{
 "meta": {"generated": ISO+07:00, "script_version", "lenh", "bridge", "cap_nhat": audit time ISO,
          "n_tai_san": int, "warnings": [str], "sources_live": [{"ten", "duong_dan", "as_of", "ok", "ghi_chu"}]},
 "trang": {"schema": "vnblocks/1", "tieu_de", "sections": [...]}   ids in order:
          tom_tat · van_de · lam_moi · tai_san · lich · goc_ck · goc_beri · phap_ly
 "csv": {"columns": [21 names], "rows": [one row per asset: registry fields + audit state]},
 "run": RUN
}
trang_thai → {"meta": {"generated", "script_version", "lenh"}, "run": RUN, "section": <section "lam_moi">}
RUN = {"run_id": str|null, "dang_chay": bool, "dry": bool, "bat_dau", "xong_luc", "ghi_chu"?,
       "n_buoc", "n_xong", "n_loi", "nhan": "đang làm mới 2/3 bước" | "làm mới xong 24/09 18:40 · 0 lỗi" | "",
       "ke_hoach_tom": {"n_chay", "n_bo_qua", "lap_luc"},
       "buoc": [{"id", "ten", "cach", "lenh", "trang_thai": cho|dang_chay|xong|loi|bo_qua, "trang_thai_txt",
                 "bat_dau", "xong", "giay", "ma_thoat", "ghi_chu"}]}
       (the plan itself is not repeated in RUN — the "lam_moi" section shows it)
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone

SCRIPT_VERSION = "1.0"
ICT = timezone(timedelta(hours=7), "ICT")
CAN = "[CẦN DATA]"
MINUS = "−"
USAGE = "Dùng: so_nguon_tab.py overview | lam_moi | trang_thai"
BRIDGE_MAC_DINH = os.path.join(os.path.expanduser("~"), "SECOND BRAIN-OBSIDIAN", "_System", "fincept_bridge")
CORE_API = ("audit", "ke_hoach_lam_moi", "bat_dau_lam_moi", "trang_thai_lam_moi", "duong", "load_registry")

TT_MAU = {"TƯƠI": "xanh", "CŨ": "vang", "HỎNG": "do", "THIẾU": "do", "KHÔNG ĐO": "xam"}
MUC_TXT = {"do": ("ĐỎ", "do"), "vang": ("VÀNG", "vang"), "xam": ("XÁM", "xam")}
LOAI_VAN_DE = {"cu": "cũ", "hong": "hỏng", "thieu": "thiếu", "cam": "cấm", "khong_lich": "không lịch",
               "mo_coi": "mồ côi", "lech_dashboard": "lệch ngưỡng", "crawl_delay": "crawl-delay", "khac": "khác"}
BUOC_TXT = {"cho": ("CHỜ", "xam"), "dang_chay": ("ĐANG CHẠY", "vang"), "xong": ("XONG", "xanh"),
            "loi": ("LỖI", "do"), "bo_qua": ("BỎ QUA", "lam")}
CACH_TXT = {"goi": "bộ điều phối", "so": "script", "launchd": "LaunchAgent"}
KIEU_PRODUCER = {"goi": "bộ điều phối", "so": "script", "launchd": "LaunchAgent", "cowork": "Cowork",
                 "thu_cong": "thủ công", "tinh_khi_doc": "tính khi đọc", "upstream": "upstream"}
NHOM_TXT = {"vi_mo": "Vĩ mô", "chung_khoan": "Chứng khoán", "lang_kinh": "Lăng Kính", "deepfa": "DeepFA",
            "tin": "Tin tức", "van_hanh": "Vận hành", "hhp": "Định giá HHP", "beri": "BERI",
            "app_noi_bo": "Nội bộ app", "msn": "MSN Reflex"}
TAB_TXT = {"sgi_fa": "SGI FA", "msn_reflex": "MSN Reflex", "hhp_valuation": "Định giá HHP",
           "langkinh": "Lăng Kính", "deepfa": "DeepFA", "beri": "BERI", "economics": "Macro",
           "dashboard": "Dashboard", "news": "News", "equity_research": "Equity Research", "markets": "Markets",
           "portfolio": "Portfolio", "watchlist": "Watchlist", "so_nguon": "Sổ nguồn"}
GOC_TT = {"song": ("đang chảy", "xanh"), "thu_cong": ("thủ công", "vang"), "chan": ("bị chặn", "do"),
          "chua_co": ("chưa có", "xam")}
PHAP_LY_TXT = {"cam": ("CẤM", "do"), "canh_bao": ("CẢNH BÁO", "vang"), "chua_kiem": ("chưa kiểm", "xam")}
TIER_MAU = {"FACT-T1": "xanh", "FACT-T2": "xanh", "SS-T3": "lam", "EST": "vang", "NEWS": "tim",
            "UNVERIFIED": "do"}
BERI_TIER = re.compile(r"^T[1-4]$")
THANG_CK = "FACT-T1 (BCTC/CBTT) > FACT-T2 (BCTN/NQ ĐHCĐ) > SS-T3 (sell-side) > EST > UNVERIFIED"
THANG_BERI = "T1..T4 — sell-side = T4, KG nội bộ = T2 (Sổ đăng ký nguồn BERI 13/8/2026)"
CSV_COLUMNS = ["ID", "Tên", "Nhóm", "Loại", "Đường dẫn", "Đo độ tươi", "Mốc", "Tuổi (giờ)", "Ngưỡng (giờ)",
               "Trạng thái", "Producer", "Kiểu producer", "Lịch", "Nhịp", "Làm mới khi FETCH", "Tab dùng",
               "Bậc", "Nguồn gốc (lớp A)", "Pháp lý", "Ghi chú pháp lý", "Ghi chú"]


class TabError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# ── Formatting ───────────────────────────────────────────────────────────────


def nfc(s):
    return unicodedata.normalize("NFC", s).strip() if isinstance(s, str) else ""


def finite(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def fmt_vn(v, dec=1):
    """Vietnamese number: 91.6→"91,6", 2700→"2.700", -1.5→"−1,5". None → "[CẦN DATA]"."""
    f = finite(v)
    if f is None:
        return CAN
    s = "%.*f" % (dec, abs(f))
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    whole, _, frac = s.partition(".")
    grouped = ""
    while len(whole) > 3:
        grouped = "." + whole[-3:] + grouped
        whole = whole[:-3]
    body = whole + grouped + ("," + frac if frac else "")
    return (MINUS + body) if f < 0 and float(s) != 0.0 else body


def doc_luc(v):
    """ISO timestamp → aware datetime in ICT (naive = ICT); None when absent/unparsable."""
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        t = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=ICT)).astimezone(ICT)


def luc_txt(v, now=None):
    """"24/09 18:40" (same year as now) or "08/08/2025 00:02"; "—" when absent."""
    t = doc_luc(v)
    if t is None:
        return "—"
    now = now or datetime.now(ICT)
    return t.strftime("%d/%m %H:%M") if t.year == now.year else t.strftime("%d/%m/%Y %H:%M")


def tuoi_txt(gio):
    """Age in hours → "35 phút" · "7,4 giờ" · "3,8 ngày"."""
    h = finite(gio)
    if h is None:
        return None
    if h < 1:
        return "%d phút" % round(h * 60)
    if h < 48:
        return fmt_vn(h, 1) + " giờ"
    return fmt_vn(h / 24, 1) + " ngày"


def giay_txt(s):
    f = finite(s)
    if f is None:
        return "—"
    return (fmt_vn(f, 1) + " giây") if f < 120 else (fmt_vn(f / 60, 1) + " phút")


# ── vnblocks helpers ─────────────────────────────────────────────────────────


def sec(sid, so, tieu_de, khoi, eyebrow="", lede=""):
    return {"id": sid, "so": so, "tieu_de": nfc(tieu_de), "eyebrow": nfc(eyebrow), "lede": nfc(lede),
            "khoi": [b for b in khoi if b]}


def doan(text, mau=None, the=False, tieu_de=None):
    text = nfc(text)
    if not text and not tieu_de:
        return None
    b = {"kieu": "doan", "text": text}
    if mau:
        b["mau"] = mau
    if the:
        b["the"] = True
        if tieu_de:
            b["tieu_de"] = nfc(tieu_de)
    return b


def heading(text):
    """Sub-heading: a plain paragraph with a colour renders bold."""
    return doan(text, mau="vang")


def cell(t, mau=None, pill=False, mono=False, dam=False, tip=None):
    c = {"t": nfc(t) if isinstance(t, str) else ("" if t is None else str(t))}
    if mau:
        c["mau"] = mau
    if pill:
        c["pill"] = True
    if mono:
        c["mono"] = True
    if dam:
        c["dam"] = True
    if tip and nfc(tip):
        c["tip"] = nfc(tip)
    return c


def bang(cot, dong, chu_thich="", can_phai=None):
    b = {"kieu": "bang", "cot": [nfc(c) for c in cot],
         "dong": [[c if isinstance(c, dict) else cell(c) for c in r] for r in dong]}
    if nfc(chu_thich):
        b["chu_thich"] = nfc(chu_thich)
    if can_phai:
        b["can_phai"] = list(can_phai)
    return b


def tile(nhan, gia_tri, phu="", mau=None):
    t = {"nhan": nfc(nhan), "gia_tri": nfc(gia_tri) or CAN, "phu": nfc(phu), "tier": "", "live": False}
    if mau:
        t["mau"] = mau
    return t


def canh_bao(tieu_de, muc, mau="vang"):
    muc = [nfc(m) for m in muc if nfc(m)]
    return {"kieu": "canh_bao", "tieu_de": nfc(tieu_de), "muc": muc, "mau": mau} if muc else None


# ── Core loading ─────────────────────────────────────────────────────────────


def bridge_dir():
    return os.environ.get("SO_NGUON_BRIDGE") or BRIDGE_MAC_DINH


def nap_core():
    """Import so_nguon.py from the bridge by path (a fresh module each call: tests swap bridges)."""
    b = bridge_dir()
    p = os.path.join(b, "so_nguon.py")
    if not os.path.isfile(p):
        raise TabError("NO_BRIDGE", "Không thấy lõi Sổ nguồn %s. Kiểm thư mục fincept_bridge hoặc đặt biến môi "
                                    "trường SO_NGUON_BRIDGE trỏ tới thư mục chứa so_nguon.py." % p)
    if b not in sys.path:
        sys.path.insert(0, b)
    try:
        spec = importlib.util.spec_from_file_location("so_nguon", p)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["so_nguon"] = mod
        spec.loader.exec_module(mod)
    except Exception as exc:  # a broken core must still yield a JSON envelope
        sys.modules.pop("so_nguon", None)
        raise TabError("NO_BRIDGE", "Không nạp được %s: %s: %s. Chạy thử: python3 %s audit"
                       % (p, type(exc).__name__, exc, p)) from exc
    thieu = [f for f in CORE_API if not callable(getattr(mod, f, None))]
    if thieu:
        raise TabError("NO_BRIDGE", "Bản so_nguon.py tại %s thiếu hàm: %s — cập nhật lõi Sổ nguồn."
                       % (p, ", ".join(thieu)))
    return mod


# ── Path shortening (display only) ───────────────────────────────────────────


class Ngan:
    """Shortens absolute paths / interpreter paths for display; placeholders of the registry too."""

    def __init__(self, core):
        P = core.duong()
        self.cap = [(str(P["bridge"]), "fincept_bridge"), (str(P["sys"]), "_System"),
                    (str(P["repo"]), "fincept-qt"), (str(P["home"]), "~")]

    def duong(self, s):
        s = nfc(s)
        for goc, ten in self.cap:
            if goc and s.startswith(goc):
                return ten + s[len(goc):]
        return s

    def text(self, s):
        s = nfc(s).replace("{PY}", "python3").replace("{BRIDGE}", "fincept_bridge").replace("{SYS}", "_System")
        for goc, ten in self.cap:
            if goc:
                s = s.replace(goc, ten)
        return s

    def lenh(self, argv):
        if not argv:
            return ""
        out = []
        for i, a in enumerate(argv):
            a = str(a)
            if i == 0 and (os.path.basename(a).startswith("python") or a == "{PY}"):
                out.append("python3")
            else:
                out.append(self.text(a))
        return " ".join(out)


# ── Run status ───────────────────────────────────────────────────────────────


def ten_buoc(b):
    if b.get("id") == "goi_nguon":
        return "goi_nguon — một lượt bộ điều phối"
    if b.get("id") == "audit":
        return "Kiểm lại Sổ nguồn"
    tep = next((os.path.basename(str(a)) for a in (b.get("lenh") or []) if str(a).endswith((".py", ".sh"))), "")
    return "%s · %s" % (b.get("id"), tep) if tep else str(b.get("id") or "")


def run_gon(tt, now):
    """Core run status → the small RUN object (plan summarised, step names and labels added)."""
    tt = tt or {}
    kh = tt.get("ke_hoach") or {}
    buoc = []
    for b in tt.get("buoc") or []:
        st = b.get("trang_thai") or "cho"
        buoc.append({"id": b.get("id"), "ten": ten_buoc(b), "cach": b.get("cach"), "lenh": b.get("lenh"),
                     "trang_thai": st, "trang_thai_txt": BUOC_TXT.get(st, (st, ""))[0],
                     "bat_dau": b.get("bat_dau"), "xong": b.get("xong"), "giay": b.get("giay"),
                     "ma_thoat": b.get("ma_thoat"), "ghi_chu": nfc(b.get("ghi_chu"))})
    n_xong = sum(1 for b in buoc if b["trang_thai"] in ("xong", "loi", "bo_qua"))
    n_loi = sum(1 for b in buoc if b["trang_thai"] == "loi")
    dang = bool(tt.get("dang_chay"))
    if dang:
        nhan = "đang làm mới %d/%d bước" % (n_xong, len(buoc))
    elif tt.get("run_id") and tt.get("xong_luc"):
        nhan = "làm mới xong %s · %d lỗi" % (luc_txt(tt.get("xong_luc"), now), n_loi)
    elif tt.get("run_id"):
        nhan = "lượt làm mới dừng giữa chừng"
    else:
        nhan = ""
    r = {"run_id": tt.get("run_id"), "dang_chay": dang, "dry": bool(tt.get("dry")),
         "bat_dau": tt.get("bat_dau"), "xong_luc": tt.get("xong_luc"), "n_buoc": len(buoc), "n_xong": n_xong,
         "n_loi": n_loi, "nhan": nhan,
         "ke_hoach_tom": {"n_chay": len(kh.get("chay") or []), "n_bo_qua": len(kh.get("bo_qua") or []),
                          "lap_luc": kh.get("lap_luc")},
         "buoc": buoc}
    if nfc(tt.get("ghi_chu")):
        r["ghi_chu"] = nfc(tt.get("ghi_chu"))
    return r


def bang_ke_hoach(kh, ng, now):
    """The plan's "chay" steps (what FETCH would run)."""
    rows = []
    for i, s in enumerate(kh.get("chay") or [], 1):
        ts = s.get("tai_san") or []
        rows.append([cell(str(i), mono=True), cell(ten_buoc(s), dam=True),
                     CACH_TXT.get(s.get("cach"), nfc(s.get("cach"))),
                     cell(ng.lenh(s.get("lenh")), mono=True),
                     ng.text(s.get("ly_do")),
                     cell("%d tài sản" % len(ts), tip=", ".join(ts))])
    if not rows:
        return doan("Không có bước nào đến hạn — FETCH lúc này chỉ kiểm lại Sổ nguồn.", mau="xanh")
    return bang(["#", "Bước", "Cách", "Lệnh", "Lý do", "Phủ"], rows,
                chu_thich="Lập lúc %s. Chạy lần lượt từng bước, không song song; cuối lượt luôn kiểm lại và ghi "
                          "data/so_nguon_audit.json." % luc_txt(kh.get("lap_luc"), now),
                can_phai=[0])


def bang_bo_qua(kh, ng):
    """Skipped rows grouped by reason (the per-row age in the reason is folded into the asset list)."""
    nhom, thu_tu = {}, []
    for s in kh.get("bo_qua") or []:
        ly_do = nfc(s.get("ly_do"))
        m = re.search(r"\s*\((tuổi [^)]*)\)\s*$", ly_do)
        goc = ly_do[:m.start()] if m else ly_do
        if goc not in nhom:
            nhom[goc] = []
            thu_tu.append(goc)
        nhom[goc].append("%s (%s)" % (s.get("id"), m.group(1)) if m else str(s.get("id")))
    if not thu_tu:
        return None
    rows = [[ng.text(g), cell(str(len(nhom[g])), mono=True), ", ".join(nhom[g])] for g in thu_tu]
    n = sum(len(v) for v in nhom.values())
    return bang(["Lý do bỏ qua", "Số", "Tài sản"], rows,
                chu_thich="%d tài sản không chạy trong lượt này. LaunchAgent gọi Vietcap trực tiếp hoặc gửi Telegram "
                          "không bao giờ được FETCH chạy." % n,
                can_phai=[1])


def sec_lam_moi(run, kh_run, kh_nay, ng, now):
    """Section "lam_moi": the current / last run (tiles + steps) and the plan. The poll rebuilds it alone."""
    khoi = []
    if not run.get("run_id"):
        khoi.append(doan("Chưa có lượt làm mới nào. FETCH mở MỘT tiến trình nền chạy lần lượt các bước "
                         + ("dưới đây" if kh_nay is not None else "đến hạn") + "; tiến độ từng bước hiện ở mục này."))
    else:
        dang = run["dang_chay"]
        if dang:
            tt, mau = "ĐANG CHẠY", "vang"
        elif run.get("xong_luc"):
            tt, mau = "XONG", ("do" if run["n_loi"] else "xanh")
        else:
            tt, mau = "DỪNG GIỮA CHỪNG", "do"
        khoi.append({"kieu": "o_so", "cot": 4, "o": [
            tile("Trạng thái", tt, "lượt " + str(run["run_id"]), mau),
            tile("Tiến độ", "%d/%d bước" % (run["n_xong"], run["n_buoc"]),
                 "%d lỗi" % run["n_loi"], "do" if run["n_loi"] else None),
            tile("Bắt đầu", luc_txt(run.get("bat_dau"), now), ""),
            tile("Xong lúc", luc_txt(run.get("xong_luc"), now) if run.get("xong_luc") else "—",
                 "đang chạy" if dang else "")]})
        if run.get("dry"):
            khoi.append(canh_bao("Chạy khô (SO_NGUON_DRY=1)",
                                 ["Lượt này chỉ ghi lệnh SẼ chạy — không producer nào chạy thật."], "vang"))
        if run.get("ghi_chu"):
            khoi.append(doan(run["ghi_chu"], mau="do", the=True, tieu_de="Lượt làm mới"))
        rows = []
        bd = doc_luc(run.get("bat_dau"))
        for i, b in enumerate(run["buoc"], 1):
            txt, m = BUOC_TXT.get(b["trang_thai"], (b["trang_thai"], "xam"))
            if b["trang_thai"] == "dang_chay" and doc_luc(b.get("bat_dau")):
                thoi_gian = giay_txt((now - doc_luc(b["bat_dau"])).total_seconds()) + " · đang chạy"
            else:
                thoi_gian = giay_txt(b.get("giay"))
            rows.append([cell(str(i), mono=True), cell(b["ten"], dam=True, tip=ng.lenh(b.get("lenh"))),
                         CACH_TXT.get(b.get("cach"), nfc(b.get("cach"))), cell(txt, mau=m, pill=True),
                         cell(luc_txt(b.get("bat_dau"), now) if b.get("bat_dau") else "—", mono=True),
                         cell(thoi_gian, mono=True),
                         cell("—" if b.get("ma_thoat") is None else str(b.get("ma_thoat")), mono=True),
                         ng.text(b.get("ghi_chu")) or "—"])
        khoi.append(bang(["#", "Bước", "Cách", "Trạng thái", "Bắt đầu", "Thời gian", "Mã thoát", "Ghi chú"], rows,
                         chu_thich=("Bắt đầu %s. " % luc_txt(run.get("bat_dau"), now) if bd else "") +
                         "Mã thoát 4 của vc_lk_fetch = đang chạy ở tiến trình khác, không phải lỗi; goi_nguon gặp "
                         "khoá bận thì bước ghi BỎ QUA.", can_phai=[0]))
        goi = next((s for s in (kh_run or {}).get("chay") or [] if s.get("id") == "goi_nguon"), None)
        if goi and goi.get("tai_san"):
            khoi.append(doan("Bước goi_nguon phủ %d tài sản: %s. Bộ điều phối tự quyết job nào đến hạn (DEN_HAN, "
                             "khung giờ, hạn mức) — không dùng --chi."
                             % (len(goi["tai_san"]), ", ".join(goi["tai_san"]))))
        if run["dang_chay"] and kh_run:
            khoi.append(heading("Bỏ qua trong lượt này"))
            khoi.append(bang_bo_qua(kh_run, ng))
    if kh_nay is not None:
        khoi.append(heading("Nếu bấm FETCH lúc %s" % luc_txt(kh_nay.get("lap_luc"), now)))
        khoi.append(bang_ke_hoach(kh_nay, ng, now))
        khoi.append(bang_bo_qua(kh_nay, ng))
    return sec("lam_moi", "III", "Lượt làm mới", khoi, eyebrow="FETCH · tiến trình nền tách rời",
               lede="FETCH làm mới mọi nguồn ĐẾN HẠN của toàn app: một lượt goi_nguon thường + các producer đã "
                    "kiểm lệnh, từng bước một. Không gọi Vietcap ngoài bộ điều phối (job tự giữ DEN_HAN) và "
                    "lk_lich / vc_lk_fetch, không gọi dulieukinhte.com/api/internal/.")


# ── Overview sections ────────────────────────────────────────────────────────


def sec_tom_tat(a, hits, goc, now):
    t = a.get("tom_tat") or {}
    n = lambda k: int(t.get(k) or 0)  # noqa: E731
    song = sum(1 for h in hits if h.get("song"))
    bak = len(hits) - song
    o = [tile("Tài sản dữ liệu", str(n("n")), "dòng trong so_nguon_dangky.py"),
         tile("Tươi", str(n("tuoi")), "trong ngưỡng SLA", "xanh"),
         tile("Cũ", str(n("cu")), "quá ngưỡng SLA", "vang" if n("cu") else None),
         tile("Hỏng", str(n("hong")), "đọc/đo thất bại", "do" if n("hong") else None),
         tile("Thiếu", str(n("thieu")), "không thấy tệp", "do" if n("thieu") else None),
         tile("Không đo", str(n("khong_do")), "không có mốc đo được", "xam"),
         tile("Vấn đề đỏ", str(n("van_de_do")), "cần xử lý trước", "do" if n("van_de_do") else "xanh"),
         tile("Vấn đề vàng", str(n("van_de_vang")), "theo dõi", "vang" if n("van_de_vang") else None),
         tile("Không lịch", str(n("khong_lich")), "không ai làm mới tự động", "vang" if n("khong_lich") else None),
         tile("Mồ côi", str(n("mo_coi")), "không tab nào đọc", "xam"),
         tile("Pháp lý cấm", str(n("cam")), "đã chặn — không đọc, không FETCH", "xam"),
         tile("Mã gọi đường cấm", str(song), "%d dòng trong bản .bak không chạy" % bak if bak else "không có",
              "do" if song else "xanh")]
    lede = "Kiểm lúc %s trên tệp thật của máy này. Số đếm là đo trạng thái tệp — không phải số thị trường, " \
           "không mang bậc bằng chứng." % luc_txt(a.get("cap_nhat"), now)
    if goc.get("cap_nhat"):
        lede += " Sổ nguồn gốc lớp A (viết tay) cập nhật %s." % nfc(goc.get("cap_nhat"))
    khoi = [{"kieu": "o_so", "o": o, "cot": 4}]
    if n("loi_dang_ky"):
        khoi.append(doan("Sổ đăng ký có %d lỗi lược đồ — xem mục Vấn đề (loại khác)." % n("loi_dang_ky"),
                         mau="do", the=True, tieu_de="Sổ đăng ký"))
    return sec("tom_tat", "I", "Tóm tắt", khoi, eyebrow="Sổ nguồn · lớp B tài sản dữ liệu", lede=lede)


def dong_van_de(v, ng):
    txt, m = MUC_TXT.get(v.get("muc"), (nfc(v.get("muc")) or "—", "xam"))
    return [cell(txt, mau=m, pill=True), LOAI_VAN_DE.get(v.get("loai"), nfc(v.get("loai")) or "—"),
            cell(nfc(v.get("id")) or "—", mono=True), ng.text(v.get("text")), ng.text(v.get("goi_y")) or "—"]


def sec_van_de(a, ng):
    vd = a.get("van_de") or []
    chinh = [v for v in vd if v.get("muc") in ("do", "vang")]
    xam = [v for v in vd if v.get("muc") not in ("do", "vang")]
    cot = ["Mức", "Loại", "Tài sản", "Vấn đề", "Gợi ý"]
    khoi = []
    if chinh:
        khoi.append(bang(cot, [dong_van_de(v, ng) for v in chinh],
                         chu_thich="Đỏ = tài sản có tab đang đọc mà hỏng / thiếu / cũ quá 2× ngưỡng, job không có "
                                   "trong LICH, hoặc mã gọi đường cấm còn chạy. Vàng = cũ, lịch tắt/lỗi, cảnh báo "
                                   "pháp lý hoặc nhịp gọi."))
    else:
        khoi.append(doan("Không có vấn đề đỏ hay vàng.", mau="xanh"))
    if xam:
        khoi.append(heading("Mức xám — thông tin, không chặn (%d)" % len(xam)))
        khoi.append(bang(cot, [dong_van_de(v, ng) for v in xam]))
    return sec("van_de", "II", "Vấn đề cần xử lý", khoi, eyebrow="xếp theo mức — đỏ trước",
               lede="%d vấn đề: %d đỏ · %d vàng · %d xám." % (
                   len(vd), sum(1 for v in vd if v.get("muc") == "do"),
                   sum(1 for v in vd if v.get("muc") == "vang"), len(xam)))


def mau_tai_san(ts):
    tt = ts.get("trang_thai")
    if tt == "CŨ":
        ng, tuoi = finite(ts.get("nguong_gio")), finite(ts.get("tuoi_gio"))
        return "do" if ts.get("tieu_thu") and ng and tuoi is not None and tuoi > 2 * ng else "vang"
    if tt == "THIẾU" and not ts.get("tieu_thu"):
        return "vang"
    return TT_MAU.get(tt, "xam")


def do_tuoi_txt(dt):
    k = (dt or {}).get("kieu")
    if k == "khoa_json":
        return "khoá JSON %s" % dt.get("khoa")
    if k == "goi_status":
        return "trạng thái job %s (goi_nguon_status)" % dt.get("khoa")
    return {"mtime": "mtime tệp", "sqlite": "truy vấn SQLite", "khong_do": "không đo"}.get(k, nfc(k) or "—")


def tier_cell(bac):
    bac = nfc(bac)
    if not bac:
        return cell("—", mau="xam", tip="Tài sản vận hành — không mang số liệu có bậc")
    if BERI_TIER.match(bac):
        return cell(bac + " · BERI", mono=True, mau="xam", tip="Thang BERI " + THANG_BERI + " — không so với thang "
                    "Chứng khoán")
    return cell(bac, mono=True, mau=TIER_MAU.get(bac))


def tuoi_cell(ts, now):
    tt = ts.get("trang_thai")
    tuoi = tuoi_txt(ts.get("tuoi_gio"))
    ng = finite(ts.get("nguong_gio"))
    sla = ("SLA " + (fmt_vn(ng, 0) + " giờ" if ng < 48 else tuoi_txt(ng))) if ng is not None else "không SLA"
    if tuoi is None:
        tuoi = {"THIẾU": "không thấy tệp", "HỎNG": "không đo được"}.get(tt, "không đo")
        if (ts.get("phap_ly") or {}).get("trang_thai") == "cam":
            tuoi = "không đọc (cấm)"
    tip = ("mốc " + luc_txt(ts.get("moc"), now)) if ts.get("moc") else ""
    return cell("%s / %s" % (tuoi, sla), mono=True, tip=tip)


def dong_tai_san(ts, ng, now):
    p = ts.get("producer") or {}
    pl = ts.get("phap_ly") or {}
    k = p.get("kieu")
    tip_p = " · ".join(x for x in (
        ("lệnh: " + ng.lenh(p.get("lenh"))) if p.get("lenh") else "",
        ("mạng: " + nfc(p.get("mang"))) if p.get("mang") else "",
        ("lịch: " + nfc(p.get("lich"))) if p.get("lich") else "",
        "FETCH: " + ("làm mới" if (k == "goi" or p.get("lam_moi_khi_fetch")) else "không")) if x)
    tip_ten = " · ".join(x for x in (ng.text(ts.get("duong_dan")), "đo: " + do_tuoi_txt(ts.get("do_tuoi")),
                                     ng.text(ts.get("ghi_chu"))) if x)
    tabs = [TAB_TXT.get(x, x) for x in ts.get("tieu_thu") or []]
    if pl.get("trang_thai") in PHAP_LY_TXT:
        txt, m = PHAP_LY_TXT[pl["trang_thai"]]
        phap_ly = cell(txt, mau=m, pill=pl["trang_thai"] != "chua_kiem", tip=pl.get("ghi_chu"))
    else:
        phap_ly = cell(nfc(pl.get("trang_thai")) or "—", mau="xanh" if pl.get("trang_thai") == "ok" else None,
                       tip=pl.get("ghi_chu"))
    return [cell(ts.get("id"), mono=True), cell(ts.get("ten"), tip=tip_ten),
            cell("[%s] %s" % (KIEU_PRODUCER.get(k, nfc(k) or "?"), nfc(p.get("ten"))), tip=tip_p),
            nfc(ts.get("nhip")) or "—", tuoi_cell(ts, now),
            cell(nfc(ts.get("trang_thai")) or "—", mau=mau_tai_san(ts), pill=True),
            ", ".join(tabs) if tabs else cell("không tab nào", mau="xam"),
            tier_cell(ts.get("bac")), phap_ly]


def sec_tai_san(a, ng, now):
    nhom, thu_tu = {}, []
    for ts in a.get("tai_san") or []:
        g = ts.get("nhom") or "khac"
        if g not in nhom:
            nhom[g] = []
            thu_tu.append(g)
        nhom[g].append(ts)
    khoi = []
    cot = ["ID", "Tên", "Producer", "Nhịp", "Tuổi / SLA", "Trạng thái", "Tab dùng", "Bậc", "Pháp lý"]
    for g in thu_tu:
        rows = nhom[g]
        dem = {}
        for ts in rows:
            dem[ts.get("trang_thai")] = dem.get(ts.get("trang_thai"), 0) + 1
        tom = " · ".join("%d %s" % (dem[k], k.lower()) for k in ("TƯƠI", "CŨ", "HỎNG", "THIẾU", "KHÔNG ĐO")
                         if dem.get(k))
        maus = {mau_tai_san(ts) for ts in rows}
        mau = "do" if "do" in maus else ("vang" if "vang" in maus else "xanh")
        khoi.append(doan("%s · %d tài sản · %s" % (NHOM_TXT.get(g, g), len(rows), tom), mau=mau))
        khoi.append(bang(cot, [dong_tai_san(ts, ng, now) for ts in rows]))
    if not khoi:
        khoi.append(doan("Sổ đăng ký trống — không có tài sản nào để kiểm.", mau="do"))
    return sec("tai_san", "IV", "Tài sản dữ liệu", khoi, eyebrow="lớp B · nhóm theo mảng",
               lede="Mỗi tài sản: tệp/kho app đọc, ai sinh ra nó, nhịp, tuổi đo theo mốc BÊN TRONG dữ liệu khi có "
                    "(không tin mtime), tab đang dùng, bậc bằng chứng của số liệu nó mang. Rê chuột lên tên / "
                    "producer / tuổi để xem đường dẫn, lệnh và mốc.")


def sec_lich(a, now):
    lich = a.get("lich") or []
    goi = [x for x in lich if x.get("nguon") == "goi"]
    khac = {"launchd": [x for x in lich if x.get("nguon") == "launchd"],
            "cowork": [x for x in lich if x.get("nguon") == "cowork"]}
    khoi = []
    if goi:
        rows = []
        for x in goi:
            st = nfc(x.get("trang_thai"))
            m = "xanh" if st == "ok" else ("do" if st.startswith("lỗi") else "xam")
            rows.append([cell(x.get("ten"), mono=True), cell(x.get("module"), mono=True), nfc(x.get("nhip")) or "—",
                         cell(fmt_vn(x.get("nguong_gio"), 0) + " giờ" if finite(x.get("nguong_gio")) is not None
                              else "—", mono=True),
                         cell(st or "—", mau=m, pill=True), cell(luc_txt(x.get("moc_log"), now), mono=True),
                         ", ".join(x.get("tai_san") or []) or cell("—", mau="xam")])
        khoi.append(heading("Bộ điều phối goi_nguon (LaunchAgent com.hoidongcovanai.fincept-goi) · %d job" % len(goi)))
        khoi.append(bang(["Job", "Module", "Nhịp", "Ngưỡng", "Trạng thái", "Chạy lần cuối", "Tài sản"], rows,
                         chu_thich="LICH đọc thẳng từ mã goi_nguon.py; trạng thái từ data/goi_nguon_status.json."))
    else:
        khoi.append(doan("Không đọc được goi_nguon.LICH.", mau="do"))
    for kieu, ten in (("launchd", "LaunchAgent riêng"), ("cowork", "Lịch Cowork / Claude")):
        rows = []
        for x in khac[kieu]:
            st = nfc(x.get("trang_thai"))
            m = "vang" if ("TẮT" in st or "chưa nạp" in st) else ("do" if "không thấy" in st else "xanh")
            rows.append([cell(x.get("ten"), mono=True), nfc(x.get("nhip")) or CAN, cell(st or "—", mau=m, pill=True),
                         cell(luc_txt(x.get("moc_log"), now), mono=True),
                         cell(nfc(x.get("co")) or "—", mau="vang" if nfc(x.get("co")) else None),
                         ", ".join(x.get("tai_san") or []) or "—"])
        if rows:
            khoi.append(heading("%s · %d lịch" % (ten, len(rows))))
            khoi.append(bang(["Lịch", "Nhịp", "Trạng thái", "Log cuối", "Cờ", "Tài sản"], rows,
                             chu_thich="Từ data/lich_so.json. FETCH không chạy các producer này — chỉ báo lịch."))
    return sec("lich", "V", "Lịch cập nhật", khoi, eyebrow="goi LICH · LaunchAgent · Cowork",
               lede="Ai làm mới tài sản nào, bao lâu một lần, lần chạy cuối.")


def sec_goc(he, so, rows, ghi_chu_goc, cap_nhat):
    if he == "ck":
        thang = next((x.split("→", 1)[1].strip() for x in ghi_chu_goc if "he=ck" in x and "→" in x), THANG_CK)
        tieu_de, sid = "Nguồn gốc — hệ Chứng khoán", "goc_ck"
    else:
        thang = next((x.split("→", 1)[1].strip() for x in ghi_chu_goc if "he=beri" in x and "→" in x), THANG_BERI)
        tieu_de, sid = "Nguồn gốc — hệ BERI", "goc_beri"
    out = []
    for g in rows:
        tt, m = GOC_TT.get(g.get("trang_thai"), (nfc(g.get("trang_thai")) or "—", "xam"))
        tan_suat = nfc(g.get("tan_suat")) or "—"
        if nfc(g.get("do_tre")):
            tan_suat += " · trễ " + nfc(g.get("do_tre"))
        tip = " · ".join(x for x in (nfc(g.get("id")), nfc(g.get("kiem"))) if x)
        out.append([cell(g.get("ten"), dam=True, tip=tip),
                    nfc(g.get("nhom")) or "—", cell(nfc(g.get("tier")) or CAN, mono=True),
                    " · ".join(x for x in (nfc(g.get("nguon_goc")), nfc(g.get("kenh"))) if x) or "—",
                    tan_suat, cell(tt, mau=m, pill=True),
                    ", ".join(g.get("tai_san") or []) or cell("—", mau="xam"), nfc(g.get("ghi_chu")) or "—"])
    khoi = []
    if he == "ck" and ghi_chu_goc:
        luat = [x.strip() for x in ghi_chu_goc if x.strip().startswith("LUẬT NỀN") or "chỉ tính là MỘT" in x
                or x.strip().startswith("Không chắc")]
        khoi.append(canh_bao("Luật nền của sổ nguồn gốc (viết tay)", luat, "lam"))
    if out:
        khoi.append(bang(["Nguồn", "Nhóm", "Bậc", "Gốc · kênh", "Tần suất · độ trễ", "Trạng thái",
                          "Tài sản lớp B", "Ghi chú"], out,
                         chu_thich="Thang bậc: %s. Không trộn với thang của hệ còn lại." % thang))
    else:
        khoi.append(doan("Lớp A không có nguồn nào của hệ này (launchpad/songuon_registry.json).", mau="vang"))
    lede = "Lớp A — phán đoán về nguồn gốc, viết tay, chỉ đọc. Thang: %s." % thang
    if cap_nhat:
        lede += " Cập nhật %s." % nfc(cap_nhat)
    return sec(sid, so, tieu_de, khoi, eyebrow="lớp A · he=%s · %d nguồn" % (he, len(rows)), lede=lede)


def sec_phap_ly(a, hits, ng):
    pl = a.get("phap_ly") or {}
    khoi = [canh_bao("Luật cứng", [
        "Không bao giờ gọi dulieukinhte.com/api/internal/ (robots.txt Disallow; chủ hệ cấm từ 20/09/2026).",
        "Vietcap chỉ qua lk_lich / vc_lk_fetch: cách lệnh ≥10 s (Crawl-delay), khoá state/vc_lk/.lock; mã thoát 4 "
        "= đang chạy ở tiến trình khác.",
        "FETCH chạy từng bước một, không song song; producer ngoài bộ điều phối mà gọi Vietcap trực tiếp hoặc gửi "
        "Telegram bị bỏ qua. Lượt goi_nguon của FETCH là đúng lệnh launchd chạy mỗi 10' (không --chi): các job "
        "Vietcap/vnstock bên trong tự giữ DEN_HAN và khoảng cách của chúng."],
        "do")]
    rows = []
    for g in pl.get("gioi_han") or []:
        st = g.get("trang_thai")
        txt, m = PHAP_LY_TXT.get(st, ("LUẬT", "lam"))
        rows.append([cell(g.get("id"), mono=True), cell(txt, mau=m, pill=True), ng.text(g.get("text"))])
    if rows:
        khoi.append(heading("Giới hạn gọi & dòng pháp lý của sổ đăng ký"))
        khoi.append(bang(["Mục", "Trạng thái", "Ghi chú"], rows))
    khoi.append(heading("Mã gọi dulieukinhte.com/api/internal/"))
    if hits:
        hr = [[cell(ng.duong(h.get("tep")), mono=True), cell(str(h.get("dong")), mono=True),
               cell(h.get("text"), mono=True),
               cell("CÓ" if h.get("song") else "không (.bak)", mau="do" if h.get("song") else "xam", pill=True)]
              for h in hits]
        khoi.append(bang(["Tệp", "Dòng", "Đoạn mã", "Còn chạy"], hr, can_phai=[1],
                         chu_thich="Quét _System và fincept-qt/scripts, bỏ dòng chú thích và tệp test; bản .bak chỉ "
                                   "tính là còn chạy khi một LaunchAgent gọi đích danh nó. Kết quả lưu đệm 1 giờ."))
    else:
        khoi.append(doan("Không thấy mã nào gọi đường cấm trong _System và fincept-qt/scripts (bỏ dòng chú thích "
                         "và tệp test; kết quả quét lưu đệm 1 giờ).", mau="xanh"))
    return sec("phap_ly", "VIII", "Pháp lý & giới hạn gọi", khoi, eyebrow="robots.txt · Crawl-delay · nguồn cấm")


def csv_rows(a, ng):
    rows = []
    for ts in a.get("tai_san") or []:
        p = ts.get("producer") or {}
        pl = ts.get("phap_ly") or {}
        rows.append([ts.get("id"), nfc(ts.get("ten")), ts.get("nhom"), ts.get("loai"), ts.get("duong_dan") or "",
                     do_tuoi_txt(ts.get("do_tuoi")), ts.get("moc") or "",
                     finite(ts.get("tuoi_gio")) if finite(ts.get("tuoi_gio")) is not None else "",
                     finite(ts.get("nguong_gio")) if finite(ts.get("nguong_gio")) is not None else "",
                     ts.get("trang_thai"), nfc(p.get("ten")), p.get("kieu"), p.get("lich") or "",
                     nfc(ts.get("nhip")), "có" if (p.get("kieu") == "goi" or p.get("lam_moi_khi_fetch")) else "không",
                     ", ".join(ts.get("tieu_thu") or []), ts.get("bac") or "", ", ".join(ts.get("nguon_goc") or []),
                     pl.get("trang_thai") or "", nfc(pl.get("ghi_chu")), ng.text(ts.get("ghi_chu"))])
    return rows


def nguon_live(core, a, goc):
    P = core.duong()

    def tep(ten, path, as_of=None, ghi=""):
        ok = os.path.exists(path)
        if as_of is None and ok:
            as_of = datetime.fromtimestamp(os.path.getmtime(path), ICT).isoformat(timespec="seconds")
        return {"ten": ten, "duong_dan": str(path), "as_of": as_of, "ok": ok, "ghi_chu": ghi}

    return [tep("Sổ đăng ký tài sản (lớp B)", os.path.join(str(P["bridge"]), "so_nguon_dangky.py"),
                ghi="%d dòng" % len(a.get("tai_san") or [])),
            tep("Sổ nguồn gốc (lớp A, viết tay)", os.path.join(str(P["sys"]), "launchpad", "songuon_registry.json"),
                as_of=goc.get("cap_nhat"), ghi="chỉ đọc"),
            tep("Trạng thái bộ điều phối", os.path.join(str(P["data"]), "goi_nguon_status.json")),
            tep("Lịch LaunchAgent / Cowork", os.path.join(str(P["data"]), "lich_so.json")),
            tep("Tiến độ lượt làm mới", os.path.join(str(P["state"]), "so_nguon_run.json"))]


# ── Commands ─────────────────────────────────────────────────────────────────


def overview(core, lenh="overview", khoi_dong=None):
    now = datetime.now(ICT)
    ng = Ngan(core)
    a = core.audit()
    goc = a.get("goc") or {}
    hits = (a.get("phap_ly") or {}).get("hits") or []
    tt = core.trang_thai_lam_moi()
    run = run_gon(tt, now)
    # The plan of "what FETCH would do now" is shown whenever no run is going; it reuses this audit.
    kh_nay = None if run["dang_chay"] else core.ke_hoach_lam_moi(a=a)
    warnings = []
    if khoi_dong and khoi_dong.get("tu_choi"):
        warnings.append(nfc(khoi_dong.get("ghi_chu")) or "Đã có một lượt làm mới đang chạy — không mở lượt thứ hai.")
    if run.get("ghi_chu"):
        warnings.append(run["ghi_chu"])
    if run.get("dry") and run["dang_chay"]:
        warnings.append("Lượt làm mới đang chạy khô (SO_NGUON_DRY=1) — không producer nào chạy thật.")
    if int((a.get("tom_tat") or {}).get("loi_dang_ky") or 0):
        warnings.append("Sổ đăng ký tài sản có lỗi lược đồ — xem mục Vấn đề.")
    if not (goc.get("ck") or goc.get("beri")):
        warnings.append("Không đọc được sổ nguồn gốc lớp A (launchpad/songuon_registry.json).")
    src = nguon_live(core, a, goc)
    if not src[2]["ok"]:
        warnings.append("Chưa có data/goi_nguon_status.json — tài sản của bộ điều phối không đo được.")
    ghi_chu_goc = [nfc(x) for x in goc.get("ghi_chu") or [] if isinstance(x, str)]
    sections = [sec_tom_tat(a, hits, goc, now), sec_van_de(a, ng),
                sec_lam_moi(run, tt.get("ke_hoach"), kh_nay, ng, now), sec_tai_san(a, ng, now), sec_lich(a, now),
                sec_goc("ck", "VI", goc.get("ck") or [], ghi_chu_goc, goc.get("cap_nhat")),
                sec_goc("beri", "VII", goc.get("beri") or [], ghi_chu_goc, goc.get("cap_nhat")),
                sec_phap_ly(a, hits, ng)]
    return {"meta": {"generated": now.isoformat(timespec="seconds"), "script_version": SCRIPT_VERSION,
                     "lenh": lenh, "bridge": str(core.duong()["bridge"]), "cap_nhat": a.get("cap_nhat"),
                     "n_tai_san": len(a.get("tai_san") or []), "warnings": warnings, "sources_live": src},
            "trang": {"schema": "vnblocks/1", "tieu_de": "Sổ nguồn", "sections": sections},
            "csv": {"columns": CSV_COLUMNS, "rows": csv_rows(a, ng)},
            "run": run}


def lam_moi(core):
    try:
        bd = core.bat_dau_lam_moi()
    except Exception as exc:  # the runner could not be started: say so, keep the page request separate
        raise TabError("RUN_FAILED", "Không khởi động được lượt làm mới: %s: %s. Xem fincept_bridge/logs/"
                       "so_nguon_run.log hoặc chạy thử python3 so_nguon.py ke_hoach."
                       % (type(exc).__name__, exc)) from exc
    return overview(core, "lam_moi", bd)


def trang_thai(core):
    """Small and fast (polled every 3 s): the run file only — no audit, no registry, no scan."""
    now = datetime.now(ICT)
    tt = core.trang_thai_lam_moi()
    run = run_gon(tt, now)
    return {"meta": {"generated": now.isoformat(timespec="seconds"), "script_version": SCRIPT_VERSION,
                     "lenh": "trang_thai"},
            "run": run, "section": sec_lam_moi(run, tt.get("ke_hoach"), None, Ngan(core), now)}


LENH = {"overview": overview, "lam_moi": lam_moi, "trang_thai": trang_thai}


def run(argv):
    args = [a for a in argv[1:] if a.strip()]
    if len(args) != 1 or args[0] not in LENH:
        raise TabError("BAD_ARGS", "Lệnh không hợp lệ: %s. %s" % (" ".join(args) or "(trống)", USAGE))
    return LENH[args[0]](nap_core())


# ── Output ───────────────────────────────────────────────────────────────────


def clean(o):
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if o is None or isinstance(o, (str, int, bool)):
        return o
    return str(o)


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
    except TabError as exc:
        out = {"error": exc.message, "error_code": exc.code}
    except Exception as exc:  # never let a traceback replace the JSON envelope
        out = {"error": "Lỗi nội bộ so_nguon_tab.py: %s: %s" % (type(exc).__name__, exc), "error_code": "INTERNAL"}
    emit(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
