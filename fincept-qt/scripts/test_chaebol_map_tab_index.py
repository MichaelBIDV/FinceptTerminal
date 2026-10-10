#!/usr/bin/env python3
"""Unit tests tab ★ ✪ VNINDEX / ★ ✪ VN30 của chaebol_map (chaebol_map_tab_index + _live) — không mạng.

Chạy (cả hai trình thông dịch):
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest scripts/test_chaebol_map_tab_index.py -v
    PYTHONDONTWRITEBYTECODE=1 ~/Library/Application\\ Support/com.fincept.terminal/venv-numpy2/bin/python \\
        -m unittest scripts/test_chaebol_map_tab_index.py

Chuỗi vàng lấy từ chaebol_map_spec/page_p2_index_tabs.md §5–§6 (khớp DOM trang gốc) và §9.1 (golden nếu nối chuỗi,
chỉ kiểm khi kho dừng ở phiên 25/09/2026). v21 cần $B/data/chaebol_map/v21_const.json (vắng → skip); live cần kho
thật (chaebol_map_data + vc_lk; vắng → skip). Socket bị chặn trong tiến trình.
"""
from __future__ import annotations

import json
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
import chaebol_map_tab_index as IX  # noqa: E402

V21_PATH = M.bridge_dir() / "data" / "chaebol_map" / "v21_const.json"
DOSSIER = M.system_dir() / "knowledge_os" / "chaebol_map" / "cap_nhat_2026-09-27.index.json"
_REAL = {}


def setUpModule():
    def blocked(*a, **k):
        raise RuntimeError("mạng bị chặn trong test chaebol_map_tab_index")
    for name in ("socket", "create_connection", "getaddrinfo"):
        _REAL[name] = getattr(socket, name)
        setattr(socket, name, blocked)


def tearDownModule():
    for name, fn in _REAL.items():
        setattr(socket, name, fn)


_V21 = None


def v21():
    global _V21
    if _V21 is None:
        _V21 = json.loads(V21_PATH.read_text(encoding="utf-8")) if V21_PATH.is_file() else {}
    return _V21


def data_mod():
    try:
        import chaebol_map_data as DM
    except Exception:  # noqa: BLE001
        return None
    return DM if (DM.bridge() / "state" / "vc_lk" / "VNINDEX" / "gap-chart.json").is_file() else None


def build(mode, tab, data=True):
    """→ (kết quả builder thô (còn khoá _tier/_can…), ctx). Mode live dùng kho thật trừ khi data=False."""
    with D.use_mode(mode, "2026-09-27"):
        ctx = M.Ctx(mode, date(2026, 9, 27), list(S.TABS_V21))
        ctx.v21 = v21()
        ctx.tab = tab
        if mode == "live" and data:
            ctx.data = data_mod()
            ctx.dossier = M.load_dossier(ctx) if ctx.data is not None else None
        fn = IX.build_vnindex if tab == "vnindex" else IX.build_vn30
        return fn(ctx), ctx


def walk(node, svg=False):
    yield node, svg
    if isinstance(node, dict):
        inside = svg or node.get("t") == "svg"
        for ch in node.get("k", ()):
            yield from walk(ch, inside)


def text_of(node):
    return node if isinstance(node, str) else "".join(text_of(c) for c in node.get("k", ()))


def find_key(node, key):
    return next((n for n, _ in walk(node) if isinstance(n, dict) and n.get("key") == key), None)


def svg_texts(node):
    return [text_of(n) for n, _ in walk(node) if isinstance(n, dict) and n.get("t") == "text"]


def attrs(node, tag):
    return [n.get("a", {}) for n, _ in walk(node) if isinstance(n, dict) and n.get("t") == tag]


# ── luật "mỗi số có nhãn bậc" (DESIGN §8.4) ─────────────────────────────────

NUM_RE = re.compile(r"(?<![vV\d.])(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d+(?:[.,]\d+)?%)")
BLOCK = {"div", "td", "th", "li", "h2", "p", "section", "tr", "table", "tbody", "thead", "ul"}
PILLS = {"ĐẠT", "BỊ BÁC", "CHƯA RÕ", "LIVE", "HẾT HẠN", "CẬP NHẬT"}


def is_label(n):
    if not isinstance(n, dict):
        return False
    if n.get("_tier") or n.get("_can") or n.get("_v21"):
        return True
    return n.get("t") == "span" and (n.get("s") or {}).get("display") == "inline-block" and text_of(n) in PILLS


def bare_numbers(root):
    """Số liệu (thập phân / nhóm nghìn / %) trong HTML không có nhãn (tier, [CẦN DATA], V21·12/05, pill trạng thái)
    đứng sau nó trong CÙNG khối trước số kế tiếp. SVG bỏ qua (chú giải kiểm riêng, trục là thang đo)."""
    bad = []

    def visit(node, pending):
        # pending: danh sách số chưa có nhãn trong khối hiện hành
        for ch in node.get("k", ()):
            if isinstance(ch, str):
                if NUM_RE.search(ch):
                    if pending:
                        bad.append(pending[-1])
                        pending.clear()
                    pending.append(ch)
                continue
            if is_label(ch):
                pending.clear()
                continue
            if ch.get("t") == "svg":
                continue
            if ch.get("t") in BLOCK:
                inner = []
                visit(ch, inner)
                bad.extend(inner)
            else:
                visit(ch, pending)

    top = []
    visit(root, top)
    return bad + top


# ── v21 ─────────────────────────────────────────────────────────────────────


@unittest.skipUnless(V21_PATH.is_file(), "thiếu v21_const.json")
class TestV21(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.vni, _ = build("v21", "vnindex")
        cls.vn30, _ = build("v21", "vn30")

    def test_structure_and_states(self):
        for res, key in ((self.vni, "idx.vnindex"), (self.vn30, "idx.vn30")):
            root = res["root"]
            self.assertEqual(root.get("key"), key)
            self.assertEqual(res["states"], [])          # IndexTab không có state nội bộ
            self.assertEqual([c.get("key") for c in root["k"]], ["idx.s%d" % i for i in range(1, 7)])
            self.assertNotIn("csv", res)
        titles = [text_of(s["k"][0]["k"][1]) for s in self.vni["root"]["k"]]
        self.assertEqual(titles, ["VN-Index — Pillar IV Flow & Chu kỳ",
                                  "📈 VN-Index Weekly Price + 5 Chu kỳ BSC overlay",
                                  "🌊 Cumulative Flow 4 channels — Toàn Vũ Pillar IV",
                                  "📊 Flow cumulative — 5w / 30w / 60w",
                                  "🔄 Chu kỳ phân tích — Toàn Vũ × Wyckoff × BSC framework",
                                  "📚 Phương pháp luận + Cutover policy"])

    def test_no_live_marks_in_v21(self):
        for res in (self.vni, self.vn30):
            _, st = D.finalize(res["root"])
            self.assertEqual((st["tiers"], st["can_data"], st["upd"], st["v21"]), ({}, 0, 0, 0))

    def test_golden_vnindex(self):
        t = text_of(self.vni["root"])
        for g in ("1327 weekly bars · 25.8 năm · FiinTrade verified 2000-07-28→2026-05-08 · NgườiQuanSát forward "
                  "≥09/05/2026", "GIÁ ĐÓNG CỬA (8/5)1,915.37+3.31%", "TỪ ĐÁY LỊCH SỬ+1815%vs 2000-07-28 (100)",
                  "WEEKLY BARS13272000-2026", "DATA SOURCEDUALFiinTrade ≤8/5 · NQS ≥9/5",
                  "5 tuần (4-8/5/26)+331.4-129.1+52.6-254.9-0.0", "30 tuần (~7 tháng)+411.5+802.1+264.3-1477.90.0",
                  "60 tuần (~14 tháng)+1408.4+982.3+321.8-2712.40.1", "~14.0××", "⑤ ★",
                  "VN-Index đóng cửa ATH 8/5 = 1915.37 (FiinTrade verified). GTGD HSX ATH 36,814 tỷ/phiên",
                  "VCB P/B 2.0× = 10-yr low → best deep-value pick trong môi trường định giá đỉnh.",
                  "SIGNAL: ★ TRANSITIONING-LATE-2-TO-3 (Q2/26 confirmed)",
                  "FiinTrade source files (10/5/2026 export):• FiinTrade_Phân_Loại_Nhà_Đầu_Tư_VNINDEX_20260510 (2).xlsx"):
            self.assertIn(g, t)

    def test_golden_vn30(self):
        t = text_of(self.vn30["root"])
        for g in ("VN30 — Pillar IV Flow & Chu kỳ", "737 weekly bars · 14.2 năm · FiinTrade verified 2012-02-10→",
                  "2,074.06+2.54%", "+353%vs 2012-02-10 (458.23)", "7372012-2026",
                  "5 tuần (4-8/5/26)+195.5-33.7+32.8-194.5", "30 tuần (~7 tháng)+287.6+450.3+103.3-841.3-0.0",
                  "60 tuần (~14 tháng)+1264.2+504.3+94.2-1862.70.0", "VN30 đóng cửa ATH 8/5 = 2074.06",
                  "📈 VN30 Weekly Price + 5 Chu kỳ BSC overlay"):
            self.assertIn(g, t)
        self.assertEqual(self.vn30["root"]["k"][0]["k"][0]["k"][0]["s"]["background"], "#a78bfa")

    def test_minichart_geometry_vnindex(self):
        svg = find_key(self.vni["root"], "idx.minichart")
        self.assertEqual(svg["a"], {"width": 1200, "height": 300, "viewBox": "0 0 1200 300"})
        tx = svg_texts(svg)
        self.assertEqual(tx[:5], ["100", "554", "1008", "1462", "1915"])
        years = [(a["x"], y) for a, y in zip(attrs(svg, "text")[5:14], tx[5:14])]
        self.assertEqual([y for _, y in years], [str(y) for y in range(2001, 2026, 3)])
        self.assertEqual([round(x, 1) for x, _ in years],
                         [98.1, 229.1, 359.3, 490.3, 620.4, 752.3, 884.1, 1016.8, 1149.5])
        rects = attrs(svg, "rect")
        self.assertEqual(len(rects), 4)                   # ⑤ không vẽ (regex năm cuối hỏng)
        self.assertEqual([round(r["width"], 2) for r in rects], [86.77, 0, 87.62, 89.32])
        self.assertEqual([r["fill"] for r in rects], ["#fb923c", "#34d399", "#60a5fa", "#a78bfa"])
        self.assertAlmostEqual(rects[0]["x"], 229.95, places=2)
        self.assertEqual(tx[14:18], ["① +346%", "② +165%", "③ +130%", "④ +131%"])
        c = attrs(svg, "circle")[0]
        self.assertEqual((c["cx"], round(c["cy"], 1), c["fill"]), (1164, 36.0, "#5b8db8"))
        self.assertTrue(attrs(svg, "path")[0]["d"].startswith("M36.0,264.0 L"))

    def test_minichart_vn30_no_overlay(self):
        svg = find_key(self.vn30["root"], "idx.minichart")
        self.assertEqual(attrs(svg, "rect"), [])
        self.assertEqual(svg_texts(svg)[:5], ["442", "852", "1261", "1671", "2080"])
        self.assertEqual(svg_texts(svg)[5:], ["2013", "2016", "2019", "2022", "2025"])
        self.assertEqual(attrs(svg, "path")[0]["stroke"], "#a78bfa")

    def test_flowchart(self):
        for res, lab in ((self.vni, ["0", "8967", "-8790", "━ Cá nhân: 8967M", "━ Tổ chức: -1183M",
                                      "━ Tự doanh: 1259M", "━ Nước ngoài: -8790M"]),
                         (self.vn30, ["0", "3719", "-5468", "━ Cá nhân: 3719M", "━ Tổ chức: 362M",
                                      "━ Tự doanh: 566M", "━ Nước ngoài: -5468M"])):
            svg = find_key(res["root"], "idx.flowchart")
            self.assertEqual(svg_texts(svg), lab)
            self.assertEqual([p["strokeWidth"] for p in attrs(svg, "path")], ["1.4", "1.4", "1.4", "1.6"])
            self.assertEqual(attrs(svg, "g")[0]["transform"], "translate(980, 32)")
        yz = attrs(find_key(self.vni["root"], "idx.flowchart"), "line")[0]["y1"]
        self.assertAlmostEqual(yz, 141.04, places=2)

    def test_helpers(self):
        self.assertEqual(IX.cycle_bounds("T4/2025-Q2/2026"), (2025, 2027))
        self.assertEqual(IX.cycle_bounds("T2/2009-T10/2009"), (2009, 2009))
        self.assertEqual(IX.years_covered("2012-02-10", "2026-05-08"), "14.2")
        rows = [["2000-07-28", 1], ["2000-08-04", 1], ["2001-01-05", 1], ["2001-12-28", 1], ["2002-01-04", 1]]
        self.assertEqual(IX.year_ticks(rows), [("2001", 3)])   # năm %3 ghi đè bằng chỉ số CUỐI năm

    def test_core_inventory_ok(self):
        with D.use_mode("v21", "2026-09-27"):
            ctx = M.Ctx("v21", date(2026, 9, 27), list(S.TABS_V21))
            ctx.v21 = v21()
            for tab in ("vnindex", "vn30"):
                res, status = M.run_tab(tab, tab, ctx)
                self.assertEqual(status, "ok")
                self.assertEqual(res["states"], [])
        self.assertFalse([w for w in ctx.warnings if w.startswith(("[vnindex]", "[vn30]"))])


# ── live ────────────────────────────────────────────────────────────────────


@unittest.skipUnless(V21_PATH.is_file() and data_mod() is not None, "thiếu v21_const hoặc kho sống")
class TestLive(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.vni, cls.ctx_vni = build("live", "vnindex")
        cls.vn30, cls.ctx_vn30 = build("live", "vn30")
        cls.golden = data_mod().data_to() == "2026-09-25"

    def test_builds_without_warnings(self):
        for res, ctx in ((self.vni, self.ctx_vni), (self.vn30, self.ctx_vn30)):
            self.assertEqual(res["states"], [])
            self.assertEqual([c.get("key") for c in res["root"]["k"]], ["idx.s%d" % i for i in range(1, 7)])
            self.assertFalse([w for w in ctx.warnings if "lỗi" in w], ctx.warnings)
            D.finalize(res["root"])                      # tuần tự hoá được

    def test_every_number_has_tier(self):
        for res in (self.vni, self.vn30):
            self.assertEqual(bare_numbers(res["root"]), [])
            with D.use_mode("live", "2026-09-27"):
                _, st = D.finalize(res["root"])
            self.assertGreater(st["tiers"].get("FACT-T2", 0), 40)
            self.assertGreater(st["can_data"], 10)
            self.assertGreater(st["v21"], 6)

    def test_flow_legend_tiers(self):
        """Chú giải giữ khung V21 200×68 @ (980, 32) — không che đuôi đường (kiểm chứng 27/09 #8); nguồn + CN/TC
        [CẦN DATA] nằm ở chú thích dưới biểu đồ."""
        for res in (self.vni, self.vn30):
            svg = find_key(res["root"], "idx.flowchart")
            leg = [n for n, _ in walk(svg) if isinstance(n, dict) and n.get("t") == "text"
                   and text_of(n).startswith(("━", "CN/TC"))]
            self.assertEqual(len(leg), 4)
            for n in leg:
                self.assertTrue(any(isinstance(c, dict) and c.get("_tier") for c in n["k"]), text_of(n))
            self.assertEqual(attrs(svg, "g")[-1]["transform"], "translate(980, 32)")
            box = attrs(svg, "rect")[-1]
            self.assertEqual((box["width"], box["height"]), ("200", "68"))
            cap = text_of(find_key(res["root"], "idx.s3"))
            self.assertIn("Cá nhân / Tổ chức nội sau 08/05: [CẦN DATA", cap)
            self.assertIn("Chú giải: Cá nhân, Tổ chức = FiinTrade, dừng ở 08/05/2026T2·08/05", cap)

    def test_flow_dates_are_session_dates(self):
        """#1: nhãn ngày của Σ rổ TD/NN = phiên cuối có số thật (tự doanh chậm), không phải ngày tuần của chỉ số."""
        for res in (self.vni, self.vn30):
            svg = find_key(res["root"], "idx.flowchart")
            leg = {text_of(n).split(":")[0]: text_of(n) for n, _ in walk(svg)
                   if isinstance(n, dict) and n.get("t") == "text" and text_of(n).startswith("━")}
            s3, s4 = text_of(find_key(res["root"], "idx.s3")), text_of(find_key(res["root"], "idx.s4"))
            self.assertIn("tự doanh có số tới", s3)
            if not self.golden:
                continue
            self.assertTrue(leg["━ Tự doanh"].endswith("E·24/09"), leg)
            self.assertTrue(leg["━ Nước ngoài"].endswith("E·25/09"), leg)
            new = s4.split("CỬA SỔ MỚI")[1]
            self.assertEqual((new.count("E·24/09"), new.count("E·25/09")), (3, 3))   # cột TD / NN × 3 cửa sổ
            self.assertIn("Tuần 21–25/09: tự doanh có số tới 24/09 ở", s3)
            self.assertIn("tự doanh mới có số tới 24/09", s4)

    def test_basket_flow_share_basis(self):
        """§6.1 #16: Σ rổ NN/TD sau 08/05 = KL từng mã quy về số cp hiện hành (basket_weekly_flow adjust=True), không
        cộng KL thô hai cơ sở qua GDKHQ; chú thích S3/S4 + CSV ghi cơ sở; ngày nhãn TD = td_last của lõi, trùng ngày
        đầu của phân bố theo mã trong chú thích."""
        DM = data_mod()
        for res, b in ((self.vni, "VNINDEX"), (self.vn30, "VN30")):
            adj = DM.basket_weekly_flow(b, start="2026-05-08", adjust=True)
            raw = {r["monday"]: r for r in DM.basket_weekly_flow(b, start="2026-05-08").value}
            by = {r["monday"]: r for r in adj.value}
            live = [r for r in res["csv"][1:] if r[8] != "FiinTrade (V21)"]
            if self.golden:
                self.assertEqual(len(live), 20)
            moved = 0
            for r in live:
                d = date.fromisoformat(r[1])
                mon = (d - timedelta(days=d.weekday())).isoformat()
                f, g = by[mon], raw[mon]
                self.assertEqual((r[6], r[7]), (DM.round_half(f["td_khop_vol"] / 1e6, 2),
                                                DM.round_half(f["nn_vol"] / 1e6, 2)), r)
                self.assertIn("NN/TD quy về số cp hiện hành", r[9])
                moved += (r[6], r[7]) != (DM.round_half(g["td_khop_vol"] / 1e6, 2), DM.round_half(g["nn_vol"] / 1e6, 2))
            if "quy về số cp hiện hành qua GDKHQ" in (adj.note or "") and not adj.note.endswith("ở 0 mã"):
                self.assertGreater(moved, 0)                 # có GDKHQ trong cửa sổ → số đổi so với KL thô
            s3, s4 = text_of(find_key(res["root"], "idx.s3")), text_of(find_key(res["root"], "idx.s4"))
            self.assertIn("TD/NN + Σ rổ (KL quy đổi quyền)E", s3)
            self.assertIn("quy về số cp hiện hành qua GDKHQ chia/thưởng/cổ tức CP/quyền mua (", s3)
            self.assertIn("FiinTrade ≤08/05 giữ KL thô lúc đó", s3)
            self.assertIn("NN/TD sau 08/05 tính theo số cp hiện hành (quy đổi quyền", s4)
            td = adj.value[-1]["td_last"]
            leg = [text_of(n) for n, _ in walk(find_key(res["root"], "idx.flowchart"))
                   if isinstance(n, dict) and n.get("t") == "text" and text_of(n).startswith("━ Tự doanh")]
            self.assertTrue(leg[0].endswith("E·%s/%s" % (td[8:10], td[5:7])), leg)
            self.assertIn("tự doanh có số tới %s/%s ở " % (td[8:10], td[5:7]), s3)
        if self.golden:                                      # api_data §2.4: VN30 tuần 21/09 adjust=True
            wk = [r for r in self.vn30["csv"] if r[1] == "2026-09-25"][0]
            self.assertEqual((wk[6], wk[7]), (7.14, -82.7))
            new = text_of(find_key(self.vn30["root"], "idx.s4")).split("CỬA SỔ MỚI")[1]
            self.assertIn("+9.0E·24/09+17.5E·25/09dư -26.5E", new)   # KL thô: -0.9 / +18.2 / dư -17.3
            self.assertIn("12/30 mã: ACB, BID, FPT, HPG, MBB, SSB, SSI, TCX, VHM, VIB, VJC, VPB",
                          text_of(find_key(self.vn30["root"], "idx.s3")))
            self.assertIn("(65/200 mã)", text_of(find_key(self.vni["root"], "idx.s3")))

    def test_as_of_wording(self):
        """§6.1 #17 / DESIGN §11.3: 'as of' chỉ ở dòng CỔNG của Header; tab index viết 'tính đến dd/mm/yyyy' và dòng
        CỔNG ở S6 mang đúng ngày as_of của CỔNG (cùng ngày Header in)."""
        cg = data_mod().cong()
        for res in (self.vni, self.vn30):
            self.assertIsNone(re.search(r"\bas of\b", text_of(res["root"]), re.I))
            s6 = text_of(find_key(res["root"], "idx.s6"))
            self.assertIn("CỔNG:", s6)
            if cg.get("as_of"):
                d = cg["as_of"]
                self.assertIn(" · tính đến %s/%s/%s" % (d[8:10], d[5:7], d[:4]), s6)

    def test_ssi_claims_not_dat_without_horizon(self):
        """#2: nguyên văn SSI không ghi horizon → tối đa CHƯA RÕ (kể cả khi giá đã chạm 1,920)."""
        t = text_of(self.vni["root"])
        self.assertIn("SSI 9/5 (nguyên văn không ghi horizon): base 1,920 CHƯA RÕ (đã chạm", t)
        self.assertNotIn("base 1,920 ĐẠT", t)
        d = json.loads(DOSSIER.read_text(encoding="utf-8"))["index"]["claims"]
        self.assertEqual((d["SSI_BASE_1920"]["status"], d["SSI_BEAR_1650"]["status"]), ("CHƯA RÕ", "CHƯA RÕ"))

    def test_liquidity_split_dates(self):
        """#3: 19,0 nghìn tỷ mang ngày 18/09; YTD −8,5% mang ngày 11/09 (hai nhãn riêng)."""
        t = text_of(self.vni["root"])
        self.assertIn("19,0 nghìn tỷ/phiên (tuần FTSE)T3·18/09", t)
        self.assertIn("YTD −8,5% y/y (luỹ kế tới 11/09)T3·11/09", t)

    def test_vn30_cycle_labels(self):
        """#4/#11: tab VN30 không gán ⑤ của VN-Index cho VN30; không nhận vẽ ①–④ khi biểu đồ không có dải."""
        sub = text_of(find_key(self.vn30["root"], "idx.s2"))
        self.assertIn("⑤ (VN-Index) đo lại", sub)
        self.assertNotIn("①–④ BSCT3", sub)
        self.assertIn("không vẽ trên VN30", sub)
        self.assertIn("5 CHU KỲ TĂNG GIÁ — BSC FRAMEWORK · SỐ CỦA VN-INDEX", text_of(self.vn30["root"]))
        self.assertNotIn("SỐ CỦA VN-INDEX", text_of(self.vni["root"]))
        if self.golden:
            self.assertIn("đáy đóng 1,168.68 (09/04/2025)", sub)
            self.assertIn("2,096.76 (07/01/2026)", sub)

    def test_no_signed_zero_and_vietnamese(self):
        """#5/#6/#7: không '-0.0'/'+0.0'; chữ mới không còn Downtrend/Risk-Off/as of/TBD/Outlier."""
        zero = re.compile(r"(?<![\d.])[-+]0\.0+(?!\d)")
        for res in (self.vni, self.vn30):
            html = [n for n, svg in walk(res["root"]) if isinstance(n, str) and not svg]
            self.assertFalse([s for s in html if zero.search(s)])
            t = text_of(res["root"])
            for bad in ("Downtrend", "Risk-Off", " as of ", "SIGNAL: TBD", "Outlier", "Phase 3 hay Phase 4"):
                self.assertNotIn(bad, t)
            self.assertIn("SIGNAL: chưa xác định (bản V21 để trống)V21·12/05", t)

    def test_cycle5_band_by_date(self):
        """#9: dải ⑤ phủ tuần chứa đáy 09/04/2025 tới tuần chứa đỉnh — không theo luật năm (01/2025→01/2026)."""
        rows = data_mod().index_weekly_spliced("VNINDEX").value
        n = len(rows)
        xs = lambda i: 36 + i / (n - 1) * 1128  # noqa: E731
        lo = min((i for i, r in enumerate(rows) if r["date"][:4] == "2025"), key=lambda i: rows[i]["c"])
        hi = max((i for i, r in enumerate(rows) if r["date"] >= "2026-01-01"), key=lambda i: rows[i]["c"])
        y25 = next(i for i, r in enumerate(rows) if r["date"][:4] == "2025")
        r5 = attrs(find_key(self.vni["root"], "idx.minichart"), "rect")[4]
        self.assertLessEqual(r5["x"], xs(lo) + 1e-6)
        self.assertGreaterEqual(r5["x"] + r5["width"], xs(hi) - 1e-6)
        self.assertGreater(r5["x"], xs(y25) + 1)

    def test_can_data_nowrap(self):
        """#10: [CẦN DATA…] không ngắt dòng giữa '[CẦN' và 'DATA]'."""
        for res in (self.vni, self.vn30):
            cans = [n for n, svg in walk(res["root"]) if isinstance(n, dict) and n.get("_can") and not svg]
            self.assertTrue(cans)
            self.assertTrue(all((n.get("s") or {}).get("whiteSpace") == "nowrap" for n in cans))

    def test_stance_kept_with_v21_mark(self):
        t = text_of(self.vni["root"])
        self.assertIn(IX.READING_STRONG + "V21·12/05", t)
        self.assertIn("SIGNAL: ⚠ UTAD watch Q3/26V21·12/05", t)
        self.assertIn("risk/reward asymmetric XẤU.V21·12/05", t)
        self.assertIn("best deep-value pick trong môi trường định giá đỉnh.V21·12/05", t)

    def test_flows_after_cut(self):
        t = text_of(self.vni["root"])
        self.assertIn("CỬA SỔ MỚI TỚI", t)
        self.assertNotIn("NgườiQuanSát forward ≥09/05/2026", t)
        self.assertIn("CỔNG:", t)
        tr = [n for n, _ in walk(self.vni["root"]) if isinstance(n, dict) and n.get("t") == "tr"]
        new = [r for r in tr if text_of(r).startswith(("5 tuần (28", "5 tuần (")) and "[CẦN DATA]" in text_of(r)]
        self.assertTrue(new)
        for r in new:                                   # CN/TC luôn [CẦN DATA], không bao giờ 0
            cells = [c for c in r["k"] if isinstance(c, dict)]
            self.assertEqual(text_of(cells[1]), "[CẦN DATA]")
            self.assertEqual(text_of(cells[2]), "[CẦN DATA]")

    def test_csv(self):
        csv = self.vni.get("csv")
        self.assertEqual(csv[0][:3], ["chi_so", "tuan_ket_thuc", "dong_cua"])
        self.assertEqual(csv[1][1], "2026-05-08")
        self.assertTrue(all(r[5] is None for r in csv[2:]))   # tc sau mốc = None

    def test_golden_live(self):
        if not self.golden:
            self.skipTest("kho đã qua phiên 25/09/2026 — golden §9.1 không còn áp dụng")
        t = text_of(self.vni["root"])
        for g in ("1347 weekly bars · 26.2 năm", "GIÁ ĐÓNG CỬA (25/9)1,785.11T2·25/09-1.68%E", "+1685%E",
                  "1347E", "+76.2%", "1,927.94", "1,668.53", "12.40×"):
            self.assertIn(g, t)
        self.assertEqual(svg_texts(find_key(self.vni["root"], "idx.minichart"))[:5],
                         ["100", "555", "1011", "1466", "1922"])
        t30 = text_of(self.vn30["root"])
        for g in ("757 weekly bars · 14.6 năm", "1,938.5T2·25/09-1.31%E", "+323%E", "2,096.76", "1,806.50"):
            self.assertIn(g, t30)

    def test_dossier_fragment(self):
        self.assertTrue(DOSSIER.is_file())
        d = json.loads(DOSSIER.read_text(encoding="utf-8"))
        self.assertEqual(d["schema"], "chaebol_map_capnhat/1")
        items = [v for sec in ("facts", "claims", "text") for v in d["index"][sec].values()]
        self.assertTrue(items)
        for it in items:
            self.assertTrue(it.get("src") and it.get("tier") and it.get("asof"), it)
        self.assertIn("GTGD bq tuần 14–18/09", text_of(self.vni["root"]))    # đọc qua ctx.dossier
        fb = d["index"]["text"]["flow_basis"]                                # §6.1 #16: cơ sở KL + tác động đo
        self.assertEqual(set(fb["tac_dong"]), {"VNINDEX", "VN30"})
        for b in fb["tac_dong"].values():
            self.assertEqual(len(b["nn_M"]), 2)
        if self.golden:                                     # tệp = dossier_part() trên kho 25/09 (không trôi)
            import chaebol_map_tab_index_dossier as XD
            self.assertEqual(XD.dossier_part(data_mod()), d)
            self.assertEqual(fb["tac_dong"]["VN30"]["td_khop_5tuan_M"], [-0.94, 9.0])

    def test_live_without_data_module(self):
        res, ctx = build("live", "vnindex", data=False)
        self.assertEqual(bare_numbers(res["root"]), [])
        self.assertIn("[CẦN DATA", text_of(res["root"]))
        self.assertTrue(any("chaebol_map_data" in w for w in ctx.warnings))


if __name__ == "__main__":
    unittest.main()
