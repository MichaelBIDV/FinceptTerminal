#!/usr/bin/env python3
"""
Fincept Terminal — DEEP FA core: loaders, parsers and gate rules (no output shaping, no IO
beyond reading the JSON/markdown layers of the HĐCV Deep FA system).

Consumed by scripts/deepfa.py (the CLI that shapes the panel payload). Stdlib only; runs on
Python 3.9+ (the app's venv-numpy2 is 3.11; the vault tooling is 3.14). Makes NO network
calls. Never raises on a missing or corrupt layer: every loader returns an object whose
`meta` says what happened, so the panel can render "[CẦN DATA]" instead of an error.

Roots (env overrides are used by the tests):
    DEEPFA_VAULT    ~/SECOND BRAIN-OBSIDIAN          (BaoCao_VN30/, BaoCao_HTML/, _System/)
    DEEPFA_TODAY    test hook only: fixes "today" (YYYY-MM-DD) for age / staleness rules

Layer map (path relative to <vault>/_System unless noted) — see deepfa.py docstring §3 for
the tier and freshness threshold of each:
    fa_insight/universe.json · BaoCao_VN30/<TK>_DD-MM-YYYY.md (vault root) ·
    fa_insight/worksheets/<TK>.json · upside_fa/evidence/<TK>.json · early_detection/edi_index.json ·
    early_detection/owner_intent.json · knowledge_os/mgmt_view.json · knowledge_os/source_map.json ·
    fund_holdings/fund_intent_signals.json · knowledge_os/hhp_vn100_valuation.json (+ hhp_vn100_series/) ·
    alpha_spine/ledger_calls.json · vietcap_live/vietcap_fundamentals.json ·
    superdash_v2/output/vietcap_iq/coverage.json · fincept_bridge/state/vc_lk/<TK>/*.json ·
    fincept_bridge/data/lk_hoso/<TK>.json · fincept_bridge/data/fft_langkinh.json ·
    fincept_bridge/data/fft_tin.json · knowledge_os/primary_filings/primary_facts.json

Hard rules encoded here (deepfa-hoidongcovanai skill / HANDOFF_PROJECT_DEEPFA 10/09/2026):
    * staleness gate: a layer older than STALE_DAYS (45) is tagged UNVERIFIED — never silently used;
    * GATE LVF: fund-intent ACCUMULATION may only be shown after removing new-fund deployments
      (|Δshares − held| < 1 % of held) and index ETFs (E1VFVN30 / FUEVFVND / Fubon); a stale
      fund-intent file makes the whole gate blind (GATE-BLIND), never "no accumulation";
    * a target price older than TP_STALE_DAYS (90) is flagged, never ranked by upside;
    * the alpha-spine ledger with open == total is a mark-to-market snapshot, not a track record;
    * every number carries t (data date), b (tier) and n (source) — see `num()`.
"""

import glob
import json
import math
import os
import re
from datetime import date, datetime, timedelta, timezone

ICT = timezone(timedelta(hours=7), "ICT")

STALE_DAYS = 45          # layer age above this → UNVERIFIED (skill: "fail loud, đừng im lặng dùng số cũ")
WARN_DAYS = 14           # 🟡 between WARN_DAYS and STALE_DAYS
TP_STALE_DAYS = 90       # sell-side target price older than this is flagged (SPEC_GOI_NGUON rule 6)
MEMO_REGEN_DAYS = 90     # memo older than this → "cần regen"
INDEX_ETFS = ("E1VFVN30", "FUEVFVND", "FUBON", "FUEVN100", "FUESSVFL", "FUEMAV30")
FLOW_CACHE_VER = 2       # bump when vc_price_flow's summary shape/logic changes (entries with another _v are recomputed)
NEW_FUND_TOL = 0.01      # |Δshares − shares_held| < 1 % → NAV deployment of a new fund, not conviction

TICKER_RE = re.compile(r"^[A-Z0-9]{2,6}$")
MEMO_NAME_RE = re.compile(r"^([A-Z0-9]{2,6})_(\d{2})-(\d{2})-(\d{4})\.md$")
# H1 of a memo: "# FPT — FPT Corporation (HOSE:FPT) · 73.600đ [CIQ·09/06] · **State B — Variant watch**"
H1_RE = re.compile(r"^#\s+(\S+)\s+[—–-]+\s+(.+?)\s+·\s+([\d.,]+)\s*đ?\s+\[([^\]·]+)·([^\]]+)\]\s+·\s+(.+)$")
STATE_RE = re.compile(r"State\s*\*{0,2}\s*([ABCD])\b")
SECTION_RE = re.compile(r"^##\s+(.*)$")
BREAK_RE = re.compile(r"(?i)(điểm gãy của thesis[^.\n]*[.!]?[^\n]*)")
TAG_RE = re.compile(r"\[(FACT-T1|FACT-T2|SS-T3|EST|NEWS|UNVERIFIED|CIQ|HSC|Vietcap[^\]]*|edi_index|mgmt_view|source_map|fund_intent|owner_intent|BCTN|BCTC[^\]]*|DHCD[^\]]*)[^\]]*\]")
NEED_RE = re.compile(r"\[CẦN [^\]]+\]|\[CAN [^\]]+\]")
DATE_HINT_RE = re.compile(r"(\d{1,2})/(\d{4})|Q([1-4])/(\d{4})|(\d{1,2})/(\d{1,2})/(\d{4})|(?:cuối|đầu|giữa)\s+(\d{1,2})/(\d{4})|(\d{4})")


# ── small helpers ────────────────────────────────────────────────────────────


def today():
    """Date the rules are evaluated against (DEEPFA_TODAY hook for deterministic tests)."""
    t = os.environ.get("DEEPFA_TODAY")
    if t:
        try:
            return datetime.strptime(t[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    return datetime.now(ICT).date()


def finite(v):
    """float or None (bool, str, NaN and ±Inf are not numbers here)."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(float(v)) else None
    if isinstance(v, str):
        s = v.strip().replace("−", "-")
        try:
            f = float(s)
            return f if math.isfinite(f) else None
        except ValueError:
            return None
    return None


def parse_day(value):
    """Best-effort date from ISO / 'DD/MM/YYYY' / 'DD-MM-YYYY' / 'DD/MM' (year unknown → None)."""
    if not value:
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%d-%m-%Y", "%d-%b-%y"):
        try:
            return datetime.strptime(s[: len(datetime.now().strftime(fmt)) + 2].split("+")[0].split(".")[0], fmt).date()
        except ValueError:
            continue
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def iso(d):
    return d.isoformat() if isinstance(d, date) else None


def age_days(d, ref=None):
    if not isinstance(d, date):
        return None
    return (ref or today()) - d


def age_int(d, ref=None):
    a = age_days(d, ref)
    return a.days if a is not None else None


def num(v, u="", t=None, b="", n="", g=None, txt=None):
    """The one number shape of the module: value · unit · data date · tier · source · note.
    A missing value is `v: null` with the note carrying the reason — never 0, never a guess."""
    return {"v": v, "u": u, "t": t, "b": b, "n": n, "g": g, "txt": txt if txt is not None else fmt_vn(v)}


def fmt_vn(v, dec=None, plus=False, unit=""):
    """Vietnamese display: decimal comma, thousands dot, U+2212 minus. None → '[CẦN DATA]'."""
    f = finite(v)
    if f is None:
        return "[CẦN DATA]"
    if dec is None:
        dec = 0 if abs(f) >= 100 or float(f).is_integer() else (1 if abs(f) >= 10 else 2)
    s = "{:,.{d}f}".format(abs(f), d=dec)
    s = s.replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")
    if f < 0:
        s = "−" + s
    elif plus and f > 0:
        s = "+" + s
    return s + unit


def fmt_pct(v, dec=1, plus=True):
    f = finite(v)
    return "[CẦN DATA]" if f is None else fmt_vn(f, dec, plus) + "%"


def fmt_date(d):
    """date/ISO → 'DD/MM/YYYY' for display."""
    dd = d if isinstance(d, date) else parse_day(d)
    return dd.strftime("%d/%m/%Y") if dd else "[CẦN DATA]"


def clean(obj):
    """Recursively replace NaN / ±Inf (json.load accepts them) with null."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    return obj


# ── roots and layer registry ─────────────────────────────────────────────────


def vault():
    return os.environ.get("DEEPFA_VAULT") or os.path.join(os.path.expanduser("~"), "SECOND BRAIN-OBSIDIAN")


def sysdir(*parts):
    return os.path.join(vault(), "_System", *parts)


class Layer(object):
    """One data layer on disk: path, mtime, inner as-of, age, status light and tier."""

    def __init__(self, key, path, tier, inner=None, warn_days=WARN_DAYS, stale_days=STALE_DAYS, label=""):
        self.key, self.path, self.tier, self.label = key, path, tier, label or key
        self.exists = os.path.isfile(path)
        self.mtime = None
        self.error = None
        if self.exists:
            try:
                self.mtime = datetime.fromtimestamp(os.path.getmtime(path), ICT)
            except OSError as exc:
                self.error = str(exc)
        self.inner = inner            # data date inside the file (hop-2), when the loader knows it
        self.warn_days, self.stale_days = warn_days, stale_days

    def asof(self):
        """Date the layer speaks for: inner as-of first, else file mtime."""
        d = parse_day(self.inner) if self.inner else None
        if d:
            return d
        return self.mtime.date() if self.mtime else None

    def age(self):
        return age_int(self.asof())

    def status(self):
        """'ok' | 'warn' | 'stale' | 'missing' — stale ⇒ the layer's numbers are UNVERIFIED."""
        if not self.exists:
            return "missing"
        a = self.age()
        if a is None:
            return "warn"
        if a > self.stale_days:
            return "stale"
        if a > self.warn_days:
            return "warn"
        return "ok"

    def light(self):
        return {"ok": "🟢", "warn": "🟡", "stale": "🔴", "missing": "⚫"}[self.status()]

    def effective_tier(self):
        return "UNVERIFIED" if self.status() in ("stale", "missing") else self.tier

    def to_json(self):
        a = self.age()
        return {
            "key": self.key, "label": self.label, "path": self.path, "exists": self.exists,
            "tier": self.tier, "tier_hieu_luc": self.effective_tier(),
            "as_of": iso(self.asof()), "as_of_txt": fmt_date(self.asof()) if self.asof() else "[CẦN DATA]",
            "age_days": a, "age_txt": ("%d ngày" % a) if a is not None else "[CẦN DATA]",
            "status": self.status(), "light": self.light(), "error": self.error,
        }


def load_json(path):
    """(obj, error). Never raises."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh), None
    except (OSError, ValueError) as exc:
        return None, "%s: %s" % (os.path.basename(path), exc)


def _first(d, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d.get(k)
    return None


# ── universe ─────────────────────────────────────────────────────────────────


def load_universe():
    path = sysdir("fa_insight", "universe.json")
    obj, err = load_json(path)
    tickers = {}
    if isinstance(obj, dict) and isinstance(obj.get("tickers"), dict):
        tickers = obj["tickers"]
    layer = Layer("universe", path, "EST", inner=(obj or {}).get("as_of") if isinstance(obj, dict) else None,
                  warn_days=60, stale_days=120, label="Universe (fa_insight/universe.json)")
    layer.error = layer.error or err
    return {"tickers": tickers, "meta": layer, "n": len(tickers)}


# ── memo (BaoCao_VN30) ───────────────────────────────────────────────────────


def memo_dir():
    return os.path.join(vault(), "BaoCao_VN30")


def list_memos():
    """{TK: [(date, path)...] newest last} over BaoCao_VN30."""
    out = {}
    for p in glob.glob(os.path.join(memo_dir(), "*.md")):
        m = MEMO_NAME_RE.match(os.path.basename(p))
        if not m:
            continue
        tk, dd, mm, yy = m.groups()
        try:
            d = date(int(yy), int(mm), int(dd))
        except ValueError:
            continue
        out.setdefault(tk, []).append((d, p))
    for tk in out:
        out[tk].sort()
    return out


def find_memo(tk, memos=None):
    memos = memos if memos is not None else list_memos()
    lst = memos.get(tk) or []
    return lst[-1] if lst else (None, None)


def split_sections(body):
    """'## heading' blocks → [{"heading", "key", "text"}] in file order. key ∈ §1..§8 | 🔬 | 🧭 | other."""
    sections, cur = [], None
    for line in body.split("\n"):
        m = SECTION_RE.match(line)
        if m:
            heading = m.group(1).strip()
            key = "other"
            km = re.match(r"§\s*(\d)", heading)
            if km:
                key = "§" + km.group(1)
            elif heading.startswith("🔬"):
                key = "🔬"
            elif heading.startswith("🧭"):
                key = "🧭"
            cur = {"heading": heading, "key": key, "text": ""}
            sections.append(cur)
        elif cur is not None:
            cur["text"] += line + "\n"
    for s in sections:
        s["text"] = s["text"].strip()
    return sections


def parse_memo(path):
    """Header, preamble, sections and derived facts of one memo. Numbers in the memo are the
    memo's own (dated by the memo); nothing here is recomputed."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            txt = fh.read()
    except OSError as exc:
        return {"error": str(exc)}
    lines = txt.split("\n")
    h1 = next((l for l in lines if l.startswith("# ")), "")
    info = {"ticker": os.path.basename(path).split("_")[0], "name": "", "exchange": "", "price": None,
            "price_src": "", "price_date": "", "state": None, "state_label": "", "h1": h1.lstrip("# ").strip()}
    m = H1_RE.match(h1)
    if m:
        info["ticker"] = m.group(1)
        nm = m.group(2)
        ex = re.search(r"\((HOSE|HSX|HNX|UPCOM):\s*\w+\)", nm)
        if ex:
            info["exchange"] = ex.group(1)
            nm = re.sub(r"\s*\((HOSE|HSX|HNX|UPCOM):\s*\w+\)", "", nm)
        info["name"] = nm.strip()
        info["price"] = finite(m.group(3).replace(".", "").replace(",", "."))
        info["price_src"] = m.group(4).strip()
        info["price_date"] = m.group(5).strip()
        st = re.sub(r"\*+", "", m.group(6)).strip()
        st = re.sub(r"\s*\(codex run[^)]*\)\s*", "", st)
        info["state_label"] = st
    sm = STATE_RE.search(h1)
    info["state"] = sm.group(1) if sm else None
    body_start = next((i for i, l in enumerate(lines) if l.startswith("## ")), len(lines))
    h1_idx = next((i for i, l in enumerate(lines) if l.startswith("# ")), 0)
    info["preamble"] = "\n".join(lines[h1_idx + 1:body_start]).strip()
    body = "\n".join(lines[body_start:]).strip()
    sections = split_sections(body)
    info["sections"] = sections
    by = {}
    for s in sections:
        by.setdefault(s["key"], s)
    info["by_key"] = by
    info["deep"] = "TENSION GIỮA CÁC DÒNG PHIẾU" in txt
    # preamble facts
    pre = info["preamble"]
    eng = re.search(r"engine\s+`([^`]+)`", pre)
    info["engine"] = eng.group(1) if eng else None
    conf = re.search(r"confidence\s+([\d.,]+)", pre)
    info["confidence"] = finite(conf.group(1).replace(",", ".")) if conf else None
    reg = re.search(r"regime\s+\*{0,2}([A-Z ]+?)\*{0,2}\s*·", pre)
    info["regime"] = reg.group(1).strip() if reg else None
    nav = re.search(r"Danh mục hiện\s+([\d.,]+)\s*%", pre)
    info["nav_pct_memo"] = finite(nav.group(1).replace(",", ".")) if nav else None
    # break point — the sentence §2 must end with ("điểm gãy của thesis là…"). Rule, in order:
    #   1. first sentence of §2 containing "điểm gãy"; 2. first "gãy nếu" item of §7 (falsifiable
    #   break conditions); 3. null + note — a memo without a stated break point is a rigor flag
    #   (skill: "memo không có điểm gãy là memo hỏng"), never a sentence invented here.
    info["break_point"], info["break_point_src"] = None, None
    s2 = (by.get("§2") or {}).get("text") or ""
    for sent in re.split(r"(?<=[.!?])\s+", s2.replace("\n", " ")):
        if "điểm gãy" in sent.lower():
            info["break_point"], info["break_point_src"] = sent.strip().strip("*"), "§2"
            break
    if info["break_point"] is None:
        gay = parse_conditions((by.get("§7") or {}).get("text")).get("gay") or []
        if gay:
            info["break_point"], info["break_point_src"] = gay[0]["text"], "§7 (gãy nếu)"
    # evidence-tag density (rigor: Evidence Density) and unresolved [CẦN …]
    info["n_tags"] = len(TAG_RE.findall(txt))
    info["n_need"] = len(NEED_RE.findall(txt))
    info["n_words"] = len(txt.split())
    return info


def parse_conditions(text):
    """§7 → {"dung": [...], "gay": [...], "lich": [...]} — each item {"text", "date_hint", "due"}.
    Date hints are extracted only when the memo wrote one; nothing is invented."""
    out = {"dung": [], "gay": [], "lich": []}
    if not text:
        return out
    bucket = None
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        is_head = line.startswith("**") or line.rstrip().endswith(":") or line.startswith("#")
        # Heading variants seen across memo vintages (06/2026 and 09/2026):
        #   "**Thesis đúng (State B → A) nếu:**" · "**Thesis gãy nếu:**" · "**Điểm gãy của thesis là:**"
        #   "**Lịch theo dõi dated:**" · "Lịch có ngày:" · "**Lịch cần theo dõi (dated khi có filing):**"
        if is_head and ("thesis đúng" in low or "đúng nếu" in low):
            bucket = "dung"
            continue
        if is_head and ("thesis gãy" in low or "gãy nếu" in low or "điểm gãy" in low):
            bucket = "gay"
            continue
        if is_head and low.lstrip("*# ").startswith("lịch"):
            bucket = "lich"
            continue
        if bucket is None:
            continue
        if line.startswith("---"):
            continue
        item = re.sub(r"^(\d+\.|[-*•])\s*", "", line).strip()
        if not item:
            continue
        due = None
        hint = None
        for mm in DATE_HINT_RE.finditer(item):
            g = mm.groups()
            if g[0] and g[1]:                       # MM/YYYY
                hint, due = mm.group(0), _month_end(int(g[1]), int(g[0]))
            elif g[2] and g[3]:                     # Qn/YYYY
                q = int(g[2]); hint, due = mm.group(0), _month_end(int(g[3]), q * 3)
            elif g[4] and g[5] and g[6]:            # DD/MM/YYYY
                hint = mm.group(0)
                try:
                    due = date(int(g[6]), int(g[5]), int(g[4]))
                except ValueError:
                    due = None
            elif g[7] and g[8]:                     # cuối/đầu/giữa MM/YYYY
                hint, due = mm.group(0), _month_end(int(g[8]), int(g[7]))
            if due:
                break
        out[bucket].append({"text": item, "date_hint": hint, "due": iso(due)})
    return out


def _month_end(y, m):
    try:
        if m == 12:
            return date(y, 12, 31)
        return date(y, m + 1, 1) - timedelta(days=1)
    except ValueError:
        return None


# ── worksheet (Lớp 2) ────────────────────────────────────────────────────────


def load_worksheet(tk):
    path = sysdir("fa_insight", "worksheets", tk + ".json")
    obj, err = load_json(path)
    layer = Layer("worksheet", path, "FACT-T1", inner=(obj or {}).get("as_of") if isinstance(obj, dict) else None,
                  label="Worksheet filing gốc (fa_insight/worksheets)")   # 45-day rule like every file; regen after a new BCTC period
    layer.error = layer.error or err
    return {"data": obj if isinstance(obj, dict) else None, "meta": layer}


# ── evidence (Lớp 1) ─────────────────────────────────────────────────────────


def load_evidence(tk):
    path = sysdir("upside_fa", "evidence", tk + ".json")
    obj, err = load_json(path)
    inner = (obj or {}).get("generated_at") if isinstance(obj, dict) else None
    layer = Layer("evidence", path, "SS-T3", inner=inner,
                  label="Evidence broker (upside_fa/evidence)")            # 45-day rule like every file
    layer.error = layer.error or err
    return {"data": obj if isinstance(obj, dict) else None, "meta": layer}


# ── shared JSON layers (loaded once per run) ─────────────────────────────────


def load_layer(key, relpath, tier, inner_keys=("generated_at", "as_of", "cap_nhat"), label="", **kw):
    path = sysdir(*relpath) if isinstance(relpath, (list, tuple)) else sysdir(relpath)
    obj, err = load_json(path)
    inner = None
    if isinstance(obj, dict):
        inner = _first(obj, *inner_keys)
        if inner is None and isinstance(obj.get("meta"), dict):
            inner = _first(obj["meta"], "generated", "as_of", "generated_at")
        if inner is None and isinstance(obj.get("_meta"), dict):
            inner = _first(obj["_meta"], "as_of", "generated_at")
    layer = Layer(key, path, tier, inner=inner, label=label or key, **kw)
    layer.error = layer.error or err
    return {"data": obj, "meta": layer}


def load_shared():
    """All cross-ticker layers. Big files are loaded once; doc_catalog (17 MB) is NOT loaded —
    primary_facts.json carries the per-ticker filing counts instead."""
    S = {}
    S["edi"] = load_layer("edi", ("early_detection", "edi_index.json"), "EST", label="EDI (early_detection/edi_index.json)")
    S["owner"] = load_layer("owner", ("early_detection", "owner_intent.json"), "FACT-T2", inner_keys=("updated",),
                            label="Ý đồ chủ thể (early_detection/owner_intent.json)")
    S["mgmt"] = load_layer("mgmt", ("knowledge_os", "mgmt_view.json"), "FACT-T2", label="BLĐ tone (knowledge_os/mgmt_view.json)")
    S["smap"] = load_layer("smap", ("knowledge_os", "source_map.json"), "SS-T3", label="Street/nguồn (knowledge_os/source_map.json)")
    S["fund"] = load_layer("fund", ("fund_holdings", "fund_intent_signals.json"), "FACT-T2",
                           label="Fund intent 117 quỹ (fund_holdings/fund_intent_signals.json)")
    S["hhp"] = load_layer("hhp", ("knowledge_os", "hhp_vn100_valuation.json"), "EST", warn_days=2, stale_days=7,
                          label="HHP σ-band (knowledge_os/hhp_vn100_valuation.json)")
    S["ledger"] = load_layer("ledger", ("alpha_spine", "ledger_calls.json"), "EST", inner_keys=("updated",),
                             label="Alpha spine ledger (alpha_spine/ledger_calls.json)")
    S["vf"] = load_layer("vf", ("vietcap_live", "vietcap_fundamentals.json"), "FACT-T2", warn_days=2, stale_days=7,
                         label="Vietcap IQ fundamentals (vietcap_live/vietcap_fundamentals.json)")
    S["cov"] = load_layer("cov", ("superdash_v2", "output", "vietcap_iq", "coverage.json"), "SS-T3", warn_days=2, stale_days=14,
                          label="Vietcap coverage-universe (superdash_v2/output/vietcap_iq/coverage.json)")
    S["fftlk"] = load_layer("fftlk", ("fincept_bridge", "data", "fft_langkinh.json"), "EST", warn_days=2, stale_days=14,
                            label="Lăng kính FFT (fincept_bridge/data/fft_langkinh.json)")
    S["ffttin"] = load_layer("ffttin", ("fincept_bridge", "data", "fft_tin.json"), "FACT-T2", warn_days=3, stale_days=14,
                             label="Sự kiện tự động (fincept_bridge/data/fft_tin.json)")
    S["pf"] = load_layer("pf", ("knowledge_os", "primary_filings", "primary_facts.json"), "FACT-T1", stale_days=120, warn_days=60,
                         label="Primary facts tier-3 (knowledge_os/primary_filings/primary_facts.json)")
    S["fflow"] = load_layer("fflow", ("fund_holdings", "fund_flows.json"), "FACT-T2",
                            label="Dòng tiền quỹ NAV/flow (fund_holdings/fund_flows.json)")
    S["etfc"] = load_layer("etfc", ("fund_holdings", "etf_forecast.json"), "SS-T3",
                           label="Dự báo ETF kỳ review — Vietcap (fund_holdings/etf_forecast.json)")
    # fft_tin: freshness is per source (moi_nhat), the file's cap_nhat may sit still for hours (owner's rule)
    tin = S["ffttin"]["data"]
    if isinstance(tin, dict):
        S["ffttin"]["meta"].inner = _fft_tin_inner(tin)
        S["ffttin"]["phien_ban_ok"] = tin.get("phien_ban") == 1
    return S


def _fft_tin_inner(tin):
    best = None
    for src in tin.get("nguon_tin") or []:
        d = parse_day((src or {}).get("moi_nhat"))
        if d and (best is None or d > best):
            best = d
    return iso(best)


def by_ticker(layer, tk):
    d = (layer or {}).get("data")
    if not isinstance(d, dict):
        return None
    for key in ("by_ticker", "signals", "facts", "ma"):
        v = d.get(key)
        if isinstance(v, dict) and tk in v:
            return v[tk]
    return d.get(tk) if isinstance(d.get(tk), dict) else None


# ── GATE LVF (fund intent) ───────────────────────────────────────────────────


def etf_forecast_for(tk, etfc):
    """Vietcap's forecast of ETF basket buy/sell for `tk` at the next index review (fund_holdings/etf_forecast.json,
    SS-T3). Returns None when the layer or the ticker is absent; a stale layer degrades the tier, never the number."""
    d = (etfc or {}).get("data")
    meta = (etfc or {}).get("meta")
    if not isinstance(d, dict) or not tk:
        return None
    row = (d.get("tickers") or {}).get(tk)
    if not isinstance(row, dict):
        return None
    parts = []
    for key, lab in (("vn30_cp", "VN30"), ("diamond_cp", "DIAMOND"), ("finlead_cp", "FINLEAD")):
        v = finite(row.get(key))
        if v is not None:
            parts.append("%s %s cp" % (lab, fmt_vn(v, 0, True)))
    tong, days = finite(row.get("tong_cp")), finite(row.get("so_ngay_gd"))
    txt = " · ".join(parts) if parts else "[CẦN DATA]"
    if tong is not None:
        txt += " = tổng %s cp" % fmt_vn(tong, 0, True)
    if days is not None:
        txt += " (%s ngày KLGD 30p)" % fmt_vn(days, 2)
    if not d.get("window"):
        txt += " · hiệu lực [CẦN DATA]"
    return {"tong_cp": tong, "so_ngay_gd": days, "vn30_cp": finite(row.get("vn30_cp")), "diamond_cp": finite(row.get("diamond_cp")),
            "finlead_cp": finite(row.get("finlead_cp")), "w_vn30": row.get("w_vn30"), "w_diamond": row.get("w_diamond"), "w_finlead": row.get("w_finlead"),
            "window": d.get("window"), "t": iso(meta.asof()) if meta else d.get("as_of"), "b": meta.effective_tier() if meta else "SS-T3",
            "n": "fund_holdings/etf_forecast.json ← Vietcap IQ funds?tab=forecast (Excel)", "txt": txt}


def fund_nav_caveat(S):
    """Fixed caveat for every fund-intent read: the universe Excel carries the EXPORT date; the 1M net is built
    from daily-NAV funds only (quarterly/member funds and funds without NAV contribute 0/null). Counts come
    from fund_flows.json of the same export; None when that layer is absent."""
    d = (S.get("fflow") or {}).get("data")
    if not isinstance(d, dict):
        return None
    c = d.get("counts") or {}
    old = c.get("nav_date_older_than_30d")
    nul = sum(1 for f in (d.get("funds") or {}).values() if isinstance(f, dict) and not f.get("nav_date"))
    return "as_of = ngày xuất Excel (tháng báo cáo [CẦN DATA]); 1M net chỉ gồm quỹ NAV ngày — %s quỹ NAV >30 ngày và %d quỹ không NAV không đóng góp" % (
        fmt_vn(old, 0) if old is not None else "?", nul)


def fund_detail_available(S):
    """True when the current fund_intent snapshot carries per-fund detail (top_accumulators) for at least one ticker."""
    d = (S.get("fund") or {}).get("data")
    if not isinstance(d, dict):
        return False
    if d.get("detail_period_tickers"):
        return True
    return any(isinstance(v, dict) and (v.get("has_fund_detail") or v.get("top_accumulators_1m")) for v in (d.get("signals") or {}).values())


def gate_lvf(sig, layer, etfc=None, tk=None):
    """Apply the LVF gate to one fund-intent signal. Returns the gated reading:
    {"trang_thai": "GATE-BLIND"|"ok"|"none", "nhan_tho", "nhan_sau_gate", "co_hoc_cp", "active_cp", "chua_loc",
     "loai_bo": [{fund, shares_chg_1m, ly_do}], "etf_du_bao", ...}. A stale layer ⇒ GATE-BLIND (no label at all).
    A fresh snapshot WITHOUT per-fund detail (only the universe Excel was exported) ⇒ trang_thai "ok" but
    chua_loc=True: the raw all-funds net is shown, no direction is voted, ETF/new-fund mechanics cannot be stripped."""
    st = layer.status() if layer else "missing"
    etf = etf_forecast_for(tk or (sig.get("ticker") if isinstance(sig, dict) else None), etfc)
    if st in ("stale", "missing"):
        return {"trang_thai": "GATE-BLIND", "ly_do": "fund_intent_signals.json %s (%s) — GATE LVF mù, cấm gán ACCUMULATION"
                % ("thiếu" if st == "missing" else "quá %d ngày" % STALE_DAYS, layer.age() if layer else "?"),
                "nhan_tho": None, "nhan_sau_gate": None, "etf_du_bao": etf}
    if not isinstance(sig, dict):
        return {"trang_thai": "none", "ly_do": "mã không có trong fund_intent_signals", "nhan_tho": None, "nhan_sau_gate": None, "etf_du_bao": etf}
    net = ((sig.get("net_change") or {}).get("m1") or {}).get("shares")
    acc = sig.get("top_accumulators_1m") or []
    if not acc and not sig.get("has_fund_detail"):
        nr, nf = finite(net), finite(sig.get("num_funds"))
        # GATE LVF runs BEFORE any label: without per-fund rows the ETF/new-fund mechanics cannot be stripped,
        # so no ACCUMULATION/DISTRIBUTION word is emitted at all — only the raw net with its date.
        return {"trang_thai": "CHƯA LỌC", "chua_loc": True,
                "ly_do": "CHƯA LỌC — kỳ %s chỉ có Excel universe (net thô %s cp 1M · %s quỹ); thiếu Funds_holdings_detail per-quỹ nên không tách ETF rổ/quỹ mới → không gán ACCUMULATION/DISTRIBUTION"
                         % (fmt_date(layer.asof()) if layer else "?", (fmt_vn(nr / 1e6, 1, True) + "M") if nr is not None else "[CẦN DATA]", fmt_vn(nf, 0)),
                "nhan_tho": None, "nhan_sau_gate": "chưa qua gate LVF — không gán nhãn",
                "net_1m_cp": nr, "co_hoc_cp": 0.0, "active_cp": None, "loai_bo": [],
                "num_funds": finite(sig.get("num_funds")), "pct_os": finite(sig.get("pct_outstanding")),
                "net_change": sig.get("net_change"), "top_distributors_1m": [], "as_of": iso(layer.asof()) if layer else None,
                "etf_du_bao": etf}
    removed, mech = [], 0.0
    for f in acc:
        name = str(f.get("fund") or "").upper()
        chg = finite(f.get("shares_chg_1m")) or 0.0
        held = finite(f.get("shares_held"))
        why = None
        if any(e in name for e in INDEX_ETFS):
            why = "ETF rổ (mua cơ học theo chỉ số)"
        elif held and held > 0 and abs(chg - held) < NEW_FUND_TOL * held:
            why = "quỹ mới: Δ ≈ toàn bộ lượng nắm (NAV deployment)"
        if why:
            removed.append({"fund": f.get("fund"), "shares_chg_1m": chg, "ly_do": why})
            mech += chg
    active = (finite(net) - mech) if finite(net) is not None else None
    raw = sig.get("signal_1m")
    if active is None:
        label = None
    elif active > 0:
        label = "ACCUMULATION (sau gate)"
    elif active < 0:
        label = "DISTRIBUTION (sau gate)"
    else:
        label = "TRUNG TÍNH (sau gate)"
    return {"trang_thai": "ok", "chua_loc": False, "ly_do": None, "nhan_tho": raw, "nhan_sau_gate": label,
            "net_1m_cp": finite(net), "co_hoc_cp": mech, "active_cp": active, "loai_bo": removed,
            "num_funds": finite(sig.get("num_funds")), "pct_os": finite(sig.get("pct_outstanding")),
            "net_change": sig.get("net_change"), "top_distributors_1m": sig.get("top_distributors_1m") or [],
            "as_of": iso(layer.asof()) if layer else None, "etf_du_bao": etf}


# ── Vietcap IQ cache (state/vc_lk) ───────────────────────────────────────────


def vc_lk_dir(tk):
    return sysdir("fincept_bridge", "state", "vc_lk", tk)


def load_vc_endpoint(tk, ep):
    """{"meta", "rows"} — rows normalised to list[dict] whatever the cache shape (cot/hang or list)."""
    path = os.path.join(vc_lk_dir(tk), ep + ".json")
    obj, err = load_json(path)
    if not isinstance(obj, dict):
        return {"meta": None, "rows": [], "error": err or "missing", "path": path}
    meta = obj.get("meta") if isinstance(obj.get("meta"), dict) else {}
    dl = obj.get("du_lieu")
    rows = []
    if isinstance(dl, dict) and isinstance(dl.get("cot"), list) and isinstance(dl.get("hang"), list):
        cols = dl["cot"]
        for h in dl["hang"]:
            if isinstance(h, list):
                rows.append(dict(zip(cols, h)))
            elif isinstance(h, dict):
                rows.append(h)
    elif isinstance(dl, list):
        rows = [r for r in dl if isinstance(r, dict)]
    elif isinstance(dl, dict):
        rows = [dl]
    return {"meta": meta, "rows": rows, "error": None, "path": path}


def _sorted_by_date(rows, key="tradingDate"):
    def k(r):
        d = parse_day(r.get(key))
        return d or date.min
    return sorted(rows, key=k)


def flow_cache_path():
    """Per-ticker summary cache of vc_price_flow (the 1.5 MB price-history files make a 247-row
    overview cost ~16 s uncached). Lives in the vault, never inside the signed app bundle.
    DEEPFA_FLOW_CACHE=off disables it (tests)."""
    return sysdir("fincept_bridge", "state", "deepfa", "flow_cache.json")


def _src_stamp(tk):
    """mtime signature of the three cache files a flow summary depends on."""
    parts = []
    for ep in ("price-history", "proprietary-history", "ratio-daily"):
        p = os.path.join(vc_lk_dir(tk), ep + ".json")
        try:
            parts.append("%s:%d" % (ep, int(os.path.getmtime(p))))
        except OSError:
            parts.append("%s:-" % ep)
    return "|".join(parts)


def vc_price_flow_cached(tk, n=20, cache=None):
    """vc_price_flow through the on-disk cache. `cache` = dict loaded by load_flow_cache(); the caller
    saves it once with save_flow_cache(). The cached summary has no `_rows`; callers needing the raw
    rows (Δ since memo at an arbitrary date) call vc_price_flow directly for that ticker."""
    if cache is None or os.environ.get("DEEPFA_FLOW_CACHE", "").lower() == "off":
        return vc_price_flow(tk, n)
    stamp = _src_stamp(tk)
    hit = cache.get(tk)
    if isinstance(hit, dict) and hit.get("_stamp") == stamp and hit.get("_n") == n and hit.get("_v") == FLOW_CACHE_VER:
        return hit["flow"]
    flow = vc_price_flow(tk, n)
    slim = {k: v for k, v in flow.items() if not k.startswith("_")}
    # keep the closes the overview needs for Δ-since-memo: (date, close, close_adj) for the last 400 sessions
    rows = flow.get("_rows") or []
    slim["_closes"] = [[iso(parse_day(r.get("tradingDate"))), finite(r.get("closePrice")), finite(r.get("closePriceAdjusted"))] for r in rows[-400:]]
    cache[tk] = {"_stamp": stamp, "_n": n, "_v": FLOW_CACHE_VER, "flow": slim}
    return slim


def load_flow_cache():
    obj, _ = load_json(flow_cache_path())
    return obj if isinstance(obj, dict) else {}


def save_flow_cache(cache):
    path = flow_cache_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def close_on_or_before_cached(flow, d):
    """Like close_on_or_before but over a cached summary's `_closes` (or `_rows` when present)."""
    if flow.get("_rows"):
        return close_on_or_before(flow["_rows"], d)
    best = None
    for item in flow.get("_closes") or []:
        rd = parse_day(item[0]) if item and item[0] else None
        if rd and rd <= d and (best is None or rd > best[0]):
            best = (rd, item[1], item[2])
    return best


def _last_with(rows, key, back=15):
    """Latest row (searching back ≤`back` sessions) whose `key` is a finite number, with its ISO date.
    Vietcap fills foreignOwnedPercentage / marketCap / totalShares of the newest session later than the
    close, so the last row is often null there — the number then comes from the previous session, dated so."""
    for r in reversed(rows[-back:]):
        if finite(r.get(key)) is not None:
            return r, iso(parse_day(r.get("tradingDate")))
    return None, None


def _lag_note(t_field, t_close):
    return None if (not t_field or t_field == t_close) else "phiên gần nhất có số: %s (phiên đóng cửa %s chưa có)" % (t_field, t_close)


def vc_price_flow(tk, n=20):
    """Last close (bảng) + adjusted close, 20-session foreign net value, prop net value, turnover,
    foreign ownership %, totalShares, market cap — all FACT-T2 dated by their own session."""
    out = {"ok": False}
    ph = load_vc_endpoint(tk, "price-history")
    if not ph["rows"]:
        out["ly_do"] = "chưa có cache vc_lk/%s/price-history" % tk
        return out
    rows = _sorted_by_date(ph["rows"])
    last = rows[-1]
    t = iso(parse_day(last.get("tradingDate")))
    src = "vc_lk/%s/price-history" % tk
    r_ts, t_ts = _last_with(rows, "totalShares")
    r_mc, t_mc = _last_with(rows, "marketCap")
    r_fo, t_fo = _last_with(rows, "foreignOwnedPercentage")
    r_fr, t_fr = _last_with(rows, "foreignCurrentRoom")
    fo = _pct100(r_fo.get("foreignOwnedPercentage")) if r_fo else None
    out.update({
        "ok": True, "t": t, "lay_luc": (ph["meta"] or {}).get("lay_luc"),
        "close": num(finite(last.get("closePrice")), "đồng", t, "FACT-T2", src + ".closePrice"),
        "close_adj": num(finite(last.get("closePriceAdjusted")), "đồng", t, "FACT-T2", src + ".closePriceAdjusted"),
        "total_shares": num(finite((r_ts or {}).get("totalShares")), "cp", t_ts, "FACT-T2", src + ".totalShares", g=_lag_note(t_ts, t)),
        "market_cap": num(finite((r_mc or {}).get("marketCap")), "đồng", t_mc, "FACT-T2", src + ".marketCap", g=_lag_note(t_mc, t)),
        # vendor stores a fraction (0.2857 = 28,57 %); display as percent
        "foreign_pct": num(fo, "%", t_fo, "FACT-T2", src + ".foreignOwnedPercentage",
                           g=" · ".join(x for x in ("mẫu số vendor có thể là số cp cũ sau GDKHQ — so bằng số cp khi cần", _lag_note(t_fo, t)) if x),
                           txt=(fmt_vn(fo, 2) + "%") if fo is not None else "[CẦN DATA]"),
        "foreign_room": num(finite((r_fr or {}).get("foreignCurrentRoom")), "cp", t_fr, "FACT-T2", src + ".foreignCurrentRoom", g=_lag_note(t_fr, t)),
    })
    win = rows[-n:]
    fn = [finite(r.get("foreignNetValueTotal")) for r in win]
    vol = [finite(r.get("totalMatchValue")) for r in win]
    fn_sum = sum(x for x in fn if x is not None) if any(x is not None for x in fn) else None
    vol_avg = (sum(x for x in vol if x is not None) / max(1, len([x for x in vol if x is not None]))) if any(x is not None for x in vol) else None
    out["foreign_net_20"] = num(fn_sum / 1e9 if fn_sum is not None else None, "tỷ đồng", t, "FACT-T2",
                                src + ".foreignNetValueTotal Σ%d phiên" % len(win), txt=fmt_vn(fn_sum / 1e9 if fn_sum is not None else None, 0, True))
    out["turnover_avg_20"] = num(vol_avg / 1e9 if vol_avg is not None else None, "tỷ đồng/phiên", t, "FACT-T2",
                                 src + ".totalMatchValue TB %d phiên" % len(win))
    # price at an arbitrary past date (for Δ since memo): nearest session on/before
    out["_rows"] = rows
    # proprietary (tự doanh)
    pr = load_vc_endpoint(tk, "proprietary-history")
    if pr["rows"]:
        prow = _sorted_by_date(pr["rows"])[-n:]
        pn = [finite(r.get("totalTradeNetValue")) for r in prow]
        ps = sum(x for x in pn if x is not None) if any(x is not None for x in pn) else None
        tp = iso(parse_day(prow[-1].get("tradingDate"))) if prow else t
        out["prop_net_20"] = num(ps / 1e9 if ps is not None else None, "tỷ đồng", tp, "FACT-T2",
                                 "vc_lk/%s/proprietary-history.totalTradeNetValue Σ%d phiên" % (tk, len(prow)),
                                 txt=fmt_vn(ps / 1e9 if ps is not None else None, 0, True))
    else:
        out["prop_net_20"] = num(None, "tỷ đồng", None, "FACT-T2", "vc_lk/%s/proprietary-history" % tk, g="chưa có cache")
    # ratio daily (P/E, P/B with date)
    rd = load_vc_endpoint(tk, "ratio-daily")
    if rd["rows"]:
        rrow = _sorted_by_date(rd["rows"])
        r_pe, t_pe = _last_with(rrow, "pe")
        r_pb, t_pb = _last_with(rrow, "pb")
        out["pe"] = num(finite((r_pe or {}).get("pe")), "x", t_pe, "FACT-T2", "vc_lk/%s/ratio-daily.pe" % tk, txt=fmt_vn(finite((r_pe or {}).get("pe")), 1))
        out["pb"] = num(finite((r_pb or {}).get("pb")), "x", t_pb, "FACT-T2", "vc_lk/%s/ratio-daily.pb" % tk, txt=fmt_vn(finite((r_pb or {}).get("pb")), 2))
        out["_ratio_rows"] = rrow
    return out


def _pct100(v):
    f = finite(v)
    return round(f * 100.0, 4) if f is not None else None


def close_on_or_before(rows, d):
    """(date, closePrice, closePriceAdjusted) of the last session on/before date d."""
    best = None
    for r in rows:
        rd = parse_day(r.get("tradingDate"))
        if rd and rd <= d and (best is None or rd > best[0]):
            best = (rd, finite(r.get("closePrice")), finite(r.get("closePriceAdjusted")))
    return best


# ── other per-ticker files ───────────────────────────────────────────────────


def load_lk_hoso(tk):
    path = sysdir("fincept_bridge", "data", "lk_hoso", tk + ".json")
    obj, err = load_json(path)
    inner = (obj or {}).get("tao_luc") if isinstance(obj, dict) else None
    layer = Layer("lk_hoso", path, "FACT-T2", inner=inner[:10] if isinstance(inner, str) else None, warn_days=3, stale_days=14,
                  label="Hồ sơ Lăng kính (fincept_bridge/data/lk_hoso)")
    layer.error = layer.error or err
    return {"data": obj if isinstance(obj, dict) else None, "meta": layer}


def load_hhp_series(tk):
    path = sysdir("knowledge_os", "hhp_vn100_series", tk + ".json")
    obj, err = load_json(path)
    return {"data": obj if isinstance(obj, dict) else None, "error": err, "path": path}


def coverage_row(cov_layer, tk):
    d = (cov_layer or {}).get("data")
    if not isinstance(d, dict):
        return None
    for r in d.get("coverage") or d.get("rows") or []:
        if isinstance(r, dict) and str(r.get("ticker") or "").upper() == tk:
            return r
    return None


def tp_age_flag(r):
    """Sell-side TP freshness: (date, age_days, flagged). Coverage rows (superdash) use
    target_price / tp_updated ("08-Jun-26"); vietcap_fundamentals.details uses rating_as_of."""
    if not isinstance(r, dict):
        return (None, None, None)
    d = parse_day(_first(r, "tpUpdatedTime", "tp_updated", "rating_as_of", "date"))
    a = age_int(d)
    return (iso(d), a, (a is not None and a > TP_STALE_DAYS))


def coverage_view(r):
    """Normalised sell-side view of one Vietcap coverage row (SS-T3, −1 conviction when sole source)."""
    if not isinstance(r, dict):
        return None
    d, a, flag = tp_age_flag(r)
    tp = finite(_first(r, "target_price", "targetPrice"))
    return {
        "rating": _first(r, "rating"), "target_price": tp, "target_price_txt": fmt_vn(tp, 0),
        "upside_pct": finite(_first(r, "upside_pct", "projectedTsrPercentage")),
        "pe_fwd": finite(_first(r, "pe_fwd", "pe")), "pb_fwd": finite(_first(r, "pb_fwd", "pb")),
        "roe_fwd": finite(_first(r, "roe_fwd", "roe")), "analyst": _first(r, "analyst"), "sector": _first(r, "sector"),
        "tp_date": d, "tp_age_days": a, "tp_stale": flag,
        "tp_flag_txt": ("TP cũ %d ngày (>%d) — không xếp hạng theo upside" % (a, TP_STALE_DAYS)) if flag else None,
        "b": "SS-T3", "n": "superdash_v2/output/vietcap_iq/coverage.json (coverage-universe)",
    }


def ledger_for(ledger_layer, tk):
    d = (ledger_layer or {}).get("data")
    if not isinstance(d, dict):
        return {"calls": [], "stats": None, "honest": None}
    calls = [c for c in d.get("calls") or [] if isinstance(c, dict) and str(c.get("ticker") or "").upper() == tk]
    stats = d.get("stats") if isinstance(d.get("stats"), dict) else None
    honest = None
    if stats:
        total, opn = finite(stats.get("total")), finite(stats.get("open"))
        honest = {
            "is_track_record": bool(total and opn is not None and opn < total),
            "note": ("%d/%d call còn mở — 'hit-rate' chỉ là ảnh chụp mark-to-market của rổ chưa chốt, KHÔNG phải track record"
                     % (opn or 0, total or 0)) if total and opn == total else None,
            "benchmark": "VN-Index (alpha = stock_ret − vnindex_ret)",
            "uniform_negative": None,
        }
        bf = stats.get("by_factor") or {}
        al = [finite((v or {}).get("avg_alpha")) for v in bf.values()]
        al = [a for a in al if a is not None]
        if al and all(a < 0 for a in al):
            honest["uniform_negative"] = ("alpha âm ở mọi bucket (%s) → nghi sai benchmark trước, nghi stock-picking sau"
                                          % ", ".join("%s %s" % (k, fmt_vn((v or {}).get("avg_alpha"), 1, True)) for k, v in bf.items()))
    return {"calls": calls, "stats": stats, "honest": honest}


# ── tension matrix (live) ────────────────────────────────────────────────────


def tension_live(tk, S, flow, gated):
    """Five independent vote streams read from today's layers. Each: {"dong", "gia_tri", "huong" (+1/0/−1/None),
    "t", "b", "n", "txt"}. Alignment = how many streams agree; lệch pha flagged when ≥2 streams disagree in sign."""
    streams = []
    mg = by_ticker(S["mgmt"], tk) or {}
    tone_blk = mg.get("tone") or {}
    tone = tone_blk.get("net")
    vs = mg.get("vs_street") or {}
    t_m = iso(S["mgmt"]["meta"].asof())
    # R7 gate: tone is a keyword count (EST); cap saturation 16/16 → no direction
    n_t, n_h = finite(tone_blk.get("n_tail")), finite(tone_blk.get("n_head"))
    cap = (n_t == 16 and n_h == 16)
    tone_dir = {"bullish": 1, "positive": 1, "bearish": -1, "cautious": -1, "negative": -1, "balanced": 0}.get(str(tone).lower()) if tone else None
    streams.append({"dong": "BLĐ (tone BCTN)", "gia_tri": tone, "huong": None if cap else tone_dir,
                    "t": t_m, "b": "EST" if tone else "UNVERIFIED", "n": "mgmt_view.by_ticker.tone (đếm keyword)",
                    "txt": ("%s (%s thuận/%s khó)%s" % (tone, tone_blk.get("n_tail"), tone_blk.get("n_head"), " ⚠cap 16/16" if cap else "")) if tone else "[CẦN DATA]",
                    "g": "cap bão hòa 16/16 — không đọc hướng" if cap else None})
    up, dn = finite(vs.get("street_up")), finite(vs.get("street_down"))
    sm = by_ticker(S["smap"], tk) or {}
    cc = sm.get("catalyst_consensus") or {}
    if up is None and cc:
        up, dn = finite((cc.get("up") or {}).get("n")), finite((cc.get("down") or {}).get("n"))
    t_s = iso(S["smap"]["meta"].asof())
    votes = (up or 0) + (dn or 0)
    street_dir = None
    if up is not None and votes >= 3:                       # <3 votes: coverage too thin to call a direction
        street_dir = 1 if (up or 0) > 2 * (dn or 0) else (-1 if (dn or 0) > (up or 0) else 0)
    streams.append({"dong": "Street (catalyst ▲/▼ regex)", "gia_tri": [up, dn], "huong": street_dir,
                    "t": t_s, "b": S["smap"]["meta"].effective_tier(), "n": "source_map.by_ticker.catalyst_consensus (UP_KW/DOWN_KW regex)",
                    "txt": ("▲%d/▼%d%s" % (up or 0, dn or 0, "" if votes >= 3 else " (<3 phiếu)")) if up is not None else "[CẦN DATA]",
                    "g": "phe ▼ thiểu số = đọc variant trước" if up and dn and up >= 3 * dn else None})
    vf = by_ticker(S["vf"], tk) or {}
    news = [a for a in (vf.get("ainews") or []) if isinstance(a, dict)]
    pos = sum(1 for a in news if str(a.get("sentiment") or "").lower() in ("positive", "tích cực", "pos"))
    neg = sum(1 for a in news if str(a.get("sentiment") or "").lower() in ("negative", "tiêu cực", "neg"))
    t_v = iso(parse_day(vf.get("fetched_at"))) if vf else None
    streams.append({"dong": "AI-news (sentiment Vietcap)", "gia_tri": [pos, neg, len(news)], "huong": (1 if pos > neg else (-1 if neg > pos else 0)) if news else None,
                    "t": t_v, "b": "EST" if news else "UNVERIFIED", "n": "vietcap_fundamentals.by_ticker.ainews.sentiment",
                    "txt": ("%d+/%d− trên %d tin" % (pos, neg, len(news))) if news else "[CẦN DATA]"})
    ga = gated or {}
    act = finite(ga.get("active_cp"))
    etf = ga.get("etf_du_bao") or {}
    etf_note = ("ETF dự báo kỳ review: %s [%s]" % (etf.get("txt"), etf.get("b"))) if etf.get("txt") else None
    if ga.get("chua_loc"):
        nr = finite(ga.get("net_1m_cp"))
        f_txt = "net thô %s cp 1M · %s quỹ — chưa qua gate LVF (thiếu detail per-quỹ)" % (
            (fmt_vn(nr / 1e6, 1, True) + "M") if nr is not None else "[CẦN DATA]", fmt_vn(ga.get("num_funds"), 0))
        f_dir = None
        f_g = "không bỏ phiếu và không gán nhãn khi chưa lọc ETF rổ/quỹ mới" + (" · " + etf_note if etf_note else "")
    elif ga.get("trang_thai") != "ok":
        f_txt, f_dir, f_g = ga.get("ly_do"), None, etf_note
    else:
        f_txt = "active %s cp 1M (cơ học %s)" % (fmt_vn(act / 1e6 if act is not None else None, 1, True) + "M", fmt_vn((ga.get("co_hoc_cp") or 0) / 1e6, 1, True) + "M")
        f_dir = None if act is None else (1 if act > 0 else (-1 if act < 0 else 0))
        f_g = etf_note
    streams.append({"dong": "Fund intent (sau GATE LVF)", "gia_tri": act, "huong": f_dir,
                    "t": ga.get("as_of"), "b": "UNVERIFIED" if ga.get("trang_thai") == "GATE-BLIND" else S["fund"]["meta"].effective_tier(), "n": "fund_intent_signals.signals + gate LVF",
                    "txt": f_txt, "g": f_g})
    fn = (flow or {}).get("foreign_net_20") or {}
    pn = (flow or {}).get("prop_net_20") or {}
    fv, pv = finite(fn.get("v")), finite(pn.get("v"))
    flow_dir = None
    if fv is not None or pv is not None:
        s = (fv or 0) + (pv or 0)
        flow_dir = 1 if s > 0 else (-1 if s < 0 else 0)
    streams.append({"dong": "Dòng tiền 20 phiên (ngoại + tự doanh)", "gia_tri": [fv, pv], "huong": flow_dir,
                    "t": fn.get("t") or pn.get("t"), "b": "FACT-T2" if (fv is not None or pv is not None) else "UNVERIFIED",
                    "n": "vc_lk price-history.foreignNetValueTotal + proprietary-history.totalTradeNetValue",
                    "txt": ("ngoại %s · tự doanh %s tỷ" % (fn.get("txt", "[CẦN DATA]"), pn.get("txt", "[CẦN DATA]"))) if (fv is not None or pv is not None) else "[CẦN DATA]"})
    dirs = [s["huong"] for s in streams if s["huong"] is not None]
    n_pos, n_neg = sum(1 for d in dirs if d > 0), sum(1 for d in dirs if d < 0)
    if len(dirs) < 2:
        align, lech = "[CẦN DATA]", None
    elif n_pos and n_neg:
        align, lech = "LỆCH PHA — %d thuận / %d nghịch" % (n_pos, n_neg), True
    else:
        align, lech = ("ĐỒNG PHA thuận" if n_pos else ("ĐỒNG PHA nghịch" if n_neg else "TRUNG TÍNH")), False
    return {"dong": streams, "alignment": align, "lech_pha": lech, "n_dong_co_du_lieu": len(dirs)}
