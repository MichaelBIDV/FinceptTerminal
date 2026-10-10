#!/usr/bin/env python3
"""Test P2 data_price (codong v2 §5, §11.2): chaebol_map_data_codong2_gia + chaebol_map_data_codong2_dong.

Hai lớp: (1) cây _System giả trong thư mục tạm (CHB_SYSTEM_DIR), mạng bị chặn, số kỳ vọng tính tay từ chính fixture;
(2) kho thật, CHỈ ĐỌC, bỏ qua khi không có (ghim dữ kiện lịch sử §1: F3, F5, F9, F21, F24; độ phủ tính động).
Chạy:  python3.14 -m pytest -q test_chaebol_map_data_codong2_gia.py
       "<venv-numpy2>/bin/python" -m pytest -q test_chaebol_map_data_codong2_gia.py
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import chaebol_map_data_codong2_dong as DG  # noqa: E402
import chaebol_map_data_codong2_gia as P  # noqa: E402
import chaebol_map_data_nen as N  # noqa: E402

REAL_SYS = Path.home() / "SECOND BRAIN-OBSIDIAN" / "_System"
ENV_KEYS = ("CHB_SYSTEM_DIR", "CHB_TODAY", "CHB_SKILLS_DIR", "CHB_SPEC_DIR")
FORBIDDEN = re.compile(r"\b(BUY|SELL|TRIM|ADD|DCA)\b|%NAV|khuyến nghị mua|khuyến nghị bán|nên mua|nên bán|as of", re.I)

COLS = ["tradingDate", "openPrice", "highestPrice", "lowestPrice", "closePrice", "openPriceAdjusted",
        "highestPriceAdjusted", "lowestPriceAdjusted", "closePriceAdjusted", "totalMatchVolume", "totalMatchValue",
        "totalDealVolume", "totalDealValue", "foreignNetVolumeTotal", "foreignNetValueTotal", "foreignOwnedPercentage",
        "foreignCurrentRoom", "foreignRoomPercentage", "totalShares", "foreignNetValueMatched", "foreignNetValueDeal",
        "averageBuyTradeVolume", "averageSellTradeVolume", "totalBuyUnmatchedVolume", "totalSellUnmatchedVolume"]
PROP_COLS = ["tradingDate", "totalTradeNetVolume", "totalTradeNetValue", "totalMatchTradeNetVolume",
             "totalMatchTradeNetValue"]
# Đường giá điều chỉnh theo tuần (×1000 đ): đỉnh 130 tuần 4, đáy 100 tuần 8, ext 126 tuần 12 (chưa đảo ≥18%).
PATH = [100, 104, 110, 120, 130, 122, 112, 104, 100, 106, 113, 121, 126, 120, 116, 112, 110, 111, None, 112, 114, 115]
MON0 = date(2018, 10, 1)
E0, E1, TS, E2 = "2018-10-10", "2018-10-15", "2018-11-05", "2019-01-07"   # cổ tức tiền, chia 2, totalShares, thưởng 1.5
SPIKE_DAY, NO_TD = "2019-01-15", ("2019-01-09", "2019-02-12")
DEAL_DAYS = {"2018-10-16": 10_000, "2018-11-01": 12_000, "2018-12-11": 8_000, "2018-12-20": 9_000,
             "2019-01-22": 11_000, SPIKE_DAY: 400_000}


def sessions() -> list:
    out = []
    for k, px in enumerate(PATH):
        if px is None:
            continue
        mon = MON0 + timedelta(weeks=k)
        for dd in range(3 if k == len(PATH) - 1 else 5):
            d = (mon + timedelta(days=dd)).isoformat()
            if d != "2019-01-01":
                out.append((d, k, px * 1000.0))
    return out


def f_of(d: str) -> float:
    """closeAdj / close của fixture."""
    f = 1.0 if d >= E2 else 1 / 1.5
    f = f if d >= E1 else f / 2
    return f if d >= E0 else f * 0.98


def shares_true(d: str) -> float:
    return 4_500_000.0 if d >= E2 else 3_000_000.0 if d >= E1 else 1_500_000.0


def mult_true(d: str) -> float:
    return 1.0 if d >= E2 else 1.5 if d >= E1 else 3.0


def ph_rows() -> list:
    pre = dict.fromkeys(COLS, None) | {"tradingDate": "2018-09-28", "closePrice": 1.0, "closePriceAdjusted": 1.0}
    rows = [[pre[c] for c in COLS]]                                      # phiên trước niêm yết: bị cắt
    ss = sessions()
    for i, (d, k, adj) in enumerate(ss):
        raw = adj / f_of(d)
        kl = 10_000.0 * (1 + i % 5)
        nv = -500.0 if i >= len(ss) - 5 else 1000.0 * (i % 7 - 3)
        r = dict.fromkeys(COLS, None)
        r.update(tradingDate=d, openPrice=raw, highestPrice=raw * 1.01, lowestPrice=raw * 0.99, closePrice=raw,
                 openPriceAdjusted=adj, highestPriceAdjusted=adj * 1.01, lowestPriceAdjusted=adj * 0.99,
                 closePriceAdjusted=adj, totalMatchVolume=kl, totalMatchValue=kl * raw, foreignNetVolumeTotal=nv,
                 foreignNetValueTotal=nv * raw, totalDealVolume=0.0, totalDealValue=0.0, foreignRoomPercentage=0.49,
                 foreignOwnedPercentage=None if i >= len(ss) - 2 else 0.05 + 0.0001 * i)
        if d in DEAL_DAYS:
            r.update(totalDealVolume=float(DEAL_DAYS[d]), totalDealValue=DEAL_DAYS[d] * raw * (1.05 if d == SPIKE_DAY else 1))
        if d >= TS and i < len(ss) - 2:
            r["totalShares"] = shares_true(d)
            r["foreignCurrentRoom"] = 1_000_000.0 if i % 2 == 0 else None
        if d == "2018-11-28":
            r["totalShares"] = 3_000_001.0                     # gai một phiên
        if i >= len(ss) - 25:
            r.update(foreignNetValueMatched=nv * raw * 0.6, foreignNetValueDeal=nv * raw * 0.4)
        if i >= len(ss) - 5:
            r.update(averageBuyTradeVolume=120.0 + i, averageSellTradeVolume=100.0, totalBuyUnmatchedVolume=50.0,
                     totalSellUnmatchedVolume=70.0)
        rows.append([r[c] for c in COLS])
    return rows


def prop_rows() -> list:
    out = []
    for i, (d, _, adj) in enumerate(sessions()):
        if d < "2019-01-02" or d in NO_TD:
            continue
        v = 200.0 * (i % 3 - 1)
        out.append([d, v, v * adj / f_of(d), v, v * adj / f_of(d)])
    return out


def fridays(n0: int, n1: int) -> list:
    return [(MON0 + timedelta(weeks=k, days=4)).isoformat() for k in range(n0, n1)]


def atom(v, u, b="EST", t="2019-02-22", g=None):
    return {"v": v, "u": u, "t": t, "b": b, "n": "fixture.fft", "g": g}


def lk_fixture() -> dict:
    t = fridays(2, 21)
    fw = [0.1 + 0.01 * i for i in range(len(t))]
    fw[5] = None
    fft = {"chuoi": {"t": t, "fw": fw, "p10": [0.05] * len(t), "p90": [0.4] * len(t), "t_cuoi": t[-1], "g": "giả"},
           "pct3y": atom(26, "diem", "FACT-T2"), "pall": atom(53, "diem", "FACT-T2"), "ma4": atom(0.1, "%tuan"),
           "p10_3y": atom(0.12, "%tuan"), "p90_3y": atom(0.5, "%tuan"), "x_p10": atom(0.83, "x"),
           "x_p90": atom(0.2, "x"), "lech": atom(-27, "diem", "FACT-T2"), "canh_bao": ["cảnh báo giả"],
           "pattern_d": [{"tuan": t[3], "boi": 2.1, "b": "EST"}]}
    return {"ma": "AAA", "fft": fft, "rrg": {"goc": "Weakening", "t_cuoi": t[-1], "n_tuan": 19, "b": "EST", "n": "rrg giả"}}


def wj(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def make_fixture(root: Path) -> dict:
    vc = root / "fincept_bridge" / "state" / "vc_lk"
    wj(vc / "AAA" / "price-history.json", {"meta": {"bac": "FACT-T2"}, "du_lieu": {"cot": COLS, "hang": ph_rows()}})
    wj(vc / "AAA" / "proprietary-history.json", {"meta": {}, "du_lieu": {"cot": PROP_COLS, "hang": prop_rows()}})
    wj(vc / "AAA" / "details.json", {"meta": {}, "du_lieu": {"listingDate": "2018-10-01T00:00:00"}})
    idx = [[d, 1000.0 + i, 1000.0 + i, 1000.0 + i, 1000.0 + i, 1e6] for i, (d, _, _) in enumerate(sessions())
           if d >= "2018-10-08"]
    wj(vc / "VNINDEX" / "gap-chart.json", {"meta": {}, "du_lieu": {"cot": ["tradingDate", "o", "h", "l", "c", "v"],
                                                                    "hang": idx}})
    wj(root / "fincept_bridge" / "data" / "lk_hoso" / "AAA.json", lk_fixture())
    db = root / "fincept_bridge" / "vnstore" / "vn_store.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE nen_ngay (symbol, ngay, mo, cao, thap, dong, kl)")
    con.executemany("INSERT INTO nen_ngay VALUES (?,?,?,?,?,?,?)",
                    [("BBB", d, 10.0, 11.0, 9.0, 10.0 + i, 100.0) for i, (d, _, _) in enumerate(sessions()[:12])])
    con.commit()
    con.close()
    return {"CHB_SYSTEM_DIR": str(root), "CHB_TODAY": "2019-02-28"}


def _deny(*_a, **_k):
    raise RuntimeError("mạng bị chặn trong test")


_PATCHES = [mock.patch("socket.socket", _deny), mock.patch("socket.create_connection", _deny),
            mock.patch("socket.getaddrinfo", _deny)]


def setUpModule():
    for p in _PATCHES:
        p.start()


def tearDownModule():
    for p in _PATCHES:
        p.stop()


def strings_of(o) -> list:
    if isinstance(o, N.V):
        return [x for x in (o.text, o.note) if isinstance(x, str)]
    if isinstance(o, dict):
        return [s for k, v in o.items() if k not in ("src", "canh_bao") for s in strings_of(v)]
    if isinstance(o, (list, tuple)):
        return [s for v in o for s in strings_of(v)]
    return [o] if isinstance(o, str) else []


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="chb_cd2p_"))
        self._env = mock.patch.dict(os.environ, make_fixture(self.tmp))
        self._env.start()
        N.clear_cache()
        self.ss = sessions()
        self.D = [d for d, _, _ in self.ss]

    def tearDown(self):
        self._env.stop()
        N.clear_cache()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def w(self):
        return P.weekly_full("AAA")


class SharesTests(Fixture):
    def test_pre_steps_only_big_step_before_ts(self):
        st = P.pre_share_steps("AAA")
        self.assertEqual([(e["date"], e["inferred"]) for e in st], [(E1, True)])   # cổ tức tiền 2% bị loại
        self.assertAlmostEqual(st[0]["factor"], 2.0, places=9)

    def test_shares_series(self):
        s = P.shares_series("AAA")
        self.assertTrue(s["ok"])
        self.assertEqual((s["ts_start"], s["tier_pre"]), (TS, N.UNV))
        for d, x in zip(s["dates"], s["s"]):
            self.assertAlmostEqual(x, shares_true(d), msg=d)        # gai 28/11 bị bỏ, 2 phiên cuối điền tiếp

    def test_mult_now(self):
        for d, m in zip(self.D, P.mult_now("AAA")):
            self.assertAlmostEqual(m, mult_true(d), msg=d)

    def test_mult_at_and_shares_at_match_series(self):
        """Một hệ số cho mọi lớp (O dùng mult_at): bằng m[phiên cuối ≤ d] của weekly_full, gồm bước suy trước TS."""
        for d in self.D:
            self.assertAlmostEqual(P.mult_at("AAA", d), mult_true(d), msg=d)
        self.assertAlmostEqual(P.mult_at("AAA", "2018-10-13"), mult_true("2018-10-12"))   # thứ Bảy → phiên thứ Sáu
        self.assertAlmostEqual(P.mult_at("AAA", "2010-01-01"), 3.0)                          # trước phiên đầu: mọi sự kiện
        self.assertEqual(P.mult_at("ZZZ", "2019-01-01"), 1.0)
        s, t = P.shares_at("AAA", "2018-10-10")
        self.assertEqual((round(s), t), (1_500_000, N.UNV))                                  # trước ts_start: suy (U)
        s, t = P.shares_at("AAA", "2019-01-25")
        self.assertEqual((round(s), t), (4_500_000, N.T2))
        self.assertEqual(P.shares_at("ZZZ", "2019-01-25"), (None, None))

    def test_missing_and_vnstore(self):
        self.assertEqual(P.shares_series("ZZZ")["why"], "chưa nạp vc_lk")
        self.assertFalse(P.shares_series("BBB")["ok"])
        self.assertEqual((P.mult_now("ZZZ"), P.pre_share_steps("ZZZ")), ([], []))


class WeeklyTests(Fixture):
    def test_shape(self):
        w = self.w()
        self.assertTrue(w["ok"])
        self.assertEqual((w["base"], w["listing"], w["first_week"], w["n_weeks"]), ("vc_lk", "2018-10-01", "2018-10-01", 21))
        self.assertEqual((w["tier_px"], w["tier_conv"], w["tier_pre"], w["ts_start"]), (N.T2, N.EST, N.UNV, TS))
        self.assertNotIn("2019-02-04", [r["w"] for r in w["rows"]])          # tuần nghỉ không có dòng
        self.assertEqual([r["partial"] for r in w["rows"]], [False] * 20 + [True])
        for r in w["rows"]:
            self.assertEqual(date.fromisoformat(r["w"]).weekday(), 0)
            self.assertEqual(r["pre"], r["we"] < TS)

    def test_week_values(self):
        rows = {r["w"]: r for r in self.w()["rows"]}
        for k, px in enumerate(PATH):
            mon = (MON0 + timedelta(weeks=k)).isoformat()
            if px is None:
                continue
            ix = [i for i, d in enumerate(self.D) if mon <= d < (MON0 + timedelta(weeks=k + 1)).isoformat()]
            r = rows[mon]
            self.assertEqual((r["we"], r["c"], r["n"]), (self.D[ix[-1]], px * 1000.0, len(ix)))
            kl = [10_000.0 * (1 + i % 5) for i in ix]
            self.assertAlmostEqual(r["vol_raw"], sum(kl))
            self.assertAlmostEqual(r["vol"], sum(k * mult_true(self.D[i]) for k, i in zip(kl, ix)))

    def test_td_fo_room(self):
        rows = self.w()["rows"]
        self.assertTrue(all(r["td_val"] is None and r["td_n"] == 0 for r in rows if r["we"] < "2019-01-02"))
        r = next(r for r in rows if r["w"] == "2019-01-07")                # 09/01 không có bản ghi tự doanh
        self.assertEqual(r["td_n"], 4)
        last = rows[-1]
        self.assertEqual(last["fo_d"], self.D[-3])                          # 2 phiên cuối thiếu %NN
        self.assertAlmostEqual(last["fo"], (0.05 + 0.0001 * (len(self.D) - 3)) * 100)
        self.assertAlmostEqual(last["fol"], 49.0)
        n = len(self.D)
        for r in rows:                                                       # room: phiên cuối tuần có cả room và số cp
            ok = [i for i, d in enumerate(self.D) if r["w"] <= d <= r["we"] and d >= TS and i < n - 2 and i % 2 == 0]
            self.assertAlmostEqual(r["room"] or 0.0, 1e8 / shares_true(self.D[ok[-1]]) if ok else 0.0, msg=r["w"])

    def test_vwap_hand(self):
        w = self.w()
        r = w["rows"][-1]
        lo = N.lui_thang(r["we"], 6)
        num = den = 0.0
        for i, (d, _, adj) in enumerate(self.ss):
            if lo < d <= r["we"]:
                k = 10_000.0 * (1 + i % 5)
                num += adj * k / shares_true(d)
                den += k / shares_true(d)
        self.assertAlmostEqual(r["v6"] / (num / den), 1.0, places=12)

    def test_vnstore_and_missing(self):
        w = P.weekly_full("BBB")
        self.assertEqual((w["ok"], w["base"], w["tier_px"]), (True, "vnstore", N.UNV))
        r = w["rows"][0]
        self.assertEqual((r["vol"], r["c"]), (500.0, 14.0))
        self.assertTrue(all(r[k] is None for k in ("nn_vol", "nn_val", "td_val", "fo", "v6", "dval", "vol_raw")))
        self.assertEqual(P.weekly_full("ZZZ")["why"], "chưa nạp vc_lk")

    def test_memo_by_mtime(self):
        a = self.w()
        self.assertIs(a, self.w())
        p = self.tmp / "fincept_bridge" / "state" / "vc_lk" / "AAA" / "price-history.json"
        os.utime(p, ns=(p.stat().st_atime_ns, p.stat().st_mtime_ns + 10**9))
        self.assertIsNot(a, self.w())

    def test_cum_series(self):
        w, c = self.w(), P.cum_series("AAA")
        acc = 0.0
        for r, x in zip(w["rows"], c["nn_cum"]):
            acc += r["nn_vol"] or 0.0
            self.assertAlmostEqual(x, acc)
        first = next(i for i, r in enumerate(w["rows"]) if r["td_val"] is not None)
        self.assertTrue(all(x is None for x in c["td_cum"][:first]))
        self.assertAlmostEqual(c["td_cum"][-1], sum(r["td_val"] or 0.0 for r in w["rows"]))
        self.assertEqual(c["td_from"], "2019-01-02")

    def test_rs_weekly(self):
        rs, rows = P.rs_weekly("AAA"), self.w()["rows"]
        self.assertIsNone(rs["rs"][0])                                       # VNINDEX fixture từ 08/10
        idx = {d: 1000.0 + i for i, (d, _, _) in enumerate(self.ss) if d >= "2018-10-08"}
        self.assertAlmostEqual(rs["rs"][5], rows[5]["c"] / idx[rows[5]["we"]])
        self.assertEqual(rs["rrg"], {"goc": "Weakening", "t_cuoi": fridays(20, 21)[0], "n_tuan": 19, "tier": "EST",
                                     "src": "rrg giả"})

    def test_fft_view(self):
        f = P.fft_view("AAA")
        self.assertTrue(f["ok"])
        self.assertEqual((f["from"], f["w"][0]), (fridays(2, 3)[0], (MON0 + timedelta(weeks=2)).isoformat()))
        for i, x in enumerate(f["ma4"]):
            win = f["fw"][i - 3:i + 1] if i >= 3 else []
            if len(win) == 4 and None not in win:
                self.assertAlmostEqual(x, sum(win) / 4)
            else:
                self.assertIsNone(x)
        self.assertEqual((f["pct3y"].tier, f["pall"].tier, f["ma4_now"].tier), (N.T2, N.T2, N.EST))
        self.assertEqual(P.fft_view("ZZZ")["why"], "chưa có lk_hoso")


class ZigzagTests(Fixture):
    def test_segments(self):
        z = P.zigzag("AAA")
        segs = [(s["i0"], s["i1"], s["p0"] / 1000, s["p1"] / 1000, s["dir"], s["open"]) for s in z["segments"]]
        self.assertEqual(segs, [(0, 4, 100, 130, "len", False), (4, 8, 130, 100, "xuong", False),
                                (8, 20, 100, 115, "len", True)])
        self.assertEqual(z, P.zigzag("AAA"))
        self.assertIn("không phải pha", z["rule"])

    def test_pivots_invariants(self):
        cs = list(enumerate([100, 90, 70, 75, 95, 80, 60, 61, 90, 95, 94]))
        piv = P._zig_pivots(cs, 0.18)
        segs = list(zip(piv, piv[1:]))
        for (a, b), (c, d) in zip(segs, segs[1:]):
            self.assertNotEqual(b[1] > a[1], d[1] > c[1])
        self.assertTrue(all(abs(b[1] / a[1] - 1) >= 0.18 for a, b in segs))

    def test_segment_stats(self):
        z = P.zigzag("AAA")
        st = P.segment_stats("AAA", z["segments"])
        self.assertEqual(len(st), 3)
        s0 = st[0]
        ix = [i for i, d in enumerate(self.D) if d <= self.w()["rows"][4]["we"]]
        vol = sum(10_000.0 * (1 + i % 5) * mult_true(self.D[i]) for i in ix)
        self.assertAlmostEqual(s0["vol_w"].value, vol / 5)
        self.assertEqual((s0["vol_w"].tier, s0["nn_vol"].tier, s0["nn_val"].tier, s0["pre"]), (N.UNV, N.UNV, N.T2, True))
        self.assertTrue(s0["td_val"].can and s0["du_val"].can)
        self.assertEqual(s0["td_val"].note, "tự doanh vc_lk chỉ từ 02/01/2019")
        self.assertAlmostEqual(st[1]["d_vol_pct"].value, (st[1]["vol_w"].value / s0["vol_w"].value - 1) * 100)
        self.assertTrue(st[0]["d_vol_pct"].can)
        self.assertEqual(st[2]["td_cover"], "8/12 tuần")      # tuần 31/12 có 02-04/01


class FlowTests(Fixture):
    def test_td_only_on_records_and_residual(self):
        d0, d1 = "2019-01-02", self.D[-1]
        f = P.flow_window("AAA", d0, d1)
        ix = [i for i, d in enumerate(self.D) if d0 <= d <= d1]
        rec = {r[0]: r for r in prop_rows()}
        td = [i for i in ix if self.D[i] in rec]
        self.assertEqual(f["td_cover"], [len(td), len(ix)])
        self.assertAlmostEqual(f["td_val"].value, sum(rec[self.D[i]][2] for i in td))
        ng = [r[COLS.index("foreignNetValueTotal")] for r in ph_rows()[1:]]
        self.assertAlmostEqual(f["du_val"].value, -sum(ng[i] + rec[self.D[i]][2] for i in td))
        self.assertEqual(f["du_cover"], len(td))
        self.assertEqual((f["td_val"].tier, f["du_val"].tier, f["nn_val"].tier, f["nn_vol"].tier), (N.T2, N.EST, N.T2, N.EST))

    def test_before_2019_and_empty(self):
        f = P.flow_window("AAA", "2018-12-01", "2019-01-31")
        self.assertTrue(f["td_val"].can and f["td_vol"].can)
        self.assertEqual(f["td_val"].note, "tự doanh vc_lk chỉ từ 02/01/2019")
        self.assertFalse(P.flow_window("AAA", "2020-01-01", "2020-02-01")["ok"])
        self.assertEqual(P.flow_window("ZZZ", "2019-01-01", "2019-02-01")["why"], "chưa nạp vc_lk")
        self.assertEqual(P.flow_window("BBB", "2018-10-01", "2019-02-01")["why"], "chưa nạp vc_lk")

    def test_premium_share_split_dfo(self):
        d0, d1 = "2019-01-14", "2019-01-25"
        f = P.flow_window("AAA", d0, d1)
        rows = [dict(zip(COLS, r)) for r in ph_rows()[1:] if d0 <= r[0] <= d1]
        dv = sum(r["totalDealVolume"] for r in rows)
        dg = sum(r["totalDealValue"] for r in rows)
        mv, mg = sum(r["totalMatchVolume"] for r in rows), sum(r["totalMatchValue"] for r in rows)
        self.assertAlmostEqual(f["premium"].value, ((dg / dv) / (mg / mv) - 1) * 100)
        self.assertAlmostEqual(f["deal_share"].value, dg / (dg + mg) * 100)
        self.assertEqual(f["deal_share"].text[0].isdigit(), True)
        fo = {r[0]: r[COLS.index("foreignOwnedPercentage")] for r in ph_rows()[1:]}
        self.assertAlmostEqual(f["d_fo_pp"].value, (fo["2019-01-25"] - fo["2019-01-14"]) * 100)   # phiên cuối có số ≤ d0
        self.assertEqual(f["nn_split"].note, "chờ --day-du (mới 25 phiên có số)")
        last20 = P.flow_window("AAA", self.D[-20], self.D[-1])["nn_split"]
        self.assertAlmostEqual(last20["khop"].value / (last20["khop"].value + last20["tt"].value), 0.6)

    def test_premium_converts_volume_across_exright(self):
        """Cửa sổ cắt qua GDKHQ 07/01/2019 (thưởng ×1.5): KL quy về số cp hiện hành trước khi chia (không trộn danh nghĩa)."""
        d0, d1 = "2018-12-10", "2019-01-25"
        f = P.flow_window("AAA", d0, d1)
        rows = [dict(zip(COLS, r)) for r in ph_rows()[1:] if d0 <= r[0] <= d1]
        dv = sum(r["totalDealVolume"] * mult_true(r["tradingDate"]) for r in rows if r["totalDealVolume"] > 0)
        dg = sum(r["totalDealValue"] for r in rows)
        mv = sum(r["totalMatchVolume"] * mult_true(r["tradingDate"]) for r in rows)
        mg = sum(r["totalMatchValue"] for r in rows)
        self.assertAlmostEqual(f["premium"].value, ((dg / dv) / (mg / mv) - 1) * 100)
        raw = (dg / sum(r["totalDealVolume"] for r in rows)) / (mg / sum(r["totalMatchVolume"] for r in rows)) - 1
        self.assertNotAlmostEqual(f["premium"].value, raw * 100, places=3)             # công thức danh nghĩa cũ
        fw = P.flow_windows("AAA", "2019-02-28")
        self.assertTrue(fw["win"]["all"]["premium"].can)
        self.assertEqual(fw["win"]["all"]["premium"].note, DG.WHY_PREM_ALL)
        self.assertFalse(P.flow_window("AAA", "2018-10-01", "2019-02-28")["premium"].can)   # memo không bị sửa

    def test_windows_yearly(self):
        fw = P.flow_windows("AAA", "2019-02-28")
        self.assertEqual((fw["order"], fw["all_from"]), (["20p", "63p", "ytd", "1y", "3y", "all"], "2018-10-01"))
        self.assertEqual((fw["win"]["20p"]["n"], fw["win"]["ytd"]["d0"]), (20, "2019-01-01"))
        y = P.yearly_flows("AAA")["rows"]
        self.assertEqual([r["year"] for r in y], [2018, 2019])
        self.assertTrue(y[0]["td_val"].can)
        self.assertAlmostEqual(y[1]["td_val"].value, sum(r[2] for r in prop_rows()))
        self.assertAlmostEqual(y[0]["chg_pct"].value, (PATH[13] / PATH[0] - 1) * 100)   # 31/12/2018 thuộc tuần 13

    def test_deal_weekly_spikes(self):
        sp = P.deal_weekly_spikes("AAA", "2018-10-01", self.D[-1])
        wk = {}
        for r in ph_rows()[1:]:
            x = dict(zip(COLS, r))
            mon = (date.fromisoformat(x["tradingDate"]) - timedelta(days=date.fromisoformat(x["tradingDate"]).weekday()))
            a = wk.setdefault(mon.isoformat(), [0.0, 0.0])
            a[0] += x["totalDealValue"]
            a[1] += x["totalMatchValue"]
        dw = sorted(v[0] for v in wk.values() if v[0] > 0)
        med = (dw[len(dw) // 2] + dw[(len(dw) - 1) // 2]) / 2
        exp = [w for w, (dv, mv) in wk.items() if dv >= 5 * med and dv / (dv + mv) >= 0.2]
        self.assertEqual((sp["n_weeks"], sp["n_deal_weeks"]), (21, len(dw)))
        self.assertAlmostEqual(sp["median"].value, med)
        self.assertEqual([x["w"] for x in sp["weeks"]], sorted(exp, reverse=True))
        self.assertEqual([x["w"] for x in sp["weeks"]], ["2019-01-14"])
        self.assertIn("CÓ thoả thuận", sp["rule"])

    def test_deal_sessions_match_5(self):
        i = self.D.index(SPIKE_DAY)
        win = [{"row": "near", "start": self.D[i + 5], "end": self.D[i + 6]},
               {"row": "far", "start": self.D[i + 6], "end": self.D[i + 7]},
               {"row": "before", "start": self.D[i - 9], "end": self.D[i - 5]}]
        ds = P.deal_sessions("AAA", years=3, top=2, windows=win)
        dval = {d: dict(zip(COLS, r))["totalDealValue"] for r in ph_rows()[1:] for d in [r[0]] if d in DEAL_DAYS}
        self.assertEqual([r["date"] for r in ds["rows"]], sorted(dval, key=lambda d: -dval[d])[:2])
        self.assertEqual(ds["rows"][0]["date"], SPIKE_DAY)
        self.assertEqual(ds["rows"][0]["match"], ["near", "before"])
        self.assertAlmostEqual(ds["rows"][0]["premium"].value, 5.0)

    def test_cost_estimate(self):
        out = P.cost_estimate("AAA", [{"row": "a", "start": "2019-01-14", "end": "2019-01-16", "qty": 400_000},
                                      {"row": "b", "start": "2019-01-14", "end": "2019-01-16", "qty": 900_000},
                                      {"row": "c", "start": "2030-01-01", "end": "2030-01-02", "qty": 1}])
        raw = PATH[15] * 1000 / f_of(SPIKE_DAY) * 1.05
        self.assertEqual([x["method"] for x in out], ["tt", "khop", None])
        self.assertAlmostEqual(out[0]["price_nominal"].value, raw)
        self.assertAlmostEqual(out[0]["price"].value, raw * f_of(SPIKE_DAY))
        self.assertEqual((out[0]["price"].tier, out[0]["price_nominal"].tier), (N.EST, N.T2))
        self.assertIsNone(out[1]["price_nominal"])
        self.assertIn("giả định khớp lệnh", out[1]["price"].note)
        self.assertTrue(out[2]["price"].can)

    def test_reexport(self):
        for name in ("flow_window", "flow_windows", "yearly_flows", "deal_weekly_spikes", "deal_sessions",
                     "cost_estimate", "SPIKE_RULE"):
            self.assertIs(getattr(P, name), getattr(DG, name))
        ns: dict = {}
        exec("from chaebol_map_data_codong2_gia import *", ns)
        self.assertIn("flow_window", ns)


class PositionTests(Fixture):
    def test_position_now(self):
        p = P.position_now("AAA")
        self.assertEqual((p["fo"].asof, p["weeks"], p["listing"]), (self.D[-3], 21, "2018-10-01"))
        self.assertEqual(p["fo"].text[0].isdigit(), True)
        self.assertAlmostEqual(p["px"].value, 115_000.0)
        self.assertEqual((p["ath"].value, p["ath"].asof), (130_000.0, "2018-10-29"))
        self.assertAlmostEqual(p["vs_ath"].value, (115 / 130 - 1) * 100)
        self.assertAlmostEqual(p["room_pct"].value, 1e6 / 4.5e6 * 100)
        self.assertEqual(p["room_pct"].tier, N.EST)
        self.assertAlmostEqual(p["close_vs_vwap_day"].value, 0.0)
        self.assertFalse(P.position_now("ZZZ")["ok"])

    def test_anchored_vwap(self):
        av = P.anchored_vwap("AAA", [{"id": "m", "date": "2019-01-01", "label": "mốc"}])
        self.assertEqual([a["id"] for a in av], ["m", "ath", "low52"])
        num = den = 0.0
        for i, (d, _, adj) in enumerate(self.ss):
            if d >= "2019-01-02":
                k = 10_000.0 * (1 + i % 5)
                num, den = num + adj * k / shares_true(d), den + k / shares_true(d)
        self.assertAlmostEqual(av[0]["vwap"].value / (num / den), 1.0, places=12)
        self.assertEqual((av[0]["vwap"].tier, av[1]["vwap"].tier), (N.EST, N.UNV))     # đỉnh 29/10 trước ts_start
        self.assertEqual(av[0]["sessions"], len([d for d in self.D if d >= "2019-01-02"]))

    def test_smr(self):
        s = P.smr_view("AAA")
        self.assertEqual((s["ok"], s["why"]), (False, "chờ --day-du (mới 5 phiên có số)"))
        s = P.smr_view("AAA", min_sessions=3)
        self.assertTrue(s["ok"])
        self.assertAlmostEqual(s["rows"][-1]["smr"], (sum(120.0 + i for i in range(len(self.D) - 3, len(self.D))) / 3) / 100)

    def test_checklist(self):
        c = P.checklist("AAA", insider_recent_n=2)
        st = {x["id"]: x["state"] for x in c["items"]}
        self.assertEqual(set(st), {"nn_ban_4p", "kl_gap_2x", "tren_3vwap", "duoi_3vwap", "noi_bo_30n", "fft_can",
                                   "fft_cao", "tt_4t", "fo_20p"})
        self.assertTrue(set(st.values()) <= {"dat", "chua", "can"})
        self.assertEqual((st["nn_ban_4p"], st["noi_bo_30n"], st["fft_can"], st["fft_cao"]), ("dat", "dat", "dat", "chua"))
        self.assertEqual(P.checklist("AAA")["items"][0]["state"], "can")
        none = P.checklist("ZZZ")
        self.assertEqual({x["state"] for x in none["items"]}, {"can"})
        for s in strings_of(c) + strings_of(none):
            self.assertIsNone(FORBIDDEN.search(s), s)

    def test_price_summary(self):
        s = P.price_summary("AAA", "2019-02-28")
        self.assertEqual((s["weeks"], s["den"]), (21, self.D[-1]))
        self.assertEqual((s["fft_pct3y"].value, s["fft_pct3y"].tier), (26, N.T2))
        self.assertEqual(s["deal_spikes_52w"].value, 1)
        z = P.price_summary("ZZZ", "2019-02-28")
        self.assertTrue(z["weeks"] is None and z["d_fo_1y_pp"].can and z["fft_pall"].can)


class DespikeTests(unittest.TestCase):
    """_despike_fo: đoạn ≤ 10 phiên lệch > 3 điểm % so mức CẢ hai đoạn dài kề (cùng phía) là gai vendor."""

    def test_alternation_and_single_spike(self):
        lvl = [15.2] * 12
        fo = lvl + [25.77, 15.25, 25.79, 25.79] + [15.25] * 12 + [56.4] + [15.3] * 11
        fol = [29.0] * len(fo)
        a, b, drop = P._despike_fo(fo, fol)
        self.assertEqual(drop, [12, 14, 15, 28])          # 15.25 giữa hai gai (đúng mức) được giữ
        self.assertEqual((a[13], a[12], b[12]), (15.25, None, None))
        self.assertEqual(max(x for x in a if x is not None), 15.3)
        self.assertEqual(fo[12], 25.77)                    # không sửa đầu vào
        vic09 = [5.0] * 12 + [24.6] * 8 + [4.1] * 12          # VIC 12/2009: 8 phiên +20 điểm khi FOL ghi 49 thay 29
        self.assertEqual(P._despike_fo(vic09, [49.0] * len(vic09))[2], list(range(12, 20)))

    def test_real_moves_kept(self):
        step = [10.0] * 11 + [14.0] * 2 + [18.0] * 11        # tăng bậc thật (không phải cực trị so hai phía)
        self.assertEqual(P._despike_fo(step, [49.0] * len(step))[2], [])
        tail = [10.0] * 11 + [20.0] * 3                       # gai ở cuối chuỗi: không có đoạn dài phía sau → giữ
        self.assertEqual(P._despike_fo(tail, [49.0] * len(tail))[2], [])
        gaps = [10.0, None] * 8 + [10.1, 10.2, 10.0, 49.0, None] + [10.1, 10.0, 10.2] * 4
        self.assertEqual(P._despike_fo(gaps, [49.0] * len(gaps))[2], [19])   # phiên trống không cắt đoạn


class StaticTests(unittest.TestCase):
    FILES = ("chaebol_map_data_codong2_gia.py", "chaebol_map_data_codong2_dong.py")

    def test_source_rules(self):
        for name in self.FILES:
            src = (HERE / name).read_text(encoding="utf-8")
            self.assertLessEqual(len(src.splitlines()), 800, name)
            self.assertIsNone(re.search(r"^\s*(import|from)\s+(socket|urllib|http|ssl|requests)\b", src, re.M), name)
            self.assertNotIn("vc_lk_fetch", src)
            self.assertIsNone(re.search(r"open\([^)]*['\"][wax+]", src), name)
            self.assertNotIn(chr(0x2014), src)          # gạch dài
            self.assertNotIn(chr(0x2013), src)          # gạch ngắn
            self.assertIsNone(re.search(r"import\s+chaebol_map_(tab|data_codong2\b)|chaebol_map_data_codong2 import", src))
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.FunctionDef):
                    self.assertLessEqual(node.end_lineno - node.lineno + 1, 50, f"{name}:{node.name}")
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assertIsNone(FORBIDDEN.search(node.value), f"{name}: {node.value[:60]}")


# ───────────────────────────── kho thật (chỉ đọc) ─────────────────────────────

def _raw(tk: str, ep: str) -> list:
    d = json.loads((REAL_SYS / "fincept_bridge" / "state" / "vc_lk" / tk / f"{ep}.json").read_text(encoding="utf-8"))
    cot = d["du_lieu"]["cot"]
    return [dict(zip(cot, r)) for r in d["du_lieu"]["hang"]]


@unittest.skipUnless((REAL_SYS / "fincept_bridge" / "state" / "vc_lk" / "VIC" / "price-history.json").exists(),
                     "không có kho thật")
class RealStore(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict(os.environ, {**{k: v for k, v in os.environ.items() if k not in ENV_KEYS},
                                                 "CHB_TODAY": "2026-10-05"}, clear=True)
        self._env.start()
        N.clear_cache()

    def tearDown(self):
        self._env.stop()
        N.clear_cache()

    def test_weekly_history_f3_f5(self):
        w = P.weekly_full("VIC")
        self.assertEqual((w["first_week"], w["listing"], w["ts_start"]), ("2007-09-17", "2007-09-19", "2010-12-21"))
        self.assertEqual(sum(1 for r in w["rows"] if r["we"] <= "2026-10-02"), 982)
        exp = {"2008-01-22": 1.4493, "2009-07-02": 1.5687, "2010-05-07": 1.7731}
        self.assertEqual({e["date"]: round(e["factor"], 4) for e in w["pre_steps"]}, exp)
        self.assertTrue(all(r["pre"] == (r["we"] < "2010-12-21") for r in w["rows"]))
        self.assertEqual([e["date"] for e in P.pre_share_steps("HPG")], ["2008-07-11", "2010-04-27"])
        ree = P.weekly_full("REE")
        self.assertEqual((ree["first_week"], ree["listing"]), ("2000-07-24", "2000-07-28"))
        self.assertEqual(sum(1 for r in ree["rows"] if r["we"] <= "2026-10-02"), 1348)
        self.assertEqual(sum(1 for r in P.weekly_full("GEL")["rows"] if r["we"] <= "2026-10-02"), 34)
        self.assertEqual(P.weekly_full("FOX")["why"], "chưa nạp vc_lk")
        plc = P.weekly_full("PLC")
        self.assertEqual((plc["base"], plc["tier_px"]), ("vnstore", N.UNV))
        self.assertTrue(all(r["nn_vol"] is None and r["nn_val"] is None for r in plc["rows"]))

    def test_msr_adj_fix(self):
        w = P.weekly_full("MSR")
        self.assertEqual(w["fix"]["brk"], "2026-09-16")
        raw = {r["tradingDate"][:10]: r["closePrice"] for r in _raw("MSR", "price-history")}
        after = [r for r in w["rows"] if r["we"] >= "2026-09-16"]
        self.assertTrue(after)
        for r in after:
            self.assertEqual(r["c"], raw[r["we"]])

    def test_vwap_v24_hand_and_existing(self):
        import chaebol_map_data_gia as G
        w, s = P.weekly_full("VIC"), P.shares_series("VIC")
        r = w["rows"][-1]
        rows = _raw("VIC", "price-history")
        lo = N.lui_thang(r["we"], 24)
        sd = dict(zip(s["dates"], s["s"]))
        num = den = 0.0
        for x in rows:
            d, c, k = x["tradingDate"][:10], x["closePriceAdjusted"], x["totalMatchVolume"]
            if lo < d <= r["we"] and N._finite(c) and N._finite(k) and k > 0:
                num, den = num + c * k / sd[d], den + k / sd[d]
        self.assertLess(abs(r["v24"] / (num / den) - 1), 1e-9)
        ph = G.price_history("VIC")
        self.assertLess(abs(r["v24"] / G._vwap_at(ph, ph.at(r["we"]), 24) - 1), 1e-12)
        av = P.anchored_vwap("VIC", [{"id": "x", "date": "2025-01-02", "label": "x"}], auto=False)[0]
        num = den = 0.0
        for x in rows:
            d, c, k = x["tradingDate"][:10], x["closePriceAdjusted"], x["totalMatchVolume"]
            if d >= "2025-01-02" and N._finite(c) and N._finite(k) and k > 0:
                num, den = num + c * k / sd[d], den + k / sd[d]
        self.assertLess(abs(av["vwap"].value / (num / den) - 1), 1e-9)

    def test_zigzag_vic(self):
        z = P.zigzag("VIC")
        self.assertEqual(z, P.zigzag("VIC"))
        segs = z["segments"]
        done = [s for s in segs if not s["open"]]
        self.assertTrue(segs[-1]["open"] and all(not s["open"] for s in segs[:-1]))
        self.assertTrue(all(abs(s["chg_pct"]) >= 18 for s in done))
        self.assertTrue(all(a["dir"] != b["dir"] for a, b in zip(done, done[1:])))
        self.assertEqual(len(P.segment_stats("VIC", segs)), len(segs))

    def test_flow_vic(self):
        f = P.flow_window("VIC", "2023-10-03", "2026-10-02")
        prop = {x["tradingDate"][:10] for x in _raw("VIC", "proprietary-history")}
        days = [x["tradingDate"][:10] for x in _raw("VIC", "price-history") if "2023-10-03" <= x["tradingDate"][:10] <= "2026-10-02"]
        self.assertEqual(f["td_cover"], [sum(1 for d in set(days) if d in prop), len(set(days))])
        self.assertLessEqual(f["du_cover"], f["td_cover"][0])
        rows = [x for x in _raw("VIC", "price-history") if "2025-01-01" <= x["tradingDate"][:10] <= "2025-12-31"]
        g = P.flow_window("VIC", "2025-01-01", "2025-12-31")
        m = {d: x for d, x in zip(P._base("VIC")["dates"], P.mult_now("VIC"))}     # KL quy về số cp hiện hành
        mt = lambda x: m[x["tradingDate"][:10]]  # noqa: E731
        dv = sum(x["totalDealVolume"] * mt(x) for x in rows if (x["totalDealVolume"] or 0) > 0)
        dg = sum(x["totalDealValue"] or 0 for x in rows)
        mv = sum(x["totalMatchVolume"] * mt(x) for x in rows if (x["totalMatchVolume"] or 0) > 0)
        mg = sum(x["totalMatchValue"] for x in rows if (x["totalMatchVolume"] or 0) > 0)
        self.assertLess(abs(g["premium"].value - ((dg / dv) / (mg / mv) - 1) * 100), 1e-9)
        self.assertIn("quy về số cp hiện hành", g["premium"].note)
        sp = sum(1 for x in rows if x.get("foreignNetValueMatched") is not None)
        if sp < 0.9 * len(rows):
            self.assertIn("chờ --day-du", g["nn_split"].note)

    def test_deal_spikes_f21(self):
        sp = P.deal_weekly_spikes("VIC", "2023-10-02", "2026-10-02")
        self.assertEqual((sp["n_weeks"], sp["n_deal_weeks"], len(sp["weeks"])), (155, 148, 27))
        self.assertLess(abs(sp["median"].value / 1e9 - 322.84), 0.01)

    def test_msn_sk_f9(self):
        out = P.cost_estimate("MSN", [{"row": "sk", "start": "2018-10-02", "end": "2018-10-02", "qty": 109_899_932}])[0]
        self.assertEqual((out["method"], out["price_nominal"].value), ("tt", 100_000.0))
        ds = P.deal_sessions("MSN", years=10, top=10, windows=[{"row": "sk", "start": "2018-10-08", "end": "2018-10-08"}])
        row = next(r for r in ds["rows"] if r["date"] == "2018-10-02")
        self.assertEqual((row["dvol"], row["match"]), (109_899_932.0, ["sk"]))

    def test_position_fo_f24(self):
        p = P.position_now("VIC")
        rows = _raw("VIC", "price-history")
        exp = max(x["tradingDate"][:10] for x in rows if x["foreignOwnedPercentage"] is not None)
        self.assertEqual(p["fo"].asof, exp)          # phiên cuối CÓ %NN (không phải phiên cuối của chuỗi)
        last = max(rows, key=lambda x: x["tradingDate"])
        if last["foreignOwnedPercentage"] is None:
            self.assertLess(p["fo"].asof, last["tradingDate"][:10])

    def test_fo_peak_without_vendor_spikes(self):
        """Đỉnh %NN không lấy gai vendor (VIC 25.79% 05/07/2011, FPT 56.41% 02/07/2010 trên FOL 49%, MBB 27.7%)."""
        v, f, m = (P.position_now(t)["fo_peak"] for t in ("VIC", "FPT", "MBB"))
        self.assertNotEqual(v.asof, "2011-07-05")
        self.assertLess(v.value, 25.0)
        self.assertLessEqual(f.value, 49.5)
        self.assertLess(m.value, 27.0)
        self.assertIn("gai vendor", f.note)
        self.assertIn("2010-07-02", P._base("FPT")["fo_spikes"])

    def test_fft_vic(self):
        f = P.fft_view("VIC")
        self.assertEqual(f["from"], "2014-06-06")
        self.assertGreaterEqual(len(f["t"]), 636)
        for i in range(3, len(f["fw"])):
            if None not in f["fw"][i - 3:i + 1]:
                self.assertAlmostEqual(f["ma4"][i], sum(f["fw"][i - 3:i + 1]) / 4)
        hs = json.loads((REAL_SYS / "fincept_bridge" / "data" / "lk_hoso" / "VIC.json").read_text(encoding="utf-8"))
        self.assertEqual((f["pct3y"].tier, f["pall"].tier), (hs["fft"]["pct3y"]["b"], hs["fft"]["pall"]["b"]))

    def test_smr_vcb_checklist(self):
        n = sum(1 for x in _raw("VCB", "price-history")
                if x.get("averageBuyTradeVolume") is not None and x.get("averageSellTradeVolume"))
        s = P.smr_view("VCB")
        if n < 120:
            self.assertEqual((s["ok"], s["why"]), (False, f"chờ --day-du (mới {n} phiên có số)"))
        for tk in ("VIC", "MBB", "FOX", "PLC", "GEL"):
            c = P.checklist(tk)
            self.assertTrue({x["state"] for x in c["items"]} <= {"dat", "chua", "can"})
            for s in strings_of(c):
                self.assertIsNone(FORBIDDEN.search(s), s)

    def test_universe_109_perf(self):
        import chaebol_map_data_langkinh as L
        import chaebol_map_data_tailieu as T
        import chaebol_map_data_vciq as Q
        u = Q.universe(T.v21(), L.basket("VN30").value or [])
        self.assertGreaterEqual(len(u), 100)
        t0 = time.time()
        for tk in u:
            z = P.zigzag(tk)
            P.segment_stats(tk, z["segments"])
            P.flow_windows(tk, "2026-10-05"), P.yearly_flows(tk), P.position_now(tk), P.checklist(tk)
            P.rs_weekly(tk), P.fft_view(tk), P.cum_series(tk), P.anchored_vwap(tk, []), P.deal_sessions(tk)
            ps = P.price_summary(tk, "2026-10-05")
            self.assertTrue(all(isinstance(ps[k], N.V) for k in ("d_fo_1y_pp", "deal_spikes_52w", "fft_pct3y")))
        t1 = time.time() - t0
        t0 = time.time()
        for tk in u:
            P.weekly_full(tk), P.flow_windows(tk, "2026-10-05"), P.zigzag(tk)
        self.assertLess(t1, 30.0)
        self.assertLess(time.time() - t0, 1.0)                               # lần hai: memo


if __name__ == "__main__":
    unittest.main(verbosity=1)
