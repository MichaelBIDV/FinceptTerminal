"""
chaebol_map_data_langkinh — lăng kính (lk_hoso, lk_thitruong, mẫu hình, số cổ đông Toàn Vũ), CỔNG (chỉ đọc),
rổ hiện hành (vnstore.ma.nhom), nhóm chaebol.

Tách từ chaebol_map_data.py (27/09/2026). Tab dùng qua mặt tiền `import chaebol_map_data as D`.
"""
from __future__ import annotations

import os
import re
from datetime import datetime

from chaebol_map_data_nen import *  # noqa: F401,F403

__all__ = [
    "lk_hoso", "lk_atom", "lk", "tv30", "pattern_label", "patterns", "codong_moc", "lk_view", "_parse_ts", "cong",
    "ticker_gate", "basket", "ecosystems", "groups_of",
]


# ───────────────────────────── lăng kính (lk_hoso, lk_thitruong, mẫu hình) ─────────────────────────────

def lk_hoso(tk: str) -> dict | None:
    d = read_json(bridge() / "data" / "lk_hoso" / f"{tk}.json", quiet=True)
    return d if isinstance(d, dict) else None


def lk_atom(a, src: str | None = None) -> V:
    """Nguyên tử lăng kính {v,u,t,b,n,g} → V (chép nguyên b/t/g)."""
    if not isinstance(a, dict):
        return can_data("không có trường lăng kính", src)
    v, u = a.get("v"), a.get("u")
    if v is None:
        return can_data(a.get("g") or "v = null", a.get("n") or src, iso(a.get("t")), u)
    txt = (js_fixed(v, 2) + "%" if u in ("%", "%tuan") else js_locale(v, 2) if _finite(v) else str(v))
    return V(v, txt, a.get("b"), iso(a.get("t")), a.get("n") or src, a.get("g"), u)


def lk(tk: str, path: str) -> V:
    """lk('VIC', 'gia.px') → V từ lk_hoso/<MÃ>.json."""
    o = lk_hoso(tk)
    if o is None:
        return can_data(f"không có lk_hoso/{tk}.json")
    for k in path.split("."):
        o = o.get(k) if isinstance(o, dict) else None
    return lk_atom(o, f"lk_hoso/{tk}.{path}")


def tv30() -> list:
    """30 mã Toàn Vũ (lk_hoso/_index.toan_vu; dự phòng fft_codong.ma)."""
    ix = read_json(bridge() / "data" / "lk_hoso" / "_index.json", quiet=True) or {}
    if ix.get("toan_vu"):
        return list(ix["toan_vu"])
    c = read_json(bridge() / "data" / "fft_codong.json", quiet=True) or {}
    return sorted((c.get("ma") or {}).keys())


def pattern_label(tk: str, label: str | None) -> str | None:
    """Mã ngoài 30 mã Toàn Vũ: nhãn pattern bắt buộc hậu tố '?' (CLAUDE.md §6 luật 4)."""
    if not label or tk in tv30():
        return label
    return label if "?" in label else label + "?"


def patterns(tk: str) -> V:
    """Mẫu hình NTH (lk_mauhinh/<MÃ>.json, EST, nhãn luôn có '?')."""
    d = read_json(bridge() / "data" / "lk_mauhinh" / f"{tk}.json", quiet=True)
    if not isinstance(d, dict):
        return can_data(f"không có lk_mauhinh/{tk}.json")
    rows = [{"id": m.get("id"), "label": pattern_label(tk, m.get("nhan")), "status": m.get("trang_thai"),
             "from": iso(m.get("tu")), "to": iso(m.get("den")), "known_at": iso(m.get("biet_luc")),
             "status_since": iso(m.get("trang_thai_tu")), "tier": m.get("b") or EST,
             "break": (m.get("diem_gay") or {}).get("mo_ta")} for m in d.get("mau") or []]
    return V(rows, None, EST, iso(d.get("t_cuoi")), f"lk_mauhinh/{tk}.json", "engine hình học NTH (EST), nhãn có '?'")


def codong_moc(tk: str) -> V:
    """Mốc số cổ đông Toàn Vũ (chỉ 30 mã): kieu quan_sat|noi_suy|chep|so_tron, cờ cf; chỉ quan_sat dùng để tính."""
    hs = lk_hoso(tk) or {}
    cd = hs.get("codong") or {}
    if cd.get("trang_thai") != "ok" or not cd.get("moc"):
        return can_data(f"{tk}: ngoài 30 mã Toàn Vũ — số cổ đông chờ OCR BCTN", f"lk_hoso/{tk}.codong")
    rows = [{"ky": m.get("ky"), "v": m.get("v"), "kieu": m.get("kieu"), "cf": bool(m.get("cf")), "tier": m.get("b")}
            for m in cd["moc"]]
    fc = ((read_json(bridge() / "data" / "fft_codong.json", quiet=True) or {}).get("ma") or {}).get(tk) or {}
    note = (f"quan sát cuối {fc.get('ky_quan_sat_cuoi')}; CF {fc.get('cf_so_ky', 0)} kỳ; "
            f"{fc.get('k_ly_do') or ''}").strip("; ")
    return V(rows, None, T3, rows[-1]["ky"], cd.get("nguon_moc") or f"lk_hoso/{tk}.codong.moc", note)


def lk_view(tk: str) -> dict:
    """Tóm tắt lăng kính theo mã (đọc tao_luc/phien_cuoi TỪNG tệp): CỔNG, chủ thể, FFT 3Y + toàn dải (thô kèm
    theo), VWAP, pattern (có '?'), Toàn Vũ, NAV/watch/avoid."""
    from chaebol_map_data_gia import vwap_cluster             # nhập trễ: gia nhập langkinh
    hs = lk_hoso(tk)
    if hs is None:
        return {"ok": False, "note": f"không có lk_hoso/{tk}.json"}
    f = hs.get("fft") or {}
    lech = (f.get("lech") or {}).get("v")
    pat = ((hs.get("codong") or {}).get("pattern") or {}).get("nhan")
    return {"ok": True, "tao_luc": hs.get("tao_luc"), "phien_cuoi": hs.get("phien_cuoi"), "tuan_cuoi": hs.get("tuan_cuoi"),
            "tv30": tk in tv30(), "cong": (hs.get("cong") or {}).get("dong"),
            "chu_the": lk_atom((hs.get("chuthe") or {}).get("nhan"), f"lk_hoso/{tk}.chuthe.nhan"),
            **{k: lk_atom(f.get(k), f"lk_hoso/{tk}.fft.{k}") for k in ("pct3y", "pall", "pct3y_tho", "pall_tho", "ma4", "x_p10")},
            "fft_hai_cua_so": lech is not None and abs(lech) >= 25,
            "vwap": vwap_cluster(tk), "pattern": pattern_label(tk, pat), "codong": codong_moc(tk),
            "nav": lk_atom(hs.get("nav"), f"lk_hoso/{tk}.nav"), "pha": (hs.get("pha") or {}).get("nhan"),
            "can_data": hs.get("can_data") or []}


def _parse_ts(s) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(s)[:25], fmt).replace(tzinfo=None)
        except ValueError:
            continue
    return None


def cong() -> dict:
    """Dòng CỔNG thị trường — CHỈ đọc (lk_thitruong.cong → fft_langkinh.cong), không tự sinh. Hai bản lệch →
    chọn bản mới hơn + cảnh báo. Thiếu hoặc quá 96 giờ → dòng [CẦN DATA]."""
    lt = read_json(bridge() / "data" / "lk_thitruong.json", quiet=True) or {}
    fl = read_json(bridge() / "data" / "fft_langkinh.json", quiet=True) or {}
    cands = []
    if isinstance(lt.get("cong"), dict) and lt["cong"].get("dong"):
        cands.append(("lk_thitruong.cong", lt["cong"], _parse_ts((lt["cong"].get("as_of") or {}).get("fft_langkinh") or lt.get("tao_luc"))))
    if isinstance(fl.get("cong"), dict) and fl["cong"].get("dong"):
        cands.append(("fft_langkinh.cong", fl["cong"], _parse_ts(fl.get("cap_nhat"))))
    if not cands:
        return {"text": "CỔNG: [CẦN DATA — fft_langkinh cũ/thiếu] · không kết luận per-mã", "as_of": None, "tier": None,
                "src": None, "dung": True, "stop": True}
    if len(cands) == 2 and cands[0][1]["dong"] == cands[1][1]["dong"]:
        src, c = "lk_thitruong.cong (= fft_langkinh.cong)", cands[0][1]
        ts = max((t[2] for t in cands if t[2]), default=None)
    else:
        if len(cands) == 2:
            warn("CỔNG: lk_thitruong và fft_langkinh lệch — dùng bản mới hơn")
        src, c, ts = max(cands, key=lambda t: t[2] or datetime.min)
    now = datetime.combine(today(), datetime.max.time()) if os.environ.get("CHB_TODAY") else datetime.now()
    if ts is None or (now - ts).total_seconds() > GATE_MAX_AGE_H * 3600:
        return {"text": "CỔNG: [CẦN DATA — fft_langkinh cũ/thiếu] · không kết luận per-mã", "as_of": iso(ts), "tier": None,
                "src": src, "dung": True, "stop": True, "note": f"bản CỔNG {ts} quá {GATE_MAX_AGE_H} giờ"}
    text = c["dong"]
    return {"text": text, "body": re.sub(r"^CỔNG:\s*", "", text), "as_of": iso(ts), "as_of_full": ts.isoformat(timespec="minutes"),
            "tier": c.get("bac") or EST, "src": src, "dung": bool(c.get("dung")),
            "stop": bool(c.get("dung")) or "[CẦN DATA" in text or "DỪNG" in text,
            "tham_chieu": c.get("tham_chieu"), "canh_bao": c.get("canh_bao") or [], "dau_vao": c.get("dau_vao")}


def ticker_gate(tk: str) -> dict:
    hs = lk_hoso(tk) or {}
    c = hs.get("cong") or {}
    ct = c.get("chu_the") or {}
    return {"text": c.get("dong") or cong()["text"], "as_of": c.get("as_of"),
            "chu_the": V(ct.get("nhan"), ct.get("nhan"), ct.get("b"), iso(ct.get("t")), f"lk_hoso/{tk}.cong.chu_the",
                         "nhãn W37 10/09 — kỳ mới phải chấm lại") if ct.get("nhan") else can_data("chưa có nhãn chủ thể")}


# ───────────────────────────── rổ, chaebol ─────────────────────────────

def basket(name: str = "VN30") -> V:
    """Rổ HIỆN HÀNH từ vnstore.ma.nhom (KBS) — KHÔNG dùng bang_vn30.json (watchlist app, lệch 4 mã)."""
    rows = db_query("SELECT symbol, nhom, cap_nhat FROM ma WHERE nhom IS NOT NULL AND nhom != ''")
    mem = sorted(r[0] for r in rows if name in str(r[1]).split(","))
    if not mem:
        return can_data(f"vnstore.ma không có rổ {name}")
    asof = max(iso(r[2]) or "" for r in rows if r[0] in mem)
    note = "rổ hiện hành (KBS); chưa đối chiếu CBTT HOSE (FACT-T1)"
    bv = read_json(bridge() / "data" / "bang_vn30.json", quiet=True) if name == "VN30" else None
    if isinstance(bv, dict):
        w = {r.get("01 Mã") for r in bv.get("dong") or []} - {"VNINDEX", "VN30"}
        if w and w != set(mem):
            note += f"; bang_vn30.json lệch (+{','.join(sorted(w - set(mem)))} / −{','.join(sorted(set(mem) - w))}) — không dùng"
    return V(mem, ", ".join(mem), T2, asof, "vnstore.ma.nhom", note)


def ecosystems() -> dict:
    """chaebol_ecosystems.json (17 nhóm ngành chia tay, EST; top-5 cổ đông, có dòng cũ) — chỉ dùng bảng nhóm → mã.
    Hỗ trợ hai lược đồ (as_of + members dict | _meta.generated + members list)."""
    d = read_json(bridge() / "data" / "chaebol_ecosystems.json", quiet=True)
    if not isinstance(d, dict):
        return {"groups": {}, "as_of": None, "note": "thiếu chaebol_ecosystems.json"}
    eco = d.get("ecosystems") or {}
    groups, n_old, dups = {}, 0, []
    for g, blk in eco.items():
        mem = blk.get("members") or {}
        if isinstance(mem, list):
            mem = {m.get("ticker") or m.get("symbol"): m for m in mem if isinstance(m, dict)}
        for tk, m in mem.items():
            tsh = (m or {}).get("top_shareholders") or []
            n_old += sum(1 for s in tsh if (_months_ago(iso(s.get("publicDate"))) or 0) > OLD_MONTHS)
            names = [s.get("ownerName") for s in tsh]
            if len(names) != len(set(names)):
                dups.append(tk)
        groups[g] = {"tickers": list(blk.get("tickers") or mem.keys()), "members": mem}
    asof = d.get("as_of") or (d.get("_meta") or {}).get("generated")
    return {"groups": groups, "as_of": asof, "tier": EST,
            "note": f"nhóm chia tay (EST), 8/17 là nhóm ngành; top-5 cổ đông theo thứ tự API; {n_old} dòng top-5 cũ >12T; "
                    f"trùng chủ sở hữu ở {','.join(sorted(set(dups))) or '—'} — cổ đông ưu tiên vc_lk"}


def groups_of(tk: str) -> list:
    return [g for g, b in ecosystems()["groups"].items() if tk in b["tickers"]]
