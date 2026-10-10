#!/usr/bin/env python3
"""
chaebol_map_tab_groups_live — lớp live cho tab 02–06 (tuanmuot, sovico, phuong, bauthuy, eliminated).

Chỉ dùng ở mode live (chaebol_map_tab_groups.build_group tạo LiveGroup). Hợp đồng: DESIGN §0.3–0.7, §6; api_python §6.
- Số sống (chaebol_map_data): giá thô phiên cuối (FACT-T2), Δ60d và Δ từ 08/05 trên giá điều chỉnh quyền (EST),
  vốn hoá/số cp (vendor), NN + tự doanh 60 phiên (FACT-T2), phần dư −(NN+TD) (EST, "phần dư"), CN/TC = [CẦN DATA].
- Câu/ô viết lại: ctx.dossier → chaebol_groups.<id>.deep_dive, tickers.<MÃ>.deep_card (mảnh
  knowledge_os/chaebol_map/cap_nhat_2026-09-27.groups.json; mỗi mục có tier/asof/src).
- Nhận định/stance V21 (pha, BUY/AVOID, KHÔNG MUA ĐUỔI, P-NEXT, ĐỌC FLOW, PhaseBar…) giữ nguyên văn + U + V21·12/05.
- Claim có điều kiện falsify đo được → status_pill + bằng chứng + bậc (từ dossier).
"""
from __future__ import annotations

import re

import chaebol_map_tab_codong as CD
from chaebol_map_dom import (
    C, F_MONO, F_SERIF, can_data, h, js_string, sign_fixed, status_pill, tier, to_fixed, to_locale, upd_mark, v21_mark,
)
from chaebol_map_shell import FlowSignal, Stat

BASE_DATE = "2026-05-08"            # phiên chốt dữ liệu V21 (FLOW 08/05)
FLOW_HEAD_LIVE = "FLOW 60D · NN+TD vc_lk 60 phiên · CN/TC chưa có kênh sau 08/05"
UPD_TITLE = "CẬP NHẬT 27/09 · DỮ KIỆN ĐÃ ĐỔI — stance V21 không chấm lại (CỔNG v1.7 DỪNG) · "
EVENTS_TITLE_LIVE = "⌖ Key Events Timeline (12 tháng → 27/09/2026)"
# Công ty con trong sơ đồ GELEX ↔ dòng relationship của vendor (mẹ, mã/tên chứa).
ECO_SUB_MAP = {"CAV — CADIVI": ("GEE", "CAV"), "THI — THIBIDI": ("GEE", "THIBIDI"), "EMIC": ("GEE", "emic"),
               "HEM": ("GEE", "HEMC"), "MEE": ("GEE", "mee"), "VGC — VIGLACERA": ("GEL", "VGC"),
               "VCW — Nước Sạch Sông Đà": ("GEL", "VWSC"), "PXL": ("GEL", "PXL"),
               "TITAN Hải Phòng": ("GEL", "titan hải phòng")}
ECO_PARENT = {"GEE": "GEE", "GEL": "GEL"}
ECO_PILL = {"background": C.paper, "padding": "0 3px", "borderRadius": 2}
# Nhãn pattern gắn với một mã (A–D của Toàn Vũ, Markdown/Markup) chưa mang '?' (CLAUDE.md §6 luật 4, DESIGN §8.4).
_PAT_Q = re.compile(r"\bPattern ([A-D]|Mark(?:down|up))\b(?!\?)")
_LABEL = {"fontSize": 9, "letterSpacing": ".18em", "fontFamily": F_MONO}


def ok(v):
    return v is not None and getattr(v, "value", None) is not None


def _strong(text, color):
    return h("strong", {**_LABEL, "color": color}, text)


class LiveGroup:
    def __init__(self, ctx, group, v21):
        self.ctx, self.D, self.group, self.gid = ctx, ctx.data, group, group["id"]
        dz = ctx.dossier if isinstance(ctx.dossier, dict) else {}
        self.dz = ((dz.get("chaebol_groups") or {}).get(self.gid) or {}).get("deep_dive") or {}
        self._tick = dz.get("tickers") or {}
        self._nums, self._csv, self._rel, self._tv, self._cd2 = {}, [], {}, None, None
        if not dz:
            ctx.warn("chưa có dossier cap_nhat — tab nhóm chỉ có số sống; câu V21 giữ nguyên + V21·12/05")
        elif not self.dz:
            ctx.warn("dossier thiếu chaebol_groups.%s.deep_dive — câu V21 giữ nguyên" % self.gid)
        if self.D is None:
            ctx.warn("chaebol_map_data không nạp được — mọi số sống của tab nhóm = [CẦN DATA]")

    # ── tiện ích nhãn ───────────────────────────────────────────────────────
    def v21(self):
        return v21_mark()

    def v21u(self):
        return [tier("U"), v21_mark()]

    def v21_flow_tier(self, fl):
        """Số FLOW V21 (FiinTrade ≤08/05, bậc theo trang FACT-T2) — đóng băng, không thay ngược."""
        return [tier("T2", fl.get("date")) if fl else None, v21_mark()]

    def tz(self, tk):
        return ((self._tick.get(tk) or {}).get("deep_card")) or {}

    def seg(self, e):
        """Mục dossier → [pill?] text + nhãn; `parts` = vế sau của cùng câu, mỗi vế mang bậc/ngày của CHÍNH số đó.
        Vế có `v21: true` là chữ V21 giữ nguyên văn (chưa chấm lại) → nhãn không ngày + V21·12/05."""
        out = []
        if e.get("status"):
            out += [status_pill(e["status"]), " "]
        for p in [e, *(e.get("parts") or [])]:
            out += ([p["text"], tier(p["tier"]), v21_mark()] if p.get("v21")
                    else [p["text"], tier(p["tier"], p.get("asof"))])
        return out

    def segs(self, lst, mark=True):
        out = []
        for i, e in enumerate(lst):
            out += ([" "] if i else []) + self.seg(e)
        return out + ([upd_mark()] if mark else [])

    # ── số sống ─────────────────────────────────────────────────────────────
    def _safe(self, fn, *a, **k):
        try:
            return fn(*a, **k)
        except Exception as exc:  # lớp dữ liệu lỗi không được làm hỏng tab
            self.ctx.warn("chaebol_map_data.%s%r lỗi: %s: %s" % (getattr(fn, "__name__", "?"), a, type(exc).__name__, exc))
            return None

    def num(self, tk):
        if tk in self._nums:
            return self._nums[tk]
        D = self.D
        n = {"px": None, "asof": None, "perf60": None, "pc0805": None, "mcap": None, "sh": None, "nn": None,
             "td": None, "du": None, "from": None, "to": None, "td_nco": None, "td_n": None, "td_last": None}
        if D is not None:
            lp = self._safe(D.last_price, tk) or {}
            n["px"] = lp.get("raw") if ok(lp.get("raw")) else None
            n["asof"] = n["px"].asof if n["px"] else None
            ph = self._safe(D.price_history, tk)
            if n["px"] is not None and ph is not None and len(ph) > 61:
                v = self._safe(D.pct_change, tk, ph.dates[-61])
                n["perf60"] = v if ok(v) else None
            v = self._safe(D.pct_change, tk, BASE_DATE) if n["px"] is not None else None
            n["pc0805"] = v if ok(v) else None
            for k, fn in (("mcap", D.market_cap), ("sh", D.shares_out)):
                v = self._safe(fn, tk) if n["px"] is not None else None
                n[k] = v if ok(v) else None
            f4 = (self._safe(D.flow4, tk, 60) or {}) if n["px"] is not None else {}
            for k in ("nn", "td", "du"):
                n[k] = f4.get(k) if ok(f4.get(k)) else None
            n["from"], n["to"] = f4.get("from"), f4.get("to")
            if n["td"] is not None:
                self._td_window(tk, n)
        self._nums[tk] = n
        self._csv.append({"ma": tk, "gia": n["px"].value if n["px"] else None, "ngay_gia": n["asof"],
                          "pct_60phien": round(n["perf60"].value, 2) if n["perf60"] else None,
                          "pct_tu_0805": round(n["pc0805"].value, 2) if n["pc0805"] else None,
                          "von_hoa_ty": round(n["mcap"].value / 1e9, 1) if n["mcap"] else None,
                          "nn60_trieu_cp": round(n["nn"].value, 3) if n["nn"] else None,
                          "td60_trieu_cp": round(n["td"].value, 3) if n["td"] else None,
                          "td_phien_co": "%s/%s" % (n["td_nco"], n["td_n"]) if n["td_nco"] is not None else None,
                          "ngay_td_cuoi": n["td_last"],
                          "bac": "FACT-T2 giá/NN/TD · EST %"})
        return n

    def _td_window(self, tk, n):
        """Tự doanh chậm 1–3 phiên và thưa: số phiên có bản ghi trong cửa sổ NN + ngày bản ghi cuối (DESIGN §9 —
        nhãn TD mang ngày của CHÍNH số TD, không phải phiên cuối của price-history). Phần dư chỉ tính khi đủ phiên."""
        fp, fv = getattr(self.D, "prop_net", None), getattr(self.D, "vc", None)
        pn = (self._safe(fp, tk, 60, None, "khop") if fp else None) or {}
        _, du = (self._safe(fv, tk, "proprietary-history") if fv else None) or (None, None)
        frm, to = n["from"], n["to"]
        if not (isinstance(du, dict) and frm and to and isinstance(pn.get("n_co"), int)):
            n["td"] = n["du"] = None       # không xác định được cửa sổ tự doanh → [CẦN DATA], không đoán ngày
            return
        days = [str(r[0])[:10] for r in du.get("hang") or [] if r]
        inwin = [d for d in days if frm <= d <= to]
        n["td_nco"], n["td_n"], n["td_last"] = pn["n_co"], pn.get("n"), max(inwin) if inwin else None
        if not n["td_last"]:
            n["td"] = None
        if not pn.get("complete"):
            n["du"] = None

    def _td_note(self, n):
        return "%s/%s phiên có bản ghi, tới %s" % (n["td_nco"], n["td_n"], self._ddmm(n["td_last"]))

    @staticmethod
    def _ddmm(d):
        return "%s/%s" % (d[8:10], d[5:7]) if d else "—"

    @staticmethod
    def _mfmt(x, unit="M"):
        """Triệu cp → chuỗi; |x| < 0,05 hiện theo nghìn cp để không in '-0.0' (mất dấu, mất độ lớn)."""
        if abs(x) >= 0.05:
            return sign_fixed(x, 1) + unit
        k = x * 1000
        return (("+" if k > 0 else "") + to_fixed(k, 1 if abs(k) < 10 else 0) if k else "0") + unit.replace("M", "K")

    def _px(self, n):
        return [to_locale(n["px"].value, "en"), tier(n["px"].tier, n["asof"])] if n["px"] else [can_data()]

    def _pct(self, v, style=None):
        if not v:
            return [can_data()]
        return [h("span", {"color": C.forest if v.value >= 0 else C.vermillion, **(style or {})},
                  sign_fixed(v.value, 1) + "%"), tier("E", v.asof)]

    def _mcap(self, n):
        v = n["mcap"]
        return [to_fixed(v.value / 1e12, 1) + "K tỷ", tier(v.tier, v.asof)] if v else [can_data()]

    def _shares(self, n):
        v = n["sh"]
        return [to_fixed(v.value / 1e6, 0) + "M cp", tier(v.tier, v.asof)] if v else None

    # ── khối đầu nhóm ───────────────────────────────────────────────────────
    def head_title(self, text):
        e = self.dz.get("head_title")
        return [*self.seg(e), upd_mark()] if e else [text, tier("U"), v21_mark()]

    def group_text(self, field, text):
        return [text, tier("U"), v21_mark()]

    def group_update_box(self):
        items = self.dz.get("update") or []
        if not items:
            return None
        return h("div", {"marginTop": 12, "padding": "10px 14px", "background": C.ochre + "10",
                         "borderLeft": "3px solid " + C.ochre, "fontSize": 11, "fontFamily": F_SERIF, "color": C.ink,
                         "lineHeight": 1.7},
                 _strong(UPD_TITLE, C.ochre), upd_mark(),
                 h("ul", {"margin": "6px 0 0", "paddingLeft": 16},
                   *[h("li", {"marginBottom": 3}, *self.seg(e)) for e in items]),
                 key="grp-update")

    def events_title(self):
        return EVENTS_TITLE_LIVE

    def events(self, group):
        rows = [(e["date"], [*self.seg(e), upd_mark()]) for e in self.dz.get("events_new") or []]
        st = self.dz.get("events_status") or {}
        for i, e in enumerate(group["keyEvents"]):
            s = st.get(str(i))
            nodes, date = [e["evt"], tier("U"), v21_mark()], e["date"]
            if s:
                nodes.append(h("div", {"marginTop": 4, "fontSize": 11, "color": C.inkD},
                               *self.seg(s), upd_mark()))
                if s.get("date"):
                    date = [s["date"], upd_mark()]
            rows.append((date, nodes))
        return rows

    # ── nút mã + thẻ mã ─────────────────────────────────────────────────────
    def button_line(self, t, fl, key):
        """Dòng 2 của nút mã. Nhãn bậc / [CẦN DATA] mang màu riêng → khi chip active (nền màu nhóm) đổi sang màu
        chữ của chip (C.bg) như số Δ60d, để không tàng hình (T2 ink2 trên nền xanh phuong, E ochre trên vàng…)."""
        n = self.num(t)
        st = {"fontSize": 10, "fontWeight": 400, "marginTop": 3, "opacity": 0.8}
        on = [{"if": {key: t}, "s": {"color": C.bg}}]
        if not n["px"]:
            return h("div", st, self._on_chip(can_data(), on))
        pf = n["perf60"]
        span = (h("span", {"color": C.forest if pf.value >= 0 else C.vermillion}, sign_fixed(pf.value, 1), "%",
                  self._on_chip(tier("E", pf.asof), on), var=on) if pf else self._on_chip(can_data(), on))
        px = [self._on_chip(x, on) if isinstance(x, dict) else x for x in self._px(n)]
        return h("div", st, *px, " · ", span)

    @staticmethod
    def _on_chip(node, on):
        if isinstance(node, dict):
            node["var"] = h("span", None, var=on)["var"]
        return node

    def stats_row(self, tk, det, fl):
        n = self.num(tk)
        pc = n["pc0805"]
        post = self.tz(tk).get("post_dilution")
        return h("div", {"display": "flex", "flexWrap": "wrap", "gap": 14, "padding": "14px 0",
                         "borderTop": "1px solid " + C.rule, "borderBottom": "1px solid " + C.rule, "marginBottom": 14},
                 Stat("GIÁ HIỆN TẠI", self._px(n), sub=n["asof"] or "", color=C.gold, big=True),
                 Stat("Δ TỪ 08/05", [sign_fixed(pc.value, 1) + "%", tier("E", pc.asof)] if pc else [can_data()],
                      sub="giá điều chỉnh quyền", color=(C.forest if pc.value >= 0 else C.vermillion) if pc else None),
                 Stat("VỐN HÓA", self._mcap(n), sub=self._shares(n)),
                 Stat("POST-DILUTION", [post["text"], tier(post["tier"], post.get("asof"))],
                      sub=[post.get("stake"), upd_mark()]) if post else None)

    def _th(self, text, align):
        return h("th", {"textAlign": align, "padding": "4px 0", "color": C.inkM, "fontSize": 9, "letterSpacing": ".1em",
                        "fontWeight": 400}, text)

    def _td(self, kids, color=C.ink, bold=False, left=False):
        st = {"padding": "8px 0", "textAlign": "left" if left else "right", "color": color}
        if bold:
            st["fontWeight"] = 700
        return h("td", st, *kids)

    def plan_table(self, tk, det):
        """KẾ HOẠCH 2026 (AGM) + cột 6T/26 ACTUAL (dossier); Q1/26 V21 giữ; %KH tính lại theo 6T khi có số."""
        plan, py, q1 = det["plan2026"], det.get("py2025") or {}, det.get("q1_26") or {}
        dp = self.tz(tk).get("plan") or {}
        h6, g6, ver = dp.get("h6") or {}, dp.get("g6") or {}, dp.get("verify")
        rows = []
        for label, field, border in (("Doanh thu (tỷ)", "rev_b", True), ("LN trước thuế (tỷ)", "pretax_b", False)):
            p = plan.get(field)
            if not p:
                continue
            a, q, c6 = py.get(field), q1.get(field), h6.get(field)
            if c6:
                kh = [to_fixed(c6["v"] / p * 100, 0) + "%", tier("E", c6.get("asof"))]
            elif q:
                kh = [to_fixed(q / p * 100, 0) + "% (Q1)", tier("U")]
            else:
                kh = ["—"]
            # verify.fields = ô KH mà nguồn xác minh thật sự chứa (vắng = mọi ô); ô còn lại là số V21 → U + V21·12/05
            vok = ver and field in (ver.get("fields") or (field,))
            rows.append(h("tr", {"borderBottom": "1px solid " + C.rule + "50"} if border else None,
                          h("td", {"padding": "8px 0", "color": C.inkD, "fontSize": 11}, label),
                          self._td([to_locale(a, "en"), tier("U")] if a else ["—"]),
                          self._td([to_locale(p, "en"), tier(ver["tier"], ver.get("asof"))] if vok
                                   else [to_locale(p, "en"), tier("U"), v21_mark()], C.gold, True),
                          self._td([to_locale(q, "en"), tier("U")] if q else ["—"]),
                          self._td([to_locale(c6["v"], "en"), tier(c6["tier"], c6.get("asof"))] if c6 else [can_data()]),
                          self._td(kh, C.inkD)))
        rg, pg = det.get("revGrowth"), det.get("profitGrowth")

        def g(label, x, c6):
            v21 = [h("span", {"color": C.forest if x > 0 else C.vermillion, "fontWeight": 700},
                     ("+" if x > 0 else "") + js_string(x) + "%"), tier("U")] \
                if x else ["—"]
            new = ([" · 6T ", h("span", {"color": C.forest if c6["v"] > 0 else C.vermillion, "fontWeight": 700},
                                  sign_fixed(c6["v"], 1) + "%"), tier(c6["tier"], c6.get("asof"))] if c6 else [])
            return h("span", None, label, *v21, *new)
        notes = [e for e in (ver, dp.get("note")) if e]
        return h("div", {"marginBottom": 14},
                 h("div", {**_LABEL, "fontSize": 10, "color": C.inkM, "marginBottom": 8},
                   "KẾ HOẠCH 2026 (AGM) · 6T/2026", upd_mark()),
                 h("table", {"width": "100%", "borderCollapse": "collapse", "fontSize": 11,
                             "fontFamily": "'JetBrains Mono', monospace"},
                   h("thead", None, h("tr", {"borderBottom": "1px solid " + C.rule},
                                      self._th("METRIC", "left"), self._th("2025 ACTUAL", "right"),
                                      self._th("2026 PLAN", "right"), self._th("Q1/26 ACTUAL", "right"),
                                      self._th("6T/26 ACTUAL", "right"), self._th("%KH", "right"))),
                   h("tbody", None, *rows)),
                 h("div", {"display": "flex", "gap": 14, "marginTop": 8, "fontSize": 10, "fontFamily": F_MONO,
                           "color": C.inkD, "flexWrap": "wrap"},
                   g("Δ DT YoY: ", rg, g6.get("rev")), g("Δ LN YoY: ", pg, g6.get("pretax"))),
                 h("div", {"marginTop": 6, "fontSize": 10, "fontFamily": F_SERIF, "color": C.inkD, "lineHeight": 1.6},
                   *self.segs(notes)) if notes else None)

    def _mini_table(self, e):
        rows = []
        for r in e.get("rows") or []:
            cells = [h("td", {"padding": "6px 0", "color": C.inkD, "fontSize": 11}, r[0])]
            for c in r[1:]:
                if isinstance(c, dict):              # ô có nguồn/ngày riêng (vd KH ĐHĐCĐ 24/04 cạnh KQKD 31/07)
                    kids = [c["text"], tier(c["tier"], c.get("asof"))]
                elif c in ("—", ""):                 # không truy được → [CẦN DATA], không để trống
                    kids = [can_data()]
                else:
                    kids = [c, tier(e["tier"], e.get("asof"))]
                cells.append(h("td", {"padding": "6px 0", "textAlign": "right", "color": C.ink}, *kids))
            rows.append(h("tr", {"borderBottom": "1px solid " + C.rule + "50"}, *cells))
        head = e.get("head") or []
        return h("table", {"width": "100%", "borderCollapse": "collapse", "fontSize": 11,
                           "fontFamily": "'JetBrains Mono', monospace"},
                 h("thead", None, h("tr", {"borderBottom": "1px solid " + C.rule},
                                    *[self._th(x, "left" if i == 0 else "right") for i, x in enumerate(head)])),
                 h("tbody", None, *rows))

    def plan_extra(self, tk):
        """Mã không có bảng KH V21: bảng KQKD mới (dossier) hoặc dòng [CẦN DATA]."""
        dz = self.tz(tk)
        kq, miss = dz.get("kqkd"), dz.get("kqkd_missing")
        if kq:
            return h("div", {"marginBottom": 14},
                     h("div", {**_LABEL, "fontSize": 10, "color": C.inkM, "marginBottom": 8}, kq["text"], upd_mark()),
                     self._mini_table(kq))
        if miss:
            return h("div", {"marginBottom": 14, "fontSize": 10, "fontFamily": F_MONO, "color": C.inkD},
                     "KQKD 6T/2026 · ", can_data("chưa có BCTC trong gói dữ kiện 27/09"))
        return None

    def dgc_block(self, tk, det):
        q1, cash = det["q1_26"], det.get("cash")
        q2 = self.tz(tk).get("q2") or {}
        u = lambda text: [text, tier("U")]  # noqa: E731
        row2 = None
        if q2:
            t = lambda k: [q2[k]["text"], tier(q2[k]["tier"], q2[k].get("asof"))]  # noqa: E731
            s = lambda k: [q2[k]["stake"], tier(q2[k]["tier"], q2[k].get("asof"))]  # noqa: E731
            row2 = [h("div", {**_LABEL, "fontSize": 10, "color": C.vermillion, "margin": "10px 0 6px"},
                      q2["title"]["text"], upd_mark()),
                    h("div", {"display": "flex", "gap": 14, "flexWrap": "wrap"},
                      Stat("Q2 DOANH THU", t("rev"), sub=s("rev"), color=C.vermillion),
                      Stat("Q2 LNST HỢP NHẤT", t("profit"), sub=s("profit"), color=C.vermillion),
                      Stat("KH LNST 2026", t("plan"), sub=s("plan"), color=C.gold))]
        return h("div", {"marginBottom": 14, "padding": "12px 14px", "background": C.vermillion + "10",
                         "border": "1px solid " + C.vermillion + "40"},
                 h("div", {**_LABEL, "fontSize": 10, "color": C.vermillion, "marginBottom": 6},
                   "Q1/2026 ACTUAL — KEY FINANCIAL", v21_mark()),
                 h("div", {"display": "flex", "gap": 14, "flexWrap": "wrap"},
                   Stat("DOANH THU", u(to_locale(q1.get("rev_b"), "en") + " tỷ"), sub=u("−24% YoY"),
                        color=C.vermillion),
                   Stat("LNST HỢP NHẤT", u(js_string(q1["profit"]) + " tỷ"),
                        sub=u("vs Q1/25: %s (-49%%)" % js_string(q1["prevProfit"])),
                        color=C.vermillion),
                   Stat("CASH POSITION", u(to_fixed(cash / 1000, 1) + "K tỷ"), sub=u("62% tổng tài sản"), color=C.gold)
                   if cash else None),
                 *(row2 or []))

    def holdings(self, tk, det):
        dz = self.tz(tk)
        v21 = det.get("holdings") or []
        if dz.get("holdings"):
            # value_asof: vế 'value' có ngày riêng (vd HAH 5.16% mốc 26/08 · đăng ký bán 23/09) → mỗi vế một nhãn
            out = [{"name": e["text"], "stake": [e["stake"], tier(e["tier"], e.get("asof"))], "value": e["value"],
                    "_mark": [tier(e.get("value_tier") or e["tier"], e["value_asof"])]} if e.get("value_asof") else
                   {"name": e["text"], "stake": e["stake"], "value": e["value"],
                    "_mark": [tier(e["tier"], e.get("asof"))]} for e in dz["holdings"]]
            codes = {m for e in dz["holdings"] for m in re.findall(r"\b([A-Z]{3})\b", e["text"])}
            for hh in v21:                       # dòng V21 không có mã thay thế (vd Fairmont) → giữ + U
                if not set(re.findall(r"\b([A-Z]{3})\b", hh["name"])) & codes:
                    out.append({**hh, "_mark": [tier("U"), v21_mark()]})
            return out
        upd = dz.get("holdings_update") or {}
        out = []
        for hh in v21:
            e = upd.get(hh["name"])
            out.append({"name": e["text"], "stake": e["stake"], "value": e["value"],
                        "_mark": [tier(e["tier"], e.get("asof")), upd_mark()]} if e else {**hh, "_mark": [tier("U")]})
        return out

    def holdings_mark(self, tk):
        dz = self.tz(tk)
        return upd_mark() if (dz.get("holdings") or dz.get("holdings_update")) else v21_mark()

    def _dynamic(self, tk):
        """Câu tính lúc dựng từ số sống (EST): quy đổi quyền mốc V21, so với VN-Index."""
        D, out = self.D, []
        if D is None:
            return out
        n = self.num(tk)
        if tk == "VIX":
            # Mốc 13K đặt trên giá thô 05/2026; sau GDKHQ 20/08 so với giá hiện hành phải dùng mốc đã quy đổi quyền.
            v = self._safe(D.convert_price, "VIX", 13000, BASE_DATE)
            if ok(v):
                out += [" Trên nền giá hiện hành, mốc 13K quy đổi quyền ≈ ", to_locale(round(v.value), "en"),
                        tier("E", v.asof)]
                if n["px"]:
                    out += ["; đóng cửa ", self._ddmm(n["asof"]), " = ", to_locale(n["px"].value, "en"),
                            tier(n["px"].tier, n["asof"]),
                            " — đang " + ("trên" if n["px"].value >= v.value else "dưới") + " mốc này"]
                out.append(".")
        if tk in ("PC1", "CTD", "GEX", "DGC") and n["pc0805"]:
            ix = self._safe(D.index_extremes, "VNINDEX", BASE_DATE) or {}
            vi = ix.get("since_start")
            out += [" Giá từ 08/05: ", sign_fixed(n["pc0805"].value, 1), "%", tier("E", n["pc0805"].asof)]
            if ok(vi):
                out += [" vs VN-Index ", sign_fixed(vi.value, 1), "%", tier("E", vi.asof)]
            out.append(".")
        return out

    def text(self, tk, field, v21text):
        dz = self.tz(tk)
        if field == "story":
            return self.segs(dz["story"]) if dz.get("story") else [v21text, tier("U"), v21_mark()]
        out = [v21text, tier("U"), v21_mark()]
        ru, dyn = dz.get("risk_update") or [], self._dynamic(tk)
        if ru or dyn:
            out.append(h("div", {"marginTop": 6, "paddingTop": 6, "borderTop": "1px dashed " + C.vermillion + "40"},
                         _strong("DỮ KIỆN 27/09 · ", C.vermillion), *self.segs(ru, mark=False), *dyn, upd_mark()))
        return out

    def value_trap(self, tk, vtw):
        e = self.tz(tk).get("vtw_status")
        out = [vtw, tier("U"), v21_mark()]
        if e:
            out.append(h("div", {"marginTop": 6}, *self.seg(e), upd_mark()))
        return out

    def name(self, tk, det):
        e = self.tz(tk).get("name")
        return [e["text"], tier(e["tier"], e.get("asof")), upd_mark()] if e else det["name"]

    def sector(self, tk, det):
        e = self.tz(tk).get("sector")
        return [e["text"], tier(e["tier"], e.get("asof"))] if e else det["sector"]

    def pnext_status(self, tk):
        e = self.tz(tk).get("pnext_status")
        if not e:
            return None
        return h("div", {"marginTop": 6, "fontSize": 10, "fontFamily": F_MONO, "color": C.inkD, "lineHeight": 1.6},
                 *self.seg(e), upd_mark())

    def flow_signal(self, tk, fl):
        n = self.num(tk)
        g = lambda k: n[k].value if n[k] else None  # noqa: E731
        asof = n["to"] or n["asof"]
        live = {"sig": None, "ca60": None, "to60": None, "td60": g("td"), "nn60": g("nn"), "date": asof,
                "px": g("px"), "perf60": g("perf60")}
        tiers = {"nn60": ("T2", asof), "td60": ("T2", n["td_last"]), "px": ("T2", n["asof"]),
                 "perf60": ("E", n["asof"])}
        du = n["du"]
        v = lambda k: sign_fixed(fl[k], 1)  # noqa: E731
        extra = h("div", {"fontSize": 9, "color": C.inkM, "fontFamily": F_MONO, "letterSpacing": ".05em",
                          "lineHeight": 1.6, "marginBottom": 10},
                  h("div", None, "Tự doanh: ", self._td_note(n), " (phiên vắng không điền 0; NN đủ 60 phiên tới ",
                    self._ddmm(asof), ")") if n["td"] else None,
                  h("div", None, "Phần dư −(NN+TD) = ",
                    *([self._mfmt(du.value), tier("E", du.asof)] if du else [can_data(self._du_gap(n))]),
                    " · phần dư, không phải kênh thật"),
                  h("div", None, "Bản V21 · FiinTrade 60 phiên tới ", fl["date"], ": CN ", v("ca60"), " · TC ",
                    v("to60"), " · TD ", v("td60"), " · NN ", v("nn60"), " (M cp) · ", fl["sig"],
                    *self.v21_flow_tier(fl)))
        sig = FlowSignal(live, head=FLOW_HEAD_LIVE, tiers=tiers)
        for label, key in (("Tự doanh", "td"), ("Nước ngoài", "nn")):
            if n[key] and abs(n[key].value) < 0.05:
                self._patch_bar(sig, label, self._mfmt(n[key].value))
        return [sig, extra]

    def _du_gap(self, n):
        if n["td"] and n["td_nco"] is not None and n["td_nco"] != n["td_n"]:
            return "tự doanh chỉ %s — lệch cửa sổ với NN, không tính" % self._td_note(n)
        return None

    @staticmethod
    def _patch_bar(sig, label, text):
        """FlowBar (shell) in số bằng toFixed(1) → '-0.0M' khi |x| < 0,05; thay chữ số của đúng hàng `label`."""
        for row in sig.get("k", ()):
            kids = row.get("k", ()) if isinstance(row, dict) else ()
            if kids and isinstance(kids[0], dict) and kids[0].get("k") == [label]:
                num = kids[-1].get("k") or []
                if num and isinstance(num[0], str) and re.fullmatch(r"[+-]?0\.0M", num[0]):
                    num[0] = text

    def placeholder_extra(self, tk):
        n = self.num(tk)
        dz = self.tz(tk)
        nn, td = n["nn"], n["td"]
        stats = h("div", {"display": "flex", "flexWrap": "wrap", "gap": 14, "marginBottom": 10},
                  Stat("GIÁ", self._px(n), sub=n["asof"] or "", color=C.gold),
                  Stat("Δ TỪ 08/05", [sign_fixed(n["pc0805"].value, 1) + "%", tier("E", n["pc0805"].asof)]
                       if n["pc0805"] else [can_data()], sub="giá điều chỉnh quyền"),
                  Stat("VỐN HÓA", self._mcap(n), sub=self._shares(n)),
                  Stat("NN 60 PHIÊN", [self._mfmt(nn.value, "M cp"), tier("T2", nn.asof)] if nn else [can_data()],
                       sub="khớp + thoả thuận"),
                  Stat("TỰ DOANH 60 PHIÊN", [self._mfmt(td.value, "M cp"), tier("T2", n["td_last"])] if td
                       else [can_data()], sub=("khớp · " + self._td_note(n) if td else "khớp") + "; CN/TC [CẦN DATA]"))
        cd = None
        if self.D is not None:
            m = self._safe(self.D.codong_moc, tk)
            if ok(m):
                obs = [x for x in m.value if not x.get("cf")]
                last = obs[-1] if obs else m.value[-1]
                cfs = [x["ky"] for x in m.value if x.get("cf")]
                cd = h("div", {"fontSize": 10, "fontFamily": F_MONO, "color": C.inkD, "marginBottom": 8},
                       "Số cổ đông (Toàn Vũ): ", to_locale(last["v"], "en"), tier(last.get("tier") or "T3"),
                       " · kỳ ", last["ky"], (" · mốc " + ", ".join(cfs) + " là CF — chưa có số mới") if cfs else "")
        facts = dz.get("facts") or []
        return h("div", {"marginTop": 4, "paddingTop": 12, "borderTop": "1px solid " + C.rule},
                 h("div", {**_LABEL, "color": C.ochre, "marginBottom": 10},
                   "SỐ SỐNG + DỮ KIỆN 27/09 · " + tk + (" (niêm yết HOSE 18/08 với mã LPS)" if tk == "LPBS" else ""),
                   upd_mark()),
                 stats, cd,
                 h("ul", {"margin": 0, "paddingLeft": 16, "fontSize": 11, "fontFamily": F_SERIF, "color": C.ink,
                          "lineHeight": 1.7},
                   *[h("li", {"marginBottom": 3}, *self.seg(e)) for e in facts]) if facts else
                 h("div", {"fontSize": 11, "color": C.inkD}, can_data("chưa có dữ kiện 27/09 cho mã này")),
                 key="grp-live:" + tk)

    def pattern_q(self, card, tk):
        """Mã ngoài 30 mã Toàn Vũ: mọi 'Pattern X' trong thẻ của mã (kể cả câu V21 giữ nguyên văn) → 'Pattern X?'
        (CLAUDE.md §6 luật 4, DESIGN §8.4). Không đọc được danh sách 30 mã → không xác nhận được → cũng gắn '?'."""
        if tk in self._tv30():
            return card
        stack = [card]
        while stack:
            kids = stack.pop().get("k") or []
            for i, c in enumerate(kids):
                if isinstance(c, str):
                    kids[i] = _PAT_Q.sub(lambda m: "Pattern %s?" % m.group(1), c)
                elif isinstance(c, dict):
                    stack.append(c)
        return card

    def codong_link(self, card, tk):
        """Nút '→ Cấu trúc cổ đông v2' (key cd2.link.<MÃ>, codong_v2_spec §8.3): đặt tab + codong.tk + codong.sub; chỉ
        mã trong vũ trụ codong v2 (LPBS chưa niêm yết: không nút). Thẻ hồ sơ: đầu cột trái; thẻ giữ chỗ: cuối thẻ."""
        if self._cd2 is None:
            self._cd2 = CD.v2_universe(self.ctx)
        if tk not in self._cd2:
            return card
        btn = CD.link_button(tk, "→ Cấu trúc cổ đông v2", "cd2.link." + tk)
        kids = card.setdefault("k", [])
        if (card.get("s") or {}).get("display") == "grid":        # ticker_card: [cột trái, cột phải]
            kids[0].setdefault("k", []).insert(0, h("div", {"marginBottom": 10}, btn))
        else:                                                     # placeholder_card
            kids.append(h("div", {"marginTop": 12}, btn))
        return card

    def _tv30(self):
        if self._tv is None:
            fn = getattr(self.D, "tv30", None)
            self._tv = frozenset((self._safe(fn) if fn else None) or ())
        return self._tv

    # ── sơ đồ GELEX ────────────────────────────────────────────────────────
    def _eco(self):
        return self.dz.get("eco") or {}

    @staticmethod
    def eco_contrast(root):
        """Sơ đồ là infographic nền sáng/màu (navy, kem, đào, trắng) còn màu bậc chọn cho nền tối → bọc nhãn bậc và
        dấu ↻ trong viên nền C.paper để giữ tương phản như ở phần còn lại của trang."""
        stack = [root]
        while stack:
            nd = stack.pop()
            if not isinstance(nd, dict):
                continue
            if nd.get("_tier") or nd.get("_upd"):
                nd["s"] = {**nd.get("s", {}), **ECO_PILL}
            stack.extend(nd.get("k", ()))
        return root

    def eco_caption_mark(self):
        return [tier("U"), v21_mark(), h("span", {"color": C.ochre, "letterSpacing": ".1em"},
                                         " · % theo vc_lk/CBTT 27/09"), upd_mark()]

    def eco_chairman_role(self, eco):
        e = self._eco().get("chairman_role")
        return [e["text"], tier(e["tier"], e.get("asof")), upd_mark()] if e else [eco["chairman"]["role"], v21_mark()]

    def eco_own_pct(self, kind, o):
        e = self._eco().get(kind)
        return [e["text"], tier(e["tier"], e.get("asof"))] if e else [o["pct"], tier("U")]

    def eco_family_note(self):
        e = self._eco().get("family_note")
        return [" (", e["text"], tier(e["tier"]), ")"] if e else [tier("U")]

    def eco_finance_note(self):
        e = self._eco().get("finance_note")
        if not e:
            return None
        return h("div", {"fontSize": 10, "color": "#475569", "marginTop": 4, "fontFamily": F_MONO},
                 e["text"], tier(e["tier"], e.get("asof")))

    def _relations(self, parent):
        if parent not in self._rel:
            r = self._safe(self.D.relationships, parent) if self.D is not None else None
            self._rel[parent] = (r or {}).get("subsidiaries") or []
        return self._rel[parent]

    def _rel_pct(self, parent, needle):
        for s in self._relations(parent):
            code, name = str(s.get("code") or ""), str(s.get("name") or "")
            if needle == code or needle.lower() in name.lower() or needle.lower() == code.lower():
                v = s.get("pct")
                if ok(v):
                    return v
        return None

    def eco_sub_pct(self, b, s):
        m = ECO_SUB_MAP.get(s["name"])
        v = self._rel_pct(*m) if m else None
        if v:
            return [to_fixed(v.value, 2) + "%", tier("T2")]
        return [s["pct"], tier("U") if s["pct"] not in ("—", "") else None]

    def eco_parent_pct(self, b):
        code = ECO_PARENT.get(b["tk"])
        v = None
        if code:
            for s in self._relations("GEX"):
                if s.get("ticker") == code and ok(s.get("pct")):
                    v = s["pct"]
        return [to_fixed(v.value, 2) + "%", tier("T2")] if v else [b["parentPct"], tier("U")]

    def eco_branch_name(self, b):
        return b["name"]

    def eco_eib_pct(self, hh):
        e = (self._eco().get("eib") or {}).get(hh["entity"])
        if e:
            return h("span", {"color": "#92400e"}, e["text"], tier(e["tier"], e.get("asof")))
        return [hh["pct"], tier("U") if re.search(r"\d", str(hh["pct"])) else None]

    def eco_eib_note(self):
        lst = self._eco().get("eib_note") or []
        if not lst:
            return None
        return h("div", {"marginTop": 8, "fontSize": 9.5, "color": "#92400e", "fontFamily": F_MONO, "lineHeight": 1.6},
                 *self.segs(lst))

    # ── kết thúc ────────────────────────────────────────────────────────────
    def csv_rows(self):
        return list(self._csv)

    def finish(self):
        return None
