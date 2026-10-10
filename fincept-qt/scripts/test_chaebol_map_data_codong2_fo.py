#!/usr/bin/env python3
"""Test chaebol_map_data_codong2_fo._impossible_fo: bỏ %NN vendor không thể đúng (rác thời UPCoM), giữ biến động thật."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import chaebol_map_data_codong2_fo as F  # noqa: E402

REAL = Path.home() / "SECOND BRAIN-OBSIDIAN/_System/fincept_bridge/state/vc_lk/BSR/price-history.json"


class ImpossibleFo(unittest.TestCase):
    def test_above_fol_dropped(self):
        fo, fol = [5.0] * 800 + [55.0], [49.0] * 801
        self.assertEqual(F._impossible_fo(fo, fol), [800])

    def test_upcom_junk_vs_recent_median(self):
        fo = [88.3, 49.8, 27.7] + [1.2] * 800       # BSR/GVR 2018 kiểu rác, mức thật ~1%
        fol = [100.0, 49.0, 100.0] + [49.0] * 800
        self.assertEqual(F._impossible_fo(fo, fol), [0, 1, 2])

    def test_real_high_ownership_kept(self):
        fo = [49.0] * 200 + [30.0] * 800            # FPT kiểu: từng chạm room 49%, nay 28 - 30%
        self.assertEqual(F._impossible_fo(fo, [49.0] * 1000), [])
        fo2 = [42.6] * 300 + [24.3] * 800           # MSN: 42.6% (2019) → 24.3%
        self.assertEqual(F._impossible_fo(fo2, [100.0] * 1100), [])

    def test_none_safe(self):
        self.assertEqual(F._impossible_fo([None, 3.0, None], [None, None, 49.0]), [])

    @unittest.skipUnless(REAL.exists(), "không có kho vc_lk")
    def test_bsr_real_peak_reasonable(self):
        import chaebol_map_data_codong2_gia as P
        b = P._base("BSR")
        peak = max(x for x in b["FO"] if x is not None)
        self.assertLess(peak, 10.0, "BSR: %NN rác 2018 (88.3%, 49.8%) phải bị loại")


if __name__ == "__main__":
    unittest.main()
