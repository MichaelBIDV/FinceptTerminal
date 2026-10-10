#!/usr/bin/env python3
"""
Fincept Terminal — Lăng kính cấu trúc cổ đông & FFT (VN30 · VN100) cho LangKinhPanel.

Chỉ ĐỌC các tệp bridge `_System/fincept_bridge/goi_fft.py` dựng sẵn: data/fft_langkinh.json,
data/fft_codong.json, data/fft_chuoi/*.json (env FINCEPT_BRIDGE_DATA ghi đè thư mục). Không gọi mạng,
không tính lại công thức CONTRACT §2 — ở đây chỉ xếp hạng, đếm, định dạng. Stdlib only;
chạy được trên Python 3.11 (venv-numpy2 của app) và 3.14.

CLI:  fincept_langkinh.py <view> [scope|ma]
      view ∈ tongquan bangquet matran bocung xephang thitruong chuoi codong chuthe cauchuyen phuongphap nguon
             hoso matran5 sigma rrg (LK_HOSO — fincept_langkinh_hoso*.py, payload layout "hoso")
             mauhinh (mẫu hình NTH — fincept_langkinh_mauhinh.py, layout "hoso")
      scope ∈ VN30|VN100|VN200 (mặc định VN30; VN200 = 200 mã đóng băng của lk_vutru.json nếu có tệp); view `chuoi`,
      `hoso` nhận mã (mặc định FPT); `matran5` nhận MÃ,MÃ,… hoặc rổ; `mauhinh` nhận MÃ hoặc rổ (mặc định VN200).
In ĐÚNG một object JSON ra stdout. Thành công không bao giờ có khoá "error" (PythonRunner coi là lỗi) và `data`
không bao giờ rỗng (B8 — data rỗng thì CSV của EconPanelBase giữ bảng của view trước).
Triển khai đủ 6 tệp cùng thư mục: fincept_langkinh.py + _base, _texts, _chuthe, _views, _story (thiếu _story thì
lớp câu chuyện V4 tắt — view `cauchuyen` báo lỗi rõ, các view khác chạy như cũ).
"""
import html
import json
import math
import os
import re
import sys
import traceback
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fincept_langkinh_chuthe as CT  # noqa: E402
import fincept_langkinh_texts as T  # noqa: E402
import fincept_langkinh_views as V  # noqa: E402
try:  # V4 — tệp mới; provision chỉ đồng bộ tệp đã có ở bundle → thiếu thì tắt lớp câu chuyện, không làm hỏng view khác
    import fincept_langkinh_story as ST  # noqa: E402
except ImportError:
    ST = None
try:  # LK_HOSO — tệp mới (+ _hoso_base, _hoso_ro); bundle chưa có thì chỉ 4 view hồ sơ báo lỗi
    import fincept_langkinh_hoso as HS  # noqa: E402
except ImportError:
    HS = None
from fincept_langkinh_base import (BUCKET_NHAN, CO, P, bang, cot, dmy, dong, ds_chu, g, ghi, phang, pp,  # noqa: E402
                                   so, so_num, the, tuan_nhan, ve)
from fincept_langkinh_texts import (CAU_BAT_BUOC, LICH, MX_TIEU_DE, PP_CONG_THUC, PP_NGUON,  # noqa: E402,F401
                                    PP_TEXT, SAO_LECH)

MAC_DINH = os.path.expanduser("~/SECOND BRAIN-OBSIDIAN/_System/fincept_bridge/data")
CU_GIO = 26  # tệp cũ hơn ngần này thì nói rõ, không im lặng hiển thị
SCOPES = ("VN30", "VN100", "VN200")
PHAN_LOAI = {"tongquan", "bangquet", "matran", "bocung", "xephang", "chuoi", "codong", "chuthe", "cauchuyen", "mauhinh"}
GOI_Y = "chạy `python3 goi_fft.py %s` trong _System/fincept_bridge (hoặc chờ goi_nguon chạy job %s)"


class LoiTrang(Exception):
    """Lỗi có thông điệp tiếng Việt cho người dùng."""


class Ctx:
    def __init__(self, thu_muc, lk, cd, scope, now):
        self.dir, self.lk, self.cd, self.scope, self.now = thu_muc, lk or {}, cd, scope, now
        ma = self.lk.get("ma")
        self.ma = {s: m for s, m in (ma.items() if isinstance(ma, dict) else []) if isinstance(m, dict)}
        self.vu_tru = vu_tru_200(thu_muc)
        if scope == "VN200":  # 200 mã đóng băng (lk_vutru.json); thiếu tệp → nhãn nhóm VN200 ∪ VN100 của fft_langkinh
            self.members = sorted(self.vu_tru) or sorted(s for s, m in self.ma.items()
                                                         if {"VN200", "VN100"} & set(m.get("nhom") or []))
        else:
            self.members = sorted(s for s, m in self.ma.items() if scope in (m.get("nhom") or []))
        self.cong = self.lk.get("cong") if isinstance(self.lk.get("cong"), dict) else {}
        self.sym = None

    def chuoi(self, ten):
        if not re.match(r"^_?[A-Z0-9]{1,12}$", ten or ""):
            return None
        d, _ = doc_tuy_chon(os.path.join(self.dir, "fft_chuoi", ten + ".json"), "fft_chuoi/%s.json" % ten)
        return d


def e(s):
    return html.escape(str(s), quote=False)


# ───────────────────────────── 7 · chuoi <MÃ> ─────────────────────────────

KIEU_TEN = {"quan_sat": "quan sát", "noi_suy": "nội suy", "chep": "chép"}


def ngay_ky(ky):
    m = re.match(r"(\d{4})-(\d{2})", str(ky or ""))
    try:
        return date(int(m.group(1)), int(m.group(2)), 1) if m else None
    except ValueError:
        return None


def chart_codong(c, s):
    """D6.4 — cổ đông tách mốc quan sát (bar) và nội suy/chép (dot); giá TV danh nghĩa trục phải."""
    cdm = g(c.cd, "ma", s)
    moc = sorted([x for x in (g(cdm, "moc") or []) if isinstance(x, dict) and ngay_ky(x.get("ky"))],
                 key=lambda x: x["ky"])
    if not moc:
        return None
    cf = int(so_num(cdm.get("cf_so_ky")) or 0)
    cd_ = [so_num(x.get("co_dong")) for x in moc]
    if any(x.get("kieu") for x in moc):
        series = [ve("Cổ đông (quan sát)", "left", "bar", "cyan",
                     [v if x.get("kieu") == "quan_sat" else None for x, v in zip(moc, cd_)]),
                  ve("Cổ đông (nội suy/chép)", "left", "dot", "dim",
                     [v if x.get("kieu") in ("noi_suy", "chep") else None for x, v in zip(moc, cd_)])]
    else:  # tệp bridge cũ chưa phân kiểu mốc — không đoán
        series = [ve("Số cổ đông (chưa phân kiểu mốc)", "left", "bar", "cyan", cd_)]
    series.append(ve("Giá TV (danh nghĩa, chưa điều chỉnh CA)", "right", "line", "amber",
                     [so_num(x.get("gia")) for x in moc]))
    return {"type": "chart", "kind": "line", "title": "%s · Số cổ đông × giá mốc" % s,
            "sub": "Toàn Vũ %s · %s · giá danh nghĩa tại mốc, chưa khử lạm phát/tỷ giá, chưa điều chỉnh CA%s%s" % (
                dmy(c.cd.get("ngay_tep")), cdm.get("bac") or CO,
                " · CF×%d kỳ: chưa có số mới" % cf if cf >= 2 else "",
                " · mốc quan sát cuối %s" % cdm["ky_quan_sat_cuoi"] if cdm.get("ky_quan_sat_cuoi") else ""),
            "height": 600, "x": [V.ms(ngay_ky(x["ky"])) for x in moc],  # 300: chỗ cho nhãn chú thích V3.4.7–9
            "left": {"label": "Số cổ đông", "min": 0}, "right": {"label": "Giá TV (đồng, danh nghĩa)"},
            "series": series, "annotations": V.ann_codong(cdm)}


COT_12 = [cot("w", "Tuần", "left"), cot("gia", "Giá"), cot("f", "FFT tuần"), cot("m", "TB4"), cot("p10", "P10 3Y"),
          cot("p90", "P90 3Y"), cot("sp", "Số phiên")]
COT_SK = [cot("ngay", "Ngày", "left"), cot("ng", "Nguồn", "left"), cot("loai", "Loại", "left"),
          cot("nd", "Nội dung", "left"), cot("bac", "Bậc", "left")]


def dong_tuan(t, y, i, tu):
    d = y.get("d")
    if d:
        sp = pp(d[i])
    elif t[i] == tu.get("week_end"):
        sp = pp(tu.get("so_phien_tuan")) + (" (dở dang)" if tu.get("do_dang") else "")
    else:
        sp = CO  # tệp fft_chuoi cũ chưa mang mảng `d` (B4)
    v = {k: (y.get(k) or [None] * len(t))[i] for k in ("c", "f", "m", "p10", "p90")}
    return dong({"w": dmy(t[i]), "gia": V.gia(v["c"]), "f": V.fftp(v["f"]), "m": V.fftp(v["m"]),
                 "p10": V.fftp(v["p10"]), "p90": V.fftp(v["p90"]), "sp": sp},
                sort={"gia": v["c"], "f": v["f"], "m": v["m"], "p10": v["p10"], "p90": v["p90"]})


def vdl(v):
    """Vốn điều lệ Toàn Vũ (đồng) → '14.711 tỷ'."""
    return "%s tỷ" % so(v / 1e9, 0) if so_num(v) is not None and v >= 1e9 else so(v, 0)


def su_kien_ma(c, s):
    """D6.4 — ISS 24T + tăng vốn Toàn Vũ + ý đồ curated, sắp ngày giảm dần (chỉ hiển thị)."""
    ct, out = CT.ct_of(c, s), []
    ph = CT.bc_khoi(ct, "phat_hanh_24t")
    if isinstance(ph, dict):
        bac = "%s · phân loại %s" % (ph.get("bac") or "FACT-T2", ph.get("bac_phan_loai") or "EST")
        for key, ten in (("thu_tien", "thu tiền"), ("khong_thu_tien", "không thu tiền"), ("khac", "khác")):
            out += [(str(x.get("ngay") or ""), {"ngay": dmy(x.get("ngay")), "ng": "Vietcap ISS 24T",
                                                "loai": "Phát hành · " + ten,
                                                "nd": x.get("nguyen_van") or x.get("loai") or CO, "bac": bac})
                    for x in ph.get(key) or [] if isinstance(x, dict)]
    tv = CT.bc_khoi(ct, "tang_von_tv")
    for x in (tv.get("su_kien") or [] if isinstance(tv, dict) else []):
        if isinstance(x, dict):
            ky, a, b = str(x.get("ky") or ""), so_num(x.get("vdl_truoc")), so_num(x.get("vdl_sau"))
            out.append((ky + "-99" if len(ky) == 7 else ky, {
                "ngay": ky or CO, "ng": "Toàn Vũ", "loai": "Tăng VĐL",
                "nd": "VĐL %s → %s%s%s" % (vdl(a), vdl(b), " (%s)" % V.tile_pct(b / a - 1) if a and b else "",
                                          " · " + x["hinh_thuc"] if x.get("hinh_thuc") else ""),
                "bac": tv.get("bac") or "SS-T3"}))
    out += [(str(x.get("ngay") or ""), {"ngay": CT.yd_ngay(x), "ng": "owner_intent · %s" % (x.get("nguon") or CO),
                                        "loai": x.get("loai") or CO, "nd": x.get("tieu_de") or CO,
                                        "bac": x.get("bac") or CO}) for x in CT.yd_ds(ct) or []]
    out.sort(key=lambda kv: kv[0], reverse=True)
    return [dong(r, mau={"bac": "dim" if r["bac"] == "UNVERIFIED" else ""}) for _, r in out]


def tiles_chu_the(c, s):
    ct = CT.ct_of(c, s)
    hien, xd = CT.ct_hien(ct), CT.xung_dot(ct)
    moc = tuan_nhan(ct.get("ngay"))
    if hien:
        t1 = the("CHỦ THỂ", hien, " · ".join(x for x in (CT.nguyen_van(ct), moc, " + ".join(CT.refs(ct))) if x),
                 "amber" if xd else "info", "EST" if xd else (ct.get("bac") or ""))
    else:
        gc = CT.ghi_chu_nganh(ct)
        t1 = the("CHỦ THỂ", "[CẦN DATA]", ("ghi chú ngành (không thành nhãn): " + " · ".join(gc)) if gc else
                 "chưa có nhãn — không suy thành 'trung tính'", "dim", "")
    pb = CT.pb_ma(c, s)
    dung = CT.cong_dung(c.cong)
    t2 = the("PLAYBOOK", "[%s]" % pb, "CỔNG chưa xác định — không kết luận per-mã" if dung else
             "CỔNG %s × chủ thể %s (PI:59-63) · bằng chứng không đổi playbook" % (
                 CT.ngoac_tien(c.cong), "xung đột" if xd else (CT.nhan(ct) or "CẦN DATA")),
             "dim" if pb.startswith("CẦN DATA") else "", "" if pb.startswith("CẦN DATA") else (c.cong.get("bac") or ""))
    return [t1, CT.so_huu_the(ct), t2]


def v_chuoi(c):
    s = c.sym
    m = c.ma[s]
    tu, bc, ff = (m.get(k) or {} for k in ("tuan", "bocung", "ff"))
    bh, bb = tu.get("bac_hang") or tu.get("bac") or "FACT-T2", bc.get("bac") or "FACT-T2"
    cff, ctu = V.co_du_lieu(m)
    fh = V.ff_hien(ff)  # % FF = mẫu số FFT (ff_cp ÷ issue_share)
    lt, ltip = V.lech_thoi(m, c.lk)
    tiles = [
        the("PCT 3Y", P(tu.get("pct3y")), "cửa sổ %s tuần · %s %s" % (pp(tu.get("n_3y")), BUCKET_NHAN,
                                                                      V.bk_ten(tu.get("bucket"))),
            V.mau_bar(tu.get("pct3y")), bh),
        the("PALL · TOÀN DẢI 2020→", P(tu.get("pall")), "%s tuần · lệch cửa sổ %s" % (
            pp(tu.get("n_tuan")), so(tu.get("lech_cua_so"), 0, True)), "", bh),
        the("×P10", V.boi(tu.get("x_p10")), "TB 4 tuần %s · P10 3Y %s (mức %s)%s" % (
            V.fftp(tu.get("ma4")), V.fftp(tu.get("p10_3y")), tu.get("bac_muc") or "EST",
            "".join(" · ⚠ " + x for x in ctu)), "warn" if ctu else "", bh),
        the("Ô 8 TUẦN", tu.get("o8") or CO, "±5% FFT · ±1% giá so 8 tuần trước (quy ước Cowork)", V.mau_o8(tu), "EST"),
        the("BO CUNG 2N", bc.get("o_2n") or CO, "ΔFFT 2N %s · giá 2N %s · 1N (EST) %s / %s" % (
            V.tile_pct(bc.get("dfft_2n")), V.tile_pct(bc.get("dgia_2n")), V.tile_pct(bc.get("dfft_1n")),
            V.tile_pct(bc.get("dgia_1n"))), V.O2N_MAU.get(bc.get("o_2n"), "dim"), bb),
        the("FREE FLOAT", V.pt(fh["p"], fh["nd"]), "%s · %s · %s%s" % (
            fh["tip"] or "%s cp" % so(ff.get("cp"), 0), ff.get("nguon") or CO, dmy(ff.get("cap_nhat")),
            "".join(" · ⚠ " + x for x in cff)), "warn" if cff or fh["canh"] else "", ff.get("bac") or "FACT-T2") if ff else
        the("FREE FLOAT", CO, "[CẦN DATA] %s" % (m.get("loi") or "chưa có free float"), "bear", ""),
    ] + tiles_chu_the(c, s)
    if m.get("loi"):
        for x in tiles[:5]:
            if x["v"] == CO:
                x["s"] = "[CẦN DATA] %s" % m["loi"]
    blocks = [{"type": "tiles", "items": tiles}]
    if ST:  # V4.4 — câu chuyện chủ thể: story + timeline ngay sau tiles
        blocks += ST.khoi_chuoi(c, s)
    if lt:
        blocks.insert(0, ghi("Dữ liệu mã cũ / chờ CA", "%s: %s." % (e(lt), e(ltip)), "Cảnh báo", "warn"))
    doc = c.chuoi(s)
    if doc:
        x, t, y = V.cat_chuoi(doc)
        ann = V.ann_chuoi(x, t, y, tu, bc)
        if x and g(c.cd, "ma", s):  # V3.4.6 — mốc cổ đông quan sát |Δ| ≥ 20% (Toàn Vũ)
            ann += V.vline_cd(g(c.cd, "ma", s), x[0], x[-1])
        ann_cc = ST.ann_chuoi(c, s, x[0], x[-1]) if ST and x else []  # V4.4 — sự kiện · vùng gom · thoi vùng giá
        if ST:
            ann = ST.gioi_han(ann + ann_cc, ann_cc)  # tổng ≤ 28, bỏ ưu tiên thấp/cũ trước
        blocks.append({"type": "chart", "kind": "line", "title": "%s · FFT × Giá" % s,
                       "sub": "FFT tuần · TB 4 tuần · dải ≤P10 / ≥P90 3Y cuộn (trái, mức EST) · giá điều chỉnh (phải) · "
                              "%s → %s%s" % (dmy(t[0] if t else None), dmy(t[-1] if t else None),
                                             ST.chu_thich_sub(ann_cc) if ST else ""),
                       "height": 680, "x": x, "left": {"label": "FFT %/tuần", "min": 0},
                       "right": {"label": "Giá (đồng)"},
                       "series": V.dai_p(y) + [ve("FFT tuần", "left", "thin", "dim", y.get("f", [])),
                                               ve("TB 4 tuần", "left", "line", "bull", y.get("m", [])),
                                               ve("Giá", "right", "line", "amber", y.get("c", []))],
                       "annotations": ann})
    else:
        blocks.append(ghi("Thiếu chuỗi", "Chưa có fft_chuoi/%s.json%s — %s." % (
            s, " (%s)" % m["loi"] if m.get("loi") else "", GOI_Y % ("fft_langkinh", "fft_langkinh")), "Thiếu", "warn"))
    ch = chart_codong(c, s) if c.cd else None
    if ch:
        blocks.append(ch)
    sk = su_kien_ma(c, s)
    blocks.append(bang("su_kien", "Sự kiện vốn & ý đồ — %s" % s, COT_SK, sk,
                       "ISS 24T (Vietcap) · tăng vốn (Toàn Vũ) · ý đồ curated (owner_intent) · ngày giảm dần",
                       "Chỉ hiển thị — không đổi nhãn chủ thể hay playbook. " + T.TV_HINH_THUC) if sk else
                  ghi("Sự kiện vốn & ý đồ", "Không có sự kiện ISS 24T / tăng vốn TV / ý đồ curated cho %s%s." % (
                      s, " ([CẦN DATA] chưa có khối bằng chứng)" if not CT.ct_of(c, s).get("bang_chung") else ""),
                      "", "dim"))
    data = []
    if doc:
        _, t, y = V.cat_chuoi(doc, 12)
        blocks.append(bang("tuan12", "12 tuần gần nhất", COT_12, [dong_tuan(t, y, i, tu) for i in reversed(range(len(t)))],
                           "tuần kết thúc thứ Sáu (W-FRI)", T.MUC_EST + ("" if y.get("d") else
                                                                         " Số phiên từng tuần chưa có trong fft_chuoi — "
                                                                         "chỉ biết tuần cuối.")))
        _, t, y = V.cat_chuoi(doc, 10 ** 6)
        data = phang(bang("", "", COT_12, [dong_tuan(t, y, i, tu) for i in range(len(t))]))
    return {"title": "%s · %s" % (s, m.get("ten") or CO),
            "sub": "%s · %s%s · tuần %s%s" % (m.get("nganh") or CO, "/".join(m.get("nhom") or []) or CO,
                                              " · danh mục " + V.dm_tag(m) if V.dm_tag(m) else "",
                                              V.dm(tu.get("week_end")), V.dang_do(c.lk)),
            "blocks": blocks, "data": data, "cong": CT.cong_ma(c, s), "tickers": sorted(c.ma)}


# ───────────────────────────── 8 · codong ─────────────────────────────

COT_CD = [cot("ma", "Mã", "left"), cot("cd", "Cổ đông (kỳ)"), cot("kieu", "Kiểu mốc cuối", "left"),
          cot("cf", "CF", "left"), cot("kqs", "Kỳ quan sát cuối", "left"), cot("vd", "vs đáy 2N"),
          cot("vdi", "vs đỉnh 2N"), cot("gdd", "Giá từ đỉnh CĐ (KHO)"), cot("cpbq", "CP bình quân/cổ đông"),
          cot("k", "k cặp cuối (nhãn)", "left"), cot("ocap", "Ô cặp cuối", "left"), cot("tv", "Tăng vốn 25–26", "left"),
          cot("lop", "Lớp", "left", "tag"), cot("pct", "pct3Y (FFT)"), cot("bac", "Bậc", "left")]


def k_ly_do(v):
    """Lý do không có k (D3.5, S:150-152) — chỉ khi tệp đã mang khoá k_cuoi (schema mới)."""
    if v.get("k_ly_do"):
        return str(v["k_ly_do"])
    if (so_num(v.get("cf_so_ky")) or 0) >= 2:
        return "CF — chưa có số mới"
    if v.get("so_tron"):
        return "số tròn — cấm làm mẫu số k"
    if v.get("noi_suy") or g((v.get("moc") or [{}])[-1], "kieu") not in (None, "quan_sat"):
        return "mốc nội suy"
    return CO


def w37(v, tho):
    """Tag 'W37 …' khi số W37 (mọi mốc) khác số quan sát sau làm tròn — để thấy lệch mà không cần tooltip."""
    a, b = V.tile_pct(v, 0), V.tile_pct(tho, 0)
    return "W37 " + b if b != CO and a != b else ""


def dong_cd(c, s, v):
    cuoi = v.get("cuoi") or {}
    cf = int(so_num(v.get("cf_so_ky")) or 0)
    n = so_num(cuoi.get("co_dong"))
    p3 = g(c.ma, s, "tuan", "pct3y")
    moc = [x for x in (v.get("moc") or []) if isinstance(x, dict)]
    kieu = KIEU_TEN.get(g(moc[-1], "kieu"), CO) if moc else CO
    k = so_num(v.get("k_cuoi"))
    kv = ("%s (%s)" % (so(k, 0), v.get("k_nhan") or CO) if k is not None else
          (k_ly_do(v) if "k_cuoi" in v else CO))
    gc = ds_chu(v.get("ghi_chu"))
    tag_lop = ("không đủ mốc" if v.get("du_moc") is False else
               ("thưởng/ESOP?" if v.get("co_su_kien_von_cua_so") else ""))
    kqs = v.get("ky_quan_sat_cuoi")
    lt, ltip = V.lech_thoi(c.ma[s], c.lk) if s in c.ma else ("", "")  # pct3Y lấy từ lớp FFT: mã cũ / chờ CA
    return dong({"ma": s, "cd": "%s (%s)" % (so(n, 0 if n is None or float(n).is_integer() else 1), cuoi.get("ky") or CO),
                 "kieu": kieu, "cf": "CF×%d" % cf if cf >= 2 else "",
                 "kqs": "%s%s" % (kqs, " · %s th" % pp(v.get("tuoi_thang")) if so_num(v.get("tuoi_thang")) is not None
                                  else "") if kqs else CO,
                 "vd": V.tile_pct(v.get("vs_day"), 0), "vdi": V.tile_pct(v.get("vs_dinh"), 0),
                 "gdd": V.tile_pct(v.get("gia_tu_dinh_cd"), 0), "cpbq": so(v.get("cp_binh_quan"), 0), "k": kv,
                 "ocap": v.get("o_cap") or CO,
                 "tv": {True: "có", False: "không"}.get(v.get("tang_von_2025_26"), CO),
                 "lop": V.LOP_TEN.get(v.get("lop"), CO), "pct": pp(p3), "bac": v.get("bac") or CO},
                sort={"cd": n, "cf": cf, "vd": so_num(v.get("vs_day")), "vdi": so_num(v.get("vs_dinh")),
                      "gdd": so_num(v.get("gia_tu_dinh_cd")), "cpbq": so_num(v.get("cp_binh_quan")), "k": k,
                      "pct": so_num(p3)},
                mau={"lop": {"bung_no": "amber", "dac_lai": "info"}.get(v.get("lop"), ""),
                     "cf": "warn" if cf >= 2 else "", "bac": "warn" if v.get("bac") == "EST" else "",
                     "kqs": "warn" if v.get("du_moc") is False else "", "k": "dim" if k is None else "",
                     "kieu": "warn" if kieu in ("nội suy", "chép") else "", "pct": "warn" if lt else ""},
                tag={"ma": V.dm_tag(c.ma.get(s) or {}),
                     "cd": "số tròn" if v.get("so_tron") else ("nội suy" if v.get("noi_suy") else
                                                             ("sửa năm" if v.get("sua_nam") else "")),
                     "vd": w37(v.get("vs_day"), v.get("vs_day_tho")), "vdi": w37(v.get("vs_dinh"), v.get("vs_dinh_tho")),
                     "lop": tag_lop, "pct": lt},
                tip={"vd": "W37 (mọi mốc, gồm nội suy): %s" % V.tile_pct(v.get("vs_day_tho"))
                     if "vs_day_tho" in v else "",
                     "vdi": "W37 (mọi mốc, gồm nội suy): %s" % V.tile_pct(v.get("vs_dinh_tho"))
                     if "vs_dinh_tho" in v else "",
                     "lop": "; ".join(gc), "ocap": "; ".join(x for x in gc if "định danh" in x), "pct": ltip},
                link=s if s in c.ma else "")


def v_codong(c):
    cd = c.cd
    mau, dk = cd.get("mau") or 30, cd.get("dem_kieu") or {}
    ma = {s: v for s, v in (cd.get("ma") or {}).items() if isinstance(v, dict)}
    vs = lambda s: so_num(ma[s].get("vs_day"))  # noqa: E731
    ds = sorted([s for s in ma if vs(s) is not None], key=lambda s: (-vs(s), s)) + sorted(s for s in ma if vs(s) is None)
    ncf = sum(1 for v in ma.values() if (so_num(v.get("cf_so_ky")) or 0) >= 2)
    kqs, kns, kch = (so_num(dk.get(k)) for k in ("quan_sat", "noi_suy", "chep"))
    tong = sum(x for x in (kqs, kns, kch) if x is not None) if kns is not None else None
    q2 = cd.get("q2") if isinstance(cd.get("q2"), dict) else CT.q2_cong(c.cong)
    q2n = CT.q2_nam(q2)
    y2 = sorted(q2n)[-2] if len(q2n) > 1 else (sorted(q2n)[-1] if q2n else None)
    tiles = V.tiles_dem(cd, "BÙNG NỔ ≥+50% TỪ ĐÁY 2N",
                        "mẫu gốc /%s — không quy đổi sang /100 · chỉ mã đủ mốc quan sát" % pp(mau))
    tiles += [the("MÃ CF · CHƯA CÓ SỐ MỚI", "%d/%s" % (ncf, pp(mau)), "số cổ đông mốc cuối bằng mốc trước ≥2 kỳ",
                  "warn", "EST"),
              the("NGÀY TỆP TOÀN VŨ", dmy(cd.get("ngay_tep")), "%s%s" % (
                  os.path.basename(str(cd.get("tep") or "")) or CO,
                  " · sửa nội bộ %s" % dmy(cd["ngay_noi_bo"]) if cd.get("ngay_noi_bo") else ""), "",
                  cd.get("bac") or "SS-T3"),
              the("MỐC QUAN SÁT/NỘI SUY/CHÉP", "%s/%s/%s" % (pp(kqs), pp(kns), pp(kch)) if dk else CO,
                  "tổng %s mốc · kiểu đọc từ công thức ô Excel của tệp" % pp(tong), "", "EST"),
              the("Q2 %s" % (y2 or "CORPORATE"), "%s sự kiện · %s/%s mã" % (
                  pp(q2n[y2].get("so_su_kien")), pp(q2n[y2].get("so_ma")), pp(q2.get("mau") or mau)) if y2 else CO,
                  CT.q2_doan(q2) if y2 else "[CẦN DATA — Q2 Corporate]", "", (q2 or {}).get("bac") or "SS-T3")]
    b = bang("codong", "Cổ đông — %d mã trong tệp (mẫu gốc /%s)" % (len(ma), pp(mau)), COT_CD,
             [dong_cd(c, s, ma[s]) for s in ds], "sắp vs đáy 2N giảm dần",
             "Cổ đông (kỳ) = số cổ đông ở mốc cuối · vs đáy/đỉnh 2N tính trên mốc QUAN SÁT (neo = kỳ quan sát cuối), "
             "tag 'W37' = số tính trên mọi mốc · CP bình quân/cổ đông = tổng cổ phần ÷ số cổ đông (không phải giá "
             "trị) · k cặp cuối, Ô cặp cuối, Giá từ đỉnh CĐ: EST, chỉ hiển thị · pct3Y lấy từ lớp FFT.")
    cau = ["<b>%d.</b> %s" % (i, md_html(CAU_BAT_BUOC[i])) for i in (2, 3, 4, 6)]
    cau += [e(T.CD_KIEU.format(ns=pp(kns), tong=pp(tong), chep=pp(kch))), e(T.CD_DAC_LAI), e(T.TV_HINH_THUC)]
    note = ghi("Câu bắt buộc (DATA_SOURCES #2, #3, #4, #6) · quy ước mốc", "<br>".join(cau), "Bắt buộc", "info")
    return {"title": "Cổ đông — Pillar I (Toàn Vũ)",
            "sub": "Tệp %s · cập nhật %s · bậc %s (EST khi CF / số tròn / nội suy)" % (
                dmy(cd.get("ngay_tep")), cd.get("cap_nhat") or CO, cd.get("bac") or "SS-T3"),
            "blocks": [{"type": "tiles", "items": tiles}, b, note], "data": phang(b)}


# ───────────────────────────── 10 · phuongphap (chữ cố định) ─────────────────────────────

def md_html(s):
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", e(s))
    return re.sub(r"`([^`]+)`", r"<i>\1</i>", s)


def md_dong(s):
    """Một dòng markdown nguyên văn → HTML (đậm, nghiêng, code) — không đổi chữ."""
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", e(s))
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", s)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", s)


def md_khoi(md):
    out = []
    for ln in md.split("\n"):
        if not ln.strip():
            continue
        if ln.startswith("### "):
            out.append("<h4>%s</h4>" % md_dong(ln[4:]))
        elif ln.startswith("> "):
            out.append("<p><i>%s</i></p>" % md_dong(ln[2:]))
        else:
            out.append("<p>%s</p>" % md_dong(ln))
    return "".join(out)


def html_pp():
    nhom = [n.split("\n") for n in PP_TEXT.strip("\n").split("\n\n")]
    out = ["<h3>%s</h3><p><i>%s</i></p>" % (e(nhom[0][0]), e(nhom[0][1]))]
    for i, n in enumerate(nhom[1:7], 1):
        out.append("<h3>%s</h3>" % e(n[0]))
        for j, ln in enumerate(n[1:], 1):
            if j in PP_CONG_THUC.get(i, ()):
                out.append("<p><code>%s</code></p>" % e(ln))
            elif i == 3 and " — " in ln:
                a, b = ln.split(" — ", 1)
                out.append("<p><b>%s</b> — %s</p>" % (e(a), e(b)))
            else:
                out.append("<p>%s</p>" % e(ln))
    mx = nhom[7]
    cols = [x.strip() for x in mx[0].split("cột:", 1)[1].split("|")]
    out.append("<table><tr><th></th>%s</tr>" % "".join("<th>%s</th>" % e(x) for x in cols))
    hang = {}
    for ln in mx[1:]:
        nhan, rest = ln.split(" · ", 1)
        hang.setdefault(nhan, []).extend(x.strip() for x in rest.split(" | "))
    for nhan, cells in hang.items():
        tds = []
        for x in cells:
            td = next((t for t in MX_TIEU_DE if x.startswith(t + " — ")), None)
            tds.append("<b>%s</b><br>%s" % (e(td), e(x[len(td) + 3:])) if td else e(x))
        out.append("<tr><th>%s</th>%s</tr>" % (e(nhan), "".join("<td>%s</td>" % t for t in tds)))
    out.append("</table>")
    bb = nhom[8]
    out.append("<h4><b>Bắt buộc</b> · %s</h4><p>%s</p>" % (e(bb[0].replace("[Bắt buộc]", "").strip()), e(bb[1])))
    out.append("<hr><p><i>%s</i></p>" % e(PP_NGUON))
    return "".join(out)


def html_p3():
    """D6.9 — Pillar III (S:177-193) + luật Δ cổ đông NTH:45-46 nguyên văn, kèm chú thích bậc."""
    return ("<h3>Pillar III — Ý đồ chủ thể (nguyên văn)</h3>" + md_khoi(T.PILLAR3_MD) +
            "<p><i>Nguồn: %s.</i></p><hr>" % e(T.PILLAR3_NGUON) +
            "<h4>Luật Δ cổ đông — Nguyễn Trần Hải (nguyên văn)</h4>" + md_khoi(T.NTH_MD) +
            "<p><i>%s · nguồn: %s.</i></p>" % (e(T.NTH_CHU_THICH), e(T.NTH_NGUON)) +
            "<p><b>%s</b></p>" % md_dong(T.NTH_7))


def v_phuongphap(c):
    return {"title": "Phương pháp luận FFT — Toàn Vũ", "sub": "Khối §1 cố định · Pillar III · Methodology v1.7",
            "blocks": [{"type": "html", "html": html_pp()},
                       ghi("Những chỗ §1 lệch v1.7 bản cuối", "<br>".join(e(x) for x in SAO_LECH), "Lệch", "warn"),
                       {"type": "html", "html": html_p3()},
                       ghi("Từ vựng — không trộn", "<br>".join("(%d) %s" % (i, e(x)) for i, x in enumerate(T.TU_VUNG, 1)),
                           "Từ vựng", "info")],
            # data rỗng → EconPanelBase::display() bỏ qua và giữ bảng CSV của view trước — nên luôn có hàng
            "data": [{"01 Mục": n[0], "02 Nội dung": " ".join(n[1:])}
                     for n in (x.split("\n") for x in PP_TEXT.strip("\n").split("\n\n"))] +
                    [{"01 Mục": "Lệch v1.7 bản cuối", "02 Nội dung": x} for x in SAO_LECH] +
                    [{"01 Mục": "Pillar III (S:177-193)", "02 Nội dung": T.PILLAR3_MD},
                     {"01 Mục": "Δ cổ đông NTH:45-46", "02 Nội dung": T.NTH_MD + " — " + T.NTH_CHU_THICH},
                     {"01 Mục": "7 mẫu hình NTH", "02 Nội dung": T.NTH_7}] +
                    [{"01 Mục": "Từ vựng — không trộn", "02 Nội dung": x} for x in T.TU_VUNG]}


# ───────────────────────────── 11 · nguon ─────────────────────────────

def v_nguon(c):
    lk, cd, ng = c.lk, c.cd or {}, c.lk.get("nguon") or {}
    cg, dv = c.cong, g(c.cong, "dau_vao") or {}
    ffs = [g(m, "ff") for m in c.ma.values() if isinstance(g(m, "ff"), dict)]
    ff_moc = max((str(f.get("cap_nhat")) for f in ffs if f.get("cap_nhat")), default=None)
    dmm = [g(m, "dm") or {} for m in c.ma.values()]
    ph = lk.get("phien") or {}
    rt, bc = ph.get("do_rong_tt") or {}, cg.get("boi_canh") or {}
    tt = {b: g(lk, "thi_truong", b) or {} for b in SCOPES}
    nct = g(lk, "nguon", "chu_the") if isinstance(g(lk, "nguon", "chu_the"), dict) else {}
    sh, phn, ydn = (nct.get(k) if isinstance(nct.get(k), dict) else {} for k in ("so_huu", "phat_hanh", "y_do"))
    ncc = g(lk, "nguon", "cau_chuyen") if isinstance(g(lk, "nguon", "cau_chuyen"), dict) else {}
    dn = CT.dem_nhan(c, sorted(c.ma))
    q2 = CT.q2_cong(cg)
    cnh = V.co_nhom(c, sorted(c.ma))  # cờ dữ liệu EST (I3 · R3 · I4) trên toàn vũ trụ FFT
    rows = [
        ("Giá · KL (phiên + tuần)", ng.get("gia_kl"), "FACT-T2", "phiên %s%s" % (dmy(lk.get("phien_cuoi")), V.so_bo(lk)),
         "%s mã · từ %s" % (pp(ng.get("n_ma")), dmy(ng.get("tu")))),
        ("Free float", ng.get("ff_nguon"), "FACT-T2 (mức FFT = EST)", dmy(ff_moc),
         "%s/%s mã" % (pp(ng.get("n_co_ff")), pp(ng.get("n_ma")))),
        ("Lịch sử 156 tuần (3Y)", ng.get("kho"), "FACT-T2", "tuần %s" % dmy(g(lk, "tuan", "week_end")),
         "%s/%s mã đủ 3 năm" % (pp(ng.get("n_du_3y")), pp(ng.get("n_ma"))))]
    rows += [("Market FFT %s" % b, "Σ KL tuần ÷ Σ FF · thành viên hiện tại áp ngược", V.bac_ro(tt[b], False),
              "tuần %s" % dmy(tt[b].get("week_end")), "%s/%s mã có FF" % tuple(pp(x) for x in V.phu_ro(tt[b])[:2]))
             for b in SCOPES]
    rows += [
        ("Cổ đông (Pillar I)", "%s · %s" % (ng.get("codong") or "fft_codong.json", os.path.basename(str(cd.get("tep") or "")) or CO),
         cd.get("bac") or CO, "tệp %s" % dmy(cd.get("ngay_tep")), "%d/%s mã" % (len(cd.get("ma") or {}), pp(cd.get("mau")))),
        ("CỔNG · tín dụng / M2 YoY", "widata_series_store (wc-tdcn / wc-tkhe)", "FACT-T2",
         "%s / %s" % (V.ky_ngan(g(dv, "td", "ky")), V.ky_ngan(g(dv, "m2", "ky"))), "GAP %s" % so(dv.get("gap"), 2)),
        ("CỔNG · OMO", "liquidity_daily/output/latest.json", "FACT-T2", dv.get("omo_asof") or CO, V.pt(dv.get("omo"), 2)),
        ("CỔNG · ON (Δ 3 phiên)", "liquidity_daily/output/snapshot_*.json", "EST", g(dv, "on", "asof") or CO,
         "%sbp" % so(dv.get("d_on_3p_bp"), 0, True)),
        ("CỔNG · Q2 Corporate", "fft_codong.json → q2 (luật CW parse_toanvu.py:110-112)",
         (q2 or {}).get("bac") or "SS-T3", "TV %s" % dmy((q2 or {}).get("ngay_tep")) if q2 else CO,
         CT.q2_doan(q2) if q2 else "[CẦN DATA — Q2 Corporate] → CỔNG DỪNG"),
        ("CỔNG · kết luận", "fft_cong.py (METHODOLOGY:395–420, 991)", cg.get("bac") or CO, lk.get("cap_nhat") or CO,
         " · ".join(x for x in ("[%s]" % CT._can_data(CT.ly_do_dung(cg)), CT.tham_chieu(cg)) if x)
         if CT.cong_dung(cg) else cg.get("chu_ky")),
        ("Chủ thể cần thị trường (nhãn)", "%s → fft_chuthe.py (k13 · q2 · pi2 · k5)" % (
            nct.get("nhan") or "fft_cauhinh.chu_the"), "SS-T3 %d · EST %d · xung đột %d" % (dn["a"], dn["b"], dn["x"]),
         ", ".join(sorted(dn["ngay"])) or CO, "%d/%d mã có nhãn · không tự hết hạn" % (dn["a"] + dn["b"] + dn["k"],
                                                                                      len(c.ma))),
        ("Sở hữu (Nhà nước · NN · trần NN)", "KHO free_float (vn_ff) · dự phòng %s" % (
            sh.get("du_phong") or "vietcap_live/vietcap_fundamentals.json"), "FACT-T2", dmy(sh.get("luc")),
         "KHO %s mã · tệp Vietcap phủ %s mã" % (pp(sh.get("kho_n")), pp(sh.get("du_phong_n")))),
        ("Phát hành 24T (Vietcap ISS)", phn.get("tep") or "vietcap_live/vietcap_fundamentals.json",
         "FACT-T2 · phân loại EST", "%s · sự kiện %s → %s" % (dmy(phn.get("luc")), dmy(phn.get("tu")), dmy(phn.get("den"))),
         "%s mã chạm trần 12 sự kiện (danh sách có thể thiếu)" % pp(phn.get("n_cat_cut"))),
        ("Ý đồ curated (owner_intent)", ydn.get("tep") or "early_detection/owner_intent.json",
         "verified → SS-T3 · còn lại UNVERIFIED", dmy(ydn.get("luc")), "%s curated · %s verified · %s auto bỏ qua" % (
             pp(ydn.get("n_curated")), pp(ydn.get("n_verified")), pp(ydn.get("n_auto_bo_qua")))),
        ("Câu chuyện chủ thể (tuyển chọn tay, V4)", ncc.get("tep") or "fft_cauchuyen.json → fft_cauchuyen.py",
         "theo từng mục · vùng giá EST", dmy(ncc.get("cap_nhat")) if ncc else CO,
         "%s mã · %s sự kiện · %s vùng gom · tạm dùng dữ liệu sẵn có" % (
             pp(ncc.get("n_ma")), pp(ncc.get("n_su_kien")), pp(ncc.get("n_vung_gia_gom"))) if ncc else
         "[CẦN DATA] bridge chưa xuất lớp câu chuyện"),
    ]
    rows += ST.nguon_tin_rows(c) if ST else []  # độ tươi từng nguồn tin của lớp tự động (job fft_tin)
    rows += [
        ("Bậc trường sở hữu VCI", T.VCI_BAC, "FACT-T2", CO, "mâu thuẫn nguồn — nêu, không đổi bậc"),
        ("Cờ dữ liệu", "goi_fft · ff.canh_bao · canh_bao mã · tuan.canh_bao", "EST", CO,
         "; ".join("%d mã: %s" % (len(v), x[:70]) for x, v in cnh.items()) or "không có"),
        ("Danh mục NAV / watch / avoid", "fft_cauhinh.json ← SKILL lang-kinh-fft-vn30-daily BƯỚC 3", CO, CO,
         "%d NAV · %d watch · %d avoid · %d mâu thuẫn nguồn (*) trong vũ trụ FFT · nav_unverified (KSV) không cộng · "
         "không hiển thị tổng NAV" % (sum(1 for d in dmm if so_num(d.get("nav"))), sum(1 for d in dmm if d.get("watch")),
                                     sum(1 for d in dmm if d.get("avoid")), sum(1 for d in dmm if d.get("xung_dot")))),
        ("VN-Index phiên", "vn_store.db", g(ph, "vnindex", "bac") or CO, dmy(ph.get("ngay")) + V.so_bo(lk), CO),
        ("Độ rộng toàn thị trường", rt.get("nguon"), "FACT-T2", rt.get("luc") or CO, "%s mã" % pp(rt.get("tong"))),
        ("Regime Hub (ngữ cảnh)", "alpha_spine/market_regime.json", bc.get("bac") or "EST", bc.get("luc") or CO,
         "không vào luật CỔNG")]
    cols = [cot("tp", "Thành phần", "left"), cot("ng", "Nguồn", "left"), cot("bac", "Bậc", "left"),
            cot("moc", "Mốc dữ liệu", "left"), cot("phu", "Độ phủ", "left")]
    b = bang("nguon", "Nguồn & giới hạn", cols, [{"tp": r[0], "ng": r[1] or CO, "bac": r[2], "moc": r[3], "phu": r[4]}
                                                  for r in rows], "fft_langkinh.json cập nhật %s" % (lk.get("cap_nhat") or CO))
    loi = [str(x) for x in (ng.get("loi") or [])]
    loi += ["%s: %s" % (s, m["loi"]) for s, m in sorted(c.ma.items()) if m.get("loi") and
            not any(x.startswith(s + ":") for x in loi)]
    loi += ["chủ thể: %s" % x for x in ds_chu(nct.get("loi"))]
    loi += ["câu chuyện: %s" % x for x in ds_chu(ncc.get("loi"))]
    blocks = [b, ghi("Lỗi / mã thiếu", "<br>".join(e(x) for x in loi) or "Không có.", "Kiểm", "warn" if loi else "dim"),
              ghi("Cờ dữ liệu (EST)", "<br>".join("%s — %d mã: %s" % (e(x), len(v), ", ".join(v)) for x, v in cnh.items())
                  or "Không có mã nào bị gắn cờ.", "Kiểm", "warn" if cnh else "dim"),
              ghi("Quy ước nguồn", "<br>".join(e(x) for x in (T.R2, T.R4, T.MUC_EST)), "Quy ước", "info"),
              ghi("Nguồn đã xét & loại", "<br>".join("<b>%s</b> — %s" % (e(a), e(r)) for a, r in T.NGUON_LOAI),
                  "Loại", "dim"),
              ghi("11 câu bắt buộc — DATA_SOURCES cột 3 (thiếu câu = báo cáo không hợp lệ)",
                  "<br>".join("<b>%d.</b> %s" % (i, md_html(x)) for i, x in enumerate(CAU_BAT_BUOC)), "Bắt buộc", "info"),
              ghi("Lịch chạy", e(LICH), "Lịch", "dim")]
    return {"title": "Nguồn & giới hạn", "sub": "Bậc bằng chứng: FACT-T1 > FACT-T2 > SS-T3 > EST > UNVERIFIED",
            "blocks": blocks, "data": phang(b)}


def v_cauchuyen(c):
    if ST is None:
        raise LoiTrang("Thiếu fincept_langkinh_story.py cạnh fincept_langkinh.py (bundle chưa có tệp mới) — view "
                       "'Câu chuyện chủ thể' tạm tắt; các view khác không ảnh hưởng.")
    return ST.v_cauchuyen(c)


def v_hs(ten):
    def v(c):
        if HS is None:
            raise LoiTrang("Thiếu fincept_langkinh_hoso*.py cạnh fincept_langkinh.py — 4 view hồ sơ tạm tắt; "
                           "các view khác không ảnh hưởng.")
        return getattr(HS, "v_" + ten)(c)
    return v


def v_mauhinh(c):
    mh = getattr(HS, "MH", None) if HS is not None else None
    if mh is None:
        raise LoiTrang("Thiếu fincept_langkinh_mauhinh.py cạnh fincept_langkinh.py — view «Mẫu hình NTH» tạm tắt; "
                       "các view khác không ảnh hưởng.")
    return mh.v_mauhinh(c)


def vu_tru_200(thu_muc):
    """VN200 = 200 mã đóng băng của lk_vutru.json ở thư mục bridge (cha của data/) → {mã: {ten, nhom…}}; thiếu/hỏng
    tệp → {}."""
    d, _ = doc_tuy_chon(os.path.join(os.path.dirname(os.path.normpath(thu_muc)), "lk_vutru.json"), "lk_vutru.json")
    ma = d.get("ma") if d else None
    return {s: m for s, m in ma.items() if re.match(r"^[A-Z0-9]{2,10}$", s) and isinstance(m, dict)} \
        if isinstance(ma, dict) else {}


VIEWS = {"tongquan": V.v_tongquan, "bangquet": V.v_bangquet, "matran": V.v_matran, "bocung": V.v_bocung,
         "xephang": V.v_xephang, "thitruong": V.v_thitruong, "chuoi": v_chuoi, "codong": v_codong,
         "chuthe": CT.v_chuthe, "cauchuyen": v_cauchuyen, "phuongphap": v_phuongphap, "nguon": v_nguon,
         "hoso": v_hs("hoso"), "matran5": v_hs("matran5"), "sigma": v_hs("sigma"), "rrg": v_hs("rrg"),
         "mauhinh": v_mauhinh}
DOI_SO_MA = ("chuoi", "hoso", "matran5", "mauhinh")  # view nhận mã / danh sách mã thay cho rổ
HO_SO = ("hoso", "matran5", "sigma", "rrg", "mauhinh")  # đọc hồ sơ riêng — rổ VN200 đủ 200 mã


# ───────────────────────────── IO · khung trả về ─────────────────────────────

def doc_tuy_chon(path, ten):
    """(dict, None) hoặc (None, thông điệp lỗi) — không ném."""
    if not os.path.exists(path):
        return None, "Chưa có %s trong %s" % (ten, os.path.dirname(path))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError) as exc:
        return None, "Không đọc được %s: %s" % (ten, exc)
    return (d, None) if isinstance(d, dict) else (None, "%s sai định dạng (không phải object JSON)" % ten)


def tuoi(cap_nhat, now):
    try:
        moc = datetime.strptime(str(cap_nhat or "").replace("T", " ")[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        return None, "không rõ mốc cập nhật"
    gio = (now - moc).total_seconds() / 3600
    if gio > CU_GIO:
        return gio, "DỮ LIỆU CŨ %d giờ" % int(gio)
    return gio, ("cập nhật %d phút trước" % max(0, int(gio * 60))) if gio < 1 else "cập nhật %d giờ trước" % int(gio)


def chon_ma(ma, arg):
    if not ma:
        raise LoiTrang("fft_langkinh.json chưa có mã nào — %s." % (GOI_Y % ("fft_langkinh", "fft_langkinh")))
    if arg:
        if arg not in ma:
            raise LoiTrang("Không có mã %s trong fft_langkinh.json (vũ trụ FFT = VN30 ∪ VN100)." % arg)
        return arg
    return "FPT" if "FPT" in ma else sorted(ma)[0]


def ds_ma(c):
    """V3.1 — vũ trụ VN100 / VN200 (A→Z) cho ô gõ mã: [{ma, ten, nhom: VN30|VN100|VN200}] — gồm cả mã của lk_vutru.json
    chưa có trong fft_langkinh (nhóm VN200) để ô mã mở được hồ sơ / mẫu hình của chúng."""
    ds = [{"ma": s, "ten": m.get("ten") or "", "nhom": "VN30" if "VN30" in (m.get("nhom") or []) else ("VN100" if "VN100" in (m.get("nhom") or []) else "VN200")}
          for s, m in sorted(c.ma.items()) if re.match(r"^[A-Z0-9]{1,10}$", s)]
    return sorted(ds + [{"ma": s, "ten": m.get("ten") or "", "nhom": "VN200"} for s, m in c.vu_tru.items()
                        if s not in c.ma], key=lambda x: x["ma"])


def tom_tat(blocks, title):
    """B8 — view không có bảng chính → hàng tóm tắt (tiles, không có thì note) để `data` không bao giờ rỗng."""
    rows = [{"01 Mục": it.get("k", ""), "02 Giá trị": it.get("v", ""), "03 Ghi chú": it.get("s", ""),
             "04 Bậc": it.get("bac", "")} for b in blocks if b.get("type") == "tiles" for it in b.get("items") or []]
    rows = rows or [{"01 Mục": b.get("title", ""), "02 Giá trị": html.unescape(re.sub(r"<[^>]+>", " ", b.get("text", "")))}
                    for b in blocks if b.get("type") == "note"]
    return rows or [{"01 Mục": title, "02 Giá trị": "không có hàng dữ liệu"}]


def chay(argv, now=None):
    now = now or datetime.now()
    view = (argv[1] if len(argv) > 1 else "tongquan").strip().lower()
    arg = argv[2].strip().upper() if len(argv) > 2 and argv[2] else ""
    if view not in VIEWS:
        raise LoiTrang("Không rõ chế độ xem '%s'. Hợp lệ: %s." % (view, ", ".join(VIEWS)))
    scope = arg or ("VN200" if view == "mauhinh" else "VN30")
    if view not in DOI_SO_MA and scope not in SCOPES:
        raise LoiTrang("Rổ '%s' không hợp lệ — chỉ VN30, VN100 hoặc VN200." % arg)
    thu_muc = os.environ.get("FINCEPT_BRIDGE_DATA") or MAC_DINH
    lk, loi = doc_tuy_chon(os.path.join(thu_muc, "fft_langkinh.json"), "fft_langkinh.json")
    if lk is None and view != "phuongphap":  # §1 là chữ tĩnh — vẫn hiện được khi chưa có dữ liệu
        raise LoiTrang("%s — %s." % (loi, GOI_Y % ("fft_langkinh", "fft_langkinh")))
    cd, loi_cd = doc_tuy_chon(os.path.join(thu_muc, "fft_codong.json"), "fft_codong.json")
    if view == "codong" and cd is None:
        raise LoiTrang("%s — %s." % (loi_cd, GOI_Y % ("fft_codong", "fft_codong")))
    c = Ctx(thu_muc, lk, cd, scope, now)
    ngoai_lk = [s for s in c.members if s not in c.ma] if view not in HO_SO else []
    if ngoai_lk:  # view cũ đọc fft_langkinh.ma[s]: mã VN200 chưa có trong fft_langkinh bị loại, nói rõ
        c.members = [s for s in c.members if s in c.ma]
    if view == "chuoi":
        c.sym = chon_ma(c.ma, arg)
        nhom = c.ma[c.sym].get("nhom") or []
        c.scope = "VN30" if "VN30" in nhom else ("VN100" if "VN100" in nhom else ("VN200" if "VN200" in nhom else (nhom[0] if nhom else "VN200")))
        c.members = sorted(s for s, m in c.ma.items() if c.scope in (m.get("nhom") or []) or (
            c.scope == "VN200" and "VN100" in (m.get("nhom") or [])))
    kq = VIEWS[view](c)
    dau, tuoi_s = [], ""
    if lk is None:
        dau.append(ghi("Chưa có dữ liệu", "%s — dòng CỔNG [CẦN DATA]." % e(loi), "Thiếu", "warn"))
    else:
        gio, tuoi_s = tuoi(lk.get("cap_nhat"), now)
        if gio is None or gio > CU_GIO:
            dau.append(ghi("Dữ liệu cũ", "fft_langkinh.json cập nhật %s — %s (ngưỡng %d giờ). Chạy lại: %s." % (
                lk.get("cap_nhat") or CO, tuoi_s, CU_GIO, GOI_Y % ("fft_langkinh", "fft_langkinh")), "Cảnh báo", "warn"))
    if cd is not None and view in ("tongquan", "chuoi", "codong", "chuthe", "nguon"):
        gio_cd, t_cd = tuoi(cd.get("cap_nhat"), now)
        if gio_cd is None or gio_cd > CU_GIO:
            dau.append(ghi("Dữ liệu cổ đông cũ", "fft_codong.json cập nhật %s — %s." % (cd.get("cap_nhat") or CO, t_cd),
                           "Cảnh báo", "warn"))
    if lk and lk.get("den"):
        dau.append(ghi("Chế độ đối chiếu", "Dữ liệu cắt tới %s (goi_fft --den)." % e(str(lk["den"])), "Hồi quy", "info"))
    if lk and not c.members:
        dau.append(ghi("Rổ trống", "Rổ %s không có mã nào trong fft_langkinh.json." % c.scope, "Thiếu", "warn"))
    if ngoai_lk:
        dau.append(ghi("%d mã VN200 chưa có trong fft_langkinh" % len(ngoai_lk), "Bị loại khỏi trang này (chưa có chuỗi "
                       "FFT): %s." % e(", ".join(ngoai_lk)), "Thiếu", "warn"))
    if view in PHAN_LOAI and CT.cong_dung(c.cong) and (kq.get("payload") or {}).get("layout") != "hoso":
        # layout hoso (hồ sơ, mẫu hình): CỔNG chỉ hiện MỘT lần — ở dải CỔNG trên cùng (nth_a3_design low #9)
        dau.append(ghi("CỔNG chưa xác định", "CỔNG chưa xác định — số dưới đây là đo lường, không kết luận per-mã.",
                       "CỔNG", "bear"))
    blocks = dau + kq["blocks"]
    if dau and kq["blocks"] and kq["blocks"][0].get("type") == "tkhead":  # hồ sơ: đầu mã luôn đứng đầu trang
        blocks = kq["blocks"][:1] + dau + kq["blocks"][1:]
    out = {"success": True, "view": view, "scope": c.scope, "title": kq["title"], "sub": kq.get("sub") or "",
           "as_of": (lk or {}).get("cap_nhat") or "", "tuoi": tuoi_s, "cong": kq.get("cong") or CT.cong_ro(c),
           "blocks": blocks, "data": kq.get("data") or tom_tat(blocks, kq["title"]),
           "tickers": kq.get("tickers") or c.members, "ds_ma": ds_ma(c)}
    out.update(kq.get("payload") or {})  # LK_HOSO: layout "hoso" + as_of/tuoi của chính hồ sơ
    return out


def sach(o):
    """NaN/Inf → null để stdout luôn là JSON hợp lệ."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: sach(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [sach(v) for v in o]
    return o


def main(argv=None):
    try:
        out = chay(argv or sys.argv)
    except LoiTrang as exc:
        out = {"success": False, "data": [], "error": str(exc)}
    except Exception as exc:  # không để traceback lọt ra stdout
        traceback.print_exc(file=sys.stderr)
        out = {"success": False, "data": [], "error": "Lỗi dựng trang: %s: %s" % (type(exc).__name__, exc)}
    sys.stdout.flush()
    sys.stdout.buffer.write((json.dumps(sach(out), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
