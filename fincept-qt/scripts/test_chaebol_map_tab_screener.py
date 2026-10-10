#!/usr/bin/env python3
"""Unit tests tab 07 · VN30 SCREENER (chaebol_map_tab_screener) — không mạng.

Chạy (cả hai trình thông dịch):
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest scripts/test_chaebol_map_tab_screener.py -v
    PYTHONDONTWRITEBYTECODE=1 ~/Library/Application\\ Support/com.fincept.terminal/venv-numpy2/bin/python \\
        -m unittest scripts/test_chaebol_map_tab_screener.py

Chuỗi vàng lấy từ chaebol_map_spec/page_p5_groups_screener.md §7 (thứ tự 45 dòng, 17/9/3 mã theo bộ lọc, mã tô
vàng, Top Picks mặc định HPG `TC-98 · NN+169` …). Mode v21 dùng v21_const thật (bỏ qua nếu vắng); mode live dùng
lớp dữ liệu GIẢ (không đọc kho) + một smoke test trên kho thật (bỏ qua nếu vắng). Socket bị chặn.
"""
from __future__ import annotations

import functools
import json
import os
import re
import socket
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import chaebol_map as M  # noqa: E402
import chaebol_map_dom as D  # noqa: E402
import chaebol_map_shell as S  # noqa: E402
import chaebol_map_tab_screener as SCR  # noqa: E402

V21_FILE = M.bridge_dir() / "data" / "chaebol_map" / "v21_const.json"
TODAY = date(2026, 9, 27)
_REAL = {}

DEFAULT_ORDER = ("VIC VHM VRE VPL MSN MSR FPT VCB BID CTG TCB MBB VPB STB ACB TPB SHB LPB SSB VIB GEX HPG HAH GMD MWG "
                 "GAS PLX BSR GVR VNM SAB VTP VGI NVL VPI SSI HCM VCI VIX VJC GEE GEL DGC PC1 CTD").split()
FRIENDLY = set("GEE VJC GEX VRE VIX VIC VHM MBB GMD TCB LPB HPG GEL VCI SHB VPL FPT".split())
NQ79 = set("BSR GAS VGI GVR CTG PLX VCB BID VTP".split())
ELIM = {"DGC", "PC1", "CTD"}
GOLD = set("GEX VIX VJC GEE GEL VCI GMD".split())


def setUpModule():
    def blocked(*a, **k):
        raise RuntimeError("mạng bị chặn trong test chaebol_map")
    for name in ("socket", "create_connection", "getaddrinfo"):
        _REAL[name] = getattr(socket, name)
        setattr(socket, name, blocked)


def tearDownModule():
    for name, fn in _REAL.items():
        setattr(socket, name, fn)


def walk(node):
    yield node
    if isinstance(node, dict):
        for ch in node.get("k", ()):
            yield from walk(ch)


def text_of(node):
    return node if isinstance(node, str) else "".join(text_of(c) for c in node.get("k", ()))


def find_key(node, key):
    return next((n for n in walk(node) if isinstance(n, dict) and n.get("key") == key), None)


def rows_of(root):
    return [n for n in walk(root) if isinstance(n, dict) and n.get("t") == "tr" and
            str(n.get("key", "")).startswith("scr.row.")]


def load_v21():
    if not V21_FILE.is_file():
        raise unittest.SkipTest("vắng v21_const.json")
    return json.loads(V21_FILE.read_text(encoding="utf-8"))


def make_ctx(mode, v21, data=None, dossier=None, cong=None):
    ctx = M.Ctx(mode, TODAY, list(S.TABS_V21))
    ctx.v21, ctx.tab, ctx.data, ctx.dossier = v21, "screener", data, dossier
    ctx.live_info = {"cong": cong} if cong else {}
    return ctx


# ── mini-resolver (DESIGN §4) để mô phỏng trạng thái trên cây builder ─────


def state_val(st, key):
    return "|".join(st.get(k, "") for k in key.split("|"))


def if_ok(cond, st):
    for k, want in (cond or {}).items():
        have = state_val(st, k)
        if have not in (want if isinstance(want, list) else [want]):
            return False
    return True


def resolved_rows(root, st):
    """→ [(tk, nền)] theo đúng if + sort + var của tbody (comparator dòng 6209–6221)."""
    vis = [r for r in rows_of(root) if if_ok(r.get("if"), st)]
    col, d = st["scr.sort"], (-1 if st["scr.dir"] == "desc" else 1)

    def cmp(a, b):
        x, y = a["sk"].get(col), b["sk"].get(col)
        if isinstance(x, str) and isinstance(y, str):
            return ((x > y) - (x < y)) * d
        z = (x or 0) - (y or 0)
        return ((z > 0) - (z < 0)) * d

    out = []
    for r in sorted(vis, key=functools.cmp_to_key(cmp)):
        bg = r["s"]["background"]
        for v in r.get("var") or []:
            if if_ok(v["if"], st):
                bg = v["s"]["background"]
        out.append((r["key"][8:], bg))
    return out


def count_grp(root, grp, st):
    """Số nút mang grp được render (tổ tiên là hàng: áp if của hàng)."""
    n = 0
    for r in rows_of(root):
        if if_ok(r.get("if"), st):
            n += sum(1 for x in walk(r) if isinstance(x, dict) and x.get("grp") == grp)
    return n


def picks(root, which, st):
    card = find_key(root, "scr.picks." + which)
    out = []
    for v in card["k"][1:]:
        if if_ok(v.get("if"), st):
            out += [text_of(row["k"][0]) + "|" + text_of(row["k"][2]) for row in v["k"]]
    return out


BASE = {"scr.sort": "perf", "scr.dir": "desc", "scr.phase": "ALL", "scr.sig": "ALL", "scr.chaebol": "ALL"}


# ── v21 ─────────────────────────────────────────────────────────────────────


class TestV21(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v21 = load_v21()
        with D.use_mode("v21", TODAY):
            cls.res = SCR.build_screener(make_ctx("v21", cls.v21))
        cls.root = cls.res["root"]

    def test_states_and_options(self):
        st = {s["key"]: s for s in self.res["states"]}
        self.assertEqual(st["scr.sort"]["default"], "perf")
        self.assertEqual(st["scr.sort"]["options"], ["perf", "tk", "phase", "sig", "px", "perf60", "ca60", "to60",
                                                     "td60", "nn60"])
        self.assertEqual(st["scr.dir"], {"key": "scr.dir", "default": "desc", "options": ["desc", "asc"]})
        self.assertEqual(st["scr.phase"]["options"], ["ALL", "CAP", "P1", "P2", "P2-P3", "MARKUP", "P3", "P3D"])
        self.assertEqual(st["scr.sig"]["options"], ["ALL", "BULL", "MIX", "BEAR"])
        self.assertEqual(st["scr.chaebol"]["options"], ["ALL", "CHAEBOL_FRIENDLY", "NQ79", "ELIMINATED"])
        exp = M.expected_options(self.v21)
        for k in ("scr.phase", "scr.sig", "scr.chaebol", "scr.dir"):
            self.assertEqual(sorted(st[k]["options"]), sorted(exp[k]), k)

    def test_core_contract_no_warnings(self):
        ctx = make_ctx("v21", self.v21)
        with D.use_mode("v21", TODAY):
            res = M.normalize_result("screener", SCR.build_screener(ctx), ctx)
        self.assertEqual(ctx.warnings, [])
        cov = M._coverage(res["states"], {"screener"}, self.v21)
        self.assertEqual(cov, {"missing": [], "mismatch": []})

    def test_structure_12_cols_9_sortable(self):
        ths = [n for n in walk(self.root) if isinstance(n, dict) and n.get("t") == "th"]
        self.assertEqual([t["k"][0] for t in ths],
                         ["MÃ", "NGÀNH", "NHÓM CHAEBOL", "PHASE", "SIG", "GIÁ", "Δ60D", "CÁ NHÂN", "TỔ CHỨC", "TỰ DOANH",
                          "NƯỚC NGOÀI", "NHẬN ĐỊNH"])
        self.assertEqual([t["on"]["sort"]["col"] for t in ths if "on" in t],
                         ["tk", "phase", "sig", "px", "perf60", "ca60", "to60", "td60", "nn60"])
        tbody = next(n for n in walk(self.root) if isinstance(n, dict) and n.get("t") == "tbody")
        self.assertEqual(tbody["sort"], {"key": "scr.sort", "dir": "scr.dir"})
        rows = rows_of(self.root)
        self.assertEqual(len(rows), 45)
        self.assertTrue(all(len([c for c in r["k"] if c["t"] == "td"]) == 12 for r in rows))
        self.assertEqual(rows[0]["sk"], {"tk": "VIC", "phase": 6, "sig": 0, "px": 224000, "perf60": 71.4, "ca60": 8.4,
                                         "to60": 12.7, "td60": -2, "nn60": -19.1})

    def test_golden_strings(self):
        main = find_key(self.root, "scr.main")
        self.assertEqual(text_of(main["k"][0]["k"][1]), "VN30+ Screener — Phase × Flow × Chaebol Matrix")
        sub = main["k"][0]["k"][2]["k"][0]
        self.assertEqual(sub["count"], {"grp": "scr.rows", "fmt": "{n}/45 mã · Pillar IV (FiinTrade verified ≤08/05 "
                                                                   "· NgườiQuanSát ≥09/05) as of 08/05/2026"})
        full = text_of(self.root)
        for s in ("Bảng matrix tổng hợp 45 mã VN30+ với 3 chiều phân loại đan vào nhau: Phase Howard Marks (đáy → đỉnh), "
                  "Flow signal Pillar IV (BULL/BEAR/MIX dựa trên 60d net buy 4 nhóm NĐT), và chaebol affiliation (nhóm "
                  "thân hữu chính trị). Click cột để sort. Filter để zoom vào nhóm cần.",
                  "HIỂN THỊ", "CAPIT.", "★ P2 ACC", "⚠ P3D DIST", "Tất cả", "Thân hữu", "NQ79/SOE", "⛔ Loại",
                  "● Đơn vị flow: triệu cổ phiếu KL khớp ròng 60 phiên", "● Vàng: chaebol thân hữu",
                  "● Đỏ: ⛔ loại khỏi cuộc / distribution", "● Xanh: tích lũy ★", "Top Picks Distilled từ Screener",
                  "★ STRONG BUY · BULL × P2/MARKUP × Tổ chức/NN tích cực", "⚠ AVOID · BEAR × P3D × NN/Tổ chức rút mạnh"):
            self.assertIn(s, full)

    def test_default_order_and_filters(self):
        self.assertEqual([tk for tk, _ in resolved_rows(self.root, BASE)], DEFAULT_ORDER)
        for val, want in (("CHAEBOL_FRIENDLY", FRIENDLY), ("NQ79", NQ79), ("ELIMINATED", ELIM)):
            got = [tk for tk, _ in resolved_rows(self.root, {**BASE, "scr.chaebol": val})]
            self.assertEqual(set(got), want, val)
            self.assertEqual(got, [t for t in DEFAULT_ORDER if t in want])

    def test_gold_ticker_colors(self):
        gold = {r["key"][8:] for r in rows_of(self.root) if r["k"][0]["s"]["color"] == D.C.gold}
        self.assertEqual(gold, GOLD)
        self.assertNotIn("LPB", gold)

    def test_summary_counts_default_and_filtered(self):
        want = {"scr.rows": 45, "scr.n.BULL": 15, "scr.n.MIX": 3, "scr.n.BEAR": 27, "scr.n.CAP": 5, "scr.n.P2": 13,
                "scr.n.P3D": 13}
        for grp, n in want.items():
            self.assertEqual(count_grp(self.root, grp, BASE), n, grp)
        th = {**BASE, "scr.chaebol": "CHAEBOL_FRIENDLY"}          # ảnh ref 42: 17 · 7 · 1 · 9 · 1 · 7 · 6
        self.assertEqual([count_grp(self.root, g, th) for g in want], [17, 7, 1, 9, 1, 7, 6])
        cards = [find_key(self.root, "scr.card." + g)["k"][1]["count"]["grp"] for g in want]
        self.assertEqual(cards, list(want))

    def test_top_picks_golden(self):
        buy = picks(self.root, "buy", BASE)
        self.assertEqual([b.split("|")[0] for b in buy], "HPG BSR GEL TCB MSN GEX VCI GMD".split())
        self.assertEqual(buy[0], "HPG|TC-98 · NN+169")
        self.assertEqual(buy[1], "BSR|TC+17 · NN+46")
        avoid = picks(self.root, "avoid", BASE)
        self.assertEqual([a.split("|")[0] for a in avoid], "SSI ACB TPB VRE HCM NVL MBB VHM".split())
        th = {**BASE, "scr.chaebol": "CHAEBOL_FRIENDLY"}           # ảnh ref 42
        self.assertEqual([b.split("|")[0] for b in picks(self.root, "buy", th)], "HPG GEL TCB GEX VCI GMD".split())
        self.assertEqual([a.split("|")[0] for a in picks(self.root, "avoid", th)], ["VRE", "MBB", "VHM"])

    def test_stripes_follow_position_after_sort_and_filter(self):
        for st in (BASE, {**BASE, "scr.sort": "nn60", "scr.dir": "asc", "scr.chaebol": "NQ79"},
                   {**BASE, "scr.sort": "tk", "scr.dir": "desc", "scr.sig": "BULL"},
                   {**BASE, "scr.sort": "phase", "scr.dir": "asc", "scr.phase": "P3D"}):
            got = resolved_rows(self.root, st)
            self.assertTrue(got, st)
            self.assertEqual([bg for _, bg in got],
                             ["transparent" if i % 2 == 0 else "#1f1d2440" for i in range(len(got))], st)
        order = [tk for tk, _ in resolved_rows(self.root, {**BASE, "scr.sort": "px", "scr.dir": "desc"})]
        self.assertEqual(order[:3], ["VIC", "VJC", "VHM"])

    def test_sort_header_arrow_and_active_color(self):
        th = find_key(self.root, "scr.th.px")
        self.assertEqual(th["k"][:2], ["GIÁ", " "])                 # hai nút chữ như `{label} {…}`
        self.assertEqual(th["on"], {"sort": {"key": "scr.sort", "dir": "scr.dir", "col": "px"}})
        self.assertEqual([c["if"] for c in th["k"][2:]], [{"scr.sort|scr.dir": "px|desc"}, {"scr.sort|scr.dir": "px|asc"}])
        self.assertEqual(th["var"][0]["s"]["color"], D.C.gold)

    def test_text_nodes_split_like_react(self):
        vic = find_key(self.root, "scr.row.VIC")
        tds = [c for c in vic["k"] if c["t"] == "td"]
        self.assertEqual(tds[5]["k"], ["224,000"])
        self.assertEqual(tds[6]["k"], ["+", "71.4", "%"])
        self.assertEqual(tds[9]["k"], ["-2.0"])
        self.assertEqual(tds[10]["k"], ["-19.1"])

    def test_v21_zero_keeps_js_sign(self):
        """Số 0 của V21 in đúng JS ('+' '0.0'); cờ zfix chỉ có tác dụng ở live."""
        ctd = [c for c in find_key(self.root, "scr.row.CTD")["k"] if c["t"] == "td"]
        self.assertEqual(ctd[10]["k"], ["+", "0.0"])
        with D.use_mode("v21", TODAY):
            self.assertEqual(SCR._sgn(-0.012, 1, zfix=True), ["", "-0.0"])
            self.assertEqual(SCR._sgn(0.0336, 1, zfix=True), ["+", "0.0"])

    def test_v21_has_no_live_marks(self):
        _, st = D.finalize(self.root)
        self.assertEqual((st["tiers"], st["can_data"], st["upd"], st["v21"]), ({}, 0, 0, 0))

    def test_filter_buttons(self):
        b = find_key(self.root, "scr.chaebol.CHAEBOL_FRIENDLY")
        self.assertEqual(b["t"], "button")
        self.assertEqual(b["on"], {"set": {"scr.chaebol": "CHAEBOL_FRIENDLY"}})
        self.assertEqual(b["var"][0]["s"], {"background": D.C.gold, "color": D.C.bg, "border": "1px solid " + D.C.gold,
                                            "fontWeight": 700})
        self.assertEqual(text_of(b), "Thân hữu")


# ── live (dữ liệu giả) ──────────────────────────────────────────────────────


FAKE_DATES = [(date(2026, 6, 28) + timedelta(days=i)).isoformat() for i in range(90)]   # tăng dần, cuối 25/09
WIN_FAKE = FAKE_DATES[-60:]                                                               # 28/07 → 25/09
GEL_REC = [d for i, d in enumerate(WIN_FAKE) if i % 3 == 0 and d <= "2026-09-18"]         # tự doanh thưa, dừng 18/09


class FakeData:
    """Lớp dữ liệu giả đủ các hàm builder dùng; trả V như chaebol_map_data. NN mỗi phiên −1 M cp; tự doanh mỗi phiên
    có bản ghi +0,1 M cp, bản ghi tới 24/09 (GEL: thưa, tới 18/09); VHM có GDKHQ cổ tức CP 100% ngày 06/08 (kèm cổ tức
    tiền / quyền mua / ESOP phải bị bỏ qua); CTD không có events-v2."""

    def __init__(self, V):
        self.V = V
        self.basket_list = sorted(set(DEFAULT_ORDER[:20]) - {"VPL"} | {"HDB", "MCH", "TCX"})

    def can_data(self, why):
        return self.V(None, None, None, None, None, why)

    def basket(self, name="VN30"):
        return self.V(self.basket_list, None, "FACT-T2", "2026-09-27", "vnstore.ma.nhom")

    def last_price(self, tk):
        if tk == "TCX":
            return {"date": None, "raw": self.can_data("không có cache"), "adj": self.can_data("x")}
        return {"date": "2026-09-25", "raw": self.V(10000.0 + len(tk), None, "FACT-T2", "2026-09-25", "vc_lk")}

    def price_history(self, tk):
        class P:
            dates = list(FAKE_DATES)
        return P()

    def pct_change(self, tk, d0):
        return self.V(-0.04 if tk == "SAB" else -12.34, None, "EST", "2026-09-25", "vc_lk adj")

    def flow4(self, tk, n=60):          # như lớp cũ: td.asof = ngày cuối cửa sổ GIÁ (25/09), không phải bản ghi cuối
        nn = {"HDB": 33.3, "VGI": -0.001}.get(tk, -4.44)         # VGI/SAB/VPL: số sống làm tròn bằng 0
        td = {"SAB": -0.0245, "VPL": 0.0251}.get(tk, 1.5)
        return {"nn": self.V(nn, None, "FACT-T2", "2026-09-25", "vc_lk", "nn"),
                "td": self.V(td, None, "FACT-T2", "2026-09-25", "vc_lk", "td"),
                "ca": self.can_data("x"), "tc": self.can_data("x"), "sig": self.can_data("x")}

    def _seg(self, n, end):
        i = FAKE_DATES.index(end or FAKE_DATES[-1])
        return FAKE_DATES[i - n + 1:i + 1]

    def _rec(self, tk):
        return set(GEL_REC) if tk == "GEL" else {d for d in FAKE_DATES if d <= "2026-09-24"}

    def foreign_net(self, tk, n=60, end=None):
        seg = self._seg(n, end)
        return {"vol": self.V(-1e6 * len(seg), None, "FACT-T2", seg[-1], "vc_lk"), "n": len(seg)}

    def prop_net(self, tk, n=60, end=None, kind="total"):
        got = [d for d in self._seg(n, end) if d in self._rec(tk)]
        vol = self.V(1e5 * len(got), None, "FACT-T2", self._seg(n, end)[-1], "vc_lk") if got else self.can_data("x")
        return {"vol": vol, "n": n, "n_co": len(got)}

    def capital_events(self, tk):
        if tk == "CTD":
            return self.can_data("không có vc_lk/CTD/events-v2")
        ev = []
        if tk == "VHM":
            ev = [{"code": "ISS", "title": "Phát hành cổ phiếu - Trả Cổ tức bằng Cổ phiếu tỉ lệ 100.0%",
                   "exright": "2026-08-06", "ratio": 1.0},
                  {"code": "DIV", "title": "Trả cổ tức bằng tiền mặt - 6,000 VND", "exright": "2026-08-20", "ratio": 0.6},
                  {"code": "ISS", "title": "Phát hành cổ phiếu - Quyền mua CP cho Cổ đông hiện hữu tỉ lệ 10.0%",
                   "exright": "2026-09-01", "ratio": 0.1},
                  {"code": "ISS", "title": "Phát hành cổ phiếu - Phát hành cho CBCNV tỉ lệ 1.0%",
                   "exright": "2026-09-02", "ratio": 0.01},
                  {"code": "ISS", "title": "Phát hành cổ phiếu - Cổ phiếu thưởng tỉ lệ 10.0%",   # trước cửa sổ
                   "exright": "2026-07-20", "ratio": 0.1}]
        return self.V(ev, None, "FACT-T2", "2026-09-26", "vc_lk/events-v2")

    def details(self, tk):
        return {"sector": "Ngân hàng"}

    def groups_of(self, tk):
        return ["Masan-TCB"]

    def pattern_label(self, tk, label):
        return label if tk in self.basket_list else label + "?"


class FakeNoEvents(FakeData):
    """Lớp dữ liệu cũ (chưa có capital_events/prop_net): không kiểm được ngày TD / quy đổi → [CẦN DATA], không số sai."""
    capital_events = None
    prop_net = None


DGC_SRC41 = "VN_Filings/DGC/IR_KQKD/…559594.pdf (trang 2)"
DOSSIER = {"tickers": {"TCB": {"screener": {"chaebol": {
    "text": "Masan-Hồ Hùng Anh (Masan 14.80%)", "tier": "FACT-T2", "asof": "2026-06-30", "src": "lk_hoso/TCB.json"}}},
    "ACB": {"screener": {"chaebol": {"text": "không src", "tier": "FACT-T2"}}},
    "DGC": {"screener": {"cmt": {
        "text": "-49.7%. KHỞI TỐ. ĐHĐCĐ bất thường 08/05/2026", "tier": "FACT-T1", "asof": "2026-05-08",
        "src": "VN_Filings/DGC/DHCD/…546703.pdf (trang 2)",
        "parts": [{"text": "-49.7%", "tier": "EST", "asof": "2026-04-29", "src": "v21_const FLOW.DGC.perf60"},
                  {"text": ". KHỞI TỐ", "tier": "FACT-T1", "asof": "2026-03-17", "src": DGC_SRC41},
                  {"text": ". ĐHĐCĐ bất thường 08/05/2026", "tier": "FACT-T1", "asof": "2026-05-08",
                   "src": "VN_Filings/DGC/DHCD/…546703.pdf (trang 2)", "upd": True}]}}},
    "PC1": {"screener": {"cmt": {                                # một phần thiếu src → không dùng parts
        "text": "PC1 viết lại", "tier": "FACT-T2", "asof": "2026-09-01", "src": "x",
        "parts": [{"text": "a", "tier": "EST", "src": "y"}, {"text": "b", "tier": "FACT-T1"}]}}}}}
CONG = {"text": "CỔNG: [CẦN DATA — M2] · không kết luận per-mã", "as_of": "2026-09-27"}


def _has_mark(node):
    return any(isinstance(x, dict) and ("_tier" in x or x.get("_can") or x.get("_v21") or x.get("_upd"))
               for x in walk(node))


class TestLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v21 = load_v21()
        import chaebol_map_data as CD
        cls.fake = FakeData(CD.V)
        cls.ctx = make_ctx("live", cls.v21, data=cls.fake, dossier=DOSSIER, cong=CONG)
        with D.use_mode("live", TODAY):
            cls.res = SCR.build_screener(cls.ctx)
        cls.root = cls.res["root"]

    def test_rows_added_and_basket_tag(self):
        rows = [r["key"][8:] for r in rows_of(self.root)]
        self.assertEqual(rows[:45], DEFAULT_ORDER)
        self.assertEqual(rows[45:], ["HDB", "MCH", "TCX"])
        vpl = text_of(find_key(self.root, "scr.row.VPL")["k"][0])
        self.assertIn("ngoài VN30 hiện hành", vpl)
        self.assertNotIn("ngoài VN30", text_of(find_key(self.root, "scr.row.VIC")["k"][0]))
        hdb = find_key(self.root, "scr.row.HDB")
        self.assertIn("Sovico", text_of(hdb))                       # CHAEBOL_GROUPS V21 (nhóm 03)
        self.assertEqual(hdb["if"]["scr.phase"], ["ALL"])            # không có pha V21 → chỉ hiện khi ALL
        self.assertIn("CHAEBOL_FRIENDLY", hdb["if"]["scr.chaebol"])
        sub = find_key(self.root, "scr.main")["k"][0]["k"][2]["k"][0]
        self.assertTrue(sub["count"]["fmt"].startswith("{n}/48 mã · "))

    def test_every_number_cell_labelled_or_can_data(self):
        for r in rows_of(self.root):
            tds = [c for c in r["k"] if c["t"] == "td"]
            for i in range(4, 12):                              # SIG … NHẬN ĐỊNH
                self.assertTrue(_has_mark(tds[i]), (r["key"], i, text_of(tds[i])))
            for i in (7, 8):                                    # CÁ NHÂN / TỔ CHỨC sau 08/05
                self.assertIn("[CẦN DATA]", text_of(tds[i]))
            self.assertIn("[CẦN DATA]", text_of(tds[4]))        # SIG 4 kênh
        tcx = [c for c in find_key(self.root, "scr.row.TCX")["k"] if c["t"] == "td"]
        self.assertIn("[CẦN DATA]", text_of(tcx[5]))            # thiếu giá → không bao giờ 0/trống
        for w in ("buy", "avoid"):
            for v in find_key(self.root, "scr.picks." + w)["k"][1:]:
                for row in v["k"]:
                    self.assertTrue(_has_mark(row["k"][2]), text_of(row))

    def test_bare_numbers_nowhere_in_table(self):
        """Không ô số nào (GIÁ…NƯỚC NGOÀI) chỉ có chữ số mà thiếu nhãn."""
        for r in rows_of(self.root):
            for td in [c for c in r["k"] if c["t"] == "td"][5:11]:
                if re.search(r"\d", text_of(td)):
                    self.assertTrue(any("_tier" in x for x in walk(td) if isinstance(x, dict)), text_of(td))

    def test_live_values_and_tiers(self):
        tds = [c for c in find_key(self.root, "scr.row.HDB")["k"] if c["t"] == "td"]
        self.assertEqual(tds[5]["k"][0], "10,003")
        self.assertEqual(text_of(tds[6]), "-12.3%E")
        self.assertEqual(text_of(tds[9]), "+1.5T2·24/09")           # ngày khác phiên tham chiếu → ghi ngày
        self.assertEqual(text_of(tds[10]), "+33.3T2")
        self.assertEqual(tds[10]["s"]["color"], D.C.forest)
        row = find_key(self.root, "scr.row.HDB")
        self.assertEqual(row["sk"], {"tk": "HDB", "phase": -1, "sig": -1, "px": 10003.0, "perf60": -12.34, "td60": 1.5,
                                     "nn60": 33.3})

    def test_live_zero_rounded_has_no_sign(self):
        """Vòng hoàn thiện 27/09 (final_check §6.1 #2): số sống làm tròn bằng 0 in '0.0' không dấu (lõi zfix), không
        '-0.0'/'+0.0'; khoá sắp và CSV giữ số gốc; số V21 ở Top Picks không đổi."""
        sab = [c for c in find_key(self.root, "scr.row.SAB")["k"] if c["t"] == "td"]
        self.assertEqual(text_of(sab[6]), "0.0%E")
        self.assertEqual(text_of(sab[9]), "0.0T2·24/09")
        self.assertEqual(sab[9]["k"][0], "0.0")                       # không còn nút '+' / '-'
        vpl = [c for c in find_key(self.root, "scr.row.VPL")["k"] if c["t"] == "td"]
        self.assertEqual(text_of(vpl[9]), "0.0T2·24/09")
        vgi = [c for c in find_key(self.root, "scr.row.VGI")["k"] if c["t"] == "td"]
        self.assertEqual(text_of(vgi[10]), "0.0T2")
        for r in rows_of(self.root):
            for td in [c for c in r["k"] if c["t"] == "td"][5:11]:
                self.assertNotRegex(text_of(td), r"^[+-]0\.0(?!\d)", r["key"])
        self.assertEqual(find_key(self.root, "scr.row.SAB")["sk"]["td60"], -0.0245)
        self.assertEqual(find_key(self.root, "scr.row.VGI")["sk"]["nn60"], -0.001)
        csv = {d["ma"]: d for d in self.res["csv"]}
        self.assertEqual((csv["SAB"]["td60_trieu_cp"], csv["SAB"]["delta60_pct"]), (-0.0245, -0.04))
        with D.use_mode("live", TODAY):
            self.assertEqual(SCR._sgn(-0.012, 1, zfix=True), ["", "0.0"])
            self.assertEqual(SCR._sgn(-0.012, 1), ["", "-0.0"])        # số V21 (Top Picks) không bật zfix
            self.assertEqual(SCR._sgn(-0.05, 1, zfix=True), ["", "-0.1"])

    def test_td_date_is_last_record_not_window_end(self):
        """Kiểm chứng 27/09 #1: ô TD mang ngày bản ghi tự doanh cuối (DESIGN §9), không phải 25/09 của cửa sổ giá."""
        vic = [c for c in find_key(self.root, "scr.row.VIC")["k"] if c["t"] == "td"][9]
        self.assertEqual(text_of(vic), "+1.5T2·24/09")                  # chỉ trễ ở đuôi → không dấu độ phủ
        gel = [c for c in find_key(self.root, "scr.row.GEL")["k"] if c["t"] == "td"][9]
        last = GEL_REC[-1]
        self.assertEqual(text_of(gel), "+1.5T2·%s/%s%d/60 phiên" % (last[8:10], last[5:7], len(GEL_REC)))
        self.assertTrue(any(isinstance(x, dict) and x.get("t") == "div" for x in gel["k"]))   # dòng phụ, không nới cột
        csv = {d["ma"]: d for d in self.res["csv"]}
        self.assertEqual(csv["GEL"]["td60_trieu_cp_asof"], last)
        self.assertEqual(csv["GEL"]["td60_phien_co"], "%d/60" % len(GEL_REC))
        self.assertEqual(csv["VIC"]["td60_trieu_cp_asof"], "2026-09-24")

    def test_share_basis_conversion(self):
        """Kiểm chứng 27/09 #2: KL trước GDKHQ cổ tức CP quy về cp hiện hành (×2 cho 100%); cổ tức tiền, quyền mua,
        ESOP và sự kiện trước cửa sổ bị bỏ qua; số quy đổi mang nhãn E."""
        i = WIN_FAKE.index("2026-08-06")                           # 9 phiên trước GDKHQ trong cửa sổ
        tds = [c for c in find_key(self.root, "scr.row.VHM")["k"] if c["t"] == "td"]
        nn = -(i * 2 + (60 - i))
        self.assertEqual(text_of(tds[10]), "%+.1fE" % nn)
        td = (i * 2 + (59 - i)) * 0.1                                # tự doanh có bản ghi tới 24/09
        self.assertEqual(text_of(tds[9]), "+%.1fE·24/09" % td)
        self.assertEqual(find_key(self.root, "scr.row.VHM")["sk"]["nn60"], nn)
        csv = {d["ma"]: d for d in self.res["csv"]}
        self.assertEqual(csv["VHM"]["quy_doi_quyen"], "2026-08-06 ×2")
        self.assertEqual(csv["VHM"]["nn60_trieu_cp_bac"], "EST")
        self.assertEqual(csv["VIC"]["quy_doi_quyen"], "")
        self.assertEqual(csv["VIC"]["nn60_trieu_cp_bac"], "FACT-T2")
        note = text_of(find_key(self.root, "scr.main"))
        self.assertIn("VHM ×2 (06/08)", note)
        self.assertIn("không tính cổ tức tiền, quyền mua", note)
        self.assertTrue(any("events-v2" in w and "CTD" in w for w in self.ctx.warnings))
        self.assertEqual(csv["CTD"]["nn60_trieu_cp_bac"], "FACT-T2")    # không kiểm được → giữ số vendor + cảnh báo

    def test_flow_basis_unavailable_gives_can_data(self):
        import chaebol_map_data as CD
        ctx = make_ctx("live", self.v21, data=FakeNoEvents(CD.V), dossier=DOSSIER, cong=CONG)
        with D.use_mode("live", TODAY):
            res = SCR.build_screener(ctx)
        tds = [c for c in find_key(res["root"], "scr.row.VIC")["k"] if c["t"] == "td"]
        self.assertIn("[CẦN DATA]", text_of(tds[9]))
        self.assertIn("[CẦN DATA]", text_of(tds[10]))
        self.assertEqual(text_of(tds[5]), "10,003T2")                  # giá vẫn sống
        self.assertTrue(any("không kiểm được ngày tự doanh" in w for w in ctx.warnings))

    def test_dgc_comment_parts_each_tiered(self):
        """Kiểm chứng 27/09 #3: '-49.7%' là % FLOW V21 (E·29/04), không nằm dưới FACT-T1·08/05."""
        dgc = [c for c in find_key(self.root, "scr.row.DGC")["k"] if c["t"] == "td"][11]
        self.assertEqual(text_of(dgc), "-49.7%E·29/04. KHỞI TỐT1·17/03. ĐHĐCĐ bất thường 08/05/2026T1·08/05↻27/09")
        pc1 = [c for c in find_key(self.root, "scr.row.PC1")["k"] if c["t"] == "td"][11]
        self.assertEqual(text_of(pc1), "PC1 viết lạiT2·01/09↻27/09")      # phần thiếu src → không dùng parts

    def test_top_picks_delta_is_est(self):
        """Kiểm chứng 27/09 #4: Δ perf60 ở Top Picks là % dẫn xuất → E·ngày; NN/CN FiinTrade giữ T2."""
        rows = [row for v in find_key(self.root, "scr.picks.avoid")["k"][1:] for row in v["k"]]
        self.assertTrue(rows)
        for row in rows:
            self.assertRegex(text_of(row["k"][1]), r"Δ[+-]\d+%E·\d\d/\d\d$")
            self.assertRegex(text_of(row["k"][2]), r"T2·\d\d/\d\d$")
        ssi = next(r for r in rows if text_of(r["k"][0]) == "SSI")
        self.assertEqual(text_of(ssi["k"][1]), "P3D · Δ+16%E·07/05")

    def test_sub_states_window_not_stitch(self):
        """Kiểm chứng 27/09 #5: NN/TD là 60 phiên vc_lk thuần (không nối FiinTrade ≤08/05 với ≥09/05)."""
        sub = find_key(self.root, "scr.main")["k"][0]["k"][2]["k"][0]["count"]["fmt"]
        self.assertEqual(sub, "{n}/48 mã · Pillar IV · NN/TD vc_lk 60 phiên 28/07→25/09/2026 (TD tới 24/09) · "
                              "Top Picks: FiinTrade ≤08/05 đóng băng")
        self.assertNotIn("≥09/05", sub)
        self.assertIn("riêng GEL %s/%s" % (GEL_REC[-1][8:10], GEL_REC[-1][5:7]), text_of(self.root))

    def test_live_layout_single_line(self):
        """Kiểm chứng 27/09 #6: tiêu đề cột không gãy (nowrap, chỉ live); SIG một dòng; v21 giữ nguyên."""
        for th in [n for n in walk(self.root) if isinstance(n, dict) and n.get("t") == "th"]:
            self.assertEqual(th["s"].get("whiteSpace"), "nowrap", text_of(th))
        self.assertEqual([th["k"][0] for th in walk(self.root) if isinstance(th, dict) and th.get("t") == "th"][9:11],
                         ["TỰ DOANH", "NƯỚC NGOÀI"])                   # giữ nhãn trang, không rút gọn TD/NN
        sig = [c for c in find_key(self.root, "scr.row.VIC")["k"] if c["t"] == "td"][4]
        self.assertEqual(sig["s"].get("whiteSpace"), "nowrap")
        self.assertEqual(text_of(sig), "[CẦN DATA]·V21 BEAR")
        self.assertFalse([c for c in sig["k"] if isinstance(c, dict) and c.get("t") == "div"])
        v21 = load_v21()
        with D.use_mode("v21", TODAY):
            root = SCR.build_screener(make_ctx("v21", v21))["root"]
        self.assertFalse([n for n in walk(root) if isinstance(n, dict) and n.get("t") == "th"
                          and "whiteSpace" in n["s"]])
        self.assertIsNone(find_key(root, "scr.picks")["k"][0]["k"][2:] or None)   # v21: Section Top Picks không sub

    def test_stance_kept_with_v21_mark_and_archive_label(self):
        vic_cmt = [c for c in find_key(self.root, "scr.row.VIC")["k"] if c["t"] == "td"][11]
        self.assertTrue(text_of(vic_cmt).startswith("Reflexivity peak. NN -19.1M 60d, BEAR signal"))
        self.assertIn("V21·12/05", text_of(vic_cmt))
        head = find_key(self.root, "scr.picks")["k"][0]             # dấu lưu trữ ở dòng tiêu đề khối (sub)
        self.assertIn("bản lưuV21·12/05 · FiinTrade ≤08/05 đóng băng · lưu trữ, không phải khuyến nghị", text_of(head))
        for w in ("buy", "avoid"):                                   # V21·12/05 nằm NGAY trên dòng tiêu đề thẻ
            title = find_key(self.root, "scr.picks." + w)["k"][0]
            self.assertTrue(text_of(title).endswith("V21·12/05"), text_of(title))
            self.assertFalse([c for c in title["k"] if isinstance(c, dict) and c.get("t") == "div"])
        self.assertEqual([b.split("|")[0] for b in picks(self.root, "buy", BASE)], "HPG BSR GEL TCB MSN GEX VCI GMD".split())
        for grp in ("scr.n.BULL", "scr.n.CAP"):
            self.assertIn("V21·12/05", text_of(find_key(self.root, "scr.card." + grp)))
        self.assertIn("vì CỔNG v1.7 đang DỪNG", text_of(self.root))

    def test_dossier_label_fix_and_src_rule(self):
        tcb = text_of([c for c in find_key(self.root, "scr.row.TCB")["k"] if c["t"] == "td"][2])
        self.assertIn("Masan-Hồ Hùng Anh (Masan 14.80%)", tcb)
        self.assertIn("V21: Vingroup ecosystem", tcb)
        self.assertIn("↻27/09", tcb)
        acb = text_of([c for c in find_key(self.root, "scr.row.ACB")["k"] if c["t"] == "td"][2])
        self.assertTrue(acb.startswith("TLG family"))              # mục thiếu src → không dùng
        tcb_row = find_key(self.root, "scr.row.TCB")               # bộ lọc vẫn chạy trên nhãn V21
        self.assertIn("CHAEBOL_FRIENDLY", tcb_row["if"]["scr.chaebol"])

    def test_pattern_suffix_outside_tv30(self):
        vci = text_of([c for c in find_key(self.root, "scr.row.VCI")["k"] if c["t"] == "td"][11])
        self.assertIn("Pattern B?", vci)
        tcb = text_of([c for c in find_key(self.root, "scr.row.TCB")["k"] if c["t"] == "td"][11])
        self.assertIn("Pattern B done", tcb)

    def test_stripes_live(self):
        st = {**BASE, "scr.sort": "nn60", "scr.dir": "desc"}
        got = resolved_rows(self.root, st)
        self.assertEqual(len(got), 48)
        self.assertEqual(got[0][0], "HDB")
        self.assertEqual([bg for _, bg in got], ["transparent" if i % 2 == 0 else "#1f1d2440" for i in range(48)])

    def test_live_without_data_module(self):
        ctx = make_ctx("live", self.v21, data=None, dossier=None)
        with D.use_mode("live", TODAY):
            res = SCR.build_screener(ctx)
        self.assertTrue(any("chaebol_map_data" in w for w in ctx.warnings))
        for r in rows_of(res["root"]):
            tds = [c for c in r["k"] if c["t"] == "td"]
            for i in (5, 6, 7, 8, 9, 10):
                self.assertIn("[CẦN DATA]", text_of(tds[i]))


class TestAssemble(unittest.TestCase):
    def test_v21_assemble_tab_only(self):
        load_v21()
        with D.use_mode("v21", TODAY):
            files, manifest, _ = M.assemble("v21", TODAY, only={"screener"})
        tab = next(t for t in manifest["tabs"] if t["id"] == "screener")
        self.assertEqual(tab["status"], "ok")
        self.assertEqual(manifest["inventory"]["coverage"], {"missing": [], "mismatch": []})
        self.assertFalse([w for w in manifest["warnings"] if w.startswith("[screener]")])
        obj = json.loads(files["tab_screener.json"])
        self.assertEqual(sorted(obj["root"]["scope"]), sorted(["scr.sort", "scr.dir", "scr.phase", "scr.sig",
                                                               "scr.chaebol"]))

    def test_live_smoke_real_store(self):
        if not (M.bridge_dir() / "state" / "vc_lk" / "VIC" / "price-history.json").is_file():
            raise unittest.SkipTest("vắng kho vc_lk")
        load_v21()
        with D.use_mode("live", TODAY):
            files, manifest, _ = M.assemble("live", TODAY, only={"screener"})
        tab = next(t for t in manifest["tabs"] if t["id"] == "screener")
        self.assertEqual(tab["status"], "ok")
        self.assertFalse([w for w in manifest["warnings"] if "builder lỗi" in w])
        obj = json.loads(files["tab_screener.json"])
        self.assertGreaterEqual(len(rows_of(obj["root"])), 45)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    unittest.main()
