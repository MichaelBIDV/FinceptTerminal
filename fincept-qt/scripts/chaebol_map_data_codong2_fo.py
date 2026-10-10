#!/usr/bin/env python3
"""
chaebol_map_data_codong2_fo: lọc %NN (sở hữu nước ngoài) lỗi của vendor cho chaebol_map_data_codong2_gia (tách 06/10/2026
để tệp gốc ≤800 dòng). Hàm thuần trên list %NN và FOL (đơn vị điểm %), không đọc kho.
"""
from __future__ import annotations

import bisect
import statistics

from chaebol_map_data_nen import _finite

FO_SPIKE_PP, FO_SPIKE_RUN = 3.0, 10  # gai %NN vendor: đoạn ≤ 10 phiên lệch > 3 điểm % so mức hai đoạn dài kề


def _despike_fo(FO: list, FOL: list) -> tuple:
    """Gai %NN vendor (VIC 07/2011 15.2 ↔ 25.8; FPT 02/07/2010 56.4% > FOL 49%): đoạn = phiên liên tiếp chênh ≤ 3 điểm;
    đoạn ≤ 10 phiên cao (thấp) hơn mức của CẢ đoạn dài gần nhất trước và sau quá 3 điểm → bỏ %NN, FOL phiên đó (bản sao)."""
    runs, prev = [], None
    for i, x in enumerate(FO):
        if _finite(x):
            runs.append([i]) if prev is None or abs(x - FO[prev]) > FO_SPIKE_PP else runs[-1].append(i)
            prev = i
    big, drop = [k for k, r in enumerate(runs) if len(r) > FO_SPIKE_RUN], []
    for k, r in enumerate(runs):
        p = bisect.bisect_left(big, k)
        if len(r) > FO_SPIKE_RUN or p == 0 or p == len(big):
            continue
        a, z, v = FO[runs[big[p - 1]][-1]], FO[runs[big[p]][0]], [FO[i] for i in r]
        if min(v) > max(a, z) + FO_SPIKE_PP or max(v) < min(a, z) - FO_SPIKE_PP:
            drop += r
    gone = set(drop) | set(_impossible_fo(FO, FOL))
    drop = sorted(gone)
    return [None if i in gone else x for i, x in enumerate(FO)], [None if i in gone else x for i, x in enumerate(FOL)], drop


def _impossible_fo(FO: list, FOL: list) -> list:
    """%NN vendor không thể đúng (rác thời UPCoM 2018: BSR 88.3%, GVR 98.1%, BCM 97.6%, PGV 99.8%, đo 06/10/2026):
    (a) %NN vượt FOL cùng phiên quá 1 điểm; (b) %NN > 20 và > 8 lần trung vị %NN 3 năm cuối của chính mã (BSR 49.8%,
    GVR 27.7% năm 2018 khi mức thật < 2%); (c) FOL thiếu hoặc ≥ 99 mà %NN > 50 và > 3 lần trung vị. Trả chỉ số phiên bỏ."""
    tail = [x for x in FO[-750:] if _finite(x)]
    med = statistics.median(tail) if tail else None
    out = []
    for i, x in enumerate(FO):
        if not _finite(x):
            continue
        fol = FOL[i] if i < len(FOL) else None
        if _finite(fol) and fol < 99 and x > fol + 1:
            out.append(i)
        elif med is not None and ((x > 20 and x > 8 * med) or
                                  ((not _finite(fol) or fol >= 99) and x > 50 and x > 3 * med)):
            out.append(i)
    return out
