#!/usr/bin/env python3
"""
Tests for deepfa_core.py (loaders, memo parser, gates). Stdlib unittest only.

    cd fincept-qt/scripts && python3 -m unittest test_deepfa_core -v

Fixture tests build a tiny vault under a temp dir (DEEPFA_VAULT) with DEEPFA_TODAY fixed, so
every staleness / age rule is deterministic. LiveDataTest runs against the real vault when it
exists and only asserts shape, never values.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deepfa_core as C  # noqa: E402

TODAY = "2026-09-23"

MEMO = """# ABC — Công ty ABC (HOSE:ABC) · 73.600đ [CIQ·09/06] · **State B — Variant watch**

> **VN30** · Deep-FA ✅ engine `claude-deep` (3 filing gốc, confidence 8.0) · 11/06/2026 · regime **RISK OFF** · Danh mục hiện 12% (kịch trần)

## §1 · THESIS
Thesis ngắn [BCTN·2025] [FACT-T1].

## §2 · TENSION GIỮA CÁC DÒNG PHIẾU
Street nói mua [SS-T3], tiền đi ra [fund_intent·10/06]. Điểm gãy của thesis là biên gộp xuống dưới 30% hai quý liên tiếp.

## §7 · ĐIỀU KIỆN THESIS + THEO DÕI (falsifiable)
**Thesis đúng (State B → A) nếu:**
1. LNTT 2026 giữ ≥14% YoY (đo: BCTC Q2 ~cuối 07/2026).
2. Hợp đồng ký thật trước 31/12/2026.

**Thesis gãy nếu:**
- LNTT <12% YoY.

**Lịch theo dõi dated:**
- Q3/2026 — cổ tức cổ phiếu 10%.
- 02/2027 — KQ cả năm.

## §8 · APPENDIX
[CẦN BÁO CÁO GỐC] cho cổ đông.
"""


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)


class _Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="deepfa_core_")
        cls.sys = os.path.join(cls.root, "_System")
        os.environ["DEEPFA_VAULT"] = cls.root
        os.environ["DEEPFA_TODAY"] = TODAY
        os.makedirs(os.path.join(cls.root, "BaoCao_VN30"))
        with open(os.path.join(cls.root, "BaoCao_VN30", "ABC_11-06-2026.md"), "w", encoding="utf-8") as fh:
            fh.write(MEMO)
        with open(os.path.join(cls.root, "BaoCao_VN30", "ABC_01-05-2026.md"), "w", encoding="utf-8") as fh:
            fh.write("# ABC — cũ\n\n## §1 · THESIS\ncũ\n")
        write_json(os.path.join(cls.sys, "fa_insight", "universe.json"),
                   {"as_of": "2026-06-18", "tickers": {"ABC": {"name": "Công ty ABC", "group": "VN30"}}})
        write_json(os.path.join(cls.sys, "fund_holdings", "fund_intent_signals.json"), {
            "as_of": "2026-09-20",
            "signals": {"ABC": {"ticker": "ABC", "shares_held": 1000.0, "pct_outstanding": 0.05, "num_funds": 4,
                                "net_change": {"m1": {"shares": 100.0}}, "signal_1m": "ACCUMULATION",
                                "top_accumulators_1m": [
                                    {"fund": "LVF", "shares_chg_1m": 60.0, "shares_held": 60.0},        # quỹ mới
                                    {"fund": "FUEVFVND", "shares_chg_1m": 30.0, "shares_held": 300.0},  # ETF rổ
                                    {"fund": "PYNELITE", "shares_chg_1m": 10.0, "shares_held": 500.0}],
                                "top_distributors_1m": []},
                        "DEF": {"ticker": "DEF", "shares_held": 5000.0, "pct_outstanding": 0.02, "num_funds": 7,
                                "net_change": {"m1": {"shares": -500000.0}}, "signal_1m": "DISTRIBUTION",
                                "has_fund_detail": False}}})                                   # universe-only export, no per-fund rows
        write_json(os.path.join(cls.sys, "fund_holdings", "etf_forecast.json"), {
            "as_of": "2026-09-23", "window": None,
            "tickers": {"ABC": {"price_t1": 66600.0, "vn30_cp": -1000.0, "diamond_cp": 3000.0, "finlead_cp": None, "tong_cp": 2000.0,
                                "adtv30_cp": 1000.0, "so_ngay_gd": 2.0, "w_vn30": {"truoc": 0.05, "sau": 0.04}}}})
        write_json(os.path.join(cls.sys, "fund_holdings", "fund_flows.json"), {
            "as_of": "2026-09-23", "funds": {"LVF": {"code": "LVF", "nav_date": "2026-08-31", "flow_mn": {"m1": 85055.9}}}})
        write_json(os.path.join(cls.sys, "fincept_bridge", "data", "lk_hoso", "ABC.json"), {
            "ma": "ABC", "tao_luc": "2026-09-23T15:14:27+07:00",
            "gia": {"px": {"v": 66.6, "u": "nghin_dong", "t": "2026-09-22", "b": "FACT-T2", "n": "vc_lk/ABC/price-history.closePrice"},
                    "bang": {"v": 67.0, "u": "nghin_dong", "t": "2026-09-23", "b": "FACT-T2", "n": "kho.gia_moi (vci_board)"}}})
        write_json(os.path.join(cls.sys, "alpha_spine", "ledger_calls.json"), {
            "updated": "2026-09-23",
            "calls": [{"ticker": "ABC", "open_date": "2026-06-01", "status": "open", "alpha": -3.0}],
            "stats": {"total": 2, "open": 2, "hit_rate": 50.0, "avg_alpha": -5.0,
                      "by_factor": {"langkinh": {"n": 1, "avg_alpha": -9.0}, "quality": {"n": 1, "avg_alpha": -1.0}}}})
        # vc_lk cache: 3 sessions, cot/hang shape
        cols = ["tradingDate", "closePrice", "closePriceAdjusted", "totalMatchValue", "foreignNetValueTotal",
                "foreignOwnedPercentage", "foreignCurrentRoom", "totalShares", "marketCap"]
        rows = [["2026-09-18", 70000, 63636, 1e11, 5e9, 0.25, 1e6, 1e9, 7e13],
                ["2026-09-19", 71000, 64545, 1e11, -2e9, 0.25, 1e6, 1e9, 7.1e13],
                ["2026-09-22", 66600, 66600, 1e11, 3e9, 0.2857, 1e6, 1.1e9, 7.3e13]]
        write_json(os.path.join(cls.sys, "fincept_bridge", "state", "vc_lk", "ABC", "price-history.json"),
                   {"meta": {"ma": "ABC", "endpoint": "price-history", "lay_luc": "2026-09-23T17:00:00+07:00"},
                    "du_lieu": {"cot": cols, "hang": rows}})
        # XYZ: newest session has close but vendor has not yet filled ownership / market cap / totalShares
        write_json(os.path.join(cls.sys, "fincept_bridge", "state", "vc_lk", "XYZ", "price-history.json"),
                   {"meta": {"ma": "XYZ", "endpoint": "price-history", "lay_luc": "2026-09-24T06:44:51+07:00"},
                    "du_lieu": {"cot": cols, "hang": [["2026-09-22", 66600, 66600, 1e11, 2e9, 0.2857, 3.5e8, 1.885e9, 1.2559e14],
                                                       ["2026-09-23", 66100, 66100, 1e11, -6e9, None, 3.51e8, None, None]]}})
        write_json(os.path.join(cls.sys, "fincept_bridge", "state", "vc_lk", "ABC", "ratio-daily.json"),
                   {"meta": {"ma": "ABC", "endpoint": "ratio-daily"},
                    "du_lieu": [{"tradingDate": "2026-09-22T00:00:00", "pe": 12.56, "pb": 3.15}]})
        write_json(os.path.join(cls.sys, "superdash_v2", "output", "vietcap_iq", "coverage.json"),
                   {"generated_at": "2026-09-23T16:10:00+07:00",
                    "coverage": [{"ticker": "ABC", "rating": "BUY", "target_price": 90300.0, "upside_pct": 39.0,
                                  "pe_fwd": 11.2, "tp_updated": "08-Jun-26", "analyst": "X"}]})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)
        os.environ.pop("DEEPFA_VAULT", None)
        os.environ.pop("DEEPFA_TODAY", None)


class MemoTest(_Fixture):
    def test_find_memo_picks_newest_by_real_date(self):
        d, p = C.find_memo("ABC")
        self.assertEqual(str(d), "2026-06-11")
        self.assertTrue(p.endswith("ABC_11-06-2026.md"))

    def test_parse_header_and_sections(self):
        _, p = C.find_memo("ABC")
        m = C.parse_memo(p)
        self.assertEqual(m["ticker"], "ABC")
        self.assertEqual(m["name"], "Công ty ABC")
        self.assertEqual(m["exchange"], "HOSE")
        self.assertEqual(m["price"], 73600.0)
        self.assertEqual(m["price_src"], "CIQ")
        self.assertEqual(m["price_date"], "09/06")
        self.assertEqual(m["state"], "B")
        self.assertEqual(m["engine"], "claude-deep")
        self.assertEqual(m["confidence"], 8.0)
        self.assertEqual(m["regime"], "RISK OFF")
        self.assertEqual(m["nav_pct_memo"], 12.0)
        self.assertTrue(m["deep"])
        self.assertEqual([s["key"] for s in m["sections"]], ["§1", "§2", "§7", "§8"])
        self.assertIn("biên gộp", m["break_point"])
        self.assertEqual(m["break_point_src"], "§2")
        self.assertGreaterEqual(m["n_tags"], 3)
        self.assertEqual(m["n_need"], 1)

    def test_break_point_falls_back_to_section_7(self):
        memo = MEMO.replace("Điểm gãy của thesis là biên gộp xuống dưới 30% hai quý liên tiếp.", "")
        path = os.path.join(self.root, "BaoCao_VN30", "XYZ_11-06-2026.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(memo.replace("ABC", "XYZ"))
        m = C.parse_memo(path)
        self.assertEqual(m["break_point_src"], "§7 (gãy nếu)")
        self.assertIn("LNTT", m["break_point"])

    def test_conditions_buckets_and_due_dates(self):
        _, p = C.find_memo("ABC")
        m = C.parse_memo(p)
        cond = C.parse_conditions(m["by_key"]["§7"]["text"])
        self.assertEqual(len(cond["dung"]), 2)
        self.assertEqual(cond["dung"][0]["due"], "2026-07-31")
        self.assertEqual(cond["dung"][1]["due"], "2026-12-31")
        self.assertEqual(len(cond["gay"]), 1)
        self.assertIsNone(cond["gay"][0]["due"])
        self.assertEqual(cond["lich"][0]["due"], "2026-09-30")   # Q3/2026
        self.assertEqual(cond["lich"][1]["due"], "2027-02-28")   # 02/2027


class GateTest(_Fixture):
    def test_gate_lvf_removes_new_fund_and_index_etf(self):
        S = C.load_shared()
        self.assertEqual(S["fund"]["meta"].status(), "ok")
        g = C.gate_lvf(C.by_ticker(S["fund"], "ABC"), S["fund"]["meta"])
        self.assertEqual(g["trang_thai"], "ok")
        self.assertEqual({r["fund"] for r in g["loai_bo"]}, {"LVF", "FUEVFVND"})
        self.assertAlmostEqual(g["co_hoc_cp"], 90.0)
        self.assertAlmostEqual(g["active_cp"], 10.0)
        self.assertEqual(g["nhan_tho"], "ACCUMULATION")
        self.assertTrue(g["nhan_sau_gate"].startswith("ACCUMULATION"))

    def test_gate_blind_when_layer_stale(self):
        os.environ["DEEPFA_TODAY"] = "2026-12-01"   # 72 days after as_of 2026-09-20
        try:
            S = C.load_shared()
            self.assertEqual(S["fund"]["meta"].status(), "stale")
            self.assertEqual(S["fund"]["meta"].effective_tier(), "UNVERIFIED")
            g = C.gate_lvf(C.by_ticker(S["fund"], "ABC"), S["fund"]["meta"])
            self.assertEqual(g["trang_thai"], "GATE-BLIND")
            self.assertIsNone(g["nhan_sau_gate"])
        finally:
            os.environ["DEEPFA_TODAY"] = TODAY

    def test_gate_none_when_ticker_absent(self):
        S = C.load_shared()
        g = C.gate_lvf(None, S["fund"]["meta"])
        self.assertEqual(g["trang_thai"], "none")

    def test_gate_fresh_but_no_detail_is_unfiltered_not_blind(self):
        S = C.load_shared()
        g = C.gate_lvf(C.by_ticker(S["fund"], "DEF"), S["fund"]["meta"], etfc=S["etfc"], tk="DEF")
        self.assertEqual(g["trang_thai"], "CHƯA LỌC")    # not 'ok', not GATE-BLIND: gate could not run
        self.assertTrue(g["chua_loc"])
        self.assertTrue(g["nhan_sau_gate"].startswith("chưa qua gate"))
        self.assertIsNone(g["nhan_tho"])                 # no ACCUMULATION/DISTRIBUTION word before the gate
        self.assertIn("không gán ACCUMULATION/DISTRIBUTION", g["ly_do"])
        self.assertIsNone(g["active_cp"])
        self.assertEqual(g["net_1m_cp"], -500000.0)
        self.assertIsNone(g["etf_du_bao"])              # DEF not in the forecast
        live = C.tension_live("DEF", S, {}, g)
        fund = [s for s in live["dong"] if s["dong"].startswith("Fund")][0]
        self.assertIsNone(fund["huong"])                 # unfiltered net never votes
        self.assertTrue(fund["txt"].startswith("net thô −0,5M cp 1M · 7 quỹ"))
        self.assertIn("không bỏ phiếu", fund["g"])

    def test_gate_attaches_etf_forecast(self):
        S = C.load_shared()
        self.assertTrue(C.fund_detail_available(S))
        g = C.gate_lvf(C.by_ticker(S["fund"], "ABC"), S["fund"]["meta"], etfc=S["etfc"], tk="ABC")
        ef = g["etf_du_bao"]
        self.assertEqual(ef["tong_cp"], 2000.0)
        self.assertEqual(ef["b"], "SS-T3")
        self.assertEqual(ef["t"], "2026-09-23")
        self.assertIn("VN30 −1.000 cp · DIAMOND +3.000 cp = tổng +2.000 cp (2,00 ngày KLGD 30p)", ef["txt"])
        live = C.tension_live("ABC", S, C.vc_price_flow("ABC"), g)
        fund = [s for s in live["dong"] if s["dong"].startswith("Fund")][0]
        self.assertEqual(fund["huong"], 1)
        self.assertIn("ETF dự báo kỳ review", fund["g"])


class WorksheetBlockTest(_Fixture):
    def test_list_insights_of_strings_and_dicts_do_not_crash(self):
        import deepfa_ticker as T
        ws = {"data": {"engine": "ollama", "as_of": "2026-06-10", "insights": {"catalysts": ["ĐHCĐ 04/2026 [DHCD]", {"event": "Chia cổ tức 10 % [BCTC 2025]"}],
                                                                             "red_flags": "OCF < LNTT [BCTC 2025]"}, "sources": ["BCTC_2025.pdf", {"tag": "BCTN", "file": "BCTN_2025.pdf", "path": "/nope/x.pdf", "status": "read"}]},
              "meta": C.Layer("worksheet", "/nope/ABC.json", "FACT-T1", inner="2026-06-10")}
        b = T.build_worksheet_block(ws)
        g = {x["key"]: x for x in b["groups"]}
        self.assertIn("ĐHCĐ 04/2026", g["catalysts"]["text"])
        self.assertIn("Chia cổ tức", g["catalysts"]["text"])
        self.assertEqual(g["catalysts"]["tier"], "UNVERIFIED")      # 105 days old → 45-day rule
        self.assertEqual(g["catalysts"]["tier_goc"], "FACT-T1")
        self.assertTrue(g["red_flags"]["g"].startswith("worksheet"))
        self.assertEqual([r["file"] for r in b["read_list"]], ["BCTC_2025.pdf", "BCTN_2025.pdf"])   # string source entries must not crash


class LastWithTest(_Fixture):
    def test_null_fields_on_newest_session_fall_back_to_previous_session_with_its_date(self):
        f = C.vc_price_flow("XYZ")
        self.assertEqual(f["close"]["t"], "2026-09-23")
        self.assertEqual(f["close"]["txt"], "66.100")
        self.assertEqual(f["foreign_pct"]["txt"], "28,57%")
        self.assertEqual(f["foreign_pct"]["t"], "2026-09-22")            # dated by the session that carries the number
        self.assertIn("phiên gần nhất có số: 2026-09-22", f["foreign_pct"]["g"])
        self.assertEqual(f["market_cap"]["t"], "2026-09-22")
        self.assertEqual(f["total_shares"]["t"], "2026-09-22")
        self.assertEqual(f["foreign_room"]["t"], "2026-09-23")           # this one IS filled on the newest row
        self.assertIsNone(f["foreign_room"]["g"])


class LayerTest(_Fixture):
    def test_missing_layer_is_marked_not_raised(self):
        S = C.load_shared()
        self.assertEqual(S["edi"]["meta"].status(), "missing")
        self.assertEqual(S["edi"]["meta"].light(), "⚫")
        self.assertEqual(S["edi"]["meta"].effective_tier(), "UNVERIFIED")
        self.assertIsNone(S["edi"]["data"])

    def test_universe_age_uses_inner_as_of(self):
        U = C.load_universe()
        self.assertEqual(U["n"], 1)
        self.assertEqual(U["meta"].age(), 97)
        self.assertEqual(U["meta"].status(), "warn")   # 60 < 97 <= 120

    def test_ledger_honesty_flags(self):
        S = C.load_shared()
        L = C.ledger_for(S["ledger"], "ABC")
        self.assertEqual(len(L["calls"]), 1)
        self.assertFalse(L["honest"]["is_track_record"])
        self.assertIn("mark-to-market", L["honest"]["note"])
        self.assertIn("nghi sai benchmark", L["honest"]["uniform_negative"])


class VietcapCacheTest(_Fixture):
    def test_price_flow_reads_cot_hang_and_sums_window(self):
        f = C.vc_price_flow("ABC", n=20)
        self.assertTrue(f["ok"])
        self.assertEqual(f["t"], "2026-09-22")
        self.assertEqual(f["close"]["v"], 66600.0)
        self.assertEqual(f["close"]["b"], "FACT-T2")
        self.assertAlmostEqual(f["foreign_net_20"]["v"], 6.0)   # (5 − 2 + 3) tỷ
        self.assertEqual(f["foreign_net_20"]["txt"], "+6")
        self.assertAlmostEqual(f["foreign_pct"]["v"], 28.57)
        self.assertEqual(f["foreign_pct"]["txt"], "28,57%")
        self.assertEqual(f["pe"]["txt"], "12,6")
        self.assertIsNone(f["prop_net_20"]["v"])                 # no proprietary cache in fixture
        self.assertEqual(C.close_on_or_before(f["_rows"], C.parse_day("2026-09-20"))[1], 71000.0)

    def test_missing_cache_is_reported(self):
        f = C.vc_price_flow("ZZZ")
        self.assertFalse(f["ok"])
        self.assertIn("ZZZ", f["ly_do"])

    def test_coverage_view_flags_old_tp(self):
        S = C.load_shared()
        v = C.coverage_view(C.coverage_row(S["cov"], "ABC"))
        self.assertEqual(v["target_price"], 90300.0)
        self.assertEqual(v["target_price_txt"], "90.300")
        self.assertEqual(v["tp_date"], "2026-06-08")
        self.assertEqual(v["tp_age_days"], 107)
        self.assertTrue(v["tp_stale"])
        self.assertEqual(v["b"], "SS-T3")


class FormatTest(unittest.TestCase):
    def test_vietnamese_numbers(self):
        self.assertEqual(C.fmt_vn(1234567), "1.234.567")
        self.assertEqual(C.fmt_vn(-3.456, 2), "−3,46")
        self.assertEqual(C.fmt_vn(12.5, 1, True), "+12,5")
        self.assertEqual(C.fmt_vn(None), "[CẦN DATA]")
        self.assertEqual(C.fmt_pct(0.0), "0,0%")
        self.assertEqual(C.fmt_date("2026-09-23"), "23/09/2026")

    def test_finite_rejects_non_numbers(self):
        self.assertIsNone(C.finite(True))
        self.assertIsNone(C.finite(float("nan")))
        self.assertEqual(C.finite("−1,5".replace(",", ".")), -1.5)

    def test_parse_day_formats(self):
        self.assertEqual(str(C.parse_day("08-Jun-26")), "2026-06-08")
        self.assertEqual(str(C.parse_day("22/09/2026")), "2026-09-22")
        self.assertEqual(str(C.parse_day("2026-09-22T00:00:00")), "2026-09-22")
        self.assertIsNone(C.parse_day("09/06"))


class LiveDataTest(unittest.TestCase):
    """Shape-only checks on the real vault; skipped when it is not on this machine."""

    def setUp(self):
        os.environ.pop("DEEPFA_VAULT", None)
        os.environ.pop("DEEPFA_TODAY", None)
        if not os.path.isdir(C.memo_dir()):
            self.skipTest("real vault not present")

    def test_universe_and_memos_load(self):
        U = C.load_universe()
        self.assertGreater(U["n"], 100)
        memos = C.list_memos()
        self.assertGreater(len(memos), 50)
        S = C.load_shared()
        for key, layer in S.items():
            self.assertIn(layer["meta"].status(), ("ok", "warn", "stale", "missing"), key)


if __name__ == "__main__":
    unittest.main()
