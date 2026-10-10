#!/usr/bin/env python3
"""
chaebol_map_tab_codong_common — helper THUẦN dùng chung của nhóm codong (tab + Deep-dive 10 sub-tab, chỉ mode live).

Tách 27/09 (final_check §6.2 #10) để mọi tệp của nhóm ≤ 800 dòng: khối helper đặt tạm ở cuối
chaebol_map_tab_codong_deep_chart.py + phần định tuyến dữ kiện ở đầu chaebol_map_tab_codong_deep_live.py, chuyển
nguyên văn; vòng hoàn thiện 27/09 thêm mcp không dấu cho số làm tròn bằng 0, pill TIỀN ĐỀ SAI, dmy_hm, nowrap_can.
Nội dung: nhãn tiếng Việt cho mã máy của kho, mốc Toàn Vũ, trần pill theo bậc, dòng tiền NN/TD theo số
phiên, quy đổi SL cổ đông, dò cơ sở giá CafeF, định dạng ngày/chuỗi, nút nhãn/pill/dữ kiện, định tuyến dữ kiện
facts → sub-tab. Không tự gọi lớp dữ liệu (route_facts nhận module dữ liệu làm tham số). Chỉ hai tệp _live nhập
module này, nên mode v21 không nạp nó.
"""
from __future__ import annotations

import re
from datetime import date

from chaebol_map_dom import C, F_MONO, can_data, h, norm_tier, sign_fixed, status_pill, tier, to_fixed, upd_mark
from chaebol_map_tab_codong_deep_chart import is_num


# ── Helper thuần dùng chung của nhóm codong (mode live) ─────────────────────

TD_LAG = 3                         # tự doanh chậm tối đa 3 phiên (api_data §3.7); thiếu hơn → [CẦN DATA]
DECISIVE = ("ĐẠT", "BỊ BÁC", "TIỀN ĐỀ SAI")
VWAP_NHAN = {"tren_cum": "trên cụm", "kep_nong": "kẹp nông", "kep_sau": "kẹp sâu", "thoat_6t": "thoát cụm 6T",
             "khac": "lẫn (khác)"}
PAT_TT = {"xac_nhan": "xác nhận", "gay": "gãy", "dang_hinh_thanh": "đang hình thành", "huy": "huỷ",
          "het_hieu_luc": "hết hiệu lực"}
KIEU_VI = {"quan_sat": "quan sát", "noi_suy": "nội suy (EST)", "chep": "chép kỳ trước (CF)", "so_tron": "số tròn (EST)"}
PAT_CODONG_VI = {"chua_ro": "chưa rõ"}
LEGAL_NAME_RE = re.compile(r"khởi tố|truy tố|bị bắt|tạm giam|phong to[aả]|vụ án|tội danh|\bTội:", re.I)


def ddmm(iso_d):
    s = str(iso_d or "")
    return "%s/%s" % (s[8:10], s[5:7]) if len(s) >= 10 else s


def ddmmyyyy(iso_d):
    s = str(iso_d or "")
    return "%s/%s/%s" % (s[8:10], s[5:7], s[:4]) if len(s) >= 10 else s


def k1(x):
    """đồng → '232.0K' (toFixed(1) như trang)."""
    return to_fixed(x / 1000, 1) + "K"


_CAN_RE = re.compile(r"\[CẦN DATA(?:\s*[—-]\s*([^\]]*))?\]")


def rich(text):
    """Chuỗi dữ kiện → [chữ, can_data(), chữ…]: '[CẦN DATA…]' trong văn bản dữ kiện tô đúng kiểu vermillion đậm."""
    s = str(text or "")
    out, pos = [], 0
    for m in _CAN_RE.finditer(s):
        out += [s[pos:m.start()], can_data(m.group(1) or None)]
        pos = m.end()
    out.append(s[pos:])
    return [x for x in out if x]


def trim_text(s, n=420):
    """Cắt ở ranh câu gần nhất ≤ n ký tự (giữ độ dài tương đương câu V21); không có ranh câu ở nửa sau thì cắt ở
    ranh từ (không bao giờ cắt giữa từ) + '…'."""
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    if len(s) <= n:
        return s
    cut = max(s.rfind(". ", 0, n), s.rfind("; ", 0, n))
    if cut > n // 2:
        return s[:cut + 1].strip()
    sp = s.rfind(" ", 0, n + 1)
    return s[:sp if sp > 0 else n].rstrip(" ,;:—-") + "…"


def vi_label(x):
    """Mã máy snake_case của kho (tren_cum, kep_sau, chep, chua_ro?…) → nhãn tiếng Việt, giữ hậu tố '?'."""
    if x is None:
        return None
    s = str(x)
    base, q = s.rstrip("?"), "?" if s.endswith("?") else ""
    for t in (VWAP_NHAN, KIEU_VI, PAT_TT, PAT_CODONG_VI):
        if base in t:
            return t[base] + q
    return s.replace("_", " ") if re.fullmatch(r"[a-z0-9_]+\??", s) else s


def ky_vi(ky):
    s = str(ky or "")
    return s[5:7] + "/" + s[:4] if re.match(r"^\d{4}-\d{2}", s) else s


def codong_summary(moc):
    """Mốc Toàn Vũ → (quan sát cuối | None, mốc cuối | None, số kỳ CF). Quan sát = kieu 'quan_sat' VÀ cf=False
    (VHM/HDB có mốc CF gắn kieu 'quan_sat'); số kỳ CF đếm theo cờ cf."""
    moc = [m for m in (moc or []) if isinstance(m, dict)]
    obs = [m for m in moc if m.get("kieu") == "quan_sat" and not m.get("cf")]
    return (obs[-1] if obs else None), (moc[-1] if moc else None), sum(1 for m in moc if m.get("cf"))


def _is_u(t):
    try:
        return norm_tier(t) == "UNVERIFIED"
    except ValueError:
        return True


def cap_status(status, *tiers):
    """Pill quyết định (ĐẠT/BỊ BÁC/TIỀN ĐỀ SAI) phải có ≥1 bằng chứng T1/T2/T3/E trong khối; chỉ có U (hoặc không
    có bậc) → CHƯA RÕ (chính sách: dữ kiện U tối đa CHƯA RÕ)."""
    if status not in DECISIVE:
        return status
    return status if any(t and not _is_u(t) for t in tiers) else "CHƯA RÕ"


def td_window(pn):
    """prop_net(kind='khop') → (n_co, n, ngày dữ liệu tự doanh cuối ISO | None)."""
    if not isinstance(pn, dict):
        return None, None, None
    note = str(getattr(pn.get("vol"), "note", "") or "")
    m = re.search(r"dữ liệu tự doanh tới (\d\d)/(\d\d)/(\d{4})", note)
    return pn.get("n_co"), pn.get("n"), ("%s-%s-%s" % (m.group(3), m.group(2), m.group(1)) if m else None)


def _du_total(nn, pt, okv):
    """Phần dư cùng cơ sở: −(NN tổng + TD TỔNG), triệu cp; NN của flow4 gồm thoả thuận nên TD cũng phải là tổng
    (totalTradeNet), không phải TD khớp. Thiếu số → None."""
    tv_ = (pt or {}).get("vol")
    if not (okv(nn) and okv(tv_)):
        return None
    from chaebol_map_data_nen import V, js_fixed
    du = -(nn.value + tv_.value / 1e6)
    return V(du, js_fixed(du, 1), "EST", min(nn.asof, tv_.asof), "−(NN tổng + TD tổng)",
             "phần dư, không phải kênh thật; NN và TD cùng gồm thoả thuận", "M cp")


def flow_view(f, pn, pt=None):
    """Dòng tiền 60 phiên sau 08/05 (DESIGN §6.5): NN thật; TD thật chỉ khi đủ phiên (n_co ≥ n − 3, phiên vắng
    không điền 0); phần dư chỉ khi TD đủ phiên. pt = prop_net(kind='total'): phần dư −(NN tổng + TD tổng) cùng cơ sở
    (NN của flow4 gồm thoả thuận); không có pt → du của flow4. Trả dict để tab codong và Deep-dive dùng chung."""
    f = f or {}
    okv = lambda v: v is not None and not getattr(v, "can", True) and getattr(v, "value", None) is not None  # noqa
    nn, td, du = f.get("nn"), f.get("td"), f.get("du")
    if pt is not None:
        du = _du_total(nn, pt, okv)
    n_co, n, td_last = td_window(pn)
    full = okv(td) and isinstance(n_co, int) and isinstance(n, int) and n > 0 and n_co >= n - TD_LAG
    why = ("%d/%d phiên có bản ghi tự doanh%s" % (n_co, n, (", tới " + ddmm(td_last)) if td_last else "")
           if isinstance(n_co, int) and isinstance(n, int) else "thiếu proprietary-history")
    return {"nn": nn if okv(nn) else None, "nn_raw": nn, "td": td if full else None, "td_raw": td,
            "du": du if full and okv(du) and okv(nn) else None, "n_co": n_co, "n": n, "td_last": td_last,
            "td_why": why, "from": f.get("from"), "to": f.get("to")}


def mcp(v):
    """V triệu cp → '−1.3M cp' (dấu như trang); làm tròn bằng 0 → '0.0M cp' không dấu (zfix, chỉ live)."""
    return sign_fixed(v.value, 1, zfix=True) + "M cp"


def win_label(fv):
    return ("%s phiên %s→%s" % (fv.get("n") or 60, ddmm(fv.get("from")), ddmm(fv.get("to")))) if fv.get("from") \
        else "60 phiên"


PRO_RATA_RE = re.compile(r"thưởng|cổ tức bằng cổ phiếu", re.I)
RIGHTS_RE = re.compile(r"quyền mua", re.I)


def dedupe_iss(events):
    """events-v2 ISS có GDKHQ, khử trùng (vendor lặp bản ghi) theo (GDKHQ, tỷ lệ, tiêu đề)."""
    seen, out = set(), []
    for e in events or []:
        key = (e.get("exright"), e.get("ratio"), e.get("title"))
        if e.get("code") == "ISS" and e.get("exright") and key not in seen:
            seen.add(key)
            out.append(e)
    return out


def holder_basis(qty, pub, pct_pub, iss, ts_pub, today):
    """SL một dòng sổ cổ đông (ngày công bố pub) quy về cơ sở cp hiện hành: × Π(1+tỷ lệ) các đợt thưởng/cổ tức CP có
    GDKHQ trong (pub, today]; ESOP/riêng lẻ không đổi SL của cổ đông cũ; có quyền mua sau pub → không quy đổi được.
    Cờ lệch: SL ÷ tổng cp tại pub khác % vendor > 0,5 điểm (vendor ghi SL và % ở hai cơ sở khác nhau)."""
    if not is_num(qty) or not pub:
        return {"adj": None, "rights": [], "lech": None, "f": None}
    f, rights = 1.0, []
    for e in iss:
        if pub < e["exright"] <= today:
            t, x = str(e.get("title") or ""), e.get("ratio")
            if PRO_RATA_RE.search(t) and is_num(x) and x > 0:
                f *= 1 + x
            elif RIGHTS_RE.search(t):
                rights.append(e["exright"])
    lech = None
    if is_num(pct_pub) and pct_pub and is_num(ts_pub) and ts_pub:
        x = qty / ts_pub * 100
        lech = (x, pct_pub) if abs(x - pct_pub) > 0.5 else None
    return {"adj": None if rights else qty * f, "rights": rights, "lech": lech, "f": f}


def cafef_basis(dates, closes, adjs, i0, i8, px):
    """Phiên + cơ sở của mốc giá CafeF V21 trong cửa sổ phiên [i0, i8] (i8 = 08/05): khớp đóng cửa THÔ phiên d
    (sai số < 0,02%) → ('raw', d); khớp giá đã điều chỉnh về cơ sở 08/05 → ('adj08', d); không khớp → None."""
    if not is_num(px) or not px or i8 < 0:
        return None
    ok_ = lambda x: is_num(x) and x  # noqa: E731
    f8 = adjs[i8] / closes[i8] if ok_(closes[i8]) and ok_(adjs[i8]) else None
    best = None
    for i in range(max(i0, 0), i8 + 1):
        if not ok_(closes[i]):
            continue
        cands = [("raw", abs(closes[i] / px - 1))] + ([("adj08", abs(adjs[i] / f8 / px - 1))] if f8 and ok_(adjs[i])
                                                      else [])
        for kind, err in cands:
            if err < 2e-4 and (best is None or err < best[2] or (err == best[2] and dates[i] > best[1])):
                best = (kind, dates[i], err)
    return best[:2] if best else None


def structure_dev(s):
    """shareholder-structure tự mâu thuẫn: Σ SL (Nhà nước + NN + khác) lệch tổng cp > 0,5% → dict, ngược lại None."""
    if not isinstance(s, dict):
        return None
    vols = [s.get(k) for k in ("stateVolume", "foreignerVolume", "otherVolume")]
    ts = s.get("totalShares")
    if not all(is_num(v) for v in vols) or not is_num(ts) or not ts:
        return None
    sv = vols[0] + vols[1] + vols[2]
    dev = (sv / ts - 1) * 100
    return {"sum": sv, "total": ts, "dev": dev, "vols": vols} if abs(dev) > 0.5 else None


def nav_books(P, tk):
    """Hai sổ danh mục (portfolio_current) cho một mã: vị thế từng sổ, cờ lệch NAV, mức cao nhất, watch/avoid từng
    sổ, xung đột watch/avoid. Không chọn sổ nào (DESIGN §0.4)."""
    a, b = P.get("lk_khoi11_1009") or {}, P.get("hdcv_1209") or {}
    pos = lambda bk: next((x for x in bk.get("positions") or [] if x.get("tk") == tk), None)  # noqa: E731
    pa, pb = pos(a), pos(b)
    conf = [c for c in P.get("conflicts") or [] if c.get("tk") == tk]
    return {"a": a, "b": b, "pa": pa, "pb": pb, "nav_c": next((c for c in conf if c.get("loai") == "nav"), None),
            "mx": max([p["nav"] for p in (pa, pb) if p] or [0]),
            "fa": "WATCH" if tk in (a.get("watch") or []) else "AVOID" if tk in (a.get("avoid") or []) else None,
            "fb": "AVOID" if tk in (b.get("avoid") or []) else None,
            "xd": [c for c in conf if c.get("loai") in ("watch_vs_avoid", "avoid")]}


# ── Helper nút/nhãn của tab codong (mode live; mode v21 các nhãn tự biến mất) ─

PILLS = ("ĐẠT", "BỊ BÁC", "CHƯA RÕ", "LIVE", "HẾT HẠN", "TIỀN ĐỀ SAI")
_LEGAL = re.compile(r"khởi tố|truy tố|bị bắt|vụ án|tội danh|bắt tạm giam", re.I)
_POLITICAL = re.compile(r"(cựu|nguyên)\s+(TT|Thủ tướng|Chủ tịch nước|Tổng Bí thư|Bộ trưởng)\b|chính trị|political", re.I)
_BUY = re.compile(r"BUY|OUTPERFORM|O-PF|OVERWEIGHT|\bADD\b|MUA|TĂNG TỶ TRỌNG|KHẢ QUAN", re.I)
_SELL = re.compile(r"SELL|UNDERPERFORM|U-PF|UNDERWEIGHT|BÁN|GIẢM TỶ TRỌNG|KÉM", re.I)
_HOLD = re.compile(r"HOLD|NEUTRAL|M-PF|MARKET|TRUNG LẬP|NẮM GIỮ|THEO DÕI", re.I)
_CO_PREFIX = re.compile(r"^(Tổng\s+)?(Công ty|Cty)\s+(Cổ phần|CP|TNHH(\s+(Một|MTV)\s*(Thành Viên)?)?)\s+", re.I)
CAT_RULES = (("BCTN", r"báo cáo thường niên|\bBCTN\b"), ("BCTC", r"báo cáo tài chính|\bBCTC\b"),
             ("KQKD", r"kết quả kinh doanh|\bKQKD\b|giải trình"), ("AGM", r"ĐHĐCĐ|ĐHCĐ|đại hội"),
             ("INSIDER", r"người nội bộ|người có liên quan|\bNLQ\b|giao dịch cổ phiếu|cổ đông lớn"),
             ("GOVERNANCE", r"HĐQT|nhân sự|vốn điều lệ|phát hành|niêm yết|điều lệ|quản trị|cổ tức"))
S_UPD = {"display": "block", "marginTop": 6, "fontSize": 10.5, "color": C.inkD, "lineHeight": 1.6}
S_UPD = {"display": "block", "marginTop": 6, "fontSize": 10.5, "color": C.inkD, "lineHeight": 1.6}


def dmy(iso):
    s = str(iso or "")[:10]
    return "%s/%s/%s" % (s[8:10], s[5:7], s[:4]) if re.match(r"^\d{4}-\d{2}-\d{2}$", s) else s


def dmy_hm(ts):
    """'2026-09-23 23:04' / '2026-09-23T23:10:31+07:00' → '23/09/2026 23:04' (DESIGN §11.3); không khớp → nguyên."""
    s = str(ts or "")
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?", s)
    if not m:
        return s
    return "%s/%s/%s" % (m.group(3), m.group(2), m.group(1)) + (" %s:%s" % m.group(4, 5) if m.group(4) else "")


def nowrap_can(text):
    """Chuỗi nguồn có '[CẦN DATA' (vd dòng CỔNG của lk_hoso) → [chữ, span nowrap '[CẦN DATA', chữ…]: không ngắt dòng
    giữa '[CẦN' và 'DATA' như can_data() của lõi; ghép chữ vẫn nguyên chuỗi."""
    parts = str(text).split("[CẦN DATA")
    out = [parts[0]]
    for p in parts[1:]:
        out += [h("span", {"whiteSpace": "nowrap"}, "[CẦN DATA"), p]
    return [x for x in out if x]


def ok(v):
    return v is not None and hasattr(v, "value") and v.value is not None


def tg(v, date=True):
    """Nhãn bậc của một V (bậc lạ → U + không làm hỏng dựng)."""
    if not ok(v) or not v.tier:
        return None
    try:
        return tier(v.tier, v.asof if date else None)
    except ValueError:
        return tier("U")


def td(entry):
    """Nhãn bậc của một mục dossier/dữ kiện {tier|bac, asof|ngay}."""
    t = entry.get("tier") or entry.get("bac")
    if not t:
        return None
    try:
        return tier(t, entry.get("asof") or entry.get("ngay"))
    except ValueError:
        return tier("U")


def cd(v, why=None):
    """[CẦN DATA — lý do] (lý do = why hoặc note của V, bỏ tiền tố [CẦN DATA] lồng)."""
    note = why or (getattr(v, "note", None) if v is not None else None) or "chưa có dữ liệu"
    note = re.sub(r"^(\s*\[?CẦN DATA\]?\s*(—|-|:)?\s*)+", "", str(note)).strip() or "chưa có dữ liệu"
    return can_data(note)


def num(v, text=None):
    """[chuỗi, nhãn] hoặc [CẦN DATA]."""
    return [text if text is not None else v.show(), tg(v)] if ok(v) else [cd(v)]


def short_name(n):
    n = re.sub(r"\s+", " ", str(n or "")).strip()
    return _CO_PREFIX.sub("", n) or n


def pill(status):
    return status_pill(status) if status in PILLS else None


def upd_block(e, prefix="↻ "):
    """Dòng cập nhật từ mục dossier {text, tier, asof, src, status?} — pill quyết định chỉ khi có bằng chứng ≠ U."""
    st = cap_status(e.get("status"), e.get("tier") or e.get("bac"))
    return h("span", S_UPD, pill(st), " " if st in PILLS else None, prefix, *rich(e.get("text")), td(e), upd_mark())


def legal(text):
    return bool(text) and bool(_LEGAL.search(str(text)))


def political(text):
    return bool(text) and bool(_POLITICAL.search(str(text)))


def legal_caveat(text):
    """U + caveat sau mệnh đề V21 nêu tên cá nhân kèm tố tụng (pháp lý) hoặc quan hệ chính trị."""
    if not (legal(text) or political(text)):
        return None
    what = "pháp lý" if legal(text) else "chính trị"
    return [tier("U"), h("span", {"fontSize": 9, "color": C.vermillion, "fontFamily": F_MONO, "marginLeft": 4},
                              "mệnh đề %s nêu tên cá nhân — chưa đối chiếu FACT-T1" % what)]


def fact_line(f):
    """Một dữ kiện facts_f*: [pill] dd/mm/yyyy · nội dung + bậc + ↻ (U → '(chưa xác minh)', pill tối đa CHƯA RÕ)."""
    st = cap_status(f.get("trang_thai"), f.get("bac"))
    unv = (f.get("bac") or "").upper() == "UNVERIFIED"
    return h("li", None, pill(st), " " if st in PILLS else None, dmy(f.get("ngay")), " · ",
             "(chưa xác minh) " if unv else None, *rich(f.get("noi_dung")), td(f), upd_mark(), key="codong.fact." + f["id"])


def rating_class(r):
    r = str(r or "")
    if _SELL.search(r):
        return "sell"
    if _BUY.search(r):
        return "buy"
    return "hold" if _HOLD.search(r) else "other"


def classify(title):
    for cat, pat in CAT_RULES:
        if re.search(pat, title or "", re.I):
            return cat
    return "OTHER"


def overlaps(f, lo, hi):
    return any(a <= hi and b >= lo for a, b in (f.get("src_lines") or []))


def _date(iso):
    return date.fromisoformat(str(iso)[:10])


# ── Định tuyến dữ kiện facts → sub-tab (dùng chung với bộ sinh dossier) ────


SEG_SUB = {"phase": "phase_info", "cluster": "cluster", "shareholderEvolution": "shareholder", "holders": "capitaliq",
           "q4Flow": "phase", "strategic": "strategic", "events": "events", "patterns": "patterns", "action": "action"}
LOAI_SUB = {"so_lieu": "phase", "su_kien": "events", "ke_hoach": "events", "nhan_su": "events", "claim": "action",
            "chinh_sach": "strategic"}
PILL_OF = {"BỊ BÁC": "BỊ BÁC", "CHƯA RÕ": "CHƯA RÕ", "ĐÃ XẢY RA": "ĐẠT", "ĐẠT": "ĐẠT", "LIVE": "LIVE",
           "HẾT HẠN": "HẾT HẠN"}
def _blocks_for(f, tk):
    subs = set()
    for b in f.get("src_blocks") or []:
        for m in re.finditer(r"(?:CHAEBOL_DEEP_DATA|DEEP_DATA)\.([A-Z0-9/]+)(?:\.([A-Za-z]+))?", b):
            if tk in m.group(1).split("/"):
                subs.add(SEG_SUB.get(m.group(2) or "", LOAI_SUB.get(f.get("loai"), "phase")))
        if b.startswith("HOLDERS_CIQ." + tk):
            subs.add("capitaliq")
        if any(m.group(1) == tk for m in re.finditer(r"SIMPLIZE_(?:REPORTS/)?CONSENSUS\.([A-Z0-9]+)", b)):
            subs.add("action")
    return subs


def route_facts(D, tk):
    """{sub_id: [fact]} — dữ kiện thay mệnh đề của khối Deep-dive (SRC 3565–4247 + HOLDERS_CIQ/SIMPLIZE_CONSENSUS)
    cho mã tk, cộng sự kiện mới (FACT-T1/T2, từ 09/05) của mã vào 'events'. Mỗi dữ kiện vào ĐÚNG một sub."""
    out, seen = {}, set()
    for f in D.facts_for_src(3509, 4247):
        subs = _blocks_for(f, tk)
        if not subs:
            if tk not in (f.get("ma") or []) or not any(3565 <= a <= 4247 for a, _ in f.get("src_lines") or []):
                continue
            subs = {LOAI_SUB.get(f.get("loai"), "phase")}
        sid = sorted(subs, key=lambda s: list(SEG_SUB.values()).index(s) if s in SEG_SUB.values() else 99)[0]
        out.setdefault(sid, []).append(f)
        seen.add(f["id"])
    for f in D.facts_for(ma=tk):
        if f["id"] in seen or f.get("loai") not in ("su_kien", "ke_hoach", "nhan_su"):
            continue
        if f.get("bac") in ("FACT-T1", "FACT-T2") and (f.get("ngay") or "") >= "2026-05-09":
            out.setdefault("events", []).append(f)
            seen.add(f["id"])
    for lst in out.values():
        lst.sort(key=lambda f: f.get("ngay") or "", reverse=True)
    return out


def fact_item(f, status_override=None):
    """Mục dossier (DESIGN §7): text, tier, asof, src + fact id + status (pill) khi là claim đo được."""
    st = cap_status(status_override or PILL_OF.get(f.get("trang_thai") or ""), f.get("bac"))
    it = {"text": trim_text(f.get("noi_dung")), "tier": f.get("bac"), "asof": f.get("ngay"),
          "src": (f.get("nguon_list") or [f.get("file")])[0], "fact": f.get("id"), "loai": f.get("loai")}
    if st:
        it["status"] = st
    return it
