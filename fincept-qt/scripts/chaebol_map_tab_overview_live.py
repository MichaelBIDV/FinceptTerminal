#!/usr/bin/env python3
"""
chaebol_map_tab_overview_live — lớp cập nhật (chỉ mode live) cho tab `overview` + `chaebol` của chaebol_map.

Nguồn: (1) số sống qua chaebol_map_data (vc_lk: NN/tự doanh/giá điều chỉnh/vốn hoá; vnstore rổ VN30);
(2) câu viết lại + trạng thái claim từ dossier mảnh cap_nhat_<ngày>.overview.json (khoá `overview.ov` / `overview.map`,
mỗi phần có tier/asof/src dẫn id dữ kiện facts_f*.json; phần có thể chứa số sống {since:MÃ}/{nn60:MÃ} và trạng thái
claim tab 09 {c20:Cxx}). Luật (DESIGN
§0.3–0.6, §6): mọi số mới có nhãn bậc hoặc [CẦN DATA]; nhận định/stance V21 giữ nguyên + V21·12/05 (CỔNG v1.7 DỪNG) —
không chấm BỊ BÁC khi V21 không nêu điều kiện/kỳ hạn đo được, dữ kiện U tối đa CHƯA RÕ; dòng tiền sau 08/05 chỉ NN + tự
doanh là số thật (KL quy về số cp hiện hành qua GDKHQ chia/thưởng cp), CN/TC = [CẦN DATA], phần dư −(NN+TD) nhãn E chỉ
trên đúng các phiên TD có đủ; nhãn Pattern A/B của cụm có mã ngoài 30 mã Toàn Vũ mang hậu tố '?'; mệnh đề pháp lý nêu
tên cá nhân không thêm mới khi thiếu FACT-T1. Mọi hàm trả nút/None; lỗi được chaebol_map_tab_overview._hook bắt và ghi
cảnh báo.
"""
from __future__ import annotations

import re
from math import prod

from chaebol_map_dom import (C, F_MONO, F_SERIF, can_data, h, sign_fixed, status_pill, tier, to_fixed, to_locale,
                             upd_mark, v21_mark)

V21_DATE = "2026-05-08"          # thanh cuối V21 (FiinTrade ≤08/05)
_VALUE = re.compile(r"\d+\.\d+|\d[\d,]*\s*(?:%|M\b|B\b|K\b|cp\b|tỷ|triệu|đ\b)")   # "số liệu" (không phải mã/NQ79/V20)
# số sống trong câu dossier: {since:MÃ} = % giá điều chỉnh từ 08/05 (E); {nn60:MÃ} = NN 60 phiên (T2; E khi quy đổi);
# {c20:Cxx} = trạng thái claim CLAIMS_C01_C20 do tab 09 chấm (khoá claims20 của dossier hợp nhất) — chỉ dẫn lại
_PH = re.compile(r"\{(since|nn60|c20):([A-Z0-9]{3,4})\}")
_RANK = ("FACT-T1", "FACT-T2", "SS-T3", "EST", "UNVERIFIED")      # bậc của một phần = bậc yếu nhất
_PATTERN = re.compile(r"\bPattern ([AB])\b(?!\?)")
_EXTRA = {"fontSize": 11, "color": C.inkD, "lineHeight": 1.6, "fontFamily": F_SERIF, "marginTop": 4,
          "paddingLeft": 10, "borderLeft": "1px solid " + C.ochre + "80", "fontStyle": "normal", "fontWeight": 400}
_SMALL = {"fontSize": 9, "color": C.inkM, "fontFamily": F_MONO, "letterSpacing": ".05em", "lineHeight": 1.6}
_GROUP_COLOR = {"gold": C.gold, "ink2": C.ink2, "vermillion": C.vermillion, "ochre": C.ochre, "orange": "#f97316"}
_TIER_SVG = {"FACT-T1": ("T1", "#3d7a4e"), "FACT-T2": ("T2", "#5b8db8"), "SS-T3": ("T3", "#caa75c"),
             "EST": ("E", "#d4a039"), "UNVERIFIED": ("U", "#c5392f")}


def _dm(iso):
    """'2026-09-25' → '25/09/2026'."""
    return "%s/%s/%s" % (iso[8:10], iso[5:7], iso[:4]) if iso and len(iso) >= 10 else str(iso)


def _pct(v, digits=1):
    return sign_fixed(v, digits, strict=True) + "%"


def _ddmm(iso):
    """'2026-09-25' → '25/09'."""
    return "%s/%s" % (iso[8:10], iso[5:7]) if iso and len(iso) >= 10 else str(iso)


class Live:
    def __init__(self, ctx):
        self.ctx = ctx
        self.D = ctx.data
        dz = (ctx.dossier or {}).get("overview") or {}
        self.ov = dz.get("ov") or {}
        self.map = dz.get("map") or {}
        if not dz:
            ctx.warn("dossier thiếu khoá 'overview' (cap_nhat_<ngày>.overview.json) — câu V21 giữ nguyên, chỉ có số sống")
        self._memo = {}

    # ── tiện ích dữ liệu ─────────────────────────────────────────────────────
    def _call(self, key, fn, *a, **kw):
        if key not in self._memo:
            try:
                self._memo[key] = fn(*a, **kw) if self.D is not None else None
            except Exception as exc:  # noqa: BLE001
                self.ctx.warn("chaebol_map_data.%s%r lỗi: %s" % (getattr(fn, "__name__", "?"), a, exc))
                self._memo[key] = None
        return self._memo[key]

    def since(self, tk):
        """% thay đổi giá điều chỉnh từ phiên 08/05/2026 (EST) → V hoặc None."""
        return self._call(("since", tk), self.D.pct_change, tk, V21_DATE) if self.D else None

    def perf60(self, tk):
        """% thay đổi 60 phiên tới phiên cuối (giá điều chỉnh, EST)."""
        if self.D is None:
            return None
        ph = self._call(("ph", tk), self.D.price_history, tk)
        if ph is None or len(getattr(ph, "dates", [])) < 61:
            return None
        return self._call(("p60", tk), self.D.pct_change, tk, ph.dates[-61])

    def num(self, v, text, tag=None):
        """Số + nhãn bậc; thiếu → [CẦN DATA — lý do]."""
        if v is None or getattr(v, "value", None) is None:
            return [can_data(getattr(v, "note", None) or "thiếu nguồn")]
        return [text, tier(tag or v.tier)]

    @staticmethod
    def tag(kind):
        """Nhãn khối V21 giữ nguyên (DESIGN §0.6): bậc gốc + dấu V21·12/05. Bậc gốc theo page_p4 §6: FLOW (FiinTrade
        theo trang) = T2; CHAEBOL_GROUPS/ENTITY note/timeline/insight/chính trị = U; phân loại nội bộ (pha, đếm) = E."""
        t = {"v21U": "U", "v21T2": "T2", "v21E": "E", "U": "U", "E": "E", "v21": None}[kind]
        return [tier(t) if t else None, v21_mark() if kind.startswith("v21") else None]

    # ── dòng tiền NN / TD n phiên (KL quy về số cp hiện hành) ────────────────
    def nn60(self, tk, n=60):
        """{nn, td (M cp, quy đổi), n, n_co, to, td_to, du, du_n, ev} hoặc None (không có price-history/NN)."""
        return self._call(("nn60", tk, n), self._nn60, tk, n) if self.D is not None else None

    def _nn60(self, tk, n):
        D = self.D
        ph = D.price_history(tk)
        if ph is None or not len(ph) or D.foreign_net(tk, n)["vol"].value is None:
            return None
        b = len(ph) - 1
        a = max(0, b - n + 1)
        evs = self._rights(ph, tk, a)
        nn = self._seg(D.foreign_net, tk, ph, a, b, evs)[0]
        td, n_co = self._seg(D.prop_net, tk, ph, a, b, evs, kind="khop")
        last = next((b - j for j in range(b - a + 1) if D.prop_net(tk, 1, ph.dates[b - j], kind="khop")["n_co"]), None)
        # TD vendor chậm 1–3 phiên: phần dư chỉ khi TD đủ phiên liên tục từ đầu cửa sổ tới b−jc (tính trên đúng đoạn đó)
        jc = next((j for j in range(min(6, b - a + 1))
                   if D.prop_net(tk, b - j - a + 1, ph.dates[b - j], kind="khop")["complete"]), None)
        du = None if jc is None else -(self._seg(D.foreign_net, tk, ph, a, b - jc, evs)[0]
                                        + self._seg(D.prop_net, tk, ph, a, b - jc, evs, kind="khop")[0])
        return {"nn": nn / 1e6, "td": td / 1e6 if n_co else None, "n": b - a + 1, "n_co": n_co, "to": ph.dates[b],
                "td_to": ph.dates[last] if last is not None else None,
                "du": du / 1e6 if du is not None else None, "du_n": None if jc is None else b - jc - a + 1,
                "ev": [(d, m) for _, m, d in evs]}

    def _rights(self, ph, tk, a):
        """GDKHQ chia/thưởng/quyền mua cp trong (phiên a, cuối]: phiên có bước giá điều chỉnh VÀ totalShares tăng →
        hệ số = min(Δ số cp, 1/bước giá). Bước giá không kèm tăng cp (cổ tức tiền) và tăng cp không kèm bước giá (ESOP,
        riêng lẻ, bán cp quỹ) không quy đổi KL. → [(chỉ số phiên, hệ số, ngày)]."""
        S = ph.col("totalShares")
        out = []
        for d, step in self.D.adj_steps(tk, ph.dates[a]):
            e = ph.at(d)
            s0 = next((S[i] for i in range(e - 1, -1, -1) if S[i]), None)
            s1 = next((S[i] for i in range(e, len(S)) if S[i]), None)
            m = min(s1 / s0, 1 / step) if s0 and s1 and step else 1.0
            if m > 1.001:
                out.append((e, m, d))
        return out

    @staticmethod
    def _seg(fn, tk, ph, a, end, evs, **kw):
        """Σ KL của fn (foreign_net/prop_net) trên phiên [a, end], cắt đoạn tại các GDKHQ; mỗi đoạn nhân tích hệ số
        của các GDKHQ sau nó. → (tổng cp, số phiên có bản ghi — chỉ prop_net có)."""
        tot, n_co, lo = 0.0, 0, a
        for hi in [e for e, _, _ in evs if a < e <= end] + [end + 1]:
            r = fn(tk, hi - lo, ph.dates[hi - 1], **kw)
            tot += (r["vol"].value or 0) * prod(m for e, m, _ in evs if e >= hi)
            n_co += r.get("n_co", 0)
            lo = hi
        return tot, n_co

    def _tv30(self):
        return self._call("tv30", self.D.tv30) if self.D is not None else None

    def outside_tv30(self, tks):
        """Mã ngoài 30 mã Toàn Vũ (không có danh sách → coi như ngoài hết)."""
        tv = self._tv30()
        return [t for t in tks if not tv or t not in tv]

    def pattern_q(self, text, tks):
        """'Pattern A/B' → 'Pattern A?/B?' khi cụm có mã ngoài 30 mã Toàn Vũ (CLAUDE.md §6 luật 4, DESIGN §8.4)."""
        return _PATTERN.sub(r"Pattern \1?", text) if self.outside_tv30(tks) else text

    def pattern_note(self, tks):
        out = self.outside_tv30(tks)
        return h("span", {**_SMALL, "fontStyle": "normal", "marginLeft": 4},
                 "'?' = cụm có mã ngoài 30 mã Toàn Vũ (%s): nhãn pattern là giả thuyết." % ", ".join(out)) if out else None

    # ── dossier ───────────────────────────────────────────────────────────────
    def entry(self, *path):
        node = {"ov": self.ov, "map": self.map}.get(path[0])
        for k in path[1:]:
            node = node.get(k) if isinstance(node, dict) else None
        return node if isinstance(node, dict) else None

    def render(self, e, pill=True, mark=True, sep="; "):
        """Mục dossier {parts:[{text,tier}], status} → [Pill trạng thái, phần + nhãn bậc…, ↻]."""
        if not e:
            return None
        out = []
        if pill and e.get("status") in ("ĐẠT", "BỊ BÁC", "CHƯA RÕ", "LIVE", "HẾT HẠN"):
            out += [status_pill(e["status"]), " "]
        for i, p in enumerate(e.get("parts") or []):
            out += ([sep] if i else []) + self._part(p)
        if mark:
            out.append(upd_mark())
        return out

    def claim20(self, cid):
        """Mục claim CLAIMS_C01_C20 mà tab 09 đã chấm (khoá `claims20` của dossier hợp nhất). Tab 01 chỉ dẫn lại trạng
        thái để hai tab không lệch nhau, không tự chấm → dict có 'status' hoặc None."""
        c = ((self.ctx.dossier or {}).get("claims20") or {}).get(cid)
        return c if isinstance(c, dict) and c.get("status") else None

    def _part(self, p):
        """Một phần dossier → [chữ (số sống thay chỗ {since:MÃ} / {nn60:MÃ}, trạng thái claim thay {c20:Cxx}), nhãn bậc].
        Bậc = bậc yếu nhất giữa bậc ghi trong dossier, bậc số sống (giá điều chỉnh = E; NN quy về cp hiện hành = E,
        không quy đổi = T2) và bậc của mục claim được dẫn."""
        text, tiers, notes, out, pos = p["text"], [p["tier"]], [], [], 0
        for m in _PH.finditer(text):
            out.append(text[pos:m.start()])
            pos = m.end()
            kind, tk = m.groups()
            if kind == "c20":
                c = self.claim20(tk)
                if c is None:
                    out.append(can_data("trạng thái %s·20 ở mảnh claims" % tk))
                    continue
                out.append("%s·20 (tab 09 chấm %s)" % (tk, c["status"]))
                if c.get("tier") in _RANK:
                    tiers.append(c["tier"])
            elif kind == "since":
                v = self.since(tk)
                if v is None or v.value is None:
                    out.append(can_data("giá %s" % tk))
                    continue
                out.append(_pct(v.value))
                tiers.append("EST")
            else:
                r = self.nn60(tk)
                if r is None:
                    out.append(can_data("NN %s" % tk))
                    continue
                out.append(sign_fixed(r["nn"], 1) + "M cp")
                if r["ev"]:
                    tiers.append("EST")
                    notes.append("KL quy về cp hiện hành: " + ", ".join(
                        "GDKHQ %s ×%s" % (_ddmm(d), to_fixed(x, 3)) for d, x in r["ev"]))
        out.append(text[pos:])
        if notes:
            out.append(" (" + "; ".join(notes) + ")")
        weakest = max(tiers, key=lambda t: _RANK.index(t) if t in _RANK else len(_RANK))
        return [x for x in out if x != ""] + [tier(weakest)]

    def extra(self, *children, key=None):
        kids = [c for c in children if c]
        return h("div", _EXTRA, *kids, key=key) if kids else None

    # ════════════════════════════ 00 · TỔNG QUAN ════════════════════════════
    def thesis_sub(self):
        return "Tháng 5, 2026 · ↻ 27/09/2026"

    def trend_extra(self, i):
        if i == 1:
            return self.extra(*self.render(self.entry("ov", "trend1")) or [], key="ov.trend1.upd")
        if i == 2:
            e = self.entry("ov", "trend2")
            nums = []
            for tk in ("GEX", "GEE"):
                v = self.since(tk)
                nums += [tk + " ", *self.num(v, _pct(v.value) if v and v.value is not None else None), ", "]
            vni = self._call("vni", lambda: self.D.index_extremes("VNINDEX", V21_DATE)["since_start"])
            # Trend ② là luận điểm V21 không nêu ngưỡng/kỳ hạn → số giá chỉ để đối chiếu, không chấm ĐẠT/BỊ BÁC
            head = ["Từ 08/05 tới 25/09 (giá điều chỉnh): "] + nums[:-1] + [
                " so với VN-Index ", *self.num(vni, _pct(vni.value, 1) if vni and vni.value is not None else None),
                " — số đối chiếu, không chấm lại: luận điểm 'lên ngôi' của V21 không nêu ngưỡng hay kỳ hạn đo được",
                v21_mark(), upd_mark()]
            return self.extra(h("div", None, *head), h("div", None, *(self.render(e) or [])), key="ov.trend2.upd")
        if i == 3:
            rows = [h("div", None, *self.render(self.entry("ov", k))) for k in ("trend3_hdb", "trend3_vjc", "trend3_sg")
                    if self.entry("ov", k)]
            return self.extra(*rows, key="ov.trend3.upd")
        return None

    def thesis_footer(self):
        return None

    def bridge_flow_note(self):
        return [upd_mark(), h("span", {**_SMALL, "marginLeft": 4},
                              "nguồn đang dùng: vc_lk NN + tự doanh (T2); cá nhân/tổ chức sau 08/05 = ",
                              can_data())]

    def bridge_footer(self):
        return h("div", {**_SMALL, "marginTop": 10},
                 "Bridge V20 → V21 là bản lưu lịch sử", v21_mark(),
                 " — danh mục hiện hành xem tab 08 (Khối 11 · hdcv đặt cạnh nhau, không chọn bản; >5% NAV → Synthesis "
                 "L1+L2+L3).")

    def _flow_v21(self, acc_v21, dist_v21):
        """Không có lớp dữ liệu: giữ bảng V21 (FiinTrade ≤08/05, T2 theo trang) + nhãn, tiêu đề báo [CẦN DATA]."""
        def row(r, is_dist):
            return dict(r, nn_node=[to_fixed(r["nn"], 1) if is_dist else "+" + to_fixed(r["nn"], 1), tier("T2")],
                        perf_node=[_pct(r["perf"]), tier("T2")], n=[r["n"], tier("U"), v21_mark()])
        return {"acc": [row(r, False) for r in acc_v21], "dist": [row(r, True) for r in dist_v21],
                "title": ["✪ Top Pillar IV Flow Insights — 60 ngày tới 08/05/2026 (FiinTrade verified) · số sống ",
                          can_data("chưa có chaebol_map_data")]}

    def flow_tables(self, acc_v21, dist_v21):
        """Tính lại hai bảng Top NN 60 phiên tới phiên cuối trên vũ trụ 45 mã VN30+ của V21 ∪ rổ VN30 hiện hành;
        KL quy về số cp hiện hành trước khi xếp hạng."""
        if self.D is None:
            return self._flow_v21(acc_v21, dist_v21)
        uni = list((self.ctx.v21 or {}).get("FLOW") or {})
        b = self._call("basket", self.D.basket, "VN30")
        for tk in (b.value if b is not None and b.value else []):
            if tk not in uni:
                uni.append(tk)
        rows, miss, to = [], [], None
        for tk in uni:
            r = self.nn60(tk)
            if r is None:
                miss.append(tk)
                continue
            to = to or r["to"]
            rows.append(dict(r, tk=tk, p60=self.perf60(tk)))
        if not rows:
            return self._flow_v21(acc_v21, dist_v21)
        acc = sorted([r for r in rows if r["nn"] > 0], key=lambda r: -r["nn"])[:6]
        dist = sorted([r for r in rows if r["nn"] < 0], key=lambda r: r["nn"])[:10]
        self.flow_meta = {"to": to, "n": len(rows), "miss": miss, "uni": len(uni),
                          "ev": [(r["tk"], d, x) for r in acc + dist for d, x in r["ev"]]}

        def row(r, is_dist):
            p = r["p60"]
            perf = p.value if p is not None and p.value is not None else None
            t_nn = "EST" if r["ev"] else "FACT-T2"
            return {"tk": r["tk"], "nn": r["nn"], "perf": perf, "n": self._td_note(r, t_nn),
                    "nn_node": [(to_fixed(r["nn"], 1) if is_dist else "+" + to_fixed(r["nn"], 1)), tier(t_nn)],
                    "perf_node": (self.num(p, _pct(perf)) if perf is not None else [can_data()])}
        return {"acc": [row(r, False) for r in acc], "dist": [row(r, True) for r in dist],
                "title": "✪ Top Pillar IV Flow Insights — 60 phiên tới %s (NN vc_lk khớp + thoả thuận)" % _dm(to),
                "sub": [upd_mark()]}

    @staticmethod
    def _td_note(r, t):
        """Ô NOTE: TD khớp (cùng cơ sở cp với NN) + số phiên TD có bản ghi; phần dư −(NN+TD) chỉ khi TD đủ phiên liên
        tục từ đầu cửa sổ, tính trên đúng đoạn phiên đó (DESIGN §6.5: phần dư, không phải kênh thật)."""
        if r["td"] is None:
            return ["TD ", can_data("không có bản ghi tự doanh trong cửa sổ")]
        out = ["TD ", sign_fixed(r["td"], 1) + "M", tier(t)]
        if r["n_co"] < r["n"]:
            out.append(" (%d/%d phiên, tới %s)" % (r["n_co"], r["n"], _ddmm(r["td_to"])))
        if r["du"] is None:
            return out + [" · phần dư: TD thiếu phiên giữa kỳ, không so sánh được"]
        out += [" · phần dư ", sign_fixed(r["du"], 1) + "M", tier("E")]
        return out + ([" (cùng %d phiên)" % r["du_n"]] if r["du_n"] < r["n"] else [])

    def flow_callout_extra(self):
        m = getattr(self, "flow_meta", None)
        if not m:
            return None
        ev = []
        if m["ev"]:
            ev = ["Mã có GDKHQ chia/thưởng/quyền mua cp trong cửa sổ: KL các phiên trước GDKHQ được quy về số cp hiện "
                  "hành (hệ số = min(Δ số cp, bước giá điều chỉnh) cùng phiên), nên NN/TD của mã đó mang nhãn E — "
                  + " · ".join("%s %s ×%s" % (tk, _ddmm(d), to_fixed(x, 3)) for tk, d, x in m["ev"]), tier("E"), ". "]
        return self.extra(
            "Hai bảng trên tính lại trên %d/%d mã (45 mã VN30+ của V21 ∪ rổ VN30 hiện hành) cho 60 phiên tới %s: NN = "
            "khớp + thoả thuận (T2), TD = tự doanh khớp (T2), Δ60d trên giá điều chỉnh (E). " % (
                m["n"], m["uni"], _dm(m["to"])), *ev,
            "TD của vendor chậm 1–3 phiên và có mã thiếu phiên giữa kỳ: phần dư −(NN+TD) chỉ tính trên đúng các phiên TD "
            "có đủ (ghi số phiên); mã thiếu phiên giữa kỳ không tính phần dư. Kênh cá nhân/tổ chức sau 08/05 là ",
            can_data(), " → không kiểm lại được mệnh đề \"cá nhân SELL / NN BUY\" ở đoạn trên; FiinTrade ≤08/05 giữ "
            "đóng băng.", upd_mark(), key="ov.flows.upd")

    def phase_note(self, p):
        return self.pattern_q(p["note"], [t["tk"] for t in p.get("tk") or []])

    def phase_footer(self):
        e = self.entry("ov", "phase_basket")
        q = []
        for p in (self.ctx.v21 or {}).get("OverviewTab.jsx@L5297") or []:
            pat, out = _PATTERN.search(p.get("note", "")), self.outside_tv30([t["tk"] for t in p.get("tk") or []])
            if pat and out:
                q.append("Nhãn 'Pattern %s?' ở cột %s: có mã ngoài 30 mã Toàn Vũ (%s) — pattern là giả thuyết. " % (
                    pat.group(1), p["phase"], ", ".join(out)))
        return h("div", {**_SMALL, "marginTop": 10},
                 "Pha = đánh giá V21", v21_mark(), " — chưa chấm lại vì CỔNG v1.7 đang DỪNG. ", *q,
                 *(self.render(e, pill=False) or []), key="ov.phase.upd")

    # ════════════════════════════ 01 · CHAEBOL MAP ═══════════════════════════
    def intro_sub(self):
        return None

    def intro_extra(self):
        return self.extra("Bản cập nhật 27/09/2026: số sống vc_lk (T2/E), dữ kiện facts_f1–f6 kèm nhãn bậc; nhận định "
                          "V21 giữ nguyên có dấu", v21_mark(), "; claim đo được chấm lại bằng nhãn ĐẠT/BỊ BÁC/CHƯA RÕ. "
                          "Mệnh đề chính trị/pháp lý nêu tên cá nhân giữ nhãn U.", upd_mark(), key="map.intro.upd")

    def group_chip(self, tk):
        v = self.perf60(tk)
        sub = self.num(v, _pct(v.value)) if v is not None and v.value is not None else [can_data()]
        return "3px solid " + C.inkM, sub

    def group_chip_note(self, gid):
        return h("div", {**_SMALL, "marginBottom": 12},
                 "Δ 60 phiên tới 25/09 (giá điều chỉnh, E) · viền xám = tín hiệu 4 kênh ", can_data())

    def group_facts(self, gid):
        items = ((self.map.get("groups") or {}).get(gid)) or []
        rows = [h("div", None, *self.render(e)) for e in items if isinstance(e, dict)]
        return h("div", {**_EXTRA, "marginTop": 10}, *rows, key="map.grp.%s.upd" % gid) if rows else None

    def axis_extra(self, key):
        e = (self.map.get("axis") or {}).get(key)
        return self.extra(*self.render(e)) if e else [tier("U"), v21_mark()]

    def entity_cells(self, e):
        ent = (self.map.get("entity") or {}).get(str(e["n"])) or {}
        out = {}
        for col in ("leader", "tk", "wealth"):
            if ent.get(col):
                out[col] = self.render(ent[col], pill=False)
        if "wealth" not in out and _VALUE.search(str(e["wealth"])):
            out["wealth"] = [e["wealth"], tier("U")]           # ước tính tài sản V21 — chưa xác minh
        v21_note = [e["note"], tier("U"), v21_mark()]
        n = ent.get("note")
        # keep_v21: note V21 chứa nhãn stance/tín hiệu (CAP, BULL, markup, distributed, OUTLIER…) → giữ nguyên + dấu,
        # dữ kiện mới đặt sau làm số đối chiếu (không thay, không chấm lại stance)
        if not n:
            out["note"] = v21_note
        else:
            out["note"] = (v21_note + [" · "] if n.get("keep_v21") else []) + self.render(n)
        return out

    def matrix_footer(self):
        return h("div", {**_SMALL, "marginTop": 10},
                 "TIER · AXIS · CLAIMS = phân loại V21", v21_mark(),
                 " (không chấm lại); cột leader/tickers/note cập nhật theo dữ kiện", upd_mark(),
                 "; ô còn dấu V21·12/05 là nguyên văn chưa có dữ kiện mới.", key="map.matrix.upd")

    def claims_insight(self, ents):
        top = sorted(ents, key=lambda e: -e["claims"])[:5]
        total = sum(e["claims"] for e in ents)
        s5 = sum(e["claims"] for e in top)
        rest = [e for e in ents if e not in top]
        big = [e for e in rest if e["claims"] > 2]
        return [h("strong", {"color": C.gold}, "Pattern insight:"),
                " " + " + ".join("%s %d" % (e["ch"].replace("Masan-Techcombank", "Masan-TCB"), e["claims"]) for e in top)
                + " = ", h("strong", None, "%d/%d claims (%s%%)" % (s5, total, to_fixed(s5 / total * 100, 1))),
                tier("E"), " tập trung 5 chaebol top — tổng thật của ma trận là %d, không phải 54. " % total,
                "%d thực thể còn lại; trong đó %s vẫn >2 claims." % (
                    len(rest), ", ".join("%s %d" % (e["ch"], e["claims"]) for e in big)),
                upd_mark(), " Câu gốc: ", h("em", None, "\"big chaebol = big thesis = big monitoring effort\""),
                v21_mark()]

    def pattern_status(self, pid):
        e = (self.map.get("patterns") or {}).get(pid)
        return self.extra(*self.render(e)) if e else None

    def timeline(self, events):
        fix = self.map.get("timeline_fix") or {}
        old = []
        for i, e in enumerate(events):
            f = fix.get(str(i))
            e = dict(e)
            # câu V21 = tổng hợp báo chí → luôn U; phần đính chính mang bậc riêng của dữ kiện
            e["_tail"] = [tier("U"), v21_mark(),
                          h("span", {**_SMALL, "marginLeft": 6}, *(self.render(f, pill=False) or [])) if f else None]
            old.append(e)
        new = []
        for x in self.map.get("timeline_new") or []:
            if not isinstance(x, dict) or not x.get("src"):
                continue
            new.append({"date": x["date"], "group": x["group"], "evt": x["evt"], "hot": bool(x.get("hot")),
                        "cl": _GROUP_COLOR.get(x.get("color"), C.ochre), "_tail": [tier(x["tier"]), upd_mark()]})
        first = new[0]["date"] if new else events[0]["date"] if events else ""
        last = events[-1]["date"] if events else ""
        return {"events": new + old, "sub": [upd_mark()],
                "title": "⌖ Timeline Sự Kiện Định Hình Chaebol Map — %s → %s" % (last, first)}

    def svg_sub(self, key, s):
        e = (self.map.get("svg") or {}).get("%s|%s" % (key, s["t"]))
        if key.endswith("L5598") and s["t"] == "GEX":
            v = self._call("mcap", self.D.market_cap, "GEX") if self.D else None
            if v is not None and v.value is not None:
                return ["Holding · " + to_locale(v.value / 1e9, "en", max_frac=0) + " tỷ", self._tspan(v.tier)]
        elif e:
            p = (e.get("parts") or [{}])[0]
            return [p.get("text", s["sub"]), self._tspan(p.get("tier"))]
        # chữ V21 giữ nguyên: có số → nhãn U (ảnh chụp CapIQ/báo chí 04–05/2026 chưa đối chiếu)
        return [s["sub"], self._tspan("UNVERIFIED") if _VALUE.search(s["sub"]) else None]

    def svg_label(self, key, s):
        """Nhãn mã trong SVG: có dữ kiện mới cho dòng → bỏ % cũ (chữ phụ đã mang số mới + bậc); không → nhãn U."""
        t = s["t"]
        if "%" not in t:
            return None
        if (self.map.get("svg") or {}).get("%s|%s" % (key, t)):
            return [re.sub(r"\s*\d+(?:\.\d+)?%", "", t)]
        return [t, self._tspan("UNVERIFIED")]

    @staticmethod
    def _tspan(t):
        if t not in _TIER_SVG:
            return None
        lab, col = _TIER_SVG[t]
        return h("tspan", None, lab, a={"fontSize": "7", "fill": col, "dx": "3"})

    def svg_footer(self):
        return "VIETNAM CHAEBOL POWER MAP · V21 MAY 2026 · SỞ HỮU ↻ 27/09/2026 (VC_LK + CBTT + BÁO CHÍ=U)"

    def svg_source_extra(self):
        return self.extra("Sơ đồ giữ hình học V21; chữ phụ cập nhật theo sổ cổ đông/quan hệ vc_lk (T2), CBTT (T1) và báo "
                          "chí (U) qua facts_f3/f4/f5 — nhãn bậc nhỏ sau từng dòng. Vốn hoá GEX = cp × giá (E).",
                          upd_mark(), key="map.svg.upd")

    def hypo_tag(self):
        return [tier("U"), v21_mark()]

    def hypo_extra(self, k):
        if k == "h3":
            nums = []
            for tk in ("BSR", "GAS", "PLX"):
                v = self.since(tk)
                nums += [tk + " ", *self.num(v, _pct(v.value) if v and v.value is not None else None), ", "]
            return self.extra("Từ 08/05 tới 25/09 (giá điều chỉnh): ", *nums[:-1], upd_mark())
        e = (self.map.get("hypo") or {}).get(k)
        return self.extra(*self.render(e)) if e else None

    def caveat_extra(self):
        v = self.since("DGC")
        e = (self.map.get("hypo") or {}).get("caveat")
        return self.extra("DGC từ 08/05 tới 25/09: ", *self.num(v, _pct(v.value) if v and v.value is not None else None),
                          " (giá điều chỉnh). ", *(self.render(e, pill=False) or []))
