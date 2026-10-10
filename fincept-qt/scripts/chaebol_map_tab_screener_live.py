#!/usr/bin/env python3
"""
chaebol_map_tab_screener_live — lớp live của tab 07 · VN30 SCREENER (tách khỏi chaebol_map_tab_screener.py 27/09 để
mỗi tệp ≤ 800 dòng, api_python §9.7). Chỉ chạy ở mode live; mode v21 không gọi hàm nào ở đây.

- Số sống mỗi mã (chaebol_map_data): giá thô, Δ60D trên giá điều chỉnh quyền, NN khớp+TT, TD khớp — cửa sổ 60 phiên.
- Ô TD ghi ngày bản ghi tự doanh cuối trong cửa sổ + số phiên có bản ghi khi cửa sổ có lỗ; KL NN/TD trước GDKHQ cổ tức
  CP / CP thưởng (events-v2) quy về cơ sở cp hiện hành → EST (kiểm chứng 27/09).
- Rổ VN30 hiện hành (vnstore.ma.nhom): thêm thành viên còn thiếu; nhãn chaebol / NHẬN ĐỊNH viết lại theo dossier
  (cap_nhat_<ngày>.screener.json, khoá tickers.<MÃ>.screener; mục thiếu src bị bỏ).
- Chú thích live dưới tiêu đề bảng (_live_note).
"""
from __future__ import annotations

import re
from collections import Counter
from math import prod

import chaebol_map_tab_codong as CD
from chaebol_map_dom import C, F_MONO, alpha, can_data, h, tier, to_fixed, upd_mark


WIN = 60                                               # cửa sổ dòng tiền (phiên)
# Sự kiện đổi đơn vị cổ phiếu (1 cp cũ = 1 + tỷ lệ cp mới, không trả tiền). Không tính cổ tức tiền, phát hành riêng
# lẻ / ESOP (không đổi đơn vị cp đang lưu hành) và quyền mua (cổ đông phải trả tiền).
RE_STOCK_EV = re.compile(r"cổ tức bằng cổ phiếu|cổ phiếu thưởng", re.I)


def _dossier_entry(ctx, tk):
    d = ctx.dossier if isinstance(ctx.dossier, dict) else {}
    ent = ((d.get("tickers") or {}).get(tk) or {}).get("screener")
    return ent if isinstance(ent, dict) else {}


def _group_label(v21, tk):
    for g in v21.get("CHAEBOL_GROUPS") or []:
        tks = [t["tk"] if isinstance(t, dict) else t for t in g.get("tickers") or []]
        if tk in tks:
            name = str(g.get("name") or g.get("id") or "")
            return re.sub(r"^NHÓM\s+", "", name).title() or None
    return None


def _ok(v):
    return v is not None and getattr(v, "value", None) is not None


def _stock_events(D, tk, win):
    """GDKHQ cổ tức CP / CP thưởng trong (win[0], win[-1]] → [(chỉ số phiên GDKHQ trong win, ngày, hệ số)] tăng dần;
    cùng ngày → hệ số 1 + Σ tỷ lệ. None = không có events-v2 (không kiểm được)."""
    ev = D.capital_events(tk)
    if getattr(ev, "value", None) is None:
        return None
    by = {}
    for e in ev.value:
        x, r = e.get("exright"), e.get("ratio")
        if (e.get("code") == "ISS" and x and RE_STOCK_EV.search(str(e.get("title") or ""))
                and isinstance(r, (int, float)) and 0 < r <= 10 and win[0] < x <= win[-1]):
            by[x] = by.get(x, 1.0) + r
    return [(next(i for i, d in enumerate(win) if d >= x), x, f) for x, f in sorted(by.items())]


def _seg_sum(win, events, fn):
    """Σ theo đoạn giữa các GDKHQ; đoạn trước một sự kiện nhân hệ số của mọi sự kiện sau nó (quy về cp hiện hành).
    fn(n, ngày_cuối) → V cp. Không đoạn nào có số → None."""
    cuts = [0] + [i for i, _, _ in events] + [len(win)]
    total = None
    for j in range(len(cuts) - 1):
        s, e = cuts[j], cuts[j + 1] - 1
        if e < s:
            continue
        v = fn(e - s + 1, win[e])
        if _ok(v):
            total = (total or 0.0) + v.value * prod(f for _, _, f in events[j:])
    return total


def _td_cover(D, tk, win):
    """(ngày bản ghi tự doanh cuối trong cửa sổ, số phiên có bản ghi, số phiên của cửa sổ tới ngày đó)."""
    n_co = D.prop_net(tk, len(win), kind="khop").get("n_co") or 0
    for j in range(len(win) - 1, -1, -1):
        if D.prop_net(tk, 1, win[j], kind="khop").get("n_co"):
            return win[j], n_co, j + 1
    return None, n_co, 0


def _flow_basis(D, tk, win, nn, td):
    """Sửa sau kiểm chứng 27/09: (1) TD mang ngày bản ghi cuối, không phải ngày cuối cửa sổ giá; (2) KL trước GDKHQ
    cổ phiếu quy về cơ sở cp hiện hành (cộng thẳng hai cơ sở là sai đơn vị) → EST."""
    out = {"nn": nn, "td": td, "td_cov": None, "conv": [], "ev_checked": True}
    last, n_co, n_upto = _td_cover(D, tk, win)
    events = _stock_events(D, tk, win)
    if events is None:
        out["ev_checked"] = False
        events = []
    if events:
        out["conv"] = [(x, f) for _, x, f in events]
        how = "; ".join("trước %s ×%s" % (_ddmm(x), _fx(f)) for _, x, f in events)
        if _ok(nn):
            s = _seg_sum(win, events, lambda n, e: D.foreign_net(tk, n, e)["vol"])
            out["nn"] = (D.V(s / 1e6, to_fixed(s / 1e6, 1), "EST", nn.asof, nn.src, "%s; KL quy về cp hiện hành: %s"
                             % (nn.note or "", how), "M cp") if s is not None else D.can_data("NN: không quy đổi được"))
        if _ok(td):
            s = _seg_sum(win, events, lambda n, e: D.prop_net(tk, n, e, kind="khop")["vol"])
            td = (D.V(s / 1e6, to_fixed(s / 1e6, 1), "EST", td.asof, td.src, "%s; KL quy về cp hiện hành: %s"
                      % (td.note or "", how), "M cp") if s is not None else D.can_data("TD: không quy đổi được"))
    if _ok(td) and last:
        td = D.V(td.value, td.text, td.tier, last, td.src, "%s; bản ghi cuối trong cửa sổ %s" % (td.note or "", last), td.unit)
        if n_co < n_upto:                         # lỗ giữa cửa sổ (không chỉ độ trễ 1–3 phiên cuối)
            out["td_cov"] = (n_co, len(win))
    out["td"] = td
    return out


def _fx(f):
    return ("%.4f" % f).rstrip("0").rstrip(".")


def _live_values(D, tk):
    lv = {}
    try:
        lp = D.last_price(tk)
        lv["px"] = lp.get("raw") if isinstance(lp, dict) else None
        dates = list(D.price_history(tk).dates)
        lv["perf"] = D.pct_change(tk, dates[-61]) if len(dates) > WIN else D.can_data("chưa đủ 61 phiên giá")
        f = D.flow4(tk, WIN)
        lv["nn"], lv["td"] = f.get("nn"), f.get("td")
        lv["win"] = (dates[-WIN:][0], dates[-1]) if dates else None
        lv["base"] = dates[-WIN - 1] if len(dates) > WIN else None
    except Exception as exc:                      # mã thiếu cache: từng ô thành [CẦN DATA]
        lv.setdefault("err", "%s: %s" % (type(exc).__name__, exc))
        return lv
    try:
        lv.update(_flow_basis(D, tk, dates[-WIN:], lv["nn"], lv["td"]))
    except Exception as exc:                      # không kiểm được ngày TD / quy đổi → không hiện số sai cơ sở
        why = "không kiểm được ngày tự doanh / quy đổi quyền (%s: %s)" % (type(exc).__name__, exc)
        lv.update(nn=D.can_data(why), td=D.can_data(why), flow_err=why)
    return lv


def _apply_live(ctx, v21, rows, cats):
    """Gắn số sống, rổ VN30 hiện hành, nhãn đã sửa (dossier) và thêm thành viên VN30 còn thiếu. → (rows, info).
    cats(nhãn) → giá trị scr.chaebol của hàng mới (luật lọc nằm ở chaebol_map_tab_screener._cats)."""
    D = ctx.data
    info = {"basket": None, "added": [], "fixed": [], "data_to": None, "cong_stop": True}
    if D is None:
        ctx.warn("chế độ live nhưng chưa nạp được chaebol_map_data — mọi số sống thành [CẦN DATA]")
        for r in rows:
            r["lv"] = {}
        return rows, info
    try:
        b = D.basket("VN30")
        info["basket"] = list(b.value) if b.value else None
        info["basket_asof"] = b.asof
    except Exception as exc:
        ctx.warn("không đọc được rổ VN30 hiện hành: %s" % exc)
    cong = (ctx.live_info or {}).get("cong") or {}
    text = str(cong.get("text") or "")
    info["cong_stop"] = ("DỪNG" in text) or ("[CẦN DATA" in text) or not text
    have = {r["tk"] for r in rows}
    for tk in (info["basket"] or []):
        if tk in have:
            continue
        label = _group_label(v21, tk)
        src = "v21:CHAEBOL_GROUPS"
        if not label:
            try:
                gs = D.groups_of(tk)
            except Exception:
                gs = []
            label, src = (gs[0], "chaebol_ecosystems.json") if gs else (None, None)
        try:
            sec = D.details(tk).get("sector")
        except Exception:
            sec = None
        rows.append({"tk": tk, "sec": sec, "chaebol": label or "", "phase": None, "sig": None, "cmt": None,
                     "px": 0, "perf60": 0, "ca60": 0, "to60": 0, "td60": 0, "nn60": 0, "date": None,
                     "v21": False, "new": True, "cats": cats(label or ""), "label_src": src,
                     "label": None, "basket": True, "lv": None})
        info["added"].append(tk)
    unchecked, cd2 = [], CD.v2_universe(ctx)
    for r in rows:
        r["cd2_on"] = CD.link_set(r["tk"], None) if r["tk"] in cd2 else None     # ô mã → tab codong v2 (§8.3)
        r["lv"] = _live_values(D, r["tk"])
        for k in ("err", "flow_err"):
            if r["lv"].get(k):
                ctx.warn("%s: %s" % (r["tk"], r["lv"][k]))
        if r["lv"].get("ev_checked") is False:
            unchecked.append(r["tk"])
        if info["basket"] is not None:
            r["basket"] = r["tk"] in info["basket"]
        fix = _dossier_entry(ctx, r["tk"]).get("chaebol")
        if r["v21"] and isinstance(fix, dict) and fix.get("text") and fix.get("src"):
            r["label"] = fix
            info["fixed"].append(r["tk"])
    if unchecked:
        ctx.warn("không có events-v2 → KL NN/TD chưa kiểm quy đổi quyền: " + ", ".join(unchecked))
    px = [r["lv"]["px"].asof for r in rows if r["lv"].get("px") is not None and r["lv"]["px"].asof]
    info["data_to"] = max(px) if px else None
    wins = Counter(r["lv"]["win"] for r in rows if r["lv"].get("win"))
    info["win"] = wins.most_common(1)[0][0] if wins else None
    bases = Counter(r["lv"]["base"] for r in rows if r["lv"].get("base"))
    info["base"] = bases.most_common(1)[0][0] if bases else None
    info["td_span"], info["td_odd"] = _td_span(rows)
    info["conv"] = [(r["tk"], r["lv"]["conv"]) for r in rows if r["lv"].get("conv")]
    info["unchecked"] = unchecked
    if ctx.dossier is None:
        ctx.warn("chưa có dossier cap_nhat_* — nhãn chaebol V21 giữ nguyên (không áp F2-046/F2-060/F2-078)")
    return rows, info


def _ddmm(iso, year=False):
    if not iso or len(str(iso)) < 10:
        return str(iso or "")
    s = str(iso)
    return s[8:10] + "/" + s[5:7] + ("/" + s[:4] if year else "")


def _span(lo, hi):
    """'22–24/09' (cùng tháng) · '28/08–24/09' · '24/09' (một ngày)."""
    if lo == hi:
        return _ddmm(lo)
    return (lo[8:10] if lo[5:7] == hi[5:7] else _ddmm(lo)) + "–" + _ddmm(hi)


def _td_span(rows):
    """Ngày bản ghi tự doanh cuối của các mã → (khoảng phủ các ngày có ≥ 2 mã, [(ngày, mã)] nằm ngoài khoảng đó)."""
    tds = [(r["lv"]["td"].asof, r["tk"]) for r in rows if _ok(r["lv"].get("td")) and r["lv"]["td"].asof]
    if not tds:
        return None, []
    cnt = Counter(d for d, _ in tds)
    main = sorted(d for d, c in cnt.items() if c >= 2) or sorted(cnt)
    lo, hi = main[0], main[-1]
    return _span(lo, hi), sorted((d, tk) for d, tk in tds if not lo <= d <= hi)


def _tg(v, ref):
    """Nhãn bậc của V sống: bỏ ngày khi trùng phiên tham chiếu của bảng (ghi ở sub + chú thích)."""
    return tier(v.tier, None if v.asof == ref else v.asof)


def _pattern_q(ctx, tk, text):
    """Mã ngoài 30 mã Toàn Vũ: 'Pattern X' → 'Pattern X?' (DESIGN §8.4)."""
    if not ctx.live or ctx.data is None or not text:
        return text
    try:
        return re.sub(r"Pattern ([A-D])\b(?!\?)", lambda m: ctx.data.pattern_label(tk, m.group(0)), text)
    except Exception:
        return text


def _live_note(info):
    ref = _ddmm(info.get("data_to"))
    added = ", ".join(info.get("added") or []) or "không mã nào"
    gate = "vì CỔNG v1.7 đang DỪNG" if info.get("cong_stop") else "theo CỔNG v1.7 hiện hành"
    w0, w1 = info.get("win") or (None, None)
    odd = info.get("td_odd") or []
    odd_s = ("; riêng " + ", ".join("%s %s" % (tk, _ddmm(d)) for d, tk in odd)) if 0 < len(odd) <= 5 else (
        "; các mã khác ghi ngày trong ô" if odd else "")
    conv = info.get("conv") or []
    conv_s = (" · ".join("%s %s" % (tk, " ".join("×%s (%s)" % (_fx(f), _ddmm(x)) for x, f in ev)) for tk, ev in conv)
              if conv else "không mã nào trong cửa sổ")
    return h("div", {"fontSize": 10, "fontFamily": F_MONO, "color": C.inkD, "lineHeight": 1.6, "marginBottom": 18,
                     "padding": "8px 18px", "background": alpha(C.ochre, "10"), "borderLeft": "3px solid " + C.ochre},
             "Bản live: GIÁ là giá thô phiên %s; Δ60D trên giá điều chỉnh quyền (mốc %s). NƯỚC NGOÀI (khớp + thoả "
             "thuận) và TỰ DOANH (khớp) là tổng vc_lk trong cửa sổ 60 phiên %s→%s — không nối FiinTrade. Tự doanh "
             "vendor chậm 1–3 phiên: ô TD ghi ngày bản ghi cuối (tới %s%s); phiên vắng không điền 0, ô có phiên vắng "
             "giữa cửa sổ ghi thêm số phiên có bản ghi. KL trước GDKHQ cổ tức CP / CP thưởng quy về cơ sở cp hiện "
             "hành (nhãn E; không tính cổ tức tiền, quyền mua): %s. CÁ NHÂN, TỔ CHỨC và SIG 4 kênh sau 08/05: "
             % (ref, _ddmm(info.get("base")), _ddmm(w0), _ddmm(w1), info.get("td_span") or "—", odd_s, conv_s),
             can_data(),
             " (phần dư −(NN+TD) không tách được hai kênh). PHASE, SIG V21, NHẬN ĐỊNH, nhóm chaebol và Top Picks là "
             "bản lưu V21·12/05, không chấm lại %s; bộ lọc PHASE/FLOW/CHAEBOL chạy trên nhãn V21. Rổ VN30 hiện hành: "
             "vnstore.ma.nhom %s — thêm %s." % (gate, _ddmm(info.get("basket_asof")), added),
             tier("FACT-T2", info.get("basket_asof")), upd_mark())
