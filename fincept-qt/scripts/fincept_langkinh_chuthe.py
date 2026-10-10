#!/usr/bin/env python3
"""
Fincept Terminal — Lăng kính: dòng CỔNG (rổ / mã) và lớp "ý đồ chủ thể" Pillar III (view `chuthe`).
Chỉ HIỂN THỊ nhãn + bằng chứng mà bridge đã phân giải (fft_chuthe.py — CONTRACT_DELTA D2.2, D4.4, D5.1):
không suy nhãn từ bằng chứng, không đổi playbook, không dùng nhãn cls/icls/pat của NTH/ydo.
Mọi khoá mới đều tuỳ chọn → '—' / [CẦN DATA]. Stdlib only; Python 3.11 và 3.14.
"""
import html
import re

import fincept_langkinh_texts as T
from fincept_langkinh_base import (CO, bang, cot, dm, dm_tag, dm_tip, dmy, dong, ds_chu, ff_hien, g, ghi, ky_ngan,
                                   lech_thoi, ngay, phang, pp, pt, so, so_num, the, tuan_nhan)

BAC_THU_TU = ("FACT-T1", "FACT-T2", "SS-T3", "EST", "UNVERIFIED")


def e(s):
    return html.escape(str(s), quote=False)


# ───────────────────────────── nhãn chủ thể ─────────────────────────────

def loai_chu_the(nhan_):
    s = str(nhan_ or "").strip().lower()
    if s.startswith("không"):
        return "không cần"
    if s.startswith("trung tính"):
        return "trung tính"
    if s.startswith("cần") or s.startswith("có"):
        return "cần"
    return None


def ct_of(c, s):
    ct = g(c.ma, s, "chu_the")
    return ct if isinstance(ct, dict) else {}


def xung_dot(ct):
    return bool(ct.get("xung_dot"))


def nhan(ct):
    """'cần' | 'không cần' | 'trung tính' | None — mã xung đột luôn None (không chọn bên, S:477)."""
    return None if xung_dot(ct) else loai_chu_the(ct.get("nhan"))


def khang_dinh(ct):
    """Khẳng định nguồn (D5.1); tệp bridge cũ chỉ có `goc` → coi là một khẳng định."""
    kd = [k for k in (ct.get("khang_dinh") or []) if isinstance(k, dict)]
    if kd:
        return kd
    if ct.get("goc"):
        return [{"nguon": "", "ref": "", "nhan": ct.get("nhan"), "nguyen_van": ct["goc"], "bac": ct.get("bac")}]
    return []


def hai_phia(ct):
    out = []
    for k in khang_dinh(ct):
        n = loai_chu_the(k.get("nhan")) or str(k.get("nhan") or CO)
        if n not in out:
            out.append(n)
    return out


def ct_hien(ct):
    """Chữ hiển thị của chủ thể: nhãn · '⚠ A ⟷ B' khi xung đột · None khi chưa có nhãn."""
    if xung_dot(ct):
        return "⚠ " + " ⟷ ".join(hai_phia(ct)) if len(hai_phia(ct)) > 1 else "⚠ xung đột"
    return nhan(ct)


def _hang_bac(b):
    return BAC_THU_TU.index(b) if b in BAC_THU_TU else len(BAC_THU_TU)


def bac_yeu(bacs):
    """Bậc yếu nhất của một nhóm số liệu gộp (con số tổng không mạnh hơn thành phần yếu nhất)."""
    bs = [b for b in bacs if b]
    return max(bs, key=_hang_bac) if bs else ""


def mot_kd(k):
    return "%s%s: %s (%s%s)" % (k.get("nguon") or "nguồn", " " + k["ref"] if k.get("ref") else "",
                                k.get("nguyen_van") or CO, k.get("bac") or CO,
                                " · chỉ ghi chú" if k.get("chi_ghi_chu") else "")


def nguyen_van(ct):
    """Nguyên văn nhãn: xung đột → mọi phía; không xung đột → bỏ khẳng định `chi_ghi_chu` (K5 chỉ là ghi chú ngành)."""
    kd = khang_dinh(ct)
    if xung_dot(ct):
        return " ⟷ ".join("%s: %s" % (k.get("nguon") or "nguồn", k.get("nguyen_van") or CO) for k in kd)
    kd = sorted([k for k in kd if not k.get("chi_ghi_chu")], key=lambda k: _hang_bac(k.get("bac")))
    if not kd:
        return ""
    return (kd[0].get("nguyen_van") or CO) + (" (+%d nguồn)" % (len(kd) - 1) if len(kd) > 1 else "")


def ghi_chu_nganh(ct):
    out = []
    for x in ct.get("ghi_chu_nganh") or []:
        if isinstance(x, dict):
            out.append("%s%s" % (x.get("nguyen_van") or CO, " (%s)" % x["ref"] if x.get("ref") else ""))
        elif isinstance(x, str) and x.strip():
            out.append(x)
    return out


def refs(ct):
    out = []
    for k in khang_dinh(ct):
        if k.get("ref") and k["ref"] not in out:
            out.append(k["ref"])
    return out


def pb_ma(c, s):
    """Playbook mã = `chu_the.playbook` của bridge, NGUYÊN VĂN (luật D4.4 chỉ ở fft_cong.playbook_ma — D2.0 một phép
    tính một chỗ); vắng khoá → CẦN DATA. CỔNG dừng → CẦN DATA (cổng an toàn, không phải tính lại luật)."""
    if cong_dung(c.cong):
        return "CẦN DATA"
    pb = str(ct_of(c, s).get("playbook") or "").strip().strip("[]").strip()
    return pb or "CẦN DATA"


# ───────────────────────────── CỔNG ─────────────────────────────

def q2_cong(cg):
    q = g(cg, "dau_vao", "q2")
    return q if isinstance(q, dict) else None


def cong_dung(cg):
    """DỪNG: không có CỔNG · chu kỳ ngoài ĐẮT/RẺ · bridge báo dừng · thiếu Q2 Corporate (D4.2, S:99, R:177)."""
    return not cg or cg.get("chu_ky") not in ("ĐẮT", "RẺ") or bool(cg.get("dung")) or q2_cong(cg) is None


def ly_do_dung(cg):
    cg = cg or {}
    if cg.get("ly_do_dung"):
        return str(cg["ly_do_dung"])
    if cg.get("chu_ky") in ("ĐẮT", "RẺ") and not cg.get("dung") and q2_cong(cg) is None:
        return "[CẦN DATA — Q2 Corporate]"
    return "chưa xác định chu kỳ"


def _can_data(s):
    s = str(s or "").strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1].strip()
    return s if s.startswith("CẦN DATA") else "CẦN DATA — " + (s or "chưa xác định chu kỳ")


def ngoac_tien(cg):
    m = re.match(r"\s*CỔNG:\s*\[([^\]]+)\]", cg.get("dong") or "")
    if m and m.group(1).strip().lower().startswith("tiền"):
        return m.group(1).strip()
    return {"ĐẮT": "tiền đắt", "RẺ": "tiền rẻ"}[cg["chu_ky"]]


def dong_dung(cg):
    d = (cg or {}).get("dong") or ""
    if d.startswith("CỔNG: [CẦN DATA"):
        return d
    return "CỔNG: [%s] · không kết luận per-mã" % _can_data(ly_do_dung(cg))


def q2_nam(q):
    nam = (q or {}).get("nam") or (q or {}).get("theo_nam") or {}
    return {str(k): v for k, v in nam.items() if isinstance(v, dict)} if isinstance(nam, dict) else {}


def q2_doan(q, so_nam=2):
    """'32 sự kiện/21 mã (2025), 15/10 (2026 tới 07)' — hai năm cuối của Q2."""
    nam = q2_nam(q)
    ys = sorted(nam)[-so_nam:]
    out = []
    for i, y in enumerate(ys):
        v = nam[y]
        den = str(v.get("den_ky") or (q.get("den_ky") if y == ys[-1] else "") or "")
        toi = " tới %s" % den[5:7] if den[:4] == y and len(den) >= 7 else ""
        fmt = "%s sự kiện/%s mã (%s%s)" if i == 0 else "%s/%s (%s%s)"
        out.append(fmt % (pp(v.get("so_su_kien")), pp(v.get("so_ma")), y, toi))
    return ", ".join(out)


def chi_tiet(dv):
    if not dv:
        return ""
    td, m2, on = dv.get("td") or {}, dv.get("m2") or {}, dv.get("on") or {}
    if td.get("ky") and td.get("ky") == m2.get("ky"):
        tm = "td %s · M2 %s (%s)" % (pt(td.get("v"), 1), pt(m2.get("v"), 1), ky_ngan(m2["ky"]))
    else:
        tm = "td %s (%s) · M2 %s (%s)" % (pt(td.get("v"), 1), ky_ngan(td.get("ky")),
                                          pt(m2.get("v"), 1), ky_ngan(m2.get("ky")))
    bp = so(dv.get("d_on_3p_bp"), 0, True)
    out = "%s · GAP %s · OMO %s · ON %s (%s) Δ3p %s" % (
        tm, so(dv.get("gap"), 1), pt(dv.get("omo"), 2), pt(on.get("v"), 2), dm(on.get("asof")),
        bp if bp == CO else bp + "bp")
    q = dv.get("q2")
    if isinstance(q, dict) and q2_doan(q):  # D4.3
        out += " · Corporate %s — TV %s" % (q2_doan(q), dm(q.get("ngay_tep")))
    return out


def tham_chieu(cg):
    """CỔNG dừng nghiêm (vd chuỗi M2 nghi gãy) mà bridge vẫn tính chu kỳ tham chiếu `cong.tham_chieu` → một dòng,
    bậc tối đa EST, không dùng cho quyết định. Không dừng / không có khoá → ''."""
    tc = (cg or {}).get("tham_chieu")
    if not tc or not cong_dung(cg):
        return ""
    if isinstance(tc, dict):  # bridge: {chu_ky_neu_bo_co, ghi_chu, gap, bac}; ck None = vùng giữa (lý do ở ghi_chu)
        gap = so_num(tc.get("gap")) if so_num(tc.get("gap")) is not None else so_num(g(cg, "dau_vao", "gap"))
        ck = tc.get("chu_ky_neu_bo_co") or tc.get("chu_ky") or "[%s]" % _can_data(tc.get("ghi_chu"))
        return "Tham chiếu nếu bỏ cờ gãy M2: %s · GAP %s — %s, không dùng cho quyết định" % (
            ck, so(gap, 1), bac_yeu([tc.get("bac") or "EST", "EST"]))
    s = str(tc).strip()
    return s if "không dùng cho quyết định" in s else "Tham chiếu nếu bỏ cờ gãy M2: %s — EST, không dùng cho quyết định" % s


def _cong_goc(c):
    cg = c.cong
    ct, tc = chi_tiet(cg.get("dau_vao") or {}), tham_chieu(cg)
    return {"bac": cg.get("bac") or "", "canh_bao": [str(x) for x in (cg.get("canh_bao") or [])],
            "chi_tiet": "\n".join(x for x in (ct, tc) if x)}


def dem_nhan(c, ds=None):
    """Đếm nhãn trong rổ: SS-T3 a · EST b · xung đột x · bậc khác k · N (D4.5); kèm tập mốc nhãn."""
    ds = c.members if ds is None else ds
    d = {"a": 0, "b": 0, "x": 0, "k": 0, "N": len(ds), "ngay": set()}
    for s in ds:
        ct = ct_of(c, s)
        if xung_dot(ct):
            d["x"] += 1
        elif nhan(ct):
            d[{"SS-T3": "a", "EST": "b"}.get(ct.get("bac"), "k")] += 1
        else:
            continue
        if tuan_nhan(ct.get("ngay")):
            d["ngay"].add(tuan_nhan(ct.get("ngay")))
    d["con"] = d["N"] - d["a"] - d["b"] - d["x"] - d["k"]
    return d


def cong_ro(c):
    cg, out = c.cong, _cong_goc(c)
    if cong_dung(cg):
        out.update(dong=dong_dung(cg), muc="dung")
        return out
    d, N = dem_nhan(c), len(c.members)
    moc = " (%s)" % ", ".join(sorted(d["ngay"])) if d["ngay"] else ""
    ct = "theo mã — %d/%d SS-T3 · %d/%d EST%s · %d/%d xung đột" % (d["a"], N, d["b"], N, moc, d["x"], N)
    if d["k"]:
        ct += " · %d/%d bậc khác" % (d["k"], N)
    if d["con"] > 0:
        ct += " · còn lại CẦN DATA"
    out["dong"] = "CỔNG: [%s] · chủ thể [%s] · playbook [%s]" % (ngoac_tien(cg), ct, cg.get("playbook") or "CẦN DATA")
    out["muc"] = "canh_bao" if out["canh_bao"] else "ok"
    return out


def cong_ma(c, sym):
    cg, out = c.cong, _cong_goc(c)
    if cong_dung(cg):
        out.update(dong=dong_dung(cg), muc="dung")
        return out
    ct = ct_of(c, sym)
    n, xd, pb = nhan(ct), xung_dot(ct), pb_ma(c, sym)
    bd = str(ct.get("cong_dong") or "").strip()
    if bd.startswith("CỔNG:"):  # dòng CỔNG theo mã của bridge — hiển thị nguyên văn
        out["dong"] = bd
    else:
        chu = "CẦN DATA — nhãn xung đột" if xd else (n or "CẦN DATA")
        out["dong"] = "CỔNG: [%s] · chủ thể [%s] thị trường · playbook [%s]" % (ngoac_tien(cg), chu, pb)
    if n or xd:  # D4.4 — "chủ thể <bac> · W37 10/09 · <ref>"
        phan = ["chủ thể %s" % ("xung đột" if xd else (ct.get("bac") or CO)), tuan_nhan(ct.get("ngay")),
                " + ".join(refs(ct))]
        out["chi_tiet"] = " · ".join(x for x in [out["chi_tiet"]] + phan if x)
    if xd:
        if not any("xung đột" in x for x in ds_chu(ct.get("canh_bao"))):  # bridge chưa tự ghi thì app ghi
            out["canh_bao"].append("%s: nhãn chủ thể xung đột (%s) — không chọn bên (S:477)" % (sym, nguyen_van(ct)))
    elif n is None:
        out["canh_bao"].append("%s chưa có nhãn chủ thể — playbook [%s]" % (sym, pb))
    out["canh_bao"] += ds_chu(ct.get("canh_bao"))
    out["muc"] = "canh_bao" if out["canh_bao"] else "ok"
    return out


def note_cong(c, cobj):
    cg = c.cong
    dv = cg.get("dau_vao") or {}
    td, m2, on = dv.get("td") or {}, dv.get("m2") or {}, dv.get("on") or {}
    acc = dv.get("acc_m2") or []
    q = q2_cong(cg)
    dung = cobj.get("muc") == "dung"  # dừng thì không in chu kỳ/playbook như kết luận, kể cả khi bridge còn giữ khoá
    dong_ = [
        "Chu kỳ tiền: <b>%s</b> · bucket: %s · playbook rổ: %s · bậc %s" % (
            "[CẦN DATA]" if dung else (cg.get("chu_ky") or "[CẦN DATA]"), CO if dung else (cg.get("bucket") or CO),
            "[CẦN DATA]" if dung else (cg.get("playbook") or "[CẦN DATA]"), cg.get("bac") or CO),
        "Tín dụng YoY %s (%s) · M2 YoY %s (%s) · GAP %s điểm · gia tốc M2 kỳ t %s · kỳ t−1 %s" % (
            pt(td.get("v"), 2), ky_ngan(td.get("ky")), pt(m2.get("v"), 2), ky_ngan(m2.get("ky")),
            so(dv.get("gap"), 2), so(acc[0] if acc else None, 3, True),
            so(acc[1] if len(acc) > 1 else None, 3, True)),
        "OMO %s (kỳ trước %s, %s) · ON %s (%s) · Δ ON 3 phiên %sbp (EST)" % (
            pt(dv.get("omo"), 2), pt(dv.get("omo_prev"), 2), dv.get("omo_asof") or CO,
            pt(on.get("v"), 2), on.get("asof") or CO, so(dv.get("d_on_3p_bp"), 0, True)),
        ("Q2 Corporate (Toàn Vũ %s · %s): %s · mẫu /%s" % (dmy(q.get("ngay_tep")), q.get("bac") or "SS-T3",
                                                          q2_doan(q) or CO, pp(q.get("mau"))) if q else
         "Q2 Corporate: <b>[CẦN DATA — Q2 Corporate]</b> — thiếu 1 trong 3 câu hỏi → DỪNG (S:99, R:177)"),
        "Luật: RẺ ⇔ gia tốc M2 &gt; 0 hai kỳ liền và GAP &lt; 10 và OMO &lt; 4,50%; ĐẮT ⇔ GAP ≥ 10 và không RẺ; "
        "còn lại DỪNG [CẦN DATA] (vùng giữa phương pháp không định nghĩa); thiếu Q2 Corporate → DỪNG.",
    ]
    if dung:
        dong_.append("<b>Dừng:</b> %s" % e(ly_do_dung(cg)))
        if tham_chieu(cg):
            dong_.append(e(tham_chieu(cg)))
    dong_ += ["⚠ %s" % e(x) for x in cobj.get("canh_bao") or []]
    bc = cg.get("boi_canh") or {}
    if bc:
        dong_.append("Bối cảnh (không vào luật): Regime Hub %s %s · %s · %s — trend/breadth kỹ thuật, "
                     "không phải chu kỳ tiền." % (bc.get("regime") or CO, so(bc.get("score"), 1),
                                                   bc.get("luc") or CO, bc.get("bac") or "EST"))
    mau = {"ok": "info", "canh_bao": "warn", "dung": "bear"}[cobj["muc"]]
    return ghi(cobj["dong"], "<br>".join(dong_), "CỔNG", mau)


# ───────────────────────────── bằng chứng (chỉ hiển thị) ─────────────────────────────

def bc_khoi(ct, k):
    v = g(ct, "bang_chung", k)
    return v if isinstance(v, (dict, list)) else None


def ph_tom(ph, key):
    ds = [x for x in (ph.get(key) or []) if isinstance(x, dict)]
    return len(ds), (max(ds, key=lambda x: str(x.get("ngay") or "")) if ds else None), ds


def yd_ngay(x):
    s = ("~" if x.get("ngay_uoc") else "") + dmy(x.get("ngay"))
    return "dự kiến " + s if x.get("du_kien") else s


def yd_ds(ct):
    yd = bc_khoi(ct, "y_do")
    return None if not isinstance(yd, list) else [x for x in yd if isinstance(x, dict)]


def so_huu_the(ct):
    """Tile 'Sở hữu' (D6.4): 'NN 5,6% · NN/trần 58%' + phụ đề nguồn."""
    sh = bc_khoi(ct, "so_huu")
    if not isinstance(sh, dict):
        return the("SỞ HỮU", CO, "[CẦN DATA] chưa có bằng chứng sở hữu (KHO free_float / Vietcap)", "dim", "")
    v = "NN %s · NN/trần %s" % (pt(sh.get("nn_pct"), 1), pt(sh.get("nn_tren_tran_pct"), 0))
    s = "Nhà nước %s · trần NN %s · %s %s%s" % (
        pt(sh.get("nha_nuoc_pct"), 2), pt(sh.get("tran_nn_pct"), 0),
        {"kho_free_float": "KHO", "vietcap_fundamentals": "dự phòng Vietcap"}.get(sh.get("nguon"), sh.get("nguon") or CO),
        dmy(sh.get("luc")), " · lệch nguồn %s điểm %%" % so(sh.get("lech_pp"), 1) if so_num(sh.get("lech_pp")) else "")
    mau = "warn" if sh.get("kin_room") or sh.get("nha_nuoc_chi_phoi") else ""
    return the("SỞ HỮU", v, s, mau, sh.get("bac") or "FACT-T2")


# ───────────────────────────── 9 · chuthe ─────────────────────────────

COT_CT = [cot("ma", "Mã", "left"), cot("ct", "Chủ thể (bậc)", "left"), cot("nv", "Nguyên văn", "left"),
          cot("nn", "Nhà nước %"), cot("khoa", "Khoá % (=100−FF)"), cot("room", "NN/trần NN %"),
          cot("thu", "Thu tiền 24T (n · mới nhất)", "left"), cot("kthu", "Không thu tiền 24T (n)"),
          cot("tv", "Tăng vốn 25–26 (TV)", "left"), cot("yd", "Ý đồ curated (n · mới nhất · bậc)", "left"),
          cot("pct", "pct3Y"), cot("o2n", "Ô 2N", "left"), cot("pb", "Playbook", "left"), cot("cb", "⚠", "left")]
COT_YD = [cot("ma", "Mã", "left"), cot("loai", "Loại", "left"), cot("ngay", "Ngày", "left"),
          cot("td", "Tiêu đề", "left"), cot("ng", "Nguồn", "left"), cot("bac", "Bậc", "left")]
NHOM = {"cần": 1, "không cần": 2, "trung tính": 3}


def nhom_ct(ct):
    return 0 if xung_dot(ct) else NHOM.get(nhan(ct), 4)


def _o_ph(ct, n):
    ph = bc_khoi(ct, "phat_hanh_24t")
    if not isinstance(ph, dict):
        return {"thu": "[CẦN DATA]", "kthu": "[CẦN DATA]"}, {}, {}, {}, {}
    n1, moi, ds1 = ph_tom(ph, "thu_tien")
    n2, _, ds2 = ph_tom(ph, "khong_thu_tien")
    v = {"thu": "%d · %s %s" % (n1, moi.get("loai") or CO, dmy(moi.get("ngay"))) if moi else "0", "kthu": str(n2)}
    tag = {"thu": "có thể thiếu" if ph.get("cat_cut") else ""}
    tip = {"thu": "; ".join("%s %s" % (dmy(x.get("ngay")), x.get("nguyen_van") or x.get("loai") or CO) for x in ds1),
           "kthu": "; ".join("%s %s" % (dmy(x.get("ngay")), x.get("nguyen_van") or x.get("loai") or CO) for x in ds2)}
    mau = {"thu": "amber" if n == "không cần" and n1 else ""}
    return v, tag, tip, mau, {"thu": n1, "kthu": n2}


def _ty(v):
    return "%s tỷ" % so(v / 1e9, 0) if so_num(v) is not None and v >= 1e9 else so(v, 0)


def dong_ct(c, s):
    m = c.ma[s]
    ct = ct_of(c, s)
    n, xd = nhan(ct), xung_dot(ct)
    sh = bc_khoi(ct, "so_huu") if isinstance(bc_khoi(ct, "so_huu"), dict) else {}
    tv = bc_khoi(ct, "tang_von_tv") if isinstance(bc_khoi(ct, "tang_von_tv"), dict) else None
    yd = yd_ds(ct)
    fh = ff_hien(g(m, "ff"))  # Khoá % = 100 − FF của CHÍNH mẫu số FFT (S:189 — một con số, không đếm hai lần)
    khoa = round(100 - fh["p"], 4) if fh["p"] is not None else None
    lt, ltip = lech_thoi(m, c.lk)
    vph, tag, tip, mau, sort = _o_ph(ct, n)
    cb = ds_chu(ct.get("canh_bao"))
    nv = nguyen_van(ct) or ("ghi chú ngành: " + " · ".join(ghi_chu_nganh(ct)) if ghi_chu_nganh(ct) else "")
    tvs = [x for x in (tv or {}).get("su_kien") or [] if isinstance(x, dict)]
    tvv = {True: "có", False: "không"}.get((tv or {}).get("tang_von_2025_26"), CO)
    y0 = yd[0] if yd else None
    vals = {"ma": s, "ct": ct_hien(ct) or "[CẦN DATA]", "nv": nv,
            "nn": pt(sh.get("nha_nuoc_pct"), 2), "khoa": pt(khoa, fh["nd"]), "room": pt(sh.get("nn_tren_tran_pct"), 0),
            "tv": tvv, "yd": ("[CẦN DATA]" if yd is None else
                              ("%d · %s %s · %s" % (len(yd), y0.get("loai") or CO, yd_ngay(y0), y0.get("bac") or CO)
                               if y0 else "0")),
            "pct": pp(g(m, "tuan", "pct3y")), "o2n": g(m, "bocung", "o_2n") or CO, "pb": pb_ma(c, s),
            "cb": "; ".join(cb)}
    vals.update(vph)
    tag.update(ma=dm_tag(m), ct=(ct.get("bac") or "") if n else "", khoa="⚠" if fh["canh"] else "", pct=lt,
               nn="≥75%" if sh.get("nha_nuoc_chi_phoi") else "", room="kín room" if sh.get("kin_room") else "")
    tip.update(ma=dm_tip(m), nv="; ".join(mot_kd(k) for k in khang_dinh(ct)), pct=ltip,
               khoa="; ".join(x for x in [fh["tip"]] + ds_chu(g(m, "ff", "canh_bao")) if x),
               nn="%s · %s%s" % (sh.get("nguon") or CO, dmy(sh.get("luc")),
                                 " · lệch %s điểm %%" % so(sh.get("lech_pp"), 1) if so_num(sh.get("lech_pp")) else "")
               if sh else "",
               tv="; ".join("%s: %s → %s%s" % (x.get("ky") or CO, _ty(x.get("vdl_truoc")), _ty(x.get("vdl_sau")),
                                               " · " + x["hinh_thuc"] if x.get("hinh_thuc") else "") for x in tvs),
               yd="; ".join("%s %s %s (%s)" % (yd_ngay(x), x.get("loai") or CO, x.get("tieu_de") or "",
                                               x.get("bac") or CO) for x in yd or []))
    mau.update(ct="amber" if xd else ("info" if n else "dim"), cb="amber" if cb else "",
               nv="dim" if not nguyen_van(ct) else "", khoa="amber" if fh["canh"] else "", pct="amber" if lt else "")
    sort.update(nn=so_num(sh.get("nha_nuoc_pct")), khoa=khoa, room=so_num(sh.get("nn_tren_tran_pct")),
                yd=len(yd) if yd is not None else None, pct=so_num(g(m, "tuan", "pct3y")))
    return dong(vals, sort=sort, mau=mau, tag=tag, tip=tip, vien="amber" if xd else ("info" if n else ""), link=s)


def q2_tile(c):
    q = q2_cong(c.cong) or (g(c.cd, "q2") if isinstance(g(c.cd, "q2"), dict) else None)
    nam = q2_nam(q)
    ys = sorted(nam)
    if not ys:
        return the("Q2 CORPORATE", CO, "[CẦN DATA — Q2 Corporate]", "warn", "")
    y0, bac = (ys[-2] if len(ys) > 1 else ys[-1]), q.get("bac") or "SS-T3"
    s = bac
    if len(ys) > 1:  # "2026 tới 07: 15/10 · SS-T3"
        la = nam[ys[-1]]
        den = str(la.get("den_ky") or q.get("den_ky") or "")
        s = "%s%s: %s/%s · %s" % (ys[-1], " tới %s" % den[5:7] if den[:4] == ys[-1] and len(den) >= 7 else "",
                                  pp(la.get("so_su_kien")), pp(la.get("so_ma")), bac)
    v = nam[y0]
    return the("Q2 CORPORATE %s" % y0, "%s sự kiện · %s/%s mã" % (pp(v.get("so_su_kien")), pp(v.get("so_ma")),
                                                                  pp(q.get("mau") or 30)), s, "", bac)


def v_chuthe(c):
    sc, ds = c.scope, sorted(c.members, key=lambda s: (nhom_ct(ct_of(c, s)), s))
    d, N = dem_nhan(c), len(c.members)
    nct = g(c.lk, "nguon", "chu_the") if isinstance(g(c.lk, "nguon", "chu_the"), dict) else {}
    nsh = [g(ct_of(c, s), "bang_chung", "so_huu", "nguon") for s in c.members]
    ydn = nct.get("y_do") if isinstance(nct.get("y_do"), dict) else {}
    n_cur, n_ver = so_num(ydn.get("n_curated")), so_num(ydn.get("n_verified"))
    yd_ro = [(s, x) for s in c.members for x in (yd_ds(ct_of(c, s)) or [])]
    bacs = [ct_of(c, s).get("bac") for s in c.members if nhan(ct_of(c, s))]
    tiles = [
        the("CÓ NHÃN", "%d/%d" % (d["a"] + d["b"] + d["k"], N), "SS-T3 %d · EST %d%s · %s" % (
            d["a"], d["b"], " · khác %d" % d["k"] if d["k"] else "", ", ".join(sorted(d["ngay"])) or CO),
            "info", bac_yeu(bacs)),
        the("XUNG ĐỘT", "%d/%d" % (d["x"], N), "nguồn mâu thuẫn — [CẦN DATA — nhãn xung đột], không chọn bên (S:477)",
            "amber" if d["x"] else "dim", "EST"),
        the("CẦN DATA", "%d/%d" % (d["con"], N), "chưa có nhãn — không suy thành 'trung tính'", "dim", ""),
        q2_tile(c),
        the("NGUỒN SỞ HỮU", "KHO %d · dự phòng Vietcap %d" % (nsh.count("kho_free_float"),
                                                             nsh.count("vietcap_fundamentals")),
            "rổ %s · %d mã chưa có · toàn vũ trụ: KHO %s · tệp Vietcap phủ %s mã" % (
                sc, N - nsh.count("kho_free_float") - nsh.count("vietcap_fundamentals"),
                pp(g(nct, "so_huu", "kho_n")), pp(g(nct, "so_huu", "du_phong_n"))), "", "FACT-T2"),
        the("Ý ĐỒ CURATED", "%s · %s SS-T3 · %s UNVERIFIED" % (
            pp(n_cur), pp(n_ver), pp(n_cur - n_ver) if n_cur is not None and n_ver is not None else CO)
            if n_cur is not None else CO,
            "owner_intent · auto bỏ qua %s · trong rổ: %d sự kiện / %d mã" % (
                pp(ydn.get("n_auto_bo_qua")), len(yd_ro), len({s for s, _ in yd_ro})), "", "UNVERIFIED")]
    b = bang("chuthe", "Chủ thể cần thị trường — %s · %d mã" % (sc, N), COT_CT, [dong_ct(c, s) for s in ds],
             "Thứ tự: xung đột → cần → không cần → trung tính → chưa nhãn; trong nhóm A→Z", T.CT_CAPTION)
    yrows = sorted(yd_ro, key=lambda sx: (str(sx[1].get("ngay") or ""), sx[0]), reverse=True)
    yb = bang("y_do", "Ý đồ chủ thể — sự kiện curated (owner_intent)", COT_YD,
              [dong({"ma": s, "loai": x.get("loai") or CO, "ngay": yd_ngay(x), "td": x.get("tieu_de") or CO,
                     "ng": x.get("nguon") or CO, "bac": x.get("bac") or CO},
                    mau={"bac": "dim" if x.get("bac") == "UNVERIFIED" else "info"}, link=s) for s, x in yrows],
              "chỉ sự kiện auto=false · lọc theo rổ %s · sắp ngày giảm dần" % sc,
              "Tiêu đề giữ nguyên như tệp (không dấu). ~ = ngày ước; 'dự kiến' = ngày trong tương lai. "
              "UNVERIFIED không dùng cho quyết định; không vào luật CỔNG hay playbook.")
    note = ghi("Câu bắt buộc — Pillar III", "<br>".join(
        ("<b>%s</b> “%s”" % (r, e(t)) if r else e(t)) for r, t in T.CHUTHE_BAT_BUOC), "Bắt buộc", "info")
    blocks = [note, {"type": "tiles", "items": tiles}, b]
    blocks.append(yb if yrows else ghi("Sự kiện curated", "[CẦN DATA] owner_intent chưa đọc được." if all(
        yd_ds(ct_of(c, s)) is None for s in c.members) else "Không có sự kiện curated cho mã nào trong rổ %s." % sc,
        "", "dim"))
    loi = ds_chu(nct.get("loi"))
    if loi:
        blocks.append(ghi("Lỗi nguồn chủ thể", "<br>".join(e(x) for x in loi), "Kiểm", "warn"))
    ngs = [ct_of(c, s).get("ngay") for s in c.members if nhan(ct_of(c, s)) or xung_dot(ct_of(c, s))]
    moc = max((x for x in ngs if ngay(x)), key=lambda x: ngs.count(x), default=None)
    tuoi = (c.now.date() - ngay(moc)).days if moc else None
    return {"title": "Ý đồ chủ thể — Pillar III · %s" % sc,
            "sub": "Nhãn %s%s (không tự hết hạn) · bằng chứng: sở hữu KHO/Vietcap · ISS 24T · Toàn Vũ · owner_intent" % (
                dmy(moc) if moc else "[CẦN DATA]", " · %d ngày tuổi" % tuoi if tuoi is not None else ""),
            "blocks": blocks, "data": phang(b)}
