#!/usr/bin/env python3
"""Unit tests cho tab `10 · DATA & METRIC AUDIT` (chaebol_map_tab_audit + _live) và móc dossier.header của shell.

Chạy (cả hai trình thông dịch, không mạng — socket bị chặn trong tiến trình):
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest scripts/test_chaebol_map_tab_audit.py -v
    PYTHONDONTWRITEBYTECODE=1 ~/Library/Application\\ Support/com.fincept.terminal/venv-numpy2/bin/python \\
        -m unittest scripts/test_chaebol_map_tab_audit.py
Chuỗi vàng lấy từ chaebol_map_spec/page_p8_audit.md (Phụ lục B) và SRC 7483–7803. Test v21 cần v21_const.json; test
live cần kho thật (_System) — vắng thì bỏ qua (skip), không bịa fixture số thị trường.
"""
from __future__ import annotations

import json
import re
import socket
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import chaebol_map as M  # noqa: E402
import chaebol_map_dom as D  # noqa: E402
import chaebol_map_shell as S  # noqa: E402
import chaebol_map_tab_audit as A  # noqa: E402
import chaebol_map_tab_audit_live as AL  # noqa: E402

V21_PATH = M.bridge_dir() / "data" / "chaebol_map" / "v21_const.json"
TODAY = date(2026, 9, 27)
PIPE_IDS = ["P0_DAILY_PRICE", "P0_FLOW_PILLAR_IV", "P0_PERF_60D", "P1_AGM_EVENTS", "P1_INSIDER_TXN",
            "P1_FOREIGN_ROOM", "P1_VWAP_CLUSTER", "P2_LEGAL_NEWS", "P2_BCTC_QUARTERLY", "P2_OWNERSHIP_CIQ_CHROME",
            "P3_MACRO_BACKDROP"]
_REAL = {}


def setUpModule():
    def blocked(*a, **k):
        raise RuntimeError("mạng bị chặn trong test chaebol_map_tab_audit")
    for name in ("socket", "create_connection", "getaddrinfo"):
        _REAL[name] = getattr(socket, name)
        setattr(socket, name, blocked)


def tearDownModule():
    for name, fn in _REAL.items():
        setattr(socket, name, fn)


def walk(n):
    yield n
    if isinstance(n, dict):
        for c in n.get("k", ()):
            yield from walk(c)


def text_of(n):
    return n if isinstance(n, str) else "".join(text_of(c) for c in n.get("k", ()))


def by_key(root, key):
    return next((n for n in walk(root) if isinstance(n, dict) and n.get("key") == key), None)


def keys_like(root, prefix):
    return [n for n in walk(root) if isinstance(n, dict) and str(n.get("key", "")).startswith(prefix)]


def is_mark(n):
    """Nút nhãn bậc / [CẦN DATA] / V21·12/05 do chaebol_map_dom phát."""
    return isinstance(n, dict) and (n.get("_tier") or n.get("_can") or n.get("_v21"))


def load_v21():
    if not V21_PATH.is_file():
        raise unittest.SkipTest("thiếu v21_const.json (%s)" % V21_PATH)
    return json.loads(V21_PATH.read_text("utf-8"))


def v21_ctx():
    ctx = M.Ctx("v21", TODAY, list(S.TABS_V21))
    ctx.v21 = load_v21()
    ctx.tab = "audit"
    return ctx


def build_v21():
    with D.use_mode("v21", TODAY):
        return A.build_audit(v21_ctx())


# ── Mode v21: cấu trúc, state, chuỗi vàng, lỗi React ────────────────────────


class TestV21(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = build_v21()
        cls.root = cls.res["root"]

    def test_state_and_options(self):
        st = self.res["states"]
        self.assertEqual(len(st), 1)
        self.assertEqual(st[0]["key"], "aud.pipe")
        self.assertEqual(st[0]["default"], "P0_DAILY_PRICE")
        self.assertEqual(st[0]["options"], PIPE_IDS)
        want = M.expected_options(load_v21())["aud.pipe"]
        self.assertEqual(sorted(st[0]["options"]), sorted(want))
        cov = M._coverage([{**st[0], "tab": "audit"}], {"audit"}, load_v21())
        self.assertEqual(cov, {"missing": [], "mismatch": []})
        self.assertNotIn("csv", self.res, "mode v21 không xuất csv")

    def test_sections_in_order(self):
        titles = [text_of(n["k"][0]["k"][1]) for n in walk(self.root)
                  if isinstance(n, dict) and n.get("t") == "section"]
        self.assertEqual(titles, [A.A_TITLE, A.B_TITLE, A.C_TITLE, A.D_TITLE, A.E_TITLE, A.F_TITLE])
        g = by_key(self.root, "aud:G")
        self.assertEqual(text_of(g["k"][0]), "★ HƯỚNG DẪN SỬ DỤNG VỚI CLAUDE CODE")
        self.assertEqual(g["s"]["background"], "#caa75c10")
        self.assertEqual(g["s"]["border"], "1px solid #caa75c40")
        sub = by_key(self.root, "aud:A")["k"][0]["k"][2]
        self.assertEqual(text_of(sub), "Spec sheet cho Claude Code · 11 pipelines · 45 tickers · 8 validation rules")

    def test_callout_golden(self):
        call = by_key(self.root, "aud:A")["k"][1]["k"][0]
        self.assertEqual(text_of(call), (
            "Tab này được thiết kế để Claude Code đọc và tự động hoá pipeline cập nhật V21 qua browser_batch tool. "
            "Mỗi pipeline có URL template, selector hint, parse logic, target field, validation rule. Khi anh chat "
            "với Claude Code, chỉ cần share file JSX này + nói \"Đọc DATA_AUDIT_PIPELINES, chạy P0 batch, cập nhật "
            "FLOW object trong file\" — phần còn lại auto."))
        self.assertEqual([c["t"] if isinstance(c, dict) else "t" for c in call["k"]], ["t", "strong", "t", "em", "t"])
        self.assertEqual(call["s"]["fontStyle"], "italic")

    def test_stat_cards(self):
        grid = by_key(self.root, "aud:A")["k"][1]["k"][1]
        self.assertEqual(grid["s"]["gridTemplateColumns"], "repeat(5, 1fr)")
        vals = [text_of(c["k"][1]) for c in grid["k"]]
        labels = [text_of(c["k"][0]) for c in grid["k"]]
        self.assertEqual(vals, ["3", "5", "3", "45", "8"])          # P2_OWNERSHIP_CIQ_CHROME đếm vào P1 (priority)
        self.assertEqual(labels, ["P0 PIPELINES", "P1 PIPELINES", "P2-P3", "TICKERS", "VALIDATION"])
        self.assertEqual([c["s"]["borderLeft"] for c in grid["k"]],
                         ["3px solid #c5392f", "3px solid #d4a039", "3px solid #caa75c", "3px solid #3d7a4e",
                          "3px solid #5b8db8"])

    def test_buttons_and_react_border_bug(self):
        btns = [n for n in walk(self.root) if isinstance(n, dict) and n.get("t") == "button"]
        self.assertEqual([b["key"] for b in btns], ["aud.pipe:" + p for p in PIPE_IDS])
        self.assertEqual(btns[0]["on"], {"set": {"aud.pipe": "P0_DAILY_PRICE"}})
        self.assertEqual(btns[3]["on"], {"set": {"aud.pipe": "P1_AGM_EVENTS", "aud.bl.P1_AGM_EVENTS": "1",
                                                 "aud.bl.P0_DAILY_PRICE": "1"}})
        b = btns[9]                                               # CIQ: priority P1 → ochre
        self.assertEqual(list(b["s"])[:8], ["fontSize", "fontWeight", "textAlign", "padding", "background", "border",
                                            "borderLeft", "borderRadius"])   # lõi thêm inherit (as_intended)
        self.assertEqual(b["s"]["borderLeft"], "3px solid #d4a039")
        self.assertEqual(b["var"][0]["s"], {"background": "#1a1a24", "border": "1px solid #d4a039",
                                            "borderLeft": "3px solid #d4a039"})
        self.assertEqual(b["var"][1], {"if": {"aud.bl.P2_OWNERSHIP_CIQ_CHROME": "1"},
                                       "s": {"borderLeft": "1px solid #26242c"}})
        self.assertEqual(b["var"][2]["if"], {"aud.bl.P2_OWNERSHIP_CIQ_CHROME|aud.pipe": "1|P2_OWNERSHIP_CIQ_CHROME"})
        self.assertEqual(text_of(b), "P2_OWNERSHIP_CIQ_CHROMEHigh (upgraded from P2)★ Capital IQ Ownership — 5 "
                         "endpoints via Claude-in-Chrome (on-demand, upgrade from quarterly-blocked)↻ On-demand per "
                         "ticker (no longer quarterly-only)")
        self.assertEqual(b["k"][2]["k"], ["↻ ", "On-demand per ticker (no longer quarterly-only)"],
                         "'↻ {p.freq}' = hai nút chữ như React")
        self.assertEqual(self.root["scope"], ["aud.bl." + p for p in PIPE_IDS])

    def test_detail_cards(self):
        cards = keys_like(self.root, "aud.detail:")
        self.assertEqual([c["if"] for c in cards], [{"aud.pipe": p} for p in PIPE_IDS])
        head = cards[0]["k"][0]["k"][0]["k"][0]
        self.assertEqual(head["k"], ["P0_DAILY_PRICE", " · ", "P0 · Critical"])
        self.assertIn("NOTES · Chạy 1 lần cuối ngày · Output: { TICKER: {px, date, vol_match} }", text_of(cards[0]))
        self.assertIn("TICKERS45 mã", text_of(cards[0]))
        self.assertIn("SIG LOGICBULL nếu (to60>20 OR nn60>20) AND ca60<0", text_of(cards[2]))

    def test_flow_pillar_six_empty_cells(self):
        grid = keys_like(self.root, "aud.detail:P0_FLOW_PILLAR_IV")[0]["k"][1]
        cells = grid["k"]
        pairs = {text_of(cells[i]): cells[i + 1] for i in range(0, len(cells), 2)}
        empty = sorted(k for k, v in pairs.items() if not v.get("k"))
        self.assertEqual(empty, ["METHOD", "PARSE LOGIC", "SELECTOR HINT", "SOURCE", "URL TEMPLATE", "VALIDATION"])
        self.assertNotIn("FALLBACK URL", pairs)
        perf = keys_like(self.root, "aud.detail:P0_PERF_60D")[0]["k"][1]["k"]
        self.assertEqual({text_of(perf[i]) for i in range(0, len(perf), 2) if not perf[i + 1].get("k")},
                         {"SELECTOR HINT"})

    def test_ciq_license_email_removed(self):
        blob = json.dumps(self.root, ensure_ascii=False)
        self.assertNotIn("@bidv", blob)
        self.assertNotIn("tuanpm3", blob)
        ciq = keys_like(self.root, "aud.detail:P2_OWNERSHIP_CIQ_CHROME")[0]
        self.assertIn("SOURCEcapitaliq.spglobal.com (Okta SSO session managed by user)URL", text_of(ciq))
        self.assertEqual(A.clean_source_label("x (a, license a.b@c.com.vn)"), "x (a)")

    def test_playbook_pre_golden(self):
        pres = [n for n in walk(by_key(self.root, "aud:C")) if isinstance(n, dict) and n.get("t") == "pre"]
        self.assertEqual([text_of(p) for p in pres], [A.C_DAILY_PRE, A.C_EVENT_PRE, A.C_MASTER_PRE])
        self.assertIn("  old: `{TICKER}: { px:OLDVAL, ...`,", A.C_DAILY_PRE)
        self.assertIn("(URL template trong pipeline). \n   Dùng browser_batch", A.C_MASTER_PRE)
        self.assertIn("Lưu ý: \n- KHÔNG", A.C_MASTER_PRE)
        self.assertEqual(pres[2]["s"]["borderLeft"], "3px solid #caa75c")
        self.assertEqual(pres[0]["s"]["whiteSpace"], "pre-wrap")

    def test_tables(self):
        d = by_key(self.root, "aud:D")
        trs = [n for n in walk(d) if isinstance(n, dict) and n.get("t") == "tr"]
        self.assertEqual(len(trs), 9)
        self.assertEqual([th["s"]["width"] for th in trs[0]["k"]], ["22%", "48%", "30%"])
        self.assertEqual(trs[1]["s"]["background"], "transparent")
        self.assertEqual(trs[2]["s"]["background"], "#1f1d2440")
        self.assertEqual(text_of(trs[3]), "Price range1,000 ≤ px ≤ 1,000,000 VNDP0_DAILY_PRICE")
        e = by_key(self.root, "aud:E")
        rows = [n for n in walk(e) if isinstance(n, dict) and n.get("t") == "tr"]
        self.assertEqual(len(rows), 9)
        self.assertEqual(text_of(rows[8]), "/home/claude/v21/master_plan_v21_chaebol_vn30.jsxSource file — "
                         "auto-update FLOW object via str_replace")
        self.assertIn("Claude Code lưu kết quả vào các file dưới đây. Tuấn có thể inspect, version-control, hoặc "
                      "feed lại cho V21 pipeline.", text_of(e))

    def test_tiers_and_guide(self):
        f = text_of(by_key(self.root, "aud:F"))
        for s in ("★ TIER 1 · CHAEBOL FOCUS (P0+P1 full coverage):GEX · GEE · GEL · VIX · VJC · VCI · DGC · MSN · "
                  "VCB · FPT", "◇ TIER 3 · VN30 PERIPHERY (P0 daily only):SSB · VIB"):
            self.assertIn(s, f)
        g = by_key(self.root, "aud:G")
        body = g["k"][1]
        self.assertEqual(sum(1 for c in body["k"] if isinstance(c, dict) and c["t"] == "br"), 6)
        self.assertIn("Lưu ý quan trọng: Claude Code KHÔNG được update các const phân tích", text_of(body))
        self.assertEqual(body["k"][-2]["s"], {"color": "#c5392f"})

    def test_no_live_marks_in_v21(self):
        with D.use_mode("v21", TODAY):
            _obj, stats = D.finalize(self.root)
        self.assertEqual((stats["tiers"], stats["can_data"], stats["upd"], stats["v21"]), ({}, 0, 0, 0))


# ── Mode live (kho thật; vắng → skip) ───────────────────────────────────────

_QTY = re.compile(r"\b\d+/\d+ mã|\b\d[\d,]*\.\d+%?|\b\d{1,3}(?:,\d{3})+\b|\b\d+ (?:giao dịch|đăng ký)\b|\d+(?:\.\d+)?h\b")

# Addendum 09/06: ngày (dd/mm[/yy]), năm, mã (C09, NQ79, Q1/26, FY26) không phải số liệu; tham số của claim che trước.
_ADD_DATE = re.compile(r"(?<![\w/])\d{1,2}/\d{1,2}(?:/\d{2,4})?(?![\w/])|\b20\d\d\b")
_ADD_PARAMS = ("hỗ trợ 23K", "trigger 42K", "stop 24K", "base 75-80K", "flow 60d", "VPB 60d", "(1 phiên)", "wave 2")
_ADD_NUM = re.compile(r"(?<![\w.,/+−-])[+−-]?\d+(?:[.,]\d+)*(?:-\d+)?(?:K|M|x|%|d|Y| tỷ)?(?!\w)")


def _strip_marks(n):
    """Chữ của nút bỏ nhãn bậc / V21·12/05 / [CẦN DATA] (để so với nguyên văn V21)."""
    if isinstance(n, str):
        return n
    return "" if is_mark(n) else "".join(_strip_marks(c) for c in n.get("k", ()))


def _unlabelled(node):
    """Đoạn chữ con trực tiếp của `node` có số liệu mà số đó không đứng cuối đoạn (đuôi ≤16 ký tự, không số) hoặc
    ngay sau không phải nhãn — tức số không có nhãn bậc của riêng nó."""
    kids = node.get("k", ())
    bad = []
    for i, c in enumerate(kids):
        if not isinstance(c, str):
            continue
        m = _ADD_DATE.sub(lambda x: "#" * len(x.group()), c)
        for p in _ADD_PARAMS:
            m = m.replace(p, "#" * len(p))
        toks = list(_ADD_NUM.finditer(m))
        if not toks:
            continue
        tail = m[toks[-1].end():]
        nxt = kids[i + 1] if i + 1 < len(kids) else None
        if len(toks) > 1 or re.search(r"\d", tail) or len(tail) > 16 or not is_mark(nxt):
            bad.append(c[:60])
    return bad


def _live_ctx(dossier=True, data=True):
    import chaebol_map_data as CD
    if not (CD.sys_dir() / "fincept_bridge" / "state" / "vc_lk").is_dir():
        raise unittest.SkipTest("không có kho vc_lk thật")
    ctx = M.Ctx("live", TODAY, list(S.TABS_V21))
    ctx.v21 = load_v21()
    ctx.data = CD if data else None
    if data:
        CD.clear_cache()
        ctx.dossier = M.load_dossier(ctx) if dossier else None
        ctx.live_info = M.live_numbers(ctx)
    ctx.tab = "audit"
    return ctx


class TestLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with D.use_mode("live", TODAY):
            cls.ctx = _live_ctx()
            cls.res = A.build_audit(cls.ctx)
        cls.root = cls.res["root"]
        cls.dz = ((cls.ctx.dossier or {}).get("audit") or {})

    def test_same_state_and_tree(self):
        self.assertEqual(self.res["states"][0]["options"], PIPE_IDS)
        self.assertEqual(len(keys_like(self.root, "aud.detail:")), 11)
        self.assertEqual(len(keys_like(self.root, "aud.live:")), 11)

    def test_every_live_number_is_labelled(self):
        """Mỗi ô/hàng số sống (khối SỔ NGUỒN, dòng 2 thẻ số, cột KIỂM, độ phủ) có nhãn bậc hoặc [CẦN DATA]."""
        bad = []
        for prefix in ("aud.live:", "aud.stat:", "aud.chk:", "aud.cov:"):
            for box in keys_like(self.root, prefix):
                rows = [c for c in box.get("k", ()) if isinstance(c, dict) and c.get("t") == "div"] or [box]
                for r in rows:
                    t = text_of(r)
                    if _QTY.search(t) and not any(is_mark(n) for n in walk(r)):
                        bad.append((box.get("key"), t[:120]))
        self.assertEqual(bad, [])
        self.assertGreaterEqual(len(keys_like(self.root, "aud.stat:")), 5)
        self.assertEqual(len(keys_like(self.root, "aud.chk:")), 8)

    def test_v21_counts_carry_v21_mark(self):
        grid = by_key(self.root, "aud:A")["k"][1]["k"][1]
        for card in grid["k"]:
            self.assertTrue(any(isinstance(n, dict) and n.get("_v21") for n in walk(card["k"][1])))

    def test_validation_statuses(self):
        allowed = {"ĐẠT", "BỊ BÁC", "CHƯA RÕ", "LIVE", "HẾT HẠN"}
        cells = keys_like(self.root, "aud.chk:")
        pills = [text_of(c["k"][0]) for c in cells]
        self.assertTrue(set(pills) <= allowed, pills)
        self.assertEqual(pills[0], "HẾT HẠN")                     # zero-sum sau 08/05 không kiểm được
        self.assertEqual(pills[5], "HẾT HẠN")                     # mùa ĐHĐCĐ 2026 đã qua
        self.assertEqual(pills[6], "CHƯA RÕ")                     # BULL/BEAR: thiếu ca60/to60
        self.assertIn("[CẦN DATA", text_of(cells[6]))
        th = [n for n in walk(by_key(self.root, "aud:D")) if isinstance(n, dict) and n.get("t") == "th"]
        self.assertEqual(len(th), 4)

    def test_flow_policy(self):
        box = by_key(self.root, "aud.live:P0_FLOW_PILLAR_IV")
        t = text_of(box)
        self.assertIn("[CẦN DATA — ca60, to60", t)
        self.assertIn("vc_lk/proprietary-history", t)
        self.assertIn("FiinTrade", t)
        if self.dz:
            btn = by_key(self.root, "aud.pipe:P0_FLOW_PILLAR_IV")
            self.assertIn("FiinTrade ≤08/05 đóng băng", text_of(btn))
            self.assertTrue(any(isinstance(n, dict) and n.get("_upd") for n in walk(btn)))

    def test_basket_is_vnstore(self):
        import chaebol_map_data as CD
        b = CD.basket("VN30")
        if b.value is None:
            self.skipTest("không đọc được rổ vnstore")
        miss = [t for t in b.value if t not in load_v21()["VN30_TICKERS_FOR_AUDIT"]]
        cov = text_of(by_key(self.root, "aud.cov:basket"))
        self.assertIn(" · ".join(miss), cov)
        self.assertNotIn("POW", cov.split("—")[0])               # bang_vn30 (watchlist) không dùng làm rổ

    def test_no_email_live_and_csv(self):
        self.assertNotIn("@bidv", json.dumps(self.root, ensure_ascii=False))
        rows = self.res["csv"]
        self.assertEqual([r["pipeline"] for r in rows], PIPE_IDS)
        self.assertTrue(all(r["trang_thai"] for r in rows))

    def test_live_without_dossier_keeps_v21_text(self):
        with D.use_mode("live", TODAY):
            ctx = _live_ctx(dossier=False)
            res = A.build_audit(ctx)
        call = text_of(by_key(res["root"], "aud:A")["k"][1]["k"][0])
        self.assertTrue(call.startswith("Tab này được thiết kế để Claude Code"))
        self.assertTrue(call.endswith("V21·12/05"))
        self.assertTrue(any("dossier chưa có khối 'audit'" in w for w in ctx.warnings))
        self.assertIn("NOTES · Chạy 1 lần cuối ngày", text_of(by_key(res["root"], "aud.detail:P0_DAILY_PRICE")))

    def test_live_without_data_module(self):
        with D.use_mode("live", TODAY):
            ctx = M.Ctx("live", TODAY, list(S.TABS_V21))
            ctx.v21 = load_v21()
            ctx.tab = "audit"
            res = A.build_audit(ctx)
        t = text_of(by_key(res["root"], "aud.live:P0_DAILY_PRICE"))
        self.assertIn("[CẦN DATA", t)
        self.assertTrue(any("không có chaebol_map_data" in w for w in ctx.warnings))

    # ── sửa sau kiểm chứng 27/09 (kho thật) ──

    def test_news_feeds_are_unverified_not_t3(self):
        """Tài sản bậc NEWS (guong, headlines) mang U; T3 của chú giải là sell-side/Toàn Vũ."""
        for aid in ("guong", "headlines"):
            box = by_key(self.root, "aud.live:P2_LEGAL_NEWS")
            rows = [r for r in box["k"] if isinstance(r, dict) and text_of(r).startswith("→ " + aid + " ·")]
            if not rows:
                continue
            tiers = [n["_tier"] for n in walk(rows[0]) if isinstance(n, dict) and n.get("_tier")]
            self.assertEqual(tiers, ["UNVERIFIED"], aid)
        chk8 = by_key(self.root, "aud.chk:8")
        self.assertNotIn("SS-T3", [n["_tier"] for n in walk(chk8) if isinstance(n, dict) and n.get("_tier")])

    def test_sla_is_asset_sla_not_weekend_threshold(self):
        raw = json.loads((M.bridge_dir() / "data" / "so_nguon_audit.json").read_text("utf-8"))
        for r in raw.get("tai_san") or []:
            if r.get("id") != "liquidity_daily" or r.get("tuoi_gio") is None or r.get("sla_gio") is None:
                continue
            row = [x for x in by_key(self.root, "aud.live:P3_MACRO_BACKDROP")["k"]
                   if isinstance(x, dict) and text_of(x).startswith("→ liquidity_daily ·")]
            self.assertTrue(row)
            self.assertIn("/SLA %dh" % r["sla_gio"], text_of(row[0]))
            if r.get("nguong_gio") and r["nguong_gio"] != r["sla_gio"]:
                self.assertIn("(ngưỡng cuối tuần %dh)" % r["nguong_gio"], text_of(row[0]))

    # ── vòng hoàn thiện 27/09 (final_check §6.1 #1, #13, #14) ──

    def test_stat_validation_breaks_only_between_statuses(self):
        """Ô VALIDATION: mỗi 'N TRẠNG THÁI' là span nowrap (không còn '2 HẾT / HẠN'); nhãn bậc dính mục cuối."""
        box = by_key(self.root, "aud.stat:VALIDATION")
        spans = [c for c in box["k"] if isinstance(c, dict)]
        self.assertEqual({(c["s"] or {}).get("whiteSpace") for c in spans}, {"nowrap"})
        self.assertEqual([c for c in box["k"] if isinstance(c, str)], [" · "] * (len(spans) - 1))
        for c in spans:
            self.assertRegex(text_of(c["k"][0]), r"^\d+ (ĐẠT|LIVE|CHƯA RÕ|BỊ BÁC|HẾT HẠN)$")
        self.assertTrue(spans[-1]["k"][-1].get("_tier"))
        self.assertNotIn("kiểm", text_of(box))

    def _shell(self):
        with D.use_mode("live", TODAY):
            return S.build_shell(self.ctx, list(S.TABS_V21))

    def test_addendum_every_number_labelled(self):
        """Addendum 09/06 ở live (dossier thật): mỗi số liệu (không tính ngày, mã, tham số của claim) kết thúc một đoạn
        chữ và ngay sau là nhãn bậc / V21·12/05; chữ ghép lại vẫn trùng nguyên văn."""
        if not (self.ctx.dossier or {}).get("header", {}).get("addendum"):
            self.skipTest("dossier chưa có header.addendum")
        add = by_key(self._shell(), "addendum")
        cells = [n for n in walk(add) if isinstance(n, dict) and n.get("t") == "td"]
        p2 = [n for n in add["k"] if n.get("t") == "p" and text_of(n).startswith("📊 Macro")]
        self.assertEqual(len(p2), 1)
        self.assertEqual(_strip_marks(p2[0]), S.ADD_P2)
        bad = []
        for n in p2 + cells:
            bad += _unlabelled(n)
        self.assertEqual(bad, [])
        rows = {text_of(tr["k"][0]): tr for tr in keys_like(add, "addendum:") if tr["t"] == "tr"}
        self.assertEqual(len(rows), 20)
        for cid, claim, _st, _c, check in S.ADD_ROWS:
            self.assertEqual(_strip_marks(rows[cid]["k"][1]).replace("Pattern A?", "Pattern A"), claim)
            self.assertTrue(_strip_marks(rows[cid]["k"][3]).startswith(check), cid)
        n_marks = sum(1 for n in walk(add) if is_mark(n))
        self.assertGreaterEqual(n_marks, 40)
        az = self.ctx.dossier["header"]["addendum"]            # DESIGN §7: mỗi mục dossier có asof + src
        segs = [s for s in az["p2"] if isinstance(s, dict)]
        for r in az["rows"].values():
            segs += [s for k in ("claim", "check") for s in r.get(k, []) if isinstance(s, dict)]
            if r.get("rescored"):
                segs.append(r)
        self.assertEqual([s.get("text") for s in segs if not (s.get("asof") and s.get("src"))], [])

    def test_addendum_rescored_rows_point_to_tab09(self):
        c20 = (self.ctx.dossier or {}).get("claims20") or {}
        if not ((self.ctx.dossier or {}).get("header", {}).get("addendum") and c20):
            self.skipTest("dossier chưa có header.addendum / claims20")
        add = by_key(self._shell(), "addendum")
        for cid in ("C03", "C08", "C14"):
            tr = by_key(add, "addendum:" + cid)
            self.assertTrue(text_of(tr["k"][2]).endswith("trạng thái 09/06"), cid)
            ptr = tr["k"][3]["k"][-1]
            self.assertTrue(text_of(ptr).startswith("→ đã chấm lại ở tab 09 · CLAIMS C01-C20: " + c20[cid]["status"]))
            self.assertEqual([n["_tier"] for n in walk(ptr) if isinstance(n, dict) and n.get("_tier")],
                             [c20[cid]["tier"]])
        for cid in ("C01", "C05", "C18"):
            self.assertNotIn("trạng thái 09/06", text_of(by_key(add, "addendum:" + cid)))
        self.assertIn("Pattern A?", text_of(by_key(add, "addendum:C09")))
        self.assertIn("MSN Pattern B accumulation", text_of(by_key(add, "addendum:C18")))   # MSN thuộc 30 mã TV

    def test_dossier_fixes_2709(self):
        if not self.dz:
            self.skipTest("không có dossier audit")
        right = self.ctx.dossier["header"]["footer"]["right"]["text"]
        self.assertIn("liquidity_daily (tỷ giá NHTM)", right)
        self.assertIn("tpcp_vn (TPCP HNX)", right)
        self.assertNotIn("26/09", self.dz["coverage"]["note"])
        flow = json.dumps(self.dz["pipelines"]["P0_FLOW_PILLAR_IV"]["notes"], ensure_ascii=False)
        self.assertNotIn("từ phiên 28/08", flow)
        self.assertIn("từ phiên 03/09", flow)
        notes = text_of(by_key(self.root, "aud.detail:P0_DAILY_PRICE"))
        self.assertIn("TCB cổ tức cổ phiếu 50% (công bố 16/09) chưa GDKHQ", notes)
        self.assertNotIn("(VHM, VPB, VJC, FPT, TCB, NVL", notes)
        e = text_of(by_key(self.root, "aud:E"))
        self.assertNotIn("TƯƠI 27/09T3", e)


# ── Sửa sau kiểm chứng 27/09: đơn vị, dữ liệu giả (tất định, không cần kho) ──


def _fake_audit(assets=None, ph=None, insider=None, cov=None, data_to="2026-09-25"):
    """LiveAudit dựng tay (bỏ qua __init__ đọc kho): chỉ các thuộc tính mà phương thức được kiểm dùng tới."""
    la = AL.LiveAudit.__new__(AL.LiveAudit)
    la.ctx = SimpleNamespace(warn=lambda m: None, today=TODAY, v21={})
    la.D = SimpleNamespace(insider_tx=lambda tk, since=None: SimpleNamespace(value=(insider or {}).get(tk, [])))
    la.tickers = sorted((ph or {}).keys()) or ["HCM"]
    la.assets = assets or {}
    la.now = datetime(2026, 9, 27, 16, 13, tzinfo=AL.ICT)
    la._ph = ph or {}
    la._cov = cov or {}
    la.data_to = data_to
    la.dz = {}
    return la


def _ph(rows, cols=("tradingDate", "closePrice", "closePriceAdjusted", "totalShares")):
    import chaebol_map_data as CD
    return CD.Cols(list(cols), [list(r) for r in rows])


class TestFixes2709(unittest.TestCase):
    def test_tag_news_is_unverified(self):
        self.assertEqual(AL._tag("NEWS"), "UNVERIFIED")
        self.assertEqual(AL._tag("FACT-T2"), "FACT-T2")

    def test_insider_pct_on_trade_date_shares(self):
        """HCM: 30,409,599 cp giao dịch 27/08, công bố 07/09; phát hành thêm 18/09 → mẫu số là cp tại 27/08."""
        ph = _ph([("2026-08-27", 30000, 30000, 1349945838), ("2026-09-07", 30000, 30000, None),
                  ("2026-09-18", 30000, 30000, 1371945838), ("2026-09-25", 30000, 30000, None)])
        rec = {"public_date": "2026-09-07", "start": "2026-08-27", "end": "2026-08-27", "status": "da_xong",
               "trader": "Tổ chức X", "action_vi": "Mua", "acquire": 30409599.0, "register": None,
               "own_after_pct": 11.26}
        la = _fake_audit(ph={"HCM": ph}, insider={"HCM": [rec]})
        with D.use_mode("live", TODAY):
            rows = la._insider_rows("2026-06-27")
            self.assertAlmostEqual(rows[0]["pct"], 30409599 / 1349945838 * 100)
            self.assertEqual(rows[0]["sh_d"], "2026-08-27")
            ex = la.insider_example()
        t = "".join(text_of(x) for x in ex if x)
        self.assertIn("HCM giao dịch 27/08/2026 (công bố 07/09/2026) — Tổ chức X mua 30,409,599 cpT2·27/08", t)
        self.assertIn("(2.25% cp lưu hành tại ngày giao dịchE·27/08; sở hữu sau 11.26%T2·27/08)", t)
        self.assertEqual(la._shares_at("HCM", "2026-09-07"), (1349945838, "2026-08-27"))   # phiên trống → lùi
        self.assertEqual(la._shares_at("HCM", "2026-01-01"), (None, None))

    def test_future_moc_is_not_fresh(self):
        a = {"headlines": {"id": "headlines", "duong_dan": "x.json", "bac": "NEWS", "trang_thai": "TƯƠI",
                           "moc": "2026-09-28T04:00:00+00:00", "tuoi_gio": 0.0, "sla_gio": 12, "nguong_gio": 60},
             "vc_cbtt": {"id": "vc_cbtt", "duong_dan": "y.xml", "bac": "FACT-T2", "trang_thai": "TƯƠI",
                         "moc": "2026-09-26T06:48:00+07:00", "tuoi_gio": 35.9, "sla_gio": 72, "nguong_gio": 72}}
        la = _fake_audit(assets=a)
        self.assertEqual(la._status("headlines"), "KHÔNG ĐO")
        self.assertEqual(la._worst(["vc_cbtt"]), "TƯƠI")
        self.assertEqual(la._worst(["vc_cbtt", "headlines"]), "KHÔNG ĐO")
        with D.use_mode("live", TODAY):
            row = la._asset_row("headlines")
        t = text_of(row)
        self.assertIn("KHÔNG ĐO · mốc 28/09/2026 11:00 ở tương lai so với lúc dựng 27/09 16:13 — lỗi khoá thời gian "
                      "nguồn (Sổ nguồn ghi TƯƠI; tuổi không đo được)", t)
        self.assertEqual([n["k"][0] for n in walk(row) if isinstance(n, dict) and n.get("_tier")], ["U"])

    def test_sla_and_weekend_threshold(self):
        a = {"liq": {"id": "liq", "duong_dan": "l.json", "bac": "FACT-T2", "trang_thai": "TƯƠI",
                     "moc": "2026-09-25T17:00:06+07:00", "tuoi_gio": 46.9, "sla_gio": 30, "nguong_gio": 78},
             "vc": {"id": "vc", "duong_dan": "m.json", "bac": "FACT-T2", "trang_thai": "TƯƠI",
                    "moc": "2026-09-25T00:00:00+07:00", "tuoi_gio": 66.7, "sla_gio": 120, "nguong_gio": 120}}
        la = _fake_audit(assets=a)
        with D.use_mode("live", TODAY):
            t1, t2 = text_of(la._asset_row("liq")), text_of(la._asset_row("vc"))
        self.assertIn("TƯƠI · mốc 25/09/2026 · tuổi 46.9h/SLA 30h (ngưỡng cuối tuần 78h)T2·25/09", t1)
        self.assertIn("tuổi 66.7h/SLA 120hT2·25/09", t2)

    def test_file_layout_endpoint_dates_and_per_asset_tiers(self):
        a = {"vc_lk_meta": {"id": "vc_lk_meta", "bac": "FACT-T2", "trang_thai": "TƯƠI", "moc": "2026-09-25T00:00:00+07:00"},
             "guong": {"id": "guong", "bac": "NEWS", "trang_thai": "TƯƠI", "moc": "2026-09-27T15:34:00+07:00"},
             "vc_cbtt": {"id": "vc_cbtt", "bac": "FACT-T2", "trang_thai": "TƯƠI", "moc": "2026-09-26T06:48:00+07:00"}}
        cov = {"proprietary-history": {"n": 45, "total": 45, "min": "2026-08-25", "max": "2026-09-24",
                                       "kind": "sự kiện mới nhất"},
               "shareholder-structure": {"n": 45, "total": 45, "min": "2026-09-23", "max": "2026-09-27", "kind": "lấy"}}
        la = _fake_audit(assets=a, cov=cov)
        la.dz = {"file_layout": {"intro": "x", "asof": "2026-09-27", "rows": [
            {"path": "p", "desc": "P", "asset": "vc_lk_meta", "endpoint": "proprietary-history"},
            {"path": "s", "desc": "S", "asset": "vc_lk_meta", "endpoint": "shareholder-structure"},
            {"path": "g", "desc": "G", "assets": ["guong", "vc_cbtt"]}]}}
        with D.use_mode("live", TODAY):
            _intro, rows, _cols = la.file_layout([], [], None)
        texts = ["".join(text_of(x) for x in d if x) for _p, d, _e in rows]
        self.assertEqual(texts[0], "P · TƯƠI · 45/45 mã tới 24/09T2·24/09")
        self.assertEqual(texts[1], "S · TƯƠI · 45/45 mã lấy 27/09 (cũ nhất 23/09)T2·27/09")
        self.assertEqual(texts[2], "G · guong TƯƠI 27/09U·27/09 · vc_cbtt TƯƠI 26/09T2·26/09")

    def test_nqs_label_uses_data_as_of(self):
        la = _fake_audit()
        la._extra_json = lambda rel: {"generated_at": "2026-09-27T16:46", "window_sessions": 10,
                                      "by_ticker": {"ACB": {"ca": 0.0, "as_of": "25/09"}, "VCB": {"ca": 0.0, "as_of": "24/09"}}}
        with D.use_mode("live", TODAY):
            rows = la._check_rows("P0_FLOW_PILLAR_IV")
        self.assertEqual("".join(text_of(x) for x in rows[0] if x),
                         "nqs_flow (alpha_spine, chưa có dòng SO): kênh cá nhân = 0 ở 2/2 mã · cửa sổ 10 phiênT3·25/09")

    def test_adj_events(self):
        ph = {"VHM": _ph([("2026-05-08", 100, 50, 1), ("2026-08-06", 60, 60, 1), ("2026-09-25", 61, 61, 1)]),
              "TCB": _ph([("2026-05-08", 30, 29.9, 1), ("2026-09-25", 35, 35, 1)]),
              "MSN": _ph([("2026-05-08", 80, 80, 1), ("2026-09-25", 90, 90, 1)])}
        la = _fake_audit(ph=ph)
        ev = dict(la.adj_events())
        self.assertEqual(sorted(ev), ["VHM"])                     # TCB lệch 0,33% < ngưỡng 0,5%; MSN không đổi
        self.assertAlmostEqual(ev["VHM"], 50.0)


# ── Móc dossier.header của shell (live) ─────────────────────────────────────


class TestShellHeaderHook(unittest.TestCase):
    HDR = {"subline": {"text": "⨯ SUBLINE MỚI ⨯", "tier": "FACT-T2", "asof": "2026-09-27", "src": "x"},
           "strip": {"IV.": {"text": " Pillar flow mới", "tier": "FACT-T2", "asof": "2026-09-27", "src": "x"}},
           "footer": {"left": {"text": "TRÁI MỚI", "tier": "EST", "asof": "2026-09-27", "src": "x"},
                      "right": {"text": "NGUỒN MỚI", "tier": "FACT-T2", "asof": "2026-09-27", "src": "x"}}}

    def _body(self, mode, header=True, data_to="2026-09-25"):
        with D.use_mode(mode, TODAY):
            ctx = M.Ctx(mode, TODAY, list(S.TABS_V21))
            if mode == "live":
                ctx.dossier = {"header": self.HDR} if header else {}
                ctx.live_info = {"vnindex": None, "usdvnd": None, "cong": None, "data_to": data_to}
            return S.build_shell(ctx, list(S.TABS_V21))

    def test_live_header_footer_rewritten(self):
        body = self._body("live")
        hdr = text_of(by_key(body, "header"))
        self.assertIn("⨯ SUBLINE MỚI ⨯↻27/09", hdr)
        self.assertNotIn("NgườiQuanSát.vn (forward", hdr)
        self.assertIn("IV. Pillar flow mới↻27/09·V. ★ NEW", text_of(by_key(body, "strip")))
        foot = text_of(by_key(body, "footer"))
        self.assertTrue(foot.startswith("TRÁI MỚI · As of 25/09/2026↻27/09NGUỒN MỚI↻27/09"))
        foot2 = text_of(by_key(self._body("live", data_to=None), "footer"))
        self.assertTrue(foot2.startswith("TRÁI MỚI · As of [CẦN DATA — ngày dữ liệu]"))

    def test_h1_month_marked_live_only(self):
        h1 = next(n for n in walk(by_key(self._body("live"), "header")) if isinstance(n, dict) and n.get("t") == "h1")
        self.assertEqual(text_of(h1), "Bản Đồ Chaebol & VN30 — Tháng 9, 2026↻27/09")
        self.assertTrue(h1["k"][-1].get("_upd"))
        h1v = next(n for n in walk(by_key(self._body("v21"), "header")) if isinstance(n, dict) and n.get("t") == "h1")
        self.assertEqual(text_of(h1v), "Bản Đồ Chaebol & VN30 — Tháng 5, 2026")

    def test_cong_legend_is_one_atomic_block(self):
        cong = by_key(self._body("live"), "cong")
        blocks = [n for n in cong["k"] if isinstance(n, dict) and (n.get("s") or {}).get("display") == "inline-block"]
        self.assertEqual(len(blocks), 1)
        self.assertTrue(text_of(blocks[0]).startswith("Nhãn bậc: T1 CBTT/BCTC · T2 vendor · T3 sell-side/Toàn Vũ"))
        self.assertTrue(text_of(blocks[0]).endswith("U chưa xác minh"))
        self.assertIn(" · as of ", text_of(cong["k"][0]))

    def test_v21_and_live_without_block_unchanged(self):
        for body in (self._body("v21"), self._body("live", header=False)):
            self.assertIn(S.SUBLINE, text_of(by_key(body, "header")))
            self.assertIn("IV. Pillar real-time (FiinTrade ≤08/05 · NgườiQuanSát ≥09/05)", text_of(by_key(body, "strip")))
            self.assertTrue(text_of(by_key(body, "footer")).startswith(S.FOOT_LEFT + S.FOOT_RIGHT))


# ── Addendum 09/06 ở live: nhãn bậc từng số, "Pattern X?", trỏ bản chấm lại (dữ liệu giả, tất định) ─────────


class TestShellAddendum(unittest.TestCase):
    C06 = next(r[4] for r in S.ADD_ROWS if r[0] == "C06")
    SEG = [{"text": "PE 8,26", "tier": "FACT-T2", "asof": "2026-06-05", "src": "x"}, "/PB 1,36 rẻ",
           {"text": ", BUY +17%", "tier": "SS-T3", "asof": "2026-06-05", "src": "y"}]

    def _add(self, mode="live", dossier=None, data=None):
        with D.use_mode(mode, TODAY):
            ctx = M.Ctx(mode, TODAY, list(S.TABS_V21))
            ctx.dossier, ctx.data = dossier, data
            return by_key(S.build_shell(ctx, list(S.TABS_V21)), "addendum"), ctx

    @staticmethod
    def _row(add, cid):
        return by_key(add, "addendum:" + cid) or next(tr for tr in walk(add) if isinstance(tr, dict)
                                                      and tr.get("t") == "tr" and text_of(tr).startswith(cid))

    def test_v21_untouched(self):
        add, _ = self._add("v21", data=SimpleNamespace(tv30=lambda: []))
        self.assertEqual(text_of(self._row(add, "C09")["k"][1]), "DGC 3 BOD khởi tố — Pattern A")
        self.assertFalse(keys_like(add, "addendum:"))
        self.assertFalse([n for n in walk(add) if is_mark(n) or (isinstance(n, dict) and n.get("_upd"))])

    def test_pattern_suffix_only_outside_tv30(self):
        tv = SimpleNamespace(tv30=lambda: ["MSN", "HPG"])
        add, _ = self._add(data=tv)
        self.assertEqual(text_of(self._row(add, "C09")["k"][1]), "DGC 3 BOD khởi tố — Pattern A?")
        self.assertEqual(text_of(self._row(add, "C18")["k"][1]), "MSN Pattern B accumulation")
        add2, _ = self._add(data=SimpleNamespace(tv30=lambda: ["DGC", "MSN"]))
        self.assertEqual(text_of(self._row(add2, "C09")["k"][1]), "DGC 3 BOD khởi tố — Pattern A")
        # không đọc được danh sách → vẫn gắn "?" (không khẳng định pattern chưa xác minh) + cảnh báo khi lỗi
        add3, _ = self._add(data=None)
        self.assertEqual(text_of(self._row(add3, "C18")["k"][1]), "MSN Pattern B? accumulation")

        def boom():
            raise OSError("hỏng")
        add4, ctx4 = self._add(data=SimpleNamespace(tv30=boom))
        self.assertIn("Pattern A?", text_of(self._row(add4, "C09")))
        self.assertTrue(any("30 mã Toàn Vũ" in w for w in ctx4.warnings))

    def test_segments_insert_tiers_keep_text(self):
        seg = self.SEG + [self.C06[len("PE 8,26/PB 1,36 rẻ, BUY +17%"):]]
        add, ctx = self._add(dossier={"header": {"addendum": {"rows": {"C06": {"check": seg}}}}})
        td = self._row(add, "C06")["k"][3]
        self.assertEqual(_strip_marks(td), self.C06)
        self.assertEqual([n["k"][0] for n in walk(td) if isinstance(n, dict) and n.get("_tier")], ["T2·05/06", "T3·05/06"])
        self.assertIsInstance(td["k"][1], dict)                      # nhãn ngay sau "PE 8,26"
        self.assertFalse(ctx.warnings)
        # ghép lệch nguyên văn → giữ nguyên văn, cảnh báo, không nhãn
        add2, ctx2 = self._add(dossier={"header": {"addendum": {"rows": {"C06": {"check": self.SEG}}}}})
        self.assertEqual(self._row(add2, "C06")["k"][3]["k"], [self.C06])
        self.assertTrue(any("lệch nguyên văn" in w for w in ctx2.warnings))

    def test_p2_and_note(self):
        p2 = [{"text": S.ADD_P2[:15], "tier": "UNVERIFIED", "src": "u"}, S.ADD_P2[15:]]
        note = {"text": "Lưu trữ 09/06 — xem tab 09.", "tier": "EST", "asof": "2026-09-27", "src": "n"}
        add, _ = self._add(dossier={"header": {"addendum": {"p2": p2, "note": note}}})
        self.assertEqual(text_of(by_key(add, "addendum:note")), "Lưu trữ 09/06 — xem tab 09.↻27/09")
        macro = next(n for n in add["k"] if n.get("t") == "p" and text_of(n).startswith("📊"))
        self.assertEqual(_strip_marks(macro), S.ADD_P2)
        self.assertEqual(macro["k"][1]["k"], ["U"])
        add2, _ = self._add()
        self.assertIsNone(by_key(add2, "addendum:note"))
        self.assertIn("lưu trữ 09/06", text_of(add2))

    def test_rescored_marks_and_pointer(self):
        rows = {"C03": {"rescored": True, "src": "s"}}
        c20 = {"C03": {"status": "BỊ BÁC", "tier": "FACT-T2", "asof": "2026-07-27", "src": "vc_lk"}}
        add, _ = self._add(dossier={"as_of": "2026-09-27", "header": {"addendum": {"rows": rows}}, "claims20": c20})
        tr = self._row(add, "C03")
        self.assertEqual(text_of(tr["k"][2]), "🟢 LIVEtrạng thái 09/06")
        self.assertEqual(tr["k"][2]["k"][1]["s"]["fontFamily"], D.F_MONO)
        ptr = tr["k"][3]["k"][-1]
        self.assertEqual(text_of(ptr), "→ đã chấm lại ở tab 09 · CLAIMS C01-C20: BỊ BÁCT2·27/07↻27/09")
        self.assertTrue(text_of(tr["k"][3]).startswith(next(r[4] for r in S.ADD_ROWS if r[0] == "C03")))
        self.assertNotIn("trạng thái 09/06", text_of(self._row(add, "C08")))
        add2, _ = self._add(dossier={"as_of": "2026-09-27", "header": {"addendum": {"rows": rows}}})
        self.assertIn("[CẦN DATA — chưa đọc được claims20.C03]", text_of(self._row(add2, "C03")))


# ── Lõi: dựng qua assemble với --tabs audit ─────────────────────────────────


class TestAssemble(unittest.TestCase):
    def test_assemble_v21_only_audit(self):
        load_v21()
        files, man, _csv = M.assemble("v21", TODAY, only={"audit"})
        tab = next(t for t in man["tabs"] if t["id"] == "audit")
        self.assertEqual(tab["status"], "ok")
        self.assertEqual(man["inventory"]["coverage"], {"missing": [], "mismatch": []})
        self.assertFalse([w for w in man["warnings"] if w.startswith("[audit]")])
        obj = json.loads(files["tab_audit.json"])
        self.assertEqual(obj["root"]["scope"], ["aud.bl." + p for p in PIPE_IDS] + ["aud.pipe"])


if __name__ == "__main__":
    unittest.main()
