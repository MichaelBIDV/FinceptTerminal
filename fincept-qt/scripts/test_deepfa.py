#!/usr/bin/env python3
"""
Tests for deepfa.py (CLI contract: status · overview · ticker). Stdlib unittest only.

    cd fincept-qt/scripts && python3 -m unittest test_deepfa -v

Runs the script as a subprocess against the synthetic vault of test_deepfa_core (DEEPFA_VAULT,
DEEPFA_TODAY), exactly as EconomicsService/PythonRunner would, and parses stdout strictly
(NaN/Infinity tokens rejected, no key may start with "_"). LiveDataTest runs against the real vault
when it exists and only asserts shape and timing.
"""

import json
import os
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_deepfa_core as F  # noqa: E402  (fixture builder)


def _reject(token):
    raise ValueError("non-finite token in output: %s" % token)


def run_script(args, env_extra):
    env = dict(os.environ)
    env.update(env_extra)
    env["DEEPFA_FLOW_CACHE"] = "off"
    p = subprocess.run([sys.executable, "-B", os.path.join(HERE, "deepfa.py")] + args, capture_output=True, env=env, timeout=120)
    out = p.stdout.decode("utf-8")
    assert p.returncode == 0, "exit %d: %s" % (p.returncode, p.stderr.decode("utf-8", "replace")[-500:])
    assert out.count("\n") == 1 and out.endswith("\n"), "exactly one JSON line expected"
    return json.loads(out, parse_constant=_reject)


def no_private_keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert not (isinstance(k, str) and k.startswith("_")), "private key leaked: %s/%s" % (path, k)
            no_private_keys(v, path + "/" + str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            no_private_keys(v, "%s[%d]" % (path, i))


class _Fixture(F._Fixture):
    @classmethod
    def setUpClass(cls):
        F._Fixture.setUpClass.__func__(cls)
        cls.env = {"DEEPFA_VAULT": cls.root, "DEEPFA_TODAY": F.TODAY}


class CliTest(_Fixture):
    def test_bad_args(self):
        d = run_script([], self.env)
        self.assertEqual(d["error_code"], "BAD_ARGS")
        d = run_script(["ticker", "bad ticker!"], self.env)
        self.assertEqual(d["error_code"], "BAD_ARGS")
        d = run_script(["nope"], self.env)
        self.assertEqual(d["error_code"], "BAD_ARGS")

    def test_status_shape(self):
        d = run_script(["status"], self.env)
        self.assertNotIn("error", d)
        no_private_keys(d)
        keys = {l["key"] for l in d["layers"]}
        self.assertIn("fund", keys)
        self.assertTrue({"fflow", "etfc"} <= keys)
        self.assertTrue(d["gates"]["fund_detail"])
        self.assertEqual(d["counts"]["universe"], 1)
        self.assertEqual(d["counts"]["memo"], 1)
        self.assertEqual(d["gates"]["fund_intent"], "ok")
        self.assertIn("mark-to-market", d["gates"]["ledger"])

    def test_overview_rows(self):
        d = run_script(["overview"], self.env)
        self.assertNotIn("error", d)
        no_private_keys(d)
        self.assertEqual(d["meta"]["n_rows"], 1)
        r = d["rows"][0]
        self.assertEqual(r["tk"], "ABC")
        self.assertEqual(r["state"], "B")
        self.assertEqual(r["memo_date"], "2026-06-11")
        self.assertEqual(r["memo_status"], "stale")          # 104 days > 45
        self.assertTrue(r["can_regen"])
        self.assertIn("memo > 90 ngày", r["can_regen_ly_do"])
        self.assertEqual(r["gia"]["txt"], "66.600")
        self.assertEqual(r["gia"]["b"], "FACT-T2")
        self.assertEqual(r["tp"]["b"], "SS-T3")
        self.assertTrue(r["tp_stale"])
        self.assertEqual(r["fund_gate"], "ok")
        self.assertTrue(r["fund_label"].startswith("ACCUMULATION"))
        self.assertIn("TP Vietcap cũ 107 ngày", r["flags"])
        self.assertIn("ETF review 2,0 ngày KLGD", r["flags"])
        self.assertIn("tổng +2.000 cp", r["etf_du_bao_txt"])
        self.assertEqual(r["edi"]["txt"], "[CẦN DATA]")       # no EDI layer in the fixture

    def test_ticker_page(self):
        d = run_script(["ticker", "abc"], self.env)
        self.assertNotIn("error", d)
        no_private_keys(d)
        self.assertEqual(d["meta"]["tk"], "ABC")
        self.assertEqual(d["meta"]["memo"]["state"], "B")
        self.assertEqual(d["meta"]["memo"]["tier_hieu_luc"], "UNVERIFIED")
        self.assertTrue(d["meta"]["regen"]["can"])
        self.assertTrue(d["cong"]["dung"])                     # no fft_langkinh in fixture → gate closed by default
        self.assertEqual(d["header"]["gia"]["txt"], "67.000")            # lk_hoso.gia.bang 23/09 newer than vc_lk 22/09
        self.assertEqual(d["header"]["gia"]["t"], "2026-09-23")
        self.assertIn("lk_hoso.gia.bang", d["header"]["gia"]["n"])
        self.assertEqual(d["header"]["gia_adj"]["txt"], "66.600")        # CA-adjusted series unchanged
        self.assertIn("biên gộp", d["thesis"]["break_point"]["text"])
        self.assertEqual(d["dieu_kien"]["tom_tat"]["n"], 5)
        due = {it["date_hint"]: it["trang_thai"] for it in d["dieu_kien"]["dung"] + d["dieu_kien"]["lich"]}
        self.assertEqual(due["cuối 07/2026"], "quá hạn")
        self.assertEqual(due["Q3/2026"], "sắp đến hạn")        # 30/09 is 7 days from 23/09
        self.assertEqual(due["02/2027"], "chưa")
        self.assertIn("alignment", d["tension"]["live"])
        self.assertEqual(d["ledger"]["honest"]["is_track_record"], False)
        self.assertFalse(d["filing"]["worksheet"]["co"])
        self.assertTrue(d["chu_the"]["co"])                              # lk_hoso fixture present (gia.bang only)
        self.assertEqual(d["chu_the"]["fund"]["trang_thai"], "ok")       # fixture carries per-fund detail → gate ran
        self.assertFalse(d["kg"]["co"])
        self.assertIsNone(d["dinh_gia"]["hhp_chart"])
        self.assertEqual(len(d["dinh_gia"]["tp_strip"]), 1)
        self.assertTrue(d["dinh_gia"]["tp_strip"][0]["stale"])

    def test_ticker_without_memo_still_renders(self):
        d = run_script(["ticker", "ZZZ"], self.env)
        self.assertNotIn("error", d)
        self.assertIsNone(d["meta"]["memo"])
        self.assertTrue(d["meta"]["regen"]["can"])
        self.assertEqual(d["meta"]["regen"]["ly_do"], ["chưa có memo"])
        self.assertEqual(d["header"]["gia"]["txt"], "[CẦN DATA]")
        self.assertFalse(d["thesis"]["memo_co"])
        self.assertEqual(d["dieu_kien"]["tom_tat"]["n"], 0)


class LiveDataTest(unittest.TestCase):
    """Shape + timing on the real vault; skipped when it is absent."""

    def setUp(self):
        self.env = {k: v for k, v in os.environ.items() if k not in ("DEEPFA_VAULT", "DEEPFA_TODAY")}
        import deepfa_core as C
        os.environ.pop("DEEPFA_VAULT", None)
        if not os.path.isdir(C.memo_dir()):
            self.skipTest("real vault not present")

    def _run(self, args):
        t0 = time.time()
        p = subprocess.run([sys.executable, "-B", os.path.join(HERE, "deepfa.py")] + args, capture_output=True, env=self.env, timeout=180)
        self.assertEqual(p.returncode, 0)
        d = json.loads(p.stdout.decode("utf-8"), parse_constant=_reject)
        return d, time.time() - t0

    def test_overview_live(self):
        d, dt = self._run(["overview"])
        self.assertNotIn("error", d)
        self.assertGreater(d["meta"]["n_rows"], 100)
        no_private_keys(d)
        self.assertLess(dt, 30.0)   # cold cache may take ~15 s; warm ~1 s

    def test_ticker_live_fpt(self):
        d, dt = self._run(["ticker", "FPT"])
        self.assertNotIn("error", d)
        no_private_keys(d)
        self.assertLess(dt, 10.0)
        self.assertIn(d["cong"]["dung"], (True, False))


if __name__ == "__main__":
    unittest.main()
