#!/usr/bin/env python3
"""
Fincept Terminal: Chaebol Reflex framework library (tab "msn_reflex", label "Chaebol Reflex").

Reads <CHAEBOL_REFLEX_DIR>/khung.json (schema "chaebol_khung/1", spec §5) and turns it into vnblocks/1 blocks for
chaebol_reflex_trang.py. Stdlib only, Python 3.9+, no network, read-only. Every framework is the author's EST,
frozen at its source date; the only live part is the data check of each "dau_hieu_do_duoc" through
chaebol_reflex_live.LiveNhom.do_dau_hieu: seen / not seen with a date, tier EST. It is a data sign, never a phase
call and never advice ("dấu hiệu dữ liệu, không phải xếp pha").

khung.json  {"schema": "chaebol_khung/1", "khung": [{"id", "ten", "nguon", "loai", "mo_ta", "noi_dung": any,
             "ap_dung_cho": ["moi_nhom" | <group id>], "dau_hieu_do_duoc": [{"id", "mo_ta", "phep_do": <key of
             chaebol_reflex_live.DAU_HIEU>, "tham_so": {...}, "ma"?: <TICKER> | "moi_ma"}], "tier"}]}
  tham_so aliases: a key ending in _pct / _x / _sigma / _lan is read without the suffix ({"x_pct": 10} → x = 10);
  "nguong" / "muc" are the sign's threshold when the engine name (DAU_HIEU_THAM_SO) is absent; any other key is
  dropped with a warning (no guess). "ma" (or "ap_cho") picks the ticker(s): absent / "me" = the group parent (else
  the base ticker), a ticker, a list of tickers, "moi_ma" / "tung_ma" = every priced member; a value that is not a
  ticker gives a [CẦN DATA] row, never the parent.

API
  load_khung(root=None, warnings=None) -> (lib | None, path)
  lib_index(lib) -> {id | bi_danh: entry}   a dossier may cite a merged framework by an old id (bi_danh)
  khung_cho(lib, nhom_id, ids=()) -> [(entry, rieng: bool)]   frameworks for a group (explicit or "moi_nhom")
  cham(lv, entry) -> [row]   every measurable sign of one framework evaluated on a LiveNhom
  section_khung(lv, lib, nhom_id, khung_ap_dung, warnings, ...) -> vnblocks section | None   per framework the
      dossier maps: one-line description + the group's frozen mapping rows; then every measurable sign checked live;
      never the framework's full noi_dung (that lives in khung.json, index on TỔNG QUAN)
  section_thu_vien(lib, path, warnings, bo_qua=(), cot_loi=CORE_IDS) -> vnblocks section | None   TỔNG QUAN: one
      index table of the library + the main stage/phase table (≤ MAX_CORE_ROWS rows) of the core frameworks
  entry_compact(entry) -> [blocks]   heading, description, "Cốt lõi" and the names of the other parts
  khung_entry(lib, pattern) -> entry | None   (first id / name matching a regex, e.g. Concentration Era)
  render_any(obj) -> [blocks]   generic renderer for free-form framework content
  ngan(text) / nguon_cell(text, n=None, **cell_kw)   source text for display: "/Users/<u>/Downloads/x" →
      "Downloads/x", "/Users/<u>/SECOND BRAIN-OBSIDIAN/_System/…" → "_System/…", "/private/tmp/…/f" → "f"; the cell
      keeps the full string in "tip"
  guard(blocks, nhan) -> int / guard_blocks(blocks, nhan, warnings, where) -> blocks   CỔNG v1.7 DỪNG: every
      unit (paragraph, table header, table ROW, list item, card, tile, warning line) carrying order, rating, sizing
      or target-price words (MUA/BÁN/GIỮ/NAV, BUY/SELL/HOLD/ADD/AVOID…, M-PF/O-PF/U-PF, TP + số, tỷ trọng, giá mục
      tiêu, khuyến nghị, khả quan, a rating word in rating context such as "xuống Giữ") without its own ĐÓNG BĂNG
      label gets "ĐÓNG BĂNG · <nhan>"; one frozen row never exempts the rest of its table
"""

from __future__ import annotations

import json
import os
import re

import chaebol_reflex_live as L
import msn_reflex as M

SCHEMA = "chaebol_khung/1"
MOI_NHOM = "moi_nhom"
MOI_MA = ("moi_ma", "tung_ma", "moi_thanh_vien")
NHAN_DAU_HIEU = "dấu hiệu dữ liệu, không phải xếp pha"
DONG_BANG = "ĐÓNG BĂNG"
SUFFIXES = ("_pct", "_x", "_sigma", "_lan")
CUA_SO_ALIAS = {"3y": "3y", "3nam": "3y", "3_nam": "3y", "3 năm": "3y", "toan_dai": "toan_dai", "toàn dải": "toan_dai",
                "toan dai": "toan_dai", "full": "toan_dai"}
MAX_DEPTH = 4
CAN = M.CAN
CORE_IDS = ("hs_msn_reflex", "vic_reflexivity_7pha", "soros_7_stage_boom_bust")
MAX_CORE_ROWS = 12
MO_TA_CUT = 220          # library index description
DESC_CUT = 120           # one-line description on a group page
NGUON_CUT = 110          # library index source ("tab + dòng")
AP_DUNG_CUT = 100
MAX_IDS = 8
MAX_MAP_ROWS = 8        # mapping rows of one framework on a group page
DITTO = "″"
CHI_TIET = "chi tiết: TỔNG QUAN · Thư viện khung"
COT_LOI = "cốt lõi"
GENERIC_KEYS = ("bang", "bảng", "nội dung", "noi dung")      # list keys that add nothing to a table title
PHA_KEY = re.compile(r"^(?:pha|phase|stage|giai[\s_]?(?:đoạn|doan)|bước|buoc)(?:$|[\s_])", re.IGNORECASE)
TMP_PATH = re.compile(r"/private/tmp/[^\s,;)\]\"'·]*")
PAREN_PATH = re.compile(r"\s*\([^()\s]*/[^()\s]*\.[A-Za-z0-9]{1,5}\)")   # "JSX v37 (/…/x.jsx) · tab" → "JSX v37 · tab"
HOME_PATHS = ((re.compile(r"/Users/[^/\s]+/SECOND BRAIN-OBSIDIAN/_System/"), "_System/"),
              (re.compile(r"/Users/[^/\s]+/"), ""))

# CỔNG v1.7 DỪNG: words of an order, a rating, a position size or a target price. A source may quote them only as
# frozen history ("ĐÓNG BĂNG · <nguồn> <ngày>"); the engine itself never writes them.
FORBID_UPPER = re.compile(
    r"\b(?:MUA|BÁN|NAV|GIỮ|BUY|SELL|HOLD|ADD|AVOID|REDUCE|ACCUMULATE|OUTPERFORM|UNDERPERFORM|NEUTRAL|OVERWEIGHT|"
    r"UNDERWEIGHT|Buy|Sell|Hold|Add|Avoid|Reduce|Accumulate)\b"
    r"|\b[MOU]\s?-?\s?PF\b"                                 # Vietcap M-PF / O-PF / U-PF
    r"|\bTP\s*[:=]?\s*[−+-]?\s*\d")                         # target price "TP 43.300", "TP −20%" (not TP.HCM)
FORBID_ANY = re.compile(r"tỷ\s+trọng|giá\s+mục\s+tiêu|target\s+price|price\s+target|khuyến\s+nghị|khả\s+quan|"
                        r"outperform|underperform|overweight|underweight", re.IGNORECASE)
# a Vietnamese rating word in rating context: "hạ xuống Giữ", "nâng lên Mua", "Giữ (TP …"
FORBID_RATING = re.compile(
    r"\b(?:xuống|lên|hạ|nâng|duy trì|sang)\s+(?:mức\s+|khuyến\s+nghị\s+)?[«\"“'‘]?(?:Mua|Bán|Giữ|Nắm giữ|Trung lập|"
    r"Tích cực|Tiêu cực)\b"
    r"|\b(?:Mua|Bán|Giữ|Nắm giữ|Trung lập)\b[»\"”'’]?\s*(?:\(\s*(?:TP|giá)\b|→|->)")
NOT_ADVICE = re.compile(r"không\s+phải\s+(?:là\s+)?(?:lời\s+)?khuyến\s+nghị", re.IGNORECASE)   # the disclaimer
# sizing / exit / target vocabulary of trade plans and sell-side tables (recheck 10/10/2026)
FORBID_PLAN = re.compile(
    r"t[ỷỉ]\s+trọng|chốt\s+lời|cắt\s+lỗ|stop[\s-]?loss|\btrim\b|\btargets?\b|market\s+perform|"
    r"phù\s+hợp\s+thị\s+trường|\brating\b|\bupside\b|tactical\s+hold", re.IGNORECASE)
FORBID_CAPS = re.compile(r"\bTRUNG\s+LẬP\b|\bPHÙ\s+HỢP\b|\bTRIM\b"
                         r"|\bT[Pp]\b(?![.\-]?\s*HCM)(?:\s+[^\W\d]+){0,2}\s*[:=]?\s*[−+-]?\s*\d"   # "TP mới 120k", "TP range 90.000"
                         r"|\bTp\b\s*\|")                                                      # "Tp | Upside" table header


# ── guard (CỔNG v1.7 DỪNG) ───────────────────────────────────────────────────


def has_forbidden(text):
    t = NOT_ADVICE.sub(" ", M.nfc((text or "").replace('\\"', '"')))   # NFC: NFD "tỷ trọng" must match too
    return bool(FORBID_UPPER.search(t) or FORBID_ANY.search(t) or FORBID_RATING.search(t) or FORBID_PLAN.search(t)
                or FORBID_CAPS.search(t))


def _dump(o):
    return json.dumps(o, ensure_ascii=False)


def _free(o):
    """A unit (block, row, item, card, tile, line) that carries such words without its own ĐÓNG BĂNG label."""
    t = o if isinstance(o, str) else _dump(o)
    return DONG_BANG not in t and has_forbidden(t)


def _prefix(label, text, sep=" · "):
    text = M.nfc(text)
    return label + (sep + text if text else "")


def _label_row(r, label):
    """Label the first offending cell of a table row (a plain cell before a pill), else the first cell."""
    hits = [i for i, c in enumerate(r) if has_forbidden(c if isinstance(c, str) else _dump(c))]
    plain = [i for i in hits if not (isinstance(r[i], dict) and r[i].get("pill"))]
    i = (plain or hits or [0])[0]
    c = r[i]
    r[i] = dict(c, t=_prefix(label, c.get("t"))) if isinstance(c, dict) else _prefix(label, c)


def _mark(b, label):
    """Label every unit of one block that needs it → number of labels added. Tables, lists, cards, tiles and
    warning lines are checked unit by unit: one frozen row never exempts the rest of its table."""
    kieu = b.get("kieu")
    n = 0
    if kieu == "bang":
        if _free({k: b.get(k) for k in ("cot", "chu_thich", "tieu_de")}):
            b["chu_thich"] = _prefix(label, b.get("chu_thich"))
            n += 1
        for r in M.as_list(b.get("dong")):
            if isinstance(r, list) and r and _free(r):
                _label_row(r, label)
                n += 1
        return n
    if kieu == "danh_sach":
        for it in M.as_list(b.get("muc")):
            if isinstance(it, dict) and _free(it):
                it["tags"] = [label] + M.tier_list(it.get("tags"))
                n += 1
        return n
    if kieu == "the":
        for c in M.as_list(b.get("the")):
            if isinstance(c, dict) and _free(c):
                c["tieu_de"] = _prefix(label, c.get("tieu_de"))
                n += 1
        return n
    if kieu == "o_so":
        for t in M.as_list(b.get("o")):
            if isinstance(t, dict) and _free(t):
                t["phu"] = _prefix(label, t.get("phu"))
                n += 1
        return n
    if kieu == "canh_bao":
        if _free(M.nfc(b.get("tieu_de"))):
            b["tieu_de"] = _prefix(label, b.get("tieu_de"))
            n += 1
        muc = []
        for m in M.as_list(b.get("muc")):
            if isinstance(m, str) and _free(m):
                m = _prefix(label, m)
                n += 1
            muc.append(m)
        b["muc"] = muc
        return n
    if not _free(b):
        return 0
    if kieu == "doan":
        if b.get("the") and M.nfc(b.get("tieu_de")):
            b["tieu_de"] = _prefix(label, b["tieu_de"])
        else:
            b["text"] = _prefix(label, b.get("text"), ": ")
    elif kieu == "bieu_do":
        b["chu_thich"] = _prefix(label, b.get("chu_thich"))
    elif kieu == "trich":
        b["nguon"] = _prefix(label, b.get("nguon"))
    elif kieu == "cong":
        b["phu"] = _prefix(label, b.get("phu"))
    elif kieu == "chips":
        b["chips"] = [{"tier": label, "text": ""}] + M.as_list(b.get("chips"))
    else:
        b["nhan_dong_bang"] = label
    return 1


def nhan_dong_bang(nhan):
    return "%s · %s" % (DONG_BANG, M.nfc(nhan)) if M.nfc(nhan) else DONG_BANG


def guard(blocks, nhan):
    """Label, unit by unit, every block part carrying order / rating / sizing / target-price words without its own
    ĐÓNG BĂNG label → number of labels added."""
    label = nhan_dong_bang(nhan)
    return sum(_mark(b, label) for b in blocks if isinstance(b, dict))


def guard_section(sec, nhan, warnings=None, where=""):
    """guard_blocks() over a section's blocks, plus its header: a title / eyebrow / lede quoting order, rating,
    sizing or target-price words gets the label on the eyebrow."""
    if not isinstance(sec, dict):
        return sec
    head = " ".join(M.nfc(sec.get(k)) for k in ("tieu_de", "eyebrow", "lede"))
    if DONG_BANG not in head and has_forbidden(head):
        sec["eyebrow"] = _prefix(nhan_dong_bang(nhan), sec.get("eyebrow"))
        if warnings is not None:
            L.add_warning(warnings, "%s: tiêu đề mục trích ngôn ngữ lệnh/tỷ trọng của nguồn, gắn %s." % (
                M.nfc(where) or "Mục", nhan_dong_bang(nhan)))
    guard_blocks(M.as_list(sec.get("khoi")), nhan, warnings, where)
    return sec


def guard_blocks(blocks, nhan, warnings=None, where=""):
    """guard() plus one warning per `where` when anything was labelled "ĐÓNG BĂNG · <nhan>" (frozen source
    history, CỔNG v1.7 DỪNG)."""
    if guard(blocks, nhan) and warnings is not None:
        L.add_warning(warnings, "%s trích lệnh, xếp hạng, định cỡ vị thế hoặc mức giá của nguồn: hiển thị như lịch "
                                "sử %s, không chấm lại (CỔNG v1.7 DỪNG)." % (M.nfc(where) or "Nguồn",
                                                                             nhan_dong_bang(nhan)))
    return blocks


# ── generic renderer ─────────────────────────────────────────────────────────


def txt(v):
    """Any JSON value → one display string (Vietnamese numbers, lists joined with " · ")."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "có" if v else "không"
    if isinstance(v, (int, float)):
        return M.fmt_vn(v, 2)
    if isinstance(v, str):
        return M.nfc(v)
    if isinstance(v, list):
        return " · ".join(t for t in (txt(x) for x in v) if t)
    if isinstance(v, dict):
        return "; ".join("%s: %s" % (label(k), txt(x)) for k, x in v.items() if txt(x))
    return M.nfc(str(v))


def label(key):
    s = M.nfc(str(key)).replace("_", " ").strip()
    return (s[:1].upper() + s[1:]) if s else ""


def cut(s, n):
    s = M.nfc(s)
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def ngan(text):
    """Display form of a source string: absolute paths shortened ("/Users/<u>/Downloads/x.html" → "Downloads/x.html",
    "/Users/<u>/SECOND BRAIN-OBSIDIAN/_System/…" → "_System/…", "/private/tmp/…/f.json" → "f.json")."""
    s = TMP_PATH.sub(lambda m: os.path.basename(m.group(0).rstrip("/")) or m.group(0), txt(text))
    for rx, rep in HOME_PATHS:
        s = rx.sub(rep, s)
    return s


def nguon_cell(text, n=None, **kw):
    """A source cell: the shortened (with n, also cut) text and the full string in "tip" when they differ; the
    plain string when nothing changed and no style is asked."""
    full = txt(text)
    short = ngan(full)
    if n:
        short = cut(short, n)
    if short == full and not kw:
        return full
    return M.cell(short, tip=full if short != full else None, **kw)


def ds_ids(ids, n=MAX_IDS):
    ids = list(ids)
    return ", ".join(ids[:n]) + (", …" if len(ids) > n else "")


def _scalar(v):
    return v is None or isinstance(v, (str, int, float, bool))


def render_any(obj, depth=0):
    """Free-form content (str / list / dict, nested) → vnblocks blocks: paragraphs, lists, tables, sub-headings."""
    if depth >= MAX_DEPTH:
        return [M.doan(txt(obj))]
    if _scalar(obj):
        return [M.doan(txt(obj))]
    if isinstance(obj, list):
        if not obj:
            return []
        if all(_scalar(x) for x in obj):
            return [M.danh_sach([{"so": str(i + 1), "text": txt(x)} for i, x in enumerate(obj) if txt(x)])]
        if all(isinstance(x, dict) for x in obj):
            cols = []
            for x in obj:
                for k in x:
                    if k not in cols:
                        cols.append(k)
            return [M.bang([label(k) for k in cols], [[txt(x.get(k)) for k in cols] for x in obj])]
        out = []
        for x in obj:
            out += render_any(x, depth + 1)
        return out
    out, rows = [], []
    for k, v in obj.items():
        if _scalar(v) or (isinstance(v, list) and all(_scalar(x) for x in v) and len(txt(v)) < 160):
            if txt(v):
                rows.append([M.cell(label(k), dam=True), txt(v)])
            continue
        if rows:
            out.append(M.bang(["Mục", "Nội dung"], rows))
            rows = []
        out.append(M.heading(label(k)))
        out += render_any(v, depth + 1)
    if rows:
        out.append(M.bang(["Mục", "Nội dung"], rows))
    return [b for b in out if b]


# ── library ──────────────────────────────────────────────────────────────────


def load_khung(root=None, warnings=None):
    """<root>/khung.json → (library dict with validated "khung" entries | None, path)."""
    warnings = [] if warnings is None else warnings
    path = os.path.join(root or L.reg_dir(), "khung.json")
    if not os.path.isfile(path):
        L.add_warning(warnings, "Chưa có thư viện khung %s (schema %s): bỏ phần khung." % (path, SCHEMA))
        return None, path
    try:
        raw = M.load_json(path)
    except (OSError, ValueError) as exc:
        L.add_warning(warnings, "Không đọc được thư viện khung %s (%s)." % (path, exc))
        return None, path
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        L.add_warning(warnings, "Thư viện khung %s sai schema (cần %s)." % (path, SCHEMA))
        return None, path
    entries, seen = [], set()
    for i, k in enumerate(M.as_list(raw.get("khung"))):
        kid = M.nfc(M.as_dict(k).get("id"))
        if not kid:
            L.add_warning(warnings, "khung.json: mục thứ %d không có id, bỏ qua." % (i + 1))
            continue
        if kid in seen:
            L.add_warning(warnings, "khung.json: id \"%s\" ghi hai lần, giữ mục đầu." % kid)
            continue
        seen.add(kid)
        entries.append(k)
    return dict(raw, khung=entries), path


def ap_dung(entry):
    v = entry.get("ap_dung_cho")
    return [M.nfc(x) for x in (v if isinstance(v, list) else [v]) if M.nfc(x)]


def khung_cho(lib, nhom_id, ids=()):
    """[(entry, rieng)] in library order: rieng = the group (or a dossier mapping) names it explicitly."""
    out = []
    for k in M.as_list((lib or {}).get("khung")):
        targets = ap_dung(k)
        rieng = nhom_id in targets or M.nfc(k.get("id")) in ids
        if rieng or MOI_NHOM in targets:
            out.append((k, rieng))
    return out


def khung_entry(lib, pattern):
    rx = re.compile(pattern, re.IGNORECASE)
    for k in M.as_list((lib or {}).get("khung")):
        if rx.search(M.nfc(k.get("id"))) or rx.search(M.nfc(k.get("ten"))):
            return k
    return None


def lib_index(lib):
    """{id: entry} plus each entry's bi_danh (ids of the frameworks merged into it); an id beats an alias."""
    entries = M.as_list((lib or {}).get("khung"))
    out = {}
    for k in entries:
        out.setdefault(M.nfc(k.get("id")), k)
    for k in entries:
        for b in M.as_list(k.get("bi_danh")):
            out.setdefault(M.nfc(b), k)
    out.pop("", None)
    return out


# ── measurable signs ─────────────────────────────────────────────────────────


def normalize_tham_so(key, tham_so, warnings=None, where=""):
    """Curator spellings → the engine's parameter names (DAU_HIEU[key]). A key ending in _pct / _x / _sigma / _lan
    is read without the suffix; "nguong" / "muc" name the sign's threshold (DAU_HIEU_THAM_SO) when the engine name
    itself is absent; "ma" / "ap_cho" (ticker choice), "cua_so" and the optional DAU_HIEU_PHU keys (pb_sigma "phep")
    are kept. Anything else is dropped with a warning: no guessing which number is the threshold."""
    want = set(L.DAU_HIEU.get(key, {})) | set(L.DAU_HIEU_PHU.get(key, ()))
    pname = L.DAU_HIEU_THAM_SO.get(key)
    out, alias, bo = {}, {}, []
    for k, v in M.as_dict(tham_so).items():
        k = M.nfc(k)
        base = k
        for suf in SUFFIXES:
            if base.endswith(suf) and base[:-len(suf)]:
                base = base[:-len(suf)]
                break
        if base in want:
            out[base] = v
        elif base in ("nguong", "muc"):
            alias.setdefault(base, v)
        elif base in ("ma", "ap_cho"):
            out[base] = v
        else:
            bo.append(k)
    for a in ("nguong", "muc"):
        if a not in alias:
            continue
        if pname and pname not in out:
            out[pname] = alias.pop(a)
        else:
            bo.append(a)
    if "cua_so" in out:
        out["cua_so"] = CUA_SO_ALIAS.get(M.nfc(out["cua_so"]).lower(), M.nfc(out["cua_so"]))
    if bo and warnings is not None:
        L.add_warning(warnings, "%s: tham số lạ %s bị bỏ qua (phép đo %s nhận: %s)." % (
            M.nfc(where) or "Khung", ", ".join("\"%s\"" % x for x in bo), key or "?",
            ", ".join(sorted(want | {"nguong", "muc", "ma"})) if key in L.DAU_HIEU else "khoá phép đo lạ"))
    return out


def gia_tri_txt(key, v):
    if M.finite(v) is None:
        return CAN
    if key == "bung_pha_250":
        return M.k_txt(v)
    if key in ("kl_tuan_tb20", "vuot_ma200", "parabol"):
        return M.x_txt(v)
    if key == "cach_dinh_52t":
        return M.fmt_vn(v, 1, fixed=True) + "% dưới đỉnh"
    if key == "pb_sigma":
        return M.sigma_txt(v)
    if key == "nn_rong_4t":
        return M.ty_txt(v)
    if key in ("lnst_yoy", "tang_tu_day"):
        return M.pct_txt(v)
    if key == "ty_so_holdco_pct":
        return "phân vị " + M.fmt_vn(v, 0) + "%"
    return M.fmt_vn(v, 2)


def thay_txt(v):
    return "ĐÃ THẤY" if v is True else ("CHƯA THẤY" if v is False else CAN)


def thay_mau(v):
    return "lam" if v is True else ("xam" if v is False else "vang")


def tham_so_txt(ts):
    return ", ".join("%s %s" % (k, txt(v)) for k, v in ts.items() if k != "ma") or "mặc định engine"


def targets(lv, d, ts):
    """Tickers a sign is checked on → ([ticker | None (= the group parent, else the base)], [bad values]). "ma" may
    be a ticker, a list of tickers, "me", or "moi_ma"; a value that is not a ticker is reported, never replaced by
    the parent."""
    raw = d.get("ma") or d.get("ap_cho") or ts.pop("ma", None) or ts.pop("ap_cho", None)
    ts.pop("ma", None)
    ts.pop("ap_cho", None)
    out, bad = [], []
    for v in (raw if isinstance(raw, list) else [raw]):
        w = M.nfc(v) if isinstance(v, str) else ("" if v is None else None)
        if w is None:
            bad.append(txt(v))
        elif w.lower() in MOI_MA:
            out += list(lv.priced) if lv is not None else [None]
        elif w.lower() in ("", "me", "mẹ"):
            out.append(None)
        elif L.ticker(w):
            out.append(L.ticker(w))
        else:
            bad.append(w)
    return list(dict.fromkeys(out)), bad


def cham(lv, entry, warnings=None):
    """Rows {"khung", "id", "mo_ta", "khoa", "ma", "thay", "ngay", "gia_tri", "gia_tri_txt", "ghi_chu", "tham_so",
    "tier"} for every measurable sign of one framework on a LiveNhom (None → [CẦN DATA] rows)."""
    out = []
    for d in M.as_list(entry.get("dau_hieu_do_duoc")):
        d = M.as_dict(d)
        key = M.nfc(d.get("phep_do"))
        where = "Khung %s · dấu hiệu %s" % (M.nfc(entry.get("id")) or "?", M.nfc(d.get("id")) or "?")
        ts = normalize_tham_so(key, d.get("tham_so"), warnings, where)
        tickers, bad = targets(lv, d, ts)
        rows = []
        for t in tickers:
            if lv is None or not getattr(lv, "ok", False):
                rows.append({"khoa": key, "ma": t, "thay": None, "ngay": None, "gia_tri": None, "tham_so": ts,
                             "tier": M.T_EST, "ghi_chu": "%s: nhóm không có giá trong kho" % CAN})
            else:
                rows.append(lv.do_dau_hieu(key, t, ts))
        for b in bad:
            rows.append({"khoa": key, "ma": b, "thay": None, "ngay": None, "gia_tri": None, "tham_so": ts,
                         "tier": M.T_EST, "ghi_chu": "%s: \"%s\" không phải mã niêm yết" % (CAN, b)})
        for r in rows:
            r.update({"khung": M.nfc(entry.get("id")), "id": M.nfc(d.get("id")), "mo_ta": M.nfc(d.get("mo_ta")),
                      "gia_tri_txt": gia_tri_txt(key, r.get("gia_tri"))})
            out.append(r)
    return out


def sign_rows(rows, ten_of):
    """Table rows of cham() results: the framework name on the first row of each run of its signs, the sign text and
    its measure on the first row of a sign checked on several tickers."""
    out, prev, prev_sign, prev_note = [], None, None, None
    for r in rows:
        sign, note = (r["khung"], r["id"], r["khoa"]), M.nfc(r.get("ghi_chu"))
        lap = sign == prev_sign
        out.append([M.cell(ten_of.get(r["khung"], r["khung"]), dam=True) if r["khung"] != prev else "",
                    "" if lap else "%s%s" % (("%s · " % r["id"]) if r["id"] else "", r["mo_ta"] or r["khoa"]),
                    r.get("ma") or "–",
                    M.cell(DITTO if lap else "%s · %s" % (r["khoa"], tham_so_txt(r.get("tham_so") or {})), mono=True),
                    M.pill(thay_txt(r["thay"]), thay_mau(r["thay"])),
                    M.cell(M.ddmmyyyy(M.parse_day(r.get("ngay"))) or "–", mono=True),
                    M.cell(r["gia_tri_txt"], mono=True), DITTO if (lap and note == prev_note) else note,
                    M.tier_cell(r.get("tier") or M.T_EST)])
        prev, prev_sign, prev_note = r["khung"], sign, note
    return out


SIGN_COLS = ["Khung", "Dấu hiệu", "Mã", "Phép đo · tham số", "Trạng thái", "Ngày", "Giá trị", "Ghi chú", "Nhãn"]


def nguon_txt(entry):
    return " · ".join(x for x in (txt(entry.get("nguon")), txt(entry.get("tier"))) if x)


def ten_ngan(entry):
    """Short name of a framework: its name up to the first ":" (e.g. "VIC Reflexivity"), else its id."""
    ten = M.nfc(entry.get("ten")).split(":")[0].strip()
    return cut(ten, 60) if ten else M.nfc(entry.get("id"))


def nhu_tren(prev, cur):
    """Display of a source cell under another one: the leading " · " segments it shares with the row above become
    DITTO ("″ · L19410"); the same text is DITTO alone; nothing shared → cur unchanged."""
    if not (prev and cur):
        return cur
    if cur == prev:
        return DITTO
    a, b = prev.split(" · "), cur.split(" · ")
    n = 0
    while n < min(len(a), len(b)) - 1 and a[n] == b[n]:
        n += 1
    return " · ".join([DITTO] + b[n:]) if n else cur


def nguon_rows_cells(texts):
    """Source cells of consecutive table rows: shortened paths, DITTO for what the row above already shows, the full
    string in the tip."""
    out, prev = [], ""
    for t in texts:
        full, short = txt(t), ngan(t)
        shown = nhu_tren(prev, short)
        out.append(M.cell(shown, tip=full) if shown != full else full)
        prev = short
    return out


def entry_blocks(entry, full=True):
    """Heading, description and (when full) the frozen content of one framework."""
    nh = "%s · %s" % (M.nfc(entry.get("ten")) or M.nfc(entry.get("id")), M.nfc(entry.get("loai"))) \
        if M.nfc(entry.get("loai")) else (M.nfc(entry.get("ten")) or M.nfc(entry.get("id")))
    out = [M.heading(nh), M.doan(txt(entry.get("mo_ta")))]
    tiers = M.tier_list(entry.get("tier"))
    out.append({"kieu": "chips", "chips": [{"tier": DONG_BANG, "text": ngan(nguon_txt(entry)) or "khung.json"}] +
                [{"tier": t, "text": ""} for t in tiers]})
    if full and entry.get("noi_dung") not in (None, "", [], {}):
        out += render_any(entry.get("noi_dung"))
    return guard_blocks([b for b in out if b], nguon_txt(entry) or "khung.json")


def render_compact(obj):
    """The top level of free-form content without its nested parts: "Cốt lõi" as a list, short scalar items as a
    table, the names of the other parts in one line (their text stays in khung.json)."""
    if not isinstance(obj, dict):
        return render_any(obj) if (_scalar(obj) or (isinstance(obj, list) and all(_scalar(x) for x in obj))) else []
    out, rows, parts = [], [], []
    for k, v in obj.items():
        if M.nfc(k).lower() == COT_LOI and isinstance(v, list) and all(_scalar(x) for x in v):
            out += render_any(v)
        elif _scalar(v) or (isinstance(v, list) and all(_scalar(x) for x in v) and len(txt(v)) < 160):
            if txt(v):
                rows.append([M.cell(label(k), dam=True), txt(v)])
        else:
            parts.append(label(k))
    if rows:
        out.append(M.bang(["Mục", "Nội dung"], rows))
    if parts:
        out.append(M.doan("Các phần khác, toàn văn %s trong khung.json: %s." % (DONG_BANG, " · ".join(parts)),
                          mau="xam"))
    return [b for b in out if b]


def entry_compact(entry):
    """Heading, description, source chips, "Cốt lõi" and the names of the other parts of one framework."""
    out = entry_blocks(entry, full=False) + render_compact(entry.get("noi_dung"))
    return guard_blocks([b for b in out if b], nguon_txt(entry) or "khung.json")


def main_table(entry):
    """The framework's main stage/phase table → (title, rows): the first list of objects in noi_dung (depth first,
    in file order) with a phase-like key (pha / phase / stage / giai đoạn / bước), else its first list of objects;
    (None, []) when there is none."""
    first = []

    def walk(o, path, depth):
        if depth > MAX_DEPTH:
            return None
        if isinstance(o, list) and o and all(isinstance(x, dict) for x in o):
            if any(PHA_KEY.match(M.nfc(k)) for x in o for k in x):
                return path, o
            if not first:
                first.append((path, o))
            return None
        kids = o.items() if isinstance(o, dict) else (((None, x) for x in o) if isinstance(o, list) else ())
        for k, v in kids:
            hit = walk(v, (path + [label(k)])[-2:] if k is not None else path, depth + 1)
            if hit:
                return hit
        return None
    hit = walk(entry.get("noi_dung"), [], 0) or (first[0] if first else None)
    if not hit:
        return None, []
    path = [x for x in hit[0] if x.lower() not in GENERIC_KEYS] or hit[0][-1:]
    return " · ".join(path) or None, hit[1]


def core_blocks(entry, n=MAX_CORE_ROWS):
    """TỔNG QUAN: the heading and the main stage/phase table (≤ n rows) of one core framework, frozen."""
    title, rows = main_table(entry)
    if not rows:
        return []
    cols = []
    for x in rows:
        for k in x:
            if k not in cols:
                cols.append(k)
    shown = rows[:n]
    note = " · ".join(x for x in (DONG_BANG, cut(ngan(nguon_txt(entry)), NGUON_CUT) or "khung.json",
                                  "%d/%d dòng" % (len(shown), len(rows)), "toàn văn trong khung.json") if x)
    ten = M.nfc(entry.get("ten")) or M.nfc(entry.get("id"))
    out = [M.heading("%s · bảng chính%s" % (ten, (": " + title) if title else "")),
           M.bang([label(k) for k in cols], [[txt(x.get(k)) for k in cols] for x in shown], note)]
    return guard_blocks(out, nguon_txt(entry) or "khung.json")


def mapping_blocks(entry, key, maps, co_lib=True, ho_so=None):
    """The dossier's khung_ap_dung rows of ONE framework (several dossier ids may resolve to the same merged entry):
    a heading, the framework's one-line description (or "khung riêng của hồ sơ" when the library has no such id),
    then one frozen table per dossier mapping, at most MAX_MAP_ROWS rows for the framework (the rest is named in one
    line that points to the dossier file). The framework's own content is never rendered here."""
    ten = (M.nfc(entry.get("ten")) or key) if entry else key
    room, an, an_dong = MAX_MAP_ROWS, [], 0
    rieng = "" if (entry or not co_lib) else " · khung riêng của hồ sơ"
    out = [M.heading("%s · ánh xạ của nguồn: %s%s" % (DONG_BANG, ten, rieng))]
    if entry:
        out.append(M.doan("%s · %s" % (cut(txt(entry.get("mo_ta")) or ten, DESC_CUT), CHI_TIET), mau="xam"))
    for m in maps:
        kid = M.nfc(m.get("khung"))
        ax = [M.as_dict(x) for x in M.as_list(m.get("anh_xa"))]
        phan = txt(m.get("ten")) or txt(m.get("thanh_phan")) or (kid if kid != key else "")
        if len(ax) > room:
            an.append(cut(phan or kid or ten, 36))
            an_dong += len(ax) - room
            ax = ax[:room]
        room -= len(ax)
        if not ax and m.get("anh_xa"):
            continue
        nguon_m = txt(m.get("nguon")) or txt(m.get("khung_nguon"))
        rows = [[M.cell(txt(a.get("pha")), dam=True), M.cell(txt(a.get("thoi_gian")), mono=True),
                 txt(a.get("dau_hieu_da_thay")), c] for a, c in zip(ax, nguon_rows_cells([a.get("nguon") for a in ax]))]
        note = " · ".join(x for x in (DONG_BANG, phan, txt(m.get("ghi_chu")) or "ánh xạ của nguồn, không chấm lại",
                                      txt(m.get("tier")),
                                      "" if (ax and all(txt(a.get("nguon")) for a in ax)) else ngan(nguon_m)) if x)
        out.append(M.bang(["Pha", "Thời gian", "Dấu hiệu nguồn đã thấy", "Nguồn"], rows, note) if rows else
                   M.doan(note, mau="xam"))
    if an:
        out.append(M.doan("%s · còn %d dòng ánh xạ của hồ sơ không hiện (tối đa %d dòng mỗi khung), ở: %s · toàn văn: "
                          "%s · khung_ap_dung." % (DONG_BANG, an_dong, MAX_MAP_ROWS, ds_ids(an, 3),
                                                   ngan(ho_so) if ho_so else "hồ sơ"), mau="xam"))
    return out


def section_khung(lv, lib, nhom_id, khung_ap_dung=None, warnings=None, sid="khung", lib_path=None, ho_so=None):
    """Frameworks of one group, compact: per framework the dossier maps (khung_ap_dung; old ids resolved through
    bi_danh) its one-line description and the group's frozen mapping rows (mapping_blocks); the frameworks applied
    to the group by name only (ap_dung_cho) with a one-line description; every measurable sign of all selected
    frameworks (mapped, explicit, "moi_nhom") checked live, tier EST; the "moi_nhom" ones without a sign in one line.
    Full content stays in khung.json (TỔNG QUAN · Thư viện khung). Dossier ids the library does not know render as
    "khung riêng của hồ sơ" with ONE aggregated warning."""
    warnings = [] if warnings is None else warnings
    idx = lib_index(lib)
    by, order, rieng_hs = {}, [], []
    for m in (x for x in M.as_list(khung_ap_dung) if isinstance(x, dict)):
        kid = M.nfc(m.get("khung"))
        e = idx.get(kid)
        key = M.nfc(e.get("id")) if e else (kid or "?")
        if key not in by:
            by[key] = []
            order.append((key, e))
        by[key].append(m)
        if lib and e is None and kid and kid not in rieng_hs:
            rieng_hs.append(kid)
    mapped = tuple(k for k, e in order if e)
    sel = khung_cho(lib, nhom_id, mapped)
    if not sel and not order:
        return None
    lib_ten = {M.nfc(k.get("id")): ten_ngan(k) for k in M.as_list((lib or {}).get("khung"))}
    khoi = [M.doan("Khung là EST của tác giả, đóng băng theo ngày nguồn. Cột \"Trạng thái\" là kiểm dữ liệu engine chạy "
                   "lại mỗi lần FETCH: %s, không chấm pha và không đưa phán đoán." % NHAN_DAU_HIEU, mau="lam")]
    for key, e in order:
        khoi += mapping_blocks(e, key, by[key], bool(lib), ho_so)
    khac = [k for k, rieng in sel if rieng and M.nfc(k.get("id")) not in mapped]
    if khac:
        khoi += [M.heading("Khung khác áp cho nhóm · hồ sơ không ánh xạ pha"),
                 M.danh_sach([{"so": str(i + 1), "tieu_de": M.nfc(k.get("ten")) or M.nfc(k.get("id")),
                               "text": "%s · %s" % (cut(txt(k.get("mo_ta")), DESC_CUT), CHI_TIET),
                               "tags": M.tier_list(k.get("tier"))} for i, k in enumerate(khac)])]
    rows = []
    for k, _ in sel:
        rows += cham(lv, k, warnings)
    if rows:
        khoi += [M.heading("Dấu hiệu đo được · %s" % NHAN_DAU_HIEU),
                 M.bang(SIGN_COLS, sign_rows(rows, lib_ten),
                        "EST · %s. Trang nhóm chỉ hiện mô tả một dòng, ánh xạ của hồ sơ và dấu hiệu đo được; toàn văn "
                        "từng khung: %s. Ngày = phiên/tuần dữ liệu engine dùng." % (NHAN_DAU_HIEU, CHI_TIET))]
    others = [k for k, rieng in sel if not rieng and not M.as_list(k.get("dau_hieu_do_duoc"))]
    if others:
        khoi.append(M.doan("Khung chung không có dấu hiệu đo được (%d): %s · %s." % (
            len(others), ", ".join(lib_ten.get(M.nfc(k.get("id"))) for k in others), CHI_TIET), mau="xam"))
    if lib_path:
        khoi.append(M.doan("Thư viện khung: %s" % lib_path, mau="xam"))
    if rieng_hs:
        L.add_warning(warnings, "%d khung chỉ có trong hồ sơ (không có trong thư viện): %s" % (len(rieng_hs),
                                                                                             ds_ids(rieng_hs)))
    return M.sec(sid, "Khung áp dụng và dấu hiệu đo được", khoi,
                 eyebrow="Thư viện khung · EST · %s" % NHAN_DAU_HIEU,
                 lede="Ánh xạ pha là của nguồn và giữ nguyên ngày; engine chỉ kiểm từng dấu hiệu có phép đo.")


def nguon_index_cell(entry):
    """Library index source: "<nguồn> · tab · dòng" without a bare file path in brackets, cut; full string in tip."""
    full = txt(entry.get("nguon"))
    shown = cut(PAREN_PATH.sub("", ngan(full)), NGUON_CUT)
    return M.cell(shown, tip=full) if shown != full else full


def ap_dung_cell(entry):
    s = ", ".join("mọi nhóm" if x == MOI_NHOM else x for x in ap_dung(entry)) or "–"
    return M.cell(cut(s, AP_DUNG_CUT), tip=s) if len(s) > AP_DUNG_CUT else s


def section_thu_vien(lib, path, warnings=None, bo_qua=(), cot_loi=CORE_IDS):
    """TỔNG QUAN: a compact index of the library (one row per framework: id/tên, loại, nguồn tab + dòng, áp dụng cho,
    số dấu hiệu đo được, mô tả ≤ MO_TA_CUT ký tự, nhãn) + the main stage/phase table of the core frameworks
    (cot_loi, ≤ MAX_CORE_ROWS rows each, ids in bo_qua skipped). Content frozen; signs are only scored on the group
    pages."""
    if not lib:
        return None
    entries = M.as_list(lib.get("khung"))
    khoi = [M.doan("Thư viện %d khung (%s). Mọi nội dung là EST của tác giả tại ngày nguồn, ĐÓNG BĂNG; dấu hiệu đo "
                   "được chỉ được chấm trên trang từng nhóm (%s)." % (len(entries), path, NHAN_DAU_HIEU), mau="lam")]
    rows = []
    for k in entries:
        kid, ten = M.nfc(k.get("id")), M.nfc(k.get("ten"))
        rows.append([M.cell(("%s (%s)" % (ten, kid)) if ten and ten != kid else kid, dam=True),
                     M.cell(M.nfc(k.get("loai")) or "–", mono=True), nguon_index_cell(k),
                     ap_dung_cell(k), M.cell(str(len(M.as_list(k.get("dau_hieu_do_duoc")))), mono=True),
                     cut(txt(k.get("mo_ta")), MO_TA_CUT), M.tier_cell(txt(k.get("tier")) or M.T_EST)])
    khoi.append(M.bang(["Khung (id)", "Loại", "Nguồn · tab · dòng", "Áp dụng cho", "Dấu hiệu đo được", "Mô tả", "Nhãn"],
                       rows, "%s · mỗi khung là EST của tác giả tại ngày nguồn; toàn văn trong khung.json. Trang nhóm "
                             "hiện mô tả một dòng, ánh xạ của hồ sơ và dấu hiệu đo được (%s)." % (DONG_BANG,
                                                                                             NHAN_DAU_HIEU),
                       can_phai=[4]))
    idx = {M.nfc(k.get("id")): k for k in entries}
    for kid in cot_loi:
        if kid in idx and kid not in bo_qua:
            khoi += core_blocks(idx[kid])
    return M.sec("thu_vien_khung", "Thư viện khung", khoi, eyebrow="Khung xuyên chaebol · ĐÓNG BĂNG · EST")
