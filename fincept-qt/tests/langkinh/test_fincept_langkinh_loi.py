#!/usr/bin/env python3
"""
Kiểm đường lỗi, dữ liệu thiếu/hỏng, schema cũ của bridge và định dạng của fincept_langkinh.py (stdlib unittest).
Chạy:  <python> -m unittest discover -s tests/langkinh -v      (từ thư mục fincept-qt)
"""
import math
import os
import unittest

from lk_nen import (B, CT, L, NOTE_DUNG, Q2_DUNG, VIEWS, Nen, bo_khoa_moi, bo_khoa_moi_cd, chay, chu)


class TestDuongLoi(Nen):
    def test_thieu_tep_chinh(self):
        d = self.ban_sao(bo=("fft_langkinh.json",))
        for v in VIEWS + ["chuoi"]:
            with self.subTest(view=v):
                o = chay(d, v)
                if v == "phuongphap":  # chữ tĩnh — vẫn hiện, CỔNG dừng
                    self.kiem_thanh_cong(o, v, "VN30")
                    self.assertEqual(o["cong"]["muc"], "dung")
                    self.assertIn("CẦN DATA", o["cong"]["dong"])
                    continue
                self.assertEqual(o, {"success": False, "data": [], "error": o["error"]})
                self.assertIn("fft_langkinh.json", o["error"])
                self.assertIn("goi_fft.py fft_langkinh", o["error"])

    def test_thu_muc_khong_ton_tai(self):
        o = chay(os.path.join(self.tmp, "khong_co"), "tongquan")
        self.assertFalse(o["success"])
        self.assertIn("goi_fft.py", o["error"])

    def test_tep_hong(self):
        d = self.ban_sao()
        with open(os.path.join(d, "fft_langkinh.json"), "w", encoding="utf-8") as fh:
            fh.write("{hỏng")
        o = chay(d, "bangquet")
        self.assertFalse(o["success"])
        self.assertIn("Không đọc được fft_langkinh.json", o["error"])

    def test_thieu_codong(self):
        d = self.ban_sao(bo=("fft_codong.json",))
        o = chay(d, "codong")
        self.assertFalse(o["success"])
        self.assertIn("goi_fft.py fft_codong", o["error"])
        o = chay(d, "tongquan")
        self.kiem_thanh_cong(o, "tongquan", "VN30")
        self.assertEqual(self.tiles(o)["CỔ ĐÔNG BÙNG NỔ ≥+50% TỪ ĐÁY 2N"]["v"], "—")
        self.assertEqual(len([b for b in chay(d, "chuoi", "FPT")["blocks"] if b["type"] == "chart"]), 1)
        self.kiem_thanh_cong(chay(d, "chuthe"), "chuthe", "VN30")  # Q2 vẫn lấy được từ cong.dau_vao

    def test_thieu_chuoi(self):
        d = self.ban_sao(bo=("fft_chuoi",))
        o = chay(d, "thitruong")
        self.kiem_thanh_cong(o, "thitruong", "VN30")
        self.assertFalse([b for b in o["blocks"] if b["type"] == "chart"])
        self.assertTrue(any(b["title"] == "Thiếu chuỗi" for b in o["blocks"] if b["type"] == "note"))
        self.kiem_thanh_cong(chay(d, "chuoi", "FPT"), "chuoi", "VN30")

    def test_view_va_scope_sai(self):
        for args in (("xyz",), ("bangquet", "VN50"), ("tongquan", "../.."), ("chuthe", "HNX")):
            o = chay(self.moi, *args)
            self.assertFalse(o["success"])
            self.assertEqual(o["data"], [])
            self.assertTrue(o["error"])
        self.assertIn("chuthe", chay(self.moi, "xyz")["error"])

    def test_du_lieu_cu(self):
        d = self.ban_sao(gio_truoc=30)
        o = chay(d, "bangquet", "VN100")
        self.kiem_thanh_cong(o, "bangquet", "VN100")
        self.assertTrue(o["tuoi"].startswith("DỮ LIỆU CŨ 30 giờ") or o["tuoi"].startswith("DỮ LIỆU CŨ 29 giờ"))
        self.assertEqual((o["blocks"][0]["title"], o["blocks"][0]["mau"]), ("Dữ liệu cũ", "warn"))
        o = chay(d, "codong")
        self.assertEqual([b["title"] for b in o["blocks"][:2]], ["Dữ liệu cũ", "Dữ liệu cổ đông cũ"])

    def test_cong_dung(self):
        def dung(doc):
            doc["cong"].update(chu_ky=None, dung=True, ly_do_dung="M2 cũ hơn 150 ngày",
                               dong="CỔNG: [CẦN DATA — M2 cũ hơn 150 ngày] · không kết luận per-mã")
        d = self.ban_sao(sua=dung)
        for v, arg in (("tongquan", "VN30"), ("bangquet", "VN30"), ("matran", "VN100"), ("bocung", "VN30"),
                       ("xephang", "VN100"), ("codong", "VN30"), ("chuthe", "VN30"), ("chuoi", "FPT")):
            with self.subTest(view=v):
                o = chay(d, v, arg)
                self.assertTrue(o["success"])
                self.assertEqual(o["cong"]["muc"], "dung")
                self.assertEqual(o["cong"]["dong"], "CỔNG: [CẦN DATA — M2 cũ hơn 150 ngày] · không kết luận per-mã")
                dau = [b for b in o["blocks"] if b["type"] == "note" and b["title"] == "CỔNG chưa xác định"]
                self.assertEqual(len(dau), 1)
                self.assertEqual(dau[0]["text"], NOTE_DUNG)
                self.assertEqual(o["blocks"][0]["title"], "CỔNG chưa xác định")
        t = self.tiles(chay(d, "chuoi", "FPT"))
        self.assertEqual((t["PLAYBOOK"]["v"], t["PLAYBOOK"]["s"]), ("[CẦN DATA]", "CỔNG chưa xác định — không kết luận per-mã"))
        self.assertEqual(t["CHỦ THỂ"]["v"], "cần")  # nhãn vẫn hiện, chỉ playbook dừng
        self.assertEqual({r["pb"] for r in self.block(chay(d, "chuthe"), "table")["rows"]}, {"CẦN DATA"})
        for v in ("thitruong", "phuongphap", "nguon"):
            o = chay(d, v)
            self.assertEqual(o["cong"]["muc"], "dung")
            self.assertFalse([b for b in o["blocks"] if b.get("title") == "CỔNG chưa xác định"])

    def test_cong_dung_khi_thieu_q2(self):
        def br(doc):  # (a) bridge đã dừng vì thiếu Q2 (D4.2)
            doc["cong"]["dau_vao"].pop("q2")
            doc["cong"].update(dung=True, ly_do_dung="[CẦN DATA — Q2 Corporate]", dong=Q2_DUNG)

        def cu(doc):  # (b) bridge chưa cập nhật: ĐẮT nhưng không có dau_vao.q2 → app DỪNG (S:99, R:177)
            doc["cong"]["dau_vao"].pop("q2")

        def ngoac(doc):  # (c) bridge dừng, ly_do có sẵn ngoặc, dong rỗng → không lồng ngoặc
            doc["cong"]["dau_vao"].pop("q2")
            doc["cong"].update(dung=True, ly_do_dung="[CẦN DATA — Q2 Corporate]", dong="")
        for f in (br, cu, ngoac):
            d = self.ban_sao(sua=f)
            for v, arg in (("tongquan", "VN30"), ("chuthe", "VN100"), ("chuoi", "FPT"), ("nguon", "VN30")):
                with self.subTest(f=f.__name__, view=v):
                    o = chay(d, v, arg)
                    self.kiem_thanh_cong(o, v, "VN30" if v == "chuoi" else arg)
                    self.assertEqual(o["cong"]["muc"], "dung")
                    self.assertEqual(o["cong"]["dong"], Q2_DUNG)
                    self.assertNotIn("Corporate", o["cong"]["chi_tiet"])
        d = self.ban_sao(sua=cu)
        o = chay(d, "tongquan")
        txt = chu(o["blocks"][1]["text"])
        self.assertIn("Dừng: [CẦN DATA — Q2 Corporate]", txt)
        self.assertIn("Q2 Corporate: [CẦN DATA — Q2 Corporate]", txt)
        self.assertEqual(o["blocks"][0]["text"], NOTE_DUNG)
        tp = {r["tp"]: r for r in self.block(chay(d, "nguon"), "table")["rows"]}
        self.assertEqual(tp["CỔNG · Q2 Corporate"]["phu"], "[CẦN DATA — Q2 Corporate] → CỔNG DỪNG")
        self.assertEqual(self.tiles(chay(d, "chuthe"))["Q2 CORPORATE 2025"]["v"],
                         "32 sự kiện · 21/30 mã")  # tile Q2 dự phòng từ fft_codong.q2

    def test_schema_cu_bridge_chua_cap_nhat(self):
        d = self.ban_sao(sua=bo_khoa_moi, sua_cd=bo_khoa_moi_cd)
        for v in VIEWS:
            for sc in ("VN30", "VN100"):
                with self.subTest(view=v, scope=sc):
                    o = chay(d, v, sc)
                    self.kiem_thanh_cong(o, v, sc)
                    self.assertEqual(o["cong"]["dong"], Q2_DUNG)
        for m in ("FPT", "HDG", "CTG", "TCX"):
            with self.subTest(ma=m):
                self.kiem_thanh_cong(chay(d, "chuoi", m), "chuoi", "VN100" if m == "HDG" else "VN30")
        o = chay(d, "chuoi", "FPT")
        ch = [b for b in o["blocks"] if b["type"] == "chart"][1]
        self.assertEqual([s["name"] for s in ch["series"]], ["Số cổ đông (chưa phân kiểu mốc)",
                                                             "Giá TV (danh nghĩa, chưa điều chỉnh CA)"])
        self.assertEqual(self.tiles(o)["SỞ HỮU"]["v"], "—")
        t = self.block(chay(d, "chuthe", "VN30"), "table")
        fpt = self.hang(t, "FPT")
        self.assertEqual((fpt["ct"], fpt["nn"], fpt["thu"], fpt["yd"], fpt["tv"]),
                         ("cần", "—", "[CẦN DATA]", "[CẦN DATA]", "—"))
        self.assertEqual(self.hang(t, "CTG")["ct"], "[CẦN DATA]")
        c = self.block(chay(d, "codong"), "table")
        self.assertEqual({self.hang(c, "MBB")[k] for k in ("kieu", "kqs", "gdd", "k", "tv")}, {"—"})
        self.assertEqual(self.tiles(chay(d, "codong"))["MỐC QUAN SÁT/NỘI SUY/CHÉP"]["v"], "—")

    def test_ro_trong_data_van_co_hang(self):
        def bo_vn30(doc):
            for m in doc["ma"].values():
                m["nhom"] = [x for x in m["nhom"] if x != "VN30"]
        d = self.ban_sao(sua=bo_vn30)
        for v in VIEWS:
            with self.subTest(view=v):
                self.kiem_thanh_cong(chay(d, v, "VN30"), v, "VN30")

    def test_danh_sach_rong_khong_thanh_hang(self):
        """C++ đánh số mọi hàng của block lists và tự vẽ "—" khi 0 hàng → không gửi hàng giữ chỗ "1. (…)"."""
        for truoc, duoi in ((None, "chưa có ảnh chụp tuần trước"),
                            ("2026-09-11", "không mã nào đổi lớp FFT (P3Y) / Ô 8 tuần")):
            def bo(doc, truoc=truoc):
                doc["doi_trang_thai"] = {"tuan_truoc": truoc, "ds": [], "ghi_chu": ""}
                for m in doc["ma"].values():
                    m["nhom"] = [x for x in m["nhom"] if x != "VN30"]
            with self.subTest(tuan_truoc=truoc):
                it = self.block(chay(self.ban_sao(sua=bo), "xephang", "VN30"), "lists")["items"]
                self.assertEqual([x["rows"] for x in it], [[], [], [], []])
                self.assertEqual(it[3]["title"], "Đổi trạng thái vs tuần trước · " + duoi)

    def test_xung_dot_bridge_da_canh_bao(self):
        def cb(doc):  # bridge tự ghi cảnh báo xung đột → app không lặp, không thêm "chưa có nhãn"
            doc["ma"]["CTG"]["chu_the"]["canh_bao"] = ["Nhãn xung đột giữa các nguồn — giữ nguyên văn mọi phía, "
                                                       "không chọn bên (S:477)"]
        o = chay(self.ban_sao(sua=cb), "chuoi", "CTG")
        self.assertEqual(sum("xung đột" in x for x in o["cong"]["canh_bao"]), 1)
        self.assertFalse([x for x in o["cong"]["canh_bao"] if "chưa có nhãn" in x])

    def test_truong_tuy_chon_trong(self):
        def bot(doc):
            doc["ma"]["VCB"]["tuan"] = None
            doc["ma"]["VCB"]["ff"] = None
            doc["ma"]["VCB"]["loi"] = "thiếu free float"
            for k in ("bocung", "phien", "chu_the", "dm"):
                del doc["ma"]["ACB"][k]
            doc["ma"]["MBB"]["tuan"]["pct3y"] = None
            doc["ma"]["MBB"]["tuan"]["vi_tri"] = float("nan")
            doc["ma"]["MBB"]["tuan"]["canh_bao"] = 12
            doc["ma"]["FPT"]["phien"]["chg"] = float("inf")
            doc["ma"]["FPT"]["chu_the"]["khang_dinh"] = ["hỏng", 3, None]
            doc["ma"]["FPT"]["chu_the"]["bang_chung"] = {"so_huu": "x", "phat_hanh_24t": [1], "y_do": {"a": 1},
                                                         "tang_von_tv": 5}
            doc["ma"]["HPG"]["chu_the"] = "hỏng"
            doc["ma"]["VHM"]["chu_the"]["bang_chung"]["y_do"] = [{"ngay": None}, "x"]
            doc["ma"]["TCX"] = "hỏng"
            del doc["thi_truong"]["VN100"]
            del doc["doi_trang_thai"]
            del doc["phien"]
            doc["nguon"]["chu_the"] = "hỏng"
            doc["cong"]["dau_vao"]["q2"]["nam"] = "hỏng"
            doc["cong"]["canh_bao"] = None

        def bot_cd(doc):
            doc["ma"]["VHM"]["cuoi"] = None
            doc["ma"]["MBB"]["vs_day"] = None
            doc["ma"]["FPT"]["moc"] = [{"ky": "hỏng"}, "x"]
            doc["q2"] = []
            del doc["dem"]
        d = self.ban_sao(sua=bot, sua_cd=bot_cd)
        for v in VIEWS:
            for sc in ("VN30", "VN100"):
                with self.subTest(view=v, scope=sc):
                    self.kiem_thanh_cong(chay(d, v, sc), v, sc)
        for m in ("VCB", "ACB", "MBB", "FPT", "HPG", "VHM"):
            with self.subTest(ma=m):
                self.kiem_thanh_cong(chay(d, "chuoi", m), "chuoi", "VN30")
        t = self.block(chay(d, "bangquet", "VN30"), "table")
        vcb = self.hang(t, "VCB")
        self.assertEqual({vcb[k] for k in ("ma4", "vt", "pall", "o8", "ff")}, {"—"})
        mbb = self.hang(t, "MBB")
        self.assertEqual(mbb["vt"], "—")
        self.assertNotIn("_bar", mbb)
        ct = self.block(chay(d, "chuthe"), "table")
        self.assertEqual(self.hang(ct, "HPG")["ct"], "[CẦN DATA]")
        self.assertEqual(self.hang(ct, "FPT")["thu"], "[CẦN DATA]")


class TestDinhDang(unittest.TestCase):
    def test_so_viet(self):
        self.assertEqual(B.so(1234.5, 1), "1.234,5")
        self.assertEqual(B.so(-3.25, 1), "−3,2")
        self.assertEqual(B.so(1234567, 0), "1.234.567")
        self.assertEqual(B.so(-0.004, 2), "0,00")
        self.assertEqual(B.so(2.5, 1, True), "+2,5")
        self.assertEqual(B.so(None), "—")
        self.assertEqual(B.so(float("nan")), "—")
        self.assertEqual(B.so(True), "—")
        self.assertEqual(B.pt(1.87, 2, True), "+1,87%")
        self.assertEqual(B.pt(None), "—")
        self.assertEqual(B.gia(66400), "66.400")
        self.assertEqual(B.fftp(0.357), "0,357%")
        self.assertEqual(B.boi(2.33), "2,33×")
        self.assertEqual(B.pp(72.5), "72,5")
        self.assertEqual(B.P(46), "P46")
        self.assertEqual(B.tile_pct(-0.41), "−41,0%")
        self.assertEqual(B.ky_ngan("2026-06"), "T6/26")
        self.assertEqual(B.dm("18/09/2026"), "18/09")
        self.assertEqual(B.ms(B.ngay("2026-09-25")), 1790294400000)
        self.assertEqual(B.tuan_nhan("2026-09-10"), "W37 10/09")
        self.assertEqual(B.tuan_nhan(None), "")
        self.assertEqual(B.ds_chu("a"), ["a"])
        self.assertEqual(B.ds_chu(["a", None, 3, ""]), ["a", "3"])
        self.assertEqual((B.ds_chu(None), B.ds_chu(12)), ([], []))
        self.assertEqual(B.dm_tag({"dm": {"avoid": True, "xung_dot": "x"}}), "avoid*")
        self.assertEqual(B.dm_tag({"dm": {"xung_dot": "x"}}), "")
        self.assertEqual(B.phu_ro({"so_ma": 7, "n_thanh_vien": 10}), (7, 10, True))
        self.assertEqual(B.phu_ro({"n_co_du_lieu": 8, "n_thanh_vien": 10}), (8, 10, False))

    def test_chu_the_va_playbook(self):
        self.assertEqual(CT.loai_chu_the("Có · thưởng 171 tr.cp"), "cần")
        self.assertEqual(CT.loai_chu_the("không cần"), "không cần")
        self.assertEqual(CT.loai_chu_the("Trung tính · tăng vốn"), "trung tính")
        self.assertIsNone(CT.loai_chu_the(None))
        self.assertIsNone(CT.loai_chu_the("BALANCED"))  # nhãn NTH/ydo không bao giờ map sang trung tính
        self.assertIsNone(CT.nhan({"nhan": "cần", "xung_dot": True}))
        self.assertEqual(CT.bac_yeu(["SS-T3", "EST", "FACT-T2"]), "EST")
        self.assertEqual(CT._can_data("[CẦN DATA — Q2 Corporate]"), "CẦN DATA — Q2 Corporate")
        self.assertEqual(CT._can_data("M2 cũ"), "CẦN DATA — M2 cũ")
        self.assertEqual(CT.q2_doan({"nam": {"2025": {"so_su_kien": 32, "so_ma": 21},
                                             "2026": {"so_su_kien": 15, "so_ma": 10, "den_ky": "2026-07"}}}),
                         "32 sự kiện/21 mã (2025), 15/10 (2026 tới 07)")
        self.assertEqual(CT.q2_doan({"theo_nam": {"2024": {"so_su_kien": 25, "so_ma": 16},
                                                  "2025": {"so_su_kien": 32, "so_ma": 21},
                                                  "2026": {"so_su_kien": 15, "so_ma": 10}}, "den_ky": "2026-07"}),
                         "32 sự kiện/21 mã (2025), 15/10 (2026 tới 07)")
        self.assertTrue(CT.cong_dung({"chu_ky": "ĐẮT", "dau_vao": {}}))
        self.assertFalse(CT.cong_dung({"chu_ky": "ĐẮT", "dau_vao": {"q2": {}}}))

    def test_sach_nan_va_tom_tat(self):
        self.assertEqual(L.sach({"a": [float("nan"), 1.0, {"b": float("-inf")}]}), {"a": [None, 1.0, {"b": None}]})
        self.assertTrue(math.isfinite(L.sach(2.0)))
        self.assertEqual(L.tom_tat([], "X"), [{"01 Mục": "X", "02 Giá trị": "không có hàng dữ liệu"}])
        self.assertEqual(L.tom_tat([{"type": "note", "title": "A", "text": "<b>x</b> &amp; y"}], "X"),
                         [{"01 Mục": "A", "02 Giá trị": " x  & y"}])


if __name__ == "__main__":
    unittest.main()
