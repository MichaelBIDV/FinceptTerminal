#!/usr/bin/env python3
"""Unit tests cho lõi chaebol_map (chaebol_map_dom / chaebol_map_shell / chaebol_map.py) — không mạng.

Chạy (cả hai trình thông dịch):
    python3 -m unittest scripts/test_chaebol_map_core.py -v
    ~/Library/Application\\ Support/com.fincept.terminal/venv-numpy2/bin/python -m unittest scripts/test_chaebol_map_core.py

Giá trị vàng của định dạng số lấy từ V8 (node v24) ngày 27/09/2026 và từ chaebol_map_spec/page_p2_index_tabs.md
(VN30 5w Cá nhân '+195.5', 30w Tổ chức '+450.3', SUM '-0.0'). Socket bị chặn trong tiến trình và trong mọi tiến
trình con CLI (bọc runpy) để chứng minh không có lời gọi mạng. Test CLI dùng CHB_SYSTEM_DIR trỏ vào thư mục rỗng và
--out / CHB_STATE_DIR tạm → không đọc/ghi kho thật.
"""
from __future__ import annotations

import io
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import chaebol_map as M  # noqa: E402
import chaebol_map_dom as D  # noqa: E402
import chaebol_map_shell as S  # noqa: E402

SCRIPT = HERE / "chaebol_map.py"
VENV_PY = Path.home() / "Library/Application Support/com.fincept.terminal/venv-numpy2/bin/python"
REAL_V21 = Path.home() / "SECOND BRAIN-OBSIDIAN/_System/fincept_bridge/data/chaebol_map/v21_const.json"
TAB_IDS = [t[0] for t in S.TABS_V21]
GUARD = textwrap.dedent("""
    import socket, runpy, sys
    def _blocked(*a, **k):
        raise RuntimeError("mạng bị chặn trong test chaebol_map")
    socket.socket = _blocked
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked
    sys.argv = [sys.argv[1]] + sys.argv[2:]
    runpy.run_path(sys.argv[0], run_name="__main__")
""")

_REAL_SOCKET = {}


def setUpModule():
    def blocked(*a, **k):
        raise RuntimeError("mạng bị chặn trong test chaebol_map")
    for name in ("socket", "create_connection", "getaddrinfo"):
        _REAL_SOCKET[name] = getattr(socket, name)
        setattr(socket, name, blocked)


def tearDownModule():
    for name, fn in _REAL_SOCKET.items():
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


# ── Luật số JS ──────────────────────────────────────────────────────────────

# Cửa sổ thật từ INDEX_DATA của trang (VN30_PL_W, 5 và 30 tuần cuối).
VN30_5W_CA = [14.46, 30.28, 64.41, 19.68, 66.62]
VN30_30W = {
    "ca": [113.81, 86.01, -26.72, 46.26, -2.12, -25.79, -37.21, -47.49, -30.51, 15.61, -30.45, -45.87, -30.89,
           -25.59, 36.84, 20.63, -18.94, 5.33, -35.16, -21.64, -7.96, -8.52, 73.99, 36.88, 51.69, 14.46, 30.28,
           64.41, 19.68, 66.62],
    "tc": [44.99, 37.25, 72.77, 14.34, 51.96, 42.64, 29.66, 50.61, -44.75, 5.87, 7.52, 18.52, -2.87, -43.21, -3.3,
           -25.28, 1.95, 71.97, 17.92, -26.06, 121.78, -15.77, 19.54, 0.59, 35.35, -29.77, -45.49, 14.68, 1.82,
           25.02],
    "td": [-40.75, -20.32, 53.09, 2.44, 7.8, 10.09, -7.6, 3.36, -0.6, -3.33, 0, 7.49, 5.98, 5.7, 3.46, 4.18, 72.36,
           -4.07, -13.21, 13.86, -17.16, 10.72, -8.64, 3.66, -17.99, 15.01, 24.22, -15.64, 5.94, 3.3],
    "nn": [-118.04, -102.93, -99.14, -63.04, -57.63, -26.94, 15.16, -6.49, 75.86, -18.16, 22.93, 19.86, 27.78,
           63.1, -37, 0.46, -55.38, -73.24, 30.45, 33.84, -96.66, 13.57, -84.89, -41.14, -69.06, 0.3, -9.01,
           -63.46, -27.43, -94.93],
}
VNI_5W = {"ca": [25.85, 72.18, 95.18, 37.72, 100.52], "tc": [-108.2, -44.63, 29.13, -4.9, -0.47],
          "td": [20.68, 36.03, -21.84, 8.44, 9.26], "nn": [61.67, -63.58, -102.47, -41.26, -109.31]}


class TestJsNumbers(unittest.TestCase):
    def test_to_fixed_golden(self):
        cases = [((1.005, 2), "1.00"), ((2.675, 2), "2.67"), ((8.345, 2), "8.35"), ((-0.04, 1), "-0.0"),
                 ((-0.04, 0), "-0"), ((-0.0, 1), "0.0"), ((450.25, 1), "450.3"), ((195.45, 1), "195.4"),
                 ((2.5, 0), "3"), ((-2.5, 0), "-3"), ((-1.5, 0), "-2"), ((0.5, 0), "1"), ((1e21, 2), "1e+21"),
                 ((26967, 1), "26967.0"), ((0.045, 2), "0.04"), ((1.45, 1), "1.4"), ((-0.05, 1), "-0.1"),
                 ((0.30000000000000004, 1), "0.3"), ((123456789.123, 2), "123456789.12")]
        for (x, d), want in cases:
            self.assertEqual(D.to_fixed(x, d), want, (x, d))

    def test_js_string_golden(self):
        cases = [(0.1 + 0.2, "0.30000000000000004"), (1e21, "1e+21"), (1e-7, "1e-7"), (-1e-7, "-1e-7"),
                 (1.5e-7, "1.5e-7"), (1e16, "10000000000000000"), (0.000001, "0.000001"), (-0.0, "0"),
                 (123.0, "123"), (5e-324, "5e-324"), (1.23e-18, "1.23e-18"), (2 ** 60, "1152921504606847000"),
                 (123456789012345680000, "123456789012345680000"), (26967, "26967"), (-2.5, "-2.5"),
                 (13.62, "13.62"), (float("nan"), "NaN"), (float("-inf"), "-Infinity")]
        for x, want in cases:
            self.assertEqual(D.js_string(x), want, x)

    def test_to_locale_golden(self):
        cases = [((1.005, "en-US", None, 2), "1.01"), ((1234.5678, "en", None, None), "1,234.568"),
                 ((-1234.5678, "vi-VN", None, None), "-1.234,568"), ((-0.0, "en", None, None), "-0"),
                 ((-0.0004, "en", None, None), "-0"), ((0, "en", None, None), "0"), ((26967, "vi-VN", None, None),
                                                                                     "26.967"),
                 ((1915.37, "en-US", None, 2), "1,915.37"), ((1.45, "vi-VN", None, 1), "1,5"),
                 ((2.5, "en-US", 2, None), "2.50"), ((1234.5, "en-US", 2, 2), "1,234.50"),
                 ((1e21, "en", None, None), "1,000,000,000,000,000,000,000"), ((0.045, "en-US", None, 2), "0.05"),
                 ((89654, "en", None, None), "89,654"), ((1785.113, "en-US", None, 2), "1,785.11"),
                 ((26180, "en-US", None, 0), "26,180"), ((-0.0001, "vi-VN", None, 2), "-0"),
                 ((2.675, "en-US", None, 2), "2.68")]
        for (x, loc, mn, mx), want in cases:
            self.assertEqual(D.to_locale(x, loc, min_frac=mn, max_frac=mx), want, (x, loc, mn, mx))
        with self.assertRaises(ValueError):
            D.to_locale(1, "fr-FR")
        with self.assertRaises(ValueError):
            D.to_locale(1, "en", min_frac=3, max_frac=2)

    def test_js_round(self):
        self.assertEqual(D.js_round(2.5), 3)
        self.assertEqual(D.js_round(-2.5), -2)
        self.assertEqual(D.js_round(-1.5), -1)
        self.assertEqual(D.js_round(0.49999999999999994), 0)
        neg0 = D.js_round(-0.4)
        self.assertTrue(neg0 == 0 and math.copysign(1, neg0) < 0, "Math.round(-0.4) = -0")
        self.assertEqual(D.to_locale(neg0, "en"), "-0")

    def test_sequential_sum_page_p2(self):
        s = D.js_sum(VN30_5W_CA)
        self.assertEqual(D.sign_fixed(s, 1), "+195.5")
        # sum() của 3.12+ và math.fsum bù sai số → '195.4' — đúng lý do phải cộng tuần tự.
        self.assertEqual(D.to_fixed(math.fsum(VN30_5W_CA), 1), "195.4")
        tc = D.js_sum(VN30_30W["tc"])
        self.assertEqual(D.sign_fixed(tc, 1), "+450.3")
        self.assertEqual(format(tc, ".1f"), "450.2", "format của Python làm tròn nửa-chẵn")
        tot30 = D.js_sum(VN30_30W["ca"]) + D.js_sum(VN30_30W["tc"]) + D.js_sum(VN30_30W["td"]) + \
            D.js_sum(VN30_30W["nn"])
        self.assertEqual(D.to_fixed(tot30, 1), "-0.0")
        tot5 = sum((D.js_sum(VNI_5W[k]) for k in ("ca", "tc", "td", "nn")), 0.0)
        self.assertEqual(D.to_fixed(tot5, 1), "-0.0")
        self.assertEqual([D.sign_fixed(D.js_sum(VNI_5W[k]), 1) for k in ("ca", "tc", "td", "nn")],
                         ["+331.4", "-129.1", "+52.6", "-254.9"])

    def test_sign_fixed(self):
        self.assertEqual(D.sign_fixed(0, 1), "+0.0")
        self.assertEqual(D.sign_fixed(-0.0, 1), "+0.0")
        self.assertEqual(D.sign_fixed(0, 1, strict=True), "0.0")
        self.assertEqual(D.sign_fixed(-45.4, 1), "-45.4")

    def test_zfix_live_only(self):
        """Số âm-không (final_check §6.2 #2): live in '0.0'; v21 giữ '-0.0' của toFixed; mặc định không đổi."""
        with D.use_mode("live", "2026-09-27"):
            self.assertEqual(D.to_fixed(-0.04, 1), "-0.0", "mặc định vẫn đúng JS")
            self.assertEqual(D.sign_fixed(-0.04, 1), "-0.0")
            self.assertEqual(D.to_fixed(-0.04, 1, zfix=True), "0.0")
            self.assertEqual(D.to_fixed(-0.04, 0, zfix=True), "0")
            self.assertEqual(D.to_fixed(-0.05, 1, zfix=True), "-0.1")
            self.assertEqual(D.sign_fixed(-0.04, 1, zfix=True), "0.0")
            self.assertEqual(D.sign_fixed(0.04, 1, zfix=True), "0.0", "số làm tròn bằng 0 không mang dấu")
            self.assertEqual(D.sign_fixed(0.05, 1, zfix=True), "+0.1")
            self.assertEqual(D.sign_fixed(-45.4, 1, zfix=True), "-45.4")
            for raw, want in (("-0.0M", "0.0M"), ("+0.0%", "0.0%"), ("−0,0", "0,0"), ("-0", "0"),
                              ("-0.05", "-0.05"), ("-10.0", "-10.0"), ("-0.0.5", "-0.0.5"), ("0.0", "0.0")):
                self.assertEqual(D.zfix(raw), want, raw)
            self.assertIsNone(D.zfix(None))
        with D.use_mode("v21", "2026-09-27"):
            self.assertEqual(D.to_fixed(-0.04, 1, zfix=True), "-0.0")
            self.assertEqual(D.sign_fixed(-0.04, 1, zfix=True), "-0.0")
            self.assertEqual(D.sign_fixed(0.04, 1, zfix=True), "+0.0")
            self.assertEqual(D.zfix("-0.0"), "-0.0")


# ── Builder nút + intern ───────────────────────────────────────────────────


class TestDom(unittest.TestCase):
    def test_children_flatten_merge_skip(self):
        n = D.h("div", None, "Giá ", 26967, None, False, True, "", [" · ", ["Δ60d "]], D.h("span", None, "x"))
        self.assertEqual(n["k"][0], "Giá 26967 · Δ60d ")
        self.assertEqual(n["k"][1]["t"], "span")
        self.assertEqual(D.h("div", None, 0.1 + 0.2)["k"], ["0.30000000000000004"])
        self.assertNotIn("k", D.h("br"))

    def test_style_normalize(self):
        n = D.h("div", {"border": "1px solid #26242c", "borderLeft": "3px solid #caa75c", "color": None,
                        "x": "", "hide": False, "width": 24.0, "strokeWidth": 2, "lineHeight": 1.7})
        self.assertEqual(list(n["s"]), ["border", "borderLeft", "width", "strokeWidth", "lineHeight"])
        self.assertEqual(n["s"]["width"], 24)
        self.assertIsInstance(n["s"]["width"], int)
        self.assertEqual(n["s"]["strokeWidth"], "2")
        self.assertEqual(n["s"]["lineHeight"], 1.7)

    def test_button_select_font_inherit(self):
        b = D.h("button", {"padding": 4})
        self.assertEqual(b["s"], {"fontFamily": "inherit", "fontSize": "inherit", "fontWeight": "inherit",
                                  "padding": 4})
        b2 = D.h("button", {"fontSize": 11, "fontWeight": 500, "fontFamily": D.F_MONO})
        self.assertNotIn("inherit", json.dumps(b2))
        s = D.h("select", {"fontSize": 10}, bind="c54.ch")
        self.assertEqual(s["s"]["fontFamily"], "inherit")
        self.assertEqual(s["s"]["fontSize"], 10)
        self.assertEqual(s["bind"], "c54.ch")

    def test_validation(self):
        with self.assertRaises(ValueError):
            D.h("blink")
        with self.assertRaises(TypeError):
            D.h("span", "chữ")
        with self.assertRaises(ValueError):
            D.h("div", None, "x", count={"grp": "g", "fmt": "Showing {n}/54"})
        with self.assertRaises(ValueError):
            D.h("div", None, count={"grp": "g", "fmt": "không có n"})
        with self.assertRaises(ValueError):
            D.h("span", href="https://x")
        with self.assertRaises(ValueError):
            D.h("div", on={"toggle": {}})
        with self.assertRaises(ValueError):
            D.h("div", inc="codong/VIC ★")

    def test_attrs(self):
        n = D.h("tbody", None, D.h("tr", None, "a", sk={"px": 26967.0, "tk": "GEX", "none": None}),
                sort={"key": "scr.sort", "dir": "scr.dir"}, key="rows")
        self.assertEqual(n["sort"], {"key": "scr.sort", "dir": "scr.dir"})
        self.assertEqual(n["k"][0]["sk"], {"px": 26967, "tk": "GEX"})
        b = D.h("th", None, "GIÁ", on={"sort": {"key": "scr.sort", "dir": "scr.dir", "col": "px"}},
                if_={"tab|scr.sig": ["screener|BULL", "screener|ALL"]})
        self.assertEqual(b["on"]["sort"]["col"], "px")
        self.assertEqual(b["if"]["tab|scr.sig"], ["screener|BULL", "screener|ALL"])
        svg = D.h("svg", {"display": "block"}, a={"viewBox": "0 0 780 340", "width": "100%", "x": float("nan")})
        self.assertEqual(svg["a"], {"viewBox": "0 0 780 340", "width": "100%"})
        self.assertEqual(D.slot("main"), {"t": "slot", "id": "main"})

    def test_finalize_interns_per_file(self):
        a = {"padding": "5px 7px", "borderBottom": "1px solid #232830"}
        tree = D.h("table", None, D.h("tbody", None,
                                      D.h("tr", None, D.h("td", a, "C01"), D.h("td", {"color": "#fff"}, "x")),
                                      D.h("tr", None, D.h("td", dict(a), "C02"),
                                          D.h("td", None, "y", var=[{"if": {"tab": "t"}, "s": a}])),
                                      D.h("tr", None, D.h("td", None, cls={"fontWeight": 700}))))
        before = json.dumps(tree, ensure_ascii=False, sort_keys=True)
        obj, st = D.finalize(tree)
        self.assertEqual(json.dumps(tree, ensure_ascii=False, sort_keys=True), before, "không sửa cây đầu vào")
        self.assertEqual(obj["cls"], {"k0": a, "k1": {"fontWeight": 700}})
        rows = obj["root"]["k"][0]["k"]
        self.assertEqual(rows[0]["k"][0]["c"], "k0")
        self.assertNotIn("s", rows[0]["k"][0])
        self.assertEqual(rows[0]["k"][1]["s"], {"color": "#fff"})
        self.assertEqual(rows[1]["k"][1]["var"], [{"if": {"tab": "t"}, "c": "k0"}])
        self.assertEqual(rows[2]["k"][0]["c"], "k1")
        self.assertEqual(st["nodes"], D.count_nodes(obj["root"]))
        self.assertEqual(st["texts"], 4)
        self.assertFalse(any(k.startswith("_") for n in walk(obj["root"]) if isinstance(n, dict) for k in n))

    def test_finalize_key_order_matters(self):
        s1 = {"border": "1px solid #26242c", "borderLeft": "3px solid #caa75c"}
        s2 = {"borderLeft": "3px solid #caa75c", "border": "1px solid #26242c"}
        obj, _ = D.finalize(D.h("div", None, D.h("div", s1), D.h("div", s2), D.h("div", s1), D.h("div", s2)))
        self.assertEqual(len(obj["cls"]), 2, "thứ tự khoá khác = style khác (shorthand/longhand)")
        self.assertEqual(list(obj["cls"]["k1"]), ["borderLeft", "border"])

    def test_jsx_text(self):
        self.assertEqual(D.jsx_text("\n        Tham chiếu cuối: "), "Tham chiếu cuối: ")
        self.assertEqual(D.jsx_text("  a  \n  b  "), "  a b  ")
        self.assertEqual(D.jsx_text("\n  dòng 1\n\n    dòng 2\n  "), "dòng 1 dòng 2")
        self.assertEqual(D.jsx_text("\n   \n"), "")

    def test_palette(self):
        self.assertEqual(D.C.gold, "#caa75c")
        self.assertEqual(D.C["parch"], "#1f1d24")
        self.assertEqual((D.C.crimson, D.C.emerald, D.C.bg2), ("#c5392f", "#3d7a4e", "#1a1a24"))
        self.assertEqual(D.alpha(D.C.paper, "70"), "#13131a70")
        with self.assertRaises(AttributeError):
            D.C.purple  # noqa: B018
        with self.assertRaises(AttributeError):
            D.C.gold = "#000"


# ── Nhãn bậc (DESIGN §6) ───────────────────────────────────────────────────


class TestLabels(unittest.TestCase):
    def test_v21_mode_emits_nothing(self):
        with D.use_mode("v21", "2026-09-27"):
            self.assertIsNone(D.tier("FACT-T2", "2026-09-25"))
            self.assertIsNone(D.upd_mark())
            self.assertIsNone(D.v21_mark())
            self.assertIsNone(D.can_data())
            self.assertIsNone(D.status_pill("ĐẠT"))
            self.assertEqual(D.h("div", None, D.val("1,785.11", "T2"))["k"], ["1,785.11"])

    def test_live_tags(self):
        with D.use_mode("live", "2026-09-27"):
            t = D.tier("FACT-T2", "2026-09-25")
            self.assertEqual(t["k"], ["T2·25/09"])
            self.assertEqual((t["s"]["fontSize"], t["s"]["letterSpacing"], t["s"]["marginLeft"], t["s"]["color"]),
                             (7, ".05em", 3, "#5b8db8"))
            self.assertEqual(t["s"]["fontFamily"], D.F_MONO)
            self.assertEqual(D.tier("e")["k"], ["E"])
            self.assertEqual(D.tier("UNVERIFIED", "09/06")["k"], ["U·09/06"])
            self.assertEqual(D.tier("T2", "2024-04-01")["k"], ["T2·01/04/24"], "khác năm hiện hành → in năm")
            self.assertEqual(D.tier("SS-T3")["s"]["color"], "#caa75c")
            self.assertEqual(text_of(D.tier("CẦN DATA")), "[CẦN DATA]")
            with self.assertRaises(ValueError):
                D.norm_tier("FACT-T9")
            u = D.upd_mark()
            self.assertEqual((u["k"], u["s"]["fontSize"], u["s"]["color"], u["s"]["marginLeft"]),
                             (["↻27/09"], 8, D.C.ochre, 4))
            self.assertEqual(D.v21_mark()["k"], ["V21·12/05"])
            self.assertEqual(D.v21_mark()["s"]["color"], "#5a564d")
            c = D.can_data("CN/TC sau 08/05")
            self.assertEqual(text_of(c), "[CẦN DATA — CN/TC sau 08/05]")
            self.assertEqual((c["s"]["color"], c["s"]["fontWeight"]), ("#c5392f", 700))
            # không ngắt giữa '[CẦN' và 'DATA' (final_check §6.2 #1); lý do dài vẫn xuống dòng được
            self.assertNotIn("whiteSpace", c["s"])
            self.assertEqual((c["k"][0]["s"], c["k"][0]["k"]), ({"whiteSpace": "nowrap"}, ["[CẦN DATA"]))
            plain = D.can_data()
            self.assertEqual((plain["k"], plain["s"]["whiteSpace"]), (["[CẦN DATA]"], "nowrap"))
            self.assertEqual(D.tier("CẦN DATA")["s"]["whiteSpace"], "nowrap")
            p = D.status_pill("bị bác")
            self.assertEqual((text_of(p), p["s"]["border"]), ("BỊ BÁC", "1px solid #c5392f"))
            self.assertEqual(D.status_pill("HẾT HẠN")["s"]["color"], "#5a564d")
            self.assertEqual(D.val("x", "CẦN DATA")[0]["k"], ["[CẦN DATA]"])
            tree = D.h("div", None, D.val("1,785.11", "T2", "2026-09-25"), D.tier("E"), D.can_data(), D.upd_mark(),
                       D.v21_mark())
            _, st = D.finalize(tree)
            self.assertEqual(st["tiers"], {"FACT-T2": 1, "EST": 1})
            self.assertEqual((st["can_data"], st["upd"], st["v21"]), (1, 1, 1))


# ── Shell + atom ───────────────────────────────────────────────────────────

GEX_FLOW = {"px": 26967, "perf60": 83.2, "ca60": -45.4, "to60": 52.8, "td60": 26.4, "nn60": -33.7, "sig": "BULL",
            "date": "2026-04-29"}


class TestShellAtoms(unittest.TestCase):
    def setUp(self):
        D.configure("v21", "2026-09-27")

    def tearDown(self):
        D.configure("live")

    def test_section(self):
        s = S.Section("Tiêu đề", "con", sub="SUB")
        head, body = s["k"]
        self.assertEqual(s["s"], {"marginBottom": 32})
        self.assertEqual(head["s"]["borderBottom"], "1px solid #26242c")
        bar, h2, sub = head["k"]
        self.assertEqual(bar["s"], {"width": 4, "height": 24, "background": "#caa75c"})
        self.assertEqual((h2["t"], h2["s"]["fontSize"], h2["s"]["letterSpacing"]), ("h2", 22, "-0.01em"))
        self.assertEqual(sub["s"]["marginLeft"], "auto")
        self.assertEqual(body["k"], ["con"])
        self.assertEqual(len(S.Section("T", accent="#a78bfa")["k"][0]["k"]), 2, "không sub → không div sub")
        self.assertEqual(S.Section("T", accent="#a78bfa")["k"][0]["k"][0]["s"]["background"], "#a78bfa")

    def test_card_stat_pill(self):
        self.assertEqual(S.Card("x")["s"]["borderLeft"], "1px solid #26242c")
        c = S.Card("x", accent="#caa75c", padding=24)
        self.assertEqual((c["s"]["borderLeft"], c["s"]["padding"]), ("3px solid #caa75c", 24))
        self.assertEqual(list(c["s"])[:4], ["background", "padding", "border", "borderLeft"])
        st = S.Stat("GIÁ", "26,967", sub="2026-04-29", color="#caa75c", big=True)
        self.assertEqual(st["s"], {"flex": "1 1 160px", "minWidth": 140})
        self.assertEqual((st["k"][1]["s"]["fontSize"], st["k"][1]["s"]["color"]), (26, "#caa75c"))
        self.assertEqual(len(S.Stat("A", 1)["k"]), 2)
        p = S.Pill("AVOID", dim=True)
        self.assertEqual((p["s"]["color"], p["s"]["border"]), ("#5a564d", "1px solid #26242c"))
        self.assertEqual(S.Pill("X")["s"]["border"], "1px solid #26242c")

    def test_flowbar_widths_match_v8(self):
        want = {-45.4: "13.62%", 52.8: "15.839999999999998%", 26.4: "7.919999999999999%",
                -33.7: "10.110000000000001%", 168.6: "50%", 8.8: "2.64%", -29: "8.7%"}
        for v, w in want.items():
            fill = S.FlowBar("x", v, "#000")["k"][1]["k"][0]
            self.assertEqual(fill["s"]["width"], w, v)
            self.assertEqual(fill["s"]["left" if v < 0 else "right"], "auto")

    def test_flowsignal_v21(self):
        fs = S.FlowSignal(GEX_FLOW)
        head, *bars, foot = fs["k"]
        self.assertEqual(text_of(head), "FLOW 60D · FIINTRADE ≤08/05 · NGƯỜIQUANSÁT ≥09/05BULL")
        self.assertEqual(head["k"][1]["s"]["color"], D.C.forest)
        self.assertEqual([text_of(b["k"][2]) for b in bars], ["-45.4M", "+52.8M", "+26.4M", "-33.7M"])
        self.assertEqual(bars[0]["k"][1]["k"][0]["s"]["background"], D.C.vermillion)
        self.assertEqual(foot["k"][0], "Tham chiếu cuối: 2026-04-29 · Giá 26,967 · Δ60d ")
        self.assertEqual(text_of(foot["k"][1]), "+83.2%")
        zero = S.FlowSignal({**GEX_FLOW, "td60": 0})["k"][3]
        self.assertEqual(text_of(zero["k"][2]), "+0.0M")
        self.assertEqual(zero["k"][2]["s"]["color"], D.C.forest)
        self.assertEqual(zero["k"][1]["k"][0]["s"]["background"], D.C.vermillion, "thanh theo >0 (bất thường gốc)")

    def test_flowsignal_live_missing(self):
        with D.use_mode("live", "2026-09-27"):
            fl = {"sig": None, "ca60": None, "to60": None, "td60": 12.5, "nn60": -3.2, "date": "2026-09-25",
                  "px": 24000, "perf60": None}
            fs = S.FlowSignal(fl, head="FLOW 60 PHIÊN · VIETCAP ≥09/05", tiers={"td60": "T2", "nn60": ("T2", "25/09")})
            t = text_of(fs)
            self.assertIn("[CẦN DATA]", t)
            self.assertIn("+12.5MT2", t)
            self.assertIn("-3.2MT2·25/09", t)
            self.assertEqual(len(fs["k"][1]["k"][1]["k"]), 1, "thiếu số → không vẽ thanh, chỉ vạch giữa")

    def test_built_label_and_tabs(self):
        self.assertEqual(S.built_label(date(2026, 5, 8)), "08 · V · MMXXVI")
        self.assertEqual(S.built_label(date(2026, 9, 27)), "27 · IX · MMXXVI")
        tabs, why = S.tabs_from_v21({})
        self.assertEqual(tabs, list(S.TABS_V21))
        self.assertIsNotNone(why)
        good = {"TABS": [{"id": i, "label": l, "icon": c} for i, l, c in S.TABS_V21]}
        self.assertEqual(S.tabs_from_v21(good), (list(S.TABS_V21), None))
        self.assertIsNotNone(S.tabs_from_v21({"TABS": good["TABS"][:17]})[1])

    def test_shell_v21(self):
        ctx = M.Ctx("v21", date(2026, 9, 27), list(S.TABS_V21))
        body = S.build_shell(ctx, list(S.TABS_V21))
        self.assertEqual(body["t"], "body")
        self.assertEqual(body["s"], {"background": "#0a0a0c", "color": "#e8e6e0",
                                     "fontFamily": "'Source Serif 4', Georgia, serif", "margin": 0})
        root = find_key(body, "root")
        self.assertEqual(root["scope"], ["tab"])
        self.assertIn("radial-gradient(at 0% 0%, #1f1d2430 0%, transparent 50%)", root["s"]["backgroundImage"])
        hdr = text_of(find_key(body, "header"))
        self.assertIn("Bản Đồ Chaebol & VN30 — Tháng 5, 2026", hdr)
        self.assertIn("08 · V · MMXXVIVN-Index ~1,265 · USD/VND 26,300", hdr)
        self.assertIn("I. TOÀN VŨ điểm đảo chiều cổ đông·II. PHÚ SSI VWAP cụm", hdr)
        self.assertIsNone(find_key(body, "cong"))
        btns = [n for n in walk(body) if isinstance(n, dict) and n.get("t") == "button"]
        self.assertEqual([b["on"]["set"]["tab"] for b in btns], TAB_IDS)
        self.assertEqual(text_of(btns[12]), "§09 · CLAIMS C01-C20 + CHANGELOG")
        self.assertEqual(btns[0]["var"][0], {"if": {"tab": "vnindex"}, "s": {"color": "#caa75c",
                                                                             "borderBottom": "2px solid #caa75c"}})
        main = find_key(body, "main")
        self.assertEqual(main["s"], {"maxWidth": 1480, "margin": "0 auto", "padding": "24px 28px 64px"})
        self.assertEqual(main["k"], [{"t": "slot", "id": "main"}])
        add = find_key(body, "addendum")
        trs = [n for n in walk(add) if isinstance(n, dict) and n.get("t") == "tr"]
        self.assertEqual(len(trs), 21)
        self.assertEqual(text_of(trs[14]), "C14FPT capitulate — NN −173.7M🔵 REVIEW / dấu hiệu đáyGiá 75K = ĐÚNG vùng "
                         "base 75-80K dự báo. NN phiên 05/06 +126 tỷ (MUA ròng) → có dấu hiệu flip như falsifyIf; có "
                         "thể đang tạo đáy. Theo dõi sát flow 60d.")
        self.assertNotIn("lưu trữ", text_of(add))
        foot = text_of(find_key(body, "footer"))
        self.assertTrue(foot.startswith("MASTER PLAN V21.29 · ALL-IN-ONE v2 MAX ENRICH"))

    def test_shell_live(self):
        with D.use_mode("live", "2026-09-27"):
            ctx = M.Ctx("live", date(2026, 9, 27), list(S.TABS_V21))
            ctx.live_info = {"vnindex": {"value": 1785.11, "date": "2026-09-25", "tier": "FACT-T2"},
                             "usdvnd": None,
                             "cong": {"text": "CỔNG: [tiền rẻ] · chủ thể cần thị trường · playbook A",
                                      "as_of": "2026-09-26"}}
            body = S.build_shell(ctx, list(S.TABS_V21))
            built = text_of(find_key(body, "built"))
            self.assertEqual(built, "BUILT27 · IX · MMXXVIVN-Index 1,785.11T2·25/09 · USD/VND [CẦN DATA]")
            cong = find_key(body, "cong")
            self.assertTrue(text_of(cong).startswith(
                "CỔNG: [tiền rẻ] · chủ thể cần thị trường · playbook A · as of 26/09/2026 · Nhãn bậc: T1 CBTT/BCTC"))
            self.assertEqual(cong["s"]["color"], D.C.gold)
            self.assertTrue(text_of(cong).endswith("· U chưa xác minh"))
            items = [n for n in walk(cong) if isinstance(n, dict) and (n.get("s") or {}).get("whiteSpace") == "nowrap"]
            self.assertEqual([text_of(n) for n in items], ["T1 CBTT/BCTC", "T2 vendor", "T3 sell-side/Toàn Vũ",
                                                           "E ước", "U chưa xác minh"])
            ctx.live_info["cong"] ={"text": "CỔNG: [CẦN DATA — M2] · không kết luận per-mã"}
            cong2 = find_key(S.build_shell(ctx, list(S.TABS_V21)), "cong")
            self.assertEqual(cong2["s"]["color"], D.C.vermillion)
            self.assertIn("Tháng 9, 2026", text_of(find_key(body, "header")))
            self.assertIn("lưu trữ 09/06", text_of(find_key(body, "addendum")))


# ── Kiểm kê state: tập options = giá trị thô JSX trong v21_const ─────────────


class TestCoverageOptions(unittest.TestCase):
    V21_MINI = {
        "SUB_TABS_CHAEBOL": [{"id": "phase_info", "label": "★ 01 Phase Infographic"}, {"id": "chart", "label": "02"}],
        "ScreenerTab.jsx@L6301": [{"v": "ALL", "l": "Tất cả"}, {"v": "CHAEBOL_FRIENDLY", "l": "Thân hữu"}],
        "CHAEBOL_GROUPS": [{"id": "tuanmuot", "tickers": [{"tk": "GEX"}, {"tk": "GEE"}]}, {"id": "hỏng"}],
        "DEEP_INSIGHT_24": {"Vingroup": {}, "Sovico": {}},
        "ResearchStackPanel.cats": "sai dạng",
    }

    def test_expected_options(self):
        o = M.expected_options(self.V21_MINI)
        self.assertEqual(o["codong.sub"], ["phase_info", "chart"])
        self.assertEqual(o["scr.chaebol"], ["ALL", "CHAEBOL_FRIENDLY"])
        self.assertEqual(o["grp.tuanmuot.tk"], ["GEX", "GEE"])
        self.assertEqual(o["d24.sel"], ["Vingroup", "Sovico"])
        self.assertEqual(o["scr.dir"], ["desc", "asc"])
        self.assertNotIn("rs.cat", o)
        self.assertEqual(M.expected_options(None), {"scr.dir": ["desc", "asc"]})

    def test_coverage_checks_values_and_group_default(self):
        states = [{"key": "scr.chaebol", "default": "ALL", "options": ["ALL", "Thân hữu"]},
                  {"key": "grp.tuanmuot.tk", "default": "GEE", "options": ["GEX", "GEE"]}]
        cov = M._coverage(states, {"screener", "tuanmuot"}, self.V21_MINI)
        self.assertIn("scr.dir", cov["missing"])
        self.assertTrue(any(x.startswith("scr.chaebol: options lệch") and "CHAEBOL_FRIENDLY" in x and "Thân hữu" in x
                            for x in cov["mismatch"]), cov)
        self.assertIn("grp.tuanmuot.tk: mặc định 'GEE' ≠ 'GEX'", cov["mismatch"])
        ok = [{"key": "grp.tuanmuot.tk", "default": "GEX", "options": ["GEE", "GEX"]}]
        self.assertEqual(M._coverage(ok, {"tuanmuot"}, self.V21_MINI)["mismatch"],
                         ["grp.tuanmuot.tk: 2 lựa chọn ≠ 6"], "thứ tự options không quan trọng; chỉ còn lệch số đếm")

    def test_real_v21_counts(self):
        p = M.bridge_dir() / "data" / "chaebol_map" / "v21_const.json"
        if not p.is_file():
            self.skipTest("không có v21_const.json thật")
        o = M.expected_options(json.loads(p.read_text("utf-8")))
        for key, (_tab, default, n) in M.EXPECTED_STATES.items():
            if key == "scr.sort":
                continue
            self.assertIn(key, o)
            if n is not None:
                self.assertEqual(len(o[key]), n, key)
            if default is not None:
                self.assertEqual(o[key][0] if key != "d24.sel" else "Vingroup", default, key)
        self.assertIn("CHAEBOL_FRIENDLY", o["scr.chaebol"])
        self.assertEqual(o["codong.sub"][:2], ["phase_info", "chart"])


# ── CLI ────────────────────────────────────────────────────────────────────


class CliBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="chb_test_"))
        self.sysdir = self.tmp / "sys"
        self.sysdir.mkdir()
        self.env = {**os.environ, "CHB_SYSTEM_DIR": str(self.sysdir), "CHB_TODAY": "2026-09-27"}
        self.env.pop("CHB_STATE_DIR", None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, *args, python=None, env=None):
        p = subprocess.run([python or sys.executable, "-c", GUARD, str(SCRIPT), *args], env=env or self.env,
                           capture_output=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        lines = p.stdout.decode("utf-8").splitlines()
        self.assertEqual(len(lines), 1, "stdout phải đúng MỘT dòng JSON")
        return json.loads(lines[0])

    def inproc(self, *args):
        buf, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.env, clear=True), redirect_stdout(buf), redirect_stderr(err):
            self.assertEqual(M.main(["chaebol_map.py", *args]), 0)
        return json.loads(buf.getvalue())


class TestCli(CliBase):
    def test_build_v21_placeholders(self):
        out = self.tmp / "state"
        res = self.cli("build", "--mode", "v21", "--out", str(out))
        self.assertNotIn("error", res)
        self.assertEqual(res["schema"], "chaebol_map/1")
        m = res["manifest"]
        build = Path(res["build"])
        self.assertTrue(build.is_dir() and build.parent == out.resolve() / "builds")
        for k in ("schema", "mode", "generated", "data_to", "source_md5", "render_mode", "cong", "warnings", "tabs",
                  "shell", "inc", "inventory", "stats", "csv"):
            self.assertIn(k, m)
        self.assertEqual((m["mode"], m["render_mode"], m["cong"], m["data_to"]),
                         ("v21", "as_intended", None, "2026-05-08"))
        self.assertEqual(m["source_md5"], "4f647f7a458e4c249ae05d4407f8ba70")
        self.assertEqual([t["id"] for t in m["tabs"]], TAB_IDS)
        self.assertEqual(m["inventory"]["tabs"], TAB_IDS)
        st0 = m["inventory"]["states"][0]
        self.assertEqual((st0["key"], st0["default"], st0["options"]), ("tab", "vnindex", TAB_IDS))
        self.assertEqual(json.loads((build / "manifest.json").read_text("utf-8")), m)
        cur = json.loads((out / "current.json").read_text("utf-8"))
        self.assertEqual((cur["build"], cur["manifest"]), (str(build), m))
        shell = json.loads((build / "shell.json").read_text("utf-8"))
        self.assertEqual(set(shell), {"cls", "root"})
        self.assertIn({"t": "slot", "id": "main"}, list(walk(shell["root"])))
        for t in m["tabs"]:
            doc = json.loads((build / t["file"]).read_text("utf-8"))
            self.assertEqual(set(doc), {"cls", "root"})
            self.assertIn(t["status"], ("ok", "placeholder", "error"))
            mod = M.TAB_BUILDERS[t["id"]][0]
            if not (HERE / (mod + ".py")).exists():
                self.assertEqual(t["status"], "placeholder")
                self.assertIn("[chưa dựng] · " + t["label"], text_of(doc["root"]))
        self.assertGreater(m["stats"]["nodes"], 300)
        self.assertEqual(m["stats"]["tiers"], {}, "mode v21 không có nhãn bậc")
        if all(t["status"] == "placeholder" for t in m["tabs"]):
            self.assertEqual(m["csv"], {"file": "export.csv", "rows": 0})
            self.assertEqual((build / "export.csv").read_text("utf-8-sig"), "tab\n")

    def test_build_order_suffix(self):
        names = ["20260927-101805-10", "20260927-101805", "20260927-101805-2", "20260926-235959"]
        self.assertEqual(sorted(names, key=M._build_order),
                         ["20260926-235959", "20260927-101805", "20260927-101805-2", "20260927-101805-10"])

    def test_build_live_without_data(self):
        res = self.cli("build", "--out", str(self.tmp / "state"))
        self.assertNotIn("error", res)
        m = res["manifest"]
        self.assertEqual(m["mode"], "live")
        self.assertIn("[CẦN DATA", m["cong"]["text"])
        shell = json.loads((Path(res["build"]) / "shell.json").read_text("utf-8"))
        self.assertIn("CỔNG: [CẦN DATA", text_of(find_key(shell["root"], "cong")))
        self.assertIn("27 · IX · MMXXVI", text_of(find_key(shell["root"], "built")))
        self.assertTrue(any("dossier" in w for w in m["warnings"]))

    def test_status_and_errors(self):
        empty = self.tmp / "empty"
        err = self.cli("status", "--out", str(empty))
        self.assertIn("error", err)
        self.assertIn("build", err["error"])
        self.assertIn("error", self.cli("frobnicate"))
        self.assertIn("error", self.cli("build", "--mode", "x"))
        self.assertIn("error", self.cli("build", "--out"))
        self.assertIn("error", self.cli("status", "--bogus", "1"))
        env = {**self.env, "CHB_TODAY": "27/09/2026"}
        self.assertIn("CHB_TODAY", self.cli("build", "--out", str(empty), env=env)["error"])
        state = self.tmp / "st"
        env2 = {**self.env, "CHB_STATE_DIR": str(state)}
        b = self.cli("build", "--mode", "v21", env=env2)
        self.assertTrue(b["build"].startswith(str(state.resolve())))
        s = self.cli("status", env=env2)
        self.assertEqual((s["build"], s["manifest"]), (b["build"], b["manifest"]))

    def test_inventory_writes_nothing(self):
        env = {**self.env, "CHB_STATE_DIR": str(self.tmp / "never")}
        res = self.cli("inventory", "--mode", "v21", env=env)
        self.assertEqual(res["inventory"]["tabs"], TAB_IDS)
        self.assertFalse((self.tmp / "never").exists())

    def test_keep_three_builds(self):
        out = self.tmp / "state"
        names = []
        for _ in range(4):
            res = self.inproc("build", "--mode", "v21", "--out", str(out))
            names.append(Path(res["build"]).name)
        kept = sorted(p.name for p in (out / "builds").iterdir())
        self.assertEqual(kept, sorted(names)[-3:])
        self.assertEqual(json.loads((out / "current.json").read_text("utf-8"))["build"], res["build"])
        self.assertEqual(len(set(names)), 4, "hai build cùng giây không được đè nhau")

    def test_other_interpreter(self):
        cands = [p for p in (VENV_PY, Path(shutil.which("python3") or "")) if p and p.is_file()]
        mine = os.path.realpath(sys.executable)
        others = [p for p in cands if os.path.realpath(p) != mine]
        if not others:
            self.skipTest("không có trình thông dịch thứ hai")
        for py in others:
            res = self.cli("build", "--mode", "v21", "--out", str(self.tmp / ("o_" + py.parent.parent.name)),
                           python=str(py))
            self.assertNotIn("error", res, str(py))
            self.assertEqual(len(res["manifest"]["tabs"]), 18)


FAKE_TAB = textwrap.dedent('''
    import chaebol_map_dom as D
    from chaebol_map_shell import Section, Card

    def build_vnindex(ctx):
        assert ctx.mode in ("v21", "live") and ctx["today"].isoformat() == "2026-09-27"
        ctx.warn("cảnh báo thử")
        rows = [D.h("tr", None, D.h("td", {"padding": "9px 10px"}, tk), grp="x.rows", sk={"tk": tk},
                    if_={"x.f": ["ALL", tk]}) for tk in ("VIC", "GEX")]
        root = D.h("div", None, Section("Thử", Card(D.h("div", None, count={"grp": "x.rows", "fmt": "Showing {n}/2"}),
                   D.h("table", None, D.h("tbody", None, *rows, sort={"key": "x.s", "dir": "x.d"})),
                   D.h("div", None, inc="x/VIC"))), scope=["x.f"])
        return {"root": root,
                "states": [{"key": "x.f", "default": "ALL", "options": ["ALL", "VIC", "GEX"]},
                           {"key": "x.s", "default": "perf", "options": ["tk"]},
                           {"key": "x.d", "default": "desc", "options": ["desc", "asc"]}],
                "inc": {"x/VIC": D.h("div", {"padding": "9px 10px"}, "nhánh VIC")},
                "csv": [{"ma": "VIC", "gia": 232000}, {"ma": "GEX", "gia": 24000}]}

    def build_vn30(ctx):
        raise RuntimeError("hỏng có chủ ý")

    def build_screener(ctx):
        print("print lạc của builder — phải sang stderr")
        assert ctx.data is None or ctx.live, "mode v21 không được có lớp số sống"
        return D.h("div", None, "không state")
''')


class TestTabBuilders(CliBase):
    def setUp(self):
        super().setUp()
        self.mod_dir = self.tmp / "mods"
        self.mod_dir.mkdir()
        (self.mod_dir / "chb_fake_tabmod.py").write_text(FAKE_TAB, "utf-8")
        sys.path.insert(0, str(self.mod_dir))
        self.patch = mock.patch.dict(M.TAB_BUILDERS, {
            "vnindex": ("chb_fake_tabmod", "build_vnindex"), "vn30": ("chb_fake_tabmod", "build_vn30"),
            "screener": ("chb_fake_tabmod", "build_screener"), "codong": ("chb_fake_tabmod", "build_missing")})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        sys.path.remove(str(self.mod_dir))
        sys.modules.pop("chb_fake_tabmod", None)
        super().tearDown()

    def test_contract(self):
        res = self.inproc("build", "--mode", "v21", "--out", str(self.tmp / "state"))
        self.assertNotIn("error", res)
        m, build = res["manifest"], Path(res["build"])
        status = {t["id"]: t["status"] for t in m["tabs"]}
        self.assertEqual((status["vnindex"], status["vn30"], status["screener"], status["codong"]),
                         ("ok", "error", "ok", "placeholder"))
        self.assertTrue(any("[vnindex] cảnh báo thử" == w for w in m["warnings"]))
        self.assertTrue(any("[vn30]" in w and "hỏng có chủ ý" in w for w in m["warnings"]))
        vn30 = json.loads((build / "tab_vn30.json").read_text("utf-8"))
        self.assertIn("[lỗi dựng]", text_of(vn30["root"]))
        codong = json.loads((build / "tab_codong.json").read_text("utf-8"))
        self.assertIn("thiếu hàm build_missing", text_of(codong["root"]))
        vni = json.loads((build / "tab_vnindex.json").read_text("utf-8"))
        self.assertEqual(vni["root"]["scope"], ["x.f", "x.s", "x.d"])
        self.assertIn({"padding": "9px 10px"}, vni["cls"].values())
        states = {s["key"]: s for s in m["inventory"]["states"]}
        self.assertEqual(states["x.f"]["tab"], "vnindex")
        self.assertEqual(m["inc"], {"x/VIC": "inc/x_VIC.json"})
        self.assertEqual(m["inventory"]["inc"], ["x/VIC"])
        inc = json.loads((build / "inc" / "x_VIC.json").read_text("utf-8"))
        self.assertEqual(text_of(inc["root"]), "nhánh VIC")
        self.assertEqual(inc["cls"], {}, "class của tệp inc tính riêng: một lần dùng → inline")
        self.assertTrue(any("x.s" in w and "không nằm trong options" in w for w in m["warnings"]))
        self.assertEqual(m["csv"], {"file": "export.csv", "rows": 2})
        csv_text = (build / "export.csv").read_text("utf-8-sig")
        self.assertEqual(csv_text.splitlines(), ["tab,ma,gia", "vnindex,VIC,232000", "vnindex,GEX,24000"])
        self.assertEqual(m["inventory"]["coverage"]["missing"],
                         ["scr.sort", "scr.dir", "scr.phase", "scr.sig", "scr.chaebol"])
        self.assertIn("audit", m["stats"]["per_tab"])


class TestNestedScope(unittest.TestCase):
    """final_check §6.2 #8 (vá 27/09): khoá có scope lồng (codong.sub trên nút Deep-dive trong inc) KHÔNG được gắn
    lên gốc tab — nếu không, gốc luôn được render nên codong.sub không bao giờ reset khi qua mã không có Deep-dive."""

    STATES = [{"key": "codong.tk", "default": "VIC", "options": ["VIC", "GEX", "VNM"]},
              {"key": "codong.sub", "default": "phase_info", "options": ["phase_info", "chart"]}]

    def norm(self, root, inc=None):
        ctx = M.Ctx("live", date(2026, 9, 27), [])
        with D.use_mode("live", "2026-09-27"):
            return M.normalize_result("codong", {"root": root, "states": self.STATES, "inc": inc or {}}, ctx), ctx

    def test_scope_in_inc_stays_off_root(self):
        deep = D.h("section", None, "Deep-dive", scope=["codong.sub"], key="deep10_VIC")
        inc = {"codong/VIC": D.h("div", None, D.h("div", None, deep)), "codong/VNM": D.h("div", None, "không Deep-dive")}
        root = D.h("div", None, D.h("div", None, inc="codong/VIC", if_={"codong.tk": "VIC"}),
                   D.h("div", None, inc="codong/VNM", if_={"codong.tk": "VNM"}))
        out, ctx = self.norm(root, inc)
        self.assertEqual(out["root"]["scope"], ["codong.tk"])
        self.assertEqual(out["inc"]["codong/VIC"]["k"][0]["k"][0]["scope"], ["codong.sub"])
        self.assertNotIn("scope", root, "không sửa cây đầu vào")
        self.assertEqual(ctx.warnings, [])

    def test_scope_on_inc_root_and_inside_tab_tree(self):
        inc = {"codong/VIC": D.h("div", None, "Deep-dive", scope=["codong.sub"])}     # scope ngay trên gốc inc
        out, _ = self.norm(D.h("div", None, D.h("div", None, inc="codong/VIC")), inc)
        self.assertEqual(out["root"]["scope"], ["codong.tk"])
        nested = D.h("div", None, D.h("div", None, D.h("span", None, "x", scope=["codong.sub"])))   # lồng trong tab
        out, _ = self.norm(nested)
        self.assertEqual(out["root"]["scope"], ["codong.tk"])

    def test_root_scope_kept_and_no_nested(self):
        out, _ = self.norm(D.h("div", None, "x", scope=["codong.sub"]))                # gốc tự khai: không phải lồng
        self.assertEqual(out["root"]["scope"], ["codong.sub", "codong.tk"])
        out, _ = self.norm(D.h("div", None, "không scope lồng"))
        self.assertEqual(out["root"]["scope"], ["codong.tk", "codong.sub"])

    @unittest.skipUnless(REAL_V21.is_file(), "chưa có v21_const.json")
    def test_real_codong_builder(self):
        ctx = M.Ctx("v21", date(2026, 9, 27), [])
        ctx.v21 = json.loads(REAL_V21.read_text("utf-8"))
        with D.use_mode("v21", "2026-09-27"):
            res, status = M.run_tab("codong", "CẤU TRÚC CỔ ĐÔNG", ctx)
        self.assertEqual(status, "ok", ctx.warnings)
        self.assertEqual(res["root"]["scope"], ["codong.tk"], "gốc tab chỉ mang codong.tk")
        scoped = lambda tk: [n["scope"] for n in walk(res["inc"]["codong/" + tk])  # noqa: E731
                             if isinstance(n, dict) and n.get("scope")]
        self.assertEqual(scoped("VIC"), [["codong.sub"]], "codong.sub sống trên nút Deep-dive trong inc")
        self.assertEqual(scoped("VNM"), [], "mã NQ79 không có Deep-dive → codong.sub về mặc định khi chọn")


if __name__ == "__main__":
    unittest.main()
