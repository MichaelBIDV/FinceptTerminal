"""
YFinance Data Fetcher
Fetches real-time stock quotes and historical data using yfinance
Returns JSON output for Qt/C++ integration

VN stocks use VNDirect dchart API as primary source (free, accurate, no rate
limit).  yfinance is the fallback for international symbols.

Mã VN (17/09/2026): đọc kho vnstock cục bộ (SQLite, chỉ đọc) trước, DCHART sau;
không bao giờ gửi mã VN trần sang yfinance. Xem khối "Kho vnstock cục bộ".
"""

import os
import sys
import json
import re
import yfinance as yf
import pandas as pd
from datetime import datetime

# Safe JSON output boundary. `json.dumps` defaults to allow_nan=True and emits
# the bare tokens NaN / Infinity / -Infinity, none of which are valid JSON.
# QJsonDocument::fromJson() on the C++ side does not repair them — it returns a
# *null document*, so the host throws away the ENTIRE payload, not just the
# offending field. One halted bar inside a 250-row series is enough to blank a
# whole chart with no error shown. Every print/frame boundary in this file goes
# through fincept_json.
try:
    import fincept_json
except ImportError:  # defensive: scripts dir not on sys.path (unusual launcher)
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import fincept_json

# Per-HTTP-request budget for every yfinance call reachable from the daemon.
# run_daemon() is a strictly serial read -> dispatch -> write loop, so a single
# unbounded Yahoo request blocks every request queued behind it — quotes,
# sparklines, history, search and financials all stall together. yfinance's own
# default is 10s but it is applied per underlying HTTP call and silently
# inherited; pin it explicitly so the budget is visible and tunable.
# Override with FINCEPT_YF_TIMEOUT (seconds).
try:
    _NET_TIMEOUT = float(os.environ.get("FINCEPT_YF_TIMEOUT", "15"))
except (TypeError, ValueError):
    _NET_TIMEOUT = 15.0


def _num(value, digits=2):
    """`round(float(value), digits)`, or None when the cell is NaN / NA / None.

    yfinance returns NaN cells routinely: halted sessions, missing intraday
    bars, thinly-traded tickers, futures roll gaps. `round(float(nan), 2)` is
    still nan and nan is not valid JSON (see the fincept_json note above), so
    an unguarded conversion voids the whole response.
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _int(value, default=None):
    """`int(value)`, or `default` when the cell is NaN / NA / None.

    Distinct from _num because `int(nan)` does not merely produce a bad number,
    it raises ValueError — which is how one missing volume cell used to abort
    the whole loop and turn an entire price series into {"error": ...}.
    """
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# VNDirect dchart API — primary source for Vietnamese equities
# ---------------------------------------------------------------------------
import ssl as _ssl
import urllib.request as _urllib_req
import time as _time

_VND_CTX = _ssl.create_default_context()
_VND_CTX.check_hostname = False
_VND_CTX.verify_mode = _ssl.CERT_NONE

# All HOSE / HNX / UPCOM symbols are bare upper-case letters (no dots).
# Known VN100 tickers — expanded from the watchlist. This set is used to
# fast-detect Vietnamese symbols so we route them to VNDirect instead of
# yfinance (where bare "ACB" resolves to Aurora Cannabis on NYSE).
_VN_TICKERS = {
    "ACB","ANV","BCM","BID","BMP","BSI","BSR","BVH","BWE","CII",
    "CMG","CTD","CTG","CTR","CTS","DBC","DCM","DGC","DGW","DIG",
    "DPM","DSE","DXG","DXS","EIB","EVF","FPT","FRT","FTS","GAS",
    "GEE","GEX","GMD","GVR","HAG","HCM","HDB","HDC","HDG","HHV",
    "HPG","HSG","HT1","IMP","KBC","KDC","KDH","KOS","LPB","MBB",
    "MSB","MSN","MWG","NAB","NKG","NLG","NT2","NVL","OCB","PAN",
    "PC1","PDR","PHR","PLX","PNJ","POW","PPC","PVD","PVS","PVT",
    "REE","SAB","SBT","SCS","SHB","SIP","SJS","SSB","SSI","STB",
    "SZC","TCB","TCH","TMP","TPB","VCB","VCG","VCI","VGC","VHC",
    "VHM","VIB","VIC","VIX","VJC","VND","VNM","VOS","VPB","VPI",
    "VPL","VRE","VSC","VSH","VTP",
    # Bổ sung 17/09/2026 — nằm trong danh mục/watchlist HĐCV nhưng thiếu ở bản gốc.
    # Đều ngoài HOSE (ACV/IDC UPCoM, HUT HNX, KSV UPCoM) nhưng DCHART vẫn trả dữ liệu:
    # đã kiểm ACV 39,4 · HUT 12,7 · IDC 31,7 · KSV 101,3 (17/09).
    # Nhãn sàn: lấy từ kho (bảng ma) khi có; không có kho thì vẫn là "HOSE".
    "ACV","HUT","IDC","KSV",
}


def _is_vn_symbol(sym: str) -> bool:
    """Return True if the symbol is Vietnamese (xem _vn_route: tập cứng ∪ kho, .VN, chỉ số).

    Không dùng heuristic "2-4 chữ hoa" — 123 mã VN trùng mã Mỹ (ACB, MCH, VNM…).
    """
    return _vn_route(sym) is not None


def _vndirect_fetch_one_quote(sym, ts_from, ts_to, mult=1000, exchange="HOSE"):
    """Fetch a single VN symbol quote. Returns (quote_dict, None) or (None, sym).

    mult: DCHART trả cổ phiếu theo NGHÌN đồng (×1000) nhưng chỉ số theo ĐIỂM (×1).
    """
    try:
        url = (f"https://dchart-api.vndirect.com.vn/dchart/history"
               f"?resolution=D&symbol={sym}&from={ts_from}&to={ts_to}")
        req = _urllib_req.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _urllib_req.urlopen(req, timeout=10, context=_VND_CTX) as resp:
            data = json.loads(resp.read())
        if not data.get("t") or len(data["t"]) == 0:
            return None, sym
        close = data["c"][-1] * mult
        prev = data["c"][-2] * mult if len(data["c"]) >= 2 else close
        change = close - prev
        change_pct = (change / prev * 100) if prev else 0
        vol = data["v"][-1] if "v" in data and data["v"] else 0
        high = data["h"][-1] * mult if "h" in data and data["h"] else None
        low = data["l"][-1] * mult if "l" in data and data["l"] else None
        opn = data["o"][-1] * mult if "o" in data and data["o"] else None
        return {
            "symbol": sym,
            "price": round(close, 2),
            "change": round(change, 2),
            "change_percent": round(change_pct, 2),
            "volume": int(vol),
            "high": round(high, 2) if high else None,
            "low": round(low, 2) if low else None,
            "open": round(opn, 2) if opn else None,
            "previous_close": round(prev, 2),
            "timestamp": int(datetime.now().timestamp()),
            "exchange": exchange,
        }, None
    except Exception:
        return None, sym


def _vndirect_batch_quotes(symbols):
    """Fetch quotes for *Vietnamese* symbols via VNDirect dchart API.
    Uses concurrent requests (10 threads) for ~3-4x speedup.
    Returns (list_of_quote_dicts, list_of_failed_symbols).

    `symbol` trả về (và mã trong danh sách lỗi) là CHUỖI GỐC app gửi ('ACB.VN',
    '^VNINDEX'): hub khớp theo topic market:quote:<chuỗi gốc>.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    ts_to = int(_time.time())
    ts_from = ts_to - 7 * 86400
    results = []
    failed = []
    # Định tuyến + sàn đọc ở luồng chính (không đụng SQLite trong luồng phụ);
    # 'ACB' và 'ACB.VN' dùng chung một request.
    jobs = {}
    for sym in symbols:
        bare, kind, mult = _vn_route(sym) or (sym, "stock", 1000)
        jobs.setdefault(bare, (mult, _vn_san(bare, kind), []))[2].append(sym)
    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = {pool.submit(_vndirect_fetch_one_quote, bare, ts_from, ts_to, job[0], job[1]): bare
                for bare, job in jobs.items()}
        for fut in as_completed(futs):
            quote, fail_sym = fut.result()
            origs = jobs[futs[fut]][2]
            if quote:
                results.extend(dict(quote, symbol=o) for o in origs)
            if fail_sym:
                failed.extend(origs)
    return results, failed


def _vndirect_fetch_one_sparkline(sym, ts_from, ts_to, mult=1000):
    """Fetch sparkline for a single VN symbol. Returns (sym, closes) or (sym, None)."""
    try:
        url = (f"https://dchart-api.vndirect.com.vn/dchart/history"
               f"?resolution=60&symbol={sym}&from={ts_from}&to={ts_to}")
        req = _urllib_req.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _urllib_req.urlopen(req, timeout=10, context=_VND_CTX) as resp:
            data = json.loads(resp.read())
        if not data.get("c") or len(data["c"]) == 0:
            return sym, None
        closes = [round(v * mult, 2) for v in data["c"]]
        return sym, closes
    except Exception:
        return sym, None


def _vndirect_batch_sparklines(symbols, period="5d"):
    """Fetch sparkline (close series) for Vietnamese symbols via VNDirect.
    Uses concurrent requests (10 threads) for ~3-4x speedup.
    Returns (dict {sym: [closes]}, list_of_failed_symbols) — khoá là chuỗi gốc."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    ts_to = int(_time.time())
    days = 7 if period in ("5d", "1wk") else 31
    ts_from = ts_to - days * 86400
    result = {}
    failed = []
    jobs = {}
    for sym in symbols:
        bare, _kind, mult = _vn_route(sym) or (sym, "stock", 1000)
        jobs.setdefault(bare, (mult, []))[1].append(sym)
    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = {pool.submit(_vndirect_fetch_one_sparkline, bare, ts_from, ts_to, job[0]): bare
                for bare, job in jobs.items()}
        for fut in as_completed(futs):
            bare, closes = fut.result()
            origs = jobs[bare][1]
            if closes:
                result.update((o, closes) for o in origs)
            else:
                failed.extend(origs)
    return result, failed


# ---------------------------------------------------------------------------
# Kho vnstock cục bộ — nguồn chính cho mã VN (hợp đồng: fincept_bridge/SPEC_VNSTOCK.md)
# ---------------------------------------------------------------------------
# - Chỉ đọc (mode=ro, timeout 0.5 s), mở-đọc-đóng mỗi truy vấn: daemon xử lý TUẦN TỰ,
#   một lần chờ khoá là chặn mọi quote/chart xếp sau (watchdog 90 s, handshake 15 s).
# - Giá cổ phiếu trong kho đã là ĐỒNG, chỉ số là ĐIỂM → đọc kho KHÔNG nhân hệ số.
#   Chỉ DCHART (nghìn đồng) mới cần `mult`.
# - Kho thiếu/khoá/hỏng → coi như không có, lui DCHART. Mã VN không bao giờ rơi xuống
#   yfinance mã trần ("ACB" trên Yahoo là Aurora Cannabis).
# - Chỉ thư viện chuẩn, import nhẹ: SYNC của provision chỉ chép đúng tệp này.
import sqlite3 as _sqlite3
from urllib.parse import quote as _url_quote
from datetime import date as _date, timedelta as _timedelta, timezone as _timezone

_VN_STORE_DEFAULT = os.path.expanduser(
    "~/SECOND BRAIN-OBSIDIAN/_System/fincept_bridge/vnstore/vn_store.db")
_VN_STATE_DEFAULT = os.path.expanduser(
    "~/SECOND BRAIN-OBSIDIAN/_System/fincept_bridge/state")
_ICT = _timezone(_timedelta(hours=7))
# Chỉ số: DCHART trả ĐIỂM → không bao giờ được lẫn vào _VN_TICKERS (×1000).
_VN_INDICES = {"VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX"}
_VN_INDEX_NAMES = {"VNINDEX": "VN-Index", "VN30": "VN30-Index",
                   "HNXINDEX": "HNX-Index", "UPCOMINDEX": "UPCoM-Index"}
# Mã VN trùng mã nằm sẵn trong cấu hình mặc định của C++ (AGG = iShares ở panel Bonds):
# dạng trần giữ nghĩa Mỹ, muốn An Gia thì gõ "AGG.VN".
_VN_LOAI_TRU = {"AGG"}
_VN_SAN = {"HOSE", "HNX", "UPCOM"}
_VN_BUSY_S = 5.0       # kho khoá/hỏng → bỏ qua kho chừng này giây (khỏi chờ timeout lặp lại)
_VN_STALE_DAYS = 5     # nến cuối cũ hơn mức này → hỏi DCHART (collector có thể đã chết)
_VN_PERIOD_NGAY = {"1d": 1, "5d": 7, "1mo": 31, "3mo": 92, "6mo": 183, "1y": 366,
                   "2y": 731, "5y": 1827, "10y": 3653}
# yfinance hiểu period '1d'/'5d' là số PHIÊN; theo ngày lịch thì sáng thứ Hai sẽ rỗng.
_VN_PERIOD_PHIEN = {"1d": 1, "5d": 5}
_VN_DCHART_RES = {"1m": "1", "2m": "1", "5m": "5", "15m": "15", "30m": "30",
                  "60m": "60", "90m": "60", "1h": "60"}
_VN_RATIO_KEYS = ("peRatio", "forwardPE", "priceToBook", "priceToSales", "pegRatio",
                  "debtToEquity", "returnOnEquity", "returnOnAssets", "profitMargin",
                  "operatingMargin", "grossMargin", "currentRatio", "quickRatio",
                  "dividendYield", "revenuePerShare", "bookValuePerShare",
                  "freeCashFlowPerShare")
_VN_NGUON_RE = re.compile(r"\s—\s([^—·]+?)\s·\s[A-Z0-9-]+\s*$")
_vn_uni = {"key": None, "ok": True, "stock": frozenset(), "ma": {}}
_vn_busy = [0.0]


def _vn_store_path():
    return os.environ.get("FINCEPT_VN_STORE") or _VN_STORE_DEFAULT


def _vn_conn():
    """Kết nối chỉ đọc, hoặc None khi chưa có kho. URI phải percent-encode (đường có dấu cách)."""
    p = _vn_store_path()
    if not os.path.isfile(p):
        return None
    try:
        return _sqlite3.connect("file:" + _url_quote(p) + "?mode=ro", uri=True, timeout=0.5)
    except _sqlite3.Error:
        return None


def _vn_query(sql, args=()):
    """Một truy vấn ngắn: mở → đọc hết → đóng (không giữ snapshot/khoá giữa các request).

    Khoá/hỏng/chưa có bảng → None, và tạm ngắt kho vài giây để một request nhiều truy vấn
    không phải chờ timeout nhiều lần.
    """
    if _time.monotonic() < _vn_busy[0]:
        return None
    con = _vn_conn()
    if con is None:
        return None
    try:
        return con.execute(sql, args).fetchall()
    except _sqlite3.Error:
        _vn_busy[0] = _time.monotonic() + _VN_BUSY_S
        return None
    finally:
        con.close()


def _vn_stat(p):
    try:
        st = os.stat(p)
        return st.st_mtime_ns, st.st_size
    except OSError:
        return None


def _vn_universe():
    """Bảng `ma` trong RAM, nạp lại khi tệp kho hoặc -wal đổi (WAL: ghi mới nằm ở -wal).

    Kho có mà đọc không được → giữ bản cũ, không đổi key để lần sau thử lại; `ok` = False
    nếu chưa từng nạp được kho này (xem _vn_chua_ro).
    """
    p = _vn_store_path()
    key = (p, _vn_stat(p), _vn_stat(p + "-wal"))
    if key == _vn_uni["key"]:
        return _vn_uni
    ma, stock = {}, set()
    if key[1] is not None:
        # Kho có tệp nhưng CHƯA dựng bảng `ma` (collector chưa chạy lần nào) là trạng thái
        # BỀN, không phải khoá tạm: phải coi như kho rỗng, nếu không `ok` kẹt False và
        # _vn_chua_ro sẽ hoãn tên MỌI mã 3 chữ của Mỹ (IBM, AMD…) vĩnh viễn.
        co_bang = _vn_query("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ma'")
        if co_bang is None:
            rows = None            # khoá/hỏng → giữ bản cũ, lần sau thử lại
        elif not co_bang:
            rows = []              # chưa có bảng → kho rỗng
        else:
            rows = _vn_query("SELECT symbol, san, loai, ten, nganh, theo_doi FROM ma")
        if rows is None:
            old = _vn_uni["key"]
            _vn_uni["ok"] = bool(old and old[0] == p and old[1] is not None)
            return _vn_uni
        for sym, san, loai, ten, nganh, theo_doi in rows:
            if not sym:
                continue
            sym = str(sym).upper()
            ma[sym] = {"san": san or "", "loai": loai or "", "ten": ten or "", "nganh": nganh or ""}
            if theo_doi and loai == "stock" and san in _VN_SAN:
                stock.add(sym)
    _vn_uni.update(key=key, ok=True, ma=ma, stock=frozenset(stock))
    return _vn_uni


def _vn_route(sym):
    """Chuỗi app gửi → (mã trần, 'stock'|'index', hệ số DCHART), hoặc None nếu không phải VN.

    Nhận 'ACB', ' acb ', 'ACB.VN', 'VNINDEX', '^VNINDEX'. Chỉ bỏ '^' cho chỉ số VN:
    '^VIX' là chỉ số Mỹ, không phải cổ phiếu VIX. Tập cổ phiếu = _VN_TICKERS ∪ kho
    (theo_doi=1, loai=stock, HOSE/HNX/UPCOM) − _VN_LOAI_TRU; '.VN' luôn ép đi VN.
    """
    if not isinstance(sym, str):
        return None
    s = sym.strip().upper()
    ep = s.endswith(".VN")
    if ep:
        s = s[:-3]
    if s.startswith("^"):
        return (s[1:], "index", 1) if s[1:] in _VN_INDICES else None
    if s in _VN_INDICES:
        return s, "index", 1
    # chỉ chữ/số ASCII: vừa là dạng mã sàn VN, vừa không để ký tự lạ lọt vào URL DCHART
    if not (s.isascii() and s.isalnum() and len(s) <= 10):
        return None
    if ep:
        return s, "stock", 1000
    if s in _VN_LOAI_TRU:
        return None
    if s in _VN_TICKERS or s in _vn_universe()["stock"]:
        return s, "stock", 1000
    return None


def _vn_chua_ro(sym):
    """Kho có mà chưa đọc được → không biết mã 3 chữ này có phải VN: hoãn, đừng hỏi Yahoo
    (quote_names bị app ghi bền; hoãn thì lần sau app hỏi lại)."""
    s = sym.strip() if isinstance(sym, str) else ""
    return not _vn_uni["ok"] and len(s) == 3 and s.isalpha()


def _vn_san(bare, kind):
    """Sàn từ kho; không có kho thì giữ nhãn cũ ('HOSE') cho cổ phiếu."""
    m = _vn_universe()["ma"].get(bare)
    return (m and m["san"]) or ("INDEX" if kind == "index" else "HOSE")


def _vn_public(bare):
    """Mã để app lưu/gọi lại: dạng trần nếu trần tự đi VN, không thì kèm '.VN' (AGG.VN…)."""
    return bare if _vn_route(bare) else bare + ".VN"


def _vn_today():
    return datetime.now(_ICT).date()


def _vn_ts(ngay):
    """'YYYY-MM-DD' → epoch 00:00 UTC (như DCHART; dùng 00:00 giờ VN thì chart lùi 1 ngày)."""
    return int(datetime.strptime(str(ngay)[:10], "%Y-%m-%d")
               .replace(tzinfo=_timezone.utc).timestamp())


def _vn_epoch(luc):
    try:
        dt = datetime.fromisoformat(str(luc))
    except (TypeError, ValueError):
        return None
    return int((dt if dt.tzinfo else dt.replace(tzinfo=_ICT)).timestamp())


def _vn_period_start(period):
    p = (period or "6mo").lower()
    if p == "max":
        return None
    today = _vn_today()
    if p == "ytd":
        return _date(today.year, 1, 1).isoformat()
    return (today - _timedelta(days=_VN_PERIOD_NGAY.get(p, 183))).isoformat()


def _vn_make_quote(sym, price, prev, opn, high, low, vol, ts, exchange):
    price = float(price)
    prev = float(prev) if prev else price
    change = price - prev
    return {
        "symbol": sym,
        "price": round(price, 2),
        "change": round(change, 2),
        "change_percent": round(change / prev * 100, 2) if prev else 0,
        "volume": _int(vol, 0),
        "high": _num(high),
        "low": _num(low),
        "open": _num(opn),
        "previous_close": round(prev, 2),
        "timestamp": ts,
        "exchange": exchange,
    }


def _vn_store_bars(bare, start=None, end=None, n_last=None):
    """Nến ngày trong kho, tăng dần: [(ngay, mo, cao, thap, dong, kl)].

    start gồm, end KHÔNG gồm (như yfinance); n_last = chỉ lấy n phiên cuối.
    """
    sql, args = "SELECT ngay, mo, cao, thap, dong, kl FROM nen_ngay WHERE symbol=? AND dong>0", [bare]
    if start:
        sql, args = sql + " AND ngay>=?", args + [start]
    if end:
        sql, args = sql + " AND ngay<?", args + [end]
    sql += " ORDER BY ngay DESC"
    if n_last:
        sql, args = sql + " LIMIT ?", args + [int(n_last)]
    rows = _vn_query(sql, args) or []
    rows.reverse()
    return rows


def _vn_store_quote(bare):
    """Quote (dạng C++) từ kho: bảng giá gia_moi nếu không cũ hơn nến cuối, không thì
    hai nến ngày cuối. Thay đổi tính theo giá tham chiếu như bảng điện VN. None nếu kho không có."""
    kind = "index" if bare in _VN_INDICES else "stock"
    bars = _vn_store_bars(bare, n_last=2)
    g = _vn_query("SELECT ngay, luc, gia, tham_chieu, mo, cao, thap, kl FROM gia_moi"
                  " WHERE symbol=?", (bare,))
    g = g[0] if g else None
    if g and g[2] and (not bars or (g[0] or "") >= bars[-1][0]):
        ngay, luc, gia, tham_chieu, mo, cao, thap, kl = g
        truoc = [b[4] for b in bars if b[0] < (ngay or "")]
        prev = tham_chieu or (truoc[-1] if truoc else None)
        ts = _vn_epoch(luc) or (_vn_ts(ngay) if ngay else int(_time.time()))
        return _vn_make_quote(bare, gia, prev, mo, cao, thap, kl, ts, _vn_san(bare, kind))
    if not bars:
        return None
    ngay, mo, cao, thap, dong, kl = bars[-1]
    prev = bars[-2][4] if len(bars) > 1 else dong
    return _vn_make_quote(bare, dong, prev, mo, cao, thap, kl, _vn_ts(ngay), _vn_san(bare, kind))


def _vn_store_profile(bare):
    """Hồ sơ từ ho_so, bù tên/sàn/ngành từ bảng ma. None nếu kho không biết mã."""
    prof = {k: v for k, v in (_vn_universe()["ma"].get(bare) or {}).items() if v}
    rows = _vn_query("SELECT ten, san, nganh, mo_ta, website, so_cp_luu_hanh, von_dieu_le,"
                     " ngay_niem_yet FROM ho_so WHERE symbol=?", (bare,))
    if rows:
        cols = ("ten", "san", "nganh", "mo_ta", "website", "so_cp_luu_hanh", "von_dieu_le",
                "ngay_niem_yet")
        prof.update({k: v for k, v in zip(cols, rows[0]) if v not in (None, "")})
    return prof or None


def _vn_fold(s):
    """Bỏ dấu + chữ thường để 'a chau' khớp 'Á Châu'."""
    import unicodedata
    s = unicodedata.normalize("NFD", str(s or "")).replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _vn_store_search(q, limit=20):
    """Mã VN khớp truy vấn (trùng khít > bắt đầu bằng > tên chứa), dạng kết quả search."""
    qs = (q or "").strip()
    qu = qs.upper()
    qu = (qu[:-3] if qu.endswith(".VN") else qu).lstrip("^")
    if not qu:
        return []
    qf = _vn_fold(qs)
    ma = _vn_universe()["ma"]
    # kho chưa có thì vẫn tìm được chỉ số + tập mã cứng (không tên)
    pool = dict.fromkeys(_VN_INDICES | _VN_TICKERS, None)
    pool.update(ma)
    hits = []
    for sym, m in pool.items():
        m = m or {"san": "", "loai": "index" if sym in _VN_INDICES else "stock",
                  "ten": _VN_INDEX_NAMES.get(sym, ""), "nganh": ""}
        if m["loai"] not in ("stock", "index"):
            continue
        if sym == qu:
            rank = 0
        elif sym.startswith(qu):
            rank = 1
        elif len(qf) >= 2 and qf in m.setdefault("_f", _vn_fold(m["ten"])):
            rank = 2
        else:
            continue
        hits.append((rank, len(sym), sym, m))
    out = []
    for _r, _n, sym, m in sorted(hits, key=lambda h: h[:3])[:limit]:
        idx = m["loai"] == "index"
        out.append({
            "symbol": _vn_public(sym),
            "name": m["ten"] or _VN_INDEX_NAMES.get(sym, ""),
            "exchange": m["san"] or ("INDEX" if idx else ""),
            "type": "INDEX" if idx else "EQUITY",
            "currency": "VND",
            "sector": "",
            "industry": m["nganh"],
        })
    return out


def _vn_news(bare, count=20):
    """Tin theo mã từ kho cuộn của gói Vietcap (AI News + CBTT), mới nhất trước. Không có → []."""
    d = os.environ.get("FINCEPT_VN_STATE") or _VN_STATE_DEFAULT
    out = []
    for ten_tep, k_title, k_desc, mac_dinh in (
            ("kho_vc_ainews.json", "than", "mo_ta", "Vietcap AI News"),
            ("kho_vc_cbtt.json", "ten", "tom_tat", "Vietcap IQ")):
        try:
            with open(os.path.join(d, ten_tep), encoding="utf-8") as f:
                items = json.load(f).get("items") or []
        except (OSError, ValueError, AttributeError):
            continue
        for it in items:
            if not isinstance(it, dict) or str(it.get("ma") or "").upper() != bare:
                continue
            title = it.get(k_title) or it.get("tieu_de") or ""
            if not title:
                continue
            m = _VN_NGUON_RE.search(it.get("tieu_de") or "")
            out.append({
                "title": title,
                "description": it.get(k_desc) or it.get("mo_ta") or "",
                "url": it.get("goc") or it.get("link") or "",
                "publisher": it.get("nguon") or (m.group(1).strip() if m else mac_dinh),
                "published_date": str(it.get("luc") or ""),
            })
    # 'luc' cùng định dạng ISO +07:00 → so chuỗi là so thời gian
    out.sort(key=lambda a: a["published_date"], reverse=True)
    return out[:max(0, int(count))]


def _vndirect_history(bare, mult, resolution, ts_from, ts_to):
    """Một GET DCHART → [(ts, o, h, l, c, v)] đã nhân hệ số; [] nếu lỗi/rỗng."""
    url = ("https://dchart-api.vndirect.com.vn/dchart/history?resolution=%s&symbol=%s"
           "&from=%d&to=%d" % (resolution, _url_quote(bare), int(ts_from), int(ts_to)))
    try:
        req = _urllib_req.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _urllib_req.urlopen(req, timeout=10, context=_VND_CTX) as resp:
            data = json.loads(resp.read())
        t, c = data.get("t") or [], data.get("c") or []
        o, h, l, v = (data.get(k) or [] for k in ("o", "h", "l", "v"))
    except Exception:
        return []

    def at(arr, i, m=1):
        return arr[i] * m if i < len(arr) and arr[i] is not None else None

    return [(int(t[i]), at(o, i, mult), at(h, i, mult), at(l, i, mult), c[i] * mult, at(v, i) or 0)
            for i in range(min(len(t), len(c))) if c[i] is not None]


def _vn_daily(route, start=None, end=None, n_last=None):
    """Nến ngày cho mã VN: kho trước; kho rỗng, hoặc nến cuối cũ quá _VN_STALE_DAYS mà
    DCHART có phiên mới hơn → dùng DCHART. Dạng [(ngay, o, h, l, c, v)] tăng dần."""
    bare, _kind, mult = route
    bars = _vn_store_bars(bare, start, end, n_last)
    han = (_vn_today() - _timedelta(days=_VN_STALE_DAYS)).isoformat()
    can_moi = end is None or end > han
    if bars and (not can_moi or bars[-1][0] >= han):
        return bars
    ts_to = _vn_ts(end) - 1 if end else int(_time.time())
    ts_from = _vn_ts(start) if start else 946684800  # 2000-01-01
    if n_last and not start:
        ts_from = ts_to - (n_last * 2 + 10) * 86400  # đủ phiên qua cuối tuần/lễ
    dc = [(datetime.fromtimestamp(t, _timezone.utc).date().isoformat(), o, h, l, c, v)
          for t, o, h, l, c, v in _vndirect_history(bare, mult, "D", ts_from, ts_to)]
    if n_last:
        dc = dc[-int(n_last):]
    if dc and (not bars or dc[-1][0] > bars[-1][0]):
        return dc
    return bars


def _vn_mm(f, a, b):
    return b if a is None else a if b is None else f(a, b)


def _vn_gop(bars, interval):
    """Gộp nến ngày thành tuần/tháng/quý; khoá = ngày đầu kỳ (như yfinance)."""
    if interval in ("1wk", "5d"):
        def dau(d):
            return d - _timedelta(days=d.weekday())
    elif interval == "1mo":
        def dau(d):
            return d.replace(day=1)
    elif interval == "3mo":
        def dau(d):
            return d.replace(month=(d.month - 1) // 3 * 3 + 1, day=1)
    else:
        return bars
    ky = {}
    for ngay, o, h, l, c, v in bars:
        k = dau(_date.fromisoformat(str(ngay)[:10])).isoformat()
        g = ky.get(k)
        if g is None:
            ky[k] = [k, o, h, l, c, v or 0]
            continue
        if g[1] is None:
            g[1] = o
        g[2], g[3] = _vn_mm(max, g[2], h), _vn_mm(min, g[3], l)
        g[4], g[5] = c, g[5] + (v or 0)
    return [tuple(g) for g in ky.values()]


def _vn_points(bars):
    """Nến (ngay, o, h, l, c, v) → điểm lịch sử C++ (timestamp 00:00 UTC của ngày)."""
    return [{"timestamp": _vn_ts(d), "open": _num(o), "high": _num(h), "low": _num(l),
             "close": _num(c), "volume": _int(v, 0)} for d, o, h, l, c, v in bars]


def _vn_history(route, interval="1d", period="6mo", start=None, end=None):
    """Lịch sử VN theo period, hoặc theo start/end nếu có. Không có dữ liệu → [].

    Ngày/tuần/tháng: kho (tự gộp). Trong ngày: chỉ DCHART có (kho giữ nến ngày).
    """
    iv = (interval or "1d").lower()
    p = (period or "6mo").lower()
    if iv in _VN_DCHART_RES:
        now = int(_time.time())
        n_phien = None
        if start:
            ts_from, ts_to = _vn_ts(start), (_vn_ts(end) - 1 if end else now)
        else:
            # như Yahoo: 1m tối đa 7 ngày, trong ngày khác tối đa 60 ngày
            ngay = min(max(_VN_PERIOD_NGAY.get(p, 183), 7), 7 if iv == "1m" else 60)
            ts_from, ts_to, n_phien = now - ngay * 86400, now, _VN_PERIOD_PHIEN.get(p)
        rows = _vndirect_history(route[0], route[2], _VN_DCHART_RES[iv], ts_from, ts_to)
        if n_phien and rows:
            giu = set(sorted({datetime.fromtimestamp(r[0], _ICT).date() for r in rows})[-n_phien:])
            rows = [r for r in rows if datetime.fromtimestamp(r[0], _ICT).date() in giu]
        return [{"timestamp": t, "open": _num(o), "high": _num(h), "low": _num(l),
                 "close": _num(c), "volume": _int(v, 0)} for t, o, h, l, c, v in rows]
    if start or end:
        bars = _vn_daily(route, start=start, end=end)
    elif iv == "1d" and p in _VN_PERIOD_PHIEN:
        bars = _vn_daily(route, n_last=_VN_PERIOD_PHIEN[p])
    else:
        bars = _vn_daily(route, start=_vn_period_start(p))
    return _vn_points(_vn_gop(bars, iv))


def _vn_close_series(route, period):
    """Chuỗi đóng cửa cho NAV: index ngày KHÔNG múi giờ (khớp yf.download ngày), giá đồng/điểm."""
    bars = _vn_daily(route, start=_vn_period_start(period))
    if not bars:
        return None
    return pd.Series([float(b[4]) for b in bars],
                     index=pd.DatetimeIndex([str(b[0])[:10] for b in bars]), dtype="float64")


def _vn_quote(symbol, route):
    """Quote một mã VN: kho → DCHART. `symbol` trả về là chuỗi gốc. None nếu không có."""
    q = _vn_store_quote(route[0])
    if q is None:
        got, _ = _vndirect_batch_quotes([symbol])
        q = got[0] if got else None
    return dict(q, symbol=symbol) if q else None


def _vn_spark_from_store(symbols, period, out):
    """Sparkline từ nến ngày trong kho vào `out`; trả các mã kho không có."""
    n = 5 if period in ("5d", "1wk") else 22
    left = []
    for s in symbols:
        bars = _vn_store_bars(_vn_route(s)[0], n_last=n)
        if bars:
            out[s] = [round(float(b[4]), 2) for b in bars]
        else:
            left.append(s)
    return left


def _vn_info(symbol, route):
    """get_info cho mã VN: ho_so + giá (kho/DCHART), currency VND. Chỉ số không có trong kho
    thì không đưa ra (C++ đọc thiếu = 0/rỗng) — không bịa."""
    bare, kind, _ = route
    prof = _vn_store_profile(bare) or {}
    q = _vn_quote(symbol, route)
    if not prof and q is None:
        return {"error": f"Không có dữ liệu VN cho {symbol}", "symbol": symbol}
    price = q["price"] if q else None
    so_cp = prof.get("so_cp_luu_hanh")
    nam = _vn_store_bars(bare, start=(_vn_today() - _timedelta(days=365)).isoformat())
    return {
        "symbol": symbol,
        "company_name": prof.get("ten") or _VN_INDEX_NAMES.get(bare) or bare,
        "sector": prof.get("nganh", ""),
        "industry": prof.get("nganh", ""),
        "description": prof.get("mo_ta", ""),
        "website": prof.get("website", ""),
        "country": "Vietnam",
        "currency": "VND" if kind == "stock" else "",
        "exchange": prof.get("san") or _vn_san(bare, kind),
        "employees": None,
        "current_price": price,
        "market_cap": round(price * so_cp) if price and so_cp else None,
        "shares_outstanding": so_cp,
        "fifty_two_week_high": _num(max(b[2] or b[4] for b in nam)) if nam else None,
        "fifty_two_week_low": _num(min(b[3] or b[4] for b in nam)) if nam else None,
        "average_volume": _int(sum(b[5] or 0 for b in nam[-63:]) / len(nam[-63:])) if nam else None,
        "timestamp": int(datetime.now().timestamp()),
    }


def _vn_company_profile(symbol, route):
    bare, kind, _ = route
    prof = _vn_store_profile(bare)
    if not prof:
        return {"error": f"No data found for symbol: {symbol}"}
    q = _vn_store_quote(bare) or {}
    so_cp = prof.get("so_cp_luu_hanh")
    return {
        "symbol": symbol,
        "companyName": prof.get("ten") or bare,
        "sector": prof.get("nganh", ""),
        "industry": prof.get("nganh", ""),
        "website": prof.get("website", ""),
        "description": prof.get("mo_ta", ""),
        "exchange": prof.get("san") or _vn_san(bare, kind),
        "country": "Vietnam",
        "city": "",
        "address": "",
        "phone": "",
        "marketCap": round(q["price"] * so_cp) if q.get("price") and so_cp else None,
        "employees": None,
        "currency": "VND" if kind == "stock" else "",
        "beta": None,
        "price": q.get("price"),
        "changes": q.get("change_percent"),
    }


# ─────────────────────── Lợi suất TPCP Việt Nam (mã VNGB1Y … VNGB20Y) ───────────────────────
# Không có mã Yahoo nào cho lợi suất TPCP Việt Nam. Số lấy từ kho tại máy do
# _System/fincept_bridge/goi_tpcp.py dựng mỗi ngày: đường cong lợi suất HNX (par_yield) qua
# bản sao công khai trên GitHub. Đi qua đúng bốn cửa như mọi mã khác (báo giá, tên, sparkline,
# lịch sử) để tab MARKETS và cửa sổ biểu đồ không phải có trường hợp đặc biệt nào.
# ĐÂY LÀ ĐƯỜNG CONG KHỚP BẰNG MÔ HÌNH, không phải lợi suất khớp lệnh — xem canh_bao trong tệp.
_TPCP_FILE = os.environ.get("FINCEPT_TPCP_FILE") or os.path.expanduser(
    "~/SECOND BRAIN-OBSIDIAN/_System/fincept_bridge/data/tpcp_vn.json")
_TPCP_RE = re.compile(r"^VNGB(\d{1,2}Y)$", re.I)
_TPCP_CACHE = {"mtime": None, "doc": None}


def _tpcp_ky(sym):
    m = _TPCP_RE.match(str(sym or "").strip())
    return m.group(1).upper() if m else None


def _tpcp_doc():
    """Đọc kho một lần cho mỗi phiên bản tệp (chế độ daemon giữ tiến trình sống)."""
    try:
        mt = os.path.getmtime(_TPCP_FILE)
    except OSError:
        return None
    if _TPCP_CACHE["mtime"] != mt:
        try:
            with open(_TPCP_FILE, encoding="utf-8") as fh:
                _TPCP_CACHE["doc"] = json.load(fh)
            _TPCP_CACHE["mtime"] = mt
        except (OSError, ValueError):
            return None
    return _TPCP_CACHE["doc"]


def _tpcp_series(sym):
    ky = _tpcp_ky(sym)
    doc = _tpcp_doc() if ky else None
    return (doc or {}).get("ky_han", {}).get(ky) or []


def _tpcp_ts(ngay_iso):
    # 15:00 giờ VN của ngày dữ liệu — mốc chốt ngày, cùng quy ước với nến ngày của kho VN.
    y, mo, d = (int(x) for x in ngay_iso[:10].split("-"))
    return int(datetime(y, mo, d, 8, 0, tzinfo=_timezone.utc).timestamp())


def _tpcp_quote(sym):
    s = _tpcp_series(sym)
    if not s:
        return None
    ngay, gt = s[-1]
    truoc = s[-2][1] if len(s) > 1 else gt
    doi = gt - truoc
    return {"symbol": sym, "price": round(gt, 4), "change": round(doi, 4),
            # CHG% của lợi suất theo đúng quy ước Yahoo cho ^TNX (% của chính con số lợi suất),
            # để cột trong bảng BONDS so được với nhau. Cửa sổ biểu đồ đọc bằng điểm %/bp.
            "change_percent": round(doi / truoc * 100, 2) if truoc else 0.0,
            "volume": 0, "high": round(gt, 4), "low": round(gt, 4), "open": round(truoc, 4),
            "previous_close": round(truoc, 4), "timestamp": _tpcp_ts(ngay), "exchange": "HNX"}


def _tpcp_name(sym):
    ky = _tpcp_ky(sym)
    if not ky:
        return None
    so = ky[:-1]
    return f"TPCP Việt Nam {so} năm (HNX)"


def _tpcp_history(sym, period="6mo", interval="1d"):
    s = _tpcp_series(sym)
    if not s:
        return []
    p = (period or "6mo").lower()
    if p != "max":
        cuoi = datetime.strptime(s[-1][0], "%Y-%m-%d").date()
        if p == "ytd":
            dau = cuoi.replace(month=1, day=1)
        else:
            ngay = {"1d": 1, "5d": 7, "1mo": 31, "3mo": 92, "6mo": 183, "1y": 366,
                    "2y": 731, "5y": 1827, "10y": 3653}.get(p, 183)
            dau = cuoi - _timedelta(days=ngay)
        s = [x for x in s if x[0] >= dau.isoformat()]
    iv = (interval or "1d").lower()
    if iv in ("1wk", "5d", "1mo", "3mo"):
        # Gộp tuần/tháng: lấy điểm CUỐI của mỗi rổ (lợi suất chốt kỳ), không trung bình.
        gom = {}
        for ngay, gt in s:
            d = datetime.strptime(ngay, "%Y-%m-%d").date()
            if iv in ("1wk", "5d"):
                k = (d - _timedelta(days=d.weekday())).isoformat()
            elif iv == "1mo":
                k = d.strftime("%Y-%m")
            else:
                k = f"{d.year}-Q{(d.month - 1) // 3}"
            gom[k] = (ngay, gt)
        s = [list(v) for v in gom.values()]
    return [{"timestamp": _tpcp_ts(n), "open": g, "high": g, "low": g, "close": g, "volume": 0}
            for n, g in s]


def get_quote(symbol):
    """Fetch real-time quote for a single symbol"""
    try:
        vn = _vn_route(symbol)
        if vn:  # mã VN: kho → DCHART, không bao giờ yf.Ticker mã trần
            return _vn_quote(symbol, vn) or {"error": "No data available", "symbol": symbol}
        import io, contextlib
        ticker = yf.Ticker(symbol)
        _buf = io.StringIO()
        with contextlib.redirect_stdout(_buf):
            info = ticker.info
            hist = ticker.history(period="1d", timeout=_NET_TIMEOUT)

        if hist.empty:
            return {"error": "No data available", "symbol": symbol}

        current_price = hist['Close'].iloc[-1]
        previous_close = info.get('previousClose', current_price)
        change = current_price - previous_close
        change_percent = (change / previous_close) * 100 if previous_close else 0

        quote_data = {
            "symbol": symbol,
            "price": round(float(current_price), 2),
            "change": round(float(change), 2),
            "change_percent": round(float(change_percent), 2),
            "volume": int(hist['Volume'].iloc[-1]) if not hist['Volume'].empty else None,
            "high": round(float(hist['High'].iloc[-1]), 2) if not hist['High'].empty else None,
            "low": round(float(hist['Low'].iloc[-1]), 2) if not hist['Low'].empty else None,
            "open": round(float(hist['Open'].iloc[-1]), 2) if not hist['Open'].empty else None,
            "previous_close": round(float(previous_close), 2),
            "timestamp": int(datetime.now().timestamp()),
            "exchange": info.get('exchange', '')
        }

        return quote_data
    except Exception as e:
        return {"error": str(e), "symbol": symbol}

def get_historical(symbol, start_date, end_date, interval='1d'):
    """Fetch historical data for a symbol with specified interval

    Args:
        symbol: Stock symbol (e.g., 'AAPL')
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        interval: Data interval - valid values: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
                  Note: Intraday data (< 1d) is only available for last 60 days
    """
    try:
        vn = _vn_route(symbol)
        if vn:
            start = _date.fromisoformat(str(start_date)[:10]).isoformat() if start_date else None
            end = _date.fromisoformat(str(end_date)[:10]).isoformat() if end_date else None
            return [dict(pt, symbol=symbol, adj_close=pt["close"])
                    for pt in _vn_history(vn, interval, start=start, end=end)]
        import io, contextlib
        ticker = yf.Ticker(symbol)
        _buf = io.StringIO()
        with contextlib.redirect_stdout(_buf):
            hist = ticker.history(start=start_date, end=end_date, interval=interval,
                                  timeout=_NET_TIMEOUT)

        if hist.empty:
            return []

        historical_data = []
        for index, row in hist.iterrows():
            # Guard every conversion the way get_batch_quotes already does — a
            # single NaN bar must not take the whole series with it.
            close = _num(row['Close'])
            if close is None:
                continue  # a bar with no close is not a price point
            historical_data.append({
                "symbol": symbol,
                "timestamp": int(index.timestamp()),
                "open": _num(row['Open']),
                "high": _num(row['High']),
                "low": _num(row['Low']),
                "close": close,
                "volume": _int(row['Volume'], 0),
                "adj_close": close
            })

        return historical_data
    except Exception as e:
        return {"error": str(e), "symbol": symbol}

def get_historical_price(symbol, target_date):
    """Fetch closing price for a specific date

    Args:
        symbol: Stock symbol (e.g., 'AAPL')
        target_date: Target date (YYYY-MM-DD)

    Returns:
        dict with price info or error
    """
    try:
        from datetime import timedelta

        # Parse target date
        target = datetime.strptime(target_date, '%Y-%m-%d')

        vn = _vn_route(symbol)
        if vn:
            # 10 ngày lùi để qua được kỳ nghỉ lễ VN; lấy phiên gần nhất ≤ ngày yêu cầu
            bars = _vn_daily(vn, start=(target - timedelta(days=10)).strftime('%Y-%m-%d'),
                             end=(target + timedelta(days=1)).strftime('%Y-%m-%d'))
            if not bars:
                return {"found": False, "error": "No data available for this date range", "symbol": symbol}
            truoc = [b for b in bars if str(b[0])[:10] <= target_date]
            b = truoc[-1] if truoc else bars[0]
            return {"found": True, "symbol": symbol, "price": round(float(b[4]), 2),
                    "date": str(b[0])[:10], "requested_date": target_date}

        # Fetch a range around the target date (to handle weekends/holidays)
        start = target - timedelta(days=5)
        end = target + timedelta(days=1)

        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'), interval='1d',
                              timeout=_NET_TIMEOUT)

        if hist.empty:
            return {"found": False, "error": "No data available for this date range", "symbol": symbol}

        # Find the closest date <= target_date
        closest_date = None
        closest_price = None

        for index, row in hist.iterrows():
            idx_date = index.to_pydatetime().replace(tzinfo=None)
            if idx_date.date() <= target.date():
                closest_date = idx_date
                closest_price = round(float(row['Close']), 2)

        if closest_price is None:
            # If no date before or on target, take the first available
            first_row = hist.iloc[0]
            closest_date = hist.index[0].to_pydatetime()
            closest_price = round(float(first_row['Close']), 2)

        return {
            "found": True,
            "symbol": symbol,
            "price": closest_price,
            "date": closest_date.strftime('%Y-%m-%d'),
            "requested_date": target_date
        }
    except Exception as e:
        return {"found": False, "error": str(e), "symbol": symbol}

def get_info(symbol):
    """Fetch company info for a symbol"""
    try:
        vn = _vn_route(symbol)
        if vn:
            return _vn_info(symbol, vn)
        ticker = yf.Ticker(symbol)
        info = ticker.info

        # Extract comprehensive information - many more fields available from yfinance
        info_data = {
            "symbol": symbol,
            "company_name": info.get('longName', info.get('shortName', 'N/A')),
            "sector": info.get('sector', 'N/A'),
            "industry": info.get('industry', 'N/A'),
            "market_cap": info.get('marketCap'),
            "pe_ratio": info.get('trailingPE'),
            "forward_pe": info.get('forwardPE'),
            "dividend_yield": info.get('dividendYield'),
            "beta": info.get('beta'),
            "fifty_two_week_high": info.get('fiftyTwoWeekHigh'),
            "fifty_two_week_low": info.get('fiftyTwoWeekLow'),
            "average_volume": info.get('averageVolume'),
            "description": info.get('longBusinessSummary', 'N/A'),
            "website": info.get('website', 'N/A'),
            "country": info.get('country', 'N/A'),
            "currency": info.get('currency', 'USD'),
            "exchange": info.get('exchange', 'N/A'),
            "employees": info.get('fullTimeEmployees'),
            # Additional comprehensive metrics
            "current_price": info.get('currentPrice'),
            "target_high_price": info.get('targetHighPrice'),
            "target_low_price": info.get('targetLowPrice'),
            "target_mean_price": info.get('targetMeanPrice'),
            "recommendation_mean": info.get('recommendationMean'),
            "recommendation_key": info.get('recommendationKey'),
            "number_of_analyst_opinions": info.get('numberOfAnalystOpinions'),
            "total_cash": info.get('totalCash'),
            "total_debt": info.get('totalDebt'),
            "total_revenue": info.get('totalRevenue'),
            "revenue_per_share": info.get('revenuePerShare'),
            "return_on_assets": info.get('returnOnAssets'),
            "return_on_equity": info.get('returnOnEquity'),
            "gross_profits": info.get('grossProfits'),
            "free_cashflow": info.get('freeCashflow'),
            "operating_cashflow": info.get('operatingCashflow'),
            "earnings_growth": info.get('earningsGrowth'),
            "revenue_growth": info.get('revenueGrowth'),
            "gross_margins": info.get('grossMargins'),
            "operating_margins": info.get('operatingMargins'),
            "ebitda_margins": info.get('ebitdaMargins'),
            "profit_margins": info.get('profitMargins'),
            "book_value": info.get('bookValue'),
            "price_to_book": info.get('priceToBook'),
            "enterprise_value": info.get('enterpriseValue'),
            "enterprise_to_revenue": info.get('enterpriseToRevenue'),
            "enterprise_to_ebitda": info.get('enterpriseToEbitda'),
            "shares_outstanding": info.get('sharesOutstanding'),
            "float_shares": info.get('floatShares'),
            "held_percent_insiders": info.get('heldPercentInsiders'),
            "held_percent_institutions": info.get('heldPercentInstitutions'),
            "short_ratio": info.get('shortRatio'),
            "short_percent_of_float": info.get('shortPercentOfFloat'),
            "peg_ratio": info.get('trailingPegRatio'),
            "total_assets": info.get('totalAssets'),
            "total_liabilities": info.get('totalLiab', info.get('totalLiabilities')),
            "book_value_total": (info.get('bookValue') or 0) * (info.get('sharesOutstanding') or 0) if info.get('bookValue') and info.get('sharesOutstanding') else None,
            "timestamp": int(datetime.now().timestamp())
        }

        return info_data
    except Exception as e:
        return {"error": str(e), "symbol": symbol}

def get_financials(symbol):
    """Fetch financial statements for a symbol"""
    try:
        if _vn_route(symbol):
            # Kho chưa có BCTC: rỗng đúng schema, KHÔNG hỏi Yahoo (mã trần = công ty Mỹ).
            return {"symbol": symbol, "income_statement": {}, "balance_sheet": {},
                    "cash_flow": {}, "timestamp": int(datetime.now().timestamp())}
        ticker = yf.Ticker(symbol)

        # Get income statement, balance sheet, and cash flow
        income_stmt = ticker.financials
        balance_sheet = ticker.balance_sheet
        cash_flow = ticker.cashflow

        def dataframe_to_dict(df):
            """Convert pandas DataFrame to dict with cleaned values"""
            if df is None or df.empty:
                return {}
            result = {}
            for col in df.columns:
                result[str(col)] = {}
                for idx in df.index:
                    value = df.loc[idx, col]
                    if pd.notna(value):
                        result[str(col)][str(idx)] = float(value) if isinstance(value, (int, float)) else str(value)
            return result

        financials_data = {
            "symbol": symbol,
            "income_statement": dataframe_to_dict(income_stmt),
            "balance_sheet": dataframe_to_dict(balance_sheet),
            "cash_flow": dataframe_to_dict(cash_flow),
            "timestamp": int(datetime.now().timestamp())
        }

        return financials_data
    except Exception as e:
        return {"error": str(e), "symbol": symbol}

def _extract_quote_from_df(data, yf_sym, report_sym):
    """Extract a single quote dict from a yf.download DataFrame.
    yf_sym is the ticker key inside the DataFrame (may include .VN suffix);
    report_sym is the original symbol to return to the caller."""
    if not isinstance(data.columns, pd.MultiIndex):
        hist = data
    else:
        level0 = data.columns.get_level_values(0).unique().tolist()
        level1 = data.columns.get_level_values(1).unique().tolist()
        if yf_sym in level0:
            hist = data[yf_sym]
        elif yf_sym in level1:
            hist = data.xs(yf_sym, axis=1, level=1)
        else:
            return None

    if hist.empty or hist.dropna(how='all').empty:
        return None

    hist = hist.dropna(how='all')
    raw_price = hist['Close'].iloc[-1]
    if pd.isna(raw_price):
        return None
    current_price = float(raw_price)
    raw_prev = hist['Close'].iloc[-2] if len(hist) >= 2 else raw_price
    previous_close = float(raw_prev) if not pd.isna(raw_prev) else current_price
    change = current_price - previous_close
    change_percent = (change / previous_close) * 100 if previous_close else 0

    return {
        "symbol": report_sym,
        "price": round(current_price, 2),
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
        "volume": int(hist['Volume'].iloc[-1]) if not pd.isna(hist['Volume'].iloc[-1]) else 0,
        "high": round(float(hist['High'].iloc[-1]), 2) if not pd.isna(hist['High'].iloc[-1]) else None,
        "low": round(float(hist['Low'].iloc[-1]), 2) if not pd.isna(hist['Low'].iloc[-1]) else None,
        "open": round(float(hist['Open'].iloc[-1]), 2) if not pd.isna(hist['Open'].iloc[-1]) else None,
        "previous_close": round(previous_close, 2),
        "timestamp": int(datetime.now().timestamp()),
        "exchange": ""
    }


# Non-US exchange suffixes to try when a bare symbol returns no data.
_EXCHANGE_SUFFIXES = [".VN", ".NS", ".BO", ".TO", ".L", ".AX", ".HK"]


def get_batch_quotes(symbols):
    """Fetch quotes for multiple symbols.

    Vietnamese symbols (_vn_route: tập cứng ∪ kho, '.VN', chỉ số) are routed to
    VNDirect dchart API first — fresher than the store during a session —
    then the local store, then yfinance with an explicit '.VN' suffix (stocks
    only, never the bare ticker).  Everything else goes through yfinance with
    the two-pass suffix retry.
    """
    import io, contextlib

    # ── Lợi suất TPCP VN: kho tại máy, không hỏi VNDirect lẫn Yahoo ──────
    results_tpcp, symbols = [], list(symbols)
    for s in [x for x in symbols if _tpcp_ky(x)]:
        q = _tpcp_quote(s)
        if q:
            results_tpcp.append(q)
        symbols.remove(s)

    # ── Split VN vs non-VN ──────────────────────────────────────────────
    routes = {s: _vn_route(s) for s in symbols}
    vn_syms = [s for s in symbols if routes[s]]
    other_syms = [s for s in symbols if not routes[s]]

    results = list(results_tpcp)

    # ── VN path: VNDirect primary ───────────────────────────────────────
    if vn_syms:
        vnd_quotes, vnd_failed = _vndirect_batch_quotes(vn_syms)
        # DCHART trả chuỗi ĐÃ ĐIỀU CHỈNH quyền. FPT ngày 18/09/2026: DCHART 65.182 trong khi
        # giá bảng là 71.700 — tỷ lệ đúng 0,9091 (= 1/1,1) ở MỌI phiên, tức thưởng 10%, không
        # phải dữ liệu cũ. Dải giá của terminal phải khớp bảng điện nhà đầu tư đang nhìn, nên
        # lệch >1% thì lấy KHO (giá bảng VCI, làm mới 10 phút/lượt); lệch nhỏ thì giữ DCHART
        # vì trong phiên nó tươi hơn kho.
        # Chỉ đổi khi CÙNG một phiên: %thay đổi khớp nhau (≤0,05 điểm %) mà MỨC GIÁ lệch >1%
        # chính là dấu hiệu của hai cơ sở giá. Nếu %thay đổi khác nhau thì hai bên đang ở hai
        # phiên khác nhau — lúc đó kho mới là bên cũ, phải giữ DCHART.
        for q in vnd_quotes:
            kho = _vn_store_quote(routes[q["symbol"]][0]) if routes.get(q["symbol"]) else None
            if not (kho and kho.get("price") and q.get("price")):
                continue
            cung_phien = abs((kho.get("change_percent") or 0) - (q.get("change_percent") or 0)) <= 0.05
            lech_muc = abs(q["price"] - kho["price"]) / kho["price"] > 0.01
            if cung_phien and lech_muc:
                q.update({k: v for k, v in kho.items() if k != "symbol"})
        results.extend(vnd_quotes)
        # DCHART hụt → kho; còn hụt thì cổ phiếu thử Yahoo hậu tố .VN (chỉ số thì thôi)
        con_lai = []
        for s in vnd_failed:
            q = _vn_store_quote(routes[s][0])
            if q:
                results.append(dict(q, symbol=s))
            elif routes[s][1] == "stock":
                con_lai.append(s)
        vnd_failed = con_lai
        if vnd_failed:
            try:
                yf_vn = [routes[s][0] + ".VN" for s in vnd_failed]
                _buf = io.StringIO()
                with contextlib.redirect_stdout(_buf):
                    data = yf.download(yf_vn, period="5d", group_by="ticker",
                                       progress=False, threads=True, auto_adjust=True, timeout=_NET_TIMEOUT)
                if data is not None and not data.empty:
                    for yf_sym, orig in zip(yf_vn, vnd_failed):
                        try:
                            q = _extract_quote_from_df(data, yf_sym, orig)
                            if q:
                                results.append(q)
                        except Exception:
                            continue
            except Exception:
                pass

    # ── Non-VN path: yfinance with two-pass suffix retry ────────────────
    if other_syms:
        def _download(syms):
            _buf = io.StringIO()
            with contextlib.redirect_stdout(_buf):
                return yf.download(syms, period="5d", group_by='ticker',
                                   progress=False, threads=True, auto_adjust=True, timeout=_NET_TIMEOUT)
        try:
            data = _download(other_syms)
            missed = []

            if data is not None and not data.empty:
                for symbol in other_syms:
                    try:
                        q = _extract_quote_from_df(data, symbol, symbol)
                        if q:
                            results.append(q)
                        else:
                            if '.' not in symbol and not symbol.startswith('^') \
                                    and '-' not in symbol and '=' not in symbol:
                                missed.append(symbol)
                    except Exception:
                        missed.append(symbol)
            else:
                missed = [s for s in other_syms
                          if '.' not in s and not s.startswith('^')
                          and '-' not in s and '=' not in s]

            # Pass 2: retry with exchange suffixes (skip .VN — already handled)
            if missed:
                suffix_map = {}
                retry_syms = []
                for sym in missed:
                    for sfx in _EXCHANGE_SUFFIXES:
                        yf_sym = sym + sfx
                        suffix_map[yf_sym] = sym
                        retry_syms.append(yf_sym)
                if retry_syms:
                    try:
                        data2 = _download(retry_syms)
                        if data2 is not None and not data2.empty:
                            resolved = set()
                            for yf_sym, orig_sym in suffix_map.items():
                                if orig_sym in resolved:
                                    continue
                                try:
                                    q = _extract_quote_from_df(data2, yf_sym, orig_sym)
                                    if q:
                                        results.append(q)
                                        resolved.add(orig_sym)
                                except Exception:
                                    continue
                    except Exception:
                        pass
        except Exception:
            for symbol in other_syms:
                quote = get_quote(symbol)
                if quote and "error" not in quote:
                    results.append(quote)

    return results

def _extract_sparkline_from_df(data, yf_sym):
    """Extract close price list from a yf.download DataFrame for one ticker."""
    if not isinstance(data.columns, pd.MultiIndex):
        hist = data
    else:
        level0 = data.columns.get_level_values(0).unique().tolist()
        level1 = data.columns.get_level_values(1).unique().tolist()
        if yf_sym in level0:
            hist = data[yf_sym]
        elif yf_sym in level1:
            hist = data.xs(yf_sym, axis=1, level=1)
        else:
            return None
    closes = hist['Close'].dropna()
    if closes.empty:
        return None
    return [round(float(v), 4) for v in closes.tolist()]


# Month tokens used by futures shortNames, e.g. "Gold Jun 26" / "Crude Oil Jul 26".
# We strip the contract-month suffix so the panel shows "Gold", not "Gold Jun 26".
_FUTURES_MONTH_RE = re.compile(
    r'\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{2,4}$')

def _clean_display_name(symbol, info):
    """Pick the most human-readable name yfinance offers for `symbol`.

    Preference: longName (fuller, e.g. "Invesco QQQ Trust") over shortName
    (often truncated to ~30 chars). Falls back to shortName, then "".
    Futures (`=F`) have no longName and a month-stamped shortName
    ("Gold Jun 26") — strip the contract month so panels show "Gold".
    """
    name = (info.get('longName') or info.get('shortName') or '').strip()
    if not name:
        return ''
    if symbol.endswith('=F'):
        name = _FUTURES_MONTH_RE.sub('', name).strip()
    return name

def get_quote_names(symbols):
    """Resolve display names + quote currency for symbols via yfinance .info.

    Returns {"names": {symbol: name}, "currencies": {symbol: code}}. Both are
    static per symbol, so the C++ caller caches the result and only asks for
    symbols it hasn't resolved yet — the per-symbol .info cost is paid once,
    never on the quote-refresh path. Symbols yfinance can't name/price are
    simply omitted (caller keeps the raw ticker / no prefix as fallback).

    Currency is omitted for forex pairs (quoteType CURRENCY — the price is a
    rate, not a monetary amount) and for indices/yields (quoteType INDEX —
    e.g. a currency symbol on the S&P level or the 10Y yield is misleading),
    so callers only ever prefix a currency where it's meaningful.
    """
    import io, contextlib, logging
    yf_logger = logging.getLogger("yfinance")
    prev_level = yf_logger.level
    yf_logger.setLevel(logging.CRITICAL)
    names = {}
    currencies = {}
    try:
        for symbol in symbols:
            ten_tpcp = _tpcp_name(symbol)
            if ten_tpcp:
                names[symbol] = ten_tpcp          # lợi suất: không gắn tiền tệ
                continue
            vn = _vn_route(symbol)
            if vn:
                # App ghi BỀN tên/tiền tệ vào settings → mã VN tuyệt đối không hỏi Yahoo
                # ("ACB" = Aurora Cannabis, USD). Kho không có tên thì bỏ trống (app giữ mã).
                bare, kind, _ = vn
                ten = ((_vn_store_profile(bare) or {}).get("ten")
                       or (_VN_INDEX_NAMES.get(bare, "") if kind == "index" else ""))
                if ten:
                    names[symbol] = ten
                if kind == "stock":  # chỉ số: không gắn tiền tệ (như quoteType INDEX)
                    currencies[symbol] = "VND"
                continue
            if _vn_chua_ro(symbol):
                continue
            try:
                _buf = io.StringIO()
                with contextlib.redirect_stdout(_buf), contextlib.redirect_stderr(_buf):
                    info = yf.Ticker(symbol).info
                info = info or {}
                name = _clean_display_name(symbol, info)
                if name:
                    names[symbol] = name
                quote_type = (info.get("quoteType") or "").upper()
                currency = info.get("currency")
                if currency and quote_type not in ("CURRENCY", "INDEX"):
                    currencies[symbol] = currency
            except Exception:
                continue
    finally:
        yf_logger.setLevel(prev_level)
    return {"names": names, "currencies": currencies}

def get_batch_sparklines(symbols, period="5d", interval="1h"):
    """Fetch close price series for multiple symbols — used for blotter sparklines.
    Returns: {"AAPL": [170.1, 171.3, ...], "MSFT": [...], ...}

    Vietnamese symbols use the local store + VNDirect; everything else uses yfinance.
    """
    import io, contextlib

    result = {}
    symbols = list(symbols)
    for s in [x for x in symbols if _tpcp_ky(x)]:
        pts = _tpcp_history(s, period if period not in ("1d", "5d") else "1mo", "1d")
        if pts:
            result[s] = [p["close"] for p in pts]
        symbols.remove(s)

    routes = {s: _vn_route(s) for s in symbols}
    vn_syms = [s for s in symbols if routes[s]]
    other_syms = [s for s in symbols if not routes[s]]

    # ── VN path ─────────────────────────────────────────────────────────
    if vn_syms:
        # Kho chỉ giữ nến ngày: sparkline trong ngày (mặc định 1h) lấy DCHART trước, kho bù;
        # sparkline ngày thì kho trước, DCHART bù.
        if str(interval).lower() in _VN_DCHART_RES:
            vnd_sparks, vnd_failed = _vndirect_batch_sparklines(vn_syms, period)
            result.update(vnd_sparks)
            vnd_failed = _vn_spark_from_store(vnd_failed, period, result)
        else:
            left = _vn_spark_from_store(vn_syms, period, result)
            vnd_sparks, vnd_failed = _vndirect_batch_sparklines(left, period) if left else ({}, [])
            result.update(vnd_sparks)
        # Fallback failed VN stocks to yfinance with explicit .VN (never the bare ticker)
        vnd_failed = [s for s in vnd_failed if routes[s][1] == "stock"]
        if vnd_failed:
            try:
                yf_vn = [routes[s][0] + ".VN" for s in vnd_failed]
                _buf = io.StringIO()
                with contextlib.redirect_stdout(_buf):
                    data = yf.download(yf_vn, period=period, interval=interval,
                                       group_by="ticker", progress=False,
                                       threads=True, auto_adjust=True, timeout=_NET_TIMEOUT)
                if data is not None and not data.empty:
                    for yf_sym, orig in zip(yf_vn, vnd_failed):
                        try:
                            sp = _extract_sparkline_from_df(data, yf_sym)
                            if sp:
                                result[orig] = sp
                        except Exception:
                            continue
            except Exception:
                pass

    # ── Non-VN path: yfinance with two-pass suffix retry ────────────────
    if other_syms:
        def _download(syms):
            _buf = io.StringIO()
            with contextlib.redirect_stdout(_buf):
                return yf.download(syms, period=period, interval=interval,
                                   group_by='ticker', progress=False,
                                   threads=True, auto_adjust=True, timeout=_NET_TIMEOUT)
        try:
            data = _download(other_syms)
            missed = []

            if data is not None and not data.empty:
                for symbol in other_syms:
                    try:
                        sp = _extract_sparkline_from_df(data, symbol)
                        if sp:
                            result[symbol] = sp
                        elif '.' not in symbol and not symbol.startswith('^') \
                                and '-' not in symbol and '=' not in symbol:
                            missed.append(symbol)
                    except Exception:
                        missed.append(symbol)
            else:
                missed = [s for s in other_syms
                          if '.' not in s and not s.startswith('^')
                          and '-' not in s and '=' not in s]

            if missed:
                suffix_map = {}
                retry_syms = []
                for sym in missed:
                    for sfx in _EXCHANGE_SUFFIXES:
                        yf_sym = sym + sfx
                        suffix_map[yf_sym] = sym
                        retry_syms.append(yf_sym)
                if retry_syms:
                    try:
                        data2 = _download(retry_syms)
                        if data2 is not None and not data2.empty:
                            resolved = set()
                            for yf_sym, orig_sym in suffix_map.items():
                                if orig_sym in resolved:
                                    continue
                                try:
                                    sp = _extract_sparkline_from_df(data2, yf_sym)
                                    if sp:
                                        result[orig_sym] = sp
                                        resolved.add(orig_sym)
                                except Exception:
                                    continue
                    except Exception:
                        pass
        except Exception as e:
            return {"error": str(e)}

    return result


def get_batch_all(payload):
    """Unified batch fetcher — returns quotes + sparklines + histories in a single call.

    Called by MarketDataService::refresh() so one DataHub refresh tick spawns a single
    Python process rather than three (quote + sparkline + history). Shares the same
    underlying yf.download paths as the individual endpoints — no behaviour change
    per family, just fewer process spawns.

    payload = {
      "quotes":     [sym, ...],                         # optional
      "sparklines": [sym, ...],                         # optional, 5d/1h
      "histories":  [{"symbol","period","interval"}, ...],  # optional
    }

    Returns:
      {
        "quotes":     [<quote dicts from get_batch_quotes>, ...],
        "sparklines": {sym: [close, ...], ...},
        "histories":  [{"symbol","period","interval","points":[...]}],
      }
    Any family absent from `payload` is omitted from the result.
    """
    out = {}

    quote_syms = payload.get("quotes") or []
    if quote_syms:
        out["quotes"] = get_batch_quotes(quote_syms)

    spark_syms = payload.get("sparklines") or []
    if spark_syms:
        out["sparklines"] = get_batch_sparklines(spark_syms)

    hist_reqs = payload.get("histories") or []
    if hist_reqs:
        histories = []
        for req in hist_reqs:
            try:
                sym = req.get("symbol")
                period = req.get("period", "6mo")
                interval = req.get("interval", "1d")
                if not sym:
                    continue
                points = get_historical_period(sym, period, interval)
                histories.append({
                    "symbol": sym,
                    "period": period,
                    "interval": interval,
                    "points": points if isinstance(points, list) else [],
                })
            except Exception as e:
                histories.append({
                    "symbol": req.get("symbol", ""),
                    "period": req.get("period", ""),
                    "interval": req.get("interval", ""),
                    "points": [],
                    "error": str(e),
                })
        out["histories"] = histories

    return out


def get_company_profile(symbol):
    """Get company profile data formatted for peer comparison"""
    try:
        vn = _vn_route(symbol)
        if vn:
            return _vn_company_profile(symbol, vn)
        ticker = yf.Ticker(symbol)
        info = ticker.info

        if not info or 'symbol' not in info:
            return {"error": f"No data found for symbol: {symbol}"}

        # Format data to match FMP structure
        profile = {
            "symbol": info.get("symbol", symbol),
            "companyName": info.get("longName", info.get("shortName", "")),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "website": info.get("website", ""),
            "description": info.get("longBusinessSummary", ""),
            "exchange": info.get("exchange", ""),
            "country": info.get("country", ""),
            "city": info.get("city", ""),
            "address": info.get("address1", ""),
            "phone": info.get("phone", ""),
            "marketCap": info.get("marketCap", 0),
            "employees": info.get("fullTimeEmployees", 0),
            "currency": info.get("currency", "USD"),
            "beta": info.get("beta", 0),
            "price": info.get("currentPrice", info.get("regularMarketPrice", 0)),
            "changes": info.get("regularMarketChangePercent", 0),
        }

        return profile
    except Exception as e:
        return {"error": str(e)}

def get_financial_ratios(symbol):
    """Get financial ratios formatted for peer comparison"""
    try:
        vn = _vn_route(symbol)
        if vn:
            # Kho chưa có chỉ số tài chính → mọi chỉ số để null (không bịa); kho không biết mã → lỗi như bản gốc.
            if not _vn_store_profile(vn[0]):
                return {"error": f"No data found for symbol: {symbol}"}
            return {"symbol": symbol, **dict.fromkeys(_VN_RATIO_KEYS)}
        ticker = yf.Ticker(symbol)
        info = ticker.info

        if not info or 'symbol' not in info:
            return {"error": f"No data found for symbol: {symbol}"}

        # Calculate free cash flow per share
        free_cashflow = info.get("freeCashflow", 0)
        shares_outstanding = info.get("sharesOutstanding", 1)
        fcf_per_share = free_cashflow / shares_outstanding if shares_outstanding else 0

        ratios = {
            "symbol": symbol,
            "peRatio": info.get("trailingPE", 0),
            "forwardPE": info.get("forwardPE", 0),
            "priceToBook": info.get("priceToBook", 0),
            "priceToSales": info.get("priceToSalesTrailing12Months", 0),
            "pegRatio": info.get("trailingPegRatio", 0),
            "debtToEquity": info.get("debtToEquity", 0),
            "returnOnEquity": info.get("returnOnEquity", 0),
            "returnOnAssets": info.get("returnOnAssets", 0),
            "profitMargin": info.get("profitMargins", 0),
            "operatingMargin": info.get("operatingMargins", 0),
            "grossMargin": info.get("grossMargins", 0),
            "currentRatio": info.get("currentRatio", 0),
            "quickRatio": info.get("quickRatio", 0),
            "dividendYield": info.get("dividendYield", 0),
            "revenuePerShare": info.get("revenuePerShare", 0),
            "bookValuePerShare": info.get("bookValue", 0),
            "freeCashFlowPerShare": fcf_per_share,
        }

        return ratios
    except Exception as e:
        return {"error": str(e)}

def get_multiple_profiles(symbols):
    """Get company profiles for multiple symbols"""
    results = []
    for symbol in symbols:
        profile = get_company_profile(symbol)
        if profile and "error" not in profile:
            results.append(profile)
    return results

def get_multiple_ratios(symbols):
    """Get financial ratios for multiple symbols"""
    results = []
    for symbol in symbols:
        ratios = get_financial_ratios(symbol)
        if ratios and "error" not in ratios:
            results.append(ratios)
    return results

def search_symbols(query, limit=20):
    """
    Search for stock symbols using yfinance's search API.
    Fast — uses Yahoo Finance's search endpoint instead of brute-force .info calls.
    """
    try:
        from urllib.request import urlopen, Request
        from urllib.parse import quote as url_quote
        import ssl

        query_str = query.strip()
        if not query_str:
            return {"results": [], "query": query, "count": 0}

        # Mã VN lên trước (tra kho cục bộ, không tốn mạng). Chặn một nửa số chỗ thôi:
        # truy vấn rộng kiểu 'A' khớp hàng chục mã VN, đẩy hết kết quả quốc tế ra ngoài.
        vn_hits = _vn_store_search(query_str, max(3, limit // 2))
        results = list(vn_hits)
        da_co = {r["symbol"] for r in vn_hits}

        # Use Yahoo Finance search/autocomplete API (fast, no auth needed)
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={url_quote(query_str)}&quotesCount={limit}&newsCount=0&enableFuzzyQuery=false&quotesQueryId=tss_match_phrase_query"
        ctx = ssl.create_default_context()
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})

        try:
            with urlopen(req, timeout=5, context=ctx) as response:
                data = json.loads(response.read().decode())
                quotes = data.get("quotes", [])

                for q in quotes:
                    symbol = q.get("symbol", "")
                    if not symbol or symbol in da_co:
                        continue
                    # Mã trần trùng mã VN (ACB = Aurora Cannabis) phải bị bỏ: chọn dòng đó
                    # thì app lưu "ACB" rồi mọi lệnh sau vẫn đi VN → hiển thị mâu thuẫn.
                    if _vn_route(symbol):
                        continue
                    da_co.add(symbol)
                    results.append({
                        "symbol": symbol,
                        "name": q.get("longname") or q.get("shortname", ""),
                        "exchange": q.get("exchange", ""),
                        "type": q.get("quoteType", "EQUITY"),
                        "currency": q.get("currency", "USD"),
                        "sector": "",
                        "industry": q.get("industry", "")
                    })
        except Exception as search_err:
            # Fallback: try the exact symbol as a yfinance Ticker
            query_upper = query_str.upper()
            suffixes = ["", ".NS", ".BO"]
            for suffix in suffixes:
                candidate = query_upper + suffix
                if candidate in da_co or _vn_route(candidate):
                    continue
                try:
                    ticker = yf.Ticker(candidate)
                    info = ticker.info
                    if info.get("longName") or info.get("shortName"):
                        results.append({
                            "symbol": candidate,
                            "name": info.get("longName", info.get("shortName", "")),
                            "exchange": info.get("exchange", ""),
                            "type": info.get("quoteType", "EQUITY"),
                            "currency": info.get("currency", "USD"),
                            "sector": info.get("sector", ""),
                            "industry": info.get("industry", "")
                        })
                        break
                except Exception:
                    continue

        results = results[:limit]
        return {"results": results, "query": query, "count": len(results)}

    except Exception as e:
        return {"error": str(e), "query": query, "results": []}

def get_news(symbol, count=20):
    """Fetch news articles for a symbol using yfinance"""
    try:
        vn = _vn_route(symbol)
        if vn:
            # Kho tin Vietcap (AI News + CBTT). Rỗng thì trả rỗng, TUYỆT ĐỐI không hỏi
            # Yahoo: ticker.news('ACB') trả tin Aurora Cannabis.
            return {"articles": _vn_news(vn[0], count), "symbol": symbol}
        import re
        ticker = yf.Ticker(symbol)
        raw_news = ticker.news
        if not raw_news:
            return {"articles": [], "symbol": symbol}

        articles = []
        for item in raw_news[:count]:
            content = item.get("content", {})
            title = content.get("title", "")
            if not title:
                continue
            # Clean HTML from summary
            summary = content.get("summary", "")
            summary = re.sub(r'<[^>]+>', '', summary)
            pub_date = content.get("pubDate", "")
            provider = content.get("provider", {})
            publisher = provider.get("displayName", "")
            # Get URL
            url = ""
            click_url = content.get("clickThroughUrl", {})
            if click_url:
                url = click_url.get("url", "")
            if not url:
                canonical = content.get("canonicalUrl", {})
                if canonical:
                    url = canonical.get("url", "")

            articles.append({
                "title": title,
                "description": summary,
                "url": url,
                "publisher": publisher,
                "published_date": pub_date
            })

        return {"articles": articles, "symbol": symbol}
    except Exception as e:
        return {"error": str(e), "symbol": symbol, "articles": []}

def _candidate_yf_symbols(symbol):
    """Generate yfinance ticker candidates for a portfolio symbol.

    Heuristic — try the symbol as-given first, then common non-US exchange
    suffixes. We can't ask the portfolio for currency here, so we just iterate
    until something returns data. Order matters: most likely first.
    """
    s = symbol.strip().upper()
    if not s:
        return []
    # Already has an exchange suffix or is an index/crypto/forex pair → trust it.
    if '.' in s or s.startswith('^') or '-' in s or '=' in s:
        return [s]
    # Bare ticker — try US first, then Toronto, NSE, BSE, LSE, ASX, Hong Kong, Vietnam.
    return [s, f"{s}.TO", f"{s}.NS", f"{s}.BO", f"{s}.L", f"{s}.AX", f"{s}.HK", f"{s}.VN"]


def _resolve_for_history(symbols, period):
    """Resolve every input symbol to a yfinance ticker that returns data
    in the given period, AND return the close-price DataFrame for each.

    Returns: dict[input_symbol] -> (resolved_symbol, closes_series).
    Symbols that fail every candidate are omitted.

    We do this in two passes:
      1. Bulk download all bare symbols + obvious-suffix variants we need to
         cover. yf.download is one HTTP fan-out so this is cheap.
      2. For each input, pick the first candidate that yielded a non-empty
         close series.
    """
    import io, contextlib, logging

    # Mã VN dựng chuỗi đóng cửa từ kho/DCHART và KHÔNG bao giờ vào yf.download:
    # _candidate_yf_symbols thử mã trần TRƯỚC .VN, nên vị thế ACB từng được định giá
    # theo Aurora Cannabis (~3,9 USD thay vì 22.800 đ). Mã VN không có dữ liệu thì bị
    # bỏ qua (rơi vào `missing`), chứ không lui xuống Yahoo.
    vn_resolved = {}
    vn_syms = set()
    for s in symbols:
        r = _vn_route(s)
        if not r:
            continue
        vn_syms.add(s)
        ser = _vn_close_series(r, period)
        if ser is not None and not ser.empty:
            # nhãn 'VN:' chỉ để người đọc `resolved` biết nguồn; C++ chỉ đọc dates/navs/costs
            vn_resolved[s] = ("VN:" + r[0], ser)

    candidates_per_symbol = {s: _candidate_yf_symbols(s) for s in symbols if s not in vn_syms}
    all_candidates = sorted({c for variants in candidates_per_symbol.values() for c in variants})

    if not all_candidates:
        return vn_resolved

    # yfinance prints "Failed download" / HTTP error lines straight to stdout
    # AND uses the logging module. Silence both — we report misses via the
    # `missing` key in the returned JSON, and noise on stdout corrupts the
    # JSON the C++ caller is trying to parse.
    yf_logger = logging.getLogger("yfinance")
    prev_level = yf_logger.level
    yf_logger.setLevel(logging.CRITICAL)
    _buf_out = io.StringIO()
    _buf_err = io.StringIO()
    try:
        with contextlib.redirect_stdout(_buf_out), contextlib.redirect_stderr(_buf_err):
            data = yf.download(
                tickers=all_candidates,
                period=period,
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
                timeout=_NET_TIMEOUT,
            )
    finally:
        yf_logger.setLevel(prev_level)

    if data is None or data.empty:
        return vn_resolved

    single = len(all_candidates) == 1

    def closes_for(ticker):
        try:
            if single:
                return data["Close"].dropna()
            return data[ticker]["Close"].dropna()
        except Exception:
            return None

    resolved = dict(vn_resolved)
    for s, variants in candidates_per_symbol.items():
        for v in variants:
            ser = closes_for(v)
            if ser is not None and not ser.empty:
                resolved[s] = (v, ser)
                break
    return resolved


def get_portfolio_nav_history(positions, period='6mo'):
    """Reconstruct a daily NAV time series from current positions.

    positions: list of {"symbol": str, "quantity": float} dicts.
    Returns: {"dates": [...], "navs": [...], "resolved": {sym: yf_sym},
              "missing": [sym, ...]}.

    Each input symbol is resolved to a yfinance ticker via _resolve_for_history,
    which tries common exchange suffixes (.TO, .NS, .BO, .L, .AX, .HK) when the
    bare symbol returns no data. Missing closes are forward-filled per symbol so
    a symbol that listed mid-period doesn't drop the whole row.

    NAV on each date = sum(close_i * quantity_i) over all resolved symbols.

    NOTE: this back-projects NAV using CURRENT quantity at every date — it
    does not account for buys/sells inside the window. That's acceptable for
    risk metrics (Beta, MDD) which measure basket variability, not realised P&L.
    """
    try:
        if not positions:
            return {"dates": [], "navs": []}
        symbols = [p["symbol"] for p in positions if p.get("symbol")]
        qty_map = {p["symbol"]: float(p.get("quantity", 0)) for p in positions if p.get("symbol")}
        if not symbols:
            return {"dates": [], "navs": []}

        resolved = _resolve_for_history(symbols, period)
        if not resolved:
            return {"dates": [], "navs": [], "error": "no historical data for any symbol",
                    "missing": symbols}

        nav_series = None
        for sym, (yf_sym, closes) in resolved.items():
            contrib = closes.ffill() * qty_map[sym]
            if nav_series is None:
                nav_series = contrib
            else:
                nav_series = nav_series.add(contrib, fill_value=0)

        if nav_series is None or nav_series.empty:
            return {"dates": [], "navs": [], "error": "no usable closes",
                    "missing": [s for s in symbols if s not in resolved]}

        nav_series = nav_series.dropna()
        dates = [idx.strftime("%Y-%m-%d") for idx in nav_series.index]
        navs = [float(v) for v in nav_series.values]
        return {
            "dates": dates,
            "navs": navs,
            "resolved": {s: yf for s, (yf, _) in resolved.items()},
            "missing": [s for s in symbols if s not in resolved],
        }
    except Exception as e:
        return {"dates": [], "navs": [], "error": str(e)}


def get_portfolio_nav_history_replay(transactions):
    """Reconstruct true daily NAV by replaying transactions over time.

    Unlike get_portfolio_nav_history (which back-projects today's quantities),
    this walks the transaction list and computes position[sym](t) = running
    sum of BUY qty − SELL qty for transactions whose date ≤ t. The chart line
    therefore reflects when capital was actually deployed: it starts at the
    first BUY date (not 1y back from today), steps when buys/sells occur, and
    moves with market prices in between.

    transactions: list of {"date": "YYYY-MM-DD", "symbol": str, "type": str,
                           "quantity": float, "price": float}.
                  Types BUY / SELL drive position changes. DIVIDEND and SPLIT
                  are ignored for now (DIVIDEND adds cash but we don't model
                  cash; SPLIT would multiply qty but is a future addition).

    Returns: {
        "dates":  ["YYYY-MM-DD", ...],   # ascending, trading days only
        "navs":   [float, ...],           # market value of positions on each day
        "costs":  [float, ...],           # cost basis on each day (BUY-WAC, SELL reduces proportionally)
        "resolved": {sym: yf_sym}, "missing": [sym, ...]
    }
    """
    try:
        from datetime import date as _date, timedelta
        import pandas as pd

        if not transactions:
            return {"dates": [], "navs": [], "costs": []}

        # Filter to BUY / SELL only (DIVIDEND / SPLIT don't move position).
        txns = [t for t in transactions
                if str(t.get("type", "")).upper() in ("BUY", "SELL")
                and t.get("symbol") and t.get("date")]
        if not txns:
            return {"dates": [], "navs": [], "costs": []}

        # Sort ascending by date so the replay walk is monotonic.
        txns.sort(key=lambda t: t["date"])

        symbols = sorted({t["symbol"] for t in txns})
        first_date = pd.Timestamp(txns[0]["date"]).normalize()
        today = pd.Timestamp(_date.today()).normalize()
        if first_date > today:
            return {"dates": [], "navs": [], "costs": [],
                    "error": "earliest transaction date is in the future"}

        # Pick a yfinance period string that covers first_date → today with a
        # bit of slack. yfinance period accepts {1mo,3mo,6mo,1y,2y,5y,10y,ytd,max}.
        days_back = (today - first_date).days + 7
        if days_back <= 31:
            period = "1mo"
        elif days_back <= 95:
            period = "3mo"
        elif days_back <= 190:
            period = "6mo"
        elif days_back <= 370:
            period = "1y"
        elif days_back <= 740:
            period = "2y"
        elif days_back <= 1850:
            period = "5y"
        elif days_back <= 3700:
            period = "10y"
        else:
            period = "max"

        resolved = _resolve_for_history(symbols, period)
        if not resolved:
            return {"dates": [], "navs": [], "costs": [],
                    "error": "no historical data for any symbol",
                    "missing": symbols}

        # Build a DataFrame of close prices, columns = symbols, indexed by date.
        # Forward-fill so a symbol that listed mid-period contributes a stable
        # price across non-trading gaps in its own series.
        closes_df = pd.DataFrame({s: ser for s, (_yf, ser) in resolved.items()})
        closes_df = closes_df.sort_index().ffill()

        # Trim the index to the replay window: first_date → today.
        closes_df = closes_df[closes_df.index >= first_date]
        if closes_df.empty:
            return {"dates": [], "navs": [], "costs": [],
                    "error": "no trading days in the requested window"}

        # Walk transactions and the price index in lockstep. For each trading
        # day we know the cumulative position vector — apply close prices to
        # get NAV. Cost basis uses weighted-average cost (WAC): BUYs add to
        # invested capital; SELLs reduce by (sold_qty × current_avg_cost).
        positions = {s: 0.0 for s in symbols}        # qty per symbol
        wac_cost = {s: 0.0 for s in symbols}         # avg cost per share
        cost_basis_total = 0.0                       # running cost basis
        tx_idx = 0
        n_tx = len(txns)

        out_dates = []
        out_navs = []
        out_costs = []

        for ts, row in closes_df.iterrows():
            day = ts.date().isoformat()

            # Apply every transaction whose date ≤ today's trading day.
            while tx_idx < n_tx and txns[tx_idx]["date"] <= day:
                tx = txns[tx_idx]
                sym = tx["symbol"]
                qty = float(tx.get("quantity", 0))
                price = float(tx.get("price", 0))
                kind = str(tx["type"]).upper()
                if sym not in positions:
                    # Symbol has no resolved price history — track position
                    # anyway so we don't desync, but it won't contribute to NAV.
                    positions[sym] = 0.0
                    wac_cost[sym] = 0.0
                if kind == "BUY":
                    new_qty = positions[sym] + qty
                    if new_qty > 0:
                        # Weighted-average cost update.
                        wac_cost[sym] = (positions[sym] * wac_cost[sym] + qty * price) / new_qty
                    positions[sym] = new_qty
                    cost_basis_total += qty * price
                elif kind == "SELL":
                    sell_qty = min(qty, positions[sym])
                    cost_basis_total -= sell_qty * wac_cost[sym]
                    positions[sym] -= sell_qty
                    if positions[sym] <= 1e-9:
                        positions[sym] = 0.0
                        wac_cost[sym] = 0.0
                tx_idx += 1

            # NAV = Σ close × qty for symbols we have prices for on this day.
            nav = 0.0
            for s in symbols:
                if s not in row.index:
                    continue
                close = row[s]
                if pd.isna(close):
                    continue
                nav += float(close) * positions.get(s, 0.0)

            out_dates.append(day)
            out_navs.append(round(nav, 4))
            out_costs.append(round(cost_basis_total, 4))

        return {
            "dates": out_dates,
            "navs": out_navs,
            "costs": out_costs,
            "resolved": {s: yf for s, (yf, _) in resolved.items()},
            "missing": [s for s in symbols if s not in resolved],
        }
    except Exception as e:
        return {"dates": [], "navs": [], "costs": [], "error": str(e)}


def get_historical_period(symbol, period='6mo', interval='1d'):
    """Fetch historical data using a period string (e.g., '1mo', '6mo', '1y', '5y')"""
    if _tpcp_ky(symbol):
        return _tpcp_history(symbol, period, interval)
    try:
        vn = _vn_route(symbol)
        if vn:
            # Đường chart/candle widget/batch_all.histories. Kho (nến ngày) → DCHART;
            # trong ngày thì chỉ DCHART có. Không có dữ liệu → [] (không hỏi Yahoo).
            return _vn_history(vn, interval, period=period)
        import io, contextlib
        ticker = yf.Ticker(symbol)
        _buf = io.StringIO()
        with contextlib.redirect_stdout(_buf):
            hist = ticker.history(period=period, interval=interval, timeout=_NET_TIMEOUT)

        if hist.empty:
            return []

        historical_data = []
        for index, row in hist.iterrows():
            # Same NaN guard as get_historical — this is the chart path, where
            # one halted bar previously blanked the entire series.
            close = _num(row['Close'])
            if close is None:
                continue
            historical_data.append({
                "timestamp": int(index.timestamp()),
                "open": _num(row['Open']),
                "high": _num(row['High']),
                "low": _num(row['Low']),
                "close": close,
                "volume": _int(row['Volume'], 0)
            })

        return historical_data
    except Exception as e:
        return {"error": str(e), "symbol": symbol}

def resolve_symbol(symbol):
    """
    Resolve a bare stock symbol to its correct yfinance-compatible form.

    Tries the symbol as-is first, then with common exchange suffixes
    (.NS for NSE India, .BO for BSE India).

    Returns a dict with:
      - resolved_symbol: the working yfinance symbol (e.g., "PIDILITIND.NS")
      - original_symbol: what the user typed (e.g., "PIDILITIND")
      - exchange: detected exchange name (if available)
      - found: bool indicating if any variant returned data
    """
    symbol = symbol.strip().upper()
    if not symbol:
        return {"resolved_symbol": symbol, "original_symbol": symbol, "exchange": "", "found": False}

    vn = _vn_route(symbol)
    if vn:
        bare, kind, _ = vn
        # Mã đã nằm trong tập cứng / chỉ số / kho thì khỏi dò mạng. Chỉ dạng '.VN' lạ
        # mới phải hỏi một lần, để không báo found=True bừa.
        biet = bare in _VN_INDICES or bare in _VN_TICKERS or bare in _vn_universe()["ma"]
        found = bool(biet or _vn_daily(vn, n_last=1))
        # trả dạng chuẩn gọi lại được: trần nếu trần tự đi VN, không thì kèm '.VN' (AGG.VN)
        return {"resolved_symbol": _vn_public(bare) if found else symbol,
                "original_symbol": symbol,
                "exchange": _vn_san(bare, kind) if found else "",
                "found": found}

    # If it already has a suffix, verify it works and return as-is
    if '.' in symbol or symbol.startswith('^') or '-' in symbol or '=' in symbol:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d", timeout=_NET_TIMEOUT)
            exchange = ticker.info.get("exchange", "") if hasattr(ticker, 'info') else ""
            if not hist.empty:
                return {"resolved_symbol": symbol, "original_symbol": symbol, "exchange": exchange, "found": True}
        except Exception:
            pass
        return {"resolved_symbol": symbol, "original_symbol": symbol, "exchange": "", "found": False}

    # Try bare symbol first (US stocks, crypto, etc.)
    suffixes_to_try = ["", ".NS", ".BO"]
    for suffix in suffixes_to_try:
        candidate = symbol + suffix
        try:
            ticker = yf.Ticker(candidate)
            hist = ticker.history(period="5d", timeout=_NET_TIMEOUT)
            if hist is not None and not hist.empty and len(hist) >= 1:
                exchange = ""
                try:
                    exchange = ticker.info.get("exchange", "")
                except Exception:
                    pass
                return {
                    "resolved_symbol": candidate,
                    "original_symbol": symbol,
                    "exchange": exchange,
                    "found": True
                }
        except Exception:
            continue

    # Nothing worked — return original
    return {"resolved_symbol": symbol, "original_symbol": symbol, "exchange": "", "found": False}


def main(args=None):
    # Support both worker pool (args parameter) and subprocess/CLI (sys.argv)
    if args is None:
        args = sys.argv[1:]

    if len(args) < 1:
        return fincept_json.dumps({"error": "Usage: python yfinance_data.py <command> <args>"})

    command = args[0]

    if command == "quote":
        if len(args) < 2:
            result = {"error": "Usage: python yfinance_data.py quote <symbol>"}
        else:
            symbol = args[1]
            result = get_quote(symbol)

    elif command == "batch_quotes":
        if len(args) < 2:
            result = {"error": "Usage: python yfinance_data.py batch_quotes <symbol1> <symbol2> ..."}
        else:
            symbols = args[1:]
            result = get_batch_quotes(symbols)

    elif command == "historical":
        if len(args) < 4:
            result = {"error": "Usage: python yfinance_data.py historical <symbol> <start_date> <end_date> [interval]"}
        else:
            symbol = args[1]
            start_date = args[2]
            end_date = args[3]
            interval = args[4] if len(args) > 4 else '1d'
            result = get_historical(symbol, start_date, end_date, interval)

    elif command == "info":
        if len(args) < 2:
            result = {"error": "Usage: python yfinance_data.py info <symbol>"}
        else:
            symbol = args[1]
            result = get_info(symbol)

    elif command == "financials":
        if len(args) < 2:
            result = {"error": "Usage: python yfinance_data.py financials <symbol>"}
        else:
            symbol = args[1]
            result = get_financials(symbol)

    elif command == "company_profile":
        if len(args) < 2:
            result = {"error": "Usage: python yfinance_data.py company_profile <symbol>"}
        else:
            symbol = args[1]
            result = get_company_profile(symbol)

    elif command == "financial_ratios":
        if len(args) < 2:
            result = {"error": "Usage: python yfinance_data.py financial_ratios <symbol>"}
        else:
            symbol = args[1]
            result = get_financial_ratios(symbol)

    elif command == "multiple_profiles":
        if len(args) < 2:
            result = {"error": "Usage: python yfinance_data.py multiple_profiles <symbol1,symbol2,...>"}
        else:
            symbols = args[1].split(",")
            result = get_multiple_profiles(symbols)

    elif command == "multiple_ratios":
        if len(args) < 2:
            result = {"error": "Usage: python yfinance_data.py multiple_ratios <symbol1,symbol2,...>"}
        else:
            symbols = args[1].split(",")
            result = get_multiple_ratios(symbols)

    elif command == "search":
        if len(args) < 2:
            result = {"error": "Usage: python yfinance_data.py search <query> [limit]"}
        else:
            query = args[1]
            limit = int(args[2]) if len(args) > 2 else 50
            result = search_symbols(query, limit)

    elif command == "news":
        if len(args) < 2:
            result = {"error": "Usage: python yfinance_data.py news <symbol> [count]"}
        else:
            symbol = args[1]
            count = int(args[2]) if len(args) > 2 else 20
            result = get_news(symbol, count)

    elif command == "portfolio_nav_history":
        # Args layout: <period> <sym1> <qty1> <sym2> <qty2> ...
        # Period defaults to 1y if first arg looks like a symbol.
        if len(args) < 3:
            result = {"error": "Usage: yfinance_data.py portfolio_nav_history <period> <sym1> <qty1> ..."}
        else:
            period = args[1]
            tail = args[2:]
            if len(tail) % 2 != 0:
                result = {"error": "symbol/quantity arguments must be paired"}
            else:
                positions = []
                for i in range(0, len(tail), 2):
                    try:
                        positions.append({"symbol": tail[i], "quantity": float(tail[i + 1])})
                    except ValueError:
                        result = {"error": f"invalid quantity for {tail[i]}"}
                        positions = None
                        break
                if positions is not None:
                    result = get_portfolio_nav_history(positions, period)

    elif command == "portfolio_nav_history_replay":
        # Args layout: <transactions_json_path>
        # The JSON file contains a list of {date, symbol, type, quantity, price}
        # objects. We replay them over time to compute true historical NAV
        # and cost basis instead of back-projecting today's positions.
        if len(args) < 2:
            result = {"error": "Usage: yfinance_data.py portfolio_nav_history_replay <transactions_json_path>"}
        else:
            try:
                with open(args[1], "r", encoding="utf-8") as f:
                    txns = json.load(f)
                if not isinstance(txns, list):
                    result = {"error": "transactions JSON must be a list"}
                else:
                    result = get_portfolio_nav_history_replay(txns)
            except Exception as e:
                result = {"error": f"failed to read transactions JSON: {e}"}

    elif command == "historical_period":
        if len(args) < 2:
            result = {"error": "Usage: python yfinance_data.py historical_period <symbol> [period] [interval]"}
        else:
            symbol = args[1]
            period = args[2] if len(args) > 2 else '6mo'
            interval = args[3] if len(args) > 3 else '1d'
            result = get_historical_period(symbol, period, interval)

    elif command == "batch_sparklines":
        if len(args) < 2:
            result = {"error": "Usage: python yfinance_data.py batch_sparklines <sym1> <sym2> ..."}
        else:
            symbols = args[1:]
            result = get_batch_sparklines(symbols)

    elif command == "quote_names":
        if len(args) < 2:
            result = {"error": "Usage: python yfinance_data.py quote_names <sym1> <sym2> ..."}
        else:
            symbols = args[1:]
            result = get_quote_names(symbols)

    elif command == "batch_all":
        # Unified hub-refresh endpoint: payload is a single JSON blob on argv[1]
        # (or @tempfile via PythonRunner's arg-spill) describing quotes + sparklines
        # + histories to fetch. One process, one yfinance warm-up, three family
        # results. See MarketDataService::refresh().
        if len(args) < 2:
            result = {"error": "Usage: python yfinance_data.py batch_all <json_payload>"}
        else:
            raw = args[1]
            # Handle PythonRunner arg-spill: args > ~8KB land as "@/tmp/…" and
            # must be read back. Payloads for large symbol lists easily exceed
            # that threshold on Windows (32KB cmdline limit).
            if raw.startswith("@"):
                path = raw[1:]
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        raw = f.read()
                    try:
                        import os as _os
                        _os.remove(path)
                    except Exception:
                        pass
                except Exception as e:
                    result = {"error": f"batch_all: failed to read spill file: {e}"}
                    raw = None
            if raw is not None:
                try:
                    payload = json.loads(raw)
                    result = get_batch_all(payload)
                except json.JSONDecodeError as e:
                    result = {"error": f"batch_all: invalid JSON payload: {e}"}

    elif command == "resolve_symbol":
        if len(args) < 2:
            result = {"error": "Usage: python yfinance_data.py resolve_symbol <symbol>"}
        else:
            symbol = args[1]
            result = resolve_symbol(symbol)

    elif command == "historical_price":
        # Get closing price for a specific date
        if len(args) < 3:
            result = {"error": "Usage: python yfinance_data.py historical_price <symbol> <date>"}
        else:
            symbol = args[1]
            target_date = args[2]  # Format: YYYY-MM-DD
            result = get_historical_price(symbol, target_date)

    else:
        result = {"error": f"Unknown command: {command}"}

    # Return JSON for worker pool, print for subprocess/CLI
    # IMPORTANT: Do NOT use indent=2 here. The host subprocess parser
    # looks for the last line starting with '{' or '[' to extract JSON.
    # Pretty-printed JSON puts '{' alone on the first line, breaking parsing.
    # fincept_json.emit == print(dumps(...)) with NaN/Infinity scrubbed.
    return fincept_json.emit(result)

# ── Daemon mode ──────────────────────────────────────────────────────────────
#
# Long-lived worker invoked by PythonWorker on the C++ side. Reads length-prefixed
# JSON request frames from stdin, writes length-prefixed JSON response frames to
# stdout. Keeps yfinance + pandas loaded so MarketDataService refreshes don't pay
# the 2–3s import cost on every spawn.
#
# Frame format (stdin + stdout, network byte order):
#   [4 bytes big-endian uint32 length N] [N bytes UTF-8 JSON]
#
# Request JSON:  {"id": <int>, "action": "batch_all"|"batch_quotes"|..., "payload": {...}}
# Response JSON: {"id": <int>, "ok": true, "result": <any>}  or
#                {"id": <int>, "ok": false, "error": "<msg>"}
#
# Special action "shutdown" causes a clean exit. EOF on stdin also exits.

def _daemon_read_frame(stream):
    """Read one length-prefixed frame. Returns bytes payload, or None on EOF."""
    header = b""
    while len(header) < 4:
        chunk = stream.read(4 - len(header))
        if not chunk:
            return None
        header += chunk
    n = int.from_bytes(header, byteorder="big", signed=False)
    if n == 0 or n > 64 * 1024 * 1024:  # sanity: cap frames at 64 MB
        return None
    buf = b""
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def _daemon_write_frame(stream, data_bytes):
    """Write one length-prefixed frame. `data_bytes` must be bytes."""
    n = len(data_bytes)
    stream.write(n.to_bytes(4, byteorder="big", signed=False))
    stream.write(data_bytes)
    stream.flush()


def _daemon_dispatch(action, payload):
    """Run one action and return the raw result object (not wrapped).

    Mirrors the CLI dispatch in main() — every action a C++ caller might pass
    through PythonRunner is wired here so the daemon can handle it without the
    ~3s subprocess + import cost.
    """
    p = payload or {}
    if action == "batch_all":
        return get_batch_all(p)
    if action == "batch_quotes":
        return get_batch_quotes(p.get("symbols") or [])
    if action == "batch_sparklines":
        return get_batch_sparklines(p.get("symbols") or [])
    if action == "historical_period":
        return get_historical_period(
            p.get("symbol"), p.get("period", "6mo"), p.get("interval", "1d"))
    if action == "historical":
        return get_historical(
            p.get("symbol"), p.get("start_date"), p.get("end_date"), p.get("interval", "1d"))
    if action == "quote":
        return get_quote(p.get("symbol"))
    if action == "info":
        return get_info(p.get("symbol"))
    if action == "news":
        return get_news(p.get("symbol"), p.get("count", 20))
    if action == "financials":
        return get_financials(p.get("symbol"))
    if action == "company_profile":
        return get_company_profile(p.get("symbol"))
    if action == "financial_ratios":
        return get_financial_ratios(p.get("symbol"))
    if action == "multiple_ratios":
        return get_multiple_ratios(p.get("symbols") or [])
    if action == "multiple_profiles":
        return get_multiple_profiles(p.get("symbols") or [])
    if action == "search":
        return search_symbols(p.get("query") or "", int(p.get("limit", 50)))
    if action == "portfolio_nav_history":
        return get_portfolio_nav_history(p.get("positions") or [], p.get("period", "1y"))
    if action == "portfolio_nav_history_replay":
        return get_portfolio_nav_history_replay(p.get("transactions") or [])
    return {"error": f"Unknown action: {action}"}


def run_daemon():
    """Main daemon loop — read frame, dispatch, write frame, repeat."""
    import io
    # Use the raw binary stdio streams; we do our own framing.
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    # Ready marker so the C++ host knows imports are done and the worker is
    # ready to accept requests. Uses the same framing.
    try:
        ready = fincept_json.dumps_bytes({"ready": True, "pid": os.getpid()})
        _daemon_write_frame(stdout, ready)
    except Exception:
        pass

    while True:
        frame = _daemon_read_frame(stdin)
        if frame is None:
            break  # EOF or bad frame — exit
        try:
            req = json.loads(frame.decode("utf-8"))
        except Exception as e:
            err = {"id": 0, "ok": False, "error": f"bad request JSON: {e}"}
            _daemon_write_frame(stdout, fincept_json.dumps_bytes(err))
            continue

        req_id = req.get("id", 0)
        action = req.get("action", "")
        if action == "shutdown":
            resp = {"id": req_id, "ok": True, "result": {"shutdown": True}}
            _daemon_write_frame(stdout, fincept_json.dumps_bytes(resp))
            break

        try:
            result = _daemon_dispatch(action, req.get("payload"))
            resp = {"id": req_id, "ok": True, "result": result}
        except Exception as e:
            resp = {"id": req_id, "ok": False, "error": str(e)}

        # Encode before writing. Every request MUST get exactly one response
        # frame: the host correlates by id and a request that never gets a
        # frame back only ends when its deadline sweep fires. So if the result
        # itself can't be serialised, downgrade to an error frame for that id
        # rather than dropping it (or killing the loop).
        try:
            payload_bytes = fincept_json.dumps_bytes(resp)
        except Exception as e:
            payload_bytes = fincept_json.dumps_bytes(
                {"id": req_id, "ok": False, "error": f"unserialisable result for {action}: {e}"})
        try:
            _daemon_write_frame(stdout, payload_bytes)
        except Exception:
            break  # stdout is gone — the host will notice the exit


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--daemon":
        run_daemon()
    else:
        main()
