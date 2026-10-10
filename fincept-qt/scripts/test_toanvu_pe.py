#!/usr/bin/env python3
"""Test cho toanvu_pe.py (stdlib) + số vàng tái lập của toanvu_pe_build.py (đọc JSON đã dựng; bỏ qua nếu chưa dựng)."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import toanvu_pe as tv  # noqa: E402

HAS_DATA = (tv.STATE / "tong_quan.json").exists()


class TestHelpers(unittest.TestCase):
    def test_vn_format(self):
        self.assertEqual(tv.vn(1234.5, 1), "1.234,5")
        self.assertEqual(tv.vn(-0.5, 2), "−0,50")
        self.assertEqual(tv.vn(0.0, 2, sign=True), "0,00")
        self.assertEqual(tv.vn(2.97, 2, sign=True), "+2,97")
        self.assertEqual(tv.vn(None), "")
        self.assertEqual(tv.vn(float("nan")), "")

    def test_pct_rank_matches_pandas_max(self):
        # pandas: Series([3,1,2,2]).rank(pct=True, method="max") -> [1.0, .25, .75, .75]
        self.assertAlmostEqual(tv.pct_rank_le([3, 1, 2, 2], 2), 75.0)
        self.assertAlmostEqual(tv.pct_rank_le([3, 1, 2, 5], 5), 100.0)
        self.assertAlmostEqual(tv.pct_rank_le([None, 4, 1], 1), 50.0)

    def test_iso_ms_and_ddmm(self):
        self.assertEqual(tv.iso_ms("1970-01-02"), 86400000)
        self.assertIsNone(tv.iso_ms("x"))
        self.assertEqual(tv.ddmm("2026-09-07"), "07/09/2026")

    def test_chart_ey_inserts_crossing(self):
        p = {"chuoi": {"x": ["2020-01-03", "2020-01-10"], "ey": [10.0, 6.0], "ls": [8.0, 8.0]}}
        b = tv.chart_ey(p)
        self.assertEqual(len(b["x"]), 3)                  # đã chèn điểm cắt
        pos_hi = b["series"][0]["y_hi"]
        neg_lo = b["series"][1]["y_lo"]
        self.assertIsNotNone(pos_hi[1])                    # điểm cắt thuộc cả hai dải
        self.assertIsNotNone(neg_lo[1])
        self.assertAlmostEqual(b["series"][3]["y"][1], 8.0)

    def test_bad_ticker_and_usage(self):
        self.assertEqual(self._run(["x", "ma", "--ma", "../etc"])["error_code"], "BAD_TICKER")
        self.assertEqual(self._run(["x", "foo"])["error_code"], "USAGE")
        self.assertEqual(self._run(["x"])["error_code"], "USAGE")

    @staticmethod
    def _run(argv):
        try:
            return tv.run(argv)
        except tv.TvError as e:
            return {"error_code": e.code}


def check_ext(tc, charts):
    """Hợp đồng khối biểu đồ mở rộng (VnChartsExt): cot = nhan/series cùng độ dài; xy = x/y cùng độ dài, có trục."""
    for c in charts:
        b = c["block"]
        tc.assertIn(b["loai"], ("cot", "xy"), c["tieu_de"])
        if b["loai"] == "cot":
            n = len(b["nhan"])
            tc.assertGreater(n, 0, c["tieu_de"])
            if "nhan_phu" in b:
                tc.assertEqual(len(b["nhan_phu"]), n, c["tieu_de"])
            for sr in b["series"]:
                tc.assertEqual(len(sr["y"]), n, (c["tieu_de"], sr["name"]))
                if "mau_tung" in sr:
                    tc.assertEqual(len(sr["mau_tung"]), n, (c["tieu_de"], sr["name"]))
        else:
            tc.assertIn("truc_x", b)
            tc.assertIn("truc_y", b)
            for sr in b["series"]:
                tc.assertEqual(len(sr["x"]), len(sr["y"]), (c["tieu_de"], sr["name"]))
                if "nhan" in sr:
                    tc.assertEqual(len(sr["nhan"]), len(sr["x"]), (c["tieu_de"], sr["name"]))


@unittest.skipUnless(HAS_DATA, "chưa dựng dữ liệu toanvu_pe")
class TestPages(unittest.TestCase):
    def cli(self, *args):
        out = subprocess.run([sys.executable, str(HERE / "toanvu_pe.py"), *args], capture_output=True, check=True)
        return json.loads(out.stdout.decode("utf-8"))

    def test_overview_contract(self):
        d = self.cli("overview")
        self.assertNotIn("error", d)
        secs = d["trang"]["sections"]
        self.assertEqual(secs[0]["khoi"][0]["kieu"], "cong")
        self.assertTrue(secs[0]["khoi"][0]["dong"].startswith("CỔNG"))
        ids = [x["id"] for x in secs]
        self.assertLess(ids.index("pp"), ids.index("A") if "A" in ids else len(ids))   # phương pháp đứng trước bảng số
        if "dochieu" in ids:
            self.assertEqual(ids[1], "dochieu")               # đọc hiểu nhanh ngay sau CỔNG
        self.assertGreater(len(d["meta"]["ds_ma"]), 300)
        ro = [x["ma"] for x in d["meta"]["ds_ma"] if x["ma"] in tv.SCOPES]
        self.assertEqual(ro, [x["ma"] for x in d["meta"]["ds_ma"][:len(ro)]])      # trang rổ đứng đầu danh sách gợi ý
        self.assertEqual(len(d["csv"]["rows"]), len(d["meta"]["ds_ma"]) - len(ro))
        kinds = {b["kieu"] for s in secs for b in s["khoi"]}
        self.assertTrue(kinds <= {"cong", "doan", "o_so", "bang", "the", "danh_sach", "trich", "bieu_do", "canh_bao", "chips"})

    def test_ticker_page(self):
        d = self.cli("ma", "--ma", "vpb")
        self.assertEqual(d["meta"]["ma"], "VPB")
        ids = [s["id"] for s in d["trang"]["sections"]]
        self.assertEqual(ids[0], "cong")
        self.assertLess(ids.index("pp"), ids.index("ma"))
        if "dochieu" in ids:
            self.assertEqual(ids[1:3], ["dochieu", "thuatngu"])
            dh = next(x for x in d["trang"]["sections"] if x["id"] == "dochieu")
            txt = json.dumps(dh, ensure_ascii=False)
            self.assertNotRegex(txt, r"\{(ma|gia|pe|pct|ls|nguong|pe_nguong|gia_nguong|ey|erp|pe_fair|trang_thai)\}")
            self.assertIn("Hit", dh["khoi"][1]["the"][0]["tieu_de"])          # câu hỏi đầu gỡ nhầm "lãi suất Hit"
            self.assertIn("VPB", txt)                                         # ví dụ điền số của chính mã đang xem
        if (tv.STATE / "sau" / "VPB.json").exists():                 # lớp sâu nối sau trang gốc
            for sid in ("pha", "hhpma", "xacsuat", "bangchungma", "hoidong"):
                self.assertIn(sid, ids)
        charts = [b for s in d["trang"]["sections"] for b in s["khoi"] if b["kieu"] == "bieu_do"]
        line = [c for c in charts if "loai" not in c["block"]]
        self.assertGreaterEqual(len(line), 3)
        check_ext(self, [c for c in charts if "loai" in c["block"]])
        for c in line:
            n = len(c["block"]["x"])
            for s in c["block"]["series"]:
                for key in ("y", "y_lo", "y_hi"):
                    if key in s:
                        self.assertEqual(len(s[key]), n, (c["tieu_de"], s["name"], key))
            for a in c["block"].get("annotations", []):
                for key in ("x", "x0", "x1"):
                    if key in a:
                        self.assertIsInstance(a[key], int)     # chú thích phải là epoch ms

    def test_scope_pages(self):
        for code in tv.SCOPES:
            if not (tv.STATE / "ro" / f"{code}.json").exists():
                continue
            d = self.cli("ma", "--ma", code.lower())
            self.assertNotIn("error", d, code)
            self.assertEqual(d["meta"]["che_do"], "ro")
            secs = d["trang"]["sections"]
            sid = [s["id"] for s in secs]
            self.assertEqual(sid[0], "cong")
            self.assertLess(sid.index("pp"), sid.index("vitri"))
            for s_ in secs:                                                   # mỗi mục có hướng dẫn thì mở bằng "Cách đọc"
                if s_["id"] in ("vitri", "chart2", "erpzone", "chart1", "rank", "regime", "signals", "vimo", "bangchung") and "dochieu" in sid:
                    self.assertTrue(s_["khoi"][0].get("text", "").startswith("Cách đọc"), (code, s_["id"]))
            ids = {s["id"] for s in secs}
            for sid in ("chart2", "erpzone", "chart1", "rank", "regime", "signals", "vimo", "bangchung", "hoidong"):
                self.assertIn(sid, ids, code)
            charts = [b for s in secs for b in s["khoi"] if b["kieu"] == "bieu_do"]
            check_ext(self, [c for c in charts if "loai" in c["block"]])
            for c in charts:
                if "loai" in c["block"]:
                    continue
                n = len(c["block"]["x"])
                for sr in c["block"]["series"]:
                    for key in ("y", "y_lo", "y_hi"):
                        if key in sr:
                            self.assertEqual(len(sr[key]), n, (code, c["tieu_de"], sr["name"], key))

    def test_missing_ticker(self):
        d = self.cli("ma", "--ma", "ZZZ")
        self.assertEqual(d["error_code"], "NO_TICKER")


@unittest.skipUnless(HAS_DATA, "chưa dựng dữ liệu toanvu_pe")
class TestGoldenReplication(unittest.TestCase):
    """Số Toàn Vũ in (SS-T3) mà luật tái lập phải trả lại đúng (cắt 07/09/2026)."""

    def ma(self, tk):
        return json.loads((tv.STATE / "ma" / f"{tk}.json").read_text(encoding="utf-8"))

    def test_vpb_exact(self):
        t = self.ma("VPB")["tai_lap_0709"]
        self.assertEqual(t["n"], 871)
        self.assertAlmostEqual(t["hit"], 60.5, places=1)
        self.assertAlmostEqual(t["alpha"], 1.11, places=2)
        self.assertAlmostEqual(t["pct_0709"], 15.2, places=1)

    def test_watchlist_pct_0709(self):
        # Bản gốc in percentile "hiện tại" theo đếm ≤ (le/250); luật dùng rank(pct=True) hạng trung bình.
        # Hai cách chỉ lệch khi P/E trùng giá trị (PVP: 12,4 vs 12,0), nên cho dung sai 0,5 điểm.
        for tk, v in {"GEE": 0.4, "PVP": 12.4, "MWG": 4.4, "HDB": 16.8, "FRT": 12.0, "HAH": 9.6, "PVT": 12.4}.items():
            self.assertLessEqual(abs(self.ma(tk)["tai_lap_0709"]["pct_0709"] - v), 0.5, msg=tk)

    def test_ls_bug_and_market_pe(self):
        t = json.loads((tv.STATE / "tong_quan.json").read_text(encoding="utf-8"))
        fi = t["nguon"]["fiinprox"]
        self.assertAlmostEqual(fi["cu_nhat"]["ls"], 11.78, places=2)      # số "hiện tại" của bản gốc
        self.assertEqual(fi["dong_cuoi_tep"], fi["cu_nhat"])               # nằm ở dòng cuối tệp
        self.assertAlmostEqual(t["nguong_hien_tai"], 29.6, places=1)
        pe0 = t["pe_thi_truong"][0]
        self.assertEqual(pe0["ngay"], "2026-09-07")
        self.assertAlmostEqual(pe0["erp_harm_bo_pe_tren40"], 2.97, places=2)  # = ERP Toàn Vũ in
        self.assertGreater(t["tai_lap"]["spearman"], 0.85)


class TestSauHelpers(unittest.TestCase):
    """Hàm thuần của lớp sâu (cần pandas; bỏ qua nếu môi trường app không có)."""

    @classmethod
    def setUpClass(cls):
        try:
            import toanvu_pe_sau as S
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"không nạp được toanvu_pe_sau: {exc}")
        cls.S = S

    def test_zigzag_turns_at_25pct(self):
        import pandas as pd
        px = pd.Series([100, 110, 130, 120, 95, 90, 100, 120, 125, 126], index=pd.date_range("2020-01-03", periods=10, freq="W-FRI"))
        piv = self.S.zigzag(px)   # đỉnh 130, đáy 90 (−31%), điểm cuối là pha đang chạy
        self.assertEqual([round(p) for _, p in piv], [100, 130, 90, 126])

    def test_wilson_and_vnum(self):
        lo, hi = self.S.wilson(5, 10)
        self.assertTrue(lo < 50 < hi)
        self.assertEqual(self.S.wilson(0, 0), (None, None))
        self.assertEqual(self.S.vnum(-1.104, 2, True), "\u22121,10")
        self.assertEqual(self.S.vnum(12932, 0), "12.932")

    def test_evidence_row_labels(self):
        cur = {"pct": 3, "nguong": 29.6, "erp": 5.8}
        hp = {"thuoc_do": "pb", "reliable": True, "sigma": -1.1, "zone": "RẺ (<−1σ)", "band": {"cheap2": 12932}}
        r = self.S.evidence_row("HPG", "x", cur, {"n_do": 47, "xs_tb": 2.8, "p_xs": 0.23}, hp, 64.0, 3.3e7, "", 8.44e9)
        self.assertEqual(r["nhan"], "Hội tụ mạnh")
        self.assertIn("12.932", r["diem_gay"])
        self.assertAlmostEqual(r["nb12_pct"], 0.391, places=2)
        hp_bad = dict(hp, reliable=False)
        r2 = self.S.evidence_row("X", "x", {"pct": 80, "nguong": 29.6, "erp": -1}, None, hp_bad, -5, None, "", None)
        self.assertEqual(r2["nhan"], "Ngược chiều")

    def test_deal_label(self):
        S = self.S
        # AST 14/09/2026: thoả thuận đúng bằng KL lệnh ở phiên hoàn tất → giá bình quân thoả thuận
        px = {"2026-09-14": (29767.0, 14927160.0, 1052846865720.0, 63700.0, 54e6)}
        self.assertEqual(S.deal_label(px, "2026-09-14", "2026-09-14", 14927160, 14927160, {}), ("thoả thuận", 70532))
        # khối nhiều phiên: KL vượt hẳn khớp lệnh cửa sổ, thoả thuận cả cửa sổ phủ đủ
        px = {"2026-07-21": (1e5, 5e7, 5e11, 1e4, 0), "2026-07-22": (1e5, 5e7, 5e11, 1e4, 0), "2026-07-23": (1e5, 4.8e7, 4.8e11, 1e4, 0)}
        self.assertEqual(S.deal_label(px, "2026-07-21", "2026-07-23", 1.48e8, 1.48e8, {})[0], "thoả thuận")
        # lô ESOP tròn nhỏ: phiên thoả thuận trùng KL nhưng KHÔNG phải ngày hoàn tất, khớp lệnh dồi dào → không gọi thoả thuận
        px = {"2026-07-30": (1e6, 40000.0, 3.156e9, 76400.0, 0), "2026-07-31": (1e6, 0.0, 0.0, 76400.0, 0)}
        self.assertEqual(S.deal_label(px, "2026-07-24", "2026-07-31", 40000, 40000, {})[0], "khớp lệnh")

    def _rows(self, insider, events=(), price=None, details=None):
        data = {"insider-transaction": list(insider), "events-v2": list(events), "events-all": [],
                "price-history": price or [], "details": details or []}
        return lambda tk, ep: data.get(ep, [])

    @staticmethod
    def _r(ten, kl, end, start=None, st="Done", act=None, bef=None, aft=None, org=False, reg=0.0, own=None):
        return {"traderNameVi": None if org else ten, "traderOrganNameVi": ten if org else None, "shareAcquire": kl,
                "tradeStatusEn": st, "endDate": end + "T00:00:00", "startDate": (start or end) + "T00:00:00",
                "publicDate": end + "T00:00:00", "eventCode": "DDINS" if org else "DDIND", "shareRegister": reg,
                "actionTypeCode": act or ("B" if kl > 0 else "S"), "shareBeforeTrade": bef, "shareAfterTrade": aft,
                "ownershipAfterTrade": own}

    def test_insider_transfer_pairs_only_open_registrations(self):
        import pandas as pd
        from unittest import mock
        S, r = self.S, self._r
        ins = [r("Sojitz", 14927160.0, "2026-09-14", org=True),
               r("Penm IV", 0.0, "2026-10-10", "2026-09-11", st="Registration", act="S", org=True, reg=9527160.0),
               r("Stic", 0.0, "2026-10-10", "2026-09-11", st="Registration", act="S", org=True, reg=5400000.0)]
        with mock.patch.object(S, "vc_rows", self._rows(ins)):
            out = S.insider_rows("AST", [], 54e6, pd.Timestamp("2025-10-05"))
        self.assertTrue(out[0]["nguon"].startswith("chuyển nội bộ"))
        # phía bán đã báo kết quả (dòng Đăng ký cũ vẫn còn) → không ghép nữa, hai chân tự triệt tiêu
        ins += [r("Penm IV", -9527160.0, "2026-09-14", org=True), r("Stic", -5400000.0, "2026-09-14", org=True)]
        with mock.patch.object(S, "vc_rows", self._rows(ins)):
            out = S.insider_rows("AST", [], 54e6, pd.Timestamp("2025-10-05"))
        self.assertTrue(all(not x["nguon"] for x in out))
        self.assertEqual(sum(x["kl"] for x in out), 0.0)

    def test_insider_issue_tags(self):
        import pandas as pd
        from unittest import mock
        S, r = self.S, self._r
        iss = [{"d": pd.Timestamp("2026-06-24"), "loai": "ESOP", "ty_le": 0.02, "tieu_de": ""},
               {"d": pd.Timestamp("2026-02-11"), "loai": "chào bán", "ty_le": 0.18, "tieu_de": ""}]
        ins = [r("SCIC", 500000.0, "2026-05-15", org=True),            # tổ chức: không nhận cp ESOP
               r("Nguyễn A", 30000.0, "2026-06-30"),                    # cá nhân, trong đợt ESOP
               r("Quỹ X", 100000.0, "2026-02-01", org=True),           # mua 10 ngày TRƯỚC đợt chào bán
               r("Ngô Thu Thuý", 6300000.0, "2026-05-19", bef=64985464.0, aft=71285464.0),
               r("Ngô Thu Thúy", 6300000.0, "2026-05-19", bef=64985464.0, aft=71285464.0)]   # cùng lệnh, khác cách đặt dấu
        with mock.patch.object(S, "vc_rows", self._rows(ins)):
            out = {x["ten"]: x for x in S.insider_rows("X", iss, 1e8, pd.Timestamp("2025-10-05"))}
        self.assertIsNone(out["SCIC"]["nguon"])
        self.assertEqual(out["Nguyễn A"]["nguon"], "ESOP")
        self.assertIsNone(out["Quỹ X"]["nguon"])
        self.assertEqual(sum(1 for t in out if t.startswith("Ngô Thu")), 1)

    def test_dinh_chinh_claims(self):
        import toanvu_pe_dinh_chinh as D
        self.assertEqual(D.claims_12m("Nội bộ mua ròng +1,2% số cp trong khi khối ngoại bán ròng 0,8%."), [1.2])
        self.assertEqual(D.claims_12m("Ngưỡng nội bộ ròng ±0,1% số cp."), [])
        self.assertEqual(D.claims_12m("nội bộ ròng 12 tháng −0,17% số cp (FACT-T2)."), [-0.17])
        self.assertEqual(D.claims_12m("Pha 2016 tới nay có nội bộ ròng +16,27% số cp."), [])
        self.assertTrue(D.lech(27.64, 0.0) and D.lech(-0.33, -1.328) and not D.lech(18.55, 17.02))
        self.assertEqual(D.vnf(-0.003), "0,00")


if __name__ == "__main__":
    unittest.main(verbosity=1)
