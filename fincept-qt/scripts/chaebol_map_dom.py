#!/usr/bin/env python3
"""
chaebol_map_dom — builder nút JSON cho tab "chaebol_map" (clone Master Plan V21 · Bản Đồ Chaebol & VN30).

Hợp đồng: SECOND BRAIN-OBSIDIAN/_System/fincept_bridge/chaebol_map_spec/DESIGN.md §3 (nút), §4 (state), §6 (nhãn).
Hướng dẫn cho người viết tab: chaebol_map_spec/api_python.md.

Nội dung:
  - h(tag, style, *children, cls=, on=, if_=, var=, inc=, scope=, grp=, count=, sort=, sk=, bind=, href=, a=, key=)
    dựng một nút phần tử; con là chuỗi (nút chữ), số (String(n) kiểu JS), nút, list/tuple (làm phẳng),
    None/True/False (bỏ, như JSX). Chuỗi kề nhau được gộp.
  - finalize(root) → ({"cls": {...}, "root": node}, stats): intern style theo TỪNG tệp (style dict xuất hiện
    ≥ 2 lần hoặc truyền qua cls= → class "k<n>"), bỏ khoá nội bộ, đếm nút / nhãn bậc / [CẦN DATA].
  - Bảng màu C (+ crimson/emerald/bg2 as_intended, DESIGN §0.1).
  - Luật số JS chính xác: to_fixed (Number.prototype.toFixed trên giá trị nhị phân), to_locale (toLocaleString
    'en'/'en-US'/'vi-VN' — Intl làm tròn nửa-xa-0 trên biểu diễn thập phân ngắn nhất), js_string (String(n)),
    js_round (Math.round), js_sum (cộng dồn tuần tự như reduce — KHÔNG dùng sum() ≥3.12 hay math.fsum);
    zfix / cờ zfix= của to_fixed, sign_fixed: lớp live không in '-0.0' (mode v21 giữ đúng JS).
  - Nhãn DESIGN §6 (chỉ phát ở mode live, mode v21 trả None): tier, val, upd_mark, v21_mark, can_data, status_pill.

Stdlib, không mạng, chạy trên Python 3.9+.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from contextlib import contextmanager
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext

__all__ = [
    "C", "F_MONO", "F_NUM", "F_DISPLAY", "F_SERIF", "F_ROOT", "F_BODY", "F_SYS",
    "h", "slot", "frag", "jsx_text", "alpha", "finalize", "dumps", "count_nodes",
    "to_fixed", "to_locale", "js_string", "js_round", "js_sum", "sign_fixed", "zfix",
    "configure", "use_mode", "mode", "is_live", "today",
    "tier", "val", "upd_mark", "v21_mark", "can_data", "status_pill", "norm_tier",
    "TIER_COLORS", "TIER_SHORT", "CAN_DATA",
]


# ── Bảng màu (SRC dòng 49–65) ───────────────────────────────────────────────


class _Palette:
    """C.gold, C['gold']; chỉ đọc; token lạ → AttributeError (bắt lỗi gõ nhầm sớm)."""

    __slots__ = ("_d",)

    def __init__(self, d):
        object.__setattr__(self, "_d", dict(d))

    def __getattr__(self, k):
        try:
            return self._d[k]
        except KeyError:
            raise AttributeError("C.%s không có trong bảng màu" % k) from None

    def __getitem__(self, k):
        return self._d[k]

    def __contains__(self, k):
        return k in self._d

    def __setattr__(self, k, v):
        raise AttributeError("bảng màu C chỉ đọc")

    def items(self):
        return self._d.items()


C = _Palette({
    "bg": "#0a0a0c", "paper": "#13131a", "paperHi": "#1a1a24", "ink": "#e8e6e0", "inkD": "#9a958a",
    "inkM": "#5a564d", "rule": "#26242c", "vermillion": "#c5392f", "ochre": "#d4a039", "forest": "#3d7a4e",
    "ink2": "#5b8db8", "bone": "#e8e6e0", "parch": "#1f1d24", "gold": "#caa75c", "ash": "#5a564d",
    # Không định nghĩa trong SRC → as_intended (DESIGN §0.1, đã duyệt).
    "crimson": "#c5392f", "emerald": "#3d7a4e", "bg2": "#1a1a24",
})

F_MONO = "'IBM Plex Mono', monospace"
F_NUM = "'JetBrains Mono', monospace"
F_DISPLAY = "'Cormorant Garamond', serif"
F_SERIF = "'Source Serif 4', serif"
F_ROOT = "'Source Serif 4', 'Cormorant Garamond', Georgia, serif"
F_BODY = "'Source Serif 4', Georgia, serif"
F_SYS = "-apple-system,Segoe UI,Roboto,Arial,sans-serif"


def alpha(color, aa):
    """`${C.x}AA` của JSX = nối chuỗi → CSS #rrggbbAA (alpha ở CUỐI). Engine/oracle hiểu đúng; đừng đưa vào QColor."""
    return str(color) + str(aa)


# ── Chế độ dựng ─────────────────────────────────────────────────────────────

_STATE = {"mode": "live", "today": None}
MODES = ("live", "v21")


def configure(mode=None, today_=None):
    """Đặt chế độ ('live' | 'v21') và ngày hôm nay (date hoặc 'YYYY-MM-DD') cho các helper nhãn."""
    if mode is not None:
        if mode not in MODES:
            raise ValueError("mode phải là live hoặc v21, nhận %r" % (mode,))
        _STATE["mode"] = mode
    if today_ is not None:
        _STATE["today"] = today_ if isinstance(today_, date) else date.fromisoformat(str(today_))


@contextmanager
def use_mode(m, today_=None):
    old = dict(_STATE)
    configure(m, today_)
    try:
        yield
    finally:
        _STATE.update(old)


def mode():
    return _STATE["mode"]


def is_live():
    return _STATE["mode"] == "live"


def today():
    return _STATE["today"] or date.today()


# ── Luật số của JS ──────────────────────────────────────────────────────────

_MAX_SAFE = 2 ** 53


def _neg(x):
    """x < 0, tính cả −0.0 (Intl in '-0')."""
    return x < 0 or (isinstance(x, float) and x == 0 and math.copysign(1.0, x) < 0)


def _shortest(x):
    """(chuỗi chữ số không có 0 đầu/cuối, số mũ n) sao cho |x| = 0.digits × 10^n (x hữu hạn, ≠ 0)."""
    mant, _, exp = repr(abs(float(x))).partition("e")
    ip, _, fp = mant.partition(".")
    digits = (ip + fp).lstrip("0")
    e10 = (int(exp) if exp else 0) - len(fp)
    stripped = digits.rstrip("0")
    e10 += len(digits) - len(stripped)
    return stripped, e10 + len(stripped)


def js_string(x):
    """String(x) của JS: biểu diễn ngắn nhất; không '.0' cho số nguyên; mũ khi ≥1e21 hoặc <1e-6; −0 → '0'."""
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, int) and abs(x) < _MAX_SAFE:
        return str(x)
    x = float(x)
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if x == 0:
        return "0"
    sign = "-" if x < 0 else ""
    s, n = _shortest(x)
    k = len(s)
    if k <= n <= 21:
        return sign + s + "0" * (n - k)
    if 0 < n <= 21:
        return sign + s[:n] + "." + s[n:]
    if -6 < n <= 0:
        return sign + "0." + "0" * (-n) + s
    e = n - 1
    es = ("+" if e >= 0 else "-") + str(abs(e))
    return sign + (s if k == 1 else s[0] + "." + s[1:]) + "e" + es


def to_fixed(x, digits=0, zfix=False):
    """Number.prototype.toFixed: làm tròn trên giá trị NHỊ PHÂN chính xác, nửa → xa 0; (-0.04).toFixed(1)='-0.0'.
    zfix=True: mode live bỏ dấu của kết quả bằng 0 ('-0.0' → '0.0'); mode v21 vẫn đúng JS (xem zfix())."""
    if not isinstance(digits, int) or not 0 <= digits <= 100:
        raise ValueError("toFixed: digits phải là số nguyên 0..100")
    if isinstance(x, bool):
        x = int(x)
    if isinstance(x, float) and not math.isfinite(x):
        return js_string(x)
    if abs(x) >= 1e21:
        return js_string(x)
    d = Decimal(x) if isinstance(x, int) else Decimal(float(x))
    with localcontext() as ctx:
        ctx.prec = 400
        q = abs(d).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    out = ("-" if x < 0 else "") + format(q, "f")
    return _zfix_live(out) if zfix else out


_LOCALES = {"en": (",", "."), "en-us": (",", "."), "vi": (".", ","), "vi-vn": (".", ",")}


def to_locale(x, locale="en-US", min_frac=None, max_frac=None, grouping=True):
    """Number.prototype.toLocaleString(locale, {minimumFractionDigits, maximumFractionDigits, useGrouping}).

    Mặc định Intl: min 0, max 3 (max = max(3, min) nếu chỉ đặt min; min = min(0, max) nếu chỉ đặt max).
    Làm tròn nửa-xa-0 trên biểu diễn thập phân NGẮN NHẤT (vd 1.005 → '1.01' với max 2, khác toFixed → '1.00').
    Số âm làm tròn về 0 và −0 in '-0' (signDisplay auto). Hỗ trợ 'en', 'en-US', 'vi', 'vi-VN'.
    """
    try:
        gsep, dsep = _LOCALES[str(locale).lower()]
    except KeyError:
        raise ValueError("to_locale: locale chưa hỗ trợ %r" % (locale,)) from None
    if min_frac is None and max_frac is None:
        mn, mx = 0, 3
    elif max_frac is None:
        mn, mx = min_frac, max(3, min_frac)
    elif min_frac is None:
        mn, mx = min(0, max_frac), max_frac
    else:
        mn, mx = min_frac, max_frac
    if not (0 <= mn <= 100 and 0 <= mx <= 100) or mn > mx:
        raise ValueError("to_locale: fraction digits không hợp lệ (min %r, max %r)" % (mn, mx))
    if isinstance(x, bool):
        x = int(x)
    if isinstance(x, float):
        if math.isnan(x):
            return "NaN"
        if math.isinf(x):
            return ("-" if x < 0 else "") + "∞"
    neg = _neg(x)
    d = Decimal(abs(x)) if isinstance(x, int) else Decimal(repr(abs(float(x))))
    with localcontext() as ctx:
        ctx.prec = 400
        q = d.quantize(Decimal(1).scaleb(-mx), rounding=ROUND_HALF_UP)
    ip, _, fp = format(q, "f").partition(".")
    fp = fp.rstrip("0")
    fp += "0" * (mn - len(fp))
    if grouping and len(ip) > 3:
        head = len(ip) % 3 or 3
        ip = ip[:head] + "".join(gsep + ip[i:i + 3] for i in range(head, len(ip), 3))
    return ("-" if neg else "") + ip + (dsep + fp if fp else "")


def js_round(x):
    """Math.round: floor(x + 0.5) không lỗi làm tròn (0.49999999999999994 → 0; -2.5 → -2; -0.4 → -0)."""
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, int):
        return x
    if not math.isfinite(x):
        return x
    r = math.floor(x)
    if x - r >= 0.5:
        r += 1
    if r == 0 and _neg(x):
        return -0.0
    return int(r)


def js_sum(values, start=0):
    """arr.reduce((s, v) => s + v, start) — cộng tuần tự double (không bù sai số như sum() 3.12+ / math.fsum)."""
    s = start
    for v in values:
        s = s + v
    return s


def sign_fixed(v, digits=1, strict=False, zfix=False):
    """`${v>=0?'+':''}${v.toFixed(d)}` (strict=True → điều kiện `v>0`).
    zfix=True: mode live in số làm tròn bằng 0 là '0.0' không dấu (thay '-0.0'/'+0.0'); mode v21 vẫn đúng JS."""
    plus = (v > 0) if strict else (v >= 0)
    out = ("+" if plus else "") + to_fixed(v, digits)
    return _zfix_live(out) if zfix else out


_SIGNED_ZERO = re.compile(r"^[+\-−](0+(?:[.,]0+)?)(?![0-9.,])")


def zfix(s):
    """Số âm-không của lớp live: chuỗi số đã định dạng mà phần số bằng 0 thì bỏ dấu ('-0.0' → '0.0',
    '+0.0M' → '0.0M', '−0,0' → '0,0'; '-0.05' giữ nguyên). CHỈ mode live — mode v21 trả nguyên chuỗi, vì trang gốc
    in '-0.0' đúng luật toFixed (bản so pixel phải giữ). Không phải chuỗi → trả nguyên."""
    return _zfix_live(s)


def _zfix_live(s):
    if not is_live() or not isinstance(s, str):
        return s
    m = _SIGNED_ZERO.match(s)
    return m.group(1) + s[m.end():] if m else s


# ── Nút ─────────────────────────────────────────────────────────────────────

TAGS = frozenset((
    "body div span section header nav main footer h1 h2 h3 h4 p ul ol li table thead tbody tr th td button select "
    "option strong b em i code pre br a small sup sub label "
    "svg g line rect path polyline polygon circle ellipse text tspan defs marker pattern"
).split())

# DESIGN §3: số trần = px trừ các thuộc tính này.
UNITLESS = frozenset(("lineHeight", "fontWeight", "opacity", "zIndex", "flex", "flexGrow", "flexShrink", "order"))
# React cũng coi các thuộc tính sau là không đơn vị → xuất chuỗi để engine không hiểu nhầm là px.
_REACT_UNITLESS_EXTRA = frozenset((
    "animationIterationCount", "aspectRatio", "borderImageOutset", "borderImageSlice", "borderImageWidth",
    "columnCount", "columns", "gridArea", "gridRow", "gridRowEnd", "gridRowSpan", "gridRowStart", "gridColumn",
    "gridColumnEnd", "gridColumnSpan", "gridColumnStart", "lineClamp", "orphans", "scale", "tabSize", "widows",
    "zoom", "fillOpacity", "floodOpacity", "stopOpacity", "strokeDasharray", "strokeDashoffset",
    "strokeMiterlimit", "strokeOpacity", "strokeWidth",
))
_FONT_INHERIT_TAGS = ("button", "select")
_INC_KEY_RE = re.compile(r"^[A-Za-z0-9_.\-/]+$")


def _norm_num(v):
    if isinstance(v, float):
        if not math.isfinite(v):
            return None
        if v.is_integer() and abs(v) < _MAX_SAFE:
            return int(v)
    return v


def norm_style(style):
    """Style React → dict JSON: bỏ None/bool/'' (như React), số nguyên dạng float → int, giữ THỨ TỰ khoá
    (shorthand trước longhand có nghĩa: `border` rồi `borderLeft`)."""
    if not style:
        return {}
    if not isinstance(style, dict):
        raise TypeError("style phải là dict hoặc None, nhận %s" % type(style).__name__)
    out = {}
    for k, v in style.items():
        if not isinstance(k, str):
            raise TypeError("khoá style phải là chuỗi: %r" % (k,))
        if v is None or isinstance(v, bool) or (isinstance(v, str) and v == ""):
            continue
        if isinstance(v, (int, float)):
            v = _norm_num(v)
            if v is None:
                continue
            if k in _REACT_UNITLESS_EXTRA:
                v = js_string(v)
        elif not isinstance(v, str):
            raise TypeError("giá trị style %s phải là số hoặc chuỗi, nhận %s" % (k, type(v).__name__))
        out[k] = v
    return out


def _flatten(children, out):
    for x in children:
        if x is None or isinstance(x, bool):
            continue
        if isinstance(x, (int, float)):
            x = js_string(x)
        if isinstance(x, str):
            if x:
                if out and isinstance(out[-1], str):
                    out[-1] = out[-1] + x
                else:
                    out.append(x)
            continue
        if isinstance(x, dict):
            if "t" not in x:
                raise TypeError("con là dict nhưng không phải nút (thiếu 't'): %r" % (list(x)[:5],))
            out.append(x)
            continue
        if isinstance(x, (bytes, bytearray)):
            raise TypeError("con không được là bytes")
        if hasattr(x, "__iter__"):
            _flatten(x, out)
            continue
        raise TypeError("con không hợp lệ: %s" % type(x).__name__)
    return out


def frag(*children):
    """<>…</>: trả list con đã làm phẳng (h() nhận list như một dãy con)."""
    return _flatten(children, [])


def _str_map(d, what):
    if not isinstance(d, dict) or not d:
        raise TypeError("%s phải là dict khác rỗng" % what)
    return {str(k): v for k, v in d.items()}


def _norm_if(cond):
    out = {}
    for k, v in _str_map(cond, "if_").items():
        if isinstance(v, (list, tuple)):
            out[k] = [str(x) for x in v]
        else:
            out[k] = str(v)
    return out


def _norm_on(on):
    on = _str_map(on, "on")
    if "set" in on:
        return {"set": {str(k): str(v) for k, v in _str_map(on["set"], "on.set").items()}}
    if "sort" in on:
        srt = _str_map(on["sort"], "on.sort")
        for need in ("key", "dir", "col"):
            if need not in srt:
                raise ValueError("on.sort thiếu %r" % need)
        return {"sort": {k: str(srt[k]) for k in ("key", "dir", "col")}}
    raise ValueError("on chỉ hỗ trợ 'set' hoặc 'sort'")


def _style_list(cls):
    if cls is None:
        return []
    items = cls if isinstance(cls, (list, tuple)) else [cls]
    return [s for s in (norm_style(x) for x in items) if s]


def h(tag, style=None, *children, cls=None, on=None, if_=None, var=None, inc=None, scope=None, grp=None,
      count=None, sort=None, sk=None, bind=None, href=None, a=None, key=None):
    """Dựng một nút phần tử (DESIGN §3). `style` = style React (dict, thứ tự khoá có nghĩa).

    cls   : dict style hoặc list dict → luôn thành class của tệp (áp TRƯỚC style).
    on    : {"set": {k: v}} | {"sort": {"key", "dir", "col"}}.
    if_   : {k: v | [v…]} (khoá ghép "a|b" = giá trị hai state nối '|').
    var   : [{"if": {...}, "s": {...}, "cls": {...}?}] — style có điều kiện, ghép sau c/s theo thứ tự.
    inc   : khoá nhánh lười ("codong/VIC"); count : {"grp", "fmt" chứa "{n}"} → con bị thay bằng chữ fmt.
    sort  : {"key", "dir"} trên tbody; sk : {cột: giá trị} trên hàng; bind : khoá state của <select>.
    a     : thuộc tính SVG/HTML (viewBox, colSpan, value…); href : chỉ cho <a>; key : tên gỡ lỗi.
    """
    if tag not in TAGS:
        raise ValueError("thẻ không hỗ trợ: %r" % (tag,))
    node = {"t": tag}
    st = norm_style(style)
    if tag in _FONT_INHERIT_TAGS and "font" not in st:
        inh = {p: "inherit" for p in ("fontFamily", "fontSize", "fontWeight") if p not in st}
        st = {**inh, **st}
    if st:
        node["s"] = st
    classes = _style_list(cls)
    if classes:
        node["_cls"] = classes
    if key is not None:
        node["key"] = str(key)
    if a:
        attrs = {}
        for k, v in _str_map(a, "a").items():
            v = _norm_num(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v
            if v is not None:
                attrs[k] = v
        if attrs:
            node["a"] = attrs
    if on is not None:
        node["on"] = _norm_on(on)
    if if_ is not None:
        node["if"] = _norm_if(if_)
    if var:
        vv = []
        for ent in var:
            if not isinstance(ent, dict) or "if" not in ent:
                raise TypeError("mỗi phần tử var phải là {'if': …, 's': …}")
            e = {"if": _norm_if(ent["if"])}
            s = norm_style(ent.get("s"))
            if s:
                e["s"] = s
            vc = _style_list(ent.get("cls"))
            if vc:
                e["_cls"] = vc
            vv.append(e)
        node["var"] = vv
    if inc is not None:
        if not _INC_KEY_RE.match(str(inc)):
            raise ValueError("khoá inc không hợp lệ: %r" % (inc,))
        node["inc"] = str(inc)
    if scope:
        node["scope"] = [str(x) for x in scope]
    if grp is not None:
        node["grp"] = str(grp)
    if count is not None:
        cnt = _str_map(count, "count")
        if "grp" not in cnt or "{n}" not in str(cnt.get("fmt", "")):
            raise ValueError("count cần {'grp': …, 'fmt': '…{n}…'}")
        node["count"] = {"grp": str(cnt["grp"]), "fmt": str(cnt["fmt"])}
    if sort is not None:
        srt = _str_map(sort, "sort")
        node["sort"] = {"key": str(srt["key"]), "dir": str(srt["dir"])}
    if sk is not None:
        node["sk"] = {k: _norm_num(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v
                      for k, v in _str_map(sk, "sk").items() if v is not None}
    if bind is not None:
        node["bind"] = str(bind)
    if href is not None:
        if tag != "a":
            raise ValueError("href chỉ dùng cho thẻ a")
        node["href"] = str(href)
    kids = _flatten(children, [])
    if count is not None and kids:
        raise ValueError("nút mang count không nhận con (engine thay bằng chữ fmt)")
    if kids:
        node["k"] = kids
    return node


def slot(slot_id):
    """Chỗ nội dung tab trong shell: engine thay bằng root của tab_<state.tab>.json."""
    return {"t": "slot", "id": str(slot_id)}


def jsx_text(s):
    """Luật khoảng trắng chữ JSX của Babel (cleanJSXElementLiteralChild) cho một đoạn chữ nhiều dòng."""
    lines = re.split(r"\r\n|\n|\r", s)
    last_non_empty = 0
    for i, line in enumerate(lines):
        if re.search(r"[^ \t]", line):
            last_non_empty = i
    out = []
    for i, line in enumerate(lines):
        t = line.replace("\t", " ")
        if i != 0:
            t = t.lstrip(" ")
        if i != len(lines) - 1:
            t = t.rstrip(" ")
        if t:
            if i != last_non_empty:
                t += " "
            out.append(t)
    return "".join(out)


# ── Finalize: intern class + thống kê ───────────────────────────────────────

_ATTR_ORDER = ("key", "id", "c", "s", "a", "on", "if", "var", "inc", "scope", "grp", "count", "sort", "sk", "bind",
               "href", "k")
_PRIVATE = ("_cls", "_tier", "_can", "_upd", "_v21")


def _canon(style):
    return json.dumps(style, ensure_ascii=False, separators=(",", ":"))


def _walk(node, fn):
    fn(node)
    for ch in node.get("k", ()):
        if isinstance(ch, dict):
            _walk(ch, fn)


def finalize(root):
    """Cây builder → ({"cls": {...}, "root": node}, stats). Không sửa cây đầu vào.

    Intern: style `s` (của nút và của var) xuất hiện ≥ 2 lần trong tệp → class; style truyền qua cls= luôn là
    class. Tên class "k0", "k1"… theo thứ tự xuất hiện đầu tiên (duyệt trước-sau) → kết quả tất định.
    stats = {"nodes", "elements", "texts", "tiers": {bậc: n}, "can_data", "upd", "v21"}.
    """
    if not isinstance(root, dict) or "t" not in root:
        raise TypeError("finalize: root phải là nút")
    counts, order = {}, []

    def see(style):
        c = _canon(style)
        if c not in counts:
            counts[c] = 0
            order.append((c, style))
        counts[c] += 1

    def collect(n):
        for s in n.get("_cls", ()):
            see(s)
            counts[_canon(s)] += 1          # ép thành class dù chỉ dùng một lần
        if n.get("s"):
            see(n["s"])
        for e in n.get("var", ()):
            for s in e.get("_cls", ()):
                see(s)
                counts[_canon(s)] += 1
            if e.get("s"):
                see(e["s"])

    _walk(root, collect)
    ids, table = {}, {}
    for c, style in order:
        if counts[c] >= 2:
            cid = "k%d" % len(table)
            ids[c] = cid
            table[cid] = style
    stats = {"nodes": 0, "elements": 0, "texts": 0, "tiers": {}, "can_data": 0, "upd": 0, "v21": 0}

    def classes_of(obj):
        cl = [ids[_canon(s)] for s in obj.get("_cls", ())]
        s = obj.get("s")
        inline = None
        if s:
            cid = ids.get(_canon(s))
            if cid is None:
                inline = s
            else:
                cl.append(cid)
        return cl, inline

    def build(n):
        stats["nodes"] += 1
        stats["elements"] += 1
        if "_tier" in n:
            stats["tiers"][n["_tier"]] = stats["tiers"].get(n["_tier"], 0) + 1
        stats["can_data"] += 1 if n.get("_can") else 0
        stats["upd"] += 1 if n.get("_upd") else 0
        stats["v21"] += 1 if n.get("_v21") else 0
        out = {"t": n["t"]}
        cl, inline = classes_of(n)
        for k in _ATTR_ORDER:
            if k == "c":
                if cl:
                    out["c"] = cl[0] if len(cl) == 1 else cl
            elif k == "s":
                if inline:
                    out["s"] = dict(inline)
            elif k == "var":
                if n.get("var"):
                    vv = []
                    for e in n["var"]:
                        ecl, einl = classes_of(e)
                        ne = {"if": e["if"]}
                        if ecl:
                            ne["c"] = ecl[0] if len(ecl) == 1 else ecl
                        if einl:
                            ne["s"] = dict(einl)
                        vv.append(ne)
                    out["var"] = vv
            elif k == "k":
                if n.get("k"):
                    kids = []
                    for ch in n["k"]:
                        if isinstance(ch, str):
                            stats["nodes"] += 1
                            stats["texts"] += 1
                            kids.append(ch)
                        else:
                            kids.append(build(ch))
                    out["k"] = kids
            elif k in n:
                out[k] = n[k]
        for k in n:
            if k not in out and k not in _PRIVATE and k != "t" and k not in _ATTR_ORDER:
                out[k] = n[k]
        return out

    return {"cls": table, "root": build(root)}, stats


def dumps(obj):
    """JSON gọn, UTF-8 thật (ensure_ascii=False), không NaN."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def count_nodes(node):
    """Số nút (phần tử + chữ) của một cây (đã hoặc chưa finalize)."""
    if isinstance(node, str):
        return 1
    return 1 + sum(count_nodes(ch) for ch in node.get("k", ()))


# ── Nhãn bậc & dấu cập nhật (DESIGN §6, chỉ mode live) ─────────────────────

CAN_DATA = "CẦN DATA"
TIER_COLORS = {"FACT-T1": "#3d7a4e", "FACT-T2": "#5b8db8", "SS-T3": "#caa75c", "EST": "#d4a039",
               "UNVERIFIED": "#c5392f"}
TIER_SHORT = {"FACT-T1": "T1", "FACT-T2": "T2", "SS-T3": "T3", "EST": "E", "UNVERIFIED": "U"}
_TIER_ALIASES = {
    "FACT-T1": "FACT-T1", "T1": "FACT-T1", "FACT_T1": "FACT-T1",
    "FACT-T2": "FACT-T2", "T2": "FACT-T2", "FACT_T2": "FACT-T2",
    "SS-T3": "SS-T3", "T3": "SS-T3", "SS_T3": "SS-T3", "SS": "SS-T3",
    "EST": "EST", "E": "EST",
    "UNVERIFIED": "UNVERIFIED", "U": "UNVERIFIED",
    "CẦN DATA": CAN_DATA, "[CẦN DATA]": CAN_DATA, "CAN DATA": CAN_DATA, "CAN_DATA": CAN_DATA,
}
_STATUS_COLORS = {"ĐẠT": C.forest, "BỊ BÁC": C.vermillion, "CHƯA RÕ": C.ochre, "LIVE": C.gold,
                  "HẾT HẠN": "#5a564d", "TIỀN ĐỀ SAI": C.ink2}


def norm_tier(tag):
    """'FACT-T2' | 'T2' | 'SS-T3' | 'EST' | 'E' | 'UNVERIFIED' | 'U' | 'CẦN DATA' → dạng chuẩn; lạ → ValueError."""
    t = _TIER_ALIASES.get(unicodedata.normalize("NFC", str(tag)).strip().upper())
    if t is None:
        raise ValueError("bậc bằng chứng lạ: %r" % (tag,))
    return t


def _short_date(asof):
    if asof is None:
        return None
    this_year = (_STATE.get("today") or date.today()).year
    if isinstance(asof, date):
        return asof.strftime("%d/%m" if asof.year == this_year else "%d/%m/%y")
    s = str(asof).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        if int(m.group(1)) != this_year:
            return "%s/%s/%s" % (m.group(3), m.group(2), m.group(1)[2:])
        return "%s/%s" % (m.group(3), m.group(2))
    m = re.match(r"^(\d{1,2})/(\d{1,2})(?:/\d{2,4})?$", s)
    if m:
        return "%02d/%02d" % (int(m.group(1)), int(m.group(2)))
    return s


_MARK_BASE = {"fontFamily": F_MONO, "fontWeight": 400, "whiteSpace": "nowrap"}


def can_data(detail=None):
    """'[CẦN DATA]' (hoặc '[CẦN DATA — detail]') chữ vermillion đậm, không nhãn bậc. Mode v21 → None.
    Không ngắt dòng giữa '[CẦN' và 'DATA': bản trơn cả span `whiteSpace: nowrap`; bản có lý do chỉ bọc '[CẦN DATA'
    trong span nowrap con — phần ' — lý do]' vẫn xuống dòng được (lý do dài tới ~100 ký tự, nowrap cả câu sẽ tràn ô)."""
    if not is_live():
        return None
    if detail:
        node = h("span", {"color": C.vermillion, "fontWeight": 700},
                 h("span", {"whiteSpace": "nowrap"}, "[" + CAN_DATA), " — %s]" % (detail,))
    else:
        node = h("span", {"color": C.vermillion, "fontWeight": 700, "whiteSpace": "nowrap"}, "[%s]" % CAN_DATA)
    node["_can"] = True
    return node


def tier(tag, asof=None):
    """Nhãn bậc thu gọn (DESIGN §6.3): span Plex Mono 7px, ls .05em, ml 3, màu bậc, 'T2' hoặc 'T2·25/09'."""
    if not is_live():
        return None
    t = norm_tier(tag)
    if t == CAN_DATA:
        return can_data()
    sd = _short_date(asof)
    node = h("span", {**_MARK_BASE, "fontSize": 7, "letterSpacing": ".05em", "marginLeft": 3,
                      "color": TIER_COLORS[t]}, TIER_SHORT[t] + ("·" + sd if sd else ""))
    node["_tier"] = t
    return node


def val(text, tag, asof=None):
    """[text, tier(tag, asof)] — số kèm nhãn bậc (mode v21: chỉ text). tag 'CẦN DATA' → can_data()."""
    if tag is not None and is_live() and norm_tier(tag) == CAN_DATA:
        return [can_data()]
    return [text, tier(tag, asof) if tag is not None else None]


def upd_mark(asof=None):
    """'↻dd/mm' (Plex Mono 8px, ochre, ml 4) sau câu/ô đã viết lại theo dữ kiện mới (DESIGN §6.4)."""
    if not is_live():
        return None
    node = h("span", {**_MARK_BASE, "fontSize": 8, "color": C.ochre, "marginLeft": 4},
             "↻" + (_short_date(asof or today())))
    node["_upd"] = True
    return node


def v21_mark():
    """'V21·12/05' (Plex Mono 8px, #5a564d, ml 4) sau nhận định/stance giữ nguyên chưa chấm lại."""
    if not is_live():
        return None
    node = h("span", {**_MARK_BASE, "fontSize": 8, "color": "#5a564d", "marginLeft": 4}, "V21·12/05")
    node["_v21"] = True
    return node


def status_pill(status):
    """Pill trạng thái claim: ĐẠT forest · BỊ BÁC vermillion · CHƯA RÕ ochre · LIVE gold · HẾT HẠN #5a564d."""
    if not is_live():
        return None
    from chaebol_map_shell import Pill  # nhập trễ: shell nhập dom
    s = unicodedata.normalize("NFC", str(status)).strip().upper()
    s = {"DAT": "ĐẠT", "BI BAC": "BỊ BÁC", "CHUA RO": "CHƯA RÕ", "HET HAN": "HẾT HẠN"}.get(s, s)
    color = _STATUS_COLORS.get(s)
    return Pill(s, color) if color else Pill(s, dim=True)
