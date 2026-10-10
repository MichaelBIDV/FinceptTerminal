#!/usr/bin/env python3
"""
chaebol_map_tab_audit_live — lớp dữ liệu sống cho tab `10 · DATA & METRIC AUDIT` (chỉ mode live).

Nguồn (chỉ đọc, không mạng): chaebol_map_data (so_nguon_audit, vc_lk, vnstore, primary_facts…) + dossier khối `audit`
(cap_nhat_<ngày>.audit.json — văn bản viết lại, ánh xạ pipeline → tài sản Sổ nguồn, mỗi mục tier/asof/src).
Không có dossier → giữ văn bản V21 + dấu V21·12/05, vẫn thêm số sống (freshness, độ phủ, kiểm 8 luật QC).

Luật (DESIGN §6, page_p8 §6–§7): mỗi số có nhãn bậc hoặc [CẦN DATA]; nhận định V21 không chấm lại (V21·12/05);
luật QC có điều kiện đo được → chấm lại bằng dữ liệu (ĐẠT / BỊ BÁC / CHƯA RÕ / LIVE / HẾT HẠN) kèm bằng chứng + bậc;
dòng tiền sau 08/05 chỉ NN + tự doanh là số thật (cá nhân/tổ chức nội = [CẦN DATA]); FiinTrade ≤08/05 đóng băng;
rổ VN30 hiện hành = vnstore.ma.nhom (không bang_vn30). Không in email/licence cá nhân.
"""
from __future__ import annotations

import re
import sys
import traceback
from datetime import date, datetime, time, timedelta, timezone

from chaebol_map_dom import (C, F_MONO, can_data, h, norm_tier, status_pill, tier, to_fixed, to_locale, upd_mark,
                             v21_mark)

FOCUS_LABEL = "SỔ NGUỒN"
STATUS_COLOR = {"TƯƠI": C.forest, "CŨ": C.ochre, "HỎNG": C.vermillion, "THIẾU": C.vermillion,
                "KHÔNG ĐO": C.inkM, "CẤM": C.vermillion}
_RANK = {"THIẾU": 4, "HỎNG": 4, "CẤM": 4, "CŨ": 3, "KHÔNG ĐO": 2, "TƯƠI": 1}
_EVENT_EPS = ("insider-transaction", "proprietary-history", "events-v2", "shareholder")
_RULE_KIND = (("zero-sum", "zero_sum"), ("foreign room", "room"), ("price range", "price"),
              ("cross-source", "cross"), ("insider", "insider"), ("agm", "agm"), ("bull/bear", "sig"),
              ("legal", "legal"))
S_LIVE_BOX = {"marginBottom": 14, "padding": "10px 14px", "background": C.parch, "fontFamily": F_MONO,
              "fontSize": 10, "lineHeight": 1.7, "color": C.inkD}
S_LBL = {"color": C.gold, "fontWeight": 600, "letterSpacing": ".12em", "fontSize": 9}
ICT = timezone(timedelta(hours=7))
ADJ_CUT = "2026-05-08"          # mốc FiinTrade/V21: so giá qua sự kiện quyền sau mốc này phải quy đổi (DESIGN §6.6)


def _tag(bac):
    """Bậc của Sổ nguồn → bậc DESIGN §6. NEWS = báo chí chưa có văn bản gốc → UNVERIFIED (U): T3 của chú giải là
    sell-side/Toàn Vũ, không phải báo; kết luận chỉ theo CBTT/FACT-T1. Lạ/None → None."""
    if not bac:
        return None
    if str(bac).upper() == "NEWS":
        return "UNVERIFIED"
    try:
        return norm_tier(bac)
    except ValueError:
        return None


def _iso(s):
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(s or ""))
    return "%s-%s-%s" % m.groups() if m else None


def _dmy(s):
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(s or ""))
    return "%s/%s/%s" % (m.group(3), m.group(2), m.group(1)) if m else None


def _dm(s):
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(s or ""))
    return "%s/%s" % (m.group(3), m.group(2)) if m else None


def _pct(x, d=2):
    return to_fixed(x, d) + "%"


def _last(vals, i):
    while i >= 0:
        if vals[i] is not None:
            return vals[i], i
        i -= 1
    return None, -1


def _ts(s):
    """Mốc ISO (có/không múi giờ) → datetime có múi giờ (thiếu múi → ICT); hỏng → None."""
    try:
        t = datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=ICT)


class LiveAudit:
    """Một lần dựng: đọc Sổ nguồn + quét 45 mã audit một lượt; builder hỏi qua các phương thức bên dưới."""

    def __init__(self, ctx, pipes, rules, layout, tickers):
        self.ctx, self.D = ctx, ctx.data
        self.pipes, self.rules, self.layout = pipes, rules, layout
        self.tickers = [str(t) for t in tickers]
        dz = (ctx.dossier or {}).get("audit") if isinstance(ctx.dossier, dict) else None
        self.dz = dz if isinstance(dz, dict) else {}
        if not self.dz:
            ctx.warn("dossier chưa có khối 'audit' (cap_nhat_<ngày>.audit.json) — giữ văn bản V21 + dấu V21·12/05")
        if self.D is None:
            ctx.warn("không có chaebol_map_data — số sống của tab audit = [CẦN DATA]")
        self.data_to = (ctx.live_info or {}).get("data_to") or self._safe("data_to", lambda: self.D.data_to())
        sa = self._safe("source_audit", lambda: self.D.source_audit()) or {}
        self.sa_time = sa.get("cap_nhat")
        self.assets = {a["id"]: a for a in sa.get("tai_san") or [] if isinstance(a, dict) and a.get("id")}
        # source_audit() không trả sla_gio (chỉ nguong_gio = ngưỡng đã nâng cuối tuần) → đọc thẳng tệp, cùng lần cập nhật
        raw = self._safe("so_nguon sla", lambda: self._extra_json("fincept_bridge/data/so_nguon_audit.json")) or {}
        if raw.get("cap_nhat") == self.sa_time:
            for r in raw.get("tai_san") or []:
                if isinstance(r, dict) and r.get("id") in self.assets:
                    self.assets[r["id"]] = {**self.assets[r["id"]], "sla_gio": r.get("sla_gio")}
        # lúc dựng: giờ thật, kẹp trần cuối ngày ctx.today (build/test với ngày cố định cho kết quả tất định)
        self.now = min(datetime.now(ICT), datetime.combine(ctx.today, time(23, 59, 59), ICT))
        self._cov = {}
        self._ph = {}
        self.px = self._safe("quét giá 45 mã", self._scan_prices) or {}
        self.checks = {}
        for kind, fn in (("zero_sum", self._chk_zero_sum), ("room", self._chk_room), ("price", self._chk_price),
                         ("cross", self._chk_cross), ("insider", self._chk_insider), ("agm", self._chk_agm),
                         ("sig", self._chk_sig), ("legal", self._chk_legal)):
            self.checks[kind] = self._safe("kiểm luật " + kind, fn) or {
                "status": "CHƯA RÕ", "parts": [can_data("lỗi khi kiểm — xem cảnh báo")]}

    # ── tiện ích ────────────────────────────────────────────────────────────

    def _safe(self, what, fn):
        if self.D is None:
            return None
        try:
            return fn()
        except Exception as exc:  # dữ liệu hỏng không được làm hỏng tab
            self.ctx.warn("audit/%s lỗi: %s: %s" % (what, type(exc).__name__, exc))
            print(traceback.format_exc(), file=sys.stderr)
            return None

    def _pipe_dz(self, pid):
        p = (self.dz.get("pipelines") or {}).get(pid)
        return p if isinstance(p, dict) else {}

    def _asset(self, aid):
        return self.assets.get(aid)

    def _future_moc(self, a):
        """Mốc Sổ nguồn nằm sau lúc dựng (vd headlines: tin 'đăng trước' làm khoá do_tuoi) → datetime, ngược lại None."""
        t = _ts((a or {}).get("moc"))
        return t if t is not None and t > self.now else None

    def _status(self, aid):
        """Trạng thái hiển thị: theo Sổ nguồn; mốc tương lai → KHÔNG ĐO (tuổi/độ tươi không đo được)."""
        a = self._asset(aid)
        if a is None:
            return "THIẾU"
        return "KHÔNG ĐO" if self._future_moc(a) else (a.get("trang_thai") or "THIẾU")

    def _worst(self, ids):
        sts = [self._status(a) for a in ids]
        return max(sts, key=lambda s: _RANK.get(s, 2)) if sts else None

    def _segments(self, segs):
        """[{text, tier?, asof?, v21?, em?}] (dossier) → nút; chuỗi trần giữ nguyên."""
        out = []
        for s in segs or []:
            if isinstance(s, str):
                out.append(s)
            elif isinstance(s, dict) and isinstance(s.get("text"), str):
                out.append(h("em", None, s["text"]) if s.get("em") else s["text"])
                if s.get("tier") and s.get("src"):
                    out.append(tier(s["tier"], s.get("asof")))
                if s.get("v21"):
                    out.append(v21_mark())
        return out

    # ── quét dữ liệu (một lượt cho 45 mã) ───────────────────────────────────

    def _scan_prices(self):
        """Giá/room/cp phiên cuối (vc_lk price-history; trường trống ở phiên cuối → lùi phiên có số, ghi ĐÚNG ngày —
        DESIGN §9) + giá vnstore.nen_ngay cùng ngày để đối chiếu nguồn."""
        out = {}
        for tk in self.tickers:
            ph = self.D.price_history(tk)
            if not ph or not len(ph) or not str(getattr(ph, "base", "")).startswith("vc_lk"):
                out[tk] = None
                continue
            self._ph[tk] = ph
            i = len(ph) - 1
            rec = {"date": ph.dates[i], "n": len(ph)}
            for f, k in (("closePrice", "close"), ("foreignOwnedPercentage", "owned"),
                         ("foreignRoomPercentage", "room"), ("totalShares", "shares")):
                v, j = _last(ph.col(f), i)
                rec[k], rec[k + "_d"] = v, (ph.dates[j] if j >= 0 else None)
            row = self.D.db_query("SELECT dong FROM nen_ngay WHERE symbol=? AND ngay=?", (tk, rec["close_d"]))
            rec["vns"] = row[0][0] if row and row[0][0] is not None else None
            out[tk] = rec
        return out

    def _shares_at(self, tk, d):
        """totalShares tại ngày d (phiên cuối ≤ d; trống → lùi phiên có số — DESIGN §9) → (cp, ngày của số).
        d=None → phiên cuối có số; d trước dòng đầu → (None, None)."""
        ph = self._ph.get(tk)
        if ph is None:
            return None, None
        i = ph.at(d) if d else len(ph) - 1
        v, j = _last(ph.col("totalShares"), i)
        return v, (ph.dates[j] if j >= 0 else None)

    def adj_events(self):
        """Mã có sự kiện quyền sau ADJ_CUT: factor = closePriceAdjusted/closePrice tại phiên ≤ ADJ_CUT so với phiên cuối
        (phiên cuối factor = 1). Trả [(mã, % điều chỉnh tích luỹ)] — gồm cả cổ tức tiền."""
        out = []
        for tk in self.tickers:
            ph = self._ph.get(tk)
            if ph is None:
                continue
            i, n = ph.at(ADJ_CUT), len(ph) - 1
            c, a = ph.col("closePrice"), ph.col("closePriceAdjusted")
            if i < 0 or not (c[i] and a[i] and c[n] and a[n]):
                continue
            r = (a[i] / c[i]) / (a[n] / c[n])
            if r < 0.995:
                out.append((tk, (1 - r) * 100))
        return out

    def coverage(self, ep):
        """Độ phủ endpoint vc_lk trên 45 mã: (n có tệp, min/max du_lieu_toi hoặc ngày lấy)."""
        if ep in self._cov:
            return self._cov[ep]
        n, dates = 0, []
        for tk in self.tickers:
            fr = (self._safe("freshness", lambda: self.D.freshness(tk)) or {}).get(ep) or {}
            if fr.get("trang_thai") == "ok":
                n += 1
                d = _iso(fr.get("du_lieu_toi")) or _iso(fr.get("lay_luc"))
                if d:
                    dates.append(d)
        kind = ("lấy" if ep in ("shareholder-structure", "relationship", "details") else
                "sự kiện mới nhất" if ep in _EVENT_EPS else "dữ liệu tới")
        res = {"n": n, "total": len(self.tickers), "min": min(dates) if dates else None,
               "max": max(dates) if dates else None, "kind": kind}
        self._cov[ep] = res
        return res

    @staticmethod
    def _dmin(cv):
        """Ngày sớm nhất: dd/mm nếu cùng năm với ngày mới nhất, ngược lại dd/mm/yyyy (tránh '23/10' của năm trước)."""
        lo, hi = cv.get("min"), cv.get("max")
        if not lo:
            return "?"
        return _dm(lo) if hi and lo[:4] == hi[:4] else _dmy(lo)

    def _primary(self):
        p = self.D.sys_dir() / "knowledge_os" / "primary_filings" / "primary_facts.json"
        d = self.D.read_json(p, quiet=True)
        return d if isinstance(d, dict) else {}

    def _extra_json(self, rel):
        d = self.D.read_json(self.D.sys_dir() / rel, quiet=True)
        return d if isinstance(d, dict) else {}

    # ── kiểm lại 8 luật QC (DATA_AUDIT_VALIDATION_RULES) trên dữ liệu thật ──

    def _chk_zero_sum(self):
        fl = (self.ctx.v21 or {}).get("FLOW") or {}
        ok = n = 0
        for tk in self.tickers:
            f = fl.get(tk)
            if not isinstance(f, dict):
                continue
            n += 1
            s = f["ca60"] + f["to60"] + f["td60"] + f["nn60"]
            g = abs(f["ca60"]) + abs(f["to60"]) + abs(f["td60"]) + abs(f["nn60"])
            ok += 1 if (g == 0 or abs(s) <= 0.05 * g) else 0
        return {"status": "HẾT HẠN",
                "parts": ["≤08/05 (FiinTrade, đóng băng): %d/%d mã |Σ| ≤ 5%% tổng tuyệt đối" % (ok, n),
                          tier("EST", "2026-05-08"),
                          " · ≥09/05: kênh NgườiQuanSát 5-ch ngừng; chỉ còn NN + tự doanh → thiếu 1 phương trình, ",
                          can_data("không kiểm được")]}

    def _chk_room(self):
        rows = [(tk, r) for tk, r in self.px.items() if r and r.get("owned") is not None and r.get("room") is not None]
        bad = [(tk, r) for tk, r in rows if r["owned"] > r["room"] + 1e-6]
        d = max((r["room_d"] for _, r in rows if r.get("room_d")), default=None)
        dmin = min((r["room_d"] for _, r in rows if r.get("room_d")), default=None)
        parts = ["%d/%d mã sở hữu NN ≤ room theo FOL từng mã (vc_lk; phiên có số %s–%s)"
                 % (len(rows) - len(bad), len(self.tickers), _dm(dmin), _dm(d)), tier("FACT-T2", d)]
        if bad:
            parts.append(" · lệch: " + ", ".join("%s room %s < sở hữu %s" % (tk, _pct(r["room"] * 100),
                                                                              _pct(r["owned"] * 100)) for tk, r in bad))
            parts.append(tier("FACT-T2", d))
        full = [tk for tk, r in rows if r["room"] >= 0.999]
        if full:
            parts.append(" · hằng [0, 49] của V21 sai với mã room 100%%: %s" % ", ".join(full))
        return {"status": "ĐẠT" if not bad and len(rows) == len(self.tickers) else "CHƯA RÕ", "parts": parts,
                "asof": d}

    def _chk_price(self):
        rows = [(tk, r) for tk, r in self.px.items() if r and r.get("close") is not None]
        bad = [tk for tk, r in rows if not (1000 <= r["close"] <= 1000000)]
        d = max((r["close_d"] for _, r in rows), default=None)
        parts = ["%d/%d mã trong [1,000; 1,000,000] đ (vc_lk closePrice)" % (len(rows) - len(bad), len(self.tickers)),
                 tier("FACT-T2", d)]
        if bad:
            parts.append(" · ngoài khoảng: " + ", ".join(bad))
        if len(rows) < len(self.tickers):
            parts += [" · ", can_data("thiếu giá: " + ", ".join(t for t in self.tickers if not self.px.get(t)))]
        return {"status": "ĐẠT" if not bad and len(rows) == len(self.tickers) else "BỊ BÁC" if bad else "CHƯA RÕ",
                "parts": parts, "asof": d}

    def _chk_cross(self):
        both = [(tk, r) for tk, r in self.px.items() if r and r.get("close") and r.get("vns")]
        bad = [tk for tk, r in both if abs(r["vns"] / r["close"] - 1) >= 0.005]
        miss = [tk for tk in self.tickers if not (self.px.get(tk) or {}).get("vns")]
        d = max((r["close_d"] for _, r in both), default=None)
        parts = ["cafef↔vietstock thay bằng vc_lk ↔ vnstore.nen_ngay cùng phiên: %d/%d mã lệch < 0.5%%"
                 % (len(both) - len(bad), len(both)), tier("FACT-T2", d)]
        if bad:
            parts.append(" · lệch ≥0.5%: " + ", ".join(bad))
        if miss:
            parts.append(" · vnstore không có phiên đó: " + ", ".join(miss))
        return {"status": "ĐẠT" if both and not bad else ("BỊ BÁC" if bad else "CHƯA RÕ"), "parts": parts, "asof": d}

    def _insider_rows(self, since):
        """% cp lưu hành tính trên totalShares tại NGÀY GIAO DỊCH (endDate → startDate → publicDate), không phải phiên
        cuối — phát hành thêm sau ngày giao dịch làm lệch mẫu số (DESIGN §9: ngày của chính số liệu)."""
        out = []
        for tk in self.tickers:
            v = self.D.insider_tx(tk, since=since)
            for r in (v.value or []) if v is not None and v.value is not None else []:
                q = r.get("acquire") if r.get("status") == "da_xong" else r.get("register")
                if q is None:
                    continue
                trade_d = r.get("end") or r.get("start") or r.get("public_date")
                sh, sh_d = self._shares_at(tk, trade_d)
                pct = abs(q) / sh * 100 if sh else None
                out.append({"tk": tk, "q": q, "pct": pct, "sh_d": sh_d, "trade_d": trade_d,
                            "done": r.get("status") == "da_xong", **r})
        return out

    def _chk_insider(self):
        if not self.data_to:
            return {"status": "CHƯA RÕ", "parts": [can_data("không rõ ngày dữ liệu")]}
        since = (date.fromisoformat(self.data_to) - timedelta(days=7)).isoformat()
        rows = self._insider_rows(since)
        hit = [r for r in rows if r["done"] and (abs(r["q"]) >= 100000 or (r["pct"] or 0) >= 0.5)]
        reg = [r for r in rows if not r["done"] and (abs(r["q"]) >= 100000 or (r["pct"] or 0) >= 0.5)]
        mas = sorted({r["tk"] for r in hit})
        done = ("%d giao dịch hoàn tất vượt ngưỡng ở %d mã (%s)" % (len(hit), len(mas), ", ".join(mas)) if hit
                else "không có giao dịch hoàn tất vượt ngưỡng")
        parts = ["7 ngày tới %s: %s · %d đăng ký vượt ngưỡng" % (_dm(self.data_to), done, len(reg)),
                 tier("FACT-T2", self.data_to), " · không có giá thực hiện (vùng giá = EST)"]
        return {"status": "LIVE", "parts": parts, "asof": self.data_to}

    def insider_example(self):
        """Giao dịch HOÀN TẤT gần nhất ≥0,5% cp lưu hành trong 45 mã (90 ngày tới data_to) — thay ví dụ VCI 04/05."""
        if not self.data_to:
            return [can_data("không rõ ngày dữ liệu")]
        since = (date.fromisoformat(self.data_to) - timedelta(days=90)).isoformat()
        rows = [r for r in self._safe("insider 90 ngày", lambda: self._insider_rows(since)) or []
                if r["done"] and (r["pct"] or 0) >= 0.5]
        if not rows:
            return [can_data("không có giao dịch hoàn tất ≥0.5% trong 90 ngày")]
        r = max(rows, key=lambda x: (x["trade_d"] or "", x.get("public_date") or "", x["pct"]))
        who = r.get("trader") or "[không rõ tên]"
        act = r.get("action_vi") or ("Mua" if r["q"] > 0 else "Bán")
        st, en = r.get("start"), r.get("end")
        when = ("%s–%s" % (_dm(st), _dmy(en))) if st and en and st != en else _dmy(r["trade_d"])
        pub = (" (công bố %s)" % _dmy(r.get("public_date"))) if r.get("public_date") != r["trade_d"] else ""
        return ["%s giao dịch %s%s — %s %s %s cp" % (r["tk"], when, pub, who, act.lower(),
                                                     to_locale(abs(r["q"]), "en-US")),
                tier("FACT-T2", r["trade_d"]),
                " (%s cp lưu hành tại ngày giao dịch" % _pct(r["pct"]), tier("EST", r.get("sh_d")),
                ("; sở hữu sau %s" % _pct(r["own_after_pct"])) if r.get("own_after_pct") is not None else "",
                tier("FACT-T2", r["trade_d"]) if r.get("own_after_pct") is not None else None, ")"]

    def _agm_tickers(self):
        p = next((x for x in self.pipes if x.get("id") == "P1_AGM_EVENTS"), None)
        return re.findall(r"\b[A-Z]{3}\b", str((p or {}).get("tickers") or ""))

    def _chk_agm(self):
        pf = self._primary()
        facts = pf.get("facts") or {}
        tks = self._agm_tickers()
        have = [t for t in tks if ((facts.get(t) or {}).get("latest") or {}).get("DHCD") == "2026"]
        d = _iso(pf.get("generated_at"))
        return {"status": "HẾT HẠN",
                "parts": ["mùa ĐHĐCĐ 2026 đã qua (kế tiếp 03–06/2027) · tài liệu ĐHĐCĐ 2026 trong primary_facts: "
                          "%d/%d mã focus" % (len(have), len(tks)), tier("FACT-T1", d),
                          " · Actual = BCTC 6T/2026, không phải Q1"], "asof": d}

    def _chk_sig(self):
        fl = (self.ctx.v21 or {}).get("FLOW") or {}

        def rule(f):
            if (f["to60"] > 20 or f["nn60"] > 20) and f["ca60"] < 0:
                return "BULL"
            if f["nn60"] < -20 and f["ca60"] > 20:
                return "BEAR"
            return "MIX"
        rows = [(tk, fl[tk]) for tk in self.tickers if isinstance(fl.get(tk), dict)]
        diff = [tk for tk, f in rows if f.get("sig") != rule(f)]
        return {"status": "CHƯA RÕ",
                "parts": ["≥09/05: ", can_data("thiếu ca60/to60"),
                          " · ≤08/05: nhãn sig trong FLOW V21 khớp luật ở %d/%d mã" % (len(rows) - len(diff), len(rows)),
                          tier("EST", "2026-05-08"), v21_mark(),
                          (" (lệch: " + ", ".join(diff[:8]) + ("…" if len(diff) > 8 else "") + ")") if diff else ""]}

    def _chk_legal(self):
        g = self._asset("guong") or {}
        c = self._asset("vc_cbtt") or {}
        return {"status": "LIVE",
                "parts": ["nguồn thay: guong (feed RSS báo) %s" % (g.get("trang_thai") or "[không có dòng SO]"),
                          tier(_tag(g.get("bac")) or "SS-T3", g.get("moc")),
                          " + vc_cbtt %s" % (c.get("trang_thai") or "[không có dòng SO]"),
                          tier(_tag(c.get("bac")) or "FACT-T2", c.get("moc")),
                          " · kết luận pháp lý chỉ theo CBTT/cơ quan chính thức (FACT-T1), báo cần chéo ≥2 nguồn"]}

    # ── API cho builder ─────────────────────────────────────────────────────

    def intro_sub(self, v21_sub):
        it = self.dz.get("intro") or {}
        if isinstance(it.get("sub"), str):
            return [it["sub"], upd_mark(it.get("asof"))]
        return [v21_sub, v21_mark()]

    def intro_runs(self, v21_runs):
        it = self.dz.get("intro") or {}
        runs = it.get("runs")
        if not isinstance(runs, list) or not runs:
            return v21_runs + [v21_mark()]
        out = []
        for r in runs:
            if not (isinstance(r, list) and len(r) == 2):
                continue
            kind, text = r
            out.append(h("strong", {"color": C.ink}, text) if kind == "strong" else
                       h("em", None, text) if kind == "em" else text)
        return out + [upd_mark(it.get("asof"))]

    def stat_extra(self, key):
        """Dòng thứ hai của 5 thẻ số: trạng thái hiện hành (mỗi số một nhãn bậc)."""
        st = {"fontSize": 8, "color": C.inkM, "fontFamily": F_MONO, "marginTop": 4, "letterSpacing": ".05em"}
        if key in ("P0", "P1", "P23"):
            pre = {"P0": ("P0",), "P1": ("P1",), "P23": ("P2", "P3")}[key]
            ps = [p for p in self.pipes if str(p.get("priority", "")).startswith(pre)]
            n_ok = sum(1 for p in ps if self._worst(self._pipe_dz(p["id"]).get("assets") or []) == "TƯƠI")
            return h("div", st, "nguồn thay TƯƠI: %d/%d" % (n_ok, len(ps)),
                     tier("EST", _iso(self.sa_time)) if self.sa_time else None, key="aud.stat:" + key)
        if key == "TICKERS":
            b = self._safe("basket", lambda: self.D.basket("VN30"))
            if b is None or b.value is None:
                return h("div", st, can_data("rổ VN30 hiện hành"), key="aud.stat:" + key)
            miss = [t for t in b.value if t not in self.tickers]
            return h("div", st, "VN30 hiện hành thiếu %d: %s" % (len(miss), "·".join(miss)), tier(b.tier, b.asof),
                     key="aud.stat:" + key)
        if key == "VALIDATION":
            cnt = {}
            for c in self.checks.values():
                cnt[c["status"]] = cnt.get(c["status"], 0) + 1
            order = ("ĐẠT", "LIVE", "CHƯA RÕ", "BỊ BÁC", "HẾT HẠN")
            parts = ["%d %s" % (cnt[s], s) for s in order if cnt.get(s)]
            # ô 1/5 lưới hẹp (~260 px): kiểm chốt 27/09 thấy "2 HẾT / HẠN" ngắt giữa trạng thái → mỗi "N TRẠNG THÁI"
            # một span nowrap, chỉ ngắt ở " · "; nhãn bậc dính mục cuối. Ngày kiểm nằm ở nhãn bậc (E·dd/mm), bỏ tiền tố
            # "kiểm dd/mm:" để cả dòng vừa một hàng.
            kids = []
            for i, p in enumerate(parts):
                last = i == len(parts) - 1
                kids += [" · " if i else None,
                         h("span", {"whiteSpace": "nowrap"}, p, tier("EST", self.data_to) if last else None)]
            return h("div", st, *kids, key="aud.stat:" + key)
        return None

    def pipe_name(self, p):
        z = self._pipe_dz(p["id"]).get("name")
        return [z, upd_mark(self._pipe_dz(p["id"]).get("asof"))] if isinstance(z, str) and z else None

    def button_status(self, p):
        ids = self._pipe_dz(p["id"]).get("assets") or []
        if not ids:
            return h("div", {"fontSize": 8, "fontFamily": F_MONO, "marginTop": 3, "letterSpacing": ".05em"},
                     can_data("chưa ánh xạ Sổ nguồn"))
        w = self._worst(ids)
        return h("div", {"fontSize": 8, "fontFamily": F_MONO, "marginTop": 3, "letterSpacing": ".05em",
                         "color": STATUS_COLOR.get(w, C.inkD)}, "→ " + " · ".join(ids) + " · " + w)

    def _asset_row(self, aid):
        a = self._asset(aid)
        if a is None:
            return h("div", None, "→ ", h("span", {"color": C.gold, "fontWeight": 600}, aid), " · ",
                     can_data("không có dòng trong so_nguon_audit.json"))
        head = ["→ ", h("span", {"color": C.gold, "fontWeight": 600}, aid), " · ",
                h("span", {"color": C.ink}, a.get("duong_dan") or "?"), " · "]
        fut = self._future_moc(a)
        if fut is not None:
            return h("div", None, *head, h("span", {"color": STATUS_COLOR["KHÔNG ĐO"], "fontWeight": 600}, "KHÔNG ĐO"),
                     " · ", h("span", {"color": C.vermillion},
                              "mốc %s ở tương lai so với lúc dựng %s — lỗi khoá thời gian nguồn"
                              % (fut.astimezone(ICT).strftime("%d/%m/%Y %H:%M"), self.now.strftime("%d/%m %H:%M"))),
                     " (Sổ nguồn ghi %s; tuổi không đo được)" % (a.get("trang_thai") or "?"),
                     tier(_tag(a.get("bac")) or "EST"))
        st = a.get("trang_thai") or "?"
        age = ""
        if a.get("tuoi_gio") is not None:
            sla, ng = a.get("sla_gio"), a.get("nguong_gio")
            if sla is None:
                sla, ng = ng, None
            age = " · tuổi %sh%s" % (to_fixed(a["tuoi_gio"], 1), ("/SLA %sh" % to_fixed(sla, 0)) if sla else "")
            if sla and ng and float(ng) != float(sla):
                age += " (ngưỡng cuối tuần %sh)" % to_fixed(ng, 0)
        return h("div", None, *head, h("span", {"color": STATUS_COLOR.get(st, C.inkD), "fontWeight": 600}, st),
                 " · mốc %s%s" % (_dmy(a.get("moc")) or "?", age), tier(_tag(a.get("bac")) or "EST", _iso(a.get("moc"))))

    def _check_rows(self, pid):
        """Số đo riêng theo pipeline (mỗi dòng một nguồn, một nhãn bậc)."""
        rows = []
        if pid == "P0_FLOW_PILLAR_IV":
            nq = self._safe("nqs_flow", lambda: self._extra_json("alpha_spine/nqs_flow.json")) or {}
            bt = nq.get("by_ticker") or {}
            if bt:
                zero = sum(1 for v in bt.values() if isinstance(v, dict) and not v.get("ca"))
                # ngày của dữ liệu = as_of 'dd/mm' từng mã (mới nhất), không phải generated_at (giờ sinh tệp)
                ds = [m.groups() for v in bt.values() if isinstance(v, dict)
                      for m in [re.match(r"^(\d{1,2})/(\d{1,2})$", str(v.get("as_of") or ""))] if m]
                d = max(ds, key=lambda g: (int(g[1]), int(g[0]))) if ds else None
                rows.append(["nqs_flow (alpha_spine, chưa có dòng SO): kênh cá nhân = 0 ở %d/%d mã · cửa sổ %s phiên"
                             % (zero, len(bt), nq.get("window_sessions", "?")),
                             tier("SS-T3", ("%s/%s" % d) if d else None)])
            else:
                rows.append(["nqs_flow: ", can_data("không đọc được alpha_spine/nqs_flow.json")])
        elif pid == "P2_BCTC_QUARTERLY":
            pf = self._safe("primary_facts", self._primary) or {}
            facts = pf.get("facts") or {}
            if facts:
                n = sum(1 for t in self.tickers if ((facts.get(t) or {}).get("latest") or {}).get("BCTC") == "2026")
                rows.append(["primary_facts: có BCTC năm 2026 ở %d/%d mã" % (n, len(self.tickers)),
                             tier("FACT-T1", _iso(pf.get("generated_at")))])
            else:
                rows.append(["primary_facts: ", can_data("không đọc được chỉ mục BCTC")])
        elif pid == "P1_AGM_EVENTS":
            rows.append(self.checks["agm"]["parts"][:2])
        elif pid == "P2_OWNERSHIP_CIQ_CHROME":
            cq = self._safe("capiq_signals", lambda: self._extra_json("alpha_spine/capiq_signals.json")) or {}
            bt = cq.get("by_ticker") or {}
            per = {}
            for v in bt.values():
                k = ((v or {}).get("ownership_activity") or {}).get("period") or "?"
                per[k] = per.get(k, 0) + 1
            if per:
                top = max(per.items(), key=lambda kv: kv[1])
                rows.append(["CapIQ trên máy (capiq_signals, lớp lịch sử): %d/%d mã ở kỳ %s"
                             % (top[1], len(bt), top[0]), tier("FACT-T2")])
        elif pid == "P1_INSIDER_TXN":
            rows.append(self.checks["insider"]["parts"][:2])
        elif pid == "P1_FOREIGN_ROOM":
            rows.append(self.checks["room"]["parts"][:2])
        elif pid == "P0_DAILY_PRICE":
            rows.append(self.checks["price"]["parts"][:2])
            rows.append(self.checks["cross"]["parts"][:2])
            ev = self._safe("sự kiện quyền", self.adj_events)
            if ev is None:
                rows.append(["sự kiện quyền sau %s: " % _dm(ADJ_CUT), can_data("không đọc được factor điều chỉnh")])
            else:
                big = sorted((x for x in ev if x[1] >= 10), key=lambda x: -x[1])
                items = []
                for i, (t, x) in enumerate(big):     # mỗi "MÃ −N%" không tách dòng
                    items += [" · " if i else " · điều chỉnh tích luỹ ≥10%: ",
                              h("span", {"whiteSpace": "nowrap"}, "%s −%s%%" % (t, to_fixed(x, 0)))]
                rows.append(["factor closePriceAdjusted/closePrice đổi sau %s ở %d/%d mã (gồm cổ tức tiền)"
                             % (_dm(ADJ_CUT), len(ev), len(self.tickers)), *items, tier("EST", self.data_to)])
        elif pid == "P0_PERF_60D":
            n = sum(1 for r in self.px.values() if r and r.get("n", 0) >= 61)
            rows.append(["perf60 tính được (≥61 phiên giá điều chỉnh): %d/%d mã" % (n, len(self.tickers)),
                         tier("EST", self.data_to)])
        elif pid == "P3_MACRO_BACKDROP":
            rows += self._macro_rows()
        return rows

    def _macro_rows(self):
        out = []
        vni = self._safe("index_close", lambda: self.D.index_close("VNINDEX"))
        usd = self._safe("usd_vnd", lambda: self.D.usd_vnd("nhtm_ban"))
        tp = self._safe("tpcp_vn", lambda: self._extra_json("fincept_bridge/data/tpcp_vn.json")) or {}
        s10 = ((tp.get("ky_han") or {}).get("10Y") or [])
        line = ["MACRO.vnindex "]
        line += ([to_locale(vni.value, "en-US", max_frac=2), tier(vni.tier, vni.asof)]
                 if vni is not None and vni.value is not None else [can_data("VN-Index")])
        line += [" · usd_vnd (bán NHTM) "]
        line += ([to_locale(usd.value, "en-US", max_frac=0), tier(usd.tier, usd.asof)]
                 if usd is not None and usd.value is not None else [can_data("USD/VND")])
        line += [" · bond_10y (par yield HNX) "]
        line += ([_pct(s10[-1][1]), tier(tp.get("nhan") or "FACT-T2", s10[-1][0])] if s10 else [can_data("TPCP 10Y")])
        out.append(line)
        return out

    def pipe_status(self, p):
        z = self._pipe_dz(p["id"])
        ids = z.get("assets") or []
        w = self._worst(ids) if ids else "THIẾU"
        rows = [h("div", None, h("span", S_LBL, FOCUS_LABEL + " · đối chiếu " + (_dmy(self.sa_time) or "?")),
                  " · so_nguon_audit.json", upd_mark(z.get("asof")))]
        if z.get("legacy"):
            rows.append(h("div", None, "☠ V21: ", h("span", {"color": C.inkD}, z["legacy"]),
                          " — ", h("span", {"color": C.vermillion, "fontWeight": 600}, z.get("legacy_status") or "ngừng")))
        rows += [self._asset_row(a) for a in ids]
        for path in z.get("paths") or []:
            rows.append(h("div", {"paddingLeft": 14, "color": C.inkM}, "· " + str(path)))
        for ep in z.get("endpoints") or []:
            cv = self.coverage(ep)
            rows.append(h("div", None, "ĐỘ PHỦ vc_lk/%s: %d/%d mã · %s %s (mã cũ nhất %s%s)"
                          % (ep, cv["n"], cv["total"], cv["kind"], _dm(cv["max"]) or "?", self._dmin(cv),
                             " — vendor chỉ ghi phiên/sự kiện có phát sinh" if ep in _EVENT_EPS else ""),
                          tier("FACT-T2", cv["max"])))
        for r in self._check_rows(p["id"]):
            rows.append(h("div", None, *r))
        if z.get("reproduces"):
            rows.append(h("div", None, h("span", {"color": C.forest, "fontWeight": 600}, "TÁI TẠO: "),
                          *self._segments(z["reproduces"] if isinstance(z["reproduces"], list) else [z["reproduces"]]),
                          tier(z["tier"], z.get("asof")) if z.get("tier") and z.get("src") else None))
        if z.get("gaps"):
            rows.append(h("div", None, h("span", {"color": C.vermillion, "fontWeight": 600}, "THIẾU: "),
                          can_data(z["gaps"])))
        return h("div", {**S_LIVE_BOX, "borderLeft": "3px solid " + STATUS_COLOR.get(w, C.inkD)}, *rows,
                 key="aud.live:" + p["id"])

    def spec_label(self, p):
        return h("div", {"fontSize": 9, "fontFamily": F_MONO, "letterSpacing": ".12em", "color": C.inkM,
                         "marginBottom": 10}, "SPEC V21 · bản lưu 12/05/2026 — nguồn/URL dưới đây đã ngừng hoặc bị thay",
                 v21_mark())

    def pipe_fields(self, p, fields):
        """P0_FLOW_PILLAR_IV: trang để 6 ô rỗng vì thông tin nằm trong historicalSource/forwardSource (không render)
        → live điền từ chính hằng V21 (vẫn là spec cũ, dưới nhãn SPEC V21)."""
        if p.get("id") != "P0_FLOW_PILLAR_IV":
            return fields
        hs = p.get("historicalSource") if isinstance(p.get("historicalSource"), dict) else {}
        fs = p.get("forwardSource") if isinstance(p.get("forwardSource"), dict) else {}
        out = dict(fields)
        out["source_label"] = " → ".join(x for x in (hs.get("label"), fs.get("label")) if x) or None
        out["source_url"] = fs.get("source_url")
        out["fallback_url"] = hs.get("files")
        out["method"] = fs.get("method")
        out["selector_hint"] = fs.get("selector_hint")
        out["parse_logic"] = fs.get("parse_logic")
        out["validation"] = " · ".join(x for x in (hs.get("validation_4ch"), fs.get("validation_5ch")) if x) or None
        return out

    def pipe_notes(self, p, v21_notes):
        z = self._pipe_dz(p["id"])
        segs = z.get("notes")
        if not isinstance(segs, list) or not segs:
            return (list(v21_notes) + [v21_mark()]) if v21_notes else None
        out = self._segments(segs)
        if p.get("id") == "P1_INSIDER_TXN":
            out += [" "] + (self.insider_example() or [])
        return out + [upd_mark(z.get("asof"))]

    def playbook(self, kind, v21):
        z = (self.dz.get("playbook") or {}).get(kind)
        if not isinstance(z, dict) or not z.get("pre"):
            return (list(v21[0]) + [v21_mark()], list(v21[1]))
        return ([z.get("label") or v21[0][0], upd_mark(z.get("asof"))], [z["pre"]])

    def validation_cols(self, cols):
        return (("RULE", "17%"), ("CHECK", "35%"), ("APPLIES TO", "18%"), ("KIỂM " + (_dm(self.data_to) or "?"), "30%"))

    def validation_cell(self, i, rule):
        name = str(rule.get("rule") or "").lower()
        kind = next((k for key, k in _RULE_KIND if key in name), None)
        c = self.checks.get(kind) if kind else None
        z = (self.dz.get("validation") or {}).get(str(i + 1))
        note = self._segments([z]) if isinstance(z, dict) else []
        if c is None:
            body = [status_pill("CHƯA RÕ"), " ", can_data("luật chưa có phép kiểm")]
        else:
            body = [status_pill(c["status"]), " ", *c["parts"]]
        if note:
            body += [" · ", *note, upd_mark(z.get("asof"))]
        return h("td", {"padding": "10px 8px", "color": C.inkD, "fontSize": 10}, *body, key="aud.chk:%d" % (i + 1))

    def file_layout(self, intro, rows, cols):
        z = self.dz.get("file_layout") or {}
        zrows = z.get("rows") if isinstance(z.get("rows"), list) else None
        if not zrows:
            return intro + [v21_mark()], [(p, d + [v21_mark()], e) for p, d, e in rows], cols
        out = []
        for r in zrows:
            if not isinstance(r, dict):
                continue
            ids = r.get("assets") if isinstance(r.get("assets"), list) else ([r["asset"]] if r.get("asset") else [])
            desc = [r.get("desc") or ""]
            for aid in ids:
                desc += self._layout_status(aid, r.get("endpoint"), len(ids) > 1)
            out.append((r.get("path"), desc, None))
        new_intro = [z["intro"], upd_mark(z.get("asof"))] if isinstance(z.get("intro"), str) else intro
        return new_intro, out, cols

    def _layout_status(self, aid, ep, named):
        """Khối E: trạng thái Sổ nguồn của tài sản + NGÀY RIÊNG của dữ liệu (endpoint vc_lk nếu có — không dùng mốc
        chung vc_lk_meta; DESIGN §9), mỗi tài sản một nhãn bậc."""
        a = self._asset(aid)
        if a is None:
            return [" · ", can_data("không có dòng SO " + str(aid))]
        st = self._status(aid)
        name = (aid + " ") if named else ""
        sty = {"color": STATUS_COLOR.get(st, C.inkD), "fontFamily": F_MONO, "fontSize": 9}
        if ep:
            cv = self.coverage(ep)
            when = ("lấy %s (cũ nhất %s)" % (_dm(cv["max"]) or "?", self._dmin(cv)) if cv["kind"] == "lấy"
                    else "tới %s" % (_dm(cv["max"]) or "?"))
            return [" · ", h("span", sty, "%s%s · %d/%d mã %s" % (name, st, cv["n"], cv["total"], when)),
                    tier("FACT-T2", cv["max"])]
        if st == "KHÔNG ĐO":
            return [" · ", h("span", sty, name + st + " (mốc tương lai)"), tier(_tag(a.get("bac")) or "EST")]
        return [" · ", h("span", sty, name + st + " " + (_dm(a.get("moc")) or "?")),
                tier(_tag(a.get("bac")) or "EST", _iso(a.get("moc")))]

    def coverage_blocks(self):
        blk = []
        b = self._safe("basket", lambda: self.D.basket("VN30"))
        z = self.dz.get("coverage") or {}
        lab = {"color": C.forest, "fontWeight": 700, "letterSpacing": ".18em", "fontSize": 10}
        if b is None or b.value is None:
            blk.append(h("div", {"marginBottom": 12}, h("span", lab, "✚ VN30 HIỆN HÀNH:"), h("br"),
                         can_data("rổ vnstore.ma.nhom"), key="aud.cov:basket"))
        else:
            miss = [t for t in b.value if t not in self.tickers]
            extra = [t for t in self.tickers if t not in b.value]
            blk.append(h("div", {"marginBottom": 12},
                         h("span", lab, "✚ VN30 HIỆN HÀNH CHƯA CÓ TRONG 45 MÃ AUDIT:"), upd_mark(z.get("asof")),
                         h("br"),
                         h("span", {"color": C.ink}, " · ".join(miss) if miss else "—"), tier(b.tier, b.asof),
                         h("span", {"color": C.inkM, "fontSize": 9},
                           " — " + (z.get("note") or "rổ vnstore.ma.nhom (KBS); bang_vn30.json lệch — không dùng")),
                         h("br"),
                         h("span", {"color": C.inkD},
                           "Ngoài rổ hiện hành (%d mã chaebol/mở rộng): %s" % (len(extra), " · ".join(extra))),
                         tier(b.tier, b.asof), key="aud.cov:basket"))
        cv = [(ep, self.coverage(ep)) for ep in ("price-history", "proprietary-history", "insider-transaction",
                                                   "shareholder")]
        line = []
        for i, (ep, c) in enumerate(cv):
            line += [(" · " if i else "") + "%s %d/%d (tới %s)" % (ep, c["n"], c["total"], _dm(c["max"]) or "?"),
                     tier("FACT-T2", c["max"])]
        blk.append(h("div", None, h("span", lab, "✓ ĐỘ PHỦ vc_lk · %d mã:" % len(self.tickers)), h("br"),
                     h("span", {"color": C.ink}, *line), key="aud.cov:vc_lk"))
        return blk

    def guide(self, title, body, render):
        z = self.dz.get("guide") or {}
        paras = z.get("paras")
        if not isinstance(paras, list) or not paras:
            return title + [v21_mark()], body + [v21_mark()]
        conv = []
        for pr in paras:
            if not (isinstance(pr, list) and len(pr) == 3):
                continue
            color, lead, parts = pr
            conv.append((color, lead, [tuple(x) if isinstance(x, list) else x for x in parts]))
        return ([z.get("title") or title[0], upd_mark(z.get("asof"))], render(conv) + [upd_mark(z.get("asof"))])

    def csv(self):
        rows = []
        for p in self.pipes:
            z = self._pipe_dz(p["id"])
            ids = z.get("assets") or []
            rows.append({"pipeline": p["id"], "priority": p.get("priority"), "nguon_v21": z.get("legacy") or "",
                         "tai_san_so_nguon": " ".join(ids), "trang_thai": self._worst(ids) if ids else "THIẾU",
                         "so_nguon_luc": self.sa_time or "", "data_to": self.data_to or ""})
        return rows
