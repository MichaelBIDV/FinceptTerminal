#!/usr/bin/env python3
"""
chaebol_map_tab_overview — tab `overview` (00 · TỔNG QUAN) và `chaebol` (01 · CHAEBOL MAP) của module chaebol_map.

Nguồn: SRC 5173–5728 (OverviewTab, ChaebolMapEnrichment, ChaebolMapTab); đặc tả chaebol_map_spec/page_p4_overview_map.md.
TuanMuotEcosystemMap (SRC 5729+) KHÔNG thuộc tab này (render ở tab 02).

Hai chế độ, CHUNG builder (DESIGN §0.7):
  - v21 : chép nguyên văn JSX (chữ, style, số theo luật JS), as_intended (crimson/emerald có màu) — so pixel với ref.
  - live: cùng cây + lớp cập nhật ở chaebol_map_tab_overview_live (số sống vc_lk có nhãn bậc, câu viết lại từ dossier
          cap_nhat_<ngày>.overview.json, nhận định V21 giữ nguyên + dấu V21·12/05, claim chấm lại bằng Pill trạng thái).
State: map.axis (ALL NQ79 NQ68 SPECIAL) · map.tier (ALL Top Mid Distress Special) — ChaebolMapEnrichment.
"""
from __future__ import annotations

from chaebol_map_dom import C, F_DISPLAY, F_MONO, F_NUM, F_SERIF, alpha, h, to_fixed
from chaebol_map_shell import Card, Section
from chaebol_map_tab_overview_map import seg

try:  # lớp live tách tệp (luật repo ≤ ~800 dòng/tệp); thiếu → live vẫn dựng như v21 + cảnh báo
    import chaebol_map_tab_overview_live as _live_mod
except ImportError:  # pragma: no cover
    _live_mod = None

# ── Hằng JSX (chữ tĩnh) ─────────────────────────────────────────────────────

PARCH80 = alpha(C.parch, "80")


def _v(ctx, name, default=None):
    v = (ctx.v21 or {}).get(name) if ctx is not None else None
    if v is None:
        if ctx is not None:
            ctx.warn("v21_const thiếu %s" % name)
        return default
    return v


def _live(ctx):
    """Đối tượng lớp live (None ở mode v21 hoặc khi thiếu module)."""
    if not getattr(ctx, "live", False):
        return None
    if _live_mod is None:
        ctx.warn("thiếu chaebol_map_tab_overview_live.py — live dựng như bản V21")
        return None
    return _live_mod.Live(ctx)


def _hook(L, name, *args, default=None):
    """Gọi L.<name>(*args) nếu có lớp live; lỗi → cảnh báo + mặc định (không làm hỏng tab)."""
    if L is None:
        return default
    try:
        return getattr(L, name)(*args)
    except Exception as exc:  # noqa: BLE001 — lớp dữ liệu không được làm hỏng build
        L.ctx.warn("live.%s lỗi: %s: %s" % (name, type(exc).__name__, exc))
        return default


# ════════════════════════════════════════════════════════════════════════════
# 00 · TỔNG QUAN (OverviewTab, SRC 5173–5324)
# ════════════════════════════════════════════════════════════════════════════

_TREND_SPAN = {"color": C.gold, "fontWeight": 700}


def _thesis(L):
    """Section A — ✦ Thesis V21 (5177–5191)."""
    trend1 = ["① Eliminated wave —", " các nhóm thân hữu cũ bị \"nắn gân\" công khai. ",
              h("span", {"color": C.vermillion},
                "DGC ngày 08/05/2026" if L else "DGC ngày HÔM NAY 8/5/2026"),
              " miễn nhiệm 3 thành viên HĐQT (CT Đào Hữu Huyền + Phó CT con trai + 1 thành viên khác — tất cả đã bị "
              "Bộ Công an khởi tố). Cộng với CTD post-Bolat, PC1 ngành tài nguyên rủi ro → cluster bị \"thanh lọc\"."]
    trend2 = ["② Ascending new chaebol —", " nhóm tỷ phú \"thế hệ mới\" lên ngôi: ",
              h("span", {"color": C.forest}, "Nguyễn Văn Tuấn (Tuấn mượt)"),
              " với GEX +83% 60d, GEE +229%, mua 10% Eximbank, khai trương Fairmont Hà Nội ngay 27-29 Lý Thái Tổ Hoàn "
              "Kiếm = symbolic seat of power."]
    trend3 = ["③ Stable holdings —", " các nhóm \"an phận thủ thường\" theo luật mới: ",
              h("span", {"color": C.ink2}, "bà Thảo (Sovico)"), " giảm sở hữu HDB/VJC theo Luật TCTD 2024; ",
              h("span", {"color": C.ink2}, "bà Phượng (Vietcap)"),
              " mở rộng Singapore tránh xung đột chính trị nội địa."]
    trends = []
    for i, t in enumerate((trend1, trend2, trend3), 1):
        extra = _hook(L, "trend_extra", i, default=None)
        trends.append(h("div", {"marginBottom": 10}, h("span", _TREND_SPAN, t[0]), *t[1:],
                        _hook(L, "tag", ("v21U", "v21T2", "v21U")[i - 1]), extra))
    body = h("div", {"fontSize": 14, "lineHeight": 1.85, "fontFamily": F_SERIF, "color": C.ink, "fontWeight": 400},
             h("strong", {"color": C.gold, "fontFamily": F_DISPLAY, "fontSize": 18, "fontStyle": "italic"},
               "Luận điểm trung tâm:"),
             " Tháng 4-5/2026 đánh dấu một ", h("em", {"color": C.bone}, "structural reshuffle"),
             " trong bản đồ thân hữu Việt Nam dưới triều Tổng BT Tô Lâm. Ba xu hướng đồng thời:",
             _hook(L, "tag", "v21U"),
             h("div", {"marginTop": 14, "paddingLeft": 20, "fontSize": 13}, *trends),
             h("div", {"marginTop": 18, "padding": 14, "background": PARCH80, "borderLeft": "2px solid " + C.gold,
                       "fontSize": 12, "fontStyle": "italic", "color": C.inkD},
               h("strong", {"color": C.gold, "fontStyle": "normal"}, "Tier 2 thinking (Howard Marks):"),
               " Sell-side và đám đông chỉ thấy giá. Người am hiểu chính trị thấy chu kỳ thân hữu. ",
               h("em", None, "\"Cùng sự kiện AGM, nhóm A là tin tốt (Tuấn quay lại HĐQT GEX), nhóm B là tin xấu (DGC "
                             "thay 3 HĐQT do bị khởi tố).\""),
               " Phân biệt được — đó mới là alpha.", _hook(L, "tag", "v21U")),
             _hook(L, "thesis_footer", default=None))
    sub = _hook(L, "thesis_sub", default=None) or "Tháng 5, 2026"
    return Section("✦ Thesis V21 — Chaebol Reshuffle Hypothesis", Card(body, accent=C.gold, padding=24), sub=sub,
                   key="ov.thesis")


_UL = {"margin": 0, "paddingLeft": 18, "fontSize": 12, "lineHeight": 1.7, "color": C.ink, "fontFamily": F_SERIF}


def _bridge(L):
    """Section B — 🜲 Bridge V20 → V21 (5194–5221); bản lịch sử, live giữ nguyên + dấu V21 cho stance."""
    lab = {"fontSize": 10, "letterSpacing": ".2em", "color": C.inkM, "fontFamily": F_MONO, "marginBottom": 10}
    v20 = ["Master plan tích sản MSN ALL-IN (84,400 cp)", "Chiếu phụ VCB (49,100 cp), FPT (19,400 cp)",
           "Methodology Toàn Vũ × Phú SSI × Capital IQ", "VIC reflexivity case study T3/2025 → T4/2026",
           "22 tabs · 7 BCTN MSN · 7 Phase ribbon", "Risk events: Quang ý chí, NVL game nợ, VCB NQ79, FPT recovery"]
    g = {"color": C.gold}
    v21 = [[h("strong", g, "4 nhóm chaebol thân hữu"), " phân tích chính trị"],
           [h("strong", g, "VN30 Screener"), " 45 mã + flow signals 60d"],
           ["Pillar IV flow: FiinTrade Phân Loại NĐT (verified ≤08/05/2026) + NgườiQuanSát.vn (forward ≥09/05/2026, "
            "FREE)", _hook(L, "bridge_flow_note", default=None)],
           ["Deep-dive: GEX, GEE, GEL, VIX (Tuấn mượt)"], ["Deep-dive: VJC + HDB (Sovico-Thảo)"],
           ["Deep-dive: VCI + IDP (Phượng-Phoenix)"],
           [h("strong", {"color": C.vermillion}, "Eliminated:"), " DGC, PC1, CTD analysis"],
           ["Portfolio actions: rotate FPT/VCB → GEX/HPG/BSR", _hook(L, "tag", "v21")]]
    return Section(
        "🜲 Bridge V20 → V21 — Có gì mới?",
        h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 14},
          Card(h("div", lab, "V20 (HIỆN TẠI)", _hook(L, "tag", "v21")),     # tiêu đề cột: chỉ dấu V21, không nhãn bậc
               h("ul", _UL, *[h("li", None, x, _hook(L, "tag", "E") if " cp)" in x else None) for x in v20]),
               accent=C.inkD),
          Card(h("div", {**lab, "color": C.gold}, "V21 (★ MỚI)", _hook(L, "tag", "v21")),
               h("ul", _UL, *[h("li", None, *x) for x in v21]), accent=C.gold)),
        _hook(L, "bridge_footer", default=None),
        accent=C.ink2, key="ov.bridge")


_TH = {"padding": "6px 4px", "color": C.inkM, "fontSize": 9, "letterSpacing": ".1em"}
_TD = {"padding": "6px 4px"}


def _flow_table(rows, title, color, nn_head, dist):
    """Bảng ★ TOP NN ACCUMULATION / ⚠ DISTRIBUTION (5227–5287). rows: dict tk, nn, perf, n (+ tùy chọn *_node)."""
    head = h("tr", {"borderBottom": "1px solid " + C.rule},
             h("th", {"textAlign": "left", **_TH}, "TICKER"), h("th", {"textAlign": "right", **_TH}, nn_head),
             h("th", {"textAlign": "right", **_TH}, "Δ60d"), h("th", {"textAlign": "left", **_TH}, "NOTE"))
    body = []
    for r in rows:
        tk_color = (C.vermillion if r["tk"] == "DGC" else C.gold) if dist else C.gold
        if "nn_node" in r:
            nn_cell = r["nn_node"]
        else:  # JSX `+{r.nn.toFixed(1)}` = 2 text node; bảng phân phối `{r.nn.toFixed(1)}` = 1
            nn_cell = [to_fixed(r["nn"], 1)] if dist else ["+", to_fixed(r["nn"], 1)]
        perf = r.get("perf")
        if "perf_node" in r:
            perf_cell, perf_color = r["perf_node"], (C.forest if (perf is not None and perf > 0) else C.vermillion)
        else:  # `{r.perf>0?'+':''}{r.perf.toFixed(1)}%` = 3 text node
            perf_cell = ["+" if perf > 0 else "", to_fixed(perf, 1), "%"]
            perf_color = C.forest if perf > 0 else C.vermillion
        body.append(h("tr", {"borderBottom": "1px solid " + alpha(C.rule, "50")},
                      h("td", {**_TD, "color": tk_color, "fontWeight": 700}, r["tk"]),
                      seg(h("td", {**_TD, "textAlign": "right", "color": C.vermillion if dist else C.forest,
                                   "fontWeight": 600}), nn_cell),
                      seg(h("td", {**_TD, "textAlign": "right", "color": perf_color}), perf_cell),
                      h("td", {**_TD, "color": C.inkD, "fontSize": 10, "fontFamily": F_SERIF}, r["n"])))
    return Card(h("div", {"fontSize": 11, "letterSpacing": ".2em", "color": color, "fontFamily": F_MONO,
                          "marginBottom": 12, "fontWeight": 700}, title),
                h("table", {"width": "100%", "borderCollapse": "collapse", "fontSize": 11, "fontFamily": F_NUM},
                  h("thead", None, head), h("tbody", None, *body)),
                accent=color)


def _flows(ctx, L):
    """Section C — ✪ Top Pillar IV Flow Insights (5224–5292)."""
    acc = _v(ctx, "OverviewTab.jsx@L5236", [])
    dist = _v(ctx, "OverviewTab.jsx@L5265", [])
    title, sub = "✪ Top Pillar IV Flow Insights — 60 ngày tới 08/05/2026 (FiinTrade verified)", None
    live = _hook(L, "flow_tables", acc, dist, default=None)
    if live:
        acc, dist, title, sub = live["acc"], live["dist"], live["title"], live.get("sub")
    # live: cụm có mã ngoài 30 mã Toàn Vũ → 'Pattern A?/B?' (h() gộp chuỗi kề → v21 vẫn MỘT text node như JSX)
    ca, cb = ["ACB", "TPB", "SSI", "HCM"], ["HPG", "MSN", "GMD"]
    pa = _hook(L, "pattern_q", "Pattern A", ca, default=None) or "Pattern A"
    pb = _hook(L, "pattern_q", "Pattern B", cb, default=None) or "Pattern B"
    callout = h("div", {"marginTop": 14, "padding": 14, "background": PARCH80, "fontSize": 11, "fontFamily": F_SERIF,
                        "color": C.ink, "lineHeight": 1.7, "fontStyle": "italic", "borderLeft": "2px solid " + C.gold},
                h("strong", {"color": C.gold, "fontStyle": "normal"},
                  "Đọc 2 bảng đối lập này bằng tư duy contrarian Munger:"),
                " Đám đông cá nhân đang chase ACB/TPB/SSI/HCM (", pa, " textbook ở đỉnh) trong khi NN bán mạnh — đây "
                "là ", h("em", None, "\"distribution at euphoria\""),
                ". Ngược lại HPG, MSN, GMD: cá nhân SELL trong khi NN BUY mạnh = \"smart money quietly accumulating while "
                "crowd capitulates\" = ", pb, " textbook ở đáy. Đây không phải coincidence — đây là ",
                h("em", None, "structural rotation cycle"), " đang diễn ra song song với chaebol reshuffle.",
                _hook(L, "tag", "v21"), _hook(L, "pattern_note", ca + cb, default=None),
                _hook(L, "flow_callout_extra", default=None))
    return Section(title,
                   h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 14},
                     _flow_table(acc, "★ TOP NN ACCUMULATION (60D)", C.forest, "NN +M cp", False),
                     _flow_table(dist, "⚠ TOP NN DISTRIBUTION (60D)", C.vermillion, "NN -M cp", True)),
                   callout, accent=C.gold, sub=sub, key="ov.flows")


def _phases(ctx, L):
    """Section D — ◐ Howard Marks Phase — 45 mã VN30+ matrix (5295–5321); pha = stance V21, không chấm lại."""
    cols = []
    for p in _v(ctx, "OverviewTab.jsx@L5297", []):
        pc = p["color"]
        chips = [h("span", {"fontSize": 9, "padding": "2px 5px", "background": alpha(pc, "15"),
                            "border": "1px solid " + alpha(pc, "40"), "color": C.ink, "fontFamily": F_NUM,
                            "fontWeight": 600}, t["tk"]) for t in p["tk"]]
        cols.append(h("div", {"background": C.paper, "border": "1px solid " + C.rule, "borderTop": "3px solid " + pc,
                              "padding": 10},
                      h("div", {"fontSize": 9, "letterSpacing": ".18em", "color": pc, "fontFamily": F_MONO,
                                "marginBottom": 4, "fontWeight": 700}, p["phase"]),
                      h("div", {"fontSize": 10, "color": C.ink, "marginBottom": 8, "fontFamily": F_DISPLAY,
                                "fontWeight": 600}, p["label"]),
                      h("div", {"display": "flex", "flexWrap": "wrap", "gap": 3, "marginBottom": 8}, *chips),
                      h("div", {"fontSize": 9, "color": C.inkM, "fontFamily": F_MONO, "lineHeight": 1.5},
                        _hook(L, "phase_note", p, default=None) or p["note"], _hook(L, "tag", "v21E"))))
    return Section("◐ Howard Marks Phase — 45 mã VN30+ matrix",
                   h("div", {"display": "grid", "gridTemplateColumns": "repeat(6, 1fr)", "gap": 8, "fontSize": 10},
                     *cols),
                   _hook(L, "phase_footer", default=None), accent=C.ink2, key="ov.phase")


def build_overview(ctx):
    """Tab 00 · TỔNG QUAN: 4 Section tĩnh, không state."""
    L = _live(ctx)
    return {"root": h("div", None, _thesis(L), _bridge(L), _flows(ctx, L), _phases(ctx, L), key="tab:overview")}


# ════════════════════════════════════════════════════════════════════════════
# 01 · CHAEBOL MAP (ChaebolMapTab 5481–5723 + ChaebolMapEnrichment 5330–5478)
# ════════════════════════════════════════════════════════════════════════════

from chaebol_map_tab_overview_map import axis_options, build_chaebol_sections, tier_options  # noqa: E402


def build_chaebol(ctx):
    """Tab 01 · CHAEBOL MAP: 9 Section; state map.axis × map.tier (bảng 24 thực thể + 'Showing n/24')."""
    L = _live(ctx)
    return {"root": h("div", None, *build_chaebol_sections(ctx, L), key="tab:chaebol"),
            "states": [{"key": "map.axis", "default": "ALL", "options": axis_options(ctx)},
                       {"key": "map.tier", "default": "ALL", "options": tier_options(ctx)}]}
