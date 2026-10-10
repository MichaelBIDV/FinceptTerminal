#!/usr/bin/env python3
"""Gói dữ kiện cho Hội đồng cố vấn AI chứng khoán (tab toanvu_pe), dựng từ dữ liệu đã kiểm của toanvu_pe_sau.py.

    python3 scripts/toanvu_pe_hoidong_facts.py          → state/toanvu_pe/hoi_dong/_facts/<KEY>.json (VNINDEX, VN30, VN100, từng mã)

Mỗi gói vài KB, mọi số mang nhãn bậc bằng chứng. Bản nhận định Hội đồng (viết ngoài app) chỉ được dùng số trong gói.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

STATE = Path.home() / "SECOND BRAIN-OBSIDIAN" / "_System" / "fincept_bridge" / "state" / "toanvu_pe"


def rd(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def macro(v: dict) -> dict:
    tg, ib, t10, sgi = v.get("tien_gui_niem_yet") or {}, v.get("lien_nh") or {}, v.get("tpcp10") or {}, v.get("sgi") or {}
    return {"ls_niem_yet_13T_NH_lon": [tg.get("x", [None])[-1], tg.get("y13", [None])[-1], "FACT-T2"],
            "lien_nh_qua_dem": [ib.get("x", [None])[-1], ib.get("on", [None])[-1], "FACT-T2"],
            "tpcp_10y": [t10.get("x", [None])[-1], t10.get("y", [None])[-1], "FACT-T2"],
            "nhnn_6_12T": (v.get("nhnn_6_12") or [None])[-1],
            "sgi": {k: sgi.get(k) for k in ("ky", "che_do", "chot", "dieu_kien_day", "tien_mat_de_xuat", "dk", "chi_so")},
            "tin_dung_m2": v.get("tin_dung_m2"),
            "ghi_chu": "SGI = bản tuần deep-macro-sgi (EST/FACT-T1 theo từng chỉ số); LTT (LS thôi tăng) chưa bật"}


def insider_12m(s: dict) -> tuple[list, dict]:
    """Mọi lệnh nội bộ trong đúng cửa sổ 365 ngày builder dùng cho nb12_pct (tính từ phiên cuối), kèm tổng khớp nb12."""
    try:
        cut = (date.fromisoformat(s["phien"]) - timedelta(days=365)).isoformat()
    except (KeyError, TypeError, ValueError):
        return [], {}
    rows = [x for x in (s.get("noi_bo") or []) if x["ngay"] >= cut]
    tinh = [x for x in rows if not x.get("nguon")]
    khoi = [x["kl"] for x in tinh if x.get("pt") in ("thoả thuận", "ngoài sàn")]
    chuoi = [x["kl"] for x in tinh if x.get("code") == "CHUOI"]
    khop = [x["kl"] for x in tinh if x.get("pt") == "khớp lệnh"]
    chua_ro = [x["kl"] for x in tinh if x.get("code") != "CHUOI" and x.get("pt") not in ("thoả thuận", "ngoài sàn", "khớp lệnh")]
    return rows, {"tu_ngay": cut, "so_lenh": len(rows),
                  "rong_tinh_kl": sum(x["kl"] for x in tinh),
                  "trong_do_khop_lenh_kl": sum(khop), "trong_do_khoi_kl": sum(khoi), "trong_do_chuoi_khong_khai_bao_kl": sum(chuoi),
                  "trong_do_chua_ro_phuong_thuc_kl": sum(chua_ro),
                  "mua_kl": sum(x["kl"] for x in tinh if x["kl"] > 0), "ban_kl": -sum(x["kl"] for x in tinh if x["kl"] < 0),
                  "loai_nhan_qua_phat_hanh_kl": sum(x["kl"] for x in rows if x.get("nguon") in ("quyền mua", "ESOP", "trùng đợt phát hành?")),
                  "loai_chuyen_noi_bo_kl": sum(x["kl"] for x in rows if (x.get("nguon") or "").startswith("chuyển nội bộ")),
                  "ghi_chu": ("rong_tinh_kl là tử số của bang_chung.nb12_pct (danh sách đầy đủ, không cắt). Lệnh khối "
                              "(pt thoả thuận/ngoài sàn, gia_tt = giá bình quân thoả thuận của phiên, EST) VẪN tính vì là thay đổi sở hữu thật; "
                              "pt khớp lệnh = KL không vượt khớp lệnh của cửa sổ (suy ra); chưa rõ = KL vượt khớp lệnh mà thoả thuận không phủ đủ; "
                              "dòng code CHUOI = biến động không khai báo suy từ chuỗi số dư (EST); lệnh có nguon bị loại.")}


def ticker_pack(tk: str, tong: dict, mac: dict, cong: str) -> dict | None:
    m, s = rd(STATE / "ma" / f"{tk}.json"), rd(STATE / "sau" / f"{tk}.json")
    if not m or not s:
        return None
    cur = m.get("hien_tai") or {}
    dot = m.get("theo_dot") or {}
    nb_rows, nb_tong = insider_12m(s)
    return {
        "key": tk, "ten": m.get("ten"), "nganh": s.get("nganh"), "phien": s.get("phien"), "cong": cong,
        "gia": {"ngay": cur.get("ngay"), "dong": cur.get("px"), "bac": "FACT-T2 (Bloomberg PX_LAST, giá điều chỉnh)"},
        "luat_tv_hien_tai": {k: cur.get(k) for k in ("pe", "pct", "nguong", "kich_hoat", "ey", "erp", "ls")} | {"bac": "EST (tái lập trên Bloomberg)"},
        "lich_su_theo_dot_doc_lap": {k: dot.get(k) for k in ("n_do", "hit", "xs_tb", "p_xs", "r60_tb")} | {"bac": "EST"},
        "pha_gan_nhat": [{k: p.get(k) for k in ("tu", "den", "r", "eps_pct", "pe_pct", "kieu", "vni_r", "ls0", "ls1")} |
                         {"noi_bo_rong_pct": (p.get("noi_bo") or {}).get("rong_pct_cp")} for p in (s.get("pha") or [])[-4:]],
        "tan_suat_thang": [{k: w.get(k) for k in ("ten", "n", "hit60", "co", "p_ro", "hit120", "r60_tv")} for w in s.get("xac_suat") or []],
        "huong_ls_6t_hien_tai": s.get("huong_ls_now"),
        "hhp": s.get("hhp"), "hhp_vung_lich_su": s.get("hhp_vung_lich_su"),
        "du_phong_eps": (s.get("du_phong") or {}).get("eps_pins"), "gia_muc_tieu": (s.get("du_phong") or {}).get("targets"),
        "noi_bo_12_thang_gan_nhat": nb_rows,
        "noi_bo_12_thang_tong": nb_tong,
        "ghi_chu_noi_bo": "lệnh có 'nguon' (quyền mua/ESOP/trùng đợt phát hành? = nhận qua phát hành; chuyển nội bộ = chân đối ứng nội bộ còn đăng ký) không tính vào ròng; lệnh khối (pt) và dòng CHUOI vẫn tính, xem noi_bo_12_thang_tong",
        "noi_bo_dang_ky_mo": s.get("noi_bo_dang_ky"),
        "su_kien_von": (s.get("von") or [])[:6],
        "tin_fft_13_thang": [{k: e.get(k) for k in ("ngay", "loai", "the_loai", "mo_ta", "bac")} for e in (s.get("su_kien_fft") or [])[:10]],
        "bang_chung": s.get("bang_chung"),
        "vi_mo": mac,
        "danh_muc_tham_chieu_12_09": "Core VCB 10% · FPT 12% · MSN 5%; Growth ACB 7% · GAS 8% · HPG 5% · TCB 5% · CTG 4%; Tactical GEX 3% · VRE 3% · PLX 3%; tiền 16%; AVOID NVL LPB VIC VJC STB HUT BCM ACV",
    }


def scope_pack(code: str, mac: dict, cong: str) -> dict | None:
    d = rd(STATE / "ro" / f"{code}.json")
    if not d:
        return None
    rows = sorted(d.get("bang_chung") or [], key=lambda r: -r["diem"])
    return {
        "key": code, "phien": d.get("phien"), "cong": cong, "chi_so_nguon": d.get("chi_so_nguon"), "hien_tai": d.get("hien_tai"),
        "erp_vung": d.get("erp_vung"), "regime": d.get("regime"),
        "hhp": {k: ({kk: vv for kk, vv in (v or {}).items() if kk != "chuoi"} if isinstance(v, dict) else v) for k, v in (d.get("hhp") or {}).items()},
        "bang_chung_tom_tat": [{k: r.get(k) for k in ("ma", "nhan", "diem", "pct", "hhp_sigma", "hhp_do", "erp", "eps26", "hit60_co", "nb12_pct", "huy_dong")}
                               for r in rows],
        "vi_mo": mac,
        "kiem_dinh_chinh": "Luật TV tái lập khớp; bỏ nhìn trước EPS 45 ngày: lợi thế ≈ 0 (vượt cùng ngày +0,22, t 0,5); đợt độc lập: 12/380 mã dương có ý nghĩa ≈ may rủi; hướng LS 6 tháng chi phối (LS tăng: TB 60 phiên ≈ −0,3…−0,8% khi tín hiệu); LS TV dùng 11,78% là lỗi đọc dòng 2008 (đúng 7,60%).",
    }


def main():
    out = STATE / "hoi_dong" / "_facts"
    out.mkdir(parents=True, exist_ok=True)
    tong = rd(STATE / "tong_quan.json") or {}
    v = rd(STATE / "vimo.json") or {}
    mac = macro(v)
    cong = "CỔNG: [CẦN DATA, M2 nghi gãy chuỗi 10/2025] · không kết luận per-mã (Cổng v1.7 đang DỪNG)"
    n = 0
    for code in ("VNINDEX", "VN30", "VN100", "VN200", "REST"):
        p = scope_pack(code, mac, cong)
        if p:
            (out / f"{code}.json").write_text(json.dumps(p, ensure_ascii=False, indent=0))
            n += 1
    for f in sorted((STATE / "sau").glob("*.json")):
        p = ticker_pack(f.stem, tong, mac, cong)
        if p:
            (out / f"{f.stem}.json").write_text(json.dumps(p, ensure_ascii=False, indent=0))
            n += 1
    print(f"{n} gói · {datetime.now():%H:%M} → {out}")


if __name__ == "__main__":
    main()
