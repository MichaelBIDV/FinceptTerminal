#!/usr/bin/env python3
"""
Fincept Terminal — DEEP FA data service (HĐCV Deep FA research desk, skill deepfa-hoidongcovanai).

Feeds src/screens/deepfa/DeepFaPanel through EconomicsService / PythonRunner. Stdlib only; runs on
Python 3.9+ (app venv-numpy2 = 3.11, vault tooling = 3.14). Makes NO network calls: it re-reads the
layers the HĐCV pipelines already write (see deepfa_core.py header for the layer map) and reshapes
them. Nothing here recomputes a memo number; live numbers carry their own data date, tier and source.

Roots / test hooks (see deepfa_core.py):
    DEEPFA_VAULT    ~/SECOND BRAIN-OBSIDIAN          DEEPFA_TODAY  YYYY-MM-DD (tests only)

USAGE
    python3 deepfa.py status                 layer table (🟢🟡🔴⚫) + what to run
    python3 deepfa.py overview               triage table: one row per universe ticker
    python3 deepfa.py ticker <TK>            research page of one ticker (contract in §4 of
                                             fincept_bridge/DEEPFA_MODULE_SPEC.md)

OUTPUT — exactly ONE compact JSON object on stdout (UTF-8, ensure_ascii=False). Non-finite numbers
are emitted as null. Exit code 0 even on errors. Display strings are Vietnamese; numbers meant for
display arrive pre-formatted ("*_txt": decimal comma, thousands dot, minus "−", explicit "+" where
the sign matters). Missing values display as "[CẦN DATA]". Every number object has the shape
{v, u, t (data date), b (tier), n (source), g (note), txt}.

Top-level errors (only these replace the payload):
    {"error": "<Vietnamese message incl. what to do>", "error_code": "NO_DATA" | "BAD_ARGS" | "INTERNAL"}

1) status →
{"meta": {"generated", "script_version", "today", "vault"},
 "layers": [{"key", "label", "path", "exists", "tier", "tier_hieu_luc", "as_of", "as_of_txt",
             "age_days", "age_txt", "status": "ok"|"warn"|"stale"|"missing", "light", "error"}],
 "counts": {"universe", "memo", "memo_deep", "memo_missing", "worksheet_deep", "worksheet_ollama",
            "vc_lk", "vc_lk_missing", "lk_hoso", "hhp_series", "vf"},
 "memo_dates": [{"date", "n"}]  newest first,
 "actions": [{"muc": "chan"|"nen"|"nho", "viec", "lenh", "ly_do"}],
 "gates": {"fund_intent": "GATE-BLIND"|"CHƯA LỌC"|"ok", "cong": str, "ledger": str}}

2) overview →
{"meta": {...status.meta, "n_rows", "freshness": [subset of status.layers used by rows], "warnings": [str]},
 "gates": {...},
 "rows": [{"tk", "ten", "nhom", "ro": ["VN30"|"VN100"|"VN101-200"|"CHAEBOL"...], "nav_pct", "dm": "NAV"|"WATCH"|"AVOID"|"",
           "memo_date", "memo_age_days", "memo_age_txt", "memo_status": "ok"|"warn"|"stale"|"missing",
           "deep": bool, "engine", "state", "state_txt", "can_regen": bool, "can_regen_ly_do",
           "gia": num (giá bảng, đồng, FACT-T2, t), "gia_memo": num, "delta_pct": num (Δ% từ ngày memo),
           "pe": num, "pb": num, "sigma_pe": num (HHP σ kèm ngày), "zone_pe",
           "edi": num, "edi_stage", "edi_late": bool,
           "align": str (mgmt vs street), "street_up", "street_down", "bld_tone",
           "tp": num (SS-T3), "tp_upside_pct", "tp_stale": bool, "rating",
           "fund_gate": "GATE-BLIND"|"CHƯA LỌC"|"ok"|"none", "fund_label",
           "foreign_net_20": num, "prop_net_20": num,
           "n_filings", "worksheet_engine", "rigor": {"tags", "need", "words"},
           "flags": [str]  (⚠ lines the PM must see: stale, gate-blind, TP cũ, lệch pha…)}]
 }
"""

import json
import os
import re
import sys
import traceback
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deepfa_core as C  # noqa: E402

SCRIPT_VERSION = "0.1"
USAGE = "Dùng: deepfa.py status | overview | ticker <TK>"
TICKER_RE = re.compile(r"^[A-Z0-9]{2,6}$")


class DeepFaError(Exception):
    def __init__(self, code, message):
        Exception.__init__(self, message)
        self.code = code


# ── shared ───────────────────────────────────────────────────────────────────


def meta_block():
    return {"generated": datetime.now(C.ICT).isoformat(timespec="seconds"), "script_version": SCRIPT_VERSION,
            "today": C.iso(C.today()), "vault": C.vault()}


def gates_block(S, fftlk_cong=None):
    fund = S["fund"]["meta"]
    fund_gate = "GATE-BLIND" if fund.status() in ("stale", "missing") else "ok"
    cong = (S["fftlk"]["data"] or {}).get("cong") if isinstance(S["fftlk"]["data"], dict) else None
    cong_line = (cong or {}).get("dong") or "CỔNG: [CẦN DATA] — fft_langkinh.cong thiếu"
    L = C.ledger_for(S["ledger"], "")   # stats only
    honest = (L.get("honest") or {})
    has_detail = C.fund_detail_available(S)
    if fund_gate == "ok" and not has_detail:
        fund_gate = "CHƯA LỌC"      # fresh universe Excel without per-fund rows: gate cannot run → no label anywhere
    return {
        "fund_intent": fund_gate,
        "fund_intent_txt": ("GATE LVF mù — fund_intent_signals.json %s" % fund.to_json()["age_txt"]) if fund_gate == "GATE-BLIND"
                           else ("GATE LVF hoạt động" if fund_gate == "ok"
                                 else "GATE LVF CHƯA LỌC — aggregate %s tươi nhưng chưa có detail per-quỹ → không gán ACCUMULATION/DISTRIBUTION" % fund.to_json()["as_of_txt"]),
        "fund_detail": has_detail,
        "cong": cong_line, "cong_dung": bool((cong or {}).get("dung", True)),
        "ledger": honest.get("note") or ("track record thật (%s)" % honest.get("benchmark") if honest else "[CẦN DATA]"),
        "ledger_benchmark_note": honest.get("uniform_negative"),
    }


# ── status ───────────────────────────────────────────────────────────────────


def build_status():
    S = C.load_shared()
    U = C.load_universe()
    memos = C.list_memos()
    tickers = U["tickers"]
    deep = 0
    dates = {}
    for tk, lst in memos.items():
        d, p = lst[-1]
        dates[C.iso(d)] = dates.get(C.iso(d), 0) + 1
        try:
            with open(p, "r", encoding="utf-8") as fh:
                if "TENSION GIỮA CÁC DÒNG PHIẾU" in fh.read():
                    deep += 1
        except OSError:
            pass
    ws_dir = C.sysdir("fa_insight", "worksheets")
    ws_deep = ws_ollama = 0
    if os.path.isdir(ws_dir):
        for fn in os.listdir(ws_dir):
            if not fn.endswith(".json"):
                continue
            obj, _ = C.load_json(os.path.join(ws_dir, fn))
            eng = (obj or {}).get("engine") if isinstance(obj, dict) else None
            if eng == "claude-deep":
                ws_deep += 1
            elif eng and eng.startswith("ollama"):
                ws_ollama += 1
    vc_dir = C.sysdir("fincept_bridge", "state", "vc_lk")
    vc = {x for x in os.listdir(vc_dir) if not x.startswith((".", "_"))} if os.path.isdir(vc_dir) else set()
    lk_dir = C.sysdir("fincept_bridge", "data", "lk_hoso")
    lk = {x[:-5] for x in os.listdir(lk_dir) if x.endswith(".json") and not x.startswith("_")} if os.path.isdir(lk_dir) else set()
    hs_dir = C.sysdir("knowledge_os", "hhp_vn100_series")
    hs = {x[:-5] for x in os.listdir(hs_dir) if x.endswith(".json")} if os.path.isdir(hs_dir) else set()
    vf = (S["vf"]["data"] or {}).get("by_ticker") if isinstance(S["vf"]["data"], dict) else {}
    layers = [U["meta"].to_json()] + [S[k]["meta"].to_json() for k in S]
    # minimum fund-flow surface (cấp quỹ; quỹ→mã cần Funds_holdings_detail): top redemptions / inflows 1M among funds with a NAV date ≤45 d
    fund_flows = None
    ff = S["fflow"]["data"] if isinstance(S["fflow"]["data"], dict) else None
    if ff:
        rows = []
        for k, f in (ff.get("funds") or {}).items():
            fm, nd = (f.get("flow_mn") or {}), f.get("nav_date")
            v = C.finite(fm.get("m1"))
            if v is None or not nd:
                continue
            age = C.age_int(C.parse_day(nd))
            if age is None or age > C.STALE_DAYS:
                continue
            rows.append({"quy": k, "ten": f.get("name"), "flow_1m": C.num(v / 1000.0, "tỷ đồng", nd, S["fflow"]["meta"].effective_tier(), "fund_flows.funds[].flow_mn.m1 (Vietcap funds?tab=flow)", txt=C.fmt_vn(v / 1000.0, 0, True)),
                         "nav_bn": C.finite(f.get("nav_total_bn")), "loai": f.get("type"), "cau_truc": f.get("structure")})
        rows.sort(key=lambda r: r["flow_1m"]["v"] or 0)
        fund_flows = {"as_of": ff.get("as_of"), "n_funds": len(ff.get("funds") or {}), "n_usable": len(rows), "b": S["fflow"]["meta"].effective_tier(),
                      "top_redemptions_1m": rows[:8], "top_inflows_1m": rows[::-1][:8], "caveat": C.fund_nav_caveat(S),
                      "n": "fund_holdings/fund_flows.json — cấp quỹ; chưa map quỹ→mã (cần Funds_holdings_detail)"}
    counts = {"universe": len(tickers), "memo": len(memos), "memo_deep": deep,
              "memo_missing": len([t for t in tickers if t not in memos]),
              "worksheet_deep": ws_deep, "worksheet_ollama": ws_ollama,
              "vc_lk": len(vc & set(tickers)) if tickers else len(vc), "vc_lk_missing": len(set(tickers) - vc),
              "lk_hoso": len(lk & set(tickers)) if tickers else len(lk), "hhp_series": len(hs & set(tickers)) if tickers else len(hs),
              "vf": len(set(vf or {}) & set(tickers)) if tickers else len(vf or {})}
    actions = []
    if S["fund"]["meta"].status() in ("stale", "missing"):
        actions.append({"muc": "chan", "viec": "Refresh fund_intent_signals.json (GATE LVF đang mù)",
                        "lenh": "Tải Excel holdings từ Vietcap IQ /iq/funds?tab=holdings (login) → python3 fund_holdings/ingest_fund_holdings.py",
                        "ly_do": "Excel tải tay, login-gated — single point of human failure; %s" % S["fund"]["meta"].to_json()["age_txt"]})
    if S["fund"]["meta"].status() not in ("stale", "missing") and not C.fund_detail_available(S):
        actions.append({"muc": "nen", "viec": "Tải Funds_holdings_detail (per-quỹ) cho mã danh mục/watchlist — GATE LVF đang chưa lọc cơ học",
                        "lenh": "Vietcap IQ /iq/funds?tab=holdings (login) → gõ từng mã → Download ↓ → bỏ vào fund_holdings/raw/ → python3 fund_holdings/ingest_fund_holdings.py",
                        "ly_do": "aggregate %s tươi nhưng thiếu detail per-quỹ nên không tách được ETF rổ / quỹ mới khỏi net" % S["fund"]["meta"].to_json()["as_of_txt"]})
    if counts["memo_missing"] or deep < len(memos):
        actions.append({"muc": "nen", "viec": "Kick Phase B — memo deep còn thiếu %d mã, %d mã chưa có memo" % (len(memos) - deep, counts["memo_missing"]),
                        "lenh": "Workflow gen_remaining_memos.js (mẻ ≤15 mã, hardcode const W) → bash fa_insight/monthly_refresh.sh render",
                        "ly_do": "ưu tiên danh mục + watchlist > mã EDI bật > phần còn lại"})
    if counts["vc_lk_missing"]:
        actions.append({"muc": "nen", "viec": "Fetch Vietcap IQ cho %d mã universe chưa có cache vc_lk" % counts["vc_lk_missing"],
                        "lenh": "python3.14 fincept_bridge/vc_lk_fetch.py --ma <list> (≥10 s/request; tránh 16:10)", "ly_do": "chỉ fetcher này được phép (LK_HOSO_SPEC §0.6)"})
    if U["meta"].status() != "ok":
        actions.append({"muc": "nho", "viec": "Universe %s — kiểm rebalance rổ" % U["meta"].to_json()["age_txt"],
                        "lenh": "python3 fa_insight/gen_filings_manifest.py (sau khi cập nhật universe.json)", "ly_do": "as_of 18/06"})
    for k in ("hhp", "vf", "cov", "edi", "smap", "ffttin"):
        if S[k]["meta"].status() in ("stale", "missing"):
            actions.append({"muc": "nen", "viec": "%s %s" % (S[k]["meta"].label, S[k]["meta"].status()), "lenh": "kiểm LaunchAgent tương ứng (launchctl list | grep hoidongcovanai)",
                            "ly_do": S[k]["meta"].to_json()["age_txt"]})
    return {"fund_flows": fund_flows, "meta": meta_block(), "layers": layers, "counts": counts,
            "memo_dates": [{"date": d, "n": n} for d, n in sorted(dates.items(), reverse=True)],
            "actions": actions, "gates": gates_block(S)}


# ── overview ─────────────────────────────────────────────────────────────────


def _dm_of(fftlk, tk):
    """NAV / WATCH / AVOID from fft_langkinh.ma.<TK>.dm (mirrors fft_cauhinh.danh_muc)."""
    m = C.by_ticker(fftlk, tk) or {}
    dm = m.get("dm")
    if isinstance(dm, dict):
        if dm.get("nav") is not None:
            return "NAV", C.finite(dm.get("nav"))
        if dm.get("watch"):
            return "WATCH", None
        if dm.get("avoid"):
            return "AVOID", None
    if isinstance(dm, str):
        u = dm.upper()
        if "NAV" in u:
            return "NAV", None
        if "WATCH" in u:
            return "WATCH", None
        if "AVOID" in u or "TRÁNH" in u:
            return "AVOID", None
    return "", None


def _ro_of(entry, tk, hhp_row):
    ro = []
    g = (entry or {}).get("group") or ""
    if g in ("VN30", "VN100", "VN101-200", "VN200"):
        ro.append(g)
    elif g:
        ro.append("CHAEBOL:" + g)
    rank = C.finite((entry or {}).get("mktcap_rank"))
    if rank is not None and rank <= 30 and "VN30" not in ro:
        ro.append("VN30")
    if rank is not None and rank <= 100 and "VN100" not in ro:
        ro.append("VN100")
    return ro


def overview_row(tk, entry, memos, S, warnings, flow_cache=None):
    d, p = C.find_memo(tk, memos)
    row = {"tk": tk, "ten": (entry or {}).get("name") or tk, "nhom": (entry or {}).get("group") or "", "ro": _ro_of(entry, tk, None),
           "mktcap_rank": C.finite((entry or {}).get("mktcap_rank"))}
    row["dm"], row["nav_pct"] = _dm_of(S["fftlk"], tk)
    flags = []
    # memo
    M = C.parse_memo(p) if p else None
    if M and "error" not in M:
        age = C.age_int(d)
        row.update({"memo_date": C.iso(d), "memo_age_days": age, "memo_age_txt": "%d ngày" % age,
                    "memo_status": "ok" if age <= C.WARN_DAYS else ("warn" if age <= C.STALE_DAYS else "stale"),
                    "deep": M["deep"], "engine": M["engine"], "state": M["state"], "state_txt": M["state_label"],
                    "regime_memo": M["regime"], "gia_memo": C.num(M["price"], "đồng", None, "SS-T3" if M["price_src"] == "CIQ" else "FACT-T2",
                                                                  "memo H1 [%s·%s]" % (M["price_src"], M["price_date"]), txt=C.fmt_vn(M["price"], 0)),
                    "rigor": {"tags": M["n_tags"], "need": M["n_need"], "words": M["n_words"]},
                    "break_point": M["break_point"], "break_point_src": M["break_point_src"]})
        if age > C.STALE_DAYS:
            flags.append("memo %d ngày → UNVERIFIED" % age)
        if not M["deep"]:
            flags.append("memo chưa deep (không có §2 TENSION)")
        if not M["break_point"]:
            flags.append("memo không nêu điểm gãy")
    else:
        row.update({"memo_date": None, "memo_age_days": None, "memo_age_txt": "chưa có memo", "memo_status": "missing",
                    "deep": False, "engine": None, "state": None, "state_txt": "", "gia_memo": C.num(None, "đồng"), "rigor": None,
                    "break_point": None, "break_point_src": None})
        flags.append("chưa có memo")
    # live price / flow
    flow = C.vc_price_flow_cached(tk, cache=flow_cache)
    if flow.get("ok"):
        row["gia"] = flow["close"]
        row["pe"] = flow.get("pe") or C.num(None, "x")
        row["pb"] = flow.get("pb") or C.num(None, "x")
        row["foreign_net_20"] = flow["foreign_net_20"]
        row["prop_net_20"] = flow["prop_net_20"]
        if d:
            hist = C.close_on_or_before_cached(flow, d)
            if hist and hist[2] and flow["close_adj"]["v"]:
                delta = (flow["close_adj"]["v"] / hist[2] - 1.0) * 100.0
                row["delta_pct"] = C.num(delta, "%", flow["t"], "FACT-T2", "vc_lk price-history.closePriceAdjusted (điều chỉnh CA) %s→%s" % (C.iso(hist[0]), flow["t"]),
                                         txt=C.fmt_pct(delta, 1))
            else:
                row["delta_pct"] = C.num(None, "%")
        else:
            row["delta_pct"] = C.num(None, "%")
    else:
        row["gia"] = C.num(None, "đồng", g=flow.get("ly_do"))
        row["pe"] = row["pb"] = C.num(None, "x")
        row["foreign_net_20"] = row["prop_net_20"] = C.num(None, "tỷ đồng")
        row["delta_pct"] = C.num(None, "%")
        flags.append("chưa có cache Vietcap (vc_lk)")
    # HHP σ (with date)
    h = C.by_ticker(S["hhp"], tk) or {}
    pe = h.get("pe") if isinstance(h.get("pe"), dict) else {}
    hhp_t = C.iso(S["hhp"]["meta"].asof())
    row["sigma_pe"] = C.num(C.finite(pe.get("sigma")), "σ", hhp_t, S["hhp"]["meta"].effective_tier(), "hhp_vn100_valuation.by_ticker.pe.sigma",
                            txt=C.fmt_vn(C.finite(pe.get("sigma")), 2, True) + "σ" if C.finite(pe.get("sigma")) is not None else "[CẦN DATA]")
    row["zone_pe"] = pe.get("zone")
    # EDI
    e = C.by_ticker(S["edi"], tk) or {}
    row["edi"] = C.num(C.finite(e.get("edi")), "/100", C.iso(S["edi"]["meta"].asof()), S["edi"]["meta"].effective_tier(), "edi_index.by_ticker.edi",
                       txt=C.fmt_vn(C.finite(e.get("edi")), 0) if C.finite(e.get("edi")) is not None else "[CẦN DATA]")
    row["edi_stage"] = e.get("lead_status")
    row["edi_late"] = bool(e.get("late_flag"))
    # BLĐ vs street
    mg = C.by_ticker(S["mgmt"], tk) or {}
    vs = mg.get("vs_street") or {}
    row["bld_tone"] = (mg.get("tone") or {}).get("net")
    row["align"] = vs.get("alignment")
    row["street_up"], row["street_down"] = C.finite(vs.get("street_up")), C.finite(vs.get("street_down"))
    if str(row["align"] or "").startswith("⚠"):
        flags.append("lệch pha BLĐ/street")
    # coverage (SS-T3)
    cv = C.coverage_view(C.coverage_row(S["cov"], tk))
    if cv:
        row["tp"] = C.num(cv["target_price"], "đồng", cv["tp_date"], "SS-T3", cv["n"], g=cv["tp_flag_txt"], txt=cv["target_price_txt"])
        row["tp_upside_pct"], row["tp_stale"], row["rating"] = cv["upside_pct"], cv["tp_stale"], cv["rating"]
        if cv["tp_stale"]:
            flags.append("TP Vietcap cũ %d ngày" % cv["tp_age_days"])
    else:
        row["tp"] = C.num(None, "đồng"); row["tp_upside_pct"] = None; row["tp_stale"] = None; row["rating"] = None
    # fund intent gate
    g = C.gate_lvf(C.by_ticker(S["fund"], tk), S["fund"]["meta"], etfc=S.get("etfc"), tk=tk)
    row["fund_gate"] = g["trang_thai"]
    row["fund_label"] = g.get("nhan_sau_gate") or ("GATE-BLIND" if g["trang_thai"] == "GATE-BLIND" else None)
    if g["trang_thai"] == "GATE-BLIND":
        flags.append("fund intent GATE-BLIND")
    ef = g.get("etf_du_bao") or {}
    row["etf_du_bao_txt"] = ef.get("txt")
    if ef.get("so_ngay_gd") is not None and ef["so_ngay_gd"] >= 1.0:
        flags.append("ETF review %s ngày KLGD" % C.fmt_vn(ef["so_ngay_gd"], 1))
    # filings / worksheet
    pf = C.by_ticker(S["pf"], tk) or {}
    row["n_filings"] = C.finite(pf.get("n_filings"))
    ws = C.load_worksheet(tk)
    row["worksheet_engine"] = (ws["data"] or {}).get("engine") if ws["data"] else None
    # regen rule
    reasons = []
    if row["memo_status"] == "missing":
        reasons.append("chưa có memo")
    elif row["memo_age_days"] is not None and row["memo_age_days"] > C.MEMO_REGEN_DAYS:
        reasons.append("memo > %d ngày" % C.MEMO_REGEN_DAYS)
    if d and _quarter_end_passed(d):
        reasons.append("đã qua kỳ BCTC mới sau ngày memo")
    row["can_regen"] = bool(reasons)
    row["can_regen_ly_do"] = "; ".join(reasons) if reasons else None
    row["flags"] = flags
    return row


def _quarter_end_passed(memo_date):
    """True when a quarterly report deadline (30/04, 30/07, 31/10, 30/01) lies between memo date and today."""
    t = C.today()
    marks = []
    for y in (memo_date.year, memo_date.year + 1):
        for mm, dd in ((1, 30), (4, 30), (7, 30), (10, 31)):
            try:
                marks.append(C.date(y, mm, dd))
            except ValueError:
                pass
    return any(memo_date < m <= t for m in marks)


def build_overview():
    S = C.load_shared()
    U = C.load_universe()
    if not U["tickers"]:
        raise DeepFaError("NO_DATA", "Không đọc được fa_insight/universe.json (%s). Kiểm vault %s." % (U["meta"].error or "rỗng", C.vault()))
    memos = C.list_memos()
    warnings = []
    for k in S:
        m = S[k]["meta"]
        if m.status() in ("stale", "missing"):
            warnings.append("%s %s (%s)" % (m.label, m.status(), m.to_json()["age_txt"]))
    if S["ffttin"].get("phien_ban_ok") is False:
        warnings.append("fft_tin.json phien_ban ≠ 1 — schema đổi, lớp sự kiện tự động tắt")
    rows = []
    order = sorted(U["tickers"].items(), key=lambda kv: (C.finite((kv[1] or {}).get("mktcap_rank")) or 9999, kv[0]))
    flow_cache = C.load_flow_cache()
    for tk, entry in order:
        rows.append(overview_row(tk, entry, memos, S, warnings, flow_cache))
    cache_saved = C.save_flow_cache(flow_cache)
    meta = meta_block()
    meta.update({"n_rows": len(rows), "freshness": [S[k]["meta"].to_json() for k in S] + [U["meta"].to_json()], "warnings": warnings,
                 "memo_dir": C.memo_dir(), "web_index": "http://localhost:9000/baocao/index.html",
                 "flow_cache": C.flow_cache_path() if cache_saved else None})
    return {"meta": meta, "gates": gates_block(S), "rows": rows}


# ── ticker (contract filled in from DEEPFA_MODULE_SPEC §4) ───────────────────


def build_ticker(tk):
    try:
        import deepfa_ticker  # noqa: F401 — the per-ticker page lives in its own module
    except ImportError:
        raise DeepFaError("INTERNAL", "deepfa_ticker.py chưa có trong thư mục scripts — chạy provision_fincept.py sync_scripts().")
    return deepfa_ticker.build(tk)


# ── CLI ──────────────────────────────────────────────────────────────────────


def run(argv):
    if len(argv) < 2:
        raise DeepFaError("BAD_ARGS", "Thiếu lệnh. " + USAGE)
    cmd = argv[1].strip().lower()
    if cmd == "status":
        return build_status()
    if cmd == "overview":
        return build_overview()
    if cmd == "ticker":
        if len(argv) < 3:
            raise DeepFaError("BAD_ARGS", "Thiếu mã cổ phiếu. " + USAGE)
        tk = argv[2].strip().upper()
        if not TICKER_RE.fullmatch(tk):
            raise DeepFaError("BAD_ARGS", "Mã không hợp lệ: %r (chỉ 2–6 ký tự A–Z, 0–9). %s" % (argv[2], USAGE))
        return build_ticker(tk)
    raise DeepFaError("BAD_ARGS", "Lệnh không hỗ trợ: %r. %s" % (argv[1], USAGE))


def strip_private(obj):
    """Drop keys starting with '_' (internal rows kept for computation, never for the panel)."""
    if isinstance(obj, dict):
        return {k: strip_private(v) for k, v in obj.items() if not (isinstance(k, str) and k.startswith("_"))}
    if isinstance(obj, list):
        return [strip_private(v) for v in obj]
    return obj


def emit(obj):
    text = json.dumps(C.clean(strip_private(obj)), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    buf = getattr(sys.stdout, "buffer", None)
    if buf is not None:
        buf.write(text.encode("utf-8") + b"\n")
        buf.flush()
    else:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()


def main(argv=None):
    argv = sys.argv if argv is None else argv
    try:
        emit(run(argv))
    except DeepFaError as exc:
        emit({"error": str(exc), "error_code": exc.code})
    except Exception as exc:  # noqa: BLE001 — the panel must always get one JSON object
        emit({"error": "Lỗi nội bộ deepfa.py: %s" % exc, "error_code": "INTERNAL", "trace": traceback.format_exc()[-1500:]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
