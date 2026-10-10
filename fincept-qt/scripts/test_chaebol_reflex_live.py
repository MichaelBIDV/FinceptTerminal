#!/usr/bin/env python3
"""Unit tests for chaebol_reflex_live.py: synthetic stores written to a temp dir (no network), plus a smoke run on
the real local stores that is skipped when they are absent.

Run: python3 -m pytest -q test_chaebol_reflex_live.py   (add -s to see the real-store numbers)

Synthetic universes (prices in đồng, constant within a week where the test needs exact weekly closes):
  A  parent PAR (100.000 flat, 1 tỷ cp) with child CON whose price makes PAR ÷ LT exactly R(d): 4,0 before 25/09/2023,
     then a ramp 1,0 → 3,0, and 2,0 on the last (open-week) session; CNP has a stake but no prices; CDT carries a
     dated schedule with a pending row; GRC is held by CON (chain + holdco layer CON → GRC).
  B  parent PBB and child CBB with zigzag swings (CBB: 100 → 60 → 120 → 72, PBB: 200 → 130 → 240), a VN-Index
     trough at week 105, and a leader / follower pair LDA / LDB (LDB = LDA two weeks later) in a parent-null group.
  C  store traps: SPL with RAW ≠ ADJUSTED (2:1 split 03/03/2025, cash dividend 2.000 đ 01/06/2026: raw 80.000 →
     40.000 → 38.000, adjusted 38.000 flat), Vietcap's adjusted column on another basis (45.600), its nen starting
     02/01/2024 (a day missing from Vietcap) and ending 5 sessions before Vietcap; STL with nen and Vietcap both
     ending 5 sessions early (largest cap of a parent-null group); CMO listed 02/06/2025 inside the window; NVC
     with vnstore rows only (no Vietcap file); NNP whose Vietcap flow rows stop on a Wednesday.
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chaebol_reflex_live as L  # noqa: E402
import msn_reflex as M  # noqa: E402

ENV_KEYS = ("MSN_REFLEX_DIR", "MSN_BRIDGE_DIR", "MSN_VNSTORE_DB", "MSN_KOS_DIR", "MSN_WIDATA_STORE", "MSN_TODAY",
            "CHAEBOL_REFLEX_DIR")
START = date(2019, 1, 7)            # Monday, week 0
DATA_TO = date(2026, 9, 24)         # Thursday → the week of Friday 25/09 is open
LAST_FRI = date(2026, 9, 18)
RAMP_FROM = date(2023, 9, 25)
# Independent of chaebol_reflex_khung's guard and deliberately wider: order, rating, sizing and target-price words.
STANCE = re.compile(
    r"\b(?:MUA|BÁN|NAV|GIỮ|BUY|SELL|HOLD|ADD|AVOID|REDUCE|ACCUMULATE|OUTPERFORM|UNDERPERFORM|NEUTRAL|OVERWEIGHT|"
    r"UNDERWEIGHT|Buy|Sell|Hold|Add|Avoid|Reduce|Accumulate|Outperform|Underperform)\b"
    r"|\b[MOU]\s?-?\s?PF\b|\bTP\s*[:=]?\s*[−+-]?\s*\d"
    r"|(?i:tỷ\s+trọng|giá\s+mục\s+tiêu|target\s+price|price\s+target|(?<!phải )(?<!phải là )khuyến\s+nghị|khả\s+quan)"
    r"|(?:xuống|lên|hạ|nâng|duy trì|sang)\s+(?:mức\s+)?\W?(?:Mua|Bán|Giữ|Nắm giữ|Trung lập)\b"
    r"|\b(?:Mua|Bán|Giữ|Trung lập)\W{0,2}\s*\(\s*TP")
SPLIT_DAY = date(2025, 3, 3)        # 2:1 split (Monday)
DIV_DAY = date(2026, 6, 1)          # cash dividend 2.000 đ (Monday)
SPL_ADJ = 38000.0                   # SPL's true adjusted close (current basis): flat
SPL_VC_ADJ = 45600.0                # Vietcap's closePriceAdjusted for SPL: same moves, another basis (× 1,2)
SPL_NEN_FIRST = date(2024, 1, 2)    # first vnstore row of SPL; Vietcap has no row that day
LIST_DAY = date(2025, 6, 2)         # CMO's first session
NNP_VC_LAST = date(2026, 9, 16)     # Wednesday of the last complete week


def weekdays(start, end):
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


DAYS = weekdays(START, DATA_TO)
EARLY_LAST = DAYS[-6]               # 5 sessions before DATA_TO


def wk(d):
    return (M.friday(d) - M.friday(START)).days // 7


def monday(k):
    return START + timedelta(days=7 * k)


def fri(k):
    return M.friday(START) + timedelta(days=7 * k)


# ── universe A ──


def ratio_a(d):
    """Target PAR ÷ LT on day d."""
    if d == DATA_TO:
        return 2.0
    if d < RAMP_FROM:
        return 4.0
    return 1.0 + 2.0 * (d - RAMP_FROM).days / (DATA_TO - RAMP_FROM).days


def a_close(sym, d):
    if sym == "PAR":
        return 100000.0
    if sym == "CON":
        return 2e5 / ratio_a(d)          # P mcap 1e14 / (0.5 × 1e9 × p) = 2e5 / p
    if sym == "CDT":
        return 20000.0
    if sym == "GRC":
        return 10000.0
    return 1000.0                        # VNINDEX


def a_vol(sym, d):
    if sym == "PAR" and M.friday(d) == LAST_FRI:
        return 3e6
    return 1e6


# ── universe B ──


def cb_k(k):
    if k < 100:
        return 100.0
    if k < 110:
        return 100.0 - 4.0 * (k - 99)
    if k < 130:
        return 60.0 + 3.0 * (k - 109)
    if k < 150:
        return 120.0 - 2.4 * (k - 129)
    return 72.0


def pb_k(k):
    if k < 100:
        return 200.0
    if k < 110:
        return 200.0 - 7.0 * (k - 99)
    if k < 130:
        return 130.0 + 5.5 * (k - 109)
    return 240.0


def vni_k(k):
    if k < 100:
        return 1000.0
    if k < 106:
        return 1000.0 - 400.0 / 6 * (k - 99)
    if k < 116:
        return 600.0 + 40.0 * (k - 105)
    return 1000.0


RNG = random.Random(11)
LAG_R = [RNG.gauss(0.0, 0.03) for _ in range(wk(DATA_TO) + 3)]


def lag_level(k, shift):
    return 100.0 * math.exp(sum(LAG_R[j - shift] for j in range(k + 1) if j - shift >= 0))


LAG_CACHE = {}


def b_close(sym, d):
    k = wk(d)
    if sym == "CBB":
        return cb_k(k) * 1000.0
    if sym == "PBB":
        return pb_k(k) * 1000.0
    if sym in ("LDA", "LDB"):
        key = (sym, k)
        if key not in LAG_CACHE:
            LAG_CACHE[key] = lag_level(k, 0 if sym == "LDA" else 2) * 1000.0
        return LAG_CACHE[key]
    return vni_k(k)


SHARES = {"PAR": 1e9, "CON": 1e9, "CDT": 1e9, "GRC": 1e9, "PBB": 1e9, "CBB": 1e9, "LDA": 1e10, "LDB": 1e9,
          "SPL": 1e9, "STL": 5e9, "CMO": 1e9, "NVC": 1e9, "NNP": 1e9}


# ── universe C (store traps) ──


def spl_raw(d):
    return 80000.0 if d < SPLIT_DAY else (40000.0 if d < DIV_DAY else 38000.0)


def spl_shares(d):
    return 5e8 if d < SPLIT_DAY else 1e9


def c_vc_rows(sym):
    """Vietcap rows (day, raw close, adjusted close, totalShares, foreign net value) of universe C."""
    if sym == "SPL":
        return [(d, spl_raw(d), SPL_VC_ADJ, spl_shares(d), 0.0) for d in DAYS if d != SPL_NEN_FIRST]
    if sym == "STL":
        return [(d, 10000.0, 10000.0, 5e9, 0.0) for d in DAYS if d <= EARLY_LAST]
    if sym == "CMO":
        return [(d, 10000.0, 10000.0, 1e9, 0.0) for d in DAYS if d >= LIST_DAY]
    if sym == "NNP":
        return [(d, 10000.0, 10000.0, 1e9, 1e9) for d in DAYS if d <= NNP_VC_LAST]
    return []


def c_nen_rows(sym):
    """vnstore rows (day, close) of universe C (adjusted history; the DATA_TO row is a raw board row)."""
    if sym == "SPL":
        return [(d, SPL_ADJ) for d in DAYS if SPL_NEN_FIRST <= d <= EARLY_LAST]
    if sym == "STL":
        return [(d, 10000.0) for d in DAYS if d <= EARLY_LAST]
    if sym == "CMO":
        return [(d, 10000.0) for d in DAYS if d >= LIST_DAY]
    return [(d, 10000.0) for d in DAYS]                      # NVC, NNP


def stake(tu, ty_le, **kw):
    r = {"tu": tu, "ty_le": ty_le, "loai": "phap_ly", "tier": "FACT-T2", "nguon": "kiểm thử"}
    r.update(kw)
    return r


def registry():
    return {"schema": L.SCHEMA_REG, "lap_luc": "2026-10-10", "nhom": [
        {"id": "nhom_a", "ten": "Nhóm A", "me": "PAR", "truc": "NQ68", "he_sinh_thai": ["HeA"],
         "thanh_vien": [
             {"ma": "PAR", "vai_tro": "mẹ"},
             {"ma": "CON", "vai_tro": "con", "me": "PAR", "trong_lt": True, "so_huu": [stake("2018-12-31", 0.5)]},
             {"ma": "CNP", "vai_tro": "con", "me": "PAR", "trong_lt": True, "so_huu": [stake("2018-12-31", 0.3)]},
             {"ma": "CDT", "vai_tro": "con", "me": "PAR", "trong_lt": False, "so_huu": [
                 stake("2026-06-30", 0.75), stake("2025-01-01", 0.78),
                 stake("2026-09-01", 0.80, ap_dung=False, nguon="CBTT chờ"),
                 stake("2024-01-01", 71.7)]},
             {"ma": "GRC", "vai_tro": "cháu", "me": "CON", "trong_lt": False, "so_huu": [stake("2018-12-31", 0.6)]},
             {"ma": None, "ten": "Công ty chưa niêm yết", "vai_tro": "con", "niem_yet": "chưa"}],
         "tang": [{"me": "CON", "con": ["GRC"]}]},
        {"id": "nhom_a2", "ten": "Nhóm A2", "me": "PAR", "thanh_vien": [
            {"ma": "CON", "me": "PAR", "trong_lt": True, "so_huu": [stake("2018-12-31", 0.5)]},
            {"ma": "CDT", "me": "PAR", "trong_lt": True, "so_huu": [
                stake("2026-06-30", 0.75), stake("2025-01-01", 0.78), stake("2026-09-01", 0.80, ap_dung=False)]}]},
        {"id": "nhom_a", "ten": "trùng id"},
        {"id": "Bad Id", "ten": "id sai"},
        {"id": "nhom_b", "ten": "Nhóm B", "me": "PBB", "thanh_vien": [
            {"ma": "CBB", "me": "PBB", "trong_lt": True, "so_huu": [stake("2018-12-31", 0.5)]},
            {"ma": "LDA", "vai_tro": "liên quan"}]},
        {"id": "nhom_lag", "ten": "Rổ không mẹ", "me": None, "thanh_vien": [
            {"ma": "LDB", "vai_tro": "thành viên"}, {"ma": "LDA", "vai_tro": "thành viên"}]},
        {"id": "nhom_spl", "ten": "Nhóm SPL", "me": "PAR", "thanh_vien": [
            {"ma": "SPL", "vai_tro": "con", "me": "PAR", "trong_lt": True, "so_huu": [stake("2018-12-31", 0.4)]}]},
        {"id": "nhom_truc", "ten": "Rổ trục", "me": None, "thanh_vien": [
            {"ma": "STL", "vai_tro": "thành viên"}, {"ma": "SPL", "vai_tro": "thành viên"},
            {"ma": "CDT", "vai_tro": "thành viên"}]},
        {"id": "nhom_niem_yet", "ten": "Nhóm niêm yết giữa chuỗi", "me": "PAR", "thanh_vien": [
            {"ma": "CON", "me": "PAR", "trong_lt": True, "so_huu": [stake("2018-12-31", 0.5)]},
            {"ma": "CMO", "me": "PAR", "trong_lt": True, "so_huu": [stake(LIST_DAY.isoformat(), 0.5)]}]},
        {"id": "nhom_nvc", "ten": "Nhóm NVC", "me": "PAR", "thanh_vien": [
            {"ma": "NVC", "me": "PAR", "trong_lt": True, "so_huu": [stake("2018-12-31", 0.5)]}]},
    ]}


def dossier_a():
    return {"schema": "chaebol_ho_so/1", "nhom": "nhom_a", "tin_hieu": [
        {"id": "X1", "bien": "me_dong_tuan", "phep": ">", "muc": 90, "nhom_tin_hieu": "xac_nhan", "ngay": "2026-09-20"},
        {"id": "X2", "bien": "kl_tuan_tb20", "phep": ">=", "muc": 1.5, "nhom_tin_hieu": "xac_nhan"},
        {"id": "X3", "bien": "me_lt", "phep": ">", "muc": 3.5, "nhom_tin_hieu": "xac_nhan"},
        {"id": "P1", "bien": "me_dong_tuan", "phep": "<", "muc": 95000, "nhom_tin_hieu": "phu_dinh"},
        {"id": "P2", "bien": "dong_tuan:CON", "phep": "<", "muc": 1000000, "nhom_tin_hieu": "phu_dinh"},
        {"id": "X4", "bien": "pb_sigma:PAR", "phep": ">=", "muc": 1, "nhom_tin_hieu": "xac_nhan"},
        {"id": "X5", "bien": "pb_sigma:CON", "phep": "<", "muc": -1, "nhom_tin_hieu": "xac_nhan"},
        {"id": "N1", "mo_ta": "không có biến", "nguong_text": "> 2", "ngay": "2026-09-10"},
        {"id": "N2", "bien": "bien_la", "phep": ">", "muc": 1}]}


class Fixture:
    """A throw-away SYS tree for both universes; env() points msn_reflex / chaebol_reflex_live at it."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="chaebol_live_test_")
        self.kos = os.path.join(self.root, "knowledge_os")
        self.bridge = os.path.join(self.root, "fincept_bridge")
        self.reg = os.path.join(self.root, "reg")
        self.vc = os.path.join(self.bridge, "state", "vc_lk")
        os.makedirs(os.path.join(self.bridge, "vnstore"))
        self.write(os.path.join(self.reg, "nhom.json"), registry())
        self.build_db()
        for s in ("PAR", "CON", "CDT", "GRC"):
            self.write_vc(s, a_close)
        for s in ("PBB", "CBB", "LDA", "LDB"):
            self.write_vc(s, b_close)
        for s in ("SPL", "STL", "CMO", "NNP"):
            self.write_vc_rows(s, c_vc_rows(s))
        self.write(os.path.join(self.vc, "CMO", "details.json"), {"du_lieu": {
            "organCode": "CMOCODE", "viOrganName": "Công ty CMO", "listingDate": LIST_DAY.isoformat() + "T00:00:00"}})
        self.write(os.path.join(self.vc, "PAR", "details.json"), {"du_lieu": {
            "organCode": "PCODE", "viOrganName": "Công ty P", "listingDate": "2010-01-01T00:00:00"}})
        self.write(os.path.join(self.vc, "CON", "shareholder.json"), {"du_lieu": [
            {"ownerCode": "PCODE", "ownerName": "Công ty P", "percentage": 0.48, "publicDate": "2026-06-30"},
            {"ownerCode": "PCODE", "ownerName": "Công ty P", "percentage": 0.40, "publicDate": "2026-09-21"},
            {"ownerCode": "OTHER", "ownerName": "Quỹ X", "percentage": 0.05, "publicDate": "2026-06-30"}]})
        self.write(os.path.join(self.vc, "PAR", "relationship.json"), {"du_lieu": {
            "subsidiaries": [{"rightTicker": "CON", "ownedPercentage": 0.5, "rightOrganNameVi": "CON JSC"}],
            "affiliates": []}})
        q = [(2024, 3, "2024-10-28", 70.0), (2024, 4, "2025-01-28", 75.0), (2025, 1, "2025-04-28", 80.0),
             (2025, 2, "2025-07-28", 100.0), (2025, 3, "2025-10-28", 90.0), (2025, 4, "2026-01-28", 110.0),
             (2026, 1, "2026-04-28", 120.0), (2026, 2, "2026-07-28", 150.0)]
        self.write(os.path.join(self.vc, "PAR", "fs-income.json"), {"du_lieu": {"years": [], "quarters": [
            {"yearReport": y, "lengthReport": n, "publicDate": d + "T00:00:00", "isa22": v} for y, n, d, v in q]}})
        frs = [d for d in DAYS if d.weekday() == 4]
        self.write(os.path.join(self.kos, "hhp_vn100_valuation.json"), {
            "meta": {"generated": "2026-09-24 16:46 ICT", "stale_fields": []},
            "by_ticker": {
                "PAR": {"fa_rec": "BÁN", "fa_tp": 1, "pb": {"mean": 4.0, "sd": 1.0, "per_share": 20000, "reliable": True,
                                                          "sigma": 1.0, "ratio_date": "2026-09-23", "n": 500}},
                "CON": {"pb": {"mean": 1.0, "sd": 1.0, "per_share": 50000, "reliable": False}},
                "CDT": {"pb": {"mean": None, "sd": None}, "pe": {"mean": 10.0, "sd": 2.0, "per_share": 2000}}}})
        self.write(os.path.join(self.kos, "hhp_vn100_series", "PAR.json"), {"pb": {
            "price": [[M.day_ms(d), 100.0] for d in frs], "base": [[M.day_ms(d), 20.0] for d in frs],
            "mean": 4.0, "sd": 1.0}})
        self.widata = os.path.join(self.root, "widata.json")
        self.write(self.widata, {"canvases": {"wc-vnindex": {"series": [{"t": M.day_ms(date(2018, 6, 1)), "v": 900.0}]}}})
        self.write(os.path.join(self.bridge, "data", "chaebol_ecosystems.json"), {
            "as_of": "2026-09-23 10:04 ICT", "ecosystems": {"HeA": {"members": {
                "CON": {"top_shareholders": [{"ownerName": "Công ty P", "percentage": 50.0, "publicDate": "2026-06-30"}]},
                "PAR": {"subsidiaries": [{"ticker": "CON", "ownedPct": 50.0, "name": "CON JSC"}]}}}}})

    @staticmethod
    def write(path, obj):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False)

    def write_vc(self, sym, fn):
        self.write_vc_rows(sym, [(d, fn(sym, d), fn(sym, d), SHARES[sym], 1e9 if sym == "PAR" else 0.0)
                                 for d in DAYS])

    def write_vc_rows(self, sym, rows):
        cot = ["tradingDate", "closePrice", "closePriceAdjusted", "totalMatchVolume", "foreignNetValueTotal",
               "totalShares", "marketCap"]
        hang = [[d.isoformat(), c, ca, 1e6, nn, sh, c * sh] for d, c, ca, sh, nn in rows]
        self.write(os.path.join(self.vc, sym, "price-history.json"),
                   {"meta": {"lay_luc": "2026-09-24T18:00:00+07:00"}, "du_lieu": {"cot": cot, "hang": hang}})

    def build_db(self):
        con = sqlite3.connect(os.path.join(self.bridge, "vnstore", "vn_store.db"))
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
            src = "vci_board" if d == DATA_TO else "vci_history"
            for s in ("PAR", "CON", "CDT", "GRC"):
                rows.append((s, d.isoformat(), a_close(s, d), a_vol(s, d), src))
            for s in ("PBB", "CBB", "LDA", "LDB"):
                rows.append((s, d.isoformat(), b_close(s, d), 1e6, src))
            rows.append(("VNINDEX", d.isoformat(), b_close("VNINDEX", d), 5e8, src))
        for s in ("SPL", "STL", "CMO", "NVC", "NNP"):
            for d, c in c_nen_rows(s):
                rows.append((s, d.isoformat(), c, 1e6, "vci_board" if d == DATA_TO else "vci_history"))
        con.executemany("INSERT INTO nen_ngay VALUES (?, ?, NULL, NULL, NULL, ?, ?, ?)", rows)
        con.executemany("INSERT INTO free_float VALUES (?, 0, 0, ?, 'vci_overview', '2026-09-21', '{}')",
                        list(SHARES.items()))
        con.executemany("INSERT INTO ma VALUES (?, 'HOSE', 'stock', '', '', '', 1, '')", [(s,) for s in SHARES])
        con.commit()
        con.close()

    def env(self):
        return {"MSN_BRIDGE_DIR": self.bridge, "MSN_KOS_DIR": self.kos, "MSN_WIDATA_STORE": self.widata,
                "MSN_TODAY": "2026-09-24", "CHAEBOL_REFLEX_DIR": self.reg}

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


def expected_pct(vals, cur):
    below = sum(1 for v in vals if v < cur)
    eq = sum(1 for v in vals if v == cur)
    return 100.0 * (below + 0.5 * eq) / len(vals)


class FixtureCase(unittest.TestCase):
    """Builds the universes once; tests only read."""

    @classmethod
    def setUpClass(cls):
        cls.fx = Fixture()
        with mock.patch.dict(os.environ, cls.fx.env()):
            cls.reg, cls.reg_warn = L.load_registry()
            cls.wa = []
            cls.a = L.build_live("nhom_a", dossier=dossier_a(), warnings=cls.wa)
            cls.ja = cls.a.to_json()
            cls.wa2 = []
            cls.a2 = L.build_live("nhom_a2", warnings=cls.wa2)
            cls.wb = []
            cls.b = L.build_live("nhom_b", warnings=cls.wb)
            cls.jb = cls.b.to_json()
            cls.lag = L.build_live("nhom_lag")
            cls.jlag = cls.lag.to_json()
            cls.wspl = []
            cls.spl = L.build_live("nhom_spl", warnings=cls.wspl)
            cls.jspl = cls.spl.to_json()
            cls.wtruc = []
            cls.truc = L.build_live("nhom_truc", warnings=cls.wtruc)
            cls.wny = []
            cls.ny = L.build_live("nhom_niem_yet", warnings=cls.wny)
            cls.wnvc = []
            cls.nvc = L.build_live("nhom_nvc", warnings=cls.wnvc)

    @classmethod
    def tearDownClass(cls):
        cls.fx.close()


# ── registry ─────────────────────────────────────────────────────────────────


class RegistryTests(FixtureCase):
    def test_load_validates_groups_and_rows(self):
        self.assertEqual([g.id for g in self.reg.groups()], ["nhom_a", "nhom_a2", "nhom_b", "nhom_lag", "nhom_spl",
                                                             "nhom_truc", "nhom_niem_yet", "nhom_nvc"])
        joined = " | ".join(self.reg_warn)
        self.assertIn("nhom_a ghi hai lần", joined)
        self.assertIn("Bad Id", joined)
        self.assertIn("bỏ dòng sở hữu của CDT", joined)          # ty_le 71.7 is not guessed as a percent
        self.assertIsNone(L.nhom("khong_co", self.reg))
        self.assertEqual(L.nhom_of_ma("grc", self.reg), ["nhom_a"])
        self.assertEqual(self.reg.nhom_of_ma("CON"), ["nhom_a", "nhom_a2", "nhom_niem_yet"])
        self.assertEqual(self.reg.nhom_of_ma("LDA"), ["nhom_b", "nhom_lag"])

    def test_missing_registry_is_an_empty_registry_with_a_warning(self):
        reg, w = L.load_registry(os.path.join(self.fx.root, "khong_co"))
        self.assertEqual(reg.groups(), [])
        self.assertTrue(w and "Chưa có registry" in w[0])

    def test_dated_stake_schedule_with_pending_row(self):
        nh = self.reg.nhom("nhom_a")
        self.assertEqual(nh.weight("CDT", date(2024, 12, 31)), 0.0)          # before the first row
        self.assertEqual(nh.weight("CDT", date(2025, 1, 1)), 0.78)
        self.assertEqual(nh.weight("CDT", date(2026, 6, 29)), 0.78)
        self.assertEqual(nh.weight("CDT", date(2026, 7, 1)), 0.75)
        self.assertEqual(nh.weight("CDT", date(2026, 9, 15)), 0.75)          # pending 0,80 never applied
        self.assertEqual([r["ty_le"] for r in nh.pending("CDT")], [0.80])
        self.assertIsNone(nh.weight("ZZZ", date(2026, 1, 1)))
        w, row = nh.weight_row("CDT", date(2026, 7, 1))
        self.assertEqual(row["tu"], "2026-06-30")
        self.assertEqual(nh.weight("CDT", date(2026, 7, 1), "hieu_dung"), None)

    def test_same_day_rows_keep_file_order_newest_first(self):
        w = []
        nh = L.Nhom({"id": "x", "me": "PAR", "thanh_vien": [{"ma": "CON", "so_huu": [
            stake("2026-01-01", 0.6), stake("2026-01-01", 0.5)]}]}, w)
        self.assertEqual(nh.weight("CON", date(2026, 2, 1)), 0.6)


# ── look-through and ratio ───────────────────────────────────────────────────


class LookThroughTests(FixtureCase):
    def test_member_without_prices_is_listed_but_left_out(self):
        tv = {m["ma"]: m for m in self.ja["thanh_vien"] if m["ma"]}
        self.assertFalse(tv["CNP"]["co_gia"])
        self.assertFalse(tv["CNP"]["trong_lt_dung"])
        self.assertTrue(tv["CNP"]["ly_do_loai"])
        self.assertTrue(any("CNP không tính vào look-through" in w for w in self.wa))
        self.assertEqual([p["ma"] for p in self.ja["lt"]["phan"]], ["CON"])
        unlisted = [m for m in self.ja["thanh_vien"] if m["ma"] is None]
        self.assertEqual(unlisted[0]["ten"], "Công ty chưa niêm yết")

    def test_current_ratio_and_lt(self):
        ts = self.ja["ty_so"]
        self.assertAlmostEqual(ts["hien_tai"], 2.0, places=9)
        self.assertAlmostEqual(self.ja["lt"]["gia_tri"], 0.5 * 1e9 * 1e5, delta=1)
        self.assertEqual(ts["txt"]["hien_tai"], "2,00×")
        self.assertEqual(self.ja["data_to"], DATA_TO.isoformat())

    def test_percentile_3y_vs_full_range(self):
        frs = [d for d in DAYS if d.weekday() == 4 and d <= DATA_TO]
        full = [ratio_a(d) for d in frs]
        three = [ratio_a(d) for d in frs if d >= date(2023, 9, 24)]
        st = self.ja["ty_so"]["thong_ke"]
        self.assertEqual(st["toan_dai"]["n"], len(full))
        self.assertEqual(st["3y"]["n"], len(three))
        self.assertAlmostEqual(st["3y"]["phan_vi"], expected_pct(three, 2.0), places=9)
        self.assertAlmostEqual(st["toan_dai"]["phan_vi"], expected_pct(full, 2.0), places=9)
        self.assertGreater(st["3y"]["phan_vi"], 40)
        self.assertLess(st["toan_dai"]["phan_vi"], 25)
        self.assertAlmostEqual(st["toan_dai"]["max"], 4.0)
        self.assertEqual(st["3y"]["min_ngay"], "2023-09-29")
        self.assertAlmostEqual(st["3y"]["trung_vi"], sorted(three)[len(three) // 2] if len(three) % 2 else
                               (sorted(three)[len(three) // 2 - 1] + sorted(three)[len(three) // 2]) / 2)

    def test_chain_weight_and_holdco_layer(self):
        self.assertAlmostEqual(self.a.w_lt("GRC", DATA_TO), 0.6 * 0.5)
        tang = self.ja["tang"][0]
        self.assertEqual((tang["me"], tang["con"]), ("CON", ["GRC"]))
        self.assertAlmostEqual(tang["hien_tai"], a_close("CON", DATA_TO) * 1e9 / (0.6 * 1e13))

    def test_week_before_first_stake_row_is_flagged_and_left_out_of_stats(self):
        blk = self.a2.ty_so
        by = {x["fri"]: x for x in blk["tuan"]}
        before, after = by[date(2024, 6, 7)], by[date(2025, 6, 6)]
        self.assertFalse(before["du"])
        self.assertTrue(after["du"])
        self.assertAlmostEqual(before["lt"], 0.5 * a_close("CON", date(2024, 6, 7)) * 1e9)
        self.assertAlmostEqual(after["lt"], 0.5 * a_close("CON", date(2025, 6, 6)) * 1e9 + 0.78 * 2e13)
        _, parts, _ = self.a2._lt(date(2026, 9, 18), ["CON", "CDT"], self.a2.w_lt)
        self.assertEqual(parts["CDT"]["w"], 0.75)
        self.assertGreater(blk["thong_ke"]["toan_dai"]["n_bo"], 0)
        self.assertTrue(any("CDT có giá nhưng chưa có dòng sở hữu" in w for w in self.wa2))

    def test_ownership_cross_check_and_mismatch_warning(self):
        c1 = next(m for m in self.ja["thanh_vien"] if m["ma"] == "CON")
        src = {(x["nguon"], x["ty_le"]) for x in c1["doi_chieu"]}
        self.assertIn(("vc_lk/CON/shareholder", 0.48), src)
        self.assertIn(("vc_lk/PAR/relationship (subsidiaries)", 0.5), src)
        self.assertTrue(any(n.startswith("chaebol_ecosystems/HeA") for n, _ in src))
        self.assertNotIn(("vc_lk/CON/shareholder", 0.05), src)
        self.assertTrue(c1["lech"])
        self.assertTrue(any("Sở hữu PAR→CON" in w for w in self.wa))

    def test_den_cuts_prices_and_ownership_rows(self):
        with mock.patch.dict(os.environ, self.fx.env()):
            lv = L.build_live("nhom_a", den=date(2026, 9, 15))
        self.assertEqual(lv.data_to, date(2026, 9, 15))
        self.assertNotIn(0.40, [r["ty_le"] for r in lv.kho.cd["CON"]])
        self.assertIn(0.40, [r["ty_le"] for r in self.a.kho.cd["CON"]])
        self.assertEqual(lv.lnst("PAR")["ky"], "Q2/2026")
        with mock.patch.dict(os.environ, self.fx.env()):
            lv2 = L.build_live("nhom_a", den=date(2026, 6, 1))
        self.assertEqual(lv2.lnst("PAR")["ky"], "Q1/2026")
        self.assertAlmostEqual(lv2.lnst("PAR")["yoy"], 50.0)

    def test_store_rows_name_the_group_not_masan(self):
        self.assertFalse(any("MSN" in w for w in self.wa))
        db = next(s for s in self.ja["nguon_live"] if s["ten"] == L.DB_SRC_TEN)
        self.assertTrue(db["ok"])
        self.assertEqual(db["as_of"], DATA_TO.isoformat())


# ── AR(1), zigzag, capture, breakouts, lead/lag, correlations ───────────────


class PureTests(unittest.TestCase):
    def test_ar1_on_a_known_series(self):
        mu, phi = math.log(0.6), 0.9
        vals, days = [], []
        d = date(2024, 1, 5)
        for y0 in (mu + 0.5, mu - 0.5):
            y = y0
            for _ in range(40):
                vals.append(math.exp(y))
                days.append(d)
                y = mu + phi * (y - mu)
                d += timedelta(days=7)
            d += timedelta(days=28)                      # the gap breaks the pair across segments
        ar = L.ar1(vals, days)
        self.assertEqual(ar["n"], 78)
        self.assertAlmostEqual(ar["b"], phi - 1, places=9)
        self.assertAlmostEqual(ar["neo"], 0.6, places=9)
        self.assertAlmostEqual(ar["nua_doi_tuan"], -math.log(2) / math.log(phi), places=6)
        self.assertIsNone(ar["t"])                      # exact fit: no residual
        rng = random.Random(3)
        noisy = [v * math.exp(rng.gauss(0, 0.01)) for v in vals]
        arn = L.ar1(noisy, days)
        self.assertLess(arn["t"], -2)
        short = L.ar1(vals[:40], days[:40])
        self.assertEqual(short["n"], 39)
        self.assertIsNone(short["nua_doi_tuan"])
        self.assertIsNone(short["b"])
        self.assertTrue(short["ghi_chu"].startswith(M.CAN))

    def test_zigzag_legs(self):
        closes = [cb_k(k) for k in range(170)]
        piv, cand = L.zigzag(closes)
        self.assertEqual(piv, [(0, "dinh"), (109, "day"), (129, "dinh")])
        self.assertEqual(cand, (149, "day"))
        days = [fri(k) for k in range(170)]
        legs = L.legs_of(days, closes, piv)
        self.assertEqual([round(x["r"], 6) for x in legs], [-40.0, 100.0, -40.0])
        self.assertEqual([x["xac_nhan"] for x in legs], [True, True, False])     # 149 is only a candidate trough
        self.assertEqual((legs[-1]["tu"], legs[-1]["den"]), (fri(129), fri(169)))

    def test_capture_formula(self):
        cap, why = L.capture_of(2e14, 20.0, 0.5, 6e13, 100.0)
        self.assertAlmostEqual(cap, 4e13 / 3e13)
        self.assertEqual(L.capture_of(2e14, 20.0, 0.0, 6e13, 100.0)[0], None)

    def test_prev_max_and_breakout(self):
        closes = [100.0] * 300 + [60.0] * 20 + [100.0, 101.0, 102.0]
        days = [date(2020, 1, 1) + timedelta(days=i) for i in range(len(closes))]
        pm = L.prev_max(closes, 250)
        self.assertIsNone(pm[249])
        self.assertEqual(pm[250], 100.0)
        j = L.first_breakout(days, closes, pm, days[305])
        self.assertEqual(j, 321)

    def test_lag_correlation_sign_and_lag(self):
        rng = random.Random(5)
        r = [rng.gauss(0, 0.02) for _ in range(200)]
        fr = [date(2023, 1, 6) + timedelta(days=7 * i) for i in range(200)]
        rb = dict(zip(fr, r))
        rc = {fr[i]: r[i - 3] for i in range(3, 200)}          # the con moves 3 weeks after the base
        res = {k: v for k, v, _ in L.lag_corr(rb, rc, fr)}
        self.assertAlmostEqual(res[3], 1.0, places=9)
        self.assertLess(abs(res[-3]), 0.3)


class SwingTests(FixtureCase):
    def test_zigzag_and_capture_through_the_engine(self):
        legs = self.jb["zigzag"]["CBB"]["chan"]
        up = next(x for x in legs if x["tu"] == fri(109).isoformat())
        self.assertEqual(up["den"], fri(129).isoformat())
        self.assertAlmostEqual(up["r"], 100.0)
        cap = next(c for c in self.jb["capture"] if c["tu"] == fri(109).isoformat())
        expect = (130000.0 * 1e9 * (240.0 / 130.0 - 1)) / (0.5 * 60000.0 * 1e9 * 1.0)
        self.assertAlmostEqual(cap["capture"], expect)
        self.assertAlmostEqual(cap["r_me"], (240.0 / 130.0 - 1) * 100)
        self.assertEqual(cap["w"], 0.5)
        win = self.b.capture_cua_so("PBB", "CBB", fri(109), fri(129))
        self.assertAlmostEqual(win["capture"], expect)

    def test_breakout_after_trough(self):
        bp = {x["day"]: x for x in self.jb["bung_pha"]["CBB"]}
        first = bp[fri(109).isoformat()]
        self.assertEqual(first["bung_pha"], monday(123).isoformat())
        self.assertAlmostEqual(first["gia"], 102000.0)
        self.assertIsNone(bp[fri(149).isoformat()]["bung_pha"])           # open trough, no breakout yet
        self.assertEqual(self.jb["bung_pha"]["PBB"][0]["bung_pha"], monday(122).isoformat())

    def test_lead_lag_in_the_vn_index_cycle(self):
        dt = self.jb["dan_tre"]
        self.assertEqual(dt["co_so"], "PBB")
        cyc = [c for c in dt["chu_ky"] if c["nguon"] == "vni_day"]
        self.assertEqual(len(cyc), 1)
        self.assertEqual(cyc[0]["vni_day"], fri(105).isoformat())
        self.assertEqual(cyc[0]["tu"], (fri(105) - timedelta(days=120)).isoformat())
        cb = cyc[0]["ma"]["CBB"]
        self.assertEqual(cb["lech_bung_pha"], 7)
        self.assertEqual(cb["dinh"], fri(129).isoformat())
        self.assertEqual(cb["lech_dinh"], 0)
        self.assertTrue(all(c["nguon"] == "2_nam" for c in dt["chu_ky"] if c is not cyc[0]))

    def test_parent_null_group_uses_the_largest_member(self):
        j = self.jlag
        self.assertIsNone(j["ty_so"])
        self.assertIsNone(j["nhom"]["me"])
        self.assertEqual(j["co_so"], "LDA")
        self.assertEqual(j["dan_tre"]["co_so"], "LDA")
        tq = j["tuong_quan"]["ma"]["LDB"]
        self.assertEqual(tq["best_lag"], 2)
        self.assertAlmostEqual(tq["best_r"], 1.0, places=9)
        self.assertTrue(tq["co_y_nghia"])
        self.assertEqual(j["tuong_quan"]["so_tuan"], L.CORR_WEEKS)
        self.assertEqual(self.lag.do_dau_hieu("ty_so_holdco_pct")["thay"], None)


# ── per ticker, signals, framework signs ─────────────────────────────────────


class TickerTests(FixtureCase):
    def test_volume_flow_returns_sigma(self):
        p = next(m for m in self.ja["thanh_vien"] if m["ma"] == "PAR")
        self.assertAlmostEqual(p["kl"]["ty_le"], 3.0)
        self.assertEqual(p["kl"]["tuan"], LAST_FRI.isoformat())
        self.assertEqual(p["kl"]["mo_so_phien"], 4)
        self.assertAlmostEqual(p["kl"]["mo_ty_le"], 4e6 / ((19 * 5e6 + 15e6) / 20))
        self.assertAlmostEqual(p["nn_4t"]["tong"], 20 * 1e9)
        self.assertEqual(p["loi_suat"]["r_13t"], 0.0)
        sg = p["sigma"]
        self.assertEqual((sg["metric"], sg["z"], sg["suy_bien"]), ("pb", 1.0, False))
        self.assertAlmostEqual(sg["dai"]["-1"], 20000 * 3.0)
        c1 = next(m for m in self.ja["thanh_vien"] if m["ma"] == "CON")
        self.assertTrue(c1["sigma"]["suy_bien"])
        c3 = next(m for m in self.ja["thanh_vien"] if m["ma"] == "CDT")
        self.assertEqual(c3["sigma"]["metric"], "pe")                      # P/E fallback
        c1r = c1["loi_suat"]
        self.assertAlmostEqual(c1r["r_1t"], (a_close("CON", DATA_TO) / a_close("CON", LAST_FRI) - 1) * 100)

    def test_lnst_yoy_and_ttm(self):
        ln = self.a.lnst("PAR")
        self.assertEqual((ln["ky"], ln["lnst"], ln["lnst_cung_ky"]), ("Q2/2026", 150.0, 100.0))
        self.assertAlmostEqual(ln["yoy"], 50.0)
        self.assertAlmostEqual(ln["ttm"], 470.0)
        self.assertAlmostEqual(ln["yoy_ttm"], (470.0 / 325.0 - 1) * 100)
        self.assertTrue(self.a.lnst("CON")["ly_do"].startswith(M.CAN))

    def test_signal_evaluation(self):
        sig = {s["id"]: s for s in self.ja["tin_hieu"]}
        self.assertEqual(sig["X1"]["trang_thai"], "Đạt")                   # muc 90 = nghìn đồng
        self.assertEqual(sig["X1"]["as_of"], M.ddmmyyyy(LAST_FRI))
        self.assertEqual(sig["X2"]["trang_thai"], "Đạt")
        self.assertEqual(sig["X3"]["trang_thai"], "Chưa")
        self.assertAlmostEqual(sig["X3"]["gia_tri"], 2.0)
        self.assertEqual(sig["P1"]["trang_thai"], "An toàn")               # muc 95000 = đồng
        self.assertEqual(sig["P2"]["trang_thai"], "Kích hoạt")
        self.assertEqual(sig["X4"]["trang_thai"], "Đạt")
        self.assertEqual(sig["X4"]["tier"], "EST")
        self.assertFalse(sig["N1"]["live"])
        self.assertIsNone(sig["N1"]["trang_thai"])
        self.assertEqual(sig["N1"]["as_of"], "10/09/2026")
        self.assertFalse(sig["N2"]["live"])

    def test_do_dau_hieu_every_key(self):
        a, b = self.a, self.b
        r = a.do_dau_hieu("kl_tuan_tb20")
        self.assertEqual((r["thay"], r["gia_tri"], r["ngay"]), (True, 3.0, LAST_FRI.isoformat()))
        self.assertFalse(a.do_dau_hieu("kl_tuan_tb20", tham_so={"k": 4})["thay"])
        self.assertTrue(a.do_dau_hieu("nn_rong_4t")["thay"])
        self.assertTrue(a.do_dau_hieu("pb_sigma", "PAR", {"s": 1})["thay"])
        self.assertIsNone(a.do_dau_hieu("pb_sigma", "CON", {"s": -1})["thay"])   # −2σ ≤ 0: cheap side not scored
        self.assertTrue(a.do_dau_hieu("cach_dinh_52t", "PAR")["thay"])
        self.assertFalse(a.do_dau_hieu("vuot_ma200", "CON")["thay"])           # falling price
        self.assertFalse(a.do_dau_hieu("parabol", "CON")["thay"])
        self.assertTrue(a.do_dau_hieu("lnst_yoy", "PAR", {"g": 20})["thay"])
        self.assertIsNone(a.do_dau_hieu("lnst_yoy", "CON")["thay"])
        h = a.do_dau_hieu("ty_so_holdco_pct", tham_so={"p": 60})
        self.assertEqual(h["thay"], True)
        self.assertAlmostEqual(h["gia_tri"], self.ja["ty_so"]["thong_ke"]["3y"]["phan_vi"])
        self.assertFalse(a.do_dau_hieu("ty_so_holdco_pct", tham_so={"p": 40})["thay"])
        self.assertTrue(a.do_dau_hieu("ty_so_holdco_pct", tham_so={"p": 40, "cua_so": "toan_dai"})["thay"])
        self.assertEqual(a.do_dau_hieu("ty_so_holdco_pct", "CON")["ma"], "CON")   # the holdco layer
        bp = b.do_dau_hieu("bung_pha_250", "CBB")
        self.assertFalse(bp["thay"])                                          # nothing after the open trough
        self.assertIn(M.ddmmyyyy(fri(149)), bp["ghi_chu"])
        bpp = b.do_dau_hieu("bung_pha_250", "PBB")
        self.assertEqual((bpp["thay"], bpp["ngay"]), (True, monday(122).isoformat()))
        tu = b.do_dau_hieu("tang_tu_day", "PBB", {"x": 30})
        self.assertTrue(tu["thay"])
        self.assertAlmostEqual(tu["gia_tri"], (240.0 / 130.0 - 1) * 100)
        flat = b.do_dau_hieu("vuot_ma200", "CBB")                           # 72 flat for 40+ weeks
        self.assertEqual((flat["thay"], flat["gia_tri"]), (False, 1.0))
        for r in (bp, tu, h):
            self.assertEqual(r["tier"], "EST")
        self.assertEqual(a.do_dau_hieu("khoa_la")["ghi_chu"], "khoá phép đo lạ")
        self.assertTrue(a.do_dau_hieu("parabol", "CNP")["ghi_chu"].startswith(M.CAN))


class OutputTests(FixtureCase):
    def test_json_is_strict_and_dateless(self):
        for j in (self.ja, self.jb, self.jlag):
            txt = json.dumps(j, ensure_ascii=False, allow_nan=False)
            self.assertTrue(all(not isinstance(v, date) for v in walk(j)))
            self.assertEqual(j["schema"], L.SCHEMA_LIVE)
            self.assertNotIn("fa_rec", txt)

    def test_no_trade_or_sizing_words(self):
        for j in (self.ja, self.jb, self.jlag, self.jspl):
            self.assertIsNone(STANCE.search(json.dumps(j, ensure_ascii=False)))

    def test_chart_series(self):
        ch = self.ja["chuoi"]
        self.assertEqual(ch["x"][0], M.friday(M.REBASE_FROM).isoformat())
        self.assertEqual(ch["quy_100"]["PAR"][0], 100.0)
        self.assertEqual(len(ch["vni"]), len(ch["x"]))
        self.assertEqual(self.ja["dinh_gia_co_so"]["metric"], "pb")
        self.assertEqual(self.ja["kl_co_so"]["mo"]["so_phien"], 4)

    def test_vc_files_are_parsed_once_per_process(self):
        seen = []
        real = M.load_json

        def spy(path):
            seen.append(path)
            return real(path)
        with mock.patch.dict(os.environ, self.fx.env()), mock.patch.object(M, "load_json", spy):
            L.build_live("nhom_a")
        self.assertFalse([p for p in seen if p.endswith("price-history.json")])


# ── review regressions (store traps, statistics, signs) ──────────────────────


def custom(nh, **kw):
    """LiveNhom of an ad-hoc group dict on the fixture stores."""
    return L.build_live(nh, **kw)


class StoreTrapTests(FixtureCase):
    def test_noi_chuoi_anchors_head_and_tail(self):
        d = [date(2026, 1, 5) + timedelta(days=i) for i in range(6)]
        days, closes, notes = L.noi_chuoi(d[2:5], [10.0, 11.0, 12.0], [d[0], d[1], d[3], d[4], d[5]],
                                          [20.0, 20.0, 22.0, 24.0, 26.0])
        self.assertEqual((days, closes, notes), (d, [10.0, 10.0, 10.0, 11.0, 12.0, 13.0], []))
        days, closes, notes = L.noi_chuoi(d[2:5], [10.0, 11.0, 12.0], [d[0], d[5]], [20.0, 26.0])
        self.assertEqual((days, closes), (d[2:5], [10.0, 11.0, 12.0]))      # no anchor: no factor-1 splice
        self.assertEqual(len(notes), 2)
        self.assertEqual(L.noi_chuoi([], [], d[:2], [5.0, None]), ([d[0]], [5.0], []))

    def test_split_and_dividend_returns_use_adjusted_caps_use_raw(self):
        lv, j = self.spl, self.jspl
        ser = lv.ser["SPL"]
        self.assertEqual((ser["d"][0], ser["d"][-1]), (START, DATA_TO))       # Vietcap head and tail spliced
        self.assertTrue(all(abs(c - SPL_ADJ) < 1e-6 for c in ser["c"]))      # no split / dividend / basis jump
        m = next(x for x in j["thanh_vien"] if x["ma"] == "SPL")
        for k in ("r_1t", "r_13t", "r_ytd"):
            self.assertAlmostEqual(m["loi_suat"][k], 0.0, places=9)          # raw would give −5% YTD
        self.assertEqual(lv.zz["SPL"]["piv"], [])                             # raw would show a −50% leg
        self.assertEqual(j["capture"], [])
        self.assertEqual(lv.mc("SPL", date(2024, 6, 7))[0], 80000.0 * 5e8)   # before the split: raw × old shares
        self.assertEqual(lv.mc("SPL", date(2025, 6, 6))[0], 40000.0 * 1e9)
        self.assertEqual(m["mcap"], 38000.0 * 1e9)
        self.assertEqual((m["gia"]["dong"], m["gia"]["dong_dc"]), (38000.0, SPL_ADJ))
        by = {x["fri"]: x["r"] for x in j["ty_so"]["tuan"]}
        self.assertAlmostEqual(by["2024-06-07"], 1e14 / (0.4 * 4e13))
        self.assertAlmostEqual(j["ty_so"]["hien_tai"], 1e14 / (0.4 * 3.8e13))

    def test_missing_anchor_day_and_basis_do_not_jump(self):
        ser = self.spl.ser["SPL"]
        i = ser["d"].index(SPL_NEN_FIRST)
        self.assertEqual(ser["c"][i - 1], ser["c"][i])                        # Vietcap 45.600 rescaled to 38.000

    def test_stale_member_is_never_the_axis(self):
        lv = self.truc
        self.assertEqual((lv.base, lv.data_to), ("CDT", DATA_TO))             # STL is the largest cap but stale
        self.assertEqual(L.chon_co_so(lv.kho, lv.nhom), "CDT")
        self.assertEqual(lv.ser["SPL"]["d"][-1], DATA_TO)                     # nen stops early, Vietcap tail used
        self.assertEqual(lv.ser["STL"]["d"][-1], EARLY_LAST)
        self.assertTrue(any("giá STL dừng ở %s" % M.ddmmyyyy(EARLY_LAST) in w for w in self.wtruc))
        self.assertFalse(any("giá SPL dừng" in w for w in self.wtruc))
        small = L.Nhom({"id": "nhom_truc", "me": None, "thanh_vien": [{"ma": "STL"}, {"ma": "CDT"}]}, [])
        self.assertEqual(L.LiveNhom(lv.kho, small, co_so="CDT").data_to, DATA_TO)

    def test_cap_from_adjusted_history_is_refused(self):
        lv, j = self.nvc, self.nvc.to_json()
        self.assertIsNone(lv.mc("NVC", date(2025, 1, 3))[0])                   # vnstore history row × today's shares
        self.assertEqual(lv.mc("NVC", DATA_TO)[0], 10000.0 * 1e9)             # the raw board row
        self.assertAlmostEqual(j["ty_so"]["hien_tai"], 1e14 / (0.5 * 1e13))
        self.assertEqual(j["ty_so"]["thong_ke"]["3y"]["n"], 0)
        self.assertTrue(any("NVC không có vc_lk price-history" in w for w in self.wnvc))
        m = next(x for x in j["thanh_vien"] if x["ma"] == "NVC")
        self.assertEqual(m["gia"]["nguon"], "nen")

    def test_partial_flow_week_is_not_a_weekly_total(self):
        with mock.patch.dict(os.environ, self.fx.env()):
            lv = custom({"id": "nhom_nn", "me": None, "thanh_vien": [{"ma": "NNP"}]})
        nn = lv.per["NNP"]["nn_4t"]
        self.assertEqual([x["gia_tri"] for x in nn["tuan"]][:3], [5e9, 5e9, 5e9])
        self.assertIsNone(nn["tuan"][-1]["gia_tri"])                          # Mon–Wed of the week of 18/09 only
        self.assertIsNone(nn["tong"])
        self.assertIsNone(lv.do_dau_hieu("nn_rong_4t", "NNP")["thay"])


class RatioWindowTests(FixtureCase):
    def test_percentile_needs_52_weeks_and_shows_its_window(self):
        txt = self.ja["ty_so"]["txt"]["phan_vi_3y"]
        self.assertRegex(txt, r"^\d+% · từ 29/09/2023 · \d+ tuần$")
        with mock.patch.dict(os.environ, self.fx.env()):
            lv = custom({"id": "nhom_ngan", "me": "PAR", "thanh_vien": [
                {"ma": "CDT", "me": "PAR", "trong_lt": True, "so_huu": [stake("2026-06-30", 0.75)]}]})
        st = lv.ty_so["thong_ke"]["3y"]
        self.assertLess(st["n"], L.PCT_MIN_N)
        self.assertFalse(st["du_mau"])
        self.assertIsNone(st["phan_vi"])
        self.assertEqual(lv.to_json()["ty_so"]["txt"]["phan_vi_3y"],
                         "%s: chỉ %d tuần từ 03/07/2026 (cần ≥ 52)" % (M.CAN, st["n"]))
        h = lv.do_dau_hieu("ty_so_holdco_pct", tham_so={"p": 99})
        self.assertIsNone(h["thay"])
        self.assertTrue(h["ghi_chu"].startswith(M.CAN))

    def test_child_listed_inside_the_window(self):
        j = self.ny.to_json()["ty_so"]
        self.assertEqual(j["niem_yet"], [{"ma": "CMO", "ngay": LIST_DAY.isoformat()}])
        s3 = j["thong_ke"]["3y"]
        self.assertTrue(s3["niem_yet"]["cat"])                                # ≥ 52 weeks after the listing
        self.assertGreaterEqual(s3["tu"], LIST_DAY.isoformat())
        self.assertGreaterEqual(s3["n"], L.PCT_MIN_N)
        self.assertIn("sau khi CMO niêm yết", j["txt"]["phan_vi_3y"])
        with mock.patch.dict(os.environ, self.fx.env()):
            early = custom("nhom_niem_yet", den=date(2026, 3, 2)).to_json()["ty_so"]["thong_ke"]["3y"]
        self.assertFalse(early["niem_yet"]["cat"])                            # too few weeks: reported, not cut
        self.assertGreater(early["niem_yet"]["n_truoc"], 0)
        self.assertLess(early["tu"], LIST_DAY.isoformat())
        self.assertIn("trước khi CMO niêm yết", L.pv_txt(early))


class SignTests(FixtureCase):
    def test_alias_thresholds_replace_the_default(self):
        a = self.a
        r = a.do_dau_hieu("kl_tuan_tb20", tham_so={"nguong": 99})
        self.assertEqual((r["thay"], r["tham_so"]["k"]), (False, 99))        # not the default 1,5
        self.assertTrue(a.do_dau_hieu("kl_tuan_tb20", tham_so={"muc": 2})["thay"])
        self.assertFalse(a.do_dau_hieu("ty_so_holdco_pct", tham_so={"muc": 1})["thay"])
        self.assertTrue(a.do_dau_hieu("ty_so_holdco_pct", tham_so={"nguong": 99})["thay"])
        self.assertTrue(a.do_dau_hieu("cach_dinh_52t", "PAR")["thay"])
        self.assertFalse(a.do_dau_hieu("cach_dinh_52t", "PAR", {"nguong": -1})["thay"])
        self.assertEqual(a.do_dau_hieu("parabol", "PAR", {"k": 3, "nguong": 0.5})["tham_so"]["k"], 3)

    def test_pb_sigma_cheap_side(self):
        a = self.a                                                            # PAR at +1σ, CON band degenerate
        r = a.do_dau_hieu("pb_sigma", "PAR", {"s": -1})
        self.assertFalse(r["thay"])                                           # +1σ is not on the cheap side of −1σ
        self.assertIn("phía rẻ", r["ghi_chu"])
        self.assertTrue(a.do_dau_hieu("pb_sigma", "PAR", {"s": 1})["thay"])
        self.assertTrue(a.do_dau_hieu("pb_sigma", "PAR", {"s": 1.5, "phep": "<="})["thay"])
        self.assertIsNone(a.do_dau_hieu("pb_sigma", "CON", {"s": 1.5, "phep": "<="})["thay"])
        x5 = next(s for s in self.ja["tin_hieu"] if s["id"] == "X5")          # dossier signal pb_sigma:CON < −1
        self.assertEqual(x5["trang_thai"], M.CAN)
        self.assertIn("suy biến", x5["ghi_chu"])

    def test_non_ticker_intermediate_holder(self):
        nh = {"id": "nhom_holdco", "me": "PAR", "thanh_vien": [
            {"ma": "CON", "me": "Công ty HoldCo chưa niêm yết", "trong_lt": True,
             "so_huu": [stake("2018-12-31", 0.6)]}]}
        w = []
        with mock.patch.dict(os.environ, self.fx.env()):
            lv = custom(nh, warnings=w)
        self.assertIsNone(lv.w_lt("CON", DATA_TO))                           # not 0,6 as if PAR held it directly
        self.assertIsNone(lv.ty_so)
        self.assertIn("qua Công ty HoldCo chưa niêm yết", lv.excluded["CON"])
        nh["thanh_vien"][0]["so_huu"].append(stake("2018-12-31", 0.3, loai="hieu_dung"))
        with mock.patch.dict(os.environ, self.fx.env()):
            lv = custom(nh)
        self.assertEqual(lv.w_lt("CON", DATA_TO), 0.3)
        self.assertEqual(lv.lt_set, ["CON"])

    def test_sigma_dated_after_den_is_not_used(self):
        with mock.patch.dict(os.environ, self.fx.env()):
            lv = L.build_live("nhom_a", den=date(2026, 9, 15), dossier=dossier_a())
        self.assertIsNone(lv.per["PAR"]["sigma"])
        self.assertIn("sau mốc --den 15/09/2026", lv.sigma_ly_do)
        r = lv.do_dau_hieu("pb_sigma", "PAR", {"s": 1})
        self.assertIsNone(r["thay"])
        self.assertIn("--den", r["ghi_chu"])
        x4 = next(s for s in lv.signals if s["id"] == "X4")
        self.assertEqual(x4["trang_thai"], M.CAN)
        self.assertIsNone(lv.to_json()["dinh_gia_co_so"])

    def test_lead_lag_marks_open_pivots(self):
        cyc = next(c for c in self.jb["dan_tre"]["chu_ky"] if c["nguon"] == "vni_day")["ma"]
        self.assertFalse(cyc["PBB"]["dinh_xac_nhan"])                         # 240 is still the running high
        self.assertTrue(cyc["CBB"]["dinh_xac_nhan"])
        self.assertTrue(cyc["CBB"]["lech_dinh_mo"])                           # measured against an open peak
        self.assertTrue(cyc["CBB"]["bung_pha_xac_nhan"])


class StatsEdgeTests(unittest.TestCase):
    @staticmethod
    def series(phi, n=70, mu=math.log(2.0), y0=0.3):
        vals, days, y, d = [], [], mu + y0, date(2023, 1, 6)
        for _ in range(n):
            vals.append(math.exp(y))
            days.append(d)
            y = mu + phi * (y - mu)
            d += timedelta(days=7)
        return vals, days

    def test_ar1_gap_and_regimes(self):
        vals, days = self.series(0.9, 130)
        keep = [i for i in range(130) if i % 10 != 9]                         # drop every 10th week
        ar = L.ar1([vals[i] for i in keep], [days[i] for i in keep])
        self.assertEqual(ar["n"], sum(1 for a, b in zip(keep, keep[1:]) if b - a == 1))   # 14-day pairs dropped
        up = L.ar1(*self.series(1.05))                                        # b = +0,05: no reversion
        self.assertAlmostEqual(up["b"], 0.05, places=9)
        self.assertIsNone(up["neo"])
        self.assertIsNone(up["nua_doi_tuan"])
        osc = L.ar1(*self.series(-0.5))                                       # b = −1,5: converging, sign-flipping
        self.assertAlmostEqual(osc["b"], -1.5, places=9)
        self.assertAlmostEqual(osc["nua_doi_tuan"], 1.0, places=9)
        self.assertAlmostEqual(osc["neo"], 2.0, places=9)
        self.assertNotIn("nổ", osc["ghi_chu"])
        boom = L.ar1(*self.series(-1.2, 60, y0=1e-6))                         # b = −2,2: explosive
        self.assertIn("b ≤ −2", boom["ghi_chu"])
        self.assertIsNone(boom["neo"])
        self.assertIsNone(boom["nua_doi_tuan"])

    def test_best_lag_flag_uses_bonferroni(self):
        rng = random.Random(7)
        fr = [date(2023, 1, 6) + timedelta(days=7 * i) for i in range(157)]
        hits = old = 0
        for _ in range(200):
            rb = {f: rng.gauss(0, 0.03) for f in fr}
            rc = {f: rng.gauss(0, 0.03) for f in fr}
            row = L.corr_row(rb, rc, fr)
            hits += row["co_y_nghia"]
            old += abs(row["best_r"]) >= row["nguong_1_phep"]
        self.assertGreater(old / 200.0, 0.3)                                  # the single-test rule: ~half flagged
        self.assertLess(hits / 200.0, 0.12)                                   # Bonferroni: about the 5 % level
        self.assertAlmostEqual(L.CORR_Z, 2.89, places=2)


# ── real stores (skipped when absent) ────────────────────────────────────────


def real_env():
    return {k: v for k, v in os.environ.items() if k not in ENV_KEYS}


def real_ready():
    with mock.patch.dict(os.environ, real_env(), clear=True):
        p = M.paths()
    need = [p["vnstore"]] + [os.path.join(p["vc_lk"], s, f) for s in ("VIC", "VHM", "VPL", "VRE", "GEX", "GEE",
                                                                      "GEL", "EIB", "VGC")
                             for f in ("price-history.json", "shareholder.json")]
    return all(os.path.isfile(x) for x in need) and os.path.isfile(os.path.join(p["vc_lk"], "VIC", "relationship.json"))


def holder_row(vc, child, code):
    for r in M.load_json(os.path.join(vc, child, "shareholder.json"))["du_lieu"]:
        if r.get("ownerCode") == code:
            return r["percentage"], r["publicDate"][:10]
    return None


def rel_row(vc, parent, child):
    d = M.load_json(os.path.join(vc, parent, "relationship.json"))["du_lieu"]
    for kind in ("subsidiaries", "affiliates"):
        for r in d.get(kind, []):
            if r.get("rightTicker") == child:
                return r["ownedPercentage"], kind
    return None


@unittest.skipUnless(real_ready(), "real stores not present")
class RealStoreSmoke(unittest.TestCase):
    """Vingroup + GELEX from a TEMP registry built from the vc_lk shareholder / relationship files."""

    @classmethod
    def setUpClass(cls):
        cls.env = real_env()
        with mock.patch.dict(os.environ, cls.env, clear=True):
            vc = M.paths()["vc_lk"]
        cls.st = {"VHM": holder_row(vc, "VHM", "VIC"), "VPL": holder_row(vc, "VPL", "VIC"),
                  "VRE": holder_row(vc, "VRE", "VIC"), "GEE": holder_row(vc, "GEE", "GELEX"),
                  "GEL": holder_row(vc, "GEL", "GELEX"), "EIB": holder_row(vc, "EIB", "GELEX"),
                  "VGC": holder_row(vc, "VGC", "GELEXINFRAS")}
        cls.rel = {"VPL": rel_row(vc, "VIC", "VPL"), "VRE": rel_row(vc, "VIC", "VRE")}

        def row(sym, src):
            v, d = cls.st[sym]
            return {"tu": d, "ty_le": v, "loai": "phap_ly", "tier": "FACT-T2",
                    "nguon": "vc_lk/%s/shareholder (%s) publicDate %s" % (sym, src, d)}
        reg = {"schema": L.SCHEMA_REG, "lap_luc": "2026-10-10", "ghi_chu": "TEMP, kiểm thử E1", "nhom": [
            {"id": "vingroup", "ten": "Vingroup", "me": "VIC", "he_sinh_thai": ["Vingroup"], "thanh_vien": [
                {"ma": "VIC", "vai_tro": "mẹ"},
                {"ma": "VHM", "vai_tro": "con", "me": "VIC", "trong_lt": True, "so_huu": [
                    row("VHM", "VIC"),
                    {"tu": "2018-05-17", "ty_le": 0.693, "tier": "NEWS",
                     "nguon": "hồ sơ MSN 24/09/2026 phan_III.cap 'VIC ← VHM (niêm yết) 69,3% 17/05/2018'"}]},
                {"ma": "VPL", "vai_tro": "con", "me": "VIC", "trong_lt": True, "so_huu": [row("VPL", "VIC")]},
                {"ma": "VRE", "vai_tro": "liên kết", "me": "VIC", "trong_lt": True, "so_huu": [row("VRE", "VIC")]}]},
            {"id": "gelex", "ten": "GELEX", "me": "GEX", "he_sinh_thai": ["GELEX-TuấnMượt"], "thanh_vien": [
                {"ma": "GEX", "vai_tro": "mẹ"},
                {"ma": "GEE", "vai_tro": "con", "me": "GEX", "trong_lt": True, "so_huu": [
                    row("GEE", "GELEX"),
                    {"tu": "2025-01-02", "ty_le": 0.78, "tier": "NEWS",
                     "nguon": "hồ sơ MSN 24/09/2026 phan_III.capture 'GEX ← GEE (~78%)' năm 2025 (ngày hiệu lực "
                              "suy từ 'năm 2025', EST)"}]},
                {"ma": "GEL", "vai_tro": "con", "me": "GEX", "trong_lt": True, "so_huu": [row("GEL", "GELEX")]},
                {"ma": "EIB", "vai_tro": "liên kết", "me": "GEX", "trong_lt": True, "so_huu": [row("EIB", "GELEX")]},
                {"ma": "VGC", "vai_tro": "cháu", "me": "GEL", "trong_lt": False,
                 "so_huu": [row("VGC", "GELEXINFRAS")]}],
             "tang": [{"me": "GEL", "con": ["VGC"]}]}]}
        cls.root = tempfile.mkdtemp(prefix="chaebol_live_real_")
        Fixture.write(os.path.join(cls.root, "nhom.json"), reg)
        cls.out, cls.t = {}, {}
        with mock.patch.dict(os.environ, cls.env, clear=True):
            for nid in ("vingroup", "gelex"):
                L.clear_cache()
                t = time.time()
                lv = L.build_live(nid, root=cls.root)
                js = lv.to_json()
                cls.t[nid] = time.time() - t
                cls.out[nid] = (lv, js)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def report(self, nid):
        lv, js = self.out[nid]
        ts = js["ty_so"]
        s3, sf = ts["thong_ke"]["3y"], ts["thong_ke"]["toan_dai"]
        lines = ["%s · dữ liệu đến %s · %.2fs" % (nid, js["data_to"], self.t[nid]),
                 "  %s ÷ LT %s (LT %s: %s)" % (ts["me"], ts["txt"]["hien_tai"], ts["txt"]["lt"],
                                               js["lt"]["txt"]["thanh_phan"]),
                 "  3Y: n %d · trung vị %s · phân vị %s · AR(1) n %d b %s t %s nửa đời %s" % (
                     s3["n"], M.x_txt(s3["trung_vi"]), ts["txt"]["phan_vi_3y"], s3["ar1"]["n"],
                     M.fmt_vn(s3["ar1"]["b"], 4), M.fmt_vn(s3["ar1"]["t"], 2), ts["txt"]["nua_doi_3y"]),
                 "  toàn dải: n %d (bỏ %d) · trung vị %s · phân vị %s" % (
                     sf["n"], sf["n_bo"], M.x_txt(sf["trung_vi"]), ts["txt"]["phan_vi_toan_dai"])]
        for t in js["tang"]:
            lines.append("  tầng %s ÷ LT %s (phân vị 3Y %s, %d tuần)" % (t["me"], t["txt"]["hien_tai"],
                                                                        t["txt"]["phan_vi_3y"], t["thong_ke"]["3y"]["n"]))
        for c in js["capture"]:
            if c["capture"] is not None:
                lines.append("  capture %s←%s %s→%s con %s me %s w %s → %s" % (
                    c["me"], c["con"], c["tu"], c["den"], M.pct_txt(c["r_con"]), M.pct_txt(c["r_me"]),
                    M.share_txt(c["w"]), M.fmt_vn(c["capture"], 3)))
        print("\n" + "\n".join(lines))

    def test_vingroup(self):
        lv, js = self.out["vingroup"]
        for s in ("VHM", "VPL", "VRE"):
            self.assertIsNotNone(self.st[s])
        self.assertEqual(self.st["VHM"], (0.717, "2026-08-06"))
        self.assertEqual(self.rel["VPL"][0], self.st["VPL"][0])
        self.assertEqual(self.rel["VRE"], (self.st["VRE"][0], "affiliates"))
        parts = {p["ma"]: p["w"] for p in js["lt"]["phan"]}
        self.assertEqual(parts, {"VHM": 0.717, "VPL": self.st["VPL"][0], "VRE": self.st["VRE"][0]})
        r = js["ty_so"]["hien_tai"]
        self.assertTrue(r and r > 1)                      # VIC trades at a premium to its listed stakes
        self.assertLess(self.t["vingroup"], 1.5)
        vhm = lv.capture_cua_so("VIC", "VHM", "2024-12-31", "2025-12-31", w=0.70)
        print("\nVIC←VHM năm 2025 (w 70%%, cửa sổ hồ sơ MSN): con %s · mẹ %s → %s" % (
            M.pct_txt(vhm["r_con"]), M.pct_txt(vhm["r_me"]), M.fmt_vn(vhm["capture"], 3)))
        self.report("vingroup")

    def test_gelex(self):
        lv, js = self.out["gelex"]
        parts = {p["ma"]: p["w"] for p in js["lt"]["phan"]}
        self.assertEqual(parts, {"GEE": self.st["GEE"][0], "GEL": self.st["GEL"][0], "EIB": self.st["EIB"][0]})
        self.assertTrue(0.2 < js["ty_so"]["hien_tai"] < 1.5)
        self.assertEqual([t["me"] for t in js["tang"]], ["GEL"])
        self.assertLess(self.t["gelex"], 1.5)
        for tu, den, w in (("2024-12-31", "2025-12-31", 0.78), ("2025-12-31", "2026-09-23", None)):
            c = lv.capture_cua_so("GEX", "GEE", tu, den, w=w)
            print("\nGEX←GEE %s→%s (w %s): con %s · mẹ %s → %s" % (tu, den, M.share_txt(c["w"]), M.pct_txt(c["r_con"]),
                                                                  M.pct_txt(c["r_me"]), M.fmt_vn(c["capture"], 3)))
        self.report("gelex")

    def test_cross_check_dossier_holdco(self):
        """MSN dossier 24/09 phan_III.holdco (giá cắt 23/09): VIC 4,42× (VHM 73,51%), GEX 0,58× (GEE 75,95%,
        GEL 79,1%); recomputed 05/10 with GEL 70,21% and EIB 10%: ~0,547×."""
        hs = "hồ sơ MSN 24/09/2026 phan_III.holdco (giá cắt 23/09)"
        cases = (
            ("2026-09-23", "VIC", {"VHM": 0.7351}, 4.42, 0.03),
            ("2026-09-23", "GEX", {"GEE": 0.7595, "GEL": 0.791}, 0.58, 0.03),
            ("2026-10-05", "GEX", {"GEE": self.st["GEE"][0], "GEL": self.st["GEL"][0], "EIB": self.st["EIB"][0]},
             0.547, 0.02))
        for den, me, kids, want, tol in cases:
            nh = {"id": "doi_chieu_%s" % me.lower(), "me": me, "thanh_vien": [
                {"ma": c, "me": me, "trong_lt": True, "so_huu": [{"tu": den, "ty_le": w, "tier": "NEWS", "nguon": hs}]}
                for c, w in kids.items()]}
            with mock.patch.dict(os.environ, self.env, clear=True):
                lv = L.build_live(nh, den=M.parse_day(den))
            r = lv.ty_so["hien_tai"]
            print("\n%s ÷ LT %s (%s): %s · hồ sơ %s" % (me, den, ", ".join("%s %s" % (c, M.share_txt(w))
                                                                         for c, w in kids.items()),
                                                         M.x_txt(r), M.x_txt(want)))
            self.assertAlmostEqual(r / want, 1.0, delta=tol)

    def test_no_trade_or_sizing_words(self):
        for _, js in self.out.values():
            self.assertIsNone(STANCE.search(json.dumps(js, ensure_ascii=False, allow_nan=False)))

    def test_large_group_under_budget(self):
        pvn = ["GAS", "BSR", "POW", "OIL", "DCM", "DPM", "PVS", "PVD", "PVT", "PVC", "PVI", "PGD", "PVB", "PGS",
               "PVG", "CNG", "NT2", "HNA", "PVP", "PTT", "PDV", "GSP", "PQN", "POS", "PVY", "PBP", "PET", "PLX",
               "PGC", "PTS"]
        nh = {"id": "petrovietnam_thu", "ten": "PVN (thử)", "me": None, "he_sinh_thai": ["Petrovietnam"],
              "thanh_vien": [{"ma": s, "vai_tro": "thành viên"} for s in pvn]}
        with mock.patch.dict(os.environ, self.env, clear=True):
            L.clear_cache()
            t = time.time()
            js = L.build_live(nh).to_json()
            dt = time.time() - t
        print("\nPVN %d mã (%d có giá): %.2fs · cơ sở %s" % (len(pvn), js["nhom"]["so_ma_co_gia"], dt, js["co_so"]))
        self.assertLess(dt, 4.0 if js["nhom"]["so_ma_co_gia"] > 20 else 1.5)   # 1,5 s per group; 4 s only > 20 mã
        self.assertIsNone(js["ty_so"])

    def test_real_registry_if_present(self):
        with mock.patch.dict(os.environ, self.env, clear=True):
            path = os.path.join(L.reg_dir(), "nhom.json")
            if not os.path.isfile(path):
                self.skipTest("registry thật chưa có: %s" % path)
            reg, _ = L.load_registry()
            for nid in ("vingroup", "gelex"):
                nh = reg.nhom(nid)
                if nh is None:
                    continue
                js = L.build_live(nh).to_json()
                ts = js["ty_so"] or {}
                print("\nregistry thật %s: %s ÷ LT %s" % (nid, ts.get("me"), (ts.get("txt") or {}).get("hien_tai")))


if __name__ == "__main__":
    unittest.main()
