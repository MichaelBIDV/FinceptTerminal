"""
chaebol_map_data_gia — giá theo mã (price-history vc_lk, hệ số quyền), chuỗi tuần + VWAP, chỉ số.

Tách từ chaebol_map_data.py (27/09/2026). Tab dùng qua mặt tiền `import chaebol_map_data as D`.
"""
from __future__ import annotations

import bisect
from datetime import date, timedelta

from chaebol_map_data_nen import *  # noqa: F401,F403
from chaebol_map_data_langkinh import lk_atom, lk_hoso
from chaebol_map_data_tailieu import v21_get

__all__ = [
    "price_history", "_psrc", "ADJ_TOL", "ADJ_STABLE", "SHARE_EV_MIN", "_RAW_OF", "_adj_series", "adj_fix",
    "_fix_note", "_adj_col", "_steps", "_share_events_all", "share_events", "_share_mult", "share_basis_note",
    "close", "_kho_close", "last_price", "adj_ratio", "adj_steps", "adj_factor", "convert_price", "pct_change",
    "pnl_since", "shares_out", "market_cap", "hi_lo_52w", "_week_groups", "_prop", "_prop_map", "_shares_filled",
    "_vwap_prep", "_vwap_at", "_vwap_label", "vwap_cluster", "weekly_ohlcv", "weekly_v21", "_index_cols",
    "index_close", "index_weekly", "index_weekly_spliced", "index_extremes", "index_pe_pb", "data_to",
]


def price_history(tk: str) -> Cols | None:
    """price-history cắt theo details.listingDate (VHM có 1.412 dòng trước niêm yết). Không có cache vc_lk →
    dự phòng vnstore.nen_ngay (base 'vnstore.nen_ngay[<MÃ>]'): TRỘN nến điều chỉnh (vci_history) với dòng bảng
    THÔ (vci_board) → thô = điều chỉnh, không có NN/tự doanh/cp; adj_factor trả [CẦN DATA]."""
    _, det = vc(tk, "details")
    start = iso(det.get("listingDate")) if isinstance(det, dict) else None
    c = _cols_of(tk, "price-history", start)
    if c is not None:
        c.base = f"vc_lk/{tk}/price-history"
        return c
    rows = db_query("SELECT ngay, mo, cao, thap, dong, kl FROM nen_ngay WHERE symbol=? ORDER BY ngay", (tk,))
    if not rows:
        return None

    def build():
        warn(f"{tk}: không có vc_lk — giá từ vnstore.nen_ngay (trộn giá điều chỉnh và giá bảng thô; không có NN/tự doanh)")
        k = Cols(["tradingDate", "openPriceAdjusted", "highestPriceAdjusted", "lowestPriceAdjusted", "closePriceAdjusted",
                  "totalMatchVolume", "closePrice"], [list(r) + [r[4]] for r in rows])
        k.base = f"vnstore.nen_ngay[{tk}]"
        return k
    return _memo(("kho_ph", str(_db_path()), tk), _sig(_db_path()), build)


def _psrc(tk, f):
    ph = price_history(tk)
    return f"{getattr(ph, 'base', None) or f'vc_lk/{tk}/price-history'}.{f}"


# ───────────────────── chuỗi điều chỉnh vendor: tự kiểm adj/raw phiên cuối ─────────────────────

ADJ_TOL = 0.002            # closeAdj/close phiên cuối phải = 1 (±0,2%); lệch hơn → chuỗi điều chỉnh vendor hỏng
ADJ_STABLE = 1e-4          # đoạn ổn định: ba phiên liên tiếp adj/raw đổi < 0,01%
SHARE_EV_MIN = 1.001       # hệ số KL ≤ 1,001 → không coi là sự kiện chia cp
_RAW_OF = {"openPriceAdjusted": "openPrice", "highestPriceAdjusted": "highestPrice",
           "lowestPriceAdjusted": "lowestPrice", "closePriceAdjusted": "closePrice",
           "averagePriceAdjusted": "averagePrice"}


def _adj_series(ph: Cols):
    """(f, fix): f[i] = closeAdj/close phiên i (None nếu thiếu hoặc giá ≤ 0). Vendor phải cho f = 1 ở phiên cuối có
    số; lệch quá ADJ_TOL (MSR 25/09 = 1,0128, VGI 1,0025: sau GDKHQ cổ tức tiền 16–17/09 vendor ghi giá điều chỉnh
    nhiễu) thì sau đoạn ổn định cuối cùng (ba phiên f không đổi) chuỗi điều chỉnh là hỏng → f = 1 (giá thô), trước đó
    giữ hệ số vendor. fix = {brk: ngày đầu dùng giá thô, k: chỉ số phiên cuối đoạn ổn định, last: f phiên cuối, stable: f[k]}
    hoặc None. Cùng thuật toán với tab codong (DeepLive._ratios). Cache trên đối tượng Cols (cache theo mtime tệp)."""
    if getattr(ph, "_adj", None) is None:
        C, A = ph.col("closePrice"), ph.col("closePriceAdjusted")
        f = [a / c if _finite(c) and _finite(a) and c > 0 and a > 0 else None for c, a in zip(C, A)]
        last, fix = next((x for x in reversed(f) if x is not None), None), None
        if str(getattr(ph, "base", "")).startswith("vc_lk") and last is not None and abs(last - 1) > ADJ_TOL:
            k = next((i for i in range(len(f) - 1, 1, -1) if None not in (f[i], f[i - 1], f[i - 2])
                      and abs(f[i] / f[i - 1] - 1) < ADJ_STABLE and abs(f[i - 1] / f[i - 2] - 1) < ADJ_STABLE), None)
            if k is not None and k < len(f) - 1:
                fix = {"brk": ph.dates[k + 1], "k": k, "last": last, "stable": f[k]}
                f = f[:k + 1] + [1.0] * (len(f) - k - 1)
        ph._adj = (f, fix)
    return ph._adj


def adj_fix(tk: str) -> dict | None:
    """Kết quả tự kiểm chuỗi điều chỉnh vendor của mã (xem _adj_series): None = adj/raw phiên cuối = 1 (ổn);
    dict {brk, k, last, stable} = từ `brk` các hàm giá điều chỉnh của lớp này dùng giá thô."""
    ph = price_history(tk)
    fix = _adj_series(ph)[1] if ph is not None and len(ph) else None
    return dict(fix) if fix else None


def _fix_note(fix: dict) -> str:
    return (f"⚑ chuỗi điều chỉnh vendor lệch từ {ddmmyyyy(fix['brk'])} (adj/raw phiên cuối {js_fixed(fix['last'], 4)} "
            f"≠ 1) — từ đó dùng giá thô")


def _adj_col(ph: Cols, name: str) -> list:
    """Cột giá điều chỉnh đã tự kiểm: sau điểm hỏng (adj_fix) lấy cột giá THÔ tương ứng; không hỏng → cột vendor."""
    fix, raw = _adj_series(ph)[1], _RAW_OF.get(name)
    if not fix or raw is None or raw not in ph.ix:
        return ph.col(name)
    key = "_sua:" + name
    if key not in ph._c:
        ph._c[key] = ph.col(name)[:fix["k"] + 1] + ph.col(raw)[fix["k"] + 1:]
    return ph._c[key]


def _steps(ph: Cols, a: int, b: int, after: str, tol: float = 0.001) -> list:
    f, out, prev = _adj_series(ph)[0], [], None
    for i in range(max(a, 0), b + 1):
        r = f[i]
        if r is not None and prev is not None and abs(r / prev - 1) > tol and ph.dates[i] > after:
            out.append((ph.dates[i], prev / r))
        prev = r if r is not None else prev
    return out


def _share_events_all(ph: Cols) -> list:
    """Mọi GDKHQ chia/thưởng/cổ tức CP/quyền mua của chuỗi: phiên có bước giá điều chỉnh VÀ totalShares tăng →
    hệ số KL = min(Δ số cp, 1/bước). Bước giá không kèm tăng cp (cổ tức tiền) và tăng cp không kèm bước giá (ESOP,
    riêng lẻ, chuyển đổi, bán cp quỹ) không tính. Thuật toán chung với tab overview/portfolio/screener (27/09)."""
    if getattr(ph, "_sev", None) is None:
        S, out = ph.col("totalShares"), []
        if str(getattr(ph, "base", "")).startswith("vc_lk") and len(ph):
            for d, step in _steps(ph, 0, len(ph) - 1, ""):
                e = ph.at(d)
                s0 = next((S[i] for i in range(e - 1, -1, -1) if S[i]), None)
                s1 = next((S[i] for i in range(e, len(S)) if S[i]), None)
                m = min(s1 / s0, 1 / step) if s0 and s1 and step else 1.0
                if m > SHARE_EV_MIN:
                    out.append({"date": d, "i": e, "factor": m, "step": step, "shares_ratio": s1 / s0})
        ph._sev = out
    return ph._sev


def share_events(tk: str, d0=None, d1=None) -> list:
    """GDKHQ chia/thưởng/cổ tức CP/quyền mua trong (d0, d1] (mặc định cả chuỗi):
    [{date, i (chỉ số phiên), factor (hệ số KL = min(Δcp, 1/bước)), step (bước giá), shares_ratio}] tăng dần. EST."""
    ph = price_history(tk)
    if ph is None or not len(ph):
        return []
    lo, hi = iso(d0) or "", iso(d1) or "9999"
    return [dict(e) for e in _share_events_all(ph) if lo < e["date"] <= hi]


def _share_mult(ph: Cols) -> list:
    """m[i] = Π hệ số KL của các sự kiện có chỉ số > i (tới phiên cuối): nhân KL phiên i → số cp hiện hành."""
    if getattr(ph, "_smul", None) is None:
        ev = {e["i"]: e["factor"] for e in _share_events_all(ph)}
        m, p = [1.0] * len(ph), 1.0
        for i in range(len(ph) - 1, -1, -1):
            m[i] = p
            p *= ev.get(i, 1.0)
        ph._smul = m
    return ph._smul


def share_basis_note(evs: list) -> str:
    """'KL quy về số cp hiện hành: ×2 trước 06/08/2026 · ×1.1 trước 21/09/2026'."""
    return "KL quy về số cp hiện hành: " + " · ".join(
        f"×{js_fixed(e['factor'], 4).rstrip('0').rstrip('.')} trước {ddmmyyyy(e['date'])}" for e in evs)


# ───────────────────────────── giá ─────────────────────────────

def close(tk: str, d=None, adjusted: bool = False) -> V:
    """Giá đóng cửa (đồng) phiên cuối ≤ d. adjusted=True → closePriceAdjusted (thưởng cp + cổ tức tiền)."""
    ph = price_history(tk)
    f = "closePriceAdjusted" if adjusted else "closePrice"
    if not ph or not len(ph):
        return _kho_close(tk) if d is None and not adjusted else can_data(f"không có vc_lk/{tk}/price-history")
    i = ph.at(d)
    if i < 0:
        return can_data(f"{tk}: trước phiên đầu {ddmmyyyy(ph.dates[0])}", _psrc(tk, f))
    v, j = _last(_adj_col(ph, f) if adjusted else ph.col(f), i)
    if v is None:
        return can_data(f"{tk}: {f} trống", _psrc(tk, f))
    note = "giá điều chỉnh vendor (thưởng cp + cổ tức tiền)" if adjusted else None
    fix = _adj_series(ph)[1] if adjusted else None
    if fix and j > fix["k"]:
        note += "; " + _fix_note(fix)
    vcb = ph.base.startswith("vc_lk")
    if not vcb:
        note = "dự phòng vnstore.nen_ngay: trộn giá điều chỉnh (vci_history) và giá bảng thô (vci_board)"
    if d is not None and ph.dates[j] != iso(d):
        note = ((note + "; ") if note else "") + f"phiên gần nhất ≤ {ddmmyyyy(d)}"
    return V(v, js_locale(v, 1), T2 if vcb else UNV, ph.dates[j], _psrc(tk, f), note, "đ")   # giá trộn → U


def _kho_close(tk: str) -> V:
    r = db_query("SELECT gia, ngay FROM gia_moi WHERE symbol=?", (tk,))
    if not r or r[0][0] is None:
        return can_data(f"không có giá {tk} (vc_lk và vnstore.gia_moi)")
    warn(f"{tk}: giá lấy từ vnstore.gia_moi (không có vc_lk) — giá bảng thô")
    return V(r[0][0], js_locale(r[0][0], 1), T2, iso(r[0][1]), "vnstore.gia_moi (vci_board)",
             "dự phòng: giá bảng thô; không trộn với chuỗi điều chỉnh", "đ")


def last_price(tk: str) -> dict:
    """{'date', 'raw': V, 'adj': V} phiên cuối vc_lk."""
    raw, adj = close(tk), close(tk, adjusted=True)
    return {"date": raw.asof, "raw": raw, "adj": adj}


def adj_ratio(tk: str, d=None):
    """closeAdjusted/close tại phiên cuối ≤ d (None nếu không đo được); chuỗi vendor hỏng → đã tự sửa (adj_fix)."""
    ph = price_history(tk)
    if not ph:
        return None
    i = ph.at(d)
    return _adj_series(ph)[0][i] if i >= 0 else None


def adj_steps(tk: str, d0, d1=None, tol: float = 0.001) -> list:
    """Các phiên mà hệ số quyền đổi (GDKHQ): [(ngày, bước)] trong (d0, d1] (trên chuỗi adj/raw đã tự kiểm)."""
    ph = price_history(tk)
    if not ph:
        return []
    return _steps(ph, ph.at(d0), ph.at(d1), iso(d0), tol)


def adj_factor(tk: str, d0, d1=None) -> V:
    """Hệ số đưa giá THÔ ngày d0 về cơ sở giá ngày d1 (mặc định phiên cuối): f(d0)/f(d1), f = adj/close.
    Ví dụ ngưỡng 23K của HPG trước cổ tức CP 10% → 23 × hệ số ≈ 20,9K. EST (dẫn xuất FACT-T2)."""
    ph = price_history(tk)
    if ph is not None and not str(getattr(ph, "base", "")).startswith("vc_lk"):
        return can_data(f"{tk}: chỉ có vnstore.nen_ngay (không tách giá thô/điều chỉnh) — không đo được hệ số quyền",
                        _psrc(tk, "closePrice"))
    f0, f1 = adj_ratio(tk, d0), adj_ratio(tk, d1)
    if f0 is None or f1 is None:
        return can_data(f"{tk}: thiếu closePrice/closePriceAdjusted quanh {ddmmyyyy(d0)}", _psrc(tk, "closePriceAdjusted"))
    d1s = ph.dates[ph.at(d1)]
    steps = adj_steps(tk, d0, d1)
    ev = "; ".join(f"{ddmmyyyy(d)} ×{js_fixed(s, 4)}" for d, s in steps) or "không có sự kiện quyền"
    fix = _adj_series(ph)[1]
    return V(f0 / f1, js_fixed(f0 / f1, 4), EST, d1s, _psrc(tk, "closePriceAdjusted/closePrice"),
             f"f({ddmmyyyy(d0)})={js_fixed(f0, 4)} ÷ f({ddmmyyyy(d1s)})={js_fixed(f1, 4)}; gồm thưởng cp và cổ tức "
             f"tiền; bước: {ev}" + (f"; {_fix_note(fix)}" if fix and ph.at(d1) > fix["k"] else ""), "x")


def convert_price(tk: str, px, d0, d1=None) -> V:
    """Quy đổi một mức giá thô cũ (ngày d0) sang cơ sở giá d1 (EST)."""
    f = adj_factor(tk, d0, d1)
    if f.can or not _finite(px):
        return can_data(f.note or "giá gốc trống", f.src)
    return V(px * f.value, js_locale(px * f.value, 1), EST, f.asof, f.src, f"{js_locale(px, 1)} × {f.text}; {f.note}", "đ")


def pct_change(tk: str, d0, d1=None) -> V:
    """% thay đổi giá điều chỉnh từ phiên ≤ d0 tới phiên ≤ d1 (mặc định cuối). EST."""
    a, b = close(tk, d0, True), close(tk, d1, True)
    if a.can or b.can or not a.value:
        return can_data(f"{tk}: thiếu giá điều chỉnh {ddmmyyyy(d0)}→{ddmmyyyy(d1) or 'cuối'}", _psrc(tk, "closePriceAdjusted"))
    x = (b.value / a.value - 1) * 100
    return V(x, pct_text(x, 1), EST, b.asof, _psrc(tk, "closePriceAdjusted"),
             f"({js_locale(b.value, 1)} / {js_locale(a.value, 1)} − 1), phiên {ddmmyyyy(a.asof)} → {ddmmyyyy(b.asof)}", "%")


def pnl_since(tk: str, d0, px0=None, position=None, cost=None) -> dict:
    """Lãi/lỗ từ bản lưu (V21) tới nay, quy đổi quyền (EST): giá d0 (px0 hoặc giá vendor), % tổng lợi suất
    giá điều chỉnh, giá trị ước = position × px0 × (1+%), lãi/lỗ so giá vốn."""
    pc = pct_change(tk, d0)
    out = {"pct": pc, "now": close(tk), "factor": adj_factor(tk, d0)}
    if pc.can:
        return out
    p0 = px0 if _finite(px0) else close(tk, d0).value
    if _finite(position) and _finite(p0):
        val = position * p0 * (1 + pc.value / 100)
        out["value_now"] = V(val, js_locale(val, 0), EST, pc.asof, pc.src,
                             "giả định giữ nguyên vị thế; quy đổi quyền bằng giá điều chỉnh (xấp xỉ tổng lợi suất)", "đ")
        if _finite(cost):
            pl = val - position * cost
            out["pnl"] = V(pl, js_locale(pl, 0), EST, pc.asof, pc.src, f"so giá vốn {js_locale(cost, 0)} đ", "đ")
            out["pnl_pct"] = V((val / (position * cost) - 1) * 100, pct_text((val / (position * cost) - 1) * 100, 1),
                               EST, pc.asof, pc.src, None, "%") if cost else can_data("giá vốn 0")
    return out


def shares_out(tk: str) -> V:
    """Số cp lưu hành: price-history.totalShares (phiên cuối có số). Lệch >0,5% với details/structure/KHO → note."""
    ph = price_history(tk)
    if not ph or not len(ph):
        return can_data(f"không có vc_lk/{tk}/price-history")
    v, j = _last(ph.col("totalShares"), len(ph) - 1)
    if v is None:
        return can_data(f"{tk}: totalShares trống", _psrc(tk, "totalShares"))
    alts = []
    _, det = vc(tk, "details")
    _, st = vc(tk, "shareholder-structure")
    if isinstance(det, dict):
        alts.append(("vc_lk details.issueShare", det.get("issueShare")))
    if isinstance(st, dict):
        alts.append(("vc_lk shareholder-structure.totalShares", st.get("totalShares")))
    for r in db_query("SELECT so_cp_luu_hanh, cap_nhat FROM ho_so WHERE symbol=?", (tk,)):
        alts.append((f"vnstore.ho_so (KBS {ddmm(r[1])})", r[0]))
    for r in db_query("SELECT issue_share, cap_nhat FROM free_float WHERE symbol=?", (tk,)):
        alts.append((f"vnstore.free_float ({ddmm(r[1])})", r[0]))
    ciq = ((read_json(sys_dir() / "alpha_spine" / "capiq_signals.json", quiet=True) or {}).get("by_ticker") or {}).get(tk) or {}
    if ciq.get("concentration"):
        per = (ciq.get("ownership_activity") or {}).get("period") or "?"
        alts.append((f"CapIQ kỳ {per} (xuất {ddmmyyyy(ciq.get('as_of'))}, cũ)", ciq["concentration"].get("shares_out")))
    lech = [f"{n}: {js_locale(x, 0)}" for n, x in alts if _finite(x) and abs(x / v - 1) > SHARE_TOL]
    note = f"mẫu số = totalShares phiên {ddmmyyyy(ph.dates[j])}"
    if lech:
        note += "; NGUỒN LỆCH — " + " · ".join(lech)
        if any("cũ)" not in x for x in lech):
            warn(f"{tk}: số cp lưu hành lệch giữa nguồn ({len(lech) + 1} số) — dùng vc_lk price-history")
    return V(v, js_locale(v, 0), T2, ph.dates[j], _psrc(tk, "totalShares"), note, "cp")


def market_cap(tk: str) -> V:
    """Vốn hoá (đồng): marketCap vendor phiên cuối; trống → cp lưu hành × giá đóng cửa (EST)."""
    ph = price_history(tk)
    if not ph or not len(ph):
        return can_data(f"không có vc_lk/{tk}/price-history")
    i = len(ph) - 1
    mc = ph.col("marketCap")[i]
    if _finite(mc):
        return V(mc, js_locale(mc / 1e9, 0) + " tỷ", T2, ph.dates[i], _psrc(tk, "marketCap"), None, "đ")
    s, c = shares_out(tk), close(tk)
    if s.can or c.can:
        return can_data(f"{tk}: vendor chưa có marketCap phiên cuối và thiếu cp/giá")
    v = s.value * c.value
    return V(v, js_locale(v / 1e9, 0) + " tỷ", EST, c.asof, f"{s.src} × {c.src}",
             f"vendor chưa có marketCap phiên {ddmmyyyy(c.asof)} → cp ({ddmmyyyy(s.asof)}) × giá", "đ")


def hi_lo_52w(tk: str, end=None, intraday: bool = False) -> dict:
    """Đỉnh/đáy 52 tuần (364 ngày lịch, giá điều chỉnh; intraday → high/lowAdjusted). V.asof = ngày cực trị."""
    ph = price_history(tk)
    if not ph or not len(ph):
        return {"hi": can_data(f"không có vc_lk/{tk}/price-history"), "lo": can_data(f"không có vc_lk/{tk}")}
    b = ph.at(end)
    if b < 0:
        c = can_data(f"{tk}: trước phiên đầu {ddmmyyyy(ph.dates[0])}")
        return {"hi": c, "lo": c}
    moc = (date.fromisoformat(ph.dates[b]) - timedelta(days=364)).isoformat()
    a = bisect.bisect_right(ph.dates, moc)
    hf, lf = ("highestPriceAdjusted", "lowestPriceAdjusted") if intraday else ("closePriceAdjusted",) * 2
    out = {}
    for k, f, pick in (("hi", hf, max), ("lo", lf, min)):
        pts = [(x, ph.dates[i]) for i, x in enumerate(_adj_col(ph, f)[a:b + 1], a) if _finite(x)]
        if not pts:
            out[k] = can_data(f"{tk}: không có {f} trong 52 tuần")
            continue
        x, d = pick(pts, key=lambda t: t[0])
        out[k] = V(x, js_locale(x, 1), T2, d, _psrc(tk, f),
                   f"52 tuần tới {ddmmyyyy(ph.dates[b])}; giá điều chỉnh", "đ")
    c = close(tk, end, True)
    if not c.can and not out["hi"].can:
        x = (c.value / out["hi"].value - 1) * 100
        out["from_hi"] = V(x, pct_text(x, 1), EST, c.asof, out["hi"].src, "so đỉnh 52 tuần", "%")
    return out


# ───────────────────────────── tuần + VWAP ─────────────────────────────

def _week_groups(dates: list, start=None, end=None) -> list:
    """[(thứ Hai ISO, [chỉ số phiên])] — tuần ISO Thứ Hai→Chủ nhật."""
    groups: list = []
    s, e = iso(start), iso(end)
    for i, d in enumerate(dates):
        if (s and d < s) or (e and d > e):
            continue
        dd = date.fromisoformat(d)
        mon = (dd - timedelta(days=dd.weekday())).isoformat()
        if groups and groups[-1][0] == mon:
            groups[-1][1].append(i)
        else:
            groups.append((mon, [i]))
    return groups


def _prop(tk: str) -> Cols | None:
    return _cols_of(tk, "proprietary-history")


def _prop_map(tk: str, kind: str = "total") -> dict:
    pr = _prop(tk)
    if not pr:
        return {}
    fv, fg = (("totalMatchTradeNetVolume", "totalMatchTradeNetValue") if kind == "khop"
              else ("totalTradeNetVolume", "totalTradeNetValue"))
    return {d: (v, g) for d, v, g in zip(pr.dates, pr.col(fv), pr.col(fg))}


def _shares_filled(ph: Cols) -> list:
    """totalShares theo ngày: bỏ gai một phiên, ffill rồi bfill."""
    s = list(ph.col("totalShares"))
    for i in range(1, len(s) - 1):
        if s[i] is not None and s[i - 1] is not None and s[i - 1] == s[i + 1] and s[i] != s[i - 1]:
            s[i] = s[i - 1]
    last = None
    for i, x in enumerate(s):
        s[i] = last = x if x else last
    first = next((x for x in s if x), None)
    return [x if x else first for x in s]


def _vwap_prep(ph: Cols):
    """Tổng tiền tố Σ(closeAdj·KL/cp_d), Σ(KL/cp_d) → VWAP = tỷ số (tương đương KLn = KL·cp_now/cp_d).
    Lưu trên chính đối tượng Cols (Cols được cache theo mtime tệp)."""
    if getattr(ph, "_vw", None) is None:
        C, K, S = _adj_col(ph, "closePriceAdjusted"), ph.col("totalMatchVolume"), _shares_filled(ph)
        pa, pb = [0.0], [0.0]
        for c, k, s in zip(C, K, S):
            w = (k / s if s else k) if _finite(c) and _finite(k) and k > 0 else 0.0
            pa.append(pa[-1] + (c * w if w else 0.0))
            pb.append(pb[-1] + w)
        ph._vw = (pa, pb)
    return ph._vw


def _vwap_at(ph: Cols, b: int, months: int):
    pa, pb = _vwap_prep(ph)
    a = bisect.bisect_right(ph.dates, lui_thang(ph.dates[b], months))
    den = pb[b + 1] - pb[a]
    return (pa[b + 1] - pa[a]) / den if den > 0 else None


def _vwap_label(kc: dict):
    """Luật nhãn lk_tinh.nhan_vwap (spec §4, ngưỡng kẹp 6%)."""
    k = [kc.get(n) for n in (6, 12, 24)]
    if any(x is None for x in k):
        return None
    if all(x < 0 for x in k):
        return "kep_nong" if max(abs(x) for x in k) <= 0.06 else "kep_sau"
    if all(x >= 0 for x in k):
        return "tren_cum"
    return "thoat_6t" if k[0] >= 0 else "khac"


def vwap_cluster(tk: str, end=None) -> dict:
    """VWAP cụm 6/12/24 tháng lịch (nghìn đồng) + kc (%) + nhãn. Ưu tiên lk_hoso.vwap khi cùng phiên cuối
    (engine lăng kính, có mô hình sự kiện vốn); ngược lại tự tính từ price-history (EST)."""
    ph = price_history(tk)
    if not ph or not len(ph):
        return {"nhan": None, **{f"v{n}": can_data(f"không có vc_lk/{tk}/price-history") for n in (6, 12, 24)}}
    b = ph.at(end)
    hs = lk_hoso(tk) if end is None else None
    vw = (hs or {}).get("vwap") or {}
    if vw.get("v6", {}).get("t") == ph.dates[b] and all(_finite((vw.get(f"v{n}") or {}).get("v")) for n in (6, 12, 24)):
        out = {f"v{n}": lk_atom(vw[f"v{n}"], f"lk_hoso/{tk}.vwap.v{n}") for n in (6, 12, 24)}
        out.update({f"kc{n}": lk_atom(vw.get(f"kc{n}"), f"lk_hoso/{tk}.vwap.kc{n}") for n in (6, 12, 24)})
        out["nhan"] = vw.get("nhan")
        return out
    px = _adj_col(ph, "closePriceAdjusted")[b]
    out, kc, vcb = {}, {}, str(ph.base).startswith("vc_lk")     # vnstore: giá trộn → VWAP mang U
    for n in (6, 12, 24):
        v = _vwap_at(ph, b, n)
        src = f"{ph.base} (Σ closeAdj·KL/cp ÷ Σ KL/cp)"
        out[f"v{n}"] = (V(v / 1000, js_fixed(v / 1000, 2), EST if vcb else UNV, ph.dates[b], src,
                          f"lịch {n} tháng từ {ddmmyyyy(lui_thang(ph.dates[b], n))}", "nghin_dong")
                        if v else can_data(f"{tk}: không đủ phiên cho VWAP {n}T", src))
        kc[n] = px / v - 1 if v and _finite(px) else None
        out[f"kc{n}"] = (V(kc[n] * 100, pct_text(kc[n] * 100, 1), EST if vcb else UNV, ph.dates[b], src, None, "%")
                         if kc[n] is not None else can_data("thiếu VWAP"))
    out["nhan"] = _vwap_label(kc)
    return out


def weekly_ohlcv(tk: str, start=None, end=None, label: str = "monday", vwap: bool = True, adjust: bool = False) -> V:
    """Chuỗi tuần ISO từ price-history (giá ĐIỀU CHỈNH, đồng): label 'monday' (quy ước WEEKLY_OHLCV của trang:
    nhãn thứ Hai, giá đóng phiên cuối tuần) | 'friday' | 'last'. Cột: o h l c c_raw vol val (khớp lệnh),
    nn_vol nn_val (Σ foreignNet*Total = khớp + thoả thuận; tách khớp bị fetcher cắt), td_vol td_val (tự doanh
    tổng) + td_khop_vol td_khop_val (chỉ khớp = ngữ nghĩa FiinTrade PL của V21) + td_n (None khi tuần không có
    bản ghi), nn_last / td_last (phiên cuối trong tuần CÓ số NN / bản ghi tự doanh — DESIGN §9), vwap6/12/24 (đồng,
    EST), n (số phiên), partial (tuần cuối chưa đủ tới thứ Sáu). adjust=True: vol, nn_vol, td_*_vol quy về số cp
    hiện hành qua GDKHQ chia/thưởng/quyền mua (share_events); giá trị đồng không đổi."""
    ph = price_history(tk)
    if not ph or not len(ph):
        return can_data(f"không có vc_lk/{tk}/price-history")
    M = _share_mult(ph) if adjust else None
    q = (lambda x, i: x * M[i] if _finite(x) else None) if M else (lambda x, i: x)  # noqa: E731
    O, H, L, C = (_adj_col(ph, f"{x}PriceAdjusted") for x in ("open", "highest", "lowest", "close"))
    CR, K, G = ph.col("closePrice"), ph.col("totalMatchVolume"), ph.col("totalMatchValue")
    NV, NG = ph.col("foreignNetVolumeTotal"), ph.col("foreignNetValueTotal")
    prop, prk = _prop_map(tk), _prop_map(tk, "khop")
    groups = _week_groups(ph.dates, start, end)
    rows = []
    for k, (mon, ix) in enumerate(groups):
        a, b = ix[0], ix[-1]
        fri = (date.fromisoformat(mon) + timedelta(days=4)).isoformat()
        td = [(q(prop[ph.dates[i]][0], i), prop[ph.dates[i]][1]) for i in ix if ph.dates[i] in prop]
        tk_ = [(q(prk[ph.dates[i]][0], i), prk[ph.dates[i]][1]) for i in ix if ph.dates[i] in prk]
        row = {"label": mon if label == "monday" else fri if label == "friday" else ph.dates[b],
               "monday": mon, "week_end": ph.dates[b], "n": len(ix),
               "o": O[a], "h": max((H[i] for i in ix if _finite(H[i])), default=None),
               "l": min((L[i] for i in ix if _finite(L[i])), default=None), "c": C[b], "c_raw": CR[b],
               "vol": _sum(q(K[i], i) for i in ix), "val": _sum(G[i] for i in ix),
               "nn_vol": _sum(q(NV[i], i) for i in ix), "nn_val": _sum(NG[i] for i in ix),
               "td_vol": _sum(t[0] for t in td), "td_val": _sum(t[1] for t in td), "td_n": len(td),
               "td_khop_vol": _sum(t[0] for t in tk_), "td_khop_val": _sum(t[1] for t in tk_),
               "nn_last": next((ph.dates[i] for i in reversed(ix) if _finite(NV[i])), None),
               "td_last": next((ph.dates[i] for i in reversed(ix) if ph.dates[i] in prop), None),
               "partial": k == len(groups) - 1 and fri > ph.dates[b]}
        if vwap:
            for n in (6, 12, 24):
                row[f"vwap{n}"] = _vwap_at(ph, b, n)
        rows.append(row)
    pr = _prop(tk)
    evs = [e for e in _share_events_all(ph) if groups and e["date"] > ph.dates[groups[0][1][0]]] if adjust else []
    return V(rows, None, T2, ph.dates[-1], f"{ph.base} + vc_lk/{tk}/proprietary-history",
             f"giá/KL/NN FACT-T2 tới {ddmmyyyy(ph.dates[-1])}; tự doanh tới "
             f"{ddmmyyyy(pr.dates[-1]) if pr and len(pr) else '—'} (phiên vắng không điền 0); VWAP EST; "
             "kênh Cá nhân/Tổ chức: [CẦN DATA]" + (f"; {share_basis_note(evs)} (EST)" if evs else ""), "đ")


def weekly_v21(tk: str, start=None, end=None) -> V:
    """Hàng theo khuôn WEEKLY_OHLCV của trang: [nhãn thứ Hai, close_K, vol_M, ca, tc, td_M, nn_M, v6_K, v12_K, v24_K].
    ca/tc = None ([CẦN DATA]); vol_M = KL khớp lệnh tuần (V21 dùng Σ kênh dương FiinTrade — khác ngữ nghĩa);
    td_M = tự doanh khớp; nn_M = NN khớp + thoả thuận. Giá theo cơ sở điều chỉnh HIỆN TẠI (VHM sau 06/08 khác V21)."""
    w = weekly_ohlcv(tk, start, end)
    if w.can:
        return w

    def k(x, n=2):
        return round_half(x / 1000, n) if _finite(x) else None

    def m(x):
        return round_half(x / 1e6, 3) if _finite(x) else None
    rows = [[r["label"], k(r["c"]), m(r["vol"]), None, None, m(r["td_khop_vol"]), m(r["nn_vol"]),
             k(r["vwap6"]), k(r["vwap12"]), k(r["vwap24"])] for r in w.value]
    return V(rows, None, T2, w.asof, w.src, w.note + "; vol_M = KL khớp lệnh (khác cột vol V21); td = tự doanh "
             "KHỚP (khớp V21 103/103 tuần MSN); nn = khớp + thoả thuận (V21 chỉ khớp → lệch ở tuần có thoả thuận)", "K/M")


# ───────────────────────────── chỉ số ─────────────────────────────

def _index_cols(idx: str):
    """(Cols[tradingDate,o,h,l,c,v], src). VNINDEX: vc_lk gap-chart; chỉ số khác: vnstore.nen_ngay."""
    if idx == "VNINDEX":
        c = _cols_of("VNINDEX", "gap-chart")
        if c and len(c):
            return c, "vc_lk/VNINDEX/gap-chart"
    rows = db_query("SELECT ngay, mo, cao, thap, dong, kl FROM nen_ngay WHERE symbol=? ORDER BY ngay", (idx,))
    if rows:
        if idx == "VNINDEX":
            warn("VNINDEX: dùng vnstore.nen_ngay dự phòng (chỉ từ 20/09/2024)")
        return Cols(["tradingDate", "o", "h", "l", "c", "v"], [list(r) for r in rows]), "vnstore.nen_ngay"
    return None, None


def index_close(idx: str = "VNINDEX", d=None) -> V:
    c, src = _index_cols(idx)
    if not c:
        return can_data(f"không có chuỗi {idx}")
    i = c.at(d)
    if i < 0:
        return can_data(f"{idx}: trước phiên đầu {ddmmyyyy(c.dates[0])}", src)
    x = c.col("c")[i]
    prev = c.col("c")[i - 1] if i > 0 else None
    chg = (x / prev - 1) * 100 if _finite(prev) and prev else None
    return V(x, js_locale(x, 2), T2, c.dates[i], src, f"±1 phiên {pct_text(chg, 2)}" if chg is not None else None, "điểm")


def index_weekly(idx: str = "VNINDEX", start=None, end=None) -> V:
    """Tuần ISO, nhãn = phiên cuối tuần (quy ước INDEX_DATA: có tuần kết thúc thứ Tư vì nghỉ lễ);
    chg = (c/c_trước − 1)×100 làm tròn 3 số (EST). VN30 chỉ có từ 20/09/2024 (vnstore)."""
    c, src = _index_cols(idx)
    if not c:
        return can_data(f"không có chuỗi {idx} (VN30 trước 20/09/2024 phải giữ INDEX_DATA V21)")
    O, H, L, Cc, Vv = (c.col(x) for x in ("o", "h", "l", "c", "v"))
    rows, prev = [], None
    groups = _week_groups(c.dates, None, end)
    for k, (mon, ix) in enumerate(groups):
        a, b = ix[0], ix[-1]
        fri = (date.fromisoformat(mon) + timedelta(days=4)).isoformat()
        r = {"date": c.dates[b], "monday": mon, "o": O[a], "h": max((H[i] for i in ix if _finite(H[i])), default=None),
             "l": min((L[i] for i in ix if _finite(L[i])), default=None),
             "c": Cc[b], "v": _sum(Vv[i] for i in ix), "n": len(ix),
             "chg": round_half((Cc[b] / prev - 1) * 100, 3) if prev else None,
             "partial": k == len(groups) - 1 and fri > c.dates[b]}
        prev = Cc[b]
        if not start or c.dates[b] >= iso(start):
            rows.append(r)
    return V(rows, None, T2, c.dates[-1], src, "giá FACT-T2; %chg EST; dòng tiền 4 kênh không có trong chuỗi", "điểm")


def index_weekly_spliced(idx: str = "VNINDEX", flows: bool = False) -> V:
    """Nối INDEX_DATA[<idx>_PL_W] của V21 (FiinTrade, ≤08/05/2026, giữ nguyên) với tuần sống sau mốc cuối.
    Hàng: {date, c, chg, ca, tc, td, nn, src 'V21'|'live'}; ca/tc tuần sống = None. flows=True → td/nn tuần
    sống = Σ rổ (EST, triệu cp, ghi độ phủ); ngược lại None."""
    from chaebol_map_data_dongtien import basket_weekly_flow   # nhập trễ: dongtien nhập gia
    live = index_weekly(idx)
    old = (v21_get("INDEX_DATA") or {}).get(f"{'VN30' if idx == 'VN30' else 'VNINDEX'}_PL_W") or []
    if not old:
        warn(f"v21 INDEX_DATA.{idx}_PL_W chưa có — chỉ trả tuần sống")
    rows = [{"date": r[0], "c": r[1], "chg": r[2], "ca": r[3], "tc": r[4], "td": r[5], "nn": r[6], "src": "V21"}
            for r in old]
    cut = rows[-1]["date"] if rows else ""
    prev = rows[-1]["c"] if rows else None
    fl = {}
    if flows and not live.can:
        bw = basket_weekly_flow("VN30" if idx == "VN30" else "VNINDEX", start=cut or None)
        fl = {r["monday"]: r for r in (bw.value or [])} if not bw.can else {}
    for r in (live.value or []) if not live.can else []:
        if r["date"] <= cut:
            continue
        f = fl.get(r["monday"]) or {}
        rows.append({"date": r["date"], "c": r["c"], "chg": round_half((r["c"] / prev - 1) * 100, 3) if prev else r["chg"],
                     "ca": None, "tc": None, "td": round_half(f["td_khop_vol"] / 1e6, 2) if _finite(f.get("td_khop_vol")) else None,
                     "nn": round_half(f["nn_vol"] / 1e6, 2) if _finite(f.get("nn_vol")) else None,
                     "src": "live", "partial": r["partial"]})
        prev = r["c"]
    note = (f"≤{ddmmyyyy(cut)}: FiinTrade (V21, FACT-T2 đóng băng) · sau đó: {live.src} (giá FACT-T2); "
            "ca/tc sau mốc [CẦN DATA]" + ("; td (khớp)/nn (khớp+TT) sau mốc = Σ rổ EST" if flows else "; td/nn sau mốc để trống"))
    return V(rows, None, T2, live.asof, "v21.INDEX_DATA + " + str(live.src), note, "điểm")


def index_extremes(idx: str = "VNINDEX", since="2026-05-08", end=None) -> dict:
    """Đỉnh đóng cửa trong [since, end], đáy sau đỉnh, cuối kỳ, % từ đỉnh/đáy (FACT-T2 / % EST)."""
    c, src = _index_cols(idx) if idx in ("VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX") else (price_history(idx), None)
    col = "c" if src else "closePriceAdjusted"
    src = src or _psrc(idx, col)
    if not c or not len(c):
        return {"peak": can_data(f"không có chuỗi {idx}")}
    a, b = bisect.bisect_left(c.dates, iso(since)), c.at(end)
    vals = c.col(col) if col == "c" else _adj_col(c, col)
    pts = [(x, c.dates[i]) for i, x in enumerate(vals[a:b + 1], a) if _finite(x)]
    if not pts:
        return {"peak": can_data(f"{idx}: không có phiên từ {ddmmyyyy(since)}")}
    pk = max(pts, key=lambda t: t[0])
    after = [p for p in pts if p[1] >= pk[1]]
    tr = min(after, key=lambda t: t[0])
    last = pts[-1]
    unit = "điểm" if col == "c" else "đ"
    mk = lambda p, g: V(p[0], js_locale(p[0], 2), T2, p[1], src, g, unit)  # noqa: E731
    return {"start": mk(pts[0], f"phiên đầu từ {ddmmyyyy(since)}"), "peak": mk(pk, "đỉnh đóng cửa"),
            "trough_after_peak": mk(tr, "đáy đóng cửa sau đỉnh"), "min": mk(min(pts, key=lambda t: t[0]), "đáy trong kỳ"),
            "last": mk(last, None),
            "from_peak": V((last[0] / pk[0] - 1) * 100, pct_text((last[0] / pk[0] - 1) * 100, 2), EST, last[1], src, None, "%"),
            "from_trough": V((last[0] / tr[0] - 1) * 100, pct_text((last[0] / tr[0] - 1) * 100, 2), EST, last[1], src, None, "%"),
            "since_start": V((last[0] / pts[0][0] - 1) * 100, pct_text((last[0] / pts[0][0] - 1) * 100, 2), EST, last[1], src, None, "%")}


def index_pe_pb(idx: str = "VNINDEX", d=None) -> dict:
    """P/E, P/B (x). Không d → lk_thitruong (kèm μ/σ/z EST); có d hoặc thiếu → vc_lk/VNINDEX/ratio-daily."""
    if idx != "VNINDEX":
        return {"pe": can_data(f"vc_lk không có ratio-daily cho {idx}"), "pb": can_data(f"không có P/B {idx}")}
    lt = read_json(bridge() / "data" / "lk_thitruong.json", quiet=True) or {}
    if d is None and lt.get("pe_vni"):
        out = {}
        for k in ("pe", "pb"):
            blk = lt.get(f"{k}_vni") or {}
            out[k] = lk_atom(blk.get("x"), f"lk_thitruong.{k}_vni.x")
            for s in ("mu", "sd", "z"):
                out[f"{k}_{s}"] = lk_atom(blk.get(s), f"lk_thitruong.{k}_vni.{s}")
        return out
    _, rows = vc("VNINDEX", "ratio-daily")
    if not isinstance(rows, list) or not rows:
        return {"pe": can_data("thiếu vc_lk/VNINDEX/ratio-daily"), "pb": can_data("thiếu ratio-daily")}
    seen, pts = set(), []
    for r in rows:
        t = iso(r.get("tradingDate"))
        if t not in seen:
            seen.add(t)
            pts.append((t, r))
    pts.sort(key=lambda t: t[0])
    i = bisect.bisect_right([t for t, _ in pts], iso(d) or "9999") - 1
    if i < 0:
        return {"pe": can_data("trước dòng đầu ratio-daily"), "pb": can_data("trước dòng đầu ratio-daily")}
    t, r = pts[i]
    return {k: V(r.get(k), js_fixed(r.get(k), 2) + "×" if _finite(r.get(k)) else CAN, T2, t,
                 f"vc_lk/VNINDEX/ratio-daily.{k}", "vendor trả trùng ngày → giữ dòng đầu", "x") for k in ("pe", "pb")}


def data_to() -> str | None:
    """Phiên cuối có dữ liệu toàn thị trường (VNINDEX)."""
    return index_close("VNINDEX").asof
