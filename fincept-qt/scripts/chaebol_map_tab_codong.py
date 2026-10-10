#!/usr/bin/env python3
"""
chaebol_map_tab_codong — tab "★ 🏛 CẤU TRÚC CỔ ĐÔNG" (CauTrucCoDongTab, SRC 4248–4673 + hằng 3509–3594).

Đặc tả: chaebol_map_spec/page_p3a_codong_tab.md (S1–S11, ma trận 48 mã) + page_p3b_deepdive10.md §0 (điểm nối).
Hợp đồng: DESIGN.md §3–§7, api_python.md. Phần live (số sống, dossier, dữ kiện): chaebol_map_tab_codong_live.

Cây: gốc div → 48 nút giữ chỗ {if codong.tk == MÃ, inc "codong/MÃ"}; mỗi inc chứa mọi Section của một mã (thanh
chọn mã tô tĩnh theo mã đó). Section Deep-dive (41 mã) chứa build_deep10(ctx, tk) của chaebol_map_tab_codong_deep
(nạp mềm; thiếu/lỗi → khối giữ chỗ có thanh 11 sub-tab).

State: codong.tk (48 mã, mặc định VIC) · codong.sub (11 id SUB_TABS_CHAEBOL, mặc định phase_info). Hành vi JSX:
đổi giữa hai mã có Deep-dive giữ sub; chọn mã không có Deep-dive (7 mã NQ79) thì Deep-dive unmount → sub về
phase_info. Lõi (normalize_result) gắn scope MỌI khoá state lên gốc tab nên scope của nút Deep-dive không bao giờ
reset được → nút của 7 mã đó đặt thêm codong.sub = phase_info khi bấm (cùng hiệu ứng quan sát được).

Mode live (05/10/2026): build_codong giao cho chaebol_map_tab_codong_v2.build_codong_v2 (109 mã, codong_v2_spec §8.1);
nhập lỗi → cảnh báo + bản live 48 mã ở dưới. Mode v21 không chạm tới nhánh đó.
"""
from __future__ import annotations

import importlib
import re
import sys

from chaebol_map_dom import C, F_DISPLAY, F_MONO, F_SERIF, h, js_sum, to_fixed, to_locale
from chaebol_map_shell import Card, Section, Stat

PURPLE = "#a78bfa"
K_TK, K_SUB = "codong.tk", "codong.sub"

ALL_TICKERS = ("VIC VHM STB MSN MSR NVL GEX GEE VIX VJC VCI DGC GEL PC1 CTD VRE VPL FPT BID CTG TCB MBB VPB VCB ACB "
               "TPB SHB LPB SSB VIB MWG HPG GAS PLX BSR VNM SAB VTP VGI GVR BVH HDB VPI SSI HCM GMD HAH BCM").split()
CIQ_TICKERS = ("VIC", "VHM", "MSN", "MSR", "NVL")
DETAIL_TICKERS = ("GEX", "GEE", "GEL", "VIX", "VJC", "VCI", "DGC", "CTD")
DEEP_EXTRA = ("VCB", "BID", "CTG", "GAS", "BSR", "PLX")                      # CauTrucCoDongTab.jsx@L4346
FALLBACK_NAME = {"VIC": "Vingroup JSC", "VHM": "Vinhomes JSC", "MSN": "Masan Group Corp.",
                 "MSR": "Masan High-Tech Materials", "NVL": "Novaland Investment Group Corp.", "STB": "Sacombank"}
SUB_TABS_FALLBACK = (("phase_info", "★ 01 Phase Infographic"), ("chart", "02 Chart Infographic"),
                     ("phase", "03 Phase + Status"), ("cluster", "04 Cụm + VWAP"), ("shareholder", "05 Cổ đông BCTN"),
                     ("capitaliq", "★ 06 Capital IQ"), ("flow", "★ 06b FiinTrade Flow"),
                     ("strategic", "07 Bàn cờ lớn"), ("events", "08 Key Events"), ("patterns", "09 Patterns"),
                     ("action", "10 Action Plan"))

# ── Chuỗi nguyên văn JSX ────────────────────────────────────────────────────
T_S1 = "🏛 CẤU TRÚC CỔ ĐÔNG — Per-Ticker Holdings Map"
SUB_S1 = ("Capital IQ S&P Global Ownership Summary (5 endpoints/ticker via Claude-in-Chrome) + V21 chaebol narrative "
          "+ BCTN/báo cáo quản trị cross-validation. Sources: capitaliq.spglobal.com (institutional license) · "
          "cafef.vn news · finance.vietstock.vn tin-tuc-su-kien.")
T_S2 = "🏛 NQ 68/79 Policy Basket — Pillar III ý đồ chủ thể (mở rộng)"
SUB_S2 = ("ChatGPT framework + V21 mapping. NQ 68 (tư nhân động lực, target 20 DN chuỗi giá trị toàn cầu 2030) · "
          "NQ 79 (DNNN dẫn dắt, target 50 DN Top 500 ĐNA + 3 NHTM Top 100 châu Á)")
SUB_S3 = ("Phase Infographic · Chart · Phase+Status · Cụm+VWAP · Cổ đông BCTN · Capital IQ · FiinTrade Flow · "
          "Bàn cờ lớn · Key Events · Patterns · Action Plan")
T_S4 = "📊 Top 10 Holders — Capital IQ S&P Global (Q4/25 verified)"
SUB_S4 = ("Source: capitaliq.spglobal.com → company/OwnershipSummary?Id={CIQ_ID} via Claude-in-Chrome (read-only "
          "post-auth). 5 endpoints: OwnershipSummary · PublicOwnershipDetailed · OwnershipHistory · "
          "publicOwnershipCrossholdings · privateOwnership.")
T_S8 = "📑 Tài liệu công ty (Simplize) — BCTC · BCTN · NQ ĐHĐCĐ · Bản cáo bạch"
SUB_S8 = ("Mining 10/5/2026 từ simplize.vn/co-phieu/{TK}/bao-cao — 4 categories standardized across 48 tickers. "
          "PDF downloadable trực tiếp tại Simplize.")
T_S9 = "📈 Sell-Side Consensus & Báo cáo phân tích broker (Simplize)"
SUB_S9 = "Pillar III ý đồ chủ thể × nghịch đảo logic Toàn Vũ — Mining từ simplize.vn/co-phieu/{TK}/bao-cao 10/5/2026"
T_S10 = "📋 Báo cáo gần nhất — BCTN · BC quản trị · BCTC quý/năm · Insider GD"
SUB_S10 = ("Nguồn: finance.vietstock.vn/{TK}/tai-lieu.htm · mined via browser_batch 10/5/2026 · Tổng hợp filings có "
           "liên quan đến cấu trúc cổ đông + KQKD ngắn hạn")
T_S11 = "📚 Phương pháp luận + Source map"

# ── Style dùng chung (thứ tự khoá = JSX) ────────────────────────────────────
S_TH = {"padding": "8px 10px", "textAlign": "left", "color": C.inkD, "fontWeight": 600, "letterSpacing": ".18em",
        "fontSize": 9}
S_TABLE = {"width": "100%", "borderCollapse": "collapse", "fontFamily": F_MONO, "fontSize": 10.5}
S_TR_HEAD = {"borderBottom": "1px solid " + C.rule}
S_P_NOTE = {"margin": 0, "fontSize": 11.5, "color": C.ink, "lineHeight": 1.7}
S_P_EMPTY = {"margin": 0, "fontSize": 11.5, "color": C.inkD, "fontStyle": "italic"}
S_UL = {"margin": 0, "paddingLeft": 18, "fontSize": 11.5, "lineHeight": 1.85, "color": C.inkD}
S_CALLOUT = {"marginTop": 10, "padding": "8px 12px", "background": C.gold + "10",
             "border": "1px solid " + C.gold + "30", "fontSize": 10.5, "color": C.inkD, "fontFamily": F_SERIF}
S_LINK = {"background": C.ink2 + "20", "color": C.ink2, "border": "1px solid " + C.ink2, "padding": "5px 12px",
          "borderRadius": 2, "cursor": "pointer", "fontFamily": F_MONO, "fontSize": 10, "letterSpacing": ".08em"}


def th(label, align="left", width=None):
    return h("th", {**S_TH, "textAlign": align, "width": width}, label)


def tr_row(i, *cells, zebra=True):
    bg = ("transparent" if i % 2 == 0 else C.parch + "30") if zebra else None
    return h("tr", {"borderBottom": "1px solid " + C.rule + "80", "background": bg}, *cells)


def chip(text, color, pad="2px 7px"):
    return h("span", {"padding": pad, "background": color + "20", "color": color, "fontSize": 9,
                      "letterSpacing": ".1em", "fontWeight": 700, "borderRadius": 2}, text)


def label9(text, color, **extra):
    """Nhãn mono 9px ls .2em (STORY/COMPOSITION/…); extra theo đúng thứ tự khoá JSX."""
    return h("div", {"fontSize": 9, "letterSpacing": ".2em", "color": color, "fontFamily": F_MONO, **extra}, text)


# ── Luật trang (port nguyên văn) ────────────────────────────────────────────
_RE_INSIDER = re.compile(r"chairman|chief executive|ceo|director|chairwoman|management board", re.I)
_RE_CORP = re.compile(r"jsc|corp|company|ltd|pte|inc|group|holdings|investment|capital|asset|fund|mgmt|management|"
                      r"partners|bank|securities", re.I)
_RE_FOREIGN = re.compile(r"dragon|vaneck|van eck|boston|norges|hsbc|jp morgan|eaton|robeco|capital group|"
                         r"investment management", re.I)
_RE_STRAT = re.compile(r"sk inv|sk investment", re.I)
_RE_VEHICLE = re.compile(r"vinspeed|vinenergo|vinpearl|vmi|vingroup|novagroup|diamond|gelex|sovico", re.I)
_RE_PERSON = re.compile(r"pham|nguyen|tran|le|hoang|vu|do|bui|cao|hà|đinh", re.I)


def tag_holder(name):
    """tagHolder (SRC 3538–3550): (tag, màu). Giữ cả phân loại sai của trang (Vinspeed → OTHER…)."""
    if not name:
        return "unknown", "#5a564d"
    if _RE_INSIDER.search(name):
        return "INSIDER", "#caa75c"
    if _RE_CORP.search(name):
        if _RE_FOREIGN.search(name):
            return "INST FOREIGN", "#3d7a4e"
        if _RE_STRAT.search(name):
            return "STRATEGIC", "#5b8db8"
        if _RE_VEHICLE.search(name):
            return "VEHICLE", "#a78bfa"
        return "INST DOMESTIC", "#5b8db8"
    if _RE_PERSON.search(name.lower()):
        return "INDIVIDUAL", "#caa75c"
    return "OTHER", "#5a564d"


def rec_color(r):
    up = (r or "").upper()
    if "MUA" in up or "OUTPERFORM" in up or "TÍCH CỰC" in up:
        return C.forest
    if "BÁN" in up or "KÉM" in up:
        return C.vermillion
    if "NẮM GIỮ" in up or "TRUNG LẬP" in up or "THEO DÕI" in up:
        return C.ochre
    return C.inkD


CAT_COLOR = {"INSIDER": C.vermillion, "AGM": C.gold, "BCTC": C.ink2, "KQKD": C.forest, "GOVERNANCE": PURPLE}


def basket_colors(basket):
    """(nền +25, viền, chữ) của ô BASKET."""
    col = {"NQ68": C.gold, "NQ79": C.ink2, "DISTRESS": C.vermillion}.get(basket, C.inkM)
    return col + "25", col, {"NQ68": C.gold, "NQ79": C.ink2, "DISTRESS": C.vermillion}.get(basket, C.ink)


def has_deep(tk, policy):
    p = policy.get(tk)
    return bool(p) and (p.get("basket") in ("NQ68", "DISTRESS") or tk in DEEP_EXTRA)


def dmy_key(d):
    """new Date(y, m-1, d) từ 'dd/mm/yyyy' → khoá sắp (y, m, d)."""
    try:
        dd, mm, yy = (int(x) for x in str(d).split("/"))
        return (yy, mm, dd)
    except ValueError:
        return (0, 0, 0)


# ── Dữ liệu V21 ─────────────────────────────────────────────────────────────


class V21:
    """Hằng V21 dùng trong tab (từ ctx.v21; thiếu → dự phòng chép tay cho danh sách mã/sub-tab)."""

    def __init__(self, v21):
        v = v21 or {}
        self.tickers = list(v.get("CauTrucCoDongTab.allTickers") or ALL_TICKERS)
        self.ciq = tuple(v.get("CauTrucCoDongTab.ciqTickers") or CIQ_TICKERS)
        self.detail_tk = tuple(v.get("CauTrucCoDongTab.detailTickers") or DETAIL_TICKERS)
        subs = v.get("SUB_TABS_CHAEBOL") or [{"id": i, "label": l} for i, l in SUB_TABS_FALLBACK]
        self.subs = [(str(s["id"]), str(s["label"])) for s in subs]
        self.detail = v.get("TICKER_DETAIL") or {}
        self.holders = v.get("HOLDERS_CIQ") or {}
        self.policy = v.get("POLICY_MAP") or {}
        self.docs = v.get("SIMPLIZE_DOCS") or {}
        self.reports = v.get("SIMPLIZE_REPORTS") or {}
        self.cons = v.get("SIMPLIZE_CONSENSUS") or {}
        self.filings = v.get("REPORTS_INDEX") or {}


# ── S1: chọn mã + card đầu mã ───────────────────────────────────────────────


def ticker_bar(D, active):
    no_deep = {tk for tk in D.tickers if not has_deep(tk, D.policy)}
    btns = []
    for tk in D.tickers:
        on, ciq = tk == active, tk in D.ciq
        st = {"background": C.gold if on else "transparent",
              "color": C.bg if on else (C.ink if ciq else C.inkD),
              "border": "1px solid " + (C.gold if on else (C.rule if ciq else C.parch)),
              "padding": "5px 10px", "borderRadius": 2, "cursor": "pointer", "fontFamily": F_MONO, "fontSize": 10.5,
              "fontWeight": 700 if on else 500, "letterSpacing": ".08em"}
        act = {K_TK: tk, K_SUB: "phase_info"} if tk in no_deep else {K_TK: tk}
        btns.append(h("button", st, tk + (" ★" if ciq else ""), on={"set": act}, key="codong.btn." + tk))
    return h("div", {"display": "flex", "gap": 6, "flexWrap": "wrap", "marginBottom": 14, "padding": "10px 12px",
                     "background": C.parch, "borderRadius": 3},
             h("span", {"fontSize": 9, "letterSpacing": ".2em", "color": C.inkM, "fontFamily": F_MONO, "marginRight": 8,
                        "alignSelf": "center"}, "SELECT TICKER:"),
             *btns,
             h("span", {"marginLeft": "auto", "fontSize": 9, "color": C.inkM, "alignSelf": "center",
                        "fontFamily": F_MONO}, "★ = Capital IQ data available"), key="codong.bar")


def head_card(D, tk, L):
    det = D.detail.get(tk)
    holders = D.holders.get(tk) or []
    total = js_sum((x.get("shares_M") or 0) for x in holders)
    name = (det or {}).get("name") or FALLBACK_NAME.get(tk, tk)
    left = [h("div", {"fontSize": 9, "letterSpacing": ".2em", "color": C.inkM, "fontFamily": F_MONO,
                      "marginBottom": 4}, tk),
            h("h3", {"margin": 0, "fontSize": 18, "fontFamily": F_DISPLAY, "color": C.ink, "fontWeight": 600,
                     "fontStyle": "italic"}, L.name(name) if L else name)]
    if det and det.get("chaebol"):
        left.append(h("div", {"fontSize": 11, "color": C.gold, "fontFamily": F_MONO, "letterSpacing": ".1em",
                              "marginTop": 4}, "NHÓM: ", L.stance(det["chaebol"]) if L else det["chaebol"]))
    sector = L.sector(det) if L else ((det or {}).get("sector") or None)
    if sector:
        left.append(h("div", {"fontSize": 11, "color": C.inkD, "marginTop": 2}, "SECTOR: ", sector))
    if L:
        left.append(L.leader_line())
    stats = L.head_stats(det, total) if L else _v21_head_stats(tk, det, total)
    body = [h("div", {"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start",
                      "flexWrap": "wrap", "gap": 14, "marginBottom": 14},
              h("div", None, *left), h("div", {"display": "flex", "gap": 14}, *stats))]
    if L:
        body.append(L.lens_block())
        body.append(L.vciq_link())
    return Card(*body, key="codong.card")


def _v21_head_stats(tk, det, total):
    out = []
    if det and det.get("currentPrice"):
        out.append(Stat("GIÁ", to_fixed(det["currentPrice"] / 1000, 1) + "K", sub="29/4/2026", color=C.gold))
    if det and det.get("cafefPx"):
        out.append(Stat("CAFEF UPDATE", to_fixed(det["cafefPx"] / 1000, 1) + "K", sub="04-08/05/2026", color=C.ink2))
    if total > 0:
        den = (det or {}).get("sharesOut") or {"VIC": 7500, "VHM": 4107, "MSN": 1438}.get(tk, 1000)
        out.append(Stat("TOP 10 HOLDERS", to_fixed(total, 0) + "M", sub="~" + to_fixed(total / den * 100, 1) + "% est",
                        color=C.forest))
    return out


def s1(D, tk, L):
    return Section(T_S1, ticker_bar(D, tk), head_card(D, tk, L), accent=C.gold, sub=L.s1_sub() if L else SUB_S1,
                   key="codong.s1")


# ── S2: Policy basket ───────────────────────────────────────────────────────

PHILO = ("★ Investment philosophy (nghịch đảo Toàn Vũ + ChatGPT framework):",
         " KHÔNG mua vì khẩu hiệu NQ 68/NQ 79. Chỉ mua khi DN ", "vừa có vai trò chính sách THẬT", " (basket above), ",
         "vừa có ROE/FCF/đòn bẩy kiểm soát được", " (cross-check Pillar I cổ đông + Pillar IV flow), và ",
         "giá thị trường còn upside ≥30%",
         " so với giá trị hợp lý đã chiết khấu rủi ro (cross-check sell-side avg TP).")


def s2(D, tk, L):
    p = D.policy.get(tk)
    if not p:
        body = Card(h("p", S_P_EMPTY, "Chưa map policy basket cho ", tk, " — cần synthesize từ ChatGPT framework."))
        return Section(T_S2, body, accent=C.gold, sub=SUB_S2, key="codong.s2")
    bg, bd, fg = basket_colors(p["basket"])
    col = lambda lbl, color, text: h("div", None, label9(lbl, color, marginBottom=6),  # noqa: E731
                                     h("p", {"margin": 0, "fontSize": 11, "color": C.ink, "lineHeight": 1.65}, text))
    grid1 = h("div", {"display": "grid", "gridTemplateColumns": "auto 1fr auto", "gap": 14, "alignItems": "center",
                      "marginBottom": 12},
              h("div", {"padding": "8px 14px", "background": bg, "border": "2px solid " + bd, "borderRadius": 4},
                h("div", {"fontSize": 9, "letterSpacing": ".3em", "color": C.inkM, "fontFamily": F_MONO,
                          "marginBottom": 2}, "BASKET"),
                h("div", {"fontSize": 14, "fontWeight": 800, "color": fg, "fontFamily": F_MONO}, p["basket"])),
              h("div", None, label9("CLUSTER", C.inkM, marginBottom=4),
                h("div", {"fontSize": 13, "fontWeight": 600, "color": C.ink}, p["cluster"], L.v21() if L else None)),
              h("div", {"padding": "4px 10px", "background": C.gold + "15", "borderRadius": 2},
                h("span", {"fontSize": 10, "color": C.gold, "fontWeight": 700, "letterSpacing": ".1em"}, p["tag"])))
    grid2 = h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr", "gap": 14},
              col("★ COMPOSITION", C.inkM, L.composition(p["shareholder"]) if L else p["shareholder"]),
              col("★ POLICY DRIVER", C.forest, L.driver(p["driver"]) if L else p["driver"]),
              col("⚠ RISK / NOTE", C.vermillion, L.risk(p["risk"]) if L else p["risk"]))
    ph = PHILO
    philo = h("div", {"marginTop": 14, "padding": "10px 14px", "background": C.parch, "border": "1px solid " + C.rule,
                      "borderRadius": 3, "fontSize": 10.5, "color": C.inkD, "lineHeight": 1.7},
              h("strong", {"color": C.gold}, ph[0]), ph[1], h("strong", {"color": C.ink}, ph[2]), ph[3],
              h("strong", {"color": C.ink}, ph[4]), ph[5], h("strong", {"color": C.ink}, ph[6]), ph[7],
              L.v21() if L else None)
    extra = L.policy_block(p) if L else None
    return Section(T_S2, Card(grid1, grid2, philo, extra), accent=C.gold, sub=SUB_S2, key="codong.s2")


# ── S3: Deep-dive (điểm nối với chaebol_map_tab_codong_deep) ────────────────


def deep_bar(D):
    on = {"background": C.gold, "color": C.bg, "border": "1px solid " + C.gold, "fontWeight": 700}
    return h("div", {"display": "flex", "gap": 4, "flexWrap": "wrap", "marginBottom": 16, "padding": "8px 10px",
                     "background": C.parch, "borderRadius": 3, "borderBottom": "1px solid " + C.gold + "40"},
             *[h("button", {"background": "transparent", "color": C.inkD, "border": "1px solid " + C.rule,
                            "padding": "5px 10px", "borderRadius": 2, "cursor": "pointer", "fontFamily": F_MONO,
                            "fontSize": 9.5, "fontWeight": 500, "letterSpacing": ".08em"}, lbl,
                 on={"set": {K_SUB: sid}}, var=[{"if": {K_SUB: sid}, "s": on}], key="codong.sub." + sid)
               for sid, lbl in D.subs])


def deep_placeholder(D, tk, reason):
    msg = "[chưa dựng] Deep-dive 11 sub-tab của " + tk + " — " + reason
    return h("div", None, deep_bar(D),
             Card(h("div", {"fontSize": 12, "color": C.inkD, "fontFamily": F_MONO, "lineHeight": 1.6}, msg)),
             scope=[K_SUB], key="codong.deep.placeholder")


def load_deep(ctx):
    """→ (build_deep10 | None, lý do). Nạp mềm module của agent Deep-dive."""
    try:
        mod = importlib.import_module("chaebol_map_tab_codong_deep")
    except ModuleNotFoundError as exc:
        if exc.name != "chaebol_map_tab_codong_deep":
            ctx.warn("chaebol_map_tab_codong_deep nhập lỗi: %s" % exc)
            return None, "module Deep-dive nhập lỗi (%s)" % exc
        return None, "chờ chaebol_map_tab_codong_deep.build_deep10"
    except Exception as exc:  # module hỏng không được làm hỏng tab
        ctx.warn("chaebol_map_tab_codong_deep nhập lỗi: %s: %s" % (type(exc).__name__, exc))
        return None, "module Deep-dive nhập lỗi (%s)" % type(exc).__name__
    fn = getattr(mod, "build_deep10", None)
    if not callable(fn):
        return None, "module Deep-dive thiếu hàm build_deep10"
    return fn, None


def deep_node(ctx, D, tk, fn, reason, inc):
    """Nút thân Section Deep-dive (+ gộp inc nếu build_deep10 trả {'root', 'inc'})."""
    if fn is not None:
        try:
            res = fn(ctx, tk)
            if isinstance(res, dict) and "root" in res and "t" not in res:
                for k, v in (res.get("inc") or {}).items():
                    inc.setdefault(k, v)
                res = res["root"]
            if isinstance(res, dict) and "t" in res:
                return res
            reason = "build_deep10 trả sai dạng (%s)" % type(res).__name__
        except Exception as exc:
            reason = "build_deep10 lỗi: %s: %s" % (type(exc).__name__, exc)
            sys.stderr.write("[codong] %s\n" % reason)
        ctx.warn("Deep-dive %s → giữ chỗ (%s)" % (tk, reason))
    return deep_placeholder(D, tk, reason)


def s3(ctx, D, tk, fn, reason, inc):
    node = deep_node(ctx, D, tk, fn, reason, inc)
    if node.get("t") == "section":                    # agent Deep-dive tự dựng cả Section
        return node
    return Section("🔬 DEEP-DIVE 10 SUB-TABS — " + tk + " (equivalent v22 MSN tab structure)", node, accent=C.gold,
                   sub=SUB_S3, key="codong.s3")


# ── S4: Top 10 Holders CapIQ ────────────────────────────────────────────────

READING_S4 = (" Δ Q on Q (Q3/25 → Q4/25). Positive = increased position; negative = trimmed. Insider/Vehicle increases "
              "trong khi Foreign giảm = chuyển giao chủ thể nội bộ pattern (Toàn Vũ thesis).")


def s4(D, tk, L):
    if L:
        return L.holders_section()
    holders = D.holders.get(tk) or []
    if tk not in D.ciq or not holders:
        return None
    rows = []
    for i, x in enumerate(holders):
        tag, tcol = tag_holder(x.get("name"))
        sh, chg = x.get("shares_M") or 0, x.get("chg_M") or 0
        ccol = C.forest if chg > 0 else (C.vermillion if chg < 0 else C.inkD)
        chg_txt = (("+" if chg > 0 else "") + to_locale(chg, "en-US", max_frac=2)) if chg else "—"
        rows.append(tr_row(i,
                           h("td", {"padding": "9px 10px", "color": C.inkD, "fontWeight": 600}, i + 1),
                           h("td", {"padding": "9px 10px", "color": C.ink, "fontWeight": 600, "fontFamily": F_SERIF,
                                    "fontSize": 11.5}, x.get("name")),
                           h("td", {"padding": "9px 10px", "textAlign": "right", "color": C.gold, "fontWeight": 700},
                             to_locale(sh, "en-US", max_frac=2)),
                           h("td", {"padding": "9px 10px", "textAlign": "right", "color": ccol, "fontWeight": 600},
                             chg_txt),
                           h("td", {"padding": "9px 10px"}, chip(tag, tcol, "2px 8px"))))
    table = h("table", S_TABLE,
              h("thead", None, h("tr", S_TR_HEAD, th("#"), th("HOLDER NAME"), th("SHARES (M)", "right"),
                                 th("Δ Q on Q (M)", "right"), th("TYPE"))),
              h("tbody", None, *rows))
    call = h("div", S_CALLOUT, h("strong", {"color": C.gold}, "★ Reading:"), READING_S4)
    return Section(T_S4, Card(table, call), accent=C.forest, sub=SUB_S4, key="codong.s4")


# ── S5 / S6: ghi chú MSR, STB ───────────────────────────────────────────────


def s5(tk, L):
    if tk != "MSR":
        return None
    body = L.msr_note() if L else [
        "MSR là UPCOM stock với ", h("strong", {"color": C.gold}, "MSN parent ~94.89% (~1,068M cp)"),
        ". Capital IQ chỉ tracking 2 institutional positions disclosed (VinaCapital + Việt Fund). Free float effective "
        "~5%. Insider/cổ đông MSN sắp được mua MSR chiết khấu 15% (5.45M+5.45M cp đăng ký 6-12/5/2026 — coupling "
        "MSN-MSR)."]
    return Section("⚠ MSR Holdings Note", Card(h("p", S_P_NOTE, *body)), accent=C.ochre, key="codong.s5")


def s6(tk, L):
    if tk != "STB":
        return None
    body = L.stb_note() if L else [
        "STB Capital IQ ownership data ", h("strong", {"color": C.vermillion}, "N/A"),
        " (không trong CAPITALIQ_EVENTS dump). Lý do: free float ~65% concentrated trong nhóm ",
        h("strong", {"color": C.gold}, "Bầu Thụy/Thaiholdings (>30%)"),
        " + VAMC + cổ đông cũ Trầm Bê — proxy chỉ available qua FiinTrade flow data. ",
        h("strong", None, "Pillar IV flow signal Q1/26 + 5-day 4-8/5"),
        ": Tổ chức nội ACCUMULATE +6.69M cp tuần — TÍCH LŨY MẠNH NHẤT trong 6 mã (proxy Bầu Thụy)."]
    return Section("⚠ STB Capital IQ data N/A", Card(h("p", S_P_NOTE, *body)), accent=C.vermillion, key="codong.s6")


# ── S7 / S7b: Narrative + Subsidiaries ──────────────────────────────────────


def s7(D, tk, L):
    det = D.detail.get(tk)
    if tk not in D.detail_tk or not det:
        return []
    ptxt = lambda color, text: h("p", {"margin": 0, "fontSize": 11.5, "color": color, "lineHeight": 1.85},  # noqa
                                 *(L.stance(text) if L else [text]))
    kids = [label9("★ STORY", C.gold, marginBottom=8), ptxt(C.ink, det.get("story"))]
    if det.get("flowReading"):
        kids += [label9("★ FLOW READING (Pillar IV)", C.forest, marginTop=14, marginBottom=8),
                 ptxt(C.inkD, det["flowReading"])]
    if det.get("risk"):
        kids += [label9("⚠ RISK", C.vermillion, marginTop=14, marginBottom=8), ptxt(C.inkD, det["risk"])]
    if L:
        kids += L.narrative_updates()
    title = "📚 Chaebol Narrative — " + (det.get("chaebol") or tk)
    out = [Section(L.legal_title(title) if L else title, Card(*kids), accent=C.gold, key="codong.s7")]
    if det.get("holdings"):
        out.append(L.subsidiaries(det["holdings"]) if L else _v21_subsidiaries(det["holdings"]))
    return out


def v21_sub_rows(holdings):
    return [h("tr", {"borderBottom": "1px solid " + C.rule + "80"},
              h("td", {"padding": "10px 10px", "color": C.ink, "fontWeight": 600}, x.get("name")),
              h("td", {"padding": "10px 10px", "color": C.gold, "fontFamily": F_MONO, "fontSize": 11}, x.get("stake")),
              h("td", {"padding": "10px 10px", "color": C.inkD, "fontStyle": "italic"}, x.get("value")))
            for x in holdings]


def _v21_subsidiaries(holdings):
    return sub_table(("SUBSIDIARY / HOLDING", "STAKE", "VALUE"), v21_sub_rows(holdings))


def sub_table(heads, rows, extra=None):
    ths = [h("th", {**S_TH, "fontFamily": F_MONO}, x) for x in heads]
    table = h("table", {"width": "100%", "borderCollapse": "collapse", "fontFamily": F_SERIF, "fontSize": 11.5},
              h("thead", None, h("tr", S_TR_HEAD, *ths)), h("tbody", None, *rows))
    return Section("🏢 Subsidiaries / Cross-Holdings", Card(table, extra), accent=C.ink2, key="codong.s7b")


# ── S8: Tài liệu công ty ────────────────────────────────────────────────────

READING_S8 = (" Truy cập BCTN từng năm để compare lượng cổ đông Δ kỳ này vs kỳ trước — datapoint then chốt "
              "VN-specific. Cụm khối lượng × cổ đông giảm = đổi chủ thể (chủ thể chiến lược thay vì retail). "
              "NQ ĐHĐCĐ cung cấp mục đích kéo (Pillar III): IPO/M&A/đấu giá → mục đích LỚN HƠN chi phí kéo. "
              "PDF link trực tiếp tại simplize.vn/co-phieu/")


def doc_label(text, color, first, tag=None):
    extra = {"marginBottom": 8} if first else {"marginTop": 14, "marginBottom": 8}
    return label9([text, tag], color, **extra, fontWeight=700)


def doc_cards(lists, tag=None):
    """lists = {BCTC, BACH, BCTN, NQ: [li con…]} → lưới 2 Card (thứ tự JSX); tag = nhãn bậc sau mỗi nhãn (live)."""
    ul = lambda items: h("ul", S_UL, *[h("li", None, x) for x in items])  # noqa: E731
    return h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 14},
             Card(doc_label("📊 BÁO CÁO TÀI CHÍNH (BCTC)", C.ink2, True, tag), ul(lists["BCTC"]),
                  doc_label("📜 BẢN CÁO BẠCH", PURPLE, False, tag), ul(lists["BACH"])),
             Card(doc_label("📕 BÁO CÁO THƯỜNG NIÊN (BCTN)", C.gold, True, tag), ul(lists["BCTN"]),
                  doc_label("📋 NGHỊ QUYẾT ĐHĐCĐ", C.forest, False, tag), ul(lists["NQ"])))


def s8(D, tk, L):
    docs = D.docs.get(tk)
    if L:
        body, title, sub = L.docs_body(docs), L.s8_title(), L.s8_sub()
    else:
        title, sub = T_S8, SUB_S8
        body = doc_cards({k: docs.get(k) or [] for k in ("BCTC", "BACH", "BCTN", "NQ")}) if docs else \
            Card(h("p", S_P_EMPTY, "Chưa mining cho ", tk))
    call = h("div", {"marginTop": 12, "padding": "10px 14px", "background": C.gold + "10",
                     "border": "1px solid " + C.gold + "30", "borderRadius": 3, "fontSize": 10.5, "color": C.inkD},
             h("strong", {"color": C.gold}, "★ Pillar I Reading (Toàn Vũ — điểm đảo chiều cổ đông):"),
             READING_S8, h("span", None, tk), "/bao-cao.", L.v21() if L else None)
    return Section(title, body, call, accent=C.gold, sub=sub, key="codong.s8")


# ── S9: Sell-side ───────────────────────────────────────────────────────────

READING_S9 = ("★ Pillar III Reading (Toàn Vũ nghịch đảo logic):", " Nếu sell-side ", "đồng loạt MUA",
              " + giá đang dựng → đối chiếu với Pillar IV flow: ",
              "nếu Cá nhân net BUY mạnh trong khi NN/Tổ chức net SELL → Pattern A đỉnh CONFIRMED",
              " (smart money distribute, retail catch knife). Ngược lại nếu sell-side trung lập + flow Pillar IV "
              "bullish → Accumulation pattern. Cross-validate với Capital IQ Top Holders Δ Q on Q.")
S9_HEAD = (("NGÀY", "left", "10%"), ("TIÊU ĐỀ BÁO CÁO", "left", None), ("BROKER", "left", "10%"),
           ("KHUYẾN NGHỊ", "left", "12%"), ("TARGET PRICE (VND)", "right", "12%"))


def s9_row(i, d, t, b, r, rcol, tp_nodes, tp_col, dim=False):
    return tr_row(i,
                  h("td", {"padding": "9px 10px", "color": C.inkD}, d),
                  h("td", {"padding": "9px 10px", "color": C.inkD if dim else C.ink, "fontFamily": F_SERIF,
                           "fontSize": 11.5}, t),
                  h("td", {"padding": "9px 10px", "color": C.ink2, "fontWeight": 700}, b),
                  h("td", {"padding": "9px 10px"}, chip(r, rcol)),
                  h("td", {"padding": "9px 10px", "textAlign": "right", "color": tp_col, "fontWeight": 700,
                           "fontSize": 11}, tp_nodes))


def s9_table(rows, L=None):
    table = h("table", S_TABLE, h("thead", None, h("tr", S_TR_HEAD, *[th(a, b, c) for a, b, c in S9_HEAD])),
              h("tbody", None, *rows))
    r = READING_S9
    call = h("div", {"marginTop": 10, "padding": "8px 12px", "background": C.ink2 + "10",
                     "border": "1px solid " + C.ink2 + "40", "fontSize": 10.5, "color": C.inkD, "fontFamily": F_SERIF},
             h("strong", {"color": C.gold}, r[0]), r[1], h("strong", {"color": C.forest}, r[2]), r[3],
             h("strong", {"color": C.vermillion}, r[4]), r[5], L.v21() if L else None)
    return Card(table, call)


def v21_report_rows(reps, start=0, dim=False):
    rows = []
    for i, r in enumerate(reps):
        tp = r.get("tp")
        rows.append(s9_row(start + i, r.get("d"), r.get("t"), r.get("b"), r.get("r"), rec_color(r.get("r")),
                           to_locale(tp, "en-US") if tp else "—", C.gold if tp else C.inkM, dim))
    return rows


def s9(D, tk, L):
    reps = D.reports.get(tk)
    has = bool(reps) and reps[0].get("b") != "-"
    if L:
        return Section(L.s9_title(), *L.sellside(reps if has else []), accent=C.ink2, sub=L.s9_sub(), key="codong.s9")
    if not has:
        body = Card(h("p", S_P_EMPTY, "⚠ Chưa có broker reports trên Simplize cho ", h("span", None, tk),
                      " — chỉ có BCTN/NQ ĐHĐCĐ. Có thể do mã ít được sell-side cover (mid-cap retail-driven) hoặc "
                      "broker reports lưu trên các nền tảng khác (HSC FiscVN, BSC danh mục, SSI bao-cao-cong-ty)."))
        return Section(T_S9, body, accent=C.ink2, sub=SUB_S9, key="codong.s9")
    cons = D.cons.get(tk) or {}
    dom_ = cons.get("dominant") or ""
    ban = cons.get("ban") or 0
    grid = h("div", {"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)", "gap": 12, "marginBottom": 14},
             Stat("BÁO CÁO", cons.get("count") or 0, sub="reports tracked", color=C.gold),
             Stat("MUA / KHẢ QUAN", cons.get("mua") or 0, sub="bullish", color=C.forest),
             Stat("⚠ BÁN", ban, sub="bearish (rare)", color=C.vermillion if ban > 0 else C.inkD),
             Stat("AVG TARGET PRICE", (to_fixed(cons["avgTp"] / 1000, 1) + "K") if cons.get("avgTp") else "N/A",
                  sub="signal: " + dom_, color=C.gold if "BULL" in dom_ else C.ink2))
    return Section(T_S9, grid, s9_table(v21_report_rows(reps)), accent=C.ink2, sub=SUB_S9, key="codong.s9")


# ── S10: Báo cáo gần nhất ───────────────────────────────────────────────────

READING_S10 = (("★ Reading:", C.gold, True), (" Filings phân loại theo: ", None, False),
               ("INSIDER", C.vermillion, False),
               (" (giao dịch CP người nội bộ/liên quan) · ", None, False), ("AGM", C.gold, False),
               (" (ĐHĐCĐ thường niên/bất thường) · ", None, False), ("BCTC", C.ink2, False),
               (" (BCTC quý/HN/mẹ) · ", None, False), ("KQKD", C.forest, False),
               (" (báo cáo cập nhật KQKD broker) · ", None, False), ("GOVERNANCE", PURPLE, False),
               (" (NQ HĐQT vốn điều lệ + tăng vốn). Cross-reference với Pillar IV flow data + Capital IQ holders để "
                "map ý đồ chủ thể.", None, False))


def s10_row(i, d, cat, title, dim=False):
    col = CAT_COLOR.get(cat, C.inkD)
    return tr_row(i, h("td", {"padding": "9px 10px", "color": C.inkD, "whiteSpace": "nowrap"}, d),
                  h("td", {"padding": "9px 10px"}, chip(cat, col)),
                  h("td", {"padding": "9px 10px", "color": C.inkD if dim else C.ink, "fontFamily": F_SERIF,
                           "fontSize": 11.5}, title))


def v21_filing_rows(D, tk, start=0, dim=False):
    rows = sorted(D.filings.get(tk) or [], key=lambda r: dmy_key(r.get("d")), reverse=True)   # sort ổn định, giảm dần
    return [s10_row(start + i, r.get("d"), r.get("cat"), r.get("t"), dim) for i, r in enumerate(rows)]


def s10_card(rows, L=None):
    table = h("table", S_TABLE,
              h("thead", None, h("tr", S_TR_HEAD, th("NGÀY", "left", "12%"), th("LOẠI", "left", "13%"), th("TIÊU ĐỀ"))),
              h("tbody", None, *rows))
    call = h("div", S_CALLOUT, *[h("strong" if b else "span", {"color": c}, t) if c else t for t, c, b in READING_S10],
             L.v21() if L else None)
    return Card(table, call)


def s10(D, tk, L):
    if L:
        return Section(T_S10, L.filings_card(), accent=C.gold, sub=L.s10_sub(), key="codong.s10")
    if not D.filings.get(tk):
        body = Card(h("p", S_P_EMPTY, "⚠ Chưa có filings index cho ", tk,
                      " — cần chạy browser_batch crawl finance.vietstock.vn/", tk, "/tai-lieu.htm."))
    else:
        body = s10_card(v21_filing_rows(D, tk))
    return Section(T_S10, body, accent=C.gold, sub=SUB_S10, key="codong.s10")


# ── S11: Phương pháp luận + Source map ──────────────────────────────────────

METHOD = (("Toàn Vũ Pillar I — điểm đảo chiều cổ đông", ": BCTN số lượng cổ đông Δ kỳ này vs kỳ trước. Critical "
           "pattern: cổ đông GIẢM mạnh + giá tăng = đổi chủ thể (smart money buy from retail)."),
          ("Capital IQ Top Holders",
           ": Top 10 institutional + insider positions với Δ Q on Q. Cross-validate Pillar I."),
          ("BCTN annual + báo cáo quản trị quý-năm", ": cấu trúc cổ đông disclosed periodically (ngày kết thúc "
           "quý/năm). Nguồn: cafef.vn news + finance.vietstock.vn tin-tuc-su-kien.htm + IR pages từng DN."),
          ("FiinTrade Pillar IV flow", ": KL khớp ròng 4 channels — proxy thực-thời tốt hơn BCTN cho daily/weekly "
           "horizon (cutover ≤8/5 historical)."),
          ("Cross-holdings + private/family-office", ' (CapIQ endpoints): publicOwnershipCrossholdings + '
           'privateOwnership giúp map "bàn cờ lớn" tỷ phú.'))
SOURCES_V21 = (("★ Capital IQ S&P", "✓ ACTIVE", C.forest,
                "Claude-in-Chrome MCP read-only post-auth (Okta SSO managed by user)"),
               ("CafeF tin-DN events", "✓ ACTIVE", C.forest,
                "cafef.vn/du-lieu/tin-doanh-nghiep/{TK}/event.chn — news + filings cross-ref"),
               ("Vietstock tin-tuc", "✓ ACTIVE", C.forest, "finance.vietstock.vn/{TK}/tin-tuc-su-kien.htm"),
               ("Vietstock co-dong-lon", "⚠ PAID", C.vermillion,
                'finance.vietstock.vn/{TK}/co-dong-lon.htm — returns "***" cho non-subscriber'),
               ("CafeF Co-dong", "✗ 404", C.vermillion,
                "cafef.vn/Co-dong/{TK}/{TK}.chn — URL pattern thay đổi 2025+, currently broken"))


def source_table(rows):
    sth = lambda x: h("th", {"padding": "6px 8px", "textAlign": "left", "color": C.inkD, "fontWeight": 600,  # noqa
                             "fontSize": 9}, x)
    body = [h("tr", {"borderBottom": "1px solid " + C.rule + "80"},
              h("td", {"padding": "8px", "color": C.ink}, a),
              h("td", {"padding": "8px", "color": col, "fontWeight": 700}, b),
              h("td", {"padding": "8px", "color": C.inkD, "fontSize": 10}, m)) for a, b, col, m in rows]
    return h("table", {"width": "100%", "borderCollapse": "collapse", "fontSize": 10.5, "fontFamily": F_MONO},
             h("thead", None, h("tr", S_TR_HEAD, sth("SOURCE"), sth("STATUS"), sth("METHOD"))), h("tbody", None, *body))


def s11(tk, L):
    lis = [h("li", None, h("strong", {"color": C.ink}, a), b, L.v21() if (L and i == 4) else None)
           for i, (a, b) in enumerate(METHOD)]
    left = Card(label9("METHODOLOGY (cùng các tab khác)", C.gold, marginBottom=8), h("ul", S_UL, *lis))
    src_label, rows = L.sources() if L else ("SOURCE MAP (3 nguồn)", SOURCES_V21)
    right = Card(label9(src_label, C.gold, marginBottom=8), source_table(rows))
    return Section(T_S11, h("div", {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": 14}, left, right),
                   accent=C.inkD, key="codong.s11")


# ── Lắp tab ─────────────────────────────────────────────────────────────────


def ticker_tree(ctx, D, tk, deep_fn, deep_reason, inc, L=None):
    parts = [s1(D, tk, L), s2(D, tk, L)]
    if has_deep(tk, D.policy):
        parts.append(s3(ctx, D, tk, deep_fn, deep_reason, inc))
    parts += [s4(D, tk, L), s5(tk, L), s6(tk, L), *s7(D, tk, L), s8(D, tk, L), s9(D, tk, L), s10(D, tk, L), s11(tk, L)]
    tree = h("div", None, *parts, key="codong.tk." + tk)
    return L.pattern_q(tree) if L else tree


def _live_module(ctx):
    if not ctx.live:
        return None
    try:
        return importlib.import_module("chaebol_map_tab_codong_live")
    except Exception as exc:  # live hỏng → vẫn dựng bản V21 + cảnh báo (không bịa số)
        ctx.warn("chaebol_map_tab_codong_live nhập lỗi → live dựng như v21: %s: %s" % (type(exc).__name__, exc))
        return None


def _v2_module(ctx):
    """Chỉ live: tab codong v2. Nhập lỗi → cảnh báo, dựng tiếp bản live 48 mã cũ (không vỡ tab)."""
    if not ctx.live:
        return None
    try:
        return importlib.import_module("chaebol_map_tab_codong_v2")
    except Exception as exc:
        ctx.warn("chaebol_map_tab_codong_v2 nhập lỗi → live dựng bản 48 mã cũ: %s: %s" % (type(exc).__name__, exc))
        return None


def v2_universe(ctx):
    """Chỉ live: tập mã của tab codong v2 = đích các nút liên kết từ tab nhóm / vciq / screener (§8.3).
    Mode v21 hoặc đọc vũ trụ lỗi → rỗng (không nút; lỗi kèm cảnh báo)."""
    if not ctx.live:
        return frozenset()
    try:
        import chaebol_map_data_codong2 as owner          # nhập trễ: mode v21 không nạp module dữ liệu live
        return frozenset(owner.universe_groups(ctx.v21)["order"])
    except Exception as exc:
        ctx.warn("vũ trụ codong v2 không đọc được (%s: %s) → không có nút sang tab codong" % (type(exc).__name__, exc))
        return frozenset()


def link_set(tk, sub="phase_info"):
    """on.set của nút sang tab codong v2: đặt cùng lúc tab + codong.tk (+ codong.sub khi sub khác None); scope codong
    giữ giá trị vì tab được dựng ngay trong lượt render đó."""
    return {"set": {"tab": "codong", K_TK: tk, **({K_SUB: sub} if sub else {})}}


def link_button(tk, label, key, sub="phase_info"):
    """Nút liên kết sang tab codong v2 (cùng kiểu nút ◈ VIETCAP IQ của bản live cũ)."""
    return h("button", S_LINK, label, on=link_set(tk, sub), key=key)


def build_codong(ctx):
    v2 = _v2_module(ctx)
    if v2 is not None:
        return v2.build_codong_v2(ctx)
    D = V21(ctx.v21)
    deep_fn, deep_reason = load_deep(ctx)
    if deep_fn is None:
        ctx.warn("Deep-dive dùng khối giữ chỗ: " + deep_reason)
    live = _live_module(ctx)
    shared = live.Shared(ctx, D) if live else None
    inc, placeholders, csv = {}, [], []
    for tk in D.tickers:
        L = live.LiveTk(shared, tk) if live else None
        inc["codong/" + tk] = ticker_tree(ctx, D, tk, deep_fn, deep_reason, inc, L)
        placeholders.append(h("div", None, if_={K_TK: tk}, inc="codong/" + tk))
        p = D.policy.get(tk) or {}
        row = {"ma": tk, "basket": p.get("basket"), "cluster": p.get("cluster"), "tag": p.get("tag"),
               "deep_dive": "có" if has_deep(tk, D.policy) else "ẩn"}
        if L:
            row.update(L.csv_extra())
        csv.append(row)
    if shared is not None:
        shared.finish()
    states = [{"key": K_TK, "default": "VIC", "options": list(D.tickers)},
              {"key": K_SUB, "default": "phase_info", "options": [s for s, _ in D.subs]}]
    return {"root": h("div", None, *placeholders, key="codong.root"), "states": states, "inc": inc, "csv": csv}
