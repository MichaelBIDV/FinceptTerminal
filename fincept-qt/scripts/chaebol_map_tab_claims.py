#!/usr/bin/env python3
"""
chaebol_map_tab_claims — tab `changelog` (09 · CLAIMS C01-C20 + CHANGELOG) và tab `claims54` (★ 11 · 54 CLAIMS PRIORITY).

Nguồn: SRC ~/Downloads/master_plan_v21_chaebol_vn30.html dòng 6672–6710 (ResearchStackPanel — render ĐẦU tab 09),
6713–6827 (Claims54Tab), 7029–7067 (ClaimsPanel), 7069–7245 (ChangelogTab); hằng CLAIMS_C01_C20 (546–796),
CLAIMS_54 (799–1340), RESEARCH_STACK (3327–3503) lấy từ ctx.v21. Đặc tả: chaebol_map_spec/page_p6 §5, page_p7b §5,
page_p7a §2. Style chép đúng thứ tự khoá JSX; màu as_intended (C.emerald/C.crimson/C.bg2 có giá trị, DESIGN §0.1).

Mode v21: nguyên văn trang gốc ("hôm nay" của tab 11 = 12/05/2026 như Claims54Tab.today).
Mode live: cùng cây + (a) chấm lại 20 + 54 claim từ dossier (khoá claims20 / claims54, mảnh
knowledge_os/chaebol_map/cap_nhat_2026-09-27.claims.json) — trạng thái mới cạnh trạng thái V21 (dấu V21·12/05);
(b) tab 11 tính lại cửa sổ ≤60 ngày / PAST theo ctx.today; (c) mục changelog mới "V21 → Fincept" (khoá changelog);
(d) khối chữ V21 có chữ số mang nhãn U (bản lưu chưa kiểm lại), số dẫn xuất (đếm, số ngày) mang nhãn E;
(e) bằng chứng dossier trộn nhiều bậc ghi nhãn nội dòng "{T2·yyyy-mm-dd}" / "{E}" ngay sau con số (xem _rich);
(f) claim tab 09 có mã chủ thể (tk[0]) ngoài 30 mã Toàn Vũ: "Pattern X" trong chữ V21 thành "Pattern X?" + chú thích.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from chaebol_map_dom import (
    C, F_DISPLAY, F_MONO, F_SERIF, can_data, h, is_live, status_pill, tier, upd_mark, v21_mark,
)
from chaebol_map_shell import Card, Pill, Section

V21_TODAY = date(2026, 5, 12)            # Claims54Tab.today = new Date('2026-05-12')
HORIZON_ANCHOR = date(2026, 5, 11)       # neo horizon CLAIMS_C01_C20 (C01: "trong 30d kể từ 11/5/2026")
URGENT_DAYS = 60                         # Claims54Tab: urgent = 0 ≤ days ≤ 60
_DIGIT = re.compile(r"\d")
# Chữ dossier: "[CẦN DATA — …]" → can_data(); "{T2·2026-05-07}" / "{E}" → nhãn bậc nội dòng (mỗi số một nhãn).
_RICH_RE = re.compile(r"\[CẦN DATA(?: — ([^\]]*))?\]|\{(T1|T2|T3|E|U)(?:·(\d{4}-\d{2}-\d{2}))?\}")
_STATUSES = ("ĐẠT", "BỊ BÁC", "CHƯA RÕ", "LIVE", "HẾT HẠN", "TIỀN ĐỀ SAI")
_ZWSP = "\u200b"                        # zero-width space (điểm ngắt dòng, không vẽ)
_SRC_BREAK = re.compile(r"/(?=[^\d\s/])")   # điểm ngắt sau '/' của đường dẫn (không chẻ ngày dd/mm/yyyy)
_PAT_RE = re.compile(r"\bPattern ([A-D])\b(?!\?)")

# ResearchStackPanel.catColor (SRC 6676) — as_intended: Research = C.emerald, Perplexity = C.crimson.
_CAT_COLOR = {"Research": C.emerald, "Memory": C.gold, "Parsing": "#a78bfa", "Skills": "#60a5fa",
              "Browser": "#fb923c", "Workflow": C.forest, "Perplexity": C.crimson, "Financial": C.gold,
              "Code-Research": C.ink2}
_PRI_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}      # Claims54Tab.order (SRC 6727)


def cat_color(c):
    return _CAT_COLOR.get(c) or C.ink2


def status_color(s):
    """ClaimsPanel.statusColor (SRC 7032) — không có fallback `||`."""
    return C.emerald if s == "LIVE" else C.gold if s == "WATCH" else C.crimson if s == "FAILED" else C.ink2


def pri_color(p):
    """Claims54Tab.priColor (SRC 6722): 'ALL' và LOW rơi về C.ink2."""
    return C.crimson if p == "CRITICAL" else C.gold if p == "HIGH" else C.emerald if p == "MEDIUM" else C.ink2


def _need(v21, name):
    val = (v21 or {}).get(name)
    if not val:
        raise ValueError("v21_const thiếu %s — cần trích lại v21_const.json" % name)
    return val


def _uniq(seq):
    out = []
    for x in seq:
        if x not in out:
            out.append(x)
    return out


def _u(text):
    """Nhãn U sau khối chữ V21 có chữ số (live): bản lưu 12/05, chưa kiểm lại (DESIGN §0.6)."""
    return tier("U") if is_live() and _DIGIT.search(str(text)) else None


def _dmy(d):
    return "%02d/%02d/%d" % (d.day, d.month, d.year)


def _rich(text):
    """Chữ dossier → list con: "[CẦN DATA — …]" thành can_data() (vermillion đậm, được đếm); "{T2·yyyy-mm-dd}",
    "{E}"… thành nhãn bậc nội dòng ngay sau con số nó gắn (khối trộn nhiều bậc)."""
    text = text or ""
    out, pos = [], 0
    for m in _RICH_RE.finditer(text):
        node = tier(m.group(2), m.group(3)) if m.group(2) else can_data(m.group(1))
        out += [text[pos:m.start()], node]
        pos = m.end()
    return out + [text[pos:]]


def _ends_with_tier(parts):
    """Chữ dossier kết thúc bằng nhãn nội dòng → không gắn thêm nhãn khối (tránh hai nhãn liền nhau)."""
    for p in reversed(parts):
        if isinstance(p, str):
            if p.strip(" .;"):
                return False
            continue
        return isinstance(p, dict) and "_tier" in p
    return False


def _src_text(src):
    """Chuỗi nguồn: chèn điểm ngắt rộng 0 sau '/' của đường dẫn, thay cho wordBreak break-all (chẻ giữa từ/ngày)."""
    return _SRC_BREAK.sub("/" + _ZWSP, str(src or ""))


def tv30_set(ctx):
    """Live: 30 mã Toàn Vũ (ctx.data.tv30). Không có lớp dữ liệu hay danh sách → rỗng, tức mọi mã coi như ngoài
    (hướng an toàn, như tab overview/codong)."""
    data = getattr(ctx, "data", None)
    return set(data.tv30() or []) if ctx.live and data is not None else set()


def pattern_q(text, tk, tv):
    """Live: mã chủ thể `tk` ngoài 30 mã Toàn Vũ → 'Pattern X' thành 'Pattern X?' (CLAUDE.md §6 luật 4, DESIGN §8.4).
    Mode v21 trả nguyên văn."""
    if not is_live() or not tk or tk in tv:
        return text
    return _PAT_RE.sub(r"Pattern \1?", text)


def _dossier_part(ctx, key):
    doc = getattr(ctx, "dossier", None) or {}
    part = doc.get(key)
    return part if isinstance(part, dict) else {}


def _pill(status):
    s = str(status or "").strip().upper()
    return Pill(s, C.ink2) if s == "TIỀN ĐỀ SAI" else status_pill(s)


# ── Khối chấm lại (chỉ live) ────────────────────────────────────────────────


def rescore_block(item, today, window=None, expired=False):
    """"CHẤM LẠI 27/09" cuối thẻ claim (live). item = mục dossier {status, evidence, tier, asof, src} | None.
    window = chữ hạn (số ngày/ngày hết horizon — dẫn xuất → nhãn E)."""
    if not is_live():
        return None
    # Chữ nhỏ 8–9px của khối live dùng C.inkD (tương phản ≈6:1 trên nền thẻ) thay C.inkM (≈2,5:1).
    head_st = {"display": "flex", "flexWrap": "wrap", "alignItems": "center", "gap": 6, "marginBottom": 5,
               "fontFamily": F_MONO, "fontSize": 9, "letterSpacing": ".1em", "color": C.inkD}
    box_st = {"marginTop": 10, "paddingTop": 8, "borderTop": "1px dashed " + C.rule}
    win = h("span", None, window, tier("E")) if window else None
    label = "CHẤM LẠI %02d/%02d" % (today.day, today.month)
    if not item:
        return h("div", box_st, h("div", head_st, label, can_data("chưa có mục dossier chấm lại"), win))
    status = str(item.get("status") or "").upper()
    pills = [_pill(status)]
    if expired and status not in ("HẾT HẠN", "ĐẠT", "BỊ BÁC", "TIỀN ĐỀ SAI"):
        pills.append(status_pill("HẾT HẠN"))
    body = _rich(item.get("evidence"))
    block_tier = None if _ends_with_tier(body) else tier(item.get("tier") or "U", item.get("asof"))
    return h("div", box_st,
             h("div", head_st, label, *pills, win),
             h("div", {"fontSize": 11, "color": C.ink, "lineHeight": 1.55, "fontFamily": F_SERIF},
               *body, block_tier, upd_mark(today)),
             h("div", {"fontSize": 8, "color": C.inkD, "fontFamily": F_MONO, "marginTop": 4, "letterSpacing": ".05em"},
               "nguồn: ", _src_text(item.get("src"))))


def summary_line(items, ids, label, today, key):
    """Dòng tổng chấm lại (live): đếm trạng thái mới — số dẫn xuất → nhãn E."""
    if not is_live():
        return None
    cnt = {k: 0 for k in _STATUSES}
    missing = 0
    for i in ids:
        s = str((items.get(i) or {}).get("status") or "").upper()
        if s in cnt:
            cnt[s] += 1
        else:
            missing += 1
    parts = []
    for k in _STATUSES:
        if cnt[k]:
            parts += [" · " if parts else "", _pill(k), " %d" % cnt[k]]
    # Câu cuối + dấu ↻ chung MỘT span: trong hộp flex, dấu đứng riêng là một flex item và rơi mồ côi xuống dòng.
    tail = h("span", None, _SUMMARY_TAIL, upd_mark(today))
    return h("div", {"display": "flex", "flexWrap": "wrap", "alignItems": "center", "gap": 4, "marginBottom": 14,
                     "padding": "8px 12px", "background": C.parch, "borderLeft": "3px solid " + C.ochre,
                     "fontFamily": F_MONO, "fontSize": 9, "letterSpacing": ".08em", "color": C.inkD, "lineHeight": 1.6},
             label, *parts, tier("E"),
             can_data("%d claim chưa có mục dossier" % missing) if missing else None,
             tail, key=key)


_SUMMARY_TAIL = (" — trạng thái V21 giữ ở đầu thẻ (V21·12/05); CỔNG v1.7 DỪNG nên không chấm lại pha/stance/khuyến "
                 "nghị; vị thế V21 >5% NAV → Synthesis L1+L2+L3 trước mọi action cần kiểm chứng.")


# ── Tab 09 · ResearchStackPanel (SRC 6672–6710) ─────────────────────────────


def _rs_card(t, live):
    col = cat_color(t["cat"])
    return Card(
        h("div", {"display": "flex", "justifyContent": "space-between", "alignItems": "baseline", "marginBottom": 5},
          h("div", {"fontSize": 12, "fontWeight": 700, "color": C.ink, "fontFamily": F_DISPLAY}, t["name"]),
          h("div", {"fontSize": 8, "color": col, "letterSpacing": ".15em", "fontFamily": F_MONO, "fontWeight": 600},
            t["cat"], tier("U") if live else None)),
        h("div", {"fontSize": 9, "color": C.ink2, "fontFamily": F_MONO, "marginBottom": 6, "letterSpacing": ".05em"},
          "github.com/" + t["url"]),
        h("div", {"fontSize": 11, "color": C.inkD, "lineHeight": 1.5, "marginBottom": 6, "fontFamily": F_SERIF},
          h("strong", {"color": col}, "Cap:"), " " + t["cap"]),
        h("div", {"fontSize": 11, "color": C.ink, "lineHeight": 1.5, "fontFamily": F_SERIF, "padding": "5px 8px",
                  "background": col + "15", "borderLeft": "2px solid " + col},
          h("strong", None, "VN Use:"), " " + t["use"]),
        accent=col, if_={"rs.cat": ["ALL", t["cat"]]}, grp="rs.cards", key="rs:" + t["name"])


def research_stack(ctx):
    stack = _need(ctx.v21, "RESEARCH_STACK")
    cats = ["ALL"] + _uniq(t["cat"] for t in stack)
    buttons = []
    for c in cats:
        col = cat_color(c)
        n = sum(1 for t in stack if t["cat"] == c)
        buttons.append(h("button", {"padding": "4px 10px", "background": "transparent", "color": C.ink,
                                    "border": "1px solid " + col, "cursor": "pointer", "fontWeight": 600},
                         c, " ", ("· %d" % n) if c != "ALL" else None,        # `{c} {c!=='ALL' && '· '+n}` → "ALL "
                         on={"set": {"rs.cat": c}},
                         var=[{"if": {"rs.cat": c}, "s": {"background": col, "color": "#0a0a0c"}}],
                         key="rs.btn:" + c))
    code_st = {"fontFamily": F_MONO, "fontSize": 10, "background": C.bg2, "padding": "1px 5px"}
    foot = h("div", {"marginTop": 14, "padding": "10px 14px", "background": C.gold + "14",
                     "border": "1px solid " + C.gold + "40", "borderRadius": 2, "fontSize": 11, "fontFamily": F_SERIF,
                     "color": C.ink, "lineHeight": 1.6},
             h("strong", {"color": C.gold}, "★★★ HIGHEST PRIORITY:"), " Install Anthropic OFFICIAL ",
             h("code", code_st, "anthropics/financial-services"),
             " — Pitch · Earnings Reviewer · Model Builder · Cowork API. ", h("strong", None, "Apply"), ": ",
             h("code", None, "/comps Big4 · /dcf GAS · /initiate ACB · /earnings TCB Q1/26"), ". Cmd: ",
             h("code", None, "/plugin marketplace add anthropics/financial-services"), v21_mark())
    sub = ("V21.29 · Map to 5 pillars Toàn Vũ + ARA Rigor 6D · MD export: "
           "Reports/research-stack/VN_EQUITY_RESEARCH_STACK_v1.md")
    node = Section(
        "🔬 VN EQUITY RESEARCH STACK · 25 tools cloned 12/05/2026",
        h("div", {"display": "flex", "flexWrap": "wrap", "gap": 6, "marginBottom": 14, "fontFamily": F_MONO,
                  "fontSize": 9, "letterSpacing": ".1em"},
          *buttons,
          h("div", {"marginLeft": "auto", "color": C.ink2, "alignSelf": "center"},
            count={"grp": "rs.cards", "fmt": "Showing {n}/%d" % len(stack)})),
        h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 10},
          *[_rs_card(t, ctx.live) for t in stack]),
        foot,
        accent=C.gold, sub=[sub, v21_mark()] if ctx.live else sub, key="rs")
    return node, {"key": "rs.cat", "default": "ALL", "options": cats}


# ── Tab 09 · ClaimsPanel (SRC 7029–7067) ────────────────────────────────────


def horizon_end(horizon, anchor=HORIZON_ANCHOR):
    """'30-60 ngày' → anchor + 60 ngày (cận trên); '90 ngày' → anchor + 90. Không đọc được → None (EST)."""
    nums = [int(x) for x in re.findall(r"\d+", str(horizon or ""))]
    return anchor + timedelta(days=max(nums)) if nums else None


def _claim_card(c, ctx, d20, tv=frozenset()):
    col = status_color(c["status"])
    rescore = None
    if ctx.live:
        end = horizon_end(c.get("horizon"))
        expired = bool(end and ctx.today > end)
        win = ("hết horizon %s%s" % (_dmy(end), " (đã qua)" if expired else "")) if end else None
        rescore = rescore_block(d20.get(c["id"]), ctx.today, win, expired)
    # Pattern trong chữ claim gắn với mã chủ thể tk[0] (C18 "MSN Pattern B" có tk MSN, MSR → theo MSN).
    subject = (c.get("tk") or [None])[0]
    raw = {k: c[k] for k in ("title", "prediction", "falsifyIf", "evidence")}
    c = dict(c, **{k: pattern_q(v, subject, tv) for k, v in raw.items()})
    q_note = None
    if any(c[k] != v for k, v in raw.items()):
        why = ("%s ngoài 30 mã Toàn Vũ" % subject) if tv else "chưa đọc được danh sách 30 mã Toàn Vũ"
        q_note = h("span", {"color": C.inkD, "marginLeft": 6}, "· '?' = %s, nhãn pattern là giả thuyết" % why)
    return Card(
        h("div", {"display": "flex", "justifyContent": "space-between", "alignItems": "baseline", "marginBottom": 6},
          h("div", {"fontFamily": F_MONO, "fontSize": 11, "color": C.gold, "fontWeight": 700, "letterSpacing": ".1em"},
            c["id"]),
          h("div", {"fontFamily": F_MONO, "fontSize": 9, "color": col, "letterSpacing": ".15em", "fontWeight": 600},
            c["status"] + " · " + c["horizon"], v21_mark())),
        h("div", {"fontSize": 13, "fontWeight": 600, "color": C.ink, "marginBottom": 6, "fontFamily": F_DISPLAY},
          c["title"], _u(c["title"])),
        h("div", {"fontSize": 9, "color": C.ink2, "fontFamily": F_MONO, "marginBottom": 8, "letterSpacing": ".1em"},
          "TK: " + " · ".join(c["tk"]), q_note),
        h("div", {"fontSize": 11, "color": C.inkD, "lineHeight": 1.6, "marginBottom": 8, "fontFamily": F_SERIF},
          h("strong", {"color": C.emerald}, "▶ Prediction:"), " " + c["prediction"], _u(c["prediction"])),
        h("div", {"fontSize": 11, "color": C.inkD, "lineHeight": 1.6, "marginBottom": 8, "fontFamily": F_SERIF,
                  "padding": "6px 10px", "background": C.crimson + "12", "borderLeft": "2px solid " + C.crimson},
          h("strong", {"color": C.crimson}, "✗ Falsified if:"), " " + c["falsifyIf"], _u(c["falsifyIf"])),
        h("div", {"fontSize": 10, "color": C.ink2, "lineHeight": 1.5, "fontFamily": F_MONO, "fontStyle": "italic"},
          h("strong", None, "Evidence:"), " " + c["evidence"], _u(c["evidence"])),
        rescore,
        accent=col, if_={"cp.filter": ["ALL", c["status"]]}, grp="cp.cards", key="cp:" + c["id"])


def claims_panel(ctx):
    claims = _need(ctx.v21, "CLAIMS_C01_C20")
    filters = ["ALL", "LIVE", "WATCH", "FAILED"]            # ClaimsPanel.jsx@L7036
    d20 = _dossier_part(ctx, "claims20") if ctx.live else {}
    tv = tv30_set(ctx)
    buttons = [h("button", {"padding": "5px 12px", "background": "transparent", "color": C.ink,
                            "border": "1px solid " + C.ink2, "cursor": "pointer", "fontWeight": 600}, s,
                 on={"set": {"cp.filter": s}},
                 var=[{"if": {"cp.filter": s}, "s": {"background": C.gold, "color": "#0a0a0c"}}],
                 key="cp.btn:" + s) for s in filters]
    sub = "V21.29 · Master report Allinone v2 (1163 lines synthesized) · Updated 12/05/2026"
    node = Section(
        "20 FALSIFIABLE CLAIMS · C01-C20 (Popper + Munger inversion)",
        h("div", {"display": "flex", "gap": 8, "marginBottom": 14, "fontFamily": F_MONO, "fontSize": 10,
                  "letterSpacing": ".15em"},
          *buttons,
          h("div", {"marginLeft": "auto", "color": C.ink2, "alignSelf": "center"},
            count={"grp": "cp.cards", "fmt": "Showing {n}/%d" % len(claims)})),
        summary_line(d20, [c["id"] for c in claims],
                     "CHẤM LẠI %s · 20 claim (neo horizon %s): " % (_dmy(ctx.today), _dmy(HORIZON_ANCHOR)),
                     ctx.today, "cp.summary"),
        h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 12},
          *[_claim_card(c, ctx, d20, tv) for c in claims]),
        accent=C.gold, sub=[sub, v21_mark()] if ctx.live else sub, key="cp")
    return node, {"key": "cp.filter", "default": "ALL", "options": filters}


# ── Tab 09 · Changelog (SRC 7074–7243) ──────────────────────────────────────

_H_LABEL = {"fontSize": 10, "letterSpacing": ".18em", "fontFamily": F_MONO, "fontWeight": 600}


def _hist_sub(ctx, text=None):
    """Sub Section cho khối lịch sử V21 ở live: bản lưu + nhãn U (khối chung một nguồn, DESIGN §6.3)."""
    if not ctx.live:
        return text
    return [text, v21_mark(), tier("U")] if text else [v21_mark(), tier("U")]


def changelog_v21(ctx):
    def st(color):
        return {"fontSize": 10, "letterSpacing": ".18em", "color": color, "fontFamily": F_MONO, "marginBottom": 10,
                "fontWeight": 600}

    def ul(color):
        return {"margin": 0, "paddingLeft": 16, "fontSize": 11, "fontFamily": F_SERIF, "color": color, "lineHeight": 1.8}
    v20 = ("Deep-dive VCB · FPT · MSN với MSN-style 9-tab cấu trúc", "Cluster VWAP + Pattern B/A flow analysis",
           "Capital IQ ownership (S&P Global) + AGM tracker", "Order flow + insider transactions feed",
           "Howard Marks 6-phase framework cho từng mã", "Action plan + methodology footnotes")
    v21 = (("Chaebol Map 4 nhóm:", " Tuấn mượt · Sovico · Bà Phượng · ⛔ Eliminated (DGC/PC1/CTD)"),
           ("VN30+ Screener matrix", " 45 mã sortable với phase × flow × chaebol"),
           ("Portfolio Action + Rotation Roadmap", " 90 ngày chia 3 phase Trim/Build/Consolidate"),
           ("Power Map SVG", " 4 quadrants ascending/stable/expanding/eliminated"),
           ("11-event Timeline", " highlight 30/3 (VCI insider) · 1/4 (Tuấn AGM) · 8/5 (DGC ĐHĐCĐ thay BOD HÔM NAY)"))
    return Section(
        "V21 Changelog — Cấu Trúc Mới So Với V20",
        h("div", {"fontSize": 13, "fontFamily": F_SERIF, "color": C.inkD, "lineHeight": 1.8, "fontStyle": "italic",
                  "marginBottom": 18, "padding": "14px 18px", "background": C.parch, "borderLeft": "3px solid " + C.gold},
          "V20 tập trung vào 3 mã danh mục (VCB/FPT/MSN) với độ sâu phân tích MSN-tab style. V21 mở rộng theo "
          "chiều ngang phủ ", h("strong", {"color": C.ink}, "4 nhóm chaebol thân hữu chính trị"), " + ",
          h("strong", {"color": C.ink}, "30+ mã VN30"),
          " ở dạng matrix screener. Hai bản chạy song song: V20 cho deep-dive 3 mã, V21 cho big picture chính "
          "trị/dòng tiền/rotation."),
        h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 14, "marginBottom": 18},
          Card(h("div", st(C.ink2), "◇ V20 (RETAINED)"),
               h("ul", ul(C.inkD), *[h("li", None, x) for x in v20]), accent=C.ink2),
          Card(h("div", st(C.gold), "★ V21 (NEW)"),
               h("ul", ul(C.ink), *[h("li", None, h("strong", None, a), b) for a, b in v21],
                 h("li", None, "Dark editorial finance theme (#0a0a0c canvas + Cormorant/JetBrains/IBM Plex "
                               "typography)")), accent=C.gold)),
        h("div", {"padding": "14px 18px", "background": C.forest + "12", "border": "1px solid " + C.forest + "40",
                  "borderRadius": 2},
          h("div", {"fontSize": 10, "letterSpacing": ".2em", "color": C.forest, "fontFamily": F_MONO,
                    "marginBottom": 10, "fontWeight": 600}, "★ THESIS NEW IN V21"),
          h("div", {"fontSize": 12, "fontFamily": F_SERIF, "color": C.ink, "lineHeight": 1.85},
            "Vietnam thị trường có 2 lớp alpha: ", h("strong", None, "(a) Lớp doanh nghiệp"),
            " — fundamentals, dòng tiền, định giá, mà sell-side và quants có thể model; và ",
            h("strong", None, "(b) Lớp chính trị/thân hữu"),
            " — chaebol nào đang ascending vs descending vs eliminated.",
            h("strong", {"color": C.gold}, " Lớp B chỉ đọc được qua tin nội bộ, AGM, ownership change, và pattern "
                                           "— không có model nào capture được"),
            ". V21 là attempt đầu tiên hệ thống hóa lớp B này dựa trên dòng tiền Pillar IV (FiinTrade institutional "
            "flow verified ≤08/05/2026 historical + NgườiQuanSát.vn forward từ 09/05/2026) làm proxy độc lập, không "
            "phụ thuộc vào sell-side narrative.")),
        accent=C.gold, sub=_hist_sub(ctx, "Build 08/05/2026"), key="cl")


_METH_ROWS = (
    ("Howard Marks", "6 phase áp dụng cho từng mã 1-by-1 (VCB/FPT/MSN)",
     "Apply trên toàn 45 mã, hiển thị matrix dạng phase distribution + screener filter"),
    ("Pillar IV (FiinTrade ≤08/05 · NgườiQuanSát ≥09/05)", "Aggregate 60d cho 3 mã danh mục",
     "Aggregate 60d cho toàn bộ 45 mã + auto-classify BULL/BEAR/MIX signal heuristic"),
    ("Munger Inversion", "Inversion check trong action plan từng mã",
     "Avoid List explicit ở Portfolio Tab + Eliminated tab tách riêng (DGC/PC1/CTD)"),
    ("Chaebol Lens", 'Khái niệm sơ khởi qua "NQ79 SOE" trong VCB analysis', None),
    ("Cluster VWAP", "Pattern B/A multi-VWAP 6M/3M/1M cho 3 mã", None),
    ("RRG Optuma", "Tham chiếu lý thuyết trong methodology",
     "Áp dụng phase matrix trên Screener: P2 = Improving quadrant; P3 = Leading→Weakening; CAP = Lagging"),
)


def methodology(ctx):
    th = {"textAlign": "left", "padding": "10px 8px", "fontSize": 9, "letterSpacing": ".18em", "color": C.inkM,
          "fontFamily": F_MONO, "fontWeight": 500}
    rows = []
    for i, (fw, v20, v21) in enumerate(_METH_ROWS):
        if fw == "Chaebol Lens":
            c3 = h("td", {"padding": "10px 8px"}, h("strong", {"color": C.gold}, "NEW."),
                   " Power map 4 quadrants + group deep-dive (Tuấn/Sovico/Phượng/Eliminated). Coverage 4 nhóm × 9 mã "
                   "chính.")
        elif fw == "Cluster VWAP":
            c3 = h("td", {"padding": "10px 8px", "color": C.inkM, "fontStyle": "italic"},
                   "Inherit từ V20, không update — vẫn dùng cho deep-dive khi cần")
        else:
            c3 = h("td", {"padding": "10px 8px"}, v21)
        last = i == len(_METH_ROWS) - 1
        rows.append(h("tr", None if last else {"borderBottom": "1px solid " + C.rule},
                      h("td", {"padding": "10px 8px", "fontWeight": 600, "color": C.gold, "fontFamily": F_MONO,
                               "fontSize": 10}, fw),
                      h("td", {"padding": "10px 8px", "color": C.inkD}, v20), c3))
    return Section(
        "Methodology Updates",
        Card(h("table", {"width": "100%", "fontSize": 11, "fontFamily": F_SERIF, "borderCollapse": "collapse"},
               h("thead", None, h("tr", {"borderBottom": "2px solid " + C.rule},
                                  h("th", {**th, "width": "18%"}, "FRAMEWORK"),
                                  h("th", {**th, "width": "40%"}, "V20 (BASELINE)"),
                                  h("th", {**th, "width": "42%"}, "V21 (UPDATED)"))),
               h("tbody", {"lineHeight": 1.65, "color": C.ink}, *rows))),
        accent=C.ink2, sub=_hist_sub(ctx), key="meth")


def _src_block(title, *body):
    return h("div", None,
             h("div", {"fontSize": 11, "fontFamily": F_MONO, "color": C.gold, "letterSpacing": ".1em", "marginBottom": 8,
                       "fontWeight": 600}, title),
             h("div", {"fontSize": 10, "color": C.inkD, "fontFamily": F_MONO, "lineHeight": 1.7}, *body))


def data_sources(ctx):
    code = {"background": C.parch, "padding": "1px 5px", "fontSize": 9}
    ink = {"color": C.ink}
    br = lambda: h("br")  # noqa: E731
    live_flow = None
    if ctx.live:
        live_flow = [br(), h("span", {"color": C.ochre},
                             "Từ 09/05 NgườiQuanSát chưa từng chạy; dòng tiền sống = vc_lk: NN (khớp + thoả thuận) "
                             "và tự doanh (khớp)"), tier("T2", ctx.live_info.get("data_to") if ctx.live_info else None),
                     h("span", {"color": C.ochre}, "; Cá nhân/Tổ chức "), can_data(), upd_mark(ctx.today)]
    flow = _src_block(
        "FLOW DATA · 45 mã",
        "• ", h("strong", ink, "FiinTrade Phân Loại Nhà Đầu Tư"), " (verified through 08/05/2026, paid-for, KEPT)", br(),
        "Path: ", h("code", code, "/mnt/project/FiinTrade_*_20260508.xlsx"), br(),
        "• ", h("strong", ink, "NgườiQuanSát.vn Phân Loại NĐT"), " (FREE, used from 09/05/2026 onwards)", br(),
        "URL: ", h("code", code, "dulieu.nguoiquansat.vn/du-lieu-giao-dich/khop-lenh-ndt-nn/{TK}"),
        " · XHR: /History/PhanLoaiNDTHistory", br(),
        "Coverage: 60 phiên gần nhất · Cá nhân/Tổ chức/Tự doanh/Nước ngoài", br(),
        "Last updated: 08/05/2026", live_flow)
    fund = ("• cafef.vn (DGC arrest 5/5; VCI 30/3 AGM)", "• tinnhanhchungkhoan.vn (GEX AGM 1/4)",
            "• thanhnien.vn (VJC AGM 27/4)", "• mekongasean.vn (Sovico ownership)", "• dnse.com.vn (Bà Thảo cổ phần)",
            "• Capital IQ S&P Global · MSN ownership 4/2026")
    meth = ('• Howard Marks · "Mastering the Market Cycle"', "• Charlie Munger · Latticework / Inversion mental model",
            "• Lawrence Cunningham · Quality Investing", "• Chuck Akre · Three-Legged Stool framework",
            "• Optuma RRG (Relative Rotation Graphs)", "• TD Sequencer / Wyckoff Phase Analysis")

    def lines(xs):
        out = []
        for i, x in enumerate(xs):
            out += [br()] if i else []
            out.append(x)
        return out

    contrarian = (" nếu sell-side đồng loạt BUY mà NN/Tổ chức rút mạnh → flip BEAR. Áp dụng cho FPT (sell-side BUY mà "
                  "NN -173.7M) và DGC (vài broker còn TP cao bất chấp pháp lý).")
    # Live: bỏ họ tên + chức vụ + đơn vị người nhận (thông tin cá nhân); mode v21 giữ nguyên văn để so ảnh.
    who = "người dùng nội bộ" if ctx.live else "Phạm Minh Tuấn (PCVP BIDV)"
    disclaimer = ("Báo cáo này dành riêng cho " + who + ". Tất cả số liệu đều được trích nguồn cụ thể. "
                  "Số liệu dự phóng (như target VCI 32-35K, GEX 40-45K) được ghi rõ là dự phóng dựa trên multiple "
                  "expansion + earnings growth giả định, không phải số liệu xác thực. Quan điểm chính trị/chaebol mapping "
                  "dựa trên thông tin công khai (bài báo + báo cáo công bố thông tin SSC + AGM) — không phải claim dạng "
                  "leak/insider information. Nội dung không thay thế khuyến nghị đầu tư chuyên nghiệp. ")
    return Section(
        "Data Sources & Citations",
        Card(h("div", {"fontSize": 10, "letterSpacing": ".18em", "color": C.inkM, "fontFamily": F_MONO,
                       "marginBottom": 14, "fontWeight": 600}, "◇ NGUỒN DỮ LIỆU CHÍNH (verified)"),
             h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 18},
               flow,
               _src_block("FUNDAMENTAL · AGM · Insider", *lines(fund)),
               _src_block("METHODOLOGY REFERENCES", *lines(meth)),
               _src_block("SELL-SIDE COVERAGE (CONTRARIAN CHECK)", "• HSC · SSI · BSC · VCSC · MAS ", br(),
                          "Use: lấy data points/EBITDA/EPS forecast", br(),
                          h("strong", {"color": C.vermillion}, "Contrarian rule:"), contrarian, _u(contrarian),
                          v21_mark()))),
        h("div", {"marginTop": 14, "padding": "12px 16px", "background": C.vermillion + "10",
                  "borderLeft": "3px solid " + C.vermillion, "fontSize": 11, "fontFamily": F_SERIF, "color": C.ink,
                  "lineHeight": 1.7, "fontStyle": "italic"},
          h("strong", {"color": C.vermillion, "fontFamily": F_MONO, "fontSize": 9, "letterSpacing": ".18em",
                       "fontStyle": "normal"}, "DISCLAIMER · "),
          disclaimer, _u(disclaimer), h("strong", None, "Quyết định cuối cùng là của anh.")),
        accent=C.inkD, sub=_hist_sub(ctx), key="src")


def roadmap(ctx):
    body = {"fontSize": 11, "fontFamily": F_SERIF, "color": C.ink, "lineHeight": 1.75}

    def card(accent, title, *kids):
        return Card(h("div", {"fontSize": 10, "letterSpacing": ".18em", "color": accent, "fontFamily": F_MONO,
                              "marginBottom": 8, "fontWeight": 600}, title), h("div", body, *kids), accent=accent)

    return Section(
        "Roadmap V22+ — Hướng Phát Triển",
        h("div", {"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": 12},
          card(C.forest, "V22 · DEEP-DIVE EXPANSION", "Mở rộng độ sâu MSN-style cho từng mã trong chaebol map: ",
               h("strong", None, "GEX, HPG, BSR, VCI"),
               ". Mỗi mã có 9-tab đầy đủ Cluster VWAP, Capital IQ, Order Flow, Events, Patterns, Action."),
          card(C.gold, "V23 · SECTOR ROTATION RRG",
               "Thêm RRG quadrant chart (Improving/Leading/Weakening/Lagging) cho 12 ngành chính + heatmap luân chuyển "
               "dòng tiền hàng tuần. Tích hợp với Gann/TD Sequencer cho timing."),
          card(C.ink2, "V24 · MACRO BACKDROP",
               "Macro tab: USD/VND, lãi suất 10y VGB, M2 growth, FDI, GDP per quarter. Tích hợp với chaebol thesis — "
               "chaebol nào hưởng lợi/thiệt từ chu kỳ macro hiện tại.")),
        accent=C.forest, sub=_hist_sub(ctx), key="road")


def fincept_entry(ctx):
    """Live: mục changelog mới đầu tiên "V21 → Fincept 27/09/2026" (dossier.changelog.fincept_2709)."""
    if not ctx.live:
        return None
    entry = (_dossier_part(ctx, "changelog").get("fincept_2709") or {})
    groups = entry.get("groups") if isinstance(entry.get("groups"), list) else []
    blocks = []
    for g in groups:
        items = [it for it in (g.get("items") or []) if isinstance(it, dict)]
        lis = [h("li", {"marginBottom": 4}, *_rich(it.get("text")), tier(it.get("tier") or "U", it.get("asof")),
                 h("span", {"fontFamily": F_MONO, "fontSize": 8, "color": C.inkD, "marginLeft": 6},
                   "nguồn: " + _src_text(it.get("src"))))
               for it in items]
        blocks.append(Card(h("div", {**_H_LABEL, "color": C.ochre, "marginBottom": 10}, g.get("title") or ""),
                           h("ul", {"margin": 0, "paddingLeft": 16, "fontSize": 11, "fontFamily": F_SERIF,
                                    "color": C.ink, "lineHeight": 1.7}, *lis), accent=C.ochre))
    if not blocks:
        blocks = [Card(can_data("chưa có dossier.changelog.fincept_2709 (mảnh cap_nhat_2026-09-27.claims.json)"))]
    data_to = (ctx.live_info or {}).get("data_to")
    try:
        data_to = _dmy(date.fromisoformat(str(data_to)[:10]))
    except ValueError:
        data_to = None
    sub = ["Build %s · dữ liệu tới " % _dmy(ctx.today), data_to or can_data(), upd_mark(ctx.today)]
    return Section("V21 → Fincept %s — Nguồn dữ liệu & dữ kiện mới" % _dmy(ctx.today),
                   h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 14}, *blocks),
                   accent=C.ochre, sub=sub, key="cl.fincept")


def build_changelog(ctx):
    rs, rs_state = research_stack(ctx)
    cp, cp_state = claims_panel(ctx)
    root = h("div", None, rs, cp, fincept_entry(ctx), changelog_v21(ctx), methodology(ctx), data_sources(ctx),
             roadmap(ctx), key="tab:changelog")
    return {"root": root, "states": [rs_state, cp_state]}


# ── Tab 11 · Claims54Tab (SRC 6713–6827) ────────────────────────────────────


def enrich54(claims, today):
    """enriched = {...c, days, urgent, past} (SRC 6716–6721): days = round((dl − today)/ngày)."""
    out = []
    for c in claims:
        days = (date.fromisoformat(c["dl"]) - today).days
        out.append(dict(c, days=days, urgent=0 <= days <= URGENT_DAYS, past=days < 0))
    return out


def sort54(enriched):
    """filtered.sort: theo order p rồi days tăng (sort ổn định V8 ⇔ sorted Python)."""
    return sorted(enriched, key=lambda c: (_PRI_ORDER[c["p"]], c["days"]))


def _stat54(accent, label, value, caption=None, value_color=None, live=False):
    return Card(
        h("div", {"fontSize": 10, "color": accent, "letterSpacing": ".2em", "fontFamily": F_MONO, "fontWeight": 600},
          label),
        h("div", {"fontSize": 28, "fontWeight": 700, "color": value_color or C.ink, "fontFamily": F_DISPLAY},
          value, tier("E") if live else None),
        h("div", {"fontSize": 10, "color": C.ink2, "marginTop": 4}, caption) if caption else None,
        accent=accent)


def _day_text(days):
    return (str(abs(days)) + "d PAST") if days < 0 else (str(days) + "d left")


def _th_caveat(c, item):
    """Thesis V21 nêu tên cá nhân trong bối cảnh pháp lý (dossier `th_caveat`): nhãn U + caveat, không thêm cáo buộc."""
    cav = (item or {}).get("th_caveat") if is_live() else None
    if not cav:
        return [_u(c["src"] + c["th"])]
    return [_u(c["src"] + c["th"]) or tier("U"),
            h("span", {"color": C.inkD, "fontStyle": "italic"}, " (" + str(cav) + ")")]


def _claim54_card(c, ctx, d54):
    live = ctx.live
    pc = pri_color(c["p"])
    dcol = C.crimson if c["days"] < 0 else C.gold if c["days"] <= 30 else C.ink2
    return Card(
        h("div", {"display": "flex", "justifyContent": "space-between", "alignItems": "baseline", "marginBottom": 5},
          h("div", {"fontFamily": F_MONO, "fontSize": 11, "color": pc, "fontWeight": 700, "letterSpacing": ".1em"},
            c["id"] + " · " + c["p"]),
          h("div", {"fontFamily": F_MONO, "fontSize": 9, "color": dcol, "fontWeight": 600},
            c["dl"] + " · " + _day_text(c["days"]), tier("E") if live else None)),
        h("div", {"fontSize": 10, "color": C.ink2, "fontFamily": F_MONO, "marginBottom": 6}, c["ch"]),
        h("div", {"fontSize": 12, "color": C.ink, "lineHeight": 1.5, "marginBottom": 6, "fontWeight": 500,
                  "fontFamily": F_SERIF}, c["claim"], _u(c["claim"])),
        h("div", {"fontSize": 10, "color": C.inkD, "lineHeight": 1.5, "padding": "5px 8px",
                  "background": C.crimson + "12", "borderLeft": "2px solid " + C.crimson, "marginBottom": 4,
                  "fontFamily": F_SERIF},
          h("strong", {"color": C.crimson}, "✗ Fail if:"), " " + c["fail"], _u(c["fail"])),
        h("div", {"fontSize": 10, "color": C.ink2, "lineHeight": 1.4, "fontFamily": F_MONO, "fontStyle": "italic"},
          h("strong", None, "Source:"), " " + c["src"] + " · ", h("strong", None, "Thesis:"), " " + c["th"],
          *_th_caveat(c, d54.get(c["id"])), v21_mark()),
        rescore_block(d54.get(c["id"]), ctx.today, None, c["past"]) if live else None,
        accent=pc, if_={"c54.pri": ["ALL", c["p"]], "c54.ch": ["ALL", c["ch"]]}, grp="c54.rows",
        key="c54:" + c["id"])


def _alert_table(top60, live, d54, label_day):
    th = lambda align, text: h("th", {"textAlign": align, "padding": "6px 8px"}, text)  # noqa: E731
    rows = []
    for c in top60:
        item = d54.get(c["id"]) if live else None
        rows.append(h("tr", {"borderBottom": "1px solid " + C.parch},
                      h("td", {"padding": "6px 8px", "fontFamily": F_MONO, "color": pri_color(c["p"]),
                               "fontWeight": 700}, c["id"]),
                      h("td", {"padding": "6px 8px"}, c["ch"]),
                      h("td", {"padding": "6px 8px", "color": C.inkD}, c["claim"], _u(c["claim"]),
                        [" ", _pill(item.get("status"))] if item else None),
                      h("td", {"padding": "6px 8px", "textAlign": "right", "fontFamily": F_MONO, "color": C.ink2},
                        c["dl"]),
                      h("td", {"padding": "6px 8px", "textAlign": "right", "fontWeight": 700,
                               "color": C.crimson if c["days"] <= 14 else C.gold if c["days"] <= 30 else C.emerald},
                        str(c["days"]) + "d", tier("E") if live else None),
                      key="c54.alert:" + c["id"]))
    return Card(
        h("div", {"fontSize": 11, "color": C.gold, "letterSpacing": ".2em", "fontFamily": F_MONO, "fontWeight": 600,
                  "marginBottom": 10}, "⚡ TOP ALERTS · ≤60 ngày (%s)" % label_day, upd_mark() if live else None),
        h("table", {"width": "100%", "fontSize": 11, "fontFamily": F_SERIF, "borderCollapse": "collapse"},
          h("thead", None, h("tr", {"borderBottom": "1px solid " + C.ink2, "color": C.ink2, "fontFamily": F_MONO,
                                    "fontSize": 9, "letterSpacing": ".1em"},
                             th("left", "ID"), th("left", "CHAEBOL"), th("left", "CLAIM"), th("right", "DEADLINE"),
                             th("right", "DAYS"))),
          h("tbody", None, *rows)),
        accent=C.gold, key="c54.alerts")


def build_claims54(ctx):
    claims = _need(ctx.v21, "CLAIMS_54")
    live = ctx.live
    today = ctx.today if live else V21_TODAY
    d54 = _dossier_part(ctx, "claims54") if live else {}
    enriched = enrich54(claims, today)
    chaebols = ["ALL"] + _uniq(c["ch"] for c in claims)
    pris = ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"]      # Claims54Tab.jsx@L6798
    counts = {k: 0 for k in _PRI_ORDER}
    for c in enriched:
        counts[c["p"]] += 1
    top60 = sorted((c for c in enriched if c["urgent"]), key=lambda c: c["days"])
    n_past = sum(1 for c in enriched if c["past"])
    label_day = "%d/%d/%d" % (today.day, today.month, today.year)
    sub = "From CHAEBOL-VN-21-PROJECT-KNOWLEDGE-v3.md · CRITICAL 4 · HIGH 14 · MEDIUM 23 · LOW 13"
    if live:
        sub = [sub, v21_mark()]
    sec1 = Section(
        "📊 54 FALSIFIABLE CLAIMS · Priority-ranked (v3.0 MD)",
        h("div", {"display": "grid", "gridTemplateColumns": "repeat(6, 1fr)", "gap": 10, "marginBottom": 14},
          _stat54(C.crimson, "🔥 CRITICAL", counts["CRITICAL"], "Portfolio decisions", live=live),
          _stat54(C.gold, "HIGH", counts["HIGH"], "Sector rotation", live=live),
          _stat54(C.emerald, "MEDIUM", counts["MEDIUM"], live=live),
          _stat54(C.ink2, "LOW", counts["LOW"], live=live),
          _stat54(C.gold, "≤60d", len(top60), "Urgent watch", C.gold, live=live),
          _stat54(C.crimson, "PAST", n_past, "Verify needed", C.crimson, live=live)),
        _alert_table(top60, live, d54, label_day) if top60 else None,
        accent=C.crimson, sub=sub, key="c54.top")
    buttons = [h("button", {"padding": "4px 10px", "background": "transparent", "color": C.ink,
                            "border": "1px solid " + pri_color(p), "cursor": "pointer", "fontWeight": 600}, p,
                 on={"set": {"c54.pri": p}},
                 var=[{"if": {"c54.pri": p}, "s": {"background": pri_color(p), "color": "#0a0a0c"}}],
                 key="c54.btn:" + p) for p in pris]
    select = h("select", {"padding": "4px 8px", "background": "transparent", "color": C.ink,
                          "border": "1px solid " + C.ink2, "fontFamily": F_MONO, "fontSize": 9, "marginLeft": 10},
               *[h("option", None, ch, a={"value": ch}) for ch in chaebols], bind="c54.ch", key="c54.select")
    sec2 = Section(
        "Filter & Browse — 54 Claims",
        h("div", {"display": "flex", "flexWrap": "wrap", "gap": 6, "marginBottom": 14, "fontFamily": F_MONO,
                  "fontSize": 9, "letterSpacing": ".1em"},
          *buttons, select,
          h("div", {"marginLeft": "auto", "color": C.ink2, "alignSelf": "center"},
            count={"grp": "c54.rows", "fmt": "Showing {n}/54"})),
        summary_line(d54, [c["id"] for c in claims],
                     "CHẤM LẠI %s · 54 claim (hạn = trường dl; hôm nay %s thay mốc cố định 12/05/2026 của V21): "
                     % (_dmy(today), _dmy(today)), today, "c54.summary"),
        h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 10},
          *[_claim54_card(c, ctx, d54) for c in sort54(enriched)]),
        accent=C.ink2, key="c54.browse")
    root = h("div", None, sec1, sec2, key="tab:claims54")
    return {"root": root, "states": [{"key": "c54.pri", "default": "ALL", "options": pris},
                                     {"key": "c54.ch", "default": "ALL", "options": chaebols}]}
