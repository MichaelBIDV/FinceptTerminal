#!/usr/bin/env python3
"""Unit tests for beri.py — synthetic fixtures only (no real data, no network).

Run: python3 -m unittest scripts/test_beri.py -v
"""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import beri as B  # noqa: E402

D = dt.date


WORKSPACE = """# beri-workspace

## 1. VAI VÀ THẨM QUYỀN

**Nguyễn Văn A** — Phó Viện trưởng Viện NCKT BIDV (BERI), bổ nhiệm 1/8/2026 theo QĐ 1080/QĐ-BIDV,
cấp lương 15 bậc 5.

Thẩm quyền theo Điều 8, QC 1128/QĐ-BIDV ngày 15/10/2025.

## 6. LỊCH SẢN PHẨM — theo Phụ lục BC 14/9 [T1]

Đây là lịch chính thức.

### 6.1 Nhịp tháng

| Sản phẩm | Hạn | Đơn vị thụ hưởng |
|---|---|---|
| Báo cáo kinh tế vĩ mô Việt Nam | ngày 6 hằng tháng | BLĐ |
| Tài liệu tiếp đối tác | phát sinh 2–3 lần/tháng | BLĐ |

### 6.2 Nhịp quý

| Sản phẩm | Hạn | Đơn vị thụ hưởng |
|---|---|---|
| BC thị trường tài chính VN và xu hướng rủi ro | trước ngày 10 tháng 1/4/7/10 | Ban QLRR |
| BC cập nhật thị trường BĐS | 31/1 · 30/6 · 30/9 · 31/12 ⚠️ xem §7 mục 11 | Ban KHDN |

### 6.3 Nhịp bán niên và năm

| Sản phẩm | Hạn | Ghi chú |
|---|---|---|
| BC đánh giá năng lực cạnh tranh BIDV | trong tháng 5 và tháng 10 | — |
| BC đánh giá BIDV so với TCTD nhóm 4 nước ASEAN | tháng 9 hằng năm | — |
| Kế hoạch công tác năm sau | tháng 10 năm trước | — |

### 6.4 Không theo nhịp

| Sản phẩm | Hạn | Ghi chú |
|---|---|---|
| BC nhanh vấn đề nóng | 1–3 ngày sau sự kiện | — |
| Viết gì đó | không rõ | — |

## 6b. CAM KẾT MỚI

| # | Việc | Mốc | Ghi chú |
|---|---|---|---|
| 1 | Ký SLA | Quý IV/2026 | mốc cứng |
| 2 | Xây cơ chế SLA | chưa nêu mốc | — |

## 6c. MỐC NEO VĂN BẢN

| Văn bản | Nội dung | Sản phẩm |
|---|---|---|
| **QĐ 1106/QĐ-BIDV ngày 5/3/2024** | x | BC triển vọng ngành |
| **QĐ 730/QĐ-BIDV** | y | Nghiên cứu ngành |
| **QĐ 1080/QĐ-BIDV** | Bổ nhiệm | — |

## 7. SỔ LỆCH

### 7.1 ĐÃ CHỐT

| # | Vấn đề | Kết luận |
|---|---|---|
| 4 | Tần suất BC triển vọng ngành | Quý |

### 7.2 ĐANG MỞ

| # | Vấn đề | Bên A | Bên B | Đề xuất |
|---|---|---|---|---|
| 1 | Tăng trưởng 2026 | 8% | 7,5% | chờ |
| 11 | Lịch BC thị trường BĐS | 30/6 | 31/7 | hỏi |

## 8. VIỆC ĐANG MỞ

### 8.1 Đang chạy — hồ sơ định biên

- Ứng viên X đã phỏng vấn
- Ứng viên Y đã phỏng vấn

### 8.4 Hạ tầng còn nợ

- Tra đủ số hiệu QĐ.
  dòng nối tiếp.
- Việc cuối ---
"""

KHO = """# KHO SỐ LIỆU CHUẨN · 6T/2026

Đã cập nhật 19/8/2026.

## G. SỔ LỆCH SỐ LIỆU

| # | Vấn đề | Nguồn A | Nguồn B | Xử lý | Trạng thái |
|---|---|---|---|---|---|
| 1 | Dự báo tăng trưởng Việt Nam 2026 | 8% | 7,5% | chờ | **MỞ — ƯU TIÊN** |
| 2 | Cán cân thương mại | a | b | c | **ĐÃ GIẢI THÍCH** |
| 3 | Tên gọi báo cáo | a | b | c | **ĐÃ ĐÓNG 1/9/2026** |
"""

CHARTER = """# Charter

## 1. HIẾN CHƯƠNG

### 1.1 Bậc bằng chứng

| Tag | Nghĩa | Ví dụ |
|---|---|---|
| [T0] | Văn bản pháp lý | QĐ 1128 |
| [T1] | Thống kê | GSO |

**Quy tắc T4:** hạ một bậc.

### 1.2 Sáu điều KHÔNG

1. KHÔNG bịa số.
2. KHÔNG bịa nguồn.

## 2. CƠ CẤU HỘI ĐỒNG

### TẦNG A — TỔ KIỂM CHỨNG *(phát biểu TRƯỚC)*

**A1 · GHẾ KIỂM CHỨNG SỐ LIỆU** — *Data Integrity Officer*
Chỉ hỏi: số này ở đâu ra.
- Số này ở đâu?
**Quyền:** CHẶN.

### TẦNG B — TỔ CHUYÊN MÔN LÕI

**B1 · GHẾ KINH TẾ VĨ MÔ** *(nhóm NC KTVM — 5 cán bộ)*
Phụ trách: BC KTVM.
- Chuyện gì thay đổi?

## 3. QUY TRÌNH 7 BƯỚC

```
B1. MANDATE      → Ai đặt hàng?
B2. KIỂM KÊ DATA → Lập bảng.
```

**Nguyên tắc thứ tự:** kiểm chứng nói trước.

## 4. BỐN TRẠNG THÁI KẾT LUẬN

| Trạng thái | Nghĩa | Xử lý |
|---|---|---|
| **A — VỮNG** | đủ | trình |
| **D — BỊ CHẶN** | chặn | dừng |
"""

EXPERTS = """# 18 ghế

> Nguyên tắc thiết kế: **không bịa ra chuyên gia tưởng tượng.** Mỗi ghế có nguyên mẫu.

## PHẦN II — MƯỜI TÁM GHẾ

### KHỐI I — THƯƠNG MẠI

#### E1 · GHẾ THƯƠNG MẠI — *Ghế Thường trực Tầng E*

**Nguyên mẫu:** Người A — nguyên Thứ trưởng.
**Mandate:** thuế quan.
**Sản phẩm:** BC thuế quan.
**Câu hỏi lõi:**
- Câu 1?
- Câu 2?

#### E2 · GHẾ ĐỐI NGOẠI

**Nguyên mẫu:** Người B.
**Mandate:** ngoại giao.

### KHỐI II — VĨ MÔ

#### E3 · GHẾ VĨ MÔ

**Mandate:** vĩ mô.
"""

VALUE = """# Kho dữ liệu

## 3. BỐN DÒNG GIÁ TRỊ

### Dòng 1 — BẢO VỆ CHẤT LƯỢNG TÀI SẢN *(lớn nhất, khó đo nhất)*

Cơ chế: BC triển vọng → giới hạn.

### Dòng 2 — Hỗ trợ bán hàng *(đo được)*

Cơ chế A.
"""

REGISTRY = {
    "cap_nhat": "2026-09-17",
    "nguon": [
        {"id": "gso", "he": "beri", "ten": "GSO", "nhom": "vĩ mô", "tier": "T1", "trang_thai": "thu_cong",
         "tan_suat": "tháng", "ghi_chu": ""},
        {"id": "bbg", "he": "beri", "ten": "Bloomberg", "nhom": "x", "tier": "T4", "trang_thai": "chua_co",
         "tan_suat": "", "ghi_chu": ""},
        {"id": "vc", "he": "ck", "ten": "Vietcap giá", "nhom": "ck", "tier": "FACT-T1", "trang_thai": "song"},
    ],
}


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class RuleEngine(unittest.TestCase):
    def test_month_list_is_months_not_dates(self):
        # The trap: "1/4" and "7/10" must NOT be read as 1 April / 7 October.
        kind, cands = B.candidates("trước ngày 10 tháng 1/4/7/10", D(2026, 9, 24))
        self.assertEqual(kind, "nam")
        self.assertIn(D(2026, 10, 10), cands)
        self.assertNotIn(D(2026, 4, 1), cands)
        self.assertNotIn(D(2026, 10, 7), cands)
        r = B.countdown("trước ngày 10 tháng 1/4/7/10", D(2026, 9, 24))
        self.assertEqual(r["moc_tiep"], "2026-10-10")
        self.assertEqual(r["con_ngay"], 16)
        self.assertEqual(r["muc"], "warn")

    def test_monthly(self):
        r = B.countdown("ngày 6 hằng tháng", D(2026, 9, 24))
        self.assertEqual(r["kieu"], "thang")
        self.assertEqual(r["moc_tiep"], "2026-10-06")
        self.assertEqual(r["ky_vua_qua"], {"moc_txt": "06/09/2026", "qua_ngay": 18})

    def test_explicit_dates_and_year_wrap(self):
        r = B.countdown("31/1 · 30/4 · 31/7 · 31/10", D(2026, 11, 2))
        self.assertEqual(r["moc_tiep"], "2027-01-31")
        r = B.countdown("31/1 · 30/6 · 30/9 · 31/12 ⚠️ xem §7 mục 11", D(2026, 9, 24))
        self.assertEqual(r["moc_tiep"], "2026-09-30")
        self.assertEqual(r["muc"], "crit")

    def test_month_windows_use_month_end(self):
        self.assertEqual(B.countdown("trong tháng 5 và tháng 10", D(2026, 9, 24))["moc_tiep"], "2026-10-31")
        self.assertEqual(B.countdown("tháng 9 hằng năm", D(2026, 9, 24))["moc_tiep"], "2026-09-30")
        self.assertEqual(B.countdown("tháng 10 năm trước", D(2026, 9, 24))["moc_tiep"], "2026-10-31")
        self.assertEqual(B.countdown("tháng 2 hằng năm", D(2027, 2, 1))["moc_tiep"], "2027-02-28")

    def test_event_driven_and_unparseable_get_no_date(self):
        for t in ("1–3 ngày sau sự kiện", "phát sinh 2–3 lần/tháng", "tối đa 3 ngày", "theo phát sinh"):
            r = B.countdown(t, D(2026, 9, 24))
            self.assertEqual(r["kieu"], "su_kien", t)
            self.assertIsNone(r["moc_tiep"])
            self.assertEqual(r["muc"], "na")
        r = B.countdown("không rõ", D(2026, 9, 24))
        self.assertEqual(r["kieu"], "khong_tinh")
        self.assertIsNone(r["con_ngay"])

    def test_thresholds(self):
        self.assertEqual(B.countdown("30/9", D(2026, 9, 23))["muc"], "crit")   # 7 days
        self.assertEqual(B.countdown("30/9", D(2026, 9, 22))["muc"], "warn")   # 8 days
        self.assertEqual(B.countdown("30/9", D(2026, 9, 9))["muc"], "warn")    # 21 days
        self.assertEqual(B.countdown("30/9", D(2026, 9, 8))["muc"], "ok")      # 22 days
        self.assertEqual(B.countdown("30/9", D(2026, 9, 30))["con_txt"], "hôm nay")


class Helpers(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(B.plain("**QĐ 1106** `x` [link](http://a) *nghiêng*"), "QĐ 1106 x link nghiêng")

    def test_name_date(self):
        self.assertEqual(B.name_date("2026.07.15_BC.pdf").date(), D(2026, 7, 15))
        self.assertEqual(B.name_date("21092026_082013_QD.pdf").date(), D(2026, 9, 21))
        self.assertIsNone(B.name_date("BC_V5.docx"))

    def test_stage(self):
        self.assertEqual(B.stage_of("X_FINAL.pdf"), "FINAL")
        self.assertEqual(B.stage_of("X_V5_3trang.docx"), "V5")
        self.assertEqual(B.stage_of("X_v3_TrackChange_PMT_V4.docx"), "bản track-change")

    def test_forbidden(self):
        self.assertTrue(B.forbidden("/a/data/nganh_42.json"))
        self.assertTrue(B.forbidden("/a/BERI_DuNoNganh_Q2.md"))
        self.assertIsNone(B.read_text("/nonexistent/config.env"))


class Overview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="beri_test_")
        t = self.tmp
        self.ws = os.path.join(t, "ws", "SKILL.md")
        self.sector = os.path.join(t, "sector")
        self.copies = os.path.join(t, "copies")
        self.prod = os.path.join(t, "prod")
        self.reg = os.path.join(t, "reg.json")
        write(self.ws, WORKSPACE)
        write(os.path.join(self.sector, "BERI_KhoSoLieuChuan_2026H1.md"), KHO)
        write(os.path.join(self.sector, "BERI_HoiDongCoVanAI_Charter.md"), CHARTER)
        write(os.path.join(self.sector, "BERI_HoiDongChuyenGia_18Ghe.md"), EXPERTS)
        write(os.path.join(self.sector, "BERI_KhoDuLieu_DoiTac_DoanhThu.md"), VALUE)
        write(os.path.join(self.copies, "BERI_KhoSoLieuChuan_2026H1.md"), KHO + "\nkhác\n")
        write(os.path.join(self.copies, "BERI_HoiDongCoVanAI_Charter.md"), CHARTER)
        write(self.reg, json.dumps(REGISTRY, ensure_ascii=False))
        feed = {"scans": [
            {"generated_at": "2026-09-23T08:10:00", "n_news": 5, "n_policy": 9},
            {"generated_at": "2026-09-24T08:10:00", "n_news": 22, "n_policy": 190,
             "sector_moves": ["SECRET"], "overlay": {"x": "SECRET"}, "ung_vien_flashnote": ["SECRET"]},
        ], "catalog": {"du_no": "SECRET"}}
        write(os.path.join(self.sector, "output", "sector_feed.json"), json.dumps(feed))
        rs = {"ngay": "2026-09-24", "tong": 3, "nghiem_trong": 2, "phat_hien": [
            {"nhom": "nguồn", "muc": "nghiêm trọng", "viec": "thay địa chỉ nguồn", "chi_tiet": "SECRET-URL"},
            {"nhom": "nguồn", "muc": "nghiêm trọng", "viec": "thay địa chỉ nguồn"},
            {"nhom": "sản phẩm", "muc": "nghiêm trọng", "viec": "SECRET-PLAN"},
        ]}
        write(os.path.join(self.sector, "output", "ra_soat_2026-09-24.json"), json.dumps(rs, ensure_ascii=False))
        for n in ("BanTomLuoc_TTBDS_TinDungBDS_9T2026_V5.docx", "BanTomLuoc_TTBDS_TinDungBDS_9T2026_V4.docx",
                  "SSI_ASEAN banks.pdf", "~$BanTin_KinhTeNganh_FINAL.docx", "BanTin_KinhTeNganh_So02_FINAL.pdf",
                  "Final TB noi bo khong lien quan.pdf", "2026.07.15_Dien bien lop tai san so 03 FINAL.pdf"):
            write(os.path.join(self.prod, n), "x")
        self.env = {"BERI_WORKSPACE_SKILL": self.ws, "BERI_SECTOR_DIR": self.sector, "BERI_SONGUON": self.reg,
                    "BERI_PRODUCT_DIR": self.prod, "BERI_COPY_DIRS": self.copies, "BERI_TODAY": "2026-09-24"}
        self.old = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            B.main(list(args))
        out = buf.getvalue()
        self.assertEqual(out.count("\n"), 1, "exactly one JSON line")
        return json.loads(out), out

    def test_bad_args(self):
        d, _ = self.run_cli()
        self.assertEqual(d["error_code"], "BAD_ARGS")
        d, _ = self.run_cli("overview", "extra")
        self.assertEqual(d["error_code"], "BAD_ARGS")

    def test_calendar(self):
        d, _ = self.run_cli("overview")
        self.assertNotIn("error", d)
        rows = {r["san_pham"]: r for g in d["lich"]["nhom"] for r in g["dong"]}
        self.assertEqual(len(d["lich"]["nhom"]), 4)
        self.assertEqual(len(rows), 9)
        bds = rows["BC cập nhật thị trường BĐS"]
        self.assertEqual(bds["moc_tiep"], "2026-09-30")
        self.assertEqual(bds["co"], ["nghi lỗi lịch — xem Sổ lệch vận hành mục 11"])
        self.assertEqual(bds["tien_do"]["tep"], "BanTomLuoc_TTBDS_TinDungBDS_9T2026_V5.docx")
        self.assertEqual(bds["tien_do"]["giai_doan"], "V5")
        self.assertIsNone(rows["BC đánh giá BIDV so với TCTD nhóm 4 nước ASEAN"]["tien_do"],
                          "broker file must not count as Viện progress")
        # "Diễn biến lớp tài sản" must not be claimed by the KTVM row
        self.assertIsNone(rows["Báo cáo kinh tế vĩ mô Việt Nam"]["tien_do"])
        self.assertEqual(d["alert"]["muc"], "crit")
        self.assertIn("30/09/2026", d["alert"]["noi_dung"])
        self.assertEqual(sum(d["lich"]["dem"].values()), 9)

    def test_ledgers_and_cross_reference(self):
        d, _ = self.run_cli("overview")
        sl = d["so_lech"]["so_lieu"]
        self.assertEqual((sl["mo"], sl["giai_thich"], sl["dong_lai"]), (1, 1, 1))
        vh = d["so_lech"]["van_hanh"]
        self.assertEqual((len(vh["da_chot"]), len(vh["dang_mo"])), (1, 2))
        self.assertEqual(sl["dong"][0]["trung_voi"], "trùng Sổ lệch vận hành mục 1")
        self.assertEqual(vh["dang_mo"][0]["trung_voi"], "trùng Sổ lệch số liệu mục 1")
        self.assertEqual(vh["dang_mo"][1]["trung_voi"], "")

    def test_commitments_anchors_open_work(self):
        d, _ = self.run_cli("overview")
        self.assertEqual(len(d["cam_ket"]["dong"]), 2)
        self.assertEqual(d["cam_ket"]["chua_moc"], 1)
        self.assertEqual(d["moc_neo"]["thieu_ngay"], 1, "QĐ 730 only; QĐ 1080 anchors no product")
        groups = d["viec_mo"]["nhom"]
        self.assertEqual(len(groups[0]["dong"]), 1)
        self.assertNotIn("Ứng viên", json.dumps(groups, ensure_ascii=False))
        self.assertEqual(groups[1]["dong"], ["Tra đủ số hiệu QĐ. dòng nối tiếp.", "Việc cuối"])

    def test_mandate_and_charter_sections(self):
        d, _ = self.run_cli("overview")
        self.assertEqual(d["mandate"]["ten"], "Nguyễn Văn A")
        self.assertEqual(d["mandate"]["hieu_luc"], "1/8/2026")
        self.assertEqual(len(d["hien_chuong"]["bac"]), 2)
        self.assertEqual(len(d["hien_chuong"]["khong"]), 2)
        self.assertEqual([g["id"] for k in d["tang_e"]["khoi"] for g in k["ghe"]], ["E1", "E2", "E3"])
        e1 = d["tang_e"]["khoi"][0]["ghe"][0]
        self.assertEqual(e1["vai_tro"], "Ghế Thường trực Tầng E")
        self.assertEqual(e1["cau_hoi"], ["Câu 1?", "Câu 2?"])
        self.assertTrue(d["tang_e"]["nguyen_tac"].startswith("không bịa ra"))
        tang = {t["id"]: t for t in d["bo_may"]["tang"]}
        self.assertEqual(tang["A"]["ghe"][0]["quyen"], "CHẶN.")
        self.assertEqual(tang["B"]["ghe"][0]["vai_tro"], "nhóm NC KTVM — 5 cán bộ")
        self.assertEqual([b["ten"] for b in d["quy_trinh"]["buoc"]], ["Mandate", "Kiểm kê data"])
        self.assertEqual([k["ma"] for k in d["ket_luan"]["dong"]], ["A", "D"])
        self.assertEqual([v["nhan"] for v in d["gia_tri"]["dong"]], ["lớn nhất, khó đo nhất", "đo được"])

    def test_registry_core_files_pipeline(self):
        d, _ = self.run_cli("overview")
        sn = d["so_nguon"]
        self.assertEqual(len(sn["dong"]), 2, "securities rows (he=ck) excluded")
        self.assertEqual(sn["dong"][0]["id"], "bbg", "chưa có sorts before thủ công")
        self.assertEqual(sn["tuoi_ngay"], 7)
        kho = {t["ten"]: t for t in d["kho"]["tep"]}
        self.assertFalse(kho["BERI_KhoSoLieuChuan_2026H1.md"]["khop"])
        self.assertTrue(kho["BERI_HoiDongCoVanAI_Charter.md"]["khop"])
        self.assertFalse(kho["BERI_MauBaoCao_Checklist.md"]["ton_tai"])
        self.assertTrue(any("lệch nội dung" in w for w in d["meta"]["warnings"]))
        cb = d["kho"]["so_lieu"]["canh_bao"]
        self.assertIn("BanTin_KinhTeNganh_So02_FINAL.pdf", cb)
        self.assertNotIn("khong lien quan", cb, "unrelated internal files never surface")
        q = d["pipeline"]["quet"]
        self.assertEqual((q["n_tin"], q["n_chinh_sach"], q["so_luot"]), (22, 190, 2))
        rs = d["pipeline"]["ra_soat"]
        self.assertEqual(rs["viec"], ["thay địa chỉ nguồn ×2"])

    def test_forbidden_content_never_emitted(self):
        _, raw = self.run_cli("overview")
        for bad in ("SECRET", "sector_moves", "overlay", "ung_vien_flashnote", "du_no"):
            self.assertNotIn(bad, raw)

    def test_missing_sources_degrade_not_crash(self):
        os.environ["BERI_WORKSPACE_SKILL"] = os.path.join(self.tmp, "none.md")
        os.environ["BERI_SECTOR_DIR"] = os.path.join(self.tmp, "none")
        os.environ["BERI_SONGUON"] = os.path.join(self.tmp, "none.json")
        d, _ = self.run_cli("overview")
        self.assertNotIn("error", d)
        self.assertIsNone(d["lich"])
        self.assertEqual(d["alert"]["muc"], "na")
        self.assertEqual(d["mandate"]["ten"], B.CAN_DATA)
        self.assertGreaterEqual(len(d["meta"]["warnings"]), 3)


class RealFilesSmoke(unittest.TestCase):
    """Runs against the live files when they exist on this machine; skipped elsewhere."""

    def test_live(self):
        ws = os.path.expanduser("~/.claude/skills/beri-workspace/SKILL.md")
        if not os.path.exists(ws):
            self.skipTest("no live workspace")
        buf = io.StringIO()
        with redirect_stdout(buf):
            B.main(["overview"])
        d = json.loads(buf.getvalue())
        self.assertNotIn("error", d)
        n = sum(len(g["dong"]) for g in d["lich"]["nhom"])
        self.assertGreaterEqual(n, 20)
        self.assertEqual(sum(len(k["ghe"]) for k in d["tang_e"]["khoi"]), 18)
        self.assertEqual(len(d["tang_e"]["khoi"]), 6)
        self.assertEqual(sum(len(t["ghe"]) for t in d["bo_may"]["tang"]), 12)
        self.assertEqual(len(d["quy_trinh"]["buoc"]), 7)
        self.assertEqual(len(d["ket_luan"]["dong"]), 4)
        self.assertEqual(len(d["gia_tri"]["dong"]), 4)
        self.assertEqual(len(d["hien_chuong"]["bac"]), 7)


if __name__ == "__main__":
    unittest.main()
