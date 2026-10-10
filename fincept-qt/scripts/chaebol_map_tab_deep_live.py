#!/usr/bin/env python3
"""
chaebol_map_tab_deep_live — lớp live của tab `catalyst` (★ 12) và `deep6` (★ 14). Chỉ nạp ở mode live.

Nguồn chữ mới: dossier (ctx.dossier — mảnh knowledge_os/chaebol_map/cap_nhat_2026-09-27.deep.json):
  catalyst          list sự kiện MỚI tới 03/2027 {d, e, ch, ma, imp, mag, tier, asof, src, facts, extra?[…]}
  catalyst_status   {"<d>|<e>": {status, text, tier, asof, src, facts, extra?[{…, status?}]}} — kết quả 16 sự kiện
                    V21; mỗi vế có thể mang pill riêng (vế U tối đa CHƯA RÕ)
  entities24        {tên: {leader, leader_note, cash[], detail[], munger{i}, interlocks{i}, risk, action}}
  claims54/claims20 (mảnh tab claims54/changelog) — trạng thái chấm lại cạnh mã claim, chỉ claim đúng bộ của thực thể.
"[CẦN DATA]" viết trong chữ dossier được dựng thành nút can_data.
Nguồn số sống: ctx.data (chaebol_map_data) — giá đóng (last_price), dòng tiền 60 phiên (flow4: chỉ NN + TD thật,
CN/TC = [CẦN DATA]), sở hữu chéo (cross_holdings, FACT-T2), quy đổi quyền ngưỡng giá V21 (convert_price, EST).
Luật: stance V21 (pha, AXIS/TIER, IMP/MAGNITUDE, KEY RISK, ACTION) giữ nguyên + V21·12/05 (CỔNG v1.7 DỪNG); chữ V21
có số mang nhãn U (bản lưu chưa kiểm); số mới mang nhãn bậc; thiếu nguồn → [CẦN DATA]. Không hô mua/bán mới.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from chaebol_map_dom import (
    C, F_MONO, can_data, h, js_round, js_string, sign_fixed, status_pill, tier, to_locale, upd_mark, v21_mark,
)

F_SS4 = "'Source Serif 4', serif"
V21_ASOF = "12/05"
# Số cần nhãn: có đơn vị/%, $ hoặc nhóm nghìn. Mã (NQ79, TD6, C19), ngày (13/5/26), pha (6/6) không tính.
NUM = re.compile(r"\$\d|\d{1,3}(?:[.,]\d{3})+|\d(?:[\d.,]*\d)?\s?(?:%|tỷ|triệu|nghìn|tấn|TWh|MW|USD|m³|×|"
                 r"(?:M|B|K|k|x|đ|cp)(?![A-Za-zÀ-ỹ]))")
LEGAL = re.compile(r"bị bắt|khởi tố|truy tố|tạm giam|bắt giam", re.I)
STATUS_COLOR = {"ĐẠT": C.forest, "BỊ BÁC": C.vermillion, "CHƯA RÕ": C.ochre, "LIVE": C.gold, "HẾT HẠN": "#5a564d",
                "TIỀN ĐỀ SAI": C.ink2}                            # = màu Pill của chaebol_map_dom
_TH = re.compile(r"([<>])\s?(\d+(?:\.\d+)?)k|(\d+)-(\d+)k")
_TK = re.compile(r"\b[A-Z]{3}\b")
CAN = "[CẦN DATA]"
# CLAIMS_54.ch ghi tên nhóm khác khoá DEEP_INSIGHT_24 (ngoài phần chuẩn hoá chữ của _norm).
CH_EXTRA = {"DGCDucGiang": ("DGC",), "PetroVietnam": ("PVN",), "Vietcombank": ("Big4 Banking",),
            "BIDV": ("Big4 Banking",), "VietinBank": ("Big4 Banking",), "Agribank": ("Big4 Banking",)}
TD_MIN_COVER = 0.8        # tự doanh phủ dưới 80% phiên cửa sổ → không so được
# Tên chủ sở hữu vendor dài, cắt ra không đọc được là tổ chức nào → tên tắt thông dụng.
OWNER_ALIAS = (("Tổng Công ty Đầu Tư Và Kinh Doanh Vốn Nhà Nước", "SCIC"),
               ("Tập Đoàn Công Nghiệp – Năng Lượng Quốc Gia", "PVN"),
               ("Công ty Đầu tư Tài chính Nhà nước Thành phố Hồ Chí Minh", "HFIC"))
# Số dòng tiền FiinTrade của V21 trong signals: "-173.7M", "+83%" → khớp trường FLOW (≤08/05) của mã.
_FLOW_NUM = re.compile(r"([+-]?\d+(?:\.\d+)?)\s?(M|%)(?![A-Za-zÀ-ỹ])")
FLOW_FIELDS = {"M": ("nn60", "to60", "ca60", "td60"), "%": ("perf60",)}
SMALL = {"fontSize": 10, "color": C.inkD, "fontFamily": F_SS4, "lineHeight": 1.6, "marginTop": 4}
MONO9 = {"fontSize": 9, "color": C.inkD, "fontFamily": F_MONO, "marginTop": 4, "letterSpacing": ".05em"}


def has_num(s):
    return bool(s) and bool(NUM.search(str(s)))


def u_mark(text):
    """Chữ V21 có số → nhãn U·12/05 (bản lưu chưa kiểm lại, page_p7b §4.1). Mệnh đề pháp lý nêu người (bị bắt,
    khởi tố…) → U + chú thích: giữ nguyên văn V21, không thêm cáo buộc (chính sách nội dung (j)/(k))."""
    legal = bool(text) and bool(LEGAL.search(str(text)))
    if not (legal or has_num(text)):
        return None
    return [tier("U", V21_ASOF),
            h("span", {"fontSize": 8, "color": C.inkM, "fontFamily": F_MONO, "fontWeight": 400, "marginLeft": 4},
              "pháp lý: nguyên văn V21, chưa đối chiếu văn bản gốc") if legal else None]


def _ddmmyyyy(d):
    return d.strftime("%d/%m/%Y")


def _asof(a):
    """Nhãn bậc chỉ in dd/mm → mốc trước 2026 bỏ ngày khỏi nhãn (chữ của mục đã ghi đủ ngày) để khỏi đọc nhầm năm."""
    return a if a and str(a)[:4] >= "2026" else None


def _txt(s):
    """Chữ dossier; '[CẦN DATA]' viết tay → nút can_data (vermillion đậm, DESIGN §6.1)."""
    parts = str(s).split(CAN)
    out = [parts[0]]
    for p in parts[1:]:
        out += [can_data(), p]
    return [x for x in out if x != ""]


def extra_nodes(extras, pill=True):
    """(" · " pill? text tier)… — mỗi vế một nhãn bậc (và pill riêng nếu vế có status)."""
    out = []
    for x in extras or []:
        out.append(" · ")
        if pill and x.get("status"):
            out += [status_pill(x["status"]), " "]
        out += [*_txt(x["text"]), tier(x["tier"], _asof(x.get("asof")))]
    return out


def entry_nodes(e, pill=True):
    """[pill?, " ", text, tier, (" · " pill? text tier)…, ↻] cho một mục dossier {status?, text, tier, asof, extra?}."""
    if not e:
        return []
    out = []
    if pill and e.get("status"):
        out += [status_pill(e["status"]), " "]
    out += [*_txt(e["text"]), tier(e["tier"], _asof(e.get("asof")))]
    out += extra_nodes(e.get("extra"), pill)
    out.append(upd_mark())
    return out


def _d(ctx, *keys):
    cur = ctx.dossier or {}
    for k in keys:
        cur = cur.get(k) if isinstance(cur, dict) else None
        if cur is None:
            return None
    return cur


# ── ★ 12 · CATALYST CALENDAR ────────────────────────────────────────────────


def catalyst_overlay(ctx, events):
    today = ctx.today
    status = _d(ctx, "catalyst_status") or {}
    new = [dict(e, ref="", _new=True) for e in (_d(ctx, "catalyst") or []) if e.get("d") and e.get("e")]
    if not ctx.dossier:
        ctx.warn("chưa có dossier (cap_nhat_*.deep.json) — lịch chỉ tính lại số ngày, không có kết quả/sự kiện mới")
    missing = [c["d"] + "|" + c["e"] for c in events if (c["d"] + "|" + c["e"]) not in status]

    def extra(c):
        if c.get("_new"):
            return {"e_mark": tier(c["tier"], _asof(c.get("asof"))),
                    "ref": ["MỚI · dữ kiện " + " · ".join(c.get("facts") or []), *extra_nodes(c.get("extra")),
                            upd_mark()]}
        st = status.get(c["d"] + "|" + c["e"])
        res = (h("div", {"fontSize": 9, "color": C.inkD, "fontFamily": F_MONO, "marginTop": 3, "lineHeight": 1.5},
                 *entry_nodes(st)) if st else
               h("div", {"fontSize": 9, "fontFamily": F_MONO, "marginTop": 3},
                 can_data("chưa có kết quả trong dossier" if c["days"] < 0 else "chưa tới hạn — chưa có dữ kiện")))
        return {"e_mark": u_mark(c["e"]), "result": res}

    def csv(rows):
        out = []
        for c in rows:
            st = {} if c.get("_new") else (status.get(c["d"] + "|" + c["e"]) or {})
            src = c if c.get("_new") else st
            out.append({"ngay": c["d"], "su_kien": c["e"], "nguon_su_kien": "MỚI" if c.get("_new") else "V21",
                        "imp_v21": c["imp"], "mag_v21": c["mag"], "chaebol": c["ch"], "so_ngay": c["days"],
                        "trang_thai": " | ".join(s for s in [st.get("status")] + [x.get("status") for x in
                                                                                  st.get("extra") or []] if s),
                        "ket_qua": st.get("text", ""),
                        "bac": src.get("tier", ""), "asof": src.get("asof", ""), "nguon": src.get("src", "")})
        return out

    n_new = len(new)
    return {
        "today": today, "new": new, "extra": extra, "csv": csv,
        "title": ["📅 CATALYST CALENDAR · Q2/2026 → Q2/2027 (16 events V21 + %d mới)" % n_new, upd_mark()],
        "sub": "From MD section 9 · Impact + Magnitude + Claim refs · hôm nay %s (V21: 12/05/2026)" % _ddmmyyyy(today),
        "intro": h("div", {"fontSize": 9, "color": C.inkD, "fontFamily": F_MONO, "letterSpacing": ".05em",
                           "marginBottom": 8, "lineHeight": 1.6},
                   "IMP/MAGNITUDE = đánh giá V21", v21_mark(),
                   " (CỔNG v1.7 đang DỪNG — không chấm lại) · dòng dưới mỗi sự kiện V21 = kết quả tới %s + bằng chứng"
                   " + bậc · MỚI = dữ kiện facts_f6 (mảnh dossier deep) · không phải khuyến nghị" % _ddmmyyyy(today),
                   (" · thiếu kết quả: %d sự kiện" % len(missing)) if missing else None),
        "days_head": tier("E", today),
    }


# ── ★ 14 · DEEP-DIVE 24 CHAEBOL ─────────────────────────────────────────────


def _owner_name(s, n=36):
    """Tên chủ sở hữu: tên tắt cho tổ chức nhà nước tên dài; còn lại cắt ở ranh giới từ."""
    s = unicodedata.normalize("NFC", str(s))
    for full, short in OWNER_ALIAS:
        if s.lower().startswith(unicodedata.normalize("NFC", full).lower()):
            return short
    if len(s) <= n:
        return s
    return s[:n].rsplit(" ", 1)[0].rstrip(" -–,") + "…"


def _price_line(data, tickers):
    if data is None:
        return h("div", MONO9, "GIÁ ĐÓNG: ", can_data("chưa có chaebol_map_data"))
    parts, miss, last = [], [], None
    for tk in tickers:
        if not re.fullmatch(r"[A-Z0-9]{3}", tk):
            miss.append(tk)
            continue
        try:
            v = (data.last_price(tk) or {}).get("raw")
        except Exception:  # noqa: BLE001 — kho thiếu tệp của một mã không làm hỏng cả thẻ
            v = None
        if v is None or v.value is None:
            miss.append(tk)
            continue
        if last is not None and v.asof != last[1]:
            parts.append(tier(last[0], last[1]))
        kho = " (vnstore, không có vc_lk)" if str(v.src or "").startswith("vnstore") else ""   # DESIGN §6.6
        parts += [(" · " if parts else "") + tk + " " + to_locale(v.value, "en") + kho]
        last = (v.tier, v.asof)
    if last is not None:
        parts.append(tier(last[0], last[1]))
    tail = [" · " if parts else "", can_data("không có cache giá: " + " · ".join(miss))] if miss else []
    return h("div", MONO9, "GIÁ ĐÓNG: ", *parts, *tail, upd_mark() if last else None)


def _flow_li(data, tickers):
    if data is None:
        return h("li", None, "Dòng tiền 60 phiên: ", can_data("chưa có chaebol_map_data"))
    for tk in tickers:
        if not re.fullmatch(r"[A-Z0-9]{3}", tk):
            continue
        try:
            f = data.flow4(tk, 60)
        except Exception:  # noqa: BLE001
            continue
        nn = f.get("nn")
        if nn is None or nn.value is None:
            continue
        return h("li", None, "Dòng tiền 60 phiên %s→%s (%s): NN %s triệu cp" % (
            f["from"][8:10] + "/" + f["from"][5:7], f["to"][8:10] + "/" + f["to"][5:7], tk,
            sign_fixed(nn.value, 1, zfix=True)),                  # số làm tròn 0 → '0.0', không '-0.0' (VGI, KSV)
                 tier(nn.tier, nn.asof), *_td_nodes(data, tk, f), " · CN/TC ", can_data(), upd_mark())
    return h("li", None, "Dòng tiền 60 phiên: ", can_data("không mã nào có cache vc_lk"))


def _td_nodes(data, tk, f):
    """TD khớp của cùng cửa sổ: nhãn = ngày cuối CÓ bản ghi tự doanh (không phải phiên cuối giá, DESIGN §9) + độ phủ
    n_co/n; phủ < TD_MIN_COVER → [CẦN DATA] (phiên vắng không điền 0 nên tổng thưa không so được với NN)."""
    td = f.get("td")
    if td is None or td.value is None:
        return [" · TD ", can_data()]
    try:
        n_co, n = data.prop_net(tk, f["n"], kind="khop")["n_co"], f["n"]
        days = [d for d in data._prop_map(tk, "khop") if f["from"] <= d <= f["to"]]
    except Exception:  # noqa: BLE001
        return [" · TD ", can_data("không đọc được độ phủ tự doanh")]
    if not days or n_co < TD_MIN_COVER * n:
        return [" · TD (khớp) ", can_data("tự doanh thưa %d/%d phiên, không so được" % (n_co, n))]
    return [" · TD (khớp) " + sign_fixed(td.value, 1, zfix=True), tier(td.tier, max(days)), " (%d/%d phiên)" % (n_co, n)]


def _diluted_after(data, tk, pub, today):
    """Đợt phát hành riêng lẻ/chào bán (làm loãng tỷ lệ) có GDKHQ sau mốc sổ cổ đông → 'riêng lẻ dd/mm/yyyy'."""
    try:
        ev = data.capital_events(tk).value or []
    except Exception:  # noqa: BLE001
        return None
    for e in ev:
        ex, t = e.get("exright") or e.get("public_date") or "", (e.get("title") or "").lower()
        if e.get("code") == "ISS" and (e.get("ratio") or 0) > 0 and pub < ex <= today and \
                ("riêng lẻ" in t or "chào bán" in t):
            return "trước phát hành %s %s" % ("riêng lẻ" if "riêng lẻ" in t else "chào bán",
                                              _ddmmyyyy(date.fromisoformat(ex)))
    return None


def _holding_nodes(data, x, today):
    """'VPL 85.51% (31/12/2025, trước phát hành riêng lẻ 23/06/2026)' + nhãn T2 theo ngày của CHÍNH tỷ lệ đó."""
    pub = x.get("public_date") or ""
    note = [_ddmmyyyy(date.fromisoformat(pub))] if pub and not _asof(pub) else []
    dil = _diluted_after(data, x["tk"], pub, today) if data is not None and pub else None
    note += [dil] if dil else []
    return [x["tk"] + " " + x["pct"].text + (" (%s)" % ", ".join(note) if note else ""), tier("T2", _asof(pub))]


def _cross_lis(ch, tickers, data=None, today="9999"):
    if not ch:
        return []
    S = set(tickers)
    seen, edges = set(), []
    for e in ch.get("ticker_edges") or []:
        pct = e.get("pct")
        if e.get("from") in S and pct is not None and pct.value and (e["from"], e["to"]) not in seen:
            seen.add((e["from"], e["to"]))
            edges.append((e["to"] not in S, -pct.value, e["from"], e["to"], pct.text))
    edges.sort()
    out = []
    if edges:
        txt = " · ".join("%s→%s %s" % (a, b, t) for _, _, a, b, t in edges[:3])
        out.append(h("li", None, "Sở hữu mẹ–con/liên kết (vc_lk, không ngày): " + txt, tier("T2"), upd_mark()))
    owners = []
    by_pct = lambda xs: sorted(xs, key=lambda x: -x["pct"].value)      # noqa: E731 — khoản lớn nhất trước khi cắt
    for o in ch.get("owners") or []:
        hs = by_pct(x for x in o.get("holdings") or [] if x["tk"] in S)
        if hs:
            owners.append((-hs[0]["pct"].value, o, hs))
    owners.sort(key=lambda t: t[0])
    for _, o, hs in owners[:2]:
        shown = hs[:3] + by_pct(x for x in o["holdings"] if x["tk"] not in S)[:2]
        nodes = []
        for x in shown:
            nodes += ([" · "] if nodes else []) + _holding_nodes(data, x, today)
        caveat = " (sổ vendor, chưa đối chiếu CBTT)" if o.get("type") == "INDIVIDUAL" else None
        out.append(h("li", None, "Chủ sở hữu chung ≥1%: " + _owner_name(o["name"]) + ": ", *nodes, caveat,
                     upd_mark()))
    return out


def _norm(s):
    s = unicodedata.normalize("NFD", str(s or "")).replace("đ", "d").replace("Đ", "D")
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if unicodedata.category(c) != "Mn").lower())


def _claims_line(ctx, name, codes, tickers):
    """Trạng thái chấm lại (mảnh tab ★ 11 / 09). V21 trộn số hiệu hai bộ trong DEEP_INSIGHT_24.claims: một mã thuộc
    CLAIMS_54 khi `ch` của claim trùng thực thể, thuộc CLAIMS_C01_C20 khi `tk` giao TICKERS (ghi 'C08·20'); không khớp
    bộ nào → [CẦN DATA], không mượn trạng thái của claim khác cùng số hiệu."""
    c54, c20 = _d(ctx, "claims54"), _d(ctx, "claims20") or {}
    if not codes or not isinstance(c54, dict):
        return None
    v21 = ctx.v21 or {}
    ch54 = {c["id"]: c.get("ch") for c in v21.get("CLAIMS_54") or []}
    tk20 = {c["id"]: set(c.get("tk") or []) for c in v21.get("CLAIMS_C01_C20") or []}
    mine = {_norm(name)} | {_norm(x) for x in CH_EXTRA.get(name, ())}
    parts = []
    for cid in codes:
        if parts:
            parts.append(" · ")
        if _norm(ch54.get(cid)) in mine:
            label, st = cid, (c54.get(cid) or {}).get("status")
        elif tk20.get(cid, set()) & set(tickers):
            label, st = cid + "·20", (c20.get(cid) or {}).get("status")
        else:
            parts += [cid + " ", can_data("số hiệu thuộc claim của thực thể khác")]
            continue
        parts.append(h("span", {"color": STATUS_COLOR.get(st, C.inkD)}, label + " " + (st or "—")))
    return h("div", MONO9, "Chấm lại (tab ★ 11; ·20 = bộ C01–C20 tab 09): ", *parts)


def _signal_mark(flow, signal, tickers):
    """Signal V21 mà MỌI số khớp trường FLOW (FiinTrade ≤08/05) của mã được nêu — hoặc mã đầu thực thể khi câu không
    nêu mã — mang T2 theo FLOW.date như tab 08 (DESIGN §6.5); còn lại giữ U·12/05 (bản lưu chưa kiểm)."""
    tks = [t for t in _TK.findall(signal) if t in flow] or [t for t in tickers[:1] if t in flow]
    rest, dates = signal, []
    for m in _FLOW_NUM.finditer(signal):
        val = float(m.group(1))
        tol = 0.051 if "." in m.group(1) else 0.51
        hit = next((tk for tk in tks for fld in FLOW_FIELDS[m.group(2)]
                    if isinstance(flow[tk].get(fld), (int, float)) and abs(flow[tk][fld] - val) < tol), None)
        if hit is None:
            return u_mark(signal)
        dates.append((hit, flow[hit].get("date")))
        rest = rest.replace(m.group(0), " ", 1)
    if not dates or has_num(rest):
        return u_mark(signal)
    pairs = list(dict.fromkeys(dates))
    if len({d for _, d in pairs}) == 1:
        return tier("T2", pairs[0][1])
    return [tier("T2"), h("span", {"fontSize": 8, "color": C.inkM, "fontFamily": F_MONO, "marginLeft": 4},
                          "FLOW " + " · ".join("%s %s/%s" % (tk, d[8:10], d[5:7]) for tk, d in pairs))]


def _thresholds(data, action, tickers):
    """Ngưỡng giá trong ACTION V21 ('<90k', '>42k', '35-40k') → quy đổi quyền tới nay (EST, DESIGN §6.6)."""
    out = []
    for m in _TH.finditer(action):
        tks = [t for t in _TK.findall(action[:m.start()]) if t in tickers]
        if not tks:
            continue
        tk = tks[-1]
        pxs = [float(m.group(2))] if m.group(2) else [float(m.group(3)), float(m.group(4))]
        conv = [data.convert_price(tk, p * 1000, "2026-05-12") if data is not None else None for p in pxs]
        if any(v is None or v.value is None for v in conv):
            out.append([tk + " " + m.group(0) + " → ", can_data("không quy đổi được")])
            continue
        note = conv[0].note or ""
        step = note.split("bước: ", 1)[1] if "bước: " in note else ""
        new = "–".join(to_locale(js_round(v.value), "en") for v in conv)
        txt = "%s %s → %s%s (%s)" % (tk, m.group(0), m.group(1) or "", new, step) if "không có" not in step else \
            "%s %s → không đổi (không có sự kiện quyền từ 12/05)" % (tk, m.group(0))
        out.append([txt, tier(conv[0].tier, conv[0].asof)])
    return out


def deep6_overlay(ctx, d24):
    data = ctx.data
    ents = _d(ctx, "entities24") or {}
    if not ents:
        ctx.warn("dossier thiếu entities24 — deep6 live chỉ có số sống, chữ V21 giữ nguyên")
    try:
        ch = data.cross_holdings() if data is not None else None
    except Exception as exc:  # noqa: BLE001
        ctx.warn("cross_holdings lỗi: %s" % exc)
        ch = None
    flow = (ctx.v21 or {}).get("FLOW") or {}

    def ov(name):
        d, e = d24[name], ents.get(name) or {}
        w, cf = d["wyckoff"], d["cashFlow"]
        o = {"chips_mark": v21_mark(), "phase_mark": v21_mark(), "risk_mark": v21_mark()}
        if e.get("leader"):
            ld = e["leader"]
            o["leader"] = [*_txt(ld["text"]), tier(ld["tier"], _asof(ld.get("asof"))), upd_mark()]
            ext = extra_nodes(ld.get("extra"), pill=False)[1:]           # vế phụ (sở hữu, tổng nhóm) — nhãn riêng
            o["leader_note"] = h("div", MONO9, *ext, " · " if ext else None, "V21: " + d["leader"], u_mark(d["leader"]),
                                 *([" · "] + entry_nodes(e["leader_note"], pill=False) if e.get("leader_note") else []))
        else:
            o["leader"] = [d["leader"], u_mark(d["leader"]) or tier("U", V21_ASOF)]
            if e.get("leader_note"):
                o["leader_note"] = h("div", MONO9, *entry_nodes(e["leader_note"], pill=False))
        o["tickers_live"] = [_price_line(data, d["tickers"]),
                             h("div", MONO9, *entry_nodes(e["tickers"], pill=False)) if e.get("tickers") else None]
        o["claims_live"] = _claims_line(ctx, name, d["claims"], d["tickers"])
        o["signal_marks"] = {i: _signal_mark(flow, s, d["tickers"]) for i, s in enumerate(w["signals"])}
        o["signals_live"] = _flow_li(data, d["tickers"])
        o["lnst_mark"] = u_mark(cf["lnst"])
        o["capex_mark"] = u_mark(cf["capex"])
        o["detail_mark"] = u_mark(cf["detail"])
        cash = e.get("cash") or []
        o["cash_live"] = h("div", {"marginBottom": 6},
                           *[h("div", {"fontSize": 11, "color": C.ink, "lineHeight": 1.6, "fontFamily": F_SS4},
                               h("strong", {"color": C.emerald, "fontSize": 10, "fontFamily": F_MONO}, "↻ KQKD: "),
                               *entry_nodes(x)) for x in cash]) if cash else \
            h("div", {"fontSize": 11, "marginBottom": 6, "fontFamily": F_SS4},
              h("strong", {"color": C.emerald, "fontSize": 10, "fontFamily": F_MONO}, "↻ KQKD 6T/2026: "),
              can_data("chưa có dữ kiện BCTC trong sổ nguồn"))
        if e.get("detail"):
            o["detail_live"] = h("div", SMALL, *[h("div", None, *entry_nodes(x)) for x in e["detail"]])
        mm = e.get("munger") or {}
        o["munger_marks"] = {i: (h("div", {"fontSize": 10, "color": C.ink, "marginTop": 3}, *entry_nodes(mm[str(i)]))
                                 if str(i) in mm else u_mark(m)) for i, m in enumerate(d["munger"])}
        o["munger_head"] = h("span", {"fontSize": 8, "letterSpacing": ".05em", "color": C.inkM, "fontWeight": 400,
                                      "marginLeft": 8},
                             "ĐẠT = kịch bản đã xảy ra · BỊ BÁC = tiền đề/kịch bản bị dữ kiện bác")
        il = e.get("interlocks") or {}
        o["interlock_marks"] = {i: (([" "] if il[str(i)].get("status") else [" — "]) + entry_nodes(il[str(i)])
                                    if str(i) in il else u_mark(x)) for i, x in enumerate(d["interlocks"])}
        o["interlocks_live"] = _cross_lis(ch, d["tickers"], data, ctx.today.isoformat())
        if e.get("risk"):
            o["risk_live"] = h("div", SMALL, *entry_nodes(e["risk"]))
        th = _thresholds(data, d["action"], d["tickers"])
        o["action_mark"] = [v21_mark(), h("span", {"fontSize": 9, "color": C.inkM, "fontWeight": 400,
                                                   "fontFamily": F_MONO},
                                          " · bản lưu — action cần kiểm chứng; >5% NAV → Synthesis L1+L2+L3")]
        rows = [h("div", None, "Quy đổi quyền ngưỡng V21 (không phải khuyến nghị mới): ", *x) for x in th]
        if e.get("action"):
            rows.append(h("div", None, *entry_nodes(e["action"])))
        if rows:
            o["action_live"] = h("div", SMALL, *rows)
        return o

    def csv():
        out = []
        for name, d in d24.items():
            e = ents.get(name) or {}
            cash = e.get("cash") or []
            out.append({"thuc_the": name, "axis_v21": d["axis"], "tier_v21": d["tier"], "leader_v21": d["leader"],
                        "leader_moi": (e.get("leader") or {}).get("text", ""),
                        "leader_bac": (e.get("leader") or {}).get("tier", ""),
                        "kqkd_moi": " | ".join(x["text"] for x in cash), "kqkd_bac": " | ".join(x["tier"] for x in cash),
                        "pha_v21": d["wyckoff"]["phase"], "action_v21": d["action"],
                        "munger_danh_dau": " | ".join("%s:%s" % (k, v.get("status", "")) for k, v in
                                                     (e.get("munger") or {}).items()),
                        "nguon": " | ".join(sorted({x["src"] for x in cash}))})
        return out

    today = ctx.today
    return {
        "entity": ov, "csv": csv,
        "sub": "From MD v3.0 section 2+3+4 · 24 entries full 6-panel analysis · Filter axis × tier · live %s" %
               _ddmmyyyy(today),
        "intro": h("div", {"fontSize": 9, "color": C.inkD, "fontFamily": F_MONO, "letterSpacing": ".05em",
                           "marginBottom": 10, "lineHeight": 1.6},
                   "Live %s · WYCKOFF / AXIS·TIER / KEY RISK / ACTION = bản lưu V21·12/05 (CỔNG v1.7 DỪNG — không chấm "
                   "lại) · chữ V21 có số mang nhãn U · ↻ = viết lại theo dữ kiện (mảnh dossier deep) · dòng tiền sau "
                   "08/05 chỉ NN + TD là số thật" % _ddmmyyyy(today)),
    }
