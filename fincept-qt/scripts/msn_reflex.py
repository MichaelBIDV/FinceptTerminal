#!/usr/bin/env python3
"""
Fincept Terminal — MSN MSR Reflex data service (tab "msn_reflex", hồ sơ độ trễ MSN).

Feeds src/screens/msn_reflex/MsnReflexPanel through EconomicsService / PythonRunner and shapes the WHOLE
page as a "vnblocks/1" document rendered by src/screens/vnblocks/VnBlocks (the C++ header points here for
the full key list). Stdlib only; runs on Python 3.9+. Makes NO network calls: never dulieukinhte.com
/api/internal/*, never Vietcap directly — Vietcap data is read only from files the Lăng Kính layer
(lk_lich / vc_lk_fetch) already wrote.

Two layers, never merged silently:
  1. Hồ sơ (profile) — the fixed 24/09/2026 dossier, one JSON per edition (schema "msn_msr_reflex/1" or
     "msn_ho_so/1"). Its sections are passed through in the artifact's order. Optional weekly issue files
     tuan_YYYY-MM-DD.json (newer than the profile) override the issue-sourced values only:
       {"ky", "tin_hieu": {id: {gia_tri, trang_thai, ghi_chu, tier, ky}}, "xuc_tac": {id: {...}},
        "viec_treo": [...], "synthesis": str | [str]}
  2. Live — recomputed on every call from local stores: last close, weekly close/±, KL tuần ÷ TB20,
     look-through, MSN ÷ look-through (+ percentile since 01/2024), P/B & σ, price zone, signals X1–X3,
     P1, P5, catalysts C4 (listing venue) / C5 (VN-Index + foreign flow), the 26-week log and 5 charts.
     P2–P4, P6 and C1–C3, C6 stay issue-sourced with their as-of date. Action text is chosen by rule from
     the profile's own sizing text — the module generates no advice.
  3. Bổ sung (annex): optional event dossiers bo_sung_YYYY-MM-DD.json (schema "msn_bo_sung/1"), dated on/after
     the profile (and on/before --den when given). An annex never edits the profile or a tuần file; it adds
       "so_huu_lich"       [{"ma", "tu": "YYYY-MM-DD", "ty_le", "tier", "nguon", "ap_dung": bool}]: dated
                           look-through stakes used from "tu" on (earlier weeks keep the profile stake);
                           "ap_dung": false = pending, listed but not applied; a later annex wins on the same day.
       "so_huu_hieu_dung"  {"MCH": {"ty_le", "nguon"}}: the effective-stake alternative quoted in the MCH warning.
       "he_sinh_thai"      {"tieu_de", "so", "eyebrow", "lede", "ghi_chu", "doan": [str], "thanh_vien": [{"ma",
                           "ten", "chuoi", "phap_ly", "hieu_dung", "trong_lt", "tier", "nguon", "ghi_chu"}]}:
                           a LIVE chaebol table (raw market cap × stake from the same stores; members outside
                           SYMS such as MML are read from state/vc_lk/<SYM>/price-history.json) with MSN ÷
                           look-through on three bases: the tab's stakes, effective stakes, and effective stakes
                           plus listed members outside the look-through.
       "sections"          [vnblocks/1 sections] passed through after "chen_sau" (default "theo_doi_tuan"); ids
                           get the prefix "bo_sung_"; blocks of unknown kinds are dropped and table rows of the
                           wrong width cut or padded, each with a warning.
     A tuần file may also override a signal's colour key "mau" (good | neu | warn | bad).

Data traps handled (msn_live_spec.md):
  - nen_ngay mixes back-adjusted history (vci_history) with RAW board rows (vci_board) for the last
    sessions → weekly returns, thresholds and volume come from nen_ngay; market caps use RAW closes
    (Vietcap price-history closePrice / marketCap, then the raw board rows) × share counts.
  - KL tuần ÷ TB20 = this week's volume ÷ mean of the 20 PREVIOUS complete weeks (not including it).
  - MSR candles in nen_ngay start 2024-09 → MSR history comes from Vietcap price-history; the profile's
    own weekly ratio series (bieu_do.c4, "bản 24/09") is drawn next to the live one, never spliced in.
  - MSN share count: Vietcap/vnstore 1.460 m vs the profile's 1.535 m → the PROFILE parameter drives X3/P5
    (from the date Vietcap's count last changed; before that Vietcap's own marketCap, which reproduces the
    profile's series exactly); the local alternative and the gap are shown as a warning.
  - Ownership weights are profile parameters; a dated annex entry (so_huu_lich) replaces one from its date
    on, earlier weeks keep the profile stake. MCH legal vs effective stake → warning (source from the annex).
  - P/B μ, σ, BVPS: engine HHP (hhp_vn100_valuation.json by_ticker.MSN.pb) when present, else the
    profile's frozen set with a warning; the set used is named on the tile.

Inputs (read-only; env overrides are used by the tests):
    MSN_REFLEX_DIR    ~/SECOND BRAIN-OBSIDIAN/_System/knowledge_os/msn_reflex   ho_so_*.json, tuan_*.json, bo_sung_*.json
    MSN_BRIDGE_DIR    ~/SECOND BRAIN-OBSIDIAN/_System/fincept_bridge
                        state/vc_lk/<SYM>/price-history.json  {meta: {lay_luc, du_lieu_toi},
                          du_lieu: {cot: [tradingDate, closePrice, closePriceAdjusted, totalMatchVolume,
                          foreignNetValueTotal, totalShares, marketCap, ...], hang: [[...]]}}
                        data/chaebol_ecosystems.json      ownership cross-check (Masan-TCB members)
    MSN_VNSTORE_DB    <MSN_BRIDGE_DIR>/vnstore/vn_store.db  nen_ngay, gia_moi, free_float, ma (mode=ro)
    MSN_KOS_DIR       ~/SECOND BRAIN-OBSIDIAN/_System/knowledge_os
                        hhp_vn100_valuation.json          meta.generated, index.pe/pb, exvic3, by_ticker
                        hhp_vn100_series/MSN.json         pb.price / pb.base weekly [[epoch_ms UTC, v]]
    MSN_WIDATA_STORE  ~/SECOND BRAIN-OBSIDIAN/_System/superdash_v2/output/widata_series_store.json
                        canvases["wc-vnindex"].series [{t: epoch_ms, v}] (VN-Index before 2024-09)
    MSN_TODAY         test hook only: fixes "today" (YYYY-MM-DD) for staleness

USAGE
    python3 msn_reflex.py overview [--den YYYY-MM-DD]
        --den cuts every live source at that session (replay / audit of an earlier week).

OUTPUT — exactly ONE compact JSON object on stdout (UTF-8, ensure_ascii=False), exit code 0 even on
errors. Non-finite numbers are emitted as null. Every display string is Vietnamese and arrives
pre-formatted (decimal comma, thousands dot, minus "−", explicit "+" where the sign matters); a missing
value displays as "[CẦN DATA]". Top-level errors replace the payload:
    {"error": "<Vietnamese message incl. what to do>",
     "error_code": "NO_PROFILE" | "BAD_PROFILE" | "BAD_ARGS" | "INTERNAL"}

overview →
{
 "meta": {"generated": "2026-09-24T19:05:00+07:00", "script_version": "1.0",
          "profile_dir": str, "profile_file": str, "profile_date": "2026-09-24",
          "tuan_file": str|null, "tuan_ky": "YYYY-MM-DD"|null,
          "artifact_url": str|null,              (the dossier's own page — UI button "🌐 BẢN GỐC")
          "data_to": "2026-09-24"|null,          (last MSN session used)
          "den": "YYYY-MM-DD"|null,              (--den cut, when given)
          "age_days": int|null,                  (today − data_to)
          "profile_age_days": int,               (today − newest of profile / tuần file)
          "stale": bool, "stale_text": "" | "DỮ LIỆU CŨ 6 ngày …" | "HỒ SƠ CŨ 12 ngày …",
          "tham_so_pb": "engine HHP 24/09 16:46" | "hồ sơ 24/09",
          "warnings": [str], "sources_live": [{"ten", "duong_dan", "as_of", "tier", "ok": bool, "ghi_chu"}],
          "bo_sung": [{"file", "ky", "tieu_de", "artifact_url"}]},
 "live": {…machine-readable live numbers (tests/debug): close, week, kl_ratio, lt, ratio, pb, zone, signals…},
 "trang": {"schema": "vnblocks/1", "tieu_de": str, "sections": [section, …]},
 "csv": {"columns": ["Mục", "Chỉ báo", "Giá trị", "Kỳ", "Trạng thái", "Nhãn", "Ghi chú"], "rows": [[str × 7]]}
}

VNBLOCKS/1 — page contract rendered by src/screens/vnblocks/VnBlocks.cpp (every value a display string):
  section  {"id", "so", "tieu_de", "eyebrow", "lede", "khoi": [block, …]}
           ids in order: cong · theo_doi_tuan · [bo_sung_*, newest annex first] · o_so_dau · keynotes · ba_dong_ho · phan_1 · phan_2 ·
           roadshow · du_bao · phan_3 · case_15 · vung_gia · phan_4 · hoi_dong · hanh_dong · pre_mortem ·
           rigor_6d · nguon  (a section whose profile part is absent is skipped with a warning)
  block    {"kieu": <kind>, …}; kinds and keys:
    cong       {"dong", "tier", "phu"}
    doan       {"text", "mau"?, "the"?: true, "tieu_de"? (card title, only with "the")}
               — a plain doan with "mau" renders bold: used as a sub-heading before tables / tiles
    o_so       {"o": [{"nhan", "gia_tri", "phu", "mau", "tier", "live": bool}], "cot": int}
    bang       {"cot": [str], "dong": [[cell, …]], "chu_thich", "can_phai": [col idx]}
               cell = str | {"t", "mau", "pill": bool, "mono": bool, "dam": bool, "tip"}
    the        {"the": [{"tieu_de", "nhan": {"text", "mau"}, "text", "mau_vien", "tier"}], "cot": int}
    danh_sach  {"muc": [{"so", "tieu_de", "text", "tags": [tier, …]}]}
    trich      {"text", "nguon"}
    bieu_do    {"tieu_de", "chu_thich", "nguon", "tier", "cao": int, "block": LkLineChart block}
    canh_bao   {"tieu_de", "muc": [str], "mau"}
    chips      {"chips": [{"tier", "text"}]}
  colour keys "mau": xanh | vang | do | xam | lam | tim (anything else = ink).
  LkLineChart block (screens/langkinh/LkChart.h): {"x": [ISO dates], "series": [{"name", "y", "style":
    line|thin|dash|dot|bar|band, "mau": bull|bear|warn|info|amber|cyan|dim, "axis"?, "alpha"?,
    "y_lo"/"y_hi"/"lo_min"/"hi_max" for bands}], "left": {"label", "min"?, "max"?}, "annotations":
    [{"kind": point|vline|xband|hband, "x"/"x0"/"x1" epoch ms UTC midnight, "y"/"y0"/"y1", "text", "sub",
    "tip", "mau", "marker", "pos", "uu_tien": 1..3}]}.
  Charts: live (1) MSN weekly since 2020 + price-zone bands + X1/P1 bands, (2) MSN ÷ look-through weekly
  (live solid + profile c4 dashed, p25–p75 band, X3/P5 bands), (3) MSN/MCH/MSR/TCB/VN-Index rebased 100
  at 03/01/2023, (4) MSN P/B with ±1σ/±2σ bands, (5) KL tuần ÷ TB20 bars with the 1,5× band; profile
  charts (bản 24/09) in Phần I: c1 MSN weekly 2013→, c2a / c2b the two historical rallies rebased.
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

USAGE = "Dùng: msn_reflex.py overview [--den YYYY-MM-DD]"
ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
PROFILE_RE = re.compile(r"ho_so_(\d{4}-\d{2}-\d{2})\.json")
TUAN_RE = re.compile(r"tuan_(\d{4}-\d{2}-\d{2})\.json")
BO_SUNG_RE = re.compile(r"bo_sung_(\d{4}-\d{2}-\d{2})\.json")
BO_SUNG_SCHEMA = "msn_bo_sung/1"
BLOCK_KINDS = ("cong", "doan", "o_so", "bang", "the", "danh_sach", "trich", "bieu_do", "canh_bao", "chips")
SCHEMAS = ("msn_msr_reflex/1", "msn_ho_so/1")
DMY_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
DISCLAIMER = "Bản của hồ sơ — tham khảo, KHÔNG phải khuyến nghị."

SYMS = ("MSN", "MCH", "MSR", "TCB")
VNI = "VNINDEX"
CHILDREN = ("MCH", "MSR", "TCB")

TB_WEEKS = 20               # KL tuần ÷ mean of the 20 PREVIOUS complete weeks
TB_SESSIONS = 20            # session volume ÷ mean of the 20 previous sessions
YEAR_SESSIONS = 250
LOG_WEEKS = 26
VOL_CHART_WEEKS = 156
RATIO_FROM = date(2024, 1, 1)       # percentile / median window ("từ 01/2024")
REBASE_FROM = date(2023, 1, 3)      # Phần II: "quy về 100 ngày 03/01/2023"
CHART1_FROM = date(2020, 1, 1)
X1_HIGH_FROM = date(2026, 5, 1)     # profile X1 note: "tuần đóng cao nhất từ 05/2026"
STALE_DATA_DAYS = 4                 # data_to older than this (calendar days) → stale
STALE_PROFILE_DAYS = 10             # issue-sourced values older than this → stale
SHARE_GAP = 0.01                    # warn when two MSN share counts differ by more than 1%
PARAM_TOL = 0.005
MCH_ALT = 0.66                      # the dossier's unresolved alternative MCH stake (look_through_ghi_chu)

T_DATA = "FACT-T2"                  # vnstore / Vietcap prices, volumes, flows
T_EST = "EST"                       # anything built on profile weights, share count or μ/σ

SRC_STORE = "vnstore (Vietcap board/lịch sử)"
SRC_VC = "Vietcap price-history (lớp Lăng Kính)"
SRC_HHP = "engine HHP"

MAU_PROFILE = {"good": "xanh", "neu": "xam", "warn": "vang", "bad": "do"}

# CỔNG v1.7 DỪNG (quyết định 07/10/2026): the dossier's NAV-sizing rules are shown verbatim as FROZEN history,
# never re-evaluated week by week. MSN_HANH_DONG=luat_ho_so restores the legacy rule-based pick (tests only).
HANH_DONG_DONG_BANG = "dong_bang"
DONG_BANG_NHAN = "ĐÓNG BĂNG · luật hồ sơ %s, không chấm lại khi CỔNG v1.7 DỪNG"


def hanh_dong_mode():
    return os.environ.get("MSN_HANH_DONG", HANH_DONG_DONG_BANG).strip() or HANH_DONG_DONG_BANG


class MsnError(Exception):
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


def as_dict(v):
    return v if isinstance(v, dict) else {}


def as_list(v):
    return v if isinstance(v, list) else []


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


def k_txt(vnd, dec=2):
    """Price in đồng → nghìn đồng text: 69800 → "69,8", 33150 → "33,15"."""
    f = finite(vnd)
    return fmt_vn(f / 1000.0, dec) if f is not None else CAN


def x_txt(v):
    return fmt_vn(v, 2, fixed=True) + "×" if finite(v) is not None else CAN


def pct_txt(p, dec=1):
    """Percent number (2.05 = 2,05%) with sign."""
    return fmt_vn(p, dec, sign=True, fixed=True) + "%" if finite(p) is not None else CAN


def sigma_txt(s):
    return fmt_vn(s, 2, sign=True, fixed=True) + "σ" if finite(s) is not None else CAN


def nghin_ty(vnd):
    f = finite(vnd)
    return fmt_vn(f / 1e12, 1, fixed=True) if f is not None else CAN


def ty_txt(vnd):
    f = finite(vnd)
    return (fmt_vn(f / 1e9, 1, sign=True, fixed=True) + " tỷ") if f is not None else CAN


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
        return date.fromisoformat(head)
    except ValueError:
        return None


def parse_dmy(text):
    """"18/09/2026" → date, else None."""
    m = DMY_RE.fullmatch(nfc(text)) if isinstance(text, str) else None
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def parse_stamp(value):
    """ISO / "YYYY-MM-DD HH:MM ICT" timestamp → aware datetime in Vietnam time, else None."""
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip().replace(" ICT", "").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt.replace(tzinfo=ICT) if dt.tzinfo is None else dt.astimezone(ICT)


def ddmm(d):
    return "%02d/%02d" % (d.day, d.month) if d else ""


def ddmmyyyy(d):
    return "%02d/%02d/%d" % (d.day, d.month, d.year) if d else ""


def stamp_txt(dt):
    return "%s %02d:%02d" % (ddmm(dt.date()), dt.hour, dt.minute) if dt else ""


def day_ms(d):
    """Date → epoch ms at UTC midnight (annotation x contract)."""
    return (d - EPOCH).days * 86400000


def ms_day(t_ms):
    """Epoch ms (UTC midnight, or 00:00 Vietnam time) → calendar date."""
    return EPOCH + timedelta(milliseconds=t_ms + 7 * 3600 * 1000)


def friday(d):
    """Week key: the Friday of d's Monday–Friday week."""
    return d + timedelta(days=4 - d.weekday())


def today():
    forced = parse_day(os.environ.get("MSN_TODAY", "").strip())
    return forced or datetime.now(ICT).date()


def env_path(name, default):
    v = os.environ.get(name, "").strip()
    return os.path.expanduser(v) if v else default


def paths():
    bridge = env_path("MSN_BRIDGE_DIR", os.path.join(SYS_DIR, "fincept_bridge"))
    kos = env_path("MSN_KOS_DIR", os.path.join(SYS_DIR, "knowledge_os"))
    return {
        "profile_dir": env_path("MSN_REFLEX_DIR", os.path.join(kos, "msn_reflex")),
        "bridge": bridge,
        "vnstore": env_path("MSN_VNSTORE_DB", os.path.join(bridge, "vnstore", "vn_store.db")),
        "vc_lk": os.path.join(bridge, "state", "vc_lk"),
        "chaebol": os.path.join(bridge, "data", "chaebol_ecosystems.json"),
        "hhp": os.path.join(kos, "hhp_vn100_valuation.json"),
        "hhp_series": os.path.join(kos, "hhp_vn100_series", "MSN.json"),
        "widata": env_path("MSN_WIDATA_STORE",
                           os.path.join(SYS_DIR, "superdash_v2", "output", "widata_series_store.json")),
    }


def compare(v, phep, muc):
    if v is None or muc is None:
        return None
    return {">": v > muc, ">=": v >= muc, "<": v < muc, "<=": v <= muc}.get(phep)


def asof(days, vals, d):
    """(day, value) of the last point with day ≤ d in a sorted day list, else (None, None)."""
    i = bisect.bisect_right(days, d) - 1
    return (days[i], vals[i]) if i >= 0 else (None, None)


def mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def tier_mau(tier):
    t = nfc(tier).upper()
    if not t:
        return "xam"
    if "UNV" in t or "1 NGUỒN" in t:
        return "do"
    if "T1" in t:
        return "xanh"
    if "T2" in t:
        return "lam"
    if "T3" in t:
        return "tim"
    if "EST" in t:
        return "vang"
    return "xam"


def status_mau(text):
    u = nfc(text).upper()
    if not u:
        return "xam"
    if any(k in u for k in ("KÍCH HOẠT", "SAI", "UNVERIFIED", "LOẠI", "MÂU THUẪN")):
        return "do"
    if any(k in u for k in ("CHỜ", "MỘT PHẦN", "GẦN", "MỞ", "TRƯỢT", "CHẠM", "VÀNG", "ĐIỀU KIỆN")):
        return "vang"
    if any(k in u for k in ("ĐẠT", "ĐÚNG", "AN TOÀN", "ĐÃ CÓ")):
        return "xanh"
    return "xam"


# ── vnblocks helpers ─────────────────────────────────────────────────────────


def sec(sid, tieu_de, khoi, so="", eyebrow="", lede=""):
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
    """Sub-heading: a plain paragraph with a colour renders bold amber."""
    return doan(text, mau="vang") if nfc(text) else None


def cell(t, mau=None, pill=False, mono=False, dam=False, tip=None):
    c = {"t": t if isinstance(t, str) else ("" if t is None else str(t))}
    if mau:
        c["mau"] = mau
    if pill:
        c["pill"] = True
    if mono:
        c["mono"] = True
    if dam:
        c["dam"] = True
    if tip:
        c["tip"] = tip
    return c


def tier_cell(tier):
    return cell(nfc(tier) or "—", mau=tier_mau(tier), pill=bool(nfc(tier)))


def pill(text, mau=None):
    text = nfc(text)
    return cell(text or "—", mau=mau or status_mau(text), pill=bool(text))


def bang(cot, dong, chu_thich="", can_phai=None):
    rows = [[c if isinstance(c, (str, dict)) else ("" if c is None else str(c)) for c in r] for r in dong]
    b = {"kieu": "bang", "cot": [nfc(c) for c in cot], "dong": rows}
    if nfc(chu_thich):
        b["chu_thich"] = nfc(chu_thich)
    if can_phai:
        b["can_phai"] = list(can_phai)
    return b


def o_so(tiles, cot=4):
    tiles = [t for t in tiles if t]
    return {"kieu": "o_so", "o": tiles, "cot": cot} if tiles else None


def tile(nhan, gia_tri, phu="", mau=None, tier="", live=False):
    t = {"nhan": nfc(nhan), "gia_tri": gia_tri or CAN, "phu": nfc(phu), "tier": nfc(tier), "live": bool(live)}
    if mau:
        t["mau"] = mau
    return t


def the_block(cards, cot=3):
    cards = [c for c in cards if c]
    return {"kieu": "the", "the": cards, "cot": cot} if cards else None


def card(tieu_de, text, nhan=None, nhan_mau=None, mau_vien=None, tier=""):
    c = {"tieu_de": nfc(tieu_de), "text": nfc(text), "tier": nfc(tier)}
    if nfc(nhan):
        c["nhan"] = {"text": nfc(nhan), "mau": nhan_mau or status_mau(nhan)}
    if mau_vien:
        c["mau_vien"] = mau_vien
    return c


def danh_sach(items):
    items = [i for i in items if i]
    return {"kieu": "danh_sach", "muc": items} if items else None


def canh_bao(tieu_de, muc, mau="vang"):
    muc = [nfc(m) for m in muc if nfc(m)]
    return {"kieu": "canh_bao", "tieu_de": nfc(tieu_de), "muc": muc, "mau": mau} if muc else None


def tier_list(v):
    if isinstance(v, list):
        return [nfc(t) for t in v if nfc(t)]
    return [nfc(v)] if nfc(v) else []


# ── Profile ──────────────────────────────────────────────────────────────────


def list_dated(pdir, rx):
    try:
        names = os.listdir(pdir)
    except OSError:
        return []
    out = []
    for n in names:
        m = rx.fullmatch(n)
        if m and parse_day(m.group(1)):
            out.append((m.group(1), os.path.join(pdir, n)))
    return sorted(out, reverse=True)


def load_profile(pdir):
    """Newest ho_so_*.json → (profile, path, date). Raises NO_PROFILE / BAD_PROFILE."""
    found = list_dated(pdir, PROFILE_RE)
    if not found:
        raise MsnError("NO_PROFILE", "Chưa có hồ sơ MSN nào trong %s — cài ho_so_YYYY-MM-DD.json "
                                     "(schema msn_msr_reflex/1) rồi bấm FETCH." % pdir)
    ky, path = found[0]
    try:
        prof = load_json(path)
    except (OSError, ValueError) as exc:
        raise MsnError("BAD_PROFILE", "Không đọc được %s (%s) — sửa JSON rồi FETCH lại." % (path, exc))
    if not isinstance(prof, dict):
        raise MsnError("BAD_PROFILE", "%s không phải JSON object." % path)
    if prof.get("schema") not in SCHEMAS:
        raise MsnError("BAD_PROFILE", "%s sai schema (%r, cần một trong %s)." % (path, prof.get("schema"),
                                                                                 ", ".join(SCHEMAS)))
    tdt = prof.get("theo_doi_tuan")
    if not isinstance(tdt, dict) or not isinstance(tdt.get("tham_so"), dict):
        raise MsnError("BAD_PROFILE", "%s thiếu theo_doi_tuan.tham_so — không tính được khối LIVE." % path)
    return prof, path, parse_day(prof.get("ho_so")) or parse_day(ky)


def load_tuan(pdir, profile_day, warnings):
    """Newest tuan_*.json dated on/after the profile → (dict, path) or (None, None)."""
    for ky, path in list_dated(pdir, TUAN_RE):
        d = parse_day(ky)
        if profile_day and d < profile_day:
            return None, None
        try:
            raw = load_json(path)
        except (OSError, ValueError) as exc:
            warnings.append("Bỏ qua %s (không đọc được: %s)" % (path, exc))
            continue
        if not isinstance(raw, dict):
            warnings.append("Bỏ qua %s (không phải JSON object)" % path)
            continue
        raw.setdefault("ky", ky)
        return raw, path
    return None, None


# ── Annexes (bo_sung_*.json) ─────────────────────────────────────────────────


def load_bo_sung(pdir, profile_day, den, warnings):
    """Annexes dated on/after the profile (and on/before `den`) → [(dict, path, day)], oldest first."""
    out = []
    for ky, path in list_dated(pdir, BO_SUNG_RE):           # newest first
        d = parse_day(ky)
        if profile_day and d < profile_day:
            break
        if den and d > den:
            continue
        try:
            raw = load_json(path)
        except (OSError, ValueError) as exc:
            warnings.append("Bỏ qua %s (không đọc được: %s)" % (path, exc))
            continue
        if not isinstance(raw, dict) or raw.get("schema") != BO_SUNG_SCHEMA:
            warnings.append("Bỏ qua %s (cần schema %s)." % (path, BO_SUNG_SCHEMA))
            continue
        raw.setdefault("ky", ky)
        out.append((raw, path, d))
    out.reverse()
    return out


def ownership_schedule(annexes, warnings):
    """Annex so_huu_lich → ({sym: [(from_day, stake, meta)] by day}, [(sym, day, stake, meta)] pending)."""
    lich, cho = {}, []
    for raw, path, _ in annexes:
        for e in as_list(raw.get("so_huu_lich")):
            e = as_dict(e)
            sym, d, w = nfc(e.get("ma")).upper(), parse_day(e.get("tu")), finite(e.get("ty_le"))
            if sym not in CHILDREN or d is None or w is None or not 0 < w <= 1:
                warnings.append("Bỏ qua dòng so_huu_lich của %s: %s (cần mã %s, ngày YYYY-MM-DD, tỷ lệ 0–1)."
                                % (os.path.basename(path), json.dumps(e, ensure_ascii=False)[:120],
                                   "/".join(CHILDREN)))
                continue
            meta = {"tier": nfc(e.get("tier")), "nguon": nfc(e.get("nguon")), "ky": raw.get("ky")}
            if e.get("ap_dung") is False:
                cho.append((sym, d, w, meta))
            else:
                lich.setdefault(sym, []).append((d, w, meta))
    for rows in lich.values():
        rows.sort(key=lambda t: t[0])                      # stable: a later annex wins on the same day
    return lich, cho


def effective_alt(annexes):
    """(stake, source) of MCH's effective stake from the newest annex that states one, else None."""
    for raw, _, _ in reversed(annexes):
        e = as_dict(as_dict(raw.get("so_huu_hieu_dung")).get("MCH"))
        v = finite(e.get("ty_le"))
        if v is not None and 0 < v <= 1:
            return v, nfc(e.get("nguon")) or "bản bổ sung %s" % raw.get("ky")
    return None


def annex_symbols(annexes):
    """Listed tickers of the annexes' chaebol tables outside SYMS (read-only, for the live table)."""
    out = []
    for raw, _, _ in annexes:
        for m in as_list(as_dict(raw.get("he_sinh_thai")).get("thanh_vien")):
            s = nfc(as_dict(m).get("ma")).upper()
            if re.fullmatch(r"[A-Z0-9]{3,10}", s) and s not in SYMS and s != VNI and s not in out:
                out.append(s)
    return tuple(out)


def deep_nfc(o):
    if isinstance(o, str):
        return nfc(o)
    if isinstance(o, dict):
        return {k: deep_nfc(v) for k, v in o.items()}
    if isinstance(o, list):
        return [deep_nfc(v) for v in o]
    return o


def share_txt(v):
    """0.8746 → "87,46%"; missing → "–"."""
    f = finite(v)
    return (fmt_vn(f * 100, 2) + "%") if f is not None else "–"


def uniq_id(sid, used, day):
    if sid in used:
        sid = "%s_%s" % (sid, day.strftime("%Y%m%d"))
    used.add(sid)
    return sid


def stake_note(lv):
    """Note under the dossier's "Cách tính": stakes in force, annex changes, pending annex lines."""
    if not lv.ok or not (lv.lich or lv.lich_cho):
        return None
    done = ["%s %s từ %s (%s · %s)" % (s, share_txt(w), ddmmyyyy(d), m.get("tier") or "chưa gắn nhãn",
                                       m.get("nguon") or "bản bổ sung %s" % m.get("ky"))
            for s in CHILDREN for d, w, m in lv.lich.get(s, [])]
    text = "Phiên %s: %s." % (ddmmyyyy(lv.data_to), lv.stakes_txt(lv.data_to))
    if done:
        text += " Bản bổ sung đổi: %s; các tuần trước ngày đó giữ tỷ lệ hồ sơ." % "; ".join(done)
    if lv.lich_cho:
        text += " Chờ CBTT, chưa áp dụng: %s." % "; ".join(
            "%s %s dự kiến từ %s (%s)" % (s, share_txt(w), ddmmyyyy(d), m.get("nguon") or m.get("tier") or "bản bổ sung")
            for s, d, w, m in lv.lich_cho)
    return doan(text, mau="lam", the=True, tieu_de="Tỷ lệ sở hữu look-through đang dùng")


def section_he_sinh_thai(raw, lv, sid, out_live, out_csv):
    """LIVE chaebol table of an annex: raw market cap × stake from the tab's own stores, and MSN ÷ look-through on
    the tab's stakes, on effective stakes, and on effective stakes plus listed members outside the LT."""
    hst = as_dict(raw.get("he_sinh_thai"))
    members = [as_dict(m) for m in as_list(hst.get("thanh_vien")) if isinstance(m, dict)]
    d = lv.data_to if lv.ok else None
    rows, extra, parts = [], [], {}
    lt_eff = lt_ext = 0.0
    full_eff = full_ext = d is not None
    for m in members:
        sym = nfc(m.get("ma")).upper()
        hd, in_lt = finite(m.get("hieu_dung")), bool(m.get("trong_lt"))
        day = c = mc = part = None
        if sym and d is not None:
            day, c, _ = lv.kho.raw_close(sym, d)
            mc, _ = lv.kho.mcap(sym, d)
            part = hd * mc if (hd is not None and mc) else None
            if part is None:
                full_ext = False
                full_eff = full_eff and not in_lt
            else:
                lt_ext += part
                if in_lt:
                    lt_eff += part
                else:
                    extra.append((sym, part))
            parts[sym] = {"mcap": mc, "part": part, "hieu_dung": hd, "day": day.isoformat() if day else None}
        w_tab = lv.weight(sym, d) if (sym in CHILDREN and in_lt and d is not None) else None
        tab = share_txt(w_tab) if w_tab is not None else ("ngoài LT" if sym else "chưa niêm yết")
        note = " · ".join(x for x in (nfc(m.get("tier")), nfc(m.get("nguon")), nfc(m.get("ghi_chu"))) if x)
        rows.append([cell(("%s · %s" % (sym, nfc(m.get("ten")))) if sym else nfc(m.get("ten")), dam=True),
                     nfc(m.get("chuoi")),
                     cell("%s · %s" % (share_txt(m.get("phap_ly")), share_txt(hd)), mono=True),
                     cell(tab, mono=True, mau=None if w_tab is not None else "xam"),
                     cell(("%s (%s) · %s" % (k_txt(c), ddmm(day), nghin_ty(mc))) if c else "–", mono=True),
                     cell(nghin_ty(part) if part is not None else "–", mono=True),
                     note])
    khoi = []
    if d is not None and lv.mcap_msn:
        r_eff = lv.mcap_msn / lt_eff if (full_eff and lt_eff) else None
        r_ext = lv.mcap_msn / lt_ext if (full_ext and lt_ext) else None
        add = " + ".join("%s %s" % (s, nghin_ty(p)) for s, p in extra) or "không có mã ngoài LT"
        tiles = [
            tile("MSN ÷ LT · tỷ lệ của tab", x_txt(lv.ratio_now),
                 "LT %s nghìn tỷ · %s · X3 > 0,60× · P5 < 0,45×" % (nghin_ty(lv.lt_now), lv.stakes_txt(d)),
                 tier=T_EST, live=True),
            tile("MSN ÷ LT hiệu dụng", x_txt(r_eff),
                 "LT %s nghìn tỷ theo lợi ích kinh tế qua các tầng trung gian" % (nghin_ty(lt_eff) if full_eff else CAN),
                 tier=T_EST, live=True),
            tile("MSN ÷ LT mở rộng", x_txt(r_ext),
                 "LT hiệu dụng + %s = %s nghìn tỷ" % (add, nghin_ty(lt_ext) if full_ext else CAN), tier=T_EST, live=True),
            tile("Vốn hóa MSN", nghin_ty(lv.mcap_msn),
                 "nghìn tỷ · %s × %s triệu cp (số cp hồ sơ) · phiên %s" % (
                     k_txt(lv.close), fmt_vn((lv.msn_shares or 0) / 1e6, 1), ddmm(d)), tier=T_EST, live=True)]
        khoi.append(o_so(tiles, cot=4))
        out_live.clear()
        out_live.update({"ky": raw.get("ky"), "lt_tab": lv.lt_now, "ratio_tab": lv.ratio_now,
                         "lt_eff": lt_eff if full_eff else None, "ratio_eff": r_eff,
                         "lt_ext": lt_ext if full_ext else None, "ratio_ext": r_ext, "members": parts})
        out_csv.extend(["Bổ sung", t["nhan"], t["gia_tri"], ddmmyyyy(d), "LIVE", t["tier"], t["phu"]] for t in tiles)
    else:
        khoi.append(doan("%s: kho giá không có phiên MSN, bảng chỉ còn phần tĩnh." % CAN, mau="do"))
    khoi.append(bang(["Mắt xích", "Chuỗi sở hữu", "Pháp lý · hiệu dụng", "Trong LT của tab",
                      "Giá · vốn hóa (nghìn tỷ)", "Phần MSN hiệu dụng (nghìn tỷ)", "Nhãn · nguồn"],
                     rows, hst.get("ghi_chu"), can_phai=[4, 5]))
    khoi += [doan(t) for t in as_list(hst.get("doan")) if nfc(t)]
    return sec(sid, nfc(hst.get("tieu_de")) or "Hệ sinh thái Masan", khoi, so=nfc(hst.get("so")) or "BS",
               eyebrow=nfc(hst.get("eyebrow")) or "Bản bổ sung %s · LIVE" % ddmmyyyy(parse_day(raw.get("ky"))),
               lede=hst.get("lede") or "")


def annex_sections(raw, path, warnings, used, day):
    """An annex's own vnblocks sections, checked against the block kinds VnBlocks renders."""
    base = os.path.basename(path)
    out = []
    for i, s in enumerate(as_list(raw.get("sections"))):
        if not isinstance(s, dict):
            warnings.append("%s: mục thứ %d không phải object, bỏ qua." % (base, i + 1))
            continue
        sid = re.sub(r"[^a-z0-9_]+", "_", nfc(s.get("id")).lower()).strip("_") or "muc_%d" % (i + 1)
        sid = uniq_id(sid if sid.startswith("bo_sung_") else "bo_sung_" + sid, used, day)
        khoi = []
        for j, b in enumerate(as_list(s.get("khoi"))):
            kieu = as_dict(b).get("kieu")
            if kieu not in BLOCK_KINDS:
                warnings.append("%s: bỏ khối lạ %r (mục %s, khối %d)." % (base, kieu, sid, j + 1))
                continue
            b = deep_nfc(b)
            if kieu == "bang":
                n = len(as_list(b.get("cot")))
                rows = []
                for r in as_list(b.get("dong")):
                    r = as_list(r)
                    if len(r) != n:
                        warnings.append("%s: dòng bảng có %d ô, cần %d (mục %s), đã cắt/đệm." % (base, len(r), n, sid))
                        r = (r + [""] * n)[:n]
                    rows.append(r)
                b["dong"] = rows
            khoi.append(b)
        out.append(sec(sid, s.get("tieu_de"), khoi, so=nfc(s.get("so")), eyebrow=s.get("eyebrow") or "",
                       lede=s.get("lede") or ""))
    return out


def insert_annexes(sections, annexes, lv, warnings, out_live, out_csv):
    """Annex sections (the live chaebol table first, then the annex's own) after each annex's anchor section;
    annexes run oldest first, so the newest lands right under the anchor."""
    used = {s.get("id") for s in sections}
    for raw, path, day in annexes:
        base = os.path.basename(path)
        block = [section_he_sinh_thai(raw, lv, uniq_id("bo_sung_he_sinh_thai", used, day), out_live, out_csv)
                 if as_list(as_dict(raw.get("he_sinh_thai")).get("thanh_vien")) else None]
        block = [b for b in block if b] + annex_sections(raw, path, warnings, used, day)
        if not block:
            warnings.append("Bản bổ sung %s không có mục nào để hiển thị." % base)
            continue
        anchor = nfc(raw.get("chen_sau")) or "theo_doi_tuan"
        ids = [s.get("id") for s in sections]
        if anchor in ids:
            k = ids.index(anchor) + 1
            sections = sections[:k] + block + sections[k:]
        else:
            warnings.append("Bản bổ sung %s: không thấy mục \"%s\" để chèn sau, đặt cuối trang." % (base, anchor))
            sections = sections + block
    return sections


class Issue:
    """Issue-sourced view: profile values overridden by the newest tuần file (never by live data)."""

    def __init__(self, prof, pday, tuan):
        tdt = as_dict(prof.get("theo_doi_tuan"))
        self.pday = pday
        self.tuan = tuan or {}
        self.tday = parse_day(self.tuan.get("ky")) if tuan else None
        over = as_dict(self.tuan.get("tin_hieu"))
        self.signals = []
        for r in as_list(tdt.get("tin_hieu")):
            if not isinstance(r, dict):
                continue
            row = dict(r)
            row["as_of"] = ddmmyyyy(pday)
            o = as_dict(over.get(row.get("id")))
            if o:
                v = o.get("gia_tri")
                if isinstance(v, str):
                    row["gia_tri_in"] = v
                elif finite(v) is not None:
                    row["gia_tri_in"] = fmt_vn(v, 2)
                for k in ("trang_thai", "ghi_chu", "tier", "ky", "mau"):
                    if nfc(o.get(k)):
                        row[k] = o[k]
                row["as_of"] = ddmmyyyy(self.tday)
            self.signals.append(row)
        xover = as_dict(self.tuan.get("xuc_tac"))
        self.catalysts = []
        for r in as_list(tdt.get("chat_xuc_tac")):
            if not isinstance(r, dict):
                continue
            row = dict(r)
            row["as_of"] = ddmmyyyy(pday)
            o = as_dict(xover.get(row.get("id")))
            if o:
                row.update({k: v for k, v in o.items() if v is not None})
                row["as_of"] = ddmmyyyy(self.tday)
            self.catalysts.append(row)
        vt = self.tuan.get("viec_treo")
        self.viec_treo = vt if isinstance(vt, list) else as_list(tdt.get("viec_treo"))
        syn = self.tuan.get("synthesis")
        if isinstance(syn, str) and syn.strip():
            syn = [syn]
        self.synthesis = syn if isinstance(syn, list) else as_list(tdt.get("synthesis_tuan"))
        self.synthesis_ky = ddmmyyyy(self.tday if (isinstance(self.tuan.get("synthesis"), (str, list))
                                                   and self.tday) else pday)


# ── Live stores ──────────────────────────────────────────────────────────────


class Kho:
    """Read-only access to the local live sources, cut at `den`; records warnings + source rows."""

    def __init__(self, p, den, warnings, extra=()):
        self.p = p
        self.den = den
        self.warnings = warnings
        self.extra = tuple(s for s in extra if s and s not in SYMS and s != VNI)   # annex-only tickers
        self.sources = []
        self.nen = {}        # sym → {"d": [date], "c": [close], "kl": [vol], "src": [nguon]}
        self.gia_moi = {}    # sym → row dict (only when its day ≤ den)
        self.shares = {}     # sym → (issue_share, cap_nhat)
        self.san = {}        # sym → exchange
        self.vc = {}         # sym → {"d": [...], "c": raw close, "ca": adjusted, "m": mcap, "sh": shares,
                             #        "nn": foreign net value, "lay_luc": str}
        self.hhp = None
        self.hhp_gen = None
        self.pb_series = None
        self.vni_ext = ([], [])
        self.owners = {}
        self._load_db()
        for s in SYMS + self.extra:
            self._load_vc(s)
        self._load_hhp()
        self._load_widata()
        self._load_owners()

    def _src(self, ten, path, as_of, tier, ok, note=""):
        self.sources.append({"ten": ten, "duong_dan": path, "as_of": as_of, "tier": tier, "ok": ok,
                             "ghi_chu": note})

    def _cut(self, d):
        return self.den is None or d <= self.den

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

    def _load_db(self):
        path = self.p["vnstore"]
        ten = "Kho giá vnstore (nen_ngay, gia_moi, free_float, ma)"
        if not os.path.isfile(path):
            self.warnings.append("Thiếu kho giá %s — khối LIVE không tính được." % path)
            self._src(ten, path, None, T_DATA, False, "không có tệp")
            return
        con = None
        try:
            try:
                con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
                con.execute("SELECT 1 FROM nen_ngay LIMIT 1")
            except sqlite3.Error:
                if con is not None:
                    con.close()
                con = sqlite3.connect("file:%s?immutable=1" % path, uri=True)
            syms = SYMS + (VNI,) + self.extra
            q = ",".join("?" * len(syms))
            for s, ngay, dong, kl, nguon in con.execute(
                    "SELECT symbol, ngay, dong, kl, nguon FROM nen_ngay WHERE symbol IN (%s) ORDER BY symbol, ngay"
                    % q, syms):
                d = parse_day(ngay)
                c = finite(dong)
                if d is None or c is None or c <= 0 or not self._cut(d):
                    continue
                r = self.nen.setdefault(s, {"d": [], "c": [], "kl": [], "src": []})
                r["d"].append(d)
                r["c"].append(c)
                r["kl"].append(finite(kl) or 0.0)
                r["src"].append(nguon or "")
            cols = [c[1] for c in con.execute("PRAGMA table_info(gia_moi)")]
            for row in con.execute("SELECT * FROM gia_moi WHERE symbol IN (%s)" % q, syms):
                r = dict(zip(cols, row))
                d = parse_day(r.get("ngay"))
                if d is not None and self._cut(d):
                    self.gia_moi[r["symbol"]] = r
            for s, sh, cap in con.execute("SELECT symbol, issue_share, cap_nhat FROM free_float WHERE symbol IN (%s)"
                                          % q, syms):
                if finite(sh):
                    self.shares[s] = (float(sh), cap)
            for s, san in con.execute("SELECT symbol, san FROM ma WHERE symbol IN (%s)" % q, syms):
                self.san[s] = san
        except sqlite3.Error as exc:
            self.warnings.append("Không đọc được kho giá %s (%s)" % (path, exc))
            self._src(ten, path, None, T_DATA, False, "lỗi SQLite: %s" % exc)
            return
        finally:
            if con is not None:
                con.close()
        last = self.nen.get("MSN", {}).get("d", [])
        missing = [s for s in SYMS + (VNI,) if s not in self.nen]
        note = "nen_ngay: lịch sử điều chỉnh (vci_history) + vài phiên cuối giá thô bảng điện (vci_board)"
        if missing:
            note += " · thiếu " + ", ".join(missing)
            self.warnings.append("Kho giá thiếu nến của: %s" % ", ".join(missing))
        self._src(ten, path, last[-1].isoformat() if last else None, T_DATA, bool(last), note)

    def _load_vc(self, sym):
        path = os.path.join(self.p["vc_lk"], sym, "price-history.json")
        ten = "%s %s" % (SRC_VC, sym)
        raw = self._read(path, ten, T_DATA)
        if raw is None:
            return
        du = as_dict(as_dict(raw).get("du_lieu"))
        cot = as_list(du.get("cot"))
        ix = {c: i for i, c in enumerate(cot)}
        need = ("tradingDate", "closePrice", "closePriceAdjusted", "marketCap", "totalShares")
        if any(k not in ix for k in need):
            self.warnings.append("%s thiếu cột (%s)" % (path, ", ".join(k for k in need if k not in ix)))
            self._src(ten, path, None, T_DATA, False, "thiếu cột")
            return
        out = {"d": [], "c": [], "ca": [], "m": [], "sh": [], "nn": []}
        rows = []
        for r in as_list(du.get("hang")):
            if not isinstance(r, list) or len(r) < len(cot):
                continue
            d = parse_day(r[ix["tradingDate"]])
            c = finite(r[ix["closePrice"]])
            if d is None or c is None or c <= 0 or not self._cut(d):
                continue
            rows.append((d, c, finite(r[ix["closePriceAdjusted"]]), finite(r[ix["marketCap"]]),
                         finite(r[ix["totalShares"]]),
                         finite(r[ix["foreignNetValueTotal"]]) if "foreignNetValueTotal" in ix else None))
        rows.sort(key=lambda t: t[0])
        for d, c, ca, m, sh, nn in rows:
            if out["d"] and out["d"][-1] == d:
                continue
            out["d"].append(d)
            out["c"].append(c)
            out["ca"].append(ca)
            out["m"].append(m)
            out["sh"].append(sh)
            out["nn"].append(nn)
        meta = as_dict(as_dict(raw).get("meta"))
        out["lay_luc"] = meta.get("lay_luc")
        if not out["d"]:
            self._src(ten, path, None, T_DATA, False, "không có dòng hợp lệ")
            return
        self.vc[sym] = out
        self._src(ten, path, out["d"][-1].isoformat(), T_DATA, True,
                  "giá thô + giá điều chỉnh + marketCap/totalShares; lấy lúc %s" % (meta.get("lay_luc") or "?"))

    def _load_hhp(self):
        raw = self._read(self.p["hhp"], "%s — định giá VN100" % SRC_HHP, T_EST)
        if isinstance(raw, dict):
            self.hhp = raw
            self.hhp_gen = parse_stamp(as_dict(raw.get("meta")).get("generated"))
            stale = as_list(as_dict(raw.get("meta")).get("stale_fields"))
            self._src("%s — định giá VN100" % SRC_HHP, self.p["hhp"],
                      self.hhp_gen.date().isoformat() if self.hhp_gen else None, T_EST, True,
                      ("trường stale: " + ", ".join(str(s) for s in stale)) if stale else "")
        ser = self._read(self.p["hhp_series"], "%s — chuỗi P/B MSN" % SRC_HHP, T_EST)
        pb = as_dict(as_dict(ser).get("pb"))
        price, base = as_list(pb.get("price")), as_list(pb.get("base"))
        if price and base:
            bd = {}
            for t, v in base:
                if finite(t) is not None and finite(v):
                    bd[ms_day(t)] = v
            pts = []
            for t, v in price:
                if finite(t) is None or not finite(v):
                    continue
                d = ms_day(t)
                if self._cut(d) and bd.get(d):
                    pts.append((d, v, bd[d]))
            pts.sort()
            self.pb_series = {"d": [x[0] for x in pts], "price_k": [x[1] for x in pts],
                              "base_k": [x[2] for x in pts], "mean": finite(pb.get("mean")),
                              "sd": finite(pb.get("sd"))}
            self._src("%s — chuỗi P/B MSN" % SRC_HHP, self.p["hhp_series"],
                      pts[-1][0].isoformat() if pts else None, T_EST, bool(pts), "giá & BVPS theo tuần")

    def _load_widata(self):
        ten = "Kho chuỗi WiData (VN-Index trước 2024-09)"
        raw = self._read(self.p["widata"], ten, T_DATA)
        ser = as_list(as_dict(as_dict(as_dict(raw).get("canvases")).get("wc-vnindex")).get("series"))
        pts = []
        for p in ser:
            if isinstance(p, dict) and finite(p.get("t")) is not None and finite(p.get("v")):
                d = ms_day(p["t"])
                if self._cut(d):
                    pts.append((d, float(p["v"])))
        pts.sort()
        self.vni_ext = ([d for d, _ in pts], [v for _, v in pts])
        if raw is not None:
            self._src(ten, self.p["widata"], pts[-1][0].isoformat() if pts else None, T_DATA, bool(pts),
                      "wc-vnindex (VnDirect)")

    def _load_owners(self):
        ten = "Hệ sinh thái chaebol (cổ đông lớn)"
        raw = self._read(self.p["chaebol"], ten, T_DATA)
        members = as_dict(as_dict(as_dict(as_dict(raw).get("ecosystems")).get("Masan-TCB")).get("members"))
        for sym in CHILDREN:
            for sh in as_list(as_dict(members.get(sym)).get("top_shareholders")):
                name = nfc(as_dict(sh).get("ownerName"))
                if "masan" in name.lower() and finite(sh.get("percentage")) is not None:
                    self.owners[sym] = (float(sh["percentage"]), name, sh.get("publicDate"))
                    break
        if raw is not None:
            self._src(ten, self.p["chaebol"], nfc(as_dict(raw).get("as_of"))[:10] or None, T_DATA,
                      bool(self.owners), "đối chiếu tỷ lệ sở hữu của hồ sơ")

    # ── price accessors ──

    def closes(self, sym):
        r = self.nen.get(sym)
        return (r["d"], r["c"]) if r else ([], [])

    def vni(self):
        """VN-Index daily: widata before the first vnstore row, vnstore after."""
        d1, c1 = self.closes(VNI)
        d0, c0 = self.vni_ext
        if not d1:
            return d0, c0
        cut = bisect.bisect_left(d0, d1[0])
        return d0[:cut] + d1, c0[:cut] + c1

    def raw_close(self, sym, d):
        """(day, raw close, source) at the last session ≤ d: Vietcap raw closePrice, or a newer
        vnstore row (the board rows are raw)."""
        dv, cv = (None, None)
        vc = self.vc.get(sym)
        if vc:
            i = bisect.bisect_right(vc["d"], d) - 1
            if i >= 0:
                dv, cv = vc["d"][i], vc["c"][i]
        dn, cn = asof(*self.closes(sym), d)
        if dn is not None and (dv is None or dn > dv):
            return dn, cn, "nen"
        return dv, cv, "vc" if dv else None

    def vc_shares(self, sym, d):
        vc = self.vc.get(sym)
        if not vc:
            return None
        i = bisect.bisect_right(vc["d"], d) - 1
        while i >= 0:
            if vc["sh"][i]:
                return vc["sh"][i]
            i -= 1
        return None

    def share_break(self, sym):
        """First day of the latest constant run of Vietcap totalShares (None when unknown)."""
        vc = self.vc.get(sym)
        if not vc:
            return None
        last = None
        start = None
        for d, sh in zip(vc["d"], vc["sh"]):
            if not sh:
                continue
            if sh != last:
                last, start = sh, d
        return start

    def mcap(self, sym, d, msn_shares=None, msn_break=None):
        """Market cap (đồng) at the last session ≤ d from RAW prices. MSN on the profile share count from
        `msn_break` on (see module doc); others: Vietcap marketCap, else raw close × shares."""
        day, c, src = self.raw_close(sym, d)
        if day is None:
            return None, None
        if sym == "MSN" and msn_shares and (msn_break is None or day >= msn_break):
            return c * msn_shares, day
        if src == "vc":
            vc = self.vc[sym]
            i = bisect.bisect_right(vc["d"], day) - 1
            if vc["m"][i]:
                return vc["m"][i], day
            sh = self.vc_shares(sym, day) or self.shares.get(sym, (None,))[0]
            return (c * sh, day) if sh else (None, day)
        sh = self.shares.get(sym, (None,))[0] or self.vc_shares(sym, day)
        return (c * sh, day) if sh else (None, day)


# ── Weekly aggregation ───────────────────────────────────────────────────────


def weeks_of(days, closes, vols=None):
    """Daily rows → weeks [{"fri", "last", "close", "kl", "n"}] (Mon–Fri, labelled by Friday)."""
    out = []
    for i, d in enumerate(days):
        f = friday(d)
        if out and out[-1]["fri"] == f:
            w = out[-1]
            w["last"], w["close"], w["n"] = d, closes[i], w["n"] + 1
            w["kl"] += vols[i] if vols else 0.0
        else:
            out.append({"fri": f, "last": d, "close": closes[i], "kl": vols[i] if vols else 0.0, "n": 1})
    return out


def vol_ratio(weeks, i):
    """Week i volume ÷ mean of the TB_WEEKS previous weeks (None without enough history)."""
    if i < TB_WEEKS:
        return None
    base = mean([w["kl"] for w in weeks[i - TB_WEEKS:i]])
    return weeks[i]["kl"] / base if base else None


def zone_of(price_k, vung):
    """Price zone by the profile's bounds (k VND): lo ≤ p < hi; the top bound is inclusive."""
    names = (("giam", "Giảm"), ("chuyen_duoi", "chuyển"), ("co_so", "Cơ sở"), ("chuyen_tren", "chuyển"),
             ("tang", "Tăng"))
    if price_k is None:
        return CAN
    for key, name in names:
        lo_hi = as_list(vung.get(key))
        if len(lo_hi) == 2 and finite(lo_hi[0]) is not None and finite(lo_hi[1]) is not None:
            lo, hi = lo_hi
            if lo <= price_k < hi or (key == "tang" and price_k == hi):
                return name
    return "ngoài dải"


def zone_label(price_k, vung):
    z = zone_of(price_k, vung)
    for key in ("giam", "chuyen_duoi", "co_so", "chuyen_tren", "tang"):
        lo_hi = as_list(vung.get(key))
        if len(lo_hi) == 2 and lo_hi[0] <= (price_k or -1) < lo_hi[1]:
            return "%s %s–%sk" % (z, fmt_vn(lo_hi[0], 1), fmt_vn(lo_hi[1], 1))
    return z


# ── Live computation ─────────────────────────────────────────────────────────


class Live:
    """Every live number of the weekly block, computed once and shared by the page, CSV and charts."""

    def __init__(self, kho, prof, iss, tham_so_mode, warnings, lich=None, lich_cho=None):
        self.kho = kho
        self.lich = lich or {}            # annex stakes {sym: [(from_day, stake, meta)]} by day
        self.lich_cho = lich_cho or []    # pending annex stakes [(sym, day, stake, meta)], not applied
        self.prof = prof
        self.iss = iss
        self.warnings = warnings
        tdt = as_dict(prof.get("theo_doi_tuan"))
        self.ts = as_dict(tdt.get("tham_so"))
        self.vung = as_dict(self.ts.get("vung_gia_k"))
        self.weights = {s: finite(as_dict(self.ts.get("so_huu")).get(s)) for s in CHILDREN}
        self.msr_before = self._msr_history_weight()
        self.msn_shares = finite(self.ts.get("so_cp_msn"))
        self.msn_break = kho.share_break("MSN")
        d, c = kho.closes("MSN")
        vols = kho.nen.get("MSN", {}).get("kl", [])
        self.data_to = d[-1] if d else None
        self.weeks = weeks_of(d, c, vols)
        self.complete = [w for w in self.weeks if w["fri"] <= self.data_to]
        self.open = self.weeks[-1] if self.weeks and self.weeks[-1]["fri"] > self.data_to else None
        self.params = self._pb_params(tham_so_mode)
        self.ok = self.data_to is not None
        if not self.ok:
            warnings.append("Không có nến MSN trong kho giá — khối LIVE hiển thị [CẦN DATA].")
            return
        self._current()
        self._ratio_history()
        self._signals()

    # ── parameters ──

    def _msr_history_weight(self):
        """Profile's time-varying MSR weight for the weekly ratio history (ty_le_theo_tuan.so_huu_gia_dinh)."""
        gd = as_dict(as_dict(as_dict(self.prof.get("phan_II")).get("ty_le_theo_tuan")).get("so_huu_gia_dinh"))
        for k, v in gd.items():
            m = re.fullmatch(r"MSR_truoc_(\d{2})_(\d{2})_(\d{4})", k)
            if m and finite(v) is not None:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1))), float(v)
        return None

    def weight_entry(self, sym, d):
        """Annex entry (from_day, stake, meta) in force for sym at d, else None (the profile stake applies)."""
        sched = self.lich.get(sym)
        if not sched or d is None:
            return None
        i = bisect.bisect_right([t[0] for t in sched], d) - 1
        return sched[i] if i >= 0 else None

    def weight(self, sym, d):
        e = self.weight_entry(sym, d)
        if e:
            return e[1]
        if sym == "MSR" and self.msr_before and d < self.msr_before[0]:
            return self.msr_before[1]
        return self.weights.get(sym)

    def stakes_txt(self, d):
        """"MCH 69,4% (bổ sung từ 06/10) · MSR 87,46% (bổ sung từ 01/10) · TCB 14,8%": the LT stakes at d."""
        parts = []
        for s in CHILDREN:
            w, e = self.weight(s, d), self.weight_entry(s, d)
            parts.append("%s %s%s" % (s, share_txt(w) if w is not None else CAN,
                                      " (bổ sung từ %s)" % ddmm(e[0]) if e else ""))
        return " · ".join(parts)

    def _pb_params(self, mode):
        prof = {"mu": finite(self.ts.get("pb_mu")), "sd": finite(self.ts.get("pb_sd")),
                "bvps": finite(self.ts.get("bvps")), "nguon": "hồ sơ %s" % ddmm(self.iss.pday), "engine": False}
        pb = as_dict(as_dict(as_dict(as_dict(self.kho.hhp).get("by_ticker")).get("MSN")).get("pb"))
        eng = {"mu": finite(pb.get("mean")), "sd": finite(pb.get("sd")), "bvps": finite(pb.get("per_share")),
               "nguon": "%s %s" % (SRC_HHP, stamp_txt(self.kho.hhp_gen) or "?"), "engine": True}
        eng_ok = all(eng[k] for k in ("mu", "sd", "bvps"))
        if mode == "ho_so" or not eng_ok:
            if mode != "ho_so":
                self.warnings.append("Engine HHP không có μ/σ/BVPS của MSN — σ-band dùng tham số hồ sơ "
                                     "(μ %s · σ %s · BVPS %s)." % (fmt_vn(prof["mu"]), fmt_vn(prof["sd"]),
                                                                   fmt_vn(prof["bvps"], 0)))
            chosen, other = prof, (eng if eng_ok else None)
        else:
            chosen, other = eng, prof
        if other and any(abs((chosen[k] or 0) - (other[k] or 0)) > (1 if k == "bvps" else PARAM_TOL)
                         for k in ("mu", "sd", "bvps")):
            self.warnings.append("Tham số P/B lệch giữa %s (μ %s · σ %s · BVPS %s) và %s (μ %s · σ %s · BVPS %s) "
                                 "— tab dùng %s." % (chosen["nguon"], fmt_vn(chosen["mu"]), fmt_vn(chosen["sd"]),
                                                     fmt_vn(chosen["bvps"], 0), other["nguon"],
                                                     fmt_vn(other["mu"]), fmt_vn(other["sd"]),
                                                     fmt_vn(other["bvps"], 0), chosen["nguon"]))
        return chosen

    def pb_at(self, price_vnd, d=None):
        """(P/B, σ) of a price; BVPS from the HHP weekly series at d when given, else the chosen BVPS."""
        p = self.params
        bv = p["bvps"]
        s = self.kho.pb_series
        if d is not None and s and s["d"]:
            _, b = asof(s["d"], s["base_k"], d)
            if b:
                bv = b * 1000.0
        if not bv or not p["mu"] or not p["sd"] or price_vnd is None:
            return None, None
        pb = price_vnd / bv
        return pb, (pb - p["mu"]) / p["sd"]

    # ── current state ──

    def lt(self, d):
        """(look-through đồng, {sym: (mcap, weight, day)}) at the last session ≤ d."""
        total, parts = 0.0, {}
        for s in CHILDREN:
            m, day = self.kho.mcap(s, d)
            w = self.weight(s, day or d)
            if m is None or w is None:
                return None, parts
            parts[s] = (m, w, day)
            total += w * m
        return total, parts

    def ratio(self, d, shares=None):
        lt, _ = self.lt(d)
        m, _ = self.kho.mcap("MSN", d, shares or self.msn_shares, self.msn_break)
        return (m / lt) if (lt and m) else None

    def _current(self):
        kho, d = self.kho, self.data_to
        _, cc = kho.closes("MSN")
        self.close = cc[-1]
        self.src_last = kho.nen["MSN"]["src"][-1]
        lw = self.complete[-1] if self.complete else None
        pw = self.complete[-2] if len(self.complete) > 1 else None
        self.last_week = lw
        # The week the current point is compared with: the last closed week midweek, the one before it when
        # the current point closes a week itself (Saturday run / --den on a Friday).
        self.ref_week = lw if self.open else pw
        self.week_chg = (lw["close"] / pw["close"] - 1) * 100 if lw and pw else None
        self.vs_week = (self.close / self.ref_week["close"] - 1) * 100 if self.ref_week else None
        self.kl_ratio = vol_ratio(self.complete, len(self.complete) - 1) if lw else None
        base = mean([w["kl"] for w in self.complete[-TB_WEEKS:]]) if len(self.complete) >= TB_WEEKS else None
        self.open_ratio = (self.open["kl"] / base) if (self.open and base) else None
        self.lt_now, self.lt_parts = self.lt(d)
        self.mcap_msn, _ = kho.mcap("MSN", d, self.msn_shares, self.msn_break)
        self.ratio_now = (self.mcap_msn / self.lt_now) if (self.mcap_msn and self.lt_now) else None
        loc = kho.shares.get("MSN", (None, None))
        self.local_shares = loc[0]
        self.ratio_local = (self.close * loc[0] / self.lt_now) if (loc[0] and self.lt_now) else None
        if self.msn_shares and loc[0] and abs(self.msn_shares / loc[0] - 1) > SHARE_GAP:
            self.warnings.append(
                "Số cp MSN: hồ sơ %s triệu (%s) khác vnstore/Vietcap %s triệu (cập nhật %s) %s — X3/P5 dùng số "
                "của hồ sơ: MSN/LT %s; theo số local là %s." % (
                    fmt_vn(self.msn_shares / 1e6, 1), nfc(self.ts.get("so_cp_msn_nguon")) or "hồ sơ",
                    fmt_vn(loc[0] / 1e6, 1), (loc[1] or "?")[:10], pct_txt((self.msn_shares / loc[0] - 1) * 100),
                    x_txt(self.ratio_now), x_txt(self.ratio_local)))
        self.lt_prev = self.lt(self.ref_week["last"])[0] if self.ref_week else None
        self.pb, self.sigma = self.pb_at(self.close)
        p = self.params
        self.band_m1 = p["bvps"] * (p["mu"] - p["sd"]) if p["bvps"] and p["mu"] and p["sd"] else None
        self.band_mu = p["bvps"] * p["mu"] if p["bvps"] and p["mu"] else None
        self.zone = zone_of(self.close / 1000.0, self.vung)
        # X1 note: highest complete weekly close since 05/2026.
        hi = [w for w in self.complete if w["fri"] >= X1_HIGH_FROM]
        self.x1_high = max(hi, key=lambda w: w["close"]) if hi else None
        # Session tile: last session vs previous, volume vs 20 previous sessions, foreign net from gia_moi.
        vols = kho.nen["MSN"]["kl"]
        self.sess_chg = (cc[-1] / cc[-2] - 1) * 100 if len(cc) > 1 else None
        self.sess_kl = vols[-1]
        base_s = mean(vols[-TB_SESSIONS - 1:-1]) if len(vols) > TB_SESSIONS else None
        self.sess_kl_ratio = vols[-1] / base_s if base_s else None
        self.kl20_year = (mean(vols[-TB_SESSIONS:]) / mean(vols[-YEAR_SESSIONS:])
                          if len(vols) >= YEAR_SESSIONS and mean(vols[-YEAR_SESSIONS:]) else None)
        gm = kho.gia_moi.get("MSN")
        self.sess_nn = None
        if gm and parse_day(gm.get("ngay")) == d and finite(gm.get("nn_mua_gt")) is not None \
                and finite(gm.get("nn_ban_gt")) is not None:
            self.sess_nn = gm["nn_mua_gt"] - gm["nn_ban_gt"]
        vd, vc = kho.vni()
        self.vni_day, self.vni = asof(vd, vc, d)
        i = bisect.bisect_right(vd, d) - 1
        self.vni_chg = (vc[i] / vc[i - 1] - 1) * 100 if i > 0 else None

    def _ratio_history(self):
        """Weekly MSN ÷ look-through (complete weeks) since the first week all sources cover."""
        self.ratio_weeks = []
        prev_lt = None
        for w in self.complete:
            if w["fri"] < RATIO_FROM:
                continue
            lt, _ = self.lt(w["last"])
            m, _ = self.kho.mcap("MSN", w["last"], self.msn_shares, self.msn_break)
            r = (m / lt) if (lt and m) else None
            self.ratio_weeks.append({"fri": w["fri"], "last": w["last"], "lt": lt, "ratio": r, "lt_prev": prev_lt})
            prev_lt = lt
        vals = [x["ratio"] for x in self.ratio_weeks if x["ratio"] is not None]
        self.ratio_n = len(vals)
        self.ratio_median = statistics.median(vals) if vals else None
        if len(vals) >= 4:
            q = statistics.quantiles(vals, n=4)
            self.ratio_p25, self.ratio_p75 = q[0], q[2]
        else:
            self.ratio_p25 = self.ratio_p75 = None
        cur = self.ratio_now
        if self.open is None and self.ratio_weeks and self.ratio_weeks[-1]["ratio"] is not None:
            vals = vals[:-1]                              # the current point is itself a complete week
        self.ratio_pct_n = len(vals)
        self.ratio_pct_lower = (100.0 * sum(1 for v in vals if v > cur) / len(vals)) if (vals and cur) else None
        first = self.ratio_weeks[0]["fri"] if self.ratio_weeks else None
        if first and first > RATIO_FROM + timedelta(days=14):
            self.warnings.append("Chuỗi MSN/LT live chỉ bắt đầu từ %s (thiếu dữ liệu Vietcap trước đó) — "
                                 "phân vị tính trên %d tuần." % (ddmmyyyy(first), self.ratio_n))

    # ── signals ──

    def _signals(self):
        lw = self.last_week
        close_w = lw["close"] / 1000.0 if lw else None
        wk = "tuần %s" % ddmm(lw["last"]) if lw else ""
        self.sig = {}
        for r in self.iss.signals:
            bien, sid = r.get("bien"), r.get("id")
            phep, muc = r.get("phep"), finite(r.get("muc"))
            if bien == "msn_dong_tuan":
                v, val_in, note = close_w, "%s (%s)" % (k_txt(lw["close"]) if lw else CAN, wk), ""
                if sid == "X1" and self.x1_high:
                    note = "Tuần đóng cao nhất từ %s: %s (%s) · vnstore" % (
                        "%02d/%d" % (X1_HIGH_FROM.month, X1_HIGH_FROM.year), k_txt(self.x1_high["close"], 1),
                        ddmm(self.x1_high["last"]))
            elif bien == "kl_tuan_tb20":
                v = self.kl_ratio
                val_in, note = "%s (%s)" % (x_txt(v), wk), "Tổng KL các phiên trong tuần ÷ TB 20 tuần trước · vnstore"
                if self.open and self.open_ratio is not None:
                    note += " · tuần đang mở (%d phiên): %s" % (self.open["n"], x_txt(self.open_ratio))
            elif bien == "msn_lt":
                v = self.ratio_now
                val_in = "%s (%s)" % (x_txt(v), ddmm(self.data_to))
                note = "Vốn hóa giá thô × tỷ lệ sở hữu %s · số cp MSN %s triệu" % (
                    ("hồ sơ/bổ sung: " + self.stakes_txt(self.data_to)) if self.lich else "hồ sơ",
                    fmt_vn((self.msn_shares or 0) / 1e6, 1))
            else:
                continue
            hit = compare(v, phep, muc)
            if sid == "P5" and hit:
                up = self.lt_now is not None and self.lt_prev is not None and self.lt_now > self.lt_prev
                hit = up
                note += " · LT %s so với tuần %s" % ("tăng" if up else "không tăng",
                                                    ddmm(self.ref_week["last"]) if self.ref_week else "?")
            elif sid == "P5":
                note += " · chỉ xét khi LT tăng so với tuần trước"
            loai = r.get("loai")
            if hit is None:
                st = CAN
            elif loai == "xac_nhan":
                st = "Đạt" if hit else "Chưa"
            else:
                st = "Kích hoạt" if hit else "An toàn"
            note = note or nfc(r.get("ghi_chu"))
            self.sig[sid] = {"v": v, "gia_tri_in": val_in, "trang_thai": st, "ghi_chu": note, "hit": bool(hit)}

    def counts(self, rows_hit):
        """(x met, x total, p triggered, p total, [ids waiting])."""
        xs = [r for r in self.iss.signals if r.get("loai") == "xac_nhan"]
        ps = [r for r in self.iss.signals if r.get("loai") == "phu_dinh"]
        xm = sum(1 for r in xs if rows_hit.get(r.get("id")))
        pm = sum(1 for r in ps if rows_hit.get(r.get("id")))
        wait = [r.get("id") for r in ps if r.get("id") not in self.sig and "chờ" in nfc(r.get("trang_thai")).lower()]
        return xm, len(xs), pm, len(ps), wait

    def issue_hits(self):
        """Issue-sourced signals whose status says they fired (never inferred from live data)."""
        return {r.get("id"): status_mau(r.get("trang_thai")) == "do"
                for r in self.iss.signals if r.get("id") not in self.sig}

    def action(self, x1, x2, p1):
        """Rule-based pick of the PROFILE's own sizing text (no new advice). The 8% branch keeps the dossier's
        own caveat: it conflicts with hard rule #10 and awaits the owner's decision (hanh_dong.xung_dot_luat).
        Default mode "dong_bang": the dossier's base text only, labelled FROZEN, whatever the signals say."""
        sz = as_dict(as_dict(self.prof.get("theo_doi_tuan")).get("sizing_may"))
        base = nfc(as_dict(as_dict(self.prof.get("theo_doi_tuan")).get("tuan_goc")).get("hanh_dong")) or CAN
        if hanh_dong_mode() == HANH_DONG_DONG_BANG:
            return "%s: %s" % (DONG_BANG_NHAN % ddmm(self.iss.pday), base), "xam"
        if p1:
            return "P1 kích hoạt → hạ về %s%% NAV (luật hồ sơ)" % fmt_vn(sz.get("stop_ha_ve_pct"), 0), "do"
        if x1 and x2:
            q3 = any(r.get("id") == "C2" and status_mau(r.get("trang_thai")) == "xanh" for r in self.iss.catalysts)
            cap = fmt_vn(sz.get("tran_nav_conviction4_pct"), 0)
            caveat = (" — hồ sơ ghi nhánh này còn xung đột luật, chờ quyết (mục Hành động)"
                      if nfc(as_dict(self.prof.get("hanh_dong")).get("xung_dot_luat")) else "")
            if q3:
                return "%s · X1 + X2 + Q3 đạt: luật hồ sơ cho khôi phục %s%% NAV%s" % (base, cap, caveat), "vang"
            return "%s · X1 + X2 đạt; luật hồ sơ chờ Q3 xác nhận cho nhánh %s%%%s" % (base, cap, caveat), "vang"
        return base, "xam"


# ── Page: gate + weekly LIVE block ───────────────────────────────────────────


def section_cong(prof, pday, live, meta_line):
    cong = as_dict(prof.get("cong"))
    chips = [{"tier": nfc(r.get("tier")), "text": nfc(r.get("mo_ta"))}
             for r in as_list(prof.get("tang_bang_chung")) if isinstance(r, dict)]
    khoi = [
        doan(" · ".join(x for x in (nfc(prof.get("lap_luc")), nfc(prof.get("nguon_gia")),
                                   nfc(prof.get("engine_hhp")), nfc(prof.get("phan_phoi"))) if x), mau=None),
        {"kieu": "cong", "dong": nfc(cong.get("dong")) or CAN, "tier": "EST",
         "phu": "Cổng của hồ sơ %s — không tự tính lại" % ddmmyyyy(pday)},
        doan(cong.get("ket_luan_mot_dong"), mau="vang", the=True, tieu_de="Kết luận một dòng · hồ sơ %s" % ddmm(pday))
        if nfc(cong.get("ket_luan_mot_dong")) else None,
        {"kieu": "chips", "chips": chips} if chips else None,
        doan(meta_line, mau="lam"),
        doan(prof.get("ghi_chu_ngay")),
    ]
    return sec("cong", prof.get("tieu_de") or "Hồ sơ độ trễ MSN", khoi, eyebrow=prof.get("eyebrow"),
               lede=prof.get("phu_de"))


def live_tiles(lv, pday):
    tg = as_dict(as_dict(lv.prof.get("theo_doi_tuan")).get("tuan_goc"))
    lw, rw = lv.last_week, lv.ref_week
    p = lv.params
    t1 = tile("MSN · đóng cửa", k_txt(lv.close),
              "%s%s · tuần %s: %s (nay %s so với tuần đó) · hồ sơ %s: %s" % (
                  ddmm(lv.data_to), " (bảng điện, giá thô)" if lv.src_last == "vci_board" else "",
                  ddmm(rw["last"]) if rw else "?", k_txt(rw["close"]) if rw else CAN, pct_txt(lv.vs_week),
                  ddmm(parse_day(tg.get("ngay"))), fmt_vn(tg.get("msn"), 2)),
              tier=T_DATA, live=True)
    pct = lv.ratio_pct_lower
    t2 = tile("MSN ÷ look-through", x_txt(lv.ratio_now),
              "LT %s nghìn tỷ · trung vị từ 01/2024: %s · thấp hơn %s số tuần · ngưỡng xác nhận > 0,60× · hồ sơ: %s" % (
                  nghin_ty(lv.lt_now), x_txt(lv.ratio_median),
                  (fmt_vn(pct, 0) + "%") if pct is not None else CAN, x_txt(tg.get("msn_lt"))),
              mau="do" if (lv.ratio_now or 1) < 0.45 else ("xanh" if (lv.ratio_now or 0) > 0.6 else None),
              tier=T_EST, live=True)
    t3 = tile("P/B · σ-band", x_txt(lv.pb),
              "%s · −1σ = %sk · μ = %sk · %s (μ %s · σ %s · BVPS %s) · hồ sơ: %s %s" % (
                  sigma_txt(lv.sigma), k_txt(lv.band_m1, 1), k_txt(lv.band_mu, 1), p["nguon"], fmt_vn(p["mu"]),
                  fmt_vn(p["sd"]), fmt_vn(p["bvps"], 0), x_txt(tg.get("pb")), sigma_txt(tg.get("sigma"))),
              tier=T_EST, live=True)
    op = ""
    if lv.open and lv.open_ratio is not None:
        op = " · tuần đang mở (%d phiên): %s" % (lv.open["n"], x_txt(lv.open_ratio))
    t4 = tile("KL tuần ÷ TB 20 tuần", x_txt(lv.kl_ratio),
              "tuần %s · ngưỡng xác nhận ≥ 1,5×%s" % (ddmm(lw["last"]) if lw else "?", op),
              mau="xanh" if (lv.kl_ratio or 0) >= 1.5 else None, tier=T_DATA, live=True)
    nn = (" · khối ngoại ròng %s" % ty_txt(lv.sess_nn)) if lv.sess_nn is not None else ""
    t5 = tile("MSN · phiên %s" % ddmm(lv.data_to), pct_txt(lv.sess_chg),
              "%s; KL %s triệu cp (%s TB 20 phiên)%s; VN-Index %s (%s)" % (
                  k_txt(lv.close), fmt_vn(lv.sess_kl / 1e6, 1), x_txt(lv.sess_kl_ratio), nn,
                  fmt_vn(lv.vni, 2), pct_txt(lv.vni_chg)),
              mau="xanh" if (lv.sess_chg or 0) > 0 else ("do" if (lv.sess_chg or 0) < 0 else None),
              tier=T_DATA, live=True)
    x1, x2 = lv.sig.get("X1", {}).get("hit"), lv.sig.get("X2", {}).get("hit")
    act, mau = lv.action(x1, x2, lv.sig.get("P1", {}).get("hit"))
    t6 = tile("Vùng giá · luật hồ sơ (đóng băng)" if hanh_dong_mode() == HANH_DONG_DONG_BANG else "Vùng giá · hành động",
              zone_label(lv.close / 1000.0, lv.vung), act, mau=mau,
              tier=nfc(lv.ts.get("vung_gia_tier")) or T_EST, live=True)
    return [t1, t2, t3, t4, t5, t6]


def signal_rows(lv):
    rows = []
    for r in lv.iss.signals:
        sid = r.get("id")
        s = lv.sig.get(sid)
        if s:
            val = cell(s["gia_tri_in"], mono=True)
            st = pill(s["trang_thai"], "xanh" if s["trang_thai"] in ("Đạt", "An toàn") else
                      ("do" if s["trang_thai"] == "Kích hoạt" else "xam"))
            note = "LIVE · %s · %s" % (T_DATA if r.get("bien") != "msn_lt" else T_EST, s["ghi_chu"])
        else:
            val = cell("%s · hồ sơ %s" % (nfc(r.get("gia_tri_in")) or CAN, r.get("as_of")), mono=True)
            st = pill(r.get("trang_thai"), MAU_PROFILE.get(r.get("mau")) or status_mau(r.get("trang_thai")))
            note = "%s · %s" % (nfc(r.get("tier")) or "—", nfc(r.get("ghi_chu")))
        rows.append([cell(sid, dam=True), nfc(r.get("ten")), cell(nfc(r.get("nguong")), mono=True), val, st, note])
    return rows


def catalyst_rows(lv):
    rows = []
    for r in lv.iss.catalysts:
        cid = r.get("id")
        dk, st, mau = nfc(r.get("dieu_kien")), nfc(r.get("trang_thai")), MAU_PROFILE.get(r.get("mau"))
        if cid == "C5" and lv.ok:
            dk, st, mau = c5_live(lv, r)
        elif cid == "C4" and lv.ok:
            san = lv.kho.san.get("MSR")
            if san:
                dk = "%s · LIVE: MSR đang niêm yết %s (vnstore)" % (dk, san)
                if san.upper() == "HOSE":
                    st, mau = "Đạt (lên HOSE)", "xanh"
        # C5 is fully live; C4 is live for the listing venue only, its status stays issue-sourced → keep as-of.
        rows.append([cell("%s · %s" % (cid, nfc(r.get("ten"))), dam=True), nfc(r.get("moc")),
                     "%s%s" % (dk, "" if (cid == "C5" and lv.ok) else " · hồ sơ %s" % r.get("as_of")),
                     pill(st or CAN, mau or status_mau(st))])
    return rows


def weekly_foreign(lv, n=4):
    """Foreign net value (đồng) of MSN per complete week, newest last (Vietcap foreignNetValueTotal)."""
    vc = lv.kho.vc.get("MSN")
    if not vc:
        return []
    out = []
    for w in lv.complete[-n:]:
        lo = w["fri"] - timedelta(days=4)
        tot, seen = 0.0, False
        for d, nn in zip(vc["d"], vc["nn"]):
            if lo <= d <= w["fri"] and nn is not None:
                tot += nn
                seen = True
        out.append((w, tot if seen else None))
    return out


def c5_live(lv, r):
    muc = finite(r.get("muc_vnindex"))
    fw = weekly_foreign(lv)
    last = fw[-1] if fw else (None, None)
    buys = sum(1 for _, v in fw if v is not None and v > 0)
    vni_ok = compare(lv.vni, ">", muc)
    nn_ok = last[1] is not None and last[1] > 0
    parts = ["LIVE: VN-Index %s (%s)" % (fmt_vn(lv.vni, 2), ddmm(lv.vni_day))]
    if last[0]:
        parts.append("khối ngoại MSN tuần %s: %s; mua ròng %d/%d tuần gần nhất" % (
            ddmm(last[0]["last"]), ty_txt(last[1]), buys, len(fw)))
    if lv.sess_nn is not None:
        parts.append("phiên %s: %s" % (ddmm(lv.data_to), ty_txt(lv.sess_nn)))
    st = CAN if vni_ok is None else ("Đạt" if (vni_ok and nn_ok) else "Chưa")
    return " · ".join(parts), st, "xanh" if st == "Đạt" else "xam"


def log_rows(lv):
    """26 complete weeks + the open week (newest first) + the profile's own log rows, by date."""
    kho, vung = lv.kho, lv.vung
    rows = []
    idx = {w["fri"]: i for i, w in enumerate(lv.complete)}
    ratio_by = {x["fri"]: x for x in lv.ratio_weeks}
    weeks = lv.complete[-LOG_WEEKS:]
    if lv.open:
        weeks = weeks + [lv.open]
    iss_hits = lv.issue_hits()
    for w in weeks:
        is_open = w is lv.open
        i = idx.get(w["fri"])
        prev = lv.complete[i - 1] if (i is not None and i > 0) else (lv.complete[-1] if is_open else None)
        chg = (w["close"] / prev["close"] - 1) * 100 if prev else None
        vr = vol_ratio(lv.complete, i) if i is not None else lv.open_ratio
        closes = []
        for s in CHILDREN:
            _, c = asof(*kho.closes(s), w["last"])
            closes.append(k_txt(c))
        _, vni = asof(*kho.vni(), w["last"])
        if is_open:
            lt, ratio, lt_prev = lv.lt_now, lv.ratio_now, lv.lt_prev
        else:
            rw = ratio_by.get(w["fri"])
            lt, ratio, lt_prev = (rw["lt"], rw["ratio"], rw["lt_prev"]) if rw else (lv.lt(w["last"])[0], None, None)
        pb, sg = lv.pb_at(w["close"], w["last"])
        ck = w["close"] / 1000.0
        hits = {}
        for r in lv.iss.signals:
            sid, bien = r.get("id"), r.get("bien")
            if bien in ("msn_dong_tuan", "kl_tuan_tb20", "msn_lt"):
                v = {"msn_dong_tuan": ck, "kl_tuan_tb20": vr, "msn_lt": ratio}[bien]
                h = compare(v, r.get("phep"), finite(r.get("muc")))
                if sid == "P5" and h:
                    h = lt is not None and lt_prev is not None and lt > lt_prev
                hits[sid] = bool(h)
        full = w["fri"] >= lv.iss.pday
        if full:
            hits.update(iss_hits)
        xm, xn, pm, pn, _ = lv.counts(hits)
        xp = "X %d/%d · P %d/%d%s%s" % (xm, xn, pm, pn, "" if full else "*", " (tạm)" if is_open else "")
        act, mau = lv.action(hits.get("X1") and not is_open, hits.get("X2") and not is_open,
                             hits.get("P1") and not is_open)
        label = "%s%s" % (ddmmyyyy(w["last"]), " · đang mở (%d phiên)" % w["n"] if is_open else "")
        rows.append((w["last"], [
            cell(label, dam=is_open), cell("%s · %s" % (k_txt(w["close"]), pct_txt(chg)), mono=True),
            cell(x_txt(vr), mono=True, mau="xanh" if (vr or 0) >= 1.5 else None),
            cell(" · ".join(closes), mono=True), cell(fmt_vn(vni, 2), mono=True),
            cell("%s · %s" % (nghin_ty(lt), x_txt(ratio)), mono=True),
            cell("%s · %s" % (x_txt(pb), sigma_txt(sg)), mono=True),
            pill(zone_of(ck, vung), {"Giảm": "do", "Tăng": "xanh", "Cơ sở": "lam"}.get(zone_of(ck, vung), "xam")),
            cell(xp, mono=True), cell(act, mau=mau)]))
    for r in as_list(as_dict(lv.prof.get("theo_doi_tuan")).get("nhat_ky")):
        d = parse_day(as_dict(r).get("ngay"))
        if not d or (lv.data_to and d > lv.data_to):
            continue
        rows.append((d, [cell("%s · hồ sơ" % nfc(r.get("tuan")), mau="xam"), cell(nfc(r.get("msn_in")), mono=True),
                         cell(nfc(r.get("kl_tb20_in")) or "—", mono=True),
                         cell(nfc(r.get("mch_msr_tcb_in")), mono=True), cell(nfc(r.get("vnindex_in")), mono=True),
                         cell(nfc(r.get("lt_in")), mono=True), cell(nfc(r.get("pb_in")), mono=True),
                         pill(nfc(r.get("vung")), "xam"), cell(nfc(r.get("x_p")), mono=True, tip=r.get("ghi_chu_trich")),
                         cell(nfc(r.get("hanh_dong")), mau="xam")]))
    rows.sort(key=lambda t: t[0], reverse=True)
    return [r for _, r in rows]


def section_theo_doi(prof, pday, lv, iss, charts, warnings):
    tdt = as_dict(prof.get("theo_doi_tuan"))
    tg = as_dict(tdt.get("tuan_goc"))
    p = lv.params
    lede = ("Khối LIVE — tính lại từ kho dữ liệu trên máy mỗi lần mở tab hoặc bấm FETCH, không chờ lịch %s. "
            "Giá tuần = đóng cửa phiên cuối tuần (vnstore, giá điều chỉnh); vốn hóa = giá thô × số cổ phiếu "
            "(Vietcap), tỷ lệ sở hữu theo hồ sơ (đổi theo ngày khi có bản bổ sung), số cp MSN theo hồ sơ; "
            "σ-band theo %s. Các phần bên dưới giữ nguyên "
            "bản gốc hồ sơ %s để đối chiếu." % (nfc(tdt.get("lich_chay")) or "thứ Bảy", p["nguon"], ddmmyyyy(pday)))
    khoi = [doan(tg.get("text"), mau="xam", the=True, tieu_de=nfc(tg.get("nhan")) or "Tuần gốc")]
    if lv.ok:
        xm, xn, pm, pn, wait = lv.counts({**{k: v["hit"] for k, v in lv.sig.items()}, **lv.issue_hits()})
        status = "Dữ liệu đến %s (%s) · tuần gần nhất đã đóng: %s%s · xác nhận %d/%d · phủ định %d/%d%s" % (
            ddmmyyyy(lv.data_to), "bảng điện, giá thô" if lv.src_last == "vci_board" else "lịch sử",
            ddmmyyyy(lv.last_week["last"]) if lv.last_week else CAN,
            " · tuần %s đang mở (%d phiên)" % (ddmm(lv.open["fri"]), lv.open["n"]) if lv.open else "",
            xm, xn, pm, pn, (" (%s chờ hồ sơ)" % ", ".join(wait)) if wait else "")
        khoi += [doan(status, mau="lam"), o_so(live_tiles(lv, pday), cot=3)]
    else:
        khoi.append(doan("%s — kho giá không có nến MSN; khối LIVE không tính được." % CAN, mau="do"))
    khoi += [heading(nfc(tdt.get("tin_hieu_nhan")) or "Tín hiệu"),
             bang(["#", "Tín hiệu", "Ngưỡng", "Giá trị gần nhất", "Trạng thái", "Nguồn · ghi chú"],
                  signal_rows(lv) if lv.ok else [],
                  "X1–X3, P1, P5 tính LIVE; P2–P4, P6 lấy từ hồ sơ/bản tuần kèm ngày. Ngưỡng là trường máy của hồ sơ."),
             bang(["Chất xúc tác", "Mốc dự kiến", "Điều kiện cho kịch bản tăng", "Trạng thái"], catalyst_rows(lv),
                  "C4 (sàn niêm yết MSR) và C5 (VN-Index, khối ngoại MSN) đối chiếu LIVE; còn lại theo hồ sơ.")]
    khoi += charts
    if lv.ok:
        khoi += [heading("Nhật ký tuần · mới nhất ở trên · tính lại từ dữ liệu"),
                 bang(as_list(tdt.get("nhat_ky_cot")) or ["Tuần"], log_rows(lv),
                      "%d tuần đã đóng gần nhất + tuần đang mở; dòng \"hồ sơ\" là bản ghi nguyên văn của hồ sơ. "
                      "* Tuần trước ngày hồ sơ: P2–P4, P6 không có lịch sử, chỉ đếm P1, P5. Hành động chọn theo "
                      "luật từ chính văn bản sizing của hồ sơ." % LOG_WEEKS)]
    khoi += [doan(tdt.get("cach_tinh"), mau=None),
             stake_note(lv),
             canh_bao("Cảnh báo dữ liệu live", warnings),
             heading("Việc còn treo · %s" % ("bản tuần %s" % ddmm(iss.tday) if iss.tday else "hồ sơ %s" % ddmm(pday))),
             bang(["Việc", "Cần gì", "Trạng thái", "Cập nhật"],
                  [[nfc(v.get("viec")), nfc(v.get("can_gi")), pill(v.get("trang_thai")), nfc(v.get("cap_nhat"))]
                   for v in iss.viec_treo if isinstance(v, dict)]),
             heading("Synthesis tuần · %s" % iss.synthesis_ky),
             danh_sach([{"so": str(i + 1), "text": nfc(t)} for i, t in enumerate(iss.synthesis) if nfc(t)]),
             doan(tdt.get("trang_thai_chay"), mau="xam")]
    return sec("theo_doi_tuan", nfc(tdt.get("tieu_de")) or "MSN tuần này", khoi,
               eyebrow="%s · LIVE" % (nfc(tdt.get("nhan")) or "Theo dõi tuần"), lede=lede)


# ── Page: top tiles ──────────────────────────────────────────────────────────


def section_o_so_dau(prof, lv):
    prof_tiles = [t for t in as_list(prof.get("tiles_dau")) if isinstance(t, dict)]
    hhp = as_dict(lv.kho.hhp)
    gen = stamp_txt(lv.kho.hhp_gen) or "?"
    idx = as_dict(hhp.get("index"))
    ex = as_dict(hhp.get("exvic3"))
    out = []
    for t in prof_tiles:
        nhan = nfc(t.get("nhan"))
        prof_txt = "hồ sơ: %s" % nfc(t.get("gia_tri"))
        low = nhan.lower()
        live_t = None
        if low.startswith("p/e vn-index") and as_dict(idx.get("pe")).get("now") is not None:
            pe, pb = as_dict(idx.get("pe")), as_dict(idx.get("pb"))
            stale = pe.get("stale") or pb.get("stale")
            live_t = tile("P/E VN-Index · engine %s" % gen, x_txt(pe.get("now")),
                          "%s (μ %s · σ %s, as-of %s) · P/B %s · %s%s" % (
                              sigma_txt(pe.get("sigma")), fmt_vn(pe.get("mean")), fmt_vn(pe.get("sd")),
                              ddmm(parse_day(pe.get("as_of"))), fmt_vn(pb.get("now")), prof_txt,
                              " · engine đánh dấu stale" if stale else ""),
                          mau="vang" if stale else None, tier="FACT-T2", live=True)
        elif low.startswith("p/e ex-vin") and ex.get("pe_exv3_now") is not None:
            lows = exvic_lows(ex)
            live_t = tile("P/E ex-Vin3 · engine %s" % gen, x_txt(ex.get("pe_exv3_now")),
                          "%s · μ %s · σ %s · đáy 2022: %s · Covid: %s · %s%s" % (
                              sigma_txt(ex.get("exv3_pe_sigma")), fmt_vn(ex.get("exv3_pe_mean")),
                              fmt_vn(ex.get("exv3_pe_sd")), x_txt(lows[0]), x_txt(lows[1]), prof_txt,
                              " · engine đánh dấu stale" if ex.get("stale") else ""),
                          mau="vang" if ex.get("stale") else None, tier="FACT-T2", live=True)
        elif low.startswith("tỷ trọng họ vin") and ex.get("w3_now") is not None:
            vic = next((v for v in as_list(ex.get("vic3")) if as_dict(v).get("ticker") == "VIC"), {})
            live_t = tile("Tỷ trọng họ Vin · engine %s" % gen, fmt_vn(ex.get("w3_now"), 1, fixed=True) + "%",
                          "VIC+VHM+VRE trong vốn hóa · P/E VIC ≈ %s× · %s%s" % (
                              fmt_vn(vic.get("pe"), 0), prof_txt, " · engine đánh dấu stale" if ex.get("stale") else ""),
                          mau="vang" if ex.get("stale") else None, tier="FACT-T2", live=True)
        elif low.startswith("độ rộng định giá") and hhp.get("by_ticker"):
            zones = [as_dict(as_dict(v).get("pe")).get("zone") for v in as_dict(hhp.get("by_ticker")).values()]
            n = sum(1 for z in zones if z)
            re_ = sum(1 for z in zones if z and z.startswith("RẺ"))
            live_t = tile("Độ rộng định giá · engine %s" % gen, "%d/%d" % (re_, n),
                          "mã RẺ theo P/E (< −1σ) · %s — dùng như hướng" % prof_txt, tier=T_EST, live=True)
        elif low.startswith("msn · p/b") and lv.ok and lv.pb is not None:
            p = lv.params
            live_t = tile("MSN · P/B · %s" % ddmm(lv.data_to), x_txt(lv.pb),
                          "%s · BVPS %s · μ %s · σ %s (%s) · %s" % (
                              sigma_txt(lv.sigma), fmt_vn(p["bvps"], 0), fmt_vn(p["mu"]), fmt_vn(p["sd"]),
                              p["nguon"], prof_txt), tier=T_EST, live=True)
        elif low.startswith("msn ÷") and lv.ok and lv.ratio_now is not None:
            pct = lv.ratio_pct_lower
            live_t = tile("MSN ÷ giá trị cổ phần niêm yết · %s" % ddmm(lv.data_to), x_txt(lv.ratio_now),
                          "thấp hơn %s số tuần từ 01/2024 (n = %d) · trung vị %s · %s" % (
                              (fmt_vn(pct, 0) + "%") if pct is not None else CAN, lv.ratio_pct_n,
                              x_txt(lv.ratio_median), prof_txt), tier=T_EST, live=True)
        out.append(live_t or tile(nhan, nfc(t.get("gia_tri")), "%s · hồ sơ (không có nguồn live)" % nfc(t.get("ghi_chu")),
                                  tier=t.get("tier")))
    return sec("o_so_dau", "Ô số đầu", [o_so(out, cot=3),
                                        doan("Ô có nhãn LIVE đọc lại engine HHP / kho giá trên máy; dòng phụ giữ số "
                                             "của hồ sơ để đối chiếu.", mau="xam")],
               eyebrow="Ô số đầu · thị trường chung và MSN")


def exvic_lows(ex):
    """Lowest P/E ex-Vin3 in 2022–H1/2023 and in 2020 (engine series)."""
    ser = as_list(as_dict(ex.get("series")).get("pe_exv3"))
    out = []
    for lo, hi in ((date(2022, 1, 1), date(2023, 6, 30)), (date(2020, 1, 1), date(2020, 12, 31))):
        vals = [v for t, v in ser if finite(t) is not None and finite(v) is not None and lo <= ms_day(t) <= hi]
        out.append(min(vals) if vals else None)
    return out


# ── Page: dossier sections (verbatim from the profile) ───────────────────────


def section_keynotes(prof):
    k = as_dict(prof.get("keynotes"))
    items = [{"so": nfc(m.get("id")), "tieu_de": nfc(m.get("tieu_de")), "text": nfc(m.get("noi_dung")),
              "tags": tier_list(m.get("tier"))} for m in as_list(k.get("muc")) if isinstance(m, dict)]
    return sec("keynotes", nfc(k.get("phu_de")) or "Keynotes", [danh_sach(items)],
               eyebrow=nfc(k.get("tieu_de")) or "Keynotes")


def section_ba_dong_ho(prof):
    b = as_dict(prof.get("ba_dong_ho"))
    cards = [card("%s · %s" % (nfc(d.get("ten")), nfc(d.get("tom_tat"))), d.get("noi_dung"),
                  nhan=d.get("trang_thai"), mau_vien=status_mau(d.get("trang_thai")), tier=d.get("tier"))
             for d in as_list(b.get("dong_ho")) if isinstance(d, dict)]
    return sec("ba_dong_ho", b.get("tieu_de"), [
        the_block(cards, 3),
        doan(b.get("bac_hai_marks"), mau="tim", the=True, tieu_de="Tư duy bậc hai · Marks"),
        doan(b.get("nghich_dao_munger"), mau="do", the=True, tieu_de="Nghịch đảo · Munger")],
        eyebrow=b.get("nhan"), lede=b.get("mo_ta"))


def profile_series(prof, ref):
    """Profile chart series ("bieu_do.c1") → (iso dates, [(name, values)])."""
    key = nfc(ref).split(".")[-1] if ref else ""
    c = as_dict(as_dict(prof.get("bieu_do")).get(key))
    ds = [parse_dmy(x) for x in as_list(c.get("d"))]
    out = []
    for s in as_list(c.get("series")):
        s = as_dict(s)
        vals = as_list(s.get("v"))
        out.append((nfc(s.get("ten")) or "?", [finite(v) for v in vals]))
    return ds, out


SERIES_MAU = {"MSN": "amber", "MCH": "cyan", "MSR": "bull", "TCB": "info", "VN-Index": "dim", "VN30": "dim"}


def profile_chart(prof, meta, extra_ann=None, left="", cao=300):
    ds, ser = profile_series(prof, meta.get("series_ref"))
    if not ds or not ser or any(d is None for d in ds):
        return None
    x = [d.isoformat() for d in ds]
    series = [{"name": n, "y": [None if v is None else round(v, 4) for v in vals][:len(x)],
               "style": "line", "mau": SERIES_MAU.get(n, "dim")} for n, vals in ser]
    ann = list(extra_ann or [])
    last = ds[-1]
    for n, vals in ser:
        end = as_dict(meta.get("nhan_cuoi")).get(n)
        v = next((v for v in reversed(vals) if v is not None), None)
        if end is not None and v is not None:
            ann.append({"kind": "point", "x": day_ms(last), "y": round(v, 3), "text": "%s %s" % (n, fmt_vn(end, 0)),
                        "mau": SERIES_MAU.get(n, "dim"), "marker": "dot", "pos": "right", "uu_tien": 2})
    # The chart widget has no log axis: never let a profile title claim one.
    title = nfc(meta.get("tieu_de"))
    caption = nfc(meta.get("chu_thich") or meta.get("ghi_chu"))
    if "thang log" in title:
        title = re.sub(r"\s*\(thang log\)|thang log,\s*|,\s*thang log", "", title)
        caption = (caption + " " if caption else "") + "Hồ sơ vẽ thang log; khung này dùng thang tuyến tính."
    return {"kieu": "bieu_do", "tieu_de": title,
            "chu_thich": caption,
            "nguon": "%s · bản %s (dữ liệu nhúng trong hồ sơ)" % (nfc(meta.get("nguon")) or "VNDirect DCHART",
                                                                 nfc(prof.get("ho_so"))),
            "tier": nfc(meta.get("tier")) or "T1·DATA", "cao": cao,
            "block": {"x": x, "series": series, "left": {"label": left}, "annotations": ann}}


def chart_c1(prof):
    """Phần I: MSN weekly 2013→ from the profile, rally bands from its caption, labels at dated events."""
    meta = as_dict(as_dict(prof.get("phan_I")).get("bieu_do_msn"))
    ds, ser = profile_series(prof, meta.get("series_ref"))
    if not ds or not ser:
        return None
    vals = ser[0][1]
    labels = [nfc(x) for x in as_list(meta.get("nhan"))]
    dates = [parse_dmy(m.group(0)) for m in DMY_RE.finditer(nfc(meta.get("chu_thich")))]
    ann = []
    band_names = [lab for lab in labels if not DMY_RE.search(lab) and not lab.startswith("MSN")]
    for i in range(0, min(len(dates), 4) - 1, 2):
        if dates[i] and dates[i + 1] and i // 2 < len(band_names):
            ann.append({"kind": "xband", "x0": day_ms(dates[i]), "x1": day_ms(dates[i + 1]),
                        "text": band_names[i // 2], "mau": "amber", "alpha": 0.10})
    c3 = [parse_dmy(x) for x in as_list(as_dict(as_dict(prof.get("bieu_do")).get("c3")).get("d"))]
    if len(band_names) > 2 and c3 and c3[0]:
        ann.append({"kind": "xband", "x0": day_ms(c3[0]), "x1": day_ms(ds[-1]), "text": band_names[2],
                    "mau": "dim", "alpha": 0.10})
    for lab in labels:
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", lab)
        if not m:
            continue
        d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        i = min(bisect.bisect_left(ds, d), len(ds) - 1)
        if vals[i] is not None:
            ann.append({"kind": "point", "x": day_ms(ds[i]), "y": vals[i], "text": lab,
                        "mau": "bear" if "hụt" in lab or "đáy" in lab else "amber", "marker": "dot",
                        "pos": "below" if "đáy" in lab else "above", "uu_tien": 2})
    last_lab = next((lab for lab in labels if lab.startswith("MSN")), "")
    if last_lab and vals[-1] is not None:
        ann.append({"kind": "point", "x": day_ms(ds[-1]), "y": vals[-1], "text": last_lab, "mau": "amber",
                    "marker": "diamond", "pos": "right", "uu_tien": 1})
    b = profile_chart(prof, meta, ann, left="nghìn đồng (điều chỉnh)", cao=320)
    return b


def section_phan_1(prof):
    p = as_dict(prof.get("phan_I"))
    ev_cols = ["Mốc", "Sự kiện", "Nhãn"]
    khoi = [chart_c1(prof),
            profile_chart(prof, as_dict(p.get("bieu_do_dot1")), left="quy về 100"),
            profile_chart(prof, as_dict(p.get("bieu_do_dot2")), left="quy về 100"),
            bang(as_list(p.get("bang_cot")), [[cell(nfc(r[0]), dam=True)] + [nfc(c) for c in r[1:]]
                                               for r in as_list(p.get("bang")) if isinstance(r, list) and r],
                 p.get("bang_nguon")),
            heading("Chất xúc tác đợt 1 (2016–2018)"),
            bang(ev_cols, [[cell(nfc(e.get("moc")), mono=True), nfc(e.get("su_kien")), tier_cell(e.get("tier"))]
                           for e in as_list(p.get("xuc_tac_dot1")) if isinstance(e, dict)]),
            heading("Chất xúc tác đợt 2 (2020–2021)"),
            bang(ev_cols, [[cell(nfc(e.get("moc")), mono=True), nfc(e.get("su_kien")), tier_cell(e.get("tier"))]
                           for e in as_list(p.get("xuc_tac_dot2")) if isinstance(e, dict)]),
            o_so([tile(d.get("nhan"), nfc(d.get("gia_tri")), d.get("ghi_chu")) for d in as_list(p.get("do_tre"))
                  if isinstance(d, dict)], cot=3)]
    return sec("phan_1", p.get("tieu_de"), khoi, so="I", eyebrow="Phần I · Hai đợt tăng giá lịch sử",
               lede=p.get("ghi_chu_gia"))


def section_phan_2(prof, charts):
    p = as_dict(prof.get("phan_II"))
    lt_rows = [[cell(nfc(r["in"][0]), dam=True)] + [cell(nfc(c), mono=True) for c in r["in"][1:]]
               for r in as_list(p.get("look_through")) if isinstance(r, dict) and len(as_list(r.get("in"))) >= 4]
    if lt_rows:
        lt_rows.append([cell("Tổng look-through", dam=True), "", "", cell(nfc(p.get("look_through_tong_in")), mono=True,
                                                                           dam=True)])
        vh, tn = as_dict(p.get("von_hoa_msn")), as_dict(p.get("tru_no_rong"))
        lt_rows.append([nfc(vh.get("text")), "", "", cell(nfc(p.get("von_hoa_msn_in")), mono=True)])
        lt_rows.append([nfc(tn.get("text")), "", "", cell(nfc(p.get("tru_no_rong_in")), mono=True)])
    ttt = as_dict(p.get("ty_le_theo_tuan"))
    ftse = as_dict(p.get("ftse"))
    nbb = as_dict(p.get("nghich_dao_ben_ban"))
    khoi = charts + [
        bang(as_list(p.get("kqkd_cot")), [[cell(nfc(r[0]), dam=True)] + [cell(nfc(c), mono=True) for c in r[1:-1]]
                                           + [tier_cell(r[-1])] for r in as_list(p.get("kqkd")) if isinstance(r, list) and r]),
        {"kieu": "chips", "chips": [{"tier": t, "text": ""} for t in tier_list(p.get("mang_q2_tier"))]}
        if tier_list(p.get("mang_q2_tier")) else None,
        doan(p.get("mang_q2")),
        heading("Giá trị cổ phần niêm yết MSN nắm · bản %s" % nfc(prof.get("du_lieu_den"))),
        bang(as_list(p.get("look_through_cot")), lt_rows, p.get("look_through_ghi_chu"), can_phai=[1, 2, 3]),
        doan(ttt.get("ghi_chu"), mau=None),
        heading("Giá APT"),
        bang(as_list(p.get("apt_cot")), [[cell(nfc(r[0]), mono=True)] + [nfc(c) for c in r[1:]]
                                          for r in as_list(p.get("apt")) if isinstance(r, list) and r],
             p.get("apt_ghi_chu")),
        doan(ftse.get("noi_dung"), mau="lam", the=True, tieu_de=ftse.get("tieu_de")),
        doan(nbb.get("noi_dung"), mau="tim", the=True, tieu_de="Nghịch đảo bên bán"),
        bang(["Nhà phân tích", "Giá mục tiêu", "Ngày"],
             [[nfc(g.get("nha")), cell(fmt_vn(g.get("gia"), 0), mono=True), nfc(g.get("ngay"))]
              for g in as_list(nbb.get("gia_muc_tieu")) if isinstance(g, dict)],
             "Trung vị ≈ %sk · %s" % (fmt_vn(nbb.get("trung_vi_k"), 0), nfc(nbb.get("tier"))), can_phai=[1])]
    return sec("phan_2", p.get("tieu_de"), khoi, so="II", eyebrow="Phần II · Đợt này (2023 → %s)" % ddmmyyyy(
        parse_day(prof.get("du_lieu_den"))), lede=p.get("mo_ta"))


def section_roadshow(prof):
    r = as_dict(prof.get("roadshow_msr"))
    tiles = [tile(t.get("nhan"), nfc(t.get("gia_tri")), t.get("ghi_chu"), tier=t.get("tier"))
             for t in as_list(r.get("tiles")) if isinstance(t, dict)]
    khoi = [
        o_so(tiles, cot=3),
        bang(["Đã chốt hoặc đã công bố", "Nguồn"],
             [[nfc(x.get("noi_dung")), tier_cell(x.get("tier"))] for x in as_list(r.get("da_chot")) if isinstance(x, dict)]),
        bang(["Mới là định hướng hoặc có điều kiện", "Kiểm của chúng tôi"],
             [[nfc(x.get("noi_dung")), nfc(x.get("kiem"))] for x in as_list(r.get("co_dieu_kien")) if isinstance(x, dict)]),
        bang(as_list(r.get("mo_cong_suat_cot")), [[cell(nfc(x[0]), dam=True)] + [nfc(c) for c in x[1:]]
                                                   for x in as_list(r.get("mo_cong_suat")) if isinstance(x, list) and x],
             r.get("nguon_bang")),
        the_block([card("%s · %s" % (x.get("id"), nfc(x.get("tieu_de"))), x.get("noi_dung"), nhan=x.get("nhan"),
                        nhan_mau="tim", tier=x.get("tier"))
                   for x in as_list(r.get("phan_tich")) if isinstance(x, dict)], 3),
        heading("Chuỗi chất xúc tác mới · từ Elmet tới cổ tức MSN"),
        bang(["#", "Mắt xích", "Trạng thái", "Kiểm chứng bằng"],
             [[cell(str(x.get("id")), mono=True), nfc(x.get("mat_xich")), pill(x.get("trang_thai")),
               nfc(x.get("kiem_chung"))] for x in as_list(r.get("chuoi_xuc_tac")) if isinstance(x, dict)],
             r.get("chuoi_ghi_chu")),
        bang(["Yếu tố", "Trước roadshow", "Sau roadshow", "Chiều"],
             [[nfc(x.get("yeu_to")), nfc(x.get("truoc")), nfc(x.get("sau")),
               cell(nfc(x.get("chieu")), dam=True, mau={"+": "xanh", "−": "do"}.get(nfc(x.get("chieu")), "xam"))]
              for x in as_list(r.get("truoc_sau")) if isinstance(x, dict)]),
        heading("Cập nhật xác suất — chỉ theo dữ kiện, bỏ qua lời lạc quan"),
    ] + [doan(t) for t in as_list(r.get("cap_nhat_xac_suat"))]
    return sec("roadshow", r.get("tieu_de"), khoi, eyebrow=r.get("nhan"), lede=r.get("mo_ta"))


def section_du_bao(prof):
    d = as_dict(prof.get("du_bao"))
    ref = finite(as_dict(as_dict(prof.get("theo_doi_tuan")).get("tuan_goc")).get("msn"))
    dn = as_dict(d.get("do_nhay"))
    cols = as_list(dn.get("cot_look_through"))
    rows = []
    for r in as_list(dn.get("dong")):
        r = as_dict(r)
        row = [cell(x_txt(r.get("ty_le")), dam=True, mono=True)]
        for j, v in enumerate(as_list(r.get("gia_k"))):
            mau = None
            if ref and finite(v) is not None:
                mau = "xanh" if v > ref * 1.3 else ("do" if v < ref * 0.85 else None)
            cur = abs((finite(r.get("ty_le")) or 0) - 0.49) < 1e-9 and j < len(cols) and cols[j] == 218
            row.append(cell(fmt_vn(v, 1, fixed=True), mono=True, dam=cur, mau="vang" if cur else mau))
        rows.append(row)
    gkv = as_dict(d.get("gia_ky_vong"))
    khoi = [
        bang(["Mốc", "Khuôn mẫu 2017 · 2020", "Đợt này"],
             [[cell(nfc(x.get("moc")), dam=True), nfc(x.get("khuon")), nfc(x.get("dot_nay"))]
              for x in as_list(d.get("khuon_mau")) if isinstance(x, dict)]),
        o_so([tile(t.get("nhan"), nfc(t.get("gia_tri")), t.get("ghi_chu"), tier=t.get("tier"))
              for t in as_list(d.get("tiles")) if isinstance(t, dict)], cot=3),
        the_block([card("%s · %s" % (nfc(k.get("ten")), nfc(k.get("mo_ta"))),
                        "Điều kiện: %s\nTỷ lệ · look-through: %s\nGiá: %s\nTín hiệu sớm: %s" % (
                            nfc(k.get("dieu_kien")), nfc(k.get("ty_le_in")), nfc(k.get("gia_in")),
                            nfc(k.get("tin_hieu_som"))),
                        nhan="%s%% (trước %s%%)" % (fmt_vn((finite(k.get("xac_suat")) or 0) * 100, 0),
                                                   fmt_vn((finite(k.get("xac_suat_truoc")) or 0) * 100, 0)),
                        nhan_mau={"Tăng": "xanh", "Giảm": "do"}.get(nfc(k.get("ten")), "lam"),
                        mau_vien={"Tăng": "xanh", "Giảm": "do"}.get(nfc(k.get("ten")), "lam"), tier="EST")
                   for k in as_list(d.get("kich_ban")) if isinstance(k, dict)], 3),
        doan(gkv.get("text"), mau="vang", the=True, tieu_de="Giá kỳ vọng và bất cân xứng"),
        heading("Độ nhạy: giá MSN theo tỷ lệ và giá trị cổ phần niêm yết (nghìn đồng)"),
        bang(as_list(dn.get("cot_in")), rows, dn.get("cong_thuc"), can_phai=list(range(1, len(cols) + 1))),
        heading("Lịch chất xúc tác"),
        bang(["Mốc", "Sự kiện", "Nhãn"], [[cell(nfc(x.get("moc")), mono=True), nfc(x.get("su_kien")),
                                          tier_cell(x.get("tier"))]
                                         for x in as_list(d.get("lich_xuc_tac")) if isinstance(x, dict)])]
    return sec("du_bao", d.get("tieu_de"), khoi, eyebrow=d.get("nhan"),
               lede=as_dict(d.get("tan_suat_co_so")).get("text"))


def section_phan_3(prof):
    p = as_dict(prof.get("phan_III"))
    cap = []
    for c in as_list(p.get("capture")):
        c = as_dict(c)
        v = finite(c.get("capture"))
        cap.append([cell(nfc(c.get("cap")), dam=True), nfc(c.get("cua_so")),
                    cell(fmt_vn(c.get("con_pct"), 1, sign=True) + "%", mono=True),
                    cell(fmt_vn(c.get("me_pct"), 1, sign=True) + "%", mono=True),
                    cell(nfc(c.get("capture_in")) or fmt_vn(v, 2, fixed=True), mono=True,
                         mau="do" if (v is not None and v < 0.2) else None)])
    khoi = [
        heading("Capture ratio trong các nhịp lớn của công ty con"),
        bang(["Cặp mẹ ← con", "Cửa sổ", "Con", "Mẹ", "Capture"], cap, p.get("capture_ghi_chu"), can_phai=[2, 3, 4]),
        bang(as_list(p.get("cap_cot")), [[cell(nfc(r[0]), dam=True)] + [nfc(c) for c in r[1:]]
                                          for r in as_list(p.get("cap")) if isinstance(r, list) and r], p.get("cap_nguon")),
        bang(as_list(p.get("holdco_cot")),
             [[cell(nfc(h["in"][0]), dam=True)] + [cell(nfc(c), mono=True) for c in h["in"][1:4]] + [nfc(h.get("doc"))]
              for h in as_list(p.get("holdco")) if isinstance(h, dict) and len(as_list(h.get("in"))) >= 4],
             can_phai=[1, 2, 3]),
        heading("Năm quy luật rút ra"),
        danh_sach([{"so": str(i + 1), "text": nfc(t)} for i, t in enumerate(as_list(p.get("nam_quy_luat")))])]
    return sec("phan_3", p.get("tieu_de"), khoi, so="III", eyebrow="Phần III · Các chaebol Việt Nam",
               lede=p.get("dinh_nghia_capture"))


def section_case(prof):
    c = as_dict(prof.get("case_toan_cau"))
    rows = [[cell(nfc(x.get("case")), dam=True), nfc(x.get("du_kien")), pill(x.get("ket_luan"))]
            for x in as_list(c.get("case")) if isinstance(x, dict)]
    return sec("case_15", c.get("tieu_de"), [
        bang(["Case", "Dữ kiện", "Kết luận"], rows),
        doan(c.get("nguon_va_loi")),
        doan("Phản ví dụ K6: " + " · ".join(nfc(x) for x in as_list(c.get("phan_vi_du_K6"))), mau="xam")
        if as_list(c.get("phan_vi_du_K6")) else None], eyebrow=c.get("nhan"), lede=c.get("mo_ta"))


def section_vung_gia(prof, lv, charts):
    v = as_dict(prof.get("vung_gia_sigma"))
    rows = []
    for m in as_list(v.get("ma")):
        m = as_dict(m)
        ng = as_list(m.get("nguong_k"))
        rows.append([cell(nfc(m.get("ma")), dam=True),
                     "%s · μ %s · σ %s" % (nfc(m.get("chi_so")), fmt_vn(m.get("mu")), fmt_vn(m.get("sd")))]
                    + [cell(fmt_vn(x, 1, fixed=True), mono=True) for x in ng[:5]]
                    + [cell("%s · %s %s · %s" % (fmt_vn(m.get("gia"), 1, fixed=True), nfc(m.get("chi_so")),
                                                 x_txt(m.get("ratio")), sigma_txt(m.get("sigma"))), mono=True),
                       nfc(m.get("nguon"))])
    if lv.ok and lv.pb is not None:
        p = lv.params
        bands = [p["bvps"] * (p["mu"] + k * p["sd"]) for k in (-2, -1, 0, 1, 2)]
        rows.insert(0, [cell("MSN · LIVE", dam=True, mau="lam"),
                        "P/B · μ %s · σ %s (%s)" % (fmt_vn(p["mu"]), fmt_vn(p["sd"]), p["nguon"])]
                    + [cell(k_txt(b, 1), mono=True) for b in bands]
                    + [cell("%s · P/B %s · %s" % (k_txt(lv.close, 1), x_txt(lv.pb), sigma_txt(lv.sigma)), mono=True,
                            mau="lam"), "LIVE %s" % ddmm(lv.data_to)])
    rrg = as_dict(prof.get("rrg"))
    rrg_rows = [[cell(nfc(r.get("ma")), dam=True), cell(fmt_vn(r.get("rs_ratio"), 1, fixed=True), mono=True),
                 cell(fmt_vn(r.get("rs_mom"), 1, fixed=True), mono=True),
                 pill(r.get("goc"), {"Dẫn dắt": "xanh", "Cải thiện": "lam", "Tụt hậu": "do", "Suy yếu": "vang"}
                      .get(nfc(r.get("goc")), "xam"))] for r in as_list(rrg.get("ma")) if isinstance(r, dict)]
    kl_note = ""
    if lv.ok and lv.kl20_year is not None:
        kl_note = "LIVE %s: khối lượng MSN 20 phiên = %s bình quân 250 phiên (hồ sơ: %s)." % (
            ddmm(lv.data_to), x_txt(lv.kl20_year), x_txt(rrg.get("kl_20_phien_bq_nam")))
    khoi = [heading("Vị trí giá trong dải σ của chính mã (nghìn đồng tại −2σ, −1σ, μ, +1σ, +2σ)"),
            bang(["Mã", "Chỉ số", "−2σ", "−1σ", "μ", "+1σ", "+2σ", "Giá · ratio · σ", "Nguồn"], rows,
                 "Vùng: " + " · ".join(nfc(x) for x in as_list(v.get("vung_nhan"))), can_phai=[2, 3, 4, 5, 6])] + charts + [
        doan(v.get("canh_bao"), mau="vang", the=True, tieu_de="Hai cảnh báo"),
        heading("%s · %s" % (nfc(rrg.get("tieu_de")) or "RRG", nfc(rrg.get("khung")))),
        bang(["Mã", "RS-Ratio", "RS-Momentum", "Góc"], rrg_rows, rrg.get("cong_thuc"), can_phai=[1, 2]),
        doan(rrg.get("doc")),
        doan(kl_note, mau="lam")]
    return sec("vung_gia", v.get("tieu_de"), khoi, eyebrow=v.get("nhan"), lede=v.get("mo_ta"))


def section_phan_4(prof):
    p = as_dict(prof.get("phan_IV"))
    rows = [[cell(str(x.get("id")), mono=True), nfc(x.get("nhan_dinh")), nfc(x.get("thuc_te")), pill(x.get("cham"))]
            for x in as_list(p.get("nhan_dinh")) if isinstance(x, dict)]
    kh = as_dict(p.get("ke_hoach_don_bay"))
    return sec("phan_4", p.get("tieu_de"), [
        bang(["#", "Nhận định", "Thực tế", "Chấm"], rows),
        doan(kh.get("noi_dung"), mau="do", the=True, tieu_de=kh.get("tieu_de")),
        heading("Năm bài học rút ra"),
        danh_sach([{"so": str(i + 1), "text": nfc(t)} for i, t in enumerate(as_list(p.get("nam_bai_hoc")))])],
        so="IV", eyebrow="Phần IV · Rà soát toàn bộ output của dự án", lede=p.get("nguon_ra_soat"))


def section_hoi_dong(prof):
    h = as_dict(prof.get("hoi_dong"))

    def zone_cards(key):
        return the_block([card(x.get("co_van"), "\n\n".join(nfc(t) for t in as_list(x.get("noi_dung"))),
                               nhan=x.get("phieu"), nhan_mau=status_mau(x.get("phieu")) if "KHÔNG" not in nfc(
                                   x.get("phieu")) else "do")
                          for x in as_list(h.get(key)) if isinstance(x, dict)], 3)

    return sec("hoi_dong", h.get("tieu_de"), [
        heading("Họp lại tối 24/09 · sau roadshow MSR"),
        bang(["Cố vấn", "Phiếu", "Điều đã đổi"],
             [[cell(nfc(x.get("co_van")), dam=True), pill(x.get("phieu"), "do" if "KHÔNG" in nfc(x.get("phieu")) else None),
               nfc(x.get("da_doi"))] for x in as_list(h.get("hop_lai_24_09")) if isinstance(x, dict)]),
        doan(h.get("ket_hop_lai"), mau="vang", the=True, tieu_de="Kết quả họp lại"),
        heading("Kill zone"), zone_cards("kill_zone"),
        doan(h.get("kill_zone_ket"), mau="do"),
        heading("Alpha zone"), zone_cards("alpha_zone"),
        heading("Synthesis L3"),
        bang(["Mục", "Nội dung"], [[cell(nfc(x.get("muc")), dam=True), nfc(x.get("noi_dung"))]
                                   for x in as_list(h.get("synthesis_L3")) if isinstance(x, dict)])],
        eyebrow=h.get("nhan"))


def section_hanh_dong(prof):
    h = as_dict(prof.get("hanh_dong"))
    rows = [[cell(nfc(x.get("ma")), dam=True), nfc(x.get("tham_chieu")), nfc(x.get("hanh_dong")),
             nfc(x.get("kich_hoat_tang")), nfc(x.get("phu_dinh_stop"))]
            for x in as_list(h.get("bang")) if isinstance(x, dict)]
    frozen = hanh_dong_mode() == HANH_DONG_DONG_BANG
    return sec("hanh_dong", h.get("tieu_de"), [
        doan(DISCLAIMER, mau="do"),
        doan("ĐÓNG BĂNG: bảng dưới là luật của hồ sơ tại ngày lập, hiển thị nguyên văn làm lịch sử. CỔNG v1.7 đang "
             "DỪNG (chuỗi M2 gãy 10/2025), nên tab không chấm lại nhánh tỷ trọng nào theo dữ liệu tuần.", mau="vang")
        if frozen else None,
        bang(["Mã", "Tham chiếu", "Hành động", "Kích hoạt tăng", "Phủ định · stop"], rows),
        doan(h.get("canh_bao_tuong_quan"), mau="vang", the=True, tieu_de="Cảnh báo tương quan"),
        doan(h.get("xung_dot_luat"), mau="tim", the=True, tieu_de="Xung đột luật cần Michael quyết")],
        eyebrow="Bảng hành động · danh mục lõi")


def section_pre_mortem(prof):
    p = as_dict(prof.get("pre_mortem"))
    cards = []
    for x in as_list(p.get("nguyen_nhan")):
        x = as_dict(x)
        extra = nfc(x.get("tin_hieu_som"))
        text = nfc(x.get("noi_dung")) + ("\n\nTín hiệu sớm: " + extra if extra else "") + (
            "\n\n" + nfc(x.get("phong_ngua")) if nfc(x.get("phong_ngua")) else "")
        cards.append(card("%s · %s" % (x.get("id"), nfc(x.get("ten"))), text, nhan=x.get("xac_suat"), nhan_mau="do",
                          mau_vien="do"))
    return sec("pre_mortem", p.get("tieu_de"), [the_block(cards, 3)], eyebrow="Pre-mortem · Gary Klein")


def section_rigor(prof):
    r = as_dict(prof.get("rigor_6d"))
    rows = []
    for x in as_list(r.get("dong")):
        x = as_dict(x)
        pts = [cell(fmt_vn(v, 0), mono=True, mau="xanh" if (finite(v) or 0) >= 4 else ("do" if (finite(v) or 9) <= 2 else None))
               for v in as_list(x.get("diem"))]
        rows.append([cell(nfc(x.get("cum")), dam=True)] + pts + [cell(fmt_vn(x.get("tb"), 1, fixed=True), mono=True, dam=True),
                                                                  nfc(x.get("ghi_chu"))])
    ncol = len(as_list(r.get("cot")))
    return sec("rigor_6d", r.get("tieu_de"), [
        bang(as_list(r.get("cot")), rows, can_phai=list(range(1, max(ncol - 1, 1)))),
        heading("Việc còn treo"),
        danh_sach([{"so": str(i + 1), "text": nfc(t)} for i, t in enumerate(as_list(prof.get("viec_con_treo_cuoi")))])],
        eyebrow="Tự chấm rigor 6D · từng cụm nhận định", lede=r.get("chu_giai"))


def section_nguon(prof, sources):
    rows = [[cell(nfc(s["ten"]), dam=True), cell(s.get("as_of") or CAN, mono=True),
             tier_cell(s.get("tier")), pill("OK" if s.get("ok") else "THIẾU", "xanh" if s.get("ok") else "do"),
             "%s%s" % (s.get("duong_dan") or "", (" · " + s["ghi_chu"]) if s.get("ghi_chu") else "")]
            for s in sources]
    return sec("nguon", "Nguồn", [
        doan("Phương pháp. " + nfc(prof.get("phuong_phap")) if nfc(prof.get("phuong_phap")) else ""),
        doan("Giới hạn đã biết. " + nfc(prof.get("gioi_han")) if nfc(prof.get("gioi_han")) else "", mau=None),
        heading("Nguồn live của tab (đọc trên máy, không gọi mạng)"),
        bang(["Nguồn", "Dữ liệu đến", "Nhãn", "Trạng thái", "Đường dẫn · ghi chú"], rows),
        heading("Nguồn chính của hồ sơ"),
        danh_sach([{"so": str(i + 1), "text": nfc(t)} for i, t in enumerate(as_list(prof.get("nguon")))]),
        doan(prof.get("chu_ky"), mau="xam")], eyebrow="Nguồn · phương pháp · giới hạn")


# ── Charts (LkLineChart blocks) ──────────────────────────────────────────────


def point(d, y, text, sub="", mau="info", pos="above", uu_tien=1, marker="dot"):
    return {"kind": "point", "x": day_ms(d), "y": round(y, 4), "text": text, "sub": sub, "tip": text + (
        " · " + sub if sub else ""), "mau": mau, "marker": marker, "pos": pos, "uu_tien": uu_tien}


def hband(y0, y1, text, mau, alpha=0.10):
    return {"kind": "hband", "y0": y0, "y1": y1, "text": text, "mau": mau, "alpha": alpha}


def bieu_do(tieu_de, chu_thich, nguon, tier, block, cao=300):
    return {"kieu": "bieu_do", "tieu_de": tieu_de, "chu_thich": chu_thich, "nguon": nguon, "tier": tier,
            "cao": cao, "block": block}


def swing(lv):
    """Swing of the current cycle from daily closes since 03/01/2023: lowest close, the highest close after
    it, and the lowest close after that peak (the dossier's 50,3 → 88,5 → 63,9)."""
    d, c = lv.kho.closes("MSN")
    i0 = bisect.bisect_left(d, REBASE_FROM)
    out = {}
    if i0 >= len(d):
        return out
    ib = min(range(i0, len(d)), key=lambda i: c[i])
    out["day"] = (d[ib], c[ib])
    if ib + 1 < len(d):
        ip = max(range(ib + 1, len(d)), key=lambda i: c[i])
        out["dinh"] = (d[ip], c[ip])
        if ip + 1 < len(d):
            it = min(range(ip + 1, len(d)), key=lambda i: c[i])
            out["day_sau"] = (d[it], c[it])
    return out


def chart_price(lv):
    """(1) MSN weekly since 2020 + zone bands + X1/P1 bands, rally bands, key points."""
    ws = [w for w in lv.weeks if w["fri"] >= CHART1_FROM]
    if not ws:
        return None
    x = [w["last"].isoformat() for w in ws]
    y = [round(w["close"] / 1000.0, 3) for w in ws]
    vung = lv.vung
    ann = []
    for key, text, mau, alpha in (("giam", "Giảm", "bear", 0.10), ("co_so", "Cơ sở", "cyan", 0.07),
                                  ("tang", "Tăng", "bull", 0.10)):
        lo_hi = as_list(vung.get(key))
        if len(lo_hi) == 2:
            ann.append(hband(lo_hi[0], lo_hi[1], "%s %s–%sk" % (text, fmt_vn(lo_hi[0]), fmt_vn(lo_hi[1])), mau, alpha))
    sig = {r.get("id"): r for r in lv.iss.signals}
    x1, p1 = finite(as_dict(sig.get("X1")).get("muc")), finite(as_dict(sig.get("P1")).get("muc"))
    co_hi = (as_list(vung.get("co_so")) or [None, None])[1]
    cd_lo = (as_list(vung.get("chuyen_duoi")) or [None, None])[0]
    if x1 and co_hi and x1 < co_hi:
        ann.append(hband(x1, co_hi, "X1 · tuần đóng > %sk" % fmt_vn(x1), "amber", 0.14))
    if p1 and cd_lo and cd_lo < p1:
        ann.append(hband(cd_lo, p1, ("P1 · tuần đóng < %sk" % fmt_vn(p1)) if hanh_dong_mode() == HANH_DONG_DONG_BANG
                     else "P1 · tuần đóng < %sk → 3%% NAV" % fmt_vn(p1), "bear", 0.18))
    ann.append({"kind": "xband", "x0": day_ms(date(2020, 2, 28)), "x1": day_ms(date(2021, 12, 29)),
                "text": "Đợt 2 · 28/02/2020 → 29/12/2021", "mau": "amber", "alpha": 0.07})
    ann.append({"kind": "xband", "x0": day_ms(REBASE_FROM), "x1": day_ms(ws[-1]["last"]), "text": "Đợt này",
                "mau": "dim", "alpha": 0.06})
    sw = swing(lv)
    for key, text, mau, pos, prio in (("day", "đáy", "bear", "below", 3), ("dinh", "đỉnh", "amber", "above", 2),
                                      ("day_sau", "đáy", "bear", "below", 3)):
        if sw.get(key):
            dd, cc = sw[key]
            ann.append(point(dd, cc / 1000.0, "%s %s" % (text, k_txt(cc, 1)), ddmmyyyy(dd), mau, pos, prio))
    if lv.x1_high:
        ann.append(point(lv.x1_high["last"], lv.x1_high["close"] / 1000.0, "tuần cao nhất từ 05/2026: %s" % k_txt(
            lv.x1_high["close"], 1), ddmm(lv.x1_high["last"]), "warn", "above", 2, "triangle"))
    ann.append(point(ws[-1]["last"], y[-1], "MSN %s" % k_txt(lv.close, 1), "%s · vùng %s" % (ddmm(lv.data_to), lv.zone),
                     "amber", "right", 1, "diamond"))
    block = {"x": x, "series": [{"name": "MSN · đóng cửa tuần", "y": y, "style": "line", "mau": "amber"}],
             "left": {"label": "nghìn đồng (giá điều chỉnh)"}, "annotations": ann}
    return bieu_do("MSN theo tuần từ 2020 · vùng giá kịch bản và ngưỡng X1/P1",
                   "Đường = đóng cửa phiên cuối mỗi tuần (tuần đang mở tính tới %s). Dải ngang = vùng giá EST của hồ sơ "
                   "(Giảm · Cơ sở · Tăng) và hai ngưỡng tín hiệu; dải dọc = đợt tăng 2020–2021 và đợt này." % ddmm(lv.data_to),
                   SRC_STORE, T_DATA, block, 320)


def chart_ratio(lv, prof):
    """(2) MSN ÷ look-through weekly: live (solid) + profile c4 (dashed), p25–p75 band, X3/P5 bands."""
    rw = [r for r in lv.ratio_weeks if r["ratio"] is not None]
    pts = [(r["last"], r["fri"], r["ratio"]) for r in rw]
    if lv.ratio_now is not None and lv.open:
        pts.append((lv.data_to, lv.open["fri"], lv.ratio_now))
    ds, ser = profile_series(prof, "bieu_do.c4")
    prof_by = {}
    if ds and ser:
        for dd, v in zip(ds, ser[0][1]):
            if dd and v is not None:
                prof_by[friday(dd)] = v
    if not pts and not prof_by:
        return None
    fri_x = {fri: day for day, fri, _ in pts}
    keys = sorted(set(fri_x) | set(prof_by))
    x = [(fri_x.get(k) or k).isoformat() for k in keys]
    live_by = {fri: v for _, fri, v in pts}
    y_live = [round(live_by[k], 4) if k in live_by else None for k in keys]
    y_prof = [prof_by.get(k) for k in keys]
    series = []
    if lv.ratio_p25 is not None:
        series.append({"name": "p25–p75 từ 01/2024", "style": "band", "mau": "dim", "alpha": 0.14,
                       "y_lo": [round(lv.ratio_p25, 4)] * len(x), "y_hi": [round(lv.ratio_p75, 4)] * len(x)})
    if prof_by:
        series.append({"name": "Bản %s (c4)" % nfc(prof.get("ho_so")), "y": y_prof, "style": "dash", "mau": "dim"})
    series.append({"name": "MSN ÷ look-through · live", "y": y_live, "style": "line", "mau": "amber"})
    vals = [v for v in y_live + y_prof if v is not None]
    top, bot = max(vals + [0.8]) + 0.05, min(vals + [0.45]) - 0.05
    sig = {r.get("id"): r for r in lv.iss.signals}
    x3, p5 = finite(as_dict(sig.get("X3")).get("muc")), finite(as_dict(sig.get("P5")).get("muc"))
    ann = []
    if x3:
        ann.append(hband(x3, top, "X3 · xác nhận > %s" % x_txt(x3), "bull", 0.10))
    if p5:
        ann.append(hband(bot, p5, "P5 · phủ định < %s (khi LT tăng)" % x_txt(p5), "bear", 0.12))
    if pts:
        hi = max(pts, key=lambda t: t[2])
        ann.append(point(hi[0], hi[2], "cao nhất %s" % x_txt(hi[2]), ddmmyyyy(hi[0]), "dim", "above", 3))
        peak = swing(lv).get("dinh")
        pk = next((t for t in pts if peak and t[1] == friday(peak[0])), None)
        if pk:
            ann.append(point(pk[0], pk[2], "tuần MSN lập đỉnh %s: %s" % (k_txt(peak[1], 1), x_txt(pk[2])),
                             ddmmyyyy(pk[0]), "amber", "above", 2))
        last = pts[-1]
        ann.append(point(last[0], last[2], "hiện tại %s" % x_txt(last[2]),
                         "%s · trung vị %s" % (ddmm(last[0]), x_txt(lv.ratio_median)), "amber", "right", 1, "diamond"))
    br = lv.msn_break
    cap = ("Look-through = Σ tỷ lệ sở hữu (hồ sơ) × vốn hóa giá thô của MCH, MSR, TCB; MSR %s trước %s theo giả định "
           "của hồ sơ. Vốn hóa MSN theo marketCap Vietcap, từ %s theo %s triệu cp của hồ sơ (Vietcap đổi số cp ngày đó). "
           "Nét đứt = chuỗi của hồ sơ %s, không ghép vào chuỗi live." % (
               (fmt_vn(lv.msr_before[1] * 100, 2) + "%") if lv.msr_before else CAN,
               ddmmyyyy(lv.msr_before[0]) if lv.msr_before else "?", ddmmyyyy(br) if br else "?",
               fmt_vn((lv.msn_shares or 0) / 1e6, 1), nfc(prof.get("ho_so"))))
    block = {"x": x, "series": series, "left": {"label": "×"}, "annotations": ann}
    return bieu_do("MSN ÷ giá trị cổ phần niêm yết, theo tuần", cap, "%s · %s" % (SRC_VC, SRC_STORE), T_EST, block, 320)


def chart_rebased(lv):
    """(3) MSN / MCH / MSR / TCB / VN-Index weekly, rebased 100 at the first session ≥ 03/01/2023."""
    kho = lv.kho
    base_weeks = [w for w in lv.weeks if w["fri"] >= friday(REBASE_FROM)]
    if not base_weeks:
        return None
    x = [w["last"].isoformat() for w in base_weeks]
    series, ann = [], []
    srcs = {}
    for name in ("MSN", "MCH", "MSR", "TCB", "VN-Index"):
        if name == "VN-Index":
            dd, cc = kho.vni()
            srcs[name] = "WiData/vnstore"
        elif name == "MSR" and kho.vc.get("MSR"):
            vc = kho.vc["MSR"]
            dd = [d for d, a in zip(vc["d"], vc["ca"]) if a]
            cc = [a for a in vc["ca"] if a]
            last_vc = dd[-1] if dd else None
            nd, nc = kho.closes("MSR")
            tail = [(d, c) for d, c in zip(nd, nc) if last_vc is None or d > last_vc]
            dd, cc = dd + [d for d, _ in tail], cc + [c for _, c in tail]
            srcs[name] = "Vietcap điều chỉnh"
        else:
            dd, cc = kho.closes(name)
            srcs[name] = "vnstore"
        i0 = bisect.bisect_left(dd, REBASE_FROM)
        if i0 >= len(dd):
            continue
        b = cc[i0]
        y = []
        for w in base_weeks:
            dv, v = asof(dd, cc, w["last"])
            y.append(round(v / b * 100.0, 3) if (v is not None and dv is not None and dv >= dd[i0]) else None)
        series.append({"name": name, "y": y, "style": "line", "mau": SERIES_MAU.get(name, "dim")})
        lastv = next((v for v in reversed(y) if v is not None), None)
        if lastv is not None:
            ann.append(point(base_weeks[-1]["last"], lastv, "%s %s" % (name, pct_txt(lastv - 100, 0)), "",
                             SERIES_MAU.get(name, "dim"), "right", 1 if name == "MSN" else 2))
    if not series:
        return None
    block = {"x": x, "series": series, "left": {"label": "quy về 100 (thang tuyến tính)"}, "annotations": ann}
    return bieu_do("Năm mã quy về 100 ngày 03/01/2023 · theo tuần · LIVE",
                   "Giá điều chỉnh: MSN, MCH, TCB từ vnstore; MSR từ Vietcap (vnstore chỉ có từ 09/2024); VN-Index "
                   "từ kho WiData nối vnstore. Hồ sơ vẽ thang log; khung này dùng thang tuyến tính.",
                   " · ".join("%s: %s" % (k, v) for k, v in srcs.items()), T_DATA, block, 320)


def chart_pb(lv):
    """(4) MSN P/B weekly (HHP series + live point) with ±1σ / ±2σ bands of the chosen parameter set."""
    s = lv.kho.pb_series
    p = lv.params
    if not s or not s["d"] or not p["mu"] or not p["sd"]:
        return None
    pts = [(d, pr / b) for d, pr, b in zip(s["d"], s["price_k"], s["base_k"]) if b]
    if lv.ok and lv.pb is not None and lv.data_to > pts[-1][0]:
        pts.append((lv.data_to, lv.pb))
    x = [d.isoformat() for d, _ in pts]
    n = len(x)
    mu, sd = p["mu"], p["sd"]
    series = [
        {"name": "RẺ SÂU < −2σ", "style": "band", "mau": "bull", "alpha": 0.16, "lo_min": True,
         "y_lo": [None] * n, "y_hi": [round(mu - 2 * sd, 4)] * n},
        {"name": "RẺ −2σ…−1σ", "style": "band", "mau": "bull", "alpha": 0.08,
         "y_lo": [round(mu - 2 * sd, 4)] * n, "y_hi": [round(mu - sd, 4)] * n},
        {"name": "ĐẮT +1σ…+2σ", "style": "band", "mau": "bear", "alpha": 0.08,
         "y_lo": [round(mu + sd, 4)] * n, "y_hi": [round(mu + 2 * sd, 4)] * n},
        {"name": "ĐẮT SÂU > +2σ", "style": "band", "mau": "bear", "alpha": 0.16, "hi_max": True,
         "y_lo": [round(mu + 2 * sd, 4)] * n, "y_hi": [None] * n},
        {"name": "P/B MSN", "y": [round(v, 4) for _, v in pts], "style": "line", "mau": "amber"}]
    ann = [point(pts[-1][0], pts[-1][1], "P/B %s · %s" % (x_txt(pts[-1][1]), sigma_txt((pts[-1][1] - mu) / sd)),
                 ddmm(pts[-1][0]), "amber", "right", 1, "diamond")]
    hi = max(pts, key=lambda t: t[1])
    lo = min(pts, key=lambda t: t[1])
    ann.append(point(hi[0], hi[1], "cao nhất %s" % x_txt(hi[1]), ddmmyyyy(hi[0]), "bear", "above", 3))
    ann.append(point(lo[0], lo[1], "thấp nhất %s" % x_txt(lo[1]), ddmmyyyy(lo[0]), "bull", "below", 3))
    block = {"x": x, "series": series, "left": {"label": "P/B (×)"}, "annotations": ann}
    return bieu_do("MSN · P/B theo tuần và dải σ",
                   "P/B = giá ÷ BVPS của engine HHP theo tuần; dải theo μ %s · σ %s (%s). Vùng không tô = trung tính "
                   "(−1σ…+1σ)." % (fmt_vn(mu), fmt_vn(sd), p["nguon"]),
                   "%s · chuỗi hhp_vn100_series/MSN · điểm cuối LIVE từ vnstore" % SRC_HHP, T_EST, block, 300)


def chart_volume(lv):
    """(5) KL tuần ÷ TB 20 tuần trước, complete weeks (bars) + the open week, 1,5× band."""
    cw = lv.complete
    idx = range(max(TB_WEEKS, len(cw) - VOL_CHART_WEEKS), len(cw))
    pts = [(cw[i]["last"], vol_ratio(cw, i)) for i in idx]
    pts = [(d, v) for d, v in pts if v is not None]
    if not pts:
        return None
    x = [d.isoformat() for d, _ in pts]
    y = [round(v, 3) for _, v in pts]
    y_open = [None] * len(x)
    if lv.open and lv.open_ratio is not None:
        x.append(lv.data_to.isoformat())
        y.append(None)
        y_open.append(round(lv.open_ratio, 3))
    top = max([v for v in y + y_open if v is not None] + [2.0]) * 1.05
    ann = [hband(1.5, top, "X2 · KL tuần ≥ 1,5× TB20", "bull", 0.10),
           point(pts[-1][0], pts[-1][1], "tuần %s: %s" % (ddmm(pts[-1][0]), x_txt(pts[-1][1])), "", "amber", "above", 1)]
    hi = max(pts, key=lambda t: t[1])
    ann.append(point(hi[0], hi[1], "cao nhất %s" % x_txt(hi[1]), ddmmyyyy(hi[0]), "warn", "above", 3))
    series = [{"name": "KL tuần ÷ TB20", "y": y, "style": "bar", "mau": "info", "alpha": 0.8}]
    if any(v is not None for v in y_open):
        series.append({"name": "tuần đang mở (%d phiên)" % lv.open["n"], "y": y_open, "style": "bar", "mau": "amber",
                       "alpha": 0.5})
    block = {"x": x, "series": series, "left": {"label": "×", "min": 0}, "annotations": ann}
    return bieu_do("KL tuần ÷ TB 20 tuần trước · MSN",
                   "Tổng khối lượng các phiên trong tuần ÷ trung bình 20 tuần đã đóng trước đó (không gồm chính tuần đó); "
                   "tuần ngắn ngày lễ vào mẫu số không chuẩn hoá, như hồ sơ. Cột cam = tuần đang mở, chưa đủ phiên.",
                   SRC_STORE, T_DATA, block, 300)


# ── CSV ──────────────────────────────────────────────────────────────────────


def s_txt(v):
    if isinstance(v, dict):
        return nfc(v.get("t"))
    return nfc(v) if isinstance(v, str) else ("" if v is None else str(v))


def build_csv(lv, log):
    rows = []
    if lv.ok:
        for t in live_tiles(lv, lv.iss.pday):
            rows.append(["Theo dõi tuần", t["nhan"], t["gia_tri"], ddmmyyyy(lv.data_to), "LIVE", t["tier"], t["phu"]])
        for r in lv.iss.signals:
            s = lv.sig.get(r.get("id"))
            if s:
                rows.append(["Tín hiệu", "%s · %s" % (r.get("id"), nfc(r.get("ten"))), s["gia_tri_in"],
                             ddmmyyyy(lv.data_to), s["trang_thai"], T_EST if r.get("bien") == "msn_lt" else T_DATA,
                             s["ghi_chu"]])
            else:
                rows.append(["Tín hiệu", "%s · %s" % (r.get("id"), nfc(r.get("ten"))), nfc(r.get("gia_tri_in")),
                             r.get("as_of"), nfc(r.get("trang_thai")), nfc(r.get("tier")), nfc(r.get("ghi_chu"))])
        for row in catalyst_rows(lv):
            rows.append(["Chất xúc tác", s_txt(row[0]), s_txt(row[2]), s_txt(row[1]), s_txt(row[3]), "", ""])
        for row in log:
            rows.append(["Nhật ký tuần", s_txt(row[0]), s_txt(row[1]), s_txt(row[0]), s_txt(row[7]), "",
                         " | ".join(s_txt(c) for c in row[2:7] + row[8:])])
    return {"columns": ["Mục", "Chỉ báo", "Giá trị", "Kỳ", "Trạng thái", "Nhãn", "Ghi chú"], "rows": rows}


# ── Overview ─────────────────────────────────────────────────────────────────


def ownership_warnings(kho, lv, warnings, alt=None):
    """Stakes in force at the last session vs the large-shareholder list, and MCH's effective-stake
    alternative: the newest annex's so_huu_hieu_dung when present, else the dossier's own 66% note."""
    d = lv.data_to
    for sym in CHILDREN:
        own = kho.owners.get(sym)
        w, e = lv.weight(sym, d), lv.weight_entry(sym, d)
        if own and w is not None and abs(own[0] / 100.0 - w) > 0.005:
            nguon = ("bản bổ sung %s, %s" % (ddmm(parse_day(e[2].get("ky"))), e[2].get("tier") or "chưa gắn nhãn")
                     if e else "hồ sơ")
            warnings.append("Sở hữu %s: tab dùng %s (%s) khác danh sách cổ đông lớn %s%% (%s, công bố %s); giữ số "
                            "của tab." % (sym, share_txt(w), nguon, fmt_vn(own[0], 2), own[1], own[2] or "?"))
    mch = lv.lt_parts.get("MCH")
    if not (mch and lv.lt_now and lv.mcap_msn):
        return
    w_mch = mch[1]
    if alt:
        a, src = alt
        r = lv.mcap_msn / (lv.lt_now - (w_mch - a) * mch[0])
        warnings.append("Sở hữu MCH: tab dùng %s (pháp lý); hiệu dụng %s theo %s. Với %s thì MSN/LT là %s thay "
                        "vì %s." % (share_txt(w_mch), share_txt(a), src, share_txt(a), x_txt(r),
                                    x_txt(lv.ratio_now)))
        return
    r = lv.mcap_msn / (lv.lt_now - (w_mch - MCH_ALT) * mch[0])
    warnings.append("Sở hữu hiệu dụng MCH chưa chốt (%s%% của hồ sơ hay %s%% theo mindmap 04/2026, việc treo "
                    "của hồ sơ); với %s%% thì MSN/LT là %s thay vì %s." % (
                        fmt_vn(w_mch * 100, 1), fmt_vn(MCH_ALT * 100, 0), fmt_vn(MCH_ALT * 100, 0), x_txt(r),
                        x_txt(lv.ratio_now)))


def build_overview(den=None, tham_so="auto"):
    p = paths()
    warnings = []
    prof, ppath, pday = load_profile(p["profile_dir"])
    tuan, tpath = load_tuan(p["profile_dir"], pday, warnings)
    iss = Issue(prof, pday, tuan)
    annexes = load_bo_sung(p["profile_dir"], pday, den, warnings)
    lich, lich_cho = ownership_schedule(annexes, warnings)
    kho = Kho(p, den, warnings, annex_symbols(annexes))
    lv = Live(kho, prof, iss, tham_so, warnings, lich, lich_cho)
    if lv.ok:
        ownership_warnings(kho, lv, warnings, effective_alt(annexes))
        if lv.src_last == "vci_board":
            warnings.append("Phiên %s là giá thô bảng điện (vci_board) — chưa được lịch sử Vietcap điều chỉnh lại." %
                            ddmm(lv.data_to))
        hhp_stale = as_list(as_dict(as_dict(kho.hhp).get("meta")).get("stale_fields"))
        if hhp_stale:
            warnings.append("Engine HHP đánh dấu stale: %s." % ", ".join(str(x) for x in hhp_stale))
    now = today()
    age = (now - lv.data_to).days if lv.data_to else None
    newest_issue = max(d for d in (pday, iss.tday) if d) if (pday or iss.tday) else None
    p_age = (now - newest_issue).days if newest_issue else None
    stale_bits = []
    if age is None or age > STALE_DATA_DAYS:
        stale_bits.append("DỮ LIỆU CŨ %s ngày (đến %s)" % (age if age is not None else "?", ddmm(lv.data_to)))
        warnings.append("Kho giá chưa có phiên mới từ %s — chạy lại bộ điều phối (goi_nguon) rồi FETCH." %
                        (ddmmyyyy(lv.data_to) or "?"))
    if p_age is not None and p_age > STALE_PROFILE_DAYS:
        stale_bits.append("HỒ SƠ CŨ %d ngày — P2–P4, P6, C1–C3 có thể đã lỗi thời" % p_age)
    meta_line = "LIVE: dữ liệu đến %s · tạo lúc %s · σ-band theo %s%s" % (
        ddmmyyyy(lv.data_to) or CAN, datetime.now(ICT).strftime("%H:%M %d/%m"), lv.params["nguon"],
        " · bản tuần %s" % ddmm(iss.tday) if iss.tday else "")

    charts_live = [chart_price(lv), chart_volume(lv)] if lv.ok else []
    charts_2 = [chart_rebased(lv), chart_ratio(lv, prof)] if lv.ok else []
    charts_pb = [chart_pb(lv)] if lv.ok else []
    for name, group in (("giá tuần", charts_live[:1]), ("KL tuần", charts_live[1:]), ("quy về 100", charts_2[:1]),
                        ("MSN/LT", charts_2[1:]), ("P/B", charts_pb)):
        if lv.ok and not any(group):
            warnings.append("Bỏ biểu đồ %s — thiếu dữ liệu." % name)

    builders = [
        ("cong", lambda: section_cong(prof, pday, lv, meta_line)),
        ("theo_doi_tuan", lambda: section_theo_doi(prof, pday, lv, iss, [c for c in charts_live if c], warnings)),
        ("tiles_dau", lambda: section_o_so_dau(prof, lv)),
        ("keynotes", lambda: section_keynotes(prof)),
        ("ba_dong_ho", lambda: section_ba_dong_ho(prof)),
        ("phan_I", lambda: section_phan_1(prof)),
        ("phan_II", lambda: section_phan_2(prof, [c for c in charts_2 if c])),
        ("roadshow_msr", lambda: section_roadshow(prof)),
        ("du_bao", lambda: section_du_bao(prof)),
        ("phan_III", lambda: section_phan_3(prof)),
        ("case_toan_cau", lambda: section_case(prof)),
        ("vung_gia_sigma", lambda: section_vung_gia(prof, lv, [c for c in charts_pb if c])),
        ("phan_IV", lambda: section_phan_4(prof)),
        ("hoi_dong", lambda: section_hoi_dong(prof)),
        ("hanh_dong", lambda: section_hanh_dong(prof)),
        ("pre_mortem", lambda: section_pre_mortem(prof)),
        ("rigor_6d", lambda: section_rigor(prof)),
        ("nguon", None),
    ]
    sections = []
    for key, fn in builders:
        if fn is None:
            continue
        if key not in ("cong", "theo_doi_tuan") and not isinstance(prof.get(key), (dict, list)):
            warnings.append("Hồ sơ thiếu phần \"%s\" — bỏ mục đó." % key)
            continue
        sections.append(fn())
    log = log_rows(lv) if lv.ok else []
    hst_live, hst_csv = {}, []
    sections = insert_annexes(sections, annexes, lv, warnings, hst_live, hst_csv)
    sections.append(section_nguon(prof, kho.sources))

    live_out = {}
    if lv.ok:
        live_out = {
            "data_to": lv.data_to.isoformat(), "close": lv.close,
            "last_week": {"last": lv.last_week["last"].isoformat(), "close": lv.last_week["close"],
                          "kl": lv.last_week["kl"], "n": lv.last_week["n"]} if lv.last_week else None,
            "open_week": {"fri": lv.open["fri"].isoformat(), "n": lv.open["n"], "kl": lv.open["kl"],
                          "kl_ratio": lv.open_ratio} if lv.open else None,
            "vs_week_pct": lv.vs_week, "week_chg_pct": lv.week_chg, "kl_ratio": lv.kl_ratio,
            "lt": lv.lt_now, "lt_prev_week": lv.lt_prev, "mcap_msn": lv.mcap_msn, "ratio": lv.ratio_now,
            "ratio_local_shares": lv.ratio_local, "ratio_median": lv.ratio_median, "ratio_pct_lower": lv.ratio_pct_lower,
            "ratio_n": lv.ratio_n, "ratio_pct_n": lv.ratio_pct_n, "ref_week": lv.ref_week["last"].isoformat()
            if lv.ref_week else None, "pb": lv.pb, "sigma": lv.sigma, "band_minus1": lv.band_m1, "band_mu": lv.band_mu,
            "pb_params": lv.params, "zone": lv.zone,
            "x1_high": {"last": lv.x1_high["last"].isoformat(), "close": lv.x1_high["close"]} if lv.x1_high else None,
            "session": {"chg_pct": lv.sess_chg, "kl": lv.sess_kl, "kl_ratio": lv.sess_kl_ratio, "nn": lv.sess_nn,
                        "kl20_year": lv.kl20_year},
            "vnindex": {"day": lv.vni_day.isoformat() if lv.vni_day else None, "close": lv.vni},
            "msn_share_break": lv.msn_break.isoformat() if lv.msn_break else None,
            "signals": {k: {kk: vv for kk, vv in v.items()} for k, v in lv.sig.items()},
        }
    if hst_live and live_out:
        live_out["he_sinh_thai"] = hst_live
    stale = bool(stale_bits)
    meta = {"generated": datetime.now(ICT).isoformat(timespec="seconds"), "script_version": SCRIPT_VERSION,
            "profile_dir": p["profile_dir"], "profile_file": ppath, "profile_date": pday.isoformat() if pday else None,
            "tuan_file": tpath, "tuan_ky": iss.tday.isoformat() if iss.tday else None,
            "artifact_url": nfc(prof.get("artifact_url")) or None,
            "data_to": lv.data_to.isoformat() if lv.data_to else None,
            "den": den.isoformat() if den else None, "age_days": age, "profile_age_days": p_age,
            "stale": stale, "stale_text": " · ".join(stale_bits), "tham_so_pb": lv.params["nguon"],
            "warnings": warnings, "sources_live": kho.sources,
            "bo_sung": [{"file": pth, "ky": a.get("ky"), "tieu_de": nfc(a.get("tieu_de")) or None,
                         "artifact_url": nfc(a.get("artifact_url")) or None} for a, pth, _ in annexes]}
    csv_out = build_csv(lv, log)
    csv_out["rows"].extend(hst_csv)
    return {"meta": meta, "live": live_out,
            "trang": {"schema": "vnblocks/1", "tieu_de": nfc(prof.get("tab")) or "MSN MSR Reflex", "sections": sections},
            "csv": csv_out}


# ── CLI ──────────────────────────────────────────────────────────────────────


def run(argv):
    if len(argv) < 2:
        raise MsnError("BAD_ARGS", "Thiếu lệnh. " + USAGE)
    cmd = argv[1].strip().lower()
    if cmd != "overview":
        raise MsnError("BAD_ARGS", "Lệnh không hỗ trợ: %r. %s" % (argv[1], USAGE))
    rest = argv[2:]
    den = None
    if rest:
        if len(rest) != 2 or rest[0] != "--den":
            raise MsnError("BAD_ARGS", "Tham số không hợp lệ: %s. %s" % (" ".join(rest), USAGE))
        den = parse_day(rest[1].strip()) if ISO_RE.fullmatch(rest[1].strip()) else None
        if den is None:
            raise MsnError("BAD_ARGS", "Ngày --den không hợp lệ: %r (cần YYYY-MM-DD). %s" % (rest[1], USAGE))
    return build_overview(den)


def emit(obj):
    text = json.dumps(clean(obj), ensure_ascii=False, separators=(",", ":"), allow_nan=False, default=str)
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
    except MsnError as exc:
        out = {"error": exc.message, "error_code": exc.code}
    except Exception as exc:  # never let a traceback replace the JSON envelope
        out = {"error": "Lỗi nội bộ msn_reflex.py: %s: %s" % (type(exc).__name__, exc), "error_code": "INTERNAL"}
    emit(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
