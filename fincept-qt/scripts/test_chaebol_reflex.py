#!/usr/bin/env python3
"""Tests for chaebol_reflex.py (CLI), chaebol_reflex_trang.py (pages, ALL-IN-ONE cell) and chaebol_reflex_khung.py
(framework library): synthetic registry + dossiers + council + khung on the store fixtures of
test_chaebol_reflex_live.py, the Masan delegation on the fixture of test_msn_reflex.py, and a real-store smoke on a
TEMP registry (skipped when the stores are absent; the real registry is only read, and only if it exists).

Run: python3 -m pytest -q test_chaebol_reflex.py   (add -s to see the real-store timings)
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from datetime import date
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chaebol_reflex as C  # noqa: E402
import chaebol_reflex_khung as K  # noqa: E402
import chaebol_reflex_live as L  # noqa: E402
import chaebol_reflex_trang as T  # noqa: E402
import msn_reflex as M  # noqa: E402
import test_chaebol_reflex_live as TL  # noqa: E402
import test_msn_reflex as TM  # noqa: E402

SCRIPT = os.path.join(HERE, "chaebol_reflex.py")
BLOCK_KINDS = {"cong", "doan", "o_so", "bang", "the", "danh_sach", "trich", "bieu_do", "canh_bao", "chips"}
STANCE = TL.STANCE          # written independently of the guard (chaebol_reflex_khung), and wider
DB = "ĐÓNG BĂNG"
TQ_MAX_BYTES = 150 * 1024   # TỔNG QUAN payload on the real registry
KHUNG_MAX_BYTES = 40 * 1024  # one group's "khung" section


# ── fixtures ─────────────────────────────────────────────────────────────────


def stake(tu, ty_le, **kw):
    return TL.stake(tu, ty_le, **kw)


GHI_CHU_DAI = ("PAR nắm 40% theo BCTN 2025 (/Users/tester/Downloads/bctn_par_2025.pdf trang 12); cổ phần còn lại của "
               "các quỹ ngoại, chưa có kế hoạch niêm yết, đối chiếu thêm với nghị quyết ĐHCĐ 2026 khi công bố.")
TMP_SRC = "/private/tmp/kiem_thu_tmp/thu_muc/su_kien_cbtt.json"
SYS_SRC = "/Users/tester/SECOND BRAIN-OBSIDIAN/_System/kiem_thu/dot_tang.json"
JSX_SRC = "/Users/tester/Downloads/master_plan.jsx · tab vicstory · L%d"


def registry():
    a = {"id": "nhom_a", "ten": "Nhóm A", "chu_the": "Chủ thể A", "truc": "NQ68", "loai": "holding_niem_yet",
         "me": "PAR", "dong_co": "chung", "hoi_dong": True, "he_sinh_thai": ["HeA"],
         "mau": {"PAR": "amber", "CON": "cyan"},
         "xung_dot": [{"chu_de": "PAR→CON", "gia_tri": [{"v": "50%", "nguon": "registry", "ngay": "2018-12-31"},
                                                        {"v": "48%", "nguon": "vc_lk", "ngay": "2026-06-30"}]}],
         "thanh_vien": [
             {"ma": "PAR", "vai_tro": "mẹ"},
             {"ma": "CON", "vai_tro": "con", "me": "PAR", "trong_lt": True, "so_huu": [stake("2018-12-31", 0.5)]},
             {"ma": "CNP", "vai_tro": "con", "me": "PAR", "trong_lt": True, "so_huu": [stake("2018-12-31", 0.3)]},
             {"ma": "CDT", "vai_tro": "con", "me": "PAR", "trong_lt": False, "so_huu": [
                 stake("2026-06-30", 0.75), stake("2026-09-01", 0.80, ap_dung=False, nguon="CBTT chờ")]},
             {"ma": "GRC", "vai_tro": "cháu", "me": "CON", "trong_lt": False, "so_huu": [stake("2018-12-31", 0.6)]},
             {"ma": None, "ten": "Công ty chưa niêm yết", "vai_tro": "con", "me": "PAR", "niem_yet": "chưa",
              "so_huu": [stake("2026-06-30", 0.4), stake("2025-01-01", 0.3)], "ghi_chu": GHI_CHU_DAI}],
         "tang": [{"me": "CON", "con": ["GRC"]}]}
    khac = {"id": "nhom_khac", "ten": "Nhóm khác", "truc": "KHAC", "me": None,
            "thanh_vien": [{"ma": "CDT", "vai_tro": "thành viên"}]}
    truc = {"id": "nhom_truc", "ten": "Rổ trục", "truc": "KHAC", "me": None,
            "thanh_vien": [{"ma": "STL", "vai_tro": "thành viên"}, {"ma": "CDT", "vai_tro": "thành viên"}]}
    khong_gia = {"id": "nhom_khong_gia", "ten": "Nhóm không giá", "truc": "KHAC", "me": "CNP",
                 "thanh_vien": [{"ma": "CNP", "vai_tro": "mẹ"}]}
    v21 = {"id": "nhom_v21", "ten": "Nhóm V21", "truc": "V21", "me": None,
           "thanh_vien": [{"ma": "PBB", "vai_tro": "thành viên"}]}
    a2 = {"id": "nhom_a2", "ten": "Nhóm A2", "truc": "KG21", "me": "PAR", "thanh_vien": [
        {"ma": "CON", "me": "PAR", "trong_lt": True, "so_huu": [stake("2018-12-31", 0.5)]},
        {"ma": "CDT", "me": "PAR", "trong_lt": True, "so_huu": [stake("2026-06-30", 0.75), stake("2025-01-01", 0.78)]}]}
    lag = {"id": "nhom_lag", "ten": "Rổ không mẹ", "chu_the": "Chủ thể chưa niêm yết", "truc": "SPECIAL", "me": None,
           "thanh_vien": [{"ma": "LDB", "vai_tro": "thành viên"}, {"ma": "LDA", "vai_tro": "thành viên"}]}
    b = {"id": "nhom_b", "ten": "Nhóm B", "truc": "NQ79", "me": "PBB", "hoi_dong": True, "thanh_vien": [
        {"ma": "CBB", "vai_tro": "con", "me": "PBB", "trong_lt": True, "so_huu": [stake("2018-12-31", 0.5)]},
        {"ma": "LDA", "vai_tro": "liên quan"}]}
    return {"schema": L.SCHEMA_REG, "lap_luc": "2026-09-24", "nhom": [a, khac, v21, a2, lag, b, truc, khong_gia]}


DS_ORDER = ["tong_quan", "nhom_a", "nhom_b", "nhom_lag", "nhom_a2", "nhom_v21", "nhom_khac", "nhom_truc",
            "nhom_khong_gia"]


def dossier_a():
    sig = [dict(r, mo_ta="Tín hiệu %s" % r["id"], nguon="kiểm thử") for r in TL.dossier_a()["tin_hieu"]]
    return {
        "schema": T.SCHEMA_HO_SO, "nhom": "nhom_a", "ho_so": "2026-09-20", "du_lieu_den": "2026-09-19",
        "tieu_de": "Hồ sơ độ trễ Nhóm A", "phu_de": "Phụ đề A", "artifact_url": "https://claude.ai/artifact/test_a",
        "cong": {"dong": "CỔNG: [CẦN DATA] · v1.7 DỪNG (chuỗi M2 gãy 10/2025) · chủ thể CẦN (giảm nợ) · playbook: "
                         "không phát", "chu_the": "CẦN", "chu_the_ly_do": "giảm nợ", "tier": "EST"},
        "keynotes": [{"id": "K1", "tieu_de": "Chiết khấu", "noi_dung": "PAR ÷ LT 2,0×.", "tier": "EST",
                      "nguon": "kiểm thử"},
                     {"id": "K2", "tieu_de": "Dòng quỹ", "noi_dung": "Quỹ tăng tỷ trọng PAR trong rổ.", "tier": "SS-T3",
                      "nguon": "kiểm thử"}],
        "co_che_truyen_dan": [{"text": "Con niêm yết truyền giá trong ngày; quỹ đất TP.HCM và TP-HCM.", "tier": "EST",
                               "nguon": "kiểm thử", "ngay": "2026-09-20"}],
        "dot_tang_lich_su": [{"ten": "Đợt 1", "tu": "2021-01-01", "den": "2021-12-31", "bien_do": "+120%",
                              "ai_dan_dau": "CON", "chat_xuc_tac": "IPO", "nguon": SYS_SRC}],
        "do_tre_quan_sat": [{"cap": "PAR←CON", "mo_ta": "bứt phá lệch 0–48 ngày", "so": "0–48", "nguon": "kiểm thử",
                             "ngay": "2026-09-20", "tier": "EST"}],
        "capture_dong_bang": [{"cap": "PAR ← CON", "cua_so": "2025", "gia_tri": 0.5, "nguon": "kiểm thử",
                               "ngay": "2026-09-20"},
                              {"cap": "PAR ← CON", "cua_so": "không rõ", "gia_tri": 1.2, "nguon": "kiểm thử",
                               "ngay": "2026-09-20"},
                              {"cap": "PAR ← CON", "cua_so": "năm 2025", "gia_tri": 0.6, "nguon": "kiểm thử",
                               "ngay": "2026-09-20", "tier": "SS-T3"}],
        "su_kien": [{"ngay": "2026-08-01", "mo_ta": "Sự kiện tháng 8", "tier": "FACT-T1", "nguon": "CBTT"},
                    {"ngay": "2026-09-10", "mo_ta": "HSC hạ CON xuống Giữ (TP −20%)", "tier": "SS-T3", "nguon": "HSC"},
                    {"ngay": "2026-06-01", "mo_ta": "Vietcap xếp PAR M-PF, TP 43.300đ", "tier": "SS-T3",
                     "nguon": "Vietcap"},
                    {"ngay": "2026-09-15", "mo_ta": "Sự kiện mới nhất", "tier": "FACT-T1", "nguon": "CBTT"},
                    {"ngay": "2026-09-01", "mo_ta": "Sự kiện đầu tháng 9", "tier": "FACT-T2", "nguon": "CBTT"},
                    {"ngay": "2026-07-01", "mo_ta": "Sự kiện tháng 7", "tier": "FACT-T2", "nguon": TMP_SRC}],
        "chat_xuc_tac": [{"id": "C1", "mo_ta": "Con lên HOSE", "moc": "2027", "trang_thai": "Chờ", "nguon": "kiểm thử"},
                         {"id": "C2", "mo_ta": "LNST quý", "moc": "10/2026", "trang_thai": "Đạt", "nguon": "kiểm thử"}],
        "tin_hieu": sig,
        "vung_gia_dong_bang": [{"ma": "PAR", "vung": "80–120k", "phuong_phap": "σ P/B", "ngay": "2026-09-20",
                                "nguon": "kiểm thử · giá mục tiêu 120k"}],
        "khung_ap_dung": [{"khung": "khung_rieng_a", "anh_xa": [{"pha": "② EARNINGS SHOCK", "thoi_gian": "T3/2026",
                                                                 "dau_hieu_da_thay": "LNST +50%", "nguon": "kiểm thử"}],
                           "ghi_chu": "ánh xạ của nguồn"},
                          {"khung": "khong_co_trong_thu_vien", "anh_xa": []},
                          {"khung": "khung_cu_a", "ten": "Thành phần cũ của A", "ghi_chu": "ánh xạ cũ",
                           "anh_xa": [{"pha": "③", "thoi_gian": "T4/2026", "dau_hieu_da_thay": "KL tăng",
                                       "nguon": JSX_SRC % 1},
                                      {"pha": "④", "thoi_gian": "T5/2026", "dau_hieu_da_thay": "giá vượt đỉnh",
                                       "nguon": JSX_SRC % 2}]}],
        "y_do_chu_the": [{"text": "Chủ thể cần thị trường để giảm nợ.", "tier": "EST", "nguon": "kiểm thử",
                          "ngay": "2026-09-20"},
                         {"text": "REALTIME v2 đổi AVOID → ALPHA-MODERATE; một công ty chứng khoán xếp khả quan.",
                          "tier": "SS-T3", "nguon": "kiểm thử", "ngay": "2026-09-20"}],
        "rui_ro": [{"text": "Con giảm sâu.", "nguon": "kiểm thử"}],
        "pre_mortem": [{"ten": "Con giảm", "xac_suat": "20%", "noi_dung": "Con giảm 40%.", "tin_hieu_som": "KL tăng",
                        "nguon": "kiểm thử"}],
        "nhan_dinh_cu_dong_bang": [{"ngay": "2026-05-01", "nguon": "Hội đồng cũ", "tom_tat": "MUA thêm 3% NAV"},
                                   {"ngay": "2026-09-01", "nguon": "Hội đồng 09", "tom_tat": "giữ tỷ trọng 5%"}],
        "viec_treo": ["Chờ BCTC Q3", "Đối chiếu tỷ lệ CON",
                      "Bản tham khảo, không phải khuyến nghị; giữ nguyên thứ tự."],
        "xung_dot_so_lieu": [{"chu_de": "CON", "gia_tri": "48% và 50%", "nguon": "vc_lk, registry"}],
        "nguon": ["Nguồn 1", "Nguồn 2"]}


def hoi_dong_a():
    return {"schema": T.SCHEMA_HOI_DONG, "nhom": "nhom_a", "ngay": "2026-09-21", "goi_du_kien": "facts.json",
            "cong": "CỔNG: [CẦN DATA] · v1.7 DỪNG", "cau_hoi": "Giá trị của con có truyền lên mẹ không?",
            "kill_zone": [{"co_van": "Munger", "phieu": "PHẢN BIỆN", "lap_luan": "Con quá nhỏ.",
                           "dieu_kien_doi_phieu": "LT tăng gấp đôi"},
                          {"co_van": "Klarman", "phieu": "CHỜ DỮ LIỆU", "lap_luan": "Thiếu BCTC riêng.",
                           "dieu_kien_doi_phieu": "BCTC Q3"}],
            "alpha_zone": [{"co_van": "Soros", "phieu": "ỦNG HỘ", "lap_luan": "Vòng phản xạ.",
                            "dieu_kien_doi_phieu": "tỷ số dưới 1,5×"}],
            "synthesis": {"trang_thai": "B", "text": "Chiết khấu còn rộng.",
                          "rigor_6d": {"Ng": 3, "Lo": 4, "Md": 3, "Bb": 2, "Pc": 3, "Hc": 4}},
            "pre_mortem": [{"ten": "Con hụt", "xac_suat": "25%", "noi_dung": "Con hụt kế hoạch.",
                            "tin_hieu_som": "KL bất thường"}],
            "phep_thu": ["Nếu PAR ÷ LT > 3× thì sao?"], "tier": "EST · Hội đồng AI 21/09/2026"}


def khung():
    return {"schema": K.SCHEMA, "khung": [
        {"id": "khung_chung", "ten": "Khung chung", "nguon": "JSX v37 · tab x · L1-L2", "loai": "checklist",
         "mo_ta": "Khung cho mọi nhóm.", "noi_dung": ["bước một", "bước hai"], "ap_dung_cho": ["moi_nhom"],
         "dau_hieu_do_duoc": [
             {"id": "D1", "mo_ta": "KL tăng", "phep_do": "kl_tuan_tb20", "tham_so": {"k_x": 1.5}},
             {"id": "D2", "mo_ta": "Gần đỉnh 52 tuần", "phep_do": "cach_dinh_52t", "tham_so": {"x_pct": 10},
              "ma": "moi_ma"},
             {"id": "D3", "mo_ta": "Tỷ số thấp", "phep_do": "ty_so_holdco_pct", "tham_so": {"p_pct": 60, "cua_so": "3Y"}}],
         "tier": "EST (khung của tác giả, 04/2026)"},
        {"id": "khung_rieng_a", "ten": "Khung riêng A", "nguon": "JSX v37 · tab y", "loai": "khuon_pha",
         "mo_ta": "Bảy pha.", "noi_dung": {"chuoi": "① → ②", "bang": [{"pha": "①", "dau_hieu": "MUA ròng mạnh"}],
                                            "insight": "giá đi trước"}, "bi_danh": ["khung_cu_a"],
         "ap_dung_cho": ["nhom_a"], "dau_hieu_do_duoc": [
             {"id": "R1", "mo_ta": "LNST tăng", "phep_do": "lnst_yoy", "tham_so": {"g_pct": 20}}],
         "tier": "EST"},
        {"id": "concentration_era", "ten": "Concentration Era", "nguon": "JSX v37 · tab macro", "loai": "chan_doan",
         "mo_ta": "Thị trường tập trung.", "noi_dung": {"chan_doan": "Top 3 chiếm 30%", "bien_chung": ["một", "hai"],
                                                         "phan_sau": {"bang": [{"x": "nội dung sâu"}]}},
         "ap_dung_cho": ["thi_truong"], "tier": "EST"},
        {"id": "vic_reflexivity_7pha", "ten": "VIC Reflexivity: bảy pha", "loai": "khuon_pha",
         "tier": "EST (khung, 04/2026)", "nguon": "JSX v37 (/Users/tester/Downloads/master_plan.jsx) · tab vicstory · L1-L9",
         "mo_ta": "M" * 400,
         "ap_dung_cho": ["thi_truong"], "noi_dung": {
             "Cốt lõi": ["điểm chính"], "Bảng phụ": {"bang": [{"cap": "VIC ← VHM", "doc": "bảng không phải pha"}]},
             "Khuôn 7 pha": {"bang": [{"pha": "P%d" % i, "dau_hieu": "dấu hiệu %d" % i} for i in range(14)],
                             "insight": "nội dung pha đầy đủ"}}},
        {"id": "khung_chung", "ten": "trùng"}]}


class Fx(TL.Fixture):
    """test_chaebol_reflex_live stores + this module's registry, dossiers, council and framework library."""

    def __init__(self):
        super().__init__()
        self.write(os.path.join(self.reg, "nhom.json"), registry())
        pa = os.path.join(self.reg, "nhom_a")
        self.write(os.path.join(pa, "ho_so_2026-09-20.json"), dossier_a())
        self.write(os.path.join(pa, "ho_so_2026-08-01.json"), {
            "schema": T.SCHEMA_HO_SO, "nhom": "nhom_a", "ho_so": "2026-08-01", "tieu_de": "Hồ sơ cũ"})
        self.write(os.path.join(pa, "ho_so_2026-09-22.json"), {"schema": "khac/1"})
        self.write(os.path.join(pa, "hoi_dong_2026-09-21.json"), hoi_dong_a())
        self.write(os.path.join(self.reg, "nhom_b", "ho_so_2026-09-20.json"), {
            "schema": T.SCHEMA_HO_SO, "nhom": "nhom_b", "ho_so": "2026-09-20",
            "cong": {"dong": "CỔNG: TIỀN RẺ · chủ thể CẦN · playbook X"}})
        self.write(os.path.join(self.reg, "khung.json"), khung())
        self.write(os.path.join(self.reg, "nhom_khong_gia", "ho_so_2026-09-20.json"), {
            "schema": T.SCHEMA_HO_SO, "nhom": "nhom_khong_gia", "ho_so": "2026-09-20",
            "capture_dong_bang": [{"cap": "CNP ← CON", "cua_so": "2025", "gia_tri": 1.0, "nguon": "kiểm thử"},
                                  {"cap": "CNP ← CON", "cua_so": "01/2025 → 06/2025", "gia_tri": 0.9,
                                   "nguon": "kiểm thử"}]})

    def env(self):
        e = super().env()
        e["MSN_REFLEX_DIR"] = os.path.join(self.root, "khong_co_msn")
        return e


def walk_blocks(page):
    for s in page["trang"]["sections"]:
        for b in s["khoi"]:
            yield s["id"], b


def units(b):
    """The guard's unit of labelling: a table header and each table ROW, each list item, card, tile and warning line,
    else the whole block (one frozen row must not exempt the rest of its table)."""
    k = b.get("kieu")
    if k == "bang":
        yield {x: b.get(x) for x in ("cot", "chu_thich", "tieu_de")}
        yield from b.get("dong", [])
    elif k == "danh_sach":
        yield from b.get("muc", [])
    elif k == "the":
        yield from b.get("the", [])
    elif k == "o_so":
        yield from b.get("o", [])
    elif k == "canh_bao":
        yield b.get("tieu_de")
        yield from b.get("muc", [])
    else:
        yield b


def leaked(blocks):
    """Units carrying order / rating / sizing / target-price words outside a ĐÓNG BĂNG label."""
    out = []
    for sid, b in blocks:
        for u in units(b):
            t = json.dumps(u, ensure_ascii=False).replace('\\"', '"')
            m = STANCE.search(t) if DB not in t else None
            if m:
                out.append((sid, t[max(0, m.start() - 60):m.end() + 40]))
    return out


def unlabel(o, label):
    """o without the guard's labels: "<label> · " / "<label>: " prefixes, label tags and label chips."""
    if isinstance(o, str):
        for sep in (" · ", ": "):
            o = o.replace(label + sep, "")
        return "" if o == label else o
    if isinstance(o, list):
        return [unlabel(x, label) for x in o if x != label and x != {"tier": label, "text": ""}]
    if isinstance(o, dict):
        return {k: unlabel(v, label) for k, v in o.items() if not (k == "nhan_dong_bang" and v == label)}
    return o


def check_blocks(tc, blocks):
    for sid, b in blocks:
        tc.assertIn(b["kieu"], BLOCK_KINDS, sid)
        if b["kieu"] == "bang":
            for r in b["dong"]:
                tc.assertEqual(len(r), len(b["cot"]), (sid, b["cot"], r))
        if b["kieu"] == "bieu_do":
            bl = b["block"]
            if bl.get("loai") == "cot":
                for s in bl["series"]:
                    tc.assertEqual(len(s["y"]), len(bl["nhan"]), sid)
            else:
                n = len(bl["x"])
                tc.assertTrue(n > 0, sid)
                for s in bl["series"]:
                    for k in ("y", "y_lo", "y_hi"):
                        if k in s:
                            tc.assertEqual(len(s[k]), n, (sid, b["tieu_de"], s["name"], k))
        if b["kieu"] == "o_so":
            tc.assertTrue(1 <= b["cot"] <= 12)


def ann_off_axis(blocks):
    """point / vline annotations of line charts whose x lies outside the drawn x axis (LkChart drops them
    silently while captions may still cite them) → [(sid, chart title, annotation text)]."""
    out = []
    for sid, b in blocks:
        bl = b.get("block") if b.get("kieu") == "bieu_do" else None
        if not bl or bl.get("loai") or not bl.get("x"):
            continue
        lo, hi = M.day_ms(M.parse_day(min(bl["x"]))), M.day_ms(M.parse_day(max(bl["x"])))
        for a in bl.get("annotations") or []:
            if a.get("kind") in ("point", "vline") and a.get("x") is not None and not lo <= a["x"] <= hi:
                out.append((sid, b.get("tieu_de"), a.get("text")))
    return out


def charts(page):
    return [b for _, b in walk_blocks(page) if b["kieu"] == "bieu_do"]


def full_warnings(page):
    """The FULL warning list: the canh_bao block at the end of the "nguon" section (meta.warnings is a summary)."""
    nguon = next(s for s in page["trang"]["sections"] if s["id"] == "nguon")
    blocks = [b for b in nguon["khoi"] if b["kieu"] == "canh_bao"]
    return blocks[-1]["muc"] if blocks else []


def cell_t(c):
    return c["t"] if isinstance(c, dict) else c


def payload_bytes(page):
    """Size of the page as chaebol_reflex.py emits it (compact UTF-8 JSON)."""
    return len(json.dumps(M.clean(page), ensure_ascii=False, separators=(",", ":"), allow_nan=False,
                          default=str).encode("utf-8"))


class FxCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = Fx()
        cls.env = cls.fx.env()
        with mock.patch.dict(os.environ, cls.env):
            t = time.time()
            cls.pa = T.build_page("nhom_a")
            cls.t_pa = time.time() - t
            cls.pb = T.build_page("nhom_b")
            cls.plag = T.build_page("nhom_lag")
            cls.pa2 = T.build_page("nhom_a2")
            cls.ptruc = T.build_page("nhom_truc")
            cls.pkg = T.build_page("nhom_khong_gia")
            cls.tq = T.build_page()
            cls.aio = {}
            for ma in ("PBB", "CBB", "CON", "STL"):
                t = time.time()
                cls.aio[ma] = (T.o_aio(ma), time.time() - t)

    @classmethod
    def tearDownClass(cls):
        cls.fx.close()

    def sec(self, page, sid):
        return next(s for s in page["trang"]["sections"] if s["id"] == sid)

    def pages(self):
        return (self.pa, self.pb, self.plag, self.pa2, self.ptruc, self.pkg, self.tq)

    def run_main(self, argv, env=None):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, env or self.env), redirect_stdout(buf):
            self.assertEqual(C.main(argv), 0)
        lines = buf.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 1)
        return json.loads(lines[0])


# ── CLI ──────────────────────────────────────────────────────────────────────


class CliTests(FxCase):
    def test_nhom_lists_groups_in_display_order(self):
        out = self.run_main(["x", "nhom"])
        self.assertEqual([g["id"] for g in out["ds_nhom"]], DS_ORDER)
        self.assertEqual(set(out["ds_nhom"][1]), {"id", "ten", "truc", "me", "co_hoi_dong"})
        self.assertEqual(out["ds_nhom"][1]["me"], "PAR")
        self.assertTrue(out["ds_nhom"][1]["co_hoi_dong"])
        self.assertEqual(out["meta"]["so_nhom"], 8)

    def test_overview_default_is_tong_quan(self):
        out = self.run_main(["x", "overview"])
        self.assertEqual(out["meta"]["nhom"]["id"], T.TONG_QUAN)
        self.assertEqual(self.run_main(["x", "overview", "--nhom", "tong_quan"])["meta"]["nhom"]["id"], T.TONG_QUAN)

    def test_overview_by_group_and_by_ticker(self):
        out = self.run_main(["x", "overview", "--nhom", "nhom_b"])
        self.assertEqual(out["meta"]["nhom"]["id"], "nhom_b")
        self.assertEqual(self.run_main(["x", "overview", "--ma", "PBB"])["meta"]["nhom"]["id"], "nhom_b")   # parent
        self.assertEqual(self.run_main(["x", "overview", "--ma", "cdt"])["meta"]["nhom"]["id"], "nhom_a2")  # LT child
        self.assertEqual(self.run_main(["x", "overview", "--ma", "CON"])["meta"]["nhom"]["id"], "nhom_a")   # order
        self.assertEqual(self.run_main(["x", "overview", "--ma", "LDB"])["meta"]["nhom"]["id"], "nhom_lag")  # any
        out = self.run_main(["x", "overview", "--nhom", "nhom_a", "--den", "2026-09-15"])
        self.assertEqual(out["meta"]["den"], "2026-09-15")

    def test_ma_command(self):
        out = self.run_main(["x", "ma", "--ma", "CON"])
        self.assertEqual(out["meta"]["nhom_ids"], ["nhom_a", "nhom_a2"])
        self.assertEqual(out["o"]["id"], "reflex")
        self.assertIsNone(self.run_main(["x", "ma", "--ma", "ZZZ"])["o"])

    def test_errors(self):
        empty = dict(self.env, CHAEBOL_REFLEX_DIR=os.path.join(self.fx.root, "khong_co_reg"))
        for argv in (["x", "nhom"], ["x", "overview"], ["x", "ma", "--ma", "VIC"]):
            self.assertEqual(self.run_main(argv, empty)["error_code"], "NO_REGISTRY", argv)
        for argv in (["x"], ["x", "khong"], ["x", "overview", "--tuan", "x"], ["x", "overview", "--nhom"],
                     ["x", "overview", "--nhom", "nhom_a", "--ma", "PAR"], ["x", "overview", "--den", "2026-13-01"],
                     ["x", "overview", "--nhom", "Bad Id"], ["x", "ma"], ["x", "ma", "--ma", "??"],
                     ["x", "nhom", "--den", "2026-09-01"], ["x", "overview", "--nhom", "a", "--nhom", "b"]):
            self.assertEqual(self.run_main(argv)["error_code"], "BAD_ARGS", argv)
        for argv in (["x", "overview", "--nhom", "khong_co"], ["x", "overview", "--ma", "ZZZ"]):
            self.assertEqual(self.run_main(argv)["error_code"], "UNKNOWN_GROUP", argv)
        with mock.patch.object(T, "build_page", side_effect=RuntimeError("hỏng")):
            out = self.run_main(["x", "overview"])
        self.assertEqual(out["error_code"], "INTERNAL")
        self.assertIn("hỏng", out["error"])

    def test_subprocess_emits_one_json_object(self):
        p = subprocess.run([sys.executable, "-B", SCRIPT, "overview", "--nhom", "nhom_lag"], capture_output=True,
                           text=True, env=dict(os.environ, **self.env, PYTHONDONTWRITEBYTECODE="1"), timeout=120)
        self.assertEqual(p.returncode, 0)
        lines = p.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["meta"]["nhom"]["id"], "nhom_lag")


# ── pages ────────────────────────────────────────────────────────────────────


class PageTests(FxCase):
    def test_full_group_page_has_every_section_in_order(self):
        self.assertEqual([s["id"] for s in self.pa["trang"]["sections"]], list(T.SIDS))
        cong = self.pa["trang"]["sections"][0]["khoi"][0]
        self.assertEqual(cong["kieu"], "cong")
        self.assertTrue(cong["dong"].startswith("CỔNG: [CẦN DATA] · v1.7 DỪNG"))
        self.assertIn("chủ thể CẦN", cong["dong"])
        for page in self.pages():
            check_blocks(self, walk_blocks(page))
            self.assertEqual(page["trang"]["schema"], "vnblocks/1")
            self.assertEqual(page["trang"]["sections"][0]["id"], "cong")
            self.assertEqual(page["trang"]["sections"][-1]["id"], "nguon")
            json.dumps(page, ensure_ascii=False, allow_nan=False)

    def test_meta_contract(self):
        m = self.pa["meta"]
        for k in ("generated", "script_version", "nhom", "ds_nhom", "data_to", "stale", "stale_text", "warnings",
                  "sources_live", "artifact_url", "profile_file", "profile_date", "age_days"):
            self.assertIn(k, m)
        self.assertEqual(m["nhom"], {"id": "nhom_a", "ten": "Nhóm A", "me": "PAR", "so_ma": 5, "co_ho_so": True,
                                     "co_hoi_dong": True})
        self.assertEqual([g["id"] for g in m["ds_nhom"]], DS_ORDER)
        self.assertTrue(m["profile_file"].endswith("ho_so_2026-09-20.json"))      # newest VALID dossier
        self.assertTrue(any("ho_so_2026-09-22.json" in w and "schema" in w for w in m["warnings"]))
        self.assertEqual(m["artifact_url"], "https://claude.ai/artifact/test_a")
        self.assertEqual(m["data_to"], TL.DATA_TO.isoformat())
        self.assertFalse(m["stale"])
        self.assertEqual(self.tq["meta"]["nhom"]["id"], T.TONG_QUAN)

    def test_parent_null_page_has_no_ratio_or_parent_chart(self):
        titles = [b["tieu_de"] for b in charts(self.plag)]
        self.assertFalse([t for t in titles if "÷ look-through" in t])
        self.assertFalse([t for t in titles if "dải σ" in t and "mã vốn hóa lớn nhất" not in t])
        rebased = next(b for b in charts(self.plag) if b["tieu_de"].startswith("Quy về 100"))
        self.assertIn("LDA", rebased["chu_thich"])
        ids = [s["id"] for s in self.plag["trang"]["sections"]]
        self.assertEqual(ids, ["cong", "he_sinh_thai", "theo_doi_tuan", "do_tre", "khung", "nguon"])
        txt = json.dumps(self.sec(self.plag, "he_sinh_thai"), ensure_ascii=False)
        self.assertIn("Nhóm không có mẹ niêm yết", txt)
        self.assertTrue(any("nhom_lag chưa có hồ sơ" in w for w in self.plag["meta"]["warnings"]))
        a_titles = [b["tieu_de"] for b in charts(self.pa)]
        self.assertIn("PAR ÷ look-through theo tuần", a_titles)
        self.assertIn("PAR theo tuần và dải σ", a_titles)
        self.assertTrue(any(b["block"].get("loai") == "cot" for b in charts(self.pa)))

    def test_signals_log_and_csv(self):
        tdt = self.sec(self.pa, "theo_doi_tuan")
        sig = next(b for b in tdt["khoi"] if b["kieu"] == "bang" and b["cot"][0] == "#")
        by = {r[0]["t"]: r for r in sig["dong"]}
        self.assertEqual(by["X1"][4]["t"], "Đạt")
        self.assertEqual(by["P2"][4]["t"], "Kích hoạt")
        self.assertEqual(by["N1"][4]["t"], "theo hồ sơ")
        log = next(b for b in tdt["khoi"] if b["kieu"] == "bang" and b["cot"][0].startswith("Tuần"))
        self.assertEqual(len(log["dong"]), T.LOG_WEEKS + 1)                     # + the open week
        self.assertIn("đang mở", log["dong"][0][0]["t"])
        self.assertFalse(any(b["kieu"] == "canh_bao" for b in tdt["khoi"]))         # moved to the end of "nguon"
        self.assertTrue(full_warnings(self.pa))
        self.assertEqual(self.pa["csv"]["columns"], T.CSV_COLS)
        self.assertTrue(all(len(r) == 7 for r in self.pa["csv"]["rows"]))
        self.assertTrue(any(r[0] == "Tín hiệu" for r in self.pa["csv"]["rows"]))

    def test_frozen_history_and_guard(self):
        nd = self.sec(self.pa, "nhan_dinh_cu")["khoi"][0]
        txt = json.dumps(nd, ensure_ascii=False)
        self.assertIn(DB, txt)
        self.assertIn("NAV", txt)                                                # shown verbatim, frozen
        self.assertEqual(nd["dong"][0][0]["t"], "01/09/2026")                    # newest first
        kn = self.sec(self.pa, "keynotes")["khoi"][0]["muc"]
        k2 = next(x for x in kn if x["so"] == "K2")
        self.assertTrue(k2["tags"][0].startswith(DB + " · hồ sơ nhom_a 20/09/2026"))
        k1 = next(x for x in kn if x["so"] == "K1")
        self.assertNotIn(DB, json.dumps(k1, ensure_ascii=False))
        self.assertTrue(any("lệnh, xếp hạng, định cỡ vị thế hoặc mức giá của nguồn" in w
                            for w in self.pa["meta"]["warnings"]))
        for page in self.pages():
            self.assertEqual(leaked(walk_blocks(page)), [], page["meta"]["nhom"]["id"])

    def test_guard_reads_ratings_and_targets_row_by_row(self):
        ev = self.sec(self.pa, "su_kien")["khoi"][0]
        rows = {r[1].split(" · ")[-1]: r[1] for r in ev["dong"]}
        lab = DB + " · hồ sơ nhom_a 20/09/2026 · "
        self.assertEqual(rows["HSC hạ CON xuống Giữ (TP −20%)"], lab + "HSC hạ CON xuống Giữ (TP −20%)")
        self.assertEqual(rows["Vietcap xếp PAR M-PF, TP 43.300đ"], lab + "Vietcap xếp PAR M-PF, TP 43.300đ")
        self.assertEqual(rows["Sự kiện mới nhất"], "Sự kiện mới nhất")          # its neighbours are not frozen
        self.assertIn(DB, ev["chu_thich"])
        yd = self.sec(self.pa, "y_do_chu_the")["khoi"][0]["muc"]
        self.assertTrue(yd[1]["tags"][0].startswith(DB))                         # AVOID, khả quan
        self.assertNotIn(DB, json.dumps(yd[0], ensure_ascii=False))
        for sid in ("truyen_dan", "viec_treo"):                                  # TP.HCM, the disclaimer
            sec = self.sec(self.pa, sid)
            self.assertNotIn("ĐÓNG BĂNG · hồ sơ", json.dumps([b for b in sec["khoi"] if b["kieu"] in
                                                              ("danh_sach",)], ensure_ascii=False), sid)
        vg = next(b for b in self.sec(self.pa, "vung_gia")["khoi"] if b["kieu"] == "bang" and b["cot"][0] == "Mã"
                  and "Vùng" in b["cot"])
        self.assertIn(DB, vg["chu_thich"])
        self.assertTrue(vg["dong"][0][4].startswith(DB))                        # the row itself, not only the caption

    def test_dossier_tables_carry_a_tier_column(self):
        for sid, first in (("dot_tang", "Đợt"), ("do_tre", "Cặp"), ("truyen_dan", "Cặp"), ("vung_gia", "Mã"),
                           ("nhan_dinh_cu", "Ngày")):
            tabs = [b for b in self.sec(self.pa, sid)["khoi"] if b["kieu"] == "bang" and b["cot"][0] == first
                    and b["cot"][-1] == "Nhãn"]
            self.assertTrue(tabs, sid)
        dt = self.sec(self.pa, "dot_tang")["khoi"][0]
        self.assertEqual(dt["dong"][0][-1]["t"], T.T_UNV)                        # row without a tier
        obs = next(b for b in self.sec(self.pa, "do_tre")["khoi"] if b["kieu"] == "bang" and b["cot"][-1] == "Nhãn")
        self.assertEqual(obs["dong"][0][-1]["t"], "EST")
        tdt = self.sec(self.pa, "theo_doi_tuan")
        log = next(b for b in tdt["khoi"] if b["kieu"] == "bang" and b["cot"][0].startswith("Tuần"))
        self.assertTrue(log["chu_thich"].startswith(T.LOG_TIER))

    def test_capture_window_without_prices_does_not_crash(self):
        ids = [s["id"] for s in self.pkg["trang"]["sections"]]
        self.assertIn("truyen_dan", ids)
        fz = next(b for b in self.sec(self.pkg, "truyen_dan")["khoi"] if b["kieu"] == "bang")
        self.assertEqual([r[3]["t"] for r in fz["dong"]], [M.CAN, M.CAN])
        stub = type("S", (), {"data_to": None})()
        w = T.Trang.window_of
        self.assertEqual(w(stub, {"cua_so": "2025"}), (date(2024, 12, 31), date(2025, 12, 31)))
        self.assertEqual(w(stub, {"cua_so": "năm 2025"}), (date(2024, 12, 31), date(2025, 12, 31)))
        self.assertEqual(w(stub, {"cua_so": "01/2025 → 06/2025"}), (date(2025, 1, 1), date(2025, 6, 30)))
        stub.data_to = date(2025, 3, 14)
        self.assertEqual(w(stub, {"cua_so": "2025"})[1], date(2025, 3, 14))
        fz = next(b for b in self.sec(self.pa, "truyen_dan")["khoi"] if b["kieu"] == "bang" and b["cot"][0] == "Cặp")
        self.assertRegex(fz["dong"][2][3]["t"], r"^−?\d")                        # "năm 2025" recomputed live

    def test_lead_lag_and_correlation_wording(self):
        dt = next(b for b in self.sec(self.pb, "do_tre")["khoi"] if b["kieu"] == "bang" and b["cot"][0] == "Chu kỳ")
        self.assertTrue(any("(đang mở)" in c["t"] for r in dt["dong"] for c in r if isinstance(c, dict)))
        tq = next(b for b in self.sec(self.plag, "do_tre")["khoi"] if b["kieu"] == "bang" and b["cot"][0] == "Mã"
                  and "r (cùng tuần)" in b["cot"])
        self.assertIn("Bonferroni 13 độ trễ", tq["cot"][4])
        pills = [r[5]["t"] for r in tq["dong"]]
        self.assertIn("vượt ngưỡng, chưa phải quy luật khai thác được", pills)
        self.assertIn("không phải quy luật dẫn/trễ khai thác được", tq["chu_thich"])

    def test_percentile_tiles_show_their_window(self):
        tiles = {t["nhan"]: t for b in self.sec(self.pa, "he_sinh_thai")["khoi"] if b["kieu"] == "o_so"
                 for t in b["o"]}
        self.assertRegex(tiles["Phân vị 3 năm"]["phu"], r"từ 29/09/2023 · \d+ tuần")
        self.assertRegex(tiles["Phân vị 3 năm"]["gia_tri"], r"^\d+%$")
        self.assertIn("từ 29/09/2023", tiles["Trung vị 3 năm"]["phu"])

    def test_stale_member_page_and_cell_share_the_axis(self):
        self.assertEqual(self.ptruc["meta"]["data_to"], TL.DATA_TO.isoformat())   # STL lags, CDT is the axis
        self.assertEqual(self.ptruc["live"]["co_so"], "CDT")
        o, _ = self.aio["STL"]
        self.assertEqual(o["trang_thai_ngay"], self.ptruc["meta"]["data_to"])
        self.assertTrue(any("giá STL dừng ở" in w for w in self.ptruc["meta"]["warnings"]))

    def test_dossier_cong_without_dung_is_flagged(self):
        self.assertTrue(any("không ghi v1.7 DỪNG" in w for w in self.pb["meta"]["warnings"]))   # gate: in the summary
        full = full_warnings(self.pb)
        self.assertTrue(any("không ghi v1.7 DỪNG" in w for w in full))
        self.assertTrue(any("nhom_b thiếu phần \"keynotes\"" in w for w in full))
        self.assertTrue(any("nhom_b thuộc 14 nhóm có Hội đồng" in w for w in full))

    def test_framework_section(self):
        s = self.sec(self.pa, "khung")
        txt = json.dumps(s, ensure_ascii=False)
        self.assertIn(K.NHAN_DAU_HIEU, txt)
        signs = next(b for b in s["khoi"] if b["kieu"] == "bang" and b["cot"] == K.SIGN_COLS)
        rows = [[c["t"] if isinstance(c, dict) else c for c in r] for r in signs["dong"]]
        self.assertTrue(rows[0][0])                                             # framework name on its first row only
        self.assertFalse([r for prev, r in zip(rows, rows[1:]) if r[0] and r[0] == prev[0]])
        full, last = [], None
        for r in rows:                                                           # a sign on several tickers: text once
            if r[1]:
                last = r
            full.append(r if r[1] else [last[0], last[1], r[2], last[3]] + r[4:])
        rows = full
        d1 = next(r for r in rows if r[1].startswith("D1"))
        self.assertEqual((d1[2], d1[4]), ("PAR", "ĐÃ THẤY"))                    # KL 3,0× ≥ 1,5×
        d2 = [r for r in rows if r[1].startswith("D2")]
        self.assertEqual(sorted(r[2] for r in d2), ["CDT", "CON", "GRC", "PAR"])
        self.assertIn("x 10", next(r for r in d2 if r[2] == "PAR")[3])         # x_pct → x
        cont = [r for r in signs["dong"] if r[1] == ""]
        self.assertEqual(len(cont), 3)
        self.assertTrue(all(r[3]["t"] == K.DITTO for r in cont))
        d3 = next(r for r in rows if r[1].startswith("D3"))
        self.assertIn("p 60", d3[3])
        self.assertIn("cua_so 3y", d3[3])
        r1 = next(r for r in rows if r[1].startswith("R1"))
        self.assertEqual(r1[4], "ĐÃ THẤY")                                      # LNST +50% ≥ 20%
        self.assertTrue(all(r[8] in ("EST", "FACT-T2") for r in rows))
        self.assertIn("ánh xạ của nguồn: Khung riêng A", txt)
        full = full_warnings(self.pa)
        self.assertTrue(any("khung_chung\" ghi hai lần" in w for w in full))
        self.assertNotIn("Concentration Era", txt)                             # not applied to groups
        lag = json.dumps(self.sec(self.plag, "khung"), ensure_ascii=False)
        self.assertNotIn("Khung riêng A", lag)
        self.assertIn("nhóm không có tỷ số", lag)                               # ty_so_holdco_pct → [CẦN DATA]

    def test_transmission_and_captures(self):
        s = self.sec(self.pa, "truyen_dan")
        fz = next(b for b in s["khoi"] if b["kieu"] == "bang" and b["cot"][0] == "Cặp")
        self.assertIn(DB, fz["chu_thich"])
        live = [r[3]["t"] for r in fz["dong"]]
        self.assertRegex(live[0], r"^(−?\d|\[CẦN DATA\])")
        self.assertEqual(live[1], M.CAN)                                       # window not parseable
        self.assertEqual(self.sec(self.pa, "do_tre")["khoi"][-1]["kieu"], "bang")

    def test_council_section(self):
        s = self.sec(self.pa, "hoi_dong")
        cards = [c for b in s["khoi"] if b["kieu"] == "the" for c in b["the"]]
        mau = {c["tieu_de"].split(" · ")[0]: c["nhan"]["mau"] for c in cards if c.get("nhan")}
        self.assertEqual((mau["Munger"], mau["Klarman"], mau["Soros"]), ("do", "vang", "xanh"))
        self.assertIn("21/09/2026", s["eyebrow"])
        self.assertTrue(any(b["kieu"] == "bang" and b["cot"] == ["Ng", "Lo", "Md", "Bb", "Pc", "Hc"] for b in s["khoi"]))

    def test_den_skips_newer_dossier_and_council(self):
        with mock.patch.dict(os.environ, self.env):
            p = T.build_page("nhom_a", den=date(2026, 9, 15))
        self.assertTrue(p["meta"]["profile_file"].endswith("ho_so_2026-08-01.json"))
        self.assertIsNone(p["meta"]["hoi_dong_file"])
        self.assertNotIn("hoi_dong", [s["id"] for s in p["trang"]["sections"]])
        self.assertTrue(any("lập sau mốc --den" in w for w in p["meta"]["warnings"]))
        self.assertEqual(p["meta"]["data_to"], "2026-09-15")

    def test_group_page_budget(self):
        self.assertLess(self.t_pa, 1.5)

    def test_meta_warnings_are_a_short_summary(self):
        for page in self.pages():
            w = page["meta"]["warnings"]
            self.assertLessEqual(len(w), T.MAX_META_WARNINGS, page["meta"]["nhom"]["id"])
            self.assertFalse([x for x in w if x.startswith("Mục \"")], page["meta"]["nhom"]["id"])  # guard notes: 1 line
            self.assertEqual(page["trang"]["sections"][-1]["khoi"][-1]["kieu"], "canh_bao")        # full list, bottom
            self.assertFalse([b for s in page["trang"]["sections"][:-1] for b in s["khoi"] if b["kieu"] == "canh_bao"])
        full = full_warnings(self.pa)
        self.assertGreater(len(full), len(self.pa["meta"]["warnings"]))
        notes = [x for x in full if "trích lệnh, xếp hạng, định cỡ vị thế hoặc mức giá của nguồn" in x]
        self.assertGreater(len(notes), 1)
        agg = [x for x in self.pa["meta"]["warnings"] if "mục trích lệnh, xếp hạng" in x]
        self.assertEqual(len(agg), 1)
        self.assertTrue(agg[0].startswith("%d mục" % len(notes)))
        self.assertIn("Sự kiện", agg[0])                                         # names the sections
        self.assertTrue(any("Bỏ hồ sơ" in x and "ho_so_2026-09-22.json" in x for x in self.pa["meta"]["warnings"]))
        self.assertTrue(any(x.startswith("Còn ") and "mục Nguồn" in x for x in self.pa["meta"]["warnings"]))

    def test_member_table_split(self):
        hs = self.sec(self.pa, "he_sinh_thai")
        tabs = {tuple(b["cot"]): b for b in hs["khoi"] if b["kieu"] == "bang"}
        priced = tabs[tuple(T.MEMBER_COLS)]
        self.assertEqual(T.MEMBER_COLS[-1], "σ P/B (P/E)")
        self.assertNotIn("Σ", T.MEMBER_COLS)
        self.assertFalse([r for r in priced["dong"] if "chưa niêm yết" in cell_t(r[0])])
        other = tabs[tuple(T.KHONG_GIA_COLS)]
        self.assertEqual(T.KHONG_GIA_COLS, ["Tên", "Vai trò", "Mẹ trực tiếp", "Tỷ lệ (pháp lý · hiệu dụng)",
                                           "As-of · bậc", "Ghi chú"])
        row = next(r for r in other["dong"] if cell_t(r[0]) == "Công ty chưa niêm yết")
        self.assertEqual([cell_t(c) for c in row[1:5]], ["con · chưa", "PAR", "40% · –", "30/06/2026 · FACT-T2"])
        self.assertLessEqual(len(row[5]["t"]), T.GHI_CHU_CUT)
        self.assertEqual(row[5]["tip"], GHI_CHU_DAI)                              # full note in the tip
        self.assertNotIn("/Users/", row[5]["t"])
        heads = [b["text"] for b in hs["khoi"] if b["kieu"] == "doan" and b.get("mau") == "vang"]
        self.assertTrue(any(h.startswith(T.TEN_KHONG_GIA) for h in heads))

    def test_source_paths_are_shortened_with_the_full_string_in_the_tip(self):
        dt = self.sec(self.pa, "dot_tang")["khoi"][0]
        self.assertEqual(dt["dong"][0][5], {"t": "_System/kiem_thu/dot_tang.json", "tip": SYS_SRC})
        ev = self.sec(self.pa, "su_kien")["khoi"][0]
        c = next(r[3] for r in ev["dong"] if r[1] == "Sự kiện tháng 7")
        self.assertEqual(c, {"t": "su_kien_cbtt.json", "tip": TMP_SRC})
        self.assertEqual(next(r[3] for r in ev["dong"] if r[1] == "Sự kiện mới nhất"), "CBTT")   # untouched
        kh = self.sec(self.pa, "khung")
        tb = next(b for b in kh["khoi"] if b["kieu"] == "bang" and b["cot"][0] == "Pha" and "Thành phần cũ" in
                  b.get("chu_thich", ""))
        self.assertEqual([r[3] for r in tb["dong"]], [{"t": "Downloads/master_plan.jsx · tab vicstory · L1",
                                                      "tip": JSX_SRC % 1},
                                                     {"t": K.DITTO + " · L2", "tip": JSX_SRC % 2}])
        txt = json.dumps(self.pa["trang"]["sections"], ensure_ascii=False)
        for full in (SYS_SRC, TMP_SRC):                                           # only ever as a tip
            self.assertEqual(txt.count(json.dumps(full, ensure_ascii=False)),
                             txt.count('"tip": %s' % json.dumps(full, ensure_ascii=False)))

    def test_group_framework_section_is_compact(self):
        s = self.sec(self.pa, "khung")
        txt = json.dumps(s, ensure_ascii=False)
        for body in ("giá đi trước", "① → ②", "bước một"):                       # never a framework's noi_dung
            self.assertNotIn(body, txt)
        self.assertIn(K.CHI_TIET, txt)
        heads = [b["text"] for b in s["khoi"] if b["kieu"] == "doan" and b.get("mau") == "vang"]
        self.assertEqual(len([h for h in heads if h.endswith("ánh xạ của nguồn: Khung riêng A")]), 1)   # alias merged
        self.assertIn(DB + " · ánh xạ của nguồn: khong_co_trong_thu_vien · khung riêng của hồ sơ", heads)
        full = full_warnings(self.pa)
        self.assertFalse([w for w in full if w.startswith("Hồ sơ dẫn khung")])     # no per-id warning
        agg = [w for w in full if "khung chỉ có trong hồ sơ" in w]
        self.assertEqual(agg, ["1 khung chỉ có trong hồ sơ (không có trong thư viện): khong_co_trong_thu_vien"])


class TongQuanTests(FxCase):
    def test_sections_rows_and_charts(self):
        self.assertEqual([s["id"] for s in self.tq["trang"]["sections"]], list(T.TQ_SIDS))
        tb = self.sec(self.tq, "nhom")["khoi"][0]
        self.assertEqual([r[0]["tip"] for r in tb["dong"]], [g["id"] for g in registry()["nhom"]])
        cot = self.sec(self.tq, "ty_so_nhom")["khoi"][0]["block"]
        self.assertEqual(cot["loai"], "cot")
        self.assertEqual(cot["nhan"], ["Nhóm A", "Nhóm A2", "Nhóm B"])
        self.assertRegex(cot["nhan_phu"][0], r"^phân vị \d+% · từ 29/09/2023 · \d+ tuần$")      # window on every label
        row = next(r for r in tb["dong"] if r[0]["tip"] == "nhom_a")
        self.assertRegex(row[5]["t"], r"phân vị 3 năm \d+% · từ 29/09/2023 · \d+ tuần")
        ev = next(r for r in tb["dong"] if r[0]["tip"] == "nhom_a")[7]
        self.assertEqual(ev, "15/09/2026 · Sự kiện mới nhất")
        ce = json.dumps(self.sec(self.tq, "concentration_era"), ensure_ascii=False)
        self.assertIn(DB, ce)
        self.assertIn("Top 3 chiếm 30%", ce)
        lib = self.sec(self.tq, "thu_vien_khung")
        heads = [b["text"] for b in lib["khoi"] if b["kieu"] == "doan" and b.get("mau") == "vang"]
        self.assertFalse([h for h in heads if h.startswith("Concentration Era")])
        caps = self.sec(self.tq, "capture")["khoi"][0]
        self.assertTrue(any(r[6].startswith(DB) for r in caps["dong"]))
        self.assertTrue(any(r[6] == "LIVE · EST" for r in caps["dong"]))

    def test_library_is_a_compact_index(self):
        lib = self.sec(self.tq, "thu_vien_khung")
        txt = json.dumps(lib, ensure_ascii=False)
        idx = next(b for b in lib["khoi"] if b["kieu"] == "bang" and b["cot"][0] == "Khung (id)")
        self.assertEqual(idx["cot"], ["Khung (id)", "Loại", "Nguồn · tab · dòng", "Áp dụng cho", "Dấu hiệu đo được",
                                      "Mô tả", "Nhãn"])
        self.assertEqual(len(idx["dong"]), 4)                                     # one row per framework
        self.assertIn(DB, idx["chu_thich"])
        core = next(r for r in idx["dong"] if "(vic_reflexivity_7pha)" in cell_t(r[0]))
        self.assertLessEqual(len(core[5]), K.MO_TA_CUT)
        self.assertEqual(core[2]["t"], "JSX v37 · tab vicstory · L1-L9")         # bracketed file path dropped
        self.assertTrue(core[2]["tip"].startswith("JSX v37 (/Users/tester/Downloads/master_plan.jsx)"))
        self.assertEqual(core[6]["t"], "EST (khung, 04/2026)")
        for body in ("giá đi trước", "bước một", "nội dung pha đầy đủ", "điểm chính", "bảng không phải pha"):
            self.assertNotIn(body, txt)                                           # no full content
        tabs = [b for b in lib["khoi"] if b["kieu"] == "bang" and b is not idx]
        self.assertEqual(len(tabs), 1)                                            # only the core framework present
        self.assertEqual(tabs[0]["cot"], ["Pha", "Dau hieu"])                     # the phase table, not the first
        self.assertEqual(len(tabs[0]["dong"]), K.MAX_CORE_ROWS)
        self.assertIn("12/14 dòng", tabs[0]["chu_thich"])
        self.assertTrue(tabs[0]["chu_thich"].startswith(DB))
        ce = json.dumps(self.sec(self.tq, "concentration_era"), ensure_ascii=False)
        self.assertNotIn("nội dung sâu", ce)                                      # parts named, not rendered
        self.assertIn("Phan sau", ce)

    def test_tong_quan_meta_and_warnings(self):
        m = self.tq["meta"]
        self.assertEqual(m["profile_date"], registry()["lap_luc"])
        self.assertLessEqual(len(m["warnings"]), T.MAX_META_WARNINGS)
        cnt = [w for w in m["warnings"] if re.fullmatch(r"\d+ nhóm có cảnh báo dữ liệu \(tổng \d+\) · mở trang nhóm "
                                                        r"để xem", w)]
        self.assertEqual(len(cnt), 1)
        full = full_warnings(self.tq)
        per = [w for w in full if re.match(r"^(Nhóm|Registry) [a-z0-9_]+: \d+ cảnh báo dữ liệu", w)]
        self.assertTrue(per)
        self.assertEqual(int(cnt[0].split()[0]), len({w.split(":")[0].split()[1] for w in per}))
        self.assertEqual(int(re.search(r"tổng (\d+)", cnt[0]).group(1)),
                         sum(int(re.search(r": (\d+) cảnh báo", w).group(1)) for w in per))
        self.assertFalse(any(b["kieu"] == "canh_bao" for b in self.sec(self.tq, "cong")["khoi"]))


# ── ALL-IN-ONE cell ──────────────────────────────────────────────────────────


class AioTests(FxCase):
    def test_parent_cell(self):
        o, dt = self.aio["PBB"]
        self.assertEqual(o["nhom_ids"], ["nhom_b", "nhom_v21"])
        self.assertEqual((o["id"], o["tab"], o["tab_nhan"], o["cot"], o["eyebrow"]),
                         ("reflex", "msn_reflex", "Chaebol Reflex", 12, "Casebook · độ trễ mẹ–con"))
        self.assertEqual(o["tieu_de"], "Chaebol Reflex · Nhóm B · Nhóm V21")
        self.assertIn("mẹ của nhóm Nhóm B · 1 con trong look-through (CBB)", o["khoi"][0]["text"])
        tiles = [t["nhan"] for b in o["khoi"] if b["kieu"] == "o_so" for t in b["o"]]
        self.assertIn("PBB ÷ look-through", tiles)
        self.assertIn("PBB so VN-Index · 13 tuần", tiles)
        self.assertLess(dt, 1.0)

    def test_child_cell(self):
        o, _ = self.aio["CBB"]
        self.assertEqual(o["nhom_ids"], ["nhom_b"])
        self.assertIn("con của PBB · PBB nắm 50% (FACT-T2 31/12/2018) · trong look-through", o["khoi"][0]["text"])
        tiles = {t["nhan"]: t for b in o["khoi"] if b["kieu"] == "o_so" for t in b["o"]}
        self.assertIn("CBB so PBB · 13 tuần", tiles)
        self.assertEqual(o["trang_thai_ngay"], TL.DATA_TO.isoformat())

    def test_two_group_cell(self):
        o, dt = self.aio["CON"]
        self.assertEqual(o["nhom_ids"], ["nhom_a", "nhom_a2"])
        roles = [b["text"] for b in o["khoi"] if b["kieu"] == "doan" and b.get("mau") == "vang"]
        self.assertEqual(len(roles), 2)
        self.assertTrue(roles[0].startswith("Nhóm A · con của PAR · PAR nắm 50%"))
        self.assertIn("tầng holdco của GRC", roles[0])
        sig = next(b for b in o["khoi"] if b["kieu"] == "bang" and b["cot"][0] == "Tín hiệu gần ngưỡng nhất")
        self.assertEqual(len(sig["dong"]), 3)
        ev = next(b for b in o["khoi"] if b["kieu"] == "bang" and b["cot"][0] == "Ngày")
        self.assertEqual([r[1] for r in ev["dong"]], ["Sự kiện mới nhất", DB + " · hồ sơ nhom_a 20/09/2026 · HSC hạ "
                                                      "CON xuống Giữ (TP −20%)", "Sự kiện đầu tháng 9"])
        self.assertTrue(ev["chu_thich"].startswith(DB + " · hồ sơ nhom_a 20/09/2026"))
        tiles = {t["nhan"]: t for t in next(b for b in o["khoi"] if b["kieu"] == "o_so")["o"]}     # nhom_a
        self.assertRegex(tiles["PAR ÷ look-through"]["phu"], r"^phân vị 3 năm \d+% · từ 29/09/2023 · \d+ tuần")
        frozen = [b["text"] for b in o["khoi"] if b["kieu"] == "doan" and b["text"].startswith(DB)]
        self.assertEqual(frozen, ["ĐÓNG BĂNG · Hội đồng 09 01/09/2026: giữ tỷ trọng 5%"])
        self.assertTrue(any(b["kieu"] == "doan" and b["text"].startswith("Hội đồng 21/09/2026") for b in o["khoi"]))
        self.assertEqual(o["ho_so_ngay"], "2026-09-20")
        self.assertLess(dt, 1.0)

    def test_cells_follow_the_aio_contract_and_the_gate(self):
        for ma, (o, _) in self.aio.items():
            check_blocks(self, [(ma, b) for b in o["khoi"]])
            self.assertEqual(leaked([(ma, b) for b in o["khoi"]]), [], ma)

    def test_non_member_and_missing_registry(self):
        with mock.patch.dict(os.environ, self.env):
            self.assertIsNone(T.o_aio("ZZZ"))
            self.assertIsNone(T.o_aio("??"))
            self.assertIsNone(T.o_aio("PAR", root=os.path.join(self.fx.root, "khong_co")))

    def test_extended_cells_for_all_in_one(self):
        # o_aio_mo_rong (public API for all_in_one_mo_rong.py, 10/10/2026): "reflex_*" cells from the group page,
        # never the action / council / rigor / price-zone / forecast / frozen-stance sections, gate applied
        with mock.patch.dict(os.environ, self.env):
            cells = T.o_aio_mo_rong("PAR")
            self.assertEqual(T.o_aio_mo_rong("ZZZ"), [])
            self.assertEqual(T.o_aio_mo_rong("??"), [])
        ids = [c["id"] for c in cells]
        for cid in ("reflex_quy_ve_100", "reflex_ty_so", "reflex_keynotes"):
            self.assertIn(cid, ids)
        self.assertEqual(len(ids), len(set(ids)))
        for c in cells:
            self.assertTrue(c["id"].startswith("reflex_"))
            self.assertIn(c["cot"], (6, 12))
            self.assertEqual((c["tab"], c["tab_nhan"]), (T.TAB_ID, T.TAB_NHAN))
            check_blocks(self, [(c["id"], b) for b in c["khoi"]])
            self.assertEqual(leaked([(c["id"], b) for b in c["khoi"]]), [], c["id"])
            self.assertEqual(ann_off_axis([(c["id"], b) for b in c["khoi"]]), [], c["id"])
        charts = {c["id"]: [b for b in c["khoi"] if b["kieu"] == "bieu_do"] for c in cells}
        self.assertTrue(charts["reflex_quy_ve_100"] and charts["reflex_ty_so"])
        for sid in T.AIO_MO_RONG_BO:
            self.assertNotIn("reflex_" + sid, ids)


# ── framework library ────────────────────────────────────────────────────────


class KhungTests(unittest.TestCase):
    def test_tham_so_aliases(self):
        n = K.normalize_tham_so
        self.assertEqual(n("cach_dinh_52t", {"x_pct": 10}), {"x": 10})
        self.assertEqual(n("lnst_yoy", {"g_pct": 50}), {"g": 50})
        self.assertEqual(n("ty_so_holdco_pct", {"p_pct": 25, "cua_so": "Toàn dải"}), {"p": 25, "cua_so": "toan_dai"})
        self.assertEqual(n("pb_sigma", {"s_sigma": 1.0, "phep": "<="}), {"s": 1.0, "phep": "<="})
        self.assertEqual(n("kl_tuan_tb20", {"k_x": 2}), {"k": 2})
        self.assertEqual(n("parabol", {"nguong": 1.8}), {"k": 1.8})              # nguong / muc = the threshold
        self.assertEqual(n("ty_so_holdco_pct", {"muc": 5}), {"p": 5})
        w = []
        self.assertEqual(n("tang_tu_day", {"pct": 30}, w, "Khung k · D1"), {})    # no guessing
        self.assertEqual(n("kl_tuan_tb20", {"so_tuan": 20}, w, "Khung k · D2"), {})
        self.assertEqual(n("kl_tuan_tb20", {"k": 2, "nguong": 3}, w, "Khung k · D3"), {"k": 2})
        self.assertEqual(len(w), 3)
        self.assertIn("tham số lạ \"so_tuan\" bị bỏ qua", w[1])

    def test_sign_targets(self):
        lv = type("LV", (), {"priced": ["PAR", "CON"], "ok": True})()
        self.assertEqual(K.targets(lv, {"ma": ["VIC", "vhm"]}, {}), (["VIC", "VHM"], []))
        self.assertEqual(K.targets(lv, {"ma": "moi_ma"}, {}), (["PAR", "CON"], []))
        self.assertEqual(K.targets(lv, {}, {"ma": "me"}), ([None], []))
        self.assertEqual(K.targets(lv, {"ma": ["VIC", "Không phải mã"]}, {}), (["VIC"], ["Không phải mã"]))
        rows = K.cham(None, {"id": "k", "dau_hieu_do_duoc": [{"id": "D", "phep_do": "parabol", "ma": "??"}]})
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["ghi_chu"].startswith(M.CAN))

    def test_render_any_shapes(self):
        b = K.render_any({"chuoi": "a → b", "bang": [{"pha": "1", "gia": 2}], "list": ["x", "y"], "nested": {"k": [1]}})
        kinds = [x["kieu"] for x in b]
        self.assertIn("bang", kinds)
        tb = next(x for x in b if x["kieu"] == "bang" and x["cot"] == ["Pha", "Gia"])
        self.assertEqual(tb["dong"], [["1", "2"]])
        self.assertEqual(K.render_any(["a", "b"])[0]["kieu"], "danh_sach")

    def test_guard_labels_every_kind(self):
        blocks = [M.doan("MUA ròng"), M.bang(["a"], [["giá mục tiêu"]]), M.danh_sach([{"so": "1", "text": "8% NAV"}]),
                  M.the_block([M.card("x", "tỷ trọng")]), M.o_so([M.tile("t", "BÁN")]), M.doan("HSC hạ xuống Giữ"),
                  M.doan("Vietcap: TP 43.300đ"), M.doan("ACV M-PF"), M.doan("REALTIME đổi AVOID"),
                  M.doan("lên Mua (TP 50k)"), M.doan("khuyến nghị nắm giữ"), M.doan("triển vọng kém khả quan"),
                  M.doan("Rating: Outperform"), M.doan("BUY"),
                  M.doan("bình thường"), M.doan("mua ròng (chữ thường)"), M.doan("TP.HCM và TP-HCM"),
                  M.doan("Bản tham khảo, KHÔNG phải khuyến nghị."), M.doan("giữ nguyên thứ tự"),
                  M.doan("Holdco và Holdings")]
        w = []
        K.guard_blocks(blocks, "nguồn X 01/01/2026", w, "Mục thử")
        for b in blocks[:14]:
            self.assertIn("ĐÓNG BĂNG · nguồn X 01/01/2026", json.dumps(b, ensure_ascii=False), b)
        self.assertNotIn(DB, json.dumps(blocks[14:], ensure_ascii=False))
        self.assertEqual(len(w), 1)
        self.assertIsNone(STANCE.search(w[0]))
        self.assertEqual(leaked([("x", b) for b in blocks]), [])

    def test_guard_works_row_by_row(self):
        tb = M.bang(["Ngày", "Sự kiện"], [["01/09", DB + " · nguồn A: MUA thêm"], ["02/09", "xuống Giữ (TP −20%)"],
                                          ["03/09", "bình thường"]], DB + " · cả bảng của nguồn")
        ds = M.danh_sach([{"so": "1", "text": "8% NAV", "tags": [DB + " · cũ"]}, {"so": "2", "text": "tỷ trọng 5%"}])
        cb = M.canh_bao("Cảnh báo", ["Nguồn trích BUY", "bình thường"])
        self.assertEqual(K.guard([tb, ds, cb], "nguồn B"), 3)
        self.assertEqual(tb["dong"][0][1], DB + " · nguồn A: MUA thêm")               # its own label is kept
        self.assertEqual(tb["dong"][1][1], DB + " · nguồn B · xuống Giữ (TP −20%)")   # caption label is not enough
        self.assertEqual(tb["dong"][2][1], "bình thường")
        self.assertEqual(ds["muc"][1]["tags"], [DB + " · nguồn B"])
        self.assertEqual(cb["muc"], [DB + " · nguồn B · Nguồn trích BUY", "bình thường"])
        self.assertEqual(K.guard([tb, ds, cb], "nguồn B"), 0)                          # idempotent

    def test_ngan_and_nguon_cell(self):
        self.assertEqual(K.ngan("/Users/macbook/Downloads/x.html"), "Downloads/x.html")
        self.assertEqual(K.ngan("/Users/macbook/SECOND BRAIN-OBSIDIAN/_System/a/b.json · L3"), "_System/a/b.json · L3")
        self.assertEqual(K.ngan("/Users/macbook/SECOND BRAIN-OBSIDIAN/BaoCao_VN30/VIC.md"),
                         "SECOND BRAIN-OBSIDIAN/BaoCao_VN30/VIC.md")
        self.assertEqual(K.ngan("đọc /private/tmp/claude-1/-Users-x/scratch/out.json, rồi so"), "đọc out.json, rồi so")
        self.assertEqual(K.ngan("~/Downloads/x.html · CBTT"), "~/Downloads/x.html · CBTT")
        self.assertEqual(K.nguon_cell("CBTT"), "CBTT")
        self.assertEqual(K.nguon_cell("/Users/u/Downloads/x.html"), {"t": "Downloads/x.html",
                                                                    "tip": "/Users/u/Downloads/x.html"})
        self.assertEqual(K.nguon_cell("abcdef", 4), {"t": "abc…", "tip": "abcdef"})
        self.assertEqual(K.nhu_tren("f.jsx · tab a · L1", "f.jsx · tab a · L2"), K.DITTO + " · L2")
        self.assertEqual(K.nhu_tren("f.jsx · tab a · L1", "f.jsx · tab a · L1"), K.DITTO)
        self.assertEqual(K.nhu_tren("g.md", "f.jsx · tab a"), "f.jsx · tab a")

    def test_lib_index_and_main_table(self):
        lib = {"khung": [{"id": "a", "bi_danh": ["b", "c"]}, {"id": "b"}, {"id": "d", "bi_danh": ["c"]}]}
        idx = K.lib_index(lib)
        self.assertEqual({k: v["id"] for k, v in idx.items()}, {"a": "a", "b": "b", "c": "a", "d": "d"})  # id wins
        e = {"noi_dung": {"x": [{"cap": 1}], "y": {"stage": "s", "Nội dung": [{"stage": "S1"}, {"stage": "S2"}]}}}
        self.assertEqual(K.main_table(e), ("Y", [{"stage": "S1"}, {"stage": "S2"}]))
        self.assertEqual(K.main_table({"noi_dung": {"x": [{"cap": 1}]}}), ("X", [{"cap": 1}]))   # first table
        self.assertEqual(K.main_table({"noi_dung": ["a"]}), (None, []))

    def test_group_mapping_rows_are_capped(self):
        m = {"khung": "k", "anh_xa": [{"pha": str(i), "nguon": "f.jsx · L%d" % i} for i in range(K.MAX_MAP_ROWS + 3)]}
        out = K.mapping_blocks({"id": "k", "ten": "Khung K", "mo_ta": "x" * 300}, "k", [m], ho_so="/Users/u/ho_so.json")
        tb = next(b for b in out if b["kieu"] == "bang")
        self.assertEqual(len(tb["dong"]), K.MAX_MAP_ROWS)
        desc = out[1]["text"]
        self.assertTrue(desc.endswith(" · " + K.CHI_TIET))
        self.assertLessEqual(len(desc), K.DESC_CUT + len(K.CHI_TIET) + 3)
        note = out[-1]["text"]
        self.assertTrue(note.startswith(DB + " · còn 3 dòng"))
        self.assertIn("ho_so.json", note)
        self.assertNotIn("/Users/", note)

    def test_tom_tat_canh_bao(self):
        ws = (["Thiếu nguồn live Vietcap price-history (lớp Lăng Kính) M%02d (/Users/u/vc_lk/M%02d/p.json)" % (i, i)
               for i in range(20)] +
              ["Mục \"Mục %d\" trích lệnh, xếp hạng, định cỡ vị thế hoặc mức giá của nguồn: hiển thị như lịch sử ĐÓNG "
               "BĂNG · hồ sơ x, không chấm lại (CỔNG v1.7 DỪNG)." % i for i in range(30)] +
              ["Nhóm g%d: %d cảnh báo dữ liệu (mở trang nhóm để xem)." % (i, i + 1) for i in range(10)] +
              ["Registry g1: 4 cảnh báo dữ liệu (mở trang nhóm để xem).", "Kho giá thiếu nến của: A11, B22",
               "Nhóm g: GAS không tính vào look-through (nhóm không có mẹ có giá)."])
        out = T.tom_tat_canh_bao(ws)
        self.assertLessEqual(len(out), T.MAX_META_WARNINGS)
        self.assertTrue(out[0].startswith("Thiếu nguồn live Vietcap price-history (lớp Lăng Kính) của 20 mã: M00, "))
        self.assertTrue(out[0].endswith(", …"))
        self.assertEqual(out[1], "Kho giá thiếu nến của 2 mã: A11, B22")
        self.assertTrue(out[2].startswith("30 mục trích lệnh"))
        self.assertIn("Mục 0, Mục 1", out[2])
        self.assertEqual(out[3], "10 nhóm có cảnh báo dữ liệu (tổng 59) · mở trang nhóm để xem")
        self.assertTrue(out[4].startswith("Còn 1 cảnh báo khác"))
        gaps = ["Nhóm g, X ÷ LT: C%d có giá nhưng chưa có dòng sở hữu từ 01/01/2020 đến 01/01/2021, các tuần đó." % i
                for i in range(12)]
        out = T.tom_tat_canh_bao(gaps + ws[20:21])
        self.assertEqual(len(out), T.MAX_META_WARNINGS)
        self.assertEqual(out[:6], gaps[:6])
        self.assertTrue(out[-1].startswith("Còn 6 cảnh báo khác"))
        lag = ["Nhóm g: giá %s dừng ở 02/10/2026, trễ 7 ngày so với ngày dữ liệu 09/10/2026 của nhóm (trục X); số của %s "
               "là của ngày đó." % (t, t) for t in ("AAA", "BBB", "CCC")]
        self.assertEqual(T.tom_tat_canh_bao(lag), ["Nhóm g: giá của 3 mã dừng ở 02/10/2026, trễ 7 ngày so với ngày dữ "
                                                   "liệu 09/10/2026 của nhóm (trục X): AAA, BBB, CCC; số của các mã đó "
                                                   "là của ngày đó."])
        self.assertEqual(T.tom_tat_canh_bao(lag[:1]), lag[:1])                 # one ticker: the line as written

    def test_load_khung_missing_and_bad(self):
        d = tempfile.mkdtemp(prefix="khung_test_")
        try:
            w = []
            self.assertIsNone(K.load_khung(d, w)[0])
            self.assertIn("Chưa có thư viện khung", w[0])
            TL.Fixture.write(os.path.join(d, "khung.json"), {"schema": "khac"})
            w = []
            self.assertIsNone(K.load_khung(d, w)[0])
            self.assertIn("sai schema", w[0])
            TL.Fixture.write(os.path.join(d, "khung.json"), khung())
            lib, path = K.load_khung(d, [])
            self.assertEqual([k["id"] for k in lib["khung"]], ["khung_chung", "khung_rieng_a", "concentration_era",
                                                               "vic_reflexivity_7pha"])
            self.assertEqual([k["id"] for k, r in K.khung_cho(lib, "nhom_a")], ["khung_chung", "khung_rieng_a"])
            self.assertEqual(K.khung_entry(lib, "concentration")["id"], "concentration_era")
            rows = K.cham(None, lib["khung"][0])
            self.assertTrue(all(r["thay"] is None for r in rows))
        finally:
            shutil.rmtree(d, ignore_errors=True)


# ── Masan delegation (test_msn_reflex fixture) ───────────────────────────────


def masan_registry():
    return {"schema": L.SCHEMA_REG, "lap_luc": "2026-09-24", "nhom": [
        {"id": "masan_tcb", "ten": "Masan-Techcombank", "chu_the": "Nguyễn Đăng Quang", "truc": "NQ68", "me": "MSN",
         "dong_co": "msn_reflex", "ho_so_dir": "msn_reflex", "hoi_dong": True, "he_sinh_thai": ["Masan-TCB"],
         "thanh_vien": [{"ma": "MSN", "vai_tro": "mẹ"},
                        {"ma": "MCH", "vai_tro": "con", "me": "MSN", "trong_lt": True,
                         "so_huu": [stake("2025-12-31", 0.7, tier="EST")]},
                        {"ma": "MSR", "vai_tro": "con", "me": "MSN", "trong_lt": True,
                         "so_huu": [stake("2025-12-31", 0.9, tier="EST")]},
                        {"ma": "TCB", "vai_tro": "liên kết", "me": "MSN", "trong_lt": True,
                         "so_huu": [stake("2025-12-31", 0.15)]}]},
        {"id": "nhom_x", "ten": "Nhóm X", "truc": "NQ79", "me": None, "thanh_vien": [{"ma": "TCB"}]}]}


class MasanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prof = TM.profile()
        prof["hoi_dong"] = {"tieu_de": "Hội đồng 24/09", "nhan": "Hội đồng", "kill_zone": [], "alpha_zone": []}
        cls.fx = TM.Fixture(prof=prof)
        cls.reg = os.path.join(cls.fx.root, "chaebol_reflex")
        TM.Fixture.write(os.path.join(cls.reg, "nhom.json"), masan_registry())
        TM.Fixture.write(os.path.join(cls.reg, "khung.json"), khung())
        TM.Fixture.write(os.path.join(cls.reg, "masan_tcb", "hoi_dong_2026-09-21.json"),
                         dict(hoi_dong_a(), nhom="masan_tcb"))
        cls.env = dict(cls.fx.env(), CHAEBOL_REFLEX_DIR=cls.reg)
        with mock.patch.dict(os.environ, cls.env):
            cls.m = M.build_overview()
            cls.p = T.build_page("masan_tcb")
            cls.tq = T.build_page()
            t = time.time()
            cls.o = T.o_aio("TCB")
            cls.t_o = time.time() - t

    @classmethod
    def tearDownClass(cls):
        cls.fx.close()

    @staticmethod
    def norm(s):
        return re.sub(r"tạo lúc \d\d:\d\d \d\d/\d\d", "tạo lúc X", json.dumps(s, ensure_ascii=False))

    def test_msn_sections_untouched_and_generic_sections_added(self):
        mid = [s["id"] for s in self.m["trang"]["sections"]]
        pid = [s["id"] for s in self.p["trang"]["sections"]]
        self.assertEqual([i for i in pid if i in mid], mid)
        added = [i for i in pid if i not in mid]
        self.assertEqual(added, ["hoi_dong_20260921", "do_tre", "khung"])
        self.assertEqual(pid.index("hoi_dong_20260921"), pid.index("hoi_dong") + 1)   # next to the dossier's own
        self.assertEqual(pid[-1], "nguon")
        self.assertEqual(pid.index("khung"), pid.index("nguon") - 1)
        hd = next(s for s in self.p["trang"]["sections"] if s["id"] == "hoi_dong_20260921")
        self.assertIn("Hội đồng 21/09/2026", hd["eyebrow"])
        by = {s["id"]: s for s in self.p["trang"]["sections"]}
        lab = DB + " · hồ sơ MSN 24/09/2026"
        nguon = dict(by["nguon"], khoi=by["nguon"]["khoi"][:-1])                 # minus the engine's canh_bao block
        self.assertEqual(by["nguon"]["khoi"][-1]["kieu"], "canh_bao")
        for s in self.m["trang"]["sections"]:                  # msn_reflex sections modulo the CỔNG labels
            got = nguon if s["id"] == "nguon" else by[s["id"]]
            self.assertEqual(self.norm(unlabel(got, lab)), self.norm(s), s["id"])
        labelled = [s["id"] for s in self.m["trang"]["sections"]
                    if self.norm(by[s["id"]]) != self.norm(s)]
        self.assertIn("theo_doi_tuan", labelled)               # "Kích hoạt → hạ MSN về 3% NAV" is frozen history
        tdt = json.dumps(by["theo_doi_tuan"], ensure_ascii=False)
        self.assertIn(lab + " · LIVE · FACT-T2 · Kích hoạt → hạ MSN về 3% NAV", tdt)
        self.assertEqual(self.p["trang"]["tieu_de"], self.m["trang"]["tieu_de"])
        self.assertEqual(self.p["csv"], self.m["csv"])

    def test_meta_gains_group_keys_only(self):
        pm, mm = self.p["meta"], self.m["meta"]
        self.assertEqual(set(pm) - set(mm), {"nhom", "ds_nhom"})
        for k in mm:
            if k not in ("generated", "warnings"):
                self.assertEqual(pm[k], mm[k], k)
        self.assertEqual(pm["warnings"][:len(mm["warnings"])], mm["warnings"])    # msn_reflex's own, unchanged
        extra = pm["warnings"][len(mm["warnings"]):]
        self.assertEqual(len(extra), 1)                                          # + at most ONE aggregated line
        self.assertTrue(extra[0].startswith("Engine chung của trang"))
        self.assertIn("mục Nguồn", extra[0])
        self.assertEqual(pm["nhom"], {"id": "masan_tcb", "ten": "Masan-Techcombank", "me": "MSN", "so_ma": 4,
                                      "co_ho_so": True, "co_hoi_dong": True})
        self.assertEqual([g["id"] for g in pm["ds_nhom"]], ["tong_quan", "masan_tcb", "nhom_x"])

    def test_every_section_respects_the_gate(self):
        self.assertEqual(leaked(walk_blocks(self.p)), [])       # msn_reflex's own sections included
        extra = [(s["id"], b) for s in self.p["trang"]["sections"] if s["id"] in ("do_tre", "khung", "hoi_dong_20260921")
                 for b in s["khoi"]]
        check_blocks(self, extra)
        self.assertIn(K.NHAN_DAU_HIEU, json.dumps(extra, ensure_ascii=False))
        self.assertFalse(any(b[1]["kieu"] == "canh_bao" for b in extra))           # the block sits in "nguon"
        self.assertTrue(any(w.startswith("Engine Masan: ") for w in full_warnings(self.p)))

    def test_cli_ma_resolves_to_masan(self):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, self.env), redirect_stdout(buf):
            C.main(["x", "overview", "--ma", "MSN"])
        out = json.loads(buf.getvalue())
        self.assertEqual(out["meta"]["nhom"]["id"], "masan_tcb")
        self.assertEqual([s["id"] for s in out["trang"]["sections"]], [s["id"] for s in self.p["trang"]["sections"]])

    def test_tong_quan_and_aio_use_the_masan_engine(self):
        row = next(r for r in next(s for s in self.tq["trang"]["sections"] if s["id"] == "nhom")["khoi"][0]["dong"]
                   if r[0]["tip"] == "masan_tcb")
        self.assertIn("engine Masan", row[5]["t"])
        self.assertIn("từ 01/2024", row[5]["t"])
        cot = next(s for s in self.tq["trang"]["sections"] if s["id"] == "ty_so_nhom")["khoi"][0]["block"]
        lab = cot["nhan_phu"][cot["nhan"].index("Masan-Techcombank")]
        self.assertRegex(lab, r"(phân vị \d+% · )?từ 01/2024 · \d+ tuần · engine Masan|chỉ \d+ tuần từ 01/2024")
        self.assertEqual(leaked(walk_blocks(self.tq)), [])
        o = self.o
        self.assertEqual(o["nhom_ids"], ["masan_tcb", "nhom_x"])
        tiles = {t["nhan"]: t for b in o["khoi"] if b["kieu"] == "o_so" for t in b["o"]}
        self.assertIn("engine Masan", tiles["MSN ÷ look-through"]["phu"])
        self.assertEqual(tiles["MSN ÷ look-through"]["gia_tri"], M.x_txt(self.m["live"]["ratio"]))
        frozen = [b["text"] for b in o["khoi"] if b["kieu"] == "doan" and b["text"].startswith(DB)]
        self.assertTrue(frozen and frozen[0].startswith("ĐÓNG BĂNG · hồ sơ MSN 24/09/2026"))
        sig = next(b for b in o["khoi"] if b["kieu"] == "bang" and b["cot"][0] == "Tín hiệu gần ngưỡng nhất")
        self.assertTrue(1 <= len(sig["dong"]) <= 3)
        self.assertEqual(leaked([("aio", b) for b in o["khoi"]]), [])
        self.assertLess(self.t_o, 1.0)


# ── real stores (skipped when absent) ────────────────────────────────────────


def real_env():
    return {k: v for k, v in os.environ.items() if k not in TL.ENV_KEYS}


def real_ready():
    with mock.patch.dict(os.environ, real_env(), clear=True):
        p = M.paths()
    need = [p["vnstore"], os.path.join(p["profile_dir"], "ho_so_2026-09-24.json")]
    need += [os.path.join(p["vc_lk"], s, f) for s in ("VIC", "VHM", "VPL", "VRE", "GEX", "GEE", "GEL", "EIB", "VGC",
                                                       "TCB", "HDB", "VJC") for f in ("price-history.json",
                                                                                      "shareholder.json")]
    return all(os.path.isfile(x) for x in need)


def real_registry(vc, prof):
    def row(ma, code):
        for r in M.load_json(os.path.join(vc, ma, "shareholder.json"))["du_lieu"]:
            if r.get("ownerCode") == code:
                d = r["publicDate"][:10]
                return {"tu": d, "ty_le": r["percentage"], "loai": "phap_ly", "tier": "FACT-T2",
                        "nguon": "vc_lk/%s/shareholder %s publicDate %s" % (ma, code, d)}
        raise AssertionError("no %s row for %s" % (code, ma))
    ts = prof["theo_doi_tuan"]["tham_so"]["so_huu"]
    hs = {"tu": "2024-01-01", "loai": "phap_ly", "tier": "EST", "nguon": "hồ sơ MSN 24/09/2026 tham_so.so_huu"}
    return {"schema": L.SCHEMA_REG, "lap_luc": "2026-10-10", "ghi_chu": "TEMP, kiểm thử E2", "nhom": [
        {"id": "vingroup", "ten": "Vingroup", "chu_the": "Phạm Nhật Vượng", "truc": "NQ68", "me": "VIC", "hoi_dong": True,
         "he_sinh_thai": ["Vingroup"], "thanh_vien": [
             {"ma": "VIC", "vai_tro": "mẹ"},
             {"ma": "VHM", "vai_tro": "con", "me": "VIC", "trong_lt": True, "so_huu": [row("VHM", "VIC")]},
             {"ma": "VPL", "vai_tro": "con", "me": "VIC", "trong_lt": True, "so_huu": [row("VPL", "VIC")]},
             {"ma": "VRE", "vai_tro": "liên kết", "me": "VIC", "trong_lt": True, "so_huu": [row("VRE", "VIC")]}]},
        {"id": "masan_tcb", "ten": "Masan-Techcombank", "chu_the": "Nguyễn Đăng Quang", "truc": "NQ68", "me": "MSN",
         "dong_co": "msn_reflex", "ho_so_dir": "msn_reflex", "hoi_dong": True, "he_sinh_thai": ["Masan-TCB"],
         "thanh_vien": [{"ma": "MSN", "vai_tro": "mẹ"}] + [
             {"ma": s, "vai_tro": "con", "me": "MSN", "trong_lt": True, "so_huu": [dict(hs, ty_le=ts[s])]}
             for s in ("MCH", "MSR", "TCB")] + [{"ma": "TCX", "vai_tro": "cháu", "me": "TCB"}]},
        {"id": "sovico", "ten": "Sovico", "chu_the": "Nguyễn Thị Phương Thảo", "truc": "NQ68", "me": None,
         "thanh_vien": [{"ma": "HDB", "vai_tro": "ngân hàng của hệ", "so_huu": [row("HDB", "11082")]},
                        {"ma": "VJC", "vai_tro": "thành viên", "so_huu": [row("VJC", "11082")]}]},
        {"id": "gelex", "ten": "GELEX", "chu_the": "Nguyễn Văn Tuấn", "truc": "NQ68", "me": "GEX", "hoi_dong": True,
         "he_sinh_thai": ["GELEX-TuấnMượt"], "thanh_vien": [
             {"ma": "GEX", "vai_tro": "mẹ"},
             {"ma": "GEE", "vai_tro": "con", "me": "GEX", "trong_lt": True, "so_huu": [row("GEE", "GELEX")]},
             {"ma": "GEL", "vai_tro": "con", "me": "GEX", "trong_lt": True, "so_huu": [row("GEL", "GELEX")]},
             {"ma": "EIB", "vai_tro": "liên kết", "me": "GEX", "trong_lt": True, "so_huu": [row("EIB", "GELEX")]},
             {"ma": "VGC", "vai_tro": "cháu", "me": "GEL", "so_huu": [row("VGC", "GELEXINFRAS")]}],
         "tang": [{"me": "GEL", "con": ["VGC"]}]}]}


@unittest.skipUnless(real_ready(), "real stores not present")
class RealStoreSmoke(unittest.TestCase):
    """The four pages + TỔNG QUAN + AIO cells on the real stores, from a TEMP registry (hermetic temp dir)."""

    @classmethod
    def setUpClass(cls):
        cls.env = real_env()
        with mock.patch.dict(os.environ, cls.env, clear=True):
            p = M.paths()
            prof = M.load_profile(p["profile_dir"])[0]
            cls.root = tempfile.mkdtemp(prefix="chaebol_reflex_real_")
            TL.Fixture.write(os.path.join(cls.root, "nhom.json"), real_registry(p["vc_lk"], prof))
            env = dict(cls.env, CHAEBOL_REFLEX_DIR=cls.root)
        cls.renv = env
        cls.out, cls.t = {}, {}
        with mock.patch.dict(os.environ, env, clear=True):
            for nid in ("vingroup", "gelex", "masan_tcb", "sovico", "tong_quan"):
                L.clear_cache()
                t = time.time()
                cls.out[nid] = T.build_page(nid)
                cls.t[nid] = time.time() - t
            for ma in ("VHM", "MSN", "HDB"):
                L.clear_cache()
                t = time.time()
                cls.out["ma_" + ma] = T.o_aio(ma)
                cls.t["ma_" + ma] = time.time() - t
        print("\nE2 real-store timings (cold, in-process): " + ", ".join("%s %.2fs" % kv for kv in cls.t.items()))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_pages_build_within_budget(self):
        for nid in ("vingroup", "gelex", "masan_tcb", "sovico", "tong_quan"):
            page = self.out[nid]
            check_blocks(self, walk_blocks(page))
            ids = [s["id"] for s in page["trang"]["sections"]]
            self.assertEqual(ids[0], "cong")
            self.assertEqual(ids[-1], "nguon")
            print("%-10s %.2fs · %s" % (nid, self.t[nid], " · ".join(ids)))
        for nid in ("vingroup", "gelex", "sovico"):
            self.assertLess(self.t[nid], 1.5, nid)
        self.assertLess(self.t["masan_tcb"], 2.5)
        self.assertLess(self.t["tong_quan"], 3.0)
        for ma in ("VHM", "MSN", "HDB"):
            self.assertLess(self.t["ma_" + ma], 1.0, ma)
            self.assertEqual(self.out["ma_" + ma]["id"], "reflex")

    def test_live_numbers_are_sane(self):
        v = self.out["vingroup"]["live"]["ty_so"]
        self.assertTrue(v["hien_tai"] > 1)                                    # VIC trades above its listed stakes
        g = self.out["gelex"]["live"]["ty_so"]
        self.assertTrue(0.2 < g["hien_tai"] < 1.5)
        self.assertIsNone(self.out["sovico"]["live"]["ty_so"])
        self.assertEqual(self.out["masan_tcb"]["meta"]["nhom"]["id"], "masan_tcb")

    def test_no_trade_words_outside_frozen_blocks(self):
        for nid in ("vingroup", "gelex", "sovico", "tong_quan"):
            self.assertEqual(leaked(walk_blocks(self.out[nid])), [], nid)
        self.assertEqual(leaked(walk_blocks(self.out["masan_tcb"])), [])          # every Masan section
        for ma in ("VHM", "MSN", "HDB"):
            self.assertEqual(leaked([(ma, b) for b in self.out["ma_" + ma]["khoi"]]), [], ma)

    def test_real_registry_if_present(self):
        with mock.patch.dict(os.environ, self.env, clear=True):
            path = os.path.join(L.reg_dir(), "nhom.json")
            if not os.path.isfile(path):
                self.skipTest("registry thật chưa có: %s" % path)
            reg, _ = L.load_registry()
            if not reg.groups():
                self.skipTest("registry thật chưa dùng được: %s" % path)
            slow, big = [], []
            msn = {x.id for x in reg.groups() if T.is_msn(x)}
            for g in [T.TONG_QUAN] + [x.id for x in reg.groups()]:
                L.clear_cache()
                t = time.time()
                page = T.build_page(g)
                dt = time.time() - t
                check_blocks(self, walk_blocks(page))
                self.assertEqual(leaked(walk_blocks(page)), [], g)                # Masan included
                if g not in msn:                                                    # msn_reflex charts: own suite
                    self.assertEqual(ann_off_axis(walk_blocks(page)), [], g)
                nh = (page.get("live") or {}).get("nhom")
                priced = (nh.get("so_ma_co_gia") or 0) if isinstance(nh, dict) else 0
                budget = 4.0 if g == T.TONG_QUAN else (2.5 if g == "masan_tcb" else (4.0 if priced > 20 else 1.5))
                if dt > budget:
                    slow.append((g, round(dt, 2), budget))
                # presentation budgets (10/10/2026): TỔNG QUAN payload, group "khung" section, meta.warnings
                if g == T.TONG_QUAN and payload_bytes(page) > TQ_MAX_BYTES:
                    big.append((g, "payload", payload_bytes(page)))
                for sec in page["trang"]["sections"]:
                    if g != T.TONG_QUAN and sec["id"].startswith("khung") and payload_bytes(sec) > KHUNG_MAX_BYTES:
                        big.append((g, sec["id"], payload_bytes(sec)))
                w = page["meta"]["warnings"]
                if g in msn:                                                       # msn_reflex's own + ≤ 1 line
                    self.assertLessEqual(len([x for x in w if x.startswith("Engine chung của trang")]), 1, g)
                else:
                    self.assertLessEqual(len(w), T.MAX_META_WARNINGS, g)
                self.assertFalse([x for x in full_warnings(page) if x.startswith("Hồ sơ dẫn khung")], g)
            print("\nregistry thật: %d nhóm · vượt ngân sách: %s · vượt cỡ: %s" % (len(reg.groups()), slow or "không",
                                                                               big or "không"))
            self.assertEqual(slow, [])
            self.assertEqual(big, [])


if __name__ == "__main__":
    unittest.main()
