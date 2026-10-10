#!/usr/bin/env python3
"""
chaebol_map_shell — khung trang + atom dùng chung của tab "chaebol_map".

Nguồn thiết kế: chaebol_map_spec/page_p1_shell_atoms.md (§3 khung, §4 atom) và SRC
~/Downloads/master_plan_v21_chaebol_vn30.html dòng 488–522 (root), 4674–4720 (Header), 5033–5168 (TabBar,
Footer, Section, Card, Stat, Pill, FlowBar, FlowSignal), 7810 (addendum tĩnh ngoài React). Style chép NGUYÊN
thứ tự khoá của JSX (shorthand trước longhand), kể cả các bất thường của trang: thanh accent Section là flex item
co được, track FlowBar trùng màu nền FlowSignal (#1f1d24 → vô hình), FlowBar tô thanh theo `>0` nhưng số theo `>=0`.

Mode live (DESIGN §0.6, §6.2): Header thêm dòng CỔNG + chú giải bậc ngay dưới dải I.–V.; khối BUILT dùng ngày
dựng + VN-Index / USD/VND sống kèm nhãn bậc; h1 dùng tháng dựng + dấu ↻ (đã viết lại so với "Tháng 5, 2026");
chú giải bậc là một khối inline-block (xuống dòng nguyên khối); addendum 09/06 gắn dấu "lưu trữ 09/06".
Số sống lấy từ ctx.live (chaebol_map.py nạp mềm từ chaebol_map_data); thiếu → [CẦN DATA].
Móc dossier (chỉ live, thêm 27/09 bởi agent tab audit): ctx.dossier["header"] = {subline, strip{"I."…"V. ★ NEW"},
footer{left, right}} (mỗi mục {text, tier, asof, src}) thay subline / mục dải / hai span Footer + dấu ↻; Footer "As of" =
ngày dữ liệu (ctx.live_info.data_to). Không có khối → giữ nguyên văn V21 (mode v21 không bao giờ đọc).
Addendum ở live (thêm 27/09, cùng agent): dossier header.addendum {note, p2, rows{Cxx: {claim, check, rescored}}} → nhãn
bậc từng số (chữ vẫn nguyên văn), "Pattern X?" cho mã ngoài 30 mã Toàn Vũ, hàng rescored trỏ bản chấm lại claims20.
"""
from __future__ import annotations

import re

from chaebol_map_dom import (
    C, F_BODY, F_DISPLAY, F_MONO, F_NUM, F_ROOT, F_SERIF, F_SYS, TIER_COLORS, can_data, h, is_live, js_string,
    slot, status_pill, tier, to_fixed, to_locale, today, upd_mark, v21_mark,
)

# ── TABS (SRC dòng 467–486, đúng thứ tự; tab "10" đứng cuối) ─────────────────

TABS_V21 = (
    ("vnindex", "★ ✪ VNINDEX", "📈"),
    ("vn30", "★ ✪ VN30", "⊕"),
    ("codong", "★ 🏛 CẤU TRÚC CỔ ĐÔNG", "⛁"),
    ("overview", "00 · TỔNG QUAN", "◐"),
    ("chaebol", "01 · CHAEBOL MAP", "◆"),
    ("tuanmuot", "02 · TUẤN MƯỢT", "★"),
    ("sovico", "03 · SOVICO", "✈"),
    ("phuong", "04 · BÀ PHƯỢNG", "❀"),
    ("bauthuy", "05 · BẦU THỤY", "⚽"),
    ("eliminated", "06 · LOẠI KHỎI CUỘC", "⛔"),
    ("screener", "07 · VN30 SCREENER", "▦"),
    ("portfolio", "08 · DANH MỤC", "⛁"),
    ("changelog", "09 · CLAIMS C01-C20 + CHANGELOG", "§"),
    ("claims54", "★ 11 · 54 CLAIMS PRIORITY", "⚠"),
    ("catalyst", "★ 12 · CATALYST CALENDAR", "📅"),
    ("portfolio25", "★ 13 · ACTION PORTFOLIO 25", "💼"),
    ("deep6", "★ 14 · DEEP-DIVE 24 CHAEBOL", "🔬"),
    ("audit", "10 · DATA & METRIC AUDIT", "⚙"),
)


def tabs_from_v21(v21):
    """TABS từ v21_const (khoá 'TABS' hoặc 'tabs': [{id,label,icon}] hoặc [[id,label,icon]]) nếu hợp lệ đủ 18,
    ngược lại bản chép cứng TABS_V21. Trả (tabs, lý do dự phòng | None)."""
    raw = (v21 or {}).get("TABS") or (v21 or {}).get("tabs")
    if not raw:
        return list(TABS_V21), "v21_const không có TABS → dùng bản chép SRC 467–486"
    tabs = []
    try:
        for t in raw:
            if isinstance(t, dict):
                tabs.append((str(t["id"]), str(t["label"]), str(t["icon"])))
            else:
                tabs.append((str(t[0]), str(t[1]), str(t[2])))
    except (KeyError, IndexError, TypeError):
        return list(TABS_V21), "v21_const.TABS sai dạng → dùng bản chép SRC 467–486"
    if len(tabs) != 18 or len({t[0] for t in tabs}) != 18:
        return list(TABS_V21), "v21_const.TABS không đủ 18 id riêng → dùng bản chép SRC 467–486"
    return tabs, None


# ── Atom dùng chung (SRC 5086–5168) ─────────────────────────────────────────


def Section(title, *children, accent=None, sub=None, key=None, **kw):
    """<Section title accent sub>: section mb32 · hàng tiêu đề flex baseline gap14 · thanh 4×24 · h2 Cormorant 22/600."""
    return h("section", {"marginBottom": 32},
             h("div", {"display": "flex", "alignItems": "baseline", "gap": 14, "marginBottom": 14,
                       "paddingBottom": 8, "borderBottom": "1px solid " + C.rule},
               h("div", {"width": 4, "height": 24, "background": accent or C.gold}),
               h("h2", {"margin": 0, "fontSize": 22, "fontWeight": 600, "fontFamily": F_DISPLAY, "color": C.ink,
                        "letterSpacing": "-0.01em"}, title),
               h("div", {"fontSize": 10, "color": C.inkM, "letterSpacing": ".1em", "fontFamily": F_MONO,
                         "marginLeft": "auto"}, sub) if sub else None),
             h("div", None, *children), key=key, **kw)


def Card(*children, accent=None, padding=18, key=None, **kw):
    """<Card accent padding=18>: nền paper, viền rule, viền trái 3px accent nếu có, bo 2."""
    return h("div", {"background": C.paper, "padding": padding, "border": "1px solid " + C.rule,
                     "borderLeft": ("3px solid " + accent) if accent else ("1px solid " + C.rule),
                     "borderRadius": 2}, *children, key=key, **kw)


def Stat(label, value, sub=None, color=None, big=False, key=None, **kw):
    """<Stat label value sub color big>: flex '1 1 160px' minWidth 140; value JetBrains 18 (big 26) 600."""
    return h("div", {"flex": "1 1 160px", "minWidth": 140},
             h("div", {"fontSize": 9, "letterSpacing": ".18em", "color": C.inkM, "fontFamily": F_MONO,
                       "marginBottom": 5}, label),
             h("div", {"fontSize": 26 if big else 18, "fontWeight": 600, "color": color or C.ink,
                       "fontFamily": F_NUM, "letterSpacing": "-0.02em"}, value),
             h("div", {"fontSize": 9, "color": C.inkM, "marginTop": 3, "fontFamily": F_MONO}, sub) if sub else None,
             key=key, **kw)


def Pill(text, color=None, dim=False, key=None, **kw):
    """<Pill text color dim>: inline-block, padding 3px 8px, Plex 9px ls .12em, viền 1px màu (dim → inkM/rule)."""
    return h("span", {"display": "inline-block", "padding": "3px 8px", "fontSize": 9, "letterSpacing": ".12em",
                      "fontFamily": F_MONO, "color": C.inkM if dim else (color or C.ink),
                      "border": "1px solid " + (C.rule if dim else (color or C.rule)), "borderRadius": 1},
             text, key=key, **kw)


def FlowBar(label, value, color, tier_tag=None, asof=None):
    """<FlowBar label value color> (chỉ dùng trong FlowSignal). value None → không vẽ thanh, số = [CẦN DATA].

    Bề rộng thanh = `${Math.min(50, |v|·0.3)}%` (chuỗi String(number) của JS); v<0 mọc sang trái (right 50%).
    Màu số theo v>=0 (forest) / <0 (vermillion); màu thanh do FlowSignal truyền theo v>0 (bất thường gốc, giữ).
    """
    missing = value is None
    if missing:
        fill = None
        num = [can_data()] if is_live() else ["—"]
        num_color = C.vermillion
    else:
        width = min(50, abs(value) * 0.3)
        fill = h("div", {"position": "absolute", "left": "auto" if value < 0 else "50%",
                         "right": "50%" if value < 0 else "auto", "top": 0, "height": 6,
                         "width": js_string(width) + "%", "background": color, "borderRadius": 1,
                         "transition": "width 0.3s"})
        num = [("+" if value >= 0 else "") + to_fixed(value, 1) + "M",
               tier(tier_tag, asof) if tier_tag else None]
        num_color = C.forest if value >= 0 else C.vermillion
    return h("div", {"display": "flex", "alignItems": "center", "gap": 10, "fontSize": 11, "fontFamily": F_NUM,
                     "marginBottom": 4},
             h("span", {"width": 80, "color": C.inkD, "fontSize": 10, "letterSpacing": ".08em"}, label),
             h("div", {"flex": 1, "height": 6, "background": C.parch, "position": "relative", "borderRadius": 1},
               fill,
               h("div", {"position": "absolute", "left": "50%", "top": -2, "width": 1, "height": 10,
                         "background": C.inkM})),
             h("span", {"width": 80, "textAlign": "right", "color": num_color, "fontWeight": 600}, *num))


FLOW_HEAD_V21 = "FLOW 60D · FIINTRADE ≤08/05 · NGƯỜIQUANSÁT ≥09/05"
_SIG_COLORS = {"BULL": C.forest, "BEAR": C.vermillion, "MIX": C.ochre}
_FLOW_ROWS = (("Cá nhân", "ca60"), ("Tổ chức", "to60"), ("Tự doanh", "td60"), ("Nước ngoài", "nn60"))


def FlowSignal(fl, head=FLOW_HEAD_V21, tiers=None, key=None):
    """<FlowSignal fl>: fl = {sig, ca60, to60, td60, nn60, date, px, perf60}; giá trị None → [CẦN DATA] (live).

    head: chuỗi nguồn ở góc trái (mặc định nguyên văn V21). tiers: {trường: bậc | (bậc, asof)} → nhãn bậc sau số
    (chỉ live). Dòng cuối: `Tham chiếu cuối: {date} · Giá {px en} · Δ60d ` + span ±perf60.toFixed(1)%.
    """
    tiers = tiers or {}

    def tg(field):
        t = tiers.get(field)
        if t is None:
            return None, None
        return (t[0], t[1]) if isinstance(t, (tuple, list)) else (t, None)

    rows = []
    for label, field in _FLOW_ROWS:
        v = fl.get(field)
        color = None if v is None else (C.forest if v > 0 else C.vermillion)
        rows.append(FlowBar(label, v, color, *tg(field)))
    sig = fl.get("sig")
    sig_style = {"fontSize": 11, "fontWeight": 700, "color": _SIG_COLORS.get(sig), "fontFamily": F_MONO,
                 "letterSpacing": ".1em"}
    perf = fl.get("perf60")
    px = fl.get("px")
    miss = can_data() if is_live() else "—"
    return h("div", {"background": C.parch, "padding": 12, "borderRadius": 2, "marginTop": 10, "marginBottom": 10},
             h("div", {"display": "flex", "justifyContent": "space-between", "alignItems": "baseline",
                       "marginBottom": 8},
               h("span", {"fontSize": 9, "letterSpacing": ".18em", "color": C.inkM, "fontFamily": F_MONO}, head),
               h("span", sig_style, sig if sig is not None else miss, tier(*tg("sig")) if tg("sig")[0] else None)),
             *rows,
             h("div", {"fontSize": 9, "color": C.inkM, "marginTop": 6, "fontFamily": F_MONO, "letterSpacing": ".05em"},
               "Tham chiếu cuối: ", fl.get("date") or miss, " · Giá ",
               to_locale(px, "en") if px is not None else miss, tier(*tg("px")) if tg("px")[0] else None,
               " · Δ60d ",
               h("span", {"color": C.forest if perf >= 0 else C.vermillion},
                 ("+" if perf >= 0 else "") + to_fixed(perf, 1) + "%",
                 tier(*tg("perf60")) if tg("perf60")[0] else None) if perf is not None else miss),
             key=key)


def placeholder_tab(tab_id, label, module, func, reason=None, error=None):
    """Tab giữ chỗ khi builder chưa có / lỗi: Section "[chưa dựng] · {label}" (hoặc "[lỗi dựng]")."""
    title = ("[lỗi dựng] · " if error else "[chưa dựng] · ") + label
    body = error or ("Tab “%s” chưa có builder: cần %s.py với hàm %s(ctx). Chạy lại build sau khi agent tab ghi xong."
                     % (label, module, func))
    lines = [h("div", None, body)]
    if reason:
        lines.append(h("div", {"marginTop": 6, "color": C.inkM}, reason))
    return h("div", {}, Section(title, Card(h("div", {"fontSize": 12, "color": C.inkD, "fontFamily": F_MONO,
                                                      "lineHeight": 1.6}, *lines)),
                                sub=module + "." + func), key="placeholder:" + tab_id)


# ── Header (SRC 4674–4720) ──────────────────────────────────────────────────

SUBLINE = ("⨯ Tiếp nối V20 — Bổ sung 4 nhóm tỷ phú thân hữu & 30 mã VN30 với Pillar IV flow data: FiinTrade "
           "(verified ≤08/05/2026) + NgườiQuanSát.vn (forward ≥09/05/2026) ⨯")
STRIP = (("I.", " TOÀN VŨ điểm đảo chiều cổ đông"), ("II.", " PHÚ SSI VWAP cụm"), ("III.", " Ý ĐỒ CHỦ THỂ tỷ phú"),
         ("IV.", " Pillar real-time (FiinTrade ≤08/05 · NgườiQuanSát ≥09/05)"),
         ("V. ★ NEW", " CHAEBOL POLITICAL MAPPING"))
TIER_LEGEND = (("T1", "FACT-T1", " CBTT/BCTC"), ("T2", "FACT-T2", " vendor"), ("T3", "SS-T3", " sell-side/Toàn Vũ"),
               ("E", "EST", " ước"), ("U", "UNVERIFIED", " chưa xác minh"))
_ROMAN = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
          (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))


def roman(n):
    out = []
    for v, s in _ROMAN:
        while n >= v:
            out.append(s)
            n -= v
    return "".join(out)


def built_label(d):
    """27/09/2026 → '27 · IX · MMXXVI' (kiểu '08 · V · MMXXVI' của V21)."""
    return "%02d · %s · %s" % (d.day, roman(d.month), roman(d.year))


def _fmt_dmy(iso):
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(iso or ""))
    return "%s/%s/%s" % (m.group(3), m.group(2), m.group(1)) if m else (str(iso) if iso else None)


def _live_number(item, fmt):
    """ctx.live[x] = {"value", "date", "tier", "src"} | None → [chuỗi số, nhãn bậc] hoặc [CẦN DATA]."""
    if not item or item.get("value") is None:
        return [can_data()]
    return [fmt(item["value"]), tier(item["tier"], item.get("date")) if item.get("tier") else None]


def _cong_line(live):
    cong = (live or {}).get("cong") or {}
    text = str(cong.get("text") or "[CẦN DATA — chưa đọc được CỔNG từ chaebol_map_data] · không kết luận per-mã")
    body = re.sub(r"^\s*CỔNG\s*:\s*", "", text)
    color = C.vermillion if ("[CẦN DATA" in body or "DỪNG" in body) else C.gold
    asof = _fmt_dmy(cong.get("as_of")) or today().strftime("%d/%m/%Y")
    items = [h("span", {"color": C.inkM}, "Nhãn bậc:")]
    for i, (short, full, desc) in enumerate(TIER_LEGEND):
        items.append(h("span", {"color": C.inkM}, (" " if i == 0 else " · ")))
        # mỗi mục chú giải không tách dòng (tránh "T3 sell-" / "side/Toàn Vũ" khi dòng CỔNG dài phải xuống dòng)
        items.append(h("span", {"color": C.inkM, "whiteSpace": "nowrap"},
                       h("span", {"color": TIER_COLORS[full]}, short), desc))
    # chú giải là MỘT khối inline-block (nguyên tử): CỔNG dài thì cả chú giải xuống dòng dưới, không bị cắt đôi
    # "T1 · T2 ·" / "T3 · E · U" (kiểm chứng 27/09); CỔNG ngắn thì vẫn cùng một dòng như DESIGN §6.2.
    legend = [h("span", {"color": C.inkM}, " · "), h("span", {"display": "inline-block"}, *items)]
    return h("div", {"marginTop": 10, "fontSize": 10, "fontFamily": F_MONO, "letterSpacing": ".1em",
                     "color": color}, "CỔNG: " + body + " · as of " + asof, *legend, key="cong")


def _dossier_header(ctx):
    """Mode live: khối `header` của dossier (cap_nhat_<ngày>*.json, DESIGN §7) — {subline, strip{số La Mã}, footer
    {left, right}}, mỗi mục {text, tier, asof, src}. v21 / thiếu dossier / sai dạng → {} (giữ nguyên văn V21)."""
    if not is_live() or ctx is None:
        return {}
    hd = (getattr(ctx, "dossier", None) or {}).get("header")
    return hd if isinstance(hd, dict) else {}


def _dz_text(item):
    """Mục dossier {text, asof, …} → (text, asof) nếu có chữ, ngược lại (None, None)."""
    if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"].strip():
        return item["text"], item.get("asof")
    return None, None


def Header(ctx=None):
    live = is_live()
    info = (getattr(ctx, "live_info", None) or {}) if ctx is not None else {}
    hd = _dossier_header(ctx)
    sub_text, sub_asof = _dz_text(hd.get("subline"))
    strip_dz = hd.get("strip") if isinstance(hd.get("strip"), dict) else {}
    d = today()
    month = ("Tháng %d, %d" % (d.month, d.year)) if live else "Tháng 5, 2026"
    built = built_label(d) if live else "08 · V · MMXXVI"
    if live:
        idx_line = ["VN-Index ", *_live_number(info.get("vnindex"), lambda v: to_locale(v, "en-US", max_frac=2)),
                    " · USD/VND ", *_live_number(info.get("usdvnd"), lambda v: to_locale(v, "en-US", max_frac=0))]
    else:
        idx_line = ["VN-Index ~1,265 · USD/VND 26,300"]
    strip = []
    for i, (num, txt) in enumerate(STRIP):
        if i:
            strip.append(h("span", {"color": C.inkM}, "·"))
        new_txt, new_asof = _dz_text(strip_dz.get(num))
        if new_txt is None:
            strip.append(h("span", None, h("span", {"color": C.gold}, num), txt))
        else:
            strip.append(h("span", None, h("span", {"color": C.gold}, num), new_txt, upd_mark(new_asof)))
    return h("header", {"borderBottom": "1px solid " + C.rule, "padding": "24px 28px 20px",
                        "background": "linear-gradient(180deg, %s70 0%%, transparent 100%%)" % C.paper},
             h("div", {"maxWidth": 1480, "margin": "0 auto"},
               h("div", {"display": "flex", "alignItems": "baseline", "justifyContent": "space-between",
                         "flexWrap": "wrap", "gap": 24},
                 h("div", None,
                   h("div", {"fontSize": 10, "letterSpacing": ".32em", "color": C.inkM, "marginBottom": 8,
                             "fontFamily": F_MONO}, "MASTER PLAN · VOLUME XXI · CHAEBOL EXTENSION"),
                   h("h1", {"margin": 0, "fontSize": 42, "fontWeight": 600, "letterSpacing": "-0.02em",
                            "fontFamily": F_DISPLAY, "color": C.ink, "lineHeight": 1.05},
                     "Bản Đồ ", h("span", {"fontStyle": "italic", "color": C.gold}, "Chaebol"), " & VN30 — ",
                     h("span", {"color": C.inkD}, month), upd_mark(d) if live else None),
                   h("div", {"fontSize": 11, "color": C.inkD, "marginTop": 10, "fontFamily": F_MONO,
                             "letterSpacing": ".06em"},
                     *((SUBLINE,) if sub_text is None else (sub_text, upd_mark(sub_asof))))),
                 h("div", {"textAlign": "right"},
                   h("div", {"fontSize": 10, "letterSpacing": ".2em", "color": C.inkM, "marginBottom": 6}, "BUILT"),
                   h("div", {"fontFamily": F_NUM, "fontSize": 14, "color": C.gold, "fontWeight": 600}, built),
                   h("div", {"fontSize": 10, "color": C.inkM, "marginTop": 4}, *idx_line), key="built")),
               h("div", {"display": "flex", "gap": 16, "marginTop": 18, "fontSize": 10, "fontFamily": F_MONO,
                         "letterSpacing": ".08em", "color": C.inkD, "flexWrap": "wrap"}, *strip, key="strip"),
               _cong_line(info) if live else None),
             key="header")


# ── TabBar (SRC 5033–5059) ──────────────────────────────────────────────────


def TabBar(tabs):
    """nav sticky + cuộn ngang; 18 nút `on: set tab`; kiểu active qua var {"if": {"tab": id}}."""
    buttons = []
    for tid, label, icon in tabs:
        buttons.append(h(
            "button",
            {"padding": "14px 18px", "fontSize": 11, "fontWeight": 500, "background": "none", "border": "none",
             "cursor": "pointer", "color": C.inkD, "borderBottom": "2px solid transparent", "letterSpacing": ".18em",
             "fontFamily": F_MONO, "transition": "all 0.2s"},
            h("span", {"marginRight": 8, "color": C.inkM}, icon,
              var=[{"if": {"tab": tid}, "s": {"color": C.gold}}]),
            label,
            on={"set": {"tab": tid}},
            var=[{"if": {"tab": tid}, "s": {"color": C.gold, "borderBottom": "2px solid " + C.gold}}],
            key="tab:" + tid))
    return h("nav", {"borderBottom": "1px solid " + C.rule, "background": C.paper + "80", "backdropFilter": "blur(8px)",
                     "position": "sticky", "top": 0, "zIndex": 10, "overflowX": "auto", "whiteSpace": "nowrap"},
             h("div", {"maxWidth": 1480, "margin": "0 auto", "padding": "0 28px", "display": "flex", "gap": 0},
               *buttons),
             key="tabbar")


# ── Footer (SRC 5062–5081) ──────────────────────────────────────────────────

FOOT_LEFT = ("MASTER PLAN V21.29 · ALL-IN-ONE v2 MAX ENRICH: +4 new tickers (ACB best-in-class + NVL DISTRESS + GAS "
             "NQ79 cleanest + KSV rare earth) — 25 tickers V21 deep-dive complete · As of 12/05/2026")
FOOT_RIGHT = "FREE: NgườiQuanSát + FiinTrade ≤08/05 + CafeF + Vietstock + SimplizeBroker + CapIQ ondemand"
FOOT_QUOTE = ('"Khi anh nhìn 1 cổ phiếu chỉ qua giá, anh đang nhìn cá tăng-giảm trong 1 hồ. Khi anh nhìn qua '
              'chaebol-map, anh thấy cả hệ sinh thái — ai bơm nước, ai xả nước, ai đặt mồi, ai bị câu. Cùng 1 con '
              'cá, hai cách nhìn khác nhau hoàn toàn."')
FOOT_ATTR = '— Phương pháp luận Toàn Vũ × Phú SSI, đối chiếu Howard Marks "what they don\'t tell you"'


def _footer_spans(ctx):
    """Hai span đầu Footer. Live + dossier.header.footer: left = text + ' · As of <ngày dữ liệu>' (ctx.live_info
    .data_to — không phải ngày dựng; thiếu → [CẦN DATA]) + ↻; right = text + ↻. Không có khối → nguyên văn V21."""
    ft = _dossier_header(ctx).get("footer")
    ft = ft if isinstance(ft, dict) else {}
    lt, la = _dz_text(ft.get("left"))
    rt, ra = _dz_text(ft.get("right"))
    left = [FOOT_LEFT]
    if lt is not None:
        dto = ((getattr(ctx, "live_info", None) or {}).get("data_to")) if ctx is not None else None
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", str(dto or ""))
        left = [lt, " · As of ", "%s/%s/%s" % (m.group(3), m.group(2), m.group(1)) if m else can_data("ngày dữ liệu"),
                upd_mark(la)]
    right = [FOOT_RIGHT] if rt is None else [rt, upd_mark(ra)]
    return h("span", None, *left), h("span", None, *right)


def Footer(ctx=None):
    return h("footer", {"borderTop": "1px solid " + C.rule, "padding": "24px 28px", "fontSize": 10, "color": C.inkM,
                        "fontFamily": F_MONO, "letterSpacing": ".1em", "maxWidth": 1480, "margin": "48px auto 0"},
             h("div", {"display": "flex", "justifyContent": "space-between", "flexWrap": "wrap", "gap": 16},
               *_footer_spans(ctx)),
             h("div", {"marginTop": 16, "fontStyle": "italic", "fontSize": 13, "color": C.inkD, "lineHeight": 1.7,
                       "fontFamily": F_SERIF, "letterSpacing": "normal", "maxWidth": 1100},
               h("em", None, FOOT_QUOTE),
               h("span", {"display": "block", "marginTop": 6, "color": C.inkD}, FOOT_ATTR)),
             key="footer")


# ── Addendum tĩnh ngoài React (SRC dòng 7810): section#claims-check-0906 ─────
# rem → px theo cỡ gốc 16px (1.12rem = 17.92 …). <table> không có tbody trong HTML → parser chèn tbody: phát tường
# minh. th: tr đặt text-align:left nên Chrome cho th thừa kế (luật HTML: th chỉ căn giữa khi cha có text-align
# initial) → ghi textAlign 'left' ngay trên th để engine không phụ thuộc luật đó (hình ảnh y hệt).

ADD_H2 = "🔄 CLAIMS STATUS CHECK — 09/06/2026 · data tươi VietcapIQ 05/06 + flow"
ADD_P1 = ("Addendum grounded — KHÔNG sửa 20 claim gốc (baked ≤08/05). Đánh giá falsifyIf theo data mới; 🔶 FLAG = cần "
          "primary source (flow 60d / commodity / BCTC) chưa pull. Nhận định nội bộ, không khuyến nghị mua/bán.")
ADD_P2 = ("📊 Macro: FTSE EM CONFIRMED hiệu lực 21/9/26 (FTSE Russell 7/4) · VN-Index 1.802 (−4,9% tháng, +37,5% năm) · "
          "Q1/26 LN +51% YoY (beat vs ~15% consensus) NHƯNG FY26 guidance thận trọng ~+14% → đừng extrapolate Q1 · "
          "fwd P/E ~13x.")
ADD_SRC = ("Nguồn: VietcapIQ iq-insight (giá/PE/PB/TP/rating 05/06) · nguoiquansat (NN ròng phiên) · FTSE Russell / "
           "CNBC / theinvestor / tradingeconomics (macro). Số liệu thị trường tươi 05/06; mục FLAG chưa đủ data để kết "
           "luận → không bịa.")
_G, _Y, _R, _B = "#3fa66a", "#d4a039", "#e0574a", "#7fb0ff"
ADD_ROWS = (
    ("C01", "Vingroup reflexivity peak", "✅ CONFIRMED-lean", _G,
     "Vietcap: VIC SELL, TP 101,6K vs giá 207K (−51%), PE 137x → luận điểm distribution/peak được data tươi xác nhận mạnh."),
    ("C02", "TCB markup wave 2", "🟢 LIVE", _G,
     "TCB BUY +34% (fresh 11/5), PE 8,6 rẻ → chu kỳ private-bank ascendancy còn nguyên."),
    ("C03", "HPG NN heavy = BULL", "🟢 LIVE", _G,
     "Giá 23.750 GIỮ trên hỗ trợ 23K (chưa thủng = chưa falsify). BUY +49%. Hỗ trợ mong manh, theo dõi."),
    ("C04", "BSR NQ79 markup", "🔶 FLAG", _Y,
     "Cần giá crude + crack spread + flow BSR (chưa pull). Không tự đánh giá → giữ, chờ data."),
    ("C05", "GAS NQ79 cleanest alpha", "🟢 LIVE ⚠", _G,
     "Giá đã lên 85K (từ 75,2K, +13%). TP Vietcap 93,6K THẤP HƠN HSC 120K trong claim → upside thực hẹp hơn claim. "
     "Verify HSC TP còn hiệu lực."),
    ("C06", "ACB best-in-class", "✅ CONFIRMED", _G,
     "PE 8,26/PB 1,36 rẻ, BUY +17%, NN MUA ròng +255 tỷ phiên 05/06 (ngược distribution) → fundamentals độc lập rescue "
     "narrative ĐÚNG."),
    ("C07", "NVL paper accounting = distress", "🟢 LIVE", _G,
     "Cần OCF Q1/26 (flag). Lưu ý Vietcap BUY +48% nhưng rating CŨ 250d — đừng tin sell-side stale; luận điểm distress còn."),
    ("C08", "GEX breakout markup wave 2", "🟡 CHƯA confirm", _Y,
     "Giá 32K — CHƯA chạm trigger 42K, cũng trên stop 24K. PE 28x. Markup wave 2 chưa kích hoạt."),
    ("C09", "DGC 3 BOD khởi tố — Pattern A", "🔴 WATCH", _R,
     "Trùng cờ brain-pass nq68: cần CBTT/cơ quan chính thức xác nhận truy tố hình sự. Vietcap +99% upside nhưng GATED "
     "governance."),
    ("C10", "STB ván cờ Bầu Thụy", "🟡 LIVE", _Y,
     "Vietcap M-PF chỉ +5% upside, PE 28x cao → sell-side trung tính, R/R kém đi vs lúc baked."),
    ("C11", "VPB inside trade flip", "🔶 FLAG", _Y, "Cần flow VPB 60d + insider Phạm Thị Nhung (chưa pull)."),
    ("C12", "SHB ESOP 5 báo cáo nội bộ", "🔶 FLAG", _Y, "Cần flow SHB + xác nhận ESOP insider (chưa pull)."),
    ("C13", "MWG foreign LARGE EXIT", "🟡 LIVE", _Y,
     "Vietcap BUY +29% nhưng rating CŨ 237d (divergence — sell-side chưa update). Luận điểm NN exit cần flow 60d mới."),
    ("C14", "FPT capitulate — NN −173.7M", "🔵 REVIEW / dấu hiệu đáy", _B,
     "Giá 75K = ĐÚNG vùng base 75-80K dự báo. NN phiên 05/06 +126 tỷ (MUA ròng) → có dấu hiệu flip như falsifyIf; có "
     "thể đang tạo đáy. Theo dõi sát flow 60d."),
    ("C15", "KSV rare earth tactical", "🔶 FLAG", _Y, "Cần cổ tức 2026 thực chia + tiến độ Đông Pao (chưa pull)."),
    ("C16", "GMD Gemalink confirm", "🔶 FLAG", _Y, "Cần TEU Q2 vs Q1 + flow GMD (chưa pull)."),
    ("C17", "VJC cycle hàng không", "🟡 LIVE", _Y,
     "Lưu ý: nq68 xếp VJC anti-pattern → thận trọng, đối chiếu cổ tức 30% thực hiện."),
    ("C18", "MSN Pattern B accumulation", "🔵 REVIEW", _B,
     "Claim: NN flip +26,6M (tích lũy, lần đầu 4Y). Phiên 05/06 NN −72 tỷ (1 phiên) → coi chừng flip đảo. FTSE 21/9 "
     "confirmed = bệ đỡ trung hạn."),
    ("C19", "VTP Viettel ESOP signal", "🔶 FLAG", _Y, "Cần insider VTP + nợ VGI (chưa pull)."),
    ("C20", "SSI + HCM dilution warning", "🔶 FLAG", _Y, "Cần EPS/ROE pro-forma sau phát hành (chưa pull)."),
)


_PATTERN_RE = re.compile(r"\bPattern [A-Z]\b(?!\?)")


class _AddendumLive:
    """Mode live của addendum (móc dossier `header.addendum`, thêm 27/09 bởi agent tab audit). Khối vẫn là LƯU TRỮ
    09/06: chữ giữ nguyên văn (cả số kiểu Việt — DESIGN §11.1), chỉ chèn nhãn bậc sau từng số theo phân đoạn dossier
    (ghép lại phải trùng nguyên văn; lệch → nguyên văn + cảnh báo); mã ngoài 30 mã Toàn Vũ → "Pattern X?" (CLAUDE.md §6
    luật 4; không đọc được danh sách → vẫn "?"); hàng có cờ `rescored` → dấu "trạng thái 09/06" dưới trạng thái + dòng
    trỏ bản chấm lại ở tab 09 (trạng thái/bậc đọc động từ dossier `claims20`)."""

    def __init__(self, ctx):
        self.ctx = ctx
        dz = (getattr(ctx, "dossier", None) or {}) if ctx is not None else {}
        hd = dz.get("header") if isinstance(dz.get("header"), dict) else {}
        self.az = hd.get("addendum") if isinstance(hd.get("addendum"), dict) else {}
        self.rows = self.az.get("rows") if isinstance(self.az.get("rows"), dict) else {}
        self.c20 = dz.get("claims20") if isinstance(dz.get("claims20"), dict) else {}
        self.as_of = dz.get("as_of")
        self.tv30 = None
        fn = getattr(getattr(ctx, "data", None), "tv30", None)
        if callable(fn):
            try:
                self.tv30 = set(fn())
            except Exception as exc:  # dữ liệu hỏng không làm hỏng khung trang
                self._warn("addendum: không đọc được 30 mã Toàn Vũ (%s: %s) — mọi Pattern gắn '?'"
                           % (type(exc).__name__, exc))

    def _warn(self, msg):
        if self.ctx is not None:
            self.ctx.warn(msg)

    def _parts(self, segs, text, tk=None):
        """Phân đoạn [{text, tier, asof, src, v21?} | chuỗi] → con có nhãn bậc sau từng số."""
        ok = isinstance(segs, list) and all(isinstance(s, str) or (isinstance(s, dict) and isinstance(s.get("text"), str))
                                            for s in segs)
        if ok and "".join(s if isinstance(s, str) else s["text"] for s in segs) == text:
            out = []
            for s in segs:
                if isinstance(s, str):
                    out.append(s)
                    continue
                out.append(s["text"])
                if s.get("tier") and s.get("src"):
                    out.append(tier(s["tier"], s.get("asof")))
                if s.get("v21"):
                    out.append(v21_mark())
        else:
            if segs is not None:
                self._warn("addendum: phân đoạn dossier lệch nguyên văn V21 — giữ nguyên văn: %s" % text[:48])
            out = [text]
        if tk is not None and (self.tv30 is None or tk not in self.tv30):
            q = []
            for p in out:          # "Pattern X?" một khối không ngắt (cột Claim hẹp, tránh "Pattern" / "A?")
                if not isinstance(p, str):
                    q.append(p)
                    continue
                pos = 0
                for m in _PATTERN_RE.finditer(p):
                    q += [p[pos:m.start()], h("span", {"whiteSpace": "nowrap"}, m.group(0) + "?")]
                    pos = m.end()
                q.append(p[pos:])
            out = [x for x in q if x != ""]
        return out

    def note(self):
        text, asof = _dz_text(self.az.get("note"))
        if text is None:
            return None
        return h("p", {"fontSize": 11.2, "color": "#9aa0a6", "margin": "0 0 4px"}, text, upd_mark(asof),
                 key="addendum:note")

    def p2(self):
        return self._parts(self.az.get("p2"), ADD_P2)

    def row(self, cid, claim, status, check):
        """→ (con cột Claim, con cột Status, con cột Fresh check)."""
        rz = self.rows.get(cid) if isinstance(self.rows.get(cid), dict) else {}
        cl = self._parts(rz.get("claim"), claim, tk=claim.split(" ", 1)[0])
        chk = self._parts(rz.get("check"), check)
        st = [status]
        if rz.get("rescored"):
            st.append(h("div", {"fontFamily": F_MONO, "fontSize": 8, "fontWeight": 400, "color": "#5a564d"},
                        "trạng thái 09/06"))
            it = self.c20.get(cid) if isinstance(self.c20.get(cid), dict) else {}
            new = ([status_pill(it["status"]), tier(it["tier"], it.get("asof")) if it.get("tier") and it.get("src")
                    else None] if it.get("status") else [can_data("chưa đọc được claims20." + cid)])
            chk.append(h("div", {"marginTop": 3, "color": "#9aa0a6"}, "→ đã chấm lại ở tab 09 · CLAIMS C01-C20: ",
                         *new, upd_mark(self.as_of)))
        return cl, st, chk


def Addendum(ctx=None):
    lv = _AddendumLive(ctx) if is_live() else None
    td = {"padding": "5px 7px", "borderBottom": "1px solid #232830"}
    th = {"padding": "5px 7px", "textAlign": "left"}
    rows = [h("tr", {"color": "#9aa0a6", "textAlign": "left"},
              *[h("th", th, t) for t in ("ID", "Claim", "Status 09/06", "Fresh check (grounded)")])]
    for cid, claim, status, color, check in ADD_ROWS:
        cl, st, chk = ([claim], [status], [check]) if lv is None else lv.row(cid, claim, status, check)
        rows.append(h("tr", None,
                      h("td", {**td, "fontWeight": 700, "color": "#cdd2d8"}, cid),
                      h("td", td, *cl),
                      h("td", {**td, "color": color, "fontWeight": 700, "whiteSpace": "nowrap"}, *st),
                      h("td", {**td, "color": "#b9bec4"}, *chk), key=None if lv is None else "addendum:" + cid))
    archive = None
    if is_live():
        archive = h("span", {"fontFamily": F_MONO, "fontSize": 8, "fontWeight": 400, "color": "#5a564d",
                             "marginLeft": 4, "whiteSpace": "nowrap"}, "lưu trữ 09/06")
        archive["_v21"] = True
    return h("section", {"maxWidth": 1120, "margin": "34px auto", "padding": 20, "background": "#0f1216",
                         "border": "1px solid #2a2f37", "borderRadius": 12, "fontFamily": F_SYS, "color": "#e7e3da"},
             h("h2", {"color": "#d4a039", "fontSize": 17.92, "margin": "0 0 6px"}, ADD_H2, archive),
             lv.note() if lv is not None else None,
             h("p", {"fontSize": 12.48, "color": "#9aa0a6", "margin": "0 0 4px"}, ADD_P1),
             h("p", {"fontSize": 11.84, "color": "#d4a039", "margin": "0 0 12px"},
               *([ADD_P2] if lv is None else lv.p2())),
             h("table", {"width": "100%", "borderCollapse": "collapse", "fontSize": 12.32}, h("tbody", None, *rows)),
             h("p", {"fontSize": 11.2, "color": "#6e747b", "marginTop": 12}, ADD_SRC),
             key="addendum")


# ── Toàn trang ─────────────────────────────────────────────────────────────


def build_shell(ctx, tabs):
    """body > div#root > div(MasterPlanV21: nền + 2 radial-gradient) > Header · TabBar · main(slot) · Footer;
    body > section addendum (ngoài React, dưới Footer ở mọi tab). Gốc mang scope ["tab"]."""
    root = h("div", {"background": C.bg, "color": C.ink, "minHeight": "100vh", "fontFamily": F_ROOT,
                     "backgroundImage": ("radial-gradient(at 0%% 0%%, %s30 0%%, transparent 50%%), "
                                         "radial-gradient(at 100%% 100%%, %s30 0%%, transparent 50%%)")
                                        % (C.parch, C.parch)},
             Header(ctx), TabBar(tabs),
             h("main", {"maxWidth": 1480, "margin": "0 auto", "padding": "24px 28px 64px"}, slot("main"), key="main"),
             Footer(ctx), scope=["tab"], key="root")
    return h("body", {"background": "#0a0a0c", "color": "#e8e6e0", "fontFamily": F_BODY, "margin": 0},
             h("div", None, root, key="#root"), Addendum(ctx), key="body")
