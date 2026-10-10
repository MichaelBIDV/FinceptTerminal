#!/usr/bin/env python3
"""
Fincept Terminal: Chaebol Reflex pages (tab "msn_reflex", label "Chaebol Reflex"), spec §7–§8.

Builds the vnblocks/1 payloads the panel renders, from the group registry (chaebol_reflex_live.load_registry), the
live engine (chaebol_reflex_live.LiveNhom), the per-group dossiers and councils, and the framework library
(chaebol_reflex_khung). Stdlib only, Python 3.9+, NO network, read-only everywhere. chaebol_reflex.py is the CLI.

INPUTS under the registry root <R> (= CHAEBOL_REFLEX_DIR, default knowledge_os/chaebol_reflex), all optional except
nhom.json; a missing part drops its section with a warning, nothing is invented:
  <R>/nhom.json                     registry "chaebol_reflex_nhom/1"
  <R>/<id>/ho_so_YYYY-MM-DD.json    dossier "chaebol_ho_so/1" (newest valid wins; with --den, files dated after the
                                    cut are skipped)
  <R>/<id>/hoi_dong_YYYY-MM-DD.json council "chaebol_hoi_dong/1" (same rule)
  <R>/khung.json                    framework library "chaebol_khung/1"
A group with "dong_co": "msn_reflex" (Masan) keeps its own engine and dossier: msn_reflex.build_overview().

PAGES (every page: {"meta", "live", "trang": {"schema": "vnblocks/1", "tieu_de", "sections"}, "csv"})
  build_page(nhom=None, ma=None, den=None, root=None)
    nhom None / "tong_quan" → TỔNG QUAN; ma → the ticker's first group (parent > LT child > any, registry order).
  Group page section ids, in order (a section without data is skipped with a warning):
    cong · he_sinh_thai · theo_doi_tuan · keynotes · truyen_dan · do_tre · dot_tang · khung · y_do_chu_the ·
    su_kien · xuc_tac · vung_gia · hoi_dong · nhan_dinh_cu · pre_mortem · xung_dot · viec_treo · nguon
    Charts: rebased 100 (mẹ + members + VN-Index), mẹ ÷ LT weekly with the 3-year p25–p75 band, weekly mẹ price
    with σ bands, P/B (else P/E) with ±1σ/±2σ, KL ÷ TB20 bars, "cot" lagged correlation. A group without a priced
    parent has no ratio chart and no parent price chart; its time axis is the largest-cap member.
    he_sinh_thai: one table of the listed members with prices (MEMBER_COLS) and one compact table of the members
    without prices on this machine (TEN_KHONG_GIA: unlisted, abroad, or listed without a price).
    khung: per framework the dossier maps, a one-line description + the group's frozen mapping rows, then the live
    measurable signs; never a framework's full content (chaebol_reflex_khung.section_khung).
  TỔNG QUAN ids: cong · nhom · ty_so_nhom · capture · thu_vien_khung · concentration_era · nguon. Built on ONE lite
    KhoNhom: vnstore for every ticker, Vietcap files only for the look-through core of each group (lt_core) plus
    each parent-less group's axis, LiveNhom(lite=True); every percentile shows "từ dd/mm/yyyy · n tuần" (≥ 52 weeks
    or [CẦN DATA]); Masan's bar is labelled with its own window (từ 01/2024 · engine Masan). thu_vien_khung = the
    library index + the main stage/phase table of the core frameworks; concentration_era = its description, "Cốt
    lõi" and the names of its parts (full text in khung.json); nguon merges the per-ticker Vietcap files.
  Masan: msn_reflex.build_overview() sections in place, every one guarded unit by unit with "ĐÓNG BĂNG · hồ sơ MSN
    <ngày>", + "do_tre" and "khung" inserted before "nguon"; meta gains "nhom" and "ds_nhom"; msn_reflex's own
    meta.warnings are kept and get at most ONE appended line pointing to the engine's added warnings.
  Warnings: meta.warnings is a summary of at most MAX_META_WARNINGS lines (tom_tat_canh_bao: data gaps first, the
    guard notes in one line, the per-group counts of TỔNG QUAN in one line); the FULL list is a canh_bao block at
    the end of the "nguon" section. Source cells show shortened paths (chaebol_reflex_khung.ngan) with the full
    string in the cell tip.
  meta: generated, script_version, nhom {id, ten, me, so_ma, co_ho_so, co_hoi_dong}, ds_nhom [{id, ten, truc, me,
    co_hoi_dong}] (TỔNG QUAN, then truc NQ68, NQ79, SPECIAL, KG21, V21, others; registry order inside a truc),
    registry_file, profile_dir, profile_file, profile_date (TỔNG QUAN: the registry lap_luc), hoi_dong_file,
    hoi_dong_date, khung_file, artifact_url, data_to, den, age_days, profile_age_days, stale, stale_text, warnings,
    sources_live.
  Every page opens with the dossier's CỔNG line, else CONG_MAC_DINH. CỔNG v1.7 DỪNG: no order, rating, sizing or
    target-price text is generated; dossier stances appear only as "ĐÓNG BĂNG · <nguồn> <ngày>" history, and every
    unit (paragraph, table row, list item, card, tile) that carries such words is labelled that way
    (chaebol_reflex_khung.guard_blocks) with a warning. Dossier tables carry a "Nhãn" tier column (UNVERIFIED when
    the row has none).

ALL-IN-ONE  o_aio(ma, den=None, root=None) -> None (ticker in no group, or no registry) | {"id": "reflex",
  "tieu_de": "Chaebol Reflex · <nhóm>[ · <nhóm>]", "eyebrow", "tab": "msn_reflex", "tab_nhan": "Chaebol Reflex",
  "cot": 12, "tier", "khoi": [vnblocks blocks, one small block per group], "trang_thai_ngay": ISO data_to,
  "ho_so_ngay": ISO | None, "nhom_ids": [ids, open-order], "nhom_mo": first id, "canh_bao": [warnings]}.
  One shared KhoNhom: vnstore for every ticker of the ticker's groups, Vietcap files for a reduced member set (the
  ticker, the parent, LT children, holding chain, holdco layers, dossier signal tickers) plus the FULL group's time
  axis (chon_co_so), passed as co_so so the cell and the group page share base and data day; under 1 s per ticker.
"""

from __future__ import annotations

import bisect
import copy
import os
import re
from datetime import date, datetime, timedelta

import chaebol_reflex_khung as K
import chaebol_reflex_live as L
import msn_reflex as M

SCRIPT_VERSION = "1.0"
SCHEMA_HO_SO = "chaebol_ho_so/1"
SCHEMA_HOI_DONG = "chaebol_hoi_dong/1"
HO_SO_RE = re.compile(r"ho_so_(\d{4}-\d{2}-\d{2})\.json")
HOI_DONG_RE = re.compile(r"hoi_dong_(\d{4}-\d{2}-\d{2})\.json")
TONG_QUAN = "tong_quan"
TEN_TONG_QUAN = "TỔNG QUAN"
MSN_DONG_CO = "msn_reflex"
TAB_ID, TAB_NHAN = "msn_reflex", "Chaebol Reflex"
AIO_EYEBROW = "Casebook · độ trễ mẹ–con"
CONG_MAC_DINH = "CỔNG: [CẦN DATA] · v1.7 DỪNG (chuỗi M2 gãy 10/2025) · chủ thể [CẦN DATA] · playbook: không phát"
TRUC_ORDER = ("NQ68", "NQ79", "SPECIAL", "KG21", "V21")
SIDS = ("cong", "he_sinh_thai", "theo_doi_tuan", "keynotes", "truyen_dan", "do_tre", "dot_tang", "khung",
        "y_do_chu_the", "su_kien", "xuc_tac", "vung_gia", "hoi_dong", "nhan_dinh_cu", "pre_mortem", "xung_dot",
        "viec_treo", "nguon")
TQ_SIDS = ("cong", "nhom", "ty_so_nhom", "capture", "thu_vien_khung", "concentration_era", "nguon")
CSV_COLS = ["Mục", "Chỉ báo", "Giá trị", "Kỳ", "Trạng thái", "Nhãn", "Ghi chú"]
MEMBER_COLS = ["Mã · tên", "Vai trò", "Pháp lý · hiệu dụng", "As-of · bậc", "Vốn hóa (nghìn tỷ)", "Phần mẹ nắm (nghìn tỷ)",
               "% tuần", "% 13 tuần", "YTD", "σ P/B (P/E)"]
TEN_KHONG_GIA = "Thành viên chưa niêm yết · không có giá trên máy"
KHONG_GIA_COLS = ["Tên", "Vai trò", "Mẹ trực tiếp", "Tỷ lệ (pháp lý · hiệu dụng)", "As-of · bậc", "Ghi chú"]
SOURCE_COLS = ["Nguồn", "Dữ liệu đến", "Nhãn", "Trạng thái", "Đường dẫn · ghi chú"]
VC_FILE = re.compile(r"/vc_lk/([A-Z0-9]{3,10})/([^/]+)$")
LOG_WEEKS = 13
MAX_LOG_MA = 6
MAX_CORR_SERIES = 4
MAX_CAPTURE_ROWS = 12
MAX_CYCLES = 4
AIO_SIGNALS = 3
AIO_EVENTS = 3
CUT = 280
PHIEU_MAU = {"ỦNG HỘ": "xanh", "PHẢN BIỆN": "do", "CHỜ DỮ LIỆU": "vang"}
XUC_TAC_MAU = {"ĐẠT": "xanh", "CHƯA": "xam", "CHỜ": "vang", "HỎNG": "do"}
SIGNAL_MAU = {"Đạt": "xanh", "An toàn": "xanh", "Kích hoạt": "do", "Chưa": "xam"}
DB = K.DONG_BANG
CAN, T_DATA, T_EST = M.CAN, M.T_DATA, M.T_EST
T_UNV = "UNVERIFIED"
LOG_TIER = "FACT-T2 giá · EST LT/tỷ số"
GHI_CHU_CUT = 120
MAX_META_WARNINGS = 8
MAX_TEN_MUC = 6
TEN_CANH_BAO = "Cảnh báo dữ liệu"
# meta.warnings summary (tom_tat_canh_bao): the full list stays in the "nguon" section
W_DEM = re.compile(r"^(?:Nhóm|Registry) ([a-z0-9_]+): (\d+) cảnh báo dữ liệu \(mở trang nhóm để xem\)\.$")
W_GUARD = re.compile(r"^(?:Mục \"(?P<muc>.+?)\"|(?P<noi>.+?))(?: trích lệnh, xếp hạng, định cỡ vị thế hoặc mức giá của "
                     r"nguồn|: tiêu đề mục trích ngôn ngữ lệnh)")
W_LIVE = re.compile(r"^Thiếu nguồn live (.+?) ([A-Z0-9]{3,10}) \(.*\)$")
W_NEN = re.compile(r"^Kho giá thiếu nến của: (.+)$")
W_LAG = re.compile(r"^Nhóm (\S+): giá (\S+) dừng ở (\d\d/\d\d/\d{4}), trễ (\d+) ngày so với ngày dữ liệu "
                   r"(\d\d/\d\d/\d{4}) của nhóm \(trục (\S+)\); số của \S+ là của ngày đó\.$")
W_GAP = re.compile(r"Kho giá chưa có phiên mới|dừng ở \d\d/\d\d/\d{4}, trễ|chỉ có giá đến|chưa có dòng sở hữu từ|"
                   r"không chạy được|^Không đọc được|^Thiếu nguồn live|không mã nào có giá|không có giá, tính như nhóm "
                   r"không có mẹ|không con nào đủ điều kiện|^Bỏ (?:hồ sơ|Hội đồng) |chưa có hồ sơ|không ghi v1\.7 DỪNG|"
                   r"^Chưa có (?:registry|thư viện)|sai schema|thiếu cột|đếm hai lần|bảng điện \(vci_board\), bỏ")

nfc, as_dict, as_list, cell, bang, doan, heading, tile = (M.nfc, M.as_dict, M.as_list, M.cell, M.bang, M.doan,
                                                          M.heading, M.tile)
add_warning, iso, txt = L.add_warning, L.iso, K.txt


# ── small helpers ────────────────────────────────────────────────────────────


def dmy(v):
    d = v if isinstance(v, date) else M.parse_day(v)
    return M.ddmmyyyy(d) if d else ""


def cut(s, n=CUT):
    return K.cut(s, n)


def src_txt(item):
    """"nguồn · ngày" of a dossier item."""
    it = as_dict(item)
    return " · ".join(x for x in (txt(it.get("nguon")), dmy(it.get("ngay"))) if x)


def src_cell(text, **kw):
    """A source / note table cell: absolute paths shortened, the full string in the cell tip."""
    return K.nguon_cell(text, **kw)


def tom_tat_canh_bao(ws, cap=MAX_META_WARNINGS):
    """meta.warnings, concise (≤ cap lines; the panel prints every line in amber at the top). First the data gaps
    (missing Vietcap files and missing candles merged into one line per kind, stale data or axis, stake gaps that
    drop weeks, skipped or missing dossiers, engine failures, gate integrity), then ONE line for the guard notes
    naming the sections, ONE line for the per-group counts (TỔNG QUAN), then how many other notes only the full list
    holds (canh_bao block of the "nguon" section)."""
    gap, live, lag, nen, muc, dem, khac = [], {}, {}, [], [], {}, 0
    for w in ws:
        m = W_LAG.match(w)
        if m:
            key = m.group(1, 3, 4, 5, 6)
            if key not in lag:
                lag[key] = []
                gap.append(key)
            lag[key].append(m.group(2))
            continue
        m = W_DEM.match(w)
        if m:
            dem[m.group(1)] = dem.get(m.group(1), 0) + int(m.group(2))
            continue
        m = W_GUARD.match(w)
        if m:
            muc.append(m.group("muc") or m.group("noi"))
            continue
        m = W_LIVE.match(w)
        if m:
            live.setdefault(m.group(1), []).append(m.group(2))
            continue
        m = W_NEN.match(w)
        if m:
            nen += [x for x in m.group(1).split(", ") if x and x not in nen]
            continue
        if W_GAP.search(w):
            gap.append(K.ngan(w))
        else:
            khac += 1
    head = ["Thiếu nguồn live %s của %d mã: %s" % (k, len(v), K.ds_ids(v)) for k, v in live.items()]
    if nen:
        head.append("Kho giá thiếu nến của %d mã: %s" % (len(nen), K.ds_ids(nen)))
    for g in gap:
        if isinstance(g, str):
            head.append(g)
        elif len(lag[g]) == 1:
            head.append("Nhóm %s: giá %s dừng ở %s, trễ %s ngày so với ngày dữ liệu %s của nhóm (trục %s); số của %s là "
                        "của ngày đó." % (g[0], lag[g][0], g[1], g[2], g[3], g[4], lag[g][0]))
        else:
            head.append("Nhóm %s: giá của %d mã dừng ở %s, trễ %s ngày so với ngày dữ liệu %s của nhóm (trục %s): %s; số "
                        "của các mã đó là của ngày đó." % (g[0], len(lag[g]), g[1], g[2], g[3], g[4], K.ds_ids(lag[g])))
    agg = []
    if muc:
        names = list(dict.fromkeys(muc))
        agg.append("%d mục trích lệnh, xếp hạng, định cỡ vị thế hoặc mức giá của nguồn, hiển thị như lịch sử %s, không "
                   "chấm lại (CỔNG v1.7 DỪNG): %s." % (len(names), DB, K.ds_ids(names, MAX_TEN_MUC)))
    if dem:
        agg.append("%d nhóm có cảnh báo dữ liệu (tổng %d) · mở trang nhóm để xem" % (len(dem), sum(dem.values())))
    if len(head) + len(agg) + (1 if khac else 0) > cap:
        room = max(0, cap - len(agg) - 1)
        khac += len(head) - room
        head = head[:room]
    out = head + agg
    if khac:
        out.append("Còn %d cảnh báo khác · danh sách đủ ở khối \"%s\" cuối trang (mục Nguồn)." % (khac, TEN_CANH_BAO))
    return out[:cap]


def source_row(s):
    """One row of a live-sources table (a msn_reflex.Kho source dict)."""
    return [cell(nfc(s.get("ten")), dam=True), cell(s.get("as_of") or CAN, mono=True), M.tier_cell(s.get("tier")),
            M.pill("OK" if s.get("ok") else "THIẾU", "xanh" if s.get("ok") else "do"),
            src_cell("%s%s" % (s.get("duong_dan") or "", (" · " + s["ghi_chu"]) if s.get("ghi_chu") else ""))]


def gop_nguon(srcs):
    """TỔNG QUAN: per-ticker Vietcap files (…/vc_lk/<MÃ>/<tệp>) merged into one source per (name, file, status) with
    the ticker list; every other source unchanged. Order of first appearance."""
    out, by = [], {}
    for s in srcs:
        m = VC_FILE.search(nfc(s.get("duong_dan")))
        ten = nfc(s.get("ten"))
        if not (m and ten.endswith(" " + m.group(1))):
            out.append(s)
            continue
        key = (ten[:-len(m.group(1)) - 1], m.group(2), bool(s.get("ok")))
        if key not in by:
            by[key] = dict(s, ten=key[0], duong_dan=s["duong_dan"][:m.start(1)] + "<MÃ>/" + m.group(2), _ma=[],
                           _as_of=[])
            out.append(by[key])
        g = by[key]
        g["_ma"].append(m.group(1))
        if s.get("as_of"):
            g["_as_of"].append(s["as_of"])
    for g in by.values():
        a = sorted(set(g.pop("_as_of")))
        mas = g.pop("_ma")
        g.update({"ten": "%s · %d mã" % (g["ten"], len(mas)), "as_of": (a[0] if len(a) == 1 else
                                                                        "%s → %s" % (a[0], a[-1])) if a else None,
                  "ghi_chu": "mã: " + ", ".join(mas) + ((" · " + g["ghi_chu"]) if not g.get("ok") and g.get("ghi_chu")
                                                       else "")})
    return out


def canh_bao_nguon(sections, warnings, tieu_de=None):
    """The FULL warning list as one canh_bao block at the end of the "nguon" section (else the last section)."""
    host = next((s for s in sections if s.get("id") == "nguon"), sections[-1] if sections else None)
    if host is not None:
        host["khoi"] += [b for b in K.guard_blocks([M.canh_bao(tieu_de or TEN_CANH_BAO, warnings)],
                                                   "cảnh báo dữ liệu") if b]


def tier_of(item):
    return ", ".join(M.tier_list(as_dict(item).get("tier")))


def nhan_cell(item):
    """The tier column of a dossier row; a row without a tier is UNVERIFIED (not for decisions)."""
    return M.tier_cell(tier_of(item) or T_UNV)


def items(lst, key):
    """Dossier list → dicts; a bare string / number becomes {key: value} (curators sometimes write plain text)."""
    out = []
    for x in as_list(lst):
        if isinstance(x, dict):
            out.append(x)
        elif txt(x):
            out.append({key: x})
    return out


def mo_txt(text, mo):
    """A lead/lag date or lag of an unconfirmed pivot (running extreme of an open leg) gets "(đang mở)"."""
    if not text:
        return "–"
    return "%s (đang mở)" % text if mo else text


def pct_mau(v):
    return "xanh" if (v or 0) > 0 else ("do" if (v or 0) < 0 else None)


def now_iso():
    return datetime.now(M.ICT).isoformat(timespec="seconds")


def truc_rank(t):
    t = nfc(t).upper()
    return TRUC_ORDER.index(t) if t in TRUC_ORDER else len(TRUC_ORDER)


def is_msn(nh):
    return nfc(nh.get("dong_co")) == MSN_DONG_CO


# ── registry, dossiers, councils ─────────────────────────────────────────────


def require_registry(root=None):
    """(Registry, warnings) or MsnError NO_REGISTRY when nhom.json is missing, broken or empty."""
    reg, w = L.load_registry(root)
    if not reg.groups():
        raise M.MsnError("NO_REGISTRY", "Chưa dùng được registry nhóm %s (%s), cài nhom.json schema %s rồi FETCH."
                         % (reg.path, "; ".join(w) or "không có nhóm nào", L.SCHEMA_REG))
    return reg, w


def reg_root(reg):
    return os.path.dirname(reg.path)


def load_dated(pdir, rx, schema, den, warnings, ten, day_key):
    """Newest <pdir>/<rx> with the right schema (dated on/before den when given) → (dict, path, day)."""
    for ky, path in M.list_dated(pdir, rx):
        d = M.parse_day(ky)
        if den and d > den:
            add_warning(warnings, "Bỏ %s %s: lập sau mốc --den %s." % (ten, os.path.basename(path), dmy(den)))
            continue
        try:
            raw = M.load_json(path)
        except (OSError, ValueError) as exc:
            add_warning(warnings, "Bỏ %s %s (không đọc được: %s)." % (ten, path, exc))
            continue
        if not isinstance(raw, dict) or raw.get("schema") != schema:
            add_warning(warnings, "Bỏ %s %s (cần schema %s)." % (ten, path, schema))
            continue
        return raw, path, M.parse_day(raw.get(day_key)) or d
    return {}, None, None


def load_dossier(root, nid, warnings, den=None):
    d, p, day = load_dated(os.path.join(root, nid), HO_SO_RE, SCHEMA_HO_SO, den, warnings, "hồ sơ", "ho_so")
    if d and nfc(d.get("nhom")) and nfc(d.get("nhom")) != nid:
        add_warning(warnings, "Hồ sơ %s ghi nhóm \"%s\", khác thư mục %s." % (p, nfc(d.get("nhom")), nid))
    return d, p, day


def load_hoi_dong(root, nid, warnings, den=None):
    return load_dated(os.path.join(root, nid), HOI_DONG_RE, SCHEMA_HOI_DONG, den, warnings, "Hội đồng", "ngay")


def ds_nhom(reg):
    groups = sorted(enumerate(reg.groups()), key=lambda t: (truc_rank(t[1].get("truc")), t[0]))
    out = [{"id": TONG_QUAN, "ten": TEN_TONG_QUAN, "truc": "", "me": None, "co_hoi_dong": False}]
    out += [{"id": g.id, "ten": nfc(g.get("ten")) or g.id, "truc": nfc(g.get("truc")), "me": g.me or None,
             "co_hoi_dong": bool(g.get("hoi_dong"))} for _, g in groups]
    return out


def groups_of_ma(reg, ma):
    """Groups holding the ticker, open order: parent first, then LT child, then any (registry order)."""
    t = L.ticker(ma)
    out = []
    for i, g in enumerate(reg.groups()):
        if not t or t not in g.tickers():
            continue
        m = as_dict(g.member(t))
        rank = 0 if g.me == t else (1 if m.get("trong_lt") else 2)
        out.append((rank, i, g))
    return [g for _, _, g in sorted(out, key=lambda x: (x[0], x[1]))]


def nhom_meta(nh, so_ma=None, co_ho_so=False):
    return {"id": nh.id, "ten": nfc(nh.get("ten")) or nh.id, "me": nh.me or None,
            "so_ma": so_ma if so_ma is not None else len(nh.tickers()),
            "co_ho_so": bool(co_ho_so), "co_hoi_dong": bool(nh.get("hoi_dong"))}


def stale_bits(data_to, pday, warnings):
    now = M.today()
    age = (now - data_to).days if data_to else None
    p_age = (now - pday).days if pday else None
    bits = []
    if age is None or age > M.STALE_DATA_DAYS:
        bits.append("DỮ LIỆU CŨ %s ngày (đến %s)" % (age if age is not None else "?", M.ddmm(data_to)))
        add_warning(warnings, "Kho giá chưa có phiên mới từ %s, chạy lại bộ điều phối (goi_nguon) rồi FETCH."
                    % (dmy(data_to) or "?"))
    if p_age is not None and p_age > M.STALE_PROFILE_DAYS:
        bits.append("HỒ SƠ CŨ %d ngày" % p_age)
    return age, p_age, bits


def msn_overview(den, warnings, cache):
    """msn_reflex.build_overview(den) once per call chain; None (with a warning) when its profile is unusable."""
    if "msn" not in cache:
        try:
            cache["msn"] = M.build_overview(den)
        except M.MsnError as exc:
            add_warning(warnings, "Engine Masan (msn_reflex) không chạy được: %s" % exc.message)
            cache["msn"] = None
    return cache["msn"]


def msn_profile(warnings, cache):
    if "msn_prof" not in cache:
        try:
            prof, path, pday = M.load_profile(M.paths()["profile_dir"])
            cache["msn_prof"] = (prof, path, pday)
        except M.MsnError as exc:
            add_warning(warnings, "Không đọc được hồ sơ Masan: %s" % exc.message)
            cache["msn_prof"] = (None, None, None)
    return cache["msn_prof"]


def shared_kho(groups, den, warnings, vc_syms=None, lite=False):
    """One KhoNhom over every ticker of `groups` (vnstore); per-ticker files only for `vc_syms` (None = all)."""
    syms, eco = [], []
    for g in groups:
        syms += g.tickers()
        eco += [k for k in as_list(g.get("he_sinh_thai")) if k not in eco]
    return L.KhoNhom(M.paths(), den, warnings, syms, eco, vc_syms=vc_syms, lite=lite)


def lt_core(nh):
    """Tickers the look-through of a group needs: the parent, LT children, holdco layers and their holding chains."""
    keep = {nh.me} if nh.me else set()
    keep |= {ma for ma, m in nh.members if ma and m.get("trong_lt")}
    for x in nh.tang:
        keep |= {x["me"]} | set(x["con"])
    return chain_up(nh, keep)


def chain_up(nh, keep):
    keep = set(keep)
    for ma in list(keep):
        up, seen = nh.holder(ma) if ma else "", set()
        while up and up not in seen:
            keep.add(up)
            seen.add(up)
            up = nh.holder(up)
    return {k for k in keep if k}


def parent_priced(kho, nh):
    return bool(nh.me) and (bool(kho.nen.get(nh.me)) or nh.me in kho.vc)


def axis_of(kho, nh):
    """The time-axis ticker of a group without a priced parent (vnstore rule, L.chon_co_so), its files loaded."""
    if parent_priced(kho, nh):
        return None
    cs = L.chon_co_so(kho, nh)
    if cs:
        kho.ensure_vc(cs)
    return cs


# ── charts ───────────────────────────────────────────────────────────────────


def _x_clip(xs, data_to):
    """Friday keys of the open week → the last session (no future date on the axis)."""
    out = []
    for x in xs:
        d = M.parse_day(x)
        out.append((min(d, data_to) if (d and data_to) else d).isoformat() if d else x)
    return out


def chart_rebased(c):
    ch = as_dict(c.js.get("chuoi"))
    xs = as_list(ch.get("x"))
    q = as_dict(ch.get("quy_100"))
    if not xs or not q:
        return None
    order = ([c.me] if c.me in q else []) + [m["ma"] for m in c.tv_list if m.get("ma") in q]
    order = list(dict.fromkeys(order + list(q)))
    mau = as_dict(c.nh.get("mau"))
    series, ann, names = [], [], []
    last_x = c.data_to
    for s in order:
        y = [round(v, 2) if v is not None else None for v in q[s]]
        if not any(v is not None for v in y):
            continue
        ser = {"name": s, "y": y, "style": "line"}
        m = nfc(mau.get(s)) or ("amber" if s == c.me else "")
        if m:
            ser["mau"] = m
        series.append(ser)
        names.append(s)
        lastv = next((v for v in reversed(y) if v is not None), None)
        if lastv is not None:
            ann.append(M.point(last_x, lastv, "%s %s" % (s, M.pct_txt(lastv - 100, 0)), "", m or "dim", "right",
                               1 if s in (c.me, c.base) else 2))
    vni = [round(v, 2) if v is not None else None for v in as_list(ch.get("vni"))]
    if any(v is not None for v in vni):
        series.append({"name": "VN-Index", "y": vni, "style": "thin", "mau": "dim"})
    if not series:
        return None
    late = ["%s từ %s" % (s, dmy(as_dict(ch.get("goc")).get(s))) for s in names
            if as_dict(ch.get("goc")).get(s) and as_dict(ch.get("goc")).get(s) != xs[0]]
    cap = ("Đóng cửa tuần, giá điều chỉnh (vnstore nối Vietcap closePriceAdjusted), quy về 100 ở tuần đầu tiên từ %s; "
           "trục thời gian theo %s%s.%s" % (dmy(ch.get("tu")), c.base, "" if c.me else " (mã vốn hóa lớn nhất, nhóm "
                                                                                     "không có mẹ niêm yết)",
                                           (" Mã có giá muộn hơn quy về 100 ở tuần đầu của nó: %s." % ", ".join(late))
                                           if late else ""))
    block = {"x": _x_clip(xs, c.data_to), "series": series, "left": {"label": "quy về 100 (thang tuyến tính)"},
             "annotations": ann}
    return M.bieu_do("Quy về 100 · %s · theo tuần · LIVE" % ", ".join(names[:8] + ["VN-Index"]), cap,
                     "vnstore · Vietcap price-history · WiData/vnstore (VN-Index)", T_DATA, block, 320)


def chart_ratio(c):
    ts = c.js.get("ty_so")
    if not ts:
        return None
    frm = M.parse_day(as_dict(c.nh.get("cua_so")).get("ratio_from"))
    s3 = as_dict(as_dict(ts.get("thong_ke")).get("3y"))
    # The x axis starts where the 3-year statistics start when that is earlier than ratio_from, so the p25–p75 band,
    # the median and the max/min points describe what is drawn; weeks before ratio_from are drawn dotted.
    tu3 = M.parse_day(s3.get("tu"))
    start = tu3 if tu3 and (frm is None or tu3 < frm) else frm
    rows = [r for r in as_list(ts.get("tuan")) if r.get("r") is not None
            and (start is None or r["fri"] >= start.isoformat())]
    if not rows:
        return None
    truoc = frm is not None and start is not None and start < frm

    def phan(r):
        return "truoc" if truoc and r["fri"] < frm.isoformat() else ("du" if r["du"] else "bo")

    x = [r["last"] for r in rows]
    y = [round(r["r"], 4) if phan(r) == "du" else None for r in rows]
    y_bo = [round(r["r"], 4) if phan(r) == "bo" else None for r in rows]
    y_truoc = [round(r["r"], 4) if phan(r) == "truoc" else None for r in rows]
    if ts.get("hien_tai") is not None and c.data_to and c.data_to.isoformat() > rows[-1]["last"]:
        x.append(c.data_to.isoformat())
        y.append(round(ts["hien_tai"], 4))
        y_bo.append(None)
        y_truoc.append(None)
    n = len(x)
    series = []
    if s3.get("p25") is not None:
        series.append({"name": "p25–p75 · 3 năm", "style": "band", "mau": "dim", "alpha": 0.14,
                       "y_lo": [round(s3["p25"], 4)] * n, "y_hi": [round(s3["p75"], 4)] * n})
    if s3.get("trung_vi") is not None:
        series.append({"name": "trung vị 3 năm", "y": [round(s3["trung_vi"], 4)] * n, "style": "dash", "mau": "dim"})
    series.append({"name": "%s ÷ look-through · live" % ts["me"], "y": y, "style": "line", "mau": "amber"})
    if any(v is not None for v in y_truoc):
        series.append({"name": "trước %s (cơ cấu LT khác, vẫn trong thống kê 3 năm)" % dmy(frm), "y": y_truoc,
                       "style": "dot", "mau": "dim"})
    if any(v is not None for v in y_bo):
        series.append({"name": "tuần thiếu dòng sở hữu (ngoài thống kê)", "y": y_bo, "style": "dot", "mau": "warn"})
    last_y = next((v for v in (y[-1], y_bo[-1], y_truoc[-1]) if v is not None), rows[-1]["r"])
    ann = [M.point(M.parse_day(x[-1]), last_y,
                   "hiện tại %s" % ts["txt"]["hien_tai"], "%s · phân vị 3 năm %s" % (M.ddmm(c.data_to),
                                                                                     ts["txt"]["phan_vi_3y"]),
                   "amber", "right", 1, "diamond")]
    for ny in as_list(ts.get("niem_yet")):
        d = M.parse_day(ny.get("ngay"))
        if d and x[0] <= ny["ngay"] <= x[-1]:
            ann.append({"kind": "vline", "x": M.day_ms(d), "text": "%s niêm yết" % ny["ma"], "mau": "dim",
                        "tip": "%s vào look-through từ %s: tỷ số gãy mức tại đây" % (ny["ma"], dmy(d))})
    for key, word, mau, pos in (("max", "cao nhất", "dim", "above"), ("min", "thấp nhất", "dim", "below")):
        v, d = s3.get(key), M.parse_day(s3.get(key + "_ngay"))
        if v is not None and d and x[0] <= d.isoformat() <= x[-1]:     # LkChart drops points off the axis silently
            ann.append(M.point(d, v, "%s 3 năm %s" % (word, M.x_txt(v)), dmy(d), mau, pos, 3))
    cap = ("Vốn hóa %s (giá thô) ÷ Σ tỷ lệ look-through × vốn hóa giá thô của %s; tỷ lệ theo ngày hiệu lực của "
           "registry. Dải = p25–p75 của cửa sổ 3 năm (%s), trục x bắt đầu cùng cửa sổ đó.%s Tuần trước dòng sở hữu đầu "
           "tiên của một con vẽ chấm, không vào thống kê.%s" % (
               ts["me"], ", ".join(ts["con"]), ts["txt"]["cua_so_3y"],
               (" Phần trước %s (ratio_from của registry) vẽ chấm xám: cơ cấu LT khác nhưng vẫn nằm trong thống kê 3 năm."
                % dmy(frm)) if truoc else "",
               (" Vạch dọc = con niêm yết giữa chuỗi (%s): trước đó con đó không có trong LT." % ", ".join(
                   "%s %s" % (ny["ma"], dmy(ny["ngay"])) for ny in as_list(ts.get("niem_yet"))))
               if as_list(ts.get("niem_yet")) else ""))
    block = {"x": x, "series": series, "left": {"label": "×"}, "annotations": ann}
    return M.bieu_do("%s ÷ look-through theo tuần" % ts["me"], cap, "vnstore · Vietcap price-history · registry",
                     T_EST, block, 320)


def sigma_hbands(dai, suy_bien, scale=1000.0):
    out = []
    if not suy_bien:
        out.append(M.hband(dai["-2"] / scale, dai["-1"] / scale, "RẺ −2σ…−1σ", "bull", 0.08))
    out.append(M.hband(dai["+1"] / scale, dai["+2"] / scale, "ĐẮT +1σ…+2σ", "bear", 0.08))
    return out


def chart_price_sigma(c):
    me = c.me
    if not me or me not in c.lv.ser:
        return None
    ws = [w for w in c.lv.ser[me]["w"] if w["fri"] >= M.friday(c.lv.rebase_from)]
    if not ws:
        return None
    x = [w["last"].isoformat() for w in ws]
    y = [round(w["close"] / 1000.0, 3) for w in ws]
    series = [{"name": "%s · đóng cửa tuần" % me, "y": y, "style": "line", "mau": "amber"}]
    sg = as_dict(c.tv.get(me)).get("sigma")
    ann = []
    note = c.lv.sigma_ly_do or "chưa có μ/σ của engine HHP cho %s" % me
    if sg:
        ann = sigma_hbands(sg["dai"], sg["suy_bien"])
        series.append({"name": "μ (%s)" % ("P/B" if sg["metric"] == "pb" else "P/E"),
                       "y": [round(sg["dai"]["0"] / 1000.0, 3)] * len(x), "style": "dash", "mau": "dim"})
        note = ("dải = %s × (μ ± kσ) của engine HHP (μ %s · σ %s · cơ sở %s), tính cho điểm cuối; đường giá là giá điều "
                "chỉnh nên các mốc xa có thể lệch%s" % ("BVPS" if sg["metric"] == "pb" else "EPS", M.fmt_vn(sg["mu"]),
                                                        M.fmt_vn(sg["sd"]), M.fmt_vn(sg["base"], 0),
                                                        "; −2σ ≤ 0 nên chỉ vẽ phía đắt" if sg["suy_bien"] else ""))
    ann.append(M.point(ws[-1]["last"], y[-1], "%s %s" % (me, M.k_txt(ws[-1]["close"], 1)),
                       "%s · %s" % (M.ddmm(ws[-1]["last"]), M.sigma_txt(sg["z"]) if sg else CAN), "amber", "right", 1,
                       "diamond"))
    block = {"x": x, "series": series, "left": {"label": "nghìn đồng (giá điều chỉnh)"}, "annotations": ann}
    return M.bieu_do("%s theo tuần và dải σ" % me, "Đóng cửa tuần từ %s; %s." % (dmy(c.lv.rebase_from), note),
                     "vnstore · %s" % M.SRC_HHP, T_EST if sg else T_DATA, block, 300)


def chart_pb(c):
    v = c.js.get("dinh_gia_co_so")
    if not v or not v.get("sd"):
        return None
    pts = [(M.parse_day(r["d"]), r["ratio"]) for r in as_list(v.get("tuan")) if r.get("ratio") is not None]
    if not pts:
        return None
    x = [d.isoformat() for d, _ in pts]
    n = len(x)
    mu, sd = v["mu"], v["sd"]
    metric = "P/B" if v["metric"] == "pb" else "P/E"
    series = []
    if mu - 2 * sd > 0:
        series += [{"name": "RẺ SÂU < −2σ", "style": "band", "mau": "bull", "alpha": 0.16, "lo_min": True,
                    "y_lo": [None] * n, "y_hi": [round(mu - 2 * sd, 4)] * n},
                   {"name": "RẺ −2σ…−1σ", "style": "band", "mau": "bull", "alpha": 0.08,
                    "y_lo": [round(mu - 2 * sd, 4)] * n, "y_hi": [round(mu - sd, 4)] * n}]
    series += [{"name": "ĐẮT +1σ…+2σ", "style": "band", "mau": "bear", "alpha": 0.08,
                "y_lo": [round(mu + sd, 4)] * n, "y_hi": [round(mu + 2 * sd, 4)] * n},
               {"name": "ĐẮT SÂU > +2σ", "style": "band", "mau": "bear", "alpha": 0.16, "hi_max": True,
                "y_lo": [round(mu + 2 * sd, 4)] * n, "y_hi": [None] * n},
               {"name": "%s %s" % (metric, v["ma"]), "y": [round(r, 4) for _, r in pts], "style": "line",
                "mau": "amber"}]
    last = pts[-1]
    ann = [M.point(last[0], last[1], "%s %s · %s" % (metric, M.x_txt(last[1]), M.sigma_txt((last[1] - mu) / sd)),
                   M.ddmm(last[0]), "amber", "right", 1, "diamond")]
    who = v["ma"] if v["ma"] == c.me else "%s (mã vốn hóa lớn nhất)" % v["ma"]
    block = {"x": x, "series": series, "left": {"label": "%s (×)" % metric}, "annotations": ann}
    return M.bieu_do("%s · %s theo tuần và dải σ" % (who, metric),
                     "Chuỗi tuần của engine HHP (hhp_vn100_series/%s); dải theo μ %s · σ %s%s." % (
                         v["ma"], M.fmt_vn(mu), M.fmt_vn(sd), "" if mu - 2 * sd > 0 else "; −2σ ≤ 0 nên bỏ phía rẻ"),
                     M.SRC_HHP, T_EST, block, 300)


def chart_kl(c):
    k = c.js.get("kl_co_so")
    rows = [r for r in as_list(as_dict(k).get("tuan")) if r.get("ty_le") is not None]
    if not rows:
        return None
    x = [r["fri"] for r in rows]
    y = [round(r["ty_le"], 3) for r in rows]
    y_open = [None] * len(x)
    mo = as_dict(k.get("mo"))
    if mo.get("ty_le") is not None:
        x.append(c.data_to.isoformat())
        y.append(None)
        y_open.append(round(mo["ty_le"], 3))
    x = _x_clip(x, c.data_to)
    series = [{"name": "KL tuần ÷ TB20", "y": y, "style": "bar", "mau": "info", "alpha": 0.8}]
    if any(v is not None for v in y_open):
        series.append({"name": "tuần đang mở (%s phiên)" % mo.get("so_phien"), "y": y_open, "style": "bar",
                       "mau": "amber", "alpha": 0.5})
    ann = [M.point(M.parse_day(rows[-1]["fri"]), y[len(rows) - 1], "tuần %s: %s" % (
        M.ddmm(M.parse_day(rows[-1]["fri"])), M.x_txt(rows[-1]["ty_le"])), "", "amber", "above", 1)]
    muc = [M.finite(r.get("muc")) for r in as_list(c.dossier.get("tin_hieu"))
           if isinstance(r, dict) and nfc(r.get("bien")) == "kl_tuan_tb20" and M.finite(r.get("muc"))]
    if muc:
        top = max([v for v in y + y_open if v is not None] + [muc[0] * 1.3])
        ann.append(M.hband(muc[0], top * 1.05, "ngưỡng hồ sơ %s" % M.x_txt(muc[0]), "bull", 0.08))
    block = {"x": x, "series": series, "left": {"label": "×", "min": 0}, "annotations": ann}
    return M.bieu_do("KL tuần ÷ TB 20 tuần trước · %s" % k["ma"],
                     "Tổng khối lượng các phiên trong tuần ÷ trung bình 20 tuần đã đóng trước đó; cột cam = tuần đang "
                     "mở.", M.SRC_STORE, T_DATA, block, 280)


def chart_corr(c):
    tq = c.js.get("tuong_quan")
    ma = as_dict(as_dict(tq).get("ma"))
    if not ma:
        return None
    pick = [s for s in c.lv.lt_set if s in ma] + sorted(
        [s for s in ma if s not in c.lv.lt_set], key=lambda s: -(as_dict(c.tv.get(s)).get("mcap") or 0))
    pick = pick[:MAX_CORR_SERIES]
    lags = ma[pick[0]]["lag"]
    series = [{"name": s, "y": [round(r, 3) if r is not None else None for r in ma[s]["r"]]} for s in pick]
    ng = ma[pick[0]].get("nguong")
    block = {"loai": "cot", "huong": "doc", "nhan": [M.fmt_vn(k, 0, sign=True) for k in lags], "series": series,
             "truc": {"label": "r", "min": -1, "max": 1}}
    if ng:
        z = M.fmt_vn(L.CORR_Z, 1)
        block["vach"] = [{"v": round(ng, 3), "text": "+%s/√n" % z, "mau": "xam"},
                         {"v": round(-ng, 3), "text": "−%s/√n" % z, "mau": "xam"}]
    return M.bieu_do("Tương quan lợi suất tuần với %s theo độ trễ" % tq["co_so"],
                     "%s. %s" % (nfc(tq.get("quy_uoc")), nfc(tq.get("ghi_chu"))), "vnstore · Vietcap price-history", T_EST,
                     block, 280)


# ── group page ───────────────────────────────────────────────────────────────


class Trang:
    """One group page: dossier + council + library + LiveNhom → vnblocks sections, meta, csv."""

    def __init__(self, nh, reg, root, den, warnings, lv=None, dossier=None, dpath=None, dday=None):
        self.nh, self.reg, self.root, self.den = nh, reg, root, den
        self.warnings = warnings
        if dossier is None:
            dossier, dpath, dday = load_dossier(root, nh.id, warnings, den)
        self.dossier, self.dpath, self.dday = dossier or {}, dpath, dday
        if not self.dossier and not is_msn(nh):
            add_warning(warnings, "Nhóm %s chưa có hồ sơ %s (%s): các mục hồ sơ bị bỏ, còn khối LIVE." % (
                nh.id, SCHEMA_HO_SO, os.path.join(root, nh.id)))
        self.hd, self.hpath, self.hday = load_hoi_dong(root, nh.id, warnings, den)
        if nh.get("hoi_dong") and not self.hd:
            add_warning(warnings, "Nhóm %s thuộc 14 nhóm có Hội đồng nhưng chưa có hoi_dong_*.json." % nh.id)
        self.lib, self.kpath = K.load_khung(root, warnings)
        self.lv = lv if lv is not None else L.build_live(nh, den=den, dossier=self.dossier, warnings=warnings)
        self.js = self.lv.to_json()
        self.tv_list = as_list(self.js.get("thanh_vien"))
        self.tv = {m["ma"]: m for m in self.tv_list if m.get("ma")}
        self.me, self.base, self.data_to = self.lv.me, self.lv.base, self.lv.data_to
        self.csv = []
        self.nhan_ho_so = "hồ sơ %s %s" % (nh.id, dmy(self.dday)) if self.dday else "hồ sơ %s" % nh.id

    # ── dossier access ──

    def part(self, key):
        """A dossier part (list), with the "missing part" warning when the dossier exists."""
        v = self.dossier.get(key)
        if isinstance(v, dict) and key == "keynotes":
            v = v.get("muc")
        if key not in self.dossier and self.dossier:          # present but empty = the curator found none
            add_warning(self.warnings, "Hồ sơ %s thiếu phần \"%s\", bỏ phần đó." % (self.nh.id, key))
        return [x for x in as_list(v) if x not in (None, "", {}, [])]

    # ── sections ──

    def s_cong(self):
        cg = as_dict(self.dossier.get("cong"))
        dong = nfc(cg.get("dong")) or CONG_MAC_DINH
        if nfc(cg.get("dong")) and "DỪNG" not in dong:
            add_warning(self.warnings, "Dòng CỔNG của hồ sơ %s không ghi v1.7 DỪNG; hiển thị nguyên văn." % self.nh.id)
        chu = nfc(cg.get("chu_the"))
        meta_line = "LIVE: dữ liệu đến %s · tạo lúc %s · trục thời gian %s · %s" % (
            dmy(self.data_to) or CAN, datetime.now(M.ICT).strftime("%H:%M %d/%m"), self.base or CAN,
            ("hồ sơ %s" % dmy(self.dday)) if self.dday else "chưa có hồ sơ")
        khoi = [{"kieu": "cong", "dong": dong, "tier": nfc(cg.get("tier")) or T_EST,
                 "phu": ("Cổng của hồ sơ %s, không tự tính lại" % dmy(self.dday)) if nfc(cg.get("dong")) else
                 "Mặc định: chưa có dòng CỔNG trong hồ sơ; CỔNG v1.7 đang DỪNG"},
                doan("Chủ thể (%s): %s%s" % (cut(self.nh.get("chu_the"), 60) or "?", chu,
                                           (" · " + nfc(cg.get("chu_the_ly_do"))) if nfc(cg.get("chu_the_ly_do")) else
                                           "")) if chu else None,
                doan(meta_line, mau="lam")]
        tieu = nfc(self.dossier.get("tieu_de")) or "Hồ sơ độ trễ %s" % (nfc(self.nh.get("ten")) or self.nh.id)
        return M.sec("cong", tieu, khoi, eyebrow=" · ".join(x for x in (
            "Chaebol Reflex", nfc(self.nh.get("truc")), cut(nfc(self.nh.get("chu_the")) or nfc(self.nh.get("ten")), 60))
            if x),
            lede=self.dossier.get("phu_de") or "")

    def ratio_tiles(self):
        ts, lt = self.js.get("ty_so"), self.js.get("lt")
        if not ts:
            return []
        st = ts["thong_ke"]
        s3, sf = st["3y"], st["toan_dai"]
        ar = s3["ar1"]
        t = ts["txt"]
        pv = ("cao hơn %s số tuần · %s" % (t["phan_vi_3y_so"], t["cua_so_3y"])) if s3.get("du_mau") else \
            t["phan_vi_3y"]
        return [
            tile("%s ÷ look-through" % ts["me"], t["hien_tai"], "vốn hóa %s %s · LT %s · %s" % (
                ts["me"], t["mcap_me"], t["lt"], dmy(ts["ngay"])), tier=T_EST, live=True),
            tile("Phân vị 3 năm", t["phan_vi_3y_so"], "%s · toàn dải %s" % (pv, t["phan_vi_toan_dai"]), tier=T_EST,
                 live=True),
            tile("Trung vị 3 năm", t["trung_vi_3y"], "p25–p75 %s–%s · %s · toàn dải %s" % (
                M.x_txt(s3["p25"]), M.x_txt(s3["p75"]), t["cua_so_3y"], t["trung_vi_toan_dai"]), tier=T_EST,
                 live=True),
            tile("Look-through", lt["txt"]["gia_tri"] if lt else CAN, lt["txt"]["thanh_phan"] if lt else "",
                 tier=T_EST, live=True),
            tile("Nửa đời AR(1) · 3 năm", t["nua_doi_3y"], "b %s · t %s · neo %s · n %d%s" % (
                M.fmt_vn(ar["b"], 3), M.fmt_vn(ar["t"], 2), t["neo_3y"], ar["n"],
                (" · " + ar["ghi_chu"]) if ar.get("ghi_chu") else ""), tier=T_EST, live=True),
            tile("Thấp nhất · cao nhất 3 năm", "%s · %s" % (M.x_txt(s3["min"]), M.x_txt(s3["max"])), "%s · %s · %s" % (
                dmy(s3["min_ngay"]), dmy(s3["max_ngay"]), t["cua_so_3y"]), tier=T_EST, live=True)]

    def raw_member(self, m):
        """The registry row of a member of to_json()["thanh_vien"] (by ticker, else by name for unlisted ones)."""
        if m.get("ma"):
            return as_dict(self.nh.member(m["ma"]))
        ten = nfc(m.get("ten"))
        return next((raw for ma, raw in self.nh.members if not ma and nfc(raw.get("ten")) == ten), {})

    def stake_txt(self, m, raw):
        """("pháp lý · hiệu dụng", "as-of · bậc [· chờ CBTT …]") of one member. A member without a ticker is not
        scheduled by the engine; its registry rows are read for display only, with the engine's row checks."""
        pl, hd, sh = m.get("so_huu_phap_ly"), m.get("so_huu_hieu_dung"), m.get("so_huu")
        cho = as_list(m.get("so_huu_cho"))
        if not m.get("ma"):
            lich = L.parse_stake_rows(self.nh.id, None, raw.get("so_huu"), [])
            pl, hd, cho = (lich["phap_ly"] or [None])[0], (lich["hieu_dung"] or [None])[0], lich["cho"]
            sh = hd or pl
        asof = ("%s · %s" % (dmy(sh["tu"]), nfc(sh["tier"]))) if sh else "–"
        if cho:
            asof += " · chờ CBTT: " + "; ".join("%s từ %s" % (M.share_txt(r["ty_le"]), dmy(r["tu"])) for r in cho)
        return "%s · %s" % (M.share_txt((pl or {}).get("ty_le")), M.share_txt((hd or {}).get("ty_le"))), asof

    def member_rows(self):
        """(rows of the listed members with prices, rows of the members without prices on this machine)."""
        rows, khong_gia = [], []
        for m in self.tv_list:
            ma = m.get("ma")
            vai = nfc(m.get("vai_tro")) or "thành viên"
            raw = self.raw_member(m)
            ty_le, asof = self.stake_txt(m, raw)
            if not m.get("co_gia"):
                ten = ("%s · %s" % (ma, m.get("ten"))) if (ma and m.get("ten")) else (ma or m.get("ten") or "?")
                note = nfc(raw.get("ghi_chu")) or nfc(m.get("ly_do_loai"))
                khong_gia.append([cell(ten, dam=True, tip=m.get("ly_do_loai")),
                                  cell(" · ".join(x for x in (vai, nfc(m.get("niem_yet")) or (
                                      "không có giá trên máy" if ma else "")) if x)),
                                  cell(nfc(m.get("me")) or "–", mono=bool(L.ticker(m.get("me")))),
                                  cell(ty_le, mono=True), cell(asof, mono=True),
                                  K.nguon_cell(note, GHI_CHU_CUT) if note else "–"])
                continue
            if ma and ma != self.me:
                vai += " · trong LT" if m.get("trong_lt_dung") else " · ngoài LT"
            ls = as_dict(m.get("loi_suat"))
            sg = as_dict(m.get("sigma"))
            rows.append([
                cell(("%s · %s" % (ma, m.get("ten"))) if (ma and m.get("ten")) else (ma or m.get("ten") or "?"), dam=True,
                     tip=m.get("ly_do_loai")),
                cell(vai, tip=m.get("ly_do_loai")), cell(ty_le, mono=True), cell(asof, mono=True),
                cell(M.nghin_ty(m.get("mcap")), mono=True),
                cell(M.nghin_ty(m.get("phan_nam")) if m.get("phan_nam") is not None else "–", mono=True),
                cell(m["txt"]["r_1t"], mono=True, mau=pct_mau(ls.get("r_1t"))),
                cell(m["txt"]["r_13t"], mono=True, mau=pct_mau(ls.get("r_13t"))),
                cell(m["txt"]["r_ytd"], mono=True, mau=pct_mau(ls.get("r_ytd"))),
                cell(("%s %s" % (m["txt"]["sigma"], "P/B" if sg.get("metric") == "pb" else "P/E")) if sg else "–",
                     mono=True)])
            if ma:
                self.csv.append(["Thành viên", ma, M.nghin_ty(m.get("mcap")), dmy(self.data_to), "LIVE", T_DATA,
                                 "sở hữu %s · %% 13T %s · σ %s" % (m["txt"]["so_huu"], m["txt"]["r_13t"],
                                                                   m["txt"]["sigma"])])
        return rows, khong_gia

    def tang_rows(self):
        out = []
        for t in as_list(self.js.get("tang")):
            out.append([cell("%s ÷ LT tầng" % t["me"], dam=True), ", ".join(t["con"]),
                        cell(t["txt"]["hien_tai"], mono=True),
                        cell("3 năm %s · toàn dải %s" % (t["txt"]["phan_vi_3y"], t["txt"]["phan_vi_toan_dai"]),
                             mono=True),
                        cell(t["txt"]["trung_vi_3y"], mono=True), cell(t["txt"]["nua_doi_3y"], mono=True)])
        return out

    def s_he_sinh_thai(self):
        tiles = self.ratio_tiles()
        for t in tiles:
            self.csv.append(["Hệ sinh thái", t["nhan"], t["gia_tri"], dmy(self.data_to), "LIVE", t["tier"], t["phu"]])
        khoi = [M.o_so(tiles, cot=3)]
        if not self.me:
            khoi.append(doan("Nhóm không có mẹ niêm yết có giá: không có tỷ số mẹ ÷ look-through. Trục thời gian, quy "
                             "về 100 và dẫn/trễ lấy %s (vốn hóa lớn nhất)." % self.base, mau="vang"))
        elif not self.js.get("ty_so"):
            khoi.append(doan("%s: chưa có con nào đủ điều kiện look-through (cần mã niêm yết có giá và dòng sở hữu có "
                             "tu, tier, nguon)." % CAN, mau="do"))
        rows, khong_gia = self.member_rows()
        khoi += [heading("Thành viên · LIVE %s" % dmy(self.data_to)),
                 bang(MEMBER_COLS, rows,
                      "Giá, vốn hóa (giá thô), % thay đổi: FACT-T2 (vnstore, Vietcap). Phần mẹ nắm = tỷ lệ look-through "
                      "× vốn hóa, σ của engine HHP: EST. Tỷ lệ sở hữu mang bậc và ngày của dòng registry.",
                      can_phai=[4, 5, 6, 7, 8, 9])]
        if khong_gia:
            khoi += [heading("%s · %d" % (TEN_KHONG_GIA, len(khong_gia))),
                     bang(KHONG_GIA_COLS, khong_gia, "Ghi nhận theo registry, không vào look-through và biểu đồ. Tỷ lệ "
                                                     "mang bậc và ngày của dòng registry; ghi chú cắt %d ký tự, bản đủ "
                                                     "ở chú thích ô." % GHI_CHU_CUT)]
        if self.tang_rows():
            khoi += [heading("Tầng holdco trung gian"),
                     bang(["Tầng", "Con tính vào", "Tỷ số hiện tại", "Phân vị 3 năm · toàn dải", "Trung vị 3 năm",
                           "Nửa đời AR(1)"], self.tang_rows(), "EST · tỷ lệ pháp lý của tầng, vốn hóa giá thô.",
                          can_phai=[2, 3, 4, 5])]
        khoi += [chart_rebased(self), chart_ratio(self)]
        return M.sec("he_sinh_thai", "Hệ sinh thái %s" % (nfc(self.nh.get("ten")) or self.nh.id), khoi,
                     eyebrow="Look-through · LIVE",
                     lede="Tính lại từ kho dữ liệu trên máy mỗi lần mở tab hoặc bấm FETCH. Tỷ lệ sở hữu theo registry, "
                          "đổi theo ngày hiệu lực; trước dòng đầu tiên con không vào look-through.")

    def signal_rows(self):
        prof = [r for r in as_list(self.dossier.get("tin_hieu")) if isinstance(r, dict)]
        rows = []
        for r, s in zip(prof, as_list(self.js.get("tin_hieu"))):
            ng = nfc(r.get("nguong_text")) or ("%s %s" % (r.get("phep"), M.fmt_vn(r.get("muc"))) if r.get("phep") else "")
            if s.get("live"):
                val = cell(s["gia_tri_txt"], mono=True)
                st = M.pill(s["trang_thai"], SIGNAL_MAU.get(s["trang_thai"], "vang"))
                note = "%s · %s" % (s.get("tier") or "", s.get("ghi_chu") or "")
            else:
                val = cell("nguyên văn · %s" % (s.get("as_of") or dmy(self.dday) or "?"), mono=True)
                st = M.pill("theo hồ sơ", "xam")
                note = src_cell(" · ".join(x for x in (tier_of(r), src_txt(r), s.get("ghi_chu")) if x))
            rows.append([cell(nfc(r.get("id")), dam=True), nfc(r.get("mo_ta")), cell(ng, mono=True), val, st, note])
            self.csv.append(["Tín hiệu", "%s · %s" % (nfc(r.get("id")), cut(r.get("mo_ta"), 80)),
                             s.get("gia_tri_txt") or CAN, s.get("as_of") or "", s.get("trang_thai") or "nguyên văn",
                             s.get("tier") or tier_of(r), cut(s.get("ghi_chu"), 120)])
        return rows

    def log_rows(self):
        lv, base = self.lv, self.base
        ws = lv.ser[base]["w"]
        comp, op = lv.complete(ws), lv.open_week(ws)
        weeks = comp[-LOG_WEEKS:] + ([op] if op else [])
        idx = {w["fri"]: i for i, w in enumerate(ws)}
        kl = as_dict(self.js.get("kl_co_so"))
        kl_by = {r["fri"]: r["ty_le"] for r in as_list(kl.get("tuan"))}
        ts = self.js.get("ty_so")
        r_by = {r["fri"]: r for r in as_list((ts or {}).get("tuan"))}
        others = [s for s in lv.lt_set if s != base] + [s for s in lv.priced if s != base and s not in lv.lt_set]
        others = others[:MAX_LOG_MA]
        by = {s: {w["fri"]: w["close"] for w in lv.ser[s]["w"]} for s in others}
        vd, vv = lv.kho.vni()
        rows = []
        for w in reversed(weeks):
            is_open = w is op
            i = idx.get(w["fri"])
            prev = ws[i - 1] if i else None
            chg = L.pct(w["close"], prev["close"]) if prev else None
            k = as_dict(kl.get("mo")).get("ty_le") if is_open else kl_by.get(iso(w["fri"]))
            if is_open:
                lt_r = (ts["lt"], ts["hien_tai"], ts["du"]) if ts else (None, None, True)
            else:
                rr = r_by.get(iso(w["fri"]))
                lt_r = (rr["lt"], rr["r"], rr["du"]) if rr else (None, None, True)
            _, vni = M.asof(vd, vv, w["last"])
            label = "%s%s" % (dmy(w["last"]), " · đang mở (%d phiên)" % w["n"] if is_open else "")
            row = [cell(label, dam=is_open), cell("%s · %s" % (M.k_txt(w["close"]), M.pct_txt(chg)), mono=True),
                   cell(M.x_txt(k), mono=True)]
            if ts:
                row.append(cell("%s · %s%s" % (M.nghin_ty(lt_r[0]), M.x_txt(lt_r[1]), "" if lt_r[2] else " *"),
                                mono=True))
            row += [cell(" · ".join("%s %s" % (s, M.k_txt(by[s].get(w["fri"]))) for s in others) or "–", mono=True),
                    cell(M.fmt_vn(vni, 2), mono=True)]
            rows.append(row)
            self.csv.append(["Nhật ký tuần", label, M.k_txt(w["close"]), dmy(w["last"]),
                             "tạm" if is_open else "đóng", T_DATA,
                             "KL ÷ TB20 %s%s" % (M.x_txt(k), (" · %s ÷ LT %s" % (self.me, M.x_txt(lt_r[1]))) if ts
                                                 else "")])
        cols = ["Tuần (phiên cuối)", "%s · ± tuần" % base, "KL ÷ TB20"] + (
            ["LT (nghìn tỷ) · %s ÷ LT" % self.me] if ts else []) + ["Mã khác (nghìn đồng)", "VN-Index"]
        return cols, rows

    def s_theo_doi(self):
        khoi = []
        sig = self.signal_rows()
        if sig:
            khoi += [heading("Tín hiệu của hồ sơ · chấm LIVE khi có biến, phép và mức"),
                     bang(["#", "Tín hiệu", "Ngưỡng", "Giá trị gần nhất", "Trạng thái", "Nhãn · nguồn · ghi chú"], sig,
                          "Tín hiệu có bien/phep/muc được chấm lại theo dữ liệu; còn lại hiện nguyên văn kèm ngày. "
                          "Đây là trạng thái ngưỡng của hồ sơ, không phải lệnh.")]
        else:
            khoi.append(doan("%s: hồ sơ chưa có tín hiệu có ngưỡng; nhật ký tuần chỉ có số đo." % CAN, mau="xam"))
        cols, rows = self.log_rows()
        khoi += [heading("Nhật ký %d tuần · mới nhất ở trên · tính lại từ dữ liệu" % LOG_WEEKS),
                 bang(cols, rows, "%s · Đóng cửa tuần = phiên cuối tuần (giá điều chỉnh), KL, VN-Index: FACT-T2; LT và "
                                  "tỷ số mẹ ÷ LT: EST. * = tuần thiếu dòng sở hữu của một con (không vào thống kê tỷ "
                                  "số)." % LOG_TIER, can_phai=list(range(1, len(cols)))),
                 chart_kl(self)]
        return M.sec("theo_doi_tuan", "%s tuần này" % (nfc(self.nh.get("ten")) or self.nh.id), khoi,
                     eyebrow="Theo dõi tuần · LIVE",
                     lede="Tuần là thứ Hai–thứ Sáu, gắn nhãn thứ Sáu; tuần có ngày thứ Sáu sau phiên dữ liệu cuối là "
                          "tuần đang mở.")

    def s_keynotes(self):
        muc = [{"so": nfc(m.get("id")) or str(i + 1), "tieu_de": nfc(m.get("tieu_de")),
                  "text": nfc(m.get("noi_dung")) + (("\nNguồn: " + src_txt(m)) if src_txt(m) else ""),
                  "tags": M.tier_list(m.get("tier"))}
                 for i, m in enumerate(items(self.part("keynotes"), "noi_dung"))]
        if not muc:
            return None
        return M.sec("keynotes", "Keynotes", [M.danh_sach(muc)], eyebrow="Keynotes · %s" % self.nhan_ho_so)

    def capture_live_rows(self):
        caps = sorted([c for c in as_list(self.js.get("capture")) if c.get("capture") is not None],
                      key=lambda c: c["tu"], reverse=True)[:MAX_CAPTURE_ROWS]
        return [[cell("%s ← %s%s" % (c["me"], c["con"], " (tầng)" if c.get("tang") else ""), dam=True),
                 cell("%s → %s%s" % (dmy(c["tu"]), dmy(c["den"]), "" if c.get("xac_nhan") else " · chân mở"), mono=True),
                 cell(M.pct_txt(c["r_con"]), mono=True), cell(M.pct_txt(c["r_me"]), mono=True),
                 cell(M.share_txt(c["w"]), mono=True), cell(M.fmt_vn(c["capture"], 2, fixed=True), mono=True, dam=True)]
                for c in caps]

    def window_of(self, row):
        """A dossier capture window → (tu, den): explicit tu/den, "2025" / "năm 2025", or "MM/YYYY → MM/YYYY"; the
        end is capped at the group's data day when there is one."""
        tu, den = M.parse_day(row.get("tu")), M.parse_day(row.get("den"))
        if tu and den:
            return tu, den

        def cap(x):
            return min(x, self.data_to) if self.data_to else x
        cs = nfc(row.get("cua_so"))
        m = re.fullmatch(r"(?:năm\s*)?(\d{4})", cs, re.IGNORECASE)
        if m:
            y = int(m.group(1))
            return date(y - 1, 12, 31), cap(date(y, 12, 31))
        m = re.fullmatch(r"(\d{1,2})/(\d{4})\s*(?:→|->|–|-)\s*(\d{1,2})/(\d{4})", cs)
        if m:
            a = date(int(m.group(2)), int(m.group(1)), 1)
            b = date(int(m.group(4)), int(m.group(3)), 1)
            b = (b.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            return a, cap(b)
        return None, None

    def capture_frozen_rows(self, rows):
        out = []
        for r in rows:
            r = as_dict(r)
            pair = [L.ticker(x) for x in re.split(r"\s*(?:←|<-|<)\s*", nfc(r.get("cap")))]
            live = CAN
            if len(pair) == 2 and all(p in self.lv.ser for p in pair):    # priced pair first: no window without data
                tu, den = self.window_of(r)
                if tu and den:
                    v = self.lv.capture_cua_so(pair[0], pair[1], tu, den)
                    live = M.fmt_vn(v["capture"], 2, fixed=True) if v["capture"] is not None else "%s (%s)" % (
                        CAN, v["ly_do"])
            out.append([cell(nfc(r.get("cap")), dam=True), cell(nfc(r.get("cua_so")), mono=True),
                        cell(txt(r.get("gia_tri")), mono=True), cell(live, mono=True), src_cell(src_txt(r)),
                        nhan_cell(r)])
        return out

    def s_truyen_dan(self):
        cc = items(self.part("co_che_truyen_dan"), "text")
        live = self.capture_live_rows()
        frozen = items(self.part("capture_dong_bang"), "cap")
        if not (cc or live or frozen):
            add_warning(self.warnings, "Nhóm %s: không có cơ chế truyền dẫn trong hồ sơ và chưa có chân con ≥ 30%% đo "
                                       "được capture, bỏ mục truyền dẫn." % self.nh.id)
            return None
        khoi = []
        if cc:
            khoi += [heading("Cơ chế truyền dẫn · %s" % self.nhan_ho_so),
                     M.danh_sach([{"so": str(i + 1), "text": txt(x.get("text")) + (
                         ("\nNguồn: " + src_txt(x)) if src_txt(x) else ""), "tags": M.tier_list(x.get("tier"))}
                                  for i, x in enumerate(cc)])]
        if live:
            khoi += [heading("Capture LIVE trên các chân zigzag 30% của con"),
                     bang(["Cặp mẹ ← con", "Chân của con", "Con", "Mẹ", "Tỷ lệ đầu chân", "Capture"], live,
                          "EST · Capture = (vốn hóa mẹ đầu chân × %% giá mẹ) ÷ (tỷ lệ × vốn hóa con đầu chân × %% giá con). "
                          "1 = mẹ bắt trọn, < 1 rò rỉ, > 1 mẹ đi vì lý do khác. %d chân gần nhất." % len(live),
                          can_phai=[2, 3, 4, 5])]
        if frozen:
            khoi += [heading("Capture của nguồn · %s" % DB),
                     bang(["Cặp", "Cửa sổ", "Giá trị của nguồn", "Tính lại LIVE (EST)", "Nguồn · ngày", "Nhãn"],
                          self.capture_frozen_rows(frozen),
                          "%s · số của nguồn giữ nguyên; cột LIVE tính lại cùng cửa sổ khi đọc được ngày." % DB,
                          can_phai=[2, 3])]
        return M.sec("truyen_dan", "Truyền dẫn con → mẹ", khoi, eyebrow="Cơ chế · capture · LIVE + %s" % DB)

    def lead_lag_blocks(self):
        js = self.js
        khoi = []
        bp, dn = as_dict(js.get("bung_pha")), as_dict(js.get("dinh"))
        rows = []
        for s in self.lv.priced:
            b = (as_list(bp.get(s)) or [None])[-1]
            p = (as_list(dn.get(s)) or [None])[-1]
            rows.append([cell(s, dam=s in (self.me, self.base)),
                         cell(("%s · %s%s" % (dmy(b["day"]), M.k_txt(b["gia_day"]), "" if b["xac_nhan_day"] else
                                              " (chưa xác nhận)")) if b else "–", mono=True),
                         cell(("%s · %s" % (dmy(b["bung_pha"]), M.k_txt(b["gia"]))) if (b and b["bung_pha"]) else
                              "chưa có", mono=True),
                         cell(str(b["so_phien"]) if (b and b["so_phien"] is not None) else "–", mono=True),
                         cell(("%s · %s%s" % (dmy(p["ngay"]), M.k_txt(p["gia"]), "" if p["xac_nhan"] else " (đang mở)"))
                              if p else "–", mono=True)])
        khoi += [heading("Đáy, bứt phá 250 phiên và đỉnh gần nhất của từng mã"),
                 bang(["Mã", "Đáy zigzag 30%", "Bứt phá 250 phiên", "Số phiên từ đáy", "Đỉnh zigzag 30%"], rows,
                      "Bứt phá = phiên đầu tiên đóng cửa trên mức cao nhất 250 phiên trước đó, tính sau đáy. FACT-T2 giá; "
                      "zigzag là phép đo EST.", can_phai=[3])]
        dt = as_dict(js.get("dan_tre"))
        cyc = list(reversed(as_list(dt.get("chu_ky"))))[:MAX_CYCLES]
        crow = []
        for cy in cyc:
            name = "%s → %s%s" % (dmy(cy["tu"]), dmy(cy["den"]), (" · đáy VN-Index %s" % dmy(cy["vni_day"]))
                                  if cy.get("vni_day") else " · cửa sổ 2 năm")
            for s, v in as_dict(cy.get("ma")).items():
                if not (v.get("bung_pha") or v.get("dinh")):
                    continue
                crow.append([cell(name, mono=True), cell(s, dam=s == dt.get("co_so")),
                             cell(mo_txt(dmy(v.get("bung_pha")), v.get("bung_pha") and v.get("bung_pha_xac_nhan") is
                                         False), mono=True),
                             cell(mo_txt(M.fmt_vn(v["lech_bung_pha"], 0, sign=True), v.get("lech_bung_pha_mo"))
                                  if v.get("lech_bung_pha") is not None else "–", mono=True),
                             cell(mo_txt(dmy(v.get("dinh")), v.get("dinh") and v.get("dinh_xac_nhan") is False),
                                  mono=True),
                             cell(mo_txt(M.fmt_vn(v["lech_dinh"], 0, sign=True), v.get("lech_dinh_mo"))
                                  if v.get("lech_dinh") is not None else "–", mono=True)])
        if crow:
            khoi += [heading("Dẫn/trễ trong từng chu kỳ · so với %s" % dt.get("co_so")),
                     bang(["Chu kỳ", "Mã", "Bứt phá", "Lệch (ngày)", "Đỉnh cao nhất", "Lệch đỉnh (ngày)"], crow,
                          "EST · %s" % nfc(dt.get("ghi_chu")), can_phai=[3, 5])]
        tq = as_dict(js.get("tuong_quan"))
        trow = []
        for s, v in as_dict(tq.get("ma")).items():
            r0 = v["r"][v["lag"].index(0)] if 0 in v["lag"] else None
            trow.append([cell(s, dam=True), cell(M.fmt_vn(r0, 2, fixed=True), mono=True),
                         cell(M.fmt_vn(v["best_lag"], 0, sign=True) if v["best_lag"] is not None else "–", mono=True),
                         cell(M.fmt_vn(v["best_r"], 2, fixed=True), mono=True),
                         cell(M.fmt_vn(v["nguong"], 2, fixed=True), mono=True),
                         M.pill("vượt ngưỡng, chưa phải quy luật khai thác được" if v["co_y_nghia"] else
                                "dưới ngưỡng, không có quy luật dẫn/trễ", "lam" if v["co_y_nghia"] else "xam")])
        if trow:
            khoi += [heading("Tương quan lợi suất tuần theo độ trễ · %d tuần" % (tq.get("so_tuan") or 0)),
                     bang(["Mã", "r (cùng tuần)", "Độ trễ có |r| lớn nhất", "r",
                           "Ngưỡng %s/√n (Bonferroni %d độ trễ)" % (M.fmt_vn(L.CORR_Z, 1), 2 * L.CORR_LAGS + 1), "Đọc"],
                          trow,
                          "EST · %s. %s" % (nfc(tq.get("quy_uoc")), nfc(tq.get("ghi_chu"))), can_phai=[1, 2, 3, 4]),
                     chart_corr(self)]
        return khoi

    def s_do_tre(self):
        khoi = self.lead_lag_blocks()
        obs = items(self.part("do_tre_quan_sat"), "mo_ta")
        if obs:
            khoi += [heading("Độ trễ đã quan sát · %s" % DB),
                     bang(["Cặp", "Quan sát", "Số", "Nguồn · ngày", "Nhãn"],
                          [[cell(txt(as_dict(o).get("cap")), dam=True), txt(as_dict(o).get("mo_ta")),
                            cell(txt(as_dict(o).get("so")), mono=True), src_cell(src_txt(o)), nhan_cell(o)] for o in obs],
                          "%s · quan sát của nguồn theo ngày lập, không chấm lại." % DB)]
        return M.sec("do_tre", "Độ trễ mẹ–con", khoi, eyebrow="Bứt phá · đỉnh · tương quan trễ · LIVE")

    def s_dot_tang(self):
        rows = self.part("dot_tang_lich_su")
        if not rows:
            return None
        return M.sec("dot_tang", "Các đợt tăng lịch sử", [bang(
            ["Đợt", "Từ → đến", "Biên độ", "Dẫn đầu", "Chất xúc tác", "Nguồn", "Nhãn"],
            [[cell(txt(r.get("ten")), dam=True), cell("%s → %s" % (txt(r.get("tu")), txt(r.get("den"))), mono=True),
              cell(txt(r.get("bien_do")), mono=True), txt(r.get("ai_dan_dau")), txt(r.get("chat_xuc_tac")),
              src_cell(r.get("nguon")), nhan_cell(r)] for r in items(rows, "ten")],
            "Theo %s; dòng không ghi bậc là %s." % (self.nhan_ho_so, T_UNV))],
            eyebrow="Lịch sử · %s" % self.nhan_ho_so)

    def s_khung(self):
        maps = self.dossier.get("khung_ap_dung")
        if self.dossier and not as_list(maps):
            add_warning(self.warnings, "Hồ sơ %s thiếu phần \"khung_ap_dung\", chỉ còn dấu hiệu đo được." % self.nh.id)
        return K.section_khung(self.lv, self.lib, self.nh.id, maps, self.warnings, lib_path=self.kpath if self.lib
                               else None, ho_so=self.dpath)

    def s_list(self, key, sid, title, eyebrow):
        rows = items(self.part(key), "text")
        if not rows:
            return None
        return M.sec(sid, title, [M.danh_sach([{"so": str(i + 1), "text": txt(x.get("text")) + (
            ("\nNguồn: " + src_txt(x)) if src_txt(x) else ""), "tags": M.tier_list(x.get("tier"))}
            for i, x in enumerate(rows)])], eyebrow=eyebrow)

    def s_su_kien(self):
        ev = self.part("su_kien")
        if not ev:
            return None
        ev = sorted(items(ev, "mo_ta"), key=lambda r: nfc(r.get("ngay")), reverse=True)
        return M.sec("su_kien", "Sự kiện", [bang(["Ngày", "Sự kiện", "Nhãn", "Nguồn"],
                                                 [[cell(dmy(r.get("ngay")) or txt(r.get("ngay")), mono=True),
                                                   txt(r.get("mo_ta")), M.tier_cell(tier_of(r)), src_cell(r.get("nguon"))]
                                                  for r in ev],
                                                 "%s · %s: sự kiện như nguồn ghi (có thể trích thay đổi xếp hạng của "
                                                 "nguồn), không chấm lại; mới nhất ở trên." % (DB, self.nhan_ho_so))],
                     eyebrow="Sự kiện · %s" % self.nhan_ho_so)

    def s_xuc_tac(self):
        cx = self.part("chat_xuc_tac")
        if not cx:
            return None
        return M.sec("xuc_tac", "Chất xúc tác", [bang(["#", "Chất xúc tác", "Mốc", "Trạng thái", "Ghi chú trạng thái",
                                                      "Nhãn · nguồn"], [
            [cell(txt(r.get("id")), mono=True), txt(r.get("mo_ta")), cell(txt(r.get("moc")), mono=True),
             M.pill(txt(r.get("trang_thai")) or CAN, XUC_TAC_MAU.get(txt(r.get("trang_thai")).upper(), "xam")),
             txt(r.get("trang_thai_nguon")), src_cell(" · ".join(x for x in (tier_of(r), txt(r.get("nguon"))) if x))]
            for r in items(cx, "mo_ta")],
            "Trạng thái theo hồ sơ %s, không tự chấm lại." % dmy(self.dday))], eyebrow="Chất xúc tác · %s" %
            self.nhan_ho_so)

    def sigma_rows(self):
        rows = []
        for m in self.tv_list:
            sg = m.get("sigma")
            if not sg:
                continue
            d = sg["dai"]
            eng = as_dict(sg.get("engine"))
            rows.append([cell(m["ma"], dam=m["ma"] == self.me),
                         "%s · μ %s · σ %s%s" % ("P/B" if sg["metric"] == "pb" else "P/E", M.fmt_vn(sg["mu"]),
                                                 M.fmt_vn(sg["sd"]), "" if eng.get("reliable") is not False else
                                                 " · engine: chưa tin cậy")]
                        + [cell("–" if (sg["suy_bien"] and k in ("-2", "-1")) else M.k_txt(d[k], 1), mono=True)
                           for k in ("-2", "-1", "0", "+1", "+2")]
                        + [cell("%s · %s · %s" % (M.k_txt(sg["gia"], 1), M.x_txt(sg["ratio"]), M.sigma_txt(sg["z"])),
                                mono=True, mau="lam"),
                           "engine %s%s" % (dmy(eng.get("ngay")) or "?", " · −2σ ≤ 0, chỉ chấm phía đắt" if sg["suy_bien"]
                                            else "")])
        return rows

    def s_vung_gia(self):
        rows = self.sigma_rows()
        frozen = self.part("vung_gia_dong_bang")
        charts = [chart_price_sigma(self), chart_pb(self)]
        if not (rows or frozen or any(charts)):
            add_warning(self.warnings, "Nhóm %s: engine HHP không có μ/σ cho mã nào và hồ sơ không có vùng giá, bỏ mục "
                                       "vùng giá." % self.nh.id)
            return None
        khoi = [doan("%s: %s." % (CAN, self.lv.sigma_ly_do), mau="vang")] if self.lv.sigma_ly_do else []
        if rows:
            khoi += [heading("Vị trí giá trong dải σ của chính mã (nghìn đồng tại −2σ, −1σ, μ, +1σ, +2σ) · LIVE"),
                     bang(["Mã", "Chỉ số", "−2σ", "−1σ", "μ", "+1σ", "+2σ", "Giá · chỉ số · σ", "Ghi chú"], rows,
                          "EST · μ, σ và cơ sở (BVPS/EPS) của engine HHP; giá thô phiên cuối. Vùng: RẺ SÂU · RẺ · TRUNG "
                          "TÍNH · ĐẮT · ĐẮT SÂU.", can_phai=[2, 3, 4, 5, 6])]
        if frozen:
            khoi += [heading("Vùng giá của nguồn · %s" % DB),
                     bang(["Mã", "Vùng", "Phương pháp", "Ngày", "Nguồn", "Nhãn"],
                          [[cell(txt(r.get("ma")), dam=True), cell(txt(r.get("vung")), mono=True),
                            txt(r.get("phuong_phap")), cell(dmy(r.get("ngay")) or txt(r.get("ngay")), mono=True),
                            src_cell(r.get("nguon")), nhan_cell(r)] for r in items(frozen, "vung")],
                          "%s · vùng giá của nguồn tại ngày lập, không chấm lại (CỔNG v1.7 DỪNG)." % DB)]
        khoi += charts
        return M.sec("vung_gia", "Vùng giá σ", khoi, eyebrow="σ engine HHP · LIVE + %s" % DB)

    def s_hoi_dong(self):
        hd = self.hd
        if not hd:
            return None
        nhan = "Hội đồng %s" % dmy(self.hday)

        def zone(key):
            cards = [M.card("%s · %s" % (txt(x.get("co_van")), txt(x.get("phieu"))), "%s%s" % (
                txt(x.get("lap_luan")), ("\n\nĐổi phiếu khi: " + txt(x.get("dieu_kien_doi_phieu")))
                if txt(x.get("dieu_kien_doi_phieu")) else ""), nhan=txt(x.get("phieu")),
                nhan_mau=PHIEU_MAU.get(txt(x.get("phieu")).upper(), "xam"),
                mau_vien=PHIEU_MAU.get(txt(x.get("phieu")).upper(), "xam"))
                for x in (as_dict(v) for v in as_list(hd.get(key)))]
            return M.the_block(cards, 3)
        syn = as_dict(hd.get("synthesis"))
        rig = as_dict(syn.get("rigor_6d"))
        khoi = [doan(txt(hd.get("cong")), mau="lam"),
                doan(txt(hd.get("cau_hoi")), mau="vang", the=True, tieu_de="Câu hỏi của Hội đồng"),
                heading("Kill zone"), zone("kill_zone"), heading("Alpha zone"), zone("alpha_zone"),
                heading("Synthesis"),
                doan(txt(syn.get("text")), mau="tim", the=True, tieu_de="Trạng thái %s" % (txt(syn.get("trang_thai"))
                                                                                           or CAN)),
                bang(list(rig), [[cell(M.fmt_vn(v, 1), mono=True) for v in rig.values()]],
                     "Rigor 6D của Hội đồng") if rig else None]
        pm = [as_dict(x) for x in as_list(hd.get("pre_mortem"))]
        if pm:
            khoi += [heading("Pre-mortem của Hội đồng"), M.the_block([M.card(
                txt(x.get("ten")), "%s%s" % (txt(x.get("noi_dung")), ("\n\nTín hiệu sớm: " + txt(x.get("tin_hieu_som")))
                                             if txt(x.get("tin_hieu_som")) else ""),
                nhan=txt(x.get("xac_suat")), nhan_mau="do", mau_vien="do") for x in pm], 3)]
        pt = as_list(hd.get("phep_thu"))
        if pt:
            khoi += [heading("Phép thử"), M.danh_sach([{"so": str(i + 1), "text": txt(t)} for i, t in enumerate(pt)])]
        khoi.append({"kieu": "chips", "chips": [{"tier": txt(hd.get("tier")) or T_EST, "text": nhan}]})
        return M.sec("hoi_dong", "Hội đồng · %s" % (nfc(self.nh.get("ten")) or self.nh.id), khoi,
                     eyebrow="%s · ỦNG HỘ / PHẢN BIỆN / CHỜ DỮ LIỆU · EST" % nhan,
                     lede="Phiếu của Hội đồng AI dựa trên gói dữ kiện của engine và hồ sơ; không có lệnh và không định "
                          "cỡ vị thế.")

    def s_nhan_dinh_cu(self):
        rows = self.part("nhan_dinh_cu_dong_bang")
        if not rows:
            return None
        rows = sorted(items(rows, "tom_tat"), key=lambda r: nfc(r.get("ngay")), reverse=True)
        return M.sec("nhan_dinh_cu", "Nhận định cũ · %s" % DB, [bang(
            ["Ngày", "Tác giả", "Nhận định", "Nguồn", "Nhãn"],
            [[cell(dmy(r.get("ngay")) or txt(r.get("ngay")), mono=True), cell(txt(r.get("tac_gia")) or "?", dam=True),
              src_cell("%s · %s %s: %s" % (DB, txt(r.get("tac_gia")) or txt(r.get("nguon")) or "?", dmy(r.get("ngay")),
                                           txt(r.get("tom_tat")))), src_cell(r.get("nguon")), nhan_cell(r)]
             for r in rows],
            "%s · lịch sử nhận định theo ngày và tác giả, không chấm lại (CỔNG v1.7 DỪNG)." % DB)],
            eyebrow="Lịch sử · %s" % DB)

    def s_pre_mortem(self):
        rr = items(self.part("rui_ro"), "text")
        pm = items(self.part("pre_mortem"), "noi_dung")
        if not (rr or pm):
            return None
        khoi = []
        if rr:
            khoi += [heading("Rủi ro"), M.danh_sach([{"so": str(i + 1), "text": txt(x.get("text")) + (
                ("\nNguồn: " + src_txt(x)) if src_txt(x) else "")} for i, x in enumerate(rr)])]
        if pm:
            khoi += [heading("Pre-mortem"), M.the_block([M.card(txt(x.get("ten")), "%s%s%s" % (
                txt(x.get("noi_dung")), ("\n\nTín hiệu sớm: " + txt(x.get("tin_hieu_som"))) if txt(x.get("tin_hieu_som"))
                else "", ("\n\nNguồn: " + txt(x.get("nguon"))) if txt(x.get("nguon")) else ""),
                nhan=txt(x.get("xac_suat")), nhan_mau="do", mau_vien="do") for x in pm], 3)]
        return M.sec("pre_mortem", "Rủi ro · pre-mortem", khoi, eyebrow="Pre-mortem · %s" % self.nhan_ho_so)

    def s_xung_dot(self):
        rows = []
        for x in as_list(self.nh.get("xung_dot")):
            x = as_dict(x)
            for v in as_list(x.get("gia_tri")):
                v = as_dict(v)
                rows.append([cell(txt(x.get("chu_de")), dam=True), cell(txt(v.get("v")), mono=True),
                             src_cell(v.get("nguon")), cell(dmy(v.get("ngay")) or txt(v.get("ngay")), mono=True),
                             "registry"])
        for m in self.tv_list:
            if not m.get("lech"):
                continue
            pl = m.get("so_huu_phap_ly") or {}
            rows.append([cell("%s→%s" % (m.get("me") or "?", m["ma"]), dam=True), cell(M.share_txt(pl.get("ty_le")),
                                                                                       mono=True),
                         src_cell("registry · %s" % (pl.get("nguon") or "")), cell(dmy(pl.get("tu")), mono=True),
                         "LIVE · lệch"])
            for d in as_list(m.get("doi_chieu")):
                rows.append([cell("%s→%s" % (m.get("me") or "?", m["ma"]), dam=True),
                             cell(M.share_txt(d.get("ty_le")), mono=True), src_cell(d.get("nguon")),
                             cell(dmy(d.get("ngay")) or "không ghi ngày", mono=True), d.get("tier") or "không nhãn"])
        extra = self.dossier.get("xung_dot_so_lieu")
        if self.dossier and extra is None:
            add_warning(self.warnings, "Hồ sơ %s thiếu phần \"xung_dot_so_lieu\", bỏ phần đó." % self.nh.id)
        if not rows and not extra:
            return None
        khoi = []
        if rows:
            khoi.append(bang(["Chủ đề", "Giá trị", "Nguồn", "Ngày", "Loại"], rows,
                             "Mỗi giá trị giữ nguồn và ngày; không lấy trung bình."))
        if extra:
            khoi += [heading("Xung đột số liệu của hồ sơ")] + K.render_any(extra)
        return M.sec("xung_dot", "Xung đột số liệu", khoi, eyebrow="Đối chiếu nguồn · không lấy trung bình")

    def s_viec_treo(self):
        vt = self.part("viec_treo")
        if not vt:
            return None
        return M.sec("viec_treo", "Việc còn treo", [M.danh_sach([{"so": str(i + 1), "text": txt(x)}
                                                                 for i, x in enumerate(vt)])],
                     eyebrow="Việc treo · %s" % self.nhan_ho_so)

    def s_nguon(self):
        srcs = as_list(self.js.get("nguon_live"))
        rows = [source_row(s) for s in srcs]
        files = [("Registry nhóm", self.reg.path), ("Hồ sơ", self.dpath), ("Hội đồng", self.hpath),
                 ("Thư viện khung", self.kpath if self.lib else None)]
        khoi = [heading("Nguồn live (đọc trên máy, không gọi mạng)"),
                bang(SOURCE_COLS, rows),
                heading("Tệp của trang"),
                bang(["Tệp", "Đường dẫn"], [[cell(a, dam=True), src_cell(b) if b else "chưa có"] for a, b in files])]
        ng = [x for x in as_list(self.dossier.get("nguon")) if txt(x)]
        if ng:
            khoi += [heading("Nguồn chính của hồ sơ"),
                     M.danh_sach([{"so": str(i + 1), "text": txt(x)} for i, x in enumerate(ng)])]
        return M.sec("nguon", "Nguồn", khoi, eyebrow="Nguồn · phương pháp · giới hạn")

    # ── assembly ──

    def labels(self):
        hd = "Hội đồng %s %s" % (self.nh.id, dmy(self.hday))
        return {"hoi_dong": hd, "khung": "khung.json", "theo_doi_tuan": self.nhan_ho_so}

    def build(self, reg):
        lv = self.lv
        builders = [("cong", self.s_cong)]
        if lv.ok:
            builders += [("he_sinh_thai", self.s_he_sinh_thai), ("theo_doi_tuan", self.s_theo_doi)]
        builders += [("keynotes", self.s_keynotes), ("truyen_dan", self.s_truyen_dan)]
        if lv.ok:
            builders.append(("do_tre", self.s_do_tre))
        builders += [("dot_tang", self.s_dot_tang), ("khung", self.s_khung),
                     ("y_do_chu_the", lambda: self.s_list("y_do_chu_the", "y_do_chu_the", "Ý đồ chủ thể",
                                                          "Ý đồ chủ thể · %s" % self.nhan_ho_so)),
                     ("su_kien", self.s_su_kien), ("xuc_tac", self.s_xuc_tac)]
        if lv.ok:
            builders.append(("vung_gia", self.s_vung_gia))
        builders += [("hoi_dong", self.s_hoi_dong), ("nhan_dinh_cu", self.s_nhan_dinh_cu),
                     ("pre_mortem", self.s_pre_mortem), ("xung_dot", self.s_xung_dot), ("viec_treo", self.s_viec_treo)]
        sections = []
        for sid, fn in builders:
            s = fn()
            if s:
                sections.append(s)
        sections.append(self.s_nguon())
        lab = self.labels()
        for s in sections:
            K.guard_section(s, lab.get(s["id"], self.nhan_ho_so), self.warnings,
                            "Mục \"%s\"" % (s.get("tieu_de") or s["id"]))
        age, p_age, bits = stale_bits(self.data_to, self.dday, self.warnings)
        canh_bao_nguon(sections, self.warnings)
        meta = {"generated": now_iso(), "script_version": SCRIPT_VERSION,
                "nhom": nhom_meta(self.nh, co_ho_so=bool(self.dossier)), "ds_nhom": ds_nhom(reg),
                "registry_file": reg.path, "profile_dir": os.path.join(self.root, self.nh.id),
                "profile_file": self.dpath, "profile_date": iso(self.dday), "hoi_dong_file": self.hpath,
                "hoi_dong_date": iso(self.hday), "khung_file": self.kpath if self.lib else None,
                "artifact_url": nfc(self.dossier.get("artifact_url")) or None, "data_to": iso(self.data_to),
                "den": iso(self.den), "age_days": age, "profile_age_days": p_age, "stale": bool(bits),
                "stale_text": " · ".join(bits), "warnings": tom_tat_canh_bao(self.warnings),
                "sources_live": as_list(self.js.get("nguon_live"))}
        return {"meta": meta, "live": live_compact(self.js),
                "trang": {"schema": "vnblocks/1", "tieu_de": "Chaebol Reflex · %s" % (nfc(self.nh.get("ten")) or
                                                                                      self.nh.id),
                          "sections": sections},
                "csv": {"columns": CSV_COLS, "rows": self.csv}}


def live_compact(js):
    """to_json() without the heavy chart arrays (tests / debug; the panel renders `trang`)."""
    out = {k: v for k, v in js.items() if k not in ("chuoi", "kl_co_so", "dinh_gia_co_so", "zigzag", "nguon_live",
                                                    "canh_bao")}
    if out.get("ty_so"):
        out["ty_so"] = {k: v for k, v in out["ty_so"].items() if k != "tuan"}
    out["tang"] = [{k: v for k, v in t.items() if k != "tuan"} for t in as_list(out.get("tang"))]
    return out


def build_nhom(nh, reg, den=None, warnings=None):
    warnings = [] if warnings is None else warnings
    return Trang(nh, reg, reg_root(reg), den, warnings).build(reg)


# ── Masan (msn_reflex engine) ────────────────────────────────────────────────


def build_masan(nh, reg, den=None, warnings=None):
    """msn_reflex.build_overview() with its sections in place; the CỔNG guard runs over EVERY one of them, unit by
    unit, with the label "ĐÓNG BĂNG · hồ sơ MSN <ngày hồ sơ>" (the dossier's NAV rules, targets and stances are
    frozen history, spec decision 2). The Masan page gains the group's chaebol_hoi_dong/1 council (right after the
    dossier's own "hoi_dong" section), live lead/lag and the framework section (both before "nguon"); meta gains
    "nhom" and "ds_nhom"."""
    out = M.build_overview(den)
    gw = [] if warnings is None else list(warnings)
    pday = M.parse_day(out["meta"].get("profile_date"))
    nhan_msn = ("hồ sơ MSN %s" % dmy(pday)) if pday else "hồ sơ MSN"
    hit = []
    for s in out["trang"]["sections"]:
        head = " ".join(nfc(s.get(k)) for k in ("tieu_de", "eyebrow", "lede"))
        n = K.guard(s["khoi"], nhan_msn)
        if K.DONG_BANG not in head and K.has_forbidden(head):
            s["eyebrow"] = K._prefix(K.nhan_dong_bang(nhan_msn), s.get("eyebrow"))
            n += 1
        if n:
            hit.append(nfc(s.get("tieu_de")) or s.get("id"))
    if hit:
        add_warning(gw, "Engine Masan: %d mục trích lệnh, xếp hạng, định cỡ vị thế hoặc mức giá của nguồn (%s): "
                        "hiển thị như lịch sử %s, không chấm lại (CỔNG v1.7 DỪNG)." % (
                            len(hit), ", ".join(cut(x, 40) for x in hit[:8]) + (" …" if len(hit) > 8 else ""),
                            K.nhan_dong_bang(nhan_msn)))
    t = Trang(nh, reg, reg_root(reg), den, gw, dossier={})
    secs = out["trang"]["sections"]
    used = {s.get("id") for s in secs}
    hd = t.s_hoi_dong()
    tail = [s for s in ((t.s_do_tre() if t.lv.ok else None), t.s_khung()) if s]
    for s in ([hd] if hd else []) + tail:
        s["id"] = M.uniq_id(s["id"], used, t.hday if s is hd else (t.data_to or M.today()))
        lab = ("Hội đồng %s %s" % (nh.id, dmy(t.hday))) if s is hd else (
            "khung.json" if s["id"].startswith("khung") else "dữ liệu live")
        K.guard_section(s, lab, gw, "Mục \"%s\"" % s.get("tieu_de"))
    if gw:
        canh_bao_nguon(secs, gw, "%s · engine chung (Hội đồng, dẫn/trễ, khung) và CỔNG" % TEN_CANH_BAO)
        out["meta"]["warnings"] = as_list(out["meta"].get("warnings")) + [
            "Engine chung của trang (Hội đồng, dẫn/trễ, khung) và CỔNG: %d cảnh báo · danh sách ở khối \"%s\" cuối "
            "trang (mục Nguồn)." % (len(gw), TEN_CANH_BAO)]
    ids = [s.get("id") for s in secs]
    k = ids.index("nguon") if "nguon" in ids else len(secs)
    secs = secs[:k] + tail + secs[k:]
    if hd:
        ids = [s.get("id") for s in secs]
        j = ids.index("hoi_dong") + 1 if "hoi_dong" in ids else k
        secs = secs[:j] + [hd] + secs[j:]
    out["trang"]["sections"] = secs
    out["meta"]["nhom"] = nhom_meta(nh, co_ho_so=True)
    out["meta"]["ds_nhom"] = ds_nhom(reg)
    return out


# ── TỔNG QUAN ────────────────────────────────────────────────────────────────


class TongQuan:
    def __init__(self, reg, den, warnings):
        self.reg, self.den, self.warnings = reg, den, warnings
        self.root = reg_root(reg)
        self.lib, self.kpath = K.load_khung(self.root, warnings)
        self.cache = {}
        # lite: vnstore for every ticker (13-week returns), Vietcap files only for what the look-through needs
        core = set()
        for g in reg.groups():
            core |= lt_core(g)
        self.kho = shared_kho(reg.groups(), den, warnings, vc_syms=core, lite=True)
        self.rows, self.cot, self.caps = [], [], []
        self.data_to = None
        self.n_ho_so = self.n_hoi_dong = 0
        self.csv = []

    def group(self, nh):
        gw = []
        dossier, dpath, dday = ({}, None, None) if is_msn(nh) else load_dossier(self.root, nh.id, gw, self.den)
        hd, _, hday = load_hoi_dong(self.root, nh.id, gw, self.den)
        lv = L.LiveNhom(self.kho, nh, dossier, gw, co_so=axis_of(self.kho, nh), lite=True)
        js = lv.to_json()
        if lv.data_to:
            self.data_to = max(self.data_to, lv.data_to) if self.data_to else lv.data_to
        ratio_txt, ratio_v, phan_vi, pv_lab = CAN, None, None, ""
        ts = js.get("ty_so")
        if is_msn(nh):
            prof, _, pday = msn_profile(gw, self.cache)
            dday = pday
            ov = msn_overview(self.den, gw, self.cache)
            lo = as_dict((ov or {}).get("live"))
            if lo.get("ratio") is not None:
                ratio_v = lo["ratio"]
                ratio_txt, phan_vi, pv_lab = msn_ratio_txt(lo)
            self.caps += msn_capture_rows(prof, pday)
        elif ts:
            s3 = ts["thong_ke"]["3y"]
            ratio_v, phan_vi = ts["hien_tai"], s3["phan_vi"]
            ratio_txt = "%s · phân vị 3 năm %s" % (ts["txt"]["hien_tai"], ts["txt"]["phan_vi_3y"])
            pv_lab = ("phân vị %s" % ts["txt"]["phan_vi_3y"]) if s3.get("du_mau") else ts["txt"]["phan_vi_3y"]
        if ratio_v is not None:
            self.cot.append((nfc(nh.get("ten")) or nh.id, ratio_v, phan_vi, pv_lab))
        fresh = lv.data_to - timedelta(days=L.LAG_WARN_DAYS) if lv.data_to else None
        tv = [m for m in as_list(js.get("thanh_vien")) if m.get("co_gia") and as_dict(m.get("loi_suat")).get("r_13t")
              is not None and fresh and as_dict(m.get("loi_suat")).get("ngay", "") >= fresh.isoformat()]
        hi = max(tv, key=lambda m: m["loi_suat"]["r_13t"]) if tv else None
        lo_ = min(tv, key=lambda m: m["loi_suat"]["r_13t"]) if tv else None
        ev = sorted(items(dossier.get("su_kien"), "mo_ta"), key=lambda r: nfc(r.get("ngay")), reverse=True)
        ev_txt = ("%s · %s" % (dmy(ev[0].get("ngay")), cut(ev[0].get("mo_ta"), 120))) if ev else (
            "xem trang Masan" if is_msn(nh) else "–")
        if ev and K.has_forbidden(ev_txt):         # an event quoting a rating change: frozen, with its dossier
            ev_txt = "%s · %s" % (K.nhan_dong_bang("hồ sơ %s %s" % (nh.id, dmy(dday))), ev_txt)
        self.n_ho_so += bool(dossier or (is_msn(nh) and dday))
        self.n_hoi_dong += bool(hd)
        p_age = (M.today() - dday).days if dday else None
        self.rows.append([
            cell(nfc(nh.get("ten")) or nh.id, dam=True, tip=nh.id), cut(nh.get("chu_the"), 90) or "–",
            cell(nfc(nh.get("truc")) or "–", mono=True), cell(nh.me or "không", mono=True),
            cell("%d/%d" % (js["nhom"]["so_ma_co_gia"], len(nh.tickers())), mono=True),
            cell(ratio_txt, mono=True), cell(("%s %s / %s %s" % (hi["ma"], hi["txt"]["r_13t"], lo_["ma"],
                                                                 lo_["txt"]["r_13t"])) if hi else "–", mono=True),
            ev_txt, hoi_dong_txt(hd, hday, nh), cell(("%d ngày" % p_age) if p_age is not None else "chưa có", mono=True)])
        self.csv.append(["Tổng quan", nh.id, ratio_txt, dmy(lv.data_to), "LIVE", T_EST,
                         "13T: %s" % (("%s %s / %s %s" % (hi["ma"], hi["txt"]["r_13t"], lo_["ma"], lo_["txt"]["r_13t"]))
                                      if hi else "–")])
        for c in latest_captures(js):
            self.caps.append([cell(nfc(nh.get("ten")) or nh.id, dam=True), cell("%s ← %s" % (c["me"], c["con"]),
                                                                                mono=True),
                              cell("%s → %s%s" % (dmy(c["tu"]), dmy(c["den"]), "" if c["xac_nhan"] else " · mở"),
                                   mono=True), cell(M.pct_txt(c["r_con"]), mono=True),
                              cell(M.pct_txt(c["r_me"]), mono=True), cell(M.fmt_vn(c["capture"], 2, fixed=True), mono=True),
                              "LIVE · EST"])
        for r in items(dossier.get("capture_dong_bang"), "cap"):
            self.caps.append([cell(nfc(nh.get("ten")) or nh.id, dam=True), cell(txt(r.get("cap")), mono=True),
                              cell(txt(r.get("cua_so")), mono=True), "–", "–", cell(txt(r.get("gia_tri")), mono=True),
                              src_cell("%s · %s" % (DB, src_txt(r)))])
        if gw:
            add_warning(self.warnings, "Nhóm %s: %d cảnh báo dữ liệu (mở trang nhóm để xem)." % (nh.id, len(gw)))

    def build(self):
        for nh in self.reg.groups():
            self.group(nh)
        sections = [self.s_cong(), self.s_nhom(), self.s_cot(), self.s_capture()]
        ce = K.khung_entry(self.lib, r"concentration")
        sections.append(K.section_thu_vien(self.lib, self.kpath, self.warnings,
                                           bo_qua=(nfc(ce.get("id")),) if ce else ()))
        if ce:
            sections.append(M.sec("concentration_era", "Concentration Era · %s" % DB, K.entry_compact(ce),
                                  eyebrow="Khung thị trường · %s · %s" % (DB, K.cut(K.ngan(K.nguon_txt(ce)),
                                                                                    K.NGUON_CUT))))
        elif self.lib:
            add_warning(self.warnings, "khung.json chưa có khung Concentration Era, bỏ mục đó.")
        sections.append(self.s_nguon())
        sections = [s for s in sections if s]
        for s in sections:
            K.guard_section(s, "khung.json" if s["id"] in ("thu_vien_khung", "concentration_era") else "hồ sơ",
                            self.warnings, "Mục \"%s\"" % (s.get("tieu_de") or s["id"]))
        age, _, bits = stale_bits(self.data_to, None, self.warnings)
        canh_bao_nguon(sections, self.warnings)
        tickers = {t for g in self.reg.groups() for t in g.tickers()}
        meta = {"generated": now_iso(), "script_version": SCRIPT_VERSION,
                "nhom": {"id": TONG_QUAN, "ten": TEN_TONG_QUAN, "me": None, "so_ma": len(tickers),
                         "co_ho_so": self.n_ho_so > 0, "co_hoi_dong": self.n_hoi_dong > 0},
                "ds_nhom": ds_nhom(self.reg), "registry_file": self.reg.path, "profile_dir": self.root,
                "profile_file": None, "profile_date": iso(M.parse_day(self.reg.get("lap_luc"))),
                "hoi_dong_file": None, "hoi_dong_date": None,
                "khung_file": self.kpath if self.lib else None, "artifact_url": None, "data_to": iso(self.data_to),
                "den": iso(self.den), "age_days": age, "profile_age_days": None, "stale": bool(bits),
                "stale_text": " · ".join(bits), "warnings": tom_tat_canh_bao(self.warnings),
                "sources_live": list(self.kho.sources)}
        return {"meta": meta, "live": {"nhom": len(self.reg.groups()), "ty_so": [
            {"ten": a, "hien_tai": b, "phan_vi": c, "nhan": d} for a, b, c, d in self.cot]},
                "trang": {"schema": "vnblocks/1", "tieu_de": "Chaebol Reflex · %s" % TEN_TONG_QUAN,
                          "sections": sections}, "csv": {"columns": CSV_COLS, "rows": self.csv}}

    def s_cong(self):
        return M.sec("cong", "Chaebol Reflex · hồ sơ độ trễ mẹ–con · %d nhóm" % len(self.reg.groups()), [
            {"kieu": "cong", "dong": CONG_MAC_DINH, "tier": T_EST,
             "phu": "Mặc định của tab: CỔNG v1.7 đang DỪNG, không phát playbook"},
            doan("LIVE: dữ liệu đến %s · tạo lúc %s · %d nhóm · %d hồ sơ · %d phiên Hội đồng" % (
                dmy(self.data_to) or CAN, datetime.now(M.ICT).strftime("%H:%M %d/%m"), len(self.reg.groups()),
                self.n_ho_so, self.n_hoi_dong), mau="lam")],
            eyebrow="Chaebol Reflex · TỔNG QUAN",
            lede="Mỗi nhóm: chủ thể, mẹ niêm yết, mẹ ÷ look-through và vị trí trong lịch sử, mã mạnh/yếu nhất 13 tuần, "
                 "sự kiện mới nhất, Hội đồng và tuổi hồ sơ. Bấm chip nhóm để mở trang chi tiết.")

    def s_nhom(self):
        return M.sec("nhom", "Các nhóm sở hữu", [bang(
            ["Nhóm", "Chủ thể", "Trục", "Mẹ", "Mã có giá", "Mẹ ÷ LT · vị trí", "Mạnh / yếu nhất 13T", "Sự kiện mới nhất",
             "Hội đồng", "Tuổi hồ sơ"], self.rows,
            "Mẹ ÷ LT: EST (vốn hóa giá thô, tỷ lệ registry); phân vị = phần trăm số tuần 3 năm thấp hơn hiện tại, kèm "
            "cửa sổ (từ ngày · số tuần), cần ≥ %d tuần. Masan theo engine riêng (số cp hồ sơ, cửa sổ từ 01/2024). Mạnh / "
            "yếu 13T: trên các mã có giá đến ngày dữ liệu của nhóm. Giá, %%: FACT-T2." % L.PCT_MIN_N, can_phai=[4])],
            eyebrow="Registry %s" % K.ngan(self.reg.path))

    def s_cot(self):
        if not self.cot:
            return None
        block = {"loai": "cot", "huong": "ngang", "nhan": [a for a, _, _, _ in self.cot],
                 "nhan_phu": [d or CAN for _, _, _, d in self.cot],
                 "series": [{"name": "mẹ ÷ look-through", "y": [round(b, 3) for _, b, _, _ in self.cot],
                             "mau": "vang"}],
                 "gia_tri": True, "so_le": 2, "dv": "×", "vach": [{"v": 1, "text": "1×", "mau": "xam"}]}
        return M.sec("ty_so_nhom", "Mẹ ÷ look-through của các nhóm có mẹ niêm yết", [M.bieu_do(
            "Mẹ ÷ look-through · LIVE %s" % dmy(self.data_to),
            "Dưới 1× = mẹ rẻ hơn phần cổ phần niêm yết nó nắm; trên 1× = thị trường trả thêm cho phần ngoài niêm yết. "
            "Nhãn phụ = phân vị kèm cửa sổ của chính nhóm (từ ngày · số tuần): 3 năm của engine chung, từ 01/2024 với "
            "engine Masan; dưới %d tuần thì %s." % (L.PCT_MIN_N, CAN), "vnstore · Vietcap · registry", T_EST, block,
            max(220, 34 * len(self.cot)))],
            eyebrow="So sánh xuyên chaebol · EST")

    def s_capture(self):
        if not self.caps:
            add_warning(self.warnings, "Chưa có capture nào (live hoặc của nguồn), bỏ bảng capture xuyên chaebol.")
            return None
        return M.sec("capture", "Capture xuyên chaebol", [bang(
            ["Nhóm", "Cặp mẹ ← con", "Cửa sổ", "Con", "Mẹ", "Capture", "Loại"], self.caps,
            "LIVE = chân zigzag 30%% gần nhất của mỗi cặp (EST); %s = số của nguồn theo cửa sổ và ngày của nó." % DB,
            can_phai=[3, 4, 5])], eyebrow="Capture · LIVE + %s" % DB)

    def s_nguon(self):
        srcs = gop_nguon(self.kho.sources)
        return M.sec("nguon", "Nguồn", [
            heading("Nguồn live (đọc trên máy, không gọi mạng)"),
            bang(SOURCE_COLS, [source_row(s) for s in srcs],
                 "Tệp Vietcap theo mã gộp một dòng mỗi loại tệp (<MÃ> trong đường dẫn), danh sách mã ở ghi chú."),
            bang(["Tệp", "Đường dẫn"], [[cell("Registry nhóm", dam=True), src_cell(self.reg.path)],
                                        [cell("Thư viện khung", dam=True), src_cell(self.kpath) if self.lib else
                                         "chưa có"],
                                        [cell("Hồ sơ, Hội đồng", dam=True), src_cell(os.path.join(self.root, "<id>"))]])],
            eyebrow="Nguồn")


def msn_ratio_txt(lo):
    """Masan's ratio from its own engine (window from 01/2024) → (table text, percentile | None, bar label)."""
    n = lo.get("ratio_pct_n") or 0
    tu = "%02d/%d" % (M.RATIO_FROM.month, M.RATIO_FROM.year)
    low = lo.get("ratio_pct_lower")
    if low is None or n < L.PCT_MIN_N:
        lab = "%s: chỉ %d tuần từ %s · engine Masan" % (CAN, n, tu) if n else "%s · engine Masan" % CAN
        return "%s · %s" % (M.x_txt(lo["ratio"]), lab), None, lab
    return ("%s · thấp hơn %s số tuần từ %s · %d tuần (engine Masan)" % (M.x_txt(lo["ratio"]), M.fmt_vn(low, 0) + "%",
                                                                        tu, n),
            100.0 - low, "phân vị %s%% · từ %s · %d tuần · engine Masan" % (M.fmt_vn(100.0 - low, 0), tu, n))


def hoi_dong_txt(hd, hday, nh):
    if not hd:
        return M.pill("chưa có phiên", "vang") if nh.get("hoi_dong") else cell("–", mono=True)
    cnt = {}
    for key in ("kill_zone", "alpha_zone"):
        for x in as_list(hd.get(key)):
            p = txt(as_dict(x).get("phieu")).upper()
            cnt[p] = cnt.get(p, 0) + 1
    st = txt(as_dict(hd.get("synthesis")).get("trang_thai")) or "?"
    return cell("%s · %s · %s" % (st, M.ddmm(hday), " · ".join("%d %s" % (n, p.lower()) for p, n in cnt.items())),
                mono=True)


def latest_captures(js):
    best = {}
    for c in as_list(js.get("capture")):
        if c.get("capture") is None:
            continue
        k = (c["me"], c["con"])
        if k not in best or c["tu"] > best[k]["tu"]:
            best[k] = c
    return list(best.values())


def msn_capture_rows(prof, pday):
    rows = []
    for c in as_list(as_dict(as_dict(prof).get("phan_III")).get("capture")):
        c = as_dict(c)
        rows.append([cell("Masan (hồ sơ MSN)", dam=True), cell(nfc(c.get("cap")), mono=True),
                     cell(nfc(c.get("cua_so")), mono=True), cell(M.fmt_vn(c.get("con_pct"), 1, sign=True) + "%", mono=True),
                     cell(M.fmt_vn(c.get("me_pct"), 1, sign=True) + "%", mono=True),
                     cell(nfc(c.get("capture_in")) or M.fmt_vn(c.get("capture"), 2, fixed=True), mono=True),
                     "%s · hồ sơ MSN %s" % (DB, dmy(pday))])
    return rows


def build_tong_quan(reg, den=None, warnings=None):
    return TongQuan(reg, den, [] if warnings is None else warnings).build()


# ── dispatch ─────────────────────────────────────────────────────────────────


REG_WARN_RE = re.compile(r"Registry ([a-z0-9_]+)(?:,|:)")


def reg_warnings(rw, nid=None):
    """Registry validation warnings for one page: a group page keeps its own and the global ones; TỔNG QUAN (nid
    None) keeps the global ones and one count line per group."""
    out, per = [], {}
    for w in rw:
        m = REG_WARN_RE.match(w)
        if not m:
            out.append(w)
        elif nid is not None:
            if m.group(1) == nid:
                out.append(w)
        else:
            per[m.group(1)] = per.get(m.group(1), 0) + 1
    out += ["Registry %s: %d cảnh báo dữ liệu (mở trang nhóm để xem)." % (k, n) for k, n in per.items()]
    return out


def build_page(nhom=None, ma=None, den=None, root=None):
    reg, rw = require_registry(root)
    nid = nfc(nhom)
    if ma:
        gs = groups_of_ma(reg, ma)
        if not gs:
            raise M.MsnError("UNKNOWN_GROUP", "Mã %s không thuộc nhóm nào của registry %s." % (L.ticker(ma) or ma,
                                                                                               reg.path))
        nh = gs[0]
    elif not nid or nid == TONG_QUAN:
        return build_tong_quan(reg, den, reg_warnings(rw))
    else:
        nh = reg.nhom(nid)
        if nh is None:
            raise M.MsnError("UNKNOWN_GROUP", "Registry không có nhóm \"%s\" (có: %s)." % (
                nid, ", ".join(g.id for g in reg.groups())))
    warnings = reg_warnings(rw, nh.id)
    if is_msn(nh):
        return build_masan(nh, reg, den, warnings)
    return build_nhom(nh, reg, den, warnings)


def cmd_nhom(root=None):
    reg, w = require_registry(root)
    return {"meta": {"generated": now_iso(), "script_version": SCRIPT_VERSION, "registry_file": reg.path,
                     "so_nhom": len(reg.groups()), "warnings": w}, "ds_nhom": ds_nhom(reg)}


# ── ALL-IN-ONE cell ──────────────────────────────────────────────────────────


def reduced_set(nh, t, dossier, extra=()):
    """The tickers an AIO cell needs: the ticker, the look-through core (lt_core), dossier signal tickers, `extra`
    (the full group's time axis), and the holding chain of each of them."""
    keep = {t} | lt_core(nh) | {x for x in extra if x}
    for r in as_list(dossier.get("tin_hieu")):
        _, _, arg = nfc(as_dict(r).get("bien")).partition(":")
        if L.ticker(arg):
            keep.add(L.ticker(arg))
    return chain_up(nh, keep)


def reduced(nh, t, dossier, warnings, extra=()):
    """The group restricted to reduced_set (registry rows unchanged)."""
    keep = reduced_set(nh, t, dossier, extra)
    raw = dict(nh)
    raw["thanh_vien"] = [m for m in as_list(nh.get("thanh_vien"))
                         if isinstance(m, dict) and L.ticker(m.get("ma")) in keep]
    raw["tang"] = [x for x in as_list(nh.get("tang")) if L.ticker(as_dict(x).get("me")) in keep]
    return L.Nhom(raw, warnings)


def vni_r13(kho, d):
    vd, vv = kho.vni()
    k = bisect.bisect_right(vd, d)
    if not k:
        return None
    ws = M.weeks_of(vd[:k], vv[:k])
    prior = [w for w in ws if w["fri"] < M.friday(vd[k - 1])]
    return L.pct(vv[k - 1], prior[-L.R13_WEEKS]["close"]) if len(prior) >= L.R13_WEEKS else None


def role_line(nh, t, lv):
    m = as_dict(nh.member(t))
    ten = nfc(nh.get("ten")) or nh.id
    if t == nh.me:
        lt = ", ".join(lv.lt_set)
        return "mẹ của nhóm %s · %s" % (ten, ("%d con trong look-through (%s)" % (len(lv.lt_set), lt)) if lt else
                                         "chưa có con nào đủ điều kiện look-through")
    vai = nfc(m.get("vai_tro")) or "thành viên"
    up = nh.holder(t)
    d = lv.data_to or M.today()
    if not nh.me:
        line = "%s nhóm %s · mẹ không niêm yết (%s)" % (vai, ten, nfc(nh.get("chu_the")) or "?")
    elif up:
        w, row = nh.weight_row(t, d, "phap_ly")
        line = "%s của %s · %s nắm %s" % (vai, up, up, ("%s (%s %s)" % (M.share_txt(w), row["tier"], dmy(row["tu"])))
                                          if row else CAN)
        wh, rh = nh.weight_row(t, d, "hieu_dung")
        if rh:
            line += " · hiệu dụng %s (%s %s)" % (M.share_txt(wh), rh["tier"], dmy(rh["tu"]))
    else:
        line = "%s · nhóm %s (mẹ %s)" % (vai, ten, nh.me)
    if nh.me and t != nh.me:
        line += " · trong look-through" if t in lv.lt_set else " · ngoài look-through"
    cho = nh.pending(t)
    if cho:
        line += " · chờ CBTT: " + "; ".join("%s từ %s" % (M.share_txt(r["ty_le"]), dmy(r["tu"])) for r in cho)
    if any(x["me"] == t for x in nh.tang):
        line += " · tầng holdco của " + ", ".join(c for x in nh.tang if x["me"] == t for c in x["con"])
    return line


def nearest_signals(js, dossier):
    prof = [r for r in as_list(dossier.get("tin_hieu")) if isinstance(r, dict)]
    out = []
    for r, s in zip(prof, as_list(js.get("tin_hieu"))):
        v, muc = M.finite(s.get("gia_tri")), M.finite(s.get("muc"))
        if not s.get("live") or v is None or muc is None:
            continue
        name = nfc(s.get("bien")).partition(":")[0]
        m = L.muc_dong(muc) if name in ("me_dong_tuan", "dong_tuan") else muc
        out.append((abs(v - m) / abs(m) if m else abs(v), nfc(r.get("id")), nfc(r.get("mo_ta")), s["gia_tri_txt"],
                    nfc(r.get("nguong_text")) or "%s %s" % (s.get("phep"), M.fmt_vn(muc)), s["trang_thai"],
                    s.get("as_of")))
    return sorted(out, key=lambda x: x[0])[:AIO_SIGNALS]


def nearest_msn_signals(ov, prof):
    sig = as_dict(as_dict(as_dict(ov).get("live")).get("signals"))
    out = []
    for r in as_list(as_dict(as_dict(prof).get("theo_doi_tuan")).get("tin_hieu")):
        r = as_dict(r)
        s = as_dict(sig.get(r.get("id")))
        v, muc = M.finite(s.get("v")), M.finite(r.get("muc"))
        if v is None or muc is None:
            continue
        out.append((abs(v - muc) / abs(muc) if muc else abs(v), nfc(r.get("id")), nfc(r.get("ten")),
                    nfc(s.get("gia_tri_in")), nfc(r.get("nguong")), nfc(s.get("trang_thai")),
                    dmy(as_dict(ov.get("live")).get("data_to"))))
    return sorted(out, key=lambda x: x[0])[:AIO_SIGNALS]


def hoi_dong_line(hd, hday):
    if not hd:
        return None
    parts = []
    for key, name in (("kill_zone", "kill zone"), ("alpha_zone", "alpha zone")):
        cnt = {}
        for x in as_list(hd.get(key)):
            p = txt(as_dict(x).get("phieu")) or "?"
            cnt[p] = cnt.get(p, 0) + 1
        if cnt:
            parts.append("%s: %s" % (name, ", ".join("%d %s" % (n, p) for p, n in cnt.items())))
    st = txt(as_dict(hd.get("synthesis")).get("trang_thai"))
    if st:
        parts.append("synthesis %s" % st)
    return doan("Hội đồng %s · %s" % (dmy(hday), " · ".join(parts) or "chưa có phiếu"), mau="tim")


def frozen_line(dossier, msn_prof=None):
    rows = sorted(items(dossier.get("nhan_dinh_cu_dong_bang"), "tom_tat"),
                  key=lambda r: nfc(r.get("ngay")), reverse=True)
    if rows:
        r = rows[0]
        return doan("%s · %s %s: %s" % (DB, txt(r.get("tac_gia")) or cut(K.ngan(r.get("nguon")), 80) or "?",
                                        dmy(r.get("ngay")), cut(r.get("tom_tat"))), mau="xam")
    prof, _, pday = msn_prof or (None, None, None)
    k = nfc(as_dict(as_dict(prof).get("cong")).get("ket_luan_mot_dong"))
    if k:
        return doan("%s · hồ sơ MSN %s: %s" % (DB, dmy(pday), cut(k)), mau="xam")
    return None


def aio_group(nh, t, lv, js, dossier, hd, hday, ov=None, msn_prof=None, nhan="hồ sơ"):
    tv = {m["ma"]: m for m in as_list(js.get("thanh_vien")) if m.get("ma")}
    m = as_dict(tv.get(t))
    ts = js.get("ty_so")
    ls, sg, kl = as_dict(m.get("loi_suat")), m.get("sigma"), as_dict(m.get("kl"))
    lo = as_dict(as_dict(ov).get("live"))
    if lo.get("ratio") is not None:
        t1 = tile("%s ÷ look-through" % nh.me, M.x_txt(lo["ratio"]), "%s · số cp hồ sơ" % msn_ratio_txt(lo)[2],
                  tier=T_EST, live=True)
    elif ts:
        t1 = tile("%s ÷ look-through" % ts["me"], ts["txt"]["hien_tai"], "phân vị 3 năm %s · toàn dải %s · trung vị 3 "
                                                                         "năm %s" % (ts["txt"]["phan_vi_3y"],
                                                                                     ts["txt"]["phan_vi_toan_dai"],
                                                                                     ts["txt"]["trung_vi_3y"]),
                  tier=T_EST, live=True)
    else:
        t1 = tile("Mẹ ÷ look-through", CAN, "nhóm không có mẹ niêm yết" if not nh.me else "chưa có con đủ điều kiện LT",
                  tier=T_EST)
    me_r = as_dict(as_dict(tv.get(nh.me)).get("loi_suat")).get("r_13t") if (nh.me and t != nh.me) else None
    if me_r is None:
        me_r, ref = vni_r13(lv.kho, lv.data_to) if lv.data_to else None, "VN-Index"
    else:
        ref = nh.me
    r13 = ls.get("r_13t")
    rel = (((1 + r13 / 100.0) / (1 + me_r / 100.0) - 1) * 100.0) if (r13 is not None and me_r is not None) else None
    t2 = tile("%s so %s · 13 tuần" % (t, ref), M.pct_txt(rel), "%s %s · %s %s" % (t, M.pct_txt(r13), ref,
                                                                                  M.pct_txt(me_r)),
              mau=pct_mau(rel), tier=T_DATA, live=True)
    t3 = tile("σ %s" % t, M.sigma_txt(sg["z"]) if sg else CAN,
              ("%s μ %s · σ %s · engine %s%s" % ("P/B" if sg["metric"] == "pb" else "P/E", M.fmt_vn(sg["mu"]),
                                                 M.fmt_vn(sg["sd"]), dmy(as_dict(sg.get("engine")).get("ngay")) or "?",
                                                 " · −2σ ≤ 0, chỉ chấm phía đắt" if sg["suy_bien"] else ""))
              if sg else (m.get("sigma_ly_do") or "engine HHP chưa có μ/σ"), tier=T_EST, live=bool(sg))
    t4 = tile("KL tuần ÷ TB20 · %s" % t, M.x_txt(kl.get("ty_le")), "tuần %s%s" % (
        dmy(kl.get("tuan")) or "?", (" · tuần đang mở (%s phiên) %s" % (kl["mo_so_phien"], M.x_txt(kl.get("mo_ty_le"))))
        if kl.get("mo_so_phien") else ""), tier=T_DATA, live=True)
    ten = nfc(nh.get("ten")) or nh.id
    khoi = [doan("%s%s · %s" % ("" if ten.lower().startswith("nhóm") else "Nhóm ", ten, role_line(nh, t, lv)), mau="vang"),
            M.o_so([t1, t2, t3, t4], cot=4)]
    sig = nearest_msn_signals(ov, (msn_prof or (None,))[0]) if ov else nearest_signals(js, dossier)
    if sig:
        khoi.append(bang(["Tín hiệu gần ngưỡng nhất", "Giá trị", "Ngưỡng", "Trạng thái", "Kỳ"],
                         [[cell("%s · %s" % (a, cut(b, 70)), dam=True), cell(c, mono=True), cell(d, mono=True),
                           M.pill(e, SIGNAL_MAU.get(e, "vang")), cell(f or "", mono=True)] for _, a, b, c, d, e, f in sig],
                         "Ngưỡng của hồ sơ, chấm LIVE; trạng thái ngưỡng, không phải lệnh."))
    ev = sorted(items(dossier.get("su_kien"), "mo_ta"), key=lambda r: nfc(r.get("ngay")),
                reverse=True)[:AIO_EVENTS]
    if ev:
        khoi.append(bang(["Ngày", "Sự kiện", "Nhãn"], [[cell(dmy(r.get("ngay")), mono=True), cut(r.get("mo_ta"), 160),
                                                         nhan_cell(r)] for r in ev],
                         "%s: sự kiện như nguồn ghi, không chấm lại." % K.nhan_dong_bang(nhan)))
    khoi += [hoi_dong_line(hd, hday), frozen_line(dossier, msn_prof)]
    return [b for b in khoi if b]


def o_aio(ma, den=None, root=None):
    """Chaebol Reflex cell of the ALL-IN-ONE grid for one ticker (see module doc), or None."""
    t = L.ticker(ma)
    if not t:
        return None
    reg, rw = L.load_registry(root)
    gs = groups_of_ma(reg, t)
    if not gs:
        return None
    root = reg_root(reg)
    warnings, cache = [w for g in gs for w in reg_warnings(rw, g.id)], {}
    warnings = list(dict.fromkeys(warnings))
    plan, need = [], set()
    for nh in gs:
        dossier, _, dday = ({}, None, None) if is_msn(nh) else load_dossier(root, nh.id, warnings, den)
        plan.append((nh, dossier, dday))
        need |= reduced_set(nh, t, dossier)
    # vnstore rows for every ticker of the groups (the time axis is chosen on the FULL group, as on its page);
    # Vietcap files only for the reduced sets plus that axis
    kho = shared_kho(gs, den, warnings, vc_syms=need)
    khoi, d_to, d_hs = [], None, None
    for nh, dossier, dday in plan:
        cs = axis_of(kho, nh)
        small = reduced(nh, t, dossier, warnings, extra=(cs,))
        hd, _, hday = load_hoi_dong(root, nh.id, warnings, den)
        lv = L.LiveNhom(kho, small, dossier, warnings, co_so=cs)
        js = lv.to_json()
        ov = mp = None
        if is_msn(nh):
            mp = msn_profile(warnings, cache)
            dday = mp[2]
            ov = msn_overview(den, warnings, cache)
        d_to = d_to or lv.data_to
        d_hs = d_hs or dday
        if not lv.ok:
            khoi.append(doan("%s · %s: kho giá không có phiên của nhóm." % (nfc(nh.get("ten")) or nh.id, CAN), mau="do"))
            continue
        nhan = ("hồ sơ MSN %s" % dmy(dday)) if is_msn(nh) else ("hồ sơ %s %s" % (nh.id, dmy(dday))).strip()
        khoi += K.guard_blocks(aio_group(nh, t, lv, js, dossier, hd, hday, ov, mp, nhan), nhan, warnings,
                               "Ô Chaebol Reflex %s · nhóm %s" % (t, nh.id))
    return {"id": "reflex", "tieu_de": "%s · %s" % (TAB_NHAN, " · ".join(nfc(g.get("ten")) or g.id for g in gs)),
            "eyebrow": AIO_EYEBROW, "tab": TAB_ID, "tab_nhan": TAB_NHAN, "cot": 12, "tier": T_EST, "khoi": khoi,
            "trang_thai_ngay": iso(d_to), "ho_so_ngay": iso(d_hs), "nhom_ids": [g.id for g in gs],
            "nhom_mo": gs[0].id, "canh_bao": warnings}


# Extra ALL-IN-ONE cells (public API for all_in_one_ma.py, request of the ALL-IN-ONE session 10/10/2026): the
# "rich" Reflex screens of the ticker's first group, taken from its built page. Never the action, council, rigor,
# price-zone, forecast, pre-mortem or frozen-stance sections (CỔNG v1.7 DỪNG); every block passes the guard again.
AIO_MO_RONG_BO = ("hanh_dong", "hoi_dong", "rigor_6d", "vung_gia", "du_bao", "nhan_dinh_cu", "pre_mortem")


def _sec_of(page, sid):
    return next((s for s in page["trang"]["sections"] if s.get("id") == sid), None)


def _charts(sec, *needles):
    """bieu_do blocks of a section whose title contains any of `needles` (case-insensitive)."""
    if not sec:
        return []
    return [b for b in sec.get("khoi") or [] if b.get("kieu") == "bieu_do"
            and any(n.lower() in nfc(b.get("tieu_de")).lower() for n in needles)]


def o_aio_mo_rong(ma, den=None, root=None):
    """→ list of ALL-IN-ONE cells (same keys as o_aio, ids "reflex_*", cot 6 | 12) for the ticker's first registry
    group, or [] when the ticker is in no group. Cells: reflex_quy_ve_100 (rebased chart), reflex_ty_so (parent ÷
    listed stakes, only with a listed parent), reflex_keynotes, reflex_ba_dong_ho (Masan), reflex_dot_tang (rallies;
    Masan: Phần I), reflex_do_tre (lead/lag)."""
    t = L.ticker(ma)
    if not t:
        return []
    reg, _ = L.load_registry(root)
    gs = groups_of_ma(reg, t)
    if not gs:
        return []
    nh = gs[0]
    page = build_page(nhom=nh.id, den=den, root=root)
    msn = is_msn(nh)
    meta = page.get("meta") or {}
    d_to = meta.get("data_to")
    ten = nfc(nh.get("ten")) or nh.id
    nhan = ("hồ sơ MSN %s" % dmy(M.parse_day(meta.get("profile_date")))) if msn else "hồ sơ %s" % nh.id
    warnings = []

    def cell_of(cid, tieu_de, khoi, cot, tier=T_EST):
        khoi = [copy.deepcopy(b) for b in khoi if b]
        if not khoi:
            return None
        K.guard_blocks(khoi, nhan, warnings, "Ô %s · %s" % (cid, t))
        return {"id": cid, "tieu_de": "%s · %s · %s" % (TAB_NHAN, ten, tieu_de), "eyebrow": AIO_EYEBROW, "tab": TAB_ID,
                "tab_nhan": TAB_NHAN, "cot": cot, "tier": tier, "khoi": khoi, "trang_thai_ngay": d_to,
                "nhom_mo": nh.id}

    hst = _sec_of(page, "phan_2" if msn else "he_sinh_thai")
    cells = [cell_of("reflex_quy_ve_100", "quy về 100 · LIVE", _charts(hst, "quy về 100"), 6, T_DATA),
             cell_of("reflex_ty_so", "mẹ ÷ giá trị cổ phần niêm yết", _charts(hst, "÷ look-through", "÷ giá trị"), 6)]
    for cid, sid, tieu_de in (("reflex_keynotes", "keynotes", "keynotes"),
                              ("reflex_ba_dong_ho", "ba_dong_ho", "ba đồng hồ thị trường"),
                              ("reflex_dot_tang", "phan_1" if msn else "dot_tang", "các đợt tăng"),
                              ("reflex_do_tre", "do_tre", "dẫn / trễ mẹ–con")):
        s = _sec_of(page, sid)
        if s and sid not in AIO_MO_RONG_BO:
            cells.append(cell_of(cid, nfc(s.get("tieu_de")) or tieu_de, s.get("khoi") or [], 12))
    return [c for c in cells if c]


def cmd_ma(ma, den=None, root=None):
    reg, w = require_registry(root)
    t = L.ticker(ma)
    o = o_aio(t, den, root)
    return {"meta": {"generated": now_iso(), "script_version": SCRIPT_VERSION, "registry_file": reg.path, "ma": t,
                     "nhom_ids": [g.id for g in groups_of_ma(reg, t)], "den": iso(den), "warnings": w}, "o": o}
