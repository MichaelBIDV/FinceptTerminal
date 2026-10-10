#!/usr/bin/env python3
"""
Fincept Terminal — Lăng kính cấu trúc cổ đông & FFT: định dạng kiểu Việt, thẻ màu, khối (block) dùng chung.
Tách khỏi fincept_langkinh_views.py (≤800 dòng/tệp) để fincept_langkinh_chuthe.py dùng được mà không vòng import.
Stdlib only; Python 3.11 và 3.14. KHÔNG tính lại công thức CONTRACT §2 — chỉ định dạng.
"""
import calendar
import math
import re
from datetime import date

CO = "—"
TRU = "−"


# ───────────────────────────── định dạng kiểu Việt ─────────────────────────────

def so(v, nd=1, dau=False):
    """1.234,5 · âm dùng U+2212 · `dau` thêm '+' cho số dương · thiếu/NaN → '—'."""
    if v is None or isinstance(v, bool):
        return CO
    try:
        x = float(v)
    except (TypeError, ValueError):
        return CO
    if math.isnan(x) or math.isinf(x):
        return CO
    s = "{:,.{}f}".format(abs(x), nd).replace(",", " ").replace(".", ",").replace(" ", ".")
    if float("{:.{}f}".format(abs(x), nd)) == 0:
        return s
    if x < 0:
        return TRU + s
    return "+" + s if dau else s


def pt(v, nd=2, dau=False):
    s = so(v, nd, dau)
    return s if s == CO else s + "%"


def fftp(v):
    return pt(v, 3)


def gia(v):
    return so(v, 0)


def boi(v, nd=2):
    s = so(v, nd)
    return s if s == CO else s + "×"


def pp(v):
    """Percentile / số đếm: 46 · 72,5 · '—'."""
    if v is None or isinstance(v, bool) or not isinstance(v, (int, float)):
        return CO
    return str(int(v)) if float(v).is_integer() else so(v, 1)


def P(v):
    s = pp(v)
    return s if s == CO else "P" + s


def tile_pct(frac, nd=1):
    """Phân số → % có dấu (0,12 → +12,0%)."""
    if not isinstance(frac, (int, float)) or isinstance(frac, bool):
        return CO
    return pt(frac * 100, nd, True)


def ngay(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def dm(s):
    d = ngay(s)
    if d:
        return d.strftime("%d/%m")
    m = re.match(r"(\d\d/\d\d)", str(s or ""))
    return m.group(1) if m else CO


def dmy(s):
    d = ngay(s)
    return d.strftime("%d/%m/%Y") if d else (str(s) if s else CO)


def ky_ngan(ky):
    m = re.match(r"(\d{4})-(\d{2})", str(ky or ""))
    return "T%d/%s" % (int(m.group(2)), m.group(1)[2:]) if m else CO


def ms(d):
    return calendar.timegm(d.timetuple()) * 1000


def so_num(v):
    """Số hữu hạn hoặc None (NaN/Inf từ tệp nguồn coi như thiếu)."""
    ok = isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    return v if ok else None


def g(d, *keys):
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def ds_chu(v):
    """Chuỗi / danh sách chuỗi / None → list[str] (khoá canh_bao của bridge có thể là một trong ba)."""
    if isinstance(v, str):
        return [v] if v.strip() else []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if isinstance(x, (str, int, float)) and str(x).strip()]
    return []


def trung_vi(vals):
    v = sorted(x for x in vals if so_num(x) is not None)
    if not v:
        return None
    k = len(v) // 2
    return v[k] if len(v) % 2 else (v[k - 1] + v[k]) / 2


def so_bo(lk):
    """R15 — ' · SƠ BỘ' khi phiên cuối chưa chốt. Ưu tiên `phien.trang_thai` của bridge; thiếu khoá thì
    heuristic (EST): cap_nhat cùng ngày với phiên cuối và trước 15:05."""
    ph = g(lk, "phien") or {}
    tt = ph.get("trang_thai")
    if isinstance(tt, str) and tt.strip():
        return " · SƠ BỘ" if "SƠ BỘ" in tt.upper() else ""
    ngay_ph = str(ph.get("ngay") or (lk or {}).get("phien_cuoi") or "")[:10]
    cap = str((lk or {}).get("cap_nhat") or "").replace("T", " ")
    if ngay_ph and cap[:10] == ngay_ph and re.match(r"\d\d:\d\d", cap[11:16]) and cap[11:16] < "15:05":
        return " · SƠ BỘ"
    return ""


def tuan_nhan(s):
    """Mốc nhãn chủ thể → 'W37 10/09' (tuần ISO) — rỗng nếu ngày hỏng."""
    d = ngay(s)
    return "W%d %s" % (d.isocalendar()[1], d.strftime("%d/%m")) if d else ""


def ff_hien(ff):
    """% free float hiển thị = đúng mẫu số FFT: 100·ff.cp ÷ ff.issue_share (1 số lẻ). Thiếu issue_share → ff.pct của
    VCI (đã làm tròn, không phải mẫu số FFT) kèm ⚠. → {p, nd, canh (⚠: ff.canh_bao hoặc dự phòng), tip (cả hai số)}."""
    ff = ff if isinstance(ff, dict) else {}
    cp, iss, vci = so_num(ff.get("cp")), so_num(ff.get("issue_share")), so_num(ff.get("pct"))
    if cp is not None and iss is not None and iss > 0:
        p = 100.0 * cp / iss
        return {"p": p, "nd": 1, "canh": bool(ds_chu(ff.get("canh_bao"))),
                "tip": "mẫu số FFT: ff_cp %s ÷ issue_share %s = %s · VCI ff_pct %s (làm tròn)" % (
                    so(cp, 0), so(iss, 0), pt(p, 1), pt(vci, 0))}
    if vci is None:
        return {"p": None, "nd": 0, "canh": False, "tip": ""}
    return {"p": vci, "nd": 0, "canh": True,
            "tip": "thiếu issue_share — hiển thị ff_pct VCI %s (làm tròn), không phải mẫu số FFT (ff_cp %s)" % (
                pt(vci, 0), so(cp, 0))}


def _ngay_cua(v):
    """Ngày trong khoá bridge `tre`/`ca_cho`: chuỗi ngày, hoặc dict có một khoá ngày."""
    if isinstance(v, str):
        return ngay(v)
    if isinstance(v, dict):  # bridge: tre = {phien_cuoi_ma, so_phien_thieu, tuan_cuoi_ma}
        for k in ("phien_cuoi_ma", "tuan_cuoi_ma", "phien", "ngay", "phien_cuoi", "week_end", "tuan"):
            if isinstance(v.get(k), str) and ngay(v[k]):
                return ngay(v[k])
    return None


def lech_thoi(m, lk):
    """Mã dữ liệu dừng (bridge `ma.<sym>.tre`) / chờ điều chỉnh CA (`ma.<sym>.ca_cho`) → (tag, tooltip); ('', '')
    nếu không. Tệp bridge chưa có khoá `tre` → so phiên/tuần của mã với phien_cuoi/tuan.week_end của tệp.
    Mã có tag bị loại khỏi mọi phép đếm/xếp hạng rổ (đếm rổ lấy của bridge)."""
    m = m if isinstance(m, dict) else {}
    tre, ca = m.get("tre"), m.get("ca_cho")
    if "tre" not in m:
        moc = ((g(m, "phien", "ngay"), (lk or {}).get("phien_cuoi") or g(lk, "phien", "ngay")),
               (g(m, "tuan", "week_end"), g(lk, "tuan", "week_end")))
        tre = next((a for a, b in moc if ngay(a) and ngay(b) and ngay(a) < ngay(b)), None)
    tags, tips = [], []
    if tre:
        d = _ngay_cua(tre) or ngay(g(m, "phien", "ngay")) or ngay(g(m, "tuan", "week_end"))
        n = so_num(tre.get("so_phien_thieu")) if isinstance(tre, dict) else None
        tags.append("cũ " + d.strftime("%d/%m") if d else "cũ")
        tips.append("dữ liệu mã dừng%s%s — pct/Ô 8 tuần/giá là của phiên/tuần cũ; loại khỏi đếm và xếp hạng rổ" % (
            " từ " + d.strftime("%d/%m/%Y") if d else "", " (thiếu %s phiên)" % pp(n) if n is not None else ""))
    if ca:  # bridge: ca_cho = bool, ngày CA nằm trong `loi` ("… (CA 2026-09-21 · …)")
        d = _ngay_cua(ca) or ngay((re.search(r"CA (\d{4}-\d\d-\d\d)", str(m.get("loi") or "")) or [None, None])[1])
        tags.append("chờ CA")
        tips.append("chờ điều chỉnh CA%s — lớp giá phiên/tuần hiện tại tạm ẩn (hai cơ sở giá); loại khỏi đếm và xếp "
                    "hạng rổ" % (" (GDKHQ " + d.strftime("%d/%m") + ")" if d else ""))
    return " · ".join(tags), "; ".join(tips)


# ───────────────────────────── màu thẻ ngữ nghĩa ─────────────────────────────

O8_MAU = {("down", "down"): "info", ("down", "flat"): "info", ("down", "up"): "bull",
          ("up", "up"): "warn", ("up", "down"): "bear", ("up", "flat"): "dim"}
VIEN = {"can_cung": "bull", "phan_phoi": "bear", "trung": "dim"}
BUCKET_TEN = {"can_cung": "cạn cung", "phan_phoi": "phân phối", "trung": "giữa"}
BUCKET_NHAN = "Lớp FFT (P3Y)"  # R13 — nhãn hiển thị của `bucket` (khoá JSON giữ nguyên)
O2N_MAU = {"BO CUNG": "bull", "XẢ HÀNG": "bear"}
LOP_TEN = {"bung_no": "Bùng nổ ≥+50% từ đáy 2N", "dac_lai": "Đặc lại — sát đáy 2N, dưới đỉnh 2N ≥5%"}


def mau_dau(v):
    v = so_num(v)
    return "" if not v else ("bull" if v > 0 else "bear")


def mau_bar(p):
    p = so_num(p)
    return "" if p is None else ("bull" if p <= 20 else ("bear" if p >= 75 else "amber"))


def mau_pct(p):
    p = so_num(p)
    return "" if p is None else ("bull" if p <= 20 else ("bear" if p >= 75 else ""))


def mau_o8(tu):
    f, gg = g(tu, "o8_fft"), g(tu, "o8_gia")
    if not f or not gg:
        return ""
    return "dim" if f == "flat" else O8_MAU.get((f, gg), "")


def dm_tag(m):
    """Tag danh mục: '12%' / 'watch' / 'avoid'; thêm '*' khi nguồn danh mục mâu thuẫn (R10, dm.xung_dot)."""
    d = g(m, "dm") or {}
    if so_num(d.get("nav")):
        t = "%s%%" % pp(d["nav"])
    elif d.get("watch"):
        t = "watch"
    elif d.get("avoid"):
        t = "avoid"
    else:
        t = ""
    return t + "*" if t and d.get("xung_dot") else t


def dm_tip(m):
    xd = g(m, "dm", "xung_dot")
    if not xd:
        return ""
    return "Danh mục mâu thuẫn nguồn: %s" % (xd if isinstance(xd, str) else "xem fft_cauhinh.danh_muc.xung_dot")


def chip_mau(m):
    d = g(m, "dm") or {}
    return "amber" if so_num(d.get("nav")) else ("info" if d.get("watch") else "")


# ───────────────────────────── block ─────────────────────────────

def ghi(title, text, pill="", mau="info"):
    return {"type": "note", "pill": pill, "mau": mau, "title": title, "text": text}


def the(k, v, s="", mau="", bac=""):
    return {"k": k, "v": v, "s": s, "mau": mau, "bac": "" if v == CO else bac}  # '—' không mang nhãn bậc


def cot(key, label, align="right", kind="text"):
    return {"key": key, "label": label, "align": align, "kind": kind}


def bang(bid, title, cols, rows, sub="", caption=""):
    return {"type": "table", "id": bid, "title": title, "sub": sub, "caption": caption,
            "cols": cols, "rows": rows, "row_link": any("_link" in r for r in rows)}


def dong(vals, sort=None, mau=None, tag=None, bar=None, vien="", link="", tip=None):
    """Một hàng bảng. `tip` → khoá `_tip` {cột: chữ} (tooltip ô; C++ chưa vẽ thì bỏ qua, vô hại)."""
    r = dict(vals)
    for k, v in (("_sort", sort), ("_mau", mau), ("_tag", tag), ("_bar", bar), ("_tip", tip)):
        v = {a: b for a, b in (v or {}).items() if b not in (None, "")}
        if v:
            r[k] = v
    if vien:
        r["_vien"] = vien
    if link:
        r["_link"] = link
    return r


def phang(block):
    """Bảng chính → hàng phẳng cho CSV; khoá đánh số vì QJsonObject xếp khoá theo chữ cái."""
    cols = block.get("cols") or []
    return [{"%02d %s" % (i + 1, c["label"]): r.get(c["key"], "") for i, c in enumerate(cols)}
            for r in block.get("rows") or []]


def ve(name, axis, style, mau, y):
    return {"name": name, "axis": axis, "style": style, "mau": mau, "y": y}


def cat_chuoi(doc, n=400):
    """Chuỗi fft_chuoi → (x epoch ms, {khoá: y[]}) — tối đa n điểm cuối, bỏ điểm ngày hỏng."""
    t = doc.get("t") or []
    idx = [i for i, s in enumerate(t) if ngay(s)][-n:]
    ys = {}
    for k in ("f", "m", "c", "p10", "p90", "n", "d"):
        arr = doc.get(k)
        if isinstance(arr, list) and len(arr) == len(t):
            ys[k] = [so_num(arr[i]) for i in idx]
    return [ms(ngay(t[i])) for i in idx], [t[i] for i in idx], ys


def phu_ro(tt):
    """B5 — (n mã có FF, N thành viên, thiếu độ phủ?) của Market FFT rổ; n ưu tiên `so_ma` (tuần cuối)."""
    n = so_num(tt.get("so_ma")) if so_num(tt.get("so_ma")) is not None else so_num(tt.get("n_co_du_lieu"))
    tong = so_num(tt.get("n_thanh_vien"))
    thieu = n is not None and bool(tong) and n / tong < 0.8
    return n, tong, thieu


def bac_ro(tt, hang):
    """R1 — bậc số liệu rổ: percentile/số đếm → bac_hang (FACT-T2); mức → bac_muc (EST). Khoá chung `bac` của rổ là
    bậc MỨC nên chỉ làm dự phòng cho mức, không bao giờ đè bậc hạng."""
    tt = tt if isinstance(tt, dict) else {}
    return (tt.get("bac_hang") or "FACT-T2") if hang else (tt.get("bac_muc") or tt.get("bac") or "EST")
