#!/usr/bin/env python3
"""Unit tests for chaebol_map_data_vciq: fixture cache trong thư mục tạm (CHB_SYSTEM_DIR), không mạng.
Chạy: python3.14 -m pytest -q test_chaebol_map_data_vciq.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import chaebol_map_data_nen as N  # noqa: E402
import chaebol_map_data_vciq as Q  # noqa: E402

COT = ["tradingDate", "openPrice", "highestPrice", "lowestPrice", "closePrice", "closePriceAdjusted",
       "totalMatchVolume", "totalMatchValue", "totalDealVolume", "totalDealValue", "totalVolume", "totalValue",
       "totalShares", "marketCap", "foreignNetVolumeTotal", "foreignNetValueTotal", "totalBuyTrade",
       "totalBuyTradeVolume", "totalSellTrade", "totalSellTradeVolume"]


def _row(d, c, sh=1000, mc=None, buy_tr=10):
    return [d, c, c + 1, c - 1, c, c, 100, 100 * c, 0, 0, 100, 100 * c, sh, mc, 5, 5 * c, buy_tr, 200, 4, 80]


class VciqTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("CHB_SYSTEM_DIR")
        os.environ["CHB_SYSTEM_DIR"] = self.tmp.name
        N.clear_cache()
        self.vc = N.vc_dir() / "TST"
        self.vc.mkdir(parents=True)

    def tearDown(self):
        if self.old is None:
            os.environ.pop("CHB_SYSTEM_DIR", None)
        else:
            os.environ["CHB_SYSTEM_DIR"] = self.old
        N.clear_cache()
        self.tmp.cleanup()

    def put(self, ep, du, **meta):
        (self.vc / (ep + ".json")).write_text(json.dumps({"meta": {"lay_luc": "2026-10-05T02:00:00+07:00", **meta},
                                                           "du_lieu": du}), encoding="utf-8")

    def test_week_label_is_first_session_and_holiday_week(self):
        # tuần 31/08–04/09/2026: nghỉ 31/08–02/09 → phiên đầu 03/09 là nhãn kỳ (như Vietcap)
        rows = [_row("2026-08-28", 10.0), _row("2026-09-03", 11.0), _row("2026-09-04", 12.0),
                _row("2026-09-07", 13.0)]
        self.put("price-history", {"cot": COT, "hang": rows})
        s = Q.stats("TST", "gia", "W")
        self.assertEqual([r["ky"] for r in s["rows"]], ["2026-09-07", "2026-09-03", "2026-08-28"])
        w = s["rows"][1]
        self.assertEqual((w["mo"], w["dong"], w["cao"], w["thap"], w["kl"]), (11.0, 12.0, 13.0, 10.0, 200))
        self.assertAlmostEqual(w["thay_doi_pct"], 20.0)
        self.assertEqual(s["n_ky"], 3)

    def test_period_sum_is_none_when_a_session_lacks_value(self):
        r1, r2 = _row("2026-09-03", 11.0), _row("2026-09-04", 12.0)
        r2[COT.index("totalBuyTrade")] = None
        self.put("price-history", {"cot": COT, "hang": [r1, r2]})
        w = Q.stats("TST", "cc", "W")["rows"][0]
        self.assertIsNone(w["lenh_mua"])
        self.assertEqual(w["kl_dat_mua"], 400)
        d = Q.stats("TST", "cc", "D")["rows"][1]
        self.assertEqual((d["lenh_mua"], d["kltb_mua"]), (10, 20.0))

    def test_market_cap_carries_shares_forward(self):
        r1, r2 = _row("2026-10-01", 70.0, sh=1000), _row("2026-10-02", 71.0, sh=None)
        self.put("price-history", {"cot": COT, "hang": [r1, r2]})
        self.assertEqual(Q.stats("TST", "gia", "D")["rows"][0]["von_hoa"], 71000.0)

    def test_earnings_all_null_means_login_locked(self):
        self.put("financial-data", {"ticker": "TST", "revenue": {"2025": None, "2026F": None}, "NPATMI": {}})
        e = Q.earnings("TST")
        self.assertFalse(e["ok"])
        self.assertTrue(e["khoa_dang_nhap"])
        self.put("financial-data", {"ticker": "TST", "revenue": {"2025": 5.0, "2026F": 6.0}})
        N.clear_cache()
        self.assertTrue(Q.earnings("TST")["ok"])

    def test_events_grouped_into_four_tabs(self):
        ev = [{"eventCode": c, "publicDate": "2026-0%d-01T00:00:00" % i, "eventTitleVi": c}
              for i, c in enumerate(("DIV", "DDIND", "AGME", "OTHE", "ISS"), 1)]
        self.put("events-all", ev)
        g = Q.events("TST")["groups"]
        self.assertEqual({k: v["n"] for k, v in g.items()}, {"dividend": 2, "shareholder": 1, "agm": 1, "other": 1})
        self.assertEqual(g["dividend"]["rows"][0]["ma_sk"], "ISS")       # mới nhất trước

    def test_fin_uses_metric_titles_and_drops_empty_rows(self):
        self.put("fs-metrics", {"INCOME_STATEMENT": [
            {"level": 1, "titleVi": "Doanh thu thuần", "field": "isa3"},
            {"level": 2, "titleVi": "Dòng rỗng", "field": "isa9"}]})
        self.put("fs-income", {"years": [{"yearReport": 2024, "lengthReport": 5, "isa3": 1e9, "isa9": None,
                                          "publicDate": "2025-03-01T00:00:00"},
                                         {"yearReport": 2025, "lengthReport": 5, "isa3": 2e9, "isa9": 0,
                                          "publicDate": "2026-03-01T00:00:00"}], "quarters": []})
        f = Q.fin("TST", "fs-income", "year")
        self.assertEqual(f["ky"], ["2024", "2025"])
        self.assertEqual(f["rows"], [(1, "Doanh thu thuần", [1e9, 2e9])])
        self.assertEqual(f["cong_bo"], "2026-03-01")
        self.assertTrue(f["ok"])

    def test_missing_cache_is_not_ok(self):
        self.assertFalse(Q.stats("TST", "gia", "D")["ok"])
        self.assertFalse(Q.news("TST")["ok"])
        self.assertFalse(Q.holders("TST")["ok"])


if __name__ == "__main__":
    unittest.main()
