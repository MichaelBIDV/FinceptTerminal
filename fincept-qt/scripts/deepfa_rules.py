#!/usr/bin/env python3
"""
Fincept Terminal — DEEP FA derived rules (pure functions over the loaders of deepfa_core.py).

Nothing here fetches or writes the vault (the KG index cache is the one exception, and it lives in
fincept_bridge/state/deepfa/ like the flow cache). Every derived number is EST and says so; every
input number keeps its own {t, b, n}. Rules (agreed by the three design lenses, 23/09/2026):

  R1  ca_factor_since       — corporate-action factor between memo date and today so memo price levels
                              ("thủng 72,1", "giá memo") are compared on the SAME basis (FPT: raw −9,5 %
                              vs adjusted −0,5 % after the 10 % bonus issue of 21/09/2026).
  R2  memo_signal_block     — the 🧭 block spliced into the memo carries its OWN json dates; parse it so
                              the memo-time vote streams can sit next to today's (tension drift).
  R3  tension_drift         — per stream: khép / mở / đổi chiều / giữ / không đo — never "đã lọc".
  R4  cond_status           — §7 checklist: chưa · sắp đến hạn (≤7d) · đến hạn · quá hạn (>7d) · không hạn.
  R5  cond_live_check       — whitelist of condition kinds the disk can verify (price level, foreign
                              streak, σ band, EDI stage, TP consensus, fund flip). Anything else → "[CẦN DATA]"
                              with the reason — the memo text is shown verbatim, never reinterpreted.
  R6  street_votes          — N brokers → K independent votes by terminal fingerprint (EST, logic shown);
                              ▲/▼ direction is regex-mined, labelled so; ▼ minority = read variant first.
  R7  bld_tone_gate         — tone.net is EST (keyword count); cap saturation (16/16) or NQ contamination
                              → direction None; alignment shown only when street_up+down ≥ 3.
  R8  rigor_6d_proxy        — self-score from tag density / need count / falsifiable presence; proxy, says so.
  R9  kg_neighborhood       — 1-step neighbourhood of ticker_<TK> in knowledge_graph.json grouped by node
                              type, each with its own date and tier; cached per built_at (30 MB file).
"""

import json
import os
import re
from datetime import date, timedelta

import deepfa_core as C

# ── R1 corporate-action basis ────────────────────────────────────────────────


def ca_factor_since(flow, d):
    """factor = (closeAdj/close at today) / (closeAdj/close at memo date) — multiply a memo-date price
    level by this to express it on today's (adjusted) basis. 1.0 when no event; None when unknown."""
    if not flow or not d:
        return None
    hist = C.close_on_or_before_cached(flow, d) if isinstance(flow, dict) else None
    now_c, now_a = C.finite((flow.get("close") or {}).get("v")), C.finite((flow.get("close_adj") or {}).get("v"))
    if not hist or not hist[1] or not hist[2] or not now_c or not now_a:
        return None
    f_then = hist[2] / hist[1]   # adjusted/raw at memo date (0.909 for FPT after the 10 % bonus of 21/09)
    f_now = now_a / now_c        # 1.0 on the latest session by construction
    if f_then <= 0 or f_now <= 0:
        return None
    # memo level (raw basis of its day) × factor = the same level on today's basis: 72,1 × 0,909 = 65,55
    return round(f_then / f_now, 6)


def rebase_price(v, factor):
    f = C.finite(v)
    return round(f * factor, 2) if (f is not None and factor) else None


# ── R2 memo 🧭 block → memo-time streams ─────────────────────────────────────

_EDI_RE = re.compile(r"\*\*(\d{1,3})/100 · ([A-Z_]+)\*\*.*?_\[edi_index·([\d-]+)\]_", re.S)
_MGMT_RE = re.compile(r"BLĐ \*\*([a-z]+)\*\*.*?street ▲(\d+|—)/▼(\d+|—).*?AI-news (\d+|—) tin \*\*([^*]+)\*\*.*?alignment: ([^_\n]+?)\s*_\[mgmt_view·([\d-]+)\]_", re.S)
_SMAP_RE = re.compile(r"catalyst ▲(\d+)/▼(\d+).*?_\[source_map·([\d-]+)\]_", re.S)
_FUND_RE = re.compile(r"(\d+) quỹ nắm ([\d.,]+)% OS · net ([+\-−][\d.,]+)M cp 1M.*?_\[fund_intent·([\d-]+)\]_", re.S)


def memo_signal_block(memo):
    """Parse the '🧭 Lớp tín hiệu hệ thống' block. Returns {"edi", "bld", "street", "ainews", "fund"}; each
    {"gia_tri", "huong", "t"} or None. Dates are the json dates written inside the block, NOT the memo date."""
    txt = ((memo or {}).get("by_key") or {}).get("🧭", {}).get("text") or ""
    out = {"present": bool(txt), "edi": None, "bld": None, "street": None, "ainews": None, "fund": None}
    if not txt:
        return out
    m = _EDI_RE.search(txt)
    if m:
        out["edi"] = {"score": int(m.group(1)), "stage": m.group(2), "t": m.group(3), "late": "LATE" in txt.split("_[edi_index")[0][-200:]}
    m = _MGMT_RE.search(txt)
    if m:
        tone = m.group(1)
        up = int(m.group(2)) if m.group(2).isdigit() else None
        dn = int(m.group(3)) if m.group(3).isdigit() else None
        out["bld"] = {"tone": tone, "huong": {"positive": 1, "bullish": 1, "cautious": -1, "negative": -1, "balanced": 0}.get(tone), "t": m.group(7)}
        out["street"] = {"up": up, "down": dn, "huong": _dir_from_votes(up, dn), "t": m.group(7)}
        n_ai = int(m.group(4)) if m.group(4).isdigit() else None
        net = m.group(5).strip()
        out["ainews"] = {"n": n_ai, "net": net, "huong": {"positive": 1, "negative": -1, "neutral": 0}.get(net.lower()) if net != "—" else None, "t": m.group(7)}
        out["alignment_memo"] = m.group(6).strip()
    m = _SMAP_RE.search(txt)
    if m and not out["street"]:
        up, dn = int(m.group(1)), int(m.group(2))
        out["street"] = {"up": up, "down": dn, "huong": _dir_from_votes(up, dn), "t": m.group(3)}
    m = _FUND_RE.search(txt)
    if m:
        # the block writes English format ("+10.1M", "+1,234.5M") — enrich_vn30_deepfa f"{sh/1e6:+,.1f}M"
        net = C.finite(m.group(3).replace("−", "-").replace(",", ""))
        out["fund"] = {"num_funds": int(m.group(1)), "pct_os": C.finite(m.group(2).replace(",", ".")), "net_1m_M": net,
                       "huong": (1 if (net or 0) > 0 else (-1 if (net or 0) < 0 else 0)) if net is not None else None,
                       "t": m.group(4), "g": "số thô trước GATE LVF (memo tự ghi 'chưa lọc quỹ-mới/ETF')"}
    return out


def _dir_from_votes(up, dn):
    if up is None and dn is None:
        return None
    up, dn = up or 0, dn or 0
    if up + dn < 3:
        return None  # coverage too thin to call a direction (R7 gate reused)
    if up > 2 * dn:
        return 1
    if dn > up:
        return -1
    return 0


# ── R3 tension drift ─────────────────────────────────────────────────────────


def tension_drift(memo_streams, live):
    """Pair memo-time streams (R2) with today's tension_live() streams. For each: pha ∈
    'khép' (lệch pha lúc memo, nay đồng pha) · 'mở' (đồng pha → lệch) · 'đổi chiều' · 'giữ' · 'không đo'.
    The pairing is by stream name; fund is 'không đo' whenever the live gate is blind."""
    live_by = {}
    for s in (live or {}).get("dong") or []:
        key = s["dong"].split(" ")[0].lower()  # 'blđ' 'street' 'ai-news' 'fund' 'dòng'
        live_by[key] = s
    pairs = []
    mapping = [("bld", "blđ", "BLĐ"), ("street", "street", "Street"), ("ainews", "ai-news", "AI-news"), ("fund", "fund", "Fund intent")]
    for mkey, lkey, label in mapping:
        m = (memo_streams or {}).get(mkey)
        l = live_by.get(lkey)
        mh = m.get("huong") if m else None
        lh = l.get("huong") if l else None
        if m is None and l is None:
            pha = "không đo"
        elif mh is None or lh is None:
            pha = "không đo"
        elif mh == lh:
            pha = "giữ"
        elif mh * lh < 0:
            pha = "đổi chiều"
        else:
            pha = "dịch nhẹ"
        pairs.append({"dong": label, "memo": m, "song": {k: l.get(k) for k in ("gia_tri", "huong", "t", "b", "txt")} if l else None, "pha": pha})
    dirs_m = [p["memo"]["huong"] for p in pairs if p["memo"] and p["memo"].get("huong") is not None]
    dirs_l = [p["song"]["huong"] for p in pairs if p["song"] and p["song"].get("huong") is not None]
    def lech(ds):
        return (any(d > 0 for d in ds) and any(d < 0 for d in ds)) if len(ds) >= 2 else None
    lm, ll = lech(dirs_m), lech(dirs_l)
    if lm is None or ll is None:
        overall = "không đo"
    elif lm and not ll:
        overall = "khép"
    elif not lm and ll:
        overall = "mở"
    elif lm and ll:
        overall = "vẫn lệch pha"
    else:
        overall = "vẫn đồng pha"
    return {"cap": pairs, "tong": overall, "n_memo": len(dirs_m), "n_song": len(dirs_l),
            "g": "so sánh định nghĩa gần nhau nhưng không đồng nhất (memo: ▲/▼ toàn corpus tại ngày memo; sống: catalyst_consensus hôm nay) — đọc cả số thô"}


# ── R4/R5 §7 conditions ──────────────────────────────────────────────────────

DUE_TOL_DAYS = 7


def cond_status(due_iso, today=None):
    t = today or C.today()
    d = C.parse_day(due_iso) if due_iso else None
    if not d:
        return "không hạn"
    if d < t - timedelta(days=DUE_TOL_DAYS):
        return "quá hạn"
    if d <= t:
        return "đến hạn"
    if d <= t + timedelta(days=DUE_TOL_DAYS):
        return "sắp đến hạn"
    return "chưa"


_PRICE_LEVEL_RE = re.compile(r"(?:thủng|dưới|mất|xuống dưới|giữ trên|vượt|trên|breakout)\s*(?:mốc|vùng|hỗ trợ|kháng cự)?\s*([\d]{2,3}(?:[.,]\d{1,3})?)\b", re.I)
_FOREIGN_STREAK_RE = re.compile(r"(NĐTNN|khối ngoại|foreign)[^.]*?(net sell|bán ròng|mua ròng|net buy)[^.]*?(\d+)\s*(tuần|phiên)", re.I)
_SIGMA_RE = re.compile(r"([+\-−]?\d(?:[.,]\d)?)\s*σ")
_EDI_STAGE_RE = re.compile(r"(MANDATE_ONLY|INTENT_FORMING|STRUCTURE_CONFIRMING|FA_TA_CONFIRMED|vehicle_creation|structure)", re.I)
_TP_RE = re.compile(r"(TP|giá mục tiêu)[^.]*?(cắt|hạ|nâng|đổi)", re.I)
_FUND_FLIP_RE = re.compile(r"(quỹ|fund|active)[^.]*?(flip|đảo|net.?buy|mua ròng)[^.]*?(\d)\s*tháng", re.I)


def cond_live_check(item, ctx):
    """One §7 item → {"loai", "kiem_duoc", "ket_qua": "đạt"|"gãy"|"chưa rõ"|None, "so_song", "ly_do"}.
    ctx = {"flow", "ca_factor", "sigma_pe", "edi_stage", "tp", "gated", "kind": "dung"|"gay"|"lich"}."""
    text = item.get("text") or ""
    low = text.lower()
    flow = ctx.get("flow") or {}
    out = {"loai": None, "kiem_duoc": False, "ket_qua": None, "so_song": None, "ly_do": None}
    m = _PRICE_LEVEL_RE.search(text)
    if m and ("giá" in low or "thủng" in low or "hỗ trợ" in low or "vượt" in low or "gann" in low):
        lvl = C.finite(m.group(1).replace(",", "."))
        px = C.finite((flow.get("close_adj") or {}).get("v"))
        if lvl and px:
            lvl_k = lvl if lvl < 1000 else lvl / 1000.0            # memo writes nghìn đồng
            f = ctx.get("ca_factor") or 1.0
            lvl_adj = lvl_k * f
            px_k = px / 1000.0
            below = px_k < lvl_adj
            hit = below if any(w in low for w in ("thủng", "dưới", "mất", "xuống")) else (px_k > lvl_adj)
            out.update({"loai": "mức giá (điều chỉnh CA)", "kiem_duoc": True,
                        "so_song": "giá %s vs mốc memo %s → %s sau CA ×%.4f" % (C.fmt_vn(px_k, 1), C.fmt_vn(lvl_k, 1), C.fmt_vn(lvl_adj, 1), f),
                        "ket_qua": ("gãy" if ctx.get("kind") == "gay" else "đạt") if hit else "chưa",
                        "ly_do": "closePriceAdjusted vc_lk %s · mốc memo quy về cùng cơ sở" % (flow.get("t") or "")})
            return out
    m = _FOREIGN_STREAK_RE.search(text)
    if m:
        fn = C.finite((flow.get("foreign_net_20") or {}).get("v"))
        if fn is not None:
            sell = "sell" in m.group(2).lower() or "bán" in m.group(2).lower()
            hit = (fn < 0) if sell else (fn > 0)
            out.update({"loai": "dòng ngoại (Σ20 phiên, proxy chuỗi tuần)", "kiem_duoc": True,
                        "so_song": "NN Σ20 phiên %s tỷ" % C.fmt_vn(fn, 0, True),
                        "ket_qua": ("gãy" if ctx.get("kind") == "gay" else "đạt") if hit else "chưa",
                        "ly_do": "proxy: tổng 20 phiên thay cho '%s %s liên tiếp' — chưa đếm chuỗi tuần" % (m.group(3), m.group(4))})
            return out
    m = _SIGMA_RE.search(text)
    if m and ("p/e" in low or "σ" in text):
        sg = C.finite((ctx.get("sigma_pe") or {}).get("v"))
        if sg is not None:
            out.update({"loai": "σ P/E (HHP)", "kiem_duoc": True, "so_song": "σ hiện %s (%s)" % (C.fmt_vn(sg, 2, True), (ctx.get("sigma_pe") or {}).get("t")),
                        "ket_qua": "chưa rõ", "ly_do": "mốc σ trong câu cần người đối chiếu chiều (rẻ/đắt)"})
            return out
    m = _EDI_STAGE_RE.search(text)
    if m and ("edi" in low or "structure" in low or "vehicle" in low or "mandate" in low):
        st = ctx.get("edi_stage")
        out.update({"loai": "EDI stage", "kiem_duoc": st is not None, "so_song": "EDI stage hôm nay: %s" % (st or "[CẦN DATA]"),
                    "ket_qua": None, "ly_do": "so stage sống với stage memo — chuyển stage là dữ kiện, không phải kết luận"})
        return out
    if _TP_RE.search(text):
        tp = ctx.get("tp") or {}
        out.update({"loai": "TP/rating sell-side", "kiem_duoc": bool(tp.get("target_price")),
                    "so_song": ("TP Vietcap %s (%s%s)" % (tp.get("target_price_txt"), tp.get("tp_date"), " ⚠cũ" if tp.get("tp_stale") else "")) if tp.get("target_price") else "[CẦN DATA]",
                    "ket_qua": "chưa rõ", "ly_do": "chỉ có TP Vietcap live; TP SSI/HSC cần catalog mới"})
        return out
    if _FUND_FLIP_RE.search(text) or "fund" in low or "quỹ" in low:
        g = ctx.get("gated") or {}
        if g.get("trang_thai") == "GATE-BLIND":
            out.update({"loai": "fund intent", "kiem_duoc": False, "so_song": "GATE-BLIND", "ket_qua": None, "ly_do": g.get("ly_do")})
        else:
            out.update({"loai": "fund intent", "kiem_duoc": g.get("active_cp") is not None, "so_song": g.get("nhan_sau_gate"), "ket_qua": "chưa rõ", "ly_do": "1 kỳ, chưa đủ '2 tháng liên tiếp'"})
        return out
    if any(k in low for k in ("lntt", "lnst", "doanh thu", "biên", "margin", "yoy", "casa", "nim", "npl", "npatmi", "kq q", "kqkd", "run-rate", "kế hoạch")):
        out.update({"loai": "KQKD quý/năm", "kiem_duoc": False, "so_song": "[CẦN DATA]",
                    "ly_do": "chưa có BCTC quý dạng cấu trúc trên đĩa (bctc_structurer chết; vietcap_fundamentals chỉ theo năm)"})
        return out
    out["ly_do"] = "loại điều kiện ngoài whitelist — đọc nguyên văn"
    return out


# ── R6 street independent votes ──────────────────────────────────────────────


def street_votes(smap_ticker, smap_by_broker):
    """N brokers → K clusters by dominant terminal (fingerprint share ≥ 50 %). EST with the logic in `g`."""
    if not isinstance(smap_ticker, dict):
        return None
    brokers = set()
    for s in smap_ticker.get("sources") or []:
        for b in s.get("brokers") or []:
            brokers.add(b)
    cc = smap_ticker.get("catalyst_consensus") or {}
    for side in ("up", "down"):
        for b in (cc.get(side) or {}).get("brokers") or []:
            brokers.add(b)
    clusters, unknown = {}, []
    for b in sorted(brokers):
        fp = ((smap_by_broker or {}).get(b) or {}).get("fingerprint") or []
        term = None
        for f in fp:
            if f.get("category") == "terminal" and C.finite(f.get("share_pct")) is not None and f["share_pct"] >= 50:
                term = f.get("name") or f.get("source")
                break
        if term:
            clusters.setdefault(term, []).append(b)
        else:
            unknown.append(b)
    n_ind = len(clusters) + len(unknown)
    up, dn = C.finite((cc.get("up") or {}).get("n")), C.finite((cc.get("down") or {}).get("n"))
    return {"n_brokers": len(brokers), "n_independent": n_ind, "clusters": [{"terminal": k, "brokers": v} for k, v in clusters.items()],
            "unknown": unknown, "up": up, "down": dn, "direction": "regex UP_KW/DOWN_KW (source_miner) — không phải khuyến nghị",
            "minority_first": bool(up and dn and up >= 3 * dn), "b": "EST",
            "g": "broker cùng terminal chủ đạo (≥50 % báo cáo trích Bloomberg/FactSet/FiinPro) gộp làm 1 phiếu; khác terminal/không rõ = 1 phiếu"}


# ── R7 BLĐ tone gate ─────────────────────────────────────────────────────────


def bld_tone_gate(mg, street_up=None, street_down=None):
    tone = (mg or {}).get("tone") or {}
    net = tone.get("net")
    n_t, n_h = C.finite(tone.get("n_tail")), C.finite(tone.get("n_head"))
    cap = (n_t == 16 and n_h == 16)
    latest = C.finite((mg or {}).get("latest_year"))
    age_y = (C.today().year - int(latest)) if latest else None
    huong = {"positive": 1, "bullish": 1, "cautious": -1, "negative": -1, "balanced": 0}.get(str(net).lower()) if net else None
    notes = []
    if cap:
        huong, notes = None, notes + ["cap bão hòa 16/16 (2 BCTN × 8+8) — không đọc hướng"]
    if age_y is not None and age_y >= 2:
        notes.append("BCTN mới nhất %s — %d năm" % (int(latest), age_y))
    votes = (street_up or 0) + (street_down or 0)
    align = (mg or {}).get("vs_street", {}).get("alignment")
    if votes < 3:
        align_shown = None
        notes.append("alignment ẩn: street chỉ %d phiếu (<3)" % votes)
    else:
        align_shown = align
    return {"tone": net, "n_tail": n_t, "n_head": n_h, "huong": huong, "cap": cap, "latest_year": latest, "age_y": age_y,
            "alignment": align_shown, "b": "EST", "g": "; ".join(notes) if notes else "tone = đếm keyword thuận/khó trong BCTN (EST); giá trị ở LỆCH PHA, không ở tone tuyệt đối"}


# ── R8 rigor 6D proxy ────────────────────────────────────────────────────────


def rigor_6d_proxy(memo, cond, break_point):
    """Six 1–5 marks from what the text exposes. A PROXY, not the skill's manual grading — says so."""
    if not memo or "error" in memo:
        return None
    words = max(1, memo.get("n_words") or 1)
    tags = memo.get("n_tags") or 0
    need = memo.get("n_need") or 0
    per_k = tags / (words / 1000.0)
    def scale(v, lo, hi):
        if v <= lo:
            return 1
        if v >= hi:
            return 5
        return 1 + int(round(4 * (v - lo) / (hi - lo)))
    src_q = scale(per_k, 3, 20)
    ev_d = scale(per_k, 3, 20)
    fals = 5 if (cond and (cond.get("gay") and cond.get("dung"))) else (3 if (cond and (cond.get("gay") or cond.get("dung"))) else 1)
    counter = 4 if memo.get("deep") else 2
    calib = max(1, 5 - min(4, need // 4))
    logic = 4 if break_point else 2
    marks = {"source_quality": src_q, "logic_validity": logic, "evidence_density": ev_d, "falsifiability": fals, "counter_evidence": counter, "calibration": calib}
    low = [k for k, v in marks.items() if v <= 2]
    return {"marks": marks, "avg": round(sum(marks.values()) / 6.0, 1), "low": low,
            "g": "proxy tự động từ mật độ tag [%d tag/%d từ], %d [CẦN…], có/không điểm gãy và §7 — không thay cho chấm tay" % (tags, words, need)}


# ── R9 knowledge-graph neighbourhood (cached per built_at) ───────────────────

KG_PATH_REL = ("knowledge_graph", "knowledge_graph.json")
KG_TYPE_TIER = {
    "consensus": "SS-T3", "fa_fact": "SS-T3", "catalyst": "SS-T3", "broker_report": "SS-T3", "pdf_doc": "SS-T3", "data_source": "SS-T3",
    "fund": "FACT-T2", "mgmt_view": "EST", "primary_filing": "FACT-T1", "variant_perception_signal": "UNVERIFIED",   # tone = keyword count; crowd F247 = 1 nguồn + LLM
    "insider_transaction": "SS-T3", "risk_factor": "EST", "thesis": "EST", "policy": "EST", "macro_factor": "EST",
    "technical_state": "EST", "analytical_framework": "EST", "subsidiary": "FACT-T2", "chaebol": "EST", "person": "FACT-T2",
    "sector": "SS-T3", "flow_aggregate": "SS-T3",
}
KG_TYPE_LABEL = {
    "consensus": "Đồng thuận sell-side", "fa_fact": "Fact HSC/broker", "catalyst": "Catalyst", "broker_report": "Báo cáo HSC (fisc)",
    "pdf_doc": "Tài liệu PDF đã mine", "data_source": "Nguồn dữ liệu broker dựa vào", "fund": "Quỹ nắm giữ", "mgmt_view": "BLĐ (BCTN)",
    "primary_filing": "Filing gốc", "variant_perception_signal": "Đám đông ⚔ consensus", "insider_transaction": "GD nội bộ",
    "risk_factor": "Rủi ro (khung)", "thesis": "Thesis (khung)", "policy": "Chính sách", "macro_factor": "Vĩ mô", "technical_state": "Trạng thái kỹ thuật",
    "analytical_framework": "Khung phân tích", "subsidiary": "Công ty con/liên kết", "chaebol": "Hệ sinh thái", "person": "Người",
    "sector": "Ngành", "flow_aggregate": "Dòng tiền tổng hợp",
}


def kg_index_path():
    return C.sysdir("fincept_bridge", "state", "deepfa", "kg_index.json")


def _kg_built_at():
    p = C.sysdir(*KG_PATH_REL)
    try:
        with open(p, "r", encoding="utf-8") as fh:
            head = fh.read(4000)
        m = re.search(r'"built_at"\s*:\s*"([^"]+)"', head)
        return m.group(1) if m else None, p
    except OSError:
        return None, p


def kg_index(rebuild=False):
    """{built_at, version, n_nodes, n_edges, by_ticker{TK: {degree, groups{type: [items]}}}} — built once per
    KG build (the graph is ~30 MB); items keep id/label/date/props subset only."""
    built, path = _kg_built_at()
    if not os.path.isfile(path):
        return {"error": "knowledge_graph.json thiếu (%s)" % path, "by_ticker": {}}
    cache, _ = C.load_json(kg_index_path())
    if not rebuild and isinstance(cache, dict) and cache.get("built_at") == built and cache.get("by_ticker"):
        return cache
    g, err = C.load_json(path)
    if not isinstance(g, dict):
        return {"error": err or "KG không đọc được", "by_ticker": {}}
    nodes = {n.get("id"): n for n in g.get("nodes") or [] if isinstance(n, dict)}
    by = {}
    for e in g.get("edges") or []:
        s, t = e.get("source") or e.get("from"), e.get("target") or e.get("to")
        for me, other in ((s, t), (t, s)):
            if isinstance(me, str) and me.startswith("ticker_"):
                tk = me[len("ticker_"):]
                on = nodes.get(other) or {}
                typ = on.get("type") or "?"
                if typ == "ticker":
                    continue
                props = on.get("properties") or {}
                item = {"id": other, "label": (on.get("label") or on.get("name") or other)[:140], "rel": e.get("relation") or e.get("type"),
                        "date": _first_date(props, e.get("properties") or {}),
                        "x": {k: props.get(k) for k in ("rec", "tp", "upside_pct", "bull", "bear", "bull_bear_ratio", "divergence_type", "divergence_strength",
                                                        "signal_score", "mentions", "fund_type", "issuer", "is_foreign", "severity", "timeline", "domain",
                                                        "broker", "report_type", "fact_type", "tone_net", "alignment", "by_type", "year_span", "md_path",
                                                        "target_price", "recommendation", "description", "conviction", "timeframe", "mechanism") if props.get(k) not in (None, "")}}
                ep = e.get("properties") or {}
                for k in ("month", "value_bn", "weight", "direction", "mechanism", "rec", "tp"):
                    if ep.get(k) not in (None, ""):
                        item["x"].setdefault("edge_" + k, ep.get(k))
                d = by.setdefault(tk, {"degree": 0, "groups": {}})
                d["degree"] += 1
                d["groups"].setdefault(typ, []).append(item)
    # trim pdf_doc duplicates (same label) and cap lists
    for tk, d in by.items():
        for typ, items in d["groups"].items():
            seen, uniq = set(), []
            for it in items:
                key = it["label"].lower()
                if key in seen:
                    continue
                seen.add(key)
                uniq.append(it)
            uniq.sort(key=lambda i: i.get("date") or "", reverse=True)
            d["groups"][typ] = {"n": len(items), "n_unique": len(uniq), "items": uniq[:8]}
        # ticker props subset that other layers do NOT own
        tn = nodes.get("ticker_" + tk) or {}
        tp = tn.get("properties") or {}
        d["props"] = {k: tp.get(k) for k in ("nvv_total_score", "nvv_founder_pt", "nvv_subs_pt", "nvv_smart_pt", "nvv_fa_pt", "nvv_ta_pt", "nvv_insider_pt",
                                              "nqs_nn_net_20d_bn", "nqs_nn_persistence", "nqs_scraped_at", "sm_accum_index", "sm_signal", "sm_month", "portfolio_role") if tp.get(k) not in (None, "")}
    out = {"built_at": built, "version": g.get("version"), "n_nodes": len(nodes), "n_edges": len(g.get("edges") or []), "by_ticker": by}
    try:
        os.makedirs(os.path.dirname(kg_index_path()), exist_ok=True)
        tmp = kg_index_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False)
        os.replace(tmp, kg_index_path())
    except OSError:
        pass
    return out


def _first_date(*dicts):
    for d in dicts:
        for k in ("date", "generated_at", "scanned_at", "as_of", "month", "tpUpdatedTime", "publicDate"):
            v = d.get(k)
            if isinstance(v, str) and v:
                m = re.fullmatch(r"(\d{2})/(\d{4})", v.strip())     # "05/2026" (fund month) → first day
                if m:
                    return "%s-%s-01" % (m.group(2), m.group(1))
                return v[:10]
    return None


def kg_neighborhood(tk, idx=None):
    idx = idx or kg_index()
    d = (idx.get("by_ticker") or {}).get(tk)
    if not d:
        return {"co": False, "built_at": idx.get("built_at"), "ly_do": idx.get("error") or "mã không có nút ticker_%s trong KG" % tk}
    groups = []
    order = ["consensus", "variant_perception_signal", "mgmt_view", "primary_filing", "fa_fact", "catalyst", "data_source", "fund", "insider_transaction",
             "subsidiary", "chaebol", "person", "risk_factor", "thesis", "policy", "macro_factor", "technical_state", "analytical_framework", "broker_report", "pdf_doc"]
    for typ in order + [t for t in d["groups"] if t not in order]:
        gdata = d["groups"].get(typ)
        if not gdata:
            continue
        dates = [i.get("date") for i in gdata["items"] if i.get("date")]
        newest = max(dates) if dates else None
        age = C.age_int(C.parse_day(newest)) if newest else None
        stale = (age is not None and age > C.STALE_DAYS) if typ not in ("primary_filing", "subsidiary", "chaebol", "person", "policy", "risk_factor", "thesis") else False
        b_goc = KG_TYPE_TIER.get(typ, "EST")
        groups.append({"type": typ, "label": KG_TYPE_LABEL.get(typ, typ), "n": gdata["n"], "n_unique": gdata["n_unique"], "items": gdata["items"],
                       "b": "UNVERIFIED" if stale else b_goc, "b_goc": b_goc, "t": newest, "age_days": age, "stale": stale})
    return {"co": True, "built_at": idx.get("built_at"), "version": idx.get("version"), "degree": d["degree"], "groups": groups, "props": d.get("props") or {},
            "viewer_url": "http://localhost:8099/graph_viewer.html", "b": "theo từng nhóm", "n": "knowledge_graph/knowledge_graph.json"}
