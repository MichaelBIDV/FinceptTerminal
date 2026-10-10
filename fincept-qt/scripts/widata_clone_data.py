#!/usr/bin/env python3
"""
Fincept Terminal, tab VĨ MÔ (MACRO), bản clone WiData: lớp đọc nguồn và biến đổi số liệu cho builder.

Hợp đồng: SECOND BRAIN-OBSIDIAN/_System/fincept_bridge/widata_clone_spec/DESIGN.md (§4.3 mốc thời gian, §4.7 luật
trạng thái, §8.2 lớp nguồn, §8.3 gãy chuỗi, §16 C1/C2). Gói A, TASKS §3.A.

Chỉ đọc tệp cục bộ (stdlib, không mạng). Mỗi chuỗi (sid) có danh sách ứng viên nguồn trong series_map.json; kho
collector của clone (data/widata_clone/collected/*.json) và bảng tay theo văn bản (data/widata_clone/manual/*.json),
cùng schema wdc_collected/1, luôn được thử. Mỗi ứng viên là MỘT nguồn: không ghép hai nguồn trong một chuỗi (§16 C17).
Hàm chính: Evaluator(Sources(...)).evaluate(sid, entry, policy) trả bản ghi chuỗi đúng schema dash_<id>.json.
"""
from __future__ import annotations

import calendar
import csv
import glob
import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta, timezone

ICT = timezone(timedelta(hours=7))
CLASS_ORDER = ("official", "secondary", "derived", "wigroup")
POLICIES = ("allow_wigroup", "strict")
REASON_CODES = ("no_source", "collector_pending", "license", "policy_excluded", "stale", "parse_error", "short")
PARTIAL_AUTO = ("short_history", "lagged")
TIER_RANK = {"FACT-T1": 0, "FACT-T2": 1, "EST": 2, "UNVERIFIED": 3}
PERIOD_DAYS = {"D": 7, "TP": 7, "W": 10, "M": 31, "YTD": 31, "Q": 92, "Y": 366}
RELEASE_TEXT = {"D": "Theo ngày quan sát của nguồn", "TP": "Theo ngày quan sát của nguồn", "W": "Hằng tuần",
                "M": "Hằng tháng", "YTD": "Hằng tháng (luỹ kế từ đầu năm)", "Q": "Hằng quý", "Y": "Hằng năm"}
LAG_DAYS_D = 4      # MẶC ĐỊNH: chuỗi ngày coi là trễ khi kỳ cuối cũ hơn 4 ngày lịch (2 phiên + cuối tuần)
LAG_DAYS_W = 14
STEP_VERIFY_DAYS = 45   # MẶC ĐỊNH: chuỗi bậc thang của bảng tay giữ mức tới ngày dựng, không quá ngày kiểm cuối + 45
WINDOW_DAYS = 3 * 365.25
MIN_POINTS = 3      # đợt 4 (DATA2 việc 4): ứng viên dưới 3 điểm có số không dùng được (trục suy biến, VERIFY_W3 V4)
UNIT_ALIASES = {
    "%": ("%", "percent", "pct", "phần trăm", "percent change from year ago"),
    "tỷ usd": ("tỷ usd", "billions of dollars", "$bn", "bn usd", "billions of u.s. dollars"),
    "triệu usd": ("triệu usd", "millions of dollars", "$mn", "mn usd", "tr usd", "millions of u.s. dollars"),
    "usd": ("usd", "dollars", "u.s. dollars"),
}
UNIT_FACTOR = {("triệu usd", "tỷ usd"): 1e-3, ("usd", "tỷ usd"): 1e-9, ("usd", "triệu usd"): 1e-6,
               ("tỷ usd", "triệu usd"): 1e3}


class WdcDataError(Exception):
    """Lỗi đọc nguồn có thông điệp tiếng Việt (chuyện gì + cần làm gì)."""


# ── Thời gian (DESIGN §4.3) ──────────────────────────────────────────────────


def ms_of_date(d):
    """00:00:00 UTC của ngày d (quy ước mốc điểm của DESIGN §4.3)."""
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def date_of_ms_utc(t):
    return datetime.fromtimestamp(t / 1000.0, timezone.utc).date()


def date_of_ms_ict(t):
    """Ngày lịch Việt Nam của một epoch: đúng cho cả 00:00 UTC (FRED, VCB, MSN) lẫn 00:00 ICT (WiChart)."""
    return (datetime.fromtimestamp(t / 1000.0, timezone.utc) + timedelta(hours=7)).date()


def period_end(d, freq):
    if freq in ("M", "YTD"):
        return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
    if freq == "Q":
        m = ((d.month - 1) // 3 + 1) * 3
        return date(d.year, m, calendar.monthrange(d.year, m)[1])
    if freq == "Y":
        return date(d.year, 12, 31)
    return d


def parse_period(s):
    """'2025-Q1' | '2025-06' | '2025' | '2025-06-30' -> ngày đầu kỳ."""
    s = str(s).strip()
    m = re.match(r"^(\d{4})-Q([1-4])$", s)
    if m:
        return date(int(m.group(1)), (int(m.group(2)) - 1) * 3 + 1, 1)
    m = re.match(r"^(\d{4})-(\d{2})$", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), 1)
    if re.match(r"^\d{4}$", s):
        return date(int(s), 1, 1)
    return date.fromisoformat(s[:10])


def parse_vn_date(s, year_hint=None):
    """'01/10/2026' | '06/2026' | 'T9/26' | 'Q2/26' | '02/10' (cần year_hint) -> ngày đầu kỳ hoặc ngày."""
    s = str(s or "").strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.match(r"^T(\d{1,2})/(\d{2})$", s)
    if m:
        return date(2000 + int(m.group(2)), int(m.group(1)), 1)
    m = re.match(r"^Q([1-4])/(\d{2})$", s)
    if m:
        return date(2000 + int(m.group(2)), (int(m.group(1)) - 1) * 3 + 1, 1)
    m = re.match(r"^(\d{1,2})/(\d{4})$", s)
    if m:
        return date(int(m.group(2)), int(m.group(1)), 1)
    m = re.match(r"^(\d{1,2})/(\d{1,2})$", s)
    if m and year_hint:
        return date(int(year_hint), int(m.group(2)), int(m.group(1)))
    return None


def parse_vn_number(s):
    """'−11.101' -> -11101.0 ; '+1.899' -> 1899.0 ; '26.917,8' -> 26917.8."""
    s = str(s).strip().replace("−", "-").replace(" ", "")
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def normalize(raw, freq):
    """[(ngày VN, v)] -> [[t_ms, v]] tăng dần, mốc cuối kỳ theo freq, trùng mốc giữ điểm sau cùng."""
    out = {}
    for d, v in raw:
        if d is None:
            continue
        if v is not None:
            try:
                v = float(v)
            except (TypeError, ValueError):
                v = None
            if v is not None and v != v:   # NaN
                v = None
        out[ms_of_date(period_end(d, freq))] = v
    return [[t, out[t]] for t in sorted(out)]


def month_index(d):
    return d.year * 12 + d.month - 1


def expand_step(pts, today, verified=None):
    """Mốc hiệu lực [[t, v | None]] của bảng tay -> điểm ngày làm việc (T2..T6, luôn giữ ngày mốc).

    Mỗi mốc giữ mức tới ngày trước mốc sau; mốc cuối giữ tới min(ngày dựng, ngày kiểm cuối + STEP_VERIFY_DAYS) để
    bảng tay lâu không kiểm lại thì tự thành `lagged`. Mốc null là đoạn chưa đủ văn bản: một điểm null (đường đứt)."""
    end = today
    if verified:
        end = min(end, date.fromisoformat(str(verified)[:10]) + timedelta(days=STEP_VERIFY_DAYS))
    out = []
    for i, (t, v) in enumerate(pts):
        d0 = date_of_ms_utc(t)
        if v is None:
            out.append([t, None])
            continue
        d1 = date_of_ms_utc(pts[i + 1][0]) - timedelta(days=1) if i + 1 < len(pts) else end
        d = d0
        while d <= d1:
            if d == d0 or d.weekday() < 5:
                out.append([ms_of_date(d), v])
            d += timedelta(days=1)
    return out


# ── Biến đổi (đã kiểm trong A/data_*.json; DESIGN §8.3) ─────────────────────


def _key_period(t, freq):
    d = date_of_ms_utc(t)
    return (d.year, (d.month - 1) // 3) if freq == "Q" else (d.year, d.month)


def op_yoy(pts, freq):
    """YoY % = v(t) / v(cùng kỳ năm trước) - 1, chỉ M/YTD/Q; thiếu kỳ so sánh thì bỏ điểm."""
    idx = {_key_period(t, freq): v for t, v in pts}
    out = []
    for t, v in pts:
        y, p = _key_period(t, freq)
        b = idx.get((y - 1, p))
        if v is not None and b not in (None, 0):
            out.append([t, (v / b - 1.0) * 100.0])
    return out


def op_ytd_yoy(pts, freq):
    """YoY luỹ kế: tổng T1..Tm năm nay / tổng T1..Tm năm trước - 1; năm nào thiếu tháng thì bỏ."""
    by = {}
    for t, v in pts:
        d = date_of_ms_utc(t)
        by.setdefault(d.year, {})[d.month] = v
    out = []
    for t, v in pts:
        d = date_of_ms_utc(t)
        cur, prev = by.get(d.year, {}), by.get(d.year - 1, {})
        ms = range(1, d.month + 1)
        if all(cur.get(m) is not None for m in ms) and all(prev.get(m) is not None for m in ms):
            sp = sum(prev[m] for m in ms)
            if sp:
                out.append([t, (sum(cur[m] for m in ms) / sp - 1.0) * 100.0])
    return out


def op_cumsum(pts, _freq):
    acc, out = 0.0, []
    for t, v in pts:
        if v is not None:
            acc += v
        out.append([t, acc])
    return out


def apply_post(pts, post, freq):
    for step in post or ():
        name, arg = step[0], (step[1] if len(step) > 1 else None)
        if name == "scale":
            pts = [[t, None if v is None else v * arg] for t, v in pts]
        elif name == "add":
            pts = [[t, None if v is None else v + arg] for t, v in pts]
        elif name == "yoy":
            pts = op_yoy(pts, freq)
        elif name == "ytd_yoy":
            pts = op_ytd_yoy(pts, freq)
        elif name == "cumsum":
            pts = op_cumsum(pts, freq)
        elif name == "from":
            lim = ms_of_date(date.fromisoformat(arg))
            pts = [p for p in pts if p[0] >= lim]
        else:
            raise WdcDataError("Biến đổi lạ trong series_map.json: %r. Sửa widata_clone_map.py rồi sinh lại." % name)
    return [[t, None if v is None else round(v, 6)] for t, v in pts]


# ── Kho nguồn ────────────────────────────────────────────────────────────────


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expand(path_tpl, sys_dir):
    p = path_tpl.replace("{SYS}", str(sys_dir)).replace("{HOME}", os.path.expanduser("~"))
    return os.path.expanduser(p)


def canon_unit(u):
    u = str(u or "").strip().lower()
    for c, al in UNIT_ALIASES.items():
        if u in al:
            return c
    return u


class Sources:
    """Bộ đọc nguồn có cache; ghi nhận tệp đã dùng cho manifest.sources."""

    def __init__(self, smap, sys_dir, today, warn=None):
        self.smap, self.sys_dir, self.today = smap, sys_dir, today
        self.cfg = smap.get("sources", {})
        self._cache, self.used = {}, {}
        self.warn = warn or (lambda m: None)

    # đường dẫn + ghi nhận
    def path(self, key):
        c = self.cfg.get(key)
        if not c:
            raise WdcDataError("series_map.json thiếu khai báo nguồn %r." % key)
        env = c.get("env")
        if env and os.environ.get(env):
            return os.path.expanduser(os.environ[env])
        return expand(c["path"], self.sys_dir)

    def _mark(self, path, key, cls):
        if path in self.used:
            return
        st = os.stat(path)
        self.used[path] = {"mtime": datetime.fromtimestamp(st.st_mtime, ICT).isoformat(timespec="seconds"),
                           "sha256": sha256_file(path), "producer": self.cfg.get(key, {}).get("producer", key),
                           "class": cls}

    def mtime_iso(self, path):
        return datetime.fromtimestamp(os.stat(path).st_mtime, ICT).isoformat(timespec="seconds")

    def _json(self, key):
        if key not in self._cache:
            p = self.path(key)
            if not os.path.isfile(p):
                self._cache[key] = (p, None)
            else:
                try:
                    with open(p, encoding="utf-8") as f:
                        self._cache[key] = (p, json.load(f))
                except (OSError, ValueError) as e:
                    self.warn("Không đọc được %s (%s)." % (os.path.basename(p), e))
                    self._cache[key] = (p, None)
        return self._cache[key]

    # kho widata_series_store.json
    def store_class(self, canvas_source):
        for pre, cls in self.smap.get("store_class_by_source_prefix", []):
            if str(canvas_source or "").startswith(pre):
                return cls
        return "secondary"

    def read_store(self, a):
        p, d = self._json("store")
        if d is None:
            return None, p, "parse_error", None
        cv = (d.get("canvases") or {}).get(a["canvas"])
        if not cv:
            return None, p, "stale", None
        ser = cv.get("series") or []
        line = a.get("line")
        if line:
            ser = None
            for s in cv.get("series_multi") or []:
                if s.get("name") == line or str(s.get("name", "")).startswith(line):
                    ser = s.get("series") or []
                    break
            if ser is None:
                return None, p, "stale", None
        shift = timedelta(days=int(a.get("shift_days") or 0))
        raw = [(date_of_ms_ict(x["t"]) + shift, x.get("v")) for x in ser if isinstance(x, dict) and "t" in x]
        return raw, p, None, self.store_class(cv.get("source"))

    # e-DSBB NSO (nso_edsbb_long.csv)
    def _nso(self):
        if "nso" not in self._cache:
            p = self.path("nso")
            rows = {}
            if os.path.isfile(p):
                with open(p, encoding="utf-8", newline="") as f:
                    for r in csv.DictReader(f):
                        rows.setdefault(r["indicator"], []).append(r)
            self._cache["nso"] = (p, rows if os.path.isfile(p) else None)
        return self._cache["nso"]

    def read_nso(self, a):
        p, rows = self._nso()
        if rows is None:
            return None, p, "parse_error", None
        rs = rows.get(a["code"]) or []
        if not rs:
            return None, p, "stale", None
        by = {}
        for r in rs:
            try:
                by.setdefault(r["sheet"], {})[parse_period(r["period"])] = float(r["value"])
            except (ValueError, KeyError):
                continue
        return by, p, None, "official"

    # liquidity_daily snapshot_*.json (khối rates của data.vietnambiz.vn)
    def read_liq(self, a):
        if "liq" not in self._cache:
            pat = self.path("liquidity")
            files = sorted(glob.glob(pat))
            series, good = {}, []
            for fp in files:
                try:
                    with open(fp, encoding="utf-8") as f:
                        r = json.load(f).get("rates")
                except (OSError, ValueError):
                    continue
                if not isinstance(r, dict) or "error" in r or not r:
                    continue
                good.append(fp)
                for k, v in r.items():
                    if k.endswith(("_prev", "_asof")) or not isinstance(v, (int, float)):
                        continue
                    d = parse_vn_date(r.get(k + "_asof"))
                    if d is not None:
                        series.setdefault(k, {})[d] = (v, fp)
            self._cache["liq"] = (pat, series, good, len(files))
        pat, series, good, n = self._cache["liq"]
        if not good:
            return None, pat, "parse_error", None
        pts = series.get(a["key"])
        if not pts:
            return None, pat, "stale", None
        cls = self.smap.get("liquidity_daily_classes", {}).get(a["key"], "wigroup")
        files = sorted({pts[d][1] for d in pts})
        return [(d, pts[d][0]) for d in sorted(pts)], files, None, cls

    # wd_vimo_raw.json (SSG vietnambiz: kỳ cuối + kỳ trước)
    def read_wd_vimo(self, a):
        p, d = self._json("wd_vimo")
        if d is None:
            return None, p, "parse_error", None
        for r in d:
            if r.get("chi_tieu") == a["name"]:
                d0 = parse_period(r["ngay_iso"])
                raw = [(d0, r.get("gia_tri"))]
                if a.get("prev") and r.get("ky_truoc") is not None and r.get("tan_suat") in ("thang", "quy"):
                    step = 1 if r["tan_suat"] == "thang" else 3
                    mi = month_index(d0) - step
                    raw.insert(0, (date(mi // 12, mi % 12 + 1, 1), r["ky_truoc"]))
                return raw, p, None, "wigroup"
        return None, p, "stale", None

    # bang_widata.json (ghi chú dạng 'nhãn số' của một dòng)
    def read_bang(self, a):
        p, d = self._json("bang_widata")
        if d is None:
            return None, p, "parse_error", None
        year = str(d.get("cap_nhat", ""))[:4] or None
        for r in d.get("dong") or []:
            if r.get("1 Chỉ tiêu") != a["name"]:
                continue
            m = re.search(re.escape(a["label"]) + r"\s*([+\-−]?[\d.]+(?:,\d+)?)", r.get("7 Ghi chú", ""))
            d0 = parse_vn_date(r.get("2 Kỳ"), year)
            if m and d0:
                return [(d0, parse_vn_number(m.group(1)))], p, None, "wigroup"
        return None, p, "stale", None

    def read_tpcp(self, a):
        p, d = self._json("tpcp")
        if d is None:
            return None, p, "parse_error", None
        pts = (d.get("ky_han") or {}).get(a["tenor"])
        if not pts:
            return None, p, "stale", None
        return [(parse_period(x[0]), x[1]) for x in pts], p, None, "secondary"

    def read_openbb(self, a):
        p, d = self._json("openbb")
        if d is None:
            return None, p, "parse_error", None
        s = (d.get("series_data") or {}).get(a["key"])
        if not s or not s.get("data"):
            return None, p, "stale", None
        return [(parse_period(x["d"]), x.get("v")) for x in s["data"]], p, None, "secondary"

    def read_sjc(self, a):
        p, d = self._json("vnstock_macro")
        g = (d or {}).get("gold_sjc") or {}
        if d is None:
            return None, p, "parse_error", None
        rows = [r for r in g.get("rows") or [] if "SJC 1L" in str(r.get("name"))]
        if not rows or not g.get("as_of"):
            return None, p, "stale", None
        return [(date.fromisoformat(g["as_of"]), rows[0].get(a.get("field", "sell")))], p, None, "secondary"

    READERS = {"store": "read_store", "nso": "read_nso", "liq": "read_liq", "wd_vimo": "read_wd_vimo",
               "bang": "read_bang", "tpcp": "read_tpcp", "openbb": "read_openbb", "sjc": "read_sjc"}
    SRC_FILE_KEY = {"store": "store", "nso": "nso", "liq": "liquidity", "wd_vimo": "wd_vimo", "bang": "bang_widata",
                    "tpcp": "tpcp", "openbb": "openbb", "sjc": "vnstock_macro"}

    # collected/*.json và manual/*.json (schema wdc_collected/1): sid -> [(rank, tệp, doc, rec)], mới trước
    def collected(self):
        if "collected" not in self._cache:
            idx = {}
            files = sorted(glob.glob(self.path("collected")))
            if "manual" in self.cfg:
                files += sorted(glob.glob(self.path("manual")))
            for fp in files:
                try:
                    with open(fp, encoding="utf-8") as f:
                        doc = json.load(f)
                except (OSError, ValueError) as e:
                    self.warn("Bỏ qua %s: không đọc được JSON (%s)." % (os.path.basename(fp), e))
                    continue
                if doc.get("schema") != "wdc_collected/1" or not isinstance(doc.get("series"), dict):
                    self.warn("Bỏ qua %s: không đúng schema wdc_collected/1." % os.path.basename(fp))
                    continue
                for sid, rec in doc["series"].items():
                    pts = [p for p in rec.get("points") or [] if isinstance(p, list) and len(p) == 2]
                    last = max((p[0] for p in pts if p[1] is not None), default=0)
                    idx.setdefault(sid, []).append(((last, str(doc.get("generated", ""))), fp, doc, rec))
            for v in idx.values():
                v.sort(key=lambda x: x[0], reverse=True)
            self._cache["collected"] = idx
        return self._cache["collected"]

    # ── đọc một đặc tả nguồn (một nguồn duy nhất, §16 C17): (raw [(ngày, v)], [tệp], lỗi | None, class, extra) ──
    def run_src(self, spec):
        kind = spec["src"]
        raw, p, err, cls = getattr(self, self.READERS[kind])(spec)
        paths = p if isinstance(p, list) else [p]
        extra = {"spans": [], "breaks": []}
        if kind == "nso" and raw is not None:
            raw, extra = nso_op(raw, spec)
        if err is None:
            for f in paths:
                self._mark(f, self.SRC_FILE_KEY[kind], cls)
        return raw, paths, err, cls, extra


# ── e-DSBB: mức GDP hai gốc, YoY trong từng sheet, CPI đổi gốc (DESIGN §8.3) ─


def nso_op(by_sheet, spec):
    op = spec["op"]
    extra = {"spans": [], "breaks": []}
    if op in ("gdp_level", "gdp_yoy"):
        main, newer = by_sheet.get("Dataset_Q", {}), by_sheet.get("Dataset_QI.2026", {})

        def yoy(sheet):
            return {d: (v / sheet[date(d.year - 1, d.month, 1)] - 1.0) * 100.0
                    for d, v in sheet.items() if sheet.get(date(d.year - 1, d.month, 1))}
        a, b = (main, newer) if op == "gdp_level" else (yoy(main), yoy(newer))
        out = dict(a)
        added = sorted(d for d in b if d not in out)
        for d in added:
            out[d] = b[d]
        if added and op == "gdp_level":
            extra["breaks"].append((added[0], "Từ quý này số lấy từ bảng giá so sánh 2020 (trước đó gốc 2010); "
                                              "mức hai gốc không so được với nhau"))
        return sorted(out.items()), extra
    if op in ("cpi_rebase", "cpi_yoy19"):
        b19, b24 = by_sheet.get("Dataset base 2019", {}), by_sheet.get("Dataset base 2024", {})
        first24 = min(b24) if b24 else None
        if op == "cpi_yoy19":
            out = {d: (v / b19[date(d.year - 1, d.month, 1)] - 1.0) * 100.0
                   for d, v in b19.items() if b19.get(date(d.year - 1, d.month, 1))}
            out.update({d: (v / b24[date(d.year - 1, d.month, 1)] - 1.0) * 100.0
                        for d, v in b24.items() if b24.get(date(d.year - 1, d.month, 1))})
            return sorted(out.items()), extra
        avg = [b19.get(date(2024, m, 1)) for m in range(1, 13)]
        if None in avg or not first24:
            return sorted(b19.items()), extra
        base = sum(avg) / 12.0
        out = {d: v / base * 100.0 for d, v in b19.items() if d < first24}
        if out:
            extra["spans"].append((min(out), max(out), "EST"))
        out.update(b24)
        extra["breaks"].append((first24, "NSO đổi kỳ gốc CPI 2019 sang 2024; trước mốc này là chỉ số gốc 2019 "
                                         "quy về bình quân 2024 = 100 (ước tính)"))
        return sorted(out.items()), extra
    raise WdcDataError("Phép e-DSBB lạ: %r." % op)


# ── Luật trạng thái (DESIGN §4.7) và chọn ứng viên theo source_policy (§8.2, §16 C1) ──

REASON_TEXT = {
    "no_source": "Chưa có nguồn cho chuỗi này trong hệ của ta.",
    "collector_pending": "Đang chờ collector nguồn chính thức: {planned}.",
    "license": "Dữ liệu có bản quyền, không có nguồn miễn phí hợp lệ.",
    "policy_excluded": "Nguồn hiện có thuộc lớp WiGroup, bị loại ở chế độ strict.",
    "stale": "Tệp nguồn có mặt nhưng không có số cho chuỗi này; kiểm lại collector.",
    "parse_error": "Không đọc được tệp nguồn (thiếu tệp hoặc sai định dạng).",
    "short": "Nguồn hiện có chỉ có {n} điểm số (dưới %d), chưa phải lịch sử thật để vẽ; kế hoạch: {planned}." % MIN_POINTS,
}
WIGROUP_NOTE = "Nguồn WiGroup công khai do collector của ta lưu; không lấy từ trang WiData trả phí."
# DESIGN §11 mục 6 + đợt 4 (DATA2 việc 5): tệp dữ liệu và state không được thấy tên miền API; chỉ nhãn trung tính.
_HOSTS = ((re.compile(r"(?:https?://)?(?:[\w-]+\.)*wichart[.]vn(?:/[\w./-]*)?", re.I), "API công khai WiGroup"),
          (re.compile(r"(?:https?://)?(?:[\w-]+\.)*vietnambiz[.]vn/?", re.I), "WiGroup công khai"),
          (re.compile(r"vietnam[ ]?biz", re.I), "WiGroup"),
          (re.compile(r"(?:https?://)?(?:[\w-]+\.)*widata[.]vn", re.I), "WiData"),
          (re.compile(r"(?:https?://)?(?:[\w-]+\.)*dulieukinhte[.]com", re.I), "dulieukinhte"),
          (re.compile(r"api[/]internal", re.I), "api nội bộ"))


def neutral(text):
    if not isinstance(text, str):
        return text
    for rx, label in _HOSTS:
        text = rx.sub(label, text)
    return text


def auto_reasons(pts, freq, today):
    vals = [p for p in pts if p[1] is not None]
    first, last = date_of_ms_utc(vals[0][0]), date_of_ms_utc(vals[-1][0])
    out = []
    if (first - date(last.year - 3, last.month, 1)).days > PERIOD_DAYS.get(freq, 31):
        out.append("short_history")
    if freq in ("D", "TP"):
        lag = (today - last).days > LAG_DAYS_D
    elif freq == "W":
        lag = (today - last).days > LAG_DAYS_W
    elif freq == "Q":
        lag = (today.year * 4 + (today.month - 1) // 3) - (last.year * 4 + (last.month - 1) // 3) > 2
    elif freq == "Y":
        lag = today.year - last.year > 2
    else:
        lag = month_index(today) - month_index(last) > 2
    if lag:
        out.append("lagged")
    return out


def coverage_3y(pts):
    """Phần cửa sổ 3Y (tính từ kỳ cuối của chính chuỗi) mà chuỗi phủ, 0..1, làm tròn 2 chữ số."""
    vals = [t for t, v in pts if v is not None]
    if not vals:
        return 0.0
    days = (date_of_ms_utc(vals[-1]) - date_of_ms_utc(vals[0])).days
    return round(min(1.0, days / WINDOW_DAYS), 2)


def choice_key(res, kind, i, today):
    """Khoá chọn nguồn (DESIGN §16 C17), nhỏ hơn là tốt hơn:
    (1) phủ đủ cửa sổ 3Y tính từ kỳ cuối (không short_history tự tính hay khai báo); hai ứng viên cùng chưa đủ thì
        ứng viên phủ phần lớn hơn của cửa sổ trước; (2) tầng cao hơn; (3) kỳ cuối mới hơn; (4) collected/bảng tay
        trước kho; rồi lớp khác wigroup trước wigroup, rồi thứ tự series_map."""
    auto = auto_reasons(res["points"], res["freq"], today)
    full = "short_history" not in auto and "short_history" not in res["partial_reasons"]
    last_t = max(t for t, v in res["points"] if v is not None)
    return (not full, -coverage_3y(res["points"]), TIER_RANK.get(res["tier"], 9), -last_t, kind != "collected",
            res["class"] == "wigroup", i)


def _t_end(iso, freq):
    return ms_of_date(period_end(date.fromisoformat(iso), freq))


def _uniq(xs):
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


class Evaluator:
    """Tính bản ghi chuỗi cho dash_<id>.json theo một source_policy."""

    def __init__(self, sources):
        self.src = sources

    def _from_collected(self, entry, hit):
        _rank, fp, doc, rec = hit
        freq = rec.get("freq") or entry["freq"]
        raw = [(date_of_ms_utc(p[0]), p[1]) for p in rec.get("points") or [] if isinstance(p, list) and len(p) == 2]
        pts = normalize(raw, freq)
        if rec.get("step"):
            pts = expand_step(pts, self.src.today, rec.get("kiem_lan_cuoi"))
        cu, tu = canon_unit(rec.get("unit")), canon_unit(entry.get("unit"))
        notes = rec.get("notes") or []
        notes = [notes] if isinstance(notes, str) else [str(n) for n in notes]
        if cu and tu and cu != tu:
            k = UNIT_FACTOR.get((cu, tu))
            if k is None:
                self.src.warn("Đơn vị của %s trong %s (%s) khác đơn vị trình bày (%s); giữ nguyên số."
                              % (entry.get("name", "?"), os.path.basename(fp), rec.get("unit"), entry.get("unit")))
            else:
                pts = [[t, None if v is None else v * k] for t, v in pts]
                notes.append("Đổi đơn vị %s sang %s khi dựng." % (rec.get("unit"), entry.get("unit")))
        tier = rec.get("tier") or "FACT-T1"
        cls = rec.get("class") or doc.get("class") or ("derived" if tier == "EST" else "official")
        if cls not in CLASS_ORDER:
            cls = "secondary"
        self.src._mark(fp, "manual" if "/manual/" in fp else "collected", cls)
        spans = [{"from": int(x["from"]), "to": int(x["to"]), "tier": x["tier"]} for x in rec.get("tier_spans") or []
                 if isinstance(x, dict) and {"from", "to", "tier"} <= set(x)]
        breaks = [{"t": int(x["t"]), "note": str(x.get("note", ""))} for x in rec.get("breaks") or []
                  if isinstance(x, dict) and "t" in x]
        reasons = [r for r in rec.get("partial_reasons") or [] if r not in PARTIAL_AUTO]
        kind = "manual" if "/manual/" in fp else "collected"
        return {"id": kind + ":" + os.path.basename(fp), "points": apply_post(pts, None, freq), "freq": freq,
                "class": cls, "tier": tier, "err": None, "files": [fp], "spans": spans, "breaks": breaks,
                "partial_reasons": reasons, "source_name": rec.get("source_name") or doc.get("producer", "collector"),
                "source_ref": rec.get("source_ref") or os.path.basename(fp),
                "notes": notes, "transform": None, "producer": doc.get("producer", "")}

    def _from_candidate(self, entry, c):
        freq = c.get("freq") or entry["freq"]
        raw, files, err, cls, extra = self.src.run_src(c["src"])
        res = {"id": c["id"], "freq": freq, "files": [f for f in files if f], "err": err,
               "class": cls or c.get("class", "secondary"), "tier": c.get("tier", "FACT-T2"),
               "partial_reasons": list(c.get("partial_reasons") or []), "source_name": c.get("source_name", ""),
               "source_ref": c.get("source_ref", ""), "notes": list(c.get("notes") or []),
               "transform": c.get("transform"), "producer": c.get("producer", ""), "points": [],
               "spans": [], "breaks": []}
        if err:
            return res
        res["points"] = apply_post(normalize(raw, freq), c.get("post"), freq)
        res["spans"] = [{"from": ms_of_date(period_end(a, freq)), "to": ms_of_date(period_end(b, freq)), "tier": t}
                        for a, b, t in extra["spans"]]
        res["spans"] += [{"from": _t_end(s["from"], freq), "to": _t_end(s["to"], freq), "tier": s["tier"]}
                         for s in c.get("tier_spans") or []]
        res["breaks"] = [{"t": ms_of_date(period_end(d, freq)), "note": n} for d, n in extra["breaks"]]
        res["breaks"] += [{"t": _t_end(b["date"], freq), "note": b["note"]} for b in c.get("breaks") or []]
        return res

    def evaluate(self, sid, entry, policy):
        """-> (bản ghi chuỗi, lớp nguồn đã chọn | None, các tệp đã dùng).

        Chọn MỘT ứng viên trong các ứng viên được policy cho phép và có số, theo choice_key (DESIGN §16 C17):
        đủ 3Y > tầng > mới hơn > collected/bảng tay trước kho. Không ghép hai nguồn trong một chuỗi."""
        cands = [("collected", h) for h in self.src.collected().get(sid, [])]
        cands += [("map", c) for c in entry.get("candidates") or []]
        excluded, errors, usable, shorts = [], [], [], []
        for i, (kind, c) in enumerate(cands):
            res = self._from_collected(entry, c) if kind == "collected" else self._from_candidate(entry, c)
            if policy == "strict" and res["class"] == "wigroup":
                excluded.append(res["id"])
                continue
            n_so = sum(1 for _, v in res["points"] if v is not None)
            if res["err"] or not n_so:
                errors.append(res["err"] or "stale")
                continue
            if n_so < MIN_POINTS:
                shorts.append(n_so)
                continue
            usable.append((choice_key(res, kind, i, self.src.today), res))
        chosen, pos = None, 0
        if usable:
            key, chosen = min(usable, key=lambda x: x[0])
            pos = key[-1] + 1
        freq = (chosen or {}).get("freq") or entry["freq"]
        rec = {"status": "missing", "tier": None, "tier_spans": [], "partial_reasons": [], "freq": freq,
               "unit": entry.get("unit") or "", "points": [], "as_of": None, "breaks": [],
               "meta": {"name": entry.get("name", sid), "source_name": "", "source_ref": "",
                        "release": RELEASE_TEXT.get(freq, ""), "last_updated": None, "notes": []},
               "reason": None, "reason_code": None, "source_class": None}
        if chosen is None:
            if shorts:
                code = "short"
            elif errors:
                code = "parse_error" if "parse_error" in errors else "stale"
            elif excluded:
                code = "policy_excluded"
            else:
                code = entry.get("reason_if_missing") or "no_source"
            planned = entry.get("planned_source") or "chưa có kế hoạch"
            rec["reason_code"] = code
            rec["reason"] = "[CẦN DATA] " + REASON_TEXT[code].format(planned=planned, n=max(shorts or [0]))
            rec["meta"]["notes"] = ["Kế hoạch nguồn: %s." % planned] if entry.get("planned_source") else []
            return rec, None, []
        pts = chosen["points"]
        reasons = _uniq(chosen["partial_reasons"] + auto_reasons(pts, freq, self.src.today))
        last_t = max(t for t, v in pts if v is not None)
        files = chosen["files"]
        notes = []
        if chosen["transform"]:
            notes.append(chosen["transform"])
        notes += chosen["notes"]
        if chosen["class"] == "wigroup":
            notes.append(WIGROUP_NOTE)
        if len(cands) > 1:
            notes.append("Nguồn chọn: %s (ứng viên %d/%d; ưu tiên phủ đủ 3Y, tầng cao, kỳ cuối mới, collected hoặc "
                         "bảng tay trước kho; không ghép hai nguồn; chế độ %s)." % (chosen["id"], pos, len(cands),
                                                                                   policy))
        rec.update({"status": "partial" if reasons else "ok", "tier": chosen["tier"], "partial_reasons": reasons,
                    "tier_spans": chosen["spans"], "points": pts, "as_of": date_of_ms_utc(last_t).isoformat(),
                    "breaks": [{"t": x["t"], "note": neutral(x["note"])} for x in chosen["breaks"]],
                    "source_class": chosen["class"]})
        rec["meta"].update({"source_name": neutral(chosen["source_name"]), "source_ref": neutral(chosen["source_ref"]),
                            "last_updated": max((self.src.mtime_iso(f) for f in files if os.path.isfile(f)),
                                                default=None),
                            "notes": _uniq(neutral(n) for n in notes)})
        return rec, chosen["class"], files
