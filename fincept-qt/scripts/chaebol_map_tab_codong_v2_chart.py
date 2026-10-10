#!/usr/bin/env python3
"""
chaebol_map_tab_codong_v2_chart: chart tuần từ niêm yết cho tab codong v2 (mode live). Hàm THUẦN.

Hợp đồng: chaebol_map_spec/codong_v2_spec.md §6 (phần P3). Chỉ nhập chaebol_map_dom, primitive cùng chủ
(chaebol_map_tab_codong_v2_svg, re-export ở đây) và stdlib. Không đọc kho, không nhập chaebol_map_data*, không đọc ngày
hệ thống. Cùng đầu vào → cùng đầu ra từng byte, kể cả giữa Python 3.11 và 3.14 (cộng dồn số thực đi qua js_sum).

Đầu vào (RD dựng, §6.2): series = {"tk", "weeks": [{"w","we","o","h","l","c","vol","dvol","fo","fol","v6","v12","v24",
"nn_cum","td_cum","nn_w","td_w","rs","fw","ma4","p10","p90","pre"}], "markers": [{"date","kind","size","label","ref"}],
"ts_start", "fft_note", "fft_warn", "fo_spikes" (số phiên gai %NN vendor đã bỏ)}. None = không có số (ngắt nét). Giá bằng đồng, KL bằng cp, giá trị bằng đồng.

Hình: viewBox 1200×826, 6 pane xếp dọc (giá 340 · KL 70 · %NN 80 · FFT 80 · dòng tiền 80 · RS 60). Mỗi chuỗi là MỘT
path. Nhãn trục là thước đo (không nhãn bậc); số chú thích (đỉnh lịch sử, đóng tuần cuối) trả trong `numbers` để RD
chép sang readout kèm bậc. Không vẽ dải zigzag, dải pha, đường mốc V21. Pane FFT không có nhãn số trục y.
"""
from __future__ import annotations

import bisect
import math
from datetime import date, timedelta

from chaebol_map_dom import C, F_MONO, h, js_sum, to_locale
from chaebol_map_tab_codong_v2_svg import (  # noqa: F401  (re-export cho RD/test: CH.path_d, CH.log_ticks…)
    BODY_MIN, GLYPH_ATTR, LANE_KINDS, MARKER_KINDS, UNNUMBERED, _cat, _fmt, _tn, band_d, bars_d, candle_paths, domain,
    fmt_bn, fmt_k, fmt_pct, fmt_px, fmt_qty, hit, is_num, lin_scale, lin_ticks, log_scale, log_ticks, marker_paths,
    marker_xy, measure, overlap, path_d, r1, text_box)

__all__ = [
    "WIN", "WIN_WEEKS", "MAX_PTS", "MAX_STEP", "VIEW_W", "VIEW_H", "PAD_L", "PAD_R", "PAD_T", "PAD_B", "GAP", "PANES",
    "PANE_Y", "PLOT_W", "BUDGET", "CANDLE_MAX", "MARKER_KINDS", "GLYPHS", "FFT_NOTE", "TS_TEXT",
    "window_plan", "window_rows", "downsample", "log_ticks", "lin_ticks", "path_d", "bars_d", "band_d",
    "candle_paths", "marker_xy", "marker_paths", "build_chart", "measure",
]

# ── Hằng hình học (§6.1) ────────────────────────────────────────────────────

WIN = ("MAX", "5Y", "2Y")
WIN_WEEKS = {"5Y": 260, "2Y": 104}
MAX_PTS = 1000
MAX_STEP = 4
VIEW_W = 1200
PAD_L = 64
PAD_R = 96
PAD_T = 20
PAD_B = 26
GAP = 14
PANES = (("price", 340), ("vol", 70), ("fo", 80), ("fft", 80), ("flow", 80), ("rs", 60))
VIEW_H = PAD_T + PAD_B + GAP * (len(PANES) - 1) + js_sum(hh for _, hh in PANES)        # 826
PLOT_W = VIEW_W - PAD_L - PAD_R
BUDGET = {"MAX": (110_000, 150), "5Y": (70_000, 150), "2Y": (50_000, 150)}       # (byte SVG, nút SVG)

CANDLE_MAX = 260          # MAX vẽ nến khi cả chuỗi ≤ 260 tuần
LOG_RATIO = 3             # thang log khi max/min > 3 (2Y luôn tuyến tính)
PRICE_TICKS_MAX = 8       # nhãn trục giá tối đa
X_LABELS_MAX = 14         # nhãn năm tối đa ở MAX
YEAR_STEPS = (1, 2, 3, 5)
N_NUMBERED = 12
FS = 8.5                  # cỡ chữ mặc định trong SVG (đặt trên g, chữ thừa kế)
PLACE_TRY = tuple((0, d) for d in (0, -10, 10, -20, 20, -30, 30, -40, 40, -50, 50)) + tuple(
    (dx, d) for dx in (-12, 12) for d in (0, -10, 10, -20, 20))   # thứ tự thử chỗ đặt chữ (dx, dy) px
GLYPHS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫"
FFT_NOTE = "FFT là proxy: im lặng không có nghĩa là không phân phối"
TS_TEXT = "trước mốc này: số cp quy đổi U"
VWAPS = (("v6", C.forest, None), ("v12", C.ochre, None), ("v24", C.vermillion, "4 3"))
WHAT = {"ath": "đỉnh lịch sử (giá điều chỉnh)", "now": "đóng tuần cuối"}


def _pane_rects() -> dict:
    out, y = {}, PAD_T
    for name, hh in PANES:
        out[name] = (y, y + hh)
        y += hh + GAP
    return out


PANE_Y = _pane_rects()


# ── Khung & hạ mẫu (§6.3) ───────────────────────────────────────────────────


def window_plan(n_weeks: int) -> dict:
    """§3.2: n ≤ 104 → cả 3 khung là MAX; 104 < n ≤ 260 → 5Y bí danh MAX, 2Y riêng; n > 260 → 3 khung riêng."""
    if n_weeks <= WIN_WEEKS["2Y"]:
        return {"MAX": "MAX", "5Y": "MAX", "2Y": "MAX"}
    if n_weeks <= WIN_WEEKS["5Y"]:
        return {"MAX": "MAX", "5Y": "MAX", "2Y": "2Y"}
    return {"MAX": "MAX", "5Y": "5Y", "2Y": "2Y"}


_LAST_KEYS = ("c", "fo", "fol", "v6", "v12", "v24", "nn_cum", "td_cum", "rs", "fw", "ma4", "p10", "p90")
_SUM_KEYS = ("vol", "dvol", "nn_w", "td_w")


def _merge(grp: list) -> dict:
    out = dict(grp[-1])
    out["w"], out["we"] = grp[0].get("w"), grp[-1].get("we")
    out["o"] = next((r["o"] for r in grp if is_num(r.get("o"))), None)
    hs = [r["h"] for r in grp if is_num(r.get("h"))]
    ls = [r["l"] for r in grp if is_num(r.get("l"))]
    out["h"], out["l"] = (max(hs) if hs else None), (min(ls) if ls else None)
    for k in _LAST_KEYS:
        out[k] = next((r[k] for r in reversed(grp) if is_num(r.get(k))), None)
    for k in _SUM_KEYS:
        vs = [r[k] for r in grp if is_num(r.get(k))]
        out[k] = js_sum(vs) if vs else None
    out["pre"] = any(bool(r.get("pre")) for r in grp)
    return out


def downsample(rows: list, step: int) -> list:
    """Gộp `step` tuần liên tiếp (từ tuần đầu): o đầu; h max; l min; c, fo, fol, v*, nn_cum, td_cum, rs, fw, ma4,
    p10, p90 = giá trị CUỐI khác None; vol, dvol, nn_w, td_w = tổng (None nếu mọi phần tử None); pre = any;
    w = tuần đầu, we = tuần cuối của nhóm. Trả bản sao, không sửa hàng đầu vào."""
    if step <= 1:
        return [dict(r) for r in rows]
    return [_merge(rows[i:i + step]) for i in range(0, len(rows), step)]


def window_rows(weeks: list, win: str, step: int | None = None) -> tuple:
    """(hàng đã cắt + hạ mẫu, step). MAX: cả chuỗi, step = ceil(n / MAX_PTS); 5Y/2Y: 260/104 tuần cuối, step 1.
    `step` truyền vào ghi đè (khi hạ cấp vì ngân sách)."""
    if win not in WIN:
        raise ValueError("khung lạ: %r" % (win,))
    cut = list(weeks) if win == "MAX" else list(weeks[-WIN_WEEKS[win]:])
    if step is None:
        step = max(1, math.ceil(len(cut) / MAX_PTS)) if win == "MAX" else 1
    return downsample(cut, step), step


def _period_starts(rows: list, quarter: bool) -> list:
    """[(chỉ số hàng, chữ)] tại hàng đầu mỗi năm ("2010") hoặc mỗi quý ("Q1/25"); hàng 0 chỉ tính khi rơi vào 7 ngày
    đầu kỳ (tránh nhãn kỳ khuyết)."""
    def key(w):
        return (w[:4], (int(w[5:7]) - 1) // 3) if quarter else w[:4]

    def starts(w):
        return int(w[8:10]) <= 7 and (int(w[5:7]) in (1, 4, 7, 10) if quarter else w[5:7] == "01")
    out = []
    for i, r in enumerate(rows):
        w = str(r.get("w") or "")[:10]
        if len(w) < 10 or (i and key(w) == key(str(rows[i - 1].get("w") or "")[:10])) or (i == 0 and not starts(w)):
            continue
        k = key(w)
        out.append((i, "Q%d/%s" % (k[1] + 1, k[0][2:]) if quarter else k))
    return out


def x_labels(rows: list, win: str) -> list:
    """[(chỉ số hàng, chữ)]: MAX mỗi k năm (k ∈ 1,2,3,5, ≤ 14 nhãn); 5Y mỗi năm; 2Y mỗi quý ("Q1/25").
    Chuỗi ngắn (khung năm cho < 2 nhãn, vd GEL 34 tuần) dùng nhãn quý."""
    out = _period_starts(rows, win == "2Y")
    if win != "2Y" and len(out) < 2:
        return _period_starts(rows, True)
    if win != "MAX":
        return out
    sel = out
    for k in YEAR_STEPS:
        sel = [p for p in out if int(p[1]) % k == 0]
        if len(sel) <= X_LABELS_MAX:
            break
    return sel


def _date_index(rows: list):
    """Ngày ISO → chỉ số hàng chứa ngày đó (hàng phủ từ w tới trước w của hàng sau; hàng cuối tới max(we, w + 6 ngày))
    | None khi ngoài khung."""
    ws = [str(r.get("w") or "")[:10] for r in rows]
    if not ws or len(ws[0]) < 10:
        return lambda d: None
    end = max(str(rows[-1].get("we") or "")[:10], (date.fromisoformat(ws[-1]) + timedelta(days=6)).isoformat())

    def idx(d):
        d = str(d or "")[:10]
        if len(d) < 10 or d < ws[0] or d > end:
            return None
        return bisect.bisect_right(ws, d) - 1
    return idx


def _rank(m: dict) -> tuple:
    s = m.get("size")
    return (0 if is_num(s) else 1, -abs(s) if is_num(s) else 0, str(m.get("date")), MARKER_KINDS.index(m["kind"]),
            str(m.get("label")), str(m.get("ref")))


def _numbered(markers: list, idx) -> list:
    """① tới ⑫: 12 marker trong khung có |size| lớn nhất (trừ dhcd, tt_dot_bien), hoà theo ngày; đánh số theo ngày."""
    cand = [m for m in markers if m.get("kind") in MARKER_KINDS and m["kind"] not in UNNUMBERED
            and idx(m.get("date")) is not None]
    top = sorted(cand, key=_rank)[:N_NUMBERED]
    return sorted(top, key=lambda m: (str(m.get("date")), MARKER_KINDS.index(m["kind"]), str(m.get("label")),
                                      str(m.get("ref"))))


def _circle(x: float, y: float, r: int) -> str:
    """Vòng tròn bán kính r phần mười px quanh (x, y), bằng hai cung tương đối."""
    rr = _fmt(r)
    return ("M" + _cat(_fmt(_tn(x) - r), _fmt(_tn(y))) + "a" + rr + " " + rr + " 0 1 0 " + _fmt(2 * r) + " 0"
            + "a" + rr + " " + rr + " 0 1 0" + _fmt(-2 * r) + " 0")


# ── Bộ vẽ một lần dựng ──────────────────────────────────────────────────────


class _Canvas:
    """Gom phần tử SVG của MỘT lần vẽ (đối tượng cục bộ; không trạng thái toàn cục, không sửa đầu vào)."""

    def __init__(self, series: dict, rows: list, win: str, candles: bool, drop6: bool):
        self.series, self.rows, self.win, self.candles, self.drop6 = series, rows, win, candles, drop6
        n = len(rows)
        self.pitch = PLOT_W / max(1, n)
        self.xs = [PAD_L + (i + 0.5) * self.pitch for i in range(n)]
        self.bw = r1(min(7.0, max(0.6, self.pitch * 0.62)))
        self.idx = _date_index(rows)
        self.grid, self.paths, self.texts, self.boxes = [], [], [], []
        self.numbers, self.legend, self.warnings = [], [], []
        self.scale, self.Yp = "lin", (lambda v: None)
        self.first = str(rows[0].get("w") or "")[:10] or None if rows else None
        self.last = str(rows[-1].get("we") or rows[-1].get("w") or "")[:10] or None if rows else None

    # tiện ích
    def col(self, k: str) -> list:
        return [r.get(k) for r in self.rows]

    def path(self, key: str, d: str, keep: bool = False, **attrs):
        if d or keep:
            a = {"d": d}
            a.update(attrs)
            self.paths.append(h("path", None, a=a, key=key))

    def line(self, key: str, vals: list, Y, stroke: str, width: float = 1.0, dash: str | None = None):
        a = {"fill": "none", "stroke": stroke, "strokeWidth": width}
        if dash:
            a["strokeDasharray"] = dash
        self.path(key, path_d(self.xs, [Y(v) for v in vals]), **a)

    def text(self, x: float, y: float, s: str, key: str, anchor: str | None = None, size: float | None = None,
             fill: str | None = None, weight: int | None = None) -> tuple:
        a = {"x": r1(x), "y": r1(y)}
        for k, v in (("textAnchor", anchor), ("fontSize", size), ("fill", fill), ("fontWeight", weight)):
            if v is not None:
                a[k] = v
        self.texts.append(h("text", None, s, a=a, key=key))
        box = text_box(a["x"], a["y"], s, size or FS, anchor)
        self.boxes.append(box)
        return box

    def place(self, x: float, y: float, s: str, key: str, lo: float, hi: float, extra: tuple = (), **kw) -> None:
        """Đặt chữ tránh chồng (chữ đã đặt + hộp `extra`): thử dời dọc 0, ∓10 … ∓50 rồi dời ngang ±12 px (tung độ kẹp
        trong [lo, hi]); không chỗ trống → chỗ chồng ít diện tích nhất (không bao giờ đè trọn lên chữ đã đặt)."""
        size, anchor = kw.get("size") or FS, kw.get("anchor")
        best, others = None, self.boxes + list(extra)
        for dx, dy in PLACE_TRY:
            xx, yy = x + dx, min(max(y + dy, lo), hi)
            box = text_box(r1(xx), r1(yy), s, size, anchor)
            over = js_sum(overlap(box, b) for b in others)
            if not over:
                self.text(xx, yy, s, key, **kw)
                return
            if best is None or over < best[0]:
                best = (over, xx, yy)
        self.text(best[1], best[2], s, key, **kw)

    def glyph_boxes(self) -> list:
        """Hộp ±5 px quanh glyph marker trong khung (chữ đỉnh lịch sử né cả glyph, không chỉ chữ)."""
        def X(d):
            j = self.idx(d)
            return None if j is None else self.xs[j]
        pts = [marker_xy(m, X, self.week_y, PANE_Y) for m in self.series.get("markers") or []
               if isinstance(m, dict) and m.get("kind") in MARKER_KINDS]
        return [(p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5) for p in pts if p]

    def place_ath(self, x: float, y: float, s: str, half: float, top: float, bot: float) -> None:
        """Chữ đỉnh lịch sử: luôn PHÍA TRÊN giá (râu nến, đóng tuần) dưới bề ngang chữ; trùng chữ hoặc glyph marker thì
        dời ngang ±20/±40 px (vẫn trên giá), hết chỗ mới để place() chọn chỗ chồng ít nhất."""
        kw = {"anchor": "middle", "size": 9, "fill": C.gold, "weight": 700}
        others = self.boxes + self.glyph_boxes()
        for dx in (0, -20, 20, -40, 40):
            xx = min(max(x + dx, PAD_L + half), PAD_L + PLOT_W - half)
            yy = max(self.top_near(xx, half, y) - 4, top + 9)
            if not any(hit(text_box(r1(xx), r1(yy), s, 9, "middle"), b) for b in others):
                self.text(xx, yy, s, "cd2.svg.ann.ath", **kw)
                return
        self.place(x, self.top_near(x, half, y) - 4, s, "cd2.svg.ann.ath", top + 9, bot - 2,
                   extra=tuple(others[len(self.boxes):]), **kw)

    def top_near(self, x: float, half: float, y: float) -> float:
        """Tung độ cao nhất (nhỏ nhất) của giá trong dải ngang [x − half, x + half]: râu nến (h) khi vẽ nến, đóng tuần khi
        vẽ đường; dùng để đặt chữ đỉnh lịch sử phía trên mọi râu nến nằm dưới chữ."""
        ys = [y]
        for xi, r in zip(self.xs, self.rows):
            if abs(xi - x) <= half + self.pitch / 2:
                v = r.get("h") if self.candles and is_num(r.get("h")) else r.get("c")
                yy = self.Yp(v) if is_num(v) else None
                if yy is not None:
                    ys.append(yy)
        return min(ys)

    def title(self, pane: str, s: str) -> None:
        self.text(PAD_L, PANE_Y[pane][0] - 4, s, "cd2.svg.t." + pane, size=8, fill=C.inkD)

    def empty(self, pane: str, what: str) -> None:
        top, bot = PANE_Y[pane]
        self.text(PAD_L + PLOT_W / 2, (top + bot) / 2 + 3, what + ": không có số trong khung", "cd2.svg.empty." + pane,
                  anchor="middle")

    def ylabel(self, pane: str, y: float, s: str, right: bool = False) -> None:
        if right:
            self.text(PAD_L + PLOT_W + 5, y + 3, s, "cd2.svg.y." + pane)
        else:
            self.text(PAD_L - 5, y + 3, s, "cd2.svg.y." + pane, anchor="end")

    def hline(self, y: float) -> None:
        self.grid.append(path_d([PAD_L, PAD_L + PLOT_W], [y, y]))

    def vline(self, x: float) -> None:
        self.grid.append(path_d([x, x], [PAD_T, PANE_Y["rs"][1]]))

    # pane giá
    def price(self) -> None:
        top, bot = PANE_Y["price"]
        keys = (("h", "l") if self.candles else ("c",)) + tuple(k for k, _, _ in VWAPS if self.vwap_on(k))
        vals = [r.get(k) for r in self.rows for k in keys]
        vals = [v for v in vals if is_num(v) and v > 0]
        if not vals:
            self.title("price", "Giá điều chỉnh (đ)")
            self.empty("price", "Giá")
            return
        lo, hi = min(vals), max(vals)
        log = self.win != "2Y" and hi / lo > LOG_RATIO
        self.scale = "log" if log else "lin"
        if log:
            dlo, dhi = lo / 1.04, hi * 1.04
            ticks, self.Yp = log_ticks(dlo, dhi), log_scale(dlo, dhi, top + 12, bot - 28)
        else:
            dlo, dhi = domain(vals, 0.05)
            ticks, self.Yp = lin_ticks(dlo, dhi, 5), lin_scale(dlo, dhi, top + 12, bot - 28)
        ticks = [t for t in ticks if t > 0]
        while len(ticks) > PRICE_TICKS_MAX:
            ticks = ticks[::2]
        for t in ticks:
            self.hline(self.Yp(t))
            self.ylabel("price", self.Yp(t), fmt_k(t))
        self.title("price", self.price_title())
        self.price_series()

    def vwap_on(self, k: str) -> bool:
        return not (self.drop6 and k == "v6")

    def price_title(self) -> str:
        vw = "/".join(k[1:] + "T" for k, _, _ in VWAPS if self.vwap_on(k))
        body = "nến tuần" if self.candles else "đóng tuần"
        scale = "thang log" if self.scale == "log" else "thang tuyến tính"
        return "Giá điều chỉnh (đ): %s + VWAP %s (24T nét đứt), %s" % (body, vw, scale)

    def price_series(self) -> None:
        if self.candles:
            cp = candle_paths(self.rows, self.xs, self.Yp)
            self.path("cd2.svg.wick", cp["wick"], True, fill="none", stroke=C.inkD, strokeWidth=min(1, self.bw))
            self.path("cd2.svg.up", cp["up"], True, fill="none", stroke=C.forest, strokeWidth=self.bw)
            self.path("cd2.svg.down", cp["down"], True, fill="none", stroke=C.vermillion, strokeWidth=self.bw)
        else:
            self.line("cd2.svg.close", self.col("c"), self.Yp, C.ink, 1.2)
        for k, color, dash in VWAPS:
            if self.vwap_on(k):
                self.line("cd2.svg." + k, self.col(k), self.Yp, color, 1.0, dash)

    def annotate(self) -> None:
        """Đỉnh lịch sử (đóng tuần điều chỉnh cao nhất CẢ chuỗi, chỉ vẽ khi nằm trong khung) và đóng tuần cuối."""
        weeks = self.series.get("weeks") or []
        cs = [(r["c"], i) for i, r in enumerate(weeks) if is_num(r.get("c")) and r["c"] > 0]
        if not cs or self.Yp(cs[-1][0]) is None:
            return
        ath = max(cs, key=lambda p: (p[0], -p[1]))
        pts, top, bot = [], PANE_Y["price"][0], PANE_Y["price"][1]
        for kind, (v, i) in (("ath", ath), ("now", cs[-1])):
            j = self.idx(weeks[i].get("w"))
            if j is None:
                continue
            x, y, s = self.xs[j], self.Yp(v), fmt_px(v)
            if kind == "ath":
                half = (text_box(0, 0, s, 9, "middle")[2])
                xx = min(max(x, PAD_L + half), PAD_L + PLOT_W - half)
                self.place_ath(xx, y, s, half, top, bot)
            else:
                self.text(PAD_L + PLOT_W + 6, y + 3, s, "cd2.svg.ann.now", size=9, fill=C.gold, weight=700)
            pts.append(_circle(x, y, 25))
            day = str(weeks[i].get("we") or weeks[i].get("w") or "")[:10]
            self.numbers.append({"id": kind, "text": s, "date": day, "what": WHAT[kind]})
        self.path("cd2.svg.ann.pt", "".join(pts), fill=C.gold)

    # pane phụ
    def vol(self) -> None:
        top, bot = PANE_Y["vol"]
        self.title("vol", "KL khớp + thoả thuận (cp quy đổi)")
        vol, dvol = self.col("vol"), self.col("dvol")
        tot = [(v if is_num(v) else 0) + (d if is_num(d) else 0) for v, d in zip(vol, dvol)]
        mx = max(tot) if tot else 0
        if mx <= 0:
            self.empty("vol", "KL")
            return
        Y = lin_scale(0, mx, top + 8, bot)
        y_vol = [Y(v) if is_num(v) and v > 0 else None for v in vol]
        base = [Y(v if is_num(v) and v > 0 else 0) for v in vol]
        y_tot = [Y(t) if is_num(d) and d > 0 else None for t, d in zip(tot, dvol)]
        self.path("cd2.svg.vol", bars_d(self.xs, bot, y_vol), fill="none", stroke=C.inkM, strokeWidth=self.bw)
        self.path("cd2.svg.dvol", bars_d(self.xs, base, y_tot), fill="none", stroke=C.ink2, strokeWidth=self.bw)
        self.ylabel("vol", top + 8, fmt_qty(mx))

    def fo(self) -> None:
        top, bot = PANE_Y["fo"]
        nsp = self.series.get("fo_spikes") or 0
        self.title("fo", "%NN sở hữu · FOL (nét đứt)" + (" · đã bỏ %d phiên gai vendor" % nsp if nsp else ""))
        fo, fol = self.col("fo"), self.col("fol")
        vals = [v for v in fo + fol if is_num(v)]
        if not vals:
            self.empty("fo", "%NN")
            return
        dhi = max(vals) * 1.08 or 1.0
        ticks, Y = lin_ticks(0, dhi, 3), lin_scale(0, dhi, top + 4, bot)
        for t in ticks:
            self.hline(Y(t))
        for t in (ticks[0], ticks[-1]):
            self.ylabel("fo", Y(t), fmt_pct(t))
        self.line("cd2.svg.fo", fo, Y, C.ink2, 1.2)
        self.line("cd2.svg.fol", fol, Y, C.inkM, 1.0, "4 3")

    def fft(self) -> None:
        top, bot = PANE_Y["fft"]
        note = self.series.get("fft_note") or FFT_NOTE
        self.text(PAD_L, top - 4, "FFT tuần · TB4 · dải P10/P90 · " + note, "cd2.svg.fft.note", size=8, fill=C.inkD)
        warn = self.series.get("fft_warn")
        if warn:
            self.text(PAD_L + PLOT_W, top - 4, warn, "cd2.svg.fft.warn", anchor="end", size=8, fill=C.vermillion)
        cols = [self.col(k) for k in ("fw", "ma4", "p10", "p90")]
        dom = domain([v for c in cols for v in c], 0.05)
        if dom is None:
            self.empty("fft", "FFT")
            return
        Y = lin_scale(dom[0], dom[1], top + 3, bot - 3)
        band = band_d(self.xs, [Y(v) for v in cols[2]], [Y(v) for v in cols[3]])
        self.path("cd2.svg.fft.band", band, fill=C.gold, fillOpacity=0.12)
        self.line("cd2.svg.fft.fw", cols[0], Y, C.inkD, 0.9)
        self.line("cd2.svg.fft.ma4", cols[1], Y, C.gold, 1.2)

    def flow(self) -> None:
        if self.win == "2Y":
            self.flow_weekly()
            return
        top, bot = PANE_Y["flow"]
        self.title("flow", "NN cộng dồn (trục trái, triệu cp) · TD cộng dồn (trục phải, tỷ đồng, từ bản ghi đầu)")
        nn, td = self.col("nn_cum"), self.col("td_cum")
        d1, d2 = domain(nn), domain(td)
        if d1 is None and d2 is None:
            self.empty("flow", "Dòng tiền")
            return
        for vals, dom, key, color, dash, right in ((nn, d1, "nn", C.ink2, None, False),
                                                    (td, d2, "td", C.ochre, "4 3", True)):
            if dom is None:
                continue
            Y, ticks = lin_scale(dom[0], dom[1], top + 4, bot - 4), lin_ticks(dom[0], dom[1], 3)
            if not right and dom[0] < 0 < dom[1]:
                self.hline(Y(0))
            for t in (ticks[0], ticks[-1]):
                self.ylabel("flow", Y(t), fmt_bn(t) if right else fmt_qty(t), right)
            self.line("cd2.svg." + key, vals, Y, color, 1.2, dash)

    def flow_weekly(self) -> None:
        top, bot = PANE_Y["flow"]
        self.title("flow", "NN và TD ròng tuần (tỷ đồng; NN trái, TD phải mỗi tuần)")
        nn, td = self.col("nn_w"), self.col("td_w")
        vals = [v for v in nn + td if is_num(v)]
        if not vals:
            self.empty("flow", "Dòng tiền")
            return
        dom = domain(vals + [0])
        Y, ticks = lin_scale(dom[0], dom[1], top + 4, bot - 4), lin_ticks(dom[0], dom[1], 3)
        self.hline(Y(0))
        for t in (ticks[0], ticks[-1]):
            self.ylabel("flow", Y(t), fmt_bn(t))
        off, bw = self.pitch * 0.2, r1(max(0.6, self.pitch * 0.34))
        for vals_, key, color, sg in ((nn, "nn", C.ink2, -1), (td, "td", C.ochre, 1)):
            xs = [x + sg * off for x in self.xs]
            d = bars_d(xs, Y(0), [Y(v) if is_num(v) else None for v in vals_])
            self.path("cd2.svg." + key, d, fill="none", stroke=color, strokeWidth=bw)

    def rs(self) -> None:
        top, bot = PANE_Y["rs"]
        self.title("rs", "RS so VNINDEX (100 = đầu khung)")
        rs = self.col("rs")
        base = next((v for v in rs if is_num(v) and v > 0), None)
        if base is None:
            self.empty("rs", "RS")
            return
        norm = [v / base * 100 if is_num(v) else None for v in rs]
        dom = domain(norm + [100], 0.08)
        Y = lin_scale(dom[0], dom[1], top + 3, bot - 3)
        self.hline(Y(100))
        self.ylabel("rs", Y(100), "100")
        self.line("cd2.svg.rs", norm, Y, C.ink, 1.0)

    def xaxis(self) -> None:
        for i, s in x_labels(self.rows, self.win):
            self.vline(self.xs[i])
            self.text(self.xs[i], VIEW_H - 9, s, "cd2.svg.x", anchor="middle")

    def ts_line(self) -> None:
        """Ranh giới số cp quy đổi U (ts_start): vạch đứt dọc + chữ, chỉ khi có ít nhất một điểm trước mốc."""
        j = self.idx(self.series.get("ts_start"))
        if not j:
            return
        x = self.xs[j] - self.pitch / 2
        self.path("cd2.svg.ts", path_d([x, x], [PAD_T, PANE_Y["rs"][1]]), fill="none", stroke=C.inkM,
                  strokeWidth=0.8, strokeDasharray="3 3")
        y, w = PANE_Y["vol"][0] + 9, text_box(0, 0, TS_TEXT, 8, None)[2]
        if x - 4 - w >= PAD_L:
            self.text(x - 4, y, TS_TEXT, "cd2.svg.ts.t", anchor="end", size=8, fill=C.inkD)
        else:
            self.text(x + 4, y, TS_TEXT, "cd2.svg.ts.t", size=8, fill=C.inkD)

    def week_y(self, d):
        j = self.idx(d)
        if j is None:
            return None
        r = self.rows[j]
        hi_ = self.Yp(r.get("h") if is_num(r.get("h")) else r.get("c"))
        lo_ = self.Yp(r.get("l") if is_num(r.get("l")) else r.get("c"))
        return None if hi_ is None or lo_ is None else (hi_, lo_)

    def markers(self) -> None:
        ms = [m for m in (self.series.get("markers") or []) if isinstance(m, dict)]
        odd = sorted({str(m.get("kind")) for m in ms if m.get("kind") not in MARKER_KINDS})
        if odd:
            self.warnings.append("marker loại lạ bị bỏ qua: " + ", ".join(odd))

        def X(d):
            j = self.idx(d)
            return None if j is None else self.xs[j]
        mp = marker_paths(ms, X, self.week_y, PANE_Y)
        for k in MARKER_KINDS:
            if k in mp:
                self.path("cd2.svg.m." + k, mp[k], **GLYPH_ATTR[k])
        top, bot = PANE_Y["price"]
        for n, m in enumerate(_numbered(ms, self.idx), 1):
            x, y = marker_xy(m, X, self.week_y, PANE_Y)
            y = y + 13 if m["kind"] == "nb_mua" else y - 7
            self.place(x, y, GLYPHS[n - 1], "cd2.svg.mk.%d" % n, top + 9, bot - 2, anchor="middle", size=9,
                       fill=C.ink)
            self.legend.append({"n": n, "glyph": GLYPHS[n - 1], "date": m.get("date"), "kind": m["kind"],
                                "label": m.get("label"), "ref": m.get("ref")})

    def render(self) -> dict:
        if self.rows:
            for step in (self.price, self.annotate, self.vol, self.fo, self.fft, self.flow, self.rs, self.xaxis,
                         self.ts_line, self.markers):
                step()
        else:
            self.text(VIEW_W / 2, VIEW_H / 2, "không có chuỗi tuần", "cd2.svg.empty", anchor="middle")
        grid = h("path", None, a={"d": "".join(self.grid), "fill": "none", "stroke": C.rule, "strokeWidth": 0.5},
                 key="cd2.svg.grid") if self.grid else None
        g = h("g", None, *self.texts, a={"fontFamily": F_MONO, "fontSize": FS, "fill": C.inkM}, key="cd2.svg.txt")
        return h("svg", {"width": "100%", "height": "auto", "display": "block"}, grid, *self.paths, g,
                 a={"viewBox": "0 0 %d %d" % (VIEW_W, VIEW_H)}, key="cd2.svg")


# ── API chính (§6.4) ────────────────────────────────────────────────────────


def build_chart(series: dict, win: str) -> dict:
    """Chart một khung. Vượt BUDGET → step += 1 (tới MAX_STEP) rồi bỏ VWAP 6T; mỗi lần hạ ghi một dòng `warnings`.
    Khung bí danh theo window_plan dựng y hệt MAX (cùng byte), `alias_of` = "MAX"."""
    if win not in WIN:
        raise ValueError("khung lạ: %r" % (win,))
    weeks = list(series.get("weeks") or [])
    eff = window_plan(len(weeks))[win]
    candles = eff != "MAX" or len(weeks) <= CANDLE_MAX
    rows, step = window_rows(weeks, eff)
    bmax, nmax = BUDGET[eff]
    warnings, drop6 = [], False
    while True:
        cv = _Canvas(series, rows, eff, candles, drop6)
        svg = cv.render()
        nbytes, nodes = measure(svg)
        if nbytes <= bmax:
            break
        over = "SVG %s %s B > %s B" % (eff, to_locale(nbytes), to_locale(bmax))
        if step < MAX_STEP:
            step += 1
            warnings.append(over + " → step %d" % step)
            rows, _ = window_rows(weeks, eff, step)
        elif not drop6:
            drop6 = True
            warnings.append(over + " ở step %d → bỏ VWAP 6T" % step)
        else:
            warnings.append(over + " sau khi hạ cấp hết mức")
            break
    if nodes > nmax:
        warnings.append("SVG %s %d nút > %d" % (eff, nodes, nmax))
    return {"svg": svg, "win": win, "alias_of": "MAX" if eff != win else None, "n_weeks": len(weeks),
            "n_pts": len(rows), "step": step, "first": cv.first, "last": cv.last, "scale": cv.scale,
            "numbers": cv.numbers, "legend": cv.legend, "nodes": nodes, "bytes": nbytes,
            "warnings": warnings + cv.warnings}
