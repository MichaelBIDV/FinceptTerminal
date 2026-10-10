#!/usr/bin/env python3
"""
chaebol_map_data — lớp dữ liệu sống, CHỈ ĐỌC, cho tab Fincept "chaebol_map" (clone Master Plan V21).

MẶT TIỀN (27/09/2026): mã đã tách sang sáu tệp con ≤800 dòng; tệp này re-export ĐÚNG mọi tên cũ (kể cả hàm cấp
thấp D._cols_of, D._prop_map, D.vc, D.V…) để tab vẫn `import chaebol_map_data as D` và gọi D.<hàm> như trước.
  chaebol_map_data_nen.py       V/can_data, bậc, định dạng JS, ngày, đường dẫn, cache, JSON/SQLite, vc_lk (Cols)
  chaebol_map_data_gia.py       giá, hệ số quyền, chuỗi tuần + VWAP, chỉ số
  chaebol_map_data_dongtien.py  NN, tự doanh, flow4, nqs_flow, Σ rổ theo tuần
  chaebol_map_data_sohuu.py     cổ đông, cơ cấu, nội bộ, quan hệ, sở hữu chéo, chi tiết mã, sự kiện vốn, sell-side
  chaebol_map_data_langkinh.py  lăng kính, CỔNG (chỉ đọc), rổ hiện hành, nhóm chaebol
  chaebol_map_data_tailieu.py   hằng V21, dữ kiện, dossier, danh mục, sổ nguồn, tỷ giá, nguồn phụ
Cài vào app: thêm CẢ BẢY tệp vào SYNC của provision_fincept.py (chép tay lần đầu — sync chỉ cập nhật tệp đã có).

Mọi hàm trả giá trị kèm nguồn: V(value, text, tier, asof, src, note, unit). Không có số → can_data(lý do):
value=None, text "[CẦN DATA]". Bậc: FACT-T1 > FACT-T2 > SS-T3 > EST > UNVERIFIED (DESIGN §6).
Stdlib, không mạng, không ghi tệp; SQLite mở '?mode=ro'. Chạy trên Python 3.11 (venv-numpy2) và 3.14.

Env: CHB_SYSTEM_DIR (gốc _System, mặc định ~/SECOND BRAIN-OBSIDIAN/_System) · CHB_TODAY=YYYY-MM-DD ·
     CHB_SKILLS_DIR (mặc định ~/.claude/skills) · CHB_SPEC_DIR (mặc định <bridge>/chaebol_map_spec).
Tài liệu API + ví dụ thật: <bridge>/chaebol_map_spec/api_data.md.
Gỡ lỗi: python3 chaebol_map_data.py demo VIC GEX MSN   (in JSON ví dụ ra stdout)
"""
from __future__ import annotations

# Tên stdlib mà module cũ để lộ ở cấp module (D.date, D.Path…): giữ để mã cũ không vỡ.
import bisect  # noqa: F401
import json
import math  # noqa: F401
import os  # noqa: F401
import re  # noqa: F401
import sqlite3  # noqa: F401
import sys
from dataclasses import asdict, dataclass  # noqa: F401
from datetime import date, datetime, timedelta  # noqa: F401
from decimal import ROUND_HALF_UP, Decimal  # noqa: F401
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:     # tệp con nằm cạnh mặt tiền
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from chaebol_map_data_nen import *  # noqa: E402,F401,F403
from chaebol_map_data_langkinh import *  # noqa: E402,F401,F403
from chaebol_map_data_tailieu import *  # noqa: E402,F401,F403
from chaebol_map_data_gia import *  # noqa: E402,F401,F403
from chaebol_map_data_dongtien import *  # noqa: E402,F401,F403
from chaebol_map_data_sohuu import *  # noqa: E402,F401,F403

SUBMODULES = ("chaebol_map_data_nen", "chaebol_map_data_gia", "chaebol_map_data_dongtien", "chaebol_map_data_sohuu",
              "chaebol_map_data_langkinh", "chaebol_map_data_tailieu")



def demo(tks: list) -> dict:
    out = {"cong": cong(), "vn30": basket("VN30"), "vnindex": index_close("VNINDEX"),
           "vnindex_pe_pb": index_pe_pb("VNINDEX"), "usd_vnd": usd_vnd(), "data_to": data_to()}
    for tk in tks:
        out[tk] = {"last_price": last_price(tk), "shares_out": shares_out(tk), "market_cap": market_cap(tk),
                   "hi_lo_52w": hi_lo_52w(tk), "pct_since_0805": pct_change(tk, "2026-05-08"),
                   "adj_factor_0805": adj_factor(tk, "2026-05-08"), "flow4_60": flow4(tk, 60),
                   "vwap": vwap_cluster(tk), "weekly_v21_last3": (weekly_v21(tk).value or [])[-3:],
                   "top_holders_3": top_holders(tk, 3), "leader": leader(tk), "lk_view_pattern": lk_view(tk).get("pattern")}
    out["warnings"] = warnings()
    return out


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "demo":
        print(json.dumps(to_jsonable(demo(sys.argv[2:] or ["VIC"])), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
