#!/usr/bin/env python3
"""toanvu_pe.py, trang cho tab Fincept "toanvu_pe" (Vùng P/E × Lãi suất · Toàn Vũ), hợp đồng vnblocks/1.

Chỉ dùng stdlib, không gọi mạng. Đọc dữ liệu đã dựng sẵn bởi toanvu_pe_build.py:
  <STATE>/tong_quan.json, <STATE>/ma/<MÃ>.json      (STATE mặc định fincept_bridge/state/toanvu_pe,
                                                    đổi bằng biến môi trường TOANVU_PE_DIR)
và đọc thêm (chỉ đọc): dòng CỔNG thị trường (fincept_bridge/data/lk_thitruong.json → fft_langkinh.json),
giá live từ fincept_bridge/vnstore/vn_store.db để tính lại P/E và percentile phiên mới nhất (EST).

Dùng:
  toanvu_pe.py overview            trang tổng: phương pháp luận + kiểm định + bảng tra
  toanvu_pe.py ma --ma MWG         trang một mã: ghi chú phương pháp luận ở đầu, rồi phân tích mã
Luôn in một JSON {"meta","trang","csv"} hoặc {"error","error_code"} và thoát 0.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0"
CAN = "[CẦN DATA]"
SYS_DIR = Path.home() / "SECOND BRAIN-OBSIDIAN" / "_System"
BRIDGE = SYS_DIR / "fincept_bridge"
STATE = Path(os.environ.get("TOANVU_PE_DIR") or BRIDGE / "state" / "toanvu_pe")
VNSTORE = BRIDGE / "vnstore" / "vn_store.db"
GATE_MAX_AGE_H = 96
USAGE = "Dùng: toanvu_pe.py overview | toanvu_pe.py ma --ma MÃ|VNINDEX|VN30|VN100"
T_TV, T_FACT, T_EST = "SS-T3", "FACT-T2", "EST"
SCOPES = ("VNINDEX", "VN30", "VN100", "VN200", "REST")


class TvError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


# ───────────────────────────── tiện ích ─────────────────────────────

def nfc(s):
    return unicodedata.normalize("NFC", s).strip() if isinstance(s, str) else ""


def num(x):
    if x is None or isinstance(x, bool):
        return None
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


def iso_ms(d):
    try:
        y, m, dd = (int(p) for p in str(d)[:10].split("-"))
        return int(datetime(y, m, dd, tzinfo=timezone.utc).timestamp() * 1000)
    except (ValueError, TypeError):
        return None


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


def mau_sign(v, nguong=0.0):
    v = num(v)
    if v is None:
        return None
    return "xanh" if v > nguong else ("do" if v < -nguong else "xam")


# ── vnblocks helpers ──
def sec(sid, tieu_de, khoi, so="", eyebrow="", lede=""):
    return {"id": sid, "so": so, "tieu_de": nfc(tieu_de), "eyebrow": nfc(eyebrow), "lede": nfc(lede),
            "khoi": [b for b in khoi if b]}


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
        c["tip"] = tip
    return c


def bang(cot, dong, chu_thich="", can_phai=None):
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


def chips(items):
    return {"kieu": "chips", "chips": [{"tier": t, "text": nfc(x)} for t, x in items]}


def canh_bao(tieu_de, muc, mau="vang"):
    muc = [nfc(m) for m in muc if nfc(m)]
    return {"kieu": "canh_bao", "tieu_de": nfc(tieu_de), "muc": muc, "mau": mau} if muc else None


def the_card(tieu_de, text, nhan=None, nhan_mau=None, mau_vien=None, tier=""):
    c = {"tieu_de": nfc(tieu_de), "text": nfc(text), "tier": tier}
    if nhan:
        c["nhan"] = {"text": nfc(nhan), "mau": nhan_mau or "xam"}
    if mau_vien:
        c["mau_vien"] = mau_vien
    return c


# ───────────────────────────── nguồn ─────────────────────────────

def load_tong():
    t = read_json(STATE / "tong_quan.json")
    if not isinstance(t, dict) or not t.get("bang"):
        raise TvError("NO_DATA", f"Chưa có dữ liệu dựng sẵn ở {STATE}/tong_quan.json. "
                                 "Chạy: python3 scripts/toanvu_pe_build.py")
    return t


def load_ma(tk):
    p = read_json(STATE / "ma" / f"{tk}.json")
    if not isinstance(p, dict):
        raise TvError("NO_TICKER", f"Không có dữ liệu Bloomberg cho mã {tk} trong bộ Toàn Vũ (405 mã VNINDEX).")
    return p


def _parse_ts(s):
    if not s:
        return None
    s = str(s)
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s[:25], fmt)
            return d.replace(tzinfo=None)
        except ValueError:
            continue
    return None


def read_cong():
    """Dòng CỔNG thị trường, CHỈ đọc (lk_thitruong.cong → fft_langkinh.cong). Thiếu/quá 96 giờ → [CẦN DATA]."""
    cands = []
    lt = read_json(BRIDGE / "data" / "lk_thitruong.json") or {}
    fl = read_json(BRIDGE / "data" / "fft_langkinh.json") or {}
    if isinstance(lt.get("cong"), dict) and lt["cong"].get("dong"):
        cands.append(("lk_thitruong.cong", lt["cong"], _parse_ts(lt.get("tao_luc"))))
    if isinstance(fl.get("cong"), dict) and fl["cong"].get("dong"):
        cands.append(("fft_langkinh.cong", fl["cong"], _parse_ts(fl.get("cap_nhat"))))
    if not cands:
        return {"dong": "CỔNG: [CẦN DATA, không đọc được lk_thitruong/fft_langkinh] · không kết luận per-mã",
                "tier": "CẦN DATA", "as_of": None}
    src, c, ts = max(cands, key=lambda t: t[2] or datetime.min)
    if ts is None or (datetime.now() - ts).total_seconds() > GATE_MAX_AGE_H * 3600:
        return {"dong": "CỔNG: [CẦN DATA, bản CỔNG quá 96 giờ] · không kết luận per-mã", "tier": "CẦN DATA",
                "as_of": ts.strftime("%d/%m %H:%M") if ts else None}
    return {"dong": nfc(c["dong"]), "tier": c.get("bac") or T_EST, "as_of": ts.strftime("%d/%m %H:%M"), "src": src}


def live_price(tk):
    """(ngày ISO, giá VND, lúc) phiên mới nhất trong vnstore; None nếu không có."""
    if not VNSTORE.exists():
        return None
    try:
        c = sqlite3.connect(f"file:{VNSTORE}?mode=ro", uri=True, timeout=2)
        r = c.execute("select ngay, gia, luc from gia_moi where symbol=?", (tk,)).fetchone()
        if not r or num(r[1]) is None:
            r = c.execute("select ngay, dong, null from nen_ngay where symbol=? order by ngay desc limit 1", (tk,)).fetchone()
        c.close()
    except sqlite3.Error:
        return None
    if not r or num(r[1]) is None or num(r[1]) <= 0:
        return None
    return str(r[0])[:10], float(r[1]), r[2]


def pct_rank_le(window, v):
    """Ngữ nghĩa pandas rank(pct=True, method='max') của v trong window: tỷ lệ phần tử ≤ v (như bản gốc TV)."""
    vals = [x for x in window if num(x) is not None]
    n = len(vals)
    if n == 0:
        return None
    return sum(1 for x in vals if x <= v) / n * 100.0


def live_layer(p):
    """P/E và percentile phiên mới nhất theo giá vnstore ÷ EPS ngầm định Bloomberg (EST)."""
    cur = p.get("hien_tai") or {}
    eps, pe250 = num(cur.get("eps_ngam")), cur.get("pe250") or []
    lp = live_price(p["ma"])
    if not lp or eps is None or eps <= 0 or not pe250:
        return None
    ngay, gia, luc = lp
    if ngay <= str(cur.get("ngay") or ""):
        return None
    pe = gia / eps
    # cửa sổ 250 phiên kết thúc ở phiên live (chỉ cuộn một phiên dù live cách phiên đủ cuối vài phiên: EST)
    win = (list(pe250[1:]) if len(pe250) >= 250 else list(pe250)) + [pe]
    if sum(1 for x in win if num(x) is not None) < 60:
        return None
    pct = pct_rank_le(win, pe)
    nguong = num(cur.get("nguong"))
    ls = num(cur.get("ls"))
    return {"ngay": ngay, "luc": luc, "gia": gia, "pe": pe, "pct": pct, "nguong": nguong,
            "kich_hoat": (pct is not None and nguong is not None and pct <= nguong),
            "ey": 100.0 / pe, "erp": (100.0 / pe - ls) if ls is not None else None}


# ───────────────────────────── khối phương pháp luận ─────────────────────────────

def cong_dung(cong):
    d = (cong or {}).get("dong") or ""
    return (not d) or "[CẦN DATA" in d or "DỪNG" in d.upper()


def block_cong(cong, extra=""):
    phu = "Đọc nguyên văn từ lăng kính v1.7"
    if cong.get("as_of"):
        phu += f" · bản {cong['as_of']}"
    phu += ". Tab này trình bày luật định giá của Toàn Vũ và kết quả kiểm định; không phát nhãn mua/bán từng mã."
    if extra:
        phu += " " + extra
    return {"kieu": "cong", "dong": cong["dong"], "tier": cong.get("tier") or T_EST, "phu": phu}


def _k(t):
    k = t["kiem_dinh"]
    return k, k.get("do_ben") or {}, k.get("eps_tre_45") or {}


def method_compact(t):
    k, db, e45 = _k(t)
    g, g4 = k["gop"], (e45.get("gop") or {})
    fi = t["nguon"]["fiinprox"]
    pe = (t.get("pe_thi_truong") or [{}])[0]
    txt = (
        "Toàn Vũ coi một tài sản là rẻ hơn khi nắm giữ nó cho khả năng sinh lời cao hơn. Lợi suất lợi nhuận "
        "EY = 100/P/E đặt cạnh lãi suất huy động VND >12 tháng cao nhất (LS); ERP = EY − LS. Ở từng mã, luật của anh: "
        "P/E ≤ percentile X của 250 phiên gần nhất của chính mã, X = max(5; 40 − 4×(LS − 5)): LS càng cao thì chuẩn \"rẻ\" "
        "càng khắt khe (LS 5% → X 40; 7,6% → 29,6; 10% → 20; từ 13,75% → 5). Hiệu quả đo bằng lợi suất 20/60/120 phiên sau "
        "mỗi ngày kích hoạt; alpha = TB khi kích hoạt − TB mọi ngày. "
        f"Kiểm định (EST): tái lập đạt. Nhưng P/E lịch sử của Bloomberg ghi EPS quý mới vào ngày cuối quý, trước khi BCTC công bố. "
        f"Trễ EPS 45 ngày cho đúng lúc thị trường biết, luật thắng {vn((g4.get('tin_hieu') or {}).get('hit'), 1)}% so với nền "
        f"{vn((g4.get('moi_ngay') or {}).get('hit'), 1)}%, so cùng ngày {vn((g4.get('tin_hieu') or {}).get('xs'), 2, True)} điểm: "
        "không còn lợi thế. Kết quả lịch sử chủ yếu do hướng đi của LS (nhịp thị trường). Phần duy nhất còn phân tầng sau khi "
        "bỏ nhìn trước là ERP từng mã."
    )
    return [
        doan(txt, the=True, tieu_de="Phương pháp luận · Toàn Vũ (SS-T3) → kiểm định Hội đồng (EST)"),
        chips([(T_TV, "luật & báo cáo 06/10/2026"), (T_FACT, f"Bloomberg PE_RATIO {t['nguon']['bloomberg']['so_ma']} mã"),
               (T_FACT, f"FiinProX LS >12T tới {ddmm(fi['moi_nhat']['ngay'])}"),
               (T_EST, f"LS 'hiện tại' 11,78% của bản gốc là dòng 03/03/2008 → đúng là {vn(t['ls_hien_tai'])}%"),
               (T_EST, f"P/E thị trường 9,5x = gộp bỏ P/E>40 (bỏ VIC); đủ mã {vn(pe.get('harm_tat_ca'))}x"),
               (T_EST, "P/E Bloomberg nhìn trước EPS ~3–7 tuần")]),
    ]


def method_full(t):
    k, db, e45 = _k(t)
    tl, fi, tv = t["tai_lap"], t["nguon"]["fiinprox"], t["tv_in"]
    pe0 = (t.get("pe_thi_truong") or [{}])[0]
    g, g4 = k["gop"], (e45.get("gop") or {})
    lag = t.get("ls_tre_1_thang") or {}
    lag6 = next((r for r in lag.get("muc_ls", []) if r["muc"] == "<6%"), {})
    luat = {"kieu": "danh_sach", "muc": [
        {"tieu_de": "Đắt/rẻ là so sánh khả năng sinh lời, không phải mức P/E vật lý",
         "text": "Một tài sản rẻ hơn tài sản khác khi nắm giữ nó cho lợi suất cao hơn. Cổ phiếu được đặt cạnh tiền gửi: "
                 "EY = 100/P/E đối với LS huy động VND kỳ hạn >12 tháng cao nhất. Khi EY bắt kịp rồi vượt LS, mua cổ phiếu hấp dẫn hơn "
                 "gửi tiết kiệm hay trái phiếu. Ví dụ anh nêu: DGW vùng 3x tương ứng EY khoảng 12,5%.",
         "tags": [T_TV]},
        {"tieu_de": "Lớp thị trường: P/E hợp lý = 100/LS, ERP = EY − LS",
         "text": f"Bản 07/09: P/E {vn(tv['macro_pe'], 1)}x, P/E hợp lý {vn(tv['macro_pe_fair'], 1)}x (LS {vn(tv['macro_ls'])}%), "
                 f"EY {vn(tv['macro_ey'])}%, ERP {vn(tv['macro_erp'], 2, True)}% → vùng \"Tích lũy\" (2–5%). Ngưỡng: ERP ≥ 5% mua mạnh, "
                 "ERP < −3% nguy hiểm, LS > 10% bất lợi cho cổ phiếu.",
         "tags": [T_TV]},
        {"tieu_de": "Lớp từng mã: rẻ so với chính nó, chuẩn rẻ siết theo LS",
         "text": "Tín hiệu khi P/E ≤ percentile X của 250 phiên gần nhất (tối thiểu 60 phiên; percentile = tỷ lệ phiên có P/E ≤ hôm nay). "
                 "X = max(5; 40 − 4×(LS − 5)). Anh backtest trên từng mã thay vì VN-Index vì chỉ số san phẳng tín hiệu, "
                 "rồi mới lấy trung bình cộng các mã.",
         "tags": [T_TV]},
        {"tieu_de": "Luận điểm đi kèm trong trao đổi 06/10",
         "text": "Năm nay tiền đắt và LS đi lên suốt năm nên đứng ngoài, phòng ngự là đúng. LS vào xu hướng tăng thì cần chiết khấu mạnh hơn: "
                 "LS càng cao càng cần ERP cao, không đổi ngang giá được. Rẻ so với chính nó cộng thủng đáy 52 tuần thường mua vào là lỗ.",
         "tags": [T_TV]},
    ]}
    loi = canh_bao("Bốn chỗ lệch trong bản gốc (tái lập bằng chính dữ liệu Toàn Vũ gửi)", [
        f"LS \"hiện tại\" {vn(tv['ls_hien_tai'])}% là giá trị CŨ NHẤT của tệp FiinProX ({ddmm(fi['cu_nhat']['ngay'])}). Tệp xếp mới nhất lên đầu; "
        f"giá trị đúng là {vn(fi['moi_nhat']['ls'])}% ({ddmm(fi['moi_nhat']['ngay'])}) nên ngưỡng đúng là {vn(t['nguong_hien_tai'], 1)}% chứ không phải "
        f"{tv['nguong']}%. Các cột từng mã trong biểu đồ ④ thật ra đã dùng ngưỡng 30% (VPB P15,2 và HDB P16,8 được tính là kích hoạt), chỉ dòng tiêu đề sai.",
        "Mọi percentile \"hiện tại\" trong báo cáo là số của phiên 07/09/2026, không phải 06/10/2026 như ngày in: khớp tuyệt đối 8/8 mã watchlist "
        "và 25/25 mã top (GEE 0,4 · PVP 12,4 · VPB 15,2 · MWG 4,4 · HDB 16,8 · FRT 12,0 · HAH 9,6 · PVT 12,4). Tới 05/10: PVP P66,8, HAH P45,2, PVT P45,6.",
        "Danh sách Top 25 \"đang có signal\" có 7 mã đang ở trên ngưỡng (GEX P44, SZL P66, DHA P60, CLW P41, TPC P38, TDW P35, MIG P34). "
        "Chỉ khớp nếu hiểu là \"từng kích hoạt trong vài chục phiên gần nhất\" (từ 27 phiên trở lên). Không định nghĩa nào tái lập cùng lúc danh sách này và con số 259.",
        f"P/E thị trường {vn(tv['macro_pe'], 1)}x ghi là \"cap-weighted\" nhưng thực chất là P/E gộp (tổng vốn hoá ÷ tổng lợi nhuận) sau khi BỎ các mã "
        f"P/E > 40: ra {vn(pe0.get('harm_bo_pe_tren40'))}x, ERP {vn(pe0.get('erp_harm_bo_pe_tren40'), 2, True)}% (khớp {vn(tv['macro_erp'], 2, True)}%). "
        f"Bộ lọc bỏ {(pe0.get('bo_pe_tren40') or {}).get('so_ma', '')} mã ({vn((pe0.get('bo_pe_tren40') or {}).get('ty_trong_von_hoa_pct'), 1)}% vốn hoá); "
        f"riêng VIC (P/E {vn(pe0.get('ma_von_hoa_lon_nhat', {}).get('pe'), 1)}x, {vn(pe0.get('ma_von_hoa_lon_nhat', {}).get('ty_trong_pct'), 1)}% vốn hoá) đã đẩy ERP "
        f"từ {vn(pe0.get('erp_harm_tat_ca'), 2, True)}% lên {vn(pe0.get('erp_harm_bo_ma_lon_nhat'), 2, True)}%. "
        f"Đủ mã: {vn(pe0.get('harm_tat_ca'))}x, ERP {vn(pe0.get('erp_harm_tat_ca'), 2, True)}%: vùng \"hoà\", không phải \"Tích lũy\".",
    ])
    pp = canh_bao("Ba lỗi phương pháp làm đẹp backtest (ảnh hưởng cả bản gốc lẫn tái lập)", [
        "Nhìn trước lợi nhuận: chuỗi PE_RATIO lịch sử của Bloomberg ghi EPS quý mới vào đúng ngày cuối quý (≈95% lần EPS đổi rơi vào 31/3, 30/6, "
        "30/9, 31/12), trong khi BCTC quý công bố sau 3–7 tuần. Trễ EPS 45 ngày thì so cùng ngày của luật từ "
        f"{vn(g['tin_hieu']['xs'], 2, True)} còn {vn((g4.get('tin_hieu') or {}).get('xs'), 2, True)} điểm, alpha kiểu TV từ {vn(g.get('alpha_kieu_tv'), 2, True)} "
        f"còn {vn(g4.get('alpha_kieu_tv'), 2, True)}.",
        "LS là số THÁNG (FiinProX ghi \"(M)\") gán từ ngày đầu tháng; nếu số tháng chỉ biết vào cuối tháng thì backtest nhìn trước tới 1 tháng. "
        f"Trễ LS 1 tháng, vùng LS < 6% đảo từ dương sang {vn(lag6.get('r60'), 2, True)}%/60 phiên, thắng {vn(lag6.get('hit'), 1)}%.",
        "Thiên lệch sống sót: bộ 405 mã là thành viên VNINDEX hiện tại; mã \"rẻ\" rồi huỷ niêm yết không có mặt, đúng loại mà luật \"rẻ so với chính nó\" sẽ mua.",
    ], mau="do")
    tiles = {"kieu": "o_so", "cot": 4, "o": [
        tile("Tái lập luật TV", vn(tl["spearman"], 2),
             "tương quan hạng alpha 53 mã TV in (lấy từ hai đuôi; trong từng đuôi ≈ 0,6) · VPB, HDB khớp tuyệt đối",
             "xanh", T_EST),
        tile("Bản gốc · so cùng ngày", vn(g["tin_hieu"]["xs"], 2, True),
             f"trung vị {vn(db.get('xs_trung_vi'), 2, True)} · bỏ 1% quan sát ngày-mã tốt nhất còn {vn(db.get('xs_bo_1pct_tot_nhat'), 2, True)} · "
             f"t Newey-West theo ngày {vn(db.get('t_nw_xs_theo_ngay'), 1)}", "vang", T_EST),
        tile("Bỏ nhìn trước EPS 45 ngày", vn((g4.get("tin_hieu") or {}).get("xs"), 2, True),
             f"so cùng ngày · thắng {vn((g4.get('tin_hieu') or {}).get('hit'), 1)}% vs nền {vn((g4.get('moi_ngay') or {}).get('hit'), 1)}% · "
             f"t theo ngày {vn((e45.get('do_ben') or {}).get('t_nw_xs_theo_ngay'), 1)}", "do", T_EST),
        tile("Độ phủ tín hiệu", f"{vn(k['do_phu_tin_hieu']['tb'], 0)}% rổ",
             f"trung bình mỗi ngày · p90 {vn(k['do_phu_tin_hieu']['p90'], 0)}%: bộ lọc thô, không phải danh sách chọn", "vang", T_EST),
    ]}
    ket = doan(
        "Đọc gọn: luận điểm vĩ mô của Toàn Vũ (đắt rẻ là so lợi suất với tiền gửi; LS đi lên thì đứng ngoài) được dữ liệu ủng hộ ở mức NHỊP thị "
        "trường, không ở mức chọn mã. Công thức từng mã (percentile P/E với ngưỡng siết theo mức LS) không giữ được lợi thế khi bỏ nhìn trước "
        "EPS, và ngưỡng động không hơn ngưỡng cố định cùng độ phủ. Thứ còn đứng là ERP của chính mã (EY − LS), đúng khái niệm anh dùng khi "
        "nói chuyện nhưng không có trong code backtest. Điểm gãy của mọi đọc ở đây: LS tháng 9–10 chưa có, và một lượt BCTC quý 3 sẽ đổi "
        "toàn bộ EPS.", the=True, tieu_de="Kết luận kiểm định")
    return [luat, loi, pp, tiles, ket]


# ───────────────────────────── bảng kiểm định ─────────────────────────────

def o_hien_tai(t):
    ls, d = num(t.get("ls_hien_tai")), num(t.get("ls_dls6m"))
    if ls is None:
        return CAN
    muc = "<6%" if ls < 6 else ("6–8%" if ls < 8 else ("8–10%" if ls < 10 else "≥10%"))
    if d is None:
        return f"mức {muc}"
    huong = "giảm" if d < -0.1 else ("tăng" if d > 0.1 else "đi ngang")
    return f"mức {muc} (LS {vn(ls)}%), hướng {huong} ({vn(d, 2, True)} điểm/6 tháng)"


def erp_co(k, e45):
    """Một câu: nhóm ERP cao nhất và chênh đầu–cuối co bao nhiêu sau khi trễ EPS (đọc từ dữ liệu)."""
    try:
        b = [num(r["moi_ngay"]["xs"]) for r in k["erp"]]
        a = [num(r["moi_ngay"]["xs"]) for r in e45["erp"]]
        top_b, top_a, sp_b, sp_a = b[-1], a[-1], b[-1] - b[0], a[-1] - a[0]
        return (f"Sau khi trễ EPS, so cùng ngày của nhóm ERP cao nhất co từ {vn(top_b, 2, True)} xuống {vn(top_a, 2, True)} "
                f"(mất {vn((1 - top_a / top_b) * 100, 0)}%), chênh đầu–cuối co từ {vn(sp_b, 2)} xuống {vn(sp_a, 2)} điểm.")
    except (KeyError, IndexError, TypeError, ZeroDivisionError):
        return ""


def stat_cells(s, with_n=True, xs=True):
    s = s or {}
    out = []
    if with_n:
        out.append(cell(vn(s.get("n"), 0)))
    out += [cell(vn(s.get("r60"), 2, True), mau_sign(s.get("r60"))), cell(vn(s.get("hit"), 1))]
    if xs:
        out.append(cell(vn(s.get("xs"), 2, True), mau_sign(s.get("xs"), 0.25)))
    return out


def audit_sections(t):
    k, db, e45 = _k(t)
    g4 = e45.get("gop") or {}
    secs = []
    # A · bỏ nhìn trước
    rows = [
        [cell("Bản gốc · P/E Bloomberg", mono=False, dam=True)] + stat_cells(k["gop"]["tin_hieu"]) +
        [cell(vn(db.get("xs_theo_ngay"), 2, True)), cell(vn(k["gop"].get("alpha_kieu_tv"), 2, True), mau_sign(k["gop"].get("alpha_kieu_tv"), 0.25))],
        [cell("Nền mọi ngày (bản gốc)", mono=False)] + stat_cells(k["gop"]["moi_ngay"]) + [cell(""), cell("")],
        [cell("EPS trễ 45 ngày", mono=False, dam=True)] + stat_cells(g4.get("tin_hieu")) +
        [cell(vn((g4.get("tin_hieu") or {}).get("xs_theo_ngay"), 2, True)), cell(vn(g4.get("alpha_kieu_tv"), 2, True), mau_sign(g4.get("alpha_kieu_tv"), 0.25))],
        [cell("Nền mọi ngày (EPS trễ)", mono=False)] + stat_cells(g4.get("moi_ngay")) + [cell(""), cell("")],
    ]
    secs.append(sec("nhin_truoc", "Bỏ nhìn trước lợi nhuận thì luật còn gì?", [
        doan("P/E dùng trong backtest phải là P/E thị trường biết vào ngày đó. Chuỗi PE_RATIO lịch sử của Bloomberg không như vậy: EPS quý mới được "
             "ghi vào ngày cuối quý, vài tuần trước khi doanh nghiệp công bố. Một mã sắp báo lãi tăng mạnh vì thế trông \"rẻ\" trong lịch sử trước "
             "khi ai biết, rồi giá tăng theo kết quả: tín hiệu \"rẻ\" thắng nhờ biết trước. Dời EPS 45 ngày (hạn công bố BCTC hợp nhất quý) thì "
             "lợi thế gần như biến mất."),
        bang(["Phiên bản", "Ngày-mã", "TB 60 phiên", "Thắng %", "So cùng ngày", "So cùng ngày (theo ngày)", "Alpha kiểu TV"], rows,
             f"So cùng ngày bản gốc: trung vị {vn(db.get('xs_trung_vi'), 2, True)}, bỏ 1% quan sát ngày-mã tốt nhất còn {vn(db.get('xs_bo_1pct_tot_nhat'), 2, True)}, "
             f"bỏ 5% còn {vn(db.get('xs_bo_5pct_tot_nhat'), 2, True)}: toàn bộ lợi thế nằm ở đuôi phải, đúng vùng mà thiên lệch sống sót và nhìn trước "
             f"thổi phồng. t Newey-West (60 phiên) theo ngày: bản gốc {vn(db.get('t_nw_xs_theo_ngay'), 1)}, EPS trễ {vn((e45.get('do_ben') or {}).get('t_nw_xs_theo_ngay'), 1)}. EST.",
             [1, 2, 3, 4, 5, 6]),
    ], so="A", eyebrow="Kiểm định · EST"))
    # B · ngưỡng
    rows = [[cell(r["nguong"], dam=r["nguong"].startswith("động"), mono=False), cell(vn(r["n"], 0)),
             cell(vn(r["r60"], 2, True), mau_sign(r["r60"])), cell(vn(r["hit"], 1)),
             cell(vn(r["xs"], 2, True), mau_sign(r["xs"], 0.25)), cell(vn(r.get("xs_theo_ngay"), 2, True), mau_sign(r.get("xs_theo_ngay"), 0.25))]
            for r in k["nguong"]]
    rows4 = [[cell(r["nguong"], dam=r["nguong"].startswith("động"), mono=False), cell(vn(r["n"], 0)),
              cell(vn(r["r60"], 2, True), mau_sign(r["r60"])), cell(vn(r["hit"], 1)),
              cell(vn(r["xs"], 2, True), mau_sign(r["xs"], 0.25)), cell(vn(r.get("xs_theo_ngay"), 2, True), mau_sign(r.get("xs_theo_ngay"), 0.25))]
             for r in (e45.get("nguong") or [])]
    secs.append(sec("nguong", "Ngưỡng động theo mức LS có thêm giá trị gì không?", [
        doan(f"Không. Ngưỡng cố định P{vn(db.get('nguong_co_dinh_cung_do_phu'), 1)} cho cùng độ phủ với ngưỡng động ({vn(db.get('do_phu_pct'), 1)}% số ngày-mã) nhưng so cùng ngày "
             f"{vn(db.get('xs_nguong_co_dinh_cung_do_phu'), 2, True)} (gộp ngày-mã) và {vn(db.get('xs_theo_ngay_nguong_co_dinh_cung_do_phu'), 2, True)} (theo ngày), "
             f"cao hơn ngưỡng động ({vn(k['gop']['tin_hieu']['xs'], 2, True)} và {vn(db.get('xs_theo_ngay'), 2, True)}). \"Càng chặt càng tốt\" chỉ đúng khi gộp "
             "ngày-mã, vì cách gộp này dồn trọng số vào vài ngày khủng hoảng có rất nhiều mã cùng rẻ; gộp theo ngày thì ngưỡng 5% lại yếu nhất. "
             "Lý do gốc: giai đoạn 2015–2022 LS quanh 6,4–7,5%, ngưỡng động nới ra khoảng 30–34%."),
        bang(["Ngưỡng", "Ngày-mã", "TB 60 phiên", "Thắng %", "So cùng ngày", "So cùng ngày (theo ngày)"], rows,
             f"Bản gốc, gộp {vn(k['so_ma'], 0)} mã, {ddmm(k['tu'])} → {ddmm(k['den_r60'])}. EST.", [1, 2, 3, 4, 5]),
        bang(["Ngưỡng · EPS trễ 45 ngày", "Ngày-mã", "TB 60 phiên", "Thắng %", "So cùng ngày", "So cùng ngày (theo ngày)"], rows4,
             "Sau khi bỏ nhìn trước, không ngưỡng nào giữ được lợi thế theo ngày. EST.", [1, 2, 3, 4, 5]),
    ], so="B", eyebrow="Kiểm định · EST"))
    # C · hướng LS
    rows = [[cell(r["huong"], mono=False, dam=True)] + stat_cells(r["tin_hieu"]) + stat_cells(r["moi_ngay"], with_n=False, xs=False)
            for r in k["huong_ls"]]
    mx = [[cell(r["muc"], mono=False), cell(r["huong"], mono=False), cell(vn(r["n"], 0)),
           cell(vn(r["r60"], 2, True), mau_sign(r["r60"])), cell(vn(r["hit"], 1)), cell(vn(r["xs"], 2, True), mau_sign(r["xs"], 0.25)),
           cell(f"{r['tu']}–{r['den']}")] for r in k["muc_x_huong"]]
    lag = t.get("ls_tre_1_thang") or {}
    lagm = {r["muc"]: r for r in lag.get("muc_ls", [])}
    lv = [[cell(r["muc"], mono=False, dam=True), cell(vn(r["tv"]["r60"], 1, True)), cell(vn(r["tv"]["r120"], 1, True)), cell(vn(r["tv"]["hit"], 0)),
           cell(vn(r["r60"], 2, True), mau_sign(r["r60"])), cell(vn(r["r120"], 2, True), mau_sign(r["r120"])), cell(vn(r["hit"], 1)),
           cell(vn(lagm.get(r["muc"], {}).get("r60"), 2, True), mau_sign(lagm.get(r["muc"], {}).get("r60"))),
           cell(vn(lagm.get(r["muc"], {}).get("hit"), 1)),
           cell(f"{r.get('tu') or ''}–{r.get('den') or ''}")] for r in k["muc_ls_tv"]]
    cur_dir = t.get("ls_dls6m")
    secs.append(sec("huong_ls", "Hướng đi của lãi suất quan trọng hơn mức lãi suất", [
        doan("Bản gốc chia theo MỨC LS và kết luận \"LS thấp + P/E rẻ là tổ hợp tốt nhất\". Chính biểu đồ ③ của anh bác câu đó: vùng tốt nhất là "
             "LS 8–10%, và vùng LS < 6% chỉ là một đợt hai tháng (12/2024–01/2025). Vùng 8–10% tốt chủ yếu nhờ các giai đoạn LS đang GIẢM từ đỉnh "
             "(khoảng 56% số ngày tín hiệu của vùng, 2009–2014); phần LS tăng trong vùng này vẫn dương nhưng thua cả rổ cùng ngày. Chia theo hướng LS 6 tháng: tín hiệu khi LS giảm hoặc đi ngang cho lợi suất 60 phiên dương, khi LS tăng cho "
             "lợi suất âm. Cột \"mọi ngày\" cho cùng thứ tự, nên đây là nhịp thị trường chứ không phải tài chọn mã của luật. Khớp đúng câu anh nói "
             "(LS tăng suốt năm thì đứng ngoài), nhưng công thức ngưỡng lại không dùng hướng LS. Lưu ý độ chắc: mỗi nhóm hướng chỉ gồm khoảng 10 "
             "giai đoạn; khác biệt giảm vs tăng có ý nghĩa ở mức biên, còn thứ tự chi tiết (tăng vs tăng mạnh) đổi khi đổi cách gộp."),
        bang(["Hướng LS 6 tháng", "Ngày tín hiệu", "TB 60 phiên", "Thắng %", "So cùng ngày", "Mọi ngày: TB 60", "Mọi ngày: thắng %"], rows,
             f"Hướng = LS hôm nay − LS 182 ngày trước, làm tròn 4 chữ số (LS đi bước 0,1 điểm): giảm mạnh < −0,5; giảm −0,5…−0,1; đi ngang ±0,1; "
             f"tăng 0,1…0,5; tăng mạnh > 0,5. Phiên đủ cuối: {vn(cur_dir, 2, True)} điểm. EST.", [1, 2, 3, 4, 5, 6]),
        bang(["Mức LS", "TV in: 60", "TV in: 120", "TV in: thắng %", "Tái lập: 60", "Tái lập: 120", "Tái lập: thắng %",
              "LS trễ 1 tháng: 60", "LS trễ 1 tháng: thắng %", "Thời gian"],
             lv, "Số TV in đọc từ biểu đồ ③ (SS-T3). Số ngày-mã của bản gốc bằng khoảng 1/4 tái lập (có thể lấy mẫu); tỷ suất khớp. EST.",
             [1, 2, 3, 4, 5, 6, 7, 8]),
        bang(["Mức LS", "Hướng", "Ngày tín hiệu", "TB 60 phiên", "Thắng %", "So cùng ngày", "Thời gian"], mx,
             f"Mức × hướng, chỉ ngày kích hoạt. Ô hiện tại: {o_hien_tai(t)}. EST.", [2, 3, 4, 5]),
    ], so="C", eyebrow="Kiểm định · EST"))
    # D · ERP
    rows = [[cell(r["erp"], mono=False, dam=True)] + stat_cells(r["moi_ngay"]) + stat_cells(r["tin_hieu"]) for r in k["erp"]]
    rows4 = [[cell(r["erp"], mono=False, dam=True)] + stat_cells(r["moi_ngay"]) +
             [cell(vn((r["moi_ngay"] or {}).get("xs_theo_ngay"), 2, True), mau_sign((r["moi_ngay"] or {}).get("xs_theo_ngay"), 0.25))]
             for r in (e45.get("erp") or [])]
    v52 = [[cell(r["nhom"], mono=False)] + stat_cells(r) for r in k["vung52"]]
    lt = k["lai_tg"]
    secs.append(sec("erp", "ERP từng mã: phần duy nhất còn đứng sau khi bỏ nhìn trước", [
        doan("Báo cáo per-stock mang tên ERP nhưng tín hiệu của nó không dùng ERP; nó chỉ so P/E với lịch sử của chính mã. Tính đúng ERP từng mã "
             "(100/P/E − LS) thì tỷ lệ thắng và so cùng ngày tăng theo từng nấc, và thứ tự này giữ được sau khi trễ EPS 45 ngày. Cần đọc đúng bản chất: ERP từng mã gần như là xếp theo E/P, tức yếu tố giá trị, cộng mức LS. Trong chính các ngày "
             "luật TV kích hoạt, nhóm ERP âm (rẻ so với mình nhưng vẫn đắt so với tiền gửi) cho so cùng ngày âm: bẫy định giá mà luật gốc không lọc. "
             + erp_co(k, e45)),
        bang(["ERP (điểm %)", "Mọi ngày: n", "TB 60", "Thắng %", "So cùng ngày", "Khi kích hoạt: n", "TB 60", "Thắng %", "So cùng ngày"], rows,
             "Bản gốc. ERP = 100/P/E trailing − LS >12T cao nhất. P/E Bloomberg chỉ có khi lãi dương nên ngày lỗ không có mặt. EST.", list(range(1, 9))),
        bang(["ERP · EPS trễ 45 ngày", "Mọi ngày: n", "TB 60", "Thắng %", "So cùng ngày", "So cùng ngày (theo ngày)"], rows4,
             "Phiên bản không nhìn trước. Nhóm thấp nhất là P/E cao (trung vị ~40x), nhóm cao nhất là P/E rất thấp (trung vị ~3,6x). EST.",
             [1, 2, 3, 4, 5]),
        doan(f"Rào cản tiền gửi: chỉ {vn(lt['vuot_pct'], 1)}% ngày kích hoạt cho lợi suất 60 phiên vượt lãi tiền gửi cùng kỳ (LS × 60/250). "
             "Báo cáo vĩ mô của anh in vùng \"Tích lũy\" (ERP 2–5%) với thắng 61% (kỳ 60 phiên) và TB +3,3% (kỳ 120 phiên): hai kỳ hạn khác nhau. "
             "+3,3% thấp hơn lãi tiền gửi 7,6%/năm trong 120 phiên (≈3,65%), nhưng chênh 0,3 điểm nằm trong nhiễu (chỉ khoảng 15 cửa sổ 120 phiên "
             "độc lập). Điều chắc chắn được: vùng \"Tích lũy\" chưa chứng minh được nó hơn gửi tiết kiệm."),
        bang(["Vùng 52 tuần", "Ngày-mã", "TB 60 phiên", "Thắng %", "So cùng ngày"], v52,
             "Kiểm câu \"rẻ so với chính nó + thủng 52 tuần thường lỗ\": đúng một nửa. Sát đáy 52 tuần (≤ 3%, chưa thủng) xoá sạch lợi thế; "
             "đã thủng đáy thì không tệ hơn. Không lọc P/E, ngày thủng đáy 52 tuần cho so cùng ngày âm. Bản gốc, EST.", [1, 2, 3, 4]),
    ], so="D", eyebrow="Kiểm định · EST"))
    # E · độ tin cậy xếp hạng
    dt = t["dot_tong"]
    secs.append(sec("dot", "Xếp hạng từng mã của bản gốc phần lớn là nhiễu", [
        doan(f"Mỗi ngày kích hoạt được tính là một quan sát, trong khi các ngày liền nhau dùng chung một cửa sổ 60 phiên. Lấy mốc vào cách nhau "
             f"từ 60 phiên trở lên để cửa sổ không chồng thì toàn rổ còn {vn(dt['n_dot'], 0)} mốc độc lập. Mã đứng đầu bảng của anh, NO1 (thắng 98%, "
             f"alpha +35%), chỉ có vài mốc như vậy. GEE đứng chót (\"bẫy\", −31,8 điểm) dựa trên 12 ngày thuộc 2 đợt cho kết quả trái ngược. "
             f"Kiểm t trên so cùng ngày tại các mốc độc lập: {dt['ma_p05_duong']} mã dương có ý nghĩa ở mức 5% trên {dt['ma_kiem']} mã kiểm, trong khi "
             f"riêng may rủi đã cho khoảng {vn(dt['ma_kiem'] * 0.025, 0)} mã (p ≈ {vn(dt.get('p_nhi_thuc_duong'), 2)}); phía âm {dt['ma_p05_am']} mã. "
             "Không có tín hiệu cấp mã nào vượt mức may rủi, và đây còn là bản chưa bỏ nhìn trước EPS. Bảng xếp hạng nên đọc như danh sách để soi, "
             "không phải bằng chứng."),
    ], so="E", eyebrow="Kiểm định · EST"))
    return secs


# ───────────────────────────── bảng tra (overview) ─────────────────────────────

TV_WATCH = ["MWG", "VPB", "HDB", "STB", "GEE", "HAH", "PVT", "PVP", "FRT"]


def row_tra(r, cur_live=None):
    kh = r.get("kich_hoat")
    kh_t = "KÍCH HOẠT" if kh is True else ("không" if kh is False else "")
    return [cell(r["ma"], dam=True, mono=False, tip=nfc(r.get("ten"))), cell(vn(r.get("pe"), 2)),
            cell(vn(r.get("pct"), 1)), cell(kh_t, "vang" if kh else "xam", pill=bool(kh), mono=False),
            cell(vn(r.get("ey"), 2)), cell(vn(r.get("erp"), 2, True), mau_sign(r.get("erp"), 0.5)),
            cell(vn(r.get("n_dot"), 0)), cell(vn(r.get("hit_dot"), 0)), cell(vn(r.get("xs_dot"), 1, True), mau_sign(r.get("xs_dot"), 0.5)),
            cell(vn(r.get("alpha_tv"), 1, True)), cell(vn(r.get("alpha_tv_goc"), 2, True), "tim" if r.get("alpha_tv_goc") is not None else None)]


COT_TRA = ["Mã", "P/E", "Pct 250", "Luật TV", "EY %", "ERP", "Đợt", "Thắng đợt %", "So cùng ngày (đợt)", "Alpha TV tái lập", "Alpha TV in"]


def overview_tables(t, cong=None):
    rows = {r["ma"]: r for r in t["bang"]}
    wl = [row_tra(rows[m]) for m in TV_WATCH if m in rows]
    vn30 = sorted([r for r in t["bang"] if "VN30" in (r.get("nhom") or "") and r["ma"] not in TV_WATCH], key=lambda r: r["ma"])
    trig = [r for r in t["bang"] if r.get("kich_hoat") is True and num(r.get("erp")) is not None]
    hi = sorted(trig, key=lambda r: -r["erp"])[:25]
    lo = sorted([r for r in trig if r["erp"] < 0], key=lambda r: r["erp"])[:25]
    note = (f"Phiên đủ {ddmm(t['phien_du_cuoi'])} · LS {vn(t['ls_hien_tai'])}% → ngưỡng {vn(t['nguong_hien_tai'], 1)}%. "
            "Đợt = đợt kích hoạt độc lập có lợi suất 60 phiên. Alpha TV in: số Toàn Vũ in (SS-T3); còn lại EST.")
    return [sec("tra", "Bảng tra trạng thái luật TV", [
        doan(f"{t['so_ma_kich_hoat']}/{t['so_ma_cham']} mã đang thỏa luật TV ở phiên {ddmm(t['phien_du_cuoi'])}. Với độ phủ cỡ này, \"kích hoạt\" "
             "chỉ là bộ lọc thô. Hai bảng dưới tách nhóm kích hoạt theo ERP: nhóm ERP cao là chỗ hiếm hoi P/E rẻ đi cùng lợi suất vượt tiền gửi; "
             "nhóm ERP âm là rẻ so với chính mình nhưng vẫn đắt so với tiền gửi. Đây là dữ kiện để soi, không phải danh sách mua"
             + (": CỔNG đang DỪNG." if cong_dung(cong) else "."),
             mau=None),
        doan("Watchlist Toàn Vũ (9 mã)", mau="vang"), bang(COT_TRA, wl, note, list(range(1, 11))),
        doan("VN30 còn lại", mau="vang"), bang(COT_TRA, [row_tra(r) for r in vn30], note, list(range(1, 11))),
        doan("Kích hoạt, ERP cao nhất (25)", mau="vang"), bang(COT_TRA, [row_tra(r) for r in hi], note, list(range(1, 11))),
        doan("Kích hoạt nhưng ERP âm (bẫy định giá tiềm năng, 25)", mau="vang"), bang(COT_TRA, [row_tra(r) for r in lo], note, list(range(1, 11))),
        doan("Gõ mã ở ô trên thanh công cụ để mở trang chi tiết từng mã. Nút CSV xuất đủ 405 mã."),
    ], so="F", eyebrow="Bảng tra · EST")]


# ───────────────────────────── trang một mã ─────────────────────────────

def chart_pe(p):
    c = p["chuoi"]
    x = c["x"]
    i0 = next((i for i, v in enumerate(c["nguong"]) if v is not None), len(x))
    sl = slice(i0, len(x))
    xs = x[sl]
    cap = pe_cap(c["pe"][sl])
    clip = lambda arr: arr   # chỉ đặt trần TRỤC; dữ liệu giữ nguyên để tooltip đúng số
    block = {"x": xs, "left": {"label": "P/E (lần)", "min": 0, **({"max": cap} if cap else {})}, "series": [
        {"name": "P10–P90 250 phiên", "style": "band", "y_lo": clip(c["p10"][sl]), "y_hi": clip(c["p90"][sl]), "mau": "grey", "alpha": 0.10},
        {"name": "Vùng rẻ theo luật TV", "style": "band", "y_lo": [None] * len(xs), "y_hi": clip(c["pe_nguong"][sl]), "lo_min": True,
         "mau": "amber", "alpha": 0.22},
        {"name": "Trung vị 250 phiên", "y": clip(c["p50"][sl]), "style": "dash", "mau": "grey"},
        {"name": "P/E trailing", "y": clip(c["pe"][sl]), "style": "line", "mau": "ink"},
    ], "annotations": [], "_tran": cap}
    ann = block["annotations"]
    eps = [e for e in p["dot"] if e.get("pe") is not None and iso_ms(e["tu"]) and e["tu"] >= xs[0]] if xs else []
    for j, e in enumerate(eps):
        r = num(e.get("r60"))
        txt = vn(r, 0, True, "%") if r is not None else "đang chạy"
        ann.append({"kind": "point", "x": iso_ms(e["tu"]), "y": min(e["pe"], cap) if cap else e["pe"], "marker": "tri_up", "pos": "below",
                    "text": txt, "sub": ddmm(e["tu"], False) + "/" + e["tu"][2:4],
                    "mau": "bull" if (r or 0) > 0 else ("bear" if r is not None else "amber"),
                    "uu_tien": 2 if j >= len(eps) - 12 else 3,
                    "tip": f"Đợt {ddmm(e['tu'])}–{ddmm(e['den'])}: P/E {vn(e['pe'])} (P{vn(e['pct'], 0)} ≤ ngưỡng {vn(e['nguong'], 0)}), "
                           f"LS {vn(e['ls'])}% {e.get('huong_ls') or ''}; 60 phiên {vn(e.get('r60'), 1, True)}%, so cùng ngày {vn(e.get('xs60'), 1, True)}"})
    cur = p.get("hien_tai") or {}
    if cur.get("pe") is not None:
        ann.append({"kind": "point", "x": iso_ms(cur["ngay"]), "y": min(cur["pe"], cap) if cap else cur["pe"], "marker": "diamond", "pos": "above",
                    "text": f"P{vn(cur.get('pct'), 0)} · {vn(cur['pe'], 1)}x", "sub": f"ngưỡng P{vn(cur.get('nguong'), 0)}",
                    "mau": "amber", "uu_tien": 1})
    return block


def pe_cap(vals):
    """Trần trục P/E: đỉnh P/E khi lợi nhuận sụp (vd MWG 2023 ~400x) làm phần còn lại của biểu đồ dẹt.
    Trần = max(2 × trung vị, 1,3 × P90, 1,15 × P/E cao nhất 52 tuần gần nhất); None nếu không cần cắt."""
    v = sorted(x for x in vals if x is not None)
    if len(v) < 10:
        return None
    recent = [x for x in vals[-52:] if x is not None]
    med, p90 = v[len(v) // 2], v[int(len(v) * 0.9)]
    cap = max(2.0 * med, 1.3 * p90, 1.15 * max(recent) if recent else 0.0)
    return float(math.ceil(cap)) if cap < v[-1] else None


def chart_ey(p):
    c = p["chuoi"]
    pts = [(d, e, l) for d, e, l in zip(c["x"], c["ey"], c["ls"]) if l is not None]
    xs, ey, ls = [], [], []
    for k, (d, e, l) in enumerate(pts):
        if k and e is not None and ey and ey[-1] is not None:
            a0 = ey[-1] - ls[-1]
            a1 = e - l
            if a0 * a1 < 0:   # chèn điểm cắt để dải xanh/đỏ không hở
                t0, t1 = iso_ms(xs[-1]), iso_ms(d)
                f = a0 / (a0 - a1)
                tm = t0 + (t1 - t0) * f
                dm = datetime.fromtimestamp(tm / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                if xs[-1] < dm < d:
                    ym = ls[-1] + (l - ls[-1]) * f
                    xs.append(dm); ey.append(ym); ls.append(ym)
        xs.append(d); ey.append(e); ls.append(l)
    pos_lo = [l if (e is not None and e >= l) else None for e, l in zip(ey, ls)]
    pos_hi = [e if (e is not None and e >= l) else None for e, l in zip(ey, ls)]
    neg_lo = [e if (e is not None and e <= l) else None for e, l in zip(ey, ls)]
    neg_hi = [l if (e is not None and e <= l) else None for e, l in zip(ey, ls)]
    top = max([v for v in ey if v is not None] + [0.0])
    clip = ey   # không cắt dữ liệu; chỉ đặt trần trục 40%/năm khi EY vượt
    left = {"label": "%/năm", "min": 0}
    if top > 40.0:
        left["max"] = 40.0
    return {"x": xs, "left": left, "series": [
        {"name": "ERP dương (EY > LS)", "style": "band", "y_lo": pos_lo, "y_hi": pos_hi,
         "mau": "up", "alpha": 0.18},
        {"name": "ERP âm (EY < LS)", "style": "band", "y_lo": neg_lo, "y_hi": neg_hi, "mau": "down", "alpha": 0.18},
        {"name": "LS huy động >12T cao nhất", "y": ls, "style": "dash", "mau": "amber"},
        {"name": "EY = 100/P/E", "y": clip, "style": "line", "mau": "ink"},
    ]}


def chart_px(p):
    c = p["chuoi"]
    i0 = next((i for i, v in enumerate(c["ls"]) if v is not None), 0)
    xs = c["x"][i0:]
    block = {"x": xs, "left": {"label": "Giá điều chỉnh (VND)"},
             "series": [{"name": "Giá đóng cửa điều chỉnh (Bloomberg)", "y": c["px"][i0:], "style": "line", "mau": "ink"}],
             "annotations": []}
    ann = block["annotations"]
    eps = [e for e in p["dot"] if xs and e["tu"] >= xs[0]]
    for j, e in enumerate(eps):
        x0, x1 = iso_ms(e["tu"]), iso_ms(e["den"])
        if x1 == x0:
            x1 = x0 + 3 * 86400000
        r = num(e.get("r60"))
        ann.append({"kind": "xband", "x0": x0, "x1": x1, "alpha": 0.09, "mau": "amber", "uu_tien": 3,
                    "text": f"{ddmm(e['tu'])}–{ddmm(e['den'])} · {e['so_phien_tin_hieu']} phiên"})
        if e.get("px") is not None:
            ann.append({"kind": "point", "x": x0, "y": e["px"], "marker": "tri_up", "pos": "below",
                        "text": vn(r, 0, True, "%") if r is not None else "đang chạy",
                        "mau": "bull" if (r or 0) > 0 else ("bear" if r is not None else "amber"),
                        "uu_tien": 2 if j >= len(eps) - 10 else 3,
                        "tip": f"Mở đợt {ddmm(e['tu'])} giá {vn(e['px'], 0)} · 20/60/120 phiên: {vn(e.get('r20'), 1, True)} / "
                               f"{vn(e.get('r60'), 1, True)} / {vn(e.get('r120'), 1, True)}%"})
    return block


def bieu_do(tieu_de, block, chu_thich, nguon, tier, cao=340):
    return {"kieu": "bieu_do", "tieu_de": nfc(tieu_de), "chu_thich": nfc(chu_thich), "nguon": nfc(nguon), "tier": tier,
            "cao": cao, "block": block}


def ticker_page(p, t, cong):
    tk = p["ma"]
    cur = p.get("hien_tai") or {}
    prov = p.get("phien_do") or {}
    live = live_layer(p)
    dot = p["theo_dot"]
    head = f"{tk} · {p.get('ten') or ''}"
    sub = " · ".join(x for x in [p.get("san"), p.get("nganh"), p.get("nhom")] if x)
    huong = cur.get("huong_ls")
    k = t["kiem_dinh"]
    huong_pool = next((r for r in k["huong_ls"] if r["huong"] == huong), None)
    kh = cur.get("kich_hoat")
    kh_txt = "KÍCH HOẠT" if kh is True else ("KHÔNG" if kh is False else CAN)
    tiles = [
        tile(f"P/E · phiên {ddmm(cur.get('ngay'), False)}", (vn(cur.get('pe'), 2) + "x") if cur.get("pe") is not None else "",
             (f"EY {vn(cur.get('ey'), 2)}% · EPS ngầm {vn(cur.get('eps_ngam'), 0)}" if cur.get("pe") is not None else "Bloomberg không có P/E (lỗ hoặc thiếu)"),
             None, T_FACT),
        tile("Percentile 250 phiên", ("P" + vn(cur.get('pct'), 1)) if cur.get("pct") is not None else "",
             f"ngưỡng TV P{vn(cur.get('nguong'), 1)} (LS {vn(cur.get('ls'))}%)", None, T_EST),
        tile("Luật Toàn Vũ", kh_txt,
             (f"kích hoạt khi P/E < {vn(cur.get('pe_nguong'), 2)}x ↔ giá < {vn(cur.get('gia_nguong'), 0)}" if cur.get("pe_nguong")
              else ("không có P/E phiên này (lỗ hoặc thiếu)" if cur.get("pe") is None else "chưa đủ 60 phiên P/E")),
             "vang" if kh else "xam", T_EST),
        tile("ERP mã", (vn(cur.get('erp'), 2, True) + " điểm") if cur.get("erp") is not None else "",
             (f"EY {vn(cur.get('ey'), 2)}% − LS {vn(cur.get('ls'))}%" if cur.get("erp") is not None else f"LS {vn(cur.get('ls'))}%"),
             mau_sign(cur.get("erp"), 0.5), T_EST),
        tile("Hướng LS 6 tháng", (huong or "").upper() + (f" {vn(cur.get('dls6m'), 2, True)}" if cur.get("dls6m") is not None else ""),
             (f"toàn rổ khi kích hoạt ở hướng này: 60 phiên {vn(huong_pool['tin_hieu']['r60'], 2, True)}%, thắng {vn(huong_pool['tin_hieu']['hit'], 1)}%"
              if huong_pool else ""), "do" if huong and "tăng" in huong else ("xanh" if huong and "giảm" in huong else None), T_EST),
        tile("Mốc vào độc lập", f"{dot['n_do']} mốc · thắng {vn(dot['hit'], 0)}%" if dot["n_do"] else "0 mốc",
             (f"cách nhau ≥ 60 phiên · TB 60 phiên {vn(dot['r60_tb'], 1, True)}% · trung vị {vn(dot['r60_trung_vi'], 1, True)}% · "
              f"so cùng ngày {vn(dot['xs_tb'], 1, True)}") if dot["n_do"] else "chưa có lần kích hoạt nào đo được 60 phiên",
             mau_sign(dot.get("xs_tb"), 0.5), T_EST),
    ]
    if live:
        tiles.append(tile(f"P/E live · {ddmm(live['ngay'], False)}", vn(live["pe"], 2) + "x",
                          f"giá {vn(live['gia'], 0)} ÷ EPS ngầm Bloomberg · P{vn(live['pct'], 1)} · "
                          f"{'KÍCH HOẠT' if live['kich_hoat'] else 'không kích hoạt'} · ERP {vn(live['erp'], 2, True)}",
                          "vang" if live["kich_hoat"] else None, T_EST, live=True))
    elif prov.get("pe") is not None:
        tiles.append(tile(f"Phiên dở {ddmm(prov.get('ngay'), False)}", vn(prov["pe"], 2) + "x",
                          f"Bloomberg chụp giữa phiên · P{vn(prov.get('pct'), 1)}", None, T_FACT))
    sections = [sec("ma", head, [{"kieu": "o_so", "cot": 4, "o": tiles}] + [
        canh_bao("Lưu ý dữ liệu của mã", p.get("canh_bao") or [])], so="1", eyebrow=sub or "Mã", lede="")]

    # biểu đồ
    pe_block = chart_pe(p)
    sections.append(sec("bieu_do", "Vùng P/E, lợi suất so với tiền gửi, và các đợt kích hoạt", [
        bieu_do("P/E so với vùng rẻ theo luật TV", pe_block,
                "Dải cam: P/E ≤ giá trị tại percentile ngưỡng (ngưỡng đổi theo LS) của 250 phiên gần nhất. Dải xám: P10–P90. "
                "▲ = ngày mở đợt kích hoạt, nhãn = lợi suất 60 phiên sau đó. ◆ = hiện tại."
                + (f" Trục cắt ở {vn(pe_block.get('_tran'), 0)}x; tooltip vẫn đúng số." if pe_block.get("_tran") else ""),
                "Bloomberg PE_RATIO (tuần) · FiinProX LS · tính theo luật TV", "FACT-T2 EST", 380),
        bieu_do("EY so với lãi suất tiền gửi (ERP của mã)", chart_ey(p),
                "Xanh: EY > LS (cổ phiếu cho lợi suất cao hơn gửi tiết kiệm). Đỏ: EY < LS. Trục cắt ở 40%/năm khi EY vượt (tooltip vẫn đúng số).",
                "Bloomberg PE_RATIO · FiinProX LSHĐ >12T cao nhất", "FACT-T2 EST", 380),
        bieu_do("Giá và các đợt kích hoạt", chart_px(p),
                "Vùng cam: từ ngày mở tới ngày cuối của mỗi đợt kích hoạt. ▲ nhãn = lợi suất 60 phiên từ ngày mở đợt.",
                "Bloomberg PX_LAST điều chỉnh (tuần)", "FACT-T2 EST", 360),
    ], so="2", eyebrow="Biểu đồ"))

    # hiệu quả luật TV
    tvg, tl7, tl = p.get("tv_goc") or {}, p.get("tai_lap_0709") or {}, p.get("tai_lap") or {}
    rows = []
    if tvg.get("alpha60") is not None or tvg.get("hit60") is not None:
        rows.append([cell("Toàn Vũ in (07/09)", "tim", mono=False, dam=True), cell(vn(tvg.get("n"), 0)), cell(vn(tvg.get("hit60"), 1)),
                     cell(vn(tvg.get("ret60"), 1, True)), cell(vn(tvg.get("base60"), 1, True)), cell(vn(tvg.get("alpha60"), 2, True), mau_sign(tvg.get("alpha60"), 0.5)),
                     cell(T_TV, "tim", pill=True, mono=False)])
    rows.append([cell("Tái lập cắt 07/09", mono=False), cell(vn(tl7.get("n"), 0)), cell(vn(tl7.get("hit"), 1)), cell(vn(tl7.get("ret"), 2, True)),
                 cell(vn(tl7.get("base"), 2, True)), cell(vn(tl7.get("alpha"), 2, True), mau_sign(tl7.get("alpha"), 0.5)), cell(T_EST, "vang", pill=True, mono=False)])
    t45 = p.get("tai_lap_eps45") or {}
    if t45:
        rows.append([cell("Bỏ nhìn trước EPS 45 ngày · 60 phiên", mono=False, dam=True), cell(vn(t45.get("n"), 0)), cell(vn(t45.get("hit"), 1)),
                     cell(vn(t45.get("ret"), 2, True)), cell(vn(t45.get("base"), 2, True)),
                     cell(vn(t45.get("alpha"), 2, True), mau_sign(t45.get("alpha"), 0.5),
                          tip=f"So cùng ngày TB {vn(t45.get('xs'), 2, True)} điểm"), cell(T_EST, "vang", pill=True, mono=False)])
    for h in ("h20", "h60", "h120"):
        s = tl.get(h) or {}
        rows.append([cell(f"Tái lập đủ dữ liệu · {h[1:]} phiên", mono=False), cell(vn(s.get("n"), 0)), cell(vn(s.get("hit"), 1)),
                     cell(vn(s.get("ret"), 2, True)), cell(vn(s.get("base"), 2, True)), cell(vn(s.get("alpha"), 2, True), mau_sign(s.get("alpha"), 0.5)),
                     cell(T_EST, "vang", pill=True, mono=False)])
    lt = p.get("lai_tg") or {}
    pct_in = tvg.get("pct_hien_tai_in")
    nhan_xet = []
    if pct_in is not None:
        nhan_xet.append(f"Bản gốc in percentile \"hiện tại\" P{vn(pct_in, 1)}: đó là số ngày 07/09 (tái lập P{vn(tl7.get('pct_0709'), 1)}); "
                        f"phiên {ddmm(cur.get('ngay'))} là P{vn(cur.get('pct'), 1)}.")
    if tvg.get("top25_dang_tin_hieu"):
        nhan_xet.append("Mã nằm trong Top 25 \"đang có signal\" của bản gốc.")
    sections.append(sec("hieu_qua", "Luật Toàn Vũ đã hoạt động thế nào ở mã này", [
        doan(("Theo ngày (cách bản gốc đếm), mỗi ngày kích hoạt là một quan sát và các ngày liền nhau chồng cửa sổ 60 phiên. "
              + (f"Lấy mốc vào cách nhau từ 60 phiên trở lên để cửa sổ không chồng, mã có {dot['n_do']} mốc: thắng {vn(dot['hit'], 0)}%, "
                 f"TB {vn(dot['r60_tb'], 1, True)}%, trung vị {vn(dot['r60_trung_vi'], 1, True)}%, so cùng ngày {vn(dot['xs_tb'], 1, True)} điểm "
                 f"(p = {vn(dot.get('p_xs'), 2) or 'không đủ mẫu'}). " if dot["n_do"] else "Mã chưa có mốc kích hoạt nào đo được 60 phiên. ")
              + (f"{vn(lt.get('vuot_pct'), 0)}% ngày kích hoạt cho lợi suất 60 phiên vượt lãi tiền gửi cùng kỳ. " if lt.get("n") else "")
              + " ".join(nhan_xet))),
        bang(["Nguồn", "Ngày tín hiệu", "Thắng %", "TB khi kích hoạt", "TB mọi ngày", "Alpha", "Bậc"], rows,
             "Alpha = TB lợi suất khi kích hoạt − TB mọi ngày có LS (định nghĩa bản gốc). Lợi suất tính từ giá đóng cửa ngày kích hoạt. Dòng \"bỏ nhìn trước\" dời EPS 45 ngày vì Bloomberg ghi EPS quý vào ngày cuối quý, trước khi BCTC công bố.",
             [1, 2, 3, 4, 5]),
    ], so="3", eyebrow="Hiệu quả · EST"))

    # theo chế độ
    hr = [[cell(r["huong"], mono=False, dam=(r["huong"] == huong))] + stat_cells(r["tin_hieu"]) + stat_cells(r["moi_ngay"], with_n=False, xs=False)
          for r in p["theo_huong_ls"]]
    mr = [[cell(r["muc"], mono=False)] + stat_cells(r["tin_hieu"]) + stat_cells(r["moi_ngay"], with_n=False, xs=False) for r in p["theo_muc_ls"]]
    er = [[cell(r["erp"], mono=False)] + stat_cells(r["moi_ngay"]) + stat_cells(r["tin_hieu"]) for r in p["theo_erp"]]
    sections.append(sec("che_do", "Theo chế độ lãi suất và ERP", [
        bang(["Hướng LS 6 tháng", "Ngày tín hiệu", "TB 60", "Thắng %", "So cùng ngày", "Mọi ngày: TB 60", "Mọi ngày: thắng %"], hr,
             f"Dòng đậm = hướng hiện tại ({huong or CAN}). Ít ngày tín hiệu ở một hướng thì đọc như giai thoại.", [1, 2, 3, 4, 5, 6]),
        bang(["Mức LS", "Ngày tín hiệu", "TB 60", "Thắng %", "So cùng ngày", "Mọi ngày: TB 60", "Mọi ngày: thắng %"], mr, "", [1, 2, 3, 4, 5, 6]),
        bang(["ERP (điểm)", "Mọi ngày: n", "TB 60", "Thắng %", "So cùng ngày", "Kích hoạt: n", "TB 60", "Thắng %", "So cùng ngày"], er,
             "ERP = 100/P/E − LS. Ở cấp toàn rổ, ERP phân tầng lợi suất đều hơn percentile P/E và còn đứng sau khi bỏ nhìn trước (trang tổng, mục D).", list(range(1, 9))),
    ], so="4", eyebrow="Chế độ · EST"))

    # danh sách đợt
    dr = []
    for e in reversed(p["dot"][-40:]):
        dr.append([cell(f"{ddmm(e['tu'])}–{ddmm(e['den'])}"), cell(vn(e["so_phien_tin_hieu"], 0)), cell(vn(e.get("pe"), 2)),
                   cell(f"P{vn(e.get('pct'), 0)}/{vn(e.get('nguong'), 0)}"), cell(f"{vn(e.get('ls'))}% {e.get('huong_ls') or ''}", mono=False),
                   cell(vn(e.get("erp"), 1, True), mau_sign(e.get("erp"), 0.5)),
                   cell(vn(e.get("r20"), 1, True), mau_sign(e.get("r20"))), cell(vn(e.get("r60"), 1, True), mau_sign(e.get("r60")), dam=True),
                   cell(vn(e.get("r120"), 1, True), mau_sign(e.get("r120"))), cell(vn(e.get("xs60"), 1, True), mau_sign(e.get("xs60"), 0.5)),
                   cell("vượt" if e.get("vuot_lai_tg") else ("thua" if e.get("vuot_lai_tg") is False else ""), mono=False),
                   cell("thủng" if e.get("day52") else ("sát" if e.get("sat52") else ""), mono=False)])
    sections.append(sec("dot", f"Các đợt kích hoạt ({len(p['dot'])})", [
        bang(["Đợt", "Phiên", "P/E mở", "Pct/ngưỡng", "LS · hướng", "ERP", "20 phiên %", "60 phiên %", "120 phiên %", "So cùng ngày", "Tiền gửi", "Đáy 52T"],
             dr, "Mới nhất ở trên, tối đa 40 đợt. Ô trống = chưa đủ phiên để đo. Tiền gửi: lợi suất 60 phiên so với LS × 60/250. EST.",
             [1, 2, 6, 7, 8, 9]) if dr else doan("Mã chưa có đợt kích hoạt nào kể từ khi có LS (03/2008)."),
    ], so="5", eyebrow="Lịch sử · EST"))

    du = p.get("du_lieu") or {}
    sections.append(sec("nguon", "Nguồn và giới hạn", [
        chips([(T_FACT, f"Bloomberg {ddmm(du.get('tu'))}→{ddmm(du.get('den'))}, P/E từ {ddmm(du.get('pe_tu'))}"),
               (T_FACT, f"FiinProX LS tới {ddmm(t['nguon']['fiinprox']['moi_nhat']['ngay'])}"),
               (T_TV, "luật + số in ngày 06/10/2026"), (T_EST, "tái lập & kiểm định Hội đồng")]),
        canh_bao("Giới hạn", [
            "Bộ mã là 405 thành viên VNINDEX hiện tại: mã đã huỷ niêm yết không có mặt (thiên lệch sống sót, làm đẹp tín hiệu \"rẻ\").",
            "P/E trailing Bloomberg chỉ có khi lãi dương; EPS đổi khi có BCTC mới. P/E live = giá vnstore ÷ EPS ngầm định phiên đủ cuối: "
            "sai khi BCTC quý 3 công bố (cuối tháng 10).",
            f"LS FiinProX dừng ở {ddmm(t['nguon']['fiinprox']['moi_nhat']['ngay'])}; các phiên sau giữ nguyên giá trị cuối.",
            "Lợi suất không trừ phí, thuế, trượt giá; không tính cổ tức tiền ngoài phần đã điều chỉnh trong PX_LAST.",
        ], mau="xam"),
    ], so="6", eyebrow="Nguồn"))
    return sections


# ───────────────────────────── lắp trang ─────────────────────────────

def ds_ma(t):
    ro = [{"ma": c, "ten": n} for c, n in (("VNINDEX", "trang rổ · 405 mã"), ("VN30", "trang rổ · 30 mã"), ("VN100", "trang rổ · 100 mã"),
                                            ("VN200", "trang rổ · top 200 vốn hoá"), ("REST", "trang rổ · mã Bloomberg ngoài VN200"))
          if (STATE / "ro" / f"{c}.json").exists()]
    return ro + [{"ma": r["ma"], "ten": r.get("ten") or ""} for r in t["bang"]]


def csv_payload(t):
    cols = ["ma", "ten", "nhom", "nganh", "pe", "pct", "nguong", "kich_hoat", "ey", "erp", "day52", "sat52",
            "n_ngay", "hit_ngay", "alpha_tv", "n_dot", "hit_dot", "xs_dot", "p_dot", "alpha_tv_goc"]
    rows = [[("" if r.get(c) is None else r.get(c)) for c in cols] for r in t["bang"]]
    return {"columns": cols, "rows": rows}


def meta(t, extra_warn=None):
    w = []
    if t.get("phien_do"):
        pd_ = t["phien_do"]
        w.append(f"Phiên {ddmm(pd_['ngay'])} trong file Bloomberg là ảnh chụp giữa phiên ({pd_['so_ma_co_pe']}/{pd_['phien_truoc']} mã có P/E): "
                 f"trạng thái dùng phiên đủ {ddmm(t['phien_du_cuoi'])}.")
    w.append(f"LS FiinProX dừng ở {ddmm(t['nguon']['fiinprox']['moi_nhat']['ngay'])}; cập nhật khi có file mới (chạy toanvu_pe_build.py).")
    if extra_warn:
        w += extra_warn
    try:
        age = (datetime.now() - datetime.strptime(t["phien_du_cuoi"], "%Y-%m-%d")).days
    except (ValueError, KeyError):
        age = None
    return {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "script_version": VERSION, "build": t.get("tao_luc"),
            "data_to": t.get("phien_du_cuoi"), "age_days": age, "stale": bool(age is not None and age > 10),
            "stale_text": f"dữ liệu Bloomberg {age} ngày tuổi" if age is not None and age > 10 else "",
            "warnings": w, "ls": t.get("ls_hien_tai"), "nguong": t.get("nguong_hien_tai")}


def build_overview():
    t = load_tong()
    cong = read_cong()
    secs = [sec("cong", "Vùng P/E × Lãi suất · phương pháp Toàn Vũ", [block_cong(cong)], eyebrow="HĐCV chứng khoán v1.7")]
    try:
        import toanvu_pe_trang as tr0
        secs += tr0.doc_hieu_sections(sys.modules[__name__], "HPG")
    except Exception:  # noqa: BLE001
        pass
    secs.append(sec("pp", "Phương pháp luận Toàn Vũ (bản đầy đủ)", method_full(t), so="0c", eyebrow="SS-T3 · trao đổi và 2 báo cáo 06/10/2026",
                    lede="Đọc phần này trước bảng số. Mọi con số ở mục A–F là tái lập và kiểm định của Hội đồng trên đúng dữ liệu anh gửi, đã qua một vòng kiểm định đối kháng độc lập."))
    secs += audit_sections(t)
    secs += overview_tables(t, cong)
    return {"meta": {**meta(t), "che_do": "overview", "ds_ma": ds_ma(t)},
            "trang": {"schema": "vnblocks/1", "tieu_de": "Vùng P/E × Lãi suất · Toàn Vũ", "sections": secs},
            "csv": csv_payload(t)}


def build_scope(code):
    import toanvu_pe_trang as tr
    t = load_tong()
    d, secs = tr.scope_page(sys.modules[__name__], code)
    m = meta(t)
    m.update({"che_do": "ro", "ma": code, "ds_ma": ds_ma(t)})
    return {"meta": m, "trang": {"schema": "vnblocks/1", "tieu_de": f"{code} · P/E × Lãi suất × ERP", "sections": secs},
            "csv": csv_payload(t)}


def build_ma(tk):
    tk = (tk or "").strip().upper()
    if not tk or not tk.isalnum() or len(tk) > 10:
        raise TvError("BAD_TICKER", f"Mã không hợp lệ: {tk!r}")
    if tk in SCOPES:
        return build_scope(tk)
    t = load_tong()
    p = load_ma(tk)
    cong = read_cong()
    secs = [sec("cong", f"{tk} · Vùng P/E × Lãi suất", [block_cong(cong)], eyebrow="HĐCV chứng khoán v1.7")]
    try:
        import toanvu_pe_trang as tr0
        secs += tr0.doc_hieu_sections(sys.modules[__name__], tk, p.get("hien_tai") or {})
    except Exception:  # noqa: BLE001
        pass
    secs.append(sec("pp", "Chi tiết phương pháp và kiểm định", method_compact(t), so="0c", eyebrow="Cho người muốn đào sâu"))
    secs += ticker_page(p, t, cong)
    try:
        import toanvu_pe_trang as tr
        secs += tr.deep_sections(sys.modules[__name__], tk, p)
    except TvError:
        raise
    except Exception as exc:  # noqa: BLE001, lớp sâu hỏng không được làm mất trang chính
        secs.append(sec("sau", "Lớp phân tích sâu", [canh_bao("Không dựng được lớp sâu", [f"{type(exc).__name__}: {exc}"], "do")], so="9"))
    try:
        secs = tr.apply_guides(sys.modules[__name__], secs)
    except Exception:  # noqa: BLE001
        pass
    m = meta(t)
    m.update({"che_do": "ma", "ma": tk, "ds_ma": ds_ma(t)})
    return {"meta": m, "trang": {"schema": "vnblocks/1", "tieu_de": f"{tk} · Vùng P/E × Lãi suất", "sections": secs},
            "csv": csv_payload(t)}


def run(argv):
    if len(argv) < 2:
        raise TvError("USAGE", USAGE)
    cmd = argv[1]
    if cmd == "overview":
        return build_overview()
    if cmd == "ma":
        if len(argv) == 4 and argv[2] == "--ma":
            return build_ma(argv[3])
        raise TvError("USAGE", USAGE)
    raise TvError("USAGE", USAGE)


_GACH_DAI = {0x2014: "-", 0x2015: "-"}   # chữ từ nguồn ngoài (nhãn rổ HHP, ghi chú TPCP…) có thể mang gạch dài


def clean(o):
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, str):
        return o.translate(_GACH_DAI)
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
    try:
        emit(run(argv))
    except TvError as exc:
        emit({"error": exc.message, "error_code": exc.code})
    except Exception as exc:  # noqa: BLE001, luôn trả JSON cho panel
        emit({"error": f"Lỗi nội bộ toanvu_pe.py: {type(exc).__name__}: {exc}", "error_code": "INTERNAL"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
