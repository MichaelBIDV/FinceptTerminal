#!/usr/bin/env python3
"""
Tests for hhp_valuation.py (ĐỊNH GIÁ HHP data service). Stdlib unittest only.

    cd fincept-qt/scripts && python3 -m unittest test_hhp_valuation -v

Most tests run the script as a subprocess against a tiny synthetic data dir (HHP_DATA_DIR),
exactly as EconomicsService/PythonRunner would, and parse stdout strictly (NaN/Infinity
tokens rejected). LiveDataTest runs against the real knowledge_os dir when it exists.
"""

import copy
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "hhp_valuation.py")
sys.path.insert(0, HERE)

import hhp_valuation as hv  # noqa: E402

NAN = float("nan")
REAL_DIR = hv.DEFAULT_DATA_DIR

CHEAP, NEUTRAL, RICH = "RẺ (<−1σ)", "TRUNG TÍNH", "ĐẮT (>+1σ)"


def _reject_constant(token):
    raise ValueError("non-finite JSON token on stdout: " + token)


def run_script(args, data_dir):
    """Run the script like the app does → (returncode, parsed object, raw stdout text)."""
    env = dict(os.environ, HHP_DATA_DIR=data_dir)
    proc = subprocess.run([sys.executable, SCRIPT] + list(args), capture_output=True, env=env, timeout=60)
    text = proc.stdout.decode("utf-8")
    return proc.returncode, json.loads(text, parse_constant=_reject_constant), text


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)  # allow_nan=True → literal NaN, like upstream files


def metric(zone, sigma, now=10.0):
    return {"now": now, "mean": 12.0, "sd": 2.0, "min": 5.0, "max": 20.0, "sigma": sigma, "zone": zone, "n": 900,
            "reliable": True, "band_cheap2": 8000, "band_cheap1": 10000, "band_fair": 12000, "band_rich1": 14000,
            "band_rich2": 16000, "upside_to_fair_pct": 20.0}


def entry(pe, pb, price=10000, **extra):
    return {"sector": None, "price_now": price, "eps": 1000.0, "bvps": 8000.0, "quality_val": "1", "fa_rec": "MUA",
            "fa_tp": 12000, "fa_catalyst": None, "forward": None, "pe": pe, "pb": pb,
            "links": {"vietcap_iq": "https://example.invalid/iq", "miquant": "https://example.invalid/mq",
                      "simplize": "https://example.invalid/sz"}, **extra}


# New-schema price / CapIQ fields (hhp_vn100_valuation.json after the Vietcap-price + fresh-CapIQ rebuild).
PRICES_META = {"source": "vnstore vn_store.db (Vietcap vci_board / vci_history)", "as_of": "2026-01-02",
               "n_vietcap": 3, "n_fallback": 2, "fallback": ["EEE", "DDD"]}
CAPIQ_META = {"file": "SPGlobal_Export_1-2-2026.xlsx", "exported": "2026-01-02 07:51 AM ET",
              "exported_date": "2026-01-02", "n": 4, "n_pe": 3, "source_dir": "Downloads"}
CAPIQ_AAA = {"pe": 9.1, "pb": 1.3, "tp": 13000.0, "tp_med": 12800.0, "tp_high": 15000.0, "tp_low": 11000.0,
             "tp_date": "2025-12-20", "n_tp": 7, "rec": "Outperform", "n_rec": 8, "upside_pct": 30.0,
             "eps_est": 1100.0, "bvps_est": 8600.0, "roe_est": 13.2, "eps_growth_1y": 10.0, "last_price": 9950.0,
             "exported": "2026-01-02"}
CAPIQ_BBB = {"pe": None, "pb": 1.1, "tp": None, "tp_med": None, "tp_high": None, "tp_low": None, "tp_date": None,
             "n_tp": None, "rec": "Hold", "n_rec": 2, "upside_pct": None, "eps_est": None, "bvps_est": 9000.0,
             "roe_est": None, "eps_growth_1y": None, "last_price": None, "exported": "2026-01-02"}
PRICE_KEYS = ("price_date", "price_time", "price_src", "eps_src", "capiq")
# CIQ-overlay rebuild (ciq_feed/hhp_ciq_overlay.json): current multiples under capiq.ttm, one stamp per screen.
CAPIQ_SCREENS_META = {
    "source": "ciq_feed/hhp_ciq_overlay.json", "updated_at": "2026-01-02T19:05:00+07:00",
    "screens": {"estimates": {"exported_ict": "2026-01-02T19:51:15+07:00", "n": 4, "file": "Estimates.xls"},
                "key_stats": {"exported_ict": "2026-01-01T20:10:00+07:00", "n": 3, "file": "Key Stats.xls"}}}
CAPIQ_TTM = {"pe": 10.4, "pb": 1.25, "pe_ttm_est": 10.9, "pb_fy0bv_est": 1.31, "eps_ltm": 917.0, "bvps_ltm": 7630.0,
             "roe_fy0": 12.1, "div_yield": 2.4, "mcap_b": 1234.5, "tev_b": 1500.0, "ev_ebitda_fwd": 8.2,
             "rev_g_ltm": -3.5, "npm_ltm": 11.0, "asof": {"key_stats": "2026-01-01", "estimates": "2026-01-02"}}


def price_fields(src, date="2026-01-02", time_=None, capiq=None):
    return {"price_date": date, "price_time": time_, "price_src": src, "eps_src": "implied", "capiq": capiq}


def basket_metric(zone, sigma):
    return {"series": [[1000, 10.0], [2000, 11.0]], "mean": 10.5, "p1": 11.0, "p2": 11.5, "m1": 10.0, "m2": 9.5,
            "now": 11.0, "sigma": sigma, "zone": zone, "as_of": "2026-01-02"}


# Series AAA/pe: prices and bases deliberately misaligned (different lengths, a ts only in price,
# a null base, a NaN price, a ts only in base, out-of-order price) → only ts 1000 and 4000 survive.
AAA_PE_MEAN, AAA_PE_SD = 10.337, 6.0


def utc_ms(y, m, d):
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp() * 1000)


# ── hhp_keynotes.json fixture (DESIGN §1.1). Hosts use the reserved .invalid TLD. ──
KN_SOURCES = [
    {"id": "s_vc", "org": "Vietcap", "title": "OHLC ngày VNINDEX", "date": "2026-01-02",
     "url": "https://trading.vc.invalid/ohlc", "type": "data", "tier": "FACT-T2"},
    {"id": "s_eng", "org": "Engine HHP", "title": "hhp_vn100_valuation.json", "date": "2026-01-02",
     "file": "hhp_vn100_valuation.json", "type": "data", "tier": "EST"},
    {"id": "s_hose", "org": "HOSE", "title": "Thông báo", "date": "2020-03-20", "url": "https://hose.invalid/tb",
     "type": "filing", "tier": "FACT-T1"},
    {"id": "s_news_a", "org": "Báo A", "title": "Tin A", "date": "2018-04-10", "url": "https://www.bao-a.invalid/a",
     "type": "news", "tier": "NEWS"},
    {"id": "s_news_b", "org": "Báo B", "title": "Tin B", "date": "2018-04-11", "url": "https://bao-b.invalid/b",
     "type": "news", "tier": "NEWS"},
    {"id": "s_news_a2", "org": "Báo A", "title": "Tin A (bài 2)", "date": "2018-04-12",
     "url": "https://other-host.invalid/a2", "type": "news", "tier": "NEWS"},
    {"id": "s_news_c", "org": "Báo C", "title": "Tin C (cùng tên miền Báo B)", "date": "2018-04-12",
     "url": "https://bao-b.invalid/c", "type": "news", "tier": "NEWS"},
    {"id": "s_nodate", "org": "Không ngày", "title": "x", "url": "https://nodate.invalid/x", "type": "news",
     "tier": "NEWS"},
]
CLOSE_NUM = {"k": "close", "scope": "VNINDEX", "v": 1204.33, "unit": "điểm", "asof": "2018-04-09", "src": "s_vc",
             "tier": "FACT-T2"}
PE_NUM = {"k": "pe", "scope": "VNINDEX", "v": 19.1, "unit": "x", "sigma": 2.1, "asof": "2018-04-09", "src": "s_eng",
          "tier": "EST", "method": "close × μ / fair (điểm engine ≤4 ngày)"}


def kn_event(kid, day, kind="dinh", **kw):
    ev = {"id": kid, "date": day, "kind": kind, "scopes": ["VNINDEX"], "title": "Tiêu đề " + kid, "boi_canh": "Bối cảnh",
          "nguyen_nhan": "Nguyên nhân", "key_factors": ["Yếu tố 1", "Yếu tố 2"], "sau_do": "Sau đó",
          "sources": ["s_news_a", "s_news_b"], "numbers": [dict(CLOSE_NUM, asof=day)], "tier": "NEWS"}
    ev.update(kw)
    return ev


def keynotes_fixture():
    """Three clean events, deliberately not in date order."""
    return {
        "meta": {"schema": "hhp_keynotes/1", "updated": "2026-01-02T10:00:00+07:00"},
        "sources": KN_SOURCES,
        "events": [
            kn_event("2020-03-day", "2020-03-24", kind="day", sources=["s_hose"], tier="FACT-T1",
                     detect={"score": 80.0, "provisional": False}),
            kn_event("2018-04-dinh", "2018-04-09", scopes=["vnindex", "VN100", "VNX50"], priority=1,
                     nhan_phu="margin + bank", numbers=[CLOSE_NUM, PE_NUM], detect={"score": 54.9},
                     claims=[{"text": "Margin bị siết", "src": ["s_news_a", "s_news_b"], "tier": "NEWS"}]),
            kn_event("2025-12-dinh", "2025-12-15", scopes=["VN30"], detect={"score": 10.0, "provisional": True}),
        ],
    }


# ── hhp_forecast.json fixture (schema hhp_forecast/1), anchored on the core/basket fixture below ──
FC_X = [3000, 4000, 5000, 6000]  # VNINDEX: first x = last x of index.pe.chart
FC_LAST = {"price": 3.0, "fair": 3.0, "cheap1": 2.6, "cheap2": 2.2, "rich1": 3.4, "rich2": 3.8}
BASKET_X = [2000, 3000, 4000]    # baskets: first x = last x of the basket series
BASKET_FLAT = {"mean": 10.5, "p1": 11.0, "p2": 11.5, "m1": 10.0, "m2": 9.5}


def fc_growth():
    return [
        {"year": 2026, "g": 0.25, "tier": "SS-T3/FACT-T2 (đồng thuận)", "est": False, "n": 2, "W": 2.0, "min": 0.2,
         "max": 0.3, "simple_median": 0.25, "flag": None,
         "sources": [{"id": "src_a", "org": "Org A", "value": 0.3, "weight": 1.0, "date": "2025-12-20",
                      "tier": "SS-T3", "url": "https://a.invalid/x"},
                     {"id": "ciq_bu", "org": "S&P Capital IQ", "value": 0.2, "weight": 1.0, "date": "2025-12-30",
                      "tier": "FACT-T2", "file": "Estimates.xls", "coverage_mcap_pct": 87.6, "n_tickers": 90}]},
        {"year": 2027, "g": 0.121, "tier": "EST", "est": True, "n": 0, "W": 0.0, "min": None, "max": None,
         "simple_median": None, "flag": "quy tắc dài hạn", "sources": []},
    ]


def index_fc_block():
    return {
        "growth": fc_growth(),
        "eps_pins": [{"year": 2025, "date": "2025-12-31", "ms": 2500, "value": 0.2, "tier": "EST",
                      "method": "EPS 4 quý tới Q4/2025 theo finfo (engine)"}],
        "base_path": [[x, round(0.2 * (1 + 0.1 * i), 4)] for i, x in enumerate(FC_X)],
        "points": {k: [[x, round(FC_LAST[k] * (1 + 0.1 * i), 4)] for i, x in enumerate(FC_X)]
                   for k in ("fair", "cheap1", "cheap2", "rich1", "rich2")},
        "milestones": [{"date": "2026-12-31", "ms": 5000, "base": 0.24, "fair": 3.6, "cheap1": 3.12, "cheap2": 2.64,
                        "rich1": 4.08, "rich2": 4.56}],
        "method": "EPS ghim theo năm tài chính", "caveats": ["Chỉ dải định giá dịch theo EPS — KHÔNG dự báo giá"],
    }


def basket_fc_block():
    return {"growth": fc_growth(), "ratio_path": [[x, round(11.0 / (1 + 0.1 * i), 2)] for i, x in enumerate(BASKET_X)],
            "flat": dict(BASKET_FLAT),
            "milestones": [{"date": "2026-12-31", "ms": 4000, "ratio": 9.17, "sigma": -2.66, "zone": CHEAP}],
            "method": "ratio(t) = R0·EPS0/EPS(t)", "caveats": ["Giá đứng yên"]}


def basket_anchor(pe=True, pb=True):
    lv = dict(BASKET_FLAT, now=11.0)
    return {"as_of": "2026-01-02", "ms": 2000, "pe": dict(lv) if pe else None, "pb": dict(lv) if pb else None}


def forecast_fixture():
    return {
        "meta": {"schema": "hhp_forecast/1", "generated": "2026-01-02 10:10 ICT", "horizon_months": 36,
                 "method": "trung vị có trọng số", "caveats": ["Tham khảo, không khuyến nghị"],
                 "inputs": {"engine": {"file": "hhp_vn100_valuation.json"}},
                 "warnings": ["2029: không nguồn nào → quy tắc dài hạn (EST)"]},
        "sources": [
            {"id": "src_a", "org": "Org A", "title": "Chiến lược 2026", "date": "2025-12-20", "url": "https://a.invalid/x",
             "tier": "SS-T3", "definition": "tăng trưởng LNST toàn thị trường"},
            {"id": "ciq_bu", "org": "S&P Capital IQ", "title": "Estimates export", "date": "2025-12-30",
             "file": "Estimates.xls", "tier": "FACT-T2"},
        ],
        "scopes": {
            "VNINDEX": {
                "anchor": {"as_of": "2026-01-02", "ms": 3000,
                           "pe": {"mean": 15.0, "sd": 2.0, "last": dict(FC_LAST)},
                           "pb": {"mean": 2.0, "sd": 0.4, "last": dict(FC_LAST)}},
                "pe": index_fc_block(),
                "pb": dict(index_fc_block(), retention={"r": 0.6, "per_year": []}),  # index.pb is null → dropped
                "targets": [
                    {"id": "t-2026-12", "horizon": "2026-12-31", "ms": 5000, "value": 4.0, "label": "12/26",
                     "members": [{"org": "Org A", "date": "2025-12-20", "value": 4.0, "scenario": "base",
                                  "url": "https://a.invalid/t", "tier": "SS-T3"}]},
                ],
            },
            "VN30": {"anchor": basket_anchor(), "pe": basket_fc_block(), "pb": basket_fc_block()},
            "VN100": {"anchor": basket_anchor(pb=False), "pe": basket_fc_block(), "pb": None},
            "VNINDEX_EXVIN3": {"pe": {"growth": fc_growth()}},
        },
    }


# ── hhp_forecast_tickers/<TK>.json fixture (schema hhp_forecast_ticker/1), anchored on the series fixture ──
# AAA/pe: the join keeps ts 1000 and 4000 → anchor = the last point (base 2.0, price 13.0);
# levels = max(0, round(2.0 × (μ + kσ), 2)) with μ 10.337, σ 6 → 20.674 / 8.674 / −1.326 / 32.674 / 44.674.
TK_X0 = 4000
AAA_PE_LAST = {"price": 13.0, "base": 2.0, "fair": 20.67, "cheap1": 8.67, "cheap2": 0.0, "rich1": 32.67, "rich2": 44.67}
BBB_PB_LAST = {"price": 10.0, "base": 4.0, "fair": 8.0, "cheap1": 6.0, "cheap2": 4.0, "rich1": 10.0, "rich2": 12.0}
TK_LEVELS = ("fair", "cheap1", "cheap2", "rich1", "rich2")
VC_TARGET = {"id": "vc-tp", "org": "Vietcap Research", "date": "2025-12-20", "horizon": "2026-12-20", "ms": 9000,
             "value": 19.5, "value_vnd": 15000.0, "scale": 1.3, "rating": "BUY", "n_analysts": 1,
             "file": "vc_coverage_hist/2025-12-28.json", "tier": "SS-T3", "label": "Vietcap 12/26"}
TK_SCALE = {"scale": 1.3, "series": 13.0, "actual_vnd": 10000.0, "date": "2026-01-02",
            "src": "hhp_vn100_valuation.json by_ticker (vietcap_board)"}  # 13.0 ÷ (10000 / 1000)
CIQ_TARGET = {"id": "ciq-tp", "org": "S&P Capital IQ", "date": "2025-12-30", "horizon": "2026-12-30", "ms": 8000,
              "value": 16.9, "value_vnd": 13000.0, "scale": 1.3, "n_analysts": 7, "file": "Estimates.xls",
              "tier": "FACT-T2", "label": "CapIQ 12/26"}


def tk_growth():
    return [
        {"year": 2026, "g": 0.12, "tier": "SS-T3", "est": False, "n": 1, "W": 1.0, "min": 0.12, "max": 0.12,
         "flag": "1 nguồn",
         "sources": [{"id": "vc_cov", "org": "Vietcap Research", "value": 0.12, "weight": 1.0, "date": "2025-12-28",
                      "tier": "SS-T3", "file": "vc_coverage_hist/2025-12-28.json",
                      "note": "LN sau thuế cổ đông mẹ ≈ EPS nếu số CP không đổi"}]},
        {"year": 2027, "g": 0.121, "tier": "EST", "est": True, "n": 0, "W": 0.0, "min": None, "max": None,
         "flag": "quy tắc dài hạn", "sources": []},
    ]


def tk_fc_block(last, x0=TK_X0):
    """37 monthly points from `last` (k=0 verbatim), 1% a step — shape only, not the bridge's math."""
    xs = [x0 + 1000 * i for i in range(hv.TICKER_FC_POINTS)]
    return {
        "growth": tk_growth(),
        "eps_pins": [{"year": 2025, "date": "2025-12-31", "ms": x0 - 500, "value": last["base"], "tier": "EST",
                      "method": "EPS 4 quý tới Q4/2025 theo finfo"}],
        "base_path": [[x, round(last["base"] * (1 + 0.01 * i), 4)] for i, x in enumerate(xs)],
        "points": {k: [[x, round(last[k] * (1 + 0.01 * i), 2)] for i, x in enumerate(xs)] for k in TK_LEVELS},
        "milestones": [{"date": "2026-12-31", "ms": x0 + 3000, "base": round(last["base"] * 1.03, 2),
                        **{k: round(last[k] * 1.03, 2) for k in TK_LEVELS}}],
        "reliable": True, "method": "EPS ghim theo năm tài chính (theo mã)",
    }


def ticker_fc_fixture():
    """AAA: P/E forecast; P/B skipped by the bridge (its σ is not finite); two ◆ targets (CapIQ first by ms)."""
    return {
        "meta": {"schema": "hhp_forecast_ticker/1", "generated": "2026-01-02 10:12 ICT", "ticker": "AAA",
                 "horizon_months": 36, "unit": "nghìn đồng (giá điều chỉnh VnDirect DCHART)",
                 "method": "trung vị có trọng số theo mã", "caveats": ["Tham khảo, không khuyến nghị"],
                 "warnings": ["2027: không nguồn → quy tắc dài hạn (EST)"], "price_scale": dict(TK_SCALE),
                 "fy_last": 2025},
        "sources": [{"id": "vc_cov", "org": "Vietcap Research", "title": "Coverage 2026F/2027F", "date": "2025-12-28",
                     "file": "vc_coverage_hist/2025-12-28.json", "tier": "SS-T3"}],
        "anchor": {"as_of": "2026-01-02", "ms": TK_X0,
                   "pe": {"mean": AAA_PE_MEAN, "sd": AAA_PE_SD, "last": dict(AAA_PE_LAST)}, "pb": None},
        "pe": tk_fc_block(AAA_PE_LAST),
        "pb": None,
        "skip": {"pe": None, "pb": "σ P/B không hữu hạn"},
        "targets": [dict(VC_TARGET), dict(CIQ_TARGET)],
    }


def bbb_fc_fixture():
    """BBB: no P/E series (bridge skip), P/B forecast with its retention rule, flagged unreliable."""
    fc = ticker_fc_fixture()
    fc["meta"]["ticker"] = "BBB"
    fc["anchor"] = {"as_of": "2026-01-02", "ms": 1000, "pe": None,
                    "pb": {"mean": 2.0, "sd": 0.5, "last": dict(BBB_PB_LAST)}}
    fc["pe"] = None
    fc["pb"] = dict(tk_fc_block(BBB_PB_LAST, x0=1000), reliable=False,
                    retention={"r": 0.55, "per_year": [{"year": 2025, "r": 0.55}], "fallback": False})
    fc["skip"] = {"pe": "không có chuỗi P/E", "pb": None}
    fc["targets"] = []
    return fc


def ticker_keynotes_fixture():
    return {"meta": {"schema": "hhp_keynotes/1"}, "sources": KN_SOURCES, "events": [
        kn_event("2024-03-dinh", "2024-03-11", scopes=["aaa"], sources=["s_hose"], tier="FACT-T1",
                 numbers=[dict(CLOSE_NUM, scope="AAA", asof="2024-03-11")]),
        kn_event("2023-10-day", "2023-10-30", kind="day", scopes=["AAA"], numbers=[]),
    ]}


def build_fixture(root, with_optional=True, with_verdict=True, with_prices=True, with_upg=True):
    core = {
        "meta": {"generated": "2026-01-02 10:00 ICT", "expert": "Huỳnh Hoàng Phương", "method": "P = E×P/E",
                 "disclaimer": "Tham khảo", "sources": ["test"], "n_tickers": 5, "fails": ["XX"]},
        "index": {
            "pe": {"metric": "P/E", "now": 12.5, "mean": 15.0, "sd": 2.0, "sigma": -1.25, "zone": CHEAP,
                   "price_now": 1800.0, "as_of": "2026-01-02", "n_points": 3,
                   "forward": {"date": "2027-12-31", "growth": 0.18, "fair": 2600.0, "cheap1": 2300.0,
                               "rich1": 2900.0, "rich2": 3200.0},
                   "chart": {k: [[1000, 1.0], [2000, NAN], [3000, 3.0]]
                             for k in ("price", "fair", "cheap1", "cheap2", "rich1", "rich2")}},
            "pb": None,
        },
        "exvic3": {"as_of": "2026-01-02", "pe_full_now": 12.5, "pe_exv3_now": 10.0, "exv3_pe_mean": 14.0,
                   "exv3_pe_sd": 2.0, "exv3_pe_sigma": 1.5, "exv3_pe_zone": RICH, "vic3": [],
                   "series": {"w3": [[1000, 20.0], [2000, float("inf")]]}},
        "by_ticker": {
            "AAA": entry(metric(CHEAP, -1.5), metric(RICH, 1.5)),
            "BBB": entry(None, metric(NEUTRAL, 0.2), price=None),
            "CCC": entry(metric(NEUTRAL, 0.0, now=NAN), {**metric(None, -1.7), "zone": None}),
            "DDD": entry(metric(NEUTRAL, 0.1), metric(NEUTRAL, 0.1)),
            "EEE": entry(metric(RICH, 2.0), metric(NEUTRAL, -0.5)),
        },
    }
    if with_prices:
        core["meta"].update(prices=PRICES_META, capiq=CAPIQ_META)
        bt = core["by_ticker"]
        bt["AAA"].update(price_fields("vietcap_board", time_="2026-01-02T15:14:27+07:00", capiq=CAPIQ_AAA))
        bt["BBB"].update(price_fields(None, date=None, capiq=CAPIQ_BBB), eps=None, bvps=None, eps_src=None)
        bt["CCC"].update(price_fields("vietcap_history"))
        bt["DDD"].update(price_fields("simplize_stale", date=None))  # outside both universes → not warned
        bt["EEE"].update(price_fields("simplize_stale", date="2025-12-30"))
    if with_verdict:
        core["hdcv_verdict"] = {"stance": "Tích sản", "headline": "h", "reads": ["r1"], "risks": ["k1"],
                                "mode": "deterministic", "updated": "2026-01-02 10:01 ICT"}
    write_json(os.path.join(root, hv.CORE_FILE), core)
    if with_upg:
        write_json(os.path.join(root, hv.KEYNOTES_FILE), keynotes_fixture())
        write_json(os.path.join(root, hv.FORECAST_FILE), forecast_fixture())
        write_json(os.path.join(root, hv.TICKER_FC_DIR, "AAA.json"), ticker_fc_fixture())
        write_json(os.path.join(root, hv.TICKER_KN_DIR, "AAA.json"), ticker_keynotes_fixture())

    if with_optional:
        write_json(os.path.join(root, hv.MEMBERS_FILE), {
            "meta": {"generated": "2026-01-02 09:00 ICT"},
            "members": {"VN30": ["AAA", "EEE", "ZZZ"], "VN100": ["BBB", "AAA", "CCC", "MISS", "bbb"]},
        })
        write_json(os.path.join(root, hv.BASKETS_FILE), {
            "meta": {"generated": "2026-01-02 09:30 ICT"},
            "baskets": [
                {"code": "VNINDEX", "label": "VN-Index", "pe": basket_metric(NEUTRAL, 0.0), "pb": None},
                {"code": "VN30", "label": "VN30 — 30 vốn hóa lớn", "pe": basket_metric(NEUTRAL, 0.5),
                 "pb": basket_metric(CHEAP, -1.2)},
                {"code": "VN100", "label": "VN100", "pe": basket_metric(RICH, 1.1), "pb": None},
            ],
        })

    series_dir = os.path.join(root, hv.SERIES_DIR)
    write_json(os.path.join(series_dir, "AAA.json"), {
        "ticker": "AAA",
        "pe": {"price": [[4000, 13.0], [1000, 10.0], [2000, 11.0], [3000, 12.0], [5000, NAN]],
               "base": [[1000, 1.0], [3000, None], [4000, 2.0], [5000, 2.5], [6000, 3.0]],
               "mean": AAA_PE_MEAN, "sd": AAA_PE_SD, "now": 6.5, "sigma": -0.6, "zone": CHEAP,
               "price_now": 13.0, "n": 5, "as_of": "2026-01-02"},
        "pb": {"price": [[1000, 10.0], [4000, 13.0]], "base": [[1000, 5.0], [4000, 6.0]],
               "mean": 1.5, "sd": NAN, "now": 2.1, "sigma": 1.2, "zone": RICH, "price_now": 13.0, "n": 2,
               "as_of": "2026-01-02"},
        "forward": {"pe": {"2026F": 11.0, "2027F": 9.5}, "tp": 15000.0, "rating": "BUY", "analyst": "X",
                    "src": {"pe2026": "vietcap"}, "note": "n"},
        "meta": {"generated": "2026-01-02 10:05 ICT", "sources": ["test"]},
    })
    write_json(os.path.join(series_dir, "BBB.json"), {
        "ticker": "BBB", "pe": None,
        "pb": {"price": [[1000, 10.0]], "base": [[1000, 4.0]], "mean": 2.0, "sd": 0.5, "now": 2.5, "sigma": 1.0,
               "zone": NEUTRAL, "price_now": 10.0, "n": 1, "as_of": "2026-01-02"},
        "forward": None, "meta": {"generated": "2026-01-02 10:06 ICT"},
    })
    # EEE: P/E stopped updating upstream years ago (like KOS) → stale; P/B is current.
    write_json(os.path.join(series_dir, "EEE.json"), {
        "ticker": "EEE",
        "pe": {"price": [[1000, 30.0]], "base": [[1000, 0.2]], "mean": 100.0, "sd": 50.0, "now": 167.0,
               "sigma": 2.0, "zone": RICH, "price_now": 30.0, "n": 1, "as_of": "2021-11-30"},
        "pb": {"price": [[1000, 30.0]], "base": [[1000, 20.0]], "mean": 1.6, "sd": 0.2, "now": 1.5, "sigma": -0.5,
               "zone": NEUTRAL, "price_now": 30.0, "n": 1, "as_of": "2025-12-20"},
        "forward": None, "meta": {},
    })
    write_json(os.path.join(series_dir, "DDD.json"), {"ticker": "DDD", "pe": None, "pb": None, "forward": None,
                                                      "meta": {}})
    write_json(os.path.join(series_dir, "QQQ.json"), {"ticker": "QQQ", "pe": None, "pb": None, "forward": None,
                                                      "meta": {}})
    with open(os.path.join(series_dir, "BAD.json"), "w", encoding="utf-8") as fh:
        fh.write("{not json")
    # CCC deliberately has no series file → NO_SERIES.


# ── hhp_vnindex_history.json fixture (schema hhp_vnindex_history/1, FINAL_PLAN §4.3). Real dates, so the long.from /
#    chart / ◇ rules bite; the engine index and the VNINDEX forecast of build_fixture() are re-anchored on the same grid
#    (build_history_fixture). Values are shapes, not the builder's math. ──
def dms(day):
    d = date.fromisoformat(day)
    return utc_ms(d.year, d.month, d.day)


H_GEN, H_FC_GEN = "2026-01-02 10:20 ICT", "2026-01-02 10:10 ICT"
H_ENGINE_X = [dms("2025-12-29"), dms("2025-12-30"), dms("2026-01-02")]
H_X0 = H_ENGINE_X[-1]
H_FC_X = [H_X0, dms("2026-02-02"), dms("2026-03-02"), dms("2026-04-02")]
H_MULT = {"fair": 0, "cheap1": -1, "cheap2": -2, "rich1": 1, "rich2": 2}
H_ENGINE = {"pe": {"now": 12.5, "mean": 15.0, "sd": 2.0, "sigma": -1.25, "zone": CHEAP, "fair": (2148.0, 2154.0, 2160.0)},
            "pb": {"now": 1.9, "mean": 2.0, "sd": 0.4, "sigma": -0.25, "zone": NEUTRAL, "fair": (1884.2, 1889.5, 1894.7)}}
H_LONG = {"pe": {"from": "2011-01-04", "to": "2026-01-02", "n_weeks": 781, "mean": 14.31, "sd": 2.24, "now": 12.5,
                 "sigma": -0.81, "zone": NEUTRAL, "zone_key": "neutral", "pct": 18.5, "method": "tuần, winsorize P5–P95",
                 "tier": "EST", "vendor_published": {"org": "Vietcap IQ", "mean": 14.48, "sd": 2.62, "date": "2026-01-02",
                                                     "tier": "FACT-T2", "note": "không winsorize"}},
          "pb": {"from": "2010-01-04", "to": "2026-01-02", "n_weeks": 834, "mean": 2.03, "sd": 0.36, "now": 1.9,
                 "sigma": -0.36, "zone": NEUTRAL, "zone_key": "neutral", "pct": 40.0, "method": "tuần, winsorize P5–P95",
                 "tier": "EST", "vendor_published": None}}
H_EIGHT = {m: {"from": "2017-12-15", "mean": e["mean"], "sd": e["sd"], "sigma": e["sigma"], "zone": e["zone"],
               "zone_key": "cheap" if e["zone"] == CHEAP else "neutral", "pct": 8.6, "pct_method": "tuần",
               "check": {"mean_w": e["mean"], "sd_w": e["sd"], "ok": True}} for m, e in H_ENGINE.items()}
H_CHART_X = {"pe": [dms("2011-01-04"), dms("2014-06-02"), dms("2018-11-13")] + H_ENGINE_X,
             "pb": [dms("2010-01-04"), dms("2014-06-02"), dms("2018-02-02")] + H_ENGINE_X}
H_BASE = {"pe": (60.0, 45.0, 70.0, 143.2, 143.6, 144.0), "pb": (250.0, 400.0, 480.0, 942.1, 944.75, 947.35)}
H_PRICE = [[dms(d), v] for d, v in (
    ("2000-07-28", 100.0), ("2001-06-25", 571.04), ("2003-10-24", 130.9), ("2007-02-28", 1050.0),
    ("2007-03-12", 1170.67), ("2008-12-31", 315.62), ("2010-01-04", 517.1), ("2011-01-04", 500.0),
    ("2012-01-06", 336.73), ("2025-12-29", 1790.0), ("2025-12-30", 1795.0), ("2026-01-02", 1800.0))]
H_SRC_IMF = {"org": "IMF", "title": "Country Report 07/385", "date": "2007-11", "url": "https://imf.invalid/cr07385.pdf",
             "loc": "tr.26, chú thích 3/", "quote": "Largest 30 listed companies"}
H_SRC_WB = {"org": "World Bank", "title": "Taking Stock 06/2007", "date": "2007-06", "url": "https://wb.invalid/ts"}
H_SRC_KBSV = {"org": "KBSV (qua VnExpress)", "title": "Hồi tưởng 2008", "date": "2020-04", "url": "https://vnx.invalid/k"}
HIST_ORG = "HHP toàn sử (hhp_vnindex_history.py)"


def engine_index_block(m):
    e = H_ENGINE[m]
    chart = {"price": [[x, p] for x, p in zip(H_ENGINE_X, (1790.0, 1795.0, 1800.0))]}
    for k, mult in H_MULT.items():
        chart[k] = [[x, round(f * (e["mean"] + mult * e["sd"]) / e["mean"], 1)] for x, f in zip(H_ENGINE_X, e["fair"])]
    return {"metric": hv.METRIC_LABEL[m], "now": e["now"], "mean": e["mean"], "sd": e["sd"], "sigma": e["sigma"],
            "zone": e["zone"], "price_now": 1800.0, "as_of": "2026-01-02", "n_points": 3, "forward": None, "chart": chart}


def history_forecast_scope():
    """scopes.VNINDEX of hhp_forecast.json on the engine above (the overview's own anchor check passes too)."""
    anchor = {"as_of": "2026-01-02", "ms": H_X0}
    scope = {"anchor": anchor, "targets": []}
    for m in hv.METRICS:
        chart = engine_index_block(m)["chart"]
        last = {k: chart[k][-1][1] for k in ("price",) + tuple(H_MULT)}
        anchor[m] = {"mean": H_ENGINE[m]["mean"], "sd": H_ENGINE[m]["sd"], "last": last}
        blk = index_fc_block()
        blk.update(base_path=[[x, round(144.0 * (1 + 0.01 * i), 2)] for i, x in enumerate(H_FC_X)],
                   points={k: [[x, round(last[k] * (1 + 0.01 * i), 1)] for i, x in enumerate(H_FC_X)] for k in H_MULT},
                   milestones=[{"date": "2026-12-31", "ms": dms("2026-12-31"), "base": 160.0, "fair": 2400.0}])
        scope[m] = blk
    return scope


def history_chart(m):
    lng = H_LONG[m]
    return {k: [[x, max(0.0, round(b * (lng["mean"] + mult * lng["sd"]), 1))] for x, b in zip(H_CHART_X[m], H_BASE[m])]
            for k, mult in H_MULT.items()}


def history_reading(k, v, asof, sigma=None, **kw):
    r = {"k": k, "scope": "VNINDEX", "v": v, "unit": "x", "asof": asof, "tier": "EST",
         "method": "σ dài hạn 01/2011→ (Vietcap IQ nối VnDirect finfo tại 2018-11-12), tuần, winsorize P5–P95",
         "src_org": HIST_ORG, "src_date": H_GEN}
    if sigma is not None:
        r["sigma"] = sigma
    r.update(kw)
    return r


def history_point(pid, day, v, close, **kw):
    p = {"id": pid, "metric": "pe", "date": day, "ms": dms(day), "v": v, "value_kind": "point", "period": None,
         "basis": "market_trailing", "definition": "P/E trailing toàn thị trường", "tier": "SS-T3",
         "src": dict(H_SRC_WB), "note": "", "close": close, "vs_long_mean": "above", "also": []}
    p.update(kw)
    return p


def history_points():
    """3 valid ◇ (one lower-bound, one with a σ the script must strip) + 5 that must be dropped alone."""
    return [
        history_point("kbsv-2008-12", "2008-12-31", 8.0, 315.62, value_kind="approx", basis="unknown",
                      src=dict(H_SRC_KBSV), vs_long_mean="below"),
        history_point("imf-2007-02", "2007-02-28", 53.6, 1050.0, basis="top30_hcm_hn", src=dict(H_SRC_IMF),
                      period={"from": "2007-01-01", "to": "2007-02-28"}, sigma_long=17.5, sigma=17.5,
                      date_note="bình quân 01–02/2007",
                      also=[{"v": 36.0, "value_kind": "approx", "basis": "market_trailing", "tier": "SS-T3",
                             "src": dict(H_SRC_WB), "date": "2006-12-29", "sigma": 9.9},
                            {"v": 73.0, "value_kind": "point", "tier": "UNVERIFIED", "src": dict(H_SRC_WB),
                             "date": "2007-01-31"}]),
        history_point("cafef-lb", "2007-03-15", 40.0, 1150.0, value_kind="lower_bound", vs_long_mean="above"),
        history_point("no-src-date", "2007-05-15", 33.0, 1000.0, src={"org": "World Bank"}),
        history_point("unv-73", "2007-01-31", 73.0, 1000.0, tier="UNVERIFIED"),
        history_point("after-long", "2012-03-01", 10.0, 420.0),
        history_point("no-close", "2006-12-29", 36.0, None),
        history_point("bad-kind", "2007-12-21", 27.5, 900.0, value_kind="guess"),
    ]


def history_metric_fixture(m):
    chart = history_chart(m)
    return {
        "long": copy.deepcopy(H_LONG[m]), "eight": copy.deepcopy(H_EIGHT[m]), "windows_agree": m == "pb",
        "seam": {"date": "2018-11-12" if m == "pe" else "2018-02-01", "grid_date": "2018-11-13", "rule": "R2 D",
                 "overlap_n": 1198, "median": 0.9999, "p10": 0.96, "p90": 1.01, "by_year": {"2018": 1.04},
                 "jump_pct": -0.1, "vendor_own_move_pct": -0.16, "excess_pp": 0.06},
        "chart": chart,
        "points": history_points() if m == "pe" else [],
        "forecast": {"x0": H_X0, "source_generated": H_FC_GEN,
                     "points": {k: [[x, round(chart[k][-1][1] * (1 + 0.02 * i), 1)] for i, x in enumerate(H_FC_X)]
                                for k in H_MULT},
                     "milestones": [{"date": "2026-12-31", "ms": dms("2026-12-31"), "base": 160.0, "fair": 2289.6}],
                     "method": "đường EPS của hhp_forecast.json × (μ ± kσ) dài hạn"},
        "keynote_readings": {"kn-2012-01-day": [history_reading(m, 7.9 if m == "pe" else 1.25, "2012-01-06",
                                                                -2.9 if m == "pe" else -2.2)]},
        "note": "khóa lạ — đi thẳng",
    }


def history_fixture():
    pe = history_metric_fixture("pe")
    pe["keynote_readings"].update({
        "kn-2007-03-dinh": [
            history_reading("pe", 53.6, "2007-02-28", tier="SS-T3", src_org="IMF", src_date="2007-11",
                            method="P/E bình quân 30 công ty lớn nhất HCM + HN (top30_hcm_hn)"),
            history_reading("pe", 40.0, "2007-03-15", 11.0, tier="NEWS", src_org="CafeF", src_date="2020-04-01"),
            history_reading("pe", 73.0, "2007-01-31", tier="UNVERIFIED", src_org="VOA", src_date="2007-02")],
        "kn-ghost": [history_reading("pe", 9.0, "2016-01-21", -2.0)],
    })
    return {
        "meta": {"schema": "hhp_vnindex_history/1", "generated": H_GEN, "engine_as_of": {"pe": "2026-01-02",
                                                                                           "pb": "2026-01-02"},
                 "inputs": {"engine": {"file": "hhp_vn100_valuation.json", "generated": "2026-01-02 10:00 ICT"},
                            "static": {"file": "hhp_vnindex_history_static.json", "built": "2026-09-27 03:00 ICT",
                                       "sha256": "ab" * 32},
                            "vnstore": {"db": "vn_store.db", "last": "2026-01-02"}, "vietcap_cache": None,
                            "forecast": {"file": "hhp_forecast.json", "generated": H_FC_GEN},
                            "keynotes": {"file": "hhp_keynotes.json", "updated": "2026-01-02T10:00:00+07:00"}},
                 "method": "Giá R1 + dải σ dài hạn", "caveats": ["◇ khác định nghĩa — chỉ tham khảo"],
                 "warnings": ["builder: cảnh báo riêng của bước 1d"],
                 "sources": [{"id": "s_cafef_px", "org": "CafeF", "title": "Lịch sử giá", "date": "2026-09-27",
                              "url": "https://cafef.invalid/px", "tier": "FACT-T2"}]},
        "base": {"date": "2000-07-28", "value": 100.0, "tier": "FACT-T2", "src": ["s_cafef_px"],
                 "conflict": "báo ghi 101,55 = giá 31/07/2000"},
        "price": {"points": copy.deepcopy(H_PRICE), "n_daily": 6365, "first_date": "2000-07-28",
                  "last_date": "2026-01-02", "src_spans": [{"from": "2000-07-28", "to": "2003-12-31", "src": "cf",
                                                            "tier": "FACT-T2", "n": 714}], "level_x_base": 18.0},
        "gaps": [],
        "pe": pe,
        "pb": history_metric_fixture("pb"),
    }


def history_keynotes_fixture():
    """VNINDEX events 2007 / 2012 / 2020 + one VN30-only (not on the full-history chart)."""
    unscoped = {k: v for k, v in PE_NUM.items() if k != "scope"}
    return {"meta": {"schema": "hhp_keynotes/1"}, "sources": KN_SOURCES, "events": [
        kn_event("kn-2012-01-day", "2012-01-06", kind="day", sources=["s_hose"], tier="FACT-T1", priority=2,
                 priority_full=1, numbers=[
                     dict(CLOSE_NUM, v=336.73, asof="2012-01-06"),
                     dict(PE_NUM, v=7.61, sigma=-2.62, asof="2012-01-06", method="σ thang Vietcap IQ 2009→"),
                     dict(PE_NUM, k="pb", v=1.21, sigma=-2.13, asof="2012-01-06"),
                     dict(PE_NUM, scope="VN100", v=8.1, sigma=-1.9),
                     dict(unscoped, v=7.7, sigma=-2.5),
                     {"k": "sigma", "scope": "VNINDEX", "v": -2.62, "unit": "σ", "src": "s_eng", "tier": "EST",
                      "method": "thang Vietcap"}]),
        kn_event("kn-2007-03-dinh", "2007-03-12", sources=["s_hose"], tier="FACT-T1", priority=1,
                 numbers=[dict(CLOSE_NUM, v=1170.67, asof="2007-03-12")]),
        kn_event("kn-2020-03-day", "2020-03-24", kind="day", scopes=["VNINDEX", "VN100"], sources=["s_hose"],
                 tier="FACT-T1", priority=1, priority_full=7),
        kn_event("kn-2025-12-dinh", "2025-12-15", scopes=["VN30"], priority=3, priority_full=2),
    ]}


def build_history_fixture(root):
    """build_fixture() + an engine / forecast / keynote file / hhp_vnindex_history.json that fit together."""
    build_fixture(root)
    core_path = os.path.join(root, hv.CORE_FILE)
    with open(core_path, encoding="utf-8") as fh:
        core = json.load(fh)
    core["index"] = {m: engine_index_block(m) for m in hv.METRICS}
    write_json(core_path, core)
    fc = forecast_fixture()
    fc["scopes"]["VNINDEX"] = history_forecast_scope()
    write_json(os.path.join(root, hv.FORECAST_FILE), fc)
    write_json(os.path.join(root, hv.KEYNOTES_FILE), history_keynotes_fixture())
    write_json(os.path.join(root, hv.HISTORY_FILE), history_fixture())


def all_keys(obj):
    """Every dict key anywhere in obj."""
    if isinstance(obj, dict):
        return set(obj) | set().union(*(all_keys(v) for v in obj.values()))
    if isinstance(obj, list):
        return set().union(*(all_keys(v) for v in obj)) if obj else set()
    return set()


# Overview output of the script BEFORE the `history` command existed (hhp_valuation.py.bak-20260927) on build_fixture(),
# volatile fields normalised. FINAL_PLAN M17: the overview may only gain meta.history_file. Regenerate ONLY for an
# intended overview change: HHP_REGEN_GOLDEN=1 python3 -m unittest test_hhp_valuation.OverviewHistoryFileTest
OVERVIEW_GOLDEN = os.path.join(HERE, "test_hhp_valuation_fixtures", "overview_golden.json")


def normalize_overview(obj):
    obj = copy.deepcopy(obj)
    m = obj["meta"]
    for k in ("file_mtime", "age_hours", "stale", "data_dir"):
        m[k] = "<volatile>"
    for k in ("keynotes_file", "forecast_file"):
        if isinstance(m.get(k), dict):
            for kk in ("mtime", "age_hours"):
                if kk in m[k]:
                    m[k][kk] = "<volatile>"
    if isinstance(obj.get("forecast"), dict):
        obj["forecast"]["meta"]["age_hours"] = "<volatile>"
    return obj


class _FixtureCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="hhp_test_")
        cls.dir = os.path.join(cls.tmp, "full")
        build_fixture(cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def overview(self):
        rc, obj, text = run_script(["overview"], self.dir)
        self.assertEqual(rc, 0)
        self.assertNotIn("error", obj, obj.get("error"))
        self.assertEqual(text.strip().count("\n"), 0, "expected exactly one compact JSON line")
        return obj

    def ticker(self, tk):
        rc, obj, _ = run_script(["ticker", tk], self.dir)
        self.assertEqual(rc, 0)
        return obj


class ZoneKeyTest(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(hv.zone_key(CHEAP), "cheap")
        self.assertEqual(hv.zone_key(NEUTRAL), "neutral")
        self.assertEqual(hv.zone_key(RICH), "rich")
        self.assertEqual(hv.zone_key("RẺ (<-1σ)"), "cheap")  # ASCII hyphen variant
        self.assertEqual(hv.zone_key(" ĐẮT "), "rich")

    def test_sigma_fallback_matches_upstream_rule(self):
        self.assertEqual(hv.zone_key(None, -1.01), "cheap")
        self.assertEqual(hv.zone_key(None, -1.0), "neutral")
        self.assertEqual(hv.zone_key("???", 1.0), "neutral")
        self.assertEqual(hv.zone_key(None, 1.2), "rich")
        self.assertIsNone(hv.zone_key(None, None))
        self.assertIsNone(hv.zone_key(None, NAN))

    def test_clean_replaces_non_finite(self):
        out = hv.clean({"a": [1.0, NAN, float("inf"), -float("inf")], "b": {"c": NAN}, "d": "x", "e": True})
        self.assertEqual(out, {"a": [1.0, None, None, None], "b": {"c": None}, "d": "x", "e": True})


class OverviewTest(_FixtureCase):
    def test_zone_keys_everywhere(self):
        d = self.overview()
        self.assertEqual(d["index"]["pe"]["zone_key"], "cheap")
        self.assertEqual(d["index"]["pe"]["zone"], CHEAP)
        self.assertIsNone(d["index"]["pb"])
        self.assertEqual(d["exvic3"]["exv3_pe_zone_key"], "rich")
        self.assertEqual(d["baskets"]["VN30"]["pe"]["zone_key"], "neutral")
        self.assertEqual(d["baskets"]["VN30"]["pb"]["zone_key"], "cheap")
        self.assertEqual(d["baskets"]["VN100"]["pe"]["zone_key"], "rich")
        self.assertIsNone(d["baskets"]["VN100"]["pb"])
        self.assertEqual(set(d["baskets"]), {"VN30", "VN100"})
        rows = {r["tk"]: r for r in d["rows"]}
        self.assertEqual(rows["AAA"]["pe"]["zone_key"], "cheap")
        self.assertEqual(rows["AAA"]["pb"]["zone_key"], "rich")
        self.assertEqual(rows["CCC"]["pb"]["zone_key"], "cheap")  # null label → sigma −1.7
        self.assertEqual(rows["EEE"]["pe"]["zone_key"], "rich")

    def test_rows_order_flags_and_missing(self):
        d = self.overview()
        self.assertEqual([r["tk"] for r in d["rows"]], ["BBB", "AAA", "CCC", "EEE"])  # VN100 order, then VN30-only
        rows = {r["tk"]: r for r in d["rows"]}
        self.assertEqual((rows["AAA"]["in_vn30"], rows["AAA"]["in_vn100"]), (True, True))
        self.assertEqual((rows["BBB"]["in_vn30"], rows["BBB"]["in_vn100"]), (False, True))
        self.assertEqual((rows["EEE"]["in_vn30"], rows["EEE"]["in_vn100"]), (True, False))
        self.assertNotIn("DDD", rows)  # in by_ticker but in neither universe
        self.assertEqual(d["members"], {"VN30": ["AAA", "EEE", "ZZZ"], "VN100": ["BBB", "AAA", "CCC", "MISS"]})
        self.assertEqual(d["missing"], {"VN30": ["ZZZ"], "VN100": ["MISS"]})
        for r in d["rows"]:
            self.assertNotIn("sector", r)
            self.assertEqual(list(r)[:3], ["tk", "in_vn30", "in_vn100"])
        self.assertIsNone(rows["BBB"]["pe"])
        self.assertIsNone(rows["BBB"]["price_now"])
        self.assertEqual(rows["AAA"]["links"]["simplize"], "https://example.invalid/sz")

    def test_zone_counts(self):
        d = self.overview()
        # EEE's P/E is stale → counted in total and "stale", in no zone.
        self.assertEqual(d["zone_counts"], {
            "VN30": {"pe": {"cheap": 1, "neutral": 0, "rich": 0, "stale": 1, "total": 2},
                     "pb": {"cheap": 0, "neutral": 1, "rich": 1, "stale": 0, "total": 2}},
            "VN100": {"pe": {"cheap": 1, "neutral": 1, "rich": 0, "stale": 0, "total": 2},
                      "pb": {"cheap": 1, "neutral": 1, "rich": 1, "stale": 0, "total": 3}},
        })

    def test_series_as_of_and_stale(self):
        rows = {r["tk"]: r for r in self.overview()["rows"]}
        self.assertEqual((rows["AAA"]["pe"]["as_of"], rows["AAA"]["pe"]["stale"]), ("2026-01-02", False))
        self.assertEqual((rows["EEE"]["pe"]["as_of"], rows["EEE"]["pe"]["stale"]), ("2021-11-30", True))
        # 13 days behind the index as_of (2026-01-02) is within STALE_SERIES_DAYS.
        self.assertEqual((rows["EEE"]["pb"]["as_of"], rows["EEE"]["pb"]["stale"]), ("2025-12-20", False))
        self.assertEqual(rows["EEE"]["pe"]["zone_key"], "rich")  # zone kept; only the counts skip it
        # No series file → date unknown, not flagged.
        self.assertEqual((rows["CCC"]["pe"]["as_of"], rows["CCC"]["pe"]["stale"]), (None, False))

    def test_stale_row_matches_between_commands(self):
        overview_row = next(r for r in self.overview()["rows"] if r["tk"] == "EEE")
        self.assertEqual(self.ticker("EEE")["row"], overview_row)

    def test_non_finite_become_null(self):
        d = self.overview()
        self.assertEqual(d["index"]["pe"]["chart"]["price"], [[1000, 1.0], [2000, None], [3000, 3.0]])
        self.assertEqual(d["exvic3"]["series"]["w3"], [[1000, 20.0], [2000, None]])
        rows = {r["tk"]: r for r in d["rows"]}
        self.assertIsNone(rows["CCC"]["pe"]["now"])

    def test_meta_and_verdict(self):
        d = self.overview()
        m = d["meta"]
        self.assertEqual(m["generated"], "2026-01-02 10:00 ICT")
        self.assertEqual(m["expert"], "Huỳnh Hoàng Phương")
        self.assertEqual(m["n_tickers"], 5)
        self.assertEqual(m["data_dir"], self.dir)
        self.assertEqual(m["baskets_generated"], "2026-01-02 09:30 ICT")
        self.assertEqual(m["members_generated"], "2026-01-02 09:00 ICT")
        self.assertEqual(m["web_url"], hv.WEB_URL)
        self.assertEqual(len(m["warnings"]), 1, m["warnings"])  # EEE's fallback price, see PriceFieldsTest
        self.assertTrue(m["file_mtime"].endswith("+07:00"))
        self.assertFalse(m["stale"])
        self.assertEqual(m["fails"], ["XX"])  # upstream meta passes through
        self.assertEqual(d["verdict"]["stance"], "Tích sản")

    def test_stale_flag(self):
        stale_dir = os.path.join(self.tmp, "stale")
        build_fixture(stale_dir)
        old = time.time() - 31 * 3600
        os.utime(os.path.join(stale_dir, hv.CORE_FILE), (old, old))
        _, d, _ = run_script(["overview"], stale_dir)
        self.assertTrue(d["meta"]["stale"])
        self.assertAlmostEqual(d["meta"]["age_hours"], 31.0, delta=0.2)

    def test_optional_files_missing(self):
        bare = os.path.join(self.tmp, "bare")
        build_fixture(bare, with_optional=False)
        rc, d, _ = run_script(["overview"], bare)
        self.assertEqual(rc, 0)
        self.assertNotIn("error", d)
        self.assertIsNone(d["baskets"])
        self.assertEqual(d["members"], {"VN30": [], "VN100": []})
        self.assertEqual(d["rows"], [])
        self.assertEqual(d["zone_counts"]["VN100"]["pe"]["total"], 0)
        self.assertIsNone(d["meta"]["baskets_generated"])
        self.assertEqual(len(d["meta"]["warnings"]), 2)
        self.assertTrue(all("hhp_index_baskets.py" in w for w in d["meta"]["warnings"]))
        self.assertIsNotNone(d["index"]["pe"])

    def test_verdict_fallback_file(self):
        vdir = os.path.join(self.tmp, "verdict")
        build_fixture(vdir, with_verdict=False)
        _, d, _ = run_script(["overview"], vdir)
        self.assertIsNone(d["verdict"])
        write_json(os.path.join(vdir, hv.VERDICT_FILE), {"stance": "Phòng thủ", "headline": "h2"})
        _, d, _ = run_script(["overview"], vdir)
        self.assertEqual(d["verdict"]["stance"], "Phòng thủ")


class PriceFieldsTest(_FixtureCase):
    def test_row_price_fields_pass_through(self):
        rows = {r["tk"]: r for r in self.overview()["rows"]}
        a = rows["AAA"]
        self.assertEqual((a["price_now"], a["price_date"], a["price_time"], a["price_src"], a["eps_src"]),
                         (10000, "2026-01-02", "2026-01-02T15:14:27+07:00", "vietcap_board", "implied"))
        self.assertEqual(a["capiq"], CAPIQ_AAA)
        self.assertEqual((rows["CCC"]["price_src"], rows["CCC"]["price_time"], rows["CCC"]["capiq"]),
                         ("vietcap_history", None, None))
        b = rows["BBB"]
        self.assertEqual((b["price_now"], b["price_src"], b["eps"], b["bvps"], b["eps_src"]),
                         (None, None, None, None, None))
        self.assertEqual(b["capiq"], CAPIQ_BBB)  # null fields inside capiq stay null

    def test_meta_prices_and_capiq(self):
        m = self.overview()["meta"]
        self.assertEqual(m["prices"], PRICES_META)
        self.assertEqual(m["capiq"], CAPIQ_META)

    def test_capiq_ttm_and_screens_survive(self):
        ttm_dir = os.path.join(self.tmp, "ttm")
        build_fixture(ttm_dir)
        path = os.path.join(ttm_dir, hv.CORE_FILE)
        core = hv.load_json(path)
        core["meta"]["capiq"].update(CAPIQ_SCREENS_META)
        core["by_ticker"]["AAA"]["capiq"] = dict(CAPIQ_AAA, ttm=dict(CAPIQ_TTM, npm_ltm=NAN))
        write_json(path, core)
        expected = dict(CAPIQ_AAA, ttm=dict(CAPIQ_TTM, npm_ltm=None))  # non-finite inside ttm → null

        _, d, _ = run_script(["overview"], ttm_dir)
        self.assertNotIn("error", d)
        self.assertEqual(d["meta"]["capiq"], dict(CAPIQ_META, **CAPIQ_SCREENS_META))
        rows = {r["tk"]: r for r in d["rows"]}
        self.assertEqual(rows["AAA"]["capiq"], expected)
        self.assertNotIn("ttm", rows["BBB"]["capiq"])  # absent upstream → absent, not invented
        _, t, _ = run_script(["ticker", "AAA"], ttm_dir)
        self.assertEqual(t["forward"]["capiq"], expected)
        self.assertEqual(t["row"]["capiq"]["ttm"]["asof"], CAPIQ_TTM["asof"])

    def test_fallback_price_is_warned_not_silent(self):
        warns = [w for w in self.overview()["meta"]["warnings"] if "Vietcap" in w]
        self.assertEqual(len(warns), 1, warns)
        self.assertIn("1 mã", warns[0])
        self.assertIn("EEE (simplize_stale)", warns[0])
        self.assertNotIn("DDD", warns[0])  # outside VN30/VN100: not on screen, not warned
        self.assertIn("hhp_vn100_valuation.py", warns[0])

    def test_ticker_forward_carries_capiq(self):
        d = self.ticker("AAA")
        self.assertEqual(d["forward"]["capiq"], CAPIQ_AAA)
        self.assertEqual((d["forward"]["rating"], d["forward"]["tp"]), ("BUY", 15000.0))  # series forward kept
        self.assertEqual(d["row"]["capiq"], CAPIQ_AAA)
        # no forward in the series file, but CapIQ has the ticker → forward holds capiq only
        self.assertEqual(self.ticker("BBB")["forward"], {"capiq": CAPIQ_BBB})
        # neither → null, as before
        self.assertIsNone(self.ticker("EEE")["forward"])
        self.assertIsNone(self.ticker("QQQ")["forward"])  # absent from by_ticker

    def test_old_schema_gives_null_keys(self):
        old = os.path.join(self.tmp, "old_schema")
        build_fixture(old, with_prices=False)
        _, d, _ = run_script(["overview"], old)
        self.assertNotIn("error", d)
        self.assertIsNone(d["meta"]["prices"])
        self.assertIsNone(d["meta"]["capiq"])
        self.assertEqual(d["meta"]["warnings"], [])
        for r in d["rows"]:
            self.assertEqual({k: r[k] for k in PRICE_KEYS}, dict.fromkeys(PRICE_KEYS), r["tk"])
        _, t, _ = run_script(["ticker", "AAA"], old)
        self.assertIsNone(t["forward"]["capiq"])
        self.assertEqual(t["forward"]["rating"], "BUY")
        _, t, _ = run_script(["ticker", "BBB"], old)
        self.assertIsNone(t["forward"])


class TickerTest(_FixtureCase):
    def test_band_math_and_alignment(self):
        d = self.ticker("AAA")
        self.assertEqual((d["ticker"], d["unit"], d["generated"]), ("AAA", "nghìn đồng", "2026-01-02 10:05 ICT"))
        pe = d["pe"]
        c = pe["chart"]
        self.assertEqual(c["price"], [[1000, 10.0], [4000, 13.0]])  # joined on ts, sorted ascending
        bases = [1.0, 2.0]
        m, sd = AAA_PE_MEAN, AAA_PE_SD
        for name, k in (("fair", m), ("cheap1", m - sd), ("cheap2", m - 2 * sd), ("rich1", m + sd),
                        ("rich2", m + 2 * sd)):
            self.assertEqual(c[name], [[ts, max(0, round(b * k, 2))] for ts, b in zip((1000, 4000), bases)], name)
        self.assertEqual(c["fair"][1], [4000, round(2.0 * AAA_PE_MEAN, 2)])
        self.assertEqual(c["cheap2"], [[1000, 0.0], [4000, 0.0]])  # mean − 2sd < 0 → floored at 0
        self.assertEqual(len({len(v) for v in c.values()}), 1)
        self.assertEqual(pe["zone_key"], "cheap")
        self.assertNotIn("price", pe)
        self.assertNotIn("base", pe)
        self.assertEqual(pe["price_now"], 13.0)

    def test_non_finite_sd_leaves_only_fair(self):
        pb = self.ticker("AAA")["pb"]
        self.assertIsNone(pb["sd"])
        self.assertEqual(pb["chart"]["fair"], [[1000, 7.5], [4000, 9.0]])
        for name in ("cheap1", "cheap2", "rich1", "rich2"):
            self.assertEqual(pb["chart"][name], [])
        self.assertEqual(pb["zone_key"], "rich")

    def test_row_and_forward(self):
        d = self.ticker("aaa")  # lower-case accepted
        self.assertEqual(d["ticker"], "AAA")
        self.assertEqual(d["forward"]["rating"], "BUY")
        overview_row = next(r for r in self.overview()["rows"] if r["tk"] == "AAA")
        self.assertEqual(d["row"], overview_row)

    def test_null_metric(self):
        d = self.ticker("BBB")
        self.assertIsNone(d["pe"])
        self.assertEqual(d["pb"]["chart"]["fair"], [[1000, 8.0]])
        self.assertEqual(d["forward"], {"capiq": CAPIQ_BBB})  # series forward is null; CapIQ block only
        self.assertEqual((d["row"]["in_vn30"], d["row"]["in_vn100"]), (False, True))

    def test_row_outside_universes_and_absent(self):
        row = self.ticker("DDD")["row"]
        self.assertEqual((row["in_vn30"], row["in_vn100"]), (False, False))
        self.assertIsNone(self.ticker("QQQ")["row"])

    def test_no_series(self):
        for tk in ("CCC", "BAD"):
            d = self.ticker(tk)
            self.assertEqual(d["error_code"], "NO_SERIES", tk)
            self.assertIn("hhp_vn100_series.py", d["error"])

    def test_bad_args(self):
        for args in (["ticker", "../x"], ["ticker", ""], ["ticker", "A"], ["ticker", "TOOLONG"], ["ticker", "F-T"],
                     ["ticker", "FPT\n.."], ["ticker"], ["bogus"], []):
            rc, d, _ = run_script(args, self.dir)
            self.assertEqual(rc, 0, args)
            self.assertEqual(d.get("error_code"), "BAD_ARGS", args)
            self.assertTrue(d["error"])


class _UpgCase(unittest.TestCase):
    """Fresh full fixture per test; helpers rewrite hhp_keynotes.json / hhp_forecast.json."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hhp_upg_")
        self.dir = os.path.join(self.tmp, "d")
        build_fixture(self.dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def overview(self):
        rc, d, text = run_script(["overview"], self.dir)  # strict parse: NaN/Infinity tokens rejected
        self.assertEqual(rc, 0)
        self.assertNotIn("error", d, d.get("error"))
        self.assertEqual(text.strip().count("\n"), 0)
        return d

    def keynotes(self, events, sources=KN_SOURCES, today=date(2026, 1, 2)):
        """In-process load of a keynote file holding `events` → (keynotes, info, warnings)."""
        write_json(os.path.join(self.dir, hv.KEYNOTES_FILE), {"meta": {}, "sources": sources, "events": events})
        warnings = []
        kept, info = hv.load_keynotes(self.dir, warnings, today=today)
        return kept, info, warnings

    def with_forecast(self, mutate):
        fc = forecast_fixture()
        mutate(fc)
        write_json(os.path.join(self.dir, hv.FORECAST_FILE), fc)
        d = self.overview()
        return d["forecast"], d["meta"]["warnings"]

    def fc_warnings(self, warnings):
        return [w for w in warnings if "Dự phóng" in w or hv.FORECAST_FILE in w]


class MissingUpgFilesTest(unittest.TestCase):
    def test_no_files_gives_empty_and_one_warning_each(self):
        tmp = tempfile.mkdtemp(prefix="hhp_noupg_")
        try:
            build_fixture(tmp, with_upg=False)
            _, d, _ = run_script(["overview"], tmp)
            self.assertNotIn("error", d)
            self.assertEqual(d["keynotes"], [])
            self.assertIsNone(d["forecast"])
            self.assertIsNone(d["meta"]["keynotes_file"])
            self.assertIsNone(d["meta"]["forecast_file"])
            new = [w for w in d["meta"]["warnings"] if "Vietcap" not in w]
            self.assertEqual(len(new), 2, new)
            self.assertIn(hv.KEYNOTES_FILE, new[0])
            self.assertIn(hv.FORECAST_FILE, new[1])
            self.assertIn("hhp_forecast_bridge.py", new[1])

            _, t, _ = run_script(["ticker", "AAA"], tmp)  # no per-ticker forecast / keynote file yet
            self.assertNotIn("error", t)
            self.assertIsNone(t["forecast"])
            self.assertEqual(t["keynotes"], [])
            self.assertEqual((t["meta"]["forecast_file"], t["meta"]["keynotes_file"]), (None, None))
            self.assertEqual(len(t["meta"]["warnings"]), 1, t["meta"]["warnings"])  # the keynote file is silent
            self.assertIn("Chưa có hhp_forecast_tickers/AAA.json — dự phóng 3 năm của mã tắt. Chạy:",
                          t["meta"]["warnings"][0])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class KeynotesTest(_FixtureCase):
    def test_payload(self):
        d = self.overview()
        kn = d["keynotes"]
        self.assertEqual([k["id"] for k in kn], ["2018-04-dinh", "2020-03-day", "2025-12-dinh"])  # by date
        self.assertEqual(d["meta"]["keynotes_file"]["n"], 3)
        self.assertEqual(d["meta"]["keynotes_file"]["n_dropped"], 0)
        self.assertTrue(d["meta"]["keynotes_file"]["mtime"].endswith("+07:00"))
        a = kn[0]
        self.assertEqual(a["ms"], utc_ms(2018, 4, 9))
        self.assertEqual((a["kind"], a["priority"], a["nhan_phu"], a["provisional"]), ("dinh", 1, "margin + bank", False))
        self.assertEqual(a["scopes"], ["VNINDEX", "VN100"])  # upper-cased; VNX50 dropped …
        self.assertEqual(a["warnings"], ["Bỏ phạm vi không hỗ trợ: VNX50"])  # … and said so
        self.assertEqual((a["tier"], a["tier_effective"]), ("NEWS", "NEWS"))  # 2 orgs, 2 domains
        self.assertEqual([s["org"] for s in a["sources"]], ["Báo A", "Báo B", "Vietcap", "Engine HHP"])
        self.assertEqual(a["sources"][0], {"org": "Báo A", "title": "Tin A", "date": "2018-04-10",
                                           "url": "https://www.bao-a.invalid/a", "type": "news", "tier": "NEWS",
                                           "domain": "bao-a.invalid"})
        pe = next(n for n in a["numbers"] if n["k"] == "pe")
        self.assertEqual((pe["v"], pe["sigma"], pe["tier"], pe["src_org"], pe["src_date"]),
                         (19.1, 2.1, "EST", "Engine HHP", "2026-01-02"))
        self.assertEqual(pe["method"], PE_NUM["method"])
        for key in ("title", "boi_canh", "nguyen_nhan", "key_factors", "sau_do"):
            self.assertIn(key, a)
        self.assertNotIn("_score", a)

    def test_priority_and_provisional_derived(self):
        kn = {k["id"]: k for k in self.overview()["keynotes"]}
        self.assertEqual(kn["2020-03-day"]["priority"], 1)   # score 80: top third
        self.assertEqual(kn["2025-12-dinh"]["priority"], 3)  # score 10: bottom third
        self.assertTrue(kn["2025-12-dinh"]["provisional"])   # from detect.provisional
        self.assertEqual(kn["2020-03-day"]["tier_effective"], "FACT-T1")


class KeynoteValidationTest(_UpgCase):
    def test_malformed_events_dropped_and_counted(self):
        bad = [
            kn_event("Bad_ID", "2018-01-02"),
            kn_event("x" * 41, "2018-01-02"),
            kn_event("bad-date", "2018-13-40"),
            kn_event("short-date", "2018-01"),
            kn_event("future", "2026-01-03"),
            kn_event("bad-kind", "2018-01-02", kind="peak"),
            kn_event("no-scope", "2018-01-02", scopes=["VNX50"]),
            kn_event("no-title", "2018-01-02", title="  "),
            kn_event("no-source", "2018-01-02", sources=["s_missing", "s_nodate"], numbers=[]),
            "not an object",
        ]
        ok = kn_event("ok", "2018-01-02")
        kept, info, warnings = self.keynotes(bad + [ok, dict(ok, title="trùng")])
        self.assertEqual([k["id"] for k in kept], ["ok"])
        self.assertEqual(kept[0]["title"], "Tiêu đề ok")  # the first of a duplicated id wins
        self.assertEqual((info["n"], info["n_dropped"]), (1, len(bad) + 1))
        self.assertEqual(len(warnings), 1, warnings)
        for frag in ("Bỏ 11 keynote", "future (ngày trong tương lai)", "bad-kind (kind sai)", "#9 (không phải object)",
                     "no-source (không có nguồn hợp lệ", "ok (trùng id)"):
            self.assertIn(frag, warnings[0])

    def test_unresolved_narrative_sources_force_unverified(self):
        ev = kn_event("typo-src", "2018-01-02", tier="FACT-T1", sources=["s_typo_news"],
                      numbers=[dict(CLOSE_NUM, asof="2018-01-02")])        # only the data number resolves
        kept, _, warnings = self.keynotes([ev])
        self.assertEqual(len(kept), 1)
        k = kept[0]
        self.assertEqual((k["tier"], k["tier_effective"]), ("FACT-T1", "UNVERIFIED"))
        self.assertTrue(any("không có nguồn truy được" in w for w in k["warnings"]))
        ok = kn_event("claim-only", "2018-01-02", sources=["s_typo_news"],
                      claims=[{"src": ["s_news_a", "s_news_b"], "tier": "NEWS"}])
        kept, _, _ = self.keynotes([ok])
        self.assertEqual(kept[0]["tier_effective"], "NEWS")                  # a resolved claim backs the narrative

    def test_event_own_warnings_carried(self):
        ev = kn_event("warned", "2018-01-02", warnings=["Điểm σ-cực trị P/E, không phải pivot giá", "x" * 400, 7, "  "]
                      + ["w%d" % i for i in range(10)])
        kept, _, _ = self.keynotes([ev])
        w = kept[0]["warnings"]
        self.assertEqual(w[0], "Điểm σ-cực trị P/E, không phải pivot giá")
        self.assertEqual(len(w[1]), hv.SOURCE_TEXT_LEN)
        self.assertTrue(w[1].endswith("…"))
        self.assertEqual(len(w), hv.MAX_RAW_WARNINGS)                       # non-strings / blanks skipped, capped

    def test_news_rule_downgrades(self):
        cases = {
            "one-news": (["s_news_a"], None, "UNVERIFIED"),
            "same-org": (["s_news_a", "s_news_a2"], None, "UNVERIFIED"),         # 2 domains, 1 org
            "same-domain": (["s_news_b", "s_news_c"], None, "UNVERIFIED"),       # 2 orgs, 1 domain
            "data-not-corroboration": (["s_news_a", "s_vc"], None, "UNVERIFIED"),  # data sources excluded
            "two-independent": (["s_news_a", "s_news_b"], None, "NEWS"),
            "news-plus-filing": (["s_news_a", "s_hose"], None, "NEWS"),
            "claim-fails": (["s_news_a", "s_news_b"], [{"src": ["s_news_a", "s_news_b"]}, {"src": "s_news_c"}],
                            "UNVERIFIED"),
            "claim-ok": (["s_news_a"], [{"src": ["s_news_a", "s_hose"]}, {"src": ["s_hose"], "tier": "FACT-T1"}],
                         "NEWS"),
        }
        events = [kn_event(k, "2018-01-02", sources=s, **({"claims": c} if c else {})) for k, (s, c, _) in cases.items()]
        kept, _, warnings = self.keynotes(events)
        self.assertEqual(warnings, [])
        got = {k["id"]: k for k in kept}
        for kid, (_, _, want) in cases.items():
            self.assertEqual(got[kid]["tier_effective"], want, kid)
            self.assertEqual(got[kid]["tier"], "NEWS", kid)  # declared tier kept
            self.assertEqual(any(w.startswith("UNVERIFIED") for w in got[kid]["warnings"]), want == "UNVERIFIED", kid)

    def test_numbers_sources_and_tier_fallback(self):
        ev = kn_event("mix", "2018-01-02", sources=["s_hose", "s_ghost"], tier=None, numbers=[
            CLOSE_NUM,
            dict(CLOSE_NUM, src="s_ghost"),                 # unresolvable source → dropped
            dict(CLOSE_NUM, tier="GUESS"),                  # unknown tier → dropped
            dict(CLOSE_NUM, v=NAN),                         # non-finite → dropped
            dict(CLOSE_NUM, scope="HNX"),                   # unsupported scope → dropped
            {k: v for k, v in PE_NUM.items() if k != "method"},  # EST without method → kept, warned
        ])
        del ev["tier"]
        kept, _, _ = self.keynotes([ev])
        k = kept[0]
        self.assertEqual([n["k"] for n in k["numbers"]], ["close", "pe"])
        self.assertEqual(k["tier"], "EST")  # lowest of HOSE FACT-T1, Vietcap FACT-T2, engine EST
        joined = " | ".join(k["warnings"])
        for frag in ("s_ghost", "Bỏ 4 số", "Số EST thiếu phương pháp: pe", "Thiếu bậc keynote"):
            self.assertIn(frag, joined)

    def test_long_strings_truncated_and_warned(self):
        ev = kn_event("long", "2018-01-02", title="T" * 200, boi_canh="B" * 800, nhan_phu="N" * 30,
                      key_factors=["F" * 250] + ["f%d" % i for i in range(8)])
        kept, _, warnings = self.keynotes([ev])
        k = kept[0]
        self.assertEqual(len(k["title"]), 140)
        self.assertTrue(k["title"].endswith("…"))
        self.assertEqual(len(k["boi_canh"]), 700)
        self.assertEqual(len(k["nhan_phu"]), 22)
        self.assertEqual(len(k["key_factors"]), 6)
        self.assertEqual(len(k["key_factors"][0]), 200)
        self.assertIn("Cắt ngắn: boi_canh, key_factors, nhan_phu, title", k["warnings"])
        self.assertEqual(len(warnings), 1)
        self.assertIn("long", warnings[0])

    def test_cap_keeps_highest_priority(self):
        events = [kn_event("e%02d" % i, "2018-01-%02d" % (i % 28 + 1) if i < 28 else "2019-02-%02d" % (i % 28 + 1),
                           priority=3 if i < 5 else 1) for i in range(65)]
        kept, info, warnings = self.keynotes(events)
        self.assertEqual(len(kept), hv.MAX_KEYNOTES)
        self.assertEqual((info["n"], info["n_dropped"]), (60, 5))
        self.assertTrue(all(k["priority"] == 1 for k in kept))
        self.assertEqual([k["ms"] for k in kept], sorted(k["ms"] for k in kept))
        self.assertIn("vượt trần 60", warnings[0])

    def test_priority_terciles(self):
        events = [kn_event("s%d" % i, "2018-01-%02d" % (i + 1), detect={"score": float(s)})
                  for i, s in enumerate((90, 80, 70, 60, 50, 40))] + [kn_event("noscore", "2018-02-01")]
        kept, _, _ = self.keynotes(events)
        self.assertEqual({k["id"]: k["priority"] for k in kept},
                         {"s0": 1, "s1": 1, "s2": 2, "s3": 2, "s4": 3, "s5": 3, "noscore": 2})

    def test_unreadable_or_wrong_shape(self):
        path = os.path.join(self.dir, hv.KEYNOTES_FILE)
        for content in ("{not json", json.dumps({"events": {"a": 1}}), "[]"):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            d = self.overview()
            self.assertEqual(d["keynotes"], [], content)
            self.assertEqual(d["meta"]["keynotes_file"]["n"], 0)
            self.assertEqual(sum(hv.KEYNOTES_FILE in w for w in d["meta"]["warnings"]), 1, d["meta"]["warnings"])


class ForecastTest(_FixtureCase):
    def test_payload(self):
        d = self.overview()
        fc = d["forecast"]
        self.assertEqual(d["meta"]["forecast_file"]["age_hours"], 0.0)
        self.assertTrue(d["meta"]["forecast_file"]["mtime"].endswith("+07:00"))
        m = fc["meta"]
        self.assertEqual((m["generated"], m["horizon_months"], m["method"]),
                         ("2026-01-02 10:10 ICT", 36, "trung vị có trọng số"))
        self.assertEqual(m["warnings"], ["2029: không nguồn nào → quy tắc dài hạn (EST)"])  # not copied to meta
        self.assertEqual([s["id"] for s in m["sources"]], ["src_a", "ciq_bu"])
        self.assertEqual(m["sources"][1]["file"], "Estimates.xls")
        self.assertEqual(set(fc), {"meta", "VNINDEX", "VN30", "VN100"})  # VNINDEX_EXVIN3 not rendered in v1

        pe = fc["VNINDEX"]["pe"]
        ref = index_fc_block()
        self.assertEqual(pe["x0"], 3000)
        self.assertEqual(pe["points"], ref["points"])
        self.assertEqual(pe["base_path"], ref["base_path"])
        self.assertEqual(pe["points"]["fair"][0], [3000, FC_LAST["fair"]])  # joins the solid band verbatim
        self.assertEqual([g["year"] for g in pe["growth"]], [2026, 2027])
        self.assertEqual(pe["growth"][0]["sources"][1]["coverage_mcap_pct"], 87.6)
        self.assertEqual(pe["milestones"], ref["milestones"])
        self.assertEqual(pe["eps_pins"], ref["eps_pins"])
        self.assertEqual((pe["method"], pe["caveats"]), (ref["method"], ref["caveats"]))
        self.assertIsNone(fc["VNINDEX"]["pb"])  # index.pb is null → no chart → no forecast, no warning
        t = fc["VNINDEX"]["targets"]
        self.assertEqual([(x["label"], x["ms"], x["value"]) for x in t], [("12/26", 5000, 4.0)])
        self.assertEqual(t[0]["members"][0]["org"], "Org A")

        vn30 = fc["VN30"]["pe"]
        self.assertEqual(vn30["x0"], 2000)
        self.assertEqual(vn30["ratio_path"], basket_fc_block()["ratio_path"])
        self.assertEqual(vn30["flat"], BASKET_FLAT)
        self.assertEqual(vn30["milestones"][0]["zone"], CHEAP)
        self.assertIsNotNone(fc["VN30"]["pb"])
        self.assertIsNotNone(fc["VN100"]["pe"])
        self.assertIsNone(fc["VN100"]["pb"])  # null in the file and no basket block: silent
        self.assertFalse([w for w in d["meta"]["warnings"] if "Dự phóng" in w or hv.FORECAST_FILE in w])


class ForecastValidationTest(_UpgCase):
    def test_vnindex_anchor_mismatch(self):
        def as_of(fc):
            fc["scopes"]["VNINDEX"]["anchor"]["as_of"] = "2026-01-01"

        def mean(fc):
            fc["scopes"]["VNINDEX"]["anchor"]["pe"]["mean"] = 15.01

        def fair_far(fc):
            fc["scopes"]["VNINDEX"]["anchor"]["pe"]["last"]["fair"] = 3.25

        for mutate, frag in ((as_of, "neo 01/01 · dữ liệu 02/01"), (mean, "neo μ 15,01 σ 2 · dữ liệu μ 15 σ 2"),
                             (fair_far, "neo TB 3,25 · dữ liệu TB 3")):
            fc, warnings = self.with_forecast(mutate)
            self.assertIsNone(fc["VNINDEX"]["pe"], frag)
            self.assertEqual(len(fc["VNINDEX"]["targets"]), 1)  # targets do not depend on the band anchor
            self.assertIsNotNone(fc["VN30"]["pe"])               # other scopes unaffected
            w = self.fc_warnings(warnings)
            self.assertEqual(len(w), 1, w)
            self.assertIn("Dự phóng VNINDEX P/E lệch neo (%s) — chờ lượt orchestrator kế" % frag, w[0])

    def test_fair_within_tolerance_passes(self):
        def near(fc):
            a = fc["scopes"]["VNINDEX"]["anchor"]["pe"]["last"]
            a["fair"] = 3.15
            fc["scopes"]["VNINDEX"]["pe"]["points"]["fair"][0][1] = 3.15
        fc, warnings = self.with_forecast(near)
        self.assertIsNotNone(fc["VNINDEX"]["pe"])
        self.assertEqual(self.fc_warnings(warnings), [])

    def test_basket_anchor_mismatch(self):
        def p1(fc):
            fc["scopes"]["VN30"]["anchor"]["pb"]["p1"] = 11.1

        fc, warnings = self.with_forecast(p1)
        self.assertIsNone(fc["VN30"]["pb"])
        self.assertIsNotNone(fc["VN30"]["pe"])
        w = self.fc_warnings(warnings)
        self.assertEqual(len(w), 1, w)
        self.assertIn("Dự phóng VN30 P/B lệch neo (neo p1 11,1 · dữ liệu 11)", w[0])

        fc, warnings = self.with_forecast(lambda f: f["scopes"]["VN100"]["anchor"].update(as_of="2025-12-31"))
        self.assertIsNone(fc["VN100"]["pe"])
        self.assertIn("neo 31/12 · dữ liệu 02/01", self.fc_warnings(warnings)[0])

    def test_shape_errors_drop_block(self):
        def pts(fc):
            return fc["scopes"]["VNINDEX"]["pe"]["points"]

        def all_levels(fn):
            return lambda f: [fn(pts(f)[k]) for k in ("fair", "cheap1", "cheap2", "rich1", "rich2")]

        cases = {  # name: (mutation, reason expected in the warning)
            "not ascending": (all_levels(lambda s: s[2].__setitem__(0, 3500)), "points.fair trục thời gian không tăng"),
            "one point": (lambda f: pts(f).__setitem__("cheap2", pts(f)["cheap2"][:1]), "points.cheap2 1 điểm"),
            "61 points": (lambda f: pts(f).__setitem__("fair", [[3000 + i, 3.0] for i in range(61)]),
                          "points.fair 61 điểm (cần 2–60)"),
            "first x": (all_levels(lambda s: [p.__setitem__(0, p[0] + 1) for p in s]), "không trùng anchor.ms"),
            "missing level": (lambda f: pts(f).pop("rich2"), "points.rich2 thiếu"),
            "first value": (lambda f: pts(f)["cheap1"][0].__setitem__(1, 2.61), "điểm đầu khác anchor.pe.last.cheap1"),
            "grid differs": (lambda f: pts(f)["rich2"][3].__setitem__(0, 6500), "không cùng lưới thời gian"),
            "non-integral x": (lambda f: pts(f)["fair"][1].__setitem__(0, 4000.5), "không hữu hạn/sai dạng"),
            "string value": (lambda f: pts(f)["fair"][1].__setitem__(1, "3.3"), "không hữu hạn/sai dạng"),
            "no growth": (lambda f: f["scopes"]["VNINDEX"]["pe"].__setitem__("growth", [{"year": "2026", "g": 0.1}]),
                          "growth[] không có năm hợp lệ"),
        }
        for name, (mutate, reason) in cases.items():
            fc, warnings = self.with_forecast(mutate)
            self.assertIsNone(fc["VNINDEX"]["pe"], name)
            w = self.fc_warnings(warnings)
            self.assertEqual(len(w), 1, (name, w))
            self.assertIn("Dự phóng VNINDEX P/E bỏ: ", w[0], name)
            self.assertIn(reason, w[0], name)
            self.assertIn("hhp_forecast_bridge.py", w[0], name)

    def test_nan_in_points_drops_block_and_output_stays_strict(self):
        def nan(fc):
            fc["scopes"]["VN30"]["pe"]["ratio_path"][1][1] = NAN
            fc["scopes"]["VN30"]["pb"]["growth"][0]["sources"][0]["value"] = NAN  # pass-through field → null

        fc, warnings = self.with_forecast(nan)  # run_script parses with NaN/Infinity rejected
        self.assertIsNone(fc["VN30"]["pe"])
        self.assertIsNone(fc["VN30"]["pb"]["growth"][0]["sources"][0]["value"])
        self.assertIn("Dự phóng VN30 P/E bỏ: ratio_path có điểm không hữu hạn", self.fc_warnings(warnings)[0])

    def test_basket_flat_and_missing_metric(self):
        fc, warnings = self.with_forecast(lambda f: f["scopes"]["VN30"]["pe"]["flat"].update(m2=9.4))
        self.assertIsNone(fc["VN30"]["pe"])
        self.assertIn("flat khác mức", self.fc_warnings(warnings)[0])

        # VN100 has no P/B basket block: a forecast block for it cannot be anchored → null + warning.
        fc, warnings = self.with_forecast(lambda f: f["scopes"]["VN100"].update(pb=basket_fc_block()))
        self.assertIsNone(fc["VN100"]["pb"])
        self.assertIn("Dự phóng VN100 P/B bỏ: dữ liệu hiện tại không có khối P/B để neo", self.fc_warnings(warnings)[0])

    def test_vn30_pe_null_passes_through(self):
        def vn30_pe_absent(fc):  # the real 26/09/2026 data: VN30 P/E absent upstream → null both sides
            fc["scopes"]["VN30"]["anchor"]["pe"] = None
            fc["scopes"]["VN30"]["pe"] = None
        path = os.path.join(self.dir, hv.BASKETS_FILE)
        baskets = hv.load_json(path)
        baskets["baskets"][1]["pe"] = None
        write_json(path, baskets)
        fc, warnings = self.with_forecast(vn30_pe_absent)
        self.assertIsNone(fc["VN30"]["pe"])
        self.assertIsNotNone(fc["VN30"]["pb"])
        self.assertEqual(self.fc_warnings(warnings), [])

    def test_targets_need_full_provenance(self):
        def targets(fc):
            ok = fc["scopes"]["VNINDEX"]["targets"][0]
            no_url = copy.deepcopy(ok)
            no_url["members"][0].pop("url")
            bad_tier = copy.deepcopy(ok)
            bad_tier["members"][0]["tier"] = "UNVERIFIED"
            mixed = dict(copy.deepcopy(ok), id="t-mixed")  # only the undated member goes; median re-taken from the rest
            mixed["members"] += [dict(ok["members"][0], org="Org B", value=5.0, date=None),
                                 dict(ok["members"][0], org="Org C", value=6.0)]
            later = dict(copy.deepcopy(ok), id="t-2027-06", ms=7000, label="06/27")
            fc["scopes"]["VNINDEX"]["targets"] = [later, no_url, bad_tier, mixed, ok]

        fc, warnings = self.with_forecast(targets)
        t = fc["VNINDEX"]["targets"]
        self.assertEqual([x["id"] for x in t], ["t-mixed", "t-2026-12", "t-2027-06"])  # sorted by ms
        mixed = t[0]
        self.assertEqual([m["org"] for m in mixed["members"]], ["Org A", "Org C"])
        self.assertEqual((mixed["value"], mixed["label"]), (5.0, "2 nguồn 01/70"))    # median of 4 and 6, not 4
        self.assertEqual((t[1]["value"], t[1]["label"]), (4.0, "12/26"))              # untouched target passes as is
        w = " | ".join(self.fc_warnings(warnings))
        self.assertIn("Bỏ 2 mục tiêu", w)                     # single-member targets with no valid member
        self.assertIn("t-mixed bỏ 1/3", w)

    def test_file_level_failures(self):
        path = os.path.join(self.dir, hv.FORECAST_FILE)
        for content in ("{nope", json.dumps({"meta": {"schema": "hhp_forecast/2"}, "scopes": {}}),
                        json.dumps({"meta": {"schema": "hhp_forecast/1"}, "scopes": []})):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            d = self.overview()
            self.assertIsNone(d["forecast"], content)
            self.assertIsNotNone(d["meta"]["forecast_file"])
            self.assertEqual(len(self.fc_warnings(d["meta"]["warnings"])), 1, d["meta"]["warnings"])

    def test_stale_file_warns_but_shows(self):
        path = os.path.join(self.dir, hv.FORECAST_FILE)
        old = time.time() - 31 * 3600
        os.utime(path, (old, old))
        d = self.overview()
        self.assertIsNotNone(d["forecast"]["VNINDEX"]["pe"])
        self.assertAlmostEqual(d["meta"]["forecast_file"]["age_hours"], 31.0, delta=0.2)
        self.assertEqual(d["forecast"]["meta"]["age_hours"], d["meta"]["forecast_file"]["age_hours"])
        w = self.fc_warnings(d["meta"]["warnings"])
        self.assertEqual(len(w), 1, w)
        self.assertIn("31 giờ chưa làm mới", w[0])

    def test_bad_sources_dropped(self):
        fc, warnings = self.with_forecast(lambda f: f["sources"].append({"id": "x", "org": "X", "date": "2026-01-01",
                                                                        "tier": "SS-T3"}))  # no url / file
        self.assertEqual([s["id"] for s in fc["meta"]["sources"]], ["src_a", "ciq_bu"])
        self.assertIn("Bỏ 1 nguồn dự phóng", self.fc_warnings(warnings)[0])


class TickerForecastTest(_UpgCase):
    """ticker <TK> → forecast / keynotes / meta (hhp_forecast_tickers/<TK>.json, hhp_keynotes_tickers/<TK>.json)."""

    FC_NAME = "hhp_forecast_tickers/AAA.json"

    def ticker(self, tk="AAA"):
        rc, d, text = run_script(["ticker", tk], self.dir)  # strict parse: NaN/Infinity tokens rejected
        self.assertEqual(rc, 0)
        self.assertNotIn("error", d, d.get("error"))
        self.assertEqual(text.strip().count("\n"), 0)
        return d

    def with_ticker_fc(self, mutate, tk="AAA", fixture=ticker_fc_fixture):
        fc = fixture()
        mutate(fc)
        write_json(os.path.join(self.dir, hv.TICKER_FC_DIR, tk + ".json"), fc)
        d = self.ticker(tk)
        return d["forecast"], d["meta"]["warnings"]

    def test_payload_joins_the_solid_bands(self):
        d = self.ticker()
        self.assertEqual(d["meta"]["warnings"], [])
        self.assertEqual(d["meta"]["forecast_file"]["age_hours"], 0.0)
        self.assertTrue(d["meta"]["forecast_file"]["mtime"].endswith("+07:00"))
        fc = d["forecast"]
        self.assertEqual(set(fc), {"meta", "pe", "pb", "skip", "targets"})
        m = fc["meta"]
        self.assertEqual((m["generated"], m["horizon_months"], m["method"], m["age_hours"]),
                         ("2026-01-02 10:12 ICT", 36, "trung vị có trọng số theo mã", 0.0))
        self.assertTrue(m["unit"].startswith("nghìn đồng"))
        self.assertEqual(m["caveats"], ["Tham khảo, không khuyến nghị"])
        self.assertEqual(m["warnings"], ["2027: không nguồn → quy tắc dài hạn (EST)"])  # not copied to meta.warnings
        self.assertEqual([s["id"] for s in m["sources"]], ["vc_cov"])
        self.assertEqual(m["price_scale"], TK_SCALE)  # provenance of every target's scale
        self.assertNotIn("fy_last", m)

        pe, ref, chart = fc["pe"], tk_fc_block(AAA_PE_LAST), d["pe"]["chart"]
        self.assertEqual(pe["x0"], TK_X0)
        self.assertEqual(pe["points"], ref["points"])
        for k in TK_LEVELS:  # the dashed line starts exactly where the solid band ends
            self.assertEqual(len(pe["points"][k]), 37, k)
            self.assertEqual(pe["points"][k][0], chart[k][-1], k)
        for key in ("base_path", "growth", "eps_pins", "milestones", "method"):
            self.assertEqual(pe[key], ref[key], key)
        self.assertIs(pe["reliable"], True)
        self.assertEqual(pe["growth"][0]["sources"][0]["note"], "LN sau thuế cổ đông mẹ ≈ EPS nếu số CP không đổi")
        self.assertIsNone(fc["pb"])
        self.assertEqual(fc["skip"], {"pe": None, "pb": "σ P/B không hữu hạn"})  # the bridge's reason, verbatim

        t = fc["targets"]
        self.assertEqual([x["id"] for x in t], ["ciq-tp", "vc-tp"])  # sorted by ms
        self.assertEqual(t[1], VC_TARGET)
        self.assertNotIn("rating", t[0])
        for x in t:
            self.assertAlmostEqual(x["value"], x["value_vnd"] / 1000 * x["scale"], places=6)

    def test_pb_with_retention_and_bridge_skip(self):
        fc, warnings = self.with_ticker_fc(lambda f: None, tk="BBB", fixture=bbb_fc_fixture)
        self.assertEqual(warnings, [])
        self.assertIsNone(fc["pe"])
        self.assertEqual(fc["skip"], {"pe": "không có chuỗi P/E", "pb": None})
        pb = fc["pb"]
        self.assertEqual(pb["x0"], 1000)
        self.assertEqual(pb["points"]["cheap2"][0], [1000, 4.0])
        self.assertEqual(pb["retention"], {"r": 0.55, "per_year": [{"year": 2025, "r": 0.55}], "fallback": False})
        self.assertIs(pb["reliable"], False)  # unreliable still ships; the dialog warns
        self.assertEqual(fc["targets"], [])

    def test_anchor_mismatch_nulls_that_metric(self):
        def anchor(fc):
            return fc["anchor"]["pe"]

        cases = (
            (lambda f: f["anchor"].update(as_of="2026-01-01"), "neo 01/01 · dữ liệu 02/01"),
            (lambda f: anchor(f).update(sd=6.01), "neo μ 10,34 σ 6,01 · dữ liệu μ 10,34 σ 6"),
            (lambda f: anchor(f)["last"].update(fair=20.69), "neo TB 20,69 · dữ liệu TB 20,67"),
            (lambda f: f["anchor"].update(pe=None), "neo μ ? σ ? · dữ liệu μ 10,34 σ 6"),
        )
        for mutate, frag in cases:
            fc, warnings = self.with_ticker_fc(mutate)
            self.assertIsNone(fc["pe"], frag)
            self.assertEqual(fc["skip"]["pe"], "lệch neo (%s)" % frag)
            self.assertEqual(len(fc["targets"]), 2, frag)  # ◆ targets do not depend on the band anchor
            self.assertEqual(warnings, ["Dự phóng AAA P/E lệch neo (%s) — chờ lượt orchestrator kế" % frag])

    def test_fair_within_tolerance_passes(self):
        def near(fc):
            fc["anchor"]["pe"]["last"]["fair"] = 20.68  # 0.01 off the series' 20.67 (both 2-decimal)
            fc["pe"]["points"]["fair"][0][1] = 20.68
        fc, warnings = self.with_ticker_fc(near)
        self.assertIsNotNone(fc["pe"])
        self.assertEqual(warnings, [])

    def test_shape_errors_drop_the_metric(self):
        def pts(f):
            return f["pe"]["points"]

        def all_levels(fn):
            return lambda f: [fn(pts(f)[k]) for k in TK_LEVELS]

        cases = {  # name: (mutation, reason expected in the warning and in skip.pe)
            "36 points": (all_levels(lambda s: s.pop()), "points.fair 36 điểm (cần 37)"),
            "not ascending": (all_levels(lambda s: s[2].__setitem__(0, TK_X0 + 500)), "trục thời gian không tăng"),
            "first x": (all_levels(lambda s: [p.__setitem__(0, p[0] + 1) for p in s]), "không trùng anchor.ms"),
            "first value": (lambda f: pts(f)["cheap1"][0].__setitem__(1, 8.68), "điểm đầu khác anchor.pe.last.cheap1"),
            "missing level": (lambda f: pts(f).pop("rich2"), "points.rich2 thiếu"),
            "grid differs": (lambda f: pts(f)["rich2"][3].__setitem__(0, TK_X0 + 3001), "không cùng lưới thời gian"),
            "NaN": (lambda f: pts(f)["fair"][5].__setitem__(1, NAN), "points.fair có điểm không hữu hạn"),
            "points not an object": (lambda f: f["pe"].__setitem__("points", []), "points.fair thiếu"),
            "no growth": (lambda f: f["pe"].__setitem__("growth", [{"year": "2026", "g": 0.1}]),
                          "growth[] không có năm hợp lệ"),
        }
        for name, (mutate, reason) in cases.items():
            fc, warnings = self.with_ticker_fc(mutate)
            self.assertIsNone(fc["pe"], name)
            self.assertIn(reason, fc["skip"]["pe"], name)
            self.assertEqual(len(warnings), 1, (name, warnings))
            self.assertTrue(warnings[0].startswith("Dự phóng AAA P/E bỏ: "), (name, warnings))
            self.assertIn(reason, warnings[0], name)
            self.assertIn("(%s sai định dạng) — Chạy:" % self.FC_NAME, warnings[0], name)
            self.assertEqual(len(fc["targets"]), 2, name)

    def test_bad_base_path_drops_only_the_path(self):
        fc, warnings = self.with_ticker_fc(lambda f: f["pe"]["base_path"][0].__setitem__(0, TK_X0 - 1))
        self.assertIsNotNone(fc["pe"])
        self.assertIsNone(fc["pe"]["base_path"])
        self.assertEqual(warnings, ["Dự phóng AAA P/E: base_path điểm đầu không trùng anchor.ms — bỏ base_path"])

    def test_metric_anchors_on_different_days(self):
        # EEE: P/E stopped in 2021 upstream, P/B runs to 2025-12-20 → the bridge writes anchor.<m>.as_of / .ms,
        # which override the file-level ones (those follow P/E).
        pe_last = {"price": 30.0, "base": 0.2, "fair": 20.0, "cheap1": 10.0, "cheap2": 0.0, "rich1": 30.0, "rich2": 40.0}
        pb_last = {"price": 30.0, "base": 20.0, "fair": 32.0, "cheap1": 28.0, "cheap2": 24.0, "rich1": 36.0, "rich2": 40.0}

        def eee(pb_as_of="2025-12-20"):
            fc = ticker_fc_fixture()
            fc["meta"]["ticker"] = "EEE"
            fc["anchor"] = {"as_of": "2021-11-30", "ms": 999,  # file-level ms deliberately off: per-metric ms wins
                            "pe": {"as_of": "2021-11-30", "ms": 1000, "mean": 100.0, "sd": 50.0, "last": pe_last},
                            "pb": {"as_of": pb_as_of, "ms": 1000, "mean": 1.6, "sd": 0.2, "last": pb_last}}
            fc["pe"], fc["pb"] = tk_fc_block(pe_last, x0=1000), tk_fc_block(pb_last, x0=1000)
            fc["skip"], fc["targets"] = {"pe": None, "pb": None}, []
            return fc

        fc, warnings = self.with_ticker_fc(lambda f: None, tk="EEE", fixture=eee)
        self.assertEqual(warnings, [])
        self.assertEqual((fc["pe"]["x0"], fc["pb"]["x0"]), (1000, 1000))
        self.assertEqual(fc["pb"]["points"]["cheap2"][0], [1000, 24.0])

        fc, warnings = self.with_ticker_fc(lambda f: None, tk="EEE", fixture=lambda: eee(pb_as_of="2021-11-30"))
        self.assertIsNotNone(fc["pe"])
        self.assertIsNone(fc["pb"])
        self.assertEqual(warnings, ["Dự phóng EEE P/B lệch neo (neo 30/11 · dữ liệu 20/12) — chờ lượt orchestrator kế"])

    def test_metric_absent_from_series(self):
        # BBB's series has no P/E: a P/E block cannot be anchored → null + warning (a null block stays silent).
        fc, warnings = self.with_ticker_fc(lambda f: f.update(pe=tk_fc_block(AAA_PE_LAST)), tk="BBB",
                                           fixture=bbb_fc_fixture)
        self.assertIsNone(fc["pe"])
        self.assertIsNotNone(fc["pb"])
        why = "hhp_vn100_series/BBB.json không có khối P/E để neo"
        self.assertEqual(fc["skip"]["pe"], why)
        self.assertEqual(warnings, ["Dự phóng BBB P/E bỏ: " + why])

    def test_targets_drop_only_bad_members(self):
        no_src = {k: v for k, v in VC_TARGET.items() if k != "file"}

        def targets(fc):
            fc["targets"] = [
                dict(VC_TARGET, id="no-tier", tier="UNVERIFIED"),
                dict(no_src, id="no-src"),
                dict(no_src, id="url-tp", url="https://vc.invalid/tp", ms=10000),   # url instead of a file: fine
                dict(VC_TARGET, id="dong", value=15000.0),                         # đồng on a nghìn-đồng chart
                dict(VC_TARGET, id="expired", ms=TK_X0),                           # not after the anchor
                dict(VC_TARGET, id="no-org", org=" "),
                dict(VC_TARGET, id="no-scale", scale=0),
                dict(VC_TARGET, id="no-ms", ms=NAN),
                "junk",
                dict(VC_TARGET), dict(CIQ_TARGET),
            ]

        fc, warnings = self.with_ticker_fc(targets)
        self.assertIsNotNone(fc["pe"])
        self.assertEqual([t["id"] for t in fc["targets"]], ["ciq-tp", "vc-tp", "url-tp"])
        self.assertEqual(len(warnings), 1, warnings)
        w = warnings[0]
        self.assertTrue(w.startswith("Bỏ 8 mục tiêu giá của mã: "), w)
        for frag in ("no-tier (bậc không phải FACT-T1/FACT-T2/SS-T3)", "no-src (thiếu url/tệp nguồn)",
                     "dong (value 15.000 lệch value_vnd/1000 × scale = 19,5)", "expired (hết hạn",
                     "no-org (thiếu org/ngày)", "no-scale (thiếu ms/value", "no-ms (thiếu ms/value", "#8 (không phải object)",
                     self.FC_NAME):
            self.assertIn(frag, w)

    def test_no_file_warns_with_the_bridge_reason(self):
        d = self.ticker("BBB")  # no hhp_forecast_tickers/BBB.json in the fixture
        self.assertIsNone(d["forecast"])
        self.assertIsNone(d["meta"]["forecast_file"])
        self.assertEqual(len(d["meta"]["warnings"]), 1)
        self.assertIn("Chưa có hhp_forecast_tickers/BBB.json — dự phóng 3 năm của mã tắt. ", d["meta"]["warnings"][0])

        write_json(os.path.join(self.dir, hv.TICKER_FC_DIR, hv.TICKER_FC_INDEX),
                   {"generated": "2026-01-02 10:12 ICT", "n_ok": 1, "n_skip": 1, "tickers": ["AAA"],
                    "skipped": {"BBB": "không có chuỗi giá/EPS"}})
        w = self.ticker("BBB")["meta"]["warnings"]
        self.assertEqual(len(w), 1)
        self.assertIn("dự phóng 3 năm của mã tắt (bridge bỏ mã: không có chuỗi giá/EPS). Chạy:", w[0])

    def test_file_level_failures(self):
        path = os.path.join(self.dir, hv.TICKER_FC_DIR, "AAA.json")
        wrong_ticker = ticker_fc_fixture()
        wrong_ticker["meta"]["ticker"] = "BBB"
        wrong_schema = ticker_fc_fixture()
        wrong_schema["meta"]["schema"] = "hhp_forecast/1"
        for content in ("{nope", json.dumps(wrong_ticker), json.dumps(wrong_schema), "[]"):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            d = self.ticker()
            self.assertIsNone(d["forecast"], content[:40])
            self.assertIsNotNone(d["meta"]["forecast_file"])
            self.assertEqual(len(d["meta"]["warnings"]), 1, d["meta"]["warnings"])
            self.assertIn(self.FC_NAME, d["meta"]["warnings"][0])
            self.assertIn("dự phóng tắt", d["meta"]["warnings"][0])

    def test_stale_file_warns_but_shows(self):
        path = os.path.join(self.dir, hv.TICKER_FC_DIR, "AAA.json")
        old = time.time() - 31 * 3600
        os.utime(path, (old, old))
        d = self.ticker()
        self.assertIsNotNone(d["forecast"]["pe"])
        self.assertAlmostEqual(d["meta"]["forecast_file"]["age_hours"], 31.0, delta=0.2)
        self.assertEqual(d["forecast"]["meta"]["age_hours"], d["meta"]["forecast_file"]["age_hours"])
        self.assertEqual(len(d["meta"]["warnings"]), 1)
        self.assertIn("31 giờ chưa làm mới", d["meta"]["warnings"][0])

    def test_bad_sources_dropped(self):
        fc, warnings = self.with_ticker_fc(lambda f: f["sources"].append({"id": "x", "org": "X", "date": "2026-01-01",
                                                                         "tier": "SS-T3"}))  # no url / file
        self.assertEqual([s["id"] for s in fc["meta"]["sources"]], ["vc_cov"])
        self.assertEqual(warnings, ["Bỏ 1 nguồn dự phóng thiếu id/org/ngày/bậc/url (%s)" % self.FC_NAME])

    def test_price_scale_needs_a_positive_scale(self):
        for bad in (None, {"scale": 0}, {"scale": NAN, "src": "x"}, {"series": 13.0}):
            fc, _ = self.with_ticker_fc(lambda f: f["meta"].__setitem__("price_scale", bad))
            self.assertIsNone(fc["meta"]["price_scale"], bad)

    def test_ticker_keynotes_present(self):
        d = self.ticker()
        kn = d["keynotes"]
        self.assertEqual([k["id"] for k in kn], ["2023-10-day", "2024-03-dinh"])  # by date
        self.assertEqual([k["scopes"] for k in kn], [["AAA"], ["AAA"]])           # upper-cased
        self.assertEqual(kn[1]["numbers"][0]["scope"], "AAA")
        self.assertEqual(kn[1]["tier_effective"], "FACT-T1")
        self.assertEqual(kn[0]["ms"], utc_ms(2023, 10, 30))
        info = d["meta"]["keynotes_file"]
        self.assertEqual((info["n"], info["n_dropped"]), (2, 0))
        self.assertTrue(info["mtime"].endswith("+07:00"))
        self.assertEqual(d["meta"]["warnings"], [])

    def test_ticker_keynotes_validated_like_the_index_file(self):
        # Same rule as hhp_keynotes_tickers.py's own validator: scopes ⊂ {AAA, VNINDEX, VN30, VN100}.
        raw = ticker_keynotes_fixture()
        raw["events"] += [
            kn_event("other-ticker", "2022-11-15", kind="day", scopes=["BBB"]),
            kn_event("mixed", "2022-06-01", scopes=["AAA", "VNINDEX", "BBB"],
                     numbers=[dict(CLOSE_NUM, k="vni_close"), dict(CLOSE_NUM, scope="AAA"),
                              dict(CLOSE_NUM, scope="BBB")]),                 # VN-Index context kept; BBB dropped
            kn_event("future", "2099-01-01", scopes=["AAA"]),
        ]
        write_json(os.path.join(self.dir, hv.TICKER_KN_DIR, "AAA.json"), raw)
        d = self.ticker()
        kn = {k["id"]: k for k in d["keynotes"]}
        self.assertEqual(sorted(kn), ["2023-10-day", "2024-03-dinh", "mixed"])
        self.assertEqual(kn["mixed"]["scopes"], ["AAA", "VNINDEX"])
        self.assertEqual([(n["k"], n["scope"]) for n in kn["mixed"]["numbers"]], [("vni_close", "VNINDEX"),
                                                                                  ("close", "AAA")])
        self.assertIn("Bỏ phạm vi không hỗ trợ: BBB", kn["mixed"]["warnings"])
        self.assertIn("Bỏ 1 số thiếu nguồn/bậc/giá trị", kn["mixed"]["warnings"])
        self.assertEqual((d["meta"]["keynotes_file"]["n"], d["meta"]["keynotes_file"]["n_dropped"]), (3, 2))
        w = [x for x in d["meta"]["warnings"] if "keynote" in x]
        self.assertEqual(len(w), 1, d["meta"]["warnings"])
        for frag in ("Bỏ 2 keynote sai định dạng", "other-ticker (scopes rỗng/sai)", "future (ngày trong tương lai)",
                     "Chạy: python3 hhp_keynotes_tickers.py --tickers AAA (thư mục knowledge_os)"):
            self.assertIn(frag, w[0])

    def test_matches_the_keynote_builders_validator(self):
        # hhp_keynotes_tickers.py validates by widening KEYNOTE_SCOPES and calling load_keynotes; that must keep
        # working (and agree with the ticker reader) after load_keynotes became a wrapper.
        raw = ticker_keynotes_fixture()
        raw["events"][0]["numbers"].append(dict(CLOSE_NUM, k="vni_close"))
        tmp = os.path.join(self.tmp, "builder")
        write_json(os.path.join(tmp, hv.KEYNOTES_FILE), raw)
        old, warns = hv.KEYNOTE_SCOPES, []
        hv.KEYNOTE_SCOPES = tuple(old) + ("AAA",)
        try:
            kept, info = hv.load_keynotes(tmp, warns, date(2026, 1, 2))
        finally:
            hv.KEYNOTE_SCOPES = old
        self.assertEqual((warns, info["n_dropped"], len(kept)), ([], 0, 2))
        write_json(os.path.join(self.dir, hv.TICKER_KN_DIR, "AAA.json"), raw)
        d = self.ticker()
        self.assertEqual(d["meta"]["warnings"], [])
        self.assertEqual([k["numbers"] for k in d["keynotes"]], [k["numbers"] for k in kept])

    def test_ticker_keynotes_absent_or_unreadable(self):
        d = self.ticker("BBB")  # no hhp_keynotes_tickers/BBB.json → [] and silent
        self.assertEqual(d["keynotes"], [])
        self.assertIsNone(d["meta"]["keynotes_file"])
        self.assertFalse([w for w in d["meta"]["warnings"] if "keynote" in w])

        with open(os.path.join(self.dir, hv.TICKER_KN_DIR, "AAA.json"), "w", encoding="utf-8") as fh:
            fh.write("{bad")
        d = self.ticker()
        self.assertEqual(d["keynotes"], [])
        self.assertEqual(d["meta"]["keynotes_file"]["n"], 0)
        self.assertEqual(len(d["meta"]["warnings"]), 1)
        self.assertIn("Không đọc được hhp_keynotes_tickers/AAA.json", d["meta"]["warnings"][0])
        self.assertIsNotNone(d["forecast"]["pe"])  # the forecast does not depend on the keynote file


class OverviewHistoryFileTest(unittest.TestCase):
    """FINAL_PLAN M17: the overview gains meta.history_file and nothing else."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hhp_ovh_")
        self.dir = os.path.join(self.tmp, "d")
        build_fixture(self.dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def overview(self):
        rc, d, _ = run_script(["overview"], self.dir)
        self.assertEqual(rc, 0)
        self.assertNotIn("error", d, d.get("error"))
        return d

    def test_matches_the_pre_change_golden(self):
        d = normalize_overview(self.overview())
        self.assertIsNone(d["meta"].pop("history_file"))  # no hhp_vnindex_history.json in build_fixture()
        if os.environ.get("HHP_REGEN_GOLDEN") == "1":
            with open(OVERVIEW_GOLDEN, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False, indent=1, sort_keys=True)
                fh.write("\n")
            self.skipTest("golden regenerated")
        with open(OVERVIEW_GOLDEN, encoding="utf-8") as fh:
            self.assertEqual(d, json.load(fh))

    def test_history_file_changes_only_meta_history_file(self):
        before = self.overview()
        path = os.path.join(self.dir, hv.HISTORY_FILE)
        for content in (json.dumps(history_fixture()), "{not json"):  # stat only: never parsed, never warned
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            after = self.overview()
            info = after["meta"]["history_file"]
            self.assertEqual(set(info), {"mtime", "age_hours"})
            self.assertTrue(info["mtime"].endswith("+07:00"))
            self.assertEqual(info["age_hours"], 0.0)
            a, b = normalize_overview(before), normalize_overview(after)
            self.assertIsNone(a["meta"].pop("history_file"))
            b["meta"].pop("history_file")
            self.assertEqual(a, b)
        self.assertEqual(list(after["meta"])[-1], "history_file")  # appended: every other key keeps its place


class _HistoryCase(unittest.TestCase):
    """Fresh history fixture per test; helpers rewrite hhp_vnindex_history.json / hhp_forecast.json in place."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hhp_hist_")
        self.dir = os.path.join(self.tmp, "d")
        build_history_fixture(self.dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_history(self):
        """Through the CLI, strict parse (NaN / Infinity tokens rejected)."""
        rc, d, text = run_script(["history"], self.dir)
        self.assertEqual(rc, 0)
        self.assertNotIn("error", d, d.get("error"))
        self.assertEqual(text.strip().count("\n"), 0)
        return d

    def with_history(self, mutate, cli=False):
        """Rewrite the history file through `mutate(fixture)` → (history payload, meta.warnings)."""
        h = history_fixture()
        mutate(h)
        write_json(os.path.join(self.dir, hv.HISTORY_FILE), h)
        d = self.run_history() if cli else hv.build_history(self.dir)
        json.dumps(hv.clean(d), allow_nan=False)
        return d["history"], d["meta"]["warnings"]

    def with_forecast_scope(self, mutate):
        fc = forecast_fixture()
        fc["scopes"]["VNINDEX"] = history_forecast_scope()
        mutate(fc)
        write_json(os.path.join(self.dir, hv.FORECAST_FILE), fc)
        d = hv.build_history(self.dir)
        return d["history"], d["meta"]["warnings"]

    def assert_one_warning(self, warnings, *frags):
        hits = [w for w in warnings if all(f in w for f in frags)]
        self.assertEqual(len(hits), 1, (frags, warnings))


class HistoryPayloadTest(_HistoryCase):
    def test_envelope_and_warnings(self):
        d = self.run_history()
        self.assertEqual(set(d), {"meta", "history"})
        info = d["meta"]["history_file"]
        self.assertTrue(info["mtime"].endswith("+07:00"))
        self.assertEqual(info["age_hours"], 0.0)
        self.assertEqual((d["meta"]["keynotes_file"]["n"], d["meta"]["keynotes_file"]["n_dropped"]), (4, 0))
        w = d["meta"]["warnings"]
        self.assertEqual(len(w), 4, w)
        self.assert_one_warning(w, "Toàn sử P/E: bỏ 5 điểm ◇ + 1 mục also", "no-src-date (nguồn thiếu org/ngày)",
                                "unv-73 (bậc UNVERIFIED)", "after-long (không trước long.from)",
                                "no-close (thiếu close)", "bad-kind (value_kind sai)")
        self.assert_one_warning(w, "Toàn sử P/E: số đọc keynote", "1 số sai", "bỏ σ của 1 số trước long.from")
        self.assert_one_warning(w, "1 số đọc toàn sử cho keynote không có trong hhp_keynotes.json: kn-ghost")
        self.assert_one_warning(w, "priority_full ngoài 1..3 → dùng priority: kn-2020-03-day")
        self.assertNotIn("builder: cảnh báo riêng của bước 1d", " ".join(w))  # the builder's notes stay in its meta

    def test_file_level_blocks_verbatim(self):
        h, src = self.run_history()["history"], history_fixture()
        self.assertEqual(list(h), ["meta", "base", "price", "gaps", "pe", "pb", "keynotes"])
        for key in ("meta", "base", "price", "gaps"):
            self.assertEqual(h[key], src[key], key)

    def test_metric_blocks(self):
        h = self.run_history()["history"]
        for m in hv.METRICS:
            blk, src = h[m], history_metric_fixture(m)
            self.assertEqual(blk["long_from"], src["long"]["from"])
            self.assertEqual(blk["long"], src["long"], m)          # zone_key recomputed = the builder's
            self.assertEqual(blk["eight"], src["eight"], m)
            self.assertEqual(blk["seam"], src["seam"], m)
            self.assertEqual(blk["chart"], src["chart"], m)
            self.assertEqual(blk["note"], "khóa lạ — đi thẳng")     # unknown keys pass through
            self.assertNotIn("keynote_readings", blk)              # merged into keynotes instead
        self.assertIs(h["pe"]["windows_agree"], False)             # RẺ (8 năm) vs TRUNG TÍNH (dài hạn)
        self.assertIs(h["pb"]["windows_agree"], True)

    def test_points(self):
        pts = self.run_history()["history"]["pe"]["points"]
        self.assertEqual([p["id"] for p in pts], ["imf-2007-02", "cafef-lb", "kbsv-2008-12"])  # by ms
        self.assertEqual(self.run_history()["history"]["pb"]["points"], [])
        imf, lb, kbsv = pts
        self.assertEqual((imf["v"], imf["value_kind"], imf["basis"], imf["tier"], imf["close"], imf["vs_long_mean"]),
                         (53.6, "point", "top30_hcm_hn", "SS-T3", 1050.0, "above"))
        self.assertEqual(imf["src"], {k: v for k, v in H_SRC_IMF.items() if k != "quote"})
        self.assertEqual(imf["period"], {"from": "2007-01-01", "to": "2007-02-28"})
        self.assertEqual((imf["ms"], imf["date_note"]), (dms("2007-02-28"), "bình quân 01–02/2007"))
        self.assertEqual([a["v"] for a in imf["also"]], [36.0])     # the UNVERIFIED "73" is not attached
        self.assertEqual(imf["also"][0], {"v": 36.0, "value_kind": "approx", "basis": "market_trailing",
                                          "tier": "SS-T3", "src": H_SRC_WB, "date": "2006-12-29"})
        self.assertIsNone(lb["vs_long_mean"])                     # a lower bound is never coloured above/below
        self.assertEqual((kbsv["value_kind"], kbsv["vs_long_mean"]), ("approx", "below"))
        for p in pts:
            self.assertFalse(all_keys(p) & {"sigma", "sigma_long"}, p["id"])  # V3 / M11: ◇ never carries a σ

    def test_forecast(self):
        h = self.run_history()["history"]
        for m in hv.METRICS:
            fc, chart = h[m]["forecast"], h[m]["chart"]
            self.assertEqual((fc["x0"], fc["source_generated"]), (H_X0, H_FC_GEN))
            self.assertEqual(set(fc), {"x0", "source_generated", "points", "milestones", "method", "caveats"})
            for k in H_MULT:
                self.assertEqual(fc["points"][k][0], chart[k][-1], (m, k))  # no join jump at "hôm nay"
                self.assertEqual([p[0] for p in fc["points"][k]], H_FC_X)
            self.assertEqual(fc["milestones"][0]["date"], "2026-12-31")

    def test_keynotes_resliced_for_the_long_scale(self):
        kn = {k["id"]: k for k in self.run_history()["history"]["keynotes"]}
        self.assertEqual(list(kn), ["kn-2007-03-dinh", "kn-2012-01-day", "kn-2020-03-day"])  # VN30-only left out
        nums = kn["kn-2012-01-day"]["numbers"]
        self.assertEqual([(n["k"], n["scope"], n["v"]) for n in nums],
                         [("close", "VNINDEX", 336.73), ("pe", "VNINDEX", 7.61), ("pb", "VNINDEX", 1.21),
                          ("pe", None, 7.7), ("pe", "VNINDEX", 7.9), ("pb", "VNINDEX", 1.25)])
        self.assertTrue(all("sigma" not in n for n in nums[:4]))           # engine / Vietcap σ stripped …
        self.assertEqual(nums[1]["method"], "σ thang Vietcap IQ 2009→")     # … value and method kept
        self.assertEqual(nums[4], {"k": "pe", "scope": "VNINDEX", "v": 7.9, "unit": "x", "asof": "2012-01-06",
                                   "tier": "EST", "src_org": HIST_ORG, "src_date": H_GEN, "sigma": -2.9,
                                   "method": history_reading("pe", 0, "")["method"]})
        self.assertEqual(nums[5]["sigma"], -2.2)
        old = kn["kn-2007-03-dinh"]["numbers"]
        self.assertEqual([(n["k"], n["v"], n["tier"]) for n in old],
                         [("close", 1170.67, "FACT-T2"), ("pe", 53.6, "SS-T3"), ("pe", 40.0, "NEWS")])
        self.assertTrue(all("sigma" not in n for n in old))                 # a ◇ reading never has a σ
        self.assertEqual((old[1]["src_org"], old[1]["src_date"]), ("IMF", "2007-11"))
        self.assertEqual({k: kn[k]["priority_full"] for k in kn},
                         {"kn-2007-03-dinh": 1, "kn-2012-01-day": 1, "kn-2020-03-day": 1})  # absent/bad → priority
        self.assertEqual(kn["kn-2012-01-day"]["priority"], 2)
        for ev in kn.values():  # D7: every σ left on the full-history chart is a long-window reading
            for n in ev["numbers"]:
                if "sigma" in n:
                    self.assertEqual(n["src_org"], HIST_ORG, (ev["id"], n))

    def test_keynote_text_sigma_reworded_for_the_long_scale(self):
        """D7 (audit 27/09): a σ figure in the free text is an engine 12/2017→ / Vietcap 2009→ reading → the full-history
        card keeps its direction vs that scale's mean and the scale, not the figure; nhan_phu drops it; the overview
        (8 NĂM) keeps the curator's text verbatim."""
        kf = history_keynotes_fixture()
        ev = next(e for e in kf["events"] if e["id"] == "kn-2020-03-day")
        ev.update(title="Đáy Covid 659 — P/E 10,3x (−2,4σ, thang engine 12/2017→)", nhan_phu="cực trị P/E +2,1σ",
                  boi_canh="P/E chỉ +1,4σ (thang engine 12/2017→) nhờ lợi nhuận; 0σ; ±1σ; σ-cực trị",
                  nguyen_nhan="(P/E ~14,5x, −0,3σ (thang engine 12/2017→): lợi nhuận) · P/E +3σ gặp",
                  key_factors=["P/E +3,12σ (thang engine 12/2017→) · +3,10σ (thang Vietcap 2009→, cao nhất)", "Yếu tố 2"])
        write_json(os.path.join(self.dir, hv.KEYNOTES_FILE), kf)
        h = self.run_history()["history"]
        k = next(e for e in h["keynotes"] if e["id"] == "kn-2020-03-day")
        eng = "thang engine 12/2017→"
        self.assertEqual(k["title"], "Đáy Covid 659 — P/E 10,3x (dưới trung bình, %s)" % eng)
        self.assertEqual(k["nhan_phu"], "cực trị P/E")
        self.assertEqual(k["boi_canh"], "P/E chỉ trên trung bình (%s) nhờ lợi nhuận; quanh trung bình (%s); lệch trung "
                                        "bình (%s); σ-cực trị" % (eng, eng, eng))
        self.assertEqual(k["nguyen_nhan"], "(P/E ~14,5x, dưới trung bình (%s): lợi nhuận) · P/E trên trung bình (%s) gặp"
                         % (eng, eng))
        self.assertEqual(k["key_factors"], ["P/E trên trung bình (%s) · trên trung bình (thang Vietcap 2009→, cao nhất)"
                                            % eng, "Yếu tố 2"])
        for e in h["keynotes"]:
            for f in [e[x] for x, _ in hv.KEYNOTE_TEXT] + e["key_factors"]:
                self.assertNotRegex(f, r"[+−\-±]?\d+(?:,\d+)?\s?σ", (e["id"], f))
        rc, ov, _ = run_script(["overview"], self.dir)
        self.assertEqual(rc, 0)
        o = next(e for e in ov["keynotes"] if e["id"] == "kn-2020-03-day")
        self.assertEqual({f: o[f] for f in ("title", "nhan_phu", "boi_canh", "nguyen_nhan", "key_factors")},
                         {f: ev[f] for f in ("title", "nhan_phu", "boi_canh", "nguyen_nhan", "key_factors")})

    def test_overview_keeps_its_own_sigma(self):
        rc, ov, _ = run_script(["overview"], self.dir)
        self.assertEqual(rc, 0)
        kn = {k["id"]: k for k in ov["keynotes"]}
        pe = [n for n in kn["kn-2012-01-day"]["numbers"] if n["k"] == "pe"]
        self.assertEqual([(n["scope"], n.get("sigma")) for n in pe],
                         [("VNINDEX", -2.62), ("VN100", -1.9), (None, -2.5)])
        self.assertIn("kn-2025-12-dinh", kn)
        self.assertNotIn("priority_full", kn["kn-2012-01-day"])
        self.assertIsNotNone(ov["forecast"]["VNINDEX"]["pe"])  # the re-anchored fixture passes the overview too
        self.assertEqual(ov["meta"]["history_file"], self.run_history()["meta"]["history_file"])


class HistoryValidationTest(_HistoryCase):
    def test_missing_file(self):
        os.remove(os.path.join(self.dir, hv.HISTORY_FILE))
        d = self.run_history()
        self.assertIsNone(d["history"])
        self.assertIsNone(d["meta"]["history_file"])
        self.assertEqual(d["meta"]["warnings"], ["Chưa có hhp_vnindex_history.json — chạy bước 1d orchestrator_hhp.sh "
                                                 "(python3 hhp_vnindex_history.py)"])

    def test_unreadable_wrong_schema_or_no_static_file(self):
        path = os.path.join(self.dir, hv.HISTORY_FILE)
        no_static = history_fixture()
        no_static["meta"]["inputs"]["static"] = None
        cases = {"{not json": "Không đọc được", "[]": "sai định dạng",
                 json.dumps(dict(history_fixture(), meta={"schema": "hhp_vnindex_history/2"})): "sai định dạng",
                 json.dumps(no_static): "thiếu tệp tĩnh"}
        for content, frag in cases.items():
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            d = self.run_history()
            self.assertIsNone(d["history"], frag)
            self.assertIsNotNone(d["meta"]["history_file"])
            self.assertEqual(len(d["meta"]["warnings"]), 1, d["meta"]["warnings"])
            self.assertIn(frag, d["meta"]["warnings"][0])
            self.assertIn("orchestrator_hhp.sh", d["meta"]["warnings"][0])

    def test_price_shape_nulls_history(self):
        cases = {
            "1 điểm": lambda p: p.__setitem__("points", p["points"][:1]),
            "2401 điểm": lambda p: p.__setitem__("points", [[i * 86400000, 100.0] for i in range(2401)]),
            "tăng dần": lambda p: p["points"].reverse(),
            "≤ 0": lambda p: p["points"][3].__setitem__(1, 0.0),
            "không hữu hạn": lambda p: p["points"][3].__setitem__(1, NAN),
            "sai dạng": lambda p: p["points"][3].__setitem__(0, p["points"][3][0] + 0.5),
        }
        for frag, mutate in cases.items():
            h, w = self.with_history(lambda f: mutate(f["price"]))
            self.assertIsNone(h, frag)
            self.assert_one_warning(w, "price.points", frag)
        h, _ = self.with_history(lambda f: f["price"].__setitem__("points", f["price"]["points"][:2]))
        self.assertEqual(len(h["price"]["points"]), 2)  # 2 pairs is enough

    def test_engine_anchor_mismatch_keeps_the_bands(self):
        cases = {
            "(30/12 vs 02/01)": lambda f: f["meta"]["engine_as_of"].__setitem__("pe", "2025-12-30"),
            "(μ 8 năm 15,01 · engine 15)": lambda f: f["pe"]["eight"].__setitem__("mean", 15.01),
            "(hiện tại 12,4 · engine 12,5)": lambda f: f["pe"]["long"].__setitem__("now", 12.4),
        }
        for frag, mutate in cases.items():
            h, w = self.with_history(mutate)
            pe = h["pe"]
            self.assertEqual((pe["long"], pe["eight"], pe["windows_agree"], pe["forecast"]), (None,) * 4, frag)
            self.assertEqual(pe["chart"], history_chart("pe"))       # history hardly moves: bands stay
            self.assertEqual(pe["long_from"], "2011-01-04")          # titles still get their date
            self.assertEqual(len(pe["points"]), 3)
            self.assert_one_warning(w, "Toàn sử P/E lệch neo engine " + frag, "chờ lượt orchestrator kế")
            self.assertIsNotNone(h["pb"]["long"])                   # the other metric is untouched
            self.assertIsNotNone(h["pb"]["forecast"])
            self.assertEqual(sum("dự phóng" in x for x in w), 0, w)  # the anchor warning covers the forecast
            sig = [n for k in h["keynotes"] if k["id"] == "kn-2012-01-day" for n in k["numbers"] if "sigma" in n]
            self.assertEqual(len(sig), 2)                            # readings are history: kept

    def test_engine_without_index_block(self):
        path = os.path.join(self.dir, hv.CORE_FILE)
        with open(path, encoding="utf-8") as fh:
            core = json.load(fh)
        core["index"]["pb"] = None
        write_json(path, core)
        d = hv.build_history(self.dir)
        self.assertIsNone(d["history"]["pb"]["long"])
        self.assertIsNotNone(d["history"]["pb"]["chart"])
        self.assert_one_warning(d["meta"]["warnings"], "Toàn sử P/B lệch neo engine (engine không có khối index)")

    def test_shape_errors_null_the_metric(self):
        def level(k, fn):
            return lambda f: fn(f["pe"]["chart"][k])
        cases = {
            "chart.rich2 thiếu": lambda f: f["pe"]["chart"].pop("rich2"),
            "chart.fair 1 điểm": level("fair", lambda a: a.__delitem__(slice(1, None))),
            "chart.cheap1 2301 điểm": lambda f: f["pe"]["chart"].__setitem__(
                "cheap1", [[dms("2011-01-04") + i * 86400000, 1.0] for i in range(2301)]),
            "chart.cheap2 có giá trị âm": level("cheap2", lambda a: a[0].__setitem__(1, -0.1)),
            "chart.rich1 trục thời gian không tăng dần": level("rich1", lambda a: a.reverse()),
            "chart.fair có điểm không hữu hạn": level("fair", lambda a: a[2].__setitem__(1, NAN)),
            "5 đường chart không cùng lưới": level("rich2", lambda a: a[1].__setitem__(0, a[1][0] + 86400000)),
            "thiếu long.from": lambda f: f["pe"]["long"].pop("from"),
            "thiếu long.from ": lambda f: f["pe"]["long"].__setitem__("from", "2011-01"),
            "chart bắt đầu 04/01/2011, trước long.from": lambda f: f["pe"]["long"].__setitem__("from", "2011-01-05"),
        }
        for frag, mutate in cases.items():
            h, w = self.with_history(mutate)
            self.assertIsNone(h["pe"], frag)
            self.assertIsNotNone(h["pb"], frag)
            self.assert_one_warning(w, "Toàn sử P/E bỏ: " + frag.strip(), hv.HISTORY_FILE)
            kn = {k["id"]: k for k in h["keynotes"]}
            self.assertEqual([n["k"] for n in kn["kn-2012-01-day"]["numbers"] if "sigma" in n], ["pb"], frag)
        h, w = self.with_history(lambda f: f.__setitem__("pe", None))
        self.assertIsNone(h["pe"])
        self.assert_one_warning(w, "Toàn sử P/E: hhp_vnindex_history.json không có khối pe")

    def test_bad_window_blocks(self):
        h, w = self.with_history(lambda f: f["pe"]["long"].__setitem__("mean", NAN), cli=True)
        self.assertEqual((h["pe"]["long"], h["pe"]["windows_agree"]), (None, None))
        self.assertIsNotNone(h["pe"]["eight"])
        self.assertEqual(h["pe"]["chart"], history_chart("pe"))
        self.assert_one_warning(w, "Toàn sử P/E: khối long thiếu μ/σ/hiện tại hữu hạn", "[CẦN DATA]")
        h, w = self.with_history(lambda f: f["pb"]["eight"].__setitem__("sd", 0.0))
        self.assertEqual((h["pb"]["eight"], h["pb"]["windows_agree"]), (None, None))
        self.assertIsNotNone(h["pb"]["long"])

    def test_windows_agree_must_match_the_zones(self):
        for bad in (True, None, "false"):
            h, w = self.with_history(lambda f: f["pe"].__setitem__("windows_agree", bad))
            self.assertIsNone(h["pe"]["windows_agree"], bad)
            self.assert_one_warning(w, "Toàn sử P/E: windows_agree thiếu/không khớp")

    def test_forecast_checks_on_the_history_file(self):
        def pts(fn):
            return lambda f: fn(f["pe"]["forecast"]["points"])
        cases = {
            "x0 khác anchor.ms": lambda f: f["pe"]["forecast"].__setitem__("x0", H_X0 + 1),
            "source_generated 2026-01-01 10:10 ICT ≠ hhp_forecast.json 2026-01-02 10:10 ICT":
                lambda f: f["pe"]["forecast"].__setitem__("source_generated", "2026-01-01 10:10 ICT"),
            "points.fair điểm đầu khác điểm cuối chart.fair":
                pts(lambda p: p["fair"][0].__setitem__(1, p["fair"][0][1] + 0.1)),
            "points.rich2 điểm đầu không trùng anchor.ms": pts(lambda p: p["rich2"][0].__setitem__(0, H_X0 - 1)),
            "points.cheap1 1 điểm": pts(lambda p: p.__setitem__("cheap1", p["cheap1"][:1])),
            "5 đường không cùng lưới": pts(lambda p: p["cheap2"][2].__setitem__(0, p["cheap2"][2][0] + 1)),
            "lưới thời gian khác base_path": pts(lambda p: [p[k][-1].__setitem__(0, p[k][-1][0] + 1) for k in p]),
            "sai định dạng": lambda f: f["pe"].__setitem__("forecast", [1, 2]),
        }
        for frag, mutate in cases.items():
            h, w = self.with_history(mutate)
            self.assertIsNone(h["pe"]["forecast"], frag)
            self.assertIsNotNone(h["pe"]["long"], frag)
            self.assertIsNotNone(h["pb"]["forecast"], frag)
            self.assert_one_warning(w, "Toàn sử P/E: dự phóng dài hạn bỏ — " + frag)
        h, w = self.with_history(lambda f: f["pe"].__setitem__("forecast", None))  # the builder's own call: silent
        self.assertIsNone(h["pe"]["forecast"])
        self.assertFalse([x for x in w if "dự phóng" in x], w)

    def test_forecast_anchor_m8(self):
        def anchor(fn):
            return lambda fc: fn(fc["scopes"]["VNINDEX"]["anchor"])
        cases = {  # the forecast file's own anchor must sit on the engine (FINAL_PLAN M8)
            "neo hhp_forecast.json lệch engine (neo 30/12 · dữ liệu 02/01)":
                anchor(lambda a: a.__setitem__("as_of", "2025-12-30")),
            "neo hhp_forecast.json lệch engine (neo μ 15,1": anchor(lambda a: a["pe"].__setitem__("mean", 15.1)),
            "anchor.ms của hhp_forecast.json không phải điểm chart engine cuối":
                anchor(lambda a: a.__setitem__("ms", H_ENGINE_X[-2])),
            "lưới thời gian khác base_path": lambda fc: fc["scopes"]["VNINDEX"]["pe"]["base_path"].pop(),
            "chưa có hhp_forecast.json": None,
            "hhp_forecast.json sai định dạng": lambda fc: fc["meta"].__setitem__("schema", "x"),
        }
        for frag, mutate in cases.items():
            if mutate is None:
                os.remove(os.path.join(self.dir, hv.FORECAST_FILE))
                d = hv.build_history(self.dir)
                h, w = d["history"], d["meta"]["warnings"]
            else:
                h, w = self.with_forecast_scope(mutate)
            self.assertIsNone(h["pe"]["forecast"], frag)
            self.assertIsNotNone(h["pe"]["chart"], frag)
            self.assert_one_warning(w, "Toàn sử P/E: dự phóng dài hạn bỏ — " + frag)

    def test_readings_validated(self):
        def add(*readings):
            return lambda f: f["pe"]["keynote_readings"].__setitem__("kn-2020-03-day", list(readings))
        good = history_reading("pe", 11.0, "2020-03-24", -1.5)
        h, w = self.with_history(add(good, history_reading("pb", 1.3, "2020-03-24", -1.0),
                                     dict(good, scope="VN30"), dict(good, v=NAN), dict(good, src_org=""),
                                     dict(good, src_date="hôm qua"), dict(good, tier="GUESS"), "x"))
        kn = {k["id"]: k for k in h["keynotes"]}
        self.assertEqual([n["v"] for n in kn["kn-2020-03-day"]["numbers"] if n["k"] == "pe"], [11.0])
        self.assert_one_warning(w, "Toàn sử P/E: số đọc keynote — 8 số sai")  # 7 bad here + the UNVERIFIED one
        h, w = self.with_history(add(*[dict(good, v=float(i)) for i in range(10)]))
        kn = {k["id"]: k for k in h["keynotes"]}
        self.assertEqual(len([n for n in kn["kn-2020-03-day"]["numbers"] if n["k"] == "pe"]), hv.MAX_READINGS)
        self.assert_one_warning(w, "cắt 2 số vượt 8/sự kiện")
        h, _ = self.with_history(add(dict(good, asof=None)))   # a σ that cannot be dated is not kept
        kn = {k["id"]: k for k in h["keynotes"]}
        self.assertEqual([n.get("sigma") for n in kn["kn-2020-03-day"]["numbers"] if n["k"] == "pe"], [None])

    def test_gaps_and_stale_file_warned_only(self):
        gap = {"from": "2003-01-28", "to": "2003-02-10", "what": "price", "reason": "Tết"}
        h, w = self.with_history(lambda f: f.__setitem__("gaps", [gap, "rác"]))
        self.assertEqual(h["gaps"], [gap])
        self.assert_one_warning(w, "Toàn sử có 1 lỗ dữ liệu > 21 ngày: 2003-01-28→2003-02-10")
        path = os.path.join(self.dir, hv.HISTORY_FILE)
        old = time.time() - 31 * 3600
        os.utime(path, (old, old))
        d = hv.build_history(self.dir)
        self.assertIsNotNone(d["history"])
        self.assertEqual(d["meta"]["history_file"]["age_hours"], 31.0)
        self.assert_one_warning(d["meta"]["warnings"], "hhp_vnindex_history.json đã 31 giờ chưa làm mới")

    def test_non_finite_passthrough_is_strict_json(self):
        def poison(f):
            f["pe"]["long"]["pct"] = NAN
            f["pe"]["seam"]["median"] = float("inf")
            f["price"]["level_x_base"] = NAN
            f["meta"]["caveats"].append(NAN)
        h, _ = self.with_history(poison, cli=True)  # run_script rejects NaN / Infinity tokens
        self.assertIsNone(h["pe"]["long"]["pct"])
        self.assertIsNone(h["pe"]["seam"]["median"])
        self.assertIsNone(h["price"]["level_x_base"])

    def test_keynote_file_missing(self):
        os.remove(os.path.join(self.dir, hv.KEYNOTES_FILE))
        d = hv.build_history(self.dir)
        self.assertEqual(d["history"]["keynotes"], [])
        self.assertIsNone(d["meta"]["keynotes_file"])
        self.assert_one_warning(d["meta"]["warnings"], "Chưa có hhp_keynotes.json")
        self.assertIsNotNone(d["history"]["pe"])

    def test_timing(self):
        t0 = time.perf_counter()
        hv.build_history(self.dir)
        self.assertLess(time.perf_counter() - t0, 1.0)


class NoDataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hhp_nodata_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def assert_no_data(self, data_dir):
        for args in (["overview"], ["ticker", "AAA"], ["history"]):
            rc, d, _ = run_script(args, data_dir)
            self.assertEqual(rc, 0)
            self.assertEqual(d.get("error_code"), "NO_DATA", (args, d))
            self.assertIn("hhp_vn100_valuation.py", d["error"])

    def test_empty_dir(self):
        self.assert_no_data(self.tmp)

    def test_nonexistent_dir(self):
        self.assert_no_data(os.path.join(self.tmp, "does-not-exist"))

    def test_corrupt_core(self):
        with open(os.path.join(self.tmp, hv.CORE_FILE), "w", encoding="utf-8") as fh:
            fh.write('{"meta": ')
        self.assert_no_data(self.tmp)


@unittest.skipUnless(os.path.isfile(os.path.join(REAL_DIR, hv.CORE_FILE)), "real HHP data dir not present")
class LiveDataTest(unittest.TestCase):
    def test_overview(self):
        t0 = time.perf_counter()
        hv.build_overview(REAL_DIR)
        self.assertLess(time.perf_counter() - t0, 1.0, "overview must build in < 1 s")

        rc, d, _ = run_script(["overview"], REAL_DIR)
        self.assertEqual(rc, 0)
        self.assertNotIn("error", d)
        self.assertEqual(len(d["members"]["VN30"]), 30)
        self.assertEqual(len(d["members"]["VN100"]), 100)
        universe = set(d["members"]["VN30"]) | set(d["members"]["VN100"])
        gone = set(d["missing"]["VN30"]) | set(d["missing"]["VN100"])
        self.assertEqual(len(d["rows"]), len(universe - gone))
        # Measured 2026-09-21: VN30 ⊂ VN100, so the union is the 100 VN100 names; TCX, VCK and VPX
        # have no valuation data upstream → 97 rows. Revisit on the next index rebalance.
        self.assertEqual(len(d["rows"]), 97)
        for r in d["rows"]:
            for m in ("pe", "pb"):
                if r[m] is not None:
                    self.assertIn(r[m]["zone_key"], ("cheap", "neutral", "rich"), (r["tk"], m))
                    self.assertIsInstance(r[m]["stale"], bool, (r["tk"], m))
        self.assertIn(d["index"]["pe"]["zone_key"], ("cheap", "neutral", "rich"))
        self.assertEqual(len(d["index"]["pe"]["chart"]["price"]), len(d["index"]["pe"]["chart"]["rich2"]))
        # Keynotes / forecast: present or explicitly absent, never an error.
        self.assertIsInstance(d["keynotes"], list)
        self.assertIn("forecast", d)
        self.assertIn("keynotes_file", d["meta"])
        self.assertIn("forecast_file", d["meta"])
        self.assertEqual(d["forecast"] is None, d["meta"]["forecast_file"] is None
                         or any(hv.FORECAST_FILE in w for w in d["meta"]["warnings"]))
        for k in d["keynotes"]:
            self.assertTrue(k["sources"], k["id"])
            self.assertIn(k["tier_effective"], hv.TIERS)

    def test_ticker_fpt_vcb(self):
        for tk in ("FPT", "VCB"):
            rc, d, _ = run_script(["ticker", tk], REAL_DIR)
            self.assertEqual(rc, 0)
            self.assertNotIn("error", d)
            c = d["pe"]["chart"]
            self.assertGreater(len(c["price"]), 0)
            self.assertEqual(len(c["fair"]), len(c["price"]))
            self.assertEqual(d["row"]["tk"], tk)
            self.assertTrue(all(math.isfinite(p[1]) for p in c["price"]))
            # Per-ticker forecast / keynotes: present or explicitly absent (warned), never an error.
            self.assertIsInstance(d["keynotes"], list)
            fc = d["forecast"]
            if fc is None:
                self.assertTrue(any(hv.TICKER_FC_DIR in w for w in d["meta"]["warnings"]), d["meta"]["warnings"])
                continue
            for m in ("pe", "pb"):
                if fc[m] is None:
                    self.assertTrue(fc["skip"][m], (tk, m))  # a null metric always says why
                    continue
                first, last = fc[m]["points"]["fair"][0], d[m]["chart"]["fair"][-1]
                self.assertEqual(len(fc[m]["points"]["fair"]), hv.TICKER_FC_POINTS, (tk, m))
                self.assertEqual(first[0], last[0], (tk, m))  # the dashed fair starts where the solid one ends
                self.assertLessEqual(abs(first[1] - last[1]), hv.TICKER_FAIR_TOLERANCE, (tk, m))

    @unittest.skipUnless(os.path.isfile(os.path.join(REAL_DIR, hv.HISTORY_FILE)), "hhp_vnindex_history.json not built")
    def test_history(self):
        t0 = time.perf_counter()
        hv.build_history(REAL_DIR)
        self.assertLess(time.perf_counter() - t0, 1.0, "history must build in < 1 s")
        rc, d, text = run_script(["history"], REAL_DIR)
        self.assertEqual(rc, 0)
        self.assertNotIn("error", d)
        h = d["history"]
        self.assertIsNotNone(h, d["meta"]["warnings"])
        bands = len(json.dumps(dict(h, keynotes=[]), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        self.assertLessEqual(bands, 600 * 1024, "price + bands + ◇ over the 600 KB budget (FINAL_PLAN M26)")
        self.assertLessEqual(len(text.encode("utf-8")), 1024 * 1024, "history payload (keynotes included) over 1 MB")
        engine = hv.load_core(REAL_DIR)[0]["index"]
        for m in hv.METRICS:
            blk = h[m]
            if blk is None:
                self.assertTrue(any("Toàn sử %s" % hv.METRIC_LABEL[m] in w for w in d["meta"]["warnings"]), m)
                continue
            self.assertGreaterEqual(blk["chart"]["fair"][0][0], dms(blk["long_from"]), m)
            if blk["eight"] is not None:
                for k in ("mean", "sd", "sigma", "zone"):
                    self.assertEqual(blk["eight"][k], engine[m][k], (m, k))  # the 8-year window IS the engine's
            for k in H_MULT if blk["forecast"] else ():
                self.assertEqual(blk["forecast"]["points"][k][0], blk["chart"][k][-1], (m, k))
            for p in blk["points"]:
                self.assertFalse(all_keys(p) & {"sigma", "sigma_long"}, p)
        for ev in h["keynotes"]:  # D7: a σ on the full-history chart is a long-window reading (dated ≥ long.from)
            for n in ev["numbers"]:
                if "sigma" in n:
                    self.assertIn(n["k"], hv.METRICS, (ev["id"], n))
                    self.assertGreaterEqual(dms(n["asof"]), dms(h[n["k"]]["long_from"]), (ev["id"], n))


if __name__ == "__main__":
    unittest.main()
