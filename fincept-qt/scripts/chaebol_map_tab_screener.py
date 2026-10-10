#!/usr/bin/env python3
"""
chaebol_map_tab_screener — tab 07 · VN30 SCREENER của module chaebol_map (clone ScreenerTab + FilterGroup,
SRC 6176–6449; dữ liệu VN30_LIST 381–427 + FLOW 86–137). Hợp đồng: chaebol_map_spec/DESIGN.md; đặc tả nội dung:
chaebol_map_spec/page_p5_groups_screener.md §7; API: api_python.md, api_data.md.

State (DESIGN §4): scr.sort (mặc định 'perf' — không khớp cột nào → giữ thứ tự VN30_LIST, như trang), scr.dir,
scr.phase (8), scr.sig (4), scr.chaebol (4).
- Lọc hàng: `if` theo 3 khoá lọc; sắp: `sort` trên tbody + `sk` mỗi hàng (comparator dòng 6209–6221).
- Nền sọc chẵn/lẻ phụ thuộc VỊ TRÍ sau lọc + sắp → Python tính trước cho mọi (sort, dir, lọc) và phát `var`.
- 7 thẻ tổng hợp: `count` trên `grp` gắn sẵn ở hàng / ô SIG / pill PHASE (đếm sau lọc, đúng `summary`).
- 2 thẻ Top Picks: tính trên hàng đã lọc → biến thể theo khoá ghép "scr.phase|scr.sig|scr.chaebol"
  (thêm scr.sort|scr.dir nếu thứ tự phụ thuộc cột sắp — chỉ khi có giá trị bằng nhau).

Mode live: + số sống vc_lk (giá thô, Δ60D giá điều chỉnh quyền, NN khớp+TT, TD khớp — 60 phiên), CÁ NHÂN/TỔ CHỨC
và SIG 4 kênh = [CẦN DATA]; PHASE, SIG V21, NHẬN ĐỊNH, Top Picks = bản lưu V21·12/05 (không chấm lại vì CỔNG DỪNG);
bộ lọc chạy trên nhãn V21; thêm thành viên VN30 hiện hành còn thiếu (vnstore.ma.nhom); nhãn chaebol đã bị dữ kiện
bác thì viết lại theo dossier (cap_nhat_<ngày>.screener.json, khoá tickers.<MÃ>.screener).
Ô TD ghi ngày bản ghi tự doanh cuối trong cửa sổ (DESIGN §9: ngày của chính số đó) + số phiên có bản ghi khi cửa sổ
có lỗ; KL NN/TD trước GDKHQ cổ tức CP / CP thưởng (events-v2) quy về cơ sở cp hiện hành → nhãn E (kiểm chứng 27/09).
Phần dữ liệu live + chú thích live nằm ở chaebol_map_tab_screener_live.py (tách 27/09, tệp ≤ 800 dòng).
"""
from __future__ import annotations

import re

from chaebol_map_dom import (C, F_MONO, F_NUM, F_SERIF, alpha, can_data, h, jsx_text, sign_fixed, tier,
                             to_fixed, to_locale, upd_mark, v21_mark)
from chaebol_map_shell import Card, Section
from chaebol_map_tab_screener_live import _apply_live, _ddmm, _dossier_entry, _fx, _live_note, _pattern_q, _tg

SORT_COLS = ("tk", "phase", "sig", "px", "perf60", "ca60", "to60", "td60", "nn60")
DIRS = ("desc", "asc")
FKEY = "scr.phase|scr.sig|scr.chaebol"
SDKEY = "scr.sort|scr.dir"
FULLKEY = SDKEY + "|" + FKEY
_PHASE_OPTS = [("ALL", "Tất cả"), ("CAP", "CAP"), ("P1", "P1"), ("P2", "P2"), ("P2-P3", "P2-P3"),
               ("MARKUP", "MARKUP"), ("P3", "P3"), ("P3D", "P3D")]
_SIG_OPTS = [("ALL", "Tất cả"), ("BULL", "BULL"), ("MIX", "MIX"), ("BEAR", "BEAR")]
_CHB_OPTS = [("ALL", "Tất cả"), ("CHAEBOL_FRIENDLY", "Thân hữu"), ("NQ79", "NQ79/SOE"), ("ELIMINATED", "⛔ Loại")]
_PHASE_ORDER = ["CAP", "P1", "P2", "P2-P3", "MARKUP", "P3", "P3D"]
_SIG_ORDER = ["BEAR", "MIX", "BULL"]
_FL0 = {"px": 0, "perf60": 0, "ca60": 0, "to60": 0, "td60": 0, "nn60": 0, "sig": "MIX"}
RE_FRIENDLY = re.compile(r"Tuấn mượt|Sovico|Phượng|Vingroup|Bầu|Quân đội|FPT", re.I)
RE_NQ79 = re.compile(r"NQ79|SOE|Viettel|PVN", re.I)
RE_GOLD = re.compile(r"Tuấn|Sovico|Phượng")          # cột MÃ/NHÓM (không cờ i, như JSX dòng 6333)
INTRO_A = jsx_text("\n          Bảng matrix tổng hợp 45 mã VN30+ với 3 chiều phân loại đan vào nhau: ")
INTRO_END = jsx_text(" (nhóm thân hữu chính trị). Click cột để sort. Filter để zoom vào nhóm cần.\n        ")
SUB_V21 = "{n}/%d mã · Pillar IV (FiinTrade verified ≤08/05 · NgườiQuanSát ≥09/05) as of 08/05/2026"
PARCH40 = alpha(C.parch, "40")


def _mono(size, color, **extra):
    return {"fontSize": size, "color": color, "fontFamily": F_MONO, **extra}


def _k(node, *parts):
    """Đặt con = các phần TÁCH RỜI như React (mỗi {biểu thức} JSX là một nút chữ riêng; '' không thành nút).
    h() gộp chuỗi kề nhau, nhưng Chrome shape theo từng nút chữ → gộp lệch ref ~0,05 % pixel; tách thì 100 %."""
    kids = []

    def add(x):
        if x is None or x is False or x == "":
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


def _sgn(v, d, zfix=False):
    """`{v>=0?'+':''}{v.toFixed(d)}` → hai nút chữ ('+' | bỏ, số). zfix=True (số sống): lớp live in số làm tròn
    bằng 0 là '0.0' không dấu (lõi sign_fixed(zfix=True)); mode v21 và số V21 giữ '-0.0'/'+0.0' như trang gốc."""
    s = sign_fixed(v, d, zfix=zfix)
    return ["+", s[1:]] if s[:1] == "+" else ["", s]


# ── Dữ liệu V21 ─────────────────────────────────────────────────────────────


def _opts(v21, name, fallback):
    raw = v21.get(name)
    try:
        return [(str(o["v"]), str(o["l"])) for o in raw] if isinstance(raw, list) and raw else list(fallback)
    except (KeyError, TypeError):
        return list(fallback)


def _cats(chaebol):
    """Giá trị scr.chaebol làm hàng hiện (luật lọc dòng 6199–6207)."""
    out = ["ALL"]
    if RE_FRIENDLY.search(chaebol):
        out.append("CHAEBOL_FRIENDLY")
    if RE_NQ79.search(chaebol):
        out.append("NQ79")
    if "⛔" in chaebol:
        out.append("ELIMINATED")
    return out


def _v21_rows(v21):
    lst, flow = v21.get("VN30_LIST"), v21.get("FLOW")
    if not isinstance(lst, list) or not lst or not isinstance(flow, dict):
        raise ValueError("v21_const thiếu VN30_LIST/FLOW — chạy lại extract_v21.mjs rồi dựng lại")
    fl0 = v21.get("ScreenerTab.fl") or _FL0
    rows = []
    for t in lst:
        r = {**t, **(flow.get(t["tk"]) or fl0)}
        r.update(v21=True, new=False, cats=_cats(r["chaebol"]), label=None, basket=None, lv=None)
        rows.append(r)
    return rows


def _idx(order, v):
    return order.index(v) if v in order else -1          # indexOf


def _sk(r):
    """Khoá sắp (DESIGN §4): tk chuỗi, phase/sig = chỉ số trong mảng order, còn lại số; thiếu → bỏ (= 0)."""
    sk = {"tk": r["tk"], "phase": _idx(_PHASE_ORDER, r.get("phase")), "sig": _idx(_SIG_ORDER, r.get("sig"))}
    if r["lv"] is None:
        for c in ("px", "perf60", "ca60", "to60", "td60", "nn60"):
            sk[c] = r[c]
        return sk
    for c, k in (("px", "px"), ("perf60", "perf"), ("td60", "td"), ("nn60", "nn")):
        v = r["lv"].get(k)
        if v is not None and v.value is not None:
            sk[c] = v.value
    return sk


def _visible(r, fp, fs, fc):
    return (fp == "ALL" or r.get("phase") == fp) and (fs == "ALL" or r.get("sig") == fs) and fc in r["cats"]


def _order(rows, col, d):
    """rows.sort(comparator 6209–6221): ổn định; thiếu = 0; desc = đảo dấu (Python reverse giữ ổn định)."""
    if col not in SORT_COLS:
        return list(rows)
    return sorted(rows, key=lambda r: r["sk"].get(col, 0), reverse=(d == "desc"))


def _states(opts):
    combos = [(p, s, c) for p, _ in opts[0] for s, _ in opts[1] for c, _ in opts[2]]
    sds = [(c, d) for c in ("perf",) + SORT_COLS for d in DIRS]
    return combos, sds


def _stripes(rows, combos, sds):
    """{tk: [var…]}: nền parch40 cho hàng ở vị trí lẻ (i % 2 === 1) sau lọc + sắp, cho từng (sort, dir, lọc)."""
    odd = {r["tk"]: {} for r in rows}
    for combo in combos:
        vis = [r for r in rows if _visible(r, *combo)]
        cv = "|".join(combo)
        for sd in sds:
            for i, r in enumerate(_order(vis, *sd)):
                if i % 2 == 1:
                    odd[r["tk"]].setdefault(sd, []).append(cv)
    out = {}
    for tk, per in odd.items():
        groups = {}
        for sd in sds:                                     # thứ tự tất định
            if sd in per:
                groups.setdefault(tuple(per[sd]), []).append("|".join(sd))
        out[tk] = [{"if": {SDKEY: sdl, FKEY: list(fl)}, "s": {"background": PARCH40}} for fl, sdl in groups.items()]
    return out


def _picks(rows):
    buy = [r for r in rows if r.get("sig") == "BULL" and r.get("phase") in ("P2", "P2-P3", "MARKUP")
           and (r["to60"] > 20 or r["nn60"] > 20)]
    buy = sorted(buy, key=lambda r: r["to60"] + r["nn60"], reverse=True)[:8]
    avoid = [r for r in rows if r.get("sig") == "BEAR" and r.get("phase") in ("P3D", "P3") and r["nn60"] < -30]
    avoid = sorted(avoid, key=lambda r: r["nn60"])[:8]
    return tuple(r["tk"] for r in buy), tuple(r["tk"] for r in avoid)


def _pick_variants(rows, combos, sds):
    """→ (khoá if, [(tks_buy, [giá trị]), …], [(tks_avoid, [giá trị]), …]). Chỉ hàng V21 vào Top Picks."""
    base = [r for r in rows if r["v21"]]
    res = {}
    for combo in combos:
        vis = [r for r in base if _visible(r, *combo)]
        for sd in sds:
            res[combo + sd] = _picks(_order(vis, *sd))
    by_filter = all(len({res[combo + sd] for sd in sds}) == 1 for combo in combos)
    key = FKEY if by_filter else FULLKEY
    buy, avoid = {}, {}
    for combo in combos:
        for sd in ([sds[0]] if by_filter else sds):
            b, a = res[combo + sd]
            cv = "|".join(combo if by_filter else sd + combo)
            buy.setdefault(b, []).append(cv)
            avoid.setdefault(a, []).append(cv)
    return key, list(buy.items()), list(avoid.items())


# ── Nút ─────────────────────────────────────────────────────────────────────


_TH_LIVE = {"whiteSpace": "nowrap"}      # live: nhãn bậc/dấu V21 làm bảng rộng → tiêu đề không được gãy 2 dòng


def _sort_header(col, label, align_r=False, extra=None, live=False):
    """SortHeader (6232–6242). `width` chuỗi không đơn vị ("60") bị trình duyệt bỏ → không phát.
    Con: "{label}", " ", mũi tên (span theo state) như `{label} {sortBy===col && …}`."""
    node = h("th", {"padding": "10px 8px", "textAlign": "right" if align_r else "left", "fontSize": 9,
                    "letterSpacing": ".14em", "color": C.inkM, "fontFamily": F_MONO,
                    "borderBottom": "2px solid " + C.rule, "cursor": "pointer", "userSelect": "none",
                    "fontWeight": 500, **(_TH_LIVE if live else {})},
             h("span", None, "↓", if_={SDKEY: col + "|desc"}),
             h("span", None, "↑", if_={SDKEY: col + "|asc"}),
             extra,
             on={"sort": {"key": "scr.sort", "dir": "scr.dir", "col": col}},
             var=[{"if": {"scr.sort": col}, "s": {"color": C.gold, "borderBottom": "2px solid " + C.gold}}],
             key="scr.th." + col)
    return _k(node, label, " ", node["k"])


def _static_header(label, extra=None, live=False):
    return h("th", {"padding": "10px 8px", "textAlign": "left", "fontSize": 9, "color": C.inkM,
                    "letterSpacing": ".14em", "borderBottom": "2px solid " + C.rule, "fontWeight": 500,
                    **(_TH_LIVE if live else {})}, label, extra)


def _name_color(chaebol, default):
    return C.vermillion if "⛔" in chaebol else (C.gold if RE_GOLD.search(chaebol) else default)


def _num_cell(style, text, marks=None):
    return _k(h("td", {"padding": "9px 8px", "textAlign": "right", "fontSize": 11, **style}), text, marks)


def _flow_cells(r, live, ref):
    """7 ô số: GIÁ, Δ60D, CÁ NHÂN, TỔ CHỨC, TỰ DOANH, NƯỚC NGOÀI (luật màu 6348–6371)."""
    if not live:
        px, pf, ca, to, td, nn = r["px"], r["perf60"], r["ca60"], r["to60"], r["td60"], r["nn60"]
        return [
            _num_cell({"color": C.ink, "fontWeight": 500}, to_locale(px, "en") if px else "—"),
            _num_cell({"fontWeight": 600, "color": C.forest if pf >= 0 else C.vermillion}, _sgn(pf, 1) + ["%"]),
            _num_cell({"color": (C.ochre if ca > 0 else C.forest) if abs(ca) > 50 else C.inkD}, _sgn(ca, 1)),
            _num_cell({"fontWeight": 600 if abs(to) > 30 else 400,
                       "color": C.forest if to >= 30 else (C.vermillion if to <= -30 else C.inkD)}, _sgn(to, 1)),
            _num_cell({"color": C.forest if td >= 10 else (C.vermillion if td <= -10 else C.inkD)}, _sgn(td, 1)),
            _num_cell({"fontWeight": 700 if abs(nn) > 30 else 500,
                       "color": C.forest if nn >= 30 else (C.vermillion if nn <= -30 else C.inkD)}, _sgn(nn, 1)),
        ]
    lv = r["lv"]
    nw = {"whiteSpace": "nowrap"}           # live: '[CẦN DATA]' + nhãn bậc không được gãy dòng trong ô hẹp

    def ok(k):
        v = lv.get(k)
        return v if (v is not None and v.value is not None) else None

    px, pf, td, nn = ok("px"), ok("perf"), ok("td"), ok("nn")
    cells = [
        _num_cell({"color": C.ink, "fontWeight": 500, **nw}, to_locale(px.value, "en") if px else can_data(),
                  _tg(px, ref) if px else None),
        _num_cell({"fontWeight": 600, "color": C.forest if (pf and pf.value >= 0) else C.vermillion, **nw},
                  (_sgn(pf.value, 1, zfix=True) + ["%"]) if pf else can_data(), _tg(pf, ref) if pf else None),
        _num_cell({"color": C.inkD, **nw}, can_data()),
        _num_cell({"fontWeight": 400, "color": C.inkD, **nw}, can_data()),
    ]
    if td:
        cov = lv.get("td_cov")                # lỗ giữa cửa sổ: số phiên có bản ghi (dòng phụ, không nới cột)
        cells.append(_num_cell({"color": C.forest if td.value >= 10 else (C.vermillion if td.value <= -10 else C.inkD),
                                **nw}, _sgn(td.value, 1, zfix=True),
                               [_tg(td, ref), h("div", _mono(7, C.inkM, letterSpacing=".05em", marginTop=1),
                                                "%d/%d phiên" % cov) if cov else None]))
    else:
        cells.append(_num_cell({"color": C.inkD, **nw}, can_data()))
    if nn:
        v = nn.value
        cells.append(_num_cell({"fontWeight": 700 if abs(v) > 30 else 500,
                                "color": C.forest if v >= 30 else (C.vermillion if v <= -30 else C.inkD), **nw},
                               _sgn(v, 1, zfix=True), _tg(nn, ref)))
    else:
        cells.append(_num_cell({"fontWeight": 500, "color": C.inkD, **nw}, can_data()))
    return cells


def _phase_cell(r, colors):
    if not r.get("phase"):
        return h("td", {"padding": "9px 8px"}, h("span", {"fontSize": 9, "whiteSpace": "nowrap"}, can_data()))
    col = colors.get(r["phase"])
    grp = {"CAP": "scr.n.CAP", "P2": "scr.n.P2", "P2-P3": "scr.n.P2", "P3D": "scr.n.P3D"}.get(r["phase"])
    return h("td", {"padding": "9px 8px"},
             h("span", {"display": "inline-block", "padding": "2px 7px", "fontSize": 9, "fontWeight": 700,
                        "letterSpacing": ".08em", "color": col, "border": "1px solid %s" % col, "borderRadius": 1},
               r["phase"], grp=grp))


def _sig_cell(r, colors, live):
    grp = ("scr.n." + r["sig"]) if r.get("sig") in ("BULL", "MIX", "BEAR") else None
    if not live:
        return h("td", {"padding": "9px 8px"},
                 h("span", {"fontSize": 10, "fontWeight": 700, "color": colors.get(r["sig"]), "letterSpacing": ".06em"},
                   r["sig"], grp=grp))
    # một dòng '[CẦN DATA] · V21 BEAR' (hai dòng làm mỗi hàng cao ~51 px thay vì ~40 px của ref)
    return h("td", {"padding": "9px 8px", "whiteSpace": "nowrap"},
             h("span", {"fontSize": 10, "letterSpacing": ".06em"}, can_data()),
             h("span", {"fontSize": 8, "color": C.inkM, "marginLeft": 4, "marginRight": 4}, "·") if r.get("sig") else None,
             h("span", {"fontSize": 8, "fontWeight": 700, "color": colors.get(r["sig"]), "letterSpacing": ".06em"},
               "V21 " + r["sig"], grp=grp) if r.get("sig") else None)


def _label_cells(ctx, r, live):
    """Ô MÃ + NGÀNH + NHÓM CHAEBOL. Màu theo nhãn V21 (luật 6333/6338) — cả ở live."""
    tk_note = None
    if live and r.get("basket") is False:
        tk_note = h("div", _mono(7, C.inkM, fontWeight=400, letterSpacing=".05em", whiteSpace="nowrap",
                                 marginTop=2), "ngoài VN30 hiện hành")
    tk = h("td", {"padding": "9px 8px", "fontWeight": 700, "fontSize": 12,
                  "color": _name_color(r["chaebol"], C.ink)}, r["tk"], tk_note,
           on=r.get("cd2_on") if live else None)            # live: ô mã → tab codong v2 (đặt tab + codong.tk)
    sec = r.get("sec") or (can_data() if live else "")
    sec_td = h("td", {"padding": "9px 8px", "fontSize": 10, "color": C.inkD}, sec,
               tier("FACT-T2") if (live and r["new"] and r.get("sec")) else None)
    ch_style = {"padding": "9px 8px", "fontSize": 10, "color": _name_color(r["chaebol"], C.inkD)}
    if not live:
        return [tk, sec_td, h("td", ch_style, r["chaebol"])]
    fix = r.get("label")
    if fix:
        body = [fix["text"], tier(fix.get("tier") or "FACT-T2", fix.get("asof")), upd_mark(),
                h("div", _mono(8, C.inkM, letterSpacing=".04em", marginTop=2), "V21: " + r["chaebol"])]
    elif r["new"]:
        body = ([r["chaebol"], v21_mark() if r.get("label_src") == "v21:CHAEBOL_GROUPS" else tier("EST")]
                if r["chaebol"] else [can_data()])
    else:
        body = [r["chaebol"], tier("UNVERIFIED") if "⛔" in r["chaebol"] else None]
    return [tk, sec_td, h("td", ch_style, *body)]


def _cmt_cell(ctx, r, live, ref_basket):
    st = {"padding": "9px 8px", "fontSize": 10, "color": C.inkD, "fontFamily": F_SERIF, "maxWidth": 340,
          "lineHeight": 1.5}
    if not live:
        return h("td", st, r["cmt"])
    if r["new"]:
        return h("td", st, "VN30 hiện hành, không có trong VN30_LIST V21 — chưa có pha/nhận định.",
                 tier("FACT-T2", ref_basket), upd_mark())
    fix = _dossier_entry(ctx, r["tk"]).get("cmt")
    parts = fix.get("parts") if isinstance(fix, dict) else None
    if (isinstance(parts, list) and parts and fix.get("src")
            and all(isinstance(p, dict) and p.get("text") and p.get("src") for p in parts)):
        # mỗi mệnh đề mang bậc + ngày của chính nó (vd '-49.7%' là % FLOW V21 → E·29/04, không phải T1·08/05)
        kids = []
        for p in parts:
            kids += [_pattern_q(ctx, r["tk"], p["text"]), tier(p.get("tier") or "EST", p.get("asof")),
                     upd_mark() if p.get("upd") else None]
        return h("td", st, *kids)
    if isinstance(fix, dict) and fix.get("text") and fix.get("src"):      # mốc thời gian tương đối đã sai ngữ cảnh
        return h("td", st, _pattern_q(ctx, r["tk"], fix["text"]), tier(fix.get("tier") or "EST", fix.get("asof")),
                 upd_mark())
    return h("td", st, _pattern_q(ctx, r["tk"], r["cmt"]), v21_mark())


def _row(ctx, r, stripes, colors, live, ref, ref_basket):
    return h("tr", {"borderBottom": "1px solid " + C.rule, "background": "transparent"},
             *_label_cells(ctx, r, live),
             _phase_cell(r, colors["phase"]),
             _sig_cell(r, colors["sig"], live),
             *_flow_cells(r, live, ref),
             _cmt_cell(ctx, r, live, ref_basket),
             if_={"scr.phase": ["ALL"] + ([r["phase"]] if r.get("phase") else []),
                  "scr.sig": ["ALL"] + ([r["sig"]] if r.get("sig") else []),
                  "scr.chaebol": r["cats"]},
             var=stripes.get(r["tk"]) or None, sk=r["sk"], grp="scr.rows", key="scr.row." + r["tk"])


def _filter_group(label, key, options):
    """FilterGroup (6428–6445): nút active nền gold chữ bg, viền gold, 700."""
    btns = [h("button", {"padding": "4px 9px", "fontSize": 9, "letterSpacing": ".1em", "fontFamily": F_MONO,
                         "background": "transparent", "color": C.inkD, "border": "1px solid " + C.rule,
                         "borderRadius": 1, "cursor": "pointer", "fontWeight": 400},
                  lbl, on={"set": {key: v}},
                  var=[{"if": {key: v}, "s": {"background": C.gold, "color": C.bg, "border": "1px solid " + C.gold,
                                              "fontWeight": 700}}],
                  key="%s.%s" % (key, v)) for v, lbl in options]
    return h("div", {"display": "flex", "alignItems": "center", "gap": 6},
             h("span", {"fontSize": 9, "letterSpacing": ".18em", "color": C.inkM, "fontFamily": F_MONO}, label),
             h("div", {"display": "flex", "gap": 4, "flexWrap": "wrap"}, *btns))


def _summary(live):
    cards = [("HIỂN THỊ", None, C.ink, "scr.rows"), ("BULL", C.forest, C.forest, "scr.n.BULL"),
             ("MIX", C.ochre, C.ochre, "scr.n.MIX"), ("BEAR", C.vermillion, C.vermillion, "scr.n.BEAR"),
             ("CAPIT.", C.vermillion, C.vermillion, "scr.n.CAP"), ("★ P2 ACC", C.forest, C.forest, "scr.n.P2"),
             ("⚠ P3D DIST", C.vermillion, C.vermillion, "scr.n.P3D")]
    out = []
    for label, accent, color, grp in cards:
        mark = v21_mark() if (live and grp != "scr.rows") else None
        out.append(Card(
            h("div", {"fontSize": 8, "letterSpacing": ".16em", "color": C.inkM, "fontFamily": F_MONO}, label, mark),
            h("div", {"fontSize": 22, "fontWeight": 600, "color": color, "fontFamily": F_NUM},
              count={"grp": grp, "fmt": "{n}"}),
            accent=accent, padding=12, key="scr.card." + grp))
    return h("div", {"display": "grid", "gridTemplateColumns": "repeat(7, 1fr)", "gap": 8, "marginBottom": 18}, *out)


def _pick_row(r, mid, right, color, mark=None, mid_mark=None):
    return h("div", {"display": "flex", "justifyContent": "space-between", "alignItems": "baseline",
                     "padding": "7px 0", "borderBottom": "1px solid " + C.rule, "fontSize": 11},
             h("span", {"fontFamily": F_NUM, "fontWeight": 700, "color": C.ink}, r["tk"]),
             _k(h("span", {"fontSize": 10, "color": C.inkD, "fontFamily": F_MONO}), mid, mid_mark),
             _k(h("span", {"fontFamily": F_NUM, "color": color, "fontWeight": 600, "fontSize": 10}), right, mark))


def _top_picks(rows, key, buy_vars, avoid_vars, live):
    by = {r["tk"]: r for r in rows}

    def tg(r, t):
        return tier(t, r.get("date")) if live else None

    def buy_row(r):
        return _pick_row(r, [r["phase"], " · ", r["sec"]],
                         ["TC", _sgn(r["to60"], 0), " · NN", _sgn(r["nn60"], 0)], C.forest, tg(r, "FACT-T2"))

    def avoid_row(r):                     # Δ perf60 là % dẫn xuất → E (api_data §1.2), NN/CN FiinTrade → T2
        return _pick_row(r, [r["phase"], " · Δ", _sgn(r["perf60"], 0), "%"],
                         ["NN", to_fixed(r["nn60"], 0), " · CN+", to_fixed(r["ca60"], 0)], C.vermillion,
                         tg(r, "FACT-T2"), tg(r, "EST"))

    def variants(vs, fn):
        return [h("div", None, *[fn(by[tk]) for tk in tks], if_={key: combos}) for tks, combos in vs if tks]

    title = {"fontSize": 11, "letterSpacing": ".18em", "fontFamily": F_MONO, "marginBottom": 10, "fontWeight": 600}
    # live: STRONG BUY/AVOID là bản lưu V21 (DESIGN §0.5) — dấu V21 ngay trên dòng tiêu đề thẻ, lời chú ở sub
    sub = ["STRONG BUY/AVOID: bản lưu", v21_mark(), " · FiinTrade ≤08/05 đóng băng · lưu trữ, không phải khuyến nghị"]
    return Section(
        "Top Picks Distilled từ Screener",
        h("div", {"display": "grid", "gridTemplateColumns": "repeat(2, 1fr)", "gap": 14},
          Card(h("div", {**title, "color": C.forest},
                 "★ STRONG BUY · BULL × P2/MARKUP × Tổ chức/NN tích cực", v21_mark()),
               *variants(buy_vars, buy_row), accent=C.forest, key="scr.picks.buy"),
          Card(h("div", {**title, "color": C.vermillion},
                 "⚠ AVOID · BEAR × P3D × NN/Tổ chức rút mạnh", v21_mark()),
               *variants(avoid_vars, avoid_row), accent=C.vermillion, key="scr.picks.avoid")),
        accent=C.forest, sub=h("span", None, *sub) if live else None, key="scr.picks")


def _legend(live):
    first = (h("span", None, "● Đơn vị flow: ", h("strong", None, "triệu cổ phiếu"),
               " (cơ sở cp hiện hành) ròng 60 phiên — NN gồm thoả thuận, TD khớp; CN/TC ", can_data(),
               upd_mark()) if live else
             h("span", None, "● Đơn vị flow: ", h("strong", None, "triệu cổ phiếu"), " KL khớp ròng 60 phiên"))
    return h("div", {"marginTop": 12, "display": "flex", "gap": 18, "fontSize": 9, "color": C.inkM,
                     "fontFamily": F_MONO, "letterSpacing": ".08em", "flexWrap": "wrap"},
             first,
             h("span", None, "● ", h("span", {"color": C.gold}, "Vàng"), ": chaebol thân hữu"),
             h("span", None, "● ", h("span", {"color": C.vermillion}, "Đỏ"), ": ⛔ loại khỏi cuộc / distribution"),
             h("span", None, "● ", h("span", {"color": C.forest}, "Xanh"), ": tích lũy ★"))


def _table(ctx, rows, stripes, colors, live, info):
    ref = info.get("data_to") if live else None
    ref_basket = info.get("basket_asof") if live else None
    head = h("tr", {"background": C.parch},
             _sort_header("tk", "MÃ", live=live),
             _static_header("NGÀNH", live=live),
             _static_header("NHÓM CHAEBOL", [v21_mark(), tier("UNVERIFIED")] if live else None, live=live),
             _sort_header("phase", "PHASE", extra=v21_mark() if live else None, live=live),
             _sort_header("sig", "SIG", live=live),
             _sort_header("px", "GIÁ", True, live=live),
             _sort_header("perf60", "Δ60D", True, live=live),
             _sort_header("ca60", "CÁ NHÂN", True, live=live),
             _sort_header("to60", "TỔ CHỨC", True, live=live),
             _sort_header("td60", "TỰ DOANH", True, live=live),
             _sort_header("nn60", "NƯỚC NGOÀI", True, live=live),
             _static_header("NHẬN ĐỊNH", live=live))
    body = [_row(ctx, r, stripes, colors, live, ref, ref_basket) for r in rows]
    return h("div", {"background": C.paper, "border": "1px solid " + C.rule, "borderRadius": 2, "overflow": "hidden"},
             h("div", {"overflowX": "auto"},
               h("table", {"width": "100%", "borderCollapse": "collapse", "minWidth": 1200, "fontFamily": F_MONO},
                 h("thead", None, head),
                 h("tbody", None, *body, sort={"key": "scr.sort", "dir": "scr.dir"}))), key="scr.table")


def _csv(rows, live):
    out = []
    for r in rows:
        d = {"ma": r["tk"], "nganh": r.get("sec") or "", "nhom_chaebol_v21": r["chaebol"] if r["v21"] else "",
             "phase_v21": r.get("phase") or "", "sig_v21": r.get("sig") or ""}
        if not live:
            d.update({k: r[k] for k in ("px", "perf60", "ca60", "to60", "td60", "nn60")}, as_of=r.get("date") or "")
        else:
            for k, c in (("px", "gia"), ("perf", "delta60_pct"), ("td", "td60_trieu_cp"), ("nn", "nn60_trieu_cp")):
                v = r["lv"].get(k)
                ok = v is not None and v.value is not None
                d[c] = v.value if ok else "[CẦN DATA]"
                d[c + "_bac"] = v.tier if ok else ""
                d[c + "_asof"] = v.asof if ok else ""
            cov = r["lv"].get("td_cov")
            d.update(ca60="[CẦN DATA]", to60="[CẦN DATA]", trong_vn30=r.get("basket"),
                     nhom_chaebol_sua=(r.get("label") or {}).get("text", ""),
                     td60_phien_co=("%d/%d" % cov) if cov else "",
                     quy_doi_quyen="; ".join("%s ×%s" % (x, _fx(f)) for x, f in r["lv"].get("conv") or []))
        out.append(d)
    return out


def build_screener(ctx):
    v21 = ctx.v21 or {}
    live = bool(ctx.live)
    opts = (_opts(v21, "ScreenerTab.jsx@L6297", _PHASE_OPTS), _opts(v21, "ScreenerTab.jsx@L6299", _SIG_OPTS),
            _opts(v21, "ScreenerTab.jsx@L6301", _CHB_OPTS))
    colors = {"phase": v21.get("ScreenerTab.phaseColors") or {
        "CAP": C.vermillion, "P1": C.inkM, "P2": C.forest, "P2-P3": C.forest, "MARKUP": C.gold, "P3": C.ochre,
        "P3D": C.vermillion}, "sig": v21.get("ScreenerTab.sigColors") or {
        "BULL": C.forest, "BEAR": C.vermillion, "MIX": C.ochre}}
    rows = _v21_rows(v21)
    n_v21 = len(rows)
    info = {}
    if live:
        rows, info = _apply_live(ctx, v21, rows, _cats)
    for r in rows:
        r["sk"] = _sk(r)
    combos, sds = _states(opts)
    stripes = _stripes(rows, combos, sds)
    key, buy_vars, avoid_vars = _pick_variants(rows, combos, sds)
    n = len(rows)
    if live:
        w0, w1 = info.get("win") or (None, None)      # NN/TD là 60 phiên vc_lk thuần, không nối FiinTrade
        sub = [h("span", None, count={"grp": "scr.rows", "fmt": "{n}/%d mã · Pillar IV · NN/TD vc_lk 60 phiên %s→%s "
                                      "(TD tới %s) · Top Picks: FiinTrade ≤08/05 đóng băng"
                                      % (n, _ddmm(w0), _ddmm(w1, True), info.get("td_span") or "—")}),
               upd_mark()]
        intro_a = INTRO_A.replace("45 mã", "%d mã" % n)
    else:
        sub = h("span", None, count={"grp": "scr.rows", "fmt": SUB_V21 % n_v21})
        intro_a = INTRO_A
    strong = {"color": C.ink}
    intro = h("div", {"fontSize": 13, "fontFamily": F_SERIF, "color": C.inkD, "lineHeight": 1.7,
                      "fontStyle": "italic", "marginBottom": 18, "padding": "14px 18px", "background": C.parch,
                      "borderLeft": "3px solid " + C.gold},
              intro_a, h("strong", strong, "Phase Howard Marks"), " (đáy → đỉnh), ",
              h("strong", strong, "Flow signal Pillar IV"),
              " (BULL/BEAR/MIX dựa trên 60d net buy 4 nhóm NĐT), và ", h("strong", strong, "chaebol affiliation"),
              INTRO_END, upd_mark() if (live and n != n_v21) else None)
    filters = h("div", {"display": "flex", "gap": 14, "flexWrap": "wrap", "marginBottom": 14, "padding": "12px 14px",
                        "background": C.parch, "borderRadius": 2},
                _filter_group("PHASE", "scr.phase", opts[0]), _filter_group("FLOW", "scr.sig", opts[1]),
                _filter_group("CHAEBOL", "scr.chaebol", opts[2]), key="scr.filters")
    main = Section("VN30+ Screener — Phase × Flow × Chaebol Matrix",
                   intro, _live_note(info) if live else None, _summary(live), filters,
                   _table(ctx, rows, stripes, colors, live, info), _legend(live),
                   accent=C.gold, sub=sub, key="scr.main")
    root = h("div", None, main, _top_picks(rows, key, buy_vars, avoid_vars, live), key="scr.root")
    states = [
        {"key": "scr.sort", "default": "perf", "options": ["perf"] + list(SORT_COLS)},
        {"key": "scr.dir", "default": "desc", "options": list(DIRS)},
        {"key": "scr.phase", "default": "ALL", "options": [v for v, _ in opts[0]]},
        {"key": "scr.sig", "default": "ALL", "options": [v for v, _ in opts[1]]},
        {"key": "scr.chaebol", "default": "ALL", "options": [v for v, _ in opts[2]]},
    ]
    return {"root": root, "states": states, "csv": _csv(rows, live)}
