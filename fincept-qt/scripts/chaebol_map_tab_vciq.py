#!/usr/bin/env python3
"""
chaebol_map_tab_vciq: tab thứ 19 "★ VIETCAP IQ · 110 MÃ" (CHỈ mode live; mode v21 vẫn đúng 18 tab của trang gốc).

Yêu cầu người dùng 05/10/2026: thay dữ liệu CapIQ/FiinTrade/Simplize đã cũ bằng Vietcap IQ, lấy dài nhất (giá, tin,
cổ đông, sự kiện, BCTC) cho VN30 + mọi mã trong Chaebol map. Tab dựng lại cấu trúc trang /iq/company của Vietcap:
bộ chọn mã → đầu trang mã → 8 tab con. Mỗi mã là một nhánh lười "vciq/<MÃ>". Đầu tab có bảng audit độ phủ cache.
Không chấm lại stance (CỔNG DỪNG); số của vendor mang nhãn T2, khuyến nghị/giá mục tiêu Vietcap mang T3.
"""
from __future__ import annotations

import chaebol_map_data_vciq as Q
import chaebol_map_tab_codong as CD
import chaebol_map_tab_dangnhap as TDN
import chaebol_map_tab_vciq_parts as P
from chaebol_map_dom import C, F_DISPLAY, F_MONO, can_data, h, tier, to_fixed, upd_mark
from chaebol_map_shell import Card, Section, Stat

K_TK = "vciq.tk"
SUBS = (("tongquan", "Tổng quan"), ("taichinh", "Tài chính"), ("thongke", "Thống kê"), ("codong", "Cổ đông"),
        ("tinsk", "Tin tức & Sự kiện"), ("baocao", "Báo cáo phân tích"), ("kythuat", "Kỹ thuật"), ("quy", "Quỹ"))
STATES = ((K_TK, None), (P.K_SUB, "tongquan"), (P.K_ST, "gia"), (P.K_TF, "D"), (P.K_FS, "fs-income"),
          (P.K_PER, "year"), (P.K_EV, "news"))
OPTS = {P.K_SUB: [s for s, _ in SUBS], P.K_ST: [k for k, _ in P.KINDS], P.K_TF: [t for t, _ in P.TFS],
        P.K_FS: [f for f, _ in P.FS_TABS], P.K_PER: [p for p, _ in P.PERS], P.K_EV: [e for e, _ in P.EV_TABS]}


# ── đầu tab ────────────────────────────────────────────────────────────────


def audit_card(cov, today):
    rows = []
    for x in cov:
        full = x["co"] == x["tong"]
        thieu = ", ".join(x["thieu"][:12]) + (" … +%d" % (len(x["thieu"]) - 12) if len(x["thieu"]) > 12 else "")
        rows.append([x["ten"], x["ep"], P.colored("%d/%d" % (x["co"], x["tong"]), 1 if full else -1),
                     P.dmy(x["toi"]) if x["toi"] else P.DASH,
                     (x["lay_moi"] or P.DASH).replace("T", " "),
                     h("span", {"color": C.inkD, "fontSize": 9.5}, thieu or "đủ")])
    return Card(P.table([[("Khối dữ liệu", 1), ("Endpoint", 1), ("Số mã có", 1), ("Dữ liệu tới", 1),
                          ("Lấy gần nhất", 1), ("Mã còn thiếu", 1)]], rows, left=2),
                P.src_line("Audit tự động lúc dựng (%s): đếm tệp state/vc_lk/<MÃ>/<endpoint>.json trên vũ trụ %d mã. "
                           "Fetcher duy nhất: fincept_bridge/vc_lk_fetch.py (1 luồng, 10 s/request, không đăng nhập). "
                           "\"LN KD dự phóng\" và Quỹ chỉ mở khi đăng nhập Vietcap." % (P.dmy(today), cov[0]["tong"])),
                accent=C.ink2, key="vciq.audit")


def picker(tks, vn30):
    def btn(tk):
        return h("button", P.S_BTN, tk, on={"set": {K_TK: tk}}, var=[{"if": {K_TK: tk}, "s": P.S_ON}],
                 key="vciq.btn." + tk)

    def row(lbl, items):
        return h("div", {**P.S_BAR, "marginBottom": 6},
                 h("span", {"fontSize": 9, "letterSpacing": ".2em", "color": C.inkM, "fontFamily": F_MONO,
                            "marginRight": 8, "minWidth": 150}, lbl), *[btn(t) for t in items])
    inn = [t for t in tks if t in vn30]
    out = [t for t in tks if t not in vn30]
    return h("div", {"padding": "10px 12px", "background": C.parch, "borderRadius": 3, "marginBottom": 14},
             row("VN30 HIỆN HÀNH (%d)" % len(inn), inn), row("NGOÀI VN30 (%d)" % len(out), out), key="vciq.picker")


# ── một mã ─────────────────────────────────────────────────────────────────


def head(tk, pf, cov_row):
    if not pf["ok"]:
        return Card(P.empty("chưa có cache Vietcap IQ cho " + tk + " (đang chờ lượt vc_lk_fetch)"))
    vh, vh_d = pf["von_hoa"]
    sh, sh_d = pf["cp_luu_hanh"]
    nn, nn_d = pf["nn_so_huu"]
    chg = pf["doi_pct"]
    title = h("div", {"display": "flex", "alignItems": "baseline", "gap": 14, "flexWrap": "wrap", "marginBottom": 12},
              h("span", {"fontFamily": F_DISPLAY, "fontSize": 30, "fontWeight": 600, "color": C.ink}, tk),
              h("span", {"fontFamily": P.F_SERIF, "fontSize": 15, "color": C.ink}, pf["ten"] or P.DASH),
              h("span", {"fontFamily": F_MONO, "fontSize": 10, "color": C.inkD, "letterSpacing": ".08em"},
                " · ".join([x for x in [pf["san"], *pf["nganh"][1:3]] if x])),
              h("span", {"marginLeft": "auto", "fontFamily": F_MONO, "fontSize": 22, "fontWeight": 600,
                         "color": P.sgn_col(chg)}, P.px(pf["gia"]),
                h("span", {"fontSize": 12, "marginLeft": 8}, (("+" if (chg or 0) > 0 else "") + to_fixed(chg, 2) + "%")
                  if chg is not None else ""), tier("T2", pf["gia_ngay"])))
    stats = [Stat("VỐN HOÁ (TỶ)", [P.ty(vh), tier("T2", vh_d)]), Stat("CP LƯU HÀNH", [P.num(sh), tier("T2", sh_d)]),
             Stat("FREE FLOAT", [P.pct(pf["free_float"], 1), tier("T2", pf["t_lay"])]),
             Stat("NN SỞ HỮU / ROOM", [P.pct(nn, 1) + " / " + P.pct(pf["room_nn"], 0), tier("T2", nn_d)]),
             Stat("KL TB 1 THÁNG", [P.num(pf["kl_tb_1t"]), tier("T2", pf["t_lay"])]),
             Stat("CAO / THẤP 52T", [P.px(pf["cao_1y"]) + " / " + P.px(pf["thap_1y"]), tier("T2", pf["t_lay"])])]
    if pf.get("rating"):
        stats.append(Stat("VIETCAP: " + str(pf["rating"]), [P.px(pf["tp"]), tier("T3", None)],
                          sub="TP · upside %s · %s" % (P.pct(pf["upside"], 1), pf.get("analyst") or ""),
                          color=C.gold))
    return Card(title, h("div", {"display": "flex", "gap": 12, "flexWrap": "wrap"}, *stats), accent=C.gold)


def sub_bar():
    return h("div", {**P.S_BAR, "padding": "8px 10px", "background": C.parch, "borderRadius": 3, "margin": "14px 0"},
             *[h("button", P.S_BTN, lbl, on={"set": {P.K_SUB: sid}}, var=[{"if": {P.K_SUB: sid}, "s": P.S_ON}],
                 key="vciq.sub." + sid) for sid, lbl in SUBS])


def price_chart(tk):
    s = Q.price_series(tk)
    if not s["ok"]:
        return P.empty("chưa có price-history")
    W, H, L, R, T, B = 1000, 230, 52, 12, 14, 26
    xs = [p[1] for p in s["pts"]]
    lo, hi = min(xs), max(xs)
    hi = hi if hi > lo else lo + 1
    n = len(s["pts"])
    X = lambda i: L + (W - L - R) * i / max(1, n - 1)  # noqa: E731
    Y = lambda v: T + (H - T - B) * (1 - (v - lo) / (hi - lo))  # noqa: E731
    d = "M" + " L".join("%.1f %.1f" % (X(i), Y(p[1])) for i, p in enumerate(s["pts"]))
    kids = [h("path", None, a={"d": d + " L%.1f %d L%d %d Z" % (X(n - 1), H - B, L, H - B), "fill": C.gold,
                               "fillOpacity": 0.08, "stroke": "none"}),
            h("path", None, a={"d": d, "fill": "none", "stroke": C.gold, "strokeWidth": 1.4})]
    for v in (lo, (lo + hi) / 2, hi):
        kids.append(h("text", None, P.px(v), a={"x": L - 6, "y": Y(v) + 3, "textAnchor": "end", "fontSize": 9,
                                                 "fill": C.inkD, "fontFamily": "IBM Plex Mono"}))
        kids.append(h("line", None, a={"x1": L, "x2": W - R, "y1": Y(v), "y2": Y(v), "stroke": C.rule,
                                       "strokeWidth": 0.6}))
    last_y = None
    for i, (dd, _) in enumerate(s["pts"]):
        y = dd[:4]
        if y != last_y and (int(y) % 2 == 0 or n < 300):
            kids.append(h("text", None, y, a={"x": X(i), "y": H - 8, "textAnchor": "middle", "fontSize": 9,
                                               "fill": C.inkM, "fontFamily": "IBM Plex Mono"}))
        last_y = y
    return h("div", None, h("svg", {"display": "block", "background": C.bg, "borderRadius": 3}, *kids,
                            a={"viewBox": "0 0 %d %d" % (W, H), "width": "100%", "height": "auto"}),
             P.src_line("Giá đóng cửa ĐÃ ĐIỀU CHỈNH quyền (nghìn đồng) toàn chuỗi %s → %s, %d phiên (vc_lk price-history"
                        " closePriceAdjusted; vẽ thưa %d điểm)" % (P.dmy(s["tu"]), P.dmy(s["toi"]), s["n"], n),
                        asof=s["toi"]))


def tongquan(tk, pf, cov):
    e = Q.earnings(tk)
    kids = [P.Card(price_chart(tk))]
    lnkd = TDN.loi_nhuan_kd(tk)            # phiên đăng nhập (state/vc_iq_dangnhap) thắng bản không đăng nhập
    if lnkd is not None:
        kids += [lnkd, TDN.kqkd_so_du_phong(tk)]
    elif e["ok"]:
        heads = [[("Lợi nhuận KD", 1)] + [(c, 1) for c in e["cot"]]]
        rows = [[lbl] + [P.ty(v) if u == "ty" else (P.pct(v, 1) if u == "%" else
                                                     P.num(v, 2) if u == "x" else P.num(v)) for v in vals]
                for lbl, u, vals in e["rows"]]
        kids.append(Card(P.table(heads, rows), P.src_line("Nguồn: vc_lk financial-data · cột F là dự phóng của Vietcap",
                                                          tag="T3", asof=e.get("t_lay"))))
    else:
        a = Q.annual_from_fs(tk)
        body = [h("p", {"fontSize": 10.5, "color": C.inkD, "margin": "0 0 8px", "fontFamily": F_MONO},
                  "Khối Lợi nhuận KD 2023 → 2027F của Vietcap ",
                  can_data("bị khoá khi không đăng nhập Vietcap" if e.get("khoa_dang_nhap") else "chưa lấy"),
                  ". Thay tạm bằng số năm thực tế từ BCTC:")]
        if a["ok"]:
            heads = [[("Năm (tỷ đồng)", 1)] + [(k, 1) for k in a["ky"]]]
            rows = []
            for lbl, vals, g in a["rows"]:
                rows.append([lbl] + [P.ty(v) for v in vals])
                rows.append([h("span", {"color": C.inkD}, "  tăng trưởng")] +
                            [P.colored(P.pct(x, 1, 1), x) for x in g])
            body += [P.table(heads, rows), P.src_line("Nguồn: vc_lk fs-income (năm, hợp nhất) · tăng trưởng tự tính",
                                                      asof=a.get("t_lay"))]
        kids.append(Card(*body))
    v = Q.valuation(tk)
    if v["ok"]:
        kids.append(Card(P.table([[("Định giá cuối năm", 1)] + [(str(y), 1) for y in v["nam"]]],
                                 [["P/E"] + [P.num(x, 1) for x in v["pe"]], ["P/B"] + [P.num(x, 2) for x in v["pb"]]]),
                         P.src_line("Nguồn: vc_lk valuation (Vietcap, YEAR_END)", asof=v.get("t_lay"))))
    pr = Q.peers(tk)
    if pr["ok"]:
        kids.append(Card(P.table([[("Cùng ngành (Vietcap coverage)", 1), ("Lợi suất cổ phiếu", 1)]],
                                 [[x.get("ticker"), P.colored(P.pct(x.get("stockReturn"), 1), x.get("stockReturn"))]
                                  for x in pr["rows"]]),
                         P.src_line("Nguồn: vc_lk peers (stock-return-coverage-peers)", asof=pr.get("t_lay"))))
    if pf.get("profile"):
        import html
        import re
        txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", pf["profile"]))).strip()
        kids.append(Card(h("p", {"fontSize": 12, "lineHeight": 1.7, "color": C.inkD, "margin": 0,
                                 "fontFamily": P.F_SERIF}, txt[:1200]), P.src_line("Hồ sơ doanh nghiệp: vc_lk details")))
    return h("div", {"display": "grid", "gap": 14}, *kids)


def codong_link(tk):
    """Sub Cổ đông → tab codong v2 đúng mã, mở sub 06 (key vciq.cd2.<MÃ>, codong_v2_spec §8.3). vciq giữ danh sách thô
    và chart riêng."""
    return h("div", {"marginBottom": 10},
             CD.link_button(tk, "→ Cấu trúc cổ đông v2 của %s: 06 · Cổ đông lớn & chuỗi sở hữu" % tk, "vciq.cd2." + tk,
                            "capitaliq"))


def ticker_tree(tk, cov_row, cd2=False):
    pf = Q.profile(tk)
    parts = {"tongquan": lambda: tongquan(tk, pf, cov_row), "taichinh": lambda: P.taichinh(Q, tk),
             "thongke": lambda: P.thongke(Q, tk), "codong": lambda: P.codong(Q, tk), "tinsk": lambda: P.tinsk(Q, tk),
             "baocao": lambda: P.baocao(Q, tk, cov_row), "kythuat": lambda: P.kythuat(Q, tk),
             "quy": lambda: TDN.quy(tk)}
    kids = [head(tk, pf, cov_row), sub_bar()]
    for sid, _ in SUBS:
        link = codong_link(tk) if (cd2 and sid == "codong") else None
        kids.append(h("div", None, link, parts[sid](), if_={P.K_SUB: sid}, key="vciq.%s.%s" % (tk, sid)))
    return h("div", None, *kids, key="vciq.tk." + tk)


def build_vciq(ctx):
    if not ctx.live:
        raise RuntimeError("tab vciq chỉ có ở mode live")
    D = ctx.data
    vn = getattr(D, "basket", None)
    b = vn("VN30") if callable(vn) else None
    vn30 = list(getattr(b, "value", None) or [])
    tks = Q.universe(ctx.v21, vn30)
    cov = Q.coverage(tks)
    today = ctx.today.isoformat()
    inc, holders, cd2 = {}, [], CD.v2_universe(ctx)
    for tk in tks:
        inc["vciq/" + tk] = ticker_tree(tk, Q.coverage_row(tk), tk in cd2)
        holders.append(h("div", None, if_={K_TK: tk}, inc="vciq/" + tk))
    default_tk = "VIC" if "VIC" in tks else tks[0]
    root = h("div", None,
             Section(["★ VIETCAP IQ · hồ sơ đầy đủ %d mã (VN30 + Chaebol map)" % len(tks), upd_mark()],
                     audit_card(cov, today), accent=C.ink2,
                     sub="Nguồn: Vietcap IQ qua vc_lk_fetch · thay CapIQ Q4/25, FiinTrade ≤08/05, Simplize 10/05"),
             picker(tks, vn30), *holders, key="vciq.root")
    states = [{"key": k, "default": (default_tk if k == K_TK else d), "options": (tks if k == K_TK else OPTS[k])}
              for k, d in STATES]
    csv = [{"ma": tk, "vn30": "có" if tk in vn30 else "", **{x["ep"]: ("có" if tk not in x["thieu"] else "thiếu")
                                                              for x in cov}} for tk in tks]
    return {"root": root, "states": states, "inc": inc, "csv": csv}
