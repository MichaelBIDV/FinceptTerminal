#!/usr/bin/env python3
"""
Kiểm 11 view của fincept_langkinh.py trên fixtures theo CONTRACT §2.3/§2.5 + CONTRACT_DELTA v2 (stdlib unittest).
Chạy:  <python> -m unittest discover -s tests/langkinh -v      (từ thư mục fincept-qt)
Nằm ngoài scripts/ để không bị chép vào bundle (B6). Chạy dưới cả venv-numpy2 (3.11) lẫn 3.14.
"""
import os
import re
import unittest
from datetime import datetime

from lk_nen import (B, CT, L, NTH, SKILL, T, U3, VN100, VN30, VIEWS, Nen, bo_khoa_moi, chay, chu, md_tron,
                    md_tron_khoi)


class TestViews(Nen):
    def test_moi_view_moi_scope(self):
        for v in VIEWS:
            for sc, mem in (("VN30", VN30), ("VN100", VN100)):
                with self.subTest(view=v, scope=sc):
                    o = chay(self.moi, v, sc)
                    self.kiem_thanh_cong(o, v, sc)
                    self.assertEqual(o["tickers"], mem)
                    self.assertTrue(o["tuoi"].startswith("cập nhật"))
                    self.assertEqual(o["cong"]["muc"], "canh_bao")

    def test_scope_mac_dinh_va_chu_thuong(self):
        self.assertEqual(chay(self.moi, "tongquan")["scope"], "VN30")
        self.assertEqual(chay(self.moi, "BANGQUET", "vn100")["scope"], "VN100")
        self.assertEqual(chay(self.moi, "ChuThe", "vn100")["scope"], "VN100")

    def test_tongquan(self):
        o = chay(self.moi, "tongquan", "VN30")
        self.assertEqual(o["blocks"][0]["pill"], "CỔNG")
        self.assertEqual(o["cong"]["dong"], "CỔNG: [tiền đắt] · chủ thể [theo mã — 3/8 SS-T3 · 3/8 EST (W37 10/09) · "
                                            "1/8 xung đột · còn lại CẦN DATA] · playbook [Theo người vay có mục đích]")
        self.assertEqual(o["cong"]["chi_tiet"],
                         "td 17,4% · M2 4,2% (T6/26) · GAP 13,2 · OMO 4,50% · ON 4,50% (18/09) Δ3p +13bp · "
                         "Corporate 32 sự kiện/21 mã (2025), 15/10 (2026 tới 07) — TV 26/08")
        self.assertIn("Q2 Corporate (Toàn Vũ 26/08/2026 · SS-T3): 32 sự kiện/21 mã (2025), 15/10 (2026 tới 07) · mẫu /30",
                      chu(o["blocks"][0]["text"]))
        o100 = chay(self.moi, "tongquan", "VN100")
        self.assertIn("3/10 SS-T3 · 4/10 EST (W37 10/09) · 1/10 xung đột · còn lại CẦN DATA", o100["cong"]["dong"])
        t = self.tiles(o)
        self.assertEqual(t["VN-INDEX · PHIÊN 21/09"]["v"], "1.799,67")
        self.assertEqual(t["VN-INDEX · PHIÊN 21/09"]["s"], "−0,88% · −15,99 điểm")
        self.assertEqual(t["CỔ ĐÔNG BÙNG NỔ ≥+50% TỪ ĐÁY 2N"]["v"], "15/30")  # luật D3.3 (EST); W37 13/30 ở phụ đề
        self.assertEqual(t["ĐẶC LẠI Ở ĐÁY 2N"]["v"], "6/30")
        self.assertTrue(t["ĐẶC LẠI Ở ĐÁY 2N"]["s"].endswith(T.CD_DAC_LAI))
        self.assertTrue(t["MARKET FFT VN30 · TB 4 TUẦN"]["s"].endswith("· 8/8 mã có FF"))
        self.assertTrue(t["MARKET FFT VN100 · VỊ TRÍ 3Y"]["s"].endswith("· 9/10 mã có FF"))
        self.assertNotEqual(t["MARKET FFT VN30 · TB 4 TUẦN"]["mau"], "warn")
        bd = self.block(o, "table", 0)
        chg = [abs(r["_sort"]["chg"]) for r in bd["rows"]]
        self.assertEqual(chg, sorted(chg, reverse=True))
        self.assertEqual([c["label"] for c in bd["cols"]],
                         ["Mã", "Giá", "%", "KL", "×20d", "FFT ngày", "FFT 4w", "Bội số", "pct3Y"])
        self.assertIn(T.MUC_EST, bd["caption"])
        kl = self.block(o, "table", 1)
        self.assertIn(T.MUC_EST, kl["caption"])
        x20 = [r["_sort"]["x20"] for r in kl["rows"]]
        self.assertEqual(x20, sorted(x20, reverse=True))
        self.assertEqual(self.note(o, "Quy tắc đọc")["text"], T.QUY_TAC_DOC)
        self.assertTrue(T.QUY_TAC_DOC.endswith("Pattern C (Toàn Vũ · mũ sắt + chân cầu) chưa cài, chỉ ghi nhận."))
        self.assertEqual(self.hang(bd, "VHM")["_tag"]["ma"], "avoid*")

    def test_do_phu_market_fft_b5(self):
        def it(doc):
            doc["thi_truong"]["VN100"]["so_ma"] = 7  # 7/10 < 0,8
        d = self.ban_sao(sua=it)
        t = self.tiles(chay(d, "tongquan", "VN30"))
        x = t["MARKET FFT VN100 · VỊ TRÍ 3Y"]
        self.assertEqual(x["mau"], "warn")
        self.assertTrue(x["s"].endswith("7/10 mã có FF — " + T.PHU_THIEU))
        self.assertNotEqual(t["MARKET FFT VN30 · TB 4 TUẦN"]["mau"], "warn")
        t = self.tiles(chay(d, "thitruong", "VN30"))
        self.assertEqual(t["VN100 · SỐ MÃ CÓ FF"]["v"], "7/10")
        self.assertEqual(t["VN100 · SỐ MÃ CÓ FF"]["mau"], "warn")
        self.assertEqual(t["VN100 · TB 4 TUẦN"]["mau"], "warn")
        self.assertIn(T.PHU_THIEU, t["VN100 · TB 4 TUẦN"]["s"])
        self.assertEqual(t["VN30 · SỐ MÃ CÓ FF"]["v"], "8/8")
        self.assertNotEqual(t["VN30 · SỐ MÃ CÓ FF"]["mau"], "warn")
        t = self.tiles(chay(self.ban_sao(sua=bo_khoa_moi), "thitruong", "VN30"))  # không có so_ma → n_co_du_lieu
        self.assertEqual(t["VN100 · SỐ MÃ CÓ FF"]["v"], "9/10")

    def test_so_bo_r15(self):
        def sb(doc):
            doc["phien"]["trang_thai"] = "SƠ BỘ"
        d = self.ban_sao(sua=sb)
        o = chay(d, "tongquan", "VN30")
        self.assertEqual(o["title"], "Tổng quan phiên 21/09/2026 · SƠ BỘ · VN30")
        self.assertIn("VN-INDEX · PHIÊN 21/09 · SƠ BỘ", self.tiles(o))
        self.assertTrue(self.block(o, "table")["sub"].startswith("phiên 21/09 · SƠ BỘ ·"))
        self.assertTrue(chay(d, "bangquet", "VN30")["sub"].endswith("phiên 21/09/2026 · SƠ BỘ"))
        self.assertNotIn("SƠ BỘ", chay(self.moi, "tongquan", "VN30")["title"])

        def chot(doc):
            doc["phien"]["trang_thai"] = "ĐÃ CHỐT"
        self.assertNotIn("SƠ BỘ", chay(self.ban_sao(sua=chot), "tongquan")["title"])
        hom_nay = datetime.now().strftime("%Y-%m-%d")

        def trong_phien(doc):  # bridge cũ chưa có trang_thai → heuristic: cap_nhat cùng ngày phiên, trước 15:05
            doc["phien"]["ngay"] = hom_nay
            doc["cap_nhat"] = hom_nay + " 10:30"
        self.assertEqual(B.so_bo({"phien": {"ngay": hom_nay}, "cap_nhat": hom_nay + " 10:30"}), " · SƠ BỘ")
        self.assertEqual(B.so_bo({"phien": {"ngay": hom_nay}, "cap_nhat": hom_nay + " 15:30"}), "")
        self.assertEqual(B.so_bo({"phien": {"ngay": "2026-09-21"}, "cap_nhat": "2026-09-22 10:30"}), "")
        self.assertIn("· SƠ BỘ", chay(self.ban_sao(sua=trong_phien), "tongquan")["title"])

    def test_bangquet_cot_va_co_du_lieu(self):
        o = chay(self.moi, "bangquet", "VN30")
        t = self.block(o, "table")
        self.assertEqual([c["label"] for c in t["cols"]],
                         ["Mã", "Giá", "%ngày", "FFT 4w", "8w", "26w", "52w", "P10 3Y", "P90 3Y", "×P10",
                          "Vị trí trong 3 năm", "Pall", "Ô 8 tuần", "52w", "2Y", "ΔVol 2Y", "FF"])
        pct = [r["_sort"].get("vt") for r in t["rows"]]
        self.assertEqual(pct, sorted(pct))
        fpt = self.hang(t, "FPT")
        self.assertEqual(fpt["_tag"]["ma"], "12%")
        self.assertEqual(fpt["_vien"], "bear")
        self.assertEqual(fpt["o8"], "FFT↑ × Giá↔")
        self.assertEqual(fpt["_mau"]["o8"], "dim")
        self.assertEqual(fpt["_bar"]["vt"]["mau"], "bear")
        self.assertEqual(fpt["_tag"]["ff"], "⚠")  # R3 — FF cũ hơn CA
        self.assertIn("FF cũ hơn điều chỉnh CA", fpt["_tip"]["ff"])
        mbb = self.hang(t, "MBB")
        self.assertEqual((mbb["_tag"]["ff"], mbb["_mau"]["ff"]), ("⚠", "warn"))  # I3
        self.assertIn("VCI tự mâu thuẫn", mbb["_tip"]["ff"])
        self.assertEqual(self.hang(t, "TCX")["_tag"]["xp"], "⚠")  # I4
        self.assertNotIn("ff", self.hang(t, "VCB").get("_tag", {}))
        vhm = self.hang(t, "VHM")
        self.assertEqual(vhm["_tag"]["ma"], "avoid*")  # R10
        self.assertIn("M:867", vhm["_tip"]["ma"])
        cap = t["caption"]
        self.assertIn("Tuần 25/09 dở dang — 1 phiên; TB 4 tuần đã gồm tuần dở dang", cap)
        self.assertIn("ΔVol 2Y dương = khối lượng đã co lại", cap)
        self.assertIn(T.MUC_EST, cap)
        self.assertIn("VCI tự mâu thuẫn: free_float vs issue_share×% — mức FFT EST — MBB ×1,25", cap)  # gom theo mẫu
        self.assertIn("đọc percentile thận trọng — TCX", cap)
        self.assertIn("Tag * = VHM (", cap)
        t = self.block(chay(self.moi, "bangquet", "VN100"), "table")
        xp = [r["_sort"]["xp"] for r in t["rows"] if "xp" in r.get("_sort", {})]
        self.assertEqual(xp, sorted(xp))
        self.assertEqual([r["ma"] for r in t["rows"]][-2:], ["HDG", "TCX"])  # thiếu ×P10 → cuối
        hdg = self.hang(t, "HDG")
        self.assertEqual((hdg["ma4"], hdg["vt"]), ("—", "—"))
        self.assertNotIn("_vien", hdg)
        self.assertIn("HDG (thiếu free float)", t["caption"])
        self.assertEqual(self.hang(t, "MBB")["_tag"]["ma"], "watch")

    def test_matran(self):
        o = chay(self.moi, "matran", "VN100")
        mx = self.block(o, "matrix")
        self.assertEqual(mx["cols"], ["Giá ↑", "Giá ↓ / đi ngang"])
        o_ = {(i, j): [c["ma"] for c in cell["chips"]] for i, r in enumerate(mx["rows"]) for j, cell in enumerate(r["cells"])}
        self.assertIn("FPT", o_[(0, 1)])  # FFT↑ × Giá↔ → cột phải
        self.assertIn("PLX", o_[(2, 1)])  # FFT↔ × Giá↓
        self.assertIn("TCX", o_[(1, 0)])  # FFT↓ × Giá↑
        self.assertNotIn("HDG", sum(o_.values(), []))
        self.assertEqual(mx["rows"][0]["cells"][0]["title"], "Markup có retail")
        self.assertEqual(mx["rows"][1]["cells"][1]["note"], "Hoặc đang gom xong chờ markup, hoặc \"mất hút thanh khoản\" "
                                                            "sau khi sập — phân biệt bằng ý đồ chủ thể.")
        chips = mx["rows"][0]["cells"][1]["chips"]
        self.assertEqual([int(c["v"]) for c in chips], sorted(int(c["v"]) for c in chips))
        self.assertEqual({c["ma"]: c["mau"] for c in chips}["MBB"], "info")
        qu = self.note(o, "Quy ước")["text"]
        self.assertIn("không có trong v1.7 bản cuối", qu)
        self.assertIn(T.M718, chu(qu))  # D6.5
        self.assertEqual(T.M718, "Trong kỳ tiền đắt, ô đáng tiền chỉ có giá trị khi chủ thể còn mục tiêu huy động "
                                 "(Khối 8).")

    def test_bocung(self):
        o = chay(self.moi, "bocung", "VN100")
        sc = self.block(o, "scatter")
        self.assertEqual(sc["quadrants"]["bl"], "[CẦN DATA]")
        mau = {p["label"]: p["mau"] for p in sc["points"]}
        self.assertEqual((mau["FPT"], mau["PLX"], mau["HPG"]), ("bull", "bear", "dim"))
        bo, xa = self.block(o, "table", 0), self.block(o, "table", 1)
        self.assertEqual([r["ma"] for r in bo["rows"]], ["FPT"])
        d2 = [r["_sort"]["d2"] for r in xa["rows"]]
        self.assertEqual(d2, sorted(d2, reverse=True))
        self.assertEqual([c["label"] for c in bo["cols"]],
                         ["Mã", "ΔFFT 2N", "Giá 2N", "ΔFFT 1N (EST)", "Giá 1N", "P 3Y", "Chủ thể"])
        self.assertIn("Ô trái–dưới: bản gốc không định danh — cấm tự đặt tên", self.block(o, "note")["text"])
        ct = {r["01 Mã"]: r["07 Chủ thể"] for r in o["data"]}  # D6.6
        self.assertEqual(ct["FPT"], "cần · EST")
        self.assertEqual(ct["MBB"], "cần · SS-T3")
        self.assertEqual(ct["ACB"], "trung tính · EST")
        self.assertEqual(ct["CTG"], "⚠ xung đột")
        self.assertEqual(ct.get("TCX", "—"), "—")
        self.assertIsNone(CT.ct_hien({}))

    def test_xephang(self):
        o = chay(self.moi, "xephang", "VN100")
        it = self.block(o, "lists")["items"]
        self.assertEqual([x["title"] for x in it], ["Cạn cung nhất · P 3 năm", "Phân phối nhất · P 3 năm",
                                                    "Lệch cửa sổ lớn nhất · 3Y thấp hơn all", "Đổi trạng thái vs tuần trước"])
        self.assertTrue(re.match(r"^CTG P13 \(all P\d+ · ×P10 [\d,]+×\)$", it[0]["rows"][0]), it[0]["rows"][0])
        self.assertIn("VCB P17 (all P46 · ×P10 1,17×)", it[0]["rows"])
        self.assertIn("VCB 3Y P17 vs all P46 (−29)", it[2]["rows"])
        self.assertTrue(it[3]["rows"][0].startswith("PLX phân phối → giữa · P80 → P74"))
        cap = T.XH_CAPTION.format(n=3, N=10)  # D6.7 — CTG (xung đột), HDG, TCX
        self.assertEqual(cap, "Đo lường, không phải xếp hạng cơ hội — Step 7 chưa trả lời cho 3/10 mã (R:184).")
        self.assertTrue(o["sub"].startswith(cap))
        t = self.block(o, "table")
        self.assertTrue(t["caption"].startswith(cap))
        self.assertEqual([c["label"] for c in t["cols"]][1:3], ["Lớp FFT (P3Y) tuần trước", "Lớp FFT (P3Y)"])  # R13
        self.assertIn("06 Lớp FFT (P3Y)", o["data"][0])
        o30 = chay(self.moi, "xephang", "VN30")
        self.assertEqual([r["ma"] for r in self.block(o30, "table")["rows"]], ["HPG"])  # PLX ngoài VN30
        self.assertIn("2/8 mã", o30["sub"])

    def test_thitruong(self):
        o = chay(self.moi, "thitruong", "VN30")
        charts = [b for b in o["blocks"] if b["type"] == "chart"]
        self.assertEqual([c["title"] for c in charts], ["Market FFT VN100 — tuần", "Market FFT VN30 — tuần",
                                                         "Zoom 3 năm — VN100 vs VN30, TB 4 tuần"])
        self.assertEqual(len(charts[2]["x"]), 157)
        # DELTA v3 V3.4.1 — hai dải P10/P90 (vẽ dưới) thay hai đường; FFT tuần + TB 4 tuần vẽ trên.
        self.assertEqual([(s["style"], s["mau"]) for s in charts[0]["series"]],
                         [("band", "bull"), ("band", "bear"), ("thin", "dim"), ("line", "amber")])
        self.assertEqual(charts[1]["series"][3]["mau"], "info")
        self.assertEqual(len(self.block(o, "tiles")["items"]), 8)
        bb = o["blocks"][-1]["text"]
        self.assertIn("không so mức", bb)
        self.assertIn(T.R5, bb)  # R5 — chỉ ghi chú, không vẽ đường 0,35/1,30
        self.assertEqual(sum(len(c["series"]) for c in charts), 10)
        self.assertEqual(charts[0]["x"][-1], 1790294400000)  # 25/09/2026 00:00 UTC
        self.assertEqual(o["data"][0]["10 Số mã có FF"], "8/8")

    def test_codong(self):
        o = chay(self.moi, "codong", "VN30")
        t = self.block(o, "table")
        self.assertEqual([c["label"] for c in t["cols"]],
                         ["Mã", "Cổ đông (kỳ)", "Kiểu mốc cuối", "CF", "Kỳ quan sát cuối", "vs đáy 2N", "vs đỉnh 2N",
                          "Giá từ đỉnh CĐ (KHO)", "CP bình quân/cổ đông", "k cặp cuối (nhãn)", "Ô cặp cuối",
                          "Tăng vốn 25–26", "Lớp", "pct3Y (FFT)", "Bậc"])
        self.assertEqual([r["ma"] for r in t["rows"]], ["FPT", "MBB", "ACB", "VHM"])  # vs_day giảm dần
        vhm = self.hang(t, "VHM")
        self.assertEqual((vhm["cd"], vhm["cf"], vhm["vd"], vhm["vdi"]), ("24.711 (2026-07)", "CF×4", "0%", "−22%"))
        self.assertEqual((vhm["kqs"], vhm["k"], vhm["lop"]), ("2025-07 · 13 th", "CF — chưa có số mới",
                                                              "Đặc lại — sát đáy 2N, dưới đỉnh 2N ≥5%"))
        fpt = self.hang(t, "FPT")
        self.assertEqual(fpt["_tag"]["cd"], "số tròn")
        self.assertEqual((fpt["k"], fpt["tv"], fpt["kieu"]), ("số tròn — cấm làm mẫu số k", "có", "quan sát"))
        self.assertEqual(fpt["_tag"]["lop"], "thưởng/ESOP?")
        mbb = self.hang(t, "MBB")
        self.assertEqual((mbb["k"], mbb["_tag"]["vd"]), ("53.700 (Chuyển tiếp)", "W37 +41%"))
        self.assertEqual(mbb["_tip"]["vd"], "W37 (mọi mốc, gồm nội suy): +40,9%")
        self.assertNotIn("vd", fpt.get("_tag", {}))  # số W37 = số quan sát → không gắn tag
        acb = self.hang(t, "ACB")
        self.assertEqual((acb["lop"], acb["_tag"]["lop"], acb["kieu"], acb["_mau"]["kqs"]),
                         ("—", "không đủ mốc", "chép", "warn"))
        tl = [x["v"] for x in self.block(o, "tiles")["items"]]
        self.assertEqual(tl[:3], ["15/30", "6/30", "2/30"])
        tt = self.tiles(o)
        self.assertEqual(tt["MỐC QUAN SÁT/NỘI SUY/CHÉP"]["v"], "339/443/31")
        self.assertEqual(tt["Q2 2025"]["v"], "32 sự kiện · 21/30 mã")
        self.assertIn("sửa nội bộ 20/08/2026", tt["NGÀY TỆP TOÀN VŨ"]["s"])
        note = chu(self.block(o, "note")["text"])
        for i in (2, 3, 4, 6):
            self.assertIn(md_tron(L.CAU_BAT_BUOC[i]), note)
        self.assertIn("443/813 mốc là công thức nội suy của tệp, 31 mốc chép — vs đáy/đỉnh tính trên mốc quan sát; "
                      "số W37 (gồm mốc nội suy) ở tooltip.", note)  # D6.3 nguyên văn
        self.assertIn("Đặc lại: vs đáy ≤ +1% và vs đỉnh ≤ −5% (PT:182, EST).", note)
        self.assertEqual(len(o["data"]), 4)

    def test_chuthe(self):
        o = chay(self.moi, "chuthe", "VN30")
        self.kiem_thanh_cong(o, "chuthe", "VN30")
        bb = self.note(o, "Câu bắt buộc — Pillar III")
        self.assertEqual(bb["pill"], "Bắt buộc")
        txt = chu(bb["text"])
        for cau in ("Mục đích lớn của chủ thể khi giữ/kéo giá là gì, và mục đích đó CÓ LỚN HƠN chi phí kéo không?",
                    "mỗi dòng cần CBTT hoặc nghị quyết gốc trước khi dùng cho quyết định",
                    "Chưa trả lời → không xếp hạng cơ hội · owner_intent chưa có CBTT gốc → SS-T3, chỉ định vị",
                    "'% khoá cao' và 'free float nhỏ' là hai cách nói cùng một con số … Cấm đếm nó hai lần.",
                    "không suy thành 'trung tính'",
                    "Nhãn là snapshot W37 10/09 — kỳ mới phải chấm lại (H17:111). Bằng chứng không đổi nhãn."):
            self.assertIn(cau, txt)
        tt = self.tiles(o)
        self.assertEqual((tt["CÓ NHÃN"]["v"], tt["CÓ NHÃN"]["s"], tt["CÓ NHÃN"]["bac"]),
                         ("6/8", "SS-T3 3 · EST 3 · W37 10/09", "EST"))
        self.assertEqual(tt["XUNG ĐỘT"]["v"], "1/8")
        self.assertEqual(tt["CẦN DATA"]["v"], "1/8")
        self.assertEqual((tt["Q2 CORPORATE 2025"]["v"], tt["Q2 CORPORATE 2025"]["s"]),
                         ("32 sự kiện · 21/30 mã", "2026 tới 07: 15/10 · SS-T3"))
        self.assertEqual(tt["NGUỒN SỞ HỮU"]["v"], "KHO 5 · dự phòng Vietcap 2")
        self.assertEqual(tt["Ý ĐỒ CURATED"]["v"], "26 · 10 SS-T3 · 16 UNVERIFIED")
        t = self.block(o, "table")
        self.assertEqual([c["label"] for c in t["cols"]],
                         ["Mã", "Chủ thể (bậc)", "Nguyên văn", "Nhà nước %", "Khoá % (=100−FF)", "NN/trần NN %",
                          "Thu tiền 24T (n · mới nhất)", "Không thu tiền 24T (n)", "Tăng vốn 25–26 (TV)",
                          "Ý đồ curated (n · mới nhất · bậc)", "pct3Y", "Ô 2N", "Playbook", "⚠"])
        # xung đột → cần → không cần → trung tính → chưa nhãn; A→Z trong nhóm
        self.assertEqual([r["ma"] for r in t["rows"]], ["CTG", "FPT", "MBB", "VHM", "HPG", "VCB", "ACB", "TCX"])
        for r in t["rows"]:
            self.assertTrue(set(r.get("_mau", {}).values()) <= {"info", "amber", "dim"}, r)  # không bull/bear
            self.assertIn(r.get("_vien", ""), ("info", "amber", "dim", ""))
            self.assertEqual(r["_link"], r["ma"])
        ctg, fpt, mbb, tcx = (self.hang(t, x) for x in ("CTG", "FPT", "MBB", "TCX"))
        # bốn trạng thái nhãn: SS-T3 · EST · xung đột · chưa nhãn
        self.assertEqual((mbb["ct"], mbb["_tag"]["ct"]), ("cần", "SS-T3"))
        self.assertEqual((fpt["ct"], fpt["_tag"]["ct"]), ("cần", "EST"))
        self.assertEqual((ctg["ct"], ctg["pb"]), ("⚠ trung tính ⟷ cần", "CẦN DATA"))
        self.assertNotIn("ct", ctg.get("_tag", {}))
        self.assertIn("k13: Trung tính · tăng vốn ⟷ q2: ", ctg["nv"])
        self.assertEqual((tcx["ct"], tcx["pb"], tcx["yd"], tcx["thu"]), ("[CẦN DATA]", "CẦN DATA", "[CẦN DATA]",
                                                                        "[CẦN DATA]"))
        self.assertEqual(fpt["nv"], "Có · thưởng 171 tr.cp (+1 nguồn)")
        self.assertEqual((fpt["pb"], fpt["nn"], fpt["khoa"], fpt["room"], fpt["tv"], fpt["kthu"]),
                         ("Theo phase, không theo định giá", "5,63%", "15,0%", "58%", "có", "2"))
        vcb = self.hang(t, "VCB")
        self.assertEqual(vcb["thu"], "1 · Phát hành riêng lẻ 28/04/2026")
        self.assertEqual(vcb["_mau"]["thu"], "amber")
        self.assertIn("Phát hành riêng lẻ", vcb["cb"])  # cảnh báo đối chiếu nhãn — nhãn không đổi
        self.assertEqual((vcb["ct"], vcb["pb"]), ("không cần", "Bo cung / đi ngang"))
        self.assertEqual(self.hang(t, "ACB")["pb"], "CẦN DATA — v1.7 không định nghĩa ô tiền đắt × trung tính")
        self.assertEqual(mbb["_tag"]["thu"], "có thể thiếu")
        self.assertEqual(mbb["_tag"]["room"], "kín room")
        self.assertEqual(self.hang(t, "VHM")["thu"], "[CẦN DATA]")
        self.assertEqual(self.hang(t, "VHM")["yd"], "2 · capital_raise dự kiến 15/10/2026 · SS-T3")
        self.assertEqual(self.hang(t, "HPG")["yd"], "1 · pledge ~01/06/2024 · UNVERIFIED")
        self.assertEqual(t["caption"], T.CT_CAPTION)
        self.assertEqual(o["data"], L.phang(t))
        yd = self.block(o, "table", 1)
        self.assertEqual(yd["title"], "Ý đồ chủ thể — sự kiện curated (owner_intent)")
        self.assertEqual([c["label"] for c in yd["cols"]], ["Mã", "Loại", "Ngày", "Tiêu đề", "Nguồn", "Bậc"])
        self.assertEqual([(r["ma"], r["ngay"]) for r in yd["rows"]],
                         [("VHM", "dự kiến 15/10/2026"), ("VHM", "20/11/2025"), ("HPG", "~01/06/2024")])
        self.assertIn("owner_intent: TCX", self.note(o, "Lỗi nguồn chủ thể")["text"])
        self.assertIn("ngày tuổi (không tự hết hạn)", o["sub"])
        o = chay(self.moi, "chuthe", "VN100")
        t = self.block(o, "table")
        self.assertEqual([r["ma"] for r in t["rows"]][-2:], ["HDG", "TCX"])
        hdg = self.hang(t, "HDG")
        self.assertEqual(hdg["ct"], "[CẦN DATA]")
        self.assertTrue(hdg["nv"].startswith("ghi chú ngành: chủ thể (Becamex, Kinh Bắc, VRG) đều có nhu cầu vốn"))
        self.assertIn("chỉ ghi chú", hdg["_tip"]["nv"])  # khẳng định K5 chi_ghi_chu không thành nguyên văn nhãn
        self.assertEqual(self.hang(t, "PLX")["_tag"]["nn"], "≥75%")
        self.assertEqual(self.tiles(o)["CÓ NHÃN"]["v"], "7/10")
        for r in t["rows"]:  # chưa nhãn không bao giờ thành "trung tính"
            if r["ma"] in ("HDG", "TCX"):
                self.assertNotIn("trung tính", r["ct"] + r["pb"])

    def test_chuthe_bang_chung_khong_doi_nhan(self):
        def doi(doc):
            for m in doc["ma"].values():
                bc = m["chu_the"].get("bang_chung") or {}
                bc["phat_hanh_24t"] = {"thu_tien": [{"ngay": "2026-01-01", "loai": "Phát hành riêng lẻ"}] * 3,
                                       "khong_thu_tien": [], "khac": []}
                bc["so_huu"] = {"nha_nuoc_pct": 99.0, "nn_pct": 1.0, "tran_nn_pct": 1.0, "nn_tren_tran_pct": 100,
                                "kin_room": True, "nha_nuoc_chi_phoi": True, "nguon": "kho_free_float"}
                bc["y_do"] = []
                m["chu_the"]["bang_chung"] = bc
        d = self.ban_sao(sua=doi)
        a = self.block(chay(self.moi, "chuthe", "VN100"), "table")
        b = self.block(chay(d, "chuthe", "VN100"), "table")
        self.assertEqual([(x["ma"], x["ct"], x["pb"]) for x in a["rows"]], [(y["ma"], y["ct"], y["pb"]) for y in b["rows"]])
        self.assertEqual(chay(self.moi, "tongquan")["cong"]["dong"], chay(d, "tongquan")["cong"]["dong"])
        self.assertEqual(chay(self.moi, "chuoi", "HPG")["cong"]["dong"], chay(d, "chuoi", "HPG")["cong"]["dong"])

    def test_chuoi(self):
        for m, sc in (("FPT", "VN30"), ("TCX", "VN30"), ("PLX", "VN100"), ("HDG", "VN100"), ("CTG", "VN30")):
            with self.subTest(ma=m):
                o = chay(self.moi, "chuoi", m.lower())
                self.kiem_thanh_cong(o, "chuoi", sc)
                self.assertEqual(o["tickers"], VN100)
                self.assertEqual(o["title"].split(" · ")[0], m)
        self.assertEqual(chay(self.moi, "chuoi")["title"].split(" · ")[0], "FPT")
        o = chay(self.moi, "chuoi", "FPT")
        self.assertEqual(o["cong"]["dong"],
                         "CỔNG: [tiền đắt] · chủ thể [cần] thị trường · playbook [Theo phase, không theo định giá]")
        self.assertTrue(o["cong"]["chi_tiet"].endswith("— TV 26/08 · chủ thể EST · W37 10/09 · M:873-883 + PI:53-54"))
        charts = [b for b in o["blocks"] if b["type"] == "chart"]
        self.assertEqual([c["title"] for c in charts], ["FPT · FFT × Giá", "FPT · Số cổ đông × giá mốc"])
        cd = charts[1]["series"]
        self.assertEqual([(s["name"], s["style"], s["mau"], s["axis"]) for s in cd],
                         [("Cổ đông (quan sát)", "bar", "cyan", "left"), ("Cổ đông (nội suy/chép)", "dot", "dim", "left"),
                          ("Giá TV (danh nghĩa, chưa điều chỉnh CA)", "line", "amber", "right")])
        self.assertEqual([x is None for x in cd[0]["y"]], [False, False, True, False])
        self.assertEqual([x is None for x in cd[1]["y"]], [True, True, False, True])
        t = self.tiles(o)
        self.assertEqual((t["CHỦ THỂ"]["v"], t["CHỦ THỂ"]["bac"], t["CHỦ THỂ"]["mau"]), ("cần", "EST", "info"))
        self.assertIn("Có · thưởng 171 tr.cp", t["CHỦ THỂ"]["s"])
        self.assertIn("W37 10/09", t["CHỦ THỂ"]["s"])
        self.assertEqual((t["SỞ HỮU"]["v"], t["SỞ HỮU"]["bac"]), ("NN 28,6% · NN/trần 58%", "FACT-T2"))
        self.assertEqual(t["PLAYBOOK"]["v"], "[Theo phase, không theo định giá]")
        self.assertEqual((t["×P10"]["bac"], t["PCT 3Y"]["bac"]), ("FACT-T2", "FACT-T2"))  # R1 bậc hạng
        self.assertIn("(mức EST)", t["×P10"]["s"])
        self.assertIn("Lớp FFT (P3Y)", t["PCT 3Y"]["s"])
        self.assertEqual(t["FREE FLOAT"]["mau"], "warn")  # R3
        tb = [b for b in o["blocks"] if b["type"] == "table"]
        sk, t12 = tb[0], tb[1]
        self.assertEqual([c["label"] for c in sk["cols"]], ["Ngày", "Nguồn", "Loại", "Nội dung", "Bậc"])
        self.assertEqual([(r["ngay"], r["ng"]) for r in sk["rows"]],
                         [("20/06/2026", "Vietcap ISS 24T"), ("2025-06", "Toàn Vũ"), ("01/06/2025", "Vietcap ISS 24T")])
        self.assertIn("(+15,8%)", sk["rows"][1]["nd"])
        self.assertEqual([c["label"] for c in t12["cols"]], ["Tuần", "Giá", "FFT tuần", "TB4", "P10 3Y", "P90 3Y", "Số phiên"])
        self.assertEqual(len(t12["rows"]), 12)
        self.assertEqual((t12["rows"][0]["w"], t12["rows"][0]["sp"]), ("25/09/2026", "1"))  # B4 — mảng d
        self.assertIn(t12["rows"][1]["sp"], ("4", "5"))
        self.assertIn(T.MUC_EST, t12["caption"])
        o = chay(self.moi, "chuoi", "TCX")  # tệp chuỗi thiếu `d` → chỉ biết tuần cuối
        t12 = [b for b in o["blocks"] if b["type"] == "table"][-1]
        self.assertEqual((t12["rows"][0]["sp"], t12["rows"][1]["sp"]), ("1 (dở dang)", "—"))
        plx = chay(self.moi, "chuoi", "PLX")["cong"]["dong"]
        self.assertTrue(plx.endswith("chủ thể [không cần] thị trường · playbook [Bo cung / đi ngang]"))
        ctg = chay(self.moi, "chuoi", "CTG")
        self.assertEqual(ctg["cong"]["dong"], "CỔNG: [tiền đắt] · chủ thể [CẦN DATA — nhãn xung đột] thị trường · "
                                              "playbook [CẦN DATA]")
        self.assertEqual((self.tiles(ctg)["CHỦ THỂ"]["v"], self.tiles(ctg)["CHỦ THỂ"]["mau"]), ("⚠ trung tính ⟷ cần", "amber"))
        self.assertEqual(sum("xung đột" in x for x in ctg["cong"]["canh_bao"]), 1)  # không lặp cảnh báo của bridge
        acb = chay(self.moi, "chuoi", "ACB")
        self.assertTrue(acb["cong"]["dong"].endswith("playbook [CẦN DATA — v1.7 không định nghĩa ô tiền đắt × trung tính]"))
        vcb = chay(self.moi, "chuoi", "VCB")
        self.assertTrue(any("Phát hành riêng lẻ" in x for x in vcb["cong"]["canh_bao"]))
        o = chay(self.moi, "chuoi", "XYZ")
        self.assertFalse(o["success"])
        self.assertIn("XYZ", o["error"])

    def test_chuoi_ma_thieu_ff_va_thieu_tep_chuoi(self):
        o = chay(self.moi, "chuoi", "HDG")
        t = self.tiles(o)
        self.assertEqual(t["PCT 3Y"]["v"], "—")
        self.assertEqual(t["FREE FLOAT"]["s"], "[CẦN DATA] thiếu free float")
        self.assertEqual(t["CHỦ THỂ"]["v"], "[CẦN DATA]")
        self.assertTrue(t["CHỦ THỂ"]["s"].startswith("ghi chú ngành (không thành nhãn): "))
        self.assertEqual(t["PLAYBOOK"]["v"], "[CẦN DATA]")
        self.assertEqual(o["cong"]["dong"], "CỔNG: [tiền đắt] · chủ thể [CẦN DATA] thị trường · playbook [CẦN DATA]")
        self.assertTrue(any(b["type"] == "note" and b["title"] == "Thiếu chuỗi" for b in o["blocks"]))
        self.assertEqual(o["data"][0]["01 Mục"], "PCT 3Y")  # B8 — không có chuỗi → hàng tóm tắt từ tiles
        self.assertEqual(len(o["data"]), len(self.block(o, "tiles")["items"]))

    def test_phuongphap_nguyen_van(self):
        o = chay(self.moi, "phuongphap", "VN30")
        h = chu(self.block(o, "html")["html"])
        for ln in L.PP_TEXT.strip("\n").split("\n"):
            if not ln or ln.startswith("[Ma trận]"):
                continue
            if ln.startswith("[Bắt buộc]"):
                self.assertIn(ln.replace("[Bắt buộc]", "").strip(), h)
            elif re.match(r"^FFT [↑↓↔] · ", ln):
                for phan in re.split(r" · | \| ", ln, maxsplit=1)[1].split(" | "):
                    td = next((x for x in L.MX_TIEU_DE if phan.startswith(x + " — ")), None)
                    for p in ([td, phan[len(td) + 3:]] if td else [phan]):
                        self.assertIn(p, h)
            else:
                self.assertIn(ln, h)
        self.assertIn("<code>FFT = KL khớp lệnh trong kỳ ÷ Free float × 100 (%)</code>", self.block(o, "html")["html"])
        sao = self.note(o, "Những chỗ §1 lệch v1.7 bản cuối")
        self.assertTrue(chu(sao["text"]).startswith("★1 "))
        self.assertEqual(sao["text"].count("★"), 4)
        p3 = chu(self.block(o, "html", 1)["html"])  # D6.9
        for ln in md_tron_khoi(T.PILLAR3_MD) + md_tron_khoi(T.NTH_MD):
            self.assertIn(ln, p3)
        self.assertIn("tham chiếu SS-T3; chỉ ô CĐ↓×Giá↑ được mã hoá — EST", p3)
        self.assertIn("7 mẫu hình NTH chưa cài — hai bộ đánh số xung đột (NTH:55-61 ⟷ task Cowork "
                      "nguyentranhai-langkinh-daily/SKILL.md:21-27).", p3)
        tv = chu(self.note(o, "Từ vựng — không trộn")["text"])  # R12
        for i, x in enumerate(T.TU_VUNG, 1):
            self.assertIn("(%d) %s" % (i, x), tv)
        self.assertEqual(len(T.TU_VUNG), 5)
        self.assertTrue(o["data"])

    @unittest.skipUnless(os.path.exists(U3), "u3.md (đặc tả gốc) không còn")
    def test_chu_co_dinh_khop_dac_ta_u3(self):
        with open(U3, encoding="utf-8") as fh:
            dong_ = fh.read().split("\n")
        i = next(k for k, x in enumerate(dong_) if x.startswith("## H."))
        a = next(k for k in range(i, len(dong_)) if dong_[k].startswith("```"))
        b = next(k for k in range(a + 1, len(dong_)) if dong_[k].startswith("```"))
        self.assertEqual(L.PP_TEXT.strip("\n"), "\n".join(dong_[a + 1:b]))
        cau = [m.group(1) for m in (re.match(r'^\d+\. \*"(.*)"\*$', x) for x in dong_) if m]
        self.assertEqual(L.CAU_BAT_BUOC, cau)

    @unittest.skipUnless(os.path.exists(SKILL) and os.path.exists(NTH), "tệp skill nguồn không còn")
    def test_pillar3_nth_khop_tep_nguon(self):
        with open(SKILL, encoding="utf-8") as fh:
            self.assertEqual(T.PILLAR3_MD, "\n".join(fh.read().split("\n")[176:193]))
        with open(NTH, encoding="utf-8") as fh:
            self.assertEqual(T.NTH_MD, "\n".join(fh.read().split("\n")[44:46]))

    def test_nguon(self):
        o = chay(self.moi, "nguon", "VN100")
        t = self.block(o, "table")
        self.assertEqual([c["label"] for c in t["cols"]], ["Thành phần", "Nguồn", "Bậc", "Mốc dữ liệu", "Độ phủ"])
        tp = {r["tp"]: r for r in t["rows"]}
        for k in ("CỔNG · Q2 Corporate", "Chủ thể cần thị trường (nhãn)", "Sở hữu (Nhà nước · NN · trần NN)",
                  "Phát hành 24T (Vietcap ISS)", "Ý đồ curated (owner_intent)", "Bậc trường sở hữu VCI", "Cờ dữ liệu"):
            self.assertIn(k, tp)
        self.assertEqual(tp["Chủ thể cần thị trường (nhãn)"]["bac"], "SS-T3 3 · EST 4 · xung đột 1")
        self.assertEqual(tp["Ý đồ curated (owner_intent)"]["phu"], "26 curated · 10 verified · 366 auto bỏ qua")
        self.assertIn("SS-T3", tp["Bậc trường sở hữu VCI"]["ng"])
        self.assertEqual(tp["Market FFT VN100"]["phu"], "9/10 mã có FF")
        self.assertIn("không hiển thị tổng NAV", tp["Danh mục NAV / watch / avoid"]["phu"])
        notes = {b["title"]: b for b in o["blocks"] if b["type"] == "note"}
        bb = next(b for k, b in notes.items() if k.startswith("11 câu bắt buộc"))
        self.assertEqual(bb["pill"], "Bắt buộc")
        txt = chu(bb["text"])
        self.assertEqual(len(L.CAU_BAT_BUOC), 11)
        for c in L.CAU_BAT_BUOC:
            self.assertIn(md_tron(c), txt)
        self.assertIn("HDG: thiếu free float", notes["Lỗi / mã thiếu"]["text"])
        self.assertIn("chủ thể: owner_intent: TCX", notes["Lỗi / mã thiếu"]["text"])
        self.assertIn("vn_ff", notes["Lịch chạy"]["text"])
        self.assertIn("fft_chuthe", notes["Lịch chạy"]["text"])
        qu = chu(notes["Quy ước nguồn"]["text"])
        self.assertIn(T.R2, qu)  # R2
        self.assertIn(T.R4, qu)  # R4
        self.assertIn("CẤM dùng Capital IQ Float%", T.R2)
        self.assertIn("Không dùng Simplize.", T.R4)
        loai = notes["Nguồn đã xét & loại"]["text"]
        self.assertEqual(loai.count("<b>"), 10)
        for ten, _ in T.NGUON_LOAI:
            self.assertIn(ten, chu(loai))
        co = chu(notes["Cờ dữ liệu (EST)"]["text"])
        self.assertIn("— 1 mã: MBB ×1,25", co)
        self.assertIn("— 1 mã: FPT", co)
        self.assertIn("— 1 mã: TCX", co)


if __name__ == "__main__":
    unittest.main()
