#!/usr/bin/env python3
"""Unit tests cho chart codong v2 (chaebol_map_tab_codong_v2_chart + _svg), spec codong_v2_spec.md §6 và §11.3.

Chạy (cả hai trình thông dịch):
    python3.14 -m pytest -q scripts/test_chaebol_map_codong2_chart.py
    ~/Library/Application\\ Support/com.fincept.terminal/venv-numpy2/bin/python -m pytest -q \\
        scripts/test_chaebol_map_codong2_chart.py

Phần lớn test dùng chuỗi TỔNG HỢP tất định (không kho). Lớp RealStore chạy một lần trên kho thật (chỉ đọc) cho VIC, REE,
GEL: ưu tiên chaebol_map_data_codong2_gia (P2) nếu đã có, không thì dựng chuỗi từ chaebol_map_data_gia.weekly_ohlcv cũ;
bỏ qua khi thiếu price-history. Mạng bị chặn trong cả tệp.
"""
from __future__ import annotations

import ast
import math
import os
import re
import socket
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("CHB_TODAY", "2026-10-05")

import chaebol_map_dom as D  # noqa: E402
import chaebol_map_tab_codong_v2_chart as CH  # noqa: E402

_REAL = {}
VC_DIR = Path(os.environ.get("CHB_SYSTEM_DIR", str(Path.home() / "SECOND BRAIN-OBSIDIAN" / "_System"))) \
    / "fincept_bridge" / "state" / "vc_lk"
EM_DASH, EN_DASH = chr(0x2014), chr(0x2013)
FFT_WARN = ("§6.4: proxy FFT đã bỏ sót phân phối ở FPT, VCB, MBB, HPG, CTG; FFT im lặng không có nghĩa là không "
            "phân phối")


def setUpModule():
    def blocked(*a, **k):
        raise RuntimeError("mạng bị chặn trong test chaebol_map")
    for name in ("socket", "create_connection", "getaddrinfo"):
        _REAL[name] = getattr(socket, name)
        setattr(socket, name, blocked)


def tearDownModule():
    for name, fn in _REAL.items():
        setattr(socket, name, fn)


# ── Chuỗi tổng hợp tất định ─────────────────────────────────────────────────


class _Rng:
    """LCG 32-bit: cùng hạt → cùng dãy trên mọi phiên bản Python."""

    def __init__(self, seed: int):
        self.x = seed & 0xFFFFFFFF

    def u(self) -> float:
        self.x = (1664525 * self.x + 1013904223) & 0xFFFFFFFF
        return self.x / 2 ** 32


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return D.js_sum(vals) / len(vals) if vals else None


def synth_series(n: int, start: str = "2007-09-17", seed: int = 7, ts_start: str | None = "2010-12-21",
                 fft_weeks: int = 636, markers: bool = True, warn: bool = False) -> dict:
    """Chuỗi n tuần dày đặc nhiễu (ca xấu cho ngân sách byte): mọi cột có số, có chỗ trống None rải rác."""
    rng, d0 = _Rng(seed), date.fromisoformat(start)
    rows, c, idx, nn, td = [], 20_000.0, 1000.0, 0.0, None
    for i in range(n):
        w = d0 + timedelta(days=7 * i)
        o = c
        c = max(500.0, c * math.exp(0.09 * (rng.u() - 0.497)))
        idx = idx * math.exp(0.05 * (rng.u() - 0.5))
        nn += (rng.u() - 0.5) * 2e6
        if i >= n - 400:
            td = (td or 0.0) + (rng.u() - 0.5) * 4e10
        rows.append({"w": w.isoformat(), "we": (w + timedelta(days=4)).isoformat(), "o": o, "c": c,
                     "h": max(o, c) * (1 + 0.03 * rng.u()), "l": min(o, c) * (1 - 0.03 * rng.u()),
                     "vol": 1e6 * (0.2 + 3 * rng.u()), "dvol": 2e6 * rng.u() if i % 3 == 0 else None,
                     "fo": None if i % 53 == 7 else 25 - 20 * i / n + rng.u(), "fol": 49.0 if i > 100 else None,
                     "nn_cum": nn, "td_cum": td, "nn_w": (rng.u() - 0.5) * 6e10,
                     "td_w": (rng.u() - 0.5) * 3e10 if td is not None else None, "rs": c / idx,
                     "pre": bool(ts_start and w.isoformat() < ts_start)})
    for k, span in (("v6", 26), ("v12", 52), ("v24", 104)):
        for i, r in enumerate(rows):
            r[k] = _avg([x["c"] for x in rows[max(0, i - span + 1):i + 1]])
    for i, r in enumerate(rows):
        on = i >= n - fft_weeks
        r["fw"] = 50 + 30 * (rng.u() - 0.5) if on else None
        r["ma4"] = _avg([x["fw"] for x in rows[max(0, i - 3):i + 1]]) if on else None
        r["p10"], r["p90"] = (38.0, 62.0) if on else (None, None)
    return {"tk": "SYN", "weeks": rows, "markers": synth_markers(rows) if markers else [], "ts_start": ts_start,
            "fft_note": CH.FFT_NOTE, "fft_warn": FFT_WARN if warn else None}


def synth_markers(rows: list) -> list:
    kinds = CH.MARKER_KINDS
    out = []
    for j in range(40):
        r = rows[(j * 37 + 11) % len(rows)]
        out.append({"date": r["we"], "kind": kinds[j % len(kinds)], "size": round(0.1 + (j * 7 % 13) * 0.37, 2),
                    "label": "chủ thể %d" % j, "ref": "row%d" % j})
    out.append({"date": rows[5]["w"], "kind": "la_lung", "size": 99, "label": "x", "ref": "x"})
    out.append({"date": "1990-01-01", "kind": "nb_mua", "size": 50, "label": "ngoài khung", "ref": "old"})
    return out


# ── Tiện ích đọc cây ────────────────────────────────────────────────────────


def walk(node):
    yield node
    if isinstance(node, dict):
        for ch in node.get("k", ()):
            yield from walk(ch)


def by_key(svg, prefix):
    return [n for n in walk(svg) if isinstance(n, dict) and str(n.get("key", "")).startswith(prefix)]


def texts(svg):
    return [n for n in walk(svg) if isinstance(n, dict) and n.get("t") == "text"]


def text_of(n):
    return "".join(ch for ch in n.get("k", ()) if isinstance(ch, str))


_NUM = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)")


def parse_path(d: str) -> list:
    """Đọc path như engine (ChbSvgPath): trả list đoạn con, mỗi đoạn = list điểm tuyệt đối (x, y) theo phần mười px."""
    toks = re.findall(r"[MmLlHhVvZzAa]|" + _NUM.pattern, d)
    subs, cur, cmd, i = [], (0, 0), None, 0
    start = cur
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd, i = t, i + 1
            if cmd in "Zz":
                subs[-1].append(start)
                cur = start
            continue
        n = {"M": 2, "m": 2, "L": 2, "l": 2, "H": 1, "h": 1, "V": 1, "v": 1, "A": 7, "a": 7}[cmd]
        a = [round(float(x) * 10) for x in toks[i:i + n]]
        i += n
        if cmd in "Mm":
            cur = (a[0], a[1]) if cmd == "M" else (cur[0] + a[0], cur[1] + a[1])
            start = cur
            subs.append([cur])
            cmd = "L" if cmd == "M" else "l"
            continue
        if cmd == "l":
            cur = (cur[0] + a[0], cur[1] + a[1])
        elif cmd == "L":
            cur = (a[0], a[1])
        elif cmd in "hH":
            cur = (cur[0] + a[0] if cmd == "h" else a[0], cur[1])
        elif cmd in "vV":
            cur = (cur[0], cur[1] + a[0] if cmd == "v" else a[0])
        elif cmd in "aA":
            cur = (cur[0] + a[5], cur[1] + a[6]) if cmd == "a" else (a[5], a[6])
        subs[-1].append(cur)
    return subs


def tn(v):
    return math.floor(v * 10 + 0.5)


# ── Test: khung, hạ mẫu, vạch ───────────────────────────────────────────────


class Windows(unittest.TestCase):
    def test_window_plan(self):
        self.assertEqual(CH.window_plan(34), {"MAX": "MAX", "5Y": "MAX", "2Y": "MAX"})
        self.assertEqual(CH.window_plan(104), {"MAX": "MAX", "5Y": "MAX", "2Y": "MAX"})
        self.assertEqual(CH.window_plan(166), {"MAX": "MAX", "5Y": "MAX", "2Y": "2Y"})
        self.assertEqual(CH.window_plan(260), {"MAX": "MAX", "5Y": "MAX", "2Y": "2Y"})
        self.assertEqual(CH.window_plan(982), {"MAX": "MAX", "5Y": "5Y", "2Y": "2Y"})

    def test_geometry_constants(self):
        self.assertEqual(CH.VIEW_H, 826)
        self.assertEqual(CH.PLOT_W, 1040)
        self.assertEqual(CH.PANE_Y["price"], (20, 360))
        self.assertEqual(CH.PANE_Y["rs"], (740, 800))

    def test_window_rows_step(self):
        weeks = synth_series(1348, start="2000-07-24", markers=False)["weeks"]
        rows, step = CH.window_rows(weeks, "MAX")
        self.assertEqual((step, len(rows)), (2, 674))
        rows, step = CH.window_rows(weeks[:982], "MAX")
        self.assertEqual((step, len(rows)), (1, 982))
        rows, step = CH.window_rows(weeks, "5Y")
        self.assertEqual((step, len(rows), rows[-1]["w"]), (1, 260, weeks[-1]["w"]))
        rows, step = CH.window_rows(weeks, "2Y")
        self.assertEqual((step, len(rows), rows[0]["w"]), (1, 104, weeks[-104]["w"]))
        with self.assertRaises(ValueError):
            CH.window_rows(weeks, "3Y")

    def test_downsample_rules(self):
        rows = [{"w": "2020-01-06", "we": "2020-01-10", "o": None, "h": 10, "l": 5, "c": 8, "vol": 1, "dvol": None,
                 "fo": 3.0, "nn_w": None, "pre": True},
                {"w": "2020-01-13", "we": "2020-01-17", "o": 8, "h": 12, "l": 7, "c": 11, "vol": 2, "dvol": None,
                 "fo": None, "nn_w": None, "pre": False},
                {"w": "2020-01-20", "we": "2020-01-24", "o": 11, "h": 9, "l": 4, "c": None, "vol": None, "dvol": 5,
                 "fo": None, "nn_w": None, "pre": False}]
        before = [dict(r) for r in rows]
        g = CH.downsample(rows, 3)
        self.assertEqual(len(g), 1)
        g = g[0]
        self.assertEqual((g["w"], g["we"], g["o"], g["h"], g["l"]), ("2020-01-06", "2020-01-24", 8, 12, 4))
        self.assertEqual((g["c"], g["fo"], g["vol"], g["dvol"], g["nn_w"], g["pre"]), (11, 3.0, 3, 5, None, True))
        self.assertEqual(rows, before, "downsample không được sửa đầu vào")
        self.assertEqual([r["w"] for r in CH.downsample(rows, 2)], ["2020-01-06", "2020-01-20"])
        self.assertEqual(CH.downsample(rows, 1), before)

    def test_log_ticks(self):
        for lo, hi in ((8_500, 256_100), (300, 80_000), (20_000, 30_000), (21_000, 23_500), (0.31, 0.37),
                       (12.31, 12.33), (1, 1_000_000), (47_000, 62_000)):
            t = CH.log_ticks(lo, hi)
            self.assertGreaterEqual(len(t), 2, (lo, hi, t))
            self.assertEqual(t, sorted(set(t)), (lo, hi))
            self.assertTrue(all(lo <= v <= hi for v in t), (lo, hi, t))
        self.assertEqual(CH.log_ticks(8_500, 256_100), [10_000, 20_000, 50_000, 100_000, 200_000])
        mant = {1, 1.5, 2, 3, 5, 7}
        for v in CH.log_ticks(20_000, 30_000):
            self.assertIn(round(v / 10 ** math.floor(math.log10(v)), 6), mant)

    def test_lin_ticks(self):
        self.assertEqual(CH.lin_ticks(0, 52, 3), [0, 20, 40])
        self.assertEqual(CH.lin_ticks(-3.2e9, 4.1e9, 3), [-2.5e9, 0, 2.5e9])
        for lo, hi in ((0.1, 0.2), (-5, 5), (210_000, 260_000), (99.5, 100.5)):
            t = CH.lin_ticks(lo, hi)
            self.assertGreaterEqual(len(t), 2)
            self.assertTrue(all(lo <= v <= hi for v in t))
            self.assertEqual(t, sorted(t))


# ── Test: primitive path ────────────────────────────────────────────────────


class Paths(unittest.TestCase):
    def test_path_d_no_drift(self):
        rng = _Rng(3)
        n = 1500
        xs = [64 + (i + 0.5) * 1040 / n for i in range(n)]
        ys = [20 + 340 * rng.u() for _ in range(n)]
        ys[100] = ys[101] = None
        ys[700] = None
        subs = parse_path(CH.path_d(xs, ys))
        self.assertEqual(len(subs), 3, "None phải mở đoạn M mới")
        got = [p for s in subs for p in s]
        want = [(tn(x), tn(y)) for x, y in zip(xs, ys) if y is not None]
        self.assertEqual(got, want, "toạ độ dựng lại từ lệnh tương đối phải đúng toạ độ đã làm tròn 0.1")

    def test_path_d_format(self):
        d = CH.path_d([10, 11.06, 12.1, 13.2, 14], [5, 5, 4.96, 5.5, -0.04])
        self.assertTrue(d.startswith("M10 5"))
        self.assertNotIn(" -", d)
        self.assertNotIn(".0", d.replace(".05", ""))
        self.assertIn("h1.1", d)
        self.assertEqual(CH.path_d([1, 2], [None, None]), "")
        self.assertEqual(CH.path_d([1.25, 2.04], [3.75, 3.751]), "M1.3 3.8h.7")

    def test_bars_d_roundtrip(self):
        xs = [100.5 + 1.06 * i for i in range(50)]
        tops = [None if i % 7 == 3 else 300 - (i * 13 % 40) for i in range(50)]
        tops[10] = 300.0
        d = CH.bars_d(xs, 300, tops)
        pts = [p for s in parse_path(d) for p in s]
        segs = [(pts[i], pts[i + 1]) for i in range(0, len(pts), 2)]
        want = [(tn(x), tn(t)) for x, t in zip(xs, tops) if t is not None and tn(t) != tn(300)]
        self.assertEqual(len(segs), len(want))
        for (a, b), (x, t) in zip(segs, want):
            self.assertEqual(a[0], x)
            self.assertEqual(b[0], x)
            self.assertEqual({a[1], b[1]}, {t, tn(300)})
        self.assertEqual(d.count("M"), 1)
        bases = [300 - i for i in range(50)]
        d2 = CH.bars_d(xs, bases, [b - 5 for b in bases])
        pts = [p for s in parse_path(d2) for p in s]
        for k in range(0, len(pts), 2):
            self.assertEqual(abs(pts[k][1] - pts[k + 1][1]), 50)

    def test_band_d_closed(self):
        xs = [float(i) for i in range(10)]
        lo = [5.0] * 10
        hi = [1.0] * 10
        lo[4] = None
        d = CH.band_d(xs, lo, hi)
        self.assertEqual(d.count("z"), 2)
        self.assertEqual(d.count("M"), 2)
        for s in parse_path(d):
            self.assertEqual(s[0], s[-1])

    def test_candle_paths(self):
        rows = [{"o": 10, "h": 12, "l": 9, "c": 11}, {"o": 11, "h": 11.5, "l": 8, "c": 9},
                {"o": 9, "h": 9, "l": 9, "c": 9}, {"o": None, "h": 10, "l": 9, "c": 9.5}]

        def Y(v):
            return None if v is None else 100 - v * 5
        cp = CH.candle_paths(rows, [10, 20, 30, 40], Y)
        self.assertEqual(set(cp), {"wick", "up", "down"})
        self.assertEqual(len([p for s in parse_path(cp["wick"]) for p in s]), 6)   # 3 râu (h=l bị bỏ)
        self.assertEqual(len([p for s in parse_path(cp["up"]) for p in s]), 4)     # nến 1 + doji
        self.assertEqual(len([p for s in parse_path(cp["down"]) for p in s]), 2)


# ── Test: build_chart trên chuỗi tổng hợp ───────────────────────────────────


def svg_bytes(svg):
    return D.dumps(D.finalize(svg)[0])


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s982 = synth_series(982, warn=True)
        cls.r = {w: CH.build_chart(cls.s982, w) for w in CH.WIN}

    def test_budget_all_windows(self):
        for w, r in self.r.items():
            bmax, nmax = CH.BUDGET[w]
            self.assertLessEqual(r["bytes"], bmax, w)
            self.assertLessEqual(r["nodes"], nmax, w)
            got_b, got_n = CH.measure(r["svg"])
            self.assertEqual((got_b, got_n), (r["bytes"], r["nodes"]))
            self.assertEqual(len(svg_bytes(r["svg"]).encode("utf-8")), r["bytes"])

    def test_heavy_1348_weeks(self):
        s = synth_series(1348, start="2000-07-24", warn=True)
        r = CH.build_chart(s, "MAX")
        self.assertGreaterEqual(r["step"], 2)
        self.assertLessEqual(r["bytes"], 110_000)
        self.assertLessEqual(r["nodes"], 150)

    def test_svg_root(self):
        svg = self.r["MAX"]["svg"]
        self.assertEqual(svg["t"], "svg")
        self.assertEqual(svg["key"], "cd2.svg")
        self.assertEqual(svg["a"], {"viewBox": "0 0 1200 826"})
        self.assertEqual(svg["s"], {"width": "100%", "height": "auto", "display": "block"})

    def test_max_no_candles_5y_2y_three_candle_paths(self):
        self.assertEqual(by_key(self.r["MAX"]["svg"], "cd2.svg.wick"), [])
        self.assertEqual(len(by_key(self.r["MAX"]["svg"], "cd2.svg.close")), 1)
        for w in ("5Y", "2Y"):
            keys = sorted(n["key"] for n in walk(self.r[w]["svg"]) if isinstance(n, dict)
                          and n.get("key") in ("cd2.svg.wick", "cd2.svg.up", "cd2.svg.down"))
            self.assertEqual(keys, ["cd2.svg.down", "cd2.svg.up", "cd2.svg.wick"], w)
            self.assertEqual(by_key(self.r[w]["svg"], "cd2.svg.close"), [], w)
        self.assertEqual(self.r["2Y"]["scale"], "lin")
        self.assertEqual(self.r["MAX"]["scale"], "log")

    def test_short_series_max_has_candles(self):
        r = CH.build_chart(synth_series(166, start="2023-06-05", ts_start=None), "MAX")
        self.assertEqual(len(by_key(r["svg"], "cd2.svg.wick")), 1)

    def test_log_ticks_monotone_on_chart(self):
        svg = self.r["MAX"]["svg"]
        labs = [n for n in texts(svg) if n.get("key") == "cd2.svg.y.price"]
        self.assertGreaterEqual(len(labs), 2)
        vals = [float(text_of(n)[:-1].replace(",", "")) for n in labs]
        ys = [n["a"]["y"] for n in labs]
        self.assertEqual(vals, sorted(vals))
        self.assertTrue(all(a > b for a, b in zip(ys, ys[1:])), "y phải giảm ngặt khi giá tăng")
        for v in vals:
            m = v / 10 ** math.floor(math.log10(v))
            self.assertIn(round(m, 6), {1, 1.5, 2, 3, 5, 7})

    def test_no_v21_levels_and_banned_text(self):
        for r in self.r.values():
            blob = " ".join(text_of(n) for n in texts(r["svg"]))
            for word in ("HI", "STOP", "BASE", "ANCHOR"):
                self.assertNotIn(word, blob)
            for bad in (EM_DASH, EN_DASH, "as of", "BUY", "SELL", "TRIM", "DCA", "%NAV", "nên mua", "nên bán"):
                self.assertNotIn(bad, blob)
            self.assertIsNone(re.search(r"\d{1,3}(\.\d{3})+,\d", blob), "số kiểu Việt")

    def test_markers(self):
        for w, r in self.r.items():
            mk = [n for n in walk(r["svg"]) if isinstance(n, dict) and str(n.get("key", "")).startswith("cd2.svg.m.")]
            self.assertLessEqual(len(mk), 8)
            nums = by_key(r["svg"], "cd2.svg.mk.")
            self.assertLessEqual(len(nums), 12)
            self.assertEqual(len(nums), len(r["legend"]))
            self.assertEqual([e["n"] for e in r["legend"]], list(range(1, len(r["legend"]) + 1)))
            self.assertEqual([text_of(n) for n in nums], [e["glyph"] for e in r["legend"]])
            self.assertTrue(all(e["kind"] not in ("dhcd", "tt_dot_bien") for e in r["legend"]))
            self.assertEqual([e["date"] for e in r["legend"]], sorted(e["date"] for e in r["legend"]))
        lg = self.r["MAX"]["legend"]
        self.assertEqual(len(lg), 12)
        self.assertNotIn("old", [e["ref"] for e in lg], "marker ngoài khung không được đánh số")
        sized = sorted((m for m in self.s982["markers"] if m["kind"] in CH.MARKER_KINDS
                        and m["kind"] not in ("dhcd", "tt_dot_bien") and m["ref"] != "old"),
                       key=lambda m: (-m["size"], m["date"]))
        self.assertEqual({e["ref"] for e in lg}, {m["ref"] for m in sized[:12]})
        self.assertTrue(any("la_lung" in w for w in self.r["MAX"]["warnings"]))

    def test_fft_pane_no_numeric_axis(self):
        top, bot = CH.PANE_Y["fft"]
        for r in self.r.values():
            svg = r["svg"]
            self.assertEqual(by_key(svg, "cd2.svg.y.fft"), [])
            notes = by_key(svg, "cd2.svg.fft.note")
            self.assertEqual(len(notes), 1)
            self.assertIn(CH.FFT_NOTE, text_of(notes[0]))
            self.assertEqual(text_of(by_key(svg, "cd2.svg.fft.warn")[0]), FFT_WARN)
            inside = [n for n in texts(svg) if top - 5 <= n["a"]["y"] <= bot + 3
                      and not str(n.get("key")).startswith(("cd2.svg.fft.", "cd2.svg.mk."))]
            self.assertEqual(inside, [], [text_of(n) for n in inside])
            self.assertEqual(len(by_key(svg, "cd2.svg.fft.band")), 1)
        r = CH.build_chart(synth_series(300, start="2020-01-06", ts_start=None), "MAX")
        self.assertEqual(by_key(r["svg"], "cd2.svg.fft.warn"), [])

    def test_numbers_in_svg_text(self):
        for w, r in self.r.items():
            blob = [text_of(n) for n in texts(r["svg"])]
            self.assertTrue(r["numbers"], w)
            for num in r["numbers"]:
                self.assertIn(num["text"], blob)
                ann = by_key(r["svg"], "cd2.svg.ann." + num["id"])
                self.assertEqual(text_of(ann[0]), num["text"])
                self.assertRegex(num["text"], r"^\d{1,3}(,\d{3})*\.\dK$")
            self.assertEqual(r["numbers"][-1]["id"], "now")
        weeks = self.s982["weeks"]
        now = self.r["MAX"]["numbers"][-1]
        self.assertEqual(now["date"], weeks[-1]["we"])
        self.assertEqual(now["text"], D.to_locale(weeks[-1]["c"] / 1000, "en-US", min_frac=1, max_frac=1) + "K")
        ath = max(range(len(weeks)), key=lambda i: (weeks[i]["c"], -i))
        self.assertEqual(self.r["MAX"]["numbers"][0]["date"], weeks[ath]["we"])

    def test_deterministic(self):
        again = CH.build_chart(synth_series(982, warn=True), "MAX")
        self.assertEqual(svg_bytes(again["svg"]), svg_bytes(self.r["MAX"]["svg"]))
        self.assertEqual({k: v for k, v in again.items() if k != "svg"},
                         {k: v for k, v in self.r["MAX"].items() if k != "svg"})

    def test_meta(self):
        r = self.r["MAX"]
        w = self.s982["weeks"]
        self.assertEqual((r["n_weeks"], r["n_pts"], r["step"], r["first"], r["last"]),
                         (982, 982, 1, "2007-09-17", w[-1]["we"]))
        self.assertIsNone(r["alias_of"])
        self.assertEqual(self.r["5Y"]["first"], w[-260]["w"])

    def test_ts_start_line(self):
        svg = self.r["MAX"]["svg"]
        self.assertEqual(len(by_key(svg, "cd2.svg.ts")), 2)       # vạch + chữ
        self.assertEqual(text_of(by_key(svg, "cd2.svg.ts.t")[0]), CH.TS_TEXT)
        self.assertEqual(by_key(self.r["2Y"]["svg"], "cd2.svg.ts"), [], "ts_start ngoài khung 2Y không vẽ")

    def test_x_labels(self):
        lab = [text_of(n) for n in texts(self.r["MAX"]["svg"]) if n.get("key") == "cd2.svg.x"]
        self.assertLessEqual(len(lab), 14)
        self.assertTrue(all(re.fullmatch(r"\d{4}", s) for s in lab))
        lab2 = [text_of(n) for n in texts(self.r["2Y"]["svg"]) if n.get("key") == "cd2.svg.x"]
        self.assertTrue(lab2 and all(re.fullmatch(r"Q[1-4]/\d{2}", s) for s in lab2), lab2)
        lab5 = [text_of(n) for n in texts(self.r["5Y"]["svg"]) if n.get("key") == "cd2.svg.x"]
        self.assertTrue(4 <= len(lab5) <= 6, lab5)
        s = synth_series(1348, start="2000-07-24", markers=False)
        lab = [text_of(n) for n in texts(CH.build_chart(s, "MAX")["svg"]) if n.get("key") == "cd2.svg.x"]
        self.assertLessEqual(len(lab), 14)
        g = synth_series(34, start="2026-02-09", ts_start=None, markers=False)       # GEL: không có tháng 1
        lab = [text_of(n) for n in texts(CH.build_chart(g, "MAX")["svg"]) if n.get("key") == "cd2.svg.x"]
        self.assertEqual(lab, ["Q2/26", "Q3/26"])

    def test_lin_price_ticks_dense_enough(self):
        labs = [n for n in texts(self.r["2Y"]["svg"]) if n.get("key") == "cd2.svg.y.price"]
        self.assertGreaterEqual(len(labs), 3, [text_of(n) for n in labs])
        self.assertLessEqual(len(labs), 8)

    def test_flow_pane_modes(self):
        self.assertEqual(len(by_key(self.r["MAX"]["svg"], "cd2.svg.nn")), 1)
        self.assertEqual(len(by_key(self.r["MAX"]["svg"], "cd2.svg.td")), 1)
        right = [n for n in texts(self.r["MAX"]["svg"]) if n.get("key") == "cd2.svg.y.flow"]
        self.assertTrue(any(text_of(n).endswith(" tỷ") for n in right))
        self.assertTrue(any(text_of(n).endswith("M") for n in right))
        bars = by_key(self.r["2Y"]["svg"], "cd2.svg.nn")[0]["a"]["d"]
        self.assertIn("v", bars)
        self.assertNotIn("l", bars)

    def test_texts_do_not_overlap(self):
        for w, r in self.r.items():
            self.assertEqual(overlaps(r["svg"]), [], w)

    def test_ath_label_above_wicks_in_span(self):
        """Chữ đỉnh lịch sử nằm TRÊN râu nến (h) của mọi tuần dưới bề ngang chữ, không phải trên giá đóng."""
        s = synth_series(104, start="2024-06-03", markers=False, ts_start=None)
        k = max(range(len(s["weeks"])), key=lambda i: s["weeks"][i]["c"])
        for j in (k - 1, k, k + 1):
            if 0 <= j < len(s["weeks"]):
                s["weeks"][j]["h"] = s["weeks"][k]["c"] * 1.04         # râu cao hơn đóng tuần đỉnh
        cv = CH._Canvas(s, s["weeks"], "2Y", True, False)
        cv.price()
        cv.annotate()
        t = next(n for n in texts(cv.render()) if n.get("key") == "cd2.svg.ann.ath")
        box = CH.text_box(t["a"]["x"], t["a"]["y"], text_of(t), 9, "middle")
        tops = [cv.Yp(r["h"]) for x, r in zip(cv.xs, s["weeks"]) if box[0] - cv.pitch / 2 <= x <= box[2] + cv.pitch / 2]
        self.assertLess(box[3], min(tops))

    def test_place_falls_back_to_least_overlap(self):
        """Mọi chỗ thử đều chồng (y kẹp ở mép pane): chọn chỗ chồng ít nhất, không đè trọn lên chữ đã đặt (PVD MAX)."""
        s = synth_series(60, start="2024-06-03", markers=False, ts_start=None)
        cv = CH._Canvas(s, s["weeks"], "2Y", True, False)
        cv.place(500, 50, "31.4K", "a", 50, 50, anchor="middle", size=9)
        cv.place(505, 50, "⑪", "b", 50, 50, anchor="middle", size=9)
        b1, b2 = cv.boxes[-2], cv.boxes[-1]
        self.assertLess(CH.overlap(b1, b2), 0.25 * (b2[2] - b2[0]) * (b2[3] - b2[1]))
        cv.place(400, 80, "x", "c", 0, 200, anchor="middle")
        self.assertEqual((cv.texts[-1]["a"]["x"], cv.texts[-1]["a"]["y"]), (400, 80))     # chỗ trống: giữ nguyên

    def test_alias_identical(self):
        s = synth_series(166, start="2023-06-05", ts_start=None)
        a, b = CH.build_chart(s, "MAX"), CH.build_chart(s, "5Y")
        self.assertEqual(b["alias_of"], "MAX")
        self.assertEqual(svg_bytes(a["svg"]), svg_bytes(b["svg"]))
        g = synth_series(34, start="2026-02-09", ts_start=None)
        self.assertEqual({CH.build_chart(g, w)["alias_of"] for w in ("5Y", "2Y")}, {"MAX"})

    def test_degrade_drops_vwap6_last(self):
        orig = CH.BUDGET
        try:
            CH.BUDGET = {"MAX": (20_000, 150), "5Y": (70_000, 150), "2Y": (50_000, 150)}
            r = CH.build_chart(self.s982, "MAX")
        finally:
            CH.BUDGET = orig
        self.assertEqual(r["step"], CH.MAX_STEP)
        self.assertEqual(by_key(r["svg"], "cd2.svg.v6"), [])
        self.assertEqual(len(by_key(r["svg"], "cd2.svg.v24")), 1)
        self.assertTrue(any("step 2" in w for w in r["warnings"]))
        self.assertTrue(any("bỏ VWAP 6T" in w for w in r["warnings"]))

    def test_empty_and_sparse_inputs(self):
        r = CH.build_chart({"weeks": []}, "MAX")
        self.assertEqual(r["n_pts"], 0)
        self.assertEqual(r["numbers"], [])
        bare = [{k: (v if k in ("w", "we", "o", "h", "l", "c", "vol") else None) for k, v in row.items()}
                for row in synth_series(400, start="2018-01-01", markers=False)["weeks"]]
        r = CH.build_chart({"weeks": bare, "markers": []}, "MAX")
        keys = {n.get("key") for n in walk(r["svg"]) if isinstance(n, dict)}
        for pane in ("fo", "fft", "flow", "rs"):
            self.assertIn("cd2.svg.empty." + pane, keys)
        self.assertLessEqual(r["nodes"], 150)
        with self.assertRaises(ValueError):
            CH.build_chart({"weeks": bare}, "10Y")



def overlaps(svg, tol=2.0):
    """Cặp chữ có hộp ước giao nhau quá tol px (luật §8.5: không hai chữ giao nhau quá 2 px)."""
    boxes = []
    for n in texts(svg):
        a = n["a"]
        size = a.get("fontSize", CH.FS)
        boxes.append((CH.text_box(a["x"], a["y"], text_of(n), size, a.get("textAnchor")), text_of(n)))
    bad = []
    for i, (b1, s1) in enumerate(boxes):
        for b2, s2 in boxes[i + 1:]:
            ox = min(b1[2], b2[2]) - max(b1[0], b2[0])
            oy = min(b1[3], b2[3]) - max(b1[1], b2[1])
            if ox > tol and oy > tol:
                bad.append((s1, s2))
    return bad


# ── Test: mã nguồn ──────────────────────────────────────────────────────────


class Source(unittest.TestCase):
    FILES = ("chaebol_map_tab_codong_v2_chart.py", "chaebol_map_tab_codong_v2_svg.py")

    def test_static_rules(self):
        for f in self.FILES:
            src = (HERE / f).read_text(encoding="utf-8")
            self.assertLessEqual(src.count("\n"), 800, f)
            for bad in ("import chaebol_map_data", "from chaebol_map_data", "vc_lk_fetch", "urllib", "requests",
                        "import socket", "open(", "date.today", "datetime.now", EM_DASH, EN_DASH):
                self.assertNotIn(bad, src, (f, bad))
            imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", src, re.M)
            for mod in imports:
                self.assertIn(mod.split(".")[0], {"__future__", "bisect", "math", "datetime", "decimal",
                                                  "chaebol_map_dom", "chaebol_map_tab_codong_v2_svg"}, (f, mod))

    def test_function_length(self):
        """Mọi hàm/phương thức ≤ 50 dòng tính cả docstring và dòng trống (đo bằng AST như test P1)."""
        for f in self.FILES:
            tree = ast.parse((HERE / f).read_text(encoding="utf-8"))
            for n in ast.walk(tree):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.assertLessEqual(n.end_lineno - n.lineno + 1, 50, (f, n.name))


# ── Test: kho thật (chỉ đọc) ────────────────────────────────────────────────


def _series_p2(tk):
    import chaebol_map_data_codong2_gia as P   # noqa: WPS433 (P2, có thể chưa có)
    wf = P.weekly_full(tk)
    if not wf.get("ok"):
        return None
    cum, rsw, fv = P.cum_series(tk), P.rs_weekly(tk), P.fft_view(tk)
    fmap = {}
    if fv.get("ok"):
        for i, wk in enumerate(fv.get("w") or []):
            fmap[wk] = {k: (fv.get(k) or [None] * (i + 1))[i] for k in ("fw", "ma4", "p10", "p90")}
    weeks = []
    for i, r in enumerate(wf["rows"]):
        row = {k: r.get(k) for k in ("w", "we", "o", "h", "l", "c", "vol", "dvol", "fo", "fol", "v6", "v12", "v24",
                                     "pre")}
        row.update({"nn_w": r.get("nn_val"), "td_w": r.get("td_val"),
                    "nn_cum": (cum.get("nn_cum") or [None] * (i + 1))[i] if cum.get("ok") else None,
                    "td_cum": (cum.get("td_cum") or [None] * (i + 1))[i] if cum.get("ok") else None,
                    "rs": (rsw.get("rs") or [None] * (i + 1))[i] if rsw.get("ok") else None})
        row.update(fmap.get(r.get("w"), {"fw": None, "ma4": None, "p10": None, "p90": None}))
        weeks.append(row)
    return {"tk": tk, "weeks": weeks, "markers": [], "ts_start": wf.get("ts_start"), "fft_note": CH.FFT_NOTE,
            "fft_warn": None, "_src": "P2"}


def _series_old(tk):
    import chaebol_map_data_gia as G
    w = G.weekly_ohlcv(tk, adjust=True)
    if getattr(w, "can", False) or not w.value:
        return None
    weeks, nn, td = [], 0.0, None
    for r in w.value:
        nn = nn + r["nn_vol"] if r.get("nn_vol") is not None else nn
        if r.get("td_n"):
            td = (td or 0.0) + (r.get("td_val") or 0.0)
        weeks.append({"w": r["monday"], "we": r["week_end"], "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"],
                      "vol": r["vol"], "dvol": None, "fo": None, "fol": None, "v6": r.get("vwap6"),
                      "v12": r.get("vwap12"), "v24": r.get("vwap24"), "nn_cum": nn, "td_cum": td,
                      "nn_w": r.get("nn_val"), "td_w": r.get("td_val") if r.get("td_n") else None, "rs": None,
                      "fw": None, "ma4": None, "p10": None, "p90": None, "pre": False})
    return {"tk": tk, "weeks": weeks, "markers": [], "ts_start": None, "fft_note": CH.FFT_NOTE, "fft_warn": None,
            "_src": "data_gia cũ"}


def real_series(tk):
    try:
        s = _series_p2(tk)
        if s is not None:
            return s
    except Exception:          # P2 chưa có / đang viết dở: dùng chuỗi cũ
        pass
    return _series_old(tk)


@unittest.skipUnless((VC_DIR / "VIC" / "price-history.json").is_file(), "thiếu vc_lk/VIC/price-history.json")
class RealStore(unittest.TestCase):
    """VIC 982 tuần, REE 1,348 tuần (ca nặng nhất), GEL 34 tuần (cả ba khung là MAX) theo §1 F3."""

    @classmethod
    def setUpClass(cls):
        cls.s = {tk: real_series(tk) for tk in ("VIC", "REE", "GEL")}

    def test_lengths_f3(self):
        want = {"VIC": (982, "2007-09-17"), "REE": (1348, "2000-07-24"), "GEL": (34, None)}
        for tk, (n, first) in want.items():
            s = self.s[tk]
            self.assertIsNotNone(s, tk)
            self.assertEqual(len(s["weeks"]), n, (tk, s.get("_src")))
            if first:
                self.assertEqual(s["weeks"][0]["w"], first)

    def test_budgets_and_shape(self):
        for tk, s in self.s.items():
            plan = CH.window_plan(len(s["weeks"]))
            for w in CH.WIN:
                r = CH.build_chart(s, w)
                eff = plan[w]
                bmax, nmax = CH.BUDGET[eff]
                self.assertLessEqual(r["bytes"], bmax, (tk, w))
                self.assertLessEqual(r["nodes"], nmax, (tk, w))
                self.assertEqual([x for x in r["warnings"] if "B >" in x], [], (tk, w, r["warnings"]))
                candles = len(by_key(r["svg"], "cd2.svg.wick"))
                self.assertEqual(candles, 0 if (eff == "MAX" and len(s["weeks"]) > 260) else 1, (tk, w))
                self.assertEqual(overlaps(r["svg"]), [], (tk, w))
                for num in r["numbers"]:
                    self.assertIn(num["text"], [text_of(n) for n in texts(r["svg"])])
        self.assertEqual(CH.build_chart(self.s["REE"], "MAX")["step"], 2)
        self.assertEqual(CH.build_chart(self.s["GEL"], "2Y")["alias_of"], "MAX")

    def test_vic_annotations(self):
        r = CH.build_chart(self.s["VIC"], "MAX")
        ath = r["numbers"][0]
        self.assertEqual(ath["id"], "ath")
        self.assertEqual(ath["date"], "2026-09-04")
        self.assertEqual(ath["text"], "256.1K")
        self.assertEqual(r["scale"], "log")
        self.assertEqual(r["first"], "2007-09-17")


if __name__ == "__main__":
    unittest.main()
