#!/usr/bin/env python3
"""Unit tests for sgi_fa.py — synthetic fixtures only (no real data, no network).

Run: python3 -m unittest scripts/test_sgi_fa.py -v
"""

from __future__ import annotations

import copy
import io
import json
import math
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sgi_fa as S  # noqa: E402

SCRIPT = os.path.join(HERE, "sgi_fa.py")
M = S.MINUS


# ── Fixtures ─────────────────────────────────────────────────────────────────


def light(mau, text="đèn"):
    return {"text": text, "mau": mau}


def issue_0920():
    """The kỳ 20/09/2026 case: scores 0,0,−2,−1,−1,0,−1,+1; conditions [MỘT PHẦN, CHƯA×3]."""
    scores = [0, 0, -2, -1, -1, 0, -1, 1]
    khoi = [{"id": i + 1, "ten": "Khối %d" % (i + 1), "diem": v, "den": [light("xanh"), light("vang")]}
            for i, v in enumerate(scores)]
    return {
        "schema": "sgi_ky/1", "ky": "2026-09-20", "ky_truoc": "2026-09-12", "ky_sau": "2026-09-27",
        "du_lieu_den": "2026-09-18",
        "verdict": {"che_do": "SIẾT", "tien_mat": {"hien_tai": 15, "de_xuat": 33}, "co_phieu": 61,
                    "san_co_phieu": 50, "dieu_kien_day_ghi": "1/4",
                    "ly_do_tien_mat": ["Độ rộng washout", "Sàn cổ phiếu 50% NAV"]},
        "khoi": khoi,
        "to_hop_truoc": {"TIỀN": -6},
        "dieu_kien_day": [{"id": 1, "trang_thai": "MỘT PHẦN"}, {"id": 2, "trang_thai": "CHƯA"},
                          {"id": 3, "trang_thai": "CHƯA"}, {"id": 4, "trang_thai": "CHƯA"}],
        "chi_so": {"cpi_yoy": {"v": 4.89, "ky": "T8/2026", "tier": "FACT-T1"},
                   "ls_tai_cap_von": {"v": 4.50, "tier": "FACT-T1"},
                   "ls_huy_dong_6_12t_cao": {"v": 9, "tier": "SS-T3"},
                   "us10y": {"v": 4.94, "ky": "2026-09-18", "tier": "FACT-T1"},
                   "vnd_12t_pct": {"v": -2.5, "ky": "14/09/2025 → 18/09/2026",
                                   "ghi_chu": "dương = VND mất giá; chợ đen 26.590 → 25.920"},
                   "do_rong_tren_ma200_pct": {"v": 25.0, "ky": "2026-09-18", "ghi_chu": "116 mã VNDirect"},
                   "vni_ytd_pct": {"v": 1.75, "ky": "2026-09-18"},
                   "trung_vi_ytd_pct": {"v": -11.33, "ky": "2026-09-18"}},
        "neo_hien_tai": {"LDR thuần": {"gia_tri": "~115%", "ky": "Q2/2026", "den": "do", "tier": "SS-T3"},
                         "US10Y": {"gia_tri": "4,94%", "ky": "2026-09-18", "den": "vang", "tier": "FACT-T1"}},
        "nguong_dao_chieu": [
            {"id": "us10y", "ten": "US 10Y < 4,5%", "bien": "us10y", "phep": "<", "muc": 4.5, "live": "us10y"},
            {"id": "vnd", "ten": "VND mất giá > 8%", "phep": ">", "muc": 8, "live": "vnd_12t",
             "keo_dai": "12 tháng"},
            {"id": "cpi", "ten": "CPI < 4,5%", "phep": "<", "muc": 4.5, "live": "cpi_yoy"},
            {"id": "lnh", "ten": "Liên NH 6 tháng < 6%", "phep": "<", "muc": 6.0, "live": None}],
        "danh_muc": {"dong": [{"ma": "VCB", "de_xuat": 40}, {"ma": "FPT", "de_xuat": 21},
                              {"ma": "TIỀN MẶT", "de_xuat": 33}]},
        "tiles": [{"nhan": "Mã trên MA200", "gia_tri": "25,0%"}],
    }


def weekdays(start, n):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def all_days(start, end):
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def monthly(start, end):
    out, y, m = [], start.year, start.month
    while date(y, m, 1) <= end:
        out.append(date(y, m, 1))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def canvas(pairs):
    """[(date, v)] → series-store canvas; epoch = 00:00 Vietnam time."""
    return {"series": [{"t": S.day_ms(d) - 7 * 3600 * 1000, "v": v} for d, v in pairs]}


def build_store():
    us_days = weekdays(date(2022, 1, 3), 1300)
    us_days = [d for d in us_days if d <= date(2026, 9, 21)]
    us10 = [(d, 4.0) for d in us_days]
    us10 = [(d, 4.98 if d == date(2023, 10, 19) else v) for d, v in us10]
    us10[-1] = (us10[-1][0], 4.96)
    fed = [(d, 3.75 if d < date(2026, 9, 17) else 4.0) for d in all_days(date(2022, 1, 1), date(2026, 9, 22))]
    fx_days = weekdays(date(2021, 1, 4), 1500)
    fx_days = [d for d in fx_days if d <= date(2026, 9, 21)]
    fx = [(d, 25000.0 + i) for i, d in enumerate(fx_days)]
    credit = [(d, 15.0) for d in monthly(date(2017, 1, 1), date(2026, 7, 1))]
    deposit = [(d, 12.0) for d in monthly(date(2017, 1, 1), date(2026, 6, 1))]
    reserves = [(d, 80000.0) for d in monthly(date(2017, 1, 1), date(2026, 6, 1))]
    return {"generated_at": "2026-09-23T09:00:00+07:00", "canvases": {
        S.SID_US10Y: canvas(us10), S.SID_US2Y: canvas([(d, 4.76) for d in us_days]),
        S.SID_FED: canvas(fed), S.SID_USDVND: canvas(fx),
        S.SID_VCB_SELL: canvas([(date(2026, 9, 23), 26210.0)]),
        S.SID_CREDIT: canvas(credit), S.SID_DEPOSIT: canvas(deposit), S.SID_FX_RES: canvas(reserves),
        "wc-frac": canvas([(date(2026, 1, 1), 0.14), (date(2026, 2, 1), 0.15)])}}


VIMO = [
    {"chi_tieu": "CPI YoY", "ky": "T8/26", "ngay_iso": "2026-08-01", "gia_tri": 4.888, "ky_truoc": 4.45,
     "don_vi": "%", "nguon": "vietnambiz/macro-economic"},
    {"chi_tieu": "Tín dụng YoY", "ky": "T7/26", "ngay_iso": "2026-07-01", "gia_tri": 17.7, "ky_truoc": 17.4,
     "don_vi": "%", "nguon": "vietnambiz"},
    {"chi_tieu": "Huy động YoY", "ky": "T6/26", "ngay_iso": "2026-06-01", "gia_tri": 10.39, "ky_truoc": 10.76,
     "don_vi": "%", "nguon": "vietnambiz"},
    {"chi_tieu": "LNH qua đêm", "ky": "22/09", "ngay_iso": "2026-09-22", "gia_tri": 4.43, "ky_truoc": 6.84,
     "don_vi": "%", "nguon": "vietnambiz"},
    {"chi_tieu": "Dự trữ ngoại hối", "ky": "T6/26", "ngay_iso": "2026-06-01", "gia_tri": 86318.35,
     "don_vi": "tr USD", "nguon": "vietnambiz"},
]


def build_db(path):
    """24 VN100 symbols × 460 sessions: 12 up, 11 down, 1 with a +50% jump; plus noise symbols."""
    days = weekdays(date(2024, 6, 3), 460)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE ma (symbol TEXT PRIMARY KEY, san TEXT, loai TEXT, ten TEXT, nganh TEXT, "
                "nhom TEXT, theo_doi INTEGER DEFAULT 0, cap_nhat TEXT)")
    con.execute("CREATE TABLE nen_ngay (symbol TEXT, ngay TEXT, mo REAL, cao REAL, thap REAL, dong REAL, "
                "kl REAL, nguon TEXT, PRIMARY KEY (symbol, ngay))")
    rows, ma = [], []

    def add(sym, closes, dates, nhom="VN100,VN200"):
        ma.append((sym, "HOSE", "stock", sym, "", nhom, 0, ""))
        rows.extend((sym, d.isoformat(), c, c, c, c, 1.0, "test") for d, c in zip(dates, closes))

    for k in range(12):
        add("UP%02d" % k, [100 * 1.001 ** i for i in range(460)], days)
    for k in range(11):
        add("DN%02d" % k, [100 * 0.999 ** i for i in range(460)], days)
    add("JMP", [100 * 1.001 ** i * (1.5 if i >= 440 else 1.0) for i in range(460)], days)
    add("SHORT", [100.0] * 300, days[-300:])                       # < 400 sessions → not in universe
    add("OTHER", [100 * 1.001 ** i for i in range(460)], days, nhom="VN200")   # not VN100
    ma.append(("VNINDEX", "HOSE", "index", "VN-Index", "", None, 0, ""))
    rows.extend(("VNINDEX", d.isoformat(), 1000.0, 1000.0, 1000.0, 1000.0, 1.0, "test") for d in days)
    con.executemany("INSERT INTO ma VALUES (?,?,?,?,?,?,?,?)", ma)
    con.executemany("INSERT INTO nen_ngay VALUES (?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return days


class Env(unittest.TestCase):
    """Temp dirs wired through the SGI_* env overrides."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sgi_fa_test_")
        self.issue_dir = os.path.join(self.tmp, "sgi_ky")
        self.bridge = os.path.join(self.tmp, "bridge")
        os.makedirs(self.issue_dir)
        os.makedirs(os.path.join(self.bridge, "data"))
        os.makedirs(os.path.join(self.bridge, "vnstore"))
        self.store = os.path.join(self.tmp, "store.json")
        self.db = os.path.join(self.bridge, "vnstore", "vn_store.db")
        self.env = {"SGI_ISSUE_DIR": self.issue_dir, "SGI_BRIDGE_DIR": self.bridge,
                    "SGI_WIDATA_STORE": self.store, "SGI_VNSTORE_DB": self.db, "SGI_TODAY": "2026-09-23"}
        self.patch = mock.patch.dict(os.environ, self.env)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, path, obj):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False)

    def write_issue(self, issue, name=None):
        self.write(os.path.join(self.issue_dir, (name or issue["ky"]) + ".json"), issue)

    def write_live(self, db=True):
        self.write(self.store, build_store())
        self.write(os.path.join(self.bridge, "data", "wd_vimo_raw.json"), VIMO)
        self.write(os.path.join(self.bridge, "data", "bang_vimo.json"),
                   {"bang": "t", "dong": [{"chi_tieu": "P/E toàn phần", "gia_tri": 12.54, "ghi_chu": "x"}]})
        tp_days = weekdays(date(2021, 1, 4), 1500)
        self.write(os.path.join(self.bridge, "data", "tpcp_vn.json"),
                   {"nhan": "FACT-T2", "du_lieu_moi_nhat": "2026-09-18",
                    "canh_bao": ["Bước nhảy −120bp ngày 22/10/2024 là lỗi khớp đường cong."],
                    "ky_han": {"10Y": [[d.isoformat(), 4.5] for d in tp_days if d <= date(2026, 9, 18)]}})
        if db:
            build_db(self.db)

    def cli(self, *args):
        env = dict(os.environ)
        res = subprocess.run([sys.executable, SCRIPT] + list(args), capture_output=True, env=env, timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        text = res.stdout.decode("utf-8")
        self.assertEqual(text.count("\n"), 1, "exactly one JSON line")
        return json.loads(text)


# ── Formatting ───────────────────────────────────────────────────────────────


class FormatTests(unittest.TestCase):
    def test_design_examples(self):
        self.assertEqual(S.fmt_vn(4.96), "4,96")
        self.assertEqual(S.fmt_vn(-4.5), M + "4,5")
        self.assertEqual(S.fmt_vn(1.5, sign=True), "+1,5")
        self.assertEqual(S.fmt_vn(2700), "2.700")

    def test_zero_trim_fixed_and_missing(self):
        self.assertEqual(S.fmt_vn(0, sign=True), "0")
        self.assertEqual(S.fmt_vn(-0.001, 2, sign=True), "0")
        self.assertEqual(S.fmt_vn(-2.0), M + "2")
        self.assertEqual(S.fmt_vn(1234567.891, 1), "1.234.567,9")
        self.assertEqual(S.fmt_vn(50, 1, fixed=True), "50,0")
        self.assertEqual(S.fmt_vn(None), S.CAN)
        self.assertEqual(S.fmt_vn(float("nan")), S.CAN)
        self.assertEqual(S.fmt_vn(True), S.CAN)
        self.assertEqual(S.pct_txt(27.84), "27,8%")

    def test_dates(self):
        self.assertEqual(S.store_day(S.day_ms(date(2025, 10, 1)) - 7 * 3600 * 1000), date(2025, 10, 1))
        self.assertEqual(S.store_day(S.day_ms(date(2026, 9, 21))), date(2026, 9, 21))   # FRED-style UTC midnight
        self.assertEqual(S.day_ms(date(1970, 1, 2)), 86400000)
        self.assertEqual(S.ky_txt("2026-09-18"), "18/09/2026")
        self.assertEqual(S.ky_txt("T8/2026"), "T8/2026")
        self.assertIsNone(S.parse_day("2026/09/18"))


# ── Engine ───────────────────────────────────────────────────────────────────


def k_of(*scores):
    return {i + 1: v for i, v in enumerate(scores)}


class CompositeTests(unittest.TestCase):
    def test_ky_0920_composites(self):
        e = S.build_engine(issue_0920())
        comp = {c["ten"]: c for c in e["to_hop"]}
        self.assertEqual([c["ten"] for c in e["to_hop"]], ["TIỀN", "CHI PHÍ", "GIÁ TRỊ", "ĐỘ RỘNG", "ĐẦU CƠ"])
        self.assertEqual(comp["TIỀN"]["gia_tri_txt"], M + "2")
        self.assertEqual(comp["TIỀN"]["cong_thuc"], "(0 + 0 %s 1) × 2 = %s2" % (M, M))
        self.assertEqual(comp["TIỀN"]["truoc_txt"], M + "6")
        self.assertEqual(comp["TIỀN"]["delta_txt"], "▲4")
        self.assertEqual(comp["CHI PHÍ"]["gia_tri_txt"], M + "4,5")
        self.assertEqual(comp["GIÁ TRỊ"]["gia_tri_txt"], "0")
        self.assertEqual(comp["GIÁ TRỊ"]["mau"], "xam")
        self.assertEqual(comp["ĐỘ RỘNG"]["gia_tri_txt"], "+1,5")
        self.assertTrue(comp["ĐỘ RỘNG"]["mo_rong"])
        self.assertEqual(comp["ĐẦU CƠ"]["gia_tri_txt"], M + "1")
        self.assertEqual(comp["TIỀN"]["mau"], "do")
        self.assertEqual(comp["ĐỘ RỘNG"]["mau"], "xanh")

    def test_null_member_and_clamp(self):
        k = k_of(0, None, 0, 0, 0, 0, 0, 0)
        c = S.composite(S.TO_HOP[0], k, {})
        self.assertIsNone(c["gia_tri"])
        self.assertEqual(c["gia_tri_txt"], S.CAN)
        self.assertIn("khối 2", c["cong_thuc"])
        c = S.composite(S.TO_HOP[4], k_of(0, 0, 0, 0, 0, 0, 3, 0), {})
        self.assertEqual(c["gia_tri"], 2)
        self.assertIn("chặn", c["cong_thuc"])

    def test_delta_down_and_flat(self):
        c = S.composite(S.TO_HOP[1], k_of(0, 0, -2, -1, 0, 0, 0, 0), {"CHI PHÍ": -3})
        self.assertEqual(c["delta_txt"], "▼1,5")
        c = S.composite(S.TO_HOP[1], k_of(0, 0, -2, 0, 0, 0, 0, 0), {"CHI PHÍ": -3})
        self.assertEqual(c["delta_txt"], "—")


class RegimeTests(unittest.TestCase):
    def day(self, d, can=0):
        return {"dat": d, "can_data": can}

    def check(self, t, v, d, name, row, band):
        r = S.regime(t, v, self.day(d))
        self.assertEqual((r["ten"], r["dong"], r["dai"]), (name, row, band))
        self.assertEqual(r["ghi_chu_bien"], "+4 thuộc dòng 1–2 theo thứ tự bảng")
        return r

    def test_rows(self):
        self.check(4, 0, 3, "MỞ RỘNG", 1, [5, 15])
        self.check(4, -1.5, 0, "HƯNG PHẤN", 2, [20, 35])
        self.check(4, -1.5, 4, "HƯNG PHẤN", 2, [20, 35])
        self.check(-2, 1.5, 3, "TÍCH LŨY", 3, [30, 50])
        r = self.check(-2, 0, 0, "SIẾT", 4, [35, 50])
        self.assertEqual(r["ly_giai"], "TIỀN %s2 < 0 và 0/4 điều kiện đáy ĐẠT < 3/4 → dòng 4 · SIẾT" % M)
        self.check(-2, 3, 2, "SIẾT", 4, [35, 50])
        self.check(0, -3, 0, "CHUYỂN TIẾP", 5, [25, 40])
        self.check(3.99, 3, 4, "CHUYỂN TIẾP", 5, [25, 40])

    def test_gap_up(self):
        r = S.regime(4, 0, self.day(2))
        self.assertEqual(r["ten"], S.NGOAI_BANG)
        self.assertTrue(r["ngoai_bang"])
        self.assertIsNone(r["dai"])
        self.assertIn("dòng 1 cần ≥3/4", r["ly_giai"])

    def test_gap_down(self):
        r = S.regime(-2, 0, self.day(3))
        self.assertEqual(r["ten"], S.NGOAI_BANG)
        self.assertIn("dòng 3 cần GIÁ TRỊ ≥ +1,5", r["ly_giai"])

    def test_null_scores(self):
        self.assertEqual(S.regime(None, 0, self.day(0))["ten"], S.CAN)
        self.assertEqual(S.regime(-2, None, self.day(0))["ten"], S.CAN)

    def test_uncertain_conditions(self):
        # 2 ĐẠT + 1 unknown: row 4 (SIẾT) or row 3 (TÍCH LŨY) → cannot decide
        r = S.regime(-2, 1.5, self.day(2, can=1))
        self.assertEqual(r["ten"], S.CAN)
        # but an unknown that cannot change the row is harmless
        self.assertEqual(S.regime(-2, 0, self.day(0, can=1))["ten"], "SIẾT")


class BottomTests(unittest.TestCase):
    def test_mismatch_text(self):
        d = S.bottom_conditions(issue_0920())
        self.assertEqual((d["dat"], d["mot_phan"], d["chua"], d["can_data"]), (0, 1, 3, 0))
        self.assertEqual(d["txt"], "0/4 ĐẠT · 1 MỘT PHẦN")
        self.assertFalse(d["nhat_quan"])
        self.assertEqual(d["ghi_chu"], "Bản tuần ghi 1/4 nhưng không điều kiện nào ĐẠT — 1 MỘT PHẦN; §5 chỉ đếm ĐẠT")
        self.assertEqual(d["luat"], "Dưới 2/4 — không mua mới bất kể conviction bottom-up")

    def test_match_missing_and_rules(self):
        iss = issue_0920()
        iss["dieu_kien_day"][0]["trang_thai"] = "ĐẠT"
        d = S.bottom_conditions(iss)
        self.assertTrue(d["nhat_quan"])
        iss["dieu_kien_day"] = iss["dieu_kien_day"][:2]
        iss["dieu_kien_day"][1]["trang_thai"] = "[CẦN DATA]"
        d = S.bottom_conditions(iss)
        self.assertEqual(d["can_data"], 3)
        del iss["verdict"]["dieu_kien_day_ghi"]
        self.assertIsNone(S.bottom_conditions(iss)["nhat_quan"])
        self.assertTrue(S.bottom_rule(2).startswith("2/4"))
        self.assertTrue(S.bottom_rule(3).startswith("3/4"))
        self.assertTrue(S.bottom_rule(4).startswith("4/4"))


class OverrideTests(unittest.TestCase):
    def ovr(self, iss, regime="SIẾT"):
        _, by_id = S.block_scores(iss)
        return {o["id"]: o for o in S.overrides(iss, {"ten": regime}, by_id)}

    def test_rule1(self):
        iss = issue_0920()
        self.assertEqual(self.ovr(iss)[1]["trang_thai"], "KÍCH HOẠT")
        self.assertEqual(self.ovr(iss, "CHUYỂN TIẾP")[1]["trang_thai"], "KHÔNG")
        self.assertEqual(self.ovr(iss, S.CAN)[1]["trang_thai"], S.CAN)

    def test_rule2(self):
        iss = issue_0920()
        self.assertEqual(self.ovr(iss)[2]["trang_thai"], "KHÔNG")
        iss["khoi"][0]["den"] = [light("do"), light("đỏ"), light("r"), light("xanh")]
        o = self.ovr(iss)[2]
        self.assertEqual(o["trang_thai"], "KÍCH HOẠT")
        self.assertEqual(o["co_so"], "3 đèn đỏ / 4 đèn khối ①")
        iss["khoi"][0]["den"] = []
        self.assertEqual(self.ovr(iss)[2]["trang_thai"], S.CAN)

    def test_rule3(self):
        iss = issue_0920()
        o = self.ovr(iss)[3]
        self.assertEqual(o["trang_thai"], "KÍCH HOẠT")
        self.assertIn("4,89", o["co_so"])
        iss["chi_so"]["cpi_yoy"]["v"] = 4.5
        self.assertEqual(self.ovr(iss)[3]["trang_thai"], "KHÔNG")
        del iss["chi_so"]["ls_tai_cap_von"]
        self.assertEqual(self.ovr(iss)[3]["trang_thai"], S.CAN)

    def test_rule4_and_5(self):
        iss = issue_0920()
        self.assertEqual(self.ovr(iss)[4]["trang_thai"], "KHÔNG")
        iss["chi_so"]["ls_huy_dong_6_12t_cao"]["v"] = 10.5
        self.assertEqual(self.ovr(iss)[4]["trang_thai"], "KÍCH HOẠT")
        del iss["chi_so"]["ls_huy_dong_6_12t_cao"]
        self.assertEqual(self.ovr(iss)[4]["trang_thai"], S.CAN)
        self.assertEqual(self.ovr(iss)[5]["trang_thai"], "THÔNG TIN")


class CashAuditTests(unittest.TestCase):
    def test_ky_0920_engine(self):
        e = S.build_engine(issue_0920())
        self.assertEqual(e["che_do"]["ten"], "SIẾT")
        self.assertTrue(e["khop"])
        cash = e["tien_mat"]
        self.assertFalse(cash["trong_dai"])
        self.assertEqual(cash["lech_txt"], "dưới biên dưới 2 điểm")
        self.assertEqual(cash["ly_do"], ["Độ rộng washout", "Sàn cổ phiếu 50% NAV"])
        self.assertEqual(cash["min_override"], 30)
        self.assertEqual(cash["max_san"], 50)
        self.assertEqual(cash["txt"], "15% → 33%")
        ovr = {o["id"]: o["trang_thai"] for o in e["override"]}
        self.assertEqual(ovr[3], "KÍCH HOẠT")
        kiem = {k["muc"]: k for k in e["kiem"]}
        self.assertTrue(kiem["Chế độ"]["ok"])
        self.assertFalse(kiem["Điều kiện đáy"]["ok"])
        self.assertFalse(kiem["Tiền mặt · dải chế độ"]["ok"])
        self.assertIn("Độ rộng washout", kiem["Tiền mặt · dải chế độ"]["text"])
        self.assertTrue(kiem["Tiền mặt · override"]["ok"])
        self.assertTrue(kiem["Tiền mặt · sàn cổ phiếu"]["ok"])
        self.assertFalse(kiem["Cổ phiếu"]["ok"])
        self.assertIn("61", kiem["Cổ phiếu"]["text"])
        self.assertIn("67", kiem["Cổ phiếu"]["text"])
        self.assertFalse(kiem["Danh mục"]["ok"])      # 40 + 21 + 33 = 94
        self.assertIn("94", kiem["Danh mục"]["text"])

    def test_bands_and_limits(self):
        ovr = [{"id": 2, "trang_thai": "KHÔNG", "min_tien_mat": None},
               {"id": 4, "trang_thai": "KÍCH HOẠT", "min_tien_mat": 50}]
        cd = {"ten": "SIẾT", "dai": [35, 50], "dai_txt": "35–50%"}
        c = S.cash_audit({"tien_mat": {"de_xuat": 40}}, cd, ovr)
        self.assertTrue(c["trong_dai"])
        self.assertEqual(c["lech_txt"], "trong dải 35–50%")
        self.assertEqual(c["min_override"], 50)
        self.assertEqual(c["ly_do"], [])
        c = S.cash_audit({"tien_mat": {"de_xuat": 55}, "san_co_phieu": 40}, cd, ovr)
        self.assertEqual(c["lech_txt"], "trên biên trên 5 điểm")
        self.assertEqual(c["max_san"], 60)
        ovr[0]["trang_thai"] = "KÍCH HOẠT"
        self.assertIsNone(S.cash_audit({"tien_mat": {"de_xuat": 55}}, cd, ovr)["max_san"])
        c = S.cash_audit({"tien_mat": {"de_xuat": 40}}, {"ten": S.NGOAI_BANG, "dai": None}, ovr)
        self.assertIsNone(c["trong_dai"])
        c = S.cash_audit({}, cd, ovr)
        self.assertIsNone(c["de_xuat"])
        self.assertEqual(c["txt"], "%s → %s" % (S.CAN, S.CAN))

    def test_override_and_floor_violations(self):
        iss = issue_0920()
        iss["verdict"]["tien_mat"]["de_xuat"] = 25
        iss["verdict"]["san_co_phieu"] = 80
        kiem = {k["muc"]: k for k in S.build_engine(iss)["kiem"]}
        self.assertFalse(kiem["Tiền mặt · override"]["ok"])
        self.assertFalse(kiem["Tiền mặt · sàn cổ phiếu"]["ok"])

    def test_portfolio_without_cash_row(self):
        iss = issue_0920()
        iss["danh_muc"]["dong"] = [{"ma": "VCB", "de_xuat": 40}, {"ma": "FPT", "de_xuat": 27},
                                   {"ma": "X", "de_xuat": "≤3"}]
        pc = S.portfolio_check(iss, 33)
        self.assertTrue(pc["ok"])
        self.assertIn("cộng tiền mặt", pc["text"])
        self.assertIn("1 dòng", pc["text"])

    def test_regime_mismatch_and_bad_score(self):
        iss = issue_0920()
        iss["verdict"]["che_do"] = "TÍCH LŨY"
        iss["khoi"][2]["diem"] = -3
        e = S.build_engine(iss)
        self.assertFalse(e["khop"])
        kiem = {k["muc"]: k for k in e["kiem"]}
        self.assertFalse(kiem["Chế độ"]["ok"])
        self.assertFalse(kiem["Khối 3"]["ok"])


class GateTests(unittest.TestCase):
    def gate(self, t, c):
        eng = {"to_hop": [{"ten": "TIỀN", "gia_tri": t}, {"ten": "CHI PHÍ", "gia_tri": c}],
               "che_do": {"ten": "SIẾT"}}
        return S.build_gate(eng, {"ky": "2026-09-20"})

    def test_gate(self):
        g = S.build_gate(S.build_engine(issue_0920()), issue_0920())
        self.assertEqual(g["text"], "CỔNG: tiền đắt · chủ thể không áp dụng (khung vĩ mô) · playbook SIẾT")
        self.assertEqual(g["co_so"], "TIỀN %s2 · CHI PHÍ %s4,5 (bản tuần 20/09)" % (M, M))
        self.assertEqual(self.gate(2, 1.5)["gia_tien"], "tiền rẻ")
        self.assertEqual(self.gate(2, -1.5)["gia_tien"], "chưa kết luận (TIỀN và CHI PHÍ ngược chiều)")
        self.assertEqual(self.gate(None, -1.5)["gia_tien"], S.CAN)
        self.assertEqual(S.build_gate(None, {})["playbook"], S.CAN)


# ── Live layer ───────────────────────────────────────────────────────────────


class LiveTests(Env):
    def live(self):
        self.write_live()
        lv = S.Live(S.paths(), [])
        self.addCleanup(lv.close)
        return lv

    def test_fraction_series_scaled(self):
        lv = self.live()
        self.assertEqual([round(v, 6) for _, v in lv.series("wc-frac", pct=True)], [14.0, 15.0])
        self.assertEqual(lv.series("wc-frac")[0][1], 0.14)

    def test_thresholds_live(self):
        lv = self.live()
        rows = {r["id"]: r for r in S.build_thresholds(lv, issue_0920())}
        self.assertEqual(rows["us10y"]["live_v"], 4.96)
        self.assertEqual(rows["us10y"]["live_trang_thai"], "CHƯA")
        self.assertEqual(rows["us10y"]["live_txt"], "4,96% (21/09)")
        self.assertEqual(rows["cpi"]["live_trang_thai"], "CHƯA")
        self.assertEqual(rows["cpi"]["live_txt"], "4,89% (T8/2026)")
        self.assertIn("không phải chợ đen", rows["vnd"]["live_ghi_chu"])
        self.assertNotIn("12 tháng", rows["vnd"]["live_ghi_chu"])     # horizon of the metric, not a duration
        self.assertGreater(rows["vnd"]["live_v"], 0)
        self.assertNotIn("live_v", rows["lnh"])
        iss = issue_0920()
        iss["nguong_dao_chieu"][0]["muc"] = 5.0
        rows = {r["id"]: r for r in S.build_thresholds(lv, iss)}
        self.assertEqual(rows["us10y"]["live_trang_thai"], "CHẠM")

    def test_anchors_merge(self):
        lv = self.live()
        neo = {r["chi_bao"]: r for r in S.build_anchors(lv, issue_0920())}
        self.assertEqual(len(neo), len(S.NEO) + len(S.NEO_NGOAI))
        self.assertEqual(neo["LDR thuần"]["nguon_hien_tai"], "bản tuần")
        self.assertEqual(neo["US10Y"]["hien_tai"], "4,94%")
        self.assertEqual(neo["US10Y"]["ky"], "18/09/2026")
        self.assertTrue(neo["US10Y"]["live_hien_tai"].startswith("4,96%"))
        self.assertEqual(neo["LS qua đêm liên NH"]["nguon_hien_tai"], "live")
        self.assertEqual(neo["LS qua đêm liên NH"]["den"], "vang")
        self.assertEqual(neo["US2Y − Fed funds"]["hien_tai"], "+0,76 điểm %")
        self.assertEqual(neo["US2Y − Fed funds"]["den"], "do")
        self.assertEqual(neo["DXY"]["hien_tai"], S.CAN)
        self.assertEqual(neo["DXY"]["nguon_hien_tai"], "")

    def test_tiles(self):
        lv = self.live()
        tiles = {t["nhan"]: t for t in S.build_tiles(lv, issue_0920())}
        self.assertEqual(tiles["US 10Y"]["gia_tri"], "4,96%")
        self.assertEqual(tiles["US 10Y"]["ky"], "21/09/2026")
        self.assertIn("bản tuần 4,94% (18/09/2026)", tiles["US 10Y"]["ghi_chu"])
        self.assertEqual(tiles["US 10Y"]["mau"], "vang")          # below the 2023 peak, above 4,5
        self.assertIn("+25bp", tiles["Fed funds (trần)"]["ghi_chu"])
        self.assertEqual(tiles["CPI YoY"]["mau"], "do")
        self.assertIn("không so được", tiles["Huy động YoY"]["ghi_chu"])
        # a YoY across the NHNN break is not the published number → it cannot keep FACT-T2
        self.assertEqual(tiles["Huy động YoY"]["tier"], "UNVERIFIED")
        self.assertEqual(tiles["Tín dụng YoY"]["tier"], "FACT-T2")
        self.assertIn("bản tuần 12T theo chợ đen %s2,5%%" % M, tiles["USD/VND (MSN)"]["ghi_chu"])
        self.assertIn("không phải chợ đen", tiles["USD/VND (MSN)"]["ghi_chu"])
        self.assertEqual(tiles["Dự trữ ngoại hối"]["gia_tri"], "86,3 tỷ USD")
        self.assertEqual(tiles["P/E toàn phần"]["tier"], "EST")

    def test_credit_chart_break(self):
        lv = self.live()
        warns = []
        c = S.chart_credit(lv, warns)
        b = c["block"]
        xs = b["x"]
        ser = {s["name"]: s for s in b["series"]}
        dep, band = ser["Huy động YoY"]["y"], ser["Khe tín dụng − huy động"]
        for x, v, lo in zip(xs, dep, band["y_lo"]):
            if x >= "2025-10-01":
                self.assertIsNone(v)
                self.assertIsNone(lo)
            else:
                self.assertEqual(v, 12.0)
                self.assertEqual(lo, 12.0)
        self.assertEqual(xs[0], "2018-01-01")
        vl = [a for a in b["annotations"] if a["kind"] == "vline"][0]
        self.assertEqual(vl["x"], S.day_ms(date(2025, 10, 1)))
        self.assertIn("không so được", vl["tip"])
        self.assertTrue(warns)

    def test_rates_chart_contract(self):
        lv = self.live()
        c = S.chart_rates(lv)
        b = c["block"]
        self.assertEqual(b["x"][-1], "2026-09-21")
        pt = [a for a in b["annotations"] if a["kind"] == "point"][0]
        self.assertEqual(pt["x"], S.day_ms(date(2026, 9, 21)))
        self.assertIsInstance(pt["x"], int)
        vl = [a for a in b["annotations"] if a["kind"] == "vline"][0]
        self.assertEqual(vl["x"], S.day_ms(date(2026, 9, 17)))
        self.assertEqual(vl["text"], "Fed +25bp")
        hb = [a for a in b["annotations"] if a["kind"] == "hband"][0]
        self.assertEqual((hb["y0"], hb["y1"], hb["mau"]), (0, 4.5, "bull"))
        self.assertTrue(all(len(s["y"]) == len(b["x"]) for s in b["series"]))

    def test_breadth_tiny_sqlite(self):
        lv = self.live()
        dr, hist, ew = S.build_breadth(lv, issue_0920())
        self.assertEqual(dr["universe"], "VN100 · 24 mã ≥400 phiên")
        self.assertEqual(dr["loai_bo"], 1)
        self.assertEqual(dr["n"], 23)
        self.assertEqual(dr["n_ma200"], 23)
        self.assertEqual(dr["n_ma50"], 23)
        self.assertAlmostEqual(dr["tren_ma200"], 12 * 100 / 23)
        self.assertEqual(dr["tren_ma200_txt"], "52,2%")
        self.assertEqual(dr["vni_ytd_txt"], "0,0%")
        self.assertEqual(dr["danh_bai_250_txt"], "52,2%")
        days = weekdays(date(2024, 6, 3), 460)
        base = max(i for i, d in enumerate(days) if d.year == 2025)
        up_ytd = (1.001 ** (459 - base) - 1) * 100
        self.assertTrue(dr["trung_vi_ytd_txt"].startswith("+"))
        self.assertAlmostEqual(float(dr["trung_vi_ytd_txt"][1:-1].replace(",", ".")), round(up_ytd, 1))
        bt = dr["ban_tuan"]
        self.assertEqual((bt["tren_ma200"], bt["universe"], bt["ky"]), ("25,0%", "116 mã VNDirect", "18/09/2026"))
        self.assertEqual((bt["vni_ytd"], bt["trung_vi_ytd"]), ("+1,75%", M + "11,33%"))
        self.assertNotIn("danh_bai_250", bt)
        iss = issue_0920()
        del iss["chi_so"]["do_rong_tren_ma200_pct"]
        self.assertEqual(S.issue_breadth(iss)["tren_ma200"], "25,0%")        # tile fallback
        self.assertIsNone(S.issue_breadth({"chi_so": {}}))
        self.assertEqual(hist["x"][-1], days[-1])
        self.assertAlmostEqual(hist[200][-1], dr["tren_ma200"])
        self.assertEqual(len(ew["x"]), 253)
        self.assertEqual(ew["vni"][-1], 100.0)
        exp = 100.0 * (1 + (12 * 0.001 - 11 * 0.001) / 23) ** 252
        self.assertAlmostEqual(ew["deu"][-1], exp, places=6)
        c = S.chart_breadth(hist, dr)
        self.assertEqual(c["id"], "do_rong")
        kinds = [a["kind"] for a in c["block"]["annotations"]]
        self.assertEqual(kinds.count("hband"), 2)

    def test_washout_episodes(self):
        xs = [date(2026, 1, 5) + timedelta(weeks=i) for i in range(14)]
        ys = [40, 25, 20, 35, 22, 40, 40, 40, 40, 40, 28, 40, None, 10]
        lows = S.washout_lows(xs, ys, gap=2)
        self.assertEqual([v for _, v in lows], [20, 10])       # 28 → 10 separated by only 2 points
        self.assertEqual([v for _, v in S.washout_lows(xs, ys, gap=1)], [20, 28, 10])


class IntegrationFixTests(Env):
    """Checks added while wiring the real kỳ 20/09 issue (live vs issue, audit lines)."""

    def live(self):
        self.write_live()
        lv = S.Live(S.paths(), [])
        self.addCleanup(lv.close)
        return lv

    def test_vimo_ky_and_vn_numbers(self):
        self.assertEqual(S.vimo_ky({"ngay_iso": "2026-09-22", "tan_suat": "ngay", "ky": "22/09"}), "22/09/2026")
        self.assertEqual(S.vimo_ky({"ngay_iso": "2026-08-01", "tan_suat": "thang"}), "T8/2026")
        self.assertEqual(S.vimo_ky({"ngay_iso": "2026-04-01", "tan_suat": "quy"}), "Q2/2026")
        self.assertEqual(S.vimo_ky({"ky": "T8/26"}), "T8/26")
        self.assertEqual(S.vn_numbers("-1.28σ · RẺ (<−1σ)"), M + "1,28σ · RẺ (<−1σ)")
        self.assertEqual(S.vn_numbers("ex-Vin 1.65"), "ex-Vin 1,65")

    def test_fred_vs_issue(self):
        pts = [(date(2026, 9, 16), 5.01), (date(2026, 9, 17), 4.94), (date(2026, 9, 18), 5.01)]
        iss = {"chi_so": {"us10y": {"v": 4.94, "ky": "2026-09-18"}}}
        note = S.fred_vs_issue(pts, iss, "us10y", "US10Y")
        self.assertIn("FRED US10Y ngày 18/09: 5,01%", note)
        self.assertIn("lệch %s7 bp" % M, note)
        self.assertIn("4,94% là số FRED ngày 17/09", note)
        iss["chi_so"]["us10y"]["v"] = 5.01
        self.assertEqual(S.fred_vs_issue(pts, iss, "us10y", "US10Y"), "")
        self.assertEqual(S.fred_vs_issue(pts, {}, "us10y", "US10Y"), "")

    def test_us10y_above_2023_peak_flagged(self):
        store = build_store()
        pts = store["canvases"][S.SID_US10Y]["series"]
        pts[-2]["v"] = 5.01                                      # one close above the 4,98 peak
        self.write_live()
        self.write(self.store, store)
        warns = []
        lv = S.Live(S.paths(), warns)
        self.addCleanup(lv.close)
        tiles = {t["nhan"]: t for t in S.build_tiles(lv, issue_0920())}
        self.assertIn("đóng cửa trên đỉnh 2023 1 phiên", tiles["US 10Y"]["ghi_chu"])
        self.assertEqual(tiles["US 10Y"]["mau"], "vang")         # the latest close is back below the peak
        self.assertTrue(any("vượt đỉnh 2023" in w for w in warns))

    def test_fed_vline_uses_issue_decision_day(self):
        lv = self.live()
        iss = issue_0920()
        iss["chi_so"]["fed_tren"] = {"v": 4.0, "ky": "2026-09-16", "tier": "FACT-T1"}
        vl = [a for a in S.chart_rates(lv, iss)["block"]["annotations"] if a["kind"] == "vline"][0]
        self.assertEqual(vl["x"], S.day_ms(date(2026, 9, 16)))
        self.assertIn("hiệu lực 17/09/2026", vl["tip"])
        iss["chi_so"]["fed_tren"]["ky"] = "2026-08-01"          # too far from the FRED date → FRED date
        vl = [a for a in S.chart_rates(lv, iss)["block"]["annotations"] if a["kind"] == "vline"][0]
        self.assertEqual(vl["x"], S.day_ms(date(2026, 9, 17)))

    def test_vni_cross_check(self):
        a = [(date(2026, 9, 22), 1816.93), (date(2026, 9, 23), 1801.65)]
        self.assertIn("lệch", S.vni_cross_check(a, [(date(2026, 9, 23), 1819.88)]))
        self.assertEqual(S.vni_cross_check(a, [(date(2026, 9, 22), 1816.93)]), "")
        self.assertEqual(S.vni_cross_check(a, []), "")

    def test_ew_gap_in_points(self):
        lv = self.live()
        dr, _, ew = S.build_breadth(lv, issue_0920())
        self.assertTrue(dr["deu_vs_vni_12t_txt"].endswith(" đpt"))
        self.assertIn("đpt", S.chart_ew(ew)["block"]["annotations"][0]["text"])

    def test_override_2_audit_line(self):
        iss = issue_0920()
        iss["khoi"][0]["den"] = [light("do"), light("do"), light("do"), light("xanh")]
        kiem = {k["muc"]: k for k in S.build_engine(iss)["kiem"]}
        line = kiem["Override #2"]
        self.assertFalse(line["ok"])
        self.assertIn("3 đèn đỏ / 4 đèn", line["text"])
        self.assertIn("khối ① vẫn chấm 0", line["text"])
        self.assertIn("viện dẫn sàn cổ phiếu", line["text"])
        self.assertIn("không nhắc", line["text"])
        iss["verdict"]["ghi_chu"] = "Áp Hard Rule 7."
        kiem = {k["muc"]: k for k in S.build_engine(iss)["kiem"]}
        self.assertNotIn("không nhắc", kiem["Override #2"]["text"])
        self.assertNotIn("Override #2", {k["muc"] for k in S.build_engine(issue_0920())["kiem"]})

    def test_portfolio_gap_explained(self):
        iss = issue_0920()
        iss["verdict"]["co_phieu"] = 61
        for r, cur in zip(iss["danh_muc"]["dong"], (40, 21, 33)):
            r["hien_tai"] = cur
        text = S.portfolio_check(iss, 33)["text"]
        self.assertIn("các dòng cổ phiếu cộng 61% = cổ phiếu bản tuần ghi", text)
        self.assertIn("cột hiện tại cũng cộng 94%", text)
        # issue v7 prints that column as "Kỳ trước" (danh_muc.cot) — the audit must use the printed name
        iss["danh_muc"]["cot"] = ["Mã", "Kỳ trước", "Trục vĩ mô chi phối", "Hành động", "Đề xuất"]
        self.assertIn("cột kỳ trước cũng cộng 94%", S.portfolio_check(iss, 33)["text"])

    def test_printed_composites_checked(self):
        iss = issue_0920()
        self.assertNotIn("Tổ hợp in", {k["muc"] for k in S.build_engine(iss)["kiem"]})  # older issues print none
        iss["to_hop"] = [{"ten": "TIỀN", "gia_tri": -2}, {"ten": "CHI PHÍ", "gia_tri": -4.5}]
        kiem = {k["muc"]: k for k in S.build_engine(iss)["kiem"]}
        self.assertTrue(kiem["Tổ hợp in"]["ok"])
        iss["to_hop"][0]["gia_tri"] = -6
        kiem = {k["muc"]: k for k in S.build_engine(iss)["kiem"]}
        self.assertFalse(kiem["Tổ hợp in"]["ok"])
        self.assertIn("TIỀN in −6, engine −2", kiem["Tổ hợp in"]["text"])


# ── Overview + CLI ───────────────────────────────────────────────────────────


class OverviewTests(Env):
    def test_full_overview(self):
        self.write_live()
        self.write_issue(issue_0920())
        out = S.build_overview(None)
        self.assertEqual(out["meta"]["issues"], ["2026-09-20"])
        self.assertEqual(out["meta"]["age_days"], 3)
        self.assertFalse(out["meta"]["stale"])
        self.assertIsNone(out["meta"]["issue_error"])
        self.assertEqual(out["engine"]["che_do"]["ten"], "SIẾT")
        self.assertEqual(out["gate"]["playbook"], "SIẾT")
        ids = [c["id"] for c in out["charts"]]
        self.assertEqual(ids, ["my_lai_suat", "tpcp_vn_my", "tin_dung_huy_dong", "ty_gia", "du_tru", "do_rong",
                               "vni_vs_deu"])
        self.assertEqual(out["csv"]["columns"], S.CSV_COLUMNS)
        self.assertTrue(all(len(r) == 7 for r in out["csv"]["rows"]))
        json.dumps(S.clean(out), allow_nan=False)

    def test_no_issue_is_not_fatal(self):
        self.write_live(db=False)
        out = S.build_overview(None)
        self.assertIsNone(out["issue"])
        self.assertIsNone(out["engine"])
        self.assertEqual(out["meta"]["issue_error"]["error_code"], "NO_ISSUE")
        self.assertEqual(out["gate"]["gia_tien"], S.CAN)
        self.assertIsNone(out["live"]["do_rong"])
        self.assertTrue(any("do_rong" in w for w in out["meta"]["warnings"]))
        self.assertTrue(out["live"]["tiles"])

    def test_missing_live_sources(self):
        self.write_issue(issue_0920())
        out = S.build_overview(None)
        self.assertEqual(out["charts"], [])
        self.assertTrue(all(not s["ok"] for s in out["meta"]["sources_live"]))
        self.assertEqual(out["engine"]["che_do"]["ten"], "SIẾT")

    def test_bad_issue(self):
        with open(os.path.join(self.issue_dir, "2026-09-20.json"), "w") as fh:
            fh.write("{not json")
        out = S.build_overview(None)
        self.assertEqual(out["meta"]["issue_error"]["error_code"], "BAD_ISSUE")
        iss = issue_0920()
        iss["schema"] = "sgi_ky/0"
        self.write_issue(iss)
        self.assertEqual(S.build_overview("2026-09-20")["meta"]["issue_error"]["error_code"], "BAD_ISSUE")
        self.assertEqual(S.build_overview("2026-09-13")["meta"]["issue_error"]["error_code"], "NO_ISSUE")

    def test_staleness(self):
        iss = issue_0920()
        self.write_issue(iss)
        with mock.patch.dict(os.environ, {"SGI_TODAY": "2026-10-02"}):
            m = S.build_overview(None)["meta"]
        self.assertTrue(m["stale"])
        self.assertEqual(m["stale_text"], "BẢN TUẦN CŨ 12 ngày — kỳ 27/09 chưa có")
        iss["ky_sau"] = "2026-09-22"
        self.write_issue(iss)
        with mock.patch.dict(os.environ, {"SGI_TODAY": "2026-09-26"}):
            self.assertTrue(S.build_overview(None)["meta"]["stale"])
        with mock.patch.dict(os.environ, {"SGI_TODAY": "2026-09-25"}):
            self.assertFalse(S.build_overview(None)["meta"]["stale"])

    def test_issue_selection_order(self):
        a, b = issue_0920(), issue_0920()
        b["ky"] = "2026-09-13"
        self.write_issue(a)
        self.write_issue(b)
        with open(os.path.join(self.issue_dir, "notes.json"), "w") as fh:
            fh.write("{}")
        self.assertEqual(S.list_issues(self.issue_dir), ["2026-09-20", "2026-09-13"])
        self.assertEqual(S.build_overview("2026-09-13")["meta"]["ky"], "2026-09-13")


class CliTests(Env):
    def test_bad_args(self):
        for args in ([], ["frobnicate"], ["overview", "20/09/2026"], ["overview", "2026-13-40"],
                     ["overview", "2026-09-20", "x"], ["issues", "x"]):
            out = self.cli(*args)
            self.assertEqual(out["error_code"], "BAD_ARGS", args)
            self.assertIn("sgi_fa.py", out["error"])

    def test_issues_command(self):
        self.write_issue(issue_0920())
        out = self.cli("issues")
        self.assertEqual(out["issues"], ["2026-09-20"])

    def test_overview_cli_no_issue(self):
        out = self.cli("overview")
        self.assertIsNone(out["issue"])
        self.assertEqual(out["meta"]["issue_error"]["error_code"], "NO_ISSUE")

    def test_nan_becomes_null(self):
        iss = issue_0920()
        self.write_issue(iss)
        path = os.path.join(self.issue_dir, "2026-09-20.json")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace('"co_phieu": 61', '"co_phieu": NaN')
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        out = self.cli("overview")
        self.assertIsNone(out["issue"]["verdict"]["co_phieu"])

    def test_internal_envelope(self):
        buf = io.BytesIO()
        fake = mock.Mock()
        fake.buffer = buf
        with mock.patch.object(S, "run", side_effect=RuntimeError("boom")), mock.patch.object(S.sys, "stdout", fake):
            self.assertEqual(S.main(["sgi_fa.py", "overview"]), 0)
        out = json.loads(buf.getvalue().decode("utf-8"))
        self.assertEqual(out["error_code"], "INTERNAL")
        self.assertIn("boom", out["error"])


class CleanTests(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(S.clean({"a": [float("nan"), 1.0, {"b": float("inf")}]}), {"a": [None, 1.0, {"b": None}]})
        self.assertTrue(math.isfinite(S.clean(2.5)))

    def test_issue_fixture_is_not_mutated(self):
        iss = issue_0920()
        before = copy.deepcopy(iss)
        S.build_engine(iss)
        self.assertEqual(iss, before)


class ReviewFixTests(Env):
    """Regressions found by the adversarial engine/live-data review."""

    def live_with(self, store, vimo=None):
        self.write_live(db=not os.path.exists(self.db))
        self.write(self.store, store)
        if vimo is not None:
            self.write(os.path.join(self.bridge, "data", "wd_vimo_raw.json"), vimo)
        warns = []
        lv = S.Live(S.paths(), warns)
        self.addCleanup(lv.close)
        return lv, warns

    def test_intraday_vni_print_is_not_a_close(self):
        # The real store was written 09:28 on 23/09: its 23/09 VN-Index is a session print, not the close.
        days = weekdays(date(2024, 6, 3), 460)
        last = days[-1]
        for stamp, flagged in (("%sT09:28:18.500000+07:00" % last.isoformat(), False),
                               ("%sT16:00:00+07:00" % last.isoformat(), True)):
            store = build_store()
            store["generated_at"] = stamp
            store["canvases"][S.SID_VNI] = canvas([(days[-2], 1000.0), (last, 1010.0)])
            lv, warns = self.live_with(store)
            S.build_breadth(lv, issue_0920())
            self.assertEqual(any("VN-Index" in w and "lệch" in w for w in warns), flagged, stamp)
        self.assertEqual(S.parse_stamp("2026-09-23T02:28:00Z").hour, 9)
        self.assertIsNone(S.parse_stamp("hôm nay"))

    def test_deposit_yoy_comparable_again_after_break_year(self):
        store = build_store()
        store["canvases"][S.SID_CREDIT] = canvas([(d, 15.0) for d in monthly(date(2017, 1, 1), date(2026, 11, 1))])
        store["canvases"][S.SID_DEPOSIT] = canvas([(d, 12.0) for d in monthly(date(2017, 1, 1), date(2026, 11, 1))])
        vimo = [dict(r) for r in VIMO]
        dep = next(r for r in vimo if r["chi_tieu"] == "Huy động YoY")
        dep["ngay_iso"] = "2026-11-01"
        lv, warns = self.live_with(store, vimo)
        b = S.chart_credit(lv, warns)["block"]
        ser = {s["name"]: s for s in b["series"]}
        y = dict(zip(b["x"], ser["Huy động YoY"]["y"]))
        lo = dict(zip(b["x"], ser["Khe tín dụng − huy động"]["y_lo"]))
        self.assertEqual(y["2025-09-01"], 12.0)
        for x in ("2025-10-01", "2026-03-01", "2026-09-01"):
            self.assertIsNone(y[x])
            self.assertIsNone(lo[x])
        self.assertEqual((y["2026-10-01"], y["2026-11-01"]), (12.0, 12.0))
        self.assertEqual(lo["2026-11-01"], 12.0)
        pt = [a for a in b["annotations"] if a["kind"] == "point" and a["text"].startswith("Huy động")][0]
        self.assertNotIn("trước gãy", pt["sub"])
        tiles = {t["nhan"]: t for t in S.build_tiles(lv, issue_0920())}
        self.assertNotIn("không so được", tiles["Huy động YoY"]["ghi_chu"])
        self.assertEqual(tiles["Huy động YoY"]["tier"], "FACT-T2")
        self.assertTrue(S.deposit_straddles(date(2026, 9, 1)))
        self.assertFalse(S.deposit_straddles(date(2026, 10, 1)))

    def test_vnd_12_month_horizon_is_not_a_duration(self):
        self.write_live()
        lv = S.Live(S.paths(), [])
        self.addCleanup(lv.close)
        iss = issue_0920()
        iss["nguong_dao_chieu"][0]["keo_dai"] = "2 tuần liên tiếp"
        rows = {r["id"]: r for r in S.build_thresholds(lv, iss)}
        self.assertNotIn("chưa kiểm độ dài", rows["vnd"]["live_ghi_chu"])
        self.assertIn("chưa kiểm độ dài \"2 tuần liên tiếp\"", rows["us10y"]["live_ghi_chu"])

    def test_reserves_unit_is_read_not_assumed(self):
        self.assertAlmostEqual(S.usd_bn(86318.35, "tr USD"), 86.31835)
        self.assertEqual(S.usd_bn(86.3, "tỷ USD"), 86.3)
        self.assertAlmostEqual(S.usd_bn(86318.35, ""), 86.31835)    # documented default: USD mn
        self.assertIsNone(S.usd_bn(86318.35, "tỷ đồng"))
        vimo = [dict(r) for r in VIMO]
        res = next(r for r in vimo if r["chi_tieu"] == "Dự trữ ngoại hối")
        res.update({"gia_tri": 86.3, "don_vi": "tỷ USD"})
        store = build_store()
        store["canvases"][S.SID_FX_RES]["unit"] = "tỷ USD"
        lv, warns = self.live_with(store, vimo)
        tiles = {t["nhan"]: t for t in S.build_tiles(lv, issue_0920())}
        self.assertEqual(tiles["Dự trữ ngoại hối"]["gia_tri"], "86,3 tỷ USD")
        self.assertEqual(S.chart_reserves(lv, warns)["block"]["series"][0]["y"][-1], 80000.0)
        res["don_vi"] = "USD"
        store["canvases"][S.SID_FX_RES]["unit"] = "nghìn USD"
        lv, warns = self.live_with(store, vimo)
        self.assertNotIn("Dự trữ ngoại hối", {t["nhan"] for t in S.build_tiles(lv, issue_0920())})
        self.assertIsNone(S.chart_reserves(lv, warns))
        self.assertEqual(sum("đơn vị" in w for w in warns), 2)

    def test_fed_tile_names_effective_date(self):
        self.write_live()
        lv = S.Live(S.paths(), [])
        self.addCleanup(lv.close)
        tiles = {t["nhan"]: t for t in S.build_tiles(lv, issue_0920())}
        self.assertIn("+25bp, hiệu lực 17/09/2026 (FRED)", tiles["Fed funds (trần)"]["ghi_chu"])



# ── §5.4 LTT ─────────────────────────────────────────────────────────────────


def multi_canvas(lines):
    """{name: [(date, v)]} → series-store canvas with series_multi (epoch = 00:00 Vietnam time)."""
    return {"series_multi": [{"name": n, "series": canvas(pts)["series"]} for n, pts in lines.items()]}


def ltt_store(posted=None, on=None, w2=None, refi=None, trade=None):
    """build_store() plus the WiChart lines §5.4 reads. Defaults: posted 13M peaked in March then flat,
    interbank easing (last 20 sessions under the 60-session mean), refinancing flat, August deficit."""
    st = build_store()
    days = weekdays(date(2026, 6, 1), 85)
    days = [d for d in days if d <= date(2026, 9, 22)]
    ease = [(d, 6.0 if i < len(days) - 20 else 3.0) for i, d in enumerate(days)]
    months = monthly(date(2025, 10, 1), date(2026, 9, 1))
    posted = posted or [(d, 6.29 if d == date(2026, 3, 1) else (5.91 if d > date(2026, 3, 1) else 5.4))
                        for d in months]
    c = st["canvases"]
    c[S.SID_LSHUY] = multi_canvas({"1-3 tháng - NHTM Lớn - MBB, ACB, T": [(d, 4.19) for d in months],
                                   "13 tháng - NHTM Lớn - MBB, ACB, TC": posted})
    c[S.SID_LNH] = multi_canvas({"LS qua đêm liên ngân hàng": on or ease,
                                 "LS liên ngân hàng kỳ hạn 2 tuần": w2 or ease})
    c[S.SID_LSDH] = multi_canvas({"Lãi suất tái cấp vốn": refi or [(d, 4.5) for d in months]})
    c[S.SID_TRADE] = multi_canvas({"Cán cân thương mại": trade or [(date(2026, 5, 1), -5333.0),
                                                                   (date(2026, 8, 1), -113.0)]})
    return st


def issue_ltt(ky, top, avgs="T7 8,23% · T8 7,94% · T9 8,05%", foreign=-2594):
    iss = issue_0920()
    iss["ky"] = ky
    iss["chi_so"]["ls_huy_dong_6_12t_cao"] = {"v": top, "tier": "NEWS"}
    iss["chi_so"]["lnh_6t_bq_thang"] = {"v": 8.05, "ky": "T9/2026", "ghi_chu": "bình quân tháng: " + avgs}
    iss["chi_so"]["khoi_ngoai_tuan_ty"] = {"v": foreign, "ky": "21–24/09/2026"}
    return iss


class LttTests(Env):
    def test_no_new_high(self):
        self.assertEqual(S.no_new_high([5.0]), (S.CAN, None))
        self.assertEqual(S.no_new_high([9.0, 9.35]), ("CHƯA", 9.35))
        self.assertEqual(S.no_new_high([9.35, 9.0]), (S.CAN, 9.35))          # 1 reading under: not yet 2
        self.assertEqual(S.no_new_high([5.0, 6.0, 5.5]), ("CHƯA", 6.0))      # the previous one set the high
        self.assertEqual(S.no_new_high([6.0, 5.5, 5.5]), ("ĐẠT", 6.0))
        self.assertEqual(S.no_new_high([5.0, 6.0, 6.0, 6.0]), ("ĐẠT", 6.0))  # flat at the top = stopped
        old_peak = [9.0] + [5.0] * 13 + [5.5, 5.5]                            # a high 15 readings back is out
        self.assertEqual(S.no_new_high(old_peak), ("CHƯA", 5.5))

    def test_month_avgs_and_combiners(self):
        cs = {"v": 8.05, "ky": "T9/2026", "ghi_chu": "T7 8,23% · T8 7,94% · T9 8,05%"}
        self.assertEqual(S.month_avgs(cs), [(7, 8.23), (8, 7.94), (9, 8.05)])
        self.assertEqual(S.month_avgs({"v": 8.0, "ky": "T9/2026", "ghi_chu": "T8 7,9%"}), [(8, 7.9), (9, 8.0)])
        self.assertEqual(S.month_avgs({}), [])
        self.assertEqual(S.combine_all(["ĐẠT", "CHƯA"]), "CHƯA")
        self.assertEqual(S.combine_all(["ĐẠT", S.CAN]), S.CAN)
        self.assertEqual(S.combine_some(["ĐẠT", "ĐẠT", "CHƯA"]), "MỘT PHẦN")
        self.assertEqual(S.combine_some([S.CAN, "CHƯA"]), "CHƯA")

    def test_ky_0926_reading(self):
        """Posted rates flat since March but the market top still climbs → T1 CHƯA; short end eases, 6M not."""
        self.write_live()
        self.write(self.store, ltt_store())
        self.write_issue(issue_ltt("2026-09-20", 9.0))
        self.write_issue(issue_ltt("2026-09-26", 9.35))
        with mock.patch.dict(os.environ, {"SGI_TODAY": "2026-09-27"}):
            out = S.build_overview(None)
        ltt = out["ltt"]
        st = {x["ma"]: x["trang_thai"] for x in ltt["tin_hieu"]}
        self.assertEqual(st, {"T1": "CHƯA", "T2": "MỘT PHẦN", "T3": "CHƯA", "T4": "CHƯA"})
        self.assertFalse(ltt["bat"])
        self.assertEqual(ltt["trang_thai"], "MỘT PHẦN")
        self.assertIn("biểu ưu đãi", " ".join(ltt["tin_hieu"][0]["chi_tiet"]))
        self.assertIn("chưa tăng lãi suất điều hành", ltt["cua_so"])
        card = out["nguong"][-1]
        self.assertEqual((card["id"], card["nguon_hang"]), ("ltt", "engine"))
        self.assertTrue(card["nhom"].startswith("MÁY ĐO"))
        self.assertEqual(card["hien_tai"], "T1 CHƯA · T2 MỘT PHẦN · T3 CHƯA · T4 CHƯA")
        self.assertIn("TB20 3% / TB60", card["live_txt"])
        tile = out["live"]["tiles"][0]
        self.assertEqual((tile["nhan"], tile["gia_tri"], tile["mau"]), ("LTT §5.4 (giả thuyết)", "CHƯA BẬT", "vang"))
        rows = [r for r in out["csv"]["rows"] if r[1].startswith("Lãi suất thôi tăng")]
        self.assertEqual(rows[0][5], "EST — engine §5.4")
        self.assertEqual(out["engine"]["che_do"]["ten"], "SIẾT")     # §7 untouched
        json.dumps(S.clean(out), allow_nan=False)

    def test_turns_on_and_never_moves_section_7(self):
        self.write_live()
        self.write(self.store, ltt_store())
        for ky, top in (("2026-09-06", 9.35), ("2026-09-13", 9.2), ("2026-09-20", 9.2)):
            self.write_issue(issue_ltt(ky, top, avgs="T8 8,23% · T9 7,94%", foreign=1200))
        with_ltt = S.build_overview(None)
        self.assertTrue(with_ltt["ltt"]["bat"])
        self.assertEqual(with_ltt["ltt"]["xac_nhan"], 1)
        self.assertEqual(with_ltt["live"]["tiles"][0]["gia_tri"], "BẬT")
        self.assertIn("≤3% NAV", with_ltt["ltt"]["ket"])
        eng = S.build_engine(issue_ltt("2026-09-20", 9.2))
        self.assertEqual(with_ltt["engine"], json.loads(json.dumps(eng)))

    def test_trade_surplus_confirms_both(self):
        self.write_live()
        self.write(self.store, ltt_store(trade=[(date(2026, 5, 1), -5333.0), (date(2026, 8, 1), 1250.0)]))
        self.write_issue(issue_ltt("2026-09-20", 9.0, foreign=1200))
        ltt = S.build_overview(None)["ltt"]
        t3 = ltt["tin_hieu"][2]
        self.assertEqual(t3["trang_thai"], "ĐẠT")
        self.assertEqual(t3["chi_tiet"], ["cán cân T8/2026 +1,25 tỷ USD; 6 tháng qua thấp nhất −5,33 tỷ (T5)"])
        self.assertEqual(ltt["xac_nhan"], 2)
        self.assertIn("2/2", ltt["ket"])
        self.assertFalse(ltt["bat"])                                     # confirmations alone never turn it on

    def test_partial_month_and_older_issue(self):
        """The running month is not a reading; viewing an older issue ignores later issues."""
        months = monthly(date(2025, 10, 1), date(2026, 9, 1))
        posted = [(d, 5.0) for d in months[:-1]] + [(date(2026, 8, 31), 5.0), (date(2026, 9, 2), 6.0)]
        self.write_live()
        self.write(self.store, ltt_store(posted=posted))
        self.write_issue(issue_ltt("2026-09-13", 9.0))
        self.write_issue(issue_ltt("2026-09-20", 9.5))
        out = S.build_overview("2026-09-13")
        t1 = out["ltt"]["tin_hieu"][0]
        self.assertIn("(T8/2026)", t1["chi_tiet"][0])                  # September skipped (SGI_TODAY 23/09)
        self.assertIn("9% (13/09) — [CẦN DATA]", t1["chi_tiet"][1])    # 20/09 is later than the issue shown

    def test_missing_lines_and_window_texts(self):
        self.write_issue(issue_ltt("2026-09-20", 9.0))
        out = S.build_overview(None)                                     # no store at all
        self.assertTrue(all(x["trang_thai"] in (S.CAN, "CHƯA") for x in out["ltt"]["tin_hieu"]))
        self.assertIn("wc-lsdh", out["ltt"]["cua_so"])
        self.assertNotIn("live_txt", out["nguong"][-1])
        months = monthly(date(2025, 10, 1), date(2026, 9, 1))
        hike = [(d, 4.5 if d < date(2026, 6, 1) else 5.0) for d in months]
        cut = [(d, 4.5 if d < date(2026, 6, 1) else 4.0) for d in months]
        for refi, needle in ((hike, "lần tăng tái cấp vốn gần nhất 01/06/2026 (+50 bp)"),
                             (cut, "đã có lần giảm tái cấp vốn 01/06/2026 (−50 bp)")):
            self.write(self.store, ltt_store(refi=refi))
            lv = S.Live(S.paths(), [])
            self.addCleanup(lv.close)
            self.assertIn(needle, S.ltt_window(lv))


if __name__ == "__main__":
    unittest.main()
