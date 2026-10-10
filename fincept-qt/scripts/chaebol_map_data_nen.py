"""
chaebol_map_data_nen — nền của lớp dữ liệu sống chaebol_map (tách từ chaebol_map_data.py 27/09/2026).

Giá trị có nguồn V + can_data, bậc/màu, luật định dạng kiểu trang (JS), ngày, đường dẫn kho, cache theo mtime,
cảnh báo, đọc JSON/SQLite chỉ đọc, đọc cache vc_lk theo cột (Cols). Stdlib, không mạng, không ghi tệp.
Tab KHÔNG nhập trực tiếp tệp này — dùng mặt tiền `import chaebol_map_data as D`.
"""
from __future__ import annotations

import bisect
import json
import math
import os
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

__all__ = [
    "T1", "T2", "T3", "EST", "UNV", "CAN", "SHORT", "TIER_COLOR", "GATE_MAX_AGE_H", "SHARE_TOL", "OLD_MONTHS",
    "STALE_MONTHS", "V", "can_data", "iso", "ddmm", "ddmmyyyy", "today", "lui_thang", "_finite", "js_fixed",
    "js_locale", "fmt_vn", "pct_text", "round_half", "to_jsonable", "sys_dir", "bridge", "spec_dir", "skills_dir",
    "vc_dir", "_CACHE", "_WARN", "warn", "warnings", "clear_cache", "_sig", "_memo", "read_json", "_db_path",
    "_ro_uri", "db_query", "vc", "Cols", "_cols_of", "_last", "_sum", "_months_ago",
]


T1, T2, T3, EST, UNV = "FACT-T1", "FACT-T2", "SS-T3", "EST", "UNVERIFIED"
CAN = "[CẦN DATA]"
SHORT = {T1: "T1", T2: "T2", T3: "T3", EST: "E", UNV: "U"}
TIER_COLOR = {T1: "#3d7a4e", T2: "#5b8db8", T3: "#caa75c", EST: "#d4a039", UNV: "#c5392f", None: "#c5392f"}
GATE_MAX_AGE_H = 96          # d4 §7.6: fft_langkinh quá 96 giờ → CỔNG [CẦN DATA]
SHARE_TOL = 0.005            # lệch số cp giữa nguồn > 0,5% → ghi rõ
OLD_MONTHS, STALE_MONTHS = 12, 18


@dataclass
class V:
    """Một giá trị có nguồn. value=None ⇔ [CẦN DATA] (note = lý do)."""
    value: object = None
    text: str | None = None
    tier: str | None = None
    asof: str | None = None
    src: str | None = None
    note: str | None = None
    unit: str | None = None

    @property
    def can(self) -> bool:
        return self.value is None

    def tag(self, with_date: bool = False) -> str:
        """Nhãn bậc thu gọn DESIGN §6.3 ('T2' / 'T2·25/09'); rỗng khi [CẦN DATA]."""
        if self.can or not self.tier:
            return ""
        s = SHORT.get(self.tier, self.tier)
        return f"{s}·{ddmm(self.asof)}" if with_date and self.asof else s

    def show(self) -> str:
        return CAN if self.can else (self.text if self.text is not None else str(self.value))


def can_data(note: str, src: str | None = None, asof: str | None = None, unit: str | None = None) -> V:
    return V(None, CAN, None, asof, src, note, unit)


# ───────────────────────────── ngày + định dạng kiểu trang (JS) ─────────────────────────────

def iso(d) -> str | None:
    if d is None or d == "":
        return None
    if isinstance(d, (date, datetime)):
        return d.isoformat()[:10]
    s = str(d).strip()
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", s)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else s[:10]


def ddmm(d) -> str:
    s = iso(d)
    return f"{s[8:10]}/{s[5:7]}" if s and len(s) >= 10 else ""


def ddmmyyyy(d) -> str:
    s = iso(d)
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if s and len(s) >= 10 else ""


def today() -> date:
    s = os.environ.get("CHB_TODAY")
    return date.fromisoformat(s) if s else date.today()


def lui_thang(ngay: str, n: int) -> str:
    """Cùng ngày n tháng lịch trước; ngày không tồn tại → cuối tháng (như lk_tinh.lui_thang)."""
    d = date.fromisoformat(ngay)
    y, m = divmod(d.year * 12 + d.month - 1 - n, 12)
    m += 1
    cuoi = (date(y + m // 12, m % 12 + 1, 1) - timedelta(days=1)).day
    return date(y, m, min(d.day, cuoi)).isoformat()


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def js_fixed(x, n: int = 0) -> str:
    """Number.prototype.toFixed: làm tròn trên giá trị nhị phân chính xác, nửa → xa 0; giữ '-0.0'."""
    if not _finite(x):
        return CAN
    r = abs(Decimal(x)).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP)
    s = f"{r:.{n}f}"
    return "-" + s if x < 0 else s


def js_locale(x, max_frac: int = 2, min_frac: int = 0) -> str:
    """toLocaleString('en-US', {maximumFractionDigits}) — nhóm nghìn ',', bỏ 0 thừa."""
    if not _finite(x):
        return CAN
    ip, _, fp = js_fixed(abs(x), max_frac).partition(".")
    fp = fp.rstrip("0").ljust(min_frac, "0")
    out = f"{int(ip):,}" + ("." + fp if fp else "")
    return "-" + out if x < 0 and (int(ip) or fp.strip("0")) else out


def fmt_vn(x, n: int = 0, sign: bool = False) -> str:
    """Kiểu Việt: thập phân ',', nghìn '.', âm '−'."""
    if not _finite(x):
        return CAN
    s = js_locale(abs(x), n, n).replace(",", "\0").replace(".", ",").replace("\0", ".")
    return ("−" + s if x < 0 and s.strip("0,.") else "+" + s if sign and x > 0 else s)


def pct_text(x, n: int = 2, sign: bool = True) -> str:
    if not _finite(x):
        return CAN
    s = js_fixed(x, n)
    return ("+" + s if sign and x > 0 else s) + "%"


def round_half(x, n: int):
    return None if not _finite(x) else float(Decimal(x).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP))


def to_jsonable(o):
    if isinstance(o, V):
        return {k: to_jsonable(v) for k, v in asdict(o).items()}
    if isinstance(o, dict):
        return {str(k): to_jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [to_jsonable(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return o


# ───────────────────────────── đường dẫn, cache, cảnh báo ─────────────────────────────

def sys_dir() -> Path:
    return Path(os.environ.get("CHB_SYSTEM_DIR") or Path.home() / "SECOND BRAIN-OBSIDIAN" / "_System")


def bridge() -> Path:
    return sys_dir() / "fincept_bridge"


def spec_dir() -> Path:
    return Path(os.environ.get("CHB_SPEC_DIR") or bridge() / "chaebol_map_spec")


def skills_dir() -> Path:
    return Path(os.environ.get("CHB_SKILLS_DIR") or Path.home() / ".claude" / "skills")


def vc_dir() -> Path:
    return bridge() / "state" / "vc_lk"


_CACHE: dict = {}
_WARN: list = []


def warn(msg: str) -> None:
    if msg not in _WARN:
        _WARN.append(msg)
        print(f"[chaebol_map_data] {msg}", file=sys.stderr)


def warnings() -> list:
    return list(_WARN)


def clear_cache() -> None:
    _CACHE.clear()
    _WARN.clear()


def _sig(p: Path):
    try:
        st = p.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _memo(key, sig, build):
    hit = _CACHE.get(key)
    if hit is not None and hit[0] == sig:
        return hit[1]
    val = build()
    _CACHE[key] = (sig, val)
    return val


def read_json(p, quiet: bool = False):
    p = Path(p)
    sig = _sig(p)
    if sig is None:
        if not quiet:
            warn(f"thiếu tệp {p}")
        return None

    def build():
        try:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError) as e:
            warn(f"không đọc được {p}: {e}")
            return None
    return _memo(("json", str(p)), sig, build)


def _db_path() -> Path:
    return bridge() / "vnstore" / "vn_store.db"


def _ro_uri(p: Path) -> str:
    """URI SQLite chỉ đọc, tự mã hoá %HH (Path.as_uri() trên 3.14 kéo urllib.request → http.client → ssl)."""
    q = "".join(chr(b) if (b < 128 and (chr(b).isalnum() or chr(b) in "/-._~")) else f"%{b:02X}"
                for b in str(p.resolve()).encode("utf-8"))
    return f"file:{q}?mode=ro"


def db_query(sql: str, args: tuple = ()) -> list:
    """SELECT trên vn_store.db (mode=ro). Lỗi/khoá → [] + cảnh báo."""
    p = _db_path()
    sig = _sig(p)
    if sig is None:
        warn(f"thiếu vnstore {p}")
        return []

    def build():
        try:
            con = sqlite3.connect(_ro_uri(p), uri=True, timeout=5)
            try:
                return con.execute(sql, args).fetchall()
            finally:
                con.close()
        except sqlite3.Error as e:
            warn(f"vnstore lỗi ({e}) — dùng số cũ có nhãn ngày nếu có")
            return []
    return _memo(("db", sql, args), sig, build)


# ───────────────────────────── vc_lk (cache Vietcap IQ) ─────────────────────────────

def vc(tk: str, ep: str):
    """(meta, du_lieu) của vc_lk/<tk>/<ep>.json hoặc (None, None)."""
    d = read_json(vc_dir() / tk / f"{ep}.json", quiet=True)
    return (d.get("meta") or {}, d.get("du_lieu")) if isinstance(d, dict) else (None, None)


class Cols:
    """Bảng dạng cột (dang 'cot'): ngày tăng dần, bỏ dòng trùng ngày (giữ dòng đầu), cắt trước `start`."""

    def __init__(self, cols: list, rows: list, start: str | None = None, meta: dict | None = None):
        keep, seen = [], set()
        for r in rows or []:
            d = str(r[0])[:10]
            if (start and d < start) or d in seen:
                continue
            seen.add(d)
            keep.append(r)
        keep.sort(key=lambda r: str(r[0])[:10])
        self.rows, self.meta, self.cut = keep, meta or {}, len(rows or []) - len(keep)
        self.ix = {c: i for i, c in enumerate(cols)}
        self.dates = [str(r[0])[:10] for r in keep]
        self._c: dict = {}
        self.base = ""

    def __len__(self):
        return len(self.rows)

    def col(self, name: str) -> list:
        if name not in self._c:
            i = self.ix.get(name)
            self._c[name] = [None] * len(self.rows) if i is None else [r[i] for r in self.rows]
        return self._c[name]

    def at(self, d) -> int:
        """Chỉ số phiên cuối ≤ d (−1 nếu trước dòng đầu); d=None → phiên cuối."""
        return len(self.dates) - 1 if d is None else bisect.bisect_right(self.dates, iso(d)) - 1


def _cols_of(tk: str, ep: str, start: str | None = None):
    p = vc_dir() / tk / f"{ep}.json"
    sig = _sig(p)
    if sig is None:
        return None

    def build():
        meta, du = vc(tk, ep)
        if not isinstance(du, dict) or "cot" not in du:
            warn(f"vc_lk/{tk}/{ep} sai dạng 'cot'")
            return None
        return Cols(du["cot"], du.get("hang") or [], start, meta)
    return _memo(("cols", str(p), start), sig, build)


def _last(vals, i):
    """(giá trị, chỉ số) khác None gần nhất ≤ i."""
    while i >= 0:
        if vals[i] is not None:
            return vals[i], i
        i -= 1
    return None, -1

def _sum(vals):
    xs = [x for x in vals if _finite(x)]
    return sum(xs) if xs else None

def _months_ago(d: str | None) -> float | None:
    return None if not d else (today() - date.fromisoformat(d)).days / 30.44
