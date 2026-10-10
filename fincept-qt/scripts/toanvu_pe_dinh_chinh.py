#!/usr/bin/env python3
"""Đính chính số nội bộ trong các bản Hội đồng đã viết khi builder đổi cách tính sau ngày viết (0 token Claude).

    python3 scripts/toanvu_pe_dinh_chinh.py      → state/toanvu_pe/hoi_dong/_dinh_chinh.json

Chạy SAU toanvu_pe_build.py + toanvu_pe_hoidong_facts.py. Trích các số % gắn với "nội bộ / ròng / nb12" trong văn bản
Hội đồng (bỏ số nói về một pha giá, một mốc sở hữu hay một ngưỡng), so với bang_chung.nb12_pct hiện tại; rổ thì so
từng mã nêu tên với bang_chung_tom_tat. Ghi đính chính khi sai chiều, hoặc lệch > 1 điểm và > 50%; nói rõ khi điểm
Chủ thể (ngưỡng ±0,1 của evidence_row) đổi, vì khi đó phần nhận định về chủ thể phải viết lại. Trang mã hiện các dòng
này trong khối "Đính chính dữ liệu" ngay trên kết luận Hội đồng.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

STATE = Path.home() / "SECOND BRAIN-OBSIDIAN" / "_System" / "fincept_bridge" / "state" / "toanvu_pe"
HD, FACTS = STATE / "hoi_dong", STATE / "hoi_dong" / "_facts"
BASKETS = {"VNINDEX", "VN30", "VN100", "VN200", "REST"}

KW = re.compile(r"nội bộ|mua ròng|bán ròng|\bgom\b|nb12|ròng 12 tháng|\bròng\s?[+−\-]\s?\d", re.I)
FOREIGN = re.compile(r"ngoại|tự doanh|dòng tiền|\bETF\b|\bquỹ\b|nâng hạng", re.I)
PCT = re.compile(r"(?<![\d.,±])([+−\-]?)\s?(\d+(?:,\d+)?)(?![.\d])\s?%")
STOP = re.compile(r"sở hữu|\bnắm\b|\blên\b|xuống|\bcòn\b|\btừ\b|\bvề\b|giữ|tỷ lệ|thưởng|cổ tức|ESOP|chào bán|EPS|P/E|giá|tần suất", re.I)
PHA = re.compile(r"\bpha\b|\d{2}/\d{4}\s*[-–]|\d{4}\s*[-–]\s*\d{4}|\(\d{2}-\d{2}/\d{4}\)", re.I)


def rd(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def vnf(x: float, nd: int = 2) -> str:
    if abs(x) < 0.5 * 10 ** -nd:
        return "0," + "0" * nd
    s = f"{x:+,.{nd}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return s.replace("-", "−")


def diem(v):
    return None if v is None else (1 if v >= 0.1 else (-1 if v <= -0.1 else 0))


def texts(d: dict) -> list:
    out = [d.get("tom_tat", "")]
    for z in ("kill_zone", "alpha_zone", "bench"):
        out += [x.get("y_kien", "") for x in d.get(z) or []]
    for x in d.get("bat_dong") or []:
        out += [x.get(k, "") for k in ("diem", "ung_ho", "phan_doi", "phan_xu")]
    out += [(v or {}).get("ghi", "") for v in (d.get("rigor") or {}).values()]
    return out  # bỏ pre_mortem / xac_nhan / phu_dinh: câu điều kiện, số trong đó là ngưỡng giả định chứ không phải số trích


def sentences(d: dict) -> list:
    res = []
    for t in texts(d):
        for s in re.split(r"(?<=[.!?])\s+", t or ""):
            if re.match(r"\s*(có\s+)?ngưỡng", s, re.I):
                continue  # câu liệt kê ngưỡng phủ định (ghi chú Falsifiability), không phải số trích
            if KW.search(s):
                res.append(s)
    return res


def claims_12m(s: str) -> list:
    """% gắn với 'nội bộ/ròng/nb12' (≤ 30 ký tự, không xuyên qua mốc sở hữu/EPS/giá…), hoặc '% số cp'. Bỏ ngưỡng
    (trên/dưới/≥…) và số nói về một pha giá. 'bán ròng X%' không dấu → −X."""
    out = []
    for m in PCT.finditer(s):
        near, right = s[max(0, m.start() - 30):m.start()], s[m.end():m.end() + 18]
        strong = re.search(r"^\s*(số cp|số cổ phiếu|cp lưu hành)", right, re.I) is not None
        km = list(re.finditer(r"nội bộ|ròng|nb12", near, re.I))
        tail = near[km[-1].end():] if km else ""
        ctx = bool(km) and ((m.group(1) in ("+", "−", "-") and not re.search(r"sở hữu|tỷ lệ|EPS|P/E|giá|tần suất|ERP", tail, re.I))
                            or not STOP.search(tail))
        if not (strong or ctx) or re.search(r"(trên|dưới|vượt|quá|≥|≤|>|<|±|ít nhất|tối thiểu)\s*$", s[max(0, m.start() - 12):m.start()], re.I):
            continue
        if FOREIGN.search(near):
            continue  # số của khối ngoại / quỹ / dòng tiền đứng cạnh, không phải nội bộ
        if not re.search(r"12 tháng|nb12", s[max(0, m.start() - 45):m.start()], re.I) and PHA.search(s[max(0, m.start() - 110):m.end() + 25]):
            continue  # số của một pha giá, không phải cửa sổ 12 tháng
        sign = -1 if m.group(1) in ("−", "-") else 1
        if not m.group(1) and re.search(r"bán ròng|rút ròng|giảm ròng", near, re.I):
            sign = -1
        out.append(sign * float(m.group(2).replace(",", ".")))
    return out


def lech(v: float, cur: float) -> bool:
    """Sai chiều, hoặc lệch ≥ 1 điểm (chừa sai số làm tròn của số trích) và > 25% số hiện tại."""
    return (v > 0.005 and cur < -0.005) or (v < -0.005 and cur > 0.005) or (abs(v - cur) >= 0.995 and abs(v - cur) / max(abs(cur), 0.01) > 0.25)


def thanh_phan(f: dict, shares) -> str:
    t = f.get("noi_bo_12_thang_tong") or {}
    if not shares or not t:
        return ""
    p = lambda k: vnf(100 * (t.get(k) or 0) / shares)  # noqa: E731
    return (f" (khớp lệnh {p('trong_do_khop_lenh_kl')}, lệnh khối {p('trong_do_khoi_kl')}, không khai báo "
            f"{p('trong_do_chuoi_khong_khai_bao_kl')}, chưa rõ phương thức {p('trong_do_chua_ro_phuong_thuc_kl')}; "
            f"đã loại nhận qua phát hành {p('loai_nhan_qua_phat_hanh_kl')} "
            f"và chuyển nội bộ {p('loai_chuyen_noi_bo_kl')})")


def stock_lines(d: dict, f: dict) -> list:
    bc = f.get("bang_chung") or {}
    cur = bc.get("nb12_pct")
    if cur is None:
        return []
    shares = rd(STATE / "sau" / f"{f.get('key')}.json") or {}
    vals = sorted({v for s in sentences(d) for v in claims_12m(s)
                   if lech(v, cur) or (diem(v) != diem(cur) and abs(v - cur) >= 0.05)}, key=lambda v: -abs(v - cur))
    if not vals:
        return []
    cu = ", ".join(vnf(v) + "%" for v in vals[:3])
    out = [f"Bản ngày {d.get('ngay', '?')} trích nội bộ ròng 12 tháng {cu}; số hiện tại là {vnf(cur)}% số cp"
           f"{thanh_phan(f, shares.get('co_phieu_luu_hanh'))}."]
    if any(diem(v) != diem(cur) for v in vals):
        out.append(f"Điểm Chủ thể theo số trích ({'/'.join(str(diem(v)) for v in vals[:3])}) khác điểm hiện tại ({diem(cur)}): "
                   "phần nhận định về chủ thể trong bản này cần đọc lại.")
    return out


MA_NB = re.compile(r"\b([A-Z][A-Z0-9]{2})\b[^%.;]{0,25}?(?i:nội bộ|ròng)[^%.;]{0,12}?([+−\-])\s?(\d+(?:,\d+)?)\s?%")
MA_LIEN = re.compile(r"\b([A-Z][A-Z0-9]{2})\b\s?:?\s?([+−\-])\s?(\d+(?:,\d+)?)\s?%")


def basket_lines(d: dict, f: dict) -> list:
    """Trang rổ: "MÃ … nội bộ/ròng … ±x%", hoặc "MÃ ±x%" đứng liền khi câu đã nói về nội bộ/nb12 (danh sách sau hai chấm)."""
    rows = {r["ma"]: r for r in (f.get("bang_chung_tom_tat") or [])}
    out = []
    for s in sentences(d):
        hits = list(MA_NB.finditer(s)) + (list(MA_LIEN.finditer(s)) if re.search(r"nội bộ|nb12", s, re.I) else [])
        for m in hits:
            cur = (rows.get(m.group(1)) or {}).get("nb12_pct")
            v = (-1 if m.group(2) in "−-" else 1) * float(m.group(3).replace(",", "."))
            if cur is not None and lech(v, cur):
                out.append(f"{m.group(1)}: bản ngày {d.get('ngay', '?')} trích nội bộ ròng {vnf(v)}%, số hiện tại {vnf(cur)}% số cp.")
    return sorted(set(out))


def main():
    res = {}
    for p in sorted(HD.glob("*.json")):
        if p.name.startswith("_"):
            continue
        d, f = rd(p), rd(FACTS / p.name)
        if not isinstance(d, dict) or not isinstance(f, dict):
            continue
        lines = basket_lines(d, f) if p.stem in BASKETS else stock_lines(d, f)
        if lines:
            res[p.stem] = {"ngay_ban": d.get("ngay"), "dong": lines}
    out = {"tao_luc": datetime.now().strftime("%Y-%m-%d %H:%M"), "nguon": "toanvu_pe_dinh_chinh.py (tự động, không qua Claude)", "ma": res}
    (HD / "_dinh_chinh.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    doi = sorted(k for k, v in res.items() if any("Điểm Chủ thể" in x for x in v["dong"]))
    print(f"{len(res)} bản cần đính chính; đổi điểm Chủ thể: {', '.join(doi) or 'không'}")


if __name__ == "__main__":
    main()
