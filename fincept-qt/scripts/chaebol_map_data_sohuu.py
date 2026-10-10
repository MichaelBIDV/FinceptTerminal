"""
chaebol_map_data_sohuu — cổ đông, cơ cấu sở hữu, giao dịch nội bộ, quan hệ công ty, sở hữu chéo; chi tiết mã,
quan điểm Vietcap, sự kiện vốn (events-v2), giá mục tiêu sell-side.

Tách từ chaebol_map_data.py (27/09/2026). Tab dùng qua mặt tiền `import chaebol_map_data as D`.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from chaebol_map_data_nen import *  # noqa: F401,F403
from chaebol_map_data_gia import share_basis_note, share_events, shares_out

__all__ = [
    "_RIGHTS_RE", "_qty_now", "top_holders", "leader", "ownership_structure", "_STATUS", "insider_tx",
    "relationships", "cross_holdings", "details", "vietcap_view", "capital_events", "sell_side_targets",
]


# ───────────────────────────── cổ đông ─────────────────────────────

_RIGHTS_RE = re.compile(r"quyền mua", re.I)


def _qty_now(tk: str, q, pub, evs: list, rights: list):
    """(V SL quy về số cp hiện hành, hệ số | None). × hệ số các GDKHQ chia/thưởng/cổ tức CP sau ngày công bố
    (share_events); có quyền mua sau ngày công bố → [CẦN DATA] (SL còn tuỳ cổ đông có thực hiện quyền hay không)."""
    src = f"vc_lk/{tk}/shareholder.quantity"
    if not _finite(q):
        return can_data("quantity trống", src), None
    if not pub:
        return can_data("dòng cổ đông không có ngày công bố — không quy đổi được SL", src), None
    rt = [d for d in rights if d > pub]
    if rt:
        return can_data(f"quyền mua GDKHQ {ddmmyyyy(rt[0])} sau ngày công bố {ddmmyyyy(pub)} — SL hiện hành tuỳ việc "
                        "thực hiện quyền", src, pub, "cp"), None
    ev = [e for e in evs if e["date"] > pub]
    if not ev:
        return V(q, js_locale(q, 0), T2, pub, src, "không có GDKHQ chia/thưởng cp sau ngày công bố", "cp"), 1.0
    f = 1.0
    for e in ev:
        f *= e["factor"]
    return V(q * f, js_locale(q * f, 0), EST, pub, src + " × share_events",
             f"SL {js_locale(q, 0)} ngày {ddmmyyyy(pub)} × {js_fixed(f, 4)}; {share_basis_note(ev)}", "cp"), f


def top_holders(tk: str, n: int | None = None, sort: str = "qty") -> V:
    """Cổ đông lớn vc_lk: khử trùng theo ownerCode (giữ publicDate mới nhất), % vendor tại publicDate
    (pct_pub, FACT-T2); qty_now = SL quy về số cp hiện hành qua GDKHQ chia/thưởng/cổ tức CP sau ngày công bố
    (share_events; E khi có quy đổi; có quyền mua sau ngày công bố → [CẦN DATA]) + factor; pct_now = qty_now ÷
    totalShares hiện hành (EST); cờ old (>12T), stale (>18T). sort="qty" (mặc định, như cũ: SL vendor thô) |
    "qty_now" (SL quy đổi; thiếu → SL thô). % giữa các dòng KHÁC kỳ không cộng được."""
    if sort not in ("qty", "qty_now"):
        raise ValueError(f"top_holders: sort phải là 'qty' hoặc 'qty_now', nhận {sort!r}")
    meta, rows = vc(tk, "shareholder")
    if not isinstance(rows, list):
        return can_data(f"không có vc_lk/{tk}/shareholder")
    evs = share_events(tk)
    ce = capital_events(tk)
    rights = sorted({e["exright"] for e in (ce.value or []) if e.get("code") == "ISS" and e.get("exright")
                     and _RIGHTS_RE.search(str(e.get("title") or ""))})
    best: dict = {}
    for r in rows:
        k = r.get("ownerCode") or re.sub(r"\s+", " ", str(r.get("ownerName", "")).lower())
        key = (str(r.get("publicDate") or ""), str(r.get("updateDate") or ""))
        if k not in best or key > best[k][0]:
            best[k] = (key, r)
    dup = len(rows) - len(best)
    sh = shares_out(tk)
    out = []
    for _, r in best.values():
        pub, q = iso(r.get("publicDate")), r.get("quantity")
        age = _months_ago(pub)
        pct_pub = r.get("percentage")
        item = {"name": r.get("ownerName"), "name_en": r.get("ownerNameEn"), "code": r.get("ownerCode"),
                "type": r.get("ownerType"), "position": r.get("positionName"), "public_date": pub,
                "update_date": iso(r.get("updateDate")), "old": age is not None and age > OLD_MONTHS,
                "stale": age is not None and age > STALE_MONTHS,
                "qty": V(q, js_locale(q, 0), T2, pub, f"vc_lk/{tk}/shareholder.quantity", None, "cp") if _finite(q) else can_data("quantity trống"),
                "pct_pub": V(pct_pub * 100, js_fixed(pct_pub * 100, 2) + "%", T2, pub, f"vc_lk/{tk}/shareholder.percentage",
                             "tính trên số cp tại publicDate", "%") if _finite(pct_pub) else can_data("percentage trống")}
        item["qty_now"], item["factor"] = _qty_now(tk, q, pub, evs, rights)
        qn = item["qty_now"]
        if not qn.can and not sh.can:
            x = qn.value / sh.value * 100
            conv = f"; SL quy đổi ×{js_fixed(item['factor'], 4)}" if item["factor"] != 1.0 else ""
            item["pct_now"] = V(x, js_fixed(x, 2) + "%", EST, sh.asof, f"{'qty_now' if conv else 'quantity'} ÷ {sh.src}",
                                f"mẫu số {js_locale(sh.value, 0)} cp ({ddmmyyyy(sh.asof)}){conv}", "%")
        else:
            item["pct_now"] = can_data(qn.note if qn.can else "thiếu số cp hiện hành")
        out.append(item)
    out.sort(key=lambda it: -((it["qty"].value or 0) if sort == "qty" or it["qty_now"].can else it["qty_now"].value))
    note = (f"{len(out)} chủ sở hữu (khử {dup} dòng trùng); lấy {ddmmyyyy((meta or {}).get('lay_luc'))}; "
            f"dòng cũ >{OLD_MONTHS}T: {sum(1 for x in out if x['old'])}")
    return V(out[:n] if n else out, None, T2, (meta or {}).get("du_lieu_toi"), f"vc_lk/{tk}/shareholder", note)


def leader(tk: str) -> V:
    """Chủ tịch HĐQT theo positionName của sổ cổ đông vendor (có thể trễ so nghị quyết)."""
    _, rows = vc(tk, "shareholder")
    for r in rows or []:
        p = str(r.get("positionName") or "")
        if re.search(r"(?<!Phó )Chủ tịch (Hội đồng Quản trị|HĐQT)", p, re.I):
            return V(r.get("ownerName"), r.get("ownerName"), T2, iso(r.get("updateDate")), f"vc_lk/{tk}/shareholder.positionName",
                     f"{p} — chức danh theo sổ cổ đông vendor, có thể trễ; ưu tiên CBTT (FACT-T1) khi mâu thuẫn")
    return can_data(f"{tk}: sổ cổ đông vendor không có dòng Chủ tịch HĐQT", f"vc_lk/{tk}/shareholder")


def ownership_structure(tk: str) -> dict:
    """Cơ cấu sở hữu (%) — ảnh chụp không ngày của vc_lk shareholder-structure."""
    meta, s = vc(tk, "shareholder-structure")
    if not isinstance(s, dict):
        return {"state": can_data(f"không có vc_lk/{tk}/shareholder-structure")}
    t = iso((meta or {}).get("t_lay") or (meta or {}).get("lay_luc"))
    note = f"ảnh chụp Vietcap (không có ngày dữ liệu), lấy {ddmmyyyy(t)}"
    out = {k: (V(s[f] * 100, js_fixed(s[f] * 100, 2) + "%", T2, t, f"vc_lk/{tk}/shareholder-structure.{f}", note, "%")
               if _finite(s.get(f)) else can_data(f"{f} trống"))
           for k, f in (("state", "statePercentage"), ("foreign", "foreignPercentage"), ("other", "otherPercentage"),
                        ("bod", "bodPercentage"), ("institution", "institutionPercentage"))}
    ts = s.get("totalShares")
    out["total_shares"] = V(ts, js_locale(ts, 0), T2, t, f"vc_lk/{tk}/shareholder-structure.totalShares", note, "cp") \
        if _finite(ts) else can_data("totalShares trống")
    return out


_STATUS = {"Đã thực hiện xong": "da_xong", "Đăng ký": "dang_ky", "Đăng kí": "dang_ky", "Không thực hiện được": "khong_thuc_hien"}


def insider_tx(tk: str, since=None, n: int | None = None) -> V:
    """Giao dịch nội bộ/NLQ (vc_lk insider-transaction): KL đăng ký + KL thực hiện (có dấu); KHÔNG có giá."""
    meta, rows = vc(tk, "insider-transaction")
    if not isinstance(rows, list):
        return can_data(f"không có vc_lk/{tk}/insider-transaction")
    out = []
    for r in rows:
        pub = iso(r.get("publicDate"))
        if since and (pub or "") < iso(since):
            continue
        own = r.get("ownershipAfterTrade")
        out.append({"public_date": pub, "start": iso(r.get("startDate")), "end": iso(r.get("endDate")),
                    "code": r.get("eventCode"), "action": r.get("actionTypeCode"), "action_vi": r.get("actionTypeVi"),
                    "status": _STATUS.get(r.get("tradeStatusVi"), r.get("tradeStatusVi")), "status_vi": r.get("tradeStatusVi"),
                    "trader": r.get("traderOrganNameVi") or r.get("traderNameVi"), "position": r.get("traderPositionVi"),
                    "related": r.get("relativeNameVi"), "title": r.get("eventTitleVi"), "url": r.get("sourceUrlVi"),
                    "register": r.get("shareRegister"), "acquire": r.get("shareAcquire"),
                    "before": r.get("shareBeforeTrade"), "after": r.get("shareAfterTrade"),
                    "own_after_pct": round(own * 100, 6) if _finite(own) else None})
    out.sort(key=lambda x: x["public_date"] or "", reverse=True)
    return V(out[:n] if n else out, None, T2, (meta or {}).get("du_lieu_toi"), f"vc_lk/{tk}/insider-transaction",
             "KL đăng ký/thực hiện, không có giá; 'dang_ky' chưa phải kết quả")


def relationships(tk: str) -> dict:
    """Công ty con/liên kết (vc_lk relationship). Giá trị FACT-T2 nhưng THỜI ĐIỂM UNVERIFIED (vendor không ghi ngày)."""
    meta, r = vc(tk, "relationship")
    if not isinstance(r, dict):
        return {"subsidiaries": [], "affiliates": [], "note": f"không có vc_lk/{tk}/relationship"}
    t = iso((meta or {}).get("t_lay") or (meta or {}).get("lay_luc"))
    note = f"theo Vietcap, lấy {ddmmyyyy(t)} — thời điểm UNVERIFIED (không có ngày)"

    def item(x):
        p = x.get("ownedPercentage")
        return {"name": x.get("rightOrganNameVi"), "code": x.get("rightOrganCode"), "ticker": x.get("rightTicker") or None,
                "pct": V(p * 100, js_fixed(p * 100, 2) + "%", T2, None, f"vc_lk/{tk}/relationship", note, "%")
                if _finite(p) else can_data("ownedPercentage trống")}
    return {"subsidiaries": [item(x) for x in r.get("subsidiaries") or []],
            "affiliates": [item(x) for x in r.get("affiliates") or []], "t_lay": t, "note": note}


def cross_holdings(min_pct: float = 1.0, since="2025-06-30", min_tickers: int = 2, tickers=None) -> dict:
    """Chủ sở hữu nắm ≥min_pct% ở ≥min_tickers mã (publicDate ≥ since; holdings sắp theo % giảm dần) + cạnh
    mã→mã từ relationship (mỗi mã nguồn sắp theo %; bỏ cạnh 0,00% và cạnh trùng subsidiaries/affiliates — giữ %
    lớn hơn). (data_d3: 64 chủ sở hữu ở mức 1% / 30/06/2025.)"""
    base = vc_dir()
    names = tickers or (sorted(p.name for p in base.iterdir() if (p / "shareholder.json").exists())
                        if base.exists() else [])
    owners: dict = {}
    edges, n_zero, n_dup = [], 0, 0
    for tk in names:
        _, rows = vc(tk, "shareholder")
        seen: dict = {}
        for r in rows or []:
            p, pub = r.get("percentage"), iso(r.get("publicDate"))
            if not _finite(p) or p * 100 < min_pct or (pub or "") < iso(since):
                continue
            k = r.get("ownerCode") or r.get("ownerName")
            if k not in seen or (pub or "") > seen[k]["public_date"]:
                seen[k] = {"tk": tk, "public_date": pub, "name": r.get("ownerName"), "type": r.get("ownerType"),
                           "pct": V(p * 100, js_fixed(p * 100, 2) + "%", T2, pub, f"vc_lk/{tk}/shareholder", None, "%")}
        for k, h in seen.items():
            o = owners.setdefault(k, {"code": k, "name": h["name"], "type": h["type"], "holdings": []})
            o["holdings"].append({x: h[x] for x in ("tk", "pct", "public_date")})
        best: dict = {}
        for grp in ("subsidiaries", "affiliates"):
            for x in relationships(tk)[grp]:
                p = x["pct"]
                if not x["ticker"]:
                    continue
                if p.can or p.value < 0.005:            # hiện "0.00%": không phải cạnh sở hữu
                    n_zero += 1
                elif x["ticker"] in best:               # cùng mã ở cả subsidiaries lẫn affiliates
                    n_dup += 1
                    if p.value > best[x["ticker"]]["pct"].value:
                        best[x["ticker"]] = {"from": tk, "to": x["ticker"], "kind": grp, "pct": p}
                else:
                    best[x["ticker"]] = {"from": tk, "to": x["ticker"], "kind": grp, "pct": p}
        edges += sorted(best.values(), key=lambda e: -e["pct"].value)
    multi = [o for o in owners.values() if len({h["tk"] for h in o["holdings"]}) >= min_tickers]
    for o in multi:
        o["holdings"].sort(key=lambda h: -h["pct"].value)
    multi.sort(key=lambda o: (-len(o["holdings"]), str(o["name"])))
    return {"owners": multi, "ticker_edges": edges, "n_tickers": len(names),
            "note": f"ngưỡng ≥{min_pct}% · publicDate ≥ {ddmmyyyy(since)} · ≥{min_tickers} mã; cạnh mã→mã thời điểm "
                    f"UNVERIFIED, sắp theo %; bỏ {n_zero} cạnh 0,00% và {n_dup} cạnh trùng (subsidiaries/affiliates); "
                    "holdings mỗi chủ sở hữu sắp theo %"}


# ───────────────────────────── chi tiết mã, sự kiện, sell-side ─────────────────────────────

def details(tk: str) -> dict:
    meta, d = vc(tk, "details")
    if not isinstance(d, dict):
        return {"name": can_data(f"không có vc_lk/{tk}/details")}
    t = iso((meta or {}).get("t_lay") or (meta or {}).get("lay_luc"))
    src = f"vc_lk/{tk}/details"

    def pct(f):
        x = d.get(f)
        return V(x * 100, js_fixed(x * 100, 2) + "%", T2, t, f"{src}.{f}", "ảnh chụp", "%") if _finite(x) else can_data(f"{f} trống")
    return {"name": V(d.get("viOrganName"), d.get("viOrganName"), T2, t, f"{src}.viOrganName"),
            "short": d.get("viOrganShortName"), "sector": d.get("sectorVn"), "listing_date": iso(d.get("listingDate")),
            "free_float": pct("freeFloatPercentage"), "foreign": pct("foreignerPercentage"),
            "foreign_max": pct("maximumForeignPercentage"), "state": pct("statePercentage"),
            "issue_share": V(d.get("issueShare"), js_locale(d.get("issueShare"), 0), T2, t, f"{src}.issueShare", None, "cp")
            if _finite(d.get("issueShare")) else can_data("issueShare trống")}


def vietcap_view(tk: str) -> dict:
    """Rating/giá mục tiêu CỦA VIETCAP (SS-T3) — quan điểm vendor, không phải khuyến nghị của trang."""
    meta, d = vc(tk, "details")
    if not isinstance(d, dict) or not d.get("rating"):
        return {"rating": can_data(f"{tk}: Vietcap không coverage")}
    ra = d.get("ratingAsOf")
    try:
        ra_iso = datetime.strptime(ra, "%d-%b-%y").date().isoformat()
    except (TypeError, ValueError):
        ra_iso = None
    note = f"quan điểm Vietcap (analyst {d.get('analyst')}), ngày {ra}; không phải khuyến nghị của trang"
    tp, up = d.get("targetPrice"), d.get("upsideToTargetPercent")
    return {"rating": V(d["rating"], d["rating"], T3, ra_iso, f"vc_lk/{tk}/details.rating", note),
            "target": V(tp, js_locale(tp, 0), T3, ra_iso, f"vc_lk/{tk}/details.targetPrice", note, "đ") if _finite(tp) else can_data("không có TP"),
            "upside": V(up * 100, pct_text(up * 100, 1), T3, iso((meta or {}).get("t_lay")), f"vc_lk/{tk}/details.upsideToTargetPercent", note, "%")
            if _finite(up) else can_data("không có upside"),
            "stale": bool(ra_iso and (today() - date.fromisoformat(ra_iso)).days > 90)}


def capital_events(tk: str, since=None, by: str = "exright") -> V:
    """events-v2 (ISS phát hành · AIS niêm yết thêm · DIV cổ tức tiền); ratio giải mã theo doi_chieu.
    `since` lọc theo NGÀY HIỆU LỰC (by="exright", mặc định từ 27/09): GDKHQ; mục chưa/không có GDKHQ (AIS, cổ tức
    chưa chốt) → ngày niêm yết → ngày phát hành → ngày công bố; mỗi mục có `effective` = ngày đó. by="public" = lọc
    theo publicDate (hành vi cũ: rơi sự kiện công bố trước mốc mà GDKHQ sau mốc, vd HPG 11/05, LPB 14/05).
    ratio = None (ratio_text None với ISS) khi vendor ghi 0 — riêng lẻ, CBCNV, chuyển đổi… không có tỷ lệ chia."""
    if by not in ("exright", "public"):
        raise ValueError(f"capital_events: by phải là 'exright' hoặc 'public', nhận {by!r}")
    meta, rows = vc(tk, "events-v2")
    if not isinstance(rows, list):
        return can_data(f"không có vc_lk/{tk}/events-v2")
    out = []
    for r in rows:
        pub, ex = iso(r.get("publicDate")), iso(r.get("exrightDate"))
        eff = ex or iso(r.get("listingDate")) or iso(r.get("issueDate")) or pub
        if since and ((pub if by == "public" else eff) or "") < iso(since):
            continue
        code, er = r.get("eventCode"), r.get("exerciseRatio")
        er = er if _finite(er) and er != 0 else None
        dec = (f"{js_locale(r.get('valuePerShare'), 0)} đ/cp" if code == "DIV" and _finite(r.get("valuePerShare"))
               else f"{js_fixed(er * 100, 2)} cp/100 cp" if code == "ISS" and er is not None else None)
        out.append({"code": code, "title": r.get("eventTitleVi"), "public_date": pub, "exright": ex,
                    "record": iso(r.get("recordDate")), "payout": iso(r.get("payoutDate")), "listing": iso(r.get("listingDate")),
                    "issue": iso(r.get("issueDate")), "effective": eff, "ratio": er, "ratio_text": dec})
    out.sort(key=lambda x: x["public_date"] or "", reverse=True)
    return V(out, None, T2, (meta or {}).get("du_lieu_toi"), f"vc_lk/{tk}/events-v2", "không có ĐHCĐ/KQKD/nhân sự")


def sell_side_targets(tk: str) -> V:
    """Giá mục tiêu 3 nguồn gộp sẵn (knowledge_os/hhp_forecast_tickers/<MÃ>.json): mỗi mục mang tier riêng."""
    d = read_json(sys_dir() / "knowledge_os" / "hhp_forecast_tickers" / f"{tk}.json", quiet=True)
    if not isinstance(d, dict) or not d.get("targets"):
        return can_data(f"{tk}: không có trong hhp_forecast_tickers")
    rows = [V(t.get("value_vnd"), js_locale(t.get("value_vnd"), 0), t.get("tier"), iso(t.get("date")),
              t.get("file") or t.get("url") or f"knowledge_os/hhp_forecast_tickers/{tk}.json#{t.get('id')}",
              f"{t.get('org')} {t.get('rating') or ''} {('n=' + str(t['n_analysts'])) if t.get('n_analysts') else ''}".strip(), "đ")
            for t in d["targets"]]
    return V(rows, None, None, (d.get("meta") or {}).get("generated"), f"knowledge_os/hhp_forecast_tickers/{tk}.json",
             "mỗi TP một tier; n=1 thì không gọi là đồng thuận")
