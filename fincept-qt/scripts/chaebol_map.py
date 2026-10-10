#!/usr/bin/env python3
"""
Fincept Terminal — Chaebol Map · VN30 (tab "chaebol_map"): dựng tệp cây JSON cho engine ChbDom.

Clone trang ~/Downloads/master_plan_v21_chaebol_vn30.html (Master Plan V21 · Bản Đồ Chaebol & VN30) + lớp dữ liệu
sống tới hôm nay. Hợp đồng: SECOND BRAIN-OBSIDIAN/_System/fincept_bridge/chaebol_map_spec/DESIGN.md (§1, §2, §4, §6);
hướng dẫn viết tab: chaebol_map_spec/api_python.md.

USAGE
    python3 chaebol_map.py build     [--mode live|v21] [--out DIR]
    python3 chaebol_map.py status    [--out DIR]
    python3 chaebol_map.py inventory [--mode live|v21]
Env: CHB_SYSTEM_DIR (thay ~/SECOND BRAIN-OBSIDIAN/_System), CHB_TODAY=YYYY-MM-DD, CHB_STATE_DIR (thay --out mặc
định $B/state/chaebol_map; --out thắng env).

build ghi <out>/builds/<YYYYmmdd-HHMMSS>/{manifest.json, shell.json, tab_<id>.json, inc/<key>.json, export.csv?},
rồi <out>/current.json = {"build": "<đường dẫn tuyệt đối>", "manifest": {…}} (atomic), giữ 3 build gần nhất.
stdout: đúng MỘT JSON {"schema":"chaebol_map/1","build":"<dir>","manifest":{…}}; lỗi → {"error": "…"} (exit 0).
Log ra stderr. Stdlib, không mạng; kho dữ liệu chỉ đọc (SQLite nếu có mở mode=ro ở chaebol_map_data).

Tab builder: bảng TAB_BUILDERS {tab_id: (module, hàm)}. Module chưa có → tab giữ chỗ "[chưa dựng]"; hàm ném lỗi →
tab "[lỗi dựng]" + cảnh báo (build vẫn thành công). Hợp đồng hàm: build_<tab>(ctx) → {"root": node,
"states": [{"key", "default", "options"}], "inc": {key: node}, "csv": [...]?}.
"""
from __future__ import annotations

import contextlib
import csv
import importlib
import io
import json
import os
import re
import shutil
import sys
import time
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import chaebol_map_dom as dom  # noqa: E402
import chaebol_map_shell as shell  # noqa: E402

SCHEMA = "chaebol_map/1"
SOURCE_MD5 = "4f647f7a458e4c249ae05d4407f8ba70"
SOURCE_URL = "http://localhost:9000/dl/master_plan_v21_chaebol_vn30.html"
ICT = timezone(timedelta(hours=7))
KEEP_BUILDS = 3
V21_DATA_TO = "2026-05-08"          # phiên cuối của dữ liệu V21 (FLOW 08/05; footer "As of 12/05/2026")
USAGE = ("Cách dùng: chaebol_map.py build [--mode live|v21] [--out DIR] [--tabs id,id] | status [--out DIR] | "
         "inventory [--mode live|v21]")

TAB_BUILDERS = {
    "vnindex": ("chaebol_map_tab_index", "build_vnindex"),
    "vn30": ("chaebol_map_tab_index", "build_vn30"),
    "codong": ("chaebol_map_tab_codong", "build_codong"),
    "overview": ("chaebol_map_tab_overview", "build_overview"),
    "chaebol": ("chaebol_map_tab_overview", "build_chaebol"),
    "tuanmuot": ("chaebol_map_tab_groups", "build_tuanmuot"),
    "sovico": ("chaebol_map_tab_groups", "build_sovico"),
    "phuong": ("chaebol_map_tab_groups", "build_phuong"),
    "bauthuy": ("chaebol_map_tab_groups", "build_bauthuy"),
    "eliminated": ("chaebol_map_tab_groups", "build_eliminated"),
    "screener": ("chaebol_map_tab_screener", "build_screener"),
    "portfolio": ("chaebol_map_tab_portfolio", "build_portfolio"),
    "changelog": ("chaebol_map_tab_claims", "build_changelog"),
    "claims54": ("chaebol_map_tab_claims", "build_claims54"),
    "catalyst": ("chaebol_map_tab_deep", "build_catalyst"),
    "portfolio25": ("chaebol_map_tab_portfolio", "build_portfolio25"),
    "deep6": ("chaebol_map_tab_deep", "build_deep6"),
    "audit": ("chaebol_map_tab_audit", "build_audit"),
    "vciq": ("chaebol_map_tab_vciq", "build_vciq"),       # chỉ mode live (05/10/2026), xem LIVE_TABS
}
# Tab chỉ có ở mode live, nối sau 18 tab V21 (mode v21 giữ đúng 18 tab của trang gốc).
LIVE_TABS = (("vciq", "★ 15 · VIETCAP IQ", "◈"),)

# DESIGN §4 + coverage_critic §2: khoá state chuẩn → (tab, mặc định, số lựa chọn | None = không kiểm số).
EXPECTED_STATES = {
    "codong.tk": ("codong", "VIC", 48), "codong.sub": ("codong", "phase_info", 11),
    "map.axis": ("chaebol", "ALL", 4), "map.tier": ("chaebol", "ALL", 5),
    "grp.tuanmuot.tk": ("tuanmuot", None, 6), "grp.sovico.tk": ("sovico", None, 2),
    "grp.phuong.tk": ("phuong", None, 2), "grp.bauthuy.tk": ("bauthuy", None, 4),
    "grp.eliminated.tk": ("eliminated", None, 3),
    "scr.sort": ("screener", "perf", None), "scr.dir": ("screener", "desc", 2), "scr.phase": ("screener", "ALL", 8),
    "scr.sig": ("screener", "ALL", 4), "scr.chaebol": ("screener", "ALL", 4),
    "rs.cat": ("changelog", "ALL", 10), "cp.filter": ("changelog", "ALL", 4),
    "c54.pri": ("claims54", "ALL", 5), "c54.ch": ("claims54", "ALL", 23), "p25.cat": ("portfolio25", "ALL", 5),
    "d24.sel": ("deep6", "Vingroup", 24), "d24.axis": ("deep6", "ALL", 4), "d24.tier": ("deep6", "ALL", 5),
    "aud.pipe": ("audit", "P0_DAILY_PRICE", 11),
}
# Chỉ live (tab codong 109 mã, 05/10/2026): đè EXPECTED_STATES; None = số lựa chọn theo live_opts (vũ trụ lúc dựng).
EXPECTED_STATES_LIVE = {"codong.tk": ("codong", "VIC", None), "codong.win": ("codong", "MAX", 3)}
CODONG_WINS = ["MAX", "5Y", "2Y"]
_BUILD_RE = re.compile(r"^\d{8}-\d{6}(?:-\d+)?$")
_DOSSIER_RE = re.compile(r"^cap_nhat_(\d{4}-\d{2}-\d{2})\.json$")


class ChbError(Exception):
    """Lỗi có thông điệp tiếng Việt cho người dùng (chuyện gì + cần làm gì)."""


def log(msg):
    print("[chaebol_map] " + str(msg), file=sys.stderr, flush=True)


# ── Đường dẫn / ngày ────────────────────────────────────────────────────────


def system_dir():
    env = os.environ.get("CHB_SYSTEM_DIR")
    return Path(env).expanduser() if env else Path.home() / "SECOND BRAIN-OBSIDIAN" / "_System"


def bridge_dir():
    return system_dir() / "fincept_bridge"


def state_dir(out=None):
    if out:
        return Path(out).expanduser().resolve()
    env = os.environ.get("CHB_STATE_DIR")
    return Path(env).expanduser().resolve() if env else bridge_dir() / "state" / "chaebol_map"


def today_date():
    env = os.environ.get("CHB_TODAY")
    if env:
        try:
            return date.fromisoformat(env.strip())
        except ValueError:
            raise ChbError("CHB_TODAY không hợp lệ: %r — cần dạng YYYY-MM-DD." % env) from None
    return datetime.now(ICT).date()


# ── Ngữ cảnh cho tab builder ────────────────────────────────────────────────


class Ctx:
    """ctx của build_<tab>(ctx): mode, today (date), live (bool), data (module chaebol_map_data | None; mode v21 → None),
    v21 (dict v21_const, {} nếu thiếu), dossier (dict hợp nhất | None), live_info (số sống của header),
    tabs [(id, label, icon)], tab (id đang dựng), sys_dir, bridge_dir; warn(msg). Truy cập ctx.x hoặc ctx["x"]."""

    def __init__(self, mode, today, tabs):
        self.mode = mode
        self.today = today
        self.live = mode == "live"
        self.tabs = tabs
        self.tab = None
        self.data = None
        self.v21 = {}
        self.dossier = None
        self.live_info = {}
        self.sys_dir = system_dir()
        self.bridge_dir = bridge_dir()
        self.warnings = []

    def warn(self, msg):
        text = ("[%s] " % self.tab if self.tab else "") + str(msg)
        if text not in self.warnings:
            self.warnings.append(text)
        log("cảnh báo: " + text)

    def __getitem__(self, k):
        return getattr(self, k)

    def get(self, k, default=None):
        return getattr(self, k, default)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_v21(ctx):
    p = ctx.bridge_dir / "data" / "chaebol_map" / "v21_const.json"
    if not p.is_file():
        ctx.warn("chưa có v21_const.json (%s) — tab builder dùng hằng tự chép" % p)
        return {}
    try:
        v = load_json(p)
    except (OSError, ValueError) as exc:
        ctx.warn("không đọc được v21_const.json: %s" % exc)
        return {}
    if not isinstance(v, dict):
        ctx.warn("v21_const.json không phải object JSON — bỏ qua")
        return {}
    md5 = v.get("source_md5") or (v.get("_meta") or {}).get("md5")
    if md5 and md5 != SOURCE_MD5:
        ctx.warn("v21_const md5 %s ≠ %s — trang gốc đã đổi, cần trích lại" % (md5, SOURCE_MD5))
    return v


def load_dossier(ctx):
    """Dossier cập nhật (DESIGN §7). Ưu tiên chaebol_map_data.dossier() (gộp mảnh .<tab>.json, bỏ mục thiếu src);
    không có module → tự đọc tệp hợp nhất mới nhất ≤ hôm nay $SYS/knowledge_os/chaebol_map/cap_nhat_<ngày>.json."""
    fn = getattr(ctx.data, "dossier", None) if ctx.data is not None else None
    if callable(fn):
        try:
            doc = fn()
        except Exception as exc:
            ctx.warn("chaebol_map_data.dossier lỗi: %s: %s" % (type(exc).__name__, exc))
            return None
        has = isinstance(doc, dict) and ((doc.get("_meta") or {}).get("date") or len(doc) > 1)
        return doc if has else None
    d = ctx.sys_dir / "knowledge_os" / "chaebol_map"
    best = None
    if d.is_dir():
        for f in d.iterdir():
            m = _DOSSIER_RE.match(f.name)
            if m and m.group(1) <= ctx.today.isoformat() and (best is None or m.group(1) > best[0]):
                best = (m.group(1), f)
    if best is None:
        ctx.warn("chưa có dossier cap_nhat_<ngày>.json ở %s — live chỉ có số sống" % d)
        return None
    try:
        doc = load_json(best[1])
    except (OSError, ValueError) as exc:
        ctx.warn("dossier %s hỏng: %s" % (best[1].name, exc))
        return None
    if not isinstance(doc, dict) or doc.get("schema") != "chaebol_map_capnhat/1":
        ctx.warn("dossier %s sai schema (cần chaebol_map_capnhat/1)" % best[1].name)
        return None
    return doc


def load_data_module(ctx):
    try:
        return importlib.import_module("chaebol_map_data")
    except ModuleNotFoundError as exc:
        if exc.name == "chaebol_map_data":
            if ctx.live:
                ctx.warn("chưa có chaebol_map_data.py — số sống = [CẦN DATA]")
            return None
        ctx.warn("chaebol_map_data nhập lỗi: %s" % exc)
    except Exception as exc:  # module lỗi không được làm hỏng build
        ctx.warn("chaebol_map_data nhập lỗi: %s: %s" % (type(exc).__name__, exc))
    return None


def _as_plain(x):
    """V(value, text, tier, asof, src, note, unit) của chaebol_map_data → dict; số/dict/chuỗi giữ nguyên."""
    if x is None or isinstance(x, (dict, int, float, str)):
        return x
    if hasattr(x, "value"):
        return {k: getattr(x, k, None) for k in ("value", "text", "tier", "asof", "src", "note", "unit")}
    return None


def _norm_num_item(x):
    """Số sống → {"value", "date", "tier", "src", "kind"} (nhận số trần, dict hoặc V của chaebol_map_data)."""
    x = _as_plain(x)
    if x is None:
        return None
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return {"value": x, "date": None, "tier": None, "src": None}
    if isinstance(x, dict):
        pick = lambda *ks: next((x[k] for k in ks if x.get(k) is not None), None)  # noqa: E731
        v = pick("value", "v", "gia_tri", "close")
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return None
        return {"value": v, "date": pick("date", "asof", "as_of", "ngay", "ky"), "tier": pick("tier", "bac"),
                "src": pick("src", "nguon", "source"), "kind": pick("kind", "loai")}
    return None


def _norm_cong(x, today):
    if not x:
        return None
    if isinstance(x, str):
        return {"text": x, "as_of": today.isoformat(), "tier": None, "src": None}
    if isinstance(x, dict):
        text = x.get("text") or x.get("dong")
        if not text:
            return None
        return {"text": str(text), "as_of": x.get("as_of") or x.get("asof") or today.isoformat(),
                "tier": x.get("tier") or x.get("bac"), "src": x.get("src") or x.get("nguon")}
    return None


# Hàm của chaebol_map_data (api_data.md) dùng cho header: trường → (tên hàm, đối số).
LIVE_SOURCES = (("cong", "cong", ()), ("vnindex", "index_close", ("VNINDEX",)),
                ("usdvnd", "usd_vnd", ("nhtm_ban",)), ("data_to", "data_to", ()))


def live_numbers(ctx):
    """Số sống cho header + manifest: vnindex, usdvnd (giá bán NHTM), cong, data_to — nạp mềm từ chaebol_map_data.

    Nếu module có shell_live(ctx) → dict {"vnindex","usdvnd","cong","data_to"} thì dùng nó; ngược lại gọi từng hàm
    trong LIVE_SOURCES. Hàm thiếu / lỗi / trả [CẦN DATA] → None ([CẦN DATA] ở header) + cảnh báo.
    """
    out = {"vnindex": None, "usdvnd": None, "cong": None, "data_to": None}
    mod = ctx.data
    if mod is None:
        return out
    raw = {}
    custom = getattr(mod, "shell_live", None)
    if callable(custom):
        try:
            raw = custom(ctx) or {}
        except Exception as exc:
            ctx.warn("chaebol_map_data.shell_live lỗi: %s: %s" % (type(exc).__name__, exc))
            log(traceback.format_exc())
    else:
        for field, fname, args in LIVE_SOURCES:
            fn = getattr(mod, fname, None)
            if not callable(fn):
                ctx.warn("chaebol_map_data thiếu hàm %s()" % fname)
                continue
            try:
                raw[field] = fn(*args)
            except Exception as exc:
                ctx.warn("chaebol_map_data.%s lỗi: %s: %s" % (fname, type(exc).__name__, exc))
                log(traceback.format_exc())
    out["vnindex"] = _norm_num_item(raw.get("vnindex"))
    out["usdvnd"] = _norm_num_item(raw.get("usdvnd"))
    out["cong"] = _norm_cong(raw.get("cong"), ctx.today)
    dt = raw.get("data_to")
    out["data_to"] = dt if isinstance(dt, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", dt) else None
    for field, label in (("vnindex", "VN-Index"), ("usdvnd", "USD/VND"), ("cong", "CỔNG"), ("data_to", "data_to")):
        if out[field] is None:
            plain = _as_plain(raw.get(field))
            why = plain.get("note") if isinstance(plain, dict) else None
            ctx.warn("chaebol_map_data chưa trả %s → [CẦN DATA]%s" % (label, (" (" + str(why) + ")") if why else ""))
    return out


def data_warnings(ctx):
    """Chép cảnh báo của chaebol_map_data (warnings()) vào manifest, tiền tố [data]."""
    fn = getattr(ctx.data, "warnings", None) if ctx.data is not None else None
    if not callable(fn):
        return
    try:
        for w in fn() or []:
            ctx.warn("[data] " + str(w))
    except Exception as exc:
        ctx.warn("chaebol_map_data.warnings lỗi: %s" % exc)


# ── Chạy tab builder ────────────────────────────────────────────────────────


def _state_ok(st):
    return (isinstance(st, dict) and isinstance(st.get("key"), str) and isinstance(st.get("default"), str)
            and isinstance(st.get("options"), list) and all(isinstance(o, str) for o in st["options"]))


def _nested_scopes(node, skip_root=False):
    """Mọi khoá state khai trong 'scope' của các nút (không tính nút gốc khi skip_root) — khoá có scope lồng thì
    gốc tab KHÔNG mang nó, nếu không scope lồng mất tác dụng (vd codong.sub reset khi qua mã không có Deep-dive)."""
    out, stack = set(), [(node, skip_root)]
    while stack:
        n, skip = stack.pop()
        if not isinstance(n, dict):
            continue
        if not skip:
            out.update(k for k in (n.get("scope") or []) if isinstance(k, str))
        for c in n.get("k") or []:
            stack.append((c, False))
    return out


def normalize_result(tab_id, res, ctx):
    """Kiểm + chuẩn hoá kết quả builder. Gốc tab mang scope = mọi khoá state của tab (DESIGN §4)."""
    if isinstance(res, dict) and "t" in res and "root" not in res:
        res = {"root": res}
    if not isinstance(res, dict) or not isinstance(res.get("root"), dict) or "t" not in res["root"]:
        raise ChbError("build_%s phải trả {'root': node, …}" % tab_id)
    states = []
    for st in res.get("states") or []:
        if not _state_ok(st):
            raise ChbError("state sai dạng ở tab %s: %r (cần key/default/options là chuỗi)" % (tab_id, st))
        if st["default"] not in st["options"]:
            ctx.warn("state %s: mặc định %r không nằm trong options" % (st["key"], st["default"]))
        states.append({"key": st["key"], "tab": tab_id, "default": st["default"], "options": list(st["options"])})
    root = dict(res["root"])
    keys = [s["key"] for s in states]
    scope = list(root.get("scope") or [])
    inc_nodes = res.get("inc") or {}
    nested = _nested_scopes(res["root"], skip_root=True) | set().union(
        *(_nested_scopes(n) for n in inc_nodes.values() if isinstance(n, dict)))
    root["scope"] = scope + [k for k in keys if k not in scope and k not in nested]
    if not root["scope"]:
        del root["scope"]
    inc = res.get("inc") or {}
    if not isinstance(inc, dict) or not all(isinstance(v, dict) and "t" in v for v in inc.values()):
        raise ChbError("inc của tab %s phải là {khoá: node}" % tab_id)
    return {"root": root, "states": states, "inc": dict(inc), "csv": res.get("csv")}


def run_tab(tab_id, label, ctx):
    """→ (kết quả chuẩn hoá, trạng thái 'ok' | 'placeholder' | 'error')."""
    module, func = TAB_BUILDERS.get(tab_id, ("chaebol_map_tab_" + tab_id, "build_" + tab_id))
    ctx.tab = tab_id
    try:
        try:
            mod = importlib.import_module(module)
        except ModuleNotFoundError as exc:
            if exc.name != module:
                raise
            return ({"root": shell.placeholder_tab(tab_id, label, module, func), "states": [], "inc": {},
                     "csv": None}, "placeholder")
        fn = getattr(mod, func, None)
        if not callable(fn):
            return ({"root": shell.placeholder_tab(tab_id, label, module, func,
                                                   reason="module có nhưng thiếu hàm %s" % func),
                     "states": [], "inc": {}, "csv": None}, "placeholder")
        return normalize_result(tab_id, fn(ctx), ctx), "ok"
    except Exception as exc:
        msg = "%s: %s" % (type(exc).__name__, exc)
        ctx.warn("builder lỗi → tab giữ chỗ: " + msg)
        log(traceback.format_exc())
        return ({"root": shell.placeholder_tab(tab_id, label, module, func, error="Builder lỗi: " + msg),
                 "states": [], "inc": {}, "csv": None}, "error")
    finally:
        ctx.tab = None


# ── Dựng toàn bộ ────────────────────────────────────────────────────────────


def _inc_file(key, used):
    base = re.sub(r"[^A-Za-z0-9_.-]", "_", key.replace("/", "_"))
    name, n = base, 2
    while name in used:
        name, n = "%s-%d" % (base, n), n + 1
    used.add(name)
    return "inc/%s.json" % name


def _file_obj(root):
    obj, stats = dom.finalize(root)
    text = dom.dumps(obj)
    return text, stats


def _merge_stats(total, st, nbytes):
    total["nodes"] += st["nodes"]
    total["bytes"] += nbytes
    total["can_data"] += st["can_data"]
    total["upd"] += st["upd"]
    total["v21_marks"] += st["v21"]
    for k, v in st["tiers"].items():
        total["tiers"][k] = total["tiers"].get(k, 0) + v


# Khoá state → nơi lấy tập options chuẩn trong v21_const (giá trị THÔ của JSX, không phải nhãn nút). Oracle
# (harness/chaebol_map/oracle/build_plan.json) và ref/README bấm đúng các giá trị này (vd scr.chaebol=CHAEBOL_FRIENDLY).
OPTION_SOURCES = (
    ("codong.tk", "CauTrucCoDongTab.allTickers", None), ("codong.sub", "SUB_TABS_CHAEBOL", "id"),
    ("map.axis", "ChaebolMapEnrichment.jsx@L5385", None), ("map.tier", "ChaebolMapEnrichment.jsx@L5389", None),
    ("scr.phase", "ScreenerTab.jsx@L6297", "v"), ("scr.sig", "ScreenerTab.jsx@L6299", "v"),
    ("scr.chaebol", "ScreenerTab.jsx@L6301", "v"), ("rs.cat", "ResearchStackPanel.cats", None),
    ("cp.filter", "ClaimsPanel.jsx@L7036", None), ("c54.pri", "Claims54Tab.jsx@L6798", None),
    ("c54.ch", "Claims54Tab.chaebols", None), ("p25.cat", "ActionPortfolio25Tab.cats", None),
    ("d24.axis", "DeepDive6Tab.jsx@L6943", None), ("d24.tier", "DeepDive6Tab.jsx@L6947", None),
    ("aud.pipe", "DATA_AUDIT_PIPELINES", "id"),
)


def expected_options(v21):
    """{khoá state: [options chuẩn]} từ v21_const (DESIGN §4, coverage_critic §2). Mục v21 thiếu/sai dạng → bỏ qua.
    Thêm: grp.<id nhóm>.tk = mã trong CHAEBOL_GROUPS (mặc định = mã đầu), d24.sel = khoá DEEP_INSIGHT_24,
    scr.dir = desc/asc. scr.sort không kiểm (mặc định 'perf' cố ý không khớp cột)."""
    v21 = v21 or {}
    out = {"scr.dir": ["desc", "asc"]}
    for key, name, field in OPTION_SOURCES:
        raw = v21.get(name)
        try:
            vals = [str(x[field] if field else x) for x in raw] if isinstance(raw, list) else None
        except (KeyError, TypeError):
            vals = None
        if vals:
            out[key] = vals
    for g in v21.get("CHAEBOL_GROUPS") or []:
        try:
            out["grp.%s.tk" % g["id"]] = [str(t["tk"] if isinstance(t, dict) else t) for t in g["tickers"]]
        except (KeyError, TypeError):
            continue
    if isinstance(v21.get("DEEP_INSIGHT_24"), dict) and v21["DEEP_INSIGHT_24"]:
        out["d24.sel"] = [str(k) for k in v21["DEEP_INSIGHT_24"]]
    return out


def _coverage(states, built_tabs, v21=None, live_opts=None):
    """So state khai báo với EXPECTED_STATES (mặc định + số lựa chọn) và expected_options(v21) (đúng tập giá trị)
    cho các tab đã dựng thật (bỏ tab giữ chỗ). live_opts (chỉ live) = {khoá: [options chuẩn]}: khoá đó theo
    EXPECTED_STATES_LIVE, số lựa chọn None = len(live_opts[khoá]), tập giá trị = live_opts (thay v21_const)."""
    have, live_opts = {s["key"]: s for s in states}, live_opts or {}
    opts, expected = {**expected_options(v21), **live_opts}, dict(EXPECTED_STATES)
    expected.update({k: v for k, v in EXPECTED_STATES_LIVE.items() if k in live_opts})
    missing, mismatch = [], []
    for key, (tab, default, n) in expected.items():
        if tab not in built_tabs:
            continue
        s = have.get(key)
        if s is None:
            missing.append(key)
            continue
        want, live = opts.get(key), key in live_opts
        n = len(want) if (n is None and live) else n
        if default is None and want:
            default = want[0]                      # grp.<nhóm>.tk: mặc định = mã đầu nhóm
        if default is not None and s["default"] != default:
            mismatch.append("%s: mặc định %r ≠ %r" % (key, s["default"], default))
        if n is not None and len(s["options"]) != n:
            mismatch.append("%s: %d lựa chọn ≠ %d" % (key, len(s["options"]), n))
        if want:
            lack = [o for o in want if o not in s["options"]]
            extra = [o for o in s["options"] if o not in want]
            if lack or extra:
                head = "options lệch vũ trụ live:" if live else "options lệch v21_const " + chr(0x2014)   # v21: chữ cũ
                mismatch.append("%s: %s thiếu %r · thừa %r" % (key, head, lack[:6], extra[:6]))
    return {"missing": missing, "mismatch": mismatch}


def _live_opts(ctx, built_tabs):
    """Chỉ live, khi tab codong đã dựng: options chuẩn của state live (vũ trụ 109 mã A/B/C đo lúc dựng, 3 khung chart).
    Vũ trụ lỗi → cảnh báo, codong.tk kiểm như v21 (builder cũng lùi về 48 mã V21)."""
    if not ctx.live or "codong" not in built_tabs:
        return None
    out = {"codong.win": list(CODONG_WINS)}
    try:
        import chaebol_map_data_codong2 as owner          # nhập trễ: mode v21 không nạp module dữ liệu live
        out["codong.tk"] = list(owner.universe_groups(ctx.v21)["order"])
    except Exception as exc:
        ctx.warn("coverage live: không đọc được vũ trụ codong (%s: %s) → kiểm theo V21" % (type(exc).__name__, exc))
    return out


def _csv_rows(tab_id, csv_spec):
    """csv của tab: list dict | {"columns": [...], "rows": [[...]]} | list list (hàng đầu = tiêu đề)."""
    if not csv_spec:
        return [], []
    if isinstance(csv_spec, dict):
        cols = [str(c) for c in csv_spec.get("columns") or []]
        return cols, [dict(zip(cols, r)) for r in csv_spec.get("rows") or []]
    if isinstance(csv_spec, list) and csv_spec and isinstance(csv_spec[0], dict):
        cols = []
        for r in csv_spec:
            cols += [str(k) for k in r if str(k) not in cols]
        return cols, [{str(k): v for k, v in r.items()} for r in csv_spec]
    if isinstance(csv_spec, list) and csv_spec and isinstance(csv_spec[0], (list, tuple)):
        cols = [str(c) for c in csv_spec[0]]
        return cols, [dict(zip(cols, r)) for r in csv_spec[1:]]
    raise ChbError("csv của tab %s sai dạng" % tab_id)


def assemble(mode, today, only=None):
    """Dựng mọi tệp trong bộ nhớ → (files {tên: text}, manifest, csv_text | None).
    only = tập id tab cần dựng thật (--tabs, cho agent dựng/kiểm từng tab); tab khác là giữ chỗ."""
    t0 = time.monotonic()
    dom.configure(mode, today)
    ctx = Ctx(mode, today, [])
    ctx.v21 = load_v21(ctx)
    tabs, why = shell.tabs_from_v21(ctx.v21)
    if why and ctx.v21:
        ctx.warn(why)
    if ctx.live:
        tabs = list(tabs) + [t for t in LIVE_TABS if t[0] not in {x[0] for x in tabs}]
    ctx.tabs = tabs
    # mode v21 = chỉ hằng V21 (DESIGN §0.7): không nạp lớp số sống để builder không lỡ trộn số mới vào bản so pixel
    ctx.data = load_data_module(ctx) if ctx.live else None
    reset = getattr(ctx.data, "clear_cache", None) if ctx.data is not None else None
    if callable(reset):
        reset()                      # mỗi build đọc lại kho + cảnh báo mới (test chạy nhiều build một tiến trình)
    if ctx.live:
        ctx.dossier = load_dossier(ctx)
        ctx.live_info = live_numbers(ctx)
    files, per_tab, inc_map, states, placeholders, errors = {}, {}, {}, [], [], []
    csv_cols, csv_rows = ["tab"], []
    total = {"nodes": 0, "bytes": 0, "can_data": 0, "upd": 0, "v21_marks": 0, "tiers": {}}
    used_inc, built = set(), set()
    for tab_id, label, _icon in tabs:
        if only is not None and tab_id not in only:
            res, status = ({"root": shell.placeholder_tab(tab_id, label, *TAB_BUILDERS[tab_id],
                                                           reason="bỏ qua (--tabs)"),
                            "states": [], "inc": {}, "csv": None}, "placeholder")
        else:
            res, status = run_tab(tab_id, label, ctx)
        if status == "ok":
            built.add(tab_id)
        elif status == "placeholder":
            placeholders.append(tab_id)
        else:
            errors.append(tab_id)
        text, st = _file_obj(res["root"])
        files["tab_%s.json" % tab_id] = text
        pt = {"nodes": st["nodes"], "bytes": len(text.encode("utf-8"))}
        _merge_stats(total, st, pt["bytes"])
        for ikey, inode in res["inc"].items():
            if ikey in inc_map:
                ctx.warn("khoá inc trùng %s (tab %s) — bỏ bản sau" % (ikey, tab_id))
                continue
            fname = _inc_file(ikey, used_inc)
            itext, ist = _file_obj(inode)
            files[fname] = itext
            inc_map[ikey] = fname
            ib = len(itext.encode("utf-8"))
            pt["nodes"] += ist["nodes"]
            pt["bytes"] += ib
            _merge_stats(total, ist, ib)
        per_tab[tab_id] = pt
        for s in res["states"]:
            if any(o["key"] == s["key"] for o in states):
                ctx.warn("state %s khai báo trùng (tab %s) — bỏ bản sau" % (s["key"], tab_id))
                continue
            states.append(s)
        cols, rows = _csv_rows(tab_id, res.get("csv"))
        csv_cols += [c for c in cols if c not in csv_cols]
        csv_rows += [{"tab": tab_id, **r} for r in rows]
    coverage = _coverage(states, built, ctx.v21, _live_opts(ctx, built))
    if placeholders:
        ctx.warn("%d tab chưa dựng (giữ chỗ): %s" % (len(placeholders), ", ".join(placeholders)))
    data_warnings(ctx)
    shell_text, sst = _file_obj(shell.build_shell(ctx, tabs))
    files["shell.json"] = shell_text
    _merge_stats(total, sst, len(shell_text.encode("utf-8")))
    tab_state = {"key": "tab", "tab": None, "default": tabs[0][0], "options": [t[0] for t in tabs]}
    all_states = [tab_state] + states
    info = ctx.live_info or {}
    if ctx.live:
        cong = info.get("cong") or {
            "text": "CỔNG: [CẦN DATA — chưa đọc được CỔNG từ chaebol_map_data] · không kết luận per-mã",
            "as_of": today.isoformat(), "tier": None, "src": None}
        data_to = info.get("data_to")
    else:
        cong = None
        data_to = (ctx.v21.get("data_to") if isinstance(ctx.v21.get("data_to"), str) else None) or V21_DATA_TO
    buf = io.StringIO()                     # luôn có export.csv (chỉ tiêu đề khi chưa tab nào trả csv) → csv.rows
    w = csv.DictWriter(buf, fieldnames=csv_cols, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(csv_rows)
    csv_text = buf.getvalue()
    total["per_tab"] = per_tab
    total["shell"] = {"nodes": sst["nodes"], "bytes": len(shell_text.encode("utf-8"))}
    total["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
    manifest = {
        "schema": SCHEMA, "mode": mode, "generated": datetime.now(ICT).isoformat(timespec="seconds"),
        "today": today.isoformat(), "data_to": data_to, "source_md5": SOURCE_MD5, "source_url": SOURCE_URL,
        "render_mode": "as_intended", "cong": cong, "warnings": list(ctx.warnings),
        "tabs": [{"id": t[0], "label": t[1], "icon": t[2], "file": "tab_%s.json" % t[0],
                  "status": "ok" if t[0] in built else ("error" if t[0] in errors else "placeholder")} for t in tabs],
        "shell": "shell.json", "inc": inc_map,
        "inventory": {"states": all_states, "tabs": [t[0] for t in tabs], "inc": list(inc_map),
                      "coverage": coverage},
        "stats": total,
        "csv": {"file": "export.csv", "rows": len(csv_rows)},
    }
    return files, manifest, csv_text


def _atomic_write(path, text):
    tmp = path.with_name(".%s.tmp-%d" % (path.name, os.getpid()))
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _build_order(name):
    base, _, n = name.partition("-")[2].partition("-")
    return name[:8], base, int(n or 1)          # "…-101805" < "…-101805-2" < "…-101805-10"


def _prune(builds, keep_path):
    names = sorted((p.name for p in builds.iterdir() if p.is_dir() and _BUILD_RE.match(p.name)), key=_build_order)
    for name in names[:-KEEP_BUILDS]:
        p = builds / name
        if p.resolve() == keep_path.resolve():
            continue
        shutil.rmtree(p, ignore_errors=True)
    cutoff = time.time() - 3600
    for p in builds.iterdir():
        if p.name.startswith(".tmp-") and p.is_dir() and p.stat().st_mtime < cutoff:
            shutil.rmtree(p, ignore_errors=True)


def _latest_build(builds):
    names = sorted((p.name for p in builds.iterdir() if p.is_dir() and _BUILD_RE.match(p.name)), key=_build_order)
    return builds / names[-1] if names else None


def write_build(out, files, manifest, csv_text):
    builds = out / "builds"
    builds.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(ICT).strftime("%Y%m%d-%H%M%S")
    tmp = builds / (".tmp-%s-%d" % (stamp, os.getpid()))
    (tmp / "inc").mkdir(parents=True)
    prev = _latest_build(builds)
    for name, text in files.items():
        data = text.encode("utf-8")
        old = prev / name if prev else None
        try:   # bản dựng là bất biến sau khi đổi tên → tệp trùng byte với bản trước dùng chung bằng hard link
            if old and old.stat().st_size == len(data) and old.read_bytes() == data:
                os.link(old, tmp / name)
                continue
        except OSError:
            pass
        with open(tmp / name, "wb") as f:
            f.write(data)
    if csv_text is not None:
        with open(tmp / "export.csv", "w", encoding="utf-8-sig", newline="") as f:
            f.write(csv_text)
    with open(tmp / "manifest.json", "w", encoding="utf-8") as f:
        f.write(dom.dumps(manifest))
    final, n = builds / stamp, 2
    while final.exists():
        final, n = builds / ("%s-%d" % (stamp, n)), n + 1
    os.rename(tmp, final)
    _atomic_write(out / "current.json", dom.dumps({"build": str(final), "manifest": manifest}))
    _prune(builds, final)
    return final


# ── CLI ─────────────────────────────────────────────────────────────────────


def parse_args(argv):
    if len(argv) < 2:
        raise ChbError("Thiếu lệnh. " + USAGE)
    cmd = argv[1].strip().lower()
    if cmd not in ("build", "status", "inventory"):
        raise ChbError("Lệnh không hỗ trợ: %r. %s" % (argv[1], USAGE))
    opts = {"mode": "live", "out": None, "tabs": None}
    rest = list(argv[2:])
    while rest:
        flag = rest.pop(0)
        name = flag[2:] if flag.startswith("--") else None
        if name not in opts or not rest:
            raise ChbError("Tham số không hợp lệ: %s. %s" % (flag, USAGE))
        opts[name] = rest.pop(0)
    if opts["mode"] not in dom.MODES:
        raise ChbError("--mode phải là live hoặc v21, nhận %r. %s" % (opts["mode"], USAGE))
    return cmd, opts


def run(argv):
    cmd, opts = parse_args(argv)
    if cmd == "status":
        cur = state_dir(opts["out"]) / "current.json"
        if not cur.is_file():
            raise ChbError("Chưa có bản dựng nào ở %s — chạy 'chaebol_map.py build' trước." % cur.parent)
        doc = load_json(cur)
        if not doc.get("build") or not Path(doc["build"]).is_dir():
            raise ChbError("current.json trỏ tới thư mục đã mất (%s) — chạy build lại." % doc.get("build"))
        return {"schema": SCHEMA, "build": doc["build"], "manifest": doc.get("manifest")}
    today = today_date()
    only = None
    if opts["tabs"]:
        only = {t.strip() for t in opts["tabs"].split(",") if t.strip()}
        unknown = sorted(only - set(TAB_BUILDERS))
        if unknown:
            raise ChbError("--tabs có id lạ: %s. Id hợp lệ: %s" % (", ".join(unknown), ", ".join(TAB_BUILDERS)))
    files, manifest, csv_text = assemble(opts["mode"], today, only)
    if cmd == "inventory":
        return {"schema": SCHEMA, "mode": manifest["mode"], "inventory": manifest["inventory"],
                "warnings": manifest["warnings"]}
    final = write_build(state_dir(opts["out"]), files, manifest, csv_text)
    log("dựng xong %s (%d nút, %d byte, %d ms)" % (final, manifest["stats"]["nodes"], manifest["stats"]["bytes"],
                                                   manifest["stats"]["elapsed_ms"]))
    return {"schema": SCHEMA, "build": str(final), "manifest": manifest}


def emit(obj, stream=None):
    stream = stream or sys.stdout
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False, default=str)
    buf = getattr(stream, "buffer", None)
    if buf is not None:
        buf.write(text.encode("utf-8") + b"\n")
        buf.flush()
    else:
        stream.write(text + "\n")
        stream.flush()


def main(argv=None):
    argv = sys.argv if argv is None else argv
    real_stdout = sys.stdout
    try:
        # print() lạc của tab builder / lớp dữ liệu sang stderr: stdout chỉ còn đúng một JSON (DESIGN §2.1)
        with contextlib.redirect_stdout(sys.stderr):
            out = run(argv)
    except ChbError as exc:
        out = {"error": str(exc)}
    except Exception as exc:  # không để traceback thay phong bì JSON
        log(traceback.format_exc())
        out = {"error": "Lỗi nội bộ chaebol_map.py: %s: %s — xem stderr, báo người dựng module." % (
            type(exc).__name__, exc)}
    emit(out, real_stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
