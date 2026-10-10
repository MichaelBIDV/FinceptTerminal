#!/usr/bin/env python3
"""
chaebol_map_tab_portfolio — tab "08 · DANH MỤC" (PortfolioActionTab, SRC 6450–6664) và
"★ 13 · ACTION PORTFOLIO 25" (ActionPortfolio25Tab, SRC 6864–6921) của module chaebol_map.

Đặc tả: chaebol_map_spec/page_p6_portfolio_research.md §4 (tab 08) + page_p7a_claims54_catalyst_port25.md §4 (tab 13).
Hợp đồng: DESIGN.md; API: api_python.md. Mode v21 = tái tạo nguyên văn trang gốc (chỉ hằng ctx.v21, as_intended:
C.emerald/C.crimson có màu, nút thừa kế font). Mode live = cùng cây + lớp cập nhật ở chaebol_map_tab_portfolio_live
(số sống có nhãn bậc, câu viết lại theo dossier, stance V21 giữ nguyên + dấu V21·12/05, khối hai danh mục hiện hành).

Mọi số hiển thị đi qua luật số JS (to_fixed / to_locale / js_sum). Không đọc SRC, không mạng, không ghi tệp.
"""
from __future__ import annotations

from chaebol_map_dom import C, F_DISPLAY, F_MONO, F_NUM, F_SERIF, h, js_sum, tier, to_fixed, to_locale, v21_mark
from chaebol_map_shell import FLOW_HEAD_V21, Card, FlowSignal, Pill, Section, Stat

__all__ = ["build_portfolio", "build_portfolio25", "P25_CATS"]

P25_CATS = ("ALL", "Core", "Growth", "Tactical", "Avoid")        # ActionPortfolio25Tab.cats (SRC 6866)
# as_intended (DESIGN §0.1): C.emerald / C.crimson có giá trị; bản gốc vẽ undefined → fallback.
P25_CAT_COLOR = {"Core": C.emerald, "Growth": C.gold, "Tactical": "#a78bfa", "Avoid": C.crimson}
P25_COL_MAP = {"emerald": C.emerald, "gold": C.gold, "crimson": C.crimson, "amber": "#fbbf24"}


def _live(ctx):
    """Lớp live (None ở mode v21 hoặc khi module live lỗi nhập → tab vẫn dựng bản V21 + cảnh báo)."""
    if not getattr(ctx, "live", False):
        return None
    try:
        import chaebol_map_tab_portfolio_live as L
    except Exception as exc:  # module live hỏng không được làm mất tab
        ctx.warn("chaebol_map_tab_portfolio_live nhập lỗi: %s: %s — chỉ dựng bản V21" % (type(exc).__name__, exc))
        return None
    return L.Live(ctx)


def _sgn(v):
    return "+" if v >= 0 else ""


def _pn(v):
    return C.forest if v >= 0 else C.vermillion


# ── Tab 08 · Section A: danh mục hiện tại (V21) ─────────────────────────────


def _kpi_label(text):
    return h("div", {"fontSize": 9, "letterSpacing": ".18em", "color": C.inkM, "fontFamily": F_MONO,
                     "marginBottom": 5}, text)


def _kpi_value(color, *kids):
    return h("div", {"fontSize": 22, "fontWeight": 600, "color": color, "fontFamily": F_NUM}, *kids)


def _intro_a(lv):
    strong = lambda t: h("strong", {"color": C.ink}, t)  # noqa: E731
    return h("div", {"fontSize": 13, "fontFamily": F_SERIF, "color": C.inkD, "lineHeight": 1.7, "fontStyle": "italic",
                     "marginBottom": 18, "padding": "14px 18px", "background": C.parch,
                     "borderLeft": "3px solid " + C.gold},
             "Anh đang nắm 3 mã từ V20: ", strong("VCB"), " (NQ79 macro hedge), ", strong("FPT"), " (AI tech), ",
             strong("MSN"),
             " (consumer + MSR supercycle). Tình huống hiện tại: MSN ★ HOLD vững (NN flip first time 4y), VCB & FPT "
             "đang phải re-evaluate vì NN/Tổ chức rút mạnh 60 phiên gần đây, đặc biệt FPT đang phase Capitulation cần "
             "lên kế hoạch exit có kỷ luật.",
             v21_mark(), lv and lv.intro_a_note())


def _summary(cur, lv):
    total_cost = js_sum(p["position"] * p["costAvg"] for p in cur)
    total_mv = js_sum(p["mktValue"] for p in cur)
    pnl = total_mv - total_cost
    pnl_pct = (pnl / total_cost) * 100
    e = tier("E")                                    # số dẫn xuất từ vị thế V21 (UNVERIFIED) — p6 §7.1
    grid = h("div", {"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)", "gap": 12, "marginBottom": 18},
             Card(_kpi_label("TỔNG MV"), _kpi_value(C.ink, to_fixed(total_mv / 1e9, 2), " tỷ", e)),
             Card(_kpi_label("TỔNG VỐN GỐC"), _kpi_value(C.ink, to_fixed(total_cost / 1e9, 2), " tỷ", tier("U"))),
             Card(_kpi_label("P&L UNREALIZED"),
                  _kpi_value(_pn(pnl), _sgn(pnl), to_fixed(pnl / 1e9, 2), " tỷ", e),
                  h("div", {"fontSize": 10, "color": _pn(pnl), "fontFamily": F_NUM, "marginTop": 3},
                    _sgn(pnl_pct), to_fixed(pnl_pct, 1), "%", e),
                  accent=C.forest if pnl >= 0 else C.vermillion),
             Card(_kpi_label("POSITIONS"), _kpi_value(C.ink, len(cur), v21_mark()),
                  h("div", {"fontSize": 10, "color": C.inkD, "fontFamily": F_MONO, "marginTop": 3},
                    "⚠ Concentration risk" if len(cur) == 3 else "Diversified")),
             key="p08.kpi")
    return grid, total_mv, total_cost


def _position(p, flow, total_mv, lv):
    tk = p["tk"]
    pnl_pos = (p["mktPrice"] - p["costAvg"]) * p["position"]
    pnl_pct = ((p["mktPrice"] - p["costAvg"]) / p["costAvg"]) * 100
    fl = flow.get(tk)
    accent = C.forest if tk == "MSN" else (C.vermillion if tk == "FPT" else C.ochre)
    e, u, fd = tier("E"), tier("U"), (fl or {}).get("date")
    head = h("div", {"display": "grid", "gridTemplateColumns": "auto 1fr auto", "gap": 18, "alignItems": "center",
                     "marginBottom": 14},
             h("div", None,
               h("div", {"fontSize": 36, "fontFamily": F_DISPLAY, "fontWeight": 700, "color": accent,
                         "letterSpacing": "-.02em", "lineHeight": 1}, tk),
               h("div", {"fontSize": 9, "color": C.inkM, "letterSpacing": ".18em", "fontFamily": F_MONO, "marginTop": 4},
                 to_locale(p["position"], "en"), " cp", u)),
             h("div", None,
               h("div", {"fontSize": 11, "color": C.inkD, "fontFamily": F_SERIF, "lineHeight": 1.6, "fontStyle": "italic"},
                 p["thesis"], v21_mark(), lv and lv.thesis_note("current", tk))),
             h("div", {"textAlign": "right"},
               h("div", {"fontSize": 9, "letterSpacing": ".18em", "color": C.inkM, "fontFamily": F_MONO}, "P&L"),
               h("div", {"fontSize": 22, "fontWeight": 700, "color": _pn(pnl_pos), "fontFamily": F_NUM},
                 _sgn(pnl_pos), to_fixed(pnl_pos / 1e6, 0), "tr", e),
               h("div", {"fontSize": 11, "color": _pn(pnl_pos), "fontFamily": F_NUM},
                 _sgn(pnl_pct), to_fixed(pnl_pct, 1), "%", e)))
    stats = h("div", {"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)", "gap": 10, "marginBottom": 14,
                      "padding": "10px 12px", "background": C.parch, "borderRadius": 2},
              Stat("GIÁ VỐN BQ", [to_locale(p["costAvg"], "en"), u]),
              Stat("GIÁ HIỆN TẠI", [to_locale(p["mktPrice"], "en"), tier("T2", fd)]),
              Stat("MARKET VALUE", [to_fixed(p["mktValue"] / 1e9, 2) + " tỷ", e]),
              Stat("% NAV", [to_fixed(p["mktValue"] / total_mv * 100, 1) + "%", e]))
    action = h("div", {"padding": "12px 14px", "background": accent + "15", "borderLeft": "3px solid " + accent,
                       "fontSize": 12, "fontFamily": F_SERIF, "color": C.ink, "lineHeight": 1.75, "marginTop": 10},
               h("strong", {"color": accent, "fontFamily": F_MONO, "fontSize": 9, "letterSpacing": ".18em"},
                 "HÀNH ĐỘNG · "),
               p["action"], v21_mark(), lv and lv.action_note(tk))
    return h("div", {"marginBottom": 14},
             Card(head, stats, lv and lv.position_live(p),
                  FlowSignal(fl, head=[FLOW_HEAD_V21, v21_mark()] if lv else FLOW_HEAD_V21,
                             tiers=_v21_flow_tiers(fl)) if fl else None,
                  lv and lv.flow_live(tk), action, accent=accent),
             key="p08.pos." + tk)


def _v21_flow_tiers(fl):
    """Mode live: số FiinTrade ≤08/05 giữ đóng băng (DESIGN §6.5); sig là stance → không nhãn. Bốn thanh kênh mang
    'T2' không ngày (ô số FlowBar rộng 80px: '-173.7M' + 'T2·07/05' tràn ô); ngày V21 nằm ở dòng tham chiếu (giá, Δ60d)."""
    d = fl.get("date")
    return {**{k: "T2" for k in ("ca60", "to60", "td60", "nn60")}, **{k: ("T2", d) for k in ("px", "perf60")}}


def section_current(pa, flow, lv):
    cur = pa.get("current") or []
    grid, total_mv, _ = _summary(cur, lv)
    sub = "As of 08/05/2026 · " + str(len(cur)) + " positions"
    return Section("Danh Mục Hiện Tại — VCB · FPT · MSN",
                   _intro_a(lv), grid, lv and lv.summary_live(cur),
                   *[_position(p, flow, total_mv, lv) for p in cur],
                   accent=C.gold, sub=[sub, v21_mark()] if lv else sub, key="p08.current")


# ── Tab 08 · Section B: khuyến nghị mua thêm (V21, stance) ──────────────────


def _intro_b():
    strong = lambda t: h("strong", {"color": C.ink}, t)  # noqa: E731
    return h("div", {"fontSize": 13, "fontFamily": F_SERIF, "color": C.inkD, "lineHeight": 1.7, "fontStyle": "italic",
                     "marginBottom": 14, "padding": "12px 16px", "background": C.forest + "10",
                     "borderLeft": "3px solid " + C.forest},
             "4 mã sau đây đáp ứng đồng thời 3 tiêu chí: ", strong("(1) Phase Howard Marks ở P2/MARKUP đầu"),
             " (chưa euphoric),", strong(" (2) Flow Pillar IV BULL"),
             " (Tổ chức hoặc NN tích lũy mạnh ≥30M cp 60d),", strong(" (3) Catalyst rõ ràng + chaebol/SOE backing"),
             ". Tổng size đề xuất 12-18% NAV chia đều theo conviction.", v21_mark())


def _flow_line(fl, lv):
    sig = fl["sig"]
    sig_c = C.forest if sig == "BULL" else (C.vermillion if sig == "BEAR" else C.ochre)
    t2 = tier("T2", fl.get("date"))
    return h("div", {"fontSize": 10, "color": C.inkD, "fontFamily": F_MONO, "marginBottom": 10, "padding": "6px 10px",
                     "background": C.parch, "borderRadius": 2, "letterSpacing": ".06em"},
             "Δ60d ", h("span", {"color": _pn(fl["perf60"]), "fontWeight": 700},
                        _sgn(fl["perf60"]), to_fixed(fl["perf60"], 1), "%", t2),
             " · SIG ", h("span", {"color": sig_c, "fontWeight": 700}, sig, v21_mark()),
             " · Tổ chức ", h("span", {"color": _pn(fl["to60"]), "fontWeight": 600},
                              _sgn(fl["to60"]), to_fixed(fl["to60"], 1), "M", t2),
             " · NN ", h("span", {"color": _pn(fl["nn60"]), "fontWeight": 600},
                         _sgn(fl["nn60"]), to_fixed(fl["nn60"], 1), "M", t2))


def _add_card(p, flow, lv):
    fl = flow.get(p["tk"])
    u, m = tier("U"), v21_mark()
    return h("div", {"marginBottom": 12},
             Card(h("div", {"display": "grid", "gridTemplateColumns": "90px 1fr 1fr 1fr", "gap": 14,
                            "alignItems": "baseline", "marginBottom": 10},
                    h("div", None, h("div", {"fontSize": 30, "fontFamily": F_DISPLAY, "fontWeight": 700,
                                             "color": C.forest, "lineHeight": 1}, p["tk"])),
                    Stat("SIZE ĐỀ XUẤT", [p["sizeRec"], u, m], color=C.gold),
                    Stat("VÙNG MUA", [p["entry"], u], color=C.ink),
                    Stat("TARGET", [p["target"], u], color=C.forest)),
                  lv and lv.add_live(p),
                  _flow_line(fl, lv) if fl else None,
                  lv and lv.add_flow_live(p["tk"]),
                  h("div", {"padding": "10px 14px", "background": C.forest + "12", "borderLeft": "3px solid " + C.forest,
                            "fontSize": 11, "fontFamily": F_SERIF, "color": C.ink, "lineHeight": 1.7},
                    h("strong", {"color": C.forest, "fontFamily": F_MONO, "fontSize": 9, "letterSpacing": ".18em"},
                      "LUẬN ĐIỂM · "),
                    lv.pattern_q(p["tk"], p["thesis"]) if lv else p["thesis"], v21_mark(),
                    lv and lv.thesis_note("add", p["tk"])),
                  accent=C.forest),
             key="p08.add." + p["tk"])


def section_add(pa, flow, lv):
    sub = "Distilled từ Chaebol Map + VN30 Screener"
    return Section("Khuyến Nghị Mua Thêm — 4 Mã Tiềm Năng", _intro_b(),
                   *[_add_card(p, flow, lv) for p in pa.get("add") or []],
                   accent=C.forest, sub=[sub, v21_mark()] if lv else sub, key="p08.add")


# ── Tab 08 · Section C: danh sách tránh ─────────────────────────────────────


def _intro_c():
    return h("div", {"fontSize": 13, "fontFamily": F_SERIF, "color": C.inkD, "lineHeight": 1.7, "fontStyle": "italic",
                     "marginBottom": 14, "padding": "12px 16px", "background": C.vermillion + "12",
                     "borderLeft": "3px solid " + C.vermillion},
             "Munger inversion: ", h("strong", {"color": C.ink}, '"Invert, always invert"'),
             ". Trước khi quyết định mua gì, hãy quyết định ", h("strong", {"color": C.vermillion},
                                                                 "không bao giờ động đến"),
             " những gì. 4 nhóm dưới đây đang trong P3D distribution / value trap / parabolic / ⛔ pháp lý — tránh xa, "
             "kể cả khi sell-side khuyến nghị BUY (đặc biệt trường hợp DGC vẫn còn nhiều brokers giữ TP cao).",
             v21_mark())


def section_avoid(pa, lv):
    cards = []
    for p in pa.get("avoid") or []:
        reason = (lv and lv.avoid_reason(p)) or [p["reason"]]
        cards.append(Card(
            h("div", {"display": "flex", "alignItems": "baseline", "gap": 12, "marginBottom": 10},
              h("div", {"fontSize": 24, "fontFamily": F_DISPLAY, "fontWeight": 700, "color": C.vermillion,
                        "lineHeight": 1}, p["tk"]),
              Pill("AVOID", C.vermillion), v21_mark()),
            h("div", {"fontSize": 11, "fontFamily": F_SERIF, "color": C.ink, "lineHeight": 1.7}, *reason),
            accent=C.vermillion, key="p08.avoid." + p["tk"]))
    return Section("Danh Sách Tránh — Risk Off Danh Mục", _intro_c(),
                   h("div", {"display": "grid", "gridTemplateColumns": "repeat(2, 1fr)", "gap": 12}, *cards),
                   accent=C.vermillion, key="p08.avoid")


# ── Tab 08 · Section D: lộ trình rotation (V21, stance) ─────────────────────

_S = object()   # đánh dấu mảnh <strong> trong mục li
ROTATION = (
    (C.ochre, "▸ TUẦN 1-3 · TRIM", (
        ("Bán ", (_S, "FPT đợt 1"), ": 5,000-6,000 cp (~25-30% position) khi nào hồi 75-78K"),
        ("Bán ", (_S, "VCB đợt 1"), ": 10,000-12,000 cp (~20-25%) khi vùng 62-64K"),
        ((_S, "Giữ MSN nguyên"), " — Pattern B đang form, NN flip 4y first time"),
        ("Lưu thanh khoản 1.5-2 tỷ chờ vào lệnh mới",))),
    (C.forest, "▸ TUẦN 4-8 · BUILD", (
        ("Mua ", (_S, "GEX"), " 5-7% NAV (chia 3 đợt 25/26/27K)"),
        ("Mua ", (_S, "HPG"), " 3-5% NAV vùng 25-27K (DCA Pattern B)"),
        ("Mua ", (_S, "BSR"), " 2-3% NAV vùng 20-22K nếu có pull-back từ +91% run"),
        ("Theo dõi VCI sau insider sell 16.91M cp ngày 4/5 — đợi BÁN xong rồi vào",),
        ("Bán FPT đợt 2 + VCB đợt 2 nếu mục tiêu trên đạt",))),
    (C.gold, "▸ TUẦN 9-12 · CONSOLIDATE", (
        ("Cân bằng tỷ trọng cuối: ", (_S, "MSN 25-30% · GEX 5-7% · HPG 3-5% · BSR 2-3% · VCI 2-3% · VCB 15% · Cash 35-40%")),
        ("FPT có thể đã exit toàn bộ (mức độ -29% capitulation đỉnh điểm rồi recovery 20-25%)",),
        ("Theo dõi ", (_S, "Nghi Sơn DGC Q3 runrate"), " như value-trap watch (KHÔNG mua nếu chưa giải quyết pháp lý)"),
        ("Reset thesis V22: theo dõi xem MSR APT có cycle peak chưa (thông thường W tungsten cycle 18-24 tháng)",))),
)
MILESTONES = (
    ("GEX", "Tuấn mượt (GEX):", " Q2/2026 BCTC + tiến độ Gia Bình airport (target khởi công 2027). Triển khai Eximbank "
                                "board nomination tháng 6-7/2026."),
    ("VCI", "Phượng (VCI):", " ESOP 4.6M cp issued tháng 6, sau đó là quarter 3 với target LN 2,300 tỷ trên đường về. "
                             "Singapore branch operation update."),
    ("VJC", "Sovico (VJC):", " Theo dõi mức độ HDB bán cổ phần VJC theo Luật TCTD 2024 — thông tin sell phá giá có thể "
                             "là entry point đầu năm 2027 nếu VJC drop về 130-140K."),
    ("DGC", "Eliminated (DGC):", " Ngày 8/5/2026 ĐHĐCĐ thay 3 BOD (HÔM NAY). BCTC kiểm toán 2025 hạn chót Q3/2026. "
                                 "Nghi Sơn runrate Q3/2026 — chỉ xem xét khi cleared toàn bộ rủi ro pháp lý."),
)


def _li(item):
    return h("li", None, *[h("strong", None, x[1]) if isinstance(x, tuple) else x for x in item])


def section_rotation(lv):
    cards = []
    for i, (accent, title, items) in enumerate(ROTATION):
        cards.append(Card(
            h("div", {"fontSize": 10, "letterSpacing": ".18em", "color": accent, "fontFamily": F_MONO,
                      "marginBottom": 10, "fontWeight": 600}, title, v21_mark()),
            h("ul", {"margin": 0, "paddingLeft": 16, "fontSize": 11, "fontFamily": F_SERIF, "color": C.ink,
                     "lineHeight": 1.85}, *[_li(it) for it in items]),
            lv and lv.rotation_note(i),
            accent=accent, key="p08.rot.%d" % (i + 1)))
    ms = []
    for tk, lead, text in MILESTONES:
        body = (lv and lv.milestone(tk)) or [text]
        ms.append(h("div", None, h("strong", {"color": C.gold}, lead), *body))
    box = h("div", {"marginTop": 18, "padding": "14px 18px", "background": C.gold + "10",
                    "border": "1px solid " + C.gold + "40", "borderRadius": 2},
            h("div", {"fontSize": 10, "letterSpacing": ".2em", "color": C.gold, "fontFamily": F_MONO, "marginBottom": 10,
                      "fontWeight": 600}, "★ KEY MILESTONES THEO DÕI"),
            h("div", {"display": "grid", "gridTemplateColumns": "repeat(2, 1fr)", "gap": 14, "fontSize": 11,
                      "fontFamily": F_SERIF, "color": C.ink, "lineHeight": 1.7}, *ms),
            key="p08.milestones")
    return Section("Lộ Trình Rotation — 90 Ngày Tới",
                   h("div", {"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": 14}, *cards), box,
                   accent=C.gold, sub=lv and lv.rotation_sub(), key="p08.rotation")


def build_portfolio(ctx):
    """Tab 08 · DANH MỤC (không state). Live: thêm khối hai danh mục hiện hành lên đầu tab."""
    v21 = ctx.v21 or {}
    pa, flow = v21.get("PORTFOLIO_ACTION") or {}, v21.get("FLOW") or {}
    if not pa:
        ctx.warn("v21_const thiếu PORTFOLIO_ACTION — tab 08 rỗng")
    lv = _live(ctx)
    root = h("div", None, lv and lv.books_section(), section_current(pa, flow, lv), section_add(pa, flow, lv),
             section_avoid(pa, lv), section_rotation(lv), key="tab.portfolio")
    return {"root": root, "states": [], "csv": lv.csv_portfolio(pa) if lv else None}


# ── Tab 13 · ACTION PORTFOLIO 25 ────────────────────────────────────────────


def _p25_table(rows, lv):
    th = lambda t, align="left", extra=None: h("th", {"textAlign": align, "padding": "8px 10px"}, t, extra)  # noqa: E731
    head = [th("TICKER"), th("CAT"), th("ACTION", extra=v21_mark()), th("TỶ TRỌNG", "right"),
            th("ENTRY"), th("NOTE")]
    if lv:
        head += lv.p25_head()
    body = []
    for p in rows:
        col = P25_COL_MAP.get(p["col"])
        cells = [
            h("td", {"padding": "8px 10px", "fontFamily": F_MONO, "fontWeight": 700, "color": col or C.ink}, p["tk"]),
            h("td", {"padding": "8px 10px", "fontSize": 9, "color": P25_CAT_COLOR.get(p["cat"]), "fontFamily": F_MONO,
                     "fontWeight": 600, "letterSpacing": ".1em"}, p["cat"].upper()),
            h("td", {"padding": "8px 10px", "fontWeight": 600, "color": col or C.ink}, p["act"]),
            h("td", {"padding": "8px 10px", "textAlign": "right", "fontFamily": F_MONO, "fontWeight": 700,
                     "color": C.gold}, p["w"]),
            h("td", {"padding": "8px 10px", "fontFamily": F_MONO, "color": C.ink2, "fontSize": 10}, p["entry"]),
            h("td", {"padding": "8px 10px", "color": C.inkD, "fontSize": 10, "lineHeight": 1.4}, p["note"]),
        ]
        if lv:
            cells += lv.p25_cells(p)
        body.append(h("tr", {"borderBottom": "1px solid " + C.parch, "background": (col or C.ink2) + "08"}, *cells,
                      if_={"p25.cat": ["ALL", p["cat"]]}, grp="p25.rows", key="p25.row." + p["tk"]))
    return h("table", {"width": "100%", "fontSize": 11, "fontFamily": F_SERIF, "borderCollapse": "collapse"},
             h("thead", None, h("tr", {"borderBottom": "2px solid " + C.gold, "color": C.ink2, "fontFamily": F_MONO,
                                       "fontSize": 9, "letterSpacing": ".1em"}, *head)),
             h("tbody", None, *body), key="p25.table")


def build_portfolio25(ctx):
    """Tab ★ 13 · state p25.cat ∈ ALL/Core/Growth/Tactical/Avoid (lọc giữ thứ tự dữ liệu, không sắp)."""
    v21 = ctx.v21 or {}
    rows = v21.get("ACTION_PORT_25") or []
    if not rows:
        ctx.warn("v21_const thiếu ACTION_PORT_25 — tab 13 rỗng")
    cats = [str(c) for c in (v21.get("ActionPortfolio25Tab.cats") or P25_CATS)]
    lv = _live(ctx)
    stat_cards = []
    for c in ("Core", "Growth", "Tactical", "Avoid"):
        cc = P25_CAT_COLOR[c]
        stat_cards.append(Card(
            h("div", {"fontSize": 10, "color": cc, "letterSpacing": ".2em", "fontFamily": F_MONO, "fontWeight": 600},
              c.upper()),
            h("div", {"fontSize": 24, "fontWeight": 700, "color": C.ink, "fontFamily": F_DISPLAY},
              len([p for p in rows if p["cat"] == c]), v21_mark()),
            h("div", {"fontSize": 10, "color": C.ink2}, "tickers"), accent=cc, key="p25.stat." + c))
    stat_cards.append(Card(
        h("div", {"fontSize": 10, "color": C.ink2, "letterSpacing": ".2em", "fontFamily": F_MONO, "fontWeight": 600},
          "CASH"),
        h("div", {"fontSize": 24, "fontWeight": 700, "color": C.ink, "fontFamily": F_DISPLAY}, "15%", v21_mark()),
        h("div", {"fontSize": 10, "color": C.ink2}, "reserve"), accent=C.ink2, key="p25.stat.CASH"))
    buttons = []
    for c in cats:
        cc = P25_CAT_COLOR.get(c)
        buttons.append(h("button", {"padding": "5px 12px", "background": "transparent", "color": C.ink,
                                    "border": "1px solid " + (cc or C.ink2), "cursor": "pointer", "fontWeight": 600},
                         c, on={"set": {"p25.cat": c}},
                         var=[{"if": {"p25.cat": c}, "s": {"background": cc or C.gold, "color": "#0a0a0c"}}],
                         key="p25.btn." + c))
    sub = "Core 40% · Growth 30% · Tactical 15% · Avoid 0% · Cash 15%"
    sec = Section("💼 ACTION PORTFOLIO · 25 mã color-coded (MD section 10)",
                  h("div", {"display": "grid", "gridTemplateColumns": "repeat(5, 1fr)", "gap": 10, "marginBottom": 14},
                    *stat_cards),
                  h("div", {"display": "flex", "gap": 6, "marginBottom": 14, "fontFamily": F_MONO, "fontSize": 9,
                            "letterSpacing": ".1em"}, *buttons, key="p25.filter"),
                  lv and lv.p25_intro(),
                  _p25_table(rows, lv),
                  accent=C.emerald, sub=[sub, v21_mark()] if lv else sub, key="p25.section")
    return {"root": h("div", None, sec, key="tab.portfolio25"),
            "states": [{"key": "p25.cat", "default": "ALL", "options": cats}],
            "csv": lv.csv_p25(rows) if lv else None}
