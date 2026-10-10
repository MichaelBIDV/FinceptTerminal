"""toanvu_pe_trang.py, phần trang mở rộng của tab "toanvu_pe" (stdlib, chỉ đọc).

  scope_page(H, code)       trang rổ VNINDEX / VN30 / VN100: hai báo cáo HTML của Toàn Vũ dựng lại (vị trí hiện tại,
                            Chart ② P/E × LS × ERP, Chart ① P/E → lợi suất, xếp hạng, watchlist, vùng LS, tín hiệu
                            đang bật) + bản kiểm định, định giá HHP của rổ, lãi suất & chế độ tiền, bảng bằng chứng
  deep_sections(H, tk)      các mục sâu cho trang một mã: pha giá (EPS × P/E), dải σ HHP, dự phóng, tần suất thắng
                            có điều kiện 60/120 phiên, chủ thể & sự kiện, bằng chứng, Hội đồng

H là module toanvu_pe (truyền vào để dùng chung tiện ích, tránh import vòng). Dữ liệu do toanvu_pe_sau.py dựng.
Khối "bieu_do" có "loai": "cot" | "xy" dùng biểu đồ mở rộng VnChartsExt của Fincept.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

SCOPES = ("VNINDEX", "VN30", "VN100", "VN200", "REST")
SCOPE_NAME = {"VNINDEX": "VN-Index (405 mã Bloomberg)", "VN30": "VN30", "VN100": "VN100",
              "VN200": "VN200 (top 200 vốn hoá, phần có trên HOSE)", "REST": "REST (mã Bloomberg ngoài VN200)"}
PORTFOLIO = {"VCB", "FPT", "MSN", "ACB", "GAS", "HPG", "TCB", "CTG", "GEX", "VRE", "PLX"}
ZONE_X = [(2, 8, "xanh", "P/E 2–8 · đáy thật"), (8, 15, "lam", "8–15 · hợp lý"), (15, 25, "vang", "15–25 · trung tính → đắt"),
          (25, 40, "do", "> 25 · đắt")]
KIEU_MAU = {"Tăng nhờ lợi nhuận": "xanh", "Tăng nhờ mở rộng P/E": "lam", "Tăng nhờ cả hai": "xanh",
            "Giảm do lợi nhuận đi xuống": "do", "Giảm do co P/E": "vang", "Giảm do cả hai": "do"}
ANN_MAU = {"xanh": "bull", "do": "bear", "vang": "amber", "lam": "info", "xam": "dim", "tim": "cyan"}


def _n(H, x):
    return H.num(x)


def cot(nhan, series, huong="ngang", nhan_phu=None, dv="", so_le=1, dau=False, vach=None, truc=None, gia_tri=True):
    b = {"loai": "cot", "huong": huong, "nhan": nhan, "series": series, "gia_tri": gia_tri, "dv": dv, "so_le": so_le, "dau": dau}
    if nhan_phu:
        b["nhan_phu"] = nhan_phu
    if vach:
        b["vach"] = vach
    if truc:
        b["truc"] = truc
    return b


def xy(truc_x, truc_y, series, vach_x=None, vach_y=None, vung_x=None, vung_y=None):
    b = {"loai": "xy", "truc_x": truc_x, "truc_y": truc_y, "series": series}
    for k, v in (("vach_x", vach_x), ("vach_y", vach_y), ("vung_x", vung_x), ("vung_y", vung_y)):
        if v:
            b[k] = v
    return b


def hline(y, text, mau, axis=None, w=0.03):
    if y is None:
        return None
    a = {"kind": "hband", "y0": y - w, "y1": y + w, "mau": mau, "alpha": 0.5, "text": text, "uu_tien": 2}
    if axis:
        a["axis"] = axis
    return a


def load_ro(H, code):
    d = H.read_json(H.STATE / "ro" / f"{code}.json")
    if not isinstance(d, dict):
        raise H.TvError("NO_DATA", f"Chưa có trang rổ {code}. Chạy: python3 scripts/toanvu_pe_sau.py")
    return d


def load_sau(H, tk):
    d = H.read_json(H.STATE / "sau" / f"{tk}.json")
    return d if isinstance(d, dict) else None


def load_hoidong(H, key):
    d = H.read_json(H.STATE / "hoi_dong" / f"{key}.json")
    return d if isinstance(d, dict) else None


# ══════════════════════════════ ĐỌC HIỂU NHANH ══════════════════════════════
# Nội dung giải thích (FAQ, luật TV từng bước, thuật ngữ, cách đọc từng mục) nằm ở toanvu_pe_giai_thich.py;
# trang chỉ điền số thật của mã ví dụ vào các chỗ trống {ma} {gia} {pe} {pct} {ls} {nguong} ... và xếp khối.

def _noi_dung():
    try:
        import toanvu_pe_giai_thich as g
        return g.NOI_DUNG
    except Exception:  # noqa: BLE001, thiếu tệp nội dung thì trang vẫn dựng, chỉ không có mục đọc hiểu
        return None


def _vi_du_vals(H, ma, cur):
    vn = H.vn
    ls = H.num(cur.get("ls"))
    on = bool(cur.get("kich_hoat"))
    return {"ma": ma, "gia": vn(cur.get("px"), 0), "pe": vn(cur.get("pe"), 2), "pct": vn(cur.get("pct"), 0),
            "ls": vn(ls, 2), "nguong": vn(cur.get("nguong"), 1), "pe_nguong": vn(cur.get("pe_nguong"), 2),
            "gia_nguong": vn(cur.get("gia_nguong"), 0), "ey": vn(cur.get("ey"), 2), "erp": vn(cur.get("erp"), 2, True),
            "pe_fair": vn(100.0 / ls, 1) if ls else "n/a", "trang_thai": "đang bật" if on else "không bật"}


def _fill(text, vals):
    out = text or ""
    for k, v in vals.items():
        out = out.replace("{" + k + "}", v if v not in (None, "") else "n/a")
    return out


def doc_hieu_sections(H, ma_vi_du=None, cur=None):
    """Mục "Đọc hiểu nhanh" (FAQ + luật TV từng bước có ví dụ số thật + phát hiện kiểm định) và mục "Thuật ngữ"."""
    nd = _noi_dung()
    if not nd:
        return []
    if cur is None:
        p = H.read_json(H.STATE / "ma" / f"{ma_vi_du or 'HPG'}.json") or {}
        cur = p.get("hien_tai") or {}
    ma = ma_vi_du or "HPG"
    vals = _vi_du_vals(H, ma, cur)
    blocks = [H.doan(_fill(nd["tom_tat_1_cau"], vals), the=True, tieu_de="Một câu")]
    faq = nd.get("faq") or []
    if faq:
        try:
            import toanvu_pe_giai_thich as g
            faq_note = f"Số trong phần hỏi đáp là của {g.MA_FAQ} phiên {g.NGAY_SO_FAQ}."
        except Exception:  # noqa: BLE001
            faq_note = ""
        blocks.append({"kieu": "the", "cot": 2, "the": [H.the_card(q["q"], _fill(q["a"], vals), mau_vien=("vang" if i == 0 else None))
                                                      for i, q in enumerate(faq)]})
        if faq_note:
            blocks.append(H.doan(faq_note, "xam"))
    buoc = nd.get("buoc") or []
    if buoc:
        blocks.append({"kieu": "danh_sach", "muc": [{"so": b.get("so") or str(i + 1), "tieu_de": H.nfc(b["tieu_de"]),
                                                    "text": H.nfc(b["text"] + "\n" + "Ví dụ: " + _fill(b["vi_du"], vals)),
                                                    "tags": []} for i, b in enumerate(buoc)]})
    kd = nd.get("kiem_dinh") or []
    if kd:
        blocks.append(H.canh_bao("Hội đồng kiểm định thấy gì (nói gọn)", [f"{k['tieu_de']}: {k['text']}" for k in kd], "lam"))
    out = [H.sec("dochieu", "Đọc hiểu nhanh · luật của Toàn Vũ và cách đọc kết quả", blocks, so="0",
                 eyebrow="Bắt đầu ở đây", lede=f"Ví dụ dùng số thật của {ma} phiên {H.ddmm(cur.get('ngay'))}.")]
    tn = nd.get("thuat_ngu") or []
    if tn:
        rows = [[H.cell(t["nhom"], "xam", mono=False), H.cell(t["term"], dam=True, mono=False), H.cell(t["nghia"], mono=False),
                 H.cell(_fill(t["vi_du"], vals), mono=False), H.cell(t["doc"], mono=False)] for t in tn]
        out.append(H.sec("thuatngu", "Thuật ngữ", [H.bang(["Nhóm", "Thuật ngữ", "Nghĩa là gì", "Ví dụ", "Đọc thế nào"], rows,
                                                          "Mỗi con số trên trang này dùng đúng các định nghĩa dưới đây.")],
                         so="0b", eyebrow="Tra khi gặp chữ lạ"))
    return out


def apply_guides(H, secs):
    """Chèn dòng "Cách đọc" ở đầu mỗi mục có hướng dẫn (khoá = id mục)."""
    nd = _noi_dung()
    g = (nd or {}).get("doc_bieu_do") or {}
    for sct in secs:
        t = g.get(sct.get("id"))
        if t:
            sct["khoi"].insert(0, H.doan("Cách đọc: " + t, "xam"))
    return secs


# ══════════════════════════════ TRANG RỔ ══════════════════════════════

def sec_vitri(H, d):
    h = d["hien_tai"]
    vn = H.vn
    zone = ("Mua mạnh (≥ +5)" if h["erp_tv"] >= 5 else "Tích lũy (+2 → +5)" if h["erp_tv"] >= 2 else
            "Hòa (0 → +2)" if h["erp_tv"] >= 0 else "Bất lợi (< 0)")
    tiles = [H.tile("P/E rổ · cách TV", vn(h["pe_tv"], 1) + "x", "điều hoà theo vốn hoá, BỎ mã P/E > 40", "lam", H.T_EST),
             H.tile("P/E fair = 100 ÷ LS", vn(h["pe_fair"], 1) + "x", f"LS {vn(h['ls'], 2)}% (FiinProX >12T cao nhất)", "vang", H.T_FACT),
             H.tile("Rẻ hơn fair", vn(h["re_hon_fair_pct"], 0) + "%", "theo P/E cách TV", "xanh" if h["re_hon_fair_pct"] > 0 else "do", H.T_EST),
             H.tile("ERP · cách TV", vn(h["erp_tv"], 2, True), zone, H.mau_sign(h["erp_tv"], 1.99) or "xam", H.T_EST),
             H.tile("P/E đủ mã", vn(h["pe_all"], 1) + "x", f"ERP {vn(h['erp_all'], 2, True)} · gồm cả mã P/E cao", H.mau_sign(h["erp_all"], 1.99) or "xam", H.T_EST),
             H.tile("P/E ngoài họ Vin", vn(h["pe_exvin"], 1) + "x", f"ERP {vn(h['erp_exvin'], 2, True)} · bỏ VIC/VHM/VRE/VPL", H.mau_sign(h["erp_exvin"], 1.99) or "xam", H.T_EST),
             H.tile("Earnings yield", vn(h["ey_tv"], 2) + "%", "100 ÷ P/E cách TV", None, H.T_EST),
             H.tile("Hướng LS 6 tháng", vn(h["dls6m"], 2, True) + " điểm", "biến chi phối trong kiểm định", "do" if (h["dls6m"] or 0) > 0.1 else "xanh", H.T_FACT)]
    gap = h["erp_tv"] - h["erp_all"]
    txt = (f"Theo đúng cách Toàn Vũ đo, {SCOPE_NAME[d['ro']]} đang ở P/E {vn(h['pe_tv'], 1)}x so với mức “ngang gửi tiết kiệm” "
           f"{vn(h['pe_fair'], 1)}x, tức ERP {vn(h['erp_tv'], 2, True)} điểm, vùng {zone.split(' (')[0].lower()}. "
           f"Con số này đứng trên một lựa chọn: bỏ các mã P/E > 40. Tính đủ mã, ERP chỉ còn {vn(h['erp_all'], 2, True)}; "
           f"bỏ riêng họ Vin, ERP {vn(h['erp_exvin'], 2, True)}. Chênh {vn(gap, 1)} điểm giữa hai cách đo lớn hơn cả khoảng cách giữa hai vùng "
           f"liền kề của TV, nên câu “thị trường rẻ” đúng với rổ ngoài họ Vin và sai với chỉ số đủ mã. "
           f"Hướng LS 6 tháng {vn(h['dls6m'], 2, True)} điểm: trong kiểm định, chính chiều LS (không phải mức P/E) quyết định tín hiệu có ăn hay không.")
    return H.sec("vitri", f"Vị trí hiện tại · {d['hien_tai']['ngay'][8:10]}/{d['hien_tai']['ngay'][5:7]}/{d['hien_tai']['ngay'][:4]}",
                 [{"kieu": "o_so", "cot": 4, "o": tiles},
                  H.chips([(H.T_EST, "P/E fair = 100 ÷ LS: mức P/E mà earnings yield bằng lãi gửi tiết kiệm"),
                           (H.T_EST, "EY = 100 ÷ P/E: lợi suất lợi nhuận của cổ phiếu"),
                           (H.T_EST, "ERP = EY − LS: phần bù khi chọn cổ phiếu thay vì gửi tiết kiệm")]),
                  H.doan(txt, the=True, tieu_de="Đọc nhanh")],
                 so="1", eyebrow="Khung 3 khái niệm của TV",
                 lede="Ba ô đầu là đúng phép tính TV in trong báo cáo (khớp 9,46x · ERP +2,97 ngày 07/09). Ba ô sau là cách đo khác cho cùng rổ.")


def phase_stats(H, d):
    c = d["chuoi"]
    rows = []
    for g in d["giai_doan"]:
        ii = [i for i, x in enumerate(c["x"]) if g["tu"] <= x <= g["den"]]
        if len(ii) < 4:
            continue
        def avg(k):
            v = [c[k][i] for i in ii if c[k][i] is not None]
            return sum(v) / len(v) if v else None
        i0, i1 = ii[0], ii[-1]
        r = (c["idx"][i1] / c["idx"][i0] - 1) * 100 if c["idx"][i0] and c["idx"][i1] else None
        rows.append({**g, "pe": avg("pe_tv"), "fair": avg("pe_fair"), "ls": avg("ls"), "erp": avg("erp_tv"), "r": r,
                     "nam": (len(ii) / 52.0)})
    return rows


def sec_chart2(H, d, vimo):
    c = d["chuoi"]
    x = c["x"]
    vn = H.vn
    lo_g = [p if (p is not None and f is not None and p < f) else None for p, f in zip(c["pe_tv"], c["pe_fair"])]
    hi_g = [f if (p is not None and f is not None and p < f) else None for p, f in zip(c["pe_tv"], c["pe_fair"])]
    lo_r = [f if (p is not None and f is not None and p >= f) else None for p, f in zip(c["pe_tv"], c["pe_fair"])]
    hi_r = [p if (p is not None and f is not None and p >= f) else None for p, f in zip(c["pe_tv"], c["pe_fair"])]
    bands = [{"kind": "xband", "x0": H.iso_ms(g["tu"]), "x1": H.iso_ms(min(g["den"], x[-1])), "alpha": 0.05,
              "mau": ("bear" if i in (0, 1, 5) else "bull" if i in (2, 4) else "amber" if i == 3 else "cyan"),
              "text": g["nhan"].split(" · ")[0], "uu_tien": 3} for i, g in enumerate(d["giai_doan"])]
    h = d["hien_tai"]
    p1 = {"x": x, "left": {"label": "P/E (lần)", "min": 0, "max": 30}, "series": [
        {"name": "Rẻ hơn fair", "style": "band", "y_lo": lo_g, "y_hi": hi_g, "mau": "up", "alpha": 0.28},
        {"name": "Đắt hơn fair", "style": "band", "y_lo": lo_r, "y_hi": hi_r, "mau": "down", "alpha": 0.30},
        {"name": "P/E fair = 100 ÷ LS", "y": c["pe_fair"], "style": "dash", "mau": "amber"},
        {"name": "P/E đủ mã", "y": c["pe_all"], "style": "thin", "mau": "grey"},
        {"name": "P/E ngoài họ Vin", "y": c["pe_exvin"], "style": "thin", "mau": "violet"},
        {"name": "P/E rổ · cách TV", "y": c["pe_tv"], "style": "line", "mau": "blue"}],
        "annotations": bands + [{"kind": "point", "x": H.iso_ms(x[-1]), "y": h["pe_tv"], "marker": "diamond", "pos": "above",
                                 "text": f"{vn(h['pe_tv'], 1)}x · fair {vn(h['pe_fair'], 1)}x", "mau": "amber", "uu_tien": 1}]}
    p2 = {"x": x, "left": {"label": "LS tiền gửi (%)", "min": 0, "max": 20}, "series": [
        {"name": "LS huy động VND >12T cao nhất (FiinProX, TV dùng)", "y": c["ls"], "style": "line", "mau": "amber"}],
        "annotations": bands + [hline(10, "LS > 10% = vùng nguy hiểm", "bear", w=0.05),
                                {"kind": "hband", "y0": 10, "y1": 20, "mau": "bear", "alpha": 0.08, "uu_tien": 3}]}
    tg = vimo.get("tien_gui_niem_yet") or {}
    if tg.get("x"):
        # chuỗi niêm yết 13T (ngày) gộp về tuần trên trục x của rổ: lấy giá trị cuối ≤ ngày tuần
        j, last, y13 = 0, None, []
        for xx in x:
            while j < len(tg["x"]) and tg["x"][j] <= xx:
                last = tg["y13"][j]
                j += 1
            y13.append(last if xx >= tg["x"][0] else None)
        p2["series"].append({"name": "13T niêm yết NH lớn (MBB/ACB/TCB, WiChart)", "y": y13, "style": "dash", "mau": "blue"})
    ep = c["erp_tv"]
    p3 = {"x": x, "left": {"label": "ERP (điểm %)", "min": -6, "max": 16}, "series": [
        {"name": "ERP ≥ 0", "style": "band", "y_lo": [0 if (v is not None and v >= 0) else None for v in ep],
         "y_hi": [v if (v is not None and v >= 0) else None for v in ep], "mau": "up", "alpha": 0.22},
        {"name": "ERP < 0", "style": "band", "y_lo": [v if (v is not None and v < 0) else None for v in ep],
         "y_hi": [0 if (v is not None and v < 0) else None for v in ep], "mau": "down", "alpha": 0.30},
        {"name": "ERP đủ mã", "y": c["erp_all"], "style": "thin", "mau": "grey"},
        {"name": "ERP ngoài họ Vin", "y": c["erp_exvin"], "style": "thin", "mau": "violet"},
        {"name": "ERP · cách TV", "y": ep, "style": "line", "mau": "cyan"}],
        "annotations": bands + [hline(5, "+5 · mua mạnh (TV)", "bull"), hline(2, "+2 · tích lũy", "bull"), hline(0, "0 · hòa với gửi tiết kiệm", "dim"),
                                hline(-3, "−3 · nguy hiểm", "bear"),
                                {"kind": "point", "x": H.iso_ms(x[-1]), "y": h["erp_tv"], "marker": "diamond", "pos": "above",
                                 "text": f"ERP {vn(h['erp_tv'], 2, True)}", "sub": f"đủ mã {vn(h['erp_all'], 1, True)}", "mau": "amber", "uu_tien": 1}]}
    ph = phase_stats(H, d)
    rows = []
    for g in ph:
        den = min(g["den"], d["chuoi"]["x"][-1])
        rows.append([H.cell(g["nhan"].split(" · ")[0], dam=True, mono=False), H.cell(f"{H.ddmm(g['tu'], True)[3:]} → {H.ddmm(den, True)[3:]}"),
                     H.cell(vn(g["ls"], 1) + "%", "do" if (g["ls"] or 0) > 10 else None), H.cell(vn(g["pe"], 1) + "x"),
                     H.cell(vn(g["erp"], 1, True), H.mau_sign(g["erp"], 1.99)), H.cell(vn(g["r"], 0, True, "%"), H.mau_sign(g["r"], 0)),
                     H.cell(g["nhan"].split(" · ", 1)[1] if " · " in g["nhan"] else "", mono=False)])
    txt = ""
    if ph:
        best = max(ph, key=lambda g: g["r"] if g["r"] is not None else -1e9)
        worst = min(ph, key=lambda g: g["r"] if g["r"] is not None else 1e9)
        c = d["chuoi"]

        def ls_at(day):
            j = max((k for k, xx in enumerate(c["x"]) if xx <= day), default=None)
            return c["ls"][j] if j is not None else None
        fall, rise = [], []
        for g in ph:
            a0, a1 = ls_at(g["tu"]), ls_at(min(g["den"], c["x"][-1]))
            if a0 is None or a1 is None or g["r"] is None:
                continue
            (fall if a1 < a0 - 0.25 else rise if a1 > a0 + 0.25 else []).append(g)
        def avg_r(lst):
            return sum(g["r"] / max(g["nam"], 0.25) for g in lst) / len(lst) if lst else None
        hi_erp = max(ph, key=lambda g: g["erp"] if g["erp"] is not None else -1e9)
        txt = (f"Ba panel đọc cùng trục thời gian. Pha mạnh nhất của rổ là {best['nhan'].split(' · ')[0]} "
               f"(chỉ số {vn(best['r'], 0, True)}%, LS trung bình {vn(best['ls'], 1)}%, ERP {vn(best['erp'], 1, True)}); "
               f"pha tệ nhất là {worst['nhan'].split(' · ')[0]} ({vn(worst['r'], 0, True)}%, LS {vn(worst['ls'], 1)}%). "
               f"Giai đoạn có ERP trung bình cao nhất là {hi_erp['nhan'].split(' · ')[0]} ({vn(hi_erp['erp'], 1, True)}), "
               f"chỉ số khi đó {vn(hi_erp['r'], 0, True)}%. ")
        af, ar = avg_r(fall), avg_r(rise)
        if af is not None and ar is not None:
            txt += (f"Các giai đoạn LS hạ trong kỳ ({', '.join(g['nhan'].split(' · ')[0] for g in fall)}) cho chỉ số TB {vn(af, 0, True)}%/năm; "
                    f"các giai đoạn LS lên ({', '.join(g['nhan'].split(' · ')[0] for g in rise)}) cho {vn(ar, 0, True)}%/năm. ")
            txt += ("Ở rổ này chiều LS tách kết quả rõ hơn mức ERP." if af - ar > 5 else
                    "Ở rổ này chiều LS KHÔNG tách được kết quả theo giai đoạn; đừng chuyển nguyên kết luận từ VN-Index." if af - ar <= 0 else
                    "Chiều LS có tách kết quả nhưng không mạnh.")
    return H.sec("chart2", "Chart ② · P/E × Lãi suất × ERP từ 2008", [
        H.bieu_do("Panel 1 · P/E rổ so với P/E fair = 100 ÷ LS", p1,
                  "Xanh: P/E dưới fair (rẻ hơn gửi tiết kiệm). Đỏ: đắt hơn. Đường tím/xám: hai cách đo khác cho cùng rổ.",
                  "Bloomberg (P/E, vốn hoá) × FiinProX (LS) · tính lại", H.T_EST, 330),
        H.bieu_do("Panel 2 · Lãi suất tiền gửi", p2,
                  "Cam: chuỗi TV dùng (tháng, dừng ở mốc cuối file). Lam đứt: lãi niêm yết 13T ngân hàng lớn từ 10/2024.",
                  "FiinProX · WiChart lshd", H.T_FACT, 260),
        H.bieu_do("Panel 3 · ERP = EY − LS", p3, "Ngưỡng +5 / +2 / 0 / −3 của TV. Dải nền: 7 giai đoạn TV đặt tên.",
                  "tính lại từ hai panel trên", H.T_EST, 300),
        H.bang(["Giai đoạn", "Thời gian", "LS TB", "P/E TB", "ERP TB", "Chỉ số", "Bối cảnh (nhãn TV)"], rows,
               "Thống kê từng giai đoạn trên chuỗi tuần của rổ; chỉ số = " + d["chi_so_nguon"], can_phai=[2, 3, 4, 5]),
        H.doan(txt, the=True, tieu_de="Diễn giải từng pha")], so="2", eyebrow="Báo cáo vĩ mô của TV, dựng lại cho " + d["ro"])


def sec_erp_zone(H, d):
    vn = H.vn
    z = d["erp_vung"]
    names = [r["vung"] for r in z["tv"]]
    hit60 = [r.get("hit60") for r in z["tv"]]
    hit120 = [r.get("hit120") for r in z["tv"]]
    r120 = [r.get("r120") for r in z["tv"]]
    ch1 = cot(names, [{"name": "Hit 60 phiên", "y": hit60, "mau": "lam"}, {"name": "Hit 120 phiên", "y": hit120, "mau": "xanh"}],
              huong="doc", nhan_phu=[f"{r.get('n_ngay', 0)} ngày · {r.get('n_doc_lap', 0)} khối" for r in z["tv"]], dv="%", so_le=0,
              vach=[{"v": 50, "text": "50% tung đồng xu", "mau": "xam"}], truc={"label": "% lần chỉ số có lãi", "min": 0, "max": 100})
    ch2 = cot(names, [{"name": "ERP cách TV", "y": r120, "mau": "lam"},
                      {"name": "ERP đủ mã", "y": [r.get("r120") for r in z["all"]], "mau": "xam"},
                      {"name": "ERP ngoài họ Vin", "y": [r.get("r120") for r in z["exvin"]], "mau": "tim"}],
              huong="doc", dv="%", so_le=1, dau=True, truc={"label": "lợi suất TB 120 phiên của chỉ số (%)"})
    rows = []
    for k, lab in (("tv", "cách TV"), ("all", "đủ mã"), ("exvin", "ngoài họ Vin")):
        for r in z[k]:
            if not r.get("n_ngay"):
                continue
            rows.append([H.cell(lab, mono=False), H.cell(r["vung"]), H.cell(str(r["n_ngay"])), H.cell(str(r.get("n_doc_lap", ""))),
                         H.cell(vn(r.get("hit60"), 0, suffix="%"), H.mau_sign((r.get("hit60") or 50) - 50, 5)),
                         H.cell(vn(r.get("r60"), 1, True, "%"), H.mau_sign(r.get("r60"))),
                         H.cell(vn(r.get("hit120"), 0, suffix="%"), H.mau_sign((r.get("hit120") or 50) - 50, 5)),
                         H.cell(vn(r.get("r120"), 1, True, "%"), H.mau_sign(r.get("r120")))])
    cur = d["hien_tai"]["erp_tv"]
    zc = next((r for r in z["tv"] if r.get("n_ngay") and _in_zone(r["vung"], cur)), None)
    txt = ""
    if zc:
        txt = (f"Hiện ERP cách TV {vn(cur, 2, True)} nằm ở vùng {zc['vung']}: lịch sử rổ có {zc['n_ngay']} ngày ở vùng này nhưng chỉ "
               f"{zc.get('n_doc_lap')} khối 60 phiên độc lập. Hit 60 phiên {vn(zc.get('hit60'), 0)}%, lợi suất 120 phiên TB {vn(zc.get('r120'), 1, True)}%. "
               f"TV in cho VN-Index vùng +2 → +5: hit 61%, 120 phiên +3,3%. {H.vn(zc['n_ngay'], 0)} ngày nghe nhiều nhưng chỉ là "
               f"{zc.get('n_doc_lap')} khối độc lập, nên khoảng tin cậy rộng hơn nhiều so với cảm giác con số ngày gợi ra.")
        if d["ro"] != "VNINDEX":
            txt += (" Lưu ý: chỉ số của rổ này được dựng từ THÀNH VIÊN HIỆN TẠI (mã yếu đã rời rổ không có mặt), nên hit và lợi suất "
                    "bị thiên lệch sống sót và cao hơn chỉ số thật; không so trực tiếp với số TV in cho VN-Index.")
    return H.sec("erpzone", "ERP theo vùng → lợi suất chỉ số sau 60 / 120 phiên", [
        H.bieu_do("Hit rate của chỉ số theo vùng ERP (cách TV)", ch1, "Nhãn phụ: số ngày quan sát · số khối 60 phiên không chồng nhau.",
                  "tính lại · " + d["chi_so_nguon"], H.T_EST, 300),
        H.bieu_do("Lợi suất TB 120 phiên theo vùng ERP · ba cách đo", ch2, "Cùng ngưỡng vùng, khác cách tính P/E rổ.",
                  "tính lại", H.T_EST, 300),
        H.bang(["Cách đo", "Vùng ERP", "Ngày", "Khối độc lập", "Hit 60", "TB 60", "Hit 120", "TB 120"], rows,
               "Ngày chồng cửa sổ: số ngày phóng đại độ chắc; đọc cột khối độc lập.", can_phai=[2, 3, 4, 5, 6, 7]),
        H.doan(txt, the=True, tieu_de="Đọc vị trí hiện tại theo backtest") if txt else None],
        so="3", eyebrow="Khối “Vị trí hiện tại” của TV, kiểm lại")


def _in_zone(name, v):
    tbl = {"≥ +5": (5, 99), "+2 → +5": (2, 5), "0 → +2": (0, 2), "−3 → 0": (-3, 0), "< −3": (-99, -3)}
    lo, hi = tbl.get(name, (0, 0))
    return v is not None and lo <= v < hi


def sec_chart1(H, d):
    c = d["chart1"]
    cp, c45 = c["cp"], c["cp45"]
    vz = [{"x0": a, "x1": b, "mau": m, "alpha": 0.10, "text": t} for a, b, m, t in ZONE_X]
    ch_r = xy({"label": "P/E cổ phiếu tại ngày mua (lần)", "min": 2, "max": 40, "so_le": 0},
              {"label": "lợi suất TB (%)", "so_le": 0},
              [{"name": "120 phiên (TV)", "kieu": "duong", "x": cp["x"], "y": cp["r120"], "mau": "xanh"},
               {"name": "60 phiên (TV)", "kieu": "net", "x": cp["x"], "y": cp["r60"], "mau": "lam"},
               {"name": "120 phiên · trễ EPS 45 ngày", "kieu": "net", "x": c45["x"], "y": c45["r120"], "mau": "vang"}],
              vach_y=[{"v": 0, "text": "", "mau": "xam"}], vung_x=vz)
    ch_h = xy({"label": "P/E cổ phiếu tại ngày mua (lần)", "min": 2, "max": 40, "so_le": 0},
              {"label": "% lần có lãi", "so_le": 0},
              [{"name": "Hit 60 phiên (TV)", "kieu": "duong", "x": cp["x"], "y": cp["hit60"], "mau": "vang"},
               {"name": "Hit 120 phiên (TV)", "kieu": "net", "x": cp["x"], "y": cp["hit120"], "mau": "tim"},
               {"name": "Hit 60 · trễ EPS 45 ngày", "kieu": "net", "x": c45["x"], "y": c45["hit60"], "mau": "xam"}],
              vach_y=[{"v": 50, "text": "50% tung đồng xu", "mau": "xam"}], vung_x=vz)
    blocks = [H.bieu_do("① Lợi suất TB theo mức P/E lúc mua", ch_r, "Mỗi điểm = mọi ngày-mã có P/E ở mức đó, làm mịn Gauss như bản TV.",
                        "Bloomberg · tính lại cho thành viên " + d["ro"], H.T_EST, 330),
              H.bieu_do("② Tỷ lệ có lãi theo mức P/E lúc mua", ch_h, "Vàng đặc: cách TV. Xám đứt: cùng phép đo khi EPS chỉ được biết sau 45 ngày.",
                        "Bloomberg · tính lại", H.T_EST, 330)]
    ro = c.get("ro")
    if ro:
        blocks.append(H.bieu_do("③ Cấp rổ: P/E gộp của rổ → lợi suất chỉ số", xy(
            {"label": "P/E rổ cách TV (lần)", "so_le": 0}, {"label": "lợi suất TB (%)", "so_le": 0},
            [{"name": "120 phiên", "kieu": "duong", "x": ro["x"], "y": ro["r120"], "mau": "xanh"},
             {"name": "60 phiên", "kieu": "net", "x": ro["x"], "y": ro["r60"], "mau": "lam"},
             {"name": "số ngày", "kieu": "diem", "x": ro["x"], "y": [0] * len(ro["x"]), "mau": "xam",
              "nhan": [str(n) if n else "" for n in ro["n"]], "co": 3}],
            vach_y=[{"v": 0, "text": "", "mau": "xam"}],
            vach_x=[{"v": d["hien_tai"]["pe_tv"], "text": "hiện tại", "mau": "vang"}]),
            "Biến thật mà câu hỏi của TV hỏi: P/E THỊ TRƯỜNG thấp thì CHỈ SỐ có lãi không. Nhãn dưới trục: số ngày ở mức đó.",
            d["chi_so_nguon"], H.T_EST, 300))
    r_lo = _at(cp, 5, "r120")
    r_hi = _at(cp, 15, "r120")
    l_lo = _at(c45, 5, "r120")
    l_hi = _at(c45, 15, "r120")
    txt = (f"Theo cách TV, mua cổ phiếu ở P/E 5x cho TB {H.vn(r_lo, 1, True)}% sau 120 phiên, ở 15x chỉ {H.vn(r_hi, 1, True)}%. "
           f"Khi EPS chỉ được biết 45 ngày sau ngày chốt quý (đúng thực tế công bố BCTC), cặp số thành {H.vn(l_lo, 1, True)}% và {H.vn(l_hi, 1, True)}%. "
           "Độ dốc còn nhưng hẹp lại: một phần “P/E thấp thì lời” của chart gốc là do P/E được tính bằng EPS mà người mua lúc đó chưa có. "
           "Thêm nữa, mỗi điểm trên chart trộn hàng trăm mã và mọi giai đoạn; trục X là P/E cổ phiếu chứ không phải P/E thị trường như tiêu đề gốc.")
    blocks.append(H.doan(txt, the=True, tieu_de="Đọc chart"))
    return H.sec("chart1", "Chart ① · Mua ở P/E thấp có lời hơn không?", blocks, so="4",
                 eyebrow="Báo cáo vĩ mô của TV, dựng lại + bản không nhìn trước",
                 lede="Vùng nền: P/E 2–8 (đáy thật) · 8–15 (hợp lý) · 15–25 (trung tính → đắt) · > 25 (đắt), như bản gốc.")


def _at(c, xv, key):
    try:
        i = min(range(len(c["x"])), key=lambda k: abs(c["x"][k] - xv))
        return c[key][i]
    except (ValueError, KeyError, TypeError):
        return None


def sec_ranking(H, d):
    vn = H.vn
    rows = [r for r in d["xep_hang"] if r.get("alpha") is not None and (r.get("n_ngay") or 0) >= 60]
    k_top = 30 if len(rows) > 120 else (15 if len(rows) > 40 else 10)
    k_bot = 15 if len(rows) > 120 else (10 if len(rows) > 40 else 8)
    top = sorted(rows, key=lambda r: -r["alpha"])[:k_top]
    bot = sorted(rows, key=lambda r: r["alpha"])[:k_bot][::-1]
    watch = set(d["watch"])

    def bars(lst, mau):
        return cot([r["ma"] for r in lst], [{"name": "alpha 60 phiên", "y": [r["alpha"] for r in lst], "mau": mau,
                                             "mau_tung": ["tim" if r["ma"] in watch else None for r in lst]}],
                   nhan_phu=[f"hit {vn(r.get('hit_sig'), 0)}%" for r in lst], dv=" điểm", so_le=1, dau=True,
                   truc={"label": "alpha = TB 60 phiên khi có tín hiệu − TB mọi ngày (điểm %)"})
    hr = [r for r in d["xep_hang"] if (r.get("n_dot") or 0) >= 6 and r.get("xs_dot") is not None]
    htop = sorted(hr, key=lambda r: -r["xs_dot"])[:k_bot]
    hbot = sorted(hr, key=lambda r: r["xs_dot"])[:k_bot][::-1]

    def hbars(lst):
        return cot([r["ma"] for r in lst], [{"name": "vượt cùng ngày", "y": [r["xs_dot"] for r in lst], "mau": "xanh",
                                             "mau_tung": [("tim" if r["ma"] in watch else ("xanh" if (r.get("p_dot") or 1) < 0.05 else "xam"))
                                                          if r["xs_dot"] > 0 else ("do" if (r.get("p_dot") or 1) < 0.05 else "xam") for r in lst]}],
                   nhan_phu=[f"{r['n_dot']} đợt · p {vn(r.get('p_dot'), 2)}" for r in lst], dv=" điểm", so_le=1, dau=True,
                   truc={"label": "TB 60 phiên của mã − TB cùng ngày mọi mã (điểm %)"})
    n_sig = sum(1 for r in hr if (r.get("p_dot") or 1) < 0.05 and r["xs_dot"] > 0)
    kv = 0.025 * len(hr)   # p < 0,05 hai phía VÀ dấu dương: ≈ 2,5% số mã nếu chỉ là may rủi
    txt = (f"Hai cột trên là cách TV xếp hạng (mọi ngày tín hiệu, cửa sổ chồng nhau). Hai cột dưới xếp lại chính các mã đó bằng đợt "
           f"độc lập (cách nhau ≥ 60 phiên) và so với trung bình cùng ngày của mọi mã: {n_sig}/{len(hr)} mã có vượt trội dương với p < 0,05, "
           f"trong khi riêng may rủi đã cho khoảng {vn(kv, 1)} mã. Tím = mã danh mục/watchlist. Xếp hạng TV vì thế đọc như danh sách mã "
           "đã hưởng lợi từ các nhịp hồi chung của thị trường hơn là mã có “signal hiệu quả”.")
    return H.sec("rank", f"Xếp hạng hiệu quả tín hiệu · {len(rows)} mã của rổ", [
        H.bieu_do(f"Top {k_top} · tín hiệu hiệu quả nhất (cách TV)", bars(top, "xanh"), "Nhãn phụ: hit 60 phiên khi tín hiệu bật.",
                  "Bloomberg × FiinProX · tái lập", H.T_EST, max(260, 22 * len(top) + 60)),
        H.bieu_do(f"Bottom {k_bot} · “value trap” (cách TV)", bars(bot, "do"), "PE rẻ nhưng tiếp tục giảm.",
                  "Bloomberg × FiinProX · tái lập", H.T_EST, max(260, 22 * len(top) + 60)),
        H.bieu_do(f"Kiểm định · {k_bot} mã vượt trội nhất theo đợt độc lập", hbars(htop), "Xanh đậm: p < 0,05. Xám: chưa phân biệt được với may rủi.",
                  "kiểm định HĐCV", H.T_EST, max(240, 22 * k_bot + 60)),
        H.bieu_do(f"Kiểm định · {k_bot} mã kém nhất theo đợt độc lập", hbars(hbot), "Đỏ: kém có ý nghĩa (p < 0,05).",
                  "kiểm định HĐCV", H.T_EST, max(240, 22 * k_bot + 60)),
        H.doan(txt, the=True, tieu_de="Đọc xếp hạng")], so="5", eyebrow="Báo cáo per-stock ① của TV")


def sec_watch(H, d):
    vn = H.vn
    by = {r["ma"]: r for r in d["xep_hang"]}
    w = [t for t in d["watch"] if t in by and by[t].get("hit_sig") is not None]
    if not w:
        return None
    hits = [by[t]["hit_sig"] for t in w]
    mau = ["xanh" if h > 55 else ("vang" if h >= 50 else "do") for h in hits]
    c1 = cot(w, [{"name": "hit 60 phiên khi tín hiệu", "y": hits, "mau": "xanh", "mau_tung": mau}], huong="doc", dv="%", so_le=1,
             vach=[{"v": 50, "text": "50%", "mau": "xam"}], truc={"label": "% lần có lãi", "min": 0, "max": 100},
             nhan_phu=["DM" if t in PORTFOLIO else "TV" for t in w])
    c2 = cot(w, [{"name": "TB 60 phiên khi tín hiệu", "y": [by[t]["r_sig"] for t in w], "mau": "lam"},
                 {"name": "TB 60 phiên mọi lúc", "y": [by[t]["r_base"] for t in w], "mau": "xam"}], huong="doc", dv="%", so_le=1, dau=True,
             truc={"label": "lợi suất TB 60 phiên (%)"})
    al = [by[t]["alpha"] for t in w]
    a45 = [by[t].get("alpha45") for t in w]
    c3 = cot(w, [{"name": "alpha cách TV", "y": al, "mau": "xanh", "mau_tung": ["xanh" if (a or 0) > 1 else ("vang" if (a or 0) >= 0 else "do") for a in al]},
                 {"name": "alpha · trễ EPS 45 ngày", "y": a45, "mau": "xam"}], huong="doc", dv=" điểm", so_le=1, dau=True,
             truc={"label": "alpha 60 phiên (điểm %)"})
    good = [t for t in w if (by[t]["alpha"] or 0) > 1 and (by[t].get("alpha45") or 0) > 1]
    bad = [t for t in w if (by[t]["alpha"] or 0) < 0]
    txt = (f"Danh mục tham chiếu (DM) và watchlist của TV trong rổ: {', '.join(w)}. Alpha dương ở cả hai cách đo: "
           f"{', '.join(good) or 'không mã nào'}; alpha âm theo cách TV: {', '.join(bad) or 'không mã nào'}. "
           "Mã có alpha âm là chỗ luật “P/E thấp + LS” từng mua vào nhịp đi xuống tiếp: rẻ không đủ, phải có chất xúc tác.")
    return H.sec("watch", "Watchlist spotlight · danh mục tham chiếu + watchlist TV", [
        H.bieu_do("Hit rate khi tín hiệu kích hoạt", c1, "Xanh > 55% · vàng 50–55% · đỏ < 50%. DM = danh mục 12/09, TV = watchlist TV.",
                  "tái lập", H.T_EST, 300),
        H.bieu_do("Lợi suất khi có tín hiệu so với mua bất kỳ", c2, "Lam: khi tín hiệu. Xám: mọi ngày có LS.", "tái lập", H.T_EST, 300),
        H.bieu_do("Alpha = tín hiệu − baseline", c3, "Xám: cùng phép đo khi EPS biết trễ 45 ngày.", "tái lập + kiểm định", H.T_EST, 300),
        H.doan(txt, the=True, tieu_de="Đọc watchlist")], so="6", eyebrow="Báo cáo per-stock ② của TV")


def sec_regime(H, d):
    vn = H.vn
    rg = d["regime"]
    lv = rg["muc_ls"]
    c1 = cot([r["vung"] for r in lv], [{"name": "60 phiên", "y": [r["r60"] for r in lv], "mau": "lam"},
                                        {"name": "120 phiên", "y": [r["r120"] for r in lv], "mau": "xanh"},
                                        {"name": "60 phiên · trễ EPS", "y": [r["r60_45"] for r in lv], "mau": "xam"}],
             huong="doc", nhan_phu=[f"hit {vn(r['hit'], 0)}% · n {r['n']:,}".replace(",", ".") for r in lv], dv="%", so_le=1, dau=True,
             truc={"label": "lợi suất TB khi tín hiệu bật (%)"})
    dr = rg["huong_ls"]
    c2 = cot([r["huong"] for r in dr], [{"name": "khi tín hiệu bật", "y": [r["r60"] for r in dr], "mau": "lam",
                                          "mau_tung": ["xanh" if (r["r60"] or 0) > 2 else ("do" if (r["r60"] or 0) < 0 else "vang") for r in dr]},
                                         {"name": "mọi ngày", "y": [r["r60_moi_ngay"] for r in dr], "mau": "xam"}],
             huong="doc", nhan_phu=[f"hit {vn(r['hit'], 0)}%" for r in dr], dv="%", so_le=1, dau=True,
             truc={"label": "lợi suất TB 60 phiên (%)"})
    pts = [r for r in d["xep_hang"] if r.get("hit_sig") is not None and r.get("alpha") is not None and (r.get("n_ngay") or 0) >= 60]
    watch = set(d["watch"])
    c3 = xy({"label": "hit 60 phiên khi tín hiệu (%)", "min": 15, "max": 100, "so_le": 0}, {"label": "alpha 60 phiên (điểm %)", "so_le": 0},
            [{"name": "mọi mã", "kieu": "diem", "x": [r["hit_sig"] for r in pts if r["ma"] not in watch],
              "y": [r["alpha"] for r in pts if r["ma"] not in watch], "mau": "lam", "co": 5,
              "nhan": [r["ma"] for r in pts if r["ma"] not in watch]},
             {"name": "danh mục + watchlist", "kieu": "diem", "x": [r["hit_sig"] for r in pts if r["ma"] in watch],
              "y": [r["alpha"] for r in pts if r["ma"] in watch], "mau": "tim", "co": 9, "nhan": [r["ma"] for r in pts if r["ma"] in watch]}],
            vach_x=[{"v": 50, "text": "50%", "mau": "xam"}], vach_y=[{"v": 0, "text": "", "mau": "xam"}],
            vung_x=[{"x0": 50, "x1": 100, "mau": "xanh", "alpha": 0.05, "text": "hit > 50% & alpha > 0 ↗"}])
    hd = {r["huong"]: r for r in dr}

    def wavg(keys):  # trung bình có trọng số số ngày-mã của từng nhóm
        rows = [hd[k] for k in keys if hd.get(k) and hd[k]["r60"] is not None and hd[k]["n"]]
        n = sum(r["n"] for r in rows)
        return [sum(r["r60"] * r["n"] for r in rows) / n] if n else []
    up = wavg(("tăng", "tăng mạnh"))
    dn = wavg(("giảm mạnh", "giảm"))
    a_dn = sum(dn) / len(dn) if dn else None
    a_up = sum(up) / len(up) if up else None
    best = max((r for r in lv if r.get("r60") is not None), key=lambda r: r["r60"], default=None)
    txt = (f"Chart vùng LS của TV (trái) xếp theo MỨC LS; ô tốt nhất ở rổ này là {best['vung'] if best else 'n/a'}. "
           f"Xếp lại theo HƯỚNG LS 6 tháng (giữa): tín hiệu khi LS đang giảm cho TB {vn(a_dn, 1, True) if a_dn is not None else 'n/a'}% sau 60 phiên, "
           f"khi LS đang tăng {vn(a_up, 1, True) if a_up is not None else 'n/a'}%. ")
    if a_dn is not None and a_up is not None and a_dn - a_up > 1 and a_dn > 0:
        txt += ("Chiều LS phân tách kết quả rõ hơn mức LS: luật P/E chỉ có lợi thế khi LS đang hạ. ")
    elif a_dn is not None and a_up is not None and a_up - a_dn > 1:
        txt += ("Ở rổ này quan hệ ĐẢO so với toàn thị trường: các mã lớn từng được mua khi LS đi lên (ngân hàng hưởng biên lãi), "
                "nên không thể chuyển nguyên kết luận “LS tăng thì tránh” từ VN-Index sang rổ này. ")
    else:
        txt += "Ở rổ này hai chiều LS không tách được kết quả: hướng LS không phải bộ lọc đủ mạnh cho riêng nhóm mã này. "
    txt += f"Hiện LS 6 tháng {vn(d['hien_tai']['dls6m'], 2, True)} điểm, tức ô “{_dir_name(d['hien_tai']['dls6m'])}”."
    return H.sec("regime", "Vùng lãi suất × tín hiệu P/E · khi nào luật hiệu quả?", [
        H.bieu_do("Theo MỨC LS (cách TV)", c1, "Nhãn phụ: hit 60 phiên · số ngày-mã. Xám: bản trễ EPS 45 ngày.", "tái lập", H.T_EST, 300),
        H.bieu_do("Theo HƯỚNG LS 6 tháng (kiểm định)", c2, "Xanh/vàng/đỏ: tín hiệu khi LS ở hướng đó. Xám: mọi ngày cùng hướng.",
                  "kiểm định HĐCV", H.T_EST, 300),
        H.bieu_do(f"Bản đồ risk-return · {len(pts)} mã", c3, "Góc phải trên = hit > 50% và alpha > 0. Tím: danh mục + watchlist.",
                  "tái lập", H.T_EST, 380),
        H.doan(txt, the=True, tieu_de="Đọc vùng lãi suất")], so="7", eyebrow="Báo cáo per-stock ③ của TV")


def _dir_name(v):
    if v is None:
        return "n/a"
    return "giảm mạnh" if v < -0.5 else "giảm" if v < -0.1 else "đi ngang" if v <= 0.1 else "tăng" if v <= 0.5 else "tăng mạnh"


def sec_signals(H, d):
    vn = H.vn
    thr = d["hien_tai"]["nguong"]
    by = {r["ma"]: r for r in d["xep_hang"]}
    w = [t for t in d["watch"] if t in by and by[t].get("pct") is not None]
    c1 = cot(w, [{"name": "percentile P/E hiện tại", "y": [by[t]["pct"] for t in w], "mau": "xanh",
                  "mau_tung": ["xanh" if by[t]["pct"] <= thr else ("vang" if by[t]["pct"] <= 50 else "do") for t in w]}],
             huong="doc", dv="", so_le=0, vach=[{"v": thr, "text": f"ngưỡng P{vn(thr, 0)} (LS {vn(d['hien_tai']['ls'], 2)}%)", "mau": "vang"},
                                               {"v": 13, "text": "ngưỡng TV in P13 (LS lỗi 11,78%)", "mau": "do"}],
             truc={"label": "percentile P/E 250 phiên", "min": 0, "max": 100})
    act = [r for r in d["xep_hang"] if r.get("kich_hoat") and r.get("hit_sig") is not None and (r.get("n_ngay") or 0) >= 60]
    act = sorted(act, key=lambda r: -r["hit_sig"])[:25][::-1]
    c2 = cot([r["ma"] for r in act], [{"name": "hit 60 phiên lịch sử", "y": [r["hit_sig"] for r in act], "mau": "xanh",
                                       "mau_tung": ["tim" if r["ma"] in set(d["watch"]) else None for r in act]}],
             nhan_phu=[f"P{vn(r['pct'], 0)} · ERP {vn(r.get('erp'), 1, True)}" for r in act], dv="%", so_le=0,
             vach=[{"v": 50, "text": "50%", "mau": "xam"}], truc={"label": "% lần có lãi khi tín hiệu", "min": 0, "max": 100})
    n_act = sum(1 for r in d["xep_hang"] if r.get("kich_hoat"))
    txt = (f"{n_act}/{len(d['xep_hang'])} mã của rổ đang có P/E dưới ngưỡng P{vn(thr, 0)}. TV in ngưỡng P13 vì đọc nhầm LS 11,78% (dòng năm 2008); "
           f"với LS đúng {vn(d['hien_tai']['ls'], 2)}% ngưỡng là P{vn(thr, 0)}, nên danh sách thật dài hơn danh sách TV in. "
           "Hit lịch sử ở đây là cách TV đo (ngày chồng nhau, EPS nhìn trước); xem trang từng mã cho tần suất độc lập và theo hướng LS.")
    return H.sec("signals", "Tín hiệu đang kích hoạt", [
        H.bieu_do("Danh mục + watchlist · percentile P/E hiện tại", c1, "Cột thấp hơn = P/E rẻ hơn lịch sử 250 phiên của chính mã.",
                  "Bloomberg · phiên đủ cuối", H.T_EST, 300),
        H.bieu_do("Top 25 mã đang bật · theo hit lịch sử", c2, "Nhãn phụ: percentile P/E · ERP cổ phiếu.", "tái lập", H.T_EST,
                  max(260, 20 * len(act) + 60)),
        H.doan(txt, the=True, tieu_de="Đọc danh sách")], so="8", eyebrow="Báo cáo per-stock ④ của TV")


def sec_hhp_scope(H, d):
    h = d.get("hhp")
    if not h:
        return None
    vn = H.vn
    tiles = []
    for met, lab in (("pe", "P/E"), ("pb", "P/B")):
        b = h.get(met) or {}
        if b.get("now") is None:
            continue
        tiles.append(H.tile(f"{lab} rổ (HHP)", vn(b["now"], 2) + "x", f"μ {vn(b['mean'], 2)} · {vn(b['sigma'], 2, True)}σ · {b.get('zone') or ''}",
                            "xanh" if (b.get("sigma") or 0) < -1 else ("do" if (b.get("sigma") or 0) > 1 else "xam"), H.T_EST))
    ex = h.get("exvic3") or {}
    if ex.get("pe_exv3_now") is not None:
        tiles.append(H.tile("P/E ngoài họ Vin (HHP)", vn(ex["pe_exv3_now"], 2) + "x", f"{vn(ex.get('exv3_pe_sigma'), 2, True)}σ", "lam", H.T_EST))
    rows = d.get("bang_chung") or []
    zc = {"rẻ": 0, "trung tính": 0, "đắt": 0, "không tin cậy": 0}
    for r in rows:
        s = r.get("hhp_sigma")
        if s is None:
            continue
        chi = next((c for c in r["chieu"] if c["k"] == "HHP"), None)
        if chi and "không tin cậy" in chi["t"]:
            zc["không tin cậy"] += 1
        elif s < -1:
            zc["rẻ"] += 1
        elif s > 1:
            zc["đắt"] += 1
        else:
            zc["trung tính"] += 1
    tiles.append(H.tile("Thành viên theo vùng σ", f"{zc['rẻ']} rẻ · {zc['đắt']} đắt", f"{zc['trung tính']} trung tính · {zc['không tin cậy']} σ không tin cậy",
                        None, H.T_EST))
    blocks = [{"kieu": "o_so", "cot": 4, "o": tiles}]
    for met, lab in (("pe", "P/E"), ("pb", "P/B")):
        b = h.get(met) or {}
        ch = b.get("chuoi") or {}
        if not ch.get("x"):
            continue
        mu, m1, p1, m2, p2 = b.get("mean"), b.get("m1"), b.get("p1"), b.get("m2"), b.get("p2")
        blk = {"x": ch["x"], "left": {"label": f"{lab} (lần)"}, "series": [
            {"name": "±1σ", "style": "band", "y_lo": [m1] * len(ch["x"]), "y_hi": [p1] * len(ch["x"]), "mau": "grey", "alpha": 0.10},
            {"name": f"{lab} rổ", "y": ch["y"], "style": "line", "mau": "blue"},
            {"name": "μ", "y": [mu] * len(ch["x"]), "style": "dash", "mau": "amber"}],
            "annotations": [a for a in (hline(m2, "−2σ", "bull", w=0.01 * (mu or 1)), hline(p2, "+2σ", "bear", w=0.01 * (mu or 1))) if a]}
        blocks.append(H.bieu_do(f"HHP · {lab} {d['ro']} trong dải μ ± σ của chính nó", blk,
                                "Dải σ HHP tính trên lịch sử tuần của chính rổ (cửa sổ 12/2017 →)."
                                + (" Gai ngày 03/08/2026 là lỗi nguồn rổ VN30 đã biết, không phải biến động thật." if d["ro"] == "VN30" else ""),
                                "engine HHP (hhp_baskets.json)", H.T_EST, 280))
    pe, pb = h.get("pe") or {}, h.get("pb") or {}
    def z(v):
        return None if v is None else (-1 if v < -1 else (1 if v > 1 else 0))
    zpe, zpb = z(pe.get("sigma")), z(pb.get("sigma"))
    rule = {(-1, -1): "rẻ cả P/E lẫn P/B: tín hiệu đáng tin nhất",
            (-1, 0): "P/E rẻ nhưng P/B không rẻ: coi chừng lợi nhuận đỉnh chu kỳ",
            (-1, 1): "P/E rẻ nhưng P/B đắt: lợi nhuận đang ở đỉnh trên nền vốn đắt, bẫy kinh điển",
            (0, -1): "P/B rẻ nhưng P/E chỉ trung tính: lợi nhuận đang thấp, định giá đỡ bằng tài sản",
            (0, 0): "cả hai trong dải trung tính: định giá không phải trụ đỡ cũng không phải rủi ro chính",
            (0, 1): "P/B đắt trong khi P/E trung tính: thị trường đang trả cho ROE cao, rủi ro nằm ở ROE",
            (1, -1): "P/E đắt nhưng P/B rẻ: lợi nhuận đang sụp, phải đọc P/B",
            (1, 0): "P/E đắt, P/B trung tính: lợi nhuận đang yếu đi so với nền vốn",
            (1, 1): "đắt cả P/E lẫn P/B: định giá là rủi ro chính"}.get((zpe, zpb), "thiếu một trong hai thước đo")
    blocks.append(H.doan(f"Luật ba ô của HHP cho {d['ro']}: P/E {vn(pe.get('sigma'), 2, True)}σ, P/B {vn(pb.get('sigma'), 2, True)}σ, "
                         f"{rule}. Cửa sổ HHP (8 năm) và cửa sổ TV (250 phiên) đo hai thứ khác nhau: HHP hỏi “rẻ so với chu kỳ của chính rổ”, "
                         "TV hỏi “rẻ so với 1 năm gần nhất”.", the=True, tieu_de="Đọc định giá HHP"))
    return H.sec("hhp", f"Định giá HHP của rổ {d['ro']}", blocks, so="9", eyebrow="Module ĐỊNH GIÁ HHP (đọc chỉ đọc)")


def sec_vimo(H, vimo, d=None):
    if not vimo:
        return None
    vn = H.vn
    tg = vimo.get("tien_gui_niem_yet") or {}
    ib = vimo.get("lien_nh") or {}
    t10 = vimo.get("tpcp10") or {}
    sgi = vimo.get("sgi") or {}
    ci = sgi.get("chi_so") or {}
    nh = [r for r in vimo.get("nhnn_6_12") or [] if r.get("dep_hi") is not None]
    last_nh = nh[-1] if nh else {}
    fi = vimo.get("fiinprox") or {}

    def val(x):
        return x.get("v") if isinstance(x, dict) else x

    # số dẫn xuất từ chuỗi (không viết cứng): ngày LS 13T đứng yên, biến động TPCP 10 năm từ đầu năm, ngưỡng TV theo hai mức LS
    y13, x13 = tg.get("y13") or [], tg.get("x") or []
    flat_since = None
    if y13:
        k = len(y13) - 1
        while k > 0 and y13[k - 1] == y13[-1]:
            k -= 1
        flat_since = x13[k] if k < len(x13) else None
    ty, tx = t10.get("y") or [], t10.get("x") or []
    ytd_bp = None
    if ty and tx:
        y0 = [v for xx, v in zip(tx, ty) if xx < tx[-1][:4] + "-01-01"]
        ytd_bp = (ty[-1] - y0[-1]) * 100 if y0 else None
    nh_hi = last_nh.get("dep_hi") if last_nh else None
    mk_lo, mk_hi = val(ci.get("ls_huy_dong_6_12t_thap")), val(ci.get("ls_huy_dong_6_12t_cao"))
    ls_tv = fi["y"][-1] if fi.get("y") else None

    def thr(ls):
        return None if ls is None else max(5.0, 40.0 - 4.0 * (ls - 5.0))
    tiles = [
        H.tile("13T niêm yết · NH lớn", vn(tg["y13"][-1], 2) + "%" if tg.get("y13") else None, (f"đứng yên từ {H.ddmm(flat_since)}" if flat_since and flat_since != x13[-1] else "vừa đổi") + f" · {H.ddmm(x13[-1]) if x13 else ''}",
               "xam", H.T_FACT),
        H.tile("NHNN 6–12T (khoảng)", f"{vn(last_nh.get('dep_lo'), 1)}–{vn(last_nh.get('dep_hi'), 1)}%" if last_nh else None,
               f"tháng {last_nh.get('thang', '')} · biên trên {vn(nh_hi, 1)}", "vang", H.T_FACT),
        H.tile("Huy động đỉnh thị trường", f"{vn(val(ci.get('ls_huy_dong_6_12t_thap')), 2)}–{vn(val(ci.get('ls_huy_dong_6_12t_cao')), 2)}%"
               if ci.get("ls_huy_dong_6_12t_cao") else None, "6–12T online, bản tuần SGI", "do", "NEWS"),
        H.tile("FiinProX >12T “cao nhất”", vn(fi["y"][-1], 2) + "%" if fi.get("y") else None, f"chuỗi TV dùng · mốc {H.ddmm(fi['x'][-1]) if fi.get('x') else ''}",
               "lam", H.T_FACT),
        H.tile("Liên NH qua đêm", vn(ib["on"][-1], 2) + "%" if ib.get("on") else None, f"{H.ddmm(ib['x'][-1]) if ib.get('x') else ''} · biến chính sách", None, H.T_FACT),
        H.tile("Liên NH 6 tháng", vn(val(ci.get("lnh_6t")), 2) + "%" if ci.get("lnh_6t") else None, "stress thật nằm ở kỳ hạn 3–6T", "vang", "FACT-T1"),
        H.tile("TPCP 10 năm", vn(t10["y"][-1], 2) + "%" if t10.get("y") else None, "HNX par-yield" + (f" · {vn(ytd_bp, 0, True)}bp từ đầu năm" if ytd_bp is not None else ""), None, H.T_FACT),
        H.tile("Chế độ tiền (SGI)", sgi.get("che_do") or None, f"điều kiện đáy {sgi.get('dieu_kien_day', '')} · tiền mặt đề xuất {sgi.get('tien_mat_de_xuat', '')}%",
               "do" if (sgi.get("che_do") or "").upper().startswith("SIẾT") else "xam", H.T_EST)]
    ser = []
    x = tg.get("x") or []
    if x:
        ser.append({"name": "13T niêm yết NH lớn", "y": tg["y13"], "style": "line", "mau": "amber"})
        ser.append({"name": "6–9T niêm yết NH lớn", "y": tg["y6"], "style": "dash", "mau": "amber"})
        for name, xs, ys, mau, sty in (("Liên NH qua đêm", ib.get("x"), ib.get("on"), "grey", "thin"),
                                       ("Liên NH 2 tuần", ib.get("x"), ib.get("w2"), "blue", "thin"),
                                       ("TPCP 10 năm", t10.get("x"), t10.get("y"), "violet", "line")):
            if xs:
                ys2, j, last = [], 0, None
                for xx in x:
                    while j < len(xs) and xs[j] <= xx:
                        last = ys[j] if j < len(ys) else last
                        j += 1
                    ys2.append(last)
                ser.append({"name": name, "y": ys2, "style": sty, "mau": mau})
    blocks = [{"kieu": "o_so", "cot": 4, "o": tiles}]
    if ser:
        blocks.append(H.bieu_do("Bốn thước đo lãi suất, lệch pha nhau", {"x": x, "left": {"label": "%/năm", "min": 0}, "series": ser,
                                                                          "annotations": [a for a in [hline(nh_hi, f"biên trên NHNN 6–12T {vn(nh_hi, 1)}%", "bear", w=0.02)] if a]},
                                f"Niêm yết NH lớn {vn(y13[-1] if y13 else None, 2)}% so với đỉnh thị trường {vn(mk_lo, 2)}–{vn(mk_hi, 2)}% và TPCP 10 năm "
                                f"{vn(ytd_bp, 0, True)}bp từ đầu năm: một con số LS “trung bình” không mô tả được giá vốn thật.",
                                "WiChart lshd/lslnh · HNX · NHNN (hhp_rates_sbv) · bản tuần SGI", H.T_FACT, 300))
    dk = sgi.get("dk") or []
    if dk:
        blocks.append(H.bang(["Điều kiện đáy chu kỳ (SGI §5.1)", "Trạng thái"],
                             [[H.cell(x["ten"], mono=False), H.cell(x["trang_thai"], "xanh" if x["trang_thai"] == "ĐẠT" else
                                                                    ("vang" if "PHẦN" in (x["trang_thai"] or "") else "do"), pill=True)] for x in dk],
                             f"Bản tuần SGI {sgi.get('ky', '')} · dữ liệu đến {sgi.get('du_lieu_den', '')}"))
    t_tv, t_mk = thr(ls_tv), thr(mk_lo)
    txt = (f"TV đặt toàn bộ luật lên MỘT con số LS (FiinProX >12T “cao nhất”, chuỗi tháng, hiện {vn(ls_tv, 2)}%). Các thước đo đang lệch pha: "
           f"niêm yết NH lớn {vn(y13[-1] if y13 else None, 2)}%" + (f" (đứng yên từ {H.ddmm(flat_since)})" if flat_since and x13 and flat_since != x13[-1] else "")
           + f", biên NHNN 6–12T {vn(nh_hi, 1)}%, đỉnh thị trường {vn(mk_lo, 2)}–{vn(mk_hi, 2)}%, TPCP 10 năm {vn(ytd_bp, 0, True)}bp từ đầu năm. "
           f"Chế độ SGI {sgi.get('che_do') or 'n/a'}, điều kiện đáy {sgi.get('dieu_kien_day') or 'n/a'}. "
           f"Với luật TV: ngưỡng hiện là P{vn(t_tv, 1)} tính trên {vn(ls_tv, 2)}%; nếu dùng mức huy động thị trường {vn(mk_lo, 1)}% thì ngưỡng còn "
           f"P{vn(t_mk, 0)} và danh sách tín hiệu ngắn lại. LTT (LS thôi tăng) chỉ bật khi cả huy động niêm yết lẫn đỉnh thị trường thôi lập đỉnh "
           "và liên ngân hàng hạ nhiệt cùng lúc.")
    blocks.append(H.doan(txt, the=True, tieu_de="Xu hướng lãi suất · đọc theo deep-macro-sgi"))
    if vimo.get("tin_dung_m2", {}).get("ghi_chu"):
        blocks.append(H.canh_bao("Lưu ý chuỗi tiền tệ", [vimo["tin_dung_m2"]["ghi_chu"]] + (t10.get("canh_bao") or [])[:2]))
    return H.sec("vimo", "Lãi suất & chế độ tiền", blocks, so="10", eyebrow="Module vĩ mô · skill deep-macro-sgi")


NHAN_MAU = {"Hội tụ mạnh": "xanh", "Hội tụ": "xanh", "Lẫn lộn": "vang", "Ngược chiều": "do"}


def evidence_table(H, rows, limit=None):
    vn = H.vn
    out = []
    for r in rows[:limit] if limit else rows:
        dims = {c["k"]: c for c in r.get("chieu") or []}

        def dcell(k, txt):
            c = dims.get(k)
            if not c:
                return H.cell("n/a", "xam")
            return H.cell(txt, "xanh" if c["s"] > 0 else ("do" if c["s"] < 0 else None), tip=c["t"])
        out.append([H.cell(r["ma"], dam=True), H.cell(r["nhan"], NHAN_MAU.get(r["nhan"]), pill=True, mono=False),
                    H.cell(vn(r["diem"], 0, True)),
                    dcell("TV", f"P{vn(r.get('pct'), 0)}/{vn(r.get('nguong'), 0)}"),
                    dcell("HHP", (f"{(r.get('hhp_do') or '').upper()} {vn(r.get('hhp_sigma'), 1, True)}σ") if r.get("hhp_sigma") is not None else "n/a"),
                    dcell("ERP", vn(r.get("erp"), 1, True)), dcell("EPS", vn(r.get("eps26"), 0, True, "%") if r.get("eps26") is not None else "n/a"),
                    dcell("Lịch sử", f"{vn(r.get('ls_xs'), 1, True)} · {r.get('ls_n') or 0} đợt" if r.get("ls_xs") is not None else "n/a"),
                    dcell("Chủ thể", (f"NB {vn(r.get('nb12_pct'), 2, True)}%" if r.get("nb12_pct") is not None else "n/a") + (" · huy động" if r.get("huy_dong") else "")),
                    H.cell(vn(r.get("hit60_co"), 0, suffix="%") if r.get("hit60_co") is not None else "n/a",
                           tip="tần suất co: luật TV bật + hướng LS hiện tại, không nhìn trước EPS" + ("" if r.get("kich_hoat") else " · luật TV hiện KHÔNG bật ở mã này")),
                    H.cell("điểm gãy", mono=False, tip=r.get("diem_gay"))])
    return H.bang(["Mã", "Mức hội tụ", "Điểm", "TV P/ngưỡng", "HHP σ", "ERP", "EPS 26", "Lịch sử", "Chủ thể", "Thắng 60 (co)", "Gãy"], out,
                  "Rê chuột lên ô để xem lý do. Đây là mức hội tụ bằng chứng, không phải khuyến nghị mua/bán; CỔNG đang DỪNG nên không gán hành động.",
                  can_phai=[2, 5, 6, 9])


def sec_evidence(H, d):
    rows = sorted(d.get("bang_chung") or [], key=lambda r: (-r["diem"], r["ma"]))
    if not rows:
        return None
    cnt = {}
    for r in rows:
        cnt[r["nhan"]] = cnt.get(r["nhan"], 0) + 1
    lab = list(NHAN_MAU)
    c = cot(lab, [{"name": "số mã", "y": [cnt.get(k, 0) for k in lab], "mau": "xanh", "mau_tung": [NHAN_MAU[k] for k in lab]}],
            huong="doc", dv="", so_le=0, truc={"label": "số mã"})
    strong = [r["ma"] for r in rows if r["nhan"] == "Hội tụ mạnh"]
    against = [r["ma"] for r in rows if r["nhan"] == "Ngược chiều"]
    txt = (f"Sáu chiều chấm −1/0/+1: luật TV, dải σ HHP (chỉ khi σ tin cậy), ERP cổ phiếu, lịch sử theo đợt độc lập, EPS FY2026 đồng thuận, "
           f"chủ thể (nội bộ ròng 12 tháng). Hội tụ mạnh: {', '.join(strong[:20]) or 'không mã nào'}. Ngược chiều: {', '.join(against[:20]) or 'không mã nào'}. "
           f"Chiều thứ bảy, hướng LS 6 tháng (hiện “{_dir_name(d['hien_tai']['dls6m'])}”, {H.vn(d['hien_tai']['dls6m'], 2, True)} điểm), áp chung cho cả rổ; "
           "cột “Thắng 60 (co)” là tần suất khi luật TV bật TRONG đúng chiều LS hiện tại, bản không nhìn trước EPS, co về tần suất cả rổ. "
           "Không có mã nào được gán hành động khi CỔNG chưa xác định được chu kỳ tiền.")
    return H.sec("bangchung", f"Bảng tổng hợp bằng chứng · {len(rows)} mã", [
        H.bieu_do("Phân bố mức hội tụ", c, "", "toanvu_pe_sau.py · HHP · Vietcap IQ", H.T_EST, 240),
        H.doan(txt, the=True, tieu_de="Cách đọc"),
        evidence_table(H, rows)], so="11", eyebrow="Kết hợp TV × HHP × EPS × chủ thể")


def sec_hoidong(H, key, so="12"):
    hd = load_hoidong(H, key)
    if not hd:
        return H.sec("hoidong", "Hội đồng cố vấn AI chứng khoán", [H.doan(
            f"Chưa có bản nhận định Hội đồng cho {key}. Bản nhận định được dựng ngoài app từ gói dữ kiện của trang này "
            f"(lưu ở state/toanvu_pe/hoi_dong/{key}.json).", "xam")], so=so, eyebrow="Kill zone → Alpha zone")
    blocks = []
    dc = ((H.read_json(H.STATE / "hoi_dong" / "_dinh_chinh.json") or {}).get("ma") or {}).get(key)
    if dc and dc.get("ngay_ban") == hd.get("ngay"):
        blocks.append(H.canh_bao("Đính chính dữ liệu sau ngày viết (tự động, đối chiếu số hiện tại)", dc.get("dong") or []))
    if hd.get("tom_tat"):
        blocks.append(H.doan(hd["tom_tat"], the=True, tieu_de=f"Kết luận Hội đồng · {hd.get('ngay', '')}"))
    cards = []
    for g, lab, mau in (("kill_zone", "KILL ZONE", "do"), ("alpha_zone", "ALPHA ZONE", "xanh"), ("bench", "CHUYÊN GIA", "lam")):
        for a in hd.get(g) or []:
            cards.append(H.the_card(f"{a.get('ten', '')} · {lab}", a.get("y_kien", ""), nhan=a.get("phieu"),
                                    nhan_mau={"ỦNG HỘ": "xanh", "PHẢN BIỆN": "do", "CHỜ": "vang"}.get((a.get("phieu") or "").upper(), "xam"),
                                    mau_vien=mau, tier=a.get("bac", H.T_EST)))
    if cards:
        blocks.append({"kieu": "the", "the": cards, "cot": 3})
    if hd.get("bat_dong"):
        blocks.append(H.bang(["Điểm bất đồng", "Phe ủng hộ", "Phe phản đối", "Dữ kiện phân xử"],
                             [[H.cell(x.get("diem", ""), mono=False), H.cell(x.get("ung_ho", ""), mono=False), H.cell(x.get("phan_doi", ""), mono=False),
                               H.cell(x.get("phan_xu", ""), mono=False)] for x in hd["bat_dong"]], "Disagreement matrix"))
    for k, lab, mau in (("pre_mortem", "Pre-mortem: 18 tháng sau giảm 50%, cái gì đã giết thesis?", "do"),
                        ("xac_nhan", "Điều kiện xác nhận", "xanh"), ("phu_dinh", "Điều kiện phủ định (điểm gãy)", "do")):
        if hd.get(k):
            blocks.append(H.canh_bao(lab, hd[k] if isinstance(hd[k], list) else [hd[k]], mau))
    if hd.get("rigor"):
        rg = hd["rigor"]
        blocks.append(H.bang(["Rigor 6D", "Điểm /5", "Ghi chú"],
                             [[H.cell(k, mono=False), H.cell(H.vn(v.get("diem"), 0)), H.cell(v.get("ghi", ""), mono=False)] for k, v in rg.items()],
                             "Tự chấm độ chặt của lập luận (không phải conviction)."))
    return H.sec("hoidong", "Hội đồng cố vấn AI chứng khoán", blocks, so=so, eyebrow="Kill zone nói trước, có quyền veto")


def scope_page(H, code):
    d = load_ro(H, code)
    t = H.load_tong()
    vimo = H.read_json(H.STATE / "vimo.json") or {}
    cong = H.read_cong()
    secs = [H.sec("cong", f"{SCOPE_NAME[code]} · P/E × Lãi suất × ERP", [H.block_cong(cong)], eyebrow="HĐCV chứng khoán v1.7")]
    secs += doc_hieu_sections(H, "HPG")
    secs.append(H.sec("pp", "Chi tiết phương pháp và kiểm định", H.method_compact(t), so="0c", eyebrow="Cho người muốn đào sâu"))
    for fn in (sec_vitri, ):
        secs.append(fn(H, d))
    secs.append(sec_chart2(H, d, vimo))
    secs.append(sec_erp_zone(H, d))
    secs.append(sec_chart1(H, d))
    for fn in (sec_ranking, sec_watch, sec_regime, sec_signals, sec_hhp_scope):
        s = fn(H, d)
        if s:
            secs.append(s)
    v = sec_vimo(H, vimo, d)
    if v:
        secs.append(v)
    e = sec_evidence(H, d)
    if e:
        secs.append(e)
    secs.append(sec_hoidong(H, code))
    return d, apply_guides(H, secs)


# ══════════════════════════════ TRANG MỘT MÃ (mở rộng) ══════════════════════════════

def phase_text(H, p):
    vn = H.vn
    s = (f"{H.ddmm(p['tu'])} → {H.ddmm(p['den'])}{' (đang chạy)' if p.get('dang_chay') else ''}, {p['tuan']} tuần: giá {vn(p['r'], 0, True)}%")
    if p.get("eps_pct") is not None:
        s += f" = EPS {vn(p['eps_pct'], 0, True)}% × P/E {vn(p['pe_pct'], 0, True)}% ({vn(p.get('pe0'), 1)}x → {vn(p.get('pe1'), 1)}x)"
    s += f". {p['kieu']}."
    if p.get("vni_r") is not None:
        s += f" VN-Index cùng kỳ {vn(p['vni_r'], 0, True)}% (chênh {vn(p['vuot_vni'], 0, True)} điểm)."
    if p.get("ls0") is not None and p.get("ls1") is not None:
        s += f" LS {vn(p['ls0'], 1)} → {vn(p['ls1'], 1)}%."
    nb = p.get("noi_bo") or {}
    if nb.get("mua") or nb.get("ban"):
        s += f" Nội bộ/người liên quan đã thực hiện (gồm lệnh khối, không khai báo): mua {vn(nb['mua'] / 1e6, 2)} tr cp, bán {vn(nb['ban'] / 1e6, 2)} tr cp"
        if nb.get("rong_pct_cp") is not None:
            s += f" (ròng {vn(nb['rong_pct_cp'], 2, True)}% số cp)"
        if nb.get("lon_nhat"):
            x = nb["lon_nhat"]
            who = x["ten"] + (f" ({x['vai']})" if x.get("vai") else "") if x.get("ten") else (x.get("vai") or "tổ chức không nêu tên")
            s += f"; lớn nhất {who} {vn(x['kl'] / 1e6, 2, True)} tr cp {H.ddmm(x['ngay'])}"
        s += "."
    if nb.get("quyen_esop"):
        s += f" Nhận qua quyền mua/ESOP: {vn(nb['quyen_esop'] / 1e6, 2)} tr cp (không tính vào ròng)."
    if p.get("phat_hanh"):
        s += " Vốn: " + "; ".join(f"{x['loai']} {H.ddmm(x['ngay'])}" for x in p["phat_hanh"][:3]) + "."
    return s


def sec_phases(H, tk, s, p_main):
    vn = H.vn
    ph = [p for p in s.get("pha") or [] if p.get("tu") >= "2008-01-01"]
    if not ph:
        return None
    c = p_main.get("chuoi") or {}
    i0 = next((i for i, v in enumerate(c.get("x") or []) if v >= ph[0]["tu"]), 0)
    xs = (c.get("x") or [])[i0:]
    blk = {"x": xs, "left": {"label": "Giá điều chỉnh (VND)"}, "series": [{"name": "Giá (Bloomberg)", "y": (c.get("px") or [])[i0:], "style": "line", "mau": "ink"}],
           "annotations": []}
    for j, p in enumerate(ph):
        m = KIEU_MAU.get(p["kieu"], "xam")
        blk["annotations"].append({"kind": "xband", "x0": H.iso_ms(p["tu"]), "x1": H.iso_ms(p["den"]), "alpha": 0.10, "mau": ANN_MAU[m],
                                   "text": f"{vn(p['r'], 0, True)}%", "uu_tien": 2})
        blk["annotations"].append({"kind": "point", "x": H.iso_ms(p["den"]), "y": p["px1"], "marker": "tri_up" if p["r"] < 0 else "tri_down",
                                   "pos": "below" if p["r"] < 0 else "above", "text": p["kieu"].split(" ")[0] + " " + vn(p["r"], 0, True, "%"),
                                   "mau": ANN_MAU[m], "uu_tien": 2 if j >= len(ph) - 6 else 3, "tip": phase_text(H, p)})
    pd_ = ph[-12:]   # 12 pha gần nhất: đủ rộng cho nhãn; bảng dưới vẫn liệt kê mọi pha
    lab = [f"{p['tu'][5:7]}/{p['tu'][2:4]}" for p in pd_]
    dec = cot(lab, [{"name": "EPS đổi %", "y": [p.get("eps_pct") for p in pd_], "mau": "xanh"},
                    {"name": "P/E đổi %", "y": [p.get("pe_pct") for p in pd_], "mau": "lam"},
                    {"name": "Giá đổi %", "y": [p["r"] for p in pd_], "mau": "xam"}], huong="doc", dv="%", so_le=0, dau=True,
              nhan_phu=[p["kieu"].split(" ")[0] + (" *" if p.get("dang_chay") else "") for p in pd_],
              truc={"label": "% thay đổi trong pha (giá = EPS × P/E)"})
    rows = [[H.cell(f"{H.ddmm(p['tu'])} → {H.ddmm(p['den'])}"), H.cell(vn(p["r"], 0, True, "%"), H.mau_sign(p["r"])),
             H.cell(vn(p.get("eps_pct"), 0, True, "%"), H.mau_sign(p.get("eps_pct"))), H.cell(vn(p.get("pe_pct"), 0, True, "%"), H.mau_sign(p.get("pe_pct"))),
             H.cell(p["kieu"], KIEU_MAU.get(p["kieu"]), pill=True, mono=False),
             H.cell(vn(p.get("vuot_vni"), 0, True), H.mau_sign(p.get("vuot_vni"))),
             H.cell(f"{vn(p.get('ls0'), 1)}→{vn(p.get('ls1'), 1)}"),
             H.cell(vn((p.get("noi_bo") or {}).get("rong_pct_cp"), 2, True, "%")),
             H.cell("chi tiết", mono=False, tip=phase_text(H, p))] for p in ph[::-1]]
    up = [p for p in ph if p["r"] > 0 and p.get("eps_pct") is not None]
    eps_led = sum(1 for p in up if p["kieu"] == "Tăng nhờ lợi nhuận")
    rer = sum(1 for p in up if p["kieu"] == "Tăng nhờ mở rộng P/E")
    last = ph[-1]
    txt = (f"{tk} có {len(ph)} pha giá (đảo chiều ≥ 25% theo tuần) từ 2008. Trong {len(up)} pha tăng tách được, {eps_led} pha chủ yếu nhờ lợi nhuận, "
           f"{rer} pha nhờ thị trường trả P/E cao hơn. Pha hiện tại: {phase_text(H, last)} "
           "Pha nhờ P/E mở rộng thường ngắn và gãy khi LS đảo chiều; pha nhờ EPS bền hơn nhưng phụ thuộc chu kỳ ngành.")
    return H.sec("pha", "Vì sao giá đi như vậy · các pha EPS × P/E", [
        H.bieu_do("Giá và các pha", blk, "Dải màu: xanh = tăng nhờ lợi nhuận, lam = tăng nhờ P/E, vàng = giảm do co P/E, đỏ = giảm do lợi nhuận. Rê chuột lên mốc cuối pha để đọc chi tiết.",
                  "Bloomberg (giá điều chỉnh, P/E) · Vietcap IQ (giao dịch nội bộ, sự kiện vốn)", H.T_FACT, 330),
        H.bieu_do("Tách lợi suất 12 pha gần nhất: giá = EPS × P/E", dec,
                  "Nhãn: tháng/năm bắt đầu pha · kiểu (* = đang chạy). EPS ngầm định = giá ÷ P/E trailing; pha có lỗ không tách được.", "tính lại", H.T_EST, 330),
        H.bang(["Pha", "Giá", "EPS", "P/E", "Động lực", "Vượt VNI", "LS", "Nội bộ ròng", ""], rows,
               "Mới nhất ở trên. Nội bộ ròng = (mua − bán) đã thực hiện của nội bộ + người liên quan ÷ số cp hiện tại (EST).", can_phai=[1, 2, 3, 5, 7]),
        H.doan(txt, the=True, tieu_de="Lịch sử tăng vì sao")], so="9", eyebrow="Phân rã lợi suất + chủ thể trong từng pha")


def hhp_live(tk):
    try:
        import hhp_valuation as hv
        return hv.clean(hv.build_ticker(hv.data_dir(), tk))
    except Exception as ex:  # noqa: BLE001
        return {"error": str(ex)}


def sec_hhp_ticker(H, tk, s):
    vn = H.vn
    hp = s.get("hhp")
    if not hp:
        return H.sec("hhpma", "Định giá HHP", [H.doan(f"HHP không có chuỗi cho {tk} ({s.get('hhp_loi') or 'không có dải σ tin cậy'}).", "xam")],
                     so="10", eyebrow="Module ĐỊNH GIÁ HHP")
    h = hhp_live(tk)
    met = hp["thuoc_do"]
    blk = (h or {}).get(met) or {}
    ch = blk.get("chart") or {}
    blocks = []
    tiles = [H.tile(f"{met.upper().replace('PE', 'P/E').replace('PB', 'P/B')} · vùng σ", f"{vn(hp.get('sigma'), 2, True)}σ", f"{hp.get('zone') or ''} · {hp['ly_do']}",
                    "xanh" if (hp.get("sigma") or 0) < -1 else ("do" if (hp.get("sigma") or 0) > 1 else "xam"), H.T_EST),
             H.tile("Giá trị hợp lý (μ)", vn((hp.get("band") or {}).get("fair"), 0) + "đ" if (hp.get("band") or {}).get("fair") else None,
                    f"tiềm năng {vn(hp.get('upside_fair'), 0, True)}%", "lam", H.T_EST),
             H.tile("Dải −1σ / +1σ", f"{vn((hp.get('band') or {}).get('cheap1'), 0)} / {vn((hp.get('band') or {}).get('rich1'), 0)}",
                    f"−2σ {vn((hp.get('band') or {}).get('cheap2'), 0)}đ", None, H.T_EST),
             H.tile("Độ tin cậy σ", "tin cậy" if hp.get("reliable") else "KHÔNG", f"μ {vn(hp.get('mean'), 2)} · sd {vn(hp.get('sd'), 2)}",
                    "xanh" if hp.get("reliable") else "do", H.T_EST)]
    blocks.append({"kieu": "o_so", "cot": 4, "o": tiles})
    if ch.get("price"):
        x = [p[0] for p in ch["price"]]

        def ys(k):
            return [p[1] for p in ch.get(k) or []]
        series = [{"name": "±2σ", "style": "band", "y_lo": ys("cheap2"), "y_hi": ys("rich2"), "mau": "grey", "alpha": 0.08},
                  {"name": "±1σ", "style": "band", "y_lo": ys("cheap1"), "y_hi": ys("rich1"), "mau": "up", "alpha": 0.12},
                  {"name": "Giá hợp lý (μ)", "y": ys("fair"), "style": "dash", "mau": "amber"},
                  {"name": "Giá (nghìn đồng, điều chỉnh)", "y": ys("price"), "style": "line", "mau": "ink"}]
        ann = []
        fc = (((h or {}).get("forecast") or {}).get(met) or {})
        pts = fc.get("points") or {}
        if pts.get("fair"):
            last_x = x[-1]

            def fpts(k):  # [[ms, v], ...] → chỉ các tháng SAU điểm lịch sử cuối; điểm đầu = neo nối liền
                return [(q[0], q[1]) for q in pts.get(k) or [] if q and q[0] is not None]
            fair = fpts("fair")
            anchor = next((v for m, v in fair if m <= last_x), None)
            fut = [(m, v) for m, v in fair if m > last_x]
            fx = [m for m, _ in fut]
            c1 = {m: v for m, v in fpts("cheap1")}
            r1 = {m: v for m, v in fpts("rich1")}
            x = x + fx
            pad = [None] * len(fx)
            for sr in series:
                if "y" in sr:
                    sr["y"] = sr["y"] + pad
                else:
                    sr["y_lo"], sr["y_hi"] = sr["y_lo"] + pad, sr["y_hi"] + pad
            n_h = len(ch["price"])
            head = [None] * (n_h - 1) + [anchor]
            series.append({"name": "Dự phóng μ (36 tháng)", "y": head + [v for _, v in fut], "style": "dot", "mau": "amber"})
            series.append({"name": "Dự phóng ±1σ", "style": "band", "y_lo": [None] * n_h + [c1.get(m) for m in fx],
                           "y_hi": [None] * n_h + [r1.get(m) for m in fx], "mau": "amber", "alpha": 0.10})
        for tg in (((h or {}).get("forecast") or {}).get("targets") or []):
            if tg.get("ms") and tg.get("value"):
                ann.append({"kind": "point", "x": tg["ms"], "y": tg["value"], "marker": "diamond", "pos": "above",
                            "text": f"{tg.get('org')} {vn(tg.get('value_vnd'), 0)}", "mau": "cyan", "uu_tien": 2,
                            "tip": f"{tg.get('org')} {tg.get('rating') or ''} · {tg.get('date')} · {tg.get('tier')}"})
        blocks.append(H.bieu_do(f"HHP · dải σ {met.upper()} trong không gian giá + dự phóng", {"x": x, "left": {"label": "nghìn đồng"}, "series": series,
                                                                                                "annotations": ann},
                                "Giá = cơ sở × bội số: cơ sở = EPS (P/E) hoặc BVPS (P/B). Dải σ trên lịch sử của chính mã (12/2017 →). Kim cương: giá mục tiêu.",
                                "engine HHP · hhp_valuation.py (chỉ đọc)", H.T_EST, 340))
    zh = s.get("hhp_vung_lich_su") or {}
    if zh:
        rows = [[H.cell(k, mono=False), H.cell(str(v.get("n60"))), H.cell(vn(v.get("hit60"), 0, suffix="%"), H.mau_sign((v.get("hit60") or 50) - 50, 5)),
                 H.cell(vn(v.get("r60"), 1, True, "%"), H.mau_sign(v.get("r60"))), H.cell(str(v.get("n120"))),
                 H.cell(vn(v.get("hit120"), 0, suffix="%"), H.mau_sign((v.get("hit120") or 50) - 50, 5)), H.cell(vn(v.get("r120"), 1, True, "%"), H.mau_sign(v.get("r120")))]
                for k, v in zh.items()]
        blocks.append(H.bang(["Vùng σ lúc mua", "Lần (60)", "Thắng 60", "Trung vị 60", "Lần (120)", "Thắng 120", "Trung vị 120"], rows,
                             "Mốc không chồng cửa sổ trên chuỗi tuần HHP. μ, σ là của TOÀN mẫu nên có nhìn trước (EST).", can_phai=[1, 2, 3, 4, 5, 6]))
    dp = s.get("du_phong") or {}
    if dp.get("eps_pins"):
        rows = [[H.cell(f"FY{x['year']}"), H.cell(vn(x.get("value"), 3)), H.cell(vn(100 * x["g"], 1, True, "%") if x.get("g") is not None else "neo"),
                 H.cell(x.get("g_tier") or x.get("tier") or "", mono=False)] for x in dp["eps_pins"]]
        blocks.append(H.bang(["Năm", "EPS (nghìn đồng)", "Tăng trưởng", "Bậc bằng chứng"], rows,
                             "Đường EPS 3 năm của HHP: FY2026–27 từ đồng thuận (Vietcap/CapIQ/HSC), các năm sau theo luật hội tụ (EST).", can_phai=[1, 2]))
    if dp.get("targets"):
        rows = [[H.cell(x.get("org") or "", mono=False), H.cell(H.ddmm(x.get("date"))), H.cell(vn(x.get("value_vnd"), 0)), H.cell(x.get("rating") or ""),
                 H.cell(x.get("tier") or ""), H.cell(x.get("note") or "", mono=False)] for x in dp["targets"]]
        blocks.append(H.bang(["Nguồn", "Ngày", "Giá mục tiêu", "Khuyến nghị nguồn", "Bậc", "Ghi chú"], rows,
                             "Giá mục tiêu của bên thứ ba (SS-T3/FACT-T2), trình bày để đối chiếu, không phải nhận định của tab.", can_phai=[2]))
    return H.sec("hhpma", "Định giá HHP · dải σ, dự phóng 3 năm, giá mục tiêu", blocks, so="10", eyebrow="Module ĐỊNH GIÁ HHP (đọc trực tiếp engine)")


def sec_winprob(H, tk, s):
    vn = H.vn
    wp = s.get("xac_suat") or []
    if not wp:
        return None
    lab = [w["ten"] for w in wp]
    c = cot(lab, [{"name": "thắng 60 phiên (co về rổ)", "y": [w.get("co") for w in wp], "mau": "xanh",
                   "mau_tung": ["xanh" if (w.get("co") or 0) >= 55 else ("vang" if (w.get("co") or 0) >= 48 else "do") for w in wp]},
                  {"name": "thắng 120 phiên (thô)", "y": [w.get("hit120") for w in wp], "mau": "xam"}],
            nhan_phu=[f"n {w['n']} · rổ {vn(w.get('p_ro'), 0)}%" for w in wp], dv="%", so_le=0,
            vach=[{"v": 50, "text": "50%", "mau": "xam"}], truc={"label": "% mốc vào có lãi", "min": 0, "max": 100})
    rows = [[H.cell(w["ten"], mono=False), H.cell(str(w["n"])), H.cell(vn(w.get("hit60"), 0, suffix="%")),
             H.cell(f"{vn(w['ci'][0], 0)}–{vn(w['ci'][1], 0)}%" if w.get("ci") and w["ci"][0] is not None else "n/a"),
             H.cell(vn(w.get("p_ro"), 0, suffix="%")), H.cell(vn(w.get("co"), 0, suffix="%"), "xanh" if (w.get("co") or 0) >= 55 else ("do" if (w.get("co") or 0) < 48 else "vang"), dam=True),
             H.cell(vn(w.get("r60_tv"), 1, True, "%"), H.mau_sign(w.get("r60_tv"))), H.cell(str(w.get("n120"))),
             H.cell(vn(w.get("hit120"), 0, suffix="%")), H.cell(vn(w.get("r120_tv"), 1, True, "%"), H.mau_sign(w.get("r120_tv")))] for w in wp]
    on = bool((s.get("bang_chung") or {}).get("kich_hoat"))
    key = next((w for w in wp if w["key"] == ("sig45_huong" if on else "huong")), None)
    base = next((w for w in wp if w["key"] == "all"), None)
    nhom = {"VN100": "VN100", "VN200": "nhóm VN101–200", "REST": "nhóm REST (ngoài VN200)"}.get(s.get("nhom_co") or "VN100", "VN100")
    txt = (f"Tần suất ở đây đếm mốc vào KHÔNG chồng cửa sổ (cách ≥ 60 hoặc 120 phiên), rồi co về tần suất cả {nhom} cùng điều kiện "
           f"((k + 8·p_rổ) ÷ (n + 8)) để mẫu nhỏ của một mã không đánh lừa. Gốc so sánh {tk}: thắng 60 phiên {vn(base.get('hit60'), 0)}% "
           f"trên {base['n']} mốc. " + (f"Luật TV đang BẬT; điều kiện sát hiện tại nhất (luật bật trong lúc LS “{s.get('huong_ls_now')}”, bản không nhìn trước EPS): "
                                         if on else f"Luật TV hiện KHÔNG bật ở {tk}; điều kiện sát hiện tại nhất là hướng LS “{s.get('huong_ls_now')}”: ")
           + f"{vn(key.get('hit60'), 0)}% thô trên {key['n']} mốc, co còn {vn(key.get('co'), 0)}%. ") if key and base else ""
    txt += "Đây là tần suất lịch sử có điều kiện, không phải xác suất dự báo; nó không chứa thông tin về KQKD sắp công bố hay sự kiện chủ thể."
    return H.sec("xacsuat", "Tần suất thắng 60 / 120 phiên theo điều kiện hiện tại", [
        H.bieu_do("Tần suất thắng theo điều kiện", c, "Nhãn phụ: số mốc độc lập · tần suất cả rổ cùng điều kiện.", "Bloomberg × FiinProX · tính lại",
                  H.T_EST, max(260, 40 * len(wp) + 60)),
        H.bang(["Điều kiện", "Mốc", "Thắng 60", "KTC 90%", "Rổ", "Co", "Trung vị 60", "Mốc 120", "Thắng 120", "Trung vị 120"], rows,
               "KTC 90% Wilson. Co = ước lượng sau khi co về rổ.", can_phai=list(range(1, 10))),
        H.doan(txt, the=True, tieu_de="Đọc xác suất")], so="11", eyebrow="Win-rate có điều kiện, không chồng cửa sổ")


def sec_owner(H, tk, s):
    vn = H.vn
    blocks = []
    ev = s.get("bang_chung") or {}
    if ev.get("huy_dong"):
        blocks.append(H.canh_bao("Chủ thể đang dùng sàn làm kênh vốn", [
            f"{tk} có đợt {ev['huy_dong']} trong 18 tháng gần nhất. Theo lăng kính v1.7, ở kỳ tiền đắt chủ thể có mục tiêu huy động thường phải giữ giá; "
            "đây là thông tin để đọc Pattern, không phải tín hiệu mua."], "lam"))
    reg = s.get("noi_bo_dang_ky") or []
    if reg:
        blocks.append(H.bang(["Công bố", "Cửa sổ", "Đăng ký"], [[H.cell(H.ddmm(r["ngay"])), H.cell(f"{H.ddmm(r['tu'])}→{H.ddmm(r['den'])}"),
                                                                H.cell(r["tieu_de"], mono=False)] for r in reg[::-1]],
                             "Giao dịch nội bộ ĐANG đăng ký (chưa có kết quả)."))
    nb = s.get("noi_bo") or []
    if nb:
        def cach(r):
            gia = f" ~{vn(r['gia_tt'], 0)}đ" if r.get("gia_tt") else ""
            if r.get("nguon"):
                return r["nguon"] + (f" · TT{gia}" if gia else "")
            if r.get("code") == "CHUOI":
                return (r.get("pt") or "không khai báo") + (f" đến {H.ddmm(r['den'])}" if r.get("den") else "")
            return (r.get("pt") or "chưa rõ") + gia
        # mọi dòng 12 tháng mang thông tin (chuỗi, nhãn loại, lệnh khối) luôn hiện; lấp cho đủ 20 bằng dòng mới nhất
        cut = (date.fromisoformat(s["phien"]) - timedelta(days=365)).isoformat() if s.get("phien") else ""
        nb12 = [r for r in nb if r["ngay"] >= cut]
        uu = [r for r in nb12 if r.get("code") == "CHUOI" or r.get("nguon") or r.get("pt") in ("thoả thuận", "ngoài sàn")]
        chon = {id(r) for r in uu} | {id(r) for r in [r for r in nb if r not in uu][:max(0, 20 - len(uu))]}
        hien = [r for r in nb if id(r) in chon]
        rows = [[H.cell(H.ddmm(r["ngay"])), H.cell(r["ten"], mono=False), H.cell(r["vai"], mono=False),
                 H.cell(vn(r["kl"], 0, True), "xam" if r.get("nguon") else H.mau_sign(r["kl"])),
                 H.cell(cach(r), "lam" if r.get("nguon") else None, pill=bool(r.get("nguon")), mono=False),
                 H.cell(vn(100 * r["sau_pct"], 3, suffix="%") if r.get("sau_pct") else "")] for r in hien]
        con = len(nb12) - sum(r["ngay"] >= cut for r in hien)
        blocks.append(H.bang(["Ngày", "Người giao dịch", "Vai trò / quan hệ", "KL thực hiện", "Cách giao dịch", "Sở hữu sau"], rows,
                             "Vietcap IQ insider-transaction (FACT-T2), đã khử dòng lặp. Cách giao dịch suy từ price-history theo ngày (EST): "
                             "thoả thuận = phiên có KL thoả thuận đúng bằng KL lệnh, giá là bình quân thoả thuận của phiên; ngoài sàn = KL vượt "
                             "dung lượng khớp + thoả thuận; không khai báo = chênh trong chuỗi số dư của cùng chủ thể. Lệnh khối vẫn tính vào ròng. "
                             "Ô xám (không tính): nhận qua quyền mua/ESOP/đợt phát hành, hoặc chuyển nội bộ có chân đối ứng còn ở trạng thái đăng ký. "
                             "Chưa rõ = KL vượt khớp lệnh của cửa sổ mà thoả thuận không phủ đủ."
                             + (f" Còn {con} dòng 12 tháng không hiện (đủ trong gói Hội đồng)." if con > 0 else ""),
                             can_phai=[3, 5]))
    von = s.get("von") or []
    if von:
        blocks.append(H.bang(["Ngày GDKHQ", "Loại", "Tỷ lệ", "Nội dung"], [[H.cell(H.ddmm(v["ngay"])), H.cell(v["loai"], "lam" if v["loai"] == "chào bán" else None, pill=True, mono=False),
                                                                         H.cell(vn(100 * (v.get("ty_le") or 0), 1, suffix="%") if v.get("ty_le") else ""),
                                                                         H.cell(v["tieu_de"], mono=False)] for v in von[:12]],
                             "Sự kiện vốn Vietcap events-v2 (FACT-T2)."))
    ft = s.get("su_kien_fft") or []
    if ft:
        blocks.append(H.bang(["Ngày", "Loại", "Mô tả", "Bậc"], [[H.cell(H.ddmm(e.get("ngay"))), H.cell(e.get("the_loai") or e.get("loai") or "", mono=False),
                                                                 H.cell((e.get("mo_ta") or "").replace(" [tự động]", ""), mono=False), H.cell(e.get("bac") or "")] for e in ft[:15]],
                             "Lớp tin DeepFA/fft_tin 13 tháng gần nhất (ĐHCĐ, phát hành, giao dịch nội bộ)."))
    if not blocks:
        return None
    return H.sec("chuthe", "Chủ thể, nội bộ và sự kiện vốn", blocks, so="12", eyebrow="Vietcap IQ × DeepFA (fft_tin)")


def sec_evidence_ma(H, tk, s):
    ev = s.get("bang_chung")
    if not ev:
        return None
    items = [(c.get("bac") or H.T_EST, f"{'▲' if c['s'] > 0 else ('▼' if c['s'] < 0 else '·')} {c['k']}: {c['t']}") for c in ev["chieu"]]
    card = H.the_card(f"{tk} · {ev['nhan']} ({H.vn(ev['diem'], 0, True)} điểm)",
                      f"Điều kiện xác nhận: {ev['xac_nhan']}. Điểm gãy: {ev['diem_gay']}.", nhan=ev["nhan"], nhan_mau=NHAN_MAU.get(ev["nhan"]),
                      mau_vien=NHAN_MAU.get(ev["nhan"]), tier=H.T_EST)
    return H.sec("bangchungma", "Bằng chứng tổng hợp", [{"kieu": "the", "the": [card], "cot": 1}, H.chips(items),
                                                         H.doan("▲ = chiều ủng hộ, ▼ = chiều ngược, · = trung tính; nhãn màu là bậc bằng chứng của con số. Không phải khuyến nghị mua/bán; CỔNG đang DỪNG.", "xam")],
                 so="13", eyebrow="TV × HHP × EPS × chủ thể")


def deep_sections(H, tk, p_main):
    s = load_sau(H, tk)
    if not s:
        return [H.sec("sau", "Lớp phân tích sâu", [H.doan(f"Chưa có lớp sâu cho {tk}. "
                                                           "Chạy: python3 scripts/toanvu_pe_sau.py", "xam")], so="9")]
    out = [sec_phases(H, tk, s, p_main), sec_hhp_ticker(H, tk, s), sec_winprob(H, tk, s), sec_owner(H, tk, s), sec_evidence_ma(H, tk, s),
           sec_hoidong(H, tk, so="14")]
    return [x for x in out if x]
