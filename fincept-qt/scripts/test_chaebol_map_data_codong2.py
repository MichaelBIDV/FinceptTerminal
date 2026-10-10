#!/usr/bin/env python3
"""Unit tests cho chaebol_map_data_codong2 (+ _ydo), P1 data_owner của codong v2 (spec codong_v2_spec.md §4, §11.1).

Ba lớp: (1) kho giả trong thư mục tạm (CHB_SYSTEM_DIR) với số tính tay cho mọi luật làm sạch / ghép cặp / alias / bậc;
(2) kho thật CHỈ ĐỌC (skip nếu vắng), ghim dữ kiện lịch sử F1, F6, F7, F9, F10, F13, F14, F15, F20 của spec §1;
(3) kiểm tĩnh mã nguồn. Mạng bị chặn.
Chạy:  python3.14 -m pytest -q test_chaebol_map_data_codong2.py
       "$HOME/Library/Application Support/com.fincept.terminal/venv-numpy2/bin/python" -m pytest -q test_chaebol_map_data_codong2.py
"""
from __future__ import annotations

import ast
import json
import os
import re
import socket
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import chaebol_map_data_nen as N  # noqa: E402
import chaebol_map_data_codong2 as O  # noqa: E402

REAL_SYS = Path.home() / "SECOND BRAIN-OBSIDIAN" / "_System"
REAL_B = REAL_SYS / "fincept_bridge"
HAS_REAL = (REAL_B / "state/vc_lk/VIC/price-history.json").exists() and \
    (REAL_B / "data/chaebol_map/v21_const.json").exists()
TODAY = "2026-10-05"
ENV_KEYS = ("CHB_SYSTEM_DIR", "CHB_TODAY", "CHB_SPEC_DIR")
_REAL_SOCK = {}
DONE, REG, NOT = "Đã thực hiện xong", "Đăng ký", "Không thực hiện được"
LABEL_RE = re.compile(r"\b(BULL|BEAR|BUY|SELL|TRIM|DCA|MUA|BÁN|tích luỹ|tích lũy|phân phối)\b")


def setUpModule():
    def blocked(*a, **k):
        raise RuntimeError("mạng bị chặn trong test chaebol_map_data_codong2")
    for name in ("socket", "create_connection", "getaddrinfo"):
        _REAL_SOCK[name] = getattr(socket, name)
        setattr(socket, name, blocked)


def tearDownModule():
    for name, fn in _REAL_SOCK.items():
        setattr(socket, name, fn)


def wj(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def keys_deep(o):
    """Mọi khoá dict (đệ quy; V là lá)."""
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from keys_deep(v)
    elif isinstance(o, (list, tuple)):
        for v in o:
            yield from keys_deep(v)


def ins(i, code, act, st, end, *, pid=None, name=None, org=None, rel=None, reg=0, acq=0, bef=None, aft=None,
        own=None, start=None, pub=None):
    return {"id": i, "eventCode": code, "actionTypeCode": act, "tradeStatusVi": st, "traderPersonId": pid,
            "traderNameVi": name, "traderOrganNameVi": org, "relativeNameVi": rel, "publicDate": pub or end,
            "startDate": start or end, "endDate": end, "shareRegister": reg, "shareAcquire": acq,
            "shareBeforeTrade": bef, "shareAfterTrade": aft, "ownershipAfterTrade": own, "eventTitleVi": f"tiêu đề {i}",
            "sourceUrlVi": ""}


A, B_, C_, E_ = "Nguyễn Văn A", "Trần Thị B", "Hoàng Văn C", "Phạm Thị E"
INSIDER = [
    ins("r01", "DDIND", "B", DONE, "2009-05-05", pid=14, name="Lê Văn D", acq=1000, bef=0, aft=1000, own=0.000001),
    ins("r02", "DDIND", "B", DONE, "2024-06-03", start="2024-06-01", pid=11, name=A, reg=20_000_000, acq=10_000_000,
        bef=290_000_000, aft=300_000_000, own=0.30),
    ins("r03", "DDIND", "S", DONE, "2025-06-10", start="2025-06-01", pid=11, name=A, acq=-100_000_000,
        bef=300_000_000, aft=200_000_000, own=0.20),
    ins("r04", "DDINS", "B", DONE, "2025-06-05", org="Công ty Cổ phần Alpha Holding", acq=100_000_000, bef=0,
        aft=100_000_000, own=0.10),
    ins("r05", "DDIND", "B", DONE, "2025-07-20", pid=15, name=E_, acq=1_000_000, bef=0, aft=1_000_000, own=0.001),
    ins("r06", "DDRP", "S", DONE, "2025-03-01", pid=12, name=B_, rel=A, acq=-150_000_000, bef=160_000_000,
        aft=10_000_000, own=0.01),
    ins("r07", "DDRP", "B", DONE, "2025-03-01", pid=13, name=C_, rel=A, acq=150_000_000, bef=0, aft=150_000_000,
        own=0.15),
    ins("r08", "DDRP", "B", DONE, "2024-01-10", pid=12, name=B_, rel=A, acq=160_000_000, bef=0, aft=160_000_000,
        own=0.16),
    ins("r09", "DDIND", "S", REG, "2026-10-30", start="2026-10-01", pub="2026-09-28", pid=11, name=A, reg=1_000_000,
        bef=200_000_000, aft=0, own=0.0),
    ins("r10", "DDIND", "B", REG, "2024-01-01", start="2023-12-25", pub="2023-12-20", pid=15, name=E_, reg=2_000_000,
        bef=0, aft=0, own=0.0),
    ins("r11", "DDINS", "S", DONE, "2011-11-18", org="BankInvest Private Equity New Markets II K/S", acq=0,
        bef=10_000_000, aft=20_000_000, own=0.02),
    ins("r12", "DDINS", "S", DONE, "2016-01-15", org="Private Equity New Market II K/S", acq=-3_000_000,
        bef=43_000_000, aft=40_000_000, own=0.0576),
    ins("r13", "DDIND", "B", DONE, "2020-02-02", pid=16, name="Đỗ Văn F", acq=50, bef=100, aft=60, own=0.0000006),
    ins("r14", "DDIND", "S", DONE, "2022-03-03", pid=17, name="Vũ Thị G", acq=-1000, bef=5000, aft=4000, own=None),
    ins("r15", "DDIND", "B", NOT, "2021-05-05", pid=16, name="Đỗ Văn F", reg=1000, acq=0, bef=100, aft=100),
    ins("r16", "DDINS", "S", DONE, "2014-12-23", org="Công ty Cổ phần Tập đoàn Beta", acq=-7_500_000,
        bef=257_500_000, aft=250_000_000, own=0.25),
    ins("r17", "DDINS", "B", DONE, "2016-12-05", org="Công ty Cổ Phần Beta", acq=2_000_000, bef=250_000_000,
        aft=252_000_000, own=0.252),
    ins("r18", "DDIND", "TN", DONE, "2019-07-07", pid=16, name="Đỗ Văn F", acq=10, bef=100, aft=110, own=0.00001),
]
PH = [("2009-05-04", 100, 50, None), ("2010-12-20", 100, 50, None), ("2010-12-21", 100, 50, 1e9),
      ("2024-06-03", 100, 50, 1e9), ("2025-06-10", 100, 50, 1e9), ("2025-12-04", 100, 50, 1e9),
      ("2025-12-05", 50, 50, 2e9), ("2026-10-02", 50, 50, 2e9)]
HOLDERS = [
    {"ownerCode": "ALPHA", "ownerName": "Công ty Cổ phần Alpha Holding", "ownerType": "CORPORATE", "quantity": 100_000_000,
     "percentage": 0.05, "publicDate": "2026-09-28"},
    {"ownerCode": "NVA", "ownerName": A, "ownerType": "INDIVIDUAL", "quantity": 400_000_000, "percentage": 0.20,
     "publicDate": "2026-06-30"},
    {"ownerCode": "OLD1", "ownerName": "Old Fund Ltd", "ownerType": "CORPORATE", "quantity": 50_000_000,
     "percentage": 0.10, "publicDate": "2024-01-01"},
    {"ownerCode": "DUP1", "ownerName": "Công ty Cổ phần Alpha Holding", "ownerType": "CORPORATE", "quantity": 10_000_000,
     "percentage": 0.01, "publicDate": "2025-01-01"},
    {"ownerCode": "TTB", "ownerName": B_, "ownerType": "INDIVIDUAL", "quantity": 2_000_000, "percentage": 0.001,
     "publicDate": "2026-04-15"},
]


def ev2(code, title, *, ex=None, issue=None, listing=None, ratio=0, vps=None, pub="2020-01-01"):
    return {"eventCode": code, "eventTitleVi": title, "publicDate": pub, "exrightDate": ex, "issueDate": issue,
            "listingDate": listing, "recordDate": None, "payoutDate": None, "exerciseRatio": ratio, "valuePerShare": vps}


EVENTS_V2 = [
    ev2("ISS", "Phát hành cổ phiếu - Phát hành riêng lẻ", issue="2026-07-10"),
    ev2("ISS", "Phát hành cổ phiếu - Cổ phiếu thưởng tỉ lệ 100.0%", ex="2025-12-05", ratio=1.0),
    ev2("ISS", "Phát hành cổ phiếu - Phát hành cho CBCNV", issue="2025-03-01"),
    ev2("ISS", "Phát hành cổ phiếu - Quyền mua CP cho Cổ đông hiện hữu tỉ lệ 20.2%", ex="2019-05-05", ratio=0.202),
    ev2("ISS", "Phát hành cổ phiếu - Chuyển từ trái phiếu chuyển đổi", issue="2024-12-01"),
    ev2("ISS", "Phát hành cổ phiếu - Phát hành để sáp nhập", issue="2026-01-02"),
    ev2("ISS", "Phát hành cổ phiếu - Loại lạ", issue="2026-02-02"),
    ev2("DIV", "Trả cổ tức bằng tiền", ex="2026-06-01", vps=500),
    ev2("AIS", "Niêm yết bổ sung", listing="2026-08-01"),
]
EVENTS_ALL = [
    {"eventCode": "AGME", "eventTitleVi": "TST - ĐHĐCĐ 2026", "displayDate1": "2026-04-22", "recordDate": "2026-03-23"},
    {"eventCode": "AGME", "eventTitleVi": "TST - ĐHĐCĐ 2027", "displayDate1": "2027-04-20", "recordDate": None},
    {"eventCode": "EGME", "eventTitleVi": "TST - ĐHĐCĐ bất thường", "displayDate1": "2025-08-01"},
    {"eventCode": "MOVE", "eventTitleVi": "Chuyển sàn", "displayDate1": "2015-01-01"},
    {"eventCode": "DDINS", "eventTitleVi": "bỏ qua", "displayDate1": "2025-01-01"},
]
CODONG = {"trang_thai": "ok", "nguon_moc": "fft_codong.json (giả)", "moc": [
    {"ky": "2018-01", "v": 900, "kieu": "quan_sat", "b": "SS-T3"}, {"ky": "2018-06", "v": 950, "kieu": "quan_sat", "b": "SS-T3"},
    {"ky": "2024-01", "v": 1000, "kieu": "quan_sat", "b": "SS-T3"}, {"ky": "2024-06", "v": 1200, "kieu": "noi_suy", "b": "EST"},
    {"ky": "2024-12", "v": 1500, "kieu": "quan_sat", "b": "SS-T3"}, {"ky": "2025-03", "v": 1505, "kieu": "quan_sat", "b": "SS-T3"},
    {"ky": "2025-06", "v": 1505, "kieu": "chep", "cf": True, "b": "EST"}, {"ky": "2025-12", "v": 2000, "kieu": "so_tron", "b": "EST"}],
    "cap": [{"tu": t, "den": d, "trang_thai": "ok", "nhan_k": "tay_to", "d_pct": {"v": x, "u": "%", "t": d + "-28", "b": "SS-T3"},
             "k": {"v": 1000, "u": "cp", "t": d + "-28", "b": "EST"}}
            for t, d, x in (("2018-01", "2018-06", 5.56), ("2024-01", "2024-12", 50.0), ("2024-12", "2025-03", 0.33),
                            ("2025-03", "2025-06", 0.0))]}
SIGMA_OK = {"chi_so": "pb", "dung_duoc": True, "x": {"v": 1.5, "u": "x", "t": "2026-10-02", "b": "FACT-T2", "n": "vc_lk/TST/ratio-daily.pb"},
            "mu": {"v": 2.0, "u": "x", "t": "2026-10-02", "b": "EST"}, "sd": {"v": 1.0, "u": "x", "t": "2026-10-02", "b": "EST"},
            "z": {"v": -0.5, "u": "sigma", "t": "2026-10-02", "b": "EST"}}


def build_store(root: Path) -> None:
    b, vcd = root / "fincept_bridge", root / "fincept_bridge" / "state" / "vc_lk"

    def vcf(tk, ep, du, **meta):
        wj(vcd / tk / f"{ep}.json", {"meta": {"lay_luc": "2026-10-05T15:00:00+07:00", "du_lieu_toi": "2026-10-02", **meta},
                                     "du_lieu": du})
    vcf("TST", "price-history", {"cot": ["tradingDate", "closePrice", "closePriceAdjusted", "totalShares"],
                                 "hang": [list(r) for r in PH]})
    vcf("TS2", "price-history", {"cot": ["tradingDate", "closePrice", "closePriceAdjusted", "totalShares"],
                                 "hang": [list(r) for r in PH]})
    vcf("TST", "insider-transaction", INSIDER, du_lieu_toi="2026-09-28")
    vcf("TST", "shareholder", HOLDERS, du_lieu_toi="2026-09-28")
    vcf("TST", "shareholder-structure", {"statePercentage": 0.1, "foreignPercentage": 0.2, "otherPercentage": 0.7,
                                         "bodPercentage": 0.3, "institutionPercentage": 0.6, "totalShares": 2e9},
        du_lieu_toi=None)
    vcf("TST", "details", {"freeFloatPercentage": 0.4, "maximumForeignPercentage": 0.49}, du_lieu_toi=None)
    vcf("TST", "relationship", {"subsidiaries": [
        {"rightOrganNameVi": "Sub A", "rightTicker": "SUBA", "ownedPercentage": 0.6},
        {"rightOrganNameVi": "Sub B", "rightTicker": "", "ownedPercentage": 0.9},
        {"rightOrganNameVi": "Zero Co", "rightTicker": "ZZZ", "ownedPercentage": 0.0}],
        "affiliates": [{"rightOrganNameVi": "Aff C", "rightTicker": "AFFC", "ownedPercentage": 0.3}]}, t_lay="2026-10-05")
    vcf("TST", "events-v2", EVENTS_V2)
    vcf("TST", "events-all", EVENTS_ALL)
    ls = b / "state" / "vc_lk_lichsu"
    wj(ls / "TST/shareholder/2026-09-01.json", {"meta": {}, "du_lieu": [
        {"ownerCode": "Q", "ownerName": "Q Co", "quantity": 100}, {"ownerCode": "R", "ownerName": "R Co", "quantity": 200}]})
    wj(ls / "TST/shareholder/2026-10-05.json", {"meta": {}, "du_lieu": [
        {"ownerCode": "Q", "ownerName": "Q Co", "quantity": 150}, {"ownerCode": "R", "ownerName": "R Co", "quantity": 200},
        {"ownerCode": "S", "ownerName": "S Co", "quantity": 70}]})
    wj(ls / "TS2/shareholder/2026-10-05.json", {"meta": {}, "du_lieu": []})
    lk = b / "data" / "lk_hoso"
    wj(lk / "_index.json", {"toan_vu": ["TST", "TS2"]})
    wj(lk / "TST.json", {"cong": {"dong": "CỔNG: [tiền rẻ] · chủ thể cần thị trường · playbook X", "dung": False,
                                  "as_of": "2026-10-05T08:00:00"}, "sigma": SIGMA_OK, "codong": CODONG})
    wj(lk / "TS2.json", {"cong": {"dong": "CỔNG: thị trường DỪNG", "dung": False, "as_of": "2026-10-05 08:00"},
                         "sigma": {"chi_so": "pe", "dung_duoc": False, "g": "thiếu EPS"}, "codong": {"trang_thai": "CAN_DATA"}})
    wj(b / "data" / "fft_langkinh.json", {"ma": {
        "TST": {"chu_the": {"nhan": "cần", "bac": "EST", "ngay": "2026-09-10", "xung_dot": True, "playbook": None,
                            "khang_dinh": [{"nguon": "q2", "ref": "M:1", "nhan": "cần", "nguyen_van": "nguyên văn", "bac": "SS-T3"}]},
                "cau_chuyen": {"vung_gia_gom": {"vwap": 10, "lo": 9, "hi": 11, "bac": "EST"}}},
        "TS2": {"chu_the": {"nhan": None, "bac": None}}}})
    wj(b / "fft_cauchuyen.json", {"cap_nhat": "2026-09-22", "ma": {"TST": {
        "tieu_de": "Tiêu đề có phán đoán", "dong_co": {"text": "động cơ", "bac": "SS-T3", "nguon": "a.md"},
        "diem_gay": {"text": "điểm gãy", "bac": "UNVERIFIED", "nguon": ["b.md", "c.md"]},
        "buc_tranh": {"text": "thiếu bậc", "nguon": "d"},
        "thau_tom": {"text": "thâu tóm nội nhóm", "bac": "FACT-T1", "nguon": ["bcqt.pdf"]},
        "muc_dich_keo": {"text": "mục đích", "bac": "EST", "nguon": "e"},
        "cau_hoi_mo_chi_tiet": [{"text": "q1", "bac": "EST", "nguon": "f"}, {"text": "q2", "bac": "EST"}],
        "su_kien": [{"id": "E1", "ngay": "2025-01-01", "loai": "khac", "chu_the": "X", "mo_ta": "mô tả", "bac": "SS-T3",
                     "nguon": "g", "cua_so": {"tu": "2025-01-01", "den": "2025-12-31"}}, {"id": "E2", "mo_ta": "không bậc"}],
        "cau_hoi_mo": ["chuỗi không bậc"]}}})
    wj(root / "fund_holdings" / "aggregate.json", {"as_of": "2026-09-23", "tickers": {"TST": {
        "shares_held": 3000, "pct_outstanding": 0.0000015, "num_funds": 4,
        "net_change": {k: {"shares": s, "value_bn": 1.0} for k, s in
                       (("m1", 10), ("m3", 20), ("m6", 30), ("ytd", 40), ("y1", -5))}}}})
    wj(root / "smart_money/history/2025-11/aggregate.json", {"as_of": "2025-11-30", "tickers": {
        "TST": {"shares_held": 1000, "num_funds": 3}}})
    wj(root / "smart_money/history/2026-09/aggregate.json", {"as_of": "2026-09-23", "tickers": {
        "TST": {"shares_held": 3000, "num_funds": 4}}})
    wj(root / "early_detection/owner_intent.json", {"by_ticker": {"TST": {"events": [
        {"date": "2025-05-14", "date_approx": True, "title": "t1", "verified": True, "auto": False, "score": 9},
        {"date": "2025-12-31", "title": "tự động", "verified": True, "auto": True},
        {"date": "2024-01-01", "title": "t3", "verified": False, "auto": False}]}}})
    wj(root / "openclaw_hdcv/data/nq68_nq79.json", {"_meta": {"as_of": "2026-05-23"}, "tier_a": {"TST": {
        "nq": "NQ68", "chaebol": "C", "founder": "F", "score": 63, "phase": 2.5, "verdict_v1": "ALPHA", "kelly": [1, 2]}}})


class _EnvCase(unittest.TestCase):
    sysdir: str | None = None

    @classmethod
    def setUpClass(cls):
        cls._old = {k: os.environ.get(k) for k in ENV_KEYS}
        os.environ["CHB_TODAY"] = TODAY
        os.environ.pop("CHB_SPEC_DIR", None)
        if cls.sysdir:
            os.environ["CHB_SYSTEM_DIR"] = cls.sysdir
        else:
            os.environ.pop("CHB_SYSTEM_DIR", None)
        N.clear_cache()

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        N.clear_cache()


class Fixture(_EnvCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        build_store(Path(cls.tmp.name))
        cls.sysdir = cls.tmp.name
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.tmp.cleanup()

    def rows(self):
        return {r["id"]: r for r in O.insider_rows("TST", TODAY)["rows"]}

    # ── 4.2 ──
    def test_cong_line_verbatim_and_stop(self):
        c = O.cong_line("TST")
        self.assertEqual(c["text"], "CỔNG: [tiền rẻ] · chủ thể cần thị trường · playbook X")
        self.assertEqual((c["as_of"], c["src"], c["stop"]), ("2026-10-05 08:00", "lk_hoso/TST.json#cong.dong", False))
        self.assertTrue(O.cong_line("TS2")["stop"])
        self.assertEqual(O.cong_line("TS3"), {"text": "CỔNG: [CẦN DATA]", "as_of": None, "src": None, "stop": True})

    def test_chu_the_label_tier_from_bac(self):
        c = O.chu_the_label("TST")
        self.assertEqual((c["nhan"].value, c["nhan"].tier, c["nhan"].asof), ("cần", N.EST, "2026-09-10"))
        self.assertTrue(c["xung_dot"])
        self.assertEqual(c["khang_dinh"], [{"nguon": "q2", "nhan": "cần", "nguyen_van": "nguyên văn", "bac": "SS-T3"}])
        self.assertTrue(O.chu_the_label("TS2")["nhan"].can)
        self.assertEqual(O.chu_the_label("TS2")["nhan"].note, "fft_langkinh chưa có nhãn chủ thể cho mã này")

    def test_sigma_label_from_chi_so(self):
        s = O.sigma_view("TST")
        self.assertTrue(s["ok"])
        self.assertEqual((s["chi_so"], s["label"], s["z"].value, s["z"].tier, s["x"].tier), ("pb", "P/B", -0.5, N.EST, N.T2))
        self.assertEqual(O.sigma_view("TS2")["why"], "thiếu EPS")
        self.assertEqual(O.sigma_view("TS3")["why"], "chưa có lk_hoso")

    # ── 4.3 ──
    def test_norm_name_rules_and_idempotent(self):
        cases = {"Công ty Cổ phần Tập đoàn Masan": "ctcp tập đoàn masan",
                 "Công ty TNHH Một Thành Viên Xây Dựng Hoa Hướng Dương": "cty tnhh mtv xây dựng hoa hướng dương",
                 "Công ty TNHH  Bảo hiểm": "cty tnhh bảo hiểm", "Sk Investment Vina I Pte. Ltd.": "sk investment vina i pte ltd",
                 "ABC Joint Stock Company": "abc jsc", "Orchid Limited": "orchid ltd", "Công Ty X, Y; Z": "cty x y z"}
        for raw, want in cases.items():
            self.assertEqual(O.norm_name(raw), want)
            self.assertEqual(O.norm_name(want), want)
        self.assertEqual(O.norm_name("Nguyễn"), O.norm_name("Nguyễn"))   # NFD → NFC

    def test_owner_keys_and_aliases(self):
        r = self.rows()
        self.assertEqual(r["r02"]["owner"]["key"], "p:11")
        self.assertEqual(r["r11"]["owner"]["key"], r["r12"]["owner"]["key"])
        self.assertEqual(r["r12"]["owner"]["alias"]["rule"], "global")
        self.assertEqual(O.chain_aliases("TST"), {"ctcp beta": "ctcp tập đoàn beta"})
        self.assertEqual(r["r17"]["owner"]["key"], "o:ctcp tập đoàn beta")
        self.assertEqual((r["r17"]["owner"]["alias"]["rule"], r["r17"]["owner"]["alias"]["tier"]), ("chain", N.EST))
        self.assertEqual(r["r06"]["related"]["key"], "p:11")             # relativeNameVi → personId qua chỉ mục tên

    def test_group_map_ddrp_rule(self):
        g = O.group_map("TST")
        self.assertEqual(g["p:12"]["group"], "Người liên quan của Nguyễn Văn A")
        self.assertEqual((g["p:13"]["rule"], g["p:13"]["tier"]), ("ddrp", N.T2))
        self.assertNotIn("p:11", g)

    # ── 4.4 ──
    def test_insider_rows_cleaning(self):
        ir = O.insider_rows("TST", TODAY)
        r = self.rows()
        self.assertEqual((ir["n_raw"], ir["n_done"], ir["n_reg"], ir["n_not"], ir["ts_start"]), (18, 15, 2, 1, "2010-12-21"))
        self.assertEqual((r["r09"]["before"], r["r09"]["after"], r["r09"]["own_after"]), (None, None, None))
        self.assertEqual(r["r09"]["flags"], ["dem_dang_ky"])
        self.assertEqual(r["r10"]["flags"], ["dem_dang_ky", "qua_han"])
        self.assertEqual((r["r11"]["valid"], r["r11"]["flags"]), (False, ["acq_0", "mau_thuan"]))
        self.assertEqual((r["r13"]["valid"], r["r13"]["flags"]), (False, ["mau_thuan"]))
        self.assertEqual((r["r14"]["valid"], r["r14"]["flags"], r["r14"]["own_after"]), (True, ["own_khong_dung"], None))
        self.assertEqual(ir["n_bad"], 2)
        self.assertEqual((r["r15"]["status"], r["r15"]["valid"]), ("khong_thuc_hien", True))
        self.assertEqual((r["r18"]["side"], r["r02"]["side"], r["r03"]["side"]), (0, 1, -1))
        self.assertEqual((r["r01"]["acq_tier"], r["r02"]["acq_tier"]), (N.UNV, N.EST))
        self.assertEqual(r["r03"]["acq_now"], 200_000_000)                 # trước GDKHQ 1:1 ngày 05/12/2025 → ×2
        self.assertEqual(r["r03"]["own_after"], 20.0)
        self.assertEqual(r["r03"]["date"], "2025-06-10")

    def test_pair_transfers(self):
        pt = O.pair_transfers("TST", TODAY)
        self.assertEqual([(p["id"], p["kind"], p["qty"], p["rows"]) for p in pt["pairs"]],
                         [("P1", "noi_nhom", 150_000_000, ["r06", "r07"]), ("P2", "cap_khop", 100_000_000, ["r03", "r04"])])
        p2 = pt["pairs"][1]
        self.assertEqual((p2["date0"], p2["date1"], p2["from"]["key"], p2["to"]["key"]),
                         ("2025-06-05", "2025-06-10", "p:11", "o:ctcp alpha holding"))
        self.assertEqual((p2["qty_now"].value, p2["qty_now"].tier, round(p2["pct"].value, 9), p2["pct"].tier),
                         (200_000_000, N.EST, 10.0, N.EST))
        self.assertEqual(pt["evidence"], [{"text": "thâu tóm nội nhóm", "tier": N.T1, "src": "bcqt.pdf"}])
        r = self.rows()
        self.assertEqual(r["r03"]["pair"], {"id": "P2", "kind": "cap_khop", "other": "r04"})
        self.assertIsNone(r["r05"]["pair"])                                # cùng KL nhưng cửa sổ ngày không giao

    def test_ownership_ladder(self):
        lad = O.ownership_ladder("TST", TODAY)
        self.assertEqual([(o["key"], round(o["span"], 6)) for o in lad["owners"]],
                         [("p:12", 15.0), ("p:11", 10.0), ("o:ctcp tập đoàn beta", 0.2)])
        a = lad["owners"][1]
        self.assertEqual([p["pct"] for p in a["points"]], [30.0, 20.0])
        self.assertEqual(a["points"][0]["after_now"], 600_000_000)
        self.assertEqual((a["pct_first"].tier, a["pct_last"].value), (N.T2, 20.0))
        self.assertNotIn("r09", [p["row"] for o in lad["owners"] for p in o["points"]])
        g = lad["groups"][0]
        self.assertEqual((g["group"], g["members"], [x["pct_sum"] for x in g["points"]]),
                         ("Người liên quan của Nguyễn Văn A", ["p:12", "p:13"], [16.0, 16.0]))
        self.assertEqual(g["pct_last"].tier, N.EST)

    def test_insider_net_excludes_pairs(self):
        n = O.insider_net("TST", "2025-01-01", "2025-12-31", TODAY, by="group")
        self.assertEqual((n["n_rows"], n["n_pairs_excluded"], n["net_now"].value, n["net_now"].tier), (1, 2, 2_000_000, N.EST))
        self.assertAlmostEqual(n["net_pct"].value, 0.1)
        keys = [t["key"] for t in n["top"]]
        self.assertNotIn("p:12", keys)
        self.assertEqual(keys[:2], ["o:ctcp alpha holding", "p:11"])
        self.assertEqual((n["top"][1]["pct_before"].tier, n["top"][0]["pct_before"].tier), (N.T2, N.EST))
        no = O.insider_net("TST", "2025-01-01", "2025-12-31", TODAY, by="owner")
        b = next(t for t in no["top"] if t["key"] == "p:12")
        self.assertEqual((b["pct_before"].value, b["pct_after"].value), (16.0, 1.0))
        self.assertLess(b["d_pct"].value, 0)
        self.assertEqual(b["cp_now"].value, 0)                             # chuyển giao không vào ròng
        self.assertEqual(O.insider_net("TS3", "2025-01-01", "2025-12-31", TODAY)["why"], "chưa nạp vc_lk")
        with self.assertRaises(ValueError):
            O.insider_net("TST", "2025-01-01", "2025-12-31", TODAY, by="x")

    def test_net_top_asof_stale_and_all_members(self):
        """% trước/sau mang ngày CHÍNH dòng vendor; mốc trước cửa sổ cũ hơn 12 tháng → % trước [CẦN DATA], Δ từ cp ÷ số
        cp hiện hành; tổng nhóm gồm cả thành viên không giao dịch trong cửa sổ (% lần cuối biết)."""
        def row(i, key, grp, d, side, acq, own, pair=None):
            return {"id": i, "owner": {"key": key, "name": key}, "group": grp, "date": d, "side": side, "acquire": acq,
                    "after": None, "own_after": own, "acq_now": abs(acq) * 2.0, "pair": pair}
        rows = [row("a", "o:x", "G", "2020-01-01", 1, 100, 30.0),                 # thành viên im lặng: 30%
                row("b", "o:y", "G", "2024-03-01", 1, 50, 10.0),                  # mốc cũ (> 12T trước d0)
                row("c", "o:y", "G", "2026-03-01", 1, 50, 9.0),                   # mua thêm nhưng % giảm (pha loãng)
                row("d", "o:z", None, "2025-08-01", 1, 10, 5.0),
                row("e", "o:z", None, "2026-02-01", -1, 20, 4.0)]
        so = N.V(1000.0, "1,000", N.T2, "2026-10-05", "so", None, "cp")
        top = O._net_top(rows, "2025-10-05", "2026-10-05", "group", None, so)
        g = next(t for t in top if t["key"] == "G")
        self.assertEqual((g["n_mem"], g["pct_after"].value, g["pct_after"].asof, g["pct_after"].tier), (2, 39.0, "2026-03-01",
                                                                                                         N.EST))
        self.assertTrue(g["pct_before"].can)
        self.assertIn("01/03/2024", g["pct_before"].note)
        self.assertAlmostEqual(g["d_pct"].value, 50 * 2.0 / 1000 * 100)           # Δ của y từ cp, x đóng góp 0
        self.assertIn("cp giao dịch", g["d_pct"].note)
        z = next(t for t in top if t["key"] == "o:z")
        self.assertEqual((z["pct_before"].value, z["pct_before"].asof, z["pct_before"].tier), (5.0, "2025-08-01", N.T2))
        self.assertEqual((z["pct_after"].value, z["pct_after"].asof, z["d_pct"].value), (4.0, "2026-02-01", -1.0))
        self.assertEqual((z["cp_now"].value, z["cp_now"].asof), (-40.0, "2026-02-01"))
        self.assertNotIn("2025-10-05", [t["pct_before"].asof for t in top])       # không gắn ngày mép cửa sổ

    def test_insider_yearly_exec_and_windows(self):
        y = O.insider_yearly("TST", TODAY)
        ys = {r["year"]: r for r in y["years"]}
        self.assertEqual([r["year"] for r in y["years"]], list(range(2009, 2027)))
        self.assertEqual((ys[2024]["exec_ratio"].value, ys[2024]["exec_ratio"].tier), (50.0, N.EST))
        self.assertTrue(ys[2025]["exec_ratio"].can)
        self.assertEqual((ys[2025]["n_buy"], ys[2025]["n_sell"], ys[2025]["n_transfer"]), (1, 0, 4))
        self.assertEqual((ys[2024]["n_overdue"], ys[2021]["n_not_done"], ys[2024]["n_reg"]), (1, 1, 1))
        self.assertEqual([r["id"] for r in y["open"]], ["r09"])
        self.assertEqual([r["id"] for r in y["overdue"]], ["r10"])
        self.assertEqual(len(O.insider_yearly("TST", TODAY, recent=5)["recent"]), 5)
        e = O.exec_stats("TST", TODAY)
        self.assertEqual((e["exec_ratio"].value, e["n_done_reg"], e["n_open"].value, e["n_not_done"].value), (50.0, 1, 1, 0))
        self.assertEqual((e["n_overdue"].value, e["n_overdue"].tier), (1, N.UNV))
        self.assertIn("quá hạn chưa có kết quả", e["n_overdue"].note)
        self.assertEqual(sorted(w["row"] for w in O.insider_windows("TST", TODAY)), ["r02", "r05", "r08"])

    def test_anchor_dates(self):
        a = {x["id"]: x for x in O.anchor_dates("TST", TODAY)}
        self.assertNotIn("ddins_max_24t", a)                               # DDINS duy nhất trong 24T là chuyển giao
        self.assertEqual((a["ph_thu_tien"]["date"], a["dhcd"]["date"]), ("2026-07-10", "2026-04-22"))

    # ── 4.5 ──
    def test_holder_table_fresh_only(self):
        h = O.holder_table("TST", TODAY)
        self.assertEqual((h["n"], h["n_fresh"], h["n_old"], h["n_dup"]), (5, 3, 2, 2))
        self.assertEqual((h["period"], h["fresh_from"]), ("2026-09-28", "2026-03-29"))
        rows = {r["code"]: r for r in h["rows"]}
        self.assertEqual([r["code"] for r in h["rows"]], ["NVA", "OLD1", "ALPHA", "DUP1", "TTB"])
        self.assertIsNone(rows["OLD1"]["qty_now"])
        self.assertEqual(rows["NVA"]["qty_now"].value, 400_000_000)
        self.assertTrue(rows["OLD1"]["old12"] and not rows["NVA"]["old12"])
        self.assertEqual(rows["TTB"]["group"], "Người liên quan của Nguyễn Văn A")
        c = {k: round(v.value, 6) for k, v in h["conc"].items()}
        self.assertEqual(c, {"top1": 20.0, "top3": 25.1, "top5": 25.1, "hhi": 425.01, "pct_person": 20.1, "pct_org": 5.0})
        self.assertTrue(all(v.tier == N.EST for v in h["conc"].values()))
        self.assertEqual((rows["NVA"]["pct"].tier, rows["NVA"]["pct"].asof), (N.T2, "2026-06-30"))

    def test_holder_delta(self):
        d = O.holder_delta("TST")
        self.assertEqual((d["d0"], d["d1"]), ("2026-09-01", "2026-10-05"))
        self.assertEqual([(r["code"], r["d_qty"].value) for r in d["rows"]], [("Q", 50), ("S", None)])
        self.assertEqual(d["rows"][0]["d_qty"].tier, N.EST)
        self.assertEqual(O.holder_delta("TS2")["why"], "mới có 1 ảnh chụp vc_lk_lichsu (05/10/2026); Δ cần ≥2")
        self.assertEqual(O.holder_delta("TS3")["why"], "mới có 0 ảnh chụp vc_lk_lichsu; Δ cần ≥2")

    def test_structure_bars(self):
        s = O.structure_bars("TST")
        self.assertAlmostEqual(s["sum1"], 100.0)
        self.assertEqual([b["k"] for b in s["bar1"]], ["state", "foreign", "other"])
        self.assertEqual([round(b["pct"].value, 6) for b in s["bar2"]], [30.0, 60.0])
        self.assertTrue(all(b["pct"].asof is None and b["pct"].tier == N.T2 for b in s["bar1"] + s["bar2"]))
        self.assertEqual(s["data_date"]["tier"], N.UNV)
        self.assertEqual((round(s["free_float"].value, 6), round(s["fol"].value, 6), s["total_shares"].value), (40.0, 49.0, 2e9))

    def test_relationship_view(self):
        r = O.relationship_view("TST")
        self.assertEqual([x["ticker"] for x in r["listed"]], ["SUBA", "AFFC"])
        self.assertEqual([x["name"] for x in r["top"]], ["Sub B", "Sub A", "Aff C"])
        self.assertEqual((r["n_sub"], r["n_aff"]), (2, 1))
        self.assertIn("UNVERIFIED", r["time_note"])
        self.assertEqual(O.relationship_view("TS2")["why"], "vc_lk chưa có relationship cho mã này")
        self.assertEqual(O.relationship_view("TS3")["why"], "chưa nạp vc_lk")

    def test_fund_view(self):
        f = O.fund_view("TST")
        self.assertEqual((f["held"].value, round(f["pct_out"].value, 8), f["n_funds"].value), (3000, 0.00015, 4))
        self.assertEqual((f["hist"]["factor"], f["hist"]["n_funds0"], f["hist"]["n_funds1"]), (2.0, 3, 4))
        d = f["hist"]["delta_now"]                  # tập quỹ đổi 3→4: hiệu hai ảnh không phải giao dịch
        self.assertTrue(d.can)
        self.assertIn("tập quỹ đổi 3→4, hiệu hai ảnh không phải giao dịch", d.note)
        self.assertEqual(f["net"]["m3"].tier, N.T2)
        self.assertIn("05/12/2025", f["net"]["y1"].note)
        self.assertIsNone(f["net"]["m1"].note)
        self.assertNotIn("value_bn", set(keys_deep(f)))
        self.assertFalse(O.fund_view("TS3")["ok"])

    # ── 4.6 ──
    def test_codong_full(self):
        c = O.codong_full("TST")
        self.assertEqual((c["n_moc"], c["n_qs"], c["thin"], len(c["cap"])), (8, 5, False, 4))
        self.assertEqual([x["usable"] for x in c["cap"]], [True, True, True, False])
        self.assertEqual({m["kieu"]: m["tier"] for m in c["moc"]}["noi_suy"], N.EST)
        self.assertEqual((c["cap"][1]["d_pct"].tier, c["cap"][1]["k"].tier), (N.T3, N.EST))
        self.assertEqual(c["moc"][0]["end"], "2018-01-31")
        self.assertEqual((c["hierarchy"], c["esop_note"]), (O.HIERARCHY_TEXT, O.ESOP_NOTE))
        for tk in ("TS2", "TS3"):
            self.assertEqual(O.codong_full(tk)["why"], O.WHY_NO_TV if tk == "TS2" else O.WHY_NO_TV)

    def test_codong_delta_never_uses_cf_or_round(self):
        v = O.codong_delta("TST", "2024-01-01", "2024-12-31")
        self.assertEqual((round(v.value, 6), v.tier), (50.0, N.T3))
        v = O.codong_delta("TST", "2024-05-01", "2024-12-31")
        self.assertEqual((round(v.value, 6), v.tier, v.note), (25.0, N.EST, "có mốc nội suy"))
        v = O.codong_delta("TST", "2025-05-01", "2025-12-31")
        self.assertEqual((v.can, v.note), (True, "không đủ 2 mốc trong đoạn"))

    def test_match_flip(self):
        calls = []

        def flow(sign):
            def f(a, b):
                calls.append((a, b))
                return {"du_val": N.V(sign * 1e9, "x", N.EST), "d_fo_pp": N.V(0.1, "0.1", N.T2), "nn_vol": N.V(1, "1", N.EST)}
            return f
        m = O.match_flip("TST", flow(1))
        self.assertEqual([(r["tu"], r["ket"]) for r in m["rows"]], [("2018-01", "KHONG_RO"), ("2024-01", "MATCH"),
                                                                     ("2024-12", "KHONG_RO")])
        self.assertEqual(m["rows"][0]["why"], "tự doanh vc_lk chỉ từ 02/01/2019")
        self.assertEqual(m["rows"][2]["why"], "|Δ cổ đông| < 1%")
        self.assertIn(("2024-01-31", "2024-12-31"), calls)
        self.assertEqual(O.match_flip("TST", flow(-1))["rows"][1]["ket"], "FLIP")
        self.assertEqual(O.match_flip("TST", lambda a, b: {})["rows"][1]["ket"], "KHONG_RO")

        def boom(a, b):
            raise RuntimeError("P2 lỗi")
        self.assertEqual(O.match_flip("TST", boom)["rows"][1]["ket"], "KHONG_RO")
        self.assertFalse(O.match_flip("TS3", flow(1))["ok"])

    # ── 4.7 ──
    def test_capital_actions_classify(self):
        ca = O.capital_actions("TST", TODAY)
        k = {it["title"]: (it["kind"], it["sub"]) for it in ca["items"]}
        self.assertEqual(k["Phát hành cổ phiếu - Phát hành riêng lẻ"], ("thu_tien", "rieng_le"))
        self.assertEqual(k["Phát hành cổ phiếu - Cổ phiếu thưởng tỉ lệ 100.0%"], ("khong_thu", "thuong"))
        self.assertEqual(k["Phát hành cổ phiếu - Phát hành cho CBCNV"], ("esop", "esop"))
        self.assertEqual(k["Phát hành cổ phiếu - Quyền mua CP cho Cổ đông hiện hữu tỉ lệ 20.2%"], ("thu_tien", "quyen_mua"))
        self.assertEqual(k["Phát hành cổ phiếu - Phát hành để sáp nhập"], ("khong_thu", "sap_nhap"))
        self.assertEqual(k["Phát hành cổ phiếu - Loại lạ"], ("khac", "khac"))
        self.assertEqual(k["Trả cổ tức bằng tiền"], ("co_tuc_tien", "co_tuc_tien"))
        self.assertEqual(k["Niêm yết bổ sung"], ("niem_yet_them", "niem_yet_them"))
        self.assertEqual(ca["counts"], {"thu_tien": 1, "esop": 1, "khong_thu": 3, "co_tuc_tien": 1})
        self.assertEqual((ca["pre2010"], ca["pre2010_why"]), (True, O.PRE2010_WHY))
        self.assertEqual([it["date"] for it in ca["items"]], sorted((it["date"] for it in ca["items"]), reverse=True))

    def test_agm_and_timeline(self):
        a = O.agm_events("TST", TODAY)
        self.assertEqual((a["last"]["date"], [x["date"] for x in a["upcoming"]], len(a["items"])),
                         ("2026-04-22", ["2027-04-20"], 3))
        self.assertEqual(O.agm_events("TS2", TODAY)["why"], "events-all chưa nạp cho mã này")
        self.assertEqual(O.agm_events("TS3", TODAY)["why"], "chưa nạp vc_lk")
        t = O.timeline("TST", TODAY, cap_rows=3)
        self.assertEqual(len(t["rows"]), 3)
        self.assertEqual([r["date"] for r in t["rows"]], sorted((r["date"] for r in t["rows"]), reverse=True))
        n_years = sum(sum(y["counts"].values()) for y in t["years"])
        self.assertEqual(n_years + 3, len(O.timeline("TST", TODAY, months_full=600, cap_rows=999)["rows"]))
        kinds = {r["kind"] for r in O.timeline("TST", TODAY, months_full=600, cap_rows=999)["rows"]}
        self.assertEqual(kinds, {"von", "dhcd", "khac", "noi_bo", "dang_ky_mo"})
        tr = [r for r in O.timeline("TST", TODAY, months_full=600, cap_rows=999)["rows"] if r["status"] == "chuyen_giao"]
        self.assertEqual(len(tr), 4)

    def test_intent_sources(self):
        i = O.intent_sources("TST")
        cc = i["cauchuyen"]
        self.assertEqual([x["field"] for x in cc["items"]], ["dong_co", "diem_gay", "thau_tom", "muc_dich_keo",
                                                              "cau_hoi_mo_chi_tiet"])
        self.assertEqual((cc["n_unv"], cc["thau_tom"]["tier"], cc["muc_dich_keo"]["text"], cc["asof"]),
                         (1, N.T1, "mục đích", "2026-09-22"))
        self.assertEqual(cc["items"][1]["src"], "b.md | c.md")
        self.assertEqual([e["id"] for e in cc["events"]], ["E1"])
        self.assertEqual(i["owner_intent"], [
            {"date": "2025-05-14", "approx": True, "title": "t1", "detail": None, "tier": N.T3},
            {"date": "2024-01-01", "approx": False, "title": "t3", "detail": None, "tier": N.UNV}])
        self.assertEqual(i["nq"], {"nq": "NQ68", "chaebol": "C", "founder": "F", "as_of": "2026-05-23", "tier": N.EST,
                                   "src": "openclaw_hdcv/data/nq68_nq79.json#tier_a"})
        self.assertEqual(i["vung_gom"]["vwap"], 10)
        ks = set(keys_deep(i))
        self.assertFalse(ks & {"score", "phase", "verdict_v1", "kelly", "tieu_de"})

    # ── 4.8 ──
    def test_summary_rows(self):
        groups = {"grp": {"TST": "A", "TS3": "C"}, "has_vc": {"TST": True, "TS3": False}, "has_lk": {"TST": True}}

        def price_fn(tk, today):
            if tk == "TS3":
                raise RuntimeError("không có giá")
            return {"weeks": 100, "den": "2026-10-02", "d_fo_1y_pp": N.V(1.2, "1.2", N.T2),
                    "deal_spikes_52w": N.V(3, "3", N.EST), "fft_pct3y": N.V(26, "26", N.EST), "fft_pall": N.V(53, "53", N.EST)}
        rows = O.summary_rows(["TST", "TS3"], price_fn, TODAY, groups)
        self.assertEqual([r["tk"] for r in rows], ["TST", "TS3"])
        t, x = rows
        self.assertEqual((t["nhom"], t["vc"], t["lk"], t["tuan"], t["dk_mo"].value, t["codong_qs"].value, t["quy_n"].value),
                         ("A", True, True, 100, 1, 5, 4))
        self.assertAlmostEqual(t["nb_rong_12t"].value, 0.0)       # 12T không có dòng tự do (E 20/07/2025 ngoài cửa sổ)
        self.assertTrue(x["tt_dot_bien_52t"].can and x["nb_rong_12t"].can)
        self.assertIsNone(x["codong_qs"])
        for r in rows:
            for k, v in r.items():
                if k in dict(O.SUMMARY_COLS):
                    self.assertTrue(v is None or isinstance(v, N.V), k)
                    self.assertFalse(isinstance(v, N.V) and isinstance(v.text, str) and LABEL_RE.search(v.text), k)


@unittest.skipUnless(HAS_REAL, "kho thật vắng")
class RealStore(_EnvCase):
    sysdir = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import chaebol_map_data_tailieu as TL
        cls.g = O.universe_groups(TL.v21())

    def raw(self, tk, ep):
        return N.vc(tk, ep)[1]

    def test_universe_groups(self):
        g = self.g
        from chaebol_map_data_langkinh import basket, tv30
        self.assertEqual((len(g["order"]), len(g["A"]), len(g["B"]), len(g["C"])), (109, 30, 20, 59))
        self.assertEqual(g["A"], sorted(basket("VN30").value))
        self.assertEqual(g["A"], sorted(tv30()))
        self.assertEqual(g["B"], "BCM BVH CTD DGC GEE GEL GEX GMD HAH HCM MSR NVL PC1 PLX TPB VCI VGI VIX VPI VTP".split())
        self.assertEqual(g["order"], g["A"] + g["B"] + g["C"])
        self.assertTrue(all(x == sorted(x) for x in (g["A"], g["B"], g["C"])))
        self.assertFalse(g["has_vc"]["FOX"])
        self.assertTrue(g["has_vc"]["VIC"])

    def test_cong_line(self):
        from chaebol_map_data_langkinh import lk_hoso
        self.assertEqual(O.cong_line("VIC")["text"], lk_hoso("VIC")["cong"]["dong"])
        for tk in ("FOX", "BHI", "CST"):
            self.assertEqual(O.cong_line(tk)["text"], "CỔNG: [CẦN DATA]")
        t = O.cong_line("TCX")
        self.assertEqual(t["text"], lk_hoso("TCX")["cong"]["dong"])
        self.assertNotEqual(t["text"], "CỔNG: [CẦN DATA]")

    def test_chu_the_tiers_per_ticker(self):
        v = O.chu_the_label("VIC")["nhan"]
        self.assertEqual((v.value, v.tier, v.asof), ("cần", N.T3, "2026-09-10"))
        self.assertTrue(O.chu_the_label("CTG")["xung_dot"] and O.chu_the_label("BCM")["xung_dot"])
        fl = (N.read_json(N.bridge() / "data/fft_langkinh.json") or {}).get("ma") or {}
        tiers = []
        for tk in self.g["order"]:
            n = O.chu_the_label(tk)["nhan"]
            if not n.can:
                self.assertEqual(n.tier, fl[tk]["chu_the"]["bac"], tk)
                tiers.append(n.tier)
        self.assertIn(N.EST, tiers)
        self.assertEqual(O.sigma_view("VIC")["label"], "P/E")

    def test_owner_normalisation(self):
        r = {x["id"]: x for x in O.insider_rows("VIC", TODAY)["rows"]}
        self.assertTrue(any(x["owner"]["key"] == "p:1497" and x["owner"]["name"] == "Phạm Nhật Vượng" for x in r.values()))
        m = O.insider_rows("MSN", TODAY)["rows"]
        bank = {x["owner"]["key"] for x in m if "Equity New Market" in str(x["owner"]["name"])}
        self.assertEqual(bank, {"o:bankinvest private equity new markets ii k/s"})
        ch = [x["owner"]["alias"] for x in m if x["owner"]["name"] == "Công ty Cổ Phần Masan"]
        self.assertTrue(ch and all(a == {"from": "ctcp masan", "rule": "chain", "tier": N.EST} for a in ch))

    def test_insider_rows_vic_msn(self):
        ir = O.insider_rows("VIC", TODAY)
        self.assertEqual(ir["n_raw"], len(self.raw("VIC", "insider-transaction")))
        self.assertGreaterEqual(ir["n_raw"], 105)
        reg = [x for x in ir["rows"] if x["status"] == "dang_ky" and x["public"] == "2026-09-28"]
        self.assertEqual(len(reg), 6)
        self.assertTrue(all(x["before"] is None and x["after"] is None and x["own_after"] is None
                            and "dem_dang_ky" in x["flags"] for x in reg))
        msn = [x for x in O.insider_rows("MSN", TODAY)["rows"]
               if x["public"] == "2011-11-18" and x["side"] == -1 and x["status"] == "da_xong"]
        self.assertEqual(len(msn), 1)
        self.assertFalse(msn[0]["valid"])

    def test_pair_transfers_vic_f6(self):
        pt = O.pair_transfers("VIC", TODAY)
        p25 = [p for p in pt["pairs"] if p["date1"].startswith("2025")]
        self.assertEqual(sorted(p["qty"] for p in p25), sorted([35_041_830, 48_086_745, 70_646_767, 87_559_863, 60_017_806,
                                                                243_462_578, 75_993_997]))
        self.assertTrue(all(p["kind"] == "noi_nhom" for p in p25))
        self.assertEqual(sum(p["qty"] for p in p25), 620_809_586)
        self.assertAlmostEqual(sum(p["qty_now"].value for p in p25), 1_165_625_175, delta=1)
        self.assertEqual({p["date1"] for p in p25}, {"2025-05-16", "2025-06-10", "2025-06-17", "2025-06-27", "2025-10-09",
                                                       "2025-10-30", "2025-12-24"})
        self.assertIn(N.T1, [e["tier"] for e in pt["evidence"]])

    def test_ownership_ladder_f7_f9(self):
        lad = O.ownership_ladder("VIC", TODAY)
        v = next(o for o in lad["owners"] if o["key"] == "p:1497")
        seq = [p["pct"] for p in v["points"] if p["date"].startswith("2025")]
        for x in (16.92, 15.68, 13.86, 11.60, 10.04, 9.101):
            self.assertIn(x, seq)
        reg_ids = {x["id"] for x in O.insider_rows("VIC", TODAY)["rows"] if x["status"] != "da_xong"}
        self.assertFalse(reg_ids & {p["row"] for o in lad["owners"] for p in o["points"]})
        sk = next(o for o in O.ownership_ladder("MSN", TODAY, n=50)["owners"] if "Vina I " in str(o["name"]))
        self.assertEqual([p["pct"] for p in sk["points"]], [9.448, 3.67])
        self.assertAlmostEqual(sk["points"][0]["after_now"], 131_879_918, delta=1)

    def test_insider_net_vic_2025(self):
        g = O.insider_net("VIC", "2025-01-01", "2025-12-31", TODAY, by="group")
        self.assertGreaterEqual(g["n_pairs_excluded"], 7)
        self.assertNotIn("p:1497", [t["key"] for t in g["top"]])
        o = O.insider_net("VIC", "2025-01-01", "2025-12-31", TODAY, by="owner")
        v = next(t for t in o["top"] if t["key"] == "p:1497")
        self.assertLess(v["d_pct"].value, 0)

    def test_net_top_real_f_mbb_vic_ctd(self):
        d0 = "2025-10-05"
        mbb = next(t for t in O.insider_net("MBB", d0, TODAY, TODAY)["top"] if "Quân đội" in str(t["name"]))
        self.assertTrue(mbb["pct_before"].can)                                    # mốc 14/03/2024 cũ hơn 12T
        self.assertGreater(mbb["d_pct"].value, 0)                                 # Viettel MUA 118,424,946 cp
        vic = O.insider_net("VIC", d0, TODAY, TODAY)["top"]
        grp = next(t for t in vic if t["key"] == "Nhóm Phạm Nhật Vượng")
        lad = next(g for g in O.ownership_ladder("VIC", TODAY)["groups"] if g["group"] == "Nhóm Phạm Nhật Vượng")
        self.assertEqual(grp["n_mem"], len(lad["members"]))                       # gồm Tập đoàn Đầu tư Việt Nam
        self.assertAlmostEqual(grp["pct_after"].value, lad["pct_last"].value, places=6)
        ctd = next(t for t in O.insider_net("CTD", d0, TODAY, TODAY)["top"] if "KIM Vietnam Growth" in str(t["name"]))
        self.assertEqual((ctd["pct_before"].asof, ctd["pct_after"].asof), ("2025-08-05", "2026-05-12"))

    def test_pre_steps_in_insider_conversion(self):
        """acq_now dùng CÙNG hệ số với P2 (gồm bước giá suy trước ts_start); % vốn từ cp U mang U."""
        import chaebol_map_data_codong2_gia as P
        for tk in ("VIC", "REE", "HPG"):
            for r in O.insider_rows(tk, TODAY)["rows"]:
                if r["acq_now"]:
                    self.assertAlmostEqual(r["acq_now"], abs(r["acquire"]) * P.mult_at(tk, r["date"]), delta=1e-6)
        ys = {r["year"]: r for r in O.insider_yearly("VIC", TODAY)["years"]}
        self.assertAlmostEqual(ys[2009]["cp_buy_now"].value / 1e6, 390.50, delta=0.01)
        self.assertEqual(ys[2009]["net_pct"].tier, N.UNV)
        ree = {r["year"]: r for r in O.insider_yearly("REE", TODAY)["years"]}[2009]
        self.assertAlmostEqual(ree["net_pct"].value, -7.27, delta=0.01)

    def test_insider_yearly_and_exec(self):
        y = O.insider_yearly("MSN", TODAY)
        yrs = [r["year"] for r in y["years"]]
        self.assertEqual(yrs, list(range(yrs[0], yrs[-1] + 1)))
        rows = [x for x in O.insider_rows("MSN", TODAY)["rows"] if x["date"].startswith("2024") and x["status"] == "da_xong"
                and x["valid"] and (x["register"] or 0) > 0]
        want = sum(abs(x["acquire"]) for x in rows) / sum(x["register"] for x in rows) * 100
        self.assertAlmostEqual(next(r for r in y["years"] if r["year"] == 2024)["exec_ratio"].value, want)
        self.assertNotIn("2024-10-31", [x["date"] for x in rows])               # SK 31/10/2024 register 0: không tính
        self.assertLessEqual(len(y["recent"]), 40)
        self.assertEqual(O.exec_stats("VIC", TODAY)["n_overdue"].tier, N.UNV)

    def test_holder_table_mbb(self):
        h = O.holder_table("MBB", TODAY)
        self.assertEqual(h["n"], len(self.raw("MBB", "shareholder")))
        self.assertGreaterEqual(h["n"], 113)
        p = date.fromisoformat(h["period"])
        self.assertEqual(h["fresh_from"], (p - timedelta(days=183)).isoformat())
        fr = sorted((r["pct"].value for r in h["rows"] if r["fresh"]), reverse=True)
        self.assertAlmostEqual(h["conc"]["top3"].value, sum(fr[:3]))
        self.assertAlmostEqual(h["conc"]["hhi"].value, sum(x * x for x in fr))
        self.assertTrue(all(r["qty_now"] is None for r in h["rows"] if not r["fresh"]))

    def test_structure_bars_vic_f13(self):
        s = O.structure_bars("VIC")
        self.assertLess(abs(s["sum1"] - 100), 0.05)
        self.assertGreater(sum(b["pct"].value for b in s["bar2"]), 60)        # chồng lấn, không cộng vào bar1
        self.assertEqual(s["data_date"]["tier"], N.UNV)

    def test_codong_full_f14(self):
        c = O.codong_full("VIC")
        self.assertEqual((c["n_moc"], c["n_qs"], len(c["cap"])), (40, 16, 15))
        self.assertTrue(all(m["tier"] == N.EST for m in c["moc"] if m["kieu"] in ("noi_suy", "chep")))
        for tk in ("VIB", "MCH", "VPL", "TCB", "TCX"):
            self.assertTrue(O.codong_full(tk)["thin"], tk)
        self.assertFalse(O.codong_full("VIC")["thin"])
        for tk in ("GEX", "FOX"):
            self.assertEqual(O.codong_full(tk)["why"], "Vietcap không có số cổ đông; Toàn Vũ chỉ phủ 30 mã; chờ OCR BCTN")
        self.assertTrue(O.codong_delta("VIC", "2026-03-01", "2026-07-31").can)    # chỉ có mốc chép (CF)

    def test_fund_view_f20(self):
        v = O.fund_view("VIC")
        h = v["hist"]
        if h["n_funds0"] != h["n_funds1"]:          # VIC 37→41 quỹ: không lấy hiệu hai ảnh làm Δ
            self.assertTrue(h["delta_now"].can)
            self.assertIn("tập quỹ đổi %d→%d" % (h["n_funds0"], h["n_funds1"]), h["delta_now"].note)
        g = O.fund_view("GEL")["hist"]
        if g and g["n_funds0"] == g["n_funds1"]:
            self.assertFalse(g["delta_now"].can)
        self.assertIn("05/12/2025", v["net"]["y1"].note)
        self.assertAlmostEqual(O.fund_view("MBB")["hist"]["factor"], 1.2005, delta=1e-3)
        self.assertNotIn("value_bn", set(keys_deep(v)))

    def test_events_timeline_intent(self):
        self.assertTrue(O.capital_actions("VIC", TODAY)["pre2010"])
        r = O.agm_events("REE", TODAY)
        self.assertEqual((r["ok"], r["why"]), (False, "events-all chưa nạp cho mã này"))
        t = O.timeline("VIC", TODAY)
        self.assertLessEqual(len(t["rows"]), 60)
        self.assertTrue(t["years"])
        i = O.intent_sources("VIC")
        self.assertEqual(i["cauchuyen"]["thau_tom"]["tier"], N.T1)
        self.assertNotIn("tieu_de", [x["field"] for x in i["cauchuyen"]["items"]])
        self.assertEqual(len(i["owner_intent"]), 5)
        self.assertEqual(O.intent_sources("MSN")["nq"]["nq"], "NQ68")
        for tk in ("VIC", "MSN"):
            self.assertFalse(set(keys_deep(O.intent_sources(tk))) & {"score", "phase", "verdict_v1", "kelly", "verdict"})

    def test_summary_rows_109(self):
        rows = O.summary_rows(self.g["order"], None, TODAY, self.g)
        self.assertEqual([r["tk"] for r in rows], self.g["order"])
        for r in rows:
            for k, _ in O.SUMMARY_COLS:
                self.assertTrue(r[k] is None or isinstance(r[k], N.V), (r["tk"], k))
                if isinstance(r[k], N.V) and isinstance(r[k].text, str):
                    self.assertIsNone(LABEL_RE.search(r[k].text), (r["tk"], k))


class Static(unittest.TestCase):
    FILES = ("chaebol_map_data_codong2.py", "chaebol_map_data_codong2_ydo.py")
    BAN = re.compile(r"\b(BUY|SELL|TRIM|ADD|DCA)\b|%NAV|khuyến nghị mua|khuyến nghị bán|nên mua|nên bán")

    def test_sources(self):
        for f in self.FILES:
            src = (HERE / f).read_text(encoding="utf-8")
            for bad in ("vc_lk_fetch", "urllib", "requests", "socket", "open(", chr(0x2014), chr(0x2013), "as of"):
                self.assertNotIn(bad, src, f"{f}: {bad!r}")
            self.assertLessEqual(src.count("\n"), 800, f)
            tree = ast.parse(src)
            for n in ast.walk(tree):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.assertLessEqual(n.end_lineno - n.lineno + 1, 50, f"{f}:{n.name}")
                if isinstance(n, ast.Constant) and isinstance(n.value, str):
                    self.assertIsNone(self.BAN.search(n.value), f"{f}: {n.value[:60]!r}")

    def test_constants_verbatim(self):
        self.assertEqual(O.HIERARCHY_TEXT, "Thứ bậc khi tín hiệu xung đột (v1.7): Δ cổ đông thật (SS-T3, file Toàn Vũ) "
                                           "> hệ số k > proxy giá/KL (FFT)")
        self.assertEqual(O.FFT_MISS, ("FPT", "VCB", "MBB", "HPG", "CTG"))
        self.assertEqual(O.FFT_MISS_TEXT, "§6.4: proxy FFT đã bỏ sót phân phối ở FPT, VCB, MBB, HPG, CTG; FFT im lặng "
                                          "không có nghĩa là không phân phối")
        self.assertEqual((O.THIN_MAX_QS, O.FRESH_DAYS, O.MARKER_MIN_PCT), (4, 183, 0.1))
        self.assertEqual(O.WHY_NO_TV, "Vietcap không có số cổ đông; Toàn Vũ chỉ phủ 30 mã; chờ OCR BCTN")


if __name__ == "__main__":
    unittest.main()
