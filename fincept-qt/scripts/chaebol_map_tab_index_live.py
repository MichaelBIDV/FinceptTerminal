#!/usr/bin/env python3
"""
chaebol_map_tab_index_live — lớp dữ liệu mode live cho tab VNINDEX / VN30 (chaebol_map_tab_index).

Luật (DESIGN §0.3–0.7, §6; nhiệm vụ tab index 27/09/2026):
- Giá tuần: INDEX_DATA V21 (FiinTrade ≤08/05/2026, đóng băng) + tuần sống tới phiên cuối (index_weekly_spliced;
  VN-Index = vc_lk gap-chart, VN30 = vnstore nen_ngay) — FACT-T2; %tuần EST.
- Dòng tiền sau 08/05: chỉ NN + tự doanh là số thật, cộng theo rổ (basket_weekly_flow adjust=True: KL từng mã quy
  về số cp hiện hành qua GDKHQ chia/thưởng/cổ tức CP/quyền mua, EST, ghi độ phủ);
  Cá nhân / Tổ chức nội = [CẦN DATA]; phần dư −(NN+TD) chỉ ghi là phần dư.
- Nhận định pha/stance V21 giữ nguyên + V21·12/05 (CỔNG đang DỪNG); claim đo được chấm lại + bằng chứng + bậc.
- Dữ kiện đã đổi: viết lại theo facts_f6 / dossier (khoá "index" của cap_nhat_<ngày>.index.json), dấu ↻.
Mọi số hiển thị mang nhãn bậc hoặc là [CẦN DATA]. Không mạng, chỉ đọc kho qua chaebol_map_data.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, timedelta

from chaebol_map_dom import (C, F_MONO, TIER_COLORS, TIER_SHORT, alpha, h, js_string, js_sum, norm_tier, sign_fixed,
                             status_pill, tier, to_fixed, to_locale, upd_mark, v21_mark)
from chaebol_map_dom import can_data as _can_data

import chaebol_map_tab_index as IX

CUT = "2026-05-08"
CAP_NOTE = {"fontSize": 9, "color": C.inkM, "fontFamily": F_MONO, "letterSpacing": ".04em", "lineHeight": 1.6,
            "marginTop": 8}
SRC_FACTS = "fincept_bridge/chaebol_map_spec/facts_f6_market_calendar.json"

# Nguyên văn V21 "SSI Research cập nhật 9/5: base case mục tiêu 1,920 (+0.3%), bear 1,650" không ghi horizon →
# chính sách chấm claim: thiếu horizon thì không ĐẠT/BỊ BÁC được, dù giá đã chạm mức → CHƯA RÕ + bằng chứng.
SSI_STATUS = "CHƯA RÕ"

# Nội dung mặc định cho mục dossier (khi dossier vắng); cùng nội dung với cap_nhat_2026-09-27.index.json.
# khoá: (mã dữ kiện, câu viết lại, bản ngắn cho ô bảng / đoạn READING, các vế có ngày riêng [(chữ, asof)] | None)
FACT_TEXT = {
    "liquidity": ("F6-008", "Thanh khoản không còn ở vùng kỷ lục: GTGD bình quân tuần 14–18/09 là 19,0 nghìn tỷ "
                            "đồng/phiên (tuần FTSE), các tuần trước quanh 15 nghìn tỷ; luỹ kế tới 11/09 thấp hơn 8,5% "
                            "so với cùng kỳ",
                  "GTGD bq tuần 14–18/09 19,0 nghìn tỷ/phiên (tuần FTSE; các tuần trước ~15), YTD −8,5% y/y",
                  [("GTGD bq tuần 14–18/09 19,0 nghìn tỷ/phiên (tuần FTSE)", "2026-09-18"),
                   ("; các tuần trước ~15 nghìn tỷ, YTD −8,5% y/y (luỹ kế tới 11/09)", "2026-09-11")]),
    "foreign": ("F6-009", "NN bán ròng 91,3 nghìn tỷ đồng từ đầu năm (tới 18/09); sở hữu NN chạm đáy 13,33% (21/08)",
                "NN bán ròng 91,3 nghìn tỷ YTD", None),
    "rates": ("F6-023", "Fed tăng 25 điểm cơ bản lên 3,75–4,00% ngày 16/09/2026", "Fed +25bp 16/09", None),
    "rates_vn": ("F6-025", "NHNN giữ lãi suất điều hành, OMO vẫn 4,5%; liên ngân hàng qua đêm 1,10% (24/09)",
                 "NHNN giữ OMO 4,5%", None),
    "phase": ("F6-006", "Q3 có nhịp giảm từ đỉnh rồi hồi một phần; bộ chỉ báo nội bộ 26/09: xu hướng giảm (điểm xu "
                        "hướng 20), 32,7% số mã trên MA50, chế độ né rủi ro điểm 27,7/100. Gọi đây là pha 3 hay pha 4 "
                        "là suy luận, chưa có quy tắc số để chấm",
              "chỉ báo nội bộ 26/09: xu hướng giảm, 32,7% mã trên MA50, chế độ né rủi ro 27,7/100", None),
}


def can_data(detail=None):
    """[CẦN DATA…] không ngắt dòng giữa '[CẦN' và 'DATA]' (whiteSpace nowrap); mode v21 → None."""
    node = _can_data(detail)
    if node is not None:
        node["s"] = {**node.get("s", {}), "whiteSpace": "nowrap"}
    return node


def ssi_check(D):
    """SSI 9/5 base 1,920 / bear 1,650 trên VN-Index sau 08/05: đỉnh/đáy đóng, đáy trong phiên, phiên cuối,
    đã chạm mức hay chưa (trạng thái claim luôn SSI_STATUS — xem chú thích hằng)."""
    e = D.index_extremes("VNINDEX", CUT)
    if e["peak"].can:
        return None
    cols = D._cols_of("VNINDEX", "gap-chart")
    pts = [(x, d) for x, d in zip(cols.col("l"), cols.dates) if d >= CUT and x is not None]
    lo = min(pts) if pts else None
    pk, mn = e["peak"], e["min"]
    return {"peak": pk, "min": mn, "last": e["last"], "lo": lo, "base_hit": pk.value >= 1920,
            "bear_hit": mn.value <= 1650 or (lo is not None and lo[0] <= 1650)}


def _dmy(d):
    return "%s/%s/%s" % (d[8:10], d[5:7], d[:4])


def _dm(d, lead=True):
    return ("%s/%s" % (d[8:10], d[5:7])) if lead else ("%d/%d" % (int(d[8:10]), int(d[5:7])))


def _wk(mon, end):
    """'21–25/09' (cùng tháng) hoặc '28/09–02/10'."""
    return ("%d–%s" % (int(mon[8:10]), _dm(end))) if mon[5:7] == end[5:7] else "%s–%s" % (_dm(mon), _dm(end))


def _num(x, frac=2):
    return to_locale(x, "en-US", min_frac=frac, max_frac=frac)


def svg_tier(tag, asof=None):
    """Nhãn bậc trong chữ SVG (tspan 7px, màu bậc) — span HTML không đặt được trong <text>."""
    t = norm_tier(tag)
    sd = _dm(asof) if asof and len(str(asof)) >= 10 else None
    node = h("tspan", None, " " + TIER_SHORT[t] + ("·" + sd if sd else ""),
             a={"fill": TIER_COLORS[t], "fontSize": "7", "fontFamily": F_MONO})
    node["_tier"] = t
    return node


class Live:
    """Số sống + câu viết lại cho một chỉ số. Mọi lỗi dữ liệu → [CẦN DATA] + ctx.warn, không làm hỏng tab."""

    def __init__(self, ctx, index, rows_v21, K):
        self.ctx, self.index, self.K, self.D = ctx, index, K, ctx.data
        self.v21rows = rows_v21
        self.basket = "VN30" if index == "VN30" else "VNINDEX"
        self.dz = (ctx.dossier or {}).get("index") or {}
        self.srcname = "VCI" if index == "VN30" else "Vietcap"
        self.rows, self.cut_i, self.cov, self.flow_src = list(rows_v21), len(rows_v21) - 1, None, None
        self.conv, self.lw = None, {}
        self.ok = False
        if self.D is None:
            ctx.warn("không có chaebol_map_data — giữ chuỗi V21, số mới = [CẦN DATA]")
            return
        try:
            self._splice()
            self.ok = True
        except Exception as exc:  # dữ liệu hỏng không được làm hỏng tab
            ctx.warn("nối chuỗi tuần %s lỗi: %s: %s" % (index, type(exc).__name__, exc))

    # ── dữ liệu ─────────────────────────────────────────────────────────────

    def _splice(self):
        D = self.D
        sp = D.index_weekly_spliced(self.index, flows=False)
        if sp.can:
            raise ValueError(sp.note or "index_weekly_spliced trả [CẦN DATA]")
        # adjust=True (§6.1 #16): KL phiên trước GDKHQ chia/thưởng/cổ tức CP/quyền mua quy về số cp hiện hành —
        # cộng KL thô thì cửa sổ vắt qua GDKHQ trộn hai cơ sở (VHM ×2 06/08, VPB ×1,26 24/09…)
        bw = D.basket_weekly_flow(self.basket, start=CUT, adjust=True)
        fl = {} if bw.can else {r["monday"]: r for r in bw.value or []}
        rows = []
        for r in sp.value:
            if r["src"] == "V21":
                rows.append([r["date"], r["c"], r["chg"], r["ca"], r["tc"], r["td"], r["nn"], "V21"])
                continue
            dd = date.fromisoformat(r["date"])
            f = self.lw = fl.get((dd - timedelta(days=dd.weekday())).isoformat()) or {}
            td = D.round_half(f["td_khop_vol"] / 1e6, 2) if f.get("td_khop_vol") is not None else None
            nn = D.round_half(f["nn_vol"] / 1e6, 2) if f.get("nn_vol") is not None else None
            rows.append([r["date"], r["c"], r["chg"], None, None, td, nn, "live", f.get("n_ma"), f.get("n_td")])
        self.rows = rows
        self.cut_i = max(i for i, r in enumerate(rows) if r[7] == "V21")
        m = re.search(r"độ phủ (\d+)/(\d+)", bw.note or "")
        live = [r for r in rows if r[7] == "live"]
        ntd = [r[9] for r in live if r[9] is not None]
        self.cov = {"n": int(m.group(1)) if m else None, "m": int(m.group(2)) if m else None,
                    "td_min": min(ntd) if ntd else None, "td_max": max(ntd) if ntd else None,
                    "missing": sum(1 for r in live if r[5] is None or r[6] is None)}
        q = re.search(r"quy về số cp hiện hành[^;]*? ở (\d+) mã(?:: ([A-Z0-9, ]+))?", bw.note or "")
        self.conv = {"n": int(q.group(1)), "ma": re.findall(r"[A-Z0-9]+", q.group(2) or "")} if q else None
        self.flow_src = bw.src
        self.price_src = sp.src

    @property
    def last(self):
        return self.rows[-1]

    def _cov_text(self):
        c = self.cov or {}
        if not c.get("n"):
            return "độ phủ [CẦN DATA]"
        what = "mã HOSE" if self.basket == "VNINDEX" else "mã rổ VN30 hiện hành"
        return "%d/%d %s" % (c["n"], c["m"], what)

    def _conv_text(self):
        """'12/30 mã: ACB, BID, …' — mã có KL quy về số cp hiện hành (liệt kê khi ≤ 15 mã); None khi không đọc được."""
        c, n = self.conv, (self.cov or {}).get("n")
        if not c:
            return None
        return ("%d/%s mã" % (c["n"], n) if n else "%d mã" % c["n"]) + (
            ": " + ", ".join(c["ma"]) if c["ma"] and len(c["ma"]) <= 15 else "")

    def _t(self, tag, asof=None):
        """tier() an toàn cho bậc đọc từ kho/dossier: bậc lạ → U + cảnh báo (không làm hỏng tab)."""
        try:
            return tier(tag, asof)
        except (ValueError, KeyError):
            self.ctx.warn("bậc lạ %r — hiện U" % (tag,))
            return tier("U", asof)

    def _safe(self, fn, what):
        try:
            return fn()
        except Exception as exc:
            self.ctx.warn("%s lỗi: %s: %s" % (what, type(exc).__name__, exc))
            return None

    def _ext(self, idx, since, end=None):
        return self._safe(lambda: self.D.index_extremes(idx, since, end), "index_extremes %s" % idx) if self.ok else None

    def cycle5(self, idx="VNINDEX"):
        """Chu kỳ ⑤ đo lại trên chuỗi idx (mặc định VN-Index — khung BSC): đỉnh đóng từ 2025, đáy đóng trước đỉnh,
        biên độ (EST), P/E tại đỉnh (chỉ VN-Index)."""
        memo = self.__dict__.setdefault("_c5", {})
        if idx in memo:
            return memo[idx]
        out = {}
        e = self._ext(idx, "2025-01-01")
        if e and not e["peak"].can:
            pk = e["peak"]
            e2 = self._ext(idx, "2025-01-01", pk.asof)
            tr = e2["min"] if e2 else None
            pe = (self._safe(lambda: self.D.index_pe_pb("VNINDEX", pk.asof), "P/E tại đỉnh") or {}) \
                if idx == "VNINDEX" else {}
            out = {"peak": pk, "trough": tr, "pe": pe.get("pe"),
                   "pct": (pk.value / tr.value - 1) * 100 if tr is not None and not tr.can else None}
        memo[idx] = out
        return out

    def flow_dates(self):
        """Phiên cuối có số tự doanh / NN của từng mã rổ trong tuần sống cuối (DESIGN §9: ghi đúng ngày của số —
        tự doanh vendor chậm 1–3 phiên, một phần mã dừng sớm). Rổ như basket_weekly_flow (mã có price-history)."""
        if "_fd" not in self.__dict__:
            self._fd = self._safe(self._flow_dates, "ngày phiên cuối NN/TD") if self.ok else None
        return self._fd

    def _flow_dates(self):
        D, end = self.D, self.last[0]
        mon = (date.fromisoformat(end) - timedelta(days=date.fromisoformat(end).weekday())).isoformat()
        mem = ([r[0] for r in D.db_query("SELECT symbol FROM ma WHERE san='HOSE' AND loai='stock' ORDER BY symbol")]
               if self.basket == "VNINDEX" else D.basket(self.basket).value or [])
        have = [t for t in mem if (D.vc_dir() / t / "price-history.json").exists()]
        cnt = {"td": Counter(), "nn": Counter()}
        for t in have:
            pr, ph = D._cols_of(t, "proprietary-history"), D.price_history(t)
            cnt["td"][max((x for x in (pr.dates if pr else []) if mon <= x <= end), default=None)] += 1
            cnt["nn"][max((x for x, v in zip(ph.dates, ph.col("foreignNetVolumeTotal")) if mon <= x <= end
                           and v is not None), default=None) if ph else None] += 1
        out = {"n": len(have), "mon": mon, "end": end}
        for k, c in cnt.items():
            out[k + "_cnt"] = sorted(((d, n) for d, n in c.items() if d), reverse=True)
            out[k + "_none"], out[k] = c.get(None, 0), (out[k + "_cnt"][0][0] if out[k + "_cnt"] else None)
        return out

    def _flow_asof(self, k):
        """Ngày của số Σ rổ kênh k ('td' | 'nn'): phiên cuối có bản ghi trong tuần cuối (nn_last/td_last của
        basket_weekly_flow; dự phòng đếm theo mã) — không phải ngày tuần của chỉ số."""
        return self.lw.get(k + "_last") or (self.flow_dates() or {}).get(k) or self.last[0]

    def _dates_text(self):
        """'Tuần 21–25/09: tự doanh có số tới 24/09 ở 16/30 mã, 22/09 ở 14 (…); NN có số tới 25/09 ở 30/30 mã'."""
        fd = self.flow_dates()
        if not fd:
            return None

        def dist(k, what):
            s = "%s có số tới " % what + ", ".join("%s ở %d%s" % (_dm(d), n, "/%d mã" % fd["n"] if i == 0 else "")
                                                  for i, (d, n) in enumerate(fd[k + "_cnt"])) if fd[k + "_cnt"] else \
                "%s: không mã nào có số" % what
            return s + (", %d mã không có số tuần này" % fd[k + "_none"] if fd[k + "_none"] else "")
        short = (" (tuần chưa đủ phiên cho tự doanh: chưa mã nào có %s)" % _dm(fd["end"])
                 if fd["td"] and fd["td"] < fd["end"] else "")
        return "Tuần %s: %s%s; %s" % (_wk(fd["mon"], fd["end"]), dist("td", "tự doanh"), short, dist("nn", "NN"))

    # ── S1 ──────────────────────────────────────────────────────────────────

    def s1_sub(self):
        first, last = self.rows[0], self.last
        if not self.ok:
            return ["%s weekly bars · FiinTrade %s→2026-05-08 (đóng băng)" % (len(self.rows), first[0]), tier("T2", CUT),
                    " · tuần sau 08/05: ", can_data("không nối được chuỗi giá")]
        return ["%s weekly bars · %s năm · FiinTrade %s→2026-05-08 (đóng băng) · %s %s→%s (giá)" % (
            len(self.rows), IX.years_covered(first[0], last[0]), first[0], self.srcname,
            _dm(self.rows[self.cut_i + 1][0]), _dmy(last[0])), tier("T2", last[0]), upd_mark()]

    def s1_grid(self, hc):
        first, last = self.rows[0], self.last
        stats = []
        if self.ok:
            chg = last[2]
            stats.append(IX.Stat("GIÁ ĐÓNG CỬA (%s)" % _dm(last[0], False),
                                 [to_locale(last[1], "en-US", max_frac=2), tier("T2", last[0])],
                                 sub=[sign_fixed(chg, 2) + "%", tier("E")],
                                 color=C.forest if chg >= 0 else C.vermillion))
        else:
            stats.append(IX.Stat("GIÁ ĐÓNG CỬA", [can_data("chuỗi giá")], color=C.vermillion))
        stats.append(IX.Stat("TỪ ĐÁY LỊCH SỬ", ["+" + to_fixed(((last[1] / first[1]) - 1) * 100, 0) + "%", tier("E")],
                             sub=["vs %s (%s)" % (first[0], js_string(first[1])), tier("T2")], color=C.gold))
        stats.append(IX.Stat("WEEKLY BARS", [js_string(len(self.rows)), tier("E")],
                             sub="%s-%s" % (first[0][:4], last[0][:4]), color=C.ink2))
        stats.append(IX.Stat("DATA SOURCE", "DUAL", sub=["FiinTrade ≤8/5 · %s ≥11/5" % self.srcname, upd_mark()],
                             color=hc))
        stats.append(self._pe_stat())
        return h("div", {"display": "grid", "gridTemplateColumns": "repeat(5, 1fr)", "gap": 12, "marginBottom": 16},
                 *stats)

    def _pe_stat(self):
        if self.index != "VNINDEX" or not self.ok:
            return IX.Stat("P/E · P/B", [can_data()], sub="vc_lk không có ratio-daily cho %s" % self.index,
                           color=C.ochre)
        pp = self._safe(lambda: self.D.index_pe_pb("VNINDEX"), "index_pe_pb") or {}
        pe, pb, z, mu = pp.get("pe"), pp.get("pb"), pp.get("pe_z"), pp.get("pe_mu")
        if pe is None or pe.can:
            return IX.Stat("P/E · P/B", [can_data()], sub="thiếu lk_thitruong.pe_vni / ratio-daily", color=C.ochre)
        val = [to_fixed(pe.value, 2) + "×", tier(pe.tier, pe.asof)]
        if pb is not None and not pb.can:
            val += [" · " + to_fixed(pb.value, 2) + "×", tier(pb.tier, pb.asof)]
        sub = None
        if z is not None and not z.can and mu is not None and not mu.can:
            sub = ["z %sσ · μ 10 năm %s×" % (sign_fixed(z.value, 2), to_fixed(mu.value, 2)), tier(z.tier)]
        return IX.Stat("P/E · P/B (%s)" % _dm(pe.asof, False), val, sub=sub, color=C.ochre)

    # ── S2 ──────────────────────────────────────────────────────────────────

    def cycles_live(self):
        """BSC_CYCLES với hàng ⑤ đo lại (đỉnh 18/05 → period đóng ở T5/2026, biên độ E). Dải ⑤ vẽ theo NGÀY: từ
        đầu tuần chứa đáy 09/04/2025 (điểm đóng tuần trước) tới cuối tuần chứa đỉnh — không theo luật năm của JSX
        (luật năm phủ 01/2025→01/2026, lệch cả đáy lẫn đỉnh)."""
        cy = [dict(c) for c in self.K["BSC"]]
        c5 = self.cycle5()
        if len(cy) >= 5 and c5.get("pct") is not None:
            pk = c5["peak"].asof
            cy[4]["period"] = "T4/2025-T%d/%s" % (int(pk[5:7]), pk[:4])
            cy[4]["chg"] = "+" + to_fixed(c5["pct"], 1) + "%"
            a = next((j for j, r in enumerate(self.rows) if r[0] >= c5["trough"].asof), None)
            b = next((j for j, r in enumerate(self.rows) if r[0] >= pk), None)
            if a is not None and b is not None:
                cy[4]["_ab"] = (max(a - 1, 0), b)
        return cy

    def price_chart(self, hc, cycles):
        rows = [r[:2] for r in self.rows]
        cy = self.cycles_live() if cycles is not None else None
        mk = (self.cut_i, "08/05 ⟂ FiinTrade | %s" % self.srcname) if self.ok else None
        return IX.mini_chart(rows, 1200, 300, hc, "#5b8db8", cy, self.K["COLORS"], self.K["CIRC"], marker=mk)

    def s2_sub(self):
        c5 = self.cycle5()
        head = (["Inline SVG · ①–④ BSC", tier("T3")] if self.index == "VNINDEX" else
                ["Inline SVG · chu kỳ BSC ①–⑤ là của VN-Index, không vẽ trên VN30"])
        if c5.get("pct") is None:
            return head + [" · ⑤ ", can_data()]
        pk = c5["peak"].asof
        return head + [" · ⑤ %sđo lại T4/25–%d/%d/%s +%s%%" % (
            "(VN-Index) " if self.index != "VNINDEX" else "", int(pk[8:10]), int(pk[5:7]), pk[2:4],
            to_fixed(c5["pct"], 1)), tier("E"), upd_mark()]

    def price_caption(self):
        if not self.ok:
            return h("div", CAP_NOTE, "Giá tuần FiinTrade tới 08/05/2026", tier("T2", CUT), " · sau đó ",
                     can_data("không nối được chuỗi"))
        c5 = self.cycle5()
        kids = ["Giá đóng tuần: FiinTrade tới 08/05/2026", tier("T2", CUT), " · %s %s→%s" % (
            "vc_lk/VNINDEX/gap-chart" if self.index == "VNINDEX" else "vnstore nen_ngay (VCI)",
            _dm(self.rows[self.cut_i + 1][0]), _dmy(self.last[0])), tier("T2", self.last[0]),
                " · %tuần tự tính", tier("E")]
        if self.index == "VNINDEX" and c5.get("pct") is not None:
            kids += [" · nhãn dải ①–④ = BSC", tier("T3"), "; ⑤ đo lại từ đáy đóng %s (%s) tới đỉnh %s (%s)" % (
                _num(c5["trough"].value), _dmy(c5["trough"].asof), _num(c5["peak"].value), _dmy(c5["peak"].asof)),
                     tier("T2", c5["peak"].asof), " = +%s%%" % to_fixed(c5["pct"], 1), tier("E"),
                     " — dải ⑤ vẽ theo ngày hai mốc này (tuần chứa đáy → tuần chứa đỉnh); ①–④ theo năm như JSX "
                     "(V21 không vẽ ⑤ vì regex năm cuối hỏng)", upd_mark()]
        elif self.index != "VNINDEX":
            v = self.cycle5(self.index)
            kids += [" · 5 chu kỳ BSC là của VN-Index nên không vẽ trên VN30"]
            if v.get("pct") is not None:
                kids += ["; cùng cách đo trên VN30: đáy đóng %s (%s)" % (_num(v["trough"].value), _dmy(v["trough"].asof)),
                         tier("T2", v["trough"].asof), " → đỉnh đóng %s (%s)" % (_num(v["peak"].value),
                                                                                _dmy(v["peak"].asof)),
                         tier("T2", v["peak"].asof), " = +%s%%" % to_fixed(v["pct"], 1), tier("E"), upd_mark()]
        return h("div", CAP_NOTE, *kids)

    def bsc_title(self, base):
        """Tiêu đề thẻ BSC: tab VN30 ghi rõ số là của VN-Index (bảng dùng chung khung BSC của VN-Index)."""
        return base if self.index == "VNINDEX" else base + " · SỐ CỦA VN-INDEX"

    @staticmethod
    def phase_signal(sig):
        """Chữ giữ chỗ 'TBD' của V21 → tiếng Việt (không chấm lại pha: F6-006 CHƯA RÕ, CỔNG DỪNG)."""
        return "chưa xác định (bản V21 để trống)" if str(sig).strip().upper() == "TBD" else sig

    # ── S3 ──────────────────────────────────────────────────────────────────

    def flow_rows(self):
        return [r[:7] for r in self.rows]

    def flow_chart(self):
        mk = (self.cut_i, "08/05 ⟂ FiinTrade | Σ rổ") if self.ok else None
        return IX.flow_chart(self.flow_rows(), 1200, 280, legend=self._legend, marker=mk)

    def _legend(self, w, sums):
        """Chú giải giữ khung V21 (200×68 ở góc phải trên, translate(w−220, PAD−4)) để không che đuôi các đường;
        mỗi dòng chỉ thêm nhãn bậc·ngày của số. Nguồn từng kênh + CN/TC [CẦN DATA] nằm ở chú thích dưới biểu đồ."""
        tags = [("T2", CUT), ("T2", CUT), ("E", self._flow_asof("td")), ("E", self._flow_asof("nn"))]
        if not self.ok:
            tags[2], tags[3] = ("T2", CUT), ("T2", CUT)
        kids = [h("rect", None, a={"x": "0", "y": "0", "width": "200", "height": "68", "fill": "#13131a",
                                   "stroke": "#26242c", "strokeWidth": "0.5", "opacity": "0.95"})]
        for k, ((nm, col, _), s, (tg, asof)) in enumerate(zip(IX.FLOW_SERIES, sums, tags)):
            kids.append(h("text", None, "━ %s: " % nm, to_fixed(s, 0), "M", svg_tier(tg, asof),
                          a={"x": "6", "y": str(14 * (k + 1)), "fontSize": "9", "fill": col, "fontFamily": F_MONO}))
        return h("g", None, *kids, a={"transform": "translate(%s, %s)" % (w - 220, IX.PAD - 4)})

    def s3_sub(self):
        return ["KL khớp ròng cộng dồn · CN/TC FiinTrade ≤08/05", tier("T2", CUT),
                " · TD/NN + Σ rổ (KL quy đổi quyền)", tier("E"), upd_mark()]

    def flow_caption(self):
        kids = ["Chú giải: Cá nhân, Tổ chức = FiinTrade, dừng ở 08/05/2026", tier("T2", CUT)]
        if self.ok:
            c = self.cov or {}
            kids += ["; Tự doanh (khớp) và Nước ngoài = FiinTrade tới 08/05 rồi nối Σ %s có cache vc_lk" %
                     self._cov_text(), tier("E"),
                     " (rổ hiện hành áp mọi tuần; tự doanh có bản ghi ở %s–%s mã/tuần; NN sau 08/05 gồm thoả thuận, "
                     "FiinTrade V21 chỉ khớp → điểm nối lệch ngữ nghĩa). " % (c.get("td_min"), c.get("td_max"))]
            cv = self._conv_text()
            kids += ["KL từng mã sau 08/05 quy về số cp hiện hành qua GDKHQ chia/thưởng/cổ tức CP/quyền mua%s; "
                     "FiinTrade ≤08/05 giữ KL thô lúc đó" % (" (%s)" % cv if cv else ""), tier("E"), upd_mark(), ". "]
            dt = self._dates_text()
            if dt:
                kids += [dt, tier("E"), ". "]
            if c.get("missing"):
                kids += ["%d tuần thiếu NN/TD → đường dừng. " % c["missing"]]
        else:
            kids += ["; Tự doanh, Nước ngoài sau 08/05: ", can_data("không nối được chuỗi"), ". "]
        kids += ["Cá nhân / Tổ chức nội sau 08/05: ", can_data("không có nguồn cấp chỉ số"),
                 " — phần dư −(NN+TD) chỉ là phần dư, không phải kênh thật. FiinTrade ≤08/05 giữ đóng băng."]
        out = [r for r in self.v21rows if r[0] == "2021-08-13" and r[3] > 1000]
        if out:
            r = out[0]
            kids += [" Điểm ngoại lai Cá nhân 13/08/2021 = +%sM" % to_fixed(r[3], 2), tier("T2"),
                     " (lỗi trong tệp FiinTrade phiên 09/08/2021; ước đúng ≈ %sM = −(TC+TD+NN)" % to_fixed(
                         -(r[4] + r[5] + r[6]), 2), tier("E"), ") giữ nguyên như bản gốc."]
        return h("div", CAP_NOTE, *kids)

    # ── S4 ──────────────────────────────────────────────────────────────────

    def s4_rows(self):
        v = self.v21rows
        t2 = lambda: tier("T2", CUT)  # noqa: E731
        grp = {"padding": "8px 10px 4px", "fontSize": 9, "letterSpacing": ".12em", "color": C.ochre}
        out = [h("tr", None, h("td", grp, "FIINTRADE PL TUẦN — ĐÓNG BĂNG TỚI 08/05/2026", a={"colSpan": 6}))]
        for n, c in zip((5, 30, 60), IX.cum_windows(v)):
            lbl = ["%d tuần (%s–%s)" % (n, _dm(v[-n][0]), _dm(v[-1][0]) + "/" + v[-1][0][2:4]),
                   upd_mark() if n == 5 else None]
            out.append(IX.cum_row(lbl, c, tiers=t2, clean=True))
        if not self.ok:
            out.append(h("tr", None, h("td", grp, "CỬA SỔ SAU 08/05: ", can_data("không nối được chuỗi"),
                                       a={"colSpan": 6})))
            return out
        out.append(h("tr", None, h("td", grp, "CỬA SỔ MỚI TỚI %s — NN/TD Σ RỔ (E), CÁ NHÂN/TỔ CHỨC [CẦN DATA]" %
                                   _dmy(self.last[0]), a={"colSpan": 6})))
        rows = self.rows
        for n in (5, 30, 60):
            win = rows[-n:]
            lbl = "%d tuần (%s–%s)" % (n, _dm(win[0][0]) + ("/" + win[0][0][2:4] if n > 5 else ""),
                                       _dm(win[-1][0]) + "/" + win[-1][0][2:4])
            tds, nns = [r[5] for r in win], [r[6] for r in win]
            cells = [IX.td_label(lbl), self._td_can(), self._td_can()]
            ok = all(x is not None for x in tds + nns)
            if ok:
                td, nn = js_sum(tds), js_sum(nns)
                cells += [IX.td_num(td, tier("E", self._flow_asof("td")), clean=True),
                          IX.td_num(nn, tier("E", self._flow_asof("nn")), clean=True),
                          IX.td_sum("dư " + IX.zfix(sign_fixed(-(nn + td), 1)), tier("E"))]
            else:
                cells += [self._td_can(), self._td_can(), IX.td_sum(can_data())]
            out.append(h("tr", {"borderBottom": "1px solid " + alpha(C.rule, "80")}, *cells))
        return out

    @staticmethod
    def _td_can():
        return h("td", {"padding": "10px 10px", "textAlign": "right", "fontSize": 9}, can_data())

    def s4_caption(self):
        kids = ["Nhãn '5 tuần (4-8/5/26)' của V21 thực là 10/04→08/05 (đã sửa)", upd_mark(),
                ". Cửa sổ 30/60 tuần mới nối FiinTrade (NN chỉ khớp) với Σ rổ vc_lk (NN khớp + thoả thuận) → số nối "
                "nguồn", tier("E"), "; cột cuối = phần dư −(NN+TD), không phải tổng kiểm 4 kênh."]
        if self.ok:
            kids += [" NN/TD sau 08/05 tính theo số cp hiện hành (quy đổi quyền qua GDKHQ chia/thưởng/cổ tức CP/quyền "
                     "mua), FiinTrade ≤08/05 là KL thô", tier("E"), upd_mark(), "."]
        fd = self.flow_dates() if self.ok else None
        if fd and fd["td"] and fd["td"] < fd["end"]:
            kids += [" Tuần cuối %s: tự doanh mới có số tới %s và chỉ ở một phần mã (thiếu phiên sau đó) — nhãn "
                     "ngày của cột Tự doanh là ngày số thật, không phải ngày tuần; chi tiết ở chú thích biểu đồ dòng "
                     "tiền." % (_wk(fd["mon"], fd["end"]), _dm(fd["td"]))]
        return h("div", CAP_NOTE, *kids)

    # ── S5 ──────────────────────────────────────────────────────────────────

    def v21_mark(self):
        return v21_mark()

    def s5_sub(self):
        return [IX.S5_SUB_V21, v21_mark()]

    def _peak_check(self, c):
        """Đỉnh ①–④ khớp đỉnh đóng gap-chart trong dải năm của period (±1 điểm) → T2, ngược lại giữ T3 (BSC)."""
        try:
            y0, y1 = IX.cycle_bounds(c["period"])
            cols = self.D._cols_of("VNINDEX", "gap-chart")
            pts = [(x, d) for x, d in zip(cols.col("c"), cols.dates) if str(y0) <= d[:4] <= str(y1) and x is not None]
            if pts and abs(max(pts)[0] - float(c["peak"])) < 1:
                return self._t("T2")
        except Exception:  # noqa: BLE001 — kiểm phụ, lỗi thì giữ bậc gốc
            pass
        return self._t("T3")

    def bsc_cells(self, i, c):
        if i < 4:
            return {"chg": [c["chg"], tier("T3")], "peak": [c["peak"], self._peak_check(c) if self.ok else tier("T3")],
                    "pe": [IX._jsv(c["pe_peak"]), "×", tier("T3")], "gtgd": [c["gtgd"], tier("T3")],
                    "driver": [c["driver"], tier("T3")]}
        c5 = self.cycle5()
        cells = {"gtgd": [can_data()], "driver": [c["driver"], " "] + self._claim_inline("foreign") +
                 ["; "] + self._claim_inline("rates", pill=False) + ["; "] + self._claim_inline("rates_vn", pill=False)}
        if c5.get("pct") is None:
            cells.update({"chg": [can_data()], "peak": [can_data()], "pe": [can_data()]})
            return cells
        pk, pe = c5["peak"], c5.get("pe")
        cells.update({"period": [self.cycles_live()[4]["period"], upd_mark()],
                      "chg": ["+" + to_fixed(c5["pct"], 1) + "%", tier("E")],
                      "peak": ["%s (%d/%d/%s)" % (to_fixed(pk.value, 2), int(pk.asof[8:10]), int(pk.asof[5:7]),
                                                  pk.asof[2:4]), tier("T2", pk.asof)],
                      "pe": [to_fixed(pe.value, 2) + "×", tier(pe.tier, pe.asof)] if pe is not None and not pe.can
                      else [can_data()]})
        return cells

    # dữ kiện F6 (dossier ưu tiên, dự phòng facts_f6) ──────────────────────

    def _fact(self, key):
        ent = (self.dz.get("facts") or {}).get(key)
        if isinstance(ent, dict) and ent.get("src"):
            return ent
        try:
            f = self.D.facts_index()["by_id"].get(FACT_TEXT[key][0]) if self.D is not None else None
        except Exception:  # noqa: BLE001
            f = None
        return _fact_entry(key, f) if f else None

    def _claim_inline(self, key, pill=True):
        f = self._fact(key)
        if f is None:
            return [can_data("dữ kiện %s" % key)]
        st = f.get("status")
        return ([status_pill(st), " "] if pill and st else []) + [f.get("short") or f["text"],
                                                                  self._t(f["tier"], f["asof"])]

    def phase_note(self):
        e = self._ext(self.index, CUT)
        f = self._fact("phase")
        kids = [status_pill((f or {}).get("status") or "CHƯA RÕ"), " "]
        if e and not e["peak"].can:
            pk, tr = e["peak"], e["trough_after_peak"]
            name = "VN30" if self.index == "VN30" else "VN-Index"
            kids += ["%s sau 08/05: đỉnh đóng %s" % (name, _num(pk.value)), tier("T2", pk.asof),
                     " → đáy %s" % _num(tr.value), tier("T2", tr.asof),
                     " (%s%%" % to_fixed((tr.value / pk.value - 1) * 100, 2), tier("E"), "). "]
        kids += ([f["text"], self._t(f["tier"], f["asof"])] if f else [can_data("F6-006")])
        kids += [" — nhãn pha giữ nguyên bản lưu", v21_mark(), ", CỔNG DỪNG nên không chấm lại.", upd_mark()]
        return h("div", {"fontSize": 11, "color": C.inkD, "lineHeight": 1.65, "marginBottom": 14,
                         "padding": "8px 12px", "border": "1px dashed " + C.rule, "borderRadius": 2}, *kids)

    def reading_title(self):
        return ["★ READING HÔM NAY (10/5/2026) · ĐỐI CHIẾU %s" % _dmy(self.last[0]) if self.ok else
                "★ READING HÔM NAY (10/5/2026)", upd_mark()]

    def _cong(self):
        return self._safe(lambda: self.D.cong(), "cong()") if self.D is not None else None

    def reading(self, label):
        cg = self._cong() or {}
        stop = bool(cg.get("stop")) or not cg
        line = h("div", {"fontFamily": F_MONO, "fontSize": 9.5, "letterSpacing": ".06em", "marginBottom": 6,
                         "color": C.vermillion if stop else C.gold},
                 (cg.get("text") or "CỔNG: [CẦN DATA — không đọc được lk_thitruong.cong]"),
                 " → pha chu kỳ không chấm lại" if stop else None)
        p = [h("strong", {"color": C.gold}, IX.READING_STRONG), v21_mark(), " "]
        p += self._reading_cycle() + self._reading_index(label) + self._reading_liq() + self._reading_pe()
        p += self._reading_ssi() + self._reading_vcb()
        return h("div", None, line, h("div", {"fontSize": 11.5, "color": C.ink, "lineHeight": 1.7}, *p))

    def _reading_cycle(self):
        c5 = self.cycle5()
        if c5.get("pct") is None:
            return ["Đo lại ⑤: ", can_data("chuỗi VN-Index"), ". "]
        return ["Đo lại ⑤ (VN-Index): %s" % _num(c5["trough"].value), tier("T2", c5["trough"].asof),
                " → %s" % _num(c5["peak"].value), tier("T2", c5["peak"].asof),
                " = +%s%%" % to_fixed(c5["pct"], 1), tier("E"), ".", upd_mark(), " "]

    def _reading_index(self, label):
        e = self._ext(self.index, CUT)
        if not e or e["peak"].can:
            return [label, " sau 8/5: ", can_data("chuỗi giá"), ". "]
        last, pk, tr = e["last"], e["peak"], e["trough_after_peak"]
        if self.index == "VN30":
            y = self._ext("VN30", "2026-01-01") or {}
            yp = y.get("peak")
            out = ["VN30 đóng 8/5 = %s" % _num(self.v21rows[-1][1]), tier("T2", CUT), " không phải ATH"]
            if yp is not None and not yp.can:
                out += [" (đỉnh %s" % _num(yp.value), tier("T2", yp.asof), ")"]
            out += ["; đáy sau mốc %s" % _num(tr.value), tier("T2", tr.asof), ", nay ",
                    h("strong", {"color": C.forest}, _num(last.value)), tier("T2", last.asof), ".", upd_mark(), " "]
            return out
        return ["%s đỉnh đóng %s" % (label, _num(pk.value)), tier("T2", pk.asof),
                " rồi %s%%" % to_fixed((tr.value / pk.value - 1) * 100, 2), tier("E"),
                " về %s" % _num(tr.value), tier("T2", tr.asof), ", nay ",
                h("strong", {"color": C.forest}, _num(last.value)), tier("T2", last.asof), ".", upd_mark(), " "]

    def _reading_liq(self):
        f = self._fact("liquidity")
        if f is None:
            return ["GTGD: ", can_data("F6-008"), ". "]
        parts = f.get("parts") or []   # mỗi vế một ngày của chính con số (19,0 nghìn tỷ ·18/09; YTD ·11/09)
        body = ([x for p in parts for x in (p["text"], self._t(f["tier"], p.get("asof") or f["asof"]))] if parts
                else [f.get("short") or f["text"], self._t(f["tier"], f["asof"])])
        return body + ["; mốc 'ATH 36,814 tỷ/phiên' chưa kiểm được", tier("U"), ".", upd_mark(), " "]

    def _reading_pe(self):
        pes = [c["pe_peak"] for c in self.K["BSC"][:4] if isinstance(c.get("pe_peak"), (int, float))]
        out = []
        if len(pes) == 4:
            out += ["P/E đỉnh 4 chu kỳ trước TB %s×" % to_fixed(js_sum(pes) / 4, 1), tier("E"),
                    " (%s× là đỉnh ①" % IX._jsv(pes[0]), tier("T3"), ")"]
        pp = self._safe(lambda: self.D.index_pe_pb("VNINDEX"), "index_pe_pb") if self.ok else None
        pe, z = (pp or {}).get("pe"), (pp or {}).get("pe_z")
        if pe is not None and not pe.can:
            out += ["; P/E nay %s×" % to_fixed(pe.value, 2), tier(pe.tier, pe.asof)]
            if z is not None and not z.can:
                out += [" (z %sσ" % sign_fixed(z.value, 2), tier("E"), ")"]
        else:
            out += ["; P/E nay ", can_data()]
        return out + [".", upd_mark(), " 'UTAD signal Q3/26 watch'", v21_mark(), " "]

    def _reading_ssi(self):
        s = self._safe(lambda: ssi_check(self.D), "SSI 9/5") if self.ok else None
        if s is None:
            return ["SSI 9/5 base 1,920 / bear 1,650: ", can_data("chuỗi VN-Index"), ". "]
        pk, mn, lo, last = s["peak"], s["min"], s["lo"], s["last"]
        out = ["SSI 9/5 (nguyên văn không ghi horizon): base 1,920 ", status_pill(SSI_STATUS),
               " (%s: đỉnh đóng %s" % ("đã chạm" if s["base_hit"] else "chưa chạm", _num(pk.value)), tier("T2", pk.asof),
               ", nay %s" % _num(last.value), tier("T2", last.asof), ") · bear 1,650 ", status_pill(SSI_STATUS),
               " (%s: đáy đóng %s" % ("đã chạm" if s["bear_hit"] else "chưa chạm", _num(mn.value)), tier("T2", mn.asof)]
        if lo is not None:
            out += [", trong phiên %s" % _num(lo[0]), tier("T2", lo[1])]
        return out + [")", upd_mark(), " — risk/reward asymmetric XẤU.", v21_mark(), " "]

    def vcb_pb(self):
        """P/B VCB (vc_lk ratio-daily, dòng trùng ngày giữ dòng đầu): tại 08/05, đáy trước 08/05, đáy sau, cuối."""
        _, rows = self.D.vc("VCB", "ratio-daily")
        seen, pts = set(), []
        for r in rows or []:
            d = str(r.get("tradingDate"))[:10]
            if d not in seen and isinstance(r.get("pb"), (int, float)):
                seen.add(d)
                pts.append((d, r["pb"]))
        pts.sort()
        before = [p for p in pts if p[0] <= CUT]
        after = [p for p in pts if p[0] > CUT]
        if not before or not after:
            return None
        return {"at": before[-1], "min_before": min(before, key=lambda p: p[1]),
                "min_after": min(after, key=lambda p: p[1]), "last": pts[-1], "first": pts[0]}

    def _reading_vcb(self):
        v = self._safe(self.vcb_pb, "P/B VCB") if self.ok else None
        if v is None:
            return ["VCB P/B 2.0× = 10-yr low: ", can_data("vc_lk/VCB/ratio-daily"), "."]
        t = lambda p: tier("T2", p[0])  # noqa: E731
        return ["VCB P/B 2.0× = 10-yr low ", status_pill("CHƯA RÕ"), " (Vietcap %s× ngày 8/5" % to_fixed(v["at"][1], 2),
                t(v["at"]), "; đáy trước đó %s×" % to_fixed(v["min_before"][1], 2), t(v["min_before"]),
                ", đáy mới %s×" % to_fixed(v["min_after"][1], 2), t(v["min_after"]),
                ", nay %s×" % to_fixed(v["last"][1], 2), t(v["last"]), ")", upd_mark(),
                " → best deep-value pick trong môi trường định giá đỉnh.", v21_mark()]

    # ── S6 ──────────────────────────────────────────────────────────────────

    def cong_block(self):
        cg = self._cong() or {}
        text = cg.get("text") or "CỔNG: [CẦN DATA — không đọc được lk_thitruong.cong] · không kết luận per-mã"
        stop = bool(cg.get("stop")) or not cg or "[CẦN DATA" in text or "DỪNG" in text
        asof = cg.get("as_of")
        return h("div", {"fontFamily": F_MONO, "fontSize": 10, "letterSpacing": ".1em", "lineHeight": 1.6,
                         "marginBottom": 14, "color": C.vermillion if stop else C.gold},
                 text, (" · tính đến " + _dmy(asof)) if asof else None,
                 self._t(cg["tier"], asof) if cg.get("tier") else None,
                 " · dòng tiền cấp chỉ số: 2/4 kênh (NN + tự doanh) — Cá nhân/Tổ chức nội ",
                 can_data())

    def method_items(self, items):
        out = list(items)
        out[0] = (items[0][0], [" — theo Lăng Kính v1.7 chỉ còn 2/4 kênh có nguồn (khối ngoại + tự doanh), hạ khỏi "
                                "PRIMARY SIGNAL; Cá nhân/Tổ chức nội sau 08/05 ", can_data(), "; dòng nội cấp thị "
                                "trường = −(NN + TD) như phần dư. Sum ≈ 0 chỉ đúng từ 10/2020.", upd_mark()])
        return out

    def cutover_paras(self):
        last = self.last[0] if self.ok else None
        p1 = h("div", IX._PARA, h("span", {"color": C.gold, "fontWeight": 700}, "≤ 08/05/2026 (historical):"),
               " FiinTrade Pro xlsx — đóng băng, giữ nguyên, không thay ngược", tier("T2", CUT), ".", upd_mark())
        kids = [h("span", {"color": C.forest, "fontWeight": 700}, "≥ 11/05/2026 (forward):"),
                " giá tuần từ cache nội bộ — VN-Index: vc_lk/VNINDEX/gap-chart (Vietcap), VN30: vnstore nen_ngay (VCI)"]
        if last:
            kids += [", tới ", h("strong", None, _dmy(last)), tier("T2", last)]
        else:
            kids += [": ", can_data("không nối được chuỗi")]
        kids += ["; NN + tự doanh = Σ rổ cache vc_lk", tier("E"), ". NgườiQuanSát.vn chưa từng nối bar nào — bỏ. "
                 "Cá nhân / Tổ chức nội: ", can_data(), upd_mark()]
        return [p1, h("div", IX._PARA, *kids)]

    def code_lines(self, lines):
        out = list(lines)
        if not self.ok:
            return out
        try:
            g = self.D._cols_of("VNINDEX", "gap-chart")
            v3, _ = self.D._index_cols("VN30")
            c = self.cov or {}
            out += ["Nguồn sống (dựng %s):" % _dmy(self.ctx.today.isoformat()),
                    "• vc_lk/VNINDEX/gap-chart.json · nến ngày %s→%s" % (_dmy(g.dates[0]), _dmy(g.dates[-1])),
                    "• vnstore/vn_store.db nen_ngay VN30 · %s→%s" % (_dmy(v3.dates[0]), _dmy(v3.dates[-1])),
                    "• Σ vc_lk/<mã>/price-history + proprietary-history · %s (tự doanh %s–%s mã/tuần%s)" % (
                        self._cov_text(), c.get("td_min"), c.get("td_max"),
                        "; KL quy về số cp hiện hành ở %d mã" % self.conv["n"] if self.conv else "")]
        except Exception as exc:  # noqa: BLE001
            self.ctx.warn("liệt kê nguồn sống lỗi: %s" % exc)
        return out

    # ── CSV ────────────────────────────────────────────────────────────────

    def csv(self):
        if not self.ok:
            return None
        cols = ["chi_so", "tuan_ket_thuc", "dong_cua", "chg_pct", "ca_M", "tc_M", "td_M", "nn_M", "nguon", "bac"]
        out = [cols]
        for r in self.rows[self.cut_i:]:
            live = r[7] == "live"
            out.append([self.index, r[0], r[1], r[2], r[3], r[4], r[5], r[6],
                        ("%s + Σ rổ %s" % (self.price_src, self._cov_text())) if live else "FiinTrade (V21)",
                        "giá FACT-T2; chg/NN/TD EST (NN/TD quy về số cp hiện hành); CN/TC CẦN DATA" if live
                        else "FACT-T2"])
        return out


# ── dossier (DESIGN §7): mục facts.<key>; dossier_part() ở chaebol_map_tab_index_dossier ───────


def _fact_entry(key, f):
    """Mục dossier 'facts.<key>' từ bản ghi facts_f6 f (câu viết lại ở FACT_TEXT; vế có ngày riêng → 'parts')."""
    fid, text, short, parts = FACT_TEXT[key]
    ent = {"text": text, "short": short, "status": f.get("trang_thai"), "tier": f.get("bac"), "asof": f.get("ngay"),
           "src": (f.get("nguon_list") or [SRC_FACTS])[0], "fact": fid}
    if parts:
        ent["parts"] = [{"text": t, "asof": d} for t, d in parts]
    return ent

