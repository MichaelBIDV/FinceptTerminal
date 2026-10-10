#!/usr/bin/env python3
"""Unit tests for chaebol_map_data.py — a tiny fixture _System tree (CHB_SYSTEM_DIR in a temp dir, sockets blocked),
a cross-interpreter smoke (3.11 venv-numpy2 ↔ system python3) and a smoke/performance pass on the real store
(skipped when absent). Run:  python3 test_chaebol_map_data.py   ·   "<venv-numpy2>/bin/python" test_chaebol_map_data.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import chaebol_map_data as D  # noqa: E402

VENV_PY = Path.home() / "Library/Application Support/com.fincept.terminal/venv-numpy2/bin/python"
REAL_SYS = Path.home() / "SECOND BRAIN-OBSIDIAN" / "_System"
ENV_KEYS = ("CHB_SYSTEM_DIR", "CHB_TODAY", "CHB_SKILLS_DIR", "CHB_SPEC_DIR")

COLS = ["tradingDate", "openPrice", "highestPrice", "lowestPrice", "closePrice", "averagePrice", "referencePrice",
        "ceilingPrice", "floorPrice", "openPriceAdjusted", "highestPriceAdjusted", "lowestPriceAdjusted",
        "closePriceAdjusted", "averagePriceAdjusted", "totalMatchVolume", "totalMatchValue", "totalDealVolume",
        "totalDealValue", "totalVolume", "totalValue", "foreignBuyVolumeTotal", "foreignSellVolumeTotal",
        "foreignBuyValueTotal", "foreignSellValueTotal", "foreignNetVolumeTotal", "foreignNetValueTotal", "foreignOwned",
        "foreignOwnedPercentage", "foreignCurrentRoom", "foreignTotalRoom", "foreignRoomPercentage", "totalShares",
        "marketCap", "stockType"]
PROP_COLS = ["tradingDate", "totalBuyTradeVolume", "totalBuyTradeValue", "totalSellTradeVolume", "totalSellTradeValue",
             "totalTradeNetVolume", "totalTradeNetValue", "totalMatchTradeNetVolume", "totalMatchTradeNetValue",
             "totalDealTradeNetVolume", "totalDealTradeNetValue", "totalVolume", "totalValue", "updateDate"]
# AAA: pre-listing row 04/09, holiday Fri 11/09, 1:1 split at GDKHQ 16/09 (f = 0.5 before, 1 after), last row lacks
# totalShares/marketCap, no proprietary record on 09/09 and 25/09.
AAA_DAYS = ["2026-09-04", "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10", "2026-09-14", "2026-09-15",
            "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25"]
SPLIT = "2026-09-16"


def aaa_prices():
    out = []
    for i, d in enumerate(AAA_DAYS):
        raw = 20000.0 + 200 * i if d < SPLIT else 10000.0 + 100 * i
        adj = raw / 2 if d < SPLIT else raw
        out.append((d, raw, adj, 1e6 if d < SPLIT else 2e6))
    return out


def ph_row(d, raw, adj, shares, kl=10000.0, fnv=1000.0, mcap=True):
    r = dict.fromkeys(COLS)
    r.update(tradingDate=d, openPrice=raw, highestPrice=raw * 1.01, lowestPrice=raw * 0.99, closePrice=raw,
             openPriceAdjusted=adj, highestPriceAdjusted=adj * 1.01, lowestPriceAdjusted=adj * 0.99,
             closePriceAdjusted=adj, totalMatchVolume=kl, totalMatchValue=raw * kl, foreignNetVolumeTotal=fnv,
             foreignNetValueTotal=fnv * raw, totalShares=shares, marketCap=shares * raw if mcap and shares else None,
             stockType="S")
    return [r[c] for c in COLS]


def wj(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def vcf(meta: dict, du) -> dict:
    return {"meta": {"bac": "FACT-T2", **meta}, "du_lieu": du}


OLD_NAMES = """
CAN Cols Decimal EST GATE_MAX_AGE_H OLD_MONTHS Path ROUND_HALF_UP SHARE_TOL SHORT STALE_MONTHS T1 T2 T3 TIER_COLOR UNV V
_CACHE _FX _P_SRC_BLOCK _P_SRC_HTML _P_SRC_LINE _STATUS _WARN _book_tiers _cols_of _db_path _drop_unsourced
_fact_numbers _finite _hdcv _index_cols _k11 _kho_close _last _memo _merge _months_ago _norm_fact _num _parse_ts _prop
_prop_map _psrc _read_text _ro_uri _shares_filled _sig _src_range _src_refs _sum _vwap_at _vwap_label _vwap_prep
_week_groups _win adj_factor adj_ratio adj_steps annotations asdict basket basket_weekly_flow bisect bridge can_data
capital_events claims_ledger clear_cache close codong_moc cong convert_price cross_holdings data_to dataclass date
datetime db_query ddmm ddmmyyyy demo details dossier ecosystems facts facts_for facts_for_src facts_index flow4 fmt_vn
foreign_net freshness groups_of hi_lo_52w index_close index_extremes index_pe_pb index_weekly index_weekly_spliced
insider_tx iso js_fixed js_locale json last_price leader lk lk_atom lk_hoso lk_view lui_thang market_cap math
news_events nqs_flow os owner_intent_curated ownership_structure pattern_label patterns pct_change pct_text pnl_since
portfolio_current portfolio_v21 price_history prop_net re read_json relationships round_half sell_side_targets
shares_out skills_dir source_audit spec_dir sqlite3 sys sys_dir ticker_gate timedelta to_jsonable today top_holders
tv30 usd_vnd v21 v21_get vc vc_dir vc_lk_status vietcap_view vnstore_status vwap_cluster warn warnings weekly_ohlcv
weekly_v21""".split()

K11_MD = """# Lăng kính
## 6 · Bước
### 6.1 Bảng danh mục — input bắt buộc của Step 10 (snapshot 10/09/2026, Khối 11)

| Mã | %NAV | P 3Y | vs VWAP12T | Chủ thể cần thị trường? |
|---|---|---|---|---|
| **FPT** | 12% | P47 | −12,1% | **Có** |
| **VCB** | 8% | P72 | −5,5% | **Không** |
| **MSN** | 8% | P30 | −11,5% | **Có** |
| **Cộng 3 mã VN100** | **28%** | | | |
| **KSV** | **3% UNVERIFIED** | — | — | Ngoài rổ |

Phần còn lại: **15% cash + 16% chưa giải trình** — hỏi user.

```
VCB   8 → 5      cash  15 → 22
Ứng viên thay thế (Pattern B xác nhận cả hai lớp): STB (đã trong watch) · MWG
```

## 7 · Khác
"""
HDCV_MD = """# Skill
## Danh mục tham chiếu (cập nhật 12/09/2026)

Core VCB 10% · FPT 12% · MSN 5%.
Tactical GEX 3%. Tiền mặt 16%.
**AVOID:** NVL, STB.

---
"""


def make_fixture(root: Path, with_v21: bool = True) -> dict:
    B = root / "fincept_bridge"
    vc = B / "state" / "vc_lk"
    px = aaa_prices()
    rows = [ph_row(d, r, a, s, mcap=(d != AAA_DAYS[-1])) for d, r, a, s in px]
    rows[-1][COLS.index("totalShares")] = None
    wj(vc / "AAA" / "price-history.json", vcf({"ma": "AAA", "du_lieu_toi": AAA_DAYS[-1]}, {"cot": COLS, "hang": rows}))
    prop = [[d, 0, 0, 0, 0, 500.0, 5e6, 300.0, 3e6, 200.0, 2e6, 0, 0, d] for d in AAA_DAYS[1:-1] if d != "2026-09-09"]
    wj(vc / "AAA" / "proprietary-history.json", vcf({"du_lieu_toi": "2026-09-24"}, {"cot": PROP_COLS, "hang": prop}))
    wj(vc / "AAA" / "details.json", vcf({"t_lay": "2026-09-26T15:00:00+07:00"}, {
        "listingDate": "2026-09-07T00:00:00", "issueShare": 2000000, "viOrganName": "CTCP Alpha", "sectorVn": "Ngân hàng",
        "freeFloatPercentage": 0.3, "foreignerPercentage": 0.05, "maximumForeignPercentage": 0.3, "statePercentage": 0.0,
        "rating": "BUY", "targetPrice": 15000.0, "ratingAsOf": "01-Sep-26", "upsideToTargetPercent": 0.2, "analyst": "X"}))
    wj(vc / "AAA" / "shareholder.json", vcf({"du_lieu_toi": "2026-06-30", "lay_luc": "2026-09-26T15:00:00+07:00"}, [
        {"ownerName": "X Corp", "ownerCode": "X1", "ownerType": "CORPORATE", "quantity": 400000, "percentage": 0.2,
         "publicDate": "2026-06-30", "updateDate": "2026-08-01T00:00:00"},
        {"ownerName": "X Corp", "ownerCode": "X1", "ownerType": "CORPORATE", "quantity": 300000, "percentage": 0.3,
         "publicDate": "2025-06-30", "updateDate": "2025-08-01T00:00:00"},
        {"ownerName": "Phó Vice", "ownerCode": "V1", "ownerType": "INDIVIDUAL", "quantity": 10000, "percentage": 0.005,
         "positionName": "Phó Chủ tịch Hội đồng Quản trị", "publicDate": "2026-06-30", "updateDate": "2026-08-02T00:00:00"},
        {"ownerName": "Chair Man", "ownerCode": "C1", "ownerType": "INDIVIDUAL", "quantity": 50000, "percentage": 0.025,
         "positionName": "Chủ tịch Hội đồng Quản trị", "publicDate": "2026-06-30", "updateDate": "2026-08-03T00:00:00"},
        {"ownerName": "Old Person", "ownerCode": "P1", "ownerType": "INDIVIDUAL", "quantity": 100000, "percentage": 0.1,
         "publicDate": "2024-01-31", "updateDate": "2024-02-01T00:00:00"}]))
    wj(vc / "AAA" / "shareholder-structure.json", vcf({"t_lay": "2026-09-26T15:00:00+07:00"}, {
        "totalShares": 2000000.0, "statePercentage": 0.0, "foreignPercentage": 0.05, "otherPercentage": 0.95,
        "bodPercentage": 0.03, "institutionPercentage": 0.6}))
    wj(vc / "AAA" / "insider-transaction.json", vcf({"du_lieu_toi": "2026-09-20"}, [
        {"publicDate": "2026-08-01T00:00:00", "eventCode": "DDIND", "actionTypeCode": "B", "actionTypeVi": "Mua",
         "tradeStatusVi": "Đã thực hiện xong", "traderNameVi": "Chair Man", "shareRegister": 1000.0, "shareAcquire": 1000.0,
         "ownershipAfterTrade": 0.025, "eventTitleVi": "mua"},
        {"publicDate": "2026-09-20T00:00:00", "eventCode": "DDINS", "actionTypeCode": "S", "actionTypeVi": "Bán",
         "tradeStatusVi": "Đăng ký", "traderOrganNameVi": "X Corp", "shareRegister": 5000.0, "shareAcquire": None,
         "startDate": "2026-09-25T00:00:00", "endDate": "2026-10-24T00:00:00", "eventTitleVi": "đăng ký bán"}]))
    wj(vc / "AAA" / "relationship.json", vcf({"t_lay": "2026-09-26T15:00:00+07:00"}, {
        "subsidiaries": [{"rightOrganCode": "B", "rightTicker": "BBB", "rightOrganNameVi": "CTCP Beta", "ownedPercentage": 0.6}],
        "affiliates": [{"rightOrganCode": "U", "rightTicker": "", "rightOrganNameVi": "Chưa niêm yết", "ownedPercentage": 0.2}]}))
    wj(vc / "AAA" / "events-v2.json", vcf({"du_lieu_toi": "2026-09-10"}, [
        {"eventCode": "ISS", "eventTitleVi": "Thưởng 1:1", "publicDate": "2026-09-10T00:00:00",
         "exrightDate": "2026-09-16T00:00:00", "exerciseRatio": 1.0},
        {"eventCode": "DIV", "eventTitleVi": "Cổ tức tiền", "publicDate": "2026-05-10T00:00:00", "exerciseRatio": 0.05,
         "valuePerShare": 500.0},
        {"eventCode": "ISS", "eventTitleVi": "Phát hành cổ phiếu - Phát hành riêng lẻ", "publicDate": "2025-01-02T00:00:00",
         "exrightDate": "2025-01-02T00:00:00", "exerciseRatio": 0.0}]))
    wj(vc / "BBB" / "price-history.json", vcf({"du_lieu_toi": "2026-09-22"},
                                              {"cot": COLS, "hang": [ph_row(d, 5000.0, 5000.0, 1e6) for d in AAA_DAYS[1:-3]]}))
    wj(vc / "BBB" / "shareholder.json", vcf({}, [{"ownerName": "X Corp", "ownerCode": "X1", "quantity": 50000,
                                                 "percentage": 0.05, "publicDate": "2026-06-30", "ownerType": "CORPORATE"}]))
    vni = [["2026-05-04", 0, 0, 0, 1900.0, 1], ["2026-05-05", 0, 0, 0, 1905.0, 1], ["2026-05-08", 0, 0, 0, 1915.37, 1],
           ["2026-05-11", 0, 0, 0, 1910.0, 1], ["2026-05-15", 0, 0, 0, 1921.6, 1], ["2026-05-18", 0, 0, 0, 1927.94, 1],
           ["2026-05-20", 0, 0, 0, 1880.0, 1]]
    wj(vc / "VNINDEX" / "gap-chart.json", vcf({"du_lieu_toi": "2026-05-20"}, {"cot": ["tradingDate", "o", "h", "l", "c", "v"],
                                                                             "hang": [[r[0], r[4], r[4], r[4], r[4], r[5]] for r in vni]}))
    wj(vc / "VNINDEX" / "ratio-daily.json", vcf({}, [{"pe": 12.0, "pb": 2.0, "tradingDate": "2026-09-24T00:00:00"},
                                                    {"pe": 12.4, "pb": 2.01, "tradingDate": "2026-09-25T00:00:00"},
                                                    {"pe": 99.0, "pb": 9.0, "tradingDate": "2026-09-25T00:00:00"}]))
    wj(vc / "_meta.json", {"cap_nhat": "2026-09-27T01:04:51+07:00", "ma": {
        "AAA": {"price-history": {"du_lieu_toi": "2026-09-25", "lay_luc": "2026-09-26T07:00:00", "trang_thai": "ok"}},
        "BBB": {"price-history": {"du_lieu_toi": "2026-09-22", "lay_luc": "2026-09-23T07:00:00", "trang_thai": "ok"}},
        "VCB": {"events-v1": {"trang_thai": "loi", "loi": "curl rc=16"}}}})
    # vnstore
    db = B / "vnstore" / "vn_store.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.executescript("""
      CREATE TABLE ma (symbol TEXT PRIMARY KEY, san TEXT, loai TEXT, ten TEXT, nganh TEXT, nhom TEXT, theo_doi INTEGER, cap_nhat TEXT);
      CREATE TABLE nen_ngay (symbol TEXT, ngay TEXT, mo REAL, cao REAL, thap REAL, dong REAL, kl REAL, nguon TEXT, PRIMARY KEY (symbol, ngay));
      CREATE TABLE ho_so (symbol TEXT PRIMARY KEY, ten TEXT, san TEXT, nganh TEXT, mo_ta TEXT, website TEXT, so_cp_luu_hanh REAL,
                          von_dieu_le REAL, ngay_niem_yet TEXT, nguon TEXT, cap_nhat TEXT, json TEXT);
      CREATE TABLE free_float (symbol TEXT PRIMARY KEY, ff_cp REAL, ff_pct REAL, issue_share REAL, nguon TEXT, cap_nhat TEXT, json TEXT);
      CREATE TABLE gia_moi (symbol TEXT PRIMARY KEY, ngay TEXT, gia REAL);
      CREATE TABLE meta (khoa TEXT PRIMARY KEY, gia_tri TEXT);""")
    con.executemany("INSERT INTO ma VALUES (?,?,?,?,?,?,?,?)", [
        ("AAA", "HOSE", "stock", "Alpha", "NH", "VN30,VN100", 1, "2026-09-27T08:04:48+07:00"),
        ("BBB", "HOSE", "stock", "Beta", "NH", "VN100", 1, "2026-09-27T08:04:48+07:00"),
        ("CCC", "HNX", "stock", "Gamma", "NH", "", 0, "2026-09-27T08:04:48+07:00")])
    con.executemany("INSERT INTO nen_ngay VALUES (?,?,?,?,?,?,?,?)",
                    [("VN30", d, 1, 1, 1, c, 1, "vci_history") for d, c in
                     (("2026-09-18", 1964.17), ("2026-09-22", 1950.0), ("2026-09-25", 1938.5))]
                    + [("KKK", d, 9, 9, 9, c, 100, n) for d, c, n in
                       (("2026-09-24", 9000.0, "vci_history"), ("2026-09-25", 9100.0, "vci_board"))])
    con.execute("INSERT INTO ho_so (symbol, so_cp_luu_hanh, cap_nhat) VALUES ('AAA', 2500000, '2026-09-24T00:00:00')")
    con.execute("INSERT INTO gia_moi VALUES ('ZZZ', '2026-09-25', 7000)")
    con.execute("INSERT INTO meta VALUES ('chay_vn_lichsu', '2026-09-26T22:46:36+07:00')")
    con.commit()
    con.close()
    # lăng kính
    wj(B / "data" / "lk_hoso" / "_index.json", {"toan_vu": ["AAA"]})
    atom = lambda v, u, b, t="2026-09-25", g=None: {"v": v, "u": u, "t": t, "b": b, "n": "fx", "g": g}  # noqa: E731
    wj(B / "data" / "lk_hoso" / "AAA.json", {
        "tao_luc": "2026-09-27T09:15:03+07:00", "phien_cuoi": "2026-09-25", "tuan_cuoi": "2026-09-25",
        "cong": {"dong": "CỔNG: [CẦN DATA — test] · không kết luận per-mã", "chu_the": {"nhan": "cần", "b": "SS-T3", "t": "2026-09-10"}},
        "fft": {"pct3y": atom(45, "diem", "FACT-T2"), "pall": atom(75, "diem", "FACT-T2"), "lech": atom(-30, "diem", "FACT-T2")},
        "vwap": {"v6": atom(1.0, "nghin_dong", "EST", t="2026-01-01")},
        "codong": {"trang_thai": "ok", "nguon_moc": "fft_codong.json", "pattern": {"nhan": "Pattern B"},
                   "moc": [{"ky": "2025-12", "v": 1000, "kieu": "quan_sat", "cf": False, "b": "SS-T3"},
                           {"ky": "2026-03", "v": 1000, "kieu": "chep", "cf": True, "b": "EST"}]},
        "chuthe": {"nhan": atom("cần", None, "SS-T3", t="2026-09-10")}, "nav": atom(3, "%", "EST", t="2026-09-21")})
    wj(B / "data" / "lk_hoso" / "BBB.json", {"codong": {"trang_thai": "CAN_DATA", "pattern": {"nhan": "Pattern A"}}})
    wj(B / "data" / "lk_mauhinh" / "BBB.json", {"t_cuoi": "2026-09-25", "mau": [
        {"id": "mu_sat", "nhan": "Mũ sắt", "trang_thai": "xac_nhan", "tu": "2026-07-01", "b": "EST"}]})
    wj(B / "data" / "lk_thitruong.json", {"tao_luc": "2026-09-27T09:15:03+07:00", "cong": {
        "dong": "CỔNG: [CẦN DATA — test] · không kết luận per-mã", "dung": True, "bac": "EST",
        "as_of": {"fft_langkinh": "2026-09-27 09:14"}, "tham_chieu": {"gap": 13.17, "bac": "EST"}, "canh_bao": ["x"]},
        "pe_vni": {"x": atom(12.399, "x", "FACT-T2"), "mu": atom(15.3, "x", "EST"), "sd": atom(2.3, "x", "EST"),
                   "z": atom(-1.3, "sigma", "EST")},
        "pb_vni": {"x": atom(2.004, "x", "FACT-T2")}})
    wj(B / "data" / "fft_langkinh.json", {"cap_nhat": "2026-09-20 08:00", "cong": {"dong": "CỔNG: bản cũ khác", "dung": True}})
    wj(B / "data" / "fft_codong.json", {"ma": {"AAA": {"ky_quan_sat_cuoi": "2025-12", "cf_so_ky": 1, "k_ly_do": "CF — chưa có số mới"}}})
    wj(B / "data" / "bang_vn30.json", {"dong": [{"01 Mã": "VNINDEX"}, {"01 Mã": "AAA"}, {"01 Mã": "ZZZ"}]})
    wj(B / "data" / "chaebol_ecosystems.json", {"as_of": "2026-09-23 10:04 ICT", "ecosystems": {
        "Alpha": {"group": "Alpha", "tickers": ["AAA", "BBB"], "members": {"AAA": {"top_shareholders": [
            {"ownerName": "X Corp", "publicDate": "2026-06-30"}, {"ownerName": "X Corp", "publicDate": "2021-01-01"}]}}},
        "Other": {"group": "Other", "tickers": ["BBB"], "members": [{"ticker": "BBB", "top_shareholders": []}]}}})
    wj(B / "data" / "so_nguon_audit.json", {"cap_nhat": "2026-09-27T00:54:26+07:00", "tom_tat": {"TƯƠI": 2},
        "tai_san": [{"id": "vc_lk_meta", "tieu_thu": ["chaebol_map"], "trang_thai": "TƯƠI", "tuoi_gio": 48.9,
                     "sla_gio": 24, "sla_cuoi_tuan": 72, "nguong_gio": 72},
                    {"id": "news_x", "tieu_thu": ["news"], "trang_thai": "CŨ"}],
        "van_de": [{"id": "news_x", "text": "cũ"}, {"id": "vc_lk_meta", "text": "x"}]})
    wj(B / "fft_cauhinh.json", {"danh_muc": {"ngay": "2026-09-21", "nav": {"FPT": 12, "VCB": 8, "MSN": 8},
        "nav_unverified": {"KSV": 3}, "watch": ["MBB"], "avoid": ["NVL", "STB", "DGC"],
        "xung_dot": {"STB": "avoid vs watch"}}})
    if with_v21:
        wj(B / "data" / "chaebol_map" / "v21_const.json", {"_meta": {"md5": "4f647f7a"}, "INDEX_DATA": {"VNINDEX_PL_W": [
            ["2026-05-01", 1850.0, 0.5, 1, 2, 3, 4], ["2026-05-08", 1915.37, 3.305, 100.52, -0.47, 9.26, -109.31]]},
            "PORTFOLIO_ACTION": {"current": [{"tk": "AAA", "position": 100}]}, "ACTION_PORT_25": [{"tk": "AAA"}]})
    spec = B / "chaebol_map_spec"
    wj(spec / "facts_f1_t.json", [{"ma": ["AAA"], "nhom": "Alpha", "loai": "so_lieu", "noi_dung": "a", "bac": "FACT-T2",
                                   "nguon": "vc_lk", "so_lieu": {"gia": "1 đ", "n": 5},
                                   "thay_the_menh_de_cu": "x.html dòng 102 FLOW.AAA 'px'; L250-251 · Synthesis L1+L2"},
                                  {"ma": ["BBB", "AAA"], "nhom": "Alpha", "loai": "claim", "noi_dung": "b"}])
    wj(spec / "facts_f2_t.json", [{"id": "F2-001", "ma": "AAA", "nhom": "Beta", "loai": "su_kien", "noi_dung": "c",
                                   "nguon": ["a", "b"], "so_lieu": [{"ten": "x", "gia_tri": 1}],
                                   "thay_the_menh_de_cu": [{"trich": "C09 'IPO' (x.html:5353; 5360)",
                                                            "khoi": "CLAIMS_54.C09", "dong": 804}],
                                   "trang_thai_menh_de_cu": "KHÔNG ÁP DỤNG (dữ kiện mới)"}])
    kos = root / "knowledge_os" / "chaebol_map"
    wj(kos / "cap_nhat_2026-09-26.json", {"overview": {"old": {"text": "cũ", "tier": "FACT-T2", "src": "s"}}})
    wj(kos / "cap_nhat_2026-09-27.overview.json", {"as_of": "2026-09-27", "overview": {
        "p1": {"text": "mới", "tier": "FACT-T1", "asof": "2026-09-20", "src": "cbtt"}, "bad": {"text": "x", "tier": "EST"}}})
    wj(kos / "cap_nhat_2026-09-27.claims20.json", {"claims20": {"C01": {"status": "BỊ BÁC", "tier": "FACT-T2", "src": "vc"}},
                                                  "catalyst": [{"x": 1, "tier": "EST", "src": "s"}, {"x": 2, "tier": "EST"}]})
    wj(root / "liquidity_daily" / "output" / "latest.json", {"rates": {
        "fx_central": 25641.0, "fx_central_prev": 25635.0, "fx_central_asof": "25/09/2026",
        "fx_nhtm_sell": 26180.0, "fx_nhtm_sell_asof": "25/09/2026"}})
    wj(B / "data" / "bang_widata.json", {"dong": [{"1 Chỉ tiêu": "Tỷ giá trung tâm", "2 Kỳ": "25/09", "3 Giá trị": "25.641",
                                                   "7 Ghi chú": "NHTM bán 26.170 · trần 26.923"}]})
    wj(root / "alpha_spine" / "nqs_flow.json", {"generated_at": "2026-09-26T16:46", "source": "NQS", "window_sessions": 10,
                                                "by_ticker": {"AAA": {"nn": 10.5, "ca": 0.0, "td": -2.0, "tc": -8.5,
                                                                      "as_of": "25/09", "n": 20}}})
    sk = root / "skills"
    (sk / "langkinh-cautruc-codong").mkdir(parents=True)
    (sk / "langkinh-cautruc-codong" / "SKILL.md").write_text(K11_MD, encoding="utf-8")
    (sk / "hoidongcovanai-chungkhoan").mkdir(parents=True)
    (sk / "hoidongcovanai-chungkhoan" / "SKILL.md").write_text(HDCV_MD, encoding="utf-8")
    return {"CHB_SYSTEM_DIR": str(root), "CHB_TODAY": "2026-09-27", "CHB_SKILLS_DIR": str(sk)}


def _deny(*_a, **_k):
    raise RuntimeError("mạng bị chặn trong test")


_PATCHES = [mock.patch("socket.socket", _deny), mock.patch("socket.create_connection", _deny),
            mock.patch("socket.getaddrinfo", _deny)]


def setUpModule():
    for p in _PATCHES:
        p.start()


def tearDownModule():
    for p in _PATCHES:
        p.stop()


class FixtureCase(unittest.TestCase):
    with_v21 = True

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="chb_data_"))
        self.env = make_fixture(self.tmp, self.with_v21)
        self._env = mock.patch.dict(os.environ, self.env)
        self._env.start()
        D.clear_cache()

    def tearDown(self):
        self._env.stop()
        D.clear_cache()
        shutil.rmtree(self.tmp, ignore_errors=True)


class FormatTests(unittest.TestCase):
    def test_js_rules(self):
        self.assertEqual(D.js_fixed(450.25, 1), "450.3")      # nửa → xa 0 (JS), không phải nửa chẵn
        self.assertEqual(D.js_fixed(1.005, 2), "1.00")        # giá trị nhị phân thật < 1.005
        self.assertEqual(D.js_fixed(-0.04, 1), "-0.0")
        self.assertEqual(D.js_locale(1938.5), "1,938.5")
        self.assertEqual(D.js_locale(1915.37), "1,915.37")
        self.assertEqual(D.js_locale(-1234.5, 0), "-1,235")
        self.assertEqual(D.fmt_vn(-1234.5, 1), "−1.234,5")
        self.assertEqual(D.pct_text(2.5, 1), "+2.5%")
        self.assertEqual(D.js_fixed(None), D.CAN)

    def test_v_and_tags(self):
        v = D.V(1.0, "1", D.T2, "2026-09-25")
        self.assertEqual(v.tag(), "T2")
        self.assertEqual(v.tag(True), "T2·25/09")
        c = D.can_data("lý do")
        self.assertTrue(c.can)
        self.assertEqual(c.show(), "[CẦN DATA]")
        self.assertEqual(c.tag(), "")
        self.assertEqual(D.to_jsonable({"a": v, "b": float("nan")})["b"], None)

    def test_lui_thang_and_iso(self):
        self.assertEqual(D.lui_thang("2026-08-31", 6), "2026-02-28")
        self.assertEqual(D.iso("25/09/2026"), "2026-09-25")
        self.assertEqual(D.ddmm("2026-09-25T00:00:00"), "25/09")

    def test_no_network_imports(self):
        files = sorted(HERE.glob("chaebol_map_data*.py"))
        # 05/10: +vciq, +codong2 (+_ydo, _gia, _dong); phiên khác có thể thêm module dữ liệu mới → kiểm ⊇ 12 tệp đã biết
        known = {"chaebol_map_data%s.py" % x for x in ("", "_nen", "_gia", "_dongtien", "_sohuu", "_langkinh", "_tailieu",
                                                       "_vciq", "_codong2", "_codong2_ydo", "_codong2_gia", "_codong2_dong")}
        self.assertLessEqual(known, {f.name for f in files}, [f.name for f in files])
        for f in files:
            src = f.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"^\s*(import|from)\s+(socket|urllib|http|ssl|requests)\b", src, re.M), f.name)


class FacadeTests(unittest.TestCase):
    """final_check §6.2 #10: chaebol_map_data.py tách thành 6 tệp con ≤800 dòng, mặt tiền giữ đúng mọi tên cũ."""

    def test_files_split_and_short(self):
        for name in D.SUBMODULES + ("chaebol_map_data",):
            n = len((HERE / (name + ".py")).read_text(encoding="utf-8").splitlines())
            self.assertLessEqual(n, 800, name)

    def test_facade_reexports_every_old_name(self):
        missing = [x for x in OLD_NAMES if not hasattr(D, x)]
        self.assertEqual(missing, [])
        import chaebol_map_data_gia as G
        import chaebol_map_data_nen as N
        self.assertIs(D._CACHE, N._CACHE)                      # cache/cảnh báo dùng chung một đối tượng
        self.assertIs(D._WARN, N._WARN)
        self.assertIs(D.V, N.V)
        self.assertIs(D.price_history, G.price_history)
        for new in ("adj_fix", "share_events"):
            self.assertTrue(callable(getattr(D, new)), new)


class PriceTests(FixtureCase):
    def test_last_price_and_listing_trim(self):
        lp = D.last_price("AAA")
        self.assertEqual(lp["date"], "2026-09-25")
        self.assertEqual(lp["raw"].tier, D.T2)
        self.assertEqual(lp["raw"].value, 10000.0 + 100 * 14)
        self.assertEqual(D.price_history("AAA").dates[0], "2026-09-07")   # 04/09 trước niêm yết bị cắt
        self.assertTrue(D.close("AAA", "2026-09-01").can)

    def test_adj_factor_and_convert(self):
        f = D.adj_factor("AAA", "2026-09-10")
        self.assertAlmostEqual(f.value, 0.5)
        self.assertEqual(f.tier, D.EST)
        self.assertIn("16/09/2026 ×0.5000", f.note)
        self.assertAlmostEqual(D.convert_price("AAA", 30000, "2026-09-10").value, 15000)
        self.assertAlmostEqual(D.adj_factor("AAA", "2026-09-17").value, 1.0)

    def test_vnstore_fallback_is_labelled(self):
        v = D.close("KKK")
        self.assertEqual((v.value, v.src), (9100.0, "vnstore.nen_ngay[KKK].closePrice"))
        self.assertIn("trộn", v.note)
        self.assertTrue(D.adj_factor("KKK", "2026-09-24").can)
        self.assertTrue(D.foreign_net("KKK", 2)["vol"].can)
        self.assertTrue(any("KKK: không có vc_lk" in w for w in D.warnings()))

    def test_pct_change_uses_adjusted(self):
        a0 = (20000.0 + 200 * 4) / 2      # 10/09 điều chỉnh
        pc = D.pct_change("AAA", "2026-09-10")
        self.assertAlmostEqual(pc.value, ((10000.0 + 100 * 14) / a0 - 1) * 100)
        self.assertIn("10/09/2026", pc.note)

    def test_shares_mismatch_and_market_cap_fallback(self):
        s = D.shares_out("AAA")
        self.assertEqual(s.value, 2e6)
        self.assertEqual(s.asof, "2026-09-24")               # phiên cuối có totalShares
        self.assertIn("NGUỒN LỆCH", s.note)
        self.assertTrue(any("AAA: số cp" in w for w in D.warnings()))
        mc = D.market_cap("AAA")
        self.assertEqual(mc.tier, D.EST)
        self.assertAlmostEqual(mc.value, 2e6 * (10000.0 + 100 * 14))

    def test_hi_lo_52w(self):
        h = D.hi_lo_52w("AAA")
        self.assertAlmostEqual(h["hi"].value, 10000.0 + 100 * 14)
        self.assertEqual(h["lo"].asof, "2026-09-07")

    def test_pnl_since(self):
        p = D.pnl_since("AAA", "2026-09-10", px0=20800.0, position=100, cost=20000.0)
        self.assertEqual(p["pct"].tier, D.EST)
        self.assertAlmostEqual(p["value_now"].value, 100 * 20800 * (1 + p["pct"].value / 100))
        self.assertIn("pnl", p)

    def test_missing_ticker_falls_back_to_board(self):
        v = D.close("ZZZ")
        self.assertEqual(v.value, 7000)
        self.assertIn("gia_moi", v.src)
        self.assertTrue(D.close("QQQ").can)


class WeeklyTests(FixtureCase):
    def test_week_labels_and_values(self):
        w = D.weekly_ohlcv("AAA")
        labels = [r["label"] for r in w.value]
        self.assertEqual(labels, ["2026-09-07", "2026-09-14", "2026-09-21"])
        first = w.value[0]
        self.assertEqual(first["week_end"], "2026-09-10")      # tuần nghỉ thứ Sáu
        self.assertEqual(first["n"], 4)
        self.assertFalse(first["partial"])
        self.assertEqual(first["td_n"], 3)                      # không có bản ghi 09/09
        self.assertEqual(first["td_vol"], 1500.0)
        self.assertEqual(first["td_khop_vol"], 900.0)
        self.assertEqual(first["nn_vol"], 4000.0)
        self.assertFalse(w.value[-1]["partial"])
        self.assertTrue(D.weekly_ohlcv("AAA", end="2026-09-23").value[-1]["partial"])
        self.assertEqual([r["label"] for r in D.weekly_ohlcv("AAA", label="friday").value][0], "2026-09-11")

    def test_weekly_v21_format(self):
        rows = D.weekly_v21("AAA").value
        self.assertEqual(len(rows[0]), 10)
        self.assertIsNone(rows[0][3])
        self.assertIsNone(rows[0][4])
        self.assertEqual(rows[-1][1], round((10000.0 + 100 * 14) / 1000, 2))
        self.assertEqual(rows[0][5], 0.001)                     # td khớp 900 cp → 0.001 M

    def test_vwap_normalized_by_shares(self):
        ph = D.price_history("AAA")
        C, S = ph.col("closePriceAdjusted"), D._shares_filled(ph)
        exp = sum(c * 1e4 / s for c, s in zip(C, S)) / sum(1e4 / s for s in S)
        v = D.vwap_cluster("AAA")                               # lk_hoso.vwap khác phiên → tự tính
        self.assertAlmostEqual(v["v6"].value, exp / 1000)
        self.assertEqual(v["v6"].tier, D.EST)
        self.assertIn(v["nhan"], ("tren_cum", "thoat_6t", "khac", "kep_nong", "kep_sau"))


class IndexTests(FixtureCase):
    def test_index_weekly_vnindex(self):
        w = D.index_weekly("VNINDEX")
        self.assertEqual([r["date"] for r in w.value], ["2026-05-08", "2026-05-15", "2026-05-20"])
        self.assertEqual(w.value[1]["chg"], round((1921.6 / 1915.37 - 1) * 100, 3))
        self.assertTrue(w.value[-1]["partial"])
        self.assertEqual(w.src, "vc_lk/VNINDEX/gap-chart")

    def test_vn30_from_vnstore(self):
        w = D.index_weekly("VN30")
        self.assertEqual(w.src, "vnstore.nen_ngay")
        self.assertEqual(w.value[-1]["c"], 1938.5)
        self.assertEqual(D.index_close("VN30").text, "1,938.5")

    def test_spliced(self):
        sp = D.index_weekly_spliced("VNINDEX")
        self.assertEqual([r["src"] for r in sp.value], ["V21", "V21", "live", "live"])
        self.assertIsNone(sp.value[2]["ca"])
        self.assertEqual(sp.value[2]["chg"], round((1921.6 / 1915.37 - 1) * 100, 3))

    def test_extremes_and_pe(self):
        e = D.index_extremes("VNINDEX", "2026-05-08")
        self.assertEqual((e["peak"].value, e["peak"].asof), (1927.94, "2026-05-18"))
        self.assertEqual(e["trough_after_peak"].value, 1880.0)
        pe = D.index_pe_pb("VNINDEX")
        self.assertEqual(pe["pe"].src, "fx")                   # lk_thitruong
        self.assertEqual(pe["pe_z"].tier, D.EST)
        pd = D.index_pe_pb("VNINDEX", "2026-09-25")
        self.assertEqual(pd["pe"].value, 12.4)                 # dòng trùng: giữ dòng đầu
        self.assertTrue(D.index_pe_pb("VN30")["pe"].can)


class FlowTests(FixtureCase):
    def test_foreign_and_prop(self):
        fn = D.foreign_net("AAA", 5)
        self.assertEqual(fn["vol"].value, 5000.0)
        self.assertEqual((fn["from"], fn["to"]), ("2026-09-21", "2026-09-25"))
        pn = D.prop_net("AAA", 5)
        self.assertEqual((pn["n_co"], pn["complete"], pn["vol"].value), (4, False, 2000.0))
        self.assertIn("4/5 phiên", pn["vol"].note)
        self.assertEqual(D.prop_net("AAA", 5, kind="khop")["vol"].value, 1200.0)

    def test_flow4(self):
        f = D.flow4("AAA", 5)
        self.assertTrue(f["ca"].can and f["tc"].can and f["sig"].can)
        self.assertAlmostEqual(f["nn"].value, 0.005)
        self.assertAlmostEqual(f["td"].value, 0.0012)           # tự doanh KHỚP
        self.assertAlmostEqual(f["du"].value, -(0.005 + 0.0012))
        self.assertEqual(f["du"].tier, D.EST)

    def test_nqs_only_real_channels(self):
        q = D.nqs_flow("AAA")
        self.assertEqual(q["nn"].value, 10.5)
        self.assertEqual(q["nn"].asof, "2026-09-25")
        self.assertTrue(q["ca"].can and q["tc"].can)

    def test_basket_weekly_flow(self):
        b = D.basket_weekly_flow("VN30")
        self.assertEqual(b.tier, D.EST)
        self.assertIn("1/1", b.note)
        self.assertEqual(b.value[-1]["nn_vol"], 5000.0)


class Fixes2709Tests(FixtureCase):
    """final_check §6.2 #3 #4 #6 #7: ngày thật của số, quy đổi quyền, GDKHQ, chuỗi điều chỉnh hỏng, sở hữu chéo."""

    def edit(self, rel, fn):
        p = self.tmp / "fincept_bridge" / "state" / "vc_lk" / rel
        d = json.loads(p.read_text(encoding="utf-8"))
        fn(d)
        wj(p, d)
        D.clear_cache()

    def test_flow_asof_is_last_real_record(self):
        def drop_last_nn(d):
            for c in ("foreignNetVolumeTotal", "foreignNetValueTotal"):
                d["du_lieu"]["hang"][-1][COLS.index(c)] = None
        self.edit("AAA/price-history.json", drop_last_nn)
        fn, pn = D.foreign_net("AAA", 5), D.prop_net("AAA", 5)
        self.assertEqual((fn["vol"].asof, fn["n_co"], fn["last"], fn["to"]), ("2026-09-24", 4, "2026-09-24", "2026-09-25"))
        self.assertIn("4/5 phiên có số", fn["vol"].note)
        self.assertEqual((pn["vol"].asof, pn["last"], pn["n_co"]), ("2026-09-24", "2026-09-24", 4))
        self.assertIn("dữ liệu tự doanh tới 24/09/2026", pn["vol"].note)      # tab đọc chuỗi này
        f = D.flow4("AAA", 5)
        self.assertEqual((f["nn"].asof, f["td"].asof, f["du"].asof), ("2026-09-24", "2026-09-24", "2026-09-24"))
        self.assertEqual((f["nn_n_co"], f["nn_last"], f["td_n_co"], f["td_last"]), (4, "2026-09-24", 4, "2026-09-24"))
        self.assertEqual(D.prop_net("AAA", 1, "2026-09-09")["last"], None)     # phiên vắng: không điền 0

    def test_adjust_to_current_shares(self):
        ev = D.share_events("AAA")
        self.assertEqual([(e["date"], e["factor"]) for e in ev], [("2026-09-16", 2.0)])
        self.assertEqual(D.share_events("AAA", "2026-09-16"), [])
        fn, fa = D.foreign_net("AAA", 10), D.foreign_net("AAA", 10, adjust=True)   # 14/09→25/09, 2 phiên trước GDKHQ
        self.assertEqual((fn["vol"].value, fn["vol"].tier), (10000.0, D.T2))
        self.assertEqual((fa["vol"].value, fa["vol"].tier, fa["adj"]), (12000.0, D.EST, [("2026-09-16", 2.0)]))
        self.assertIn("KL quy về số cp hiện hành: ×2 trước 16/09/2026", fa["vol"].note)
        self.assertEqual((fa["val"].value, fa["val"].tier), (fn["val"].value, D.T2), "giá trị đồng không quy đổi")
        self.assertEqual(D.prop_net("AAA", 10, adjust=True)["vol"].value, 2 * 500 * 2 + 7 * 500.0)
        self.assertEqual(D.foreign_net("AAA", 5, adjust=True)["vol"].tier, D.T2, "cửa sổ sau GDKHQ: không quy đổi")
        self.assertAlmostEqual(D.flow4("AAA", 10, adjust=True)["nn"].value, 0.012)
        w = D.weekly_ohlcv("AAA", adjust=True).value[0]
        self.assertEqual((w["nn_vol"], w["td_vol"], w["nn_val"]), (8000.0, 3000.0, D.weekly_ohlcv("AAA").value[0]["nn_val"]))

    def test_basket_last_dates_and_adjust(self):
        b = D.basket_weekly_flow("VN30")
        self.assertEqual((b.value[-1]["nn_last"], b.value[-1]["td_last"]), ("2026-09-25", "2026-09-24"))
        self.assertEqual(b.value[0]["td_last"], "2026-09-10")
        ba = D.basket_weekly_flow("VN30", adjust=True)
        self.assertEqual((ba.value[0]["nn_vol"], b.value[0]["nn_vol"]), (8000.0, 4000.0))
        self.assertIn("quyền mua ở 1 mã: AAA", ba.note)

    def test_capital_events_filter_by_exright(self):
        self.assertEqual([e["code"] for e in D.capital_events("AAA", "2026-09-12").value], ["ISS"])   # GDKHQ 16/09
        self.assertEqual(D.capital_events("AAA", "2026-09-12", by="public").value, [])                # công bố 10/09
        self.assertEqual([e["effective"] for e in D.capital_events("AAA").value], ["2026-09-16", "2026-05-10", "2025-01-02"])
        with self.assertRaises(ValueError):
            D.capital_events("AAA", by="x")

    def test_rights_after_pub_not_converted(self):
        self.edit("AAA/events-v2.json", lambda d: d["du_lieu"].append({
            "eventCode": "ISS", "eventTitleVi": "Phát hành cổ phiếu - Quyền mua CP cho Cổ đông hiện hữu tỉ lệ 10.0%",
            "publicDate": "2026-09-01T00:00:00", "exrightDate": "2026-09-20T00:00:00", "exerciseRatio": 0.1}))
        x = D.top_holders("AAA").value[0]
        self.assertTrue(x["qty_now"].can and x["pct_now"].can)
        self.assertIn("quyền mua GDKHQ 20/09/2026", x["qty_now"].note)
        self.assertIsNone(x["factor"])

    def test_top_holders_sort_option(self):
        self.edit("AAA/shareholder.json", lambda d: d["du_lieu"].append({                 # 30/06: 450k > 400k thô
            "ownerName": "Y Fund", "ownerCode": "Y1", "ownerType": "CORPORATE", "quantity": 450000, "percentage": 0.225,
            "publicDate": "2026-09-18", "updateDate": "2026-09-19T00:00:00"}))
        self.assertEqual([x["code"] for x in D.top_holders("AAA", 2).value], ["Y1", "X1"], "mặc định: SL thô như cũ")
        self.assertEqual([x["code"] for x in D.top_holders("AAA", 2, sort="qty_now").value], ["X1", "Y1"])
        with self.assertRaises(ValueError):
            D.top_holders("AAA", sort="x")

    def test_broken_vendor_adjusted_tail(self):
        days = AAA_DAYS[1:11]                                # 10 phiên; 6 phiên đầu adj/raw 0,9 ổn định rồi nhiễu
        f = [0.9] * 6 + [0.95, 1.03, 0.99, 1.01]
        wj(self.tmp / "fincept_bridge/state/vc_lk/MMM/price-history.json",
           vcf({}, {"cot": COLS, "hang": [ph_row(d, 10000.0, 10000.0 * x, 1e6) for d, x in zip(days, f)]}))
        D.clear_cache()
        fix = D.adj_fix("MMM")
        self.assertEqual((fix["brk"], fix["k"], round(fix["last"], 4), fix["stable"]), (days[6], 5, 1.01, 0.9))
        self.assertIsNone(D.adj_fix("AAA"), "AAA: adj/raw phiên cuối = 1")
        self.assertEqual(D.close("MMM", adjusted=True).value, 10000.0)                     # sau điểm hỏng: giá thô
        self.assertIn("⚑ chuỗi điều chỉnh vendor lệch từ", D.close("MMM", adjusted=True).note)
        self.assertEqual(D.adj_steps("MMM", days[0]), [(days[6], 0.9)])
        self.assertAlmostEqual(D.adj_factor("MMM", days[0]).value, 0.9)
        self.assertAlmostEqual(D.pct_change("MMM", days[0]).value, (10000.0 / 9000.0 - 1) * 100)
        self.assertEqual(D.hi_lo_52w("MMM")["hi"].value, 10000.0)
        self.assertEqual(D.share_events("MMM"), [], "bước giá không kèm tăng cp (cổ tức tiền) không phải sự kiện chia cp")

    def test_cross_holdings_sorted_no_zero_no_dup(self):
        self.edit("AAA/relationship.json", lambda d: d["du_lieu"]["affiliates"].extend([
            {"rightOrganCode": "B", "rightTicker": "BBB", "rightOrganNameVi": "CTCP Beta", "ownedPercentage": 0.6},
            {"rightOrganCode": "Z", "rightTicker": "ZZZ", "rightOrganNameVi": "Zeta", "ownedPercentage": 0.0}]))
        self.edit("BBB/shareholder.json", lambda d: d["du_lieu"][0].update(percentage=0.5))
        ch = D.cross_holdings()
        self.assertEqual([(e["from"], e["to"], e["kind"]) for e in ch["ticker_edges"]], [("AAA", "BBB", "subsidiaries")])
        self.assertIn("bỏ 1 cạnh 0,00% và 1 cạnh trùng", ch["note"])
        self.assertEqual([h["tk"] for h in ch["owners"][0]["holdings"]], ["BBB", "AAA"], "holdings sắp theo %")


class OwnershipTests(FixtureCase):
    def test_top_holders(self):
        th = D.top_holders("AAA")
        names = [x["name"] for x in th.value]
        self.assertEqual(names.count("X Corp"), 1)
        x = th.value[0]
        self.assertEqual((x["name"], x["public_date"]), ("X Corp", "2026-06-30"))
        # thưởng 1:1 GDKHQ 16/09 sau ngày công bố 30/06 → SL 400.000 quy về 800.000 cp hiện hành (§6.2 #7)
        self.assertEqual((x["qty_now"].value, x["qty_now"].tier, x["factor"]), (800000.0, D.EST, 2.0))
        self.assertIn("×2 trước 16/09/2026", x["qty_now"].note)
        self.assertAlmostEqual(x["pct_now"].value, 40.0)
        self.assertEqual(x["pct_now"].tier, D.EST)
        self.assertAlmostEqual(x["pct_pub"].value, 20.0)
        old = next(i for i in th.value if i["name"] == "Old Person")
        self.assertTrue(old["old"] and old["stale"])
        self.assertIn("khử 1 dòng trùng", th.note)

    def test_leader_skips_vice(self):
        self.assertEqual(D.leader("AAA").value, "Chair Man")
        self.assertTrue(D.leader("BBB").can)

    def test_structure_insider_relationship(self):
        s = D.ownership_structure("AAA")
        self.assertAlmostEqual(s["institution"].value, 60.0)
        self.assertEqual(s["institution"].asof, "2026-09-26")
        ins = D.insider_tx("AAA").value
        self.assertEqual(ins[0]["status"], "dang_ky")
        self.assertIsNone(ins[0]["acquire"])
        self.assertEqual(ins[1]["status"], "da_xong")
        rel = D.relationships("AAA")
        self.assertEqual(rel["subsidiaries"][0]["ticker"], "BBB")
        self.assertIsNone(rel["subsidiaries"][0]["pct"].asof)
        self.assertIn("UNVERIFIED", rel["note"])

    def test_cross_holdings(self):
        ch = D.cross_holdings()
        self.assertEqual([o["code"] for o in ch["owners"]], ["X1"])
        self.assertEqual({h["tk"] for h in ch["owners"][0]["holdings"]}, {"AAA", "BBB"})
        self.assertEqual(ch["ticker_edges"][0]["to"], "BBB")

    def test_details_view_events(self):
        self.assertEqual(D.details("AAA")["listing_date"], "2026-09-07")
        vv = D.vietcap_view("AAA")
        self.assertEqual(vv["rating"].tier, D.T3)
        self.assertTrue(vv["stale"] is False)
        ev = D.capital_events("AAA").value
        self.assertEqual(ev[0]["ratio_text"], "100.00 cp/100 cp")
        self.assertEqual(ev[1]["ratio_text"], "500 đ/cp")
        self.assertEqual((ev[2]["ratio"], ev[2]["ratio_text"]), (None, None), "vendor ghi 0 → None")


class LensTests(FixtureCase):
    def test_cong_prefers_newest_and_warns(self):
        c = D.cong()
        self.assertTrue(c["text"].startswith("CỔNG: [CẦN DATA — test]"))
        self.assertEqual(c["src"], "lk_thitruong.cong")
        self.assertTrue(c["stop"])
        self.assertTrue(any("lệch" in w for w in D.warnings()))

    def test_cong_stale(self):
        with mock.patch.dict(os.environ, {"CHB_TODAY": "2026-10-10"}):
            c = D.cong()
        self.assertIn("[CẦN DATA — fft_langkinh cũ/thiếu]", c["text"])

    def test_pattern_suffix_outside_tv30(self):
        self.assertEqual(D.tv30(), ["AAA"])
        self.assertEqual(D.pattern_label("AAA", "Pattern B"), "Pattern B")
        self.assertEqual(D.pattern_label("BBB", "Pattern A"), "Pattern A?")
        self.assertEqual(D.patterns("BBB").value[0]["label"], "Mũ sắt?")
        lv = D.lk_view("AAA")
        self.assertTrue(lv["fft_hai_cua_so"])                 # |lech| ≥ 25 → nêu cả hai cửa sổ
        self.assertEqual(lv["chu_the"].value, "cần")
        self.assertEqual(lv["codong"].value[1]["kieu"], "chep")
        self.assertTrue(lv["codong"].value[1]["cf"])
        self.assertTrue(D.codong_moc("BBB").can)

    def test_basket_uses_vnstore_not_bang_vn30(self):
        b = D.basket("VN30")
        self.assertEqual(b.value, ["AAA"])
        self.assertIn("bang_vn30.json lệch", b.note)
        self.assertEqual(D.basket("VN100").value, ["AAA", "BBB"])

    def test_ecosystems_both_schemas(self):
        e = D.ecosystems()
        self.assertEqual(e["groups"]["Other"]["tickers"], ["BBB"])
        self.assertIn("AAA", e["note"])                        # trùng chủ sở hữu trong top-5
        self.assertEqual(D.groups_of("BBB"), ["Alpha", "Other"])


class StoreTests(FixtureCase):
    def test_facts_index(self):
        ix = D.facts_index()
        self.assertEqual(sorted(ix["by_id"]), ["F1-001", "F1-002", "F2-001"])
        self.assertEqual(ix["by_ma"]["AAA"], ["F1-001", "F1-002", "F2-001"])
        self.assertEqual([r["id"] for r in D.facts_for(loai="claim")], ["F1-002"])

    def test_facts_normalized_fields_and_src_lookup(self):
        ix = D.facts_index()["by_id"]
        a, b, c = ix["F1-001"], ix["F1-002"], ix["F2-001"]
        self.assertEqual(a["src_lines"], [[102, 102], [250, 251]], "L1+L2 của Synthesis không phải dòng SRC")
        self.assertEqual(a["src_blocks"], ["FLOW.AAA"])
        self.assertEqual(a["so_lieu_list"], [{"ten": "gia", "text": "1 đ"}, {"ten": "n", "gia_tri": 5}])
        self.assertEqual((a["nguon_list"], a["trang_thai"]), (["vc_lk"], None))
        self.assertEqual((b["src_lines"], b["so_lieu_list"], b["nguon_list"]), ([], [], []))
        self.assertEqual(c["src_lines"], [[804, 804], [5353, 5353], [5360, 5360]])
        self.assertEqual((c["src_blocks"], c["trang_thai"]), (["CLAIMS_54.C09"], "KHÔNG ÁP DỤNG"))
        self.assertEqual(c["so_lieu_list"], [{"ten": "x", "gia_tri": 1}])
        self.assertEqual(c["nguon"], ["a", "b"], "trường gốc giữ nguyên")
        self.assertEqual([r["id"] for r in D.facts_for_src(100, 110)], ["F1-001"])
        self.assertEqual([r["id"] for r in D.facts_for_src(251)], ["F1-001"])
        self.assertEqual([r["id"] for r in D.facts_for_src(block="CLAIMS_54")], ["F2-001"])
        self.assertEqual(D.facts_for_src(block="CLAIMS"), [], "tiền tố theo từng đoạn chấm")
        self.assertEqual(D.facts_for_src(), [])

    def test_dossier_merges_fragments_and_drops_unsourced(self):
        d = D.dossier()
        self.assertEqual(d["_meta"]["date"], "2026-09-27")
        self.assertTrue(d["_meta"]["merged_parts"])
        self.assertEqual(d["_meta"]["dropped"], 2)
        self.assertEqual(list(d["overview"]), ["p1"])
        self.assertEqual(len(d["catalyst"]), 1)
        self.assertEqual(d["claims20"]["C01"]["status"], "BỊ BÁC")

    def test_portfolio_two_books_and_conflicts(self):
        pc = D.portfolio_current()
        a, b = pc["lk_khoi11_1009"], pc["hdcv_1209"]
        self.assertEqual((a["date"], b["date"]), ("2026-09-10", "2026-09-12"))
        self.assertEqual(a["tong_text"], "28% verified + 3% UNVERIFIED")
        self.assertEqual((a["cash"], a["unexplained"], b["cash"]), (15.0, 16.0, 16.0))
        ksv = next(x for x in a["positions"] if x["tk"] == "KSV")
        self.assertEqual(ksv["v"].tier, D.UNV)
        kinds = {(c["loai"], c["tk"]) for c in pc["conflicts"]}
        for k in (("nav", "VCB"), ("nav", "MSN"), ("chi_mot_ban", "KSV"), ("cash", None), ("watch_vs_avoid", "STB"),
                  ("avoid", "DGC")):
            self.assertIn(k, kinds)
        self.assertEqual(a["actions"][0], {"tk": "VCB", "tu": 8.0, "den": 5.0})

    def test_portfolio_fallback_to_fft_cauhinh(self):
        with mock.patch.dict(os.environ, {"CHB_SKILLS_DIR": str(self.tmp / "nope")}):
            pc = D.portfolio_current()
        a = pc["lk_khoi11_1009"]
        self.assertEqual(a["date"], "2026-09-21")
        self.assertEqual(a["tong_text"], "28% verified + 3% UNVERIFIED")
        self.assertEqual(pc["hdcv_1209"]["positions"], [])

    def test_v21_present(self):
        self.assertEqual(D.v21_get("ACTION_PORT_25"), [{"tk": "AAA"}])
        self.assertEqual(D.portfolio_v21()["PORTFOLIO_ACTION"]["current"][0]["tk"], "AAA")

    def test_audit_and_status(self):
        a = D.source_audit("chaebol_map")
        self.assertEqual([r["id"] for r in a["tai_san"]], ["vc_lk_meta"])
        self.assertEqual((a["tai_san"][0]["sla_gio"], a["tai_san"][0]["sla_cuoi_tuan"]), (24, 72))
        self.assertEqual(len(a["van_de"]), 1)
        st = D.vc_lk_status()["endpoints"]
        self.assertEqual((st["price-history"]["min_du_lieu_toi"], st["price-history"]["max_du_lieu_toi"]),
                         ("2026-09-22", "2026-09-25"))
        self.assertEqual(len(st["events-v1"]["loi"]), 1)
        self.assertEqual(D.vnstore_status()["nen_ngay_max"], "2026-09-25")

    def test_usd_vnd_kinds_and_fallback(self):
        v = D.usd_vnd()
        self.assertEqual((v.value, v.tier, v.asof), (26180.0, D.T2, "2026-09-25"))
        self.assertIn("giá bán NHTM", v.note)
        self.assertEqual(D.usd_vnd("trung_tam").value, 25641.0)
        (self.tmp / "liquidity_daily" / "output" / "latest.json").unlink()
        D.clear_cache()
        self.assertEqual(D.usd_vnd("nhtm_ban").value, 26170.0)
        self.assertEqual(D.usd_vnd("trung_tam").value, 25641.0)
        self.assertTrue(D.usd_vnd("tu_do").can)


class NoV21Tests(FixtureCase):
    with_v21 = False

    def test_missing_v21_is_empty_with_warning(self):
        self.assertEqual(D.v21(), {})
        self.assertTrue(any("v21_const.json" in w for w in D.warnings()))
        self.assertEqual([r["src"] for r in D.index_weekly_spliced("VNINDEX").value], ["live"] * 3)


class CliAndInterpreterTests(FixtureCase):
    PRELUDE = ("import socket, sys\n"
               "_pre = set(sys.modules)\n"
               "def _d(*a, **k): raise RuntimeError('mạng bị chặn')\n"
               "socket.socket = socket.create_connection = socket.getaddrinfo = _d\n"
               f"sys.path.insert(0, {str(HERE)!r})\n"
               "import json, chaebol_map_data as D\n")
    PROBE = ("out = D.to_jsonable([D.last_price('AAA')['raw'].value, D.adj_factor('AAA', '2026-09-10').value,"
             " [r['label'] for r in D.weekly_ohlcv('AAA').value], D.cong()['text'], D.basket('VN30').value,"
             " D.portfolio_current()['lk_khoi11_1009']['tong_text']])\n"
             "assert not {'urllib.request', 'http.client', 'ssl'} & (set(sys.modules) - _pre), 'module mạng bị nạp'\n"
             "print(json.dumps(out, ensure_ascii=False))\n")

    def _run(self, py: str) -> list:
        env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
        env.update(self.env)
        r = subprocess.run([py, "-c", self.PRELUDE + self.PROBE], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_other_interpreters(self):
        here = json.loads(json.dumps(D.to_jsonable([
            D.last_price("AAA")["raw"].value, D.adj_factor("AAA", "2026-09-10").value,
            [r["label"] for r in D.weekly_ohlcv("AAA").value], D.cong()["text"], D.basket("VN30").value,
            D.portfolio_current()["lk_khoi11_1009"]["tong_text"]]), ensure_ascii=False))
        pys = [p for p in (str(VENV_PY), shutil.which("python3")) if p and Path(p).exists()]
        ran = 0
        for py in pys:
            if Path(py).resolve() == Path(sys.executable).resolve():
                continue
            self.assertEqual(self._run(py), here, py)
            ran += 1
        if not ran:
            self.skipTest("không tìm thấy trình thông dịch thứ hai")

    def test_demo_cli(self):
        env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
        env.update(self.env)
        r = subprocess.run([sys.executable, str(HERE / "chaebol_map_data.py"), "demo", "AAA"], capture_output=True,
                           text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["AAA"]["last_price"]["raw"]["tier"], "FACT-T2")
        self.assertTrue(out["cong"]["text"].startswith("CỔNG:"))


@unittest.skipUnless((REAL_SYS / "fincept_bridge" / "state" / "vc_lk" / "VIC" / "price-history.json").exists(),
                     "không có kho thật")
class RealStoreSmoke(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if k not in ENV_KEYS}, clear=True)
        self._env.start()
        D.clear_cache()

    def tearDown(self):
        self._env.stop()
        D.clear_cache()

    def test_perf_50_tickers(self):
        t0 = time.time()
        tks = list(D.basket("VN30").value or []) + ["VPL", "MSR", "NVL", "GEX", "GEE", "GEL", "VIX", "VCI", "DGC", "PC1",
                                                   "CTD", "EIB", "VGC", "THD", "BCM", "PLX", "TPB", "HCM", "GMD", "KSV"]
        self.assertGreaterEqual(len(tks), 50)
        for tk in tks[:50]:
            D.last_price(tk), D.shares_out(tk), D.market_cap(tk), D.hi_lo_52w(tk), D.pct_change(tk, "2026-05-08")
            D.flow4(tk, 60), D.vwap_cluster(tk), D.weekly_v21(tk, "2024-04-29"), D.top_holders(tk), D.lk_view(tk)
            D.insider_tx(tk, "2026-05-12"), D.relationships(tk), D.details(tk), D.capital_events(tk, "2026-05-12")
        self.assertLess(time.time() - t0, 5.0)

    def test_market_level(self):
        self.assertTrue(D.cong()["text"].startswith("CỔNG:"))
        vn30 = D.basket("VN30").value
        self.assertEqual(len(vn30), 30)
        lp = D.last_price("VIC")
        self.assertEqual(lp["raw"].tier, D.T2)
        self.assertGreater(lp["raw"].value, 0)
        self.assertGreaterEqual(len(D.cross_holdings()["owners"]), 20)
        e = D.index_extremes("VNINDEX", "2026-05-08")
        self.assertEqual((e["start"].value, e["peak"].asof), (1915.37, "2026-05-18"))

    def test_weekly_td_matches_v21(self):
        wk = (D.v21_get("WEEKLY_OHLCV") or {}).get("MSN")
        if not wk:
            self.skipTest("v21_const.json chưa có WEEKLY_OHLCV")
        live = {r[0]: r for r in D.weekly_v21("MSN").value}
        pairs = [(r[5], live[r[0]][5]) for r in wk[:-2] if r[0] in live]
        ok = sum(1 for a, b in pairs if abs(a - (b or 0)) <= 0.0015)
        self.assertGreaterEqual(ok / len(pairs), 0.95)

    def test_spliced_vnindex(self):
        sp = D.index_weekly_spliced("VNINDEX")
        if not D.v21_get("INDEX_DATA"):
            self.skipTest("v21_const.json chưa có INDEX_DATA")
        first_live = next(r for r in sp.value if r["src"] == "live")
        self.assertEqual((first_live["date"], first_live["c"], first_live["chg"]), ("2026-05-15", 1921.6, 0.325))

    def test_msn_share_count_conflict_noted(self):
        self.assertIn("NGUỒN LỆCH", D.shares_out("MSN").note or "")

    def test_portfolio_real(self):
        pc = D.portfolio_current()
        if not pc["lk_khoi11_1009"]["positions"] or not pc["hdcv_1209"]["positions"]:
            self.skipTest("không đọc được skill danh mục")
        kinds = {(c["loai"], c["tk"]) for c in pc["conflicts"]}
        self.assertIn(("nav", "VCB"), kinds)
        self.assertIn(("cash", None), kinds)


if __name__ == "__main__":
    unittest.main(verbosity=1)
