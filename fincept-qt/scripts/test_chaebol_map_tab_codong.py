#!/usr/bin/env python3
"""Unit tests cho tab codong (chaebol_map_tab_codong + _live) — không mạng.

Chạy (cả hai trình thông dịch):
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest scripts/test_chaebol_map_tab_codong.py -v
    PYTHONDONTWRITEBYTECODE=1 ~/Library/Application\\ Support/com.fincept.terminal/venv-numpy2/bin/python \\
        -m unittest scripts/test_chaebol_map_tab_codong.py

Chuỗi vàng lấy từ chaebol_map_spec/page_p3a_codong_tab.md (ma trận 48 mã §4, S1–S11) — đã khớp ảnh ref Chrome.
Test v21 cần v21_const.json (skip nếu vắng). Test live đọc kho thật (chỉ đọc; skip nếu vắng). Khối Deep-dive
(agent khác) được thay bằng hàm giả để test chỉ khoá phần của tab codong; một test riêng kiểm điểm nối.
"""
from __future__ import annotations

import re
import socket
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import chaebol_map as M  # noqa: E402
import chaebol_map_dom as D  # noqa: E402
import chaebol_map_shell as S  # noqa: E402
import chaebol_map_tab_codong as T  # noqa: E402

V21_FILE = Path.home() / "SECOND BRAIN-OBSIDIAN/_System/fincept_bridge/data/chaebol_map/v21_const.json"
VC_DIR = Path.home() / "SECOND BRAIN-OBSIDIAN/_System/fincept_bridge/state/vc_lk"
NO_DEEP = ["VNM", "SAB", "VTP", "VGI", "GVR", "BVH", "BCM"]
SUB_IDS = ["phase_info", "chart", "phase", "cluster", "shareholder", "capitaliq", "flow", "strategic", "events",
           "patterns", "action"]
_REAL = {}


def setUpModule():
    def blocked(*a, **k):
        raise RuntimeError("mạng bị chặn trong test chaebol_map_tab_codong")
    for name in ("socket", "create_connection", "getaddrinfo"):
        _REAL[name] = getattr(socket, name)
        setattr(socket, name, blocked)


def tearDownModule():
    for name, fn in _REAL.items():
        setattr(socket, name, fn)


def walk(node, anc=()):
    yield node, anc
    if isinstance(node, dict):
        for ch in node.get("k", ()):
            yield from walk(ch, anc + (node,))


def text_of(node):
    return node if isinstance(node, str) else "".join(text_of(c) for c in node.get("k", ()))


def find_key(node, key):
    return next((n for n, _ in walk(node) if isinstance(n, dict) and n.get("key") == key), None)


def resolve_inc(node, inc):
    """Live v2 (codong_v2_spec §8.6): thay nút giữ chỗ {inc: khoá} bằng cây inc tương ứng (đệ quy, bỏ 'if') để đọc
    nội dung Deep-dive lồng theo sub-tab và khung chart."""
    if not isinstance(node, dict):
        return node
    kids = [resolve_inc(c, inc) for c in node.get("k", ())]
    if node.get("inc") in inc:
        kids.append(resolve_inc(inc[node["inc"]], inc))
    return {**{k: v for k, v in node.items() if k not in ("if", "inc")}, "k": kids}


def fake_deep(ctx, tk):
    """build_deep10 giả: thanh 11 sub-tab + một panel theo sub (scope codong.sub)."""
    D_ = T.V21(ctx.v21)
    return D.h("div", None, T.deep_bar(D_), *[D.h("div", None, "panel " + s, if_={T.K_SUB: s}, key="deep.p." + s)
                                              for s in SUB_IDS], scope=[T.K_SUB], key="deep.fake")


def make_ctx(mode, data=True):
    ctx = M.Ctx(mode, date(2026, 9, 27), list(S.TABS_V21))
    ctx.v21 = M.load_v21(ctx)
    if mode == "live":
        ctx.data = M.load_data_module(ctx) if data else None
        if ctx.data is not None and hasattr(ctx.data, "clear_cache"):
            ctx.data.clear_cache()
        ctx.dossier = M.load_dossier(ctx) if data else None
    ctx.tab = "codong"
    return ctx


_CACHE = {}


def build(mode, deep=fake_deep, data=True):
    key = (mode, deep, data)
    if key not in _CACHE:
        stub = lambda ctx: (deep, None if deep else "test")  # noqa: E731
        with D.use_mode(mode, "2026-09-27"), mock.patch.object(T, "load_deep", stub):
            ctx = make_ctx(mode, data)
            _CACHE[key] = (T.build_codong(ctx), ctx)
    return _CACHE[key]


@unittest.skipUnless(V21_FILE.is_file(), "chưa có v21_const.json")
class V21Structure(unittest.TestCase):
    def setUp(self):
        self.res, self.ctx = build("v21")

    def test_states_options(self):
        st = {s["key"]: s for s in self.res["states"]}
        self.assertEqual(st["codong.tk"]["default"], "VIC")
        self.assertEqual(st["codong.tk"]["options"], list(T.ALL_TICKERS))
        self.assertEqual(len(st["codong.tk"]["options"]), 48)
        self.assertEqual(st["codong.sub"]["default"], "phase_info")
        self.assertEqual(st["codong.sub"]["options"], SUB_IDS)
        norm = M.normalize_result("codong", self.res, self.ctx)
        cov = M._coverage(norm["states"], {"codong"}, self.ctx.v21)
        self.assertEqual(cov, {"missing": [], "mismatch": []})
        self.assertEqual(norm["root"]["scope"], ["codong.tk"])  # codong.sub có scope lồng ở nút Deep-dive (DESIGN §4)

    def test_root_is_48_lazy_placeholders(self):
        root = self.res["root"]
        kids = root["k"]
        self.assertEqual(len(kids), 48)
        for tk, k in zip(T.ALL_TICKERS, kids):
            self.assertEqual(k["inc"], "codong/" + tk)
            self.assertEqual(k["if"], {"codong.tk": tk})
        self.assertEqual(sorted(self.res["inc"]), sorted("codong/" + t for t in T.ALL_TICKERS))

    def test_no_live_markers_in_v21(self):
        for key, tree in self.res["inc"].items():
            _, st = D.finalize(tree)
            self.assertEqual((st["tiers"], st["can_data"], st["upd"], st["v21"]), ({}, 0, 0, 0), key)

    def test_deep_dive_visibility(self):
        for tk in T.ALL_TICKERS:
            has = find_key(self.res["inc"]["codong/" + tk], "codong.s3") is not None
            self.assertEqual(has, tk not in NO_DEEP, tk)

    def test_ticker_buttons(self):
        tree = self.res["inc"]["codong/VIC"]
        for tk in T.ALL_TICKERS:
            b = find_key(tree, "codong.btn." + tk)
            self.assertEqual(text_of(b), tk + (" ★" if tk in T.CIQ_TICKERS else ""))
            want = {"codong.tk": tk, "codong.sub": "phase_info"} if tk in NO_DEEP else {"codong.tk": tk}
            self.assertEqual(b["on"], {"set": want}, tk)
        on = find_key(tree, "codong.btn.VIC")["s"]
        self.assertEqual((on["background"], on["color"], on["fontWeight"]), ("#caa75c", "#0a0a0c", 700))
        off = find_key(tree, "codong.btn.STB")["s"]
        self.assertEqual((off["color"], off["border"]), ("#9a958a", "1px solid #1f1d24"))

    def test_golden_head_card(self):
        g = {"VIC": ("Vingroup JSC", "5927M", "~79.0% est"), "VHM": ("Vinhomes JSC", "3048M", "~74.2% est"),
             "MSN": ("Masan Group Corp.", "171M", "~11.9% est"),
             "MSR": ("Masan High-Tech Materials", "1M", "~0.1% est"),
             "NVL": ("Novaland Investment Group Corp.", "869M", "~86.9% est")}
        for tk, (name, top, pct) in g.items():
            card = text_of(find_key(self.res["inc"]["codong/" + tk], "codong.card"))
            for s in (name, "TOP 10 HOLDERS", top, pct):
                self.assertIn(s, card, tk)
        gex = text_of(find_key(self.res["inc"]["codong/GEX"], "codong.card"))
        for s in ("CTCP Tập đoàn GELEX", "NHÓM: Tuấn mượt", "SECTOR: Industrial Holding", "27.0K", "29/4/2026",
                  "39.3K", "04-08/05/2026"):
            self.assertIn(s, gex)
        self.assertNotIn("TOP 10", gex)
        self.assertEqual(text_of(find_key(self.res["inc"]["codong/VRE"], "codong.card")), "VREVRE")

    def test_ciq_table_and_tagholder(self):
        s4 = find_key(self.res["inc"]["codong/VIC"], "codong.s4")
        t = text_of(s4)
        for s in ("📊 Top 10 Holders — Capital IQ S&P Global (Q4/25 verified)", "2,520.27", "+486.93", "OTHER",
                  "INSIDER", "★ Reading:"):
            self.assertIn(s, t)
        for tk in T.ALL_TICKERS:
            self.assertEqual(find_key(self.res["inc"]["codong/" + tk], "codong.s4") is not None,
                             tk in T.CIQ_TICKERS, tk)

    def test_tag_holder_rules(self):
        cases = {"Vinspeed": "OTHER", "Vinenergo": "OTHER", "CBR Investment AG": "INST DOMESTIC",
                 "RWC Partners Ltd.": "INST DOMESTIC", "Viet Fund Management Company": "INST DOMESTIC",
                 "Vuong Nhat Pham / Chairman": "INSIDER", "Dragon Capital Management": "INST FOREIGN",
                 "SK Investment Vina I Pte. Ltd.": "STRATEGIC", "Vingroup JSC": "VEHICLE",
                 "Pham Thu Huong": "INDIVIDUAL", "": "unknown", "Xyz": "OTHER"}
        for name, tag in cases.items():
            self.assertEqual(T.tag_holder(name)[0], tag, name)

    def test_rec_color_quirks(self):
        self.assertEqual(T.rec_color("KHẢ QUAN"), "#9a958a")
        self.assertEqual(T.rec_color("KÉM KHẢ QUAN"), "#c5392f")
        self.assertEqual(T.rec_color("MUA"), "#3d7a4e")
        self.assertEqual(T.rec_color("TRUNG LẬP"), "#d4a039")
        self.assertEqual(T.rec_color("OUTPERFORM"), "#3d7a4e")

    def test_special_sections(self):
        inc = self.res["inc"]
        self.assertIn("MSN parent ~94.89% (~1,068M cp)", text_of(find_key(inc["codong/MSR"], "codong.s5")))
        self.assertIn("Bầu Thụy/Thaiholdings (>30%)", text_of(find_key(inc["codong/STB"], "codong.s6")))
        for tk in T.ALL_TICKERS:
            self.assertEqual(find_key(inc["codong/" + tk], "codong.s5") is not None, tk == "MSR")
            self.assertEqual(find_key(inc["codong/" + tk], "codong.s6") is not None, tk == "STB")
            self.assertEqual(find_key(inc["codong/" + tk], "codong.s7") is not None, tk in T.DETAIL_TICKERS, tk)
            self.assertEqual(find_key(inc["codong/" + tk], "codong.s7b") is not None, tk in ("GEX", "VCI"), tk)
        self.assertIn("📚 Chaebol Narrative — ⛔ Đào Hữu Huyền — đã bị khởi tố",
                      text_of(find_key(inc["codong/DGC"], "codong.s7")))

    def test_sellside_and_filings(self):
        inc = self.res["inc"]
        for tk in ("GEE", "GEL", "VIX", "SSB"):
            self.assertIn("⚠ Chưa có broker reports trên Simplize cho " + tk + " — chỉ có BCTN/NQ ĐHĐCĐ.",
                          text_of(find_key(inc["codong/" + tk], "codong.s9")))
        vic9 = text_of(find_key(inc["codong/VIC"], "codong.s9"))
        for s in ("reports tracked", "34.5K", "signal: NEUTRAL", "63,900", "Cập nhập từ Hội nghị NĐT 2025"):
            self.assertIn(s, vic9)
        self.assertIn("N/A", text_of(find_key(inc["codong/VPL"], "codong.s9")))
        s10 = find_key(inc["codong/VIC"], "codong.s10")
        dates = [text_of(td) for n, _ in walk(s10) if isinstance(n, dict) and n.get("t") == "tr"
                 for td in n.get("k", [])[:1] if isinstance(td, dict) and td.get("t") == "td"]
        self.assertEqual(dates, ["29/04/2026", "28/04/2026", "28/04/2026", "28/04/2026", "24/04/2026", "22/04/2026",
                                 "15/04/2026"])
        s11 = text_of(find_key(inc["codong/VIC"], "codong.s11"))
        for s in ("SOURCE MAP (3 nguồn)", "✗ 404", 'returns "***" cho non-subscriber',
                  "METHODOLOGY (cùng các tab khác)"):
            self.assertIn(s, s11)

    def test_click_state_machine(self):
        """Mô phỏng bấm: đổi mã giữ sub giữa hai mã có Deep-dive; qua mã NQ79 ẩn Deep-dive thì sub về phase_info."""
        inc, state = self.res["inc"], {"codong.tk": "VIC", "codong.sub": "phase_info"}

        def click(key):
            node = find_key(inc["codong/" + state["codong.tk"]], key)
            self.assertIsNotNone(node, key)
            state.update(node["on"]["set"])

        click("codong.sub.cluster")
        click("codong.btn.GEX")
        self.assertEqual(state, {"codong.tk": "GEX", "codong.sub": "cluster"})
        click("codong.btn.VNM")
        self.assertEqual(state, {"codong.tk": "VNM", "codong.sub": "phase_info"})
        click("codong.btn.MSN")
        click("codong.sub.action")
        click("codong.btn.STB")
        self.assertEqual(state, {"codong.tk": "STB", "codong.sub": "action"})


@unittest.skipUnless(V21_FILE.is_file(), "chưa có v21_const.json")
class DeepJunction(unittest.TestCase):
    def _run(self, fn):
        with D.use_mode("v21", "2026-09-27"), mock.patch.object(T, "load_deep", lambda ctx: (fn, None)):
            ctx = make_ctx("v21")
            return T.build_codong(ctx), ctx

    def test_section_used_as_is(self):
        sec = lambda ctx, tk: S.Section("X " + tk, D.h("div", None, "b"), scope=[T.K_SUB], key="deep10_" + tk)  # noqa
        res, _ = self._run(sec)
        tree = res["inc"]["codong/VIC"]
        self.assertIsNotNone(find_key(tree, "deep10_VIC"))
        self.assertIsNone(find_key(tree, "codong.s3"))

    def test_div_wrapped_and_error_placeholder(self):
        res, _ = self._run(lambda ctx, tk: D.h("div", None, "x", key="d"))
        s3 = find_key(res["inc"]["codong/GEX"], "codong.s3")
        self.assertIn("🔬 DEEP-DIVE 10 SUB-TABS — GEX (equivalent v22 MSN tab structure)", text_of(s3))

        def boom(ctx, tk):
            raise KeyError("x")
        res, ctx = self._run(boom)
        ph = find_key(res["inc"]["codong/GEX"], "codong.deep.placeholder")
        self.assertEqual(ph["scope"], [T.K_SUB])
        self.assertIsNotNone(find_key(ph, "codong.sub.action"))
        self.assertTrue(any("build_deep10 lỗi" in w for w in ctx.warnings))


# ── live ────────────────────────────────────────────────────────────────────

NUM_RE = re.compile(r"\d+(?:\.\d+)?%|\d+\.\dK\b|\d{1,3}(?:,\d{3})+|\b\d+\.\d+\b")
MARK_RE = re.compile(r"^(T1|T2|T3|E|U)(·\d\d/\d\d(?:/\d\d)?)?$|^↻\d\d/\d\d$|^V21·12/05$|^\[CẦN DATA")


def is_mark(n):
    return isinstance(n, dict) and n.get("t") == "span" and MARK_RE.match(text_of(n) or "") is not None


def has_mark(node):
    return any(is_mark(n) for n, _ in walk(node))


def bare_numbers(tree):
    """Chữ có số (%, K, nghìn có dấu phẩy, thập phân) mà hàng/đoạn chứa nó không có nhãn bậc/[CẦN DATA]/↻/V21.
    Phạm vi: tr/li/p gần nhất, ngược lại phần tử cha (lên tối đa 2 cấp). Bỏ nhánh lưu trữ V21 (key codong.arch.*)."""
    bad = []
    for n, anc in walk(tree):
        if not isinstance(n, str) or not NUM_RE.search(n):
            continue
        if any(isinstance(a, dict) and str(a.get("key", "")).startswith("codong.arch.") for a in anc):
            continue
        scope = next((a for a in reversed(anc) if a.get("t") in ("tr", "li", "p")), None)
        scopes = [scope] if scope is not None else list(reversed(anc))[:3]
        if not any(has_mark(s) for s in scopes):
            bad.append(n[:80])
    return bad


LIVE_OK = VC_DIR.is_dir() and V21_FILE.is_file()


@unittest.skipUnless(LIVE_OK, "kho vc_lk/v21_const vắng — bỏ test live")
class Live(unittest.TestCase):
    def setUp(self):
        self.res, self.ctx = build("live")
        self.inc = self.res["inc"]

    def txt(self, tk, key):
        n = find_key(self.inc["codong/" + tk], key)
        return text_of(n) if n else ""

    def test_builds_all_109(self):
        order = __import__("chaebol_map_data_codong2").universe_groups(self.ctx.v21)["order"]
        self.assertEqual(len([k for k in self.inc if re.fullmatch(r"codong/[A-Z0-9]+", k)]), len(order))
        self.assertFalse([w for w in self.ctx.warnings if "lỗi" in w and "Deep" not in w], self.ctx.warnings)

    def test_no_bare_numbers(self):
        for tk in T.ALL_TICKERS:
            self.assertEqual(bare_numbers(self.inc["codong/" + tk]), [], tk)

    def test_stats_labelled(self):
        for tk in ("VIC", "GEX", "MSN", "VNM", "GEE"):
            card = find_key(self.inc["codong/" + tk], "codong.card")
            vals = [n for n, _ in walk(card) if isinstance(n, dict) and (n.get("s") or {}).get("fontFamily") == D.F_NUM]
            self.assertTrue(vals, tk)
            for v in vals:
                self.assertTrue(has_mark(v), (tk, text_of(v)))

    def test_lens_and_rules(self):
        gex = self.txt("GEX", "codong.lens")
        self.assertIn("?", gex.split("PATTERN")[1].split("CỔ ĐÔNG")[0])            # ngoài TV30 → "?"
        self.assertIn("[CẦN DATA — ngoài 30 mã Toàn Vũ", gex)
        self.assertIn("[CẦN DATA — sau 08/05 chỉ NN + TD có số thật]", gex)
        self.assertIn("toàn dải", gex)
        self.assertIn("CỔNG:", gex)
        vic = self.txt("VIC", "codong.lens")
        self.assertIn("mốc cuối: chưa có số mới (CF, kỳ 07/2026", vic)
        self.assertIn("Synthesis L1+L2+L3", self.txt("MSN", "codong.lens"))

    # ── sửa sau kiểm chứng 27/09 ──

    def test_lens_toan_vu_and_vi_labels(self):
        """Quan sát cuối = mốc cf=False + kieu quan_sat (VHM/HDB có CF gắn kieu quan_sat); mốc CF không hiện số;
        không còn mã máy snake_case trên dòng lăng kính."""
        vhm, hdb = self.txt("VHM", "codong.lens"), self.txt("HDB", "codong.lens")
        self.assertIn("quan sát cuối 24,711 (06/2025)", vhm)
        self.assertIn("quan sát cuối 38,334 (03/2026)", hdb)
        self.assertNotIn("(2026-07", vhm)
        self.assertIn("quan sát cuối 32,157 (10/2024)", self.txt("MSN", "codong.lens"))
        raw = re.compile(r"\b(tren_cum|kep_sau|kep_nong|thoat_6t|quan_sat|noi_suy|so_tron|chua_ro|het_hieu_luc|"
                         r"dang_hinh_thanh|xac_nhan)\b|\(\d{4}-\d{2}[,)]")
        for tk in T.ALL_TICKERS:
            self.assertIsNone(raw.search(self.txt(tk, "codong.lens")), tk)

    def test_nav_two_books_and_conflicts(self):
        msn = self.txt("MSN", "codong.lens")
        for s in ("Khối 11 (10/09) 8%", "HĐCV (12/09) 5%", "⚑ lệch 8 vs 5", ">5% NAV → Synthesis L1+L2+L3"):
            self.assertIn(s, msn)
        self.assertNotIn("sổ Khối 11)", msn)
        self.assertIn("chạm 5% NAV → Synthesis", self.txt("HPG", "codong.lens"))
        self.assertIn("⚑ xung đột sổ: Khối 11 watch vs HĐCV AVOID", self.txt("STB", "codong.lens"))
        self.assertIn("⚑ xung đột sổ: Khối 11 avoid vs HĐCV không có trong AVOID", self.txt("DGC", "codong.lens"))

    def test_flow_td_coverage_and_units(self):
        dgc, vic = self.txt("DGC", "codong.lens"), self.txt("VIC", "codong.lens")
        self.assertIn("tự doanh khớp [CẦN DATA — 15/60 phiên có bản ghi tự doanh", dgc)
        self.assertNotIn("phần dư", dgc)
        self.assertIn("(59/60 phiên)", vic)
        self.assertIn("T2·24/09", vic)
        self.assertIn("M cp", vic)
        self.assertIn("NN tới 25/09, TD tới 24/09", vic)

    def test_top10_adjusted_and_asof(self):
        vjc = self.txt("VJC", "codong.card")
        m = re.search(r"~(\d+\.\d)% cp hiện hành", vjc)
        self.assertTrue(m and 55 < float(m.group(1)) < 61, vjc)          # quy đổi 30% CP 16/06 (thô 46.3%)
        self.assertIn("công bố 12/01/17→30/06/26", vjc)
        self.assertIn("⚑ nguồn lệch", self.txt("GAS", "codong.card"))
        s4 = self.txt("VIC", "codong.s4")
        self.assertIn("công bố tới 30/06/2026 · vendor cập nhật 10/09", s4)
        self.assertNotIn("dữ liệu tới 10/09", s4)
        self.assertIn("công bố tới 30/06/2026", self.txt("VIC", "codong.s1"))

    def test_cafef_basis(self):
        gex = self.txt("GEX", "codong.card")
        for s in ("39.3K", "V21·12/05", "đóng cửa thô 04/05 — trước GDKHQ 05/05", "27.1K"):
            self.assertIn(s, gex)
        self.assertNotIn("T2·08/05", gex)
        self.assertIn("98.6K", self.txt("GEE", "codong.card"))

    def test_structure_subsidiary_sellside_news(self):
        fpt = self.txt("FPT", "codong.structure")
        self.assertIn("⚑ vendor lệch mẫu số", fpt)
        self.assertIn("Nhà nước 5.12%", fpt)
        s7b = self.txt("GEX", "codong.s7b")
        self.assertIn("vendor ghi 0% / 0 cp", s7b)
        self.assertIsNone(re.search(r"(?<![\d.])0\.00%", s7b))
        s9 = self.txt("MSN", "codong.s9")
        self.assertIn("1 nguồn tổng hợp (CapIQ n=11)", s9)
        self.assertNotIn("không phải đồng thuận", s9)
        self.assertEqual(self.txt("MSN", "codong.s10").count("Nghị quyết Chủ sở hữu trái phiếu số 01"), 1)

    def test_pattern_suffix_outside_tv30(self):
        gex = text_of(resolve_inc(self.inc["codong/GEX"], self.inc))
        self.assertIsNone(re.search(r"Pattern [A-D](?!\?)", gex.replace(T.READING_S9[4], "")
                                    .replace(__import__("chaebol_map_tab_codong_deep").TV_READING, "")))
        self.assertIn("Pattern B? đáy", self.txt("GEX", "codong.s7"))
        self.assertIn(T.READING_S9[4], self.txt("GEX", "codong.s9"))          # câu phương pháp chung: giữ nguyên
        vic = text_of(resolve_inc(self.inc["codong/VIC"], self.inc))
        self.assertNotIn("Pattern A?", vic)                                  # VIC trong 30 mã Toàn Vũ

    def test_decisive_pills_need_non_u_evidence(self):
        st_re = re.compile(r"^(ĐẠT|BỊ BÁC|TIỀN ĐỀ SAI)$")
        for tk in T.ALL_TICKERS:
            for n, anc in walk(self.inc["codong/" + tk]):
                if not (isinstance(n, dict) and n.get("t") == "span" and st_re.match(text_of(n))):
                    continue
                blk = next(a for a in reversed(anc) if a.get("t") in ("li", "tr", "div", "p"))
                tiers = [text_of(x).split("·")[0] for x, _ in walk(blk) if is_mark(x) and
                         re.match(r"^(T1|T2|T3|E|U)", text_of(x))]
                self.assertTrue(any(t != "U" for t in tiers), (tk, text_of(blk)[:80]))

    def test_legal_political_caveats_and_inline_can_data(self):
        self.assertIn("mệnh đề chính trị nêu tên cá nhân", self.txt("VCI", "codong.s7"))
        for tk in T.ALL_TICKERS:
            for n, anc in walk(self.inc["codong/" + tk]):
                if isinstance(n, str) and "[CẦN DATA" in n and not n.startswith("[CẦN DATA"):
                    key = next((a.get("key") for a in reversed(anc) if a.get("key")), "")
                    self.assertFalse(key.startswith(("codong.fact.", "codong.s2")), (tk, key, n[:60]))

    def test_dossier_rewrites_and_claims(self):
        self.assertIn("92.89%", self.txt("MSR", "codong.s5"))
        self.assertIn("≈87.46%", self.txt("MSR", "codong.s5"))
        stb = self.txt("STB", "codong.s6")
        self.assertIn("BỊ BÁC", stb)
        self.assertIn("V21·12/05", stb)
        self.assertIn("UBND TP. Hồ Chí Minh 95.44%", self.txt("BCM", "codong.s2"))
        self.assertIn("Nguyễn Văn Hùng", self.txt("BCM", "codong.card"))
        self.assertIn("room còn ≈839M cp", self.txt("VCB", "codong.s2"))
        self.assertIn("QĐ 40/2026", self.txt("PLX", "codong.s2"))
        self.assertIn("Quyết định 40/2026/QĐ-TTg", self.txt("GVR", "codong.policy"))

    def test_stance_kept_with_v21_mark(self):
        s2 = self.txt("VIC", "codong.s2")
        for s in ("★ FLAGSHIP", "NQ 68 + HSR + RE 2.6GW + giải cứu VinFast", "Net debt 256K tỷ + VFS burn $570M/quý",
                  "KHÔNG mua vì khẩu hiệu NQ 68/NQ 79", "V21·12/05"):
            self.assertIn(s, s2)
        dgc = self.txt("DGC", "codong.s7")
        self.assertIn("pháp lý nêu tên cá nhân", dgc)
        self.assertIn("UNVERIFIED", dgc)

    def test_holders_table_live(self):
        s4 = self.txt("VIC", "codong.s4")
        self.assertIn("Vietcap IQ", s4)
        self.assertIn("32.47%", s4)
        self.assertIn("Phạm Nhật Vượng", s4)
        self.assertNotIn("Capital IQ S&P Global (Q4/25 verified)", s4)
        for s in ("CƠ CẤU SỞ HỮU", "Nhà nước", "room NN tối đa", "M cp"):
            self.assertIn(s, s4)

    def test_no_new_buy_sell_calls(self):
        for tk in T.ALL_TICKERS:
            t = text_of(self.inc["codong/" + tk])
            for bad in ("STRONG BUY", "KHUYẾN NGHỊ MUA", "nên mua", "nên bán"):
                self.assertNotIn(bad, t, tk)

    # ── vòng hoàn thiện 27/09 (final_check §6.1 #2 #3 #4) ──

    def test_no_signed_zero(self):
        """#2: số của lớp live làm tròn bằng 0 in '0.0' không dấu (SAB tự doanh khớp, VGI NN, VPL)."""
        rx = re.compile(r"(?<![\d.,])[-+−]0[.,]0+(?!\d)")
        for tk in T.ALL_TICKERS:
            self.assertIsNone(rx.search(text_of(self.inc["codong/" + tk])), tk)

    def test_new_strings_vietnamese_dates(self):
        """#3 + DESIGN §11.3: dòng CỔNG mã ghi 'tính đến dd/mm/yyyy hh:mm'; giờ dựng lk_hoso (S11) không còn ISO."""
        for tk in T.ALL_TICKERS:
            self.assertNotIn("as of", text_of(self.inc["codong/" + tk]), tk)
            self.assertRegex(self.txt(tk, "codong.lens"), r" · tính đến (\d\d/\d\d/\d{4} \d\d:\d\d|\[CẦN DATA)", tk)
            self.assertNotRegex(self.txt(tk, "codong.s11"), r"dựng \d{4}-", tk)

    def test_s10_capital_events_by_public_date(self):
        """S10 là danh sách CBTT từ 09/05: sự kiện vốn lọc theo ngày công bố (lõi đổi mặc định sang GDKHQ 27/09 làm
        cổ tức HPG/LPB/SAB công bố 05–08/05 hiện với ngày trước mốc, và rơi AIS BID/NVL công bố 13–14/05)."""
        for tk in ("HPG", "LPB", "SAB", "BID", "NVL"):
            for n, _ in walk(find_key(self.inc["codong/" + tk], "codong.s10")):
                if isinstance(n, dict) and n.get("t") == "tr":
                    t = text_of(n)
                    if "bản lưu vietstock" in t:
                        break
                    m = re.match(r"(\d\d)/(\d\d)/(\d{4})", t)
                    if m:
                        self.assertGreaterEqual(m.group(3) + m.group(2) + m.group(1), "20260509", (tk, t[:60]))

    def test_can_data_never_breaks(self):
        """#4: mọi '[CẦN DATA' của tab (kể cả dòng CỔNG chép từ lk_hoso) nằm trong phần tử whiteSpace nowrap."""
        for tk in T.ALL_TICKERS:
            for n, anc in walk(self.inc["codong/" + tk]):
                if isinstance(n, str) and "[CẦN DATA" in n:
                    self.assertTrue(any((a.get("s") or {}).get("whiteSpace") == "nowrap" for a in anc), (tk, n[:60]))


@unittest.skipUnless(V21_FILE.is_file(), "chưa có v21_const.json")
class LiveWithoutData(unittest.TestCase):
    def test_everything_can_data(self):
        res, ctx = build("live", data=False)
        tree = res["inc"]["codong/GEX"]
        t = text_of(tree)
        self.assertIn("[CẦN DATA", t)
        self.assertEqual(bare_numbers(tree), [])


if __name__ == "__main__":
    unittest.main()
