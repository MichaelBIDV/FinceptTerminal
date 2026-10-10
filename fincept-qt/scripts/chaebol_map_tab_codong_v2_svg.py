#!/usr/bin/env python3
"""
chaebol_map_tab_codong_v2_svg: primitive SVG cho chart codong v2 (chaebol_map_tab_codong_v2_chart). Hàm THUẦN.

Hợp đồng: chaebol_map_spec/codong_v2_spec.md §6.3. Chỉ nhập chaebol_map_dom và stdlib. Module chart re-export mọi tên
công khai ở đây (RD và test gọi qua CH.path_d, CH.log_ticks...).

Chống trôi: toạ độ TUYỆT ĐỐI làm tròn về số nguyên phần mười trước, lệnh tương đối là hiệu của các số nguyên đó, nên
cộng dồn lại luôn ra đúng toạ độ đã làm tròn. Số in tối giản: bỏ ".0", bỏ số 0 đầu (".5"), bỏ khoảng trắng trước "-"
và trước "." khi số trước đã có "." (cú pháp path SVG chuẩn; engine ChbSvgPath và Chrome đều đọc được).
"""
from __future__ import annotations

import math
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from chaebol_map_dom import C, dumps, finalize, js_sum, to_locale

__all__ = [
    "MARKER_KINDS", "UNNUMBERED", "LANE_KINDS", "GLYPH_ATTR", "BODY_MIN",
    "log_ticks", "lin_ticks", "path_d", "bars_d", "band_d", "candle_paths", "marker_xy", "marker_paths", "measure",
    "fmt_k", "fmt_px", "fmt_qty", "fmt_bn", "fmt_pct", "text_box", "hit", "overlap", "domain", "lin_scale", "log_scale",
    "is_num", "r1",
]

BODY_MIN = 0.6            # thân nến tối thiểu (px) để nến doji vẫn thấy

MARKER_KINDS = ("nb_mua", "nb_ban", "chuyen_giao", "ph_thu_tien", "ph_khong_thu", "cp_thuong", "dhcd", "tt_dot_bien")
UNNUMBERED = ("dhcd", "tt_dot_bien")
LANE_KINDS = ("ph_thu_tien", "ph_khong_thu", "cp_thuong")

_DIAMOND = "l4 4l-4 4l-4-4z"
# kind → (dx, dy tính bằng phần mười px từ tâm tới điểm đầu, phần đuôi tương đối)
_GLYPH = {
    "nb_mua": (0, -35, "l3.5 6.5h-7z"),                       # ▲
    "nb_ban": (0, 35, "l3.5-6.5h-7z"),                        # ▼
    "chuyen_giao": (0, -40, _DIAMOND),                        # ◇ (nét)
    "ph_thu_tien": (0, -40, _DIAMOND),                        # ◆
    "ph_khong_thu": (0, -40, _DIAMOND),                       # ◆
    "cp_thuong": (-30, 0, "a3 3 0 1 0 6 0a3 3 0 1 0-6 0"),    # ●
    "dhcd": (0, -80, "v8"),                                   # │ (nét, đáy pane giá)
    "tt_dot_bien": (-25, -25, "h5v5h-5z"),                    # ■ (đỉnh pane KL)
}
GLYPH_ATTR = {
    "nb_mua": {"fill": C.forest},
    "nb_ban": {"fill": C.vermillion},
    "chuyen_giao": {"fill": "none", "stroke": C.inkM, "strokeWidth": 1.2},
    "ph_thu_tien": {"fill": C.gold},
    "ph_khong_thu": {"fill": C.inkM},
    "cp_thuong": {"fill": C.ochre},
    "dhcd": {"fill": "none", "stroke": C.ink2, "strokeWidth": 1.2},
    "tt_dot_bien": {"fill": C.ink2},
}


# ── Số học nhỏ ──────────────────────────────────────────────────────────────


def is_num(v) -> bool:
    """Số hữu hạn (int/float, không bool)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _tn(v: float) -> int:
    """Toạ độ → số nguyên phần mười (làm tròn nửa lên, tất định)."""
    return math.floor(v * 10 + 0.5)


def r1(v: float):
    """Toạ độ thuộc tính (x, y của chữ) làm tròn 0.1; số nguyên trả int (JSON không '.0')."""
    t = _tn(v)
    return t // 10 if t % 10 == 0 else t / 10


def _fmt(t: int) -> str:
    """Số nguyên phần mười → chuỗi tối giản: 20→'2', 15→'1.5', 5→'.5', -5→'-.5', 0→'0'."""
    sign = "-" if t < 0 else ""
    q, r = divmod(abs(t), 10)
    if r == 0:
        return sign + str(q)
    return sign + (str(q) if q else "") + "." + str(r)


def _cat(a: str, b: str) -> str:
    """Nối hai số liền nhau: bỏ khoảng trắng khi số sau mở bằng '-', hoặc bằng '.' mà số trước đã có '.'."""
    if b[0] == "-" or (b[0] == "." and "." in a):
        return a + b
    return a + " " + b


# ── Vạch trục ───────────────────────────────────────────────────────────────


def _ticks_from(lo: float, hi: float, mants: tuple) -> list:
    k0, k1 = math.floor(math.log10(lo)) - 1, math.ceil(math.log10(hi)) + 1
    out = set()
    for k in range(k0, k1 + 1):
        for m in mants:
            v = float(Decimal(m).scaleb(k))
            if lo <= v <= hi:
                out.add(v)
    return sorted(out)


def _sig2(v: float, rounding) -> float:
    d = Decimal(repr(v))
    q = Decimal(1).scaleb(d.adjusted() - 1)
    return float((d / q).to_integral_value(rounding=rounding) * q)


def log_ticks(lo: float, hi: float) -> list:
    """Vạch thang log: {1,2,5}×10^k trong [lo, hi], tăng dần; < 3 vạch → {1,1.5,2,3,5,7}×10^k; luôn ≥ 2 vạch (thêm lo
    làm tròn LÊN và hi làm tròn XUỐNG 2 chữ số có nghĩa; rơi ra ngoài [lo, hi] thì dùng chính lo, hi)."""
    if not (is_num(lo) and is_num(hi) and 0 < lo < hi):
        return [v for v in (lo, hi) if is_num(v)]
    t = _ticks_from(lo, hi, ("1", "2", "5"))
    if len(t) < 3:
        t = _ticks_from(lo, hi, ("1", "1.5", "2", "3", "5", "7"))
    if len(t) < 2:
        extra = [v for v in (_sig2(lo, ROUND_CEILING), _sig2(hi, ROUND_FLOOR)) if lo <= v <= hi]
        t = sorted(set(t + extra))
    if len(t) < 2:
        t = sorted(set(t + [lo, hi]))
    return t


def lin_ticks(lo: float, hi: float, n: int = 4) -> list:
    """Vạch tuyến tính: bước 'đẹp' {1, 2, 2.5, 5, 10}×10^k GẦN (hi − lo)/n nhất theo tỷ lệ (hoà → bước nhỏ); các bội
    của bước trong [lo, hi]; luôn ≥ 2 vạch."""
    if not (is_num(lo) and is_num(hi) and lo < hi):
        return [v for v in (lo, hi) if is_num(v)]
    raw = (hi - lo) / max(1, n)
    e = math.floor(math.log10(raw))
    cands = [Decimal(m).scaleb(e) for m in ("1", "2", "2.5", "5", "10")]
    step = min(cands, key=lambda s: abs(math.log(float(s) / raw)))
    k0, k1 = math.ceil(Decimal(repr(lo)) / step), math.floor(Decimal(repr(hi)) / step)
    t = [float(step * k) for k in range(k0, k1 + 1)]
    if len(t) < 2:
        t = sorted(set(t + [lo, hi]))
    return t


# ── Path ────────────────────────────────────────────────────────────────────


def path_d(xs: list, ys: list) -> str:
    """Đường gấp khúc: toạ độ TUYỆT ĐỐI làm tròn về bội 0.1 rồi phát lệnh tương đối = hiệu toạ độ đã làm tròn
    ("M x y" đầu đoạn; sau đó "l dx dy", hoặc "h dx" khi dy = 0). None → kết thúc đoạn; điểm có số kế tiếp mở "M" mới."""
    out, prev = [], None
    for x, y in zip(xs, ys):
        if not (is_num(x) and is_num(y)):
            prev = None
            continue
        X, Y = _tn(x), _tn(y)
        if prev is None:
            out.append("M" + _cat(_fmt(X), _fmt(Y)))
        else:
            dx, dy = X - prev[0], Y - prev[1]
            out.append("h" + _fmt(dx) if dy == 0 else "l" + _cat(_fmt(dx), _fmt(dy)))
        prev = (X, Y)
    return "".join(out)


def bars_d(xs: list, y0, ys: list) -> str:
    """Một path cột dọc (vẽ bằng NÉT, strokeWidth = bề rộng cột): cột đầu "M x y0 v -h", các cột sau nối bằng "m"
    tương đối. Cột kế tiếp đổi chiều (đỉnh xuống đáy rồi đáy lên đỉnh) cho lệnh "m" ngắn hơn; hình vẽ y hệt.
    y0: số (đáy chung) hoặc list đáy từng cột; ys: đỉnh từng cột (None = bỏ cột; cột cao 0 sau làm tròn = bỏ)."""
    out, cur, at_top = [], None, False
    many = isinstance(y0, (list, tuple))
    for i, (x, y) in enumerate(zip(xs, ys)):
        b = y0[i] if many else y0
        if not (is_num(x) and is_num(y) and is_num(b)):
            continue
        X, T, B = _tn(x), _tn(y), _tn(b)
        if T == B:
            continue
        if cur is None:
            out.append("M" + _cat(_fmt(X), _fmt(B)) + "v" + _fmt(T - B))
            cur, at_top = (X, T), True
            continue
        s, e = (T, B) if at_top else (B, T)
        out.append("m" + _cat(_fmt(X - cur[0]), _fmt(s - cur[1])) + "v" + _fmt(e - s))
        cur, at_top = (X, e), not at_top
    return "".join(out)


def band_d(xs: list, lo: list, hi: list) -> str:
    """Dải kín (một path, có thể nhiều đoạn): mỗi đoạn liên tục có cả lo và hi → cạnh hi đi tới, cạnh lo đi lùi, 'z'."""
    out, run = [], []

    def flush():
        if len(run) >= 2:
            pts = [(x, b) for x, _, b in run] + [(x, a) for x, a, _ in reversed(run)]
            out.append(path_d([p[0] for p in pts], [p[1] for p in pts]) + "z")
        run.clear()
    for x, a, b in zip(xs, lo, hi):
        if is_num(x) and is_num(a) and is_num(b):
            run.append((x, a, b))
        else:
            flush()
    flush()
    return "".join(out)


def candle_paths(rows: list, X: list, Y) -> dict:
    """Nến = 3 path {"wick": râu từ h tới l, "up": thân c ≥ o, "down": thân c < o}. X: hoành độ từng hàng;
    Y: giá → tung độ (None khi không vẽ được). Thân thấp hơn BODY_MIN px được nới đều hai phía (doji vẫn thấy)."""
    acc = {k: ([], [], []) for k in ("wick", "up", "down")}
    for r, x in zip(rows, X):
        yh, yl = Y(r.get("h")), Y(r.get("l"))
        if yh is not None and yl is not None:
            for lst, v in zip(acc["wick"], (x, yl, yh)):
                lst.append(v)
        o, c = r.get("o"), r.get("c")
        yo, yc = Y(o), Y(c)
        if yo is None or yc is None:
            continue
        top, bot = min(yo, yc), max(yo, yc)
        if bot - top < BODY_MIN:
            mid = (top + bot) / 2
            top, bot = mid - BODY_MIN / 2, mid + BODY_MIN / 2
        for lst, v in zip(acc["up" if c >= o else "down"], (x, bot, top)):
            lst.append(v)
    return {k: bars_d(v[0], v[1], v[2]) for k, v in acc.items()}


# ── Marker ──────────────────────────────────────────────────────────────────


def marker_xy(m: dict, X, Y, pane: dict):
    """Tâm glyph của một marker, hoặc None khi ngoài khung. X: ngày → hoành độ | None; Y: ngày → (tung độ đỉnh, tung độ
    đáy) của tuần chứa ngày | None; pane: {"price": (top, bot), "vol": (top, bot)}.
    nb_mua dưới đáy tuần · nb_ban trên đỉnh · chuyen_giao trên thêm một nấc · sự kiện vốn ở làn đáy pane giá ·
    dhcd vạch đáy pane giá · tt_dot_bien đỉnh pane KL."""
    x = X(m.get("date"))
    if x is None:
        return None
    kind = m.get("kind")
    top, bot = pane["price"]
    if kind == "dhcd":
        return x, bot
    if kind == "tt_dot_bien":
        return x, pane["vol"][0] + 4
    if kind in LANE_KINDS:
        return x, bot - 16
    yy = Y(m.get("date"))
    if yy is None:
        return x, (top + bot) / 2
    hi_, lo_ = yy
    y = lo_ + 8 if kind == "nb_mua" else hi_ - 16 if kind == "chuyen_giao" else hi_ - 8
    return x, min(max(y, top + 5), bot - 5)


def _glyph(kind: str, x: float, y: float) -> str:
    dx, dy, tail = _GLYPH[kind]
    return "M" + _cat(_fmt(_tn(x) + dx), _fmt(_tn(y) + dy)) + tail


def marker_paths(markers: list, X, Y, pane: dict) -> dict:
    """{kind: d} theo thứ tự MARKER_KINDS (≤ 8 path); glyph 6 tới 8 px vẽ bằng lệnh path; glyph trùng chỗ vẽ một lần.
    Loại lạ bị bỏ qua (người gọi tự cảnh báo)."""
    parts = {}
    for m in markers:
        kind = m.get("kind")
        if kind not in _GLYPH:
            continue
        p = marker_xy(m, X, Y, pane)
        if p is not None:
            parts.setdefault(kind, {})[_glyph(kind, p[0], p[1])] = None
    return {k: "".join(parts[k]) for k in MARKER_KINDS if k in parts}


# ── Định dạng nhãn (en-US) ──────────────────────────────────────────────────


def _z(v: float) -> float:
    return v + 0.0          # −0.0 → 0.0 (Intl in '-0')


def fmt_k(v: float) -> str:
    """Nhãn trục giá: "8.5K", "100K"."""
    return to_locale(_z(v / 1000), "en-US", max_frac=1) + "K"


def fmt_px(v: float) -> str:
    """Số chú thích giá (đỉnh lịch sử, đóng tuần cuối): "224.0K", "1,234.5K"."""
    return to_locale(_z(v / 1000), "en-US", min_frac=1, max_frac=1) + "K"


def fmt_qty(v: float) -> str:
    """Số cổ phiếu: "12.3M", "850K", "120"."""
    a = abs(v)
    if a >= 1e6:
        return to_locale(_z(v / 1e6), "en-US", max_frac=1) + "M"
    if a >= 1e3:
        return to_locale(_z(v / 1e3), "en-US", max_frac=1) + "K"
    return to_locale(_z(v), "en-US", max_frac=0)


def fmt_bn(v: float) -> str:
    """Giá trị đồng → tỷ đồng: "1,250 tỷ", "3.5 tỷ"."""
    return to_locale(_z(v / 1e9), "en-US", max_frac=0 if abs(v) >= 1e10 else 1) + " tỷ"


def fmt_pct(v: float) -> str:
    return to_locale(_z(v), "en-US", max_frac=1) + "%"


# ── Hộp chữ, miền, thang ────────────────────────────────────────────────────


def text_box(x: float, y: float, s: str, size: float, anchor: str | None) -> tuple:
    """Hộp ước (x0, y0, x1, y1) của chữ Plex Mono: 0.6 em/ký tự, ký hiệu từ U+2460 (①…) tính 1 em."""
    w = js_sum(1.0 if ord(ch) >= 0x2460 else 0.6 for ch in s) * size
    x0 = x - w / 2 if anchor == "middle" else x - w if anchor == "end" else x
    return (x0, y - 0.8 * size, x0 + w, y + 0.25 * size)


def hit(a: tuple, b: tuple) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def overlap(a: tuple, b: tuple) -> float:
    """Diện tích giao của hai hộp (x0, y0, x1, y1); không giao → 0."""
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def domain(vals, pad: float = 0.06):
    """(lo, hi) nới `pad` mỗi phía; một giá trị duy nhất → nới 10%; không có số → None."""
    vals = [v for v in vals if is_num(v)]
    if not vals:
        return None
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or abs(hi) * 0.1 or 1.0
    return lo - span * pad, hi + span * pad


def lin_scale(lo: float, hi: float, top: float, bot: float):
    def Y(v):
        return bot - (v - lo) / (hi - lo) * (bot - top) if is_num(v) else None
    return Y


def log_scale(lo: float, hi: float, top: float, bot: float):
    a, b = math.log10(lo), math.log10(hi)

    def Y(v):
        return bot - (math.log10(v) - a) / (b - a) * (bot - top) if is_num(v) and v > 0 else None
    return Y


def measure(svg: dict) -> tuple:
    """(byte, nút) của cây SVG, đo đúng như builder: dumps(finalize(svg)) mã UTF-8; nút = phần tử + chữ."""
    out, st = finalize(svg)
    return len(dumps(out).encode("utf-8")), st["nodes"]
