#!/usr/bin/env python3
"""
chaebol_map_tab_groups — tab 02–06 của "chaebol_map": tuanmuot, sovico, phuong, bauthuy, eliminated.

Nguồn thiết kế: chaebol_map_spec/page_p5_groups_screener.md §0–§6, §8–§9 (ChaebolDeepDive, TickerDeepCard, PhaseBar)
và page_p4_overview_map.md §4 (TuanMuotEcosystemMap). SRC 144–380 (CHAEBOL_GROUPS, TICKER_DETAIL — đọc qua ctx.v21),
5729–6175 (JSX). Style chép đúng thứ tự khoá JSX (shorthand trước longhand).

Mode v21: tái tạo NGUYÊN VĂN (chỉ hằng V21, kể cả bất thường của trang: PhaseBar tự tính pha, tên công ty con màu
C.ink trên nền trắng, pct chip EIB gần như vô hình…). Mode live: cùng builder; lớp dữ liệu sống + dossier + nhãn bậc ở
chaebol_map_tab_groups_live.py (đối tượng `lv`, None ở v21).

State: grp.<tab>.tk (mặc định mã đầu nhóm) — nút mã `on.set`, kiểu active qua `var`, thẻ mã qua `if`.
"""
from __future__ import annotations

from chaebol_map_dom import C, F_DISPLAY, F_MONO, F_NUM, F_SERIF, h, js_string, sign_fixed, to_fixed, to_locale
from chaebol_map_shell import Card, FlowSignal, Pill, Section, Stat

GROUP_IDS = ("tuanmuot", "sovico", "phuong", "bauthuy", "eliminated")
ECO_TITLE = "🗺 CHAEBOL-MAP · HỆ SINH THÁI GELEX"
ECO_SUB = "Nguyễn Văn Tuấn × GEX × GEE × GEL × VIX × EIB — full org chart từ infographic Chaebol Project VN 11/05/2026"
ECO_CAPTION = "CHAEBOL-MAP · HỆ SINH THÁI GELEX · Nguồn: Chaebol Project Vietnam 11/05/2026"
EVENTS_TITLE = "⌖ Key Events Timeline (12 tháng)"
PLACEHOLDER = ("Detail panel đang được biên soạn cho ", ". Tham chiếu screener tab cho flow signal hiện tại.")


def truthy(x):
    """Truthiness JS cho giá trị JSON (None/0/''/False → False; list/dict rỗng vẫn True như JS)."""
    if x is None or x is False:
        return False
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return x != 0
    if isinstance(x, str):
        return x != ""
    return True


def state_key(gid):
    return "grp.%s.tk" % gid


def _rule50():
    return "1px solid " + C.rule + "50"


# ── PhaseBar (SRC 6134–6171) ────────────────────────────────────────────────


def phase_of(perf, sig):
    """if/else-if đúng thứ tự JSX (giữ bất thường: BEAR đè luật theo perf; MIX ∈ [−10, 40) → NEGLECT)."""
    phase, color, label, pos = "P1", C.inkD, "NEGLECT", 10
    if perf < -30:
        phase, color, label, pos = "CAP", C.vermillion, "CAPITULATION", 5
    elif perf < -10:
        phase, color, label, pos = "P1", C.inkD, "DOUBT/NEGLECT", 18
    elif perf < 10 and sig == "BULL":
        phase, color, label, pos = "P2", C.forest, "ACCUMULATION (★)", 35
    elif 10 <= perf < 40 and sig == "BULL":
        phase, color, label, pos = "MARKUP", C.gold, "EARLY MARKUP", 55
    elif 40 <= perf < 80:
        phase, color, label, pos = "P3", C.ochre, "EUPHORIA", 75
    elif perf >= 80 or sig == "BEAR":
        phase, color, label, pos = "P3D", C.vermillion, "DISTRIBUTION", 92
    return phase, color, label, pos


def phase_bar(perf, sig, mark=None, perf_mark=None):
    """Fragment PhaseBar → list nút (chèn thẳng vào Card như JSX). mark / perf_mark: nhãn thêm (live, None ở v21)."""
    phase, color, label, pos = phase_of(perf, sig)
    grad = ("linear-gradient(90deg, %s30 0%%, %s30 17%%, %s30 35%%, %s30 55%%, %s30 75%%, %s30 100%%)"
            % (C.vermillion, C.inkM, C.forest, C.gold, C.ochre, C.vermillion))
    left = js_string(pos) + "%"
    return [
        h("div", {"position": "relative", "height": 36, "background": grad, "borderRadius": 2, "marginBottom": 8},
          h("div", {"position": "absolute", "left": left, "top": -4, "width": 2, "height": 44, "background": color,
                    "transform": "translateX(-50%)"}),
          h("div", {"position": "absolute", "left": left, "top": -22, "transform": "translateX(-50%)", "fontSize": 11,
                    "fontFamily": F_NUM, "color": color, "fontWeight": 700, "whiteSpace": "nowrap"}, phase)),
        h("div", {"display": "flex", "justifyContent": "space-between", "fontSize": 8, "color": C.inkM,
                  "fontFamily": F_MONO, "letterSpacing": ".1em"},
          *[h("span", None, x) for x in ("CAP", "P1", "P2", "MARKUP", "P3", "P3D")]),
        h("div", {"marginTop": 10, "fontSize": 11, "fontFamily": F_DISPLAY, "color": color, "fontWeight": 700,
                  "fontStyle": "italic"}, "Hiện tại: ", label, mark),
        h("div", {"fontSize": 10, "color": C.inkD, "fontFamily": F_MONO, "marginTop": 4, "lineHeight": 1.6},
          "Δ60d: ", sign_fixed(perf, 1), "%", perf_mark, " · Flow: ", sig),
    ]


# ── TuanMuotEcosystemMap (SRC 5791–5899) ────────────────────────────────────


def _own_card(o, bg, border, label_color, last=False, pct_node=None, extra=None, detail_mark=None):
    kids = [h("div", {"fontSize": 9, "fontWeight": 700, "color": label_color, "letterSpacing": ".18em",
                      "marginBottom": 4, "fontFamily": F_MONO}, o["label"])]
    if last:
        kids.append(h("div", {"fontSize": 10.5, "color": C.inkD, "lineHeight": 1.5}, o["detail"], detail_mark))
    else:
        kids.append(h("div", {"fontSize": 10.5, "color": C.inkD, "lineHeight": 1.5, "marginBottom": 4}, o["detail"],
                      detail_mark))
        kids.append(h("div", {"fontSize": 14, "fontWeight": 800, "color": "#dc2626", "fontFamily": F_MONO},
                      pct_node if pct_node is not None else o["pct"]))
    if extra is not None:
        kids.append(extra)
    return h("div", {"padding": "10px 14px", "background": bg, "borderRadius": 4, "border": "1px solid " + border},
             *kids)


def _branch(b, lv):
    subs = b["subs"]
    rows = []
    for si, s in enumerate(subs):
        pct = lv.eco_sub_pct(b, s) if lv else s["pct"]
        rows.append(h("div", {"display": "flex", "justifyContent": "space-between", "alignItems": "baseline",
                              "padding": "5px 0",
                              "borderBottom": "1px solid #e5e7eb" if si < len(subs) - 1 else "none"},
                      h("div", None,
                        h("div", {"fontSize": 10.5, "fontWeight": 700, "color": C.ink}, s["name"]),
                        h("div", {"fontSize": 9.5, "color": C.inkD}, s["desc"])),
                      h("div", {"fontSize": 10, "fontWeight": 800, "color": b["color"], "fontFamily": F_MONO}, pct)))
    head_pct = lv.eco_parent_pct(b) if lv else b["parentPct"]
    head_name = lv.eco_branch_name(b) if lv else b["name"]
    return h("div", {"border": "2px solid " + b["color"], "borderRadius": 6, "overflow": "hidden",
                     "background": "#fff"},
             h("div", {"padding": "10px 12px", "background": b["color"], "color": "#fff"},
               h("div", {"fontSize": 9, "opacity": 0.85, "letterSpacing": ".1em"}, "SỞ HỮU ", head_pct),
               h("div", {"fontSize": 14, "fontWeight": 800, "fontFamily": F_MONO, "marginTop": 2},
                 b["tk"], " — ", head_name),
               h("div", {"fontSize": 9.5, "marginTop": 3, "opacity": 0.9}, b["field"])),
             h("div", {"padding": "10px 12px"},
               *rows,
               h("div", {"marginTop": 10, "padding": "8px 10px", "background": b["color"] + "15", "borderRadius": 3,
                         "border": "1px dashed " + b["color"] + "80"},
                 h("div", {"fontSize": 8.5, "letterSpacing": ".18em", "color": b["color"], "fontWeight": 700,
                           "marginBottom": 4, "fontFamily": F_MONO}, "ĐẶC ĐIỂM"),
                 h("ul", {"margin": 0, "paddingLeft": 14, "fontSize": 9.5, "color": C.inkD, "lineHeight": 1.6},
                   *[h("li", None, t) for t in b["tags"]]))),
             key="eco-branch:" + b["tk"])


def eco_map(eco, lv=None):
    own = eco["ownership"]
    exi = eco["eximbank"]
    flow = eco["flow"]
    steps = []
    for i, f in enumerate(flow):
        steps.append(h("div", {"padding": "6px 10px", "background": "#fff", "border": "1px solid #cbd5e1",
                               "borderRadius": 3, "fontSize": 10, "minWidth": 140},
                       h("div", {"fontWeight": 700, "color": "#1e293b"}, js_string(f["step"]), ". ", f["t"]),
                       h("div", {"fontSize": 9, "color": C.inkD, "marginTop": 2}, f["d"])))
        if i < len(flow) - 1:
            steps.append(h("span", {"color": "#94a3b8", "fontSize": 14}, "→"))
    chips = []
    for hh in exi["holdings"]:
        pct = lv.eco_eib_pct(hh) if lv else hh["pct"]
        chips.append(h("span", {"padding": "3px 9px", "background": "#fef3c7", "border": "1px solid #fbbf24",
                                "borderRadius": 3, "fontSize": 10, "fontFamily": F_MONO},
                       h("strong", {"color": "#b45309"}, hh["entity"], ":"), " ", pct))
    root = h("div", {"background": C.parch + "40", "border": "1px solid " + C.rule, "borderRadius": 4,
                     "padding": "16px 18px"},
             h("div", {"fontSize": 9, "letterSpacing": ".3em", "color": C.inkM, "fontFamily": F_MONO,
                       "marginBottom": 14}, ECO_CAPTION, lv.eco_caption_mark() if lv else None),
             h("div", {"textAlign": "center", "marginBottom": 18},
               h("div", {"display": "inline-block", "padding": "14px 28px", "background": "#1e3a8a", "color": "#fff",
                         "borderRadius": 6, "boxShadow": "0 4px 12px rgba(30,58,138,.25)"},
                 h("div", {"fontSize": 18, "fontWeight": 800, "letterSpacing": ".1em", "fontFamily": F_MONO},
                   eco["chairman"]["name"]),
                 h("div", {"fontSize": 11, "marginTop": 4, "opacity": 0.85},
                   lv.eco_chairman_role(eco) if lv else eco["chairman"]["role"]))),
             h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr", "gap": 12, "marginBottom": 18},
               _own_card(own["direct"], "#dbeafe", "#93c5fd", "#1e40af",
                         pct_node=lv.eco_own_pct("direct", own["direct"]) if lv else None),
               _own_card(own["family"], "#fed7aa", "#fb923c", "#ea580c",
                         pct_node=lv.eco_own_pct("family", own["family"]) if lv else None,
                         detail_mark=lv.eco_family_note() if lv else None),
               _own_card(own["finance"], "#fff", "#cbd5e1", "#475569", last=True,
                         extra=lv.eco_finance_note() if lv else None)),
             h("div", {"textAlign": "center", "marginBottom": 14},
               h("div", {"display": "inline-block", "padding": "14px 32px", "background": "#dc2626", "color": "#fff",
                         "borderRadius": 6, "boxShadow": "0 4px 12px rgba(220,38,38,.3)"},
                 h("div", {"fontSize": 11, "opacity": 0.9, "letterSpacing": ".1em"}, "HOLDING COMPANY"),
                 h("div", {"fontSize": 18, "fontWeight": 800, "fontFamily": F_MONO},
                   eco["holding"]["tk"], " — ", eco["holding"]["name"]),
                 h("div", {"fontSize": 10.5, "marginTop": 4, "opacity": 0.85}, "Lĩnh vực: ", eco["holding"]["field"]))),
             h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr", "gap": 12, "marginBottom": 14},
               *[_branch(b, lv) for b in eco["branches"]]),
             h("div", {"padding": "12px 16px", "background": "#fffbeb", "border": "2px solid #f59e0b", "borderRadius": 6,
                       "marginBottom": 14},
               h("div", {"display": "flex", "justifyContent": "space-between", "alignItems": "baseline",
                         "flexWrap": "wrap", "gap": 10, "marginBottom": 8},
                 h("div", None,
                   h("div", {"fontSize": 9, "letterSpacing": ".18em", "color": "#d97706", "fontWeight": 700,
                             "fontFamily": F_MONO}, exi["rel"]),
                   h("div", {"fontSize": 14, "fontWeight": 800, "color": "#92400e", "fontFamily": F_MONO},
                     exi["tk"], " — ", exi["name"])),
                 h("div", {"fontSize": 11, "color": C.inkD, "fontStyle": "italic"}, exi["note"])),
               h("div", {"display": "flex", "gap": 10, "flexWrap": "wrap"}, *chips),
               lv.eco_eib_note() if lv else None),
             h("div", {"padding": "12px 16px", "background": "#f1f5f9", "borderRadius": 6},
               h("div", {"fontSize": 9, "letterSpacing": ".18em", "color": C.inkM, "fontWeight": 700,
                         "marginBottom": 8, "fontFamily": F_MONO},
                 "★ TÓM TẮT DÒNG CHẢY GIÁ TRỊ TRONG HỆ SINH THÁI GELEX", lv.v21() if lv else None),
               h("div", {"display": "flex", "alignItems": "center", "flexWrap": "wrap", "gap": 6}, *steps)),
             key="eco-map")
    return lv.eco_contrast(root) if lv else root


# ── TickerDeepCard (SRC 5988–6132) ──────────────────────────────────────────


def _label(text, color, mb, fs=10, ls=".18em", extra=None):
    return h("div", {"fontSize": fs, "letterSpacing": ls, "color": color, "fontFamily": F_MONO, "marginBottom": mb},
             text, extra)


def _plan_table(det, lv, tk):
    """KẾ HOẠCH 2026 (AGM) — hiện khi plan2026 && (rev_b || pretax_b). Live: lv.plan_table thay toàn bộ."""
    plan = det.get("plan2026")
    if not (truthy(plan) and (truthy(plan.get("rev_b")) or truthy(plan.get("pretax_b")))):
        return lv.plan_extra(tk) if lv else None
    if lv:
        return lv.plan_table(tk, det)
    th = lambda text, align: h("th", {"textAlign": align, "padding": "4px 0", "color": C.inkM, "fontSize": 9,  # noqa
                                      "letterSpacing": ".1em", "fontWeight": 400}, text)
    py = det.get("py2025") or {}
    q1 = det.get("q1_26") or {}

    def row(label, field, border):
        a, p, q = py.get(field), plan[field], q1.get(field)
        pct = (to_fixed(q / p * 100, 0) + "%") if truthy(q) and truthy(p) else "—"
        return h("tr", {"borderBottom": _rule50()} if border else None,
                 h("td", {"padding": "8px 0", "color": C.inkD, "fontSize": 11}, label),
                 h("td", {"padding": "8px 0", "textAlign": "right", "color": C.ink},
                   to_locale(a, "en") if truthy(a) else "—"),
                 h("td", {"padding": "8px 0", "textAlign": "right", "color": C.gold, "fontWeight": 700},
                   to_locale(p, "en")),
                 h("td", {"padding": "8px 0", "textAlign": "right", "color": C.ink},
                   to_locale(q, "en") if truthy(q) else "—"),
                 h("td", {"padding": "8px 0", "textAlign": "right", "color": C.inkD}, pct))

    rows = []
    if truthy(plan.get("rev_b")):
        rows.append(row("Doanh thu (tỷ)", "rev_b", True))
    if truthy(plan.get("pretax_b")):
        rows.append(row("LN trước thuế (tỷ)", "pretax_b", False))
    growth = None
    rg, pg = det.get("revGrowth"), det.get("profitGrowth")
    if truthy(rg) or truthy(pg):
        def g(label, x):
            return h("span", None, label,
                     h("span", {"color": C.forest if x > 0 else C.vermillion, "fontWeight": 700},
                       ("+" if x > 0 else "") + js_string(x) + "%"))
        growth = h("div", {"display": "flex", "gap": 14, "marginTop": 8, "fontSize": 10, "fontFamily": F_MONO,
                           "color": C.inkD}, g("Δ DT YoY: ", rg), g("Δ LN YoY: ", pg))
    return h("div", {"marginBottom": 14},
             _label("KẾ HOẠCH 2026 (AGM)", C.inkM, 8),
             h("table", {"width": "100%", "borderCollapse": "collapse", "fontSize": 11, "fontFamily": F_NUM},
               h("thead", None, h("tr", {"borderBottom": "1px solid " + C.rule},
                                  th("METRIC", "left"), th("2025 ACTUAL", "right"), th("2026 PLAN", "right"),
                                  th("Q1/26 ACTUAL", "right"), th("%KH", "right"))),
               h("tbody", None, *rows)),
             growth)


def _dgc_block(det, lv, tk):
    q1 = det.get("q1_26")
    if not (truthy(q1) and truthy(q1.get("profit")) and truthy(q1.get("prevProfit"))):
        return None
    if lv:
        return lv.dgc_block(tk, det)
    cash = det.get("cash")
    return h("div", {"marginBottom": 14, "padding": "12px 14px", "background": C.vermillion + "10",
                     "border": "1px solid " + C.vermillion + "40"},
             _label("Q1/2026 ACTUAL — KEY FINANCIAL", C.vermillion, 6),
             h("div", {"display": "flex", "gap": 14, "flexWrap": "wrap"},
               Stat("DOANH THU", to_locale(q1.get("rev_b"), "en") + " tỷ", sub="−24% YoY", color=C.vermillion),
               Stat("LNST HỢP NHẤT", js_string(q1["profit"]) + " tỷ",
                    sub="vs Q1/25: %s (-49%%)" % js_string(q1["prevProfit"]), color=C.vermillion),
               Stat("CASH POSITION", to_fixed(cash / 1000, 1) + "K tỷ", sub="62% tổng tài sản", color=C.gold)
               if truthy(cash) else None))


def _holdings(det, lv, tk):
    items = lv.holdings(tk, det) if lv else det.get("holdings")
    if not (items and len(items) > 0):
        return None
    rows = []
    for i, hh in enumerate(items):
        rows.append(h("div", {"display": "flex", "justifyContent": "space-between", "padding": "6px 0",
                              "borderBottom": _rule50() if i < len(items) - 1 else "none", "fontSize": 11},
                      h("span", {"color": C.ink, "fontFamily": F_NUM, "fontWeight": 600}, hh["name"]),
                      h("span", {"color": C.inkD, "fontFamily": F_MONO}, hh["stake"], " ",
                        h("span", {"color": C.inkM}, "· ", hh["value"]), hh.get("_mark"))))
    return h("div", {"marginBottom": 14},
             _label("HOLDINGS / SUBSIDIARIES", C.inkM, 8, extra=lv.holdings_mark(tk) if lv else None),
             *rows)


def _stats_row(det, fl, lv, tk):
    if lv:
        return lv.stats_row(tk, det, fl)
    cp, cafef = det.get("currentPrice"), det.get("cafefPx")
    mcap, sh, after = det.get("mcap_b"), det.get("sharesOut"), det.get("afterCapInc_b")
    return h("div", {"display": "flex", "flexWrap": "wrap", "gap": 14, "padding": "14px 0",
                     "borderTop": "1px solid " + C.rule, "borderBottom": "1px solid " + C.rule, "marginBottom": 14},
             Stat("GIÁ HIỆN TẠI", to_locale(cp, "en") if truthy(cp) else "—", sub=fl["date"] if fl else "",
                  color=C.gold, big=True),
             Stat("CAFEF UPDATE", to_locale(cafef, "en"), sub="04-08/05/2026", color=C.ink2)
             if truthy(cafef) and cafef != cp else None,
             Stat("VỐN HÓA", to_fixed(mcap / 1000, 1) + "K tỷ", sub=(to_fixed(sh, 0) + "M cp") if truthy(sh) else "")
             if truthy(mcap) else None,
             Stat("POST-DILUTION", to_fixed(after / 1000, 1) + "K tỷ", sub="sau bonus + ESOP")
             if truthy(after) else None)


def ticker_card(det, fl, tk, group, lv=None, **kw):
    gc = group["color"]
    story = lv.text(tk, "story", det.get("story")) if lv else det.get("story")
    risk = lv.text(tk, "risk", det.get("risk")) if lv else det.get("risk")
    vtw = det.get("valueTrapWatch")
    left = Card(
        h("div", {"marginBottom": 14},
          h("div", {"fontSize": 9, "letterSpacing": ".2em", "color": C.inkM, "fontFamily": F_MONO, "marginBottom": 4},
            "HỒ SƠ DOANH NGHIỆP"),
          h("div", {"fontSize": 22, "fontFamily": F_DISPLAY, "fontWeight": 700, "color": C.ink, "lineHeight": 1.2},
            lv.name(tk, det) if lv else det["name"]),
          h("div", {"fontSize": 11, "color": C.inkD, "marginTop": 4, "fontFamily": F_MONO, "letterSpacing": ".05em"},
            tk, " · ", lv.sector(tk, det) if lv else det["sector"], " · Chaebol: ",
            h("span", {"color": gc}, det["chaebol"]), lv.v21() if lv else None)),
        _stats_row(det, fl, lv, tk),
        _plan_table(det, lv, tk),
        _dgc_block(det, lv, tk),
        _holdings(det, lv, tk),
        h("div", {"marginBottom": 14},
          _label("★ CÂU CHUYỆN — POLITICAL × BUSINESS ANGLE", C.gold, 8),
          h("div", {"fontSize": 12, "fontFamily": F_SERIF, "color": C.ink, "lineHeight": 1.85}, *story)
          if lv else h("div", {"fontSize": 12, "fontFamily": F_SERIF, "color": C.ink, "lineHeight": 1.85}, story)),
        h("div", {"padding": "12px 14px", "background": C.vermillion + "15", "borderLeft": "3px solid " + C.vermillion,
                  "fontSize": 11, "fontFamily": F_SERIF, "color": C.ink, "lineHeight": 1.75},
          h("strong", {"color": C.vermillion, "fontFamily": F_MONO, "fontSize": 9, "letterSpacing": ".18em"},
            "RỦI RO · "),
          *(risk if lv else [risk])),
        h("div", {"marginTop": 10, "padding": "10px 14px", "background": C.ochre + "15",
                  "borderLeft": "3px solid " + C.ochre, "fontSize": 11, "fontFamily": F_SERIF, "color": C.ink,
                  "lineHeight": 1.7},
          h("strong", {"color": C.ochre, "fontFamily": F_MONO, "fontSize": 9, "letterSpacing": ".18em"},
            "VALUE TRAP WATCH · "),
          *(lv.value_trap(tk, vtw) if lv else [vtw])) if truthy(vtw) else None,
        accent=gc, padding=20)
    right = [
        (lv.flow_signal(tk, fl) if lv else FlowSignal(fl)) if fl else None,
        Card(_label("★ ĐỌC FLOW — TOÀN VŨ × PILLAR IV (FIINTRADE → NGƯỜIQUANSÁT)", C.gold, 10),
             h("div", {"fontSize": 11, "fontFamily": F_SERIF, "color": C.ink, "lineHeight": 1.8},
               det.get("flowReading") or "N/A", lv.v21_flow_tier(fl) if lv else None),
             accent=gc),
        h("div", {"marginTop": 10},
          Card(_label("P-NEXT · CỤM TIẾP THEO", C.ink2, 10),
               h("div", {"fontSize": 11, "fontFamily": F_SERIF, "color": C.ink, "lineHeight": 1.8},
                 det["pnext"], lv.v21u() if lv else None, lv.pnext_status(tk) if lv else None),
               accent=C.ink2)) if truthy(det.get("pnext")) else None,
        h("div", {"marginTop": 10},
          # live: dấu V21 chỉ ở dòng "Hiện tại" — đặt cạnh nhãn này thì marker pha (top −22) đè lên
          Card(_label("◐ HOWARD MARKS PHASE", C.inkM, 10),
               *phase_bar(fl["perf60"], fl["sig"], mark=lv.v21() if lv else None,
                          perf_mark=lv.v21_flow_tier(fl) if lv else None))) if fl else None,
    ]
    return h("div", {"display": "grid", "gridTemplateColumns": "1.3fr 1fr", "gap": 14},
             h("div", None, left), h("div", None, *right), key="card:" + tk, **kw)


def placeholder_card(tk, lv=None, **kw):
    return Card(h("div", {"textAlign": "center", "padding": 30, "color": C.inkD, "fontStyle": "italic"},
                  PLACEHOLDER[0], tk, PLACEHOLDER[1]),
                lv.placeholder_extra(tk) if lv else None, key="card:" + tk, **kw)


# ── ChaebolDeepDive (SRC 5901–5986) ─────────────────────────────────────────


def group_header(group, lv=None):
    gc = group["color"]
    political = lv.group_text("political", group["political"]) if lv else [group["political"]]
    thesis = lv.group_text("coreThesis", group["coreThesis"]) if lv else [group["coreThesis"]]
    return Section(
        group["name"] + " · DEEP DIVE",
        Card(
            h("div", {"display": "flex", "justifyContent": "space-between", "alignItems": "baseline", "marginBottom": 14,
                      "flexWrap": "wrap", "gap": 14},
              h("div", None,
                h("div", {"fontSize": 24, "color": gc, "fontFamily": F_DISPLAY, "fontWeight": 700,
                          "fontStyle": "italic", "marginBottom": 4}, group["head"]),
                Pill(group["status"], group["statusColor"]), lv.v21() if lv else None),
              h("div", {"fontSize": 11, "color": C.inkD, "fontFamily": F_MONO, "letterSpacing": ".05em",
                        "maxWidth": 540, "lineHeight": 1.7, "textAlign": "right"}, *political)),
            h("div", {"fontSize": 12, "fontFamily": F_SERIF, "color": C.ink, "lineHeight": 1.85, "padding": "12px 14px",
                      "background": C.parch + "80", "borderLeft": "3px solid " + gc},
              h("strong", {"color": gc, "fontFamily": F_MONO, "fontSize": 10, "letterSpacing": ".18em"},
                "CORE THESIS · "),
              *thesis),
            lv.group_update_box() if lv else None,
            accent=gc, padding=20),
        accent=gc, sub=lv.head_title(group["headTitle"]) if lv else group["headTitle"], key="grp-head")


def ticker_section(group, v21, lv=None):
    gc = group["color"]
    key = state_key(group["id"])
    flows = v21.get("FLOW") or {}
    details = v21.get("TICKER_DETAIL") or {}
    buttons, panels = [], []
    for t in group["tickers"]:
        fl = flows.get(t)
        line2 = lv.button_line(t, fl, key) if lv else None
        if not lv and fl:
            line2 = h("div", {"fontSize": 10, "fontWeight": 400, "marginTop": 3, "opacity": 0.8},
                      to_locale(fl["px"], "en"), " · ",
                      h("span", {"color": C.forest if fl["perf60"] >= 0 else C.vermillion},
                        sign_fixed(fl["perf60"], 1), "%", var=[{"if": {key: t}, "s": {"color": C.bg}}]))
        buttons.append(h("button", {"padding": "12px 18px", "cursor": "pointer", "background": C.paper, "color": C.ink,
                                    "border": "1px solid " + C.rule, "fontFamily": F_NUM, "fontSize": 14,
                                    "fontWeight": 700, "letterSpacing": ".05em", "transition": "all 0.2s"},
                         h("div", None, t), line2,
                         on={"set": {key: t}},
                         var=[{"if": {key: t}, "s": {"background": gc, "color": C.bg, "border": "1px solid " + gc}}],
                         key="grp-btn:" + t))
        det = details.get(t)
        if det:
            panels.append(ticker_card(det, fl, t, group, lv, if_={key: t}))
        else:
            panels.append(placeholder_card(t, lv, if_={key: t}))
        if lv:
            lv.pattern_q(panels[-1], t)      # mã ngoài 30 mã Toàn Vũ: 'Pattern X?'
            lv.codong_link(panels[-1], t)    # nút sang tab codong v2 (mã trong vũ trụ 109)
    return Section("◑ Cổ phiếu trong nhóm",
                   h("div", {"display": "flex", "gap": 10, "marginBottom": 18, "flexWrap": "wrap"}, *buttons,
                     key="grp-buttons"),
                   *panels, accent=gc, key="grp-tickers")


def events_section(group, lv=None):
    gc = group["color"]
    evts = lv.events(group) if lv else [(e["date"], [e["evt"]]) for e in group["keyEvents"]]
    rows = []
    for i, (date, evt) in enumerate(evts):
        rows.append(h("div", {"display": "flex", "gap": 14, "padding": "12px 0",
                              "borderBottom": _rule50() if i < len(evts) - 1 else "none"},
                      h("div", {"fontSize": 10, "color": gc, "fontFamily": F_NUM, "letterSpacing": ".05em",
                                "fontWeight": 700, "width": 130, "flexShrink": 0}, date),
                      h("div", {"fontSize": 12, "fontFamily": F_SERIF, "color": C.ink, "lineHeight": 1.7}, *evt)))
    return Section(lv.events_title() if lv else EVENTS_TITLE, h("div", None, *rows), accent=gc, key="grp-events")


def _group(v21, gid):
    for g in v21.get("CHAEBOL_GROUPS") or []:
        if isinstance(g, dict) and g.get("id") == gid:
            return g
    raise ValueError("v21_const thiếu CHAEBOL_GROUPS[%s] — cần trích lại v21_const.json" % gid)


def build_group(ctx, gid):
    v21 = ctx.v21 or {}
    group = _group(v21, gid)
    lv = None
    if ctx.live:
        import chaebol_map_tab_groups_live as live   # nhập trễ: mode v21 không cần lớp dữ liệu
        lv = live.LiveGroup(ctx, group, v21)
    sections = []
    if gid == "tuanmuot":
        eco = v21.get("TUAN_MUOT_ECOSYSTEM")
        if not eco:
            raise ValueError("v21_const thiếu TUAN_MUOT_ECOSYSTEM")
        sections.append(Section(ECO_TITLE, eco_map(eco, lv), accent=group["color"], sub=ECO_SUB, key="eco"))
    sections.append(group_header(group, lv))
    sections.append(ticker_section(group, v21, lv))
    sections.append(events_section(group, lv))
    tickers = [str(t) for t in group["tickers"]]
    res = {"root": h("div", None, *sections, key="groups:" + gid),
           "states": [{"key": state_key(gid), "default": tickers[0], "options": tickers}]}
    if lv:
        res["csv"] = lv.csv_rows()
        lv.finish()
    return res


def build_tuanmuot(ctx):
    return build_group(ctx, "tuanmuot")


def build_sovico(ctx):
    return build_group(ctx, "sovico")


def build_phuong(ctx):
    return build_group(ctx, "phuong")


def build_bauthuy(ctx):
    return build_group(ctx, "bauthuy")


def build_eliminated(ctx):
    return build_group(ctx, "eliminated")
