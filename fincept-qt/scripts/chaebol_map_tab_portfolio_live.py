#!/usr/bin/env python3
"""
chaebol_map_tab_portfolio_live — lớp LIVE cho tab 08 (DANH MỤC) và ★ 13 (ACTION PORTFOLIO 25) của chaebol_map.

Chỉ chạy ở mode live (chaebol_map_tab_portfolio._live). Nguyên tắc (DESIGN §0.3–0.6, §6; nhiệm vụ tab portfolio):
  - Bản V21 (12/05) là BẢN LƯU: stance/khuyến nghị giữ nguyên văn + dấu V21·12/05 (không chấm lại: CỔNG đang DỪNG).
  - Lãi/lỗ tới nay của vị thế V21 = EST, quy đổi quyền (giá điều chỉnh vendor ≈ tổng lợi suất), giá mới FACT-T2.
  - Khối MỚI: hai danh mục hiện hành cạnh nhau (Lăng kính Khối 11 · 10/09 và hoidongcovanai-chungkhoan · 12/09) từ
    chaebol_map_data.portfolio_current(); cờ lệch; tổng "66% verified + 3% UNVERIFIED" (không gộp); KHÔNG chọn bản.
  - Câu viết lại theo dữ kiện lấy từ dossier (ctx.dossier["portfolio"], mảnh cap_nhat_2026-09-27.portfolio.json):
    mỗi mệnh đề mang nhãn bậc của dữ kiện + dấu ↻27/09. Thiếu dossier → chỉ số sống + bản V21.
  - Dòng tiền sau 08/05: chỉ NN + tự doanh (khớp) là số thật; Cá nhân/Tổ chức = [CẦN DATA]; phần dư −(NN+TD) nhãn E.
  - Không hô mua/bán mới: nội dung mới là "action cần kiểm chứng"; >5% NAV → Synthesis L1+L2+L3.
Phần dòng tiền (FlowMixin) + helper định dạng dùng chung nằm ở chaebol_map_tab_portfolio_flow (tách 27/09, tệp ≤ ~800 dòng).
"""
from __future__ import annotations

import re
from dataclasses import replace

from chaebol_map_dom import (
    C, F_MONO, F_NUM, F_SERIF, can_data, h, js_sum, status_pill, tier, to_fixed, to_locale, upd_mark, v21_mark,
)
from chaebol_map_shell import Card, Section, Stat
from chaebol_map_tab_portfolio_flow import _NOTE, FlowMixin, _dm, _dmy, _k, _pct, _pn

D0_POS = "2026-05-08"          # "As of 08/05/2026" của tab 08 (vùng giá/target viết trên giá thô ngày này)
D0_P25 = "2026-05-12"          # "hôm nay" đóng cứng của trang (as_of ACTION_PORT_25)
UPD = "2026-09-27"
_ZONE_RE = re.compile(r"(\d+(?:\.\d+)?(?:\s*[-–/]\s*\d+(?:\.\d+)?)*)\s*[kK]\b")
_SKILL_PATH = re.compile(r"(?:/Users/[^/\s]+|~)/\.claude/skills/([\w.-]+)/SKILL\.md")
_HOME_PATH = re.compile(r"/Users/[^/\s]+/")
_PAT_Q = re.compile(r"\bPattern ([A-D])\b(?!\?)")


def _short_src(s):
    """Nguồn hiển thị: không in đường dẫn tuyệt đối của máy ('skill <tên>' thay cho ~/.claude/skills/<tên>/SKILL.md)."""
    return _HOME_PATH.sub("~/", _SKILL_PATH.sub(r"skill \1", str(s or "")))


class Live(FlowMixin):
    """Một lần dựng live cho tab portfolio/portfolio25 (cache số sống theo mã)."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.D = ctx.data
        dos = ctx.dossier if isinstance(ctx.dossier, dict) else {}
        self.dos = dos.get("portfolio") if isinstance(dos.get("portfolio"), dict) else {}
        if not self.dos:
            ctx.warn("dossier chưa có khoá 'portfolio' — tab chỉ có số sống + bản V21")
        self.v21 = ctx.v21 or {}
        self._c = {}
        self.pc = self._call("portfolio_current") or self._pc_from_dossier()

    def _pc_from_dossier(self):
        """Dự phòng khi không đọc được hai SKILL.md: dựng lại hai sổ từ snapshot trong dossier (27/09)."""
        meta = self.dos.get("books_meta") or {}
        if not self.dos.get("lk_khoi11_1009") or not meta:
            return {}
        self.ctx.warn("sổ danh mục hiện hành lấy từ snapshot dossier (không đọc được SKILL.md qua chaebol_map_data)")
        out = {"conflicts": list(self.dos.get("conflicts") or [])}
        for key in ("lk_khoi11_1009", "hdcv_1209"):
            m = meta.get(key) or {}
            pos = [{"tk": x["tk"], "nav": x["nav"], "verified": x["verified"], **({"layer": x["layer"]} if x.get("layer")
                                                                                   else {})}
                   for x in self.dos.get(key) or []]
            ver = js_sum(x["nav"] for x in pos if x["verified"])
            unv = js_sum(x["nav"] for x in pos if not x["verified"])
            out[key] = {"date": m.get("date"), "positions": pos, "cash": m.get("cash"), "unexplained": m.get("unexplained"),
                        "tong_text": m.get("tong_text"), "tong_verified": ver, "tong_unverified": unv, "src": m.get("src"),
                        "avoid": [], "watch": [], "candidates": [], "xung_dot": {}, "actions": []}
        return out

    # ── truy cập dữ liệu an toàn ────────────────────────────────────────────

    def _call(self, fn, *a, **kw):
        f = getattr(self.D, fn, None) if self.D is not None else None
        if not callable(f):
            return None
        key = (fn, a, tuple(sorted(kw.items())))
        if key not in self._c:
            try:
                self._c[key] = f(*a, **kw)
            except Exception as exc:  # một mã lỗi không được làm hỏng tab
                self.ctx.warn("chaebol_map_data.%s%r lỗi: %s: %s" % (fn, a, type(exc).__name__, exc))
                self._c[key] = None
        return self._c[key]

    @staticmethod
    def ok(v):
        return v is not None and getattr(v, "value", None) is not None

    def num(self, v, text, date=True):
        """[text, nhãn bậc] hoặc [CẦN DATA — lý do]."""
        if not self.ok(v):
            return [can_data(getattr(v, "note", None) or "không có nguồn")]
        return [text, tier(v.tier, v.asof if date else None) if v.tier else None]

    def price(self, tk):
        return self._call("close", tk)

    def _has_ex(self, tk, d0, d1=None):
        """Có GDKHQ (ISS/DIV của events-v2) trong (d0, d1]? Không đọc được events-v2 → coi như có (giữ giá điều chỉnh)."""
        ev = self._call("capital_events", tk)
        if not self.ok(ev):
            return True
        return any(e.get("code") in ("ISS", "DIV") and e.get("exright") and d0 < e["exright"] <= (d1 or "9999")
                   for e in ev.value)

    def pct(self, tk, d0, d1=None):
        """Δ% từ d0 (EST). Có GDKHQ sau d0 → giá điều chỉnh vendor (quy đổi quyền); không có → giá THÔ, vì chuỗi
        closePriceAdjusted của vendor có nhiễu dù không có sự kiện quyền (vd ACV, tab_report 7a)."""
        if self._has_ex(tk, d0, d1):
            return self._call("pct_change", tk, d0, d1)
        a, b = self._call("close", tk, d0), self._call("close", tk, d1)
        if not (self.ok(a) and self.ok(b)) or not a.value:
            return self._call("pct_change", tk, d0, d1)
        x = (b.value / a.value - 1) * 100
        return replace(b, value=x, text=_pct(x), tier="EST", unit="%",
                       note="giá thô %s → %s (không có GDKHQ trong events-v2)" % (_dmy(a.asof), _dmy(b.asof)))

    def factor(self, tk, d0):
        return self._call("adj_factor", tk, d0)

    def events(self, tk, d0):
        """Sự kiện quyền GDKHQ sau d0 (bỏ ESOP): [(ngày, loại, tỉ lệ, chữ)] — FACT-T2 (vc_lk events-v2).
        Đọc TOÀN BỘ events-v2 rồi lọc theo ngày GDKHQ: capital_events(tk, since) lọc theo ngày CÔNG BỐ nên bỏ sót sự
        kiện công bố trước d0 mà GDKHQ sau d0 (vd HPG cổ tức tiền 500đ, GDKHQ 11/05)."""
        ev = self._call("capital_events", tk)
        dt = self._call("data_to") or "9999"
        out = []
        for e in (getattr(ev, "value", None) or []):
            d, title = e.get("exright"), str(e.get("title") or "").lower()
            if not d or d <= d0 or e.get("code") not in ("ISS", "DIV"):
                continue
            r, soon = e.get("ratio"), (" (sắp)" if d > dt else "")
            if e["code"] == "DIV":
                out.append((d, "div", None, "tiền %s %s%s" % (e.get("ratio_text") or "", _dm(d), soon)))
            elif "quyền mua" in title and r:
                out.append((d, "rights", r, "quyền mua %s%% %s%s" % (_k(r * 100), _dm(d), soon)))
            elif ("thưởng" in title or "cổ tức bằng cổ phiếu" in title) and r:
                out.append((d, "stock", r, "CP %s%% %s%s" % (_k(r * 100), _dm(d), soon)))
            # ESOP (CBCNV), riêng lẻ, chuyển đổi trái phiếu: không chia theo tỷ lệ cho cổ đông hiện hữu → bỏ
        out.sort()
        return out

    def conv(self, tk, text, d0):
        """Quy đổi mọi mức giá '…K' trong chuỗi V21 sang cơ sở giá hiện tại (× adj_factor d0→cuối). → (chuỗi, V)."""
        f = self.factor(tk, d0)
        if not self.ok(f) or not _ZONE_RE.search(str(text or "")):
            return None, f
        def rep(m):
            nums = re.split(r"\s*[-–/]\s*", m.group(1))
            seps = re.findall(r"\s*[-–/]\s*", m.group(1))
            vals = [_k(float(n) * f.value) for n in nums]
            return "".join(v + (seps[i].strip() if i < len(seps) else "") for i, v in enumerate(vals)) + "K"
        return _ZONE_RE.sub(rep, str(text)), f

    def zone_bounds(self, tk, text, d0):
        f = self.factor(tk, d0)
        m = _ZONE_RE.search(str(text or ""))
        if not self.ok(f) or not m:
            return None
        nums = [float(n) * f.value * 1000 for n in re.split(r"\s*[-–/]\s*", m.group(1))]
        return min(nums), max(nums)

    def where(self, tk, text, d0):
        """Giá cuối so với vùng V21 đã quy đổi: 'trong vùng' / 'dưới vùng' / 'trên vùng' (so sánh dữ kiện, không phải lệnh)."""
        b, px = self.zone_bounds(tk, text, d0), self.price(tk)
        if b is None or not self.ok(px):
            return None
        lo, hi = b
        if "<" in str(text) and lo == hi:
            return "dưới mức" if px.value < hi else "trên mức"
        return "trong vùng" if lo <= px.value <= hi else ("dưới vùng" if px.value < lo else "trên vùng")

    def book(self, tk):
        """(K11 vị thế|None, HĐCV vị thế|None, K11 watch/avoid, HĐCV avoid). Khối 11 vừa watch (v1.7) vừa AVOID
        (danh sách daily) → 'watch/AVOID' = sổ tự mâu thuẫn, nêu cả hai, không chọn."""
        a, b = self.pc.get("lk_khoi11_1009") or {}, self.pc.get("hdcv_1209") or {}
        x = next((p for p in a.get("positions") or [] if p["tk"] == tk), None)
        y = next((p for p in b.get("positions") or [] if p["tk"] == tk), None)
        w = tk in (a.get("watch") or []) or any(c.startswith(tk + " ") and "watch" in c for c in a.get("candidates") or [])
        av = tk in (a.get("avoid") or [])
        wa = "watch/AVOID" if (w and av) else ("avoid" if av else ("watch" if w else None))
        return x, y, wa, ("AVOID" if tk in (b.get("avoid") or []) else None)

    def _unexpl_flag(self, a, b):
        ua, ub = self._unexpl(a)[0], self._unexpl(b)[0]
        return ua is not None and ub is not None and ua != ub

    # ── dossier ─────────────────────────────────────────────────────────────

    def entry(self, *path):
        d = self.dos
        for k in path:
            d = d.get(k) if isinstance(d, dict) else None
        return d if isinstance(d, dict) else None

    def claim_status(self, e):
        """Trạng thái claim lấy từ MỘT nguồn: mảnh claims (ctx.dossier[claim_set][claim].status — claims20 = CLAIMS_C01_C20,
        claims54 = CLAIMS_54; hai bộ trùng ký hiệu). Mục không trỏ claim hoặc bộ claims vắng → status của chính mục."""
        cid, cset = e.get("claim"), e.get("claim_set")
        dos = self.ctx.dossier if isinstance(self.ctx.dossier, dict) else {}
        c = (dos.get(cset) or {}).get(cid) if cid and cset else None
        st = c.get("status") if isinstance(c, dict) else None
        if st and e.get("status") and st != e["status"]:
            self.ctx.warn("portfolio: %s.%s trạng thái mảnh portfolio '%s' ≠ mảnh claims '%s' — dùng mảnh claims"
                          % (cset, cid, e["status"], st))
        return st or e.get("status")

    def render(self, e, pill=True, sep=" "):
        """Mục dossier → [pill claim] mệnh đề₁ nhãn₁ mệnh đề₂ nhãn₂ … ↻27/09."""
        if not e:
            return []
        out = []
        st = self.claim_status(e) if pill else None
        if st:
            out += [status_pill(st), " "]
        for i, p in enumerate(e.get("parts") or [{"text": e.get("text"), "tier": e.get("tier")}]):
            if not p.get("text"):
                continue
            out += [sep if i else "", p["text"], tier(p["tier"]) if p.get("tier") else None]
        return out + [upd_mark(UPD)]

    # ── Tab 08: khối hai danh mục hiện hành ─────────────────────────────────

    def _cong(self):
        """Tham chiếu ngắn tới dòng CỔNG ở header (DESIGN §6.2), cùng kiểu chữ đoạn văn — không chép lại cả chuỗi."""
        cong = (getattr(self.ctx, "live_info", None) or {}).get("cong") or {}
        text = str(cong.get("text") or "CỔNG: [CẦN DATA]")
        stop = "[CẦN DATA" in text or "DỪNG" in text
        return "CỔNG v1.7 đang DỪNG — xem dòng CỔNG ở header" if stop else "CỔNG: xem dòng CỔNG ở header"

    def _v21_view(self, tk):
        """Nhận định V21 về mã (tab 08 + AP25) để đối chiếu — chuỗi thuần, gắn dấu V21 ở tiêu đề cột."""
        pa = self.v21.get("PORTFOLIO_ACTION") or {}
        bits = []
        if any(p["tk"] == tk for p in pa.get("current") or []):
            bits.append("08 nắm")
        for p in pa.get("add") or []:
            if p["tk"] == tk:
                bits.append("08 mua thêm " + p["sizeRec"].replace(" NAV", ""))
        if any(tk in p["tk"].split(",") for p in pa.get("avoid") or []):
            bits.append("08 AVOID")
        for p in self.v21.get("ACTION_PORT_25") or []:
            if p["tk"] == tk:
                bits.append("AP25 %s %s" % (p["act"], p["w"]))
        return " · ".join(bits) or "—"

    def books_section(self):
        a, b = self.pc.get("lk_khoi11_1009"), self.pc.get("hdcv_1209")
        if not a or not b:
            return Section("Danh Mục Hiện Hành — Hai Bản Cạnh Nhau",
                           Card(h("div", _NOTE, can_data("chaebol_map_data.portfolio_current() không trả sổ"))),
                           accent=C.ink2, key="p08.books")
        intro = h("div", {"fontSize": 13, "fontFamily": F_SERIF, "color": C.inkD, "lineHeight": 1.7,
                          "fontStyle": "italic", "marginBottom": 18, "padding": "14px 18px", "background": C.parch,
                          "borderLeft": "3px solid " + C.ink2},
                  "Hai sổ danh mục nội bộ đang lệch nhau: ", h("strong", {"color": C.ink}, "Lăng kính Khối 11"),
                  " (snapshot %s) và skill điều hành " % _dm(a["date"]),
                  h("strong", {"color": C.ink}, "hoidongcovanai-chungkhoan"), " (%s). " % _dm(b["date"]),
                  "Trang đặt hai bản cạnh nhau, gắn cờ chỗ lệch, không chọn bản nào. %NAV là số sổ nội bộ, không phải "
                  "số thị trường: trang gắn E dù skill Khối 11 tự ghi FACT-T2 (hạ bậc vì không phải số vendor/CBTT). (",
                  self._cong(), ") → stance V21 bên dưới giữ nguyên, không chấm lại. Mọi action chạm >5% NAV → "
                  "Synthesis L1+L2+L3; không lệnh nào đặt từ đây.", upd_mark(UPD))
        return Section("Danh Mục Hiện Hành — Hai Bản Cạnh Nhau",
                       intro, self._books_kpi(a, b), self._books_table(a, b), self._books_notes(a, b),
                       accent=C.ink2, sub="Khối 11 · %s ↔ HĐCV · %s · không chọn bản" % (_dm(a["date"]), _dm(b["date"])),
                       key="p08.books")

    def _kpi(self, label, value, sub=None, color=C.ink, size=18):
        return Card(h("div", {"fontSize": 9, "letterSpacing": ".18em", "color": C.inkM, "fontFamily": F_MONO,
                              "marginBottom": 5}, label),
                    h("div", {"fontSize": size, "fontWeight": 600, "color": color, "fontFamily": F_NUM}, *value),
                    h("div", {"fontSize": 10, "color": C.inkD, "fontFamily": F_MONO, "marginTop": 3}, *sub) if sub else None)

    @staticmethod
    def _unexpl(bk):
        """Phần chưa giải trình: sổ ghi sẵn (Khối 11) hoặc tự tính 100 − verified − UNVERIFIED − cash (EST)."""
        if bk.get("unexplained") is not None:
            return bk["unexplained"], "sổ ghi"
        if bk.get("cash") is None:
            return None, None
        return 100 - bk["tong_verified"] - bk["tong_unverified"] - bk["cash"], "tự tính"

    def _books_kpi(self, a, b):
        def tong(bk):
            v = [to_locale(bk["tong_verified"], "en") + "% verified", tier("E", bk["date"])]
            if bk.get("tong_unverified"):
                v += [" + " + to_locale(bk["tong_unverified"], "en") + "% UNVERIFIED", tier("U", bk["date"])]
            return v

        def sub(bk):
            ux, how = self._unexpl(bk)
            s = ["cash ", to_locale(bk["cash"], "en") + "%" if bk.get("cash") is not None else can_data(),
                 tier("E"), " · chưa giải trình "]
            s += ([to_locale(ux, "en") + "%", " (" + how + ")", tier("E")] if ux is not None else [can_data()])
            return s
        conf = [c["tk"] or c["loai"] for c in self.pc.get("conflicts") or []]
        if self._unexpl_flag(a, b):
            conf.append("chưa giải trình")      # cùng số dòng có cờ ở cột CỜ LỆCH của bảng
        dt = self._call("data_to")
        return h("div", {"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)", "gap": 12, "marginBottom": 18},
                 self._kpi("LĂNG KÍNH KHỐI 11 · " + _dm(a["date"]), tong(a), sub(a), size=15),
                 self._kpi("HOIDONGCOVANAI · " + _dm(b["date"]), tong(b), sub(b), size=15),
                 self._kpi("CỜ LỆCH GIỮA HAI SỔ", [str(len(conf)), tier("E")],
                           [" · ".join(conf) or "—"], color=C.vermillion if conf else C.ink),
                 self._kpi("GIÁ ĐẾN", [_dmy(dt), tier("T2")] if dt else [can_data()],
                           ["vc_lk · Δ quy đổi quyền từ ngày sổ"]),
                 key="p08.books.kpi")

    def _books_table(self, a, b):
        th = lambda t, al="left": h("th", {"textAlign": al, "padding": "8px 10px"}, t)  # noqa: E731
        td = {"padding": "8px 10px"}
        conf = {c["tk"]: c for c in self.pc.get("conflicts") or [] if c.get("tk")}
        order = [p["tk"] for p in a["positions"]] + [p["tk"] for p in b["positions"] if p["tk"] not in
                                                      {x["tk"] for x in a["positions"]}]
        order += [t for t in conf if t not in order]
        rows = []
        for tk in order:
            x, y, wa, ha = self.book(tk)
            c = conf.get(tk)
            k11 = ([to_locale(x["nav"], "en") + "%", tier("E" if x["verified"] else "U", a["date"]),
                    " UNVERIFIED" if not x["verified"] else None] if x else [wa or "—"])
            hd = ([to_locale(y["nav"], "en") + "%", tier("E", b["date"]), " · " + y.get("layer", "")] if y
                  else [ha or "—"])
            if c is None:
                flag = h("span", {"color": C.inkM}, "—")
            elif c["loai"] == "nav":
                flag = h("span", {"color": C.vermillion, "fontWeight": 700},
                         "%s vs %s" % (to_locale(c["lk_khoi11"], "en"), to_locale(c["hdcv"], "en")))
            elif c["loai"] == "chi_mot_ban":
                flag = h("span", {"color": C.vermillion, "fontWeight": 700},
                         "chỉ " + ("Khối 11" if c.get("lk_khoi11") is not None else "HĐCV") +
                         (" · UNVERIFIED" if c.get("note") == "UNVERIFIED" else ""))
            elif wa == "watch/AVOID":
                flag = h("span", {"color": C.vermillion, "fontWeight": 700},
                         "Khối 11 tự mâu thuẫn · HĐCV " + str(c.get("hdcv") or "—"))
            else:
                flag = h("span", {"color": C.vermillion, "fontWeight": 700}, "%s vs %s" % (c["lk_khoi11"], c["hdcv"]))
            px, pc = self.price(tk), self.pct(tk, a["date"])
            rows.append(h("tr", {"borderBottom": "1px solid " + C.parch},
                          h("td", {**td, "fontFamily": F_MONO, "fontWeight": 700, "color": C.ink}, tk),
                          h("td", {**td, "textAlign": "right", "fontFamily": F_MONO, "color": C.gold}, *k11),
                          h("td", {**td, "textAlign": "right", "fontFamily": F_MONO, "color": C.gold}, *hd),
                          h("td", {**td, "fontFamily": F_MONO, "fontSize": 10}, flag),
                          h("td", {**td, "textAlign": "right", "fontFamily": F_MONO},
                            *self.num(px, to_locale(px.value, "en") if self.ok(px) else "")),
                          h("td", {**td, "textAlign": "right", "fontFamily": F_MONO,
                                   "color": _pn(pc.value) if self.ok(pc) else C.ink},
                            *self.num(pc, _pct(pc.value) if self.ok(pc) else "")),
                          h("td", {**td, "color": C.inkD, "fontSize": 10}, self._v21_view(tk)),
                          key="p08.books.row." + tk))
        for label, fa, fb in (("TIỀN MẶT", a.get("cash"), b.get("cash")),
                              ("CHƯA GIẢI TRÌNH", self._unexpl(a)[0], self._unexpl(b)[0])):
            rows.append(h("tr", {"borderBottom": "1px solid " + C.parch},
                          h("td", {**td, "fontFamily": F_MONO, "fontWeight": 700, "color": C.inkD, "fontSize": 9,
                                   "letterSpacing": ".1em"}, label),
                          *[h("td", {**td, "textAlign": "right", "fontFamily": F_MONO, "color": C.gold},
                              *([to_locale(v, "en") + "%", tier("E")] if v is not None else [can_data()]))
                            for v in (fa, fb)],
                          h("td", {**td, "fontFamily": F_MONO, "fontSize": 10},
                            h("span", {"color": C.vermillion, "fontWeight": 700},
                              "%s vs %s" % (to_locale(fa, "en"), to_locale(fb, "en"))) if (fa is not None and fb is not None
                                                                                           and fa != fb) else "—"),
                          h("td", td), h("td", td),
                          h("td", {**td, "color": C.inkD, "fontSize": 10},
                            "AP25: Cash 15%" if label == "TIỀN MẶT" else "Khối 11 ghi sẵn; HĐCV tự tính = 100 − verified − cash")))
        rows.append(h("tr", {"borderTop": "2px solid " + C.gold},
                      h("td", {**td, "fontFamily": F_MONO, "fontWeight": 700, "color": C.ink, "fontSize": 9,
                               "letterSpacing": ".1em"}, "TỔNG (KHÔNG GỘP)"),
                      *[h("td", {**td, "textAlign": "right", "fontFamily": F_MONO, "color": C.ink, "fontWeight": 700},
                          to_locale(bk["tong_verified"], "en") + "% verified", tier("E"),
                          *([" + " + to_locale(bk["tong_unverified"], "en") + "% UNVERIFIED", tier("U")]
                            if bk.get("tong_unverified") else [])) for bk in (a, b)],
                      h("td", td, a={"colSpan": 4})))
        head = h("tr", {"borderBottom": "2px solid " + C.gold, "color": C.ink2, "fontFamily": F_MONO, "fontSize": 9,
                        "letterSpacing": ".1em"},
                 th("MÃ"), th("KHỐI 11 · %s" % _dm(a["date"]), "right"), th("HĐCV · %s" % _dm(b["date"]), "right"),
                 th("CỜ LỆCH"), th("GIÁ %s" % _dm(self._call("data_to")), "right"),
                 th("Δ TỪ %s (QUY ĐỔI)" % _dm(a["date"]), "right"), h("th", {"textAlign": "left", "padding": "8px 10px"},
                                                                     "V21 ĐÃ NÓI", v21_mark()))
        return h("table", {"width": "100%", "fontSize": 11, "fontFamily": F_SERIF, "borderCollapse": "collapse",
                           "marginBottom": 14},
                 h("thead", None, head), h("tbody", None, *rows), key="p08.books.table")

    def _books_notes(self, a, b):
        acts = " · ".join("%s %s→%s" % (x["tk"], to_locale(x["tu"], "en"), to_locale(x["den"], "en"))
                          for x in a.get("actions") or [])
        xd = a.get("xung_dot") or {}
        lines = [
            h("div", None, h("strong", {"color": C.ink}, "AVOID · "), "Khối 11 · %s: " % (a.get("src_watch_avoid") or "—"),
              " ".join(a.get("avoid") or []) or "—", tier("E"), " · HĐCV (%s): " % _dm(b["date"]),
              " ".join(b.get("avoid") or []) or "—", tier("E"), " · WATCH Khối 11: ", " ".join(a.get("watch") or []) or "—",
              tier("E")),
            h("div", None, h("strong", {"color": C.vermillion}, "KHỐI 11 TỰ MÂU THUẪN · "),
              " · ".join("%s: %s" % (t, n) for t, n in sorted(xd.items())), tier("E"),
              " — nêu cả hai, không chọn.") if xd else None,
            h("div", None, h("strong", {"color": C.ink}, "ACTION CẦN KIỂM CHỨNG (Keynote 13, Khối 11) · "),
              acts or "—", tier("E"), " · ứng viên: ", " · ".join(a.get("candidates") or []) or "—",
              " — đây không phải lệnh; mọi mục >5% NAV hoặc chạm 5% → Synthesis L1+L2+L3."),
            h("div", None, h("strong", {"color": C.ink}, "ĐỐI CHIẾU V21 · "), *self._v21_conflicts(a, b)),
            h("div", {"color": C.inkM}, "Nguồn: ", _short_src(a.get("src")) or "—", " · ", _short_src(b.get("src")) or "—",
              " (đọc qua chaebol_map_data.portfolio_current)"),
        ]
        return h("div", {**_NOTE, "padding": "10px 14px", "background": C.ink2 + "12",
                         "borderLeft": "3px solid " + C.ink2}, *lines, key="p08.books.notes")

    def _v21_conflicts(self, a, b):
        pa = self.v21.get("PORTFOLIO_ACTION") or {}
        avoid08 = {t for p in pa.get("avoid") or [] for t in p["tk"].split(",")}
        ap_avoid = {p["tk"] for p in self.v21.get("ACTION_PORT_25") or [] if p["cat"] == "Avoid"}
        held = {p["tk"]: p["nav"] for p in a["positions"]}
        held_b = {p["tk"]: p["nav"] for p in b["positions"]}
        out = []
        for tk in sorted(set(held) | set(held_b)):
            src = [s for s, bag in (("08 AVOID", avoid08), ("AP25 AVOID", ap_avoid)) if tk in bag]
            if src:
                out.append("%s: V21 %s ↔ sổ %s/%s%%" % (tk, " + ".join(src), to_locale(held.get(tk, 0), "en") if tk in held
                                                       else "—", to_locale(held_b[tk], "en") if tk in held_b else "—"))
        for p in pa.get("add") or []:
            if p["tk"] in held or p["tk"] in held_b:
                out.append("%s: V21 mua thêm %s ↔ sổ %s/%s%%" % (p["tk"], p["sizeRec"].replace(" NAV", ""),
                                                                to_locale(held.get(p["tk"], 0), "en"),
                                                                to_locale(held_b.get(p["tk"], 0), "en")))
        stb = self.book("STB")
        if stb[2] in ("watch", "watch/AVOID") and "STB" in ap_avoid:
            out.append("STB: AP25 AVOID ↔ Khối 11 " + ("watch/AVOID (tự mâu thuẫn)" if stb[2] == "watch/AVOID"
                                                      else "watch"))
        return [" · ".join(out) or "—", tier("E")]

    # ── Tab 08: Section A (bản lưu V21 + lãi/lỗ tới nay) ────────────────────

    def intro_a_note(self):
        e = self.entry("p08", "intro")
        if not e:
            return None
        return h("div", {"marginTop": 8, "fontStyle": "normal", "fontSize": 11, "color": C.inkD},
                 h("strong", {"color": C.ochre, "fontFamily": F_MONO, "fontSize": 9, "letterSpacing": ".18em"},
                   "DỮ KIỆN MỚI · "), *self.render(e))

    def _pnl(self, p):
        fl = (self.v21.get("FLOW") or {}).get(p["tk"]) or {}
        return self._call("pnl_since", p["tk"], fl.get("date") or D0_POS, p["mktPrice"], p["position"],
                          p["costAvg"]) or {}

    def summary_live(self, cur):
        rs = [self._pnl(p) for p in cur]
        if not rs or not all(self.ok(r.get("value_now")) for r in rs):
            return h("div", {**_NOTE, "marginBottom": 18}, "Ước tới nay: ", can_data("thiếu giá điều chỉnh vc_lk"))
        now = js_sum(r["value_now"].value for r in rs)
        mv = js_sum(p["mktValue"] for p in cur)
        cost = js_sum(p["position"] * p["costAvg"] for p in cur)
        pnl, asof = now - cost, rs[0]["value_now"].asof
        e = tier("E", asof)
        return h("div", None,
                 h("div", {**_NOTE, "color": C.ochre, "marginBottom": 6},
                   "↻ ƯỚC TỚI %s — giữ nguyên vị thế V21 (UNVERIFIED), quy đổi quyền bằng giá điều chỉnh vendor ≈ tổng "
                   "lợi suất; không phải sao kê" % _dmy(asof)),
                 h("div", {"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)", "gap": 12, "marginBottom": 18},
                   self._kpi("MV ƯỚC " + _dm(asof), [to_fixed(now / 1e9, 2) + " tỷ", e], size=22),
                   self._kpi("Δ MV TỪ 07/05", [_pct((now / mv - 1) * 100), e], color=_pn(now - mv), size=22),
                   self._kpi("P&L ƯỚC SO VỐN GỐC", [("+" if pnl >= 0 else "") + to_fixed(pnl / 1e9, 2) + " tỷ", e],
                             [_pct(pnl / cost * 100), e], color=_pn(pnl), size=22),
                   self._kpi("GIÁ ĐẾN", [_dmy(asof), tier("T2")], ["vc_lk price-history · closeAdjusted"], size=22)),
                 key="p08.kpi.live")

    def _steps_text(self, tk, d0):
        f = self.factor(tk, d0)
        ev = self.events(tk, d0)
        if not self.ok(f):
            return [can_data(getattr(f, "note", None) or "không có hệ số quyền")]
        return ["hệ số quyền ×" + f.text, tier("E", f.asof), " (" + (" · ".join(x[3] for x in ev) or "không có GDKHQ")
                + ")", tier("T2") if ev else None]

    def position_live(self, p):
        tk = p["tk"]
        fl = (self.v21.get("FLOW") or {}).get(tk) or {}
        d0 = fl.get("date") or D0_POS
        r = self._pnl(p)
        px, pc, vn, pl = self.price(tk), r.get("pct"), r.get("value_now"), r.get("pnl")
        plp = r.get("pnl_pct")
        stock = [x for x in self.events(tk, d0) if x[1] == "stock" and x[2]]
        mult = 1.0
        for x in stock:
            mult *= 1 + x[2]
        adj = []
        if stock:
            adj = [" · vị thế sau CP thưởng/cổ tức CP ≈ ", to_locale(round(p["position"] * mult), "en"), " cp, giá vốn ≈ ",
                   to_locale(round(p["costAvg"] / mult), "en"), tier("E")]
        return h("div", {"marginBottom": 14},
                 h("div", {"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)", "gap": 10, "padding": "10px 12px",
                           "background": C.ochre + "10", "borderRadius": 2, "borderLeft": "2px solid " + C.ochre},
                   Stat("GIÁ " + _dm(getattr(px, "asof", None)), self.num(px, to_locale(px.value, "en") if self.ok(px) else "")),
                   Stat("Δ TỪ " + _dm(d0) + " (QUY ĐỔI)", self.num(pc, _pct(pc.value) if self.ok(pc) else ""),
                        color=_pn(pc.value) if self.ok(pc) else None),
                   Stat("MV ƯỚC", self.num(vn, to_fixed(vn.value / 1e9, 2) + " tỷ" if self.ok(vn) else "")),
                   Stat("P&L ƯỚC TỚI NAY", self.num(pl, ("+" if self.ok(pl) and pl.value >= 0 else "") +
                                                     to_fixed(pl.value / 1e6, 0) + "tr" if self.ok(pl) else ""),
                        sub=[_pct(plp.value), " so vốn gốc"] if self.ok(plp) else None,
                        color=_pn(pl.value) if self.ok(pl) else None)),
                 h("div", {**_NOTE, "fontSize": 9, "color": C.inkM, "marginTop": 4}, *self._steps_text(tk, d0), *adj),
                 key="p08.pos.live." + tk)

    def _book_line(self, tk):
        x, y, wa, ha = self.book(tk)
        k = (to_locale(x["nav"], "en") + "%" + ("" if x["verified"] else " UNVERIFIED")) if x else (wa or "—")
        v = (to_locale(y["nav"], "en") + "%") if y else (ha or "—")
        big = any(z and z["nav"] > 5 for z in (x, y))
        return h("div", {"marginTop": 6, "fontFamily": F_MONO, "fontSize": 9, "letterSpacing": ".1em", "color": C.ochre},
                 "ACTION CẦN KIỂM CHỨNG · sổ hiện hành: Khối 11 ", k, " · HĐCV ", v, tier("E"),
                 " · >5% NAV → Synthesis L1+L2+L3; không lệnh nào đặt từ đây" if big else
                 " · không lệnh nào đặt từ đây")

    def action_note(self, tk):
        e = self.entry("p08", "current", tk, "action")
        return h("div", {"marginTop": 6, "fontSize": 11, "color": C.inkD},
                 *(self.render(e) if e else []), self._book_line(tk))

    def thesis_note(self, sec, tk):
        e = self.entry("p08", "current", tk, "thesis") if sec == "current" else self.entry("p08", "add", tk)
        if not e:
            return None
        return h("div", {"marginTop": 6, "fontStyle": "normal", "color": C.ink,
                         "fontSize": 11 if sec == "add" else 10}, *self.render(e))

    # ── Tab 08: Section B ───────────────────────────────────────────────────

    def pattern_q(self, tk, text):
        """Câu V21 gắn mã ngoài 30 mã Toàn Vũ: 'Pattern X' → 'Pattern X?' (CLAUDE.md §6 luật 4, DESIGN §8.4; cùng cách
        tab codong). Không đọc được danh sách 30 mã → coi như ngoài danh sách."""
        return text if tk in (self._call("tv30") or []) else _PAT_Q.sub(r"Pattern \1?", str(text))

    def add_live(self, p):
        tk = p["tk"]
        px, pc = self.price(tk), self.pct(tk, D0_POS)
        ez, f = self.conv(tk, p["entry"], D0_POS)
        tz, _ = self.conv(tk, p["target"], D0_POS)
        wh = self.where(tk, p["entry"], D0_POS)
        ev = " · ".join(x[3] for x in self.events(tk, D0_POS)) or "không có GDKHQ"
        return h("div", {**_NOTE, "marginBottom": 10, "padding": "6px 10px", "background": C.ochre + "10",
                         "borderRadius": 2},
                 "↻ ", _dmy(getattr(px, "asof", None)), ": giá ", *self.num(px, to_locale(px.value, "en") if self.ok(px) else ""),
                 " · Δ từ 08/05 (quy đổi) ", h("span", {"color": _pn(pc.value) if self.ok(pc) else C.ink, "fontWeight": 700},
                                              *self.num(pc, _pct(pc.value) if self.ok(pc) else "")),
                 " · vùng mua V21 quy đổi ", *([ez, tier("E")] if ez else ["= V21 (không có mức K)"]),
                 (" (giá " + wh + ")") if wh else None,
                 " · target V21 quy đổi ", *([tz, tier("E")] if tz else ["—"]),
                 " — ngưỡng V21, không phải khuyến nghị mới",
                 " · sự kiện quyền: ", ev, tier("T2") if self.events(tk, D0_POS) else None)

    def _win(self, tk, n=60):
        ph = self._call("price_history", tk)
        if ph is None or len(ph) < 2:
            return (D0_POS, None)
        b = len(ph) - 1
        return (ph.dates[max(0, b - n)], ph.dates[b])

    # ── Tab 08: Section C ───────────────────────────────────────────────────

    def avoid_reason(self, p):
        """Viết lại ô lý do: mệnh đề dữ kiện đã đổi thay bằng dữ kiện mới (↻ + bậc); mệnh đề stance giữ + V21·12/05."""
        tk = p["tk"]
        e = self.entry("p08", "avoid", tk)
        v21 = lambda t: [t, v21_mark(), " "]  # noqa: E731
        if tk == "DGC":
            return self.render(e) + [" "] + v21("Value trap risk.")[:2] if e else None
        if tk == "VIC,VHM,VRE":
            got = [(t,) + self._flow4(t, 60) for t in ("VIC", "VHM", "VRE")]
            nn = [(t, (f4 or {}).get("nn"), adj) for t, f4, adj in got]
            if not all(self.ok(v) for _, v, _ in nn):
                live = [can_data("thiếu foreign_net 60 phiên")]
            else:
                tot = js_sum(v.value for _, v, _ in nn)
                adjs = ["%s %s" % (t, a) for t, _, a in nn if a]
                live = ["NN 60 phiên tới %s trong 3 mã: %sM (" % (_dm(nn[0][1].asof), to_fixed(tot, 1)),
                        " · ".join("%s %s" % (t, to_fixed(v.value, 1)) for t, v, _ in nn), ")",
                        tier("E" if adjs else "T2", nn[0][1].asof),
                        (" — " + "; ".join(adjs)) if adjs else None]
            px = self.price("VIC")
            return (v21("Phase 3D distribution clear.") + live + [" "] + self.render(e) + [" "] +
                    v21("Đợi mean reversion tới 175-185K VIC để tham gia lại")[:2] +
                    [" — VIC "] + self.num(px, to_locale(px.value, "en") if self.ok(px) else "") +
                    [" (%s)" % (self.where("VIC", "175-185K", D0_POS) or "?")])
        if tk in ("VJC", "GEE"):
            pc = self.pct(tk, D0_POS)
            ev = " · ".join(x[3] for x in self.events(tk, D0_POS))
            live = ["Δ 08/05→%s (quy đổi%s) " % (_dm(getattr(pc, "asof", None)), (" " + ev) if ev else "")] + \
                self.num(pc, _pct(pc.value) if self.ok(pc) else "") + [". "]
            tail = ("P/E forward 25-30x airline cyclical = quá cao. NN distribution. Sovico Group đang giảm ownership theo "
                    "Luật TCTD" if tk == "VJC" else
                    "Risk-reward awful for new entry. Existing holders hold; new buyers wait split-adjusted")
            return live + self.render(e) + [" "] + v21(tail)[:2]
        return None

    # ── Tab 08: Section D ───────────────────────────────────────────────────

    def rotation_sub(self):
        r = self.entry("p08", "rotation") or {}
        return [status_pill(r.get("status") or "HẾT HẠN"), " ",
                r.get("text") or "cửa sổ 90 ngày từ 08/05/2026 đã hết", tier(r["tier"]) if r.get("tier") else None,
                v21_mark()]

    def _zone_line(self, tk, label, zone):
        z, _ = self.conv(tk, zone, D0_POS)
        px = self.price(tk)
        return h("div", None, label, " ", zone, " ≈ ", *([z, tier("E")] if z else [can_data()]),
                 " · giá ", *self.num(px, to_locale(px.value, "en") if self.ok(px) else ""),
                 (" · " + self.where(tk, zone, D0_POS)) if self.where(tk, zone, D0_POS) else None)

    def rotation_note(self, i):
        box = {**_NOTE, "fontSize": 9, "marginTop": 10, "paddingTop": 8, "borderTop": "1px dashed " + C.rule}
        head = h("div", {"color": C.ochre, "letterSpacing": ".12em", "marginBottom": 2},
                 "↻ ĐIỀU KIỆN GIÁ V21 QUY ĐỔI 08/05 → CUỐI (E) · KHÔNG PHẢI KHUYẾN NGHỊ MỚI" if i < 2
                 else "↻ ĐỐI CHIẾU SỔ HIỆN HÀNH (KHỐI 11 / HĐCV, E)")
        card = self.entry("p08", "rotation", "cards", str(i + 1))
        extra = h("div", {"marginTop": 4}, *self.render(card)) if card else None
        if i == 0:
            return h("div", box, head, self._zone_line("FPT", "FPT hồi", "75-78K"),
                     self._zone_line("VCB", "VCB vùng", "62-64K"), extra)
        if i == 1:
            return h("div", box, head, self._zone_line("GEX", "GEX", "25/26/27K"),
                     self._zone_line("HPG", "HPG", "25-27K"), self._zone_line("BSR", "BSR", "20-22K"), extra)
        tgt = (("MSN", "25-30%"), ("GEX", "5-7%"), ("HPG", "3-5%"), ("BSR", "2-3%"), ("VCI", "2-3%"), ("VCB", "15%"))
        bits = []
        for tk, w in tgt:
            x, y, _, _ = self.book(tk)
            bits.append("%s %s ↔ %s/%s" % (tk, w, to_locale(x["nav"], "en") if x else "—",
                                          to_locale(y["nav"], "en") if y else "—"))
        a, b = self.pc.get("lk_khoi11_1009") or {}, self.pc.get("hdcv_1209") or {}
        bits.append("Cash 35-40%% ↔ %s/%s" % (to_locale(a.get("cash"), "en") if a.get("cash") is not None else "—",
                                              to_locale(b.get("cash"), "en") if b.get("cash") is not None else "—"))
        return h("div", box, head, h("div", None, " · ".join(bits), tier("E")), extra)

    def milestone(self, tk):
        e = self.entry("p08", "milestones", tk)
        if not e:
            return None
        out = [" "] + self.render(e)
        if tk == "VJC":
            px = self.price("VJC")
            out += [" Giá VJC "] + self.num(px, to_locale(px.value, "en") if self.ok(px) else "") + \
                [" (%s)." % (self.where("VJC", "130-140K", D0_POS) or "?")]
        return out

    # ── Tab 13 ──────────────────────────────────────────────────────────────

    def p25_intro(self):
        return h("div", {"fontSize": 11, "fontFamily": F_SERIF, "color": C.inkD, "lineHeight": 1.7, "marginBottom": 12,
                         "padding": "8px 14px", "background": C.parch, "borderLeft": "3px solid " + C.ochre},
                 h("strong", {"color": C.ochre, "fontFamily": F_MONO, "fontSize": 9, "letterSpacing": ".18em"},
                   "BẢN LƯU V21 · 12/05 · "),
                 "ACTION, TỶ TRỌNG, ENTRY, NOTE giữ nguyên văn, không chấm lại (", self._cong(), "). Cột mới: giá cuối ",
                 "(T2) · Δ từ 12/05 (E; giá điều chỉnh vendor khi có GDKHQ, giá thô khi không có) · sổ hiện hành "
                 "Khối 11 / HĐCV (E) · trạng thái dữ kiện (↻ theo facts, nhãn bậc từng mệnh đề; trạng thái claim lấy từ "
                 "tab claims). Không lệnh nào đặt từ bảng này; >5% NAV → Synthesis L1+L2+L3.", upd_mark(UPD),
                 key="p25.intro")

    def p25_head(self):
        th = lambda t, al="left": h("th", {"textAlign": al, "padding": "8px 10px", "whiteSpace": "nowrap"}, t)  # noqa
        dt = self._call("data_to")
        return [th("GIÁ " + _dm(dt), "right"), th("Δ 12/05→" + _dm(dt), "right"), th("SỔ K11 · HĐCV"),
                th("TRẠNG THÁI DỮ KIỆN")]

    def p25_cells(self, p):
        tk = p["tk"]
        px, pc = self.price(tk), self.pct(tk, D0_P25)
        x, y, wa, ha = self.book(tk)
        k = (to_locale(x["nav"], "en") + ("" if x["verified"] else " U")) if x else (wa or "—")
        v = to_locale(y["nav"], "en") if y else (ha or "—")
        conflict = tk in {c.get("tk") for c in self.pc.get("conflicts") or []}
        ev = self.events(tk, D0_P25)
        st = []
        if ev:
            st += ["GDKHQ " + " · ".join(e[3] for e in ev), tier("T2")]
        z, _ = self.conv(tk, p["entry"], D0_P25) if any(e[1] in ("stock", "div") for e in ev) else (None, None)
        if z:
            st += [" → entry ≈ ", z, tier("E")]
            wh = self.where(tk, p["entry"], D0_P25)
            if wh:
                st += [" (" + wh + ")"]
        if any(e[1] == "stock" for e in ev) and p["entry"] == "-":
            st += [" · giá thô không so trực tiếp với 12/05"]
        de = self.entry("p25", tk)
        if de:
            st += (["; "] if st else []) + self.render(de)
        td = {"padding": "8px 10px"}
        return [
            h("td", {**td, "textAlign": "right", "fontFamily": F_MONO, "fontSize": 10},
              *self.num(px, to_locale(px.value, "en") if self.ok(px) else "")),
            h("td", {**td, "textAlign": "right", "fontFamily": F_MONO, "fontSize": 10, "fontWeight": 700,
                     "color": _pn(pc.value) if self.ok(pc) else C.ink},
              *self.num(pc, _pct(pc.value) if self.ok(pc) else "")),
            h("td", {**td, "fontFamily": F_MONO, "fontSize": 10, "whiteSpace": "nowrap",
                     "color": C.vermillion if conflict else C.inkD},
              k, " · ", v, tier("E") if (x or y or wa or ha) else None),
            h("td", {**td, "color": C.inkD, "fontSize": 10, "lineHeight": 1.4, "minWidth": 260},
              *(st or ["—"])),
        ]

    # ── CSV ─────────────────────────────────────────────────────────────────

    def csv_portfolio(self, pa):
        rows = []
        for bk, key in ((self.pc.get("lk_khoi11_1009") or {}, "lk_khoi11"), (self.pc.get("hdcv_1209") or {}, "hdcv")):
            for x in bk.get("positions") or []:
                px = self.price(x["tk"])
                rows.append({"so": key, "ngay_so": bk.get("date"), "ma": x["tk"], "nav_pct": x["nav"],
                             "verified": x["verified"], "bac": "EST" if x["verified"] else "UNVERIFIED",
                             "gia": px.value if self.ok(px) else "[CẦN DATA]",
                             "ngay_gia": getattr(px, "asof", None)})
        return rows

    def csv_p25(self, rows):
        out = []
        for p in rows:
            px, pc = self.price(p["tk"]), self.pct(p["tk"], D0_P25)
            out.append({"ma": p["tk"], "cat": p["cat"], "act_v21": p["act"], "w_v21": p["w"], "entry_v21": p["entry"],
                        "gia": px.value if self.ok(px) else "[CẦN DATA]", "ngay_gia": getattr(px, "asof", None),
                        "pct_tu_1205_E": round(pc.value, 2) if self.ok(pc) else "[CẦN DATA]"})
        return out
