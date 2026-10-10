#!/usr/bin/env python3
"""
chaebol_map_tab_index — tab ★ ✪ VNINDEX và ★ ✪ VN30 (component `IndexTab`, SRC 4723–5032) của module chaebol_map.

Đặc tả: chaebol_map_spec/page_p2_index_tabs.md · hợp đồng: DESIGN.md · API: api_python.md / api_data.md.
- mode v21: tái tạo nguyên văn (hằng INDEX_DATA/BSC_CYCLES/CHU_KY_PHASES của ctx.v21; số theo luật JS; hai SVG
  phát đúng hình học JSX kể cả bất thường: overlay ⑤ không vẽ, dải ② rộng 0, mốc năm ở tuần cuối năm…).
- mode live: cùng builder; lớp dữ liệu ở chaebol_map_tab_index_live (chuỗi tuần nối tới phiên cuối, NN/TD Σ rổ
  EST, CN/TC [CẦN DATA], claim chấm lại, stance giữ V21·12/05, dòng CỔNG).
IndexTab không có state nội bộ (chỉ `tab` cấp trang) → states = [].
"""
from __future__ import annotations

import re
from datetime import date

from chaebol_map_dom import (C, F_MONO, alpha, h, jsx_text, js_round, js_string, js_sum, sign_fixed, to_fixed,
                             to_locale)
from chaebol_map_shell import Card, Section, Stat

__all__ = ["build_vnindex", "build_vn30", "mini_chart", "flow_chart", "cum_windows"]

F_SERIF_TBL = "'Source Serif 4', serif"
PURPLE = "#a78bfa"
CIRC_DEFAULT = ["①", "②", "③", "④", "⑤"]
COLORS_DEFAULT = ["#fb923c", "#34d399", "#60a5fa", "#a78bfa", "#f87171"]
PAD = 36
S2_SUB_V21 = ("Inline SVG · 5 chu kỳ tăng giá BSC framework: ① 2005-06 (+346%) · ② 2009 (+165%) · ③ 2016-18 "
              "(+130%) · ④ 2020-22 (+131%) · ⑤ T4/25-Nay (+61%)")
S3_SUB_V21 = ("KL khớp ròng cộng dồn: Cá nhân (gold) · Tổ chức (blue) · Tự doanh (purple) · Nước ngoài (green) · "
              "zero-sum constraint")
S5_SUB_V21 = "Phase logic + 5 BSC cycles + current readings (sourced from SuperDashboard Chu kỳ tab)"
WIN_LABELS_V21 = ("5 tuần (4-8/5/26)", "30 tuần (~7 tháng)", "60 tuần (~14 tháng)")
METHOD_V21 = (
    ("Toàn Vũ Pillar IV", " — 4-channel KL khớp ròng (cá nhân/tổ chức/tự doanh/nước ngoài). Sum constraint ≈ 0 "
                          "zero-sum."),
    ("Phú SSI VWAP cụm", " — concept áp dụng cho per-ticker (chưa applicable cho index aggregate)."),
    ("BSC 5 chu kỳ tăng giá", " — 2005-2026 framework với P/E peak + GTGD reference."),
    ("Goldman 4 phases", " — ACCUMULATION/MARKUP/DISTRIBUTION/MARKDOWN từ Wyckoff phase logic."),
    ("Capital IQ holdings", " — không applicable cho index, dùng cho per-ticker constituents (VN30 components)."),
    ("SuperDashboard Chu kỳ tab", " — cross-validated với VN100_Market_Analysis weekly report (latest 9/5/26 v4.38)."),
)
CODE_LINES_V21 = (
    "FiinTrade source files (10/5/2026 export):",
    "• FiinTrade_Phân_Loại_Nhà_Đầu_Tư_VNINDEX_20260510 (2).xlsx · 1327 weekly bars",
    "• FiinTrade_Phân_Loại_Nhà_Đầu_Tư_VN30_20260510.xlsx · 737 weekly bars",
    "• FiinTrade_Đặt_Lệnh_VNINDEX/VN30_20260510.xlsx",
    "• FiinTrade_Nước_Ngoài_VNINDEX_20260510.xlsx",
    "• FiinTrade_Tự_Doanh_VNINDEX_20260510.xlsx",
)
READING_V21 = jsx_text("""
              GTGD HSX ATH 36,814 tỷ/phiên cao kỷ lục lịch sử. P/E peak 4 chu kỳ trước trung bình 30.6× — hiện ~14× nên chưa quá định giá nhưng GTGD-driven momentum đã xuất hiện UTAD signal Q3/26 watch (Wyckoff Upthrust After Distribution).
              SSI Research cập nhật 9/5: base case mục tiêu 1,920 (+0.3%), bear 1,650 (-13.8%) — risk/reward asymmetric XẤU.
              VCB P/B 2.0× = 10-yr low → best deep-value pick trong môi trường định giá đỉnh.
            """)
READING_STRONG = "Chu kỳ ⑤ T4/25-Nay (+61%) đang ở giai đoạn LATE PHASE 2 → TRANSITIONING TO PHASE 3."
BSC_TITLE = "5 CHU KỲ TĂNG GIÁ — BSC FRAMEWORK"


def build_vnindex(ctx):
    return _build(ctx, "VNINDEX")


def build_vn30(ctx):
    return _build(ctx, "VN30")


# ── hằng từ ctx.v21 ──────────────────────────────────────────────────────────


def _consts(ctx):
    v = ctx.v21 or {}
    circ = v.get("IndexTab.jsx@L4971") or v.get("MiniChart.jsx@L4805") or CIRC_DEFAULT
    return {"INDEX_DATA": v.get("INDEX_DATA") or {}, "BSC": v.get("BSC_CYCLES") or [],
            "PHASES": v.get("CHU_KY_PHASES") or [], "COLORS": v.get("MiniChart.colors") or COLORS_DEFAULT,
            "CIRC": circ if len(circ) >= 5 else CIRC_DEFAULT}


def _build(ctx, index):
    K = _consts(ctx)
    rows = K["INDEX_DATA"].get("VN30_PL_W" if index == "VN30" else "VNINDEX_PL_W") or []
    if not rows:
        ctx.warn("thiếu INDEX_DATA.%s_PL_W trong v21_const — tab trống" % index)
        return {"root": h("div", {"color": C.vermillion, "fontFamily": F_MONO, "fontSize": 11},
                          "[thiếu INDEX_DATA %s trong v21_const.json]" % index), "states": []}
    L = None
    if ctx.live:
        try:  # lớp live tách tệp (luật repo ≤ ~800 dòng); nhập trễ để tránh vòng nhập
            import chaebol_map_tab_index_live as LV
        except ImportError as exc:
            ctx.warn("thiếu chaebol_map_tab_index_live.py (%s) — giữ bản V21" % exc)
        else:
            L = LV.Live(ctx, index, rows, K)
    label = "VN30" if index == "VN30" else "VN-Index"
    hc = PURPLE if index == "VN30" else C.gold
    root = h("div", None,
             _s1_header(rows, label, hc, L),
             _s2_price(rows, label, hc, index, K, L),
             _s3_flow(rows, L),
             _s4_table(rows, L),
             _s5_cycle(rows, label, K, L),
             _s6_method(L),
             key="idx." + index.lower())
    out = {"root": root, "states": []}
    if L is not None:
        out["csv"] = L.csv()
    return out


# ── S1 · Header + 4 Stat ─────────────────────────────────────────────────────


def years_covered(d0, d1):
    """((new Date(d1) − new Date(d0)) / (365.25·86400000)).toFixed(1) — ms nguyên chia double như V8."""
    ms = (date.fromisoformat(d1) - date.fromisoformat(d0)).days * 86400000
    return to_fixed(ms / (365.25 * 86400000), 1)


def _s1_header(rows, label, hc, L):
    first, last = rows[0], rows[-1]
    title = "%s — Pillar IV Flow & Chu kỳ" % label
    if L is not None:
        return Section(title, L.s1_grid(hc), accent=hc, sub=L.s1_sub(), key="idx.s1")
    sub = "%s weekly bars · %s năm · FiinTrade verified %s→2026-05-08 · NgườiQuanSát forward ≥09/05/2026" % (
        len(rows), years_covered(first[0], last[0]), first[0])
    grid = h("div", {"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)", "gap": 12, "marginBottom": 16},
             Stat("GIÁ ĐÓNG CỬA (8/5)", to_locale(last[1], "en-US", max_frac=2),
                  sub=sign_fixed(last[2], 2) + "%", color=C.forest if last[2] >= 0 else C.vermillion),
             Stat("TỪ ĐÁY LỊCH SỬ", "+" + to_fixed(((last[1] / first[1]) - 1) * 100, 0) + "%",
                  sub="vs %s (%s)" % (first[0], js_string(first[1])), color=C.gold),
             Stat("WEEKLY BARS", js_string(len(rows)), sub="%s-%s" % (first[0][:4], last[0][:4]), color=C.ink2),
             Stat("DATA SOURCE", "DUAL", sub="FiinTrade ≤8/5 · NQS ≥9/5", color=hc))
    return Section(title, grid, accent=hc, sub=sub, key="idx.s1")


# ── S2 · MiniChart ───────────────────────────────────────────────────────────


def _svg(w, hh, *kids, key=None):
    return h("svg", {"display": "block", "maxWidth": "100%", "height": "auto"}, *kids,
             a={"width": w, "height": hh, "viewBox": "0 0 %s %s" % (w, hh)}, key=key)


def _txt_mono(x, y, anchor, fill, *kids):
    return h("text", None, *kids, a={"x": x, "y": y, "textAnchor": anchor, "fontSize": "9", "fill": fill,
                                     "fontFamily": F_MONO})


def cycle_bounds(period):
    """(startYear, endYear) như JSX: regex năm đầu; năm cuối `/-T?\\d*\\/?(\\d{4})/` hoặc start+2."""
    m = re.search(r"(\d{4})", period)
    start = int(m.group(1)) if m else 2005
    m2 = re.search(r"-T?\d*/?(\d{4})", period)
    return start, (int(m2.group(1)) if m2 else start + 2)


def year_ticks(rows):
    """yearMap của JSX (năm %3 bị ghi đè bằng chỉ số CUỐI năm; `!yearMap[y]` đúng cả khi = 0) → [(năm, i)]."""
    ym = {}
    for i, r in enumerate(rows):
        y = r[0][:4]
        if not ym.get(y) or (int(y) % 3 == 0 and i > ym[y]):
            ym[y] = i
    years = [y for y in sorted(ym, key=int) if int(y) % 3 == 0][:12]
    return [(y, ym[y]) for y in years]


def mini_chart(rows, w=1200, hh=300, color=C.gold, accent="#5b8db8", cycles=None, colors=COLORS_DEFAULT,
               circ=CIRC_DEFAULT, marker=None):
    """MiniChart (SRC 4750–4815). rows = [[ngày, giá, …]]; cycles = BSC_CYCLES khi cyclesOverlay (chỉ VNINDEX).
    marker (live) = (chỉ số hàng, nhãn) → vạch dọc đánh dấu điểm nối nguồn.
    cycle có khoá "_ab" (live) = (chỉ số hàng đầu, cuối) → dải vẽ theo ngày thay cho luật năm của JSX."""
    n = len(rows)
    prices = [r[1] for r in rows]
    mn, mx = min(prices), max(prices)

    def xs(i):
        return PAD + (i / (n - 1)) * (w - PAD * 2)

    def ys(p):
        return PAD + (1 - (p - mn) / (mx - mn)) * (hh - PAD * 2)

    path = " ".join(("M" if i == 0 else "L") + to_fixed(xs(i), 1) + "," + to_fixed(ys(p), 1)
                    for i, p in enumerate(prices))
    kids = []
    for i in range(5):
        p = mn + (mx - mn) * i / (5 - 1)
        y = ys(p)
        kids.append(h("g", None,
                      h("line", None, a={"x1": PAD, "y1": y, "x2": w - PAD, "y2": y, "stroke": "#26242c",
                                         "strokeWidth": "0.5"}),
                      _txt_mono(PAD - 4, y + 3, "end", "#5a564d", js_string(js_round(p)))))
    for y, i in year_ticks(rows):
        x = xs(i)
        kids.append(h("g", None,
                      h("line", None, a={"x1": x, "y1": PAD, "x2": x, "y2": hh - PAD, "stroke": "#26242c",
                                         "strokeWidth": "0.3", "strokeDasharray": "2,2"}),
                      _txt_mono(x, hh - PAD + 14, "middle", "#5a564d", y)))
    for i, cy in enumerate(cycles or ()):
        ly = PAD + 12
        if cy.get("_ab"):   # dải theo ngày kết thúc ở đỉnh chu kỳ → đường giá đi qua mép trên: nhãn đặt ở đáy dải
            a, b = cy["_ab"]
            ly = hh - PAD - 6
        else:
            y0, y1 = cycle_bounds(cy["period"])
            a = next((j for j, r in enumerate(rows) if int(r[0][:4]) >= y0), -1)
            b = next((j for j, r in enumerate(rows) if int(r[0][:4]) >= y1), -1)
        if a < 0 or b < 0:
            continue
        xa, xb = xs(a), xs(b)
        kids.append(h("g", None,
                      h("rect", None, a={"x": xa, "y": PAD, "width": xb - xa, "height": hh - PAD * 2,
                                         "fill": colors[i], "opacity": "0.10"}),
                      h("text", None, circ[i], " ", cy["chg"],
                        a={"x": (xa + xb) / 2, "y": ly, "textAnchor": "middle", "fontSize": "9",
                           "fontWeight": "700", "fill": colors[i], "opacity": "0.9"})))
    if marker is not None:
        kids.append(_marker(xs(marker[0]), hh, marker[1]))
    kids.append(h("path", None, a={"d": path, "fill": "none", "stroke": color, "strokeWidth": "1.6"}))
    kids.append(h("circle", None, a={"cx": xs(n - 1), "cy": ys(prices[-1]), "r": "3", "fill": accent}))
    return _svg(w, hh, *kids, key="idx.minichart")


def _marker(x, hh, label):
    """(live) vạch nối nguồn: đứt nét ochre + nhãn nhỏ ở mép trên."""
    return h("g", None,
             h("line", None, a={"x1": x, "y1": PAD - 6, "x2": x, "y2": hh - PAD, "stroke": C.ochre,
                                "strokeWidth": "0.6", "strokeDasharray": "1,3"}),
             h("text", None, label, a={"x": x - 4, "y": PAD - 10, "textAnchor": "end", "fontSize": "8",
                                       "fill": C.ochre, "fontFamily": F_MONO}))


def _s2_price(rows, label, hc, index, K, L):
    title = "📈 %s Weekly Price + 5 Chu kỳ BSC overlay" % label
    cycles = K["BSC"] if index == "VNINDEX" else None
    if L is not None:
        chart = L.price_chart(hc, cycles)
        return Section(title, Card(chart, L.price_caption()), accent=C.gold, sub=L.s2_sub(), key="idx.s2")
    chart = mini_chart(rows, 1200, 300, hc, "#5b8db8", cycles, K["COLORS"], K["CIRC"])
    return Section(title, Card(chart), accent=C.gold, sub=S2_SUB_V21, key="idx.s2")


# ── S3 · FlowChart ───────────────────────────────────────────────────────────

FLOW_SERIES = (("Cá nhân", "#caa75c", "1.4"), ("Tổ chức", "#5b8db8", "1.4"), ("Tự doanh", "#a78bfa", "1.4"),
               ("Nước ngoài", "#3d7a4e", "1.6"))


def flow_series(rows):
    """Cộng dồn tuần tự 4 kênh (cột 3..6); giá trị None (live: kênh không có số) → điểm None (đường dừng)."""
    out = [[], [], [], []]
    s = [0, 0, 0, 0]
    for r in rows:
        for k in range(4):
            v = r[3 + k]
            if v is None or s[k] is None:
                s[k] = None
            else:
                s[k] = s[k] + v
            out[k].append(s[k])
    return out


def flow_chart(rows, w=1200, hh=280, legend=None, marker=None):
    """FlowChart (SRC 4818–4860): 4 đường cộng dồn chồng (không stack), vạch 0, nhãn max/min, chú giải.
    legend (live) = hàm (w, sums) → nút g chú giải thay khối 4 dòng gốc."""
    n = len(rows)
    cum = flow_series(rows)
    allv = [v for arr in cum for v in arr if v is not None]
    mn, mx = min(allv), max(allv)

    def xs(i):
        return PAD + (i / (n - 1)) * (w - PAD * 2)

    def ys(v):
        return PAD + (1 - (v - mn) / (mx - mn)) * (hh - PAD * 2)

    def mk(arr):
        return " ".join(("M" if i == 0 else "L") + to_fixed(xs(i), 1) + "," + to_fixed(ys(v), 1)
                        for i, v in enumerate(arr) if v is not None)

    yz = ys(0)
    kids = [h("line", None, a={"x1": PAD, "y1": yz, "x2": w - PAD, "y2": yz, "stroke": "#5a564d",
                               "strokeWidth": "0.7", "strokeDasharray": "3,3"}),
            _txt_mono(PAD - 4, yz + 3, "end", "#5a564d", "0"),
            _txt_mono(PAD - 4, PAD + 8, "end", "#3d7a4e", js_string(js_round(mx))),
            _txt_mono(PAD - 4, hh - PAD, "end", "#c5392f", js_string(js_round(mn)))]
    if marker is not None:
        kids.append(_marker(xs(marker[0]), hh, marker[1]))
    for (_, col, sw), arr in zip(FLOW_SERIES, cum):
        kids.append(h("path", None, a={"d": mk(arr), "fill": "none", "stroke": col, "strokeWidth": sw,
                                        "opacity": "0.95"}))
    sums = [next((v for v in reversed(arr) if v is not None), None) for arr in cum]
    if legend is not None:
        kids.append(legend(w, sums))
    else:
        kids.append(h("g", None,
                      h("rect", None, a={"x": "0", "y": "0", "width": "200", "height": "68", "fill": "#13131a",
                                         "stroke": "#26242c", "strokeWidth": "0.5", "opacity": "0.95"}),
                      *[h("text", None, "━ %s: " % nm, to_fixed(s, 0), "M",
                          a={"x": "6", "y": str(14 * (k + 1)), "fontSize": "9", "fill": col, "fontFamily": F_MONO})
                        for k, ((nm, col, _), s) in enumerate(zip(FLOW_SERIES, sums))],
                      a={"transform": "translate(%s, %s)" % (w - 220, PAD - 4)}))
    return _svg(w, hh, *kids, key="idx.flowchart")


def _s3_flow(rows, L):
    title = "🌊 Cumulative Flow 4 channels — Toàn Vũ Pillar IV"
    if L is not None:
        return Section(title, Card(L.flow_chart(), L.flow_caption()), accent=C.forest, sub=L.s3_sub(), key="idx.s3")
    return Section(title, Card(flow_chart(rows, 1200, 280)), accent=C.forest, sub=S3_SUB_V21, key="idx.s3")


# ── S4 · bảng cộng dồn ───────────────────────────────────────────────────────


def cum_windows(rows, ns=(5, 30, 60)):
    """{ca,tc,td,nn} = reduce tuần tự trên rows.slice(-n) (cột 3..6) — KHÔNG sum()/fsum."""
    return [{k: js_sum(r[i] for r in rows[-n:]) for k, i in (("ca", 3), ("tc", 4), ("td", 5), ("nn", 6))} for n in ns]


TH4 = (("WINDOW", "left", C.inkD), ("CÁ NHÂN (M)", "right", C.gold), ("TỔ CHỨC (M)", "right", C.ink2),
       ("TỰ DOANH (M)", "right", PURPLE), ("NƯỚC NGOÀI (M)", "right", C.forest),
       ("SUM (zero-check)", "right", C.inkD))


def th4(label, align, color):
    return h("th", {"padding": "8px 10px", "textAlign": align, "color": color, "fontWeight": 600,
                    "letterSpacing": ".18em", "fontSize": 9}, label)


def zfix(s):
    """(live) số làm tròn ra 0 không mang dấu: '-0.0'/'+0.0' → '0.0' (V21 giữ '-0.0' như toFixed của JS)."""
    bare = s.lstrip("+-")
    return bare if bare.strip("0.") == "" else s


def td_num(v, extra=None, clean=False):
    txt = sign_fixed(v, 1)
    return h("td", {"padding": "10px 10px", "textAlign": "right", "color": C.forest if v >= 0 else C.vermillion,
                    "fontWeight": 700}, zfix(txt) if clean else txt, extra)


def td_label(lbl):
    return h("td", {"padding": "10px 10px", "color": C.ink, "fontWeight": 600}, lbl)


def td_sum(*kids):
    return h("td", {"padding": "10px 10px", "textAlign": "right", "color": C.inkD, "fontFamily": F_MONO}, *kids)


def cum_row(lbl, c, tiers=None, clean=False):
    """Một hàng bảng S4. tiers (live) = hàm () → nút nhãn bậc cho mỗi ô số (V21 đóng băng);
    clean (live) = in số làm tròn ra 0 không dấu."""
    t = tiers or (lambda: None)
    s = to_fixed(c["ca"] + c["tc"] + c["td"] + c["nn"], 1)
    return h("tr", {"borderBottom": "1px solid " + alpha(C.rule, "80")},
             td_label(lbl), *[td_num(c[k], t(), clean) for k in ("ca", "tc", "td", "nn")],
             td_sum(zfix(s) if clean else s, t()))


def _s4_table(rows, L):
    body = L.s4_rows() if L is not None else [cum_row(lbl, c) for lbl, c in zip(WIN_LABELS_V21, cum_windows(rows))]
    tbl = h("table", {"width": "100%", "borderCollapse": "collapse", "fontFamily": F_MONO, "fontSize": 11},
            h("thead", None, h("tr", {"borderBottom": "1px solid " + C.rule}, *[th4(*x) for x in TH4])),
            h("tbody", None, *body))
    kids = [tbl, L.s4_caption() if L is not None else None]
    return Section("📊 Flow cumulative — 5w / 30w / 60w", *kids, accent=C.ochre, key="idx.s4")


# ── S5 · chu kỳ ──────────────────────────────────────────────────────────────


def signal_color(sig):
    return C.gold if "TRANSITIONING" in sig else (C.ochre if "UTAD" in sig else C.inkD)


def phase_card(p, mark=None, sig=None):
    """sig (live) = chữ hiển thị thay p['signal'] (chỉ dịch chữ giữ chỗ, màu vẫn theo signal gốc)."""
    return Card(
        h("div", {"fontSize": 9, "letterSpacing": ".2em", "color": C.inkM, "fontFamily": F_MONO, "marginBottom": 6},
          p["name"]),
        h("div", {"fontSize": 11.5, "color": C.ink, "lineHeight": 1.6, "marginBottom": 8}, p["desc"]),
        h("div", {"fontSize": 10.5, "color": signal_color(p["signal"]), "fontFamily": F_MONO, "letterSpacing": ".1em"},
          "SIGNAL: ", p["signal"] if sig is None else sig, mark))


TH_BSC = (("#", "left", C.inkD), ("PERIOD", "left", C.inkD), ("CHANGE", "right", C.gold), ("PEAK", "right", C.inkD),
          ("P/E PEAK", "right", C.inkD), ("GTGD", "right", C.inkD), ("DRIVER", "left", C.inkD))
_TD = {"padding": "9px 8px"}


def _jsv(x):
    """`${x}` của JSX: số → String(n); chuỗi giữ nguyên ('~14.0×' → '~14.0××' sau khi nối '×')."""
    return js_string(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else str(x)


def bsc_row(i, c, circ, cells=None):
    """Một hàng bảng BSC. cells (live) = dict ô → danh sách con thay nội dung V21."""
    cells = cells or {}
    mono = {"fontFamily": F_MONO, "fontSize": 10.5}
    return h("tr", {"borderBottom": "1px solid " + alpha(C.rule, "80"),
                    "background": alpha(C.gold, "10") if i == 4 else "transparent"},
             h("td", {**_TD, "color": C.gold if i == 4 else C.ink, "fontWeight": 700 if i == 4 else 500},
               circ[i], " ★" if i == 4 else ""),
             h("td", {**_TD, "color": C.ink, **mono}, cells.get("period", c["period"])),
             h("td", {**_TD, "textAlign": "right", "color": C.forest, "fontWeight": 700}, cells.get("chg", c["chg"])),
             h("td", {**_TD, "textAlign": "right", "color": C.ink, **mono}, cells.get("peak", c["peak"])),
             h("td", {**_TD, "textAlign": "right", "color": C.ochre, **mono},
               cells.get("pe", [_jsv(c["pe_peak"]), "×"])),
             h("td", {**_TD, "textAlign": "right", "color": C.ink2, **mono}, cells.get("gtgd", c["gtgd"])),
             h("td", {**_TD, "color": C.inkD, "fontSize": 10.5}, cells.get("driver", c["driver"])))


def reading_v21(label, last_close):
    return h("div", {"fontSize": 11.5, "color": C.ink, "lineHeight": 1.7},
             h("strong", {"color": C.gold}, READING_STRONG), " ", label, " đóng cửa ATH 8/5 = ",
             h("strong", {"color": C.forest}, to_fixed(last_close, 2)), " (FiinTrade verified). " + READING_V21)


def _s5_cycle(rows, label, K, L):
    grid = h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 14, "marginBottom": 14},
             *[phase_card(p, L.v21_mark(), L.phase_signal(p["signal"])) if L is not None else phase_card(p)
               for p in K["PHASES"]])
    bsc_rows = [bsc_row(i, c, K["CIRC"], L.bsc_cells(i, c) if L is not None else None)
                for i, c in enumerate(K["BSC"])]
    table = h("table", {"width": "100%", "borderCollapse": "collapse", "fontFamily": F_SERIF_TBL, "fontSize": 11.5},
              h("thead", None, h("tr", {"borderBottom": "1px solid " + C.rule},
                                 *[h("th", {"padding": "6px 8px", "textAlign": al, "color": co, "fontWeight": 600,
                                            "fontSize": 10, "letterSpacing": ".12em"}, t) for t, al, co in TH_BSC])),
              h("tbody", None, *bsc_rows))
    body = L.reading(label) if L is not None else reading_v21(label, rows[-1][1])
    title_r = L.reading_title() if L is not None else "★ READING HÔM NAY (10/5/2026)"
    callout = h("div", {"marginTop": 12, "padding": "10px 14px", "background": alpha(C.gold, "15"),
                        "border": "1px solid " + alpha(C.gold, "40"), "borderRadius": 3},
                h("div", {"fontSize": 10, "letterSpacing": ".2em", "color": C.gold, "fontFamily": F_MONO,
                          "marginBottom": 6, "fontWeight": 700}, title_r),
                body)
    card = Card(h("div", {"fontSize": 9, "letterSpacing": ".2em", "color": C.gold, "fontFamily": F_MONO,
                          "marginBottom": 8}, L.bsc_title(BSC_TITLE) if L is not None else BSC_TITLE),
                table, callout)
    extra = L.phase_note() if L is not None else None
    return Section("🔄 Chu kỳ phân tích — Toàn Vũ × Wyckoff × BSC framework", grid, extra, card, accent=C.gold,
                   sub=L.s5_sub() if L is not None else S5_SUB_V21, key="idx.s5")


# ── S6 · phương pháp + cutover ───────────────────────────────────────────────

_CARD_T = {"fontSize": 9, "letterSpacing": ".2em", "color": C.gold, "fontFamily": F_MONO, "marginBottom": 8}
_PARA = {"fontSize": 11.5, "color": C.ink, "lineHeight": 1.7, "marginBottom": 10}


def method_list(items):
    """items = [(chữ đậm, phần sau (chuỗi hoặc list con))]."""
    return h("ul", {"margin": 0, "paddingLeft": 18, "fontSize": 11.5, "lineHeight": 1.85, "color": C.inkD},
             *[h("li", None, h("strong", {"color": C.ink}, b), rest) for b, rest in items])


def code_box(lines):
    kids = []
    for i, ln in enumerate(lines):
        kids.append(ln)
        if i < len(lines) - 1:
            kids.append(h("br"))
    return h("div", {"fontSize": 10.5, "color": C.inkD, "fontFamily": F_MONO, "padding": "8px 10px",
                     "background": C.parch, "borderRadius": 3}, *kids)


def _s6_method(L):
    if L is not None:
        items, paras, lines, head = L.method_items(METHOD_V21), L.cutover_paras(), L.code_lines(CODE_LINES_V21), \
            L.cong_block()
    else:
        items, lines, head = METHOD_V21, CODE_LINES_V21, None
        paras = [h("div", _PARA, h("span", {"color": C.gold, "fontWeight": 700}, "≤ 08/05/2026 (historical):"),
                   " FiinTrade Pro xlsx exports verified — paid-for, KEPT."),
                 h("div", _PARA, h("span", {"color": C.forest, "fontWeight": 700}, "≥ 09/05/2026 (forward):"),
                   " NgườiQuanSát.vn (FREE public) — XHR PhanLoaiNDTHistory verified 9/5. Next bar: ",
                   h("strong", None, "Mon 11/05/2026"), " (next trading session sau Sat 9/5 + Sun 10/5 nghỉ).")]
    grid = h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 14},
             Card(h("div", _CARD_T, "METHODOLOGY (cùng các tab khác)"), method_list(items)),
             Card(h("div", _CARD_T, "SOURCE CUTOVER POLICY"), *paras, code_box(lines)))
    return Section("📚 Phương pháp luận + Cutover policy", head, grid, accent=C.inkD, key="idx.s6")
