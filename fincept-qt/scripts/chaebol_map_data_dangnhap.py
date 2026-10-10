#!/usr/bin/env python3
"""
chaebol_map_data_dangnhap: đọc dữ liệu Vietcap IQ lấy bằng phiên ĐÃ ĐĂNG NHẬP của người dùng (state/vc_iq_dangnhap,
nạp bởi fincept_bridge/vciq_dangnhap_nap.py). CHỈ ĐỌC, không mạng.

Hai khối Vietcap khoá khi chưa đăng nhập (đo 05/10/2026):
  financial-data   Lợi nhuận KD 2023 → TTM → 2026F/2027F (năm F = dự phóng Vietcap, SS-T3)
  earning-result   KQKD luỹ kế so kế hoạch năm
  funds-holding    nhóm quỹ Vietcap theo dõi nắm mã theo tháng: KL, % tổng cp, Δ 1M/3M/6M/YTD/1Y, số quỹ
Không có tệp → {"ok": False, "ly_do": ...}.
"""
from __future__ import annotations

from chaebol_map_data_nen import bridge, read_json

CUA_SO = ("1M", "3M", "6M", "YTD", "1Y")


def _doc(tk: str, ep: str):
    d = read_json(bridge() / "state" / "vc_iq_dangnhap" / tk / f"{ep}.json", quiet=True)
    return (d.get("meta") or {}, d.get("du_lieu")) if isinstance(d, dict) else (None, None)


def financial_data(tk: str) -> dict:
    m, du = _doc(tk, "financial-data")
    if not isinstance(du, dict):
        return {"ok": False, "ly_do": "chưa có phiên đăng nhập cho " + tk}
    cols = list((du.get("revenue") or {}).keys())
    co_so = any(v is not None for k, x in du.items() if isinstance(x, dict) for v in x.values())
    return {"ok": co_so, "cot": cols, "du": du, "lay": str((m or {}).get("lay_luc") or "")[:10] or None,
            "ly_do": None if co_so else "vendor trả rỗng"}


def earning_result(tk: str) -> dict:
    m, du = _doc(tk, "earning-result")
    if not isinstance(du, dict):
        return {"ok": False, "ly_do": "chưa có phiên đăng nhập cho " + tk}
    rows = [r for r in du.get("earningData") or [] if isinstance(r, dict)]
    co_so = any(r.get(k) is not None for r in rows for k in ("prevYearValue", "currentYearForecastValue",
                                                             "currentYearCumulativeValue", "percentOfCurrentYear"))
    return {"ok": co_so, "rows": rows, "extras": du.get("extras") or {},
            "lay": str((m or {}).get("lay_luc") or "")[:10] or None}


def funds(tk: str) -> dict:
    """Chuỗi tháng (mới nhất trước): ky, so_quy, kl, pct (phần của tổng cp), gia_tri, delta{1M..1Y: (kl, gt)}."""
    m, du = _doc(tk, "funds-holding")
    if not isinstance(du, list) or not du:
        return {"ok": False, "ly_do": "chưa có phiên đăng nhập hoặc nhóm quỹ không nắm " + tk}
    out = []
    for r in du:
        ch = r.get("percentHoldingChange") or {}
        out.append({"ky": r.get("ky"), "so_quy": r.get("totalFundHolding"), "kl": r.get("quantity"),
                    "pct": r.get("percentHoldingPerTotalShares"), "gia_tri": r.get("marketValue"),
                    "gia": r.get("marketPrice"), "so_ma_trong_ky": r.get("so_ma_trong_ky"),
                    "delta": {w: ((ch.get(w) or {}).get("volume"), (ch.get(w) or {}).get("value")) for w in CUA_SO}})
    return {"ok": True, "rows": out, "lay": str((m or {}).get("lay_luc") or "")[:10] or None}
