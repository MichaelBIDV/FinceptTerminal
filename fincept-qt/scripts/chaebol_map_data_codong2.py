"""
chaebol_map_data_codong2, lớp dữ liệu CHỦ THỂ (P1 data_owner) cho tab codong v2 (mode live, 109 mã).

Hợp đồng: chaebol_map_spec/codong_v2_spec.md §2 (kiểu V + gói _env), §4 (API). Chỉ ĐỌC kho (vc_lk, vc_lk_lichsu,
lk_hoso, fft_langkinh, fft_cauchuyen, fund_holdings, smart_money/history, owner_intent, nq68_nq79, facts_f*), qua các
hàm đọc của lớp dữ liệu cũ; không mạng, không ghi tệp. Bậc gán theo nguồn THẬT (§2.2), thiếu số → can_data(lý do).
Phần §4.7 (sự kiện vốn, ĐHCĐ, dòng thời gian, nguồn ý đồ) và §4.8 (bảng tổng) nằm ở chaebol_map_data_codong2_ydo,
re-export ở cuối tệp này. Không nhãn mua/bán, không chấm lại pha/stance (CỔNG v1.7 DỪNG).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

from chaebol_map_data_nen import *  # noqa: F401,F403
from chaebol_map_data_nen import _finite, _last, _memo, _sig
from chaebol_map_data_gia import price_history, shares_out
from chaebol_map_data_codong2_gia import mult_at, shares_at
from chaebol_map_data_langkinh import basket, lk_atom, lk_hoso, tv30
from chaebol_map_data_vciq import CODONG_48, universe

HIERARCHY_TEXT = "Thứ bậc khi tín hiệu xung đột (v1.7): Δ cổ đông thật (SS-T3, file Toàn Vũ) > hệ số k > proxy giá/KL (FFT)"
FFT_MISS = ("FPT", "VCB", "MBB", "HPG", "CTG")
FFT_MISS_TEXT = ("§6.4: proxy FFT đã bỏ sót phân phối ở FPT, VCB, MBB, HPG, CTG; FFT im lặng không có nghĩa là không "
                 "phân phối")
ESOP_NOTE = "ESOP và chia tách làm phồng số cổ đông; đọc Δ cổ đông cùng sự kiện vốn cùng kỳ"
THIN_MAX_QS = 4                 # ≤4 mốc quan sát → "Pillar I mỏng"
NET_BASE_MONTHS = 12            # mốc % sở hữu trước cửa sổ cũ hơn d0 quá 12 tháng → không làm % đầu kỳ (gộp pha loãng)
FRESH_DAYS = 183                # dòng cổ đông "mới" = publicDate ≥ kỳ mới nhất − 183 ngày
MARKER_MIN_PCT = 0.1            # ngưỡng % vốn để thành marker chart (RD dùng)
ORG_ALIAS_GLOBAL = {"private equity new market ii k/s": "bankinvest private equity new markets ii k/s"}
ORG_ALIAS_TK: dict = {}         # {(tk, norm_name): norm_name đích}; bổ sung tay, mỗi mục kèm chú thích nguồn
GROUP_SEEDS = (
    {"group": "Nhóm Phạm Nhật Vượng", "tks": ("VIC", "VHM", "VRE", "VPL"), "members": (
        {"pid": 1497, "tier": T2, "src": "vc_lk/VIC/insider-transaction traderPersonId 1497"},
        {"all": ("tập đoàn đầu tư việt nam",), "tier": T2, "src": "fft_cauchuyen.ma.VIC.chu_the"},
        {"all": ("vinspeed",), "tier": T2, "src": "fft_cauchuyen.ma.VIC.chu_the"},
        {"all": ("vinenergo",), "tier": T2, "src": "fft_cauchuyen.ma.VIC.chu_the"},
        {"all": ("hưng long", "bất động sản"), "tier": T1,
         "src": "fft_cauchuyen.ma.VIC.thau_tom (BC quản trị 2025 tr.19-21)"})},
    {"group": "Nhóm Nguyễn Đăng Quang (Masan)", "tks": ("MSN", "MCH", "MSR"), "members": (
        {"all": ("masan",), "tier": T2, "src": "vc_lk shareholder/insider (pháp nhân Masan)"},
        {"all": ("hoa hướng dương",), "tier": T3, "src": "fft_cauchuyen.ma.MSN.chu_the (21_Chaebol)"},
        {"name": "nguyễn đăng quang", "tier": T3, "src": "fft_cauchuyen.ma.MSN.chu_the"},
        {"name": "nguyễn hoàng yến", "tier": T3, "src": "fft_cauchuyen.ma.MSN.chu_the (MasterPlan)"})},
)
WHY_NO_VC = "chưa nạp vc_lk"
WHY_NO_LK = "chưa có lk_hoso"
WHY_NO_TV = "Vietcap không có số cổ đông; Toàn Vũ chỉ phủ 30 mã; chờ OCR BCTN"

__all__ = [
    "HIERARCHY_TEXT", "FFT_MISS", "FFT_MISS_TEXT", "ESOP_NOTE", "THIN_MAX_QS", "NET_BASE_MONTHS", "FRESH_DAYS",
    "MARKER_MIN_PCT", "ORG_ALIAS_GLOBAL", "ORG_ALIAS_TK", "GROUP_SEEDS", "WHY_NO_VC", "WHY_NO_LK", "WHY_NO_TV",
    "universe_groups", "cong_line", "chu_the_label", "sigma_view", "norm_name", "owner_of", "chain_aliases",
    "group_map", "insider_rows", "pair_transfers", "ownership_ladder", "insider_net", "insider_yearly", "exec_stats",
    "insider_windows", "anchor_dates", "holder_table", "holder_delta", "structure_bars", "relationship_view",
    "fund_view", "codong_full", "codong_delta", "match_flip",
    "ISS_KIND", "capital_actions", "agm_events", "timeline", "intent_sources", "SUMMARY_COLS", "summary_row",
    "summary_rows",
]


# ───────────────────────────── tiện ích chung ─────────────────────────────

def _env(ok, why=None, tier=None, asof=None, src=None, note=None, **kw) -> dict:
    return {"ok": ok, "why": why, "tier": tier, "asof": asof, "src": src, "note": note, **kw}


def _has_vc(tk: str) -> bool:
    return (vc_dir() / tk / "price-history.json").exists()


def _why_vc(tk: str, ep: str) -> str:
    return WHY_NO_VC if not _has_vc(tk) else f"vc_lk chưa có {ep} cho mã này"


def _int(x):
    return int(x) if _finite(x) else None


def _sgn(x) -> int:
    return (x > 0) - (x < 0)


def _vq(x, tier, asof, src, note=None, unit="cp") -> V:
    return V(x, js_locale(x, 0), tier, asof, src, note, unit)


def _vp(x, tier, asof, src, note=None, unit="%") -> V:
    return V(x, js_fixed(x, 2) + ("%" if unit == "%" else ""), tier, asof, src, note, unit)


def _vn(n, tier, asof, src, note=None) -> V:
    return V(n, js_locale(n, 0), tier, asof, src, note, None)


def _month_end(ky: str) -> str:
    y, m = int(ky[:4]), int(ky[5:7])
    return (date(y + m // 12, m % 12 + 1, 1) - timedelta(days=1)).isoformat()


def _days_before(d: str, n: int) -> str:
    return (date.fromisoformat(d) - timedelta(days=n)).isoformat()


def _ts_info(tk: str):
    """(ts_start, Cols | None): ngày đầu có totalShares trong price-history vc_lk (vnstore → None)."""
    ph = price_history(tk)
    if ph is None or not len(ph) or not str(getattr(ph, "base", "")).startswith("vc_lk"):
        return None, None
    S = ph.col("totalShares")
    i0 = next((i for i, s in enumerate(S) if s), None)
    return (ph.dates[i0] if i0 is not None else None), ph


def _ts_at(ph, d):
    if ph is None or not d:
        return None
    return _last(ph.col("totalShares"), ph.at(d))[0]


def _fft_langkinh() -> dict:
    return read_json(bridge() / "data" / "fft_langkinh.json", quiet=True) or {}


def _cauchuyen() -> dict:
    return read_json(bridge() / "fft_cauchuyen.json", quiet=True) or {}


def _src_text(n) -> str | None:
    if isinstance(n, list):
        return " | ".join(str(x) for x in n) or None
    return str(n) if n else None


# ───────────────────────────── 4.2 vũ trụ, CỔNG, chủ thể, định giá ─────────────────────────────

def universe_groups(v21: dict) -> dict:
    """Vũ trụ 109 mã chia A (VN30 hiện hành), B (48 mã codong ngoài VN30), C (phần còn lại)."""
    b = basket("VN30")
    vn30 = list(b.value or [])
    uni = universe(v21, vn30)
    a = sorted(set(uni) & set(vn30))
    bb = sorted((set(CODONG_48) & set(uni)) - set(a))
    c = sorted(set(uni) - set(a) - set(bb))
    grp = {**{t: "A" for t in a}, **{t: "B" for t in bb}, **{t: "C" for t in c}}
    order = a + bb + c
    lk_dir = bridge() / "data" / "lk_hoso"
    return {"order": order, "A": a, "B": bb, "C": c, "grp": grp, "tv30": list(tv30()),
            "has_vc": {t: _has_vc(t) for t in order}, "has_lk": {t: (lk_dir / f"{t}.json").exists() for t in order},
            "vn30_asof": b.asof}


def cong_line(tk: str) -> dict:
    """Dòng CỔNG của MÃ nguyên văn (lk_hoso.cong.dong). Không dùng CỔNG thị trường làm dự phòng."""
    c = (lk_hoso(tk) or {}).get("cong") or {}
    txt = c.get("dong")
    if not txt:
        return {"text": "CỔNG: [CẦN DATA]", "as_of": None, "src": None, "stop": True}
    asof = str(c["as_of"]).replace("T", " ")[:16] if c.get("as_of") else None
    return {"text": txt, "as_of": asof, "src": f"lk_hoso/{tk}.json#cong.dong",
            "stop": "[CẦN DATA" in txt or "DỪNG" in txt or bool(c.get("dung"))}


def chu_the_label(tk: str) -> dict:
    """Nhãn chủ thể theo bậc của TỪNG mã (fft_langkinh.ma.<tk>.chu_the), nhãn tĩnh; giữ nguyên văn khẳng định."""
    ct = ((_fft_langkinh().get("ma") or {}).get(tk) or {}).get("chu_the") or {}
    src = f"fft_langkinh.ma.{tk}.chu_the"
    nhan = (V(ct["nhan"], ct["nhan"], ct.get("bac"), iso(ct.get("ngay")), src, "nhãn tĩnh, chưa chấm lại kỳ mới")
            if ct.get("nhan") else can_data("fft_langkinh chưa có nhãn chủ thể cho mã này", src))
    kd = [{"nguon": k.get("nguon"), "nhan": k.get("nhan"), "nguyen_van": k.get("nguyen_van"), "bac": k.get("bac")}
          for k in ct.get("khang_dinh") or [] if isinstance(k, dict)]
    return {"nhan": nhan, "xung_dot": bool(ct.get("xung_dot")), "khang_dinh": kd, "playbook": ct.get("playbook")}


def sigma_view(tk: str) -> dict:
    """Định giá σ theo ĐÚNG chỉ số của mã (lk_hoso.sigma.chi_so); bậc atom giữ nguyên."""
    hs = lk_hoso(tk)
    if hs is None:
        return _env(False, WHY_NO_LK)
    s = hs.get("sigma") or {}
    cs = s.get("chi_so")
    src = f"lk_hoso/{tk}.sigma"
    if not s or not s.get("dung_duoc") or cs not in ("pe", "pb"):
        return _env(False, s.get("g") or "lk_hoso.sigma không dùng được cho mã này", src=src)
    atoms = {k: lk_atom(s.get(k), f"{src}.{k}") for k in ("x", "mu", "sd", "z")}
    return _env(True, tier=atoms["z"].tier, asof=atoms["x"].asof, src=src, note=s.get("g"), chi_so=cs,
                label={"pe": "P/E", "pb": "P/B"}[cs], **atoms)


# ───────────────────────────── 4.3 chuẩn hoá chủ thể, nhóm ─────────────────────────────

_LEGAL = (("công ty cổ phần", "ctcp"), ("công ty tnhh một thành viên", "cty tnhh mtv"), ("công ty tnhh", "cty tnhh"),
          ("công ty", "cty"), ("joint stock company", "jsc"), ("pte. ltd", "pte ltd"), ("limited", "ltd"))
_PUNCT = re.compile(r"[.,;:\"']")


def norm_name(s: str) -> str:
    """NFC → thường → bỏ . , ; : " ' → gộp khoảng trắng → rút gọn dạng pháp lý. Giữ dấu tiếng Việt; idempotent."""
    t = _PUNCT.sub(" ", unicodedata.normalize("NFC", str(s or "")).lower())
    t = re.sub(r"\s+", " ", t).strip()
    for a, b in _LEGAL:
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t).strip()


def _raw_insider(tk: str) -> list | None:
    _, rows = vc(tk, "insider-transaction")
    return rows if isinstance(rows, list) else None


def _static_alias(tk: str, n: str):
    if (tk, n) in ORG_ALIAS_TK:
        return ORG_ALIAS_TK[(tk, n)], "tk"
    if n in ORG_ALIAS_GLOBAL:
        return ORG_ALIAS_GLOBAL[n], "global"
    return n, None


def _rdate(r: dict) -> str:
    return iso(r.get("endDate")) or iso(r.get("startDate")) or iso(r.get("publicDate")) or ""


def chain_aliases(tk: str) -> dict:
    """Luật chuỗi (EST): tổ chức X có dòng ĐẦU shareBeforeTrade == shareAfterTrade dòng CUỐI của Y (≥1,000,000),
    X sau Y → gộp X vào khoá của Y (khoá = tên xuất hiện sớm nhất trong chuỗi). → {norm X: norm khoá}."""
    p = vc_dir() / tk / "insider-transaction.json"
    return _memo(("cd2o", "chain_aliases", tk), (_sig(p),), lambda: _chain_build(tk))


def _chain_build(tk: str) -> dict:
    by: dict = {}
    for r in _raw_insider(tk) or []:
        if r.get("eventCode") != "DDINS" or r.get("tradeStatusVi") != "Đã thực hiện xong" or not r.get("traderOrganNameVi"):
            continue
        by.setdefault(_static_alias(tk, norm_name(r["traderOrganNameVi"]))[0], []).append(r)
    span = {n: (min(rs, key=_rdate), max(rs, key=_rdate)) for n, rs in by.items()}
    link = {}
    for x, (fx, _) in span.items():
        bx = fx.get("shareBeforeTrade")
        if not _finite(bx) or bx < 1_000_000:
            continue
        ys = sorted(y for y, (_, ly) in span.items() if y != x and ly.get("shareAfterTrade") == bx
                    and _rdate(fx) > _rdate(ly))
        if ys:
            link[x] = ys[0]
    out = {}
    for x in link:
        root, seen = x, set()
        while root in link and root not in seen:
            seen.add(root)
            root = link[root]
        out[x] = root
    return out


def _pid_index(tk: str) -> dict:
    out = {}
    for r in _raw_insider(tk) or []:
        if r.get("traderPersonId") and r.get("traderNameVi"):
            out.setdefault(norm_name(r["traderNameVi"]), int(r["traderPersonId"]))
    return out


def _person(name, pid) -> dict:
    n = norm_name(name)
    return {"key": f"p:{int(pid)}" if pid else f"n:{n}", "name": name, "kind": "person",
            "pid": int(pid) if pid else None, "alias": None}


def _org(tk: str, name) -> dict:
    n0 = norm_name(name)
    n, rule = _static_alias(tk, n0)
    if rule is None and n0 in chain_aliases(tk):
        n, rule = chain_aliases(tk)[n0], "chain"
    alias = {"from": n0, "rule": rule, "tier": EST if rule == "chain" else T2} if rule else None
    return {"key": f"o:{n}", "name": name, "kind": "org", "pid": None, "alias": alias}


def owner_of(row: dict, tk: str) -> dict:
    """Khoá chủ thể của dòng insider: DDINS → tổ chức (alias tk → global → chuỗi); DDIND/DDRP → người (personId)."""
    if row.get("eventCode") == "DDINS" and row.get("traderOrganNameVi"):
        return _org(tk, row["traderOrganNameVi"])
    if row.get("traderNameVi") or row.get("traderPersonId"):
        return _person(row.get("traderNameVi") or "", row.get("traderPersonId"))
    if row.get("traderOrganNameVi"):
        return _org(tk, row["traderOrganNameVi"])
    return {"key": f"u:{row.get('id')}", "name": None, "kind": "org", "pid": None, "alias": None}


def _related(row: dict, pidx: dict) -> dict | None:
    rel = row.get("relativeNameVi")
    if not rel or row.get("eventCode") != "DDRP":
        return None
    return _person(rel, pidx.get(norm_name(rel)))


def _seed_match(tk: str, o: dict) -> dict | None:
    nm = o["key"][2:] if o["kind"] == "org" else norm_name(o["name"])
    for sd in GROUP_SEEDS:
        if tk not in sd["tks"]:
            continue
        for m in sd["members"]:
            hit = (("pid" in m and o["pid"] == m["pid"]) or ("all" in m and all(s in nm for s in m["all"]))
                   or ("name" in m and o["kind"] == "person" and nm == m["name"]))
            if hit:
                return {"group": sd["group"], "tier": m["tier"], "src": m["src"], "rule": "seed"}
    return None


def group_map(tk: str) -> dict:
    """owner key → {group, tier, src, rule}: hạt giống GROUP_SEEDS rồi luật DDRP (người liên quan)."""
    p = vc_dir() / tk / "insider-transaction.json"
    return _memo(("cd2o", "group_map", tk), (_sig(p),), lambda: _group_build(tk))


def _group_build(tk: str) -> dict:
    raw, pidx, owners = _raw_insider(tk) or [], _pid_index(tk), {}
    for r in raw:
        for o in (owner_of(r, tk), _related(r, pidx)):
            if o:
                owners.setdefault(o["key"], o)
    seeds = {k: g for k, o in owners.items() if (g := _seed_match(tk, o))}
    out = dict(seeds)
    for r in raw:
        rel = _related(r, pidx)
        me = owner_of(r, tk)
        if not rel or me["key"] in seeds:
            continue
        rg = seeds.get(rel["key"])
        out[me["key"]] = {"group": rg["group"] if rg else f"Người liên quan của {rel['name']}", "tier": T2,
                          "src": f"vc_lk/{tk}/insider-transaction relativeNameVi", "rule": "ddrp"}
    return out


def _owner_key_for_name(tk: str, name: str, kind: str) -> dict:
    """Khoá chủ thể cho một TÊN (dòng sổ cổ đông): người → personId tra từ insider nếu có."""
    if kind == "person":
        return _person(name, _pid_index(tk).get(norm_name(name)))
    return _org(tk, name)


# ───────────────────────────── 4.4 dòng nội bộ, cặp chuyển giao ─────────────────────────────

_STATUS = {"Đã thực hiện xong": "da_xong", "Đăng ký": "dang_ky", "Đăng kí": "dang_ky",
           "Không thực hiện được": "khong_thuc_hien"}
_SIDE = {"B": 1, "S": -1}


def _flags(st: str, side: int, acq, bef, aft, own, end, today: str):
    flags, valid = [], True
    if st == "dang_ky":
        flags.append("dem_dang_ky")
        bef = aft = own = None
        if end and end < today:
            flags.append("qua_han")
    if st == "da_xong":
        if not acq:
            flags.append("acq_0")
            valid = False
        if side and ((acq or 0) * side < 0 or (bef is not None and aft is not None and _sgn(aft - bef) != side)):
            flags.append("mau_thuan")
            valid = False
    if st != "dang_ky" and (own is None or (own == 0 and (aft or 0) > 0)):
        flags.append("own_khong_dung")
        own = None
    return flags, valid, bef, aft, own


def _clean_row(tk, r, today, ctx) -> dict:
    st = _STATUS.get(r.get("tradeStatusVi"), "khac")
    side = _SIDE.get(r.get("actionTypeCode"), 0)
    acq, bef, aft = _int(r.get("shareAcquire")), _int(r.get("shareBeforeTrade")), _int(r.get("shareAfterTrade"))
    own0 = r.get("ownershipAfterTrade")
    own = round(own0 * 100, 6) if _finite(own0) else None
    pub, start, end = iso(r.get("publicDate")), iso(r.get("startDate")), iso(r.get("endDate"))
    d = end or start or pub
    flags, valid, bef, aft, own = _flags(st, side, acq, bef, aft, own, end, today)
    o = owner_of(r, tk)
    pre = ctx["ts_start"] is None or (d or "") < ctx["ts_start"]
    cap, cap_t = _cap_at(tk, ctx["ph"], d, aft, own, infer=True) if acq else (None, None)
    return {"id": str(r.get("id")), "public": pub, "start": start, "end": end, "date": d, "code": r.get("eventCode"),
            "side": side, "status": st, "owner": o, "related": _related(r, ctx["pidx"]),
            "group": (ctx["groups"].get(o["key"]) or {}).get("group"), "register": _int(r.get("shareRegister")),
            "acquire": acq, "before": bef, "after": aft, "own_after": own, "valid": valid, "flags": flags,
            "pair": None, "acq_now": abs(acq) * mult_at(tk, d) if acq else None, "acq_tier": UNV if pre else EST,
            "acq_pct": abs(acq) / cap * 100 if cap else None, "acq_pct_tier": cap_t,
            "title": r.get("eventTitleVi"), "url": r.get("sourceUrlVi") or None}


def _span(r: dict):
    lo = r["start"] or r["end"] or r["public"] or ""
    hi = r["end"] or r["start"] or r["public"] or ""
    return (lo, hi) if lo <= hi else (hi, lo)


def _gap(a: str, b: str) -> int:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def _match_pairs(rows: list) -> list:
    """Ghép tham lam theo ngày tăng dần của dòng bán: |acquire| bằng nhau, ngược chiều, chủ thể khác, khoảng ngày
    giao nhau; ưu tiên cùng nhóm rồi lệch ngày nhỏ nhất. → [(dòng bán, dòng mua)]."""
    ok = [r for r in rows if r["status"] == "da_xong" and r["valid"] and r["side"] and r["acquire"]]
    buys, used, out = [r for r in ok if r["side"] > 0], set(), []
    for s in sorted((r for r in ok if r["side"] < 0), key=lambda r: (r["date"], r["id"])):
        q, (s0, s1) = abs(s["acquire"]), _span(s)
        opts = [b for b in buys if b["id"] not in used and abs(b["acquire"]) == q
                and b["owner"]["key"] != s["owner"]["key"] and _span(b)[0] <= s1 and s0 <= _span(b)[1]]
        if not opts:
            continue
        opts.sort(key=lambda b: (not (s["group"] and b["group"] == s["group"]), _gap(s["date"], b["date"]), b["id"]))
        used.add(opts[0]["id"])
        out.append((s, opts[0]))
    return out


def _insider(tk: str, today: str) -> dict:
    p, ph = vc_dir() / tk / "insider-transaction.json", vc_dir() / tk / "price-history.json"
    return _memo(("cd2o", "insider", tk, today), (_sig(p), _sig(ph)), lambda: _insider_build(tk, today))


def _insider_build(tk: str, today: str) -> dict:
    raw = _raw_insider(tk)
    if raw is None:
        return {"ok": False, "why": _why_vc(tk, "insider-transaction"), "rows": [], "pairs": [], "ts_start": None}
    ts_start, ph = _ts_info(tk)
    ctx = {"ts_start": ts_start, "pidx": _pid_index(tk), "groups": group_map(tk), "ph": ph}
    rows = sorted((_clean_row(tk, r, today, ctx) for r in raw), key=lambda r: (r["date"] or "", r["id"]))
    pairs = _match_pairs(rows)
    kinds = {}
    for n, (s, b) in enumerate(pairs, 1):
        kind = "noi_nhom" if s["group"] and s["group"] == b["group"] else "cap_khop"
        kinds[s["id"]] = {"id": f"P{n}", "kind": kind, "other": b["id"]}
        kinds[b["id"]] = {"id": f"P{n}", "kind": kind, "other": s["id"]}
    rows = [{**r, "pair": kinds.get(r["id"])} for r in rows]
    meta = vc(tk, "insider-transaction")[0] or {}
    return {"ok": True, "why": None, "rows": rows, "pairs": [(kinds[s["id"]], s["id"], b["id"]) for s, b in pairs],
            "ts_start": ts_start, "ph": ph, "asof": meta.get("du_lieu_toi")}


def insider_rows(tk: str, today: str) -> dict:
    """Dòng insider đã làm sạch (đệm đăng ký, acquire 0, mâu thuẫn dấu, % sở hữu sai) + cặp chuyển giao."""
    b = _insider(tk, today)
    src = f"vc_lk/{tk}/insider-transaction"
    if not b["ok"]:
        return _env(False, b["why"], src=src, rows=[], n_raw=0, n_done=0, n_reg=0, n_not=0, n_bad=0, ts_start=None)
    rows = b["rows"]
    cnt = {s: sum(1 for r in rows if r["status"] == s) for s in ("da_xong", "dang_ky", "khong_thuc_hien")}
    return _env(True, tier=T2, asof=b["asof"], src=src, rows=rows, n_raw=len(rows), n_done=cnt["da_xong"],
                n_reg=cnt["dang_ky"], n_not=cnt["khong_thuc_hien"], n_bad=sum(1 for r in rows if not r["valid"]),
                ts_start=b["ts_start"])


def _cap_at(tk: str, ph, d, after, own, infer: bool = False) -> tuple:
    """(số cp lưu hành tại ngày d, bậc) cho % vốn của MỘT giao dịch: totalShares vendor phiên cuối ≤ d (EST) → suy từ
    số cp và % sở hữu sau giao dịch (EST) → infer: chuỗi số cp P2 (trước ts_start suy từ bước giá, U); không có →
    (None, None). Cùng mẫu số cho dòng nội bộ và cặp chuyển giao."""
    ts = _ts_at(ph, d)
    if ts:
        return ts, EST
    if own and after:
        return after * 100 / own, EST
    if infer:
        s, t = shares_at(tk, d)
        return (s, UNV if t == UNV else EST) if s else (None, None)
    return None, None


def _pair_pct(tk: str, ph, q, d, s: dict) -> V:
    cap, t = _cap_at(tk, ph, d, s.get("after"), s.get("own_after"))
    if cap:
        why = "qty ÷ totalShares tại ngày" if _ts_at(ph, d) else "qty ÷ số cp suy từ % sở hữu sau giao dịch"
        return _vp(q / cap * 100, t, d, why)
    return can_data("thiếu totalShares tại ngày chuyển giao", "vc_lk price-history.totalShares", d)


def pair_transfers(tk: str, today: str) -> dict:
    """Cặp chuyển giao (cùng |KL|, ngược chiều, cửa sổ ngày giao nhau): nội nhóm hoặc cặp khớp; + bằng chứng thau_tom."""
    b = _insider(tk, today)
    src = f"vc_lk/{tk}/insider-transaction (ghép cặp)"
    if not b["ok"]:
        return _env(False, b["why"], tier=EST, src=src, pairs=[], evidence=[], n_rows_paired=0)
    by_id = {r["id"]: r for r in b["rows"]}
    out = []
    for info, sid, bid in b["pairs"]:
        s, bu = by_id[sid], by_id[bid]
        d0, d1 = sorted((s["date"], bu["date"]))
        q = abs(s["acquire"])
        pre = b["ts_start"] is None or d1 < b["ts_start"]
        out.append({"id": info["id"], "kind": info["kind"], "qty": q,
                    "qty_now": _vq(q * mult_at(tk, d1), UNV if pre else EST, d1, src, "quy về số cp hiện hành"),
                    "pct": _pair_pct(tk, b["ph"], q, d1, s), "from": s["owner"], "to": bu["owner"],
                    "from_group": s["group"], "to_group": bu["group"], "date0": d0, "date1": d1, "rows": [sid, bid]})
    tt = ((_cauchuyen().get("ma") or {}).get(tk) or {}).get("thau_tom")
    ev = ([{"text": tt.get("text"), "tier": tt.get("bac"), "src": _src_text(tt.get("nguon"))}]
          if isinstance(tt, dict) and tt.get("text") and tt.get("bac") else [])
    return _env(True, tier=EST, asof=b["asof"], src=src, pairs=out, evidence=ev, n_rows_paired=2 * len(out))


def ownership_ladder(tk: str, today: str, n: int = 6) -> dict:
    """Bậc thang % sở hữu từng chủ thể (dòng da_xong hợp lệ có % sau giao dịch) + dải nhóm (tổng % lần cuối biết)."""
    b = _insider(tk, today)
    rule = "6 chủ thể có biên % sở hữu lớn nhất, ≥2 bản ghi hợp lệ; % sở hữu không bị cổ tức cổ phiếu làm lệch"
    if not b["ok"]:
        return _env(False, b["why"], tier=T2, owners=[], groups=[], rule=rule)
    src = f"vc_lk/{tk}/insider-transaction.ownershipAfterTrade"
    pts: dict = {}
    for r in b["rows"]:
        if r["status"] == "da_xong" and r["valid"] and r["own_after"] is not None:
            pts.setdefault(r["owner"]["key"], (r, []))[1].append(
                {"date": r["date"], "pct": r["own_after"], "after": r["after"], "side": r["side"],
                 "after_now": r["after"] * mult_at(tk, r["date"]) if r["after"] is not None else None,
                 "transfer": r["pair"] is not None, "row": r["id"]})
    owners = []
    for key, (r0, p) in pts.items():
        if len(p) < 2:
            continue
        ps = [x["pct"] for x in p]
        owners.append({"key": key, "name": r0["owner"]["name"], "group": r0["group"], "kind": r0["owner"]["kind"],
                       "points": p, "pct_first": _vp(ps[0], T2, p[0]["date"], src),
                       "pct_last": _vp(ps[-1], T2, p[-1]["date"], src), "span": max(ps) - min(ps), "n": len(p)})
    owners.sort(key=lambda o: (-o["span"], str(o["name"])))
    return _env(True, tier=T2, asof=b["asof"], src=src, owners=owners[:n], groups=_ladder_groups(pts), rule=rule)


def _ladder_groups(pts: dict) -> list:
    by: dict = {}
    for key, (r0, p) in pts.items():
        if r0["group"]:
            by.setdefault(r0["group"], {})[key] = p
    out = []
    for g, mem in sorted(by.items()):
        days = sorted({x["date"] for p in mem.values() for x in p})
        series = []
        for d in days:
            last = [next((x["pct"] for x in reversed(p) if x["date"] <= d), None) for p in mem.values()]
            series.append({"date": d, "pct_sum": round(sum(x for x in last if x is not None), 6)})
        out.append({"group": g, "members": sorted(mem), "points": series,
                    "pct_last": _vp(series[-1]["pct_sum"], EST, days[-1], "Σ % lần cuối biết của thành viên")})
    return out


def _done(b: dict) -> list:
    return [r for r in b["rows"] if r["status"] == "da_xong" and r["valid"]]


def _ent_key(r: dict, by: str):
    return (r["group"], r["group"]) if by == "group" and r["group"] else (r["owner"]["key"], r["owner"]["name"])


def _pct_before(r_first: dict, ph) -> tuple:
    """% sở hữu ngay trước dòng đầu trong cửa sổ (chủ thể chưa có mốc nào trước cửa sổ): own_after − |KL| ÷ số cp tại
    ngày (totalShares, hoặc suy từ số cp và % sau giao dịch) × 100, EST; thiếu số cp → own_after."""
    cap, _ = _cap_at(None, ph, r_first["date"], r_first["after"], r_first["own_after"])
    base = r_first["own_after"] - (r_first["acquire"] or 0) / cap * 100 if cap else r_first["own_after"]
    return max(base, 0.0), EST


def _member_pct(rs: list, d0: str, d1: str, ph, so, cut: str) -> dict | None:
    """Một chủ thể (dòng da_xong hợp lệ, tăng dần ngày). % sau = own_after lần cuối biết ≤ d1 (ngày của chính dòng đó).
    Không giao dịch trong cửa sổ: % trước = % sau, Δ 0. Có giao dịch: % trước = own_after lần cuối < d0 nếu không cũ
    hơn `cut`; không có mốc trước → suy từ dòng đầu (E); mốc cũ hơn `cut` → không dùng (stale), Δ = Σ cp giao dịch
    trong cửa sổ (quy đổi) ÷ số cp hiện hành (E). Không có % nào ≤ d1 → None."""
    known = [r for r in rs if r["own_after"] is not None and r["date"] <= d1]
    if not known:
        return None
    last = known[-1]
    m = {"after": last["own_after"], "after_d": last["date"], "stale": None}
    win = [r for r in known if r["date"] >= d0]
    if not win:
        return {**m, "before": last["own_after"], "before_d": last["date"], "before_t": T2, "delta": 0.0}
    prev = [r for r in known if r["date"] < d0]
    if prev and prev[-1]["date"] >= cut:
        p = prev[-1]
        return {**m, "before": p["own_after"], "before_d": p["date"], "before_t": T2,
                "delta": last["own_after"] - p["own_after"]}
    if not prev:
        x, t = _pct_before(win[0], ph)
        return {**m, "before": x, "before_d": win[0]["date"], "before_t": t, "delta": last["own_after"] - x}
    cp = sum(r["side"] * (r["acq_now"] or 0) for r in rs if d0 <= r["date"] <= d1)
    return {**m, "before": None, "before_d": prev[-1]["date"], "before_t": None, "stale": prev[-1]["date"],
            "delta": cp / so.value * 100 if not so.can and so.value else None}


def _ent_row(key, name, ms: list, cp: float, cp_d, src: str) -> dict:
    """Một thực thể (một chủ thể hoặc cả nhóm) từ các thành viên _member_pct; số tổng nhiều thành viên mang EST."""
    one, after_d = len(ms) == 1, max(m["after_d"] for m in ms)
    stale = [m["stale"] for m in ms if m["stale"]]
    if stale:
        bef = can_data("mốc %% sở hữu đầu kỳ (%s) cũ hơn %d tháng trước cửa sổ" % (ddmmyyyy(min(stale)), NET_BASE_MONTHS),
                       src)
    else:
        bef = _vp(sum(m["before"] for m in ms), T2 if one and ms[0]["before_t"] == T2 else EST,
                  max(m["before_d"] for m in ms), src)
    dl = [m["delta"] for m in ms]
    note = "có thành viên mốc đầu kỳ cũ: Δ của người đó = cp giao dịch trong cửa sổ ÷ số cp hiện hành" if stale else None
    d_pct = (_vp(sum(dl), EST, after_d, src, note, unit="pp") if None not in dl
             else can_data("thiếu số cp lưu hành để quy Δ từ cp giao dịch", src))
    return {"key": key, "name": name, "n_mem": len(ms), "pct_before": bef,
            "pct_after": _vp(sum(m["after"] for m in ms), T2 if one else EST, after_d, src),
            "d_pct": d_pct, "cp_now": _vq(cp, EST, cp_d, src, "không tính chuyển giao")}


def _net_top(rows: list, d0: str, d1: str, by: str, ph, so) -> list:
    """Top 3 theo |Δ % sở hữu| trong [d0, d1] (gồm chuyển giao) của các thực thể CÓ dòng % trong cửa sổ. Thực thể =
    nhóm (by="group"; chủ thể không nhóm là nhóm riêng) hoặc chủ thể; tổng nhóm cộng MỌI thành viên (% lần cuối biết),
    không chỉ người có giao dịch trong cửa sổ. Mỗi số mang ngày của chính dòng vendor (tổng: ngày muộn nhất)."""
    by_o, ents = {}, {}
    for r in rows:
        by_o.setdefault(r["owner"]["key"], []).append(r)
    for okey, rs in by_o.items():
        k, nm = _ent_key(rs[0], by)
        ents.setdefault(k, {"name": nm, "mem": []})["mem"].append(okey)
    act = {_ent_key(r, by)[0] for r in rows if d0 <= r["date"] <= d1 and r["own_after"] is not None}
    cut, src, out = lui_thang(d0, NET_BASE_MONTHS), "vc_lk insider ownershipAfterTrade", []
    for k in act:
        mem = ents[k]["mem"]
        ms = [m for m in (_member_pct(by_o[o], d0, d1, ph, so, cut) for o in mem) if m]
        wr = [r for o in mem for r in by_o[o] if d0 <= r["date"] <= d1 and not r["pair"]]
        cp = sum(r["side"] * (r["acq_now"] or 0) for r in wr)
        out.append(_ent_row(k, ents[k]["name"], ms, cp, max((r["date"] for r in wr), default=d1), src))
    out.sort(key=lambda t: (-abs(t["d_pct"].value) if not t["d_pct"].can else 0, str(t["name"])))
    return out[:3]


def insider_net(tk: str, d0: str, d1: str, today: str, by: str = "group") -> dict:
    """Nội bộ ròng (cp quy đổi) trong [d0, d1], LOẠI dòng chuyển giao; top 3 theo |Δ% sở hữu| (gồm cả chuyển giao)."""
    if by not in ("owner", "group"):
        raise ValueError(f"insider_net: by phải là 'owner' hoặc 'group', nhận {by!r}")
    b = _insider(tk, today)
    src = f"vc_lk/{tk}/insider-transaction"
    if not b["ok"]:
        c = can_data(b["why"], src)
        return _env(False, b["why"], src=src, buy_now=c, sell_now=c, net_now=c, net_pct=c, n_rows=0,
                    n_pairs_excluded=0, top=[])
    rows = _done(b)
    win = [r for r in rows if d0 <= (r["date"] or "") <= d1]
    flows = [r for r in win if not r["pair"] and r["side"] and r["acq_now"]]
    tier = UNV if any(r["acq_tier"] == UNV for r in flows) else EST
    buy = sum(r["acq_now"] for r in flows if r["side"] > 0)
    sell = sum(r["acq_now"] for r in flows if r["side"] < 0)
    so = shares_out(tk)
    note = "cp quy về số cp hiện hành; không tính chuyển giao (ghép cặp)"
    pct = (_vp((buy - sell) / so.value * 100, tier, d1, f"net ÷ {so.src}", note, unit="%")
           if not so.can and so.value else can_data("thiếu số cp lưu hành", so.src))
    return _env(True, tier=tier, asof=b["asof"], src=src, note=note, buy_now=_vq(buy, tier, d1, src, note),
                sell_now=_vq(sell, tier, d1, src, note), net_now=_vq(buy - sell, tier, d1, src, note), net_pct=pct,
                n_rows=len(flows), n_pairs_excluded=len({r["pair"]["id"] for r in win if r["pair"]}),
                top=_net_top(rows, d0, d1, by, b["ph"], so))


def _exec_ratio(rows: list, src: str, asof) -> tuple:
    rs = [r for r in rows if r["status"] == "da_xong" and r["valid"] and (r["register"] or 0) > 0]
    reg = sum(r["register"] for r in rs)
    if not reg:
        return can_data("không có số đăng ký", src), 0
    x = sum(abs(r["acquire"] or 0) for r in rs) / reg * 100
    return _vp(x, EST, asof, src, "Σ|KL thực hiện| ÷ Σ KL đăng ký trên dòng đã xong có đăng ký"), len(rs)


def _year_row(y: str, rows: list, so, src: str) -> dict:
    yr = [r for r in rows if (r["date"] or "")[:4] == y]
    fl = [r for r in yr if r["status"] == "da_xong" and r["valid"] and not r["pair"] and r["side"] and r["acq_now"]]
    tier = UNV if any(r["acq_tier"] == UNV for r in fl) else EST
    bq = sum(r["acq_now"] for r in fl if r["side"] > 0)
    sq = sum(r["acq_now"] for r in fl if r["side"] < 0)
    end = f"{y}-12-31"
    net = (_vp((bq - sq) / so.value * 100, tier, end, src, "÷ số cp hiện hành") if not so.can and so.value
           else can_data("thiếu số cp lưu hành"))
    return {"year": int(y), "n_buy": sum(1 for r in fl if r["side"] > 0), "n_sell": sum(1 for r in fl if r["side"] < 0),
            "cp_buy_now": _vq(bq, tier, end, src), "cp_sell_now": _vq(sq, tier, end, src), "net_pct": net,
            "n_transfer": sum(1 for r in yr if r["pair"]),
            "n_reg": sum(1 for r in rows if (r["public"] or "")[:4] == y and (r["register"] or 0) > 0),
            "exec_ratio": _exec_ratio(yr, src, end)[0],
            "n_not_done": sum(1 for r in yr if r["status"] == "khong_thuc_hien"),
            "n_overdue": sum(1 for r in yr if "qua_han" in r["flags"])}


def insider_yearly(tk: str, today: str, recent: int = 40) -> dict:
    """Nội bộ theo năm (cp quy đổi, không tính chuyển giao) + dòng gần nhất + đăng ký đang mở / quá hạn."""
    b = _insider(tk, today)
    src = f"vc_lk/{tk}/insider-transaction"
    if not b["ok"]:
        return _env(False, b["why"], src=src, years=[], recent=[], open=[], overdue=[])
    rows, so = b["rows"], shares_out(tk)
    ys = sorted({(r["date"] or "")[:4] for r in rows if r["date"]})
    years = [_year_row(str(y), rows, so, src) for y in range(int(ys[0]), int(ys[-1]) + 1)] if ys else []
    reg = [r for r in rows if r["status"] == "dang_ky"]
    return _env(True, tier=EST, asof=b["asof"], src=src, note="cp mua/bán không tính dòng chuyển giao (ghép cặp)",
                years=years, recent=sorted(rows, key=lambda r: (r["public"] or "", r["id"]), reverse=True)[:recent],
                open=[r for r in reg if (r["end"] or "") >= today], overdue=[r for r in reg if "qua_han" in r["flags"]])


def exec_stats(tk: str, today: str, months: int = 36) -> dict:
    """Tỷ lệ thực hiện đăng ký (|acq|/register), không thực hiện được, đang mở, quá hạn chưa kết quả (U)."""
    b = _insider(tk, today)
    src = f"vc_lk/{tk}/insider-transaction"
    if not b["ok"]:
        c = can_data(b["why"], src)
        return _env(False, b["why"], src=src, exec_ratio=c, n_done_reg=0, n_not_done=c, n_open=c, n_overdue=c,
                    window=f"{months}T")
    cut = lui_thang(today, months)
    win = [r for r in b["rows"] if cut <= (r["date"] or "") <= today]
    ratio, n_reg = _exec_ratio(win, src, today)
    n_open = sum(1 for r in b["rows"] if r["status"] == "dang_ky" and (r["end"] or "") >= today)
    return _env(True, tier=EST, asof=b["asof"], src=src, exec_ratio=ratio, n_done_reg=n_reg,
                n_not_done=_vn(sum(1 for r in win if r["status"] == "khong_thuc_hien"), T2, today, src),
                n_open=_vn(n_open, T2, today, src),
                n_overdue=_vn(sum(1 for r in win if "qua_han" in r["flags"]), UNV, today, src,
                              "vendor ghi đè bản đăng ký bằng kết quả; quá hạn chưa có kết quả ≠ không thực hiện"),
                window=f"{months}T")


def insider_windows(tk: str, today: str, months: int = 36) -> list:
    """Cửa sổ ngày của dòng da_xong hợp lệ KHÔNG chuyển giao (cho P.deal_sessions)."""
    b = _insider(tk, today)
    cut = lui_thang(today, months)
    return [{"row": r["id"], "start": r["start"] or r["end"], "end": r["end"] or r["start"], "owner": r["owner"],
             "group": r["group"], "side": r["side"], "qty": abs(r["acquire"])}
            for r in _done(b) if not r["pair"] and r["acquire"] and (r["start"] or r["end"])
            and cut <= (r["date"] or "") <= today] if b["ok"] else []


def anchor_dates(tk: str, today: str) -> list:
    """Mốc neo VWAP: DDINS lớn nhất 24T (không chuyển giao), phát hành thu tiền gần nhất, ĐHCĐ gần nhất đã họp."""
    from chaebol_map_data_codong2_ydo import agm_events, capital_actions
    out, b, cut = [], _insider(tk, today), lui_thang(today, 24)
    dd = [r for r in _done(b) if r["code"] == "DDINS" and not r["pair"] and r["acquire"] and cut <= r["date"] <= today]
    if dd:
        r = max(dd, key=lambda x: (abs(x["acquire"]), x["date"]))
        verb = "mua" if r["side"] > 0 else "bán" if r["side"] < 0 else "giao dịch"
        out.append({"id": "ddins_max_24t", "date": r["date"],
                    "label": f"Tổ chức nội bộ lớn nhất 24 tháng: {r['owner']['name']} {verb} {js_locale(abs(r['acquire']), 0)} cp"})
    ca = capital_actions(tk, today)
    tt = [it for it in ca.get("items") or [] if it["kind"] == "thu_tien" and (it["date"] or "") <= today]
    if tt:
        out.append({"id": "ph_thu_tien", "date": tt[0]["date"], "label": f"Phát hành thu tiền gần nhất: {tt[0]['title']}"})
    last = agm_events(tk, today).get("last")
    if last:
        out.append({"id": "dhcd", "date": last["date"], "label": f"ĐHCĐ gần nhất: {last['title']}"})
    return out


from chaebol_map_data_codong2_ydo import *  # noqa: E402,F401,F403
