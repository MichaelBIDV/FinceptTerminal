#!/usr/bin/env python3
"""
chaebol_map_tab_codong_v2_parts: khối MỚI (key cd2.*) của các sub-tab Deep-dive v2, tab codong mode live (P4 render).

Hợp đồng: chaebol_map_spec/codong_v2_spec.md §7.3 (nội dung top/bottom từng sub-tab), §2 (V + gói _env, bậc theo
nguồn). Mỗi hàm top_<sid>(td, lite) nhận đối tượng TkData (chaebol_map_tab_codong_v2) và trả MỘT nút key "cd2.top.<sid>";
lite = 1 là bản hạ cấp khi vượt ngân sách (§3.3). Không đọc kho trực tiếp: mọi số đi qua td (P1/P2 hoặc lớp dữ liệu cũ).

Luật chữ (CLAUDE.md §6, DESIGN §11): mỗi số mới đúng một nhãn bậc theo nguồn THẬT (bảng dùng nhãn ở tiêu đề cột, ô lệch
bậc cột mang nhãn riêng, mỗi hàng có một ô khoá mang nhãn); thiếu số → can_data(lý do); số en-US; chữ mới không có ký tự
gạch dài/gạch ngắn; chữ nguyên văn của nguồn chứa ký tự cấm hoặc từ cấm được bọc nút key "cd2.trich.*" (hàm q).
Không hô mua/bán, không chấm lại pha/stance (CỔNG v1.7 DỪNG).
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from chaebol_map_dom import C, F_MONO, can_data, h, norm_tier, sign_fixed, tier, to_fixed, to_locale
import chaebol_map_tab_codong_v2_chart as CH

T1, T2, T3, E, U = "FACT-T1", "FACT-T2", "SS-T3", "EST", "UNVERIFIED"
K_TK, K_SUB, K_WIN = "codong.tk", "codong.sub", "codong.win"
DASHES = (chr(0x2014), chr(0x2013))
FORBID_RE = re.compile(r"(?<![A-Za-z])(?:BUY|SELL|TRIM|ADD|DCA)(?![A-Za-z])|%NAV|khuyến nghị (?:mua|bán)|nên (?:mua|bán)",
                       re.I)
VN_NUM_RE = re.compile(r"\d{1,3}(?:\.\d{3})+,\d")
WIN_VI = {"20p": "20 phiên", "63p": "63 phiên", "ytd": "từ đầu năm", "1y": "1 năm", "3y": "3 năm", "all": "toàn dải"}
KIND_VI = {"von": "vốn", "dhcd": "ĐHCĐ", "noi_bo": "nội bộ", "dang_ky_mo": "đăng ký mở", "khac": "khác"}
KET_VI = {"MATCH": "MATCH (cùng chiều)", "FLIP": "FLIP (ngược chiều)", "KHONG_RO": "chưa rõ"}
NHAN_K = {"tay_to": "tay to", "vung_xam": "vùng xám", "nho_le": "nhỏ lẻ", "retail": "nhỏ lẻ"}
STATUS_TL = {"dang_ky": "đăng ký", "da_xong": "đã thực hiện", "chuyen_giao": "chuyển giao (ghép cặp)",
             "khong_thuc_hien": "không thực hiện được"}
SUB_VI = {"rieng_le": "riêng lẻ", "quyen_mua": "quyền mua", "dau_gia": "đấu giá", "esop": "ESOP", "chuyen_doi":
          "chuyển đổi", "sap_nhap": "sáp nhập", "co_tuc_cp": "cổ tức bằng cp", "thuong": "cổ phiếu thưởng"}
TRIG_VI = {"chua": "chưa thoả"}
CK_VI = {"dat": "đạt", "chua": "chưa đạt"}
WHY_CN = "không có kênh Cá nhân/Tổ chức sau 08/05/2026"
WHY_LK22 = "chưa trích LANGKINH v22 vào kho đọc được"
WHY_VN_SEG = "giá vnstore nen_ngay (giá trộn): không có KL quy đổi, NN, tự doanh, thoả thuận"

S_TBL = {"width": "100%", "borderCollapse": "collapse", "fontFamily": F_MONO, "fontSize": 10, "marginBottom": 8}
S_TH = {"padding": "5px 6px", "textAlign": "left", "color": C.inkD, "fontSize": 8.5, "letterSpacing": ".06em",
        "fontWeight": 600, "verticalAlign": "bottom"}
S_THR = {**S_TH, "textAlign": "right"}
S_TD = {"padding": "4px 6px", "color": C.ink, "verticalAlign": "top"}
S_TDR = {**S_TD, "textAlign": "right", "whiteSpace": "nowrap"}
S_TDRW = {**S_TD, "textAlign": "right"}        # ô số có [CẦN DATA: lý do]: lý do được xuống dòng
S_TR = {"borderBottom": "1px solid " + C.rule + "80"}
S_TRH = {"borderBottom": "1px solid " + C.rule}
S_TR_HL = {**S_TR, "background": C.gold + "18"}
S_CAP = {"fontSize": 9, "letterSpacing": ".14em", "color": C.ink2, "fontFamily": F_MONO, "fontWeight": 700,
         "margin": "14px 0 6px"}
S_LINE = {"fontSize": 10.5, "color": C.inkD, "fontFamily": F_MONO, "lineHeight": 1.7, "marginBottom": 4}
S_NOTE = {"fontSize": 9.5, "color": C.inkM, "fontFamily": F_MONO, "lineHeight": 1.6, "marginTop": 4}
S_TOP = {"marginBottom": 14, "padding": "10px 14px", "background": C.ink2 + "08", "border": "1px solid " + C.ink2 + "30",
         "borderRadius": 3}
S_SMALL = {"fontSize": 9, "color": C.inkM}


# ── giá trị + nhãn ──────────────────────────────────────────────────────────


def ok(v):
    return v is not None and not isinstance(v, (dict, list)) and getattr(v, "value", None) is not None


def env_ok(e):
    return isinstance(e, dict) and bool(e.get("ok"))


def ntier(t):
    try:
        return norm_tier(t or U)
    except ValueError:
        return U


def tag(t, asof=None):
    """Nhãn bậc (bậc lạ/thiếu → U)."""
    return tier(ntier(t), asof)


def why_of(x=None, why=None):
    """Lý do [CẦN DATA]: lý do của chính nguồn (why của gói, note của V) trước, rồi lý do dự phòng `why`."""
    r = (x.get("why") if isinstance(x, dict) else getattr(x, "note", None)) or why or "chưa có số"
    r = re.sub(r"^\s*\[?CẦN DATA\]?\s*[:\-]?\s*", "", str(r)).strip()
    return r or "chưa có số"


def cdn(x=None, why=None):
    """[CẦN DATA: lý do] từ V/gói (lý do của nguồn), không có thì lý do dự phòng."""
    return can_data(why_of(x, why))


def tv(v, fmt=None, date=True, why=None):
    """[chữ, nhãn bậc] của một V; thiếu → [can_data(lý do)]."""
    if not ok(v):
        return [cdn(v, why)]
    txt = fmt(v.value) if fmt else (v.text if v.text is not None else str(v.value))
    return [txt, tag(v.tier, v.asof if date else None)]


def cv(v, col, fmt=None, why=None):
    """Ô bảng có bậc ở tiêu đề cột: chỉ gắn nhãn khi bậc ô khác bậc cột."""
    if not ok(v):
        return [cdn(v, why)]
    txt = fmt(v.value) if fmt else (v.text if v.text is not None else str(v.value))
    return [txt] if ntier(v.tier) == ntier(col) else [txt, tag(v.tier, v.asof)]


def q(text):
    """Chữ nguyên văn của nguồn: có ký tự gạch dài/ngắn, từ cấm hoặc số kiểu Việt → bọc nút cd2.trich.q (trích nguồn)."""
    s = "" if text is None else str(text)
    if any(d in s for d in DASHES) or FORBID_RE.search(s) or VN_NUM_RE.search(s):
        return h("span", None, s, key="cd2.trich.q")
    return s


def trich(name, text):
    """Trích nguyên văn (fft_cauchuyen, dữ kiện, owner_intent…): luôn bọc nút cd2.trich.<name>."""
    return h("span", None, str(text or ""), key="cd2.trich." + name)


def trim(s, n=220):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n].rstrip() + "…"


# ── định dạng số (en-US) ────────────────────────────────────────────────────


def _z(x, nd):
    return 0.0 if round(float(x), nd) == 0 else float(x)


def fk(x):
    """Giá đồng → '224.0K'."""
    return CH.fmt_px(x)


def fkk(x):
    """Giá nghìn đồng → '212.7K'."""
    return to_locale(_z(x, 1), "en-US", min_frac=1, max_frac=1) + "K"


def fm(x, sign=False):
    """Số cổ phiếu → '105.22M' / '850.5K' / '120'."""
    a, x = abs(x), _z(x, 2)
    s = (to_locale(x / 1e6, "en-US", max_frac=2) + "M" if a >= 1e6 else
         to_locale(x / 1e3, "en-US", max_frac=1) + "K" if a >= 1e3 else to_locale(x, "en-US", max_frac=0))
    return ("+" + s) if sign and x > 0 else s


def fb(x, sign=False):
    """Đồng → tỷ đồng: '1,470.7 tỷ'."""
    x = _z(x / 1e9, 1)
    s = to_locale(x, "en-US", max_frac=1 if abs(x) < 100 else 0) + " tỷ"
    return ("+" + s) if sign and x > 0 else s


def fp(x, nd=2, sign=False):
    """Phần trăm en-US có nhóm nghìn: '1,007.51%'; sign → '+'/'-'; số làm tròn bằng 0 không mang dấu."""
    x = _z(x, nd)
    return ("+" if sign and x > 0 else "") + to_locale(x, "en-US", min_frac=nd, max_frac=nd) + "%"


def fps(x):
    return fp(x, 2, True)


def fpp(x):
    return sign_fixed(_z(x, 2), 2, zfix=True) + " điểm %"


def fn(x):
    return to_locale(int(round(x)), "en-US")


def dmy(d):
    s = str(d or "")
    return "%s/%s/%s" % (s[8:10], s[5:7], s[:4]) if len(s) >= 10 else s


def dmy2(d):
    s = str(d or "")
    return "%s/%s/%s" % (s[8:10], s[5:7], s[2:4]) if len(s) >= 10 else s


def dmy_hm(ts):
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?", str(ts or ""))
    if not m:
        return str(ts or "")
    return "%s/%s/%s" % (m.group(3), m.group(2), m.group(1)) + (" %s:%s" % m.group(4, 5) if m.group(4) else "")


# ── khung nút ───────────────────────────────────────────────────────────────


def cap(*kids, key=None):
    return h("div", S_CAP, *kids, key=key)


def line(*kids, key=None):
    return h("div", S_LINE, *kids, key=key)


def note(*kids, key=None):
    return h("div", S_NOTE, *kids, key=key)


def top_box(sid, *kids):
    return h("div", S_TOP, *kids, key="cd2.top." + sid)


def cell(x):
    if x is None:
        return ["·"]
    return x if isinstance(x, list) else [x]


def _has_can(kids):
    return any(isinstance(k, dict) and k.get("_can") for k in kids)


def table(heads, rows, key=None, hl=()):
    """heads: [(nhãn, phải?, bậc cột | None)]; rows: [[ô]] (ô = chuỗi | nút | list con); hl: chỉ số hàng tô nổi.
    Ô cột số không ngắt dòng, trừ ô có [CẦN DATA: lý do] (lý do dài ép bảng tràn ngang nếu không xuống dòng)."""
    ths = [h("th", S_THR if r else S_TH, lab, tag(t) if t else None) for lab, r, t in heads]
    trs = [h("tr", S_TR_HL if j in hl else S_TR,
             *[h("td", (S_TDRW if _has_can(cell(c)) else S_TDR) if heads[i][1] else S_TD, *cell(c))
               for i, c in enumerate(row)])
           for j, row in enumerate(rows)]
    return h("table", S_TBL, h("thead", None, h("tr", S_TRH, *ths)), h("tbody", None, *trs), key=key)


def chuthe_line(td, key):
    """'Nhãn chủ thể: <nhãn> <bậc·ngày> (nhãn tĩnh, chưa chấm lại)' + cờ nguồn mâu thuẫn."""
    ct = td.chu_the or {}
    nh = ct.get("nhan")
    body = tv(nh) if ok(nh) else [cdn(nh, "fft_langkinh chưa có nhãn chủ thể cho mã này")]  # lý do nguồn trước
    return line("Nhãn chủ thể: ", *body, " (nhãn tĩnh, chưa chấm lại)" if ok(nh) else None,
                " · nguồn mâu thuẫn" if ct.get("xung_dot") else None, key=key)


# ── 01 Phase Infographic: định vị hiện tại, định giá cuối bảng ──────────────


def _band_pos(ff):
    """Vị trí TB 4 tuần FFT so dải P10/P90 3Y (không in mức tuyệt đối)."""
    if not env_ok(ff) or not all(ok(ff.get(k)) for k in ("ma4_now", "p10_3y", "p90_3y")):
        return [cdn(ff, "chưa có TB 4 tuần FFT")]
    m, lo, hi = ff["ma4_now"].value, ff["p10_3y"].value, ff["p90_3y"].value
    txt = "≤ P10 3Y" if m <= lo else "≥ P90 3Y" if m >= hi else "giữa P10 và P90 3Y"
    return [txt, tag(E, ff["ma4_now"].asof)]


def fft_pcts(td):
    ff = td.fft
    if not env_ok(ff):
        return [cdn(ff)]
    out = ["3Y ", *tv(ff.get("pct3y"), fn), " / toàn dải ", *tv(ff.get("pall"), fn), " · TB 4 tuần ", *_band_pos(ff)]
    lech = ff.get("lech")
    if ok(lech) and abs(lech.value) >= 25:
        out.append(" (hai cửa sổ lệch từ 25 điểm, đọc cả hai)")
    return out


def sigma_cells(td):
    sg = td.sigma
    if not env_ok(sg):
        return ["Định giá σ", [cdn(sg)]]
    lab = sg.get("label") or "P/E"
    return ["Định giá σ (%s, cuối bảng)" % lab,
            [lab + " ", *tv(sg.get("x")), " · z ", *tv(sg.get("z")), " (trung bình ", *tv(sg.get("mu")), ", độ lệch ",
             *tv(sg.get("sd")), ")"]]


def top_phase_info(td, lite=0):
    pos = td.pos if env_ok(td.pos) else {}
    why = None if pos else why_of(td.pos)
    g = lambda k, f=None: tv(pos.get(k), f, why=why)  # noqa: E731
    rows = [["Giá đóng phiên cuối", g("px", fk)],
            ["So VWAP 6T / 12T / 24T", [*g("vs_v6", fps), " / ", *g("vs_v12", fps), " / ", *g("vs_v24", fps)]],
            ["Đỉnh lịch sử (đóng điều chỉnh) · cách đỉnh", [*g("ath", fk), " · ", *g("vs_ath", fps)]],
            ["Đỉnh / đáy 52 tuần (đóng cửa)", [*g("hi52", fk), " / ", *g("lo52", fk)]],
            ["%NN sở hữu · đỉnh %NN · cách đỉnh", [*g("fo", fp), " · ", *g("fo_peak", fp), " · ",
                                                     *g("vs_fo_peak_pp", fpp)]],
            ["FOL · room còn lại", [*g("fol", fp), " · ", *g("room_pct", fp)]],
            ["FFT percentile (proxy, không phải tín hiệu)",
             [*fft_pcts(td), *([" · ", h("strong", {"color": C.vermillion}, td.FFT_MISS_TEXT)] if td.fft_miss else [])]],
            ["Đóng cửa so VWAP khớp phiên", g("close_vs_vwap_day", fps)],
            sigma_cells(td)]
    return top_box("phase_info", chuthe_line(td, "cd2.chuthe2"),
                   cap("ĐỊNH VỊ HIỆN TẠI (giá vc_lk; so VWAP, room, % chênh là ước tính)"),
                   table([("Chỉ số", 0, None), ("Giá trị", 0, None)], rows, key="cd2.pos"),
                   note("Định giá đặt cuối bảng: đọc sau nhãn chủ thể và vị trí giá; mốc pha/stance V21 phía dưới "
                        "giữ nguyên văn, không chấm lại."))


# ── 04 Cụm + VWAP: VWAP cụm, đoạn zigzag, VWAP neo, dòng tiền cụm V21 ───────


def vwap_line(td):
    vc = td.vc or {}
    if not vc or not any(ok(vc.get("v%d" % n)) for n in (6, 12, 24)):
        return line("VWAP 6T/12T/24T: ", cdn(vc.get("v6") if vc else None, "chưa có VWAP vc_lk"))
    from chaebol_map_tab_codong_common import vi_label
    out = ["VWAP cụm "]
    for n in (6, 12, 24):
        out += ["%dT " % n, *tv(vc.get("v%d" % n), fkk), " · " if n != 24 else None]
    nh, v6 = vc.get("nhan"), vc.get("v6")
    out += [" · cụm: ", *([vi_label(nh), tag(E, v6.asof if ok(v6) else None)] if nh else [cdn(None, "chưa gắn nhãn cụm")])]
    return line(*out, key="cd2.vwap")


SEG_HEADS = (("#", 0, None), ("Từ → đến (tuần)", 0, None), ("Giá đầu → cuối", 1, T2), ("%", 1, None),
             ("KL/tuần", 1, E), ("ΔKL", 1, E), ("Δ%NN", 1, T2), ("NN ròng cp", 1, E), ("TD ròng", 1, T2),
             ("Thoả thuận", 1, T2), ("Phần dư", 1, E), ("Nội bộ ròng", 1, E))


def _seg_row(td, i, sg, st, tv30):
    nb = td.call("insider_net", "O", "insider_net", td.tk, sg["d0"], sg["d1"], td.today, by="group")
    ptxt = "%s → %s" % (fk(sg["p0"]), fk(sg["p1"])) if sg.get("p0") and sg.get("p1") else "·"
    chg = [fps(sg["chg_pct"]), tag(U if st.get("pre") or td.weekly.get("base") != "vc_lk" else E, sg["d1"])]
    row = [str(i), "%s → %s (%s%s)" % (dmy2(sg["d0"]), dmy2(sg["d1"]), sg.get("weeks"), ", mở" if sg.get("open") else ""),
           ptxt, chg]
    if td.weekly.get("base") != "vc_lk":           # mã vnstore: 7 ô cùng một lý do → một ghi chú dưới bảng (cd2.zig.vn)
        row += ["·"] * 7
    else:
        row += [cv(st.get("vol_w"), E, fm), cv(st.get("d_vol_pct"), E, fps), cv(st.get("d_fo_pp"), T2, fpp),
                cv(st.get("nn_vol"), E, lambda x: fm(x, True)),
                [*cv(st.get("td_val"), T2, lambda x: fb(x, True)), " " + st["td_cover"] if st.get("td_cover") else None],
                cv(st.get("dval"), T2, fb), cv(st.get("du_val"), E, lambda x: fb(x, True))]
    row.append(cv(nb.get("net_pct") if env_ok(nb) else nb, E, fps))
    if tv30:
        row.append(cv(td.call("codong_delta", "O", "codong_delta", td.tk, sg["d0"], sg["d1"]), T3, fps))
    return row


def seg_table(td, lite=0):
    zg = td.zig
    if not env_ok(zg) or not zg.get("segments"):
        return line("Đoạn giá zigzag: ", cdn(zg))
    segs = zg["segments"]
    take = segs[-12:]
    stats = td.segs[-len(take):] if len(td.segs) >= len(take) else [{}] * len(take)
    tpx = (td.weekly.get("tier_px") if env_ok(td.weekly) else None) or T2      # vnstore: giá trộn → U
    heads = [x if x[0] != "Giá đầu → cuối" else (x[0], 1, tpx) for x in SEG_HEADS] + (
        [("Δ cổ đông", 1, T3)] if td.tv30 else [])
    rows = [_seg_row(td, len(segs) - k, sg, st, td.tv30) for k, (sg, st) in
            enumerate(zip(reversed(take), reversed(stats)))]
    old = segs[:-12]
    kids = [cap("ĐOẠN GIÁ CƠ HỌC ZIGZAG 18% (ước tính, không phải pha) · 12 đoạn gần nhất"),
            table(heads, rows, key="cd2.zig")]
    if td.weekly.get("base") != "vc_lk":
        kids.append(line("KL/tuần, ΔKL, Δ%NN, NN ròng, TD ròng, thoả thuận, phần dư (mọi đoạn): ", can_data(WHY_VN_SEG),
                         key="cd2.zig.vn"))
    if old:
        fw = td.call("flow_window", "P", "flow_window", td.tk, old[0]["d0"], old[-1]["d1"])
        kids.append(line("Gộp %d đoạn cũ hơn (%s → %s): NN ròng " % (len(old), dmy(old[0]["d0"]), dmy(old[-1]["d1"])),
                         *tv(fw.get("nn_vol") if env_ok(fw) else fw, lambda x: fm(x, True)), " cp · TD ròng ",
                         *tv(fw.get("td_val") if env_ok(fw) else fw, lambda x: fb(x, True)), " · thoả thuận ",
                         *tv(fw.get("dval") if env_ok(fw) else fw, fb), key="cd2.zig.old"))
    kids.append(note(zg.get("rule") or "", ". Nội bộ ròng: % vốn, không tính chuyển giao nội nhóm (ghép cặp). TD ròng ",
                     "kèm số tuần có bản ghi; phần dư = −(NN + TD) chỉ trên phiên có bản ghi tự doanh, không phải kênh thật."
                     + ("" if td.tv30 else " Δ số cổ đông: "), None if td.tv30 else cdn(None, td.WHY_NO_TV)))
    return h("div", None, *kids)


def anchor_table(td):
    av = td.anchors[:5]
    if not av:
        return line("VWAP neo: ", cdn(td.weekly))
    rows = [[q(a.get("label")), dmy(a.get("date")), cv(a.get("vwap"), E, fk), cv(a.get("px"), T2, fk),
             tv(a.get("gap_pct"), fps), str(a.get("sessions") or "·")] for a in av]
    return h("div", None, cap("VWAP NEO TỪ MỐC (trọng số KL theo số cp; ước tính)"),
             table([("Mốc", 0, None), ("Ngày neo", 0, None), ("VWAP neo", 1, E), ("Giá", 1, T2),
                    ("Chênh", 1, None), ("Phiên", 1, None)], rows, key="cd2.avwap"))


_PERIOD_RE = re.compile(r"^(?:(\d{4})|Q([1-4])/(\d{2}|\d{4}))$")
_Q = {"1": ("01-01", "03-31"), "2": ("04-01", "06-30"), "3": ("07-01", "09-30"), "4": ("10-01", "12-31")}


def period_bounds(period):
    """'2023' → (2023-01-01, 2023-12-31); 'Q2/26' | 'Q2/2026' → quý; dạng khác → None."""
    m = _PERIOD_RE.match(str(period or "").strip())
    if not m:
        return None
    if m.group(1):
        return m.group(1) + "-01-01", m.group(1) + "-12-31"
    y = m.group(3) if len(m.group(3)) == 4 else "20" + m.group(3)
    a, b = _Q[m.group(2)]
    return y + "-" + a, y + "-" + b


def v21_cluster_flows(td):
    cls = (((td.T.deep or {}).get("cluster") or {}).get("clusters") or []) if td.T else []
    if not cls:
        return None
    rows = []
    for c in cls:
        b = period_bounds(c.get("period"))
        if b is None:
            rows.append([q(c.get("id")), q(c.get("period")), [cdn(None, "không đọc được kỳ của cụm V21")], None, None,
                         None])
            continue
        fw = td.call("flow_window", "P", "flow_window", td.tk, b[0], b[1])
        g = lambda k, f, t: cv(fw.get(k) if env_ok(fw) else fw, t, f)  # noqa: E731
        rows.append([q(c.get("id")), q(c.get("period")),
                     tv(fw.get("nn_val") if env_ok(fw) else fw, lambda x: fb(x, True)),
                     g("td_val", lambda x: fb(x, True), T2), g("dval", fb, T2), g("du_val", lambda x: fb(x, True), E)])
    return h("div", None, cap("DÒNG TIỀN TRONG CÁC CỤM V21 (kỳ dạng năm hoặc quý)"),
             table([("Cụm V21", 0, None), ("Kỳ (nguyên văn)", 0, None), ("NN ròng", 1, None), ("TD ròng", 1, T2),
                    ("Thoả thuận", 1, T2), ("Phần dư", 1, E)], rows, key="cd2.v21flow"))


def top_cluster(td, lite=0):
    return top_box("cluster", vwap_line(td), seg_table(td, lite), anchor_table(td), v21_cluster_flows(td))


# ── 05 Cổ đông BCTN: Pillar I Toàn Vũ ───────────────────────────────────────


def _moc_day(m):
    """Ngày của mốc: cuối kỳ (end) hoặc ngày cuối tháng của ky 'YYYY-MM'; không đọc được → None."""
    e = str(m.get("end") or "")[:10]
    if len(e) == 10:
        return date.fromisoformat(e)
    k = str(m.get("ky") or "")
    if re.match(r"^\d{4}-\d{2}$", k):
        y, mo = int(k[:4]), int(k[5:7])
        return date(y + mo // 12, mo % 12 + 1, 1) - timedelta(days=1)
    return None


def _moc_x(moc):
    """(xs, X): hoành độ theo NGÀY của mốc (không theo thứ tự mốc) trên [70, 1170]; X(ngày) cho nhãn năm ở 1/1."""
    ds = [_moc_day(m) for m in moc]
    known = [d for d in ds if d]
    d0, d1 = (min(known), max(known)) if known else (None, None)
    span = (d1 - d0).days if known and d1 > d0 else 0
    X = (lambda d: 70 + 1100 * (d - d0).days / span) if span else (lambda d: 620.0)
    n = len(moc)
    return [X(d) if d else 70 + 1100 * i / max(1, n - 1) for i, d in enumerate(ds)], X, d0, d1


def codong_svg(moc):
    """Bậc thang số cổ đông 1200×160: quan sát nét liền, mọi mốc không CF nét đứt, mốc CF chấm rỗng. Trục ngang theo
    thời gian (ngày cuối kỳ của mốc), nhãn năm đặt ở 1/1."""
    pts = [(i, m) for i, m in enumerate(moc) if isinstance(m.get("v"), (int, float))]
    if len(pts) < 2:
        return None
    vals = [m["v"] for _, m in pts]
    lo, hi = CH.domain(vals, 0.08)
    Y = CH.lin_scale(lo, hi, 14, 140)
    xs, X, d0, d1 = _moc_x(moc)
    ys_all = [Y(m["v"]) if isinstance(m.get("v"), (int, float)) and not m.get("cf") else None for m in moc]
    ys_obs = [Y(m["v"]) if m.get("usable") and not m.get("cf") else None for m in moc]
    obs_xy = [(xs[i], y) for i, y in enumerate(ys_obs) if y is not None]
    solid = CH.path_d([x for x, _ in obs_xy], [y for _, y in obs_xy])
    cf = "".join("M%s %sa3 3 0 1 0 6 0a3 3 0 1 0-6 0" % (CH.r1(xs[i] - 3), CH.r1(Y(m["v"]))) for i, m in pts
                 if m.get("cf"))
    lab = [h("text", None, fn(t), a={"x": 64, "y": CH.r1(Y(t) + 3), "textAnchor": "end"}) for t in CH.lin_ticks(lo, hi, 3)]
    ys = list(range(d0.year + (d0 > date(d0.year, 1, 1)), d1.year + 1)) if d0 else []
    at = [(y, X(date(y, 1, 1))) for y in ys] or ([(d0.year, X(d0))] if d0 else [])   # không có 1/1 trong dải → năm đầu
    yrs = [h("text", None, str(y), a={"x": CH.r1(x), "y": 156, "textAnchor": "middle"}) for y, x in at]
    return h("svg", {"width": "100%", "height": "auto", "display": "block"},
             h("path", None, a={"d": CH.path_d(xs, ys_all), "fill": "none", "stroke": C.inkM, "strokeWidth": 1,
                                "strokeDasharray": "4 3"}),
             h("path", None, a={"d": solid, "fill": "none", "stroke": C.gold, "strokeWidth": 1.6}),
             h("path", None, a={"d": cf, "fill": "none", "stroke": C.ochre, "strokeWidth": 1.2}) if cf else None,
             h("g", None, *lab, *yrs, a={"fontFamily": F_MONO, "fontSize": 9, "fill": C.inkM}),
             a={"viewBox": "0 0 1200 160"}, key="cd2.svg.codong")


def moc_list(moc):
    out = []
    for m in moc:
        ky = "%s/%s" % (str(m.get("ky"))[5:7], str(m.get("ky"))[:4])
        if m.get("cf"):
            out += [ky + ": chưa có số mới (CF)", " · "]
        elif isinstance(m.get("v"), (int, float)):
            out += [ky + ": " + fn(m["v"]), tag(m.get("tier"), m.get("end")), " · "]
    return h("p", {"margin": "4px 0 8px", "fontSize": 10, "color": C.inkD, "fontFamily": F_MONO, "lineHeight": 1.8},
             *out[:-1], key="cd2.moc")


def cap_table(cf, lite):
    caps = cf.get("cap") or []
    caps = caps[-12:] if lite else caps
    rows = [["%s → %s" % (c.get("tu"), c.get("den")), tv(c.get("d_pct"), fps), cv(c.get("k"), E, fn),
             NHAN_K.get(c.get("nhan_k"), c.get("nhan_k") or "·"), "dùng được" if c.get("usable") else
             "không dùng (%s)" % (c.get("trang_thai") or "mốc không quan sát")] for c in caps]
    return table([("Cặp mốc", 0, None), ("Δ% số cổ đông", 1, None), ("k cp/cổ đông ròng", 1, E), ("Nhãn k", 0, None),
                  ("Trạng thái", 0, None)], rows, key="cd2.capk")


def mf_table(td, lite):
    mf = td.mf
    if not env_ok(mf):
        return line("MATCH/FLIP: ", cdn(mf))
    rs = mf.get("rows") or []
    rs = rs[-12:] if lite else rs
    rows = [["%s → %s" % (r.get("tu"), r.get("den")), tv(r.get("d_codong"), fps), cv(r.get("du"), E, lambda x: fb(x, True)),
             cv(r.get("d_fo_pp"), T2, fpp), cv(r.get("nn_vol"), E, lambda x: fm(x, True)),
             KET_VI.get(r.get("ket"), r.get("ket")), r.get("why") or ""] for r in rs]
    return h("div", None, cap("Δ CỔ ĐÔNG × DÒNG TIỀN (MATCH/FLIP: nhãn so sánh dữ liệu, không phải tín hiệu)"),
             table([("Cặp", 0, None), ("Δ cổ đông", 1, None), ("Phần dư", 1, E), ("Δ%NN", 1, T2), ("NN cp", 1, E),
                    ("Kết quả", 0, None), ("Ghi chú", 0, None)], rows, key="cd2.mf"))


def top_shareholder(td, lite=0):
    from chaebol_map_data_codong2 import ESOP_NOTE, HIERARCHY_TEXT, THIN_MAX_QS
    cf = td.codong
    kids = [line(h("strong", {"color": C.gold}, HIERARCHY_TEXT), key="cd2.hier")]
    if not env_ok(cf):
        return top_box("shareholder", *kids, line("Số cổ đông Toàn Vũ: ", cdn(cf)))
    nk = cf.get("n_kieu") or {}
    kids.append(line("Toàn Vũ: %d mốc (%d quan sát, %d nội suy, %d chép CF, %d số tròn); chỉ mốc quan sát dùng để tính Δ"
                     % (cf.get("n_moc", 0), cf.get("n_qs", 0), nk.get("noi_suy", 0), nk.get("chep", 0),
                        nk.get("so_tron", 0)), tag(cf.get("tier"), cf.get("asof"))))
    if cf.get("thin"):
        kids.append(line(h("strong", {"color": C.vermillion}, "Pillar I mỏng: "),
                         "chỉ %d mốc quan sát (ngưỡng %d)" % (cf.get("n_qs", 0), THIN_MAX_QS)))
    kids += [codong_svg(cf.get("moc") or []), moc_list(cf.get("moc") or []), cap("CẶP MỐC VÀ HỆ SỐ k"),
             cap_table(cf, lite), mf_table(td, lite), note(ESOP_NOTE)]
    return top_box("shareholder", *kids)


# ── 06b Flow: cửa sổ, thoả thuận, theo năm, SMR ─────────────────────────────


def _win_row(key, w):
    if not env_ok(w):
        return [WIN_VI.get(key, key), [cdn(w)], None, None, None, None, None, None]
    tc = w.get("td_cover") or [0, 0]
    return ["%s (%s → %s)" % (WIN_VI.get(key, key), dmy2(w.get("d0")), dmy2(w.get("d1"))),
            cv(w.get("nn_vol"), E, lambda x: fm(x, True)), tv(w.get("nn_val"), lambda x: fb(x, True)),
            cv(w.get("d_fo_pp"), T2, fpp),
            [*cv(w.get("td_val"), T2, lambda x: fb(x, True)), " %d/%d phiên" % (tc[0], tc[1]) if tc[1] else None],
            cv(w.get("deal_share"), E, fp), "·" if key == "all" else cv(w.get("premium"), E, fps),
            cv(w.get("du_val"), E, lambda x: fb(x, True))]


def flow_windows_block(td):
    fw = td.flows
    if not env_ok(fw):
        return line("Dòng tiền theo cửa sổ: ", cdn(fw))
    wins = fw.get("win") or {}
    order = [k for k in (fw.get("order") or list(WIN_VI)) if k in wins]
    rows = [_win_row(k, wins[k]) for k in order]
    split = [wins[k].get("nn_split") for k in order if env_ok(wins[k])][:1]
    heads = [("Cửa sổ", 0, None), ("NN ròng cp", 1, E), ("NN ròng", 1, None), ("Δ%NN", 1, T2), ("TD ròng", 1, T2),
             ("Tỷ trọng TT", 1, E), ("Premium TT", 1, E), ("Phần dư", 1, E)]
    sp_line = line("NN tách khớp / thoả thuận: ", *(tv(split[-1]) if split and ok(split[-1]) else [cdn(
        split[-1] if split else None, "chờ --day-du")]))
    return h("div", None, cap("DÒNG TIỀN THEO CỬA SỔ (NN gồm thoả thuận; TD = tự doanh tổng; premium TT quy KL về cp "
                              "hiện hành, bỏ ở toàn dải vì tỷ số hai bình quân nhiều năm không so được)"),
             table(heads, rows, key="cd2.flowwin"), sp_line,
             line("Cá nhân / Tổ chức: ", can_data(WHY_CN), " · phần dư −(NN + TD) chỉ tính trên phiên có bản ghi tự "
                  "doanh: phần dư, không phải kênh thật (CN + TC gộp)."))


def spikes_block(td):
    sp = td.spikes
    if not env_ok(sp):
        return line("Tuần thoả thuận đột biến: ", cdn(sp))
    wk = sp.get("weeks") or []
    rows = [[dmy(w.get("w")), fb(w.get("dval") or 0), [fp(w.get("share") or 0, 1), tag(E, w.get("w"))],
             "×" + to_fixed(w.get("x_med") or 0, 1)] for w in wk[:12]]
    return h("div", None, cap("TUẦN THOẢ THUẬN ĐỘT BIẾN (%s → %s)" % (dmy(sp.get("d0")), dmy(sp.get("d1")))),
             line(sp.get("rule") or "", " · trung vị ", *tv(sp.get("median"), fb), " · %d/%d tuần có thoả thuận · %d tuần "
                  "đột biến, %d trong 52 tuần" % (sp.get("n_deal_weeks", 0), sp.get("n_weeks", 0), len(wk),
                                                   sp.get("n_52w", 0)), tag(E, sp.get("asof"))),
             table([("Tuần", 0, None), ("GT thoả thuận", 1, T2), ("Tỷ trọng TT", 1, None), ("Lần trung vị", 1, E)], rows,
                   key="cd2.spikes") if rows else None)


def deals_block(td):
    ds = td.deals
    if not env_ok(ds) or not ds.get("rows"):
        return line("Phiên thoả thuận lớn nhất: ", cdn(ds, "không có phiên thoả thuận trong 3 năm"))
    names = td.row_names()
    rows = [[dmy(r.get("date")), [fm(r.get("dvol") or 0), tag(T2, r.get("date"))], fb(r.get("dval") or 0),
             cv(r.get("dprice"), T2, fk), cv(r.get("mvwap"), E, fk), cv(r.get("premium"), E, fps),
             q("; ".join(names.get(x, x) for x in r.get("match") or [])) or "không khớp"] for r in ds["rows"]]
    return h("div", None, cap("10 PHIÊN THOẢ THUẬN LỚN NHẤT 3 NĂM, ĐỐI CHIẾU NỘI BỘ TỔ CHỨC ±5 PHIÊN"),
             table([("Ngày", 0, None), ("KL TT", 1, None), ("GT TT", 1, T2), ("Giá TT danh nghĩa", 1, T2),
                    ("VWAP khớp phiên", 1, E), ("Premium", 1, E), ("Khớp giao dịch nội bộ", 0, None)], rows,
                   key="cd2.deals"))


def yearly_block(td, lite):
    yf = td.yflows
    if not env_ok(yf):
        return line("Dòng tiền theo năm: ", cdn(yf))
    rs = list(reversed(yf.get("rows") or []))
    rs = rs[:10] if lite else rs
    rows = [[str(r.get("year")), cv(r.get("open"), T2, fk), cv(r.get("close"), T2, fk), tv(r.get("chg_pct"), fps),
             cv(r.get("nn_val"), T2, lambda x: fb(x, True)), cv(r.get("td_val"), T2, lambda x: fb(x, True)),
             cv(r.get("dval"), T2, fb)] for r in rs]
    return h("div", None, cap("THEO NĂM (giá đóng điều chỉnh đầu/cuối năm)"),
             table([("Năm", 0, None), ("Đầu năm", 1, T2), ("Cuối năm", 1, T2), ("%", 1, None), ("NN ròng", 1, T2),
                    ("TD ròng", 1, T2), ("Thoả thuận", 1, T2)], rows, key="cd2.yflow"))


def smr_line(td):
    sm = td.smr
    if not env_ok(sm):
        return line("SMR (TB KL lệnh mua / TB KL lệnh bán): ", cdn(sm))
    last = (sm.get("rows") or [{}])[-1]
    return line("SMR tuần %s: %s" % (dmy(last.get("w")), to_fixed(last.get("smr") or 0, 2)), tag(E, last.get("w")))


def top_flow(td, lite=0):
    return top_box("flow", flow_windows_block(td), spikes_block(td), deals_block(td), yearly_block(td, lite),
                   smr_line(td))


# ── 08 Key Events: dòng thời gian ───────────────────────────────────────────


def _tl_row(r):
    st = r.get("status")
    return [dmy(r.get("date")), KIND_VI.get(r.get("kind"), r.get("kind") or "·"),
            [r.get("code") or "", " · ", q(r.get("title"))],
            tv(r.get("qty"), fm) if r.get("qty") is not None else [tag(r.get("tier"), r.get("date"))],
            fp(r["ratio"] * 100, 2) if isinstance(r.get("ratio"), (int, float)) else "·",
            STATUS_TL.get(st, st or "·")]


def top_events(td, lite=0):
    tl = td.timeline if not lite else td.call("timeline12", "O", "timeline", td.tk, td.today, months_full=12)
    if not env_ok(tl):
        return top_box("events", line("Dòng thời gian: ", cdn(tl)))
    kids = [cap("DÒNG THỜI GIAN %d THÁNG GẦN NHẤT (vốn, ĐHCĐ, nội bộ, đăng ký mở)" % (12 if lite else 24)),
            table([("Ngày", 0, None), ("Loại", 0, None), ("Nội dung (nguyên văn vendor)", 0, None), ("KL", 1, None),
                   ("Tỷ lệ", 1, T2), ("Trạng thái", 0, None)], [_tl_row(r) for r in tl.get("rows") or []],
                  key="cd2.tl")]
    yrs = tl.get("years") or []
    if yrs:
        rows = [[str(y.get("year")), [" · ".join("%s %d" % (KIND_VI.get(k, k), n) for k, n in (y.get("counts") or {})
                                                .items()), tag(T2)],
                 [q("; ".join(trim(t, 80) for t in y.get("top3") or []))]] for y in yrs]
        kids += [cap("CŨ HƠN: GỘP THEO NĂM (số sự kiện theo loại, 3 sự kiện lớn nhất)"),
                 table([("Năm", 0, None), ("Số sự kiện", 0, None), ("Lớn nhất (nguyên văn vendor)", 0, None)], rows,
                       key="cd2.tlyear")]
    if tl.get("pre2010_why"):
        kids.append(line("Trước 2010: ", can_data(tl["pre2010_why"]), " · bước giá ≥10% suy (chia/thưởng chưa xác minh): ",
                         *_pre_steps(td)))
    return top_box("events", *kids)


def _pre_steps(td):
    st = td.pre_steps
    if not st:
        return ["không có"]
    out = []
    for s in st:
        out += ["%s ×%s" % (dmy(s.get("date")), to_fixed(s.get("factor") or 0, 4)), tag(U, s.get("date")), " · "]
    return out[:-1]


# ── 09 Patterns: tuần KL ≥2× TB12 (vế đọc được), điều kiện theo dõi, checklist ──


def _trig_state(t):
    s = str(t.get("trang_thai_hien") or "")
    if s == "CAN_DATA":
        return [can_data("thiếu dữ liệu để kiểm điều kiện")]
    if s.startswith("dat"):
        return ["thoả điều kiện dữ liệu (CỔNG đang dừng, không kết luận)", tag(t.get("b"), t.get("t"))]
    return [TRIG_VI.get(s, s), tag(t.get("b"), t.get("t"))]


PAT_D_CAP = ("TUẦN KL ≥2× TB 12 TUẦN TRƯỚC (lk_hoso.fft.pattern_d: vế đọc được của v1.7 §3.2, ước tính; "
             "nguồn không gán nhãn D, trang cũng không gán)")


def _pattern_d(td):
    """Vế dữ liệu fw ≥ 2× TB 12 tuần trước của lk_hoso (nguồn ghi 'không gán nhãn D'): chỉ mô tả vế, không đặt tên mẫu."""
    ff = td.fft
    pd = (ff.get("pattern_d") or []) if env_ok(ff) else []
    if not pd:
        return line("Tuần KL ≥2× TB12: ", "không có tuần nào đạt ngưỡng" if env_ok(ff) else cdn(ff))
    out = []
    for p in pd:
        out += ["Tuần %s: KL ×%s TB12 " % (dmy(p.get("tuan")), to_fixed(p.get("boi") or 0, 2)),
                tag(p.get("b"), p.get("tuan")), " (", q(p.get("n")), ") · "]
    return line(*out[:-1], key="cd2.patd")


def fft_miss_line(td, key):
    """Cảnh báo §6.4 cho FPT, VCB, MBB, HPG, CTG ở mọi khối hiện FFT (None với mã khác)."""
    return line(h("strong", {"color": C.vermillion}, td.FFT_MISS_TEXT), key=key) if td.fft_miss else None


def top_patterns(td, lite=0):
    trig = td.trig
    kids = [fft_miss_line(td, "cd2.patwarn"), cap(PAT_D_CAP), _pattern_d(td),
            cap("ĐIỀU KIỆN THEO DÕI (máy, không phải tín hiệu)"),
            table([("Điều kiện (nguyên văn lk_hoso)", 0, None), ("Trạng thái", 0, None)],
                  [[[q(t.get("loai"))], _trig_state(t)] for t in trig], key="cd2.trig") if trig else
            line(cdn(None, "lk_hoso không có trigger cho mã này"))]
    ck = td.check
    items = (ck.get("items") or []) if isinstance(ck, dict) else []
    rows = [[it.get("text"), [cdn(it.get("value"))] if it.get("state") == "can" else [CK_VI.get(it.get("state"))],
             "·" if it.get("state") == "can" else tv(it.get("value"), _ck_fmt(it))] for it in items]
    kids += [cap("CHECKLIST ĐỊNH LƯỢNG TỰ CHẤM (đạt/chưa đạt mô tả dữ liệu, không kèm hành động)"),
             table([("Điều kiện", 0, None), ("Trạng thái", 0, None), ("Số đo", 1, None)], rows, key="cd2.check")
             if rows else line(cdn(ck))]
    return top_box("patterns", *kids)


def _ck_fmt(it):
    i = it.get("id")
    if i in ("fft_can", "fft_cao"):
        return lambda x: "TB4 ×" + to_fixed(x, 2) + " so ngưỡng"
    if i in ("tren_3vwap", "duoi_3vwap"):
        return fk
    if i == "fo_20p":
        return fpp
    if i == "kl_gap_2x":
        return lambda x: "×" + to_fixed(x, 2)
    return lambda x: fn(x)


# ── 10 Action: Vietcap, TP các công ty chứng khoán, lịch sử coverage ────────


def vietcap_block(td):
    vv = td.vview or {}
    rt = vv.get("rating")
    if not ok(rt):
        return line("Vietcap: ", cdn(rt, "Vietcap không coverage mã này"))
    tp, up = vv.get("target"), vv.get("upside")
    out = ["Vietcap (quan điểm vendor, không phải khuyến nghị của trang): ", h("span", None, rt.value, key="cd2.trich.rating"),
           tag(rt.tier, rt.asof), " · TP ", *tv(tp, lambda x: fn(x) + " đ"), " · chênh ", *tv(up, fps),
           " (quá 90 ngày)" if vv.get("stale") else None]
    pv = td.prev
    if pv:
        out += [" · lần trước: ", h("span", None, str(pv.get("rating") or "·"), key="cd2.trich.rating"),
                ", TP " + fn(pv.get("targetPrice") or 0) + " đ" if pv.get("targetPrice") else None,
                tag(T3, pv.get("date"))]
    return line(*out, key="cd2.vietcap")


def sst_block(td):
    ss = td.sst
    lst = ss.value if ok(ss) and isinstance(ss.value, list) else []
    cut = td.days_ago(90)
    new = [t for t in lst if str(getattr(t, "asof", "") or "") >= cut]
    if not new:
        return line("TP các công ty chứng khoán trong 90 ngày: ", cdn(ss if not lst else None,
                                                                    "không có TP trong 90 ngày"))
    rows = [[[q(t.note or "")], tv(t, lambda x: fn(x) + " đ"), dmy(t.asof)] for t in new]
    return h("div", None, cap("TP CÁC CÔNG TY CHỨNG KHOÁN TRONG 90 NGÀY (bậc từng mục; quan điểm bên ngoài)"),
             table([("Nguồn", 0, None), ("TP", 1, None), ("Ngày", 0, None)], rows, key="cd2.sst"),
             note("%d mục cũ hơn 90 ngày không hiện." % (len(lst) - len(new))) if len(lst) > len(new) else None)


def covh_block(td):
    ch = td.covh
    if not ch:
        return line("Lịch sử coverage Vietcap: ", cdn(None, "mã không có trong vc_coverage_hist"))
    rows = [[dmy(c["date"]), [h("span", None, str(c.get("rating") or "·"), key="cd2.trich.rating")],
             [fn(c["tp"]) + " đ", tag(T3, c["date"])] if isinstance(c.get("tp"), (int, float)) else [cdn()],
             q(c.get("tp_time") or "·")] for c in ch]
    return h("div", None, cap("LỊCH SỬ COVERAGE VIETCAP (ngày TP/rating đổi trong các ảnh chụp)"),
             table([("Ảnh chụp", 0, None), ("Rating", 0, None), ("TP", 1, None), ("TP cập nhật", 0, None)], rows,
                   key="cd2.covh"))


def top_action(td, lite=0):
    import chaebol_map_tab_dangnhap as TDN  # khối Vietcap cần đăng nhập (state/vc_iq_dangnhap)
    return top_box("action", vietcap_block(td), TDN.loi_nhuan_kd(td.tk, td.off), TDN.kqkd_so_du_phong(td.tk, td.off), sst_block(td),
                   covh_block(td),
                   note("Các quan điểm trên là của bên ngoài; trang không sinh lệnh, không chấm lại action V21 "
                        "(CỔNG v1.7 DỪNG)."))


# ── bottom: một dòng nguồn ──────────────────────────────────────────────────

SRC = {"phase_info": "vc_lk price-history, lk_hoso (fft, sigma), fft_langkinh (nhãn chủ thể)",
       "chart": "vc_lk price-history + proprietary-history, lk_hoso.fft, vc_lk VNINDEX, insider, events",
       "phase": "bản lưu V21 + vc_lk price-history",
       "cluster": "vc_lk price-history + proprietary-history (zigzag, VWAP neo), insider-transaction",
       "shareholder": "lk_hoso.codong (Toàn Vũ), vc_lk price-history + proprietary-history",
       "capitaliq": "vc_lk shareholder, shareholder-structure, insider-transaction, relationship, details; fund_holdings",
       "flow": "vc_lk price-history + proprietary-history",
       "strategic": "vc_lk, lk_hoso, fft_langkinh, fft_cauchuyen, owner_intent, nq68_nq79, facts_f*, fund_holdings",
       "events": "vc_lk events-v2, events-all, insider-transaction",
       "patterns": "lk_hoso (fft.pattern_d, trigger), vc_lk price-history, lk_mauhinh",
       "action": "vc_lk details, vc_iq_dangnhap (phiên đăng nhập), hhp_forecast_tickers, state/vc_coverage_hist"}


def bottom(td, sid):
    return h("div", S_NOTE, "Nguồn: ", SRC.get(sid, "vc_lk"), " · tính đến ", dmy(td.today), key="cd2.nguon." + sid)
