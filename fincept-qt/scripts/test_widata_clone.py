#!/usr/bin/env python3
"""
Test builder bản clone WiData (gói A, TASKS §3.A; mục builder của DESIGN §10.3).

Chạy: python3 scripts/test_widata_clone.py      (/usr/bin/python3 3.9 hoặc venv-numpy2 3.11)
Hai nhóm: (1) dữ liệu thật (layout_const, series_map, kho cục bộ; tự bỏ qua nếu thiếu tệp đầu vào), build vào thư
mục tạm, không đụng state thật; (2) fixture tổng hợp cho mốc thời gian, luật trạng thái, policy, ưu tiên collected.
Không mạng: test 'no_socket' thay socket.socket bằng hàm ném lỗi rồi dựng trong cùng tiến trình.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import widata_clone as wc  # noqa: E402
import widata_clone_data as wd  # noqa: E402

SYS = Path(os.environ.get("WDC_SYSTEM_DIR", str(Path.home() / "SECOND BRAIN-OBSIDIAN" / "_System")))
DATA = SYS / "fincept_bridge" / "data" / "widata_clone"
TODAY = "2026-10-04"
FORBIDDEN = wc.FORBIDDEN_KEYS
BAD_STRINGS = ("api/internal", "widata" + ".vn", "wichart" + ".vn", "dulieukinhte" + ".com")
# đợt 4 (DATA2 việc 5): tệp dữ liệu và state không ghi tên miền API của WiGroup (mã nguồn collector được giữ URL)
API_HOST = re.compile("wichart" + r"[.]vn|vietnam[ ]?biz|wichartapi", re.I)
SCRIPTS = ("widata_clone.py", "widata_clone_data.py", "widata_clone_map.py")
HAVE_REAL = (DATA / "layout_const.json").is_file() and (DATA / "series_map.json").is_file()
SPLIT_TITLES = ("VN_Lạm phát", "Chênh lệch lãi suất Mỹ và Việt Nam")


def run_cli(args, env_extra):
    env = dict(os.environ, WDC_TODAY=TODAY, **env_extra)
    p = subprocess.run([sys.executable, str(HERE / "widata_clone.py")] + args, capture_output=True, text=True,
                       env=env, timeout=600)
    lines = [ln for ln in p.stdout.splitlines() if ln.strip()]
    return json.loads(lines[-1]) if lines else {"error": p.stderr}


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def keys_in(obj, acc):
    if isinstance(obj, dict):
        acc.update(obj.keys())
        for v in obj.values():
            keys_in(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            keys_in(v, acc)
    return acc


def build_files(bdir):
    return {p.name: load(p) for p in Path(bdir).glob("*.json")}


# ── (1) dữ liệu thật ─────────────────────────────────────────────────────────


@unittest.skipUnless(HAVE_REAL, "thiếu layout_const.json/series_map.json")
class RealData(unittest.TestCase):
    tmp = None
    out = {}

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="wdc_test_"))
        cls.layout = load(DATA / "layout_const.json")
        cls.smap = load(DATA / "series_map.json")
        for pol in ("allow_wigroup", "strict"):
            res = run_cli(["build", "--policy", pol, "--out", str(cls.tmp / pol)], {})
            cls.out[pol] = res

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def files(self, pol):
        self.assertTrue(self.out[pol].get("ok"), self.out[pol])
        return build_files(self.out[pol]["build"])

    def test_layout_counts_492_331(self):
        rows = wc.layout_rows(self.layout)
        n_cards = sum(len(d["cards"]) for d in self.layout["dashboards"])
        n_panes = sum(len(c["panes"]) for d in self.layout["dashboards"] for c in d["cards"])
        self.assertEqual((len(self.layout["dashboards"]), n_cards, n_panes), (10, 108, 110))
        self.assertEqual(sum(len(v) for v in rows.values()), 492)
        self.assertEqual(len(rows), 331)

    def test_sid_unique_per_key(self):
        tuples = Counter()
        for sid in wc.layout_rows(self.layout):
            parts = sid.split("|")
            self.assertEqual(len(parts), 4, sid)
            self.assertNotIn(parts[0], ("stk", "null"), sid)
            tuples[tuple(parts)] += 1
        self.assertTrue(all(v == 1 for v in tuples.values()))
        self.assertEqual(len(tuples), 331)

    def test_pane2_refs_complete(self):
        need = {"sid", "si", "name_raw", "type", "stacking", "stack", "slot", "color", "negativeColor", "swatch2",
                "lineWidth", "dashStyle", "marker", "zIndex", "unit", "date_type", "kind"}
        p2 = [s for d in self.layout["dashboards"] for c in d["cards"] if len(c["panes"]) == 2
              for s in c["panes"][1]["series"]]
        self.assertEqual(len(p2), 5)
        for s in p2:
            self.assertFalse(need - set(s), s["sid"])
        self.assertIn("vn|227|lamphat_yoy|monthly-yoy", {s["sid"] for s in p2})

    def test_series_map_covers_layout_and_single(self):
        rows, singles = wc.layout_rows(self.layout), wc.single_sids(self.layout)
        self.assertFalse(set(rows) - set(self.smap["series"]))
        self.assertFalse(set(singles) - set(self.smap["series"]))
        e = self.smap["series"]["vn|227|lamphat_yoy|monthly-yoy"]
        self.assertIn("CHƯA XÁC MINH", e["planned_source"])
        for sid, e in self.smap["series"].items():
            self.assertIn(e["reason_if_missing"], wd.REASON_CODES, sid)
        p = subprocess.run([sys.executable, str(HERE / "widata_clone_map.py"), "--check"], capture_output=True,
                           text=True, timeout=120)
        self.assertEqual(p.returncode, 0, "series_map.json lệch với widata_clone_map.py: " + p.stdout + p.stderr)

    def test_schema_and_counts(self):
        for pol in ("allow_wigroup", "strict"):
            f = self.files(pol)
            m = f["manifest.json"]
            self.assertEqual(m["schema"], wc.SCHEMA)
            self.assertEqual(m["source_policy"], pol)
            c = m["counts"]
            self.assertEqual((c["dashboards"], c["cards"], c["panes"], c["series_rows"], c["series_unique"]),
                             (10, 108, 110, 492, 331))
            self.assertEqual(sum(c["status"].values()), 331)
            self.assertEqual(sum(c["status_rows"].values()), 492)
            self.assertEqual(c["coverage_alt"]["source_policy"], "strict" if pol == "allow_wigroup" else
                             "allow_wigroup")
            self.assertEqual(sum(c["coverage_alt"]["status"].values()), 331)
            self.assertEqual(c["single"]["series_unique"], 3)
            for d in self.layout["tab_order"]:
                self.assertIn("dash_%s.json" % d, f)
            self.assertIn("dash_single.json", f)
            self.assertEqual(f["layouts.json"]["schema"], wc.SCHEMA)
            self.assertEqual(f["layouts.json"]["single_charts"][0]["id"], "mai3_09")
            cur = load(Path(self.out[pol]["build"]).parent.parent / "current.json")
            self.assertEqual(cur["build"], self.out[pol]["build"])
            self.assertEqual(cur["manifest"], m)
            for sid, r in self._all(f).items():
                self.assertIn(r["status"], ("ok", "partial", "missing"))
                self.assertIn(r["freq"], ("D", "W", "M", "Q", "Y", "YTD", "TP"))
                for k in ("tier", "tier_spans", "partial_reasons", "unit", "points", "as_of", "breaks", "meta",
                          "reason"):
                    self.assertIn(k, r, sid)

    def _all(self, f):
        out = {}
        for name, doc in f.items():
            if name.startswith("dash_"):
                self.assertEqual(doc["schema"], wc.SCHEMA)
                out.update(doc["series"])
        return out

    def test_status_from_real_numbers(self):
        for pol in ("allow_wigroup", "strict"):
            for sid, r in self._all(self.files(pol)).items():
                has = any(v is not None for _, v in r["points"])
                if r["status"] == "missing":
                    self.assertFalse(has, sid)
                    self.assertIn(r["reason_code"], wd.REASON_CODES, sid)
                    self.assertTrue(r["reason"].startswith("[CẦN DATA]"), sid)
                else:
                    self.assertTrue(has, sid)
                    self.assertEqual(r["status"] == "partial", bool(r["partial_reasons"]), sid)
                    self.assertIsNotNone(r["tier"], sid)
                    self.assertTrue(r["meta"]["source_ref"], sid)

    def test_time_convention(self):
        for sid, r in self._all(self.files("allow_wigroup")).items():
            ts = [t for t, _ in r["points"]]
            self.assertEqual(ts, sorted(set(ts)), sid)
            for t in ts:
                self.assertEqual(t % 86400000, 0, sid)
                d = datetime.fromtimestamp(t / 1000, timezone.utc).date()
                if r["freq"] in ("M", "YTD", "Q", "Y"):
                    self.assertEqual(d, wd.period_end(d, r["freq"]), sid)
                if r["freq"] == "Q":
                    self.assertIn(d.month, (3, 6, 9, 12), sid)

    def test_cards_with_data_recount(self):
        for pol in ("allow_wigroup", "strict"):
            f = self.files(pol)
            m = f["manifest.json"]
            for db in self.layout["dashboards"]:
                ser = f["dash_%s.json" % db["id"]]["series"]
                n = sum(1 for c in db["cards"] if any(ser[s["sid"]]["status"] != "missing"
                                                      for p in c["panes"] for s in p["series"]))
                self.assertEqual(m["counts"]["cards_with_data"][db["id"]], [n, len(db["cards"])])
            alt = "strict" if pol == "allow_wigroup" else "allow_wigroup"
            self.assertEqual(m["counts"]["coverage_alt"]["cards_with_data"],
                             self.files(alt)["manifest.json"]["counts"]["cards_with_data"])

    def test_policy_strict_excludes_wigroup(self):
        strict = self._all(self.files("strict"))
        allow = self._all(self.files("allow_wigroup"))
        self.assertFalse([s for s, r in strict.items() if r["source_class"] == "wigroup"])
        self.assertTrue([s for s, r in allow.items() if r["source_class"] == "wigroup"])
        for sid, r in strict.items():
            if r["reason_code"] == "policy_excluded":     # ở allow: lớp wigroup, hoặc missing vì nguồn dưới 3 điểm
                self.assertIn((allow[sid]["source_class"], allow[sid]["reason_code"]),
                              (("wigroup", None), (None, "short")), sid)
        for sid, r in allow.items():
            if r["source_class"] not in (None, "wigroup"):
                self.assertNotEqual(strict[sid]["status"], "missing", sid)

    def test_sources_listed(self):
        f = self.files("allow_wigroup")
        src = f["manifest.json"]["sources"]
        for k, v in src.items():
            self.assertTrue(os.path.isfile(k), k)
            self.assertIn(v["class"], wd.CLASS_ORDER)
            self.assertEqual(len(v["sha256"]), 64)
        names = {os.path.basename(k) for k in src}
        for sid, r in self._all(f).items():
            if r["status"] != "missing" and "collected" in " ".join(r["meta"]["notes"]):
                self.assertTrue(any(n.endswith(".json") for n in names), sid)

    def test_no_forbidden_keys_or_hosts(self):
        acc = keys_in(load(DATA / "layout_const.json"), set()) | keys_in(load(DATA / "series_map.json"), set())
        for pol in ("allow_wigroup", "strict"):
            for name, doc in self.files(pol).items():
                acc |= keys_in(doc, set())
                text = json.dumps(doc, ensure_ascii=False)
                for s in BAD_STRINGS:
                    self.assertNotIn(s, text, "%s chứa %s" % (name, s))
                self.assertIsNone(API_HOST.search(text), "%s chứa tên miền API" % name)
        self.assertFalse(set(FORBIDDEN) & acc, set(FORBIDDEN) & acc)
        tep = [DATA / "series_map.json"] + sorted((DATA / "collected").glob("*.json"))
        tep += sorted((DATA / "collected" / "vn_raw").glob("*.json")) + sorted((DATA / "manual").rglob("*.json"))
        for p in tep:
            self.assertIsNone(API_HOST.search(p.read_text(encoding="utf-8")), "%s chứa tên miền API" % p)

    def test_dot4_choices(self):
        """Đợt 4: CPI YoY, CPI bình quân, GDP YoY lấy số NSO công bố (một nguồn, FACT-T1, đủ 3Y); chuỗi < 3 điểm
        là missing 'short'; YoY trong cùng gốc không phải partial; lãi suất điều hành không còn đoạn null 2020-2022."""
        allow = self._all(self.files("allow_wigroup"))
        for sid in ("vn|225|cpi_yoy|monthly-yoy", "vn|226|cpi_yoy_ave|monthly-yoyave",
                    "vn|244|gdp_so_sanh_2010_yoy|quarterly-yoy", "vn|244|gdp_so_sanh_2010_yoy|None"):
            r = allow[sid]
            self.assertEqual((r["status"], r["tier"], r["source_class"]), ("ok", "FACT-T1", "official"), sid)
            self.assertTrue(r["meta"]["source_name"].startswith("Cục Thống kê"), sid)
        g = dict(allow["vn|244|gdp_so_sanh_2010_yoy|quarterly-yoy"]["points"])
        self.assertEqual((g[ms(2026, 3, 31)], g[ms(2026, 6, 30)], g[ms(2026, 9, 30)]), (8.15, 8.81, 9.95))
        for sid in ("md|269|gia_vang_trong_nuoc_ban_ra|daily-value", "vn|251|sbv_bills_lstb|daily-value"):
            self.assertEqual((allow[sid]["status"], allow[sid]["reason_code"]), ("missing", "short"), sid)
        for sid, r in allow.items():
            if r["status"] != "missing":
                self.assertGreaterEqual(sum(1 for _, v in r["points"] if v is not None), wd.MIN_POINTS, sid)
        for sid in ("vn|244|dich_vu_yoy|quarterly-yoy", "vn|244|cong_nghiep_yoy|quarterly-yoy"):
            self.assertEqual((allow[sid]["status"], allow[sid]["tier"]), ("ok", "EST"), sid)
        tcv = allow["vn|250|lai_suat_dieu_hanh_tai_cap_von|None"]
        nam = [v for t, v in tcv["points"] if ms(2020, 3, 17) <= t <= ms(2022, 9, 22)]
        self.assertTrue(nam and all(v is not None for v in nam))
        self.assertEqual(tcv["tier_spans"][0]["tier"], "UNVERIFIED")

    def test_c17_choices_and_neutral_refs(self):
        allow = self._all(self.files("allow_wigroup"))
        host = re.compile(r"://|\b[a-z0-9-]+\.(?:vn|com|org|gov|net)\b", re.I)
        for sid, r in allow.items():
            self.assertIsNone(host.search(r["meta"]["source_ref"] or ""), (sid, r["meta"]["source_ref"]))
        for sid in ("md|409|usd_cny|daily-value", "md|217|wti_usd|daily-value",
                    "md|333|dau_brent_hoa_ky_investing_spot|daily-value"):
            self.assertTrue(allow[sid]["meta"]["source_ref"].startswith("FRED:"), sid)
        self.assertIn("Vietcombank", allow["vn|269|usd_nhtm_ban_ra|daily-value"]["meta"]["source_ref"])
        for sid in ("vn|250|lai_suat_dieu_hanh_tai_cap_von|None", "vn|224|cpi_max|yearly-value"):
            self.assertEqual((allow[sid]["tier"], allow[sid]["source_class"]), ("FACT-T1", "official"), sid)
            self.assertIn("Bảng tay", allow[sid]["meta"]["source_ref"], sid)
        lv = allow["vn|244|dich_vu|quarterly-value"]
        self.assertTrue(lv["status"] == "partial" and lv["breaks"], "GDP mức qua đổi gốc phải partial + breaks")
        for e in self.smap["series"].values():
            for c in e["candidates"]:
                self.assertNotEqual(c["src"]["src"], "union", "ghép hai nguồn trong một ứng viên")

    def test_idempotent(self):
        a = run_cli(["build", "--out", str(self.tmp / "idem")], {})
        b = run_cli(["build", "--out", str(self.tmp / "idem")], {})
        fa, fb = build_files(a["build"]), build_files(b["build"])
        self.assertEqual(set(fa), set(fb))

        def strip(o):
            if isinstance(o, dict):
                return {k: strip(v) for k, v in o.items() if k != "generated"}
            if isinstance(o, list):
                return [strip(v) for v in o]
            return o
        for k in fa:
            self.assertEqual(strip(fa[k]), strip(fb[k]), k)

    def test_status_command(self):
        res = run_cli(["status", "--out", str(self.tmp / "allow_wigroup")], {})
        self.assertTrue(res.get("ok"), res)
        self.assertEqual(res["source_policy"], "allow_wigroup")
        res = run_cli(["status", "--out", str(self.tmp / "khong_co")], {})
        self.assertEqual(res.get("error_code"), "no_build")


class NoSocket(unittest.TestCase):
    def test_sources_have_no_network_code(self):
        rx = re.compile(r"^\s*(?:import|from)\s+(urllib\.request|urllib|http\.client|http|socket|requests)\b", re.M)
        for name in SCRIPTS:
            src = (HERE / name).read_text(encoding="utf-8")
            self.assertIsNone(rx.search(src), "%s nhập mô-đun mạng" % name)
            for s in BAD_STRINGS:
                self.assertNotIn(s, src, "%s chứa %s" % (name, s))

    @unittest.skipUnless(HAVE_REAL, "thiếu đầu vào thật")
    def test_build_with_socket_blocked(self):
        def boom(*a, **k):
            raise AssertionError("builder mở socket")
        tmp = tempfile.mkdtemp(prefix="wdc_nosock_")
        old, old_cc = socket.socket, getattr(socket, "create_connection")
        socket.socket, socket.create_connection = boom, boom
        os.environ["WDC_TODAY"] = TODAY
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                wc.main(["build", "--out", tmp])
            res = json.loads(buf.getvalue().strip().splitlines()[-1])
            self.assertTrue(res.get("ok"), res)
        finally:
            socket.socket, socket.create_connection = old, old_cc
            shutil.rmtree(tmp, ignore_errors=True)


# ── (2) fixture tổng hợp ─────────────────────────────────────────────────────


def ms(y, m, d, h=0):
    return int(datetime(y, m, d, h, tzinfo=timezone.utc).timestamp() * 1000)


class Synthetic(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wdc_syn_"))
        (self.tmp / "col").mkdir()
        store = {"canvases": {
            "wc-x": {"source": "WiChart:x", "series": [{"t": ms(2022, m, d, 17), "v": 1.0}
                                                       for m, d in ((10, 31), (11, 30), (12, 31))]},
            "wc-m": {"source": "WiChart:m", "series": [{"t": ms(y, m, 1) - 7 * 3600000, "v": float(10 * y + m)}
                                                       for y in (2023, 2024, 2025, 2026) for m in range(1, 13)
                                                       if (y, m) <= (2026, 9)]},
            "wc-fq": {"source": "FRED:Q", "series": [{"t": ms(2026, 4, 1), "v": 2.5}, {"t": ms(2026, 1, 1), "v": 1.5},
                                                     {"t": ms(2025, 10, 1), "v": 1.0}]},
            "wc-empty": {"source": "FRED:E", "series": []},
            "vnm-a": {"source": "vnstock MSN:A", "series": [{"t": ms(2026, 9, d), "v": 5.0} for d in (24, 25, 28)]},
            "wc-2": {"source": "FRED:2", "series": [{"t": ms(2026, 8, 1), "v": 1.0}, {"t": ms(2026, 9, 1), "v": 2.0}]},
        }}
        (self.tmp / "store.json").write_text(json.dumps(store), encoding="utf-8")
        self.smap = {"sources": {"store": {"path": str(self.tmp / "store.json")},
                                 "collected": {"path": str(self.tmp / "col" / "*.json")}},
                     "store_class_by_source_prefix": wc.load_json(DATA / "series_map.json", "m")[
                         "store_class_by_source_prefix"] if HAVE_REAL else [["WiChart", "wigroup"],
                                                                            ["FRED", "official"]]}
        self.src = wd.Sources(self.smap, self.tmp, date.fromisoformat(TODAY), warn=lambda m: None)
        self.ev = wd.Evaluator(self.src)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def entry(self, freq, cands, **kw):
        e = {"freq": freq, "unit": "%", "name": "x", "candidates": cands, "reason_if_missing": "no_source",
             "planned_source": ""}
        e.update(kw)
        return e

    def cand(self, canvas, **kw):
        c = {"id": "c:" + canvas, "src": {"src": "store", "canvas": canvas}, "class": "official", "tier": "FACT-T1",
             "partial_reasons": [], "post": []}
        c.update(kw)
        return c

    def test_time_rules(self):
        self.assertEqual(wd.date_of_ms_ict(ms(2026, 8, 31, 17)), date(2026, 9, 1))
        self.assertEqual(wd.date_of_ms_ict(ms(2026, 9, 1)), date(2026, 9, 1))
        self.assertEqual(wd.period_end(date(2026, 4, 1), "Q"), date(2026, 6, 30))
        self.assertEqual(wd.period_end(date(2024, 2, 1), "M"), date(2024, 2, 29))
        self.assertEqual(wd.period_end(date(2025, 1, 1), "Y"), date(2025, 12, 31))
        r, _, _ = self.ev.evaluate("s", self.entry("Q", [self.cand("wc-fq")]), "allow_wigroup")
        self.assertEqual([t for t, _ in r["points"]], [ms(2025, 12, 31), ms(2026, 3, 31), ms(2026, 6, 30)])
        r, _, _ = self.ev.evaluate("s", self.entry("M", [self.cand("wc-m")]), "allow_wigroup")
        self.assertEqual(r["points"][-1], [ms(2026, 9, 30), 20269.0])
        sh = self.cand("vnm-a")
        sh["src"]["shift_days"] = 1
        r, _, _ = self.ev.evaluate("s", self.entry("D", [sh]), "allow_wigroup")
        self.assertEqual(r["points"], [[ms(2026, 9, d), 5.0] for d in (25, 26, 29)])

    def test_status_rules(self):
        r, _, _ = self.ev.evaluate("s", self.entry("M", [self.cand("wc-empty")]), "allow_wigroup")
        self.assertEqual((r["status"], r["reason_code"]), ("missing", "stale"))
        r, _, _ = self.ev.evaluate("s", self.entry("M", [self.cand("wc-nope")]), "allow_wigroup")
        self.assertEqual(r["status"], "missing")
        r, _, _ = self.ev.evaluate("s", self.entry("M", []), "allow_wigroup")
        self.assertEqual((r["status"], r["reason_code"]), ("missing", "no_source"))
        r, _, _ = self.ev.evaluate("s", self.entry("M", [self.cand("wc-m")]), "allow_wigroup")
        self.assertEqual((r["status"], r["as_of"]), ("ok", "2026-09-30"))
        r, _, _ = self.ev.evaluate("s", self.entry("M", [self.cand("wc-m", partial_reasons=["rounded"])]),
                                   "allow_wigroup")
        self.assertEqual((r["status"], r["partial_reasons"]), ("partial", ["rounded"]))
        r, _, _ = self.ev.evaluate("s", self.entry("Q", [self.cand("wc-fq")]), "allow_wigroup")
        self.assertIn("short_history", r["partial_reasons"])
        r, _, _ = self.ev.evaluate("s", self.entry("M", [self.cand("wc-x")]), "allow_wigroup")
        self.assertEqual(set(r["partial_reasons"]), {"short_history", "lagged"})

    def test_policy(self):
        e = self.entry("M", [self.cand("wc-m", **{"class": "wigroup"})])
        r, cls, _ = self.ev.evaluate("s", e, "allow_wigroup")
        self.assertEqual((r["status"], cls), ("ok", "wigroup"))
        self.assertIn(wd.WIGROUP_NOTE, r["meta"]["notes"])
        r, cls, _ = self.ev.evaluate("s", e, "strict")
        self.assertEqual((r["status"], r["reason_code"], cls), ("missing", "policy_excluded", None))
        # lớp lấy theo trường source của canvas, không theo khai báo trong map
        e = self.entry("M", [self.cand("wc-m", **{"class": "official"})])
        r, _, _ = self.ev.evaluate("s", e, "strict")
        self.assertEqual(r["reason_code"], "policy_excluded")

    def write_collected(self, name, series, **doc):
        d = {"schema": "wdc_collected/1", "producer": "test", "generated": "2026-10-04T00:00:00+07:00",
             "series": series}
        d.update(doc)
        (self.tmp / "col" / name).write_text(json.dumps(d), encoding="utf-8")

    def test_collected_priority_and_zero_point_sid(self):
        sid = "cn|3|clnon_fin_sector|monthly-value"
        self.write_collected("a.json", {sid: {"freq": "M", "unit": "%", "points": [[ms(2026, 6, 30), 1.0],
                                                                                  [ms(2026, 7, 31), 1.0],
                                                                                  [ms(2026, 8, 31), 1.0],
                                                                                  [ms(2026, 9, 30), None]],
                                              "source_name": "PBOC", "source_ref": "x", "tier": "FACT-T1",
                                              "notes": "một câu", "breaks": [{"t": ms(2026, 8, 31), "note": "b"}],
                                              "partial_reasons": ["proxy", "lagged"]}})
        r, cls, files = self.ev.evaluate(sid, self.entry("M", [], reason_if_missing="collector_pending"), "strict")
        self.assertEqual((r["status"], cls, r["as_of"]), ("partial", "official", "2026-08-31"))
        self.assertIn("một câu", r["meta"]["notes"])
        self.assertEqual(r["breaks"], [{"t": ms(2026, 8, 31), "note": "b"}])
        self.assertEqual(r["partial_reasons"], ["proxy", "short_history"])   # "lagged" của collector bị tính lại
        self.assertTrue(files[0].endswith("a.json"))
        # §16 C17 (4): cùng phủ 3Y, cùng tầng, cùng kỳ cuối thì collected thắng kho, kể cả collected lớp wigroup
        sid2 = "us|1|x|monthly-value"
        full = [[ms(y, m, 28), 7.0] for y in (2023, 2024, 2025, 2026) for m in range(1, 13) if (y, m) <= (2026, 9)]
        self.write_collected("b.json", {sid2: {"freq": "M", "unit": "%", "points": full, "tier": "FACT-T1"}},
                             **{"class": "official"})
        self.src._cache.pop("collected", None)
        store = json.loads((self.tmp / "store.json").read_text())
        store["canvases"]["wc-m"]["source"] = "FRED:M"
        (self.tmp / "store.json").write_text(json.dumps(store))
        self.src._cache.pop("store", None)
        r, _, _ = self.ev.evaluate(sid2, self.entry("M", [self.cand("wc-m")]), "allow_wigroup")
        self.assertEqual(r["points"][-1][1], 7.0)
        self.write_collected("b.json", {sid2: {"freq": "M", "unit": "%", "points": full, "tier": "FACT-T2",
                                               "class": "wigroup"}})
        self.src._cache.pop("collected", None)
        r, cls, _ = self.ev.evaluate(sid2, self.entry("M", [self.cand("wc-m", tier="FACT-T2")]), "allow_wigroup")
        self.assertEqual((cls, r["points"][-1][1]), ("wigroup", 7.0))

    def test_short_history_loses_at_equal_rank(self):
        sid = "vn|269|usd_nhtm_ban_ra|daily-value"
        self.write_collected("d.json", {sid: {"freq": "M", "unit": "%", "points": [[ms(2026, 9, 30), 1.0]],
                                              "tier": "FACT-T1", "class": "official"}})
        store = json.loads((self.tmp / "store.json").read_text())
        store["canvases"]["wc-m"]["source"] = "FRED:M"
        (self.tmp / "store.json").write_text(json.dumps(store))
        r, cls, _ = self.ev.evaluate(sid, self.entry("M", [self.cand("wc-m")]), "allow_wigroup")
        self.assertEqual((cls, r["points"][-1][1]), ("official", 20269.0))
        # cùng phủ đủ 3Y: tầng cao thắng dù trễ hơn (§16 C17 (2) trước (3))
        self.write_collected("d.json", {sid: {"freq": "M", "unit": "%", "tier": "FACT-T1", "class": "official",
                                              "points": [[ms(y, m, 28), 2.0] for y in (2023, 2024, 2025, 2026)
                                                         for m in range(1, 13) if (y, m) <= (2026, 5)]}})
        self.src._cache.pop("collected", None)
        r, _, _ = self.ev.evaluate(sid, self.entry("M", [self.cand("wc-m", tier="FACT-T2")]), "allow_wigroup")
        self.assertEqual((r["points"][-1][1], r["partial_reasons"]), (2.0, ["lagged"]))

    def test_c17_full_window_beats_tier_and_newer_wins(self):
        sid = "md|409|usd_cny|daily-value"
        # (1) ứng viên chưa phủ 3Y thua ứng viên phủ đủ, dù tầng cao hơn
        self.write_collected("e.json", {sid: {"freq": "M", "unit": "%", "points": [[ms(2026, m, 28), 1.0]
                                                                                  for m in (7, 8, 9)],
                                              "tier": "FACT-T1", "class": "official"}})
        r, cls, _ = self.ev.evaluate(sid, self.entry("M", [self.cand("wc-m", tier="FACT-T2")]), "allow_wigroup")
        self.assertEqual((cls, r["points"][-1][1]), ("wigroup", 20269.0))
        # cùng chưa đủ: phủ phần lớn hơn của cửa sổ thắng
        two_y = [[ms(y, m, 28), 3.0] for y in (2024, 2025, 2026) for m in range(1, 13) if (2024, 10) <= (y, m) <= (2026, 8)]
        self.write_collected("e.json", {sid: {"freq": "M", "unit": "%", "points": two_y, "tier": "FACT-T2",
                                              "class": "official"}})
        self.src._cache.pop("collected", None)
        r, _, _ = self.ev.evaluate(sid, self.entry("M", [self.cand("vnm-a", tier="FACT-T1")]), "allow_wigroup")
        self.assertEqual(r["points"][-1][1], 3.0)
        # (3) cùng phủ, cùng tầng: kỳ cuối mới hơn thắng, dù là kho
        old = [[ms(y, m, 28), 4.0] for y in (2023, 2024, 2025, 2026) for m in range(1, 13) if (y, m) <= (2026, 7)]
        self.write_collected("e.json", {sid: {"freq": "M", "unit": "%", "points": old, "tier": "FACT-T2",
                                              "class": "official"}})
        self.src._cache.pop("collected", None)
        r, _, _ = self.ev.evaluate(sid, self.entry("M", [self.cand("wc-m", tier="FACT-T2")]), "allow_wigroup")
        self.assertEqual(r["points"][-1][1], 20269.0)

    def test_manual_step_table(self):
        (self.tmp / "man").mkdir()
        self.smap["sources"]["manual"] = {"path": str(self.tmp / "man" / "*.json")}
        self.src = wd.Sources(self.smap, self.tmp, date.fromisoformat(TODAY), warn=lambda m: None)
        self.ev = wd.Evaluator(self.src)
        sid = "vn|250|lai_suat_dieu_hanh_tai_cap_von|None"
        rec = {"freq": "D", "unit": "%", "tier": "FACT-T1", "class": "official", "step": True,
               "kiem_lan_cuoi": "2026-10-01", "source_name": "NHNN", "source_ref": "Bảng tay",
               "points": [[ms(2019, 9, 16), 6.0], [ms(2020, 3, 17), None], [ms(2022, 9, 23), 5.0],
                          [ms(2023, 6, 19), 4.5]]}
        doc = {"schema": "wdc_collected/1", "producer": "t", "generated": "x", "series": {sid: rec}}
        (self.tmp / "man" / "p.json").write_text(json.dumps(doc), encoding="utf-8")
        r, cls, files = self.ev.evaluate(sid, self.entry("D", [self.cand("wc-m", tier="FACT-T2")]), "allow_wigroup")
        self.assertTrue(files[0].endswith("p.json"))
        pts = dict((t, v) for t, v in r["points"])
        self.assertIsNone(pts[ms(2020, 3, 17)])
        self.assertNotIn(ms(2020, 3, 18), pts)                       # đoạn chưa xác minh: chỉ một điểm null
        self.assertEqual(pts[ms(2020, 3, 16)], 6.0)                  # thứ Hai trước mốc null giữ mức cũ
        self.assertNotIn(ms(2023, 6, 17), pts)                       # thứ Bảy bỏ
        self.assertEqual(pts[ms(2023, 6, 16)], 5.0)
        self.assertEqual((r["as_of"], r["status"]), ("2026-10-02", "ok"))   # 04/10 là Chủ nhật
        rec["kiem_lan_cuoi"] = "2026-06-01"                          # lâu không kiểm: dừng ở +45 ngày, thành trễ
        (self.tmp / "man" / "p.json").write_text(json.dumps(doc), encoding="utf-8")
        self.src._cache.pop("collected", None)
        r, _, _ = self.ev.evaluate(sid, self.entry("D", []), "allow_wigroup")
        self.assertEqual((r["as_of"], r["partial_reasons"]), ("2026-07-16", ["lagged"]))

    def test_under_three_points_is_missing_short(self):
        """Đợt 4 (DATA2 việc 4, VERIFY_W3 V4): chuỗi dưới 3 điểm có số không lên trục; missing, reason 'short'."""
        sid = "md|269|gia_vang_trong_nuoc_ban_ra|daily-value"
        self.write_collected("g.json", {sid: {"freq": "D", "unit": "%", "points": [[ms(2026, 9, 30), 144.1]],
                                              "tier": "FACT-T2", "class": "secondary"}})
        r, cls, files = self.ev.evaluate(sid, self.entry("D", [self.cand("wc-2")], planned_source="P3"),
                                         "allow_wigroup")
        self.assertEqual((r["status"], r["reason_code"], cls, files, r["points"]), ("missing", "short", None, [], []))
        self.assertTrue(r["reason"].startswith("[CẦN DATA]") and "2 điểm" in r["reason"] and "P3" in r["reason"],
                        r["reason"])
        r, _, _ = self.ev.evaluate(sid, self.entry("D", [self.cand("wc-2"), self.cand("vnm-a")]), "allow_wigroup")
        self.assertEqual((r["status"], len(r["points"])), ("partial", 3))     # ứng viên đủ 3 điểm vẫn được chọn

    def test_scrub_old_builds(self):
        root = self.tmp / "state"
        b = root / "builds" / "20260101-000000"
        b.mkdir(parents=True)
        doc = {"series": {"s": {"meta": {"source_name": "VietnamBiz (WiGroup công khai, data." + "vietnambiz.vn)",
                                         "notes": ["https://api." + "wichart" + ".vn/vietnambiz/vi-mo?name=gdp"]},
                                "points": [[1, 2.5]]}}}
        (b / "dash_x.json").write_text(json.dumps(doc), encoding="utf-8")
        (root / "current.json").write_text(json.dumps({"build": str(b), "manifest": {"producer": "rates.py (data."
                                                                                                 "vietnambiz.vn)"}}))
        res = wc.cmd_scrub(["--out", str(root)])
        self.assertEqual(res["changed"], 2, res)
        for p in (b / "dash_x.json", root / "current.json"):
            self.assertIsNone(API_HOST.search(p.read_text(encoding="utf-8")), p)
        self.assertEqual(load(b / "dash_x.json")["series"]["s"]["points"], [[1, 2.5]])   # số liệu giữ nguyên
        self.assertEqual(wc.cmd_scrub(["--out", str(root)])["changed"], 0)               # chạy lại không đổi gì

    def test_collected_unit_conversion(self):
        sid = "us|99|walcl|weekly-value"
        self.write_collected("c.json", {sid: {"freq": "W", "unit": "Millions of Dollars",
                                              "points": [[ms(2026, 9, d), 6743031.0] for d in (16, 23, 30)],
                                              "tier": "FACT-T1"}})
        r, _, _ = self.ev.evaluate(sid, self.entry("W", [], unit="Tỷ USD"), "strict")
        self.assertAlmostEqual(r["points"][0][1], 6743.031)

    def test_transforms(self):
        pts = [[ms(y, m, 28), float(m + (y - 2025) * 100)] for y in (2025, 2026) for m in (1, 2, 3)]
        pts = wd.normalize([(wd.date_of_ms_utc(t), v) for t, v in pts], "M")
        yoy = wd.op_yoy(pts, "M")
        self.assertEqual(len(yoy), 3)
        self.assertAlmostEqual(yoy[0][1], (101 / 1 - 1) * 100)
        ytd = wd.op_ytd_yoy(pts, "M")
        self.assertAlmostEqual(ytd[1][1], ((101 + 102) / 3 - 1) * 100)
        self.assertEqual(wd.op_cumsum([[1, 1.0], [2, None], [3, 2.0]], "D"), [[1, 1.0], [2, 1.0], [3, 3.0]])
        self.assertEqual(wd.parse_vn_number("−11.101"), -11101.0)
        self.assertEqual(wd.parse_vn_number("26.917,8"), 26917.8)
        self.assertEqual(wd.parse_vn_date("Q2/26"), date(2026, 4, 1))
        self.assertEqual(wd.parse_vn_date("01/10/2026"), date(2026, 10, 1))

    def test_cpi_rebase_and_gdp_bases(self):
        b19 = {date(2024, m, 1): 100.0 + m for m in range(1, 13)}
        b19.update({date(2025, m, 1): 120.0 for m in range(1, 11)})
        b24 = {date(2025, 11, 1): 105.0, date(2025, 12, 1): 106.0}
        out, extra = wd.nso_op({"Dataset base 2019": b19, "Dataset base 2024": b24}, {"op": "cpi_rebase"})
        avg = sum(100.0 + m for m in range(1, 13)) / 12
        self.assertAlmostEqual(dict(out)[date(2025, 10, 1)], 120.0 / avg * 100)
        self.assertEqual(dict(out)[date(2025, 11, 1)], 105.0)
        self.assertEqual(extra["breaks"][0][0], date(2025, 11, 1))
        self.assertEqual(extra["spans"][0][2], "EST")
        q = {date(2024, 1, 1): 100.0, date(2025, 1, 1): 110.0}
        qi = {date(2025, 1, 1): 160.0, date(2026, 1, 1): 176.0}
        lv, ex = wd.nso_op({"Dataset_Q": q, "Dataset_QI.2026": qi}, {"op": "gdp_level"})
        self.assertEqual(dict(lv)[date(2026, 1, 1)], 176.0)
        self.assertEqual(dict(lv)[date(2025, 1, 1)], 110.0)
        self.assertEqual(ex["breaks"][0][0], date(2026, 1, 1))
        yo, _ = wd.nso_op({"Dataset_Q": q, "Dataset_QI.2026": qi}, {"op": "gdp_yoy"})
        self.assertAlmostEqual(dict(yo)[date(2026, 1, 1)], 10.0)
        self.assertAlmostEqual(dict(yo)[date(2025, 1, 1)], 10.0)

    def test_neutral_hostnames(self):
        s = wd.neutral("api." + "wichart" + ".vn/vietnambiz/vi-mo?name=gdp")
        self.assertFalse(any(b in s for b in BAD_STRINGS), s)
        self.assertIn("name=gdp", s)


if __name__ == "__main__":
    unittest.main(verbosity=2)
