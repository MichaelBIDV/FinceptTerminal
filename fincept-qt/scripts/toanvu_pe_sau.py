#!/usr/bin/env python3
"""Lớp SÂU cho tab "Vùng P/E × Lãi suất · Toàn Vũ": trang rổ VNINDEX / VN30 / VN100 và phần mở rộng từng mã.

Chạy NGOÀI app (pandas), sau toanvu_pe_build.py (builder gọi build_sau() ở cuối; chạy riêng cũng được):
    python3 scripts/toanvu_pe_sau.py            # đọc cache Bloomberg + FiinProX như builder, tính lại luật TV

Ghi vào fincept_bridge/state/toanvu_pe/:
    ro/<VNINDEX|VN30|VN100>.json   hai báo cáo HTML của TV dựng lại cho từng rổ + bản kiểm định
    sau/<MÃ>.json                  pha giá (tách EPS × P/E), tần suất thắng có điều kiện, sự kiện chủ thể
    vimo.json                      lãi suất & chế độ tiền (WiChart, HNX, NHNN, bản tuần SGI)
    bang_chung.json                bảng tổng hợp bằng chứng (không phải khuyến nghị mua/bán)

Chỉ ĐỌC nguồn của hệ khác (vc_lk, WiData store, tpcp_vn, sgi_ky, hhp_*). Không gọi mạng.
"""
from __future__ import annotations

import csv
import json
import math
import sqlite3
import sys
import itertools
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import toanvu_pe_build as tb  # noqa: E402

SYS = tb.SYS_DIR
VC = SYS / "fincept_bridge" / "state" / "vc_lk"
FFT_TIN = SYS / "fincept_bridge" / "data" / "fft_tin.json"
WIDATA = SYS / "superdash_v2" / "output" / "widata_series_store.json"
TPCP = SYS / "fincept_bridge" / "data" / "tpcp_vn.json"
SBV_CSV = SYS / "knowledge_os" / "hhp_rates_sbv.csv"
SGI_DIR = SYS / "knowledge_os" / "sgi_ky"
HHP_DIR = SYS / "knowledge_os"

SCOPES = ("VNINDEX", "VN30", "VN100", "VN200", "REST")
UNIVERSE_JSON = SYS / "fa_insight" / "universe.json"   # top-200 vốn hoá HOSE+HNX (finfo), mktcap_rank 1..200
VIN = {"VIC", "VHM", "VRE", "VPL"}
PORTFOLIO = ["VCB", "FPT", "MSN", "ACB", "GAS", "HPG", "TCB", "CTG", "GEX", "VRE", "PLX"]  # danh mục tham chiếu 12/09
TV_WATCH = ["MWG", "VPB", "HDB", "STB", "GEE", "HAH", "PVT", "PVP", "FRT"]
PB_SECTORS = {"Ngân hàng", "Bất động sản", "Dịch vụ tài chính", "Bảo hiểm", "Tài nguyên Cơ bản", "Hóa chất", "Dầu khí"}
ZIGZAG = 0.25        # pha giá: đảo chiều ≥ 25% từ cực trị (tuần)
SHRINK_M = 8         # co tần suất của mã về tần suất gộp rổ: (k + m·p0)/(n + m)
ERP_ZONES = [("≥ +5", 5, 99), ("+2 → +5", 2, 5), ("0 → +2", 0, 2), ("−3 → 0", -3, 0), ("< −3", -99, -3)]
LS_LEVELS = [("LS < 6%", 0, 6), ("6–8%", 6, 8), ("8–10%", 8, 10), ("> 10%", 10, 99)]
HIST_PHASES = [  # 7 giai đoạn của Chart ② (nhãn TV), dùng làm dải nền
    ("2008-01-01", "2009-06-30", "GĐ1 · khủng hoảng, LS 18%"), ("2010-01-01", "2012-06-30", "GĐ2 · LS 10–13%, ERP ≈ 0"),
    ("2013-01-01", "2017-12-31", "GĐ3 · LS hạ dần, P/E mở rộng"), ("2018-06-01", "2020-02-29", "GĐ4 · ERP thu hẹp"),
    ("2020-03-01", "2021-12-31", "GĐ5 · LS 6%, sóng COVID"), ("2022-01-01", "2023-12-31", "GĐ6 · LS tăng lại 9%"),
    ("2024-01-01", "2026-12-31", "GĐ7 · LS 7,6%, P/E 9–10x")]


def log(*a):
    tb.log(*a)


def f(x, nd=2):
    return tb.r2(x, nd)


def vnum(x, nd=1, sign=False) -> str:
    """Số kiểu Việt: phẩy thập phân, chấm hàng nghìn, dấu trừ U+2212."""
    if x is None or not np.isfinite(x):
        return "n/a"
    t = f"{abs(x):,.{nd}f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return ("\u2212" if x < 0 and round(abs(x), nd) > 0 else ("+" if sign and x > 0 else "")) + t


def ms(d) -> int:
    return int(pd.Timestamp(d).value // 1_000_000)


def iso(d) -> str:
    return pd.Timestamp(d).strftime("%Y-%m-%d")


def read_json(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def vc_rows(tk: str, ep: str) -> list:
    """vc_lk/<TK>/<ep>.json → list of dicts (dạng 'ban_ghi' hoặc 'cot'/'hang')."""
    d = read_json(VC / tk / f"{ep}.json")
    if not d:
        return []
    dl = d.get("du_lieu", d)
    if isinstance(dl, dict) and "cot" in dl:
        return [dict(zip(dl["cot"], r)) for r in dl.get("hang", [])]
    if isinstance(dl, dict):
        return [dl]
    return dl if isinstance(dl, list) else []


def wilson(k, n, z=1.645):
    if not n:
        return None, None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return round(100 * (c - h), 1), round(100 * (c + h), 1)


# ── vũ trụ ────────────────────────────────────────────────────────────────────

def load_universe(bbg_tickers: set) -> dict:
    con = sqlite3.connect(f"file:{tb.VNSTORE}?mode=ro", uri=True)
    rows = con.execute("select symbol, nhom, nganh from ma").fetchall()
    con.close()
    vn30 = sorted(s for s, n, _ in rows if n and "VN30" in n.split(","))
    vn100 = sorted(s for s, n, _ in rows if n and "VN100" in n.split(","))
    u = (read_json(UNIVERSE_JSON) or {}).get("tickers") or {}
    vn200 = sorted(k for k, v in u.items() if isinstance(v, dict) and (v.get("mktcap_rank") or 10**9) <= 200)
    if len(vn200) < 150:  # tệp vũ trụ hỏng/thiếu: VN200 ít nhất phải chứa VN100
        vn200 = sorted(set(vn200) | set(vn100))
    # REST = mọi mã có dữ liệu trong tệp Bloomberg nằm ngoài VN200 (VN200 ∪ REST = toàn bộ tệp Bloomberg)
    rest = sorted(set(bbg_tickers) - set(vn200))
    return {"VNINDEX": sorted(bbg_tickers), "VN30": vn30, "VN100": vn100, "VN200": vn200, "REST": rest}


def sector_of(tk: str) -> str | None:
    d = vc_rows(tk, "details")
    return (d[0].get("sectorVn") if d else None) or None


# ── chỉ số & P/E rổ ───────────────────────────────────────────────────────────

def vnindex_close() -> pd.Series:
    rows = vc_rows("VNINDEX", "gap-chart")
    s = pd.Series({pd.Timestamp(r["tradingDate"]): r["c"] for r in rows if r.get("c")}).sort_index()
    return s[~s.index.duplicated()]


def wide_frames(d: pd.DataFrame, cols) -> list:
    """Bảng ngày × mã dựng bằng numpy: pivot_table/unstack trên pandas 2.3 + py3.14 trả chỉ mục ngày hỏng
    (ngày lặp, sai thứ tự), cùng họ lỗi với sort_values đã gặp ở builder."""
    dv = d.date.to_numpy(dtype="datetime64[ns]")
    days, di = np.unique(dv, return_inverse=True)
    tks, ti = np.unique(d.tk.to_numpy(dtype=str), return_inverse=True)
    idx = pd.DatetimeIndex(days, name="date")
    out = []
    for c in cols:
        m = np.full((len(days), len(tks)), np.nan)
        m[di, ti] = d[c].to_numpy(dtype=float)
        out.append(pd.DataFrame(m, index=idx, columns=list(tks)))
    return out


def scope_frame(df: pd.DataFrame, members: list, ls: pd.Series, idx_close: pd.Series | None) -> pd.DataFrame:
    """P/E gộp điều hoà theo vốn hoá (3 biến thể), chỉ số rổ và ERP, theo ngày."""
    pe, mc, px = wide_frames(df[df.tk.isin(members)], ("pe", "mcap", "px"))
    ok = (pe > 0) & mc.notna()

    def harm(mask):
        m = mc.where(mask)
        return m.sum(axis=1) / (m / pe).where(mask).sum(axis=1)

    out = pd.DataFrame(index=pe.index)
    out["pe_tv"] = harm(ok & (pe <= 40))
    out["pe_all"] = harm(ok)
    vin_cols = [c for c in pe.columns if c in VIN]
    if vin_cols:
        mask = ok.copy()
        mask[vin_cols] = False
        out["pe_exvin"] = harm(mask)
    else:
        out["pe_exvin"] = out["pe_all"]
    out["n_ma"] = ok.sum(axis=1)
    if idx_close is not None:
        out["idx"] = idx_close.reindex(out.index)
    else:  # chỉ số vốn hoá dựng từ thành viên hiện tại (thiên lệch sống sót: ghi rõ ở trang)
        r = px.pct_change(fill_method=None)
        r = r.where(r.abs() < 0.2)
        w = mc.shift(1)
        w = w.where(r.notna())
        ret = (r * w).sum(axis=1) / w.sum(axis=1)
        out["idx"] = 100 * (1 + ret.fillna(0)).cumprod()
    lsd = ls.reindex(pd.date_range(ls.index[0], max(ls.index[-1], out.index[-1])), method="ffill")
    out["ls"] = lsd.reindex(out.index).to_numpy()
    out.loc[out.index < ls.index[0], "ls"] = np.nan
    for k in ("tv", "all", "exvin"):
        out[f"erp_{k}"] = 100.0 / out[f"pe_{k}"] - out.ls
    out["pe_fair"] = 100.0 / out.ls
    idxff = out.idx.ffill()
    for h in (60, 120):
        out[f"r{h}"] = (idxff.shift(-h) / out.idx - 1) * 100
    out["dls6m"] = np.round((lsd - lsd.shift(182)).reindex(out.index).to_numpy(), 4)
    return out


def weekly(s: pd.DataFrame, cols, since="2008-03-01") -> dict:
    src = s[s.index >= since]
    w = src[cols].resample("W-FRI").last().dropna(how="all")
    xs = [iso(d) for d in w.index]
    if xs and len(src):
        xs[-1] = min(xs[-1], iso(src.index[-1]))   # tuần dở: nhãn W-FRI là ngày tương lai → dùng phiên thật cuối
    return {"x": xs, **{c: [f(v, 3) if pd.notna(v) else None for v in w[c]] for c in cols}}


def zone_table(sf: pd.DataFrame, col: str) -> list:
    out = []
    base = sf[sf[col].notna() & sf.r60.notna()]
    for name, lo, hi in ERP_ZONES:
        z = base[(base[col] >= lo) & (base[col] < hi)]
        z120 = z[z.r120.notna()]
        if not len(z):
            out.append({"vung": name, "n_ngay": 0})
            continue
        # số khối 60 phiên độc lập: tham lam, cách ≥ 60 phiên giao dịch
        pos = np.flatnonzero(base.index.isin(z.index))
        k, last = 0, -10**9
        for p_ in pos:
            if p_ - last >= 60:
                k, last = k + 1, p_
        out.append({"vung": name, "n_ngay": int(len(z)), "n_doc_lap": k, "hit60": f(100 * (z.r60 > 0).mean(), 1),
                    "r60": f(z.r60.mean(), 2), "r60_tv": f(z.r60.median(), 2),
                    "hit120": f(100 * (z120.r120 > 0).mean(), 1) if len(z120) else None,
                    "r120": f(z120.r120.mean(), 2) if len(z120) else None})
    return out


def bins_curve(x: np.ndarray, y60: np.ndarray, y120: np.ndarray, edges: np.ndarray, sigma=1.5, min_n=200) -> dict:
    """Bins theo mức X → TB r60/r120, hit 60/120, n; làm mịn Gauss có trọng số n (như Chart ① của TV)."""
    centers = (edges[:-1] + edges[1:]) / 2
    k = np.digitize(x, edges) - 1
    rows = []
    for i in range(len(centers)):
        m = k == i
        n = int(m.sum())
        a60, a120 = y60[m], y120[m]
        a120 = a120[np.isfinite(a120)]
        rows.append((n, np.nanmean(a60) if n else np.nan, np.nanmean(a120) if len(a120) else np.nan,
                     100 * np.mean(a60 > 0) if n else np.nan, 100 * np.mean(a120 > 0) if len(a120) else np.nan))
    arr = np.array(rows, dtype=float)
    n = arr[:, 0]

    def smooth(col):
        v = arr[:, col]
        ok = np.isfinite(v) & (n >= min_n)
        out = []
        for c in centers:
            w = np.exp(-0.5 * ((centers - c) / (sigma * (edges[1] - edges[0]))) ** 2) * n * ok
            out.append(float(np.nansum(w * np.where(ok, v, 0)) / w.sum()) if w.sum() > 0 else None)
        return [f(v, 2) if v is not None and np.isfinite(v) else None for v in out]

    return {"x": [f(c, 2) for c in centers], "n": [int(v) for v in n],
            "r60": smooth(1), "r120": smooth(2), "hit60": smooth(3), "hit120": smooth(4),
            "r60_tho": [f(v, 2) if np.isfinite(v) else None for v in arr[:, 1]]}


# ── thống kê thành viên rổ ────────────────────────────────────────────────────

def member_stats(a: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for tk, g in a.groupby("tk", sort=True):
        e = g[g.ls.notna() & g.pct.notna() & g.r60.notna()]
        s = e[e.sig]
        e45 = g[g.ls.notna() & g.pct45.notna() & g.r60.notna()]
        s45 = e45[e45.sig45]
        rows.append({"ma": tk, "n_sig": len(s), "hit_sig": 100 * (s.r60 > 0).mean() if len(s) else np.nan,
                     "r_sig": s.r60.mean() if len(s) else np.nan, "r_base": e.r60.mean() if len(e) else np.nan,
                     "r120_sig": s.r120.mean() if len(s) else np.nan,
                     "alpha": (s.r60.mean() - e.r60.mean()) if len(s) and len(e) else np.nan,
                     "xs_sig": s.xs60.mean() if len(s) else np.nan,
                     "n45": len(s45), "hit45": 100 * (s45.r60 > 0).mean() if len(s45) else np.nan,
                     "alpha45": (s45.r60.mean() - e45.r60.mean()) if len(s45) and len(e45) else np.nan})
    return pd.DataFrame(rows).set_index("ma")


def regime_tables(a: pd.DataFrame) -> dict:
    e = a[a.ls.notna() & a.pct.notna() & a.r60.notna()]
    lv, dr = [], []
    for name, lo, hi in LS_LEVELS:
        z = e[(e.ls >= lo) & (e.ls < hi)]
        s = z[z.sig]
        s45 = z[z.sig45 & z.pct45.notna()]
        s120 = s[s.r120.notna()]
        lv.append({"vung": name, "n": int(len(s)), "r60": f(s.r60.mean()), "r120": f(s120.r120.mean()) if len(s120) else None,
                   "hit": f(100 * (s.r60 > 0).mean(), 1) if len(s) else None, "r60_moi_ngay": f(z.r60.mean()),
                   "r60_45": f(s45.r60.mean()) if len(s45) else None, "xs": f(s.xs60.mean()) if len(s) else None})
    for name in ("giảm mạnh", "giảm", "đi ngang", "tăng", "tăng mạnh"):
        z = e[e.dls6m.map(tb.bucket_dir) == name]
        s = z[z.sig]
        dr.append({"huong": name, "n": int(len(s)), "r60": f(s.r60.mean()) if len(s) else None,
                   "hit": f(100 * (s.r60 > 0).mean(), 1) if len(s) else None, "r60_moi_ngay": f(z.r60.mean()) if len(z) else None,
                   "xs": f(s.xs60.mean()) if len(s) else None})
    return {"muc_ls": lv, "huong_ls": dr}


def scope_payload(code, members, df, a, ls, idx_close, ov_rows, mstat, last_full, hhp_b, hhp_core, ev_rows) -> dict:
    sf = scope_frame(df[df.date <= last_full], members, ls, idx_close)
    am = a[a.tk.isin(members)]
    cur = sf[sf.pe_tv.notna()].iloc[-1]
    lsn = float(cur.ls)
    # Chart ① cổ phiếu (gộp mọi mã của rổ, như TV) + bản trễ EPS 45 ngày
    base = am[am.pe.notna() & am.r60.notna() & (am.pe > 0)]
    edges = np.arange(1.5, 41.5, 1.0)
    c1 = bins_curve(base.pe.to_numpy(), base.r60.to_numpy(), base.r120.to_numpy(), edges)
    b45 = am[am.pe45.notna() & am.r60.notna() & (am.pe45 > 0)]
    c45 = bins_curve(b45.pe45.to_numpy(), b45.r60.to_numpy(), b45.r120.to_numpy(), edges)
    bx = base[base.xs60.notna()]
    cxs = bins_curve(bx.pe.to_numpy(), bx.xs60.to_numpy(), bx.xs60.to_numpy(), edges)
    # Chart ① cấp rổ: P/E gộp → lợi suất chỉ số
    sr = sf[sf.pe_tv.notna() & sf.r60.notna()]
    e2 = np.arange(np.floor(sr.pe_tv.quantile(0.01)), np.ceil(sr.pe_tv.quantile(0.99)) + 1, 1.0)
    c_ro = bins_curve(sr.pe_tv.to_numpy(), sr.r60.to_numpy(), sr.r120.to_numpy(), e2, sigma=1.0, min_n=20) if len(e2) > 2 else None
    # xếp hạng & danh sách
    rows = [r for r in ov_rows if r["ma"] in set(members)]
    ms_ = mstat.reindex([r["ma"] for r in rows])
    for r in rows:
        m = ms_.loc[r["ma"]] if r["ma"] in ms_.index else None
        for k in ("r_sig", "r_base", "alpha", "hit_sig", "alpha45", "hit45", "n45", "xs_sig", "r120_sig"):
            r[k] = f(m[k]) if m is not None and pd.notna(m[k]) else None
    watch = [t for t in PORTFOLIO + TV_WATCH if t in set(members)]
    hhp = None
    if hhp_b:
        hhp = {k: hhp_b.get(k) for k in ("code", "label")}
        for met in ("pe", "pb"):
            b = hhp_b.get(met) or {}
            ser = b.get("series") or []
            hhp[met] = {k: b.get(k) for k in ("now", "mean", "m1", "m2", "p1", "p2", "sigma", "zone", "as_of")}
            hhp[met]["chuoi"] = {"x": [p[0] for p in ser], "y": [p[1] for p in ser]}
        if code == "VNINDEX" and hhp_core:
            ex = hhp_core.get("exvic3") or {}
            hhp["exvic3"] = {k: ex.get(k) for k in ("pe_exv3_now", "exv3_pe_sigma", "exv3_pe_mean", "exv3_pe_sd", "zone") if k in ex}
            ser = (ex.get("series") or {}).get("pe_exv3") or []
            hhp["exvic3"]["chuoi"] = {"x": [p[0] for p in ser[::5]], "y": [p[1] for p in ser[::5]]}
    pe_mem = ev_rows
    return {
        "ro": code, "so_ma": len(members), "so_ma_bbg": int(am.tk.nunique()),
        "thieu_bbg": sorted(set(members) - set(am.tk.unique())),
        "phien": iso(last_full), "chi_so_nguon": "VN-Index thật (Vietcap gap-chart)" if idx_close is not None
        else f"chỉ số vốn hoá dựng từ {am.tk.nunique()} thành viên hiện tại (thiên lệch sống sót)",
        "hien_tai": {"ngay": iso(sf[sf.pe_tv.notna()].index[-1]), "pe_tv": f(cur.pe_tv), "pe_all": f(cur.pe_all),
                     "pe_exvin": f(cur.pe_exvin), "ls": f(lsn), "pe_fair": f(100 / lsn), "ey_tv": f(100 / cur.pe_tv),
                     "erp_tv": f(cur.erp_tv), "erp_all": f(cur.erp_all), "erp_exvin": f(cur.erp_exvin),
                     "re_hon_fair_pct": f(100 * (1 - cur.pe_tv / (100 / lsn)), 1), "n_ma": int(cur.n_ma),
                     "dls6m": f(cur.dls6m), "nguong": f(float(tb.thr_tv(lsn)), 1)},
        "chuoi": weekly(sf, ["pe_tv", "pe_all", "pe_exvin", "pe_fair", "ls", "erp_tv", "erp_all", "erp_exvin", "idx"]),
        "erp_vung": {"tv": zone_table(sf, "erp_tv"), "all": zone_table(sf, "erp_all"), "exvin": zone_table(sf, "erp_exvin")},
        "chart1": {"cp": c1, "cp45": c45, "cp_xs": cxs, "ro": c_ro},
        "regime": regime_tables(am),
        "xep_hang": rows, "watch": watch, "hhp": hhp, "bang_chung": pe_mem,
        "giai_doan": [{"tu": a_, "den": b_, "nhan": n_} for a_, b_, n_ in HIST_PHASES],
    }


# ── pha giá từng mã ───────────────────────────────────────────────────────────

def zigzag(px: pd.Series, th=ZIGZAG) -> list:
    v = px.dropna()
    if len(v) < 10:
        return []
    piv = [(v.index[0], v.iloc[0])]
    hi = lo = (v.index[0], v.iloc[0])
    trend = 0
    for d, p in v.iloc[1:].items():
        if trend >= 0 and p > hi[1]:
            hi = (d, p)
        if trend <= 0 and p < lo[1]:
            lo = (d, p)
        if trend >= 0 and p <= hi[1] * (1 - th) and hi[0] != piv[-1][0]:
            piv.append(hi)
            trend, lo = -1, (d, p)
        elif trend <= 0 and p >= lo[1] * (1 + th) and lo[0] != piv[-1][0]:
            piv.append(lo)
            trend, hi = 1, (d, p)
    last = v.index[-1], v.iloc[-1]
    if last[0] != piv[-1][0]:
        piv.append(last)
    return piv


def near_val(s: pd.Series, d, tol_days=21):
    w = s.dropna()
    if w.empty:
        return None
    i = w.index.get_indexer([d], method="nearest")[0]
    return float(w.iloc[i]) if abs((w.index[i] - d).days) <= tol_days else None


def phases(g: pd.DataFrame, ls_daily: pd.Series, vni: pd.Series, ins: list, iss: list, shares) -> list:
    gi = g.set_index("date")
    w = gi[["px", "pe"]].resample("W-FRI").last()
    real = gi.assign(dd=g.date.to_numpy()).dd.resample("W-FRI").last()  # nhãn tuần → phiên giao dịch thật cuối tuần
    eps = (w.px / w.pe).where(w.pe > 0)
    piv = [(pd.Timestamp(real.get(d, d)), p) for d, p in zigzag(w.px)]
    w.index = pd.DatetimeIndex([real.get(d, d) for d in w.index])
    eps.index = w.index
    out = []
    for i in range(1, len(piv)):
        (d0, p0), (d1, p1) = piv[i - 1], piv[i]
        e0, e1 = near_val(eps, d0), near_val(eps, d1)
        pe0, pe1 = near_val(w.pe, d0), near_val(w.pe, d1)
        r = (p1 / p0 - 1) * 100
        ph = {"tu": iso(d0), "den": iso(d1), "dang_chay": i == len(piv) - 1, "px0": f(p0, 0), "px1": f(p1, 0), "r": f(r, 1),
              "tuan": int((d1 - d0).days // 7), "pe0": f(pe0, 1), "pe1": f(pe1, 1)}
        if e0 and e1 and e0 > 0 and e1 > 0 and p0 > 0 and p1 > 0 and abs(math.log(p1 / p0)) > 0.05:
            le, lp = math.log(e1 / e0), math.log(p1 / p0)
            ph.update({"eps_pct": f((e1 / e0 - 1) * 100, 1), "pe_pct": f(((p1 / e1) / (p0 / e0) - 1) * 100, 1),
                       "phan_eps": f(100 * le / lp, 0), "phan_pe": f(100 * (lp - le) / lp, 0)})
            up = lp > 0
            sh = le / lp
            ph["kieu"] = (("Tăng nhờ lợi nhuận" if sh >= 0.6 else "Tăng nhờ mở rộng P/E" if sh <= 0.4 else "Tăng nhờ cả hai")
                          if up else
                          ("Giảm do lợi nhuận đi xuống" if sh >= 0.6 else "Giảm do co P/E" if sh <= 0.4 else "Giảm do cả hai"))
        elif e0 and e1 and e0 > 0 and e1 > 0 and p0 > 0 and p1 > 0:
            # giá đổi < 5% (pha đang chạy): tỷ phần ln(EPS)/ln(giá) bùng nổ khi mẫu số ≈ 0 → không chia tỷ phần
            ph.update({"eps_pct": f((e1 / e0 - 1) * 100, 1), "pe_pct": f(((p1 / e1) / (p0 / e0) - 1) * 100, 1)})
            ph["kieu"] = "Đi ngang (giá đổi < 5%)"
        else:
            ph["kieu"] = "Không tách được (lỗ hoặc thiếu P/E)"
        l0, l1 = near_val(ls_daily, d0, 45), near_val(ls_daily, d1, 45)
        ph["ls0"], ph["ls1"] = f(l0), f(l1)
        v0, v1 = near_val(vni, d0, 7), near_val(vni, d1, 7)
        if v0 and v1:
            ph["vni_r"] = f((v1 / v0 - 1) * 100, 1)
            ph["vuot_vni"] = f(r - ph["vni_r"], 1)
        mua = sum(x["kl"] for x in ins if d0 < x["d"] <= d1 and x["kl"] > 0 and not x.get("nguon"))
        quyen = sum(x["kl"] for x in ins if d0 < x["d"] <= d1 and x["kl"] > 0 and x.get("nguon") in ISSUE_TAGS)
        ban = -sum(x["kl"] for x in ins if d0 < x["d"] <= d1 and x["kl"] < 0 and not x.get("nguon"))
        ph["noi_bo"] = {"mua": int(mua), "ban": int(ban), "quyen_esop": int(quyen), "rong_pct_cp": f(100 * (mua - ban) / shares, 2) if shares else None,
                        "lon_nhat": max(([x for x in ins if d0 < x["d"] <= d1 and not x.get("nguon")]), key=lambda x: abs(x["kl"]), default=None)}
        if ph["noi_bo"]["lon_nhat"]:
            x = ph["noi_bo"]["lon_nhat"]
            ph["noi_bo"]["lon_nhat"] = {"ngay": iso(x["d"]), "ten": x["ten"], "vai": x["vai"], "kl": int(x["kl"])}
        ph["phat_hanh"] = [{"ngay": iso(x["d"]), "loai": x["loai"], "ty_le": x["ty_le"], "tieu_de": x["tieu_de"]}
                           for x in iss if d0 < x["d"] <= d1][:6]
        out.append(ph)
    return out


ISSUE_TAGS = ("quyền mua", "ESOP", "trùng đợt phát hành?")   # nguon = nhận qua phát hành; "chuyển nội bộ…" = loại vì trùng đối ứng


def vc_price_map(tk: str) -> dict:
    """ngày ISO → (KL khớp, KL thoả thuận, GT thoả thuận, giá đóng cửa, tổng số cp) từ price-history Vietcap."""
    out = {}
    for r in vc_rows(tk, "price-history"):
        d = (r.get("tradingDate") or "")[:10]
        if d:
            out[d] = (float(r.get("totalMatchVolume") or 0), float(r.get("totalDealVolume") or 0),
                      float(r.get("totalDealValue") or 0), float(r.get("closePrice") or 0), float(r.get("totalShares") or 0))
    return out


def share_events(tk: str) -> list:
    """Thưởng / cổ tức cp / quyền mua làm đổi số cp người nắm giữ (events-v2 + events-all). events-all không có
    exerciseRatio thì đọc "tỉ lệ x%" trong tiêu đề."""
    out, seen = [], set()
    for ep in ("events-v2", "events-all"):
        for r in vc_rows(tk, ep):
            if r.get("eventCode") != "ISS":
                continue
            d = (r.get("exrightDate") or r.get("issueDate") or r.get("publicDate") or "")[:10]
            t = (r.get("eventTitleVi") or "").lower()
            ratio = r.get("exerciseRatio")
            if ratio is None:
                m = re.search(r"t[ỉỷ] l[ệe]\s*([0-9]+(?:[.,][0-9]+)?)\s*%", t)
                ratio = float(m.group(1).replace(",", ".")) / 100 if m else None
            if not d or not ratio:
                continue
            kind = ("thuong" if ("thưởng" in t or "cổ tức bằng cổ phiếu" in t or "nguồn vốn chủ" in t)
                    else "quyen" if ("quyền mua" in t or "hiện hữu" in t) else None)
            if kind and (d, round(float(ratio), 5), kind) not in seen:
                seen.add((d, round(float(ratio), 5), kind))
                out.append({"d": d, "r": float(ratio), "kind": kind})
    return sorted(out, key=lambda x: x["d"])


def deal_label(px: dict, start: str, end: str, k: float, k_group: float, used: dict) -> tuple:
    """Phương thức suy từ price-history (theo NGÀY, không theo lệnh), xét lần lượt:
    (1) phiên hoàn tất có KL thoả thuận đúng bằng tổng các lệnh cùng ngày cùng chiều, hoặc phần thoả thuận CHƯA gán cho
        lệnh khác đúng bằng KL lệnh (±0,5%) → "thoả thuận", giá = bình quân thoả thuận của phiên;
    (2) KL lệnh > 1,05 × KL khớp của cả cửa sổ (không thể đi qua khớp lệnh) và thoả thuận của cửa sổ phủ ≥ 95% KL lệnh
        → "thoả thuận" (nhiều phiên), giá = ΣGT/ΣKL thoả thuận cửa sổ;
    (3) KL lệnh > 1,05 × (khớp + thoả thuận) của cửa sổ và của 5 phiên tới ngày hoàn tất → "ngoài sàn";
    (4) KL lệnh ≤ KL khớp của cửa sổ → "khớp lệnh" (suy ra, có thể lẫn thoả thuận nhỏ); còn lại None = chưa rõ."""
    if not px or not end:
        return None, None
    if not start or start > end or (pd.Timestamp(end) - pd.Timestamp(start)).days > 62:
        start = end
    days = [d for d in sorted(px) if start <= d <= end]
    if not days:
        return None, None
    if end in px and px[end][1] > 0:
        dv = px[end][1]
        if abs(dv - k_group) <= max(0.005 * k_group, 100):
            return "thoả thuận", round(px[end][2] / dv)
        if abs(dv - used.get(end, 0.0) - k) <= max(0.005 * k, 100):
            used[end] = used.get(end, 0.0) + k
            return "thoả thuận", round(px[end][2] / dv)
    M, D, V = (sum(px[d][j] for d in days) for j in (0, 1, 2))
    if k > 1.05 * M and D >= 0.95 * k:
        return "thoả thuận", round(V / D)
    allp = sorted(px)
    i = allp.index(days[-1])
    cap5 = sum(px[d][0] + px[d][1] for d in allp[max(0, i - 4): i + 1])
    if k > 1.05 * (M + D) and k > 1.05 * cap5:
        return "ngoài sàn", None
    return ("khớp lệnh", None) if k <= M else (None, None)


def chain_rows(ins: list, tk: str, shares, px: dict, cut) -> list:
    """Biến động KHÔNG khai báo giữa hai lệnh liên tiếp của cùng chủ thể (shareBefore lệnh sau ≠ shareAfter lệnh trước).
    Một khoảng là "chắc" khi: dài ≤ 365 ngày; không có ngày nào của sự kiện vốn ISS/AIS (GDKHQ, phát hành, niêm yết,
    công bố) chen giữa; số cp lưu hành không tăng trong khoảng; không dòng nào khác của chủ thể nối được vào hai đầu
    (dòng ghi sai ngày); tỷ lệ sở hữu sau giao dịch của cả hai dòng khớp số cp ±3%. Khoảng có |chênh| < 0,01% số cp
    hoặc hai cửa sổ chồng nhau thì bỏ qua. Trong cửa sổ 12 tháng, một chủ thể chỉ được cộng chuỗi khi MỌI khoảng đáng kể
    của nó đều chắc (tránh lệch một chiều); ngoài cửa sổ chỉ hiển thị khoảng chắc. Dòng "CHUOI" ghi ở ngày đầu khoảng."""
    if not shares:
        return []
    any_ev = {(r.get(k) or "")[:10] for ep in ("events-v2", "events-all") for r in vc_rows(tk, ep)
              if r.get("eventCode") in ("ISS", "AIS") for k in ("exrightDate", "issueDate", "listingDate", "publicDate", "recordDate")}
    any_ev = (any_ev | {e["d"] for e in share_events(tk)}) - {""}
    days = sorted(px)

    def tong_cp(d):  # số cp lưu hành gần nhất tại/ trước ngày d
        j = next((i for i in range(len(days) - 1, -1, -1) if days[i] <= d), None)
        return px[days[j]][4] if j is not None else 0

    def own_ok(y):
        sh = tong_cp(iso(y["d"])) or shares
        o, a = y.get("_own"), float(y["_aft"])
        return bool(o) and a > 0 and abs(o * sh - a) <= 0.03 * a

    # quỹ báo cáo theo nhóm (≥ 50% số lần công bố trùng ngày với tổ chức khác, kiểu Dragon Capital ở DXG):
    # điều chuyển giữa các quỹ trong nhóm có thể hiện thành khoảng hụt → vẫn tính, nhưng ghi rõ để người đọc chiết khấu
    pub = {}
    for r in vc_rows(tk, "insider-transaction"):
        if r.get("traderOrganNameVi") and r.get("publicDate"):
            pub.setdefault(r["publicDate"][:10], set()).add(r["traderOrganNameVi"])
    nhom = set()
    for o in {o for s in pub.values() for o in s}:
        ds = [d for d, s in pub.items() if o in s]
        if sum(len(pub[d]) >= 2 for d in ds) >= 0.5 * len(ds):
            nhom.add(o)
    by = {}
    for x in ins:
        if x["code"] != "CHUOI" and x.get("_bef") is not None and x.get("_aft") is not None and x["ten"]:
            by.setdefault(x["ten"], []).append(x)
    out = []
    for ten, xs in by.items():
        xs = sorted(xs, key=lambda x: (x["d"], float(x["_bef"])))
        gaps = []
        for a, b in zip(xs, xs[1:]):
            prev, cur = float(a["_aft"]), float(b["_bef"])
            g = cur - prev
            if (cur == 0 and prev > 0) or abs(g) <= max(1000, 0.005 * max(prev, 1)) or abs(g) < 0.0001 * shares:
                continue
            a0, b0 = a.get("_start") or iso(a["d"]), iso(b["d"])
            ref = b["_start"] if b.get("_start") and b["_start"] <= b0 else b0
            if ref < iso(a["d"]):
                continue  # hai cửa sổ chồng nhau: không so được
            vals = [float(v) for y in xs if y is not a and y is not b and abs((y["d"] - b["d"]).days) <= 730
                    for v in (y["_bef"], y["_aft"]) if v]
            ta, tb = tong_cp(iso(a["d"])), tong_cp(b0)
            chac = ((b["d"] - a["d"]).days <= 365 and not any(a0 <= e <= b0 for e in any_ev)
                    and not (ta and tb and tb > 1.001 * ta)
                    and not any(abs(v - cur) <= 1 or abs(v - prev) <= 1 for v in vals if v > 0)
                    and own_ok(a) and own_ok(b))
            gaps.append((a, b, g, chac, cur / (tb or shares)))
        trong = [x for x in gaps if x[0]["d"] >= cut]
        giu = [x for x in gaps if x[0]["d"] < cut and x[3]] + (trong if all(x[3] for x in trong) else [])
        for a, b, g, _, own_b in giu:
            out.append({"d": a["d"], "den": iso(b["d"]), "kl": float(g), "ten": ten, "vai": b["vai"], "lq": b["lq"], "code": "CHUOI",
                        "sau_pct": own_b, "nguon": None, "gia_tt": None,
                        "pt": "không khai báo (chuỗi số dư" + (", nhóm quỹ báo cáo chung" if ten in nhom else "") + ")"})
    return out


def insider_rows(tk: str, iss: list, shares=None, cut=None) -> list:
    """Giao dịch nội bộ đã thực hiện. Khử dòng lặp (Vietcap phân trang trùng): khoá theo tên người HOẶC tổ chức
    (traderNameVi của tổ chức là None), thêm khoá phụ (KL, ngày, cp trước, cp sau) cho tên khác cách đặt dấu.
    Gắn "nguon" (loại khỏi ròng) cho lệnh mua nhận qua phát hành:
      • KL = cp trước giao dịch × tỷ lệ quyền, từ 30 ngày trước tới 150 ngày sau ngày đợt → "quyền mua";
      các nhãn dưới chỉ xét ±60 ngày quanh đợt:
      • đợt ESOP → "ESOP", chỉ với cá nhân (tổ chức không nhận cp ESOP);
      • đợt chào bán/phát hành khác → "trùng đợt phát hành?", trừ lệnh hoàn tất sớm hơn ngày đợt quá 3 ngày;
      • không gắn khi lệnh ≥ 0,1% số cp đi qua thoả thuận (cp phát hành không qua thoả thuận) hoặc KL > 1,05 × quy mô đợt.
    Lệnh khối (thoả thuận, ngoài sàn) VẪN tính vào ròng (thay đổi sở hữu thật), chỉ gắn "pt" và "gia_tt". Riêng lệnh
    ≥ 1% số cp có chân đối ứng của người nội bộ khác còn ở trạng thái Đăng ký CHƯA có kết quả (tổng khớp ±2%, cửa sổ
    phủ ngày lệnh ±3 ngày) → "chuyển nội bộ" và loại, vì chân kia chưa vào ròng; khi chân kia báo kết quả thì cả hai
    chân cùng được tính và tự triệt tiêu. Thêm dòng "CHUOI" cho biến động không khai báo (chain_rows)."""
    raw = vc_rows(tk, "insider-transaction")
    px = vc_price_map(tk)
    cut = cut if cut is not None else pd.Timestamp.max
    out, seen, seen2 = [], set(), set()
    ev = [x for x in iss if x["loai"] in ("ESOP", "chào bán", "phát hành khác")]
    for r in raw:
        kl = r.get("shareAcquire") or 0
        st = (r.get("tradeStatusEn") or "").lower()
        if not kl or "registration" in st or "fail" in st:
            continue
        ds = (r.get("endDate") or r.get("publicDate") or "")[:10]
        if not ds:
            continue
        ten = r.get("traderNameVi") or r.get("traderOrganNameVi") or ""
        key = (ten, float(kl), ds)
        bef, aft = r.get("shareBeforeTrade"), r.get("shareAfterTrade")
        key2 = (float(kl), ds, bef, aft) if bef and aft else None
        if key in seen or (key2 and key2 in seen2):
            continue
        seen.add(key)
        if key2:
            seen2.add(key2)
        out.append({"d": pd.Timestamp(ds), "kl": float(kl), "ten": ten, "vai": r.get("traderPositionVi") or r.get("roleNameVi") or "",
                    "lq": r.get("relativeNameVi") or "", "code": r.get("eventCode"), "sau_pct": r.get("ownershipAfterTrade"), "nguon": None,
                    "_bef": bef, "_aft": aft, "_own": r.get("ownershipAfterTrade"), "_ca_nhan": bool(r.get("traderNameVi")),
                    "_start": (r.get("startDate") or "")[:10] or None})
    grp = {}
    for x in out:
        grp[(x["d"], x["kl"] > 0)] = grp.get((x["d"], x["kl"] > 0), 0.0) + abs(x["kl"])
    used = {}
    for x in sorted(out, key=lambda y: -abs(y["kl"])):  # lệnh lớn nhận phiên thoả thuận trước
        x["pt"], x["gia_tt"] = deal_label(px, x["_start"], iso(x["d"]), abs(x["kl"]), grp[(x["d"], x["kl"] > 0)], used)
    for x in out:
        if x["kl"] <= 0:
            continue
        before = float(x["_bef"] or 0)
        for e in ev:
            dd = (x["d"] - e["d"]).days
            ratio = e.get("ty_le") or 0
            # KL đúng bằng cp trước × tỷ lệ: bằng chứng đủ mạnh, cp quyền mua thường về tài khoản 2-5 tháng sau GDKHQ
            if -30 <= dd <= 150 and ratio and before > 0 and abs(x["kl"] - before * ratio) <= max(0.02 * x["kl"], 1):
                x["nguon"] = "quyền mua"
                break
            if abs(dd) > 60:
                continue
            if ((x["pt"] == "thoả thuận" and shares and x["kl"] >= 0.001 * shares)
                    or (ratio and shares and x["kl"] > 1.05 * ratio * shares)):
                continue
            if e["loai"] == "ESOP":
                if x["_ca_nhan"]:
                    x["nguon"] = "ESOP"
                    break
                continue
            if dd >= -3:
                x["nguon"] = x["nguon"] or "trùng đợt phát hành?"
    done = {}
    for x in out:
        done.setdefault((x["ten"], x["kl"] > 0), []).append(x["d"])
    regs = []
    for r in raw:
        if "registration" not in (r.get("tradeStatusEn") or "").lower() or r.get("actionTypeCode") not in ("B", "S"):
            continue
        ten_r, mua = r.get("traderNameVi") or r.get("traderOrganNameVi") or "", r.get("actionTypeCode") == "B"
        v, end = float(r.get("shareRegister") or 0), (r.get("endDate") or r.get("publicDate") or "")[:10]
        if v <= 0 or not end:
            continue
        lo = pd.Timestamp((r.get("startDate") or end)[:10]) - pd.Timedelta(days=3)
        hi = pd.Timestamp(end) + pd.Timedelta(days=3)
        if any(lo <= d <= hi for d in done.get((ten_r, mua), [])):
            continue  # đăng ký đã có dòng kết quả của chính chủ thể: không còn là "đăng ký"
        regs.append((ten_r, mua, v, lo, hi))
    for x in out:
        k = abs(x["kl"])
        if x["nguon"] or not shares or k < 0.01 * shares:
            continue
        cands = [(v, t) for t, mua, v, lo, hi in regs if t != x["ten"] and mua != (x["kl"] > 0) and lo <= x["d"] <= hi]
        hit = next((c for n in (1, 2, 3) for c in itertools.combinations(cands[:12], n)
                    if abs(sum(v for v, _ in c) - k) <= 0.02 * k), None)
        if hit:
            x["nguon"] = "chuyển nội bộ (đối ứng còn đăng ký: " + " + ".join(
                f"{t[:40]} {v:,.0f}".replace(",", ".") for v, t in hit) + ")"
    out += chain_rows(out, tk, shares, px, cut)
    return sorted(out, key=lambda x: x["d"])


def insider_registered(tk: str, today: str) -> list:
    """Đăng ký chưa có kết quả mà cửa sổ còn mở (hoặc vừa đóng ≤ 30 ngày); đăng ký cũ không bao giờ đóng thì bỏ."""
    out = []
    cut = iso(pd.Timestamp(today) - pd.Timedelta(days=30))
    for r in vc_rows(tk, "insider-transaction"):
        if "registration" not in (r.get("tradeStatusEn") or "").lower():
            continue
        if (r.get("endDate") or r.get("publicDate") or "")[:10] < cut:
            continue
        out.append({"ngay": (r.get("publicDate") or "")[:10], "tu": (r.get("startDate") or "")[:10], "den": (r.get("endDate") or "")[:10],
                    "tieu_de": r.get("eventTitleVi") or "", "kl_dk": r.get("shareRegister")})
    return sorted(out, key=lambda x: x["ngay"])[-8:]


def issue_rows(tk: str) -> list:
    out, seen = [], set()
    for r in vc_rows(tk, "events-v2"):
        code = r.get("eventCode")
        d = r.get("exrightDate") or r.get("issueDate") or r.get("publicDate")
        if code not in ("ISS", "DIV") or not d:
            continue
        key = (code, d[:10], r.get("exerciseRatio"))
        if key in seen:
            continue
        seen.add(key)
        t = (r.get("eventTitleVi") or "").lower()
        if code == "DIV":
            loai = "cổ tức tiền"
        elif "cổ tức bằng cổ phiếu" in t or "thưởng" in t or "nguồn vốn chủ" in t:
            loai = "cổ tức/thưởng cp"
        elif "esop" in t or "người lao động" in t or "cbcnv" in t:
            loai = "ESOP"
        elif "sáp nhập" in t or "hoán đổi" in t:
            loai = "sáp nhập/hoán đổi"
        elif any(k in t for k in ("riêng lẻ", "chào bán", "quyền mua", "hiện hữu", "chuyển đổi")):
            loai = "chào bán"
        else:
            loai = "phát hành khác"
        out.append({"d": pd.Timestamp(d[:10]), "loai": loai,
                    "ty_le": r.get("exerciseRatio"), "tieu_de": (r.get("eventTitleVi") or "")[:140]})
    return sorted(out, key=lambda x: x["d"])


def fft_events(tin: dict, tk: str, since: str) -> list:
    ev = ((tin or {}).get("ma") or {}).get(tk, {}).get("su_kien") or []
    out = [{k: e.get(k) for k in ("ngay", "loai", "the_loai", "chu_the", "vai_tro", "so_luong_cp", "mo_ta", "bac", "trang_thai_gd", "ty_le_sau_pct")}
           for e in ev if (e.get("ngay") or "") >= since]
    return sorted(out, key=lambda x: x["ngay"] or "", reverse=True)[:30]


# ── tần suất thắng có điều kiện ───────────────────────────────────────────────

def pick_nonoverlap(mask: np.ndarray, step: int) -> np.ndarray:
    idx, last = [], -10**9
    for i in np.flatnonzero(mask):
        if i - last >= step:
            idx.append(i)
            last = i
    return np.array(idx, dtype=int)


def cond_stat(g: pd.DataFrame, mask: np.ndarray) -> dict:
    r60 = g.r60.to_numpy()
    r120 = g.r120.to_numpy()
    i60 = pick_nonoverlap(mask & np.isfinite(r60), 60)
    i120 = pick_nonoverlap(mask & np.isfinite(r120), 120)
    k = int((r60[i60] > 0).sum()) if len(i60) else 0
    lo, hi = wilson(k, len(i60))
    return {"n": int(len(i60)), "k": k, "hit60": f(100 * k / len(i60), 1) if len(i60) else None,
            "r60_tv": f(float(np.median(r60[i60])), 1) if len(i60) else None, "ci": [lo, hi],
            "n120": int(len(i120)), "hit120": f(100 * (r120[i120] > 0).mean(), 1) if len(i120) else None,
            "r120_tv": f(float(np.median(r120[i120])), 1) if len(i120) else None}


def erp_bucket(v):
    if v is None or not np.isfinite(v):
        return None
    for name, lo, hi in ERP_ZONES:
        if lo <= v < hi:
            return name
    return None


def win_prob(g: pd.DataFrame, pool: dict, now: dict) -> list:
    e = g[g.ls.notna() & g.pct.notna()].reset_index(drop=True)
    if e.empty:
        return []
    hd = e.dls6m.map(tb.bucket_dir).to_numpy()
    eb = e.erp.map(erp_bucket).to_numpy()
    sig = e.sig.to_numpy(dtype=bool)
    sig45 = (e.sig45 & e.pct45.notna()).to_numpy(dtype=bool)
    eb45 = e.erp45.map(erp_bucket).to_numpy()
    allm = np.ones(len(e), dtype=bool)
    conds = [("all", "Mọi thời điểm (gốc so sánh)", allm),
             ("sig", "Khi luật TV bật", sig),
             ("sig45", "Khi luật TV bật · bản không nhìn trước EPS", sig45),
             ("huong", f"Khi hướng LS 6 tháng = “{now.get('huong')}” như hiện tại", hd == now.get("huong")),
             ("sig_huong", f"Luật TV bật VÀ LS “{now.get('huong')}”", sig & (hd == now.get("huong"))),
             ("sig45_huong", f"Luật TV bật VÀ LS “{now.get('huong')}” · không nhìn trước EPS", sig45 & (hd == now.get("huong"))),
             ("erp", f"Khi ERP cổ phiếu cùng vùng hiện tại ({now.get('erp_vung')})", eb == now.get("erp_vung")),
             ("erp45", f"ERP cùng vùng hiện tại · không nhìn trước EPS", eb45 == now.get("erp_vung"))]
    out = []
    for key, name, m in conds:
        st = cond_stat(e, m)
        p0 = pool.get(key)
        st.update({"key": key, "ten": name, "p_ro": p0})
        if st["n"] and p0 is not None:
            st["co"] = f(100 * (st["k"] + SHRINK_M * p0 / 100) / (st["n"] + SHRINK_M), 1)
        else:
            st["co"] = p0
        out.append(st)
    return out


def pool_rates(a: pd.DataFrame, members: set, now: dict) -> dict:
    """Tần suất gộp (độc lập trong từng mã) của rổ cho cùng điều kiện, làm tiên nghiệm co."""
    acc = {k: [0, 0] for k in ("all", "sig", "sig45", "huong", "sig_huong", "sig45_huong", "erp", "erp45")}
    for tk, g in a[a.tk.isin(members)].groupby("tk"):
        e = g[g.ls.notna() & g.pct.notna()].reset_index(drop=True)
        if e.empty:
            continue
        hd = e.dls6m.map(tb.bucket_dir).to_numpy()
        eb = e.erp.map(erp_bucket).to_numpy()
        sig = e.sig.to_numpy(dtype=bool)
        s45 = (e.sig45 & e.pct45.notna()).to_numpy(bool)
        m = {"all": np.ones(len(e), bool), "sig": sig, "sig45": s45,
             "huong": hd == now["huong"], "sig_huong": sig & (hd == now["huong"]), "sig45_huong": s45 & (hd == now["huong"]),
             "erp": eb == now["erp_vung"], "erp45": e.erp45.map(erp_bucket).to_numpy() == now["erp_vung"]}
        for k, mk in m.items():
            if mk is None:
                continue
            st = cond_stat(e, mk)
            acc[k][0] += st["k"]
            acc[k][1] += st["n"]
    return {k: (100 * v[0] / v[1] if v[1] else None) for k, v in acc.items()}


# ── HHP (đọc engine qua hhp_valuation.py, chỉ đọc) ───────────────────────────

def hhp_ticker(tk: str):
    try:
        import hhp_valuation as hv
        return hv.clean(hv.build_ticker(hv.data_dir(), tk))
    except Exception as ex:  # thiếu chuỗi (TCX/VCK/VPX) hoặc lỗi engine
        return {"error": str(ex)}


def hhp_pick(h: dict, sector: str | None) -> dict | None:
    if not h or h.get("error"):
        return None
    row = h.get("row") or {}
    want = "pb" if sector in PB_SECTORS else "pe"
    blk, rb = h.get(want), row.get(want)
    if not blk or not rb or not rb.get("reliable"):
        alt = "pe" if want == "pb" else "pb"
        if h.get(alt) and (row.get(alt) or {}).get("reliable"):
            want, blk, rb = alt, h.get(alt), row.get(alt)
    if not blk or not rb:
        return None
    return {"thuoc_do": want, "ly_do": "ngành " + (sector or "?") + (" → P/B" if want == "pb" else " → P/E"),
            "sigma": rb.get("sigma"), "zone": rb.get("zone"), "zone_key": rb.get("zone_key"), "reliable": rb.get("reliable"),
            "now": rb.get("now"), "mean": rb.get("mean"), "sd": rb.get("sd"), "upside_fair": rb.get("upside_to_fair_pct"),
            "band": {k: rb.get(f"band_{k}") for k in ("cheap2", "cheap1", "fair", "rich1", "rich2")}, "as_of": rb.get("as_of"),
            # σ quá rộng so với μ: −2σ rơi về ≈ 0đ, dải không còn mang thông tin dù cờ reliable bật
            "suy_bien": bool(rb.get("band_fair") and (rb.get("band_cheap2") is None or rb["band_cheap2"] <= 0.1 * rb["band_fair"]))}


def hhp_zone_hist(h: dict, met: str) -> dict | None:
    """Tần suất thắng 12/24 tuần (≈ 60/120 phiên) theo vùng σ trên chuỗi tuần của HHP (μ, σ toàn mẫu: có nhìn trước)."""
    ch = ((h or {}).get(met) or {}).get("chart") or {}
    pr, c1, r1 = ch.get("price") or [], ch.get("cheap1") or [], ch.get("rich1") or []
    if len(pr) < 60 or len(c1) != len(pr) or len(r1) != len(pr):
        return None
    p = np.array([x[1] if x[1] is not None else np.nan for x in pr], float)
    lo = np.array([x[1] if x[1] is not None else np.nan for x in c1], float)
    hi = np.array([x[1] if x[1] is not None else np.nan for x in r1], float)
    out = {}
    for name, m in (("RẺ (< −1σ)", p < lo), ("TRUNG TÍNH", (p >= lo) & (p <= hi)), ("ĐẮT (> +1σ)", p > hi)):
        res = {}
        for h_, lab in ((12, "60"), (24, "120")):
            fwd = np.full_like(p, np.nan)
            fwd[:-h_] = p[h_:] / p[:-h_] - 1
            ii = pick_nonoverlap(m & np.isfinite(fwd), h_)
            res["n" + lab] = int(len(ii))
            res["hit" + lab] = f(100 * (fwd[ii] > 0).mean(), 1) if len(ii) else None
            res["r" + lab] = f(100 * float(np.median(fwd[ii])), 1) if len(ii) else None
        out[name] = res
    return out


# ── lãi suất ──────────────────────────────────────────────────────────────────

def wd_lines(C, cid, prefixes):
    c = C.get(cid) or {}
    out = {}
    for s in c.get("series_multi") or []:
        for pf in prefixes:
            if s["name"].startswith(pf):
                out[pf] = [(iso(pd.Timestamp(p["t"] + 7 * 3600 * 1000, unit="ms")), p["v"]) for p in s["series"] if p.get("v") is not None]
    if c.get("series"):
        out["_"] = [(iso(pd.Timestamp(p["t"] + 7 * 3600 * 1000, unit="ms")), p["v"]) for p in c["series"] if p.get("v") is not None]
    return out


def build_vimo(ls: pd.Series, ls_info: dict) -> dict:
    out = {"canh_bao": []}
    st = read_json(WIDATA) or {}
    C = st.get("canvases") or {}
    dep = wd_lines(C, "wc-lshuy", ["1-3 tháng", "6-9 tháng", "13 tháng"])
    ib = wd_lines(C, "wc-hllai", ["LS qua đêm", "LS liên ngân hàng kỳ hạn 1 tuần", "LS liên ngân hàng kỳ hạn 2 tuần"])
    pol = wd_lines(C, "wc-lsdh", ["Lãi suất tái cấp vốn"])
    out["tien_gui_niem_yet"] = {"nguon": "WiChart lshd · bình quân MBB/ACB/TCB", "bac": "FACT-T2", "x": [d for d, _ in dep.get("13 tháng", [])],
                                "y13": [v for _, v in dep.get("13 tháng", [])], "y6": [v for _, v in dep.get("6-9 tháng", [])]}
    out["lien_nh"] = {"nguon": "WiChart lslnh", "bac": "FACT-T2", "x": [d for d, _ in ib.get("LS qua đêm", [])],
                      "on": [v for _, v in ib.get("LS qua đêm", [])], "w2": [v for _, v in ib.get("LS liên ngân hàng kỳ hạn 2 tuần", [])]}
    out["tai_cap_von"] = (pol.get("Lãi suất tái cấp vốn") or [[None, None]])[-1]
    td, m2 = wd_lines(C, "wc-tdcn", [])["_"] if C.get("wc-tdcn") else [], wd_lines(C, "wc-tkhe", [])["_"] if C.get("wc-tkhe") else []
    out["tin_dung_m2"] = {"tin_dung": td[-1] if td else None, "m2": m2[-1] if m2 else None,
                          "ghi_chu": "M2 YoY vắt qua điểm gãy chuỗi 10/2025 của NHNN: hở thô ≈13 điểm phóng đại; nối gãy ước ≈5–7 điểm [EST]"}
    t = read_json(TPCP) or {}
    k10 = (t.get("ky_han") or {}).get("10Y") or []
    k10 = [p for p in k10 if p[0] >= "2016-01-01"]
    out["tpcp10"] = {"nguon": "HNX par-yield (bản sao FTU-kudo)", "bac": "FACT-T2", "x": [p[0] for p in k10[::5]] + ([k10[-1][0]] if k10 else []),
                     "y": [p[1] for p in k10[::5]] + ([k10[-1][1]] if k10 else []), "canh_bao": t.get("canh_bao") or []}
    sbv = []
    try:
        for r in csv.DictReader(SBV_CSV.open()):
            sbv.append({"thang": r["ym"], "dep_lo": float(r["dep612_lo"]) if r["dep612_lo"] else None,
                        "dep_hi": float(r["dep612_hi"]) if r["dep612_hi"] else None, "nguon": r.get("nguon")})
    except Exception:
        out["canh_bao"].append("không đọc được hhp_rates_sbv.csv")
    out["nhnn_6_12"] = sbv[-12:]
    out["fiinprox"] = {"x": [iso(d) for d in ls.index if d >= pd.Timestamp("2016-01-01")],
                       "y": [f(v) for d, v in ls.items() if d >= pd.Timestamp("2016-01-01")], **{k: ls_info.get(k) for k in ("ten", "den") if k in ls_info}}
    issues = sorted(SGI_DIR.glob("20*.json"))
    if issues:
        s = read_json(issues[-1]) or {}
        v = s.get("verdict") or {}
        ci = s.get("chi_so") or {}
        out["sgi"] = {"ky": s.get("ky") or issues[-1].stem, "du_lieu_den": s.get("du_lieu_den"), "che_do": v.get("che_do"),
                      "chot": v.get("chot"), "dieu_kien_day": v.get("dieu_kien_day_ghi"),
                      "tien_mat_de_xuat": (v.get("tien_mat") or {}).get("de_xuat"),
                      "dk": [{"ten": x.get("ten"), "trang_thai": x.get("trang_thai")} for x in s.get("dieu_kien_day") or []],
                      "chi_so": {k: ci.get(k) for k in ("ls_huy_dong_6_12t_thap", "ls_huy_dong_6_12t_cao", "lnh_6t", "lnh_6t_bq_thang",
                                                         "chenh_6t_qd_bp", "tpcp_vn_10y", "tin_dung_ytd", "m2_ytd") if k in ci}}
    return out


# ── bằng chứng ────────────────────────────────────────────────────────────────

def evidence_row(tk, ten, cur, dot, hp, eps_g, ins12, raise18, shares, eps_tier=None) -> dict:
    """Sáu chiều −1/0/+1. Không phải khuyến nghị: là mức hội tụ bằng chứng kèm điều kiện xác nhận và điểm gãy."""
    dims = []
    pct, thr = cur.get("pct"), cur.get("nguong")
    if pct is not None and thr is not None:
        sc = 1 if pct <= thr else (-1 if pct >= 70 else 0)
        dims.append(("TV", sc, f"P/E ở P{vnum(pct, 0)} của 250 phiên (ngưỡng P{vnum(thr, 0)})"))
    if hp:
        if hp.get("suy_bien") and (hp.get("sigma") is None or hp["sigma"] <= 1):
            # σ quá rộng: phía RẺ vô nghĩa (−2σ ≈ 0đ); phía ĐẮT (> +1σ của dải rộng) vẫn là đắt thật nên chấm như thường
            dims.append(("HHP", 0, "dải σ HHP suy biến (−2σ ≈ 0đ), phía rẻ không mang thông tin"))
        elif hp.get("reliable") or hp.get("suy_bien"):
            s = hp.get("sigma")
            sc = 1 if (s is not None and s < -1) else (-1 if (s is not None and s > 1) else 0)
            dims.append(("HHP", sc, f"{hp['thuoc_do'].upper().replace('PE', 'P/E').replace('PB', 'P/B')} {vnum(s, 2, True)}σ, "
                                    f"{(hp.get('zone') or '').split(' (')[0].lower()}" if s is not None else "HHP: thiếu σ"))
        else:
            dims.append(("HHP", 0, "dải σ HHP không tin cậy (sd/μ ≥ 0,6)"))
    erp = cur.get("erp")
    if erp is not None:
        dims.append(("ERP", 1 if erp >= 5 else (-1 if erp < 0 else 0), f"ERP cổ phiếu {vnum(erp, 1, True)} điểm"))
    if dot and dot.get("n_do"):
        xs, p = dot.get("xs_tb"), dot.get("p_xs")
        sc = 0
        if xs is not None and p is not None and p < 0.1:
            sc = 1 if xs > 0 else -1
        dims.append(("Lịch sử", sc, f"{dot['n_do']} đợt độc lập, vượt cùng ngày {vnum(xs, 1, True)} điểm (p {vnum(p, 2)})"
                     if xs is not None and p is not None else f"{dot['n_do']} đợt độc lập"))
    if eps_g is not None:
        src = "đồng thuận" if eps_tier in ("SS-T3", "FACT-T2", "FACT-T1") else "ước theo luật hội tụ (EST)"
        dims.append(("EPS", 1 if eps_g >= 15 else (-1 if eps_g < 0 else 0), f"EPS FY2026 {src} {vnum(eps_g, 0, True)}%"))
    txt, ow = [], 0
    if ins12 is not None and shares:
        net = 100 * ins12 / shares
        ow = 1 if net >= 0.1 else (-1 if net <= -0.1 else 0)
        txt.append(f"nội bộ ròng 12 tháng {vnum(net, 2, True)}% số cp")
    if raise18:
        txt.append(f"đang huy động vốn qua sàn ({raise18})")
    if txt:
        dims.append(("Chủ thể", ow, "; ".join(txt)))
    score = sum(s for _, s, _ in dims)
    nhan = ("Hội tụ mạnh" if score >= 3 else "Hội tụ" if score == 2 else "Lẫn lộn" if score >= 0 else "Ngược chiều")
    pos = [d for d in dims if d[1] > 0]
    gay = []
    if any(d[0] == "HHP" and d[1] > 0 for d in dims) and hp:
        c2 = (hp.get("band") or {}).get("cheap2")
        if (hp.get("sigma") or 0) <= -2:
            gay.append("giá đã dưới −2σ HHP nên dải σ không còn là điểm gãy; gãy nếu cơ sở (EPS/BVPS) tiếp tục giảm hoặc chế độ định giá đã đổi")
        else:
            gay.append(f"giá thủng dải −2σ HHP{(' ≈ ' + vnum(c2, 0) + 'đ') if c2 else ''} hoặc EPS FY2026 hụt dự phóng")
    if any(d[0] == "TV" and d[1] > 0 for d in dims):
        gay.append("LS 6 tháng tiếp tục đi lên (trong kiểm định, tín hiệu TV mất lợi thế khi LS tăng)")
    if any(d[0] == "EPS" and d[1] > 0 for d in dims):
        gay.append("KQKD quý kế tiếp đi ngược đường EPS dự phóng")
    xn = ("KQKD quý tới giữ đà EPS; LS huy động thôi lập đỉnh (LTT)" if pos else "chưa có trụ bằng chứng dương để xác nhận")
    bac = {"TV": "EST", "HHP": "EST", "ERP": "EST", "Lịch sử": "EST", "Chủ thể": "FACT-T2",
           "EPS": eps_tier if eps_tier in ("SS-T3", "FACT-T2", "FACT-T1") else "EST"}
    return {"ma": tk, "ten": ten, "diem": score, "nhan": nhan, "chieu": [{"k": k, "s": s, "t": t, "bac": bac.get(k, "EST")} for k, s, t in dims],
            "xac_nhan": xn, "diem_gay": "; ".join(gay) or "n/a", "huy_dong": raise18 or None,
            "ls_n": (dot or {}).get("n_do"), "ls_xs": (dot or {}).get("xs_tb"), "ls_p": (dot or {}).get("p_xs"),
            "nb12_pct": round(100 * ins12 / shares, 3) if (ins12 is not None and shares) else None}


# ── điều phối ────────────────────────────────────────────────────────────────

def build_sau(a: pd.DataFrame, df: pd.DataFrame, ls: pd.Series, ls_info: dict, names: dict, out: Path, last_full,
              ov_rows: list, only: set | None = None) -> None:
    t0 = datetime.now()
    (out / "ro").mkdir(parents=True, exist_ok=True)
    (out / "sau").mkdir(parents=True, exist_ok=True)
    uni = load_universe(set(a.tk.unique()))
    vni = vnindex_close()
    lsd = ls.reindex(pd.date_range(ls.index[0], max(ls.index[-1], df.date.max())), method="ffill")
    tin = read_json(FFT_TIN)
    vimo = build_vimo(ls, ls_info)
    (out / "vimo.json").write_text(json.dumps(vimo, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    log(f"vimo.json · LS niêm yết 13T {vimo['tien_gui_niem_yet']['y13'][-1:]} · SGI {(vimo.get('sgi') or {}).get('che_do')}")

    cur_dls = float(a[a.date == a.date.max()].dls6m.dropna().iloc[0]) if a[a.date == a.date.max()].dls6m.notna().any() else None
    now_common = {"huong": tb.bucket_dir(cur_dls)}
    vn100 = set(uni["VN100"])
    vn200 = set(uni["VN200"])
    deep = sorted(set(a.tk.unique()))   # lớp sâu cho MỌI mã của tệp Bloomberg (VN200 + REST)

    def group_of(tk):  # tiên nghiệm co: nhóm của chính mã (VN100 / VN101–200 / REST), không co mã nhỏ về rổ lớn
        return "VN100" if tk in vn100 else ("VN200" if tk in vn200 else "REST")
    group_members = {"VN100": vn100, "VN200": vn200 - vn100, "REST": set(uni["REST"])}
    if only:
        deep = [t for t in deep if t in only]
    ov_by = {r["ma"]: r for r in ov_rows}
    ev_rows = {}
    pools = {}
    for tk in deep:
        g = a[a.tk == tk].sort_values("date").reset_index(drop=True)
        last = g[g.pct.notna()].iloc[-1] if g.pct.notna().any() else g.iloc[-1]
        now = {**now_common, "erp_vung": erp_bucket(last.erp)}
        grp = group_of(tk)
        pk = (grp, now["erp_vung"])
        if pk not in pools:
            pools[pk] = pool_rates(a, group_members[grp], {**now_common, "erp_vung": pk[1]})
        sector = sector_of(tk)
        h = hhp_ticker(tk)
        hp = hhp_pick(h, sector)
        iss = issue_rows(tk)
        det = vc_rows(tk, "details")
        shares = (det[0].get("numberOfSharesMktCap") or det[0].get("issueShare")) if det else None
        cut12 = pd.Timestamp(last.date) - pd.Timedelta(days=365)
        ins = insider_rows(tk, iss, shares, cut12)
        tp = json.loads((out / "ma" / f"{tk}.json").read_text()) if (out / "ma" / f"{tk}.json").exists() else {}
        pool = dict(pools[pk])
        # ERP pool cho đúng vùng của mã
        e_pool = []
        wp = win_prob(g, pool, now)
        erp_pool = None
        ph = phases(g, lsd, vni, ins, iss, shares)
        ins12 = sum(x["kl"] for x in ins if x["d"] >= cut12 and not x.get("nguon"))  # gồm lệnh khối và CHUOI; loại nhận qua phát hành / chuyển nội bộ
        cut18 = pd.Timestamp(last.date) - pd.Timedelta(days=548)
        raise18 = ", ".join(sorted({x["loai"] for x in iss if x["d"] >= cut18 and x["loai"] == "chào bán"}))
        fc = ((h or {}).get("forecast") or {}).get("pe") or {}
        g26e = next((x for x in fc.get("growth") or [] if x.get("year") == 2026), {}) or {}
        g26, g26_tier = g26e.get("g"), g26e.get("tier")
        eps_g = 100 * g26 if g26 is not None else None
        cur = (tp.get("hien_tai") or {})
        ev = evidence_row(tk, names.get(tk, {}).get("ten") if isinstance(names.get(tk), dict) else tp.get("ten"),
                          cur, tp.get("theo_dot"), hp, eps_g, ins12, raise18, shares, g26_tier)
        ev.update({"pe": cur.get("pe"), "pct": cur.get("pct"), "nguong": cur.get("nguong"), "erp": cur.get("erp"),
                   "hhp_sigma": hp.get("sigma") if hp else None, "hhp_do": hp.get("thuoc_do") if hp else None,
                   "hhp_upside": hp.get("upside_fair") if hp else None, "eps26": f(eps_g, 1) if eps_g is not None else None,
                   # cột "Thắng 60 (co)": bản KHÔNG nhìn trước EPS (Bloomberg ghi EPS quý vào ngày cuối quý)
                   "hit60_co": next((w["co"] for w in wp if w["key"] == "sig45_huong"), None),
                   "kich_hoat": bool(cur.get("kich_hoat")),
                   "hit60_all": next((w["hit60"] for w in wp if w["key"] == "all"), None), "nganh": sector})
        ev_rows[tk] = ev
        targets = [{k: t.get(k) for k in ("org", "date", "value_vnd", "rating", "tier", "note")} for t in
                   (((h or {}).get("forecast") or {}).get("targets") or [])]
        payload = {
            "ma": tk, "phien": iso(last_full), "nganh": sector, "co_phieu_luu_hanh": shares,
            "pha": ph, "xac_suat": wp, "huong_ls_now": now["huong"], "erp_vung_now": now["erp_vung"], "nhom_co": grp,
            "hhp": hp, "hhp_vung_lich_su": hhp_zone_hist(h, hp["thuoc_do"]) if hp else None,
            "hhp_loi": (h or {}).get("error"),
            "du_phong": {"eps_pins": [{k: x.get(k) for k in ("year", "value", "tier", "g", "g_tier")} for x in fc.get("eps_pins") or []],
                         "growth": [{k: x.get(k) for k in ("year", "g", "tier", "n", "min", "max")} for x in fc.get("growth") or []],
                         "targets": targets, "forward": {k: ((h or {}).get("forward") or {}).get(k) for k in ("pe", "pb", "roe", "tp", "rating")}},
            # đủ mọi dòng trong cửa sổ 12 tháng của nb12 (để tổng khớp), cộng dòng cũ hơn cho tới 40
            "noi_bo": [{"ngay": iso(x["d"]), "ten": x["ten"], "vai": x["vai"], "lq": x["lq"], "kl": int(x["kl"]),
                        "sau_pct": x["sau_pct"], "code": x["code"], "nguon": x.get("nguon"), "pt": x.get("pt"),
                        "gia_tt": x.get("gia_tt"), **({"den": x["den"]} if x.get("den") else {})}
                       for x in ([y for y in ins if y["d"] < cut12][-max(0, 40 - sum(y["d"] >= cut12 for y in ins)):]
                                 if sum(y["d"] >= cut12 for y in ins) < 40 else []) + [y for y in ins if y["d"] >= cut12]][::-1],
            "noi_bo_dang_ky": insider_registered(tk, iso(last_full)),
            "von": [{"ngay": iso(x["d"]), "loai": x["loai"], "ty_le": x["ty_le"], "tieu_de": x["tieu_de"]} for x in iss[-14:]][::-1],
            "su_kien_fft": fft_events(tin, tk, iso(pd.Timestamp(last_full) - pd.Timedelta(days=400))),
            "bang_chung": ev,
        }
        (out / "sau" / f"{tk}.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
                                                           default=lambda o: None))
    log(f"Ghi {len(deep)} tệp sau/ ({(datetime.now() - t0).seconds}s)")

    mstat = member_stats(a)
    hb = read_json(HHP_DIR / "hhp_baskets.json") or {}
    core = read_json(HHP_DIR / "hhp_vn100_valuation.json") or {}
    if only:  # chạy thử vài mã: không ghi đè trang rổ và bảng tổng (sẽ chỉ còn vài dòng)
        log("--chi-ma: bỏ qua ro/*.json và bang_chung.json")
        return
    for code in SCOPES:
        mem = uni[code]
        b = next((x for x in hb.get("baskets") or [] if x.get("code") == code), None)
        rows = [ev_rows[t] for t in mem if t in ev_rows]
        sp = scope_payload(code, mem, df, a, ls, vni if code == "VNINDEX" else None, [dict(r) for r in ov_rows], mstat,
                           last_full, b, core, rows)
        (out / "ro" / f"{code}.json").write_text(json.dumps(sp, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
                                                            default=lambda o: None))
        log(f"ro/{code}.json · {sp['so_ma']} mã · P/E {sp['hien_tai']['pe_tv']} · ERP {sp['hien_tai']['erp_tv']}")
    bang = sorted(ev_rows.values(), key=lambda r: (-r["diem"], r["ma"]))
    (out / "bang_chung.json").write_text(json.dumps({"phien": iso(last_full), "huong_ls": now_common["huong"], "dls6m": cur_dls,
                                                     "rows": bang}, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
                                                    default=lambda o: None))
    log(f"Lớp sâu xong ({(datetime.now() - t0).seconds}s)")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bbg", type=Path, default=tb.BBG_DEFAULT)
    ap.add_argument("--fiin", type=Path, default=tb.FIIN_DEFAULT)
    ap.add_argument("--out", type=Path, default=tb.OUT_DEFAULT)
    ap.add_argument("--chi-ma", default="")
    args = ap.parse_args(argv)
    cache = args.out / "cache" / f"bbg_{tb.sha256(args.bbg)[:16]}.parquet"
    df = pd.read_parquet(cache) if cache.exists() else tb.parse_bloomberg(args.bbg)
    ls, ls_info = tb.parse_fiin(args.fiin)
    names = tb.load_names()
    last_full, _, _ = tb.detect_sessions(df)
    df_full = df[df.date <= last_full]
    a = tb.compute(df_full, ls)
    tong = read_json(args.out / "tong_quan.json") or {}
    only = {x.strip().upper() for x in args.chi_ma.split(",") if x.strip()} or None
    build_sau(a, df_full, ls, ls_info, names, args.out, last_full, tong.get("bang") or [], only)


if __name__ == "__main__":
    main()
