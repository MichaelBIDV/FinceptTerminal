#!/usr/bin/env python3
"""
Fincept Terminal, tab VĨ MÔ (MACRO): builder dữ liệu offline cho bản clone WiData Dashboard.

Hợp đồng: SECOND BRAIN-OBSIDIAN/_System/fincept_bridge/widata_clone_spec/DESIGN.md (§3, §4, §8, §16 C1/C4).
Gói A, TASKS §3.A. Đọc layout_const.json (hình thức) + series_map.json (sid -> nguồn của ta) + kho cục bộ, sinh:

    <state>/builds/<YYYYmmdd-HHMMSS>/{manifest.json, layouts.json, dash_<dash_id>.json (10), dash_single.json}
    <state>/current.json = {"schema", "build": "<đường dẫn tuyệt đối>", "manifest": {...}}   (os.replace)

USAGE
    python3 widata_clone.py build     [--policy allow_wigroup|strict] [--out DIR]
    python3 widata_clone.py status    [--out DIR]
    python3 widata_clone.py inventory [--policy allow_wigroup|strict] [--json] [--sids]
    python3 widata_clone.py scrub     [--out DIR]   (thay tên miền API trong các bản dựng cũ bằng nhãn trung tính)
Env: WDC_SYSTEM_DIR (thay ~/SECOND BRAIN-OBSIDIAN/_System), WDC_STATE_DIR (thư mục state; --out thắng env),
     WDC_DATA_DIR (thư mục layout_const.json + series_map.json), WDC_TODAY=YYYY-MM-DD (ngày tính 'lagged').

stdout: đúng MỘT JSON nhỏ {"ok": true, "build": "...", "counts": {...}}; lỗi -> {"error", "error_code"} (exit 0).
Log ra stderr. Stdlib, không mạng, không đọc capture của WiData. Mặc định source_policy = allow_wigroup (§16 C1).
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import sys
import time
from collections import Counter, OrderedDict
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import widata_clone_data as wd  # noqa: E402

SCHEMA = "widata_clone/1"
BUILDER_VERSION = "1.0.0"
KEEP_BUILDS = 5
LOCK_WAIT_S = 120
DASH_WARN_BYTES = 5 * 1024 * 1024
DEFAULT_POLICY = "allow_wigroup"
FORBIDDEN_KEYS = ("data", "minPoint", "maxPoint", "dataMin", "dataMax", "tickPositions", "labels", "t0", "t1",
                  "n_points", "lingo_desc", "lingo_note", "lingo_freq")
_BUILD_RE = re.compile(r"^\d{8}-\d{6}(?:-\d+)?$")
USAGE = ("Cách dùng: widata_clone.py build [--policy allow_wigroup|strict] [--out DIR] | status [--out DIR] | "
         "inventory [--policy P] [--json] [--sids] | scrub [--out DIR]")


class WdcError(Exception):
    def __init__(self, msg, code="build_failed"):
        super().__init__(msg)
        self.code = code


def log(msg):
    print("[widata_clone] " + str(msg), file=sys.stderr, flush=True)


# ── Đường dẫn, ngày, tham số ────────────────────────────────────────────────


def system_dir():
    env = os.environ.get("WDC_SYSTEM_DIR")
    return Path(env).expanduser() if env else Path.home() / "SECOND BRAIN-OBSIDIAN" / "_System"


def data_dir():
    env = os.environ.get("WDC_DATA_DIR")
    return Path(env).expanduser() if env else system_dir() / "fincept_bridge" / "data" / "widata_clone"


def state_dir(out=None):
    if out:
        return Path(out).expanduser().resolve()
    env = os.environ.get("WDC_STATE_DIR")
    return Path(env).expanduser().resolve() if env else system_dir() / "fincept_bridge" / "state" / "widata_clone"


def today_date():
    env = os.environ.get("WDC_TODAY")
    if env:
        try:
            return date.fromisoformat(env.strip())
        except ValueError:
            raise WdcError("WDC_TODAY không hợp lệ: %r, cần YYYY-MM-DD." % env, "bad_env") from None
    return datetime.now(wd.ICT).date()


def opt(argv, name, default=None):
    if name in argv:
        i = argv.index(name)
        if i + 1 >= len(argv):
            raise WdcError("Thiếu giá trị cho %s. %s" % (name, USAGE), "bad_args")
        return argv[i + 1]
    return default


def policy_of(argv):
    p = opt(argv, "--policy", DEFAULT_POLICY)
    if p not in wd.POLICIES:
        raise WdcError("source_policy lạ %r; dùng allow_wigroup hoặc strict." % p, "bad_args")
    return p


def load_json(path, what):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise WdcError("Thiếu %s (%s). Chạy gói P0/A để sinh lại." % (what, path), "missing_input") from None
    except ValueError as e:
        raise WdcError("%s hỏng JSON (%s): %s." % (what, path, e), "bad_input") from None


def dump(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def write_atomic(path, text):
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# ── Đầu vào ─────────────────────────────────────────────────────────────────


def load_inputs():
    d = data_dir()
    layout = load_json(d / "layout_const.json", "layout_const.json")
    smap = load_json(d / "series_map.json", "series_map.json")
    if not isinstance(layout.get("dashboards"), list) or not layout.get("tab_order"):
        raise WdcError("layout_const.json sai schema (thiếu dashboards/tab_order).", "bad_input")
    if smap.get("schema") != "widata_clone_map/1":
        raise WdcError("series_map.json sai schema; chạy lại widata_clone_map.py.", "bad_input")
    for k in FORBIDDEN_KEYS:
        if find_key(layout, k):
            raise WdcError("layout_const.json chứa khoá cấm %r (DESIGN §8.1)." % k, "forbidden_key")
    rows = layout_rows(layout)
    lost = [sid for sid in rows if sid not in smap["series"]]
    if lost:
        raise WdcError("series_map.json thiếu %d sid của layout (vd %s); chạy lại widata_clone_map.py."
                       % (len(lost), lost[0]), "map_mismatch")
    return layout, smap, d


def find_key(obj, key):
    if isinstance(obj, dict):
        return key in obj or any(find_key(v, key) for v in obj.values())
    if isinstance(obj, list):
        return any(find_key(v, key) for v in obj)
    return False


def layout_rows(layout):
    """sid -> [(dash_id, card_key, pane_idx)] theo thứ tự xuất hiện (chỉ 10 bố cục)."""
    out = OrderedDict()
    for db in layout["dashboards"]:
        for c in db["cards"]:
            for pi, p in enumerate(c["panes"]):
                for s in p["series"]:
                    out.setdefault(s["sid"], []).append((db["id"], c["key"], pi))
    return out


def single_sids(layout):
    out = OrderedDict()
    for sc in layout.get("single_charts") or []:
        for s in sc["pane"]["series"]:
            out.setdefault(s["sid"], []).append(("single", sc["id"], 0))
    return out


# ── Đánh giá + đếm ──────────────────────────────────────────────────────────


def evaluate_all(smap, policy, today, warn):
    src = wd.Sources(smap, system_dir(), today, warn)
    ev = wd.Evaluator(src)
    recs, files = OrderedDict(), set()
    for sid, entry in smap["series"].items():
        rec, _cls, used = ev.evaluate(sid, entry, policy)
        recs[sid] = rec
        files.update(used)
    sources = {f: src.used[f] for f in sorted(files) if f in src.used}
    return recs, sources


def coverage(layout, recs):
    rows = layout_rows(layout)
    st = Counter(recs[sid]["status"] for sid in rows)
    st_rows = Counter(recs[sid]["status"] for sid, us in rows.items() for _ in us)
    cards = OrderedDict()
    for db in layout["dashboards"]:
        n_with = sum(1 for c in db["cards"]
                     if any(recs[s["sid"]]["status"] != "missing" for p in c["panes"] for s in p["series"]))
        cards[db["id"]] = [n_with, len(db["cards"])]
    tier = Counter(recs[sid]["tier"] for sid in rows if recs[sid]["status"] != "missing")
    fill = lambda c: {k: c.get(k, 0) for k in ("ok", "partial", "missing")}  # noqa: E731
    return {"status": fill(st), "status_rows": fill(st_rows), "cards_with_data": cards,
            "tier": {k: tier.get(k, 0) for k in ("FACT-T1", "FACT-T2", "EST", "UNVERIFIED")}}


def counts_of(layout, recs, alt_recs, policy, alt):
    cov, alt_cov = coverage(layout, recs), coverage(layout, alt_recs)
    rows = layout_rows(layout)
    singles = single_sids(layout)
    n_cards = sum(len(db["cards"]) for db in layout["dashboards"])
    return {"dashboards": len(layout["dashboards"]), "cards": n_cards,
            "panes": sum(len(c["panes"]) for db in layout["dashboards"] for c in db["cards"]),
            "series_rows": sum(len(v) for v in rows.values()), "series_unique": len(rows),
            "status": cov["status"], "status_rows": cov["status_rows"], "tier": cov["tier"],
            "cards_with_data": cov["cards_with_data"],
            "coverage_alt": {"source_policy": alt, "status": alt_cov["status"], "status_rows": alt_cov["status_rows"],
                             "cards_with_data": alt_cov["cards_with_data"]},
            "single": {"charts": len(layout.get("single_charts") or []), "series_rows": sum(len(v) for v in
                                                                                           singles.values()),
                       "series_unique": len(singles),
                       "status": dict(Counter(recs[s]["status"] for s in singles))}}


def missing_list(layout, recs, smap):
    use = OrderedDict()
    for sid, us in list(layout_rows(layout).items()) + list(single_sids(layout).items()):
        use.setdefault(sid, []).extend(("single:" + k) if d == "single" else k for d, k, _ in us)
    out = []
    for sid, cards in use.items():
        r = recs[sid]
        if r["status"] == "missing":
            out.append({"sid": sid, "cards": list(OrderedDict.fromkeys(cards)), "reason": r["reason_code"],
                        "planned_source": smap["series"][sid].get("planned_source") or ""})
    return out


def data_to(layout, recs):
    xs = [recs[s]["as_of"] for s in layout_rows(layout) if recs[s]["status"] != "missing"]
    return max(xs) if xs else None


# ── build ────────────────────────────────────────────────────────────────────


class Lock:
    def __init__(self, path):
        self.path, self.fd = path, None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = open(self.path, "w")
        t0 = time.time()
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.time() - t0 > LOCK_WAIT_S:
                    self.fd.close()
                    raise WdcError("Builder khác đang chạy (khoá %s); thử lại sau." % self.path, "locked") from None
                time.sleep(0.5)

    def __exit__(self, *exc):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        self.fd.close()


def new_build_dir(root):
    stamp = datetime.now(wd.ICT).strftime("%Y%m%d-%H%M%S")
    d, i = root / "builds" / stamp, 0
    while d.exists():
        i += 1
        d = root / "builds" / ("%s-%d" % (stamp, i))
    d.mkdir(parents=True)
    return d


def prune(root, keep_path):
    bdir = root / "builds"
    olds = sorted((p for p in bdir.iterdir() if p.is_dir() and _BUILD_RE.match(p.name)), key=lambda p: p.name)
    for p in olds[:-KEEP_BUILDS]:
        if p.resolve() != keep_path.resolve():
            shutil.rmtree(p, ignore_errors=True)


def dash_doc(dash_id, sids, recs, generated):
    return {"schema": SCHEMA, "dash_id": dash_id, "generated": generated,
            "series": OrderedDict((sid, recs[sid]) for sid in sids)}


def cmd_build(argv):
    policy = policy_of(argv)
    alt = "strict" if policy == "allow_wigroup" else "allow_wigroup"
    root = state_dir(opt(argv, "--out"))
    today = today_date()
    warnings = []
    with Lock(root / ".lock"):
        layout, smap, ddir = load_inputs()
        recs, sources = evaluate_all(smap, policy, today, warnings.append)
        alt_recs, _ = evaluate_all(smap, alt, today, lambda m: None)
        generated = datetime.now(wd.ICT).isoformat(timespec="seconds")
        bdir = new_build_dir(root)
        lay = OrderedDict([("schema", SCHEMA)])
        lay.update((k, v) for k, v in layout.items())
        lay["single_charts_data"] = "dash_single.json"
        write_atomic(bdir / "layouts.json", dump(lay))
        files = {}
        for db in layout["dashboards"]:
            sids = OrderedDict.fromkeys(s["sid"] for c in db["cards"] for p in c["panes"] for s in p["series"])
            name = "dash_%s.json" % db["id"]
            text = dump(dash_doc(db["id"], sids, recs, generated))
            if len(text.encode("utf-8")) > DASH_WARN_BYTES:
                warnings.append("%s lớn hơn 5 MB (%d byte)." % (name, len(text.encode("utf-8"))))
            write_atomic(bdir / name, text)
            files[db["id"]] = name
        write_atomic(bdir / "dash_single.json", dump(dash_doc("single", single_sids(layout), recs, generated)))
        counts = counts_of(layout, recs, alt_recs, policy, alt)
        if not sources:
            warnings.append("Không đọc được tệp nguồn nào.")
        if not any("/collected/" in k for k in sources):
            warnings.append("Kho collected/ của clone chưa có chuỗi nào được dùng (gói A2 chưa chạy hoặc chưa ghi).")
        manifest = OrderedDict([
            ("schema", SCHEMA), ("generated", generated), ("builder_version", BUILDER_VERSION),
            ("source_policy", policy), ("data_to", data_to(layout, recs)),
            ("layout_const_sha256", wd.sha256_file(ddir / "layout_const.json")),
            ("series_map_sha256", wd.sha256_file(ddir / "series_map.json")),
            ("counts", counts), ("warnings", sorted(set(warnings))), ("missing", missing_list(layout, recs, smap)),
            ("sources", sources),
            ("files", {"layouts": "layouts.json", "dash": files, "single": "dash_single.json"})])
        write_atomic(bdir / "manifest.json", dump(manifest))
        cur = OrderedDict([("schema", SCHEMA), ("build", str(bdir.resolve())), ("manifest", manifest)])
        write_atomic(root / "current.json", dump(cur))
        prune(root, bdir)
    log("build %s: policy %s, sid ok/partial/missing %s, %d tệp nguồn"
        % (bdir.name, policy, counts["status"], len(sources)))
    total = [sum(v[0] for v in counts["cards_with_data"].values()), counts["cards"]]
    alt_total = [sum(v[0] for v in counts["coverage_alt"]["cards_with_data"].values()), counts["cards"]]
    return {"ok": True, "build": str(bdir.resolve()),
            "counts": {"source_policy": policy, "status": counts["status"], "status_rows": counts["status_rows"],
                       "cards_with_data": total,
                       "coverage_alt": {"source_policy": alt, "status": counts["coverage_alt"]["status"],
                                        "cards_with_data": alt_total}}}


def cmd_status(argv):
    root = state_dir(opt(argv, "--out"))
    cur = root / "current.json"
    if not cur.is_file():
        raise WdcError("Chưa có bản dựng (%s). Chạy: python3 widata_clone.py build" % cur, "no_build")
    doc = load_json(cur, "current.json")
    m = doc.get("manifest") or {}
    gen = datetime.fromisoformat(m["generated"]) if m.get("generated") else None
    age = round((datetime.now(wd.ICT) - gen).total_seconds() / 3600.0, 2) if gen else None
    c = m.get("counts") or {}
    return {"ok": True, "build": doc.get("build"), "build_exists": Path(str(doc.get("build"))).is_dir(),
            "generated": m.get("generated"), "age_hours": age, "source_policy": m.get("source_policy"),
            "data_to": m.get("data_to"),
            "counts": {k: c.get(k) for k in ("status", "status_rows", "cards_with_data", "coverage_alt")}}


def inventory_table(layout, counts, policy):
    alt = counts["coverage_alt"]
    lines = ["| Bố cục | Thẻ | Thẻ có số (%s) | Thẻ có số (%s) |" % (policy, alt["source_policy"]), "|---|---|---|---|"]
    for db in layout["dashboards"]:
        a, b = counts["cards_with_data"][db["id"]], alt["cards_with_data"][db["id"]]
        lines.append("| %s | %d | %d (%d %%) | %d (%d %%) |" % (db["name"], a[1], a[0], round(100 * a[0] / a[1]),
                                                               b[0], round(100 * b[0] / b[1])))
    ta = sum(v[0] for v in counts["cards_with_data"].values())
    tb = sum(v[0] for v in alt["cards_with_data"].values())
    lines.append("| **Tổng** | %d | %d | %d |" % (counts["cards"], ta, tb))
    return "\n".join(lines)


def cmd_inventory(argv):
    policy = policy_of(argv)
    alt = "strict" if policy == "allow_wigroup" else "allow_wigroup"
    layout, smap, _ = load_inputs()
    warnings = []
    recs, sources = evaluate_all(smap, policy, today_date(), warnings.append)
    alt_recs, _ = evaluate_all(smap, alt, today_date(), lambda m: None)
    counts = counts_of(layout, recs, alt_recs, policy, alt)
    if "--json" in argv:
        out = {"ok": True, "source_policy": policy, "counts": counts, "warnings": sorted(set(warnings)),
               "sources": sorted(sources)}
        if "--sids" in argv:
            out["sids"] = {sid: {"status": r["status"], "alt_status": alt_recs[sid]["status"], "tier": r["tier"],
                                 "as_of": r["as_of"], "reasons": r["partial_reasons"], "reason": r["reason_code"],
                                 "class": r["source_class"], "n": len(r["points"])} for sid, r in recs.items()}
        return out
    print(inventory_table(layout, counts, policy))
    print("\nsid (%s): %s ; dòng: %s ; %s: sid %s, dòng %s" % (
        policy, counts["status"], counts["status_rows"], alt, counts["coverage_alt"]["status"],
        counts["coverage_alt"]["status_rows"]))
    if "--sids" in argv:
        for sid, r in recs.items():
            print("%-60s %-8s %-8s %-10s %s %s" % (sid, r["status"], alt_recs[sid]["status"], r["tier"] or "-",
                                                   r["as_of"] or "-", ",".join(r["partial_reasons"]) or
                                                   (r["reason_code"] or "")))
    return None


def _neutral_all(o):
    if isinstance(o, str):
        return wd.neutral(o)
    if isinstance(o, list):
        return [_neutral_all(v) for v in o]
    if isinstance(o, dict):
        return OrderedDict((k, _neutral_all(v)) for k, v in o.items())
    return o


def cmd_scrub(argv):
    """Đợt 4 (DATA2 việc 5): các bản dựng cũ còn giữ (prune giữ 5) có thể ghi tên miền API trong source_name/notes;
    thay bằng nhãn trung tính của wd.neutral() tại chỗ, không đổi số liệu. Chỉ ghi tệp có thay đổi."""
    root = state_dir(opt(argv, "--out"))
    changed = []
    with Lock(root / ".lock"):
        paths = sorted((root / "builds").glob("*/*.json")) + [root / "current.json"]
        for path in paths:
            if not path.is_file():
                continue
            with open(path, encoding="utf-8") as f:
                doc = json.load(f, object_pairs_hook=OrderedDict)
            new = _neutral_all(doc)
            if new != doc:
                write_atomic(path, dump(new))
                changed.append(str(path.relative_to(root)))
    return {"ok": True, "changed": len(changed), "files": changed}


def main(argv):
    cmds = {"build": cmd_build, "status": cmd_status, "inventory": cmd_inventory, "scrub": cmd_scrub}
    if not argv or argv[0] not in cmds:
        print(dump({"error": USAGE, "error_code": "bad_args"}))
        return 0
    try:
        out = cmds[argv[0]](argv[1:])
    except WdcError as e:
        out = {"error": str(e), "error_code": e.code}
    except wd.WdcDataError as e:
        out = {"error": str(e), "error_code": "data_error"}
    except Exception as e:  # noqa: BLE001  (lỗi lạ vẫn phải trả JSON cho EconomicsService)
        log("lỗi không lường: %r" % (e,))
        out = {"error": "Builder lỗi không lường (%s: %s). Xem stderr." % (type(e).__name__, e),
               "error_code": "internal"}
    if out is not None:
        print(dump(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
