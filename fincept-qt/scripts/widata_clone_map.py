#!/usr/bin/env python3
"""
Fincept Terminal, tab VĨ MÔ (MACRO), bản clone WiData: sinh series_map.json (sid -> nguồn của ta).

Hợp đồng: widata_clone_spec/DESIGN.md §4.2 (chuẩn hoá sid), §4.7 (planned_source, reason_if_missing), §8.2 (lớp
nguồn), §16 C1/C4. Gói A, TASKS §3.A. Chạy tay khi analysis hoặc công thức nguồn đổi; builder chỉ đọc tệp kết quả.

USAGE
    python3 widata_clone_map.py [--out PATH] [--check]
Env: WDC_SYSTEM_DIR (thay ~/SECOND BRAIN-OBSIDIAN/_System).

Đầu vào (chỉ đọc): fincept_bridge/data/widata_clone/layout_const.json, widata_clone_spec/analysis/data_{vn,us,
other}.json. Không đọc capture. Không chép số, mốc t0/t1, n_points hay câu chữ mô tả của WiData: mọi câu trong
series_map là câu của ta (công thức viết tay dưới đây); từ analysis chỉ lấy nhãn trạng thái, mã collector, mã
nguồn (canvas, mã e-DSBB, mã FRED).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

SCHEMA = "widata_clone_map/1"
FREQ_BY_PREFIX = {"daily": "D", "weekly": "W", "monthly": "M", "quarterly": "Q", "yearly": "Y", "ytd": "YTD"}
FREQ_BY_DATE_TYPE = {"ngay": "D", "thang": "M", "quy": "Q", "nam": "Y"}

SOURCES = {
    "store": {"path": "{SYS}/superdash_v2/output/widata_series_store.json", "env": "WDC_STORE_JSON",
              "producer": "superdash_v2/widata_series_builder.py (FRED), widata_wichart.py (WiGroup công khai), "
                          "widata_sbv.py (Vietcombank), collector_vnstock_macro.py (MSN)"},
    "nso": {"path": "{HOME}/Downloads/BERI_Cowork/03_Kho_du_lieu/nso_edsbb/nso_edsbb_long.csv", "env": "WDC_NSO_CSV",
            "producer": "nso_edsbb.py (e-DSBB, NSO)"},
    "liquidity": {"path": "{SYS}/liquidity_daily/output/snapshot_*.json", "env": "WDC_LIQ_GLOB",
                  "producer": "liquidity_daily/rates.py (WiGroup công khai)"},
    "wd_vimo": {"path": "{SYS}/fincept_bridge/data/wd_vimo_raw.json", "producer": "fincept_bridge/goi_widata.py"},
    "bang_widata": {"path": "{SYS}/fincept_bridge/data/bang_widata.json", "producer": "fincept_bridge/goi_widata.py"},
    "tpcp": {"path": "{SYS}/fincept_bridge/data/tpcp_vn.json",
             "producer": "fincept_bridge/goi_tpcp.py (HNX par yield)"},
    "openbb": {"path": "{SYS}/superdash_v2/output/collector_openbb_global.json",
               "producer": "superdash_v2/collector_openbb_global.py (OpenBB, yfinance)"},
    "vnstock_macro": {"path": "{SYS}/superdash_v2/output/vnstock_macro.json",
                      "producer": "superdash_v2/widata_vnstock_macro.py (SJC qua vnstock)"},
    "collected": {"path": "{SYS}/fincept_bridge/data/widata_clone/collected/*.json", "env": "WDC_COLLECTED_GLOB",
                  "producer": "collector của clone (gói A2, schema wdc_collected/1)"},
    "manual": {"path": "{SYS}/fincept_bridge/data/widata_clone/manual/*.json", "env": "WDC_MANUAL_GLOB",
               "producer": "bảng tay theo văn bản chính thức (collectors/wdc_vn_policy.py, schema wdc_collected/1)"},
}
STORE_CLASS = [["WiChart", "wigroup"], ["FRED", "official"], ["WorldBank", "official"], ["Vietcombank", "secondary"],
               ["vnstock", "secondary"], ["VnDirect", "secondary"], ["HSC", "secondary"]]
LIQ_KEYS = ("on_interbank", "omo_rate", "bills_rate", "discount_rate", "refinance_rate", "fx_central", "fx_nhtm_sell",
            "fx_free_sell", "reserves_musd", "m2_growth", "credit_growth", "deposit_growth")
US_PLAN = {"FRED_CAN_THEM": ("collector_pending", "A2-US1"), "FRED_PHAI_SINH": ("collector_pending", "A2-US3"),
           "ALFRED_SEP": ("collector_pending", "A2-US2"),
           "NGUON_CHINH_THUC_NGOAI_FRED": ("collector_pending", "A2-US4"),
           "BAN_QUYEN_CAN_DATA": ("license", ""), "BIEN_TAP_CAN_DATA": ("no_source", ""),
           "CO_TRONG_STORE": ("stale", ""), "CO_TRONG_STORE_PROXY": ("stale", "")}

# Đợt 4 (DATA2 việc 5): tên nguồn chỉ là nhãn trung tính, không ghi tên miền API (DESIGN §16 C17).
WIC_NAME = "WiGroup công khai (kho widata_series_store của superdash_v2)"
NSO_NAME = "NSO (Cục Thống kê), e-DSBB"
VNB_NAME = "WiGroup công khai (bản chụp thanh khoản liquidity_daily)"
YOY_TF = "YoY tự tính: mức kỳ này / cùng kỳ năm trước - 1, trên chuỗi mức của cùng nguồn."
YTD_TF = "YoY luỹ kế tự tính: tổng các tháng từ đầu năm / cùng kỳ năm trước - 1."
BREAK_NHNN = {"date": "2025-10-31", "note": "NHNN phân tổ lại số liệu tiền tệ từ kỳ 10/2025; YoY các kỳ sau vắt qua "
                                            "điểm gãy, chưa nối"}
SPAN_NHNN = {"from": "2025-10-31", "to": "2026-09-30", "tier": "EST"}


def cand(cid, src, cls, tier, source_name, source_ref, producer, **kw):
    c = {"id": cid, "src": src, "class": cls, "tier": tier, "source_name": source_name, "source_ref": source_ref,
         "producer": producer, "post": kw.get("post") or [], "partial_reasons": list(kw.get("reasons") or []),
         "transform": kw.get("transform"), "notes": list(kw.get("notes") or [])}
    for k in ("freq", "breaks", "tier_spans"):
        if kw.get(k):
            c[k] = kw[k]
    return c


def wic(canvas, line=None, **kw):
    src = {"src": "store", "canvas": canvas}
    if line:
        src["line"] = line
    ref = "widata_series_store.json#" + canvas + (" / " + line if line else "")
    kw.setdefault("transform", "Lấy nguyên chuỗi, dời mốc về ngày cuối kỳ (DESIGN §4.3).")
    return cand("store:" + canvas + (":" + line if line else ""), src, "wigroup", kw.pop("tier", "FACT-T2"), WIC_NAME,
                ref, "superdash_v2/widata_wichart.py", **kw)


def liq(key, tier="FACT-T2", **kw):
    kw.setdefault("transform", "Mỗi ảnh chụp lấy giá trị và ngày *_asof của khoá; trùng ngày giữ ảnh chụp sau.")
    return cand("liquidity:" + key, {"src": "liq", "key": key}, "wigroup", tier, VNB_NAME,
                "liquidity_daily/output/snapshot_*.json#rates." + key, "liquidity_daily/rates.py", **kw)


def nso(code, op, tier, cls, transform, **kw):
    return cand("nso:%s:%s" % (op, code), {"src": "nso", "code": code, "op": op}, cls, tier, NSO_NAME,
                "nso_edsbb_long.csv: " + code, "nso_edsbb.py", transform=transform, **kw)


# ── Công thức VN viết tay (căn cứ A/data_vn.json, DESIGN §8.3) ───────────────

TF_GDP_LEVEL = ("Mức quý giá so sánh: đến 2025-Q4 bảng Dataset_Q (gốc 2010), từ 2026-Q1 bảng Dataset_QI.2026 "
                "(gốc 2020); hai gốc không nối.")
TF_GDP_YOY = "YoY tính trong từng bảng e-DSBB (cùng gốc giá so sánh), không vắt qua hai gốc."
TF_CPI = ("Từ 11/2025 lấy nguyên chỉ số gốc 2024; trước đó chỉ số gốc 2019 chia bình quân 12 tháng 2024 "
          "của chính chuỗi đó, nhân 100 (ước tính).")
TF_CPI_YOY = "YoY tự tính từ chỉ số CPI cùng kỳ gốc (e-DSBB); không tính qua điểm đổi gốc 11/2025."
# DESIGN §16 C17: mỗi ứng viên là MỘT nguồn, không ghép hai nguồn trong một chuỗi (bỏ kiểu "union").
CENTRAL = {"src": "liq", "key": "fx_central"}


def vn_band(factor, word):
    return cand("derived:fx_central_x%s" % factor, CENTRAL, "wigroup", "EST", VNB_NAME,
                "liquidity_daily/output/snapshot_*.json#rates.fx_central", "liquidity_daily/rates.py",
                post=[["scale", factor]], reasons=["est_transform"],
                transform="%s = tỷ giá trung tâm x %s (biên độ ±5%%, chỉ đúng cho giai đoạn biên độ này)."
                          % (word, factor))


def vn_recipes(vn):
    """sid -> [ứng viên] cho các định danh VN có nguồn cục bộ."""
    r = {}
    for s in vn:
        sid, n = "vn|" + s["id"], s.get("nguon_ta") or {}
        ref, kind = str(n.get("ref") or ""), n.get("kind")
        m = re.search(r"csv: ([A-Z0-9_]+)", ref)
        if kind == "collector" and m:
            code, col, tk = m.group(1), s["column_name"], s["target_key"]
            if s["table_name"] == "244" and tk == "quarterly-value":
                r[sid] = [nso(code, "gdp_level", "FACT-T1", "official", TF_GDP_LEVEL, reasons=["unverified_meaning"],
                              notes=["Mức hai gốc giá so sánh trên cùng một đường; không so mức qua điểm gãy."])]
            elif s["table_name"] == "244":
                r[sid] = [nso(code, "gdp_yoy", "EST", "derived", TF_GDP_YOY)]
            elif s["table_name"] == "225" and col != "cpi_yoy":
                r[sid] = [nso(code, "cpi_rebase", "FACT-T1", "derived", TF_CPI, reasons=["est_transform"])]
            continue
        cm = re.search(r"\b(wch?-[a-z0-9-]+)", ref)
        if kind == "store" and cm:
            lm = re.search(r"đường '([^']+)'", ref)
            line = lm.group(1).rstrip("…").strip() if lm else None
            r[sid] = [wic(cm.group(1), line)]
    tune = {
        "vn|244|gdp_so_sanh_2010_yoy|quarterly-yoy": dict(reasons=["rounded"]),
        "vn|248|toan_nganh_cong_nghiep_yoy|monthly-yoy": dict(reasons=["rounded"]),
        "vn|278|tong_yrl_yoy|monthly-yoy": dict(post=[["yoy"]], tier="EST", transform=YOY_TF),
        "vn|278|tong_yrl_yoy|ytd-yoy": dict(post=[["ytd_yoy"]], tier="EST", transform=YTD_TF),
        "vn|254|tong_yrl_yoy|monthly-yoy": dict(post=[["yoy"]], tier="EST", transform=YOY_TF),
        "vn|254|tong_yrl_yoy|ytd-yoy": dict(post=[["ytd_yoy"]], tier="EST", transform=YTD_TF),
        "vn|229|huy_dong_von_tong_tien_gui_1_yoy|monthly-yoy": dict(
            reasons=["unverified_meaning"], breaks=[BREAK_NHNN], tier_spans=[SPAN_NHNN]),
        "vn|229|m2_1_yoy|monthly-yoy": dict(reasons=["unverified_meaning"], breaks=[BREAK_NHNN],
                                            tier_spans=[SPAN_NHNN]),
        "vn|269|bom_hut_rong_tong_luu_hanh|None": dict(
            post=[["cumsum"]], tier="EST", reasons=["proxy"],
            transform="Luỹ kế bơm hút ròng theo ngày từ điểm đầu của kho; không phải số dư lưu hành thật "
                      "(thiếu số dư đầu kỳ)."),
        "vn|269|usd_nhtm_ban_ra|daily-value": dict(
            reasons=["short_history"], notes=["Trước 06/2026 kho chỉ có một điểm mỗi tháng."]),
        "vn|269|usd_nhtm_mua_vao|daily-value": dict(
            reasons=["short_history", "unverified_meaning"],
            notes=["Trước 06/2026 kho chỉ có một điểm mỗi tháng.", "Dùng giá mua chuyển khoản của Vietcombank."]),
    }
    for sid in [k for k in r if "|234|" in k or "|232|" in k or "|302|" in k]:
        tune.setdefault(sid, dict(reasons=["unverified_meaning"]))
    for sid, kw in tune.items():
        if sid in r:
            c = r[sid][0]
            for k, v in kw.items():
                c["partial_reasons" if k == "reasons" else k] = v
    vcb = "Vietcombank (tỷ giá niêm yết), lưu bởi superdash_v2/widata_sbv.py"
    for sid in ("vn|269|usd_nhtm_ban_ra|daily-value", "vn|269|usd_nhtm_mua_vao|daily-value"):
        r[sid][0].update({"class": "secondary", "source_name": vcb, "producer": "superdash_v2/widata_sbv.py",
                          "transform": "Lấy nguyên giá niêm yết; mốc 00:00 UTC của ngày Việt Nam."})
    r["vn|269|usd_tu_do_ban_ra|daily-value"] = [liq("fx_free_sell", tier="UNVERIFIED")]
    for col in ("omo_lstb", "sbv_bills_lstb"):
        key = "omo_rate" if col == "omo_lstb" else "bills_rate"
        for tk in ("None", "daily-value"):
            r["vn|251|%s|%s" % (col, tk)] = [liq(key)]
    r["vn|269|usd_nhnn_trung_tam|daily-value"] = [
        liq("fx_central"),
        cand("wd_vimo:fx_central", {"src": "wd_vimo", "name": "Tỷ giá trung tâm"}, "wigroup", "FACT-T2", VNB_NAME,
             "wd_vimo_raw.json 'Tỷ giá trung tâm'", "fincept_bridge/goi_widata.py",
             transform="Một kỳ cuối của nguồn WiGroup công khai.")]
    r["vn|269|usd_nhnn_tran|daily-value"] = [vn_band(1.05, "Trần")]
    r["vn|269|usd_nhnn_san|daily-value"] = [vn_band(0.95, "Sàn")]
    r["vn|225|cpi_yoy|monthly-yoy"] = [
        cand("wd_vimo:cpi_yoy", {"src": "wd_vimo", "name": "CPI YoY", "prev": True}, "wigroup", "FACT-T2", VNB_NAME,
             "wd_vimo_raw.json 'CPI YoY'", "fincept_bridge/goi_widata.py",
             transform="Kỳ cuối và kỳ trước của nguồn WiGroup công khai."),
        # YoY trong cùng gốc: không phải partial (đợt 4, DATA2 việc 6); tier EST vì tự tính.
        nso("PCPI_IX", "cpi_yoy19", "EST", "derived", TF_CPI_YOY)]
    for col, label in (("can_can_vang_lai", "cctt vãng lai"), ("can_can_tai_chinh", "cctt tài chính")):
        r["vn|220|%s|quarterly-value" % col] = [cand(
            "bang:" + label, {"src": "bang", "name": "Cán cân thanh toán", "label": label}, "wigroup", "FACT-T2",
            VNB_NAME, "bang_widata.json 'Cán cân thanh toán' / " + label, "fincept_bridge/goi_widata.py",
            transform="Một kỳ cuối đọc từ ghi chú dòng 'Cán cân thanh toán'.")]
    r["vn|220|can_can_tong_the|quarterly-value"] = [cand(
        "wd_vimo:bop", {"src": "wd_vimo", "name": "Cán cân thanh toán", "prev": True}, "wigroup", "FACT-T2", VNB_NAME,
        "wd_vimo_raw.json 'Cán cân thanh toán'", "fincept_bridge/goi_widata.py",
        transform="Kỳ cuối và kỳ trước của nguồn WiGroup công khai.")]
    return r


# ── Mỹ (A/data_us.json) và nhóm khác (A/data_other.json) ─────────────────────


def us_store_recipe(s):
    st, ng = s["store"], s["nguon"]
    fid = st.get("fred_store") or ng["fred_id"]
    post, tier, cls, notes, reasons = [], "FACT-T1", "official", [], []
    tf = "Lấy nguyên chuỗi FRED trong kho, dời mốc về ngày cuối kỳ (DESIGN §4.3)."
    if "chia 1000" in str(ng.get("hau_xu_ly") or ""):
        post.append(["scale", 0.001])
        tf = "Chuỗi FRED (triệu USD) chia 1000 sang tỷ USD."
    if ng.get("fred_units") == "pc1" and st.get("unit_store") != "%":
        post.append(["yoy"])
        tier, cls, tf = "EST", "derived", YOY_TF
    if st.get("khop") == "proxy":
        reasons.append("proxy")
        notes.append("Tạm dùng mã FRED %s thay %s (khác định nghĩa); chờ gói A2-US1." % (fid, ng["fred_id"]))
    return cand("store:" + st["canvas"], {"src": "store", "canvas": st["canvas"]}, cls, tier,
                "FRED, St. Louis Fed (mã %s; nhà công bố: %s)" % (fid, ng.get("publisher") or "?"),
                "widata_series_store.json#%s (FRED:%s)" % (st["canvas"], fid), "superdash_v2/widata_series_builder.py",
                post=post, reasons=reasons, transform=tf, notes=notes,
                freq={"D": "D", "W": "W", "M": "M", "Q": "Q"}.get(st.get("freq_store")))


def ot_recipes():
    msn = "MSN qua vnstock, lưu bởi superdash_v2/collector_vnstock_macro.py"
    yf = "OpenBB/yfinance, lưu bởi superdash_v2/collector_openbb_global.py"

    def store(canvas, name, cls="secondary", tier="FACT-T2", **kw):
        kw.setdefault("transform", "Lấy nguyên chuỗi trong kho, mốc theo ngày Việt Nam.")
        return cand("store:" + canvas, {"src": "store", "canvas": canvas, **({"shift_days": kw.pop("shift")}
                                                                            if "shift" in kw else {})},
                    cls, tier, name, "widata_series_store.json#" + canvas, "superdash_v2", **kw)

    def obb(key, sym, **kw):
        return cand("openbb:" + key, {"src": "openbb", "key": key}, "secondary", "FACT-T2", yf,
                    "collector_openbb_global.json#series_data/%s (%s)" % (key, sym),
                    "superdash_v2/collector_openbb_global.py", **kw)
    fut = dict(reasons=["proxy"], transform="Giá hợp đồng kỳ hạn gần (yfinance) thay giá giao ngay; chờ gói A2-OT1.")
    return {
        "md|409|usd_cny|daily-value": [store("vnm-usdcny", msn, reasons=["rounded"],
                                             notes=["Nguồn MSN làm tròn 2 chữ số thập phân."])],
        "md|217|xau_usd|daily-value": [store("vnm-xau", msn)],
        "md|408|dji|daily-value": [store("vnm-dji", msn)],
        "md|408|spx|daily-value": [store("vnm-spx", msn)],
        "md|408|ssec|daily-value": [store("vnm-sse", msn, shift=1, transform="MSN ghi chỉ số châu Á lùi một ngày; "
                                                                             "cộng 1 ngày khi dựng.")],
        "md|410|us_10y|daily-value": [store("wc-usbond", "FRED, St. Louis Fed (mã DGS10)", "official", "FACT-T1")],
        "cn|27|forei_cur_res|monthly-value": [store(
            "wc-cn-reserves", "World Bank (FI.RES.TOTL.CD)", "official", "FACT-T1", freq="Y",
            post=[["scale", 1e-9]], reasons=["proxy"],
            transform="Số năm của World Bank (gồm cả vàng), USD chia 1e9 sang tỷ USD; tạm thay chuỗi tháng.")],
        "md|269|gia_vang_trong_nuoc_ban_ra|daily-value": [cand(
            "sjc:sell", {"src": "sjc", "field": "sell"}, "secondary", "FACT-T2", "SJC qua vnstock",
            "vnstock_macro.json#gold_sjc (Vàng SJC 1L, bán ra)", "superdash_v2/widata_vnstock_macro.py",
            post=[["scale", 0.001]], transform="Giá bán ra VND/lượng chia 1000 sang nghìn VND/lượng; một điểm.")],
        "md|410|vietnam_10y|daily-value": [cand(
            "tpcp:10Y", {"src": "tpcp", "tenor": "10Y"}, "secondary", "FACT-T2",
            "HNX, đường cong lợi suất TPCP (par yield), qua bản sao FTU-kudo", "tpcp_vn.json#ky_han/10Y",
            "fincept_bridge/goi_tpcp.py", transform="Lấy nguyên lợi suất kỳ hạn 10 năm theo ngày.",
            notes=["Đường cong khớp bằng mô hình của HNX, không phải lợi suất khớp lệnh.",
                   "Bước nhảy ngày 22/10/2024 là lỗi khớp đường cong, không phải biến động thị trường."])],
        "md|409|dx|daily-value": [obb("dxy", "DX-Y.NYB", transform="Lấy nguyên chỉ số theo ngày.")],
        "md|409|dx|None": [obb("dxy", "DX-Y.NYB", transform="Lấy nguyên chỉ số theo ngày.")],
        "md|217|wti_usd|daily-value": [obb("wti", "CL=F", **fut)],
        "md|333|dau_brent_hoa_ky_investing_spot|daily-value": [obb("brent", "BZ=F", **fut)],
        "eu|69|mlfr_lev|daily-value": [cand(
            "derived:ecb_mrr_plus_25bp", {"src": "store", "canvas": "wc-eu-mrr"}, "derived", "EST",
            "FRED, St. Louis Fed (mã ECBMRRFR) + quy tắc biên của ECB", "widata_series_store.json#wc-eu-mrr",
            "superdash_v2/widata_series_builder.py", post=[["add", 0.25]], reasons=["proxy"],
            transform="Lãi suất cho vay cận biên ước = lãi suất tái cấp vốn chính + 0,25 điểm % (chờ gói A2-OT1).")],
    }


# ── Lắp series_map ───────────────────────────────────────────────────────────


def sys_dir():
    env = os.environ.get("WDC_SYSTEM_DIR")
    return Path(env).expanduser() if env else Path.home() / "SECOND BRAIN-OBSIDIAN" / "_System"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def layout_rows(layout):
    """sid -> SeriesRef đầu tiên (dashboard trước, chart đơn sau) + số dòng."""
    out = {}
    for db in layout["dashboards"]:
        for c in db["cards"]:
            for p in c["panes"]:
                for s in p["series"]:
                    out.setdefault(s["sid"], [s, 0, "dash"])[1] += 1
    for sc in layout.get("single_charts") or []:
        for s in sc["pane"]["series"]:
            out.setdefault(s["sid"], [s, 0, "single"])[1] += 1
    return out


def clean_name(raw):
    s = re.sub(r"^\s*\[[A-Z]+\]\s*-\s*", "", raw or "")
    return re.sub(r"\s+", " ", s).strip()


def freq_of(sid, ref):
    tk = sid.split("|")[3]
    if ref.get("kind") == "third_party":
        return "TP"
    pre = tk.split("-")[0]
    return FREQ_BY_PREFIX.get(pre) or FREQ_BY_DATE_TYPE.get(ref.get("date_type") or "", "M")


def analysis_index(a_dir):
    vn = json.loads((a_dir / "data_vn.json").read_text(encoding="utf-8"))
    us = json.loads((a_dir / "data_us.json").read_text(encoding="utf-8"))
    ot = json.loads((a_dir / "data_other.json").read_text(encoding="utf-8"))
    idx = {}
    for s in vn:
        col = s.get("collector_can_viet") or []
        reason = "collector_pending" if col else "no_source"
        idx["vn|" + s["id"]] = {"origin": "data_vn.json", "label": s["status"], "reason": reason,
                                "planned": ", ".join(col)}
    for s in us["series"]:
        w = s["widata"]
        key = s["key"]
        sid = ("tp|" + key[5:] if key.startswith("null|") else
               "%s|%s|%s|%s" % (w["country"], w["table_name"], w["column_name"], w.get("target_key") or "None"))
        reason, a2 = US_PLAN[s["status"]]
        if (s.get("nguon") or {}).get("fred_id") == "GDPNOW":
            a2 = "A2-US4"
        idx[sid] = {"origin": "data_us.json", "label": s["status"], "reason": reason,
                    "planned": s["status"] + (" · " + a2 if a2 else ""), "us": s}
    for s in ot["series"]:
        kind = s["our_source"]["kind"]
        if kind == "fred":
            reason, planned = "collector_pending", "FRED · A2-OT1"
        elif s.get("collector"):
            reason, planned = "collector_pending", str(s["collector"])
        else:
            reason, planned = "no_source", ""
        idx[s["id"]] = {"origin": "data_other.json", "label": s["status"], "reason": reason, "planned": planned}
    return vn, us, ot, idx


def build_map(sdir):
    data_dir = sdir / "fincept_bridge" / "data" / "widata_clone"
    a_dir = sdir / "fincept_bridge" / "widata_clone_spec" / "analysis"
    layout = json.loads((data_dir / "layout_const.json").read_text(encoding="utf-8"))
    vn, us, ot, idx = analysis_index(a_dir)
    recipes = vn_recipes(vn)
    for s in us["series"]:
        if s["status"].startswith("CO_TRONG_STORE"):
            w = s["widata"]
            recipes["%s|%s|%s|%s" % (w["country"], w["table_name"], w["column_name"], w.get("target_key") or "None")] \
                = [us_store_recipe(s)]
    recipes.update(ot_recipes())
    for sid in ("vn|250|ls_du_tru_bat_buoc_vnd|None", "vn|250|ls_du_tru_bat_buoc_ngoai_te|None"):
        idx[sid] = dict(idx[sid], planned="C6 bảng tay NHNN (manual/vn_policy.json): chưa có văn bản xác minh được")
    idx["vn|227|lamphat_yoy|monthly-yoy"] = {
        "origin": "pane2", "label": "missing", "reason": "no_source",
        "planned": "NSO lạm phát cơ bản (CHƯA XÁC MINH có trong e-DSBB)"}
    aliases = {"vn|229|tong_tin_dung_trong_nen_kinh_te_yoy|None":
               "vn|229|tong_tin_dung_trong_nen_kinh_te_yoy|monthly-yoy",
               "vn|244|gdp_so_sanh_2010_yoy|None": "vn|244|gdp_so_sanh_2010_yoy|quarterly-yoy",
               "vn|229|m2_1_yoy|None": "vn|229|m2_1_yoy|monthly-yoy"}
    series, problems = {}, []
    for sid, (ref, nrows, scope) in layout_rows(layout).items():
        base = aliases.get(sid, sid)
        info = idx.get(base)
        if info is None:
            problems.append("sid trong layout không có bản ghi analysis: " + sid)
            continue
        cands = recipes.get(base, [])
        country, table, column, tk = sid.split("|")
        e = {"country": country, "table": table, "column": column, "target_key": tk, "scope": scope,
             "rows": nrows, "origin": info["origin"], "analysis_label": info["label"],
             "alias_of": base if base != sid else None, "name": clean_name(ref.get("name_raw")),
             "unit": ref.get("unit") or "", "freq": (cands[0].get("freq") if cands else None) or freq_of(sid, ref),
             "kind": ref.get("kind"), "planned_source": info["planned"],
             "reason_if_missing": "stale" if info["reason"] == "stale" and not cands else info["reason"]}
        if cands:
            c0 = cands[0]
            e.update({"producer": c0["producer"], "file": file_key_of(c0["src"]), "key": src_key(c0["src"]),
                      "transform": c0.get("transform"), "class": c0["class"], "tier": c0["tier"]})
        else:
            e.update({"producer": None, "file": None, "key": None, "transform": None, "class": None, "tier": None})
        e["candidates"] = cands
        series[sid] = e
    for sid in recipes:
        if sid not in series:
            problems.append("công thức cho sid không có trong layout: " + sid)
    inputs = {str(p.relative_to(sdir)): sha(p) for p in
              (data_dir / "layout_const.json", a_dir / "data_vn.json", a_dir / "data_us.json",
               a_dir / "data_other.json")}
    doc = {"schema": SCHEMA, "generator": "scripts/widata_clone_map.py", "inputs": inputs, "sources": SOURCES,
           "store_class_by_source_prefix": STORE_CLASS,
           "liquidity_daily_classes": {k: "wigroup" for k in LIQ_KEYS},
           "liquidity_daily_note": "Mọi khoá rates.* lấy từ trang dữ liệu công khai của WiGroup (rates.py dòng 1-4): "
                                   "lớp wigroup (DESIGN §8.2, §16 C1).",
           "series": series}
    return doc, problems


def file_key_of(src):
    return {"store": "store", "nso": "nso", "liq": "liquidity", "wd_vimo": "wd_vimo", "bang": "bang_widata",
            "tpcp": "tpcp", "openbb": "openbb", "sjc": "vnstock_macro"}[src["src"]]


def src_key(src):
    for k in ("canvas", "code", "key", "name", "tenor", "field"):
        if k in src:
            return str(src[k]) + ((" / " + src["line"]) if src.get("line") else "")
    return None


def dump(doc):
    return json.dumps(doc, ensure_ascii=False, indent=1) + "\n"


def main(argv):
    sdir = sys_dir()
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else \
        sdir / "fincept_bridge" / "data" / "widata_clone" / "series_map.json"
    doc, problems = build_map(sdir)
    text = dump(doc)
    if problems:
        print(json.dumps({"error": "series_map có lỗi ghép: " + "; ".join(problems[:5]),
                          "error_code": "map_mismatch", "n": len(problems)}, ensure_ascii=False))
        return 1
    if "--check" in argv:
        same = out.is_file() and out.read_text(encoding="utf-8") == text
        print(json.dumps({"ok": same, "path": str(out)}, ensure_ascii=False))
        return 0 if same else 1
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, out)
    n_c = sum(1 for e in doc["series"].values() if e["candidates"])
    print(json.dumps({"ok": True, "path": str(out), "series": len(doc["series"]), "with_candidates": n_c},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
