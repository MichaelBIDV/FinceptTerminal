#!/usr/bin/env python3
"""
Fincept Terminal: Chaebol Reflex CLI (tab "msn_reflex", label "Chaebol Reflex"). The panel calls this script through
EconomicsService / PythonRunner; the pages are built by chaebol_reflex_trang.py on the chaebol_reflex_live.py
engine, the Masan page by msn_reflex.py. Stdlib only, Python 3.9+, no network, read-only.

USAGE
    python3 chaebol_reflex.py nhom
        → {"meta": {generated, script_version, registry_file, so_nhom, warnings}, "ds_nhom": [{id, ten, truc, me,
           co_hoi_dong}]}   (TỔNG QUAN first, then NQ68, NQ79, SPECIAL, KG21, V21, others)
    python3 chaebol_reflex.py overview [--nhom ID | --ma MÃ] [--den YYYY-MM-DD]
        → one page {"meta", "live", "trang": vnblocks/1, "csv"}; no --nhom / --nhom tong_quan = TỔNG QUAN; --ma opens
          the ticker's first group (parent > LT child > any).
    python3 chaebol_reflex.py ma --ma MÃ [--den YYYY-MM-DD]
        → {"meta": {..., "ma", "nhom_ids"}, "o": ALL-IN-ONE cell | null}

OUTPUT: exactly ONE compact JSON object on stdout (UTF-8), exit code 0 even on errors:
    {"error": "<Vietnamese message>", "error_code": "NO_REGISTRY" | "BAD_ARGS" | "UNKNOWN_GROUP" | "INTERNAL"}
    (the Masan page can also return msn_reflex's NO_PROFILE / BAD_PROFILE).
Env: CHAEBOL_REFLEX_DIR (registry root) plus the msn_reflex MSN_* overrides; MSN_TODAY fixes "today" in tests.
"""

from __future__ import annotations

import sys

import chaebol_reflex_live as L
import chaebol_reflex_trang as T
import msn_reflex as M

USAGE = ("Dùng: chaebol_reflex.py nhom | overview [--nhom ID | --ma MÃ] [--den YYYY-MM-DD] | "
         "ma --ma MÃ [--den YYYY-MM-DD]")
FLAGS = {"nhom": (), "overview": ("--nhom", "--ma", "--den"), "ma": ("--ma", "--den")}


def parse_flags(rest, allowed):
    out = {}
    if len(rest) % 2:
        raise M.MsnError("BAD_ARGS", "Tham số không hợp lệ: %s. %s" % (" ".join(rest), USAGE))
    for k, v in zip(rest[::2], rest[1::2]):
        if k not in allowed:
            raise M.MsnError("BAD_ARGS", "Tham số không hỗ trợ: %r. %s" % (k, USAGE))
        if k in out:
            raise M.MsnError("BAD_ARGS", "Tham số %s ghi hai lần. %s" % (k, USAGE))
        out[k] = v.strip()
    return out


def parse_den(v):
    if v is None:
        return None
    d = M.parse_day(v) if M.ISO_RE.fullmatch(v) else None
    if d is None:
        raise M.MsnError("BAD_ARGS", "Ngày --den không hợp lệ: %r (cần YYYY-MM-DD). %s" % (v, USAGE))
    return d


def parse_ma(v):
    t = L.ticker(v)
    if not t:
        raise M.MsnError("BAD_ARGS", "Mã không hợp lệ: %r. %s" % (v, USAGE))
    return t


def run(argv):
    if len(argv) < 2:
        raise M.MsnError("BAD_ARGS", "Thiếu lệnh. " + USAGE)
    cmd = argv[1].strip().lower()
    if cmd not in FLAGS:
        raise M.MsnError("BAD_ARGS", "Lệnh không hỗ trợ: %r. %s" % (argv[1], USAGE))
    f = parse_flags(argv[2:], FLAGS[cmd])
    den = parse_den(f.get("--den"))
    if cmd == "nhom":
        return T.cmd_nhom()
    if cmd == "ma":
        if "--ma" not in f:
            raise M.MsnError("BAD_ARGS", "Lệnh ma cần --ma MÃ. " + USAGE)
        return T.cmd_ma(parse_ma(f["--ma"]), den)
    if "--nhom" in f and "--ma" in f:
        raise M.MsnError("BAD_ARGS", "Chỉ dùng một trong --nhom hoặc --ma. " + USAGE)
    if "--nhom" in f and not L.ID_RE.fullmatch(f["--nhom"]):
        raise M.MsnError("BAD_ARGS", "Mã nhóm không hợp lệ: %r (slug ASCII a-z0-9_). %s" % (f["--nhom"], USAGE))
    ma = parse_ma(f["--ma"]) if "--ma" in f else None
    return T.build_page(f.get("--nhom"), ma, den)


def main(argv=None):
    argv = sys.argv if argv is None else argv
    try:
        out = run(argv)
    except M.MsnError as exc:
        out = {"error": exc.message, "error_code": exc.code}
    except Exception as exc:  # never let a traceback replace the JSON envelope
        out = {"error": "Lỗi nội bộ chaebol_reflex.py: %s: %s" % (type(exc).__name__, exc), "error_code": "INTERNAL"}
    M.emit(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
