#!/usr/bin/env python3
"""
chaebol_map_tab_codong_v2_book: Sổ bằng chứng chủ thể (sub 07), khối Cổ đông lớn & chuỗi sở hữu (sub 06) và Bảng tổng
109 mã (inc codong/_tong) của tab codong v2, mode live (P4 render).

Hợp đồng: chaebol_map_spec/codong_v2_spec.md §7.3 (capitaliq), §7.4 (Sổ bằng chứng: 9 dòng câu hỏi, KHÔNG cột kết luận,
dòng vàng để mở), §7.5 (bảng tổng: chỉ số, không nhãn; bậc ở tiêu đề cột, ô lệch bậc mới gắn nhãn tại ô). Mọi số qua
TkData (P1/P2/lớp dữ liệu cũ); chữ nguyên văn của nguồn bọc nút cd2.trich.*. Không kết luận, không hô mua/bán.
"""
from __future__ import annotations

from collections import Counter

from chaebol_map_data_codong2 import FFT_MISS, FFT_MISS_TEXT
import chaebol_map_tab_dangnhap as TDN
from chaebol_map_dom import C, F_MONO, can_data, h, sign_fixed, to_fixed, v21_mark
import chaebol_map_tab_codong_v2_parts as PT
from chaebol_map_tab_codong_v2_parts import (E, K_SUB, K_TK, T2, U, cdn, cv, dmy, dmy2, dmy_hm, env_ok, fb,
                                             fk, fm, fn, fp, fpp, fps, line, note, ok, q, table, tag, top_box, trich,
                                             trim, tv)

S_BAR = {"display": "flex", "height": 10, "background": C.parch, "borderRadius": 2, "overflow": "hidden",
         "margin": "4px 0"}
S_GRID3 = {"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": 10, "margin": "6px 0 10px"}
S_LAD = {"fontSize": 9.5, "color": C.inkD, "fontFamily": F_MONO, "lineHeight": 1.5}
S_EVQ = {"padding": "6px 8px", "color": C.ink, "fontWeight": 600, "verticalAlign": "top", "width": "16%"}
S_EV = {"padding": "6px 8px", "color": C.inkD, "verticalAlign": "top", "lineHeight": 1.65}
S_ROWB = {"display": "block", "width": "100%", "textAlign": "left", "background": "transparent", "border": "none",
          "padding": "1px 0", "cursor": "pointer", "whiteSpace": "pre", "fontFamily": F_MONO, "fontSize": 10,
          "color": C.ink, "lineHeight": 1.55}
S_HEADR = {**S_ROWB, "color": C.inkD, "cursor": "default", "fontWeight": 600, "borderBottom": "1px solid " + C.rule}
COLORS1 = {"state": C.vermillion, "foreign": C.ink2, "other": C.inkM}
COLORS2 = {"bod": C.gold, "institution": C.forest}
PAIR_VI = {"noi_nhom": "chuyển giao nội nhóm (không qua thị trường)", "cap_khop": "cặp khớp"}
STATUS_VI = {"da_xong": "đã thực hiện", "dang_ky": "đăng ký", "khong_thuc_hien": "không thực hiện được", "khac": "khác"}
GOLD_Q = "Câu hỏi vàng: mục đích kéo giá có lớn hơn chi phí kéo không? Để mở (CỔNG v1.7 DỪNG, không kết luận)"


# ── 06 (a) cơ cấu sở hữu: hai thanh ─────────────────────────────────────────


def _bar(items, colors):
    segs = [h("div", {"width": to_fixed(max(0.0, it["pct"].value), 2) + "%", "background": colors.get(it["k"], C.inkM)})
            for it in items if ok(it.get("pct"))]
    return h("div", S_BAR, *segs)


def structure_block(td):
    sb = td.structure
    if not env_ok(sb):
        return line("Cơ cấu sở hữu: ", cdn(sb))
    b1, b2 = sb.get("bar1") or [], sb.get("bar2") or []
    lab1 = [x for it in b1 for x in (it["label"] + " ", *tv(it.get("pct"), fp, False), " · ")][:-1]
    kids = [PT.cap("(a) CƠ CẤU SỞ HỮU: THANH 1 CỘNG THÀNH 100%"), _bar(b1, COLORS1),
            line(*lab1, " (tổng %s)" % fp(sb.get("sum1") or 0))]
    for it in b2:
        kids += [_bar([dict(it, k=it["k"])], COLORS2), line(it["label"] + " ", *tv(it.get("pct"), fp, False))]
    dd = sb.get("data_date") or {}
    kids += [note("Thanh HĐQT và Tổ chức là lát chồng lấn, không cộng thành 100% và không cộng vào thanh 1."),
             line("Tự do chuyển nhượng ", *tv(sb.get("free_float"), fp, False), " · FOL ", *tv(sb.get("fol"), fp, False),
                  " · tổng cp ", *tv(sb.get("total_shares"), fn, False)),
             line("Ngày dữ liệu: ", dd.get("text") or "vendor không ghi ngày dữ liệu", tag(dd.get("tier") or U),
                  " · lấy lúc ", dmy_hm(sb.get("lay_luc")))]
    return h("div", None, *kids, key="cd2.struct")


# ── 06 (b, c, c2) cổ đông lớn, tập trung, Δ theo kỳ ─────────────────────────


def _holder_row(r):
    extra = " · ".join(x for x in (r.get("position"), r.get("group")) if x)
    name = "%s. %s%s%s%s" % (r.get("rank"), r.get("name"), " (%s)" % extra if extra else "",
                             "" if r.get("fresh") else " · cũ", " · trùng tên" if r.get("dup") else "")
    return [[q(name)], cv(r.get("qty"), T2, fm), tv(r.get("qty_now"), fm, False) if r.get("qty_now") else "·",
            tv(r.get("pct"), fp)]


def holders_block(td, lite=0):
    ht = td.holders
    if not env_ok(ht):
        return line("Cổ đông lớn: ", cdn(ht))
    rows = ht.get("rows") or []
    hidden = 0
    if lite:
        olds = [r for r in rows if not r.get("fresh")]
        keep = {id(r) for r in olds[:40]}
        hidden = max(0, len(olds) - 40)
        rows = [r for r in rows if r.get("fresh") or id(r) in keep]
    tb = table([("Cổ đông (chức vụ · nhóm; cũ = ngoài kỳ mới)", 0, None), ("SL công bố", 1, T2),
                ("SL quy đổi hiện hành", 1, None), ("% vốn", 1, None)], [_holder_row(r) for r in rows], key="cd2.holders")
    return h("div", None, PT.cap("(b) MỌI CỔ ĐÔNG LỚN (vc_lk shareholder; % tại ngày công bố từng dòng)"), tb,
             note("%d dòng: %d dòng kỳ mới (công bố từ %s, kỳ %s), %d dòng cũ; SL quy đổi chỉ cho dòng kỳ mới."
                  % (ht.get("n", 0), ht.get("n_fresh", 0), dmy(ht.get("fresh_from")), dmy(ht.get("period")),
                     ht.get("n_old", 0)) + (" Ẩn %d dòng cũ (hạ cấp ngân sách)." % hidden if hidden else "")))


def conc_line(td):
    ht = td.holders
    c = (ht.get("conc") or {}) if env_ok(ht) else {}
    if not c:
        return line("Tập trung: ", cdn(ht))
    return line("(c) Tập trung, chỉ dòng kỳ mới: top 1 ", *tv(c.get("top1"), fp), " · top 3 ", *tv(c.get("top3"), fp),
                " · top 5 ", *tv(c.get("top5"), fp), " · HHI ", *tv(c.get("hhi"), fn), " · cá nhân ",
                *tv(c.get("pct_person"), fp), " · tổ chức ", *tv(c.get("pct_org"), fp), key="cd2.conc")


def hdelta_block(td):
    hd = td.hdelta
    if not env_ok(hd):
        return line("(c2) Δ cổ đông lớn theo kỳ: ", cdn(hd))
    rows = [[q(r.get("name")), cv(r.get("qty0"), T2, fm), cv(r.get("qty1"), T2, fm), tv(r.get("d_qty"),
            lambda x: fm(x, True))] for r in (hd.get("rows") or [])[:20]]
    return h("div", None, PT.cap("(c2) Δ CỔ ĐÔNG LỚN %s → %s" % (dmy(hd.get("d0")), dmy(hd.get("d1")))),
             table([("Cổ đông", 0, None), ("SL kỳ trước", 1, T2), ("SL kỳ sau", 1, T2), ("Δ", 1, None)], rows))


# ── 06 (d, d2) chuỗi sở hữu chủ thể, chuyển giao ────────────────────────────


def _ordinal(d):
    s = str(d)
    return int(s[:4]) * 372 + int(s[5:7]) * 31 + int(s[8:10])


def _ladder_svg(o, i):
    pts = [p for p in o.get("points") or [] if isinstance(p.get("pct"), (int, float))]
    if len(pts) < 2:
        return None
    xs0 = [_ordinal(p["date"]) for p in pts]
    lo, hi = min(xs0), max(xs0)
    X = lambda v: 8 + 364 * (v - lo) / max(1, hi - lo)  # noqa: E731
    top = max(p["pct"] for p in pts) * 1.1 or 1.0
    Y = PT.CH.lin_scale(0, top, 10, 108)
    xs, ys = [X(v) for v in xs0], [Y(p["pct"]) for p in pts]
    dots = "".join("M%s %sh0.1" % (PT.CH.r1(x), PT.CH.r1(y)) for x, y in zip(xs, ys))
    return h("svg", {"width": "100%", "height": "auto", "display": "block"},
             h("path", None, a={"d": PT.CH.path_d(xs, ys), "fill": "none", "stroke": C.gold, "strokeWidth": 1.4}),
             h("path", None, a={"d": dots, "fill": "none", "stroke": C.ink, "strokeWidth": 4, "strokeLinecap": "round"}),
             a={"viewBox": "0 0 380 120"}, key="cd2.svg.lad.%d" % i)


def ladder_block(td):
    ld = td.ladder
    if not env_ok(ld) or not ld.get("owners"):
        return line("(d) Chuỗi sở hữu chủ thể: ", cdn(ld, "không đủ bản ghi sở hữu sau giao dịch"))
    cells = []
    for i, o in enumerate(ld["owners"][:6]):
        cells.append(h("div", None,
                       h("div", S_LAD, q(o.get("name")), " · ", *tv(o.get("pct_first"), fp), " → ",
                         *tv(o.get("pct_last"), fp), (" · " + o["group"]) if o.get("group") else None),
                       _ladder_svg(o, i)))
    grs = sorted((g for g in ld.get("groups") or [] if ok(g.get("pct_last"))), key=lambda g: -g["pct_last"].value)[:5]
    gl = [x for g in grs for x in ("%s (%d thành viên): " % (g.get("group"), len(g.get("members") or [])),
                                    *tv(g.get("pct_last"), fp), " · ")][:-1]
    return h("div", None, PT.cap("(d) CHUỖI SỞ HỮU CHỦ THỂ (% sở hữu sau giao dịch, vendor)"),
             h("div", S_GRID3, *cells), line("Nhóm, tổng % lần cuối biết: ", *gl) if gl else None,
             note(ld.get("rule") or ""), key="cd2.ladder")


def transfers_block(td):
    pt = td.pairs
    if not env_ok(pt):
        return line("(d2) Chuyển giao: ", cdn(pt))
    prs = list(reversed(pt.get("pairs") or []))
    rows = [[p.get("id"), dmy(p.get("date1")), [q("%s → %s" % ((p.get("from") or {}).get("name"),
                                                             (p.get("to") or {}).get("name")))],
             [fm(p.get("qty") or 0), tag(T2, p.get("date1"))], cv(p.get("qty_now"), E, fm), cv(p.get("pct"), E, fp),
             PAIR_VI.get(p.get("kind"), p.get("kind"))] for p in prs]
    ev = [x for e in pt.get("evidence") or [] for x in (trich("thau_tom", e.get("text")), tag(e.get("tier")), " ")]
    return h("div", None, PT.cap("(d2) CẶP CHUYỂN GIAO (cùng KL, ngược chiều, cùng cửa sổ; không tính vào nội bộ ròng)"),
             table([("Cặp", 0, None), ("Ngày", 0, None), ("Bên chuyển → bên nhận", 0, None), ("KL", 1, None),
                    ("Quy đổi hiện hành", 1, E), ("% vốn", 1, E), ("Loại", 0, None)], rows, key="cd2.pairs")
             if rows else line("Không có cặp chuyển giao."),
             line("Đối chiếu nguồn: ", *ev) if ev else None)


# ── 06 (e) nội bộ: theo năm, gần nhất, đăng ký ──────────────────────────────


def _year_row(y):
    return [str(y.get("year")), ["%d · " % y.get("n_buy", 0), *cv(y.get("cp_buy_now"), E, fm)],
            ["%d · " % y.get("n_sell", 0), *cv(y.get("cp_sell_now"), E, fm)], tv(y.get("net_pct"), fps, False),
            str(y.get("n_transfer", 0)), str(y.get("n_reg", 0)), cv(y.get("exec_ratio"), E, fp),
            "%d / %d" % (y.get("n_not_done", 0), y.get("n_overdue", 0))]


def _recent_row(r, today):
    reg = r.get("status") == "dang_ky"
    qty = r.get("register") if reg else abs(r.get("acquire") or 0)
    flags = [STATUS_VI.get(r.get("status"), r.get("status"))] + (["quá hạn U"] if "qua_han" in r.get("flags", []) else []) \
        + (["chuyển giao %s" % r["pair"]["id"]] if r.get("pair") else []) + (["loại (mâu thuẫn)"] if not r.get("valid") else [])
    own = r.get("own_after")
    return [dmy(r.get("date")), [q("%s%s" % (r["owner"]["name"], " · " + r["group"] if r.get("group") else ""))],
            "%s %s" % (r.get("code"), {1: "mua", -1: "bán"}.get(r.get("side"), "khác")),
            [("ĐK " if reg else "") + fm(qty or 0), tag(T2, r.get("public"))],
            fp(own) if isinstance(own, (int, float)) else "·", ", ".join(flags)]


def insider_block(td, lite=0):
    yr = td.yearly
    if not env_ok(yr):
        return line("(e) Giao dịch nội bộ: ", cdn(yr))
    years = list(reversed(yr.get("years") or []))
    recent = (yr.get("recent") or [])[:20 if lite else 40]
    opened = {id(r) for r in yr.get("open") or []}
    hl = {i for i, r in enumerate(recent) if id(r) in opened or (r.get("status") == "dang_ky" and
                                                                str(r.get("end") or "") >= td.today)}
    return h("div", None,
             PT.cap("(e) NỘI BỘ THEO NĂM (cp quy đổi, không tính chuyển giao)"),
             table([("Năm", 0, None), ("Mua: dòng · cp", 1, E), ("Bán: dòng · cp", 1, E), ("Ròng % vốn", 1, None),
                    ("Chuyển giao", 1, None), ("Đăng ký", 1, None), ("Tỷ lệ thực hiện", 1, E),
                    ("Không TH / quá hạn", 1, None)], [_year_row(y) for y in years], key="cd2.inyear"),
             PT.cap("%d GIAO DỊCH NỘI BỘ GẦN NHẤT (tô nổi: đăng ký còn mở)" % len(recent)),
             table([("Ngày", 0, None), ("Chủ thể · nhóm", 0, None), ("Loại", 0, None), ("KL", 1, None),
                    ("Sở hữu sau", 1, T2), ("Trạng thái", 0, None)], [_recent_row(r, td.today) for r in recent],
                   key="cd2.inrecent", hl=hl),
             line("Đăng ký còn mở: %d · đăng ký quá hạn chưa có kết quả: %d" % (len(yr.get("open") or []),
                                                                            len(yr.get("overdue") or [])),
                  tag(U), " (vendor ghi đè bản đăng ký bằng kết quả; quá hạn chưa có kết quả không có nghĩa là "
                          "không thực hiện)"))


# ── 06 (g, h) công ty con / liên kết, quỹ ───────────────────────────────────


def rel_block(td, lite=0):
    rv = td.rel
    if not env_ok(rv):
        return line("(g) Công ty con / liên kết: ", cdn(rv))
    top = (rv.get("top") or [])[:8 if lite else 15]
    listed = rv.get("listed") or []
    seen = {(x.get("name"), x.get("ticker")) for x in listed}
    rows = [[q(x.get("name")), x.get("ticker") or "·", {"subsidiaries": "con", "affiliates": "liên kết"}.get(
        x.get("kind"), x.get("kind") or "·"), tv(x.get("pct"), fp, False)]
            for x in listed + [t for t in top if (t.get("name"), t.get("ticker")) not in seen]]
    return h("div", None, PT.cap("(g) CÔNG TY CON / LIÊN KẾT: mọi mã niêm yết + top %d theo %%" % len(top)),
             table([("Tên", 0, None), ("Mã", 0, None), ("Loại", 0, None), ("% sở hữu", 1, None)], rows, key="cd2.rel"),
             line("%d công ty con, %d liên kết · " % (rv.get("n_sub", 0), rv.get("n_aff", 0)),
                  rv.get("time_note") or "thời điểm UNVERIFIED (vendor không ghi ngày)", tag(U)))


def _counts(hs):
    """Số quỹ hai kỳ smart_money: ['37', T2·10/06, ' → ', '41', T2·23/09] (ô thiếu → '?')."""
    out = []
    for k, d in (("n_funds0", "d0"), ("n_funds1", "d1")):
        n = hs.get(k)
        out += ([" → "] if out else []) + ([fn(n), tag(T2, hs.get(d))] if isinstance(n, int) else ["?"])
    return out


def _fund_counts(ev, hs):
    ev.t(" · số quỹ ", *_counts(hs))
    for k, d in (("n_funds0", "d0"), ("n_funds1", "d1")):
        if isinstance(hs.get(k), int):
            ev.mark(T2, hs.get(d))
    return ev


def fund_block(td):
    fv = td.fund
    if not env_ok(fv):
        return line("(h) Quỹ: ", cdn(fv))
    net = fv.get("net") or {}
    parts = []
    for k, lab in (("m1", "1T"), ("m3", "3T"), ("m6", "6T"), ("ytd", "từ đầu năm"), ("y1", "1 năm")):
        v = net.get(k)
        parts += [lab + " ", *tv(v, lambda x: fm(x, True)),
                  (" (%s)" % v.note) if ok(v) and v.note else None, " · "]
    hs = fv.get("hist") or {}
    hl = (["Hiệu hai ảnh quy đổi %s → %s: " % (dmy(hs.get("d0")), dmy(hs.get("d1"))),
           *tv(hs.get("delta_now"), lambda x: fm(x, True)), " cp · số quỹ ", *_counts(hs),
           " (chỉ so được khi cùng số quỹ; Δ chính là ròng cùng tập quỹ ở dòng trên)"]
          if hs else [cdn(None, "chưa có hai kỳ smart_money")])
    return h("div", None, PT.cap("(h) QUỸ (tín hiệu quỹ, không phải chủ thể)"),
             line("Nắm ", *tv(fv.get("held"), fm), " cp (", *tv(fv.get("pct_out"), fp), " vốn) · số quỹ ",
                  *tv(fv.get("n_funds"), fn)),
             line("Ròng cùng tập quỹ theo cửa sổ (vendor net_change, cp, chưa quy đổi): ", *parts[:-1]), line(*hl),
             line("Chi tiết từng quỹ: ", can_data(fv.get("detail_why") or "chi tiết từng quỹ cần đăng nhập Vietcap IQ")),
             key="cd2.fund")


def top_capitaliq(td, lite=0):
    return top_box("capitaliq", PT.cap("06 · CỔ ĐÔNG LỚN & CHUỖI SỞ HỮU (VIETCAP IQ)"), structure_block(td),
                   holders_block(td, lite), conc_line(td), hdelta_block(td), ladder_block(td), transfers_block(td),
                   insider_block(td, lite), rel_block(td, lite), fund_block(td), TDN.quy(td.tk, off=td.off, compact=True))


# ── 07 Sổ bằng chứng chủ thể (9 dòng câu hỏi, không cột kết luận) ───────────


class Ev:
    """Gom bằng chứng một dòng: chữ + số (mỗi số một nhãn), bậc và ngày đã dùng, trạng thái dữ liệu."""

    def __init__(self):
        self.kids, self.tiers, self.dates, self.n_ok, self.n_can, self.why = [], [], [], 0, 0, None

    def t(self, *kids):
        self.kids += [k for k in kids if k is not None]
        return self

    def v(self, v, fmt=None, date=True, why=None):
        if ok(v):
            self.mark(v.tier, v.asof)
        else:
            self.n_can += 1
            self.why = self.why or PT.why_of(v, why)
        self.kids += tv(v, fmt, date, why)
        return self

    def mark(self, t, asof=None):
        """Ghi một bằng chứng có bậc (chữ trích nguyên văn, số đếm…): tính là có dữ liệu."""
        self.n_ok += 1
        t = PT.ntier(t)
        if t not in self.tiers:
            self.tiers.append(t)
        if asof:
            self.dates.append(str(asof)[:10])
        return self

    def can(self, why):
        self.n_can += 1
        self.why = self.why or why
        self.kids.append(can_data(why))
        return self

    def br(self):
        self.kids.append(h("br"))
        return self

    def state(self):
        if self.n_ok and not self.n_can:
            return ["có số"]
        if self.n_ok:
            return ["một phần"]
        return [can_data(self.why or "chưa có số")]


def _ev1(td):
    ev, ht = Ev(), td.holders
    fresh = [r for r in (ht.get("rows") or []) if r.get("fresh")] if env_ok(ht) else []
    if fresh:
        ev.t("Cổ đông lớn nhất kỳ mới: ", q(fresh[0].get("name")), " ").v(fresh[0].get("pct"), fp)
    else:
        ev.t("Cổ đông lớn nhất: ").v(ht if not env_ok(ht) else None, why=None if not env_ok(ht) else "không có dòng kỳ mới")
    ev.br().t("Chủ tịch HĐQT (sổ vendor): ").v(td.leader)
    ev.br().t("Nhóm chaebol (bảng tay): ")
    if td.chaebol:
        ev.t(", ".join(td.chaebol), tag(E)).mark(E)
    else:
        ev.can(td.why_none("mã không thuộc nhóm chaebol nào trong bảng tay"))
    seeds = Counter(m["group"] for m in td.gmap.values() if m.get("rule") == "seed")
    ddrp = {m["group"] for m in td.gmap.values() if m.get("rule") == "ddrp"}
    for g, n in seeds.items():
        ts = sorted({m["tier"] for m in td.gmap.values() if m.get("group") == g})
        ev.br().t("%s: %d thành viên khớp hạt giống" % (g, n), *[tag(t) for t in ts])
        for t in ts:
            ev.mark(t)
    if ddrp:
        ev.br().t("%d nhóm người liên quan (DDRP, vendor)" % len(ddrp), tag(T2)).mark(T2)
    return ev, "vc_lk shareholder; bảng nhóm chaebol; GROUP_SEEDS + insider DDRP"


def _net_part(ev, lab, net):
    if not env_ok(net):
        return ev.t(lab + ": ").v(net)
    ev.t(lab + ": ròng ").v(net.get("net_now"), lambda x: fm(x, True)).t(" cp quy đổi (").v(net.get("net_pct"), fps) \
        .t(" vốn), đã loại %d dòng chuyển giao" % net.get("n_pairs_excluded", 0))
    return ev


def _ev2(td):
    ev = Ev()
    _net_part(ev, "12T", td.net12).br()
    _net_part(ev, "36T", td.net36)
    for x in (td.net12.get("top") or [])[:3] if env_ok(td.net12) else []:
        n, dp = x.get("n_mem") or 1, x.get("d_pct")
        ev.br().t(q(x.get("name")), " (%d thành viên, %% lần cuối biết)" % n if n > 1 else None, ": ") \
            .v(x.get("pct_before"), fp).t(" → ").v(x.get("pct_after"), fp).t(" (Δ ") \
            .v(dp, lambda v: sign_fixed(v + 0.0, 2, zfix=True) + " điểm %") \
            .t(")", "; " + dp.note if ok(dp) and dp.note else None)
    return ev, "vc_lk insider-transaction (theo nhóm, khử chuyển giao)"


def _ev3(td):
    ev, ex = Ev(), td.execs
    if not env_ok(ex):
        return ev.t("Thực hiện đăng ký 36T: ").v(ex), "vc_lk insider-transaction"
    ev.t("36T: tỷ lệ thực hiện ").v(ex.get("exec_ratio"), fp).t(" (%d dòng có đăng ký)" % ex.get("n_done_reg", 0)) \
        .br().t("Không thực hiện được ").v(ex.get("n_not_done"), fn).t(" · đang mở ").v(ex.get("n_open"), fn) \
        .t(" · quá hạn chưa có kết quả ").v(ex.get("n_overdue"), fn)
    return ev, "vc_lk insider-transaction (|KL thực hiện| ÷ KL đăng ký)"


def _ev4(td):
    ev, ca, ag = Ev(), td.cap, td.agm
    if env_ok(ca):
        c = ca.get("counts") or {}
        ev.t("24T: thu tiền %d · ESOP %d · không thu tiền %d · cổ tức tiền %d" % (
            c.get("thu_tien", 0), c.get("esop", 0), c.get("khong_thu", 0), c.get("co_tuc_tien", 0)),
            tag(T2, ca.get("asof"))).mark(T2, ca.get("asof"))
    else:
        ev.t("Sự kiện vốn: ").v(ca)
    ev.br().t("ĐHCĐ sắp tới: ")
    if env_ok(ag):
        up = ag.get("upcoming") or []
        ev.t(", ".join(dmy(x.get("date")) for x in up) if up else "không có", tag(T2, ag.get("asof"))).mark(T2)
    else:
        ev.v(ag)
    ct = td.chu_the or {}
    ev.br().t("Nhãn chủ thể: ").v(ct.get("nhan")).t(" · nguồn mâu thuẫn" if ct.get("xung_dot") else "")
    nq = (td.intent or {}).get("nq")
    ev.br().t("Khung NQ (bảng tay, chỉ khung): ")
    if nq:
        ev.t("%s · %s · %s" % (nq.get("nq"), nq.get("chaebol"), nq.get("founder")), tag(nq.get("tier") or E,
                                                                                     nq.get("as_of"))).mark(E, nq.get("as_of"))
    else:
        ev.can(td.why_none("mã không có trong tier_a nq68_nq79"))
    p = td.policy
    ev.br().t("Basket V21: ", *([q("%s · %s · %s" % (p.get("basket"), p.get("cluster"), p.get("tag"))), v21_mark()]
                                if p else [can_data("V21 không có POLICY_MAP cho mã này")]))
    return ev, "vc_lk events-v2, events-all; fft_langkinh; nq68_nq79 (tier_a); V21 POLICY_MAP"


def _ev5(td):
    ev, sp, ds = Ev(), td.spikes, td.deals
    if env_ok(sp):
        ev.t("Tuần thoả thuận đột biến: %d trong 52 tuần, %d trong %d tuần" % (
            sp.get("n_52w", 0), len(sp.get("weeks") or []), sp.get("n_weeks", 0)), tag(E, sp.get("asof"))).mark(E)
    else:
        ev.t("Tuần thoả thuận đột biến: ").v(sp)
    ev.br()
    if env_ok(ds) and ds.get("rows"):
        m = [r for r in ds["rows"] if r.get("match")]
        ev.t("Phiên thoả thuận lớn khớp nội bộ tổ chức ±5 phiên: %d/%d" % (len(m), len(ds["rows"])), tag(E)).mark(E)
        for r in m[:3]:
            ev.br().t(dmy(r.get("date")) + ": premium ").v(r.get("premium"), fps)
    else:
        ev.t("Phiên thoả thuận lớn: ").v(ds, why="không có phiên thoả thuận trong 3 năm")
    return ev, "vc_lk price-history (totalDeal*), insider-transaction"


def _ev6(td):
    ev, fw = Ev(), td.flows
    wins = (fw.get("win") or {}) if env_ok(fw) else {}
    for k in ("1y", "3y"):
        w = wins.get(k)
        if not env_ok(w):
            ev.t(PT.WIN_VI[k] + ": ").v(w or fw).br()
            continue
        ev.t(PT.WIN_VI[k] + ": NN ").v(w.get("nn_vol"), lambda x: fm(x, True)).t(" cp · Δ%NN ").v(w.get("d_fo_pp"), fpp) \
            .t(" · TD ").v(w.get("td_val"), lambda x: fb(x, True)).t(" (%d/%d phiên) · phần dư " % tuple(
                w.get("td_cover") or (0, 0))).v(w.get("du_val"), lambda x: fb(x, True)).br()
    pos = td.pos if env_ok(td.pos) else {}
    ev.t("%NN cách đỉnh: ").v(pos.get("vs_fo_peak_pp") if pos else td.pos, fpp)
    fv = td.fund
    ev.br().t("Quỹ (tín hiệu quỹ, không phải chủ thể): ")
    if env_ok(fv):
        hs, net = fv.get("hist") or {}, fv.get("net") or {}
        ev.t("nắm ").v(fv.get("held"), fm).t(" cp · ").v(fv.get("n_funds"), fn).t(" quỹ · ròng cùng tập quỹ (vendor, "
                                                                                  "chưa quy đổi) 1T ") \
            .v(net.get("m1"), lambda x: fm(x, True)).t(" · 3T ").v(net.get("m3"), lambda x: fm(x, True))
        if hs:
            _fund_counts(ev, hs)
            ev.t(" · hiệu hai ảnh quy đổi ").v(hs.get("delta_now"), lambda x: fm(x, True))
    else:
        ev.v(fv)
    if td.fft_miss:
        ev.br().t(h("strong", {"color": C.vermillion}, td.FFT_MISS_TEXT))
    return ev, "vc_lk price-history + proprietary-history; fund_holdings, smart_money/history"


def _ev7(td):
    ev, cf = Ev(), td.codong
    if not env_ok(cf):
        return ev.can(PT.why_of(cf)), "lk_hoso.codong (Toàn Vũ)"
    us = [c for c in cf.get("cap") or [] if c.get("usable")][-2:]
    for c in us:
        ev.t("%s → %s: Δ " % (c.get("tu"), c.get("den"))).v(c.get("d_pct"), fps).t(" · k ").v(c.get("k"), fn) \
            .t(" (%s)" % PT.NHAN_K.get(c.get("nhan_k"), c.get("nhan_k") or "chưa nhãn")).br()
    if not us:
        ev.can("không có cặp mốc quan sát dùng được").br()
    if cf.get("thin"):
        ev.t(h("strong", {"color": C.vermillion}, "Pillar I mỏng"), " (%d mốc quan sát)" % cf.get("n_qs", 0)).br()
    mf = td.mf
    rs = [r for r in (mf.get("rows") or []) if r.get("ket") != "KHONG_RO"] if env_ok(mf) else []
    if rs:
        r = rs[-1]
        ev.t("Gần nhất %s → %s: %s" % (r.get("tu"), r.get("den"), PT.KET_VI.get(r.get("ket"))), tag(E)).mark(E)
    else:
        ev.t("MATCH/FLIP: chưa có cặp đủ dữ liệu", tag(E)).mark(E)
    return ev, "lk_hoso.codong (Toàn Vũ) × vc_lk dòng tiền"


def _how(c):
    return "thoả thuận" if c.get("method") == "tt" else "giả định khớp lệnh"


def _ev8(td):
    ev = Ev()
    names = td.row_names()
    for c in td.costs[:5]:
        ev.t(q(names.get(c.get("row"), c.get("row"))), ": giá vốn ước (mua) ").v(c.get("price"), fk) \
            .t(" (%s) · giá nay " % _how(c)).v(c.get("px"), fk).t(" · chênh ").v(c.get("gap_pct"), fps).br()
    if not td.costs:
        ev.can(td.why_none("không có giao dịch mua của tổ chức nội bộ trong 36T")).br()
    for c in td.sells[:3]:
        ev.t(q(names.get(c.get("row"), c.get("row"))), ": giá bán ra ước ").v(c.get("price"), fk) \
            .t(" (%s; dòng bán, không phải giá vốn, không tính chênh)" % _how(c)).br()
    vg = (td.intent or {}).get("vung_gom")
    ev.t("Vùng gom (fft_langkinh, nguyên văn): ")
    if isinstance(vg, dict):
        ev.t(trich("vung_gom", "VWAP %s, lo %s, hi %s; %s" % (fn(vg.get("vwap") or 0), fn(vg.get("lo") or 0),
                                                            fn(vg.get("hi") or 0), vg.get("logic") or "")),
             tag(vg.get("bac") or E)).mark(vg.get("bac") or E)
    else:
        ev.can(td.why_none("fft_langkinh không có vùng gom cho mã này"))
    return ev, "vc_lk insider + price-history (giá vốn ước); fft_langkinh.cau_chuyen.vung_gia_gom"


def _ev9_v21(ev, td):
    deep = (td.T.deep or {}) if td.T else {}
    ph, st = deep.get("phase") or {}, deep.get("strategic") or {}
    if ph.get("stance") or st.get("title"):
        ev.t("V21: ", q(" · ".join(x for x in (ph.get("stance"), st.get("title")) if x)), v21_mark())
    else:
        ev.can("V21 không có strategic/stance cho mã này")


def _ev9(td):
    ev, it = Ev(), td.intent or {}
    _ev9_v21(ev, td)
    cc = it.get("cauchuyen") or {}
    for x in (cc.get("items") or []) if env_ok(cc) else []:
        ev.br().t(x.get("field") + ": ", trich("cc", trim(x.get("text"), 160)), tag(x.get("tier"), cc.get("asof")),
                  " không dùng cho quyết định" if x.get("unv") else None).mark(x.get("tier"), cc.get("asof"))
    if not env_ok(cc):
        ev.br().t("fft_cauchuyen: ").can(PT.why_of(cc))
    facts = sorted(it.get("facts") or [], key=lambda f: str(f.get("asof") or ""), reverse=True)
    ev.br().t("Dữ kiện facts_f*: %d mục" % len(facts))
    for f in facts[:3]:
        ev.br().t("· ", trich("fact", trim(f.get("text"), 140)), tag(f.get("tier"), f.get("asof"))).mark(
            f.get("tier"), f.get("asof"))
    for o in it.get("owner_intent") or []:
        ev.br().t("owner_intent %s: " % dmy(o.get("date")), trich("oi", trim(o.get("title"), 120)),
                  tag(o.get("tier"))).mark(o.get("tier"))
    mh = td.mauhinh
    for i, m in enumerate(mh.value if ok(mh) else []):          # bậc và ngày theo TỪNG mục (b, trang_thai_tu)
        ev.br().t("lk_mauhinh: ") if i == 0 else ev.t(", ")
        ev.t(q(str(m.get("label"))), tag(m.get("tier"), m.get("status_since"))).mark(m.get("tier"), m.get("status_since"))
    ev.br().t("Pha LANGKINH: ").can(PT.WHY_LK22)
    return ev, "V21; fft_cauchuyen; facts_f*; owner_intent (tuyển chọn); lk_mauhinh"


QUESTIONS = (("Ai là chủ thể?", _ev1), ("Chủ thể đã làm gì trong 12T và 36T?", _ev2),
             ("Đăng ký có thực hiện không?", _ev3),
             ("Chủ thể có đang cần tiền / thị trường không? (chỉ liệt kê)", _ev4),
             ("Dòng khối có trùng giao dịch chủ thể không?", _ev5), ("Ai đang hấp thụ hoặc cung?", _ev6),
             ("Pillar I: số cổ đông và k", _ev7), ("Giá hiện tại so với giá vốn ước của chủ thể", _ev8),
             ("Khung có sẵn, không chấm lại", _ev9))


def _book_row(td, i, qtext, fn_):
    try:
        ev, src = fn_(td)
    except Exception as exc:  # một dòng lỗi không làm vỡ Sổ
        td.ctx.warn("codong v2 %s: Sổ dòng %d lỗi %s: %s" % (td.tk, i, type(exc).__name__, exc))
        ev, src = Ev().can("dòng lỗi, xem cảnh báo"), "·"
    last = max(ev.dates) if ev.dates else None
    return h("tr", PT.S_TR, h("td", PT.S_TD, str(i)), h("td", S_EVQ, qtext), h("td", S_EV, *ev.kids),
             h("td", PT.S_TD, h("span", PT.S_SMALL, src)), h("td", PT.S_TD, *([tag(t) for t in ev.tiers] or ["·"])),
             h("td", PT.S_TD, dmy(last) if last else "·"), h("td", PT.S_TD, *ev.state()), key="cd2.book.r%d" % i)


def _gold_row(td):
    mk = ((td.intent or {}).get("cauchuyen") or {}).get("muc_dich_keo")
    body = ([trich("muc_dich_keo", mk.get("text")), tag(mk.get("tier"))] if isinstance(mk, dict) and mk.get("text")
            else [can_data("fft_cauchuyen không có muc_dich_keo cho mã này")])
    return h("div", {**PT.S_LINE, "marginTop": 10, "padding": "8px 12px", "border": "1px solid " + C.gold + "50"},
             h("strong", {"color": C.gold}, GOLD_Q), h("br"), "Mục đích kéo (nguyên văn): ", *body, h("br"),
             "liên quan: dòng 2, 4, 6, 8", key="cd2.book.vang")


def evidence_book(td, lite=0):
    from chaebol_map_data_codong2 import HIERARCHY_TEXT
    heads = ("#", "Câu hỏi", "Bằng chứng (số)", "Nguồn", "Bậc", "Ngày", "Trạng thái dữ liệu")
    tbl = h("table", PT.S_TBL, h("thead", None, h("tr", PT.S_TRH, *[h("th", PT.S_TH, x) for x in heads])),
            h("tbody", None, *[_book_row(td, i, qt, f) for i, (qt, f) in enumerate(QUESTIONS, 1)]))
    return h("div", PT.S_TOP, PT.cap("SỔ BẰNG CHỨNG CHỦ THỂ (9 câu hỏi; không có cột kết luận)"),
             line(h("strong", {"color": C.gold}, HIERARCHY_TEXT)), tbl, _gold_row(td), key="cd2.book")


# ── Bảng tổng 109 mã (inc codong/_tong) ─────────────────────────────────────

SUM_COLS = (("tuan", "Tuần", 7), ("den", "Tới", 10), ("nb_rong_12t", "NB12T", 11), ("dk_mo", "ĐKmở", 11),
            ("tt_dot_bien_52t", "TT52T", 11), ("d_nn_1y_pp", "ΔNN1Y", 11), ("fft_pct3y", "FFT3Y", 11),
            ("fft_pall", "FFTtd", 11), ("codong_qs", "TVqs", 11), ("quy_n", "Quỹ", 7))
SUM_LEGEND = (("NB12T", "nội bộ ròng 12T khử chuyển giao (% vốn)", "nb_rong_12t"), ("ĐKmở", "đăng ký mở", "dk_mo"),
              ("TT52T", "tuần thoả thuận đột biến 52T", "tt_dot_bien_52t"),
              ("ΔNN1Y", "Δ%NN 1 năm (điểm %)", "d_nn_1y_pp"), ("FFT3Y", "FFT percentile 3Y", "fft_pct3y"),
              ("FFTtd", "FFT percentile toàn dải", "fft_pall"), ("TVqs", "mốc Toàn Vũ quan sát", "codong_qs"),
              ("Quỹ", "số quỹ nắm giữ", "quy_n"))
SUM_FMT = {"nb_rong_12t": fps, "d_nn_1y_pp": lambda x: sign_fixed(x + 0.0, 2, zfix=True)}
FFT_COLS = ("fft_pct3y", "fft_pall")          # ô FFT của 5 mã proxy đã bỏ sót phân phối mang '*' (CLAUDE.md §6.4)


def col_tiers(rows):
    """Bậc tiêu đề cột: bậc hằng của SUMMARY_COLS; cột theo atom (None) lấy bậc phổ biến nhất trong các ô có số."""
    from chaebol_map_data_codong2 import SUMMARY_COLS
    out = {}
    for k, t in SUMMARY_COLS:
        if t is None:
            cnt = Counter(PT.ntier(r[k].tier) for r in rows if ok(r.get(k)))
            t = cnt.most_common(1)[0][0] if cnt else None
        out[k] = PT.ntier(t) if t else None
    return out


def _sum_cell(r, k, width, colt):
    v = r.get(k)
    if k == "tuan":
        return [(fn(v) if isinstance(v, int) else "·").ljust(width)]
    if k == "den":
        return [(dmy2(v) if v else "·").ljust(width)]
    if not ok(v):
        return [can_data(), " " * max(1, width - 10)]
    txt = SUM_FMT.get(k, fn)(v.value) + ("*" if k in FFT_COLS and r.get("tk") in FFT_MISS else "")
    if colt and PT.ntier(v.tier) == colt:
        return [txt.ljust(width)]
    return [txt, tag(v.tier), " " * max(1, width - len(txt) - 3)]


def _sum_row(r, ct):
    kids = [r["tk"].ljust(5), (r.get("nhom") or "·").ljust(3)]
    vals = [r.get(k) for k, _, _ in SUM_COLS[2:]]
    if not r.get("tuan") and not any(ok(v) for v in vals):        # cả hàng thiếu: một ô [CẦN DATA] kèm lý do
        kids += ["·".ljust(7) + "·".ljust(10), cdn(next((v for v in vals if v is not None), None))]
    else:
        for k, _, w in SUM_COLS:
            kids += _sum_cell(r, k, w, ct.get(k))
    st = S_ROWB if r.get("vc") else {**S_ROWB, "color": C.inkM}
    return h("button", st, *kids, on={"set": {K_TK: r["tk"], K_SUB: "phase_info"}}, key="cd2.tong." + r["tk"])


def summary_table(rows, groups=None):
    """Bảng tổng (key cd2.tong): mỗi mã một hàng chữ đều cột (font mono), bấm hàng → trang mã sub 01."""
    ct = col_tiers(rows)
    head = "Mã".ljust(5) + "Nh".ljust(3) + "".join(lab.ljust(w) for _, lab, w in SUM_COLS)
    leg = [x for code, desc, k in SUM_LEGEND for x in ("%s: %s " % (code, desc), tag(ct[k]) if ct.get(k) else
                                                       can_data(), " · ")][:-1]
    body, cur = [], None
    gname = {"A": "A · VN30 hiện hành (= Toàn Vũ 30)", "B": "B · 48 mã codong ngoài VN30", "C": "C · chaebol khác trong V21"}
    for r in rows:
        if r.get("nhom") != cur:
            cur = r.get("nhom")
            body.append(h("div", {**PT.S_CAP, "margin": "8px 0 2px"}, gname.get(cur, cur or "·")))
        body.append(_sum_row(r, ct))
    return h("div", None,
             PT.cap("Bảng tổng %d mã (chỉ số, không nhãn; thứ tự A/B/C; sắp theo cột: dùng CSV xuất)" % len(rows)),
             line(*leg), note("Tuần: số tuần từ niêm yết · Tới: dữ liệu giá tới · hàng chữ mờ: chưa nạp vc_lk · bấm "
                              "một hàng để mở trang mã (sub 01)."),
             h("div", S_HEADR, head), *body,
             line(h("strong", {"color": C.vermillion}, "* ô FFT3Y, FFTtd: " + FFT_MISS_TEXT), key="cd2.fftmiss.tong"),
             key="cd2.tong")


# ── bảng chọn mã (gốc tab), dòng bảng tổng an toàn, CSV ─────────────────────

GROUP_TITLE = (("A", "A · VN30 hiện hành (= Toàn Vũ 30)"), ("B", "B · 48 mã codong ngoài VN30"),
               ("C", "C · chaebol khác trong V21"))
S_PICK = {"marginBottom": 14, "padding": "10px 12px", "background": C.parch, "borderRadius": 3}
S_PROW = {"display": "flex", "gap": 5, "flexWrap": "wrap", "alignItems": "center", "marginBottom": 6}
S_PLAB = {"fontSize": 9, "letterSpacing": ".14em", "color": C.inkM, "fontFamily": F_MONO, "marginRight": 6,
          "minWidth": 230}
S_PK = {"background": "transparent", "color": C.ink, "border": "1px solid " + C.rule, "padding": "3px 7px",
        "borderRadius": 2, "cursor": "pointer", "fontFamily": F_MONO, "fontSize": 10, "letterSpacing": ".06em"}
S_PK_DIM = {**S_PK, "color": C.inkM, "border": "1px dashed " + C.parch}
S_PK_ON = {"background": C.gold, "color": C.bg, "border": "1px solid " + C.gold, "fontWeight": 700}


def picker(groups):
    """cd2.picker: 3 hàng A/B/C; nút đặt codong.tk; var tô nút đang chọn; mã chưa có vc_lk tô mờ."""
    rows = []
    for g, title in GROUP_TITLE:
        tks = groups.get(g) or []
        btns = [h("button", S_PK if (groups.get("has_vc") or {}).get(tk) else S_PK_DIM, tk, on={"set": {K_TK: tk}},
                  var=[{"if": {K_TK: tk}, "s": S_PK_ON}], key="cd2.pk." + tk) for tk in tks]
        rows.append(h("div", S_PROW, h("span", S_PLAB, "%s (%d)" % (title, len(tks))), *btns))
    return h("div", S_PICK, *rows, h("div", {**PT.S_NOTE, "marginTop": 2}, "Nút mờ: chưa nạp vc_lk (trang mã hiện "
                                                                            "[CẦN DATA] tương ứng)."), key="cd2.picker")


def _can_rows(order, groups, why):
    from chaebol_map_data_codong2 import SUMMARY_COLS
    from chaebol_map_data_nen import can_data as vcan
    cd = vcan(why)
    return [{"tk": t, "nhom": (groups.get("grp") or {}).get(t), "vc": False, "lk": False, "tuan": None, "den": None,
             **{k: cd for k, _ in SUMMARY_COLS}} for t in order]


def summary_rows_safe(ctx, groups, why_off):
    """O.summary_rows(order, P.price_summary): ctx.data None → mọi ô [CẦN DATA]; lỗi → [CẦN DATA] + cảnh báo."""
    import chaebol_map_data_codong2 as O
    import chaebol_map_data_codong2_gia as P
    order = groups["order"]
    if getattr(ctx, "data", None) is None:
        return _can_rows(order, groups, why_off)
    try:
        return O.summary_rows(order, P.price_summary, ctx.today.isoformat(), groups)
    except Exception as exc:  # bảng tổng lỗi → mọi ô [CẦN DATA]
        ctx.warn("codong v2: summary_rows lỗi %s: %s" % (type(exc).__name__, exc))
        return _can_rows(order, groups, "bảng tổng lỗi, xem cảnh báo")


def csv_rows(rows, extras):
    """Một dòng/mã: cột bảng tổng (số thô + bậc) + LiveTk.csv_extra() cho 48 mã cũ."""
    from chaebol_map_data_codong2 import SUMMARY_COLS
    out = []
    for r in rows:
        row = {"ma": r["tk"], "nhom": r.get("nhom"), "tuan": r.get("tuan"), "du_lieu_toi": r.get("den")}
        for k, _ in SUMMARY_COLS:
            v = r.get(k)
            row[k] = v.value if ok(v) else None
            row[k + "_bac"] = PT.ntier(v.tier) if ok(v) else None
        row.update(extras.get(r["tk"]) or {})
        out.append(row)
    return out


# ── bảng ① tới ⑫ của chart (cd2.legend) ─────────────────────────────────────

KIND_LBL = {"nb_mua": "nội bộ mua", "nb_ban": "nội bộ bán", "chuyen_giao": "chuyển giao", "ph_thu_tien":
            "phát hành thu tiền", "ph_khong_thu": "phát hành không thu tiền", "cp_thuong": "thưởng / cổ tức cp",
            "dhcd": "ĐHCĐ", "tt_dot_bien": "TT đột biến"}


def _legend_cells(inf):
    """(Δ cp quy đổi, % vốn, sở hữu sau, trạng thái, bậc nguồn) của một mốc; ô cùng bậc tiêu đề cột không gắn nhãn."""
    t = inf.get("t")
    if t == "row":
        r, own = inf["r"], inf["r"].get("own_after")
        dq = fm(r["side"] * r["acq_now"], True)
        st = PT.ntier(inf.get("size_tier") or E)
        return ([dq] if PT.ntier(r.get("acq_tier")) == E else [dq, tag(r.get("acq_tier"), r["date"])],
                [fp(inf["size"])] if st == E else [fp(inf["size"]), tag(st, r["date"])],
                fp(own) if isinstance(own, (int, float)) else "·", "đã thực hiện", T2)
    if t == "pair":
        p = inf["p"]
        return (PT.cv(p.get("qty_now"), E, fm), PT.cv(p.get("pct"), E, fp), "·",
                PAIR_VI.get(p.get("kind"), p.get("kind")), E)
    if t == "cap":
        it = inf["it"]
        return ("·", [fp(it["ratio"] * 100), tag(T2, it.get("date"))] if it.get("ratio") else "·", "·",
                PT.SUB_VI.get(it.get("sub"), it.get("sub") or "·"), T2)
    if t == "step":
        s = inf["s"]
        return ("·", [fp((s["factor"] - 1) * 100), tag(U, s["date"])], "·", "bước giá ≥10% suy", U)
    return ("·", "·", "·", "·", E)


def legend_table(td, res, compact=False):
    """Bảng ①…⑫ (cd2.legend). compact = bản hạ cấp khi inc vượt trần nút: gộp # với ngày và ba cột số vào một ô."""
    info = getattr(td, "marker_info", {}) or {}
    rows = []
    for lg in res.get("legend") or []:
        dq, pct, own, st, src_t = _legend_cells(info.get(lg.get("ref")) or {})
        kind = KIND_LBL.get(lg.get("kind"), lg.get("kind"))
        if compact:
            nums = [x for lab, c, tail in (("Δ ", dq, ""), ("", pct, " vốn"), ("sau ", own, "")) if c != "·"
                    for x in (" · ", lab, *PT.cell(c), tail)][1:] or ["·"]
            rows.append([lg.get("glyph") + " " + dmy(lg.get("date")), kind, [q(lg.get("label"))], nums, st, [tag(src_t)]])
        else:
            rows.append([lg.get("glyph"), dmy(lg.get("date")), kind, [q(lg.get("label"))], dq, pct, own, st,
                         [tag(src_t)]])
    if not rows:
        return note("Không có mốc đánh số trong khung này.")
    if compact:
        return table([("# · ngày", 0, None), ("Loại", 0, None), ("Chủ thể / nội dung", 0, None),
                      ("Δ cp quy đổi (E) · % vốn (E) · sở hữu sau (T2)", 1, None), ("Trạng thái", 0, None),
                      ("Bậc nguồn", 0, None)], rows, key="cd2.legend")
    return table([("#", 0, None), ("Ngày", 0, None), ("Loại", 0, None), ("Chủ thể / nội dung", 0, None),
                  ("Δ cp quy đổi", 1, E), ("% vốn", 1, E), ("Sở hữu sau", 1, T2), ("Trạng thái", 0, None),
                  ("Bậc nguồn", 0, None)], rows, key="cd2.legend")
