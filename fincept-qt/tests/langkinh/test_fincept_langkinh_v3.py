#!/usr/bin/env python3
"""
CONTRACT_DELTA v3 (22/09/2026): ds_ma cho ô gõ mã (V3.1), series 'band' (V3.2), 'annotations' (V3.3–V3.4).
Chạy:  <python> -m unittest discover -s tests/langkinh -v      (từ thư mục fincept-qt; cả 3.11 lẫn 3.14)
"""
import re
import unittest
from datetime import date, timedelta

from lk_nen import VN30, VN100, Nen, chay

import fincept_langkinh_views as V  # noqa: E402 — sys.path đã trỏ scripts/ trong lk_nen

TUAN = 7 * 86400000
KHUYEN_NGHI = re.compile(r"\b(mua|bán|khuyến nghị|nên)\b", re.I)


def chuoi_gia(n, m):
    """Chuỗi tuần tổng hợp: p10 = 0,2 · p90 = 0,8 cố định; m theo hàm tuần → (x, t, y)."""
    d0 = date(2020, 1, 3)
    t = [(d0 + timedelta(weeks=i)).isoformat() for i in range(n)]
    x = [V.ms(d0 + timedelta(weeks=i)) for i in range(n)]
    return x, t, {"m": [m(i) for i in range(n)], "p10": [0.2] * n, "p90": [0.8] * n, "c": [10000.0] * n}


class TestDeltaV3(Nen):
    def test_ds_ma_moi_view(self):
        for v, a in (("tongquan", "VN30"), ("bangquet", "VN100"), ("chuoi", "FPT"), ("nguon", "VN30")):
            with self.subTest(view=v):
                o = chay(self.moi, v, a)
                self.assertEqual([m["ma"] for m in o["ds_ma"]], VN100)
                self.assertEqual([m["ma"] for m in o["ds_ma"] if m["nhom"] == "VN30"], VN30)
                self.assertIn("tickers", o)  # giữ khoá cũ

    def test_chuoi_dai_thay_duong_p10_p90(self):
        ch = next(b for b in chay(self.moi, "chuoi", "FPT")["blocks"] if b["type"] == "chart")
        s = ch["series"]
        self.assertEqual([(x["name"], x["style"], x["mau"]) for x in s],
                         [("Vùng cạn cung (≤P10 3Y)", "band", "bull"), ("Vùng phân phối (≥P90 3Y)", "band", "bear"),
                          ("FFT tuần", "thin", "dim"), ("TB 4 tuần", "line", "bull"), ("Giá", "line", "amber")])
        self.assertTrue(s[0]["lo_min"] and not s[0]["hi_max"] and "y_hi" in s[0])
        self.assertTrue(s[1]["hi_max"] and not s[1]["lo_min"] and "y_lo" in s[1])
        self.assertLess(s[1]["alpha"], s[0]["alpha"])  # dải ≥P90 phủ tới đỉnh trục → nhạt hơn

    def test_chuoi_chu_thich(self):
        ch = next(b for b in chay(self.moi, "chuoi", "FPT")["blocks"] if b["type"] == "chart")
        tb4 = dict(zip(ch["x"], ch["series"][3]["y"]))
        pts = [a for a in ch["annotations"] if a["kind"] == "point"]
        nay = [a for a in pts if a["marker"] == "diamond"]
        self.assertEqual(len(nay), 1)
        self.assertEqual((nay[0]["mau"], nay[0]["pos"], nay[0]["uu_tien"]), ("amber", "left", 1))
        self.assertTrue(nay[0]["text"].startswith("Nay: TB4 ") and "/3Y" in nay[0]["text"])
        self.assertEqual(nay[0]["x"], max(x for x, v in tb4.items() if v is not None))
        vao = [a for a in pts if a["text"].startswith("Vào vùng")]
        self.assertTrue(0 < len(vao) <= 8)
        self.assertLessEqual(sum(a["uu_tien"] == 1 for a in vao), 4)
        for a in pts:
            if a["axis"] == "left":
                self.assertAlmostEqual(a["y"], tb4[a["x"]], 9)  # marker nằm đúng trên TB4
            self.assertIsNone(KHUYEN_NGHI.search(a["text"] + " " + a["sub"]), a)
        for a in vao:
            self.assertEqual((a["marker"], a["mau"]), ("tri_down", "bull") if "cạn cung" in a["text"] else ("tri_up", "bear"))
        gia = sorted(a["text"].split(" 2N ")[0] for a in pts if a["axis"] == "right")
        self.assertEqual(gia, ["Đáy giá", "Đỉnh giá"])
        self.assertEqual(sorted(a["text"] for a in ch["annotations"] if a["kind"] == "xband"),
                         ["26 tuần gần", "Nền 2N trước"])
        vl = [a for a in ch["annotations"] if a["kind"] == "vline"]
        self.assertTrue(vl and all(re.match(r"^CĐ [+−]\d+%$", a["text"]) and a["mau"] == "cyan" for a in vl), vl)

    def test_su_kien_vung_gop_va_vao_lai(self):
        # vào cạn cung tuần 5, rời 10, vào lại 12 (<6 tuần → gộp), rời 14; phân phối 30→33, vào lại 40 (≤13 tuần).
        def m(i):
            return 0.1 if 5 <= i < 10 or 12 <= i < 14 else (0.9 if 30 <= i < 33 or 40 <= i < 42 else 0.5)
        x, t, y = chuoi_gia(60, m)
        out = V.su_kien_vung(x, t, y)
        got = sorted(((a["x"] - x[0]) // TUAN, a["text"], a["uu_tien"]) for a in out)
        self.assertEqual(got, [(5, "Vào vùng cạn cung", 1), (14, "Rời vùng cạn cung", 3), (30, "Vào vùng phân phối", 1),
                               (33, "Rời vùng phân phối", 3), (40, "Vào vùng phân phối", 3),
                               (42, "Rời vùng phân phối", 3)])
        a = next(a for a in out if a["text"] == "Vào vùng cạn cung")
        self.assertEqual((a["marker"], a["mau"], a["pos"], a["sub"]), ("tri_down", "bull", "below", "02/2020"))
        self.assertTrue(a["tip"].startswith("Vào vùng cạn cung · tuần 07/02/2020 · TB4 0,100% · P10 0,200%"), a["tip"])

    def test_su_kien_vung_toi_da_8(self):
        x, t, y = chuoi_gia(200, lambda i: 0.1 if i % 20 in (10, 11) else 0.5)
        vao = [a for a in V.su_kien_vung(x, t, y) if a["text"].startswith("Vào")]
        tuan = sorted(((a["x"] - x[0]) // TUAN, a["uu_tien"]) for a in vao)
        self.assertEqual(tuan, [(50, 2), (70, 2), (90, 2), (110, 2), (130, 1), (150, 1), (170, 1), (190, 1)])

    def test_codong_gop_nhan_va_mau(self):
        cdm = {"bac": "EST", "cf_so_ky": 0, "moc": [
            {"ky": "2022-06", "co_dong": 100, "kieu": "quan_sat", "gia": 10000},
            {"ky": "2023-06", "co_dong": 60, "kieu": "quan_sat", "gia": 9000},
            {"ky": "2024-01", "co_dong": 65, "kieu": "noi_suy", "gia": 9500},
            {"ky": "2024-06", "co_dong": 70, "kieu": "quan_sat", "gia": 12000}]}
        out = {a["text"]: a for a in V.ann_codong(cdm)}
        self.assertEqual(set(out), {"Đỉnh CĐ 2N 100", "Đáy CĐ 2N 60"})  # mốc nội suy không gắn nhãn
        day = out["Đáy CĐ 2N 60"]  # chấm đáy trùng mốc −40% → một nhãn, tam giác giảm màu cyan
        self.assertEqual((day["marker"], day["mau"], day["sub"]), ("tri_down", "cyan", "06/2023 · −40% CĐ"))
        self.assertEqual((out["Đỉnh CĐ 2N 100"]["marker"], out["Đỉnh CĐ 2N 100"]["mau"]), ("dot", "dim"))
        vl = V.vline_cd(cdm, V.ms_ky("2020-01"), V.ms_ky("2026-01"))
        self.assertEqual([(a["text"], a["sub"], a["x"]) for a in vl], [("CĐ −40%", "06/2023", V.ms_ky("2023-06"))])
        self.assertEqual(V.vline_cd(cdm, V.ms_ky("2024-01"), V.ms_ky("2026-01")), [])  # ngoài khung trục

    def test_thitruong_zoom_chi_diem_nay(self):
        charts = [b for b in chay(self.moi, "thitruong", "VN100")["blocks"] if b["type"] == "chart"]
        for c in charts[:2]:
            self.assertEqual([s["style"] for s in c["series"]][:2], ["band", "band"])
        z = charts[2]
        self.assertNotIn("band", [s["style"] for s in z["series"]])
        self.assertEqual([(a["marker"], a["text"].split(":")[0]) for a in z["annotations"]],
                         [("diamond", "VN100 nay"), ("diamond", "VN30 nay")])


if __name__ == "__main__":
    unittest.main()
