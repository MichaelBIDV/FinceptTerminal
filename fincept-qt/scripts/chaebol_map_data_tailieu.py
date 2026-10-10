"""
chaebol_map_data_tailieu — tài liệu tĩnh/tuyển chọn: hằng V21, dữ kiện facts_f*.json, dossier cập nhật, hai sổ
danh mục, sổ nguồn + độ tươi, tỷ giá, nguồn phụ (claims ledger, owner intent, tin).

Tách từ chaebol_map_data.py (27/09/2026). Tab dùng qua mặt tiền `import chaebol_map_data as D`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from chaebol_map_data_nen import *  # noqa: F401,F403

__all__ = [
    "v21", "v21_get", "_P_SRC_LINE", "_P_SRC_HTML", "_P_SRC_BLOCK", "_src_range", "_src_refs", "_fact_numbers",
    "_norm_fact", "facts", "facts_index", "facts_for", "facts_for_src", "_merge", "_drop_unsourced", "dossier",
    "portfolio_v21", "_read_text", "_num", "_k11", "_hdcv", "_book_tiers", "portfolio_current", "source_audit",
    "vc_lk_status", "freshness", "vnstore_status", "_FX", "usd_vnd", "claims_ledger", "owner_intent_curated",
    "news_events",
]


# ───────────────────────────── V21, dữ kiện, dossier ─────────────────────────────

def v21() -> dict:
    """$B/data/chaebol_map/v21_const.json (agent A trích một lần). Thiếu → {} + cảnh báo."""
    d = read_json(bridge() / "data" / "chaebol_map" / "v21_const.json", quiet=True)
    if not isinstance(d, dict):
        warn("v21_const.json chưa có (hoặc hỏng) — hằng V21 trống")
        return {}
    return d


def v21_get(name: str):
    d = v21()
    for k in ("", "const", "consts", "constants", "data"):
        blk = d.get(k) if k else d
        if isinstance(blk, dict) and name in blk:
            return blk[name]
    return None


# Tham chiếu dòng SRC trong thay_the_menh_de_cu: "dòng 102", "dòng 4725–4728", "html:L88", "L250-251",
# "html:3524; 5353", {"dong": [93, 307]}. Dạng "L<n>" cần ≥2 chữ số (tránh "L1+L2+L3" của Synthesis).
_P_SRC_LINE = re.compile(r"(?:\bdòng|\bdong|\bL(?=\d{2}))\s*(\d{1,4})(?:\s*[–-]\s*L?(\d{1,4}))?")
_P_SRC_HTML = re.compile(r"\.html:(\d{1,4})((?:\s*[;,]\s*\d{1,4})*)")
_P_SRC_BLOCK = re.compile(r"\b([A-Z][A-Z0-9_]{2,}(?:\.[A-Za-z0-9_]+)+)")


def _src_range(a, b=None):
    a, b = int(a), int(b) if b else int(a)
    if b < a or b - a > 400:
        b = a
    return (a, b) if 1 <= a <= 8000 else None


def _src_refs(x, lines: set, blocks: set) -> None:
    """Gom dòng SRC + đường dẫn hằng V21 (FLOW.VIC, CLAIMS_54.C09…) từ thay_the_menh_de_cu (str | list | dict)."""
    if isinstance(x, list):
        for y in x:
            _src_refs(y, lines, blocks)
    elif isinstance(x, dict):
        d = x.get("dong")
        for n in (d if isinstance(d, list) else [d]):
            if isinstance(n, int) and not isinstance(n, bool) and _src_range(n):
                lines.add((n, n))
        if isinstance(x.get("khoi"), str):
            blocks.add(x["khoi"].strip())
        for k in ("trich", "text"):
            _src_refs(x.get(k), lines, blocks)
    elif isinstance(x, str):
        for m in _P_SRC_LINE.finditer(x):
            r = _src_range(m.group(1), m.group(2))
            if r:
                lines.add(r)
        for m in _P_SRC_HTML.finditer(x):
            for n in [m.group(1)] + re.findall(r"\d{1,4}", m.group(2) or ""):
                r = _src_range(n)
                if r:
                    lines.add(r)
        blocks.update(_P_SRC_BLOCK.findall(x))


def _fact_numbers(x) -> list:
    """so_lieu các tệp khác dạng (None | list {ten,gia_tri,don_vi,ngay,bac} | dict tên→chuỗi | chuỗi) → list dict."""
    if isinstance(x, list):
        return [dict(y) if isinstance(y, dict) else {"text": str(y)} for y in x]
    if isinstance(x, dict):
        return [{"ten": str(k), "gia_tri": v} if isinstance(v, (int, float)) and not isinstance(v, bool)
                else {"ten": str(k), "text": v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)}
                for k, v in x.items()]
    return [{"text": x}] if isinstance(x, str) and x.strip() else []


def _norm_fact(r: dict) -> dict:
    """Thêm trường chuẩn hoá (giữ nguyên trường gốc): nguon_list, so_lieu_list, src_lines [[a,b]], src_blocks,
    trang_thai (trang_thai_menh_de_cu bỏ phần chú thích trong ngoặc)."""
    ng = r.get("nguon")
    r["nguon_list"] = [str(s) for s in ng] if isinstance(ng, list) else ([ng] if isinstance(ng, str) and ng else [])
    r["so_lieu_list"] = _fact_numbers(r.get("so_lieu"))
    lines, blocks = set(), set()
    _src_refs(r.get("thay_the_menh_de_cu"), lines, blocks)
    r["src_lines"] = [list(t) for t in sorted(lines)]
    r["src_blocks"] = sorted(blocks)
    st = r.get("trang_thai_menh_de_cu")
    r["trang_thai"] = st.split(" (")[0].strip() if isinstance(st, str) and st.strip() else None
    return r


def facts() -> list:
    """Dữ kiện facts_f*.json (spec dir), chuẩn hoá: id (sinh 'F1-001' khi thiếu), ma (list), file + _norm_fact."""
    def build():
        out = []
        for p in sorted(spec_dir().glob("facts_f*.json")):
            rows = read_json(p) or []
            m = re.match(r"facts_f(\d+)", p.name)
            for i, r in enumerate(rows if isinstance(rows, list) else [], 1):
                r = dict(r)
                r["id"] = r.get("id") or f"F{m.group(1) if m else '0'}-{i:03d}"
                ma = r.get("ma")
                r["ma"] = [ma] if isinstance(ma, str) else list(ma or [])
                r["file"] = p.name
                out.append(_norm_fact(r))
        return out
    sig = tuple((p.name, _sig(p)) for p in sorted(spec_dir().glob("facts_f*.json")))
    return _memo(("facts", str(spec_dir())), sig, build)


def facts_index() -> dict:
    idx = {"by_id": {}, "by_ma": {}, "by_nhom": {}, "by_loai": {}}
    for r in facts():
        idx["by_id"][r["id"]] = r
        for tk in r["ma"]:
            idx["by_ma"].setdefault(tk, []).append(r["id"])
        idx["by_nhom"].setdefault(r.get("nhom"), []).append(r["id"])
        idx["by_loai"].setdefault(r.get("loai"), []).append(r["id"])
    return idx


def facts_for(ma: str | None = None, nhom: str | None = None, loai: str | None = None) -> list:
    return [r for r in facts() if (ma is None or ma in r["ma"]) and (nhom is None or r.get("nhom") == nhom)
            and (loai is None or r.get("loai") == loai)]


def facts_for_src(line_from: int | None = None, line_to: int | None = None, block: str | None = None) -> list:
    """Dữ kiện thay thế mệnh đề V21 nằm ở dòng SRC [line_from, line_to] (giao khoảng) và/hoặc hằng có tiền tố
    `block` (vd "CLAIMS_54.C09", "FLOW.GEX", "CHAEBOL_DEEP_DATA.VIC"). Cả hai None → []. Tab dùng dải dòng của
    component mình (page_p*.md ghi dòng SRC) để tìm câu cần viết lại."""
    if line_from is None and block is None:
        return []
    lo = line_from if line_from is not None else 0
    hi = line_to if line_to is not None else lo
    out = []
    for r in facts():
        hit_line = line_from is not None and any(a <= hi and b >= lo for a, b in r["src_lines"])
        hit_blk = block is not None and any(b == block or b.startswith(block + ".") for b in r["src_blocks"])
        if hit_line or hit_blk:
            out.append(r)
    return out


def _merge(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            out[k] = _merge(a[k], v, f"{path}.{k}") if k in a else v
        return out
    if isinstance(a, list) and isinstance(b, list):
        return a + b
    if a != b:
        warn(f"dossier: khoá {path or '/'} bị ghi đè bởi mảnh sau")
    return b


def _drop_unsourced(o, cnt):
    """DESIGN §7: mục có 'tier' mà không có 'src' → không dùng."""
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            if isinstance(v, dict) and "tier" in v and not v.get("src"):
                cnt[0] += 1
                continue
            out[k] = _drop_unsourced(v, cnt)
        return out
    if isinstance(o, list):
        keep = [x for x in o if not (isinstance(x, dict) and "tier" in x and not x.get("src"))]
        cnt[0] += len(o) - len(keep)
        return [_drop_unsourced(x, cnt) for x in keep]
    return o


def dossier() -> dict:
    """knowledge_os/chaebol_map/cap_nhat_<ngày>.json mới nhất; chưa có tệp hợp nhất cho ngày mới nhất → gộp các
    mảnh cap_nhat_<ngày>.<tab>.json (dict gộp sâu, list nối). Kết quả có '_meta' {date, files, dropped}."""
    d = sys_dir() / "knowledge_os" / "chaebol_map"
    files = sorted(d.glob("cap_nhat_*.json")) if d.exists() else []
    if not files:
        warn("chưa có dossier cap_nhat_*.json — chế độ live chỉ dùng số sống")
        return {"_meta": {"date": None, "files": [], "dropped": 0}}
    by: dict = {}
    for p in files:
        m = re.match(r"cap_nhat_(\d{4}-\d{2}-\d{2})(?:\.([\w-]+))?\.json$", p.name)
        if not m:
            continue
        slot = by.setdefault(m.group(1), {"full": None, "parts": []})
        if m.group(2):
            slot["parts"].append(p)
        else:
            slot["full"] = p
    if not by:
        warn("dossier: không có tệp đúng mẫu cap_nhat_<YYYY-MM-DD>[.<tab>].json")
        return {"_meta": {"date": None, "files": [], "dropped": 0}}
    cut = today().isoformat()
    days = [x for x in by if cut is None or x <= cut] or list(by)
    day = max(days)
    use = [by[day]["full"]] if by[day]["full"] else sorted(by[day]["parts"])
    merged: dict = {}
    for p in use:
        blk = read_json(p)
        if isinstance(blk, dict):
            merged = _merge(merged, blk)
    cnt = [0]
    merged = _drop_unsourced(merged, cnt)
    if cnt[0]:
        warn(f"dossier {day}: bỏ {cnt[0]} mục thiếu 'src'")
    merged["_meta"] = {"date": day, "files": [p.name for p in use], "dropped": cnt[0], "merged_parts": not by[day]["full"]}
    return merged


# ───────────────────────────── danh mục (V21 + hai bản hiện hành) ─────────────────────────────

def portfolio_v21() -> dict:
    return {"PORTFOLIO_ACTION": v21_get("PORTFOLIO_ACTION") or {}, "ACTION_PORT_25": v21_get("ACTION_PORT_25") or [],
            "note": "bản lưu V21·12/05 — nhận định giữ nguyên, không chấm lại (CỔNG đang DỪNG)"}


def _read_text(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return None


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _k11() -> dict:
    """Lăng kính Khối 11 (snapshot 10/09/2026): langkinh-cautruc-codong/SKILL.md §6.1; dự phòng/bổ sung
    fft_cauhinh.danh_muc (21/09, cùng dòng sổ) cho watch/avoid/xung đột."""
    p = skills_dir() / "langkinh-cautruc-codong" / "SKILL.md"
    txt = _read_text(p) or ""
    m = re.search(r"### 6\.1[^\n]*\n(.*?)(?=\n### |\n## |\Z)", txt, re.S)
    pos, cash, unexpl, actions, cands, day = [], None, None, [], [], None
    if m:
        sec, head = m.group(1), re.search(r"### 6\.1[^\n]*", txt).group(0)
        dm = re.search(r"(\d{2}/\d{2}/\d{4})", head)
        day = iso(dm.group(1)) if dm else None
        for ln in sec.splitlines():
            r = re.match(r"^\|\s*\*\*([A-Z0-9]{3})\*\*\s*\|\s*\**\s*(\d+(?:[.,]\d+)?)%\s*(UNVERIFIED)?\s*\**\s*\|(.*)$", ln)
            if r:
                cells = [c.strip() for c in r.group(4).strip().strip("|").split("|")]
                pos.append({"tk": r.group(1), "nav": _num(r.group(2)), "verified": not r.group(3), "cot": cells})
        cm = re.search(r"(\d+)% cash", sec)
        um = re.search(r"(\d+)% chưa giải trình", sec)
        cash, unexpl = (float(cm.group(1)) if cm else None), (float(um.group(1)) if um else None)
        cb = re.search(r"```\n(.*?)```", sec, re.S)
        if cb:
            actions = [{"tk": a, "tu": float(b), "den": float(c)} for a, b, c in re.findall(r"([A-Za-z]+)\s+(\d+)\s*→\s*(\d+)", cb.group(1))]
            cl = re.search(r"Ứng viên thay thế[^:]*:\s*(.*)", cb.group(1))
            cands = [x.strip() for x in cl.group(1).split("·")] if cl else []
    src = f"{p} §6.1" if pos else None
    dm_ = (read_json(bridge() / "fft_cauhinh.json", quiet=True) or {}).get("danh_muc") or {}
    if not pos and dm_.get("nav"):
        warn("Khối 11: không đọc được SKILL §6.1 — dùng fft_cauhinh.danh_muc (21/09)")
        pos = [{"tk": k, "nav": float(v), "verified": True, "cot": []} for k, v in dm_["nav"].items()]
        pos += [{"tk": k, "nav": float(v), "verified": False, "cot": []} for k, v in (dm_.get("nav_unverified") or {}).items()]
        src, day = "fincept_bridge/fft_cauhinh.json → danh_muc", iso(dm_.get("ngay"))
    return {"date": day, "positions": pos, "cash": cash, "unexplained": unexpl, "actions": actions, "candidates": cands,
            "watch": list(dm_.get("watch") or []), "avoid": list(dm_.get("avoid") or []),
            "xung_dot": dm_.get("xung_dot") or {}, "src": src,
            "src_watch_avoid": f"fft_cauhinh.json danh_muc ({ddmmyyyy(dm_.get('ngay'))})" if dm_ else None}


def _hdcv() -> dict:
    """Skill điều hành hoidongcovanai-chungkhoan: '## Danh mục tham chiếu (cập nhật 12/09/2026)'."""
    p = skills_dir() / "hoidongcovanai-chungkhoan" / "SKILL.md"
    txt = _read_text(p) or ""
    m = re.search(r"## Danh mục tham chiếu \(cập nhật (\d{2}/\d{2}/\d{4})\)\s*\n(.*?)(?=\n---|\n## |\Z)", txt, re.S)
    if not m:
        return {"date": None, "positions": [], "cash": None, "avoid": [], "src": None}
    body = m.group(2)
    pos = []
    for layer, seg in re.findall(r"\b(Core|Growth|Tactical)\s+([^.\n]*)", body):
        pos += [{"tk": t, "nav": _num(x), "verified": True, "layer": layer}
                for t, x in re.findall(r"\b([A-Z0-9]{3})\s+(\d+(?:[.,]\d+)?)%", seg)]
    cm = re.search(r"Tiền mặt\s+(\d+(?:[.,]\d+)?)%", body)
    am = re.search(r"AVOID:\*\*\s*([A-Z0-9 ,]+)", body)
    return {"date": iso(m.group(1)), "positions": pos, "cash": _num(cm.group(1)) if cm else None,
            "avoid": [x.strip() for x in am.group(1).split(",") if x.strip()] if am else [], "watch": [], "src": f"{p}"}


def _book_tiers(b: dict, name: str) -> dict:
    for x in b["positions"]:
        x["v"] = V(x["nav"], js_locale(x["nav"], 1) + "%", EST if x["verified"] else UNV, b["date"], b["src"],
                   f"{name}: sổ danh mục nội bộ (không phải số thị trường)" + ("" if x["verified"] else " — UNVERIFIED"), "%NAV")
    ver = sum(x["nav"] for x in b["positions"] if x["verified"])
    unv = sum(x["nav"] for x in b["positions"] if not x["verified"])
    b["tong_text"] = f"{js_locale(ver, 1)}% verified" + (f" + {js_locale(unv, 1)}% UNVERIFIED" if unv else "")
    b["tong_verified"], b["tong_unverified"] = ver, unv
    return b


def portfolio_current() -> dict:
    """HAI bản danh mục hiện hành cạnh nhau + danh sách mâu thuẫn. KHÔNG tự chọn bản nào (DESIGN §0.4)."""
    a, b = _book_tiers(_k11(), "Lăng kính Khối 11"), _book_tiers(_hdcv(), "hoidongcovanai-chungkhoan")
    na, nb = {x["tk"]: x for x in a["positions"]}, {x["tk"]: x for x in b["positions"]}
    conf = []
    for tk in sorted(set(na) | set(nb)):
        x, y = na.get(tk), nb.get(tk)
        if x and y and x["nav"] != y["nav"]:
            conf.append({"loai": "nav", "tk": tk, "lk_khoi11": x["nav"], "hdcv": y["nav"]})
        elif bool(x) != bool(y):
            conf.append({"loai": "chi_mot_ban", "tk": tk, "lk_khoi11": x["nav"] if x else None, "hdcv": y["nav"] if y else None,
                         "note": "UNVERIFIED" if x and not x["verified"] else None})
    if a["cash"] != b["cash"]:
        conf.append({"loai": "cash", "tk": None, "lk_khoi11": a["cash"], "hdcv": b["cash"]})
    wa = set(a["watch"]) | {re.sub(r"\s*\(.*", "", c) for c in a["candidates"] if "watch" in c}
    for tk in sorted((wa & set(b["avoid"])) | set(a["xung_dot"])):
        conf.append({"loai": "watch_vs_avoid", "tk": tk, "lk_khoi11": "watch" if tk in wa else "avoid",
                     "hdcv": "AVOID" if tk in b["avoid"] else "—", "note": a["xung_dot"].get(tk)})
    for tk in sorted(set(a["avoid"]) ^ set(b["avoid"])):
        if tk not in a["xung_dot"]:
            conf.append({"loai": "avoid", "tk": tk, "lk_khoi11": "avoid" if tk in a["avoid"] else "—",
                         "hdcv": "AVOID" if tk in b["avoid"] else "—"})
    ds = dossier().get("portfolio")
    return {"lk_khoi11_1009": a, "hdcv_1209": b, "conflicts": conf, "dossier": ds,
            "note": "hiện CẢ HAI bản, gắn cờ lệch; không chọn; mọi hành động >5% NAV → Synthesis L1+L2+L3"}


# ───────────────────────────── sổ nguồn, độ tươi, tỷ giá ─────────────────────────────

def source_audit(tab: str | None = None) -> dict:
    """so_nguon_audit.json: tài sản (lọc tieu_thu ∋ tab nếu có), vấn đề, mốc cập nhật. Mỗi tài sản có sla_gio (SLA
    danh nghĩa) và sla_cuoi_tuan (SLA cuối tuần nếu sổ ghi; thường None) bên cạnh nguong_gio (ngưỡng đã nâng)."""
    a = read_json(bridge() / "data" / "so_nguon_audit.json", quiet=True)
    if not isinstance(a, dict):
        return {"cap_nhat": None, "tai_san": [], "van_de": [], "note": "thiếu so_nguon_audit.json"}
    ts = [r for r in a.get("tai_san") or [] if tab is None or tab in (r.get("tieu_thu") or [])]
    ids = {r.get("id") for r in ts}
    return {"cap_nhat": a.get("cap_nhat"), "tom_tat": a.get("tom_tat"),
            "tai_san": [{k: r.get(k) for k in ("id", "ten", "nhom", "duong_dan", "bac", "trang_thai", "tuoi_gio",
                                                "nguong_gio", "sla_gio", "sla_cuoi_tuan", "moc", "tieu_thu", "nguon_goc",
                                                "phap_ly", "ghi_chu")} for r in ts],
            "van_de": [v for v in a.get("van_de") or [] if tab is None or v.get("id") in ids]}


def vc_lk_status() -> dict:
    """Độ tươi vc_lk theo endpoint từ _meta.json (min/max du_lieu_toi, lỗi)."""
    m = read_json(vc_dir() / "_meta.json", quiet=True)
    if not isinstance(m, dict):
        return {"cap_nhat": None, "endpoints": {}}
    eps: dict = {}
    for tk, blk in (m.get("ma") or {}).items():
        for ep, st in (blk or {}).items():
            e = eps.setdefault(ep, {"n_ma": 0, "min_du_lieu_toi": None, "max_du_lieu_toi": None, "min_lay_luc": None,
                                    "max_lay_luc": None, "loi": []})
            e["n_ma"] += 1
            for f, k in (("du_lieu_toi", "du_lieu_toi"), ("lay_luc", "lay_luc")):
                v = st.get(k)
                if v:
                    e[f"min_{f}"] = min(filter(None, [e[f"min_{f}"], v]))
                    e[f"max_{f}"] = max(filter(None, [e[f"max_{f}"], v]))
            if st.get("trang_thai") not in (None, "ok"):
                e["loi"].append({"ma": tk, "trang_thai": st.get("trang_thai"), "loi": st.get("loi")})
    return {"cap_nhat": m.get("cap_nhat"), "lan_chay_cuoi": m.get("lan_chay_cuoi"), "endpoints": eps}


def freshness(tk: str) -> dict:
    m = read_json(vc_dir() / "_meta.json", quiet=True) or {}
    return (m.get("ma") or {}).get(tk) or {}


def vnstore_status() -> dict:
    meta = {k: v for k, v in db_query("SELECT khoa, gia_tri FROM meta") if k.startswith(("chay_", "loi_", "dm:"))}
    r = db_query("SELECT MAX(ngay) FROM nen_ngay")
    return {"meta": meta, "nen_ngay_max": r[0][0] if r else None}


_FX = {"trung_tam": ("fx_central", "tỷ giá trung tâm NHNN"), "nhtm_ban": ("fx_nhtm_sell", "giá bán NHTM"),
       "tu_do": ("fx_free_sell", "giá bán thị trường tự do")}


def usd_vnd(kind: str = "nhtm_ban") -> V:
    """USD/VND theo loại (trung_tam | nhtm_ban | tu_do) từ liquidity_daily/output/latest.json (FACT-T2);
    dự phòng bang_widata 'Tỷ giá trung tâm'. Luôn ghi loại tỷ giá trong note."""
    key, name = _FX.get(kind, _FX["nhtm_ban"])
    L = read_json(sys_dir() / "liquidity_daily" / "output" / "latest.json", quiet=True) or {}
    r = L.get("rates") or {}
    if _finite(r.get(key)):
        prev = r.get(f"{key}_prev")
        return V(r[key], js_locale(r[key], 0), T2, iso(r.get(f"{key}_asof")), f"liquidity_daily/output/latest.json rates.{key}",
                 f"loại: {name}; kỳ trước {js_locale(prev, 0) if _finite(prev) else '—'}", "VND/USD")
    w = read_json(bridge() / "data" / "bang_widata.json", quiet=True) or {}
    for row in w.get("dong") or []:
        if str(row.get("1 Chỉ tiêu", "")).startswith("Tỷ giá trung tâm"):
            v = float(str(row.get("3 Giá trị")).replace(".", "").replace(",", "."))
            if kind == "trung_tam":
                return V(v, js_locale(v, 0), T2, iso(f"{row.get('2 Kỳ')}/{today().year}"), "data/bang_widata.json",
                         f"loại: {name}; {row.get('7 Ghi chú')}", "VND/USD")
            mm = re.search(r"NHTM bán ([\d.]+)", str(row.get("7 Ghi chú")))
            if mm and kind == "nhtm_ban":
                x = float(mm.group(1).replace(".", ""))
                return V(x, js_locale(x, 0), T2, iso(f"{row.get('2 Kỳ')}/{today().year}"), "data/bang_widata.json",
                         f"loại: {name} (ghi chú bảng WiData)", "VND/USD")
    return can_data(f"không có tỷ giá USD/VND loại {name}")


# ───────────────────────────── nguồn phụ (claims, ý đồ, tin) ─────────────────────────────

def claims_ledger() -> V:
    d = read_json(sys_dir() / "early_detection" / "claims_ledger.json", quiet=True)
    if not isinstance(d, dict):
        return can_data("thiếu early_detection/claims_ledger.json")
    return V(d.get("claims") or [], None, EST, iso(d.get("updated")), "early_detection/claims_ledger.json",
             "luận điểm EST; trạng thái do máy — builder chỉ hiển thị")


def owner_intent_curated(tk: str | None = None, until=None) -> V:
    """26 sự kiện curated (auto=false) của owner_intent; auto bị loại (ngày giữ chỗ 31/12). verified → EST, không → UNVERIFIED."""
    d = read_json(sys_dir() / "early_detection" / "owner_intent.json", quiet=True)
    if not isinstance(d, dict):
        return can_data("thiếu early_detection/owner_intent.json")
    rows = []
    for t, blk in (d.get("by_ticker") or {}).items():
        if tk and t != tk:
            continue
        for e in (blk or {}).get("events") or []:
            if e.get("auto") or (until and iso(e.get("date")) > iso(until)):
                continue
            rows.append({**e, "ticker": t, "group": (blk or {}).get("group"), "tier": EST if e.get("verified") else UNV})
    rows.sort(key=lambda e: e.get("date") or "", reverse=True)
    return V(rows, None, EST, iso(d.get("updated")), "early_detection/owner_intent.json", "chỉ sự kiện curated")


def news_events(tk: str, since=None) -> V:
    """fft_tin.ma[<MÃ>].su_kien (mỗi mục mang bac riêng; 'dang_ky' ≠ kết quả)."""
    d = read_json(bridge() / "data" / "fft_tin.json", quiet=True)
    if not isinstance(d, dict):
        return can_data("thiếu data/fft_tin.json")
    ev = [e for e in ((d.get("ma") or {}).get(tk) or {}).get("su_kien") or [] if not since or (e.get("ngay") or "") >= iso(since)]
    ev.sort(key=lambda e: e.get("ngay") or "", reverse=True)
    return V(ev, None, T2, iso(d.get("cap_nhat")), "fincept_bridge/data/fft_tin.json", "bậc theo từng mục (trường 'bac')")
