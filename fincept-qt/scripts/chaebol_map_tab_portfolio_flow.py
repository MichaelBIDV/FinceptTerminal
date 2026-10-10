#!/usr/bin/env python3
"""
chaebol_map_tab_portfolio_flow — phần DÒNG TIỀN của lớp live tab 08 (DANH MỤC) + helper định dạng dùng chung của nhóm
portfolio. Tách khỏi chaebol_map_tab_portfolio_live (27/09, final_check §6.2 #10: tệp ≤ ~800 dòng, api_python §9.7).

Tệp này là lớp DƯỚI: chỉ nhập chaebol_map_dom/shell; chaebol_map_tab_portfolio_live nhập helper + FlowMixin từ đây
(không nhập ngược, không vòng lúc nạp). FlowMixin không tự đứng: dùng các hàm truy cập của Live (_call, ok, num, price,
pct, events, _win).

Luật (DESIGN §6.5, §6.6, §9): sau 08/05 chỉ NN (khớp + thoả thuận) và tự doanh (khớp) là số thật; Cá nhân/Tổ chức/SIG
= [CẦN DATA]; phần dư −(NN+TD) nhãn E. KL cộng qua GDKHQ thưởng/cổ tức CP quy về số cp hiện hành (nhãn E). Nhãn TD mang
ngày bản ghi tự doanh cuối, kèm độ phủ "x/60 phiên có bản ghi".
"""
from __future__ import annotations

import re
from dataclasses import replace

from chaebol_map_dom import C, F_MONO, can_data, h, sign_fixed, tier, to_fixed
from chaebol_map_shell import FlowSignal

_NOTE = {"fontSize": 10, "fontFamily": F_MONO, "color": C.inkD, "letterSpacing": ".04em", "lineHeight": 1.6}
_TD_TO = re.compile(r"tự doanh tới (\d{2})/(\d{2})/(\d{4})")          # ghi chú prop_net (chaebol_map_data)
_TD_COV = re.compile(r"(\d+)/(\d+) phiên có bản ghi tự doanh")
_BAR_MAX = 6          # FlowBar: ô số rộng 80px — "±xxx.xM" (7 ký tự) + nhãn có ngày tràn ô → bỏ ngày ở nhãn


# ── helper định dạng dùng chung (tab_portfolio_live nhập lại từ đây) ─────────


def _pct(v):
    return sign_fixed(v, 1) + "%"


def _pn(v):
    return C.forest if v >= 0 else C.vermillion


def _dm(iso):
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(iso or ""))
    return "%s/%s" % (m.group(3), m.group(2)) if m else str(iso or "")


def _dmy(iso):
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(iso or ""))
    return "%s/%s/%s" % (m.group(3), m.group(2), m.group(1)) if m else str(iso or "")


def _k(x):
    """Mức giá nghìn đồng kiểu trang: 22.73 → '22.7' (bỏ .0)."""
    s = to_fixed(x, 1)
    return s[:-2] if s.endswith(".0") else s


class FlowMixin:
    """Dòng tiền 60 phiên của tab 08: FlowSignal sống (thẻ vị thế), dòng vc_lk ở Section B, tổng NN ô VIC,VHM,VRE."""

    # ── quy đổi KL qua thưởng/cổ tức CP, ngày thật của tự doanh ─────────────

    def _segments(self, tk, n=60):
        """Cửa sổ n phiên (như chaebol_map_data._win) cắt tại GDKHQ thưởng/cổ tức CP: ([(đầu, cuối, hệ số về số cp
        hiện hành)], dates, [chữ]). Không có sự kiện trong cửa sổ → ([], dates, [])."""
        ph = self._call("price_history", tk)
        if ph is None or len(ph) < 2:
            return [], None, []
        dates, b = ph.dates, len(ph.dates) - 1
        a = max(0, b - n + 1)
        cuts = [(next(j for j in range(a, b + 1) if dates[j] >= d), 1 + r, "×%s trước %s" % (_k(1 + r), txt))
                for d, kind, r, txt in self.events(tk, dates[a]) if kind == "stock" and r and d <= dates[b]]
        segs, m, end = [], 1.0, b
        for i, mm, _ in reversed(cuts):          # đoạn sau GDKHQ cuối ×1; lùi qua mỗi GDKHQ nhân thêm (1 + tỉ lệ)
            segs.append((i, end, m))
            m, end = m * mm, i - 1
        return (segs + [(a, end, m)] if cuts else []), dates, [t for _, _, t in cuts]

    def _seg_sum(self, fn, tk, segs, dates, **kw):
        """Σ KL (cp) theo đoạn × hệ số. Đoạn tự doanh không có bản ghi nào → 0 (lớp dữ liệu không điền 0 phiên vắng)."""
        tot = 0.0
        for s, e, m in segs:
            r = self._call(fn, tk, e - s + 1, dates[e], **kw) or {}
            if self.ok(r.get("vol")):
                tot += r["vol"].value * m
            elif not (fn == "prop_net" and r.get("n_co") == 0):
                return None
        return tot

    def _flow4(self, tk, n=60):
        """flow4 (triệu cp) với NN/TD quy về số cp hiện hành khi cửa sổ cắt qua GDKHQ thưởng/cổ tức CP (DESIGN §6.6:
        so qua mốc quyền phải quy đổi). Số đã quy đổi mang nhãn E; không quy đổi được → giữ số thô + ghi 'KL chưa quy đổi'.
        Trả (f4, chú thích quy đổi | None)."""
        f4 = self._call("flow4", tk, n)
        if not f4:
            return None, None
        segs, dates, txt = self._segments(tk, n)
        if not segs:
            return f4, None
        out = dict(f4)
        nn, td = f4.get("nn"), f4.get("td")
        adj = "KL quy về số cp hiện hành: " + " · ".join(txt)
        vn = self._seg_sum("foreign_net", tk, segs, dates) if self.ok(nn) else None
        vt = self._seg_sum("prop_net", tk, segs, dates, kind="khop") if self.ok(td) else None
        if vn is None or (self.ok(td) and vt is None):
            return f4, "KL chưa quy đổi qua " + " · ".join(t.split(" trước ", 1)[-1] for t in txt)
        out["nn"] = replace(nn, value=vn / 1e6, text=to_fixed(vn / 1e6, 1), tier="EST", note="%s; %s" % (nn.note, adj))
        if self.ok(td):
            out["td"] = replace(td, value=vt / 1e6, text=to_fixed(vt / 1e6, 1), tier="EST", note="%s; %s" % (td.note, adj))
            du = -(out["nn"].value + out["td"].value)
            out["du"] = replace(f4["du"], value=du, text=to_fixed(du, 1)) if self.ok(f4.get("du")) else f4.get("du")
        return out, adj

    @staticmethod
    def _td_info(td):
        """Từ ghi chú prop_net: (ngày cuối CÓ bản ghi tự doanh — không phải ngày cuối cửa sổ, 'x/60 phiên có bản ghi')."""
        note, a = str(getattr(td, "note", "") or ""), getattr(td, "asof", None)
        m, c = _TD_TO.search(note), _TD_COV.search(note)
        d = "%s-%s-%s" % (m.group(3), m.group(2), m.group(1)) if m else None
        return (min(d, a) if d and a else (d or a)), ("%s/%s phiên có bản ghi" % c.groups() if c else None)

    # ── hiển thị ────────────────────────────────────────────────────────────

    def _flow_live_data(self, tk, n=60):
        f4, adj = self._flow4(tk, n)
        if not f4:
            return None
        ph = self._call("price_history", tk)
        perf = None
        if ph is not None and len(ph) > 1:
            b = len(ph) - 1
            perf = self.pct(tk, ph.dates[max(0, b - n)], ph.dates[b])
        px = self.price(tk)
        val = lambda v: v.value if self.ok(v) else None  # noqa: E731
        fl = {"sig": None, "ca60": None, "to60": None, "td60": val(f4.get("td")), "nn60": val(f4.get("nn")),
              "date": f4.get("to"), "px": val(px), "perf60": val(perf)}
        tiers = {}
        td = f4.get("td")
        for k, v, d, bar in (("td60", td, self._td_info(td)[0], True), ("nn60", f4.get("nn"), None, True),
                             ("px", px, None, False), ("perf60", perf, None, False)):
            if self.ok(v):     # ô số FlowBar rộng 80px: số ≥ 7 ký tự + nhãn có ngày tràn ô → nhãn không ngày
                tiers[k] = (v.tier, None if bar and len(sign_fixed(v.value, 1) + "M") > _BAR_MAX else d or v.asof)
        return f4, fl, tiers, adj

    def flow_live(self, tk):
        got = self._flow_live_data(tk)
        if not got:
            return h("div", _NOTE, "Dòng tiền sau 08/05: ", can_data("flow4 không chạy"))
        f4, fl, tiers, adj = got
        head = "FLOW %s PHIÊN · vc_lk %s→%s · NN khớp+TT · TD khớp" % (f4.get("n") or "?", _dm(f4.get("from")),
                                                                     _dm(f4.get("to")))
        du, td = f4.get("du"), f4.get("td")
        d_td, cov = self._td_info(td) if self.ok(td) else (None, None)
        note = h("div", {**_NOTE, "fontSize": 9, "color": C.inkM, "marginTop": -4, "marginBottom": 10},
                 "phần dư −(NN+TD) ", *self.num(du, ("+" if self.ok(du) and du.value >= 0 else "") +
                                                (du.text + "M" if self.ok(du) else "")),
                 " — không phải kênh thật; Cá nhân/Tổ chức & SIG 4 kênh sau 08/05 = [CẦN DATA]",
                 (" · tự doanh: %s, dữ liệu tới %s" % (cov, _dmy(d_td))) if cov else None,
                 (" · " + adj) if adj else None)
        return h("div", None, FlowSignal(fl, head=head, tiers=tiers), note, key="p08.flow.live." + tk)

    def add_flow_live(self, tk):
        got = self._flow_live_data(tk)
        if not got:
            return None
        f4, fl, tiers, adj = got
        nn, td = f4.get("nn"), f4.get("td")

        def span(v, txt, w=600, asof=None):
            return h("span", {"color": _pn(v.value) if self.ok(v) else C.ink, "fontWeight": w},
                     *([txt, tier(v.tier, asof or v.asof)] if self.ok(v) else self.num(v, txt)))
        pv = self.pct(tk, *self._win(tk))
        d_td, cov = self._td_info(td) if self.ok(td) else (None, None)
        return h("div", {"fontSize": 10, "color": C.inkD, "fontFamily": F_MONO, "marginBottom": 10,
                         "padding": "6px 10px", "background": C.parch, "borderRadius": 2, "letterSpacing": ".06em"},
                 "vc_lk %s→%s · Δ%sp " % (_dm(f4.get("from")), _dm(f4.get("to")), f4.get("n")),
                 span(pv, _pct(pv.value) if self.ok(pv) else "", 700),
                 " · SIG ", can_data(), " · Tổ chức ", can_data(),
                 " · NN ", span(nn, (sign_fixed(nn.value, 1) + "M") if self.ok(nn) else ""),
                 " · TD ", span(td, (sign_fixed(td.value, 1) + "M") if self.ok(td) else "", asof=d_td),
                 (" (%s)" % cov) if cov else None, (" · " + adj) if adj else None)
