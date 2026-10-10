#!/usr/bin/env python3
"""
Fincept Terminal — ĐỊNH GIÁ HHP · BẢN TUẦN (weekly issue reader + audit engine).

Feeds the "BẢN TUẦN" view of src/screens/hhp_valuation/HhpValuationPanel (HhpWeeklyPage,
HhpWeeklyScreener) through EconomicsService / PythonRunner. Stdlib only; Python 3.9+.
Makes NO network calls and writes NOTHING.

The weekly issue ("Ba chiếc đồng hồ của thị trường…", Hội đồng cố vấn AI) is a self-contained
HTML page produced by the weekly HHP run and saved as
    <HHP_WEEKLY_DIR>/hhp_weekly_YYYY-MM-DD.html          (kỳ = the date in the file name)
This script parses that page (html.parser) into typed blocks, keeps every number and word of
the issue verbatim, and adds three layers the page itself cannot have:
  1. Snapshot  — the issue's embedded screener rows (`var D=[…]`, 194 tickers, compact schema
                 below) + its MINE / AV ticker lists (`var MINE=[…],AV=[…]`).
  2. Live      — the same numbers read NOW from the HHP pipeline JSON (hhp_vn100_valuation.json,
                 hhp_baskets.json). Live values carry their own date; issue values are never
                 overwritten.
  3. Engine    — deterministic audit: issue age, valuation vintage, internal consistency
                 (breadth recount, rigor averages, portfolio sum), issue-vs-live drift
                 (headline stats, portfolio/advisor tickers, 17 baskets), dated items already
                 past, VN-Index levels named in action tables vs the live close.

Inputs (read-only; env overrides are used by the tests):
    HHP_WEEKLY_DIR   ~/SECOND BRAIN-OBSIDIAN/_System/knowledge_os/hhp_weekly
    HHP_DATA_DIR     ~/SECOND BRAIN-OBSIDIAN/_System/knowledge_os
                        hhp_vn100_valuation.json  {meta{generated, zone_dist}, index{pe,pb}, exvic3, by_ticker}
                        hhp_baskets.json          {meta{generated}, baskets:[{code, label, pe, pb}]}
                     Both optional here: missing live data → live parts null + a warning.
    HHP_TODAY        test hook only: fixes "today" (YYYY-MM-DD, ICT) for age / past-date logic.

USAGE
    python3 hhp_weekly.py issues
    python3 hhp_weekly.py brief
    python3 hhp_weekly.py weekly [YYYY-MM-DD]        default = newest issue

OUTPUT — exactly ONE compact JSON object on stdout (UTF-8, ensure_ascii=False). Non-finite
numbers are emitted as null. Exit code 0 even on errors. Display strings are Vietnamese;
numbers meant for display arrive pre-formatted in "*_txt" fields (decimal comma, thousands
dot, minus "−", explicit "+" where the sign matters). Missing values display as "—".

Errors (replace the whole payload):
    {"error": "<Vietnamese message incl. what to do>", "error_code": CODE}
    CODE ∈ NO_ISSUE (no hhp_weekly_*.html in the dir / requested kỳ absent)
         | BAD_ARGS (unknown command, malformed date)
         | INTERNAL (unexpected exception — should not happen)
A page that parses only partly is NOT an error: what could not be read becomes a warning in
meta.warnings and, where relevant, a {"t":"p"} block with the raw text (e.g. a section nested too
deep to lay out). HTML's optional end tags (</p> </li> </td> </th> </tr> </tbody>…) may be omitted.

──────────────────────────────────────────────────────────────────────────────────────────
INLINE MARKUP ("ihtml") — every rich-text string in the payload uses ONLY:
    escaped text (html.escape(quote=True): &amp; &lt; &gt; &quot; &#x27;)
    <b>…</b>   <i>…</i>   <br>
    <span class="K">…</span>   with K exactly one of
        z-floor z-up z-ref z-down z-ceil      zone pill (≤−2σ, ≤−1σ, neutral, ≥+1σ, ≥+2σ)
        tag tag-f tag-p                       small bordered tag (plain · gold · strong)
        num                                   monospace figures
        tk                                    ticker (bold monospace)
        v-hold v-add v-trim                   verdict pill (grey · green · red)
        c-up c-down c-ref c-muted c-ink2 c-floor c-ceil     text colour
        sub                                   small muted second line (e.g. basket label)
        hl                                    highlighted text (gold tint background)
No other tag, no other attribute, no newline characters. Spans nest properly. Source mapping:
strong/b→b · em/i→i · br→br · span.z.z-X→z-X · span.tag[.f|.p]→tag|tag-f|tag-p ·
span.num / td.num content→num · span.tk / td.tk→tk · span.verdict.v-X→v-X ·
style="color:var(--X)"→c-X (X: up down ref muted ink-2→ink2 floor ceil; other colours dropped) ·
style with background color-mix(…ref…)→hl · a→its text (href dropped) · div inside a cell→
<br><span class="sub">…</span> · any other element→its children. Whitespace is collapsed.

TONE = "up" | "down" | "ref" | "muted" | "ink2" | "floor" | "ceil" | null   (colour role)

BLOCKS — a section body is an ordered list of blocks {"t": type, …}:
  {"t":"p", "html": ihtml, "tone": TONE, "small": bool, "box": "down"|"surface"|null, "bold": bool}
        small = font-size < 14px in the page; box = p with background var(--down-bg)/var(--surface-2);
        bold = font-weight 600+ on the p itself (advisor thesis line).
  {"t":"h3", "text": plain, "tone": TONE}
  {"t":"eyebrow", "text": plain, "tone": TONE}                         (div.eyebrow)
  {"t":"note", "html": ihtml, "tone": "ref"|"down"|"up"}               (div.note; tone = border colour, default "ref")
  {"t":"table", "head": [{"text": plain, "align": "l"|"r"}],
        "rows": [{"cells": [{"html": ihtml, "align": "l"|"r", "tone": TONE, "bold": bool}],
                  "mine": bool}],                                       (tr.mine = highlighted row)
        "caption": ihtml ("" if none), "scroll": bool (div.tw had max-height → render height-capped),
        "kind": "generic"|"action"|"rigor"|"basket"|"cheap",
        "id": "T<n>"}                                                   (n = 0-based order of tables in the page)
        kind: action = first head starts with "Việc" or head == Mã/Hiện tại/Hành động…;
              rigor = first head "Chiều"; basket = head starts "Rổ" in section 05;
              cheap = section 06 table.
  {"t":"cards", "cols": 2|3, "cards": [CARD]}   (div.grid2; cols = 2 for "grid2 g2", else min(3, n))
  {"t":"card", …CARD fields}                                           (standalone div.card)
        CARD = {"title": plain ("" if none), "title_tone": TONE, "chip": ihtml ("" if none —
                the status text right of the title, e.g. "GẦN ĐỦ", "-2,26σ RẺ SÂU"),
                "tone": TONE (border-left colour) , "outline": TONE (2px full border) ,
                "blocks": [BLOCK]}
  {"t":"stats", "items": [STAT]}                                       (div.stats inside a section)
        STAT = {"label": plain, "value": plain, "value_tone": TONE, "sub": ihtml,
                "live": {"text": plain, "tone": TONE} | null}
  {"t":"kv", "items": [{"k": plain, "v": ihtml}]}                      (dl.kv)
  {"t":"list", "ordered": bool, "items": [ihtml], "tone": TONE}        (ul/ol, and loose <li> runs)
  {"t":"rule"}                                                         (div.rule)
  {"t":"band", "ticker": "VCB", "metric": "P/E"|"P/B",
        "cheap2", "cheap1", "fair", "rich1", "rich2", "price": numbers in đồng (from the SVG
        aria-label "Dải định giá PE: rẻ 65 031–75 900, hợp lý 86 769, đắt 97 638–108 507,
        giá hiện tại 62 200"), "label": plain aria text,
        "live": {"cheap2","cheap1","fair","rich1","rich2","price","as_of","sigma","sigma_txt",
                 "zone_key"} | null}
        live band = by_ticker[TK].pe|pb band_* and price_now of hhp_vn100_valuation.json;
        live.as_of = by_ticker[TK].price_date (dd/mm/yyyy, the date of that price) when present,
        else the index as_of.
  {"t":"dist", "caption": ihtml,
        "issue": {"n": int, "as_of": "11/09/2026", "points": [{"tk", "s": float, "mine": bool}]},
        "live":  {"n": int, "as_of": "22/09/2026", "points": [...]} | null,
        "labels": [tk…]}
        σ per ticker = min(σ P/E, σ P/B) over the non-null ones (the page's rule), issue from the
        snapshot rows, live from by_ticker. labels = MINE ∪ the 3 lowest and 3 highest issue σ.
  {"t":"screener"}           the interactive table of section 07 — data in payload "snapshot"
  {"t":"advisor", "ticker": "FPT", "subtitle": plain ("FPT Corporation · 72.900đ · đang giữ 12% NAV"),
        "verdict": plain ("HOLD 12%"), "verdict_class": "hold"|"add"|"trim",
        "blocks": [BLOCK]}   (div.adv: .hd → ticker/subtitle/verdict; .bd → blocks incl. voice)
  {"t":"voice", "side": "kill"|"alpha", "who": plain, "html": ihtml}  (div.voice)
Unknown element with text → {"t":"p", "html": <its inline markup>, "tone": null, "small": false,
"box": null, "bold": false}. Empty elements are dropped. Controls (div.bar2, button, input,
label.ck) are dropped.

──────────────────────────────────────────────────────────────────────────────────────────
1) issues → {"issues": ["2026-09-14", "2026-09-12"] newest first, "issue_dir": str}

2) brief → (latest issue only; for the LIVE page banner and screener marks)
{"ky": "2026-09-14"|null, "ky_txt": "14/09/2026", "rev": "rev.3"|null, "title": plain,
 "issues": [...], "age_days": int, "stale": bool, "stale_text": str,
 "mine": [tk], "avoid": [tk],
 "advisors": [{"ticker", "verdict", "verdict_class"}],
 "file": str}
 (no issue → {"ky": null, "issues": [], "mine": [], "avoid": [], "advisors": [], …} — not an error)

3) weekly [ky] →
{
 "meta": {"generated": "2026-09-23T22:50:00+07:00", "script_version": "1.0",
          "issue_dir", "issue_file", "file_url": "file:///…/hhp_weekly_2026-09-14.html",
          "issues": [...], "ky": "2026-09-14", "ky_txt": "14/09/2026", "rev": "rev.3"|null,
          "data_as_of": "2026-09-11"|null   (valuation vintage stated by the issue: first match of
                                             "chốt phiên dd/mm/yyyy" | "dữ liệu chốt dd/mm/yyyy" |
                                             "dữ liệu dd/mm/yyyy" in the masthead status / footer),
          "data_as_of_txt": "11/09/2026"|"—",
          "engine_run": "2026-09-12 15:43 ICT"|null  ("Engine chạy lần cuối …" / "engine chạy …"),
          "age_days": int, "next_due": "2026-09-21", "next_due_txt": "21/09/2026",
          "stale": bool (today >= next_due + 2 days), "stale_text": "" | "BẢN TUẦN CŨ 9 ngày — kỳ 21/09 chưa có",
          "live_as_of": "2026-09-22"|null, "live_as_of_txt", "live_generated": str|null,
          "links": [{"kind": plain (".dual-k"), "title": plain, "url": str, "desc": plain}],
          "warnings": [str]},
 "issue": {"kicker": [plain…], "title": plain (h1; <br> → "\n"), "lede": ihtml,
           "chips": [{"text": plain, "tier": "FACT-T1"|"FACT-T2"|"SS-T3"|"EST"|"NEWS"|"UNVERIFIED"|"",
                      "tone": TONE}]   (tier = the chip text's leading tag when it is one of those;
                                        tone: chip.t1→up, chip.t3→ref, inline style down→down, else null),
           "status": ihtml|"",       (the small paragraph right after the chips)
           "stats": [STAT],          (masthead div.stats; STAT.live filled by the engine, see 4b)
           "sections": [{"id": "00A", "title": plain, "eyebrow": plain, "blocks": [BLOCK]}],
           "footer": [BLOCK]},
 "core": {"mine": [tk], "avoid": [tk],
          "advisors": [{"ticker", "subtitle", "verdict", "verdict_class"}],
          "portfolio": {"items": [{"name": "VCB"|"tiền mặt", "pct": 10.0}], "sum": 101.0,
                        "sum_txt": "101%", "text": plain} | null,
                        (first "Danh mục tham chiếu hiện là …" sentence; items "XXX nn%" split on "·",
                         words after the nn% ignored; a part that is not exactly one "name nn%" is left
                         out of items/sum and reported in meta.warnings)
          "rigor": [{"table_id": "T<n>", "section": "11", "cols": [head…],   (header text per score
                                                     column, colspan expanded; "" past the header's end)
                     "dims": [{"name", "scores": [num|null …]}],   (one score per numeric column)
                     "calc_avg": [num|null], "calc_avg_txt": ["4,67"…],
                     "printed_avg": [num|null], "printed_src": "row"|"caption"|null}]},
 "snapshot": {"rows": [ROW] (the page's `var D` verbatim, order kept), "n": 194,
              "as_of_txt": "11/09/2026",
              "live": {"TK": {"pe": [now, sigma] | null, "pb": [now, sigma] | null,
                              "price": num|null}} | null,
              "live_as_of_txt": "22/09/2026"|"—"},
    ROW (compact, exactly as the page): {"t": ticker,
         "p": price đồng|null, "s": unused (null),
         "pe": [now, mean, sigma, zone_label, reliable(bool), fair_price_đồng|null, to_fair_pct|null],
         "pb": same shape,
         "f": [fwd_pe_2026F, fwd_pb_2026F, roe_pct, tp_đồng, rating ("BUY"…|null), src ("vietcap"|"spg"|null), upside_pct],
         "c": [rec, consensus ("bull"…), n_reports, source, date "YYYY-MM-DD", title],
         "b": "30" (VN30) | "100" (VN100, not VN30) | "" }
        Page filter rules the Qt screener reproduces: row hidden when ratio σ (pe[2]/pb[2]) is null;
        "reliable only" hides reliable=false; VN30 = b=="30"; VN100 = b in ("30","100");
        Danh mục = t in mine; Chỉ RẺ = σ ≤ −1. Zone class of σ: ≤−2 floor, ≤−1 up, ≥+2 ceil, ≥+1 down.
 "engine": {
   "kiem": [{"muc": plain, "ok": true|false|null, "text": plain}]
           ok true = checked and consistent · false = contradiction / expired / drift beyond rule ·
           null = information only or not checkable [CẦN DATA]. Order: tuổi bản tuần · vintage định giá
           (ok false when live is older than the issue's data_as_of, else null) · độ rộng (recount) ·
           rigor (each table) · danh mục (sum) · mốc đã qua · mức chỉ số vs live · drift summary.
   "drift": [{"muc": plain, "issue_txt": plain, "live_txt": plain, "delta_txt": plain,
              "changed": bool}]
           headline rows: VN-Index (level), VN-Index P/E (×, σ), Loại họ Vin P/E (×, σ),
           Họ Vin % vốn hóa, Độ rộng P/E (rẻ/trung tính/đắt counts), Độ rộng P/B.
           changed = zone of the σ changed (σ crossed ±1) or a count moved by ≥ 3.
   "tickers": [{"tk", "mine": bool, "avoid": bool, "advisor": "HOLD 12%"|"",
                "pe_issue_txt": "12,39× · −0,79σ", "pe_live_txt": "12,49× · −0,77σ",
                "pb_issue_txt", "pb_live_txt", "zone_issue": "neutral"|"cheap"|"rich"|null,
                "zone_live": …, "changed": bool}]     (mine ∪ avoid ∪ advisors, mine first; zone
                                                        from min(σPE, σPB) like the dist chart)
   "baskets": [{"code", "label", "pe_issue_txt": "−0,77σ", "pe_live_txt", "pb_issue_txt",
                "pb_live_txt", "changed": bool}]      (section-05 table vs hhp_baskets.json)
   "levels": [{"level": 1726.0, "level_txt": "1.726", "context": plain (≤ 90 chars of the row),
               "live_txt": "1.816,9 (22/09)", "gap_txt": "+5,3%", "side": "trên"|"dưới"}]
             VN-Index levels 1.000–2.999 written "1.726" / "1.788–1.791" in action-table sentences
             that mention chỉ số|VN-Index|MA200|chốt chặn|hỗ trợ|mốc and are not broker forecasts
             ("Dự báo …"), excluding numbers followed by tỷ|triệu|nghìn|USD|VND|VNĐ|đồng|%|đ and any level
             being replaced anywhere in the action tables ("thay 1.820 bằng …"); live = last point of
             index.pe.chart.price (price_now / as_of when that point has no readable ms timestamp). A
             range gives two levels. The kiem list carries ONE "Mức chỉ số" line summarising all levels.
   "past": [{"date": "18/09", "text": plain (≤ 90 chars), "table_id": "T<n>", "row": int}]
             action-table rows whose FIRST cell names dd/mm dates that are all before today.
 },
 "csv": {"columns": ["Mã", "Danh mục", "P/E", "σ P/E (bản tuần)", "σ P/E (live)", "P/B",
                     "σ P/B (bản tuần)", "σ P/B (live)", "Giá (bản tuần)", "Fwd P/E 26F", "TP", "Catalyst"],
         "rows": [[str × 12]]}     (all snapshot rows; Danh mục = "danh mục"|"tránh"|"")
}

4) Engine rules (all deterministic):
 a. age_days = today − ky. next_due = ky + 7 days. stale = today >= next_due + 2 days.
 b. Masthead STAT.live, matched on the label (case-insensitive, accents kept):
      "VN-Index P/E" → "live dd/mm: 12,54× · −1,28σ"         (index.pe.now / sigma / as_of)
      "Loại họ Vin"  → "live dd/mm: 10,6× · −1,92σ"          (exvic3.pe_exv3_now / exv3_pe_sigma)
      "Độ rộng"      → "live: 40 / 129 / 24 · P/B 57 / 114 / 23"  (meta.zone_dist)
      "Họ Vin chiếm" → "live dd/mm: 28,5%"                    (exvic3.w3_now)
      label with a dd–dd/mm or dd/mm date range entirely before today → "đã qua (hôm nay dd/mm)"
    tone of STAT.live: the zone colour of the live σ when there is one, else "muted".
 c. Breadth recount: count snapshot rows by pe[3] (and pb[3]) zone label → compare with the
    stat whose label starts "Độ rộng" ("42 / 128 / 23", sub "P/B: 57 / 117 / 20").
 d. Rigor: for each rigor table, average each numeric column over the dimension rows (row whose
    first cell starts "Trung bình" excluded; exact decimal arithmetic, so 24,9 / 6 = 4,15 → 4,2);
    score columns = right-aligned header cells, else the columns most rows hold a number in;
    printed average from that row, else from the
    caption pattern "Trung bình a → b". ok = |round(calc, d) − printed| < 0.005 where d = number
    of decimals printed.
 e. Portfolio: ok = sum == 100 (±0.5); null when a part could not be read (then the sum is not scored).
    text e.g. "Danh mục tham chiếu cộng lại 101% (11 mã + tiền mặt 16%)".
 f. Past: see engine.past; one kiem line listing them, ok = null.
 g. Levels: one kiem line for all levels, ok = null.
 h. Drift summary: "n mã danh mục đổi vùng từ bản tuần: …" (ok false when n > 0; else null when a
    mã danh mục could not be compared — σ missing in the issue or in live, named "[CẦN DATA]" — or
    none could; else true).
Numbers in issue strings are parsed Vietnamese-style: "1 795,2" / "1.795,2" (space, NBSP, NNBSP
or dot as thousands) · "12,4×" · "-1,36σ" / "−1,36σ".
"""

from __future__ import annotations

import html
import json
import math
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from html.parser import HTMLParser
from pathlib import Path

SCRIPT_VERSION = "1.0"
ICT = timezone(timedelta(hours=7), "ICT")
SYS_DIR = os.path.join(os.path.expanduser("~"), "SECOND BRAIN-OBSIDIAN", "_System")
MINUS = "−"
USAGE = "Dùng: hhp_weekly.py issues | hhp_weekly.py brief | hhp_weekly.py weekly [YYYY-MM-DD]"
ISSUE_RE = re.compile(r"^hhp_weekly_(\d{4}-\d{2}-\d{2})\.html$")
STALE_GRACE_DAYS = 2
ISSUE_PERIOD_DAYS = 7

DEFAULT_WEEKLY_DIR = os.path.join(SYS_DIR, "knowledge_os", "hhp_weekly")
DEFAULT_DATA_DIR = os.path.join(SYS_DIR, "knowledge_os")
VALUATION_FILE = "hhp_vn100_valuation.json"
BASKETS_FILE = "hhp_baskets.json"
TEXT_MAX = 90  # engine.levels context / engine.past text
TIERS = ("FACT-T1", "FACT-T2", "SS-T3", "EST", "NEWS", "UNVERIFIED")
TONE_VARS = {"up": "up", "down": "down", "ref": "ref", "muted": "muted", "ink-2": "ink2", "floor": "floor",
             "ceil": "ceil"}
ZONE_CLASSES = ("z-floor", "z-up", "z-ref", "z-down", "z-ceil")
VERDICT_CLASSES = ("v-hold", "v-add", "v-trim")
ZONE_VI = {"cheap": "rẻ", "neutral": "trung tính", "rich": "đắt"}
CSV_COLUMNS = ["Mã", "Danh mục", "P/E", "σ P/E (bản tuần)", "σ P/E (live)", "P/B", "σ P/B (bản tuần)",
               "σ P/B (live)", "Giá (bản tuần)", "Fwd P/E 26F", "TP", "Catalyst"]

VOID_TAGS = frozenset("area base br col embed hr img input link meta param source track wbr".split())
DROP_TAGS = frozenset("script style button input select textarea noscript template title link meta".split())
TEXT_SKIP = frozenset("script style svg button input select textarea noscript template".split())
BLOCK_TAGS = frozenset("p div table ul ol dl h1 h2 h3 h4 h5 h6 svg section header footer nav blockquote figure "
                       "hr form main article aside".split())
TEXT_BREAKS = frozenset("div p li tr td th h1 h2 h3 h4 h5 h6 dt dd caption".split())
# HTML's optional end tags: start tag → (open tags it closes implicitly, tags that bound the search down the stack).
_CELLS = frozenset(("td", "th"))
_ROWS = _CELLS | {"tr"}
_TABLE = frozenset(("table",))
IMPLIED_CLOSE = {"td": (_CELLS, frozenset(("tr", "table"))), "th": (_CELLS, frozenset(("tr", "table"))),
                 "tr": (_ROWS, _TABLE), "thead": (_ROWS | {"thead", "tbody", "tfoot"}, _TABLE),
                 "tbody": (_ROWS | {"thead", "tbody", "tfoot"}, _TABLE),
                 "tfoot": (_ROWS | {"thead", "tbody", "tfoot"}, _TABLE),
                 "li": (frozenset(("li",)), frozenset(("ul", "ol", "table", "td", "th")))}
P_CLOSERS = (BLOCK_TAGS - {"svg"}) | {"li", "dd", "dt"}  # block starts that close an open <p>
P_SCOPE = frozenset(("table", "td", "th", "caption", "button", "svg"))

WS_RE = re.compile(r"[ \t\n\r\f\v]+")
TAG_SPLIT_RE = re.compile(r"(<[^>]*>)")
EMPTY_EL_RE = re.compile(r'<(b|i)></\1>|<span class="[a-z0-9-]+"></span>')
VAR_RE = re.compile(r"var\(\s*--([a-z0-9-]+)\s*\)")
PX_RE = re.compile(r"([\d.]+)\s*px")
NUM_RE = re.compile(r"(?<![\d,])([−\-+]?)(\d{1,3}(?:[   .]\d{3})+|\d+)(?:,(\d+))?(?!\d)")
SIGMA_RE = re.compile(r"([−\-+]?\d+(?:,\d+)?)\s*σ")
DATE_RE = re.compile(r"(?<![\d/.,])(\d{1,2})/(\d{2})(?:/(\d{4}))?(?![\d/])")
DATE_RANGE_RE = re.compile(r"(?<![\d/.,])(\d{1,2})\s*[–-]\s*(\d{1,2})/(\d{2})(?:/(\d{4}))?(?![\d/])")
LEVEL_NUM_RE = re.compile(r"(?<![\d.,])([12]\.\d{3})(?!\d)(?![.,]\d)")
LEVEL_KW_RE = re.compile(r"chỉ số|vn-index|ma200|chốt chặn|hỗ trợ|mốc", re.I)
LEVEL_UNIT_RE = re.compile(r"\s*(?:tỷ|triệu|nghìn|USD|VNĐ|VND|%|đồng(?![^\W\d_])(?!\s*hồ))|\s?đ(?![^\W\d_])", re.I)
LEVEL_RANGE_SEP_RE = re.compile(r"\s*[–-]\s*")
# Sentence ends: ". " (the thousands dot in "1.726" is never followed by a space) and the cell joins.
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+| · ")
AS_OF_RE = re.compile(r"(?:chốt phiên|dữ liệu chốt|dữ liệu)\s+(\d{1,2}/\d{1,2}/\d{4})", re.I)
ENGINE_RUN_RE = re.compile(r"engine chạy(?:\s+lần cuối|\s+lúc)?\s*:?\s*(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})", re.I)
REV_RE = re.compile(r"\brev\.\s?(\d+)", re.I)
PORTFOLIO_RE = re.compile(r"Danh mục tham chiếu hiện là\s*(.+?)(?:\.(?!\d)|$)")
PORTFOLIO_ITEM_RE = re.compile(r"^(.*?)\s*(\d+(?:[.,]\d+)?)\s*%")
PORTFOLIO_PCT_RE = re.compile(r"\d+(?:[.,]\d+)?\s*%")
AVG_CAPTION_RE = re.compile(r"Trung bình\s*:?\s*(\d+(?:,\d+)?(?:\s*(?:→|->)\s*\d+(?:,\d+)?)*)")
_BN = r"([\d \u00a0\u202f.,]+?)"  # one đồng amount inside the band aria-label
BAND_RE = re.compile(r"Dải định giá\s+(P/?E|P/?B)\s*:\s*rẻ\s+" + _BN + r"\s*[–-]\s*" + _BN + r",\s*hợp lý\s+" + _BN
                     + r",\s*đắt\s+" + _BN + r"\s*[–-]\s*" + _BN + r",\s*giá hiện tại\s+([\d \u00a0\u202f.,]+)", re.I)


class WeeklyError(Exception):
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


def env_dir(name, default):
    env = os.environ.get(name, "").strip()
    return os.path.expanduser(env) if env else default


def parse_iso(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def dmy(d):
    return d.strftime("%d/%m/%Y") if isinstance(d, date) else "—"


def dm(d):
    return d.strftime("%d/%m") if isinstance(d, date) else "—"


def clip(s, n=TEXT_MAX):
    s = s or ""
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def today_ict(warnings):
    env = os.environ.get("HHP_TODAY", "").strip()
    if env:
        d = parse_iso(env)
        if d is not None:
            return d
        warnings.append("HHP_TODAY '%s' không đúng dạng YYYY-MM-DD — dùng ngày hôm nay thật" % env)
    return datetime.now(ICT).date()


def list_issues(wdir):
    try:
        names = os.listdir(wdir)
    except OSError:
        return []
    kys = {m.group(1) for m in map(ISSUE_RE.match, names) if m and parse_iso(m.group(1))}
    return sorted(kys, reverse=True)


def issue_path(wdir, ky):
    return os.path.join(wdir, "hhp_weekly_%s.html" % ky)


# ── Vietnamese numbers ───────────────────────────────────────────────────────


def _num_value(m):
    v = float(re.sub(r"[   .]", "", m.group(2)) + ("." + m.group(3) if m.group(3) else ""))
    return -v if m.group(1) in ("-", MINUS) else v


def vn_num(s):
    """First Vietnamese-style number in s → (float, decimals printed) or (None, 0)."""
    m = NUM_RE.search(s or "")
    return (_num_value(m), len(m.group(3) or "")) if m else (None, 0)


def vn_sigma(s):
    m = SIGMA_RE.search(s or "")
    return vn_num(m.group(1))[0] if m else None


def half_up(v, dec):
    return float(Decimal(repr(v)).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP))


def fmt_dec(v, dec=2, sign=False, thousands=True):
    """Display number: decimal comma, thousands dot, minus "−", optional explicit "+". None → "—"."""
    v = finite(v)
    if v is None:
        return "—"
    q = Decimal(repr(v)).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP)
    body = "{:,.{}f}".format(abs(q), dec).replace(",", "\x00").replace(".", ",")
    body = body.replace("\x00", "." if thousands else "")
    if q < 0:
        return MINUS + body
    return ("+" if sign and q > 0 else "") + body


def fmt_trim(v, dec=2, sign=False):
    s = fmt_dec(v, dec, sign)
    return s.rstrip("0").rstrip(",") if "," in s else s


def fmt_sigma(v):
    return "—" if finite(v) is None else fmt_dec(v, 2, sign=True) + "σ"


def fmt_ratio_sigma(now, sigma, dec=2):
    if finite(now) is None and finite(sigma) is None:
        return "—"
    return "%s× · %s" % (fmt_dec(now, dec), fmt_sigma(sigma))


def zone3(s):
    s = finite(s)
    if s is None:
        return None
    return "cheap" if s <= -1 else ("rich" if s >= 1 else "neutral")


def zone_tone(s):
    """σ → the page's zone colour role (≤−2 floor, ≤−1 up, ≥+2 ceil, ≥+1 down, else muted)."""
    s = finite(s)
    if s is None:
        return "muted"
    if s <= -2:
        return "floor"
    if s <= -1:
        return "up"
    if s >= 2:
        return "ceil"
    return "down" if s >= 1 else "muted"


def label_zone(label):
    """Upstream zone label ("RẺ (<−1σ)", "TRUNG TÍNH", "ĐẮT (>+1σ)") → cheap | neutral | rich | None."""
    if not isinstance(label, str):
        return None
    up = unicodedata.normalize("NFC", label).strip().upper()
    if up.startswith("RẺ"):
        return "cheap"
    if up.startswith(("ĐẮT", "MẮC")):
        return "rich"
    return "neutral" if up.startswith("TRUNG") else None


def min_sigma(pairs, fallback=False):
    """min σ over the reliable non-null (σ, reliable) pairs — the page's dist rule; `fallback` → any non-null."""
    vals = [s for s, rel in pairs if s is not None and rel]
    if not vals and fallback:
        vals = [s for s, _ in pairs if s is not None]
    return min(vals) if vals else None


def dates_in(text, ref):
    """dd/mm[/yyyy] and dd–dd/mm dates named in text; year inferred around `ref` (the issue date)."""
    found = []

    def add(d, mo, y):
        try:
            d, mo = int(d), int(mo)
            if y:
                found.append(date(int(y), mo, d))
                return
            cand = date(ref.year, mo, d)
            if (cand - ref).days > 183:
                cand = date(ref.year - 1, mo, d)
            elif (ref - cand).days > 183:
                cand = date(ref.year + 1, mo, d)
            found.append(cand)
        except ValueError:
            pass

    for m in DATE_RANGE_RE.finditer(text or ""):
        add(m.group(1), m.group(3), m.group(4))
    for m in DATE_RE.finditer(text or ""):
        add(m.group(1), m.group(2), m.group(3))
    return found


# ── Minimal DOM ──────────────────────────────────────────────────────────────


class Node(object):
    __slots__ = ("tag", "attrs", "cls", "children", "_style")

    def __init__(self, tag, attrs):
        self.tag = tag
        self.attrs = attrs
        self.cls = frozenset((attrs.get("class") or "").split())
        self.children = []
        self._style = None

    def els(self):
        return [c for c in self.children if isinstance(c, Node)]

    def style(self):
        if self._style is None:
            self._style = {}
            for part in (self.attrs.get("style") or "").split(";"):
                if ":" in part:
                    k, v = part.split(":", 1)
                    self._style[k.strip().lower()] = v.strip()
        return self._style

    def child(self, tag=None, cls=None):
        for c in self.els():
            if (tag is None or c.tag == tag) and (cls is None or cls in c.cls):
                return c
        return None


class TreeBuilder(HTMLParser):
    """Forgiving HTML → Node tree. HTML's optional end tags are implied (td/th close an open td/th, tr closes
    td/th/tr, tbody/thead/tfoot close rows, li closes an open li, a block start closes an open p — each only
    within its table/list/cell). Unmatched end tags are ignored; open elements are closed at EOF."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {})
        self.stack = [self.root]

    def _node(self, tag, attrs):
        node = Node(tag, {k: (v if v is not None else "") for k, v in attrs})
        self.stack[-1].children.append(node)
        return node

    def _close_implied(self, tag):
        rules = ([(frozenset(("p",)), P_SCOPE)] if tag in P_CLOSERS else []) + \
            ([IMPLIED_CLOSE[tag]] if tag in IMPLIED_CLOSE else [])
        for closes, scope in rules:
            cut = None
            for i in range(len(self.stack) - 1, 0, -1):
                t = self.stack[i].tag
                if t in scope:
                    break
                if t in closes:
                    cut = i  # keep going: the outermost match within the scope is closed
            if cut is not None:
                del self.stack[cut:]

    def handle_starttag(self, tag, attrs):
        self._close_implied(tag)
        node = self._node(tag, attrs)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self._close_implied(tag)
        self._node(tag, attrs)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        kids = self.stack[-1].children
        if kids and isinstance(kids[-1], str):
            kids[-1] += data
        else:
            kids.append(data)


def iter_els(node):
    stack = list(reversed(node.els()))
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.els()))


def find(node, pred):
    return next((n for n in iter_els(node) if pred(n)), None)


def find_all(node, pred):
    return [n for n in iter_els(node) if pred(n)]


def _text_pieces(node, out, br):
    todo = list(reversed(node.children))  # iterative: any nesting depth
    while todo:
        c = todo.pop()
        if isinstance(c, str):
            out.append(c)
        elif c.tag == "br":
            out.append(br)
        elif c.tag not in TEXT_SKIP:
            sep = c.tag in TEXT_BREAKS
            if sep:
                out.append(" ")
                todo.append(" ")
            todo.extend(reversed(c.children))


def text_of(node, newline_br=False):
    """Plain text, whitespace collapsed; <br> → "\\n" when newline_br."""
    if node is None:
        return ""
    parts = []
    _text_pieces(node, parts, "\x00" if newline_br else " ")
    s = "".join(parts)
    if newline_br:
        return "\n".join(x for x in (WS_RE.sub(" ", p).strip() for p in s.split("\x00")) if x)
    return WS_RE.sub(" ", s).strip()


def var_tone(value):
    m = VAR_RE.search(value or "")
    return TONE_VARS.get(m.group(1)) if m else None


def color_tone(node):
    return var_tone(node.style().get("color")) if node is not None else None


def font_px(node):
    m = PX_RE.search(node.style().get("font-size", ""))
    return float(m.group(1)) if m else None


def is_bold(node):
    w = node.style().get("font-weight", "").strip().lower()
    return w in ("bold", "bolder") or (w.isdigit() and int(w) >= 600)


def is_control(node):
    return node.tag in DROP_TAGS or "bar2" in node.cls or (node.tag == "label" and "ck" in node.cls)


# ── Inline markup (ihtml) ────────────────────────────────────────────────────


def span_classes(node):
    """The contract's span classes for one source element (outer → inner)."""
    out = []
    if node.tag == "span":
        out.extend(k for k in ZONE_CLASSES if k in node.cls)
        if "tag" in node.cls:
            out.append("tag-f" if "f" in node.cls else ("tag-p" if "p" in node.cls else "tag"))
        out.extend(k for k in ("num", "tk") if k in node.cls)
        out.extend(k for k in VERDICT_CLASSES if k in node.cls)
    st = node.style()
    tone = var_tone(st.get("color"))
    if tone:
        out.append("c-" + tone)
    bg = st.get("background", "") + st.get("background-color", "")
    if "color-mix" in bg and "--ref" in bg:
        out.append("hl")
    return out


def _has_visible(out):
    return bool(re.sub(r"<[^>]*>", "", "".join(out)).strip())


def _inline(children, out):
    todo = list(reversed(children))  # iterative: any nesting depth; a tuple = closing tags queued after children
    while todo:
        c = todo.pop()
        if isinstance(c, tuple):
            out.extend(c)
            continue
        if isinstance(c, str):
            out.append(html.escape(c, quote=True))
            continue
        if c.tag in TEXT_SKIP or is_control(c):
            continue
        if c.tag == "br":
            out.append("<br>")
            continue
        if c.tag == "div":
            if _has_visible(out):
                out.append("<br>")
            out.append('<span class="sub">')
            todo.append(("</span>",))
            todo.extend(reversed(c.children))
            continue
        if c.tag in BLOCK_TAGS or c.tag in TEXT_BREAKS:
            if _has_visible(out):
                out.append("<br>")
            todo.extend(reversed(c.children))
            continue
        opens, closes = [], []
        if c.tag in ("strong", "b"):
            opens.append("<b>")
            closes.append("</b>")
        elif c.tag in ("em", "i"):
            opens.append("<i>")
            closes.append("</i>")
        for k in span_classes(c):
            opens.append('<span class="%s">' % k)
            closes.insert(0, "</span>")
        out.extend(opens)
        todo.append(tuple(closes))
        todo.extend(reversed(c.children))


def _rstrip_last_text(out):
    for i in range(len(out) - 1, -1, -1):
        t = out[i]
        if t.startswith("</"):
            continue
        if t.startswith("<"):
            return
        out[i] = t.rstrip(" ")
        if out[i]:
            return


def normalize_ihtml(s):
    """Collapse whitespace across tag boundaries, trim, drop empty elements."""
    out, prev_space = [], True
    for tok in TAG_SPLIT_RE.split(s):
        if not tok:
            continue
        if tok.startswith("<"):
            if tok == "<br>":
                _rstrip_last_text(out)
                prev_space = True
            out.append(tok)
            continue
        tok = WS_RE.sub(" ", tok)
        if prev_space:
            tok = tok.lstrip(" ")
        if tok:
            prev_space = tok.endswith(" ")
            out.append(tok)
    _rstrip_last_text(out)
    s, prev = "".join(out), None
    while prev != s:
        prev, s = s, EMPTY_EL_RE.sub("", s)
    while s.startswith("<br>"):
        s = s[4:].lstrip(" ")
    while s.endswith("<br>"):
        s = s[:-4].rstrip(" ")
    return s


def ihtml_nodes(children):
    out = []
    _inline(children, out)
    return normalize_ihtml("".join(out))


def ihtml(node):
    return ihtml_nodes(node.children) if node is not None else ""


def ihtml_text(text):
    return normalize_ihtml(html.escape(text or "", quote=True))


# ── Live data (HHP pipeline JSON, read now) ──────────────────────────────────


def _load_json(path, warnings):
    name = os.path.basename(path)
    if not os.path.isfile(path):
        warnings.append("Thiếu %s trong %s — phần live để trống (chạy engine HHP để có dữ liệu mới)"
                        % (name, os.path.dirname(path)))
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        warnings.append("Không đọc được %s (%s) — phần live tương ứng để trống" % (name, exc))
        return None


def _dict(v):
    return v if isinstance(v, dict) else {}


class Live(object):
    """hhp_vn100_valuation.json + hhp_baskets.json as they are now (each optional)."""

    def __init__(self, ddir, warnings):
        val = _dict(_load_json(os.path.join(ddir, VALUATION_FILE), warnings))
        bsk = _dict(_load_json(os.path.join(ddir, BASKETS_FILE), warnings))
        meta = _dict(val.get("meta"))
        self.ok = bool(val)
        self.by_ticker = _dict(val.get("by_ticker"))
        self.index_pe = _dict(_dict(val.get("index")).get("pe"))
        self.exvic3 = _dict(val.get("exvic3"))
        self.zone_dist = _dict(meta.get("zone_dist"))
        self.generated = meta.get("generated") if isinstance(meta.get("generated"), str) else None
        self.as_of = parse_iso(self.index_pe.get("as_of"))
        self.as_of_txt = dmy(self.as_of)
        self.close, self.close_date = self._last_close(warnings)
        blist = bsk.get("baskets")
        if bsk and not isinstance(blist, list):
            warnings.append("%s: trường baskets không phải danh sách — phần so 17 rổ để trống" % BASKETS_FILE)
            blist = []
        self.baskets = {b["code"]: b for b in blist or []
                        if isinstance(b, dict) and isinstance(b.get("code"), str)}

    def _last_close(self, warnings):
        pts = _dict(self.index_pe.get("chart")).get("price")
        if isinstance(pts, list):
            for p in reversed(pts):
                if isinstance(p, (list, tuple)) and len(p) >= 2 and finite(p[0]) is not None \
                        and finite(p[1]) is not None:
                    try:
                        return float(p[1]), datetime.fromtimestamp(p[0] / 1000.0, ICT).date()
                    except (ValueError, OverflowError, OSError):
                        warnings.append("%s: điểm cuối index.pe.chart.price có thời điểm không đọc được (%r, cần "
                                        "mili-giây epoch) — dùng price_now / as_of" % (VALUATION_FILE, p[0]))
                        break
        return finite(self.index_pe.get("price_now")), self.as_of

    def ticker(self, tk):
        return _dict(self.by_ticker.get(tk))


def live_metric(ent, key):
    m = _dict(_dict(ent).get(key))
    return finite(m.get("now")), finite(m.get("sigma")), bool(m.get("reliable"))


def row_metric(row, key):
    m = row.get(key) if isinstance(row, dict) else None
    if not isinstance(m, list):
        return None, None, False
    return (finite(m[0]) if len(m) > 0 else None, finite(m[2]) if len(m) > 2 else None,
            bool(m[4]) if len(m) > 4 else False)


# ── Page → blocks ────────────────────────────────────────────────────────────


class Ctx(object):
    """Parse state shared by the block converters (section id, table counter, collections)."""

    def __init__(self, ky, today, live, rows, mine, avoid, snap_as_of_txt, warnings):
        self.ky, self.today, self.live = ky, today, live
        self.rows, self.mine, self.avoid = rows, mine, avoid
        self.snap_as_of_txt = snap_as_of_txt
        self.warnings = warnings
        self.section = ""
        self.table_n = 0
        self.tables = []  # {"id", "section", "kind", "head", "rows": [[td Node]], "caption": plain}
        self.advisors = []
        self.ticker_hint = None


def num_out(v):
    return int(v) if isinstance(v, float) and v.is_integer() else v


def p_block(node, h=None):
    h = ihtml(node) if h is None else h
    if node is None:
        return {"t": "p", "html": h, "tone": None, "small": False, "box": None, "bold": False}
    st = node.style()
    bg = st.get("background", "") + " " + st.get("background-color", "")
    px = font_px(node)
    return {"t": "p", "html": h, "tone": color_tone(node), "small": px is not None and px < 14,
            "box": "down" if "--down-bg" in bg else ("surface" if "--surface-2" in bg else None),
            "bold": is_bold(node)}


def blocks_of(children, ctx):
    blocks, run, lis = [], [], []

    def flush():
        if run:
            h = ihtml_nodes(run)
            if h:
                blocks.append(p_block(None, h))
            del run[:]
        if lis:
            items = [x for x in (ihtml(li) for li in lis) if x]
            if items:
                blocks.append({"t": "list", "ordered": False, "items": items, "tone": None})
            del lis[:]

    for c in children:
        if isinstance(c, str):
            if c.strip() or run:
                if lis:
                    flush()
                run.append(c)
            continue
        if is_control(c):
            continue
        if c.tag == "li":
            if run:
                flush()
            lis.append(c)
        elif c.tag not in BLOCK_TAGS:
            if lis:
                flush()
            run.append(c)
        else:
            flush()
            blocks.extend(block_of(c, ctx))
    flush()
    return blocks


def block_of(el, ctx):
    tag, cls = el.tag, el.cls
    if tag == "p":
        b = p_block(el)
        return [b] if b["html"] else []
    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        t = text_of(el)
        return [{"t": "h3", "text": t, "tone": color_tone(el)}] if t else []
    if tag == "svg":
        return svg_block(el, ctx)
    if tag == "table":
        return [table_block(el, False, ctx)]
    if tag in ("ul", "ol"):
        return list_block(el)
    if tag == "dl":
        return kv_block(el)
    if tag == "hr" or "rule" in cls:
        return [{"t": "rule"}]
    if "sechead" in cls:
        return []
    if "eyebrow" in cls:
        t = text_of(el)
        return [{"t": "eyebrow", "text": t, "tone": color_tone(el)}] if t else []
    if "note" in cls:
        h = ihtml(el)
        tone = var_tone(el.style().get("border-left-color") or el.style().get("border-left"))
        return [{"t": "note", "html": h, "tone": tone if tone in ("down", "up") else "ref"}] if h else []
    if "tw" in cls:
        tables = find_all(el, lambda n: n.tag == "table")
        if tables:
            return [table_block(t, "max-height" in el.style(), ctx) for t in tables]
    if "grid2" in cls:
        return [cards_block(el, ctx)]
    if "card" in cls:
        return [dict({"t": "card"}, **card_of(el, ctx))]
    if "stats" in cls:
        return [{"t": "stats", "items": [stat_of(s) for s in el.els() if "stat" in s.cls]}]
    if "adv" in cls:
        return [advisor_block(el, ctx)]
    if "voice" in cls:
        return [voice_block(el)]
    if any(c.tag in BLOCK_TAGS or c.tag == "li" for c in el.els()):
        return blocks_of(el.children, ctx)
    b = p_block(el)
    return [b] if b["html"] else []


def list_block(el):
    items = [x for x in (ihtml(li) for li in el.els() if li.tag == "li") if x]
    return [{"t": "list", "ordered": el.tag == "ol", "items": items, "tone": color_tone(el)}] if items else []


def kv_block(el):
    items, key = [], None
    for c in el.els():
        if c.tag == "dt":
            if key is not None:
                items.append({"k": key, "v": ""})
            key = text_of(c)
        elif c.tag == "dd":
            items.append({"k": key or "", "v": ihtml(c)})
            key = None
    if key is not None:
        items.append({"k": key, "v": ""})
    return [{"t": "kv", "items": items}] if items else []


def stat_of(el, live=None):
    def part(name):
        return find(el, lambda n: name in n.cls)

    big = part("big")
    return {"label": text_of(part("lbl")), "value": text_of(big), "value_tone": color_tone(big),
            "sub": ihtml(part("sub")), "live": live}


def cell_of(td):
    h = ihtml(td)
    if h and "num" in td.cls:
        h = '<span class="num">%s</span>' % h
    if h and "tk" in td.cls:
        h = '<span class="tk">%s</span>' % h
    return {"html": h, "align": "l" if "l" in td.cls else "r", "tone": color_tone(td), "bold": is_bold(td)}


def table_kind(heads, section):
    first = heads[0] if heads else ""
    if first.startswith("Chiều"):
        return "rigor"
    if first.startswith("Việc") or heads[:3] == ["Mã", "Hiện tại", "Hành động"]:
        return "action"
    if section == "05" and first.startswith("Rổ"):
        return "basket"
    return "cheap" if section == "06" else "generic"


def colspan(cell):
    try:
        return min(max(int(cell.attrs.get("colspan") or 1), 1), 100)
    except ValueError:
        return 1


def table_block(tbl, scroll, ctx):
    tid = "T%d" % ctx.table_n
    ctx.table_n += 1
    thead = find(tbl, lambda n: n.tag == "thead")
    head_tr = find(thead, lambda n: n.tag == "tr") if thead is not None else None
    bodies = find_all(tbl, lambda n: n.tag == "tbody")
    trs = [tr for b in bodies for tr in b.els() if tr.tag == "tr"] if bodies else \
        [tr for tr in tbl.els() if tr.tag == "tr"]
    if head_tr is None and trs and all(c.tag == "th" for c in trs[0].els()):
        head_tr, trs = trs[0], trs[1:]
    ths = [th for th in (head_tr.els() if head_tr is not None else []) if th.tag in ("th", "td")]
    head = [{"text": text_of(th), "align": "l" if "l" in th.cls else "r"} for th in ths]
    head_cols = [h for th, h in zip(ths, head) for _ in range(colspan(th))]  # index i ↔ body cell i
    if tbl.attrs.get("id") == "scr" or (ctx.section == "07" and not trs):
        return {"t": "screener"}
    raw = [[c for c in tr.els() if c.tag in ("td", "th")] for tr in trs]
    rows = [{"cells": [cell_of(td) for td in tds], "mine": "mine" in tr.cls} for tr, tds in zip(trs, raw)]
    cap = tbl.child("caption")
    heads = [h["text"] for h in head]
    kind = table_kind(heads, ctx.section)
    ctx.tables.append({"id": tid, "section": ctx.section, "kind": kind, "head": head, "head_cols": head_cols,
                       "rows": raw, "caption": text_of(cap)})
    return {"t": "table", "head": head, "rows": rows, "caption": ihtml(cap), "scroll": bool(scroll),
            "kind": kind, "id": tid}


def cards_block(el, ctx):
    cards = []
    for c in el.els():
        if is_control(c):
            continue
        card = card_of(c, ctx) if "card" in c.cls else \
            {"title": "", "title_tone": None, "chip": "", "tone": None, "outline": None, "blocks": blocks_of([c], ctx)}
        if card["title"] or card["blocks"]:
            cards.append(card)
    return {"t": "cards", "cols": 2 if "g2" in el.cls else max(1, min(3, len(cards))), "cards": cards}


def card_of(el, ctx):
    st = el.style()
    rest = list(el.children)
    title, title_tone, chip = "", None, ""
    first = next((i for i, c in enumerate(rest) if isinstance(c, Node) or c.strip()), None)
    if first is not None and isinstance(rest[first], Node):
        f = rest[first]
        h3 = f if f.tag in ("h2", "h3", "h4") else (f.child("h3") if f.tag == "div" and not f.cls else None)
        if h3 is not None:
            title, title_tone = text_of(h3), color_tone(h3)
            if h3 is not f:
                chip = ihtml_nodes([c for c in f.children if c is not h3])
            del rest[first]
    token = title.split()[0] if title else ""
    saved, ctx.ticker_hint = ctx.ticker_hint, (token if re.fullmatch(r"[A-Z][A-Z0-9]{1,5}", token) else None)
    blocks = blocks_of(rest, ctx)
    ctx.ticker_hint = saved
    return {"title": title, "title_tone": title_tone, "chip": chip,
            "tone": var_tone(st.get("border-left") or st.get("border-left-color")),
            "outline": var_tone(st.get("border")), "blocks": blocks}


def advisor_block(el, ctx):
    hd, bd = el.child(cls="hd"), el.child(cls="bd")
    tk_el = find(hd, lambda n: "t" in n.cls) if hd is not None else None
    v_el = find(hd, lambda n: "verdict" in n.cls) if hd is not None else None
    sub = next((c for c in hd.els() if c is not tk_el and c is not v_el), None) if hd is not None else None
    verdict = text_of(v_el)
    vclass = next((k[2:] for k in VERDICT_CLASSES if v_el is not None and k in v_el.cls), None)
    if vclass is None:
        up = verdict.upper()
        vclass = "add" if up.startswith("ADD") else ("trim" if up.startswith("TRIM") else "hold")
    body = bd.children if bd is not None else [c for c in el.children if c is not hd]
    block = {"t": "advisor", "ticker": text_of(tk_el), "subtitle": text_of(sub), "verdict": verdict,
             "verdict_class": vclass, "blocks": blocks_of(body, ctx)}
    if not block["ticker"]:
        ctx.warnings.append("Mục %s: một khối hội đồng cố vấn không có mã" % (ctx.section or "?"))
    ctx.advisors.append(block)
    return block


def voice_block(el):
    who = el.child(cls="who")
    return {"t": "voice", "side": "kill" if "kill" in el.cls else "alpha", "who": text_of(who),
            "html": ihtml_nodes([c for c in el.children if c is not who])}


def svg_block(el, ctx):
    aria = WS_RE.sub(" ", el.attrs.get("aria-label") or "").strip()
    if aria.startswith("Dải định giá"):
        return [band_block(aria, ctx)]
    if aria.startswith("Phân bố"):
        return [dist_block(el, aria, ctx)]
    return []


def band_live(tk, key, ctx):
    live = ctx.live
    ent = live.ticker(tk) if live is not None else {}
    m = _dict(ent.get(key))
    if not m:
        return None
    s = finite(m.get("sigma"))
    out = {k: num_out(finite(m.get("band_" + k))) for k in ("cheap2", "cheap1", "fair", "rich1", "rich2")}
    price_day = parse_iso(ent.get("price_date"))
    out.update({"price": num_out(finite(ent.get("price_now"))),
                "as_of": dmy(price_day) if price_day else live.as_of_txt, "sigma": s,
                "sigma_txt": fmt_sigma(s), "zone_key": zone3(s)})
    return out


def band_block(aria, ctx):
    m = BAND_RE.search(aria)
    tk = ctx.ticker_hint
    if not m or not tk:
        ctx.warnings.append("Mục %s: không đọc được dải giá σ (%s)" % (ctx.section or "?", clip(aria, 80)))
        return p_block(None, ihtml_text(aria))
    metric = "P/E" if m.group(1).upper().endswith("E") else "P/B"
    v = [num_out(vn_num(g)[0]) for g in m.groups()[1:]]
    return {"t": "band", "ticker": tk, "metric": metric, "cheap2": v[0], "cheap1": v[1], "fair": v[2],
            "rich1": v[3], "rich2": v[4], "price": v[5], "label": aria,
            "live": band_live(tk, "pe" if metric == "P/E" else "pb", ctx)}


def dist_points(entries, metric_fn, mine):
    pts = []
    for tk, ent in entries:
        pe, pb = metric_fn(ent, "pe"), metric_fn(ent, "pb")
        s = min_sigma([(pe[1], pe[2]), (pb[1], pb[2])])
        if s is not None:
            pts.append({"tk": tk, "s": s, "mine": tk in mine})
    return pts


def dist_block(el, aria, ctx):
    texts = [t for t in iter_els(el) if t.tag == "text"]
    rows = [(r.get("t"), r) for r in ctx.rows if isinstance(r, dict) and isinstance(r.get("t"), str)]
    issue = dist_points(rows, row_metric, ctx.mine)
    live_pts = dist_points(ctx.live.by_ticker.items(), live_metric, ctx.mine) if ctx.live is not None else []
    printed = vn_num(aria)[0]
    if printed is not None and int(printed) != len(issue):
        ctx.warnings.append("Mục %s: trang ghi phân bố σ của %d mã, tính lại từ snapshot được %d mã"
                            % (ctx.section or "?", int(printed), len(issue)))
    ranked = [p["tk"] for p in sorted(issue, key=lambda p: p["s"])]
    labels = []
    for tk in [t for t in ctx.mine if any(p["tk"] == t for p in issue)] + ranked[:3] + ranked[-3:]:
        if tk not in labels:
            labels.append(tk)
    return {"t": "dist", "caption": ihtml_text(text_of(texts[-1])) if texts else "",
            "issue": {"n": len(issue), "as_of": ctx.snap_as_of_txt, "points": issue},
            "live": {"n": len(live_pts), "as_of": ctx.live.as_of_txt, "points": live_pts} if live_pts else None,
            "labels": labels}


# ── Masthead, script data, whole page ───────────────────────────────────────


def chip_of(el):
    text = text_of(el)
    m = re.match(r"(%s)\b" % "|".join(re.escape(t) for t in TIERS), text)
    tone = "up" if "t1" in el.cls else ("ref" if "t3" in el.cls else color_tone(el))
    return {"text": text, "tier": m.group(1) if m else "", "tone": tone}


def stat_live(label, ctx):
    """Engine rule 4b: the live line under a masthead stat tile (None when nothing maps)."""
    low, live = label.lower(), ctx.live
    if live is not None and live.ok:
        if low.startswith("vn-index p/e") and live.index_pe:
            s = finite(live.index_pe.get("sigma"))
            return {"text": "live %s: %s× · %s" % (dm(live.as_of), fmt_trim(live.index_pe.get("now")), fmt_sigma(s)),
                    "tone": zone_tone(s)}
        if low.startswith("loại họ vin") and live.exvic3:
            s = finite(live.exvic3.get("exv3_pe_sigma"))
            return {"text": "live %s: %s× · %s" % (dm(parse_iso(live.exvic3.get("as_of")) or live.as_of),
                                                  fmt_trim(live.exvic3.get("pe_exv3_now")), fmt_sigma(s)),
                    "tone": zone_tone(s)}
        if low.startswith("độ rộng") and live.zone_dist:
            pe, pb = breadth_live(live, "pe"), breadth_live(live, "pb")
            if pe or pb:
                return {"text": "live: %s · P/B %s" % (breadth_txt(pe), breadth_txt(pb)), "tone": "muted"}
        if low.startswith("họ vin chiếm") and live.exvic3:
            return {"text": "live %s: %s%%" % (dm(parse_iso(live.exvic3.get("as_of")) or live.as_of),
                                               fmt_trim(live.exvic3.get("w3_now"), 1)), "tone": "muted"}
    ds = dates_in(label, ctx.ky)
    if ds and all(d < ctx.today for d in ds):
        return {"text": "đã qua (hôm nay %s)" % dm(ctx.today), "tone": "muted"}
    return None


def breadth_live(live, key):
    zd = _dict(live.zone_dist.get(key))
    counts = {"cheap": 0, "neutral": 0, "rich": 0}
    for label, n in zd.items():
        z = label_zone(label)
        if z and finite(n) is not None:
            counts[z] += int(n)
    return [counts["cheap"], counts["neutral"], counts["rich"]] if zd else None


def breadth_txt(c):
    return " / ".join(str(x) for x in c) if c else "—"


def _js_value(code, pattern):
    m = re.search(pattern, code)
    if not m:
        return None
    try:
        return json.JSONDecoder().raw_decode(code, m.end())[0]
    except ValueError:
        return None


def script_data(root, warnings):
    code = "\n".join(c for s in find_all(root, lambda n: n.tag == "script") for c in s.children if isinstance(c, str))
    rows = _js_value(code, r"\bvar\s+D\s*=\s*")
    mine = _js_value(code, r"\bMINE\s*=\s*")
    avoid = _js_value(code, r"\bAV\s*=\s*")
    if not isinstance(rows, list):
        warnings.append("Không đọc được bảng snapshot `var D=[…]` trong trang — mục 07 và phần so live theo mã "
                        "để trống")
        rows = []
    rows = [r for r in rows if isinstance(r, dict) and isinstance(r.get("t"), str)]
    lists = []
    for name, v in (("MINE", mine), ("AV", avoid)):
        if not isinstance(v, list):
            warnings.append("Không đọc được danh sách %s trong trang — để trống" % name)
            v = []
        lists.append([x for x in v if isinstance(x, str)])
    return rows, lists[0], lists[1]


def parse_header(mast, stats_el, ctx):
    out = {"kicker": [], "title": "", "lede": "", "chips": [], "status": "", "stats": []}
    status_el = None
    if mast is None:
        ctx.warnings.append("Không tìm thấy phần đầu trang (header.mast) — tiêu đề và nguồn để trống")
    else:
        kick = mast.child(cls="kicker")
        spans = kick.els() if kick is not None else find_all(mast, lambda n: "eyebrow" in n.cls)
        out["kicker"] = [t for t in (text_of(s) for s in spans) if t]
        out["title"] = text_of(find(mast, lambda n: n.tag == "h1"), newline_br=True)
        out["lede"] = ihtml(find(mast, lambda n: n.tag == "p" and "lede" in n.cls))
        prov = find(mast, lambda n: "provenance" in n.cls)
        if prov is not None:
            out["chips"] = [chip_of(c) for c in find_all(prov, lambda n: "chip" in n.cls)]
        seen_prov = prov is None
        for c in mast.els():
            if c is prov:
                seen_prov = True
            elif seen_prov and c.tag == "p" and "lede" not in c.cls:
                status_el = c
                break
        out["status"] = ihtml(status_el)
    if stats_el is None:
        ctx.warnings.append("Không tìm thấy hàng số liệu đầu trang (div.stats)")
    else:
        for s in stats_el.els():
            if "stat" in s.cls:
                item = stat_of(s)
                item["live"] = stat_live(item["label"], ctx)
                out["stats"].append(item)
    return out, status_el


def parse_section(sec, ctx):
    head = sec.child(cls="sechead")
    ctx.section = text_of(head.child(cls="n")) if head is not None else ""
    title = text_of(find(head, lambda n: n.tag in ("h2", "h3"))) if head is not None else ""
    eyebrow = text_of(head.child(cls="eyebrow")) if head is not None else ""
    if head is None:
        ctx.warnings.append("Một mục (section) không có tiêu đề div.sechead")
    return {"id": ctx.section, "title": title, "eyebrow": eyebrow,
            "blocks": safe_blocks([c for c in sec.children if c is not head], ctx)}


def safe_blocks(children, ctx):
    """blocks_of; nesting too deep for the block converters → a warning + the raw text as one {"t":"p"}."""
    try:
        return blocks_of(children, ctx)
    except RecursionError:
        ctx.ticker_hint = None
        ctx.warnings.append("Mục %s lồng thẻ quá sâu, không dựng được bố cục — hiện dạng chữ thô"
                            % (ctx.section or "?"))
        frag = Node("#frag", {})
        frag.children = list(children)
        h = ihtml_text(text_of(frag))
        return [p_block(None, h)] if h else []


def first_match(regex, texts):
    for t in texts:
        m = regex.search(t or "")
        if m:
            return m
    return None


def parse_issue(src, ky, today, live, warnings):
    """Whole page → dict(header, sections, footer, links, rows, mine, avoid, ctx, vintage fields)."""
    tb = TreeBuilder()
    try:
        tb.feed(src)
        tb.close()
    except Exception as exc:  # html.parser is forgiving; keep whatever was built before the failure
        warnings.append("Trình đọc HTML dừng giữa chừng (%s: %s) — phần còn lại bị bỏ qua" % (type(exc).__name__, exc))
    unclosed = [n.tag for n in tb.stack[1:] if n.tag not in ("html", "body")]
    if unclosed:
        warnings.append("Trang bản tuần có vẻ bị cắt cụt: %d thẻ chưa đóng khi hết tệp (… %s)"
                        % (len(unclosed), " > ".join(unclosed[-4:])))
    root = tb.root
    rows, mine, avoid = script_data(root, warnings)
    wrap = find(root, lambda n: n.tag == "div" and "wrap" in n.cls) or find(root, lambda n: n.tag == "body") or root
    mast = find(wrap, lambda n: n.tag == "header")
    footer = find(wrap, lambda n: n.tag == "footer")
    stats_el = next((c for c in wrap.els() if "stats" in c.cls), None)
    status_guess = [text_of(c) for c in (mast.els() if mast is not None else [])
                    if c.tag == "p" and "lede" not in c.cls]
    texts = status_guess[-1:] + [text_of(footer)]
    m = first_match(AS_OF_RE, texts)
    data_as_of = None
    if m:
        try:
            data_as_of = datetime.strptime(m.group(1), "%d/%m/%Y").date()
        except ValueError:
            data_as_of = None
    if data_as_of is None:
        warnings.append("Bản tuần không ghi rõ ngày chốt dữ liệu định giá (\"chốt phiên dd/mm/yyyy\") [CẦN DATA]")
    m = first_match(ENGINE_RUN_RE, texts)
    ctx = Ctx(ky, today, live, rows, mine, avoid, dmy(data_as_of), warnings)
    header, status_el = parse_header(mast, stats_el, ctx)
    secs = [c for c in wrap.els() if c.tag == "section"] or \
        [s for s in find_all(wrap, lambda n: n.tag == "section")]
    if not secs:
        warnings.append("Không tìm thấy mục (section) nào trong trang")
    sections = [parse_section(s, ctx) for s in secs]
    ctx.section = "footer"
    nav = find(wrap, lambda n: n.tag == "nav")
    links = []
    for a in (find_all(nav, lambda n: n.tag == "a") if nav is not None else []):
        def part(name, a=a):
            return text_of(find(a, lambda n: name in n.cls))
        links.append({"kind": part("dual-k"), "title": part("dual-t") or text_of(a), "url": a.attrs.get("href", ""),
                      "desc": part("dual-d")})
    rev = REV_RE.search(" · ".join(header["kicker"]))
    return {"header": header, "sections": sections,
            "footer": safe_blocks(footer.children, ctx) if footer is not None else [],
            "links": links, "rows": rows, "mine": mine, "avoid": avoid, "ctx": ctx,
            "data_as_of": data_as_of, "engine_run": ("%s %s ICT" % (m.group(1), m.group(2))) if m else None,
            "rev": "rev.%s" % rev.group(1) if rev else None, "page_text": text_of(wrap)}


# ── Core extracts (portfolio, rigor, breadth) ───────────────────────────────


def plain_of_ihtml(h):
    return WS_RE.sub(" ", html.unescape(re.sub(r"<[^>]*>", " ", h or ""))).strip()


def portfolio_of(page_text, warnings):
    """→ (core.portfolio | None, [parts that are not one "name nn%"]) — unread parts also become a warning."""
    m = PORTFOLIO_RE.search(page_text or "")
    if not m:
        return None, []
    items, skipped = [], []
    for part in m.group(1).split("·"):
        part = part.strip()
        # one "name nn%" per part; words after the % ("(giữ)", ")", the next cell's text) are ignored
        mm = PORTFOLIO_ITEM_RE.match(part) if len(PORTFOLIO_PCT_RE.findall(part)) == 1 else None
        if mm and mm.group(1).strip():
            items.append({"name": mm.group(1).strip(), "pct": float(mm.group(2).replace(",", "."))})
        elif part:
            skipped.append(part)
    if skipped:
        warnings.append("Danh mục tham chiếu: không đọc được %d mục (%s) — tổng danh mục chưa kiểm được"
                        % (len(skipped), "; ".join(clip(s, 40) for s in skipped)))
    if not items:
        return None, skipped
    total = sum(i["pct"] for i in items)
    return {"items": items, "sum": total, "sum_txt": fmt_trim(total, 1) + "%",
            "text": "Danh mục tham chiếu hiện là " + m.group(1).strip()}, skipped


def rigor_of(t):
    """One rigor table → (core.rigor entry, ok|None, printed display strings)."""
    texts = [[text_of(td) for td in r] for r in t["rows"]]
    avg_rows = [r for r in texts if r and r[0].startswith("Trung bình")]
    dims = [r for r in texts if r and not r[0].startswith("Trung bình")]
    hc = t["head_cols"]  # header cells expanded by colspan; may still be narrower than the body rows
    cols = [i for i, h in enumerate(hc) if i > 0 and h["align"] == "r"]
    if not cols:
        width = max((len(r) for r in dims), default=0)
        cols = [i for i in range(1, width)
                if dims and sum(1 for r in dims if i < len(r) and vn_num(r[i])[0] is not None) * 2 > len(dims)]
    scores = [[vn_num(r[i])[0] if i < len(r) else None for i in cols] for r in dims]
    calc = []
    for k in range(len(cols)):
        vals = [s[k] for s in scores if s[k] is not None]
        # exact decimal mean: float sum/len puts 24,9/6 at 4,1499… and half-up would print 4,1 instead of 4,2
        calc.append(float(sum(Decimal(repr(v)) for v in vals) / len(vals)) if vals else None)
    printed, decs, src = [None] * len(cols), [2] * len(cols), None
    if avg_rows:
        src = "row"
        for k, i in enumerate(cols):
            v, d = vn_num(avg_rows[0][i]) if i < len(avg_rows[0]) else (None, 0)
            printed[k], decs[k] = v, (d if v is not None else 2)
    else:
        m = AVG_CAPTION_RE.search(t["caption"])
        if m:
            src = "caption"
            for k, part in enumerate(re.split(r"\s*(?:→|->)\s*", m.group(1))[: len(cols)]):
                printed[k], decs[k] = vn_num(part)
    checks = [abs(half_up(c, d) - p) < 0.005 for c, p, d in zip(calc, printed, decs) if c is not None and p is not None]
    entry = {"table_id": t["id"], "section": t["section"], "cols": [hc[i]["text"] if i < len(hc) else "" for i in cols],
             "dims": [{"name": r[0], "scores": s} for r, s in zip(dims, scores)], "calc_avg": calc,
             "calc_avg_txt": [fmt_dec(c, d) for c, d in zip(calc, decs)], "printed_avg": printed,
             "printed_src": src if any(p is not None for p in printed) else None}
    return entry, (all(checks) if checks else None), [fmt_dec(p, d) for p, d in zip(printed, decs)]


def recount(rows, key):
    counts, missing = {"cheap": 0, "neutral": 0, "rich": 0}, 0
    for r in rows:
        m = r.get(key)
        z = label_zone(m[3]) if isinstance(m, list) and len(m) > 3 else None
        if z:
            counts[z] += 1
        else:
            missing += 1
    return [counts["cheap"], counts["neutral"], counts["rich"]], missing


def stat_by(stats, prefix):
    return next((s for s in stats if s["label"].lower().startswith(prefix)), None)


def printed_breadth(stat):
    if stat is None:
        return None, None
    pe = [int(x) for x in re.findall(r"\d+", stat["value"])][:3]
    m = re.search(r"P/B\s*:?\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)", plain_of_ihtml(stat["sub"]))
    return (pe if len(pe) == 3 else None), ([int(x) for x in m.groups()] if m else None)


# ── Engine ───────────────────────────────────────────────────────────────────


def _delta(a, b, dec=2, unit=""):
    if a is None or b is None:
        return "—"
    return fmt_dec(b - a, dec, sign=True) + unit


def drift_rows(stats, live):
    rows = []
    ok = live is not None and live.ok
    vn = stat_by(stats, "vn-index p/e")
    if vn is not None:
        sub = plain_of_ihtml(vn["sub"])
        m = re.search(r"chỉ số\s+(\d[\d   .]*(?:,\d+)?)", sub)
        lvl, d = vn_num(m.group(1)) if m else (None, 0)
        close = live.close if ok else None
        pct = " (%s%%)" % fmt_dec((close / lvl - 1) * 100, 1, sign=True) if lvl and close else ""
        rows.append({"muc": "VN-Index", "issue_txt": fmt_dec(lvl, d), "live_txt": fmt_dec(close, 1),
                     "delta_txt": _delta(lvl, close, 1) + (pct if lvl and close else ""), "changed": False})
        now, d = vn_num(vn["value"])
        s = vn_sigma(sub)
        lnow = finite(live.index_pe.get("now")) if ok else None
        ls = finite(live.index_pe.get("sigma")) if ok else None
        rows.append(_ratio_row("VN-Index P/E", now, d, s, lnow, ls))
    ex = stat_by(stats, "loại họ vin")
    if ex is not None:
        now, d = vn_num(ex["value"])
        lnow = finite(live.exvic3.get("pe_exv3_now")) if ok else None
        ls = finite(live.exvic3.get("exv3_pe_sigma")) if ok else None
        rows.append(_ratio_row("Loại họ Vin P/E", now, d, vn_sigma(plain_of_ihtml(ex["sub"])), lnow, ls))
    w3 = stat_by(stats, "họ vin chiếm")
    if w3 is not None:
        v, d = vn_num(w3["value"])
        lv = finite(live.exvic3.get("w3_now")) if ok else None
        rows.append({"muc": "Họ Vin % vốn hóa", "issue_txt": fmt_dec(v, d) + "%" if v is not None else "—",
                     "live_txt": fmt_trim(lv, 1) + "%" if lv is not None else "—",
                     "delta_txt": _delta(v, lv, 1, " điểm %"), "changed": False})
    pe_p, pb_p = printed_breadth(stat_by(stats, "độ rộng"))
    for name, printed, key in (("Độ rộng P/E", pe_p, "pe"), ("Độ rộng P/B", pb_p, "pb")):
        if printed is None:
            continue
        lv = breadth_live(live, key) if ok else None
        diffs = [b - a for a, b in zip(printed, lv)] if lv else None
        rows.append({"muc": name, "issue_txt": breadth_txt(printed), "live_txt": breadth_txt(lv),
                     "delta_txt": " / ".join(fmt_dec(x, 0, sign=True) for x in diffs) if diffs else "—",
                     "changed": bool(diffs) and any(abs(x) >= 3 for x in diffs)})
    return rows


def _ratio_row(muc, now, dec, s, lnow, ls):
    return {"muc": muc,
            "issue_txt": "%s× · %s" % (fmt_dec(now, dec), fmt_sigma(s)) if now is not None else "—",
            "live_txt": "%s× · %s" % (fmt_trim(lnow), fmt_sigma(ls)) if lnow is not None else "—",
            "delta_txt": "%s · %s" % (_delta(now, lnow, 2, "×"), _delta(s, ls, 2, "σ"))
            if now is not None and lnow is not None else "—",
            "changed": zone3(s) is not None and zone3(ls) is not None and zone3(s) != zone3(ls)}


def ticker_rows(rows, mine, avoid, advisors, live):
    by_tk = {r["t"]: r for r in rows}
    verdicts = {a["ticker"]: a["verdict"] for a in advisors if a["ticker"]}
    order = []
    for tk in list(mine) + list(avoid) + list(verdicts):
        if tk not in order:
            order.append(tk)
    out = []
    for tk in order:
        pe, pb = row_metric(by_tk.get(tk), "pe"), row_metric(by_tk.get(tk), "pb")
        ent = live.ticker(tk) if live is not None and live.ok else {}
        lpe, lpb = live_metric(ent, "pe"), live_metric(ent, "pb")
        zi = zone3(min_sigma([(pe[1], pe[2]), (pb[1], pb[2])], fallback=True))
        zl = zone3(min_sigma([(lpe[1], lpe[2]), (lpb[1], lpb[2])], fallback=True)) if ent else None
        out.append({"tk": tk, "mine": tk in mine, "avoid": tk in avoid, "advisor": verdicts.get(tk, ""),
                    "pe_issue_txt": fmt_ratio_sigma(pe[0], pe[1]), "pe_live_txt": fmt_ratio_sigma(lpe[0], lpe[1]),
                    "pb_issue_txt": fmt_ratio_sigma(pb[0], pb[1]), "pb_live_txt": fmt_ratio_sigma(lpb[0], lpb[1]),
                    "zone_issue": zi, "zone_live": zl, "changed": zi is not None and zl is not None and zi != zl})
    return out


def basket_rows(ctx, live):
    t = next((t for t in ctx.tables if t["kind"] == "basket"), None)
    if t is None:
        return []
    sig_cols = [i for i, h in enumerate(t["head"]) if h["text"].strip() == "σ"]
    out = []
    for tds in t["rows"]:
        if not tds:
            continue
        tk = find(tds[0], lambda n: "tk" in n.cls)
        sub = find(tds[0], lambda n: n.tag == "div")
        code = text_of(tk) if tk is not None else (text_of(tds[0]).split() or [""])[0]
        sig = [vn_sigma(text_of(tds[i])) if i < len(tds) else None for i in sig_cols[:2]] + [None, None]
        b = live.baskets.get(code) if live is not None else None
        lsig = [finite(_dict(_dict(b).get(k)).get("sigma")) for k in ("pe", "pb")]
        changed = any(zone3(a) != zone3(c) for a, c in zip(sig[:2], lsig) if a is not None and c is not None)
        out.append({"code": code, "label": text_of(sub) or str(_dict(b).get("label") or ""),
                    "pe_issue_txt": fmt_sigma(sig[0]), "pe_live_txt": fmt_sigma(lsig[0]),
                    "pb_issue_txt": fmt_sigma(sig[1]), "pb_live_txt": fmt_sigma(lsig[1]), "changed": changed})
    return out


def level_values(text):
    """VN-Index levels 1.000–2.999 in text → [(value, span_start, span_end)]; a range yields both ends."""
    ms, vals, i = list(LEVEL_NUM_RE.finditer(text)), [], 0
    while i < len(ms):
        group = [ms[i]]
        while i + 1 < len(ms) and LEVEL_RANGE_SEP_RE.fullmatch(text[group[-1].end(): ms[i + 1].start()]):
            i += 1
            group.append(ms[i])
        if not LEVEL_UNIT_RE.match(text, group[-1].end()):
            span = (group[0].start(), group[-1].end())
            vals.extend((v,) + span for v in (int(g.group(1).replace(".", "")) for g in group) if 1000 <= v <= 2999)
        i += 1
    return vals


def snippet(text, start, end, n=TEXT_MAX):
    """≤ n chars of text around [start, end), cut at spaces, "…" where clipped."""
    if len(text) <= n:
        return text
    lo = max(0, min(start - (n - (end - start)) // 2, len(text) - n + 2))
    hi = min(len(text), lo + n - 2)
    if lo > 0:
        sp = text.find(" ", lo, start)
        lo = sp + 1 if sp >= 0 else lo
    if hi < len(text):
        sp = text.rfind(" ", end, hi)
        hi = sp if sp >= 0 else hi
    return ("…" if lo > 0 else "") + text[lo:hi].strip() + ("…" if hi < len(text) else "")


def action_rows(ctx):
    for t in ctx.tables:
        if t["kind"] == "action":
            for i, tds in enumerate(t["rows"]):
                cells = [text_of(td) for td in tds]
                yield t["id"], i, cells, " · ".join(c for c in cells if c)


def levels_of(ctx, live):
    """Levels are read per sentence: a sentence must name the index (LEVEL_KW_RE) and must not be a
    broker forecast ("Dự báo …: BVSC 1.765–1.785"), and a level being replaced ("thay 1.820 bằng …")
    is not a level any more — anywhere in the issue, whichever table is read first."""
    out = []
    close = live.close if live is not None and live.ok else None
    sentences = [s for _tid, _i, _cells, row_text in action_rows(ctx) for s in SENTENCE_SPLIT_RE.split(row_text)
                 if LEVEL_KW_RE.search(s) and "dự báo" not in s.lower()]
    seen = {lvl for s in sentences for lvl, a, _b in level_values(s) if s[max(0, a - 5):a].lower() == "thay "}
    for sentence in sentences:
        for lvl, a, b in level_values(sentence):
            if lvl in seen:
                continue
            seen.add(lvl)
            out.append(level_entry(lvl, snippet(sentence, a, b), close, live))
    return out


def level_entry(lvl, context, close, live):
    gap = close / lvl - 1 if close else None
    return {"level": float(lvl), "level_txt": fmt_dec(lvl, 0), "context": context,
            "live_txt": "%s (%s)" % (fmt_dec(close, 1), dm(live.close_date)) if close else "—",
            "gap_txt": fmt_dec(gap * 100, 1, sign=True) + "%" if gap is not None else "—",
            "side": ("trên" if gap >= 0 else "dưới") if gap is not None else ""}


def past_of(ctx):
    out = []
    for tid, i, cells, row_text in action_rows(ctx):
        ds = dates_in(cells[0] if cells else "", ctx.ky)
        if ds and all(d < ctx.today for d in ds):
            out.append({"date": dm(max(ds)), "text": clip(row_text), "table_id": tid, "row": i})
    return out


def kiem_lines(p, meta, core, drift, tickers, levels, past, live):
    ctx, stats = p["ctx"], p["header"]["stats"]
    k = []
    age_txt = "Kỳ %s · %d ngày tuổi · kỳ kế tiếp dự kiến %s" % (meta["ky_txt"], meta["age_days"], meta["next_due_txt"])
    k.append({"muc": "Tuổi bản tuần", "ok": not meta["stale"],
              "text": age_txt + (" — " + meta["stale_text"] if meta["stale"] else "")})
    vint_ok = None
    if p["data_as_of"] is None:
        vint = "Bản tuần không ghi ngày chốt dữ liệu định giá [CẦN DATA]"
    else:
        vint = "Định giá trong bản tuần chốt %s" % meta["data_as_of_txt"]
        if meta["engine_run"]:
            vint += " (engine chạy %s)" % meta["engine_run"]
        lag = (ctx.ky - p["data_as_of"]).days
        if lag > 0:
            vint += ", trước ngày phát hành %d ngày" % lag
        if live.ok and live.as_of:
            d = (live.as_of - p["data_as_of"]).days
            if d > 0:
                vint += " · live chốt %s, mới hơn %d ngày" % (live.as_of_txt, d)
            elif d == 0:
                vint += " · live chốt %s, cùng ngày chốt" % live.as_of_txt
            else:  # the live pipeline is behind the issue: every live comparison below uses older numbers
                vint += " · live chốt %s, cũ hơn %d ngày — dữ liệu live chưa cập nhật" % (live.as_of_txt, -d)
                vint_ok = False
    k.append({"muc": "Vintage định giá", "ok": vint_ok, "text": vint})
    pe_p, pb_p = printed_breadth(stat_by(stats, "độ rộng"))
    (pe_c, pe_miss), (pb_c, pb_miss) = recount(p["rows"], "pe"), recount(p["rows"], "pb")
    if not p["rows"]:
        k.append({"muc": "Độ rộng (đếm lại)", "ok": None, "text": "Không có snapshot để đếm lại [CẦN DATA]"})
    else:
        ok = None if pe_p is None and pb_p is None else \
            all(a == b for a, b in ((pe_p, pe_c), (pb_p, pb_c)) if a is not None)
        miss = ["%d mã không có %s" % (n, t) for t, n in (("P/E", pe_miss), ("P/B", pb_miss)) if n]
        txt = "Đếm lại %d dòng snapshot theo nhãn vùng: P/E %s · P/B %s" % (len(p["rows"]), breadth_txt(pe_c),
                                                                           breadth_txt(pb_c))
        if miss:
            txt += " (%s)" % ", ".join(miss)
        txt += " — %s số in P/E %s · P/B %s" % ("khớp" if ok else ("lệch" if ok is False else "không có"),
                                               breadth_txt(pe_p), breadth_txt(pb_p))
        k.append({"muc": "Độ rộng (đếm lại)", "ok": ok, "text": txt})
    for entry, ok, printed_txt in p["rigor"]:
        txt = "Bảng %s (mục %s, %d chiều): tính lại %s" % (entry["table_id"], entry["section"], len(entry["dims"]),
                                                           " | ".join(entry["calc_avg_txt"]) or "—")
        if entry["printed_src"]:
            src = "dòng Trung bình" if entry["printed_src"] == "row" else "chú thích bảng"
            txt += " — %s số in %s (%s)" % ("khớp" if ok else "lệch", " | ".join(printed_txt), src)
        else:
            txt += " — bảng không in trung bình"
        k.append({"muc": "Rigor %s" % entry["table_id"], "ok": ok, "text": txt})
    pf, skipped = core["portfolio"], p["portfolio_skipped"]
    if pf is None:
        k.append({"muc": "Danh mục tham chiếu", "ok": None,
                  "text": ("Không đọc được mục nào trong câu “Danh mục tham chiếu hiện là …” [CẦN DATA]" if skipped
                           else "Không tìm thấy câu “Danh mục tham chiếu hiện là …” [CẦN DATA]")})
    else:
        cash = [i for i in pf["items"] if i["name"].lower().startswith("tiền mặt")]
        n = len(pf["items"]) - len(cash)
        detail = "%d mã" % n + (" + tiền mặt %s%%" % fmt_trim(sum(i["pct"] for i in cash), 1) if cash else "")
        ok = abs(pf["sum"] - 100.0) <= 0.5
        txt = "Danh mục tham chiếu cộng lại %s (%s)" % (pf["sum_txt"], detail)
        if skipped:  # an incomplete list is never scored against 100%
            ok = None
            txt += " — %d mục không đọc được (%s), chưa kiểm được tổng [CẦN DATA]" % (
                len(skipped), "; ".join(clip(s, 40) for s in skipped))
        elif not ok:
            txt += " — lệch %s điểm %% so với 100%%" % fmt_trim(pf["sum"] - 100.0, 1, sign=True)
        k.append({"muc": "Danh mục tham chiếu", "ok": ok, "text": txt})
    if past:
        txt = "%d việc trong bảng hành động đã quá ngày (hôm nay %s): %s" % (
            len(past), dm(ctx.today), " | ".join("%s · %s" % (x["date"], clip(x["text"], 60)) for x in past))
    else:
        txt = "Không có việc nào trong bảng hành động đã quá ngày (hôm nay %s)" % dm(ctx.today)
    k.append({"muc": "Mốc đã qua", "ok": None, "text": txt})
    if levels:
        # One line for all levels; the per-level context lives in engine.levels.
        if levels[0]["side"]:
            parts = ["%s (%s %s)" % (lv["level_txt"], lv["side"], lv["gap_txt"].lstrip("+" + MINUS)) for lv in levels]
            txt = "VN-Index live %s so với các mốc bảng hành động: %s" % (levels[0]["live_txt"], " · ".join(parts))
        else:
            txt = "Mốc %s — chưa có giá đóng cửa live để so" % " · ".join(lv["level_txt"] for lv in levels)
        k.append({"muc": "Mức chỉ số", "ok": None, "text": txt})
    if not live.ok:
        k.append({"muc": "Drift so với live", "ok": None, "text": "Không có dữ liệu live — chưa so được drift"})
    else:
        mine_rows = [t for t in tickers if t["mine"]]
        moved = [t for t in mine_rows if t["changed"]]
        # a mã with no σ on either side was not compared — it must not count as "unchanged"
        blind = [t["tk"] for t in mine_rows if t["zone_issue"] is None or t["zone_live"] is None]
        if len(blind) == len(mine_rows):
            ok = None
            txt = ("Không so được mã danh mục nào — thiếu σ ở bản tuần hoặc live: %s [CẦN DATA]" % ", ".join(blind)
                   if blind else "Bản tuần không có danh sách mã danh mục để so [CẦN DATA]")
        else:
            ok = False if moved else (None if blind else True)
            txt = "%d mã danh mục đổi vùng từ bản tuần" % len(moved)
            if moved:
                txt += ": " + ", ".join("%s (%s → %s)" % (t["tk"], ZONE_VI[t["zone_issue"]], ZONE_VI[t["zone_live"]])
                                        for t in moved)
            if blind:
                txt += " · không so được (thiếu σ): %s [CẦN DATA]" % ", ".join(blind)
        others = [t["tk"] for t in tickers if not t["mine"] and t["changed"]]
        if others:
            txt += " · ngoài danh mục: " + ", ".join(others)
        heads = [d["muc"] for d in drift if d["changed"]]
        if heads:
            txt += " · chỉ tiêu đầu trang đổi: " + ", ".join(heads)
        k.append({"muc": "Drift so với live", "ok": ok, "text": txt})
    return k


# ── Payload ──────────────────────────────────────────────────────────────────


def csv_of(rows, mine, avoid, live):
    out = []
    for r in rows:
        tk = r["t"]
        pe, pb = row_metric(r, "pe"), row_metric(r, "pb")
        ent = live.ticker(tk) if live is not None and live.ok else {}
        f = r.get("f") if isinstance(r.get("f"), list) else []
        c = r.get("c") if isinstance(r.get("c"), list) else []
        fv = [f[i] if i < len(f) else None for i in range(6)]
        cv = [c[i] if i < len(c) else None for i in range(6)]
        tp = fmt_dec(finite(fv[3]), 0)
        if fv[4] and tp != "—":
            tp += " " + str(fv[4])
        cat = " ".join(str(x) for x in (cv[3], cv[4], cv[5]) if x) if cv[5] else "—"
        out.append([tk, "danh mục" if tk in mine else ("tránh" if tk in avoid else ""),
                    fmt_dec(pe[0]), fmt_dec(pe[1], sign=True), fmt_dec(live_metric(ent, "pe")[1], sign=True),
                    fmt_dec(pb[0]), fmt_dec(pb[1], sign=True), fmt_dec(live_metric(ent, "pb")[1], sign=True),
                    fmt_dec(finite(r.get("p")), 0), fmt_dec(finite(fv[0])), tp, cat])
    return {"columns": CSV_COLUMNS, "rows": out}


def snapshot_live(rows, live):
    if live is None or not live.ok:
        return None
    out = {}
    for r in rows:
        ent = live.ticker(r["t"])
        if not ent:
            continue
        pair = {}
        for key in ("pe", "pb"):
            now, s, _ = live_metric(ent, key)
            pair[key] = [now, s] if isinstance(ent.get(key), dict) else None
        out[r["t"]] = {"pe": pair["pe"], "pb": pair["pb"], "price": finite(ent.get("price_now"))}
    return out


def read_issue(wdir, ky, today, live, warnings):
    path = issue_path(wdir, ky)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            src = fh.read()
    except OSError as exc:
        raise WeeklyError("NO_ISSUE", "Không đọc được bản tuần %s (%s) — kiểm tra quyền đọc tệp trong %s"
                          % (os.path.basename(path), exc, wdir))
    p = parse_issue(src, parse_iso(ky), today, live, warnings)
    p["rigor"] = [rigor_of(t) for t in p["ctx"].tables if t["kind"] == "rigor"]
    p["path"] = path
    return p


def age_fields(ky, today, issues):
    kd = parse_iso(ky)
    due = kd + timedelta(days=ISSUE_PERIOD_DAYS)
    age = (today - kd).days
    # contract example: kỳ 14/09 read on 23/09 (age 9) is stale — hence ≥ at the end of the grace days
    stale = today >= due + timedelta(days=STALE_GRACE_DAYS)
    text = ""
    if stale:
        newer = [k for k in issues if k > ky]
        text = "BẢN TUẦN CŨ %d ngày — " % age + ("đã có kỳ mới hơn %s" % dmy(parse_iso(newer[0])) if newer
                                                 else "kỳ %s chưa có" % dm(due))
    return {"age_days": age, "next_due": due.isoformat(), "next_due_txt": dmy(due), "stale": stale, "stale_text": text}


def build_weekly(wdir, ky_req):
    warnings = []
    today = today_ict(warnings)
    issues = list_issues(wdir)
    if not issues:
        raise WeeklyError("NO_ISSUE", "Chưa có bản tuần nào trong %s (cần tệp hhp_weekly_YYYY-MM-DD.html). "
                                      "Lưu bản tuần HHP vào thư mục này hoặc đặt HHP_WEEKLY_DIR." % wdir)
    ky = ky_req or issues[0]
    if ky not in issues:
        raise WeeklyError("NO_ISSUE", "Không có bản tuần kỳ %s trong %s. Các kỳ hiện có: %s — chọn một kỳ trong "
                                      "danh sách." % (dmy(parse_iso(ky)), wdir, ", ".join(issues)))
    live = Live(env_dir("HHP_DATA_DIR", DEFAULT_DATA_DIR), warnings)
    p = read_issue(wdir, ky, today, live, warnings)
    ctx = p["ctx"]
    meta = {"generated": datetime.now(ICT).replace(microsecond=0).isoformat(), "script_version": SCRIPT_VERSION,
            "issue_dir": wdir, "issue_file": p["path"], "file_url": Path(os.path.abspath(p["path"])).as_uri(),
            "issues": issues, "ky": ky, "ky_txt": dmy(parse_iso(ky)), "rev": p["rev"],
            "data_as_of": p["data_as_of"].isoformat() if p["data_as_of"] else None,
            "data_as_of_txt": dmy(p["data_as_of"]), "engine_run": p["engine_run"]}
    meta.update(age_fields(ky, today, issues))
    meta.update({"live_as_of": live.as_of.isoformat() if live.as_of else None, "live_as_of_txt": live.as_of_txt,
                 "live_generated": live.generated, "links": p["links"], "warnings": warnings})
    advisors = [{k: a[k] for k in ("ticker", "subtitle", "verdict", "verdict_class")} for a in ctx.advisors]
    portfolio, p["portfolio_skipped"] = portfolio_of(p["page_text"], warnings)
    core = {"mine": p["mine"], "avoid": p["avoid"], "advisors": advisors, "portfolio": portfolio,
            "rigor": [entry for entry, _ok, _txt in p["rigor"]]}
    stats = p["header"]["stats"]
    drift = drift_rows(stats, live)
    tickers = ticker_rows(p["rows"], p["mine"], p["avoid"], ctx.advisors, live)
    levels = levels_of(ctx, live)
    past = past_of(ctx)
    engine = {"kiem": kiem_lines(p, meta, core, drift, tickers, levels, past, live), "drift": drift,
              "tickers": tickers, "baskets": basket_rows(ctx, live), "levels": levels, "past": past}
    issue = dict(p["header"], sections=p["sections"], footer=p["footer"])
    snapshot = {"rows": p["rows"], "n": len(p["rows"]), "as_of_txt": ctx.snap_as_of_txt,
                "live": snapshot_live(p["rows"], live), "live_as_of_txt": live.as_of_txt}
    return {"meta": meta, "issue": issue, "core": core, "snapshot": snapshot, "engine": engine,
            "csv": csv_of(p["rows"], p["mine"], p["avoid"], live)}


def build_brief(wdir):
    warnings = []
    today = today_ict(warnings)
    issues = list_issues(wdir)
    if not issues:
        return {"ky": None, "ky_txt": "—", "rev": None, "title": "", "issues": [], "age_days": None,
                "stale": False, "stale_text": "", "mine": [], "avoid": [], "advisors": [], "file": ""}
    ky = issues[0]
    p = read_issue(wdir, ky, today, None, warnings)
    age = age_fields(ky, today, issues)
    return {"ky": ky, "ky_txt": dmy(parse_iso(ky)), "rev": p["rev"], "title": p["header"]["title"].replace("\n", " "),
            "issues": issues, "age_days": age["age_days"], "stale": age["stale"], "stale_text": age["stale_text"],
            "mine": p["mine"], "avoid": p["avoid"],
            "advisors": [{k: a[k] for k in ("ticker", "verdict", "verdict_class")} for a in p["ctx"].advisors],
            "file": p["path"]}


def run(argv):
    args = list(argv[1:])
    if not args:
        raise WeeklyError("BAD_ARGS", "Thiếu lệnh. " + USAGE)
    cmd, rest = args[0], args[1:]
    wdir = env_dir("HHP_WEEKLY_DIR", DEFAULT_WEEKLY_DIR)
    if cmd == "issues" and not rest:
        return {"issues": list_issues(wdir), "issue_dir": wdir}
    if cmd == "brief" and not rest:
        return build_brief(wdir)
    if cmd == "weekly" and len(rest) <= 1:
        ky = rest[0] if rest else None
        if ky is not None and (not re.fullmatch(r"\d{4}-\d{2}-\d{2}", ky) or parse_iso(ky) is None):
            raise WeeklyError("BAD_ARGS", "Kỳ không hợp lệ: '%s' — dùng dạng YYYY-MM-DD, ví dụ 2026-09-14. %s"
                              % (ky, USAGE))
        return build_weekly(wdir, ky)
    raise WeeklyError("BAD_ARGS", "Lệnh không hợp lệ: '%s'. %s" % (" ".join(args), USAGE))


def emit(obj):
    text = json.dumps(clean(obj), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
    sys.stdout.flush()


def main(argv=None):
    argv = sys.argv if argv is None else argv
    try:
        out = run(argv)
    except WeeklyError as exc:
        out = {"error": exc.message, "error_code": exc.code}
    except Exception as exc:  # never let a traceback replace the JSON envelope
        out = {"error": "Lỗi nội bộ hhp_weekly.py: %s: %s — báo lại kèm tệp bản tuần đang mở"
                        % (type(exc).__name__, exc), "error_code": "INTERNAL"}
    emit(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
