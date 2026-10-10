#!/usr/bin/env python3
"""
chaebol_map_tab_overview_map — thân tab `chaebol` (01 · CHAEBOL MAP) của chaebol_map, tách khỏi
chaebol_map_tab_overview.py theo luật ≤ ~800 dòng/tệp (api_python §9.7). Nguồn: SRC 5330–5723.

Thứ tự 9 Section: E Intro → F Bốn nhóm → [Enrichment: G 3 trục → H Matrix (state) → I Claims → J Insights]
→ K Timeline → L Power Map (SVG) → M Hypothesis. Lớp live (L) chỉ chèn/thay nội dung, không đổi khung.
"""
from __future__ import annotations

from chaebol_map_dom import C, F_DISPLAY, F_MONO, F_NUM, F_SERIF, alpha, h, js_string, sign_fixed
from chaebol_map_shell import Card, Pill, Section

PARCH80 = alpha(C.parch, "80")
# ChaebolMapEnrichment 5336–5337; C.crimson/C.emerald theo ý đồ (DESIGN §0.1) — v21_const bỏ các khoá undefined.
AXIS_COLOR = {"NQ79": C.crimson, "NQ68": C.emerald, "SPECIAL": C.gold}
TIER_COLOR = {"Top": C.gold, "Mid": C.emerald, "Distress": C.crimson, "Special": "#a78bfa"}
_AXIS_DEFAULT = ["ALL", "NQ79", "NQ68", "SPECIAL"]
_TIER_DEFAULT = ["ALL", "Top", "Mid", "Distress", "Special"]


def _v(ctx, name, default=None):
    v = (ctx.v21 or {}).get(name)
    if v is None:
        ctx.warn("v21_const thiếu %s" % name)
        return default
    return v


def axis_options(ctx):
    return [str(x) for x in (ctx.v21 or {}).get("ChaebolMapEnrichment.jsx@L5385") or _AXIS_DEFAULT]


def tier_options(ctx):
    return [str(x) for x in (ctx.v21 or {}).get("ChaebolMapEnrichment.jsx@L5389") or _TIER_DEFAULT]


def seg(node, *parts):
    """Đặt con của `node` thành các nút chữ RIÊNG như React (`{a} · {b}` → 3 text node). h() gộp chuỗi kề nhau,
    nhưng Chrome vẽ mỗi text node thành một mảnh riêng (làm tròn vị trí khác) → lệch 1 px so với ref."""
    kids = []

    def add(x):
        if x is None or isinstance(x, bool) or x == "":
            return
        if isinstance(x, (list, tuple)):
            for y in x:
                add(y)
        elif isinstance(x, (int, float)):
            kids.append(js_string(x))
        else:
            kids.append(x)
    add(parts)
    if kids:
        node["k"] = kids
    return node


def _hook(L, name, *args, default=None):
    if L is None:
        return default
    try:
        return getattr(L, name)(*args)
    except Exception as exc:  # noqa: BLE001
        L.ctx.warn("live.%s lỗi: %s: %s" % (name, type(exc).__name__, exc))
        return default


def _tag(L, kind):
    """Nhãn khối V21 giữ nguyên ở mode live (bậc gốc + V21·12/05); v21 → None."""
    return _hook(L, "tag", kind)


# ── E · Intro (5484–5490) ───────────────────────────────────────────────────


def _intro(L):
    body = h("div", {"fontSize": 13, "fontFamily": F_SERIF, "color": C.ink, "lineHeight": 1.85},
             "Khái niệm ", h("strong", {"color": C.gold, "fontStyle": "italic"}, "chaebol"),
             " nguyên gốc từ Hàn Quốc — chỉ các tập đoàn gia đình nắm quyền lực kinh tế lớn liên kết chặt với nhà nước. "
             "Tại Việt Nam, hiện tượng tương đương đã hình thành từ 2012-2026 với các \"tỷ phú thân hữu\" có ảnh hưởng "
             "đa ngành. ", h("em", None, "V21 phân tích 4 nhóm chính ảnh hưởng đến VN30 và ETFs."),
             " Đây ", h("span", {"color": C.vermillion}, "KHÔNG"),
             " phải claim chính trị — chỉ là ánh xạ ownership patterns + AGM disclosures + Capital IQ shareholder data + "
             "công khai báo chí, để giúp anh hiểu ", h("em", None, "\"ai bơm nước, ai xả nước\""),
             " trong từng cụm cổ phiếu cụ thể.", _hook(L, "intro_extra"))
    return Section("◆ Bản Đồ Chaebol Việt Nam — Tháng 5, 2026", Card(body, padding=20),
                   sub=_hook(L, "intro_sub") or "Politicalmaps × stock market overlay", key="map.intro")


# ── F · Bốn nhóm trọng yếu (5493–5530) ─────────────────────────────────────


def _chip(t, fl, live_chip):
    """Chip mã: viền trái theo sig FLOW (BULL forest / BEAR vermillion / MIX ochre), không FLOW → inkM."""
    if live_chip is not None:
        border, sub = live_chip
    elif fl:
        sig = fl.get("sig")
        border = "3px solid " + (C.forest if sig == "BULL" else C.vermillion if sig == "BEAR" else C.ochre)
        sub = sign_fixed(fl["perf60"], 1, strict=True) + "%"
    else:
        border, sub = "3px solid " + C.inkM, "N/A"
    return h("div", {"padding": "6px 10px", "background": C.parch, "borderLeft": border, "fontFamily": F_NUM,
                     "fontSize": 11, "fontWeight": 700},
             h("div", None, t), h("div", {"fontSize": 9, "color": C.inkD, "fontWeight": 400, "marginTop": 2}, sub))


def _groups(ctx, L):
    flow = _v(ctx, "FLOW", {})
    cards = []
    for g in _v(ctx, "CHAEBOL_GROUPS", []):
        gc = g["color"]
        chips = [_chip(t, flow.get(t), _hook(L, "group_chip", t)) for t in g["tickers"]]
        cards.append(Card(
            h("div", {"display": "flex", "justifyContent": "space-between", "alignItems": "baseline", "marginBottom": 10},
              h("h3", {"margin": 0, "fontSize": 20, "fontFamily": F_DISPLAY, "fontWeight": 700, "color": gc,
                       "letterSpacing": "-0.01em"}, g["name"]),
              Pill(g["status"], g["statusColor"])),
            h("div", {"fontSize": 13, "color": C.bone, "marginBottom": 4, "fontFamily": F_DISPLAY,
                      "fontStyle": "italic"}, g["head"]),
            h("div", {"fontSize": 10, "color": C.inkD, "marginBottom": 12, "fontFamily": F_MONO,
                      "letterSpacing": ".05em"}, g["headTitle"]),
            h("div", {"display": "flex", "gap": 5, "marginBottom": 14, "flexWrap": "wrap"}, *chips),
            _hook(L, "group_chip_note", g["id"]),
            h("div", {"fontSize": 11, "color": C.inkD, "lineHeight": 1.7, "fontFamily": F_SERIF, "marginBottom": 10},
              g["political"], _tag(L, "v21U")),
            h("div", {"fontSize": 11, "color": C.ink, "lineHeight": 1.65, "fontFamily": F_SERIF,
                      "padding": "10px 12px", "background": PARCH80, "borderLeft": "2px solid " + gc},
              h("strong", {"color": gc, "fontFamily": F_MONO, "fontSize": 9, "letterSpacing": ".2em"},
                "CORE THESIS · "),
              g["coreThesis"], _tag(L, "v21U")),
            _hook(L, "group_facts", g["id"]),
            accent=gc, padding=20, key="map.grp." + g["id"]))
    return Section("✦ Bốn Nhóm Trọng Yếu", h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 14},
                                              *cards), accent=C.gold, key="map.groups")


# ── G · Phân nhóm 3 trục (5347–5380) ───────────────────────────────────────


def _axes(ctx, L, ents):
    counts = {"NQ79": 0, "NQ68": 0, "SPECIAL": 0}
    for e in ents:
        counts[e["axis"]] = counts.get(e["axis"], 0) + 1
    lab = {"fontSize": 10, "letterSpacing": ".2em", "fontFamily": F_MONO, "fontWeight": 600, "marginBottom": 6}
    desc = {"fontSize": 11, "color": C.inkD, "marginTop": 6, "lineHeight": 1.5, "fontFamily": F_SERIF}
    lst = {"fontSize": 10, "color": C.ink2, "marginTop": 8, "fontFamily": F_MONO}

    def card(color, label, n, text, names, key):
        return Card(h("div", {"fontSize": 10, "color": color, **{k: v for k, v in lab.items() if k != "fontSize"}},
                          label),
                    h("div", {"fontSize": 36, "fontWeight": 700, "color": color, "fontFamily": F_DISPLAY}, n,
                      _tag(L, "E")),
                    h("div", desc, *text, _hook(L, "axis_extra", key)),
                    h("div", lst, names), accent=color, padding=18, key="map.axis." + key)

    return Section(
        "⚖ Phân Nhóm 3 Trục — NQ 68 (Tư nhân) vs NQ 79 (Nhà nước) vs Special",
        h("div", {"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": 14, "marginBottom": 14},
          card(C.crimson, "★ NQ 79 — NHÀ NƯỚC", counts["NQ79"],
               [h("strong", None, "Mục tiêu:"),
                " 50 DNNN Top 500 ĐNA · 1-3 Top 500 thế giới · ≥3 NHTM Top 100 châu Á"],
               "Big4 · PVN · Viettel · Petrolimex · ACV · Becamex · TKV · Vinatex", "NQ79"),
          card(C.emerald, "★ NQ 68 — TƯ NHÂN", counts["NQ68"],
               [h("strong", None, "Mục tiêu:"),
                " Tư nhân đóng góp 55-58% GDP đến 2030 · >20 DN tham gia chuỗi giá trị toàn cầu"],
               "Vingroup · Masan-TCB · Sovico · GELEX · FPT · HPG · VPB · T&T · REE · DGC · NVL · Tasco", "NQ68"),
          card(C.gold, "★ ĐẶC BIỆT", counts["SPECIAL"],
               [h("strong", None, "Bầu Thụy"), " — LPB → Sacombank transition · không thuộc 100% NQ nào do tính chất "
                                               "chuyển giao quyền lực ngân hàng"],
               "LPB · STB · THD · HAG · LPBS", "SPECIAL")),
        accent=C.gold, sub="From MD v3.0 section 2 · 21 chaebol map", key="map.axes")


# ── H · 21 Chaebol Full Matrix (5383–5431) — state map.axis × map.tier ─────


def _filter_btn(state_key, value, color_map):
    """<button onClick={setX(v)}> — style chưa chọn + var khi chọn (nền màu||gold, chữ #0a0a0c)."""
    return h("button", {"padding": "4px 10px", "background": "transparent", "color": C.ink,
                        "border": "1px solid " + (color_map.get(value) or C.ink2), "cursor": "pointer",
                        "fontWeight": 600},
             value, on={"set": {state_key: value}},
             var=[{"if": {state_key: value}, "s": {"background": color_map.get(value) or C.gold, "color": "#0a0a0c"}}],
             key="map.btn.%s.%s" % (state_key, value))


_TD = {"padding": "8px 8px"}


def _row(e, L):
    tc, ac = TIER_COLOR.get(e["tier"]), AXIS_COLOR.get(e["axis"])
    span = {"padding": "2px 6px", "fontFamily": F_MONO, "fontSize": 9, "fontWeight": 700, "letterSpacing": ".1em"}
    bg = alpha(C.crimson, "10") if e["tier"] == "Distress" else alpha(C.gold, "06") if e["tier"] == "Top" \
        else "transparent"
    cl_color = C.crimson if e["claims"] >= 5 else C.gold if e["claims"] >= 3 else C.ink2
    live = _hook(L, "entity_cells", e) or {}
    return h("tr", {"borderBottom": "1px solid " + C.parch, "background": bg},
             h("td", {**_TD, "fontFamily": F_MONO, "color": C.ink2}, e["n"]),
             h("td", {**_TD, "fontWeight": 700, "color": C.ink, "fontFamily": F_DISPLAY, "fontSize": 13}, e["ch"]),
             h("td", {**_TD, "color": C.inkD, "fontStyle": "italic"}, live.get("leader", e["leader"])),
             h("td", {**_TD, "fontFamily": F_MONO, "fontSize": 10, "color": C.gold}, live.get("tk", e["tk"])),
             h("td", {**_TD, "textAlign": "center"},
               h("span", {"padding": "2px 6px", "background": tc + "25", "color": tc, **{
                   k: v for k, v in span.items() if k != "padding"}}, e["tier"].upper())),
             h("td", {**_TD, "textAlign": "center"},
               h("span", {"padding": "2px 6px", "background": ac + "25", "color": ac, **{
                   k: v for k, v in span.items() if k != "padding"}}, e["axis"])),
             h("td", {**_TD, "color": C.inkD, "fontSize": 10}, e["cl"]),
             h("td", {**_TD, "textAlign": "right", "fontFamily": F_MONO, "fontWeight": 700, "color": cl_color},
               e["claims"]),
             seg(h("td", {**_TD, "color": C.inkD, "fontSize": 10, "lineHeight": 1.4}),
                 h("strong", {"color": C.gold, "fontFamily": F_MONO, "fontSize": 9}, live.get("wealth", e["wealth"])),
                 " · ", live.get("note", e["note"])),
             if_={"map.axis": ["ALL", e["axis"]], "map.tier": ["ALL", e["tier"]]}, grp="map.rows",
             key="map.row.%s" % e["n"])


def _matrix(ctx, L, ents):
    ths = [("left", "#", 30), ("left", "CHAEBOL", None), ("left", "LEADER", None), ("left", "TICKERS", None),
           ("center", "TIER", 60), ("center", "AXIS", 70), ("left", "CLUSTER", None), ("right", "CLAIMS", 60),
           ("left", "WEALTH / NOTE", None)]
    bar = h("div", {"display": "flex", "flexWrap": "wrap", "gap": 6, "marginBottom": 14, "fontFamily": F_MONO,
                    "fontSize": 9, "letterSpacing": ".1em"},
            *[_filter_btn("map.axis", a, AXIS_COLOR) for a in axis_options(ctx)],
            h("div", {"width": 1, "background": C.ink2, "margin": "0 6px"}),
            *[_filter_btn("map.tier", t, TIER_COLOR) for t in tier_options(ctx)],
            h("div", {"marginLeft": "auto", "color": C.ink2, "alignSelf": "center"},
              count={"grp": "map.rows", "fmt": "Showing {n}/24"}, key="map.count"), key="map.filters")
    table = h("div", {"overflowX": "auto"},
              h("table", {"width": "100%", "fontSize": 11, "fontFamily": F_SERIF, "borderCollapse": "collapse",
                          "minWidth": 1100},
                h("thead", None, h("tr", {"borderBottom": "2px solid " + C.gold, "color": C.ink2, "fontFamily": F_MONO,
                                          "fontSize": 9, "letterSpacing": ".1em"},
                                   *[h("th", {"textAlign": al, "padding": "8px 8px", "width": w}, lb,
                                       _tag(L, "E") if lb == "CLAIMS" else None) for al, lb, w in ths])),
                h("tbody", None, *[_row(e, L) for e in ents])), key="map.table")
    return Section("📋 21 Chaebol Full Matrix — Leader · Tickers · Tier · Cluster · Claims", bar, table,
                   _hook(L, "matrix_footer"), accent=C.emerald,
                   sub="24 entries (Big4 tách 4 NH thành 4 row riêng — gọi là 21 do report rule)", key="map.matrix")


# ── I · 54 Claims Distribution (5434–5450) ─────────────────────────────────


def _claims(ctx, L, ents):
    by_claim = sorted(ents, key=lambda e: -e["claims"])[:10]          # sort ổn định như V8 TimSort
    max_claim = max(e["claims"] for e in by_claim) if by_claim else 1
    rows = []
    for e in by_claim:
        fill = C.crimson if e["claims"] >= 7 else C.gold if e["claims"] >= 5 else C.emerald
        rows.append(h("div", {"display": "grid", "gridTemplateColumns": "180px 1fr 40px", "gap": 10,
                              "alignItems": "center", "marginBottom": 8},
                      h("div", {"fontSize": 12, "color": C.ink, "fontWeight": 600, "fontFamily": F_DISPLAY}, e["ch"]),
                      h("div", {"position": "relative", "height": 18, "background": C.parch},
                        h("div", {"width": js_string(e["claims"] / max_claim * 100) + "%", "height": "100%",
                                  "background": fill, "transition": "width 0.3s"}),
                        seg(h("div", {"position": "absolute", "left": 8, "top": 0, "lineHeight": "18px",
                                      "fontSize": 9, "color": C.bg, "fontFamily": F_MONO, "fontWeight": 700,
                                      "letterSpacing": ".1em"}), e["axis"], " · ", e["tier"].upper())),
                      h("div", {"textAlign": "right", "fontFamily": F_MONO, "fontWeight": 700, "color": C.gold,
                                "fontSize": 13}, e["claims"])))
    insight = _hook(L, "claims_insight", ents)
    if insight is None:
        insight = [h("strong", {"color": C.gold}, "Pattern insight:"),
                   " Masan-TCB 9 + FPT 7 + GELEX 7 + Vingroup 7 + Hoà Phát 6 = ", h("strong", None, "36/54 claims (67%)"),
                   " tập trung 5 chaebol top. Pattern này khẳng định ",
                   h("em", None, "\"big chaebol = big thesis = big monitoring effort\""),
                   ". 16 chaebol khác chỉ chiếm ≤2 claims/each → mostly tactical positioning."]
    return Section("📊 54 Claims Distribution per Chaebol — Top 10 (drives portfolio focus)",
                   Card(h("div", {"fontSize": 11, "color": C.inkD, "lineHeight": 1.7, "marginBottom": 14,
                                  "fontFamily": F_SERIF}, *insight), *rows, padding=18),
                   accent=C.crimson, sub="From MD section 3 · Chaebol có nhiều claims = thesis sâu, monitor chặt",
                   key="map.claims")


# ── J · 5 patterns (5453–5476) — Card bỏ `style` → Pattern 5 KHÔNG span 2 cột (giữ như gốc) ─

PATTERNS = (
    ("p1", C.crimson, "PATTERN 1 · Banking + CK IPO monetization",
     ["TCBS IPO Q4/26-Q1/27 (~$3.5B) là MAJOR catalyst chưa pricing-in. VPBankS lock-up hết 30/6. LPBS Bầu Thụy IPO "
      "Q3/26. Cả 3 thuộc cùng pattern monetize CK subsidiary."]),
    ("p2", C.gold, "PATTERN 2 · Crisis Q1 — quarterly pain",
     ["ACV Vũ Thế Phiệt bị bắt 3/4. DGC 3 BOD khởi tố 3/2026. VPB Phạm Thị Nhung INSIDER 5/5. Pattern Q1 = quý có nhiều "
      "scandal/legal events nhất."]),
    ("p3", "#a78bfa", "PATTERN 3 · 40% anchor rule",
     ["Munger 40% RED FLAG: nếu chaebol kiểm soát >40% qua cross-holdings phức tạp → governance discount tự động. "
      "Apply: Vingroup 60%+ family · Masan-TCB 76.7% concentrated."]),
    ("p4", C.emerald, "PATTERN 4 · Free float crisis",
     ["6 mã NQ79 (BSR, PLX, BCM, VGI, GVR, ACV) hạn cuối 31/12/2026 phải nâng free float >10%. Vi phạm = bị HOSE cảnh "
      "báo. VPL 13/5/26 cũng cùng deadline."]),
    ("p5", C.crimson, "PATTERN 5 · 4-piece NH-CK-BH-Holding (ván cờ hoàn chỉnh)",
     ["Mỗi chaebol mạnh đều có 4 mảnh: Ngân hàng (TCB/VPB/HDB/SHB) · Chứng khoán (TCBS/VPBankS/HCM/SHS) · Bảo hiểm "
      "(BHI/BIC/PVI) · Holding (MSN/VPB/Sovico/T&T). Chaebol thiếu mảnh nào = thiếu pricing power. ",
      ("strong", "Vingroup hiện thiếu mảnh CK"), " → có thể M&A trong 12T."]),
)


def _patterns(L):
    cards = []
    for pid, color, title, body in PATTERNS:
        runs = [h("strong", {"color": C.gold}, x[1]) if isinstance(x, tuple) else x for x in body]
        cards.append(Card(h("div", {"fontSize": 10, "color": color, "letterSpacing": ".2em", "fontFamily": F_MONO,
                                    "fontWeight": 600, "marginBottom": 6}, title),
                          h("div", {"fontSize": 11, "color": C.inkD, "lineHeight": 1.6, "fontFamily": F_SERIF}, *runs,
                            _tag(L, "v21U")),
                          _hook(L, "pattern_status", pid), accent=color, key="map.pattern." + pid))
    return Section("💡 Key Insights từ MD v3.0 — 5 patterns lớn",
                   h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 12}, *cards),
                   accent=C.gold, key="map.patterns")


# ── K · Timeline (5535–5568) ────────────────────────────────────────────────


def _timeline(ctx, L):
    events = [dict(e, _v21=True) for e in _v(ctx, "ChaebolMapTab.jsx@L5538", [])]
    title, sub = "⌖ Timeline 30 Ngày Gần Nhất — Sự Kiện Định Hình Chaebol Map", None
    live = _hook(L, "timeline", events)
    if live:
        events, title, sub = live["events"], live["title"], live.get("sub")
    n = len(events)
    last = 10 if L is None else n - 1          # gốc gắn cứng i<10 (11 mốc); live nhiều mốc hơn → i<n-1
    rows = []
    for i, e in enumerate(events):
        cl, hot = e["cl"], bool(e.get("hot"))
        rows.append(h("div", {"display": "flex", "alignItems": "baseline", "gap": 14, "padding": "10px 0",
                              "borderBottom": ("1px solid " + alpha(C.rule, "50")) if i < last else "none"},
                      h("div", {"width": 120, "fontSize": 10, "color": cl if hot else C.inkD, "fontFamily": F_NUM,
                                "letterSpacing": ".05em", "fontWeight": 700 if hot else 400, "textAlign": "right",
                                "flexShrink": 0}, e["date"]),
                      h("div", {"width": 14, "height": 14, "borderRadius": "50%", "background": cl,
                                "border": "2px solid " + C.bg, "boxShadow": "0 0 0 1px " + alpha(cl, "50"),
                                "flexShrink": 0, "position": "relative", "zIndex": 1}),
                      h("div", {"flex": 1, "fontSize": 12, "fontFamily": F_SERIF, "color": C.ink, "lineHeight": 1.6},
                        seg(h("span", {"fontSize": 9, "color": cl, "fontFamily": F_MONO, "letterSpacing": ".1em",
                                       "marginRight": 8}), "[", e["group"].upper(), "]"),
                        e["evt"], e.get("_tail"))))
    return Section(title, h("div", {"display": "flex", "flexDirection": "column", "gap": 0, "position": "relative"},
                             h("div", {"position": "absolute", "left": 140, "top": 0, "bottom": 0, "width": 1,
                                       "background": C.rule}), *rows),
                   accent=C.ochre, sub=sub, key="map.timeline")


# ── L · Power Map SVG (5571–5703) — hình học y gốc (kể cả chữ đè/tràn) ──────

_BOXES = (
    # (key v21 hàng, translate, rect h, stroke, strokeWidth, dash, tiêu đề, màu tiêu đề, tên, cỡ tên, màu tên, subX, màu mã)
    ("ChaebolMapTab.jsx@L5598", "translate(60, 50)", "160", C.gold, "2", None, "★ TUẤN MƯỢT", C.gold,
     "Nguyễn Văn Tuấn", "13", C.ink, "60", C.gold),
    ("ChaebolMapTab.jsx@L5618", "translate(800, 50)", "160", "#9b6dd0", "2", None, "✈ SOVICO", "#9b6dd0",
     "Bà Phương Thảo", "13", C.ink, "100", "#9b6dd0"),
    ("ChaebolMapTab.jsx@L5638", "translate(430, 220)", "170", C.ink2, "2", None, "❀ BÀ PHƯỢNG", C.ink2,
     "Nguyễn Thanh Phượng", "13", C.ink, "100", C.ink2),
    ("ChaebolMapTab.jsx@L5658", "translate(60, 280)", "140", C.vermillion, "2", "4 4", "⛔ ELIMINATED", C.vermillion,
     "Loại khỏi cuộc chơi", "12", C.inkD, "60", C.vermillion),
    ("ChaebolMapTab.jsx@L5676", "translate(800, 280)", "140", C.inkD, "1", None, "⊞ VN30 OTHER", C.bone,
     "Independent / Other groups", "12", C.inkD, "100", C.bone),
)


def _svg_box(ctx, L, spec):
    key, tr, rh, stroke, sw, dash, title, tcol, name, nsize, ncol, subx, mcol = spec
    rows = []
    for s in _v(ctx, key, []):
        sub = _hook(L, "svg_sub", key, s) or [s["sub"]]
        rows.append(h("g", None,
                      h("text", None, *(_hook(L, "svg_label", key, s) or [s["t"]]),
                        a={"x": "20", "y": s["y"], "fontSize": "11", "fill": mcol,
                                                 "fontFamily": F_NUM, "fontWeight": "600"}),
                      h("text", None, *sub, a={"x": subx, "y": s["y"], "fontSize": "10", "fill": C.inkD,
                                               "fontFamily": F_MONO})))
    ra = {"width": "240", "height": rh, "fill": C.paper, "stroke": stroke, "strokeWidth": sw}
    if dash:
        ra["strokeDasharray"] = dash
    ra["rx"] = "2"
    return h("g", None,
             h("rect", None, a=ra),
             h("text", None, title, a={"x": "120", "y": "22", "fontSize": "11", "fill": tcol, "fontFamily": F_MONO,
                                       "textAnchor": "middle", "fontWeight": "700", "letterSpacing": "0.15em"}),
             h("text", None, name, a={"x": "120", "y": "40", "fontSize": nsize, "fill": ncol, "fontFamily": F_DISPLAY,
                                      "textAnchor": "middle", "fontStyle": "italic"}),
             h("line", None, a={"x1": "20", "y1": "52", "x2": "220", "y2": "52", "stroke": C.rule}),
             *rows, a={"transform": tr}, key="map.svg." + title)


def _power_map(ctx, L):
    arrow = {"viewBox": "0 0 10 10", "refX": "9", "refY": "5", "markerWidth": "5", "markerHeight": "5",
             "orient": "auto"}
    svg = h("svg", {"width": "100%", "height": "auto", "background": C.bg},
            h("defs", None,
              h("pattern", None, h("path", None, a={"d": "M 50 0 L 0 0 0 50", "fill": "none", "stroke": C.rule,
                                                    "strokeWidth": "0.3", "opacity": "0.4"}),
                a={"id": "grid", "width": "50", "height": "50", "patternUnits": "userSpaceOnUse"}),
              h("marker", None, h("path", None, a={"d": "M 0 0 L 10 5 L 0 10 z", "fill": C.gold}),
                a={"id": "arrow-gold", **arrow}),
              h("marker", None, h("path", None, a={"d": "M 0 0 L 10 5 L 0 10 z", "fill": C.vermillion}),
                a={"id": "arrow-red", **arrow})),
            h("rect", None, a={"width": "1100", "height": "460", "fill": "url(#grid)"}),
            *[_svg_box(ctx, L, b) for b in _BOXES],
            h("line", None, a={"x1": "300", "y1": "130", "x2": "430", "y2": "280", "stroke": C.gold, "strokeWidth": "1",
                               "strokeOpacity": "0.4", "markerEnd": "url(#arrow-gold)"}),
            h("line", None, a={"x1": "800", "y1": "130", "x2": "670", "y2": "280", "stroke": "#9b6dd0",
                               "strokeWidth": "1", "strokeOpacity": "0.4"}),
            h("line", None, a={"x1": "670", "y1": "305", "x2": "800", "y2": "305", "stroke": C.ink2, "strokeWidth": "1",
                               "strokeOpacity": "0.4", "strokeDasharray": "2 2"}),
            h("line", None, a={"x1": "430", "y1": "305", "x2": "300", "y2": "305", "stroke": C.vermillion,
                               "strokeWidth": "0.5", "strokeOpacity": "0.3", "strokeDasharray": "2 2"}),
            h("text", None, _hook(L, "svg_footer") or
              "VIETNAM CHAEBOL POWER MAP · MAY 2026 · BUILT FROM CAPITAL IQ + AGM 2026 + PRESS",
              a={"x": "550", "y": "445", "textAnchor": "middle", "fill": C.inkM, "fontSize": "9", "fontFamily": F_MONO,
                 "letterSpacing": ".2em"}),
            a={"viewBox": "0 0 1100 460"}, key="map.svg")
    lead = h("div", {"fontSize": 11, "fontFamily": F_SERIF, "color": C.inkD, "marginBottom": 18, "lineHeight": 1.7},
             "Sơ đồ dưới minh họa các kết nối ownership lớn giữa 4 nhóm chaebol và VN30. Các kết nối ",
             h("strong", {"color": C.gold}, "màu vàng"),
             " là legitimate strategic stakes (theo Capital IQ + AGM disclosures); ",
             h("strong", {"color": C.vermillion}, "màu đỏ"),
             " là các nhóm bị \"thanh lọc\" — không tham gia vào bản đồ mới.")
    src = h("div", {"marginTop": 14, "padding": 12, "background": PARCH80, "fontSize": 10, "fontFamily": F_MONO,
                    "color": C.inkD, "letterSpacing": ".05em", "lineHeight": 1.6},
            h("strong", {"color": C.gold}, "NGUỒN:"),
            " Gelex Annual Report 2025, AGM materials 2026 (GEX 1/4, GEE 8/4, VJC 27/4, VCI 30/3); Capital IQ shareholder "
            "snapshots 28/04/2026; cafef.vn / tinnhanhchungkhoan.vn / vietstock.vn 2025-2026 archives. Group "
            "\"ELIMINATED\" dựa trên thông tin chính thức về khởi tố/diện cảnh báo HOSE (DGC) và phân tích of headwind "
            "ngành (PC1, CTD).", _tag(L, "v21U"), _hook(L, "svg_source_extra"))
    return Section("◆ Power Map — Mạng Lưới Sở Hữu Chéo (Cross-Holdings)", Card(lead, svg, src, padding=20),
                   accent=C.gold, key="map.power")


# ── M · Hypothesis (5706–5720) — suy diễn chính trị: giữ nguyên văn + UNVERIFIED ──


def _hypothesis(L):
    li = [(C.gold, "Tỷ phú thế hệ mới có \"track record sạch\":",
           " Tuấn mượt (1979) — không liên quan các vụ pre-2020. GEX không có pháp lý lớn 5 năm.", "h1"),
          (C.ink2, "Nữ tỷ phú stable holdings:",
           " Bà Thảo (Sovico) tuân thủ Luật TCTD 2024 nghiêm túc; Bà Phượng (Vietcap) \"đi quốc tế hóa\" sang Singapore "
           "— tránh political concentration risk nội địa.", "h2"),
          (C.gold, "NQ79 PVN cluster:",
           " BSR +91.5%, GAS +17.8%, PLX -10% — câu chuyện trở lại với SOE refinery + Lọc Dầu sau Petrovietnam "
           "restructuring.", "h3")]
    body = h("div", {"fontSize": 13, "fontFamily": F_SERIF, "color": C.ink, "lineHeight": 1.85},
             h("strong", {"color": C.gold, "fontFamily": F_DISPLAY, "fontSize": 16, "fontStyle": "italic"},
               "Hypothesis (rủi ro suy diễn — không khẳng định):"),
             " Từ Đại hội XIV (1/2026) và sau đó, Tổng BT Tô Lâm thực thi chính sách \"đốt lò 2.0\" tập trung vào: (i) "
             "các vụ vi phạm môi trường gắn khoáng sản (DGC, có thể PC1); (ii) các CT đã có vấn đề pháp lý kéo dài (CTD "
             "post-Bolat); (iii) các chaebol cũ thân Tư Sang, X gần Trầm Bê. Đồng thời mở đường cho:",
             _hook(L, "hypo_tag"),
             h("ul", {"marginTop": 10, "paddingLeft": 24, "fontSize": 12, "lineHeight": 1.8},
               *[h("li", None, h("strong", {"color": c}, s), t, _tag(L, "v21T2" if k == "h3" else "v21U"),
                   _hook(L, "hypo_extra", k))
                 for c, s, t, k in li]),
             h("div", {"marginTop": 14, "padding": 12, "background": PARCH80, "fontSize": 11, "fontStyle": "italic",
                       "color": C.inkD, "borderLeft": "2px solid " + C.vermillion, "lineHeight": 1.7},
               h("strong", {"color": C.vermillion, "fontStyle": "normal"},
                 "Caveat — KHÔNG nhầm lẫn correlation và causation:"),
               " Việc DGC bị khởi tố cùng lúc giá cổ phiếu rơi 49.7% có thể là (a) trùng hợp kinh tế (giá lưu huỳnh "
               "+200%, mỏ tạm dừng), (b) chính trị thật sự, hoặc (c) cả hai. Không có nghĩa anh dán nhãn \"thân hữu "
               "chính trị\" cho mọi case không có chứng cứ rõ. Đây là ", h("em", None, "working hypothesis"),
               " để giúp framework decision-making, không phải chân lý tuyệt đối.", _tag(L, "v21U"),
               _hook(L, "caveat_extra")))
    return Section("❖ Hypothesis — Triều Tô Lâm và Sự Tái Định Hình Thân Hữu",
                   Card(body, accent=C.vermillion, padding=20), accent=C.vermillion, key="map.hypothesis")


def build_chaebol_sections(ctx, L):
    ents = _v(ctx, "ENTITY_21_FULL", [])
    return [_intro(L), _groups(ctx, L), _axes(ctx, L, ents), _matrix(ctx, L, ents), _claims(ctx, L, ents),
            _patterns(L), _timeline(ctx, L), _power_map(ctx, L), _hypothesis(L)]
