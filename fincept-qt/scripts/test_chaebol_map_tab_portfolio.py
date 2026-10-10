#!/usr/bin/env python3
"""Unit tests — tab 08 · DANH MỤC (build_portfolio) và ★ 13 · ACTION PORTFOLIO 25 (build_portfolio25) của chaebol_map.

Chạy (cả hai trình thông dịch, không mạng — socket bị chặn):
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest scripts/test_chaebol_map_tab_portfolio.py -v
    PYTHONDONTWRITEBYTECODE=1 ~/Library/Application\\ Support/com.fincept.terminal/venv-numpy2/bin/python \\
        -m unittest scripts/test_chaebol_map_tab_portfolio.py

Chuỗi vàng: chaebol_map_spec/page_p6_portfolio_research.md §4.1–4.5 (đối chiếu main.innerText trang thật) và
page_p7a_claims54_catalyst_port25.md §4 (5 nút, 25 hàng, Core 5 · Growth 8 · Tactical 2 · Avoid 10).
Mode live kiểm bằng lớp dữ liệu GIẢ (không đọc kho) + một smoke test trên kho thật (bỏ qua nếu vắng).
"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import types
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import chaebol_map as M  # noqa: E402
import chaebol_map_dom as DOM  # noqa: E402
import chaebol_map_shell as S  # noqa: E402
import chaebol_map_tab_portfolio as P  # noqa: E402

V21_PATH = Path.home() / "SECOND BRAIN-OBSIDIAN/_System/fincept_bridge/data/chaebol_map/v21_const.json"
TODAY = date(2026, 9, 27)
_REAL = {}


def setUpModule():
    def blocked(*a, **k):
        raise RuntimeError("mạng bị chặn trong test chaebol_map_tab_portfolio")
    for name in ("socket", "create_connection", "getaddrinfo"):
        _REAL[name] = getattr(socket, name)
        setattr(socket, name, blocked)


def tearDownModule():
    for name, fn in _REAL.items():
        setattr(socket, name, fn)


def walk(n):
    yield n
    if isinstance(n, dict):
        for c in n.get("k", ()):
            yield from walk(c)


def text(n):
    return n if isinstance(n, str) else "".join(text(c) for c in n.get("k", ()))


def by_key(n, key):
    return next((x for x in walk(n) if isinstance(x, dict) and x.get("key") == key), None)


def load_v21():
    if not V21_PATH.is_file():
        return None
    return json.loads(V21_PATH.read_text(encoding="utf-8"))


def make_ctx(mode, v21, data=None, dossier=None, cong=None):
    ctx = M.Ctx(mode, TODAY, list(S.TABS_V21))
    ctx.v21, ctx.data, ctx.dossier = v21, data, dossier
    ctx.live_info = {"cong": cong or {"text": "CỔNG: [CẦN DATA — test] · không kết luận per-mã", "as_of": "2026-09-27",
                                      "tier": "EST", "src": "test"}}
    return ctx


def resolve(node, state):
    """Áp `if` (DESIGN §4) — trả cây chỉ còn nút được render."""
    if isinstance(node, str):
        return node
    for k, v in (node.get("if") or {}).items():
        cur = "|".join(state.get(x, "") for x in k.split("|"))
        if cur not in (v if isinstance(v, list) else [v]):
            return None
    kids = [resolve(c, state) for c in node.get("k", ())]
    out = dict(node)
    out["k"] = [c for c in kids if c is not None]
    return out


# ── kiểm "số trần thiếu nhãn" (DESIGN §8.4) trên cây builder CHƯA finalize (còn cờ _tier/_can/_v21/_upd) ─────

_MARK = ("_tier", "_can", "_v21", "_upd")
_STRUCT = [r"\d{4}-\d{2}-\d{2}", r"\d{1,2}/\d{1,2}(/\d{2,4})?", r"\bC\d{2}\b", r"\bV2[01]\b", r"\bVN(30|100)\b",
           r"L1\+L2\+L3", r">5% NAV", r"\bQ\d/\d{4}\b", r"Keynote 13", r"Khối 11", r"\b\d{4}–\d{4}\b", r"\b[A-Z]{3}\d\b",
           r"\b(TUẦN|Tuần) \d+-\d+", r"\b0[89] ·", r"\b1[0-4] ·", r"\bP\d\b", r"\b6T/\d{4}\b"]


def has_mark(n):
    return any(isinstance(x, dict) and any(x.get(m) for m in _MARK) for x in walk(n))


def structural(s):
    t = s
    for p in _STRUCT:
        t = re.sub(p, "", t)
    return not re.search(r"\d", t)


def uncovered_numbers(root, depth=4):
    bad = []

    def rec(n, anc):
        if n.get("t") == "h2":
            return
        for ch in n.get("k", ()):
            if isinstance(ch, str):
                if re.search(r"\d", ch) and not structural(ch):
                    chain = [n] + anc[::-1]
                    if not any(has_mark(a) for a in chain[:depth]):
                        bad.append((ch[:80], n.get("key")))
            else:
                rec(ch, anc + [n])
    rec(root, [])
    return bad


# ── lớp dữ liệu GIẢ (hàm cùng tên chaebol_map_data; không đọc kho) ──────────


def fake_data():
    import chaebol_map_data as RD
    V = RD.V
    px = {"MSN": 70100, "VCB": 58000, "FPT": 64700, "GEX": 24000, "HPG": 20650, "BSR": 30400, "VCI": 19800,
          "VIC": 232000, "VHM": 69100, "VRE": 24500, "VJC": 132800, "GEE": 73900, "KSV": 106200, "ACV": 39400}
    px0 = {"ACV": 43800}                     # giá thô 12/05 (ACV không có GDKHQ; chuỗi điều chỉnh vendor nhiễu)
    f = {"FPT": 0.8967, "HPG": 0.9091, "VJC": 0.7692}
    ns = types.SimpleNamespace()

    def close(tk, d=None, adjusted=False):
        if tk not in px:
            return RD.can_data("giả: không có " + tk)
        if d and tk in px0 and not adjusted:
            return V(float(px0[tk]), None, "FACT-T2", "2026-05-12", "fake", None, "đ")
        return V(float(px[tk]), None, "FACT-T2", "2026-09-25", "fake", None, "đ")
    ns.close = close
    ns.pct_change = lambda tk, d0, d1=None: (V(-5.0, "-5.0%", "EST", "2026-09-25", "fake", None, "%") if tk in px
                                             else RD.can_data("giả"))
    ns.adj_factor = lambda tk, d0, d1=None: V(f.get(tk, 1.0), "%.4f" % f.get(tk, 1.0), "EST", "2026-09-25", "fake", "", "x")
    ev = {"FPT": [{"code": "ISS", "title": "Phát hành cổ phiếu - Cổ phiếu thưởng tỉ lệ 10.0%", "exright": "2026-09-21",
                   "public_date": "2026-08-20", "ratio": 0.1, "ratio_text": "10.00 cp/100 cp"},
                  {"code": "ISS", "title": "Phát hành cổ phiếu - Phát hành cho CBCNV tỉ lệ 0.5%", "exright": "2026-06-24",
                   "public_date": "2026-06-01", "ratio": 0.005, "ratio_text": "0.50 cp/100 cp"}],
          # cổ tức tiền CÔNG BỐ trước 08/05 nhưng GDKHQ 11/05 — phải hiện (lọc theo GDKHQ, không theo ngày công bố)
          "HPG": [{"code": "DIV", "title": "Trả cổ tức bằng tiền mặt - Cả năm 2025 - 500 VND", "exright": "2026-05-11",
                   "public_date": "2026-04-20", "ratio": 0.05, "ratio_text": "500 đ/cp"},
                  {"code": "ISS", "title": "Phát hành cổ phiếu - Trả Cổ tức bằng Cổ phiếu tỉ lệ 10.0%",
                   "exright": "2026-05-25", "public_date": "2026-05-10", "ratio": 0.1, "ratio_text": "10.00 cp/100 cp"}],
          "VHM": [{"code": "ISS", "title": "Phát hành cổ phiếu - Trả Cổ tức bằng Cổ phiếu tỉ lệ 100.0%",
                   "exright": "2026-08-06", "public_date": "2026-07-20", "ratio": 1.0, "ratio_text": "100.00 cp/100 cp"}]}
    ns.capital_events = lambda tk, since=None: V(
        [e for e in ev.get(tk, []) if not since or e["public_date"] >= since], None, "FACT-T2", "2026-09-21", "fake")

    def pnl_since(tk, d0, px0=None, position=None, cost=None):
        pc = ns.pct_change(tk, d0)
        val = position * px0 * 0.95
        return {"pct": pc, "now": ns.close(tk), "factor": ns.adj_factor(tk, d0),
                "value_now": V(val, None, "EST", "2026-09-25", "fake", None, "đ"),
                "pnl": V(val - position * cost, None, "EST", "2026-09-25", "fake", None, "đ"),
                "pnl_pct": V((val / (position * cost) - 1) * 100, None, "EST", "2026-09-25", "fake", None, "%")}
    ns.pnl_since = pnl_since
    # tự doanh: như chaebol_map_data.prop_net — asof = cuối cửa sổ (25/09), bản ghi thật chỉ tới 24/09 (ghi trong note)
    td_note = ("41/60 phiên có bản ghi tự doanh (01/07/2026→25/09/2026); phiên vắng không điền 0; "
               "dữ liệu tự doanh tới 24/09/2026")
    ns.flow4 = lambda tk, n=60, end=None: {
        "n": 60, "from": "2026-07-01", "to": "2026-09-25",
        "nn": V(-3.5, "-3.5", "FACT-T2", "2026-09-25", "fake", "60 phiên", "M cp"),
        "td": V(-1.6, "-1.6", "FACT-T2", "2026-09-25", "fake", td_note, "M cp"),
        "du": V(5.1, "5.1", "EST", "2026-09-25", "−(nn+td)", "phần dư", "M cp"),
        "ca": RD.can_data("giả"), "tc": RD.can_data("giả"), "sig": RD.can_data("giả")}
    # KL theo đoạn (quy đổi qua thưởng/cổ tức CP): mỗi phiên NN −1 tr cp, TD −0,2 tr cp
    ns.foreign_net = lambda tk, n=60, end=None: {"vol": V(-1e6 * n, None, "FACT-T2", "2026-09-25", "fake", None, "cp")}
    ns.prop_net = lambda tk, n=60, end=None, kind="total": {
        "vol": V(-2e5 * n, None, "FACT-T2", "2026-09-25", "fake", td_note, "cp"), "n": n, "n_co": n}
    class PH:
        dates = ["2026-06-30", "2026-09-25"]

        def __len__(self):
            return 2
    ns.price_history = lambda tk: PH()
    ns.data_to = lambda: "2026-09-25"

    def book(date_, pos, cash, unexpl, avoid, watch, cands, xung, src):
        ps = [{"tk": t, "nav": float(n), "verified": v, **({"layer": l} if l else {})} for t, n, v, l in pos]
        ver = sum(p["nav"] for p in ps if p["verified"])
        unv = sum(p["nav"] for p in ps if not p["verified"])
        return {"date": date_, "positions": ps, "cash": cash, "unexplained": unexpl, "avoid": avoid, "watch": watch,
                "candidates": cands, "xung_dot": xung, "actions": [{"tk": "VCB", "tu": 8.0, "den": 5.0}],
                "src": src, "src_watch_avoid": "fft_cauhinh.json danh_muc (21/09/2026)",
                "tong_text": "%g%% verified" % ver + (" + %g%% UNVERIFIED" % unv if unv else ""),
                "tong_verified": ver, "tong_unverified": unv}
    a = book("2026-09-10", [("FPT", 12, True, None), ("VCB", 8, True, None), ("MSN", 8, True, None),
                            ("KSV", 3, False, None)], 15.0, 16.0, ["DGC", "STB"], ["VPB"], ["STB (đã trong watch)"],
             {"STB": "xung đột"}, "SKILL §6.1")
    b = book("2026-09-12", [("VCB", 10, True, "Core"), ("FPT", 12, True, "Core"), ("MSN", 5, True, "Core")], 16.0,
             None, ["STB"], [], [], {}, "hdcv SKILL")
    ns.portfolio_current = lambda: {"lk_khoi11_1009": a, "hdcv_1209": b, "conflicts": [
        {"loai": "chi_mot_ban", "tk": "KSV", "lk_khoi11": 3.0, "hdcv": None, "note": "UNVERIFIED"},
        {"loai": "nav", "tk": "MSN", "lk_khoi11": 8.0, "hdcv": 5.0},
        {"loai": "nav", "tk": "VCB", "lk_khoi11": 8.0, "hdcv": 10.0},
        {"loai": "cash", "tk": None, "lk_khoi11": 15.0, "hdcv": 16.0},
        {"loai": "watch_vs_avoid", "tk": "STB", "lk_khoi11": "watch", "hdcv": "AVOID"},
        {"loai": "avoid", "tk": "DGC", "lk_khoi11": "avoid", "hdcv": "—"}]}
    return ns


FAKE_DOSSIER = {"portfolio": {
    "p08": {"avoid": {"DGC": {"parts": [{"text": "BCTC 2025 đã nộp nhưng ngoại trừ.", "tier": "FACT-T1",
                                         "asof": "2026-08-26", "src": "x.pdf", "fact": "F4-046"}],
                              "tier": "FACT-T1", "asof": "2026-08-26", "src": "x.pdf"}},
            "rotation": {"status": "HẾT HẠN", "text": "cửa sổ 90 ngày đã hết", "tier": "EST", "asof": "2026-08-06",
                         "src": "spec"}},
    "p25": {"GEX": {"parts": [{"text": "C08: thủng 24K.", "tier": "FACT-T2", "asof": "2026-07-31", "src": "vc_lk",
                               "fact": "F4-002"}], "tier": "FACT-T2", "asof": "2026-07-31", "src": "vc_lk",
                    "status": "BỊ BÁC", "claim": "C08"},
            # trạng thái cũ lệch mảnh claims → builder phải lấy từ claims54 (một nguồn) và cảnh báo
            "VRE": {"parts": [{"text": "C34: xuống 21.300 ngày 28/07.", "tier": "FACT-T2", "asof": "2026-07-28",
                               "src": "vc_lk", "fact": "F1-060"}], "tier": "FACT-T2", "asof": "2026-07-28",
                    "src": "vc_lk", "status": "CHƯA RÕ", "claim": "C34", "claim_set": "claims54"}}},
    "claims54": {"C34": {"status": "BỊ BÁC", "tier": "FACT-T2", "asof": "2026-07-28", "src": "vc_lk"}},
    "claims20": {"C34": {"status": "LIVE", "tier": "FACT-T2", "asof": "2026-07-28", "src": "vc_lk"}}}


@unittest.skipIf(load_v21() is None, "thiếu v21_const.json")
class TestV21Portfolio(unittest.TestCase):
    """Mode v21: tái tạo nguyên văn (page_p6 §4)."""

    @classmethod
    def setUpClass(cls):
        cls.v21 = load_v21()
        with DOM.use_mode("v21", TODAY):
            ctx = make_ctx("v21", cls.v21)
            cls.res = P.build_portfolio(ctx)
            cls.warn = list(ctx.warnings)
        cls.root = cls.res["root"]
        cls.txt = text(cls.root)

    def test_structure_and_no_state(self):
        self.assertEqual(self.res["states"], [])
        self.assertEqual(self.warn, [])
        secs = [n for n in walk(self.root) if isinstance(n, dict) and n.get("t") == "section"]
        self.assertEqual([text(n.get("k")[0]) for n in secs][:1], ["Danh Mục Hiện Tại — VCB · FPT · MSNAs of 08/05/2026 · 3 positions"])
        titles = [text(n) for n in walk(self.root) if isinstance(n, dict) and n.get("t") == "h2"]
        self.assertEqual(titles, ["Danh Mục Hiện Tại — VCB · FPT · MSN", "Khuyến Nghị Mua Thêm — 4 Mã Tiềm Năng",
                                  "Danh Sách Tránh — Risk Off Danh Mục", "Lộ Trình Rotation — 90 Ngày Tới"])

    def test_golden_numbers(self):
        for s in ("TỔNG MV11.22 tỷ", "TỔNG VỐN GỐC11.85 tỷ", "P&L UNREALIZED-0.63 tỷ-5.3%", "POSITIONS3⚠ Concentration risk",
                  "84,400 cp", "+127tr+1.9%", "-83tr-2.7%", "-679tr-32.4%", "61.0%", "26.4%", "12.7%",
                  "GIÁ VỐN BQ79,500", "GIÁ HIỆN TẠI81,000", "MARKET VALUE6.84 tỷ",
                  "Tham chiếu cuối: 2026-05-07 · Giá 60,300 · Δ60d -16.0%",
                  "Δ60d +83.2% · SIG BULL · Tổ chức +52.8M · NN -33.7M",
                  "Δ60d +3.7% · SIG BULL · Tổ chức -97.8M · NN +168.6M",
                  "Δ60d -7.2% · SIG BULL · Tổ chức +69.5M · NN -54.8M"):
            self.assertIn(s, self.txt)

    def test_verbatim_text(self):
        for s in ("(consumer + MSR supercycle). Tình huống hiện tại: MSN ★ HOLD vững",
                  "(chưa euphoric), (2) Flow Pillar IV BULL (Tổ chức hoặc NN tích lũy mạnh ≥30M cp 60d), (3) Catalyst",
                  'Munger inversion: "Invert, always invert". Trước khi quyết định mua gì',
                  "HÀNH ĐỘNG · HOLD ENTIRE — V20 thesis intact", "LUẬN ĐIỂM · Tuấn mượt ascending",
                  "▸ TUẦN 1-3 · TRIM", "Bán FPT đợt 1: 5,000-6,000 cp (~25-30% position) khi nào hồi 75-78K",
                  "★ KEY MILESTONES THEO DÕI", "Tuấn mượt (GEX): Q2/2026 BCTC + tiến độ Gia Bình airport (target khởi "
                  "công 2027). Triển khai Eximbank board nomination tháng 6-7/2026."):
            self.assertIn(s, self.txt)

    def test_flowbar_cap_and_accents(self):
        fpt = by_key(self.root, "p08.pos.FPT")
        widths = [n["s"]["width"] for n in walk(fpt) if isinstance(n, dict) and "width" in (n.get("s") or {})
                  and str(n["s"]["width"]).endswith("%")]
        self.assertIn("50%", widths)                 # 173.7·0.3 = 52.11 → chặn trần 50
        self.assertIn("24.45%", widths)
        card = by_key(self.root, "p08.pos.MSN")["k"][0]
        self.assertEqual(card["s"]["borderLeft"], "3px solid " + DOM.C.forest)

    def test_no_live_marks(self):
        self.assertFalse(has_mark(self.root))
        for bad in ("V21·12/05", "↻", "CẦN DATA", "Hai Bản"):
            self.assertNotIn(bad, self.txt)


@unittest.skipIf(load_v21() is None, "thiếu v21_const.json")
class TestV21Portfolio25(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v21 = load_v21()
        with DOM.use_mode("v21", TODAY):
            cls.res = P.build_portfolio25(make_ctx("v21", cls.v21))
        cls.root = cls.res["root"]

    def test_state_options(self):
        self.assertEqual(self.res["states"], [{"key": "p25.cat", "default": "ALL",
                                               "options": ["ALL", "Core", "Growth", "Tactical", "Avoid"]}])
        exp = M.expected_options(self.v21)["p25.cat"]
        self.assertEqual(sorted(exp), sorted(self.res["states"][0]["options"]))
        self.assertEqual(M.EXPECTED_STATES["p25.cat"], ("portfolio25", "ALL", 5))

    def test_buttons(self):
        btns = [n for n in walk(self.root) if isinstance(n, dict) and n.get("t") == "button"]
        self.assertEqual([text(b) for b in btns], ["ALL", "Core", "Growth", "Tactical", "Avoid"])
        for b in btns:
            self.assertEqual(b["on"], {"set": {"p25.cat": text(b)}})
            self.assertEqual(b["s"]["fontFamily"], "inherit")          # as_intended (DESIGN §0.1)
        core = btns[1]
        self.assertEqual(core["s"]["border"], "1px solid " + DOM.C.emerald)
        self.assertEqual(btns[0]["var"][0]["s"]["background"], DOM.C.gold)

    def test_filter_counts(self):
        want = {"ALL": 25, "Core": 5, "Growth": 8, "Tactical": 2, "Avoid": 10}
        for cat, n in want.items():
            r = resolve(self.root, {"p25.cat": cat})
            rows = [x for x in walk(r) if isinstance(x, dict) and x.get("grp") == "p25.rows"]
            self.assertEqual(len(rows), n, cat)
            if cat != "ALL":
                self.assertTrue(all(text(x["k"][1]) == cat.upper() for x in rows))
        order = [text(x["k"][0]) for x in walk(resolve(self.root, {"p25.cat": "ALL"}))
                 if isinstance(x, dict) and x.get("grp") == "p25.rows"]
        self.assertEqual(order[:5], ["VCB", "FPT", "MSN", "HPG", "VHM"])     # giữ thứ tự dữ liệu, không sắp

    def test_golden_cells(self):
        t = text(self.root)
        for s in ("💼 ACTION PORTFOLIO · 25 mã color-coded (MD section 10)",
                  "Core 40% · Growth 30% · Tactical 15% · Avoid 0% · Cash 15%", "CORE5tickers", "GROWTH8tickers",
                  "TACTICAL2tickers", "AVOID10tickers", "CASH15%reserve", "TICKERCATACTIONTỶ TRỌNGENTRYNOTE",
                  "FPTCOREHOLD STRONG12%<90k pullbackAI-Nvidia · FCF +8,000 tỷ · SCIC 5.67% (C15)",
                  "DGCTACTICALWAIT Phase 35% chờ35-40k (P/B<1)Howard Marks 1:3 R/R · C02"):
            self.assertIn(s, t)
        vcb = by_key(self.root, "p25.row.VCB")
        self.assertEqual(vcb["s"]["background"], "#fbbf2408")          # amber + '08'
        fpt = by_key(self.root, "p25.row.FPT")
        self.assertEqual(fpt["s"]["background"], DOM.C.emerald + "08")  # as_intended

    def test_no_live_marks(self):
        self.assertFalse(has_mark(self.root))


@unittest.skipIf(load_v21() is None, "thiếu v21_const.json")
class TestLiveFake(unittest.TestCase):
    """Mode live với lớp dữ liệu giả: khối hai sổ, nhãn bậc, [CẦN DATA], dossier."""

    @classmethod
    def setUpClass(cls):
        cls.v21 = load_v21()
        with DOM.use_mode("live", TODAY):
            ctx = make_ctx("live", cls.v21, data=fake_data(), dossier=FAKE_DOSSIER)
            cls.p08 = P.build_portfolio(ctx)
            cls.p25 = P.build_portfolio25(ctx)
            cls.warn = list(ctx.warnings)

    def test_books_side_by_side(self):
        books = by_key(self.p08["root"], "p08.books")
        self.assertIsNotNone(books)
        t = text(books)
        kpi = text(by_key(books, "p08.books.kpi"))
        self.assertIn("28% verified", kpi)                  # giả: FPT 12 + VCB 8 + MSN 8
        self.assertIn(" + 3% UNVERIFIED", kpi)              # KSV tách riêng, không gộp thành 31%
        self.assertNotIn("31%", t)
        self.assertIn("không chọn bản", t)
        self.assertIn("8 vs 10", t)
        self.assertIn("8 vs 5", t)
        self.assertIn("chỉ Khối 11 · UNVERIFIED", t)
        self.assertIn("Khối 11 tự mâu thuẫn · HĐCV AVOID", t)    # STB: Khối 11 vừa watch vừa AVOID
        self.assertIn("15 vs 16", t)
        self.assertIn("Synthesis L1+L2+L3", t)
        self.assertIn("không lệnh nào đặt từ đây", t)
        self.assertNotIn("69%", t)
        # books là khối đầu tiên của tab (trước bản lưu V21)
        self.assertEqual(self.p08["root"]["k"][0].get("key"), "p08.books")

    def test_no_bare_numbers(self):
        for res in (self.p08, self.p25):
            self.assertEqual(uncovered_numbers(res["root"]), [])

    def test_v21_stance_kept_with_mark(self):
        t = text(self.p08["root"])
        self.assertIn("HOLD ENTIRE — V20 thesis intact, foreign FLIP first time in 4 yearsV21·12/05", t)
        self.assertIn("Value trap risk.V21·12/05", t)
        self.assertIn("HẾT HẠN", t)
        t25 = text(self.p25["root"])
        self.assertIn("ACTIONV21·12/05", t25)

    def test_flow_live_two_channels_only(self):
        fl = by_key(self.p08["root"], "p08.flow.live.MSN")
        t = text(fl)
        sig = fl["k"][0]                                    # FlowSignal (phần tử đầu), không tính dòng chú thích
        self.assertEqual(sum(1 for x in walk(sig) if isinstance(x, dict) and x.get("_can")), 3)  # CN, TC, SIG
        self.assertIn("phần dư", t)
        self.assertIn("-3.5M", t)

    def test_rights_adjusted_position(self):
        t = text(by_key(self.p08["root"], "p08.pos.live.FPT"))
        self.assertIn("21,340", t)                      # 19,400 × 1,10 (thưởng 10%; ESOP bị bỏ)
        self.assertIn("98,182", t)
        self.assertIn("CP 10% 21/09", t)
        self.assertNotIn("0.5%", t)

    def test_p25_live_columns_and_dossier(self):
        gex = by_key(self.p25["root"], "p25.row.GEX")
        self.assertEqual(len(gex["k"]), 10)
        t = text(gex)
        self.assertIn("24,000", t)
        self.assertIn("BỊ BÁC", t)
        self.assertIn("C08: thủng 24K.", t)
        fpt = text(by_key(self.p25["root"], "p25.row.FPT"))
        self.assertIn("entry ≈ <80.7K pullback", fpt)     # 90 × 0,8967
        self.assertEqual(self.p25["states"][0]["options"], ["ALL", "Core", "Growth", "Tactical", "Avoid"])

    def test_missing_ticker_is_can_data(self):
        t = text(by_key(self.p25["root"], "p25.row.LPB"))     # giả: không có giá LPB
        self.assertIn("[CẦN DATA", t)


@unittest.skipIf(load_v21() is None, "thiếu v21_const.json")
class TestFixes2709(unittest.TestCase):
    """Sửa sau kiểm chứng 27/09 (tab_report_portfolio.md, mục "Sửa sau kiểm chứng 27/09"; số phát hiện ghi ở từng test)."""

    @classmethod
    def setUpClass(cls):
        with DOM.use_mode("live", TODAY):
            ctx = make_ctx("live", load_v21(), data=fake_data(), dossier=FAKE_DOSSIER)
            cls.p08 = P.build_portfolio(ctx)
            cls.p25 = P.build_portfolio25(ctx)
            cls.warn = list(ctx.warnings)
        cls.t08, cls.t25 = text(cls.p08["root"]), text(cls.p25["root"])

    def test_td_tier_uses_last_prop_date_and_coverage(self):          # phát hiện 1
        msn = text(by_key(self.p08["root"], "p08.flow.live.MSN"))
        self.assertIn("Tự doanh-1.6MT2·24/09", msn)                    # không phải T2·25/09
        self.assertIn("Nước ngoài-3.5MT2·25/09", msn)
        gex = text(by_key(self.p08["root"], "p08.add.GEX"))
        self.assertIn("TD -1.6MT2·24/09 (41/60 phiên có bản ghi)", gex)

    def test_split_adjusted_volume(self):                                # phát hiện 3
        t = text(by_key(self.p08["root"], "p08.avoid.VIC,VHM,VRE"))
        self.assertIn("-10.0M (VIC -3.5 · VHM -3.0 · VRE -3.5)E·25/09", t)    # VHM: −1×2 + −1
        self.assertIn("KL quy về số cp hiện hành: ×2 trước CP 100% 06/08", t)
        fpt = text(by_key(self.p08["root"], "p08.flow.live.FPT"))
        self.assertIn("Nước ngoài-2.1ME·25/09", fpt)                   # −1×1,1 + −1, nhãn E (dẫn xuất)
        self.assertIn("Tự doanh-0.4ME·24/09", fpt)
        self.assertIn("×1.1 trước CP 10% 21/09", fpt)

    def test_events_filtered_by_exright_not_publication(self):         # phát hiện 6
        self.assertIn("sự kiện quyền: tiền 500 đ/cp 11/05 · CP 10% 25/05", text(by_key(self.p08["root"], "p08.add.HPG")))

    def test_claim_status_single_source(self):                         # phát hiện 2, 9, 15
        vre = text(by_key(self.p25["root"], "p25.row.VRE"))
        self.assertIn("BỊ BÁC C34", vre)
        self.assertNotIn("CHƯA RÕ", vre)
        self.assertTrue(any("claims54.C34" in w for w in self.warn))

    def test_raw_price_when_no_exright(self):                          # phát hiện 10
        self.assertIn("-10.0%", text(by_key(self.p25["root"], "p25.row.ACV")))   # 39.400/43.800 − 1, không phải −5,0

    def test_stb_internal_conflict_and_flag_count(self):               # phát hiện 7
        kpi = text(by_key(self.p08["root"], "p08.books.kpi"))
        self.assertIn("CỜ LỆCH GIỮA HAI SỔ7", kpi)
        self.assertIn("· chưa giải trình", kpi)
        row = text(by_key(self.p08["root"], "p08.books.row.STB"))
        self.assertIn("watch/AVOID", row)
        self.assertIn("KHỐI 11 TỰ MÂU THUẪN · STB", text(by_key(self.p08["root"], "p08.books.notes")))

    def test_nav_tier_reason(self):                                     # phát hiện 8
        self.assertIn("skill Khối 11 tự ghi FACT-T2", text(by_key(self.p08["root"], "p08.books")))

    def test_vjc_v21_clause_kept(self):                                 # phát hiện 13
        self.assertIn("NN distribution. Sovico Group đang giảm ownership theo Luật TCTDV21·12/05",
                      text(by_key(self.p08["root"], "p08.avoid.VJC")))

    def test_zone_label_not_new_recommendation(self):                  # phát hiện 16
        gex = text(by_key(self.p08["root"], "p08.add.GEX"))
        self.assertIn("vùng mua V21 quy đổi", gex)
        self.assertIn("ngưỡng V21, không phải khuyến nghị mới", gex)

    def test_no_machine_paths_no_inline_cong(self):                    # phát hiện 17, 18, 19b
        for t in (self.t08, self.t25):
            self.assertNotIn("/Users/", t)
            self.assertNotIn("CỔNG: [CẦN DATA — test]", t)
        self.assertIn("xem dòng CỔNG ở header", text(by_key(self.p25["root"], "p25.intro")))
        self.assertIn("xem dòng CỔNG ở header", text(by_key(self.p08["root"], "p08.books")))

    def test_short_src(self):
        import chaebol_map_tab_portfolio_live as L
        self.assertEqual(L._short_src("/Users/x/.claude/skills/langkinh-cautruc-codong/SKILL.md §6.1"),
                         "skill langkinh-cautruc-codong §6.1")
        self.assertEqual(L._short_src("/Users/x/a/b.json"), "~/a/b.json")

    def test_v21_flowbar_tier_no_date(self):                            # phát hiện 19a
        fpt = text(by_key(self.p08["root"], "p08.pos.FPT"))
        self.assertIn("Nước ngoài-173.7MT2Tham chiếu", fpt)             # nhãn không ngày → không tràn ô 80px
        self.assertIn("Giá 73,000T2·07/05", fpt)                        # ngày V21 ở dòng tham chiếu

    def test_no_bare_numbers(self):
        for res in (self.p08, self.p25):
            self.assertEqual(uncovered_numbers(res["root"]), [])


def _fragment():
    base = Path(os.environ.get("CHB_SYSTEM_DIR") or Path.home() / "SECOND BRAIN-OBSIDIAN/_System")
    f = base / "knowledge_os/chaebol_map/cap_nhat_2026-09-27.portfolio.json"
    return json.loads(f.read_text(encoding="utf-8"))["portfolio"] if f.is_file() else None


@unittest.skipIf(load_v21() is None, "thiếu v21_const.json")
class TestFinish2709(unittest.TestCase):
    """Vòng hoàn thiện 27/09 (final_check §6.1 #1, #10, #11; §6.2 #10) — tab_report_portfolio.md mục cùng tên."""

    @classmethod
    def setUpClass(cls):
        cls.frag = _fragment()
        dos = json.loads(json.dumps(FAKE_DOSSIER))
        if cls.frag:                       # mục thật của mảnh (DGC tab 08, NVL tab 13) dựng qua builder với dữ liệu giả
            dos["portfolio"]["p08"]["avoid"]["DGC"] = cls.frag["p08"]["avoid"]["DGC"]
            dos["portfolio"]["p25"]["NVL"] = cls.frag["p25"]["NVL"]
            dos["claims20"]["C07"] = {"status": "CHƯA RÕ", "tier": "FACT-T1", "asof": "2026-06-30", "src": "bctc"}
        data = fake_data()
        data.tv30 = lambda: ["MSN", "HPG", "BSR", "VCB", "FPT", "VIC", "VHM", "VRE", "VJC"]   # GEX, VCI, DGC ở ngoài
        with DOM.use_mode("live", TODAY):
            ctx = make_ctx("live", load_v21(), data=data, dossier=dos)
            cls.lv = __import__("chaebol_map_tab_portfolio_live").Live(ctx)
            cls.p08, cls.p25 = P.build_portfolio(ctx), P.build_portfolio25(ctx)
        with DOM.use_mode("v21", TODAY):
            cls.v08 = P.build_portfolio(make_ctx("v21", load_v21()))

    def test_pattern_q_outside_tv30(self):                              # §6.1 #1
        self.assertIn("BULL Pattern B? → MarkupV21·12/05", text(by_key(self.p08["root"], "p08.add.GEX")))
        self.assertIn("BULL Tổ chức +69.5M Pattern B?. Singapore", text(by_key(self.p08["root"], "p08.add.VCI")))
        self.assertIn("BULL Pattern B → Markup", text(self.v08["root"]))          # v21 giữ nguyên văn
        self.assertNotIn("Pattern B?", text(self.v08["root"]))
        self.assertEqual(self.lv.pattern_q("MSN", "Pattern B đáy"), "Pattern B đáy")        # trong 30 mã Toàn Vũ
        self.assertEqual(self.lv.pattern_q("GEX", "Pattern B?"), "Pattern B?")              # không thêm lần hai
        self.lv._c[("tv30", (), ())] = None                                                 # không đọc được danh sách
        self.assertEqual(self.lv.pattern_q("MSN", "Pattern A đỉnh"), "Pattern A? đỉnh")

    @unittest.skipIf(_fragment() is None, "mảnh dossier portfolio vắng")
    def test_dgc_restriction_split(self):                               # §6.1 #10
        parts = self.frag["p08"]["avoid"]["DGC"]["parts"]
        for p in parts:
            self.assertTrue(p.get("tier") and p.get("asof") and p.get("src"), p["text"])
        qd = [p for p in parts if "hạn chế giao dịch" in p["text"] and "19/05" in p["text"]]
        self.assertEqual([(p["tier"], p["asof"]) for p in qd], [("FACT-T2", "2026-05-20")])
        self.assertNotIn("26/05", qd[0]["text"])
        self.assertNotIn("448", qd[0]["text"])                  # số QĐ 448 chỉ có ở nguồn báo chí
        press = [p for p in parts if "26/05" in p["text"] or "448" in p["text"]]
        self.assertEqual([p["tier"] for p in press], ["UNVERIFIED"])
        self.assertIn("báo chí", press[0]["text"])
        t = text(by_key(self.p08["root"], "p08.avoid.DGC"))
        self.assertIn("Điều 2 được sửa bằng QĐ ngày 20/05.T2 Theo báo chí (chưa xác minh): QĐ sửa ngày 20/05 là QĐ 448, "
                      "hạn chế có hiệu lực từ 26/05", t)
        self.assertNotIn("19–20/05", t)

    @unittest.skipIf(_fragment() is None, "mảnh dossier portfolio vắng")
    def test_nvl_ocf_from_filings(self):                               # §6.1 #11
        e = self.frag["p25"]["NVL"]
        self.assertEqual((e["claim"], e["claim_set"]), ("C07", "claims20"))
        for p in e["parts"]:
            self.assertTrue(p.get("tier") and p.get("asof") and p.get("src"), p["text"])
            self.assertNotIn("CẦN DATA", p["text"])
            if "báo chí" in p["text"]:
                self.assertEqual(p["tier"], "UNVERIFIED")       # câu báo chí không bị nâng E
        t1 = [(p["asof"], p["text"]) for p in e["parts"] if p["tier"] == "FACT-T1"]
        self.assertEqual([a for a, _ in t1], ["2026-03-31", "2026-06-30"])
        self.assertIn("-436.5 tỷ", t1[0][1])
        self.assertIn("-3,611.7 tỷ", t1[1][1])
        t = text(by_key(self.p25["root"], "p25.row.NVL"))
        self.assertIn("CHƯA RÕ C07 (horizon hết 09/08): vế OCF không chạm", t)
        self.assertIn("-436.5 tỷ (BCTC Q1, mã 20),T1 6T/2026 -3,611.7 tỷ (BCTC soát xét).T1", t)
        self.assertIn("tài sản đã bán ~11,266 tỷU ≈ 0.43 tỷ USD", t)
        self.assertEqual(uncovered_numbers(self.p25["root"]), [])

    def test_live_split_under_800_lines(self):                          # §6.2 #10
        import chaebol_map_tab_portfolio_flow as F
        import chaebol_map_tab_portfolio_live as L
        for name in ("chaebol_map_tab_portfolio.py", "chaebol_map_tab_portfolio_live.py",
                     "chaebol_map_tab_portfolio_flow.py"):
            n = len((HERE / name).read_text(encoding="utf-8").splitlines())
            self.assertLessEqual(n, 800, name)
        self.assertTrue(issubclass(L.Live, F.FlowMixin))
        src = (HERE / "chaebol_map_tab_portfolio_flow.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"^\s*(from|import)\s+chaebol_map_tab_portfolio(_live)?\b", src, re.M))  # không nhập ngược


class TestChecker(unittest.TestCase):
    def test_checker_catches_bare_number(self):
        with DOM.use_mode("live", TODAY):
            bare = DOM.h("div", None, DOM.h("div", None, "giá 70,100"))
            ok = DOM.h("div", None, DOM.h("div", None, "giá 70,100", DOM.tier("T2", "2026-09-25")))
            date_only = DOM.h("div", None, "GIÁ 25/09")
        self.assertEqual(len(uncovered_numbers(bare)), 1)
        self.assertEqual(uncovered_numbers(ok), [])
        self.assertEqual(uncovered_numbers(date_only), [])


@unittest.skipIf(load_v21() is None, "thiếu v21_const.json")
class TestLiveDossierFallback(unittest.TestCase):
    def test_books_from_dossier_snapshot(self):
        data = fake_data()
        data.portfolio_current = lambda: {}
        dos = json.loads(json.dumps(FAKE_DOSSIER))
        dos["portfolio"].update({
            "lk_khoi11_1009": [{"tk": "FPT", "nav": 12.0, "verified": True, "tier": "EST", "asof": "2026-09-10", "src": "s"},
                               {"tk": "KSV", "nav": 3.0, "verified": False, "tier": "UNVERIFIED", "asof": "2026-09-10",
                                "src": "s"}],
            "hdcv_1209": [{"tk": "FPT", "nav": 12.0, "verified": True, "layer": "Core", "tier": "EST", "asof": "2026-09-12",
                           "src": "h"}],
            "conflicts": [{"loai": "chi_mot_ban", "tk": "KSV", "lk_khoi11": 3.0, "hdcv": None, "note": "UNVERIFIED",
                           "tier": "EST", "asof": "2026-09-21", "src": "x"}],
            "books_meta": {"lk_khoi11_1009": {"date": "2026-09-10", "cash": 15.0, "unexplained": 16.0, "tier": "EST",
                                              "asof": "2026-09-10", "src": "s", "tong_text": "12% verified + 3% UNVERIFIED"},
                           "hdcv_1209": {"date": "2026-09-12", "cash": 16.0, "tier": "EST", "asof": "2026-09-12",
                                         "src": "h", "tong_text": "12% verified"}}})
        with DOM.use_mode("live", TODAY):
            ctx = make_ctx("live", load_v21(), data=data, dossier=dos)
            r8 = P.build_portfolio(ctx)
        t = text(by_key(r8["root"], "p08.books"))
        self.assertIn("chỉ Khối 11 · UNVERIFIED", t)
        self.assertIn("3% UNVERIFIED", t)
        self.assertTrue(any("snapshot dossier" in w for w in ctx.warnings))
        self.assertEqual(uncovered_numbers(r8["root"]), [])


@unittest.skipIf(load_v21() is None, "thiếu v21_const.json")
class TestLiveNoData(unittest.TestCase):
    def test_builds_without_data_module(self):
        with DOM.use_mode("live", TODAY):
            ctx = make_ctx("live", load_v21(), data=None, dossier=None)
            r8, r25 = P.build_portfolio(ctx), P.build_portfolio25(ctx)
        self.assertIn("[CẦN DATA", text(r8["root"]))
        self.assertEqual(uncovered_numbers(r8["root"]), [])
        self.assertEqual(uncovered_numbers(r25["root"]), [])
        self.assertTrue(any("portfolio" in w for w in ctx.warnings))


def _real_store():
    base = Path(os.environ.get("CHB_SYSTEM_DIR") or Path.home() / "SECOND BRAIN-OBSIDIAN/_System")
    return (base / "fincept_bridge/state/vc_lk/MSN/price-history.json").is_file() and V21_PATH.is_file()


@unittest.skipUnless(_real_store(), "kho thật vắng")
class TestLiveRealStore(unittest.TestCase):
    def test_assemble_live(self):
        files, manifest, _ = M.assemble("live", TODAY, only={"portfolio", "portfolio25"})
        st = {t["id"]: t["status"] for t in manifest["tabs"]}
        self.assertEqual(st["portfolio"], "ok")
        self.assertEqual(st["portfolio25"], "ok")
        self.assertEqual(manifest["inventory"]["coverage"], {"missing": [], "mismatch": []})
        self.assertFalse([w for w in manifest["warnings"] if "builder lỗi" in w])
        t08 = json.loads(files["tab_portfolio.json"])
        s = json.dumps(t08, ensure_ascii=False)
        self.assertIn("66% verified", s)
        self.assertIn("3% UNVERIFIED", s)
        self.assertNotIn("69% NAV", s)
        with DOM.use_mode("live", TODAY):
            ctx = M.Ctx("live", TODAY, list(S.TABS_V21))
            ctx.v21, ctx.data = M.load_v21(ctx), M.load_data_module(ctx)
            ctx.dossier, ctx.live_info = M.load_dossier(ctx), M.live_numbers(ctx)
            r8, r25 = P.build_portfolio(ctx), P.build_portfolio25(ctx)
        self.assertEqual(uncovered_numbers(r8["root"]), [])
        self.assertEqual(uncovered_numbers(r25["root"]), [])


if __name__ == "__main__":
    unittest.main()
