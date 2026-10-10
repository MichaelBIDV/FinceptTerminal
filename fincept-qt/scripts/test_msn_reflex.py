#!/usr/bin/env python3
"""Unit tests for msn_reflex.py — synthetic fixtures (no network), plus one regression against the real
local stores that is skipped when they are absent.

Run: python3 -m unittest scripts/test_msn_reflex.py -v

The regression replays the dossier's own 23/09/2026 numbers with `--den 2026-09-23` and the profile's
frozen P/B parameters. It reads live stores, so a later Vietcap back-adjustment of MSN history (a new
dividend or bonus issue) can move the weekly closes; that is a real reproduction break worth seeing.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import msn_reflex as M  # noqa: E402

SCRIPT = os.path.join(HERE, "msn_reflex.py")
ENV_KEYS = ("MSN_REFLEX_DIR", "MSN_BRIDGE_DIR", "MSN_VNSTORE_DB", "MSN_KOS_DIR", "MSN_WIDATA_STORE", "MSN_TODAY")
BLOCK_KINDS = {"cong", "doan", "o_so", "bang", "the", "danh_sach", "trich", "bieu_do", "canh_bao", "chips"}

START = date(2026, 1, 5)            # Monday
DATA_TO = date(2026, 9, 24)         # Thursday → the week of Friday 25/09 is still open
BREAK = date(2026, 6, 25)           # Vietcap MSN share count changes here
LAST_WEEK_FRI = date(2026, 9, 18)


# ── Fixtures ─────────────────────────────────────────────────────────────────


def weekdays(start, end):
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


DAYS = weekdays(START, DATA_TO)


def msn_close(d):
    """Adjusted = raw for MSN. Flat 68,0k, week of 18/09 closes at 68,4k, last session 70,0k."""
    if d == DATA_TO:
        return 70000.0
    if M.friday(d) == LAST_WEEK_FRI:
        return 68400.0
    return 68000.0


def msn_vol(d):
    """1 m/session; the week of 18/09 trades 3 m/session → weekly ratio exactly 3,0× vs the 20 before."""
    return 3_000_000.0 if M.friday(d) == LAST_WEEK_FRI else 1_000_000.0


def profile():
    return {
        "schema": "msn_msr_reflex/1", "ho_so": "2026-09-24", "du_lieu_den": "2026-09-23",
        "tieu_de": "Hồ sơ độ trễ MSN", "tab": "MSN MSR Reflex", "eyebrow": "Hội đồng", "phu_de": "Phụ đề",
        "artifact_url": "https://claude.ai/artifact/test",
        "cong": {"dong": "CỔNG: TIỀN ĐẮT · chủ thể MSN: CẦN · playbook: bỏ đòn bẩy", "ket_luan_mot_dong": "Kết luận."},
        "tang_bang_chung": [{"tier": "FACT-T1", "mo_ta": "BCTC"}],
        "theo_doi_tuan": {
            "nhan": "Theo dõi tuần", "tieu_de": "MSN tuần này", "lich_chay": "09:00 thứ Bảy",
            "tham_so": {"pb_mu": 4.32, "pb_sd": 1.62, "bvps": 26049, "tier": "EST",
                        "so_huu": {"MCH": 0.7, "MSR": 0.9, "TCB": 0.15}, "so_cp_msn": 1_535_000_000,
                        "so_cp_msn_nguon": "hồ sơ",
                        "vung_gia_k": {"giam": [50, 61], "chuyen_duoi": [61, 65], "co_so": [65, 86],
                                       "chuyen_tren": [86, 100], "tang": [100, 117]}, "vung_gia_tier": "EST"},
            "tuan_goc": {"nhan": "Tuần gốc", "text": "MSN 69,8", "ngay": "2026-09-23", "msn": 69.8, "msn_lt": 0.49,
                         "pb": 2.68, "sigma": -1.01, "hanh_dong": "giữ ≤ 5% NAV, không margin"},
            "tin_hieu": [
                {"id": "X1", "loai": "xac_nhan", "ten": "Tuần đóng cửa", "nguong": "> 80,0k", "bien": "msn_dong_tuan",
                 "phep": ">", "muc": 80.0},
                {"id": "X2", "loai": "xac_nhan", "ten": "KL tuần ÷ TB 20 tuần", "nguong": "≥ 1,5×",
                 "bien": "kl_tuan_tb20", "phep": ">=", "muc": 1.5},
                {"id": "X3", "loai": "xac_nhan", "ten": "MSN ÷ look-through", "nguong": "> 0,60×", "bien": "msn_lt",
                 "phep": ">", "muc": 0.6},
                {"id": "P1", "loai": "phu_dinh", "ten": "Stop", "nguong": "< 63,4k", "bien": "msn_dong_tuan",
                 "phep": "<", "muc": 63.4, "ghi_chu": "Kích hoạt → hạ MSN về 3% NAV"},
                {"id": "P3", "loai": "phu_dinh", "ten": "LNST Q3", "bien": ["a", "b"], "phep": "<", "muc": [1, 2],
                 "gia_tri_in": "chưa công bố", "trang_thai": "Chờ", "mau": "warn", "tier": "FACT-T1"},
                {"id": "P5", "loai": "phu_dinh", "ten": "MSN/LT khi con tăng", "nguong": "< 0,45×", "bien": "msn_lt",
                 "phep": "<", "muc": 0.45}],
            "chat_xuc_tac": [
                {"id": "C2", "ten": "KQKD Q3", "moc": "~cuối 10/2026", "dieu_kien": "≥ 3.000 tỷ", "trang_thai": "Chờ",
                 "mau": "warn"},
                {"id": "C4", "ten": "MSR lên HOSE", "moc": "2027", "dieu_kien": "trước sự kiện", "trang_thai": "Chưa",
                 "mau": "neu"},
                {"id": "C5", "ten": "VN-Index > 1.850 và khối ngoại mua ròng", "moc": "—", "dieu_kien": "VNI",
                 "trang_thai": "Chưa", "mau": "neu", "muc_vnindex": 1850}],
            "nhat_ky_cot": ["Tuần (phiên cuối)", "MSN · ± tuần", "KL ÷ TB20", "MCH · MSR · TCB", "VN-Index",
                            "LT · MSN/LT", "P/B · σ", "Vùng", "X · P", "Hành động"],
            "nhat_ky": [{"tuan": "23/09/2026 · gốc", "ngay": "2026-09-23", "msn_in": "69,8", "x_p": "0/3 · 0/5",
                         "vung": "Cơ sở", "hanh_dong": "≤ 5% NAV"}],
            "cach_tinh": "Cách tính.",
            "viec_treo": [{"viec": "Việc A", "can_gi": "BCTC", "trang_thai": "Mở", "cap_nhat": "24/09"}],
            "synthesis_tuan": ["Synthesis hồ sơ."],
            "sizing_may": {"tran_nav_conviction4_pct": 8, "stop_ha_ve_pct": 3}},
        "tiles_dau": [{"nhan": "MSN · P/B", "gia_tri": "2,68×", "tier": "EST"},
                      {"nhan": "Tỷ trọng họ Vin", "gia_tri": "28,0%", "tier": "T2"}],
        "keynotes": {"tieu_de": "Keynotes", "phu_de": "Chín điều", "muc": [{"id": "K1", "tieu_de": "A", "noi_dung": "B",
                                                                           "tier": ["EST"]}]},
        "nguon": ["Nguồn 1"],
    }


def vc_rows(sym):
    """Vietcap price-history rows up to 23/09 (the board row of 24/09 lives only in vnstore)."""
    cot = ["tradingDate", "closePrice", "closePriceAdjusted", "totalMatchVolume", "foreignNetValueTotal",
           "totalShares", "marketCap"]
    hang = []
    for d in DAYS:
        if d >= DATA_TO:
            continue
        if sym == "MSN":
            c = msn_close(d)
            sh = 1_440_000_000.0 if d < BREAK else 1_460_000_000.0
            hang.append([d.isoformat(), c, c, msn_vol(d), 1e9, sh, c * sh])
        elif sym == "MCH":   # raw 130k; the adjusted series (and vnstore history) is 100k
            hang.append([d.isoformat(), 130000.0, 100000.0, 1e5, 0.0, 1e9, 130000.0 * 1e9])
        elif sym == "MSR":
            hang.append([d.isoformat(), 50000.0, 50000.0, 1e5, 0.0, 1.1e9, 50000.0 * 1.1e9])
        else:                # TCB: marketCap missing on the last row → close × last totalShares
            last = d == DATA_TO - timedelta(days=1)
            hang.append([d.isoformat(), 30000.0, 30000.0, 1e6, 0.0, None if last else 7e9,
                         None if last else 30000.0 * 7e9])
    return {"meta": {"lay_luc": "2026-09-24T06:44:00+07:00"}, "du_lieu": {"cot": cot, "hang": hang}}


def build_db(path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE nen_ngay (symbol TEXT, ngay TEXT, mo REAL, cao REAL, thap REAL, dong REAL, kl REAL, "
                "nguon TEXT, PRIMARY KEY (symbol, ngay))")
    con.execute("CREATE TABLE gia_moi (symbol TEXT PRIMARY KEY, ngay TEXT, luc TEXT, gia REAL, tham_chieu REAL, "
                "kl REAL, nn_mua_gt REAL, nn_ban_gt REAL, nguon TEXT)")
    con.execute("CREATE TABLE free_float (symbol TEXT PRIMARY KEY, ff_cp REAL, ff_pct REAL, issue_share REAL, "
                "nguon TEXT, cap_nhat TEXT, json TEXT)")
    con.execute("CREATE TABLE ma (symbol TEXT PRIMARY KEY, san TEXT, loai TEXT, ten TEXT, nganh TEXT, nhom TEXT, "
                "theo_doi INTEGER, cap_nhat TEXT)")
    rows = []
    for d in DAYS:
        board = d == DATA_TO
        src = "vci_board" if board else "vci_history"
        rows.append(("MSN", d.isoformat(), msn_close(d), msn_vol(d), src))
        rows.append(("MCH", d.isoformat(), 130000.0 if board else 100000.0, 1e5, src))
        rows.append(("TCB", d.isoformat(), 30000.0, 1e6, src))
        rows.append(("VNINDEX", d.isoformat(), 1800.0, 5e8, src))
        if d >= date(2026, 6, 1):
            rows.append(("MSR", d.isoformat(), 50000.0, 1e5, src))
    con.executemany("INSERT INTO nen_ngay VALUES (?, ?, NULL, NULL, NULL, ?, ?, ?)", rows)
    con.execute("INSERT INTO gia_moi VALUES ('MSN', ?, ?, 70000, 68400, 5e6, 300e9, 100e9, 'vci_board')",
                (DATA_TO.isoformat(), DATA_TO.isoformat() + "T16:40:00+07:00"))
    con.executemany("INSERT INTO free_float VALUES (?, 0, 0, ?, 'vci_overview', '2026-09-21', '{}')",
                    [("MSN", 1_460_000_000.0), ("MCH", 1e9), ("MSR", 1.1e9), ("TCB", 7e9)])
    con.executemany("INSERT INTO ma VALUES (?, ?, 'stock', '', '', '', 1, '')",
                    [("MSN", "HOSE"), ("MCH", "HOSE"), ("MSR", "UPCOM"), ("TCB", "HOSE"), ("VNINDEX", "INDEX")])
    con.commit()
    con.close()


def hhp(mean=4.0, sd=1.0, bvps=20000):
    return {"meta": {"generated": "2026-09-24 16:46 ICT", "stale_fields": []},
            "index": {"pe": {"now": 12.4, "mean": 15.0, "sd": 1.9, "sigma": -1.3, "as_of": "2026-09-23"},
                      "pb": {"now": 2.0}},
            "exvic3": {"w3_now": 28.0, "vic3": [{"ticker": "VIC", "pe": 85.4}], "series": {}},
            "by_ticker": {"MSN": {"pb": {"mean": mean, "sd": sd, "per_share": bvps}}}}


def hhp_series():
    fridays = [d for d in DAYS if d.weekday() == 4]
    return {"pb": {"price": [[M.day_ms(d), msn_close(d) / 1000.0] for d in fridays],
                   "base": [[M.day_ms(d), 20.0] for d in fridays], "mean": 4.0, "sd": 1.0}}


class Fixture:
    """A throw-away SYS tree; `env()` points msn_reflex at it."""

    def __init__(self, prof=None, with_hhp=True, hhp_obj=None):
        self.root = tempfile.mkdtemp(prefix="msn_reflex_test_")
        self.kos = os.path.join(self.root, "knowledge_os")
        self.pdir = os.path.join(self.kos, "msn_reflex")
        self.bridge = os.path.join(self.root, "fincept_bridge")
        os.makedirs(self.pdir)
        os.makedirs(os.path.join(self.bridge, "vnstore"))
        os.makedirs(os.path.join(self.kos, "hhp_vn100_series"))
        self.write(os.path.join(self.pdir, "ho_so_2026-09-24.json"), profile() if prof is None else prof)
        build_db(os.path.join(self.bridge, "vnstore", "vn_store.db"))
        for s in M.SYMS:
            self.write(os.path.join(self.bridge, "state", "vc_lk", s, "price-history.json"), vc_rows(s))
        if with_hhp:
            self.write(os.path.join(self.kos, "hhp_vn100_valuation.json"), hhp_obj or hhp())
            self.write(os.path.join(self.kos, "hhp_vn100_series", "MSN.json"), hhp_series())
        self.widata = os.path.join(self.root, "widata.json")
        self.write(self.widata, {"canvases": {"wc-vnindex": {"series": [
            {"t": M.day_ms(date(2023, 1, 3)), "v": 1050.0}, {"t": M.day_ms(date(2025, 12, 31)), "v": 1700.0}]}}})
        self.write(os.path.join(self.bridge, "data", "chaebol_ecosystems.json"), {
            "as_of": "2026-09-23 10:04 ICT", "ecosystems": {"Masan-TCB": {"members": {
                "TCB": {"top_shareholders": [{"ownerName": "Công ty Cổ phần Tập đoàn Masan", "percentage": 14.8,
                                              "publicDate": "2026-06-30"}]}}}}})

    @staticmethod
    def write(path, obj):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False)

    def env(self, today="2026-09-24"):
        return {"MSN_REFLEX_DIR": self.pdir, "MSN_BRIDGE_DIR": self.bridge, "MSN_KOS_DIR": self.kos,
                "MSN_WIDATA_STORE": self.widata, "MSN_TODAY": today}

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


def walk(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)
    else:
        yield o


class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()

    def tearDown(self):
        self.fx.close()

    def overview(self, den=None, tham_so="auto", today="2026-09-24"):
        with mock.patch.dict(os.environ, self.fx.env(today)):
            return M.build_overview(den, tham_so)


# ── Helpers ──────────────────────────────────────────────────────────────────


class HelperTests(unittest.TestCase):
    def test_fmt_vn(self):
        self.assertEqual(M.fmt_vn(4.96), "4,96")
        self.assertEqual(M.fmt_vn(-4.5), "−4,5")
        self.assertEqual(M.fmt_vn(1.5, sign=True), "+1,5")
        self.assertEqual(M.fmt_vn(2700), "2.700")
        self.assertEqual(M.fmt_vn(None), M.CAN)
        self.assertEqual(M.k_txt(69800), "69,8")
        self.assertEqual(M.k_txt(33150), "33,15")
        self.assertEqual(M.x_txt(0.4902), "0,49×")
        self.assertEqual(M.pct_txt(2.047), "+2,0%")
        self.assertEqual(M.sigma_txt(-1.0126), "−1,01σ")

    def test_friday_and_weeks(self):
        self.assertEqual(M.friday(date(2026, 9, 21)), date(2026, 9, 25))
        self.assertEqual(M.friday(date(2026, 9, 25)), date(2026, 9, 25))
        ds = weekdays(date(2026, 9, 14), date(2026, 9, 24))
        ws = M.weeks_of(ds, [float(i) for i in range(len(ds))], [1.0] * len(ds))
        self.assertEqual([w["fri"] for w in ws], [date(2026, 9, 18), date(2026, 9, 25)])
        self.assertEqual((ws[0]["n"], ws[0]["kl"], ws[0]["close"]), (5, 5.0, 4.0))
        self.assertEqual(ws[1]["last"], date(2026, 9, 24))

    def test_vol_ratio_excludes_the_week_itself(self):
        weeks = [{"kl": 5.0} for _ in range(20)] + [{"kl": 15.0}]
        self.assertAlmostEqual(M.vol_ratio(weeks, 20), 3.0)
        self.assertIsNone(M.vol_ratio(weeks, 19))

    def test_zone_bounds(self):
        vung = profile()["theo_doi_tuan"]["tham_so"]["vung_gia_k"]
        self.assertEqual(M.zone_of(65.0, vung), "Cơ sở")
        self.assertEqual(M.zone_of(64.99, vung), "chuyển")
        self.assertEqual(M.zone_of(117.0, vung), "Tăng")
        self.assertEqual(M.zone_of(49.0, vung), "ngoài dải")
        self.assertEqual(M.zone_label(69.8, vung), "Cơ sở 65–86k")

    def test_status_colours(self):
        self.assertEqual(M.status_mau("An toàn"), "xanh")
        self.assertEqual(M.status_mau("Kích hoạt"), "do")
        self.assertEqual(M.status_mau("Chờ"), "vang")
        self.assertEqual(M.status_mau("ĐÚNG LUẬT, TRƯỢT GIÁ"), "vang")
        self.assertEqual(M.tier_mau("T1·DATA"), "xanh")
        self.assertEqual(M.tier_mau("1 nguồn"), "do")


# ── Live computation on synthetic stores ─────────────────────────────────────


class LiveTests(FixtureCase):
    def test_weekly_block(self):
        live = self.overview()["live"]
        self.assertEqual(live["data_to"], "2026-09-24")
        self.assertEqual(live["close"], 70000.0)
        self.assertEqual(live["last_week"]["last"], "2026-09-18")
        self.assertEqual(live["last_week"]["close"], 68400.0)
        self.assertAlmostEqual(live["kl_ratio"], 3.0)          # not 15/5.5: the week itself is excluded
        self.assertEqual(live["open_week"]["n"], 4)
        self.assertAlmostEqual(live["vs_week_pct"], (70000 / 68400 - 1) * 100)

    def test_look_through_uses_raw_prices_and_profile_shares(self):
        live = self.overview()["live"]
        # MCH raw 130k (vnstore history is adjusted 100k); TCB last Vietcap row has no marketCap.
        lt = 0.7 * 130000 * 1e9 + 0.9 * 50000 * 1.1e9 + 0.15 * 30000 * 7e9
        self.assertAlmostEqual(live["lt"], lt, delta=1e6)
        self.assertAlmostEqual(live["mcap_msn"], 70000 * 1_535_000_000, delta=1)
        self.assertAlmostEqual(live["ratio"], 70000 * 1_535_000_000 / lt, places=6)
        self.assertAlmostEqual(live["ratio_local_shares"], 70000 * 1_460_000_000 / lt, places=6)
        self.assertEqual(live["msn_share_break"], BREAK.isoformat())

    def test_vietcap_row_without_marketcap_falls_back_to_close_times_shares(self):
        live = self.overview(den=date(2026, 9, 23))["live"]       # TCB's 23/09 Vietcap row has no marketCap
        lt = 0.7 * 130000 * 1e9 + 0.9 * 50000 * 1.1e9 + 0.15 * 30000 * 7e9
        self.assertAlmostEqual(live["lt"], lt, delta=1e6)

    def test_share_gap_warning(self):
        warnings = self.overview()["meta"]["warnings"]
        self.assertTrue(any(w.startswith("Số cp MSN: hồ sơ 1.535 triệu") for w in warnings), warnings)

    def test_history_before_break_uses_vietcap_marketcap(self):
        p = M.paths
        with mock.patch.dict(os.environ, self.fx.env()):
            warnings = []
            prof, _, pday = M.load_profile(p()["profile_dir"])
            kho = M.Kho(p(), None, warnings)
            lv = M.Live(kho, prof, M.Issue(prof, pday, None), "auto", warnings)
        before = date(2026, 6, 19)
        m, _ = kho.mcap("MSN", before, lv.msn_shares, lv.msn_break)
        self.assertAlmostEqual(m, 68000 * 1_440_000_000)
        m, _ = kho.mcap("MSN", date(2026, 7, 3), lv.msn_shares, lv.msn_break)
        self.assertAlmostEqual(m, 68000 * 1_535_000_000)

    def test_pb_engine_params_and_mismatch_warning(self):
        out = self.overview()
        live = out["live"]
        self.assertAlmostEqual(live["pb"], 3.5)
        self.assertAlmostEqual(live["sigma"], -0.5)
        self.assertTrue(live["pb_params"]["engine"])
        self.assertTrue(any("Tham số P/B lệch" in w for w in out["meta"]["warnings"]))

    def test_pb_profile_params_when_forced(self):
        live = self.overview(tham_so="ho_so")["live"]
        self.assertAlmostEqual(live["pb"], 70000 / 26049)
        self.assertAlmostEqual(live["sigma"], (70000 / 26049 - 4.32) / 1.62)

    def test_pb_fallback_without_engine(self):
        self.fx.close()
        self.fx = Fixture(with_hhp=False)
        out = self.overview()
        self.assertFalse(out["live"]["pb_params"]["engine"])
        self.assertTrue(any("Engine HHP không có μ/σ/BVPS" in w for w in out["meta"]["warnings"]))

    def test_signals(self):
        sig = self.overview()["live"]["signals"]
        self.assertEqual(sig["X1"]["trang_thai"], "Chưa")
        self.assertEqual(sig["X2"]["trang_thai"], "Đạt")          # 3,0× ≥ 1,5×
        self.assertEqual(sig["P1"]["trang_thai"], "An toàn")
        self.assertIn("Kích hoạt → hạ MSN về 3% NAV", sig["P1"]["ghi_chu"])
        self.assertNotIn("P3", sig)                               # issue-sourced, not live

    def test_p5_needs_rising_look_through(self):
        # A smaller MSN share count pushes MSN/LT under 0,45×, but LT is flat week on week → not triggered.
        self.fx.close()
        prof = profile()
        prof["theo_doi_tuan"]["tham_so"]["so_cp_msn"] = 900_000_000     # pushes MSN/LT under 0,45
        self.fx = Fixture(prof=prof)
        sig = self.overview()["live"]["signals"]
        self.assertEqual(sig["X3"]["trang_thai"], "Chưa")
        self.assertEqual(sig["P5"]["trang_thai"], "An toàn")           # LT did not rise vs 18/09
        self.assertIn("LT không tăng", sig["P5"]["ghi_chu"])

    def test_den_cuts_every_source(self):
        live = self.overview(den=date(2026, 9, 18))["live"]
        self.assertEqual(live["data_to"], "2026-09-18")
        self.assertIsNone(live["open_week"])
        self.assertEqual(live["last_week"]["last"], "2026-09-18")
        self.assertIsNone(live["session"]["nn"])                  # gia_moi is dated 24/09 → cut

    def test_catalyst_c5_live(self):
        out = self.overview()
        rows = [b for s in out["trang"]["sections"] if s["id"] == "theo_doi_tuan" for b in s["khoi"]
                if b["kieu"] == "bang" and b["cot"][0] == "Chất xúc tác"][0]["dong"]
        c5 = [r for r in rows if r[0]["t"].startswith("C5")][0]
        self.assertIn("LIVE: VN-Index 1.800", c5[2])
        self.assertEqual(c5[3]["t"], "Chưa")
        c4 = [r for r in rows if r[0]["t"].startswith("C4")][0]
        self.assertIn("UPCOM", c4[2])

    def test_p5_on_a_week_close_compares_with_the_previous_week(self):
        # Saturday run / --den on a Friday: the current point closes the week of 18/09 itself, so "LT tăng so
        # với tuần trước" must compare with 11/09 (before the fix it compared LT with itself → P5 never fired).
        self.fx.close()
        prof = profile()
        prof["theo_doi_tuan"]["tham_so"]["so_cp_msn"] = 900_000_000     # pushes MSN/LT under 0,45
        self.fx = Fixture(prof=prof)
        msr = vc_rows("MSR")
        for r in msr["du_lieu"]["hang"]:                                # MSR +20% in the week of 18/09 → LT up
            if M.friday(date.fromisoformat(r[0])) == LAST_WEEK_FRI:
                r[1], r[2], r[6] = 60000.0, 60000.0, 60000.0 * 1.1e9
        Fixture.write(os.path.join(self.fx.bridge, "state", "vc_lk", "MSR", "price-history.json"), msr)
        live = self.overview(den=LAST_WEEK_FRI, today="2026-09-19")["live"]
        self.assertIsNone(live["open_week"])
        self.assertGreater(live["lt"], live["lt_prev_week"])
        self.assertEqual(live["signals"]["P5"]["trang_thai"], "Kích hoạt")
        self.assertEqual(live["ref_week"], "2026-09-11")
        self.assertIn("LT tăng so với tuần 11/09", live["signals"]["P5"]["ghi_chu"])
        self.assertAlmostEqual(live["vs_week_pct"], (68400 / 68000 - 1) * 100)
        self.assertEqual(live["ratio_pct_n"], live["ratio_n"] - 1)       # the current week is not its own peer

    def test_action_keeps_the_dossiers_rule_conflict(self):
        # X1 + X2 (+ Q3) pick the dossier's 8% branch; the dossier marks it as conflicting with hard rule #10,
        # so the page must never print it as a bare "khôi phục 8%" instruction.
        self.fx.close()
        prof = profile()
        prof["hanh_dong"] = {"xung_dot_luat": "Hard rule #10 chỉ cho giải ngân ở pha 3."}
        self.fx = Fixture(prof=prof)
        Fixture.write(os.path.join(self.fx.pdir, "tuan_2026-10-31.json"),
                      {"ky": "2026-10-31", "xuc_tac": {"C2": {"trang_thai": "Đạt"}}})
        env = dict(self.fx.env("2026-11-01"), MSN_HANH_DONG="luat_ho_so")   # legacy rule-based pick
        with mock.patch.dict(os.environ, env):
            p = M.paths()
            warnings = []
            prof, _, pday = M.load_profile(p["profile_dir"])
            tuan, _ = M.load_tuan(p["profile_dir"], pday, warnings)
            lv = M.Live(M.Kho(p, None, warnings), prof, M.Issue(prof, pday, tuan), "auto", warnings)
            text, mau = lv.action(True, True, False)                     # X1 + X2 + Q3 (C2 "Đạt")
            self.assertIn("xung đột luật, chờ quyết", text)
            self.assertTrue(text.startswith("giữ ≤ 5% NAV, không margin"))
            self.assertEqual(mau, "vang")
            self.assertEqual(lv.action(True, False, False), ("giữ ≤ 5% NAV, không margin", "xam"))
            self.assertEqual(lv.action(True, True, True)[1], "do")      # P1 wins

    def test_action_is_frozen_by_default(self):
        # CỔNG v1.7 DỪNG (decision 07/10/2026): whatever X1/X2/P1 say, the action text is the dossier's own
        # base rule, labelled FROZEN, never a re-evaluated NAV branch.
        with mock.patch.dict(os.environ, self.fx.env("2026-11-01")):
            os.environ.pop("MSN_HANH_DONG", None)
            p = M.paths()
            warnings = []
            prof, _, pday = M.load_profile(p["profile_dir"])
            tuan, _ = M.load_tuan(p["profile_dir"], pday, warnings)
            lv = M.Live(M.Kho(p, None, warnings), prof, M.Issue(prof, pday, tuan), "auto", warnings)
            for args in ((True, True, False), (False, False, True), (False, False, False)):
                text, mau = lv.action(*args)
                self.assertTrue(text.startswith("ĐÓNG BĂNG · luật hồ sơ"), text)
                self.assertTrue(text.endswith("giữ ≤ 5% NAV, không margin"), text)
                self.assertNotIn("khôi phục", text)
                self.assertNotIn("hạ về", text)
                self.assertEqual(mau, "xam")

    def test_stale_engine_block_is_flagged_on_the_vin_tile(self):
        self.fx.close()
        obj = hhp()
        obj["exvic3"]["stale"] = True
        self.fx = Fixture(hhp_obj=obj)
        out = self.overview()
        tiles = [t for s in out["trang"]["sections"] if s["id"] == "o_so_dau" for b in s["khoi"]
                 if b["kieu"] == "o_so" for t in b["o"]]
        vin = [t for t in tiles if t["nhan"].startswith("Tỷ trọng họ Vin")][0]
        self.assertIn("engine đánh dấu stale", vin["phu"])
        self.assertEqual(vin["mau"], "vang")

    def test_c4_status_keeps_its_as_of(self):
        out = self.overview()
        rows = [b for s in out["trang"]["sections"] if s["id"] == "theo_doi_tuan" for b in s["khoi"]
                if b["kieu"] == "bang" and b["cot"][0] == "Chất xúc tác"][0]["dong"]
        c4 = [r for r in rows if r[0]["t"].startswith("C4")][0]
        c5 = [r for r in rows if r[0]["t"].startswith("C5")][0]
        self.assertIn("hồ sơ 24/09/2026", c4[2])                  # status "Chưa" is issue-sourced
        self.assertNotIn("hồ sơ", c5[2])                            # C5 is computed live end to end


class IssueOverrideTests(FixtureCase):
    def test_tuan_file_overrides_issue_values_only(self):
        Fixture.write(os.path.join(self.fx.pdir, "tuan_2026-10-31.json"), {
            "ky": "2026-10-31", "tin_hieu": {"P3": {"gia_tri": "LNST MSR Q3 1.200 tỷ", "trang_thai": "An toàn"},
                                             "X1": {"trang_thai": "Đạt"}},
            "xuc_tac": {"C2": {"trang_thai": "Đạt"}}, "synthesis": "Synthesis mới."})
        out = self.overview(today="2026-11-01")
        self.assertEqual(out["meta"]["tuan_ky"], "2026-10-31")
        self.assertEqual(out["live"]["signals"]["X1"]["trang_thai"], "Chưa")     # live wins for X1
        page = json.dumps(out["trang"], ensure_ascii=False)
        self.assertIn("LNST MSR Q3 1.200 tỷ · hồ sơ 31/10/2026", page)
        self.assertIn("Synthesis mới.", page)
        self.assertIn("Synthesis tuần · 31/10/2026", page)

    def test_older_tuan_file_is_ignored(self):
        Fixture.write(os.path.join(self.fx.pdir, "tuan_2026-09-01.json"), {"ky": "2026-09-01", "synthesis": "cũ"})
        out = self.overview()
        self.assertIsNone(out["meta"]["tuan_file"])
        self.assertNotIn("\"cũ\"", json.dumps(out["trang"], ensure_ascii=False))


# ── Annexes (bo_sung_*.json) ─────────────────────────────────────────────────


def annex(ky="2026-09-24"):
    """Synthetic annex: MSR stake 0,8 from 21/09, a pending MCH line, a bad line, a chaebol table, and one
    pass-through section with an unknown block and two misfit table rows."""
    return {
        "schema": "msn_bo_sung/1", "ky": ky, "tieu_de": "Bổ sung thử", "artifact_url": "https://claude.ai/artifact/bs",
        "so_huu_lich": [
            {"ma": "MSR", "tu": "2026-09-21", "ty_le": 0.8, "tier": "FACT-T1", "nguon": "CBTT thử"},
            {"ma": "MCH", "tu": "2026-10-23", "ty_le": 0.75, "ap_dung": False, "tier": "FACT-T1", "nguon": "Lepus"},
            {"ma": "XYZ", "tu": "2026-09-21", "ty_le": 0.5}],
        "so_huu_hieu_dung": {"MCH": {"ty_le": 0.66, "nguon": "BCTN thử"}},
        "he_sinh_thai": {"tieu_de": "Hệ sinh thái thử", "ghi_chu": "Chú thích.", "doan": ["Đọc bảng."], "thanh_vien": [
            {"ma": "MCH", "ten": "Hàng tiêu dùng", "phap_ly": 0.7, "hieu_dung": 0.66, "trong_lt": True},
            {"ma": "MSR", "ten": "Vonfram", "phap_ly": 0.8, "hieu_dung": 0.8, "trong_lt": True},
            {"ma": "TCB", "ten": "Ngân hàng", "phap_ly": 0.15, "hieu_dung": 0.15, "trong_lt": True},
            {"ma": "MML", "ten": "Thịt", "phap_ly": 0.9, "hieu_dung": 0.9, "trong_lt": False},
            {"ten": "WinCommerce", "chuoi": "chưa niêm yết"}]},
        "sections": [{"id": "lepus", "so": "BS2", "tieu_de": "Sự kiện thử", "khoi": [
            {"kieu": "doan", "text": "Đoạn"}, {"kieu": "khoi_la"},
            {"kieu": "bang", "cot": ["A", "B"], "dong": [["1"], ["1", "2", "3"], ["x", "y"]]}]}]}


def mml_rows():
    cot = ["tradingDate", "closePrice", "closePriceAdjusted", "totalMatchVolume", "foreignNetValueTotal",
           "totalShares", "marketCap"]
    hang = [[d.isoformat(), 27000.0, 27000.0, 1e4, 0.0, 3.4e8, 27000.0 * 3.4e8] for d in DAYS if d < DATA_TO]
    return {"meta": {"lay_luc": "2026-09-24T06:44:00+07:00"}, "du_lieu": {"cot": cot, "hang": hang}}

class AnnexTests(FixtureCase):
    LT_TAB = 0.7 * 130000 * 1e9 + 0.8 * 50000 * 1.1e9 + 0.15 * 30000 * 7e9

    def write_annex(self, ky="2026-09-24", obj=None):
        Fixture.write(os.path.join(self.fx.pdir, "bo_sung_%s.json" % ky), obj or annex(ky))
        Fixture.write(os.path.join(self.fx.bridge, "state", "vc_lk", "MML", "price-history.json"), mml_rows())

    def test_schedule_applies_from_its_date_only(self):
        self.write_annex()
        out = self.overview()
        self.assertAlmostEqual(out["live"]["lt"], self.LT_TAB, delta=1e6)
        with mock.patch.dict(os.environ, self.fx.env()):
            p = M.paths()
            warnings = []
            prof, _, pday = M.load_profile(p["profile_dir"])
            ann = M.load_bo_sung(p["profile_dir"], pday, None, warnings)
            lich, cho = M.ownership_schedule(ann, warnings)
            kho = M.Kho(p, None, warnings, M.annex_symbols(ann))
            lv = M.Live(kho, prof, M.Issue(prof, pday, None), "auto", warnings, lich, cho)
        self.assertEqual(lv.weight("MSR", date(2026, 9, 18)), 0.9)      # earlier weeks keep the profile stake
        self.assertEqual(lv.weight("MSR", date(2026, 9, 21)), 0.8)
        self.assertEqual(lv.weight("MCH", date(2026, 10, 30)), 0.7)     # the pending line is never applied
        self.assertEqual([c[0] for c in cho], ["MCH"])
        self.assertTrue(any("XYZ" in w for w in warnings), warnings)
        self.assertIn("MML", kho.vc)
        page = json.dumps(out["trang"], ensure_ascii=False)
        self.assertIn("MSR 80% từ 21/09/2026", page)
        self.assertIn("Chờ CBTT, chưa áp dụng: MCH 75%", page)
        self.assertIn("hồ sơ/bổ sung: MCH 70% · MSR 80% (bổ sung từ 21/09)", page)

    def test_sections_follow_the_weekly_block(self):
        self.write_annex()
        out = self.overview()
        ids = [s["id"] for s in out["trang"]["sections"]]
        self.assertEqual(ids[:5], ["cong", "theo_doi_tuan", "bo_sung_he_sinh_thai", "bo_sung_lepus", "o_so_dau"])
        warnings = out["meta"]["warnings"]
        self.assertTrue(any("khoi_la" in w for w in warnings), warnings)
        self.assertEqual(sum("cần 2" in w for w in warnings), 2)
        for s in out["trang"]["sections"]:
            for k in ("id", "so", "tieu_de", "eyebrow", "lede", "khoi"):
                self.assertIn(k, s)
            for b in s["khoi"]:
                self.assertIn(b["kieu"], BLOCK_KINDS)
                if b["kieu"] == "bang":
                    for r in b["dong"]:
                        self.assertEqual(len(r), len(b["cot"]), (s["id"], b["cot"]))
        self.assertEqual(out["meta"]["bo_sung"][0]["ky"], "2026-09-24")
        self.assertEqual(out["meta"]["bo_sung"][0]["artifact_url"], "https://claude.ai/artifact/bs")

    def test_live_chaebol_table(self):
        self.write_annex()
        out = self.overview()
        hst = out["live"]["he_sinh_thai"]
        mcap_msn = 70000 * 1_535_000_000
        lt_eff = 0.66 * 130000 * 1e9 + 0.8 * 50000 * 1.1e9 + 0.15 * 30000 * 7e9
        lt_ext = lt_eff + 0.9 * 27000 * 3.4e8
        self.assertAlmostEqual(hst["lt_eff"], lt_eff, delta=1e6)
        self.assertAlmostEqual(hst["ratio_eff"], mcap_msn / lt_eff, places=6)
        self.assertAlmostEqual(hst["lt_ext"], lt_ext, delta=1e6)
        self.assertAlmostEqual(hst["ratio_ext"], mcap_msn / lt_ext, places=6)
        sec_ = [s for s in out["trang"]["sections"] if s["id"] == "bo_sung_he_sinh_thai"][0]
        table = [b for b in sec_["khoi"] if b["kieu"] == "bang"][0]
        self.assertEqual(len(table["dong"]), 5)
        self.assertEqual(table["dong"][3][3]["t"], "ngoài LT")
        self.assertEqual(table["dong"][4][3]["t"], "chưa niêm yết")
        self.assertEqual(sum(1 for r in out["csv"]["rows"] if r[0] == "Bổ sung"), 4)

    def test_mch_warning_names_the_annex_source(self):
        self.write_annex()
        warnings = self.overview()["meta"]["warnings"]
        self.assertTrue(any("hiệu dụng 66% theo BCTN thử" in w for w in warnings), warnings)

    def test_annex_older_than_profile_or_after_den_is_ignored(self):
        self.write_annex(ky="2026-09-01")
        self.write_annex(ky="2026-10-06")
        out = self.overview(den=date(2026, 9, 23))
        self.assertEqual(out["meta"]["bo_sung"], [])
        self.assertFalse(any(s["id"].startswith("bo_sung_") for s in out["trang"]["sections"]))

    def test_bad_schema_is_skipped_with_warning(self):
        Fixture.write(os.path.join(self.fx.pdir, "bo_sung_2026-09-25.json"), {"schema": "khac/1"})
        out = self.overview()
        self.assertTrue(any("cần schema msn_bo_sung/1" in w for w in out["meta"]["warnings"]))
        self.assertEqual(out["meta"]["bo_sung"], [])

    def test_tuan_file_can_recolour_a_signal(self):
        Fixture.write(os.path.join(self.fx.pdir, "tuan_2026-10-31.json"), {
            "ky": "2026-10-31", "tin_hieu": {"P3": {"trang_thai": "Một phần", "mau": "bad"}}})
        out = self.overview(today="2026-11-01")
        rows = [b for s in out["trang"]["sections"] if s["id"] == "theo_doi_tuan" for b in s["khoi"]
                if b["kieu"] == "bang" and b["cot"][0] == "#"][0]["dong"]
        p3 = [r for r in rows if r[0]["t"] == "P3"][0]
        self.assertEqual(p3[4]["mau"], "do")
        self.assertEqual(out["live"]["signals"].get("P3"), None)

# ── Page contract ────────────────────────────────────────────────────────────


class PageTests(FixtureCase):
    def test_sections_and_blocks_follow_vnblocks(self):
        out = self.overview()
        secs = out["trang"]["sections"]
        self.assertEqual(out["trang"]["schema"], "vnblocks/1")
        self.assertEqual([s["id"] for s in secs][:4], ["cong", "theo_doi_tuan", "o_so_dau", "keynotes"])
        self.assertEqual(secs[-1]["id"], "nguon")
        for s in secs:
            for k in ("id", "so", "tieu_de", "eyebrow", "lede", "khoi"):
                self.assertIn(k, s)
            for b in s["khoi"]:
                self.assertIn(b["kieu"], BLOCK_KINDS)
                if b["kieu"] == "bang":
                    for r in b["dong"]:
                        self.assertEqual(len(r), len(b["cot"]), (s["id"], b["cot"]))
                if b["kieu"] == "bieu_do":
                    blk = b["block"]
                    for ser in blk["series"]:
                        for key in ("y", "y_lo", "y_hi"):
                            if key in ser:
                                self.assertEqual(len(ser[key]), len(blk["x"]), (b["tieu_de"], ser["name"]))
                    for a in blk["annotations"]:
                        for key in ("x", "x0", "x1"):
                            if key in a:
                                self.assertIsInstance(a[key], int)
                        self.assertIn(a["mau"], {"bull", "bear", "warn", "info", "amber", "cyan", "dim"})

    def test_missing_profile_parts_are_skipped_with_warning(self):
        out = self.overview()
        ids = [s["id"] for s in out["trang"]["sections"]]
        self.assertNotIn("roadshow", ids)
        self.assertTrue(any("roadshow_msr" in w for w in out["meta"]["warnings"]))

    def test_live_block_has_charts_and_log(self):
        out = self.overview()
        tdt = [s for s in out["trang"]["sections"] if s["id"] == "theo_doi_tuan"][0]
        kinds = [b["kieu"] for b in tdt["khoi"]]
        self.assertEqual(kinds.count("bieu_do"), 2)
        tiles = [b for b in tdt["khoi"] if b["kieu"] == "o_so"][0]["o"]
        self.assertTrue(all(t["live"] for t in tiles))
        log = [b for b in tdt["khoi"] if b["kieu"] == "bang" and b["cot"][0] == "Tuần (phiên cuối)"][0]["dong"]
        self.assertIn("đang mở", log[0][0]["t"])
        self.assertTrue(any("hồ sơ" in r[0]["t"] for r in log))

    def test_csv_shape(self):
        csv = self.overview()["csv"]
        self.assertEqual(len(csv["columns"]), 7)
        self.assertTrue(csv["rows"])
        for r in csv["rows"]:
            self.assertEqual(len(r), 7)
            self.assertTrue(all(isinstance(c, str) for c in r))

    def test_stale_flags(self):
        meta = self.overview(today="2026-10-20")["meta"]
        self.assertTrue(meta["stale"])
        self.assertIn("DỮ LIỆU CŨ", meta["stale_text"])
        self.assertIn("HỒ SƠ CŨ", meta["stale_text"])
        fresh = self.overview()["meta"]
        self.assertFalse(fresh["stale"])
        self.assertEqual(fresh["age_days"], 0)
        self.assertEqual(fresh["artifact_url"], "https://claude.ai/artifact/test")


# ── Errors and CLI ───────────────────────────────────────────────────────────


class ErrorTests(FixtureCase):
    def run_main(self, argv, env=None):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, env or self.fx.env()), redirect_stdout(buf):
            code = M.main(argv)
        self.assertEqual(code, 0)
        return json.loads(buf.getvalue())

    def test_no_profile(self):
        os.remove(os.path.join(self.fx.pdir, "ho_so_2026-09-24.json"))
        out = self.run_main(["msn_reflex.py", "overview"])
        self.assertEqual(out["error_code"], "NO_PROFILE")

    def test_bad_profile_schema(self):
        prof = profile()
        prof["schema"] = "khac/1"
        Fixture.write(os.path.join(self.fx.pdir, "ho_so_2026-09-24.json"), prof)
        self.assertEqual(self.run_main(["x", "overview"])["error_code"], "BAD_PROFILE")

    def test_bad_profile_json(self):
        with open(os.path.join(self.fx.pdir, "ho_so_2026-09-24.json"), "w", encoding="utf-8") as fh:
            fh.write("{không phải json")
        self.assertEqual(self.run_main(["x", "overview"])["error_code"], "BAD_PROFILE")

    def test_bad_args(self):
        for argv in (["x"], ["x", "khac"], ["x", "overview", "--den"], ["x", "overview", "--den", "24/09/2026"],
                     ["x", "overview", "--tuan", "2026-09-24"]):
            self.assertEqual(self.run_main(argv)["error_code"], "BAD_ARGS", argv)

    def test_missing_store_is_not_fatal(self):
        os.remove(os.path.join(self.fx.bridge, "vnstore", "vn_store.db"))
        shutil.rmtree(os.path.join(self.fx.bridge, "state"))
        out = self.run_main(["x", "overview"])
        self.assertNotIn("error", out)
        self.assertEqual(out["live"], {})
        self.assertIn(M.CAN, json.dumps(out["trang"], ensure_ascii=False))

    def test_subprocess_emits_one_json_object(self):
        env = dict(os.environ)
        env.update(self.fx.env())
        res = subprocess.run([sys.executable, SCRIPT, "overview"], capture_output=True, env=env, timeout=60)
        self.assertEqual(res.returncode, 0)
        lines = res.stdout.decode("utf-8").strip().split("\n")
        self.assertEqual(len(lines), 1)
        out = json.loads(lines[0])
        self.assertIn("trang", out)
        self.assertNotIn("NaN", lines[0])


# ── Regression against the real local stores (skipped when absent) ───────────


def real_env():
    env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
    return env


def real_ready():
    with mock.patch.dict(os.environ, real_env(), clear=True):
        p = M.paths()
    need = [os.path.join(p["profile_dir"], "ho_so_2026-09-24.json"), p["vnstore"],
            os.path.join(p["vc_lk"], "MSN", "price-history.json")]
    if not all(os.path.isfile(x) for x in need):
        return False
    last = None
    for mode in ("mode=ro", "immutable=1"):      # same fallback as msn_reflex.Kho (WAL without -shm access)
        try:
            con = sqlite3.connect("file:%s?%s" % (p["vnstore"], mode), uri=True)
            last = con.execute("SELECT MAX(ngay) FROM nen_ngay WHERE symbol='MSN'").fetchone()[0]
            con.close()
            break
        except sqlite3.Error:
            continue
    return bool(last) and last >= "2026-09-23"


def annex_layout(base, annexes):
    """Section ids msn_reflex.insert_annexes must produce: annexes oldest first, each block (live chaebol table, then
    the annex's sections, ids made unique like annex_sections) right after the annex's chen_sau anchor (default
    theo_doi_tuan), at the end when the anchor is missing; "nguon" stays last."""
    secs = [i for i in base if i != "nguon"]
    used = set(secs)
    for raw, _path, day in annexes:
        block = []
        if M.as_list(M.as_dict(raw.get("he_sinh_thai")).get("thanh_vien")):
            block.append(M.uniq_id("bo_sung_he_sinh_thai", used, day))
        for i, s in enumerate(M.as_list(raw.get("sections"))):
            if not isinstance(s, dict):
                continue
            sid = re.sub(r"[^a-z0-9_]+", "_", M.nfc(s.get("id")).lower()).strip("_") or "muc_%d" % (i + 1)
            block.append(M.uniq_id(sid if sid.startswith("bo_sung_") else "bo_sung_" + sid, used, day))
        if not block:
            continue
        anchor = M.nfc(raw.get("chen_sau")) or "theo_doi_tuan"
        k = secs.index(anchor) + 1 if anchor in secs else len(secs)
        secs = secs[:k] + block + secs[k:]
    return secs + (["nguon"] if "nguon" in base else [])


@unittest.skipUnless(real_ready(), "real stores / installed profile not present")
class RealStoreRegression(unittest.TestCase):
    """Reproduce the dossier's 23/09/2026 weekly block from the real stores."""

    @classmethod
    def setUpClass(cls):
        with mock.patch.dict(os.environ, real_env(), clear=True):
            cls.out = M.build_overview(date(2026, 9, 23), "ho_so")
        cls.live = cls.out["live"]

    def test_close_and_week(self):
        self.assertEqual(self.live["data_to"], "2026-09-23")
        self.assertEqual(M.k_txt(self.live["close"]), "69,8")
        self.assertEqual(self.live["last_week"]["last"], "2026-09-18")
        self.assertEqual(M.k_txt(self.live["last_week"]["close"]), "68,4")
        self.assertEqual(M.pct_txt(self.live["vs_week_pct"]), "+2,0%")

    def test_volume_ratio(self):
        self.assertAlmostEqual(self.live["kl_ratio"], 1.016, delta=0.002)
        self.assertEqual(M.x_txt(self.live["kl_ratio"]), "1,02×")

    def test_pb_sigma_with_profile_params(self):
        self.assertEqual(M.x_txt(self.live["pb"]), "2,68×")
        self.assertEqual(M.sigma_txt(self.live["sigma"]), "−1,01σ")
        self.assertEqual(M.k_txt(self.live["band_minus1"], 1), "70,3")
        self.assertEqual(M.k_txt(self.live["band_mu"], 1), "112,5")

    def test_msn_look_through(self):
        self.assertAlmostEqual(self.live["ratio"], 0.490, delta=0.001)
        self.assertEqual(M.x_txt(self.live["ratio"]), "0,49×")
        self.assertAlmostEqual(self.live["lt"] / 1e12, 218.56, delta=0.3)
        self.assertAlmostEqual(self.live["ratio_local_shares"], 0.466, delta=0.002)

    def test_x1_week_high(self):
        self.assertEqual(self.live["x1_high"]["last"], "2026-05-08")
        self.assertEqual(M.k_txt(self.live["x1_high"]["close"], 1), "80,2")

    def test_ratio_distribution(self):
        self.assertAlmostEqual(self.live["ratio_median"], 0.67, delta=0.005)
        self.assertGreaterEqual(self.live["ratio_pct_lower"], 95.0)

    def test_session_and_index(self):
        self.assertAlmostEqual(self.live["vnindex"]["close"], 1801.65, places=2)
        self.assertAlmostEqual(self.live["session"]["kl20_year"], 0.682, delta=0.002)

    def test_full_overview_under_budget(self):
        t0 = time.time()
        with mock.patch.dict(os.environ, real_env(), clear=True):
            out = M.build_overview()
        self.assertLess(time.time() - t0, 3.0)
        ids = [s["id"] for s in out["trang"]["sections"]]
        base = [i for i in ids if not i.startswith("bo_sung_")]
        with mock.patch.dict(os.environ, real_env(), clear=True):
            p = M.paths()
            pday = M.load_profile(p["profile_dir"])[2]
            annexes = M.load_bo_sung(p["profile_dir"], pday, None, [])
        self.assertEqual(ids, annex_layout(base, annexes))     # each annex under its own chen_sau anchor
        ids = base
        self.assertEqual(ids, ["cong", "theo_doi_tuan", "o_so_dau", "keynotes", "ba_dong_ho", "phan_1", "phan_2",
                               "roadshow", "du_bao", "phan_3", "case_15", "vung_gia", "phan_4", "hoi_dong",
                               "hanh_dong", "pre_mortem", "rigor_6d", "nguon"])
        charts = [b for s in out["trang"]["sections"] for b in s["khoi"] if b["kieu"] == "bieu_do"]
        self.assertEqual(len(charts), 8)


if __name__ == "__main__":
    unittest.main()
