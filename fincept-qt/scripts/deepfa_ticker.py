#!/usr/bin/env python3
"""
Fincept Terminal — DEEP FA per-ticker page builder (`deepfa.py ticker <TK>`), contract in
fincept_bridge/DEEPFA_MODULE_SPEC.md §4.3. Stdlib only; reads the disk through deepfa_core and
derives through deepfa_rules; never fetches, never writes the vault (kg_index cache aside).

Page order (spec Q1): CỔNG/header → thesis + điểm gãy → §7 checklist sống → TENSION memo ⚔ sống →
chủ thể & dòng tiền → định giá → filing teardown → codex/EDI/board → đồ thị tri thức → ledger → phụ lục.
A ticker without a memo still renders: every memo-derived slice is null with a "[CẦN DATA]" note; the
live layers (Vietcap IQ cache, EDI, street, HHP, KG) fill what they can.
"""

import html
import os
import re
from datetime import datetime

import deepfa_core as C
import deepfa_rules as R

try:  # same scripts dir; only the pure series→chart reshaping is borrowed (no data dir side effects)
    import hhp_valuation as _hv
except Exception:  # noqa: BLE001
    _hv = None

_NEED = "[CẦN DATA]"


# ── markdown → simple rich text (QLabel) ─────────────────────────────────────


def _inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", s)
    s = re.sub(r"(?<![\w_])_([^_\n]+)_(?![\w_])", r"<i>\1</i>", s)
    return s


def md_to_html(md, max_chars=20000):
    """Paragraphs, bullets, ### headings, > quotes, tables (as mono block). Good enough for memo prose."""
    if not md:
        return ""
    md = md[:max_chars]
    out, para, i = [], [], 0
    lines = md.split("\n")
    def flush():
        if para:
            out.append("<p>%s</p>" % " ".join(_inline(x) for x in para))
            del para[:]
    while i < len(lines):
        l = lines[i].rstrip()
        if not l.strip():
            flush(); i += 1; continue
        if l.startswith("|"):
            flush(); block = []
            while i < len(lines) and lines[i].startswith("|"):
                block.append(html.escape(lines[i])); i += 1
            out.append("<pre style='font-size:11px'>%s</pre>" % "\n".join(block)); continue
        m = re.match(r"^(#{1,4})\s+(.*)$", l)
        if m:
            flush(); out.append("<p><b>%s</b></p>" % _inline(m.group(2))); i += 1; continue
        if l.startswith(">"):
            flush(); out.append("<p style='color:#8b9099'><i>%s</i></p>" % _inline(l.lstrip("> "))); i += 1; continue
        m = re.match(r"^\s*(?:[-*•]|\d+\.)\s+(.*)$", l)
        if m:
            flush(); items = []
            while i < len(lines):
                mm = re.match(r"^\s*(?:[-*•]|\d+\.)\s+(.*)$", lines[i].rstrip())
                if not mm:
                    break
                items.append("<li>%s</li>" % _inline(mm.group(1))); i += 1
            out.append("<ul>%s</ul>" % "".join(items)); continue
        para.append(l.strip()); i += 1
    flush()
    return "".join(out)


def _sec(M, key):
    return ((M or {}).get("by_key") or {}).get(key, {}).get("text") if M else None


# ── pieces ───────────────────────────────────────────────────────────────────


def _pctile(rows, key, window_days=None, today=None):
    """Percentile (0–100) of the latest value within the window of ratio-daily rows (EST)."""
    vals = []
    t = today or C.today()
    for r in rows:
        d = C.parse_day(r.get("tradingDate"))
        v = C.finite(r.get(key))
        if v is None or v <= 0 or d is None:
            continue
        if window_days and (t - d).days > window_days:
            continue
        vals.append(v)
    if len(vals) < 30:
        return None, len(vals)
    cur = vals[-1]
    rank = sum(1 for v in vals if v <= cur) / float(len(vals)) * 100.0
    return round(rank, 1), len(vals)


def build_hhp_chart(tk):
    s = C.load_hhp_series(tk)
    if not s["data"] or _hv is None:
        return None
    try:
        pe = _hv.ticker_metric(s["data"].get("pe"))
    except Exception:  # noqa: BLE001
        return None
    if not pe or not (pe.get("chart") or {}).get("price"):
        return None
    ch = pe["chart"]
    return {"metric": "pe", "unit": "nghìn đồng", "as_of": pe.get("as_of"), "sigma": C.finite(pe.get("sigma")), "zone": pe.get("zone"),
            "price": ch.get("price"), "fair": ch.get("fair"), "cheap1": ch.get("cheap1"), "cheap2": ch.get("cheap2"), "rich1": ch.get("rich1"), "rich2": ch.get("rich2"),
            "b": "EST", "n": "knowledge_os/hhp_vn100_series/%s.json (DCHART adjusted, nghìn đồng)" % tk,
            "g": "chuỗi giá DCHART điều chỉnh CA — khác giá bảng ở header (cùng cơ sở với Δ memo)"}


def build_worksheet_block(ws):
    d = ws.get("data")
    meta = ws["meta"].to_json()
    if not d:
        return {"co": False, "meta": meta, "ly_do": "chưa có worksheet fa_insight/worksheets/<TK>.json — Lớp 2 chưa đọc filing mã này"}
    ins = d.get("insights") or {}
    labels = [("earnings_quality", "Chất lượng lợi nhuận"), ("dilution", "Pha loãng / cấu trúc vốn"), ("intercompany_flows", "Dòng tiền nội bộ / cash-to-parent"),
              ("dividend_buffer", "Đệm cổ tức (LNCPP)"), ("run_rate", "Run-rate"), ("margin_dynamics", "Biên"), ("red_flags", "Red flags"),
              ("sotp", "SOTP / giá trị ẩn"), ("governance", "Quản trị / cổ đông / insider"), ("catalysts", "Catalyst")]
    tag_re = re.compile(r"\[(BCTC[^\]·]*|BCTN|DHCD|ĐHCĐ|BC_QuanTri|Vietcap[^\]]*|HSC[^\]]*|CIQ[^\]]*|EST|FACT-T1|FACT-T2|SS-T3)[^\]]*\]")
    def tier_of(text):
        tags = [m.group(1) for m in tag_re.finditer(text or "")]
        if any(t.startswith("BCTC") or t == "FACT-T1" for t in tags):
            return "FACT-T1", tags
        if any(t in ("BCTN", "DHCD", "ĐHCĐ", "BC_QuanTri", "FACT-T2") for t in tags):
            return "FACT-T2", tags
        if any(t.startswith(("Vietcap", "HSC", "CIQ", "SS")) for t in tags):
            return "SS-T3", tags
        return "EST", tags
    engine = d.get("engine")
    stale = ws["meta"].status() in ("stale", "missing")      # >45 ngày: mọi số/nhận định trong worksheet hạ UNVERIFIED (luật §1)
    groups = []
    for key, label in labels:
        v = ins.get(key)
        text = v if isinstance(v, str) else (v.get("structure_note") if isinstance(v, dict)
                                             else ("; ".join(str((x.get("event") or x.get("note") or x) if isinstance(x, dict) else x) for x in v) if isinstance(v, list) else ""))
        tier, tags = tier_of(text or "")
        need = "[CẦN" in (text or "")
        gate = (key in ("governance", "intercompany_flows", "dilution") and engine != "claude-deep")
        notes = []
        if gate:
            notes.append("engine %s — lớp governance/intercompany/dilution chỉ tin khi claude-deep" % (engine or "?"))
        if stale and text:
            notes.append("worksheet %s → hạ UNVERIFIED (luật >45 ngày); tag gốc %s" % (meta.get("age_txt"), tier))
        groups.append({"key": key, "label": label, "text": text or _NEED, "html": md_to_html(text or _NEED, 4000),
                       "tier": ("UNVERIFIED" if (stale or not text) else tier), "tier_goc": tier if text else None,
                       "tags": tags[:6], "need": need, "gated": gate, "g": " · ".join(notes) if notes else None})
    read_list = []
    for s in d.get("sources") or []:
        if not isinstance(s, dict):                       # some ollama worksheets list sources as bare strings
            s = {"file": str(s), "tag": None, "path": "", "status": None, "method": None}
        p = s.get("path") or ""
        read_list.append({"tag": s.get("tag"), "file": s.get("file"), "path": p, "exists": bool(p and os.path.exists(p)), "status": s.get("status"), "method": s.get("method")})
    return {"co": True, "meta": meta, "engine": engine, "as_of": d.get("as_of"), "confidence": C.finite(d.get("confidence_score")), "confidence_level": d.get("confidence_level"),
            "summary_html": md_to_html(d.get("summary") or "", 6000), "groups": groups, "read_list": read_list, "n_read": sum(1 for r in read_list if r["status"] == "read"),
            "doc_gaps": [str(x) for x in (d.get("doc_gaps") or [])]}


def build_chu_the(tk, lk, flow, gated, S, kg):
    d = lk.get("data")
    out = {"meta": lk["meta"].to_json(), "co": bool(d)}
    if not d:
        out["ly_do"] = "chưa có hồ sơ lăng kính lk_hoso/%s.json — chạy lk_hoso.py --ma %s" % (tk, tk)
    else:
        ct = d.get("chuthe") or {}
        out["nhan"] = ct.get("nhan")
        nb = []
        for x in (ct.get("noi_bo") or [])[:10]:
            nb.append({k: x.get(k) for k in ("ngay", "nguoi", "chuc_vu", "hanh_dong", "so_luong", "trang_thai", "gia_bao_cao", "bac", "nguon") if k in x})
        out["noi_bo"] = nb
        out["su_kien_von"] = (ct.get("su_kien_von") or [])[:8]
        ng = d.get("ngoai") or {}
        out["ngoai"] = {k: ng.get(k) for k in ("hien_pct", "hien_pct_tong_cp", "room", "rong_20", "chuoi_tuan", "xu_huong") if k in ng}
        td = d.get("tudoanh") or {}
        out["tudoanh"] = {k: td.get(k) for k in ("rong_20", "rong_63", "xu_huong") if k in td}
        cd = d.get("codong") or {}
        out["codong"] = {"trang_thai": cd.get("trang_thai"), "nguon_moc": cd.get("nguon_moc"), "moc": (cd.get("moc") or [])[-8:], "k": cd.get("k"), "pattern": cd.get("pattern")}
        out["pha"] = d.get("pha")
        out["trigger"] = (d.get("trigger") or [])[:8]
        out["trigger_phan_doan"] = d.get("trigger_phan_doan")
        out["can_data"] = d.get("can_data") or []
        out["sigma_lk"] = d.get("sigma")
    out["flow"] = {k: flow.get(k) for k in ("foreign_net_20", "prop_net_20", "foreign_pct", "foreign_room", "turnover_avg_20") if k in flow}
    out["fund"] = gated
    props = (kg or {}).get("props") or {}
    if props.get("nqs_nn_net_20d_bn") is not None:
        out["nqs_doi_chieu"] = C.num(C.finite(props.get("nqs_nn_net_20d_bn")), "tỷ đồng", (props.get("nqs_scraped_at") or "")[:10], "SS-T3", "KG ticker props nqs_nn_net_20d_bn (NguoiQuanSat)",
                                     g="persistence %s" % props.get("nqs_nn_persistence"), txt=C.fmt_vn(C.finite(props.get("nqs_nn_net_20d_bn")), 0, True))
    oi = C.by_ticker(S["owner"], tk) or {}
    ev = [e for e in (oi.get("events") or []) if isinstance(e, dict)]
    ev.sort(key=lambda e: e.get("date") or "", reverse=True)
    out["y_do_chu_the"] = [{k: e.get(k) for k in ("date", "type", "title", "direction", "magnitude", "verified", "auto")} for e in ev[:8]]
    out["y_do_meta"] = S["owner"]["meta"].to_json()
    return out


def build_dinh_gia(tk, M, flow, S, cv, ev):
    h = C.by_ticker(S["hhp"], tk) or {}
    pe, pb = (h.get("pe") if isinstance(h.get("pe"), dict) else {}), (h.get("pb") if isinstance(h.get("pb"), dict) else {})
    t_h = C.iso(S["hhp"]["meta"].asof())
    def blk(x, name):
        return {"now": C.finite(x.get("now")), "mean": C.finite(x.get("mean")), "sd": C.finite(x.get("sd")), "sigma": C.finite(x.get("sigma")), "zone": x.get("zone"),
                "n": C.finite(x.get("n")), "reliable": x.get("reliable"), "t": t_h, "b": S["hhp"]["meta"].effective_tier(), "src": "hhp_vn100_valuation.by_ticker.%s" % name,
                "sigma_txt": (C.fmt_vn(C.finite(x.get("sigma")), 2, True) + "σ") if C.finite(x.get("sigma")) is not None else _NEED}
    rows = flow.get("_ratio_rows") or []
    p3, n3 = _pctile(rows, "pe", 365 * 3)
    pa, na = _pctile(rows, "pe", None)
    pb3, _ = _pctile(rows, "pb", 365 * 3)
    pba, _ = _pctile(rows, "pb", None)
    tp_strip = []
    if cv and cv.get("target_price"):
        tp_strip.append({"nguon": "Vietcap coverage", "tp": cv["target_price"], "tp_txt": cv["target_price_txt"], "rec": cv.get("rating"), "t": cv.get("tp_date"), "age_d": cv.get("tp_age_days"),
                         "stale": cv.get("tp_stale"), "upside_pct": cv.get("upside_pct"), "b": "SS-T3", "analyst": cv.get("analyst")})
    evd = ev.get("data") or {}
    for c in (evd.get("broker_calls") or [])[:6]:
        tp = C.finite(c.get("target_price"))
        d = c.get("date")
        a = C.age_int(C.parse_day(d))
        tp_strip.append({"nguon": c.get("broker"), "tp": tp, "tp_txt": C.fmt_vn(tp, 0), "rec": (c.get("rec") or [None])[0] if isinstance(c.get("rec"), list) else c.get("rec"),
                         "t": d, "age_d": a, "stale": (a is not None and a > C.TP_STALE_DAYS), "b": "UNVERIFIED" if ev["meta"].status() in ("stale", "missing") else "SS-T3",
                         "title": (c.get("title") or "")[:120]})
    return {"memo_html": md_to_html(_sec(M, "§6") or "", 12000) if M else "", "memo_co": bool(_sec(M, "§6")),
            "sigma": {"pe": blk(pe, "pe"), "pb": blk(pb, "pb"), "g": "σ theo chính lịch sử ratio của mã (HHP, finfo) — KHÔNG so ngành; price_now HHP không dùng"},
            "ratio_song": {"pe": flow.get("pe") or C.num(None, "x"), "pb": flow.get("pb") or C.num(None, "x")},
            "pctile": {"pe_3y": p3, "pe_all": pa, "pb_3y": pb3, "pb_all": pba, "n_3y": n3, "n_all": na, "t": flow.get("t"), "b": "EST", "n": "vc_lk ratio-daily (Vietcap, 10 năm)",
                       "g": "percentile của giá trị hiện tại trong cửa sổ; luật §6.5: chấm cả 3Y và toàn dải"},
            "hhp_chart": build_hhp_chart(tk), "tp_strip": tp_strip,
            "gia_note": "giá bảng = lk_hoso.gia.bang (kho vci_board) khi mới hơn, nếu không = vc_lk closePrice (FACT-T2, phiên đã đóng); chart HHP dùng chuỗi điều chỉnh (nghìn đồng); Δ memo/σ quy về cùng cơ sở CA của chuỗi vc_lk"}


def build_phu_luc(tk, M, S, memo_date, cond, break_point, layers_used):
    tin = C.by_ticker(S["ffttin"], tk) or {}
    events = []
    for e in (tin.get("su_kien") or []):
        if not isinstance(e, dict) or e.get("bac") == "UNVERIFIED":
            continue
        events.append({"ngay": e.get("ngay"), "mo_ta": (e.get("mo_ta") or "")[:160], "bac": e.get("bac"), "loai": e.get("loai"), "the_loai": e.get("the_loai"),
                       "chu_the": e.get("chu_the"), "so_luong_cp": e.get("so_luong_cp"), "nguon": e.get("nguon_id"), "sau_memo": bool(memo_date and (e.get("ngay") or "") > C.iso(memo_date))})
    ef = C.etf_forecast_for(tk, S.get("etfc"))
    if ef and ef.get("tong_cp") is not None:
        events.append({"ngay": ef["t"], "mo_ta": "Dự báo ETF kỳ review (Vietcap, chưa khớp; ngày = ngày xuất): " + ef["txt"],
                       "bac": ef["b"], "loai": "ETF_FORECAST", "the_loai": "dòng tiền cơ học", "chu_the": "ETF rổ", "so_luong_cp": ef["tong_cp"],
                       "nguon": "vietcap-funds-forecast", "sau_memo": bool(memo_date and (ef["t"] or "") > C.iso(memo_date))})
    events.sort(key=lambda e: e.get("ngay") or "", reverse=True)
    vf = C.by_ticker(S["vf"], tk) or {}
    news = []
    for a in (vf.get("ainews") or [])[:12]:
        if isinstance(a, dict):
            news.append({"date": a.get("date"), "title": (a.get("title") or "")[:140], "sentiment": a.get("sentiment"), "source": a.get("source_name"),
                         "sau_memo": bool(memo_date and (a.get("date") or "") > C.iso(memo_date))})
    div = [e for e in (vf.get("events") or []) if isinstance(e, dict)][:8]
    return {"memo_html": md_to_html(_sec(M, "§8") or "", 16000) if M else "", "memo_co": bool(_sec(M, "§8")),
            "catalyst": events[:20], "n_catalyst_sau_memo": sum(1 for e in events if e["sau_memo"]),
            "tin_sau_memo": news, "co_tuc_phat_hanh": div,
            "nguon": layers_used, "rigor": R.rigor_6d_proxy(M, cond, break_point) if M else None,
            "registry_gaps": ["sổ nguồn chưa có id cho cache Vietcap IQ lăng kính (price-history/ratio-daily/proprietary/insider/shareholder) — đề xuất 'vietcap-lk' FACT-T2",
                              "'vietcap-iq' hiện = SS-T3 chỉ đúng cho targetPrice/rating/forward; kiem trỏ vào hhp_vn100_valuation.json (dẫn xuất)"],
            "ffttin_meta": S["ffttin"]["meta"].to_json()}


# ── main builder ─────────────────────────────────────────────────────────────


def build(tk):
    S = C.load_shared()
    U = C.load_universe()
    entry = (U["tickers"] or {}).get(tk) or {}
    memos = C.list_memos()
    d, p = C.find_memo(tk, memos)
    M = C.parse_memo(p) if p else None
    if M and "error" in M:
        M = None
    memo_age = C.age_int(d) if d else None
    memo_status = ("ok" if memo_age <= C.WARN_DAYS else ("warn" if memo_age <= C.STALE_DAYS else "stale")) if memo_age is not None else "missing"
    memo_tier = "UNVERIFIED" if memo_status in ("stale", "missing") else "theo tag"
    flow = C.vc_price_flow(tk)
    gated = C.gate_lvf(C.by_ticker(S["fund"], tk), S["fund"]["meta"], etfc=S.get("etfc"), tk=tk)
    gated["nav_caveat"] = C.fund_nav_caveat(S)
    live = C.tension_live(tk, S, flow, gated)
    cv = C.coverage_view(C.coverage_row(S["cov"], tk))
    ws = C.load_worksheet(tk)
    ev = C.load_evidence(tk)
    lk = C.load_lk_hoso(tk)
    kg = R.kg_neighborhood(tk)
    ca = R.ca_factor_since(flow, d) if (flow.get("ok") and d) else None

    # header
    gia_memo = C.num(M["price"], "đồng", None, "SS-T3" if (M and M.get("price_src") == "CIQ") else "FACT-T2",
                     "memo H1 [%s·%s]" % (M["price_src"], M["price_date"]) if M else "", txt=C.fmt_vn(M["price"], 0)) if M else C.num(None, "đồng")
    delta = C.num(None, "%")
    if flow.get("ok") and d:
        hist = C.close_on_or_before(flow["_rows"], d)
        if hist and hist[2] and flow["close_adj"]["v"]:
            dv = (flow["close_adj"]["v"] / hist[2] - 1.0) * 100.0
            delta = C.num(dv, "%", flow["t"], "FACT-T2", "vc_lk closePriceAdjusted %s→%s (điều chỉnh CA)" % (C.iso(hist[0]), flow["t"]), txt=C.fmt_pct(dv, 1))
    h = C.by_ticker(S["hhp"], tk) or {}
    pe_h = h.get("pe") if isinstance(h.get("pe"), dict) else {}
    e = C.by_ticker(S["edi"], tk) or {}
    # giá bảng: chuỗi vc_lk (phiên đã đóng) — thay bằng lk_hoso.gia.bang (kho.gia_moi vci_board) khi mốc đó MỚI HƠN;
    # Δ memo, σ và percentile vẫn tính trên chuỗi vc_lk (điều chỉnh CA), nên ghi rõ hai mốc.
    gia = flow.get("close") or C.num(None, "đồng", g=flow.get("ly_do"))
    bang = (((lk.get("data") or {}).get("gia") or {}).get("bang")) if isinstance(lk.get("data"), dict) else None
    if isinstance(bang, dict) and C.finite(bang.get("v")) is not None and bang.get("t") and (not gia.get("t") or str(bang["t"]) > str(gia["t"])):
        bv = C.finite(bang["v"]) * (1000.0 if bang.get("u") == "nghin_dong" else 1.0)
        gia = C.num(bv, "đồng", bang["t"], bang.get("b") or "FACT-T2", "lk_hoso.gia.bang ← %s" % (bang.get("n") or "kho.gia_moi"),
                    g="giá bảng chính thức %s; chuỗi vc_lk tới %s (Δ memo/σ theo chuỗi vc_lk)" % (C.fmt_date(C.parse_day(bang["t"])), C.fmt_date(C.parse_day(gia.get("t"))) if gia.get("t") else "[CẦN DATA]"),
                    txt=C.fmt_vn(bv, 0))
    header = {
        "gia": gia, "gia_adj": flow.get("close_adj") or C.num(None, "đồng"), "gia_memo": gia_memo, "delta_pct": delta,
        "ca_factor": ca, "ca_note": ("mốc giá memo × %.4f = cùng cơ sở hôm nay" % ca) if ca and abs(ca - 1) > 1e-4 else ("không có sự kiện vốn từ ngày memo" if ca else "chưa quy CA (thiếu phiên)"),
        "pe": flow.get("pe") or C.num(None, "x"), "pb": flow.get("pb") or C.num(None, "x"), "foreign_pct": flow.get("foreign_pct") or C.num(None, "%"),
        "market_cap": flow.get("market_cap") or C.num(None, "đồng"), "total_shares": flow.get("total_shares") or C.num(None, "cp"),
        "sigma_pe": C.num(C.finite(pe_h.get("sigma")), "σ", C.iso(S["hhp"]["meta"].asof()), S["hhp"]["meta"].effective_tier(), "hhp_vn100_valuation.by_ticker.pe.sigma",
                          txt=(C.fmt_vn(C.finite(pe_h.get("sigma")), 2, True) + "σ") if C.finite(pe_h.get("sigma")) is not None else _NEED),
        "zone_pe": pe_h.get("zone"),
        "edi": {"v": C.finite(e.get("edi")), "stage": e.get("lead_status"), "late": bool(e.get("late_flag")), "t": C.iso(S["edi"]["meta"].asof()), "b": S["edi"]["meta"].effective_tier(),
                "drivers": (e.get("drivers") or [])[:4], "analog": e.get("analog_best"), "txt": C.fmt_vn(C.finite(e.get("edi")), 0) if C.finite(e.get("edi")) is not None else _NEED},
        "tp": cv, "fund_gate": gated["trang_thai"],
        "kg_chip": {"built_at": kg.get("built_at"), "degree": kg.get("degree"), "co": kg.get("co")},
    }
    # thesis + break point
    bp_levels = []
    if M and M.get("break_point"):
        for m in re.finditer(r"(\d{2,3}[.,]\d{1,2})", M["break_point"]):
            lvl = C.finite(m.group(1).replace(",", "."))
            if lvl and 5 <= lvl <= 500:
                bp_levels.append({"memo_lvl": lvl, "adj_lvl": R.rebase_price(lvl, ca) if ca else None, "ca_factor": ca})
    thesis = {"memo_html": md_to_html(_sec(M, "§1") or "", 12000) if M else "", "memo_co": bool(_sec(M, "§1")),
              "break_point": {"text": M.get("break_point") if M else None, "src": M.get("break_point_src") if M else None, "muc_gia": bp_levels},
              "thieu_diem_gay": bool(M) and not M.get("break_point")}
    # §7 conditions
    cond = C.parse_conditions(_sec(M, "§7")) if M else {"dung": [], "gay": [], "lich": []}
    ctx = {"flow": flow, "ca_factor": ca, "sigma_pe": header["sigma_pe"], "edi_stage": e.get("lead_status"), "tp": cv, "gated": gated}
    dk = {"dung": [], "gay": [], "lich": []}
    n_kiem = n_den = n_qua = n_gay = 0
    for kind in ("dung", "gay", "lich"):
        for it in cond[kind]:
            ctx["kind"] = kind
            st = R.cond_status(it.get("due"))
            chk = R.cond_live_check(it, ctx)
            row = dict(it); row.update({"trang_thai": st, "b": "EST"}); row.update(chk)
            dk[kind].append(row)
            n_kiem += 1 if chk["kiem_duoc"] else 0
            n_den += 1 if st in ("đến hạn", "sắp đến hạn") else 0
            n_qua += 1 if st == "quá hạn" else 0
            n_gay += 1 if chk["ket_qua"] == "gãy" else 0
    dk["tom_tat"] = {"n": sum(len(cond[k]) for k in cond), "n_kiem_duoc": n_kiem, "n_den_han": n_den, "n_qua_han": n_qua, "n_gay": n_gay,
                     "memo_co": bool(_sec(M, "§7")), "memo_html": md_to_html(_sec(M, "§7") or "", 8000) if M else ""}
    # tension
    blk = R.memo_signal_block(M) if M else {"present": False}
    sm = C.by_ticker(S["smap"], tk)
    votes = R.street_votes(sm, (S["smap"]["data"] or {}).get("by_broker") if isinstance(S["smap"]["data"], dict) else None)
    bld = R.bld_tone_gate(C.by_ticker(S["mgmt"], tk), votes and votes.get("up"), votes and votes.get("down"))
    tension = {"memo_html": md_to_html(_sec(M, "§2") or "", 20000) if M else "", "memo_co": bool(_sec(M, "§2")), "memo_streams": blk, "live": live,
               "drift": R.tension_drift(blk, live) if blk.get("present") else {"tong": "không đo", "cap": [], "g": "memo không có block 🧭"}, "street_votes": votes, "bld": bld}
    # regen verdict
    reasons = []
    if not M:
        reasons.append("chưa có memo")
    else:
        if memo_age > C.MEMO_REGEN_DAYS:
            reasons.append("memo %d ngày (>%d)" % (memo_age, C.MEMO_REGEN_DAYS))
        if d and _quarter_passed(d):
            reasons.append("đã qua hạn BCTC quý sau ngày memo")
        if not M.get("deep"):
            reasons.append("memo chưa deep (không có §2 TENSION)")
    wsd = ws.get("data") or {}
    pf = C.by_ticker(S["pf"], tk) or {}
    latest_bctc = str((pf.get("latest") or {}).get("BCTC") or "")
    if wsd and latest_bctc and (wsd.get("as_of") or "") < "%s-07-01" % latest_bctc and latest_bctc >= "2026":
        reasons.append("filing BCTC %s mới hơn worksheet %s" % (latest_bctc, wsd.get("as_of")))
    layers_used = [S[k]["meta"].to_json() for k in S] + [U["meta"].to_json(), ws["meta"].to_json(), ev["meta"].to_json(), lk["meta"].to_json()]
    warnings = ["%s %s (%s)" % (l["label"], l["status"], l["age_txt"]) for l in layers_used if l["status"] in ("stale", "missing")]
    cong = (S["fftlk"]["data"] or {}).get("cong") if isinstance(S["fftlk"]["data"], dict) else None
    meta = {"generated": datetime.now(C.ICT).isoformat(timespec="seconds"), "today": C.iso(C.today()), "tk": tk, "ten": entry.get("name") or (M or {}).get("name") or tk,
            "nhom": entry.get("group") or "", "ro": [], "web_url": "http://localhost:9000/baocao/%s.html" % tk,
            "memo": ({"path": p, "date": C.iso(d), "age_days": memo_age, "age_txt": "%d ngày" % memo_age, "status": memo_status, "tier_hieu_luc": memo_tier, "deep": M["deep"], "engine": M["engine"],
                      "confidence": M["confidence"], "regime": M["regime"], "state": M["state"], "state_txt": M["state_label"], "block_date": (blk.get("edi") or blk.get("bld") or {}).get("t") if blk.get("present") else None,
                      "n_words": M["n_words"], "n_tags": M["n_tags"], "n_need": M["n_need"]} if M else None),
            "freshness": layers_used, "warnings": warnings,
            "regen": {"can": bool(reasons), "ly_do": reasons, "lenh": "Workflow gen_remaining_memos.js (const W=['%s']) → monthly_refresh.sh render" % tk}}
    m = C.by_ticker(S["fftlk"], tk) or {}
    dm = m.get("dm") if isinstance(m.get("dm"), dict) else {}
    meta["dm"] = "NAV" if dm.get("nav") is not None else ("WATCH" if dm.get("watch") else ("AVOID" if dm.get("avoid") else ""))
    meta["nav_pct"] = C.finite(dm.get("nav"))
    meta["ro"] = m.get("nhom") if isinstance(m.get("nhom"), list) else ([entry.get("group")] if entry.get("group") else [])
    cd = C.by_ticker(S["edi"], tk) or {}
    codex = {"memo_html": md_to_html(_sec(M, "§3") or "", 16000) if M else "", "memo_co": bool(_sec(M, "§3")), "state": (M or {}).get("state"),
             "edi_live": header["edi"], "edi_memo": blk.get("edi") if blk.get("present") else None,
             "edi_doi": (blk.get("edi") or {}).get("stage") != cd.get("lead_status") if (blk.get("present") and blk.get("edi")) else None,
             "claims_due_90d": cd.get("claims_due_90d") or [], "timeline": (cd.get("timeline") or [])[-8:],
             "board_html": md_to_html(_sec(M, "§5") or "", 12000) if M else "", "board_co": bool(_sec(M, "§5")),
             "engines_note": "Board of Engines grounded (legend_lens) cần evidence tươi — evidence %s → v2; hiện chỉ §5 memo + phiếu độc lập street" % ev["meta"].to_json()["age_txt"]}
    return {
        "meta": meta,
        "cong": {"dong": (cong or {}).get("dong") or "CỔNG: [CẦN DATA] — fft_langkinh.cong thiếu", "dung": bool((cong or {}).get("dung", True)), "muc": (cong or {}).get("muc"),
                 "ly_do_dung": (cong or {}).get("ly_do_dung"), "t": C.iso(S["fftlk"]["meta"].asof()), "n": "fincept_bridge/data/fft_langkinh.json.cong"},
        "header": header, "thesis": thesis, "dieu_kien": dk, "tension": tension,
        "chu_the": build_chu_the(tk, lk, flow, gated, S, kg), "dinh_gia": build_dinh_gia(tk, M, flow, S, cv, ev),
        "filing": {"memo_html": md_to_html(_sec(M, "§4") or "", 16000) if M else "", "memo_co": bool(_sec(M, "§4")), "worksheet": build_worksheet_block(ws),
                   "inventory": {"n_filings": C.finite(pf.get("n_filings")), "by_type": pf.get("by_type"), "latest": pf.get("latest"), "year_span": pf.get("year_span") or pf.get("years"),
                                 "recent_docs": (pf.get("recent_docs") or [])[:8], "b": "FACT-T1 (chỉ mục)", "t": C.iso(S["pf"]["meta"].asof())},
                   "moi_hon_worksheet": any(r.startswith("filing BCTC") for r in reasons)},
        "codex": codex, "kg": kg,
        "ledger": C.ledger_for(S["ledger"], tk),
        "phu_luc": build_phu_luc(tk, M, S, d, cond, (M or {}).get("break_point"), layers_used),
    }


def _quarter_passed(memo_date):
    t = C.today()
    marks = []
    for y in (memo_date.year, memo_date.year + 1):
        for mm, dd in ((1, 30), (4, 30), (7, 30), (10, 31)):
            try:
                marks.append(C.date(y, mm, dd))
            except ValueError:
                pass
    return any(memo_date < m <= t for m in marks)
