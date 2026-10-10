#!/usr/bin/env python3
"""Unit tests for so_nguon_tab.py — a fixture bridge in a temp tree (no network, no real producer).

The fixture bridge holds copies of the REAL core (fincept_bridge/so_nguon.py + goi_chung.py, from
SO_NGUON_CORE_SRC or the default bridge; the suite is skipped when they are absent) next to a small
registry, a fake goi_nguon.py, a goi status file, a schedule file and a layer-A registry. Every refresh
run uses SO_NGUON_DRY=1: the detached runner only records what it WOULD run.

Run: python3 -m unittest scripts/test_so_nguon_tab.py -v
"""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import so_nguon_tab as T  # noqa: E402

SCRIPT = os.path.join(HERE, "so_nguon_tab.py")
CORE_SRC = os.environ.get("SO_NGUON_CORE_SRC") or T.BRIDGE_MAC_DINH
ENV_KEYS = ("SO_NGUON_BRIDGE", "SO_NGUON_SYS", "SO_NGUON_HOME", "SO_NGUON_REPO", "SO_NGUON_AGENTS",
            "SO_NGUON_PY", "SO_NGUON_DRY", "SO_NGUON_GOI_CHO", "SO_NGUON_PHAP_LY_TTL", "SO_NGUON_LOCK_FD")
BLOCK_KINDS = {"cong", "doan", "o_so", "bang", "the", "danh_sach", "trich", "bieu_do", "canh_bao", "chips"}
MAU = {"xanh", "vang", "do", "xam", "lam", "tim"}
SECTION_IDS = ["tom_tat", "van_de", "lam_moi", "tai_san", "lich", "goc_ck", "goc_beri", "phap_ly"]
ICT = timezone(timedelta(hours=7))

FAKE_GOI = '''
import pathlib
LICH = [
    ("job_a", "mod_a", 10, 60, 8, "localhost"),
]
if __name__ == "__main__":
    pathlib.Path(__file__).with_name("GOI_DA_CHAY").write_text("x")
    print("đến hạn: job_a")
'''
FAKE_SO = '''
import pathlib
pathlib.Path(__file__).with_name("SO_DA_CHAY").write_text("x")
'''


def iso(hours_ago):
    return (datetime.now(ICT) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")


def prod(kieu, lenh=None, **kw):
    p = {"kieu": kieu, "ten": "producer " + kieu, "lenh": lenh, "cwd": None, "timeout_giay": 30, "uoc_giay": 1,
         "lam_moi_khi_fetch": kieu in ("goi", "so"), "chay_nen": kieu == "so", "mang": None, "lich": None}
    p.update(kw)
    return p


def row(rid, nhom, duong_dan, do_tuoi, producer, sla=24, tieu_thu=("sgi_fa",), bac="EST", goc=(),
        phap_ly="ok", ghi=""):
    return {"id": rid, "ten": "Tên " + rid, "nhom": nhom, "loai": "tep", "duong_dan": duong_dan, "do_tuoi": do_tuoi,
            "sla_gio": sla, "nhip": "nhịp " + rid, "producer": producer, "tieu_thu": list(tieu_thu), "bac": bac,
            "nguon_goc": list(goc), "phap_ly": {"trang_thai": phap_ly, "ghi_chu": ghi}, "ghi_chu": ""}


REGISTRY = [
    row("a_goi", "vi_mo", "fincept_bridge/data/a.json", {"kieu": "goi_status", "khoa": "job_a"},
        prod("goi", ten="goi_nguon · job job_a", lich="job_a"), sla=8, tieu_thu=("dashboard",), goc=("goc-ck",)),
    row("b_json", "vi_mo", "fincept_bridge/data/b.json", {"kieu": "khoa_json", "khoa": "cap_nhat"},
        prod("so", ["{PY}", "-B", "{BRIDGE}/fake_so.py"], chu_ky_gio=12), bac="FACT-T2"),
    row("c_thieu", "vi_mo", "fincept_bridge/data/khong_co.json", {"kieu": "mtime"}, prod("thu_cong"),
        tieu_thu=("news",)),
    row("d_cam", "vi_mo", None, {"kieu": "khong_do"}, prod("upstream"), sla=None, bac=None, phap_ly="cam",
        ghi="robots.txt Disallow"),
    row("e_launchd", "beri", "fincept_bridge/data/e.json", {"kieu": "mtime"},
        prod("launchd", lich="com.test.agent"), tieu_thu=("beri",), bac="T4", goc=("goc-beri",)),
    row("f_cowork", "beri", "fincept_bridge/data/f.json", {"kieu": "mtime"}, prod("cowork", lich="cw-weekly"),
        tieu_thu=(), phap_ly="canh_bao", ghi="Crawl-delay: thử nghiệm"),
]
GOC = {"cap_nhat": "2026-09-17",
       "_ghi_chu": ["HAI THANG BẰNG CHỨNG KHÁC NHAU, KHÔNG TRỘN:",
                    "  he=beri → T1..T4, sell-side = T4, KG nội bộ = T2",
                    "  he=ck   → FACT-T1 > FACT-T2 > SS-T3 > EST > UNVERIFIED",
                    "LUẬT NỀN: kênh KHÔNG nâng bậc."],
       "nguon": [{"id": "goc-ck", "he": "ck", "ten": "Nguồn CK", "tier": "FACT-T1", "trang_thai": "song",
                  "nguon_goc": "HOSE", "kenh": "tệp", "tan_suat": "ngày", "do_tre": "T+0", "ghi_chu": "g1"},
                 {"id": "goc-ck2", "he": "ck", "ten": "CK chặn", "tier": "UNVERIFIED", "trang_thai": "chan"},
                 {"id": "goc-beri", "he": "beri", "ten": "Nguồn BERI", "tier": "T2", "trang_thai": "chua_co"}]}


def cell_text(c):
    return c["t"] if isinstance(c, dict) else c


def tables(section):
    return [b for b in section["khoi"] if b["kieu"] == "bang"]


@unittest.skipUnless(os.path.isfile(os.path.join(CORE_SRC, "so_nguon.py"))
                     and os.path.isfile(os.path.join(CORE_SRC, "goi_chung.py")),
                     "bridge core so_nguon.py / goi_chung.py not found")
class FixtureBridge(unittest.TestCase):
    """Temp _System/fincept_bridge with the real core, fixture data, DRY runs."""

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ENV_KEYS}
        self.tmp = tempfile.mkdtemp(prefix="so_nguon_tab_test_")
        self.sys_ = os.path.join(self.tmp, "_System")
        self.b = os.path.join(self.sys_, "fincept_bridge")
        for d in ("data", "state", "logs"):
            os.makedirs(os.path.join(self.b, d))
        for d in ("home", "repo/scripts", "agents"):
            os.makedirs(os.path.join(self.tmp, d))
        os.makedirs(os.path.join(self.sys_, "launchpad"))
        for f in ("so_nguon.py", "goi_chung.py"):
            shutil.copy(os.path.join(CORE_SRC, f), self.b)
        self.write("fincept_bridge/goi_nguon.py", FAKE_GOI)
        self.write("fincept_bridge/fake_so.py", FAKE_SO)
        self.write("fincept_bridge/so_nguon_dangky.py", "SO = " + repr(REGISTRY) + "\n")
        self.write("fincept_bridge/data/a.json", "{}")
        self.write("fincept_bridge/data/b.json", json.dumps({"cap_nhat": iso(100)}))
        self.write("fincept_bridge/data/e.json", "{}")
        self.write("fincept_bridge/data/f.json", "{}")
        self.write("fincept_bridge/data/goi_nguon_status.json", json.dumps(
            {"job_a": {"ok": True, "moi_nhat": iso(1), "chay_luc": iso(0.5), "nguong_gio": 8, "loi_lien_tiep": 0}}))
        self.write("fincept_bridge/data/lich_so.json", json.dumps({"viec": [
            {"ten": "com.test.agent", "nhip": "08:00", "trang_thai": "đã nạp", "moc_log": iso(2), "co": ""},
            {"ten": "cw-weekly", "nhip": "0 7 * * 6", "trang_thai": "TẮT", "moc_log": iso(900), "co": "⚠ đang TẮT"}]}))
        self.write("launchpad/songuon_registry.json", json.dumps(GOC, ensure_ascii=False))
        os.environ.update({"SO_NGUON_BRIDGE": self.b, "SO_NGUON_SYS": self.sys_,
                           "SO_NGUON_HOME": os.path.join(self.tmp, "home"),
                           "SO_NGUON_REPO": os.path.join(self.tmp, "repo"),
                           "SO_NGUON_AGENTS": os.path.join(self.tmp, "agents"), "SO_NGUON_PY": sys.executable,
                           "SO_NGUON_PHAP_LY_TTL": "0", "SO_NGUON_GOI_CHO": "1", "SO_NGUON_DRY": "1"})
        os.environ.pop("SO_NGUON_LOCK_FD", None)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── helpers ──

    def write(self, rel, text):
        p = os.path.join(self.sys_, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def cmd(self, lenh):
        return T.run(["so_nguon_tab.py", lenh])

    def section(self, payload, sid):
        return next(s for s in payload["trang"]["sections"] if s["id"] == sid)

    def check_section(self, s):
        self.assertTrue(s["id"] and s["tieu_de"])
        for b in s["khoi"]:
            self.assertIn(b["kieu"], BLOCK_KINDS)
            if b.get("mau"):
                self.assertIn(b["mau"], MAU)
            if b["kieu"] == "bang":
                for r in b["dong"]:
                    self.assertEqual(len(r), len(b["cot"]), b["cot"])
                    for c in r:
                        self.assertIsInstance(cell_text(c), str)
                        if isinstance(c, dict) and c.get("mau"):
                            self.assertIn(c["mau"], MAU)
            if b["kieu"] == "o_so":
                for o in b["o"]:
                    self.assertTrue(o["nhan"] and o["gia_tri"])
                    self.assertEqual(o["tier"], "")   # audit counts carry no evidence tier

    def check_page(self, p):
        self.assertEqual(p["trang"]["schema"], "vnblocks/1")
        for s in p["trang"]["sections"]:
            self.check_section(s)
        text = json.dumps(p["trang"], ensure_ascii=False)
        self.assertNotIn("{PY}", text)
        self.assertNotIn("{BRIDGE}", text)
        self.assertNotIn(self.tmp, text)       # absolute paths are shortened for display
        self.assertIn(p["run"]["dang_chay"], (True, False))

    def wait_run(self, timeout=30):
        t0 = time.time()
        while time.time() - t0 < timeout:
            p = self.cmd("trang_thai")
            if not p["run"]["dang_chay"]:
                return p
            time.sleep(0.2)
        self.fail("DRY runner did not finish in %d s" % timeout)

    # ── overview ──

    def test_overview_shape_and_order(self):
        t0 = time.time()
        p = self.cmd("overview")
        self.assertLess(time.time() - t0, 3.0)
        self.assertEqual([s["id"] for s in p["trang"]["sections"]], SECTION_IDS)
        self.assertEqual(set(p), {"meta", "trang", "csv", "run"})
        self.check_page(p)
        self.assertEqual(p["meta"]["n_tai_san"], len(REGISTRY))
        self.assertEqual(p["meta"]["lenh"], "overview")
        self.assertTrue(all(s["ok"] for s in p["meta"]["sources_live"][:4]))
        self.assertIsNone(p["run"]["run_id"])
        self.assertEqual(p["meta"]["warnings"], [])

    def test_summary_tiles_match_audit(self):
        p = self.cmd("overview")
        tiles = {o["nhan"]: o for o in self.section(p, "tom_tat")["khoi"][0]["o"]}
        self.assertEqual(tiles["Tài sản dữ liệu"]["gia_tri"], "6")
        self.assertEqual(tiles["Cũ"]["gia_tri"], "1")            # b_json 100 h > 24 h
        self.assertEqual(tiles["Cũ"]["mau"], "vang")
        self.assertEqual(tiles["Thiếu"]["gia_tri"], "1")         # c_thieu
        self.assertEqual(tiles["Thiếu"]["mau"], "do")
        self.assertEqual(tiles["Pháp lý cấm"]["gia_tri"], "1")   # d_cam
        self.assertEqual(tiles["Mã gọi đường cấm"]["gia_tri"], "0")

    def test_issues_sorted_with_pills_and_filled_hints(self):
        p = self.cmd("overview")
        s = self.section(p, "van_de")
        main = tables(s)[0]
        muc = [cell_text(r[0]) for r in main["dong"]]
        self.assertEqual(muc, sorted(muc, key=lambda m: {"ĐỎ": 0, "VÀNG": 1}[m]))
        self.assertTrue(all(r[0]["pill"] for r in main["dong"]))
        by_id = {cell_text(r[2]): r for r in main["dong"]}
        self.assertEqual(cell_text(by_id["c_thieu"][0]), "ĐỎ")        # a tab reads it → red
        self.assertEqual(cell_text(by_id["b_json"][1]), "cũ")
        self.assertIn("python3 -B fincept_bridge/fake_so.py", cell_text(by_id["b_json"][4]))
        grey = tables(s)[1]
        self.assertIn("f_cowork", [cell_text(r[2]) for r in grey["dong"]])   # mồ côi = grey

    def test_assets_grouped_by_nhom(self):
        p = self.cmd("overview")
        s = self.section(p, "tai_san")
        tb = tables(s)
        self.assertEqual(len(tb), 2)                     # vi_mo, beri — registry order
        heads = [b["text"] for b in s["khoi"] if b["kieu"] == "doan"]
        self.assertTrue(heads[0].startswith("Vĩ mô · 4 tài sản"))
        self.assertTrue(heads[1].startswith("BERI · 2 tài sản"))
        rows = {cell_text(r[0]): r for b in tb for r in b["dong"]}
        self.assertEqual(sorted(rows), sorted(r["id"] for r in REGISTRY))
        self.assertEqual(cell_text(rows["a_goi"][5]), "TƯƠI")
        self.assertEqual(rows["a_goi"][5]["mau"], "xanh")
        self.assertEqual(rows["b_json"][5]["mau"], "do")             # 100 h > 2 × SLA 24 h and a tab reads it
        self.assertIn("4,2 ngày", cell_text(rows["b_json"][4]))
        self.assertEqual(cell_text(rows["e_launchd"][7]), "T4 · BERI")  # BERI scale marked, never mixed
        self.assertEqual(cell_text(rows["d_cam"][8]), "CẤM")
        self.assertEqual(cell_text(rows["f_cowork"][6]), "không tab nào")
        self.assertTrue(cell_text(rows["a_goi"][2]).startswith("[bộ điều phối]"))

    def test_origin_tables_separate_scales(self):
        p = self.cmd("overview")
        ck, beri = self.section(p, "goc_ck"), self.section(p, "goc_beri")
        ck_rows, beri_rows = tables(ck)[0]["dong"], tables(beri)[0]["dong"]
        self.assertEqual([cell_text(r[0]) for r in ck_rows], ["Nguồn CK", "CK chặn"])
        self.assertEqual([cell_text(r[0]) for r in beri_rows], ["Nguồn BERI"])
        self.assertEqual({cell_text(r[2]) for r in ck_rows}, {"FACT-T1", "UNVERIFIED"})
        self.assertEqual({cell_text(r[2]) for r in beri_rows}, {"T2"})
        self.assertIn("FACT-T1 > FACT-T2", ck["lede"])
        self.assertNotIn("FACT-", beri["lede"])
        self.assertIn("T1..T4", beri["lede"])
        self.assertEqual(cell_text(ck_rows[0][6]), "a_goi")          # layer-B asset linked to its origin
        self.assertEqual(ck_rows[1][5]["mau"], "do")                 # chan

    def test_schedule_tables(self):
        p = self.cmd("overview")
        s = self.section(p, "lich")
        tb = tables(s)
        self.assertEqual(len(tb), 3)                                 # goi · launchd · cowork
        self.assertEqual(cell_text(tb[0]["dong"][0][0]), "job_a")
        self.assertEqual(cell_text(tb[2]["dong"][0][2]), "TẮT")
        self.assertEqual(tb[2]["dong"][0][2]["mau"], "vang")

    def test_forbidden_endpoint_hit_turns_red(self):
        url = "https://" + "dulieukinhte.com" + "/api/internal/data/x"
        with open(os.path.join(self.tmp, "repo", "scripts", "goi_cam.py"), "w", encoding="utf-8") as f:
            f.write("import urllib.request\nu = '%s'\n" % url)
        p = self.cmd("overview")
        tiles = {o["nhan"]: o for o in self.section(p, "tom_tat")["khoi"][0]["o"]}
        self.assertEqual(tiles["Mã gọi đường cấm"]["gia_tri"], "1")
        self.assertEqual(tiles["Mã gọi đường cấm"]["mau"], "do")
        hits = tables(self.section(p, "phap_ly"))[-1]
        self.assertEqual(cell_text(hits["dong"][0][0]), "fincept-qt/scripts/goi_cam.py")
        self.assertEqual(cell_text(hits["dong"][0][3]), "CÓ")

    def test_csv_one_row_per_asset(self):
        p = self.cmd("overview")
        cols, rows = p["csv"]["columns"], p["csv"]["rows"]
        self.assertEqual(len(cols), len(T.CSV_COLUMNS))
        self.assertEqual([r[0] for r in rows], [r["id"] for r in REGISTRY])
        self.assertTrue(all(len(r) == len(cols) for r in rows))
        b = rows[1]
        self.assertEqual(b[cols.index("Trạng thái")], "CŨ")
        self.assertGreater(b[cols.index("Tuổi (giờ)")], 99)

    def test_plan_shown_when_idle(self):
        p = self.cmd("overview")
        s = self.section(p, "lam_moi")
        heads = [b["text"] for b in s["khoi"] if b["kieu"] == "doan" and b.get("mau")]
        self.assertTrue(any(h.startswith("Nếu bấm FETCH") for h in heads))
        plan, skip = tables(s)
        self.assertEqual([cell_text(r[1]) for r in plan["dong"]],
                         ["goi_nguon — một lượt bộ điều phối", "b_json · fake_so.py"])
        skipped = " ".join(cell_text(r[2]) for r in skip["dong"])
        for rid in ("c_thieu", "d_cam", "e_launchd", "f_cowork"):
            self.assertIn(rid, skipped)

    # ── runs (DRY) ──

    def test_lam_moi_dry_run_end_to_end(self):
        p = self.cmd("lam_moi")
        core = sys.modules["so_nguon"]      # the module whose Popen started the runner (reaped below)
        self.check_page(p)
        self.assertEqual(p["meta"]["lenh"], "lam_moi")
        self.assertTrue(p["run"]["run_id"])
        self.assertEqual([b["id"] for b in p["run"]["buoc"]], ["goi_nguon", "b_json", "audit"])
        self.assertNotIn("ke_hoach", p["run"])
        self.assertEqual(p["run"]["ke_hoach_tom"]["n_chay"], 2)
        done = self.wait_run()
        for child in getattr(core, "_CON", []):
            child.wait(timeout=10)
        run = done["run"]
        self.assertEqual([b["trang_thai"] for b in run["buoc"]], ["xong", "xong", "xong"])
        self.assertIn("DRY", run["buoc"][0]["ghi_chu"])
        self.assertTrue(run["nhan"].startswith("làm mới xong"))
        self.assertEqual(run["n_xong"], 3)
        self.assertFalse(os.path.exists(os.path.join(self.b, "GOI_DA_CHAY")))   # DRY: nothing really ran
        self.assertFalse(os.path.exists(os.path.join(self.b, "SO_DA_CHAY")))
        self.assertTrue(os.path.exists(os.path.join(self.b, "data", "so_nguon_audit.json")))
        sec = done["section"]
        self.assertEqual(sec["id"], "lam_moi")
        self.check_section(sec)
        steps = tables(sec)[0]
        self.assertEqual(len(steps["dong"]), 3)
        self.assertEqual({cell_text(r[3]) for r in steps["dong"]}, {"XONG"})
        self.assertLess(len(json.dumps(done, ensure_ascii=False)), 20000)
        # After the run: overview shows the finished run and the next plan.
        p2 = self.cmd("overview")
        tiles = {o["nhan"]: o for o in self.section(p2, "lam_moi")["khoi"][0]["o"]}
        self.assertEqual(tiles["Trạng thái"]["gia_tri"], "XONG")

    def test_second_run_refused_while_locked(self):
        run_file = os.path.join(self.b, "state", "so_nguon_run.json")
        fd = os.open(os.path.join(self.b, "state", "so_nguon.lock"), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # lock held, no FETCH run on file → the holder is the goi_nguon background job
            p = self.cmd("lam_moi")
            self.assertTrue(any("job nền" in w for w in p["meta"]["warnings"]))
            self.assertFalse(p["run"]["dang_chay"])
            self.assertFalse(os.path.exists(run_file))
            # lock held by a FETCH run → refused, the running run stays the one on file
            with open(run_file, "w", encoding="utf-8") as f:
                json.dump({"run_id": "dang-chay", "dang_chay": True, "buoc": []}, f)
            p = self.cmd("lam_moi")
        finally:
            os.close(fd)
        self.assertTrue(any("không mở lượt thứ hai" in w for w in p["meta"]["warnings"]))
        with open(run_file, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["run_id"], "dang-chay")

    def progress(self, dang_chay, states):
        buoc = [{"id": i, "cach": c, "lenh": ["/usr/bin/python3", "-B", os.path.join(self.b, f)] if f else None,
                 "trang_thai": st, "bat_dau": iso(0.1) if st != "cho" else None,
                 "xong": iso(0.05) if st in ("xong", "loi") else None, "giay": 3.2 if st == "xong" else None,
                 "ma_thoat": 0 if st == "xong" else None, "ghi_chu": ""}
                for (i, c, f), st in zip((("goi_nguon", "goi", "goi_nguon.py"), ("b_json", "so", "fake_so.py"),
                                          ("audit", "so", None)), states)]
        kh = {"lap_luc": iso(0.2), "chay": [{"id": "goi_nguon", "cach": "goi", "tai_san": ["a_goi"]}],
              "bo_qua": [{"id": "c_thieu", "ly_do": "producer thủ công — không có lệnh chạy không người trông"},
                         {"id": "x1", "ly_do": "chưa đến hạn (tuổi 1,2 giờ)"},
                         {"id": "x2", "ly_do": "chưa đến hạn (tuổi 3 giờ)"}]}
        self.write("fincept_bridge/state/so_nguon_run.json", json.dumps(
            {"run_id": "r-test", "dang_chay": dang_chay, "dry": False, "pid": None, "bat_dau": iso(0.1),
             "xong_luc": None, "ke_hoach": kh, "buoc": buoc}, ensure_ascii=False))

    def test_poll_while_running(self):
        self.progress(True, ("xong", "dang_chay", "cho"))
        fd = os.open(os.path.join(self.b, "state", "so_nguon.lock"), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            t0 = time.time()
            p = self.cmd("trang_thai")
            self.assertLess(time.time() - t0, 1.0)
            ov = self.cmd("overview")
        finally:
            os.close(fd)
        run = p["run"]
        self.assertTrue(run["dang_chay"])
        self.assertEqual(run["nhan"], "đang làm mới 1/3 bước")
        self.assertEqual([b["ten"] for b in run["buoc"]],
                         ["goi_nguon — một lượt bộ điều phối", "b_json · fake_so.py", "Kiểm lại Sổ nguồn"])
        self.assertEqual(set(p), {"meta", "run", "section"})
        sec = p["section"]
        self.check_section(sec)
        tiles = {o["nhan"]: o for o in sec["khoi"][0]["o"]}
        self.assertEqual(tiles["Trạng thái"]["gia_tri"], "ĐANG CHẠY")
        self.assertEqual(tiles["Tiến độ"]["gia_tri"], "1/3 bước")
        steps, skip = tables(sec)
        self.assertEqual([cell_text(r[3]) for r in steps["dong"]], ["XONG", "ĐANG CHẠY", "CHỜ"])
        self.assertIn("đang chạy", cell_text(steps["dong"][1][5]))
        grouped = {cell_text(r[0]): r for r in skip["dong"]}
        self.assertEqual(cell_text(grouped["chưa đến hạn"][1]), "2")      # ages folded into the asset list
        self.assertIn("x1 (tuổi 1,2 giờ)", cell_text(grouped["chưa đến hạn"][2]))
        self.assertNotIn(self.tmp, json.dumps(p["section"], ensure_ascii=False))
        # overview during a run: no "if you press FETCH now" plan
        heads = [b["text"] for b in self.section(ov, "lam_moi")["khoi"] if b["kieu"] == "doan"]
        self.assertFalse(any(h.startswith("Nếu bấm FETCH") for h in heads))

    def test_dead_runner_reported(self):
        self.progress(True, ("dang_chay", "cho", "cho"))   # file says running, nobody holds the lock
        p = self.cmd("trang_thai")
        self.assertFalse(p["run"]["dang_chay"])
        self.assertEqual(p["run"]["buoc"][0]["trang_thai"], "loi")
        self.assertEqual(p["run"]["nhan"], "lượt làm mới dừng giữa chừng")
        ov = self.cmd("overview")
        self.assertTrue(any("dừng giữa chừng" in w for w in ov["meta"]["warnings"]))
        tiles = {o["nhan"]: o for o in self.section(ov, "lam_moi")["khoi"][0]["o"]}
        self.assertEqual(tiles["Trạng thái"]["gia_tri"], "DỪNG GIỮA CHỪNG")

    def test_cli_envelope_single_json_line(self):
        env = dict(os.environ)
        for lenh in ("overview", "trang_thai"):
            out = subprocess.run([sys.executable, SCRIPT, lenh], capture_output=True, env=env, timeout=30)
            self.assertEqual(out.returncode, 0)
            lines = out.stdout.decode("utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertNotIn("error", json.loads(lines[0]))


class Errors(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("SO_NGUON_BRIDGE")
        self.tmp = tempfile.mkdtemp(prefix="so_nguon_tab_err_")
        os.environ["SO_NGUON_BRIDGE"] = self.tmp

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SO_NGUON_BRIDGE", None)
        else:
            os.environ["SO_NGUON_BRIDGE"] = self._old
        shutil.rmtree(self.tmp, ignore_errors=True)
        sys.modules.pop("so_nguon", None)

    def cli(self, *args):
        out = subprocess.run([sys.executable, SCRIPT] + list(args), capture_output=True, timeout=30,
                             env=dict(os.environ))
        self.assertEqual(out.returncode, 0)
        lines = out.stdout.decode("utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        return json.loads(lines[0])

    def core(self, text):
        with open(os.path.join(self.tmp, "so_nguon.py"), "w", encoding="utf-8") as f:
            f.write(text)

    def test_no_bridge(self):
        p = self.cli("overview")
        self.assertEqual(p["error_code"], "NO_BRIDGE")
        self.assertIn("SO_NGUON_BRIDGE", p["error"])

    def test_broken_core(self):
        self.core("def audit(:\n")
        p = self.cli("trang_thai")
        self.assertEqual(p["error_code"], "NO_BRIDGE")
        self.assertIn("SyntaxError", p["error"])

    def test_core_missing_api(self):
        self.core("def audit():\n    return {}\n")
        p = self.cli("overview")
        self.assertEqual(p["error_code"], "NO_BRIDGE")
        self.assertIn("trang_thai_lam_moi", p["error"])

    def test_bad_args(self):
        for args in ((), ("xoa",), ("overview", "thua")):
            p = self.cli(*args)
            self.assertEqual(p["error_code"], "BAD_ARGS")
            self.assertIn("overview | lam_moi | trang_thai", p["error"])

    def test_runner_start_failure(self):
        self.core("\n".join(["def duong():",
                             "    import pathlib; b = pathlib.Path(%r)" % self.tmp,
                             "    return {k: b for k in ('bridge', 'sys', 'repo', 'home', 'data', 'state')}",
                             "def audit(): return {}",
                             "def ke_hoach_lam_moi(**k): return {}",
                             "def trang_thai_lam_moi(): return {}",
                             "def load_registry(): return []",
                             "def bat_dau_lam_moi(): raise OSError('đĩa đầy')", ""]))
        p = self.cli("lam_moi")
        self.assertEqual(p["error_code"], "RUN_FAILED")
        self.assertIn("đĩa đầy", p["error"])


class Formatting(unittest.TestCase):
    def test_fmt_vn(self):
        self.assertEqual(T.fmt_vn(91.64, 1), "91,6")
        self.assertEqual(T.fmt_vn(1440, 0), "1.440")
        self.assertEqual(T.fmt_vn(-1.5, 1), "−1,5")
        self.assertEqual(T.fmt_vn(None), T.CAN)
        self.assertEqual(T.fmt_vn(float("nan")), T.CAN)

    def test_tuoi_txt(self):
        self.assertEqual(T.tuoi_txt(0.3), "18 phút")
        self.assertEqual(T.tuoi_txt(7.44), "7,4 giờ")
        self.assertEqual(T.tuoi_txt(91.6), "3,8 ngày")
        self.assertIsNone(T.tuoi_txt(None))

    def test_luc_txt(self):
        now = datetime(2026, 9, 24, 20, 0, tzinfo=ICT)
        self.assertEqual(T.luc_txt("2026-09-24T18:40:12+07:00", now), "24/09 18:40")
        self.assertEqual(T.luc_txt("2026-09-24T11:40:12+00:00", now), "24/09 18:40")
        self.assertEqual(T.luc_txt("2025-08-08T00:02:33+00:00", now), "08/08/2025 07:02")
        self.assertEqual(T.luc_txt(None, now), "—")
        self.assertEqual(T.luc_txt("không phải ngày", now), "—")


if __name__ == "__main__":
    unittest.main()
