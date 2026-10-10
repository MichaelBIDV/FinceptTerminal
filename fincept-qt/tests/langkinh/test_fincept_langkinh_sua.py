#!/usr/bin/env python3
"""
Kiểm các sửa theo review (review_raw.json, đợt sửa app): (a) bậc tile Bùng nổ/Đặc lại · (b) % free float = mẫu số FFT ·
(c) playbook per-mã hiển thị nguyên giá trị bridge · (d) mã cũ / chờ CA · (e) bậc tile rổ bac_hang/bac_muc ·
(f) CỔNG dừng nghiêm + dòng tham chiếu. Chạy:  <python> -m unittest discover -s tests/langkinh -v
"""
import unittest

from lk_nen import CT, T, Nen, chay, chu

THAM_CHIEU = "Tham chiếu nếu bỏ cờ gãy M2: ĐẮT · GAP 13,2 — EST, không dùng cho quyết định"
LY_DO_M2 = ("[CẦN DATA — M2 nghi gãy chuỗi (bước nhảy 10/2025); nguồn goi_widata ghi 'không dùng kết luận "
            "tín dụng/M2']")
DUNG_M2 = "CỔNG: %s · không kết luận per-mã" % LY_DO_M2  # khuôn fft_cong.tinh_cong (strict_m2 = true)


def dung_nghiem(giu_chu_ky=False):
    """Bridge sau sửa M2 (fft_cong.tinh_cong): DỪNG nghiêm vì chuỗi M2 nghi gãy, chu_ky null, kết quả luật đọc nguyên
    văn chỉ ở `tham_chieu` (EST); playbook mã None, cong_dong = dòng DỪNG. giu_chu_ky: bridge lỡ giữ 'ĐẮT'."""
    def f(doc):
        cg = doc["cong"]
        cg.update(chu_ky="ĐẮT" if giu_chu_ky else None, dung=True, ly_do_dung=LY_DO_M2, dong=DUNG_M2,
                  m2_nghi_gay=True, chu_ky_q1=None,
                  tham_chieu={"chu_ky_neu_bo_co": "ĐẮT", "gap": 13.17, "bac": "EST",
                              "ghi_chu": "chỉ do bước nhảy chuỗi M2 — không dùng cho quyết định"})
        if not giu_chu_ky:
            cg.update(bucket=None, playbook=None)
        for m in doc["ma"].values():
            m["chu_the"].update(playbook=None, cong_dong=DUNG_M2)
    return f


def lech(doc):
    """Khuôn goi_fft.mot_ma: VHM dừng dữ liệu từ 12/08 (`tre` dict); FPT chờ điều chỉnh CA 21/09 (`ca_cho` bool,
    ngày CA trong `loi`, lớp giá phiên/tuần hiện tại bị ẩn = null)."""
    vhm, fpt = doc["ma"]["VHM"], doc["ma"]["FPT"]
    vhm["tuan"]["week_end"], vhm["phien"]["ngay"] = "2026-08-14", "2026-08-12"
    vhm["tre"] = {"phien_cuoi_ma": "2026-08-12", "so_phien_thieu": 27, "tuan_cuoi_ma": "2026-08-14"}
    fpt["ca_cho"] = True
    fpt["loi"] = ("đang chờ điều chỉnh sự kiện quyền — lớp phiên/tuần hiện tại tạm ẩn (CA 2026-09-21 · tham chiếu "
                  "lệch 10,0% so giá đóng cửa trước)")
    fpt["phien"].update(chg=None, vol_x20=None, boi_so=None, fft_d=None)
    fpt["tuan"].update(chg_1w=None, o8_gia=None, o8=None, ret_52w=None, ret_2y=None)
    for m in doc["ma"].values():
        m.setdefault("tre", None)
        m.setdefault("ca_cho", False)


class TestSuaReview(Nen):
    # ── (a) ────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_a_bung_no_dac_lai_bac_est_va_w37(self):
        t = self.tiles(chay(self.moi, "codong", "VN30"))
        bn, dl = t["BÙNG NỔ ≥+50% TỪ ĐÁY 2N"], t["ĐẶC LẠI Ở ĐÁY 2N"]
        self.assertEqual((bn["v"], bn["bac"]), ("15/30", "EST"))
        self.assertTrue(bn["s"].startswith("(EST · mốc quan sát, luật D3.3) · W37: 13/30 (SS-T3)"), bn["s"])
        self.assertEqual((dl["v"], dl["bac"]), ("6/30", "EST"))
        self.assertTrue(dl["s"].startswith("(EST · mốc quan sát, luật D3.4) · W37: 6/30 (SS-T3)"), dl["s"])
        self.assertIn(T.CD_DAC_LAI, dl["s"])
        t = self.tiles(chay(self.moi, "tongquan", "VN30"))
        bn = t["CỔ ĐÔNG BÙNG NỔ ≥+50% TỪ ĐÁY 2N"]
        self.assertEqual((bn["v"], bn["bac"]), ("15/30", "EST"))
        self.assertTrue(bn["s"].startswith("(EST · mốc quan sát, luật D3.3) · W37: 13/30 (SS-T3) · tệp Toàn Vũ 26/08/2026"))
        self.assertEqual(t["ĐẶC LẠI Ở ĐÁY 2N"]["bac"], "EST")

    def test_a_tep_cu_khong_mang_bac_tep_ss_t3(self):
        def cu(doc):  # bridge chưa có dem.bac / dem.w37 → không được mượn bậc cấp tệp (SS-T3)
            doc["dem"] = {"bung_no": 15, "dac_lai": 6}
        d = self.ban_sao(sua_cd=cu)
        for v, k in (("codong", "BÙNG NỔ ≥+50% TỪ ĐÁY 2N"), ("tongquan", "CỔ ĐÔNG BÙNG NỔ ≥+50% TỪ ĐÁY 2N")):
            x = self.tiles(chay(d, v, "VN30"))[k]
            self.assertEqual(x["bac"], "EST")
            self.assertNotIn("W37:", x["s"])
            self.assertTrue(x["s"].startswith("(EST · mốc quan sát, luật D3.3)"))

    # ── (b) ────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_b_ff_hien_thi_bang_mau_so_fft(self):
        t = self.block(chay(self.moi, "bangquet", "VN30"), "table")
        mbb, fpt, vcb = (self.hang(t, x) for x in ("MBB", "FPT", "VCB"))
        self.assertEqual((mbb["ff"], mbb["_sort"]["ff"]), ("62,5%", 62.5))  # 100·ff_cp/issue_share, không phải 50%
        self.assertEqual((mbb["_tag"]["ff"], mbb["_mau"]["ff"]), ("⚠", "warn"))
        self.assertIn("VCI ff_pct 50%", mbb["_tip"]["ff"])
        self.assertIn("62,5%", mbb["_tip"]["ff"])
        self.assertEqual(fpt["ff"], "85,0%")
        self.assertEqual(vcb["ff"], "11,0%")
        self.assertNotIn("ff", vcb.get("_tag", {}))
        plx = self.hang(self.block(chay(self.moi, "bangquet", "VN100"), "table"), "PLX")
        self.assertEqual((plx["ff"], plx["_tag"]["ff"]), ("10%", "⚠"))  # thiếu issue_share → % VCI + ⚠
        self.assertIn("thiếu issue_share", plx["_tip"]["ff"])
        ct = self.block(chay(self.moi, "chuthe", "VN30"), "table")
        mbb = self.hang(ct, "MBB")
        self.assertEqual((mbb["khoa"], mbb["_sort"]["khoa"]), ("37,5%", 37.5))
        self.assertEqual((mbb["_tag"]["khoa"], mbb["_mau"]["khoa"]), ("⚠", "amber"))
        self.assertIn("VCI ff_pct 50%", mbb["_tip"]["khoa"])
        self.assertIn("VCI tự mâu thuẫn", mbb["_tip"]["khoa"])
        self.assertNotIn("khoa", self.hang(ct, "VCB").get("_tag", {}))
        plx = self.hang(self.block(chay(self.moi, "chuthe", "VN100"), "table"), "PLX")
        self.assertEqual((plx["khoa"], plx["_tag"]["khoa"]), ("90%", "⚠"))
        t = self.tiles(chay(self.moi, "chuoi", "MBB"))["FREE FLOAT"]
        self.assertEqual((t["v"], t["mau"]), ("62,5%", "warn"))
        self.assertIn("VCI ff_pct 50%", t["s"])

    # ── (c) ────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_c_playbook_ma_la_gia_tri_bridge(self):
        def re_(doc):  # khuôn fft_cong.playbook_ma/dong_ma sau sửa: RẺ + có nhãn → Quality; xung đột/không nhãn → CẦN DATA
            doc["cong"].update(chu_ky="RẺ", playbook="Quality Investing thuần",
                               dong=doc["cong"]["dong"].replace("tiền đắt", "tiền rẻ"))
            for m in doc["ma"].values():
                ct = m["chu_the"]
                co = bool(ct.get("nhan")) and not ct.get("xung_dot")
                ct["playbook"] = "Quality Investing thuần" if co else "[CẦN DATA]"
                dau = ct["cong_dong"].replace("tiền đắt", "tiền rẻ").rsplit("playbook [", 1)[0]
                ct["cong_dong"] = dau + "playbook [%s]" % ct["playbook"].strip("[]")
        d = self.ban_sao(sua=re_)
        rows = {r["ma"]: r["pb"] for r in self.block(chay(d, "chuthe", "VN30"), "table")["rows"]}
        self.assertEqual((rows["FPT"], rows["ACB"], rows["CTG"], rows["TCX"]),
                         ("Quality Investing thuần", "Quality Investing thuần", "CẦN DATA", "CẦN DATA"))
        o = chay(d, "chuoi", "TCX")
        self.assertEqual(o["cong"]["dong"], "CỔNG: [tiền rẻ] · chủ thể [CẦN DATA] thị trường · playbook [CẦN DATA]")
        self.assertIn("TCX chưa có nhãn chủ thể — playbook [CẦN DATA]", o["cong"]["canh_bao"])  # khớp dòng CỔNG
        self.assertEqual(chay(d, "chuoi", "CTG")["cong"]["dong"],
                         "CỔNG: [tiền rẻ] · chủ thể [CẦN DATA — nhãn xung đột] thị trường · playbook [CẦN DATA]")

        def khac(doc):  # app không tự chấm lại: giá trị bridge nào cũng hiện nguyên văn, kể cả cho mã xung đột
            re_(doc)
            doc["ma"]["CTG"]["chu_the"].update(playbook="PB-cầu-nối", cong_dong="CỔNG: [tiền rẻ] · x · playbook [PB-cầu-nối]")
        d = self.ban_sao(sua=khac)
        self.assertEqual(self.hang(self.block(chay(d, "chuthe", "VN30"), "table"), "CTG")["pb"], "PB-cầu-nối")
        o = chay(d, "chuoi", "CTG")
        self.assertEqual((o["cong"]["dong"], self.tiles(o)["PLAYBOOK"]["v"]),
                         ("CỔNG: [tiền rẻ] · x · playbook [PB-cầu-nối]", "[PB-cầu-nối]"))

    def test_c_thieu_playbook_bridge_thi_can_data(self):
        def bo(doc):  # khoá bridge vắng → [CẦN DATA], không tự suy lại luật D4.4 trong app
            for m in doc["ma"].values():
                m["chu_the"].pop("playbook", None)
                m["chu_the"].pop("cong_dong", None)
        d = self.ban_sao(sua=bo)
        rows = {r["ma"]: r["pb"] for r in self.block(chay(d, "chuthe", "VN30"), "table")["rows"]}
        self.assertEqual(set(rows.values()), {"CẦN DATA"})
        o = chay(d, "chuoi", "FPT")
        self.assertEqual(o["cong"]["dong"], "CỔNG: [tiền đắt] · chủ thể [cần] thị trường · playbook [CẦN DATA]")
        self.assertFalse(hasattr(CT, "playbook_ma"))

    # ── (d) ────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_d_ma_cu_va_cho_ca(self):
        d = self.ban_sao(sua=lech)
        o = chay(d, "bangquet", "VN30")
        t = self.block(o, "table")
        self.assertEqual([r["ma"] for r in t["rows"]][-2:], ["FPT", "VHM"])  # ra khỏi thứ hạng, xuống cuối
        vhm, fpt = self.hang(t, "VHM"), self.hang(t, "FPT")
        self.assertEqual((vhm["_tag"]["gia"], vhm["_mau"]["gia"], vhm["_vien"]), ("cũ 12/08", "warn", "warn"))
        self.assertEqual((fpt["_tag"]["gia"], fpt["_vien"]), ("chờ CA", "warn"))
        self.assertIn("GDKHQ 21/09", fpt["_tip"]["gia"])
        self.assertIn("thiếu 27 phiên", vhm["_tip"]["gia"])
        self.assertIn("VHM cũ 12/08", t["caption"])
        o = chay(d, "tongquan", "VN30")
        do_rong = self.tiles(o)["ĐỘ RỘNG PHIÊN · VN30"]
        self.assertTrue(do_rong["v"].endswith("/6"), do_rong)  # 8 − VHM − FPT
        self.assertIn("2 mã cũ/chờ CA (loại khỏi đếm)", do_rong["s"])
        for i in (0, 1):
            self.assertFalse({"VHM", "FPT"} & {r["ma"] for r in self.block(o, "table", i)["rows"]})
        mx = chay(d, "matran", "VN30")
        chips = {c["ma"] for r in self.block(mx, "matrix")["rows"] for cell in r["cells"] for c in cell["chips"]}
        self.assertFalse({"VHM", "FPT"} & chips)
        self.assertIn("6/8 mã xếp được", mx["sub"])
        self.assertIn("VHM (cũ 12/08)", self.note(mx, "Dữ liệu cũ / chờ CA — không xếp")["text"])
        it = self.block(chay(d, "xephang", "VN30"), "lists")["items"]
        self.assertFalse([x for x in it[0]["rows"] + it[1]["rows"] + it[2]["rows"] if x.split()[0] in ("VHM", "FPT")])
        sc = self.block(chay(d, "bocung", "VN30"), "scatter")
        self.assertFalse({"VHM", "FPT"} & {p["label"] for p in sc["points"]})
        o = chay(d, "chuoi", "VHM")
        self.assertIn("12/08", self.note(o, "Dữ liệu mã cũ / chờ CA")["text"])
        self.assertEqual(self.hang(self.block(chay(d, "chuthe", "VN30"), "table"), "FPT")["_tag"]["pct"], "chờ CA")
        o = chay(self.moi, "bangquet", "VN30")  # fixture gốc: không mã nào lệch
        self.assertFalse([r for r in self.block(o, "table")["rows"] if r.get("_vien") == "warn"])

    def test_d_bridge_cu_khong_co_khoa_tre_so_ngay(self):
        def cu(doc):  # tệp bridge chưa có khoá `tre`: tuần/phiên của mã trễ hơn tệp → vẫn gắn cũ
            doc["ma"]["VHM"]["tuan"]["week_end"], doc["ma"]["VHM"]["phien"]["ngay"] = "2026-08-14", "2026-08-12"
        t = self.block(chay(self.ban_sao(sua=cu), "bangquet", "VN30"), "table")
        self.assertEqual(self.hang(t, "VHM")["_tag"]["gia"], "cũ 12/08")

    # ── (e) ────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_e_bac_tile_ro(self):
        t = self.tiles(chay(self.moi, "tongquan", "VN30"))
        self.assertEqual(t["MARKET FFT VN100 · VỊ TRÍ 3Y"]["bac"], "FACT-T2")  # percentile → bac_hang
        self.assertEqual(t["MARKET FFT VN30 · TB 4 TUẦN"]["bac"], "EST")  # mức → bac_muc
        t = self.tiles(chay(self.moi, "thitruong", "VN30"))
        self.assertEqual(t["VN30 · SỐ MÃ CÓ FF"]["bac"], "FACT-T2")
        for k in ("VN30 · MARKET FFT TUẦN", "VN30 · TB 4 TUẦN", "VN30 · P10 / P90 3Y"):
            self.assertEqual(t[k]["bac"], "EST", k)

        def chi_bac(doc):  # chỉ có khoá chung `bac` (EST) → percentile vẫn FACT-T2, khoá chung không đè
            for tt in doc["thi_truong"].values():
                tt.pop("bac_hang")
                tt.pop("bac_muc")
        t = self.tiles(chay(self.ban_sao(sua=chi_bac), "tongquan", "VN30"))
        self.assertEqual(t["MARKET FFT VN100 · VỊ TRÍ 3Y"]["bac"], "FACT-T2")
        self.assertEqual(t["MARKET FFT VN30 · TB 4 TUẦN"]["bac"], "EST")

    # ── (f) ────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_f_cong_dung_nghiem_va_tham_chieu(self):
        for giu in (False, True):
            d = self.ban_sao(sua=dung_nghiem(giu))
            with self.subTest(chu_ky_con="ĐẮT" if giu else None):
                for v, arg in (("tongquan", "VN30"), ("chuoi", "FPT"), ("chuthe", "VN30"), ("bangquet", "VN30")):
                    o = chay(d, v, arg)
                    self.assertEqual((o["cong"]["muc"], o["cong"]["dong"]), ("dung", DUNG_M2))
                    self.assertEqual(o["cong"]["chi_tiet"].split("\n")[1], THAM_CHIEU)
                self.assertEqual({r["pb"] for r in self.block(chay(d, "chuthe", "VN30"), "table")["rows"]}, {"CẦN DATA"})
                self.assertEqual(self.tiles(chay(d, "chuoi", "FPT"))["PLAYBOOK"]["v"], "[CẦN DATA]")
                txt = chu(chay(d, "tongquan", "VN30")["blocks"][1]["text"])
                self.assertIn("Chu kỳ tiền: [CẦN DATA]", txt)
                self.assertIn(THAM_CHIEU, txt)
                tp = {r["tp"]: r for r in self.block(chay(d, "nguon", "VN30"), "table")["rows"]}
                self.assertTrue(tp["CỔNG · kết luận"]["phu"].startswith(LY_DO_M2), tp["CỔNG · kết luận"]["phu"])
                self.assertTrue(tp["CỔNG · kết luận"]["phu"].endswith(THAM_CHIEU))
        o = chay(self.moi, "tongquan", "VN30")  # không dừng → không có dòng tham chiếu
        self.assertNotIn("Tham chiếu", o["cong"]["chi_tiet"])


if __name__ == "__main__":
    unittest.main()
