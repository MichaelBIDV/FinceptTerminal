#!/usr/bin/env python3
"""
chaebol_map_tab_deep — tab `catalyst` (★ 12 · CATALYST CALENDAR) và tab `deep6` (★ 14 · DEEP-DIVE 24 CHAEBOL).

Nguồn: SRC ~/Downloads/master_plan_v21_chaebol_vn30.html dòng 6829–6862 (CatalystCalendarTab), 6922–7027
(DeepDive6Tab); hằng CATALYST_CAL (1341–1470), DEEP_INSIGHT_24 (1979–3027) lấy từ ctx.v21. Đặc tả:
chaebol_map_spec/page_p7a §3, page_p7b §3–§4. Style chép đúng thứ tự khoá JSX; màu as_intended (C.crimson,
C.emerald có giá trị, DESIGN §0.1); nút lọc thừa kế font cha (lõi tự thêm `inherit`).

Mode v21: nguyên văn trang gốc ("hôm nay" của tab 12 = 12/05/2026 như CatalystCalendarTab.today).
Mode live: cùng cây + lớp `chaebol_map_tab_deep_live` (nhập trễ): hôm nay = ctx.today, kết quả sự kiện đã qua,
sự kiện mới tới 03/2027, cập nhật lãnh đạo / KQKD / sở hữu chéo, đánh dấu Munger bị dữ kiện bác, stance V21 giữ
nguyên + dấu V21·12/05. Mọi chữ mới lấy từ dossier (khoá catalyst / catalyst_status / entities24).

State deep6 (DESIGN §4): d24.sel (24 khoá, mặc định Vingroup), d24.axis (4), d24.tier (5). Tổ hợp lọc rỗng quay
về đủ 24 nút (bộ đếm vẫn "24/24 chaebol"); sel không reset khi lọc — sel rơi khỏi danh sách thì panel hiện
names[0] mà không nút nào sáng. Hai điều này phát bằng khoá ghép `d24.axis|d24.tier` và `d24.sel|d24.axis|d24.tier`.
"""
from __future__ import annotations

from datetime import date

from chaebol_map_dom import C, F_MONO, h, js_string
from chaebol_map_shell import Card, Section

F_SS4 = "'Source Serif 4', serif"
F_CG = "'Cormorant Garamond', serif"
V21_TODAY = date(2026, 5, 12)                     # CatalystCalendarTab.today = new Date('2026-05-12')
CAT_GRID = "80px 1fr 50px 90px 110px 90px"
CAT_TITLE = "📅 CATALYST CALENDAR · Q2/2026 → Q2/2027 (16 events)"
CAT_SUB = "From MD section 9 · Impact + Magnitude + Claim refs"
D24_TITLE = "🔬 DEEP-DIVE 24 CHAEBOL · Wyckoff + Cash Flow + Munger + Interlocks (MAX)"
D24_SUB = "From MD v3.0 section 2+3+4 · 24 entries full 6-panel analysis · Filter axis × tier"
MUNGER_HEAD = '🔄 MUNGER INVERSION · "Nếu THẤT BẠI?"'
VIOLET = "#a78bfa"
SEL_INK = "#0a0a0c"

# DeepDive6Tab (SRC 6935–6937) — as_intended: C.crimson / C.emerald có giá trị.
WYC_COLOR = {"emerald": C.emerald, "amber": "#fbbf24", "crimson": C.crimson, "gold": C.gold}
AXIS_COLOR = {"NQ79": C.crimson, "NQ68": C.emerald, "SPECIAL": C.gold}
TIER_COLOR = {"Top": C.gold, "Mid": C.emerald, "Distress": C.crimson, "Special": VIOLET}


def _need(v21, name):
    val = (v21 or {}).get(name)
    if not val:
        raise ValueError("v21_const thiếu %s — cần trích lại v21_const.json" % name)
    return val


def _live_layer(ctx):
    """Lớp live (nhập trễ để mode v21 không phụ thuộc). Trả module hoặc None ở v21."""
    if not ctx.live:
        return None
    import chaebol_map_tab_deep_live as L
    return L


# ── ★ 12 · CATALYST CALENDAR ────────────────────────────────────────────────


def mag_color(m):
    """magColor (SRC 6835): 'Mid' và mọi nhãn khác rơi về C.ink2."""
    return C.crimson if m == "CRITICAL" else C.gold if m == "Very High" else C.emerald if m == "High" else C.ink2


def imp_symbol(i):
    """impSymbol (SRC 6836) — emoji nguyên văn (có U+FE0F)."""
    return "⬆️" if i == "+" else "⬇️" if i == "-" else "⬇️⬇️" if i == "--" else "❓"


def days_color(n):
    return C.ink2 if n < 0 else C.crimson if n <= 14 else C.gold if n <= 60 else C.emerald


def days_text(n):
    return js_string(abs(n)) + "d ago" if n < 0 else js_string(n) + "d"


def enrich(events, today):
    """enriched = CATALYST_CAL.map(+days).sort((a,b) => a.days - b.days) — sắp ổn định như V8 TimSort."""
    out = [dict(c, days=(date.fromisoformat(c["d"]) - today).days) for c in events]
    return sorted(out, key=lambda c: c["days"])


def cat_header(live=None):
    cell = lambda *k, **s: h("div", s or None, *k)
    return h("div", {"display": "grid", "gridTemplateColumns": CAT_GRID, "gap": 8, "padding": "8px 12px",
                     "background": C.parch, "fontFamily": F_MONO, "fontSize": 9, "letterSpacing": ".15em",
                     "color": C.ink2, "fontWeight": 600, "marginBottom": 8},
             cell("DATE"), cell("EVENT", live and live.get("event_head")), cell("IMP"),
             cell("MAGNITUDE", live and live.get("mag_head")), cell("CHAEBOL"),
             h("div", {"textAlign": "right"}, "DAYS", live and live.get("days_head")), key="cat.head")


def cat_card(c, i, extra=None):
    """Một thẻ sự kiện (SRC 6844–6856). extra (live): {ref, result, mag} — dòng phụ thêm trong ô EVENT."""
    extra = extra or {}
    n = c["days"]
    return Card(
        h("div", {"display": "grid", "gridTemplateColumns": CAT_GRID, "gap": 8, "alignItems": "center"},
          h("div", {"fontFamily": F_MONO, "fontSize": 10, "color": C.ink, "fontWeight": 600}, c["d"]),
          h("div", None,
            h("div", {"fontSize": 12, "color": C.ink, "fontWeight": 500, "fontFamily": F_SS4}, c["e"],
              extra.get("e_mark")),
            h("div", {"fontSize": 9, "color": C.ink2, "fontFamily": F_MONO, "marginTop": 2},
              extra.get("ref") if "ref" in extra else ["Claims: ", c["ref"]]),
            extra.get("result")),
          h("div", {"fontSize": 18, "textAlign": "center"}, imp_symbol(c["imp"])),
          h("div", {"fontSize": 10, "color": mag_color(c["mag"]), "fontWeight": 700, "fontFamily": F_MONO,
                    "letterSpacing": ".1em"}, c["mag"]),
          h("div", {"fontSize": 10, "color": C.inkD, "fontFamily": F_MONO}, c["ch"]),
          h("div", {"textAlign": "right", "fontSize": 11, "fontWeight": 700, "color": days_color(n),
                    "fontFamily": F_MONO}, days_text(n))),
        accent=mag_color(c["mag"]), key="cat.card.%d" % i)


def build_catalyst(ctx):
    events = list(_need(ctx.v21, "CATALYST_CAL"))
    L = _live_layer(ctx)
    live = L.catalyst_overlay(ctx, events) if L else None
    today = live["today"] if live else V21_TODAY
    rows = enrich(events + (live["new"] if live else []), today)
    cards = [cat_card(c, i, live and live["extra"](c)) for i, c in enumerate(rows)]
    sec = Section(live["title"] if live else CAT_TITLE, live and live.get("intro"), cat_header(live), *cards,
                  accent=C.gold,
                  sub=live["sub"] if live else CAT_SUB, key="cat.section")
    res = {"root": h("div", None, sec), "states": []}
    if live:
        res["csv"] = live["csv"](rows)
    return res


# ── ★ 14 · DEEP-DIVE 24 CHAEBOL ─────────────────────────────────────────────


def names_for(d24, all_names, axis, tier):
    """names (SRC 6926–6932): lọc AXIS × TIER; rỗng → quay về đủ 24."""
    f = [n for n in all_names if (axis == "ALL" or d24[n]["axis"] == axis) and (tier == "ALL" or d24[n]["tier"] == tier)]
    return f if f else list(all_names)


def shown_for(d24, all_names, sel, axis, tier):
    """d = DEEP_INSIGHT_24[names.includes(sel) ? sel : names[0]] (SRC 6933)."""
    names = names_for(d24, all_names, axis, tier)
    return sel if sel in names else names[0]


def _head(text, color, mb, extra=None):
    return h("div", {"fontSize": 10, "color": color, "letterSpacing": ".2em", "fontFamily": F_MONO, "fontWeight": 600,
                     "marginBottom": mb}, text, extra)


def _chip(text, color):
    return h("span", {"padding": "2px 8px", "background": color + "25", "color": color, "fontFamily": F_MONO,
                      "fontSize": 9, "fontWeight": 700, "letterSpacing": ".1em"}, text)


def _filter_button(value, color_map, key):
    return h("button", {"padding": "3px 8px", "background": "transparent", "color": C.ink,
                        "border": "1px solid " + (color_map.get(value) or C.ink2), "cursor": "pointer",
                        "fontWeight": 600}, value,
             on={"set": {key: value}},
             var=[{"if": {key: value}, "s": {"background": color_map.get(value) or C.gold, "color": SEL_INK}}])


def filter_row(axis_opts, tier_opts):
    return h("div", {"display": "flex", "flexWrap": "wrap", "gap": 6, "marginBottom": 10, "fontFamily": F_MONO,
                     "fontSize": 9, "letterSpacing": ".1em"},
             h("span", {"color": C.ink2, "alignSelf": "center", "marginRight": 4}, "AXIS:"),
             [_filter_button(a, AXIS_COLOR, "d24.axis") for a in axis_opts],
             h("span", {"color": C.ink2, "alignSelf": "center", "marginLeft": 8, "marginRight": 4}, "TIER:"),
             [_filter_button(t, TIER_COLOR, "d24.tier") for t in tier_opts],
             h("span", {"marginLeft": "auto", "color": C.ink2, "alignSelf": "center"},
               count={"grp": "d24.names", "fmt": "{n}/24 chaebol"}),
             key="d24.filters")


def entity_row(d24, all_names, axis_opts, tier_opts):
    combos_all = ["%s|%s" % (a, t) for a in axis_opts for t in tier_opts]
    buttons = []
    for n in all_names:
        combos = [c for c in combos_all if n in names_for(d24, all_names, *c.split("|"))]
        buttons.append(h("button", {"padding": "5px 10px", "background": "transparent", "color": C.ink,
                                    "border": "1px solid " + (TIER_COLOR.get(d24[n]["tier"]) or C.gold),
                                    "cursor": "pointer", "fontWeight": 600, "fontSize": 10, "fontFamily": F_MONO}, n,
                         on={"set": {"d24.sel": n}}, grp="d24.names",
                         if_=None if len(combos) == len(combos_all) else {"d24.axis|d24.tier": combos},
                         var=[{"if": {"d24.sel": n}, "s": {"background": C.gold, "color": SEL_INK}}],
                         key="d24.btn." + n))
    return h("div", {"display": "flex", "flexWrap": "wrap", "gap": 5, "marginBottom": 18}, *buttons,
             key="d24.entities")


def leader_card(d, ov):
    ax, ti = AXIS_COLOR.get(d["axis"]), TIER_COLOR.get(d["tier"])
    return Card(
        _head("👑 LEADER", C.gold, 6, ov.get("leader_head")),
        h("div", {"fontSize": 18, "color": C.ink, "fontWeight": 700, "fontFamily": F_CG},
          ov["leader"] if "leader" in ov else d["leader"]),
        ov.get("leader_note"),
        h("div", {"display": "flex", "gap": 6, "marginTop": 8},
          _chip(d["axis"], ax), _chip(d["tier"].upper(), ti), ov.get("chips_mark")),
        h("div", {"fontSize": 10, "color": C.ink2, "fontFamily": F_MONO, "marginTop": 8, "letterSpacing": ".1em"},
          "TICKERS: " + " · ".join(d["tickers"]), ov.get("tickers_mark")),
        ov.get("tickers_live"),
        h("div", {"fontSize": 10, "color": C.ink2, "marginTop": 6},
          "Claims: " + (" · ".join(d["claims"]) if d["claims"] else "None tracked"), ov.get("claims_mark")),
        ov.get("claims_live"),
        accent=C.gold, key="d24.leader")


def wyckoff_card(d, ov):
    w = d["wyckoff"]
    wyc = WYC_COLOR.get(w["color"]) or C.ink2
    return Card(
        _head("📈 WYCKOFF PHASE", wyc, 6, ov.get("wyc_head")),
        h("div", {"fontSize": 18, "color": wyc, "fontWeight": 700, "fontFamily": F_CG}, w["phase"], ov.get("phase_mark")),
        h("div", {"display": "flex", "gap": 4, "marginTop": 8},
          *[h("div", {"width": 30, "height": 8, "background": wyc if k <= w["score"] else C.parch, "borderRadius": 1})
            for k in range(1, 7)]),
        h("div", {"fontSize": 10, "color": C.ink2, "marginTop": 4, "fontFamily": F_MONO},
          "Distribution score: " + js_string(w["score"]) + "/6"),
        h("ul", {"margin": "8px 0 0", "paddingLeft": 18, "fontSize": 10, "color": C.inkD, "lineHeight": 1.6,
                 "fontFamily": F_SS4},
          *[h("li", None, s, (ov.get("signal_marks") or {}).get(i)) for i, s in enumerate(w["signals"])],
          ov.get("signals_live")),
        accent=wyc, key="d24.wyckoff")


def cash_card(d, ov):
    cf = d["cashFlow"]
    lbl = {"color": C.emerald, "fontSize": 11, "fontFamily": F_MONO}
    val = {"color": C.ink, "fontSize": 12}
    return Card(
        _head("💰 CASH FLOW", C.emerald, 6, ov.get("cash_head")),
        h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 10, "marginBottom": 6},
          h("div", None, h("strong", lbl, "LNST 2025:"), " ", h("span", val, cf["lnst"]), ov.get("lnst_mark")),
          h("div", None, h("strong", lbl, "CAPEX:"), " ", h("span", val, cf["capex"]), ov.get("capex_mark"))),
        ov.get("cash_live"),
        h("div", {"fontSize": 11, "color": C.inkD, "lineHeight": 1.6, "fontFamily": F_SS4, "marginTop": 6},
          cf["detail"], ov.get("detail_mark")),
        ov.get("detail_live"),
        accent=C.emerald, key="d24.cash")


def munger_card(d, ov):
    marks = ov.get("munger_marks") or {}
    return Card(
        _head(MUNGER_HEAD, C.crimson, 8, ov.get("munger_head")),
        *[h("div", {"fontSize": 11, "color": C.inkD, "lineHeight": 1.6, "padding": "6px 10px",
                    "background": C.crimson + "10", "borderLeft": "2px solid " + C.crimson, "marginBottom": 6,
                    "fontFamily": F_SS4}, m, marks.get(i)) for i, m in enumerate(d["munger"])],
        accent=C.crimson, key="d24.munger")


def interlock_card(d, ov):
    marks = ov.get("interlock_marks") or {}
    return Card(
        _head("🔗 HIDDEN INTERLOCKS", VIOLET, 8, ov.get("inter_head")),
        h("ul", {"margin": 0, "paddingLeft": 18, "fontSize": 11, "color": C.inkD, "lineHeight": 1.7, "fontFamily": F_SS4},
          *[h("li", None, it, marks.get(i)) for i, it in enumerate(d["interlocks"])], ov.get("interlocks_live")),
        accent=VIOLET, key="d24.interlocks")


def risk_action(d, ov):
    return h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 10, "marginTop": 14},
             Card(_head("⚠ KEY RISK", C.crimson, 6, ov.get("risk_head")),
                  h("div", {"fontSize": 11, "color": C.ink, "lineHeight": 1.6, "fontFamily": F_SS4}, d["risk"],
                    ov.get("risk_mark")),
                  ov.get("risk_live"), accent=C.crimson, key="d24.risk"),
             Card(_head("🎯 ACTION", C.gold, 6, ov.get("action_head")),
                  h("div", {"fontSize": 11, "color": C.ink, "lineHeight": 1.6, "fontWeight": 500, "fontFamily": F_SS4},
                    d["action"], ov.get("action_mark")),
                  ov.get("action_live"), accent=C.gold, key="d24.action"),
             key="d24.grid2")


def panel(n, d, ov):
    """Bảng 7 thẻ của một thực thể (SRC 6964–7023). Bọc div không style = cùng hình (margin collapse xuyên qua)."""
    return [
        h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 14, "marginBottom": 14},
          leader_card(d, ov), wyckoff_card(d, ov), key="d24.grid1"),
        cash_card(d, ov), munger_card(d, ov), interlock_card(d, ov), risk_action(d, ov)]


def build_deep6(ctx):
    v21 = ctx.v21
    d24 = _need(v21, "DEEP_INSIGHT_24")
    axis_opts = [str(x) for x in _need(v21, "DeepDive6Tab.jsx@L6943")]
    tier_opts = [str(x) for x in _need(v21, "DeepDive6Tab.jsx@L6947")]
    all_names = list(d24)
    L = _live_layer(ctx)
    live = L.deep6_overlay(ctx, d24) if L else None
    panels = []
    for n in all_names:
        combos = ["%s|%s|%s" % (s, a, t) for s in all_names for a in axis_opts for t in tier_opts
                  if shown_for(d24, all_names, s, a, t) == n]
        panels.append(h("div", None, *panel(n, d24[n], live["entity"](n) if live else {}),
                        if_={"d24.sel|d24.axis|d24.tier": combos}, key="d24.panel." + n))
    sec = Section(D24_TITLE, live and live.get("intro"), filter_row(axis_opts, tier_opts),
                  entity_row(d24, all_names, axis_opts, tier_opts), *panels,
                  accent=C.gold, sub=live["sub"] if live else D24_SUB, key="d24.section")
    res = {"root": h("div", None, sec),
           "states": [{"key": "d24.sel", "default": "Vingroup", "options": all_names},
                      {"key": "d24.axis", "default": "ALL", "options": axis_opts},
                      {"key": "d24.tier", "default": "ALL", "options": tier_opts}]}
    if live:
        res["csv"] = live["csv"]()
    return res
