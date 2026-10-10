#!/usr/bin/env python3
"""Unit tests cho Deep-dive 10 sub-tab của tab codong (chaebol_map_tab_codong_deep + _chart + _live + _common),
không mạng.

Chạy (cả hai trình thông dịch, PYTHONDONTWRITEBYTECODE=1):
    python3 -m unittest scripts/test_chaebol_map_tab_codong_deep.py -v
    ~/Library/Application\\ Support/com.fincept.terminal/venv-numpy2/bin/python -m unittest \\
        scripts/test_chaebol_map_tab_codong_deep.py

Chuỗi vàng lấy từ chaebol_map_spec/page_p3b_deepdive10.md (§3–§6) và page_p3a §S3; bản v21 đã khớp ảnh ref 19–31
≥ 99,97 % vùng khối Deep-dive qua oracle Chrome (27/09/2026). Test live trên kho thật (chỉ đọc) bỏ qua khi thiếu
v21_const / vc_lk; test live với lớp dữ liệu None kiểm mọi số mới thành [CẦN DATA].
"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("CHB_TODAY", "2026-09-27")

import chaebol_map as M  # noqa: E402
import chaebol_map_dom as D  # noqa: E402
import chaebol_map_tab_codong_common as CO  # noqa: E402
import chaebol_map_tab_codong_deep as DD  # noqa: E402
import chaebol_map_tab_codong_deep_chart as CH  # noqa: E402
import chaebol_map_tab_codong_deep_live as LV  # noqa: E402

V21_FILE = M.bridge_dir() / "data" / "chaebol_map" / "v21_const.json"
VC_DIR = M.bridge_dir() / "state" / "vc_lk"
SUBS = ["phase_info", "chart", "phase", "cluster", "shareholder", "capitaliq", "flow", "strategic", "events",
        "patterns", "action"]
LABELS = ["★ 01 Phase Infographic", "02 Chart Infographic", "03 Phase + Status", "04 Cụm + VWAP", "05 Cổ đông BCTN",
          "★ 06 Capital IQ", "★ 06b FiinTrade Flow", "07 Bàn cờ lớn", "08 Key Events", "09 Patterns", "10 Action Plan"]
HIDDEN = {"VNM", "SAB", "VTP", "VGI", "GVR", "BVH", "BCM"}
_REAL = {}
_V21 = None


def setUpModule():
    def blocked(*a, **k):
        raise RuntimeError("mạng bị chặn trong test chaebol_map")
    for name in ("socket", "create_connection", "getaddrinfo"):
        _REAL[name] = getattr(socket, name)
        setattr(socket, name, blocked)


def tearDownModule():
    for name, fn in _REAL.items():
        setattr(socket, name, fn)


def v21_const():
    global _V21
    if _V21 is None:
        _V21 = json.loads(V21_FILE.read_text(encoding="utf-8")) if V21_FILE.is_file() else {}
    return _V21


def make_ctx(mode, data=None, dossier=None):
    ctx = M.Ctx(mode, date(2026, 9, 27), [])
    ctx.v21 = v21_const()
    ctx.data = data
    ctx.dossier = dossier
    ctx.tab = "codong"
    return ctx


def walk(node, parents=()):
    yield node, parents
    if isinstance(node, dict):
        for ch in node.get("k", ()):
            yield from walk(ch, parents + (node,))


def texts(node):
    return [n for n, _ in walk(node) if isinstance(n, str)]


def alltext(node):
    return "".join(texts(node))


def by_key(node, key):
    return [n for n, _ in walk(node) if isinstance(n, dict) and n.get("key") == key]


def panel(root, sid):
    ps = by_key(root, "deep10_" + sid)
    return ps[0] if ps else None


def build(tk, mode="v21", **kw):
    with D.use_mode(mode, "2026-09-27"):
        return DD.build_deep10(make_ctx(mode, **kw), tk)


NUM_RE = re.compile(r"(?<![A-Za-z/\d.,])\d+(?:[.,]\d+)*\s?(?:K|M|%|x|×|tỷ|đ)(?![A-Za-zÀ-ỹ/])|\d{1,3}(?:,\d{3})+")
MARKS = ("_tier", "_can", "_v21", "_upd")


def is_mark(n):
    return isinstance(n, dict) and any(n.get(m) for m in MARKS)


def has_mark(n, depth):
    if is_mark(n):
        return True
    if depth == 0 or not isinstance(n, dict):
        return False
    return any(has_mark(c, depth - 1) for c in n.get("k", ()))


def unmarked_numbers(node, zone=False, out=None):
    """Luật DESIGN §8.4 (live): chữ có số trong phần tử không mang nhãn bậc/[CẦN DATA]/V21/↻ ở cùng cấp và không nằm
    trong vùng đã có nhãn (khối chú thích/nhãn đứng trước trong cùng cha) → vi phạm."""
    out = [] if out is None else out
    if not isinstance(node, dict) or is_mark(node):
        return out
    kids = node.get("k", ())
    direct = any(is_mark(c) for c in kids)
    for c in kids:
        if isinstance(c, str) and NUM_RE.search(c) and not (direct or zone):
            out.append(c[:80])
    z = zone
    for c in kids:
        if isinstance(c, dict):
            unmarked_numbers(c, z or direct, out)          # số trong <strong> cạnh nhãn bậc cùng cha
            if has_mark(c, 3):
                z = True
    return out


@unittest.skipUnless(V21_FILE.is_file(), "thiếu v21_const.json")
class TestStructureV21(unittest.TestCase):
    def test_has_deep10_41_of_48(self):
        tks = v21_const()["CauTrucCoDongTab.allTickers"]
        shown = [t for t in tks if DD.has_deep10(t, v21_const())]
        self.assertEqual(len(tks), 48)
        self.assertEqual(len(shown), 41)
        self.assertEqual(set(tks) - set(shown), HIDDEN)
        self.assertTrue(DD.has_deep10("GAS"))           # ngoại lệ NQ79 trong danh sách JSX
        self.assertFalse(DD.has_deep10("VNM"))

    def test_sub_options_match_v21(self):
        self.assertEqual(DD.sub_options(v21_const()), SUBS)
        self.assertEqual(M.expected_options(v21_const())["codong.sub"], SUBS)
        self.assertEqual([lbl for _, lbl in DD.sub_tabs(v21_const())], LABELS)

    def test_section_scope_title_buttons(self):
        root = build("VIC")
        self.assertEqual(root["t"], "section")
        self.assertEqual(root["scope"], ["codong.sub"])
        self.assertEqual(root["key"], "deep10_VIC")
        h2 = [n for n, _ in walk(root) if isinstance(n, dict) and n["t"] == "h2"][0]
        self.assertEqual(alltext(h2), "🔬 DEEP-DIVE 10 SUB-TABS — VIC (equivalent v22 MSN tab structure)")
        self.assertIn(DD.SUB_LINE, texts(root))
        btns = [n for n, _ in walk(root) if isinstance(n, dict) and n["t"] == "button"]
        self.assertEqual([alltext(b) for b in btns], LABELS)
        for b, sid in zip(btns, SUBS):
            self.assertEqual(b["on"], {"set": {"codong.sub": sid}})
            self.assertEqual(b["var"][0]["if"], {"codong.sub": sid})
            self.assertEqual(b["var"][0]["s"]["background"], "#caa75c")
            self.assertEqual(b["s"]["fontSize"], 9.5)
            self.assertEqual(b["s"]["fontFamily"], "'IBM Plex Mono', monospace")   # JSX tự đặt → lõi không thêm inherit
        for sid in SUBS:
            p = panel(root, sid)
            self.assertIsNotNone(p, sid)
            self.assertEqual(p["if"], {"codong.sub": sid})

    def test_empty_panels_like_jsx(self):
        vre = build("VRE")
        self.assertIsNone(panel(vre, "phase_info"))     # deep undefined → panel trống (kể cả tab mặc định)
        self.assertIsNone(panel(vre, "cluster"))
        self.assertIsNotNone(panel(vre, "chart"))
        self.assertIsNone(panel(build("HDB"), "flow"))  # HDB không có FLOW

    def test_golden_strings_phase_info(self):
        t = texts(build("VIC"))
        self.assertIn("★ 01 Phase Infographic — VIC", t)
        self.assertIn("MARKUP — parabolic dở dang", t)
        self.assertIn("STANCE: HOLD / TRIM PARTIAL on rip", t)
        for s in ("250K", "207K", "165K", "5-7%", "5-7% NAV combined VHM", "upside", "entry zone", "exit downside"):
            self.assertIn(s, t)
        for tk, size0 in (("GEX", "3-5%"), ("GEE", "KHÔNG"), ("VIX", "Swing"), ("VJC", "Hold")):
            self.assertIn(size0, texts(panel(build(tk), "phase_info")), tk)

    def test_golden_phase_status(self):
        p = panel(build("VIC"), "phase")
        t = texts(p)
        self.assertIn("⚡ 03 Phase + Status — VIC", t)
        self.assertIn("224.0K", t)
        self.assertIn("2026-05-07", t)
        self.assertIn("HOLD / TRIM PARTIA", t)          # substring(0,18)
        self.assertIn("+71.4%", t)
        self.assertIn("BEAR", t)
        gex = texts(panel(build("GEX"), "phase"))
        self.assertIn("39.3K", gex)                     # cafefPx ưu tiên
        self.assertIn("04-08/05", gex)
        vre = texts(panel(build("VRE"), "phase"))
        self.assertIn("N/A", vre)

    def test_chart_modes_geometry(self):
        a = panel(build("VIC"), "chart")
        svg = [n for n, _ in walk(a) if isinstance(n, dict) and n["t"] == "svg"][0]
        self.assertEqual(svg["a"], {"viewBox": "0 0 820 380", "width": "100%", "height": "auto"})
        t = texts(a)
        self.assertIn("WEEKLY OHLCV + VWAP 6M/12M/24M · VIC · 105 weeks (FiinTrade ≤08/05 + NgườiQuanSát Mon 11/05 "
                      "intraday)", t)
        self.assertIn(CH.LEGEND_A, t)                   # "104 weeks" viết cứng
        self.assertIn("CLOSE 05/15: ", t)               # ngày MM/DD như JSX
        self.assertIn("NOW 223.0K", t)
        self.assertIn("ANCHOR 165K", t)
        self.assertIn("HI 250K", t)
        self.assertIn("STOP 165K", t)
        circles = [n for n, _ in walk(svg) if isinstance(n, dict) and n["t"] == "circle"]
        self.assertEqual(len(circles), 106)             # 105 chấm + NOW
        msn = texts(panel(build("MSN"), "chart"))
        self.assertIn("NOW 78.1K", msn)
        self.assertIn("ANCHOR 77K", msn)
        b = panel(build("GEX"), "chart")
        svgb = [n for n, _ in walk(b) if isinstance(n, dict) and n["t"] == "svg"][0]
        self.assertEqual(svgb["a"]["viewBox"], "0 0 780 340")
        tb = texts(b)
        self.assertIn("CLUSTER + VWAP MAP · GEX (synthesized from Toàn Vũ hộp + Phú SSI VWAP — không có FiinTrade "
                      "weekly data)", tb)
        self.assertIn(CH.LEGEND_B, tb)
        self.assertIn("NOW 39.3K", tb)
        self.assertTrue(any(s.startswith("HI TARGET ") for s in tb))
        self.assertIn("Chart data chưa available cho VRE", texts(panel(build("VRE"), "chart")))

    def test_chart_path_js_numbers(self):
        a = panel(build("VIC"), "chart")
        paths = [n["a"]["d"] for n, _ in walk(a) if isinstance(n, dict) and n["t"] == "path"]
        self.assertEqual(len(paths), 4)
        self.assertTrue(paths[0].startswith("M56 "))
        self.assertNotIn(".0 ", paths[3])               # String(n) kiểu JS, không '56.0'

    def test_mood_color_and_js_helpers(self):
        self.assertEqual(CH.mood_color("pre-markup"), "#caa75c")        # 'markup' kiểm trước → gold
        self.assertEqual(CH.mood_color("markup-distribution"), "#c5392f")
        self.assertEqual(CH.mood_color(None), "#5b8db8")
        self.assertEqual(CH.js_slice("2026-05-15", 2, 7), "26-05")
        self.assertEqual(CH.js_slice("😀abc", 0, 2), "😀")                # UTF-16
        self.assertEqual(CH.jsv(None), "null")
        self.assertEqual(CH.jsv(1, missing=True), "undefined")
        self.assertFalse(CH.truthy(0))
        self.assertTrue(CH.truthy([]))

    def test_tables_golden(self):
        t = texts(panel(build("VIC"), "cluster"))
        for s in ("VWAP CỤM (6M / 12M / 24M)", "CỤM KHỐI LƯỢNG (Toàn Vũ)", "VWAP 6T", "152.5", "FAR", "C2023",
                  "★ Cụm RA HÀNG parabolic", "distribution-or-markup", "★ VERDICT:"):
            self.assertIn(s, t)
        t5 = texts(panel(build("VIC"), "shareholder"))
        self.assertIn("~120,000", t5)
        self.assertIn("★ Reading per Toàn Vũ:", t5)
        self.assertIn("Chưa có shareholder evolution detailed cho VRE. Tham chiếu BCTN từng năm tại "
                      "simplize.vn/co-phieu/VRE/bao-cao.", alltext(panel(build("VRE"), "shareholder")))
        t6 = texts(panel(build("VIC"), "capitaliq"))
        self.assertIn("2520.27M", t6)
        self.assertIn("33.61%", t6)
        self.assertIn("—", t6)                          # shares_M null
        self.assertIn("Holders data chưa available.", texts(panel(build("VRE"), "capitaliq")))
        t6b = texts(panel(build("VIC"), "flow"))
        for s in ("8.4M", "12.7M", "-2.0M", "-19.1M", "SIGNAL: BEAR",
                  " — Smart money distributing, retail catch knife. Pattern A đỉnh."):
            self.assertIn(s, t6b)
        t8 = texts(panel(build("VRE"), "events"))
        self.assertIn("VRE: NQ và Biên bản họp ĐHĐCĐ TN 2026", t8)   # REPORTS_INDEX dự phòng
        t10 = alltext(panel(build("VIC"), "action"))
        self.assertIn("★ Sell-side consensus: 2 MUA / 0 BÁN / avg TP 34.5K VND.", t10)
        self.assertNotIn("★ Sell-side consensus:", alltext(panel(build("GEE"), "action")))  # avgTp null

    def test_v21_has_no_live_marks(self):
        root = build("VHM")
        self.assertFalse(any(is_mark(n) for n, _ in walk(root)))
        self.assertNotIn("[CẦN DATA", alltext(root))

    def test_all_41_build_both_modes_none_data(self):
        for tk in [t for t in v21_const()["CauTrucCoDongTab.allTickers"] if DD.has_deep10(t)]:
            for mode in ("v21", "live"):
                with D.use_mode(mode, "2026-09-27"):
                    root = DD.build_deep10(make_ctx(mode), tk)
                    obj, _ = D.finalize(root)
                    self.assertEqual(obj["root"]["t"], "section")

    def test_live_without_data_is_can_data(self):
        with D.use_mode("live", "2026-09-27"):
            root = DD.build_deep10(make_ctx("live", data=None), "VIC")
        txt = alltext(root)
        self.assertIn("[CẦN DATA", txt)
        self.assertIn("V21·12/05", txt)
        self.assertEqual(unmarked_numbers(root), [])


@unittest.skipUnless(V21_FILE.is_file() and (VC_DIR / "VIC" / "price-history.json").is_file(), "thiếu kho vc_lk")
class TestLiveStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import chaebol_map_data as data
        data.clear_cache()
        cls.data = data
        cls.dossier = data.dossier()

    def live(self, tk, dossier="real"):
        with D.use_mode("live", "2026-09-27"):
            return DD.build_deep10(make_ctx("live", data=self.data,
                                            dossier=self.dossier if dossier == "real" else dossier), tk)

    def test_every_number_tagged(self):
        for tk in ("VIC", "VHM", "MSN", "GEX", "HDB", "VRE", "LPB", "GAS"):
            bad = unmarked_numbers(self.live(tk))
            self.assertEqual(bad, [], tk)

    def test_live_chart_extended_mode_a(self):
        for tk in ("GEX", "VRE", "HDB"):
            p = panel(self.live(tk), "chart")
            svg = [n for n, _ in walk(p) if isinstance(n, dict) and n["t"] == "svg"][0]
            self.assertEqual(svg["a"]["viewBox"], "0 0 820 380", tk)
            self.assertTrue(any("vc_lk giá điều chỉnh quyền" in s for s in texts(p)), tk)

    def test_vhm_levels_converted(self):
        t = texts(panel(self.live("VHM"), "phase_info"))
        self.assertTrue(any("V21 200K ×0.4815" in s for s in t), t[:40])
        self.assertIn("96.3K", t)                       # 200K × 0.4815 (VHM chia 100% 06/08 + cổ tức tiền)
        chart = texts(panel(self.live("VHM"), "chart"))
        self.assertTrue(any(s.startswith("HI 96.3K (V21 200K quy đổi)") for s in chart))

    def test_flow_rules(self):
        p = panel(self.live("VIC"), "flow")
        txt = alltext(p)
        self.assertIn("FiinTrade ≤08/05 — đóng băng", txt)
        self.assertIn("TỰ DOANH (khớp)", txt)
        self.assertIn("phần dư, không phải kênh thật", txt)
        self.assertGreaterEqual(txt.count("[CẦN DATA]"), 2)            # Cá nhân, Tổ chức
        hdb = panel(self.live("HDB"), "flow")
        self.assertIsNotNone(hdb)                                        # live hiện NN/TD dù V21 không có FLOW
        self.assertIn("V21 không có FLOW cho HDB", alltext(hdb))

    def test_stance_kept_with_v21_mark(self):
        txt = alltext(panel(self.live("VIC"), "action"))
        self.assertIn("Bản lưu V21·12/05 — không chấm lại", txt)
        self.assertIn(">5% NAV → Synthesis L1+L2+L3", txt)
        self.assertIn("không phải khuyến nghị của trang", txt)
        self.assertNotRegex(txt, r"(?i)khuyến nghị (mua|bán) mới")

    def test_patterns_question_mark(self):
        p = panel(self.live("GEX"), "patterns")
        live = by_key(p, "deep10_patterns_live")
        self.assertTrue(live)
        tds = [alltext(n) for n, par in walk(live[0]) if isinstance(n, dict) and n["t"] == "tr"][1:]
        for row in tds:
            self.assertIn("?", row)

    def test_codong_cf_and_outside_tv30(self):
        self.assertIn("chưa có số mới", texts(panel(self.live("VIC"), "shareholder")))
        self.assertIn("ngoài 30 mã Toàn Vũ", alltext(panel(self.live("GEX"), "shareholder")))

    def test_dossier_event_status(self):
        fake = {"tickers": {"VJC": {"deep10": {"updates": {}, "events_new": [],
                                               "v21_events_status": {"0": {"status": "BỊ BÁC", "evidence": "đã ngã ngũ",
                                                                           "tier": "FACT-T1", "asof": "2025-10-30",
                                                                           "src": "x"}}}}}}
        p = panel(self.live("VJC", dossier=fake), "events")
        txt = alltext(p)
        self.assertIn("BỊ BÁC", txt)
        self.assertIn("đã ngã ngũ", txt)
        self.assertEqual(unmarked_numbers(p), [])

    def test_level_eval_status(self):
        txt = alltext(panel(self.live("GEX"), "phase_info"))
        self.assertRegex(txt, r"Chấm lại mốc HI/STOP V21 bằng giá điều chỉnh 12/05→\d\d/\d\d:")
        self.assertTrue(any(s in txt for s in ("ĐẠT", "BỊ BÁC", "LIVE")))

    # ── sửa sau kiểm chứng 27/09 ──

    def test_msr_vendor_adj_repair(self):
        t = alltext(panel(self.live("MSR"), "phase_info"))
        for s in ("58.8K", "31.3K", "V21 60K ×0.9792", "chuỗi giá điều chỉnh của vendor lệch từ 16/09",
                  "đỉnh 55.5K (24/09)", "đáy 32.2K (22/07)", "cuối 53.5K", "LIVE"):
            self.assertIn(s, t)
        self.assertNotIn("0.9668", t)

    def test_gee_premise_and_scale(self):
        t = alltext(panel(self.live("GEE"), "phase_info"))
        for s in ("CHƯA RÕ", "theo thang ×0.9869", "thủng STOP 59.2K ngày 14/09 (57.2K)",
                  "Cổ phiếu thưởng 75% đã GDKHQ 05/05/2026"):
            self.assertIn(s, t)

    def test_vhm_factor_decomposed(self):
        t = alltext(panel(self.live("VHM"), "phase_info"))
        self.assertIn("×0.9630 (cổ tức tiền 29/06) × 0.5000 (cổ tức CP 06/08) = ×0.4815", t)

    def test_flow_td_coverage_window_units(self):
        dgc = alltext(panel(self.live("DGC"), "flow"))
        self.assertIn("15/60 phiên có bản ghi tự doanh", dgc)
        self.assertIn("không tính phần dư", dgc)
        vic = panel(self.live("VIC"), "flow")
        txt = alltext(vic)
        self.assertIn("M cp", txt)
        self.assertIn("NN tới 25/09, TD tới 24/09", txt)
        self.assertNotIn("09/05→", txt)                                 # một nhãn cửa sổ: 60 phiên 01/07→25/09
        self.assertIn("60 phiên 01/07→25/09", txt)
        self.assertIn("T2·24/09", txt)

    def test_codong_note_and_cf_kind(self):
        msn = alltext(panel(self.live("MSN"), "shareholder"))
        self.assertIn("quan sát cuối 10/2024; CF 2 kỳ", msn)
        vhm = panel(self.live("VHM"), "shareholder")
        rows = [alltext(n) for n, _ in walk(by_key(vhm, "deep10_codong_live")[0]) if isinstance(n, dict)
                and n["t"] == "tr"]
        cf = [r for r in rows if "chưa có số mới" in r]
        self.assertEqual(len(cf), 3)
        self.assertTrue(all(r.endswith("chép kỳ trước (CF)") for r in cf), cf)

    def test_events_sorted_split_and_ratio(self):
        p = panel(self.live("VIC"), "events")
        txt = alltext(p)
        self.assertNotIn("0.00 cp/100 cp", txt)
        self.assertIn("— ↻ dữ kiện trước 09/05/2026", txt)
        dates = []
        for n, _ in walk(p):
            if isinstance(n, dict) and n["t"] == "tr":
                d = alltext(n)[:10]
                if re.match(r"\d\d/\d\d/\d{4}$", d):
                    dates.append(d[6:] + d[3:5] + d[:2])
                if "V21" in alltext(n) or alltext(n).startswith("— ↻"):
                    break
        head = []
        for n, _ in walk(p):                                   # hàng đầu (trước bản lưu V21): ≥ 09/05, giảm dần
            if isinstance(n, dict) and n["t"] == "tr" and "↻" in alltext(n)[:40]:
                d = alltext(n)[:10]
                if re.match(r"\d\d/\d\d/\d{4}$", d):
                    head.append(d[6:] + d[3:5] + d[:2])
        new = [d for d in head if d >= "20260509"]
        self.assertEqual(new, sorted(new, reverse=True))
        self.assertNotIn("giá kho…", txt)

    def test_vpb_c11_not_decided_here(self):
        txt = alltext(panel(self.live("VPB"), "events"))
        self.assertNotIn("đã kích hoạt", txt)
        self.assertIn("[CẦN DATA — KL khớp từng ngày]", txt)
        self.assertIn("ClaimsPanel", txt)

    def test_stb_action_no_sell_trigger(self):
        txt = alltext(panel(self.live("STB"), "action"))
        self.assertNotIn("đã bị vượt xa", txt)
        self.assertIn("Trigger V21 không chấm lại", txt)

    def test_dgc_legal_banner_and_marks(self):
        root = self.live("DGC")
        ban = by_key(root, "deep10_legal")
        self.assertTrue(ban)
        self.assertIn("17/03", alltext(ban[0]))
        cap = alltext(panel(root, "capitaliq"))
        self.assertIn("KHỞI TỐU", cap)
        self.assertEqual(by_key(self.live("VIC"), "deep10_legal"), [])

    def test_pattern_caption_tier(self):
        txt = alltext(panel(self.live("VIC"), "patterns"))
        self.assertIn("bậc chép theo atom nguồn", txt)
        self.assertNotIn("(EST, nhãn luôn", txt)

    def test_route_facts_one_sub_each(self):
        r = CO.route_facts(self.data, "VIC")
        ids = [f["id"] for lst in r.values() for f in lst]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("F1-001", [f["id"] for f in r.get("phase_info", [])])     # CHAEBOL_DEEP_DATA.VIC.phase

    # ── vòng hoàn thiện 27/09 (final_check §6.1 #2 #3 #4 #7) ──

    def test_vpl_free_float_premise_false(self):
        """#7: 'VPL hạn cuối nâng free float >10%' — vế đạt đã thoả lúc dựng → TIỀN ĐỀ SAI (cùng claims54 C22 và
        catalyst); vế ngưỡng luật (U) tách mục riêng, không pill."""
        ev = panel(self.live("VIC"), "events")
        row = next(n for n, _ in walk(ev) if isinstance(n, dict) and n["t"] == "tr"
                   and "VPL hạn cuối nâng free float" in alltext(n))
        self.assertIn("TIỀN ĐỀ SAI", texts(row))
        self.assertNotIn("BỊ BÁC", texts(row))
        self.assertIn("T2·31/12/25", alltext(row))
        act = alltext(panel(self.live("VPL"), "action"))
        self.assertIn("TIỀN ĐỀ SAI Free float VPL", act)
        self.assertIn("chưa đọc nguyên văn điều luật.U·23/09", act)
        self.assertNotIn("BỊ BÁC Free float", act)

    def test_v21_stat_labels_marked(self):
        """#3: 'upside / entry zone / exit downside' là nhãn Stat V21 nguyên văn (SRC 3928–3930) — giữ; mốc đã quy
        đổi quyền thì dấu V21·12/05 đứng ngay sau nhãn."""
        p = panel(self.live("VHM"), "phase_info")
        for lab in ("upside", "entry zone", "exit downside"):
            kids = next(par[-1]["k"] for n, par in walk(p) if n == lab)
            nxt = kids[kids.index(lab) + 1]
            self.assertTrue(is_mark(nxt) and alltext(nxt) == "V21·12/05", lab)
        self.assertIn(" · mốc V21 200K ×0.4815", texts(p))

    def test_events_capital_rows_not_under_old_separator(self):
        """Sự kiện vốn lọc theo ngày công bố: cổ tức HPG/LPB công bố 05–08/05 (GDKHQ 11/05, 14/05) không bị xếp dưới
        hàng '— ↻ dữ kiện trước 09/05/2026 (thay mệnh đề V21 …)'."""
        for tk in ("HPG", "LPB"):
            old = False
            for n, _ in walk(panel(self.live(tk), "events")):
                if isinstance(n, dict) and n["t"] == "tr":
                    t = alltext(n)
                    old = old or t.startswith("— ↻ dữ kiện trước 09/05/2026")
                    self.assertFalse(old and "↻ vốn" in t, (tk, t[:80]))

    def test_flow_v21_date_vietnamese(self):
        vic = alltext(panel(self.live("VIC"), "flow"))
        self.assertIn("60d net · ≤07/05/2026", vic)
        self.assertNotRegex(vic, r"≤\d{4}-")

    def test_no_signed_zero_and_can_data_nowrap(self):
        """#2 + #4 trên cả 41 khối Deep-dive: không '-0.0'/'+0.0'; mọi '[CẦN DATA' nằm trong phần tử nowrap."""
        rx = re.compile(r"(?<![\d.,])[-+−]0[.,]0+(?!\d)")
        for tk in [t for t in v21_const()["CauTrucCoDongTab.allTickers"] if DD.has_deep10(t)]:
            root = self.live(tk)
            self.assertIsNone(rx.search(alltext(root)), tk)
            for n, par in walk(root):
                if isinstance(n, str) and "[CẦN DATA" in n:
                    self.assertTrue(any((a.get("s") or {}).get("whiteSpace") == "nowrap" for a in par), (tk, n[:60]))


class TestPureHelpers(unittest.TestCase):
    def test_cap_status(self):
        self.assertEqual(CO.cap_status("BỊ BÁC", "UNVERIFIED"), "CHƯA RÕ")
        self.assertEqual(CO.cap_status("ĐẠT", "U", "FACT-T2"), "ĐẠT")
        self.assertEqual(CO.cap_status("TIỀN ĐỀ SAI"), "CHƯA RÕ")
        self.assertEqual(CO.cap_status("LIVE", "U"), "LIVE")
        self.assertIsNone(CO.cap_status(None, "U"))

    def test_vi_label(self):
        self.assertEqual(CO.vi_label("tren_cum"), "trên cụm")
        self.assertEqual(CO.vi_label("chua_ro?"), "chưa rõ?")
        self.assertEqual(CO.vi_label("het_hieu_luc"), "hết hiệu lực")
        self.assertEqual(CO.vi_label("chep"), "chép kỳ trước (CF)")
        self.assertEqual(CO.vi_label("Mũ sắt?"), "Mũ sắt?")

    def test_codong_summary(self):
        moc = [{"ky": "2025-06", "v": 1, "kieu": "quan_sat", "cf": False},
               {"ky": "2026-01", "v": 1, "kieu": "quan_sat", "cf": True}]
        obs, last, n_cf = CO.codong_summary(moc)
        self.assertEqual((obs["ky"], last["ky"], n_cf), ("2025-06", "2026-01", 1))

    def test_holder_basis(self):
        iss = [{"exright": "2026-06-16", "ratio": 0.3, "title": "Trả Cổ tức bằng Cổ phiếu tỉ lệ 30.0%"},
               {"exright": "2025-06-12", "ratio": 0.09, "title": "Phát hành riêng lẻ tỉ lệ 9.2%"}]
        r = CO.holder_basis(100.0, "2025-12-31", 26.16, iss, 591.6 / 1.5465, "2026-09-27")
        self.assertAlmostEqual(r["adj"], 130.0)
        r2 = CO.holder_basis(100.0, "2024-01-01", None, iss + [{"exright": "2025-01-01", "ratio": 0.1,
                                                                 "title": "Quyền mua CP tỉ lệ 10%"}], None, "2026-09-27")
        self.assertIsNone(r2["adj"])
        self.assertEqual(r2["rights"], ["2025-01-01"])
        r3 = CO.holder_basis(2243.39, "2026-06-30", 95.76, [], 2412.95, "2026-09-27")
        self.assertIsNotNone(r3["lech"])                          # GAS/PVN: SL ÷ tổng cp 92.97% ≠ 95.76%

    def test_cafef_basis(self):
        dates = ["2026-04-29", "2026-05-04", "2026-05-05", "2026-05-08"]
        self.assertEqual(CO.cafef_basis(dates, [39100, 39300, 27450, 33500], [26967, 27105, 27450, 33500], 0, 3, 39300),
                         ("raw", "2026-05-04"))                  # GEX: giá thô trước GDKHQ 05/05
        self.assertEqual(CO.cafef_basis(dates, [174900, 174800, 106800, 128000],
                                        [98632.78, 98576.39, 105405.31, 126328.46], 0, 3, 99938),
                         ("adj08", "2026-04-29"))                # GEE: giá đã điều chỉnh về cơ sở 08/05
        self.assertIsNone(CO.cafef_basis(dates, [1, 2, 3, 4], [1, 2, 3, 4], 0, 3, 99))

    def test_structure_dev(self):
        s = {"stateVolume": 96585637, "foreignerVolume": 487808303, "otherVolume": 1129932482,
             "totalShares": 1885759064}
        d = CO.structure_dev(s)
        self.assertAlmostEqual(d["dev"], -9.09, places=1)
        self.assertIsNone(CO.structure_dev(dict(s, totalShares=96585637 + 487808303 + 1129932482)))

    def test_live_format_helpers(self):
        """Vòng hoàn thiện 27/09: ngày kiểu Việt (DESIGN §11.3), '[CẦN DATA' nowrap trong chuỗi nguồn, số âm-không."""
        self.assertEqual(CO.dmy_hm("2026-09-23 23:04"), "23/09/2026 23:04")
        self.assertEqual(CO.dmy_hm("2026-09-23T23:10:31+07:00"), "23/09/2026 23:10")
        self.assertEqual(CO.dmy_hm("2026-09-23"), "23/09/2026")
        self.assertEqual(CO.dmy_hm("—"), "—")
        src = "CỔNG: [CẦN DATA — M2] · x [CẦN DATA]"
        parts = CO.nowrap_can(src)
        self.assertEqual("".join(p if isinstance(p, str) else p["k"][0] for p in parts), src)
        self.assertEqual([p["s"] for p in parts if isinstance(p, dict)], [{"whiteSpace": "nowrap"}] * 2)
        v = type("V", (), {"value": -0.04})()
        with D.use_mode("live", "2026-09-27"):
            self.assertEqual(CO.mcp(v), "0.0M cp")
            self.assertEqual(CO.mcp(type("V", (), {"value": -0.05})()), "-0.1M cp")
            self.assertEqual(alltext(CO.pill("TIỀN ĐỀ SAI")), "TIỀN ĐỀ SAI")
        with D.use_mode("v21", "2026-09-27"):
            self.assertEqual(CO.mcp(v), "-0.0M cp")                          # v21 giữ đúng toFixed của JS


class TestAutoStatus(unittest.TestCase):
    def test_auto_event_status(self):
        self.assertEqual(LV.auto_event_status("Q2/2026")["status"], "CHƯA RÕ")
        self.assertEqual(LV.auto_event_status("Q4/2026")["status"], "LIVE")
        self.assertEqual(LV.auto_event_status("25/06/2026")["status"], "CHƯA RÕ")
        self.assertIsNone(LV.auto_event_status("04-08/05/2026"))
        self.assertIsNone(LV.auto_event_status("12/05/2026"))
        self.assertEqual(LV.auto_event_status("2026-2027")["status"], "LIVE")

    def test_trim_text(self):
        s = "Câu một dài. " * 60
        self.assertLessEqual(len(CO.trim_text(s, 100)), 101)
        w = "một " * 30 + "khoảng 530 triệu USD"
        out = CO.trim_text(w, 125)
        self.assertTrue(out.endswith("…"))
        self.assertTrue(w.startswith(out[:-1]))
        self.assertIn(out[:-1].split(" ")[-1], w.split(" "))       # không cắt giữa từ


if __name__ == "__main__":
    unittest.main()
