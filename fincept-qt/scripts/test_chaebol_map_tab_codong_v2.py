#!/usr/bin/env python3
"""Unit tests cho tab codong v2 (P4 render): chaebol_map_tab_codong_v2 + _parts + _book. Spec codong_v2_spec.md §7, §11.4.

Chạy (cả hai trình thông dịch):
    python3.14 -m pytest -q scripts/test_chaebol_map_tab_codong_v2.py
    ~/Library/Application\\ Support/com.fincept.terminal/venv-numpy2/bin/python -m pytest -q \\
        scripts/test_chaebol_map_tab_codong_v2.py

Lớp Pure không cần kho. Lớp Live/Off dựng CẢ tab một lần trên kho thật (chỉ đọc, CHB_TODAY=2026-10-05) với ctx.data thật
và với ctx.data = None; bỏ qua khi thiếu vc_lk/v21_const. Mạng bị chặn trong cả tệp.
"""
from __future__ import annotations

import ast
import os
import re
import socket
import sys
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("CHB_TODAY", "2026-10-05")

import chaebol_map as M  # noqa: E402
import chaebol_map_dom as D  # noqa: E402
import chaebol_map_shell as S  # noqa: E402
import chaebol_map_tab_codong_v2 as V2  # noqa: E402
import chaebol_map_tab_codong_v2_book as BK  # noqa: E402
import chaebol_map_tab_codong_v2_parts as PT  # noqa: E402
from chaebol_map_data_nen import V  # noqa: E402

SYS = Path(os.environ.get("CHB_SYSTEM_DIR", str(Path.home() / "SECOND BRAIN-OBSIDIAN" / "_System")))
V21_FILE = SYS / "fincept_bridge" / "data" / "chaebol_map" / "v21_const.json"
VC_DIR = SYS / "fincept_bridge" / "state" / "vc_lk"
LIVE_OK = (VC_DIR / "VIC" / "price-history.json").is_file() and V21_FILE.is_file()
SUB_IDS = ["phase_info", "chart", "phase", "cluster", "shareholder", "capitaliq", "flow", "strategic", "events",
           "patterns", "action"]
EM, EN = chr(0x2014), chr(0x2013)
NUM_RE = re.compile(r"\d+(?:\.\d+)?%|\d+\.\dK\b|\d{1,3}(?:,\d{3})+|\b\d+\.\d+\b")
MARK_RE = re.compile(r"^(T1|T2|T3|E|U)(·\d\d/\d\d(?:/\d\d)?)?$|^↻\d\d/\d\d$|^V21·12/05$|^\[CẦN DATA")
BAN_RE = re.compile(r"(?<![A-Za-z])(?:BUY|SELL|TRIM|ADD|DCA)(?![A-Za-z])|%NAV|khuyến nghị mua|khuyến nghị bán|nên mua"
                    r"|nên bán", re.I)
VN_NUM = re.compile(r"\d{1,3}(\.\d{3})+,\d")
SRC_BAN = re.compile(r"\b(BUY|SELL|TRIM|ADD|DCA)\b|%NAV|(?i:khuyến nghị mua|khuyến nghị bán|nên mua|nên bán)")
FILES = ("chaebol_map_tab_codong_v2.py", "chaebol_map_tab_codong_v2_parts.py", "chaebol_map_tab_codong_v2_book.py")
_REAL = {}


def setUpModule():
    def blocked(*a, **k):
        raise RuntimeError("mạng bị chặn trong test chaebol_map_tab_codong_v2")
    for name in ("socket", "create_connection", "getaddrinfo"):
        _REAL[name] = getattr(socket, name)
        setattr(socket, name, blocked)


def tearDownModule():
    for name, fn in _REAL.items():
        setattr(socket, name, fn)


# ── duyệt cây ───────────────────────────────────────────────────────────────


def walk(node, anc=()):
    yield node, anc
    if isinstance(node, dict):
        for ch in node.get("k", ()):
            yield from walk(ch, anc + (node,))


def text_of(node):
    return node if isinstance(node, str) else "".join(text_of(c) for c in node.get("k", ()))


def keyed(node, pred):
    return [n for n, _ in walk(node) if isinstance(n, dict) and pred(str(n.get("key", "")))]


def find_key(node, key):
    return next(iter(keyed(node, lambda k: k == key)), None)


def is_mark(n):
    return isinstance(n, dict) and n.get("t") == "span" and MARK_RE.match(text_of(n) or "") is not None


def has_mark(node):
    return any(is_mark(n) for n, _ in walk(node))


def new_parts(node):
    """Cây con khối MỚI (key cd2.*), bỏ: panel V21 (deep10_*), SVG (cd2.svg*), trích nguyên văn (cd2.trich.*)."""
    def keep(n):
        k = str(n.get("key", "")) if isinstance(n, dict) else ""
        return not (k.startswith("deep10_") or k.startswith("cd2.svg") or k.startswith("cd2.trich."))

    def prune(n):
        if not isinstance(n, dict):
            return n
        return {**n, "k": [prune(c) for c in n.get("k", ()) if keep(c)]}
    roots = keyed(node, lambda k: k.startswith("cd2.") and not k.startswith("cd2.svg") and not k.startswith("cd2.trich."))
    out, seen = [], set()
    for r in roots:                                   # chỉ gốc ngoài cùng (bỏ cd2.* lồng trong cd2.* khác)
        if id(r) not in seen:
            out.append(prune(r))
            seen.update(id(x) for x, _ in walk(r) if isinstance(x, dict))
    return out


def bare_numbers(tree):
    """Như helper test cũ: chữ có số mà hàng/đoạn chứa nó (tr/li/p gần nhất, không có thì ≤3 cấp cha) không có nhãn."""
    bad = []
    for n, anc in walk(tree):
        if not isinstance(n, str) or not NUM_RE.search(n):
            continue
        scope = next((a for a in reversed(anc) if a.get("t") in ("tr", "li", "p")), None)
        scopes = [scope] if scope is not None else list(reversed(anc))[:3]
        if not any(has_mark(s) for s in scopes):
            bad.append(n[:80])
    return bad


def plain_texts(tree):
    """Chữ không nằm trong nút can_data (token [CẦN DATA, lý do] được miễn ký tự gạch)."""
    out = []
    for n, anc in walk(tree):
        if isinstance(n, str) and not any(isinstance(a, dict) and a.get("_can") for a in anc):
            out.append(n)
    return out


def resolve(node, inc, state):
    """Thay nút inc bằng cây inc (đệ quy), bỏ nhánh có if không khớp state."""
    if isinstance(node, str):
        return node
    cond = node.get("if") or {}
    for k, v in cond.items():
        if (state.get(k) not in v) if isinstance(v, list) else state.get(k) != v:
            return None
    if node.get("inc"):
        sub = inc.get(node["inc"])
        return resolve(sub, inc, state) if sub is not None else None
    kids = [resolve(c, inc, state) for c in node.get("k", ())]
    return {**node, "k": [c for c in kids if c is not None]}


# ── dựng (một lần mỗi chế độ) ───────────────────────────────────────────────

_CACHE = {}


def make_ctx(data=True):
    ctx = M.Ctx("live", date(2026, 10, 5), list(S.TABS_V21))
    ctx.v21 = M.load_v21(ctx)
    ctx.data = M.load_data_module(ctx) if data else None
    if ctx.data is not None and hasattr(ctx.data, "clear_cache"):
        ctx.data.clear_cache()
    ctx.dossier = M.load_dossier(ctx) if data else None
    ctx.live_info = M.live_numbers(ctx) if data else {}
    ctx.tab = "codong"
    return ctx


def build(data=True):
    if data not in _CACHE:
        with D.use_mode("live", "2026-10-05"):
            ctx = make_ctx(data)
            res = V2.build_codong_v2(ctx)
            _CACHE[data] = (res, ctx, M.normalize_result("codong", res, ctx))
    return _CACHE[data]


# ── không cần kho ───────────────────────────────────────────────────────────


class Pure(unittest.TestCase):
    def setUp(self):
        self._m = D.use_mode("live", "2026-10-05")
        self._m.__enter__()

    def tearDown(self):
        self._m.__exit__(None, None, None)

    def test_formatters_en_us(self):
        self.assertEqual(PT.fp(1007.514), "1,007.51%")
        self.assertEqual(PT.fps(-0.004), "0.00%")
        self.assertEqual(PT.fps(4.0226), "+4.02%")
        self.assertEqual(PT.fm(105221001.0), "105.22M")
        self.assertEqual(PT.fm(-105221001.0, True), "-105.22M")
        self.assertEqual(PT.fm(850500), "850.5K")
        self.assertEqual(PT.fb(-1470657214500.0, True), "-1,471 tỷ")
        self.assertEqual(PT.fb(33381160000.0, True), "+33.4 tỷ")
        self.assertEqual(PT.fk(224000.0), "224.0K")
        self.assertEqual(PT.fpp(-0.004), "0.00 điểm %")
        self.assertEqual(PT.dmy("2007-09-17"), "17/09/2007")
        self.assertEqual(PT.dmy_hm("2026-10-05 20:54"), "05/10/2026 20:54")

    def test_tv_cv_one_tier(self):
        v = V(32.468, "32.47%", "FACT-T2", "2026-09-28", "x")
        self.assertEqual(text_of(D.h("span", None, *PT.tv(v, PT.fp))), "32.47%T2·28/09")
        self.assertEqual(PT.cv(v, "FACT-T2", PT.fp), ["32.47%"])
        cell = PT.cv(V(1.0, "1", "EST", "2026-09-28"), "FACT-T2")
        self.assertEqual(text_of(D.h("span", None, *cell)), "1E·28/09")
        miss = PT.tv(V(None, "[CẦN DATA]", None, None, None, "chưa nạp vc_lk"))
        self.assertEqual(text_of(miss[0]), "[CẦN DATA " + EM + " chưa nạp vc_lk]")
        self.assertTrue(miss[0].get("_can"))
        self.assertEqual(text_of(PT.cdn({"ok": False, "why": "[CẦN DATA] lý do"})), "[CẦN DATA " + EM + " lý do]")

    def test_q_wraps_verbatim_only_when_needed(self):
        self.assertEqual(PT.q("Công ty Cổ phần Vinpearl"), "Công ty Cổ phần Vinpearl")
        for s_ in ("HOLD / TRIM PARTIAL", "a " + EM + " b", "3.329,3 triệu", "Vietcap SELL"):
            n = PT.q(s_)
            self.assertEqual(n["key"], "cd2.trich.q", s_)
            self.assertEqual(text_of(n), s_)
        self.assertEqual(PT.trich("x", "a")["key"], "cd2.trich.x")
        self.assertTrue(PT.trim("x" * 300, 50).endswith("…"))

    def test_period_bounds(self):
        self.assertEqual(PT.period_bounds("2023"), ("2023-01-01", "2023-12-31"))
        self.assertEqual(PT.period_bounds("Q2/2026"), ("2026-04-01", "2026-06-30"))
        self.assertEqual(PT.period_bounds("Q4/25"), ("2025-10-01", "2025-12-31"))
        for bad in ("H1/2024", "2025-Q1/26", "Q1-Q2/26", None, "2024 H1"):
            self.assertIsNone(PT.period_bounds(bad), bad)

    def test_table_header_tiers_and_highlight(self):
        t = PT.table([("A", 0, None), ("B", 1, "FACT-T2")], [["x", ["1,234", D.tier("E")]], ["y", "·"]], hl={1})
        th = [n for n, _ in walk(t) if isinstance(n, dict) and n.get("t") == "th"]
        self.assertTrue(has_mark(th[1]) and not has_mark(th[0]))
        trs = [n for n, _ in walk(t) if isinstance(n, dict) and n.get("t") == "tr"][1:]
        self.assertNotEqual(trs[0].get("s"), trs[1].get("s"))
        self.assertEqual(bare_numbers(t), [])

    def test_table_reason_cells_wrap_numbers_do_not(self):
        t = PT.table([("A", 0, None), ("Số", 1, None), ("Số", 1, None)],
                     [["x", ["1,234", D.tier("E")], [D.can_data("tự doanh vc_lk chỉ từ 02/01/2019")]]])
        tds = [n for n, _ in walk(t) if isinstance(n, dict) and n.get("t") == "td"]
        self.assertEqual(tds[1]["s"].get("whiteSpace"), "nowrap")
        self.assertNotIn("whiteSpace", tds[2]["s"])                   # lý do [CẦN DATA] được xuống dòng

    def test_codong_svg_time_axis(self):
        moc = [{"ky": "2020-12", "end": "2020-12-31", "v": 100, "usable": True},
               {"ky": "2021-01", "end": "2021-01-31", "v": 110, "usable": True},
               {"ky": "2023-12", "end": "2023-12-31", "v": 150, "usable": True}]
        svg = PT.codong_svg(moc)
        yrs = {n["k"][0]: n["a"]["x"] for n, _ in walk(svg) if isinstance(n, dict) and n.get("t") == "text"
               and n["a"].get("y") == 156}
        self.assertEqual(sorted(yrs), ["2021", "2022", "2023"])          # nhãn năm ở 1/1, không ở mốc đầu tiên
        self.assertAlmostEqual(yrs["2022"] - yrs["2021"], yrs["2023"] - yrs["2022"], delta=1)   # thời gian đều
        d = next(n for n, _ in walk(svg) if isinstance(n, dict) and n.get("t") == "path")["a"]["d"]
        dx = float(re.match(r"M[\d.]+ [\d.]+l([\d.]+)", d).group(1))
        self.assertLess(dx, 50)                                           # mốc 01/2021 sát mốc 12/2020 (1 tháng)

    def test_ev8_buy_cost_and_sell_price_split(self):
        V_ = lambda x: V(x, str(x), "EST", "2026-10-01")  # noqa: E731
        td = type("TD", (), {})()
        td.costs = [{"row": "b1", "method": "tt", "price": V_(20000.0), "px": V_(30000.0), "gap_pct": V_(50.0)}]
        td.sells = [{"row": "s1", "method": "khop", "price": V_(40000.0), "px": V_(30000.0), "gap_pct": V_(-25.0)}]
        td.row_names = lambda: {"b1": "Quỹ Mua", "s1": "Quỹ Bán"}
        td.intent, td.why_none = {}, (lambda w: w)
        ev, _ = BK._ev8(td)
        txt = text_of(D.h("div", None, *ev.kids))
        self.assertIn("Quỹ Mua: giá vốn ước (mua) 20.0K", txt)
        self.assertIn("Quỹ Bán: giá bán ra ước 40.0K", txt)
        self.assertNotIn("Quỹ Bán: giá vốn", txt)
        self.assertNotIn("-25.00%", txt)                                  # dòng bán không tính chênh
        td.costs = []
        txt = text_of(D.h("div", None, *BK._ev8(td)[0].kids))
        self.assertIn("không có giao dịch mua của tổ chức nội bộ trong 36T", txt)

    def test_chart_slots_by_plan(self):
        CH = V2.CH
        one = V2.chart_slots("GEL", CH.window_plan(34), 34)
        self.assertEqual([(s.get("if"), s["inc"]) for s in one], [(None, "codong/GEL/chart/MAX")])
        two = V2.chart_slots("X", CH.window_plan(166), 166)
        self.assertEqual([(s["if"], s["inc"]) for s in two], [({"codong.win": ["MAX", "5Y"]}, "codong/X/chart/MAX"),
                                                               ({"codong.win": "2Y"}, "codong/X/chart/2Y")])
        three = V2.chart_slots("VIC", CH.window_plan(982), 982)
        self.assertEqual([s["inc"] for s in three], ["codong/VIC/chart/" + w for w in ("MAX", "5Y", "2Y")])

    def test_fit_budget_downgrade_and_warn(self):
        big = D.h("div", None, *[D.h("span", None, "x" * 50) for _ in range(40)], key="k")
        small = D.h("div", None, "ok", key="k")
        msgs = []
        out = V2.fit_budget("codong/T/x", big, (1000, 500), [("rút gọn thử", lambda: small)], msgs.append)
        self.assertIs(out, small)
        self.assertEqual(len(msgs), 1)
        self.assertTrue(msgs[0].startswith("codong v2: codong/T/x ") and msgs[0].endswith("→ rút gọn thử"), msgs)
        self.assertIs(V2.fit_budget("k", small, (1000, 500), [], msgs.append), small)
        V2.fit_budget("k2", big, (1000, 500), [], msgs.append)
        self.assertIn("không còn cách hạ", msgs[-1])

    def test_trim_old_sections_only(self):
        rows = lambda n: D.h("tbody", None, *[D.h("tr", None, D.h("td", None, str(i))) for i in range(n)])  # noqa: E731
        tree = D.h("div", None, D.h("section", None, rows(9), key="codong.s9"), D.h("section", None, rows(9),
                                                                                  key="codong.s4"))
        V2._trim_old(tree, 2)
        self.assertEqual(len(find_key(tree, "codong.s9")["k"][0]["k"]), 2)
        self.assertEqual(len(find_key(tree, "codong.s4")["k"][0]["k"]), 9)


class Static(unittest.TestCase):
    def test_sources(self):
        for f in FILES:
            src = (HERE / f).read_text(encoding="utf-8")
            for bad in ("vc_lk_fetch", "urllib", "requests", "socket", "open(", EM, EN, "as of", "105 weeks"):
                self.assertNotIn(bad, src, "%s: %r" % (f, bad))
            self.assertLessEqual(src.count("\n"), 800, f)
            for n in ast.walk(ast.parse(src)):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.assertLessEqual(n.end_lineno - n.lineno + 1, 50, "%s:%s" % (f, n.name))
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value != PT.FORBID_RE.pattern:
                    self.assertIsNone(SRC_BAN.search(n.value), "%s: %r" % (f, n.value[:60]))

    def test_v21_mode_untouched(self):
        """Mode v21 không nhập module v2 (luật §0.2-1): chỉ chaebol_map_tab_codong nhập trễ ở nhánh live."""
        src = (HERE / "chaebol_map.py").read_text(encoding="utf-8")
        self.assertNotIn("codong_v2", src)


# ── kho thật ────────────────────────────────────────────────────────────────


@unittest.skipUnless(LIVE_OK, "kho vc_lk/v21_const vắng: bỏ test live")
class Live(unittest.TestCase):
    def setUp(self):
        self.res, self.ctx, self.norm = build(True)
        self.inc = self.res["inc"]
        import chaebol_map_data_codong2 as O
        self.O = O
        self.groups = O.universe_groups(self.ctx.v21)
        self.order = self.groups["order"]

    def page(self, tk, sub="phase_info", win="MAX"):
        st = {"codong.tk": tk, "codong.sub": sub, "codong.win": win}
        return resolve({"t": "div", "k": [{"t": "div", "inc": "codong/" + tk}]}, self.inc, st)

    def test_states_and_scopes(self):
        st = {s["key"]: s for s in self.norm["states"]}
        self.assertEqual((st["codong.tk"]["default"], st["codong.tk"]["options"]), ("VIC", self.order))
        self.assertGreaterEqual(len(self.order), 100)
        self.assertEqual((st["codong.sub"]["default"], st["codong.sub"]["options"]), ("phase_info", SUB_IDS))
        self.assertEqual((st["codong.win"]["default"], st["codong.win"]["options"]), ("MAX", ["MAX", "5Y", "2Y"]))
        self.assertEqual(self.norm["root"]["scope"], ["codong.tk"])

    def test_inc_keys_and_root(self):
        keys = set(self.inc)
        self.assertIn("codong/_tong", keys)
        for tk in self.order:
            self.assertIn("codong/" + tk, keys)
            for sid in SUB_IDS:
                self.assertIn("codong/%s/%s" % (tk, sid), keys)
        root = self.res["root"]
        self.assertEqual(root["key"], "codong.root")
        self.assertEqual(root["k"][0]["key"], "cd2.picker")
        holders = root["k"][1:-1]
        self.assertEqual([(x["if"]["codong.tk"], x["inc"]) for x in holders], [(t, "codong/" + t) for t in self.order])
        self.assertEqual(root["k"][-1], {"t": "div", "inc": "codong/_tong"})
        for k in keys:                                             # mọi inc lồng đều có đích
            for n, _ in walk(self.inc[k]):
                if isinstance(n, dict) and n.get("inc"):
                    self.assertIn(n["inc"], keys, k)

    def test_picker(self):
        pk = self.res["root"]["k"][0]
        btns = keyed(pk, lambda k: k.startswith("cd2.pk."))
        self.assertEqual([b["key"][7:] for b in btns], self.order)
        fox = find_key(pk, "cd2.pk.FOX")
        self.assertEqual(fox["on"], {"set": {"codong.tk": "FOX"}})
        self.assertNotEqual(fox["s"], find_key(pk, "cd2.pk.VIC")["s"])         # FOX chưa có vc_lk → nút mờ
        self.assertEqual(find_key(pk, "cd2.pk.VIC")["var"][0]["if"], {"codong.tk": "VIC"})

    def test_cong_first_child_verbatim(self):
        for tk in self.order:
            first = self.inc["codong/" + tk]["k"][0]
            self.assertEqual(first.get("key"), "cd2.cong", tk)
            want = self.O.cong_line(tk)["text"]
            self.assertEqual(text_of(find_key(first, "cd2.trich.cong")), want, tk)
        for tk in ("FOX", "BHI", "CST"):
            self.assertEqual(text_of(find_key(self.inc["codong/" + tk], "cd2.trich.cong")), "CỔNG: [CẦN DATA]", tk)

    def test_reading_order_chuthe_before_sigma(self):
        tree = self.page("VIC")
        keys = [n.get("key") for n, _ in walk(tree) if isinstance(n, dict) and n.get("key")]
        self.assertLess(keys.index("cd2.chuthe"), keys.index("cd2.pos"))
        self.assertEqual(keys[:2], ["codong.tk.VIC", "cd2.cong"])
        pos = text_of(find_key(tree, "cd2.pos"))
        self.assertIn("P/E", pos.split("Định giá σ")[1])                     # định giá ở dòng cuối bảng
        self.assertTrue(text_of(find_key(tree, "cd2.chuthe")).startswith("Nhãn chủ thể: cần"))

    def test_no_bare_numbers_in_new_blocks(self):
        for tk in ("VIC", "MSN", "MBB", "GEL", "FOX", "REE", "GEX", "FPT"):
            for k in [x for x in self.inc if x == "codong/" + tk or x.startswith("codong/%s/" % tk)]:
                for part in new_parts(self.inc[k]):
                    self.assertEqual(bare_numbers(part), [], (k, part.get("key")))

    def test_svg_numbers_copied_to_readout(self):
        for tk in ("VIC", "REE", "GEL", "MBB"):
            for k in [x for x in self.inc if x.startswith("codong/%s/chart/" % tk)]:
                tree = self.inc[k]
                ro = find_key(tree, "cd2.readout")
                anns = keyed(tree, lambda key: key.startswith("cd2.svg.ann.") and key != "cd2.svg.ann.pt")
                self.assertTrue(anns, k)
                for a in anns:
                    num = text_of(a)
                    hit = [p for p, anc in walk(ro) if isinstance(p, dict) and any(
                        c == num or (isinstance(c, str) and c.endswith(num)) for c in p.get("k", ()))]
                    self.assertTrue(hit, (k, num))
                    kids = hit[0]["k"]
                    i = next(j for j, c in enumerate(kids) if isinstance(c, str) and c.endswith(num))
                    self.assertTrue(is_mark(kids[i + 1]), (k, num))

    def test_no_banned_words_dashes_vn_numbers(self):
        for tk in ("VIC", "MSN", "MBB", "GEL", "FOX", "REE", "STB", "HPG"):
            for k in [x for x in self.inc if x == "codong/" + tk or x.startswith("codong/%s/" % tk)]:
                for part in new_parts(self.inc[k]):
                    for s_ in plain_texts(part):
                        self.assertIsNone(BAN_RE.search(s_), (k, s_[:80]))
                        self.assertFalse(EM in s_ or EN in s_, (k, s_[:80]))
                        self.assertNotIn("as of", s_.lower())
                        self.assertIsNone(VN_NUM.search(s_), (k, s_[:80]))

    def test_pattern_q_outside_tv30(self):
        """Vế KL ≥2× TB12 của lk_hoso ('không gán nhãn D') không mang chữ 'Pattern D'; mọi 'Pattern X' (kể cả CHỮ HOA,
        như câu V21 'PATTERN B CONFIRMED' của GEX) ở mã ngoài TV30 có '?'."""
        self.assertNotIn("GEX", self.groups["tv30"])
        for tk in ("GEX", "VIC"):
            box = text_of(find_key(self.inc["codong/%s/patterns" % tk], "cd2.top.patterns"))
            self.assertIn("TUẦN KL ≥2× TB 12 TUẦN TRƯỚC", box)
            self.assertIsNone(re.search(r"pattern d", box, re.I), tk)
        import chaebol_map_tab_codong as MC
        import chaebol_map_tab_codong_deep as DD
        exempt = {MC.READING_S9[4], DD.TV_READING}         # câu định nghĩa phương pháp chung mọi mã: miễn '?'
        out = [t for t in self.order if t not in self.groups["tv30"]]
        for k in [x for x in self.inc if x.split("/")[1:2] and x.split("/")[1] in out]:
            for n, _ in walk(self.inc[k]):
                if isinstance(n, str) and n not in exempt:
                    self.assertIsNone(re.search(r"\bPattern [A-D]\b(?!\?)", n, re.I), (k, n[:80]))
        self.assertIn("PATTERN B?", text_of(self.inc["codong/GEX/phase"]))

    def test_fft_miss_warning_in_readout(self):
        for tk in ("FPT", "VCB", "MBB", "HPG", "CTG"):
            ro = text_of(find_key(self.inc["codong/%s/chart/MAX" % tk], "cd2.readout"))
            self.assertIn(self.O.FFT_MISS_TEXT, ro, tk)
            self.assertIn(self.O.FFT_MISS_TEXT, text_of(find_key(self.inc["codong/%s/strategic" % tk], "cd2.book.r6")))
        self.assertNotIn("§6.4", text_of(find_key(self.inc["codong/VIC/chart/MAX"], "cd2.readout")))

    def test_fft_miss_warning_everywhere_fft_shows(self):
        """§6.4 ở lens đầu trang, Định vị (sub 01), khối checklist/trigger (sub 09) và bảng tổng (dấu *)."""
        for tk in self.O.FFT_MISS:
            self.assertIn(self.O.FFT_MISS_TEXT, text_of(find_key(self.inc["codong/" + tk], "codong.lens")), tk)
            self.assertIn(self.O.FFT_MISS_TEXT, text_of(find_key(self.inc["codong/%s/phase_info" % tk], "cd2.pos")), tk)
            self.assertIn(self.O.FFT_MISS_TEXT, text_of(find_key(self.inc["codong/%s/patterns" % tk], "cd2.top.patterns")))
            self.assertIn("*", text_of(find_key(self.inc["codong/_tong"], "cd2.tong." + tk)), tk)
        self.assertIn(self.O.FFT_MISS_TEXT, text_of(find_key(self.inc["codong/_tong"], "cd2.fftmiss.tong")))
        self.assertNotIn("*", text_of(find_key(self.inc["codong/_tong"], "cd2.tong.VIC")))
        self.assertNotIn("§6.4", text_of(find_key(self.inc["codong/VIC"], "codong.lens")))

    def test_book_cost_fund_and_net_rows(self):
        vic8 = text_of(find_key(self.inc["codong/VIC/strategic"], "cd2.book.r8"))
        self.assertNotIn("SK Investment Vina II: giá vốn", vic8)          # SK BÁN 16/01/2025: không phải giá vốn
        self.assertNotIn("Vinpearl: giá vốn", vic8)
        msn8 = text_of(find_key(self.inc["codong/MSN/strategic"], "cd2.book.r8"))
        self.assertNotRegex(msn8, r"GIC[^:]*: giá vốn")
        vic6 = text_of(find_key(self.inc["codong/VIC/strategic"], "cd2.book.r6"))
        self.assertIn("ròng cùng tập quỹ", vic6)
        self.assertRegex(vic6, r"số quỹ 37T2·10/06 → 41T2·23/09")
        self.assertIn("tập quỹ đổi 37→41", vic6)
        vic2 = text_of(find_key(self.inc["codong/VIC/strategic"], "cd2.book.r2"))
        self.assertIn("Nhóm Phạm Nhật Vượng (6 thành viên", vic2)
        self.assertNotIn("T2·05/10/25", vic2)                              # không gắn ngày mép cửa sổ
        ctd2 = text_of(find_key(self.inc["codong/CTD/strategic"], "cd2.book.r2"))
        self.assertIn("2.45%T2·05/08/25 → 1.38%T2·12/05", ctd2)

    def test_vnstore_tickers_tier_u_and_source(self):
        for tk in ("PLC", "PPC", "SGN"):
            if self.groups["has_vc"].get(tk):
                continue
            main = text_of(self.inc["codong/" + tk])
            self.assertRegex(main, r"GIÁ[\d.,]+KU·", tk)
            self.assertNotRegex(main, r"GIÁ[\d.,]+KT2", tk)
            phu = text_of(find_key(self.inc["codong/" + tk], "cd2.phu"))
            self.assertIn("vnstore nen_ngay (giá trộn)", phu)
            self.assertNotIn("vc_lk tới", phu)
            ch = text_of(self.inc["codong/%s/chart" % tk])
            self.assertNotIn("(vc_lk, ", ch)
            cl = self.inc["codong/%s/cluster" % tk]
            self.assertTrue(find_key(cl, "cd2.zig.vn"), tk)
            self.assertLessEqual(text_of(find_key(cl, "cd2.zig")).count("[CẦN DATA"), 12, tk)

    def test_lens_residual_same_basis(self):
        txt = text_of(find_key(self.inc["codong/VIC"], "codong.lens"))
        m = re.search(r"phần dư −\(NN tổng \+ TD tổng\) ([+-]?[\d.]+)M cp", txt)
        if m:
            f4, pt = self.ctx.data.flow4("VIC", 60), self.ctx.data.prop_net("VIC", 60, kind="total")
            self.assertAlmostEqual(float(m.group(1)), -(f4["nn"].value + pt["vol"].value / 1e6), delta=0.051)

    def test_chart_ath_not_covered_by_marker_numbers(self):
        """Chữ đỉnh lịch sử và nhãn số ①…⑫ không chồng quá 1/4 diện tích chữ nhỏ hơn (ca PVD MAX '31⑪4K')."""
        CH = V2.CH
        for k in [x for x in self.inc if x.count("/") == 3 and "/chart/" in x]:
            ts = [n for n, _ in walk(self.inc[k]) if isinstance(n, dict) and n.get("t") == "text"
                  and str(n.get("key", "")).startswith(("cd2.svg.ann.ath", "cd2.svg.mk."))]
            bx = [CH.text_box(n["a"]["x"], n["a"]["y"], text_of(n), n["a"].get("fontSize", CH.FS),
                              n["a"].get("textAnchor")) for n in ts]
            for i, a in enumerate(bx):
                for b in bx[i + 1:]:
                    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
                    self.assertLess(CH.overlap(a, b), 0.25 * small, k)

    def test_v21_marks_and_no_105_weeks(self):
        deep = [t for t in (self.ctx.v21.get("CHAEBOL_DEEP_DATA") or {}) if t in self.order]
        self.assertGreaterEqual(len(deep), 20)
        for tk in deep:
            txt = "".join(text_of(self.inc[k]) for k in self.inc if k == "codong/" + tk or k.startswith(
                "codong/%s/" % tk))
            self.assertIn("V21·12/05", txt, tk)
        for k, n in self.inc.items():
            self.assertNotIn("105 weeks", text_of(n), k)

    def test_vic_chart_eyebrow_and_windows(self):
        ey = text_of(find_key(self.inc["codong/VIC/chart/MAX"], "cd2.eyebrow"))
        self.assertIn("982 tuần từ niêm yết (17/09/2007 →", ey)
        self.assertIn("thang log", ey)
        bar = find_key(self.inc["codong/VIC/chart"], "cd2.chart")
        self.assertEqual(bar["scope"], ["codong.win"])
        for w in ("MAX", "5Y", "2Y"):
            self.assertEqual(find_key(bar, "cd2.win." + w)["on"], {"set": {"codong.win": w}})
            self.assertIn("codong/VIC/chart/" + w, self.inc)
        self.assertTrue(find_key(self.inc["codong/VIC/chart/MAX"], "cd2.legend"))

    def test_gel_short_series_one_chart(self):
        self.assertEqual([k for k in self.inc if k.startswith("codong/GEL/chart/")], ["codong/GEL/chart/MAX"])
        bar = find_key(self.inc["codong/GEL/chart"], "cd2.chart")
        for w in ("MAX", "5Y", "2Y"):
            self.assertNotIn("on", find_key(bar, "cd2.win." + w), w)
        slots = [n for n, _ in walk(bar) if isinstance(n, dict) and n.get("inc")]
        self.assertEqual([(s.get("if"), s["inc"]) for s in slots], [(None, "codong/GEL/chart/MAX")])

    def test_fox_can_data_no_error(self):
        for sid in SUB_IDS:
            self.assertIn("[CẦN DATA", text_of(self.inc["codong/FOX/" + sid]), sid)
        self.assertIn("chưa nạp vc_lk", text_of(self.inc["codong/FOX/chart"]))
        self.assertFalse([k for k in self.inc if k.startswith("codong/FOX/chart/")])
        self.assertFalse([w for w in self.ctx.warnings if " FOX" in w and "lỗi" in w], self.ctx.warnings)

    def test_mbb_capitaliq_holders(self):
        tb = find_key(self.inc["codong/MBB/capitaliq"], "cd2.holders")
        n_rows = len(tb["k"][1]["k"])
        ht = self.O.holder_table("MBB", "2026-10-05")
        down = [w for w in self.ctx.warnings if "codong/MBB/capitaliq" in w and "→" in w]
        if down:
            self.assertEqual(n_rows, ht["n_fresh"] + min(40, ht["n_old"]))
        else:
            self.assertEqual(n_rows, ht["n"])
        self.assertGreaterEqual(ht["n"], 113)

    def test_vic_evidence_book(self):
        book = find_key(self.inc["codong/VIC/strategic"], "cd2.book")
        rows = keyed(book, lambda k: re.fullmatch(r"cd2\.book\.r\d", k) is not None)
        self.assertEqual([r["key"] for r in rows], ["cd2.book.r%d" % i for i in range(1, 10)])
        heads = [text_of(n) for n, _ in walk(book) if isinstance(n, dict) and n.get("t") == "th"]
        self.assertEqual(heads, ["#", "Câu hỏi", "Bằng chứng (số)", "Nguồn", "Bậc", "Ngày", "Trạng thái dữ liệu"])
        self.assertFalse(any("kết luận" in x.lower() for x in heads))
        self.assertIn(self.O.HIERARCHY_TEXT, text_of(book))
        gold = find_key(book, "cd2.book.vang")
        self.assertTrue(text_of(gold).startswith(BK.GOLD_Q))
        mk = self.O.intent_sources("VIC")["cauchuyen"]["muc_dich_keo"]
        node = find_key(gold, "cd2.trich.muc_dich_keo")
        self.assertEqual(text_of(node), mk["text"])
        kids = gold["k"]
        self.assertTrue(is_mark(kids[kids.index(node) + 1]))
        self.assertIn("liên quan: dòng 2, 4, 6, 8", text_of(gold))

    def test_vic_transfers_and_msn_ladder(self):
        pairs = find_key(self.inc["codong/VIC/capitaliq"], "cd2.pairs")
        rows = [text_of(r) for r in pairs["k"][1]["k"]]
        y25 = [r for r in rows if "/2025" in r]
        self.assertEqual(len(y25), 7)
        self.assertTrue(all("chuyển giao nội nhóm (không qua thị trường)" in r for r in y25))
        lad = text_of(find_key(self.inc["codong/MSN/capitaliq"], "cd2.ladder"))
        self.assertRegex(lad, r"(?i)SK Investment Vina I\b.*9\.45%.*→ 3\.67%")

    def test_budgets_or_downgrade_warning(self):
        for k, node in self.inc.items():
            parts = k.split("/")
            if k == "codong/_tong":
                cap = V2.TONG_BUDGET
            elif len(parts) == 2:
                cap = V2.TK_BUDGET[parts[1] in V2_old_tickers(self.ctx)]
            elif len(parts) == 4:
                cap = V2.CHART_BUDGET[parts[3]]
            else:
                cap = V2.SUB_BUDGET[parts[2]]
            obj, st = D.finalize(node)
            nb = len(D.dumps(obj).encode("utf-8"))
            if nb > cap[0] or st["nodes"] > cap[1]:
                self.assertTrue([w for w in self.ctx.warnings if (" %s " % k) in w], (k, nb, st["nodes"]))
        obj, st = D.finalize(self.norm["root"])
        self.assertLessEqual(len(D.dumps(obj).encode("utf-8")), V2.ROOT_BUDGET[0])
        self.assertLessEqual(st["nodes"], V2.ROOT_BUDGET[1])

    def test_summary_table_and_csv(self):
        tong = self.inc["codong/_tong"]
        rows = keyed(tong, lambda k: k.startswith("cd2.tong."))
        self.assertEqual([r["key"][9:] for r in rows], self.order)
        self.assertEqual(rows[0]["on"], {"set": {"codong.tk": self.order[0], "codong.sub": "phase_info"}})
        self.assertTrue(text_of(tong).count("[CẦN DATA]") > 0)
        self.assertEqual(bare_numbers(tong), [])
        for s_ in plain_texts(tong):
            if self.O.FFT_MISS_TEXT in s_:          # cảnh báo §6.4 bắt buộc (CLAUDE.md), không phải nhãn của mã
                continue
            self.assertIsNone(re.search(r"BULL|BEAR|MUA|BÁN|tích luỹ|phân phối", s_), s_)
        csv = self.res["csv"]
        self.assertEqual([r["ma"] for r in csv], self.order)
        vic = next(r for r in csv if r["ma"] == "VIC")
        self.assertEqual(vic["nb_rong_12t_bac"], "EST")
        self.assertIn("top1", vic)

    def test_no_error_warnings_except_known_old_layer(self):
        bad = [w for w in self.ctx.warnings if "lỗi" in w and "LiveTk.head_stats" not in w]
        self.assertEqual(bad, [])


def V2_old_tickers(ctx):
    import chaebol_map_tab_codong as TC
    return set(TC.V21(ctx.v21).tickers)


@unittest.skipUnless(LIVE_OK, "kho vc_lk/v21_const vắng: bỏ test live")
class Off(unittest.TestCase):
    """ctx.data None: dựng được, mọi số mới là [CẦN DATA] (không có nhãn bậc ngoài tiêu đề cột và dấu V21)."""

    def setUp(self):
        self.res, self.ctx, self.norm = build(False)

    def test_builds_all_and_new_numbers_are_can_data(self):
        inc = self.res["inc"]
        order = self.norm["states"][0]["options"]
        self.assertIn("codong/_tong", inc)
        for tk in ("VIC", "FOX", "MBB"):
            first = inc["codong/" + tk]["k"][0]
            self.assertEqual(text_of(find_key(first, "cd2.trich.cong")), "CỔNG: [CẦN DATA]")
            for k in [x for x in inc if x == "codong/" + tk or x.startswith("codong/%s/" % tk)]:
                for part in new_parts(inc[k]):
                    tiers = [n for n, anc in walk(part) if isinstance(n, dict) and n.get("_tier")
                             and not any(a.get("t") == "th" for a in anc)]
                    self.assertEqual(tiers, [], (k, part.get("key")))
            self.assertFalse([k for k in inc if k.startswith("codong/%s/chart/" % tk)])
        self.assertEqual(len([k for k in inc if k.count("/") == 1]) - 1, len(order))

    def test_ticker_error_isolated(self):
        """Một mã lỗi → inc = [CỔNG, [CẦN DATA: dựng mã lỗi…]] + cảnh báo; mã khác vẫn dựng (§7.1)."""
        from unittest import mock
        real = V2.build_ticker

        def boom(ctx, D21, shared, tk, groups, v21):
            if tk == "FOX":
                raise KeyError("thử lỗi")
            return real(ctx, D21, shared, tk, groups, v21)
        with D.use_mode("live", "2026-10-05"), mock.patch.object(V2, "build_ticker", boom):
            ctx = make_ctx(False)
            res = V2.build_codong_v2(ctx)
        fox = res["inc"]["codong/FOX"]
        self.assertEqual(fox["k"][0]["key"], "cd2.cong")
        self.assertIn("[CẦN DATA " + EM + " dựng mã lỗi, xem cảnh báo]", text_of(fox))
        self.assertTrue([w for w in ctx.warnings if "dựng FOX lỗi KeyError" in w])
        self.assertFalse([k for k in res["inc"] if k.startswith("codong/FOX/")])
        self.assertIn("codong/VIC/strategic", res["inc"])


@unittest.skipUnless(LIVE_OK, "kho vc_lk/v21_const vắng: bỏ test live")
class Hooks(unittest.TestCase):
    """DeepLiveV2 dời khối live cũ lên top/bottom (không lặp) và giữ thẻ đầu mã khi LiveTk.head_stats lỗi."""

    def test_overrides_and_card_survives(self):
        res, ctx, _ = build(True)
        lv = V2.DeepLiveV2(ctx, "VIC", V2.DD._T(ctx.v21, "VIC"), V2.TkData(ctx, "VIC", "2026-10-05", {"tv30": []}))
        self.assertEqual((lv.codong_table(), lv.holders_live(), lv.vwap_live_table(), lv.flow_only_live()),
                         (None, None, None, None))
        self.assertEqual((lv.flow_live_rows(), lv.events_new_rows()), ([], []))
        self.assertIsNone(lv.top("phase"))
        self.assertEqual(lv.bottom("flow")["key"], "cd2.nguon.flow")
        for tk in ("DPM", "PVT", "REE"):
            page = res["inc"]["codong/" + tk]
            self.assertTrue(find_key(page, "codong.card"), tk)
            self.assertTrue(find_key(page, "codong.lens"), tk)
        new_tk = [k for k in res["inc"] if k == "codong/REE"][0]
        self.assertIsNone(find_key(res["inc"][new_tk], "codong.s2"))          # s2/s4…s7/s11 chỉ 48 mã cũ
        self.assertTrue(find_key(res["inc"]["codong/VIC"], "codong.s2"))
        no_action = text_of(res["inc"]["codong/REE/action"])
        self.assertIn("Không có action V21 cho REE; CỔNG v1.7 DỪNG: không sinh khuyến nghị.", no_action)
