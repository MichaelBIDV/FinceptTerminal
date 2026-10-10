#!/usr/bin/env python3
"""bbg_research.py — tab "BBG RESEARCH" của Fincept Terminal (trang vnblocks/1, xem VnBlocks.h).

Đọc (chỉ đọc, không mạng) kho Bloomberg Research theo ngày — báo cáo UBS · J.P. Morgan · HSBC · Citi…
tải từ Bloomberg — mà scheduled task 18:00 thứ Sáu (hằng tuần) ghi ở ~/SECOND BRAIN-OBSIDIAN/_System/bbg_research/
(lược đồ: README.md của thư mục đó):
    kho/<YYYY-MM-DD>.jsonl        SỰ THẬT (SS-T3) — lô = các tệp lên Drive cùng một ngày
    phan_tich/<YYYY-MM-DD>.json   Ý KIẾN Hội đồng (EST)
    chuoi.json                    chuỗi dựng lại từ kho (bbg_kho.py chuoi), khoá khuyến nghị = "MÃ·TỔ CHỨC"
Mượn khối dựng trang của hsc_research.py (cùng thư mục scripts) để hai tab đọc giống nhau. Đối chiếu
chỉ-đọc: chuoi.json của hệ HSC và kho giá vn_store (giá hôm nay → upside hôm nay là phép tính [EST]).
Không sửa tệp nào. Thiếu số → [CẦN DATA]. Chuỗi CẮT tại ngày lô đang xem.

USAGE
    python3 bbg_research.py overview [--ngay YYYY-MM-DD]

OUTPUT — đúng MỘT đối tượng JSON trên stdout, exit 0 kể cả khi lỗi (cùng hợp đồng với hsc_research.py).
Biến môi trường (test): BBG_GOC (thư mục kho), BBG_TODAY (YYYY-MM-DD).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hsc_research as H  # noqa: E402 — khối dựng trang, định dạng số, đọc JSONL dùng chung

GOC = Path(os.environ.get("BBG_GOC") or Path.home() / "SECOND BRAIN-OBSIDIAN" / "_System" / "bbg_research")
HSC_CHUOI = GOC.parent / "hsc_research" / "chuoi.json"
VN_STORE = GOC.parent / "fincept_bridge" / "vnstore" / "vn_store.db"
INDEX_URL = "http://localhost:9000/sys/bbg_research/index.html"
STALE_DAYS = 14          # đồng nghiệp lên tệp không theo lịch — hai tuần không có lô mới mới đáng cảnh báo
CU_NGAY = 90
PV = {"VN": "Việt Nam", "ASEAN": "ASEAN", "APAC": "Châu Á", "EM": "EM", "TOAN_CAU": "Toàn cầu"}
TEN_XD = {"IB_3_THANG": "Dự kiến phí IB trong 3 tháng", "KHACH_HANG": "Là khách hàng của nhà phát hành",
          "TAO_LAP_TT": "Tạo lập thị trường", "KHONG_GHI": "Không ghi xung đột nào"}
T_KHO, T_HD, T_MKT = "SS-T3", "EST", "MKT"
CAN, so, pct, cell, sec, doan, ds, ddmm, ddmmyyyy = (H.CAN, H.so, H.pct, H.cell, H.sec, H.doan, H.ds, H.ddmm,
                                                      H.ddmmyyyy)


class BbgError(Exception):
    pass


def _ngay(s):
    return H._ngay(s)


def _doi_chu(o, cap):
    """Thay chuỗi trong mọi string của một khối đã dựng (khối HSC dùng lại mang chữ 'HSC')."""
    if isinstance(o, str):
        for a, b in cap:
            o = o.replace(a, b)
        return o
    if isinstance(o, list):
        return [_doi_chu(x, cap) for x in o]
    if isinstance(o, dict):
        return {k: _doi_chu(v, cap) for k, v in o.items()}
    return o


def tp(v, tien):
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return "—"
    return so(v) if (tien or "VND") == "VND" else f"{so(v, 2)} {tien}"


def up(tp_, gia):
    return (tp_ / gia - 1) * 100 if isinstance(tp_, (int, float)) and isinstance(gia, (int, float)) and gia else None


# ───────────────────────────── đọc kho ─────────────────────────────

def doc_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as ex:
        raise BbgError(f"Không đọc được {p.name}: {ex}. Chạy lại: python3 bbg_kho.py tat_ca trong {GOC}")


def doc_lo(p):
    try:
        return H.doc_lo(p)
    except H.HscError as ex:
        raise BbgError(str(ex).replace("hsc_kho.py", "bbg_kho.py"))


def cac_lo():
    kho = GOC / "kho"
    if not kho.is_dir():
        raise BbgError(f"Chưa có kho Bloomberg Research ở {kho}. Scheduled task 18:00 thứ Sáu chưa chạy lần nào, "
                       "hoặc kho bị chuyển chỗ (đặt biến BBG_GOC).")
    out = sorted(p.stem for p in kho.glob("*.jsonl") if _ngay(p.stem))
    if not out:
        raise BbgError(f"Kho {kho} chưa có lô nào (kho/<YYYY-MM-DD>.jsonl).")
    return out


def gia_nay(ma_ds):
    ma_ds = sorted({m for m in ma_ds if m and "@" not in m})
    if not ma_ds or not VN_STORE.exists():
        return {}
    try:
        con = sqlite3.connect(f"file:{VN_STORE}?mode=ro", uri=True, timeout=5)
        out = {}
        for m in ma_ds:
            r = con.execute("select ngay, dong from nen_ngay where symbol=? order by ngay desc limit 1", (m,)).fetchone()
            if r and r[1]:
                out[m] = (r[0], float(r[1]))
        con.close()
        return out
    except sqlite3.Error:
        return {}


def hsc_moi_nhat(ngay):
    try:
        c = json.loads(HSC_CHUOI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for m, lich in (c.get("khuyen_nghi") or {}).items():
        lich = [x for x in lich if (x.get("ngay_bc") or "") <= ngay]
        if lich:
            out[m] = lich[-1]
    return out


# ───────────────────────────── các mục ─────────────────────────────

def muc_lo(lo_hdr, bcs, ngay, info, gia):
    tc, nhom_dem = {}, {}
    for b in bcs:
        tc[b.get("to_chuc")] = tc.get(b.get("to_chuc"), 0) + 1
        nhom_dem[b.get("nhom")] = nhom_dem.get(b.get("nhom"), 0) + 1
    vn = [b for b in bcs if b.get("pham_vi") == "VN"]
    kn_vn = [k for b in vn for k in b.get("khuyen_nghi") or []]
    ma_vn = sorted({k.get("ma") for k in kn_vn if k.get("ma")})
    tren30 = sorted({k["ma"] for k in kn_vn if (up(k.get("muc_tieu"), (gia.get(k["ma"]) or (None, None))[1]) or -1) >= 30})
    ngay_gia = max((v[0] for v in gia.values()), default=None)
    info = info or {}
    tiles = [
        {"nhan": "Báo cáo trong lô", "gia_tri": so(len(bcs)),
         "phu": " · ".join(f"{k} {v}" for k, v in sorted(tc.items(), key=lambda kv: -kv[1])), "tier": T_KHO},
        {"nhan": "Việt Nam / khu vực", "gia_tri": f"{len(vn)} / {len(bcs) - len(vn)}",
         "phu": "khu vực đọc như tham chiếu", "tier": T_KHO},
        {"nhan": "Mã VN có hạng", "gia_tri": so(len(ma_vn)), "phu": ", ".join(ma_vn) or "—", "tier": T_KHO},
        {"nhan": "Upside ≥30% theo giá hôm nay", "gia_tri": so(len(tren30)), "phu": ", ".join(tren30) or "—",
         "mau": "vang" if tren30 else None, "tier": f"{T_HD} {T_MKT}"},
        {"nhan": "Nâng / hạ hạng", "gia_tri": f"{len(info.get('nang') or [])} / {len(info.get('ha') or [])}",
         "phu": ", ".join((info.get("nang") or []) + (info.get("ha") or [])) or "—", "tier": T_KHO},
        {"nhan": "Lên Drive lúc", "gia_tri": (lo_hdr.get("tai_len_luc") or "")[11:16] or CAN,
         "phu": f"{lo_hdr.get('ten_lo') or ''} · giá hôm nay {ddmm(ngay_gia) if ngay_gia else CAN}", "tier": T_KHO},
    ]
    khoi = [{"kieu": "o_so", "o": tiles, "cot": 3}]
    dong = []
    for b in sorted(bcs, key=lambda b: (b.get("pham_vi") != "VN", [k for k, _ in H.NHOM].index(b.get("nhom")),
                                        b.get("ngay_bc") or "")):
        ks = b.get("khuyen_nghi") or []
        hang = "; ".join(f"{k.get('ma')} {H.hang_txt(k)} · TP {tp(k.get('muc_tieu'), k.get('tien'))} ({pct(k.get('upside'))})"
                         for k in ks)
        dong.append([cell(H.NHOM_TEN.get(b.get("nhom"), b.get("nhom")), pill=True), cell(b.get("to_chuc"), dam=True),
                     cell(b.get("loai")), cell(b.get("tieu_de"), dam=True, tip=b.get("link")),
                     cell(", ".join(b.get("ma") or []) or "—", mono=True),
                     cell(hang or "—", H.CHUAN_MAU.get(ks[0].get("chuan")) if ks else None),
                     cell(b.get("tom_tat") or CAN, None if b.get("pham_vi") == "VN" else "xam")])
    khoi.append({"kieu": "bang", "cot": ["Nhóm", "Tổ chức", "Loại", "Báo cáo", "Mã", "Hạng · TP · upside", "Tóm tắt"],
                 "dong": dong, "chu_thich": "Việt Nam trước, khu vực sau (chữ xám = tham chiếu). Mã MÃ@SÀN là cổ phiếu "
                                            "ngoài VN. Upside theo giá in trên báo cáo. Mọi số: nhà phát hành (SS-T3)."})
    for key, ten in H.NHOM:
        nhom_bc = [b for b in vn if b.get("nhom") == key]
        if not nhom_bc:
            continue
        khoi.append(doan(f"{ten} · Việt Nam · {len(nhom_bc)} báo cáo", mau="lam"))
        khoi.append({"kieu": "the", "cot": 2, "the": [
            {"tieu_de": (", ".join(b.get("ma") or []) + " · " if b.get("ma") else "") + (b.get("tieu_de") or CAN),
             "nhan": {"text": f"{b.get('to_chuc')} · {b.get('loai') or ''} · {ddmm(b.get('ngay_bc'))}", "mau": "xam"},
             "text": (b.get("tom_tat") or "") + "\n\n" + "\n".join("• " + t for t in b.get("y_chinh") or []),
             "tier": T_KHO} for b in nhom_bc]})
    kv = [b for b in bcs if b.get("pham_vi") != "VN"]
    if kv:
        khoi.append(doan(f"Khu vực · {len(kv)} báo cáo · đọc như tham chiếu", mau="lam"))
        khoi.append({"kieu": "the", "cot": 2, "the": [
            {"tieu_de": (", ".join(b.get("ma") or []) + " · " if b.get("ma") else "") + (b.get("tieu_de") or CAN),
             "nhan": {"text": f"{b.get('to_chuc')} · {PV.get(b.get('pham_vi'), b.get('pham_vi'))} · {ddmm(b.get('ngay_bc'))}",
                      "mau": "xam"},
             "text": f"Liên quan VN: {b.get('lien_quan_vn') or '—'}\n\n" + (b.get("tom_tat") or "") + "\n\n"
                     + "\n".join("• " + t for t in b.get("y_chinh") or []), "tier": T_KHO} for b in kv]})
    bq = lo_hdr.get("bo_qua") or []
    if bq:
        khoi.append({"kieu": "canh_bao", "tieu_de": "Tệp trong thư mục Drive cố ý không nạp", "mau": "vang",
                     "muc": [f"{x.get('tep')}: {x.get('ly_do')}" for x in bq]})
    return sec("lo", "I", f"Lô {ddmmyyyy(ngay)}", "Báo cáo lên Drive trong ngày · theo tổ chức và 7 nhóm", khoi,
               "Sự thật trích từ báo cáo sell-side quốc tế (SS-T3). Báo cáo được cấp phép qua Bloomberg — chỉ dùng nội bộ.")


def muc_hoi_dong(pt, ngay):
    pt2 = None
    if pt:
        pt2 = dict(pt)
        pt2["soi_khuyen_nghi"] = [dict(x, hsc=x.get("sell_side") or x.get("hsc")) for x in pt.get("soi_khuyen_nghi") or []
                                  if isinstance(x, dict)]
    s = H.muc_hoi_dong(pt2, ngay)
    return _doi_chu(s, [("HSC nói", "Sell-side nói"), ("Chuỗi nhận định của HSC", "Chuỗi nhận định của sell-side quốc tế"),
                        ("trên nền số HSC (SS-T3). Một nguồn sell-side duy nhất", "trên nền báo cáo sell-side quốc tế "
                         "(SS-T3). Nhiều nhà vẫn là sell-side"),
                        ("mỗi lượt chạy 12:30", "mỗi lượt tuần 18:00 thứ Sáu"),
                        ("chỉ có sự thật từ kho HSC (SS-T3)", "chỉ có sự thật từ kho Bloomberg (SS-T3)")])


def muc_doi_chieu(bcs, gia, hsc):
    theo = {}
    for b in bcs:
        if b.get("pham_vi") != "VN":
            continue
        for k in b.get("khuyen_nghi") or []:
            ds_ = theo.setdefault(k["ma"], [])
            if not any(x[0] == b.get("to_chuc") for x in ds_):
                ds_.append((b.get("to_chuc"), k, b.get("ngay_bc")))
    dong = []
    for ma in sorted(theo):
        g, x = gia.get(ma), hsc.get(ma)
        qt = "; ".join(f"{t}: {H.hang_txt(k)} · {tp(k.get('muc_tieu'), k.get('tien'))} · {ddmm(n)}" for t, k, n in theo[ma])
        ups = [f"{t} {pct(up(k.get('muc_tieu'), g[1]))}" for t, k, _ in theo[ma]] if g else []
        if x and g:
            ups.append(f"HSC {pct(up(x.get('muc_tieu'), g[1]))}")
        n = len(theo[ma]) + (1 if x else 0)
        dong.append([cell(ma, mono=True, dam=True), cell(qt),
                     cell(f"{H.hang_txt(x)} · {so(x.get('muc_tieu'))} · {ddmm(x.get('ngay_bc'))}" if x
                          else "không phủ trong kho HSC", None if x else "xam"),
                     cell(f"{so(g[1])} ({ddmm(g[0])})" if g else "—", mono=True),
                     cell(" · ".join(ups) or "—", mono=True), cell(so(n), "xanh" if n >= 2 else "vang", pill=True)])
    if not dong:
        return None
    return sec("doi_chieu", "II·b", "Đối chiếu chéo", "Quốc tế × HSC × giá hôm nay", [
        {"kieu": "bang", "cot": ["Mã", "Quốc tế (hạng · TP · ngày BC)", "HSC (hạng · TP · ngày BC)", "Giá hôm nay",
                                 "Upside theo giá hôm nay", "Số nhà"], "dong": dong, "can_phai": [3, 4],
         "chu_thich": "Số nhà ≥2 = có nguồn sell-side thứ hai độc lập — vẫn là sell-side, chưa phải BCTC/CBTT. Giá: kho "
                      "Vietcap tại máy (giá điều chỉnh); upside hôm nay là phép tính [EST]."}],
               "Hard Rule #9: sell-side là nguồn duy nhất thì hạ một bậc conviction — hai nhà sell-side cùng chiều chưa gỡ luật này.")


def muc_khuyen_nghi(c, ngay, khoa_lo, today, gia):
    rows, csv = [], []
    for khoa, lich in (c.get("khuyen_nghi") or {}).items():
        lich = [x for x in lich if (x.get("lo") or "") <= ngay]
        if lich:
            x = lich[-1]
            rows.append((khoa, x, lich, (today - (_ngay(x.get("ngay_bc")) or today)).days > CU_NGAY))
    rows.sort(key=lambda r: (r[3], r[1].get("pham_vi") != "VN", r[1].get("ma") or "", r[1].get("to_chuc") or ""))
    dm = {m.get("khoa"): m.get("danh_muc") for m in c.get("moi_nhat") or []}
    dong = []
    for khoa, x, lich, cu in rows:
        g = gia.get(x.get("ma"))
        u_nay = up(x.get("muc_tieu"), g[1]) if g else None
        d = dm.get(khoa) or ""
        dong.append([cell(x.get("ma"), "xam" if cu else None, mono=True, dam=khoa in khoa_lo),
                     cell(x.get("to_chuc")),
                     cell(d or "—", "lam" if d == "NẮM" else ("do" if d == "TRÁNH" else None), pill=bool(d)),
                     cell(H.hang_txt(x), H.CHUAN_MAU.get(x.get("chuan")), pill=True),
                     cell(tp(x.get("muc_tieu"), x.get("tien")) + (f" ({x.get('ky_tp')})" if x.get("ky_tp") not in (None, "12m") else ""),
                          mono=True),
                     cell(f"{tp(x.get('gia'), x.get('tien'))} ({ddmm(x.get('ngay_gia'))})", mono=True),
                     cell(pct(x.get("upside")), mono=True),
                     cell(f"{pct(u_nay)} ({ddmm(g[0])})" if g else "—", "xanh" if (u_nay or 0) >= 30 else None, mono=True),
                     cell(x.get("doi_hang"), H.DOI_MAU.get(x.get("doi_hang"))),
                     cell(pct(x.get("doi_tp_pct")) if x.get("doi_tp_pct") is not None else "—", mono=True),
                     cell(f"{len(lich)} lần · " + " → ".join(tp(y.get("muc_tieu"), y.get("tien")) for y in lich[-4:]), mono=True),
                     cell(f"{ddmm(x.get('ngay_bc'))} · {x.get('tieu_de') or ''}", "xam" if cu else None, tip=x.get("link"))])
        csv.append([x.get("ma"), x.get("to_chuc"), d, x.get("chuan"), x.get("muc_tieu"), x.get("tien"), x.get("ky_tp"),
                    x.get("gia"), x.get("ngay_gia"), x.get("upside"), round(u_nay, 1) if u_nay is not None else None,
                    g[0] if g else None, x.get("doi_hang"), x.get("doi_tp_pct"), len(lich), x.get("ngay_bc"),
                    x.get("tieu_de"), x.get("link")])
    vn = [r for r in rows if r[1].get("pham_vi") == "VN" and not r[3]]
    tren30 = sorted({r[1].get("ma") for r in vn if (up(r[1].get("muc_tieu"), (gia.get(r[1].get("ma")) or (None, None))[1]) or -1) >= 30})
    khoi = [{"kieu": "o_so", "cot": 4, "o": [
        {"nhan": "Cặp mã · tổ chức", "gia_tri": so(len(rows)), "phu": f"cắt tại lô {ddmm(ngay)}", "tier": T_KHO},
        {"nhan": "Mã VN còn hiệu lực", "gia_tri": so(len({r[1].get('ma') for r in vn})),
         "phu": ", ".join(sorted({r[1].get("ma") for r in vn})) or "—", "tier": T_KHO},
        {"nhan": "Upside ≥30% theo giá hôm nay", "gia_tri": so(len(tren30)), "phu": ", ".join(tren30) or "—",
         "tier": f"{T_HD} {T_MKT}"},
        {"nhan": "TP cũ > 90 ngày", "gia_tri": so(sum(1 for r in rows if r[3])), "phu": "tô xám, xếp cuối", "tier": T_KHO}]},
        {"kieu": "bang", "cot": ["Mã", "Tổ chức", "DM", "Hạng", "TP", "Giá (ngày giá)", "Upside BC", "Upside hôm nay",
                                 "Đổi hạng", "Đổi TP", "Hành trình TP", "Báo cáo gần nhất"],
         "dong": dong, "can_phai": [4, 5, 6, 7, 9],
         "chu_thich": "Mỗi dòng là một cặp mã · tổ chức (JPM và UBS cùng phủ MSN là hai dòng). In đậm = có trong lô đang xem. "
                      "TP kỳ khác 12 tháng ghi kèm (vd Dec-27). DM: NẮM = danh mục, TRÁNH = danh sách tránh."}]
    return sec("khuyen_nghi", "III", "Chuỗi khuyến nghị theo mã · tổ chức", "Hạng và giá mục tiêu quốc tế qua các lần",
               khoi), csv


def muc_xung_dot(c, ngay):
    xd = sorted([x for x in c.get("xung_dot") or [] if (x.get("ngay_bc") or "") <= ngay],
                key=lambda x: x.get("ngay_bc") or "", reverse=True)[:30]
    ls = [x for x in c.get("lich_su_kn") or [] if (x.get("ngay_bc") or "") <= ngay]
    khoi = []
    if xd:
        khoi.append({"kieu": "bang", "cot": ["Ngày BC", "Mã", "Tổ chức", "Loại", "Nội dung công bố", "Trang"],
                     "dong": [[cell(ddmm(x.get("ngay_bc")), mono=True), cell(x.get("ma"), mono=True, dam=True),
                               cell(x.get("to_chuc")),
                               cell(TEN_XD.get(x.get("loai"), x.get("loai")), "xam" if x.get("loai") == "KHONG_GHI" else "do",
                                    pill=True),
                               cell(x.get("mo_ta"), tip=x.get("link")), cell(f"tr.{x.get('trang')}", mono=True)] for x in xd],
                     "chu_thich": "Đọc từ phần disclosures của từng báo cáo. 'Dự kiến phí IB trong 3 tháng' là cờ lùa gà mạnh nhất."})
    if ls:
        khoi.append(doan("Lịch sử hạng và TP do chính tổ chức công bố", mau="lam"))
        khoi.append({"kieu": "bang", "cot": ["Mã", "Tổ chức", "Ngày", "Hạng", "Giá lúc đó", "TP", "Upside lúc đó", "Trang"],
                     "dong": [[cell(x.get("ma"), mono=True, dam=True), cell(x.get("to_chuc")), cell(ddmmyyyy(x.get("ngay")), mono=True),
                               cell(x.get("xep_hang"), pill=True), cell(tp(x.get("gia"), x.get("tien")), mono=True),
                               cell(tp(x.get("muc_tieu"), x.get("tien")), mono=True),
                               cell(pct(up(x.get("muc_tieu"), x.get("gia"))), mono=True), cell(f"tr.{x.get('trang')}", mono=True)]
                              for x in ls], "can_phai": [4, 5, 6],
                     "chu_thich": "Hiệu chỉnh (Rigor 6D): TP có từng được chạm trong 12 tháng không? Nhà giữ một hạng quá lâu "
                                  "với upside luôn lớn là tín hiệu cần nghịch đảo."})
    if not khoi:
        return None
    return sec("xung_dot", "III·b", "Xung đột lợi ích & lịch sử công bố", "Soi mùi lùa gà từ chính disclosures", khoi)


def muc_nguon(c, ngay, lo_file, pt_file, ngay_list, gia):
    co_hd = [x.get("lo") for x in ngay_list if x.get("co_phan_tich")]
    ngay_gia = max((v[0] for v in gia.values()), default=None)
    return sec("nguon", "VII", "Nguồn & bậc bằng chứng", "Đọc trước khi dùng số", [
        {"kieu": "chips", "chips": [{"tier": T_KHO, "text": "Kho: số của báo cáo sell-side quốc tế"},
                                    {"tier": T_HD, "text": "Hội đồng: ý kiến trên nền SS-T3"},
                                    {"tier": T_MKT, "text": f"Giá hôm nay: kho Vietcap tại máy {ddmm(ngay_gia) if ngay_gia else CAN}"}]},
        ds([f"Kho lô: {lo_file}",
            f"Hội đồng: {pt_file}" if pt_file else f"Hội đồng: chưa có phan_tich/{ngay}.json",
            f"Chuỗi: {GOC / 'chuoi.json'} · dựng lúc {c.get('cap_nhat') or CAN} · {so(c.get('so_lo'))} lô · "
            f"{so(c.get('so_bc'))} báo cáo · tổ chức: "
            + ", ".join(f"{k} {v}" for k, v in sorted((c.get("to_chuc") or {}).items(), key=lambda kv: -kv[1])),
            "Lô có bản Hội đồng: " + (", ".join(ddmm(x) for x in co_hd) or "—"),
            f"Đối chiếu HSC: {HSC_CHUOI} (chỉ đọc) · giá: {VN_STORE} (chỉ đọc)",
            "Nhiều nhà vẫn là sell-side (SS-T3): Hard Rule #9 luôn áp — cần BCTC/CBTT trước khi một mã vào Synthesis.",
            "Báo cáo cấp phép qua Bloomberg cho người dùng tại BIDV — chỉ dùng nội bộ, không phân phối lại.",
            f"Trang chuỗi đầy đủ: {INDEX_URL}"])])


# ───────────────────────────── dựng trang ─────────────────────────────

def overview(ngay_chon=None):
    lo_ds = cac_lo()
    ngay = ngay_chon or lo_ds[-1]
    if ngay not in lo_ds:
        raise BbgError(f"Không có lô {ngay} trong kho. Các lô có: {lo_ds[0]} → {lo_ds[-1]} ({len(lo_ds)} lô).")
    c = doc_json(GOC / "chuoi.json")
    if c is None:
        raise BbgError(f"Thiếu {GOC / 'chuoi.json'}. Chạy: python3 bbg_kho.py chuoi trong {GOC}")
    lo_file = GOC / "kho" / f"{ngay}.jsonl"
    lo_hdr, bcs = doc_lo(lo_file)
    pt_path = GOC / "phan_tich" / f"{ngay}.json"
    pt = doc_json(pt_path)
    today = _ngay(os.environ.get("BBG_TODAY")) or datetime.now(H.ICT).date()
    ngay_list = c.get("ngay") or []
    info = next((x for x in ngay_list if x.get("lo") == ngay), None)
    ma_all = {k.get("ma") for lich in (c.get("khuyen_nghi") or {}).values() for k in lich} | \
             {m for b in bcs for m in b.get("ma") or []}
    gia = gia_nay(ma_all)
    hsc = hsc_moi_nhat(ngay)

    warnings = []
    moi_nhat = lo_ds[-1]
    age = (today - _ngay(moi_nhat)).days
    stale = age > STALE_DAYS
    if info is None:
        warnings.append(f"chuoi.json chưa có lô {ddmm(ngay)} — chạy bbg_kho.py tat_ca để dựng lại chuỗi.")
    elif info.get("so_bc") != len(bcs):
        warnings.append(f"chuoi.json ghi {info.get('so_bc')} báo cáo cho lô {ddmm(ngay)}, kho có {len(bcs)} — chuỗi cũ hơn kho.")
    so_tep, bq = lo_hdr.get("so_tep"), len(lo_hdr.get("bo_qua") or [])
    if isinstance(so_tep, int) and so_tep != len(bcs) + bq:
        warnings.append(f"Lô {ddmm(ngay)} chưa đủ: Drive có {so_tep} tệp, kho có {len(bcs)} báo cáo + {bq} bỏ qua.")
    if not pt:
        warnings.append(f"Lô {ddmm(ngay)} chưa có bản Hội đồng.")
    if not gia:
        warnings.append("Không đọc được kho giá vn_store — cột upside hôm nay để trống.")

    khoa_lo = {f"{k.get('ma')}·{b.get('to_chuc')}" for b in bcs for k in b.get("khuyen_nghi") or []}
    s_kn, csv_rows = muc_khuyen_nghi(c, ngay, khoa_lo, today, gia)
    cap = [("Số HSC in trong báo cáo", "Số sell-side quốc tế in trong báo cáo")]
    sections = [H.muc_cong(pt), muc_lo(lo_hdr, bcs, ngay, info, gia), muc_hoi_dong(pt, ngay),
                muc_doi_chieu(bcs, gia, hsc), s_kn, muc_xung_dot(c, ngay),
                _doi_chu(H.muc_vi_mo(c, ngay), cap), H.muc_su_kien(c, ngay),
                muc_nguon(c, ngay, lo_file, pt_path if pt else None, ngay_list, gia)]
    sections = [s for s in sections if s]
    ng = [x for x in (pt or {}).get("nguon_ngoai") or [] if isinstance(x, dict)]
    if ng:
        sections[-1]["khoi"].append(doan("Nguồn ngoài kho dùng trong bản Hội đồng", mau="lam"))
        sections[-1]["khoi"].append(ds([f"{x.get('ten')} — {x.get('url')}" for x in ng]))
    theo = {x.get("lo"): x for x in ngay_list}
    ky_list = []
    for d in reversed(lo_ds):
        x = theo.get(d) or {}
        nhan = f"{ddmm(d)} · {x.get('so_bc', '?')} bc" + (" · HĐ" if x.get("co_phan_tich") or (d == ngay and pt) else "")
        ky_list.append({"ngay": d, "nhan": nhan})
    return {"meta": {"generated": datetime.now(H.ICT).isoformat(timespec="seconds"), "data_to": ngay, "lo": ngay,
                     "lo_moi_nhat": moi_nhat, "ky_list": ky_list, "stale": stale, "age_days": age,
                     "stale_text": f"LÔ MỚI NHẤT {ddmm(moi_nhat)} — {age} ngày chưa có lô mới" if stale else "",
                     "warnings": warnings, "index_url": INDEX_URL, "lo_file": str(lo_file),
                     "co_hoi_dong": bool(pt), "ten_lo": lo_hdr.get("ten_lo") or ""},
            "trang": {"sections": sections},
            "csv": {"columns": ["ma", "to_chuc", "danh_muc", "chuan", "muc_tieu", "tien", "ky_tp", "gia", "ngay_gia",
                                "upside_bc_pct", "upside_hom_nay_pct", "ngay_gia_hom_nay", "doi_hang", "doi_tp_pct",
                                "so_lan", "ngay_bc", "tieu_de", "link"], "rows": csv_rows}}


USAGE = "Dùng: python3 bbg_research.py overview [--ngay YYYY-MM-DD]"


def run(argv):
    if len(argv) < 2 or argv[1].strip().lower() != "overview":
        raise BbgError("Lệnh không hỗ trợ. " + USAGE)
    rest, ngay = argv[2:], None
    if rest:
        if len(rest) != 2 or rest[0] != "--ngay" or not _ngay(rest[1]):
            raise BbgError("Tham số sai. " + USAGE)
        ngay = rest[1][:10]
    return overview(ngay)


def main(argv=None):
    argv = sys.argv if argv is None else argv
    try:
        out = run(argv)
    except (BbgError, H.HscError) as ex:
        out = {"error": str(ex)}
    except Exception as ex:  # noqa: BLE001 — tab phải nhận JSON, không nhận traceback
        out = {"error": f"bbg_research.py lỗi ngoài dự kiến: {type(ex).__name__}: {ex}"}
    sys.stdout.write(json.dumps(H._sach(out), ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
