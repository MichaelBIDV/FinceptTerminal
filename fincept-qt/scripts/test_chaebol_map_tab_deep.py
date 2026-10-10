#!/usr/bin/env python3
"""Unit tests tab ★ 12 · CATALYST CALENDAR / ★ 14 · DEEP-DIVE 24 CHAEBOL (chaebol_map_tab_deep + _live) — không mạng.

Chạy (cả hai trình thông dịch):
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest scripts/test_chaebol_map_tab_deep.py -v
    PYTHONDONTWRITEBYTECODE=1 ~/Library/Application\\ Support/com.fincept.terminal/venv-numpy2/bin/python \\
        -m unittest scripts/test_chaebol_map_tab_deep.py

Chuỗi vàng: chaebol_map_spec/page_p7a §3 (catalyst: thứ tự, nhãn DAYS so 12/05/2026) và page_p7b §3 (deep6: 24 nút,
bảng tổ hợp AXIS×TIER, sel không reset, tổ hợp rỗng → 24/24). v21 cần $B/data/chaebol_map/v21_const.json (vắng → skip);
live cần kho thật (chaebol_map_data + vc_lk) và mảnh dossier cap_nhat_2026-09-27.deep.json (vắng → skip).
"""
from __future__ import annotations

import json
import re
import socket
import sys
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import chaebol_map as M  # noqa: E402
import chaebol_map_dom as D  # noqa: E402
import chaebol_map_shell as S  # noqa: E402
import chaebol_map_tab_deep as DP  # noqa: E402

V21_PATH = M.bridge_dir() / "data" / "chaebol_map" / "v21_const.json"
DOSSIER = M.system_dir() / "knowledge_os" / "chaebol_map" / "cap_nhat_2026-09-27.deep.json"
_REAL = {}
_V21 = None


def setUpModule():
    def blocked(*a, **k):
        raise RuntimeError("mạng bị chặn trong test chaebol_map_tab_deep")
    for name in ("socket", "create_connection", "getaddrinfo"):
        _REAL[name] = getattr(socket, name)
        setattr(socket, name, blocked)


def tearDownModule():
    for name, fn in _REAL.items():
        setattr(socket, name, fn)


def v21():
    global _V21
    if _V21 is None:
        _V21 = json.loads(V21_PATH.read_text(encoding="utf-8")) if V21_PATH.is_file() else {}
    return _V21


def data_mod():
    try:
        import chaebol_map_data as DM
    except Exception:  # noqa: BLE001
        return None
    return DM if (DM.bridge() / "state" / "vc_lk" / "VIC" / "price-history.json").is_file() else None


def build(mode, tab, data=True):
    with D.use_mode(mode, "2026-09-27"):
        ctx = M.Ctx(mode, date(2026, 9, 27), list(S.TABS_V21))
        ctx.v21 = v21()
        ctx.tab = tab
        if mode == "live" and data:
            ctx.data = data_mod()
            ctx.dossier = M.load_dossier(ctx) if ctx.data is not None else None
        fn = DP.build_catalyst if tab == "catalyst" else DP.build_deep6
        return fn(ctx), ctx


def walk(node, parents=()):
    yield node, parents
    if isinstance(node, dict):
        for ch in node.get("k", ()):
            yield from walk(ch, parents + (node,))


def text_of(node):
    return node if isinstance(node, str) else "".join(text_of(c) for c in node.get("k", ()))


def find_key(node, key):
    return next((n for n, _ in walk(node) if isinstance(n, dict) and n.get("key") == key), None)


def keys_with(node, prefix):
    return [n for n, _ in walk(node) if isinstance(n, dict) and str(n.get("key", "")).startswith(prefix)]


def cond_ok(cond, state):
    """Ngữ nghĩa `if` (DESIGN §4): mọi điều kiện đúng; khoá ghép 'a|b' = giá trị nối '|'; giá trị list = một trong."""
    for k, want in (cond or {}).items():
        got = "|".join(state.get(p, "") for p in k.split("|"))
        if got not in (want if isinstance(want, list) else [want]):
            return False
    return True


def marked(n):
    return isinstance(n, dict) and bool(n.get("_tier") or n.get("_can") or n.get("_v21"))


def pills(node):
    """Chữ các Pill trạng thái (chaebol_map_shell.Pill: span inline-block, padding 3px 8px) theo thứ tự."""
    return [text_of(x) for x, _ in walk(node) if isinstance(x, dict) and x.get("t") == "span" and
            (x.get("s") or {}).get("display") == "inline-block" and (x.get("s") or {}).get("padding") == "3px 8px"]


def tags(node):
    return [text_of(x) for x, _ in walk(node) if isinstance(x, dict) and x.get("_tier")]


class V21Catalyst(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not v21():
            raise unittest.SkipTest("thiếu v21_const.json")
        cls.res, cls.ctx = build("v21", "catalyst")

    def test_structure_and_order(self):
        root = self.res["root"]
        self.assertEqual(self.res["states"], [])
        self.assertIn(DP.CAT_TITLE, text_of(root))
        head = find_key(root, "cat.head")
        self.assertEqual([text_of(c) for c in head["k"]], ["DATE", "EVENT", "IMP", "MAGNITUDE", "CHAEBOL", "DAYS"])
        cards = keys_with(root, "cat.card.")
        self.assertEqual(len(cards), 16)
        days = [text_of(c["k"][0]["k"][5]) for c in cards]           # p7a §3.3
        self.assertEqual(days, ["95d ago", "95d ago", "69d ago", "67d ago", "6d ago", "1d", "3d", "44d", "49d", "79d",
                                "110d", "141d", "233d", "234d", "322d", "414d"])
        first = text_of(cards[0])
        self.assertTrue(first.startswith("2026-02-06GEL niêm yết HOSEClaims: C17·C37⬆️Mid"), first)

    def test_colors_as_intended(self):
        cards = keys_with(self.res["root"], "cat.card.")
        acc = [c["s"]["borderLeft"] for c in cards]
        self.assertEqual(acc[5], "3px solid #c5392f")                   # CRITICAL (VPL) — crimson as_intended
        self.assertEqual(acc[2], "3px solid #3d7a4e")                   # High (ACV) — emerald
        self.assertEqual(acc[6], "3px solid #caa75c")                   # Very High
        self.assertEqual(acc[0], "3px solid #5b8db8")                   # Mid
        dcol = [c["k"][0]["k"][5]["s"]["color"] for c in cards]
        self.assertEqual(dcol[:5], ["#5b8db8"] * 5)
        self.assertEqual(dcol[5:7], ["#c5392f"] * 2)                     # ≤14 ngày
        self.assertEqual(dcol[7:9], ["#caa75c"] * 2)                     # 15–60
        self.assertEqual(set(dcol[9:]), {"#3d7a4e"})                     # >60

    def test_emoji_exact(self):
        self.assertEqual([DP.imp_symbol(x) for x in ("+", "-", "--", "?")],
                         ["⬆️", "⬇️", "⬇️⬇️", "❓"])

    def test_no_live_marks(self):
        self.assertFalse(any(marked(n) or (isinstance(n, dict) and n.get("_upd")) for n, _ in walk(self.res["root"])))


class V21Deep6(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not v21():
            raise unittest.SkipTest("thiếu v21_const.json")
        cls.res, cls.ctx = build("v21", "deep6")
        cls.d24 = v21()["DEEP_INSIGHT_24"]
        cls.names = list(cls.d24)

    def test_states(self):
        st = {s["key"]: s for s in self.res["states"]}
        self.assertEqual(st["d24.sel"]["default"], "Vingroup")
        self.assertEqual(st["d24.sel"]["options"], self.names)
        self.assertEqual(len(self.names), 24)
        self.assertEqual(st["d24.axis"]["options"], ["ALL", "NQ79", "NQ68", "SPECIAL"])
        self.assertEqual(st["d24.tier"]["options"], ["ALL", "Top", "Mid", "Distress", "Special"])
        cov = M._coverage([dict(s, tab="deep6") for s in self.res["states"]], {"deep6"}, v21())
        self.assertEqual(cov, {"missing": [], "mismatch": []})

    def test_filter_row_and_counter(self):
        f = find_key(self.res["root"], "d24.filters")
        labels = [text_of(c) for c in f["k"]]
        self.assertEqual(labels[:6], ["AXIS:", "ALL", "NQ79", "NQ68", "SPECIAL", "TIER:"])
        self.assertEqual(f["k"][-1]["count"], {"grp": "d24.names", "fmt": "{n}/24 chaebol"})
        btns = [c for c in f["k"] if c.get("t") == "button"]
        self.assertEqual([b["on"]["set"] for b in btns[:4]], [{"d24.axis": a} for a in ("ALL", "NQ79", "NQ68", "SPECIAL")])
        self.assertEqual(btns[1]["var"][0]["s"], {"background": "#c5392f", "color": "#0a0a0c"})

    def _visible(self, state):
        root = self.res["root"]
        btns = [n for n in keys_with(root, "d24.btn.") if cond_ok(n.get("if"), state)]
        lit = [n["key"][8:] for n in btns if cond_ok(n["var"][0]["if"], state)]
        panels = [n["key"][10:] for n in keys_with(root, "d24.panel.") if cond_ok(n.get("if"), state)]
        return [b["key"][8:] for b in btns], lit, panels

    def test_filter_semantics_p7b(self):
        s = lambda sel, a, t: {"d24.sel": sel, "d24.axis": a, "d24.tier": t}
        names, lit, panels = self._visible(s("Vingroup", "ALL", "ALL"))
        self.assertEqual((len(names), lit, panels), (24, ["Vingroup"], ["Vingroup"]))
        names, lit, panels = self._visible(s("Vingroup", "NQ79", "ALL"))      # sel rơi → names[0], không nút sáng
        self.assertEqual((len(names), lit, panels), (11, [], ["Vietcombank"]))
        names, lit, panels = self._visible(s("Vingroup", "NQ79", "Distress"))  # tổ hợp rỗng → đủ 24
        self.assertEqual((len(names), lit, panels), (24, ["Vingroup"], ["Vingroup"]))
        counts = {(a, t): len(self._visible(s("Vingroup", a, t))[0])
                  for a in ("ALL", "NQ79", "NQ68", "SPECIAL") for t in ("ALL", "Top", "Mid", "Distress", "Special")}
        self.assertEqual(counts[("ALL", "Top")], 11)
        self.assertEqual(counts[("NQ68", "Distress")], 3)
        self.assertEqual(sum(1 for v in counts.values() if v == 24), 7)   # ALL×ALL + 6 tổ hợp rỗng (p7b §3.4)

    def test_every_state_one_panel(self):
        for sel in self.names:
            for a in ("ALL", "NQ79", "NQ68", "SPECIAL"):
                for t in ("ALL", "Top", "Mid", "Distress", "Special"):
                    _, _, panels = self._visible({"d24.sel": sel, "d24.axis": a, "d24.tier": t})
                    self.assertEqual(panels, [DP.shown_for(self.d24, self.names, sel, a, t)])

    def test_panel_golden(self):
        vg = text_of(find_key(self.res["root"], "d24.panel.Vingroup"))
        for s in ("👑 LEADER", "Phạm Nhật Vượng ($32.8B family)", "NQ68", "TOP", "TICKERS: VIC · VHM · VRE · VPL · VEF · VFS",
                  "Claims: C19 · C20 · C21 · C22 · C23 · C05 · C34", "📈 WYCKOFF PHASE", "P3 distribution 6/6",
                  "Distribution score: 6/6", "💰 CASH FLOW", "LNST 2025: -3,000 tỷ deficit 2025",
                  '🔄 MUNGER INVERSION · "Nếu THẤT BẠI?"', "🔗 HIDDEN INTERLOCKS", "⚠ KEY RISK", "🎯 ACTION",
                  "AVOID VIC. HOLD VHM nhẹ 5%. AVOID VPL chờ freefloat fix."):
            self.assertIn(s, vg)
        self.assertIn("Claims: None tracked", text_of(find_key(self.res["root"], "d24.panel.Agribank")))
        bars = [n for n, _ in walk(find_key(self.res["root"], "d24.panel.Agribank"))
                if isinstance(n, dict) and (n.get("s") or {}).get("width") == 30]
        self.assertEqual([b["s"]["background"] for b in bars], ["#1f1d24"] * 6)   # score 0 → 6 ô rỗng

    def test_seven_cards(self):
        p = find_key(self.res["root"], "d24.panel.FPT")
        for k in ("d24.leader", "d24.wyckoff", "d24.cash", "d24.munger", "d24.interlocks", "d24.risk", "d24.action"):
            self.assertIsNotNone(find_key(p, k), k)

    def test_run_tab_ok(self):
        with D.use_mode("v21", "2026-09-27"):
            ctx = M.Ctx("v21", date(2026, 9, 27), list(S.TABS_V21))
            ctx.v21 = v21()
            for tab in ("catalyst", "deep6"):
                _, status = M.run_tab(tab, tab, ctx)
                self.assertEqual(status, "ok")
            self.assertEqual([w for w in ctx.warnings if "[catalyst]" in w or "[deep6]" in w], [])


class Live(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not v21() or data_mod() is None:
            raise unittest.SkipTest("thiếu v21_const.json hoặc kho sống")
        if not DOSSIER.is_file():
            raise unittest.SkipTest("thiếu mảnh dossier deep")
        cls.cat, cls.cctx = build("live", "catalyst")
        cls.deep, cls.dctx = build("live", "deep6")

    def test_bare_numbers(self):
        """Mỗi text có số liệu (NUM của lớp live) phải có nhãn bậc / [CẦN DATA] / V21·12/05 trong khối gần nhất."""
        import chaebol_map_tab_deep_live as L
        blocks = {"div", "li", "h2", "td", "section", "ul"}
        bad = []
        for root in (self.cat["root"], self.deep["root"]):
            for n, parents in walk(root):
                if not isinstance(n, str) or not L.NUM.search(n):
                    continue
                if parents and marked(parents[-1]):
                    continue                                          # chính là nhãn
                blk = next((p for p in reversed(parents) if p.get("t") in blocks), None)
                if blk is None or not any(marked(x) for x, _ in walk(blk)):
                    bad.append(n)
        self.assertEqual(bad, [])

    def test_catalyst_live(self):
        doc = json.loads(DOSSIER.read_text(encoding="utf-8"))
        cards = keys_with(self.cat["root"], "cat.card.")
        self.assertEqual(len(cards), 16 + len(doc["catalyst"]))
        self.assertIn("hôm nay 27/09/2026", text_of(self.cat["root"]))
        rows = {text_of(c["k"][0]["k"][1]["k"][0]): text_of(c["k"][0]["k"][5]) for c in cards}
        self.assertEqual(rows["Sovico thoái HDB < 15% + Bầu Thụy LPBS IPOU·12/05"], "3d")
        self.assertEqual(len(self.cat["csv"]), len(cards))
        for c in cards:
            ev = c["k"][0]["k"][1]
            self.assertGreaterEqual(len(ev["k"]), 2)
            self.assertTrue(any(marked(x) for x, _ in walk(ev)), text_of(ev))

    def test_stance_kept(self):
        root = self.deep["root"]
        for n in keys_with(root, "d24.panel."):
            act = find_key(n, "d24.action")
            self.assertTrue(any(x.get("_v21") for x, _ in walk(act) if isinstance(x, dict)))
            self.assertIn("action cần kiểm chứng", text_of(act))
            self.assertIn(self.d24(n["key"][10:])["action"], text_of(act))

    def d24(self, name):
        return v21()["DEEP_INSIGHT_24"][name]

    def test_leader_bidv_t1(self):
        lead = find_key(find_key(self.deep["root"], "d24.panel.BIDV"), "d24.leader")
        self.assertIn("Lê Ngọc Lâm", text_of(lead))
        self.assertIn("FACT-T1", [x.get("_tier") for x, _ in walk(lead) if isinstance(x, dict)])
        self.assertIn("V21: Phan Đức Tú (Chairman)", text_of(lead))

    def test_munger_vinspeed_u_capped(self):
        """Dữ kiện UNVERIFIED (báo chí) → tối đa CHƯA RÕ; vế T1 (NQ VHM 29/06) mang nhãn riêng."""
        mg = find_key(find_key(self.deep["root"], "d24.panel.Vingroup"), "d24.munger")
        item = [c for c in mg["k"] if "VinSpeed KHÔNG ký nhà thầu" in text_of(c)][0]
        self.assertEqual(pills(item), ["CHƯA RÕ"])
        self.assertIn("25/12/2025", text_of(item))
        self.assertEqual([x.get("_tier") for x, _ in walk(item) if isinstance(x, dict) and x.get("_tier")],
                         ["UNVERIFIED", "FACT-T1"])

    def test_dossier_u_status_capped(self):
        """Luật đã chốt: dữ kiện U tối đa CHƯA RÕ — không mục/vế UNVERIFIED nào mang ĐẠT/BỊ BÁC/LIVE/HẾT HẠN/TIỀN ĐỀ SAI."""
        doc = json.loads(DOSSIER.read_text(encoding="utf-8"))
        entries = list(doc["catalyst"]) + list(doc["catalyst_status"].values())
        for ent in doc["entities24"].values():
            for part in ent.values():
                entries += part if isinstance(part, list) else list(part.values()) if "text" not in part else [part]
        entries += [x for e in entries for x in e.get("extra") or []]
        bad = [(e.get("text") or e.get("e"), e.get("status")) for e in entries
               if e.get("tier") == "UNVERIFIED" and e.get("status") not in (None, "CHƯA RÕ")]
        self.assertEqual(bad, [])

    def _card(self, e):
        return next(c for c in keys_with(self.cat["root"], "cat.card.")
                    if text_of(c["k"][0]["k"][1]["k"][0]).startswith(e))

    def test_catalyst_pills_per_clause(self):
        """Pill theo đúng nguyên văn điều kiện + horizon, mỗi vế một pill (phát hiện kiểm chứng 27/09)."""
        want = {"TCB BCTC Q2 — dự phòng VinFast": ["CHƯA RÕ"],
                "VPL 1-năm-niêm-yết freefloat deadline": ["TIỀN ĐỀ SAI"],
                "Sovico thoái HDB < 15% + Bầu Thụy LPBS IPO": ["TIỀN ĐỀ SAI", "CHƯA RÕ"],
                "VPBankS lock-up hết + ACV Long Thành": ["BỊ BÁC", "CHƯA RÕ"],     # <80% chạm 02–12/06, trong hạn
                "VN30 review T7 — DGC có thể rời": ["TIỀN ĐỀ SAI"],              # QĐ loại 07/05, trước ngày dựng
                "MCH lock-up insider hết": ["HẾT HẠN"],
                "GEL T+30 floor test": ["ĐẠT"]}
        for e, want_pills in want.items():
            self.assertEqual(pills(self._card(e)["k"][0]["k"][1]["k"][2]), want_pills, e)
        gel = text_of(self._card("GEL T+30 floor test"))
        self.assertNotIn("30 phiên đầu", gel)
        self.assertIn("16 phiên", gel)
        self.assertIn("67.9% IPO quy đổi", text_of(self._card("HPA T+90 giá test")))
        self.assertIn("thô 47,900", text_of(self._card("DGC vào diện kiểm soát")))
        mch = text_of(self._card("MCH lock-up insider hết"))
        self.assertIn("126,131", mch)
        self.assertIn("+11.8%", mch)
        ftse = self._card("FTSE đợt 2")
        self.assertEqual(text_of(ftse["k"][0]["k"][0]), "2027-03-22")
        self.assertEqual(tags(ftse)[-1], "E·27/09")                     # ngày ước, không phải T1
        self.assertIn("mốc cập nhật 9T", text_of(self._card("Mùa BCTC Q3/2026")))
        vpl = self._card("VPL 1-năm-niêm-yết")
        self.assertTrue(any(x.get("_can") for x, _ in walk(vpl) if isinstance(x, dict)))   # vế lock-up [CẦN DATA]
        self.assertIn("T2·21/09", tags(vpl))                             # free float vendor mang ngày của nó

    def test_claims_line_set_aware(self):
        """Mã claim DEEP_INSIGHT_24 trộn hai bộ: chỉ nhận claim đúng thực thể (CLAIMS_54.ch hoặc C01–C20.tk)."""
        def line(name):
            lead = find_key(find_key(self.deep["root"], "d24.panel." + name), "d24.leader")
            return next(text_of(n) for n, _ in walk(lead) if isinstance(n, dict) and text_of(n).startswith("Chấm lại"))
        doc = self.dctx.dossier or {}                                   # mảnh claims do nhóm khác giữ → đọc sống
        s20 = lambda c: (doc.get("claims20") or {}).get(c, {}).get("status") or "—"   # noqa: E731
        s54 = lambda c: (doc.get("claims54") or {}).get(c, {}).get("status") or "—"   # noqa: E731
        for name, want in (("GELEX", ["C08·20 " + s20("C08")]),
                           ("PetroVietnam", ["C04·20 " + s20("C04"), "C05·20 " + s20("C05")]),
                           ("Novaland", ["C04 " + s54("C04"), "C07·20 " + s20("C07")]),
                           ("VPBank", ["C11·20 " + s20("C11"), "C14 " + s54("C14")]),
                           ("Vietcombank", ["C11 " + s54("C11")])):            # Big4 Banking ⊃ VCB
            got = line(name)
            for w in want:
                self.assertIn(w, got, name)
        self.assertNotRegex(line("GELEX"), r"C08 (?!·)")                    # không mượn C08 (VPB holding) của bộ 54

    def test_td_window_date_and_cover(self):
        """TD: nhãn ngày = ngày cuối có bản ghi tự doanh; phủ < 80% → [CẦN DATA] (DESIGN §9)."""
        acv = text_of(find_key(find_key(self.deep["root"], "d24.panel.ACVHVN"), "d24.wyckoff"))
        self.assertIn("tự doanh thưa 4/60 phiên", acv)
        vic = text_of(find_key(find_key(self.deep["root"], "d24.panel.Vingroup"), "d24.wyckoff"))
        self.assertRegex(vic, r"TD \(khớp\) [-+]\d+\.\dT2·24/09 \(59/60 phiên\)")

    def test_signal_flow_t2(self):
        """Số FiinTrade của V21 (FLOW ≤08/05) → T2·FLOW.date như tab 08; số không khớp FLOW giữ U·12/05."""
        wy = find_key(find_key(self.deep["root"], "d24.panel.FPT"), "d24.wyckoff")
        li = {text_of(n["k"][0]): n for n, _ in walk(wy) if isinstance(n, dict) and n.get("t") == "li" and n.get("k")}
        self.assertEqual(tags(li["FPT NN -173.7M 60d cực mạnh"]), ["T2·07/05"])
        self.assertEqual(tags(li["FOL chạm trần 32.75%"]), ["U·12/05"])

    def test_cross_holdings_per_number(self):
        """Mỗi tỷ lệ mang ngày của chính nó; số trước đợt riêng lẻ ghi rõ; khoản lớn nhất trước; tên tắt SCIC/PVN."""
        card = lambda n, k: text_of(find_key(find_key(self.deep["root"], "d24.panel." + n), k))  # noqa: E731
        vg = card("Vingroup", "d24.interlocks")
        self.assertIn("VPL 85.51% (31/12/2025, trước phát hành riêng lẻ 23/06/2026)", vg)
        self.assertIn("VHM 71.70%T2·06/08", vg)
        self.assertIn("Chủ sở hữu chung ≥1%: PVN: GAS 95.76%", card("PetroVietnam", "d24.interlocks"))
        fpt = card("FPT", "d24.interlocks")
        self.assertIn("Chủ sở hữu chung ≥1%: SCIC: FPT 5.67%", fpt)
        self.assertNotIn("…:", fpt)
        self.assertIn("PLC 18,700 (vnstore, không có vc_lk)", card("Petrolimex", "d24.leader"))

    def test_flow_only_nn_td(self):
        wy = text_of(find_key(find_key(self.deep["root"], "d24.panel.MasanTCB"), "d24.wyckoff"))
        self.assertRegex(wy, r"NN [-+]\d+\.\d triệu cp")
        self.assertIn("CN/TC [CẦN DATA]", wy)

    def test_flow_signed_zero(self):
        """Số làm tròn bằng 0 in '0.0' không dấu (final_check §6.1 #2: VGI 'NN -0.0', KSV '+0.0') — cả NN lẫn TD."""
        import chaebol_map_tab_deep_live as L
        from types import SimpleNamespace as V

        class Stub:
            def flow4(self, tk, n):
                return {"nn": V(value=-0.001013, tier="FACT-T2", asof="2026-09-25"),
                        "td": V(value=-0.0336, tier="FACT-T2", asof="2026-09-24"),
                        "from": "2026-07-01", "to": "2026-09-25", "n": 60}

            def prop_net(self, tk, n, kind="total"):
                return {"n_co": 60}

            def _prop_map(self, tk, kind):
                return {"2026-09-24": 1}

        with D.use_mode("live", "2026-09-27"):
            li = text_of(L._flow_li(Stub(), ["VGI"]))
        self.assertIn("(VGI): NN 0.0 triệu cp", li)
        self.assertIn("TD (khớp) 0.0T2·24/09", li)
        signed0 = re.compile(r"(?<![\d.,])[-+−]0\.0(?![\d])")
        for root in (self.cat["root"], self.deep["root"]):
            self.assertEqual([n for n, _ in walk(root) if isinstance(n, str) and signed0.search(n)], [])
        vt = text_of(find_key(find_key(self.deep["root"], "d24.panel.Viettel"), "d24.wyckoff"))
        self.assertRegex(vt, r"\(VGI\): NN \d+\.\d triệu cp")

    def test_tasco_cash_bctc_t1(self):
        """Tasco: số BCTC (T1) thay số báo chí '>324 tỷ' U (final_check §6.1 #8); chữ V21 '2025 declining' chấm theo
        BCTC kiểm toán 2025 (lập trước ngày dựng); Munger 'HUT lỗ Q2/26?' chấm theo BCTC quý 2 (T1)."""
        p = find_key(self.deep["root"], "d24.panel.TascoSVC")
        cash = find_key(p, "d24.cash")
        txt = text_of(cash)
        self.assertIn("LNST hợp nhất 310.47 tỷ (cùng kỳ 114.18 tỷ); cổ đông công ty mẹ 91.06 tỷ", txt)
        self.assertNotIn("LNST >324", txt)
        self.assertEqual(tags(cash), ["U·12/05", "T1·29/08", "T1·30/07", "T1·30/03"])   # U·12/05 = chữ V21 có số
        self.assertEqual(pills(cash), ["BỊ BÁC"])                       # chỉ vế 2025, không chấm 6T/2026
        self.assertIn("630.26 tỷ (2024: 304.75 tỷ)", txt)
        mg = find_key(p, "d24.munger")
        item = [c for c in mg["k"] if "HUT lỗ Q2/26?" in text_of(c)][0]
        self.assertEqual(pills(item), ["BỊ BÁC"])
        self.assertEqual(tags(item), ["T1·30/07", "E·29/08"])
        self.assertIn("270.58 tỷ", text_of(item))

    def test_fpt_scic_invert_matches_c15(self):
        """Munger FPT 'SCIC bán FPT < 90k?' = nhánh fail 'giá < 90k' của C15 (cùng sự kiện, cùng hạn 31/12/2026) →
        trạng thái phải khớp C15 khi chưa tới hạn (final_check §6.1 #9). C15 đổi trạng thái → phải chấm lại mục này."""
        c15 = ((self.dctx.dossier or {}).get("claims54") or {}).get("C15", {}).get("status")
        if c15 is None:
            self.skipTest("thiếu mảnh claims (C15)")
        self.assertEqual(c15, "LIVE", "C15 đã đổi trạng thái — chấm lại Munger FPT #1 (dossier deep)")
        mg = find_key(find_key(self.deep["root"], "d24.panel.FPT"), "d24.munger")
        item = [c for c in mg["k"] if "SCIC bán FPT < 90k?" in text_of(c)][0]
        self.assertEqual(pills(item), ["LIVE"])
        self.assertIn("C15", text_of(item))
        self.assertEqual(tags(item), ["T2·30/06", "E·25/09", "U·13/08"])

    def test_legal_caveat(self):
        lead = text_of(find_key(find_key(self.deep["root"], "d24.panel.ACVHVN"), "d24.leader"))
        self.assertIn("pháp lý: nguyên văn V21", lead)

    def test_no_data_module(self):
        res, ctx = build("live", "deep6", data=False)
        self.assertTrue(any(isinstance(n, dict) and n.get("_can") for n, _ in walk(res["root"])))
        res, ctx = build("live", "catalyst", data=False)
        self.assertEqual(len(keys_with(res["root"], "cat.card.")), 16)

    def test_dossier_fragment(self):
        doc = json.loads(DOSSIER.read_text(encoding="utf-8"))
        self.assertEqual(set(doc), {"schema", "as_of", "catalyst", "catalyst_status", "entities24", "deep_meta"})
        entries = list(doc["catalyst"]) + list(doc["catalyst_status"].values())
        for ent in doc["entities24"].values():
            for part in ent.values():
                entries += part if isinstance(part, list) else \
                    list(part.values()) if "text" not in part else [part]
        for e in entries + [x for e in entries for x in e.get("extra") or []]:
            for k in ("tier", "asof", "src"):
                self.assertTrue(e.get(k), (k, e.get("text") or e.get("e")))
            self.assertIsNone(re.search(r"\b(BUY|SELL|ADD|AVOID)\b", e.get("text") or e.get("e") or ""))
        self.assertEqual(set(doc["entities24"]) - set(v21()["DEEP_INSIGHT_24"]), set())


if __name__ == "__main__":
    unittest.main()
