#!/usr/bin/env python3
"""
Nền chung cho bộ test Lăng kính (fincept_langkinh.py + _base, _texts, _chuthe, _views): chạy script như PythonRunner
(tiến trình con, cùng interpreter), kiểm schema block §3.1, bản sao fixtures có sửa. Không phải tệp test (không khớp
mẫu test*.py). Fixtures sinh bằng lk_make_fixtures_v2.py (scratchpad, có seed) — mã cũ giữ nguyên số của đợt 1.
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.dont_write_bytecode = True  # không để __pycache__ rơi vào scripts/ (bị chép vào bundle)
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts")
SCRIPT = os.path.join(SCRIPTS, "fincept_langkinh.py")
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, SCRIPTS)
import fincept_langkinh as L  # noqa: E402
import fincept_langkinh_base as B  # noqa: E402
import fincept_langkinh_chuthe as CT  # noqa: E402
import fincept_langkinh_texts as T  # noqa: E402

VIEWS = ["tongquan", "bangquet", "matran", "bocung", "xephang", "thitruong", "codong", "chuthe", "cauchuyen",
         "phuongphap", "nguon"]
MAU = {"bull", "bear", "warn", "info", "amber", "dim", "cyan", ""}
BAC = ("FACT-T1", "FACT-T2", "SS-T3", "EST", "UNVERIFIED")
MAU_SU_KIEN = {"cyan", "amber", "info", "warn", "dim"}  # V4.3 — sự kiện chủ thể không bao giờ bull/bear
KHONG_QD = "không dùng cho quyết định"
VN30 = ["ACB", "CTG", "FPT", "HPG", "MBB", "TCX", "VCB", "VHM"]
VN100 = sorted(VN30 + ["HDG", "PLX"])
NOTE_DUNG = "CỔNG chưa xác định — số dưới đây là đo lường, không kết luận per-mã."
Q2_DUNG = "CỔNG: [CẦN DATA — Q2 Corporate] · không kết luận per-mã"
SP = "/private/tmp/claude-501/-Users-macbook-Downloads/aecc2fd1-90df-44bc-a354-d00866903817/scratchpad"
U3 = os.path.join(SP, "u3.md")
SKILL = os.path.expanduser("~/.claude/skills/langkinh-cautruc-codong/SKILL.md")
NTH = os.path.expanduser("~/.claude/skills/nguyen-tran-hai/SKILL.md")


def chu(s):
    """HTML → chữ trơn để so nguyên văn."""
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def md_tron(s):
    return s.replace("**", "").replace("`", "")


def md_tron_khoi(md):
    """Markdown nguyên văn → các dòng chữ trơn như md_khoi hiển thị (bỏ '### ', '> ', **, *, `)."""
    out = []
    for ln in md.split("\n"):
        if not ln.strip():
            continue
        ln = ln[4:] if ln.startswith("### ") else (ln[2:] if ln.startswith("> ") else ln)
        out.append(re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", ln.replace("**", "")).replace("`", ""))
    return out


def chay(thu_muc, *args):
    env = dict(os.environ, FINCEPT_BRIDGE_DATA=thu_muc, PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, SCRIPT] + list(args), capture_output=True, env=env, timeout=60)
    out = p.stdout.decode("utf-8")
    assert p.returncode == 0, p.stderr.decode()
    assert out.count("\n") == 1 and out.endswith("\n"), "stdout phải là đúng một dòng JSON: %r" % out[:200]
    obj = json.loads(out)  # toàn bộ stdout là một object JSON hợp lệ (không NaN)
    assert isinstance(obj, dict)
    return obj


def bo_khoa_moi(doc):
    """Đưa fft_langkinh.json về schema đợt 1 (bridge chưa cập nhật) — mọi khoá DELTA phải là tuỳ chọn."""
    doc["phien_ban"] = 1
    doc["cong"]["dau_vao"].pop("q2", None)
    doc["nguon"].pop("chu_the", None)
    doc["phien"].pop("trang_thai", None)
    for tt in doc["thi_truong"].values():
        tt.pop("so_ma", None)
    for m in doc["ma"].values():
        ct = m.get("chu_the") or {}
        m["chu_the"] = {"nhan": ct.get("nhan") or None, "bac": "SS-T3" if ct.get("nhan") else None,
                        "ngay": "2026-09-10" if ct.get("nhan") else None}
        m.pop("canh_bao", None)
        for k in ("tuan", "ff"):
            if isinstance(m.get(k), dict):
                for kk in ("bac_muc", "bac_hang", "canh_bao"):
                    m[k].pop(kk, None)
        m.get("dm", {}).pop("xung_dot", None)


def bo_khoa_moi_cd(doc):
    for k in ("q2", "dem_kieu", "ngay_noi_bo"):
        doc.pop(k, None)
    for v in doc["ma"].values():
        for k in list(v):
            if k not in ("moc", "cuoi", "cf_so_ky", "so_tron", "noi_suy", "sua_nam", "vs_day", "vs_dinh",
                         "cp_binh_quan", "lop", "bac", "ghi_chu"):
                del v[k]
        for x in v["moc"]:
            x.pop("kieu", None)


class Nen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="lk_test_")
        cls.tmp = cls._tmp.name
        cls.moi = cls.ban_sao()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    @classmethod
    def ban_sao(cls, sua=None, sua_cd=None, bo=(), gio_truoc=1):
        d = tempfile.mkdtemp(dir=cls.tmp)
        shutil.copytree(FIX, d, dirs_exist_ok=True)
        cap = (datetime.now() - timedelta(hours=gio_truoc)).strftime("%Y-%m-%d %H:%M")
        for ten, f in (("fft_langkinh.json", sua), ("fft_codong.json", sua_cd)):
            p = os.path.join(d, ten)
            with open(p, encoding="utf-8") as fh:
                doc = json.load(fh)
            doc["cap_nhat"] = cap
            if f:
                f(doc)
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, ensure_ascii=False)
        for ten in bo:
            p = os.path.join(d, ten)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        return d

    def kiem_thanh_cong(self, o, view, scope, vu_tru=None):
        self.assertTrue(o["success"], o.get("error"))
        self.assertNotIn("error", o)
        for k, t in (("view", str), ("scope", str), ("title", str), ("sub", str), ("as_of", str), ("tuoi", str),
                     ("cong", dict), ("blocks", list), ("data", list), ("tickers", list)):
            self.assertIsInstance(o[k], t, k)
        self.assertEqual(o["view"], view)
        self.assertEqual(o["scope"], scope)
        self.assertEqual(o["tickers"], sorted(o["tickers"]))
        # DELTA v3 V3.1 — ô gõ mã: vũ trụ VN100 A→Z, mọi view (fixture sửa có thể bớt mã → chỉ kiểm cấu trúc;
        # khớp đúng danh sách ở test_v3).
        ds = [m["ma"] for m in o["ds_ma"]]
        self.assertEqual(ds, sorted(set(ds)))
        self.assertLessEqual(set(ds), set(vu_tru or VN100))  # vu_tru: dữ liệu thật (test v4)
        for m in o["ds_ma"]:
            self.assertEqual(set(m), {"ma", "ten", "nhom"})
            self.assertIsInstance(m["ten"], str)
            nhom = m["nhom"] if isinstance(m["nhom"], list) else [m["nhom"]]   # rổ mở rộng 23/09: nhom là danh sách
            self.assertTrue(set(nhom) & {"VN30", "VN100", "VN200", "CHAEBOL"}, nhom)
        cg = o["cong"]
        self.assertTrue(cg["dong"].startswith("CỔNG:"))
        self.assertNotIn("[[", cg["dong"])
        self.assertIn(cg["muc"], ("ok", "canh_bao", "dung"))
        self.assertIsInstance(cg["chi_tiet"], str)
        self.assertIsInstance(cg["canh_bao"], list)
        for b in o["blocks"]:
            self.kiem_block(b)
        self.assertTrue(o["data"], "B8: data không bao giờ rỗng khi success (%s %s)" % (view, scope))
        for r in o["data"]:
            self.assertTrue(r and all(re.match(r"^\d\d ", k) for k in r), r)

    def kiem_block(self, b):
        t = b["type"]
        self.assertIn(t, {"note", "tiles", "table", "matrix", "chart", "scatter", "html", "lists", "story", "timeline"})
        if t == "note":
            self.assertIn(b["mau"], MAU)
            for k in ("pill", "title", "text"):
                self.assertIsInstance(b[k], str)
        elif t == "tiles":
            for it in b["items"]:
                self.assertEqual(set(it), {"k", "v", "s", "mau", "bac"})
                self.assertIn(it["mau"], MAU)
                self.assertIsInstance(it["v"], str)
                self.assertIn(it["bac"], ("", "FACT-T1", "FACT-T2", "SS-T3", "EST", "UNVERIFIED"), it)
                if it["v"] == "—":
                    self.assertEqual(it["bac"], "")
        elif t == "table":
            self.assertTrue(b["cols"])
            keys = [c["key"] for c in b["cols"]]
            for c in b["cols"]:
                self.assertIn(c["kind"], ("text", "bar", "tag"))
                self.assertIn(c["align"], ("left", "right"))
            for r in b["rows"]:
                for k in keys:
                    self.assertIsInstance(r[k], str, (k, r))
                for k, v in r.get("_sort", {}).items():
                    self.assertTrue(isinstance(v, (int, float)) and not isinstance(v, bool), (k, v))
                for v in r.get("_mau", {}).values():
                    self.assertIn(v, MAU)
                for v in r.get("_bar", {}).values():
                    self.assertTrue(0 <= v["frac"] <= 1)
                    self.assertIn(v["mau"], MAU)
                for k, v in r.get("_tip", {}).items():
                    self.assertIn(k, keys)
                    self.assertIsInstance(v, str)
                self.assertIn(r.get("_vien", ""), MAU)
            self.assertIsInstance(b["row_link"], bool)
        elif t == "matrix":
            self.assertEqual(len(b["cols"]), 2)
            self.assertEqual([r["label"] for r in b["rows"]], ["FFT ↑", "FFT ↓", "FFT ↔"])
            for r in b["rows"]:
                self.assertEqual(len(r["cells"]), 2)
                for cell in r["cells"]:
                    for ch in cell["chips"]:
                        self.assertIn(ch["mau"], ("amber", "info", ""))
        elif t == "chart":
            self.assertTrue(all(isinstance(x, int) for x in b["x"]))
            self.assertLessEqual(len(b["x"]), 400)
            self.assertLessEqual(len(b.get("annotations", [])), 28)  # V4.4 — tổng chú thích/chart
            for s in b["series"]:
                self.assertIn(s["style"], ("line", "thin", "dash", "dot", "bar", "band"))
                self.assertIn(s["mau"], MAU)
                if s["style"] == "band":  # DELTA v3 V3.2
                    self.assertNotIn("y", s)
                    self.assertTrue(0 < s["alpha"] <= 1)
                    for k, bien in (("y_lo", "lo_min"), ("y_hi", "hi_max")):
                        self.assertIs(s[bien], k not in s, (s["name"], k))
                        if k in s:
                            self.assertEqual(len(s[k]), len(b["x"]), (s["name"], k))
                else:
                    self.assertEqual(len(s["y"]), len(b["x"]), s["name"])
                if s["axis"] == "right":
                    self.assertIn("right", b)
            for a in b.get("annotations", []):
                self.kiem_chu_thich(a, b)
        elif t == "scatter":
            self.assertEqual(set(b["quadrants"]), {"tl", "tr", "bl", "br"})
            for p in b["points"]:
                self.assertIsInstance(p["x"], (int, float))
                self.assertIn(p["mau"], MAU)
        elif t == "html":
            self.assertTrue(b["html"])
        elif t == "lists":
            for it in b["items"]:
                self.assertTrue(all(isinstance(x, str) for x in it["rows"]))
        elif t == "story":
            self.kiem_story(b)
        elif t == "timeline":
            self.kiem_timeline(b)

    def kiem_story(self, b):
        """DELTA v4 V4.3 — thẻ câu chuyện: bậc trên mọi mục, UNVERIFIED mang 'không dùng cho quyết định'."""
        self.assertEqual(set(b), {"type", "ma", "tieu_de", "sub", "chu_the", "dong_co", "vung_gia", "diem_gay",
                                  "cau_hoi_mo", "canh_bao", "link", "sections"})
        for x in b["sections"]:  # DELTA V5.1 — mỗi mục có tiêu đề, chữ, bậc; UNVERIFIED mang 'không dùng cho quyết định'
            self.assertEqual(set(x), {"title", "text", "bac", "tip"})
            self.assertIn(x["bac"], BAC)
            self.assertTrue(x["title"] and x["text"])
            if x["bac"] == "UNVERIFIED":
                self.assertIn(KHONG_QD, x["text"])
        titles = [x["title"] for x in b["sections"]]
        if "Bức tranh tổng thể" in titles:
            self.assertEqual(titles[0], "Bức tranh tổng thể")
        for k in ("ma", "tieu_de", "sub", "link"):
            self.assertTrue(isinstance(b[k], str) and b[k], k)
        for x in b["chu_the"]:
            self.assertEqual(set(x), {"ten", "vai_tro", "so_huu", "bac", "tip"})
            self.assertIn(x["bac"], BAC)
            self.assertTrue(all(isinstance(x[k], str) for k in x))
            if x["bac"] == "UNVERIFIED":
                self.assertIn(KHONG_QD, x["vai_tro"])
        dc = b["dong_co"]
        self.assertEqual(set(dc), {"text", "bac", "tip"})
        self.assertIn(dc["bac"], BAC + ("",))
        self.assertTrue(dc["text"])
        if dc["bac"] == "":
            self.assertTrue(dc["text"].startswith("[CẦN DATA]"))
        vg = b["vung_gia"]
        if vg is not None:
            self.assertEqual(set(vg), {"lo", "hi", "vwap", "nay", "lech_pct", "bac", "nhan", "logic"})
            self.assertTrue(vg["lo"] <= vg["hi"])
            for k in ("vwap", "nay", "lech_pct"):
                self.assertTrue(vg[k] is None or isinstance(vg[k], (int, float)), k)
            self.assertIn(vg["bac"], BAC)
        if b["diem_gay"] is not None:
            self.assertEqual(set(b["diem_gay"]), {"text", "bac"})
            self.assertIn(b["diem_gay"]["bac"], BAC)
        for k in ("cau_hoi_mo", "canh_bao"):
            self.assertTrue(all(isinstance(x, str) and x for x in b[k]), k)

    def kiem_timeline(self, b):
        self.assertTrue(b["title"] and isinstance(b["sub"], str) and b["items"])
        ngay = []
        for it in b["items"]:
            self.assertLessEqual({"ngay", "ngay_uoc", "chu_the", "hanh_dong", "mo_ta", "gia", "bac", "mau", "tip"}, set(it))
            self.assertIn(it["bac"], BAC)
            self.assertIn(it["mau"], MAU_SU_KIEN)
            self.assertIsInstance(it["ngay_uoc"], bool)
            self.assertFalse(it["ngay"].startswith("~"))  # C++ tự thêm "~" theo ngay_uoc
            if it["bac"] == "UNVERIFIED":
                self.assertIn(KHONG_QD, it["mo_ta"])
                self.assertIn(KHONG_QD, it["tip"])
            if re.match(r"^\d\d/\d\d/\d{4}$", it["ngay"]):
                ngay.append(datetime.strptime(it["ngay"], "%d/%m/%Y"))
        self.assertEqual(ngay, sorted(ngay, reverse=True))  # ngày giảm dần

    def kiem_chu_thich(self, a, b):
        """DELTA v3 V3.3 — point / vline / xband; x trong khung trục; chữ không NaN, số kiểu Việt."""
        x0, x1 = min(b["x"]), max(b["x"])
        self.assertIn(a["mau"], MAU - {""})
        self.assertIsInstance(a["text"], str)
        self.assertNotRegex(a["text"] + a.get("sub", ""), r"\d\.\d{1,2}%|\d,\d{3}\b(?!%)|nan|None", a)
        if a["kind"] == "point":
            self.assertTrue(x0 <= a["x"] <= x1, a)
            self.assertIsInstance(a["y"], (int, float))
            self.assertIn(a["axis"], ("left", "right"))
            self.assertIn(a["marker"], ("tri_down", "tri_up", "dot", "diamond", "none"))
            self.assertIn(a["pos"], ("above", "below", "left", "right"))
            self.assertIn(a["uu_tien"], (1, 2, 3))
            if a["axis"] == "right":
                self.assertIn("right", b)
        elif a["kind"] == "vline":
            self.assertTrue(x0 <= a["x"] <= x1, a)
            self.assertIn(a["style"], ("dash", "dot"))
            self.assertIn(a["uu_tien"], (1, 2, 3))
        elif a["kind"] == "hband":  # DELTA v4 V4.3
            self.assertTrue(isinstance(a["y0"], (int, float)) and isinstance(a["y1"], (int, float)) and a["y0"] < a["y1"])
            self.assertIn(a["axis"], ("left", "right"))
            if a["axis"] == "right":
                self.assertIn("right", b)
            self.assertTrue(0 < a["alpha"] <= 1)
        else:
            self.assertEqual(a["kind"], "xband")
            self.assertTrue(x0 <= a["x0"] < a["x1"] <= x1, a)
            self.assertTrue(0 < a["alpha"] <= 1)

    def block(self, o, typ, i=0):
        return [b for b in o["blocks"] if b["type"] == typ][i]

    def note(self, o, title):
        return next(b for b in o["blocks"] if b["type"] == "note" and b["title"] == title)

    def tiles(self, o):
        return {t["k"]: t for t in self.block(o, "tiles")["items"]}

    def hang(self, table, ma):
        return next(r for r in table["rows"] if r["ma"] == ma)
