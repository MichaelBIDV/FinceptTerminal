#!/usr/bin/env python3
"""
CONTRACT_DELTA v4 (22/09/2026) — lớp "Câu chuyện chủ thể": block story/timeline (V4.3), chú thích chart FFT × Giá
(vạch sự kiện · dải vùng gom · thoi vùng giá; tổng ≤28 — V4.4), view `cauchuyen`, CỔNG dừng, UNVERIFIED, thiếu tệp
_story trong bundle, và chạy mọi view trên dữ liệu THẬT của bridge (có / chưa có lớp câu chuyện).
Fixture câu chuyện: fixtures_v4/cau_chuyen.json — dạng ĐẦU RA bridge (fft_cauchuyen.py); chủ thể, số liệu, nguồn GIẢ.
Chạy:  <python> -m unittest discover -s tests/langkinh -v      (từ thư mục fincept-qt; cả 3.11 lẫn 3.14)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date

from lk_nen import HERE, KHONG_QD, MAU_SU_KIEN, NOTE_DUNG, SCRIPTS, VIEWS, Nen, chay

import fincept_langkinh_story as ST  # noqa: E402 — sys.path đã trỏ scripts/ trong lk_nen

FX4 = os.path.join(HERE, "fixtures_v4", "cau_chuyen.json")
THAT = os.path.expanduser("~/SECOND BRAIN-OBSIDIAN/_System/fincept_bridge/data")


def ms(s):
    return ST.ms(date.fromisoformat(s))


def gan(doc):
    """Gắn lớp câu chuyện fixture (đầu ra bridge) vào bản sao fft_langkinh.json."""
    with open(FX4, encoding="utf-8") as fh:
        fx = json.load(fh)
    doc["nguon"]["cau_chuyen"] = fx["nguon"]
    for s, v in fx["ma"].items():
        if isinstance(doc["ma"].get(s), dict):
            doc["ma"][s]["cau_chuyen"] = v


def dung(doc):
    gan(doc)
    doc["cong"].update(chu_ky=None, dung=True, ly_do_dung="M2 cũ hơn 150 ngày",
                       dong="CỔNG: [CẦN DATA — M2 cũ hơn 150 ngày] · không kết luận per-mã")


class TestCauChuyen(Nen):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cc = cls.ban_sao(sua=gan)

    def chart_gia(self, o):
        return next(b for b in o["blocks"] if b["type"] == "chart" and b["title"].endswith("FFT × Giá"))

    def test_chuoi_story_timeline_sau_tiles(self):
        o = chay(self.cc, "chuoi", "VHM")
        self.kiem_thanh_cong(o, "chuoi", "VN30")
        self.assertEqual([b["type"] for b in o["blocks"]][:4], ["tiles", "story", "timeline", "chart"])
        st = self.block(o, "story")
        self.assertEqual((st["ma"], st["link"]), ("VHM", "VHM"))
        self.assertEqual(st["tieu_de"], "[FIXTURE] Chủ thể A thâu tóm rồi mua thêm")
        vg = st["vung_gia"]
        self.assertEqual({k: vg[k] for k in ("lo", "hi", "vwap", "nay", "lech_pct", "bac", "nhan")},
                         {"lo": 43800, "hi": 46900, "vwap": 45200, "nay": 77000, "lech_pct": 70.35, "bac": "EST",
                          "nhan": "Vùng gom ước tính"})
        self.assertIn("sự kiện góp: VHM-01", vg["logic"])
        self.assertEqual([(x["ten"], x["bac"]) for x in st["chu_the"]],
                         [("Chủ thể A (fixture)", "FACT-T2"), ("Quỹ B (fixture)", "UNVERIFIED")])
        self.assertEqual((st["dong_co"]["bac"], st["diem_gay"]["bac"]), ("SS-T3", "EST"))
        self.assertIn("fixture/nguon_gia.md:313", st["dong_co"]["tip"])
        self.assertEqual(st["canh_bao"], ["1 mục thiếu tên/nguồn — không hiển thị (V4.0: không truy được → không đưa vào)",
                                          "2 mục UNVERIFIED — chỉ để theo dõi, " + KHONG_QD])
        self.assertIn("tạm dùng dữ liệu sẵn có, chưa nghiên cứu web mới", st["sub"])
        self.assertIn("4 sự kiện (FACT-T1 1 · FACT-T2 1 · SS-T3 1 · UNVERIFIED 1)", st["sub"])
        tl = self.block(o, "timeline")["items"]  # VHM-05 thiếu nguồn → bỏ
        self.assertEqual([(x["ngay"], x["hanh_dong"], x["gia"], x["bac"], x["mau"]) for x in tl], [
            ("05/08/2026", "Sự kiện khác", "—", "UNVERIFIED", "dim"),
            ("02/02/2026", "Bán 2,5 tr cp", "[CẦN DATA] vùng giá", "SS-T3", "amber"),
            ("14/11/2025", "Mua 5 tr cp", "61.500 (FACT-T1)", "FACT-T1", "cyan"),
            ("20/06/2025", "Thâu tóm 120 tr cp", "~45.200 (EST) · P25–P75 43.800–46.900", "FACT-T2", "cyan")])
        self.assertTrue(tl[0]["ngay_uoc"])
        self.assertEqual(tl[0]["mo_ta"], "Tin tăng sở hữu một nguồn (giả) · " + KHONG_QD)
        self.assertTrue(tl[3]["tip"].startswith("nguồn: fixture/nguon_gia.md:101 · bậc FACT-T2 · id VHM-01 · "
                                                "cửa sổ nguồn 02/05/2025 → 20/06/2025 · VWAP ~45.200"), tl[3]["tip"])

    def test_chuoi_chu_thich_su_kien(self):
        ch = self.chart_gia(chay(self.cc, "chuoi", "VHM"))
        an = ch["annotations"]
        self.assertLessEqual(len(an), 28)
        vl = [a for a in an if a["kind"] == "vline" and a["style"] == "dot"]
        self.assertEqual([(a["x"], a["text"], a["mau"], a["uu_tien"]) for a in vl], [
            (ms("2026-08-05"), "Quỹ B… sự kiện khác", "dim", 1), (ms("2026-02-02"), "Chủ thể C… bán 2,5tr", "amber", 1),
            (ms("2025-11-14"), "Chủ thể A… mua 5tr", "cyan", 1), (ms("2025-06-20"), "Chủ thể A… thâu tóm 120tr", "cyan", 1)])
        self.assertEqual(vl[0]["sub"], "~08/2026 · UNVERIFIED")
        self.assertTrue(vl[0]["tip"].endswith(KHONG_QD))
        hb = [a for a in an if a["kind"] == "hband"]
        self.assertEqual([(a["y0"], a["y1"], a["axis"], a["mau"], a["text"]) for a in hb],
                         [(43800, 46900, "right", "amber", "Vùng gom ước tính 43,8–46,9k (EST)")])
        th = [a for a in an if a["kind"] == "point" and a["axis"] == "right" and a["marker"] == "diamond"]
        self.assertEqual(sorted((a["x"], a["y"], a["text"], a["uu_tien"], a["mau"]) for a in th), [
            (ms("2025-06-20"), 45200, "~45.200 (EST)", 3, "cyan"), (ms("2025-11-14"), 61500, "61.500 (FACT-T1)", 3, "cyan")])
        for a in vl + hb + th:
            self.assertNotIn(a["mau"], ("bull", "bear"))
        self.assertEqual(sum(1 for a in an if a.get("marker") == "diamond" and a["axis"] == "left"), 1)  # "Nay" giữ nguyên
        self.assertEqual(len([a for a in an if a["kind"] == "xband"]), 2)
        self.assertTrue(ch["sub"].endswith(" · vạch dọc = sự kiện chủ thể · thoi = vùng giá sự kiện · dải ngang = "
                                           "vùng gom ước tính (EST)"), ch["sub"])

    def test_chuoi_toi_da_8_vach_va_28_chu_thich(self):
        an = self.chart_gia(chay(self.cc, "chuoi", "HPG"))["annotations"]
        self.assertLessEqual(len(an), 28)
        vl = [a for a in an if a["kind"] == "vline" and a["style"] == "dot"]
        self.assertEqual(sorted((a["x"], a["uu_tien"]) for a in vl), sorted(
            [(ms(d), 1) for d in ("2026-09-10", "2026-06-16", "2026-04-21", "2026-01-09")] +
            [(ms(d), 2) for d in ("2025-10-14", "2025-07-30", "2025-05-22", "2025-03-18")]))
        mau = {a["x"]: a["mau"] for a in vl}
        self.assertEqual([mau[ms(d)] for d in ("2025-10-14", "2025-05-22", "2025-03-18", "2026-04-21", "2026-06-16")],
                         ["amber", "dim", "warn", "dim", "cyan"])
        self.assertEqual([(a["y0"], a["y1"]) for a in an if a["kind"] == "hband"], [(10400, 18300)])
        self.assertEqual(sorted(a["y"] for a in an if a["kind"] == "point" and a["axis"] == "right" and
                                a["marker"] == "diamond"), [10600, 13400, 14100, 14800])

    def test_gioi_han_uu_tien(self):
        khac = [{"kind": "point", "x": i, "uu_tien": 3} for i in range(30)]
        cao = [{"kind": "point", "x": 100 + i, "uu_tien": 2} for i in range(5)] + [{"kind": "vline", "x": 200,
                                                                                    "uu_tien": 1}]
        dai = [{"kind": "xband", "x0": 0, "x1": 5}, {"kind": "hband", "y0": 1, "y1": 2}]
        cc = [{"kind": "point", "x": -1, "uu_tien": 3}, {"kind": "point", "x": -2, "uu_tien": 3}]
        ann = khac + cao + dai + cc
        out = ST.gioi_han(ann, cc)
        self.assertEqual(len(out), 28)
        self.assertEqual([a for a in ann if a in out], out)  # giữ thứ tự gốc
        for a in cao + dai + cc:
            self.assertTrue(any(a is b for b in out), a)
        self.assertEqual(sorted(a["x"] for a in out if a in khac), list(range(12, 30)))  # ưu tiên 3: mới nhất còn lại
        ngan = khac[:5]
        self.assertIs(ST.gioi_han(ngan, []), ngan)

    def test_cauchuyen_vn30_vn100(self):
        for sc, thu_tu, n_tl, chua in (("VN30", ["HPG", "VHM", "MBB"], 19, "ACB, CTG, FPT, TCX, VCB"),
                                       ("VN100", ["HPG", "PLX", "VHM", "MBB"], 20, "ACB, CTG, FPT, HDG, TCX, VCB")):
            with self.subTest(scope=sc):
                o = chay(self.cc, "cauchuyen", sc)
                self.kiem_thanh_cong(o, "cauchuyen", sc)
                self.assertEqual(o["title"], "Câu chuyện chủ thể — " + sc)
                self.assertEqual(o["blocks"][0]["title"], "Luật bằng chứng — lớp câu chuyện (V4.0)")
                self.assertIn("Tạm dùng dữ liệu sẵn có, chưa nghiên cứu web mới", o["blocks"][0]["text"])
                self.assertIn("không dùng cho quyết định", o["blocks"][0]["text"])
                self.assertEqual([b["ma"] for b in o["blocks"] if b["type"] == "story"], thu_tu)
                tl = self.block(o, "timeline")
                self.assertEqual(len(tl["items"]), n_tl)
                self.assertTrue(all(x["chu_the"].startswith(x["link"] + " · ") for x in tl["items"]))
                self.assertEqual(self.note(o, "Chưa có câu chuyện")["text"],
                                 "[CẦN DATA] %d mã chưa có câu chuyện tuyển chọn: %s." % (chua.count(",") + 1, chua))
                self.assertIn("STB: ngoài vũ trụ", self.note(o, "Lỗi tệp tuyển chọn")["text"])
                self.assertEqual(len(o["data"]), (19 if sc == "VN30" else 21) + chua.count(",") + 1)
        t = self.tiles(chay(self.cc, "cauchuyen", "VN30"))
        self.assertEqual((t["MÃ CÓ CÂU CHUYỆN"]["v"], t["VÙNG GIÁ GOM"]["v"], t["VÙNG GIÁ GOM"]["bac"]), ("3/8", "2/3", "EST"))
        sk = t["SỰ KIỆN THEO BẬC"]
        self.assertEqual((sk["v"], sk["bac"], sk["mau"]), ("19", "UNVERIFIED", "warn"))
        self.assertTrue(sk["s"].startswith("FACT-T1 4 · FACT-T2 7 · SS-T3 6 · EST 0 · UNVERIFIED 2"), sk["s"])
        self.assertEqual(t["TỆP TUYỂN CHỌN"]["v"], "22/09/2026")

    def test_cauchuyen_chua_co_lop(self):
        o = chay(self.moi, "cauchuyen", "VN30")  # fixture gốc: bridge chưa xuất lớp câu chuyện
        self.kiem_thanh_cong(o, "cauchuyen", "VN30")
        self.assertFalse([b for b in o["blocks"] if b["type"] in ("story", "timeline")])
        self.assertIn("nguon.cau_chuyen", self.note(o, "Chưa có lớp câu chuyện")["text"])
        self.assertEqual(self.tiles(o)["MÃ CÓ CÂU CHUYỆN"]["v"], "0/8")
        self.assertEqual(len(o["data"]), 8)
        self.assertEqual({r["06 Mô tả"] for r in o["data"]}, {"[CẦN DATA] chưa có câu chuyện"})
        o = chay(self.moi, "chuoi", "VHM")
        self.assertFalse([b for b in o["blocks"] if b["type"] in ("story", "timeline")])
        an = self.chart_gia(o)["annotations"]
        self.assertFalse([a for a in an if a["kind"] == "hband" or (a["kind"] == "vline" and a["style"] == "dot")])
        self.assertNotIn("sự kiện chủ thể", self.chart_gia(o)["sub"])

    def test_bridge_bo_lop_vi_thieu_tep(self):
        loi = "không thấy /x/fft_cauchuyen.json — bỏ lớp câu chuyện (chưa có bản tuyển chọn)"

        def bo(doc):
            doc["nguon"]["cau_chuyen"] = {"tep": "/x/fft_cauchuyen.json", "cap_nhat": None, "n_ma": 0, "n_su_kien": 0,
                                          "n_vung_gia_gom": 0, "bac_dem": {}, "loi": [loi]}
        d = self.ban_sao(sua=bo)
        o = chay(d, "cauchuyen", "VN100")
        self.kiem_thanh_cong(o, "cauchuyen", "VN100")
        self.assertIn(loi, self.note(o, "Chưa có lớp câu chuyện")["text"])
        o = chay(d, "nguon", "VN30")
        r = next(x for x in self.block(o, "table")["rows"] if x["tp"] == "Câu chuyện chủ thể (tuyển chọn tay, V4)")
        self.assertEqual((r["phu"], r["moc"]), ("0 mã · 0 sự kiện · 0 vùng gom · tạm dùng dữ liệu sẵn có", "—"))
        self.assertIn("câu chuyện: " + loi, self.note(o, "Lỗi / mã thiếu")["text"])
        r = next(x for x in self.block(chay(self.moi, "nguon"), "table")["rows"] if x["tp"].startswith("Câu chuyện"))
        self.assertEqual(r["phu"], "[CẦN DATA] bridge chưa xuất lớp câu chuyện")

    def test_nguon_dong_cau_chuyen(self):
        o = chay(self.cc, "nguon", "VN30")
        r = next(x for x in self.block(o, "table")["rows"] if x["tp"] == "Câu chuyện chủ thể (tuyển chọn tay, V4)")
        self.assertEqual((r["ng"], r["moc"], r["phu"]), ("/fixture/fft_cauchuyen.json", "22/09/2026",
                                                         "4 mã · 21 sự kiện · 2 vùng gom · tạm dùng dữ liệu sẵn có"))

    def test_cong_dung_story_van_hien(self):
        d = self.ban_sao(sua=dung)
        for v, arg in (("chuoi", "VHM"), ("cauchuyen", "VN30"), ("cauchuyen", "VN100")):
            with self.subTest(view=v, arg=arg):
                o = chay(d, v, arg)
                self.kiem_thanh_cong(o, v, "VN30" if v == "chuoi" else arg)
                self.assertEqual(o["cong"]["muc"], "dung")
                self.assertEqual((o["blocks"][0]["title"], o["blocks"][0]["text"]), ("CỔNG chưa xác định", NOTE_DUNG))
                st = [b for b in o["blocks"] if b["type"] == "story"]
                self.assertTrue(st)
                for b in st:
                    self.assertEqual(b["canh_bao"][-1], ST.CONG_DUNG)
        self.assertFalse([x for b in chay(self.cc, "cauchuyen", "VN30")["blocks"] if b["type"] == "story"
                          for x in b["canh_bao"] if x == ST.CONG_DUNG])

    def test_khong_bull_bear_moi_muc(self):
        for v, arg in (("chuoi", "HPG"), ("chuoi", "PLX"), ("cauchuyen", "VN100")):
            o = chay(self.cc, v, arg)
            for b in o["blocks"]:
                if b["type"] == "timeline":
                    self.assertLessEqual({x["mau"] for x in b["items"]}, MAU_SU_KIEN)
        mau = {x["hanh_dong"].split(" ")[0]: x["mau"] for x in self.block(chay(self.cc, "chuoi", "PLX"), "timeline")["items"]}
        self.assertEqual(mau, {"Pháp": "warn", "Cầm": "warn"})

    def test_thieu_tep_story_trong_bundle(self):
        """provision chỉ đồng bộ tệp đã có ở bundle → nếu thiếu _story: view khác chạy như cũ, `cauchuyen` báo lỗi rõ."""
        tmp = tempfile.mkdtemp(dir=self.tmp)
        for f in os.listdir(SCRIPTS):
            if f.startswith("fincept_langkinh") and f.endswith(".py") and f != "fincept_langkinh_story.py":
                shutil.copy(os.path.join(SCRIPTS, f), tmp)
        env = dict(os.environ, FINCEPT_BRIDGE_DATA=self.cc, PYTHONDONTWRITEBYTECODE="1")

        def run(*a):
            p = subprocess.run([sys.executable, os.path.join(tmp, "fincept_langkinh.py")] + list(a),
                               capture_output=True, env=env, timeout=60)
            self.assertEqual(p.returncode, 0, p.stderr.decode())
            return json.loads(p.stdout.decode("utf-8"))
        o = run("chuoi", "VHM")
        self.kiem_thanh_cong(o, "chuoi", "VN30")
        self.assertFalse([b for b in o["blocks"] if b["type"] in ("story", "timeline")])
        self.kiem_thanh_cong(run("tongquan", "VN30"), "tongquan", "VN30")
        o = run("cauchuyen", "VN30")
        self.assertEqual((o["success"], o["data"]), (False, []))
        self.assertIn("fincept_langkinh_story.py", o["error"])

    def test_dinh_dang(self):
        self.assertEqual([ST.sl(5e6), ST.sl(2.5e6, True), ST.sl(120e6), ST.sl(12_345_678), ST.sl(250_000), ST.sl(None)],
                         ["5 tr cp", "2,5tr", "120 tr cp", "12,3 tr cp", "250 nghìn cp", ""])
        self.assertEqual([ST.k_range(58000, 64000), ST.k_range(43800, 46900)], ["58–64k", "43,8–46,9k"])
        self.assertEqual([ST.kqd("x", "UNVERIFIED"), ST.kqd("", "UNVERIFIED"), ST.kqd("x", "EST")],
                         ["x · " + KHONG_QD, KHONG_QD, "x"])
        self.assertEqual([ST.bac_of({"bac": "xx"}), ST.bac_of({}), ST.bac_of({"bac": "SS-T3"})],
                         ["UNVERIFIED", "UNVERIFIED", "SS-T3"])
        self.assertEqual(ST.ngan_ten("Chủ thể A (fixture)"), "Chủ thể A…")


@unittest.skipUnless(os.path.isfile(os.path.join(THAT, "fft_langkinh.json")), "chưa có dữ liệu bridge thật")
class TestDuLieuThat(Nen):
    """Mọi view trên bản chụp dữ liệu THẬT của bridge (chép sang thư mục tạm — bridge có thể ghi lại giữa chừng)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.that = os.path.join(cls.tmp, "that")
        os.makedirs(cls.that)
        for f in ("fft_langkinh.json", "fft_codong.json"):
            if os.path.isfile(os.path.join(THAT, f)):
                shutil.copy(os.path.join(THAT, f), cls.that)
        shutil.copytree(os.path.join(THAT, "fft_chuoi"), os.path.join(cls.that, "fft_chuoi"))
        with open(os.path.join(cls.that, "fft_langkinh.json"), encoding="utf-8") as fh:
            cls.doc = json.load(fh)
        cls.vu_tru = sorted(cls.doc["ma"])

    def pham_vi(self, m):
        return "VN30" if "VN30" in (self.doc["ma"][m].get("nhom") or []) else "VN100"

    def test_moi_view_du_lieu_that(self):
        for v in VIEWS:
            for sc in ("VN30", "VN100"):
                with self.subTest(view=v, scope=sc):
                    self.kiem_thanh_cong(chay(self.that, v, sc), v, sc, self.vu_tru)
        for m in ("MSN", "STB", "VHM", "FPT", "HPG", "MBB"):
            if m in self.doc["ma"]:
                with self.subTest(ma=m):
                    o = chay(self.that, "chuoi", m)
                    self.kiem_thanh_cong(o, "chuoi", self.pham_vi(m), self.vu_tru)
                    st = [b for b in o["blocks"] if b["type"] == "story"]
                    if not isinstance(self.doc["ma"][m].get("cau_chuyen"), dict):  # chưa tuyển chọn xong → không có thẻ
                        self.assertFalse(st)
                    self.assertTrue(all(b["ma"] == m for b in st))

    def test_du_lieu_that_gan_cau_chuyen_fixture(self):
        d = os.path.join(self.tmp, "that_cc")
        shutil.copytree(self.that, d)
        p = os.path.join(d, "fft_langkinh.json")
        doc = json.loads(json.dumps(self.doc))
        gan(doc)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False)
        co = [m for m in ("HPG", "VHM", "MBB", "PLX") if m in doc["ma"]]
        for m in co:
            with self.subTest(ma=m):
                o = chay(d, "chuoi", m)
                self.kiem_thanh_cong(o, "chuoi", self.pham_vi(m), self.vu_tru)
                self.assertEqual([b["ma"] for b in o["blocks"] if b["type"] == "story"], [m])
                if o["cong"]["muc"] == "dung":  # dữ liệu thật hiện dừng CỔNG → note đầu + cảnh báo trong thẻ
                    self.assertEqual(o["blocks"][0]["text"], NOTE_DUNG)
                    self.assertEqual(self.block(o, "story")["canh_bao"][-1], ST.CONG_DUNG)
        for sc in ("VN30", "VN100"):
            with self.subTest(scope=sc):
                o = chay(d, "cauchuyen", sc)
                self.kiem_thanh_cong(o, "cauchuyen", sc, self.vu_tru)
                mem = [m for m in co if sc in (doc["ma"][m].get("nhom") or [])]
                # Dữ liệu thật nay đã có câu chuyện tuyển chọn cho nhiều mã → fixture chỉ cần là TẬP CON của thẻ story.
        self.assertTrue(set(mem) <= {b["ma"] for b in o["blocks"] if b["type"] == "story"})


if __name__ == "__main__":
    unittest.main()
