#!/usr/bin/env python3
"""
chaebol_map_tab_codong_deep_live — lớp sống (mode live) cho Deep-dive 10 sub-tab (chaebol_map_tab_codong_deep).

Luật (DESIGN §0.3–0.7, §6; api_python §6): cùng builder với v21, chỉ thêm/đổi lớp dữ liệu:
  (a) số có nguồn sống → số sống + nhãn bậc (giá/NN/TD/cổ đông vc_lk FACT-T2; VWAP, %, quy đổi quyền EST)
  (b) dữ kiện đã đổi → khối "↻ CẬP NHẬT 27/09" theo dossier cap_nhat_2026-09-27.codong_deep.json (dự phòng:
      facts_f*.json qua chaebol_map_data.facts_for_src), mỗi mục mang nhãn bậc + dấu ↻
  (c) nhận định/stance V21 (pha, HI/BASE/STOP, sizing, verdict, trigger…) giữ nguyên + dấu V21·12/05
  (d) claim có điều kiện đo được → chấm lại (ĐẠT/BỊ BÁC/CHƯA RÕ/LIVE/HẾT HẠN) + bằng chứng + bậc
  (e) không có nguồn → [CẦN DATA]; (f) dòng tiền sau 08/05: chỉ NN + tự doanh thật, CN/TC [CẦN DATA]
  (g) mốc giá cũ quy đổi quyền (adj_factor từ 08/05); (h) pattern máy luôn có "?"; CF = "chưa có số mới"
  (i) không hô mua/bán — "action cần kiểm chứng", >5% NAV → Synthesis L1+L2+L3; (j)(k) pháp lý: UNVERIFIED + caveat
Mọi lời gọi chaebol_map_data bọc try/except → lỗi = [CẦN DATA] + cảnh báo (build không vỡ).
"""
from __future__ import annotations

import re

from chaebol_map_dom import (C, F_MONO, F_SERIF, can_data, h, sign_fixed, status_pill, tier, to_fixed, to_locale,
                             upd_mark, v21_mark)
from chaebol_map_shell import Card, Section, Stat
from chaebol_map_tab_codong_common import (KIEU_VI, LEGAL_NAME_RE, VWAP_NHAN, cap_status, codong_summary, ddmm,
                                           ddmmyyyy, fact_item, flow_view, k1, ky_vi, mcp, rich, route_facts,
                                           vi_label, win_label)
from chaebol_map_tab_codong_deep_chart import is_num, jsv, mode_a, truthy

V21_DATE = "2026-05-08"            # phiên cuối dữ liệu V21 — cơ sở giá của mốc HI/BASE/STOP/ANCHOR/VWAP
V21_SET = "2026-05-12"             # ngày trang chốt nhận định (mốc bắt đầu chấm lại)
V21_CUT = "2026-05-09"             # dữ kiện/sự kiện "mới" = từ ngày này
ADJ_TOL = 0.002                    # closeAdj/close phiên cuối phải = 1 (lệch hơn → chuỗi điều chỉnh vendor hỏng)
SUB_KEY = "codong.sub"
LOAI_VI = {"so_lieu": "số liệu", "su_kien": "sự kiện", "ke_hoach": "kế hoạch", "nhan_su": "nhân sự", "claim": "claim",
           "chinh_sach": "chính sách"}
LEGAL_RE = re.compile(r"khởi tố|thanh tra|bắt |điều tra|chính trị|political|protection|tội|Bộ Công an|pháp lý|"
                      r"tòa|toà|kiện|vi phạm", re.I)
CAP_STYLE = {"fontSize": 9, "letterSpacing": ".1em", "color": C.inkM, "fontFamily": F_MONO, "marginBottom": 8}
UPD_BOX = {"marginTop": 12, "padding": "10px 14px", "background": C.ochre + "10", "border": "1px solid " + C.ochre + "40",
           "borderRadius": 3, "fontSize": 10.5, "color": C.inkD, "lineHeight": 1.65}
LIVE_BOX = {"padding": "10px 14px", "background": C.ink2 + "10", "border": "1px solid " + C.ink2 + "40",
            "borderRadius": 3, "fontSize": 11, "color": C.inkD, "lineHeight": 1.7}
TR_ROW = {"borderBottom": "1px solid " + C.rule + "80"}
TR_HEAD = {"borderBottom": "1px solid " + C.rule}


class DeepLive:
    """Lớp sống cho một mã. Mọi phương thức trả nút (hoặc None) để builder chèn đúng chỗ."""

    def __init__(self, ctx, tk, T):
        self.ctx, self.tk, self.T = ctx, tk, T
        self.D = getattr(ctx, "data", None)
        dos = getattr(ctx, "dossier", None) or {}
        self.dos = (((dos.get("tickers") or {}).get(tk) or {}).get("deep10")) if isinstance(dos, dict) else None
        self._cache = {}
        cong = ((getattr(ctx, "live_info", None) or {}).get("cong") or {}).get("text") or ""
        self.cong_stop = ("DỪNG" in cong) or ("CẦN DATA" in cong) or not cong

    # ── tiện ích ──
    def _get(self, key, fn, *a, **k):
        if key in self._cache:
            return self._cache[key]
        val = None
        if self.D is not None:
            try:
                val = getattr(self.D, fn)(*a, **k)
            except Exception as exc:  # lớp dữ liệu hỏng không được làm vỡ tab
                self.ctx.warn("deep10 %s: %s lỗi %s: %s" % (self.tk, fn, type(exc).__name__, exc))
        self._cache[key] = val
        return val

    @staticmethod
    def ok(v):
        return v is not None and not getattr(v, "can", True) and getattr(v, "value", None) is not None

    def v21(self):
        return v21_mark()

    def v21_caption(self, text):
        return h("div", CAP_STYLE, text, v21_mark())

    @staticmethod
    def dmy(iso):
        """Ngày ISO của dữ liệu V21 chèn vào chuỗi mới của live → dd/mm/yyyy (DESIGN §11.3)."""
        return ddmmyyyy(iso)

    def spaced(self, node):
        """Khối sống đặt trên bản lưu V21: cách 12px (Card không nhận style ngoài)."""
        return h("div", {"marginBottom": 12}, node)

    def v21_caption_can(self, text, why):
        return h("div", CAP_STYLE, text, v21_mark(), " · ", can_data(why))

    def cap(self, *kids):
        return h("div", CAP_STYLE, *kids)

    def can(self, v, why):
        return can_data((getattr(v, "note", None) if v is not None else None) or why)

    # ── giá / quy đổi ──
    def last(self):
        return self._get("last", "last_price", self.tk) or {}

    def raw(self):
        return self.last().get("raw")

    def _ratios(self):
        """(ph, f, fix): f[i] = closeAdj/close của phiên i. Vendor phải cho f = 1 ở phiên cuối; nếu lệch (MSR từ
        16/09: adj/raw 25/09 = 1,0128) thì chuỗi điều chỉnh sau đoạn ổn định cuối cùng là hỏng → sau GDKHQ dùng
        giá thô (f = 1), trước đó giữ hệ số vendor. fix = {brk, k, last, stable} hoặc None."""
        if "ratios" in self._cache:
            return self._cache["ratios"]
        ph, out = self._get("ph", "price_history", self.tk), None
        if ph and str(getattr(ph, "base", "")).startswith("vc_lk") and len(ph):
            C_, A_ = ph.col("closePrice"), ph.col("closePriceAdjusted")
            f = [A_[i] / C_[i] if is_num(C_[i]) and is_num(A_[i]) and C_[i] else None for i in range(len(ph))]
            last = next((x for x in reversed(f) if x is not None), None)
            fix = None
            if last is not None and abs(last - 1) > ADJ_TOL:
                k = next((i for i in range(len(f) - 1, 1, -1) if None not in (f[i], f[i - 1], f[i - 2])
                          and abs(f[i] / f[i - 1] - 1) < 1e-4 and abs(f[i - 1] / f[i - 2] - 1) < 1e-4), None)
                if k is not None and k < len(f) - 1:
                    fix = {"brk": ph.dates[k + 1], "k": k, "last": last, "stable": f[k]}
                    f = f[:k + 1] + [1.0] * (len(f) - k - 1)
            out = (ph, f, fix)
        self._cache["ratios"] = out
        return out

    def adj_fix(self):
        r = self._ratios()
        return r[2] if r else None

    def _adjc(self, i):
        """Giá đóng cửa điều chỉnh phiên i (đã sửa chuỗi vendor hỏng)."""
        ph, _, fix = self._ratios()
        v = ph.col("closePrice")[i] if fix and i > fix["k"] else ph.col("closePriceAdjusted")[i]
        return v if is_num(v) else None

    def factor(self):
        if "f08" in self._cache:
            return self._cache["f08"]
        v = self._get("f08_raw", "adj_factor", self.tk, V21_DATE)
        rs, Vc = self._ratios(), getattr(self.D, "V", None)
        if rs and rs[2] and Vc is not None:
            ph, f, fix = rs
            i0 = ph.at(V21_DATE)
            if i0 >= 0 and f[i0] is not None:
                v = Vc(f[i0], to_fixed(f[i0], 4), "EST", ph.dates[-1],
                       "vc_lk/%s/price-history.closePriceAdjusted/closePrice (sửa)" % self.tk,
                       "adj/raw vendor phiên cuối %s ≠ 1 → sau GDKHQ %s dùng giá thô" % (
                           to_fixed(fix["last"], 4), ddmm(fix["brk"])), "x")
        self._cache["f08"] = v
        return v

    def factor_steps(self):
        """[(ngày, bước, loại)] của hệ số 08/05→cuối (adj_steps; chuỗi hỏng → một bước tại ngày GDKHQ)."""
        fix = self.adj_fix()
        rs = self._ratios()
        if fix:
            steps = list(self._get("steps_pre", "adj_steps", self.tk, V21_DATE, rs[0].dates[fix["k"]]) or [])
            steps.append((fix["brk"], fix["stable"]))
        else:
            steps = list(self._get("steps", "adj_steps", self.tk, V21_DATE) or [])
        ce = self._get("ce_all", "capital_events", self.tk)
        kinds = {}
        for e in (ce.value if self.ok(ce) else []):
            t = str(e.get("title") or "")
            k = ("cổ tức tiền" if e.get("code") == "DIV" else "thưởng CP" if re.search(r"thưởng", t, re.I) else
                 "cổ tức CP" if re.search(r"cổ tức bằng cổ phiếu", t, re.I) else None)
            if k and e.get("exright"):
                kinds.setdefault(e["exright"], k)
        return [(d, s, kinds.get(d, "sự kiện quyền")) for d, s in steps]

    def factor_line(self):
        """'Hệ số quyền 08/05→25/09: ×0.9630 (cổ tức tiền 29/06) × ×0.5000 (cổ tức CP 06/08) = ×0.4815' (E)."""
        f = self.factor()
        if not self.ok(f) or abs(f.value - 1) <= 0.005:
            return None
        steps = self.factor_steps()
        parts = ("×" + " × ".join("%s (%s %s)" % (to_fixed(s, 4), k, ddmm(d)) for d, s, k in steps)) if steps else "—"
        fix = self.adj_fix()
        return h("div", {"fontSize": 9.5, "color": C.inkM, "marginTop": 4, "fontFamily": F_MONO},
                 "Hệ số quyền %s→%s: %s = ×%s" % (ddmm(V21_DATE), ddmm(f.asof), parts, f.text), tier("EST", f.asof),
                 (" · ⚑ chuỗi giá điều chỉnh của vendor lệch từ %s (adj/raw phiên cuối %s ≠ 1) — sau GDKHQ dùng giá "
                  "thô; đề xuất lõi kiểm adj/raw ≤ 1 ở phiên cuối" % (ddmm(fix["brk"]), to_fixed(fix["last"], 4)))
                 if fix else None)

    def conv(self, k):
        """Mốc V21 (nghìn đ, cơ sở 08/05) → (giá trị K hiện hành, đã đổi?)."""
        f = self.factor()
        if not is_num(k) or not self.ok(f):
            return None, False
        return k * f.value, abs(f.value - 1) > 0.005

    def level(self, key, ph):
        k = ph.get(key)
        if not is_num(k):
            return [jsv(k, key not in ph) + "K", v21_mark()]
        cv, changed = self.conv(k)
        if cv is None:
            return [jsv(k) + "K", v21_mark(), can_data("chưa quy đổi được quyền")]
        if changed:
            return [to_fixed(cv, 1) + "K", tier("EST", self.factor().asof)]
        return [jsv(k) + "K", v21_mark()]

    def level_sub(self, key, ph, orig):
        k = ph.get(key)
        cv, changed = self.conv(k)
        if changed:                             # nhãn Stat V21 nguyên văn (upside/entry zone/exit downside) + dấu V21
            return [orig, v21_mark(), " · mốc V21 %sK ×%s" % (jsv(k), self.factor().text)]
        return orig

    def basis_note(self):
        f = self.factor()
        if self.ok(f) and abs(f.value - 1) > 0.005:
            return h("span", {"color": C.ochre, "fontWeight": 400, "letterSpacing": ".05em", "marginLeft": 6},
                     "· cơ sở giá 08/05 — nhân ×%s để so với giá %s" % (f.text, ddmm(f.asof)), tier("EST", f.asof))
        return None

    def _adj_series(self, since):
        rs = self._ratios()
        if not rs:
            return []
        ph = rs[0]
        return [(d, c) for d, c in ((ph.dates[i], self._adjc(i)) for i in range(len(ph))) if d > since and is_num(c)]

    def level_eval(self, ph):
        """(d) HI/STOP V21 chấm lại bằng giá đóng cửa điều chỉnh 12/05→phiên cuối: chạm HI trước → ĐẠT, chạm STOP
        trước → BỊ BÁC, chưa chạm → LIVE; giá lúc chốt đã ngoài dải → CHƯA RÕ (kèm hai mốc chạm theo cùng thang).
        Chỉ đo mốc; nhận định pha/sizing không chấm lại."""
        hi, st = self.conv(ph.get("hi"))[0], self.conv(ph.get("stop"))[0]
        ser = self._adj_series(V21_SET)
        if hi is None or st is None or not ser:
            return h("div", {**LIVE_BOX, "marginTop": 12},
                     h("strong", {"color": C.ink2}, "↻ Chấm lại mốc V21:"), " ",
                     can_data("thiếu chuỗi giá điều chỉnh vc_lk hoặc hệ số quyền"))
        rs = self._ratios()
        i0 = rs[0].at(V21_DATE)
        p0 = (self._adjc(i0), rs[0].dates[i0]) if i0 >= 0 else (None, None)   # giá điều chỉnh lúc trang chốt (08/05)
        t_hi = next(((d, c) for d, c in ser if c >= hi * 1000), None)
        t_st = next(((d, c) for d, c in ser if c <= st * 1000), None)
        mx = max(ser, key=lambda x: x[1])
        mn = min(ser, key=lambda x: x[1])
        last = ser[-1]
        f = self.factor()
        if is_num(p0[0]) and not (st * 1000 < p0[0] < hi * 1000):
            scale = ("theo thang ×%s: " % f.text) if self.ok(f) else ""
            touch = "; ".join(x for x in (
                ("đã trên HI %sK từ %s" % (to_fixed(hi, 1), ddmm(t_hi[0]))) if t_hi else "chưa chạm HI %sK" % to_fixed(hi, 1),
                ("thủng STOP %sK ngày %s (%s)" % (to_fixed(st, 1), ddmm(t_st[0]), k1(t_st[1]))) if t_st
                else "chưa chạm STOP %sK" % to_fixed(st, 1)) if x)
            status, ev = "CHƯA RÕ", "mốc V21 lệch giá lúc chốt: giá %s (%s) đã %s — mốc sai thang, không đo được · %s%s" % (
                k1(p0[0]), ddmm(p0[1]), "trên HI %sK" % to_fixed(hi, 1) if p0[0] >= hi * 1000
                else "dưới STOP %sK" % to_fixed(st, 1), scale, touch)
        elif t_hi and (not t_st or t_hi[0] <= t_st[0]):
            status, ev = "ĐẠT", "chạm HI %sK ngày %s (đóng cửa điều chỉnh %s)" % (to_fixed(hi, 1), ddmm(t_hi[0]), k1(t_hi[1]))
        elif t_st:
            status, ev = "BỊ BÁC", "chạm STOP %sK ngày %s (đóng cửa điều chỉnh %s) trước HI" % (
                to_fixed(st, 1), ddmm(t_st[0]), k1(t_st[1]))
        else:
            status, ev = "LIVE", "chưa chạm HI %sK / STOP %sK" % (to_fixed(hi, 1), to_fixed(st, 1))
        note = ((self.dos or {}).get("level_note") if self.dos else None) or None
        return h("div", {**LIVE_BOX, "marginTop": 12},
                 h("strong", {"color": C.ink2}, "↻ Chấm lại mốc HI/STOP V21 bằng giá điều chỉnh %s→%s:" % (
                     ddmm(V21_SET), ddmm(last[0]))), " ", status_pill(status), " ", ev,
                 " · đỉnh %s (%s) · đáy %s (%s) · cuối %s" % (k1(mx[1]), ddmm(mx[0]), k1(mn[1]), ddmm(mn[0]), k1(last[1])),
                 tier("EST", last[0]), upd_mark(),
                 h("div", {"marginTop": 4}, "↻ ", rich(note.get("text")), tier(note.get("tier"), note.get("asof"))
                   if note.get("tier") else None, upd_mark()) if isinstance(note, dict) and note.get("text") else None,
                 self.factor_line(),
                 h("div", {"fontSize": 9.5, "color": C.inkM, "marginTop": 4, "fontFamily": F_MONO},
                   "Chỉ đo mốc giá; pha/stance/sizing V21 không chấm lại (CỔNG v1.7 %s)." % (
                       "đang DỪNG" if self.cong_stop else "chưa mở cho per-mã")))

    # ── 02 chart ──
    def chart(self, T):
        w = self._get("wk", "weekly_ohlcv", self.tk)
        if not self.ok(w) or len(w.value) <= 10:
            return None
        rows = w.value[-105:]
        fix = self.adj_fix()                    # chuỗi điều chỉnh vendor hỏng sau GDKHQ → tuần đó dùng giá thô

        def close_of(r):
            c = r.get("c_raw") if fix and str(r.get("week_end") or "") >= fix["brk"] else r.get("c")
            return c / 1000 if is_num(c) else None
        bars = [{"date": r["label"], "close": close_of(r),
                 "vol": r["vol"] / 1e6 if is_num(r.get("vol")) else None,
                 "vwap6m": r["vwap6"] / 1000 if is_num(r.get("vwap6")) else None,
                 "vwap12m": r["vwap12"] / 1000 if is_num(r.get("vwap12")) else None,
                 "vwap24m": r["vwap24"] / 1000 if is_num(r.get("vwap24")) else None} for r in rows]
        bars = [b for b in bars if is_num(b["close"])]
        if len(bars) <= 10:
            return None
        ph = (T.deep or {}).get("phase") or {}
        anchor = ((T.deep or {}).get("cluster") or {}).get("anchor")
        levels = {}
        for key, lab, v in (("hi", "HI", ph.get("hi")), ("base", "BASE", ph.get("base")),
                            ("stop", "STOP", ph.get("stop")), ("anchor", "ANCHOR", anchor)):
            if not truthy(v) or not is_num(v):
                continue
            cv, changed = self.conv(v)
            if cv is None:
                continue
            levels[key] = (cv, "%s %sK (V21%s)" % (lab, to_fixed(cv, 1) if changed else jsv(v),
                                                  " %sK quy đổi" % jsv(v) if changed else ""))
        last = bars[-1]
        lr = rows[-1]
        eyebrow = ("WEEKLY OHLCV + VWAP 6M/12M/24M · %s · %d weeks (vc_lk giá điều chỉnh quyền · %s→%s)"
                   % (self.tk, len(bars), ddmmyyyy(bars[0]["date"]), ddmmyyyy(lr.get("week_end"))))
        ro = ["CLOSE %s: " % ddmm(lr.get("week_end")), h("strong", {"color": C.gold}, to_fixed(last["close"], 1) + "K"),
              tier("FACT-T2", lr.get("week_end")), " · "]
        for lab, key, col in (("VWAP6M", "vwap6m", C.forest), ("VWAP12M", "vwap12m", C.ochre),
                              ("VWAP24M", "vwap24m", C.vermillion)):
            v = last.get(key)
            ro += [lab + " ", h("strong", {"color": col}, to_fixed(v, 1) + "K") if is_num(v) else can_data()]
            ro += [tier("EST") if is_num(v) else None, " · " if key != "vwap24m" else None]
        label = [ph.get("label") if truthy(ph.get("label")) else ph.get("id"), v21_mark() if ph else None]
        legend = ("━ Close (điều chỉnh) · ─ VWAP6M (green) · ─ VWAP12M (amber) · ─ ─ VWAP24M (red) · ▮ Volume (KL khớp) · "
                  "%d weeks" % len(bars))
        return mode_a(self.tk, bars, ph, anchor, eyebrow=eyebrow, readout=ro, label=label, legend=legend,
                      levels=levels)

    def vwap_label_line(self):
        vc = self._get("vc", "vwap_cluster", self.tk) or {}
        parts = []
        for n in (6, 12, 24):
            v = vc.get("v%d" % n)
            parts += ["%dT " % n, (to_fixed(v.value, 1) + "K") if self.ok(v) else can_data(), " · " if n != 24 else None]
        nh = VWAP_NHAN.get(vc.get("nhan"), vc.get("nhan") or "—")
        v6 = vc.get("v6")
        vn = str(getattr(v6, "src", "") or "").startswith("vnstore")        # mã chưa có vc_lk: giá trộn → U
        return [h("br"), h("br"), h("strong", {"color": C.ink2}, "↻ VWAP cụm lăng kính (%s, %s):" % (
            "vnstore nen_ngay, giá trộn" if vn else "vc_lk", ddmm(getattr(v6, "asof", None)))), " ", parts, " — nhãn: ",
            nh, tier("UNVERIFIED" if vn else "EST", getattr(v6, "asof", None))]

    # ── 03 ──
    def price_stat(self):
        r = self.raw()
        if not self.ok(r):
            return can_data(), (getattr(r, "note", None) or "chưa có giá vc_lk")
        return [k1(r.value), tier(r.tier, r.asof)], ddmmyyyy(r.asof)

    def perf60_stat(self):
        ph = self._get("ph", "price_history", self.tk)
        if not ph or len(ph) < 61:
            return can_data(), "thiếu 61 phiên giá", C.vermillion
        d0 = ph.dates[-61]
        if self.adj_fix():                      # chuỗi điều chỉnh vendor hỏng → tính trên chuỗi đã sửa
            a, b = self._adjc(len(ph) - 61), self._adjc(len(ph) - 1)
            if not (is_num(a) and is_num(b) and a):
                return can_data(), "thiếu giá điều chỉnh", C.vermillion
            x, asof = (b / a - 1) * 100, ph.dates[-1]
        else:
            p = self._get("p60", "pct_change", self.tk, d0)
            if not self.ok(p):
                return can_data(), "thiếu giá điều chỉnh", C.vermillion
            x, asof = p.value, p.asof
        return ([sign_fixed(x, 1, strict=True, zfix=True) + "%", tier("EST", asof)], "vs 60 phiên (%s)" % ddmm(d0),
                C.forest if x > 0 else C.vermillion)

    def sig_stat(self, flow):
        sig = (flow or {}).get("sig")
        return can_data(), ("4 kênh thiếu CN/TC · V21·12/05: %s" % sig) if sig else "4 kênh thiếu CN/TC · V21: không có FLOW"

    # ── 04 ──
    def vwap_live_table(self):
        vc = self._get("vc", "vwap_cluster", self.tk) or {}
        r = self.raw()
        px = k1(r.value) if self.ok(r) else None
        rows = []
        for n in (6, 12, 24):
            v, kc = vc.get("v%d" % n), vc.get("kc%d" % n)
            rows.append(h("tr", TR_ROW,
                          h("td", {"padding": "8px", "color": C.ink}, "VWAP %dT" % n),
                          h("td", {"padding": "8px", "textAlign": "right", "color": C.ink2, "fontWeight": 700},
                            [to_fixed(v.value, 2), tier("EST", v.asof)] if self.ok(v) else can_data()),
                          h("td", {"padding": "8px", "color": C.inkD, "fontSize": 10.5},
                            ["Giá %s · cách " % px, sign_fixed(kc.value, 1, strict=True, zfix=True) + "%",
                             tier("EST", kc.asof)]
                            if px and self.ok(kc) else can_data()),
                          h("td", {"padding": "8px"}, VWAP_NHAN.get(vc.get("nhan"), vc.get("nhan")) or can_data())))
        th = lambda t, al: h("th", {"padding": "6px 8px", "textAlign": al, "color": C.inkD, "fontSize": 9}, t)  # noqa
        return h("div", None,
                 h("div", {"fontSize": 9, "letterSpacing": ".2em", "color": C.ink2, "fontFamily": F_MONO,
                           "marginBottom": 10, "fontWeight": 700},
                   "↻ VWAP CỤM 6T/12T/24T — vc_lk tới %s (Σ giá điều chỉnh × KL/cp, EST)" % ddmmyyyy(
                       getattr(vc.get("v6"), "asof", None)), upd_mark()),
                 h("table", {"width": "100%", "borderCollapse": "collapse", "fontFamily": F_MONO, "fontSize": 11,
                             "marginBottom": 14},
                   h("thead", None, h("tr", TR_HEAD, th("PERIOD", "left"), th("VAL (K)", "right"), th("STATUS", "left"),
                                      th("LABEL", "left"))),
                   h("tbody", None, *rows)))

    # ── 05 ──
    def codong_table(self):
        cm = self._get("cm", "codong_moc", self.tk)
        cap = self.cap("↻ SỐ CỔ ĐÔNG — Toàn Vũ (lk_hoso.codong.moc); chỉ điểm quan sát dùng để tính", upd_mark())
        if not self.ok(cm):
            return self.spaced(Card(cap, h("p", {"margin": 0, "fontSize": 11.5, "color": C.inkD},
                               self.can(cm, "ngoài 30 mã Toàn Vũ — số cổ đông chờ OCR BCTN")),
                        key="deep10_codong_live"))
        rows = []
        moc = cm.value
        recent = [m for m in moc if str(m.get("ky") or "") >= "2023-01"] or moc[-6:]
        for m in recent:
            ky = str(m.get("ky") or "")
            rows.append(h("tr", TR_ROW,
                          h("td", {"padding": "8px 10px", "color": C.ink, "fontWeight": 600}, ky[5:7] + "/" + ky[:4]),
                          h("td", {"padding": "8px 10px", "textAlign": "right", "color": C.gold, "fontWeight": 700,
                                   "fontFamily": F_MONO},
                            "chưa có số mới" if m.get("cf") else to_locale(m.get("v"), "en", max_frac=0) if is_num(m.get("v"))
                            else can_data(), tier(m.get("tier") or "SS-T3") if not m.get("cf") else None),
                          h("td", {"padding": "8px 10px", "color": C.inkD, "fontSize": 11},
                            KIEU_VI["chep"] if m.get("cf") else vi_label(m.get("kieu")))))
        th = lambda t, al: h("th", {"padding": "8px 10px", "textAlign": al, "color": C.inkD, "fontSize": 9,  # noqa
                                    "letterSpacing": ".18em", "fontFamily": F_MONO}, t)
        return self.spaced(Card(cap, h("table", {"width": "100%", "borderCollapse": "collapse", "fontFamily": F_SERIF,
                                     "fontSize": 11.5},
                           h("thead", None, h("tr", TR_HEAD, th("KỲ", "left"), th("SỐ CỔ ĐÔNG", "right"),
                                              th("KIỂU", "left"))),
                           h("tbody", None, *rows)),
                    h("div", {"fontSize": 9.5, "color": C.inkM, "marginTop": 6, "fontFamily": F_MONO},
                      self.codong_note(moc), " · hiện %d/%d mốc từ 01/2023 (đủ chuỗi ở lk_hoso)" % (len(recent), len(moc))),
                    key="deep10_codong_live"))

    @staticmethod
    def codong_note(moc):
        """Chú thích bảng Toàn Vũ — cùng luật với dòng lăng kính của tab (codong_summary)."""
        obs, last, n_cf = codong_summary(moc)
        return "quan sát cuối %s; CF %d kỳ%s" % (ky_vi(obs.get("ky")) if obs else "—", n_cf,
                                                 "; CF — chưa có số mới" if last and last.get("cf") else "")

    # ── 06 ──
    def holders_live(self):
        th = self._get("th", "top_holders", self.tk, 10)
        cap = self.cap("↻ CỔ ĐÔNG LỚN — vc_lk shareholder (FACT-T2); % tại ngày công bố từng dòng, khác kỳ không "
                       "cộng được. Capital IQ của bản V21 lấy trên máy cũ (Q4/25) — không làm mới.", upd_mark())
        if not self.ok(th):
            return self.spaced(Card(cap, self.can(th, "không có vc_lk shareholder"), key="deep10_holders_live"))
        thh = lambda t, al: h("th", {"padding": "8px 10px", "textAlign": al, "color": C.inkD, "fontSize": 9,  # noqa
                                     "letterSpacing": ".18em"}, t)
        rows = []
        for it in th.value:
            q, p = it.get("qty"), it.get("pct_pub")
            rows.append(h("tr", TR_ROW,
                          h("td", {"padding": "9px 10px", "color": C.ink, "fontFamily": F_SERIF, "fontSize": 11},
                            it.get("name")),
                          h("td", {"padding": "9px 10px", "textAlign": "right", "color": C.gold, "fontWeight": 700},
                            [to_fixed(q.value / 1e6, 2) + "M", tier(q.tier, q.asof)] if self.ok(q) else can_data()),
                          h("td", {"padding": "9px 10px", "textAlign": "right", "color": C.ink2},
                            [to_fixed(p.value, 2) + "%", tier(p.tier, p.asof)] if self.ok(p) else can_data()),
                          h("td", {"padding": "9px 10px", "color": C.inkD, "fontSize": 10, "fontStyle": "italic"},
                            it.get("position") or it.get("type"), " · cũ >12T" if it.get("old") else None)))
        return self.spaced(Card(cap, h("table", {"width": "100%", "borderCollapse": "collapse", "fontFamily": F_MONO,
                                     "fontSize": 10.5},
                           h("thead", None, h("tr", TR_HEAD, thh("HOLDER", "left"), thh("SHARES", "right"),
                                              thh("PCT", "right"), thh("TYPE", "left"))),
                           h("tbody", None, *rows)),
                    h("div", {"fontSize": 9.5, "color": C.inkM, "marginTop": 6, "fontFamily": F_MONO}, th.note),
                    key="deep10_holders_live"))

    # ── 06b ──
    def flow_view(self):
        if "fv" not in self._cache:
            self._cache["fv"] = flow_view(self._get("f4", "flow4", self.tk, 60),
                                          self._get("pn", "prop_net", self.tk, 60, kind="khop"),
                                          self._get("pt", "prop_net", self.tk, 60, kind="total"))
        return self._cache["fv"]

    def flow_sub(self):
        fv = self.flow_view()
        return ["FiinTrade ≤08/05 đóng băng · %s: NN + tự doanh vc_lk (T2); Cá nhân/Tổ chức " % win_label(fv),
                can_data()]

    def flow_live_rows(self, has_v21=True):
        fv = self.flow_view()
        win = win_label(fv)
        nn, td, du = fv["nn"], fv["td"], fv["du"]
        n_txt = "%s/%s phiên" % (fv["n_co"], fv["n"]) if isinstance(fv["n_co"], int) else None
        td_stat = (Stat("TỰ DOANH (khớp)", [mcp(td), tier(td.tier, fv["td_last"] or td.asof)],
                        sub="%s · tới %s · %s" % (n_txt, ddmm(fv["td_last"]), win) if fv["td_last"] else win,
                        color=C.forest if td.value > 0 else C.vermillion) if td else
                   Stat("TỰ DOANH (khớp)", can_data(), sub=[fv["td_why"], " · ", win], color=C.vermillion))
        nn_stat = (Stat("NƯỚC NGOÀI (khớp+TT)", [mcp(nn), tier(nn.tier, nn.asof)], sub=win,
                        color=C.forest if nn.value > 0 else C.vermillion) if nn else
                   Stat("NƯỚC NGOÀI (khớp+TT)", can_data(), sub=["thiếu foreignNet · ", win], color=C.vermillion))
        grid = h("div", {"display": "grid", "gridTemplateColumns": "repeat(4,1fr)", "gap": 12, "marginBottom": 10},
                 Stat("CÁ NHÂN", can_data(), sub="không có nguồn sau 08/05 · " + win, color=C.vermillion),
                 Stat("TỔ CHỨC", can_data(), sub="không có nguồn sau 08/05 · " + win, color=C.vermillion),
                 td_stat, nn_stat)
        res = h("div", {"fontSize": 10.5, "color": C.inkD, "marginBottom": 10, "fontFamily": F_MONO},
                "Phần dư −(NN tổng + TD tổng) = ",
                [sign_fixed(du.value, 1, zfix=True) + "M cp", tier("EST", du.asof),
                 " (NN tới %s, TD tới %s)" % (ddmm(nn.asof), ddmm(fv["td_last"] or td.asof))] if du else
                can_data("tự doanh thiếu phiên (%s) — không tính phần dư" % fv["td_why"]),
                " — phần dư, không phải kênh thật (CN + TC gộp, không tách được).")
        box = h("div", {"padding": "10px 14px", "background": C.ochre + "15", "border": "2px solid " + C.ochre,
                        "borderRadius": 3, "fontSize": 11.5, "color": C.ink, "lineHeight": 1.7},
                h("strong", None, "SIGNAL %s: " % win), can_data("thiếu kênh Cá nhân/Tổ chức — không tính lại"),
                " · NN/TD thật ở trên" + ("; tín hiệu V21 giữ nguyên ở khối FiinTrade." if has_v21 else "."))
        return [h("div", {"marginTop": 16, **CAP_STYLE}, "↻ %s — vc_lk (NN gồm thoả thuận; TD = tự doanh khớp)" % win,
                  upd_mark()), grid, res, box]

    def flow_only_live(self):
        """HDB (V21 không có FLOW): v21 để trống; live hiện riêng phần NN/TD sống."""
        body = [self.cap("V21 không có FLOW cho %s — FiinTrade ≤08/05: " % self.tk, can_data())] + \
            self.flow_live_rows(has_v21=False)
        return Section("★ 06b FiinTrade Pillar IV — 4-channel Flow 60d", Card(*body), accent=C.forest,
                       sub=self.flow_sub(), if_={SUB_KEY: "flow"}, key="deep10_flow")

    # ── 07 ──
    def legal_caveat(self):
        st = (self.T.deep or {}).get("strategic") or {}
        text = " ".join([str(st.get("thesis") or "")] + [str(p.get("d") or "") + str(p.get("h") or "")
                                                         for p in st.get("pillars") or []])
        if not LEGAL_RE.search(text):
            return None
        return h("div", {"marginTop": 10, "fontSize": 10, "color": C.inkD, "lineHeight": 1.6, "fontFamily": F_MONO},
                 "⚠ Mệnh đề chính trị/pháp lý nêu tên cá nhân trong bản V21: ", tier("UNVERIFIED"),
                 " chưa có văn bản FACT-T1 trong kho — không trình bày như sự thật đã xác lập, không thêm cáo buộc mới.")

    def legal_texts(self):
        """Chuỗi V21 của khối Deep-dive có thể nêu tên cá nhân kèm mệnh đề tố tụng (phase/holders/events/strategic/action)."""
        d = self.T.deep or {}
        out = [str((d.get("phase") or {}).get("note") or "")]
        out += [str(x.get("name") or "") + " " + str(x.get("type") or "") for x in d.get("holders") or []]
        out += [str(x.get("t") or "") + " " + str(x.get("d") or "") for x in d.get("events") or []]
        st = d.get("strategic") or {}
        out += [str(st.get("thesis") or "")] + [str(p.get("h") or "") + " " + str(p.get("d") or "")
                                                 for p in st.get("pillars") or []]
        out += [str(r.get("t") or "") + " " + str(r.get("d") or "") for r in (d.get("action") or {}).get("risks") or []]
        return [t for t in out if t.strip()]

    def legal_banner(self):
        """Banner cấp khối Deep-dive (phủ mọi sub-tab) khi bản V21 nêu tên cá nhân kèm khởi tố/phong toả: U + caveat;
        dossier deep10.legal_note (vd DGC: CBTT không nêu tên — FACT-T1) hiện kèm bậc."""
        if not any(LEGAL_NAME_RE.search(t) for t in self.legal_texts()):
            return None
        note = (self.dos or {}).get("legal_note") if self.dos else None
        return h("div", {"marginBottom": 12, "padding": "8px 14px", "background": C.vermillion + "10",
                         "border": "1px solid " + C.vermillion + "40", "borderRadius": 3, "fontSize": 10.5,
                         "color": C.inkD, "lineHeight": 1.65},
                 h("strong", {"color": C.vermillion}, "⚠ Mệnh đề pháp lý nêu tên cá nhân (bản V21·12/05): "),
                 "tên người gắn với khởi tố/phong toả ở các sub-tab dưới đây là mệnh đề V21/báo chí", tier("UNVERIFIED"),
                 " — chưa đối chiếu FACT-T1; không dùng cho quyết định, không thêm cáo buộc mới.",
                 [" ↻ ", rich(note.get("text")), tier(note.get("tier"), note.get("asof")) if note.get("tier") else None,
                  upd_mark()] if isinstance(note, dict) and note.get("text") else None, key="deep10_legal")

    def legal_mark(self, text):
        """Nhãn U ngay sau câu/ô V21 nêu tên cá nhân kèm mệnh đề tố tụng (không có văn bản FACT-T1 trong kho)."""
        return tier("UNVERIFIED") if text and LEGAL_NAME_RE.search(str(text)) else None

    # ── 08 ──
    def events_caption(self):
        return self.cap("↻ Hàng đầu: sự kiện 09/05→%s (dữ kiện FACT-T1/T2 + vc_lk sự kiện vốn/nội bộ, mới → cũ) · phần "
                        "dưới: bản lưu V21·12/05, sự kiện đã tới hạn có trạng thái chấm lại; dữ kiện trước 09/05 xếp "
                        "sau bản lưu" % ddmm(getattr(self.raw(), "asof", None) or "2026-09-25"), upd_mark())

    def _ev_items(self):
        if self.dos and isinstance(self.dos.get("events_new"), list):
            return self.dos["events_new"]
        if self.D is None:
            return []
        try:
            return [fact_item(f) for f in route_facts(self.D, self.tk).get("events", [])]
        except Exception as exc:
            self.ctx.warn("deep10 %s: route_facts lỗi %s" % (self.tk, exc))
            return []

    def _ev_all(self):
        """[(ngày ISO, hàng)] của mọi dòng ↻ (dossier/dữ kiện + sự kiện vốn + nội bộ), sắp mới → cũ."""
        if "ev_all" in self._cache:
            return self._cache["ev_all"]
        from chaebol_map_tab_codong_deep import event_row
        out = []
        for it in self._ev_items():
            txt = it.get("text") or ""
            m = re.match(r"(.{20,160}?[.;:])\s(.+)$", txt)
            t, d = (m.group(1), m.group(2)) if m else (txt, "")
            st = cap_status(it.get("status"), it.get("tier"))
            sev = "rose" if st == "BỊ BÁC" else "amber" if st == "CHƯA RÕ" else "emerald" if it.get("tier") == "FACT-T1" \
                else "cyan"
            out.append((str(it.get("asof") or ""), event_row(
                {"date": ddmmyyyy(it.get("asof")), "cat": "↻ " + LOAI_VI.get(it.get("loai"), "dữ kiện"),
                 "sev": sev, "t": rich(t), "d": rich(d) if d else ""},
                extra_cat=[h("br"), status_pill(st)] if st else None,
                extra_t=[tier(it.get("tier"), it.get("asof")), upd_mark()])))
        ce = self._get("ce", "capital_events", self.tk, since=V21_CUT, by="public")   # hàng mang ngày công bố
        for e in (ce.value if self.ok(ce) else [])[:6]:
            ratio = e.get("ratio_text") if e.get("ratio") not in (None, 0, 0.0) else None   # vendor ghi 0/null = không có tỉ lệ
            d = " · ".join(x for x in (ratio, ("GDKHQ " + ddmmyyyy(e["exright"])) if e.get("exright")
                                       else None, ("niêm yết " + ddmmyyyy(e["listing"])) if e.get("listing") else None) if x)
            out.append((str(e.get("public_date") or ""), event_row(
                {"date": ddmmyyyy(e.get("public_date")), "cat": "↻ vốn · " + str(e.get("code")), "sev": "cyan",
                 "t": e.get("title"), "d": d}, extra_t=[tier("FACT-T2", e.get("public_date")), upd_mark()])))
        it_ = self._get("ins", "insider_tx", self.tk, since=V21_CUT)
        for e in (it_.value if self.ok(it_) else [])[:6]:
            acq = e.get("acquire")
            d = "%s · thực hiện %s cp · sở hữu sau %s%% (không có giá giao dịch)" % (
                e.get("status_vi") or e.get("status") or "", to_locale(acq, "en") if is_num(acq) else "—",
                to_fixed(e["own_after_pct"], 2) if is_num(e.get("own_after_pct")) else "—")
            out.append((str(e.get("public_date") or ""), event_row(
                {"date": ddmmyyyy(e.get("public_date")), "cat": "↻ nội bộ",
                 "sev": "rose" if e.get("action") == "S" else "emerald", "t": e.get("title"), "d": d},
                extra_t=[tier("FACT-T2", e.get("public_date")), upd_mark()])))
        out.sort(key=lambda x: x[0], reverse=True)          # sort ổn định: cùng ngày giữ thứ tự nguồn
        self._cache["ev_all"] = out
        return out

    def events_new_rows(self):
        """Hàng đầu bảng 08: chỉ sự kiện/dữ kiện từ 09/05, mới → cũ."""
        return [r for d, r in self._ev_all() if d >= V21_CUT]

    def events_old_rows(self):
        """Dữ kiện ↻ có ngày trước 09/05 (thay mệnh đề V21 cũ) — xếp sau bản lưu V21, có hàng phân cách."""
        old = [r for d, r in self._ev_all() if d < V21_CUT]
        if not old:
            return []
        sep = h("tr", TR_HEAD, h("td", {"padding": "7px 9px", "color": C.inkM, "fontSize": 9, "letterSpacing": ".1em"},
                                  "— ↻ dữ kiện trước 09/05/2026 (thay mệnh đề V21, không phải sự kiện mới) —", upd_mark(),
                                  a={"colSpan": 3}))
        return [sep] + old

    def event_v21_row(self, i, r):
        from chaebol_map_tab_codong_deep import event_row
        st = ((self.dos or {}).get("v21_events_status") or {}).get(str(i)) if self.dos else None
        if st is None and (self.T.deep or {}).get("events"):
            st = auto_event_status(r.get("date"))
        lm = self.legal_mark(str(r.get("t") or "") + " " + str(r.get("d") or ""))
        if not st:
            return event_row(r, extra_t=[lm]) if lm else event_row(r)
        pill = cap_status(st.get("status"), st.get("tier")) if st.get("tier") else st.get("status")
        return event_row(r, extra_cat=[h("br"), status_pill(pill)], extra_t=[lm] if lm else None,
                         extra_d=[h("div", {"color": C.ink2, "marginTop": 3}, "↻ ", st.get("evidence"),
                                        tier(st.get("tier"), st.get("asof")) if st.get("tier") else None, upd_mark())])

    # ── 09 ──
    def patterns_live(self):
        pt = self._get("pt", "patterns", self.tk)
        view = self._get("lv", "lk_view", self.tk) or {}
        cap = self.cap("↻ PATTERN MÁY — NTH lk_mauhinh (bậc chép theo atom nguồn, thường T3; nhãn luôn '?'; mã ngoài 30 "
                       "Toàn Vũ bắt buộc '?')", upd_mark())
        if not self.ok(pt) or not pt.value:
            return self.spaced(Card(cap, self.can(pt, "không có lk_mauhinh"), key="deep10_patterns_live"))
        th = lambda t, w=None: h("th", {"padding": "8px", "textAlign": "left", "color": C.inkD, "fontSize": 9,  # noqa
                                        "fontFamily": F_MONO, "width": w}, t)
        rows = []
        for m in pt.value:
            rows.append(h("tr", TR_ROW,
                          h("td", {"padding": "10px", "color": C.ink, "fontWeight": 600, "fontSize": 11.5}, m.get("label")),
                          h("td", {"padding": "10px", "fontFamily": F_MONO, "fontSize": 10, "color": C.ink2},
                            vi_label(m.get("status")), tier(m.get("tier") or "EST", m.get("status_since"))),
                          h("td", {"padding": "10px", "color": C.inkD, "lineHeight": 1.6, "fontSize": 11},
                            "%s→%s · biết lúc %s. " % (ddmm(m.get("from")), ddmm(m.get("to")), ddmm(m.get("known_at"))),
                            m.get("break"))))
        extra = None
        if view.get("pattern"):
            extra = h("div", {"fontSize": 10, "color": C.inkD, "marginTop": 8, "fontFamily": F_MONO},
                      "Pattern cổ đông (lk_hoso.codong): ", vi_label(view["pattern"]), tier("EST"))
        return self.spaced(Card(cap, h("table", {"width": "100%", "borderCollapse": "collapse", "fontFamily": F_SERIF,
                                     "fontSize": 11.5},
                           h("thead", None, h("tr", TR_HEAD, th("PATTERN", "40%"), th("STATUS", "15%"), th("NOTE"))),
                           h("tbody", None, *rows)), extra, key="deep10_patterns_live"))

    # ── 10 ──
    def action_banner(self):
        r = self.raw()
        px = [k1(r.value), tier(r.tier, r.asof)] if self.ok(r) else can_data("chưa có giá")
        return h("div", {**LIVE_BOX, "marginBottom": 14},
                 h("strong", {"color": C.ink2}, "Bản lưu V21·12/05 — không chấm lại"), v21_mark(),
                 " (CỔNG v1.7 %s). Action cần kiểm chứng: đối chiếu từng trigger với giá " % (
                     "đang DỪNG" if self.cong_stop else "chưa mở cho per-mã"), px,
                 " và mốc đã quy đổi quyền (sub-tab 01); tỷ trọng >5% NAV → Synthesis L1+L2+L3; không có lệnh mua/bán mới.",
                 upd_mark())

    def consensus_box(self, cons):
        vv = self._get("vv", "vietcap_view", self.tk) or {}
        ss = self._get("ss", "sell_side_targets", self.tk)
        live = []
        rt, tp = vv.get("rating"), vv.get("target")
        if self.ok(rt):
            live += ["Vietcap ", rt.value, " · TP ", h("strong", None, (k1(tp.value) + " VND") if self.ok(tp) else "—"),
                     tier(rt.tier, rt.asof), " (quá 90 ngày)" if vv.get("stale") else None]
        for t in (ss.value if self.ok(ss) else []):
            if "Vietcap" in (t.note or "") and self.ok(rt):
                continue
            live += [" · ", t.note or "", " ", h("strong", None, k1(t.value) + " VND") if is_num(t.value) else "—",
                     tier(t.tier, t.asof) if t.tier else None]
        kids = [h("strong", {"color": C.gold}, "★ Sell-side (quan điểm vendor, không phải khuyến nghị của trang):"), " "]
        kids += live if live else [can_data("không có coverage vendor trong kho")]
        if truthy(cons.get("avgTp")):
            kids += [h("br"), "Bản lưu V21 (Simplize, UNVERIFIED — VIC/DGC nghi sai đơn vị): ",
                     "%s MUA / %s BÁN / avg TP %sK" % (cons.get("mua"), cons.get("ban"), to_fixed(cons["avgTp"] / 1000, 1)),
                     tier("UNVERIFIED"), v21_mark()]
        return h("div", {"marginTop": 10, "padding": "10px 14px", "background": C.gold + "10",
                         "border": "1px solid " + C.gold + "30", "borderRadius": 3, "fontSize": 11, "color": C.inkD,
                         "lineHeight": 1.7}, *kids)

    # ── chung ──
    def empty_panel(self, sid, title):
        return Section(title, Card(h("p", {"margin": 0, "fontSize": 11.5, "color": C.inkD, "fontStyle": "italic"},
                                         can_data("V21 không có CHAEBOL_DEEP_DATA cho %s; CỔNG v1.7 %s nên không dựng "
                                                  "pha/cụm mới" % (self.tk, "DỪNG" if self.cong_stop else "chưa mở")))),
                       accent=C.gold, if_={SUB_KEY: sid}, key="deep10_" + sid)

    def _upd_items(self, sid):
        if self.dos is not None:
            return (self.dos.get("updates") or {}).get(sid) or []
        if self.D is None:
            return []
        try:
            return [fact_item(f) for f in route_facts(self.D, self.tk).get(sid, [])]
        except Exception as exc:
            self.ctx.warn("deep10 %s: route_facts lỗi %s" % (self.tk, exc))
            return []

    def updates(self, sid):
        items = self._upd_items(sid)
        if not items:
            return None
        lines = []
        for it in items:
            st = cap_status(it.get("status"), it.get("tier"))
            lines.append(h("div", {"marginTop": 6},
                           status_pill(st) if st else None, " " if st else None, rich(it.get("text")),
                           tier(it.get("tier"), it.get("asof")) if it.get("tier") else None, upd_mark()))
        return h("div", UPD_BOX,
                 h("div", {"fontSize": 9, "letterSpacing": ".2em", "color": C.ochre, "fontFamily": F_MONO,
                           "fontWeight": 700}, "↻ CẬP NHẬT 27/09 — dữ kiện thay mệnh đề V21 (", str(len(items)), ")"),
                 *lines)

    def header_note(self):
        r = self.raw()
        at = ddmm(getattr(r, "asof", None)) if self.ok(r) else "[CẦN DATA]"
        vn = str(getattr(r, "src", "") or "").startswith("vnstore")        # mã chưa có vc_lk: giá trộn → U
        src = (("LIVE · giá: vnstore nen_ngay (giá trộn) tới %s (U) · NN/TD/cổ đông: chưa nạp vc_lk · VWAP, %%: U" % at)
               if vn else "LIVE · giá/NN/TD/cổ đông: vc_lk tới %s (T2) · VWAP, %%, quy đổi quyền: E" % at)
        return h("div", {"marginTop": 10, "fontSize": 9, "color": C.inkM, "letterSpacing": ".05em",
                         "fontFamily": F_MONO, "lineHeight": 1.6},
                 src + " · nhận định V21·12/05 giữ nguyên, không chấm lại (CỔNG v1.7 %s) · ↻ = viết lại theo dữ kiện "
                 "27/09%s" % ("DỪNG" if self.cong_stop else "mở",
                              "" if self.dos is not None else " (dossier chưa có — dùng facts)"))


_Q_END = {"Q1": "03-31", "Q2": "06-30", "Q3": "09-30", "Q4": "12-31"}


def auto_event_status(date_text, today_iso="2026-09-27"):
    """Dự phòng khi dossier chưa chấm: sự kiện V21 hẹn sau 12/05 — đã tới hạn → CHƯA RÕ (kho chưa thấy kết quả);
    chưa tới hạn → LIVE. Không nhận diện được → None (không gắn nhãn)."""
    s = str(date_text or "")
    m = re.search(r"(Q[1-4])/(20\d\d)", s)
    end = None
    if m:
        end = "%s-%s" % (m.group(2), _Q_END[m.group(1)])
    else:
        m = re.match(r"(\d{1,2})/(\d{1,2})/(20\d\d)", s)
        if m:
            end = "%s-%02d-%02d" % (m.group(3), int(m.group(2)), int(m.group(1)))
        elif re.match(r"^20(2[6-9])(E|F)?$|^20\d\d-20\d\d", s):
            y = int(s[:4]) if not re.match(r"^20\d\d-20\d\d", s) else int(s[5:9])
            end = "%d-12-31" % y
    if not end or end <= V21_SET:
        return None
    if end <= today_iso:
        return {"status": "CHƯA RÕ", "evidence": "đã tới hạn %s — kho chưa thấy kết quả" % ddmmyyyy(end)}
    return {"status": "LIVE", "evidence": "chưa tới hạn %s" % ddmmyyyy(end)}
