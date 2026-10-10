#!/usr/bin/env python3
"""
DELTA v5 + lớp sự kiện TỰ ĐỘNG (job fft_tin, 22/09/2026): mục "Bức tranh tổng thể"… trong thẻ story, sự kiện tự động
chỉ lấp chỗ trống (timeline ≤12, chart ưu tiên 2, thoi ≤4), mã chỉ có sự kiện tự động không có thẻ story, độ tươi
nguồn tin tính lại LÚC MỞ (LIVE/STALE/DEAD), hàng nguồn tin ở view `nguon`. Dữ liệu giả, gắn lên bản sao fixture.
"""
import unittest
from datetime import datetime, timedelta

from lk_nen import KHONG_QD, Nen, chay
from test_fincept_langkinh_v4 import gan

import fincept_langkinh_story as ST  # noqa: E402

NOW = datetime.now(ST.ICT)


def _iso(gio):
    return (NOW - timedelta(hours=gio)).isoformat(timespec="seconds")


NGUON_TIN = [
    {"id": "vc_noibo", "bac": "FACT-T2", "moi_nhat": _iso(20), "nguong_gio": 48, "phu_vn100": "9/100",
     "n_su_kien": 25, "tep": "kho_vc_noibo_tho.json", "lich": "120'/720'", "chet": None, "loi": None},
    {"id": "vnf", "bac": "FACT-T1", "moi_nhat": _iso(219), "nguong_gio": 168, "phu_vn100": "100/100",
     "n_su_kien": 6, "tep": "VN_Filings", "chet": None, "loi": None},
    {"id": "sz_noibo_cu", "bac": "FACT-T2", "moi_nhat": _iso(20), "nguong_gio": 192, "phu_vn100": "57/100",
     "n_su_kien": 359, "tep": "simplize_insider.json", "chet": "script refresh_simplize_insider.py không tồn tại",
     "loi": None}]


def _td(i, ngay, loai, ma, **kw):
    return {"id": "td:x:%s" % i, "ma": ma, "ngay": ngay, "loai": loai, "chu_the": kw.pop("chu_the", "Quỹ C (fixture)"),
            "bac": kw.pop("bac", "FACT-T2"), "nguon": "kho_fixture.json#%s" % i, "mo_ta": "%s [tự động]" % i,
            "tu_dong": True, "nguon_id": "vcnb", "vung_gia": kw.pop("vung_gia", None),
            "vung_gia_ly_do": "[CẦN DATA] vùng giá", **kw}


def _vg(v):
    return {"vwap": v, "p25": v - 500, "p75": v + 500, "lo": v - 1000, "hi": v + 1000, "n_phien": 5, "kl": 1,
            "tu": "2026-08-12", "den": "2026-08-20", "bac": "EST", "logic": "ĐĂNG KÝ, chưa có kết quả. fixture"}


def gan_v5(doc):
    gan(doc)
    ng = doc["nguon"]["cau_chuyen"]
    ng["nguon_tin"] = NGUON_TIN
    ng["tu_dong"] = {"cap_nhat": "2026-09-22 12:35", "n_su_kien": 20, "n_ma": 2, "n_bi_an": 1}
    vhm = doc["ma"]["VHM"]["cau_chuyen"]
    vhm["buc_tranh"] = {"text": "Tổng hợp fixture.", "bac": "SS-T3", "nguon": ["fixture/a.md:1", "fixture/b.md:2"]}
    vhm["thau_tom"] = {"text": "Ai gom (fixture).", "bac": "UNVERIFIED", "nguon": ["fixture/c.md:3"]}
    vhm["su_kien"] = vhm["su_kien"] + [_td("vhm%d" % k, "2026-0%d-1%d" % (k % 3 + 6, k), "dang_ky_mua", "VHM")
                                       for k in range(15)]
    doc["ma"]["FPT"]["cau_chuyen"] = {
        "tieu_de": None, "chu_the": [], "chi_tu_dong": True, "dong_co": None, "diem_gay": None, "cau_hoi_mo": [],
        "vung_gia_gom": None, "canh_bao": [], "tai_lieu": [],
        "su_kien": [_td("f%d" % k, "2026-08-%02d" % (k + 1), "dang_ky_mua", "FPT", vung_gia=_vg(100000 + k * 100))
                    for k in range(6)] + [_td("fk", "2026-08-20", "khac", "FPT")]}


class TestTuDongV5(Nen):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cc = cls.ban_sao(sua=gan_v5)

    def test_story_sections_v5(self):
        o = chay(self.cc, "chuoi", "VHM")
        self.kiem_thanh_cong(o, "chuoi", "VN30")
        st = self.block(o, "story")
        self.assertEqual([x["title"] for x in st["sections"]], ["Bức tranh tổng thể", "Ai đang thâu tóm"])
        self.assertIn("fixture/a.md:1; fixture/b.md:2", st["sections"][0]["tip"])
        self.assertIn(KHONG_QD, st["sections"][1]["text"])
        self.assertIn("+15 tự động", st["sub"])
        self.assertIn("4 sự kiện (", st["sub"])                         # đếm bậc chỉ trên bản tuyển chọn

    def test_timeline_toi_da_12_tu_dong_va_dong_nguon(self):
        o = chay(self.cc, "chuoi", "VHM")
        tl = self.block(o, "timeline")
        tu_dong = [x for x in tl["items"] if "tự động (job fft_tin)" in x["tip"]]
        self.assertEqual(len(tu_dong), ST.MAX_TD_TL)
        self.assertIn("+ 12/15 tự động mới nhất", tl["sub"])
        n = self.note(o, "Độ tươi nguồn tin (tính lúc mở)")
        self.assertEqual(n["mau"], "amber")
        self.assertIn("<b>LIVE</b>", n["text"])
        self.assertIn("<b>STALE</b>", n["text"])
        self.assertIn("<b>DEAD</b>", n["text"])

    def test_ma_chi_tu_dong_khong_co_story(self):
        o = chay(self.cc, "chuoi", "FPT")
        self.kiem_thanh_cong(o, "chuoi", "VN30")
        typ = [b["type"] for b in o["blocks"]]
        self.assertNotIn("story", typ)
        self.assertIn("[CẦN DATA]", self.note(o, "Chưa có câu chuyện tuyển chọn — FPT")["text"])
        self.assertEqual(len(self.block(o, "timeline")["items"]), 7)
        chart = next(b for b in o["blocks"] if b["type"] == "chart" and b["title"].endswith("FFT × Giá"))
        ann = chart.get("annotations") or []
        vl = [a for a in ann if a.get("kind") == "vline" and "tự động" in a.get("sub", "")]
        self.assertEqual(len(vl), 6)                                      # loại "khac" không lên chart
        self.assertTrue(all(a["uu_tien"] == 2 for a in vl))
        thoi = [a for a in ann if a.get("marker") == "diamond" and "tự động" in str(a.get("sub"))]
        self.assertEqual(len(thoi), ST.MAX_TD_THOI)
        self.assertFalse([a for a in ann if a.get("kind") == "hband"])   # tự động không có vùng gom

    def test_cauchuyen_tiles_nguon_tin(self):
        o = chay(self.cc, "cauchuyen", "VN30")
        self.kiem_thanh_cong(o, "cauchuyen", "VN30")
        tiles = [t for b in o["blocks"] if b["type"] == "tiles" for t in b["items"]]
        k = {t["k"]: t for t in tiles}
        self.assertTrue(k["MÃ CHỈ CÓ SỰ KIỆN TỰ ĐỘNG"]["v"].startswith("1/"))
        self.assertTrue(k["GD NỘI BỘ 14 NGÀY · VIETCAP"]["s"].startswith("LIVE"))
        self.assertEqual(k["GD NỘI BỘ 14 NGÀY · VIETCAP"]["mau"], "info")
        self.assertEqual(k["PDF GỐC · VN_FILINGS"]["mau"], "amber")
        self.assertEqual(k["INSIDER · SIMPLIZE"]["mau"], "warn")
        n = self.note(o, "Nguồn tin chưa LIVE")
        self.assertIn("refresh_simplize_insider.py", n["text"])
        self.assertIn("Hệ quả", n["text"])
        self.assertIn("Trong đó 1 mã đã có sự kiện tự động", self.note(o, "Chưa có câu chuyện")["text"])

    def test_nguon_hang_nguon_tin(self):
        o = chay(self.cc, "nguon", "VN30")
        tp = [r.get("01 Thành phần") for r in o["data"]]
        self.assertIn("Tin tự động · GD nội bộ 14 ngày · Vietcap", tp)
        self.assertIn("Tin tự động · Insider · Simplize", tp)

    def test_trang_thai_nay(self):
        tt = {n["id"]: ST.trang_thai_nay(n, NOW) for n in NGUON_TIN}
        self.assertEqual(tt, {"vc_noibo": "LIVE", "vnf": "STALE", "sz_noibo_cu": "DEAD"})
        self.assertEqual(ST.trang_thai_nay({"moi_nhat": _iso(1000), "nguong_gio": 48}, NOW), "DEAD")
        self.assertEqual(ST.trang_thai_nay({"moi_nhat": None, "nguong_gio": 48}, NOW), "DEAD")
        self.assertEqual(ST.tuoi_chu(0.5), "30 phút")
        self.assertEqual(ST.tuoi_chu(219), "9,1 ngày")


if __name__ == "__main__":
    unittest.main()
