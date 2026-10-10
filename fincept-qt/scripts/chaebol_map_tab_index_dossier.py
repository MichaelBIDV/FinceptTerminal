#!/usr/bin/env python3
"""
chaebol_map_tab_index_dossier — sinh mảnh dossier "index" (DESIGN §7) cho tab VNINDEX / VN30.

Chạy tay khi cập nhật (không dùng lúc dựng; builder đọc tệp qua ctx.dossier['index']):
    PYTHONDONTWRITEBYTECODE=1 python3 scripts/chaebol_map_tab_index_dossier.py > \\
        "$SYS/knowledge_os/chaebol_map/cap_nhat_<ngày>.index.json"
Tách khỏi chaebol_map_tab_index_live 27/09 (luật ≤ ~800 dòng, api_python §9.7). Mọi mục có tier/asof/src.
"""
from __future__ import annotations

import json
import re

from chaebol_map_dom import to_fixed

from chaebol_map_tab_index_live import (CUT, FACT_TEXT, SRC_FACTS, SSI_STATUS, Live, _dm, _dmy, _fact_entry, _num,
                                        ssi_check)

GSRC = "fincept_bridge/state/vc_lk/VNINDEX/gap-chart.json"
METHOD_SRC = "Downloads/hdcv_v17_build/METHODOLOGY_LANGKINH_v1.7.md (bảng Pillar dòng 78; §đổi v1.5→v1.7 dòng 1106)"
FLOW_SRC = ("fincept_bridge/state/vc_lk/<mã>/price-history.json (foreignNetVolumeTotal, closePrice/closePriceAdjusted, "
            "totalShares) + proprietary-history.json; api_data §2.4 basket_weekly_flow(adjust=True)")


def flow_impact(D):
    """Tác động quy đổi quyền lên Σ rổ NN / TD khớp sau 08/05 (triệu cp, [thô, quy đổi]): cả các tuần sống và 5 tuần
    cuối (= cửa sổ 5 tuần mới của bảng S4). Số mã có quy đổi đọc từ note của basket_weekly_flow."""
    out = {}
    for b in ("VNINDEX", "VN30"):
        raw, adj = (D.basket_weekly_flow(b, start=CUT, adjust=a) for a in (False, True))
        r, a = ([x for x in v.value if x["monday"] > CUT] for v in (raw, adj))

        def s(rows, k):
            return round(sum(x[k] for x in rows) / 1e6, 2)
        q = re.search(r"quy về số cp hiện hành[^;]*? ở (\d+) mã", adj.note or "")
        out[b] = {"ma_quy_doi": int(q.group(1)) if q else None,
                  "tuan": "%s–%s" % (_dm(a[0]["monday"]), _dmy(a[-1]["week_end"])),
                  "nn_M": [s(r, "nn_vol"), s(a, "nn_vol")], "td_khop_M": [s(r, "td_khop_vol"), s(a, "td_khop_vol")],
                  "nn_5tuan_M": [s(r[-5:], "nn_vol"), s(a[-5:], "nn_vol")],
                  "td_khop_5tuan_M": [s(r[-5:], "td_khop_vol"), s(a[-5:], "td_khop_vol")],
                  "asof": adj.asof}
    return out


def dossier_part(D, today="2026-09-27"):
    """Dựng khối dossier từ facts_f6 + số sống (chạy tay khi cập nhật; builder đọc qua ctx.dossier['index'])."""
    fi = D.facts_index()["by_id"]
    facts = {key: _fact_entry(key, fi[v[0]]) for key, v in FACT_TEXT.items()}
    facts["liquidity"]["sua"] = "27/09 sau kiểm chứng: tách nhãn ngày — 19,0 nghìn tỷ tính tới 18/09, YTD −8,5% tới 11/09"
    s = ssi_check(D)
    pk, mn, lo, last = s["peak"], s["min"], s["lo"], s["last"]
    ex = D.index_extremes("VNINDEX", "2025-01-01")
    tr = D.index_extremes("VNINDEX", "2025-01-01", ex["peak"].asof)["min"]
    pct = (ex["peak"].value / tr.value - 1) * 100
    nohz = "nguyên văn V21 không ghi horizon nên không chấm ĐẠT/BỊ BÁC"
    claims = {
        "SSI_BASE_1920": {"claim": "SSI Research 9/5: base case VN-Index 1,920 (không ghi horizon)", "status": SSI_STATUS,
                          "evidence": "%s: đỉnh đóng %s ngày %s; nay %s (%s); %s" % (
                              "đã chạm" if s["base_hit"] else "chưa chạm", _num(pk.value), _dmy(pk.asof),
                              _num(last.value), _dmy(last.asof), nohz),
                          "tier": "FACT-T2", "asof": last.asof, "src": GSRC,
                          "sua": "27/09 sau kiểm chứng: ĐẠT → CHƯA RÕ (một phiên đóng vượt 1,920 không đủ khi thiếu "
                                 "horizon)"},
        "SSI_BEAR_1650": {"claim": "SSI Research 9/5: bear case VN-Index 1,650 (không ghi horizon)", "status": SSI_STATUS,
                          "evidence": "%s: đáy đóng sau 08/05 là %s ngày %s%s; %s" % (
                              "đã chạm" if s["bear_hit"] else "chưa chạm", _num(mn.value), _dmy(mn.asof),
                              ", trong phiên %s ngày %s" % (_num(lo[0]), _dmy(lo[1])) if lo else "", nohz),
                          "tier": "FACT-T2", "asof": mn.asof, "src": GSRC},
        "BSC5_PEAK": {"claim": "BSC ⑤ 'T4/25-Nay +61%, peak 1915 (8/5/26)'", "status": "CẬP NHẬT",
                      "evidence": "đáy đóng %s (%s) → đỉnh đóng %s (%s) = +%s%% (EST)" % (
                          _num(tr.value), _dmy(tr.asof), _num(ex["peak"].value), _dmy(ex["peak"].asof),
                          to_fixed(pct, 1)), "tier": "FACT-T2", "asof": ex["peak"].asof, "src": GSRC, "fact": "F6-005"},
    }
    lv = Live.__new__(Live)
    lv.D = D
    v = lv.vcb_pb()
    if v:
        claims["VCB_PB_10Y_LOW"] = {
            "claim": "VCB P/B 2.0× = 10-yr low (10/5/2026)", "status": "CHƯA RÕ",
            "evidence": "Vietcap ratio-daily: %s× (08/05); đáy chuỗi %s→08/05 %s× (%s); đáy mới %s× (%s); nay %s× (%s)"
                        "; cơ sở P/B nguồn gốc chưa rõ" % (
                            to_fixed(v["at"][1], 2), v["first"][0][:4], to_fixed(v["min_before"][1], 2),
                            _dmy(v["min_before"][0]), to_fixed(v["min_after"][1], 2), _dmy(v["min_after"][0]),
                            to_fixed(v["last"][1], 2), _dmy(v["last"][0])),
            "tier": "FACT-T2", "asof": v["last"][0], "src": "fincept_bridge/state/vc_lk/VCB/ratio-daily.json"}
    imp = flow_impact(D)
    texts = {
        "method_pillar4": {"text": "Toàn Vũ Pillar IV — Lăng Kính v1.7: 2/4 kênh (NN + tự doanh), hạ khỏi PRIMARY "
                                   "SIGNAL; CN/TC [CẦN DATA]; dòng nội thị trường = −(NN+TD) phần dư",
                           "tier": "EST", "asof": "2026-09-23", "src": METHOD_SRC,
                           "note": "quy ước phương pháp nội bộ (không phải số thị trường)"},
        "cutover": {"text": "≤08/05/2026 FiinTrade đóng băng; ≥11/05 giá tuần vc_lk gap-chart (VN-Index) / vnstore "
                            "nen_ngay (VN30); NN+TD Σ rổ vc_lk (EST, KL quy về số cp hiện hành); NgườiQuanSát chưa "
                            "từng nối bar — bỏ",
                    "tier": "FACT-T2", "asof": "2026-09-25",
                    "src": "fincept_bridge/chaebol_map_spec/page_p2_index_tabs.md §9.1–9.2; api_data §2.3–2.4",
                    "sua": "27/09 vòng hoàn thiện: thêm 'KL quy về số cp hiện hành' (final_check §6.1 #16)"},
        "flow_basis": {"text": "Σ rổ NN / tự doanh khớp sau 08/05: KL từng mã phiên trước GDKHQ chia/thưởng/cổ tức "
                               "CP/quyền mua quy về số cp hiện hành (hệ số share_events); FiinTrade ≤08/05 giữ KL thô",
                       "tier": "EST", "asof": imp["VNINDEX"]["asof"], "src": FLOW_SRC,
                       "sua": "27/09 vòng hoàn thiện (final_check §6.1 #16): trước đó cộng KL thô hai cơ sở qua GDKHQ",
                       "tac_dong": {b: {k: x for k, x in d.items() if k != "asof"} for b, d in imp.items()},
                       "note": "tac_dong = [thô, quy đổi], triệu cp; 'tuan' = các tuần sống; 5 tuần = cửa sổ 5 tuần "
                               "mới của bảng S4"},
    }
    return {"schema": "chaebol_map_capnhat/1", "as_of": today, "nguon_facts": [SRC_FACTS],
            "index": {"facts": facts, "claims": claims, "text": texts,
                      "applied": ["F6-001", "F6-002", "F6-003", "F6-005", "F6-006", "F6-007", "F6-008", "F6-009",
                                  "F6-023", "F6-025"],
                      "skipped": {"F6-004": "ô BUILT ở Header — thuộc shell, không phải tab index",
                                  "F6-010..F6-067 (trừ trên)": "không thay mệnh đề trong SRC 4723–5032"}}}


if __name__ == "__main__":
    import chaebol_map_data as _D
    print(json.dumps(dossier_part(_D), ensure_ascii=False, indent=1), end="")
