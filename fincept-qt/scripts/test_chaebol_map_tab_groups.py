#!/usr/bin/env python3
"""Unit tests cho tab nhóm 02–06 của chaebol_map (chaebol_map_tab_groups + _live) — không mạng.

Chạy (cả hai trình thông dịch, PYTHONDONTWRITEBYTECODE=1):
    python3 -m unittest scripts/test_chaebol_map_tab_groups.py -v
    ~/Library/Application\\ Support/com.fincept.terminal/venv-numpy2/bin/python -m unittest \\
        scripts/test_chaebol_map_tab_groups.py

Chuỗi vàng lấy từ chaebol_map_spec/page_p5_groups_screener.md §6 (ma trận thể hiện) và §5 (PhaseBar), đã khớp ảnh
ref 06–10, 35–40 ≥ 99,99 % qua oracle Chrome (27/09/2026). Test live dùng lớp dữ liệu giả (không kho) để có chuỗi
vàng tất định; test trên kho thật chỉ chạy khi có v21_const + vc_lk (chỉ đọc) và kiểm luật nhãn bậc.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("CHB_TODAY", "2026-09-27")

import chaebol_map as M  # noqa: E402
import chaebol_map_dom as D  # noqa: E402
import chaebol_map_shell as S  # noqa: E402
import chaebol_map_tab_groups as G  # noqa: E402
import chaebol_map_tab_groups_live as L  # noqa: E402

VENV_PY = Path.home() / "Library/Application Support/com.fincept.terminal/venv-numpy2/bin/python"
V21_FILE = M.bridge_dir() / "data" / "chaebol_map" / "v21_const.json"
GROUPS = {"tuanmuot": ["GEX", "GEE", "GEL", "VGC", "VIX", "EIB"], "sovico": ["VJC", "HDB"], "phuong": ["VCI", "IDP"],
          "bauthuy": ["LPB", "STB", "THD", "LPBS"], "eliminated": ["DGC", "PC1", "CTD"]}
GUARD = textwrap.dedent("""
    import socket, runpy, sys
    def _blocked(*a, **k):
        raise RuntimeError("mạng bị chặn trong test chaebol_map")
    socket.socket = _blocked
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked
    sys.argv = [sys.argv[1]] + sys.argv[2:]
    runpy.run_path(sys.argv[0], run_name="__main__")
""")
_REAL_SOCKET = {}
_V21 = None


def setUpModule():
    def blocked(*a, **k):
        raise RuntimeError("mạng bị chặn trong test chaebol_map")
    for name in ("socket", "create_connection", "getaddrinfo"):
        _REAL_SOCKET[name] = getattr(socket, name)
        setattr(socket, name, blocked)


def tearDownModule():
    for name, fn in _REAL_SOCKET.items():
        setattr(socket, name, fn)


def v21_const():
    global _V21
    if _V21 is None:
        _V21 = json.loads(V21_FILE.read_text(encoding="utf-8")) if V21_FILE.is_file() else {}
    return _V21


# ── duyệt cây ───────────────────────────────────────────────────────────────


def walk(node, parents=()):
    yield node, parents
    if isinstance(node, dict):
        for ch in node.get("k", ()):
            yield from walk(ch, parents + (node,))


def text_of(node):
    if isinstance(node, str):
        return node
    return "".join(text_of(c) for c in node.get("k", ()))


def find_key(root, key):
    for n, _ in walk(root):
        if isinstance(n, dict) and n.get("key") == key:
            return n
    return None


def keyed(root, prefix):
    return [n for n, _ in walk(root) if isinstance(n, dict) and str(n.get("key", "")).startswith(prefix)]


def visible(root, state):
    """Bản sao cây chỉ giữ nút có `if` đúng với state (như engine resolve)."""
    def ok(n):
        for k, v in (n.get("if") or {}).items():
            cur = "|".join(state.get(p, "") for p in k.split("|"))
            if (cur not in v) if isinstance(v, list) else (cur != v):
                return False
        return True

    def cp(n):
        if isinstance(n, str):
            return n
        if not ok(n):
            return None
        out = dict(n)
        if "k" in n:
            out["k"] = [c for c in (cp(x) for x in n["k"]) if c is not None]
        return out
    return cp(root)


NUM_RE = re.compile(r"(?<![\w/])[+\-−]?\d{1,3}(?:,\d{3})+(?:\.\d+)?"
                    r"|(?<![\w/])[+\-−]?\d+(?:[.,]\d+)?\s?(?:%|K tỷ|\s?tỷ|M cp|M\b|cp\b|đ\b|x\b|nghìn|triệu)")
DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{4}-\d{4}\b|\b(?:19|20)\d{2}\b")


def _has_label(node):
    for n, _ in walk(node):
        if isinstance(n, dict) and (n.get("_tier") or n.get("_can")):
            return True
    return False


def bare_numbers(root, levels=3):
    """Chữ có giá trị số (không tính ngày/năm) mà trong `levels` tổ tiên gần nhất không có nhãn bậc / [CẦN DATA]."""
    bad = []
    for n, parents in walk(root):
        if not isinstance(n, str) or not parents:
            continue
        if not NUM_RE.search(DATE_RE.sub(" ", n)):
            continue
        if parents[-1].get("_tier") or parents[-1].get("_can"):
            continue
        if not any(_has_label(p) for p in parents[-levels:]):
            bad.append(n[:90])
    return bad


# ── dựng ─────────────────────────────────────────────────────────────────────


def make_ctx(mode, data=None, dossier=None):
    ctx = M.Ctx(mode, date(2026, 9, 27), list(S.TABS_V21))
    ctx.v21 = v21_const()
    ctx.data = data
    ctx.dossier = dossier
    return ctx


def build(gid, mode="v21", data=None, dossier=None):
    with D.use_mode(mode, "2026-09-27"):
        ctx = make_ctx(mode, data, dossier)
        ctx.tab = gid
        res = getattr(G, "build_" + gid)(ctx)
    return res, ctx


class _V:
    def __init__(self, value, tier="FACT-T2", asof="2026-09-25", text=None):
        self.value, self.tier, self.asof, self.text, self.src, self.note, self.unit = value, tier, asof, text, "x", None, None
        self.can = value is None


class _Cols:
    def __init__(self, n):
        self.dates = ["2026-%02d-%02d" % (6 + i // 28, 1 + i % 28) for i in range(n)]

    def __len__(self):
        return len(self.dates)


class StubData:
    """Lớp dữ liệu giả, tất định: mọi mã có giá trừ IDP/LPBS; GEX số cố định để kiểm chuỗi vàng live.
    Tự doanh: GEX đủ 60/60 phiên tới 25/09; GEL chỉ 20/60 tới 18/09 (như kho thật 27/09); DGC tự doanh và THD NN
    nhỏ hơn 0,05M cp (kiểm định dạng nghìn cp thay '-0.0')."""
    NOPX = {"IDP", "LPBS"}
    PROP = {"GEL": (20, "2026-09-18")}              # mã → (số phiên có bản ghi, ngày bản ghi cuối); còn lại đủ
    TD = {"DGC": -0.0025}
    NN = {"THD": -0.012845}

    def prop_net(self, tk, n=60, end=None, kind="total"):
        nco = self.PROP.get(tk, (60, None))[0]
        return {"n": 60, "n_co": nco, "complete": nco == 60, "from": "2026-07-01", "to": "2026-09-25"}

    def vc(self, tk, ep):
        last = self.PROP.get(tk, (60, "2026-09-25"))[1]
        return {}, {"cot": ["tradingDate"], "hang": [["2026-06-30T00:00:00"], ["2026-07-01T00:00:00"],
                                                     [last + "T00:00:00"]]}

    def last_price(self, tk):
        return {"date": "2026-09-25", "raw": _V(None if tk in self.NOPX else (24000.0 if tk == "GEX" else 10000.0))}

    def price_history(self, tk):
        return None if tk in self.NOPX else _Cols(80)

    def pct_change(self, tk, d0, d1=None):
        return _V(-28.4 if d0 == "2026-05-08" else -23.7, "EST")

    def market_cap(self, tk):
        return _V(31403312592000.0)

    def shares_out(self, tk):
        return _V(1308471358.0, asof="2026-09-24")

    def flow4(self, tk, n=60, end=None):
        return {"nn": _V(self.NN.get(tk, -13.025195)), "td": _V(self.TD.get(tk, -1.91508)),
                "du": _V(14.940275, "EST"), "ca": _V(None), "tc": _V(None), "sig": _V(None),
                "from": "2026-07-01", "to": "2026-09-25"}

    def relationships(self, tk):
        return {"subsidiaries": [{"ticker": "GEE", "code": "X", "name": "Điện lực Gelex", "pct": _V(75.95)},
                                 {"ticker": "CAV", "code": "CAV", "name": "Dây cáp điện", "pct": _V(97.09)}]}

    def codong_moc(self, tk):
        return _V(None)

    def convert_price(self, tk, px, d0, d1=None):
        return _V(12381.0, "EST")

    def index_extremes(self, idx="VNINDEX", since=None, end=None):
        return {"since_start": _V(-6.8, "EST")}

    def tv30(self):
        return ["HDB", "LPB", "STB", "VJC"]          # đủ cho 17 mã nhóm: 4 mã này thuộc 30 mã Toàn Vũ


class StubNoTv30(StubData):
    """Không đọc được danh sách 30 mã Toàn Vũ → không xác nhận được mã nào."""
    tv30 = None


DECISIVE = ("ĐẠT", "BỊ BÁC", "TIỀN ĐỀ SAI")
PAT_BARE = re.compile(r"\bPattern (?:[A-D]|Mark(?:down|up))\b(?!\?)")


def decisive_u_only(root):
    """Pill ĐẠT/BỊ BÁC/TIỀN ĐỀ SAI mà mọi nhãn bậc sau nó (cùng cha) đều U — DESIGN §11.2: đầu vào U tối đa CHƯA RÕ."""
    bad = []
    for n, _ in walk(root):
        kids = n.get("k", ()) if isinstance(n, dict) else ()
        for i, c in enumerate(kids):
            if isinstance(c, dict) and not c.get("_tier") and text_of(c) in DECISIVE and len(c.get("k", ())) == 1:
                tiers = [s["_tier"] for s in kids[i + 1:] if isinstance(s, dict) and s.get("_tier")]
                if tiers and all(t == "UNVERIFIED" for t in tiers):
                    bad.append(text_of(n)[:120])
    return bad


# ── test ─────────────────────────────────────────────────────────────────────


@unittest.skipUnless(V21_FILE.is_file(), "không có v21_const.json")
class TestV21(unittest.TestCase):
    def test_states_and_structure(self):
        for gid, tks in GROUPS.items():
            res, ctx = build(gid)
            self.assertEqual(res["states"], [{"key": "grp.%s.tk" % gid, "default": tks[0], "options": tks}])
            root = res["root"]
            for k in ("grp-head", "grp-tickers", "grp-events"):
                self.assertIsNotNone(find_key(root, k), (gid, k))
            self.assertEqual(find_key(root, "eco") is not None, gid == "tuanmuot")
            btns = keyed(root, "grp-btn:")
            self.assertEqual([b["key"] for b in btns], ["grp-btn:" + t for t in tks])
            for b, t in zip(btns, tks):
                self.assertEqual(b["t"], "button")
                self.assertEqual(b["on"], {"set": {"grp.%s.tk" % gid: t}})
                self.assertEqual(b["var"][0]["if"], {"grp.%s.tk" % gid: t})
            cards = keyed(root, "card:")
            self.assertEqual([c["if"] for c in cards], [{"grp.%s.tk" % gid: t} for t in tks])
            self.assertEqual(ctx.warnings, [])

    def test_no_live_marks_in_v21(self):
        for gid in GROUPS:
            root = build(gid)[0]["root"]
            for n, _ in walk(root):
                if isinstance(n, dict):
                    self.assertFalse(set(n) & {"_tier", "_can", "_upd", "_v21"}, gid)
                else:
                    self.assertNotIn("CẦN DATA", n)
                    self.assertNotIn("V21·12/05", n)

    def test_button_lines(self):
        root = build("tuanmuot")[0]["root"]
        got = {b["key"][8:]: text_of(b) for b in keyed(root, "grp-btn:")}
        self.assertEqual(got, {"GEX": "GEX26,967 · +83.2%", "GEE": "GEE99,938 · +229.2%", "GEL": "GEL32,150 · -6.9%",
                               "VGC": "VGC", "VIX": "VIX16,700 · +75.2%", "EIB": "EIB"})
        root = build("bauthuy")[0]["root"]
        got = {b["key"][8:]: text_of(b) for b in keyed(root, "grp-btn:")}
        self.assertEqual(got, {"LPB": "LPB51,200 · +23.2%", "STB": "STB73,700 · +17.0%", "THD": "THD", "LPBS": "LPBS"})

    def test_gex_card_golden(self):
        root = build("tuanmuot")[0]["root"]
        card = visible(root, {"grp.tuanmuot.tk": "GEX"})
        gex = find_key(card, "card:GEX")
        t = text_of(gex)
        for s in ("HỒ SƠ DOANH NGHIỆPCTCP Tập đoàn GELEXGEX · Industrial Holding · Chaebol: Tuấn mượt",
                  "GIÁ HIỆN TẠI26,9672026-04-29", "CAFEF UPDATE39,30004-08/05/2026", "VỐN HÓA35.5K tỷ902M cp",
                  "POST-DILUTION13.1K tỷsau bonus + ESOP",
                  "Doanh thu (tỷ)39,51344,71210,72224%", "LN trước thuế (tỷ)4,6213,61570019%",
                  "Δ DT YoY: +13.2%Δ LN YoY: -21.8%",
                  "Eximbank (EIB)10% (~187M cp) · long-term", "Fairmont Hà Nội Hoteldeveloper · opened 30/3/2026",
                  "Tham chiếu cuối: 2026-04-29 · Giá 26,967 · Δ60d +83.2%",
                  "P3DCAPP1P2MARKUPP3P3DHiện tại: DISTRIBUTIONΔ60d: +83.2% · Flow: BULL"):
            self.assertIn(s, t)

    def test_vci_and_dgc_golden(self):
        vci = text_of(find_key(build("phuong")[0]["root"], "card:VCI"))
        for s in ("Doanh thu (tỷ)5,0216,5251,40021%", "LN trước thuế (tỷ)1,6292,30040017%",
                  "Δ DT YoY: +30%Δ LN YoY: +41%", "STB" + "GIẢM Q1 · rebalance", "Hiện tại: ACCUMULATION (★)"):
            self.assertIn(s, vci)
        self.assertEqual(vci.count("· core AFS"), 2)
        dgc = text_of(find_key(build("eliminated")[0]["root"], "card:DGC"))
        for s in ("Q1/2026 ACTUAL — KEY FINANCIALDOANH THU2,125 tỷ−24% YoYLNST HỢP NHẤT430 tỷvs Q1/25: 837 (-49%)"
                  "CASH POSITION11.3K tỷ62% tổng tài sản", "VALUE TRAP WATCH · Watchpoint:",
                  "Hiện tại: CAPITULATION"):
            self.assertIn(s, dgc)
        self.assertNotIn("KẾ HOẠCH 2026", dgc)

    def test_phase_bar_per_ticker(self):
        want = {"GEX": "DISTRIBUTION", "GEE": "DISTRIBUTION", "GEL": "ACCUMULATION (★)", "VIX": "EUPHORIA",
                "VJC": "DISTRIBUTION", "VCI": "ACCUMULATION (★)", "DGC": "CAPITULATION", "PC1": "DISTRIBUTION",
                "CTD": "ACCUMULATION (★)"}
        for gid, tks in GROUPS.items():
            root = build(gid)[0]["root"]
            for tk in tks:
                card = find_key(root, "card:" + tk)
                if tk in want:
                    self.assertIn("Hiện tại: " + want[tk], text_of(card), tk)
                else:
                    self.assertEqual(text_of(card), G.PLACEHOLDER[0] + tk + G.PLACEHOLDER[1], tk)

    def test_titles_events_eco(self):
        n_events = {"tuanmuot": 7, "sovico": 3, "phuong": 3, "bauthuy": 6, "eliminated": 4}
        for gid, n in n_events.items():
            root = build(gid)[0]["root"]
            ev = find_key(root, "grp-events")
            self.assertTrue(text_of(ev).startswith("⌖ Key Events Timeline (12 tháng)"))
            self.assertEqual(len(ev["k"][1]["k"][0]["k"]), n, gid)
        root = build("eliminated")[0]["root"]
        self.assertTrue(text_of(find_key(root, "grp-head")).startswith(
            "⛔ LOẠI KHỎI CUỘC CHƠI · DEEP DIVECác nhóm bị \"nắn gân\""))
        eco = text_of(find_key(build("tuanmuot")[0]["root"], "eco"))
        for s in ("CHAEBOL-MAP · HỆ SINH THÁI GELEX · Nguồn: Chaebol Project Vietnam 11/05/2026", "NGUYỄN VĂN TUẤN",
                  "CAV — CADIVIDây cáp điện~96-97%", "SỞ HỮU ~70%GEL — GELEX INFRASTRUCTURE",
                  "Gelex sở hữu: ~10%VIX sở hữu: ~3.58%Nhóm liên quan khác: thêm", "1. GEE tạo dòng tiền"):
            self.assertIn(s, eco)
        self.assertEqual(eco.count("→"), 5)


class TestRules(unittest.TestCase):
    def test_phase_of(self):
        cases = [((-49.7, "BEAR"), "CAP"), ((-30, "BULL"), "P1"), ((-10.5, "MIX"), "P1"), ((-4.7, "BEAR"), "P3D"),
                 ((5, "MIX"), "P1"), ((9.99, "BULL"), "P2"), ((10, "BULL"), "MARKUP"), ((39.9, "BULL"), "MARKUP"),
                 ((40, "MIX"), "P3"), ((79.9, "BULL"), "P3"), ((80, "BULL"), "P3D"), ((20, "MIX"), "P1")]
        for (perf, sig), ph in cases:
            self.assertEqual(G.phase_of(perf, sig)[0], ph, (perf, sig))
        self.assertEqual(G.phase_of(-10.5, "MIX")[2], "DOUBT/NEGLECT")
        self.assertEqual(G.phase_of(20, "MIX")[2], "NEGLECT")

    def test_truthy(self):
        for x, want in ((None, False), (0, False), (0.0, False), ("", False), ([], True), ({}, True), (13.2, True),
                        ("x", True)):
            self.assertEqual(G.truthy(x), want, x)

    def test_bare_number_checker(self):
        with D.use_mode("live", "2026-09-27"):
            ok = D.h("div", None, "LNST 1,372 tỷ", D.tier("U"))
            bad = D.h("div", None, D.h("span", None, "giá 24,000"))
            self.assertEqual(bare_numbers(ok), [])
            self.assertEqual(bare_numbers(bad), ["giá 24,000"])
            self.assertEqual(bare_numbers(D.h("div", None, "ĐHĐCĐ 24/04/2026 · kỳ 2025-12 · Q1/26")), [])


@unittest.skipUnless(V21_FILE.is_file(), "không có v21_const.json")
class TestLiveStub(unittest.TestCase):
    def test_live_without_data_or_dossier(self):
        for gid in GROUPS:
            res, ctx = build(gid, "live")
            self.assertEqual(bare_numbers(res["root"]), [], gid)
            self.assertTrue(any("chưa có dossier" in w for w in ctx.warnings))
            self.assertTrue(any("không nạp được" in w for w in ctx.warnings))
            self.assertIn("[CẦN DATA]", text_of(res["root"]))
        root = build("tuanmuot", "live")[0]["root"]
        self.assertIn("NHÓM TUẤN MƯỢT · DEEP DIVE", text_of(find_key(root, "grp-head")))
        self.assertIn("V21·12/05", text_of(find_key(root, "grp-head")))

    def test_live_stub_golden(self):
        res, ctx = build("tuanmuot", "live", data=StubData())
        root = res["root"]
        self.assertEqual(bare_numbers(root), [])
        btn = text_of(find_key(root, "grp-btn:GEX"))
        self.assertEqual(btn, "GEX24,000T2·25/09 · -23.7%E·25/09")
        gex = text_of(find_key(root, "card:GEX"))
        for s in ("GIÁ HIỆN TẠI24,000T2·25/092026-09-25", "Δ TỪ 08/05-28.4%E·25/09giá điều chỉnh quyền",
                  "VỐN HÓA31.4K tỷT2·25/091308M cpT2·24/09",
                  L.FLOW_HEAD_LIVE,
                  "Cá nhân[CẦN DATA]Tổ chức[CẦN DATA]Tự doanh-1.9MT2·25/09Nước ngoài-13.0MT2·25/09",
                  "Phần dư −(NN+TD) = +14.9ME·25/09 · phần dư, không phải kênh thật",
                  "Bản V21 · FiinTrade 60 phiên tới 2026-04-29: CN -45.4 · TC +52.8 · TD +26.4 · NN -33.7 (M cp) · BULL"
                  "T2·29/04V21·12/05",
                  "Hiện tại: DISTRIBUTIONV21·12/05Δ60d: +83.2%T2·29/04V21·12/05 · Flow: BULL"):
            self.assertIn(s, gex)
        self.assertEqual(text_of(find_key(root, "grp-btn:VGC")), "VGC10,000T2·25/09 · -23.7%E·25/09")
        eco = text_of(find_key(root, "eco-map"))
        self.assertIn("CAV — CADIVIDây cáp điện97.09%T2", eco)
        self.assertIn("SỞ HỮU 75.95%T2GEE — GELEX ELECTRIC", eco)
        self.assertIn("THI — THIBIDIMáy biến áp, thiết bị điện~98%U", eco)
        self.assertTrue(res["csv"] and res["csv"][0]["ma"] == "GEX" and res["csv"][0]["gia"] == 24000.0)
        res2 = build("bauthuy", "live", data=StubData())[0]
        self.assertEqual(text_of(find_key(res2["root"], "grp-btn:LPBS")), "LPBS[CẦN DATA]")
        self.assertEqual(bare_numbers(res2["root"]), [])

    # ── sửa sau kiểm chứng 27/09 ────────────────────────────────────────────
    def test_td_label_date_and_residual_window(self):
        """TD mang ngày bản ghi tự doanh cuối + số phiên có bản ghi; phần dư chỉ tính khi đủ cửa sổ (DESIGN §9)."""
        root = build("tuanmuot", "live", data=StubData())[0]["root"]
        gel = text_of(find_key(root, "card:GEL"))
        self.assertIn("Tự doanh-1.9MT2·18/09Nước ngoài-13.0MT2·25/09", gel)
        self.assertIn("Tự doanh: 20/60 phiên có bản ghi, tới 18/09", gel)
        self.assertIn("Phần dư −(NN+TD) = [CẦN DATA — tự doanh chỉ 20/60 phiên có bản ghi, tới 18/09 — lệch cửa sổ"
                      " với NN, không tính]", gel)
        self.assertIn("TỰ DOANH 60 PHIÊN-1.9M cpT2·25/09khớp · 60/60 phiên có bản ghi, tới 25/09",
                      text_of(find_key(root, "grp-live:VGC")))

    def test_small_flow_values_not_minus_zero(self):
        """|x| < 0,05M cp → nghìn cp; không in '-0.0' (mất dấu và độ lớn)."""
        el = build("eliminated", "live", data=StubData())[0]["root"]
        self.assertIn("Tự doanh-2.5KT2·25/09", text_of(find_key(el, "card:DGC")))
        bt = build("bauthuy", "live", data=StubData())[0]["root"]
        self.assertIn("NN 60 PHIÊN-13K cpT2·25/09", text_of(find_key(bt, "grp-live:THD")))
        for root in (el, bt):
            self.assertNotRegex(text_of(root), r"(Tự doanh|Nước ngoài|PHIÊN)[+-]?0\.0M")
        f = L.LiveGroup._mfmt
        self.assertEqual([f(0.025), f(-0.0025), f(0.034, "M cp"), f(0.0), f(-0.05), f(-3.7871)],
                         ["+25K", "-2.5K", "+34K cp", "0K", "-0.1M", "-3.8M"])

    def test_chip_labels_follow_active_color(self):
        """Nhãn bậc / [CẦN DATA] trên nút mã đổi sang màu chữ chip (C.bg) khi chip active, như số Δ60d."""
        root = build("phuong", "live", data=StubData())[0]["root"]
        for tk in ("VCI", "IDP"):
            line = find_key(root, "grp-btn:" + tk)["k"][1]
            marks = [n for n, _ in walk(line) if isinstance(n, dict) and (n.get("_tier") or n.get("_can"))]
            self.assertTrue(marks, tk)
            for n in marks:
                self.assertEqual(n.get("var"), [{"if": {"grp.phuong.tk": tk}, "s": {"color": D.C.bg}}], tk)

    def test_eco_labels_on_dark_pill_only_in_map(self):
        root = build("tuanmuot", "live", data=StubData())[0]["root"]
        marks = [n for n, _ in walk(find_key(root, "eco-map")) if isinstance(n, dict) and n.get("_tier")]
        self.assertGreater(len(marks), 5)
        self.assertEqual({n["s"].get("background") for n in marks}, {D.C.paper})
        card = find_key(root, "card:GEX")
        self.assertFalse([n for n, _ in walk(card) if isinstance(n, dict) and n.get("_tier")
                          and "background" in n.get("s", {})])

    def test_howard_label_without_v21_mark(self):
        """Dấu V21 cạnh nhãn HOWARD MARKS bị marker pha (top −22) đè → chỉ giữ ở dòng 'Hiện tại'."""
        vci = find_key(build("phuong", "live", data=StubData())[0]["root"], "card:VCI")
        labels = [n for n, _ in walk(vci) if isinstance(n, dict) and n.get("k", [None])[0] == "◐ HOWARD MARKS PHASE"]
        self.assertEqual([text_of(n) for n in labels], ["◐ HOWARD MARKS PHASE"])
        self.assertIn("Hiện tại: ACCUMULATION (★)V21·12/05", text_of(vci))

    def test_vix_stop_compared_on_adjusted_basis(self):
        vix = text_of(find_key(build("tuanmuot", "live", data=StubData())[0]["root"], "card:VIX"))
        self.assertIn("Trên nền giá hiện hành, mốc 13K quy đổi quyền ≈ 12,381E·25/09; đóng cửa 25/09 = "
                      "10,000T2·25/09 — đang dưới mốc này.", vix)

    def test_dossier_parts_cells_fields_holdings(self):
        """parts: mỗi vế một bậc/ngày; ô KQKD có nguồn riêng, ô '—' → [CẦN DATA]; verify.fields chỉ chứng thực đúng ô
        KH có trong nguồn (ô khác là số V21 → U + V21·12/05); holdings value_asof → nhãn riêng cho stake và value."""
        s = "x"
        dz = {"chaebol_groups": {"sovico": {"deep_dive": {"events_new": [
            {"date": "18/08/2026", "text": "room 50%", "tier": "FACT-T1", "asof": "2026-08-18", "src": s,
             "parts": [{"text": "; NN 46.6%.", "tier": "FACT-T2", "asof": "2026-09-23", "src": s}]}]}}},
            "tickers": {
                "VJC": {"deep_card": {"kqkd": {
                    "text": "KH · 6T", "tier": "UNVERIFIED", "asof": "2026-07-31", "src": s,
                    "head": ["METRIC", "KH 2026", "6T/2026"],
                    "rows": [["DT", {"text": "86,774", "tier": "UNVERIFIED", "asof": "2026-04-24", "src": s}, "—"],
                             ["LNST", "—", "1,372"]]}}},
                "VCI": {"deep_card": {"plan": {"verify": {"text": "KH LNTT", "tier": "UNVERIFIED", "asof": "2026-08-17",
                                                          "src": s, "fields": ["pretax_b"]}}}},
                "GEX": {"deep_card": {"holdings": [{"text": "HAH (Hải An)", "tier": "FACT-T2", "asof": "2026-08-26",
                                                    "value_asof": "2026-09-23", "src": s, "stake": "5.16%",
                                                    "value": "đăng ký bán 23/09"}]}}}}
        sov = build("sovico", "live", data=StubData(), dossier=dz)[0]["root"]
        self.assertIn("18/08/2026room 50%T1·18/08; NN 46.6%.T2·23/09↻27/09", text_of(find_key(sov, "grp-events")))
        vjc = text_of(find_key(sov, "card:VJC"))
        self.assertIn("DT86,774U·24/04[CẦN DATA]LNST[CẦN DATA]1,372U·31/07", vjc)
        vci = text_of(find_key(build("phuong", "live", data=StubData(), dossier=dz)[0]["root"], "card:VCI"))
        self.assertIn("Doanh thu (tỷ)5,021U6,525UV21·12/05", vci)
        self.assertIn("LN trước thuế (tỷ)1,629U2,300U·17/08", vci)
        gex = text_of(find_key(build("tuanmuot", "live", data=StubData(), dossier=dz)[0]["root"], "card:GEX"))
        self.assertIn("HAH (Hải An)5.16%T2·26/08 · đăng ký bán 23/09T2·23/09", gex)

    # ── vòng hoàn thiện 27/09 (final_check §6.1 #1, #5, #6) ─────────────────
    def test_pattern_q_outside_tv30(self):
        """Mã ngoài 30 mã Toàn Vũ: 'Pattern X' trong thẻ (kể cả câu V21) → 'Pattern X?'; mã trong 30 mã giữ nguyên;
        mode v21 không đổi; không đọc được danh sách 30 mã → gắn '?' cho mọi mã."""
        tm = build("tuanmuot", "live", data=StubData())[0]["root"]
        for tk in ("GEX", "GEL", "VIX"):
            t = text_of(find_key(tm, "card:" + tk))
            self.assertNotRegex(t, PAT_BARE, tk)
            self.assertIn("Pattern B?", t, tk)
        self.assertIn("Đây là điển hình Pattern B? đáy + đầu Markup theo Toàn Vũ.", text_of(find_key(tm, "card:GEX")))
        vci = text_of(find_key(build("phuong", "live", data=StubData())[0]["root"], "card:VCI"))
        self.assertEqual(vci.count("Pattern B?"), 3)
        dgc = text_of(find_key(build("eliminated", "live", data=StubData())[0]["root"], "card:DGC"))
        self.assertIn("Pattern A? textbook ở đỉnh nhưng chuyển về Pattern Markdown? nhanh", dgc)
        vjc = text_of(find_key(build("sovico", "live", data=StubData())[0]["root"], "card:VJC"))
        self.assertIn("Đây là Pattern A dấu hiệu distribution", vjc)            # VJC thuộc 30 mã: không '?'
        vjc = text_of(find_key(build("sovico", "live", data=StubNoTv30())[0]["root"], "card:VJC"))
        self.assertIn("Đây là Pattern A? dấu hiệu distribution", vjc)
        self.assertIn("Pattern B đáy + đầu Markup", text_of(find_key(build("tuanmuot")[0]["root"], "card:GEX")))
        self.assertEqual(L._PAT_Q.sub(r"Pattern \1?", "Pattern A? · Pattern C · Pattern Markup · Pattern Box"),
                         "Pattern A? · Pattern C? · Pattern Markup? · Pattern Box")

    def test_v21_part_and_split_labels(self):
        """Vế `v21: true` = chữ V21 giữ nguyên văn → nhãn không ngày + V21·12/05; head_title dùng seg() nên mỗi vế một
        nhãn (không gộp vế U dưới T1); pill quyết định với vế T1 + vế U → nhãn riêng từng vế."""
        s = "x"
        dz = {"chaebol_groups": {"bauthuy": {"deep_dive": {
            "head_title": {"text": "Operator", "tier": "UNVERIFIED", "asof": "2026-05-12", "v21": True, "src": s,
                           "parts": [{"text": " · Phó CT TT từ 22/04/2026", "tier": "FACT-T1", "asof": "2026-04-22",
                                      "src": s},
                                     {"text": " · rời DS ≥1% LPB (báo chí)", "tier": "UNVERIFIED",
                                      "asof": "2026-06-23", "src": s}]},
            "events_status": {"4": {"text": "LNTT Q1 2,826.5 tỷ", "tier": "FACT-T1", "asof": "2026-04-20", "src": s,
                                    "status": "BỊ BÁC", "date": "20/04/2026",
                                    "parts": [{"text": "; 6T 5,973 tỷ (báo chí).", "tier": "UNVERIFIED",
                                               "asof": "2026-07-21", "src": s}]}}}}}}
        root = build("bauthuy", "live", data=StubData(), dossier=dz)[0]["root"]
        self.assertIn("OperatorUV21·12/05 · Phó CT TT từ 22/04/2026T1·22/04 · rời DS ≥1% LPB (báo chí)U·23/06↻27/09",
                      text_of(find_key(root, "grp-head")))
        ev = text_of(find_key(root, "grp-events"))
        self.assertIn("20/04/2026↻27/09", ev)
        self.assertIn("BỊ BÁC LNTT Q1 2,826.5 tỷT1·20/04; 6T 5,973 tỷ (báo chí).U·21/07↻27/09", ev)
        self.assertEqual(decisive_u_only(root), [])
        dz["chaebol_groups"]["bauthuy"]["deep_dive"]["events_status"]["4"]["tier"] = "UNVERIFIED"
        bad = decisive_u_only(build("bauthuy", "live", data=StubData(), dossier=dz)[0]["root"])
        self.assertEqual(len(bad), 1)                                           # bộ kiểm bắt được pill chỉ có U


def _real_live():
    """ctx live trên kho thật (chỉ đọc) — None nếu thiếu kho."""
    if not V21_FILE.is_file() or not (M.bridge_dir() / "state" / "vc_lk" / "GEX" / "price-history.json").is_file():
        return None
    with D.use_mode("live", "2026-09-27"):
        ctx = make_ctx("live")
        ctx.data = M.load_data_module(ctx)
        if ctx.data is None:
            return None
        ctx.dossier = M.load_dossier(ctx)
    return ctx


class TestLiveReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = _real_live()
        if cls.ctx is None:
            raise unittest.SkipTest("không có kho thật (v21_const / vc_lk / chaebol_map_data)")
        cls.res = {}
        with D.use_mode("live", "2026-09-27"):
            for gid in GROUPS:
                cls.ctx.tab = gid
                cls.res[gid] = getattr(G, "build_" + gid)(cls.ctx)

    def test_every_number_labelled(self):
        for gid, res in self.res.items():
            self.assertEqual(bare_numbers(res["root"]), [], gid)

    def test_flow_and_stance(self):
        gex = text_of(find_key(self.res["tuanmuot"]["root"], "card:GEX"))
        self.assertIn("Cá nhân[CẦN DATA]Tổ chức[CẦN DATA]", gex)
        self.assertIn("Pattern B? đáy + đầu Markup theo Toàn Vũ.T2·29/04V21·12/05", gex)   # GEX ngoài 30 mã TV
        vjc = text_of(find_key(self.res["sovico"]["root"], "card:VJC"))
        self.assertIn("★ KHÔNG MUA ĐUỔI.", vjc)                       # stance V21 giữ nguyên văn …
        self.assertIn("V21·12/05", vjc)                                # … kèm dấu V21

    def test_dossier_applied(self):
        if not isinstance(self.ctx.dossier, dict) or "chaebol_groups" not in self.ctx.dossier:
            self.skipTest("chưa có dossier cap_nhat_2026-09-27.groups.json")
        gel = text_of(find_key(self.res["tuanmuot"]["root"], "card:GEL"))
        self.assertIn("CTCP Hạ tầng GELEX", gel)
        self.assertIn("không phải 'Gelex Logistics'", gel)
        gex = text_of(find_key(self.res["tuanmuot"]["root"], "card:GEX"))
        self.assertIn("GEE (Gelex Electric)75.95% · 30/06/2026", gex)
        self.assertIn("23.63%", gex)
        self.assertIn("6T/26 ACTUAL", gex)
        bt = self.res["bauthuy"]["root"]
        self.assertIn("Phó CT thường trực STB từ 22/04/2026", text_of(find_key(bt, "grp-head")))
        self.assertIn("Phạm Thu Hương 4.965%", text_of(find_key(bt, "card:LPB")))
        self.assertIn("mã LPS", text_of(find_key(bt, "card:LPBS")))
        el = self.res["eliminated"]["root"]
        self.assertIn("Bolat Duisenov vẫn là Chủ tịch ExCom", text_of(find_key(el, "grp-head")))
        self.assertIn("PC1 đổi chủ thể", text_of(find_key(el, "grp-head")))
        # sự kiện mới 09/05→27/09 đứng trước sự kiện V21
        ev = find_key(self.res["sovico"]["root"], "grp-events")
        self.assertTrue(text_of(ev).startswith("⌖ Key Events Timeline (12 tháng → 27/09/2026)22/09/2026"))

    def test_flow_windows_consistent(self):
        """Kho thật: phần dư có số ⇒ TD và NN cùng ngày cuối; không thanh/ô nào in '±0.0M'."""
        tdr = re.compile(r"Tự doanh[+-][\d.]+[MK]T2·(\d\d/\d\d)")
        nnr = re.compile(r"Nước ngoài[+-][\d.]+[MK]T2·(\d\d/\d\d)")
        for gid, res in self.res.items():
            for card in keyed(res["root"], "card:"):
                t = text_of(card)
                self.assertNotRegex(t, r"(Tự doanh|Nước ngoài|PHIÊN)[+-]?0\.0M", card["key"])
                if re.search(r"Phần dư −\(NN\+TD\) = [+-]", t):
                    self.assertEqual(tdr.search(t).group(1), nnr.search(t).group(1), card["key"])

    def test_verified_fixes_in_dossier(self):
        if not isinstance(self.ctx.dossier, dict) or "chaebol_groups" not in self.ctx.dossier:
            self.skipTest("chưa có dossier cap_nhat_2026-09-27.groups.json")
        R = {g: r["root"] for g, r in self.res.items()}
        self.assertIn("; P/E 316x, P/B 9.5x (22/09).T2·22/09", text_of(find_key(R["bauthuy"], "grp-live:THD")))
        self.assertIn("; P/E 316x (22/09).T2·22/09", text_of(find_key(R["bauthuy"], "grp-update")))
        self.assertIn("86,774U·24/04[CẦN DATA][CẦN DATA]", text_of(find_key(R["sovico"], "card:VJC")))
        self.assertIn("6,525UV21·12/05", text_of(find_key(R["phuong"], "card:VCI")))
        self.assertIn("; NN đang nắm 46.6%.T2·23/09", text_of(find_key(R["eliminated"], "card:CTD")))
        head = text_of(find_key(R["eliminated"], "grp-head"))
        self.assertIn("EVNNPT–PC1 — theo báo chí, chưa có văn bản tố tụng trong khoU·16/05", head)
        self.assertNotIn("vụ án thật", head)
        vix = text_of(find_key(R["tuanmuot"], "card:VIX"))
        self.assertRegex(vix, r"đã thủng từ 20/07 trên cùng nền giá thô.*đang (trên|dưới) mốc này")
        self.assertIn("bà Nguyễn Thị Tuyết 4.98%T2·03/07/24", vix)
        self.assertIn("4.98% VIX (mốc 07/2024)T2·03/07/24", text_of(find_key(R["tuanmuot"], "eco-map")))
        self.assertIn("30 ngày đầu (tới 06/03) đóng cửa thấp nhất 33,700", text_of(find_key(R["tuanmuot"], "card:GEL")))
        self.assertIn("13.1K tỷT1·30/06", text_of(find_key(R["tuanmuot"], "card:GEX")))
        self.assertIn("chạm lần đầu ngày 10/07/2026 (đóng cửa 19,750).T2·10/07",
                      text_of(find_key(R["tuanmuot"], "grp-live:EIB")))

    # ── vòng hoàn thiện 27/09 (final_check §6.1 #1, #5, #6) ─────────────────
    def test_pattern_suffix_real(self):
        """#1: không còn 'Pattern X' trần trong thẻ mã ngoài 30 mã Toàn Vũ (đọc lk_hoso/_index.toan_vu)."""
        tv = set(self.ctx.data.tv30())
        n = 0
        for gid, res in self.res.items():
            for card in keyed(res["root"], "card:"):
                tk = card["key"][5:]
                t = text_of(card)
                if tk not in tv:
                    self.assertNotRegex(t, PAT_BARE, tk)
                    n += t.count("Pattern ")
        self.assertGreaterEqual(n, 10)          # GEX ×3, GEL, VIX, VCI ×3, DGC ×2 (A + Markdown)
        self.assertIn("Đây là Pattern A dấu hiệu", text_of(find_key(self.res["sovico"]["root"], "card:VJC")))

    def test_no_decisive_pill_on_u_only(self):
        """#5: không pill ĐẠT/BỊ BÁC/TIỀN ĐỀ SAI nào chỉ dựa trên bằng chứng U."""
        for gid, res in self.res.items():
            self.assertEqual(decisive_u_only(res["root"]), [], gid)

    def test_completion_fixes_in_dossier(self):
        if not isinstance(self.ctx.dossier, dict) or "chaebol_groups" not in self.ctx.dossier:
            self.skipTest("chưa có dossier cap_nhat_2026-09-27.groups.json")
        R = {g: r["root"] for g, r in self.res.items()}
        ph = text_of(R["phuong"])                                               # #5 phuong: T1 CBTT 20/07
        self.assertIn("BỊ BÁC Q2/2026 LNTT 270.8 tỷ (+28% YoY), LNST 250.6 tỷ (CBTT giải trình 20/07)", ph)
        self.assertIn("270.8 tỷ < 600 tỷ (CBTT giải trình 20/07)T1·20/07; 6T 675 tỷ ≈ 29% KH (báo chí).U·17/08", ph)
        ev = text_of(find_key(R["bauthuy"], "grp-events"))                      # #5 bauthuy
        self.assertIn("CHƯA RÕ Theo báo chí: IPO hoàn tất 16/06", ev)
        self.assertNotIn("ĐẠT IPO", ev)
        self.assertIn("28/04/2026↻27/09", ev)
        self.assertIn("không phải 16,000 tỷ (+25%)T1·28/04; cổ tức năm 2025 trả bằng tiền 3,000 đ/cp (30%)", ev)
        self.assertIn("LNTT Q1 2,826.5 tỷ, thấp hơn Q1/2025 3,175.4 tỷ", ev)
        self.assertIn("ĐẠT Vào Ban TGĐ Sacombank 23/12/2025, rời ngày 22/04/2026", ev)          # #6 grp-events
        self.assertIn("'bổ nhiệm chức danh TGĐ'T1·22/04; báo chí nêu ông là TGĐ từ 03/03/2026", ev)
        vjc = text_of(find_key(R["sovico"], "card:VJC"))                        # C17: đầu vào T1, phép tính E
        self.assertIn("6T hơn 13.4 triệu kháchT1·30/07 → Q1 ≈ 7.2 triệu, Q2 ≈ −13.9% QoQ", vjc)
        head = text_of(find_key(R["bauthuy"], "grp-head"))                       # #6
        self.assertIn("Xuân ThiệnUV21·12/05 · Phó CT thường trực STB từ 22/04/2026T1·22/04 · rời DS ≥1% LPB (báo chí)"
                      "U·23/06↻27/09", head)
        gex = text_of(find_key(R["tuanmuot"], "card:GEX"))
        self.assertIn("TIỀN ĐỀ SAI Tiền đề 'Eximbank deal close'", gex)
        self.assertIn("trước ngày dựngT1·01/07/24; GEX chưa lần nào vượt 36,200 sau 08/05.T2·25/09", gex)
        self.assertIn("P/B 3.22xT2·25/09, cao hơn trung bình ~2.1σE·25/09; NN mua ròng 884 tỷ từ 11/05.T2·25/09",
                      text_of(find_key(R["bauthuy"], "grp-live:LPB")))
        self.assertIn("P/B 2.30xT2·25/09 (+2.7σ so trung bình)E·25/09; đỉnh lịch sử 78,200 ngày 18/09T2·18/09",
                      text_of(find_key(R["bauthuy"], "grp-live:STB")))
        self.assertIn("Bộ Xây dựng 38.58%T2·31/03, khối ngoại 0.90%T2·23/09 — free float thực ~11% (suy ra: 100 − "
                      "50.21 − 38.58)E·31/03; vendor ghi free float 12%.T2·23/09",
                      text_of(find_key(R["tuanmuot"], "grp-live:VGC")))
        # quét cùng lớp: số cộng/tỷ lệ tự tính mang E, không nằm dưới nhãn T1/T2
        for gid, s in (("sovico", "Nhóm Sovico tại VJC ≈ 47.05%E·30/06"), ("bauthuy", " — gộp 9.86%E·28/07"),
                       ("bauthuy", "(mua 21–23/07)T2·28/07 = 9.86%E·28/07, lớn hơn VNPost 6.537%.T2·28/07"),
                       ("bauthuy", "THD ×3.9 từ 07/05E·25/09"), ("eliminated", "; nhóm CII gom ~13%E·09/09"),
                       ("eliminated", "Nhóm CII nắm ~13% PC1E·09/09"), ("eliminated", ", tổng ~3,038 tỷ.E·25/09")):
            self.assertIn(s, text_of(R[gid]), s)

    def test_no_new_buy_sell_calls(self):
        p = self.ctx.sys_dir / "knowledge_os" / "chaebol_map" / "cap_nhat_2026-09-27.groups.json"
        if not p.is_file():
            self.skipTest("chưa có mảnh dossier groups")
        doc = json.loads(p.read_text(encoding="utf-8"))
        texts = []

        def grab(o):
            if isinstance(o, dict):
                if isinstance(o.get("text"), str):
                    texts.append(o["text"])
                    self.assertTrue(o.get("src"), o["text"][:60])
                    self.assertIn(o.get("tier"), ("FACT-T1", "FACT-T2", "SS-T3", "EST", "UNVERIFIED"))
                    self.assertRegex(o.get("asof") or "", r"^\d{4}-\d{2}-\d{2}$")
                for v in o.values():
                    grab(v)
            elif isinstance(o, list):
                for v in o:
                    grab(v)
        grab(doc)
        self.assertGreater(len(texts), 100)
        for t in texts:
            for bad in ("STRONG BUY", "AVOID", "KHÔNG MUA ĐUỔI", "nên mua", "nên bán", "khuyến nghị mua"):
                self.assertNotIn(bad, t)


class TestCli(unittest.TestCase):
    """Dựng qua CLI (tiến trình con, socket bị chặn) ở cả hai mode, chỉ 5 tab nhóm, thư mục ra tạm."""

    def _run(self, py, mode):
        with tempfile.TemporaryDirectory() as out:
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", CHB_TODAY="2026-09-27")
            cp = subprocess.run([str(py), "-c", GUARD, str(HERE / "chaebol_map.py"), "build", "--mode", mode, "--out",
                                 out, "--tabs", ",".join(GROUPS)], capture_output=True, text=True, env=env,
                                timeout=180)
            doc = json.loads(cp.stdout.strip().splitlines()[-1])
            self.assertNotIn("error", doc, cp.stderr[-2000:])
            m = doc["manifest"]
            st = {t["id"]: t["status"] for t in m["tabs"]}
            for gid in GROUPS:
                self.assertEqual(st[gid], "ok", gid)
            self.assertEqual(m["inventory"]["coverage"], {"missing": [], "mismatch": []})
            self.assertFalse([w for w in m["warnings"] if "builder lỗi" in w or "options" in w])
            return m

    @unittest.skipUnless(V21_FILE.is_file(), "không có v21_const.json")
    def test_cli_both_modes_current_python(self):
        m = self._run(sys.executable, "v21")
        self.assertEqual(m["stats"]["can_data"], 0)
        self._run(sys.executable, "live")

    @unittest.skipUnless(V21_FILE.is_file() and VENV_PY.is_file(), "không có venv-numpy2 hoặc v21_const")
    def test_cli_other_interpreter(self):
        other = VENV_PY if Path(sys.executable).resolve() != VENV_PY.resolve() else Path("/usr/bin/env")
        if other == Path("/usr/bin/env"):
            self.skipTest("đang chạy trên venv-numpy2 — test chéo chạy từ python3")
        self._run(other, "v21")


if __name__ == "__main__":
    unittest.main()
