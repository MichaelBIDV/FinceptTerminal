#!/usr/bin/env python3
"""Unit tests tab `overview` (00 · TỔNG QUAN) + `chaebol` (01 · CHAEBOL MAP) của chaebol_map — không mạng.

Chạy (cả hai trình thông dịch, PYTHONDONTWRITEBYTECODE=1):
    python3 -m unittest scripts/test_chaebol_map_tab_overview.py -v
    ~/Library/Application\\ Support/com.fincept.terminal/venv-numpy2/bin/python -m unittest \\
        scripts/test_chaebol_map_tab_overview.py

Chuỗi vàng lấy từ chaebol_map_spec/page_p4_overview_map.md (§2–§3, §5) và SRC 5173–5728. Phần live dùng kho thật
(bỏ qua nếu vắng); phần live "không dữ liệu" (ctx.data=None, dossier=None) luôn chạy. Socket bị chặn.
"""
from __future__ import annotations

import json
import re
import socket
import sys
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import chaebol_map as M  # noqa: E402
import chaebol_map_dom as D  # noqa: E402
import chaebol_map_shell as S  # noqa: E402
import chaebol_map_tab_overview as T  # noqa: E402

V21_PATH = Path.home() / "SECOND BRAIN-OBSIDIAN/_System/fincept_bridge/data/chaebol_map/v21_const.json"
VCLK = Path.home() / "SECOND BRAIN-OBSIDIAN/_System/fincept_bridge/state/vc_lk"
_REAL_SOCKET = {}
V21 = json.loads(V21_PATH.read_text(encoding="utf-8")) if V21_PATH.is_file() else None


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


def keyed(node, key):
    return next((n for n in walk(node) if isinstance(n, dict) and n.get("key") == key), None)


def ctx_for(mode, data=None, dossier=None):
    ctx = M.Ctx(mode, date(2026, 9, 27), list(S.TABS_V21))
    ctx.v21 = V21 or {}
    ctx.data, ctx.dossier = data, dossier
    return ctx


def build(tab, mode, data=None, dossier=None):
    ctx = ctx_for(mode, data, dossier)
    ctx.tab = tab
    with D.use_mode(mode, "2026-09-27"):
        res = getattr(T, "build_" + tab)(ctx)
    return res, ctx


# ── 'Số trần thiếu nhãn' (DESIGN §8.4): số-giá-trị phải có nhãn bậc / [CẦN DATA] trong khối gần nhất ──
VALUE = re.compile(r"(\d+\.\d+)|([-+−~≈]?\$?\d[\d,]*\s*(%|M\b|B\b|K\b|k\b|tỷ|triệu|nghìn|cp\b|x\b|×|đ\b|USD))|(\$\d)")
BLOCK = {"div", "li", "td", "th", "p", "h2", "h3", "text", "section", "ul", "button"}
NOT_DATA = re.compile(r"v\d+\.\d+|>5% NAV|L1\+L2\+L3|40% anchor rule")  # phiên bản, luật, tên pattern — không phải số liệu


def _is_label(n):
    return isinstance(n, dict) and (n.get("_tier") or n.get("_can") or (
        n.get("t") == "tspan" and (n.get("a") or {}).get("fontSize") == "7"))


def _has_label(n):
    return _is_label(n) or (isinstance(n, dict) and any(_has_label(k) for k in n.get("k") or []))


def bare_numbers(root):
    bad = []

    def rec(n, chain):
        if isinstance(n, str):
            if VALUE.search(NOT_DATA.sub("", n)):
                blk = next((a for a in reversed(chain) if a.get("t") in BLOCK), None)
                if blk is not None and blk.get("t") in ("h2", "th"):
                    return                                  # tiêu đề/nhãn cột: cấu trúc, không phải số liệu
                if blk is None or not _has_label(blk):
                    bad.append(n[:80])
            return
        for k in n.get("k") or []:
            rec(k, chain + [n])
    rec(root, [])
    return bad


@unittest.skipIf(V21 is None, "thiếu v21_const.json")
class V21Overview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res, cls.ctx = build("overview", "v21")
        cls.root = cls.res["root"]
        cls.txt = text_of(cls.root)

    def test_four_sections_in_order(self):
        keys = [n.get("key") for n in walk(self.root) if isinstance(n, dict) and n.get("t") == "section"]
        self.assertEqual(keys, ["ov.thesis", "ov.bridge", "ov.flows", "ov.phase"])
        self.assertEqual(self.res.get("states") or [], [])

    def test_golden_strings(self):
        for s in ("✦ Thesis V21 — Chaebol Reshuffle Hypothesis", "Tháng 5, 2026", "DGC ngày HÔM NAY 8/5/2026",
                  "🜲 Bridge V20 → V21 — Có gì mới?", "V20 (HIỆN TẠI)", "V21 (★ MỚI)",
                  "Master plan tích sản MSN ALL-IN (84,400 cp)", "Portfolio actions: rotate FPT/VCB → GEX/HPG/BSR",
                  "✪ Top Pillar IV Flow Insights — 60 ngày tới 08/05/2026 (FiinTrade verified)",
                  "★ TOP NN ACCUMULATION (60D)", "⚠ TOP NN DISTRIBUTION (60D)", "Đọc 2 bảng đối lập này bằng tư duy "
                  "contrarian Munger:", "◐ Howard Marks Phase — 45 mã VN30+ matrix", "★ Sweet spot — vào dần",
                  "(Pattern A textbook ở đỉnh)", "= Pattern B textbook ở đáy", "★ Đáy Pattern B đang form"):
            self.assertIn(s, self.txt)
        self.assertNotIn("↻", self.txt)
        self.assertNotIn("Pattern A?", self.txt)                     # hậu tố '?' chỉ ở live
        self.assertNotIn("V21·12/05", self.txt)
        self.assertNotIn("[CẦN DATA", self.txt)

    def test_flow_tables_js_numbers(self):
        flows = keyed(self.root, "ov.flows")
        rows = [n for n in walk(flows) if isinstance(n, dict) and n.get("t") == "tr"]
        cells = [[text_of(td) for td in r["k"]] for r in rows]
        self.assertEqual(cells[1][:3], ["HPG", "+168.6", "+3.7%"])
        self.assertIn(["BSR", "+46.0", "+91.5%"], [c[:3] for c in cells])
        self.assertIn(["MSN", "+26.6", "-3.3%"], [c[:3] for c in cells])
        self.assertIn(["VCB", "-90.8", "-16.0%"], [c[:3] for c in cells])
        self.assertIn(["DGC", "-44.0", "-49.7%", "⛔ Khởi tố CT/Phó CT"], cells)
        self.assertEqual(len(rows), 2 + 6 + 10)
        # JSX `+{nn}` / `{sign}{perf}%` = các text node RIÊNG (khớp ref từng pixel)
        hpg = rows[1]["k"]
        self.assertEqual(hpg[1]["k"], ["+", "168.6"])
        self.assertEqual(hpg[2]["k"], ["+", "3.7", "%"])

    def test_phase_matrix_columns(self):
        phase = keyed(self.root, "ov.phase")
        cols = [n for n in walk(phase) if isinstance(n, dict) and (n.get("s") or {}).get("padding") == 10]
        self.assertEqual(len(cols), 6)
        chips = [[text_of(c) for c in col["k"][2]["k"]] for col in cols]
        self.assertEqual(chips[0], ["FPT", "VCB", "BID", "VTP", "DGC"])
        self.assertEqual(sum(len(c) for c in chips), 45)
        self.assertEqual([text_of(c["k"][0]) for c in cols], ["CAP", "P1", "P2", "MARKUP", "P3", "P3D"])


@unittest.skipIf(V21 is None, "thiếu v21_const.json")
class V21Chaebol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res, cls.ctx = build("chaebol", "v21")
        cls.root = cls.res["root"]
        cls.txt = text_of(cls.root)

    def test_nine_sections(self):
        keys = [n.get("key") for n in walk(self.root) if isinstance(n, dict) and n.get("t") == "section"]
        self.assertEqual(keys, ["map.intro", "map.groups", "map.axes", "map.matrix", "map.claims", "map.patterns",
                                "map.timeline", "map.power", "map.hypothesis"])

    def test_states_and_options(self):
        st = {s["key"]: s for s in self.res["states"]}
        self.assertEqual(st["map.axis"]["options"], ["ALL", "NQ79", "NQ68", "SPECIAL"])
        self.assertEqual(st["map.tier"]["options"], ["ALL", "Top", "Mid", "Distress", "Special"])
        self.assertEqual((st["map.axis"]["default"], st["map.tier"]["default"]), ("ALL", "ALL"))
        cov = M._coverage([dict(s, tab="chaebol") for s in self.res["states"]], {"chaebol"}, V21)
        self.assertEqual(cov, {"missing": [], "mismatch": []})

    def test_filter_buttons_and_counter(self):
        btns = [n for n in walk(self.root) if isinstance(n, dict) and n.get("t") == "button"]
        self.assertEqual([text_of(b) for b in btns], ["ALL", "NQ79", "NQ68", "SPECIAL", "ALL", "Top", "Mid",
                                                      "Distress", "Special"])
        self.assertEqual(btns[1]["on"], {"set": {"map.axis": "NQ79"}})
        self.assertEqual(btns[1]["var"][0]["s"], {"background": D.C.crimson, "color": "#0a0a0c"})  # as_intended
        self.assertEqual(btns[0]["var"][0]["s"]["background"], D.C.gold)                          # ALL → gold
        cnt = keyed(self.root, "map.count")
        self.assertEqual(cnt["count"], {"grp": "map.rows", "fmt": "Showing {n}/24"})

    def test_filter_combinations(self):
        rows = [n for n in walk(self.root) if isinstance(n, dict) and n.get("grp") == "map.rows"]
        self.assertEqual(len(rows), 24)

        def shown(axis, tier):
            return sum(1 for r in rows if axis in r["if"]["map.axis"] and tier in r["if"]["map.tier"])
        self.assertEqual(shown("ALL", "ALL"), 24)
        self.assertEqual([shown(a, "ALL") for a in ("NQ79", "NQ68", "SPECIAL")], [11, 12, 1])
        self.assertEqual([shown("ALL", t) for t in ("Top", "Mid", "Distress", "Special")], [11, 9, 3, 1])
        empty = [(a, t) for a in ("NQ79", "NQ68", "SPECIAL") for t in ("Top", "Mid", "Distress", "Special")
                 if shown(a, t) == 0]
        self.assertEqual(len(empty), 6)              # coverage_critic §1: 6/12 tổ hợp chỉ còn header

    def test_golden_strings(self):
        for s in ("◆ Bản Đồ Chaebol Việt Nam — Tháng 5, 2026", "Politicalmaps × stock market overlay",
                  "✦ Bốn Nhóm Trọng Yếu", "⛔ LOẠI KHỎI CUỘC CHƠI", "CORE THESIS · ", "★ NQ 79 — NHÀ NƯỚC",
                  " 50 DNNN Top 500 ĐNA · 1-3 Top 500 thế giới · ≥3 NHTM Top 100 châu Á",
                  " Tư nhân đóng góp 55-58% GDP đến 2030 · >20 DN tham gia chuỗi giá trị toàn cầu",
                  "24 entries (Big4 tách 4 NH thành 4 row riêng — gọi là 21 do report rule)", "36/54 claims (67%)",
                  "PATTERN 5 · 4-piece NH-CK-BH-Holding (ván cờ hoàn chỉnh)", "Vingroup hiện thiếu mảnh CK",
                  "⌖ Timeline 30 Ngày Gần Nhất — Sự Kiện Định Hình Chaebol Map", "[ELIMINATED]",
                  "VIETNAM CHAEBOL POWER MAP · MAY 2026 · BUILT FROM CAPITAL IQ + AGM 2026 + PRESS",
                  "KHỞI TỐ HÔM NAY 8/5", "Caveat — KHÔNG nhầm lẫn correlation và causation:"):
            self.assertIn(s, self.txt)
        self.assertNotIn("↻", self.txt)

    def test_group_chips_from_flow(self):
        grp = keyed(self.root, "map.grp.tuanmuot")
        chips = [n for n in walk(grp) if isinstance(n, dict) and (n.get("s") or {}).get("padding") == "6px 10px"]
        self.assertEqual([text_of(c) for c in chips],
                         ["GEX+83.2%", "GEE+229.2%", "GEL-6.9%", "VGCN/A", "VIX+75.2%", "EIBN/A"])
        self.assertEqual(chips[3]["s"]["borderLeft"], "3px solid " + D.C.inkM)       # không FLOW
        self.assertEqual(chips[4]["s"]["borderLeft"], "3px solid " + D.C.ochre)      # MIX

    def test_claims_bars(self):
        bars = [n for n in walk(keyed(self.root, "map.claims")) if isinstance(n, dict)
                and (n.get("s") or {}).get("transition") == "width 0.3s"]
        self.assertEqual([b["s"]["width"] for b in bars[:3]], ["100%", "77.77777777777779%", "77.77777777777779%"])
        self.assertEqual(bars[0]["s"]["background"], D.C.crimson)
        self.assertEqual(len(bars), 10)

    def test_pattern5_not_span(self):
        p5 = keyed(self.root, "map.pattern.p5")
        self.assertNotIn("gridColumn", p5.get("s") or {})        # Card bỏ `style` → giữ như gốc

    def test_timeline_and_svg(self):
        tl = keyed(self.root, "map.timeline")
        rows = [n for n in walk(tl) if isinstance(n, dict) and (n.get("s") or {}).get("padding") == "10px 0"]
        self.assertEqual(len(rows), 11)
        self.assertEqual([r["s"]["borderBottom"] for r in rows][-2:], ["1px solid #26242c50", "none"])
        svg = keyed(self.root, "map.svg")
        self.assertEqual(svg["a"]["viewBox"], "0 0 1100 460")
        boxes = [n for n in svg["k"] if isinstance(n, dict) and n.get("t") == "g"]
        self.assertEqual(len(boxes), 5)
        self.assertEqual(boxes[0]["a"]["transform"], "translate(60, 50)")
        self.assertIn("EIB 10%", text_of(boxes[0]))


@unittest.skipIf(V21 is None, "thiếu v21_const.json")
class LiveNoData(unittest.TestCase):
    """live nhưng thiếu lớp dữ liệu + dossier: vẫn dựng, số V21 có nhãn, số sống = [CẦN DATA]."""

    def test_builds_and_labels(self):
        for tab in ("overview", "chaebol"):
            res, ctx = build(tab, "live", data=None, dossier=None)
            self.assertEqual(bare_numbers(res["root"]), [], tab)
            self.assertFalse([w for w in ctx.warnings if "lỗi" in w], ctx.warnings)
            t = text_of(res["root"])
            self.assertIn("V21·12/05", t)
            self.assertIn("[CẦN DATA", t)
            self.assertNotIn("HÔM NAY 8/5/2026", t)


@unittest.skipIf(V21 is None or not (VCLK / "GEX" / "price-history.json").is_file(), "thiếu kho vc_lk thật")
class LiveReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import chaebol_map_data as DATA
        cls.dossier = DATA.dossier()
        cls.ov, cls.ov_ctx = build("overview", "live", data=DATA, dossier=cls.dossier)
        cls.map, cls.map_ctx = build("chaebol", "live", data=DATA, dossier=cls.dossier)

    def test_no_bare_numbers_and_no_errors(self):
        self.assertEqual(bare_numbers(self.ov["root"]), [])
        self.assertEqual(bare_numbers(self.map["root"]), [])
        for c in (self.ov_ctx, self.map_ctx):
            self.assertFalse([w for w in c.warnings if "lỗi" in w], c.warnings)

    def test_flow_tables_recomputed(self):
        t = text_of(keyed(self.ov["root"], "ov.flows"))
        self.assertIn("60 phiên tới 25/09/2026", t)
        self.assertIn("phần dư", t)
        self.assertNotIn("Steel supercycle", t)             # ghi chú V21 không đi kèm số mới
        tr = [n for n in walk(keyed(self.ov["root"], "ov.flows")) if isinstance(n, dict) and n.get("t") == "tr"]
        self.assertEqual(len(tr), 2 + 6 + 10)

    def test_dossier_rewrites_applied(self):
        if not (self.dossier or {}).get("overview"):
            self.skipTest("chưa có mảnh dossier overview")
        t = text_of(self.map["root"])
        for s in ("Lê Ngọc Lâm (CT từ 01/07/2026)", "Đào Hữu Kha (CT từ 08/05/2026)", "TCBS đã niêm yết mã TCX",
                  "HOSE loại DGC khỏi VN30", "Thảo 8% · Sunny 26.2%", "khởi tố 17/03 + 23/07"):
            self.assertIn(s, t)
        self.assertNotIn("KHỞI TỐ HÔM NAY", t)
        pills = [text_of(n) for n in walk(self.map["root"]) if isinstance(n, dict) and n.get("t") == "span"
                 and text_of(n) in ("ĐẠT", "BỊ BÁC", "CHƯA RÕ")]
        self.assertGreaterEqual(pills.count("BỊ BÁC"), 5)
        o = text_of(self.ov["root"])
        self.assertIn("Sovico còn 9.992% HDB", o)
        self.assertIn("V21·12/05", o)

    def test_chips_live(self):
        grp = keyed(self.map["root"], "map.grp.phuong")
        chips = [n for n in walk(grp) if isinstance(n, dict) and (n.get("s") or {}).get("padding") == "6px 10px"]
        self.assertIn("[CẦN DATA", text_of(chips[1]))       # IDP: không có cache vc_lk
        self.assertTrue(any(isinstance(x, dict) and x.get("_tier") == "EST" for x in walk(chips[0])))

    def test_legal_names_not_added(self):
        """Luật j: không thêm tên cá nhân gắn cáo buộc mới khi chỉ có nguồn báo chí (F4-009, F4-042, F4-055)."""
        t = text_of(self.map["root"]) + text_of(self.ov["root"])
        for name in ("Đặng Phan Tường", "Lưu Bách Đạt", "Trịnh Văn Tuấn"):
            self.assertNotIn(name, t)

    # ── kiểm chứng 27/09 ─────────────────────────────────────────────────────
    def _flow_rows(self):
        flows = keyed(self.ov["root"], "ov.flows")
        rows = [n for n in walk(flows) if isinstance(n, dict) and n.get("t") == "tr" and n["k"][0]["k"][0] != "TICKER"]
        return rows[:6], rows[6:]

    def test_flow_nn_rebased_and_ranked(self):
        """#3: NN cộng KL quy về cp hiện hành (mã có GDKHQ → nhãn E), xếp hạng theo số đã quy đổi."""
        import chaebol_map_data as DATA
        L = T._live_mod.Live(self.ov_ctx)
        for rows, sign in zip(self._flow_rows(), (-1, 1)):
            vals = [float(r["k"][1]["k"][0]) for r in rows]           # nn_node = [số, nhãn bậc]
            self.assertEqual(vals, sorted(vals, key=lambda v: sign * v))
            for r in rows:
                tk = text_of(r["k"][0])
                tiers = [x.get("_tier") for x in walk(r["k"][1]) if isinstance(x, dict) and x.get("_tier")]
                self.assertEqual(tiers, ["EST" if L.nn60(tk)["ev"] else "FACT-T2"], tk)
        # đối chiếu độc lập theo từng phiên cho VHM (thưởng 100% GDKHQ 06/08/2026)
        ph = DATA.price_history("VHM")
        S, C, A, V = (ph.col(c) for c in ("totalShares", "closePrice", "closePriceAdjusted", "foreignNetVolumeTotal"))
        a = len(ph) - 60
        mult, want = 1.0, 0.0
        for i in range(len(ph) - 1, a - 1, -1):
            want += (V[i] or 0) * mult
            if i > a and S[i] and S[i - 1] and C[i] and C[i - 1]:
                js, jf = S[i] / S[i - 1], (A[i] / C[i]) / (A[i - 1] / C[i - 1])
                if min(js, jf) > 1.001:
                    mult *= min(js, jf)
        self.assertAlmostEqual(L.nn60("VHM")["nn"], want / 1e6, places=3)

    def test_flow_td_window_marked(self):
        """#2: TD thiếu phiên → ghi 'n/60 phiên, tới dd/mm'; phần dư chỉ trên đúng các phiên TD đủ, còn lại bỏ."""
        for r in sum(self._flow_rows(), []):
            note = text_of(r["k"][3])
            self.assertTrue(re.search(r"phần dư [-+]\d", note) or "không so sánh được" in note, note)
            m = re.search(r"\((\d+)/60 phiên, tới \d\d/\d\d\)", note)
            if m and re.search(r"phần dư [-+]", note):
                self.assertIn("(cùng %s phiên)" % m.group(1), note)
        t = text_of(keyed(self.ov["root"], "ov.flows"))
        self.assertIn("quy về số cp hiện hành", t)

    def test_no_regrade_of_v21_stance(self):
        """#1 #5 #9 #10 #11: không BỊ BÁC cho luận điểm/tín hiệu/TIER V21 hay dữ kiện chỉ có U."""
        def pills(node):
            return [text_of(n) for n in walk(node) if isinstance(n, dict) and n.get("t") == "span"
                    and text_of(n) in ("ĐẠT", "BỊ BÁC", "CHƯA RÕ")]
        self.assertEqual(pills(keyed(self.ov["root"], "ov.trend2.upd")), [])
        for k in ("map.row.4", "map.row.24"):
            self.assertNotIn("BỊ BÁC", pills(keyed(self.map["root"], k)), k)
        r4, r24 = text_of(keyed(self.map["root"], "map.row.4")), text_of(keyed(self.map["root"], "map.row.24"))
        self.assertIn("BULL", r4)
        self.assertIn("[CẦN DATA", r4)
        self.assertNotIn("không còn khớp", r4)
        self.assertNotIn("Distress' bị bác", r24)
        self.assertIn("V21·12/05", r24)
        self.assertEqual(pills(keyed(self.map["root"], "map.pattern.p2")), ["CHƯA RÕ"])
        self.assertIn("chưa đọc văn bản tố tụng", text_of(keyed(self.map["root"], "map.pattern.p2")))
        bt = keyed(self.map["root"], "map.grp.bauthuy.upd")
        lps = next(r for r in bt["k"] if "LPS" in text_of(r))
        self.assertEqual(pills(lps), ["CHƯA RÕ"])

    def test_tier_split_and_mark_style(self):
        """#6 #8 #12: vế U/E không nằm dưới nhãn T1/T2; ↻ không đứng trần trong tiêu đề; tiêu đề cột Bridge không nhãn."""
        bt = keyed(self.map["root"], "map.grp.bauthuy.upd")
        first = bt["k"][0]
        self.assertEqual([x["_tier"] for x in walk(first) if isinstance(x, dict) and x.get("_tier")],
                         ["FACT-T1", "UNVERIFIED"])
        r10 = keyed(self.map["root"], "map.row.10")
        self.assertIn("EST", [x["_tier"] for x in walk(r10) if isinstance(x, dict) and x.get("_tier")])
        h2 = next(n for n in walk(keyed(self.ov["root"], "ov.flows")) if isinstance(n, dict) and n.get("t") == "h2")
        self.assertNotIn("↻", text_of(h2))
        br = keyed(self.ov["root"], "ov.bridge")
        labels = [n for n in walk(br) if isinstance(n, dict) and n.get("t") == "div"
                  and text_of(n).startswith(("V20 (HIỆN TẠI)", "V21 (★ MỚI)"))
                  and (n.get("s") or {}).get("letterSpacing") == ".2em"]
        self.assertEqual(len(labels), 2)
        for n in labels:
            self.assertFalse([x for x in walk(n) if isinstance(x, dict) and x.get("_tier")])

    def test_pvn_row_one_anchor(self):
        """#4: BSR/GAS/PLX cùng mốc 08/05, nhãn E, khớp số Hypothesis."""
        import chaebol_map_data as DATA
        r6 = text_of(keyed(self.map["root"], "map.row.6"))
        self.assertNotIn("07/05", r6)
        for tk in ("BSR", "GAS", "PLX"):
            v = DATA.pct_change(tk, "2026-05-08").value
            self.assertIn("%s %s" % (tk, D.sign_fixed(v, 1, strict=True) + "%"), r6)

    def test_pattern_suffix_outside_tv30(self):
        """#7: 'Pattern A/B' của cụm có mã ngoài 30 mã Toàn Vũ mang '?'."""
        t = text_of(keyed(self.ov["root"], "ov.flows"))
        self.assertIn("Pattern A? textbook", t)
        self.assertIn("Pattern B? textbook", t)
        self.assertIn("★ Đáy Pattern B? đang form", text_of(keyed(self.ov["root"], "ov.phase")))

    # ── hoàn thiện 27/09 (final_check §6.1 #12) ──────────────────────────────
    def test_insider_rows_follow_claims_tab(self):
        """Hàng 19/20: ô V21 chỉ mô tả giao dịch nội bộ, không có mệnh đề 'insider exit' → không Pill; note V21 giữ
        + U + V21·12/05; dữ kiện T2 chỉ nêu chiều MUA; trạng thái C11/C12·20 lấy đúng từ mảnh claims (tab 09)."""
        if not (self.dossier or {}).get("overview"):
            self.skipTest("chưa có mảnh dossier overview")
        c20 = (self.dossier or {}).get("claims20") or {}
        status = ("ĐẠT", "BỊ BÁC", "CHƯA RÕ", "LIVE", "HẾT HẠN", "TIỀN ĐỀ SAI")
        for n, v21, cid in ((19, "VPBankS catalyst · Phạm Thị Nhung GD 5/5", "C11"),
                            (20, "Vietravel Airlines cạnh tranh VJC · 5 INSIDER ESOP", "C12")):
            row = keyed(self.map["root"], "map.row.%d" % n)
            t = text_of(row)
            self.assertEqual([text_of(x) for x in walk(row) if isinstance(x, dict) and x.get("t") == "span"
                              and text_of(x) in status], [], n)
            self.assertIn(v21, t)
            self.assertIn("V21·12/05", t)
            self.assertIn("giao dịch MUA" if n == 20 else "đăng ký MUA 30M cp", t)
            self.assertNotIn("insider exit' là ngược", t)
            self.assertNotIn("MUA cp ESOP", t)                      # vc_lk không ghi loại ESOP → không nêu ở T2
            if cid in c20:
                self.assertIn("claim %s·20 (tab 09 chấm %s)" % (cid, c20[cid]["status"]), t)
            else:
                self.assertIn("[CẦN DATA — trạng thái %s·20" % cid, t)
            kids = row["k"][-1]["k"]                                   # ô WEALTH / NOTE (seg: con riêng)
            i = kids.index(v21)
            self.assertEqual((kids[i + 1].get("_tier"), bool(kids[i + 2].get("_v21"))), ("UNVERIFIED", True))

    def test_vpx_first_below_80(self):
        """F6-042 (sửa 27/09): VPX đóng < 80% giá chào sàn lần đầu 02/06, không phải 13/07 — hàng 19 và Pattern 1 cùng
        mốc; đối chiếu độc lập price-history tới 25/09 (số trong câu mang ngày 25/09)."""
        import chaebol_map_data as DATA
        ph = DATA.price_history("VPX")
        if ph is None or ph.dates[-1] < "2026-09-25":
            self.skipTest("thiếu price-history VPX tới 25/09")
        ref, close = ph.col("referencePrice")[0], ph.col("closePrice")
        thr = 0.8 * ref
        below = [d for d, c in zip(ph.dates, close) if c and c < thr]
        self.assertEqual((ref, below[0]), (33900.0, "2026-06-02"))
        self.assertTrue(all(close[i] < thr for i in range(ph.at("2026-07-21"), ph.at("2026-09-25") + 1)))
        self.assertGreaterEqual(close[ph.at("2026-07-17")], thr)
        self.assertEqual(D.to_fixed(close[ph.at("2026-09-25")] / ref * 100, 1), "75.1")
        for key in ("map.row.19", "map.pattern.p1"):
            t = text_of(keyed(self.map["root"], key))
            self.assertIn("giá chào sàn 33,900 lần đầu 02/06", t, key)
            self.assertIn("25/09 còn 75.1%", t, key)
            self.assertNotIn("dưới 80% giá IPO từ 13/07", t, key)


class _FakeData:
    """Lớp dữ liệu giả 10 phiên: thưởng 100% GDKHQ ở phiên 6 (cp 100→200, giá điều chỉnh/giá = 0,5→1); NN (i+1) M cp
    mỗi phiên; tự doanh 1 M cp/phiên, vắng các phiên `td_missing`."""

    def __init__(self, td_missing):
        import chaebol_map_data as DATA
        self.DATA = DATA
        dates = ["2026-09-%02d" % d for d in range(10, 20)]
        rows = [[d, 100.0 if i < 5 else 200.0, 50.0 if i < 5 else 100.0, 100.0, (i + 1) * 1e6]
                for i, d in enumerate(dates)]
        self.ph = DATA.Cols(["tradingDate", "totalShares", "closePriceAdjusted", "closePrice",
                             "foreignNetVolumeTotal"], rows)
        self.td = {d: 1e6 for i, d in enumerate(dates) if i not in td_missing}

    def price_history(self, tk):
        return self.ph

    def adj_steps(self, tk, d0, d1=None):
        return [(self.ph.dates[5], 0.5)] if self.ph.dates[5] > d0 else []

    def _win(self, n, end):
        b = self.ph.at(end)
        return max(0, b - n + 1), b

    def foreign_net(self, tk, n=60, end=None):
        a, b = self._win(n, end)
        return {"vol": self.DATA.V(sum(self.ph.col("foreignNetVolumeTotal")[a:b + 1]), None, "FACT-T2"),
                "n": b - a + 1, "to": self.ph.dates[b]}

    def prop_net(self, tk, n=60, end=None, kind="total"):
        a, b = self._win(n, end)
        got = [self.td[d] for d in self.ph.dates[a:b + 1] if d in self.td]
        v = self.DATA.V(sum(got), None, "FACT-T2") if got else self.DATA.can_data("trống")
        return {"vol": v, "n": b - a + 1, "n_co": len(got), "complete": len(got) == b - a + 1}

    def pct_change(self, tk, d0, d1=None):
        return self.DATA.V(12.34, None, "EST")

    def tv30(self):
        return ["ACB", "SSI"]


@unittest.skipIf(V21 is None, "thiếu v21_const.json")
class LiveFlowLogic(unittest.TestCase):
    """Logic quy đổi KL qua GDKHQ + cửa sổ TD trên dữ liệu giả (không phụ thuộc kho)."""

    def live(self, td_missing):
        ctx = ctx_for("live", data=_FakeData(td_missing), dossier={"overview": {"ov": {}, "map": {}}})
        return T._live_mod.Live(ctx)

    def test_trailing_td_gap(self):
        r = self.live({9}).nn60("FAKE", n=10)
        self.assertAlmostEqual(r["nn"], 2 * (1 + 2 + 3 + 4 + 5) + (6 + 7 + 8 + 9 + 10))
        self.assertEqual(r["ev"], [("2026-09-15", 2.0)])
        self.assertEqual((r["n_co"], r["n"], r["td_to"], r["du_n"]), (9, 10, "2026-09-18", 9))
        self.assertAlmostEqual(r["td"], 2 * 5 + 4)
        self.assertAlmostEqual(r["du"], -((2 * 15 + 30) + (2 * 5 + 4)))    # NN và TD cùng 9 phiên đầu

    def test_interior_td_gap(self):
        L = self.live({2, 9})
        r = L.nn60("FAKE", n=10)
        self.assertIsNone(r["du"])
        with D.use_mode("live", "2026-09-27"):
            note = "".join(x if isinstance(x, str) else text_of(x) for x in L._td_note(r, "EST"))
        self.assertIn("(8/10 phiên, tới 18/09)", note)
        self.assertIn("không so sánh được", note)

    def test_placeholders_and_pattern(self):
        L = self.live(set())
        with D.use_mode("live", "2026-09-27"):
            out = L._part({"text": "NN {nn60:FAKE} 60 phiên; {since:FAKE} từ 08/05", "tier": "FACT-T2"})
        txt = "".join(x if isinstance(x, str) else text_of(x) for x in out)
        self.assertIn("NN +70.0M cp 60 phiên; +12.3% từ 08/05 (KL quy về cp hiện hành: GDKHQ 15/09 ×2.000)", txt)
        self.assertEqual(out[-1]["_tier"], "EST")                    # bậc yếu nhất
        self.assertEqual(L.pattern_q("Pattern A textbook", ["ACB", "TPB"]), "Pattern A? textbook")
        self.assertEqual(L.pattern_q("Pattern A textbook", ["ACB", "SSI"]), "Pattern A textbook")

    def test_claim20_placeholder(self):
        """{c20:Cxx} dẫn trạng thái tab 09 từ khoá claims20 (bậc yếu nhất tính cả bậc mục claim); thiếu → [CẦN DATA]."""
        ctx = ctx_for("live", data=None, dossier={"overview": {"ov": {}, "map": {}}, "claims20": {
            "C11": {"status": "TIỀN ĐỀ SAI", "tier": "EST", "src": "x"}, "C12": {"tier": "FACT-T2", "src": "x"}}})
        L = T._live_mod.Live(ctx)
        with D.use_mode("live", "2026-09-27"):
            out = L._part({"text": "đọc ở claim {c20:C11}; {c20:C12}", "tier": "FACT-T2"})
        txt = "".join(x if isinstance(x, str) else text_of(x) for x in out)
        self.assertIn("đọc ở claim C11·20 (tab 09 chấm TIỀN ĐỀ SAI); [CẦN DATA — trạng thái C12·20 ở mảnh claims]", txt)
        self.assertEqual(out[-1]["_tier"], "EST")
        self.assertIsNone(L.claim20("C12"))                           # mục không có status → không dẫn


if __name__ == "__main__":
    unittest.main()
