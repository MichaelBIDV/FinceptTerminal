#!/usr/bin/env python3
"""
Tests for hhp_weekly.py (ĐỊNH GIÁ HHP · BẢN TUẦN reader + audit engine). Stdlib unittest only.

    cd fincept-qt/scripts && python3 -m unittest test_hhp_weekly -v

Every test runs the script as a subprocess with env overrides (HHP_WEEKLY_DIR, HHP_DATA_DIR,
HHP_TODAY), exactly as EconomicsService/PythonRunner would, and parses stdout strictly
(NaN/Infinity tokens rejected). RealIssueTest / TodayTest read copies of the two real issues
(12/09 and 14/09/2026) in a temp dir — so a newer issue saved into knowledge_os changes nothing —
and are skipped when they are absent; SyntheticTest builds throwaway dirs. Nothing is written
into knowledge_os.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "hhp_weekly.py")
sys.path.insert(0, HERE)

import hhp_weekly as hw  # noqa: E402

REAL_WEEKLY = hw.DEFAULT_WEEKLY_DIR
REAL_DATA = hw.DEFAULT_DATA_DIR
REAL_KYS = ("2026-09-12", "2026-09-14")
HAVE_REAL = all(os.path.isfile(os.path.join(REAL_WEEKLY, "hhp_weekly_%s.html" % k)) for k in REAL_KYS)
HAVE_LIVE = os.path.isfile(os.path.join(REAL_DATA, hw.VALUATION_FILE))

IHTML_CLASSES = ("z-floor|z-up|z-ref|z-down|z-ceil|tag|tag-f|tag-p|num|tk|v-hold|v-add|v-trim|"
                 "c-up|c-down|c-ref|c-muted|c-ink2|c-floor|c-ceil|sub|hl")
IHTML_TAG_RE = re.compile(r'<(b|i)>|</(b|i)>|<br>|<span class="(%s)">|</span>' % IHTML_CLASSES)
ENTITY_RE = re.compile(r"&(?:amp|lt|gt|quot|#x27|#\d+|#x[0-9a-fA-F]+);")
# payload keys whose string values are ihtml (contract); "chip" only inside cards
IHTML_KEYS = {"html", "sub", "chip", "caption", "lede", "status", "v"}


def _reject_constant(token):
    raise ValueError("non-finite JSON token on stdout: " + token)


def run_script(args, weekly_dir=REAL_WEEKLY, data_dir=REAL_DATA, today=None):
    """Run the script like the app does → (returncode, parsed object)."""
    env = dict(os.environ, HHP_WEEKLY_DIR=weekly_dir, HHP_DATA_DIR=data_dir)
    env.pop("HHP_TODAY", None)
    if today:
        env["HHP_TODAY"] = today
    proc = subprocess.run([sys.executable, SCRIPT] + list(args), capture_output=True, env=env, timeout=60)
    text = proc.stdout.decode("utf-8")
    return proc.returncode, json.loads(text, parse_constant=_reject_constant)


def real_issue_dir():
    """Temp dir with copies of the two real issues only (the real dir may already hold newer kỳ)."""
    d = tempfile.mkdtemp(prefix="hhp_weekly_real_")
    for k in REAL_KYS:
        shutil.copy(os.path.join(REAL_WEEKLY, "hhp_weekly_%s.html" % k), d)
    return d


def ihtml_problem(s):
    """None when s follows the contract's ihtml grammar, else a description of the first problem."""
    if "\n" in s or "\r" in s:
        return "newline"
    stack, pos = [], 0
    for m in re.finditer(r"<[^>]*>", s):
        text = s[pos:m.start()]
        pos = m.end()
        if ">" in text:
            return "raw '>' in text %r" % text
        if "&" in ENTITY_RE.sub("", text):
            return "bare '&' in text %r" % text
        tm = IHTML_TAG_RE.fullmatch(m.group(0))
        if not tm:
            return "tag not allowed: %s" % m.group(0)
        tag = m.group(0)
        if tag == "<br>":
            continue
        if tag.startswith("</"):
            name = "span" if tag == "</span>" else tag[2]
            if not stack or stack[-1] != name:
                return "unbalanced %s" % tag
            stack.pop()
        else:
            stack.append("span" if tag.startswith("<span") else tag[1])
    tail = s[pos:]
    if "<" in tail or ">" in tail:
        return "raw '<'/'>' in text %r" % tail
    if "&" in ENTITY_RE.sub("", tail):
        return "bare '&' in text %r" % tail
    return "unclosed %s" % stack if stack else None


def iter_ihtml(obj, path="$"):
    """Yield (path, string) for every ihtml string in a weekly payload."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = "%s.%s" % (path, k)
            if k in IHTML_KEYS and isinstance(v, str):
                yield p, v
            elif k == "items" and isinstance(v, list) and obj.get("t") == "list":
                for i, x in enumerate(v):
                    yield "%s[%d]" % (p, i), x
            else:
                yield from iter_ihtml(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_ihtml(v, "%s[%d]" % (path, i))


def iter_blocks(blocks):
    """Depth-first over blocks, descending into cards, card, advisor."""
    for b in blocks:
        yield b
        if b.get("t") == "cards":
            for c in b["cards"]:
                yield from iter_blocks(c["blocks"])
        elif b.get("t") in ("card", "advisor"):
            yield from iter_blocks(b["blocks"])


def all_blocks(payload):
    for s in payload["issue"]["sections"]:
        yield from iter_blocks(s["blocks"])
    yield from iter_blocks(payload["issue"]["footer"])


def kiem(payload, prefix):
    return [k for k in payload["engine"]["kiem"] if k["muc"].startswith(prefix)]


SECTIONS_12 = ["00", "00B", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11"]
TITLES = {"00": "Tuần 07–11/09 đã đổi những gì", "03": "Vùng giá σ — chart đặc trưng của phương pháp",
          "08": "Hội đồng cố vấn — FPT · MSN · VCB", "11": "Tự chấm điểm — 6 chiều rigor"}


@unittest.skipUnless(HAVE_REAL, "real weekly issues not present")
class RealIssueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wdir = real_issue_dir()
        cls.w14 = run_script(["weekly", "2026-09-14"], weekly_dir=cls.wdir, today="2026-09-23")[1]
        cls.w12 = run_script(["weekly", "2026-09-12"], weekly_dir=cls.wdir, today="2026-09-23")[1]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.wdir, ignore_errors=True)

    def test_no_error_no_warning(self):
        for p in (self.w14, self.w12):
            self.assertNotIn("error", p)
            self.assertEqual(p["meta"]["warnings"], [])

    def test_sections_in_order(self):
        ids14 = [s["id"] for s in self.w14["issue"]["sections"]]
        ids12 = [s["id"] for s in self.w12["issue"]["sections"]]
        self.assertEqual(ids14, ["00A"] + SECTIONS_12)
        self.assertEqual(ids12, SECTIONS_12)
        self.assertNotIn("00A", ids12)
        for p in (self.w14, self.w12):
            titles = {s["id"]: s["title"] for s in p["issue"]["sections"]}
            for sid, title in TITLES.items():
                self.assertEqual(titles[sid], title)
        self.assertEqual(self.w14["issue"]["sections"][0]["title"], "Kỳ 14/09 — hai báo cáo HSC cùng ngày đọc ngược nhau")

    def test_masthead(self):
        iss = self.w14["issue"]
        self.assertEqual(iss["title"], "Ba chiếc đồng hồ của thị trường\nđang chỉ mấy giờ?")
        self.assertEqual(iss["kicker"][-1], "Hội đồng cố vấn AI · Bản tuần · rev.3")
        self.assertEqual(self.w14["meta"]["rev"], "rev.3")
        self.assertIsNone(self.w12["meta"]["rev"])
        tiers = [c["tier"] for c in iss["chips"]]
        self.assertIn("SS-T3", tiers)
        self.assertIn("FACT-T1", tiers)
        self.assertEqual([s["label"] for s in iss["stats"]][:4],
                         ["VN-Index P/E", "Loại họ Vin", "Độ rộng định giá P/E", "Họ Vin chiếm"])
        self.assertEqual(iss["stats"][2]["value"], "42 / 128 / 23")
        for p in (self.w14, self.w12):
            self.assertEqual(p["meta"]["data_as_of"], "2026-09-11")
            self.assertEqual(p["meta"]["engine_run"], "2026-09-12 15:43 ICT")
        self.assertEqual(len(self.w14["meta"]["links"]), 2)

    def test_advisors(self):
        for p in (self.w14, self.w12):
            adv = [(a["ticker"], a["verdict"], a["verdict_class"]) for a in p["core"]["advisors"]]
            self.assertEqual(adv, [("FPT", "HOLD 12%", "hold"), ("MSN", "TRIM → 5%", "trim"),
                                   ("VCB", "ADD → 10%", "add")])
            blocks = [b for b in all_blocks(p) if b["t"] == "advisor"]
            self.assertEqual([b["ticker"] for b in blocks], ["FPT", "MSN", "VCB"])
            for b in blocks:
                voices = [x for x in b["blocks"] if x["t"] == "voice"]
                self.assertEqual([v["side"] for v in voices], ["kill"] * 3 + ["alpha"] * 3)
                self.assertTrue(b["blocks"][0]["bold"])

    def test_bands_verbatim(self):
        bands = [b for b in all_blocks(self.w14) if b["t"] == "band"]
        self.assertEqual([(b["ticker"], b["metric"]) for b in bands], [("VCB", "P/E"), ("FPT", "P/E"), ("MSN", "P/B")])
        vcb = bands[0]
        self.assertEqual([vcb[k] for k in ("cheap2", "cheap1", "fair", "rich1", "rich2", "price")],
                         [65031, 75900, 86769, 97638, 108507, 62200])
        self.assertEqual(vcb["label"], "Dải định giá PE: rẻ 65 031–75 900, hợp lý 86 769, đắt 97 638–108 507, "
                                       "giá hiện tại 62 200")
        if HAVE_LIVE:
            self.assertIsNotNone(vcb["live"])
            self.assertIn(vcb["live"]["zone_key"], ("cheap", "neutral", "rich"))

    def test_band_card_chip(self):
        cards = [c for b in all_blocks(self.w14) if b["t"] == "cards" for c in b["cards"]]
        vcb = next(c for c in cards if c["title"].startswith("VCB "))
        self.assertEqual(vcb["title"], "VCB PE 11,68× · μ 16,29×")
        self.assertEqual(vcb["chip"], '<span class="z-floor">-2,26σ RẺ SÂU</span>')

    def test_dist(self):
        dist = [b for b in all_blocks(self.w14) if b["t"] == "dist"]
        self.assertEqual(len(dist), 1)
        d = dist[0]
        self.assertEqual(d["issue"]["n"], 189)  # the page's own count ("Phân bố σ … của 189 mã")
        self.assertEqual(d["issue"]["as_of"], "11/09/2026")
        self.assertTrue(d["caption"].startswith("Mỗi vạch = 1 mã"))
        mine = set(self.w14["core"]["mine"])
        self.assertTrue(mine.issubset(set(d["labels"])))
        self.assertTrue(all(p["mine"] == (p["tk"] in mine) for p in d["issue"]["points"]))

    def test_snapshot(self):
        for p in (self.w14, self.w12):
            snap = p["snapshot"]
            self.assertEqual(snap["n"], 194)
            self.assertEqual(len(snap["rows"]), 194)
            self.assertEqual(snap["as_of_txt"], "11/09/2026")
            self.assertEqual(len(p["core"]["mine"]), 11)
            self.assertEqual(len(p["core"]["avoid"]), 8)
            row = next(r for r in snap["rows"] if r["t"] == "FPT")
            self.assertEqual(row["pe"][0], 12.39)
            self.assertEqual(len(p["csv"]["rows"]), 194)
            self.assertEqual(len(p["csv"]["columns"]), 12)
            self.assertTrue(all(len(r) == 12 for r in p["csv"]["rows"]))
        screener = [b for b in all_blocks(self.w14) if b["t"] == "screener"]
        self.assertEqual(len(screener), 1)

    def test_rigor_recomputed(self):
        r14 = self.w14["core"]["rigor"]
        self.assertEqual([(r["section"], r["printed_src"]) for r in r14],
                         [("00A", "row"), ("11", "caption"), ("11", "row")])
        self.assertEqual([r["calc_avg_txt"] for r in r14], [["4,67", "4,33"], ["4,5", "4,67"], ["4,3"]])
        self.assertEqual(len(self.w12["core"]["rigor"]), 2)
        for p in (self.w14, self.w12):
            lines = kiem(p, "Rigor ")
            self.assertEqual(len(lines), len(p["core"]["rigor"]))
            self.assertTrue(all(k["ok"] is True for k in lines))
            for r in p["core"]["rigor"]:
                self.assertEqual(len(r["dims"]), 6)
                for k, avg in enumerate(r["calc_avg"]):
                    scores = [d["scores"][k] for d in r["dims"]]
                    self.assertAlmostEqual(avg, sum(scores) / len(scores))

    def test_portfolio_sum(self):
        for p in (self.w14, self.w12):
            pf = p["core"]["portfolio"]
            self.assertEqual([i["name"] for i in pf["items"]],
                             ["VCB", "FPT", "MSN", "ACB", "GAS", "HPG", "TCB", "CTG", "GEX", "VRE", "PLX", "tiền mặt"])
            self.assertEqual(pf["sum"], 81.0)  # 65% in 11 tickers + 16% cash — the issue does not add to 100
            line = kiem(p, "Danh mục tham chiếu")[0]
            self.assertIs(line["ok"], False)
            self.assertIn("81%", line["text"])

    def test_breadth_recount(self):
        for p in (self.w14, self.w12):
            counts = {}
            for key in ("pe", "pb"):
                c = [0, 0, 0]
                for r in p["snapshot"]["rows"]:
                    z = hw.label_zone(r[key][3])
                    if z:
                        c[["cheap", "neutral", "rich"].index(z)] += 1
                counts[key] = c
            printed = ([42, 128, 23], [57, 117, 20])
            line = kiem(p, "Độ rộng")[0]
            self.assertIn("P/E %s" % " / ".join(map(str, counts["pe"])), line["text"])
            self.assertIs(line["ok"], (counts["pe"], counts["pb"]) == printed)

    def test_ihtml_grammar(self):
        for p in (self.w14, self.w12):
            n = 0
            for path, s in iter_ihtml(p):
                n += 1
                self.assertIsNone(ihtml_problem(s), "%s: %r" % (path, s[:200]))
            self.assertGreater(n, 500)

    def test_kiem_order(self):
        order = [k["muc"] for k in self.w14["engine"]["kiem"]]
        self.assertEqual(order[:3], ["Tuổi bản tuần", "Vintage định giá", "Độ rộng (đếm lại)"])
        pos = {m: i for i, m in enumerate(order)}
        self.assertLess(pos["Rigor T22"], pos["Danh mục tham chiếu"])
        self.assertLess(pos["Danh mục tham chiếu"], pos["Mốc đã qua"])
        self.assertEqual(order[-1], "Drift so với live")

    def test_levels(self):
        levels = self.w14["engine"]["levels"]
        vals = [lv["level"] for lv in levels]
        self.assertIn(1726.0, vals)
        self.assertIn(1788.0, vals)
        self.assertIn(1791.0, vals)
        # 00A T6 "thay 1.820 bằng MA200 1.788–1.791" retires 1.820 for the whole issue, even though the
        # older 00B row "Thêm chốt chặn kỹ thuật 1.820 …" is read after it
        self.assertNotIn(1820.0, vals)
        self.assertNotIn("1.820", kiem(self.w14, "Mức chỉ số")[0]["text"])
        self.assertEqual(len(vals), len(set(vals)))
        self.assertTrue(all(len(lv["context"]) <= hw.TEXT_MAX for lv in levels))
        if HAVE_LIVE:
            self.assertTrue(all(lv["side"] in ("trên", "dưới") for lv in levels))

    def test_tickers_and_baskets(self):
        e = self.w14["engine"]
        tks = [t["tk"] for t in e["tickers"]]
        self.assertEqual(tks[:11], self.w14["core"]["mine"])
        self.assertEqual(next(t for t in e["tickers"] if t["tk"] == "FPT")["pe_issue_txt"], "12,39× · −0,79σ")
        self.assertEqual(len(e["baskets"]), 17)
        self.assertEqual(e["baskets"][0]["code"], "VNINDEX")
        self.assertEqual(e["baskets"][0]["pe_issue_txt"], "−0,77σ")
        tables = [b for b in all_blocks(self.w14) if b["t"] == "table"]
        kinds = {b["id"]: b["kind"] for b in tables}
        self.assertEqual(kinds["T15"], "basket")
        self.assertEqual(kinds["T16"], "cheap")
        self.assertNotIn("T17", kinds)  # the screener table keeps its number but is a screener block
        self.assertTrue(next(b for b in tables if b["id"] == "T16")["scroll"])


@unittest.skipUnless(HAVE_REAL, "real weekly issues not present")
class TodayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wdir = real_issue_dir()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.wdir, ignore_errors=True)

    def run_real(self, args, today=None):
        return run_script(args, weekly_dir=self.wdir, today=today)

    def test_age_stale_past(self):
        p = self.run_real(["weekly", "2026-09-14"], today="2026-09-23")[1]
        m = p["meta"]
        self.assertEqual(m["age_days"], 9)
        self.assertIs(m["stale"], True)
        self.assertEqual(m["next_due"], "2026-09-21")
        self.assertEqual(m["stale_text"], "BẢN TUẦN CŨ 9 ngày — kỳ 21/09 chưa có")
        past = p["engine"]["past"]
        self.assertIn("18/09", [x["date"] for x in past])
        self.assertIn("21/09", [x["date"] for x in past])
        stat = next(s for s in p["issue"]["stats"] if s["label"].startswith("Tuần sự kiện"))
        self.assertEqual(stat["live"]["text"], "đã qua (hôm nay 23/09)")

    def test_fresh_issue(self):
        p = self.run_real(["weekly", "2026-09-14"], today="2026-09-15")[1]
        self.assertEqual(p["meta"]["age_days"], 1)
        self.assertIs(p["meta"]["stale"], False)
        self.assertEqual(p["meta"]["stale_text"], "")
        self.assertEqual(p["engine"]["past"], [])
        self.assertIs(kiem(p, "Tuổi bản tuần")[0]["ok"], True)

    def test_older_issue_points_to_newer(self):
        p = self.run_real(["weekly", "2026-09-12"], today="2026-09-23")[1]
        self.assertIn("14/09/2026", p["meta"]["stale_text"])

    def test_issues_and_brief(self):
        rc, out = self.run_real(["issues"])
        self.assertEqual(rc, 0)
        self.assertEqual(out["issues"], ["2026-09-14", "2026-09-12"])
        rc, b = self.run_real(["brief"], today="2026-09-23")
        self.assertEqual(b["ky"], "2026-09-14")
        self.assertEqual(b["rev"], "rev.3")
        self.assertEqual(len(b["mine"]), 11)
        self.assertEqual(len(b["avoid"]), 8)
        self.assertEqual([a["ticker"] for a in b["advisors"]], ["FPT", "MSN", "VCB"])
        self.assertIs(b["stale"], True)


class SyntheticTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hhp_weekly_test_")
        self.wdir = os.path.join(self.tmp, "weekly")
        os.makedirs(self.wdir)
        self.nodata = os.path.join(self.tmp, "no_data")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_tmp(self, args, today="2026-09-23", data_dir=None):
        return run_script(args, weekly_dir=self.wdir, data_dir=data_dir or self.nodata, today=today)

    def write_page(self, body, script="", footer="chốt phiên 11/09/2026"):
        """A minimal issue page (kỳ 14/09/2026) around section markup `body`."""
        page = ('<html><body><div class="wrap"><header class="mast"><h1>T</h1></header>%s<footer><p>%s</p></footer>'
                '<script>%s</script></div></body></html>' % (body, footer, script))
        with open(os.path.join(self.wdir, "hhp_weekly_2026-09-14.html"), "w", encoding="utf-8") as fh:
            fh.write(page)

    def write_live(self, valuation, baskets=None):
        ddir = os.path.join(self.tmp, "data")
        os.makedirs(ddir, exist_ok=True)
        for name, obj in ((hw.VALUATION_FILE, valuation), (hw.BASKETS_FILE, baskets)):
            if obj is not None:
                with open(os.path.join(ddir, name), "w", encoding="utf-8") as fh:
                    json.dump(obj, fh)
        return ddir

    @staticmethod
    def section(n, inner):
        return '<section><div class="sechead"><span class="n">%s</span><h2>S</h2></div>%s</section>' % (n, inner)

    def weekly_ok(self, data_dir=None):
        rc, p = self.run_tmp(["weekly"], data_dir=data_dir)
        self.assertEqual(rc, 0)
        self.assertNotIn("error", p, p.get("error"))
        return p

    def test_empty_dir(self):
        rc, out = self.run_tmp(["weekly"])
        self.assertEqual(rc, 0)
        self.assertEqual(out["error_code"], "NO_ISSUE")
        self.assertIn("hhp_weekly_YYYY-MM-DD.html", out["error"])
        self.assertEqual(self.run_tmp(["issues"])[1]["issues"], [])
        b = self.run_tmp(["brief"])[1]
        self.assertIsNone(b["ky"])
        self.assertEqual(b["advisors"], [])
        self.assertNotIn("error", b)

    def test_bad_args(self):
        for args in (["weekly", "2026-13-45"], ["weekly", "14/09/2026"], ["weekly", "2026-09-14", "x"], ["nope"], []):
            rc, out = self.run_tmp(args)
            self.assertEqual(rc, 0)
            self.assertEqual(out["error_code"], "BAD_ARGS", args)

    def test_absent_ky(self):
        with open(os.path.join(self.wdir, "hhp_weekly_2026-09-14.html"), "w", encoding="utf-8") as fh:
            fh.write("<html><body></body></html>")
        rc, out = self.run_tmp(["weekly", "2026-09-07"])
        self.assertEqual(out["error_code"], "NO_ISSUE")
        self.assertIn("2026-09-14", out["error"])

    @unittest.skipUnless(HAVE_REAL, "real weekly issues not present")
    def test_missing_live_data(self):
        shutil.copy(os.path.join(REAL_WEEKLY, "hhp_weekly_2026-09-14.html"), self.wdir)
        rc, p = self.run_tmp(["weekly"])
        self.assertNotIn("error", p)
        self.assertIsNone(p["snapshot"]["live"])
        self.assertIsNone(p["meta"]["live_as_of"])
        self.assertTrue(any(hw.VALUATION_FILE in w for w in p["meta"]["warnings"]))
        bands = [b for b in all_blocks(p) if b["t"] == "band"]
        self.assertEqual(len(bands), 3)
        self.assertTrue(all(b["live"] is None for b in bands))
        self.assertTrue(all(b["live"] is None for b in all_blocks(p) if b["t"] == "dist"))
        self.assertTrue(all(s["live"] is None or s["live"]["text"].startswith("đã qua") for s in p["issue"]["stats"]))
        self.assertIsNone(kiem(p, "Drift so với live")[0]["ok"])
        self.assertEqual(p["snapshot"]["n"], 194)

    @unittest.skipUnless(HAVE_REAL, "real weekly issues not present")
    def test_truncated_html(self):
        with open(os.path.join(REAL_WEEKLY, "hhp_weekly_2026-09-14.html"), "r", encoding="utf-8") as fh:
            src = fh.read()
        cut = src.find('<section><div class="sechead"><span class="n">05')
        self.assertGreater(cut, 0)
        for text in (src[: cut + 3000], src[: len(src) // 3], src[:5000], "<html><body><div class=wrap><sec"):
            with open(os.path.join(self.wdir, "hhp_weekly_2026-09-14.html"), "w", encoding="utf-8") as fh:
                fh.write(text)
            rc, p = self.run_tmp(["weekly"])
            self.assertEqual(rc, 0)
            self.assertNotIn("error", p, p.get("error"))
            self.assertTrue(p["meta"]["warnings"], "no warning for truncated page of %d chars" % len(text))
            for path, s in iter_ihtml(p):
                self.assertIsNone(ihtml_problem(s), "%s: %r" % (path, s[:200]))

    def test_hostile_markup_is_escaped(self):
        page = ('<html><body><div class="wrap"><header class="mast"><h1>T<br>x</h1>'
                '<p class="lede">a <script>alert(1)</script><img src=x onerror=y> <a href="javascript:x">&lt;b&gt;'
                'link</a> <span class="z z-up" style="color:red">z</span> & "q"</p></header>'
                '<section><div class="sechead"><span class="n">01</span><h2>S</h2></div>'
                '<p>Brent <90 <u>u</u> <span style="color:var(--down)">d</span></p>'
                '<div class="tw"><table><thead><tr><th class="l">Việc</th></tr></thead><tbody>'
                '<tr><td class="l">01/01 <div>sub</div></td></tr></tbody></table></div></section>'
                '</div></body></html>')
        with open(os.path.join(self.wdir, "hhp_weekly_2026-09-14.html"), "w", encoding="utf-8") as fh:
            fh.write(page)
        rc, p = self.run_tmp(["weekly"])
        self.assertNotIn("error", p)
        for path, s in iter_ihtml(p):
            self.assertIsNone(ihtml_problem(s), "%s: %r" % (path, s))
        self.assertEqual(p["issue"]["title"], "T\nx")
        self.assertEqual(p["issue"]["lede"], 'a &lt;b&gt;link <span class="z-up">z</span> &amp; &quot;q&quot;')
        blocks = p["issue"]["sections"][0]["blocks"]
        self.assertEqual(blocks[0]["html"], 'Brent &lt;90 u <span class="c-down">d</span>')
        self.assertEqual(blocks[1]["rows"][0]["cells"][0]["html"], '01/01<br><span class="sub">sub</span>')
        self.assertEqual(blocks[1]["kind"], "action")

    def test_implied_end_tags(self):
        # valid HTML5 that omits the optional </p> </th> </td> </tr> </li>
        self.write_page(self.section("01", (
            '<p>Intro<p>Đoạn hai<div class="tw"><table><thead><tr><th class="l">Việc<th class="l">A<th>B'
            '</thead><tbody><tr><td class="l">01/09 việc một<td>x<td>y<tr><td class="l">02/09 việc hai<td>x2<td>y2'
            '</tbody></table></div><ul><li>một<li>hai</ul>')))
        p = self.weekly_ok()
        blocks = p["issue"]["sections"][0]["blocks"]
        self.assertEqual([b["t"] for b in blocks], ["p", "p", "table", "list"])
        self.assertEqual([b["html"] for b in blocks[:2]], ["Intro", "Đoạn hai"])
        t = blocks[2]
        self.assertEqual(t["kind"], "action")
        self.assertEqual([h["text"] for h in t["head"]], ["Việc", "A", "B"])
        self.assertEqual([[c["html"] for c in r["cells"]] for r in t["rows"]],
                         [["01/09 việc một", "x", "y"], ["02/09 việc hai", "x2", "y2"]])
        self.assertEqual(blocks[3]["items"], ["một", "hai"])
        self.assertEqual([x["date"] for x in p["engine"]["past"]], ["01/09", "02/09"])
        self.assertFalse([w for w in p["meta"]["warnings"] if "cắt cụt" in w])

    def test_long_table_without_end_tags(self):
        rows = "".join('<tr><td class="l">Việc %d<td>%d<td>x' % (i, i) for i in range(400))
        self.write_page(self.section("01", '<table><thead><tr><th class="l">Việc<th>N<th>X<tbody>%s</table>' % rows))
        p = self.weekly_ok()
        t = p["issue"]["sections"][0]["blocks"][0]
        self.assertEqual(len(t["rows"]), 400)
        self.assertEqual([c["html"] for c in t["rows"][399]["cells"]], ["Việc 399", "399", "x"])

    def test_deep_nesting_degrades_to_warning(self):
        deep_div = "<div>" * 3000 + "chữ sâu" + "</div>" * 3000
        deep_span = "<p>" + "<span>" * 3000 + "chữ trong span" + "</span>" * 3000 + "</p>"
        self.write_page(self.section("01", deep_div) + self.section("02", deep_span))
        p = self.weekly_ok()
        s1, s2 = p["issue"]["sections"]
        self.assertTrue([w for w in p["meta"]["warnings"] if "Mục 01" in w and "quá sâu" in w], p["meta"]["warnings"])
        self.assertEqual(s1["blocks"][0]["t"], "p")
        self.assertIn("chữ sâu", s1["blocks"][0]["html"])
        self.assertEqual(s2["blocks"][0]["html"], "chữ trong span")

    RIGOR_ROWS = [("Dữ liệu", "4,5", "5"), ("Phương pháp", "4,5", "4,5"), ("Nguồn", "4", "4,5"),
                  ("Phản biện", "5", "5"), ("Rủi ro", "4,5", "4"), ("Hành động", "4,5", "4,5")]

    @staticmethod
    def rigor_table(head, rows, avg=None):
        body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % c for c in r) for r in rows + ([avg] if avg else []))
        return "<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (head, body)

    def test_rigor_head_narrower_than_rows(self):
        avg = ("Trung bình", "4,5", "4,58")
        for head, cols in (('<th class="l">Chiều</th><th class="l" colspan="2">Điểm</th>', ["Điểm", "Điểm"]),
                           ('<th class="l">Chiều</th><th class="l">Điểm</th>', ["Điểm", ""])):
            with self.subTest(head=head):
                self.write_page(self.section("11", self.rigor_table(head, self.RIGOR_ROWS, avg)))
                p = self.weekly_ok()
                r = p["core"]["rigor"][0]
                self.assertEqual(r["cols"], cols)
                self.assertEqual(r["calc_avg_txt"], ["4,5", "4,58"])
                self.assertIs(kiem(p, "Rigor ")[0]["ok"], True)
                self.assertEqual(self.run_tmp(["brief"])[1].get("ky"), "2026-09-14")

    def test_rigor_average_exact_decimal(self):
        # exact mean 24,9 / 6 = 4,15 → the printed 4,2 is right (float sum/len = 4,1499999… → 4,1)
        rows = [("Chiều %d" % i, v) for i, v in enumerate(("4,2", "3,9", "4,6", "5,0", "3,7", "3,5"))]
        self.write_page(self.section("11", self.rigor_table('<th class="l">Chiều</th><th>Điểm</th>', rows,
                                                            ("Trung bình", "4,2"))))
        p = self.weekly_ok()
        self.assertEqual(p["core"]["rigor"][0]["calc_avg_txt"], ["4,2"])
        line = kiem(p, "Rigor ")[0]
        self.assertIs(line["ok"], True, line["text"])

    def test_levels_replaced_anywhere(self):
        head = '<thead><tr><th class="l">Việc</th><th class="l">Chi tiết</th></tr></thead>'
        older = '<tr><td class="l">Chốt chặn</td><td class="l">Thêm chốt chặn kỹ thuật 1.820 bên cạnh 1.726</td></tr>'
        newer = '<tr><td class="l">Mốc</td><td class="l">Mốc kỹ thuật: thay 1.820 bằng MA200 1.788–1.791</td></tr>'
        # the older row sits in the FIRST table, so it is read before the "thay 1.820" sentence
        self.write_page(self.section("00B", "<table>%s<tbody>%s</tbody></table>" % (head, older))
                        + self.section("01", "<table>%s<tbody>%s</tbody></table>" % (head, newer)))
        p = self.weekly_ok()
        self.assertEqual([lv["level"] for lv in p["engine"]["levels"]], [1726.0, 1788.0, 1791.0])
        self.assertNotIn("1.820", kiem(p, "Mức chỉ số")[0]["text"])

    def test_portfolio_items_with_trailing_text(self):
        cases = [
            ('<table><tbody><tr><td class="l">Danh mục tham chiếu hiện là VCB 10% · FPT 12% · tiền mặt 78%</td>'
             '<td class="l">Việc cần làm tiếp.</td></tr></tbody></table>', True),
            ("<p>(Danh mục tham chiếu hiện là VCB 10% · FPT 12% · tiền mặt 78%). Hết.</p>", True),
            ("<p>Danh mục tham chiếu hiện là VCB 10% · FPT 12% (giữ) · tiền mặt 78%.</p>", True),
            ("<p>Danh mục tham chiếu hiện là VCB 10%, FPT 12%, tiền mặt 78%.</p>", None),
        ]
        for body, ok in cases:
            with self.subTest(body=body):
                self.write_page(self.section("01", body))
                p = self.weekly_ok()
                line = kiem(p, "Danh mục tham chiếu")[0]
                self.assertIs(line["ok"], ok, line["text"])
                if ok:
                    pf = p["core"]["portfolio"]
                    self.assertEqual([(i["name"], i["pct"]) for i in pf["items"]],
                                     [("VCB", 10.0), ("FPT", 12.0), ("tiền mặt", 78.0)])
                    self.assertEqual(pf["sum_txt"], "100%")
                    self.assertIn("2 mã + tiền mặt 78%", line["text"])
                else:
                    self.assertIn("[CẦN DATA]", line["text"])
                    self.assertTrue([w for w in p["meta"]["warnings"] if "Danh mục tham chiếu" in w])

    SNAP_SCRIPT = ('var D=[{"t":"VCB","p":62200,"pe":[11.68,16.29,-2.26,"RẺ (<−1σ)",true,null,null],'
                   '"pb":[1.9,2.1,-0.5,"TRUNG TÍNH",true,null,null]}],MINE=["VCB"],AV=[];')
    LIVE_BASE = {"meta": {"generated": "2026-09-23T06:00:00+07:00"},
                 "index": {"pe": {"now": 12.5, "sigma": -1.2, "as_of": "2026-09-22", "price_now": 1810.0}},
                 "exvic3": {"pe_exv3_now": 10.6, "exv3_pe_sigma": -1.9}}

    def test_drift_nothing_compared_is_not_ok(self):
        self.write_page(self.section("01", "<p>x</p>"), script=self.SNAP_SCRIPT)
        line = kiem(self.weekly_ok(self.write_live(self.LIVE_BASE)), "Drift so với live")[0]  # no by_ticker
        self.assertIsNone(line["ok"], line["text"])
        self.assertIn("VCB", line["text"])
        self.assertIn("[CẦN DATA]", line["text"])
        live = dict(self.LIVE_BASE, by_ticker={"VCB": {"pe": {"now": 11.9, "sigma": -2.1, "reliable": True},
                                                       "pb": {"now": 1.9, "sigma": -0.4, "reliable": True}}})
        line = kiem(self.weekly_ok(self.write_live(live)), "Drift so với live")[0]
        self.assertIs(line["ok"], True, line["text"])
        self.assertTrue(line["text"].startswith("0 mã danh mục đổi vùng"))

    def test_live_json_odd_shapes_warn(self):
        head = '<thead><tr><th class="l">Việc</th></tr></thead>'
        self.write_page(self.section("01", '<table>%s<tbody><tr><td class="l">Giữ hỗ trợ 1.726</td></tr></tbody>'
                                           '</table>' % head))
        val = json.loads(json.dumps(self.LIVE_BASE))
        val["index"]["pe"]["chart"] = {"price": [[1790035200000, 1800.0], [1e18, 1805.0]]}
        p = self.weekly_ok(self.write_live(val, baskets={"baskets": 5}))
        warns = p["meta"]["warnings"]
        self.assertTrue([w for w in warns if hw.BASKETS_FILE in w], warns)
        self.assertTrue([w for w in warns if "thời điểm" in w], warns)
        self.assertEqual(p["engine"]["levels"][0]["live_txt"], "1.810,0 (22/09)")  # price_now / as_of fallback

    BAND_CARD = ('<div class="grid2 g2"><div class="card"><h3>VCB PE</h3><svg role="img" aria-label="Dải định giá PE: '
                 'rẻ 65 031–75 900, hợp lý 86 769, đắt 97 638–108 507, giá hiện tại 62 200"></svg></div></div>')

    def test_band_live_as_of_is_price_date(self):
        self.write_page(self.section("03", self.BAND_CARD))
        vcb = {"price_now": 66000, "pe": {"now": 11.9, "sigma": -2.1, "reliable": True, "band_cheap2": 64000,
                                          "band_cheap1": 75000, "band_fair": 86000, "band_rich1": 97000,
                                          "band_rich2": 108000}}
        # the live row is labelled with the date of the price it shows; no price_date → the index as_of (22/09)
        for price_date, as_of in (("2026-09-23", "23/09/2026"), (None, "22/09/2026"), ("bad", "22/09/2026")):
            with self.subTest(price_date=price_date):
                live = dict(self.LIVE_BASE, by_ticker={"VCB": dict(vcb, price_date=price_date)})
                band = next(b for b in all_blocks(self.weekly_ok(self.write_live(live))) if b["t"] == "band")
                self.assertEqual((band["ticker"], band["price"]), ("VCB", 62200))  # issue value untouched
                self.assertEqual((band["live"]["price"], band["live"]["fair"]), (66000, 86000))
                self.assertEqual(band["live"]["as_of"], as_of)

    def test_vintage_live_older_than_issue(self):
        self.write_page(self.section("01", "<p>x</p>"))
        for as_of, part, ok in (("2026-09-08", "cũ hơn 3 ngày", False), ("2026-09-11", "cùng ngày chốt", None),
                                ("2026-09-22", "mới hơn 11 ngày", None)):
            with self.subTest(as_of=as_of):
                val = json.loads(json.dumps(self.LIVE_BASE))
                val["index"]["pe"]["as_of"] = as_of
                line = kiem(self.weekly_ok(self.write_live(val)), "Vintage định giá")[0]
                self.assertIn(part, line["text"])
                self.assertNotIn("-", line["text"].split("live chốt")[1])
                self.assertIs(line["ok"], ok)


class UnitTest(unittest.TestCase):
    def test_vn_numbers(self):
        self.assertEqual(hw.vn_num("chỉ số 1 795,2"), (1795.2, 1))
        self.assertEqual(hw.vn_num("1.795,2")[0], 1795.2)
        self.assertEqual(hw.vn_num("1 795,2")[0], 1795.2)
        self.assertEqual(hw.vn_num("12,4×"), (12.4, 1))
        self.assertEqual(hw.vn_sigma("-1,36σ"), -1.36)
        self.assertEqual(hw.vn_sigma("−1,36σ"), -1.36)
        self.assertEqual(hw.vn_num("4,3 / 5"), (4.3, 1))

    def test_format(self):
        self.assertEqual(hw.fmt_dec(1816.9, 1), "1.816,9")
        self.assertEqual(hw.fmt_dec(-0.79), "−0,79")
        self.assertEqual(hw.fmt_dec(0.531, 2, sign=True), "+0,53")
        self.assertEqual(hw.fmt_dec(-0.001, 2), "0,00")
        self.assertEqual(hw.fmt_dec(None), "—")
        self.assertEqual(hw.fmt_trim(10.6), "10,6")
        self.assertEqual(hw.fmt_dec(4.665, 2), "4,67")  # half-up, not banker's rounding

    def test_levels_and_dates(self):
        self.assertEqual([v for v, _a, _b in hw.level_values("MA200 1.788–1.791, đáy 1.726 · 1.648 tỷ · 61.500đ")],
                         [1788, 1791, 1726])
        self.assertEqual([v for v, _a, _b in hw.level_values("mốc 1.726,7 và 2.000 điểm")], [2000])
        for money in ("mốc chốt quyền cổ tức 1.500 đồng/cp", "mốc 1.500 VND", "mốc 1.500 VNĐ", "mốc 1.500 vnd",
                      "mốc 1.500đ", "mốc 1.500 đ/cp", "mốc 1.500 đồng."):
            self.assertEqual(hw.level_values(money), [], money)
        self.assertEqual([v for v, _a, _b in hw.level_values("hỗ trợ 1.726 điểm, mốc 1.788 đồng hồ")], [1726, 1788])
        ref = hw.date(2026, 9, 14)
        self.assertEqual(hw.dates_in("Tuần sự kiện 14–21/09", ref), [hw.date(2026, 9, 14), hw.date(2026, 9, 21)])
        self.assertEqual(hw.dates_in("2/3 đồng hồ · 8/2026 · 10/2025", ref), [])


if __name__ == "__main__":
    unittest.main()
