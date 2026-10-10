#!/usr/bin/env python3
"""toanvu_pe_build.py, dựng dữ liệu cho tab Fincept "toanvu_pe" (Vùng P/E × Lãi suất · Toàn Vũ).

Chạy NGOÀI app (cần pandas/numpy/lxml/openpyxl; scipy nếu có). Đọc đúng hai tệp Toàn Vũ gửi
ngày 06/10/2026 rồi:
  1. tái lập luật "Dream-RSI per-stock" của Toàn Vũ (SS-T3) đúng như bản gốc đã tính:
       pct  = P/E.rolling(250, min_periods=60).rank(pct=True) × 100      (P/E trailing Bloomberg)
       ngưỡng = max(5, 40 − 4 × (LS − 5))                                  (LS = LSHĐ VND >12T cao nhất, %)
       tín hiệu = pct ≤ ngưỡng ; lợi suất h phiên = PX(t+h)/PX(t) − 1 ; alpha = TB(r60|tín hiệu) − TB(r60 mọi ngày có LS)
  2. kiểm định bổ sung (EST): so cùng ngày, đợt độc lập, ngưỡng cố định, hướng LS 6 tháng, ERP từng mã,
     vùng 52 tuần, rào cản tiền gửi, P/E gộp thị trường.
  3. ghi JSON: <out>/tong_quan.json, <out>/ma/<MÃ>.json, <out>/MANIFEST.json.
Script trong app (scripts/toanvu_pe.py, stdlib) chỉ đọc các JSON này.

Dùng:
  python3 toanvu_pe_build.py [--bbg XLSX] [--fiin XLSX] [--out DIR] [--cat-tv YYYY-MM-DD]
Mặc định --out = ~/SECOND BRAIN-OBSIDIAN/_System/fincept_bridge/state/toanvu_pe
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

VERSION = "1.0"
HOME = Path.home()
SYS_DIR = HOME / "SECOND BRAIN-OBSIDIAN" / "_System"
OUT_DEFAULT = SYS_DIR / "fincept_bridge" / "state" / "toanvu_pe"
VNSTORE = SYS_DIR / "fincept_bridge" / "vnstore" / "vn_store.db"
BBG_DEFAULT = HOME / "Downloads" / "Bloomberg_VNINDEX_2000-nay.xlsx"
FIIN_DEFAULT = HOME / "Downloads" / "FiinProX_DE_Du_lieu_vi_mo_20261006.xlsx"
TV_HTML = HOME / "Downloads" / "perstock_erp_backtest_20261006.html"
TV_MACRO_HTML = HOME / "Downloads" / "macro_valuation_v2_20261006.html"

WIN, MINP = 250, 60          # cửa sổ percentile của bản gốc (đã tái lập: rolling(250, min_periods=60))
HORIZONS = (20, 60, 120)
EPS_LAG_DAYS = 45            # trễ EPS cho bản không nhìn trước
EP_GAP = 10                  # chỉ số hàng tín hiệu nhảy > 10 (≥ 10 phiên không kích hoạt xen giữa) → đợt mới
CUT_TV = "2026-09-07"        # ngày dữ liệu thật của báo cáo TV (tái lập khớp tuyệt đối percentile 8 mã)
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# ── Số Toàn Vũ IN TRONG BÁO CÁO (SS-T3), đọc từ 4 biểu đồ nhúng của perstock_erp_backtest_20261006.html ──
TV_RANK = {  # alpha 60D (pp), hit 60D (%), biểu đồ ① top 30 + bottom 15
    "NO1": (35.16, 98), "PTL": (28.04, 81), "VCA": (25.96, 100), "DAT": (21.32, 56), "TSC": (21.17, 54),
    "SVT": (17.24, 67), "TMT": (14.25, 66), "DTT": (13.27, 77), "TIX": (13.21, 94), "DTL": (12.58, 67),
    "VPG": (12.51, 61), "GEX": (12.04, 70), "CTF": (10.98, 80), "TVS": (9.49, 67), "DBC": (9.43, 61),
    "TDH": (9.38, 54), "VDS": (9.24, 68), "ASP": (9.16, 59), "HAX": (9.13, 68), "ABR": (8.92, 61),
    "TN1": (8.87, 65), "TDC": (8.67, 62), "VTB": (8.36, 70), "SFC": (8.32, 68), "LGC": (7.89, 73),
    "CLW": (7.87, 79), "HTV": (7.79, 60), "BAF": (7.61, 84), "TNH": (7.43, 69), "VDP": (7.42, 90),
    "PTB": (-8.26, None), "VPH": (-8.39, None), "LPB": (-8.44, None), "PDR": (-8.45, None),
    "PTC": (-9.34, None), "CSV": (-9.46, None), "DAH": (-10.14, None), "CRE": (-10.18, None),
    "HTN": (-10.68, None), "TNT": (-11.41, None), "NAF": (-12.76, None), "HPX": (-12.95, None),
    "DGC": (-15.67, None), "TTE": (-19.49, None), "GEE": (-31.78, None),
}
TV_WATCH = {  # biểu đồ ②: hit 60D, n, ret khi tín hiệu, ret baseline, alpha
    "VPB": (60.5, 871, 6.5, 5.4, 1.11), "MWG": (57.7, 1062, 6.7, 6.8, -0.10),
    "FRT": (53.8, 799, 7.6, 8.0, -0.36), "STB": (51.5, 1778, 3.4, 4.5, -1.14),
    "PVP": (65.7, 198, 4.3, 5.7, -1.32), "HDB": (55.1, 791, 2.5, 4.4, -1.91),
    "PVT": (48.3, 1399, 0.3, 4.2, -3.85), "HAH": (48.3, 896, 0.6, 8.0, -7.39),
    "GEE": (75.0, 12, 2.2, 34.0, -31.78),
}
TV_PCT_NOW = {  # biểu đồ ④: "PE_pct hiện tại" (thực chất ngày 07/09/2026)
    "GEE": 0.4, "PVP": 12.4, "VPB": 15.2, "MWG": 4.4, "HDB": 16.8, "FRT": 12.0, "HAH": 9.6, "PVT": 12.4,
}
TV_TOP25 = ["VTB", "GEX", "SZL", "BCE", "PPC", "BTT", "VNG", "CLC", "DSN", "GEE", "CCI", "PDN", "TPC",
            "QNP", "NAB", "DTT", "MIG", "HTI", "CLW", "DHA", "PJT", "VCB", "TDW", "S4A", "VDP"]
TV_REGIME = {  # biểu đồ ③ (khi tín hiệu kích hoạt): r60, r120, hit, n
    "<6": (2.7, 10.2, 52, 1299), "6-8": (4.2, 8.4, 53, 64597),
    "8-10": (11.5, 21.2, 71, 3522), ">10": (-2.2, -2.7, 40, 3510),
}
TV_HEAD = {"ls_hien_tai": 11.78, "nguong": 13, "so_ma_tin_hieu": 259, "hit_tb": 53.5, "so_ma": 368,
           "macro_pe": 9.5, "macro_pe_fair": 13.2, "macro_ls": 7.60, "macro_ey": 10.57, "macro_erp": 2.97,
           "macro_tichluy_hit60": 61, "macro_tichluy_r120": 3.3, "macro_tichluy_ngay": 1827}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def r2(x, nd=2):
    """Số → float làm tròn; NaN/None → None (JSON null)."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(v) else round(v, nd)


# ───────────────────────────── 1. Đọc nguồn ─────────────────────────────

def _col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def parse_bloomberg(path: Path) -> pd.DataFrame:
    """Đọc Data_01..Data_09: mỗi mã 1 khối 8 cột (Ngày, PX_LAST, PX_VOLUME, CUR_MKT_CAP, PE, PB, PS, trống)."""
    from lxml import etree
    import openpyxl

    z = zipfile.ZipFile(path)
    ss = ["".join(si.itertext()) for si in etree.fromstring(z.read("xl/sharedStrings.xml")).iter(NS + "si")]
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    names = {ws.title: i + 1 for i, ws in enumerate(wb.worksheets)}
    tick_map = {}  # (sheet_index, block) -> ticker
    for row in wb["Tickers"].iter_rows(min_row=3, values_only=True):
        tk, sh, col = row[2], row[3], row[4]
        if isinstance(tk, str) and tk.endswith(" Equity") and sh in names and isinstance(col, str):
            tick_map[(names[sh], _col_index(col) // 8)] = tk.replace(" VM Equity", "").strip()
    wb.close()
    rx = re.compile(r"([A-Z]+)(\d+)")
    parts = []
    for sname, si in names.items():
        if not sname.startswith("Data_"):
            continue
        hdr, data = {}, {}
        with z.open(f"xl/worksheets/sheet{si}.xml") as f:
            for _, el in etree.iterparse(f, events=("end",), tag=NS + "c"):
                m = rx.match(el.get("r"))
                c, r = _col_index(m.group(1)), int(m.group(2))
                t, v = el.get("t"), el.find(NS + "v")
                if v is not None and v.text is not None:
                    if r == 1 and c % 8 == 1:
                        hdr[c // 8] = (ss[int(v.text)] if t == "s" else v.text).replace(" VM Equity", "").strip()
                    elif r >= 3 and t is None:
                        blk, off = divmod(c, 8)
                        if off < 7:
                            data.setdefault(blk, {}).setdefault(r, [np.nan] * 7)[off] = float(v.text)
                el.clear()
                while el.getprevious() is not None:
                    del el.getparent()[0]
        for blk, rows in data.items():
            tk = tick_map.get((si, blk)) or hdr.get(blk)
            if not tk:
                log(f"  ! bỏ khối không rõ mã: {sname} khối {blk}")
                continue
            if hdr.get(blk) and tick_map.get((si, blk)) and hdr[blk] != tick_map[(si, blk)]:
                log(f"  ! lệch tên mã {sname}/{blk}: dòng 1={hdr[blk]} Tickers={tick_map[(si, blk)]}")
            a = np.array(list(rows.values()), dtype=float)
            d = pd.DataFrame(a, columns=["date", "px", "vol", "mcap", "pe", "pb", "ps"])
            d.insert(0, "tk", tk)
            parts.append(d)
        log(f"  {sname}: {len(data)} khối")
    df = pd.concat(parts, ignore_index=True)
    df = df[df.date.notna()].copy()
    df["date"] = pd.to_datetime("1899-12-30") + pd.to_timedelta(df.date.round(), unit="D")
    df = df.drop_duplicates(["tk", "date"], keep="last").sort_values(["tk", "date"]).reset_index(drop=True)
    return df


def parse_fiin(path: Path):
    """Trả (Series LS % theo ngày, tăng dần; dict mô tả thứ tự gốc của tệp)."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    title, rows = None, []
    for r in ws.iter_rows(values_only=True):
        if r and r[0] == "STT":
            title = r[3]
            continue
        if title and isinstance(r[0], int) and r[2] is not None and r[3] is not None:
            rows.append((pd.Timestamp(r[2]), float(r[3]) * 100.0))
    wb.close()
    if not rows:
        raise SystemExit("FiinProX: không tìm thấy dòng dữ liệu")
    s = pd.Series({d: v for d, v in rows}).sort_index()
    info = {
        "chuoi": (title or "").replace("\n", " "),
        "dong_dau_tep": {"ngay": rows[0][0].strftime("%Y-%m-%d"), "ls": r2(rows[0][1])},
        "dong_cuoi_tep": {"ngay": rows[-1][0].strftime("%Y-%m-%d"), "ls": r2(rows[-1][1])},
        "moi_nhat": {"ngay": s.index[-1].strftime("%Y-%m-%d"), "ls": r2(s.iloc[-1])},
        "cu_nhat": {"ngay": s.index[0].strftime("%Y-%m-%d"), "ls": r2(s.iloc[0])},
        "so_dong": len(s),
    }
    return s, info


def load_names() -> dict:
    if not VNSTORE.exists():
        return {}
    try:
        c = sqlite3.connect(f"file:{VNSTORE}?mode=ro", uri=True)
        rows = c.execute("select symbol, ten, san, nganh, nhom from ma").fetchall()
        c.close()
    except sqlite3.Error as e:
        log("  ! vnstore:", e)
        return {}
    return {s: {"ten": t or "", "san": sa or "", "nganh": ng or "", "nhom": nh or ""} for s, t, sa, ng, nh in rows}


# ───────────────────────────── 2. Tính toán ─────────────────────────────

def thr_tv(ls):
    return np.maximum(5.0, 40.0 - 4.0 * (ls - 5.0))


def rolling_q_varying(pe: np.ndarray, thr: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """Trần P/E kích hoạt ở ngày i: P/E giả định v của ngày i thoả rank(pct=True, method="max") ≤ ngưỡng khi
    #(249 phiên trước ≤ v) + 1 ≤ k với k = floor(n·thr/100), n = số giá trị hợp lệ kể cả v. Tức v < giá trị thứ k
    của 249 phiên trước (đã sắp). Trả giá trị đó (biên trên, loại trừ)."""
    out = np.full(len(idx), np.nan)
    for j, i in enumerate(idx):
        if not np.isfinite(thr[i]):
            continue
        w = pe[max(0, i - WIN + 1): i]
        w = np.sort(w[np.isfinite(w)])
        n = len(w) + 1
        if n < MINP:
            continue
        k = int(math.floor(n * thr[i] / 100.0))
        if 1 <= k <= len(w):
            out[j] = w[k - 1]
    return out


def compute(df: pd.DataFrame, ls: pd.Series) -> pd.DataFrame:
    # LS kéo tới ngày giá cuối cùng (FiinProX dừng ở mốc tháng; giữ giá trị cuối, ghi rõ as-of ở trang)
    lsd = ls.reindex(pd.date_range(ls.index[0], max(ls.index[-1], df.date.max())), method="ffill")
    out = []
    for tk, g in df.groupby("tk", sort=True):
        g = g.reset_index(drop=True).copy()
        g.loc[g.pe <= 0, "pe"] = np.nan
        # method="max" = tỷ lệ cửa sổ ≤ hôm nay: khớp tuyệt đối percentile TV in (cả 8 mã watchlist + 25 mã top)
        g["pct"] = g.pe.rolling(WIN, min_periods=MINP).rank(pct=True, method="max") * 100.0
        lsv = ls.reindex(g.date, method="ffill").to_numpy()
        lsv[(g.date < ls.index[0]).to_numpy()] = np.nan
        g["ls"] = lsv
        g["thr"] = thr_tv(g.ls)
        g["sig"] = (g.pct <= g.thr) & g.ls.notna()
        # Giá thoát = giá giao dịch gần nhất ≤ t+h (phiên không giao dịch có PX trống; shift thô sẽ ra NaN và làm rơi đợt)
        px_ff = g.px.ffill()
        for h in HORIZONS:
            g[f"r{h}"] = (px_ff.shift(-h) / g.px - 1.0) * 100.0
        g["ey"] = 100.0 / g.pe
        g["erp"] = g.ey - g.ls
        # round: LS đi bước 0,1 điểm; không làm tròn thì nhiễu số thực đẩy các mức ±0,1/±0,5 sang nhóm bên cạnh
        g["dls6m"] = np.round((lsd - lsd.shift(182)).reindex(g.date).to_numpy(), 4)
        # Bản không nhìn trước EPS: Bloomberg ghi EPS quý vào NGÀY CUỐI QUÝ (trước khi BCTC công bố 3–7 tuần).
        # EPS dùng ở ngày t = EPS ngầm định (PX/PE) của ngày cuối cùng ≤ t − 45 ngày (hạn công bố BCTC hợp nhất quý).
        eps_s = g.px / g.pe
        notrade = g.px.isna()
        eps_s = eps_s.where(~notrade, eps_s.ffill())   # phiên không giao dịch: mang EPS gần nhất; phiên lỗ (PE trống, có giá) giữ NaN
        eps = eps_s.to_numpy()
        src_d = (g.date + pd.Timedelta(days=EPS_LAG_DAYS)).to_numpy()
        k = np.searchsorted(src_d, g.date.to_numpy(), side="right") - 1
        eps45 = np.where(k >= 0, eps[np.clip(k, 0, None)], np.nan)
        g["pe45"] = g.px / eps45
        g["pct45"] = g.pe45.rolling(WIN, min_periods=MINP).rank(pct=True, method="max") * 100.0
        g["sig45"] = (g.pct45 <= g.thr) & g.ls.notna()
        g["erp45"] = 100.0 / g.pe45 - g.ls
        g["lo250"] = g.px.rolling(WIN, min_periods=200).min()
        g["co52"] = g.lo250.notna() & g.px.notna()
        g["brk52"] = g.co52 & (g.px <= g.lo250)
        g["near52"] = g.co52 & (g.px <= g.lo250 * 1.03) & ~g.brk52
        out.append(g)
    a = pd.concat(out, ignore_index=True)
    elig = a.ls.notna() & a.pct.notna() & a.r60.notna()
    mean_by_date = a[elig].groupby("date").r60.mean()
    a["xs60"] = a.r60 - a.date.map(mean_by_date)
    elig45 = a.ls.notna() & a.pct45.notna() & a.r60.notna()
    a["xs45"] = a.r60 - a.date.map(a[elig45].groupby("date").r60.mean())
    a["carry60"] = a.ls * 60 / 250
    return a


def bucket_dir(d):
    if d is None or not np.isfinite(d):
        return None
    if d < -0.5:
        return "giảm mạnh"
    if d < -0.1:
        return "giảm"
    if d <= 0.1:
        return "đi ngang"
    if d <= 0.5:
        return "tăng"
    return "tăng mạnh"


DIR_ORDER = ["giảm mạnh", "giảm", "đi ngang", "tăng", "tăng mạnh"]
LEV_EDGES, LEV_LAB = [0, 6, 8, 10, 100], ["<6%", "6–8%", "8–10%", "≥10%"]
ERP_EDGES, ERP_LAB = [-999, -3, 0, 2, 5, 10, 999], ["<−3", "−3…0", "0…2", "2…5", "5…10", ">10"]


def agg_stats(x: pd.DataFrame) -> dict:
    n = int(len(x))
    if n == 0:
        return {"n": 0}
    return {"n": n, "r60": r2(x.r60.mean()), "hit": r2((x.r60 > 0).mean() * 100, 1),
            "xs": r2(x.xs60.mean()), "r120": r2(x.r120.mean()), "r20": r2(x.r20.mean()),
            "ma_n": int(x.tk.nunique()) if "tk" in x else None}


def tstat_p(v: np.ndarray):
    v = v[np.isfinite(v)]
    if len(v) < 3 or np.std(v, ddof=1) == 0:
        return None
    t = v.mean() / (np.std(v, ddof=1) / math.sqrt(len(v)))
    try:
        from scipy import stats
        return float(2 * stats.t.sf(abs(t), len(v) - 1))
    except Exception:
        return float(math.erfc(abs(t) / math.sqrt(2)))


def episodes(g: pd.DataFrame) -> list:
    idx = np.where(g.sig.to_numpy())[0]
    if len(idx) == 0:
        return []
    starts = idx[np.r_[True, np.diff(idx) > EP_GAP]]
    ends = idx[np.r_[np.diff(idx) > EP_GAP, True]]
    eps = []
    for s, e in zip(starts, ends):
        r = g.iloc[s]
        eps.append({
            "tu": r.date.strftime("%Y-%m-%d"), "den": g.iloc[e].date.strftime("%Y-%m-%d"),
            "so_phien_tin_hieu": int(g.sig.iloc[s:e + 1].sum()), "do_dai": int(e - s + 1),
            "px": r2(r.px, 0), "pe": r2(r.pe), "pct": r2(r.pct, 1), "nguong": r2(r.thr, 1), "ls": r2(r.ls),
            "huong_ls": bucket_dir(r.dls6m), "dls6m": r2(r.dls6m), "erp": r2(r.erp),
            "r20": r2(r.r20), "r60": r2(r.r60), "r120": r2(r.r120), "xs60": r2(r.xs60),
            "vuot_lai_tg": None if not np.isfinite(r.r60) else bool(r.r60 > r.carry60),
            "day52": bool(r.brk52), "sat52": bool(r.near52),
        })
    return eps


def onsets(g: pd.DataFrame, step: int = 60) -> list:
    """Mốc vào độc lập: ngày kích hoạt đầu tiên, rồi ngày kích hoạt kế tiếp cách mốc trước ≥ step phiên, để cửa sổ
    60 phiên của các mốc không chồng nhau (các đợt cách 10 phiên vẫn dùng chung phần lớn đường giá)."""
    idx = np.where(g.sig.to_numpy())[0]
    out, last = [], -10 ** 9
    for i in idx:
        if i - last >= step:
            out.append(i)
            last = i
    return out


def ticker_payload(tk: str, g: pd.DataFrame, names: dict, last_full: pd.Timestamp, prov_snap) -> dict:
    g = g.reset_index(drop=True)
    base = g[g.ls.notna() & g.r60.notna()]
    sig = g[g.sig & g.r60.notna()]
    elig = g[g.ls.notna() & g.pct.notna() & g.r60.notna()]
    tv_stat = {}
    for h in HORIZONS:
        s, b = g[g.sig & g[f"r{h}"].notna()], g[g.ls.notna() & g[f"r{h}"].notna()]
        tv_stat[f"h{h}"] = {"n": int(len(s)), "hit": r2((s[f"r{h}"] > 0).mean() * 100, 1) if len(s) else None,
                           "ret": r2(s[f"r{h}"].mean()), "base": r2(b[f"r{h}"].mean()),
                           "alpha": r2(s[f"r{h}"].mean() - b[f"r{h}"].mean()) if len(s) else None}
    # bản cắt đúng ngày báo cáo TV (07/09) để đối chiếu số in
    gc = g[g.date <= pd.Timestamp(CUT_TV)].copy()
    for h in (60,):
        gc[f"r{h}"] = (gc.px.shift(-h) / gc.px - 1.0) * 100.0
    sc, bc = gc[gc.sig & gc.r60.notna()], gc[gc.ls.notna() & gc.r60.notna()]
    tai_lap_cut = {"n": int(len(sc)), "hit": r2((sc.r60 > 0).mean() * 100, 1) if len(sc) else None,
                   "ret": r2(sc.r60.mean()), "base": r2(bc.r60.mean()),
                   "alpha": r2(sc.r60.mean() - bc.r60.mean()) if len(sc) else None,
                   "pct_0709": r2(gc.pct.iloc[-1], 1) if len(gc) else None}
    s4, b4 = g[g.sig45 & g.r60.notna()], g[g.ls.notna() & g.r60.notna()]
    tai_lap_eps45 = {"n": int(len(s4)), "hit": r2((s4.r60 > 0).mean() * 100, 1) if len(s4) else None,
                     "ret": r2(s4.r60.mean()), "base": r2(b4.r60.mean()),
                     "alpha": r2(s4.r60.mean() - b4.r60.mean()) if len(s4) else None,
                     "xs": r2(s4.xs45.mean()) if len(s4) else None}
    tv_goc = {}
    if tk in TV_RANK:
        tv_goc["alpha60"], tv_goc["hit60"] = TV_RANK[tk]
    if tk in TV_WATCH:
        h_, n_, rs, rb, al = TV_WATCH[tk]
        tv_goc.update({"hit60": h_, "n": n_, "ret60": rs, "base60": rb, "alpha60": al})
    if tk in TV_PCT_NOW:
        tv_goc["pct_hien_tai_in"] = TV_PCT_NOW[tk]
    if tk in TV_TOP25:
        tv_goc["top25_dang_tin_hieu"] = True

    gl = g[g.ls.notna()].reset_index(drop=True)
    eps = episodes(gl)
    on = gl.iloc[onsets(gl)]
    on = on[on.r60.notna()]
    ep_r = on.r60.to_numpy(float)
    ep_x = on.xs60.to_numpy(float)
    ep_x = ep_x[np.isfinite(ep_x)]
    theo_dot = {"n": len(eps), "n_do": int(len(ep_r)), "dinh_nghia": "mốc vào cách nhau ≥ 60 phiên",
                "hit": r2((ep_r > 0).mean() * 100, 1) if len(ep_r) else None,
                "r60_tb": r2(ep_r.mean()) if len(ep_r) else None,
                "r60_trung_vi": r2(np.median(ep_r)) if len(ep_r) else None,
                "xs_tb": r2(ep_x.mean()) if len(ep_x) else None, "p_xs": r2(tstat_p(ep_x), 3)}

    # theo hướng LS × tín hiệu (ngày)
    huong = []
    gd = elig.assign(h=elig.dls6m.map(bucket_dir))
    for k in DIR_ORDER:
        sub = gd[gd.h == k]
        huong.append({"huong": k, "tin_hieu": agg_stats(sub[sub.sig]), "moi_ngay": agg_stats(sub)})
    muc = []
    lv = pd.cut(elig.ls, LEV_EDGES, right=False, labels=LEV_LAB)
    for k in LEV_LAB:
        sub = elig[lv == k]
        muc.append({"muc": k, "tin_hieu": agg_stats(sub[sub.sig]), "moi_ngay": agg_stats(sub)})
    erp_rows = []
    eb = pd.cut(elig.erp, ERP_EDGES, labels=ERP_LAB)
    for k in ERP_LAB:
        sub = elig[eb == k]
        erp_rows.append({"erp": k, "moi_ngay": agg_stats(sub), "tin_hieu": agg_stats(sub[sub.sig])})

    # trạng thái phiên đủ cuối cùng + phiên dở
    def snap(row):
        if row is None:
            return None
        return {"ngay": row.date.strftime("%Y-%m-%d"), "px": r2(row.px, 0), "pe": r2(row.pe), "pct": r2(row.pct, 1),
                "ls": r2(row.ls), "nguong": r2(row.thr, 1), "kich_hoat": bool(row.sig) if np.isfinite(row.pct) else None,
                "ey": r2(row.ey), "erp": r2(row.erp), "dls6m": r2(row.dls6m), "huong_ls": bucket_dir(row.dls6m),
                "day52": bool(row.brk52), "sat52": bool(row.near52), "lo250": r2(row.lo250, 0)}
    gf = g[g.date <= last_full]
    cur = snap(gf.iloc[-1]) if len(gf) else None
    prov = snap(prov_snap) if prov_snap is not None else None
    # ngưỡng P/E hiện tại theo luật TV + giá tương ứng (EPS ngầm định = PX/PE ở phiên đủ cuối)
    pe_arr = g.pe.to_numpy(float)
    if cur and cur["pe"]:
        i = len(gf) - 1
        q = rolling_q_varying(pe_arr, g.thr.to_numpy(float), np.array([i]))[0]
        cur["pe_nguong"] = r2(q)
        cur["eps_ngam"] = r2(gf.px.iloc[-1] / gf.pe.iloc[-1], 1)
        cur["gia_nguong"] = r2(q * gf.px.iloc[-1] / gf.pe.iloc[-1], 0) if np.isfinite(q) else None
        # 250 P/E gần nhất (để script trong app tính lại percentile với giá live)
        tail = gf.tail(WIN)
        cur["pe250"] = [r2(v) for v in tail.pe]
        cur["pe250_tu"] = tail.date.iloc[0].strftime("%Y-%m-%d")

    # chuỗi tuần cho biểu đồ
    gw = g.assign(wk=g.date.dt.to_period("W-FRI"))
    last_idx = gw.drop_duplicates("wk", keep="last").index.to_numpy()
    sig_wk = gw.groupby("wk").sig.any()
    w = g.loc[last_idx]
    qthr = rolling_q_varying(pe_arr, g.thr.to_numpy(float), last_idx)
    p10 = g.pe.rolling(WIN, min_periods=MINP).quantile(0.10).to_numpy()[last_idx]
    p50 = g.pe.rolling(WIN, min_periods=MINP).quantile(0.50).to_numpy()[last_idx]
    p90 = g.pe.rolling(WIN, min_periods=MINP).quantile(0.90).to_numpy()[last_idx]
    chuoi = {
        "x": [d.strftime("%Y-%m-%d") for d in w.date],
        "px": [r2(v, 0) for v in w.px], "pe": [r2(v) for v in w.pe], "pct": [r2(v, 1) for v in w.pct],
        "nguong": [r2(v, 1) for v in w.thr], "pe_nguong": [r2(v) for v in qthr],
        "p10": [r2(v) for v in p10], "p50": [r2(v) for v in p50], "p90": [r2(v) for v in p90],
        "ey": [r2(v) for v in w.ey], "ls": [r2(v) for v in w.ls], "erp": [r2(v) for v in w.erp],
        "tin_hieu_tuan": [bool(sig_wk.get(k, False)) for k in gw.loc[last_idx, "wk"]],
    }
    meta = names.get(tk, {})
    canh_bao = []
    if theo_dot["n_do"] < 5:
        canh_bao.append(f"Chỉ {theo_dot['n_do']} đợt tín hiệu độc lập có kết quả 60 phiên, mọi tỷ lệ thắng ở mã này là nhiễu.")
    if g.pe.notna().sum() < WIN:
        canh_bao.append(f"Lịch sử P/E chỉ {int(g.pe.notna().sum())} phiên (< 250): percentile tính trên cửa sổ ngắn (min 60 phiên như bản gốc).")
    if cur and cur.get("pe") is None:
        canh_bao.append("Bloomberg không có P/E ở phiên cuối (lỗ hoặc thiếu dữ liệu), luật TV không chấm được.")
    return {
        "ma": tk, "ten": meta.get("ten", ""), "san": meta.get("san", ""), "nganh": meta.get("nganh", ""),
        "nhom": meta.get("nhom", ""),
        "du_lieu": {"tu": g.date.iloc[0].strftime("%Y-%m-%d"), "den": g.date.iloc[-1].strftime("%Y-%m-%d"),
                    "so_phien": int(len(g)), "so_phien_pe": int(g.pe.notna().sum()),
                    "pe_tu": g.loc[g.pe.notna(), "date"].min().strftime("%Y-%m-%d") if g.pe.notna().any() else None},
        "hien_tai": cur, "phien_do": prov,
        "tv_goc": tv_goc, "tai_lap_0709": tai_lap_cut, "tai_lap": tv_stat, "tai_lap_eps45": tai_lap_eps45,
        "theo_dot": theo_dot, "dot": eps,
        "theo_huong_ls": huong, "theo_muc_ls": muc, "theo_erp": erp_rows,
        "lai_tg": {"n": int(len(sig)), "vuot_pct": r2((sig.r60 > sig.carry60).mean() * 100, 1) if len(sig) else None,
                   "du_tb": r2((sig.r60 - sig.carry60).mean()) if len(sig) else None},
        "chuoi": chuoi, "canh_bao": canh_bao,
    }


def pooled_audit(a: pd.DataFrame) -> dict:
    E = a[a.ls.notna() & a.pct.notna() & a.r60.notna()]
    S = E[E.sig]
    out = {"so_quan_sat": int(len(E)), "so_ma": int(E.tk.nunique()),
           "tu": E.date.min().strftime("%Y-%m-%d"), "den_r60": E.date.max().strftime("%Y-%m-%d")}
    out["gop"] = {"moi_ngay": agg_stats(E), "tin_hieu": agg_stats(S),
                  "alpha_kieu_tv": r2(S.r60.mean() - E.r60.mean()),
                  "xs_hit": r2((S.xs60 > 0).mean() * 100, 1)}
    per = S.groupby("date").xs60.mean()
    out["gop"]["ngay_xs_duong_pct"] = r2((per > 0).mean() * 100, 1)
    breadth = (S.groupby("date").size() / E.groupby("date").size()).fillna(0)
    out["do_phu_tin_hieu"] = {"tb": r2(breadth.mean() * 100, 1), "trung_vi": r2(breadth.median() * 100, 1),
                              "p90": r2(breadth.quantile(0.9) * 100, 1)}
    rows = []
    for thr in (5, 10, 13, 20, 30, 40):
        x = E[E.pct <= thr]
        rows.append({"nguong": f"cố định {thr}%", **agg_stats(x), "alpha": r2(x.r60.mean() - E.r60.mean())})
    rows.append({"nguong": "động TV", **agg_stats(S), "alpha": r2(S.r60.mean() - E.r60.mean())})
    out["nguong"] = rows
    h = E.dls6m.map(bucket_dir)
    out["huong_ls"] = [{"huong": k, "tin_hieu": agg_stats(S[h[S.index] == k]), "moi_ngay": agg_stats(E[h == k])}
                       for k in DIR_ORDER]
    lv = pd.cut(S.ls, LEV_EDGES, right=False, labels=LEV_LAB)
    hs = S.dls6m.map(bucket_dir).map(lambda v: None if v is None else ("giảm" if "giảm" in v else ("tăng" if "tăng" in v else "đi ngang")))
    mx = []
    for k in LEV_LAB:
        for d in ("giảm", "đi ngang", "tăng"):
            x = S[(lv == k) & (hs == d)]
            if len(x):
                st = agg_stats(x)
                st.update({"muc": k, "huong": d, "tu": x.date.min().strftime("%m/%Y"), "den": x.date.max().strftime("%m/%Y")})
                mx.append(st)
    out["muc_x_huong"] = mx
    lvl = pd.cut(S.ls, LEV_EDGES, right=False, labels=LEV_LAB)
    out["muc_ls_tv"] = []
    for k, key in zip(LEV_LAB, ["<6", "6-8", "8-10", ">10"]):
        x = S[lvl == k]
        st = agg_stats(x)
        st.update({"muc": k, "tv": dict(zip(["r60", "r120", "hit", "n"], TV_REGIME[key])),
                   "tu": x.date.min().strftime("%m/%Y") if len(x) else None,
                   "den": x.date.max().strftime("%m/%Y") if len(x) else None})
        out["muc_ls_tv"].append(st)
    eb = pd.cut(E.erp, ERP_EDGES, labels=ERP_LAB)
    out["erp"] = [{"erp": k, "moi_ngay": agg_stats(E[eb == k]), "tin_hieu": agg_stats(S[eb[S.index] == k])}
                  for k in ERP_LAB]
    out["vung52"] = [
        {"nhom": "Tín hiệu & giá ≤ đáy 52 tuần", **agg_stats(S[S.brk52])},
        {"nhom": "Tín hiệu & cách đáy 52 tuần ≤ 3%", **agg_stats(S[S.near52])},
        {"nhom": "Tín hiệu & xa đáy 52 tuần", **agg_stats(S[S.co52 & ~S.brk52 & ~S.near52])},
        {"nhom": "Mọi ngày giá ≤ đáy 52 tuần (không cần P/E)", **agg_stats(E[E.brk52])},
        {"nhom": "Mọi ngày (nền)", **agg_stats(E)},
    ]
    out["lai_tg"] = {"vuot_pct": r2((S.r60 > S.carry60).mean() * 100, 1), "du_tb": r2((S.r60 - S.carry60).mean())}
    # ── độ bền (bổ sung sau kiểm định đối kháng 06/10) ──
    xs = S.xs60.to_numpy()
    q99, q95 = np.nanquantile(xs, 0.99), np.nanquantile(xs, 0.95)
    per_s = S.groupby("date").xs60.mean()
    nons = E[~E.sig]
    spread = (per_s - nons.groupby("date").xs60.mean()).dropna()
    out["do_ben"] = {
        "xs_trung_vi": r2(np.nanmedian(xs)),
        "xs_bo_1pct_tot_nhat": r2(np.nanmean(xs[xs < q99])),
        "xs_bo_5pct_tot_nhat": r2(np.nanmean(xs[xs < q95])),
        "xs_theo_ngay": r2(per_s.mean()), "t_nw_xs_theo_ngay": r2(nw_t(per_s.to_numpy()), 1),
        "chenh_tin_hieu_vs_khong": r2(spread.mean()), "t_nw_chenh": r2(nw_t(spread.to_numpy()), 1),
        "alpha_vs_ngay_khong_tin_hieu": r2(S.r60.mean() - nons.r60.mean()),
        "so_ngay": int(per_s.size),
    }
    cover = len(S) / len(E)
    q_eq = float(np.nanquantile(E.pct, cover)) if len(E) else None
    out["do_ben"]["nguong_co_dinh_cung_do_phu"] = r2(q_eq, 1)
    out["do_ben"]["do_phu_pct"] = r2(cover * 100, 1)
    if q_eq is not None:
        x = E[E.pct <= q_eq]
        out["do_ben"]["xs_nguong_co_dinh_cung_do_phu"] = r2(x.xs60.mean())
        out["do_ben"]["xs_theo_ngay_nguong_co_dinh_cung_do_phu"] = r2(x.groupby("date").xs60.mean().mean())
    E4 = a[a.ls.notna() & a.pct45.notna() & a.r60.notna()]
    S4 = E4[E4.sig45]
    def ag45(x):
        st = agg_stats(x.assign(xs60=x.xs45))
        st["xs_theo_ngay"] = r2(x.groupby("date").xs45.mean().mean()) if len(x) else None
        return st
    eb4 = pd.cut(E4.erp45, ERP_EDGES, labels=ERP_LAB)
    out["eps_tre_45"] = {
        "gop": {"moi_ngay": ag45(E4), "tin_hieu": ag45(S4), "alpha_kieu_tv": r2(S4.r60.mean() - E4.r60.mean())},
        "nguong": [{"nguong": f"cố định {t}%", **ag45(E4[E4.pct45 <= t])} for t in (5, 10, 30)] +
                  [{"nguong": "động TV", **ag45(S4)}],
        "erp": [{"erp": k, "moi_ngay": ag45(E4[eb4 == k])} for k in ERP_LAB],
        "do_ben": {"xs_trung_vi": r2(np.nanmedian(S4.xs45)),
                   "t_nw_xs_theo_ngay": r2(nw_t(S4.groupby("date").xs45.mean().to_numpy()), 1)},
    }
    for r in out["nguong"]:
        lab = r["nguong"]
        x = S if lab.startswith("động") else E[E.pct <= float(lab.split()[2].rstrip("%"))]
        r["xs_theo_ngay"] = r2(x.groupby("date").xs60.mean().mean())
    return out


def nw_t(v, lag=60):
    """t-stat Newey-West (Bartlett) cho trung bình chuỗi theo ngày; lag 60 vì cửa sổ 60 phiên chồng nhau."""
    v = np.asarray(v, dtype=float)
    v = v[np.isfinite(v)]
    n = len(v)
    if n < lag + 10:
        return None
    e = v - v.mean()
    var = e @ e / n
    for k in range(1, lag + 1):
        var += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    return float(v.mean() / math.sqrt(var / n)) if var > 0 else None


def lag_audit(df: pd.DataFrame, ls: pd.Series) -> dict:
    """Độ bền khi LS trễ 1 tháng: chuỗi FiinProX là số THÁNG ('(M)') gán từ ngày 1 của tháng; nếu số tháng chỉ biết
    vào cuối tháng thì bản gốc nhìn trước tối đa ~1 tháng. Tính lại luật với LS dời sang tháng sau."""
    ls_lag = ls.copy()
    ls_lag.index = ls_lag.index + pd.DateOffset(months=1)
    ls_lag = ls_lag[~ls_lag.index.duplicated(keep="last")]   # 29–31/1 → 28/2 trùng ngày; giá trị trong tháng như nhau
    a = compute(df, ls_lag)
    E = a[a.ls.notna() & a.pct.notna() & a.r60.notna()]
    S = E[E.sig]
    lv = pd.cut(S.ls, LEV_EDGES, right=False, labels=LEV_LAB)
    h = E.dls6m.map(bucket_dir)
    return {"gop": {"moi_ngay": agg_stats(E), "tin_hieu": agg_stats(S)},
            "muc_ls": [{"muc": k, **agg_stats(S[lv == k])} for k in LEV_LAB],
            "huong_ls": [{"huong": k, "tin_hieu": agg_stats(S[h[S.index] == k])} for k in DIR_ORDER]}


def market_pe(df: pd.DataFrame, ls: pd.Series, dates) -> list:
    d = df[(df.pe > 0) & df.mcap.notna()]
    rows = []
    for dt in dates:
        x = d[d.date == dt]
        if x.empty:
            continue
        lsv = float(ls[ls.index <= dt].iloc[-1]) if (ls.index <= dt).any() else np.nan

        def harm(y):
            return y.mcap.sum() / (y.mcap / y.pe).sum()
        v = {"ngay": dt.strftime("%Y-%m-%d"), "so_ma": int(len(x)), "ls": r2(lsv),
             "harm_tat_ca": r2(harm(x)), "harm_bo_pe_tren40": r2(harm(x[x.pe <= 40])),
             "trung_vi": r2(x.pe.median()), "capw_so_hoc": r2((x.mcap * x.pe).sum() / x.mcap.sum())}
        for k in ("harm_tat_ca", "harm_bo_pe_tren40"):
            v["erp_" + k] = r2(100 / v[k] - lsv) if v[k] else None
        top = x.loc[x.mcap.idxmax()]
        v["ma_von_hoa_lon_nhat"] = {"ma": top.tk, "pe": r2(top.pe), "ty_trong_pct": r2(top.mcap / x.mcap.sum() * 100, 1)}
        bo = x[x.pe > 40]
        v["bo_pe_tren40"] = {"so_ma": int(len(bo)), "ty_trong_von_hoa_pct": r2(bo.mcap.sum() / x.mcap.sum() * 100, 1)}
        v["harm_bo_ma_lon_nhat"] = r2(harm(x[x.tk != top.tk]))
        v["erp_harm_bo_ma_lon_nhat"] = r2(100 / v["harm_bo_ma_lon_nhat"] - lsv) if v["harm_bo_ma_lon_nhat"] else None
        rows.append(v)
    return rows


def replication_compare(a: pd.DataFrame) -> dict:
    gc = a[a.date <= pd.Timestamp(CUT_TV)].copy()
    gc["r60c"] = gc.groupby("tk").px.transform(lambda s: (s.shift(-60) / s - 1) * 100)
    s = gc[gc.sig & gc.r60c.notna()]
    b = gc[gc.ls.notna() & gc.r60c.notna()]
    al = s.groupby("tk").r60c.mean() - b.groupby("tk").r60c.mean()
    rows = []
    for tk in list(TV_RANK) + [k for k in TV_WATCH if k not in TV_RANK]:
        tv = TV_WATCH[tk][4] if tk in TV_WATCH else TV_RANK[tk][0]
        rep = al.get(tk, np.nan)
        rows.append({"ma": tk, "tv": tv, "tai_lap": r2(rep), "lech": r2(rep - tv)})
    df = pd.DataFrame(rows).dropna()
    rho = df[["tv", "tai_lap"]].rank().corr().iloc[0, 1]
    last = gc.drop_duplicates("tk", keep="last")  # gc đã theo thứ tự (mã, ngày); tránh sort_values lỗi trên pandas/py3.14
    return {"bang": rows, "spearman": r2(rho, 3), "lech_trung_vi": r2(df.lech.abs().median()),
            "ty_le_trong_2pp": r2((df.lech.abs() <= 2).mean() * 100, 0),
            "so_ma_tin_hieu_0709": int(last.sig.sum()),
            "ls_0709": r2(last.ls.mode().iloc[0]) if last.ls.notna().any() else None}


def binom_sf(k: int, n: int, p: float) -> float:
    """P(X ≥ k), X ~ Binomial(n, p)."""
    if n <= 0:
        return 1.0
    return float(sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1)))


def detect_sessions(df: pd.DataFrame):
    c = df[df.pe.notna()].groupby("date").size()
    last = c.index[-1]
    prev = c.index[-2]
    if c[last] < 0.9 * c[prev]:
        return prev, last, {"ngay": last.strftime("%Y-%m-%d"), "so_ma_co_pe": int(c[last]),
                            "phien_truoc": int(c[prev])}
    return last, None, None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bbg", type=Path, default=BBG_DEFAULT)
    ap.add_argument("--fiin", type=Path, default=FIIN_DEFAULT)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--chi-ma", default="", help="chỉ ghi các mã này (phẩy), để thử nhanh")
    ap.add_argument("--khong-sau", action="store_true", help="bỏ lớp sâu (toanvu_pe_sau.py)")
    args = ap.parse_args(argv)
    t0 = time.time()
    for p in (args.bbg, args.fiin):
        if not p.exists():
            raise SystemExit(f"Thiếu tệp nguồn: {p}")
    out = args.out
    (out / "ma").mkdir(parents=True, exist_ok=True)
    (out / "cache").mkdir(exist_ok=True)
    h_bbg, h_fiin = sha256(args.bbg), sha256(args.fiin)
    cache = out / "cache" / f"bbg_{h_bbg[:16]}.parquet"
    if cache.exists():
        df = pd.read_parquet(cache)
        log(f"Bloomberg: dùng cache {cache.name}")
    else:
        log("Bloomberg: đang đọc xlsx (≈1 phút)…")
        df = parse_bloomberg(args.bbg)
        df.to_parquet(cache)
    ls, ls_info = parse_fiin(args.fiin)
    names = load_names()
    log(f"  {df.tk.nunique()} mã, {len(df)} dòng, {df.date.min().date()} → {df.date.max().date()}; LS {len(ls)} ngày")

    last_full, prov_date, prov_info = detect_sessions(df)
    # Phiên dở (ảnh chụp giữa phiên) KHÔNG vào thống kê: không làm giá thoát, không thành ngày tín hiệu.
    df_full = df[df.date <= last_full]
    a = compute(df_full, ls)
    prov_rows = {}
    if prov_date is not None:
        ap_ = compute(df[df.tk.isin(df[df.date == prov_date].tk.unique())], ls)
        for _, r in ap_[ap_.date == prov_date].iterrows():
            prov_rows[r.tk] = r
    log(f"Tính xong luật TV + kiểm định ({time.time() - t0:.0f}s)")

    # ── payload từng mã ──
    only = {x.strip().upper() for x in args.chi_ma.split(",") if x.strip()}
    rows = []
    for tk, g in a.groupby("tk", sort=True):
        if only and tk not in only:
            continue
        p = ticker_payload(tk, g, names, last_full, prov_rows.get(tk))
        (out / "ma" / f"{tk}.json").write_text(json.dumps(p, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
        cur = p["hien_tai"] or {}
        rows.append({"ma": tk, "ten": p["ten"], "nhom": p["nhom"], "nganh": p["nganh"],
                     "pe": cur.get("pe"), "pct": cur.get("pct"), "nguong": cur.get("nguong"),
                     "kich_hoat": cur.get("kich_hoat"), "ey": cur.get("ey"), "erp": cur.get("erp"),
                     "day52": cur.get("day52"), "sat52": cur.get("sat52"),
                     "n_ngay": p["tai_lap"]["h60"]["n"], "hit_ngay": p["tai_lap"]["h60"]["hit"],
                     "alpha_tv": p["tai_lap"]["h60"]["alpha"], "n_dot": p["theo_dot"]["n_do"],
                     "hit_dot": p["theo_dot"]["hit"], "xs_dot": p["theo_dot"]["xs_tb"], "p_dot": p["theo_dot"]["p_xs"],
                     "alpha_tv_goc": p["tv_goc"].get("alpha60")})
    log(f"Ghi {len(rows)} tệp mã ({time.time() - t0:.0f}s)")

    ep = pd.DataFrame(rows)
    sig_cnt = int(sum(1 for v in ep.kich_hoat if v is True)) if len(ep) else 0
    tong = {
        "phien_ban": VERSION, "tao_luc": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "nguon": {
            "bloomberg": {"tep": str(args.bbg), "sha256": h_bbg, "tu": df.date.min().strftime("%Y-%m-%d"),
                          "den": df.date.max().strftime("%Y-%m-%d"), "so_ma": int(df.tk.nunique()), "bac": "FACT-T2"},
            "fiinprox": {"tep": str(args.fiin), "sha256": h_fiin, **ls_info, "bac": "FACT-T2"},
            "bao_cao_tv": [str(TV_HTML), str(TV_MACRO_HTML)],
        },
        "phien_du_cuoi": last_full.strftime("%Y-%m-%d"), "phien_do": prov_info,
        "tv_in": TV_HEAD,
        "ls_hien_tai": r2(ls.iloc[-1]), "nguong_hien_tai": r2(float(thr_tv(ls.iloc[-1])), 1),
        "ls_dls6m": r2(float(ls[ls.index <= last_full].iloc[-1] - ls[ls.index <= last_full - pd.Timedelta(days=182)].iloc[-1])),
        "so_ma_kich_hoat": sig_cnt, "so_ma_cham": int(ep.pct.notna().sum()) if len(ep) else 0,
        "kiem_dinh": pooled_audit(a),
        "tai_lap": replication_compare(a),
        "pe_thi_truong": market_pe(df, ls, [pd.Timestamp(CUT_TV), last_full]),
        "dot_tong": {"n_dot": int(ep.n_dot.sum()) if len(ep) else 0,
                     "ma_p05_duong": int(((ep.p_dot < 0.05) & (ep.xs_dot > 0)).sum()) if len(ep) else 0,
                     "ma_p05_am": int(((ep.p_dot < 0.05) & (ep.xs_dot < 0)).sum()) if len(ep) else 0,
                     "ma_kiem": int(ep.p_dot.notna().sum()) if len(ep) else 0},
        "bang": rows,
    }
    dt = tong["dot_tong"]
    dt["p_nhi_thuc_duong"] = r2(binom_sf(dt["ma_p05_duong"], dt["ma_kiem"], 0.025), 4)
    log("Độ bền: LS trễ 1 tháng…")
    tong["ls_tre_1_thang"] = lag_audit(df_full, ls)
    if not only:
        (out / "tong_quan.json").write_text(json.dumps(tong, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    (out / "MANIFEST.json").write_text(json.dumps({
        "phien_ban": VERSION, "tao_luc": tong["tao_luc"], "bbg_sha256": h_bbg, "fiin_sha256": h_fiin,
        "so_ma": len(rows), "phien_du_cuoi": tong["phien_du_cuoi"], "chi_ma": sorted(only)}, ensure_ascii=False, indent=1))
    if not args.khong_sau:
        # Lớp sâu: trang rổ VNINDEX/VN30/VN100, pha giá, tần suất có điều kiện, chủ thể, lãi suất, bảng bằng chứng
        import toanvu_pe_sau
        toanvu_pe_sau.build_sau(a, df_full, ls, ls_info, names, out, last_full, rows, only or None)
    log(f"Xong {time.time() - t0:.0f}s → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
