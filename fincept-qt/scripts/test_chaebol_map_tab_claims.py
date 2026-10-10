#!/usr/bin/env python3
"""Unit tests cho chaebol_map_tab_claims (tab 09 `changelog` + tab 11 `claims54`) — không mạng.

Chạy (cả hai trình thông dịch):
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest scripts/test_chaebol_map_tab_claims.py -v
    PYTHONDONTWRITEBYTECODE=1 ~/Library/Application\\ Support/com.fincept.terminal/venv-numpy2/bin/python \\
        -m unittest scripts/test_chaebol_map_tab_claims.py

Chuỗi vàng lấy từ chaebol_map_spec/page_p6 §5, page_p7b §5, page_p7a §2 (và cây JSX gốc đã đối chiếu 0 lệch ở trạng thái
mặc định + 10 trạng thái lọc). Hằng V21 đọc từ fincept_bridge/data/chaebol_map/v21_const.json (bỏ qua nếu vắng).
"""
from __future__ import annotations

import json
import re
import socket
import sys
import types
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import chaebol_map as M  # noqa: E402
import chaebol_map_dom as D  # noqa: E402
import chaebol_map_shell as S  # noqa: E402
import chaebol_map_tab_claims as T  # noqa: E402

V21_PATH = M.bridge_dir() / "data" / "chaebol_map" / "v21_const.json"
DOSSIER_PIECE = M.system_dir() / "knowledge_os" / "chaebol_map" / "cap_nhat_2026-09-27.claims.json"
STATUSES = {"ĐẠT", "BỊ BÁC", "CHƯA RÕ", "LIVE", "HẾT HẠN", "TIỀN ĐỀ SAI"}
TIERS = {"FACT-T1", "FACT-T2", "SS-T3", "EST", "UNVERIFIED"}
_REAL_SOCKET = {}


def setUpModule():
    def blocked(*a, **k):
        raise RuntimeError("mạng bị chặn trong test chaebol_map_tab_claims")
    for name in ("socket", "create_connection", "getaddrinfo"):
        _REAL_SOCKET[name] = getattr(socket, name)
        setattr(socket, name, blocked)


def tearDownModule():
    for name, fn in _REAL_SOCKET.items():
        setattr(socket, name, fn)


def load_v21():
    if not V21_PATH.is_file():
        raise unittest.SkipTest("không có v21_const.json thật")
    return json.loads(V21_PATH.read_text("utf-8"))


def walk(node):
    yield node
    if isinstance(node, dict):
        for ch in node.get("k", ()):
            yield from walk(ch)


def text_of(node):
    return node if isinstance(node, str) else "".join(text_of(c) for c in node.get("k", ()))


def by_key(root, key):
    return next((n for n in walk(root) if isinstance(n, dict) and n.get("key") == key), None)


def cond_ok(cond, st):
    for k, v in cond.items():
        val = "|".join(st.get(x, "") for x in k.split("|"))
        if (val not in v) if isinstance(v, list) else (val != v):
            return False
    return True


def rendered(node, st):
    """Cây sau khi áp `if` theo state (giống engine/oracle)."""
    if isinstance(node, str):
        return node
    if "if" in node and not cond_ok(node["if"], st):
        return None
    out = dict(node)
    kids = [rendered(k, st) for k in node.get("k", ())]
    out["k"] = [k for k in kids if k is not None]
    return out


def grp_count(node, grp, st):
    r = rendered(node, st)
    return sum(1 for n in walk(r) if isinstance(n, dict) and n.get("grp") == grp) if r else 0


def make_ctx(mode, v21, dossier=None, today=date(2026, 9, 27)):
    ctx = M.Ctx(mode, today, list(S.TABS_V21))
    ctx.v21 = v21
    ctx.dossier = dossier
    ctx.live_info = {"data_to": "2026-09-25"} if mode == "live" else {}
    return ctx


def is_label(n):
    return isinstance(n, dict) and ("_tier" in n or n.get("_can"))


class V21Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v21 = load_v21()
        with D.use_mode("v21", "2026-09-27"):
            ctx = make_ctx("v21", cls.v21)
            cls.cl = T.build_changelog(ctx)
            cls.c54 = T.build_claims54(ctx)


class TestV21Structure(V21Base):
    def test_changelog_blocks_in_order(self):
        keys = [k.get("key") for k in self.cl["root"]["k"]]
        self.assertEqual(keys, ["rs", "cp", "cl", "meth", "src", "road"])       # ResearchStackPanel render ĐẦU tab 09
        titles = [text_of(s["k"][0]["k"][1]) for s in self.cl["root"]["k"]]
        self.assertEqual(titles, ["🔬 VN EQUITY RESEARCH STACK · 25 tools cloned 12/05/2026",
                                  "20 FALSIFIABLE CLAIMS · C01-C20 (Popper + Munger inversion)",
                                  "V21 Changelog — Cấu Trúc Mới So Với V20", "Methodology Updates",
                                  "Data Sources & Citations", "Roadmap V22+ — Hướng Phát Triển"])

    def test_no_live_marks_in_v21(self):
        for res in (self.cl, self.c54):
            _, st = D.finalize(res["root"])
            self.assertEqual(st["tiers"], {})
            self.assertEqual((st["can_data"], st["upd"], st["v21"]), (0, 0, 0))

    def test_states_and_options(self):
        st = {s["key"]: s for s in self.cl["states"] + self.c54["states"]}
        self.assertEqual(st["rs.cat"]["options"], ["ALL", "Research", "Memory", "Parsing", "Skills", "Browser",
                                                  "Workflow", "Perplexity", "Financial", "Code-Research"])
        self.assertEqual(st["cp.filter"]["options"], ["ALL", "LIVE", "WATCH", "FAILED"])
        self.assertEqual(st["c54.pri"]["options"], ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"])
        self.assertEqual(len(st["c54.ch"]["options"]), 23)
        self.assertEqual(st["c54.ch"]["options"][:4], ["ALL", "Masan-TCB", "Vingroup", "Bầu Thụy"])
        for v in ("Hoà Phát", "T&T-SHB", "Vietcombank"):
            self.assertIn(v, st["c54.ch"]["options"])
        self.assertTrue(all(s["default"] == "ALL" for s in st.values()))
        opts = M.expected_options(self.v21)
        for k in ("rs.cat", "cp.filter", "c54.pri", "c54.ch"):
            self.assertEqual(sorted(opts[k]), sorted(st[k]["options"]), k)
        cov = M._coverage(list(st.values()), {"changelog", "claims54"}, self.v21)
        self.assertEqual(cov, {"missing": [], "mismatch": []})


class TestV21GoldenStrings(V21Base):
    def test_research_stack(self):
        rs = by_key(self.cl["root"], "rs")
        self.assertEqual(text_of(by_key(rs, "rs.btn:ALL")), "ALL ")                  # `{c} {false}` → "ALL "
        self.assertEqual(text_of(by_key(rs, "rs.btn:Research")), "Research · 5")
        self.assertEqual(text_of(by_key(rs, "rs.btn:Code-Research")), "Code-Research · 1")
        cnt = next(n for n in walk(rs) if isinstance(n, dict) and "count" in n)
        self.assertEqual(cnt["count"], {"grp": "rs.cards", "fmt": "Showing {n}/25"})
        card = by_key(rs, "rs:claude-research")
        self.assertIn("github.com/flonat/claude-research", text_of(card))
        self.assertIn("Cap: 48 skills + bibliography MCP (OpenAlex/Scopus/WoS)", text_of(card))
        self.assertIn("★★★ HIGHEST PRIORITY: Install Anthropic OFFICIAL anthropics/financial-services — Pitch",
                      text_of(rs))

    def test_claims_panel(self):
        cp = by_key(self.cl["root"], "cp")
        c01 = by_key(cp, "cp:C01")
        t = text_of(c01)
        self.assertTrue(t.startswith("C01LIVE · 30-60 ngàyVingroup reflexivity peakTK: VIC · VHM · VRE · VPL"))
        self.assertIn("✗ Falsified if: NN flip về +ve > +30M trên VIC OR VHM trong 30d kể từ 11/5/2026.", t)
        self.assertIn("Evidence: FiinTrade ≤08/05: VIC NN -19.1M", t)
        self.assertEqual(text_of(by_key(cp, "cp:C09")).split("·")[0], "C09WATCH ")
        self.assertIn("DGC 3 BOD bị khởi tố — Pattern A riskTK: DGC▶", text_of(by_key(cp, "cp:C09")))  # v21 nguyên văn

    def test_changelog_text(self):
        cl = text_of(by_key(self.cl["root"], "cl"))
        self.assertIn("— chaebol nào đang ascending vs descending vs eliminated. Lớp B chỉ đọc được qua tin nội bộ", cl)
        self.assertIn("Tuấn mượt · Sovico · Bà Phượng · ⛔ Eliminated (DGC/PC1/CTD)", cl)
        src = text_of(by_key(self.cl["root"], "src"))
        self.assertIn("dulieu.nguoiquansat.vn/du-lieu-giao-dich/khop-lenh-ndt-nn/{TK}", src)
        self.assertIn("• HSC · SSI · BSC · VCSC · MAS Use: lấy data points", src)
        self.assertIn("DISCLAIMER · Báo cáo này dành riêng cho", src)
        meth = by_key(self.cl["root"], "meth")
        rows = [n for n in walk(meth) if isinstance(n, dict) and n["t"] == "tr"]
        self.assertEqual(len(rows), 7)
        self.assertNotIn("s", rows[-1])                                              # dòng cuối không viền

    def test_claims54_order_and_stats(self):
        root = self.c54["root"]
        ids = [n["key"][4:] for n in walk(root) if isinstance(n, dict) and str(n.get("key", "")).startswith("c54:C")]
        self.assertEqual(ids[:4], ["C22", "C25", "C19", "C09"])                      # page_p7a §2.3
        self.assertEqual(ids[4:8], ["C18", "C02", "C13", "C28"])
        self.assertEqual(ids[-3:], ["C49", "C41", "C44"])
        self.assertEqual(len(ids), 54)
        top = text_of(by_key(root, "c54.top"))
        self.assertIn("From CHAEBOL-VN-21-PROJECT-KNOWLEDGE-v3.md · CRITICAL 4 · HIGH 14 · MEDIUM 23 · LOW 13", top)
        self.assertIn("⚡ TOP ALERTS · ≤60 ngày (12/5/2026)", top)
        alerts = [n["key"][10:] for n in walk(root) if isinstance(n, dict) and str(n.get("key", "")).startswith("c54.alert:")]
        self.assertEqual(alerts, ["C22", "C18", "C03", "C14"])
        self.assertIn("≤60d4Urgent watch", top)
        self.assertIn("PAST5Verify needed", top)
        c16 = text_of(by_key(root, "c54:C16"))
        self.assertIn("2026-05-06 · 6d PAST", c16)
        self.assertIn("Source: HPA HOSE · Thesis: PASSED 6d ago", c16)


class TestV21Interaction(V21Base):
    DEF = {"rs.cat": "ALL", "cp.filter": "ALL", "c54.pri": "ALL", "c54.ch": "ALL"}

    def st(self, **kw):
        s = dict(self.DEF)
        s.update({k.replace("_", "."): v for k, v in kw.items()})
        return s

    def test_research_filter_counts(self):
        root = self.cl["root"]
        want = {"ALL": 25, "Research": 5, "Memory": 4, "Parsing": 3, "Skills": 5, "Browser": 2, "Workflow": 1,
                "Perplexity": 3, "Financial": 1, "Code-Research": 1}
        for c, n in want.items():
            self.assertEqual(grp_count(root, "rs.cards", self.st(rs_cat=c)), n, c)

    def test_claims_filter_counts(self):
        root = self.cl["root"]
        for f, n in (("ALL", 20), ("LIVE", 19), ("WATCH", 1), ("FAILED", 0)):
            self.assertEqual(grp_count(root, "cp.cards", self.st(cp_filter=f)), n, f)

    def test_claims54_filters(self):
        root = self.c54["root"]
        for p, n in (("ALL", 54), ("CRITICAL", 4), ("HIGH", 14), ("MEDIUM", 23), ("LOW", 13)):
            self.assertEqual(grp_count(root, "c54.rows", self.st(c54_pri=p)), n, p)
        self.assertEqual(grp_count(root, "c54.rows", self.st(c54_ch="GELEX")), 5)
        self.assertEqual(grp_count(root, "c54.rows", self.st(c54_pri="CRITICAL", c54_ch="GELEX")), 0)
        empty = sum(1 for p in ("CRITICAL", "HIGH", "MEDIUM", "LOW") for ch in self.c54["states"][1]["options"][1:]
                    if grp_count(root, "c54.rows", self.st(c54_pri=p, c54_ch=ch)) == 0)
        self.assertEqual(empty, 54)                                                  # coverage_critic §2 #13
        sel = by_key(root, "c54.select")
        self.assertEqual(sel["bind"], "c54.ch")
        self.assertEqual([o["a"]["value"] for o in sel["k"]][0], "ALL")

    def test_as_intended_colors_and_fonts(self):
        rs = by_key(self.cl["root"], "rs")
        self.assertEqual(by_key(rs, "rs:claude-research")["s"]["borderLeft"], "3px solid #3d7a4e")    # C.emerald
        self.assertEqual(by_key(rs, "rs:perplexity-py")["s"]["borderLeft"], "3px solid #c5392f")      # C.crimson
        code = next(n for n in walk(rs) if isinstance(n, dict) and n["t"] == "code" and n.get("s"))
        self.assertEqual(code["s"]["background"], "#1a1a24")                                          # C.bg2
        btn = by_key(rs, "rs.btn:ALL")
        self.assertEqual((btn["s"]["fontFamily"], btn["s"]["fontSize"]), ("inherit", "inherit"))
        self.assertEqual(btn["s"]["fontWeight"], 600)
        self.assertEqual(by_key(self.cl["root"], "cp:C01")["s"]["borderLeft"], "3px solid #3d7a4e")


class TestHelpers(unittest.TestCase):
    def test_horizon_and_days(self):
        self.assertEqual(T.horizon_end("30-60 ngày"), date(2026, 7, 10))
        self.assertEqual(T.horizon_end("90 ngày"), date(2026, 8, 9))
        self.assertIsNone(T.horizon_end("?"))
        e = {c["id"]: c for c in T.enrich54([{"id": "C22", "dl": "2026-05-13", "p": "CRITICAL"},
                                             {"id": "C16", "dl": "2026-05-06", "p": "MEDIUM"}], date(2026, 5, 12))}
        self.assertEqual((e["C22"]["days"], e["C22"]["urgent"], e["C16"]["days"], e["C16"]["past"]), (1, True, -6, True))

    def test_rich_can_data(self):
        with D.use_mode("live", "2026-09-27"):
            out = [x for x in T._rich("A [CẦN DATA — OCF Q1] B [CẦN DATA]") if x]
        self.assertEqual(out[0], "A ")
        self.assertEqual(text_of(out[1]), "[CẦN DATA — OCF Q1]")
        self.assertEqual(text_of(out[3]), "[CẦN DATA]")

    def test_rich_inline_tiers(self):
        """Khối trộn bậc: "{T3·2026-08-28}" / "{E}" → nhãn nội dòng ngay sau con số; kết bằng nhãn → bỏ nhãn khối."""
        with D.use_mode("live", "2026-09-27"):
            out = [x for x in T._rich("DT 26,2 nghìn tỷ{T3·2026-08-28}, ~13/quý{E} [CẦN DATA]{U}") if x]
            self.assertEqual([x.get("_tier") if isinstance(x, dict) else x for x in out],
                             ["DT 26,2 nghìn tỷ", "SS-T3", ", ~13/quý", "EST", " ", None, "UNVERIFIED"])
            self.assertEqual(text_of(out[1]), "T3·28/08")
            self.assertTrue(T._ends_with_tier(out + ["."]))
            self.assertFalse(T._ends_with_tier(T._rich("A{T2} còn chữ")))
            blk = T.rescore_block({"status": "LIVE", "evidence": "X 1{T1·2026-06-30}", "tier": "FACT-T2",
                                   "asof": "2026-09-25", "src": "a/b"}, date(2026, 9, 27))
            tiers = [n["_tier"] for n in walk(blk) if isinstance(n, dict) and "_tier" in n]
            self.assertEqual(tiers, ["FACT-T1"])                                # không có nhãn khối trùng
            blk = T.rescore_block({"status": "LIVE", "evidence": "X 1", "tier": "FACT-T2", "asof": "2026-09-25",
                                   "src": "a/b"}, date(2026, 9, 27))
            self.assertEqual([n["_tier"] for n in walk(blk) if isinstance(n, dict) and "_tier" in n], ["FACT-T2"])

    def test_src_text_breaks(self):
        z = "\u200b"
        self.assertEqual(T._src_text("fincept_bridge/state/vc_lk/HPG/price-history.json"),
                         "fincept_bridge/" + z + "state/" + z + "vc_lk/" + z + "HPG/" + z + "price-history.json")
        self.assertEqual(T._src_text("tinnhanhchungkhoan.vn 13/08/2026; a / b"), "tinnhanhchungkhoan.vn 13/08/2026; a / b")
        with D.use_mode("live", "2026-09-27"):
            blk = T.rescore_block({"status": "LIVE", "evidence": "x", "tier": "E", "asof": "2026-09-27",
                                   "src": "vc_lk/A/b.json"}, date(2026, 9, 27))
        src = [n for n in walk(blk) if isinstance(n, dict) and text_of(n).startswith("nguồn: ")][0]
        self.assertNotIn("wordBreak", src["s"])                                  # không chẻ giữa từ/ngày
        self.assertEqual(src["s"]["color"], D.C.inkD)                           # tương phản ≥4,5 trên nền thẻ


FIXTURE = {
    "claims20": {"C03": {"status": "BỊ BÁC", "evidence": "HPG thủng 23K ngày 10/07 [CẦN DATA — TEU]", "tier": "FACT-T2",
                         "asof": "2026-07-20", "src": "vc_lk/HPG/price-history.json"},
                 "C02": {"status": "CHƯA RÕ", "evidence": "Tổ chức [CẦN DATA]", "tier": "FACT-T2", "asof": "2026-08-07",
                         "src": "vc_lk/TCB/price-history.json"}},
    "claims54": {"C09": {"status": "TIỀN ĐỀ SAI", "evidence": "TCX niêm yết 21/10/2025", "tier": "FACT-T2",
                         "asof": "2025-10-21", "src": "vnstore nen_ngay"},
                 "C01": {"status": "CHƯA RÕ", "evidence": "LPS lên HOSE 18/08", "tier": "UNVERIFIED", "asof": "2026-08-18",
                         "src": "báo chí"}},
    "changelog": {"fincept_2709": {"groups": [{"title": "◇ NGUỒN", "items": [
        {"text": "NN + tự doanh tới 25/09", "tier": "FACT-T2", "asof": "2026-09-25", "src": "vc_lk"}]}]}},
}


class LiveBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v21 = load_v21()
        with D.use_mode("live", "2026-09-27"):
            ctx = make_ctx("live", cls.v21, FIXTURE)
            cls.cl = T.build_changelog(ctx)
            cls.c54 = T.build_claims54(ctx)
            ctx0 = make_ctx("live", cls.v21, None)
            cls.cl0 = T.build_changelog(ctx0)


class TestLive(LiveBase):
    def test_claims54_today_recomputed(self):
        root = self.c54["root"]
        top = text_of(by_key(root, "c54.top"))
        self.assertIn("⚡ TOP ALERTS · ≤60 ngày (27/9/2026)", top)
        alerts = [n["key"][10:] for n in walk(root) if isinstance(n, dict) and str(n.get("key", "")).startswith("c54.alert:")]
        self.assertEqual(sorted(alerts), ["C01", "C26", "C38", "C39"])               # page_p7a §2.5
        self.assertIn("PAST13", top.replace("E", ""))
        self.assertIn("2026-09-30 · 3d left", text_of(by_key(root, "c54:C01")))

    def test_rescore_blocks(self):
        c03 = text_of(by_key(self.cl["root"], "cp:C03"))
        self.assertIn("CHẤM LẠI 27/09BỊ BÁC", c03)
        self.assertIn("[CẦN DATA — TEU]", c03)
        c02 = text_of(by_key(self.cl["root"], "cp:C02"))
        self.assertIn("CHƯA RÕHẾT HẠN", c02)                                       # horizon 09/08 đã qua → cờ HẾT HẠN
        self.assertIn("V21·12/05", c02)                                             # trạng thái V21 giữ + dấu
        c09 = text_of(by_key(self.c54["root"], "c54:C09"))
        self.assertIn("TIỀN ĐỀ SAI", c09)
        c05 = text_of(by_key(self.cl["root"], "cp:C05"))
        self.assertIn("[CẦN DATA — chưa có mục dossier chấm lại]", c05)
        fin = text_of(by_key(self.cl["root"], "cl.fincept"))
        self.assertIn("V21 → Fincept 27/09/2026", fin)
        self.assertIn("dữ liệu tới 25/09/2026", fin)
        self.assertIn("[CẦN DATA — chưa có dossier.changelog", text_of(by_key(self.cl0["root"], "cl.fincept")))

    def test_summary_tail_and_synthesis(self):
        summ = by_key(self.cl["root"], "cp.summary")
        tail = summ["k"][-1]
        self.assertEqual(tail["t"], "span")                                     # câu cuối + ↻ một flex item
        self.assertTrue(any(isinstance(n, dict) and n.get("_upd") for n in tail["k"]))
        self.assertIn(">5% NAV → Synthesis L1+L2+L3", text_of(summ))

    def test_disclaimer_live_no_personal_name(self):
        live = text_of(by_key(self.cl["root"], "src"))
        self.assertIn("Báo cáo này dành riêng cho người dùng nội bộ.", live)
        self.assertNotIn("Phạm Minh Tuấn", live)
        with D.use_mode("v21", "2026-09-27"):
            v21 = text_of(by_key(T.build_changelog(make_ctx("v21", self.v21))["root"], "src"))
        self.assertIn("dành riêng cho Phạm Minh Tuấn (PCVP BIDV).", v21)         # mode v21 giữ nguyên văn

    def test_thesis_person_caveat(self):
        doc = {"claims54": {"C52": {"status": "CHƯA RÕ", "evidence": "x", "tier": "UNVERIFIED", "asof": "2026-07-31",
                                    "src": "s", "th_caveat": "tên cá nhân — không hàm ý cáo buộc"}}}
        with D.use_mode("live", "2026-09-27"):
            root = T.build_claims54(make_ctx("live", self.v21, doc))["root"]
        card = by_key(root, "c54:C52")
        line = next(n for n in walk(card) if isinstance(n, dict) and "Thesis:" in "".join(
            text_of(k) for k in n.get("k", ()) if not isinstance(k, str) or True) and n["t"] == "div"
            and any(isinstance(k, dict) and text_of(k) == "Thesis:" for k in n.get("k", ())))
        self.assertTrue(any(is_label(k) and k.get("_tier") == "UNVERIFIED" for k in line["k"]))
        self.assertIn("(tên cá nhân — không hàm ý cáo buộc)", text_of(line))
        c03 = by_key(root, "c54:C03")                                             # không có th_caveat → như cũ
        self.assertNotIn("không hàm ý cáo buộc", text_of(c03))

    def test_pattern_q_outside_tv30(self):
        """Mã chủ thể ngoài 30 mã Toàn Vũ (C09 DGC) → 'Pattern A?' + chú thích; ACB (C06), MSN (C18, tk có MSR) giữ."""
        data = types.SimpleNamespace(tv30=lambda: ["ACB", "MSN", "VIC"])
        with D.use_mode("live", "2026-09-27"):
            ctx = make_ctx("live", self.v21, FIXTURE)
            ctx.data = data
            root = T.build_changelog(ctx)["root"]
        c09 = text_of(by_key(root, "cp:C09"))
        self.assertIn("DGC 3 BOD bị khởi tố — Pattern A? risk", c09)
        self.assertIn("giải đáp = governance discount tăng. Pattern A? nguy cơ cao", c09)
        self.assertNotRegex(c09, r"Pattern [A-D](?!\?)")
        self.assertIn("TK: DGC· '?' = DGC ngoài 30 mã Toàn Vũ, nhãn pattern là giả thuyết", c09)
        self.assertIn("= local FOMO Pattern A nhưng", text_of(by_key(root, "cp:C06")))
        c18 = text_of(by_key(root, "cp:C18"))
        self.assertIn("MSN Pattern B accumulationTK: MSN · MSR▶", c18)       # không có chú thích '?'
        self.assertIn("Cluster VWAP + Pattern B/A flow analysis", text_of(by_key(root, "cl")))   # câu phương pháp
        c06_nolist = text_of(by_key(self.cl["root"], "cp:C06"))                  # ctx.data None → không có danh sách
        self.assertIn("Pattern A? nhưng", c06_nolist)
        self.assertIn("· '?' = chưa đọc được danh sách 30 mã Toàn Vũ", c06_nolist)
        self.assertEqual(T.pattern_q("x Pattern B y", "ACB", set()), "x Pattern B? y")   # không có danh sách → '?'
        self.assertEqual(T.pattern_q("x Pattern B? y", "DGC", set()), "x Pattern B? y")
        with D.use_mode("v21", "2026-09-27"):
            self.assertEqual(T.pattern_q("x Pattern B y", "DGC", set()), "x Pattern B y")

    def test_states_same_as_v21(self):
        self.assertEqual([s["options"] for s in self.cl["states"]][1], ["ALL", "LIVE", "WATCH", "FAILED"])
        self.assertEqual(len(self.c54["states"][1]["options"]), 23)

    _SKIP = (re.compile(r"^(nguồn: |TK: |github\.com/|Showing |≤60d$|⚡ TOP ALERTS · ≤60 ngày|Big4 Banking$"
                        r"|— trạng thái V21 giữ ở đầu thẻ"          # câu phương pháp cuối dòng tổng (không phải số liệu)
                        r"|· '\?' = )"),                             # chú thích hậu tố '?' (định nghĩa, không số liệu)
             re.compile(r"^C\d\d( · [A-Z]+)?$"),
             re.compile(r"^\d{4}-\d{2}-\d{2}$"))
    _DATES = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}(/\d{4})?\b|\bV2\d\b")

    def _bare_numbers(self, root, block_prefixes):
        """Phần tử trong khối dữ liệu có chữ số ở con chữ trực tiếp mà không có nhãn bậc/[CẦN DATA]/dấu V21 là con
        trực tiếp. Loại trừ có chủ đích: mã claim, ngày hạn, chú thích nguồn, danh sách mã, bộ đếm UI."""
        bad = []
        blocks = [n for n in walk(root) if isinstance(n, dict) and str(n.get("key", "")).startswith(block_prefixes)]
        for b in blocks:
            for n in walk(b):
                if not isinstance(n, dict) or n.get("_tier") or n.get("_can") or n.get("_v21") or n.get("_upd"):
                    continue
                own = "".join(k for k in n.get("k", ()) if isinstance(k, str)).strip()
                if not own or any(p.search(own) for p in self._SKIP):
                    continue
                core = self._DATES.sub("", own)                  # ngày (dd/mm[/yyyy], ISO) và nhãn phiên bản V21/V22…
                if not re.search(r"\d", core):
                    continue
                if n["t"] in ("strong", "h2"):                   # nhãn in đậm / tiêu đề Section
                    continue
                if not any(is_label(k) or (isinstance(k, dict) and k.get("_v21")) for k in n.get("k", ())):
                    bad.append((b.get("key"), own[:60]))
        return bad

    def test_no_bare_numbers_in_live_claims(self):
        self.assertEqual(self._bare_numbers(self.cl["root"], ("cp:", "cp.summary", "cl.fincept")), [])
        self.assertEqual(self._bare_numbers(self.c54["root"], ("c54:", "c54.alert:", "c54.summary", "c54.top")), [])

    def test_no_bare_numbers_with_real_dossier(self):
        if not DOSSIER_PIECE.is_file():
            self.skipTest("chưa có mảnh dossier claims")
        doc = json.loads(DOSSIER_PIECE.read_text("utf-8"))
        with D.use_mode("live", "2026-09-27"):
            ctx = make_ctx("live", self.v21, doc)
            cl, c54 = T.build_changelog(ctx), T.build_claims54(ctx)
        self.assertEqual(self._bare_numbers(cl["root"], ("cp:", "cp.summary", "cl.fincept")), [])
        self.assertEqual(self._bare_numbers(c54["root"], ("c54:", "c54.alert:", "c54.summary", "c54.top")), [])
        for root in (cl["root"], c54["root"]):
            miss = [n["key"] for n in walk(root) if isinstance(n, dict) and str(n.get("key", "")).startswith(("cp:C", "c54:C"))
                    and "chưa có mục dossier" in text_of(n)]
            self.assertEqual(miss, [])                                              # đủ 20 + 54 mục chấm lại

    def test_block_labels_history_and_research(self):
        for key in ("cl", "meth", "src", "road"):
            sec = by_key(self.cl["root"], key)
            head = sec["k"][0]
            self.assertTrue(any(is_label(n) for n in walk(head)), key)            # nhãn U ở sub (khối chung nguồn)
            self.assertTrue(any(isinstance(n, dict) and n.get("_v21") for n in walk(head)), key)
        for t in self.v21["RESEARCH_STACK"]:
            card = by_key(self.cl["root"], "rs:" + t["name"])
            self.assertTrue(any(is_label(n) for n in walk(card)), t["name"])


class TestDossierPiece(unittest.TestCase):
    def test_piece_contract(self):
        if not DOSSIER_PIECE.is_file():
            self.skipTest("chưa có mảnh dossier claims")
        v21 = load_v21()
        doc = json.loads(DOSSIER_PIECE.read_text("utf-8"))
        self.assertEqual(doc["schema"], "chaebol_map_capnhat/1")
        self.assertEqual(set(doc["claims20"]), {c["id"] for c in v21["CLAIMS_C01_C20"]})
        self.assertEqual(set(doc["claims54"]), {c["id"] for c in v21["CLAIMS_54"]})
        for part in ("claims20", "claims54"):
            for cid, it in doc[part].items():
                self.assertIn(it["status"], STATUSES, cid)
                self.assertIn(it["tier"], TIERS, cid)
                self.assertTrue(it.get("src"), cid)
                date.fromisoformat(it["asof"])
                if it["tier"] == "UNVERIFIED":
                    self.assertNotIn(it["status"], ("ĐẠT", "BỊ BÁC"), cid)          # U → tối đa CHƯA RÕ
                self.assertNotRegex(it["evidence"], r"\b(MUA|BÁN) (VÀO|RA) NGAY\b")
        for g in doc["changelog"]["fincept_2709"]["groups"]:
            for it in g["items"]:
                self.assertTrue(it["src"] and it["tier"] in TIERS and it["asof"])
        # tiền đề sai đã biết: TCBS niêm yết 21/10/2025
        self.assertEqual(doc["claims54"]["C09"]["status"], "TIỀN ĐỀ SAI")
        self.assertEqual(doc["claims54"]["C25"]["status"], "TIỀN ĐỀ SAI")
        # sửa sau kiểm chứng 27/09 (tab_report_claims §9)
        want20 = {"C04": "CHƯA RÕ", "C05": "CHƯA RÕ", "C13": "TIỀN ĐỀ SAI", "C19": "TIỀN ĐỀ SAI", "C01": "HẾT HẠN"}
        want54 = {"C02": "TIỀN ĐỀ SAI", "C14": "BỊ BÁC", "C34": "TIỀN ĐỀ SAI", "C24": "BỊ BÁC"}
        for cid, st in want20.items():
            self.assertEqual(doc["claims20"][cid]["status"], st, cid)
        for cid, st in want54.items():
            self.assertEqual(doc["claims54"][cid]["status"], st, cid)
        # dòng tổng khớp đếm thật (meta + mục changelog)
        from collections import Counter
        for part in ("claims20", "claims54"):
            cnt = Counter(it["status"] for it in doc[part].values())
            self.assertEqual(doc["claims_meta"]["tong_hop"][part], {k: v for k, v in cnt.items()}, part)
        items = [i["text"] for g in doc["changelog"]["fincept_2709"]["groups"] for i in g["items"]]
        self.assertTrue(any(t.startswith("20 claim C01–C20") and "TIỀN ĐỀ SAI 4" in t for t in items))
        self.assertTrue(any(t.startswith("54 claim ưu tiên") and "TIỀN ĐỀ SAI 9" in t for t in items))
        # nhãn nội dòng hợp lệ; giá so mốc cũ đã quy đổi quyền ở các claim bị nêu
        tok = re.compile(r"\{([^}]*)\}")
        for part in ("claims20", "claims54"):
            for cid, it in doc[part].items():
                for t in tok.findall(it["evidence"]):
                    self.assertRegex(t, r"^(T1|T2|T3|E|U)(·\d{4}-\d{2}-\d{2})?$", cid)
        for cid, frag in (("C02", "33.104"), ("C03", "24.546"), ("C05", "71.524"), ("C07", "15.627"),
                          ("C19", "53.853")):
            self.assertIn(frag, doc["claims20"][cid]["evidence"], cid)
        self.assertNotIn("[CẦN DATA — OCF", doc["claims20"]["C07"]["evidence"])
        self.assertEqual(doc["claims20"]["C07"]["tier"], "FACT-T1")
        # vòng hoàn thiện 27/09 (final_check §6.1 #15): nợ xấu 6T VCB từ BCTC soát xét (T1), chưa tới hạn → LIVE
        c54 = doc["claims54"]["C54"]
        self.assertEqual((c54["status"], c54["tier"], c54["asof"]), ("LIVE", "FACT-T1", "2026-06-30"))
        self.assertNotIn("[CẦN DATA", c54["evidence"])
        for frag in ("10,736.5 tỷ", "1,758,168.1 tỷ{T1·2026-06-30}", "0.61%{E}", "≈0.86%{E}", "1.5%{T1·2026-04-24}"):
            self.assertIn(frag, c54["evidence"])
        self.assertIn("Soát_xét_6_tháng_đầu_năm_2026_558380.pdf", c54["src"])
        self.assertIn("https://www.vietcombank.com.vn/", c54["src"])
        self.assertEqual(c54["doi_chieu"]["tier"], "UNVERIFIED")                 # báo chí chỉ đối chiếu
        # bảng chất lượng nợ tr.34 (triệu VND, nhóm 1…5; tổng in trên trang 1.758.168.065) → số trong câu (en-US, §11.1)
        groups = (1742980001, 4451543, 1185589, 1226793, 8324139)
        self.assertEqual(sum(groups), 1758168065)
        npl = sum(groups[2:])
        self.assertIn(f"{npl / 1000:,.1f} tỷ", c54["evidence"])
        self.assertIn(f"{sum(groups) / 1000:,.1f} tỷ", c54["evidence"])
        self.assertIn(f"{npl / sum(groups) * 100:.2f}%", c54["evidence"])
        self.assertIn(f"≈{(npl + groups[1]) / sum(groups) * 100:.2f}%", c54["evidence"])


if __name__ == "__main__":
    unittest.main()
