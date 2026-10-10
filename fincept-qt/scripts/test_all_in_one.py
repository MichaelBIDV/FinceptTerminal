#!/usr/bin/env python3
"""Test hợp đồng aio/1 của scripts/all_in_one.py (chạy trên dữ liệu thật của máy, chỉ đọc).

    python3 -m pytest scripts/test_all_in_one.py -q
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import all_in_one as aio  # noqa: E402

KIEU = {"cong", "doan", "o_so", "bang", "the", "danh_sach", "trich", "bieu_do", "canh_bao", "chips"}
TRANG_THAI = {"du", "cu", "thieu"}


def run_cli(*args):
    t0 = time.time()
    r = subprocess.run([sys.executable, str(HERE / "all_in_one.py"), *args], capture_output=True, timeout=120)
    assert r.returncode == 0, r.stderr.decode()
    return json.loads(r.stdout.decode("utf-8")), time.time() - t0


def check_blocks(blocks):
    for b in blocks:
        assert isinstance(b, dict) and b.get("kieu") in KIEU, b
        if b["kieu"] == "bieu_do" and b["block"].get("loai") == "cot":
            blk = b["block"]
            for s in blk["series"]:
                assert len(s["y"]) == len(blk["nhan"])
        elif b["kieu"] == "bieu_do":
            blk = b["block"]
            n = len(blk["x"])
            assert n > 1
            for s in blk["series"]:
                for key in ("y", "y_lo", "y_hi"):
                    if key in s:
                        assert len(s[key]) == n, (b["tieu_de"], s["name"], key)
        if b["kieu"] == "bang":
            w = len(b["cot"])
            for row in b["dong"]:
                assert len(row) == w, (b.get("chu_thich"), row)


def check_payload(p):
    assert "error" not in p, p.get("error")
    meta = p["meta"]
    assert meta["ro"] in ("VN30", "VN100", "VN200", "CHAEBOL")
    assert len(meta["ds_ma"]) >= 220, "ô gợi ý phải có hợp VN200 ∪ Chaebol MAP (~229 mã)"
    nhom = p["bang"]["nhom"]
    assert nhom and all(g["nhan"] and g["ma"] for g in nhom)
    chips = [c["ma"] for g in nhom for c in g["ma"]]
    assert len(chips) == len(set(chips)), "một mã chỉ hiện ở một nhóm chip"
    assert p["cong"]["kieu"] == "cong"
    for o in p["o"]:
        assert o["id"] and o["tieu_de"]
        assert 1 <= o["cot"] <= 12
        assert o["trang_thai"] in TRANG_THAI
        check_blocks(o["khoi"])


def test_board_vn30():
    p, dt = run_cli("bang", "--ro", "VN30")
    check_payload(p)
    assert p["meta"]["ma"] == ""
    assert p["csv"]["rows"] and len(p["csv"]["rows"]) == 30
    assert dt < 20


def test_board_vn100():
    p, _ = run_cli("bang", "--ro", "VN100")
    check_payload(p)
    assert len(p["csv"]["rows"]) >= 95


def test_board_vn200_is_lang_kinh_universe():
    p, dt = run_cli("bang", "--ro", "VN200")
    check_payload(p)
    vt = json.loads((aio.BRIDGE / "lk_vutru.json").read_text(encoding="utf-8"))["ma"]
    vn100 = json.loads((aio.KOS / "hhp_basket_members.json").read_text(encoding="utf-8"))["members"]["VN100"]
    rows = {r[0] for r in p["csv"]["rows"]}
    assert rows == set(vt) | set(vn100), "VN200 = lk_vutru.json (bộ Lăng Kính) ∪ VN100"
    assert [g["nhan"].split(" (")[0] for g in p["bang"]["nhom"]][-1].startswith("VN101")
    assert dt < 20


def test_board_chaebol_matches_chaebol_map():
    import chaebol_map_data_vciq as V
    p, dt = run_cli("bang", "--ro", "CHAEBOL")
    check_payload(p)
    v21 = json.loads((aio.BRIDGE / "data" / "chaebol_map" / "v21_const.json").read_text(encoding="utf-8"))
    vn30 = json.loads((aio.KOS / "hhp_basket_members.json").read_text(encoding="utf-8"))["members"]["VN30"]
    want = set(V.universe(v21, vn30))
    assert {r[0] for r in p["csv"]["rows"]} == want
    chips = {c["ma"] for g in p["bang"]["nhom"] for c in g["ma"]}
    assert chips == want
    nhan = [g["nhan"] for g in p["bang"]["nhom"]]
    assert nhan[0].startswith("NHÓM TUẤN MƯỢT") and any(n.startswith("VINGROUP") for n in nhan)
    assert dt < 20


@pytest.mark.parametrize("ma,ro", [("DHG", "VN200"), ("SHS", "VN200"), ("NET", "CHAEBOL"), ("BHI", "CHAEBOL")])
def test_outside_vn100(ma, ro):
    p, _ = run_cli("ma", "--ma", ma)
    check_payload(p)
    assert p["meta"]["ma"] == ma and p["meta"]["ro"] == ro
    ho_so = next(o for o in p["o"] if o["id"] == "ho_so")
    assert ho_so["trang_thai"] != "thieu"


@pytest.mark.parametrize("ma", ["MSN", "HPG", "VCB", "FPT"])
def test_ticker_workspace(ma):
    p, dt = run_cli("ma", "--ma", ma)
    check_payload(p)
    assert p["meta"]["ma"] == ma
    ids = [o["id"] for o in p["o"]]
    for need in ("ho_so", "gia", "dinh_gia", "kqkd", "pe_tv", "co_dong", "fft", "noi_bo", "deepfa", "hoi_dong", "research", "tin", "nguon"):
        assert need in ids, (ma, need, ids)
    assert len(json.dumps(p, ensure_ascii=False)) < 2_500_000
    assert dt < 20, f"{ma} gom mất {dt:.1f}s"


def test_msn_has_reflex_tile():
    p, _ = run_cli("ma", "--ma", "MSN")
    assert "reflex" in [o["id"] for o in p["o"]]


def test_chaebol_reflex_tile_for_ecosystem_members():
    # Chaebol Reflex (07/10/2026): every ticker of the 32-group registry gets the "reflex" tile, opening tab msn_reflex
    for ma in ("VIC", "GEE"):
        p, _ = run_cli("ma", "--ma", ma)
        tiles = [o for o in p["o"] if o["id"] == "reflex"]
        assert len(tiles) == 1, ma
        t = tiles[0]
        assert t["tab"] == "msn_reflex" and t["tab_nhan"] == "Chaebol Reflex", ma
        assert t["khoi"], ma


def test_unknown_ticker_is_error_json():
    p, _ = run_cli("ma", "--ma", "ZZZ")
    assert p.get("error_code") == "NO_TICKER"


def test_bad_command_is_error_json():
    p, _ = run_cli("xyz")
    assert p.get("error_code") == "USAGE"


def test_vn_number_format():
    assert aio.vn(1234567.891, 1) == "1.234.567,9"
    assert aio.vn(-0.5, 2) == "−0,50"
    assert aio.vn(None) == ""
    assert aio.vn(3, 0, sign=True) == "+3"


@pytest.mark.parametrize("ma,ro,want", [("ANV", "VN30", "VN30"), ("ACV", "VN30", "VN200"), ("AST", "VN30", "CHAEBOL"),
                                         ("VCB", "CHAEBOL", "CHAEBOL"), ("DHG", "CHAEBOL", "VN200")])
def test_ro_choice_keeps_board_when_chip_is_on_it(ma, ro, want):
    p, _ = run_cli("ma", "--ma", ma, "--ro", ro)
    assert p["meta"]["ro"] == want
    assert ma in {c["ma"] for g in p["bang"]["nhom"] for c in g["ma"]}


def test_no_false_pre_ex_flag_on_upcom_noise():
    import all_in_one_ma  # noqa: F401
    U, _, _, san = aio.load_universe()
    q = aio.load_quotes(["MML", "MSR", "NET"], san)
    assert not q["MML"].get("truoc_gdkhq") and not q["MSR"].get("truoc_gdkhq")
    assert q["NET"].get("truoc_gdkhq"), "NET (đc/thô 0,9015 suốt 29/09→02/10) phải còn bị gắn cờ"


def test_no_bare_separators_in_tiles():
    for ma in ("VGI", "SHS", "BHI", "NET"):
        p, _ = run_cli("ma", "--ma", ma)
        for o in p["o"]:
            for b in o["khoi"]:
                if b["kieu"] == "o_so":
                    for t in b["o"]:
                        assert t["gia_tri"].strip(" /·") != "", (ma, o["id"], t["nhan"], t["gia_tri"])
                        assert "  " not in t["phu"] and "room còn  cp" not in t["phu"], (ma, o["id"], t["phu"])


# ───────────── lượt 4 (10/10/2026): sổ lệnh gom/xả, Chaebol chart, HHP đầy đủ, ERP, pha EPS × P/E, Soros ─────────────

def _ann_ok(blocks):
    for b in blocks:
        if b["kieu"] != "bieu_do" or b["block"].get("loai"):
            continue
        for a in b["block"].get("annotations") or []:
            if a["kind"] in ("point", "vline"):
                assert isinstance(a["x"], (int, float)), (b["tieu_de"], a)
            if a["kind"] in ("point",):
                assert isinstance(a["y"], (int, float)), (b["tieu_de"], a)
            assert a.get("mau", "dim") in {"bull", "bear", "warn", "info", "amber", "cyan", "dim"}, a


@pytest.mark.parametrize("ro", ["VN30", "VN100", "VN200"])
def test_board_starts_with_order_book_ranking(ro):
    p, dt = run_cli("bang", "--ro", ro)
    check_payload(p)
    ids = [o["id"] for o in p["o"]]
    assert ids[0] == "sl_xep_hang" and ids.index("tom_tat") > 0, ids
    first = p["o"][0]
    tb = next(b for b in first["khoi"] if b["kieu"] == "bang")
    assert tb["cot"][:3] == ["Mã", "Nghiêng", "Phiên SL"] and "Pct VN200" in tb["cot"]
    assert {r[1]["t"].rstrip("?") for r in tb["dong"]} <= {"GOM", "XẢ", "CÂN"}
    import all_in_one_solenh as SL
    for r in tb["dong"]:   # mã ngoài 30 mã Toàn Vũ: nhãn nghiêng mang hậu tố "?" (CLAUDE.md §6 luật 4)
        if r[1]["t"] != "CÂN":
            assert r[1]["t"].endswith("?") == (r[0]["t"] not in SL.tv30()), r[:2]
    minis = [o for o in p["o"] if o["id"].startswith("sl_") and o["id"] not in ("sl_xep_hang", "sl_v5")]
    assert len(minis) == 6
    for o in p["o"]:
        _ann_ok(o["khoi"])
    assert dt < 20


def test_chaebol_board_has_no_order_book_ranking():
    p, _ = run_cli("bang", "--ro", "CHAEBOL")
    assert not any(o["id"].startswith("sl_") for o in p["o"])


@pytest.mark.parametrize("ma", ["MSN", "HPG", "VCB", "DHG"])
def test_ticker_round4_tiles(ma):
    p, dt = run_cli("ma", "--ma", ma)
    check_payload(p)
    by = {o["id"]: o for o in p["o"]}
    for need in ("chaebol_chart", "hhp_full", "pe_erp", "pe_pha_gia", "pe_pha_tach", "pe_pha_bang", "soros", "solenh"):
        assert need in by and by[need]["trang_thai"] != "thieu", (ma, need, by.get(need, {}).get("ghi_chu"))
    assert by["chaebol_chart"]["tab"] == "chaebol_map" and by["hhp_full"]["tab"] == "hhp_valuation"
    assert by["pe_erp"]["tab"] == "toanvu_pe"
    # chart giá của ô gia / dinh_gia nhường chỗ cho Chaebol chart / HHP đầy đủ (không vẽ trùng)
    assert not any(b["kieu"] == "bieu_do" for b in by["gia"]["khoi"])
    assert not any(b["kieu"] == "bieu_do" for b in by["dinh_gia"]["khoi"])
    for o in p["o"]:
        _ann_ok(o["khoi"])
    assert dt < 20


def test_ticker_outside_bloomberg_keeps_page():
    p, _ = run_cli("ma", "--ma", "SHS")
    check_payload(p)
    by = {o["id"]: o for o in p["o"]}
    assert by["pe_erp"]["trang_thai"] == "thieu" and "[CẦN DATA]" in by["pe_erp"]["ghi_chu"]
    assert by["chaebol_chart"]["trang_thai"] != "thieu" and by["solenh"]["trang_thai"] != "thieu"


def test_soros_never_assigns_a_stage():
    p, _ = run_cli("ma", "--ma", "HPG")
    s = next(o for o in p["o"] if o["id"] == "soros")
    txt = json.dumps(s, ensure_ascii=False)
    assert "Không gán mã vào pha nào" in txt
    sig = next(b for b in s["khoi"] if b["kieu"] == "bang" and b["cot"][0] == "Dấu hiệu")
    assert [r[0]["t"] for r in sig["dong"]] == ["S1", "S3", "S5", "S6"]


def test_msn_reflex_extended_tiles():
    p, _ = run_cli("ma", "--ma", "MSN")
    ids = [o["id"] for o in p["o"]]
    assert "reflex_quy_ve_100" in ids and "reflex_keynotes" in ids
    soros = next(o for o in p["o"] if o["id"] == "soros")
    assert "ĐÓNG BĂNG" in json.dumps(soros, ensure_ascii=False), "phụ lục mp_soros của MSN phải mang nhãn ĐÓNG BĂNG"


def _row(d, o, h, l, c, v, pc_row=None, buy=1000, sell=1000):
    return {"tradingDate": d, "openPrice": o, "closePrice": c, "closePriceAdjusted": c, "highestPriceAdjusted": h,
            "lowestPriceAdjusted": l, "totalMatchVolume": v, "averageBuyTradeVolume": buy, "averageSellTradeVolume": sell}


def _base(n=20, px=100.0, v=1000):
    return [_row(f"2026-08-{i + 1:02d}", px, px + 1, px - 1, px, v) for i in range(n)]


@pytest.mark.parametrize("bar,want", [
    (("2026-09-01", 100, 101, 90, 99, 1000), "N5"),          # rút chân dài > 60%, đáy ≤ −2%
    (("2026-09-01", 100, 100.2, 97.0, 97.2, 1000), "N3"),    # đỏ đặc, đóng sát đáy, −2,8%
    (("2026-09-01", 102, 103, 98, 98.3, 1500), "N6"),        # mở gap lên, đóng sát đáy, KL 1,5×
    (("2026-09-01", 100, 100.8, 99.5, 100.5, 500), "CB"),    # chạm đỉnh 20 phiên, KL 0,5×
    (("2026-09-01", 100, 101, 99, 100, 6000), "BV"),         # KL ≥ 5× TB20
])
def test_candle_rules(bar, want):
    import all_in_one_solenh as SL
    rows = _base() + [_row(*bar)]
    assert want in SL._mau(rows, len(rows) - 1), (want, SL._mau(rows, len(rows) - 1))


def test_hs2_classes_and_distribution_streak():
    import all_in_one_solenh as SL
    rows = _base()
    sells = [700, 1600, 1600, 1600, 1600, 1000]
    rows += [_row(f"2026-09-{i + 1:02d}", 100, 101, 99, 100, 1000, sell=s) for i, s in enumerate(sells)]
    st = SL.thong_ke(SL.tinh_ma("X", rows), [r["tradingDate"] for r in rows[-6:]])
    assert (st["gom"], st["xa"], st["chuoi_xa"], st["n"]) == (1, 4, 4, 6)
    assert "".join(st["o"][r["tradingDate"]] for r in rows[-6:]) == "GXXXX·"


def _x_ms(v):
    import all_in_one_solenh as SL
    return v if isinstance(v, (int, float)) else SL._ms(v)


@pytest.mark.parametrize("ma", ["MSN", "HPG", "BVB"])
def test_round4_annotations_inside_x_range_and_no_long_dash(ma):
    p, _ = run_cli("ma", "--ma", ma)
    raw = json.dumps(p, ensure_ascii=False)
    assert "\u2014" not in raw and "\u2015" not in raw
    for o in p["o"]:
        if o["id"] not in ("chaebol_chart", "hhp_full", "soros", "solenh", "pe_erp", "pe_pha_gia"):
            continue
        for b in o["khoi"]:
            if b["kieu"] != "bieu_do" or b["block"].get("loai"):
                continue
            xs = [_x_ms(x) for x in b["block"]["x"]]
            lo, hi = min(xs), max(xs)
            for a in b["block"].get("annotations") or []:
                if a["kind"] in ("point", "vline"):
                    assert lo <= a["x"] <= hi, (ma, o["id"], b["tieu_de"], a.get("text"))


def test_ticker_order_book_tile_matches_board_row():
    pb, _ = run_cli("bang", "--ro", "VN30")
    row = next(r for r in next(b for b in pb["o"][0]["khoi"] if b["kieu"] == "bang")["dong"] if r[0]["t"] == "MSN")
    pm, _ = run_cli("ma", "--ma", "MSN")
    t = next(o for o in pm["o"] if o["id"] == "solenh")
    gx = next(b for b in t["khoi"] if b["kieu"] == "o_so")["o"][0]["gia_tri"]
    assert gx == f"{row[3]['t']} / {row[4]['t']}", (gx, [c["t"] for c in row[:8]])


def test_bvb_empty_pe_series_is_thieu():
    p, _ = run_cli("ma", "--ma", "BVB")
    by = {o["id"]: o for o in p["o"]}
    assert by["pe_tv"]["trang_thai"] == "thieu" and by["pe_erp"]["trang_thai"] == "thieu"
