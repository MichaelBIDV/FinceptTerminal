#!/usr/bin/env python3
"""
chaebol_map_tab_codong_deep_chart — `ChaebolCanvasChart` (SRC 3595–3881) cho Deep-dive 10 sub-tab của tab codong.

Đặc tả: chaebol_map_spec/page_p3b_deepdive10.md §5. Phát SVG inline đúng hình học JSX (viewBox + toạ độ tính bằng
số học double y hệt JS; chuỗi `d` của path và nhãn qua luật số JS của chaebol_map_dom).

Ba chế độ (xét theo thứ tự như JSX):
  A  tuần thật  820×380  — WEEKLY_OHLCV[tk] > 10 dòng (v21: VIC, VHM, MSN, MSR); live: chuỗi tuần vc_lk điều chỉnh
  B  dải cụm    780×340  — deep.cluster.clusters có phần tử
  C  trống               — «Chart data chưa available cho {tk}»

Module chỉ dựng hình; số liệu sống (live) do chaebol_map_tab_codong_deep_live chuẩn bị rồi truyền vào `mode_a`.
Trong SVG không có nhãn bậc dạng span (chữ SVG chỉ nhận chuỗi) — nhãn bậc đặt ở dòng readout HTML phía trên.
"""
from __future__ import annotations

from chaebol_map_dom import C, F_DISPLAY, F_MONO, h, js_string, to_fixed

__all__ = ["chart_mode", "canvas_chart", "mode_a", "mode_b", "mode_c", "v21_bars", "frame", "js_slice", "jsv",
           "truthy", "is_num"]

WRAP = {"background": C.parch + "40", "border": "1px solid " + C.rule, "borderRadius": 4, "padding": "14px 16px 8px"}
HEAD = {"display": "flex", "justifyContent": "space-between", "alignItems": "baseline", "marginBottom": 10,
        "flexWrap": "wrap", "gap": 8}
EYEBROW = {"fontSize": 9, "letterSpacing": ".3em", "color": C.inkM, "fontFamily": F_MONO}
LABEL = {"fontSize": 13, "color": C.ink, "fontFamily": F_DISPLAY, "fontStyle": "italic", "fontWeight": 600,
         "marginTop": 2}
READOUT = {"fontSize": 9.5, "color": C.inkD, "fontFamily": F_MONO, "letterSpacing": ".05em"}
SVG_STYLE = {"display": "block", "background": C.bg, "borderRadius": 3}
EMPTY = {"padding": "24px 14px", "textAlign": "center", "color": C.inkD, "fontStyle": "italic", "fontSize": 11}
LEGEND_A = "━ Close · ─ VWAP6M (green) · ─ VWAP12M (amber) · ─ ─ VWAP24M (red) · ▮ Volume · 104 weeks"
LEGEND_B = "▮ Cluster band (height = vol intensity) · ▬▬ HI/STOP · ─ ─ VWAP · ━ NOW"


# ── Luật JS nhỏ dùng chung với module chính ─────────────────────────────────


def is_num(x):
    """typeof x === 'number' (JSON: int/float, không bool)."""
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def truthy(x):
    """Truthiness JS cho giá trị JSON (None/0/''/False/NaN → False; list/dict rỗng vẫn True)."""
    if x is None or x is False:
        return False
    if is_num(x):
        return x == x and x != 0
    if isinstance(x, str):
        return x != ""
    return True


def jsv(x, missing=False):
    """Ghép chuỗi kiểu JS (`x + 'K'`, `${x}`): số → String(n); None → 'null'; khoá thiếu (missing) → 'undefined'."""
    if missing:
        return "undefined"
    if x is None:
        return "null"
    if isinstance(x, bool):
        return "true" if x else "false"
    if is_num(x):
        return js_string(x)
    return str(x)


def js_slice(s, a, b=None):
    """String.prototype.slice/substring trên đơn vị UTF-16 (không phải code point như Python)."""
    s = "" if s is None else str(s)
    u = s.encode("utf-16-le")
    n = len(u) // 2
    a = max(0, min(n, a if a >= 0 else n + a))
    b = n if b is None else max(0, min(n, b if b >= 0 else n + b))
    if b <= a:
        return ""
    return u[2 * a:2 * b].decode("utf-16-le", errors="surrogatepass")


def _t(x, y, text, size, fill, anchor=None, weight=None):
    a = {"x": x, "y": y}
    if anchor:
        a["textAnchor"] = anchor
    a["fontSize"] = size
    a["fontFamily"] = F_MONO
    if weight is not None:
        a["fontWeight"] = weight
    a["fill"] = fill
    return h("text", None, text, a=a)


def _line(x1, y1, x2, y2, stroke, width, dash=None, opacity=None):
    a = {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "stroke": stroke, "strokeWidth": width}
    if dash:
        a["strokeDasharray"] = dash
    if opacity is not None:
        a["opacity"] = opacity
    return h("line", None, a=a)


def frame(eyebrow, label, readout, svg_children, W, H):
    """Khung chung Mode A/B: div nền parch40 · hàng tiêu đề (eyebrow + nhãn pha | readout) · svg viewBox."""
    return h("div", WRAP,
             h("div", HEAD,
               h("div", None, h("div", EYEBROW, eyebrow), h("div", LABEL, label)),
               h("div", READOUT, readout)),
             h("svg", SVG_STYLE, *svg_children, a={"viewBox": "0 0 %d %d" % (W, H), "width": "100%", "height": "auto"}))


# ── Mode A ──────────────────────────────────────────────────────────────────


def v21_bars(rows):
    """WEEKLY_OHLCV[tk] → bars {date, close, vol, vwap6m, vwap12m, vwap24m} (r[3..6] không vẽ)."""
    return [{"date": r[0], "close": r[1], "vol": r[2], "vwap6m": r[7], "vwap12m": r[8], "vwap24m": r[9]} for r in rows]


def _yfn(yMin, yRange, padT, plotH):
    def yFor(v):
        if not is_num(v):
            return float("nan")
        return padT + (1 - (v - yMin) / yRange) * plotH
    return yFor


def _path(pts):
    """`${i===0?'M':'L'}${x} ${y}` nối ' ' — điểm y NaN (thiếu số) cắt đường: điểm kế tiếp mở lại bằng 'M'."""
    out, pen = [], False
    for x, y in pts:
        if y != y:
            pen = False
            continue
        out.append(("L" if pen else "M") + js_string(x) + " " + js_string(y))
        pen = True
    return " ".join(out)


def mode_a(tk, bars, phase, anchor, eyebrow=None, readout=None, label=None, legend=LEGEND_A, levels=None):
    """Mode A (SRC 3599–3742). bars: list dict (K, M cp). phase/anchor: số V21 (hoặc đã quy đổi ở live).
    levels = {"hi": (giá trị, chữ), "stop": (…), "anchor": (…)} ghi đè nhãn chữ trong SVG (live); None → JSX."""
    W, H, padL, padR, padT, padB = 820, 380, 56, 110, 28, 50
    plotW, plotH = W - padL - padR, H - padT - padB
    n = len(bars)
    phase = phase or {}
    if levels is None:                     # V21: mốc nguyên văn
        lv = {}
        hi, base, stop, anc = phase.get("hi"), phase.get("base"), phase.get("stop"), anchor
    else:                                  # live: chỉ mốc đã quy đổi quyền (thiếu → không vẽ)
        lv = levels
        hi, base, stop, anc = ((lv.get(k) or (None,))[0] for k in ("hi", "base", "stop", "anchor"))
    ys = [b["close"] for b in bars if is_num(b["close"])] + [v for v in (hi, base, stop, anc) if is_num(v)]
    yMin = min(ys) * 0.92
    yMax = max(ys) * 1.05
    yRange = yMax - yMin
    yFor = _yfn(yMin, yRange, padT, plotH)

    def xFor(i):
        return padL + (plotW / (n - 1)) * i
    maxVol = max([(b["vol"] if truthy(b["vol"]) else 0) for b in bars] or [0])
    volH = 36
    volY = H - padB - volH

    def volYFor(v):
        return H - padB - (v / (maxVol or 1)) * volH
    kids = []
    for i in range(7):
        v = yMin + (yRange * i / 6)
        y = yFor(v)
        kids.append(h("g", None, _line(padL, y, W - padR, y, C.rule, 0.5, "2 4", 0.4),
                      _t(padL - 6, y + 3, to_fixed(v, 0) + "K", 9, C.inkM, "end")))
    for i in range(0, n, 13):
        x = xFor(i)
        kids.append(h("g", None, _line(x, padT, x, H - padB, C.rule, 0.4, None, 0.25),
                      _t(x, H - padB + 12, js_slice(bars[i]["date"], 2, 7), 8.5, C.inkM, "middle")))
    if truthy(anc):
        a_txt = lv["anchor"][1] if "anchor" in lv else "ANCHOR " + jsv(anc) + "K"
        kids.append(h("g", None,
                      h("rect", None, a={"x": padL, "y": yFor(anc * 1.03), "width": plotW,
                                         "height": yFor(anc * 0.97) - yFor(anc * 1.03), "fill": C.gold,
                                         "opacity": 0.07}),
                      _line(padL, yFor(anc), W - padR, yFor(anc), C.gold, 1, "6 3", 0.55),
                      _t(W - padR + 4, yFor(anc) + 3, a_txt, 9, C.gold, None, 700)))
    if truthy(hi):
        kids.append(h("g", None, _line(padL, yFor(hi), W - padR, yFor(hi), C.forest, 1.2, "10 4"),
                      _t(padL + 4, yFor(hi) - 4, lv["hi"][1] if "hi" in lv else "HI " + jsv(hi) + "K", 9, C.forest,
                         None, 700)))
    if truthy(stop):
        kids.append(h("g", None, _line(padL, yFor(stop), W - padR, yFor(stop), C.vermillion, 1.2, "10 4"),
                      _t(padL + 4, yFor(stop) + 12, lv["stop"][1] if "stop" in lv else "STOP " + jsv(stop) + "K", 9,
                         C.vermillion, None, 700)))
    for key, color, width, op, dash in (("vwap24m", C.vermillion, 1.5, 0.75, "6 3"), ("vwap12m", C.ochre, 1.5, 0.85, None),
                                        ("vwap6m", C.forest, 1.8, 0.95, None)):
        a = {"d": _path((xFor(i), yFor(b[key])) for i, b in enumerate(bars)), "fill": "none", "stroke": color,
             "strokeWidth": width, "opacity": op}
        if dash:
            a["strokeDasharray"] = dash
        kids.append(h("path", None, a=a))
    kids.append(h("path", None, a={"d": _path((xFor(i), yFor(b["close"])) for i, b in enumerate(bars)), "fill": "none",
                                   "stroke": C.ink, "strokeWidth": 1.2, "opacity": 0.85}))

    def up(i):
        prev = bars[i - 1]["close"] if i > 0 else bars[i]["close"]
        return is_num(bars[i]["close"]) and is_num(prev) and bars[i]["close"] >= prev
    for i, b in enumerate(bars):
        if not is_num(b["close"]):
            continue
        kids.append(h("circle", None, a={"cx": xFor(i), "cy": yFor(b["close"]), "r": 1.5,
                                         "fill": C.forest if up(i) else C.vermillion, "opacity": 0.8}))
    barW = max(1.5, plotW / n * 0.65)
    for i, b in enumerate(bars):
        if not truthy(b["vol"]):
            continue
        x = xFor(i)
        hh = volY + volH - volYFor(b["vol"])
        kids.append(h("rect", None, a={"x": x - barW / 2, "y": volYFor(b["vol"]), "width": barW, "height": hh,
                                       "fill": C.forest if up(i) else C.vermillion, "opacity": 0.45}))
    last = bars[-1]
    x, y = xFor(n - 1), yFor(last["close"])
    kids.append(h("g", None,
                  h("circle", None, a={"cx": x, "cy": y, "r": 5, "fill": C.gold, "stroke": C.bg, "strokeWidth": 1.5}),
                  h("rect", None, a={"x": W - padR + 2, "y": y - 9, "width": 84, "height": 18, "fill": C.gold,
                                     "opacity": 0.95, "rx": 2}),
                  _t(W - padR + 5, y + 4, "NOW " + to_fixed(last["close"], 1) + "K", 10, C.bg, None, 800)))
    kids.append(h("g", None, _t(padL, H - 6, legend, 8.5, C.inkM)))
    if eyebrow is None:
        eyebrow = ("WEEKLY OHLCV + VWAP 6M/12M/24M · " + tk + " · " + js_string(n)
                   + " weeks (FiinTrade ≤08/05 + NgườiQuanSát Mon 11/05 intraday)")
    if readout is None:
        d = js_slice(last["date"], 5).replace("-", "/", 1)
        readout = ["CLOSE " + d + ": ", h("strong", {"color": C.gold}, to_fixed(last["close"], 1) + "K"), " · ",
                   "VWAP6M ", h("strong", {"color": C.forest}, to_fixed(last["vwap6m"], 1) + "K"), " · ",
                   "VWAP12M ", h("strong", {"color": C.ochre}, to_fixed(last["vwap12m"], 1) + "K"), " · ",
                   "VWAP24M ", h("strong", {"color": C.vermillion}, to_fixed(last["vwap24m"], 1) + "K")]
    if label is None:
        label = phase.get("label") if truthy(phase.get("label")) else phase.get("id")
    return frame(eyebrow, label, readout, kids, W, H)


# ── Mode B ──────────────────────────────────────────────────────────────────


def mood_color(m):
    if not truthy(m):
        return C.ink2
    if "distribution" in m or "panic" in m:
        return C.vermillion
    if "absorption" in m or "accumulation" in m:
        return C.forest
    if "markup" in m or "breakout" in m:
        return C.gold
    if "consolidation" in m or "pre-markup" in m:
        return C.ochre
    return C.ink2


def vwap_cls(cls):
    return C.forest if cls == "emerald" else C.vermillion if cls == "rose" else C.gold if cls == "amber-bright" \
        else C.ochre


def curr_px(det, flow):
    """det?.cafefPx/1000 ‖ flow?.px/1000 ‖ det?.currentPrice/1000 ‖ null (SRC 3753)."""
    det, flow = det or {}, flow or {}
    if truthy(det.get("cafefPx")):
        return det["cafefPx"] / 1000
    if truthy(flow.get("px")):
        return flow["px"] / 1000
    if truthy(det.get("currentPrice")):
        return det["currentPrice"] / 1000
    return None


def mode_b(tk, deep, currPx, eyebrow=None, readout_extra=None):
    """Mode B (SRC 3749–3880): dải cụm Toàn Vũ + VWAP ngang + HI/STOP + NOW (currPx K hoặc None)."""
    cl = deep["cluster"]
    clusters = cl["clusters"]
    vwapRows = cl.get("vwap") or []
    phase = deep.get("phase") or {}
    anchor = cl.get("anchor")
    allPx = [c.get("vwapEst") for c in clusters if is_num(c.get("vwapEst"))]
    allPx += [v.get("val") for v in vwapRows if is_num(v.get("val"))]
    allPx += [phase.get("hi"), phase.get("base"), phase.get("stop"), anchor, currPx]
    allPx = [v for v in allPx if is_num(v) and v > 0]
    yMin = max(0, min(allPx) * 0.85)
    yMax = max(allPx) * 1.05
    yRange = yMax - yMin
    W, H, padL, padR, padT, padB = 780, 340, 56, 100, 28, 36
    plotW, plotH = W - padL - padR, H - padT - padB
    yFor = _yfn(yMin, yRange, padT, plotH)
    colW = plotW / len(clusters)
    maxVol = max((c.get("vol") if truthy(c.get("vol")) else 1) for c in clusters)
    kids = []
    for i in range(7):
        v = yMin + (yRange * i / 6)
        y = yFor(v)
        kids.append(h("g", None, _line(padL, y, W - padR, y, C.rule, 0.5, "2 4", 0.4),
                      _t(padL - 6, y + 3, to_fixed(v, 0) + "K", 9, C.inkM, "end")))
    if truthy(anchor):
        kids.append(h("g", None,
                      h("rect", None, a={"x": padL, "y": yFor(anchor * 1.04), "width": plotW,
                                         "height": yFor(anchor * 0.96) - yFor(anchor * 1.04), "fill": C.gold,
                                         "opacity": 0.07}),
                      _line(padL, yFor(anchor), W - padR, yFor(anchor), C.gold, 1, "6 3", 0.6),
                      _t(W - padR + 4, yFor(anchor) + 3, "ANCHOR " + jsv(anchor) + "K", 9, C.gold, None, 700)))
    for i, c in enumerate(clusters):
        if not truthy(c.get("vwapEst")):
            continue
        cx = padL + colW * (i + 0.5)
        barW = max(18, colW * 0.78)
        cy = yFor(c["vwapEst"])
        volRatio = (c.get("vol") if truthy(c.get("vol")) else 0) / maxVol
        bandH = 14 + volRatio * 28
        fill = mood_color(c.get("mood"))
        hot = "★" in (c.get("label") or "")
        kids.append(h("g", None,
                      h("rect", None, a={"x": cx - barW / 2, "y": cy - bandH / 2, "width": barW, "height": bandH,
                                         "fill": fill, "opacity": 0.18 + volRatio * 0.35, "rx": 2}),
                      _line(cx - barW / 2, cy, cx + barW / 2, cy, fill, 2, None, 0.85),
                      _t(cx, cy + bandH / 2 + 14, jsv(c.get("id"), "id" not in c) + (" ★" if hot else ""), 11,
                         C.gold if hot else C.ink2, "middle", 700),
                      _t(cx, cy + bandH / 2 + 25, _strip20(c.get("period")), 8, C.inkM, "middle"),
                      _t(cx, cy - bandH / 2 - 5, "v" + jsv(c.get("vol"), "vol" not in c), 8, C.inkD, "middle")))
    for v in vwapRows:
        if not truthy(v.get("val")):
            continue
        y = yFor(v["val"])
        color = vwap_cls(v.get("cls"))
        per = v.get("period") or ""
        long_ = "24" in per or "TRIGGER" in per
        kids.append(h("g", None,
                      _line(padL, y, W - padR, y, color, 1.3, "8 2" if long_ else "3 3", 0.75),
                      h("rect", None, a={"x": W - padR + 2, "y": y - 7, "width": 84, "height": 14, "fill": color,
                                         "opacity": 0.18, "rx": 2}),
                      _t(W - padR + 5, y + 3, js_slice(per, 0, 8) + " " + jsv(v["val"]) + "K", 8.5, color, None,
                         700)))
    if truthy(phase.get("hi")):
        hi = phase["hi"]
        kids.append(h("g", None, _line(padL, yFor(hi), W - padR, yFor(hi), C.forest, 1.5, "10 4"),
                      _t(padL + 4, yFor(hi) - 4, "HI TARGET " + jsv(hi) + "K", 9, C.forest, None, 700)))
    if truthy(phase.get("stop")):
        st = phase["stop"]
        kids.append(h("g", None, _line(padL, yFor(st), W - padR, yFor(st), C.vermillion, 1.5, "10 4"),
                      _t(padL + 4, yFor(st) + 12, "STOP " + jsv(st) + "K", 9, C.vermillion, None, 700)))
    if truthy(currPx):
        y = yFor(currPx)
        kids.append(h("g", None,
                      _line(padL, y, W - padR, y, C.gold, 2, None, 0.9),
                      h("circle", None, a={"cx": W - padR - 12, "cy": y, "r": 5, "fill": C.gold, "stroke": C.bg,
                                           "strokeWidth": 1.5}),
                      h("rect", None, a={"x": W - padR + 2, "y": y - 9, "width": 84, "height": 18, "fill": C.gold,
                                         "opacity": 0.95, "rx": 2}),
                      _t(W - padR + 5, y + 4, "NOW " + to_fixed(currPx, 1) + "K", 10, C.bg, None, 800)))
    kids.append(h("g", None, _t(padL, H - 6, LEGEND_B, 8.5, C.inkM)))
    if eyebrow is None:
        eyebrow = ("CLUSTER + VWAP MAP · " + tk
                   + " (synthesized from Toàn Vũ hộp + Phú SSI VWAP — không có FiinTrade weekly data)")
    ro = []
    if truthy(currPx):
        ro += ["GIÁ: ", h("strong", {"color": C.gold}, to_fixed(currPx, 1) + "K"), " · "]
    if truthy(phase.get("hi")):
        ro += ["HI ", h("strong", {"color": C.forest}, jsv(phase["hi"]) + "K"), " · "]
    if truthy(phase.get("base")):
        ro += ["BASE ", h("strong", {"color": C.gold}, jsv(phase["base"]) + "K"), " · "]
    if truthy(phase.get("stop")):
        ro += ["STOP ", h("strong", {"color": C.vermillion}, jsv(phase["stop"]) + "K")]
    if readout_extra:
        ro += list(readout_extra)
    label = phase.get("label") if truthy(phase.get("label")) else phase.get("id")
    return frame(eyebrow, label, ro, kids, W, H)


def _strip20(period):
    p = period if truthy(period) else ""
    return p[2:] if p.startswith("20") else p


# ── Mode C + điều phối ──────────────────────────────────────────────────────


def mode_c(tk, text=None):
    return h("div", EMPTY, text if text is not None else "Chart data chưa available cho " + tk)


def chart_mode(weekly_rows, deep):
    if weekly_rows and len(weekly_rows) > 10:
        return "A"
    cl = (deep or {}).get("cluster") or {}
    if cl.get("clusters"):
        return "B"
    return "C"


def canvas_chart(tk, deep, det, flow, weekly_rows):
    """Bản V21 nguyên văn: điều phối A → B → C như JSX."""
    m = chart_mode(weekly_rows, deep)
    if m == "A":
        return mode_a(tk, v21_bars(weekly_rows), (deep or {}).get("phase") or {},
                      ((deep or {}).get("cluster") or {}).get("anchor"))
    if m == "B":
        return mode_b(tk, deep, curr_px(det, flow))
    return mode_c(tk)
