#!/usr/bin/env python3
"""all_in_one_mo_rong.py, các ô mở rộng của trang mã ALL-IN-ONE (lượt 4, 10/10/2026).

Mỗi ô lấy NGUYÊN dữ liệu / khối của tab gốc (chỉ đọc), không tính lại số của tab đó:
  chaebol_chart   Chaebol MAP · 02 Chart Infographic: giá tuần + VWAP 6T/12T/24T + mốc ①…⑫ (cùng hàm chọn mốc
                  chaebol_map_tab_codong_v2_chart.build_chart), KL tuần + %NN/FOL, FFT tuần với dải P10–P90
  hhp_full        Định giá HHP: dải σ P/E hoặc P/B trong không gian giá + dự phóng 36 tháng + keynote đỉnh/đáy
                  (hhp_valuation.build_ticker) + giá mục tiêu nguồn + mốc dự phóng
  pe_erp          P/E×LS Toàn Vũ: EY so với lãi suất tiền gửi (khối của toanvu_pe.build_ma, nguyên văn)
  pe_pha_*        P/E×LS Toàn Vũ: các pha giá tách EPS × P/E (khối của toanvu_pe_trang, nguyên văn)
  soros           Mô phỏng Soros: giá = EPS × P/E (tách đòn bẩy theo cửa sổ, chỉ số quy về 100 + EPS dự phóng HHP)
                  + bốn dấu hiệu đo được của khung soros_7_stage_boom_bust; không gán pha (CỔNG v1.7 DỪNG)
  reflex_*        Chaebol Reflex mở rộng (chaebol_reflex_trang.o_aio_mo_rong, phiên Reflex cung cấp)
"""
from __future__ import annotations

import bisect
import contextlib
import io
import math
import re
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import all_in_one as A
from all_in_one import (CAN, EST, T2, T3, bang, bieu_do, canh_bao, cell, ddmm, doan, mau_sign, nfc, num, o, o_so,
                        tile, trang_thai, vn)


def _ms(d):
    try:
        y, m, dd = (int(p) for p in str(d)[:10].split("-"))
        return int(datetime(y, m, dd, tzinfo=timezone.utc).timestamp() * 1000)
    except (ValueError, TypeError):
        return None


def _iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _cut(s, n):
    s = nfc(s).replace(" | ", " / ")
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _im_lang(fn, *a, **k):
    """Chạy engine của tab khác; stdout của script này là JSON aio/1 nên mọi dòng in của engine bị nuốt."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def _loi(exc):
    return f"{type(exc).__name__}: {exc}"


def _last(ys):
    for i in range(len(ys) - 1, -1, -1):
        if num(ys[i]) is not None:
            return i, ys[i]
    return None, None


def an_toan(oid, tieu_de, fn, *a, warnings=None):
    """Gọi một hàm dựng ô; lỗi bất ngờ → một ô "thieu" ghi lý do thay vì làm hỏng cả trang mã."""
    try:
        return fn(*a)
    except Exception as exc:  # noqa: BLE001
        if warnings is not None:
            warnings.append(f"Ô {oid} lỗi: {_loi(exc)}")
        return o(oid, tieu_de, [], 12, ghi_chu=f"{CAN} lỗi dựng ô: {_loi(exc)}")


# ───────────────────────────── Chaebol MAP · Chart Infographic ─────────────────────────────

KIND_NHAN = {"nb_mua": "nội bộ mua", "nb_ban": "nội bộ bán", "chuyen_giao": "chuyển giao",
             "ph_thu_tien": "phát hành thu tiền", "ph_khong_thu": "phát hành không thu tiền",
             "cp_thuong": "thưởng / cổ tức cp", "dhcd": "ĐHCĐ", "tt_dot_bien": "TT đột biến"}
KIND_VE = {"nb_mua": ("tri_up", "bull", "below"), "nb_ban": ("tri_down", "bear", "above"),
           "chuyen_giao": ("diamond", "info", "above"), "ph_thu_tien": ("diamond", "amber", "above"),
           "ph_khong_thu": ("diamond", "cyan", "above"), "cp_thuong": ("dot", "dim", "above")}
CHB = ("Chaebol MAP · 02 Chart Infographic", "chaebol_map", "Chaebol MAP")


def chaebol_data(tk):
    """(TkData, series, chart MAX, lỗi) của tab Chaebol MAP cho một mã; dùng chung cho ô chart và ô Soros."""
    try:
        import chaebol_map_data as D  # noqa: PLC0415
        import chaebol_map_tab_codong_v2 as C  # noqa: PLC0415
        import chaebol_map_tab_codong_v2_chart as CH  # noqa: PLC0415

        def run():
            td = C.TkData(SimpleNamespace(data=D, warn=lambda m: None), tk, date.today().isoformat(), {})
            s = td.series
            return td, s, (CH.build_chart(s, "MAX") if s and s.get("weeks") else None)
        td, s, res = _im_lang(run)
        return td, s, res, None
    except Exception as exc:  # noqa: BLE001, engine tab khác lỗi: ô báo thiếu, lưới vẫn dựng
        return None, None, None, _loi(exc)


def _bac_moc(inf):
    """Bậc của % vốn một mốc theo đúng nguồn Chaebol MAP: dòng nội bộ = size_tier, cặp chuyển giao = pct.tier,
    sự kiện vốn = tỷ lệ phát hành (EST); thiếu → [CẦN DATA]."""
    t = inf.get("t")
    if t == "row":
        return nfc(inf.get("size_tier")) or EST
    if t == "pair":
        return nfc(getattr((inf.get("p") or {}).get("pct"), "tier", "")) or CAN
    return EST if t == "cap" else CAN


def _k(v):
    return round(v / 1000, 3) if isinstance(v, (int, float)) and v > 0 else None


def o_chaebol_chart(tk, cb):
    td, s, res, err = cb
    weeks = (s or {}).get("weeks") or []
    if len(weeks) < 5:
        return o("chaebol_chart", "Chart Infographic · cụm cổ đông + VWAP", [], 12, *CHB,
                 ghi_chu=f"{CAN} {err or 'chưa có chuỗi tuần của mã (vc_lk / vnstore)'}")
    xs = [str(w.get("we") or w.get("w"))[:10] for w in weeks]
    ws = [str(w.get("w"))[:10] for w in weeks]
    c = [_k(w.get("c")) for w in weeks]

    def idx(d):
        i = bisect.bisect_right(ws, str(d or "")[:10]) - 1
        return i if 0 <= i < len(c) and c[i] is not None else None
    size_of = {m.get("ref"): m.get("size") for m in s.get("markers") or []}
    info = getattr(td, "marker_info", {}) or {}
    ann, legend_rows = [], []
    for lg in (res or {}).get("legend") or []:
        i = idx(lg.get("date"))
        kind = lg.get("kind")
        sz = size_of.get(lg.get("ref"))
        inf = info.get(lg.get("ref")) or {}
        own = (inf.get("r") or {}).get("own_after") if inf.get("t") == "row" else None
        bac = _bac_moc(inf) if num(sz) is not None else ""
        nhan = KIND_NHAN.get(kind, kind)
        legend_rows.append([cell(lg.get("glyph") or "", "vang", dam=True), cell(ddmm(lg.get("date"))),
                            cell(nhan, mono=False), cell(_cut(lg.get("label"), 80), mono=False, tip=nfc(lg.get("label"))),
                            cell(vn(abs(sz), 2, suffix="%") if num(sz) is not None else ""), cell(bac, "xam"),
                            cell(vn(own, 2, suffix="%") if num(own) is not None else "")])
        if i is None:
            continue
        mk, mau, pos = KIND_VE.get(kind, ("dot", "dim", "above"))
        ann.append({"kind": "point", "x": _ms(xs[i]), "y": c[i], "marker": mk, "pos": pos, "mau": mau, "uu_tien": 1,
                    "text": lg.get("glyph") or "",
                    "tip": " | ".join(x for x in (
                        f"{lg.get('glyph')} {ddmm(lg.get('date'))} · {nhan}", _cut(lg.get("label"), 140),
                        f"{vn(abs(sz), 2)}% {'tỷ lệ phát hành' if inf.get('t') == 'cap' else 'vốn'} ({bac})"
                        if num(sz) is not None else "",
                        f"sở hữu sau {vn(own, 2)}% (theo công bố)" if num(own) is not None else "") if x)})
    so = {x.get("id"): x for x in (res or {}).get("numbers") or []}
    for key, mk, mau, pos in (("ath", "tri_down", "warn", "above"),):
        x = so.get(key)
        i = idx(x.get("date")) if x else None
        if i is not None:
            ann.append({"kind": "point", "x": _ms(xs[i]), "y": c[i], "marker": mk, "pos": pos, "mau": mau, "uu_tien": 2,
                        "text": f"Đỉnh LS {vn(c[i], 1)}", "tip": f"Đỉnh lịch sử đóng tuần {vn(c[i], 1)} nghìn đồng · {ddmm(x['date'])}"})
    last = weeks[-1]
    gia = {"x": xs, "left": {"label": "nghìn đồng (điều chỉnh)"}, "series": [
        {"name": "Đóng tuần (điều chỉnh)", "y": c, "style": "line", "mau": "ink"},
        {"name": "VWAP 6T", "y": [_k(w.get("v6")) for w in weeks], "style": "thin", "mau": "up"},
        {"name": "VWAP 12T", "y": [_k(w.get("v12")) for w in weeks], "style": "thin", "mau": "amber"},
        {"name": "VWAP 24T", "y": [_k(w.get("v24")) for w in weeks], "style": "dash", "mau": "down"}], "annotations": ann}
    fol = [num(w.get("fol")) if (num(w.get("fol")) or 0) > 0 else None for w in weeks]
    kl = {"x": xs, "left": {"label": "KL khớp tuần (triệu cp)", "min": 0}, "right": {"label": "% vốn", "min": 0},
          "series": [{"name": "KL khớp tuần", "y": [round(w["vol"] / 1e6, 3) if num(w.get("vol")) else None for w in weeks],
                      "style": "bar", "mau": "grey", "alpha": 0.5},
                     {"name": "%NN sở hữu", "y": [num(w.get("fo")) for w in weeks], "style": "line", "mau": "blue",
                      "axis": "right"},
                     {"name": "Room NN (FOL)", "y": fol, "style": "dash", "mau": "violet", "axis": "right"}]}
    khoi_chart = [bieu_do(f"{tk} · giá tuần + VWAP cụm + mốc cổ đông ①…⑫", gia,
                          f"{len(xs)} tuần {ddmm(xs[0])} → {ddmm(xs[-1])} · thang tuyến tính (tab gốc vẽ log) · ①…⑫: "
                          "tối đa 12 mốc có % vốn lớn nhất (trừ ĐHCĐ, tuần thoả thuận đột biến), đánh số theo ngày; rê "
                          "chuột lên mốc để đọc chủ thể và % vốn",
                          "Chaebol MAP (chaebol_map_tab_codong_v2) · giá vc_lk điều chỉnh · VWAP cụm EST",
                          f"{T2} {EST}", 420),
                  bieu_do("KL khớp tuần · %NN sở hữu · room NN", kl, "Cột xám = KL khớp tuần (trục trái); %NN và FOL "
                          "(trục phải)", "Chaebol MAP · vc_lk price-history (foreignRoom/foreignOwnership)", T2, 220)]
    if any(num(w.get("fw")) is not None for w in weeks):
        ff = {"x": xs, "left": {"label": "FFT tuần"}, "series": [
            {"name": "Dải P10–P90", "style": "band", "y_lo": [num(w.get("p10")) for w in weeks],
             "y_hi": [num(w.get("p90")) for w in weeks], "mau": "grey", "alpha": 0.18},
            {"name": "FFT tuần", "y": [num(w.get("fw")) for w in weeks], "style": "line", "mau": "amber"},
            {"name": "TB 4 tuần", "y": [num(w.get("ma4")) for w in weeks], "style": "thin", "mau": "blue"}]}
        khoi_chart.append(bieu_do("FFT tuần với dải P10–P90", ff, nfc(s.get("fft_note")) or "FFT là proxy giá/KL",
                                  "Lăng kính FFT qua Chaebol MAP", EST, 220))
    elif s.get("fft_warn"):
        khoi_chart.append(doan(nfc(s.get("fft_warn")), "xam"))
    v6, v12, v24, px = (_k(last.get(k)) for k in ("v6", "v12", "v24", "c"))
    ath = so.get("ath") or {}
    i_ath = idx(ath.get("date"))
    xong = [w for w in weeks if _week_done(w, date.today())]
    vols = [num(w.get("vol")) or 0 for w in xong[-21:-1]]
    w_kl = xong[-1] if len(xong) >= 21 and num(xong[-1].get("vol")) else None
    pos = td.pos if td is not None and getattr(td, "pos", None) and td.pos.get("ok") else {}
    fo_v, fol_v, room_v = pos.get("fo"), pos.get("fol"), pos.get("room_pct")
    tiles = [
        tile(f"Đóng tuần {ddmm(xs[-1], False)}", vn(px, 1),
             f"đỉnh lịch sử {vn(c[i_ath], 1)} ({ddmm(ath.get('date'))}) · cách {vn((px / c[i_ath] - 1) * 100, 1, True, '%')}"
             if i_ath is not None and px else "", None, T2),
        tile("VWAP 6T / 12T / 24T", f"{vn(v6, 1)} / {vn(v12, 1)} / {vn(v24, 1)}" if v6 else "",
             " · ".join(f"{n} {vn((px / v - 1) * 100, 1, True, '%')}" for n, v in (("so 6T", v6), ("12T", v12), ("24T", v24))
                        if v and px), None, EST),
        tile("%NN sở hữu / trần NN (FOL)", f"{vn(getattr(fo_v, 'value', None), 1, suffix='%')} / "
             f"{vn(getattr(fol_v, 'value', None), 1, suffix='%')}" if getattr(fo_v, "value", None) is not None else "",
             f"room còn {vn(room_v.value, 1)}% số cp (foreignCurrentRoom ÷ số cp, {room_v.tier}) · "
             f"{ddmm(getattr(fo_v, 'asof', ''), False)}" if getattr(room_v, "value", None) is not None else "", None, T2),
        tile("KL tuần đã đóng ÷ TB 20 tuần", vn(w_kl["vol"] / (sum(vols) / 20), 2, suffix="×") if w_kl and sum(vols) else "",
             f"tuần {ddmm(w_kl.get('we'), False)} · {vn(w_kl['vol'] / 1e6, 2)} triệu cp (cùng phép đo S3 của ô Soros)"
             if w_kl else "", None, EST),
    ]
    khoi = [o_so(tiles, 4)] + khoi_chart
    if legend_rows:
        khoi.append(bang(["#", "Ngày", "Loại", "Chủ thể / nội dung", "% vốn", "Bậc %", "Sở hữu sau"], legend_rows,
                         "Bảng ①…⑫ cùng hàm chọn mốc của tab Chaebol MAP; % vốn = |KL| ÷ số cp tại ngày (sự kiện vốn: tỷ lệ "
                         "phát hành), bậc theo nguồn; sở hữu sau theo công bố của dòng nội bộ.", can_phai=[4, 6]))
    return o("chaebol_chart", "Chart Infographic · cụm cổ đông + VWAP (Chaebol MAP)", khoi, 12, *CHB, f"{T2} {EST}",
             trang_thai(xs[-1], 9))


# ───────────────────────────── Định giá HHP · đầy đủ ─────────────────────────────

HHP = ("Định giá HHP · vùng P/E · P/B", "hhp_valuation", "Định giá HHP")


def hhp_data(tk):
    try:
        import hhp_valuation as H  # noqa: PLC0415
        return _im_lang(H.build_ticker, H.data_dir(), tk), None
    except Exception as exc:  # noqa: BLE001
        return None, _loi(exc)


def _degen(x):
    return not ((x.get("chart") or {}).get("price")) or (num(x.get("mean")) or 0) - 2 * (num(x.get("sd")) or 0) <= 0


def chon_thuoc_do(r, sau):
    hh = ((sau or {}).get("hhp") or {}).get("thuoc_do")
    if hh in ("pe", "pb") and ((r.get(hh) or {}).get("chart") or {}).get("price"):
        return hh
    for m in ("pe", "pb"):
        if not _degen(r.get(m) or {}):
            return m
    return "pe" if ((r.get("pe") or {}).get("chart") or {}).get("price") else "pb"


def _keynote_tip(k):
    return " | ".join(x for x in (nfc(k.get("title")), _cut(k.get("boi_canh"), 260), _cut(k.get("nguyen_nhan"), 220),
                                  _cut(k.get("sau_do"), 160)) if x)


def o_hhp_full(tk, r, err, sau):
    m = chon_thuoc_do(r, sau) if r else "pe"
    x = (r or {}).get(m) or {}
    ch = x.get("chart") or {}
    if not ch.get("price"):
        return o("hhp_full", "Định giá HHP · vùng định giá, keynote, dự phóng 3 năm", [], 12, *HHP,
                 ghi_chu=f"{CAN} {err or 'mã ngoài chuỗi của engine HHP (hhp_vn100_series)'}")
    nm = "P/E" if m == "pe" else "P/B"
    fc = ((r.get("forecast") or {}).get(m) or {})
    pts = fc.get("points") or {}
    ms_all = sorted({p[0] for p in ch["price"]} | {p[0] for p in pts.get("fair") or []})
    xs = [_iso(t) for t in ms_all]

    def col(src, key):
        mp = {p[0]: p[1] for p in src.get(key) or []}
        return [mp.get(t) for t in ms_all]
    gia = col(ch, "price")
    ann = []
    for k in r.get("keynotes") or []:
        t = num(k.get("ms")) or _ms(k.get("date"))
        y = next((num(n.get("v")) for n in k.get("numbers") or [] if n.get("k") == "close"), None)
        if y is None and t:
            i = bisect.bisect_right(ms_all, t) - 1
            y = gia[i] if 0 <= i < len(gia) else None
        if not t or y is None:
            continue
        dinh = k.get("kind") == "dinh"
        tam = bool(k.get("provisional"))
        ann.append({"kind": "point", "x": t, "y": y, "marker": "tri_down" if dinh else "tri_up",
                    "pos": "above" if dinh else "below", "mau": "warn" if tam else ("bear" if dinh else "bull"),
                    "uu_tien": max(1, min(3, int(num(k.get("priority")) or 2))),
                    "text": nfc(k.get("title")).split(" · ")[0] + (" (tạm)" if tam and "tạm" not in nfc(k.get("title")) else ""),
                    "tip": _keynote_tip(k)})
    for tg in (r.get("forecast") or {}).get("targets") or []:
        if num(tg.get("ms")) and num(tg.get("value")):
            ann.append({"kind": "point", "x": tg["ms"], "y": tg["value"], "marker": "diamond", "mau": "info", "uu_tien": 3,
                        "text": nfc(tg.get("label")),
                        "tip": f"{nfc(tg.get('org'))} {ddmm(tg.get('date'))} · giá mục tiêu nguồn {vn(tg.get('value_vnd'), 0)} đ "
                               f"· kỳ hạn {ddmm(tg.get('horizon'))} | {_cut(tg.get('note'), 120)} | {tg.get('tier') or T3}"})
    lo_x, hi_x = ms_all[0], ms_all[-1]
    ann = [a for a in ann if lo_x <= a["x"] <= hi_x]
    hom_nay = _ms(date.today().isoformat())
    if lo_x <= hom_nay <= hi_x:
        ann.append({"kind": "vline", "x": hom_nay, "mau": "dim", "style": "dot", "text": "hôm nay"})
    co_fc = bool(pts.get("fair"))
    goc = "EPS" if m == "pe" else "BVPS"
    het_fc = _iso(pts["fair"][-1][0])[:7] if co_fc else ""
    block = {"x": xs, "left": {"label": "nghìn đồng (giá điều chỉnh)", "min": 0}, "series": [
        {"name": "±2σ", "style": "band", "y_lo": col(ch, "cheap2"), "y_hi": col(ch, "rich2"), "mau": "grey", "alpha": 0.08},
        {"name": "±1σ", "style": "band", "y_lo": col(ch, "cheap1"), "y_hi": col(ch, "rich1"), "mau": "blue", "alpha": 0.14},
        {"name": f"μ {nm} × {goc} (giá hợp lý)", "y": col(ch, "fair"), "style": "dash", "mau": "blue"},
        {"name": "Giá điều chỉnh", "y": gia, "style": "line", "mau": "amber"}], "annotations": ann}
    if co_fc:
        block["series"][2:2] = [{"name": f"Dự phóng ±1σ (dải dịch theo {goc} dự phóng)", "style": "band",
                                 "y_lo": col(pts, "cheap1"), "y_hi": col(pts, "rich1"), "mau": "violet", "alpha": 0.12}]
        block["series"].insert(-1, {"name": "Dự phóng μ", "y": col(pts, "fair"), "style": "dot", "mau": "violet"})
    row = (r.get("row") or {}).get(m) or {}
    ms_fc = fc.get("milestones") or []
    kn = sorted(r.get("keynotes") or [], key=lambda k: str(k.get("date")), reverse=True)
    tiles = [
        tile(f"Vị trí {nm} so trung bình lịch sử", vn(x.get("sigma"), 2, True, "σ"),
             f"{vn(x.get('now'), 2)}x · μ {vn(x.get('mean'), 2)} · σ {vn(x.get('sd'), 2)} · {x.get('zone') or ''}",
             A.zone_mau(x.get("zone")), EST),
        tile("Giá ứng với bội số trung bình", vn(row.get("band_fair"), 0),
             f"μ × {goc} hôm nay (±1σ {vn(row.get('band_cheap1'), 0)} đến {vn(row.get('band_rich1'), 0)} đ); không phải giá "
             "mục tiêu" if row else "", None, EST),
        tile(f"Bội số trung bình × {goc} dự phóng {ms_fc[-1]['date'][:4]}" if ms_fc else "Bội số trung bình × dự phóng",
             vn((ms_fc[-1].get("fair") or 0) * 1000, 0) if ms_fc else "",
             f"dải dịch theo {goc} dự phóng, không phải giá mục tiêu" if ms_fc else f"{CAN} engine HHP chưa có dự phóng",
             None, EST),
        tile("Keynote gần nhất", nfc(kn[0].get("title")).split(" · ")[0] if kn else "",
             _cut(kn[0].get("sau_do"), 90) if kn else "", None, EST),
    ]
    khoi = [o_so(tiles, 4), bieu_do(
        f"{tk} · dải σ {nm} trong không gian giá" + (" + dự phóng 36 tháng" if co_fc else "") + " + keynote đỉnh/đáy", block,
        "▲ đáy ▼ đỉnh: keynote của engine HHP (rê chuột hoặc bấm mốc để ghim bảng bối cảnh, nguyên nhân, diễn biến sau đó)"
        + (f" · ◆ giá mục tiêu của nguồn tại kỳ hạn · dải tím = μ ± 1σ dịch theo {goc} dự phóng tới {het_fc}" if co_fc
           else f" · {CAN} engine HHP chưa có dự phóng cho mã này"),
        "engine HHP · hhp_valuation.build_ticker (keynotes, forecast)", f"{T2} {EST}", 460)]
    if kn:
        khoi.append(bang(["Ngày", "Loại", "Mốc", "Sau đó"], [
            [cell(ddmm(k.get("date"))), cell("đỉnh" if k.get("kind") == "dinh" else "đáy",
                                             "do" if k.get("kind") == "dinh" else "xanh", pill=True),
             cell(nfc(k.get("title")) + (" (tạm)" if k.get("provisional") and "tạm" not in nfc(k.get("title")) else ""),
                  mono=False, tip=_keynote_tip(k)),
             cell(_cut(k.get("sau_do"), 140), mono=False)] for k in kn[:15]],
            "Rê chuột lên tên mốc để đọc bối cảnh và nguyên nhân; số liệu từng mốc theo bậc ghi trong engine HHP."))
    if ms_fc:
        def band_cell(v):
            return cell("suy biến", "xam") if v is None or v <= 0.05 * (num(ms_fc[0].get("fair")) or 1) else cell(vn(v * 1000, 0))
        khoi.append(bang([f"Mốc dự phóng ({nm})", f"{goc} (nghìn)", "TB − 2 ĐLC", "TB − 1 ĐLC", "Trung bình", "TB + 1 ĐLC",
                          "TB + 2 ĐLC"], [
            [cell(ddmm(mm.get("date"))), cell(vn(mm.get("base"), 3))] +
            [band_cell(num(mm.get(k))) for k in ("cheap2", "cheap1", "fair", "rich1", "rich2")] for mm in ms_fc],
            f"Giá (đồng) tại mốc nếu bội số giữ trung bình (μ) ± k độ lệch chuẩn (ĐLC, σ) của lịch sử mã; {goc} nối theo tăng "
            "trưởng đồng thuận (bậc từng năm ở engine HHP). Không phải dự báo giá.", can_phai=[1, 2, 3, 4, 5, 6]))
    fw = r.get("forward") or {}
    nam = sorted({y for k in ("pe", "pb", "roe") for y in (fw.get(k) or {})})
    if nam:
        khoi.append(bang(["Năm", "P/E forward", "P/B forward", "ROE"], [
            [cell(y), cell(vn((fw.get("pe") or {}).get(y), 2, suffix="x")), cell(vn((fw.get("pb") or {}).get(y), 2, suffix="x")),
             cell(vn((fw.get("roe") or {}).get(y), 1, suffix="%"))] for y in nam],
            f"Nguồn forward: {', '.join(sorted({nfc(v) for v in (fw.get('src') or {}).values() if v})) or 'không rõ'} (SS-T3) · {nfc(fw.get('note'))}",
            can_phai=[1, 2, 3]))
    cav = ((r.get("forecast") or {}).get("meta") or {}).get("caveats") or []
    khoi.append(canh_bao("Đọc dự phóng", [nfc(c) for c in cav[:3]], "xam"))
    return o("hhp_full", f"Định giá HHP · vùng {nm}, keynote đỉnh/đáy, dự phóng 3 năm", khoi, 12, *HHP, f"{T2} {EST}",
             trang_thai(x.get("as_of"), 4))


# ───────────────────────────── P/E × LS Toàn Vũ · ERP và các pha ─────────────────────────────

TV = ("P/E×LS Toàn Vũ", "toanvu_pe", "P/E×LS TV")


def tv_page(tk):
    try:
        import toanvu_pe as TVM  # noqa: PLC0415
        return _im_lang(TVM.build_ma, tk), None
    except Exception as exc:  # noqa: BLE001, TvError: mã ngoài tệp Bloomberg HOSE
        return None, (nfc(getattr(exc, "message", "")) or _loi(exc))


def _sec(page, sid):
    return next((s for s in ((page or {}).get("trang") or {}).get("sections") or [] if s.get("id") == sid), None)


def _tv_tt(page):
    return trang_thai(((page or {}).get("meta") or {}).get("data_to"), 9)


def _ls_moi_nhat():
    """Ngày LS FiinProX mới nhất trong bộ Toàn Vũ (tong_quan.nguon.fiinprox.moi_nhat), sau ngày đó LS được giữ nguyên."""
    t = A.read_json(A.BRIDGE / "state" / "toanvu_pe" / "tong_quan.json") or {}
    return ((((t.get("nguon") or {}).get("fiinprox") or {}).get("moi_nhat")) or {}).get("ngay")


def o_pe_erp(tk, page, err, tv=None):
    s = _sec(page, "bieu_do")
    b = next((x for x in (s or {}).get("khoi") or [] if x.get("kieu") == "bieu_do"
              and nfc(x.get("tieu_de")).startswith("EY so với")), None)
    if not b:
        return o("pe_erp", "EY so với lãi suất tiền gửi (ERP của mã)", [], 12, *TV,
                 ghi_chu=f"{CAN} {err or 'trang P/E×LS không có biểu đồ EY'} (chỉ mã có trong tệp Bloomberg HOSE của Toàn Vũ)")
    blk = b["block"]
    ch = (tv or {}).get("chuoi") or {}
    xs_g, ey, ls = ch.get("x") or blk.get("x") or [], ch.get("ey") or [], ch.get("ls") or []
    if not ey:   # không có chuỗi gốc: đọc từ khối biểu đồ (đã chèn điểm cắt nên chỉ để lấy số cuối)
        ser = {x.get("name"): x.get("y") or [] for x in blk.get("series") or []}
        xs_g = blk.get("x") or []
        ey = next((v for k, v in ser.items() if str(k).startswith("EY")), [])
        ls = next((v for k, v in ser.items() if str(k).startswith("LS")), [])
    i_ey, v_ey = _last(ey)
    if i_ey is None:
        return o("pe_erp", nfc(b.get("tieu_de")), [], 12, *TV,
                 ghi_chu=f"{CAN} chuỗi P/E Bloomberg của {tk} không có điểm hữu hạn nào (EY trống)")
    v_ls = ls[i_ey] if i_ey < len(ls) and num(ls[i_ey]) is not None else None
    ngay_ls = _ls_moi_nhat()
    pairs = [(e, l) for e, l in zip(ey, ls) if num(e) is not None and num(l) is not None]
    duong = sum(1 for e, l in pairs if e > l)
    erp = v_ey - v_ls if v_ls is not None else None
    d_ey = ddmm(xs_g[i_ey], False) if i_ey < len(xs_g) else ""
    tiles = [
        tile(f"EY = 100 / P/E · {d_ey}", vn(v_ey, 2, suffix="%"), "lợi suất lợi nhuận của cổ phiếu (Bloomberg)", None,
             f"{T2} {EST}"),
        tile(f"LS huy động >12T · {ddmm(ngay_ls, False)}" if ngay_ls else "LS huy động >12T", vn(v_ls, 2, suffix="%"),
             f"cao nhất các NH (FiinProX, chuỗi tháng), giữ nguyên tới {d_ey}" if ngay_ls else "cao nhất các NH (FiinProX)",
             None, T2),
        tile("ERP = EY − LS", vn(erp, 2, True, " điểm"),
             f"EY {d_ey} − LS {ddmm(ngay_ls, False)}" if erp is not None and ngay_ls else "", mau_sign(erp, 0.0), EST),
        tile("Tỷ lệ tuần ERP dương", vn(100 * duong / len(pairs), 0, suffix="%") if pairs else "",
             f"{len(pairs)} tuần có cả EY và LS (chuỗi gốc, không tính điểm cắt của biểu đồ)", None, EST),
    ]
    return o("pe_erp", nfc(b.get("tieu_de")), [o_so(tiles, 4), b], 12, *TV, f"{T2} {EST}", _tv_tt(page))


def o_pe_pha(tk, page, err):
    s = _sec(page, "pha")
    if not s:
        return [o("pe_pha_gia", "Vì sao giá đi như vậy · các pha EPS × P/E", [], 12, *TV,
                  ghi_chu=f"{CAN} {err or 'lớp sâu P/E×LS chưa có pha cho mã'} (chỉ mã có trong tệp Bloomberg HOSE)")]
    kh = s.get("khoi") or []
    doc = [b for b in kh if b.get("kieu") == "doan" and not b.get("tieu_de")][:1]
    gia = [b for b in kh if b.get("kieu") == "bieu_do" and (b.get("block") or {}).get("loai") != "cot"]
    tach = [b for b in kh if b.get("kieu") == "bieu_do" and (b.get("block") or {}).get("loai") == "cot"]
    bg = [b for b in kh if b.get("kieu") == "bang"]
    lich = [b for b in kh if b.get("kieu") == "doan" and b.get("tieu_de")]
    eb = nfc(s.get("eyebrow")) or TV[0]
    tt = _tv_tt(page)
    return [o("pe_pha_gia", nfc(s.get("tieu_de")) or "Các pha EPS × P/E", doc + gia, 7, eb, TV[1], TV[2], f"{T2} {EST}", tt),
            o("pe_pha_tach", "Tách lợi suất các pha gần nhất: giá = EPS × P/E", tach, 5, eb, TV[1], TV[2], EST, tt),
            o("pe_pha_bang", "Bảng các pha: giá, EPS, P/E, động lực, LS, nội bộ ròng", bg + lich, 12, eb, TV[1], TV[2],
              f"{T2} {EST}", tt)]


# ───────────────────────────── Soros mô phỏng ─────────────────────────────

SOROS_ID = "soros_7_stage_boom_bust"
PHEP = {">=": lambda a, b: a >= b, ">": lambda a, b: a > b, "<=": lambda a, b: a <= b, "<": lambda a, b: a < b}
SOROS = ("Soros / Shiller · phản thân", "msn_reflex", "Chaebol Reflex")
CUA_SO = ((13, "13 tuần"), (52, "52 tuần"), (156, "3 năm"))


def _eps_series(r):
    """[(ms, giá, EPS 4 quý)] từ dải P/E của engine HHP: μ-band = μ × EPS ⇒ EPS = fair ÷ μ (nghìn đồng)."""
    x = (r or {}).get("pe") or {}
    mu = num(x.get("mean"))
    ch = x.get("chart") or {}
    if not mu or mu <= 0:
        return []
    fair = {p[0]: p[1] for p in ch.get("fair") or []}
    return [(t, p, fair[t] / mu) for t, p in ch.get("price") or [] if num(p) and num(fair.get(t))]


def _tach(a, b):
    p0, e0, p1, e1 = a[1], a[2], b[1], b[2]
    if not all(v and v > 0 for v in (p0, e0, p1, e1)):
        return None
    lp, le = math.log(p1 / p0), math.log(e1 / e0)
    return {"gp": p1 / p0 - 1, "ge": e1 / e0 - 1, "gpe": (p1 / e1) / (p0 / e0) - 1, "le": le, "lpe": lp - le}


def _don_bay(t):
    lp = t["le"] + t["lpe"]
    if t["le"] * t["lpe"] < 0 and abs(lp) < 0.25 * max(abs(t["le"]), abs(t["lpe"])):
        return "hai đòn bẩy triệt tiêu nhau", "xam"
    if t["le"] > 0 and t["lpe"] > 0:
        return "double-click lên (EPS ↑ × P/E ↑)", "xanh"
    if t["le"] < 0 and t["lpe"] < 0:
        return "double-click xuống (EPS ↓ × P/E ↓)", "do"
    return ("chủ yếu do EPS", "lam") if abs(t["le"]) >= abs(t["lpe"]) else ("chủ yếu do P/E", "vang")


def _week_done(w, today):
    try:
        return date.fromisoformat(str(w.get("we"))[:10]) >= date.fromisoformat(str(w.get("w"))[:10]) + timedelta(days=4) \
            or date.fromisoformat(str(w.get("w"))[:10]) + timedelta(days=7) <= today
    except ValueError:
        return False


def _dau_hieu(d, r, weeks):
    """(giá trị text, thoả True/False/None, ngày) của một dấu hiệu đo được; cùng nghĩa với chaebol_reflex_live."""
    key, ts = nfc(d.get("phep_do")), d.get("tham_so") or {}
    if key == "pb_sigma":
        x = (r or {}).get("pb") or {}
        m = "P/B"
        if x.get("sigma") is None:
            x, m = (r or {}).get("pe") or {}, "P/E"
        z = num(x.get("sigma"))
        s = next((num(ts.get(k)) for k in ("s", "nguong", "muc") if num(ts.get(k)) is not None), 1.0)
        if z is None:
            return f"{CAN} σ HHP", None, None
        # như chaebol_reflex_live.do_dau_hieu: s ≥ 0 = phía đắt (z ≥ s), s < 0 = phía rẻ (z ≤ s); "phep" hợp lệ thì thắng
        phep = ts.get("phep") if ts.get("phep") in PHEP else (">=" if s >= 0 else "<=")
        if phep in ("<", "<=") and (num(x.get("mean")) or 0) - 2 * (num(x.get("sd")) or 0) <= 0:
            return f"{CAN} dải σ suy biến (−2σ ≤ 0), chỉ chấm phía đắt", None, x.get("as_of")
        return f"{m} {vn(z, 2, True, 'σ')}", PHEP[phep](z, s), x.get("as_of")
    done = [w for w in weeks if _week_done(w, date.today())]
    if key == "kl_tuan_tb20":
        k = num(ts.get("k")) or 1.5
        if len(done) < 21 or not num(done[-1].get("vol")):
            return f"{CAN} KL tuần", None, None
        tb = sum(num(w.get("vol")) or 0 for w in done[-21:-1]) / 20
        q = done[-1]["vol"] / tb if tb else None
        return (f"{vn(q, 2)}× TB20", (q >= k) if q is not None else None, done[-1].get("we"))
    if key == "nn_rong_4t":
        v = [num(w.get("nn_w")) for w in done[-4:]]
        if len(v) < 4 or any(x is None for x in v):
            return f"{CAN} NN ròng tuần", None, None
        tong = sum(v)
        return f"{vn(tong / 1e9, 1, True)} tỷ đồng", tong > 0, done[-1].get("we")
    return f"{CAN} phép đo {key}", None, None


def o_soros(tk, r, cb):
    _, s, _, _ = cb
    weeks = (s or {}).get("weeks") or []
    try:
        import chaebol_reflex_khung as K  # noqa: PLC0415
        lib, _ = K.load_khung()
        e = K.khung_entry(lib, SOROS_ID) or {}
    except Exception as exc:  # noqa: BLE001
        K, e = None, {}
        loi_khung = _loi(exc)
    else:
        loi_khung = "" if e else f"không thấy khung {SOROS_ID} trong khung.json"
    pts = _eps_series(r)
    khoi = [doan("Giá = EPS × P/E nên một đợt định giá lại lớn đến từ hai đòn bẩy nhân nhau ('double-click'). Ô này tách "
                 "đòn bẩy trên dữ liệu của chính mã và đo bốn dấu hiệu có phép đo của khung Soros 7 pha. Không gán mã vào "
                 "pha nào: CỔNG v1.7 đang DỪNG, và bốn dấu hiệu không đủ để suy thứ tự pha.", "xam")]
    if len(pts) >= 20:
        rows = []
        for n, nhan in CUA_SO:
            t0 = pts[-1][0] - n * 7 * 86400000
            i0 = bisect.bisect_left([p[0] for p in pts], t0)
            if i0 >= len(pts) - 1:
                continue
            t = _tach(pts[i0], pts[-1])
            if not t:
                rows.append([cell(nhan, dam=True), cell(ddmm(_iso(pts[i0][0]))), cell("EPS ≤ 0, không tách được", "xam",
                                                                                     mono=False), cell(""), cell(""), cell("")])
                continue
            db, mau = _don_bay(t)
            rows.append([cell(nhan, dam=True), cell(ddmm(_iso(pts[i0][0]))),
                         cell(vn(t["gp"] * 100, 1, True, "%"), mau_sign(t["gp"])),
                         cell(vn(t["ge"] * 100, 1, True, "%"), mau_sign(t["ge"])),
                         cell(vn(t["gpe"] * 100, 1, True, "%"), mau_sign(t["gpe"])), cell(db, mau, pill=True)])
        khoi.append(bang(["Cửa sổ", "Từ", "Giá", "EPS 4 quý", "P/E", "Đòn bẩy"], rows,
                         "(1 + giá) = (1 + EPS) × (1 + P/E). EPS 4 quý suy từ dải μ của engine HHP (μ-band ÷ μ P/E), "
                         "cùng nguồn với ô định giá.", can_phai=[2, 3, 4]))
        n3 = [p for p in pts if p[0] >= pts[-1][0] - 156 * 7 * 86400000 and p[2] > 0]
        fc = (((r.get("forecast") or {}).get("pe") or {}).get("base_path")) or []
        fc = [p for p in fc if num(p[1]) and p[1] > 0 and n3 and p[0] > n3[-1][0]]
        if len(n3) >= 10:
            b0 = n3[0]

            def lg(v, v0):
                return round(100 * math.log(v / v0), 1)
            ms_all = [p[0] for p in n3] + [p[0] for p in fc]
            pad = [None] * len(fc)
            blk = {"x": [_iso(t) for t in ms_all], "left": {"label": "lũy kế từ đầu khung (log × 100)"}, "series": [
                {"name": "Giá", "y": [lg(p[1], b0[1]) for p in n3] + pad, "style": "line", "mau": "amber"},
                {"name": "Phần EPS 4 quý", "y": [lg(p[2], b0[2]) for p in n3] + pad, "style": "line", "mau": "up"},
                {"name": "Phần P/E", "y": [lg(p[1] / p[2], b0[1] / b0[2]) for p in n3] + pad, "style": "line", "mau": "blue"},
                {"name": "EPS dự phóng (HHP, đồng thuận)", "y": [None] * (len(n3) - 1) + [lg(n3[-1][2], b0[2])]
                 + [lg(p[1], b0[2]) for p in fc], "style": "dot", "mau": "up"}],
                "annotations": [{"kind": "hband", "y0": -0.5, "y1": 0.5, "mau": "dim", "alpha": 0.5, "text": "0"},
                                {"kind": "vline", "x": n3[-1][0], "mau": "dim", "style": "dot", "text": "dữ liệu tới"}]}
            khoi.append(bieu_do(
                f"{tk} · giá = phần EPS + phần P/E, lũy kế 3 năm (log × 100) + đường EPS dự phóng", blk,
                f"Cộng theo log nên đường Giá luôn bằng tổng hai phần: hai phần cùng dương là 'double-click', ngược dấu là một "
                f"đòn bẩy triệt tiêu đòn kia. 69 điểm log ≈ ×2, 100 điểm ≈ ×2,7. Đầu khung {ddmm(_iso(b0[0]))}; đường chấm = "
                "EPS nối theo tăng trưởng đồng thuận của engine HHP, không phải dự báo giá.",
                "engine HHP (giá điều chỉnh, dải μ P/E, forecast.base_path)", f"{T2} {EST}", 300))
    else:
        khoi.append(canh_bao("Tách EPS × P/E", [f"{CAN} engine HHP không có dải P/E đủ dài cho {tk}"], "xam"))
    sig = []
    for d in (e.get("dau_hieu_do_duoc") or []):
        gt, thoa, ngay = _dau_hieu(d, r, weeks)
        ts = d.get("tham_so") or {}
        mo_ta = re.sub(r"^Pha [^:]*:\s*", "", nfc(d.get("mo_ta")))   # điều kiện đo được, không gắn tên pha
        sig.append([cell(nfc(d.get("id")), dam=True), cell(mo_ta, mono=False),
                    cell(f"{nfc(d.get('phep_do'))} · {', '.join(f'{k}={v}' for k, v in ts.items())}"), cell(gt),
                    cell("đạt ngưỡng" if thoa else ("chưa" if thoa is False else CAN),
                         "xam" if thoa is not None else "vang", pill=True), cell(ddmm(ngay))])
    if sig:
        khoi.append(bang(["Dấu hiệu", "Điều kiện đo được", "Phép đo · tham số", "Giá trị", "Trạng thái", "Ngày"], sig,
                         "Bốn dấu hiệu có phép đo của khung (S1, S3, S5, S6), đo trên chính mã: σ HHP (P/B, thiếu thì P/E), "
                         "KL tuần đã đóng ÷ TB 20 tuần trước, NN ròng 4 tuần đã đóng (Chaebol MAP). Đạt ngưỡng một dấu "
                         "hiệu không có nghĩa mã đang ở pha đó."))
    if K is not None and e:
        khoi += K.entry_compact(e)
        if tk == "MSN":
            khoi += _msn_soros(K)
    else:
        khoi.append(canh_bao("Khung Soros", [f"{CAN} {loi_khung}"], "xam"))
    moc = _iso(pts[-1][0]) if pts else (str(weeks[-1].get("we"))[:10] if weeks else None)
    return o("soros", "Soros mô phỏng · giá = EPS × P/E và dấu hiệu khung 7 pha", khoi, 12, *SOROS, EST,
             trang_thai(moc, 7) if moc else "cu")


def _msn_soros(K):
    """Phụ lục MSN: mục mp_soros của bản bổ sung Masan (kịch bản ĐÓNG BĂNG của JSX v37, guard_section)."""
    for p in sorted((A.KOS / "msn_reflex").glob("bo_sung_*.json"), reverse=True):
        d = A.read_json(p)
        if not isinstance(d, dict):
            continue
        sec = next((x for x in d.get("sections") or [] if x.get("id") == "mp_soros"), None)
        if sec:
            K.guard_section(sec, "JSX v37 · tab soros", None, "mp_soros")
            return [doan(f"{nfc(sec.get('tieu_de'))} · {nfc(sec.get('eyebrow'))}", "vang", True, "Phụ lục MSN (ĐÓNG BĂNG)"),
                    doan(nfc(sec.get("lede")), "xam")] + list(sec.get("khoi") or []) + [
                doan("Giá và P/E từng stage là kịch bản viết trước của tác giả JSX (13/04/2026), không phải giá mục tiêu "
                     "và không được chấm lại.", "xam")]
    return []


# ───────────────────────────── Chaebol Reflex mở rộng ─────────────────────────────

def o_reflex_mo_rong(tk, warnings):
    """Các ô reflex_* của phiên Chaebol Reflex (đã guard ở nguồn); mã ngoài registry → []."""
    try:
        import chaebol_reflex_trang as CRT  # noqa: PLC0415
        cells = _im_lang(CRT.o_aio_mo_rong, tk) or []
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Chaebol Reflex mở rộng lỗi: {_loi(exc)}")
        return []
    return [o(c.get("id"), c.get("tieu_de") or "Chaebol Reflex", c.get("khoi") or [], c.get("cot") or 12,
              c.get("eyebrow") or "", c.get("tab") or "msn_reflex", c.get("tab_nhan") or "Chaebol Reflex",
              c.get("tier") or EST, trang_thai(c.get("trang_thai_ngay"), 14)) for c in cells if c.get("id")]
