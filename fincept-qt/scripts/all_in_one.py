#!/usr/bin/env python3
"""all_in_one.py, trang cho tab Fincept "all_in_one" (ALL-IN-ONE · VN30/VN100/VN200/Chaebol MAP), hợp đồng aio/1.

Gom, CHỈ ĐỌC, những gì các tab khác đã có về một mã, xếp thành lưới ô (bento 12 cột). Không tính lại số nào
mà module gốc đã tính; mỗi ô ghi nguồn, bậc bằng chứng và tuổi dữ liệu. Chỉ dùng stdlib, không gọi mạng.

Dùng:
  all_in_one.py bang --ro VN30|VN100|VN200|CHAEBOL   bảng rổ: chip mã + bảng tóm tắt từng mã
  all_in_one.py ma --ma MSN [--ro VN30]  lưới ô của một mã
Luôn in một JSON {"meta","bang","cong","o","csv"} hoặc {"error","error_code"} và thoát 0.

Nguồn (thư mục gốc ~/SECOND BRAIN-OBSIDIAN/_System, đổi bằng AIO_SYS_DIR):
  knowledge_os/hhp_basket_members.json      rổ VN30/VN100 chính thức
  fincept_bridge/vnstore/vn_store.db        tên mã, giá bảng (gia_moi), chỉ mở read-only
  fincept_bridge/data/lk_hoso/<MÃ>.json     Lăng kính: CỔNG, FFT, VWAP, cổ đông, NN, chủ thể, pha, trigger
  fincept_bridge/state/vc_lk/<MÃ>/*.json    Vietcap IQ (chưa đăng nhập): giá lịch sử, hồ sơ, tin, báo cáo
  fincept_bridge/state/vc_iq_dangnhap/<MÃ>/ Vietcap IQ (đã đăng nhập): KQKD + dự phóng, quỹ
  fincept_bridge/state/toanvu_pe/{ma,sau,hoi_dong}/<MÃ>.json   P/E×LS TV, pha giá, Hội đồng
  knowledge_os/hhp_vn100_valuation.json     Định giá HHP (σ P/E, P/B, forward, CapIQ)
  fincept_bridge/data/fft_tin.json          sự kiện chủ thể (tin)
  hsc_research/chuoi.json, bbg_research/chuoi.json   khuyến nghị broker
  ~/SECOND BRAIN-OBSIDIAN/BaoCao_VN30/<MÃ>_DD-MM-YYYY.md, early_detection/edi_index.json,
  fund_holdings/fund_intent_signals.json    DEEP FA
  knowledge_os/msn_reflex/ho_so_*.json      MSN Reflex (chỉ MSN)
"""
from __future__ import annotations

import json
import math
import re
import os
import sqlite3
import sys
import unicodedata
from datetime import datetime, date
from pathlib import Path

VERSION = "1.0"
CAN = "[CẦN DATA]"
SYS_DIR = Path(os.environ.get("AIO_SYS_DIR") or Path.home() / "SECOND BRAIN-OBSIDIAN" / "_System")
VAULT = SYS_DIR.parent
KOS = SYS_DIR / "knowledge_os"
BRIDGE = SYS_DIR / "fincept_bridge"
VNSTORE = BRIDGE / "vnstore" / "vn_store.db"
USAGE = "Dùng: all_in_one.py bang --ro VN30|VN100|VN200|CHAEBOL | all_in_one.py ma --ma MÃ [--ro …]"
T1, T2, T3, EST, UNV = "FACT-T1", "FACT-T2", "SS-T3", "EST", "UNVERIFIED"


class AioError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


# ───────────────────────────── tiện ích ─────────────────────────────

def nfc(s):
    return unicodedata.normalize("NFC", s).strip() if isinstance(s, str) else ""


def num(x):
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, dict):
        x = x.get("v")
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def vn(x, nd=2, sign=False, suffix=""):
    """Số kiểu Việt: '.' nghìn, ',' thập phân, dấu trừ U+2212. None → ''."""
    v = num(x)
    if v is None:
        return ""
    s = f"{abs(v):,.{nd}f}".replace(",", "§").replace(".", ",").replace("§", ".")
    if v < 0 and s.strip("0,.") != "":
        s = "−" + s
    elif sign and v > 0:
        s = "+" + s
    return s + suffix


def ddmm(d, nam=True):
    d = str(d or "")[:10]
    if len(d) < 10:
        return d
    return f"{d[8:10]}/{d[5:7]}/{d[0:4]}" if nam else f"{d[8:10]}/{d[5:7]}"


def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def tuoi_ngay(d):
    """Số ngày từ một mốc ISO (ngày hoặc giờ) tới hôm nay; None khi không đọc được."""
    s = str(d or "")[:10]
    try:
        return (date.today() - date.fromisoformat(s)).days
    except ValueError:
        return None


def trang_thai(d, cu_sau):
    """du | cu | thieu theo tuổi dữ liệu (ngày) so với ngưỡng cu_sau."""
    t = tuoi_ngay(d)
    if t is None:
        return "thieu"
    return "cu" if t > cu_sau else "du"


def mau_sign(v, nguong=0.0):
    v = num(v)
    if v is None:
        return None
    return "xanh" if v > nguong else ("do" if v < -nguong else "xam")


def zone_mau(zone):
    z = (zone or "").upper()
    if "RẺ" in z:
        return "xanh"
    if "ĐẮT" in z:
        return "do"
    return "xam" if z else None


# ── vnblocks helpers ──
def doan(text, mau=None, the=False, tieu_de=None):
    b = {"kieu": "doan", "text": nfc(text)}
    if mau:
        b["mau"] = mau
    if the:
        b["the"] = True
        if tieu_de:
            b["tieu_de"] = nfc(tieu_de)
    return b


def cell(t, mau=None, pill=False, mono=True, dam=False, tip=None):
    c = {"t": t if isinstance(t, str) else ("" if t is None else str(t))}
    if mau:
        c["mau"] = mau
    if pill:
        c["pill"] = True
    if mono:
        c["mono"] = True
    if dam:
        c["dam"] = True
    if tip:
        c["tip"] = nfc(tip)
    return c


def bang(cot, dong, chu_thich="", can_phai=None):
    w = len(cot)
    dong = [(r + [cell("")] * w)[:w] for r in dong]
    b = {"kieu": "bang", "cot": [nfc(c) for c in cot], "dong": dong}
    if chu_thich:
        b["chu_thich"] = nfc(chu_thich)
    if can_phai:
        b["can_phai"] = list(can_phai)
    return b


def tile(nhan, gia_tri, phu="", mau=None, tier="", live=False):
    t = {"nhan": nfc(nhan), "gia_tri": gia_tri or CAN, "phu": nfc(phu), "tier": tier, "live": bool(live)}
    if mau:
        t["mau"] = mau
    return t


def o_so(tiles, cot=4):
    return {"kieu": "o_so", "cot": cot, "o": tiles}


def chips(items):
    return {"kieu": "chips", "chips": [{"tier": t, "text": nfc(x)} for t, x in items if x]}


def canh_bao(tieu_de, muc, mau="vang"):
    muc = [nfc(m) for m in muc if nfc(m)]
    return {"kieu": "canh_bao", "tieu_de": nfc(tieu_de), "muc": muc, "mau": mau} if muc else None


def bieu_do(tieu_de, block, chu_thich, nguon, tier, cao=300):
    return {"kieu": "bieu_do", "tieu_de": nfc(tieu_de), "chu_thich": nfc(chu_thich), "nguon": nfc(nguon),
            "tier": tier, "cao": cao, "block": block}


def o(oid, tieu_de, khoi, cot=6, eyebrow="", tab="", tab_nhan="", tier="", tt="du", ghi_chu=""):
    """Một ô của lưới. tt = du | cu | thieu; khối rỗng bị bỏ."""
    khoi = [b for b in khoi if b]
    return {"id": oid, "tieu_de": nfc(tieu_de), "eyebrow": nfc(eyebrow), "cot": cot, "tab": tab,
            "tab_nhan": nfc(tab_nhan), "tier": tier, "trang_thai": tt if khoi else "thieu",
            "ghi_chu": nfc(ghi_chu), "khoi": khoi}


# ───────────────────────────── nguồn chung ─────────────────────────────

def db():
    if not VNSTORE.exists():
        return None
    try:
        return sqlite3.connect(f"file:{VNSTORE}?mode=ro", uri=True, timeout=2)
    except sqlite3.Error:
        return None


RO = ("VN30", "VN100", "VN200", "CHAEBOL")
RO_NHAN = {"VN30": "VN30", "VN100": "VN100", "VN200": "VN200", "CHAEBOL": "Chaebol MAP"}


def _v21():
    return read_json(BRIDGE / "data" / "chaebol_map" / "v21_const.json") or {}


CHAEBOL_DU_PHONG = ""  # khác rỗng khi không nạp được vũ trụ của Chaebol MAP (cảnh báo hiện ở bảng rổ)
VUTRU_LK: set = set()


def chaebol_universe(vn30, listed):
    """109 mã của tab VIETCAP IQ trong Chaebol MAP (cùng hàm chaebol_map_data_vciq.universe); lỗi nạp → hệ sinh thái."""
    global CHAEBOL_DU_PHONG
    v21 = _v21()
    try:
        import chaebol_map_data_vciq as V  # noqa: PLC0415 (bundle có sẵn, glob chaebol_map*.py)
        out = sorted(V.universe(v21, vn30))
        if not v21 or len(out) < 100:
            CHAEBOL_DU_PHONG = (f"Vũ trụ Chaebol MAP chỉ ra {len(out)} mã (v21_const.json "
                                f"{'thiếu' if not v21 else 'đọc được'}); kiểm tra fincept_bridge/data/chaebol_map/v21_const.json.")
        return out
    except (ImportError, SyntaxError) as exc:
        out = set(vn30)
        for blk in ((read_json(BRIDGE / "data" / "chaebol_ecosystems.json") or {}).get("ecosystems") or {}).values():
            out |= {t for t in (blk.get("tickers") or []) if t in listed}
        CHAEBOL_DU_PHONG = (f"Không nạp được chaebol_map_data_vciq ({type(exc).__name__}): dùng vũ trụ dự phòng "
                            f"VN30 ∪ chaebol_ecosystems.json ({len(out)} mã), KHÁC bộ 109 mã của tab Chaebol MAP.")
        return sorted(out)


def load_universe():
    """{VN30, VN100, VN200, CHAEBOL} + tên/ngành/sàn.

    VN30/VN100: rổ chính thức knowledge_os/hhp_basket_members.json (dự phòng nhóm vnstore).
    VN200: 200 mã đóng băng fincept_bridge/lk_vutru.json, đúng bộ tab Lăng Kính dùng (EST, không có danh sách
    VN200 chính thức trên máy). CHAEBOL: vũ trụ 109 mã tab VIETCAP IQ của Chaebol MAP.
    """
    mem = (read_json(KOS / "hhp_basket_members.json") or {}).get("members") or {}
    vn30, vn100 = list(mem.get("VN30") or []), list(mem.get("VN100") or [])
    ten, nganh, san = {}, {}, {}
    con = db()
    if con is not None:
        try:
            for sym, t, ng, nhom, sn in con.execute("SELECT symbol, ten, nganh, nhom, san FROM ma"):
                ten[sym], nganh[sym], san[sym] = t or "", ng or "", sn or ""
                if not mem:
                    if "VN30" in (nhom or ""):
                        vn30.append(sym)
                    if "VN100" in (nhom or ""):
                        vn100.append(sym)
        except sqlite3.Error:
            pass
        finally:
            con.close()
    if not vn100:
        raise AioError("NO_DATA", f"Không đọc được rổ VN30/VN100 ({KOS / 'hhp_basket_members.json'} và vnstore).")
    global VUTRU_LK
    vt = (read_json(BRIDGE / "lk_vutru.json") or {}).get("ma") or {}
    VUTRU_LK = set(vt)
    for m, x in vt.items():
        ten.setdefault(m, x.get("ten") or "")
        nganh.setdefault(m, x.get("nganh") or "")
    vn200 = sorted(set(vt) | set(vn100)) if vt else sorted(vn100)
    chb = chaebol_universe(sorted(set(vn30)), set(san) | set(vt))
    return {"VN30": sorted(set(vn30)), "VN100": sorted(set(vn100)), "VN200": vn200, "CHAEBOL": chb}, ten, nganh, san


def thanh_vien(tk, U):
    return [r for r in RO if tk in U[r]]


_LK = {}


def lk_hoso(tk):
    if tk not in _LK:
        _LK[tk] = read_json(BRIDGE / "data" / "lk_hoso" / f"{tk}.json")
    return _LK[tk]


NGAY_BANG = ""  # phiên mới nhất của bảng giá vnstore (đặt bởi load_quotes)


def _quote_vc(tk, upcom=False):
    """Phiên cuối có giá của vc_lk price-history (mã HNX/UPCOM không có trên bảng vnstore).

    truoc_gdkhq: giá điều chỉnh của chính phiên cuối lệch giá thô > 2% (UPCOM: lệch giá bình quân, vì Vietcap điều
    chỉnh UPCOM theo giá bình quân) → có sự kiện quyền SAU phiên cuối, giá thô đang hiện là giá trước GDKHQ.
    """
    d = read_json(BRIDGE / "state" / "vc_lk" / tk / "price-history.json")
    du = (d or {}).get("du_lieu") or {}
    if not isinstance(du, dict) or not du.get("hang"):
        return None
    c = du["cot"]
    priced = [dict(zip(c, r)) for r in du["hang"][-6:] if num(dict(zip(c, r)).get("closePrice"))]
    if not priced:
        return None
    row = priced[-1]
    g, t = num(row.get("closePrice")), num(row.get("referencePrice"))
    adj = num(row.get("closePriceAdjusted"))
    base = num(row.get("averagePrice")) if upcom else g
    # điều chỉnh quyền thật luôn làm giá đc THẤP hơn, và cùng một tỷ lệ đc/thô ở các phiên trước (NET 0,9015 suốt
    # 29/09→02/10); một phiên lệch đơn lẻ (MML 05/10, MSR 01/10) là nhiễu averagePrice, không phải GDKHQ
    truoc = None
    if adj and base and g and adj < base * 0.98 and len(priced) >= 2:
        prev = priced[-2]
        r_now, r_prev = adj / g, (num(prev.get("closePriceAdjusted")) or 0) / (num(prev.get("closePrice")) or 1)
        if abs(r_now - r_prev) <= 0.005 * r_now:
            truoc = adj
    return {"ngay": row.get("tradingDate"), "luc": row.get("tradingDate"), "gia": g, "tham_chieu": t,
            "kl": num(row.get("totalMatchVolume")), "gt": num(row.get("totalMatchValue")), "room": None,
            "nguon": "vc_lk price-history (đóng phiên)", "pct": (g / t - 1) * 100 if g and t else None,
            "truoc_gdkhq": truoc}


def load_quotes(mas, san=None):
    """{MÃ: {gia, tham_chieu, pct, kl, luc, nguon, room}}: vnstore.gia_moi (giá bảng) → vc_lk đóng phiên.

    Giá dự phòng cũ hơn phiên mới nhất của bảng → cờ "cu"."""
    global NGAY_BANG
    out = {}
    con = db()
    if con is not None and mas:
        try:
            q = ",".join("?" * len(mas))
            for sym, ngay, luc, gia, tc, kl, gt, room, nguon in con.execute(
                    f"SELECT symbol, ngay, luc, gia, tham_chieu, kl, gt, room, nguon FROM gia_moi WHERE symbol IN ({q})",
                    list(mas)):
                g, t = num(gia), num(tc)
                out[sym] = {"ngay": ngay, "luc": luc, "gia": g, "tham_chieu": t, "kl": num(kl), "gt": num(gt),
                            "room": num(room), "nguon": nguon,
                            "pct": (g / t - 1) * 100 if g and t else None}
        except sqlite3.Error:
            pass
        finally:
            con.close()
    NGAY_BANG = max((x.get("ngay") or "" for x in out.values()), default="")
    for m in mas:
        if m not in out or out[m].get("gia") is None:
            vq = _quote_vc(m, (san or {}).get(m) == "UPCOM")
            if vq:
                vq["cu"] = bool(NGAY_BANG) and str(vq.get("ngay") or "")[:10] < NGAY_BANG[:10]
                out[m] = vq
    return out


def hhp_all():
    return read_json(KOS / "hhp_vn100_valuation.json") or {}


def toanvu(kind, tk):
    return read_json(BRIDGE / "state" / "toanvu_pe" / kind / f"{tk}.json")


def read_cong(h=None):
    """Dòng CỔNG, chỉ đọc: lk_hoso.cong → fft_langkinh.cong."""
    c = (h or {}).get("cong") or {}
    if not c.get("dong"):
        c = (read_json(BRIDGE / "data" / "fft_langkinh.json") or {}).get("cong") or {}
    dong = nfc(c.get("dong")) or "CỔNG: [CẦN DATA] chưa đọc được dòng cổng của lăng kính v1.7"
    phu = "Đọc nguyên văn từ lăng kính v1.7"
    if c.get("as_of"):
        phu += f" · bản {c['as_of']}"
    phu += (". ALL-IN-ONE chỉ gom số của các tab khác; CỔNG đang DỪNG thì không có kết luận per-mã, "
            "không phát nhãn mua/bán.") if ("DỪNG" in dong.upper() or "CẦN DATA" in dong) else \
        ". ALL-IN-ONE chỉ gom số của các tab khác, không phát nhãn mua/bán."
    return {"kieu": "cong", "dong": dong, "tier": EST, "phu": phu}


def fmt_gia(v_dong):
    """Giá đồng → '72.000'."""
    return vn(v_dong, 0)


# ───────────────────────────── bảng rổ ─────────────────────────────

def chip(m, ten, quotes):
    q = quotes.get(m) or {}
    p = q.get("pct")
    mau = "" if p is None else ("xanh" if p > 0.05 else ("do" if p < -0.05 else "vang"))
    live = (q.get("nguon") or "").startswith("vci")
    return {"ma": m, "ten": nfc(ten.get(m)), "gia": fmt_gia(q.get("gia")), "pct": vn(p, 2, True, "%"), "mau": mau,
            "live": live, "ngay": ddmm(q.get("ngay")), "nguon": "" if live else "đóng phiên Vietcap",
            "truoc_gdkhq": fmt_gia(q.get("truoc_gdkhq")) if q.get("truoc_gdkhq") else ""}


def nhom_chaebol(U):
    """[(nhãn, [mã])] của vũ trụ Chaebol MAP: 5 nhóm V21 (CHAEBOL_GROUPS) → 17 hệ sinh thái (chaebol_ecosystems.json,
    nhóm chia tay EST) → phần còn lại. Mỗi mã chỉ hiện ở nhóm ĐẦU TIÊN chứa nó."""
    uni, seen, out = set(U["CHAEBOL"]), set(), []

    def add(nhan, tks):
        tks = [t for t in tks if t in uni and t not in seen]
        if tks:
            seen.update(tks)
            out.append((nhan, sorted(tks)))
    for g in _v21().get("CHAEBOL_GROUPS") or []:
        add(nfc(g.get("name")) or g.get("id", ""), re.findall(r"[A-Z][A-Z0-9]{2,3}", str(g.get("tickers") or "")))
    eco = (read_json(BRIDGE / "data" / "chaebol_ecosystems.json") or {}).get("ecosystems") or {}
    for g, blk in eco.items():
        if g.lower().startswith("watchlist"):
            continue  # bảng giá theo dõi, không phải hệ sinh thái
        mem = blk.get("members") or {}
        tks = list(blk.get("tickers") or (mem.keys() if isinstance(mem, dict) else
                                          [x.get("ticker") for x in mem if isinstance(x, dict)]))
        nhan = "".join(" " + ch if i and ch.isupper() and g[i - 1].islower() else ch for i, ch in enumerate(g))
        add(nhan.upper(), [t for t in tks if t])
    add("KHÁC TRONG VŨ TRỤ CHAEBOL MAP", sorted(uni))
    return out


def nhom_ro(ro, U):
    """[(nhãn, [mã])] của bảng chip một rổ."""
    vn30, vn100 = U["VN30"], U["VN100"]
    if ro == "CHAEBOL":
        return nhom_chaebol(U)
    g = [("VN30 HIỆN HÀNH", vn30), ("NGOÀI VN30 · VN100", [m for m in vn100 if m not in vn30])]
    if ro == "VN200":
        g.append(("VN101–200 (LĂNG KÍNH)", [m for m in U["VN200"] if m not in vn100]))
    return g


def bang_chip(ro, U, ten, quotes):
    return {"nhom": [{"nhan": f"{n} ({len(t)})", "ma": [chip(m, ten, quotes) for m in t]} for n, t in nhom_ro(ro, U)]}


def board_rows(mas, ten, quotes, nhom_cua):
    hall = (hhp_all().get("by_ticker") or {})
    rows = []
    for m in mas:
        q = quotes.get(m) or {}
        h = lk_hoso(m) or {}
        tv = (toanvu("ma", m) or {}).get("hien_tai") or {}
        hv = hall.get(m) or {}
        metric = "pb" if ((hv.get("pb") or {}).get("reliable") and not (hv.get("pe") or {}).get("reliable")) else "pe"
        hs = hv.get(metric) or {}
        fft = h.get("fft") or {}
        fw = hv.get("forward") or {}
        src = fw.get("src")
        tp_src = ("Vietcap" if (src == "vietcap" or (isinstance(src, dict) and "vietcap" in src.values())) else
                  ("S&P CapIQ" if src == "spg" else (str(src) if src else "")))
        tp = num(fw.get("tp"))
        tp_ngay = None
        if tp_src == "Vietcap":
            det = (read_json(BRIDGE / "state" / "vc_lk" / m / "details.json") or {}).get("du_lieu") or {}
            try:
                tp_ngay = datetime.strptime(det.get("ratingAsOf") or "", "%d-%b-%y").strftime("%Y-%m-%d")
            except ValueError:
                tp_ngay = None
        elif tp_src == "S&P CapIQ":
            tp_ngay = ((fw.get("capiq") or hv.get("capiq") or {}).get("tp_date") or None)
        gia = q.get("gia")
        rows.append({
            "ma": m, "ten": nfc(ten.get(m)), "nhom": nhom_cua.get(m, ""), "gia": gia, "pct": q.get("pct"),
            "gia_live": (q.get("nguon") or "").startswith("vci"),
            "pe": num(tv.get("pe")), "tv_pct": num(tv.get("pct")), "tv_nguong": num(tv.get("nguong")),
            "tv_kh": tv.get("kich_hoat"), "erp": num(tv.get("erp")),
            "hhp_m": "P/B" if metric == "pb" else "P/E", "hhp_s": num(hs.get("sigma")) if hs else None,
            "hhp_z": hs.get("zone") or "",
            "fft3": num(fft.get("pct3y")), "fftall": num(fft.get("pall")),
            "chu_the": nfc(((h.get("chuthe") or {}).get("nhan") or {}).get("v")),
            "pha": nfc((h.get("pha") or {}).get("nhan")),
            "nn": num((h.get("ngoai") or {}).get("hien")),
            "tp": tp, "tp_src": tp_src, "tp_ngay": tp_ngay, "tp_tuoi": tuoi_ngay(tp_ngay),
            "upside": (tp / gia - 1) * 100 if tp and gia else None, "truoc_gdkhq": q.get("truoc_gdkhq"),
        })
    return rows


def tiles_solenh(ro, U, ten):
    """Bảng xếp hạng gom / xả theo sổ lệnh (all_in_one_solenh) đặt đầu trang rổ VN30/VN100/VN200; lỗi → một ô thiếu."""
    try:
        import all_in_one_solenh as SL  # noqa: PLC0415
        return SL.tiles_bang(ro, U, ten)
    except Exception as exc:  # noqa: BLE001, bảng xếp hạng hỏng không được làm mất trang rổ
        return [o("sl_xep_hang", f"Bảng xếp hạng gom / xả theo sổ lệnh · {ro}", [], 12, "Sổ lệnh", "langkinh",
                  "Lăng kính FFT", ghi_chu=f"{CAN} engine sổ lệnh lỗi: {type(exc).__name__}: {exc}")]


def run_board(ro):
    U, ten, _, san = load_universe()
    mas = U[ro]
    groups = nhom_ro(ro, U)
    nhom_cua = {m: n for n, t in groups for m in t}
    quotes = load_quotes(sorted(set(mas) | {m for _, t in groups for m in t}), san)
    rows = board_rows(mas, ten, quotes, nhom_cua)
    h0 = lk_hoso(U["VN30"][0]) if U["VN30"] else None
    co_nhom = ro in ("VN200", "CHAEBOL")

    live_rows = [r for r in rows if r["gia_live"]]
    up = sum(1 for r in live_rows if (r["pct"] or 0) > 0.05)
    dn = sum(1 for r in live_rows if (r["pct"] or 0) < -0.05)
    kh = [r["ma"] for r in rows if r["tv_kh"] is True]
    re_ = [r["ma"] for r in rows if (r["hhp_s"] is not None and r["hhp_s"] <= -1)]
    can_cung = [r["ma"] for r in rows if r["fft3"] is not None and r["fft3"] <= 20]
    can = [r["ma"] for r in rows if r["chu_the"] == "cần"]
    khong_gia_bang = [r["ma"] for r in rows if r["gia"] is not None and not r["gia_live"]]
    truoc_gdkhq = [r["ma"] for r in rows if r["truoc_gdkhq"]]
    tp_cu = [r["ma"] for r in rows if r["tp"] and (r["tp_tuoi"] or 0) > 180]
    thieu_lk = [r["ma"] for r in rows if not lk_hoso(r["ma"])]
    luc = max((q.get("luc") or "" for q in quotes.values() if (q.get("nguon") or "").startswith("vci")), default="")

    def ds(x):
        return ", ".join(x[:12]) + ("…" if len(x) > 12 else "")
    tiles = [
        tile(f"Phiên {ddmm(luc, False)}", f"{up} tăng · {dn} giảm",
             f"{len(live_rows) - up - dn} đứng giá · trên bảng vnstore {len(live_rows)}/{len(rows)} mã", None, T2, live=True),
        tile("Luật P/E × LS (Toàn Vũ)", f"{len(kh)} mã kích hoạt", ds(kh), "vang" if kh else None, EST),
        tile("HHP ≤ −1σ (rẻ so với chính mã)", f"{len(re_)} mã", ds(re_), "xanh" if re_ else None, EST),
        tile("FFT ≤ P20 3Y (cạn cung, proxy)", f"{len(can_cung)} mã", ds(can_cung), None, EST),
        tile("Chủ thể 'cần' thị trường", f"{len(can)} mã", ds(can), None, T3),
    ]
    dong = []
    for r in rows:
        d = [cell(r["ma"], "vang", mono=True, dam=True, tip=r["ten"])]
        if co_nhom:
            d.append(cell(cut_s(r["nhom"], 26), mono=False))
        d += [
            cell(fmt_gia(r["gia"]), None if r["gia_live"] else "xam", tip=None if r["gia_live"] else "đóng phiên Vietcap, không phải giá bảng"),
            cell(vn(r["pct"], 2, True, "%"), mau_sign(r["pct"], 0.05) if r["gia_live"] else "xam"),
            cell(vn(r["pe"], 1, suffix="x")),
            cell(f"P{vn(r['tv_pct'], 0)} / P{vn(r['tv_nguong'], 0)}" if r["tv_pct"] is not None else ""),
            cell("KÍCH HOẠT" if r["tv_kh"] else ("không" if r["tv_kh"] is False else ""), "vang" if r["tv_kh"] else None, pill=bool(r["tv_kh"])),
            cell(vn(r["erp"], 2, True), mau_sign(r["erp"], 0.5)),
            cell(f"{r['hhp_m']} {vn(r['hhp_s'], 2, True, 'σ')}" if r["hhp_s"] is not None else "", zone_mau(r["hhp_z"]), tip=r["hhp_z"]),
            cell(f"P{vn(r['fft3'], 0)} · P{vn(r['fftall'], 0)}" if r["fft3"] is not None else ""),
            cell(r["chu_the"]), cell(r["pha"], mono=False),
            cell(vn(r["nn"], 1, suffix="%")),
            cell(vn(r["upside"], 1, True, "%"),
                 "xam" if (r["tp_tuoi"] or 0) > 180 else mau_sign(r["upside"], 5),
                 tip=(f"TP {vn(r['tp'], 0)} · nguồn {r['tp_src'] or 'không rõ'}"
                      + (f" · ngày TP {ddmm(r['tp_ngay'])} ({r['tp_tuoi']} ngày)" if r["tp_ngay"] else " · không rõ ngày TP"))
                 if r["tp"] else None),
        ]
        dong.append(d)
    cot = ["Mã"] + (["Nhóm"] if co_nhom else []) + ["Giá", "%", "P/E", "P/E pct / ngưỡng TV", "Luật TV", "ERP", "HHP σ",
                                                   "FFT 3Y · toàn dải", "Chủ thể", "Pha (tác giả)", "NN sở hữu",
                                                   "Upside TP (Vietcap/CapIQ)"]
    off = 2 if co_nhom else 1
    bang_ro = bang(cot, dong,
                   "Bấm chip mã phía trên để mở lưới ô của mã. Giá: vnstore (bảng Vietcap) FACT-T2; chữ xám = đóng phiên "
                   "Vietcap (mã HNX/UPCOM không có trên bảng) · P/E, luật TV, ERP: P/E×LS TV (EST, chỉ mã có trong tệp "
                   "Bloomberg HOSE) · HHP σ: Định giá HHP, thước đo theo ngành (EST) · FFT: Lăng kính, tuần đã đóng (proxy, "
                   "EST) · chủ thể/pha: nhãn tĩnh có tác giả (SS-T3) · upside: TP forward của HHP ÷ giá; nguồn TP (Vietcap "
                   "hoặc S&P CapIQ) ở tooltip và cột CSV tp_nguon.",
                   can_phai=list(range(off, len(cot))))
    n_eco = sum(1 for n, _ in groups if not n.startswith("NHÓM") and not n.startswith("⛔") and not n.startswith("KHÁC"))
    nguon_ro = {"VN30": "rổ VN30 chính thức (hhp_basket_members)", "VN100": "rổ VN100 chính thức (hhp_basket_members)",
                "VN200": f"{len(U['VN200'])} mã = lk_vutru.json (bộ đóng băng của Lăng Kính, EST: không có danh sách VN200 "
                         "chính thức) ∪ VN100",
                "CHAEBOL": (f"{len(U['CHAEBOL'])} mã tab VIETCAP IQ của Chaebol MAP (VN30 ∪ 48 mã cổ đông ∪ mã nêu trong "
                            f"V21); nhóm: các nhóm V21 rồi {n_eco} hệ sinh thái có mã trong chaebol_ecosystems.json (EST)")
                if not CHAEBOL_DU_PHONG else f"{len(U['CHAEBOL'])} mã dự phòng (VN30 ∪ chaebol_ecosystems.json)"}[ro]
    canh = []
    if khong_gia_bang:
        canh.append(f"{len(khong_gia_bang)} mã không có trên bảng giá vnstore, dùng giá đóng phiên Vietcap: {ds(khong_gia_bang)}")
    if thieu_lk:
        canh.append(f"{len(thieu_lk)} mã chưa có hồ sơ Lăng kính (FFT, chủ thể, pha, NN trống): {ds(thieu_lk)}")
    if truoc_gdkhq:
        canh.append(f"{len(truoc_gdkhq)} mã có phiên Vietcap cuối nằm trước ngày GDKHQ (giá thô cao hơn tham chiếu sắp tới): "
                    f"{ds(truoc_gdkhq)}")
    if tp_cu:
        canh.append(f"{len(tp_cu)} mã có TP quá 180 ngày (cột upside tô xám): {ds(tp_cu)}")
    if CHAEBOL_DU_PHONG and ro == "CHAEBOL":
        canh.append(CHAEBOL_DU_PHONG)
    if ro == "VN200":
        ngoai_vt = [m for m in U["VN100"] if m not in VUTRU_LK]
        if ngoai_vt:
            canh.append(f"{len(ngoai_vt)} mã VN100 chưa có trong lk_vutru.json (đóng băng 23/09), vẫn được tính vào VN200: "
                        f"{ds(ngoai_vt)}")
    grid = [
        o("tom_tat", f"Rổ {RO_NHAN[ro]} · {len(rows)} mã", [o_so(tiles, 5), doan(f"Vũ trụ: {nguon_ro}.", "xam"),
                                                        canh_bao("Độ phủ dữ liệu của rổ", canh)], 12,
          "Tóm tắt rổ", "chaebol_map" if ro == "CHAEBOL" else "dashboard",
          "Chaebol map" if ro == "CHAEBOL" else "Dashboard", f"{T2} {EST}", trang_thai(luc, 3)),
        o("bang_ro", f"Bảng tóm tắt {RO_NHAN[ro]}", [bang_ro], 12, "Mỗi dòng một mã · số lấy từ tab gốc", "toanvu_pe",
          "P/E×LS TV", f"{T2} {EST}", trang_thai(luc, 3)),
    ]
    grid = tiles_solenh(ro, U, ten) + grid
    csv_cols = ["ma", "ten", "nhom", "gia", "gia_bang", "pct", "pe", "tv_pct", "tv_nguong", "tv_kich_hoat", "erp",
                "hhp_thuoc_do", "hhp_sigma", "hhp_vung", "fft_pct3y", "fft_pall", "chu_the", "pha", "nn_pct", "tp",
                "tp_nguon", "tp_ngay", "upside_pct"]
    csv_rows = [[r["ma"], r["ten"], r["nhom"], r["gia"], str(r["gia_live"]).lower(), r["pct"], r["pe"], r["tv_pct"],
                 r["tv_nguong"], None if r["tv_kh"] is None else str(bool(r["tv_kh"])).lower(), r["erp"], r["hhp_m"],
                 r["hhp_s"], r["hhp_z"], r["fft3"], r["fftall"], r["chu_the"], r["pha"], r["nn"], r["tp"], r["tp_src"],
                 r["tp_ngay"], r["upside"]] for r in rows]
    return {
        "meta": meta_obj("", ro, "", U, ten, luc, []),
        "bang": bang_chip(ro, U, ten, quotes),
        "cong": read_cong(h0),
        "o": grid,
        "csv": {"columns": csv_cols, "rows": csv_rows},
    }


def cut_s(s, n):
    s = nfc(s)
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def meta_obj(ma, ro, ten_ma, U, ten, luc, warnings):
    tat_ca = sorted(set().union(*U.values()))
    return {"schema": "aio/1", "version": VERSION, "ma": ma, "ro": ro, "ten": nfc(ten_ma),
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "data_to": ddmm(luc, False) + (" " + str(luc)[11:16] if len(str(luc)) >= 16 else ""),
            "warnings": [nfc(w) for w in warnings if nfc(w)],
            "ds_ma": [{"ma": m, "ten": nfc(ten.get(m)), "ro": RO_NHAN[next(r for r in RO if m in U[r])]} for m in tat_ca]}


# ───────────────────────────── lối vào ─────────────────────────────

def run_ma(tk, ro):
    import all_in_one_ma as M  # noqa: PLC0415 (tách tệp cho gọn; cùng thư mục scripts/)
    U, ten, nganh, san = load_universe()
    tv = thanh_vien(tk, U)
    if not tv:
        raise AioError("NO_TICKER", f"Mã {tk} không thuộc VN200 (lk_vutru.json) hay vũ trụ Chaebol MAP.")
    if ro not in tv and not (ro in RO and tk in {m for _, t in nhom_ro(ro, U) for m in t}):
        ro = tv[0]  # bấm chip VN100 trên bảng VN30 thì vẫn ở bảng VN30 (chip thuộc bảng đó)
    groups = nhom_ro(ro, U)
    quotes = load_quotes(sorted({m for _, t in groups for m in t} | {tk}), san)
    nhom_chb = next((n for n, t in nhom_chaebol(U) if tk in t), "") if "CHAEBOL" in tv else ""
    grid, warnings, h = M.build(tk, ten.get(tk, ""), nganh.get(tk, ""), san.get(tk, ""), tv, nhom_chb,
                                quotes.get(tk) or {}, U)
    luc = (quotes.get(tk) or {}).get("luc") or ""
    return {
        "meta": meta_obj(tk, ro, ten.get(tk, ""), U, ten, luc, warnings),
        "bang": bang_chip(ro, U, ten, quotes),
        "cong": read_cong(h),
        "o": grid,
        "csv": M.csv_for(tk, grid),
    }


def arg_value(argv, flag):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def run(argv):
    if len(argv) < 2:
        raise AioError("USAGE", USAGE)
    cmd = argv[1]
    ro = (arg_value(argv, "--ro") or "VN30").upper()
    if cmd == "bang":
        return run_board(ro if ro in RO else "VN30")
    if cmd == "ma":
        tk = (arg_value(argv, "--ma") or "").upper().strip()
        if not tk or not tk.isalnum() or len(tk) > 10:
            raise AioError("USAGE", USAGE)
        return run_ma(tk, ro)
    raise AioError("USAGE", USAGE)


def clean(o):
    """NaN/Inf → null; chuỗi chuyển tiếp từ tab gốc bỏ gạch dài U+2014/U+2015 (quy ước viết của người dùng)."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, str):
        return o.replace(" \u2014 ", ", ").replace("\u2014", "-").replace("\u2015", "-") if ("\u2014" in o or "\u2015" in o) else o
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    return o


def emit(obj):
    sys.stdout.buffer.write(json.dumps(clean(obj), ensure_ascii=False, separators=(",", ":"), allow_nan=False,
                                       default=str).encode("utf-8") + b"\n")
    sys.stdout.flush()


def main(argv=None):
    argv = sys.argv if argv is None else argv
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    # all_in_one_ma.py làm `import all_in_one`: trỏ về chính module đang chạy để biến toàn cục (NGAY_BANG, cache) là một.
    sys.modules.setdefault("all_in_one", sys.modules[__name__])
    try:
        emit(run(argv))
    except AioError as exc:
        emit({"error": exc.message, "error_code": exc.code})
    except Exception as exc:  # noqa: BLE001, luôn trả JSON cho panel
        emit({"error": f"Lỗi nội bộ all_in_one.py: {type(exc).__name__}: {exc}", "error_code": "INTERNAL"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
