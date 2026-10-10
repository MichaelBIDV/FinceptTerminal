#!/usr/bin/env python3
"""
chaebol_map_tab_vciq_parts: các tab con của tab "★ VIETCAP IQ" (chỉ mode live), dựng từ chaebol_map_data_vciq.

Bố cục bám trang trading.vietcap.com.vn/iq/company: Tổng quan · Tài chính · Thống kê (Lịch sử giá, Nước ngoài, Tự doanh,
Nội bộ, Cung cầu × D/W/M/Q/Y) · Cổ đông · Tin tức & Sự kiện (5 tab con, kèm link PDF CBTT) · Báo cáo phân tích ·
Kỹ thuật · Quỹ. Số định dạng en-US (DESIGN §11.1), chữ mới tiếng Việt (§11.4), mỗi bảng một nhãn bậc ở dòng nguồn.
Giá cổ phiếu hiển thị theo nghìn đồng như Vietcap (70.70); giá trị giao dịch theo triệu đồng; BCTC theo tỷ đồng.
"""
from __future__ import annotations

from chaebol_map_dom import C, F_MONO, can_data, h, tier, to_fixed, to_locale
from chaebol_map_shell import Card, Stat

K_SUB, K_ST, K_TF, K_FS, K_PER, K_EV = "vciq.sub", "vciq.st", "vciq.tf", "vciq.fs", "vciq.per", "vciq.ev"
F_SERIF = "'Source Serif 4', serif"
DASH = "-"

S_TABLE = {"width": "100%", "borderCollapse": "collapse", "fontFamily": F_MONO, "fontSize": 10.5}
S_TH = {"padding": "7px 8px", "textAlign": "right", "color": C.inkD, "fontWeight": 600, "letterSpacing": ".08em",
        "fontSize": 9, "borderBottom": "1px solid " + C.rule, "whiteSpace": "nowrap"}
S_TH_L = {**S_TH, "textAlign": "left"}
S_TD = {"padding": "6px 8px", "textAlign": "right", "color": C.ink, "whiteSpace": "nowrap"}
S_TD_L = {**S_TD, "textAlign": "left", "whiteSpace": "normal"}
S_TR = {"borderBottom": "1px solid " + C.rule + "60"}
S_SRC = {"fontSize": 9.5, "color": C.inkD, "fontFamily": F_MONO, "lineHeight": 1.7, "marginTop": 8}
S_SCROLL = {"overflowX": "auto"}
S_BTN = {"background": "transparent", "color": C.inkD, "border": "1px solid " + C.rule, "padding": "5px 11px",
         "borderRadius": 2, "cursor": "pointer", "fontFamily": F_MONO, "fontSize": 10, "fontWeight": 500,
         "letterSpacing": ".06em"}
S_ON = {"background": C.gold, "color": C.bg, "border": "1px solid " + C.gold, "fontWeight": 700}
S_BAR = {"display": "flex", "gap": 5, "flexWrap": "wrap", "alignItems": "center", "marginBottom": 12}


# ── định dạng ──────────────────────────────────────────────────────────────


def dmy(d):
    return "%s/%s/%s" % (d[8:10], d[5:7], d[:4]) if d and len(d) >= 10 else DASH


def num(v, frac=0):
    return DASH if v is None else to_locale(v, max_frac=frac, min_frac=frac)


def px(v):
    """Giá theo nghìn đồng, 2 số lẻ (70.70)."""
    return DASH if v is None else to_locale(v / 1000, min_frac=2, max_frac=2)


def mil(v):
    """Triệu đồng."""
    return DASH if v is None else to_locale(v / 1e6, max_frac=0)


def ty(v, frac=0):
    return DASH if v is None else to_locale(v / 1e9, max_frac=frac, min_frac=frac)


def pct(v, frac=2, mul=100):
    return DASH if v is None else to_fixed(v * mul, frac) + "%"


def sgn_col(v):
    return C.inkM if v is None else (C.forest if v > 0 else (C.vermillion if v < 0 else C.inkD))


def src_line(*parts, tag="T2", asof=None):
    return h("div", S_SRC, *parts, tier(tag, asof))


def bar(key, items, prefix):
    return h("div", S_BAR, *[h("button", S_BTN, lbl, on={"set": {key: sid}}, var=[{"if": {key: sid}, "s": S_ON}],
                                key="%s.%s" % (prefix, sid)) for sid, lbl in items])


def table(heads, rows, left=1):
    """heads: [(nhãn, colspan?)] một hoặc hai tầng; rows: list[list[node|str]] (cột < left căn trái)."""
    thead = []
    for tier_heads in heads:
        ths, col = [], 0
        for lbl, span in tier_heads:
            st = S_TH_L if col < left else S_TH
            ths.append(h("th", None, lbl, cls=st, a={"colSpan": span} if span > 1 else None))
            col += span
        thead.append(h("tr", None, *ths))
    body = [h("tr", None, *[h("td", None, c, cls=S_TD_L if i < left else S_TD) for i, c in enumerate(r)], cls=S_TR)
            for r in rows]
    return h("div", None, h("table", None, h("thead", None, *thead), h("tbody", None, *body), cls=S_TABLE),
             cls=S_SCROLL)


def colored(text, v):
    return h("span", {"color": sgn_col(v)}, text)


def empty(msg):
    return h("p", {"fontSize": 11, "color": C.inkD, "fontFamily": F_MONO, "margin": "6px 0"}, can_data(msg))


# ── Thống kê ───────────────────────────────────────────────────────────────

KINDS = (("gia", "Lịch sử giá"), ("nn", "Nước ngoài"), ("td", "Tự doanh"), ("nb", "Nội bộ"), ("cc", "Cung cầu"))
TFS = (("D", "D"), ("W", "W"), ("M", "M"), ("Q", "Q"), ("Y", "Y"))
TF_NAME = {"D": "Ngày", "W": "Tuần", "M": "Tháng", "Q": "Quý", "Y": "Năm"}


def _stat_gia(s, tf):
    heads = [[("%s %d" % (TF_NAME[tf], s["n_ky"]), 1), ("Thay đổi giá", 1), ("Giá (nghìn đồng)", 4),
              ("GD khớp lệnh", 2), ("GD thoả thuận", 2), ("Tổng GD", 2), ("KL chưa khớp (cp)", 2),
              ("Vốn hoá (triệu)", 1)],
             [("", 1), ("", 1), ("Đóng", 1), ("Mở", 1), ("Cao", 1), ("Thấp", 1), ("KL", 1), ("GT (triệu)", 1),
              ("KL", 1), ("GT (triệu)", 1), ("KL", 1), ("GT (triệu)", 1), ("Mua", 1), ("Bán", 1), ("", 1)]]
    rows = [[dmy(r["ky"]), colored("%s (%s%%)" % (("+" if (r["thay_doi"] or 0) > 0 else "") + px(r["thay_doi"]),
                                                  to_fixed(r["thay_doi_pct"], 1) if r["thay_doi_pct"] is not None
                                                  else DASH), r["thay_doi"]),
             px(r["dong"]), px(r["mo"]), px(r["cao"]), px(r["thap"]), num(r["kl_khop"]), mil(r["gt_khop"]),
             num(r["kl_tt"]), mil(r["gt_tt"]), num(r["kl"]), mil(r["gt"]), num(r["chua_khop_mua"]),
             num(r["chua_khop_ban"]), mil(r["von_hoa"])] for r in s["rows"]]
    return heads, rows


def _stat_flow(s, tf, label):
    heads = [[("%s %d" % (TF_NAME[tf], s["n_ky"]), 1), ("Tổng ròng", 2), ("Mua", 2), ("Bán", 2),
              ("Khớp lệnh ròng", 2), ("Thoả thuận ròng", 2)] + ([("Sở hữu", 2)] if label == "nn" else []),
             [("", 1)] + [("KL", 1), ("GT (triệu)", 1)] * 5 + ([("% NN", 1), ("Room còn (cp)", 1)]
                                                              if label == "nn" else [])]
    rows = []
    for r in s["rows"]:
        row = [dmy(r["ky"]), colored(num(r["rong_kl"]), r["rong_kl"]), colored(mil(r["rong_gt"]), r["rong_gt"]),
               num(r["mua_kl"]), mil(r["mua_gt"]), num(r["ban_kl"]), mil(r["ban_gt"]),
               colored(num(r["khop_rong_kl"]), r["khop_rong_kl"]), colored(mil(r["khop_rong_gt"]), r["khop_rong_gt"]),
               colored(num(r["tt_rong_kl"]), r["tt_rong_kl"]), colored(mil(r["tt_rong_gt"]), r["tt_rong_gt"])]
        if label == "nn":
            row += [pct(r["so_huu_pct"]), num(r["room_con"])]
        rows.append(row)
    return heads, rows


def _stat_cc(s, tf):
    heads = [[("%s %d" % (TF_NAME[tf], s["n_ky"]), 1), ("KL chưa khớp (cp)", 2), ("Số lệnh đặt", 2),
              ("KL đặt (cp)", 2), ("KLTB 1 lệnh", 2), ("Chênh lệch KL đặt mua - bán", 1)],
             [("", 1)] + [("Mua", 1), ("Bán", 1)] * 4 + [("", 1)]]
    rows = [[dmy(r["ky"]), num(r["chua_khop_mua"]), num(r["chua_khop_ban"]), num(r["lenh_mua"]), num(r["lenh_ban"]),
             num(r["kl_dat_mua"]), num(r["kl_dat_ban"]), num(r["kltb_mua"]), num(r["kltb_ban"]),
             colored(num(r["chenh_lech"]), r["chenh_lech"])] for r in s["rows"]]
    return heads, rows


def _insider(Q, tk):
    ins = Q.insider(tk)
    if not ins["ok"]:
        return [empty("chưa có insider-transaction cho " + tk)]
    heads = [[("Tổ chức / người GD", 1), ("Chức vụ", 1), ("Loại GD", 1), ("Số lượng (cp)", 4), ("Ngày", 3),
              ("Trạng thái", 1)],
             [("", 1), ("", 1), ("", 1), ("Đăng ký", 1), ("Trước GD", 1), ("Thực hiện", 1), ("Sau GD", 1),
              ("Thông báo", 1), ("Bắt đầu", 1), ("Kết thúc", 1), ("", 1)]]
    rows = [[r["ten"] or DASH, r["chuc_vu"] or DASH,
             h("span", {"color": C.forest if r["loai"] == "Mua" else (C.vermillion if r["loai"] == "Bán" else C.inkD)},
               r["loai"] or DASH),
             num(r["dang_ky"]), num(r["truoc"]), colored(num(r["thuc_hien"]), r["thuc_hien"]), num(r["sau"]),
             dmy(r["thong_bao"]), dmy(r["bat_dau"]), dmy(r["ket_thuc"]), r["trang_thai"] or DASH]
            for r in ins["rows"]]
    return [table(heads, rows, left=3),
            src_line("Nguồn: vc_lk insider-transaction · %d giao dịch (hiện %d mới nhất) · lấy %s" % (
                ins["n"], len(ins["rows"]), dmy((ins.get("lay_luc") or "")[:10])), asof=ins.get("toi"))]


def thongke(Q, tk):
    kids = [bar(K_ST, KINDS, "vciq.st"), bar(K_TF, TFS, "vciq.tf")]
    for kid, _lbl in KINDS:
        if kid == "nb":
            kids.append(h("div", None, *_insider(Q, tk), if_={K_ST: "nb"}, key="vciq.nb"))
            continue
        for tf, _ in TFS:
            s = Q.stats(tk, kid, tf)
            if not s["ok"]:
                body = [empty(s.get("ly_do") or "không có dữ liệu")]
            else:
                heads, rows = (_stat_gia(s, tf) if kid == "gia" else _stat_cc(s, tf) if kid == "cc"
                               else _stat_flow(s, tf, kid))
                miss = kid == "cc" or kid == "nn"
                note = (" · cột Cung cầu/NN tách khớp-thoả thuận chỉ có từ lượt nạp 05/10/2026; kỳ có phiên thiếu số "
                        "ghi \"-\" (không cộng thiếu)") if miss else ""
                body = [table(heads, rows), src_line(
                    "Nguồn: vc_lk %s · %s %d kỳ từ %s tới %s (hiện %d kỳ gần nhất; W/M/Q/Y cộng từ phiên ngày, nhãn "
                    "= phiên đầu kỳ)%s" % (s["ep"], TF_NAME[tf].lower(), s["n_ky"], dmy(s["tu"]), dmy(s["toi"]),
                                            len(rows), note), asof=s["toi"])]
            kids.append(h("div", None, *body, if_={K_ST: kid, K_TF: tf}, key="vciq.%s.%s" % (kid, tf)))
    return Card(*kids)


# ── Tài chính ──────────────────────────────────────────────────────────────

FS_TABS = (("fs-income", "Kết quả kinh doanh"), ("fs-balance", "Cân đối kế toán"), ("fs-cashflow", "Lưu chuyển tiền tệ"),
           ("fs-note", "Thuyết minh"), ("ratio", "Chỉ số"))
PERS = (("year", "Năm"), ("quarter", "Quý"))


def _fs_table(f):
    heads = [[("Chỉ tiêu (tỷ đồng)", 1)] + [(k, 1) for k in f["ky"]]]
    rows = []
    for lvl, name, vals in f["rows"]:
        lbl = h("span", {"paddingLeft": (lvl - 1) * 14, "fontWeight": 600 if lvl == 1 else 400,
                         "color": C.ink if lvl == 1 else C.inkD}, name)
        rows.append([lbl] + [colored(ty(v), v) if v is not None and v < 0 else ty(v) for v in vals])
    return table(heads, rows)


def taichinh(Q, tk):
    kids = [bar(K_FS, FS_TABS, "vciq.fs"), bar(K_PER, PERS, "vciq.per")]
    for ep, _lbl in FS_TABS:
        for per, pname in PERS:
            if ep == "fs-note" and per == "quarter":     # thuyết minh ~150 dòng: chỉ theo năm cho nhẹ
                kids.append(h("div", None, empty("thuyết minh chỉ hiện theo năm (cache có đủ theo quý)"),
                              if_={K_FS: ep, K_PER: per}, key="vciq.fs.note.q"))
                continue
            if ep == "ratio":
                r = Q.ratios(tk, 8)
                if not r["ok"]:
                    body = [empty("chưa có statistics-financial cho " + tk)]
                else:
                    heads = [[("Chỉ số (TTM theo quý)", 1)] + [(k, 1) for k in r["ky"]]]
                    rows = [[name] + [DASH if v is None else (to_fixed(v * 100, 1) + "%" if u == "%" else
                                                              to_fixed(v, 1) if u == "n" else to_fixed(v, 2))
                                      for v in vals] for name, u, vals in r["rows"]]
                    body = [table(heads, rows), src_line("Nguồn: vc_lk statistics-financial (Vietcap tính TTM) · lấy "
                                                         + dmy(r.get("t_lay")), asof=r.get("t_lay"))]
                kids.append(h("div", None, *body, if_={K_FS: ep}, key="vciq.fs.ratio." + per))
                continue
            f = Q.fin(tk, ep, per, 6 if per == "year" else 8)
            if not f.get("ok"):
                body = [empty(f.get("ly_do") or "không có số")]
            else:
                body = [_fs_table(f), src_line(
                    "Nguồn: vc_lk %s + fs-metrics (tên dòng của Vietcap) · %s · BCTC công bố mới nhất %s · lấy %s" % (
                        ep, pname.lower(), dmy(f["cong_bo"]), dmy(f.get("t_lay"))), asof=f["cong_bo"])]
            kids.append(h("div", None, *body, if_={K_FS: ep, K_PER: per}, key="vciq.fs.%s.%s" % (ep, per)))
    return Card(*kids)


# ── Tin tức & sự kiện ──────────────────────────────────────────────────────

EV_TABS = (("news", "Tin tức"), ("dividend", "Trả cổ tức - Phát hành thêm"),
           ("shareholder", "GD cổ đông lớn & cổ đông nội bộ"), ("agm", "Đại hội cổ đông"), ("other", "Sự kiện khác"))


def _news(Q, tk):
    n = Q.news(tk, 60)
    if not n["ok"]:
        return [empty("chưa có tin Vietcap IQ cho " + tk)]
    rows = []
    for x in n["rows"]:
        links = [h("a", {"color": C.ink2, "marginLeft": 8, "fontSize": 9.5}, "PDF %d" % (i + 1), href=u)
                 for i, u in enumerate(x["tep"][:3])]
        rows.append([dmy(x["ngay"][:10]) + " " + x["ngay"][11:16],
                     h("span", {"color": C.ink if x["cbtt"] else C.inkD}, x["tieu_de"] or DASH, *links),
                     h("span", {"color": C.gold if x["cbtt"] else C.inkM, "fontSize": 9},
                       "CBTT" if x["cbtt"] else "tin")])
    return [table([[("Ngày", 1), ("Tiêu đề", 1), ("Loại", 1)]], rows, left=2),
            src_line("Nguồn: vc_lk news · %d tin từ %s tới %s (hiện 60 mới nhất) · %d tin CBTT của doanh nghiệp · "
                     "%d tin đã lấy chi tiết, %d link tệp đính kèm (PDF gốc trên cmsv6.fiingroup.vn)" % (
                         n["n"], dmy(n["dau"]), dmy(n["rows"][0]["ngay"][:10]), n["n_cbtt"], n["n_chi_tiet"],
                         n["n_tep"]), asof=n.get("toi"))]


def _events(e, gid):
    g = e["groups"][gid]
    if not g["n"]:
        return [empty("không có sự kiện nhóm này trong vc_lk " + e["nguon"])]
    if gid == "dividend":
        heads = [[("Công bố", 1), ("GDKHQ", 1), ("Sự kiện", 1), ("Tỷ lệ", 1), ("Tiền/cp", 1), ("Thanh toán", 1)]]
        rows = [[dmy(r["cong_bo"]), dmy(r["thuc_hien"]), r["ten"] or DASH,
                 pct(r["ty_le"], 2) if r["ty_le"] else DASH, num(r["tien"]) if r["tien"] else DASH,
                 dmy(r["thanh_toan"])] for r in g["rows"]]
    elif gid == "shareholder":
        heads = [[("Công bố", 1), ("Bắt đầu", 1), ("Kết thúc", 1), ("Sự kiện", 1), ("Loại", 1)]]
        rows = [[dmy(r["cong_bo"]), dmy(r["thuc_hien"]), dmy(r["ket_thuc"]), r["ten"] or DASH,
                 h("span", {"color": C.forest if r["loai"] == "Mua" else C.vermillion}, r["loai"] or DASH)]
                for r in g["rows"]]
    else:
        heads = [[("Công bố", 1), ("Ngày thực hiện", 1), ("Mã", 1), ("Sự kiện", 1)]]
        rows = [[dmy(r["cong_bo"]), dmy(r["thuc_hien"]), r["ma_sk"], r["ten"] or DASH] for r in g["rows"]]
    return [table(heads, rows, left=4 if gid == "shareholder" else 3),
            src_line("Nguồn: vc_lk %s · %d sự kiện nhóm này (hiện %d mới nhất)" % (e["nguon"], g["n"], len(rows)),
                     asof=e.get("toi"))]


def tinsk(Q, tk):
    e = Q.events(tk)
    kids = [bar(K_EV, EV_TABS, "vciq.ev"), h("div", None, *_news(Q, tk), if_={K_EV: "news"}, key="vciq.ev.news")]
    for gid, _ in EV_TABS[1:]:
        body = _events(e, gid) if e["ok"] else [empty("chưa có events-all/events-v2 cho " + tk)]
        kids.append(h("div", None, *body, if_={K_EV: gid}, key="vciq.ev." + gid))
    return Card(*kids)


# ── Cổ đông ────────────────────────────────────────────────────────────────


def codong(Q, tk):
    hd = Q.holders(tk)
    if not hd["ok"]:
        return Card(empty("chưa có shareholder cho " + tk))
    st = hd["co_cau"] or {}
    tot = st.get("totalShares")
    stats = h("div", {"display": "flex", "gap": 12, "flexWrap": "wrap", "marginBottom": 14},
              *[Stat(lbl, [pct(st.get(k)), tier("T2")], color=col) for lbl, k, col in (
                  ("NHÀ NƯỚC", "statePercentage", C.ink2), ("NƯỚC NGOÀI", "foreignPercentage", C.gold),
                  ("HĐQT", "bodPercentage", C.ochre), ("TỔ CHỨC", "institutionPercentage", C.forest),
                  ("KHÁC", "otherPercentage", C.inkD))],
              Stat("TỔNG CP", [num(tot), tier("T2")], color=C.ink))
    rows = [[r["ten"] or DASH, r["chuc_vu"] or DASH, r["loai"] or DASH, num(r["sl"]), pct(r["pct"]), dmy(r["ngay"])]
            for r in hd["rows"]]
    rel = [[x["ten"] or DASH, x["ma"] or DASH, pct(x["pct"]), "công ty con"] for x in hd["con"]] + \
          [[x["ten"] or DASH, x["ma"] or DASH, pct(x["pct"]), "liên kết"] for x in hd["lien_ket"]]
    kids = [stats, table([[("Cổ đông", 1), ("Chức vụ", 1), ("Loại", 1), ("Số cp", 1), ("Tỷ lệ", 1),
                           ("Cập nhật", 1)]], rows, left=3),
            src_line("Nguồn: vc_lk shareholder + shareholder-structure (ảnh chụp vendor, %% tại ngày công bố từng dòng)"
                     " · %d cổ đông" % len(rows), asof=hd.get("toi"))]
    if rel:
        kids += [h("div", {"fontSize": 9, "letterSpacing": ".2em", "color": C.inkM, "fontFamily": F_MONO,
                           "margin": "16px 0 6px"}, "CÔNG TY CON & LIÊN KẾT"),
                 table([[("Doanh nghiệp", 1), ("Mã", 1), ("Sở hữu", 1), ("Quan hệ", 1)]], rel, left=2),
                 src_line("Nguồn: vc_lk relationship (ảnh chụp vendor)", asof=None)]
    return Card(*kids)


# ── Báo cáo phân tích · Kỹ thuật · Quỹ ─────────────────────────────────────


def baocao(Q, tk, cov):
    a = Q.analysis(tk)
    kids = []
    if cov:
        f = lambda d, k: (d or {}).get(k)  # noqa: E731
        kids.append(h("div", {"display": "flex", "gap": 12, "flexWrap": "wrap", "marginBottom": 14}, *[
            Stat("KHUYẾN NGHỊ VIETCAP", [cov.get("rating") or DASH, tier("T3")], color=C.gold),
            Stat("GIÁ MỤC TIÊU", [px(cov.get("targetPrice")), tier("T3")], color=C.gold),
            Stat("TSR DỰ PHÓNG", [pct(cov.get("projectedTsrPercentage"), 1), tier("T3")], color=C.gold),
            Stat("P/E 2026F · 2027F", [to_fixed(f(cov.get("pe"), "2026F") or 0, 1) + " · " +
                                       to_fixed(f(cov.get("pe"), "2027F") or 0, 1), tier("T3")], color=C.gold),
            Stat("ROE 2026F", [pct(f(cov.get("roe"), "2026F"), 1), tier("T3")], color=C.gold)]))
    if not a["ok"]:
        kids.append(empty("chưa có danh sách báo cáo phân tích Vietcap cho " + tk))
    else:
        kids += [table([[("Ngày", 1), ("Báo cáo (Vietcap)", 1), ("Nhóm", 1)]],
                       [[dmy(r["ngay"]), r["ten"], r["loai"] or DASH] for r in a["rows"]], left=2),
                 src_line("Nguồn: vietcap.com.vn cms-service (danh sách báo cáo của Vietcap) · %d báo cáo, hiện %d mới "
                          "nhất · quan điểm sell-side, không phải khuyến nghị của trang" % (a["n"], len(a["rows"])),
                          tag="T3", asof=a["rows"][0]["ngay"] if a["rows"] else None)]
    return Card(*kids)


RATING_VI = {"STRONG_BUY": "MUA MẠNH", "BUY": "MUA", "VERY_GOOD": "MUA MẠNH", "GOOD": "MUA", "NEUTRAL": "TRUNG TÍNH",
             "SELL": "BÁN", "BAD": "BÁN", "VERY_BAD": "BÁN MẠNH", "STRONG_SELL": "BÁN MẠNH"}


def kythuat(Q, tk):
    t = Q.technical(tk)
    if not t["ok"]:
        return Card(empty("chưa có technical/ONE_DAY cho " + tk))

    def g(lbl, d):
        v = d.get("values") or {}
        r = RATING_VI.get(d.get("rating"), d.get("rating") or DASH)
        col = C.forest if "MUA" in r else (C.vermillion if "BÁN" in r else C.ochre)
        return Stat(lbl, [r, tier("T2", t.get("t_lay"))], sub="mua %s · trung tính %s · bán %s" % (
            v.get("BUY", 0), v.get("NEUTRAL", 0), v.get("SELL", 0)), color=col)
    rows = [[x.get("name"), px(x.get("value")) if str(x.get("name", "")).startswith(("sma", "ema", "vwma", "hma"))
             else to_fixed(x.get("value") or 0, 2), RATING_VI.get(x.get("rating"), x.get("rating") or DASH)]
            for x in t["ma_rows"] + t["osc_rows"]]
    pv = t["pivot"]
    piv = [[k, px(pv.get(k))] for k in ("resistance3", "resistance2", "resistance1", "pivotPoint", "support1",
                                         "support2", "support3") if pv.get(k) is not None]
    return Card(h("div", {"display": "flex", "gap": 12, "flexWrap": "wrap", "marginBottom": 14},
                  g("TỔNG HỢP", t["tong"]), g("ĐƯỜNG TRUNG BÌNH", t["ma"]), g("DAO ĐỘNG", t["osc"])),
                h("div", {"display": "grid", "gridTemplateColumns": "2fr 1fr", "gap": 16},
                  table([[("Chỉ báo", 1), ("Giá trị", 1), ("Tín hiệu", 1)]], rows),
                  table([[("Pivot (khung ngày)", 1), ("Giá", 1)]], piv)),
                src_line("Nguồn: vc_lk technical/ONE_DAY (Vietcap tự tính, ảnh chụp lấy %s, giá %s) · chỉ báo kỹ thuật "
                         "của vendor, không phải tín hiệu của trang" % (dmy(t.get("t_lay")), px(t.get("gia"))),
                         asof=t.get("t_lay")))
