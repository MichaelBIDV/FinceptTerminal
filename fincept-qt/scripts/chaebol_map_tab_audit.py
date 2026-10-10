#!/usr/bin/env python3
"""
chaebol_map_tab_audit — tab `10 · DATA & METRIC AUDIT` của module chaebol_map (clone DataAuditTab, SRC 7483–7803;
hằng VN30_TICKERS_FOR_AUDIT 7255, DATA_AUDIT_PIPELINES 7262, DATA_AUDIT_VALIDATION_RULES 7461,
DATA_AUDIT_FILE_LAYOUT 7472 — đọc từ ctx.v21, không đọc SRC lúc chạy). Hợp đồng: chaebol_map_spec/DESIGN.md; nội dung:
chaebol_map_spec/page_p8_audit.md; API: api_python.md, api_data.md.

State duy nhất (DESIGN §4): `aud.pipe` — 11 id pipeline, mặc định P0_DAILY_PRICE. Thẻ chi tiết = 11 Card mang `if`.
Lỗi React giữ nguyên như trang (page_p8 §3.B1): nút pipeline có `border` rồi `borderLeft`; khi đổi chọn React chỉ ghi lại
`border` (shorthand) của nút cũ và nút mới → vạch trái 3px của hai nút đó thành 1px màu border và không bao giờ về lại.
Tái hiện bằng cờ ẩn `aud.bl.<id>` (không khai báo trong inventory, nằm trong scope gốc tab → reset khi đổi tab):
bấm nút X ≠ mặc định đặt aud.bl.X và aud.bl.<mặc định>; mặc định chỉ "mất vạch" khi đã có nút khác được chọn.
Ô rỗng giữ như trang: P0_FLOW_PILLAR_IV có 6 ô trống (SOURCE, URL TEMPLATE, METHOD, SELECTOR HINT, PARSE LOGIC,
VALIDATION); P0_PERF_60D, P1_VWAP_CLUSTER trống SELECTOR HINT.
Sai khác có chủ đích (cả hai mode): bỏ email licence cá nhân khỏi `source_label` của P2_OWNERSHIP_CIQ_CHROME.

Mode live: cùng builder + lớp chaebol_map_tab_audit_live (sổ nguồn so_nguon_audit, độ phủ vc_lk 45 mã, kiểm lại 8 luật
QC trên dữ liệu thật, văn bản viết lại từ dossier `audit` của cap_nhat_<ngày>.audit.json).
"""
from __future__ import annotations

import re

from chaebol_map_dom import C, F_DISPLAY, F_MONO, F_NUM, F_SERIF, alpha, h, jsx_text, v21_mark
from chaebol_map_shell import Card, Pill, Section

STATE_KEY = "aud.pipe"
BL_PREFIX = "aud.bl."          # cờ ẩn tái hiện lỗi borderLeft của React (xem docstring)

# ── Chuỗi JSX nguyên văn (SRC 7497–7800) ────────────────────────────────────

A_TITLE = "Data & Metric Audit · Browser-Batch Automation Spec"
A_SUB = "Spec sheet cho Claude Code · 11 pipelines · 45 tickers · 8 validation rules"
A_RUNS = (
    ("t", jsx_text("\n          Tab này được thiết kế để ")),
    ("strong", "Claude Code đọc và tự động hoá pipeline cập nhật V21"),
    ("t", jsx_text(" qua browser_batch tool.\n          Mỗi pipeline có URL template, selector hint, parse logic, "
                   "target field, validation rule. Khi anh chat với Claude Code,\n          chỉ cần share file JSX này "
                   "+ nói ")),
    ("em", "\"Đọc DATA_AUDIT_PIPELINES, chạy P0 batch, cập nhật FLOW object trong file\""),
    ("t", jsx_text(" — phần còn lại auto.\n        ")),
)
STAT_CARDS = (   # (khoá, màu, nhãn, phụ)
    ("P0", "vermillion", "P0 PIPELINES", "Daily critical"),
    ("P1", "ochre", "P1 PIPELINES", "Event/weekly"),
    ("P23", "gold", "P2-P3", "Quarterly/macro"),
    ("TICKERS", "forest", "TICKERS", "VN30 + chaebol"),
    ("VALIDATION", "ink2", "VALIDATION", "QC rules"),
)
B_TITLE = "Pipelines · Click để xem spec đầy đủ"
C_TITLE = "Claude Code Browser-Batch Playbook · Daily Routine"
C_DAILY_LABEL = "▸ DAILY P0 ROUTINE · ~5 minutes"
C_DAILY_PRE = (
    "# Step 1: Bulk price fetch (15:30 ICT)\nbrowser_batch([\n  {tool: 'navigate', url: "
    "'cafef.vn/du-lieu/lich-su-giao-dich-VIC-1.chn'},\n  {tool: 'read_page'},\n  {tool: 'navigate', url: "
    "'...VHM-1.chn'},\n  ... // 45 tickers, 5-10 per batch call\n]);\n\n# Step 2: Parse & validate\nfor ticker in "
    "tickers:\n  px = parseFloat(html_extract(ticker))\n  assert 1000 ≤ px ≤ 1000000\n\n# Step 3: Update FLOW object "
    "in JSX\nstr_replace(\n  file: 'master_plan_v21_chaebol_vn30.jsx',\n  old: `{TICKER}: { px:OLDVAL, ...`,\n  new: "
    "`{TICKER}: { px:NEWVAL, ...`\n)\n\n# Step 4: Run flow update from FiinTrade xlsx\n# (Tuấn manual download — "
    "script parses)")
C_EVENT_LABEL = "▸ EVENT P1 TRIGGERS"
C_EVENT_PRE = (
    "# AGM season (Mar-Jun): scan top picks\nfor ticker in CHAEBOL_FOCUS_LIST:\n  search('ĐHĐCĐ {ticker} 2026 kế "
    "hoạch')\n  read_top_3_results()\n  extract({rev_target, profit_target, dividend})\n  diff_with_existing_data()\n"
    "  if diff > 5%: ALERT\n\n# Insider transactions: daily scan\nscrape_ssc_insider_disclosure()\nfilter(date ≥ "
    "today-7d AND shares ≥ 100K)\nflag_critical(shares ≥ 0.5% outstanding)\n\n# Legal news: daily news scan\n"
    "google_search('{TICKER} (khởi tố OR điều tra)')\nfilter_last_30d_top3_sources()\nif any_match: WATCHLIST_ALERT")
C_MASTER_LABEL = "▸ MASTER PROMPT · Anh paste cái này cho Claude Code khi bắt đầu session"
C_MASTER_PRE = (
    "Đọc file master_plan_v21_chaebol_vn30.jsx tại /mnt/user-data/uploads/.\n\nTìm const DATA_AUDIT_PIPELINES — đó "
    "là spec sheet cho automation.\n\nTasks hôm nay:\n1. Chạy P0_DAILY_PRICE: fetch giá đóng cửa của 45 ticker từ "
    "cafef.vn (URL template trong pipeline). \n   Dùng browser_batch chia 5-7 navigate/call để tránh timeout. \n   "
    "Validate: 1000 ≤ px ≤ 1,000,000.\n\n2. Chạy P0_PERF_60D: compute lại perf60 từ price history mới + \n   classify "
    "BULL/BEAR/MIX theo sig_logic.\n\n3. Update FLOW object trong file JSX bằng str_replace, mỗi ticker 1 lần.\n   "
    "Format: TICKER: { px:NEW, perf60:NEW, ca60:..., to60:..., td60:..., \n                     nn60:..., "
    "sig:'BULL/BEAR/MIX', date:'YYYY-MM-DD' }\n\n4. Sau khi xong, save backup vào /home/claude/v21/data_cache/\n   "
    "prices_{YYYYMMDD}.json + flow_60d_{YYYYMMDD}.json.\n\n5. Run validation rules trong "
    "DATA_AUDIT_VALIDATION_RULES.\n   Báo cáo discrepancy nếu có.\n\n6. Trả về summary: số ticker đã update, số ticker "
    "fail validation, \n   top 5 BULL signals mới + top 5 BEAR signals mới.\n\nLưu ý: \n- KHÔNG đụng vào "
    "TICKER_DETAIL, VN30_LIST, PORTFOLIO_ACTION trong file \n  (đó là analytical content, không phải auto-data).\n- "
    "Chỉ update FLOW object — đó là single source of truth cho data tự động.\n- Nếu cafef.vn không reachable thì "
    "fallback vietstock.vn (URL trong pipeline).")
D_TITLE = "Validation & Quality-Control Rules"
D_COLS = (("RULE", "22%"), ("CHECK", "48%"), ("APPLIES TO", "30%"))
E_TITLE = "Cache File Layout · Output Schema"
E_INTRO = jsx_text("\n            Claude Code lưu kết quả vào các file dưới đây. Tuấn có thể inspect, version-control, "
                   "hoặc feed lại cho V21 pipeline.\n          ")
E_COLS = (("PATH", "45%"), ("DESCRIPTION", "55%"))
F_TITLE = "Ticker Coverage · 45 mã + Priority"
F_TIERS = (   # (nhãn, màu nhãn, weight nhãn, danh sách, màu danh sách)
    ("★ TIER 1 · CHAEBOL FOCUS (P0+P1 full coverage):", "gold", 700,
     "GEX · GEE · GEL · VIX · VJC · VCI · DGC · MSN · VCB · FPT", "ink"),
    ("◆ TIER 2 · VN30 CORE (P0 daily, P1 weekly):", "ochre", 700,
     "VIC · VHM · VRE · VPL · MSR · BID · CTG · TCB · MBB · VPB · STB · ACB · TPB · SHB · LPB · MWG · HPG · GAS · BSR · "
     "PLX", "ink"),
    ("◇ TIER 3 · VN30 PERIPHERY (P0 daily only):", "inkD", 600,
     "SSB · VIB · GVR · VNM · SAB · VTP · VGI · NVL · VPI · SSI · HCM · GMD · HAH · PC1 · CTD", "inkD"),
)
G_TITLE = "★ HƯỚNG DẪN SỬ DỤNG VỚI CLAUDE CODE"
G_PARAS = (   # (màu strong, strong, [phần: chuỗi | ("em", chuỗi)])
    ("gold", "Workflow đề xuất 1 (daily 5 phút):",
     [" Mở Claude Code, paste master prompt ở section \"Browser-Batch Playbook\", attach file V21 JSX. Claude Code sẽ "
      "chạy P0 batch, update FLOW object, save cache, validate. Tuấn review summary trong vài phút."]),
    ("gold", "Workflow đề xuất 2 (event-driven):",
     [" Khi có news lớn (AGM, khởi tố, insider txn, BCTC), trigger Claude Code chạy P1/P2 specific pipeline qua prompt: ",
      ("em", "\"Chạy P1_AGM_EVENTS cho ticker X — file Y.jsx\""), "."]),
    ("gold", "Workflow đề xuất 3 (V22 expansion):",
     [" Khi cần build deep-dive cho 1 chaebol mới (ví dụ HPG/Bầu Long), Claude Code dùng các pipeline P1/P2 để gom đủ "
      "data points (AGM 2026, top holders, foreign room, insider txn last 90d, BCTC quý gần nhất, VWAP cluster) — sau "
      "đó tự generate thêm tab GEX-style theo template ChaebolDeepDive."]),
    ("vermillion", "Lưu ý quan trọng:",
     [" Claude Code KHÔNG được update các const phân tích (TICKER_DETAIL, VN30_LIST, PORTFOLIO_ACTION) tự động — đó là "
      "analytical opinion của Tuấn, cần manual review. Auto-update CHỈ áp dụng cho FLOW object (numerical/factual "
      "data)."]),
)
KV_LABELS = ("FREQUENCY", "SOURCE", "URL TEMPLATE", "FALLBACK URL", "METHOD", "SELECTOR HINT", "PARSE LOGIC",
             "TARGET FIELDS", "VALIDATION", "TICKERS", "SIG LOGIC")
_LICENSE_RE = re.compile(r",\s*license\s+[^\s,()]+@[^\s,()]+", re.I)

# ── Style (thứ tự khoá như JSX) ─────────────────────────────────────────────

S_CALLOUT = {"fontSize": 13, "fontFamily": F_SERIF, "color": C.inkD, "lineHeight": 1.75, "fontStyle": "italic",
             "marginBottom": 18, "padding": "14px 18px", "background": C.parch, "borderLeft": "3px solid " + C.gold}
S_KV_LABEL = {"color": C.inkM, "letterSpacing": ".12em", "fontSize": 9}
S_CODE = {"color": C.ink, "background": C.parch, "padding": "4px 8px", "fontSize": 10, "borderRadius": 1,
          "wordBreak": "break-all"}
S_CODE_FB = {"color": C.inkD, "background": C.parch, "padding": "4px 8px", "fontSize": 10, "borderRadius": 1,
             "wordBreak": "break-all"}
S_CODE_SEL = {"color": C.ink, "background": C.parch, "padding": "4px 8px", "fontSize": 10, "borderRadius": 1}
S_CARD_LABEL = {"fontSize": 10, "letterSpacing": ".18em", "fontFamily": F_MONO, "marginBottom": 10, "fontWeight": 600}
S_PRE = {"fontFamily": F_NUM, "fontSize": 10, "color": C.ink, "lineHeight": 1.7, "margin": 0, "whiteSpace": "pre-wrap"}
S_PRE_MASTER = {"fontFamily": F_NUM, "fontSize": 10, "color": C.ink, "lineHeight": 1.75, "margin": 0,
                "padding": "14px 16px", "background": C.parch, "borderRadius": 2, "whiteSpace": "pre-wrap",
                "borderLeft": "3px solid " + C.gold}
S_TABLE = {"width": "100%", "fontSize": 11, "fontFamily": F_MONO, "borderCollapse": "collapse"}
S_TD = {"padding": "10px 8px"}


def _k(node, *parts):
    """Đặt con = các phần TÁCH RỜI như React: mỗi {biểu thức} JSX là một nút chữ riêng (h() gộp chuỗi kề nhau;
    Chrome shape theo từng nút chữ nên gộp lệch ref). '' / None / False bỏ như JSX."""
    kids = []

    def add(x):
        if x is None or x is False or x is True or x == "":
            return
        if isinstance(x, (list, tuple)):
            for y in x:
                add(y)
            return
        kids.append(x)

    add(parts)
    if kids:
        node["k"] = kids
    else:
        node.pop("k", None)
    return node


def prio_color(priority):
    """priorityColor (SRC 7487–7492): đọc chuỗi priority (không đọc id) → P2_OWNERSHIP_CIQ_CHROME tô ochre."""
    p = str(priority or "")
    if p.startswith("P0"):
        return C.vermillion
    if p.startswith("P1"):
        return C.ochre
    if p.startswith("P2"):
        return C.gold
    return C.inkD


def clean_source_label(text):
    """Bỏ email licence cá nhân (page_p8 §9.9) — sai khác CÓ CHỦ ĐÍCH ở cả hai mode."""
    return _LICENSE_RE.sub("", text) if isinstance(text, str) else text


def js_split(s, sep, i):
    """`s.split(sep)[i]` của JS; phần tử không có → None (undefined → React không vẽ gì)."""
    parts = str(s).split(sep)
    return parts[i] if 0 <= i < len(parts) else None


def _v21_lists(ctx):
    v = ctx.v21 or {}
    pipes = v.get("DATA_AUDIT_PIPELINES")
    rules = v.get("DATA_AUDIT_VALIDATION_RULES")
    layout = v.get("DATA_AUDIT_FILE_LAYOUT")
    tickers = v.get("VN30_TICKERS_FOR_AUDIT")
    for name, val in (("DATA_AUDIT_PIPELINES", pipes), ("DATA_AUDIT_VALIDATION_RULES", rules),
                      ("DATA_AUDIT_FILE_LAYOUT", layout), ("VN30_TICKERS_FOR_AUDIT", tickers)):
        if not isinstance(val, list) or not val:
            ctx.warn("v21_const thiếu %s — khối tương ứng rỗng" % name)
    ok = lambda x: x if isinstance(x, list) else []  # noqa: E731
    return ok(pipes), ok(rules), ok(layout), ok(tickers)


# ── Section A ───────────────────────────────────────────────────────────────


def _runs(runs):
    out = []
    for kind, text in runs:
        if kind == "strong":
            out.append(h("strong", {"color": C.ink}, text))
        elif kind == "em":
            out.append(h("em", None, text))
        else:
            out.append(text)
    return out


def _stat_card(color, label, value, sub, extra=None):
    return Card(h("div", {"fontSize": 8, "letterSpacing": ".16em", "color": C.inkM, "fontFamily": F_MONO}, label),
                _k(h("div", {"fontSize": 22, "fontWeight": 600, "color": color, "fontFamily": F_NUM}), value),
                h("div", {"fontSize": 9, "color": C.inkD, "fontFamily": F_MONO, "marginTop": 3}, sub),
                extra, padding=12, accent=color)


def section_a(pipes, rules, tickers, L):
    counts = {
        "P0": sum(1 for p in pipes if str(p.get("priority", "")).startswith("P0")),
        "P1": sum(1 for p in pipes if str(p.get("priority", "")).startswith("P1")),
        "P23": sum(1 for p in pipes if str(p.get("priority", "")).startswith(("P2", "P3"))),
        "TICKERS": len(tickers), "VALIDATION": len(rules),
    }
    cards = []
    for key, cname, label, sub in STAT_CARDS:
        value = str(counts[key])
        if L is not None:
            value = [value, v21_mark()]      # số đếm của spec V21 (bản lưu) — không phải số thị trường
        cards.append(_stat_card(C[cname], label, value, sub, L.stat_extra(key) if L is not None else None))
    sub = A_SUB if L is None else L.intro_sub(A_SUB)
    runs = _runs(A_RUNS) if L is None else L.intro_runs(_runs(A_RUNS))
    return Section(A_TITLE,
                   _k(h("div", S_CALLOUT), runs),
                   h("div", {"display": "grid", "gridTemplateColumns": "repeat(5, 1fr)", "gap": 10,
                             "marginBottom": 18}, *cards),
                   accent=C.gold, sub=sub, key="aud:A")


# ── Section B: danh sách pipeline + thẻ chi tiết ────────────────────────────


def _pipe_button(p, default_id, L):
    pid, P = p["id"], prio_color(p.get("priority"))
    on_set = {STATE_KEY: pid}
    if pid != default_id:
        on_set.update({BL_PREFIX + pid: "1", BL_PREFIX + default_id: "1"})
    bl = BL_PREFIX + pid
    name = p.get("name")
    if L is not None:
        name = L.pipe_name(p) or name
    return h("button",
             {"textAlign": "left", "padding": "10px 12px", "background": C.paper, "border": "1px solid " + C.rule,
              "borderLeft": "3px solid " + P, "borderRadius": 1, "cursor": "pointer", "color": C.ink,
              "fontFamily": F_SERIF},
             h("div", {"display": "flex", "justifyContent": "space-between", "alignItems": "baseline",
                       "marginBottom": 3},
               _k(h("span", {"fontFamily": F_MONO, "fontSize": 9, "color": P, "letterSpacing": ".1em",
                             "fontWeight": 700}), pid),
               _k(h("span", {"fontFamily": F_MONO, "fontSize": 8, "color": C.inkM, "letterSpacing": ".1em"}),
                  js_split(p.get("priority", ""), " · ", 1))),
             _k(h("div", {"fontSize": 11, "fontWeight": 400, "color": C.inkD, "lineHeight": 1.4},
                  var=[{"if": {STATE_KEY: pid}, "s": {"fontWeight": 600, "color": C.ink}}]), name),
             _k(h("div", {"fontSize": 9, "color": C.inkM, "fontFamily": F_MONO, "marginTop": 4,
                          "letterSpacing": ".05em"}), "↻ ", p.get("freq")),
             L.button_status(p) if L is not None else None,
             on={"set": on_set},
             var=[{"if": {STATE_KEY: pid},
                   "s": {"background": C.paperHi, "border": "1px solid " + P, "borderLeft": "3px solid " + P}},
                  {"if": {bl: "1"}, "s": {"borderLeft": "1px solid " + C.rule}},
                  {"if": {bl + "|" + STATE_KEY: "1|" + pid}, "s": {"borderLeft": "1px solid " + P}}],
             key="aud.pipe:" + pid)


def _kv(label, value_node):
    return [h("span", S_KV_LABEL, label), value_node]


def _kv_rows(p, fields):
    """Lưới khoá–giá trị (SRC 7572–7606). fields = giá trị hiển thị theo khoá (đã qua lớp live nếu có)."""
    tf = fields.get("target_fields")
    tf_text = " · ".join(str(x) for x in tf) if isinstance(tf, list) else tf
    tk = fields.get("tickers")
    tk_text = ("%s mã" % tk) if isinstance(tk, (int, float)) and not isinstance(tk, bool) else tk
    rows = []
    rows += _kv("FREQUENCY", _k(h("span", {"color": C.ink}), fields.get("freq")))
    rows += _kv("SOURCE", _k(h("span", {"color": C.gold, "fontWeight": 600}), fields.get("source_label")))
    rows += _kv("URL TEMPLATE", _k(h("code", S_CODE), fields.get("source_url")))
    if fields.get("fallback_url"):
        rows += _kv("FALLBACK URL", _k(h("code", S_CODE_FB), fields.get("fallback_url")))
    rows += _kv("METHOD", _k(h("span", {"color": C.ink2, "fontWeight": 600}), fields.get("method")))
    rows += _kv("SELECTOR HINT", _k(h("code", S_CODE_SEL), fields.get("selector_hint")))
    rows += _kv("PARSE LOGIC", _k(h("code", S_CODE), fields.get("parse_logic")))
    rows += _kv("TARGET FIELDS", _k(h("span", {"color": C.forest, "fontFamily": F_NUM, "fontWeight": 600,
                                                "fontSize": 10}), tf_text))
    rows += _kv("VALIDATION", _k(h("span", {"color": C.ochre, "fontSize": 10, "fontWeight": 500}),
                                 fields.get("validation")))
    rows += _kv("TICKERS", _k(h("span", {"color": C.ink}), tk_text))
    if fields.get("sig_logic"):
        rows += _kv("SIG LOGIC", _k(h("span", {"color": C.gold, "fontSize": 10, "fontWeight": 500}),
                                    fields.get("sig_logic")))
    return rows


def _pipe_detail(p, L):
    pid, P = p["id"], prio_color(p.get("priority"))
    fields = dict(p)
    fields["source_label"] = clean_source_label(p.get("source_label"))
    name = p.get("name")
    notes = [p.get("notes")] if p.get("notes") else None
    status_block = spec_mark = None
    if L is not None:
        name = L.pipe_name(p) or name
        fields = L.pipe_fields(p, fields)
        status_block = L.pipe_status(p)
        spec_mark = L.spec_label(p)
        notes = L.pipe_notes(p, notes)
    head = h("div", {"display": "flex", "alignItems": "baseline", "justifyContent": "space-between",
                     "marginBottom": 14, "paddingBottom": 10, "borderBottom": "1px solid " + C.rule},
             h("div", None,
               _k(h("div", {"fontSize": 10, "letterSpacing": ".18em", "color": P, "fontFamily": F_MONO,
                            "fontWeight": 600, "marginBottom": 4}), pid, " · ", p.get("priority")),
               _k(h("h3", {"margin": 0, "fontSize": 20, "fontFamily": F_DISPLAY, "color": C.ink, "fontWeight": 600,
                           "letterSpacing": "-0.01em"}), name)),
             Pill(js_split(p.get("freq", ""), " · ", 0), P))
    grid = h("div", {"display": "grid", "gridTemplateColumns": "140px 1fr", "gap": "10px 18px", "fontSize": 11,
                     "fontFamily": F_MONO, "lineHeight": 1.7}, *_kv_rows(p, fields))
    note_box = None
    if notes:
        note_box = _k(h("div", {"marginTop": 14, "padding": "10px 14px", "background": alpha(P, "12"),
                                "borderLeft": "3px solid " + P, "fontSize": 11, "fontFamily": F_SERIF, "color": C.ink,
                                "lineHeight": 1.7}),
                      h("strong", {"color": P, "fontFamily": F_MONO, "fontSize": 9, "letterSpacing": ".18em"},
                        "NOTES · "), notes)
    return Card(head, status_block, spec_mark, grid, note_box, accent=P, if_={STATE_KEY: pid},
                key="aud.detail:" + pid)


def section_b(pipes, L):
    default_id = pipes[0]["id"] if pipes else None
    picker = h("div", {"display": "flex", "flexDirection": "column", "gap": 6},
               *[_pipe_button(p, default_id, L) for p in pipes])
    details = [_pipe_detail(p, L) for p in pipes]
    return Section(B_TITLE,
                   h("div", {"display": "grid", "gridTemplateColumns": "320px 1fr", "gap": 14}, picker, *details),
                   accent=C.ink2, key="aud:B")


# ── Section C: playbook ─────────────────────────────────────────────────────


def _pre_card(label, color, pre, accent):
    return Card(h("div", {**S_CARD_LABEL, "color": color}, *label),
                h("pre", S_PRE, *pre), accent=accent)


def section_c(L):
    parts = {"daily": ([C_DAILY_LABEL], [C_DAILY_PRE]), "event": ([C_EVENT_LABEL], [C_EVENT_PRE]),
             "master": ([C_MASTER_LABEL], [C_MASTER_PRE])}
    if L is not None:
        parts = {k: L.playbook(k, v) for k, v in parts.items()}
    return Section(C_TITLE,
                   h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 14},
                     _pre_card(parts["daily"][0], C.vermillion, parts["daily"][1], C.vermillion),
                     _pre_card(parts["event"][0], C.ochre, parts["event"][1], C.ochre)),
                   h("div", {"marginTop": 14},
                     Card(h("div", {"fontSize": 10, "letterSpacing": ".18em", "color": C.ink2, "fontFamily": F_MONO,
                                    "marginBottom": 10, "fontWeight": 600}, *parts["master"][0]),
                          h("pre", S_PRE_MASTER, *parts["master"][1]))),
                   accent=C.gold, key="aud:C")


# ── Section D, E: bảng ──────────────────────────────────────────────────────


def _th(label, width):
    return h("th", {"textAlign": "left", "padding": "10px 8px", "fontSize": 9, "letterSpacing": ".16em",
                    "color": C.inkM, "fontWeight": 500, "width": width}, label)


def _zebra(i):
    return {"borderBottom": "1px solid " + C.rule, "background": "transparent" if i % 2 == 0 else alpha(C.parch, "40")}


def section_d(rules, L):
    cols = D_COLS if L is None else L.validation_cols(D_COLS)
    body = []
    for i, r in enumerate(rules):
        extra = L.validation_cell(i, r) if L is not None else None
        body.append(h("tr", _zebra(i),
                      _k(h("td", {**S_TD, "fontWeight": 600, "color": C.gold, "fontSize": 10}), r.get("rule")),
                      _k(h("td", {**S_TD, "color": C.ink, "fontSize": 10}), r.get("check")),
                      _k(h("td", {**S_TD, "color": C.ink2, "fontSize": 10}), r.get("applies")),
                      extra))
    return Section(D_TITLE,
                   Card(h("table", S_TABLE,
                          h("thead", None, h("tr", {"borderBottom": "2px solid " + C.rule},
                                             *[_th(lbl, w) for lbl, w in cols])),
                          h("tbody", None, *body))),
                   accent=C.ochre, key="aud:D")


def section_e(layout, L):
    rows = [(f.get("path"), [f.get("desc")], None) for f in layout]
    intro, cols = [E_INTRO], E_COLS
    if L is not None:
        intro, rows, cols = L.file_layout(intro, rows, cols)
    body = []
    for i, (path, desc, extra) in enumerate(rows):
        body.append(h("tr", _zebra(i),
                      _k(h("td", {**S_TD, "fontFamily": F_NUM, "color": C.gold, "fontSize": 10}), path),
                      _k(h("td", {**S_TD, "color": C.ink, "fontSize": 10, "fontFamily": F_SERIF}), desc),
                      extra))
    return Section(E_TITLE,
                   Card(h("div", {"fontSize": 11, "fontFamily": F_SERIF, "color": C.inkD, "lineHeight": 1.7,
                                  "marginBottom": 14, "fontStyle": "italic"}, *intro),
                        h("table", S_TABLE,
                          h("thead", None, h("tr", {"borderBottom": "2px solid " + C.rule},
                                             *[_th(lbl, w) for lbl, w in cols])),
                          h("tbody", None, *body))),
                   accent=C.forest, key="aud:E")


# ── Section F, G ────────────────────────────────────────────────────────────


def section_f(L):
    blocks = []
    for i, (label, lcolor, weight, items, icolor) in enumerate(F_TIERS):
        mark = v21_mark() if L is not None else None
        blocks.append(h("div", {"marginBottom": 12} if i < len(F_TIERS) - 1 or L is not None else None,
                        h("span", {"color": C[lcolor], "fontWeight": weight, "letterSpacing": ".18em",
                                   "fontSize": 10}, label),
                        mark, h("br"),
                        h("span", {"color": C[icolor]}, items)))
    if L is not None:
        blocks += L.coverage_blocks()
    return Section(F_TITLE,
                   Card(h("div", {"fontSize": 11, "fontFamily": F_MONO, "color": C.ink, "lineHeight": 2,
                                  "letterSpacing": ".05em"}, *blocks)),
                   accent=C.ink2, key="aud:F")


def _g_paras(paras):
    out = []
    for i, (color, lead, parts) in enumerate(paras):
        out.append(h("strong", {"color": C[color] if color in C else color}, lead))
        for part in parts:
            out.append(h("em", None, part[1]) if isinstance(part, tuple) and part[0] == "em" else part)
        if i < len(paras) - 1:
            out += [h("br"), h("br")]
    return out


def block_g(L):
    title, body = [G_TITLE], _g_paras(G_PARAS)
    if L is not None:
        title, body = L.guide(title, body, _g_paras)
    return h("div", {"marginTop": 24, "padding": "18px 22px", "background": alpha(C.gold, "10"),
                     "border": "1px solid " + alpha(C.gold, "40"), "borderRadius": 2},
             h("div", {"fontSize": 10, "letterSpacing": ".2em", "color": C.gold, "fontFamily": F_MONO,
                       "marginBottom": 10, "fontWeight": 600}, *title),
             _k(h("div", {"fontSize": 12, "fontFamily": F_SERIF, "color": C.ink, "lineHeight": 1.85}), body),
             key="aud:G")


# ── Builder ─────────────────────────────────────────────────────────────────


def build_audit(ctx):
    pipes, rules, layout, tickers = _v21_lists(ctx)
    pipes = [p for p in pipes if isinstance(p, dict) and p.get("id")]
    L = None
    if ctx.live:
        from chaebol_map_tab_audit_live import LiveAudit   # nhập trễ: mode v21 không đụng lớp dữ liệu sống
        L = LiveAudit(ctx, pipes, rules, layout, tickers)
    root = h("div", None,
             section_a(pipes, rules, tickers, L),
             section_b(pipes, L),
             section_c(L),
             section_d(rules, L),
             section_e(layout, L),
             section_f(L),
             block_g(L),
             scope=[BL_PREFIX + p["id"] for p in pipes],
             key="aud:root")
    ids = [p["id"] for p in pipes]
    out = {"root": root,
           "states": [{"key": STATE_KEY, "default": ids[0] if ids else "P0_DAILY_PRICE", "options": ids}]}
    if L is not None:
        out["csv"] = L.csv()
    return out
