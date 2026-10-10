#!/usr/bin/env python3
"""
chaebol_map_tab_codong_deep — Section "🔬 DEEP-DIVE 10 SUB-TABS — {mã}" của tab CẤU TRÚC CỔ ĐÔNG (codong).

Nguồn thiết kế: chaebol_map_spec/page_p3b_deepdive10.md (§3–§6) + page_p3a_codong_tab.md §S3 (điểm nối).
SRC 3565–3594 (CHAEBOL_DEEP_DATA, WEEKLY_OHLCV, SUB_TABS_CHAEBOL — đọc qua ctx.v21) và 3884–4245 (ChaebolDeepDive10),
wrapper 4344–4351 (CauTrucCoDongTab). Chart SVG ở chaebol_map_tab_codong_deep_chart.py; lớp sống (mode live) ở
chaebol_map_tab_codong_deep_live.py (đối tượng `lv`, None ở mode v21).

API cho agent codong:
    has_deep10(tk, v21=None) -> bool       điều kiện hiện Section (41/48 mã; ẩn VNM SAB VTP VGI GVR BVH BCM)
    build_deep10(ctx, tk) -> node           Section đầy đủ: 11 nút sub + 11 panel bọc if {"codong.sub": id}
Gốc Section mang scope ["codong.sub"] (không khai states — agent codong khai `codong.sub`). Đổi mã giữa hai mã đều
có Deep-dive thì `sub` giữ nguyên (cùng khoá scope vẫn được render); qua mã ẩn → không nút nào mang scope → reset
`phase_info` — đúng hành vi React (ChaebolDeepDive10 không có `key`).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from chaebol_map_dom import C, F_DISPLAY, F_MONO, F_SERIF, h, to_fixed
from chaebol_map_shell import Card, Section, Stat
from chaebol_map_tab_codong_deep_chart import canvas_chart, js_slice, jsv, truthy

SUB_KEY = "codong.sub"
SUB_DEFAULT = "phase_info"
SUB_LINE = ("Phase Infographic · Chart · Phase+Status · Cụm+VWAP · Cổ đông BCTN · Capital IQ · FiinTrade Flow · "
            "Bàn cờ lớn · Key Events · Patterns · Action Plan")
EXC_V21 = ["VCB", "BID", "CTG", "GAS", "BSR", "PLX"]          # CauTrucCoDongTab.jsx@L4346
SUB_TABS_V21 = [("phase_info", "★ 01 Phase Infographic"), ("chart", "02 Chart Infographic"),
                ("phase", "03 Phase + Status"), ("cluster", "04 Cụm + VWAP"), ("shareholder", "05 Cổ đông BCTN"),
                ("capitaliq", "★ 06 Capital IQ"), ("flow", "★ 06b FiinTrade Flow"), ("strategic", "07 Bàn cờ lớn"),
                ("events", "08 Key Events"), ("patterns", "09 Patterns"), ("action", "10 Action Plan")]
PHASE_COLOR = {"amber": C.ochre, "emerald": C.forest, "rose": C.vermillion, "gold": C.gold, "ink2": C.ink2,
               "vermillion": C.vermillion}
P2_NOTE = (' "Sau khi rũ hết lượng kẹp ở đó, vùng lên tiếp không vol. Vùng kẹp = nơi cụm vol vào nhiều mà giá đứng — '
           'phải vượt + KL gấp 1.5x TB mới confirm thoát."')
TV_READING = (" Pattern A (đỉnh): cổ đông ×1.5-2× từ đáy + KL đỉnh dòng tiền. Pattern B (đáy): cổ đông đặc lại + KL "
              "cạn 40-50%. Pattern D (đảo chuyển): cổ đông KHÔNG tăng tương ứng KL bùng = đổi chủ thể nội bộ.")
SIG_TEXT = {"BULL": " — Smart money accumulating, retail capitulate. Pattern B đáy.",
            "BEAR": " — Smart money distributing, retail catch knife. Pattern A đỉnh.",
            "MIX": " — 4 kênh không đồng pha. Phase Markup/Markdown/Transition."}

# Style lặp (chép đúng thứ tự khoá JSX)
GOLD_BOX = {"padding": "10px 14px", "background": C.gold + "10", "border": "1px solid " + C.gold + "30",
            "borderRadius": 3, "fontSize": 11.5, "color": C.ink, "lineHeight": 1.7}
EMPTY_P = {"margin": 0, "fontSize": 11.5, "color": C.inkD, "fontStyle": "italic"}
GRID4 = {"display": "grid", "gridTemplateColumns": "repeat(4,1fr)", "gap": 12, "marginBottom": 14}
TR_ROW = {"borderBottom": "1px solid " + C.rule + "80"}
TR_HEAD = {"borderBottom": "1px solid " + C.rule}


def _v21_default():
    base = os.environ.get("CHB_SYSTEM_DIR")
    root = Path(base).expanduser() if base else Path.home() / "SECOND BRAIN-OBSIDIAN" / "_System"
    p = root / "fincept_bridge" / "data" / "chaebol_map" / "v21_const.json"
    key = (str(p), p.stat().st_mtime if p.is_file() else None)
    if _V21_CACHE.get("key") != key:
        try:
            with open(p, "r", encoding="utf-8") as f:
                _V21_CACHE["v"] = json.load(f)
        except (OSError, ValueError):
            _V21_CACHE["v"] = {}
        _V21_CACHE["key"] = key
    return _V21_CACHE["v"]


_V21_CACHE = {}


def _v21_of(src):
    """ctx | dict v21_const | None → dict v21_const."""
    if src is None:
        return _v21_default()
    if isinstance(src, dict):
        return src
    v = getattr(src, "v21", None)
    return v if isinstance(v, dict) and v else _v21_default()


def has_deep10(tk, v21=None):
    """POLICY_MAP[tk] && (basket ∈ {NQ68, DISTRESS} || tk ∈ ['VCB','BID','CTG','GAS','BSR','PLX']) (SRC 4345)."""
    v = _v21_of(v21)
    pm = (v.get("POLICY_MAP") or {}).get(tk)
    exc = v.get("CauTrucCoDongTab.jsx@L4346") or EXC_V21
    return bool(pm) and (pm.get("basket") in ("NQ68", "DISTRESS") or tk in exc)


def sub_tabs(v21=None):
    """[(id, label)] từ SUB_TABS_CHAEBOL (dự phòng bản chép SRC 3572–3584)."""
    raw = _v21_of(v21).get("SUB_TABS_CHAEBOL")
    try:
        out = [(str(t["id"]), str(t["label"])) for t in raw]
        return out if len(out) == 11 else list(SUB_TABS_V21)
    except (TypeError, KeyError):
        return list(SUB_TABS_V21)


def sub_options(v21=None):
    return [i for i, _ in sub_tabs(v21)]


class _T:
    """Dữ liệu V21 của một mã (SRC 3885–3896): det, holders, filings, flow, cons, deep, phaseColor."""

    def __init__(self, v21, tk):
        g = lambda name: (v21.get(name) or {}).get(tk)  # noqa: E731
        self.tk = tk
        self.det = g("TICKER_DETAIL")
        self.holders = g("HOLDERS_CIQ") or []
        self.filings = g("REPORTS_INDEX") or []
        self.flow = g("FLOW")
        self.cons = g("SIMPLIZE_CONSENSUS")
        self.deep = g("CHAEBOL_DEEP_DATA")
        self.weekly = g("WEEKLY_OHLCV")
        self.phase = (self.deep or {}).get("phase")
        pc = (self.phase or {}).get("color")
        cmap = v21.get("ChaebolDeepDive10.phaseColorMap") or PHASE_COLOR
        self.phaseColor = (cmap.get(pc) or C.gold) if truthy(pc) else C.gold


def _sub_bar(subs):
    base = {"background": "transparent", "color": C.inkD, "border": "1px solid " + C.rule, "padding": "5px 10px",
            "borderRadius": 2, "cursor": "pointer", "fontFamily": F_MONO, "fontSize": 9.5, "fontWeight": 500,
            "letterSpacing": ".08em"}
    act = {"background": C.gold, "color": C.bg, "border": "1px solid " + C.gold, "fontWeight": 700}
    btns = [h("button", base, label, on={"set": {SUB_KEY: sid}}, var=[{"if": {SUB_KEY: sid}, "s": act}],
              key="deep10_sub_" + sid) for sid, label in subs]
    return h("div", {"display": "flex", "gap": 4, "flexWrap": "wrap", "marginBottom": 16, "padding": "8px 10px",
                     "background": C.parch, "borderRadius": 3, "borderBottom": "1px solid " + C.gold + "40"}, *btns)


def _panel(sid, title, *children, accent=None, sub=None):
    return Section(title, *children, accent=accent, sub=sub, if_={SUB_KEY: sid}, key="deep10_" + sid)


def _strong(color, text):
    return h("strong", {"color": color}, text)


# ── 01 Phase Infographic (SRC 3914–3936) ────────────────────────────────────


def p01(T, lv):
    ph = T.phase
    if not truthy(ph):
        return lv.empty_panel("phase_info", "★ 01 Phase Infographic — " + T.tk) if lv else None
    pc = T.phaseColor
    sizing = ph.get("sizing")
    size0 = str(sizing).split(" ")[0] if sizing is not None else None
    stats = [Stat("HI TARGET", lv.level("hi", ph) if lv else jsv(ph.get("hi"), "hi" not in ph) + "K",
                  sub=lv.level_sub("hi", ph, "upside") if lv else "upside", color=C.forest),
             Stat("BASE", lv.level("base", ph) if lv else jsv(ph.get("base"), "base" not in ph) + "K",
                  sub=lv.level_sub("base", ph, "entry zone") if lv else "entry zone", color=C.gold),
             Stat("STOP", lv.level("stop", ph) if lv else jsv(ph.get("stop"), "stop" not in ph) + "K",
                  sub=lv.level_sub("stop", ph, "exit downside") if lv else "exit downside", color=C.vermillion),
             Stat("SIZING", [size0, lv.v21()] if lv else size0, sub=sizing, color=C.ink2)]
    body = [
        h("div", {"display": "grid", "gridTemplateColumns": "auto 1fr", "gap": 14, "alignItems": "center",
                  "marginBottom": 14},
          h("div", {"padding": "14px 22px", "background": pc + "25", "border": "3px solid " + pc, "borderRadius": 4,
                    "textAlign": "center"},
            h("div", {"fontSize": 9, "letterSpacing": ".3em", "color": C.inkM, "fontFamily": F_MONO,
                      "marginBottom": 4}, "PHASE"),
            h("div", {"fontSize": 16, "fontWeight": 800, "color": pc, "fontFamily": F_MONO}, ph.get("id"))),
          h("div", None,
            h("h3", {"margin": 0, "fontSize": 18, "fontFamily": F_DISPLAY, "color": pc, "fontStyle": "italic",
                     "fontWeight": 700}, ph.get("label"), lv.v21() if lv else None),
            h("p", {"margin": "6px 0 0", "fontSize": 12, "color": C.inkD, "fontFamily": F_MONO,
                    "letterSpacing": ".06em"}, "STANCE: ", ph.get("stance"), lv.v21() if lv else None))),
        h("div", GRID4, *stats),
        h("p", {"margin": 0, "fontSize": 11.5, "color": C.inkD, "lineHeight": 1.85, "fontFamily": F_SERIF},
          ph.get("note"), lv.legal_mark(ph.get("note")) if lv else None, lv.v21() if lv else None),
    ]
    if lv:
        body += [lv.level_eval(ph), lv.updates("phase_info")]
    return _panel("phase_info", "★ 01 Phase Infographic — " + T.tk, Card(*body), accent=pc)


# ── 02 Chart Infographic (SRC 3939–3950) ────────────────────────────────────


def p02(T, lv):
    verdict = ((T.deep or {}).get("cluster") or {}).get("verdict")
    chart = lv.chart(T) if lv else None
    if chart is None:
        chart = canvas_chart(T.tk, T.deep, T.det, T.flow, T.weekly)
        if lv:                                   # live nhưng không có chuỗi tuần vc_lk → bản lưu V21 có dấu
            chart = [lv.v21_caption_can("Chart bản lưu V21·12/05 (FiinTrade/Toàn Vũ, cơ sở giá 08/05)",
                                        "chưa có chuỗi tuần vc_lk"), chart]
    p = h("p", {"margin": "14px 0 0", "fontSize": 11, "color": C.inkD, "fontStyle": "italic", "lineHeight": 1.7},
          _strong(C.gold, "★ Nguyên tắc Phú SSI:"), P2_NOTE,
          [h("br"), h("br"), _strong(C.gold, "Reading hiện tại:"), " ", verdict, lv.v21() if lv else None]
          if truthy(verdict) else None,
          lv.vwap_label_line() if lv else None)
    return _panel("chart", "📈 02 Chart Infographic — Cluster + VWAP overlay", Card(chart, p), accent=C.gold,
                  sub="Phú SSI VWAP cụm methodology · cluster history bars + VWAP 6M/12M/24M + phase HI/BASE/STOP")


# ── 03 Phase + Status (SRC 3953–3979) ───────────────────────────────────────


def p03(T, lv):
    det, flow, deep, pc = T.det or {}, T.flow or {}, T.deep or {}, T.phaseColor
    ph = deep.get("phase") or {}
    if lv:
        px_val, px_sub = lv.price_stat()
        perf_val, perf_sub, perf_col = lv.perf60_stat()
        sig_val, sig_sub = lv.sig_stat(flow)
    else:
        if truthy(det.get("cafefPx")):
            px_val = to_fixed(det["cafefPx"] / 1000, 1) + "K"
        elif truthy(flow.get("px")):
            px_val = to_fixed(flow["px"] / 1000, 1) + "K"
        else:
            px_val = "N/A"
        px_sub = "04-08/05" if truthy(det.get("cafefPx")) else (flow.get("date") if truthy(flow.get("date")) else "")
        p60 = flow.get("perf60")
        perf_val = (("+" if p60 > 0 else "") + to_fixed(p60, 1) + "%") if truthy(p60) else "N/A"
        perf_sub = "vs 60d ago"
        perf_col = C.forest if (p60 if truthy(p60) else 0) > 0 else C.vermillion
        sig_val = flow.get("sig") if truthy(flow.get("sig")) else "N/A"
        sig_sub = flow.get("date") if truthy(flow.get("date")) else ""
    sig = flow.get("sig")
    ph_id = ph.get("id") if truthy(ph.get("id")) else "N/A"
    stance = ph.get("stance")
    st18 = js_slice(stance, 0, 18) if truthy(stance) else ""
    stats = [Stat("GIÁ HIỆN TẠI", px_val, sub=px_sub, color=C.ink2),
             Stat("PHASE", [ph_id, lv.v21() if lv and ph_id != "N/A" else None], sub=st18 or None, color=pc),
             Stat("60D PERF", perf_val, sub=perf_sub, color=perf_col),
             Stat("FLOW SIG", sig_val, sub=sig_sub or None,
                  color=C.forest if sig == "BULL" else C.vermillion if sig == "BEAR" else C.ochre)]
    q4 = deep.get("q4Flow")
    body = [h("div", GRID4, *stats)]
    if truthy((q4 or {}).get("narrative")):
        body.append(h("div", {"padding": "10px 14px", "background": pc + "15", "border": "1px solid " + pc + "40",
                              "borderRadius": 3, "fontSize": 11.5, "color": C.ink, "lineHeight": 1.7,
                              "marginBottom": 10},
                      _strong(pc, "★ Q4/Q1 FLOW NARRATIVE:"), " ", q4["narrative"], lv.v21() if lv else None))
    if truthy((q4 or {}).get("verdict")):
        body.append(h("div", GOLD_BOX, _strong(C.gold, "★ VERDICT:"), " ", q4["verdict"], lv.v21() if lv else None))
    if truthy(det.get("flowReading")) and not truthy(q4):
        body.append(h("div", GOLD_BOX, _strong(C.gold, "★ FLOW READING (V21):"), " ", det["flowReading"],
                      lv.v21() if lv else None))
    if lv:
        body.append(lv.updates("phase"))
    return _panel("phase", "⚡ 03 Phase + Status — " + T.tk, Card(*body), accent=pc)


# ── 04 Cụm + VWAP (SRC 3982–4038) ───────────────────────────────────────────


def _lbl(text, extra=None):
    st = {"fontSize": 9, "letterSpacing": ".2em", "color": C.gold, "fontFamily": F_MONO, "marginBottom": 10,
          "fontWeight": 700}
    if extra:
        st.update(extra)
    return h("div", st, *text) if isinstance(text, list) else h("div", st, text)


def _vwap_cc(cls):
    return C.forest if cls == "emerald" else C.vermillion if cls == "rose" else C.gold if cls == "amber-bright" \
        else C.ochre


def p04(T, lv):
    cl = (T.deep or {}).get("cluster")
    if not truthy(cl):
        return lv.empty_panel("cluster", "🎯 04 Cụm + VWAP — Phú SSI methodology") if lv else None
    rows = []
    for v in cl.get("vwap") or []:
        cc = _vwap_cc(v.get("cls"))
        rows.append(h("tr", TR_ROW,
                      h("td", {"padding": "8px", "color": C.ink}, v.get("period")),
                      h("td", {"padding": "8px", "textAlign": "right", "color": cc, "fontWeight": 700}, v.get("val")),
                      h("td", {"padding": "8px", "color": C.inkD, "fontSize": 10.5}, v.get("status")),
                      h("td", {"padding": "8px"}, h("span", {"padding": "2px 7px", "background": cc + "20", "color": cc,
                                                             "fontSize": 9, "fontWeight": 700, "borderRadius": 2},
                                                    v.get("label")))))
    tA = h("table", {"width": "100%", "borderCollapse": "collapse", "fontFamily": F_MONO, "fontSize": 11,
                     "marginBottom": 14},
           h("thead", None, h("tr", TR_HEAD,
                              h("th", {"padding": "6px 8px", "textAlign": "left", "color": C.inkD, "fontSize": 9},
                                "PERIOD"),
                              h("th", {"padding": "6px 8px", "textAlign": "right", "color": C.inkD, "fontSize": 9},
                                "VAL (K)"),
                              h("th", {"padding": "6px 8px", "textAlign": "left", "color": C.inkD, "fontSize": 9},
                                "STATUS"),
                              h("th", {"padding": "6px 8px", "textAlign": "left", "color": C.inkD, "fontSize": 9},
                                "LABEL"))),
           h("tbody", None, *rows))
    th6 = lambda t, al: h("th", {"padding": "6px", "textAlign": al, "color": C.inkD, "fontSize": 9}, t)  # noqa: E731
    rowsB = []
    for c in cl.get("clusters") or []:
        star = "★" in (c.get("label") or "")
        rowsB.append(h("tr", {"borderBottom": "1px solid " + C.rule + "80",
                              "background": C.gold + "15" if star else "transparent"},
                       h("td", {"padding": "7px", "color": C.gold, "fontWeight": 700}, c.get("id")),
                       h("td", {"padding": "7px", "color": C.ink}, c.get("period")),
                       h("td", {"padding": "7px", "textAlign": "right", "color": C.inkD}, c.get("bars")),
                       h("td", {"padding": "7px", "textAlign": "right", "color": C.ink2, "fontWeight": 600}, c.get("vol")),
                       h("td", {"padding": "7px", "textAlign": "right", "color": C.gold, "fontWeight": 700},
                         c.get("vwapEst")),
                       h("td", {"padding": "7px", "color": C.ink, "fontSize": 10}, c.get("label")),
                       h("td", {"padding": "7px", "color": C.inkD, "fontStyle": "italic", "fontSize": 10}, c.get("mood"))))
    tB = h("table", {"width": "100%", "borderCollapse": "collapse", "fontFamily": F_MONO, "fontSize": 10.5},
           h("thead", None, h("tr", TR_HEAD, th6("ID", "left"), th6("PERIOD", "left"), th6("BARS", "right"),
                              th6("VOL", "right"), th6("VWAP", "right"), th6("LABEL", "left"), th6("MOOD", "left"))),
           h("tbody", None, *rowsB))
    lblA = ["VWAP CỤM (6M / 12M / 24M)", lv.v21() if lv else None, lv.basis_note() if lv else None]
    body = [lv.vwap_live_table() if lv else None, _lbl(lblA), tA,
            _lbl(["CỤM KHỐI LƯỢNG (Toàn Vũ)", lv.v21() if lv else None], {"marginTop": 18}), tB,
            h("div", {"marginTop": 12, **GOLD_BOX}, _strong(C.gold, "★ VERDICT:"), " ", cl.get("verdict"),
              lv.v21() if lv else None)]
    if lv:
        body.append(lv.updates("cluster"))
    return _panel("cluster", "🎯 04 Cụm + VWAP — Phú SSI methodology", Card(*body), accent=C.gold)


# ── 05 Cổ đông BCTN (SRC 4041–4075) ─────────────────────────────────────────


def _mood_color(m):
    m = m if isinstance(m, str) else None
    if m and ("rising-strong" in m or "falling-strong" in m):
        return C.vermillion
    if m and "rising" in m:
        return C.ochre
    if m and "falling" in m:
        return C.forest
    return C.gold if m == "tbd" else C.inkD


def p05(T, lv):
    evo = (T.deep or {}).get("shareholderEvolution")
    thS = lambda t, al: h("th", {"padding": "8px 10px", "textAlign": al, "color": C.inkD, "fontSize": 9,  # noqa: E731
                                 "letterSpacing": ".18em", "fontFamily": F_MONO}, t)
    if truthy(evo):
        rows = []
        for e in evo:
            mc = _mood_color(e.get("mood"))
            rows.append(h("tr", TR_ROW,
                          h("td", {"padding": "10px", "color": C.ink, "fontWeight": 600}, e.get("period")),
                          h("td", {"padding": "10px", "textAlign": "right", "color": C.gold, "fontWeight": 700,
                                   "fontFamily": F_MONO}, e.get("count")),
                          h("td", {"padding": "10px", "color": C.inkD, "fontSize": 11}, e.get("note")),
                          h("td", {"padding": "10px"}, h("span", {"padding": "2px 7px", "background": mc + "20",
                                                                  "color": mc, "fontSize": 9, "fontWeight": 700,
                                                                  "fontFamily": F_MONO}, e.get("mood")))))
        first = Card(lv.v21_caption("Bản lưu V21·12/05 — số cổ đông không nêu nguồn (UNVERIFIED)") if lv else None,
                     h("table", {"width": "100%", "borderCollapse": "collapse", "fontFamily": F_SERIF,
                                 "fontSize": 11.5},
                       h("thead", None, h("tr", TR_HEAD, thS("PERIOD", "left"), thS("COUNT", "right"),
                                          thS("NOTE", "left"), thS("MOOD", "left"))),
                       h("tbody", None, *rows)))
    else:
        first = Card(h("p", EMPTY_P, "Chưa có shareholder evolution detailed cho ", T.tk,
                       ". Tham chiếu BCTN từng năm tại simplize.vn/co-phieu/", T.tk, "/bao-cao."))
    note = h("div", {"marginTop": 12, "padding": "10px 14px", "background": C.parch, "border": "1px solid " + C.rule,
                     "borderRadius": 3, "fontSize": 10.5, "color": C.inkD, "lineHeight": 1.7},
             _strong(C.gold, "★ Reading per Toàn Vũ:"), TV_READING)
    kids = [lv.codong_table() if lv else None, first, note, lv.updates("shareholder") if lv else None]
    return _panel("shareholder", "👥 05 Cổ đông BCTN — Pillar I điểm đảo chiều cổ đông", *kids, accent=C.gold,
                  sub="Toàn Vũ — datapoint then chốt VN-specific. Δ cổ đông giữa các kỳ BCTN = chữ ký đổi chủ thể.")


# ── 06 Capital IQ (SRC 4078–4103) ───────────────────────────────────────────


def _shares_txt(hd):
    s = hd.get("shares")
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        return to_fixed(s / 1e6, 2) + "M"
    if truthy(hd.get("shares_M")):
        return to_fixed(hd["shares_M"], 2) + "M"
    return s if truthy(s) else "—"


def holders_table(rows, name_cell=None, mark=None):
    thH = lambda t, al: h("th", {"padding": "8px 10px", "textAlign": al, "color": C.inkD, "fontSize": 9,  # noqa: E731
                                 "letterSpacing": ".18em"}, t)
    trs = []
    for hd in rows:
        pct = hd.get("pct")
        trs.append(h("tr", {"borderBottom": "1px solid " + C.rule + "80",
                            "background": C.vermillion + "10" if hd.get("tag") == "eliminated" else "transparent"},
                     h("td", {"padding": "9px 10px", "color": C.ink, "fontFamily": F_SERIF, "fontSize": 11},
                       hd.get("name"), mark(str(hd.get("name") or "") + " " + str(hd.get("type") or "")) if mark else None),
                     h("td", {"padding": "9px 10px", "textAlign": "right", "color": C.gold, "fontWeight": 700},
                       _shares_txt(hd)),
                     h("td", {"padding": "9px 10px", "textAlign": "right", "color": C.ink2},
                       to_fixed(pct, 2) + "%" if truthy(pct) else "—"),
                     h("td", {"padding": "9px 10px", "color": C.inkD, "fontSize": 10, "fontStyle": "italic"},
                       hd.get("type"))))
    return h("table", {"width": "100%", "borderCollapse": "collapse", "fontFamily": F_MONO, "fontSize": 10.5},
             h("thead", None, h("tr", TR_HEAD, thH("HOLDER", "left"), thH("SHARES", "right"), thH("PCT", "right"),
                                thH("TYPE", "left"))),
             h("tbody", None, *trs))


def p06(T, lv):
    dh = (T.deep or {}).get("holders")
    has = (truthy(dh) and len(dh) > 0) or len(T.holders) > 0
    if has:
        rows = dh if truthy(dh) else T.holders
        v21card = Card(lv.v21_caption("Bản lưu V21·12/05 — Capital IQ Q4/25 lấy trên máy cũ, không làm mới")
                       if lv else None, holders_table(rows, mark=lv.legal_mark if lv else None))
    else:
        v21card = Card(h("p", EMPTY_P, "Holders data chưa available."))
    kids = [lv.holders_live() if lv else None, v21card, lv.updates("capitaliq") if lv else None]
    return _panel("capitaliq", "★ 06 Capital IQ — Top Holders + Δ", *kids, accent=C.forest)


# ── 06b FiinTrade Flow (SRC 4106–4124) ──────────────────────────────────────


def p06b(T, lv):
    flow = T.flow
    if not truthy(flow):
        return lv.flow_only_live() if lv else None
    stats = []
    for label, k in (("CÁ NHÂN", "ca60"), ("TỔ CHỨC", "to60"), ("TỰ DOANH", "td60"), ("NƯỚC NGOÀI", "nn60")):
        x = flow.get(k) if truthy(flow.get(k)) else 0
        stats.append(Stat(label, to_fixed(x, 1) + "M",
                          sub="60d net" if not lv else ["60d net · ≤", lv.dmy(flow.get("date"))],
                          color=C.forest if x > 0 else C.vermillion))
    sig = flow.get("sig")
    col = C.forest if sig == "BULL" else C.vermillion if sig == "BEAR" else C.ochre
    box = h("div", {"padding": "10px 14px", "background": col + "15", "border": "2px solid " + col, "borderRadius": 3,
                    "fontSize": 11.5, "color": C.ink, "lineHeight": 1.7},
            h("strong", None, "SIGNAL: ", sig), SIG_TEXT.get(sig) if isinstance(sig, str) else None,
            lv.v21() if lv else None)
    body = [lv.v21_caption("FiinTrade ≤08/05 — đóng băng, không thay ngược (V21·12/05, UNVERIFIED)") if lv else None,
            h("div", GRID4, *stats), box]
    if lv:
        body += lv.flow_live_rows()
    return _panel("flow", "★ 06b FiinTrade Pillar IV — 4-channel Flow 60d", Card(*body), accent=C.forest,
                  sub=lv.flow_sub() if lv else "Cutover ≤08/05 FiinTrade verified · ≥09/05 NgườiQuanSát forward")


# ── 07 Bàn cờ lớn (SRC 4127–4145) ───────────────────────────────────────────


def p07(T, lv):
    st = (T.deep or {}).get("strategic")
    if truthy(st):
        pillars = []
        for p in st.get("pillars") or []:
            tag = p.get("tag") or ""
            stop, warn = "⛔" in tag, "⚠" in tag
            pillars.append(h("div", {"padding": "10px 12px",
                                     "background": C.vermillion + "15" if stop or warn else C.parch,
                                     "border": "1px solid " + (C.vermillion if stop else C.rule), "borderRadius": 3},
                             h("div", {"fontSize": 8.5, "letterSpacing": ".25em",
                                       "color": C.vermillion if stop else C.gold, "fontFamily": F_MONO,
                                       "fontWeight": 700, "marginBottom": 4}, p.get("tag")),
                             h("div", {"fontSize": 12, "fontWeight": 700, "color": C.ink, "marginBottom": 4}, p.get("h")),
                             h("div", {"fontSize": 10.5, "color": C.inkD, "lineHeight": 1.65}, p.get("d"))))
        card = Card(h("h3", {"margin": "0 0 10px", "fontSize": 16, "fontFamily": F_DISPLAY, "color": C.gold,
                             "fontStyle": "italic"}, st.get("title"), lv.v21() if lv else None),
                    h("p", {"margin": "0 0 16px", "fontSize": 11.5, "color": C.ink, "lineHeight": 1.85,
                            "fontFamily": F_SERIF}, st.get("thesis"), lv.v21() if lv else None),
                    h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 10}, *pillars),
                    lv.legal_caveat() if lv else None)
    else:
        card = Card(h("p", EMPTY_P, "Chưa có strategic deep-dive cho ", T.tk, "."))
    return _panel("strategic", "🏛 07 Bàn cờ lớn — Pillar III ý đồ chủ thể", card,
                  lv.updates("strategic") if lv else None, accent=C.gold)


# ── 08 Key Events (SRC 4148–4177) ───────────────────────────────────────────


def _sev_color(sev):
    return C.vermillion if sev == "rose" else C.forest if sev == "emerald" else C.ochre if sev == "amber" else C.ink2


def event_row(r, extra_cat=None, extra_t=None, extra_d=None):
    sc = _sev_color(r.get("sev"))
    return h("tr", TR_ROW,
             h("td", {"padding": "9px", "color": C.inkD}, r.get("date")),
             h("td", {"padding": "9px"}, h("span", {"padding": "2px 7px", "background": sc + "20", "color": sc,
                                                    "fontSize": 9, "fontWeight": 700}, r.get("cat")), extra_cat),
             h("td", {"padding": "9px"},
               h("div", {"color": C.ink, "fontFamily": F_SERIF, "fontSize": 11.5, "fontWeight": 600}, r.get("t"),
                 extra_t),
               h("div", {"color": C.inkD, "fontSize": 10.5, "marginTop": 3, "lineHeight": 1.6}, r.get("d"), extra_d)
               if truthy(r.get("d")) or extra_d else None))


def events_table(rows_nodes):
    thE = lambda t, w=None: h("th", {"padding": "8px 10px", "textAlign": "left", "color": C.inkD,  # noqa: E731
                                     "fontSize": 9, "letterSpacing": ".18em", "width": w}, t)
    return h("table", {"width": "100%", "borderCollapse": "collapse", "fontFamily": F_MONO, "fontSize": 10.5},
             h("thead", None, h("tr", TR_HEAD, thE("NGÀY", "12%"), thE("LOẠI", "13%"), thE("SỰ KIỆN"))),
             h("tbody", None, *rows_nodes))


def p08(T, lv):
    deep = T.deep or {}
    ev = deep.get("events")
    if not truthy(ev):
        ev = [{"date": f.get("d"), "cat": f.get("cat"), "sev": "rose" if f.get("cat") == "INSIDER" else "cyan",
               "t": f.get("t"), "d": ""} for f in T.filings]
    new_rows = lv.events_new_rows() if lv else []
    old_rows = lv.events_old_rows() if lv else []            # dữ kiện ↻ trước 09/05: sau bản lưu V21
    if len(ev) > 0 or new_rows or old_rows:
        rows = list(new_rows)
        for i, r in enumerate(ev):
            rows.append(lv.event_v21_row(i, r) if lv else event_row(r))
        rows += old_rows
        inner = events_table(rows)
    else:
        inner = h("p", EMPTY_P, "Chưa có events.")
    return _panel("events", "📋 08 Key Events Timeline — " + T.tk, Card(lv.events_caption() if lv else None, inner),
                  accent=C.gold)


# ── 09 Patterns (SRC 4180–4206) ─────────────────────────────────────────────


def _pat_color(cls):
    return C.forest if cls == "emerald" else C.vermillion if cls == "rose" else C.ochre if cls == "amber" else C.inkD


def p09(T, lv):
    pats = (T.deep or {}).get("patterns")
    thP = lambda t, w=None: h("th", {"padding": "8px", "textAlign": "left", "color": C.inkD, "fontSize": 9,  # noqa: E731
                                     "fontFamily": F_MONO, "width": w}, t)
    if truthy(pats):
        rows = []
        for p in pats:
            cc = _pat_color(p.get("cls"))
            rows.append(h("tr", TR_ROW,
                          h("td", {"padding": "10px", "color": C.ink, "fontWeight": 600, "fontSize": 11.5}, p.get("i")),
                          h("td", {"padding": "10px"}, h("span", {"padding": "3px 8px", "background": cc + "20",
                                                                  "color": cc, "fontSize": 9.5, "fontWeight": 700,
                                                                  "fontFamily": F_MONO, "borderRadius": 2}, p.get("s"))),
                          h("td", {"padding": "10px", "color": C.inkD, "lineHeight": 1.6, "fontSize": 11}, p.get("n"))))
        card = Card(lv.v21_caption("Bản lưu V21·12/05 — checklist 8 pattern, không chấm lại (CỔNG v1.7 DỪNG)")
                    if lv else None,
                    h("table", {"width": "100%", "borderCollapse": "collapse", "fontFamily": F_SERIF, "fontSize": 11.5},
                      h("thead", None, h("tr", TR_HEAD, thP("PATTERN", "40%"), thP("STATUS", "15%"), thP("NOTE"))),
                      h("tbody", None, *rows)))
    else:
        card = Card(h("p", EMPTY_P, "Patterns checklist chưa available cho ", T.tk, "."))
    return _panel("patterns", "🔍 09 Patterns Checklist — Toàn Vũ 8-pattern", lv.patterns_live() if lv else None,
                  card, lv.updates("patterns") if lv else None, accent=C.gold)


# ── 10 Action Plan (SRC 4209–4242) ──────────────────────────────────────────


def p10(T, lv):
    act = (T.deep or {}).get("action")
    if truthy(act):
        lab = lambda t, col: h("div", {"fontSize": 9, "letterSpacing": ".2em", "color": col,  # noqa: E731
                                       "fontFamily": F_MONO, "marginBottom": 8, "fontWeight": 700}, t,
                               lv.v21() if lv else None)
        ul = lambda items: h("ul", {"margin": 0, "paddingLeft": 18, "fontSize": 11, "lineHeight": 1.85,  # noqa: E731
                                    "color": C.inkD}, *[h("li", None, x) for x in items])
        risks = []
        for r in act.get("risks") or []:
            w = r.get("w") or ""
            stop = "⛔" in w
            risks.append(h("div", {"padding": "8px 12px", "background": C.vermillion + "15" if stop else C.parch,
                                   "border": "1px solid " + (C.vermillion if stop else C.rule), "borderRadius": 3,
                                   "marginBottom": 6},
                           h("div", {"fontSize": 9, "letterSpacing": ".2em", "color": C.vermillion if stop else C.gold,
                                     "fontFamily": F_MONO, "fontWeight": 700}, r.get("w"), ": ", r.get("t"),
                             lv.legal_mark(str(r.get("t") or "") + " " + str(r.get("d") or "")) if lv else None),
                           h("div", {"fontSize": 11, "color": C.inkD, "lineHeight": 1.65, "marginTop": 4}, r.get("d"))))
        cons = T.cons or {}
        cons_box = None
        if lv:
            cons_box = lv.consensus_box(cons)
        elif truthy(cons.get("avgTp")):
            cons_box = h("div", {"marginTop": 10, "padding": "10px 14px", "background": C.gold + "10",
                                 "border": "1px solid " + C.gold + "30", "borderRadius": 3, "fontSize": 11,
                                 "color": C.inkD, "lineHeight": 1.7},
                         _strong(C.gold, "★ Sell-side consensus:"), " ", jsv(cons.get("mua"), "mua" not in cons),
                         " MUA / ", jsv(cons.get("ban"), "ban" not in cons), " BÁN / avg TP ",
                         h("strong", None, to_fixed(cons["avgTp"] / 1000, 1) + "K VND"), ".")
        elif "avgTp" in cons and cons["avgTp"] == 0:
            cons_box = "0"                       # {0 && …} của JSX in chữ "0"
        card = Card(lv.action_banner() if lv else None,
                    h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 14, "marginBottom": 14},
                      h("div", None, lab("★ BUY TRIGGERS", C.forest), ul(act.get("buy") or [])),
                      h("div", None, lab("⚠ SELL TRIGGERS", C.vermillion), ul(act.get("sell") or []))),
                    lab("★ RISKS", C.gold), *risks, cons_box)
    else:
        card = Card(lv.action_banner() if lv else None,
                    h("p", EMPTY_P, "Action plan chưa available cho ", T.tk, "."))
    return _panel("action", "🎯 10 Action Plan — Buy/Sell/Risks", card, lv.updates("action") if lv else None,
                  accent=C.gold)


PANELS = (p01, p02, p03, p04, p05, p06, p06b, p07, p08, p09, p10)


def build_deep10(ctx, tk):
    """Section "🔬 DEEP-DIVE 10 SUB-TABS — {tk}" (SRC 4344–4351 + ChaebolDeepDive10). Gọi khi has_deep10(tk)."""
    v21 = _v21_of(ctx)
    T = _T(v21, tk)
    lv = None
    if getattr(ctx, "live", False):
        from chaebol_map_tab_codong_deep_live import DeepLive   # nhập trễ: mode v21 không đụng lớp sống
        lv = DeepLive(ctx, tk, T)
    panels = [fn(T, lv) for fn in PANELS]
    body = h("div", None, lv.legal_banner() if lv else None, _sub_bar(sub_tabs(v21)), *[p for p in panels if p])
    return Section("🔬 DEEP-DIVE 10 SUB-TABS — " + tk + " (equivalent v22 MSN tab structure)", body,
                   lv.header_note() if lv else None, accent=C.gold, sub=SUB_LINE, scope=[SUB_KEY],
                   key="deep10_" + tk)
