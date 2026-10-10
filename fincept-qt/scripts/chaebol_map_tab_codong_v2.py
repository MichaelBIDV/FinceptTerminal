#!/usr/bin/env python3
"""
chaebol_map_tab_codong_v2: tab "★ 🏛 CẤU TRÚC CỔ ĐÔNG" bản v2, CHỈ mode live, 109 mã (P4 render).

Hợp đồng: chaebol_map_spec/codong_v2_spec.md §3 (cây, state, inc, ngân sách), §7 (lắp tab, header, Deep-dive v2, hook
DeepLiveV2, chart, Sổ bằng chứng, bảng tổng). Dữ liệu: chaebol_map_data_codong2 (O, chủ thể), chaebol_map_data_codong2_gia
(P, giá/dòng tiền), lớp dữ liệu cũ ctx.data (D) cho vwap_cluster, vietcap_view, sell_side_targets, leader, groups_of,
patterns, lk_hoso; chart: chaebol_map_tab_codong_v2_chart (CH). Khối mới mang key cd2.*; V21 giữ nguyên văn + V21·12/05.

Cây: gốc (key codong.root) = cd2.picker (A/B/C, 109 nút) + 109 × {if codong.tk == MÃ, inc codong/MÃ} + {inc codong/_tong}.
inc codong/MÃ = cd2.cong (dòng CỔNG nguyên văn, con ĐẦU TIÊN) · cd2.chuthe · codong.s1 (+ cd2.phu) · s2 (mã V21) ·
deep10_MÃ (11 placeholder sub) · s4…s7 (48 mã cũ) · s8 s9 s10 (bọc try) · s11 (48 mã cũ).
inc codong/MÃ/<sub> = div(top(sid), panel V21 sid, bottom(sid)); inc codong/MÃ/chart/<KHUNG> = chart_inc.
Mỗi mã bọc try: lỗi → [CỔNG, can_data("dựng mã lỗi, xem cảnh báo")] + cảnh báo, tab không vỡ.
Module này chỉ được chaebol_map_tab_codong.build_codong nhập trễ ở nhánh live (mode v21 không chạm tới).
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from functools import cached_property

import chaebol_map_data_codong2 as O
import chaebol_map_data_codong2_gia as P
import chaebol_map_tab_codong_deep as DD
import chaebol_map_tab_codong_v2_book as BK
import chaebol_map_tab_codong_v2_chart as CH
import chaebol_map_tab_codong_v2_parts as PT
from chaebol_map_dom import C, F_MONO, can_data, count_nodes, dumps, finalize, h, to_fixed, v21_mark
from chaebol_map_shell import Section
from chaebol_map_tab_codong_common import nowrap_can
from chaebol_map_tab_codong_deep_live import DeepLive
from chaebol_map_tab_codong_v2_parts import (E, K_SUB, K_TK, K_WIN, T2, U, cdn, dmy, dmy_hm, env_ok, fn, fp, fps, line,
                                             note, ok, tag, tv)

WHY_OFF = "live không có lớp dữ liệu chaebol_map_data"
WHY_ERR = "dựng mã lỗi, xem cảnh báo"
DEEP_TITLE = "🔬 DEEP-DIVE 10 SUB-TABS " + chr(0x2014) + " %s (equivalent v22 MSN tab structure)"
SUB_BUDGET = {"phase_info": (25000, 600), "chart": (25000, 600), "phase": (25000, 600), "patterns": (25000, 600),
              "action": (25000, 600), "cluster": (40000, 900), "shareholder": (40000, 900), "strategic": (40000, 900),
              "flow": (50000, 1100), "events": (60000, 1400), "capitaliq": (120000, 2600)}
SHRINK_HOW = {"capitaliq": "bảng cổ đông giữ dòng mới + tối đa 40 dòng cũ, nội bộ gần nhất 40 → 20, công ty con 15 → 8",
              "events": "dòng thời gian đầy đủ 24T → 12T, phần cũ gộp theo năm",
              "flow": "bảng theo năm chỉ 10 năm gần nhất", "cluster": "giữ nguyên",
              "shareholder": "bảng cặp k và MATCH/FLIP chỉ 12 dòng gần nhất"}
CHART_BUDGET = {"MAX": (135000, 450), "5Y": (95000, 450), "2Y": (75000, 450)}
TK_BUDGET = {True: (60000, 1300), False: (25000, 600)}
ROOT_BUDGET, TONG_BUDGET = (40000, 800), (70000, 1600)
LINE_LEGEND = ("Nét: đóng tuần (MAX dài) hoặc nến tuần · VWAP 6T xanh lá, 12T vàng, 24T đỏ nét đứt · KL khớp xám, "
               "thoả thuận xanh · %NN xanh, FOL nét đứt · FFT tuần, TB 4 tuần vàng, dải P10/P90 · NN cộng dồn xanh, "
               "TD cộng dồn vàng nét đứt (khung 2Y: cột ròng tuần) · RS so VNINDEX. Mốc: ▲ nội bộ mua · ▼ nội bộ bán "
               "· ◇ chuyển giao · ◆ phát hành thu tiền (vàng) hoặc không thu tiền (xám) · ● thưởng, cổ tức cp · │ ĐHCĐ "
               "· ■ tuần thoả thuận đột biến.")
S_CONG = {"fontSize": 11, "fontFamily": F_MONO, "color": C.inkD, "padding": "8px 12px", "marginBottom": 8,
          "background": C.parch, "borderLeft": "3px solid " + C.vermillion, "lineHeight": 1.6}
S_BTN = {"background": C.gold + "20", "color": C.gold, "border": "1px solid " + C.gold, "padding": "4px 10px",
         "borderRadius": 2, "cursor": "pointer", "fontFamily": F_MONO, "fontSize": 10}
S_PK_ON = BK.S_PK_ON
S_WBAR = {"display": "flex", "gap": 6, "alignItems": "center", "flexWrap": "wrap", "marginBottom": 8}
S_WBTN = {**BK.S_PK, "fontSize": 9.5}
S_WDIM = {**S_WBTN, "color": C.inkM, "border": "1px dashed " + C.rule, "cursor": "default"}
S_EYE = {"fontSize": 9, "letterSpacing": ".12em", "color": C.inkM, "fontFamily": F_MONO, "marginBottom": 6}
S_READ = {"fontSize": 10.5, "color": C.ink, "fontFamily": F_MONO, "lineHeight": 1.75, "marginBottom": 8}


def _env(ok_, why=None, **kw):
    return {"ok": ok_, "why": why, "tier": None, "asof": None, "src": None, "note": None, **kw}


# ── dữ liệu một mã ──────────────────────────────────────────────────────────


class TkData:
    """Gom dữ liệu một mã; mỗi thuộc tính gọi O/P/D đúng một lần, bọc try → _env(False, lý do) + ctx.warn.
    ctx.data None (live không có lớp dữ liệu) → mọi thuộc tính là [CẦN DATA]."""

    FFT_MISS_TEXT = O.FFT_MISS_TEXT
    WHY_NO_TV = O.WHY_NO_TV

    def __init__(self, ctx, tk, today, groups, T=None, policy=None):
        self.ctx, self.tk, self.today, self.groups, self.T, self.policy = ctx, tk, today, groups, T, policy
        self.D = getattr(ctx, "data", None)
        self.off = self.D is None
        self.tv30 = tk in set(groups.get("tv30") or [])
        self.fft_miss = tk in O.FFT_MISS
        self._memo, self.charts, self.marker_info = {}, {}, {}

    def _c(self, label, fn_, *a, default=None, **k):
        if self.off:
            return _env(False, WHY_OFF) if default is None else default
        try:
            return fn_(*a, **k)
        except Exception as exc:  # một hàm dữ liệu hỏng không làm vỡ mã
            self.ctx.warn("codong v2 %s: %s lỗi %s: %s" % (self.tk, label, type(exc).__name__, exc))
            return _env(False, "%s lỗi, xem cảnh báo" % label) if default is None else default

    def call(self, label, mod, fname, *a, **k):
        key = (fname, a, tuple(sorted(k.items())))
        if key not in self._memo:
            self._memo[key] = self._c(label, getattr({"O": O, "P": P}[mod], fname), *a, **k)
        return self._memo[key]

    def _d(self, fname, *a, default=None):
        return self._c(fname, lambda: getattr(self.D, fname)(*a), default=default)

    def why_none(self, why):
        """Lý do cho ô trống: live không có lớp dữ liệu → WHY_OFF, ngược lại lý do riêng của ô."""
        return WHY_OFF if self.off else why

    def days_ago(self, n):
        return (date.fromisoformat(self.today) - timedelta(days=n)).isoformat()

    # P1 (chủ thể)
    @cached_property
    def cong(self):
        return self._c("cong_line", O.cong_line, self.tk,
                       default={"text": "CỔNG: [CẦN DATA]", "as_of": None, "src": None, "stop": True})

    @cached_property
    def chu_the(self):
        return self._c("chu_the_label", O.chu_the_label, self.tk, default={
            "nhan": can_data_v(WHY_OFF), "xung_dot": False, "khang_dinh": [], "playbook": None})

    sigma = property(lambda s: s.call("sigma_view", "O", "sigma_view", s.tk))
    rows = property(lambda s: s.call("insider_rows", "O", "insider_rows", s.tk, s.today))
    pairs = property(lambda s: s.call("pair_transfers", "O", "pair_transfers", s.tk, s.today))
    ladder = property(lambda s: s.call("ownership_ladder", "O", "ownership_ladder", s.tk, s.today))
    yearly = property(lambda s: s.call("insider_yearly", "O", "insider_yearly", s.tk, s.today))
    execs = property(lambda s: s.call("exec_stats", "O", "exec_stats", s.tk, s.today))
    holders = property(lambda s: s.call("holder_table", "O", "holder_table", s.tk, s.today))
    hdelta = property(lambda s: s.call("holder_delta", "O", "holder_delta", s.tk))
    structure = property(lambda s: s.call("structure_bars", "O", "structure_bars", s.tk))
    rel = property(lambda s: s.call("relationship_view", "O", "relationship_view", s.tk))
    codong = property(lambda s: s.call("codong_full", "O", "codong_full", s.tk))
    fund = property(lambda s: s.call("fund_view", "O", "fund_view", s.tk))
    cap = property(lambda s: s.call("capital_actions", "O", "capital_actions", s.tk, s.today))
    agm = property(lambda s: s.call("agm_events", "O", "agm_events", s.tk, s.today))
    timeline = property(lambda s: s.call("timeline", "O", "timeline", s.tk, s.today))
    gmap = property(lambda s: s._c("group_map", O.group_map, s.tk, default={}))
    net12 = property(lambda s: s.call("insider_net", "O", "insider_net", s.tk, s.days_ago(365), s.today, s.today))
    net36 = property(lambda s: s.call("insider_net", "O", "insider_net", s.tk, s.days_ago(1096), s.today, s.today))

    @cached_property
    def intent(self):
        return self._c("intent_sources", O.intent_sources, self.tk, default={
            "chu_the": self.chu_the, "cauchuyen": _env(False, WHY_OFF), "vung_gom": None, "owner_intent": [],
            "nq": None, "facts": []})

    @cached_property
    def mf(self):
        return self._c("match_flip", O.match_flip, self.tk, lambda a, b: P.flow_window(self.tk, a, b))

    # P2 (giá, dòng tiền)
    weekly = property(lambda s: s.call("weekly_full", "P", "weekly_full", s.tk))
    cum = property(lambda s: s.call("cum_series", "P", "cum_series", s.tk))
    rs = property(lambda s: s.call("rs_weekly", "P", "rs_weekly", s.tk))
    fft = property(lambda s: s.call("fft_view", "P", "fft_view", s.tk))
    zig = property(lambda s: s.call("zigzag", "P", "zigzag", s.tk))
    flows = property(lambda s: s.call("flow_windows", "P", "flow_windows", s.tk, s.today))
    yflows = property(lambda s: s.call("yearly_flows", "P", "yearly_flows", s.tk))
    spikes = property(lambda s: s.call("deal_weekly_spikes", "P", "deal_weekly_spikes", s.tk))
    pos = property(lambda s: s.call("position_now", "P", "position_now", s.tk))
    smr = property(lambda s: s.call("smr_view", "P", "smr_view", s.tk))
    pre_steps = property(lambda s: s._c("pre_share_steps", P.pre_share_steps, s.tk, default=[]))

    @cached_property
    def segs(self):
        segs = (self.zig.get("segments") or []) if env_ok(self.zig) else []
        return self._c("segment_stats", P.segment_stats, self.tk, segs[-13:], default=[]) if segs else []

    @cached_property
    def anchors(self):
        return self._c("anchored_vwap", lambda: P.anchored_vwap(self.tk, O.anchor_dates(self.tk, self.today)),
                       default=[])

    @cached_property
    def windows(self):
        return self._c("insider_windows", O.insider_windows, self.tk, self.today, default=[])

    @cached_property
    def deals(self):
        return self._c("deal_sessions", P.deal_sessions, self.tk, windows=self.windows)

    def _ddins(self, side, n):
        """Giá ước của `n` dòng tổ chức nội bộ (DDINS, không chuyển giao, 36T) có |KL| lớn nhất theo chiều `side`."""
        code = {r["id"]: r.get("code") for r in (self.rows.get("rows") or [])} if env_ok(self.rows) else {}
        top = sorted((w for w in self.windows if code.get(w.get("row")) == "DDINS" and (w.get("side") or 0) * side > 0),
                     key=lambda w: -(w.get("qty") or 0))
        rows = [{"row": w["row"], "start": w["start"], "end": w["end"], "qty": w["qty"]} for w in top[:n]]
        return self._c("cost_estimate", P.cost_estimate, self.tk, rows, default=[]) if rows else []

    @cached_property
    def costs(self):
        """Giá vốn ước: CHỈ dòng mua (giá bán ra không phải giá vốn của khối còn nắm)."""
        return self._ddins(1, 5)

    @cached_property
    def sells(self):
        """Giá bán ra ước của dòng bán DDINS (không tính chênh so giá nay)."""
        return self._ddins(-1, 3)

    @cached_property
    def check(self):
        return self._c("checklist", P.checklist, self.tk, self.recent30())

    def recent30(self):
        if not env_ok(self.rows):
            return None
        d0 = self.days_ago(30)
        return sum(1 for r in self.rows["rows"] if r.get("status") == "da_xong" and r.get("valid")
                   and d0 <= str(r.get("date") or "") <= self.today)

    @cached_property
    def plan(self):
        return CH.window_plan(self.weekly["n_weeks"]) if env_ok(self.weekly) else None

    # lớp dữ liệu cũ (D)
    vc = property(lambda s: s._d("vwap_cluster", s.tk, default={}))
    vview = property(lambda s: s._d("vietcap_view", s.tk, default={}))
    sst = property(lambda s: s._d("sell_side_targets", s.tk))
    leader = property(lambda s: s._d("leader", s.tk))
    chaebol = property(lambda s: s._d("groups_of", s.tk, default=[]))
    mauhinh = property(lambda s: s._d("patterns", s.tk))
    shares_now = property(lambda s: s._d("shares_out", s.tk))

    @cached_property
    def trig(self):
        hs = self._d("lk_hoso", self.tk, default={}) or {}
        return [t for t in (hs.get("trigger") if isinstance(hs, dict) else None) or [] if isinstance(t, dict)]

    @cached_property
    def prev(self):
        meta_d = self._d("vc", self.tk, "details", default=(None, None))
        pv = (meta_d[1] or {}).get("prevInsight") if isinstance(meta_d, tuple) and isinstance(meta_d[1], dict) else None
        if not isinstance(pv, dict) or not pv.get("rating"):
            return None
        try:
            d = datetime.strptime(str(pv.get("ratingAsOf")), "%d-%b-%y").date().isoformat()
        except ValueError:
            d = None
        return {"rating": pv.get("rating"), "targetPrice": pv.get("targetPrice"), "date": d}

    @cached_property
    def covh(self):
        return self._c("vc_coverage_hist", self._covh, default=[])

    def _covh(self):
        d = self.D.bridge() / "state" / "vc_coverage_hist"
        out, prev = [], None
        for f in sorted(d.glob("*.json")) if d.is_dir() else []:
            rows = self.D.read_json(f, quiet=True)
            r = next((x for x in rows or [] if isinstance(x, dict) and x.get("ticker") == self.tk), None)
            if r is None:
                continue
            cur = (r.get("rating"), r.get("targetPrice"))
            if cur != prev:
                out.append({"date": f.stem, "rating": r.get("rating"), "tp": r.get("targetPrice"),
                            "tp_time": r.get("tpUpdatedTime")})
                prev = cur
        return out

    def row_names(self):
        if "names" not in self._memo:
            rs = self.rows.get("rows") or [] if env_ok(self.rows) else []
            self._memo["names"] = {r["id"]: r["owner"]["name"] for r in rs}
        return self._memo["names"]

    @cached_property
    def series(self):
        return build_series(self) if env_ok(self.weekly) else None


def can_data_v(why):
    from chaebol_map_data_nen import can_data as vcan
    return vcan(why)


# ── chuỗi chart (§6.2) + mốc ① tới ⑫ ────────────────────────────────────────────


def _fft_map(ff):
    out = {}
    if env_ok(ff):
        cols = {k: ff.get(k) or [] for k in ("fw", "ma4", "p10", "p90")}
        for i, wk in enumerate(ff.get("w") or []):
            out[wk] = {k: (v[i] if i < len(v) else None) for k, v in cols.items()}
    return out


def build_series(td):
    w, cum, rsw = td.weekly, td.cum, td.rs
    nn = cum.get("nn_cum") if env_ok(cum) else None
    tc = cum.get("td_cum") if env_ok(cum) else None
    rs = rsw.get("rs") if env_ok(rsw) else None
    fmap, empty = _fft_map(td.fft), {"fw": None, "ma4": None, "p10": None, "p90": None}
    at = lambda arr, i: arr[i] if arr and i < len(arr) else None  # noqa: E731
    weeks = []
    for i, r in enumerate(w["rows"]):
        row = {k: r.get(k) for k in ("w", "we", "o", "h", "l", "c", "vol", "dvol", "fo", "fol", "v6", "v12", "v24", "pre")}
        row.update({"nn_w": r.get("nn_val"), "td_w": r.get("td_val"), "nn_cum": at(nn, i), "td_cum": at(tc, i),
                    "rs": at(rs, i)})
        row.update(fmap.get(r.get("w")) or empty)
        weeks.append(row)
    markers, info = build_markers(td)
    td.marker_info = info
    return {"tk": td.tk, "weeks": weeks, "markers": markers, "ts_start": w.get("ts_start"), "fft_note": CH.FFT_NOTE,
            "fft_warn": O.FFT_MISS_TEXT if td.fft_miss else None, "fo_spikes": len(w.get("fo_spikes") or [])}


def _insider_markers(td, out, info):
    """% vốn của dòng nội bộ = |KL| ÷ số cp TẠI NGÀY (O.acq_pct, cùng mẫu số với cặp chuyển giao); không có số cp tại
    ngày → |KL quy đổi| ÷ số cp hiện hành (E)."""
    so = td.shares_now
    so = so.value if ok(so) and so.value else None
    for r in (td.rows.get("rows") or []) if env_ok(td.rows) else []:
        if r.get("status") != "da_xong" or not r.get("valid") or r.get("pair") or not r.get("acq_now") or not r.get("side"):
            continue
        size, st = r.get("acq_pct"), r.get("acq_pct_tier")
        if size is None:
            size, st = (abs(r["acq_now"]) / so * 100, E) if so else (None, None)
        if size is None or size < O.MARKER_MIN_PCT:
            continue
        ref = "r:" + str(r["id"])
        out.append({"date": r["date"], "kind": "nb_mua" if r["side"] > 0 else "nb_ban", "size": size,
                    "label": r["owner"]["name"], "ref": ref})
        info[ref] = {"t": "row", "r": r, "size": size, "size_tier": st}


def _pair_markers(td, out, info):
    for p in (td.pairs.get("pairs") or []) if env_ok(td.pairs) else []:
        ref = "p:" + str(p["id"])
        out.append({"date": p["date1"], "kind": "chuyen_giao", "size": p["pct"].value if ok(p.get("pct")) else None,
                    "label": "%s → %s" % ((p.get("from") or {}).get("name"), (p.get("to") or {}).get("name")),
                    "ref": ref})
        info[ref] = {"t": "pair", "p": p}


def _cap_kind(it):
    if it.get("kind") == "thu_tien":
        return "ph_thu_tien"
    if it.get("kind") == "esop" or it.get("sub") in ("chuyen_doi", "sap_nhap"):
        return "ph_khong_thu"
    if it.get("sub") in ("co_tuc_cp", "thuong") and (it.get("ratio") or 0) >= 0.10:
        return "cp_thuong"
    return None


def _cap_markers(td, out, info):
    best = {}
    for it in (td.cap.get("items") or []) if env_ok(td.cap) else []:
        kind = _cap_kind(it)
        if kind and it.get("date"):
            k = (it["date"], kind)
            if k not in best or (it.get("ratio") or 0) > (best[k].get("ratio") or 0):
                best[k] = it
    for i, ((d, kind), it) in enumerate(sorted(best.items())):
        ref = "c:%d" % i
        size = it["ratio"] * 100 if it.get("ratio") and kind != "cp_thuong" else None   # chia đều: không xếp hạng
        out.append({"date": d, "kind": kind, "size": size, "label": it.get("title"), "ref": ref})
        info[ref] = {"t": "cap", "it": it}
    for i, s in enumerate(td.pre_steps):
        ref = "s:%d" % i
        out.append({"date": s["date"], "kind": "cp_thuong", "size": None, "label": "bước giá ≥10% suy", "ref": ref})
        info[ref] = {"t": "step", "s": s}


def build_markers(td):
    out, info = [], {}
    _insider_markers(td, out, info)
    _pair_markers(td, out, info)
    _cap_markers(td, out, info)
    for i, a in enumerate((td.agm.get("items") or []) if env_ok(td.agm) else []):
        out.append({"date": a.get("date"), "kind": "dhcd", "size": None, "label": a.get("title"), "ref": "a:%d" % i})
    for i, wk in enumerate((td.spikes.get("weeks") or []) if env_ok(td.spikes) else []):
        out.append({"date": wk.get("w"), "kind": "tt_dot_bien", "size": None, "label": "tuần thoả thuận đột biến",
                    "ref": "t:%d" % i})
    return [m for m in out if m.get("date")], info


# ── chart: thanh khung (p02) + inc từng khung ───────────────────────────────


def chart_slots(tk, plan, n):
    base = "codong/%s/chart/" % tk
    if n <= CH.WIN_WEEKS["2Y"]:
        return [h("div", None, inc=base + "MAX")]
    if n <= CH.WIN_WEEKS["5Y"]:
        return [h("div", None, if_={K_WIN: ["MAX", "5Y"]}, inc=base + "MAX"),
                h("div", None, if_={K_WIN: "2Y"}, inc=base + plan["2Y"])]
    return [h("div", None, if_={K_WIN: w}, inc=base + plan[w]) for w in CH.WIN]


def chart_bar(td):
    """cd2.chart (scope codong.win): thanh MAX/5Y/2Y + placeholder inc theo window_plan; khung bí danh: nút mờ."""
    w = td.weekly
    if not env_ok(w):
        return h("div", None, line("Chart tuần từ niêm yết: ", cdn(w)), key="cd2.chart")
    n, plan = w["n_weeks"], td.plan
    btns = []
    for win in CH.WIN:
        own = plan[win] == win and n > CH.WIN_WEEKS["2Y"]
        btns.append(h("button", S_WBTN if own else S_WDIM, win, on={"set": {K_WIN: win}} if own else None,
                      var=[{"if": {K_WIN: win}, "s": S_PK_ON}] if own else None, key="cd2.win." + win))
    head = h("div", S_WBAR, h("span", S_EYE, "CHART TUẦN TỪ NIÊM YẾT · KHUNG "), *btns,
             h("span", S_EYE, " (khung mờ = cùng khung MAX vì chuỗi ngắn)") if n <= CH.WIN_WEEKS["5Y"] else None)
    return h("div", None, head, *chart_slots(td.tk, plan, n), scope=[K_WIN], key="cd2.chart")


def _num_week(w, kind):
    cs = [(r["c"], i) for i, r in enumerate(w["rows"]) if isinstance(r.get("c"), (int, float)) and r["c"] > 0]
    if not cs:
        return None
    v, i = max(cs, key=lambda p: (p[0], -p[1])) if kind == "ath" else cs[-1]
    r = w["rows"][i]
    return {"id": kind, "text": CH.fmt_px(v), "date": str(r.get("we") or r.get("w"))[:10]}


def _dd(d, today):
    return dmy(d) if str(d)[:4] != today[:4] else "%s/%s" % (str(d)[8:10], str(d)[5:7])


def _rs_change(td, res):
    rs = td.rs
    if not env_ok(rs):
        return [cdn(rs)]
    first = res.get("first") or ""
    vals = [(r.get("we"), v) for r, v in zip(td.weekly["rows"], rs.get("rs") or []) if str(r.get("w")) >= first
            and isinstance(v, (int, float)) and v > 0]
    if len(vals) < 2:
        return [cdn(None, "chưa đủ RS trong khung")]
    chg = (vals[-1][1] / vals[0][1] - 1) * 100
    rrg = rs.get("rrg") or {}
    out = [fps(chg) + " từ đầu khung", tag(E, vals[-1][0])]
    if rrg.get("goc"):
        out += [" (RRG ", rrg["goc"], tag(rrg.get("tier") or E, rrg.get("t_cuoi")), ")"]
    return out


def readout(td, res):
    w, today = td.weekly, td.today
    nums = {x["id"]: x for x in res.get("numbers") or []}
    now, ath = nums.get("now") or _num_week(w, "now"), nums.get("ath") or _num_week(w, "ath")
    tpx = w.get("tier_px") or T2
    last = w["rows"][-1]
    pos = td.pos if env_ok(td.pos) else {}
    k = ["ĐÓNG %s: " % _dd(now["date"], today), now["text"], tag(tpx, now["date"])] if now else []
    for lab, key in ((" · VWAP 6T ", "v6"), (" · 12T ", "v12"), (" · 24T ", "v24")):
        v = last.get(key)
        k += [lab, *([CH.fmt_px(v), tag(w.get("tier_conv") or E, last.get("we"))] if isinstance(v, (int, float))
                     else [cdn(None, "thiếu VWAP")])]
    k += [" · %NN ", *tv(pos.get("fo"), fp, why=PT.why_of(td.pos)), " (FOL ", *tv(pos.get("fol"), fp, False, PT.why_of(td.pos)),
          ", room còn ", *tv(pos.get("room_pct"), fp, False, PT.why_of(td.pos)), ") · FFT pct ", *PT.fft_pcts(td)]
    if ath:
        k += [" · Đỉnh lịch sử (đóng tuần) ", ath["text"], tag(tpx, ath["date"])]
    k += [" · RS so VNINDEX ", *_rs_change(td, res)]
    warn = h("div", {"color": C.vermillion, "fontWeight": 700}, O.FFT_MISS_TEXT) if td.fft_miss else None
    return h("div", S_READ, h("div", None, *k), warn, key="cd2.readout")


def _eyebrow(td, res, win):
    w = td.weekly
    base = "giá điều chỉnh quyền vc_lk" if w.get("base") == "vc_lk" else "giá vnstore trộn điều chỉnh và thô (U)"
    s = "TUẦN · %s · %s tuần từ niêm yết (%s → %s) · %s · thang %s · 1 điểm = %d tuần" % (
        td.tk, fn(w["n_weeks"]), dmy(w.get("first_week")), dmy(w["rows"][-1].get("we")), base,
        "log" if res.get("scale") == "log" else "tuyến tính", res.get("step") or 1)
    if win != "MAX":
        s += " · khung %s: %s → %s" % (win, dmy(res.get("first")), dmy(res.get("last")))
    return h("div", S_EYE, s, key="cd2.eyebrow")


def chart_inc(td, win, compact=False):
    """inc codong/<MÃ>/chart/<KHUNG> (key cd2.chartwin.<KHUNG>): eyebrow · readout · SVG · chú giải · bảng ①…⑫ · ghi chú."""
    res = td.charts.get(win)
    if res is None:
        res = td.charts[win] = CH.build_chart(td.series, win)
        for x in res.get("warnings") or []:
            td.ctx.warn("codong v2: %s chart %s: %s" % (td.tk, win, x))
    ts = td.weekly.get("ts_start")
    notes = [note("① tới ⑫: tối đa 12 mốc có % vốn lớn nhất trong khung (trừ ĐHCĐ, tuần thoả thuận đột biến; thưởng và "
                  "cổ tức cp chia đều cho mọi cổ đông nên xếp sau), đánh số theo ngày. Số trên chart (đỉnh lịch sử, đóng tuần cuối) chép ở dòng số phía trên kèm bậc. Không vẽ dải "
                  "zigzag, dải pha, mốc giá V21. ", CH.FFT_NOTE + "."),
             note("Trước %s: số cp quy đổi U (hệ số suy từ bước giá ≥10%%)." % dmy(ts)) if ts and str(ts) > str(
                 res.get("first") or "") else None]
    return h("div", None, _eyebrow(td, res, win), readout(td, res), res["svg"], note(LINE_LEGEND),
             BK.legend_table(td, res, compact), *notes, key="cd2.chartwin." + win)


# ── Deep-dive v2 ────────────────────────────────────────────────────────────


TOPS = {"phase_info": PT.top_phase_info, "cluster": PT.top_cluster, "shareholder": PT.top_shareholder,
        "capitaliq": BK.top_capitaliq, "flow": PT.top_flow, "strategic": BK.evidence_book, "events": PT.top_events,
        "patterns": PT.top_patterns, "action": PT.top_action}


class DeepLiveV2(DeepLive):
    """Lớp sống cũ + hook v2: khối live cũ dời lên top/bottom (không lặp), chart mới, action/consensus theo §7.2."""

    def __init__(self, ctx, tk, T, td):
        super().__init__(ctx, tk, T)
        self.td = td

    def chart(self, T):
        return chart_bar(self.td)

    def codong_table(self):
        return None

    def holders_live(self):
        return None

    def vwap_live_table(self):
        return None

    def flow_live_rows(self, has_v21=True):
        return []

    def flow_only_live(self):
        return None

    def events_new_rows(self):
        return []

    def consensus_box(self, cons):
        if not (cons or {}).get("avgTp"):
            return None
        return h("div", {"marginTop": 10, "padding": "10px 14px", "background": C.gold + "10", "border": "1px solid "
                         + C.gold + "30", "borderRadius": 3, "fontSize": 11, "color": C.inkD, "lineHeight": 1.7},
                 "Bản lưu V21 (Simplize; VIC/DGC nghi sai đơn vị): ", "%s MUA / %s BÁN / avg TP %sK" % (
                     cons.get("mua"), cons.get("ban"), to_fixed(cons["avgTp"] / 1000, 1)), tag(U), v21_mark(),
                 " · phần sống ở khối Vietcap phía trên.", key="deep10_cons_v21")

    def action_banner(self):
        if (self.T.deep or {}).get("action"):
            return super().action_banner()
        return h("div", {"marginBottom": 14, "fontSize": 11, "color": C.inkD, "fontFamily": F_MONO},
                 "Không có action V21 cho %s; CỔNG v1.7 DỪNG: không sinh khuyến nghị." % self.tk, key="cd2.action.banner")

    def top(self, sid, lite=0):
        fn_ = TOPS.get(sid)
        if fn_ is None:
            return None
        try:
            return fn_(self.td, lite)
        except Exception as exc:  # khối mới lỗi → [CẦN DATA] + cảnh báo, panel V21 vẫn hiện
            self.ctx.warn("codong v2 %s: top %s lỗi %s: %s" % (self.tk, sid, type(exc).__name__, exc))
            return h("div", None, can_data("khối mới lỗi, xem cảnh báo"), key="cd2.top." + sid)

    def bottom(self, sid):
        return PT.bottom(self.td, sid)


def _measure(node, cap):
    nn = count_nodes(node)
    est = len(json.dumps(node, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if est <= 0.8 * cap:
        return est, nn
    obj, st = finalize(node)
    return len(dumps(obj).encode("utf-8")), st["nodes"]


def fit_budget(key, node, budget, shrink, warn=None):
    """§3.3/§7.6: vượt trần → hạ cấp tất định theo shrink [(cách hạ, hàm → nút)], ghi cảnh báo; không làm hỏng build."""
    warn = warn or (lambda m: None)
    for how, fn_ in list(shrink) + [(None, None)]:
        nb, nn = _measure(node, budget[0])
        if nb <= budget[0] and nn <= budget[1]:
            return node
        msg = "codong v2: %s %s KB > %s KB" % (key, to_fixed(nb / 1000, 1), to_fixed(budget[0] / 1000, 0)) \
            if nb > budget[0] else "codong v2: %s %d nút > %d nút" % (key, nn, budget[1])
        if fn_ is None:
            warn(msg + " → giữ nguyên (không còn cách hạ)")
            return node
        warn(msg + " → " + how)
        node = fn_()
    return node


def sub_inc(ctx, td, T, lv, i, sid, L=None):
    try:
        panel = DD.PANELS[i](T, lv)
    except Exception as exc:  # panel V21 lỗi → chỗ trống có lý do
        ctx.warn("codong v2 %s: panel %s lỗi %s: %s" % (td.tk, sid, type(exc).__name__, exc))
        panel = can_data("panel V21 lỗi, xem cảnh báo")

    def build(lite):
        node = h("div", None, lv.top(sid, lite), panel, lv.bottom(sid), key="cd2.sub." + sid)
        return L.pattern_q(node) if L is not None else node
    shrink = [(SHRINK_HOW[sid], lambda: build(1))] if sid in SHRINK_HOW and sid != "cluster" else []
    return fit_budget("codong/%s/%s" % (td.tk, sid), build(0), SUB_BUDGET.get(sid, (60000, 1400)), shrink, ctx.warn)


def deep10_v2(ctx, tk, td, T, lv, v21, L=None):
    """Section Deep-dive v2 (tiêu đề V21 nguyên văn) + inc 11 sub + inc chart theo window_plan."""
    subs = DD.sub_tabs(v21)
    slots = [h("div", None, if_={DD.SUB_KEY: sid}, inc="codong/%s/%s" % (tk, sid)) for sid, _ in subs]
    body = h("div", None, lv.legal_banner(), DD._sub_bar(subs), *slots)
    root = Section(DEEP_TITLE % tk, body, lv.header_note(), accent=C.gold, sub=DD.SUB_LINE, scope=[DD.SUB_KEY],
                   key="deep10_" + tk)
    inc = {"codong/%s/%s" % (tk, sid): sub_inc(ctx, td, T, lv, i, sid, L) for i, (sid, _) in enumerate(subs)}
    if td.plan and td.series is not None:
        for win in sorted(set(td.plan.values())):
            try:
                node = chart_inc(td, win)
            except Exception as exc:  # chart một khung lỗi → [CẦN DATA]
                ctx.warn("codong v2 %s: chart %s lỗi %s: %s" % (tk, win, type(exc).__name__, exc))
                node = h("div", None, can_data("chart lỗi, xem cảnh báo"), key="cd2.chartwin." + win)
            shrink = [("bảng ① tới ⑫ gộp cột số", lambda w=win: chart_inc(td, w, True))]
            inc["codong/%s/chart/%s" % (tk, win)] = fit_budget("codong/%s/chart/%s" % (tk, win), node,
                                                               CHART_BUDGET[win], shrink, ctx.warn)
    return {"root": root, "inc": inc}


# ── header, cây một mã ──────────────────────────────────────────────────────


def cong_node(cong):
    txt = cong.get("text") or "CỔNG: [CẦN DATA]"
    at = cong.get("as_of")
    return h("div", S_CONG, h("span", {"color": C.vermillion if cong.get("stop") else C.gold, "fontWeight": 700},
                              *nowrap_can(txt), key="cd2.trich.cong"),          # '[CẦN DATA' không ngắt dòng
             " · tính đến ", dmy_hm(at) if at else can_data("lk_hoso không ghi thời điểm"), key="cd2.cong")


def _count(env, n, label):
    if not env_ok(env):
        return [label + " ", cdn(env)]
    return [fn(n) + " " + label, tag(T2, env.get("asof"))]


def phu_node(td):
    g, w = td.groups, td.weekly
    yn = lambda b: "có" if b else "không"  # noqa: E731
    vc = [dmy(w.get("asof")), tag(w.get("tier") or T2, w.get("asof"))] if env_ok(w) else [cdn(w)]
    ir, ht, ca = td.rows, td.holders, td.cap
    src = ("vc_lk tới " if not env_ok(w) or w.get("base") == "vc_lk" else
           "chưa nạp vc_lk; giá vnstore nen_ngay (giá trộn) tới ")
    return line("Độ phủ dữ liệu: " + src, *vc, " · ", *_count(ir, ir.get("n_raw", 0), "dòng nội bộ"), " · ",
                *_count(ht, ht.get("n", 0), "cổ đông"), " · ", *_count(ca, len(ca.get("items") or []), "sự kiện vốn"),
                " · lk_hoso %s · Toàn Vũ %s · nhóm %s · VN30 %s" % (
                    yn((g.get("has_lk") or {}).get(td.tk)), yn(td.tv30), (g.get("grp") or {}).get(td.tk, "·"),
                    yn((g.get("grp") or {}).get(td.tk) == "A")), key="cd2.phu")


def chuthe_node(td):
    btn = h("button", S_BTN, "→ Sổ bằng chứng chủ thể (07)", on={"set": {K_SUB: "strategic"}}, key="cd2.chuthe.btn")
    return h("div", {"display": "flex", "gap": 12, "alignItems": "center", "flexWrap": "wrap", "marginBottom": 8},
             PT.chuthe_line(td, None), btn, key="cd2.chuthe")


class _SafeCard:
    """Bọc LiveTk cho head_card: head_stats lỗi (mã ngoài V21, sổ cổ đông có dòng không quy đổi được) → [CẦN DATA]
    + cảnh báo, phần còn lại của thẻ (tên, ngành, lăng kính) giữ nguyên."""

    def __init__(self, L, ctx, tk):
        self._L, self._ctx, self._tk = L, ctx, tk

    def __getattr__(self, k):
        return getattr(self._L, k)

    def head_stats(self, det, total):
        try:
            return self._L.head_stats(det, total)
        except Exception as exc:  # lỗi lớp cũ không làm mất thẻ đầu mã
            self._ctx.warn("codong v2 %s: LiveTk.head_stats lỗi %s: %s" % (self._tk, type(exc).__name__, exc))
            from chaebol_map_shell import Stat
            return [Stat("TOP 10 HOLDERS", can_data("thẻ cũ lỗi với mã này, xem cảnh báo"), color=C.forest)]


def header_v2(ctx, tk, td, D21, L):
    """[cd2.cong, cd2.chuthe, codong.s1(head_card + lăng kính, KHÔNG thanh mã cũ) + cd2.phu]."""
    import chaebol_map_tab_codong as M
    try:
        card = M.head_card(D21, tk, _SafeCard(L, ctx, tk) if L is not None else None)
    except Exception as exc:  # card cũ lỗi với mã ngoài V21 → [CẦN DATA]
        ctx.warn("codong v2 %s: head_card lỗi %s: %s" % (tk, type(exc).__name__, exc))
        card = can_data("thẻ đầu mã lỗi, xem cảnh báo")
    s1 = Section(M.T_S1, card, phu_node(td), accent=C.gold, sub=L.s1_sub() if L else M.SUB_S1, key="codong.s1")
    return [cong_node(td.cong), chuthe_node(td), s1]


def _try(ctx, tk, name, fn_):
    try:
        return fn_()
    except Exception as exc:  # một Section cũ lỗi → bỏ Section + cảnh báo
        ctx.warn("codong v2 %s: %s lỗi %s: %s" % (tk, name, type(exc).__name__, exc))
        return None


def ticker_tree_v2(ctx, D21, tk, td, L, deep_root):
    import chaebol_map_tab_codong as M
    old = tk in D21.tickers
    kids = header_v2(ctx, tk, td, D21, L)
    kids.append(M.s2(D21, tk, L) if old else None)
    kids.append(deep_root)
    if old:
        kids += [M.s4(D21, tk, L), M.s5(tk, L), M.s6(tk, L), *M.s7(D21, tk, L)]
    kids += [_try(ctx, tk, n, lambda f=f: f(D21, tk, L)) for n, f in (("s8", M.s8), ("s9", M.s9), ("s10", M.s10))]
    kids.append(M.s11(tk, L) if old else None)
    tree = h("div", None, *kids, key="codong.tk." + tk)
    return L.pattern_q(tree) if L is not None else tree


def _trim_lists(node, n):
    for c in node.get("k") or []:
        if isinstance(c, dict):
            _trim_lists(c, n)
    kids = node.get("k") or []
    grid = len(kids) >= 4 and all(isinstance(c, dict) and c.get("t") == "div" for c in kids)
    if (node.get("t") in ("tbody", "ul") or grid) and len(kids) > n:
        node["k"] = kids[:n]


def _trim_old(tree, n):
    """Hạ cấp trang mã: bảng, danh sách, lưới thẻ của Section cũ s8, s9, s10 giữ n mục đầu (tài liệu, sell-side, báo cáo)."""
    for sec in tree.get("k") or []:
        if isinstance(sec, dict) and sec.get("key") in ("codong.s8", "codong.s9", "codong.s10"):
            _trim_lists(sec, n)
    return tree


def build_ticker(ctx, D21, shared, tk, groups, v21):
    """→ (inc của mã, dòng csv_extra | None)."""
    from chaebol_map_tab_codong_live import LiveTk
    L = LiveTk(shared, tk) if shared is not None else None
    T = DD._T(v21, tk)
    td = TkData(ctx, tk, ctx.today.isoformat(), groups, T, D21.policy.get(tk))
    lv = DeepLiveV2(ctx, tk, T, td)
    dv = deep10_v2(ctx, tk, td, T, lv, v21, L)
    tree = ticker_tree_v2(ctx, D21, tk, td, L, dv["root"])
    shrink = [("bảng, danh sách, lưới thẻ ở s8, s9, s10 rút còn %d mục" % n, lambda n=n: _trim_old(tree, n)) for n in (5, 2)]
    inc = {"codong/" + tk: fit_budget("codong/" + tk, tree, TK_BUDGET[tk in D21.tickers], shrink, ctx.warn)}
    inc.update(dv["inc"])
    extra = _try(ctx, tk, "csv_extra", L.csv_extra) if L is not None and tk in D21.tickers else None
    return inc, extra


def error_inc(ctx, tk):
    try:
        cg = O.cong_line(tk) if getattr(ctx, "data", None) is not None else None
    except Exception:  # CỔNG cũng lỗi → chuỗi chuẩn
        cg = None
    return h("div", None, cong_node(cg or {"text": "CỔNG: [CẦN DATA]", "stop": True}), can_data(WHY_ERR),
             key="codong.tk." + tk)


# ── bảng chọn mã, bảng tổng, lắp tab ────────────────────────────────────────


def _groups(ctx, D21):
    try:
        return O.universe_groups(ctx.v21)
    except Exception as exc:  # vũ trụ lỗi → 48 mã V21 (nhóm B), không vỡ tab
        ctx.warn("codong v2: universe_groups lỗi %s: %s → dùng 48 mã V21" % (type(exc).__name__, exc))
        tks = list(D21.tickers)
        return {"order": tks, "A": [], "B": tks, "C": [], "grp": {t: "B" for t in tks}, "tv30": [],
                "has_vc": {t: False for t in tks}, "has_lk": {t: False for t in tks}, "vn30_asof": None}


def build_codong_v2(ctx):
    """→ {"root", "states": [codong.tk, codong.sub, codong.win], "inc", "csv"} (§7.1)."""
    import chaebol_map_tab_codong as M
    import chaebol_map_tab_codong_live as LV
    D21, v21 = M.V21(ctx.v21), DD._v21_of(ctx)
    groups = _groups(ctx, D21)
    order = groups["order"]
    shared = LV.Shared(ctx, D21)
    inc, extras = {}, {}
    for tk in order:
        try:
            part, extra = build_ticker(ctx, D21, shared, tk, groups, v21)
            inc.update(part)
            extras[tk] = extra
        except Exception as exc:  # một mã lỗi không làm vỡ tab
            ctx.warn("codong v2: dựng %s lỗi %s: %s" % (tk, type(exc).__name__, exc))
            sys.stderr.write("[codong v2] %s: %s: %s\n" % (tk, type(exc).__name__, exc))
            inc["codong/" + tk] = error_inc(ctx, tk)
    shared.finish()
    rows = BK.summary_rows_safe(ctx, groups, WHY_OFF)
    inc["codong/_tong"] = fit_budget("codong/_tong", BK.summary_table(rows, groups), TONG_BUDGET, [], ctx.warn)
    root = h("div", None, BK.picker(groups), *[h("div", None, if_={K_TK: tk}, inc="codong/" + tk) for tk in order],
             h("div", None, inc="codong/_tong"), key="codong.root")
    states = [{"key": K_TK, "default": "VIC" if "VIC" in order else order[0], "options": list(order)},
              {"key": K_SUB, "default": "phase_info", "options": [s for s, _ in DD.sub_tabs(v21)]},
              {"key": K_WIN, "default": "MAX", "options": list(CH.WIN)}]
    return {"root": fit_budget("tab codong (gốc)", root, ROOT_BUDGET, [], ctx.warn), "states": states, "inc": inc,
            "csv": BK.csv_rows(rows, extras)}
