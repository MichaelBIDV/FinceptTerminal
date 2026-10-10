#!/usr/bin/env python3
"""
Fincept Terminal: Chaebol Reflex live engine (tab "msn_reflex", label "Chaebol Reflex").

Shared engine for the 32 ownership groups of the Chaebol Map. Reads the group registry (schema
"chaebol_reflex_nhom/1"), loads the group's tickers from the same local stores as msn_reflex.Kho and computes the
live parent-child lag file: dated look-through, parent ÷ look-through (3Y + full range), AR(1), zigzag legs,
capture, 250-session breakouts, lead/lag, lagged correlations, HHP σ, KL ÷ TB20, foreign flow and returns.
Stdlib only, Python 3.9+, NO network, SQLite read-only (msn_reflex.Kho opens vnstore with mode=ro). It renders no
page: chaebol_reflex_trang.py builds the vnblocks pages from to_json(). It never emits buy/sell, NAV, position-size
or target-price text (CỔNG v1.7 DỪNG); HHP fields such as fa_rec / fa_tp / forward.tp are never read.

REGISTRY  <CHAEBOL_REFLEX_DIR>/nhom.json (default ~/SECOND BRAIN-OBSIDIAN/_System/knowledge_os/chaebol_reflex)
  load_registry(root=None) -> (Registry, [warnings]). Registry is the JSON dict itself ("nhom" holds Nhom objects)
  with .nhom(id) -> Nhom | None and .nhom_of_ma(ma) -> [ids]; module-level nhom(id, reg=None) and
  nhom_of_ma(ma, reg=None) load the default registry when reg is None. A missing / broken file gives an empty
  registry plus a warning. Group checks: id ASCII slug [a-z0-9_]+ (unique), me = ticker or null. Stake rows
  so_huu[] = {"tu": "YYYY-MM-DD", "ty_le": 0 < x <= 1, "loai": "phap_ly"|"hieu_dung" (empty = phap_ly), "tier",
  "nguon", "ap_dung"}: a row without tu / tier / nguon or with ty_le outside (0, 1] is dropped with a warning
  (no default stakes, a percent such as 71.7 is not guessed). "ap_dung": false = pending CBTT: listed by
  Nhom.pending(ma), never applied.
  Nhom.weight(ma, d, loai=None) / weight_row(...) -> stake in force at d: the NEWEST applied row with tu <= d
  (file order breaks ties, newer first). Before the first row -> 0.0 (spec: "trọng số 0", with a warning when it
  matters); no row at all -> None. loai None = "hieu_dung" rows when the member has any, else "phap_ly".
  Semantics: phap_ly = direct legal stake of the member's own "me" (holding node); hieu_dung = effective economic
  stake of the GROUP parent. The look-through weight of a member (LiveNhom.w_lt) is its hieu_dung stake, else its
  phap_ly stake when its "me" is the group parent (or empty), else phap_ly × w_lt(its "me") along the chain; a "me"
  that is not a ticker (an unlisted holding) needs a hieu_dung row, otherwise the member is left out of LT.
  Members without a usable stake, without prices, unlisted / listed abroad ("niem_yet": "chưa" | "nước ngoài")
  are listed but left out of LT with a warning. A "tang" layer {"me": X, "con": [...]} uses the con's phap_ly
  stakes, which must be held directly by X.

KhoNhom(p, den, warnings, syms, he_sinh_thai=(), vc_syms=None, lite=False)  subclass of msn_reflex.Kho (extra=syms;
  Masan's own SYMS that are not in syms are skipped). vnstore rows for every ticker of syms; the per-ticker files only
  for vc_syms (default all; ensure_vc(sym) adds one). lite (TỔNG QUAN): no HHP / WiData / ecosystem / shareholder /
  relationship / fs-income files, and Vietcap rows older than LITE_YEARS are not decoded (kho.vc_tu).
  Adds: kho.hhp_ser[sym] (hhp_vn100_series/<SYM>.json, pb/pe weekly price & base),
  kho.hhp_ma(sym) (by_ticker pb / pe blocks only), kho.cd[sym] (vc_lk shareholder rows, publicDate <= den),
  kho.rel[sym] (vc_lk relationship: listed subsidiaries / affiliates), kho.organ[sym] (details organCode, names,
  listingDate),
  kho.fs[sym] (vc_lk fs-income) and kho.eco[sym] = (ecosystem key, member dict) of chaebol_ecosystems.json for
  the he_sinh_thai keys.
  Parsed vc_lk price histories, WiData and the small JSON files are cached at module level (key: path, mtime,
  size, den), so one process building many groups (TỔNG QUAN) parses each file once; clear_cache() empties it.

LiveNhom(kho, nhom, dossier=None, warnings=None, co_so=None, lite=False)  computes everything at construction;
  build_live(id_or_nhom, den=None, root=None, dossier=None) wires registry + paths + KhoNhom. Prices: adjusted daily
  closes = vnstore nen_ngay extended BEFORE its first and AFTER its last row by Vietcap closePriceAdjusted, each part
  rescaled on an anchor day present in both (within SPLICE_SESSIONS nen sessions; no anchor → that part dropped with
  a warning, never factor 1) — noi_chuoi(); rows before the vc_lk details listingDate are dropped (Vietcap keeps
  older rows of a reused ticker, e.g. VHM). Weeks are Mon–Fri labelled by Friday (msn_reflex.weeks_of); a week is
  complete when its Friday <= data_to. Market caps use RAW prices (msn_reflex.Kho.mcap, no profile share count for
  any parent); a cap older than STALE_MCAP_DAYS before the date counts as missing, and a cap from a vnstore history
  row (adjusted × today's shares: no Vietcap file, or before its first row) is refused. The time axis is the base
  ticker: the parent, else co_so when given (an ALL-IN-ONE cell passes the FULL group's axis), else chon_co_so():
  the largest vnstore cap among members whose nen reaches the latest nen day. data_to = the base's last session;
  a member lagging it (or a parent lagging its members) by more than LAG_WARN_DAYS is warned. lite = TỔNG QUAN:
  ratios, captures and returns only (no breakouts, lead/lag, correlations, σ, KL, flows, signals, charts).
  do_dau_hieu(key, ma=None, tham_so=None) -> {"khoa", "ma", "thay": bool|None, "ngay": iso|None, "gia_tri",
    "ghi_chu", "tham_so", "tier": "EST"}. Keys (default thresholds in DAU_HIEU):
      bung_pha_250 {phien}  a close above the max of the previous `phien` sessions after the latest trough
      kl_tuan_tb20 {k}      last complete week's KL ÷ mean of the 20 previous weeks >= k
      vuot_ma200 {}         last complete weekly close > MA40 of weekly closes
      cach_dinh_52t {x}     % below the 52-week high <= x
      pb_sigma {s, phep}    HHP σ (P/B, else P/E): s >= 0 tests z >= s (expensive side), s < 0 tests z <= s
                            (cheap side, None when −2σ <= 0); "phep" overrides the comparison
      nn_rong_4t {}         foreign net value of the last 4 complete weeks > 0
      lnst_yoy {g}          NPAT to parent (fs-income isa22) of the latest quarter vs the same quarter a year
                            earlier >= g %
      tang_tu_day {x}       % above the latest zigzag trough (or the running low after the last peak) >= x
      parabol {k}           last weekly close ÷ MA40 >= k
      ty_so_holdco_pct {p, cua_so}  percentile of the current parent ÷ LT (window "3y" | "toan_dai") <= p; ma =
                            a tang parent selects that layer; None below PCT_MIN_N weeks
    A tham_so "nguong" / "muc" is the threshold (DAU_HIEU_THAM_SO) when the engine name is absent.
    μ/σ generated after --den are not used (sigma None, sigma_ly_do says why: no look-ahead).
  to_json() -> one dict, numbers raw (VND, ×, percent numbers such as 2.05 = 2,05%), dates ISO, txt = display
  strings pre-formatted with msn_reflex helpers ("[CẦN DATA]" when missing):
  {"schema": "chaebol_reflex_live/1", "script_version",
   "ok": bool, "data_to", "den", "co_so": base ticker,
   "nhom": {"id", "ten", "chu_the", "truc", "loai", "me" (priced parent or null), "me_registry", "co_so",
            "so_ma" (members with a ticker), "so_ma_co_gia", "co_ho_so": bool, "hoi_dong": bool},
   "thanh_vien": [{"ma", "ten", "vai_tro", "me", "niem_yet", "trong_lt" (registry flag), "trong_lt_dung" (used),
       "co_gia", "ly_do_loai" (why not in LT / null),
       "so_huu": row in force at data_to on the LT basis | null, "so_huu_phap_ly", "so_huu_hieu_dung",
         row = {"ty_le", "loai", "tu", "tier", "nguon"}; "so_huu_cho": [pending rows], "w_lt": effective weight,
       "gia": {"ngay", "dong" (raw VND), "dong_dc" (adjusted), "nguon": "vc"|"nen"} | null,
       "mcap", "mcap_ngay", "phan_nam" (w_lt × mcap),
       "loi_suat": {"ngay", "r_1t", "r_13t", "r_ytd", "r_dinh_52t", "dinh_52t", "dinh_52t_ngay", "tier"},
       "kl": {"tuan", "ty_le", "mo_so_phien", "mo_ty_le", "tier"},
       "nn_4t": {"tong", "tuan": [{"tuan", "gia_tri"}], "mo", "den_ngay", "tier"}  (a week whose Vietcap flow
                rows stop before its last session is null, not a partial sum),
       "sigma": {"metric": "pb"|"pe", "mu", "sd", "base", "gia", "ratio", "z", "dai": {"-2","-1","0","+1","+2"}
                 (VND = base × (μ + kσ)), "suy_bien" (μ−2σ <= 0: only the expensive side is scored),
                 "engine": {"reliable", "sigma", "ngay", "n", "generated"}, "tier"} | null,
       "lnst": {"ky", "ngay_cong_bo", "lnst", "lnst_cung_ky", "yoy", "ttm", "ttm_truoc", "yoy_ttm", "truong",
                "ly_do", "tier", "nguon"},
       "doi_chieu": [{"nguon", "ty_le", "ngay", "tier", "ten"}], "lech": bool, "txt": {...}}],
   "lt": {"gia_tri", "ngay", "du", "phan": [{"ma", "w", "mcap", "ngay", "phan"}], "tier", "txt"} | null,
   "ty_so": RATIO | null,  "tang": [RATIO + "con"],
     RATIO = {"me", "con": [...], "hien_tai", "ngay", "mcap_me", "lt", "du",
              "thong_ke": {"3y": W, "toan_dai": W, "cua_so": W | null},
                W = {"tu", "n", "n_bo" (weeks with an unweighted priced member, left out), "du_mau" (n >=
                     PCT_MIN_N), "trung_vi", "p25", "p75", "phan_vi" (mid-rank % of history below the current value,
                     current week excluded; null when not du_mau), "niem_yet" ({"ma", "ngay", "n_truoc", "n_sau",
                     "cat"}: an LT child listed inside the window; cat = window cut to the weeks after it, done when
                     >= PCT_MIN_N remain), "min", "min_ngay", "max", "max_ngay", "ar1": AR},
                AR = {"n", "a", "b", "t", "nua_doi_tuan", "neo", "ghi_chu"} (Δln R = a + b·ln R₋₁ on pairs at most
                     AR_GAP_DAYS apart; n < 52 -> numbers null, ghi_chu "[CẦN DATA] …"; half-life −ln2/ln|1+b| and
                     neo only for −2 < b < 0),
              "niem_yet": [{"ma", "ngay"}] (LT children listed after the series start: level breaks),
              txt "phan_vi_3y" / "phan_vi_toan_dai" = "57% · từ 29/09/2023 · 157 tuần" or "[CẦN DATA]: chỉ n tuần
              từ …" (pv_txt), "*_so" = the bare number, "cua_so_*" = "từ … · n tuần",
              "tuan": [{"fri", "last", "lt", "mcap_me", "r", "du"}], "tier", "txt"}
   "zigzag": {MA: {"nguong", "pivot": [{"ngay", "gia", "loai": "day"|"dinh", "xac_nhan"}],
                   "chan": [{"tu", "den", "gia_tu", "gia_den", "r", "huong": "tang"|"giam", "so_tuan",
                             "xac_nhan"}]}},   (last leg = last confirmed pivot → today, xac_nhan false; huong
                                                 "ngang" when flat)
   "capture": [{"me", "con", "tang": bool, "tu", "den", "huong", "r_con", "r_me", "w", "mcap_me0", "mcap_con0",
                "capture", "xac_nhan", "ly_do", "tier"}],  (|r_con| >= 30 %, legs starting after the parent's first
                price; capture_cua_so(me, con, tu, den, w=None) recomputes any window, e.g. a dossier's)
   "bung_pha": {MA: [{"day", "gia_day", "xac_nhan_day", "bung_pha", "gia", "so_phien"}]},
   "dinh": {MA: [{"ngay", "gia", "xac_nhan"}]},
   "dan_tre": {"co_so", "chu_ky": [{"tu", "den", "nguon": "vni_day"|"2_nam", "vni_day",
               "ma": {MA: {"bung_pha", "bung_pha_xac_nhan", "lech_bung_pha", "lech_bung_pha_mo", "dinh",
                           "dinh_xac_nhan", "lech_dinh", "lech_dinh_mo"}}}], "tier", "ghi_chu"},
               (lech = days vs co_so, negative = MA earlier; xac_nhan false / *_mo true = a pivot of an open leg)
   "tuong_quan": {"co_so", "so_tuan", "quy_uoc", "z_bonferroni", "ma": {MA: {"lag": [-6..6], "r": [...],
                  "n": [...], "best_lag", "best_r", "nguong" (CORR_Z/√n at the best lag: Bonferroni over 13 lags,
                  ≈ 2,9/√n), "nguong_1_phep" (2/√n at lag 0), "co_y_nghia"}}, "ghi_chu", "tier"},
   "chuoi": {"tu", "x": [Friday ISO], "quy_100": {MA: [...]}, "goc": {MA: ISO}, "vni": [...]},
   "kl_co_so": {"ma", "tuan": [{"fri", "ty_le"}], "mo": {"fri", "so_phien", "ty_le"} | null},
   "dinh_gia_co_so": {"ma", "metric", "mu", "sd", "tuan": [{"d", "gia_k", "base_k", "ratio"}]} | null,
   "tin_hieu": [{"id", "bien", "phep", "muc", "nhom_tin_hieu", "live", "gia_tri", "gia_tri_txt", "trang_thai"
                 ("Đạt"/"Chưa" xac_nhan, "Kích hoạt"/"An toàn" phu_dinh, "[CẦN DATA]", null when not live),
                 "as_of", "tier", "ghi_chu"}],
     bien: me_dong_tuan | dong_tuan:<MÃ> (last complete weekly close; muc >= 1000 = đồng, else nghìn đồng) |
           kl_tuan_tb20 (parent, else base) | me_lt (current ratio) | pb_sigma:<MÃ>
   "canh_bao": [warnings], "nguon_live": [source rows of msn_reflex.Kho]}
"""

from __future__ import annotations

import bisect
import json
import math
import os
import re
import statistics
from collections import deque
from datetime import date, timedelta

import msn_reflex as M

SCRIPT_VERSION = "1.0"
SCHEMA_REG = "chaebol_reflex_nhom/1"
SCHEMA_LIVE = "chaebol_reflex_live/1"
ID_RE = re.compile(r"[a-z0-9_]+")
MA_RE = re.compile(r"[A-Z0-9]{3,10}")
LOAI_SH = ("phap_ly", "hieu_dung")
KHONG_GIA = ("chưa", "nước ngoài")       # niem_yet values that never enter LT / charts

ZZ = 0.30                 # zigzag reversal
CAPTURE_MIN = 30.0        # % move of the child leg for a capture row
BREAK_SESSIONS = 250
CORR_WEEKS = 156
CORR_LAGS = 6
# the best of 2·CORR_LAGS+1 lags is picked, so a two-sided 5 % test needs Bonferroni: z(1 − 0,025/13) ≈ 2,89
CORR_Z = statistics.NormalDist().inv_cdf(1 - 0.05 / (2 * (2 * CORR_LAGS + 1)))
AR_MIN_N = 52
PCT_MIN_N = AR_MIN_N      # a "3 năm" / "toàn dải" percentile needs at least 52 weekly points
AR_GAP_DAYS = 10          # one weekly step (7 days) plus a holiday; 14-day pairs are not one step
SPLICE_SESSIONS = 5       # nen ↔ Vietcap adjusted anchor: a common day within the first / last 5 nen sessions
LAG_WARN_DAYS = 4         # a member series ending more than this many days before data_to is flagged
LITE_YEARS = 5            # TỔNG QUAN (lite) reads Vietcap price history from 5 years before the reference day
CYCLE_PAD = timedelta(days=120)
CYCLE_YEARS = 2
MA_WEEKS = 40
NN_WEEKS = 4
R13_WEEKS = 13
HIGH_DAYS = 364
STALE_MCAP_DAYS = 10
OWN_TOL = 0.005           # 0,5 pp between the registry stake and a vc_lk figure → warning
YEARS_3 = 3

T_DATA, T_EST, CAN = M.T_DATA, M.T_EST, M.CAN
DB_SRC_TEN = "Kho giá vnstore (nen_ngay, gia_moi, free_float, ma)"     # msn_reflex.Kho._load_db source name
DAU_HIEU = {"bung_pha_250": {"phien": BREAK_SESSIONS}, "kl_tuan_tb20": {"k": 1.5}, "vuot_ma200": {},
            "cach_dinh_52t": {"x": 10.0}, "pb_sigma": {"s": 1.0}, "nn_rong_4t": {}, "lnst_yoy": {"g": 0.0},
            "tang_tu_day": {"x": 30.0}, "parabol": {"k": 1.5}, "ty_so_holdco_pct": {"p": 20.0, "cua_so": "3y"}}
# the threshold parameter of each sign: a curator's "nguong" / "muc" means this one when it is not given itself
DAU_HIEU_THAM_SO = {k: next((p for p in v if p != "cua_so"), None) for k, v in DAU_HIEU.items()}
DAU_HIEU_PHU = {"pb_sigma": ("phep",)}      # optional extra parameters (pb_sigma: explicit comparison)
PHEP = (">", ">=", "<", "<=")
LNST_FIELD = "isa22"      # vc_lk fs-metrics: "Attributable to parent company" (VIC, VCB, GEX, SSI, BVH, VHM 10/10)

_VC_MEMO = {}
_JSON_MEMO = {}
_WIDATA_MEMO = {}


def clear_cache():
    for c in (_VC_MEMO, _JSON_MEMO, _WIDATA_MEMO):
        c.clear()


def _fkey(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return path, st.st_mtime_ns, st.st_size


def iso(d):
    return d.isoformat() if isinstance(d, date) else None


_DAY_MEMO = {}


def _day(v):
    """msn_reflex.parse_day, memoised per string (Vietcap repeats the same dates in every file)."""
    if v.__class__ is not str:
        return M.parse_day(v)
    if v in _DAY_MEMO:
        return _DAY_MEMO[v]
    d = _DAY_MEMO[v] = M.parse_day(v)
    return d


def _fin(v, _isfinite=math.isfinite):
    """msn_reflex.finite (int / float, not bool, finite → float; else None) without its call chain."""
    c = v.__class__
    if c is float:
        return v if _isfinite(v) else None
    if c is int:
        return float(v)
    return None if (v is None or c is str or c is bool) else M.finite(v)


_COT_RE = re.compile(r'"cot"\s*:\s*\[')
_HANG_RE = re.compile(r'"hang"\s*:\s*\[')
_LAY_RE = re.compile(r'"lay_luc"\s*:\s*"([^"]*)"')


def _vc_tail(path, tu, probe=15):
    """Rows of a Vietcap price-history file dated ≥ tu, decoding only that tail → (cot, rows, lay_luc), or None to
    decode the whole file: any layout other than {"meta", "du_lieu": {"cot": [tradingDate, …], "hang": [rows in
    date order]}}, a file starting after tu, or an unreadable file (the full read then reports it)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        mc, mh = _COT_RE.search(text), _HANG_RE.search(text)
        if not (mc and mh) or mh.start() < mc.start():
            return None
        cot = json.loads(text[mc.end() - 1:text.index("]", mc.end()) + 1])
        if not cot or cot[0] != "tradingDate" or not text.rstrip().endswith("]]}}"):
            return None
        body, d, pos = mh.end(), tu, -1
        for _ in range(probe):                       # first session on/after tu (weekends, Tết)
            pos = text.find('["' + d.isoformat(), body)
            if pos >= 0:
                break
            d += timedelta(days=1)
        if pos <= body:                              # not found, or the file starts after tu: full decode
            return None
        prev = text.rfind('["', body, pos - 1)
        if prev < 0 or text[prev + 2:prev + 12] >= tu.isoformat():
            return None
        rows = json.loads("[" + text[pos:text.rstrip().rindex("]]") + 2])
        key = ""
        for r in rows:                               # date order is what makes the cut exact
            if r.__class__ is not list or not r or r[0].__class__ is not str or r[0] < key:
                return None
            key = r[0]
        m = _LAY_RE.search(text, 0, mc.start())
        return cot, rows, m.group(1) if m else None
    except (OSError, ValueError, IndexError):
        return None


def ticker(v):
    """Registry value → ticker ("" when it is not one)."""
    s = M.nfc(v).upper()
    return s if MA_RE.fullmatch(s) else ""


def years_back(d, n):
    try:
        return d.replace(year=d.year - n)
    except ValueError:                      # 29/02
        return d.replace(year=d.year - n, day=28)


def pct(a, b):
    """(a / b − 1) × 100, or None."""
    return (a / b - 1.0) * 100.0 if (a is not None and b) else None


def add_warning(warnings, msg):
    if msg not in warnings:
        warnings.append(msg)


def nt(v):
    """Đồng → "1.818,6 nghìn tỷ" (CẦN DATA when missing)."""
    return (M.nghin_ty(v) + " nghìn tỷ") if M.finite(v) is not None else CAN


def strip_row(r):
    return {k: v for k, v in r.items() if not k.startswith("_")} if r else None


# ── Registry ─────────────────────────────────────────────────────────────────


def reg_dir():
    kos = M.env_path("MSN_KOS_DIR", os.path.join(M.SYS_DIR, "knowledge_os"))
    return M.env_path("CHAEBOL_REFLEX_DIR", os.path.join(kos, "chaebol_reflex"))


def parse_stake_rows(nid, ma, rows, warnings):
    """Validated so_huu rows of one member → {"phap_ly": [...], "hieu_dung": [...], "cho": [...]}, newest first."""
    out = {"phap_ly": [], "hieu_dung": [], "cho": []}
    for e in M.as_list(rows):
        e = M.as_dict(e)
        d, w = M.parse_day(e.get("tu")), M.finite(e.get("ty_le"))
        loai = M.nfc(e.get("loai")) or "phap_ly"
        bad = []
        if d is None:
            bad.append("tu")
        if w is None or not 0 < w <= 1:
            bad.append("ty_le 0–1")
        if not M.nfc(e.get("tier")):
            bad.append("tier")
        if not M.nfc(e.get("nguon")):
            bad.append("nguon")
        if loai not in LOAI_SH:
            bad.append("loai phap_ly|hieu_dung")
        if bad:
            add_warning(warnings, "Registry %s: bỏ dòng sở hữu của %s (thiếu/sai %s)." % (nid, ma or "?",
                                                                                     ", ".join(bad)))
            continue
        r = {"ty_le": w, "loai": loai, "tu": d.isoformat(), "tier": M.nfc(e.get("tier")),
             "nguon": M.nfc(e.get("nguon")), "_tu": d}
        out["cho" if e.get("ap_dung") is False else loai].append(r)
    for k in out:
        out[k].sort(key=lambda r: r["_tu"], reverse=True)   # stable: earlier in the file = newer on a tie
    return out


class Nhom(dict):
    """One registry entry. The dict keeps the registry JSON as given; parsed schedules live in attributes."""

    def __init__(self, raw, warnings):
        super().__init__(raw)
        nid = M.nfc(raw.get("id"))
        if not ID_RE.fullmatch(nid):
            raise ValueError("id %r không phải slug ASCII [a-z0-9_]" % raw.get("id"))
        self.id = nid
        self.me_raw = M.nfc(raw.get("me"))
        self.me = ticker(raw.get("me"))
        if self.me_raw and not self.me:
            add_warning(warnings, "Registry %s: mẹ %r không phải mã niêm yết, nhóm tính như không có mẹ."
                        % (nid, raw.get("me")))
        self.members = []                   # [(ma, raw member dict)]
        self._lich = {}
        seen = set()
        for m in M.as_list(raw.get("thanh_vien")):
            if not isinstance(m, dict):
                continue
            ma = ticker(m.get("ma"))
            if ma and ma in seen:
                add_warning(warnings, "Registry %s: %s ghi hai lần trong thanh_vien, giữ dòng đầu." % (nid, ma))
                continue
            if ma:
                seen.add(ma)
                self._lich[ma] = parse_stake_rows(nid, ma, m.get("so_huu"), warnings)
            elif M.as_list(m.get("so_huu")):
                add_warning(warnings, "Registry %s: thành viên %r không có mã, tỷ lệ sở hữu chỉ để đọc."
                            % (nid, M.nfc(m.get("ten"))))
            self.members.append((ma, m))
        self.tang = []
        for t in M.as_list(raw.get("tang")):
            t = M.as_dict(t)
            x = ticker(t.get("me"))
            cons = [c for c in (ticker(v) for v in M.as_list(t.get("con"))) if c]
            if x and cons:
                self.tang.append({"me": x, "con": cons})
            else:
                add_warning(warnings, "Registry %s: bỏ tầng holdco %r (cần mã mẹ và danh sách con)." % (nid, t))

    def member(self, ma):
        for m, raw in self.members:
            if m == ma:
                return raw
        return None

    def holder(self, ma):
        return ticker(M.as_dict(self.member(ma)).get("me"))

    def holder_raw(self, ma):
        """The member's "me" as written (a ticker, an unlisted holding name, or "")."""
        return M.nfc(M.as_dict(self.member(ma)).get("me"))

    def tickers(self):
        out = [self.me] if self.me else []
        out += [m for m, _ in self.members if m]
        for t in self.tang:
            out += [t["me"]] + t["con"]
        return list(dict.fromkeys(out))

    def _rows(self, ma, loai):
        lich = self._lich.get(ma)
        if not lich:
            return []
        if loai is None:
            loai = "hieu_dung" if lich["hieu_dung"] else "phap_ly"
        return lich.get(loai, [])

    def has(self, ma, loai):
        return bool(self._lich.get(ma, {}).get(loai))

    def weight_row(self, ma, d, loai=None):
        """(stake, row) in force at d: newest applied row with tu ≤ d; (0.0, None) before the first row;
        (None, None) without rows."""
        rows = self._rows(ma, loai)
        if not rows:
            return None, None
        for r in rows:
            if r["_tu"] <= d:
                return r["ty_le"], r
        return 0.0, None

    def weight(self, ma, d, loai=None):
        return self.weight_row(ma, d, loai)[0]

    def first_tu(self, ma, loai=None):
        rows = self._rows(ma, loai)
        return rows[-1]["_tu"] if rows else None

    def pending(self, ma):
        return list(self._lich.get(ma, {}).get("cho", []))


class Registry(dict):
    def __init__(self, raw, path):
        super().__init__(raw)
        self.path = path

    def groups(self):
        return [g for g in self.get("nhom", []) if isinstance(g, Nhom)]

    def nhom(self, nid):
        for g in self.groups():
            if g.id == nid:
                return g
        return None

    def nhom_of_ma(self, ma):
        ma = ticker(ma)
        return [g.id for g in self.groups() if ma and ma in g.tickers()]


def load_registry(root=None):
    root = root or reg_dir()
    path = os.path.join(root, "nhom.json")
    warnings = []
    empty = Registry({"schema": SCHEMA_REG, "nhom": []}, path)
    if not os.path.isfile(path):
        warnings.append("Chưa có registry nhóm %s." % path)
        return empty, warnings
    try:
        raw = M.load_json(path)
    except (OSError, ValueError) as exc:
        warnings.append("Không đọc được registry %s (%s)." % (path, exc))
        return empty, warnings
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA_REG:
        warnings.append("Registry %s sai schema (cần %s)." % (path, SCHEMA_REG))
        return empty, warnings
    groups, seen = [], set()
    for i, g in enumerate(M.as_list(raw.get("nhom"))):
        if not isinstance(g, dict):
            warnings.append("Registry: mục thứ %d không phải object, bỏ qua." % (i + 1))
            continue
        try:
            nh = Nhom(g, warnings)
        except ValueError as exc:
            warnings.append("Registry: bỏ nhóm thứ %d (%s)." % (i + 1, exc))
            continue
        if nh.id in seen:
            warnings.append("Registry: nhóm %s ghi hai lần, giữ mục đầu." % nh.id)
            continue
        seen.add(nh.id)
        groups.append(nh)
    return Registry(dict(raw, nhom=groups), path), warnings


def nhom(nid, reg=None):
    return (reg if reg is not None else load_registry()[0]).nhom(nid)


def nhom_of_ma(ma, reg=None):
    return (reg if reg is not None else load_registry()[0]).nhom_of_ma(ma)


# ── Stores ───────────────────────────────────────────────────────────────────


class KhoNhom(M.Kho):
    """msn_reflex.Kho for a group's tickers plus the per-ticker HHP, ownership and income files.

    vnstore rows are read for every ticker of `syms` (one SQL query); the per-ticker files (vc_lk price history,
    details, shareholder, relationship, fs-income, HHP series) only for `vc_syms` (default: all of `syms`), and
    ensure_vc(sym) adds one later. lite=True (TỔNG QUAN) also skips the HHP engine, WiData, the ecosystem file and
    the shareholder / relationship / fs-income files: only prices, market caps and listing dates are needed."""

    def __init__(self, p, den, warnings, syms, he_sinh_thai=(), vc_syms=None, lite=False):
        self.syms = tuple(dict.fromkeys(s for s in (ticker(x) for x in syms) if s and s != M.VNI))
        self.lite = bool(lite)
        # lite: Vietcap rows older than vc_tu are not decoded (TỔNG QUAN shows 3-year statistics only)
        self.vc_tu = years_back(den or M.today(), LITE_YEARS) if self.lite else None
        self._want = set(self.syms) if vc_syms is None else (
            {s for s in (ticker(x) for x in vc_syms) if s} & set(self.syms))
        self.he_sinh_thai = tuple(M.nfc(k) for k in (he_sinh_thai or ()) if M.nfc(k))
        self.hhp_ser = {}
        self.eco = {}
        self.cd = {}
        self.rel = {}
        self.organ = {}
        self.fs = {}
        super().__init__(p, den, warnings, extra=self.syms)
        self._fix_db_source()
        self._load_files()

    # ── cached readers ──

    def _replay(self, store, key, run, get, put):
        hit = store.get(key) if key is not None else None
        if hit is not None:
            val, srcs, warns = hit
            put(val)
            self.sources.extend(dict(s) for s in srcs)
            for w in warns:
                add_warning(self.warnings, w)
            return
        ns, nw = len(self.sources), len(self.warnings)
        run()
        if key is not None:
            store[key] = (get(), [dict(s) for s in self.sources[ns:]], list(self.warnings[nw:]))

    def _read(self, path, ten, tier):
        if os.path.basename(path) == "price-history.json" or path == self.p.get("widata"):
            return super()._read(path, ten, tier)
        key = _fkey(path)
        if key is not None and key in _JSON_MEMO:
            return _JSON_MEMO[key]
        raw = super()._read(path, ten, tier)
        if raw is not None and key is not None:
            _JSON_MEMO[key] = raw
        return raw

    def _read_opt(self, path):
        """Optional file: None without a warning when absent."""
        key = _fkey(path)
        if key is None:
            return None
        if key in _JSON_MEMO:
            return _JSON_MEMO[key]
        try:
            raw = M.load_json(path)
        except (OSError, ValueError) as exc:
            add_warning(self.warnings, "Không đọc được %s (%s)" % (path, exc))
            return None
        _JSON_MEMO[key] = raw
        return raw

    def _load_vc(self, sym):
        if sym not in self._want:
            return                                          # Masan's SYMS outside this group
        path = os.path.join(self.p["vc_lk"], sym, "price-history.json")
        key = _fkey(path)
        self._replay(_VC_MEMO, key + (self.den, self.vc_tu) if key else None, lambda: self._parse_vc(sym),
                     lambda: self.vc.get(sym), lambda v: self.vc.__setitem__(sym, v) if v else None)

    def _parse_vc(self, sym):
        """msn_reflex.Kho._load_vc with the same output, warnings and source row, with dates parsed once per
        distinct string and a cheaper number check (a 2,6 MB file holds ~5.000 rows × 58 columns; TỔNG QUAN reads
        ~90 of them)."""
        path = os.path.join(self.p["vc_lk"], sym, "price-history.json")
        ten = "%s %s" % (M.SRC_VC, sym)
        tail = _vc_tail(path, self.vc_tu) if self.vc_tu else None
        if tail is not None:
            cot, hang, lay_luc = tail
        else:
            raw = M.Kho._read(self, path, ten, T_DATA)
            if raw is None:
                return
            du = M.as_dict(M.as_dict(raw).get("du_lieu"))
            cot, hang = M.as_list(du.get("cot")), M.as_list(du.get("hang"))
            lay_luc = M.as_dict(M.as_dict(raw).get("meta")).get("lay_luc")
        ix = {c: i for i, c in enumerate(cot)}
        need = ("tradingDate", "closePrice", "closePriceAdjusted", "marketCap", "totalShares")
        if any(k not in ix for k in need):
            self.warnings.append("%s thiếu cột (%s)" % (path, ", ".join(k for k in need if k not in ix)))
            self._src(ten, path, None, T_DATA, False, "thiếu cột")
            return
        n = len(cot)
        i_d, i_c, i_ca, i_m, i_sh = (ix[k] for k in need)
        i_nn = ix.get("foreignNetValueTotal")
        rows = []
        for r in hang:
            if r.__class__ is not list or len(r) < n:
                continue
            d, c = _day(r[i_d]), _fin(r[i_c])
            if d is None or c is None or c <= 0 or not self._cut(d):
                continue
            rows.append((d, c, _fin(r[i_ca]), _fin(r[i_m]), _fin(r[i_sh]),
                         _fin(r[i_nn]) if i_nn is not None else None))
        rows.sort(key=lambda t: t[0])
        out = {"d": [], "c": [], "ca": [], "m": [], "sh": [], "nn": []}
        last = None
        for d, c, ca, m, sh, nn in rows:
            if d == last:
                continue
            last = d
            out["d"].append(d)
            out["c"].append(c)
            out["ca"].append(ca)
            out["m"].append(m)
            out["sh"].append(sh)
            out["nn"].append(nn)
        out["lay_luc"] = lay_luc
        if not out["d"]:
            self._src(ten, path, None, T_DATA, False, "không có dòng hợp lệ")
            return
        self.vc[sym] = out
        self._src(ten, path, out["d"][-1].isoformat(), T_DATA, True,
                  "giá thô + giá điều chỉnh + marketCap/totalShares; lấy lúc %s%s" % (
                      lay_luc or "?",
                      (" · đọc từ %s (TỔNG QUAN)" % M.ddmmyyyy(self.vc_tu)) if tail is not None else ""))

    def ensure_vc(self, sym):
        """Load the per-ticker files of one more ticker of `syms` (e.g. a group's time-axis ticker)."""
        sym = ticker(sym)
        if not sym or sym not in self.syms or sym in self._want:
            return
        self._want.add(sym)
        self._load_vc(sym)
        self._files_of(sym, {})

    def _load_widata(self):
        if self.lite:
            return
        key = _fkey(self.p["widata"])
        self._replay(_WIDATA_MEMO, key + (self.den,) if key else None, lambda: M.Kho._load_widata(self),
                     lambda: self.vni_ext, lambda v: setattr(self, "vni_ext", v))

    def _load_hhp(self):
        if self.lite:
            return
        ten = "%s · định giá VN100" % M.SRC_HHP
        raw = self._read(self.p["hhp"], ten, T_EST)
        if isinstance(raw, dict):
            self.hhp = raw
            self.hhp_gen = M.parse_stamp(M.as_dict(raw.get("meta")).get("generated"))
            stale = M.as_list(M.as_dict(raw.get("meta")).get("stale_fields"))
            self._src(ten, self.p["hhp"], self.hhp_gen.date().isoformat() if self.hhp_gen else None, T_EST, True,
                      ("trường stale: " + ", ".join(str(s) for s in stale)) if stale else "")
            if self.den and self.hhp_gen and self.hhp_gen.date() > self.den:
                add_warning(self.warnings, "Tham số σ của engine HHP lập %s, sau mốc --den %s." % (
                    M.ddmmyyyy(self.hhp_gen.date()), M.ddmmyyyy(self.den)))
        sdir = os.path.dirname(self.p["hhp_series"])
        have, miss, last = [], [], None
        for s in self.syms:
            if s not in self._want:
                continue
            ser = self._series_of(self._read_opt(os.path.join(sdir, s + ".json")))
            if ser:
                self.hhp_ser[s] = ser
                have.append(s)
                for v in ser.values():
                    last = max(last, v["d"][-1]) if last else v["d"][-1]
            else:
                miss.append(s)
        if self.syms:
            self._src("%s · chuỗi P/B, P/E theo mã" % M.SRC_HHP, sdir, iso(last), T_EST, bool(have),
                      "có %s%s" % (", ".join(have) or "không mã nào", (" · thiếu " + ", ".join(miss)) if miss else ""))

    def _series_of(self, raw):
        out = {}
        for metric in ("pb", "pe"):
            b = M.as_dict(M.as_dict(raw).get(metric))
            base = {}
            for t, v in M.as_list(b.get("base")):
                if M.finite(t) is not None and M.finite(v):
                    base[M.ms_day(t)] = float(v)
            pts = []
            for t, v in M.as_list(b.get("price")):
                if M.finite(t) is None or not M.finite(v):
                    continue
                d = M.ms_day(t)
                if self._cut(d) and base.get(d):
                    pts.append((d, float(v), base[d]))
            pts.sort()
            if pts:
                out[metric] = {"d": [x[0] for x in pts], "price_k": [x[1] for x in pts],
                               "base_k": [x[2] for x in pts], "mean": M.finite(b.get("mean")),
                               "sd": M.finite(b.get("sd"))}
        return out

    def _load_owners(self):
        """chaebol_ecosystems.json members of the group's he_sinh_thai keys (replaces Masan's owner lookup)."""
        self.owners = {}
        if not self.he_sinh_thai or self.lite:
            return
        ten = "Hệ sinh thái chaebol (chaebol_ecosystems.json)"
        raw = self._read(self.p["chaebol"], ten, T_DATA)
        ecos = {M.nfc(k): v for k, v in M.as_dict(M.as_dict(raw).get("ecosystems")).items()}
        found = []
        for k in self.he_sinh_thai:
            e = M.as_dict(ecos.get(k))
            if not e:
                add_warning(self.warnings, "chaebol_ecosystems.json không có hệ \"%s\"." % k)
                continue
            found.append(k)
            for sym, m in M.as_dict(e.get("members")).items():
                self.eco.setdefault(ticker(sym), (k, M.as_dict(m)))
        if raw is not None:
            self._src(ten, self.p["chaebol"], M.nfc(M.as_dict(raw).get("as_of"))[:10] or None, T_DATA, bool(found),
                      "đối chiếu sở hữu · hệ " + (", ".join(found) or "không khớp"))

    def _fix_db_source(self):
        """msn_reflex.Kho._load_db reports Masan's tickers; restate the vnstore row for this group."""
        base_missing = [s for s in M.SYMS + (M.VNI,) if s not in self.nen]
        txt = "Kho giá thiếu nến của: %s" % ", ".join(base_missing)
        if base_missing and txt in self.warnings:
            self.warnings.remove(txt)
        for src in self.sources:
            if src.get("ten") != DB_SRC_TEN or not M.nfc(src.get("ghi_chu")).startswith("nen_ngay"):
                continue
            missing = [s for s in self.syms + (M.VNI,) if s not in self.nen]
            lasts = [self.nen[s]["d"][-1] for s in self.syms if s in self.nen and self.nen[s]["d"]]
            note = "nen_ngay: lịch sử điều chỉnh (vci_history) + vài phiên cuối giá thô bảng điện (vci_board)"
            if missing:
                note += " · thiếu " + ", ".join(missing)
                add_warning(self.warnings, "Kho giá thiếu nến của: %s" % ", ".join(missing))
            src.update({"as_of": max(lasts).isoformat() if lasts else None, "ok": bool(lasts), "ghi_chu": note})

    def _files_of(self, s, acc):
        """details (listing date, organ code), and unless lite: shareholder, relationship, fs-income of one ticker;
        `acc` counts files and the newest dates for the source rows."""
        vc = self.p["vc_lk"]
        det = M.as_dict(M.as_dict(self._read_opt(os.path.join(vc, s, "details.json"))).get("du_lieu"))
        if det:
            self.organ[s] = {"code": M.nfc(det.get("organCode")).upper(),
                             "ten": [M.nfc(det.get(k)) for k in ("viOrganName", "viOrganShortName",
                                                                "enOrganName") if M.nfc(det.get(k))],
                             "niem_yet_tu": M.parse_day(det.get("listingDate"))}
        if self.lite:
            return

        def newest(key, d):
            if d:
                acc[key] = max(acc[key], d) if acc.get(key) else d
        raw = self._read_opt(os.path.join(vc, s, "shareholder.json"))
        if raw is not None:
            rows = []
            for r in M.as_list(M.as_dict(raw).get("du_lieu")):
                r = M.as_dict(r)
                d, v = M.parse_day(r.get("publicDate")), M.finite(r.get("percentage"))
                if v is None or (self.den and d and d > self.den):
                    continue
                rows.append({"code": M.nfc(r.get("ownerCode")).upper(), "ten": M.nfc(r.get("ownerName")),
                             "ty_le": v, "ngay": d})
                newest("last_sh", d)
            self.cd[s] = rows
            acc["n_sh"] = acc.get("n_sh", 0) + 1
        rel = M.as_dict(M.as_dict(self._read_opt(os.path.join(vc, s, "relationship.json"))).get("du_lieu"))
        if rel:
            kids = {}
            for kind in ("subsidiaries", "affiliates"):
                for r in M.as_list(rel.get(kind)):
                    r = M.as_dict(r)
                    t, v = ticker(r.get("rightTicker")), M.finite(r.get("ownedPercentage"))
                    if t and v is not None:
                        kids.setdefault(t, (v, kind, M.nfc(r.get("rightOrganNameVi"))))
            self.rel[s] = kids
            acc["n_rel"] = acc.get("n_rel", 0) + 1
        fs = self._read_opt(os.path.join(vc, s, "fs-income.json"))
        if fs is not None:
            self.fs[s] = fs
            acc["n_fs"] = acc.get("n_fs", 0) + 1
            for q in M.as_list(M.as_dict(M.as_dict(fs).get("du_lieu")).get("quarters")):
                d = M.parse_day(M.as_dict(q).get("publicDate"))
                if d and (self.den is None or d <= self.den):
                    newest("last_fs", d)

    def _load_files(self):
        vc = self.p["vc_lk"]
        acc = {}
        loaded = [s for s in self.syms if s in self._want]
        for s in loaded:
            self._files_of(s, acc)
        if not loaded or self.lite:
            return
        n = len(loaded)
        self._src("vc_lk shareholder (cổ đông lớn, đối chiếu sở hữu)", vc, iso(acc.get("last_sh")), T_DATA,
                  acc.get("n_sh", 0) > 0, "%d/%d mã có tệp" % (acc.get("n_sh", 0), n))
        self._src("vc_lk relationship (con, liên kết)", vc, None, T_DATA, acc.get("n_rel", 0) > 0,
                  "%d/%d mã có tệp · vendor không ghi ngày dữ liệu" % (acc.get("n_rel", 0), n))
        self._src("vc_lk fs-income (LNST cổ đông mẹ, %s)" % LNST_FIELD, vc, iso(acc.get("last_fs")), T_DATA,
                  acc.get("n_fs", 0) > 0, "%d/%d mã có tệp" % (acc.get("n_fs", 0), n))

    def hhp_ma(self, sym):
        """{"pb": {...}, "pe": {...}} of the HHP engine for a ticker (valuation blocks only)."""
        bt = M.as_dict(M.as_dict(M.as_dict(self.hhp).get("by_ticker")).get(sym))
        return {k: M.as_dict(bt.get(k)) for k in ("pb", "pe") if M.as_dict(bt.get(k))}


# ── Pure computations ────────────────────────────────────────────────────────


def zigzag(closes, nguong=ZZ):
    """Confirmed pivots [(i, "day"|"dinh")] by a ≥ nguong reversal from the running extreme, plus the open
    candidate extreme (i, kind) after the last pivot (None before the first swing is confirmed)."""
    piv = []
    n = len(closes)
    if n < 2:
        return piv, None
    hi = lo = 0
    trend = 0
    for i in range(1, n):
        c = closes[i]
        if trend == 0:
            if c > closes[hi]:
                hi = i
            if c < closes[lo]:
                lo = i
            if hi == i and lo < i and c >= closes[lo] * (1 + nguong):
                piv.append((lo, "day"))
                trend = 1
            elif lo == i and hi < i and c <= closes[hi] * (1 - nguong):
                piv.append((hi, "dinh"))
                trend = -1
        elif trend == 1:
            if c > closes[hi]:
                hi = i
            elif c <= closes[hi] * (1 - nguong):
                piv.append((hi, "dinh"))
                trend, lo = -1, i
        else:
            if c < closes[lo]:
                lo = i
            elif c >= closes[lo] * (1 + nguong):
                piv.append((lo, "day"))
                trend, hi = 1, i
    cand = (hi, "dinh") if trend == 1 else ((lo, "day") if trend == -1 else None)
    return piv, cand


def legs_of(days, closes, piv):
    """Legs between consecutive pivots, then the open leg from the last pivot to the last point."""
    pts = [(i, True) for i, _ in piv]
    if pts and pts[-1][0] < len(closes) - 1:
        pts.append((len(closes) - 1, False))
    out = []
    for (i0, _), (i1, ok) in zip(pts, pts[1:]):
        r = pct(closes[i1], closes[i0])
        out.append({"tu": days[i0], "den": days[i1], "gia_tu": closes[i0], "gia_den": closes[i1], "r": r,
                    "huong": "tang" if r > 0 else ("giam" if r < 0 else "ngang"), "so_tuan": i1 - i0, "xac_nhan": ok})
    return out


def prev_max(closes, n):
    """out[i] = max(closes[i−n:i]) once n earlier sessions exist, else None (monotonic deque, O(len))."""
    out = [None] * len(closes)
    dq = deque()
    for i, c in enumerate(closes):
        while dq and dq[0] < i - n:
            dq.popleft()
        if i >= n and dq:
            out[i] = closes[dq[0]]
        while dq and closes[dq[-1]] <= c:
            dq.pop()
        dq.append(i)
    return out


def first_breakout(days, closes, pm, after, until=None):
    """(index) of the first session after `after` (and before `until`) closing above pm, else None."""
    j = bisect.bisect_right(days, after)
    end = bisect.bisect_left(days, until) if until else len(days)
    for k in range(j, end):
        if pm[k] is not None and closes[k] > pm[k]:
            return k
    return None


def capture_of(mcap_me0, r_me, w, mcap_c0, r_c):
    """(capture, reason): (mcap_me0 × r_me) ÷ (w × mcap_c0 × r_c); r in percent."""
    if mcap_me0 is None or r_me is None:
        return None, "thiếu giá hoặc vốn hóa mẹ ở đầu chân"
    if mcap_c0 is None or r_c is None:
        return None, "thiếu vốn hóa con ở đầu chân"
    if not w:
        return None, "chưa có tỷ lệ sở hữu tại ngày đầu chân"
    den = w * mcap_c0 * r_c / 100.0
    if not den:
        return None, "con không đổi giá"
    return mcap_me0 * r_me / 100.0 / den, ""


def ar1(vals, days=None, min_n=AR_MIN_N):
    """OLS of Δln R = a + b·ln R₋₁ on consecutive points; numbers None when fewer than min_n pairs."""
    xs, zs = [], []
    for i in range(1, len(vals)):
        a, b = vals[i - 1], vals[i]
        if a is None or b is None or a <= 0 or b <= 0:
            continue
        if days is not None and (days[i] - days[i - 1]).days > AR_GAP_DAYS:
            continue
        y0 = math.log(a)
        xs.append(y0)
        zs.append(math.log(b) - y0)
    n = len(xs)
    out = {"n": n, "a": None, "b": None, "t": None, "nua_doi_tuan": None, "neo": None, "ghi_chu": ""}
    if n < min_n:
        out["ghi_chu"] = "%s: chỉ %d cặp tuần, cần ≥ %d" % (CAN, n, min_n)
        return out
    mx, mz = sum(xs) / n, sum(zs) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        out["ghi_chu"] = "%s: tỷ số không đổi" % CAN
        return out
    b = sum((x - mx) * (z - mz) for x, z in zip(xs, zs)) / sxx
    a = mz - b * mx
    sse = sum((z - a - b * x) ** 2 for x, z in zip(xs, zs))
    se = math.sqrt(sse / (n - 2) / sxx) if n > 2 and sse > 0 else 0.0
    out.update({"a": a, "b": b, "t": (b / se) if se > abs(b) * 1e-9 else None})     # None: exact fit
    # y_t − neo = (1 + b)(y_{t−1} − neo): mean-reverting iff |1 + b| < 1, i.e. −2 < b < 0
    if b >= 0:
        out["ghi_chu"] = "b ≥ 0: chuỗi không hồi về neo trong cửa sổ này"
    elif b <= -2:
        out["ghi_chu"] = "b ≤ −2: dao động nổ, không hồi về neo"
    elif b == -1:
        out["nua_doi_tuan"] = 0.0
        out["ghi_chu"] = "b = −1: về neo ngay trong một tuần"
    else:
        out["nua_doi_tuan"] = -math.log(2) / math.log(abs(1 + b))
        if b < -1:
            out["ghi_chu"] = "−2 < b < −1: hồi về neo kèm dao động đổi dấu quanh neo"
    if -2 < b < 0 and abs(a / b) < 700:
        out["neo"] = math.exp(-a / b)
    if out["t"] is not None and abs(out["t"]) < 2 and not out["ghi_chu"]:
        out["ghi_chu"] = "|t| < 2: hồi về neo không có ý nghĩa thống kê"
    return out


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs)
    sy = sum((y - my) ** 2 for y in ys)
    if sx <= 0 or sy <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sx * sy)


def lag_corr(rb, rc, fris, lags=CORR_LAGS):
    """[(k, r, n)] for k = −lags…+lags with r(k) = corr(base_t, con_{t+k}) over the Fridays `fris`
    (k > 0: the con moves k weeks AFTER the base)."""
    out = []
    for k in range(-lags, lags + 1):
        xs, ys = [], []
        for i, f in enumerate(fris):
            j = i + k
            if 0 <= j < len(fris):
                a, b = rb.get(f), rc.get(fris[j])
                if a is not None and b is not None:
                    xs.append(a)
                    ys.append(b)
        out.append((k, pearson(xs, ys), len(xs)))
    return out


def corr_row(rb, rc, fris, lags=CORR_LAGS):
    """Lagged correlation of one ticker against the base: r at every lag, the lag of the largest |r|, and whether
    that maximum clears the Bonferroni threshold CORR_Z/√n (best of 2·lags+1 tests; ≈ 2,9/√n for 13 lags)."""
    res = lag_corr(rb, rc, fris, lags)
    fin = [(k, r, n) for k, r, n in res if r is not None]
    best = max(fin, key=lambda t: (abs(t[1]), -abs(t[0]))) if fin else None
    n0 = next((n for k, r, n in res if k == 0), 0)
    nguong = CORR_Z / math.sqrt(best[2]) if (best and best[2]) else None
    return {"lag": [k for k, _, _ in res], "r": [r for _, r, _ in res], "n": [n for _, _, n in res],
            "best_lag": best[0] if best else None, "best_r": best[1] if best else None, "nguong": nguong,
            "nguong_1_phep": 2.0 / math.sqrt(n0) if n0 else None,
            "co_y_nghia": bool(best and nguong and abs(best[1]) >= nguong)}


def weekly_log_returns(weeks):
    """{fri: ln(close / previous close)} for weeks at most 14 days apart."""
    out = {}
    for w0, w1 in zip(weeks, weeks[1:]):
        if (w1["fri"] - w0["fri"]).days <= 14 and w0["close"] > 0 and w1["close"] > 0:
            out[w1["fri"]] = math.log(w1["close"] / w0["close"])
    return out


def phan_vi(vals, cur):
    """Mid-rank percentile of cur among vals (share below + half the ties), in %."""
    if cur is None or not vals:
        return None
    below = sum(1 for v in vals if v < cur)
    eq = sum(1 for v in vals if v == cur)
    return 100.0 * (below + 0.5 * eq) / len(vals)


def muc_dong(muc):
    """A price threshold in đồng: values < 1000 are read as nghìn đồng."""
    return muc * 1000.0 if (muc is not None and abs(muc) < 1000) else muc


def noi_chuoi(nd, nc, vd, va, k=SPLICE_SESSIONS):
    """Adjusted daily closes: vnstore nen (nd, nc) extended BEFORE its first row and AFTER its last row by Vietcap
    closePriceAdjusted (vd, va), each part rescaled to meet nen on an anchor day present in both series (searched
    within the first / last k nen sessions; nen and Vietcap adjust on different bases). Without an anchor that part
    is dropped, never spliced at factor 1. No nen at all: the Vietcap adjusted series as is.
    → (days, closes, notes) with one note per dropped part."""
    vmap = {d: a for d, a in zip(vd, va) if a and a > 0}
    if not nd:
        days = [d for d in vd if d in vmap]
        return days, [vmap[d] for d in days], []
    notes, head_d, head_c, tail_d, tail_c = [], [], [], [], []
    if vd and vd[0] < nd[0]:
        j = next((j for j in range(min(k, len(nd))) if nd[j] in vmap), None)
        if j is None:
            notes.append("không có phiên chung với Vietcap trong %d phiên đầu của nến (từ %s), bỏ giá Vietcap trước "
                         "đó thay vì nối với hệ số 1" % (k, M.ddmmyyyy(nd[0])))
        else:
            f = nc[j] / vmap[nd[j]]
            for d in vd[:bisect.bisect_left(vd, nd[0])]:
                if d in vmap:
                    head_d.append(d)
                    head_c.append(vmap[d] * f)
    if vd and vd[-1] > nd[-1]:
        j = next((j for j in range(len(nd) - 1, max(-1, len(nd) - 1 - k), -1) if nd[j] in vmap), None)
        if j is None:
            notes.append("không có phiên chung với Vietcap trong %d phiên cuối của nến (đến %s), không nối giá "
                         "Vietcap sau đó" % (k, M.ddmmyyyy(nd[-1])))
        else:
            f = nc[j] / vmap[nd[j]]
            for d in vd[bisect.bisect_right(vd, nd[-1]):]:
                if d in vmap:
                    tail_d.append(d)
                    tail_c.append(vmap[d] * f)
    return head_d + list(nd) + tail_d, head_c + list(nc) + tail_c, notes


def chon_co_so(kho, nh):
    """Time-axis ticker of a group without a priced parent: the largest vnstore market cap (last nen close × free_float
    issue_share) among members whose nen reaches the group's latest nen session (a member with stale nen is never the
    axis). vnstore only, so a group page and an ALL-IN-ONE cell on a reduced member set agree. None when no member
    has nen rows and a share count."""
    cands = []
    for s in nh.tickers():
        m = nh.member(s)
        if m is not None and M.nfc(m.get("niem_yet")).lower() in KHONG_GIA:
            continue
        r = kho.nen.get(s)
        sh = M.finite(kho.shares.get(s, (None,))[0])
        if r and r["d"] and sh:
            cands.append((r["d"][-1], r["c"][-1] * sh, s))
    if not cands:
        return None
    last = max(c[0] for c in cands)
    return max((c for c in cands if c[0] == last), key=lambda c: c[1])[2]


def pv_txt(w):
    """Display of one RATIO window: "57% · từ 29/09/2023 · 157 tuần", or "[CẦN DATA]: chỉ 14 tuần từ 03/07/2026"
    below PCT_MIN_N points (a listing inside the window is named)."""
    w = M.as_dict(w)
    tu = M.ddmmyyyy(M.parse_day(w.get("tu"))) or "?"
    n = w.get("n") or 0
    if not w.get("du_mau"):
        return "%s: chỉ %d tuần từ %s (cần ≥ %d)" % (CAN, n, tu, PCT_MIN_N) if n else CAN
    if w.get("phan_vi") is None:
        return CAN
    out = "%s%% · từ %s · %d tuần" % (M.fmt_vn(w["phan_vi"], 0), tu, n)
    ny = M.as_dict(w.get("niem_yet"))
    if ny.get("cat"):
        out += " (sau khi %s niêm yết)" % ny.get("ma")
    elif ny:
        out += " · gồm %d tuần trước khi %s niêm yết %s" % (ny.get("n_truoc") or 0, ny.get("ma"),
                                                         M.ddmmyyyy(M.parse_day(ny.get("ngay"))))
    return out


# ── Live group ───────────────────────────────────────────────────────────────


class LiveNhom:
    """Every live number of one group, computed at construction (see module doc for to_json)."""

    def __init__(self, kho, nhom, dossier=None, warnings=None, co_so=None, lite=False):
        self.kho = kho
        self.warnings = kho.warnings if warnings is None else warnings
        self.nhom = nhom if isinstance(nhom, Nhom) else Nhom(nhom, self.warnings)
        self.dossier = dossier if isinstance(dossier, dict) else {}
        self.co_so_cho = ticker(co_so) or None      # time axis chosen on the FULL group (ALL-IN-ONE reduced sets)
        self.lite = bool(lite)                      # TỔNG QUAN: ratio, captures and returns only
        cs = M.as_dict(self.nhom.get("cua_so"))
        self.rebase_from = M.parse_day(cs.get("rebase_from")) or M.REBASE_FROM
        self.ratio_from = M.parse_day(cs.get("ratio_from"))
        self._mc = {}
        self._mc_warned = set()
        self._pm = {}
        self.ser, self.priced, self.me, self.base, self.data_to = {}, [], None, None, None
        self.lt_set, self.excluded = [], {}
        self.ty_so, self.tang, self.zz, self.captures = None, [], {}, []
        self.bp, self.pk, self.dan_tre, self.tuong_quan = {}, {}, None, None
        self.per, self.signals, self.thanh_vien = {}, [], []
        self.sigma_ly_do = None
        gen = getattr(kho, "hhp_gen", None)
        if kho.den and gen and gen.date() > kho.den:
            self.sigma_ly_do = "μ/σ của engine HHP lập %s, sau mốc --den %s: không dùng (tránh nhìn trước)" % (
                M.ddmmyyyy(gen.date()), M.ddmmyyyy(kho.den))
        self._load_series()
        self.ok = self.data_to is not None
        if not self.ok:
            add_warning(self.warnings, "Nhóm %s: không mã nào có giá trong kho, khối LIVE là %s." % (
                self.nhom.id, CAN))
            return
        self._lt_members()
        self._ratios()
        self._zigzags()
        self._captures()
        if not self.lite:
            self._breakouts()
            self._lead_lag()
            self._correlations()
        for s in self.priced:
            self.per[s] = {"loi_suat": self._returns(s)} if self.lite else {
                "loi_suat": self._returns(s), "kl": self._kl(s), "nn_4t": self._nn(s), "sigma": self._sigma(s)}
        if not self.lite:
            self._signals()
        members = list(self.nhom.members)
        if self.nhom.me and all(ma != self.nhom.me for ma, _ in members):
            members.insert(0, (self.nhom.me, {"ma": self.nhom.me, "vai_tro": "mẹ", "ten": M.nfc(self.nhom.get("ten"))}))
        self.thanh_vien = [self._member_json(ma, m) for ma, m in members]

    # ── series ──

    def _priced_listing(self, s):
        m = self.nhom.member(s)
        return m is None or M.nfc(m.get("niem_yet")).lower() not in KHONG_GIA

    def _adjusted(self, s):
        """Adjusted daily closes: vnstore nen extended before its first and after its last row by Vietcap
        closePriceAdjusted rescaled on a common anchor day (noi_chuoi)."""
        nd, nc = self.kho.closes(s)
        vc = self.kho.vc.get(s)
        days, closes, notes = noi_chuoi(nd, nc, vc["d"], vc["ca"]) if vc else (list(nd), list(nc), [])
        for n in notes:
            add_warning(self.warnings, "Nhóm %s, %s: %s." % (self.nhom.id, s, n))
        start = self.kho.organ.get(s, {}).get("niem_yet_tu")
        if start and days and days[0] < start:
            k = bisect.bisect_left(days, start)
            days, closes = days[k:], closes[k:]
        return days, closes

    def _load_series(self):
        nh, kho = self.nhom, self.kho
        raw = {}
        for s in nh.tickers():
            if not self._priced_listing(s):
                self.excluded[s] = "niêm yết \"%s\": không tính LT, không vẽ" % M.nfc(nh.member(s).get("niem_yet"))
                continue
            d, c = self._adjusted(s)
            if d:
                raw[s] = (d, c)
            else:
                self.excluded[s] = "không có giá ở vc_lk/vnstore"
        if not raw:
            return
        if nh.me and nh.me in raw:
            self.me = nh.me
        elif nh.me:
            add_warning(self.warnings, "Nhóm %s: mẹ %s không có giá, tính như nhóm không có mẹ." % (nh.id, nh.me))
        if self.me:
            self.base = self.me
        else:
            cs = self.co_so_cho if self.co_so_cho in raw else chon_co_so(kho, nh)
            if cs not in raw:                         # no vnstore cap: largest cap among the freshest series
                last = max(v[0][-1] for v in raw.values())
                cs = max((s for s in raw if raw[s][0][-1] == last), key=lambda s: kho.mcap(s, last)[0] or 0.0)
            self.base = cs
        self.data_to = raw[self.base][0][-1]
        self._lag_warnings(raw)
        for s, (d, c) in raw.items():
            k = bisect.bisect_right(d, self.data_to)
            if not k:
                self.excluded[s] = "giá bắt đầu sau ngày dữ liệu của nhóm"
                continue
            wn = []
            if not self.lite:
                nd, nc = kho.closes(s)
                kl = kho.nen.get(s, {}).get("kl", [])
                kn = bisect.bisect_right(nd, self.data_to)
                wn = M.weeks_of(nd[:kn], nc[:kn], kl[:kn]) if kn else []
                if kn and nd[kn - 1] < self.data_to:     # nen stops early: its last week may be partial
                    wn = [w for w in wn if w["fri"] <= nd[kn - 1]]
            self.ser[s] = {"d": d[:k], "c": c[:k], "w": M.weeks_of(d[:k], c[:k]), "wn": wn}
            self.priced.append(s)
        for s, why in self.excluded.items():
            m = nh.member(s)
            # LT members are reported by _lt_members; a missing price file is already a msn_reflex.Kho warning
            if m is not None and not m.get("trong_lt") and s not in self.ser and why.startswith("niêm yết"):
                add_warning(self.warnings, "Nhóm %s: %s %s." % (nh.id, s, why))

    def _lag_warnings(self, raw):
        """Members whose series ends well before the group's data day, and a parent that lags its members."""
        nh, to = self.nhom, self.data_to
        for s, (d, _) in raw.items():
            if self.lite and s not in self.kho.vc:
                continue                              # TỔNG QUAN reads Vietcap only for the look-through set
            if (to - d[-1]).days > LAG_WARN_DAYS:
                add_warning(self.warnings, "Nhóm %s: giá %s dừng ở %s, trễ %d ngày so với ngày dữ liệu %s của nhóm "
                                           "(trục %s); số của %s là của ngày đó." % (
                                               nh.id, s, M.ddmmyyyy(d[-1]), (to - d[-1]).days, M.ddmmyyyy(to),
                                               self.base, s))
        newest = max(v[0][-1] for v in raw.values())
        if self.me and (newest - to).days > LAG_WARN_DAYS:
            add_warning(self.warnings, "Nhóm %s: mẹ %s chỉ có giá đến %s, các mã khác đến %s; cả nhóm tính đến %s." % (
                nh.id, self.me, M.ddmmyyyy(to), M.ddmmyyyy(newest), M.ddmmyyyy(to)))

    def complete(self, weeks):
        return [w for w in weeks if w["fri"] <= self.data_to]

    def open_week(self, weeks):
        return weeks[-1] if weeks and weeks[-1]["fri"] > self.data_to else None

    def adj_at(self, s, d):
        ser = self.ser.get(s)
        return M.asof(ser["d"], ser["c"], d) if ser else (None, None)

    def mc(self, s, d):
        """(raw market cap, day) at the last session ≤ d; stale (> STALE_MCAP_DAYS) or missing → (None, day)."""
        key = (s, d)
        if key not in self._mc:
            m, day = self.kho.mcap(s, d)
            start = self.kho.organ.get(s, {}).get("niem_yet_tu")
            ok = m is not None and m > 0 and day is not None and (d - day).days <= STALE_MCAP_DAYS and \
                (start is None or day >= start)
            vc = self.kho.vc.get(s)
            if ok and (vc is None or day < vc["d"][0]) and not self._raw_nen_row(s, day):
                ok = False                            # adjusted history × today's share count is not a cap
                if vc is None and s not in self._mc_warned:
                    self._mc_warned.add(s)
                    add_warning(self.warnings, "Nhóm %s: %s không có vc_lk price-history; vốn hóa chỉ tính ở phiên "
                                               "giá thô bảng điện (vci_board), bỏ các phiên lịch sử của nến (giá điều "
                                               "chỉnh × số cp hiện tại)." % (self.nhom.id, s))
            self._mc[key] = (m if ok else None, day)
        return self._mc[key]

    def _raw_nen_row(self, s, day):
        """The vnstore row of s on `day` is a raw board row (vci_board), not adjusted history."""
        r = self.kho.nen.get(s)
        if not r:
            return False
        i = bisect.bisect_right(r["d"], day) - 1
        return i >= 0 and r["d"][i] == day and r["src"][i] == "vci_board"

    # ── look-through ──

    def w_lt(self, ma, d, _seen=None):
        """Effective look-through weight of a member for the group parent at d (see module doc)."""
        nh = self.nhom
        if nh.has(ma, "hieu_dung"):
            return nh.weight(ma, d, "hieu_dung")
        w = nh.weight(ma, d, "phap_ly")
        if not w:
            return w
        raw, up = nh.holder_raw(ma), nh.holder(ma)
        if not raw or (up and up == self.me):
            return w
        if not up:
            return None              # held through an unlisted node: needs a hieu_dung row, no guessed factor
        seen = (_seen or set()) | {ma}
        if up in seen or nh.member(up) is None:
            return None
        uw = self.w_lt(up, d, seen)
        return None if uw is None else w * uw

    def _lt_members(self):
        nh = self.nhom
        for ma, m in nh.members:
            if not m.get("trong_lt"):
                continue
            why = None
            if not self.me:
                why = "nhóm không có mẹ có giá"
            elif not ma:
                why = "chưa có mã niêm yết"
            elif ma == self.me:
                why = "là mẹ của nhóm"
            elif ma not in self.ser:
                why = self.excluded.get(ma) or "không có giá"
            elif self.nhom._rows(ma, None) == []:
                why = "chưa có tỷ lệ sở hữu (có tu, tier, nguon)"
            elif self.w_lt(ma, self.data_to) is None:
                why = "không quy được tỷ lệ về mẹ nhóm qua %s%s" % (
                    nh.holder_raw(ma) or "?", "" if nh.holder(ma) else " (nút chưa niêm yết: cần dòng hieu_dung)")
            if why:
                self.excluded[ma or M.nfc(m.get("ten"))] = why
                add_warning(self.warnings, "Nhóm %s: %s không tính vào look-through (%s)." % (
                    nh.id, ma or M.nfc(m.get("ten")) or "?", why))
            else:
                self.lt_set.append(ma)
        for c in self.lt_set:
            up, seen = nh.holder(c), {c}
            while up and up != self.me and up not in seen:
                if up in self.lt_set:
                    add_warning(self.warnings, "Nhóm %s: %s và tầng trên %s cùng nằm trong look-through, phần %s "
                                               "bị đếm hai lần." % (nh.id, c, up, c))
                    break
                seen.add(up)
                up = nh.holder(up)

    def _lt(self, d, cons, wfn):
        total, parts, thieu = 0.0, {}, []
        for c in cons:
            w = wfn(c, d)
            if w is None:
                continue
            m, day = self.mc(c, d)
            if w == 0:
                if m is not None:
                    thieu.append(c)
                continue
            if m is None:
                return None, parts, thieu
            parts[c] = {"w": w, "mcap": m, "ngay": day, "phan": w * m}
            total += w * m
        return (total if parts else None), parts, thieu

    def _ratio_block(self, me, cons, wfn):
        weeks = self.complete(self.ser[self.base]["w"])
        rows, thieu_by = [], {}
        for w in weeks:
            d = w["last"]
            lt, _, thieu = self._lt(d, cons, wfn)
            mm = self.mc(me, d)[0]
            r = mm / lt if (lt and mm) else None
            if r is None and not rows:
                continue
            for c in thieu:
                a, b = thieu_by.get(c, (d, d))
                thieu_by[c] = (min(a, d), max(b, d))
            rows.append({"fri": w["fri"], "last": d, "lt": lt, "mcap_me": mm, "r": r, "du": not thieu})
        lt, parts, thieu = self._lt(self.data_to, cons, wfn)
        mm = self.mc(me, self.data_to)[0]
        cur = mm / lt if (lt and mm) else None
        for c, (a, b) in thieu_by.items():
            add_warning(self.warnings, "Nhóm %s, %s ÷ LT: %s có giá nhưng chưa có dòng sở hữu từ %s đến %s, các tuần "
                                       "đó không tính %s vào LT (trọng số 0) và bị loại khỏi thống kê tỷ số." % (
                                           self.nhom.id, me, c, M.ddmmyyyy(a), M.ddmmyyyy(b), c))
        cur_is_week = self.open_week(self.ser[self.base]["w"]) is None
        # an LT child listed after the series start joins LT only from its first price: a level break
        first = next((x["last"] for x in rows if x["r"] is not None), None)
        late = sorted((self.ser[c]["d"][0], c) for c in cons if c in self.ser and first and self.ser[c]["d"][0] > first)
        ny = (late[-1][1], late[-1][0]) if late else None
        stats = {"3y": self._stats(rows, cur, cur_is_week, years_back(self.data_to, YEARS_3), ny),
                 "toan_dai": self._stats(rows, cur, cur_is_week, None, ny),
                 "cua_so": self._stats(rows, cur, cur_is_week, self.ratio_from, ny) if self.ratio_from else None}
        return {"me": me, "con": list(cons), "hien_tai": cur, "ngay": self.data_to, "mcap_me": mm, "lt": lt,
                "du": not thieu, "phan": parts, "thong_ke": stats, "tuan": rows,
                "niem_yet": [{"ma": c, "ngay": d} for d, c in late]}

    def _stats(self, rows, cur, cur_is_week, frm, niem_yet=None):
        """One window: percentile (needs PCT_MIN_N points), median, quartiles, min/max and AR(1). A child listing
        inside the window (niem_yet = (ma, day)) cuts the window to the weeks after it when ≥ PCT_MIN_N remain;
        otherwise the counts before / after the listing are reported."""
        inwin = [x for x in rows if x["r"] is not None and (frm is None or x["fri"] >= frm)]
        pts = [x for x in inwin if x["du"]]
        n_bo = len(inwin) - len(pts)
        ny = None
        if niem_yet and pts and pts[0]["last"] < niem_yet[1]:
            after = [x for x in pts if x["last"] >= niem_yet[1]]
            n_after = len(after) - (1 if (cur_is_week and after and after[-1]["last"] == self.data_to) else 0)
            ny = {"ma": niem_yet[0], "ngay": iso(niem_yet[1]), "n_truoc": len(pts) - len(after), "n_sau": n_after,
                  "cat": n_after >= PCT_MIN_N}
            if ny["cat"]:
                pts = after
        hist = pts[:-1] if (cur_is_week and pts and pts[-1]["last"] == self.data_to) else pts
        vals = [x["r"] for x in hist]
        du_mau = len(vals) >= PCT_MIN_N
        out = {"tu": iso(pts[0]["fri"]) if pts else None, "n": len(vals), "n_bo": n_bo, "du_mau": du_mau,
               "n_toi_thieu": PCT_MIN_N, "niem_yet": ny,
               "trung_vi": statistics.median(vals) if vals else None, "p25": None, "p75": None,
               "phan_vi": phan_vi(vals, cur) if du_mau else None,
               "min": None, "min_ngay": None, "max": None, "max_ngay": None}
        if len(vals) >= 4:
            q = statistics.quantiles(vals, n=4)
            out["p25"], out["p75"] = q[0], q[2]
        allp = [(x["r"], x["last"]) for x in hist] + ([(cur, self.data_to)] if cur is not None else [])
        if allp:
            lo, hi = min(allp, key=lambda t: t[0]), max(allp, key=lambda t: t[0])
            out.update({"min": lo[0], "min_ngay": iso(lo[1]), "max": hi[0], "max_ngay": iso(hi[1])})
        out["ar1"] = ar1([x["r"] for x in pts], [x["fri"] for x in pts])
        return out

    def _ratios(self):
        nh = self.nhom
        if self.me and self.lt_set:
            self.ty_so = self._ratio_block(self.me, self.lt_set, self.w_lt)
        elif self.me:
            add_warning(self.warnings, "Nhóm %s: không con nào đủ điều kiện look-through, không có tỷ số %s ÷ LT."
                        % (nh.id, self.me))
        for t in nh.tang:
            x = t["me"]
            if x not in self.ser:
                add_warning(self.warnings, "Nhóm %s: tầng %s không có giá, bỏ tầng." % (nh.id, x))
                continue
            cons = []
            for c in t["con"]:
                why = None
                if c not in self.ser:
                    why = self.excluded.get(c) or "không có giá"
                elif nh.holder(c) != x:
                    why = "registry ghi người nắm trực tiếp là %s" % (nh.holder(c) or "?")
                elif nh.weight(c, self.data_to, "phap_ly") is None:
                    why = "chưa có tỷ lệ pháp lý"
                if why:
                    add_warning(self.warnings, "Nhóm %s, tầng %s: bỏ %s (%s)." % (nh.id, x, c, why))
                else:
                    cons.append(c)
            if cons:
                self.tang.append(self._ratio_block(x, cons, lambda c, d: nh.weight(c, d, "phap_ly")))

    # ── zigzag, capture, breakouts ──

    def _zigzags(self):
        need = set(self.lt_set) | {c for t in self.tang for c in t["con"]} if self.lite else None
        for s in self.priced:
            if need is not None and s not in need:
                continue                              # TỔNG QUAN: only the capture legs of children
            ws = self.ser[s]["w"]
            days, closes = [w["last"] for w in ws], [w["close"] for w in ws]
            piv, cand = zigzag(closes)
            self.zz[s] = {"days": days, "closes": closes, "piv": piv, "cand": cand,
                          "legs": legs_of(days, closes, piv)}

    def capture_cua_so(self, me, con, tu, den, w=None):
        """Capture of `me` on `con` over [tu, den] (adjusted closes, raw caps at tu; w = stake at tu unless given),
        e.g. a dossier's frozen window recomputed live."""
        t0, t1 = M.parse_day(tu) if isinstance(tu, str) else tu, M.parse_day(den) if isinstance(den, str) else den
        r_me = pct(self.adj_at(me, t1)[1], self.adj_at(me, t0)[1])
        r_c = pct(self.adj_at(con, t1)[1], self.adj_at(con, t0)[1])
        if w is None:
            w = self.w_lt(con, t0) if me == self.me else self.nhom.weight(con, t0, "phap_ly")
        m0, c0 = self.mc(me, t0)[0], self.mc(con, t0)[0]
        cap, why = capture_of(m0, r_me, w, c0, r_c)
        return {"me": me, "con": con, "tu": iso(t0), "den": iso(t1), "r_con": r_c, "r_me": r_me, "w": w,
                "mcap_me0": m0, "mcap_con0": c0, "capture": cap, "ly_do": why, "tier": T_EST}

    def _cap_child(self, me, c, wfn, tang):
        start = self.ser[me]["d"][0]
        for leg in self.zz.get(c, {}).get("legs", []):
            if abs(leg["r"]) < CAPTURE_MIN or leg["tu"] < start:
                continue
            t0, t1 = leg["tu"], leg["den"]
            p0, p1 = self.adj_at(me, t0)[1], self.adj_at(me, t1)[1]
            r_me = pct(p1, p0)
            m0, c0, w = self.mc(me, t0)[0], self.mc(c, t0)[0], wfn(c, t0)
            cap, why = capture_of(m0, r_me, w, c0, leg["r"])
            self.captures.append({"me": me, "con": c, "tang": tang, "tu": t0, "den": t1, "huong": leg["huong"],
                                  "r_con": leg["r"], "r_me": r_me, "w": w, "mcap_me0": m0, "mcap_con0": c0,
                                  "capture": cap, "xac_nhan": leg["xac_nhan"], "ly_do": why})

    def _captures(self):
        if self.ty_so:
            for c in self.lt_set:
                self._cap_child(self.me, c, self.w_lt, False)
        for t in self.tang:
            for c in t["con"]:
                self._cap_child(t["me"], c, lambda x, d: self.nhom.weight(x, d, "phap_ly"), True)

    def prevmax(self, s, n=BREAK_SESSIONS):
        key = (s, n)
        if key not in self._pm:
            self._pm[key] = prev_max(self.ser[s]["c"], n)
        return self._pm[key]

    def troughs(self, s):
        z = self.zz.get(s)
        if not z:
            return []
        out = [(z["days"][i], z["closes"][i], True) for i, k in z["piv"] if k == "day"]
        if z["cand"] and z["cand"][1] == "day":
            i = z["cand"][0]
            out.append((z["days"][i], z["closes"][i], False))
        return out

    def _breakouts_of(self, s, n=BREAK_SESSIONS):
        ser = self.ser[s]
        pm = self.prevmax(s, n)
        ts = self.troughs(s)
        out = []
        for k, (d, c, ok) in enumerate(ts):
            until = ts[k + 1][0] if k + 1 < len(ts) else None
            j = first_breakout(ser["d"], ser["c"], pm, d, until)
            i0 = bisect.bisect_right(ser["d"], d) - 1
            out.append({"day": d, "gia_day": c, "xac_nhan_day": ok, "bung_pha": ser["d"][j] if j is not None else None,
                        "gia": ser["c"][j] if j is not None else None,
                        "so_phien": (j - i0) if j is not None else None})
        return out

    def _breakouts(self):
        for s in self.priced:
            self.bp[s] = self._breakouts_of(s)
            z = self.zz[s]
            pk = [{"ngay": z["days"][i], "gia": z["closes"][i], "xac_nhan": True} for i, k in z["piv"] if k == "dinh"]
            if z["cand"] and z["cand"][1] == "dinh":
                i = z["cand"][0]
                pk.append({"ngay": z["days"][i], "gia": z["closes"][i], "xac_nhan": False})
            self.pk[s] = pk

    # ── lead / lag and correlations ──

    def _cycles(self):
        vd, vv = self.kho.vni()
        k = bisect.bisect_right(vd, self.data_to)
        vw = M.weeks_of(vd[:k], vv[:k])
        piv, _ = zigzag([w["close"] for w in vw])
        troughs = [vw[i]["last"] for i, kind in piv if kind == "day"]
        end = self.data_to + timedelta(days=1)
        cycles = []
        if troughs:
            starts = [t - CYCLE_PAD for t in troughs]
            for a, b, t in zip(starts, starts[1:] + [end], troughs):
                cycles.append((a, b, "vni_day", t))
            hi = starts[0]
        else:
            hi = end
        first = min(self.ser[s]["d"][0] for s in self.priced)
        pre = []
        while hi > first:
            lo = years_back(hi, CYCLE_YEARS)
            pre.insert(0, (lo, hi, "2_nam", None))
            hi = lo
        return pre + cycles

    def _lead_lag(self):
        base = self.base
        rows = []
        for a, b, src, t in self._cycles():
            ev = {}
            for s in self.priced:
                bps = [x for x in self.bp.get(s, []) if x["bung_pha"] and a <= x["bung_pha"] < b]
                pks = [x for x in self.pk.get(s, []) if a <= x["ngay"] < b]
                top = max(pks, key=lambda x: x["gia"]) if pks else None
                ev[s] = (bps[0]["bung_pha"] if bps else None, bps[0]["xac_nhan_day"] if bps else None,
                         top["ngay"] if top else None, top["xac_nhan"] if top else None)
            if not any(v[0] or v[2] for v in ev.values()):
                continue
            bb, bb_ok, bk, bk_ok = ev.get(base, (None, None, None, None))
            # xac_nhan False = the trough before the breakout, or the peak itself, is still the running extreme
            # of an open leg: the date (and its lag) can move or vanish next week
            ma = {s: {"bung_pha": iso(v[0]), "bung_pha_xac_nhan": v[1],
                      "lech_bung_pha": (v[0] - bb).days if (v[0] and bb) else None,
                      "lech_bung_pha_mo": bool(v[0] and bb and not (v[1] and bb_ok)),
                      "dinh": iso(v[2]), "dinh_xac_nhan": v[3],
                      "lech_dinh": (v[2] - bk).days if (v[2] and bk) else None,
                      "lech_dinh_mo": bool(v[2] and bk and not (v[3] and bk_ok))}
                  for s, v in ev.items()}
            rows.append({"tu": iso(a), "den": iso(b), "nguon": src, "vni_day": iso(t), "ma": ma})
        self.dan_tre = {"co_so": base, "chu_ky": rows, "tier": T_EST,
                        "ghi_chu": "Bứt phá 250 phiên sau đáy zigzag 30%% và đỉnh zigzag cao nhất trong chu kỳ; chu kỳ "
                                   "gom theo đáy zigzag VN-Index ±%d ngày, trước đó theo cửa sổ %d năm; lệch = số ngày "
                                   "so với %s (âm = sớm hơn); \"đang mở\" = đáy hoặc đỉnh của chân chưa xác nhận, ngày "
                                   "và độ lệch còn đổi." % (CYCLE_PAD.days, CYCLE_YEARS, base)}

    def _correlations(self):
        base = self.base
        cw = self.complete(self.ser[base]["w"])
        rb = weekly_log_returns(cw)
        fris = [w["fri"] for w in cw if w["fri"] in rb][-CORR_WEEKS:]
        ma = {s: corr_row(rb, weekly_log_returns(self.complete(self.ser[s]["w"])), fris)
              for s in self.priced if s != base}
        self.tuong_quan = {"co_so": base, "so_tuan": len(fris), "ma": ma, "tier": T_EST, "z_bonferroni": CORR_Z,
                           "quy_uoc": "r(k) = tương quan lợi suất log tuần của %s ở tuần t với mã ở tuần t+k; k > 0: "
                                      "mã đi sau %s k tuần" % (base, base),
                           "ghi_chu": "%d tuần gần nhất. Độ trễ có |r| lớn nhất được chọn trong %d độ trễ nên ngưỡng "
                                      "hiệu chỉnh Bonferroni ≈ %s/√n. Vượt ngưỡng chỉ nói tương quan khó là ngẫu "
                                      "nhiên trong mẫu này, không phải quy luật dẫn/trễ khai thác được; dưới ngưỡng "
                                      "thì không có quy luật nào." % (len(fris), 2 * CORR_LAGS + 1,
                                                                       M.fmt_vn(CORR_Z, 1))}

    # ── per ticker ──

    def _returns(self, s):
        ser = self.ser[s]
        d, c = ser["d"], ser["c"]
        last_d, last = d[-1], c[-1]
        prior = [w for w in ser["w"] if w["fri"] < M.friday(last_d)]
        ye_d, ye = M.asof(d, c, date(last_d.year - 1, 12, 31))
        k = bisect.bisect_left(d, last_d - timedelta(days=HIGH_DAYS))
        hi_i = max(range(k, len(c)), key=lambda i: c[i])
        return {"ngay": iso(last_d), "r_1t": pct(last, prior[-1]["close"]) if prior else None,
                "r_13t": pct(last, prior[-R13_WEEKS]["close"]) if len(prior) >= R13_WEEKS else None,
                "r_ytd": pct(last, ye) if (ye_d and ye_d.year == last_d.year - 1) else None,
                "r_dinh_52t": pct(last, c[hi_i]), "dinh_52t": c[hi_i], "dinh_52t_ngay": iso(d[hi_i]),
                "tier": T_DATA}

    def _kl(self, s):
        wn = self.ser[s]["wn"]
        comp, op = self.complete(wn), self.open_week(wn)
        out = {"tuan": None, "ty_le": None, "mo_so_phien": None, "mo_ty_le": None, "tier": T_DATA}
        if comp:
            out["tuan"] = iso(comp[-1]["last"])
            out["ty_le"] = M.vol_ratio(comp, len(comp) - 1)
        if op:
            base = M.mean([w["kl"] for w in comp[-M.TB_WEEKS:]]) if len(comp) >= M.TB_WEEKS else None
            out["mo_so_phien"] = op["n"]
            out["mo_ty_le"] = op["kl"] / base if base else None
        return out

    def _nn(self, s):
        vc = self.kho.vc.get(s)
        out = {"tong": None, "tuan": [], "mo": None, "den_ngay": None, "tier": T_DATA}
        if not vc:
            return out
        def week_sum(w):
            """Foreign net value of a week; None when Vietcap's flow rows stop before the week's last session
            (vc_lk fetched mid-week: a partial week is not a weekly total)."""
            fri = w["fri"]
            lo, tot, seen = fri - timedelta(days=4), 0.0, None
            i = bisect.bisect_left(vc["d"], lo)
            while i < len(vc["d"]) and vc["d"][i] <= fri:
                if vc["nn"][i] is not None:
                    tot += vc["nn"][i]
                    seen = vc["d"][i]
                i += 1
            return tot if (seen is not None and seen >= w["last"]) else None
        ws = self.ser[s]["w"]
        comp, op = self.complete(ws)[-NN_WEEKS:], self.open_week(ws)
        out["tuan"] = [{"tuan": iso(w["last"]), "gia_tri": week_sum(w)} for w in comp]
        vals = [x["gia_tri"] for x in out["tuan"]]
        out["tong"] = sum(vals) if (vals and all(v is not None for v in vals)) else None
        if op:
            out["mo"] = week_sum(op)
        j = bisect.bisect_right(vc["d"], self.data_to) - 1
        while j >= 0 and vc["nn"][j] is None:
            j -= 1
        out["den_ngay"] = iso(vc["d"][j]) if j >= 0 else None
        return out

    def _sigma(self, s):
        if self.sigma_ly_do:
            return None                               # --den before the engine's own date: look-ahead
        blocks = self.kho.hhp_ma(s)
        for metric in ("pb", "pe"):
            b = blocks.get(metric) or {}
            mu, sd, base = M.finite(b.get("mean")), M.finite(b.get("sd")), M.finite(b.get("per_share"))
            if mu is not None and sd and sd > 0 and base and base > 0:
                break
        else:
            return None
        day, price, _ = self.kho.raw_close(s, self.data_to)
        ratio = price / base if price else None
        gen = self.kho.hhp_gen
        return {"metric": metric, "mu": mu, "sd": sd, "base": base, "gia": price, "gia_ngay": iso(day),
                "ratio": ratio, "z": (ratio - mu) / sd if ratio is not None else None,
                "dai": {k: base * (mu + kk * sd) for k, kk in (("-2", -2), ("-1", -1), ("0", 0), ("+1", 1), ("+2", 2))},
                "suy_bien": mu - 2 * sd <= 0,
                "engine": {"reliable": b.get("reliable"), "sigma": M.finite(b.get("sigma")),
                           "ngay": M.nfc(b.get("ratio_date")) or None, "n": b.get("n"),
                           "generated": gen.isoformat() if gen else None},
                "tier": T_EST}

    def lnst(self, s):
        """NPAT to parent: latest quarter vs the same quarter a year earlier, and trailing 4 quarters."""
        out = {"ky": None, "ngay_cong_bo": None, "lnst": None, "lnst_cung_ky": None, "yoy": None, "ttm": None,
               "ttm_truoc": None, "yoy_ttm": None, "truong": LNST_FIELD, "ly_do": "", "tier": T_DATA,
               "nguon": "vc_lk/%s/fs-income.json" % s}
        fs = self.kho.fs.get(s)
        if fs is None:
            out["ly_do"] = "%s: không có vc_lk/%s/fs-income.json" % (CAN, s)
            return out
        q = {}
        for r in M.as_list(M.as_dict(M.as_dict(fs).get("du_lieu")).get("quarters")):
            r = M.as_dict(r)
            y, n, v = r.get("yearReport"), r.get("lengthReport"), M.finite(r.get(LNST_FIELD))
            d = M.parse_day(r.get("publicDate"))
            if not isinstance(y, int) or n not in (1, 2, 3, 4) or v is None:
                continue
            if self.kho.den and d and d > self.kho.den:
                continue
            q[(y, n)] = (v, d)
        if not q:
            out["ly_do"] = "%s: fs-income không có quý nào có trường %s" % (CAN, LNST_FIELD)
            return out
        y, n = max(q)
        cur, d = q[(y, n)]
        out.update({"ky": "Q%d/%d" % (n, y), "ngay_cong_bo": iso(d), "lnst": cur})
        prev = q.get((y - 1, n))
        if prev is None:
            out["ly_do"] = "%s: thiếu quý cùng kỳ Q%d/%d" % (CAN, n, y - 1)
        elif prev[0] <= 0:
            out["lnst_cung_ky"] = prev[0]
            out["ly_do"] = "cùng kỳ ≤ 0, không tính %"
        else:
            out["lnst_cung_ky"] = prev[0]
            out["yoy"] = pct(cur, prev[0])

        def back(yy, nn, k):
            for _ in range(k):
                yy, nn = (yy - 1, 4) if nn == 1 else (yy, nn - 1)
            return yy, nn
        last4 = [back(y, n, k) for k in range(4)]
        prev4 = [back(y, n, k) for k in range(4, 8)]
        if all(x in q for x in last4):
            out["ttm"] = sum(q[x][0] for x in last4)
            if all(x in q for x in prev4):
                out["ttm_truoc"] = sum(q[x][0] for x in prev4)
                if out["ttm_truoc"] > 0:
                    out["yoy_ttm"] = pct(out["ttm"], out["ttm_truoc"])
        return out

    def doi_chieu(self, ma):
        """Ownership figures for (holder → ma) from vc_lk shareholder / relationship and chaebol_ecosystems."""
        kho, up = self.kho, self.nhom.holder(ma)
        if not (ma and up):
            return []
        organ = kho.organ.get(up, {})
        codes = {up, organ.get("code")} - {"", None}
        rows, names = [], {M.nfc(n).lower() for n in organ.get("ten", [])}
        for r in kho.cd.get(ma, []):
            if r["code"] in codes:
                names.add(r["ten"].lower())
                rows.append({"nguon": "vc_lk/%s/shareholder" % ma, "ty_le": r["ty_le"], "ngay": iso(r["ngay"]),
                             "tier": T_DATA, "ten": r["ten"]})
        rel = kho.rel.get(up, {}).get(ma)
        if rel:
            rows.append({"nguon": "vc_lk/%s/relationship (%s)" % (up, rel[1]), "ty_le": rel[0], "ngay": None,
                         "tier": T_DATA, "ten": rel[2]})
        k, m = kho.eco.get(ma, (None, {}))
        for sh in M.as_list(m.get("top_shareholders")):
            sh = M.as_dict(sh)
            v = M.finite(sh.get("percentage"))
            if v is not None and M.nfc(sh.get("ownerName")).lower() in names:
                rows.append({"nguon": "chaebol_ecosystems/%s · %s cổ đông lớn" % (k, ma), "ty_le": v / 100.0,
                             "ngay": iso(M.parse_day(sh.get("publicDate"))), "tier": None,
                             "ten": M.nfc(sh.get("ownerName"))})
        k2, m2 = kho.eco.get(up, (None, {}))
        for kind in ("subsidiaries", "affiliates"):
            for sub in M.as_list(m2.get(kind)):
                sub = M.as_dict(sub)
                v = M.finite(sub.get("ownedPct"))
                if ticker(sub.get("ticker")) == ma and v is not None:
                    rows.append({"nguon": "chaebol_ecosystems/%s · %s %s" % (k2, up, kind), "ty_le": v / 100.0,
                                 "ngay": None, "tier": None, "ten": M.nfc(sub.get("name"))})
        return rows

    # ── signals and framework signs ──

    def last_week(self, s):
        ws = self.complete(self.ser[s]["w"]) if s in self.ser else []
        return ws[-1] if ws else None

    def _bien(self, bien):
        """(value, day, display, tier, note) of a dossier signal variable, or None when the name is unknown."""
        name, _, arg = bien.partition(":")
        s = ticker(arg) if arg else (self.me if name in ("me_dong_tuan", "me_lt") else (self.me or self.base))
        if name in ("me_dong_tuan", "dong_tuan"):
            w = self.last_week(s) if s else None
            return (w["close"] if w else None, w["last"] if w else None, "%s (tuần %s)" % (
                M.k_txt(w["close"]) if w else CAN, M.ddmm(w["last"]) if w else "?"), T_DATA,
                "%s · đóng cửa tuần hoàn chỉnh · vnstore" % (s or "mẹ"))
        if name == "kl_tuan_tb20":
            kl = self.per.get(s, {}).get("kl", {}) if s else {}
            return (kl.get("ty_le"), M.parse_day(kl.get("tuan")), M.x_txt(kl.get("ty_le")), T_DATA,
                    "%s · KL tuần ÷ TB 20 tuần trước · vnstore" % (s or "?"))
        if name == "me_lt":
            r = self.ty_so["hien_tai"] if self.ty_so else None
            return r, self.data_to if r is not None else None, M.x_txt(r), T_EST, "mẹ ÷ look-through, vốn hóa giá thô"
        if name == "pb_sigma":
            sg = self.per.get(s, {}).get("sigma") if s else None
            z = sg["z"] if sg else None
            return (z, M.parse_day(sg["gia_ngay"]) if sg else None, M.sigma_txt(z), T_EST,
                    ("%s · σ %s engine HHP" % (s or "?", "P/B" if sg["metric"] == "pb" else "P/E")) if sg else
                    "%s · %s" % (s or "?", self.sigma_ly_do or "engine HHP không có μ/σ"))
        return None

    def _signals(self):
        for r in M.as_list(self.dossier.get("tin_hieu")):
            if not isinstance(r, dict):
                continue
            bien, phep, muc = M.nfc(r.get("bien")), r.get("phep"), M.finite(r.get("muc"))
            loai = M.nfc(r.get("nhom_tin_hieu") or r.get("loai"))
            row = {"id": M.nfc(r.get("id")), "bien": bien or None, "phep": phep, "muc": muc, "nhom_tin_hieu": loai,
                   "live": False, "gia_tri": None, "gia_tri_txt": CAN, "trang_thai": None,
                   "as_of": M.ddmmyyyy(M.parse_day(r.get("ngay"))), "tier": M.nfc(r.get("tier")) or None,
                   "ghi_chu": "hiện nguyên văn theo hồ sơ"}
            got = self._bien(bien) if (bien and phep in (">", ">=", "<", "<=") and muc is not None) else None
            if got is None:
                if bien:
                    row["ghi_chu"] = "biến \"%s\" hoặc phép/mức không chấm được, hiện nguyên văn" % bien
                self.signals.append(row)
                continue
            v, d, txt, tier, note = got
            name, _, arg = bien.partition(":")
            hit = M.compare(v, phep, muc_dong(muc) if name in ("me_dong_tuan", "dong_tuan") else muc)
            sg = self.per.get(ticker(arg) or self.me or self.base, {}).get("sigma") if name == "pb_sigma" else None
            if sg and sg["suy_bien"] and phep in ("<", "<="):
                hit = None                            # spec: a degenerate band (−2σ ≤ 0) scores the expensive side
                note += " · dải σ suy biến (−2σ ≤ 0), không chấm phía rẻ"
            if hit is None:
                st = CAN
            elif loai == "phu_dinh":
                st = "Kích hoạt" if hit else "An toàn"
            else:
                st = "Đạt" if hit else "Chưa"
            row.update({"live": True, "gia_tri": v, "gia_tri_txt": txt, "trang_thai": st,
                        "as_of": M.ddmmyyyy(d) or M.ddmmyyyy(self.data_to), "tier": tier, "ghi_chu": "LIVE · " + note})
            self.signals.append(row)

    def do_dau_hieu(self, key, ma=None, tham_so=None):
        """Data check of one measurable framework sign: seen / not seen with a date, EST (no phase scoring).
        A curator's "nguong" / "muc" is the sign's threshold when the engine name itself (DAU_HIEU_THAM_SO) is
        absent; the DAU_HIEU default applies only when no spelling of the threshold is given."""
        given = {k: v for k, v in M.as_dict(tham_so).items() if v is not None}
        pname = DAU_HIEU_THAM_SO.get(key)
        if pname and pname not in given:
            for alias in ("nguong", "muc"):
                if alias in given:
                    given[pname] = given.pop(alias)
                    break
        ts = dict(DAU_HIEU.get(key, {}))
        ts.update(given)
        s = ticker(ma) or self.me or self.base
        out = {"khoa": key, "ma": s, "thay": None, "ngay": None, "gia_tri": None, "ghi_chu": "", "tham_so": ts,
               "tier": T_EST}
        if key not in DAU_HIEU:
            out["ghi_chu"] = "khoá phép đo lạ"
            return out
        if not self.ok or (key != "ty_so_holdco_pct" and s not in self.ser):
            out["ghi_chu"] = "%s: %s không có giá" % (CAN, s or "?")
            return out
        if self.lite and key != "ty_so_holdco_pct":
            out["ghi_chu"] = "%s: trang TỔNG QUAN không chấm dấu hiệu theo mã" % CAN
            return out

        def num(name):
            return M.finite(ts.get(name))
        if key == "bung_pha_250":
            n = int(num("phien") or BREAK_SESSIONS)
            bps = self._breakouts_of(s, n) if n != BREAK_SESSIONS else self.bp.get(s, [])
            if not bps:
                out["ghi_chu"] = "%s: chưa xác định được đáy zigzag 30%%" % CAN
                return out
            last = bps[-1]
            out.update({"thay": last["bung_pha"] is not None, "ngay": iso(last["bung_pha"] or self.data_to),
                        "gia_tri": last["gia"]})
            out["ghi_chu"] = ("phiên đầu tiên đóng trên mức cao nhất %d phiên, sau đáy %s" if last["bung_pha"] else
                              "chưa có phiên đóng trên mức cao nhất %d phiên kể từ đáy %s") % (
                n, M.ddmmyyyy(last["day"]))
        elif key == "kl_tuan_tb20":
            kl = self.per[s]["kl"]
            k = num("k")
            out.update({"gia_tri": kl["ty_le"], "ngay": kl["tuan"],
                        "thay": M.compare(kl["ty_le"], ">=", k), "ghi_chu": "KL tuần ÷ TB 20 tuần trước ≥ %s" %
                                                                           M.fmt_vn(k)})
        elif key in ("vuot_ma200", "parabol"):
            ws = self.complete(self.ser[s]["w"])
            if len(ws) < MA_WEEKS:
                out["ghi_chu"] = "%s: chưa đủ %d tuần" % (CAN, MA_WEEKS)
                return out
            ma40 = M.mean([w["close"] for w in ws[-MA_WEEKS:]])
            x = ws[-1]["close"] / ma40
            out.update({"gia_tri": x, "ngay": iso(ws[-1]["last"])})
            if key == "vuot_ma200":
                out.update({"thay": x > 1, "ghi_chu": "đóng cửa tuần ÷ MA40 tuần (≈ MA200 phiên)"})
            else:
                k = num("k")
                out.update({"thay": M.compare(x, ">=", k), "ghi_chu": "giá ÷ MA40 tuần ≥ %s" % M.fmt_vn(k)})
        elif key == "cach_dinh_52t":
            r = self.per[s]["loi_suat"]
            dist = -r["r_dinh_52t"] if r["r_dinh_52t"] is not None else None
            x = num("x")
            out.update({"gia_tri": dist, "ngay": r["ngay"], "thay": M.compare(dist, "<=", x),
                        "ghi_chu": "%% dưới đỉnh 52 tuần (%s ngày %s) ≤ %s%%" % (
                            M.k_txt(r["dinh_52t"]), M.ddmmyyyy(M.parse_day(r["dinh_52t_ngay"])), M.fmt_vn(x))})
        elif key == "pb_sigma":
            sg = self.per[s]["sigma"]
            th = num("s")
            if not sg:
                out["ghi_chu"] = "%s: %s" % (CAN, self.sigma_ly_do or "engine HHP không có μ/σ của %s" % s)
                return out
            out.update({"gia_tri": sg["z"], "ngay": sg["gia_ngay"]})
            # s ≥ 0 = expensive side (z ≥ s); s < 0 = cheap side (z ≤ s); an explicit "phep" overrides
            phep = ts.get("phep") if ts.get("phep") in PHEP else (">=" if (th is None or th >= 0) else "<=")
            cheap = phep in ("<", "<=")
            if sg["suy_bien"] and cheap:
                out["ghi_chu"] = "%s: dải σ suy biến (−2σ ≤ 0), chỉ chấm phía đắt" % CAN
                return out
            out.update({"thay": M.compare(sg["z"], phep, th),
                        "ghi_chu": "σ %s %s %s%s" % ("P/B" if sg["metric"] == "pb" else "P/E",
                                                    {">=": "≥", "<=": "≤"}.get(phep, phep), M.fmt_vn(th),
                                                    " (phía rẻ)" if cheap else " (phía đắt)")})
        elif key == "nn_rong_4t":
            nn = self.per[s]["nn_4t"]
            out.update({"gia_tri": nn["tong"], "ngay": nn["den_ngay"], "thay": M.compare(nn["tong"], ">", 0.0),
                        "ghi_chu": "khối ngoại ròng %d tuần hoàn chỉnh (Vietcap foreignNetValueTotal)" % NN_WEEKS})
        elif key == "lnst_yoy":
            ln = self.lnst(s)
            g = num("g")
            out.update({"gia_tri": ln["yoy"], "ngay": ln["ngay_cong_bo"], "thay": M.compare(ln["yoy"], ">=", g),
                        "tier": T_DATA, "ghi_chu": ln["ly_do"] or "LNST cổ đông mẹ %s so cùng kỳ ≥ %s%%" % (
                            ln["ky"], M.fmt_vn(g))})
        elif key == "tang_tu_day":
            ts_ = self.troughs(s)            # confirmed troughs, then the running low of an open down leg
            if not ts_:
                out["ghi_chu"] = "%s: chưa có đáy zigzag" % CAN
                return out
            low = ts_[-1]
            last = self.ser[s]["c"][-1]
            x = num("x")
            r = pct(last, low[1])
            out.update({"gia_tri": r, "ngay": iso(self.ser[s]["d"][-1]), "thay": M.compare(r, ">=", x),
                        "ghi_chu": "%% trên đáy gần nhất %s (%s) ≥ %s%%" % (M.k_txt(low[1]), M.ddmmyyyy(low[0]),
                                                                           M.fmt_vn(x))})
        elif key == "ty_so_holdco_pct":
            blk = self.ty_so
            if ma and ticker(ma) != self.me:
                blk = next((t for t in self.tang if t["me"] == ticker(ma)), None)
            if not blk:
                out["ghi_chu"] = "%s: nhóm không có tỷ số mẹ ÷ LT" % CAN
                return out
            win = M.nfc(ts.get("cua_so")) or "3y"
            st = M.as_dict(blk["thong_ke"].get(win))
            p = num("p")
            tu = M.ddmmyyyy(M.parse_day(st.get("tu"))) or "?"
            out.update({"ma": blk["me"], "gia_tri": st.get("phan_vi"), "ngay": iso(blk["ngay"])})
            if not st.get("du_mau"):
                out["ghi_chu"] = "%s: phân vị %s ÷ LT cửa sổ %s chỉ có %d tuần từ %s, cần ≥ %d" % (
                    CAN, blk["me"], win, st.get("n") or 0, tu, PCT_MIN_N)
                return out
            out.update({"thay": M.compare(st.get("phan_vi"), "<=", p),
                        "ghi_chu": "phân vị %s ÷ LT cửa sổ %s (từ %s · %d tuần) ≤ %s%%" % (
                            blk["me"], win, tu, st.get("n") or 0, M.fmt_vn(p))})
        if out["thay"] is None and not out["ghi_chu"].startswith(CAN):
            out["ghi_chu"] = "%s: %s" % (CAN, out["ghi_chu"])
        return out

    # ── output ──

    def _ratio_json(self, blk):
        if not blk:
            return None
        st = blk["thong_ke"]
        s3, sf = st["3y"], st["toan_dai"]
        ar = s3["ar1"]

        def so(w):
            return (M.fmt_vn(w["phan_vi"], 0) + "%") if w["phan_vi"] is not None else CAN

        def cua_so(w):
            return "từ %s · %d tuần" % (M.ddmmyyyy(M.parse_day(w["tu"])) or "?", w["n"])
        return {"me": blk["me"], "con": blk["con"], "hien_tai": blk["hien_tai"], "ngay": iso(blk["ngay"]),
                "mcap_me": blk["mcap_me"], "lt": blk["lt"], "du": blk["du"], "thong_ke": st,
                "niem_yet": [{"ma": x["ma"], "ngay": iso(x["ngay"])} for x in blk.get("niem_yet", [])],
                "tuan": [{"fri": iso(x["fri"]), "last": iso(x["last"]), "lt": x["lt"], "mcap_me": x["mcap_me"],
                          "r": x["r"], "du": x["du"]} for x in blk["tuan"]],
                "tier": T_EST,
                "txt": {"hien_tai": M.x_txt(blk["hien_tai"]), "lt": nt(blk["lt"]), "mcap_me": nt(blk["mcap_me"]),
                        "trung_vi_3y": M.x_txt(s3["trung_vi"]), "trung_vi_toan_dai": M.x_txt(sf["trung_vi"]),
                        "phan_vi_3y": pv_txt(s3), "phan_vi_toan_dai": pv_txt(sf),
                        "phan_vi_3y_so": so(s3), "phan_vi_toan_dai_so": so(sf),
                        "cua_so_3y": cua_so(s3), "cua_so_toan_dai": cua_so(sf),
                        "nua_doi_3y": (M.fmt_vn(ar["nua_doi_tuan"], 1) + " tuần") if ar["nua_doi_tuan"] is not None
                        else CAN, "neo_3y": M.x_txt(ar["neo"])}}

    def _member_json(self, ma, m):
        nh, d = self.nhom, self.data_to
        row = {"ma": ma or None, "ten": M.nfc(m.get("ten")), "vai_tro": M.nfc(m.get("vai_tro")),
               "me": M.nfc(m.get("me")) or None, "niem_yet": M.nfc(m.get("niem_yet")) or None,
               "trong_lt": bool(m.get("trong_lt")), "trong_lt_dung": ma in self.lt_set, "co_gia": ma in self.ser,
               "ly_do_loai": self.excluded.get(ma or M.nfc(m.get("ten"))), "so_huu": None, "so_huu_phap_ly": None,
               "so_huu_hieu_dung": None, "so_huu_cho": [strip_row(r) for r in nh.pending(ma)] if ma else [],
               "w_lt": None, "gia": None, "mcap": None, "mcap_ngay": None, "phan_nam": None, "loi_suat": None,
               "kl": None, "nn_4t": None, "sigma": None, "sigma_ly_do": None, "lnst": None, "doi_chieu": [],
               "lech": False}
        if ma and d:
            row["so_huu"] = strip_row(nh.weight_row(ma, d)[1])
            row["so_huu_phap_ly"] = strip_row(nh.weight_row(ma, d, "phap_ly")[1])
            row["so_huu_hieu_dung"] = strip_row(nh.weight_row(ma, d, "hieu_dung")[1])
            if self.me and ma != self.me:
                row["w_lt"] = self.w_lt(ma, d)
            row["doi_chieu"] = self.doi_chieu(ma)
            row["lnst"] = self.lnst(ma)
            pl = row["so_huu_phap_ly"]
            for x in row["doi_chieu"]:
                if pl and x["tier"] == T_DATA and abs(x["ty_le"] - pl["ty_le"]) > OWN_TOL:
                    row["lech"] = True
                    add_warning(self.warnings, "Sở hữu %s→%s: registry %s (%s · %s) khác %s %s%s." % (
                        nh.holder(ma), ma, M.share_txt(pl["ty_le"]), pl["tier"], M.ddmmyyyy(M.parse_day(pl["tu"])),
                        x["nguon"], M.share_txt(x["ty_le"]), (" (%s)" % M.ddmmyyyy(M.parse_day(x["ngay"])))
                        if x["ngay"] else ""))
        if ma in self.ser:
            day, c, src = self.kho.raw_close(ma, d)
            if src == "nen" and not self._raw_nen_row(ma, day):
                src = "nen_dieu_chinh"                # vci_history row: adjusted, not a raw close
            row["gia"] = {"ngay": iso(day), "dong": c, "dong_dc": self.ser[ma]["c"][-1], "nguon": src}
            if not (self.lite and ma not in self.kho.vc):     # TỔNG QUAN reads caps for the look-through set only
                mc, mday = self.mc(ma, d)
                row.update({"mcap": mc, "mcap_ngay": iso(mday),
                            "phan_nam": (row["w_lt"] * mc) if (row["w_lt"] and mc and ma in self.lt_set) else None})
            row.update(self.per.get(ma, {}))
            if row["sigma"] is None and not self.lite:
                row["sigma_ly_do"] = self.sigma_ly_do or "engine HHP chưa có μ/σ của %s" % ma
        ls, sg, kl = row["loi_suat"] or {}, row["sigma"] or {}, row["kl"] or {}
        sh = row["so_huu"]
        row["txt"] = {"so_huu": ("%s (%s · %s)" % (M.share_txt(sh["ty_le"]), sh["tier"],
                                                    M.ddmmyyyy(M.parse_day(sh["tu"])))) if sh else CAN,
                      "mcap": M.nghin_ty(row["mcap"]), "phan_nam": M.nghin_ty(row["phan_nam"]),
                      "gia": M.k_txt((row["gia"] or {}).get("dong")), "r_1t": M.pct_txt(ls.get("r_1t")),
                      "r_13t": M.pct_txt(ls.get("r_13t")), "r_ytd": M.pct_txt(ls.get("r_ytd")),
                      "r_dinh_52t": M.pct_txt(ls.get("r_dinh_52t")), "sigma": M.sigma_txt(sg.get("z")),
                      "kl": M.x_txt(kl.get("ty_le"))}
        return row

    def _chart_json(self):
        base = self.base
        grid = [w["fri"] for w in self.ser[base]["w"] if w["fri"] >= M.friday(self.rebase_from)]
        q, goc = {}, {}
        for s in self.priced:
            by = {w["fri"]: w["close"] for w in self.ser[s]["w"]}
            c0 = next((by[f] for f in grid if f in by), None)
            q[s] = [(100.0 * by[f] / c0) if (c0 and f in by) else None for f in grid]
            g0 = next((f for f in grid if f in by), None)
            goc[s] = iso(g0)
        vd, vv = self.kho.vni()
        k = bisect.bisect_right(vd, self.data_to)
        vby = {w["fri"]: w["close"] for w in M.weeks_of(vd[:k], vv[:k])}
        v0 = next((vby[f] for f in grid if f in vby), None)
        return {"tu": iso(self.rebase_from), "x": [iso(f) for f in grid], "quy_100": q, "goc": goc,
                "vni": [(100.0 * vby[f] / v0) if (v0 and f in vby) else None for f in grid]}

    def _kl_chart(self):
        wn = self.ser[self.base]["wn"]
        comp, op = self.complete(wn), self.open_week(wn)
        rows = [{"fri": iso(comp[i]["fri"]), "ty_le": M.vol_ratio(comp, i)}
                for i in range(max(0, len(comp) - M.VOL_CHART_WEEKS), len(comp))]
        kl = self.per.get(self.base, {}).get("kl", {})
        return {"ma": self.base, "tuan": rows,
                "mo": {"fri": iso(op["fri"]), "so_phien": op["n"], "ty_le": kl.get("mo_ty_le")} if op else None}

    def _val_chart(self):
        sg = self.per.get(self.base, {}).get("sigma")
        ser = self.kho.hhp_ser.get(self.base, {}).get(sg["metric"]) if sg else None
        if not ser:
            return None
        return {"ma": self.base, "metric": sg["metric"], "mu": sg["mu"], "sd": sg["sd"],
                "tuan": [{"d": iso(d), "gia_k": p, "base_k": b, "ratio": p / b if b else None}
                         for d, p, b in zip(ser["d"], ser["price_k"], ser["base_k"])]}

    def to_json(self):
        nh = self.nhom
        out = {"schema": SCHEMA_LIVE, "script_version": SCRIPT_VERSION, "ok": self.ok, "data_to": iso(self.data_to),
               "den": iso(self.kho.den), "co_so": self.base,
               "nhom": {"id": nh.id, "ten": M.nfc(nh.get("ten")), "chu_the": M.nfc(nh.get("chu_the")),
                        "truc": M.nfc(nh.get("truc")), "loai": M.nfc(nh.get("loai")), "me": self.me,
                        "me_registry": nh.me or None, "co_so": self.base,
                        "so_ma": len([m for m, _ in nh.members if m]), "so_ma_co_gia": len(self.priced),
                        "co_ho_so": bool(self.dossier), "hoi_dong": bool(nh.get("hoi_dong"))},
               "thanh_vien": [], "lt": None, "ty_so": None, "tang": [], "zigzag": {}, "capture": [], "bung_pha": {},
               "dinh": {}, "dan_tre": None, "tuong_quan": None, "chuoi": None, "kl_co_so": None,
               "dinh_gia_co_so": None, "tin_hieu": self.signals}
        if self.ok:
            out["thanh_vien"] = self.thanh_vien
            if self.ty_so:
                ts = self.ty_so
                out["lt"] = {"gia_tri": ts["lt"], "ngay": iso(ts["ngay"]), "du": ts["du"], "tier": T_EST,
                             "phan": [{"ma": c, "w": p["w"], "mcap": p["mcap"], "ngay": iso(p["ngay"]),
                                       "phan": p["phan"]} for c, p in ts["phan"].items()],
                             "txt": {"gia_tri": nt(ts["lt"]), "thanh_phan": " · ".join(
                                 "%s %s × %s" % (c, M.share_txt(p["w"]), M.nghin_ty(p["mcap"]))
                                 for c, p in ts["phan"].items())}}
            out["ty_so"] = self._ratio_json(self.ty_so)
            out["tang"] = [self._ratio_json(t) for t in self.tang]
            out["zigzag"] = {s: {"nguong": ZZ,
                                 "pivot": [{"ngay": iso(z["days"][i]), "gia": z["closes"][i], "loai": k, "xac_nhan": True}
                                           for i, k in z["piv"]] + ([{"ngay": iso(z["days"][z["cand"][0]]),
                                                                       "gia": z["closes"][z["cand"][0]],
                                                                       "loai": z["cand"][1], "xac_nhan": False}]
                                                                     if z["cand"] else []),
                                 "chan": [dict(leg, tu=iso(leg["tu"]), den=iso(leg["den"])) for leg in z["legs"]]}
                             for s, z in self.zz.items()}
            out["capture"] = [dict(c, tu=iso(c["tu"]), den=iso(c["den"]), tier=T_EST) for c in self.captures]
            out["bung_pha"] = {s: [dict(b, day=iso(b["day"]), bung_pha=iso(b["bung_pha"])) for b in v]
                               for s, v in self.bp.items()}
            out["dinh"] = {s: [dict(p, ngay=iso(p["ngay"])) for p in v] for s, v in self.pk.items()}
            out["dan_tre"] = self.dan_tre
            out["tuong_quan"] = self.tuong_quan
            if not self.lite:
                out["chuoi"] = self._chart_json()
                out["kl_co_so"] = self._kl_chart()
                out["dinh_gia_co_so"] = self._val_chart()
        out["lite"] = self.lite
        out["sigma_ly_do"] = self.sigma_ly_do
        out["canh_bao"] = list(self.warnings)
        out["nguon_live"] = list(self.kho.sources)
        return M.clean(out)


def build_live(nhom_or_id, den=None, root=None, dossier=None, warnings=None):
    """Registry entry (or its id) → LiveNhom on the real stores (msn_reflex.paths(), env overrides honoured)."""
    warnings = [] if warnings is None else warnings
    nh = nhom_or_id
    if not isinstance(nh, dict):
        reg, w = load_registry(root)
        warnings.extend(w)
        nh = reg.nhom(M.nfc(nhom_or_id))
        if nh is None:
            raise M.MsnError("BAD_ARGS", "Registry không có nhóm \"%s\"." % nhom_or_id)
    elif not isinstance(nh, Nhom):
        nh = Nhom(nh, warnings)
    kho = KhoNhom(M.paths(), den, warnings, nh.tickers(), M.as_list(nh.get("he_sinh_thai")))
    return LiveNhom(kho, nh, dossier, warnings)
