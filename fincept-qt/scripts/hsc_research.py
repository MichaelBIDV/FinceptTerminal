#!/usr/bin/env python3
"""hsc_research.py — tab "HSC RESEARCH" của Fincept Terminal (trang vnblocks/1, xem VnBlocks.h).

Đọc (chỉ đọc, không mạng) kho HSC Research theo ngày mà pipeline 12:30 T2–T6 ghi ở
~/SECOND BRAIN-OBSIDIAN/_System/hsc_research/ (lược đồ: README.md của thư mục đó):
    kho/<YYYY-MM-DD>.jsonl        SỰ THẬT (SS-T3) — dòng đầu là lô, mỗi dòng sau một báo cáo
    phan_tich/<YYYY-MM-DD>.json   Ý KIẾN Hội đồng (EST) — chỉ có ở những lô đã viết
    chuoi.json                    chuỗi dựng lại từ kho (hsc_kho.py chuoi)
Không sửa tệp nào. Không tự suy số: mọi con số lấy nguyên từ kho/chuỗi/phân tích; thiếu → [CẦN DATA].
Chuỗi được CẮT tại ngày lô đang xem (--ngay), nên xem lại lô cũ thấy đúng những gì biết được hôm đó.

USAGE
    python3 hsc_research.py overview [--ngay YYYY-MM-DD]     # mặc định: lô mới nhất

OUTPUT — đúng MỘT đối tượng JSON trên stdout, exit 0 kể cả khi lỗi:
    {"meta": {generated, data_to, lo, ky_list: [{ngay, nhan}], stale, stale_text, age_days, warnings,
              index_url, lo_file},
     "trang": {"sections": [...]},  "csv": {"columns", "rows"}}
    lỗi: {"error": "<thông điệp tiếng Việt kèm việc cần làm>"}

Biến môi trường (dùng cho test): HSC_GOC (thư mục kho), HSC_TODAY (YYYY-MM-DD, cố định "hôm nay").
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ICT = timezone(timedelta(hours=7))
CAN = "[CẦN DATA]"
MINUS = "−"
GOC = Path(os.environ.get("HSC_GOC") or Path.home() / "SECOND BRAIN-OBSIDIAN" / "_System" / "hsc_research")
INDEX_URL = "http://localhost:9000/sys/hsc_research/index.html"
STALE_DAYS = 4          # lô mới nhất cũ hơn ngần này ngày lịch → cảnh báo (cuối tuần + 1 phiên)
CU_NGAY = 90            # TP quá 90 ngày = cũ (cùng luật với hsc_kho.CU_NGAY)

NHOM = [("ngay", "Báo cáo ngày"), ("tuan", "Báo cáo tuần"), ("chien_luoc", "Chiến lược"),
        ("vi_mo", "Vĩ mô"), ("nganh", "Ngành"), ("doanh_nghiep", "Doanh nghiệp"), ("su_kien", "Sự kiện")]
NHOM_TEN = dict(NHOM)
CHUAN = {"MUA": "Mua", "TANG": "Tăng TT", "GIU": "Nắm giữ", "GIAM": "Giảm TT", "BAN": "Bán",
         "XEM_XET": "Đang xem xét", "KHONG": "Không đánh giá"}
CHUAN_MAU = {"MUA": "xanh", "TANG": "xanh", "GIU": "vang", "GIAM": "do", "BAN": "do"}
DOI_MAU = {"NÂNG": "xanh", "HẠ": "do", "MỚI": "lam"}
PHIEU_MAU = (("KHÔNG", "do"), ("CHỜ", "vang"), ("CÓ", "xanh"))
RIGOR = [("nguon", "Nguồn"), ("logic", "Logic"), ("mat_do", "Mật độ bằng chứng"),
         ("phu_dinh", "Phủ định được"), ("phan_chung", "Phản chứng"), ("hieu_chinh", "Hiệu chỉnh")]
T_KHO, T_HD = "SS-T3", "EST"


class HscError(Exception):
    pass


# ───────────────────────────── định dạng ─────────────────────────────

def so(v, nd=0):
    """Số kiểu Việt: phẩy thập phân, chấm nghìn, dấu trừ U+2212. Không phải số → [CẦN DATA]."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return CAN
    s = f"{abs(v):,.{nd}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if nd and "," in s:
        s = s.rstrip("0").rstrip(",")
    return (MINUS + s) if v < 0 and s != "0" else s


def pct(v, nd=1):
    t = so(v, nd)
    return t if t == CAN else (("+" if v > 0 else "") + t + "%")


def ddmm(iso):
    d = _ngay(iso)
    return d.strftime("%d/%m") if d else (iso or CAN)


def ddmmyyyy(iso):
    d = _ngay(iso)
    return d.strftime("%d/%m/%Y") if d else (iso or CAN)


def _ngay(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def cell(t, mau=None, **kw):
    c = {"t": t if t not in (None, "") else CAN}
    if mau:
        c["mau"] = mau
    c.update({k: v for k, v in kw.items() if v})
    return c


def sec(sid, so_, tieu_de, eyebrow, khoi, lede=""):
    return {"id": sid, "so": so_, "tieu_de": tieu_de, "eyebrow": eyebrow, "lede": lede, "khoi": khoi}


def doan(text, mau=None, the=False, tieu_de=None):
    b = {"kieu": "doan", "text": text}
    if mau:
        b["mau"] = mau
    if the:
        b["the"] = True
        if tieu_de:
            b["tieu_de"] = tieu_de
    return b


def ds(muc, tier=None):
    return {"kieu": "danh_sach", "muc": [{"so": str(i), "tieu_de": "", "text": t, "tags": [tier] if tier else []}
                                         for i, t in enumerate(muc, 1) if isinstance(t, str) and t.strip()]}


def _hoac(v):
    """Trường tuỳ chọn báo cáo không in: gạch ngang thay vì [CẦN DATA]."""
    return "—" if v is None else so(v)


def hang_txt(k):
    c = k.get("chuan")
    return CHUAN.get(c, k.get("xep_hang") or CAN)


# ───────────────────────────── đọc kho ─────────────────────────────

def doc_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as ex:
        raise HscError(f"Không đọc được {p.name}: {ex}. Chạy lại: python3 hsc_kho.py tat_ca trong {GOC}")


def doc_lo(p):
    lo, bcs = {}, []
    for i, x in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not x.strip():
            continue
        try:
            d = json.loads(x)
        except ValueError as ex:
            raise HscError(f"{p.name} dòng {i} không phải JSON ({ex}). Chạy: python3 hsc_kho.py kiem {p.name}")
        if d.get("dong") == "lo":
            lo = d
        elif d.get("dong") == "bc":
            bcs.append(d)
    return lo, bcs


def cac_lo():
    kho = GOC / "kho"
    if not kho.is_dir():
        raise HscError(f"Chưa có kho HSC Research ở {kho}. Pipeline 12:30 T2–T6 chưa chạy lần nào, "
                       "hoặc kho bị chuyển chỗ (đặt biến HSC_GOC).")
    out = sorted(p.stem for p in kho.glob("*.jsonl") if _ngay(p.stem))
    if not out:
        raise HscError(f"Kho {kho} chưa có lô nào (kho/<YYYY-MM-DD>.jsonl).")
    return out


# ───────────────────────────── các mục ─────────────────────────────

def muc_cong(pt):
    cong = (pt or {}).get("cong")
    if isinstance(cong, str) and cong.strip():
        return sec("cong", "", "Cổng", "HĐCV chứng khoán v1.7",
                   [{"kieu": "cong", "dong": cong.strip(), "tier": T_HD, "phu": "ghi trong bản Hội đồng của lô"}])
    return sec("cong", "", "Cổng", "HĐCV chứng khoán v1.7", [{
        "kieu": "cong", "tier": "UNVERIFIED",
        "dong": "CỔNG: [CẦN DATA] · chủ thể [CẦN DATA] · playbook [CẦN DATA]",
        "phu": ("Bản Hội đồng của lô này không ghi dòng CỔNG (chu kỳ tiền đắt/rẻ). Phần ý kiến bên dưới "
                "chỉ để đọc, chưa dùng cho quyết định." if pt else
                "Lô này chưa có bản Hội đồng — trang chỉ có sự thật từ kho HSC (SS-T3).")}])


def muc_lo(lo_hdr, bcs, ngay, ngay_info, ids_kho):
    chinh = [b for b in bcs if b.get("ban_dich_cua") not in ids_kho and b.get("ban_sao_cua") not in ids_kho]
    phu = len(bcs) - len(chinh)
    nhom_dem = {}
    for b in bcs:
        nhom_dem[b.get("nhom")] = nhom_dem.get(b.get("nhom"), 0) + 1
    kn = [k for b in chinh for k in b.get("khuyen_nghi") or []]
    info = ngay_info or {}
    tiles = [
        {"nhan": "Báo cáo trong lô", "gia_tri": so(len(bcs)),
         "phu": f"{len(chinh)} bản chính · {phu} bản dịch/sao" if phu else f"{len(chinh)} bản chính", "tier": T_KHO},
        {"nhan": "Mã có hạng", "gia_tri": so(len({k.get('ma') for k in kn})),
         "phu": ", ".join(sorted({k.get("ma") for k in kn if k.get("ma")})) or "—", "tier": T_KHO},
        {"nhan": "Nâng hạng", "gia_tri": so(len(info.get("nang") or [])), "phu": ", ".join(info.get("nang") or []) or "—",
         "mau": "xanh" if info.get("nang") else None, "tier": T_KHO},
        {"nhan": "Hạ hạng", "gia_tri": so(len(info.get("ha") or [])), "phu": ", ".join(info.get("ha") or []) or "—",
         "mau": "do" if info.get("ha") else None, "tier": T_KHO},
        {"nhan": "Lên Drive lúc", "gia_tri": (lo_hdr.get("tai_len_luc") or "")[11:16] or CAN,
         "phu": f"{lo_hdr.get('ten_lo') or ''} · {so(lo_hdr.get('so_tep'))} tệp", "tier": T_KHO},
        {"nhan": "Theo nhóm", "gia_tri": so(len(nhom_dem)),
         "phu": " · ".join(f"{NHOM_TEN.get(k, k)} {v}" for k, v in sorted(nhom_dem.items(), key=lambda kv: -kv[1])),
         "tier": T_KHO},
    ]
    khoi = [{"kieu": "o_so", "o": tiles, "cot": 3}]

    dong = []
    for key, ten in NHOM:
        for b in [x for x in bcs if x.get("nhom") == key]:
            ks = b.get("khuyen_nghi") or []
            hang = "; ".join(f"{k.get('ma')} {hang_txt(k)} · TP {so(k.get('muc_tieu'))} ({pct(k.get('upside'))})"
                             for k in ks)
            ban_phu = b.get("ban_dich_cua") in ids_kho or b.get("ban_sao_cua") in ids_kho
            dong.append([cell(ten, pill=True), cell(b.get("hsc_loai")),
                         cell(b.get("tieu_de"), dam=True, tip=b.get("link")),
                         cell(", ".join(b.get("ma") or []) or "—", mono=True),
                         cell(hang or "—", CHUAN_MAU.get(ks[0].get("chuan")) if ks else None),
                         cell((("[bản dịch] " if ban_phu else "") + (b.get("tom_tat") or "")) or CAN,
                              "xam" if ban_phu else None)])
    khoi.append({"kieu": "bang", "cot": ["Nhóm", "Loại (bìa HSC)", "Báo cáo", "Mã", "Hạng · TP · upside", "Tóm tắt"],
                 "dong": dong, "chu_thich": "Rê chuột lên tên báo cáo để xem đường dẫn Drive. Mọi số: HSC (SS-T3)."})

    for key, ten in NHOM:
        nhom_bc = [b for b in chinh if b.get("nhom") == key]
        if not nhom_bc:
            continue
        khoi.append(doan(f"{ten} · {len(nhom_bc)} báo cáo", mau="lam"))
        cards = []
        for b in nhom_bc:
            y = [t for t in b.get("y_chinh") or [] if isinstance(t, str)]
            text = (b.get("tom_tat") or "") + ("\n\n" if y else "") + "\n".join("• " + t for t in y)
            ma = ", ".join(b.get("ma") or [])
            cards.append({"tieu_de": (ma + " · " if ma else "") + (b.get("tieu_de") or CAN),
                          "nhan": {"text": f"{b.get('hsc_loai') or ''} · {(b.get('ngon_ngu') or '').upper()} · "
                                           f"{ddmm(b.get('ngay_bc'))}", "mau": "xam"},
                          "text": text or CAN, "tier": T_KHO})
        khoi.append({"kieu": "the", "the": cards, "cot": 2})

    bq = lo_hdr.get("bo_qua") or []
    if bq:
        khoi.append({"kieu": "canh_bao", "tieu_de": "Tệp trong thư mục Drive cố ý không nạp", "mau": "vang",
                     "muc": [f"{x.get('tep')}: {x.get('ly_do')}" for x in bq]})
    return sec("lo", "I", f"Lô {ddmmyyyy(ngay)}", "Báo cáo HSC trong ngày · 7 nhóm", khoi,
               "Sự thật trích từ báo cáo HSC (bậc SS-T3). Cặp EN/VI của cùng một báo cáo chỉ tính một lần.")


def _phieu_mau(p):
    p = (p or "").upper()
    for k, m in PHIEU_MAU:
        if p.startswith(k):
            return m
    return "xam"


def muc_hoi_dong(pt, ngay):
    if not pt:
        return sec("hoi_dong", "II", "Hội đồng", "Kill zone trước · Alpha zone sau",
                   [doan(f"Lô {ddmm(ngay)} chưa có bản Hội đồng (phan_tich/{ngay}.json). Bản Hội đồng chỉ viết cho "
                         "lô mới nhất của mỗi lượt chạy 12:30; lô cũ chỉ có trang sự thật.", the=True)])
    khoi = []
    if pt.get("tieu_de"):
        khoi.append(doan(pt["tieu_de"], mau="vang", the=True, tieu_de="Kết luận của ngày"))
    if pt.get("keynotes"):
        khoi += [doan("Keynotes", mau="lam"), ds(pt["keynotes"], T_HD)]
    if pt.get("chuoi_nhan_dinh"):
        khoi += [doan("Chuỗi nhận định của HSC", mau="lam"), doan(pt["chuoi_nhan_dinh"])]
    for key, ten in (("thi_truong", "Thị trường"), ("vi_mo", "Vĩ mô"), ("su_kien", "Sự kiện")):
        if pt.get(key):
            khoi += [doan(ten, mau="lam"), ds(pt[key])]

    skn = [x for x in pt.get("soi_khuyen_nghi") or [] if isinstance(x, dict)]
    if skn:
        lg_mau = {0: "xanh", 1: "vang", 2: "do", 3: "do"}
        khoi += [doan("Soi khuyến nghị", mau="lam"), {
            "kieu": "bang", "cot": ["Mã", "HSC nói", "Đọc ngược", "Lùa gà", "Liên quan danh mục", "Hành động"],
            "dong": [[cell(x.get("ma"), mono=True, dam=True), cell(x.get("hsc")), cell(x.get("doc_nguoc")),
                      cell(so(x.get("lua_ga")) + "/3", lg_mau.get(x.get("lua_ga")), pill=True),
                      cell(x.get("lien_quan")), cell(x.get("hanh_dong"), dam=True)] for x in skn],
            "chu_thich": "Lùa gà 0 sạch · 1 lưu ý · 2 nghi (upside lớn + một nguồn + lệch consensus) · 3 nghịch đảo.",
            "can_phai": [3]}]
    dm = [x for x in pt.get("danh_muc") or [] if isinstance(x, dict)]
    if dm:
        khoi += [doan("Tác động lên danh mục", mau="lam"), {
            "kieu": "bang", "cot": ["Mã", "Tác động", "Hành động", "Điều kiện phủ định"],
            "dong": [[cell(x.get("ma"), mono=True, dam=True), cell(x.get("tac_dong")),
                      cell(x.get("hanh_dong"), dam=True), cell(x.get("phu_dinh"))] for x in dm]}]

    hd = pt.get("hoi_dong") or {}
    for key, ten in (("kill_zone", "Kill zone (nói trước)"), ("alpha_zone", "Alpha zone (nói sau)")):
        tv = [x for x in hd.get(key) or [] if isinstance(x, dict)]
        if tv:
            khoi += [doan(ten, mau="lam"), {"kieu": "the", "cot": 3, "the": [
                {"tieu_de": x.get("ten") or CAN, "nhan": {"text": x.get("phieu") or CAN, "mau": _phieu_mau(x.get("phieu"))},
                 "text": x.get("y_kien") or CAN, "mau_vien": _phieu_mau(x.get("phieu")), "tier": T_HD} for x in tv]}]
    if hd.get("tong_hop"):
        khoi.append({"kieu": "trich", "text": hd["tong_hop"], "nguon": "Tổng hợp Hội đồng · EST"})
    if pt.get("pre_mortem"):
        khoi.append({"kieu": "canh_bao", "tieu_de": "Pre-mortem — 18 tháng sau −30%, cái gì đã giết luận điểm?",
                     "mau": "do", "muc": [t for t in pt["pre_mortem"] if isinstance(t, str)]})
    rg = pt.get("rigor") or {}
    if any(isinstance(rg.get(k), (int, float)) for k, _ in RIGOR):
        tong = sum(rg.get(k) for k, _ in RIGOR if isinstance(rg.get(k), (int, float)))
        o = [{"nhan": ten, "gia_tri": f"{so(rg.get(k))}/5", "mau": ("do" if isinstance(rg.get(k), (int, float))
                                                                       and rg.get(k) <= 2 else None), "tier": T_HD}
             for k, ten in RIGOR]
        khoi += [doan(f"Rigor 6D · {so(tong)}/30", mau="lam"), {"kieu": "o_so", "o": o, "cot": 6}]
        if rg.get("ghi_chu"):
            khoi.append(doan(rg["ghi_chu"]))
    if pt.get("viec_treo"):
        khoi += [doan("Việc treo", mau="lam"), ds(pt["viec_treo"])]
    return sec("hoi_dong", "II", "Hội đồng", f"Bản viết {ddmmyyyy(pt.get('viet_luc'))} "
               f"{(pt.get('viet_luc') or '')[11:16]} · Kill zone trước · Alpha zone sau", khoi,
               "Ý kiến (EST) trên nền số HSC (SS-T3). Một nguồn sell-side duy nhất → mọi kết luận về mã đã hạ một bậc.")


def muc_khuyen_nghi(c, ngay, ma_lo, today):
    rows, csv = [], []
    for ma, lich in (c.get("khuyen_nghi") or {}).items():
        lich = [x for x in lich if (x.get("lo") or "") <= ngay]
        if not lich:
            continue
        x = lich[-1]
        cu = (today - (_ngay(x.get("ngay_bc")) or today)).days > CU_NGAY
        rows.append((ma, x, lich, cu))
    rows.sort(key=lambda r: (r[3], -(r[1].get("upside") if isinstance(r[1].get("upside"), (int, float)) else -999)))
    dm = {m.get("ma"): m.get("danh_muc") for m in c.get("moi_nhat") or []}
    dong = []
    for ma, x, lich, cu in rows:
        moi = ma in ma_lo
        tp0 = lich[0].get("muc_tieu")
        tp_hanh_trinh = " → ".join(so(y.get("muc_tieu")) for y in lich[-4:])
        dong.append([cell(ma, "xam" if cu else None, mono=True, dam=moi),
                     cell(dm.get(ma) or "—", "lam" if dm.get(ma) == "NẮM" else ("do" if dm.get(ma) == "TRÁNH" else None),
                          pill=bool(dm.get(ma))),
                     cell(hang_txt(x), CHUAN_MAU.get(x.get("chuan")), pill=True),
                     cell(so(x.get("muc_tieu")), mono=True), cell(f"{so(x.get('gia'))} ({ddmm(x.get('ngay_gia'))})", mono=True),
                     cell(pct(x.get("upside")), "xanh" if (x.get("upside") or 0) >= 30 else None, mono=True),
                     cell(x.get("doi_hang"), DOI_MAU.get(x.get("doi_hang"))),
                     cell(pct(x.get("doi_tp_pct")) if x.get("doi_tp_pct") is not None else "—", mono=True),
                     cell(f"{len(lich)} lần · {tp_hanh_trinh}", mono=True, tip=f"TP đầu {so(tp0)} ({ddmm(lich[0].get('ngay_bc'))})"),
                     cell(f"{ddmm(x.get('ngay_bc'))} · {x.get('tieu_de') or ''}", "xam" if cu else None, tip=x.get("link"))])
        csv.append([ma, dm.get(ma) or "", x.get("chuan"), x.get("muc_tieu"), x.get("gia"), x.get("ngay_gia"),
                    x.get("upside"), x.get("doi_hang"), x.get("doi_tp_pct"), len(lich), x.get("ngay_bc"), x.get("tieu_de"),
                    x.get("link")])
    tren30 = sum(1 for _, x, _, cu in rows if not cu and (x.get("upside") or 0) >= 30)
    khoi = [{"kieu": "o_so", "cot": 4, "o": [
        {"nhan": "Mã có khuyến nghị", "gia_tri": so(len(rows)), "phu": f"cắt tại lô {ddmm(ngay)}", "tier": T_KHO},
        {"nhan": "Upside ≥ 30%", "gia_tri": so(tren30), "phu": "ngưỡng giải ngân của Hội đồng (chỉ ở phase 3)", "tier": T_KHO},
        {"nhan": "Mã của lô này", "gia_tri": so(len(ma_lo)), "phu": ", ".join(sorted(ma_lo)) or "—", "tier": T_KHO},
        {"nhan": "TP cũ > 90 ngày", "gia_tri": so(sum(1 for r in rows if r[3])), "phu": "tô xám, xếp cuối", "tier": T_KHO}]},
        {"kieu": "bang", "cot": ["Mã", "DM", "Hạng", "TP", "Giá (ngày giá)", "Upside", "Đổi hạng", "Đổi TP",
                                 "Hành trình TP (4 lần cuối)", "Báo cáo gần nhất"],
         "dong": dong, "can_phai": [3, 4, 5, 7],
         "chu_thich": "Mã in đậm = có trong lô đang xem. DM: NẮM = danh mục, TRÁNH = danh sách tránh. Bản dịch và "
                      "báo cáo nhắc lại cùng hạng+TP+giá+ngày giá đã gộp."}]
    return sec("khuyen_nghi", "III", "Chuỗi khuyến nghị theo mã", "Hạng và giá mục tiêu HSC qua các lần", khoi), csv


def _chart(tieu_de, chu_thich, x, series, left, cao=260, right=None):
    block = {"x": x, "series": series, "left": {"label": left}}
    if right:
        block["right"] = {"label": right}
    return {"kieu": "bieu_do", "tieu_de": tieu_de, "chu_thich": chu_thich, "nguon": "HSC Morning Take / Weekly Note",
            "tier": T_KHO, "cao": cao, "block": block}


def muc_thi_truong(c, ngay):
    tt = [t for t in c.get("thi_truong") or [] if (t.get("ngay_bc") or t.get("ngay_phien") or "") <= ngay]
    tu = [t for t in c.get("thi_truong_tuan") or [] if (t.get("ngay_bc") or t.get("ngay_phien") or "") <= ngay]
    khoi = []
    diem = [t for t in tt if isinstance(t.get("vnindex"), (int, float))]
    if len(diem) >= 2:
        khoi.append(_chart("VN-Index theo phiên (số HSC in trong Morning Take)", "Mỗi điểm là phiên mà một báo cáo ngày của "
                           "HSC nhận định; phiên không có báo cáo thì không có điểm.",
                           [t["ngay_phien"] for t in diem], [{"name": "VN-Index", "y": [t["vnindex"] for t in diem],
                                                              "style": "line", "mau": "amber"}], "điểm"))
    nn = [t for t in tt if isinstance(t.get("nn_rong_ty"), (int, float))]
    if len(nn) >= 2:
        khoi.append(_chart("Khối ngoại ròng theo phiên", "Cột = mua/bán ròng phiên (tỷ đồng, âm = bán ròng); đường = lũy kế "
                           "từ đầu năm (nghìn tỷ, trục phải).",
                           [t["ngay_phien"] for t in nn],
                           [{"name": "Ròng phiên (tỷ)", "y": [t["nn_rong_ty"] for t in nn], "style": "bar", "mau": "info"},
                            {"name": "Lũy kế YTD (nghìn tỷ)", "axis": "right", "style": "line", "mau": "bear",
                             "y": [(t["nn_rong_ytd_ty"] / 1000.0) if isinstance(t.get("nn_rong_ytd_ty"), (int, float))
                                   else None for t in nn]}], "tỷ đồng", right="nghìn tỷ"))
    dong = []
    for t in reversed(tt[-12:]):
        mocs = []
        if t.get("ho_tro"):
            mocs.append("HT " + ", ".join(so(v) for v in t["ho_tro"]))
        if t.get("khang_cu"):
            mocs.append("KC " + ", ".join(so(v) for v in t["khang_cu"]))
        dong.append([cell(ddmm(t.get("ngay_phien")) + (" *" if t.get("ngay_phien_suy_ra") else ""), mono=True),
                     cell(so(t.get("vnindex"), 2), mono=True),
                     cell(pct(t.get("thay_doi_pct"), 2), "xanh" if (t.get("thay_doi_pct") or 0) > 0 else "do", mono=True),
                     cell(so(t.get("gtgd_ty")), mono=True),
                     cell(so(t.get("nn_rong_ty")), "xanh" if (t.get("nn_rong_ty") or 0) > 0 else "do", mono=True),
                     cell(so(t.get("nn_rong_ytd_ty")), mono=True), cell(" · ".join(mocs) or "—"),
                     cell(t.get("quan_diem"), tip=t.get("nguon"))])
    if dong:
        khoi.append({"kieu": "bang", "cot": ["Phiên", "VN-Index", "±%", "GTGD (tỷ)", "NN ròng (tỷ)", "NN YTD (tỷ)",
                                             "Mốc", "Quan điểm HSC"], "dong": dong, "can_phai": [1, 2, 3, 4, 5],
                     "chu_thich": "12 phiên gần nhất, mới trước. * = ngày phiên suy ra từ ngày báo cáo."})
    dong_t = [[cell(ddmm(t.get("ngay_phien")), mono=True), cell(so(t.get("vnindex"), 2), mono=True),
               cell(pct((t.get("tuan") or {}).get("thay_doi_pct") if t.get("tuan") else t.get("thay_doi_pct")), mono=True),
               cell(_hoac((t.get("tuan") or {}).get("gtgd_bq_phien_ty")), mono=True),
               cell(_hoac((t.get("tuan") or {}).get("nn_rong_ty")), mono=True), cell(t.get("quan_diem"), tip=t.get("nguon"))]
              for t in reversed(tu[-6:])]
    if dong_t:
        khoi += [doan("Theo tuần (Weekly Note)", mau="lam"),
                 {"kieu": "bang", "cot": ["Tuần tới", "VN-Index", "±% tuần", "GTGD bq/phiên", "NN ròng tuần", "Quan điểm HSC"],
                  "dong": dong_t, "can_phai": [1, 2, 3, 4]}]
    if not khoi:
        khoi = [doan(f"{CAN} Chưa có báo cáo ngày/tuần nào của HSC tới lô {ddmm(ngay)}.")]
    return sec("thi_truong", "IV", "Chuỗi thị trường", "Giọng HSC qua từng phiên", khoi)


def muc_vi_mo(c, ngay):
    vm = [v for v in c.get("vi_mo") or [] if (v.get("ngay_bc") or "") <= ngay]
    moi = {}
    for v in vm:   # chuỗi đã xếp theo ngày báo cáo: bản sau đè bản trước cho cùng chỉ tiêu + kỳ + loại
        moi[(v.get("chi_tieu"), v.get("ky"), v.get("loai"))] = v
    ds_ = sorted(moi.values(), key=lambda v: v.get("ngay_bc") or "", reverse=True)[:40]
    if not ds_:
        return sec("vi_mo", "V", "Vĩ mô", "Số HSC in trong báo cáo", [doan(f"{CAN} Chưa có số vĩ mô tới lô {ddmm(ngay)}.")])
    dong = [[cell(v.get("chi_tieu"), dam=True), cell(v.get("ky"), mono=True),
             cell(f"{so(v.get('gia_tri'), 2)} {v.get('don_vi') or ''}".strip(), mono=True),
             cell("dự báo" if v.get("loai") == "du_bao" else "thực tế", "tim" if v.get("loai") == "du_bao" else None, pill=True),
             cell(so(v.get("gia_tri_cu"), 2) if v.get("gia_tri_cu") is not None else "—", mono=True),
             cell(ddmm(v.get("ngay_bc")), mono=True, tip=v.get("nguon")), cell(v.get("ghi_chu") or "—", "xam")]
            for v in ds_]
    return sec("vi_mo", "V", "Vĩ mô", "Số HSC in trong báo cáo · mới nhất cho mỗi chỉ tiêu và kỳ", [
        {"kieu": "bang", "cot": ["Chỉ tiêu", "Kỳ", "Giá trị", "Loại", "Trước", "Báo cáo", "Ghi chú"], "dong": dong,
         "can_phai": [2, 4], "chu_thich": f"{len(ds_)} trên {len(moi)} cặp chỉ tiêu–kỳ, xếp theo ngày báo cáo mới trước."}])


def muc_su_kien(c, ngay):
    sk = sorted([s for s in c.get("su_kien") or [] if (s.get("ngay_bc") or "") <= ngay],
                key=lambda s: (s.get("ngay_bc") or "", s.get("ngay") or ""), reverse=True)[:20]
    if not sk:
        return sec("su_kien", "VI", "Sự kiện", "ETF · ĐHCĐ · KQKD · chính sách", [doan(f"{CAN} Chưa có sự kiện tới lô {ddmm(ngay)}.")])
    dong = [[cell(ddmm(s.get("ngay")), mono=True), cell(s.get("loai"), pill=True), cell(s.get("mo_ta"), tip=s.get("nguon")),
             cell(", ".join(s.get("ma") or []) or "—", mono=True),
             cell("; ".join(f"{k}: {so(v, 2)}" for k, v in (s.get("so_lieu") or {}).items()) or "—", "xam")] for s in sk]
    return sec("su_kien", "VI", "Sự kiện", "ETF · ĐHCĐ · KQKD · chính sách · 20 gần nhất", [
        {"kieu": "bang", "cot": ["Ngày", "Loại", "Mô tả", "Mã", "Số liệu"], "dong": dong}])


def muc_nguon(c, ngay, lo_file, pt_file, ngay_list):
    co_hd = [x.get("lo") for x in ngay_list if x.get("co_phan_tich")]
    return sec("nguon", "VII", "Nguồn & bậc bằng chứng", "Đọc trước khi dùng số", [
        {"kieu": "chips", "chips": [{"tier": T_KHO, "text": "Kho: mọi số của báo cáo HSC"},
                                    {"tier": T_HD, "text": "Hội đồng: ý kiến trên nền SS-T3"}]},
        ds([f"Kho lô: {lo_file}",
            f"Hội đồng: {pt_file}" if pt_file else f"Hội đồng: chưa có phan_tich/{ngay}.json",
            f"Chuỗi: {GOC / 'chuoi.json'} · dựng lúc {c.get('cap_nhat') or CAN} · {so(c.get('so_lo'))} lô · "
            f"{so(c.get('so_bc'))} báo cáo ({so(c.get('so_chinh'))} bản chính)",
            "Lô có bản Hội đồng: " + (", ".join(ddmm(x) for x in co_hd) or "—"),
            "Toàn bộ kho là một nhà môi giới (SS-T3): Hard Rule #9 luôn áp — cần nguồn thứ hai (SSI/BSC/VCSC) trước "
            "khi một mã vào Synthesis.",
            "Số trong biểu đồ dạng ảnh của báo cáo không lấy được (trích bằng đọc hiểu, không OCR bảng).",
            f"Trang chuỗi đầy đủ: {INDEX_URL}"] + _goc_drive_dong())])


def _goc_drive_dong():
    """Các thư mục gốc Drive (goc_drive.json): từ 10/2026 HSC RS mở một gốc mới mỗi tháng."""
    g = doc_json(GOC / "goc_drive.json")
    if not g:
        return [f"Gốc Drive: {CAN} (thiếu goc_drive.json)"]
    out = []
    for x in g.get("goc") or []:
        den = ddmm(x.get("den")) if x.get("den") else "nay"
        out.append(f"Gốc Drive '{x.get('ten')}': lô {ddmm(x.get('tu'))} → {den} · "
                   f"https://drive.google.com/drive/folders/{x.get('id')}")
    return out


# ───────────────────────────── dựng trang ─────────────────────────────

def overview(ngay_chon=None):
    lo_ds = cac_lo()
    ngay = ngay_chon or lo_ds[-1]
    if ngay not in lo_ds:
        raise HscError(f"Không có lô {ngay} trong kho. Các lô có: {lo_ds[0]} → {lo_ds[-1]} ({len(lo_ds)} lô).")
    c = doc_json(GOC / "chuoi.json")
    if c is None:
        raise HscError(f"Thiếu {GOC / 'chuoi.json'}. Chạy: python3 hsc_kho.py chuoi trong {GOC}")
    lo_file = GOC / "kho" / f"{ngay}.jsonl"
    lo_hdr, bcs = doc_lo(lo_file)
    pt_path = GOC / "phan_tich" / f"{ngay}.json"
    pt = doc_json(pt_path)

    today = _ngay(os.environ.get("HSC_TODAY")) or datetime.now(ICT).date()
    ngay_list = c.get("ngay") or []
    info = next((x for x in ngay_list if x.get("lo") == ngay), None)
    ids_kho = {b.get("id") for p in (GOC / "kho").glob("*.jsonl") for b in doc_lo(p)[1]}

    warnings = []
    moi_nhat = lo_ds[-1]
    age = (today - _ngay(moi_nhat)).days
    stale = age > STALE_DAYS
    if info is None:
        warnings.append(f"chuoi.json chưa có lô {ddmm(ngay)} — chạy hsc_kho.py tat_ca để dựng lại chuỗi.")
    elif info.get("so_bc") != len(bcs):
        warnings.append(f"chuoi.json ghi {info.get('so_bc')} báo cáo cho lô {ddmm(ngay)}, kho có {len(bcs)} — chuỗi cũ hơn kho.")
    so_tep, bq = lo_hdr.get("so_tep"), len(lo_hdr.get("bo_qua") or [])
    if isinstance(so_tep, int) and so_tep != len(bcs) + bq:
        warnings.append(f"Lô {ddmm(ngay)} chưa đủ: Drive có {so_tep} tệp, kho có {len(bcs)} báo cáo + {bq} bỏ qua.")
    if not pt:
        warnings.append(f"Lô {ddmm(ngay)} chưa có bản Hội đồng.")

    ma_lo = {k.get("ma") for b in bcs for k in b.get("khuyen_nghi") or [] if k.get("ma")}
    s_kn, csv_rows = muc_khuyen_nghi(c, ngay, ma_lo, today)
    sections = [muc_cong(pt), muc_lo(lo_hdr, bcs, ngay, info, ids_kho), muc_hoi_dong(pt, ngay), s_kn,
                muc_thi_truong(c, ngay), muc_vi_mo(c, ngay), muc_su_kien(c, ngay),
                muc_nguon(c, ngay, lo_file, pt_path if pt else None, ngay_list)]

    theo = {x.get("lo"): x for x in ngay_list}
    ky_list = []
    for d in reversed(lo_ds):
        x = theo.get(d) or {}
        nhan = f"{ddmm(d)} · {x.get('so_bc', '?')} bc" + (" · HĐ" if x.get("co_phan_tich") or (d == ngay and pt) else "")
        ky_list.append({"ngay": d, "nhan": nhan})
    return {"meta": {"generated": datetime.now(ICT).isoformat(timespec="seconds"), "data_to": ngay, "lo": ngay,
                     "lo_moi_nhat": moi_nhat, "ky_list": ky_list, "stale": stale, "age_days": age,
                     "stale_text": f"LÔ MỚI NHẤT {ddmm(moi_nhat)} — {age} ngày chưa có lô mới" if stale else "",
                     "warnings": warnings, "index_url": INDEX_URL, "lo_file": str(lo_file),
                     "co_hoi_dong": bool(pt), "ten_lo": lo_hdr.get("ten_lo") or ""},
            "trang": {"sections": sections},
            "csv": {"columns": ["ma", "danh_muc", "chuan", "muc_tieu", "gia", "ngay_gia", "upside_pct", "doi_hang",
                                "doi_tp_pct", "so_lan", "ngay_bc", "tieu_de", "link"], "rows": csv_rows}}


USAGE = "Dùng: python3 hsc_research.py overview [--ngay YYYY-MM-DD]"


def run(argv):
    if len(argv) < 2 or argv[1].strip().lower() != "overview":
        raise HscError("Lệnh không hỗ trợ. " + USAGE)
    rest, ngay = argv[2:], None
    if rest:
        if len(rest) != 2 or rest[0] != "--ngay" or not _ngay(rest[1]):
            raise HscError("Tham số sai. " + USAGE)
        ngay = rest[1][:10]
    return overview(ngay)


def _sach(o):
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, dict):
        return {k: _sach(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_sach(v) for v in o]
    return o


def main(argv=None):
    argv = sys.argv if argv is None else argv
    try:
        out = run(argv)
    except HscError as ex:
        out = {"error": str(ex)}
    except Exception as ex:  # noqa: BLE001 — tab phải nhận JSON, không nhận traceback
        out = {"error": f"hsc_research.py lỗi ngoài dự kiến: {type(ex).__name__}: {ex}"}
    sys.stdout.write(json.dumps(_sach(out), ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
