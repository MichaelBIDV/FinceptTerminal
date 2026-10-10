#!/usr/bin/env python3
"""
Fincept Terminal — Fincept Macro Integration Service (v2.5)
Engineered for EconomicsScreen -> FinceptMacroPanel and Dashboard widgets.
Extracts real-time leaderboard snap-cards and maximum historical time series (20-56 years)
from dulieukinhte.com across 4 key economies: Vietnam (VN), US (US), China (CN), Eurozone (EU).
"""

import sys
import os
import json
import re
import ssl
import time
import urllib.request
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

CACHE_DIR = os.path.expanduser("~/.cache/fincept/macro")
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_TTL = 3600 * 2  # 2 hours

ECONOMIES = {
    "VN": {"code": "VN", "name": "Việt Nam", "url": "https://dulieukinhte.com/kinh-te/viet-nam"},
    "US": {"code": "US", "name": "Hoa Kỳ", "url": "https://dulieukinhte.com/kinh-te/my"},
    "CN": {"code": "CN", "name": "Trung Quốc", "url": "https://dulieukinhte.com/kinh-te/trung-quoc"},
    "EU": {"code": "EU", "name": "Châu Âu", "url": "https://dulieukinhte.com/kinh-te/chau-au"}
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://dulieukinhte.com/"
}

PULSE_METRICS = {
    "VN": {
        "label": "🇻🇳 Việt Nam",
        "gdp": 268,
        "inflation": 319,
        "rate": None,
        "unemployment": None,
    },
    "US": {
        "label": "🇺🇸 Hoa Kỳ",
        "gdp": 429,
        "inflation": 432,
        "rate": 446,
        "unemployment": 437,
    },
    "CN": {
        "label": "🇨🇳 Trung Quốc",
        "gdp": 546,
        "inflation": 549,
        "rate": 556,
        "unemployment": 558,
    },
    "EU": {
        "label": "🇪🇺 Châu Âu",
        "gdp": 489,
        "inflation": 491,
        "rate": 503,
        "unemployment": 494,
    },
}

def _get_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def _fetch_url(url: str, cache_key: str, force_refresh: bool = False, is_json: bool = False) -> str:
    ext = "json" if is_json else "html"
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.{ext}")
    if not force_refresh and os.path.exists(cache_file):
        if (time.time() - os.path.getmtime(cache_file)) < CACHE_TTL:
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                pass

    req = urllib.request.Request(url, headers=HEADERS)
    ctx = _get_ssl_context()
    with urllib.request.urlopen(req, context=ctx, timeout=25) as resp:
        content = resp.read().decode("utf-8")
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass
        return content

def fetch_leaderboard_rows(country_code: str, force_refresh: bool = False) -> Dict[str, Any]:
    code = country_code.upper()
    if code not in ECONOMIES:
        return {"success": False, "error": f"Mã quốc gia không hợp lệ: {country_code}"}

    eco = ECONOMIES[code]
    try:
        html = _fetch_url(eco["url"], f"leaderboard_{code.lower()}", force_refresh)
    except Exception as e:
        return {"success": False, "error": str(e)}

    raw_cards = re.findall(r'<a class="snap-card([^"]*)" href="([^"]+)">(.*?)</a>', html, re.DOTALL)
    rows = []

    for cls, href, body in raw_cards:
        lbl_m = re.search(r'<span class="snap-label">([^<]+)(?:<span class="snap-hint">([^<]+)</span>)?</span>', body)
        label = lbl_m.group(1).strip() if lbl_m else ""
        hint = lbl_m.group(2).strip() if lbl_m and lbl_m.group(2) else ""

        if not label:
            lbl_block = re.search(r'<span class="snap-label">(.*?)</span>', body, re.DOTALL)
            if lbl_block:
                label = re.sub(r'<[^>]+>', ' ', lbl_block.group(1)).strip()

        val_m = re.search(r'<span class="snap-value">([^<]+)(?:<span class="snap-unit">([^<]+)</span>)?</span>', body)
        val = val_m.group(1).strip() if val_m else ""
        unit = val_m.group(2).strip() if val_m and val_m.group(2) else ""

        per_m = re.search(r'<span class="snap-period">([^<]+)</span>', body)
        period = per_m.group(1).strip() if per_m else ""

        delta_m = re.search(r'<span class="snap-delta([^"]*)">([^<]+)(?:<span class="snap-delta-note">([^<]+)</span>)?</span>', body)
        delta_cls = delta_m.group(1).strip() if delta_m else ""
        delta_val = delta_m.group(2).strip() if delta_m else ""
        delta_note = delta_m.group(3).strip() if delta_m and delta_m.group(3) else ""
        
        trend = "TĂNG ▲" if "up" in delta_cls else ("GIẢM ▼" if "down" in delta_cls else "ĐI NGANG ━")

        table_id_m = re.search(r'-(\d+)$', href)
        table_id = int(table_id_m.group(1)) if table_id_m else 0

        # Parse numeric value for sorting/aggregation if possible
        num_val = None
        try:
            clean_val = val.replace(".", "").replace(",", ".")
            num_val = float(clean_val)
        except Exception:
            pass

        rows.append({
            "CHỈ TIÊU": label,
            "GIẢI THÍCH": hint if hint else "—",
            "GIÁ TRỊ": val,
            "ĐƠN VỊ": unit if unit else "—",
            "KỲ BÁO CÁO": period,
            "BIẾN ĐỘNG": delta_val if delta_val else "—",
            "SO VỚI": delta_note if delta_note else "—",
            "XU HƯỚNG": trend,
            "MÃ BẢNG": table_id,
            "QUỐC GIA": eco["name"]
        })

    return {
        "success": True,
        "data": rows,
        "count": len(rows),
        "country": eco["name"],
        "source": "dulieukinhte.com"
    }

_LEADERBOARD_IDX: Dict[int, Dict[str, Any]] = {}


def _leaderboard_index(force_refresh: bool = False) -> Dict[int, Dict[str, Any]]:
    """MÃ BẢNG → thẻ, gom từ 4 TRANG CÔNG KHAI /kinh-te/<nước>.

    Thẻ trên trang công khai đã mang sẵn 'MÃ BẢNG' (bóc từ href /du-lieu/<slug>-<id>) nên
    tra được giá trị mới nhất của đúng chỉ tiêu mà KHÔNG cần API nội bộ.
    """
    global _LEADERBOARD_IDX
    if _LEADERBOARD_IDX and not force_refresh:
        return _LEADERBOARD_IDX
    idx: Dict[int, Dict[str, Any]] = {}
    for code in ECONOMIES:
        res = fetch_leaderboard_rows(code, force_refresh=force_refresh)
        if not res.get("success"):
            continue
        for row in res.get("data") or []:
            try:
                tid = int(row.get("MÃ BẢNG") or 0)
            except (TypeError, ValueError):
                continue
            if tid:
                idx[tid] = row
    _LEADERBOARD_IDX = idx
    return idx


def fetch_max_series_rows(table_id: Any, force_refresh: bool = False) -> Dict[str, Any]:
    """CHUỖI LỊCH SỬ: không lấy từ dulieukinhte.com.

    robots.txt của trang ghi `Disallow: /api/internal/`, mà toàn bộ chuỗi lịch sử của họ chỉ
    nằm sau đúng đường đó (/api/internal/data/tablemacro/<id>, /api/internal/data/rows/<id>).
    dulieukinhte là trang BÊN THỨ BA — chủ hệ đã chốt ngày 20/09/2026: chỉ đọc trang công khai.
    Trang /du-lieu/<slug>-<id> cũng KHÔNG nhúng chuỗi trong HTML (đã kiểm: 0 mảng số dài trong
    218 KB payload), nên không có đường hợp lệ nào khác từ nguồn này.

    Ảnh chụp mới nhất vẫn dùng được — lấy từ thẻ trang công khai qua _leaderboard_index().
    Chuỗi để vẽ đồ thị phải lấy từ nguồn gốc miễn phí của hệ: FRED · ECB · WiChart/VietnamBiz ·
    World Bank (xem _System/superdash_v2/output/widata_series_store.json qua hub :9000).
    """
    return {
        "success": False,
        "error": ("Chuỗi lịch sử của dulieukinhte.com nằm sau /api/internal/ mà robots.txt cấm. "
                  "Dùng nguồn gốc (FRED/ECB/WiChart/World Bank) hoặc "
                  "http://localhost:9000/sys/superdash_v2/output/widata_series_store.json"),
        "data": [],
        "table_id": str(table_id),
        "policy": "robots_disallow",
    }


def _format_latest_metric(table_id: Optional[int], force_refresh: bool = False) -> Tuple[str, Optional[float], str]:
    """Giá trị mới nhất của một chỉ tiêu, đọc từ THẺ trang công khai (không đụng API nội bộ)."""
    if table_id is None:
        return "—", None, "—"
    row = _leaderboard_index(force_refresh).get(int(table_id))
    if not row:
        return "[CẦN DATA]", None, "—"

    raw = str(row.get("GIÁ TRỊ") or "").strip()
    unit = str(row.get("ĐƠN VỊ") or "").strip()
    date = str(row.get("KỲ BÁO CÁO") or "").strip()

    numeric_value = None
    if raw:
        # '1.234,5' kiểu Việt → 1234.5 ; '−3,1' → -3.1
        norm = raw.replace("\u2212", "-").replace("–", "-").replace(" ", "").replace("\xa0", "")
        norm = norm.replace(".", "").replace(",", ".")
        try:
            numeric_value = float(norm)
        except ValueError:
            numeric_value = None

    display_value = raw if raw else "—"
    unit_suffix = f" {unit}" if unit and unit != "—" else ""
    date_suffix = f" ({date})" if date and date != "—" else ""
    return f"{display_value}{unit_suffix}{date_suffix}", numeric_value, date


def _range_label(metric_dates: List[str]) -> str:
    valid_dates = [d for d in metric_dates if d and d != "—"]
    if not valid_dates:
        return "Theo nguồn"
    return f"Mới nhất: {max(valid_dates)}"

def fetch_pulse_matrix(force_refresh: bool = False) -> Dict[str, Any]:
    matrix_rows = []
    for code, cfg in PULSE_METRICS.items():
        gdp, gdp_value, gdp_date = _format_latest_metric(cfg["gdp"], force_refresh)
        inflation, inflation_value, inflation_date = _format_latest_metric(cfg["inflation"], force_refresh)
        rate, rate_value, rate_date = _format_latest_metric(cfg["rate"], force_refresh)
        unemployment, unemployment_value, unemployment_date = _format_latest_metric(cfg["unemployment"], force_refresh)

        matrix_rows.append({
            "NỀN KINH TẾ": cfg["label"],
            "GDP": gdp,
            "GDP_VALUE": gdp_value,
            "LẠM PHÁT": inflation,
            "LẠM_PHÁT_VALUE": inflation_value,
            "LÃI SUẤT": rate,
            "LÃI_SUẤT_VALUE": rate_value,
            "THẤT NGHIỆP": unemployment,
            "THẤT_NGHIỆP_VALUE": unemployment_value,
            "DẢI QUAN SÁT": _range_label([gdp_date, inflation_date, rate_date, unemployment_date]),
            "SOURCE_IDS": {
                "GDP": cfg["gdp"],
                "LẠM PHÁT": cfg["inflation"],
                "LÃI SUẤT": cfg["rate"],
                "THẤT NGHIỆP": cfg["unemployment"],
            },
        })

    return {
        "success": True,
        "data": matrix_rows,
        "count": len(matrix_rows),
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": "dulieukinhte.com"
    }


# ─────────────────────────── SGI / Lê Chí Phúc macro lens ───────────────────────────
# Bốn bảng chẩn đoán do `_System/fincept_bridge/goi_vimo.py` dựng sẵn tại máy. Ở đây CHỈ đọc
# tệp — không gọi mạng, không tính lại: một phép chấm chạy ở hai nơi là hai kết quả sớm muộn.
# Khoá cột đã đánh số từ nguồn vì QJsonObject xếp cột theo chữ cái.

SGI_DIR = os.path.expanduser("~/SECOND BRAIN-OBSIDIAN/_System/fincept_bridge/data")
SGI_BANG = {
    "chedo":  ("bang_chedo",  "CỔNG — Chẩn đoán chế độ & tỷ trọng tiền mặt"),
    "khoi":   ("bang_7khoi",  "Bảy khối chỉ báo — thứ tự và trọng số của tác giả"),
    "neo":    ("bang_neo",    "Neo lịch sử — con số hôm nay đứng ở đâu"),
    "tukiem": ("bang_tukiem", "Tự kiểm — track record, nghịch đảo, đơn hàng dữ liệu"),
}
SGI_CU_GIO = 12  # bảng cũ hơn ngần này thì nói rõ trong tiêu đề, không im lặng hiển thị


def fetch_sgi_table(which: str) -> Dict[str, Any]:
    key = (which or "").lower()
    if key not in SGI_BANG:
        return {"success": False, "error": "Khong ro bang SGI: %s" % which, "data": []}
    tep, ten = SGI_BANG[key]
    path = os.path.join(SGI_DIR, tep + ".json")
    if not os.path.exists(path):
        return {"success": False, "data": [],
                "error": ("Chua co %s.json — chay `python3 goi_nguon.py %s` trong "
                          "_System/fincept_bridge de dung bang." % (tep, "vimo_" + key))}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        return {"success": False, "data": [], "error": "Khong doc duoc %s: %s" % (tep, exc)}

    rows = doc.get("dong") or []
    if not rows:
        return {"success": False, "data": [],
                "error": "%s rong — nguon chua dung duoc bang nao." % tep}

    tuoi = ""
    try:
        moc = datetime.strptime(doc.get("cap_nhat", ""), "%Y-%m-%d %H:%M")
        gio = (datetime.now() - moc).total_seconds() / 3600
        if gio > SGI_CU_GIO:
            tuoi = " · DU LIEU CU %d gio" % int(gio)
    except ValueError:
        tuoi = " · khong ro moc cap nhat"

    return {"success": True, "data": rows,
            "title": "%s — %s%s" % (ten, doc.get("cap_nhat", "?"), tuoi),
            "note": doc.get("ghi_chu", ""), "as_of": doc.get("cap_nhat", "")}


def main():
    if len(sys.argv) < 2:
        print(json.dumps(fetch_leaderboard_rows("VN"), ensure_ascii=False, indent=2))
        return

    cmd = sys.argv[1].lower()
    refresh = "--refresh" in sys.argv

    if cmd in ["leaderboard", "top", "cards"]:
        country = sys.argv[2] if len(sys.argv) > 2 else "VN"
        result = fetch_leaderboard_rows(country, force_refresh=refresh)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd in ["series", "max_series", "history"]:
        target = sys.argv[2] if len(sys.argv) > 2 else "268"
        result = fetch_max_series_rows(target, force_refresh=refresh)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd in ["sgi", "chedo", "khoi", "neo", "tukiem"]:
        which = sys.argv[2] if (cmd == "sgi" and len(sys.argv) > 2) else cmd
        print(json.dumps(fetch_sgi_table(which), ensure_ascii=False, indent=2))

    elif cmd in ["pulse", "matrix"]:
        result = fetch_pulse_matrix(force_refresh=refresh)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        # Fallback: treat first arg as country or table_id
        if cmd.upper() in ["VN", "US", "CN", "EU"]:
            result = fetch_leaderboard_rows(cmd, force_refresh=refresh)
        elif cmd.isdigit():
            result = fetch_max_series_rows(cmd, force_refresh=refresh)
        else:
            result = fetch_leaderboard_rows("VN", force_refresh=refresh)
        print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
