#!/usr/bin/env python3
"""
Fincept Terminal — BERI data service (Hội đồng Cố vấn AI, Viện Nghiên cứu Kinh tế BIDV).

Feeds src/screens/beri/BeriPanel through EconomicsService / PythonRunner. Stdlib only; runs on
Python 3.9+. Makes NO network calls. Reads local files only, never writes.

The module is the living version of the artifact "BERI · Advisory Council v2.0" (9/8/2026). The
artifact froze its calendar and its ledger on the day it was drawn; this script re-reads the files
the Viện keeps current and recomputes every countdown against today.

Sources (read-only; env overrides are used by the tests):
    BERI_WORKSPACE_SKILL  ~/.claude/skills/beri-workspace/SKILL.md
                            §1 vai · §6 lịch sản phẩm (Phụ lục BC 14/9) · §6b cam kết · §6c mốc neo ·
                            §7 Sổ lệch vận hành · §8 việc đang mở
    BERI_SECTOR_DIR       ~/SECOND BRAIN-OBSIDIAN/_System/beri_sector
                            the 8 core files · output/sector_feed.json (ONLY generated_at, n_news,
                            n_policy are read) · output/ra_soat_<date>.json (counts + one-line tasks)
    BERI_COPY_DIRS        ~/Downloads:~/Downloads/BERI_Cowork/01_He_thong:~/Downloads/BERI_Cowork/03_Kho_du_lieu
                            other copies of the 8 core files, compared by md5 only
    BERI_SONGUON          ~/SECOND BRAIN-OBSIDIAN/_System/launchpad/songuon_registry.json  (rows he == "beri")
    BERI_PRODUCT_DIR      ~/Downloads   (top level only: file NAMES of recent .docx/.pdf, never contents)
    BERI_TODAY            test hook only: fixes "today" (YYYY-MM-DD)

Never read (internal BIDV credit data, or keys the BERI terminal forbids): data/nganh_42.json,
data/sector_map.json, BERI_DuNoNganh*, BERI_AnhXaNganh*, config.env, and the sector_feed keys
sector_moves / overlay / ung_vien_flashnote / catalog / sellside_signals / top_news.

USAGE
    python3 beri.py overview

OUTPUT — exactly ONE compact JSON object on stdout (UTF-8, ensure_ascii=False). Exit code 0 even
on errors. Display strings are Vietnamese, markdown stripped. A missing source is not fatal: its
section carries "[CẦN DATA]" and meta.warnings says what is missing.

Top-level error (replaces the payload): {"error": str, "error_code": "BAD_ARGS" | "INTERNAL"}

overview →
{
 "meta": {"generated", "today", "script_version", "warnings": [str], "local_only": str,
          "sources": [{"ten", "duong_dan", "ton_tai", "sua_luc", "tuoi_ngay"}]},
 "mandate": {"ten", "vai", "hieu_luc", "van_ban": [str], "nguon"},
 "alert": {"muc": "crit"|"warn"|"ok"|"na", "tieu_de", "noi_dung"},
 "lich": {"nguon", "ghi_chu", "nhom": [{"ten", "dong": [ROW]}], "dem": {"crit","warn","ok","na"}},
     ROW = {"san_pham", "han_goc", "don_vi", "moc_tiep": ISO|null, "moc_tiep_txt", "con_ngay": int|null,
            "con_txt", "muc", "kieu": "thang"|"nam"|"su_kien"|"khong_tinh", "ky_vua_qua": {"moc_txt","qua_ngay"}|null,
            "co": [str], "tien_do": {"tep", "ngay_txt", "giai_doan"}|null}
 "cam_ket": {"nguon", "dong": [{"so", "viec", "moc", "trang_thai"}], "chua_moc": int},
 "moc_neo": {"nguon", "dong": [{"van_ban", "noi_dung", "san_pham", "thieu_ngay": bool}], "thieu_ngay": int},
 "so_lech": {"so_lieu": {"nguon", "dong": [LED], "mo": int, "dong_lai": int},
             "van_hanh": {"nguon", "da_chot": [LED], "dang_mo": [LED]}},
     LED = {"so", "van_de", "a", "b", "xu_ly", "trang_thai", "mo": bool, "trung_voi": str}
 "viec_mo": {"nguon", "nhom": [{"ten", "dong": [str]}]},
 "so_nguon": {"nguon", "cap_nhat", "tuoi_ngay", "dem": {status: n}, "dong": [{"id","ten","nhom","tier",
              "trang_thai","trang_thai_txt","tan_suat","ghi_chu"}]},
 "kho": {"tep": [{"ten", "vai_tro", "sua_luc", "tuoi_ngay", "ban_sao": int, "khop": bool, "lech": [str]}],
         "so_lieu": {"cap_nhat_txt", "ky", "canh_bao"}},
 "pipeline": {"quet": {"moi_nhat_txt", "cach_gio", "so_luot", "n_tin", "n_chinh_sach", "muc"},
              "ra_soat": {"ngay_txt", "tong", "nghiem_trong", "nhom": {nhom: n}, "viec": [str]}},
 "hien_chuong": {"nguon", "bac": [{"tag", "nghia", "vi_du"}], "quy_tac_t4", "khong": [str]},
 "tang_e": {"nguon", "khoi": [{"ten", "ghe": [{"id","ten","vai_tro","nguyen_mau","mandate","san_pham","cau_hoi":[str]}]}]},
 "bo_may": {"nguon", "tang": [{"id", "ten", "vai_tro", "ghe": [{"id","ten","vai_tro","mo_ta","quyen"}]}]},
 "quy_trinh": {"nguon", "buoc": [{"so", "ten", "mo_ta"}], "nguyen_tac"},
 "ket_luan": {"nguon", "dong": [{"ma", "ten", "nghia", "xu_ly"}]},
 "gia_tri": {"nguon", "dong": [{"so", "ten", "nhan", "mo_ta"}]},
 "csv": {"columns": [str], "rows": [[str]]}
}
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import os
import re
import sys

SCRIPT_VERSION = "1.0"
CAN_DATA = "[CẦN DATA]"
VN_TZ = _dt.timezone(_dt.timedelta(hours=7))

HOME = os.path.expanduser("~")
SYS_DIR = os.path.join(HOME, "SECOND BRAIN-OBSIDIAN", "_System")

CORE_FILES = [
    ("BERI_KhoSoLieuChuan_2026H1.md", "Nguồn trích dẫn duy nhất cho số 6T–7T/2026 · Sổ lệch số liệu"),
    ("BERI_HoiDongCoVanAI_Charter.md", "Hiến chương dữ liệu · 12 ghế · quy trình 7 bước"),
    ("BERI_HoiDongChuyenGia_18Ghe.md", "Tầng E — 18 ghế chuyên gia"),
    ("BERI_ChuanNha_TichHopDuLieu.md", "Chuẩn nhà: văn phong, trình bày"),
    ("BERI_BIDV_TaiChinh_Q2-2026.md", "Atlas tài chính BIDV Q2/2026"),
    ("BERI_NguonDuLieu_Registry.md", "106 nguồn / 13 nhóm — tìm nguồn"),
    ("BERI_KhoDuLieu_DoiTac_DoanhThu.md", "Đối tác · 4 dòng giá trị · 4 nút thắt"),
    ("BERI_MauBaoCao_Checklist.md", "4 mẫu báo cáo · checklist 6 bước Điều 9"),
]

# Files this module must never open, whatever directory they turn up in.
FORBIDDEN_NAMES = ("nganh_42.json", "sector_map.json", "config.env")
FORBIDDEN_PREFIXES = ("BERI_DuNoNganh", "BERI_AnhXaNganh", "draft_bantin_")
FEED_KEYS_ALLOWED = ("generated_at", "n_news", "n_policy")

STATUS_TXT = {
    "song": "sống",
    "thu_cong": "thủ công",
    "chua_co": "chưa có",
    "chap_chon": "chập chờn",
    "chan": "bị chặn",
}

# Same issue, two ledgers, two numbering schemes (Kho §G vs beri-workspace §7). The pair is listed
# explicitly — a phrase from each side — so a cross-reference is only ever printed when BOTH phrases
# are found in the live files; nothing is inferred.
LEDGER_LINKS = [
    ("Dự báo tăng trưởng Việt Nam 2026", "Tăng trưởng 2026"),
    ("7/8 chỉ tiêu rủi ro", "7/8 chỉ tiêu rủi ro"),
    ("Thương mại CN nhẹ", "Thương mại CN nhẹ"),
]

# Product row → file-name pattern for "latest working file" (names only, top level of the product
# dir). Conservative on purpose: a miss shows nothing, a hit shows the file name so the reader judges.
_S = r"[ _.+-]?"  # separator inside a file name: none, space, _, ., +, -
PRODUCT_FILES = [  # most specific first — a file is claimed by the first product whose pattern hits
    (r"lớp tài sản", r"lop" + _S + r"tai" + _S + r"san"),
    (r"xu hướng rủi ro", r"xu" + _S + r"huong" + _S + r"rui" + _S + r"ro|TTTC" + _S + r"RuiRo"),
    (r"Dashboard thị trường tài chính", r"Dashboard" + _S + r"(TTTC|thi" + _S + r"truong" + _S + r"tai" + _S + r"chinh)"),
    (r"dự báo lãi suất", r"du" + _S + r"bao" + _S + r"lai" + _S + r"suat|LaiSuat" + _S + r"LNH"),
    (r"thị trường BĐS", r"TTBDS|TinDung" + _S + r"BDS|ThiTruong" + _S + r"BDS"),
    (r"4 nước ASEAN", r"ASEAN"),
    (r"tiêu dùng tài chính", r"tieu" + _S + r"dung" + _S + r"tai" + _S + r"chinh"),
    (r"năng lực cạnh tranh", r"nang" + _S + r"luc" + _S + r"canh" + _S + r"tranh|NLCT"),
    (r"CAMELS", r"CAMELS|Nganh" + _S + r"NH(?![a-z])"),
    (r"triển vọng các ngành", r"trien" + _S + r"vong" + _S + r"nganh"),
    (r"Kế hoạch công tác", r"ke" + _S + r"hoach" + _S + r"cong" + _S + r"tac"),
    (r"kinh tế vĩ mô Việt Nam", r"KTVM|kinh" + _S + r"te" + _S + r"vi" + _S + r"mo"),
]
# Viện publications that are not calendar rows but still feed Kho numbers.
PUBLICATION_FILES = r"BanTin" + _S + r"KinhTe" + _S + r"Nganh|Bản tin Kinh tế ngành"
PRODUCT_EXCLUDE = re.compile(
    r"^~\$|\(\d\)|__1\.|HSC|SSI|VCSC|Vietcap|BSC|MBS|KBSV|VNDirect|VDS|ACBS|FPTS|Mirae|Yuanta|Rong ?Viet"
    r"|chu[ _]de[ _]dau[ _]tu",  # broker thematic reports use this phrase; the Viện does not
    re.I)
PRODUCT_MAX_AGE_DAYS = 60


# ── small utilities ──────────────────────────────────────────────────────────

def env_path(name: str, default: str) -> str:
    v = os.environ.get(name, "").strip()
    return os.path.expanduser(v) if v else default


def today() -> _dt.date:
    v = os.environ.get("BERI_TODAY", "").strip()
    if v:
        try:
            return _dt.date.fromisoformat(v)
        except ValueError:
            pass
    return _dt.datetime.now(VN_TZ).date()


def now_vn() -> _dt.datetime:
    v = os.environ.get("BERI_TODAY", "").strip()
    if v:
        try:
            d = _dt.date.fromisoformat(v)
            return _dt.datetime(d.year, d.month, d.day, 12, 0, tzinfo=VN_TZ)
        except ValueError:
            pass
    return _dt.datetime.now(VN_TZ)


def ddmm(d: _dt.date) -> str:
    return d.strftime("%d/%m/%Y")


def forbidden(path: str) -> bool:
    b = os.path.basename(path)
    return b in FORBIDDEN_NAMES or b.startswith(FORBIDDEN_PREFIXES)


def read_text(path: str):
    if forbidden(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def file_info(path: str, ref: _dt.date) -> dict:
    info = {"duong_dan": path.replace(HOME, "~"), "ton_tai": False, "sua_luc": CAN_DATA, "tuoi_ngay": None}
    try:
        st = os.stat(path)
    except OSError:
        return info
    m = _dt.datetime.fromtimestamp(st.st_mtime, VN_TZ)
    info.update(ton_tai=True, sua_luc=m.strftime("%d/%m/%Y %H:%M"), tuoi_ngay=(ref - m.date()).days)
    return info


def md5_6(path: str):
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:6]
    except OSError:
        return None


_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def plain(s: str) -> str:
    """Markdown cell → display text: drop emphasis/code markers and link targets, collapse space."""
    s = _MD_LINK.sub(r"\1", s or "")
    s = s.replace("**", "").replace("`", "")
    s = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"\1", s)  # *italic*
    s = re.sub(r"(?<!\w)_(?!\s)([^_\n]+?)(?<!\s)_(?!\w)", r"\1", s)          # _italic_
    return re.sub(r"\s+", " ", s).strip()


def section(text: str, heading_re: str, level: int):
    """Body under the first heading of `level` (#-count) matching heading_re, up to the next
    heading of the same or a higher level. None when the heading is absent."""
    if not text:
        return None
    pat = re.compile(r"^(#{1,6})\s+(.*)$", re.M)
    start = None
    for m in pat.finditer(text):
        n = len(m.group(1))
        if start is None:
            if n == level and re.search(heading_re, m.group(2)):
                start = m.end()
        elif n <= level:
            return text[start:m.start()]
    return text[start:] if start is not None else None


def tables(text: str):
    """Every pipe table in `text` → list of (header cells, [row cells]). Separator rows dropped."""
    out, cur = [], []
    for line in (text or "").splitlines() + [""]:
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cur.append([c.strip() for c in s[1:-1].split("|")])
            continue
        if cur:
            rows = [r for r in cur if not all(re.fullmatch(r":?-{2,}:?", c or "-") for c in r)]
            if rows:
                out.append((rows[0], rows[1:]))
            cur = []
    return out


def cell(row, i):
    return row[i] if i < len(row) else ""


# ── calendar rule engine ─────────────────────────────────────────────────────

_EVENT_WORDS = ("sau sự kiện", "phát sinh", "theo kết quả", "tối đa", "liên tục", "theo chỉ đạo")


def last_day(y: int, m: int) -> int:
    nxt = _dt.date(y + (m // 12), m % 12 + 1, 1)
    return (nxt - _dt.timedelta(days=1)).day


def _safe(y, m, d):
    return _dt.date(y, m, min(d, last_day(y, m)))


def candidates(han: str, ref: _dt.date):
    """Due dates the text describes, for the year before, of and after `ref`.

    Returns (kind, [dates]). kind: "thang" monthly, "nam" yearly/explicit, "su_kien" event-driven,
    "khong_tinh" unparseable. Order of the patterns matters: "ngày 10 tháng 1/4/7/10" must be read as
    months before the bare "d/m" scan, which would otherwise take "1/4" and "7/10" as dates."""
    t = plain(han).lower()
    years = (ref.year - 1, ref.year, ref.year + 1)
    # 1) day-of-month + explicit month list: "trước ngày 10 tháng 1/4/7/10"
    m = re.search(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2}(?:\s*/\s*\d{1,2})+)", t)
    if m:
        d = int(m.group(1))
        months = [int(x) for x in re.split(r"\s*/\s*", m.group(2))]
        return "nam", [_safe(y, mo, d) for y in years for mo in months if 1 <= mo <= 12]
    # 2) monthly: "ngày 6 hằng tháng"
    m = re.search(r"ngày\s+(\d{1,2})\s+hằng\s+tháng", t)
    if m:
        d = int(m.group(1))
        out = []
        for y in years:
            for mo in range(1, 13):
                out.append(_safe(y, mo, d))
        return "thang", out
    # 3) month windows: "trong tháng 5 và tháng 10" → month end
    m = re.search(r"trong\s+tháng\s+(\d{1,2})(?:\s+và\s+tháng\s+(\d{1,2}))?", t)
    if m:
        months = [int(x) for x in m.groups() if x]
        return "nam", [_safe(y, mo, 31) for y in years for mo in months]
    # 4) "tháng 9 hằng năm" / "tháng 10 năm trước" → month end, yearly
    m = re.search(r"tháng\s+(\d{1,2})\s+(?:hằng\s+năm|năm\s+trước|hàng\s+năm)", t)
    if m:
        mo = int(m.group(1))
        return "nam", [_safe(y, mo, 31) for y in years]
    # 5) explicit d/m list: "31/1 · 30/4 · 31/7 · 31/10"
    pairs = re.findall(r"(?<![\d/])(\d{1,2})\s*/\s*(\d{1,2})(?![\d/])", t)
    dates = []
    for d, mo in pairs:
        d, mo = int(d), int(mo)
        if 1 <= mo <= 12 and 1 <= d <= 31:
            dates += [_safe(y, mo, d) for y in years]
    if dates:
        return "nam", dates
    if any(w in t for w in _EVENT_WORDS):
        return "su_kien", []
    return "khong_tinh", []


def countdown(han: str, ref: _dt.date) -> dict:
    kind, cands = candidates(han, ref)
    cands = sorted(set(cands))
    nxt = next((d for d in cands if d >= ref), None)
    prev = next((d for d in reversed(cands) if d < ref), None)
    row = {"kieu": kind, "moc_tiep": None, "moc_tiep_txt": "—", "con_ngay": None, "con_txt": "—",
           "muc": "na", "ky_vua_qua": None}
    if kind == "su_kien":
        row["moc_tiep_txt"] = "theo sự kiện"
        return row
    if kind == "khong_tinh" or nxt is None:
        row["moc_tiep_txt"] = "không tính được mốc"
        return row
    n = (nxt - ref).days
    row.update(moc_tiep=nxt.isoformat(), moc_tiep_txt=ddmm(nxt), con_ngay=n,
               con_txt="hôm nay" if n == 0 else f"{n} ngày",
               muc="crit" if n <= 7 else "warn" if n <= 21 else "ok")
    # A period that just closed is shown but never judged: the module cannot know whether it was issued.
    if prev is not None and (ref - prev).days <= 21:
        row["ky_vua_qua"] = {"moc_txt": ddmm(prev), "qua_ngay": (ref - prev).days}
    return row


# ── product working files (names only) ───────────────────────────────────────

def name_date(name: str):
    """Date written into a file name (2026.07.15_… or 21092026_…), else None. Copying a file resets its
    mtime, so the name is the better witness of when the document was made."""
    m = re.match(r"(20\d\d)[._-](\d\d)[._-](\d\d)", name)
    if m:
        y, mo, d = (int(x) for x in m.groups())
    else:
        m = re.match(r"(\d\d)(\d\d)(20\d\d)[_ ]", name)
        if not m:
            return None
        d, mo, y = (int(x) for x in m.groups())
    try:
        return _dt.datetime(y, mo, d, 0, 0, tzinfo=VN_TZ)
    except ValueError:
        return None


def product_files(product_dir: str, ref: _dt.date):
    """Recent .docx/.pdf names at the top level of product_dir → {product key: [(name, when)]}.
    Only files that match a Viện product pattern are kept; everything else is never looked at again."""
    try:
        names = os.listdir(product_dir)
    except OSError:
        return {}
    out = {}
    for n in names:
        if not n.lower().endswith((".docx", ".pdf")) or PRODUCT_EXCLUDE.search(n) or forbidden(n):
            continue
        key = next((k for k, pat in PRODUCT_FILES if re.search(pat, n, re.I)), None)
        if key is None and re.search(PUBLICATION_FILES, n, re.I):
            key = "_ban_tin"
        if key is None:
            continue
        p = os.path.join(product_dir, n)
        try:
            mt = _dt.datetime.fromtimestamp(os.stat(p).st_mtime, VN_TZ)
        except OSError:
            continue
        nd = name_date(n)
        when = min(mt, nd) if nd else mt
        if (ref - when.date()).days > PRODUCT_MAX_AGE_DAYS:
            continue
        out.setdefault(key, []).append((n, when))
    return out


def stage_of(name: str) -> str:
    u = name.upper()
    if "FINAL" in u:
        return "FINAL"
    if "TRACKCHANGE" in u.replace("_", "").replace(" ", ""):
        return "bản track-change"
    m = re.findall(r"[_ -]V(\d+)(?![\d])", name, re.I)
    if m:
        return f"V{max(int(x) for x in m)}"
    return "bản làm việc"


def match_progress(san_pham: str, files):
    key = next((k for k, _ in PRODUCT_FILES if re.search(k, san_pham, re.I)), None)
    hits = files.get(key) if key else None
    if not hits:
        return None
    n, when = max(hits, key=latest_key)
    return {"tep": n, "ngay_txt": when.strftime("%d/%m"), "giai_doan": stage_of(n)}


def latest_key(hit):
    """Same day → the later draft (V5 > V4, FINAL above all) wins, whatever order the files were copied."""
    name, when = hit
    return (when.date(), n_stage_rank(name), when)


def n_stage_rank(name: str) -> int:
    st = stage_of(name)
    if st == "FINAL":
        return 1000
    m = re.match(r"V(\d+)$", st)
    return int(m.group(1)) if m else 0


# ── beri-workspace parsers ───────────────────────────────────────────────────

def parse_calendar(ws: str, ref: _dt.date, files):
    sec = section(ws, r"LỊCH SẢN PHẨM", 2)
    if sec is None:
        return None
    head = sec.strip().splitlines()[0] if sec.strip() else ""
    groups = []
    for m in re.finditer(r"^###\s+(.+)$", sec, re.M):
        name = plain(m.group(1))
        body = section(sec, re.escape(m.group(1).strip()), 3) or ""
        for hdr, rows in tables(body)[:1]:
            h = [plain(x).lower() for x in hdr]
            i_sp = 0
            i_han = next((i for i, x in enumerate(h) if x.startswith("hạn")), 1)
            i_dv = next((i for i, x in enumerate(h) if "thụ hưởng" in x or "ghi chú" in x), None)
            dong = []
            for r in rows:
                sp, han = plain(cell(r, i_sp)), cell(r, i_han)
                row = {"san_pham": sp, "han_goc": plain(han),
                       "don_vi": plain(cell(r, i_dv)) if i_dv is not None else ""}
                row.update(countdown(han, ref))
                flags = []
                if "⚠" in han:
                    ref_m = re.search(r"§\s*7\s*mục\s*(\d+)", plain(han))
                    flags.append("nghi lỗi lịch — xem Sổ lệch vận hành mục " + ref_m.group(1)
                                 if ref_m else "có cảnh báo trong nguồn")
                row["co"] = flags
                row["tien_do"] = match_progress(sp, files)
                dong.append(row)
            groups.append({"ten": name, "dong": dong})
    return {"nguon": "beri-workspace §6 — " + plain(head.lstrip("#")) if head else "beri-workspace §6",
            "nhom": groups}


def parse_commitments(ws: str):
    sec = section(ws, r"CAM KẾT MỚI", 2)
    if sec is None:
        return None
    t = tables(sec)
    if not t:
        return None
    _, rows = t[0]
    dong = [{"so": plain(cell(r, 0)), "viec": plain(cell(r, 1)), "moc": plain(cell(r, 2)),
             "trang_thai": plain(cell(r, 3))} for r in rows]
    return {"nguon": "beri-workspace §6b — hiệu lực khi TGĐ phê duyệt BC 14/9; chưa duyệt vẫn là đề xuất",
            "dong": dong, "chua_moc": sum(1 for d in dong if d["moc"].lower().startswith("chưa"))}


def parse_anchors(ws: str):
    sec = section(ws, r"MỐC NEO VĂN BẢN", 2)
    if sec is None:
        return None
    t = tables(sec)
    if not t:
        return None
    _, rows = t[0]
    dong = []
    for r in rows:
        vb = plain(cell(r, 0))
        has_date = bool(re.search(r"ngày\s+\d{1,2}/\d{1,2}/\d{4}", vb))
        sp = plain(cell(r, 2))
        # A product-anchoring QĐ without its date is what §8.4 asks to look up; QĐ 1080 (the
        # appointment) anchors no product, so it is listed but not counted.
        dong.append({"van_ban": vb, "noi_dung": plain(cell(r, 1)), "san_pham": sp,
                     "thieu_ngay": vb.startswith("QĐ") and not has_date and sp not in ("", "—", "-")})
    return {"nguon": "beri-workspace §6c — trích BC 14/9",
            "dong": dong, "thieu_ngay": sum(1 for d in dong if d["thieu_ngay"])}


def _ledger_rows(rows, hdr, closed_default: bool):
    h = [plain(x).lower() for x in hdr]
    idx = lambda *keys: next((i for i, x in enumerate(h) if any(k in x for k in keys)), None)
    i_so, i_vd = 0, idx("vấn đề", "nội dung")
    i_a, i_b = idx("bên a", "nguồn a"), idx("bên b", "nguồn b")
    i_xl, i_tt = idx("xử lý", "kết luận", "đề xuất"), idx("trạng thái")
    out = []
    for r in rows:
        tt = plain(cell(r, i_tt)) if i_tt is not None else ("ĐÃ CHỐT" if closed_default else "MỞ")
        xl = plain(cell(r, i_xl)) if i_xl is not None else ""
        # "ĐÃ GIẢI THÍCH" (Kho §G): the gap is explained, not an error — resolved, though not "closed".
        closed = closed_default or bool(re.search(r"ĐÃ ĐÓNG|ĐÃ CHỐT|CHỐT:|ĐÃ GIẢI THÍCH", tt + " " + xl))
        out.append({"so": plain(cell(r, i_so)), "van_de": plain(cell(r, i_vd)) if i_vd is not None else "",
                    "a": plain(cell(r, i_a)) if i_a is not None else "",
                    "b": plain(cell(r, i_b)) if i_b is not None else "",
                    "xu_ly": xl, "trang_thai": tt or ("ĐÃ CHỐT" if closed else "MỞ"),
                    "mo": not closed, "trung_voi": ""})
    return out


def parse_ops_ledger(ws: str):
    sec = section(ws, r"SỔ LỆCH", 2)
    if sec is None:
        return None
    closed = section(sec, r"ĐÃ CHỐT", 3) or ""
    opened = section(sec, r"ĐANG MỞ", 3) or ""
    tc, to = tables(closed), tables(opened)
    return {"nguon": "Sổ lệch vận hành — beri-workspace §7 (cập nhật theo BC 14/9)",
            "da_chot": _ledger_rows(tc[0][1], tc[0][0], True) if tc else [],
            "dang_mo": _ledger_rows(to[0][1], to[0][0], False) if to else []}


def parse_open_work(ws: str):
    sec = section(ws, r"VIỆC ĐANG MỞ", 2)
    if sec is None:
        return None
    head = plain(re.sub(r"^#+", "", sec.strip().splitlines()[0])) if sec.strip() else ""
    groups = []
    for m in re.finditer(r"^###\s+(.+)$", sec, re.M):
        body = section(sec, re.escape(m.group(1).strip()), 3) or ""
        items, cur = [], None
        for line in body.splitlines():
            s = line.rstrip()
            if re.match(r"^\s*-\s+", s):
                if cur:
                    items.append(cur)
                cur = plain(re.sub(r"^\s*-\s+", "", s))
            elif cur is not None and s.strip() and not s.lstrip().startswith("#"):
                cur += " " + plain(s)
        if cur:
            items.append(cur)
        items = [re.sub(r"\s*-{3,}\s*$", "", x) for x in items]
        ten = plain(m.group(1))
        if re.search(r"định biên|nhân sự", ten, re.I):
            # Staffing file (candidates, interviews): count only, never the content, on a terminal screen.
            items = [f"{len(items)} việc — hồ sơ nhân sự, chỉ xem trong beri-workspace §8, không hiện trên terminal"]
        groups.append({"ten": ten, "dong": items})
    return {"nguon": "beri-workspace §8" + (" — " + head if head else ""), "nhom": groups}


def parse_mandate(ws: str):
    sec = section(ws, r"VAI VÀ THẨM QUYỀN", 2) or ""
    m = re.search(r"\*\*([^*]+)\*\*\s*—\s*([^\n]+)\n([^\n]*)", sec)
    ten = plain(m.group(1)) if m else CAN_DATA
    vai = plain(m.group(2) + " " + m.group(3)) if m else CAN_DATA
    hl = re.search(r"bổ nhiệm\s+(\d{1,2}/\d{1,2}/\d{4})", vai)
    docs = []
    for pat in (r"QĐ\s*1080/QĐ-BIDV", r"QC\s*1128/QĐ-BIDV ngày \d{1,2}/\d{1,2}/\d{4}"):
        mm = re.search(pat, sec)
        if mm:
            docs.append(plain(mm.group(0)))
    return {"ten": ten, "vai": vai, "hieu_luc": hl.group(1) if hl else CAN_DATA, "van_ban": docs,
            "nguon": "beri-workspace §1"}


# ── Kho §G + other core files ────────────────────────────────────────────────

def parse_data_ledger(kho: str):
    sec = section(kho, r"SỔ LỆCH SỐ LIỆU", 2)
    if sec is None:
        return None
    t = tables(sec)
    if not t:
        return None
    rows = _ledger_rows(t[0][1], t[0][0], False)
    return {"nguon": "Sổ lệch số liệu — BERI_KhoSoLieuChuan_2026H1.md §G", "dong": rows,
            "mo": sum(1 for r in rows if r["mo"]),
            "giai_thich": sum(1 for r in rows if "GIẢI THÍCH" in r["trang_thai"]),
            "dong_lai": sum(1 for r in rows if not r["mo"] and "GIẢI THÍCH" not in r["trang_thai"])}


def link_ledgers(data_led, ops_led):
    if not data_led or not ops_led:
        return
    ops_all = ops_led["dang_mo"] + ops_led["da_chot"]
    for a_phrase, b_phrase in LEDGER_LINKS:
        a = next((r for r in data_led["dong"] if a_phrase in r["van_de"]), None)
        b = next((r for r in ops_all if b_phrase in r["van_de"]), None)
        if a and b:
            a["trung_voi"] = f"trùng Sổ lệch vận hành mục {b['so']}"
            b["trung_voi"] = f"trùng Sổ lệch số liệu mục {a['so']}"


def parse_kho_meta(kho: str):
    if not kho:
        return {"cap_nhat_txt": CAN_DATA, "ky": CAN_DATA, "canh_bao": ""}
    m = re.search(r"Đã cập nhật\s+(\d{1,2}/\d{1,2}/\d{4})", kho)
    k = re.search(r"^#\s+.*?·\s*([^\n]+)$", kho, re.M)
    has_7t = bool(re.search(r"CẬP NHẬT 7T/2026", kho))
    ky = (plain(k.group(1)) if k else CAN_DATA) + (" (có mục cập nhật 7T/2026)" if has_7t else "")
    return {"cap_nhat_txt": m.group(1) if m else CAN_DATA, "ky": ky, "canh_bao": ""}


def parse_tiers(charter: str):
    sec = section(charter, r"Bậc bằng chứng", 3)
    bac = []
    for hdr, rows in tables(sec or "")[:1]:
        for r in rows:
            bac.append({"tag": plain(cell(r, 0)), "nghia": plain(cell(r, 1)), "vi_du": plain(cell(r, 2))})
    t4 = ""
    if sec:
        m = re.search(r"\*\*Quy tắc T4:\*\*([^\n]+)", sec)
        t4 = plain(m.group(1)) if m else ""
    khong = []
    no = section(charter, r"Sáu điều KHÔNG", 3) or ""
    for line in no.splitlines():
        s = line.strip()
        if re.match(r"^(\d+\.|-)\s+", s):
            khong.append(plain(re.sub(r"^(\d+\.|-)\s+", "", s)))
    return {"nguon": "BERI_HoiDongCoVanAI_Charter.md §1.1–1.2", "bac": bac, "quy_tac_t4": t4, "khong": khong}


def parse_expert_seats(text: str):
    part = section(text, r"MƯỜI TÁM GHẾ", 2)
    if part is None:
        return None
    khoi = []
    for m in re.finditer(r"^###\s+(KHỐI[^\n]+)$", part, re.M):
        body = section(part, re.escape(m.group(1).strip()), 3) or ""
        ghe = []
        for s in re.finditer(r"^####\s+(E\d+)\s*·\s*(.+)$", body, re.M):
            sb = section(body, re.escape(s.group(0)[5:].strip()), 4) or ""
            title = s.group(2)
            role = ""
            rm = re.search(r"—\s*\*([^*]+)\*\s*$", title)
            if rm:
                role, title = plain(rm.group(1)), title[:rm.start()]
            name = plain(re.sub(r"^GHẾ\s+", "", plain(title)))

            def field(label):
                fm = re.search(r"\*\*" + label + r":\*\*\s*([^\n]+)", sb)
                return plain(fm.group(1)) if fm else ""

            qs = []
            qm = re.search(r"\*\*Câu hỏi lõi:\*\*\s*\n((?:\s*-\s+[^\n]+\n?)+)", sb)
            if qm:
                qs = [plain(re.sub(r"^\s*-\s+", "", q)) for q in qm.group(1).strip().splitlines()]
            ghe.append({"id": s.group(1), "ten": name, "vai_tro": role,
                        "nguyen_mau": field("Nguyên mẫu"), "mandate": field("Mandate"),
                        "san_pham": field("Sản phẩm"), "cau_hoi": qs})
        khoi.append({"ten": plain(m.group(1)), "ghe": ghe})
    pm = re.search(r"Nguyên tắc thiết kế:\s*([^\n]+)", text)
    return {"nguon": "BERI_HoiDongChuyenGia_18Ghe.md", "nguyen_tac": plain(pm.group(1)) if pm else "",
            "khoi": khoi}


def parse_operating_seats(charter: str):
    part = section(charter, r"CƠ CẤU HỘI ĐỒNG", 2)
    if part is None:
        return None
    tang = []
    for m in re.finditer(r"^###\s+(TẦNG\s+([A-D])[^\n]*)$", part, re.M):
        body = section(part, re.escape(m.group(1).strip()), 3) or ""
        head = m.group(1)
        rm = re.search(r"\*\(([^)]+)\)\*", head)
        ten = plain(re.sub(r"\*\([^)]*\)\*", "", head))
        ghe = []
        blocks = re.split(r"^(?=\*\*[A-D]\d\s*·)", body, flags=re.M)
        for b in blocks:
            # Role comes either as "— *Red Team*" (tầng A) or as "*(nhóm NC KTVM — 5 cán bộ)*" (tầng B–D).
            sm = re.match(r"\*\*([A-D]\d)\s*·\s*([^*]+)\*\*\s*(?:[—-]\s*\*([^*]+)\*|\*\(([^)]+)\)\*)?[^\n]*\n?", b)
            if not sm:
                continue
            rest = b[sm.end():]
            lines = [l.strip() for l in rest.splitlines() if l.strip()]
            desc = plain(lines[0]) if lines and not lines[0].startswith(("-", "**Quyền")) else ""
            qm = re.search(r"\*\*Quyền:\*\*\s*([^\n]+)", rest)
            qs = [plain(l[1:]) for l in lines if l.startswith("- ")]
            ghe.append({"id": sm.group(1), "ten": plain(re.sub(r"^GHẾ\s+", "", sm.group(2).strip())),
                        "vai_tro": plain(sm.group(3) or sm.group(4) or ""), "mo_ta": desc,
                        "quyen": plain(qm.group(1)) if qm else "", "cau_hoi": qs})
        tang.append({"id": m.group(2), "ten": ten, "vai_tro": plain(rm.group(1)) if rm else "", "ghe": ghe})
    return {"nguon": "BERI_HoiDongCoVanAI_Charter.md §2 — mười hai ghế vận hành", "tang": tang}


def parse_process(charter: str):
    sec = section(charter, r"QUY TRÌNH 7 BƯỚC", 2)
    if sec is None:
        return None
    buoc = []
    for m in re.finditer(r"^B(\d)\.\s*([^→\n]+?)\s*→\s*([^\n]+)$", sec, re.M):
        ten = plain(m.group(2))
        buoc.append({"so": int(m.group(1)), "ten": ten[:1].upper() + ten[1:].lower(), "mo_ta": plain(m.group(3))})
    nt = re.search(r"\*\*Nguyên tắc thứ tự:\*\*\s*([^\n]+)", sec)
    return {"nguon": "BERI_HoiDongCoVanAI_Charter.md §3", "buoc": buoc,
            "nguyen_tac": plain(nt.group(1)) if nt else ""}


def parse_conclusions(charter: str):
    sec = section(charter, r"BỐN TRẠNG THÁI KẾT LUẬN", 2)
    t = tables(sec or "")
    if not t:
        return None
    dong = []
    for r in t[0][1]:
        full = plain(cell(r, 0))
        mm = re.match(r"([A-D])\s*[—-]\s*(.+)", full)
        dong.append({"ma": mm.group(1) if mm else full[:1], "ten": mm.group(2) if mm else full,
                     "nghia": plain(cell(r, 1)), "xu_ly": plain(cell(r, 2))})
    return {"nguon": "BERI_HoiDongCoVanAI_Charter.md §4", "dong": dong}


def parse_value_lines(text: str):
    sec = section(text, r"BỐN DÒNG GIÁ TRỊ", 2)
    if sec is None:
        return None
    dong = []
    for m in re.finditer(r"^###\s+Dòng\s+(\d)\s*[—-]\s*(.+)$", sec, re.M):
        head = m.group(2)
        tm = re.search(r"\*\(([^)]+)\)\*", head)
        ten = plain(re.sub(r"\*\([^)]*\)\*", "", head))
        body = section(sec, re.escape(m.group(0)[4:].strip()), 3) or ""
        paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        first = next((p for p in paras if not p.startswith("|") and not p.startswith("-")), "")
        dong.append({"so": int(m.group(1)), "ten": ten.capitalize() if ten.isupper() else ten,
                     "nhan": plain(tm.group(1)) if tm else "", "mo_ta": plain(first)})
    return {"nguon": "BERI_KhoDuLieu_DoiTac_DoanhThu.md §3", "dong": dong}


# ── source registry, core files, pipeline ────────────────────────────────────

def parse_registry(path: str, ref: _dt.date, warnings):
    raw = read_text(path)
    if raw is None:
        warnings.append("Không đọc được sổ nguồn " + path.replace(HOME, "~"))
        return None
    try:
        d = json.loads(raw)
    except ValueError:
        warnings.append("Sổ nguồn hỏng JSON: " + path.replace(HOME, "~"))
        return None
    rows = [x for x in d.get("nguon", []) if isinstance(x, dict) and x.get("he") == "beri"]
    dem = {}
    dong = []
    for x in rows:
        st = str(x.get("trang_thai", ""))
        dem[st] = dem.get(st, 0) + 1
        dong.append({"id": str(x.get("id", "")), "ten": plain(str(x.get("ten", ""))),
                     "nhom": plain(str(x.get("nhom", ""))), "tier": plain(str(x.get("tier", ""))),
                     "trang_thai": st, "trang_thai_txt": STATUS_TXT.get(st, st),
                     "tan_suat": plain(str(x.get("tan_suat", ""))),
                     "ghi_chu": plain(str(x.get("ghi_chu", "")))})
    order = {"chan": 0, "chua_co": 1, "chap_chon": 2, "thu_cong": 3, "song": 4}
    dong.sort(key=lambda r: (order.get(r["trang_thai"], 5), r["id"]))
    cap = str(d.get("cap_nhat", ""))
    tuoi = None
    try:
        tuoi = (ref - _dt.date.fromisoformat(cap[:10])).days
    except ValueError:
        pass
    return {"nguon": "songuon_registry.json — lớp phán đoán viết tay (he = beri)",
            "cap_nhat": ddmm(_dt.date.fromisoformat(cap[:10])) if tuoi is not None else CAN_DATA,
            "tuoi_ngay": tuoi, "dem": dem, "dong": dong}


def core_files(sector_dir: str, copy_dirs, ref: _dt.date):
    out = []
    for name, role in CORE_FILES:
        main = os.path.join(sector_dir, name)
        info = file_info(main, ref)
        h0 = md5_6(main)
        copies, diff = 0, []
        for d in copy_dirs:
            p = os.path.join(d, name)
            if os.path.abspath(p) == os.path.abspath(main) or not os.path.exists(p):
                continue
            copies += 1
            if h0 is not None and md5_6(p) != h0:
                diff.append(p.replace(HOME, "~"))
        out.append({"ten": name, "vai_tro": role, "sua_luc": info["sua_luc"], "tuoi_ngay": info["tuoi_ngay"],
                    "ton_tai": info["ton_tai"], "ban_sao": copies, "khop": not diff and info["ton_tai"],
                    "lech": diff})
    return out


def parse_pipeline(sector_dir: str, now: _dt.datetime):
    res = {"quet": None, "ra_soat": None}
    feed = os.path.join(sector_dir, "output", "sector_feed.json")
    raw = read_text(feed)
    if raw is not None:
        try:
            d = json.loads(raw)
            scans = d.get("scans") or []
            # The analyzer prepends new scans, so scans[-1] is the OLDEST; take the max timestamp.
            best = max(scans, key=lambda s: str(s.get("generated_at", "")), default=None)
            if best is not None:
                safe = {k: best.get(k) for k in FEED_KEYS_ALLOWED}
                ts = str(safe.get("generated_at") or "")
                try:
                    t = _dt.datetime.fromisoformat(ts)
                    if t.tzinfo is None:
                        t = t.replace(tzinfo=VN_TZ)
                    gio = (now - t).total_seconds() / 3600.0
                    # Scans run ~08:10 · 12:45 · 17:10, so the overnight gap is ~15 h by design.
                    muc = "ok" if gio <= 16 else "warn" if gio <= 26 else "crit"
                    res["quet"] = {"moi_nhat_txt": t.strftime("%d/%m %H:%M"),
                                   "cach_gio": round(gio, 1), "so_luot": len(scans),
                                   "n_tin": safe.get("n_news"), "n_chinh_sach": safe.get("n_policy"), "muc": muc}
                except ValueError:
                    pass
        except ValueError:
            pass
    out_dir = os.path.join(sector_dir, "output")
    try:
        files = sorted(f for f in os.listdir(out_dir) if re.fullmatch(r"ra_soat_\d{4}-\d{2}-\d{2}\.json", f))
    except OSError:
        files = []
    if files:
        raw = read_text(os.path.join(out_dir, files[-1]))
        try:
            d = json.loads(raw or "")
            nhom = {}
            viec = {}
            for f in d.get("phat_hien", []) or []:
                g = str(f.get("nhom", ""))
                nhom[g] = nhom.get(g, 0) + 1
                muc = str(f.get("muc", "")).lower()
                # "sản phẩm" findings describe internal product plans; the task line is enough elsewhere.
                if ("nghiêm" in muc or "cao" in muc) and "sản phẩm" not in g.lower():
                    v = plain(str(f.get("viec", "")))
                    viec[v] = viec.get(v, 0) + 1
            res["ra_soat"] = {"ngay_txt": ddmm(_dt.date.fromisoformat(str(d.get("ngay"))[:10]))
                              if d.get("ngay") else CAN_DATA,
                              "tong": d.get("tong"), "nghiem_trong": d.get("nghiem_trong"),
                              "nhom": nhom,
                              "viec": [v if n == 1 else f"{v} ×{n}" for v, n in list(viec.items())[:8]]}
        except ValueError:
            pass
    return res


# ── assembly ─────────────────────────────────────────────────────────────────

def build_alert(lich):
    rows = [r for g in (lich or {}).get("nhom", []) for r in g["dong"] if r.get("con_ngay") is not None]
    if not rows:
        return {"muc": "na", "tieu_de": "Mốc gần nhất", "noi_dung": CAN_DATA + " — chưa tính được lịch sản phẩm"}
    n = min(r["con_ngay"] for r in rows)
    near = [r for r in rows if r["con_ngay"] == n]
    names = "; ".join(r["san_pham"] for r in near)
    muc = near[0]["muc"]
    when = "hôm nay" if n == 0 else f"còn {n} ngày"
    return {"muc": muc, "tieu_de": "Mốc gần nhất",
            "noi_dung": f"{names} — hạn {near[0]['moc_tiep_txt']}, {when}."}


def build_csv(p):
    cols = ["phan", "muc", "noi_dung", "han_hoac_nguon", "con_ngay", "trang_thai"]
    rows = []
    for g in (p.get("lich") or {}).get("nhom", []):
        for r in g["dong"]:
            rows.append(["lich · " + g["ten"], r["san_pham"], r["han_goc"], r["moc_tiep_txt"],
                         "" if r["con_ngay"] is None else str(r["con_ngay"]), r["muc"]])
    sl = p.get("so_lech") or {}
    for r in (sl.get("so_lieu") or {}).get("dong", []):
        rows.append(["so_lech_so_lieu", r["so"], r["van_de"], r["xu_ly"], "", r["trang_thai"]])
    for key in ("dang_mo", "da_chot"):
        for r in (sl.get("van_hanh") or {}).get(key, []):
            rows.append(["so_lech_van_hanh", r["so"], r["van_de"], r["xu_ly"], "", r["trang_thai"]])
    for r in (p.get("so_nguon") or {}).get("dong", []):
        rows.append(["so_nguon", r["id"], r["ten"], r["tier"], "", r["trang_thai_txt"]])
    return {"columns": cols, "rows": rows}


def overview():
    ref = today()
    now = now_vn()
    warnings = []
    ws_path = env_path("BERI_WORKSPACE_SKILL", os.path.join(HOME, ".claude", "skills", "beri-workspace", "SKILL.md"))
    sector = env_path("BERI_SECTOR_DIR", os.path.join(SYS_DIR, "beri_sector"))
    reg_path = env_path("BERI_SONGUON", os.path.join(SYS_DIR, "launchpad", "songuon_registry.json"))
    prod_dir = env_path("BERI_PRODUCT_DIR", os.path.join(HOME, "Downloads"))
    copy_env = os.environ.get("BERI_COPY_DIRS", "").strip()
    copy_dirs = ([os.path.expanduser(x) for x in copy_env.split(":") if x] if copy_env else
                 [os.path.join(HOME, "Downloads"), os.path.join(HOME, "Downloads", "BERI_Cowork", "01_He_thong"),
                  os.path.join(HOME, "Downloads", "BERI_Cowork", "03_Kho_du_lieu")])

    ws = read_text(ws_path)
    if ws is None:
        warnings.append("Không đọc được beri-workspace (" + ws_path.replace(HOME, "~") +
                        ") — lịch, cam kết, mốc neo và Sổ lệch vận hành hiện [CẦN DATA]")
    charter = read_text(os.path.join(sector, "BERI_HoiDongCoVanAI_Charter.md"))
    experts = read_text(os.path.join(sector, "BERI_HoiDongChuyenGia_18Ghe.md"))
    kho = read_text(os.path.join(sector, "BERI_KhoSoLieuChuan_2026H1.md"))
    value = read_text(os.path.join(sector, "BERI_KhoDuLieu_DoiTac_DoanhThu.md"))
    for label, txt in (("Hiến chương", charter), ("18 ghế", experts), ("Kho số liệu chuẩn", kho),
                       ("Kho dữ liệu – đối tác – doanh thu", value)):
        if txt is None:
            warnings.append(f"Thiếu tệp {label} trong {sector.replace(HOME, '~')}")

    files = product_files(prod_dir, ref)
    lich = parse_calendar(ws, ref, files) if ws else None
    if lich:
        dem = {"crit": 0, "warn": 0, "ok": 0, "na": 0}
        for g in lich["nhom"]:
            for r in g["dong"]:
                dem[r["muc"]] = dem.get(r["muc"], 0) + 1
        lich["dem"] = dem
        lich["ghi_chu"] = ("Mốc tính từ chữ trong cột Hạn, không suy đoán. Kỳ vừa qua chỉ hiện ngày, KHÔNG "
                           "kết luận đã phát hành hay chưa. Tiến độ suy từ tên tệp trong ~/Downloads — "
                           "không phải xác nhận phát hành.")
    data_led = parse_data_ledger(kho) if kho else None
    ops_led = parse_ops_ledger(ws) if ws else None
    link_ledgers(data_led, ops_led)

    kho_meta = parse_kho_meta(kho)
    newer = []
    try:
        kho_d = _dt.datetime.strptime(kho_meta["cap_nhat_txt"], "%d/%m/%Y").date()
        for key, hits in files.items():
            if not hits:
                continue
            n, when = max(hits, key=latest_key)
            if when.date() > kho_d:
                newer.append(f"{n} ({when.strftime('%d/%m')}, {stage_of(n)})")
    except ValueError:
        pass
    if newer:
        kho_meta["canh_bao"] = ("Ấn phẩm của Viện mới hơn lần cập nhật Kho (" + kho_meta["cap_nhat_txt"] +
                                "), số chưa nạp vào Kho: " + "; ".join(sorted(newer)))

    core = core_files(sector, copy_dirs, ref)
    for c in core:
        if c["lech"]:
            warnings.append(f"{c['ten']}: bản sao lệch nội dung với bản trong beri_sector — " + ", ".join(c["lech"]))

    payload = {
        "meta": {
            "generated": now.isoformat(timespec="seconds"), "today": ref.isoformat(),
            "script_version": SCRIPT_VERSION, "warnings": warnings,
            "local_only": "NỘI BỘ — dữ liệu kế hoạch của Viện NCKT, chỉ đọc cục bộ. Không đưa lên OpenBB, "
                          "không chia sẻ màn hình ra ngoài hệ thống.",
            "sources": [dict(file_info(p, ref), ten=t) for t, p in (
                ("beri-workspace", ws_path), ("Kho số liệu chuẩn", os.path.join(sector, "BERI_KhoSoLieuChuan_2026H1.md")),
                ("Sổ nguồn", reg_path), ("Quét tin ngành", os.path.join(sector, "output", "sector_feed.json")))],
        },
        "mandate": parse_mandate(ws) if ws else {"ten": CAN_DATA, "vai": CAN_DATA, "hieu_luc": CAN_DATA,
                                                  "van_ban": [], "nguon": "beri-workspace §1"},
        "lich": lich,
        "cam_ket": parse_commitments(ws) if ws else None,
        "moc_neo": parse_anchors(ws) if ws else None,
        "so_lech": {"so_lieu": data_led, "van_hanh": ops_led},
        "viec_mo": parse_open_work(ws) if ws else None,
        "so_nguon": parse_registry(reg_path, ref, warnings),
        "kho": {"tep": core, "so_lieu": kho_meta},
        "pipeline": parse_pipeline(sector, now),
        "hien_chuong": parse_tiers(charter) if charter else None,
        "tang_e": parse_expert_seats(experts) if experts else None,
        "bo_may": parse_operating_seats(charter) if charter else None,
        "quy_trinh": parse_process(charter) if charter else None,
        "ket_luan": parse_conclusions(charter) if charter else None,
        "gia_tri": parse_value_lines(value) if value else None,
    }
    payload["alert"] = build_alert(lich)
    payload["csv"] = build_csv(payload)
    return payload


# ── output ───────────────────────────────────────────────────────────────────

def clean(o):
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    return o


def emit(obj):
    text = json.dumps(clean(obj), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    buf = getattr(sys.stdout, "buffer", None)
    if buf is not None:
        buf.write((text + "\n").encode("utf-8"))
        buf.flush()
    else:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] != "overview" or len(argv) > 1:
        emit({"error": "Lệnh không hợp lệ — dùng: beri.py overview", "error_code": "BAD_ARGS"})
        return 0
    try:
        emit(overview())
    except Exception as e:  # never crash the panel; say what failed
        emit({"error": f"Lỗi nội bộ khi dựng dữ liệu BERI: {type(e).__name__}: {e}", "error_code": "INTERNAL"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
