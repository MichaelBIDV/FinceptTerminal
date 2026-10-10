#!/usr/bin/env python3
"""
chaebol_map_tab_codong_live — lớp live của tab "★ 🏛 CẤU TRÚC CỔ ĐÔNG" (chỉ mode live; chaebol_map_tab_codong gọi).

Luật (DESIGN §0.3, §6; nhiệm vụ codong 27/09): số có nguồn sống → số sống + nhãn bậc (ưu tiên nhãn sẵn có của
lk_hoso); dữ kiện đã đổi → câu viết lại theo dossier cap_nhat_2026-09-27.codong.json (tickers.<MÃ>.codong.*, mỗi
mục tier/asof/src) hoặc facts_f*.json, kèm ↻27/09; stance V21 (basket/tag, story, driver, risk, triết lý…) giữ
nguyên văn + V21·12/05; claim đo được → pill ĐẠT/BỊ BÁC/CHƯA RÕ; không nguồn → [CẦN DATA]. Dòng tiền sau 08/05: chỉ
NN + tự doanh là số thật. Mã ngoài 30 mã Toàn Vũ: pattern có "?", số cổ đông = [CẦN DATA]. Mệnh đề pháp lý nêu tên
cá nhân: giữ U + caveat, không thêm cáo buộc mới (lọc dữ kiện UNVERIFIED có nội dung tố tụng).

Mọi nguồn qua chaebol_map_data (chỉ đọc). Hàm dữ liệu lỗi → [CẦN DATA] + một cảnh báo, không làm hỏng tab.
"""
from __future__ import annotations

import re
from functools import cached_property

import chaebol_map_tab_codong as M
from chaebol_map_data_codong2 import FFT_MISS, FFT_MISS_TEXT
from chaebol_map_dom import C, F_MONO, can_data, h, js_sum, sign_fixed, tier, to_fixed, to_locale, upd_mark, v21_mark
from chaebol_map_shell import Card, Section, Stat
from chaebol_map_tab_codong_common import (_date, cafef_basis, cd, classify, codong_summary, dedupe_iss, dmy,
                                           dmy_hm, fact_line, flow_view, holder_basis, ky_vi, legal, legal_caveat,
                                           mcp, nav_books, nowrap_can, num, ok, overlaps, pill, rating_class,
                                           short_name, structure_dev, td, tg, upd_block, vi_label, win_label)

V21_CUT = "2026-05-09"                       # dữ liệu sau mốc V21 (08/05/2026)
VS_FILE = "knowledge_os/primary_filings/vietstock_filings.json"
_PAT_Q = re.compile(r"\b(Pattern) ([A-D])\b(?!\?)", re.I)     # cả 'PATTERN B CONFIRMED' (giữ hoa thường gốc)
CAFEF_WIN = ("2026-04-24", "2026-05-08")    # "04-08/05/2026" của V21 (+ phiên 24–29/04 để dò cơ sở giá)
S_LENS = {"marginTop": 0, "paddingTop": 10, "borderTop": "1px dashed " + C.rule, "fontSize": 10, "fontFamily": F_MONO,
          "color": C.inkD, "lineHeight": 1.8, "letterSpacing": ".02em"}


# ── dùng chung cho 48 mã ────────────────────────────────────────────────────


class Shared:
    def __init__(self, ctx, D):
        self.ctx, self.D, self.data = ctx, D, ctx.data
        self.today = ctx.today.isoformat()
        self.dossier = ctx.dossier if isinstance(ctx.dossier, dict) else {}
        self.errs = set()
        self.dz_used = 0
        if self.data is None:
            ctx.warn("live không có chaebol_map_data → mọi số sống của tab = [CẦN DATA]")
        if not self.dossier:
            ctx.warn("chưa có dossier cap_nhat_* — câu cập nhật dùng số sống + facts, không có bản viết lại")

    def call(self, name, *a, **k):
        fn = getattr(self.data, name, None) if self.data is not None else None
        if not callable(fn):
            return None
        try:
            return fn(*a, **k)
        except Exception as exc:  # hàm dữ liệu hỏng → [CẦN DATA] + một cảnh báo mỗi hàm
            if name not in self.errs:
                self.errs.add(name)
                self.ctx.warn("chaebol_map_data.%s lỗi: %s: %s" % (name, type(exc).__name__, exc))
            return None

    def dz(self, tk, field):
        e = ((((self.dossier.get("tickers") or {}).get(tk) or {}).get("codong") or {}).get(field))
        if isinstance(e, dict) and e.get("src") and (e.get("text") or e.get("strong")):
            self.dz_used += 1
            return e
        return None

    @cached_property
    def facts(self):
        return self.call("facts") or []

    @cached_property
    def fact_by_id(self):
        return {f["id"]: f for f in self.facts if f.get("id")}

    def facts_of(self, tk):
        return [f for f in self.facts if tk in (f.get("ma") or [])]

    @cached_property
    def vietstock(self):
        d = self.call("read_json", self.ctx.sys_dir / VS_FILE, quiet=True)
        want, out = set(self.D.tickers), {}
        if isinstance(d, dict):
            for x in d.get("filings") or []:
                if x.get("ticker") in want:
                    out.setdefault(x["ticker"], []).append(x)
            for v in out.values():
                v.sort(key=lambda x: int(x.get("catalog_id") or 0), reverse=True)
        return {"rows": out, "asof": str((d or {}).get("generated_at") or "")[:10] if isinstance(d, dict) else None}

    @cached_property
    def tv30(self):
        return self.call("tv30") or []

    @cached_property
    def portfolio(self):
        """Hai sổ danh mục hiện hành cạnh nhau (Khối 11 10/09 · HĐCV 12/09) + xung đột — không chọn (DESIGN §0.4)."""
        p = self.call("portfolio_current")
        return p if isinstance(p, dict) else {}

    @cached_property
    def pattern_exempt(self):
        """Câu định nghĩa phương pháp (chung mọi mã) — không gắn '?' (luật '?' chỉ cho pattern gắn với một mã)."""
        out = {M.READING_S9[4]}
        try:
            import chaebol_map_tab_codong_deep as DD
            out.add(DD.TV_READING)
        except Exception:  # module Deep-dive vắng/lỗi: chỉ miễn câu S9
            pass
        return out

    def finish(self):
        if self.dz_used:
            self.ctx.warn("dossier: dùng %d mục viết lại (tickers.<MÃ>.codong)" % self.dz_used)


# ── theo mã ─────────────────────────────────────────────────────────────────


class LiveTk:
    def __init__(self, S, tk):
        self.S, self.tk, self.D = S, tk, S.D

    def v21(self):
        return v21_mark()

    def dz(self, field):
        return self.S.dz(self.tk, field)

    # dữ liệu (lười)
    @cached_property
    def det(self):
        return self.S.call("details", self.tk) or {}

    @cached_property
    def px(self):
        lp = self.S.call("last_price", self.tk) or {}
        return lp.get("raw")

    @cached_property
    def holders(self):
        return self.S.call("top_holders", self.tk)

    @cached_property
    def shares(self):
        return self.S.call("shares_out", self.tk)

    @cached_property
    def lk(self):
        return self.S.call("lk_view", self.tk) or {"ok": False, "note": "không đọc được lk_hoso"}

    @cached_property
    def ph(self):
        return self.S.call("price_history", self.tk)

    def shares_at(self, d):
        """totalShares phiên cuối có số ≤ d (None nếu trước niêm yết/không có)."""
        ph = self.ph
        if not ph or not len(ph) or not d:
            return None
        ts, i = ph.col("totalShares"), ph.at(d)
        while i >= 0 and not isinstance(ts[i], (int, float)):
            i -= 1
        return ts[i] if i >= 0 and ts[i] else None

    @cached_property
    def rows_h(self):
        """Sổ cổ đông vendor, sắp theo SL quy về cơ sở cp hiện hành (dòng có quyền mua sau ngày công bố: SL gốc)."""
        hv = self.holders
        ce = self.S.call("capital_events", self.tk)
        iss = dedupe_iss(ce.value if ok(ce) and isinstance(ce.value, list) else [])
        val = lambda v: v.value if ok(v) else None  # noqa: E731
        rows = [dict(r, _adj=holder_basis(val(r.get("qty")), r.get("public_date"), val(r.get("pct_pub")), iss,
                                          self.shares_at(r.get("public_date")), self.S.today))
                for r in (hv.value if ok(hv) and isinstance(hv.value, list) else [])]
        def cur_qty(r):
            a = r["_adj"]["adj"]
            return a if a is not None else (r["qty"].value if ok(r.get("qty")) else 0)
        return sorted(rows, key=lambda r: -cur_qty(r))

    def pub_range(self, rows=None):
        ds = sorted(r.get("public_date") for r in (self.rows_h if rows is None else rows) if r.get("public_date"))
        return (ds[0], ds[-1]) if ds else (None, None)

    def asof_text(self):
        """'công bố tới 30/06/2026 · vendor cập nhật 10/09' — ngày của số sở hữu ≠ ngày vendor sửa bản ghi."""
        hv = self.holders
        if not ok(hv):
            return "[CẦN DATA]"
        return "công bố tới %s · vendor cập nhật %s" % (dmy(self.pub_range()[1]), dmy(hv.asof)[:5])

    # S1
    def name(self, v21_name):
        n = self.det.get("name")
        return [n.value, tg(n)] if ok(n) else [v21_name]

    def stance(self, text):
        return [text, legal_caveat(text), v21_mark()]

    def sector(self, det):
        sec, nm = self.det.get("sector"), self.det.get("name")
        if sec:
            return [sec, tier("T2", nm.asof) if ok(nm) else tier("T2")]
        return (det or {}).get("sector") or None

    def leader_line(self):
        e = self.dz("leader")
        if e:
            body = [e["text"], td(e), upd_mark()]
        else:
            v = self.S.call("leader", self.tk)
            body = [v.value, tg(v)] if ok(v) else [cd(v, "sổ cổ đông vendor không ghi Chủ tịch HĐQT")]
        return h("div", {"fontSize": 11, "color": C.inkD, "marginTop": 2}, "CHỦ TỊCH HĐQT: ", *body)

    def cafef_stat(self, px):
        """CAFEF UPDATE: số V21 (V21·12/05) + phiên/cơ sở dò được + giá quy đổi quyền tới phiên cuối (E)."""
        ph = self.ph
        basis = cafef_basis(ph.dates, ph.col("closePrice"), ph.col("closePriceAdjusted"), ph.at(CAFEF_WIN[0]),
                            ph.at(CAFEF_WIN[1]), px) if ph and len(ph) else None
        if basis is None:
            sub = ["04-08/05/2026 · ", can_data("không xác định được phiên/cơ sở giá của mốc CafeF")]
        else:
            kind, d = basis
            steps = self.S.call("adj_steps", self.tk, d, CAFEF_WIN[1]) or []
            if kind == "raw":
                base_txt = "đóng cửa thô %s%s" % (dmy(d)[:5], (" — trước GDKHQ " + dmy(steps[0][0])[:5]) if steps else "")
                d0 = d
            else:
                base_txt = "cơ sở giá sau GDKHQ %s (≈ đóng cửa %s đã điều chỉnh)" % (
                    dmy(steps[0][0])[:5] if steps else "trong 04–08/05", dmy(d)[:5])
                d0 = CAFEF_WIN[1]
            conv = self.S.call("convert_price", self.tk, px, d0)
            sub = [base_txt, " · quy đổi quyền ",
                   *([to_fixed(conv.value / 1000, 1) + "K", tg(conv)] if ok(conv) else [cd(conv)])]
        return Stat("CAFEF UPDATE", [to_fixed(px / 1000, 1) + "K", v21_mark()], sub=sub, color=C.ink2)

    def top10_stat(self):
        """Σ 10 cổ đông lớn nhất, SL quy về cơ sở cp hiện hành (E); ngày = dải ngày công bố; quyền mua sau ngày công
        bố → [CẦN DATA]; SL ≠ % vendor → cờ nguồn lệch."""
        rows = self.rows_h[:10]
        if not rows:
            return Stat("TOP 10 HOLDERS", [cd(self.holders, "chưa có sổ cổ đông vendor")], color=C.forest)
        lo, hi = self.pub_range(rows)
        short = lambda d: dmy(d)[:6] + dmy(d)[8:]  # noqa: E731  dd/mm/yy
        rng = ("công bố %s→%s" % (short(lo), short(hi))) if lo else None
        rights = [r for r in rows if r["_adj"]["rights"]]
        if rights:
            return Stat("TOP 10 HOLDERS", [cd(None, "%d dòng có quyền mua sau ngày công bố — không quy đổi được" %
                                              len(rights))], sub=rng, color=C.forest)
        if any(r["_adj"]["adj"] is None for r in rows):      # mã ngoài V21 (codong v2): dòng thiếu SL/ngày công bố
            return Stat("TOP 10 HOLDERS", [cd(None, "sổ vendor có dòng thiếu SL hoặc ngày công bố: không cộng được")],
                        sub=rng, color=C.forest)
        tot = js_sum([r["_adj"]["adj"] for r in rows])
        sh = self.shares
        sub = ([("~" + to_fixed(tot / sh.value * 100, 1) + "% cp hiện hành"), tier("E", sh.asof)] if ok(sh) else
               [cd(sh)]) + ([" · " + rng] if rng else [])
        gap = lambda r: -abs(r["_adj"]["lech"][0] - r["_adj"]["lech"][1])  # noqa: E731
        lech = sorted((r for r in rows if r["_adj"]["lech"]), key=gap)
        if lech:
            x, p = lech[0]["_adj"]["lech"]
            sub += [" · ⚑ nguồn lệch %d dòng: SL ÷ tổng cp %s%% ≠ %% vendor %s%% (%s)" % (
                len(lech), to_fixed(x, 2), to_fixed(p, 2), short_name(lech[0].get("name"))[:28]), tier("E")]
        return Stat("TOP 10 HOLDERS", [to_fixed(tot / 1e6, 0) + "M", tier("E", hi)], sub=sub, color=C.forest)

    def head_stats(self, det, total_v21):
        out, px = [], self.px
        val_px = [to_fixed(px.value / 1000, 1) + "K", tg(px)] if ok(px) else [cd(px, "chưa có giá vc_lk")]
        out.append(Stat("GIÁ", val_px,
                        sub=dmy(px.asof) if ok(px) else None, color=C.gold))
        if det and det.get("cafefPx"):
            out.append(self.cafef_stat(det["cafefPx"]))
        out.append(self.top10_stat())
        return out

    def s1_sub(self):
        return ["Vietcap IQ cache (vc_lk shareholder + structure, " + self.asof_text() + ") + lăng kính lk_hoso + V21 "
                "chaebol narrative + BCTN/báo cáo quản trị cross-validation. Capital IQ Q4/25 (V21 12/05) lưu ở chế độ "
                "v21 · Vietstock filings 23/09.", upd_mark()]

    def lens_block(self):
        L, tk = self.lk, self.tk
        lab = lambda t: h("span", {"color": C.gold, "letterSpacing": ".1em"}, t)  # noqa: E731
        lines = []
        if not L.get("ok"):
            return h("div", S_LENS, lab("LĂNG KÍNH "), cd(None, L.get("note")), key="codong.lens")
        tail = " · hai cửa sổ lệch ≥25 điểm — đọc cả hai" if L.get("fft_hai_cua_so") else None
        lines.append([lab("LĂNG KÍNH · FFT percentile "), "3Y ", *num(L["pct3y"]), " · toàn dải ", *num(L["pall"]),
                      " · thô ", *num(L["pct3y_tho"]), "/", *num(L["pall_tho"]), tail])
        lines += [[h("strong", {"color": C.vermillion}, FFT_MISS_TEXT)]] if tk in FFT_MISS else []   # CLAUDE.md §6.4
        vw = L.get("vwap") or {}
        vv = [vw.get(k) for k in ("v6", "v12", "v24")]
        nhan = vw.get("nhan")
        nhan = nhan.get("v") if isinstance(nhan, dict) else getattr(nhan, "value", nhan)
        v6 = vv[0]
        lines.append([lab("VWAP 6/12/24T "), *[x for i, v in enumerate(vv) for x in (["/"] if i else []) + num(v)],
                      " nghìn đ · cụm: ", *([vi_label(nhan), tier("E", v6.asof if ok(v6) else None)] if nhan else
                                           [can_data("chưa đủ VWAP để gắn nhãn cụm")])])
        lines.append(self._flow_line(lab))
        lines.append(self._pattern_line(lab))
        lines.append(self._codong_line(lab))
        lines.append(self._subject_line(lab))
        gate = self.S.call("ticker_gate", tk) or {}
        gt = str(gate.get("text") or "CỔNG: [CẦN DATA — chưa đọc được CỔNG mã]")
        red = "[CẦN DATA" in gt or "DỪNG" in gt
        at = gate.get("as_of")
        lines.append([h("span", {"color": C.vermillion if red else C.gold}, *nowrap_can(gt)), " · tính đến ",
                      dmy_hm(at) if at else can_data("lk_hoso không ghi thời điểm CỔNG mã")])
        return h("div", S_LENS, *[h("div", None, *ln) for ln in lines], key="codong.lens")

    def _flow_line(self, lab):
        fv = flow_view(self.S.call("flow4", self.tk, 60), self.S.call("prop_net", self.tk, 60, kind="khop"),
                       self.S.call("prop_net", self.tk, 60, kind="total"))
        nn, td_, du = fv["nn"], fv["td"], fv["du"]
        out = [lab("DÒNG TIỀN %s " % win_label(fv)), "NN ", *([mcp(nn), tg(nn)] if nn else [cd(fv["nn_raw"])]),
               " · tự doanh khớp ",
               *([mcp(td_), tier(td_.tier, fv["td_last"] or td_.asof), " (%s/%s phiên)" % (fv["n_co"], fv["n"])]
                 if td_ else [can_data(fv["td_why"])]),
               " · cá nhân/tổ chức nội ", can_data("sau 08/05 chỉ NN + TD có số thật")]
        if du:
            out += [" · phần dư −(NN tổng + TD tổng) ", mcp(du), tier("E", du.asof),
                    " (NN tới %s, TD tới %s; không phải kênh thật)" % (dmy(nn.asof)[:5], dmy(fv["td_last"] or td_.asof)[:5])]
        return out

    def _pattern_line(self, lab):
        pv = self.S.call("patterns", self.tk)
        if ok(pv) and pv.value:
            parts = []
            for i, r in enumerate(pv.value[:4]):
                lbl = self.S.call("pattern_label", self.tk, r.get("label")) or r.get("label")
                parts += ([" · "] if i else []) + [lbl, " (", vi_label(r.get("status")) or "?", " ",
                                                   dmy(r.get("status_since")), ")",
                                                   tier(r.get("tier") or "E", r.get("status_since"))]
            return [lab("PATTERN "), *parts]
        pat = self.lk.get("pattern")
        return [lab("PATTERN "), vi_label(pat), tier("E")] if pat else [lab("PATTERN "), cd(pv, "chưa có mẫu hình NTH")]

    def _codong_line(self, lab):
        """Toàn Vũ: quan sát cuối = mốc cuối có kieu 'quan_sat' và cf=False (bậc T3, đúng kỳ); mốc cuối là CF →
        'chưa có số mới (CF, kỳ mm/yyyy)' — không hiện số chép (cùng luật với sub-tab 05)."""
        cv = self.lk.get("codong")
        if not ok(cv) or not cv.value:
            return [lab("CỔ ĐÔNG (Toàn Vũ) "), cd(cv, "ngoài 30 mã Toàn Vũ — chờ OCR BCTN")]
        obs, last, n_cf = codong_summary(cv.value)
        out = [lab("CỔ ĐÔNG (Toàn Vũ) ")]
        if obs:
            out += ["quan sát cuối ", to_locale(obs["v"], "en", max_frac=0), " (", ky_vi(obs["ky"]), ")",
                    tier(obs.get("tier") or "T3")]
        else:
            out.append(can_data("chưa có kỳ quan sát (chỉ nội suy/CF)"))
        if last and last is not obs:
            if last.get("cf"):
                out += [" · mốc cuối: chưa có số mới (CF, kỳ %s; %d kỳ CF)" % (ky_vi(last["ky"]), n_cf)]
            else:
                out += [" · mốc cuối ", to_locale(last["v"], "en", max_frac=0), " (", ky_vi(last["ky"]), ", ",
                        vi_label(last.get("kieu")) or "?", ")", tier(last.get("tier") or "E")]
        return out

    def _nav_parts(self, lab):
        """NAV hai sổ cạnh nhau (Khối 11 10/09 · HĐCV 12/09), cờ lệch; >5% (hoặc chạm 5%) ở bất kỳ sổ nào →
        Synthesis; watch/avoid của từng sổ + cờ xung đột (nav.xung_dot / portfolio_current().conflicts)."""
        P = self.S.portfolio
        if not P:
            return [lab("NAV "), cd(None, "không đọc được hai sổ danh mục")]
        B = nav_books(P, self.tk)
        fmt = lambda x: to_locale(x, "en", max_frac=1)  # noqa: E731
        dd = lambda d, dflt: dmy(d)[:5] if d else dflt  # noqa: E731

        def book(name, bk, p):
            if not p:
                return [name + " (" + dd(bk.get("date"), "?") + ") —"]
            return [name + " (" + dd(bk.get("date"), "?") + ") ", fmt(p["nav"]) + "%",
                    tier(getattr(p.get("v"), "tier", None) or "E", bk.get("date"))]
        out = [lab("NAV "), *book("Khối 11", B["a"], B["pa"]), " · ", *book("HĐCV", B["b"], B["pb"])]
        if not B["pa"] and not B["pb"]:
            out += [" ", can_data("không có tỷ trọng trong hai sổ")]
        if B["nav_c"]:
            out.append(" ⚑ lệch %s vs %s" % (fmt(B["nav_c"]["lk_khoi11"]), fmt(B["nav_c"]["hdcv"])))
        if B["mx"] >= 5:
            out.append(" · %s NAV → Synthesis L1+L2+L3 trước mọi action (action cần kiểm chứng)" % (
                ">5%" if B["mx"] > 5 else "chạm 5%"))
        raw = (self.S.call("lk_hoso", self.tk) or {}).get("nav") or {}
        if B["fa"] or B["fb"]:
            out += [" · sổ nội bộ: Khối 11 (fft_cauhinh %s) %s · HĐCV (%s) %s" % (
                dd(raw.get("t"), "21/09"), B["fa"] or "—", dd(B["b"].get("date"), "12/09"), B["fb"] or "—"),
                tier("E", raw.get("t")), " (bản lưu sổ, không phải khuyến nghị mới)"]
        if B["xd"] or raw.get("xung_dot"):
            c = B["xd"][0] if B["xd"] else {}
            txt = ("Khối 11 %s vs HĐCV %s" % (c.get("lk_khoi11") or "—", "không có trong AVOID" if c.get("hdcv") == "—"
                                              else c.get("hdcv"))) if c else ""
            out.append(h("span", {"color": C.vermillion}, " ⚑ xung đột sổ: " + "; ".join(
                x for x in (txt, c.get("note") or raw.get("xung_dot")) if x)))
        return out

    def _subject_line(self, lab):
        ct = self.lk.get("chu_the")
        return [lab("CHỦ THỂ "), *(num(ct) if ok(ct) else [cd(ct)]), " (nhãn W37 — kỳ mới phải chấm lại)", " · ",
                *self._nav_parts(lab)]

    # S2
    def auto_comp(self):
        rows = [r for r in self.rows_h if not r.get("stale") and ok(r.get("pct_pub"))][:3] or \
               [r for r in self.rows_h if ok(r.get("pct_pub"))][:3]
        if not rows:
            return None
        txt = " · ".join("%s %s" % (short_name(r["name"]), r["pct_pub"].text) for r in rows)
        last = max((r.get("public_date") or "") for r in rows)
        return txt + " (sổ vendor, % tại ngày công bố)", last

    def composition(self, v21_text):
        e = self.dz("composition")
        if e:
            return [e["text"], td(e), upd_mark()]
        a = self.auto_comp()
        if a:
            return [a[0], tier("T2", a[1]), upd_mark()]
        return [v21_text, v21_mark(), " ", can_data("chưa có sổ cổ đông vendor")]

    def driver(self, v21_text):
        e = self.dz("driver_upd")
        return [v21_text, v21_mark(), upd_block(e) if e else None]

    def risk(self, v21_text):
        e = self.dz("risk_upd")
        return [v21_text, legal_caveat(v21_text), v21_mark(), upd_block(e) if e else None]

    def policy_facts(self, basket):
        want = []
        for f in self.S.facts:
            if not f.get("id", "").startswith("F5") or f.get("loai") != "chinh_sach":
                continue
            ma = f.get("ma") or []
            if self.tk in ma or (not ma and basket == "NQ79" and f["id"] == "F5-001") or \
                    (basket == "NQ79" and f["id"] == "F5-003") or (not ma and basket == "NQ68" and f["id"] == "F5-011"):
                if not ((f.get("bac") or "").upper() == "UNVERIFIED" and legal(f.get("noi_dung"))):
                    want.append(f)
        seen, out = set(), []
        for f in sorted(want, key=lambda f: f.get("ngay") or "", reverse=True):
            if f["id"] not in seen:
                seen.add(f["id"])
                out.append(f)
        return out

    def policy_block(self, p):
        fs = self.policy_facts(p.get("basket"))
        if not fs:
            return None
        return h("div", {"marginTop": 12, "padding": "8px 14px", "background": C.ink2 + "10",
                         "border": "1px solid " + C.ink2 + "30", "borderRadius": 3, "fontSize": 10.5, "color": C.inkD,
                         "lineHeight": 1.7},
                 M.label9("↻ KHUNG CHÍNH SÁCH (facts_f5 · 27/09)", C.ink2, marginBottom=4),
                 h("ul", {"margin": 0, "paddingLeft": 18}, *[fact_line(f) for f in fs]), key="codong.policy")

    # S4
    def holders_section(self):
        rows = self.rows_h[:10]
        if not rows:
            return None
        hv = self.holders
        trs = []
        for i, r in enumerate(rows):
            old = bool(r.get("old"))
            typ = "INSIDER" if r.get("position") else ("INDIVIDUAL" if r.get("type") == "INDIVIDUAL" else "CORPORATE")
            tcol = {"INSIDER": C.gold, "INDIVIDUAL": C.gold}.get(typ, C.ink2)
            q, pp = r.get("qty"), r.get("pct_pub")
            trs.append(M.tr_row(
                i,
                h("td", {"padding": "9px 10px", "color": C.inkD, "fontWeight": 600}, i + 1),
                h("td", {"padding": "9px 10px", "color": C.inkM if old else C.ink, "fontWeight": 600,
                         "fontFamily": "'Source Serif 4', serif", "fontSize": 11.5}, r.get("name"),
                  h("span", {"fontSize": 9.5, "color": C.inkD, "fontFamily": F_MONO, "fontWeight": 400},
                    " · " + r["position"]) if r.get("position") else None),
                h("td", {"padding": "9px 10px", "textAlign": "right", "color": C.inkM if old else C.gold,
                         "fontWeight": 700},
                  *(num(q, to_locale(q.value / 1e6, "en-US", max_frac=2)) if ok(q) else [cd(q)])),
                h("td", {"padding": "9px 10px", "textAlign": "right", "color": C.inkM if old else C.ink,
                         "fontWeight": 600}, *(num(pp) if ok(pp) else [cd(pp)]),
                  h("span", {"fontSize": 9, "color": C.inkD, "fontWeight": 400}, " · " + dmy(r.get("public_date"))),
                  h("span", {"fontSize": 9, "color": C.vermillion}, " cũ") if old else None),
                h("td", {"padding": "9px 10px"}, M.chip(typ, tcol, "2px 8px"))))
        table = h("table", M.S_TABLE,
                  h("thead", None, h("tr", M.S_TR_HEAD, M.th("#"), M.th("HOLDER NAME"), M.th("SHARES (M)", "right"),
                                     M.th("% · NGÀY CÔNG BỐ", "right"), M.th("TYPE"))),
                  h("tbody", None, *trs))
        call = h("div", M.S_CALLOUT, h("strong", {"color": C.gold}, "★ Reading:"),
                 " % tại ngày công bố của từng dòng (FACT-T2) — các dòng khác kỳ không cộng được; dòng >12 tháng "
                 "tô mờ, đánh dấu “cũ”. Δ theo kỳ ", can_data("sổ vendor chụp đè, không có lịch sử"),
                 ". Insider/Vehicle tăng khi NN giảm = pattern chuyển giao chủ thể (Toàn Vũ) — đối chiếu insider-"
                 "transaction trước khi kết luận.", v21_mark(), " · ", hv.note if ok(hv) else None,
                 tg(hv) if ok(hv) else None, upd_mark())
        title = ["📊 Top 10 Holders — Vietcap IQ (sổ cổ đông vendor · " + self.asof_text() + ")", upd_mark()]
        return Section(title, Card(self.structure_line(), table, call), accent=C.forest, sub=self._s4_sub(),
                       key="codong.s4")

    def structure_line(self):
        """Cơ cấu sở hữu (vc_lk shareholder-structure, ảnh chụp không ngày) + free float/room NN (details)."""
        st = self.S.call("ownership_structure", self.tk) or {}
        parts = [("Nhà nước ", st.get("state")), ("NN ", st.get("foreign")), ("HĐQT ", st.get("bod")),
                 ("tổ chức ", st.get("institution")), ("khác ", st.get("other")),
                 ("free float ", self.det.get("free_float")), ("room NN tối đa ", self.det.get("foreign_max"))]
        kids = [h("span", {"color": C.gold, "letterSpacing": ".1em"}, "CƠ CẤU SỞ HỮU ")]
        for i, (lbl, v) in enumerate(parts):
            kids += ([" · "] if i else []) + [lbl] + (num(v) if ok(v) else [cd(v)])
        tot = st.get("total_shares")
        kids += [" · tổng ", *(num(tot, to_locale(tot.value / 1e6, "en-US", max_frac=2) + "M cp") if ok(tot) else
                               [cd(tot)]), " (ảnh chụp Vietcap, không ngày dữ liệu)"]
        kids += self.structure_warn()
        return h("div", {"fontSize": 10, "fontFamily": F_MONO, "color": C.inkD, "lineHeight": 1.8,
                         "marginBottom": 10}, *kids, key="codong.structure")

    def structure_warn(self):
        """Ảnh chụp shareholder-structure tự mâu thuẫn (FPT sau thưởng 21/09: % trên mẫu số cũ 1.714,33M, tổng cp mới
        1.885,76M) → cảnh báo + tỷ lệ tính lại trên tổng cp (E)."""
        meta, s = self.S.call("vc", self.tk, "shareholder-structure") or (None, None)
        d = structure_dev(s)
        if d is None:
            return []
        t = str((meta or {}).get("t_lay") or (meta or {}).get("lay_luc") or "")[:10] or None
        pct = lambda v: to_fixed(v / d["total"] * 100, 2) + "%"  # noqa: E731
        return [h("div", {"color": C.vermillion}, "⚑ vendor lệch mẫu số: Σ SL các nhóm ",
                  to_locale(d["sum"] / 1e6, "en-US", max_frac=2), "M ≠ tổng ",
                  to_locale(d["total"] / 1e6, "en-US", max_frac=2), "M cp (", sign_fixed(d["dev"], 1), "%)", tier("E", t),
                  " — % ở trên tính trên Σ SL (mẫu số chưa cập nhật); theo tổng cp: Nhà nước ", pct(d["vols"][0]),
                  " · NN ", pct(d["vols"][1]), " · khác ", pct(d["vols"][2]), tier("E", t))]

    def _s4_sub(self):
        return ("Nguồn: state/vc_lk/" + self.tk + "/shareholder.json (khử trùng theo ownerCode, giữ publicDate mới "
                "nhất; sắp theo SL quy về cơ sở cp hiện hành) + shareholder-structure · TYPE theo ownerType/positionName "
                "của vendor · bảng Capital IQ Q4/25 của V21 lưu ở chế độ v21.")

    # S5 / S6
    def msr_note(self):
        e, e2 = self.dz("msr_note"), self.dz("msr_note2")
        if not e:
            a = self.auto_comp()
            return ["MSR là UPCOM stock với ", h("strong", {"color": C.gold}, a[0] if a else can_data()),
                    tier("T2", a[1]) if a else None, ". ", v21_mark(), upd_mark()]
        out = [e.get("lead"), h("strong", {"color": C.gold}, e.get("strong")), e.get("text"), td(e), upd_mark()]
        if e2:
            out += [" ", e2.get("text"), td(e2), upd_mark()]
        return out

    def stb_note(self):
        e, hv = self.dz("claim_bau_thuy"), self.holders
        comp = self.composition(None)
        f = self.S.call("flow4", self.tk, 60) or {}
        nn = f.get("nn")
        out = ["STB Capital IQ ownership data ", h("strong", {"color": C.vermillion}, "N/A"), v21_mark(),
               " — nay thay bằng sổ cổ đông Vietcap IQ (",
               *([str(len(self.rows_h)), " chủ sở hữu, tới ", dmy(hv.asof), tg(hv)] if ok(hv) else [cd(hv)]), "): ",
               *comp, ". Mệnh đề V21 ", h("strong", {"color": C.gold}, "Bầu Thụy/Thaiholdings (>30%)"), " "]
        out += [pill(e.get("status")), " ", e.get("text"), td(e), upd_mark()] if e else \
            [can_data("chưa chấm lại — không có dữ kiện")]
        out += [" ", h("strong", None, "Pillar IV flow signal Q1/26 + 5-day 4-8/5"),
                ": Tổ chức nội ACCUMULATE +6.69M cp tuần (FiinTrade ≤08/05, đóng băng)", v21_mark(),
                "; sau 08/05 tổ chức nội ", can_data("chỉ NN + tự doanh có số thật"), ", NN 60 phiên ",
                *(num(nn, mcp(nn)) if ok(nn) else [cd(nn)]),
                "."]
        return out

    # S7
    def legal_title(self, title):
        return [title, tier("U")] if legal(title) else title

    def narrative_updates(self):
        det = self.D.detail.get(self.tk) or {}
        fs = [f for f in self.S.facts_of(self.tk) if overlaps(f, 245, 373) or overlaps(f, 4248, 4673)]
        fs = [f for f in fs if not ((f.get("bac") or "").upper() == "UNVERIFIED" and legal(f.get("noi_dung")))]
        fs.sort(key=lambda f: f.get("ngay") or "", reverse=True)
        out = []
        if legal(det.get("chaebol")) or legal(det.get("risk")):
            out.append(h("p", {"margin": "14px 0 0", "fontSize": 10.5, "color": C.vermillion, "lineHeight": 1.7},
                         "⚠ Nhóm/tiêu đề V21 nêu tên cá nhân kèm mệnh đề pháp lý — UNVERIFIED, chưa đối chiếu văn bản "
                         "tố tụng (FACT-T1); không dùng cho quyết định.", tier("U")))
        if fs:
            out += [M.label9("↻ DỮ KIỆN CẬP NHẬT 27/09 (facts)", C.ochre, marginTop=14, marginBottom=8),
                    h("ul", M.S_UL, *[fact_line(f) for f in fs[:6]])]
        return out

    def subsidiaries(self, v21_holdings):
        rel = self.S.call("relationships", self.tk) or {}
        items = [(x, "công ty con") for x in rel.get("subsidiaries") or []] + \
                [(x, "liên kết") for x in rel.get("affiliates") or []]
        pct_ok = lambda x: ok(x.get("pct")) and x["pct"].value > 0  # noqa: E731  vendor ghi 0% + 0 cp = không có số
        items.sort(key=lambda it: (not it[0].get("ticker"), -it[0]["pct"].value if pct_ok(it[0]) else 0))
        if not items:                            # không có relationship → bảng V21 lưu trữ + [CẦN DATA]
            rows = [dict(r, key="codong.arch.s7b") for r in M.v21_sub_rows(v21_holdings)]
            note = h("div", M.S_CALLOUT, can_data("không đọc được vc_lk/" + self.tk + "/relationship"),
                     " · bảng trên là bản lưu V21 (TICKER_DETAIL.holdings)", v21_mark())
            return M.sub_table(("SUBSIDIARY / HOLDING", "STAKE", "VALUE"), rows, note)
        rows = [h("tr", {"borderBottom": "1px solid " + C.rule + "80"},
                  h("td", {"padding": "10px 10px", "color": C.ink, "fontWeight": 600}, x.get("name"),
                    (" (" + x["ticker"] + ")") if x.get("ticker") else None),
                  h("td", {"padding": "10px 10px", "color": C.gold, "fontFamily": F_MONO, "fontSize": 11},
                    *(num(x.get("pct")) if pct_ok(x) else [cd(x.get("pct") if not ok(x.get("pct")) else None,
                                                              "vendor ghi 0% / 0 cp — không có số")])),
                  h("td", {"padding": "10px 10px", "color": C.inkD, "fontStyle": "italic"}, kind))
                for x, kind in items[:10]]
        note = h("div", M.S_CALLOUT, h("strong", {"color": C.gold}, "★ Nguồn:"),
                 " vc_lk/" + self.tk + "/relationship (Vietcap) — " + str(rel.get("note") or ""), tier("U"),
                 ". Bảng V21 (", ", ".join(str(x.get("name")) for x in v21_holdings[:3]), "…) lưu ở chế độ v21.",
                 upd_mark())
        return M.sub_table(("SUBSIDIARY / HOLDING", "STAKE (thời điểm U)", "LOẠI"), rows, note)

    # S8
    def s8_title(self):
        return ["📑 Tài liệu công ty (Vietcap IQ · Vietstock): BCTC · BCTN · NQ ĐHĐCĐ · Bản cáo bạch", upd_mark()]

    def s8_sub(self):
        return ("Danh mục tài liệu Vietstock (" + VS_FILE + ", " + dmy(self.S.vietstock["asof"]) + ") — 4 nhóm như "
                "V21; khuôn Simplize 10/5/2026 của V21 (giống nhau ở 48 mã) xếp UNVERIFIED, lưu ở chế độ v21.")

    def vciq_link(self):
        """Nút sang tab ★ 15 VIETCAP IQ đúng mã (đặt cùng lúc tab + vciq.tk; scope vciq giữ giá trị vì tab được dựng)."""
        return h("div", {"marginTop": 10, "display": "flex", "gap": 8, "alignItems": "center", "flexWrap": "wrap"},
                 h("button", {"background": C.ink2 + "20", "color": C.ink2, "border": "1px solid " + C.ink2,
                              "padding": "5px 12px", "borderRadius": 2, "cursor": "pointer", "fontFamily": F_MONO,
                              "fontSize": 10, "letterSpacing": ".08em"},
                   "◈ HỒ SƠ VIETCAP IQ ĐẦY ĐỦ CỦA " + self.tk + " →",
                   on={"set": {"tab": "vciq", "vciq.tk": self.tk}}, key="codong.vciq." + self.tk),
                 h("span", {"fontSize": 9.5, "color": C.inkD, "fontFamily": F_MONO},
                   "tài chính · thống kê D/W/M/Q/Y · NN · tự doanh · nội bộ · cung cầu · tin & sự kiện kèm PDF · báo cáo"))

    def vietcap_docs(self):
        """CBTT của doanh nghiệp trên Vietcap IQ (vc_lk news + news-detail) chia 4 nhóm như V21, kèm link PDF gốc."""
        import chaebol_map_data_vciq as Q
        n = Q.news(self.tk, 100000)
        if not n["ok"]:
            return None
        rules = (("BCTC", r"báo cáo tài chính|bctc"), ("BACH", r"cáo bạch"), ("BCTN", r"báo cáo thường niên"),
                 ("NQ", r"(nghị quyết|biên bản|tài liệu).{0,12}(đhđcđ|đại hội|đhcđ)"))
        lim = {"BCTC": 4, "BACH": 3, "BCTN": 4, "NQ": 5}
        pick = {k: [] for k, _ in rules}
        for x in n["rows"]:
            if not x["cbtt"]:
                continue
            t = str(x["tieu_de"] or "")
            k = next((k for k, rx in rules if re.search(rx, t, re.I)), None)
            if k and len(pick[k]) < lim[k]:
                links = [h("a", {"color": C.ink2, "marginLeft": 6}, "PDF", href=u) for u in x["tep"][:2]]
                pick[k].append([dmy(x["ngay"][:10]), " · ", t.split(":", 1)[-1].strip(), tier("T2", x["ngay"][:10]),
                                *links])
        miss = {"BCTC": "BCTC", "BACH": "bản cáo bạch", "BCTN": "BCTN", "NQ": "NQ/tài liệu ĐHĐCĐ"}
        lists = {k: v or [can_data("Vietcap IQ chưa có CBTT " + miss[k] + " cho " + self.tk)] for k, v in pick.items()}
        return [M.label9("◈ CBTT TRÊN VIETCAP IQ · %d tin CBTT/%d tin, %d link PDF (tính đến %s)" % (
            n["n_cbtt"], n["n"], n["n_tep"], dmy(n["rows"][0]["ngay"][:10])), C.ink2, marginBottom=8),
            M.doc_cards(lists, tier("T2", n["rows"][0]["ngay"][:10])),
            M.label9("· danh mục Vietstock 23/09 (nguồn phụ) ·", C.inkM, marginTop=14, marginBottom=8)]

    def docs_body(self, v21_docs):
        vc_docs = self.vietcap_docs() or []
        return h("div", None, *vc_docs, self._vietstock_docs(v21_docs))

    def _vietstock_docs(self, v21_docs):
        rows = self.S.vietstock["rows"].get(self.tk) or []
        pick = {"BCTC": [], "BACH": [], "BCTN": [], "NQ": []}
        lim = {"BCTC": 3, "BACH": 3, "BCTN": 5, "NQ": 6}
        for x in rows:
            t, ft = str(x.get("title") or ""), x.get("filing_type")
            k = {"BCTC": "BCTC", "BanCaoBach": "BACH", "BCTN": "BCTN"}.get(ft)
            if ft == "DHCD" and re.search(r"nghị quyết\s+(ĐHĐCĐ|đại hội)", t, re.I):
                k = "NQ"
            if k == "BACH" and not re.search(r"cáo bạch", t, re.I):
                k = None
            if k and len(pick[k]) < lim[k]:
                pick[k].append(t)
        miss = {"BCTC": "BCTC", "BACH": "bản cáo bạch", "BCTN": "BCTN", "NQ": "NQ ĐHĐCĐ"}
        lists = {k: v or [can_data("Vietstock chưa có mục " + miss[k] + " cho " + self.tk)] for k, v in pick.items()}
        return M.doc_cards(lists, tier("T2", self.S.vietstock["asof"]))

    # S9
    def s9_title(self):
        return ["📈 Sell-Side Consensus & giá mục tiêu (Vietcap IQ · CapIQ)", upd_mark()]

    def s9_sub(self):
        reps = self.D.reports.get(self.tk) or []
        tail = " · Simplize ≤08/05 (V21) lưu bên dưới" if reps and reps[0].get("b") != "-" else ""
        return ("Nguồn: knowledge_os/hhp_forecast_tickers/" + self.tk + ".json + vc_lk details — quan điểm vendor "
                "(SS-T3), không phải khuyến nghị của trang" + tail)

    @cached_property
    def targets(self):
        v = self.S.call("sell_side_targets", self.tk)
        out = []
        for x in (v.value if ok(v) and isinstance(v.value, list) else []):
            m = re.match(r"^(\S+)\s*(.*?)(?:\s+n=(\d+))?$", str(x.note or "").strip())
            org, rat, n = (m.group(1), m.group(2), m.group(3)) if m else ("?", "", None)
            title = ("Vietcap IQ coverage" if org.lower().startswith("vietcap") else
                     ("CapIQ Estimates — đồng thuận n=" + n) if n else org + " — giá mục tiêu")
            out.append({"d": x.asof, "t": title, "b": org, "r": rat or "—", "tp": x})
        return out

    def sellside(self, v21_reps):
        live, today = self.targets, self.S.ctx.today
        rows = []
        for i, r in enumerate(live):
            cls = rating_class(r["r"])
            col = {"buy": C.forest, "sell": C.vermillion, "hold": C.ochre}.get(cls, C.inkD)
            rows.append(M.s9_row(i, dmy(r["d"]), r["t"], r["b"], r["r"], col,
                                 num(r["tp"], to_locale(r["tp"].value, "en-US", max_frac=0)), C.gold))
        if v21_reps:
            rows.append(h("tr", {"borderBottom": "1px solid " + C.rule}, h("td", {
                "padding": "7px 10px", "color": C.inkM, "fontSize": 9, "letterSpacing": ".1em"},
                "— bản lưu Simplize ≤08/05/2026 (V21, SS-T3) —", v21_mark(), a={"colSpan": 5})))
            rows += [dict(r, key="codong.arch.s9") for r in M.v21_report_rows(v21_reps, len(rows), dim=True)]
        facts = [f for f in self.S.facts_of(self.tk) if overlaps(f, 3532, 3533)]
        facts.sort(key=lambda f: f.get("ngay") or "", reverse=True)
        extra = [M.label9("↻ CẬP NHẬT SELL-SIDE (facts)", C.ochre, marginTop=12, marginBottom=6),
                 h("ul", M.S_UL, *[fact_line(f) for f in facts[:4]])] if facts else []
        if not live and not v21_reps:
            return [Card(h("p", M.S_P_EMPTY,
                           "⚠ Chưa có giá mục tiêu trong kho (Vietcap IQ coverage · CapIQ · HSC) cho ",
                           self.tk, " ", can_data("không có TP"), ". Bản V21 (Simplize 10/5/2026) cũng không có broker "
                           "report.", upd_mark()), *extra)]
        fresh_rows = [r for r in live if r["d"] and (today - _date(r["d"])).days <= 90]
        fresh = [r["tp"].value for r in fresh_rows]
        n_buy = sum(1 for r in live if rating_class(r["r"]) == "buy")
        n_sell = sum(1 for r in live if rating_class(r["r"]) == "sell")
        if live:
            e = lambda x: [str(x), tier("E")]  # noqa: E731
            avg = [to_fixed(js_sum(fresh) / len(fresh) / 1000, 1) + "K", tier("E")] if fresh else \
                [can_data("không có TP ≤90 ngày")]
            m_n = re.search(r"đồng thuận n=(\d+)", fresh_rows[0]["t"]) if len(fresh_rows) == 1 else None
            sub_avg = (("1 nguồn tổng hợp (%s n=%s) ≤90 ngày" % (fresh_rows[0]["b"], m_n.group(1))) if m_n else
                       "n=%d ≤90 ngày" % len(fresh) + (" · n=1 — không phải đồng thuận" if len(fresh) == 1 else ""))
            stats = [Stat("BÁO CÁO", e(len(live)), sub="TP trong kho", color=C.gold),
                     Stat("MUA / KHẢ QUAN", e(n_buy), sub="rating mua (vendor)", color=C.forest),
                     Stat("⚠ BÁN", e(n_sell), sub="rating bán (vendor)", color=C.vermillion if n_sell else C.inkD),
                     Stat("AVG TARGET PRICE", avg, sub=sub_avg, color=C.ink2)]
        else:
            stats = [Stat(lbl, [can_data("không có TP sống")], color=C.inkD)
                     for lbl in ("BÁO CÁO", "MUA / KHẢ QUAN", "⚠ BÁN", "AVG TARGET PRICE")]
        grid = h("div", {"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)", "gap": 12, "marginBottom": 14},
                 *stats)
        card = M.s9_table(rows, self)
        card["k"] = card.get("k", []) + extra if extra else card.get("k", [])
        return [grid, card, *self.vietcap_reports()]

    def vietcap_reports(self):
        import chaebol_map_data_vciq as Q
        a = Q.analysis(self.tk, 8)
        if not a["ok"]:
            return []
        items = [h("li", None, dmy(r["ngay"]), " · ", r["ten"], tier("T3", r["ngay"])) for r in a["rows"]]
        return [Card(M.label9("◈ BÁO CÁO PHÂN TÍCH CỦA VIETCAP · %d báo cáo (8 mới nhất)" % a["n"], C.gold,
                              marginBottom=6),
                     h("ul", M.S_UL, *items), h("div", {"fontSize": 9.5, "color": C.inkD, "fontFamily": F_MONO,
                                                      "marginTop": 6}, "Nguồn: vietcap.com.vn cms-service qua vc_lk analysis · "
                                                      "quan điểm sell-side", tier("T3", a["rows"][0]["ngay"])),
                     key="codong.s9.vietcap")]

    # S10
    def s10_sub(self):
        return ("Nguồn: vc_lk news · insider-transaction · events-v2 (Vietcap IQ, FACT-T2) từ 09/05/2026 + danh mục "
                "Vietstock 23/09 · LOẠI phân theo từ khoá tiêu đề (EST) · bản vietstock ≤08/05 của V21 bên dưới")

    def live_filings(self):
        out, tk = [], self.tk
        _, news = self.S.call("vc", tk, "news") or (None, None)
        for x in news or []:
            d = str(x.get("publicDate") or "")[:10]
            if d >= V21_CUT and x.get("newsTitle"):
                out.append((d, classify(x["newsTitle"]), x["newsTitle"]))
        ins = self.S.call("insider_tx", tk, since=V21_CUT)
        for x in (ins.value if ok(ins) else []):
            qty = x.get("acquire") if x.get("acquire") not in (None, 0) else x.get("register")
            q = to_locale(abs(qty), "en") + " cp" if isinstance(qty, (int, float)) else "[CẦN DATA]"
            out.append((x.get("public_date") or "", "INSIDER", "%s · %s %s · %s" % (
                x.get("trader") or "?", x.get("action_vi") or "", q, x.get("status_vi") or "")))
        ev = self.S.call("capital_events", tk, since=V21_CUT, by="public")    # danh sách CBTT: theo ngày công bố
        for x in (ev.value if ok(ev) else []):
            ratio = (" · " + x["ratio_text"]) if x.get("ratio_text") and x.get("ratio") not in (None, 0) else ""
            out.append((x.get("public_date") or "", "GOVERNANCE", (x.get("title") or x.get("code") or "") + ratio))
        seen, uniq = set(), []
        for r in sorted(out, key=lambda r: r[0], reverse=True):
            k = (r[0], re.sub(r"\s+", "", str(r[2])).lower())       # vendor lặp tin, khác nhau khoảng trắng
            if k not in seen:
                seen.add(k)
                uniq.append(r)
        return uniq[:12]

    def filings_card(self):
        live = self.live_filings()
        rows = [M.s10_row(i, [dmy(d), tier("T2")], cat, title) for i, (d, cat, title) in enumerate(live)]
        if len(live) < 4:
            vs = [x for x in (self.S.vietstock["rows"].get(self.tk) or []) if str(x.get("year")) == "2026"][:6]
            vmap = {"BCTC": "BCTC", "BCTN": "BCTN", "DHCD": "AGM", "BC_QuanTri": "GOVERNANCE", "IR_KQKD": "KQKD"}
            rows += [M.s10_row(len(rows) + i, ["năm 2026", tier("T2", self.S.vietstock["asof"])],
                               vmap.get(x.get("filing_type"), "OTHER"), x.get("title")) for i, x in enumerate(vs)]
        if not rows:
            rows.append(h("tr", None, h("td", {"padding": "9px 10px"}, can_data(
                "không có CBTT/insider/sự kiện vốn sau 08/05 trong kho"), a={"colSpan": 3})))
        if self.D.filings.get(self.tk):
            rows.append(h("tr", {"borderBottom": "1px solid " + C.rule}, h("td", {
                "padding": "7px 10px", "color": C.inkM, "fontSize": 9, "letterSpacing": ".1em"},
                "— bản lưu vietstock ≤08/05/2026 (V21) —", v21_mark(), a={"colSpan": 3})))
            rows += [dict(r, key="codong.arch.s10") for r in M.v21_filing_rows(self.D, self.tk, len(rows), dim=True)]
        return M.s10_card(rows, self)

    # S11
    def sources(self):
        tk = self.tk
        fr = self.S.call("freshness", tk) or {}
        sh = fr.get("shareholder") or {}
        L = self.lk
        nv = len(self.S.vietstock["rows"].get(tk) or [])
        nt = len(self.targets)
        rows = (("★ Vietcap IQ (vc_lk)", "✓ ACTIVE" if sh else "✗ THIẾU", C.forest if sh else C.vermillion,
                 ["state/vc_lk/" + tk + "/shareholder · insider · events-v2 · news — ", self.asof_text(), tier("T2")]),
                ("Lăng kính lk_hoso", "✓ ACTIVE" if L.get("ok") else "✗ THIẾU", C.forest if L.get("ok") else
                 C.vermillion, ["data/lk_hoso/" + tk + ".json — FFT/VWAP/pattern/Toàn Vũ · dựng ",
                                dmy_hm(L.get("tao_luc")) or "—"]),
                ("Vietstock tài liệu", "✓ ACTIVE" if nv else "✗ THIẾU", C.forest if nv else C.vermillion,
                 [VS_FILE + " · ", str(nv), " mục", tier("T2", self.S.vietstock["asof"])]),
                ("Sell-side TP", "✓ ACTIVE" if nt > 1 else "⚠ MỎNG", C.forest if nt > 1 else C.ochre,
                 ["hhp_forecast_tickers + vc_lk details — ", str(nt), " TP", tier("E")]),
                ("Capital IQ S&P", "⚠ ĐÓNG BĂNG", C.vermillion,
                 "Q4/25 · V21 12/05 — không còn phiên Chrome; chỉ dùng ở chế độ v21"))
        return ["SOURCE MAP (5 nguồn)", upd_mark()], rows

    def pattern_q(self, tree):
        """Mã ngoài 30 mã Toàn Vũ: mọi 'Pattern A/B/C/D' gắn với mã này (kể cả câu V21 của Deep-dive) → 'Pattern X?'
        như screener (DESIGN §8.4); câu định nghĩa phương pháp dùng chung mọi mã được miễn."""
        if self.tk in set(self.S.tv30):
            return tree
        skip = self.S.pattern_exempt

        def fix(node):
            kids = node.get("k") if isinstance(node, dict) else None
            for i, c in enumerate(kids or []):
                if isinstance(c, str):
                    if c not in skip and _PAT_Q.search(c):
                        kids[i] = _PAT_Q.sub(lambda m: "%s %s?" % (m.group(1), m.group(2)), c)
                else:
                    fix(c)
        fix(tree)
        return tree

    def csv_extra(self):
        r0 = self.rows_h[0] if self.rows_h else {}
        ld = self.S.call("leader", self.tk)
        px = self.px
        return {"top1": r0.get("name"), "top1_pct": r0["pct_pub"].text if ok(r0.get("pct_pub")) else None,
                "top1_ngay": r0.get("public_date"), "chu_tich": ld.value if ok(ld) else None,
                "gia": px.value if ok(px) else None, "gia_ngay": px.asof if ok(px) else None}
