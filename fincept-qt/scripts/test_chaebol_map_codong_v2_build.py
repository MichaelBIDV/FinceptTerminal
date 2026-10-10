#!/usr/bin/env python3
"""Test tích hợp tab codong v2 (P5, codong_v2_spec §8.5): golden v21 trong bộ nhớ, coverage live, khoá inc, ngân sách
§3.3, liên kết tab (nhóm, vciq, screener), harness offscreen.

Chạy (cả hai trình thông dịch):
    python3.14 -m pytest -q scripts/test_chaebol_map_codong_v2_build.py
    ~/Library/Application\\ Support/com.fincept.terminal/venv-numpy2/bin/python -m pytest -q \\
        scripts/test_chaebol_map_codong_v2_build.py

Lớp Pure không cần kho. GoldenV21 cần v21_const.json. LiveBuild dựng MỘT lần (assemble live, 8 tab: codong, 5 tab
nhóm, screener, vciq; ngày 05/10/2026; chỉ đọc kho). Harness gọi chb_harness offscreen nếu đã build; ảnh lưu ở
CHB_SHOT_DIR (mặc định thư mục tạm của test). Mạng bị chặn trong tệp (harness là tiến trình con, không dùng mạng).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("CHB_TODAY", "2026-10-05")

import chaebol_map as M  # noqa: E402
import chaebol_map_dom as D  # noqa: E402

TODAY = date(2026, 10, 5)
V21_FILE = M.bridge_dir() / "data" / "chaebol_map" / "v21_const.json"
VC_DIR = M.bridge_dir() / "state" / "vc_lk"
LIVE_OK = (VC_DIR / "VIC" / "price-history.json").is_file() and V21_FILE.is_file()
HARNESS = M.bridge_dir() / "harness" / "chaebol_map" / "qt" / "build" / "chb_harness"
GROUP_TABS = ("tuanmuot", "sovico", "phuong", "bauthuy", "eliminated")
LIVE_TABS = {"codong", "screener", "vciq", *GROUP_TABS}
SUB_IDS = ("phase_info", "chart", "phase", "cluster", "shareholder", "capitaliq", "flow", "strategic", "events",
           "patterns", "action")
# codong_v2_spec §3.3 (byte, nút); đo trên tệp đã finalize + dumps, đúng như builder ghi
SUB_BUDGET = {**{s: (25000, 600) for s in ("phase_info", "chart", "phase", "patterns", "action")},
              **{s: (40000, 900) for s in ("cluster", "shareholder", "strategic")},
              "flow": (50000, 1100), "events": (60000, 1400), "capitaliq": (120000, 2600)}
CHART_BUDGET = {"MAX": (135000, 450), "5Y": (95000, 450), "2Y": (75000, 450)}
TK_BUDGET = {True: (60000, 1300), False: (25000, 600)}          # 48 mã V21 cũ / 61 mã mới
ROOT_BUDGET, TONG_BUDGET, OPEN_BUDGET = (40000, 800), (70000, 1600), (190000, 4000)
TAB_MAX_BYTES, TAB_MAX_S = 30_000_000, 30.0
GOLDEN_V21 = """
4dc30f498de9dff1c8dc51576f106ec404d34c00a03b644d01adf200f758e788  ./export.csv
eedcc06a9fced7e4c733f91f1f73878cb67b247732c0310cfd89acb0c2db155a  ./inc/codong_ACB.json
c80c1c659deb4e9b0cc04138d62115082f6b718d0b4efeb7cc9d229f0ca63032  ./inc/codong_BCM.json
780e1ca2d01ff4c40f50848f7352b55d1c4f5a5d905aa02a13a61bbb3ef6d46b  ./inc/codong_BID.json
3e27fe7069f64365c5fd8b7382429dddc8048083f0a8fe185e21680887e6660a  ./inc/codong_BSR.json
72b1fe93498417814a41efd69ff20f0fd02b609b6e4df1fb12f98643bd516f00  ./inc/codong_BVH.json
69d015e4c5ee082cf61e57fda1f5a14547ddebadd65fcf59638cbeb570b24f06  ./inc/codong_CTD.json
6abc4ad9d3c3b67f82c1b1db36e96542457ddcc46de7164ccf3b65f7349e57e1  ./inc/codong_CTG.json
4b39351428e915ccc21bcd5ae8463137c9b719f57d7931965661b1c38a195e78  ./inc/codong_DGC.json
67ea46c399a6d3fa6d61913b138e03dd40097c0eb5fc9ff1a4d2e0ec8d42e67c  ./inc/codong_FPT.json
4f1a3fb79cba78390188f3671c2bcfa0583d040499a6c9be1a4ab6d1773e51aa  ./inc/codong_GAS.json
b8693b319c9744d0277ef01ebbcd225550e4b720cf201aaac073ab257ffd40fd  ./inc/codong_GEE.json
69a2d0113e15fa913f02324defcf3ab78b3c46923d0f1ed33561b13cd76a1436  ./inc/codong_GEL.json
bc5f9b9d64d1ccce61016ea439ccae0252c7c2ce25164c9848bb4ffb590ccbc8  ./inc/codong_GEX.json
85ea740c217ffdfd7f31522aa9322912e3a3151a3f1a6d56e7f844608c7cbd46  ./inc/codong_GMD.json
74e02a6393849a2c30bd8070afe81e5babfd9954d5b6f17030d712e2a808ea4f  ./inc/codong_GVR.json
cecd1dbd3b11697f17208bb6193e1800e55ea66d02fd5ed4a9c7aa48bd3cbad9  ./inc/codong_HAH.json
b22b63d10a48c876dc3f1451d91999f6e28eb146ea71f84d33b1d064548f21e3  ./inc/codong_HCM.json
dd7904238e9b58d131cbda3151d88eeb5723d8aaa9e85a2dde8a77e9120aeb75  ./inc/codong_HDB.json
6b70c46573e960263070c987f1714c2473e86aa0ed4aa858b40956fb9a1e2bf2  ./inc/codong_HPG.json
6d272098acc674676dd13b43caaf76880c5e7bc98fb034d1b469ef81844b59c7  ./inc/codong_LPB.json
6a99ec7b5c0d6eaa6bae1f46fbc7125d0a43eacce8efa6e3c1c762d05e28bcd7  ./inc/codong_MBB.json
d5306c9c2dc14db5e4846e4c4b3d1ad5ee01c210f955ab71ab9feb6fb04c7449  ./inc/codong_MSN.json
dd7efe57e857501a4a7c6557b6a6c6ac6ad0131b2d3aea0d6666d618b8660e6a  ./inc/codong_MSR.json
5737138dfb08184258c6e538a1753ddf52425afb4a1a69883a0c1a4e6cdc0615  ./inc/codong_MWG.json
0aaf2c60540ba9067eb5c34b8e02ac93e89975d817fba422e88b0c570f03d438  ./inc/codong_NVL.json
f154cb9dfa79c6749375f452ce5f1bf5fa57b1ee22e721bf055a2a54f87d4f63  ./inc/codong_PC1.json
d705e037811596b598dea47922514aae0488168d0c54557305bd3d6041f2e822  ./inc/codong_PLX.json
06f71538d0daa2da2e69f75873c59f24d3c37a92d24d75b065e1c1e01a817347  ./inc/codong_SAB.json
3898aba4579d599fed6f68cbe591682e2f851ae654edf01277e8ad49c02decfc  ./inc/codong_SHB.json
5ce66901cac1bd1ed8d851ee9831d18a47381d41c176a8bf5b0c678d8344e974  ./inc/codong_SSB.json
44efd6a013d5824267e6119376316324fb90446643ae44991ca2796dbe04e3a1  ./inc/codong_SSI.json
d39c3aa6b384bc04d329fa7c910ca461280ba8e5bf40481fcb65579f0e4e0b40  ./inc/codong_STB.json
7783f29c22e14ebb8fb655071a926cdca564fa715a3cf43d5179aad91e5bdc80  ./inc/codong_TCB.json
d9c1fb27dd001052397bd4bbc0e7e3cd2f3cf2144a2c3ac0faf4d68570edaa74  ./inc/codong_TPB.json
071a201a38234b3a428114086b6a1bf12a49b1a9b5226a8ae8279ce79ecfbb45  ./inc/codong_VCB.json
a3150fec4a2a78fcd74fff8fdd07b7bb9f6346b9b8da86ffece4a54f5a8df854  ./inc/codong_VCI.json
b4caf7ab05896fc0439830c74ccedb29f0bf6848b8193d80b734b3c597a0fdd0  ./inc/codong_VGI.json
a65c4b15a2c587861f2b4b79033b5e339571e39dd1d88e171cbad4536c583303  ./inc/codong_VHM.json
82b437bb1b7ef5e2bc1e127de236fe4f6207e1bd5b912546452710dc3c8c4315  ./inc/codong_VIB.json
e7c5b169a8893461c69b842fb0ccdd417f1fb2f0ed425390e71c727d57cc35a1  ./inc/codong_VIC.json
5d58bf98939c1eddb1c1c467869b63b3f2885f70771fb928b662d53c418fe336  ./inc/codong_VIX.json
aa0b2db5c387fdd7e56e807e21a9507cc00ac4e0e59bec3ae45334cab636ba6b  ./inc/codong_VJC.json
1e99f797831f23e9db58275e59cc2b373e9ddfcc42523b88ed3edf2f376f1691  ./inc/codong_VNM.json
d45016282d34824adf19499c6b16de8bd0f585a9a7a670bb66a7efdcefa4a44f  ./inc/codong_VPB.json
d57316ddb109ca68a25e36936cc59191223a66b3d6f7d6e4a6dfd4a2039a5ba9  ./inc/codong_VPI.json
2c8062d5868fcc844298dbe3ecc5fcf7e4fc2454c83d3ffe93cad687b55d313b  ./inc/codong_VPL.json
f8b5236e92bae89897de11580e70ae0c1f807a896948357d639df383b51cd334  ./inc/codong_VRE.json
5296a7e6829310b7dd27dcb2f9c274696649ddc90522fdef679bb5ae832e6c20  ./inc/codong_VTP.json
ce3b463669233719b2d038e5e6998cfa3ad10608194feeb23b172ce9d8f2af6a  ./shell.json
ecb7840d3baa80a27cff943ef4e9eaf0b5bfdf9bba8d28e64a6497db2f70a60f  ./tab_audit.json
e020f2a702d12c1491003910444548dc543a898444f0887ba731820c4b5d26ea  ./tab_bauthuy.json
4d05cbd799f814e9ebaf041d6c2d90b3209d8130fc73e9cc739c8263d12646c9  ./tab_catalyst.json
5c9dfe0d043ff49c724901e6224fe05fcc7670a1612a5f79617fe8bfa3bed118  ./tab_chaebol.json
425a76b7b6a8da3442b11cdf711b5dac48bcb9f15fe2fd919c5fa61bbd84f7bc  ./tab_changelog.json
d79a8952d0f91fccf7cb16120505675ab564183342da36ff770a533d5416c7b6  ./tab_claims54.json
6b0535a9b1f3414dec59cac1d5c66b240b2cc6d766d5dcc3e65e3ff6c86d8e73  ./tab_codong.json
65996dbfa168603480fd5e644c710a44fa68ffc2f4c6fbcbd3417a1080edf683  ./tab_deep6.json
1bec8667dcc0f6945a55c82663a7185471a8fd0ece89f97a9fe431a11196bf90  ./tab_eliminated.json
10910a43d25bd0e6571bc3c38a4dc22ad763eb0aa13ff7b942ba2b61447d902d  ./tab_overview.json
f845bda37a94438f9294d2b22c1bfae77b668fd9eb78549c5eafdf6ce72498dd  ./tab_phuong.json
078250788480697b9a5fcfcb4a275af30527cc8afc058975f0ad5b7d37546b3b  ./tab_portfolio.json
b1b7e0d9a1f106f9aaeaccbbbb4046e87c127cce248778841a4030aa70e80041  ./tab_portfolio25.json
51d4919078dd7d209b215c4b5fd903f8b9530f77bbeb9a27b82ffe93b415a911  ./tab_screener.json
d0a0a092f0fdffae15543745f494d432dcd27da4e8e6c291a3a76c359794efd7  ./tab_sovico.json
c6c08c47832362ae6362896ead3260d16a8443eb6b5e198d155ab8dffa9909d5  ./tab_tuanmuot.json
4549e3e4e106d4b79772eceabe186b927a50a55ab4b19c18381a7a8a6909e149  ./tab_vn30.json
95d954230695b0f4b5f7a9229a18fd8a7adc9f0ce59220217f1562af1de75939  ./tab_vnindex.json
"""
_REAL, _CACHE = {}, {}


def setUpModule():
    def blocked(*a, **k):
        raise RuntimeError("mạng bị chặn trong test chaebol_map_codong_v2_build")
    for name in ("socket", "create_connection", "getaddrinfo"):
        _REAL[name] = getattr(socket, name)
        setattr(socket, name, blocked)


def tearDownModule():
    for name, fn in _REAL.items():
        setattr(socket, name, fn)
    tmp = _CACHE.pop("tmp", None)
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)


# ── duyệt cây ───────────────────────────────────────────────────────────────


def walk(node):
    yield node
    if isinstance(node, dict):
        for ch in node.get("k", ()):
            yield from walk(ch)


def text_of(node):
    return node if isinstance(node, str) else "".join(text_of(c) for c in node.get("k", ()))


def by_key(node, pred):
    return [n for n in walk(node) if isinstance(n, dict) and pred(str(n.get("key", "")))]


def golden():
    out = {}
    for ln in GOLDEN_V21.strip().splitlines():
        digest, name = ln.split(None, 1)
        out[name[2:] if name.startswith("./") else name] = digest
    return out


def sha(text, enc="utf-8"):
    return hashlib.sha256(text.encode(enc)).hexdigest()


# ── dựng (một lần) ──────────────────────────────────────────────────────────


def live_build():
    """assemble live 8 tab (một lần cho cả tệp) → (files, manifest, csv_text, {tab: giây})."""
    if "live" not in _CACHE:
        times, orig = {}, M.run_tab

        def timed(tab_id, label, ctx):
            t0 = time.monotonic()
            try:
                return orig(tab_id, label, ctx)
            finally:
                times[tab_id] = time.monotonic() - t0
        with mock.patch.object(M, "run_tab", timed):
            files, man, csv_text = M.assemble("live", TODAY, only=LIVE_TABS)
        _CACHE["live"] = (files, man, csv_text, times)
    return _CACHE["live"]


def tree(files, man, key):
    """Gốc cây của inc `key` (hoặc 'tab_<id>.json') từ tệp đã finalize."""
    name = key if key.endswith(".json") else man["inc"][key]
    return json.loads(files[name])["root"]


def size(files, man, key):
    name = man["inc"][key]
    return len(files[name].encode("utf-8")), D.count_nodes(json.loads(files[name])["root"])


def build_dir():
    """Bản dựng live ghi ra thư mục tạm (cho chb_harness --build)."""
    if "dir" not in _CACHE:
        files, man, csv_text, _ = live_build()
        _CACHE["tmp"] = tempfile.mkdtemp(prefix="chb_cd2_")
        _CACHE["dir"] = M.write_build(Path(_CACHE["tmp"]), files, man, csv_text)
    return _CACHE["dir"]


# ── không cần kho ───────────────────────────────────────────────────────────


class CoverageLive(unittest.TestCase):
    """§8.2: live_opts thay v21_const cho codong.tk / codong.win; mode v21 gọi như cũ."""
    SUBS = [{"key": "codong.sub", "default": "phase_info", "options": list(SUB_IDS)}]
    LIVE = {"codong.tk": ["VIC", "ACB", "FOX"], "codong.win": ["MAX", "5Y", "2Y"]}

    def st(self, tks=("VIC", "ACB", "FOX"), win=True):
        out = [{"key": "codong.tk", "default": "VIC", "options": list(tks)}] + self.SUBS
        return out + ([{"key": "codong.win", "default": "MAX", "options": ["MAX", "5Y", "2Y"]}] if win else [])

    def test_live_ok_missing_and_mismatch(self):
        self.assertEqual(M._coverage(self.st(), {"codong"}, None, self.LIVE), {"missing": [], "mismatch": []})
        self.assertEqual(M._coverage(self.st(win=False), {"codong"}, None, self.LIVE)["missing"], ["codong.win"])
        mis = M._coverage(self.st(("VIC", "ACB")), {"codong"}, None, self.LIVE)["mismatch"]
        self.assertIn("codong.tk: 2 lựa chọn ≠ 3", mis)
        self.assertTrue(any("options lệch vũ trụ live:" in x and "FOX" in x for x in mis), mis)

    def test_v21_path_unchanged(self):
        cov = M._coverage(self.st(win=False), {"codong"}, None)
        self.assertEqual(cov["missing"], [])
        self.assertEqual(cov["mismatch"], ["codong.tk: 3 lựa chọn ≠ 48"])
        self.assertEqual(M.EXPECTED_STATES["codong.tk"], ("codong", "VIC", 48))
        ctx = M.Ctx("v21", TODAY, [])
        self.assertIsNone(M._live_opts(ctx, {"codong"}))
        self.assertIsNone(M._live_opts(M.Ctx("live", TODAY, []), {"screener"}))


class TopTenGuard(unittest.TestCase):
    """§8.1: LiveTk.top10_stat không vỡ với mã ngoài V21 có dòng sổ vendor thiếu SL/ngày (DPM, PVT 05/10)."""

    def test_rows_without_qty_give_can_data(self):
        import chaebol_map_tab_codong_live as LV
        L = LV.LiveTk.__new__(LV.LiveTk)
        row = lambda adj: {"public_date": "2026-06-30", "_adj": {"adj": adj, "rights": [], "lech": None, "f": 1.0}}  # noqa
        L.__dict__["rows_h"] = [row(5e6), row(None)]
        with D.use_mode("live", "2026-10-05"):
            t = text_of(L.top10_stat())
        self.assertIn("TOP 10 HOLDERS", t)
        self.assertIn("[CẦN DATA", t)
        self.assertIn("thiếu SL hoặc ngày công bố", t)


# ── golden v21 ─────────────────────────────────────────────────────────────


@unittest.skipUnless(V21_FILE.is_file(), "chưa có v21_const.json")
class GoldenV21(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files, cls.man, cls.csv = M.assemble("v21", TODAY)

    def test_byte_identical(self):
        gold = golden()
        self.assertEqual(len(gold), 68)
        tree_files = {k: v for k, v in gold.items() if k != "export.csv"}
        self.assertEqual(sorted(self.files), sorted(tree_files))
        bad = [n for n, h in tree_files.items() if sha(self.files[n]) != h]
        self.assertEqual(bad, [])
        self.assertEqual(sha(self.csv, "utf-8-sig"), gold["export.csv"])

    def test_no_live_links_or_states(self):
        keys = {s["key"]: s for s in self.man["inventory"]["states"]}
        self.assertEqual(len(keys["codong.tk"]["options"]), 48)
        self.assertNotIn("codong.win", keys)
        self.assertEqual(self.man["inventory"]["coverage"], {"missing": [], "mismatch": []})
        for name, text in self.files.items():
            if name == "shell.json":
                continue                              # thanh tab: on.set {tab} là của trang gốc
            for n in walk(json.loads(text)["root"]):
                if isinstance(n, dict):
                    self.assertFalse(str(n.get("key", "")).startswith(("cd2.", "vciq.cd2.")), (name, n.get("key")))
                    self.assertNotIn("tab", ((n.get("on") or {}).get("set") or {}), (name, n.get("key")))


# ── live ────────────────────────────────────────────────────────────────────


@unittest.skipUnless(LIVE_OK, "kho vc_lk/v21_const vắng: bỏ test live")
class LiveBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files, cls.man, cls.csv, cls.times = live_build()
        import chaebol_map_data_codong2 as O
        cls.v21 = json.loads(V21_FILE.read_text("utf-8"))
        cls.order = O.universe_groups(cls.v21)["order"]
        cls.old48 = set(cls.v21.get("CauTrucCoDongTab.allTickers") or [])
        cls.warn = [w for w in cls.man["warnings"] if w.startswith("[codong]")]

    def test_states_and_coverage(self):
        st = {s["key"]: s for s in self.man["inventory"]["states"]}
        self.assertEqual(len(self.order), 109)
        self.assertEqual((st["codong.tk"]["default"], st["codong.tk"]["options"]), ("VIC", self.order))
        self.assertEqual((st["codong.win"]["default"], st["codong.win"]["options"]), ("MAX", ["MAX", "5Y", "2Y"]))
        self.assertEqual(st["codong.sub"]["options"], list(SUB_IDS))
        cov = self.man["inventory"]["coverage"]
        self.assertEqual([x for x in cov["missing"] + cov["mismatch"] if x.startswith("codong.")], [], cov)
        self.assertEqual(cov, {"missing": [], "mismatch": []})
        root = tree(self.files, self.man, "tab_codong.json")
        self.assertEqual(root.get("scope"), ["codong.tk"], "codong.sub/win có scope lồng, không gắn lên gốc")

    def test_inc_keys_match_plan(self):
        import chaebol_map_data_codong2_gia as P
        import chaebol_map_tab_codong_v2_chart as CH
        want = {"codong/_tong"}
        for tk in self.order:
            want |= {"codong/" + tk} | {"codong/%s/%s" % (tk, s) for s in SUB_IDS}
            w = P.weekly_full(tk)
            if w.get("ok"):
                want |= {"codong/%s/chart/%s" % (tk, x) for x in set(CH.window_plan(w["n_weeks"]).values())}
        self.assertEqual({k for k in self.man["inc"] if k.startswith("codong/")}, want)
        self.assertEqual(len({k for k in want if k.count("/") == 1}) - 1, 109)

    def test_no_dangling_inc(self):
        names = ["tab_codong.json"] + [self.man["inc"][k] for k in self.man["inc"] if k.startswith("codong/")]
        refs = {n["inc"] for name in names for n in walk(json.loads(self.files[name])["root"])
                if isinstance(n, dict) and "inc" in n}
        self.assertEqual(sorted(refs - set(self.man["inc"])), [])
        self.assertEqual(len([r for r in refs if r.count("/") == 1 and r != "codong/_tong"]), 109)

    def test_tab_size_time_and_no_error_warnings(self):
        self.assertEqual({t["id"]: t["status"] for t in self.man["tabs"]}["codong"], "ok")
        self.assertLessEqual(self.man["stats"]["per_tab"]["codong"]["bytes"], TAB_MAX_BYTES)
        self.assertLessEqual(self.times["codong"], TAB_MAX_S, "tab codong %.1f s" % self.times["codong"])
        self.assertEqual([w for w in self.warn if "lỗi" in w], [])

    def _check_budget(self, key, budget):
        nb, nn = size(self.files, self.man, key)
        if nb > budget[0] or nn > budget[1]:            # vượt trần chỉ được khi có cảnh báo hạ cấp của chính inc đó
            self.assertTrue(any(("codong v2: %s " % key) in w for w in self.warn), (key, nb, nn))

    def test_budgets(self):
        for key in self.man["inc"]:
            parts = key.split("/")
            if parts[0] != "codong":
                continue
            if key == "codong/_tong":
                self._check_budget(key, TONG_BUDGET)
            elif len(parts) == 2:
                self._check_budget(key, TK_BUDGET[parts[1] in self.old48])
            elif len(parts) == 3:
                self._check_budget(key, SUB_BUDGET[parts[2]])
            else:
                self._check_budget(key, CHART_BUDGET[parts[3]])
        text = self.files["tab_codong.json"]
        nb, nn = len(text.encode("utf-8")), D.count_nodes(json.loads(text)["root"])
        self.assertTrue((nb <= ROOT_BUDGET[0] and nn <= ROOT_BUDGET[1]) or any("(gốc)" in w for w in self.warn))

    def test_one_open_within_budget(self):
        """Một lần mở mã = codong/X + 1 sub (+ 1 khung khi sub là chart: inc khung chỉ nạp trong sub chart)."""
        for tk in ("VIC", "MBB", "REE", "GMD"):
            add = lambda a, b: (a[0] + b[0], a[1] + b[1])  # noqa: E731
            head = size(self.files, self.man, "codong/" + tk)
            opens = [add(head, size(self.files, self.man, "codong/%s/%s" % (tk, s))) for s in SUB_IDS if s != "chart"]
            chart = add(head, size(self.files, self.man, "codong/%s/chart" % tk))
            opens += [add(chart, size(self.files, self.man, k)) for k in self.man["inc"]
                      if k.startswith("codong/%s/chart/" % tk)]
            self.assertLessEqual(max(b for b, _ in opens), OPEN_BUDGET[0], tk)
            self.assertLessEqual(max(n for _, n in opens), OPEN_BUDGET[1], tk)

    # ── liên kết §8.3 ──

    def test_group_links(self):
        n = 0
        for g in self.v21["CHAEBOL_GROUPS"]:
            root = tree(self.files, self.man, "tab_%s.json" % g["id"])
            for t in g["tickers"]:
                tk = t["tk"] if isinstance(t, dict) else t
                nodes = by_key(root, lambda k, tk=tk: k == "cd2.link." + tk)
                if tk not in self.order:                    # LPBS chưa niêm yết: không nút
                    self.assertEqual(nodes, [], tk)
                    continue
                self.assertEqual(len(nodes), 1, tk)
                self.assertEqual(nodes[0]["on"], {"set": {"tab": "codong", "codong.tk": tk,
                                                          "codong.sub": "phase_info"}})
                n += 1
        self.assertGreaterEqual(n, 15)

    def test_vciq_links(self):
        vc = [k for k in self.man["inc"] if k.startswith("vciq/")]
        self.assertTrue(vc)
        for key in vc:
            tk = key.split("/")[1]
            nodes = by_key(tree(self.files, self.man, key), lambda k, tk=tk: k == "vciq.cd2." + tk)
            self.assertEqual(len(nodes), 1 if tk in self.order else 0, tk)
            if nodes:
                self.assertEqual(nodes[0]["on"], {"set": {"tab": "codong", "codong.tk": tk, "codong.sub": "capitaliq"}})

    def test_screener_cells(self):
        rows = by_key(tree(self.files, self.man, "tab_screener.json"), lambda k: k.startswith("scr.row."))
        self.assertGreaterEqual(len(rows), 30)
        for r in rows:
            tk = r["key"][len("scr.row."):]
            cell = r["k"][0]
            self.assertEqual(cell["t"], "td")
            want = {"set": {"tab": "codong", "codong.tk": tk}} if tk in self.order else None
            self.assertEqual(cell.get("on"), want, tk)
            self.assertFalse([c for c in cell.get("k", ()) if isinstance(c, dict) and c.get("t") == "button"], tk)


# ── harness offscreen ───────────────────────────────────────────────────────


def overlaps(geom, tol=2.0):
    """Cặp chữ (lá text) giao nhau quá tol px theo cả hai chiều trong cùng một SVG."""
    bad = []
    for svg in (n for n in geom["nodes"] if n["t"] == "svg"):
        rects = [(t["text"], r) for t in geom["texts"] if t["p"].startswith(svg["p"] + ".") for r in t["rects"]]
        for i, (a, ra) in enumerate(rects):
            for b, rb in rects[i + 1:]:
                dx = min(ra[0] + ra[2], rb[0] + rb[2]) - max(ra[0], rb[0])
                dy = min(ra[1] + ra[3], rb[1] + rb[3]) - max(ra[1], rb[1])
                if dx > tol and dy > tol:
                    bad.append((svg.get("key"), a, b))
    return bad


@unittest.skipUnless(LIVE_OK and HARNESS.is_file(), "chưa có chb_harness hoặc kho: bỏ test harness")
class Harness(unittest.TestCase):
    SHOTS = (("VIC", "chart", "MAX"), ("VIC", "chart", "5Y"), ("VIC", "chart", "2Y"), ("MBB", "capitaliq", None),
             ("GEL", "chart", None), ("FOX", "phase_info", None), ("FOX", "chart", None), ("REE", "chart", "MAX"))

    @classmethod
    def setUpClass(cls):
        cls.build = build_dir()
        cls.out = Path(os.environ.get("CHB_SHOT_DIR") or (Path(_CACHE["tmp"]) / "shots"))
        cls.out.mkdir(parents=True, exist_ok=True)

    def run_h(self, *args):
        res = subprocess.run([str(HARNESS), "--build", str(self.build), *args], capture_output=True, text=True,
                             timeout=300)
        self.assertEqual(res.returncode, 0, res.stderr[-2000:])
        return res

    def test_shots_layout_and_no_overlap(self):
        for tk, sub, win in self.SHOTS:
            name = "%s_%s%s" % (tk, sub, "_" + win if win else "")
            st = ["--state", "codong.tk=" + tk, "--state", "codong.sub=" + sub]
            st += ["--state", "codong.win=" + win] if win else []
            self.run_h("--tab", "codong", *st, "--png", str(self.out / (name + ".png")),
                       "--geom", str(self.out / (name + ".json")))
            geom = json.loads((self.out / (name + ".json")).read_text("utf-8"))
            meta = geom["meta"]
            self.assertLess(meta["timing_ms"]["layout"], 150, name)
            self.assertEqual((meta["state"]["codong.tk"], meta["state"]["codong.sub"]), (tk, sub), name)
            self.assertEqual(overlaps(geom), [], name)
            if sub == "chart" and tk != "FOX":
                self.assertTrue([n for n in geom["nodes"] if n["t"] == "svg" and n.get("key") == "cd2.svg"], name)

    def test_link_clicks_keep_codong_state(self):
        """Bấm nút liên kết = merge on.set → render → reset scope: tab + codong.tk + codong.sub không bị reset; đổi mã
        khi ở chart giữ khung; rời sub chart thì khung về MAX (§3.1)."""
        files, man, _, _ = live_build()
        g = tree(files, man, "tab_tuanmuot.json")
        link = by_key(g, lambda k: k.startswith("cd2.link."))[0]
        vtk = "MBB"
        vlink = by_key(tree(files, man, "vciq/" + vtk), lambda k: k == "vciq.cd2." + vtk)[0]
        shots = [("a", [{"tab": "tuanmuot"}, link["on"]["set"]]),
                 ("b", [{"tab": "vciq", "vciq.tk": vtk, "vciq.sub": "codong"}, vlink["on"]["set"]]),
                 ("c", [{"codong.tk": "VIC", "codong.sub": "chart", "codong.win": "2Y"}, {"codong.tk": "MSN"}]),
                 ("d", [{"codong.sub": "phase_info"}])]
        plan = self.out / "link_plan.json"
        plan.write_text(json.dumps({"schema": "chb_build_plan/1", "shots": [
            {"file": "link_%s.png" % f, "steps": s} for f, s in shots]}), "utf-8")
        self.run_h("--plan", str(plan), "--out", str(self.out))
        state = {f: json.loads((self.out / ("link_%s.json" % f)).read_text("utf-8"))["meta"]["state"] for f, _ in shots}
        want_a = link["on"]["set"]
        self.assertEqual({k: state["a"][k] for k in want_a}, want_a)
        self.assertEqual({k: state["b"][k] for k in vlink["on"]["set"]}, vlink["on"]["set"])
        self.assertEqual((state["c"]["codong.tk"], state["c"]["codong.sub"], state["c"]["codong.win"]),
                         ("MSN", "chart", "2Y"))
        self.assertEqual((state["d"]["codong.sub"], state["d"]["codong.win"]), ("phase_info", "MAX"))


if __name__ == "__main__":
    unittest.main()
