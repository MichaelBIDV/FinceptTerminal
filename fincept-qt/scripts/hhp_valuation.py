#!/usr/bin/env python3
"""
Fincept Terminal — ĐỊNH GIÁ HHP data service (phương pháp Huỳnh Hoàng Phương).

Feeds src/screens/hhp_valuation/HhpValuationPanel (+ HhpTickerDialog) through
EconomicsService / PythonRunner. Stdlib only; runs on Python 3.9+.

Method: P = E × P/E and P = BVPS × P/B; cheap/rich zones = mean ± 1σ / ± 2σ of the SAME
series' own history (index, basket or ticker — never versus sector or market).

This script does not fetch anything. It reshapes the JSON files the HHP pipeline rebuilds
3×/day (the same files behind the Cowork page hhp_vn100_valuation.html), restricted to the
VN30 and VN100 universes.

Data dir = env HHP_DATA_DIR, else ~/SECOND BRAIN-OBSIDIAN/_System/knowledge_os
(= /Users/macbook/SECOND BRAIN-OBSIDIAN/_System/knowledge_os on the author's machine):
    hhp_vn100_valuation.json   {meta, index, exvic3, by_ticker, hdcv_verdict}   REQUIRED
    hhp_baskets.json           {meta, baskets:[{code, label, pe, pb}]}          optional
    hhp_basket_members.json    {meta, members:{VN30:[...], VN100:[...]}}        optional
    hhp_hdcv_verdict.json      fallback when hdcv_verdict is absent above        optional
    hhp_vn100_series/<TK>.json {ticker, pe:{price, base, mean, sd, now, sigma, zone,
                                price_now, n, as_of}, pb, forward, meta}         per ticker
    hhp_keynotes.json          {meta, sources:[...], events:[...]} peak/trough keynotes,
                                hand-curated (schema hhp_keynotes/1)             optional
    hhp_forecast.json          {meta, sources, scopes} 3-year forecast written by
                                hhp_forecast_bridge.py (schema hhp_forecast/1)   optional
    hhp_forecast_tickers/<TK>.json  {meta, sources, anchor, pe, pb, skip, targets} per-ticker
                                3-year forecast (schema hhp_forecast_ticker/1), + _index.json
                                {generated, n_ok, n_skip, tickers, skipped:{TK: reason}}  optional
    hhp_keynotes_tickers/<TK>.json  per-ticker keynotes (schema hhp_keynotes/1, scopes [TK]),
                                written by hhp_keynotes_tickers.py               optional
    hhp_vnindex_history.json   {meta, base, price, gaps, pe, pb} VNINDEX full history 28/07/2000→
                                (schema hhp_vnindex_history/1), written by hhp_vnindex_history.py
                                (orchestrator step 1d); parsed only by `history`   optional

USAGE
    python3 hhp_valuation.py overview
    python3 hhp_valuation.py ticker <TK>        TK is upper-cased, must match ^[A-Z0-9]{2,6}$
    python3 hhp_valuation.py history            lazy: the VNINDEX TOÀN SỬ view fetches it when first opened

OUTPUT — exactly ONE compact JSON object on stdout (UTF-8, ensure_ascii=False). Non-finite
numbers (NaN / ±Infinity, which json.load accepts in the inputs) are emitted as null. The exit
code is 0 even on errors.

Errors:
    {"error": "<Vietnamese message incl. what to run>", "error_code": CODE}
    CODE ∈ NO_DATA (data dir / hhp_vn100_valuation.json missing or unreadable)
         | NO_SERIES (hhp_vn100_series/<TK>.json missing or unreadable)
         | BAD_ARGS (unknown command, missing/invalid ticker)
         | INTERNAL (unexpected exception — should not happen)

Zones: every block that carries the upstream Vietnamese "zone" label also gets "zone_key":
    "RẺ (<−1σ)" → "cheap", "TRUNG TÍNH" → "neutral", "ĐẮT (>+1σ)" → "rich"
    (unknown label → derived from sigma with the upstream rule σ<−1 cheap, σ>+1 rich;
     no label and no sigma → null). The original "zone" is kept.
Time series are [[epoch_ms, value], ...] in ascending time.

1) overview →
{
 "meta": {"generated": "2026-09-21 15:35 ICT", "expert": "Huỳnh Hoàng Phương", "method": str,
          "disclaimer": str, "sources": [str], "n_tickers": 194,
          "data_dir": str, "file_mtime": "2026-09-21T15:35:12+07:00", "age_hours": 6.9,
          "stale": bool (age_hours > 30), "baskets_generated": str|null,
          "members_generated": str|null,
          "web_url": "http://localhost:9000/sys/knowledge_os/hhp_vn100_valuation.html",
          "warnings": [str]  (missing optional files; rows whose price_src is not Vietcap — one line
                              naming them; dropped keynotes / forecast blocks with the reason;
                              [] when all good),
          "keynotes_file": {"mtime": ISO local, "n": kept events, "n_dropped": int} | null  (null = no file),
          "forecast_file": {"mtime": ISO local, "age_hours": float} | null                 (null = no file),
          "history_file": {"mtime": ISO local, "age_hours": float} | null   (hhp_vnindex_history.json; null = no
                          file. One stat, never parsed here and never warned — the panel re-fetches `history`
                          when it changes. The only overview key the full-history work adds),
          "prices": {"source": "vnstore vn_store.db (Vietcap vci_board / vci_history)",
                     "as_of": "2026-09-23", "n_vietcap": int, "n_fallback": int,
                     "fallback": [tk...]} | null   (upstream verbatim; null in files built before it),
          "capiq": {"file": basename, "exported": "2026-09-23 07:51 AM ET",
                    "exported_date": "2026-09-23", "n": int, "n_pe": int,
                    "source_dir": "Downloads"|"knowledge_os",
                    "source": str, "updated_at": ISO local,
                    "screens": {<slug> ("estimates"|"key_stats"|"multiples_capitalization"|"fundamental"|
                                        "stock_performance"|...):
                                {"exported_ict": "2026-09-23T18:51:15+07:00", "n": int, "file": basename}}
                    } | null  (upstream verbatim; null = no CapIQ export was read. source / updated_at /
                               screens come with the CIQ-overlay rebuild (ciq_feed/hhp_ciq_overlay.json,
                               one entry per CapIQ screen export) and are absent in older files;
                               exported_date / n / n_pe keep their meaning),
          ... every other upstream meta key passed through (forward, fails, zone_dist, ...)},
 "verdict": hdcv_verdict verbatim {"stance", "headline", "reads": [str], "risks": [str],
            "mode": "deterministic"|"brain", "updated", "by", "disclaimer", ...} | null,
 "index": {"pe": {"metric": "P/E", "now", "mean", "sd", "sigma", "zone", "zone_key",
                  "price_now", "as_of", "n_points",
                  "forward": {"date", "growth", "fair", "cheap1", "rich1", "rich2"} | null,
                  "chart": {"price", "fair", "cheap1", "cheap2", "rich1", "rich2"}} | null,
           "pb": same shape | null},
          (chart levels are index POINTS; the six arrays share one x-grid, ~1201 points)
 "exvic3": {"as_of", "pe_full_now", "pe_exv3_now", "pb_full_now", "pb_exv3_now", "w3_now",
            "exv3_pe_mean", "exv3_pe_sd", "exv3_pe_sigma", "exv3_pe_zone", "exv3_pe_zone_key",
            "vic3": [{"ticker", "mcap_kty", "mcap_src", "pe", "pb"}, ...],
                    (pe/pb = current finfo ratios; mcap_src names where mcap_kty came from)
            "series": {"pe_full", "pe_exv3", "pb_full", "pb_exv3", "w3"}} | null,
            (w3 = Vin-group weight, % of index market cap)
 "baskets": {"VN30": {"code", "label",
                      "pe": {"series": [[ms, v]...], "mean", "p1", "p2", "m1", "m2", "now",
                             "sigma", "zone", "zone_key", "as_of"} | null,
                      "pb": same | null} | null,
             "VN100": same | null} | null (null when hhp_baskets.json is missing),
            (p1/p2 = mean+1σ/+2σ, m1/m2 = mean−1σ/−2σ — flat levels)
 "members": {"VN30": [tk...], "VN100": [tk...]}   ([] when hhp_basket_members.json is missing),
 "missing": {"VN30": [tk...], "VN100": [tk...]}   (members with no entry in by_ticker),
 "zone_counts": {"VN30": {"pe": {"cheap", "neutral", "rich", "stale", "total"}, "pb": {...}},
                 "VN100": {...}}   (over that universe's rows having the metric block;
                                    total = number of such rows; a stale block counts in
                                    "stale" and total but in no zone),
 "rows": [ one per ticker of VN100 ∪ VN30 present in by_ticker — VN100 member order, then
           VN30 members not in VN100:
   {"tk": "FPT", "in_vn30": bool, "in_vn100": bool,
    "price_now": 72900 | null            (VND đồng, from by_ticker: Vietcap close/last),
    "price_date": "2026-09-23" | null,   (trading day of price_now)
    "price_time": "2026-09-23T15:14:27+07:00" | null   (board quote time; null for history closes),
    "price_src": "vietcap_board" | "vietcap_history" | "vnd_dchart" | "simplize_stale" | null
                                         (anything but vietcap_* is a fallback, listed in meta.warnings;
                                          null = file built before price_src existed),
    "eps", "bvps": đồng | null           (implied: price_now / pe.now, price_now / pb.now),
    "eps_src": "implied" | null,
    "capiq": {"pe", "pb" (fwd FY2026, x), "tp", "tp_med", "tp_high", "tp_low" (đồng),
              "tp_date": "2026-09-10", "n_tp": int, "rec": "Buy"|"Outperform"|"Hold"|..., "n_rec": int,
              "upside_pct": (tp / price_now − 1) × 100, "eps_est", "bvps_est" (đồng, FY+1),
              "roe_est", "eps_growth_1y" (%), "last_price" (CapIQ, đồng), "exported": "2026-09-23",
              "ttm": {"pe", "pb" (current, as CapIQ reports them, x),
                      "pe_ttm_est", "pb_fy0bv_est" (x; [EST] = derived upstream from CapIQ inputs —
                                                     P/E on EPS LTM, P/B on book value FY0 — not CapIQ figures),
                      "eps_ltm", "bvps_ltm" (đồng), "roe_fy0", "div_yield", "rev_g_ltm" (revenue growth
                      LTM), "npm_ltm" (net margin LTM) (% as CapIQ gives them), "mcap_b", "tev_b" (tỷ đồng),
                      "ev_ebitda_fwd" (x),
                      "asof": {<screen slug>: "2026-09-23"}  (ICT export day of each screen that fed ttm)}
                     (keys only when present; "ttm" itself is absent in files built before the
                      CIQ-overlay rebuild)}
             | null   (any field may be null; upstream verbatim, ttm included — non-finite → null),
    (the five keys price_date, price_time, price_src, eps_src, capiq are always present, null when
     the upstream row lacks them)
    "fa_rec": "MUA" | null, "fa_tp": 90600 | null,
    "fa_catalyst": {"rec", "tp", "upside", "consensus", "net_revisions", "n_reports",
                    "latest": {"title", "date", "source", "fact_type"} | null} | null,
    "forward": {"pe", "pb", "roe", "pe2", "tp", "rating", "analyst", "src": "vietcap"|"spg",
                "upside_pct"} | null,
    "pe": {"now", "mean", "sd", "min", "max", "sigma", "zone", "zone_key", "n",
           "reliable": bool, "band_cheap2", "band_cheap1", "band_fair", "band_rich1",
           "band_rich2" (all VND đồng), "upside_to_fair_pct",
           "as_of": "2026-09-18" | null  (last date of hhp_vn100_series/<TK>.json for that
                                          metric; null when the series file is absent),
           "stale": bool  (as_of more than STALE_SERIES_DAYS before the index as_of — the
                           ratio stopped updating upstream, e.g. KOS P/E ends 2021-11-30)} | null,
    "pb": same | null,
    "links": {"vietcap_iq": url, "miquant": url, "simplize": url},
    ... other upstream fields passed through (quality_val, ...); "sector" is stripped
        (it is null for every ticker upstream)} ],
 "keynotes": [ one per valid event of hhp_keynotes.json, sorted by date ascending ([] when the file is
               missing or unreadable — one meta warning):
   {"id": "2018-04-dinh" ([a-z0-9-], ≤40), "date": "2018-04-09", "ms": epoch ms of that date at UTC midnight,
    "kind": "dinh" | "day", "provisional": bool (event value, else detect.provisional, else false),
    "scopes": [⊂ "VNINDEX", "VN30", "VN100"],
    "priority": 1..3 (1 = labelled first; missing → terciles of detect.score, top third = 1; no score → 2),
    "nhan_phu" (≤22 chars), "title" (≤140), "boi_canh" (≤700), "nguyen_nhan" (≤700),
    "key_factors": [≤6 × ≤200], "sau_do" (≤400)   (longer text is cut with "…" and warned; absent → ""),
    "numbers": [{"k", "scope": str | null, "v", "unit": str | null, "sigma"?, "asof": str | null, "tier",
                 "method"? (EST without one is warned), "src_org", "src_date"}]
               (a number whose src id does not resolve, whose v is not finite or whose tier is unknown is dropped),
    "sources": [{"org", "title", "date", "url": str | null, "type": str | null, "tier", "domain": str | null}]
               (event "sources" refs, then claims[].src, then numbers[].src, resolved against the file's
                sources[] table; a source needs org + date),
    "tier": declared tier (missing → the lowest tier among its sources, warned),
    "tier_effective": tier, or "UNVERIFIED" when a load-bearing claim rests on news (type "news" / tier NEWS)
                      without ≥2 of its sources differing in BOTH org and web domain. Load-bearing = each
                      claims[] entry; with no claims[], the event's own non-"data" sources. Also UNVERIFIED
                      (warned) when no narrative source resolves: none of the event "sources" nor any
                      claims[].src is in the table (numbers[].src alone do not back bối cảnh/nguyên nhân),
    "warnings": [str] (the event's own warnings[] strings from the file first — ≤8, each ≤300 chars — then
                       the loader's)} ],
   Tier order: FACT-T1 > FACT-T2 > SS-T3 > EST > NEWS > UNVERIFIED.
   Dropped (counted in meta.keynotes_file.n_dropped, named in one meta warning): bad/missing id, date (or a
   future date), kind, scopes or title; no resolvable source; duplicate id; beyond the 60-event cap (lowest
   priority, then oldest, go first).
 "forecast": {
   "meta": {"generated", "age_hours" (file mtime), "horizon_months", "method", "caveats": [str],
            "warnings": [str] (the bridge's own notes, NOT copied into meta.warnings),
            "sources": [{"id", "org", "title", "date", "url" | "file", "tier", "definition"?}]
                       (entries lacking id / org / date / tier / url-or-file are dropped, warned)},
   "VNINDEX": {"pe": {"x0": anchor.ms, "points": {"fair", "cheap1", "cheap2", "rich1", "rich2": [[ms, v]]},
                      "base_path": [[ms, v]] | null, "growth": [{"year", "g", "tier", "est", "n", "W", "min",
                      "max", "simple_median", "flag", "sources": [...]}], "eps_pins": [...],
                      "milestones": [{"date", "ms", "base", "fair", ...}], "method", "caveats"} | null,
               "pb": same shape (+ "retention" when present; growth = book-value growth: n/W describe the BV
                     rule itself (1 / 0), "eps_n"/"eps_W" the EPS consensus it is derived from) | null,
               "targets": [{"id", "horizon", "ms", "value", "label",
                            "members": [{"org", "date", "value", "scenario", "url", "tier", "note"?}]}]},
   "VN30": {"pe": {"x0", "ratio_path": [[ms, v]], "flat": {"mean", "p1", "p2", "m1", "m2"}, "growth",
                   "milestones": [{"date", "ms", "ratio", "sigma", "zone" (null + "note" when the basket's σ is
                                   flagged unreliable upstream, e.g. VN100 P/B)}], "method", "caveats"} | null,
            "pb": same | null},
   "VN100": same as VN30
 } | null   (null when hhp_forecast.json is missing, unreadable or not schema hhp_forecast/1 — one meta warning)
   Checks (no numbers are made here — the bridge computes every point):
   * shape: every [[ms, v]] array holds 2–60 finite pairs, x strictly ascending and integral, first x ==
     anchor.ms; VNINDEX needs all five level arrays on one x-grid, each first value == anchor.<m>.last.<level>
     verbatim; baskets need ratio_path + flat; growth needs ≥1 entry with int year, finite g and a tier.
   * anchor, VNINDEX: anchor.as_of == index.<m>.as_of, anchor.<m>.mean/sd == index.<m>.mean/sd exactly and
     |anchor.<m>.last.fair − index.<m>.chart.fair[last finite]| ≤ 0.2 index points.
   * anchor, baskets: anchor.as_of == baskets.<U>.<m>.as_of and anchor.<m> + flat mean/p1/p2/m1/m2 equal it.
   A failing block becomes null + one meta warning. A block whose chart is not drawn at all (index.<m> null,
   hhp_baskets.json missing, basket code missing — the last two already warned) is null without a new
   warning; a basket that exists but lacks that metric is warned. A file older than 30 h is warned only; the
   anchor check decides. Targets show without the pe/pb blocks
   (index points on both charts); a member lacking org, date, finite value, url or tier FACT-T1|FACT-T2|SS-T3
   is dropped (warned) and the marker's value/label are re-taken from the remaining members (value = their
   median, so it traces to every member shown); a target with no valid member is dropped whole.
}

2) ticker <TK> →
{"ticker": "FPT", "generated": "2026-09-21 15:37 ICT" | null, "unit": "nghìn đồng",
 "pe": {"now", "mean", "sd", "sigma", "zone", "zone_key",
        "price_now": 65.2 (NGHÌN đồng), "as_of", "n",
        "chart": {"price": [[ms, v]], "fair": [[ms, v]], "cheap1", "cheap2", "rich1",
                  "rich2"}} | null,
 "pb": same | null,
 "forward": {"pe": {"2026F": 11.0, "2027F": 9.51}, "pb": {...}, "roe": {...},
             "tp": 82100.0 (đồng), "rating", "analyst",
             "src": {"pe2026": "vietcap"|"spg", ...}, "note": str,
             "capiq": the row's capiq block | null}
            | {"capiq": {...}}  (series file has no forward but the row has a capiq block)
            | null              (neither),
 "row": the overview row for this ticker | null (null when absent from by_ticker),
 "forecast": {
   "meta": {"generated", "age_hours" (file mtime), "horizon_months", "unit" (chart units, verbatim), "method",
            "caveats": [str], "warnings": [str] (the bridge's own notes, NOT copied into meta.warnings),
            "price_scale": {"scale", "series" (last adjusted price, nghìn đồng), "actual_vnd" (actual price, đồng),
                            "date", "src"} | null   (where every target's scale comes from; verbatim, null without
                                                     a finite scale > 0),
            "sources": [{"id", "org", "title", "date", "url" | "file", "tier"}]
                       (entries lacking id / org / date / tier / url-or-file are dropped, warned)},
   "pe": {"x0": anchor(.pe).ms, "points": {"fair", "cheap1", "cheap2", "rich1", "rich2": [[ms, v]] × 37} (nghìn đồng,
          the series' adjusted scale), "base_path": [[ms, EPS]] × ≤60 | null (dropped alone, warned),
          "growth": [{"year", "g", "tier", "est", "n", "W", "min", "max", "flag",
                      "sources": [{"id", "org", "value", "weight", "date", "tier", "url" | "file", "note"?}]}],
          "eps_pins": [{"year", "date", "ms", "value", "tier", "method"}],
          "milestones": [{"date", "ms", "base", "fair", "cheap1", "cheap2", "rich1", "rich2"}],
          "reliable": bool | null (false = σ/μ ≥ 0,6 — drawn, but the UI warns), "method", "caveats"} | null,
   "pb": same shape (growth = BVPS growth; + "retention": {"r", "per_year", "fallback"} when present) | null,
   "skip": {"pe": str | null, "pb": str | null}   (why that block is null: the bridge's own reason verbatim, else
                                                    the reason it was dropped here — that one is also in meta.warnings),
   "targets": [{"id", "org", "date", "horizon", "ms", "value" (chart units = value_vnd / 1000 × scale), "value_vnd"
                (đồng), "scale", "rating"?, "n_analysts"?, "url" | "file", "tier", "label"}]
              (one ◆ per source, sorted by ms. A target lacking org, date, integral ms, finite value / value_vnd,
               scale > 0, url or file, or tier FACT-T1|FACT-T2|SS-T3 — or whose value is more than 1% off
               value_vnd / 1000 × scale, or whose ms is not after anchor.ms — is dropped alone, warned)
 } | null   (null when hhp_forecast_tickers/<TK>.json is missing — warned, quoting the bridge's reason when
             _index.json lists the ticker as skipped — unreadable, not schema hhp_forecast_ticker/1, or for another
             ticker; one meta warning each)
   Checks per metric (no numbers are made here — the bridge computes every point):
   * anchor (anchor.<m>.as_of / .ms override anchor.as_of / .ms when present — P/E and P/B may end on different
     days): anchor.as_of == the series' <m>.as_of, anchor.<m>.mean/sd == the series' mean/sd exactly and
     |anchor.<m>.last.fair − <m>.chart.fair[last finite]| ≤ 0.011 nghìn đồng (both rounded to 2 decimals);
   * shape: the five level arrays hold exactly 37 finite [ms, v] pairs (36 months + the anchor), x strictly
     ascending and integral, one x-grid, first x == anchor.ms, each first value == anchor.<m>.last.<level> verbatim;
     growth needs ≥1 entry with int year, finite g and a tier.
   A failing block becomes null + one meta warning (a block for a metric the series lacks too). A file older than
   30 h is warned only; the anchor check decides.
 "keynotes": [same shape as the overview keynotes] from hhp_keynotes_tickers/<TK>.json, same validation with
             scopes ⊂ {TK, VNINDEX, VN30, VN100} — the ticker keynote builder writes scopes [TK] and adds VNINDEX-scoped
             numbers as market context  ([] without a warning when the file does not exist),
 "meta": {"forecast_file": {"mtime": ISO local, "age_hours": float} | null   (null = no file),
          "keynotes_file": {"mtime": ISO local, "n": kept events, "n_dropped": int} | null   (null = no file),
          "warnings": [str]}}

 Band levels: level_k[i] = max(0, round(base[i] * k, 2)) with k ∈ {mean, mean−sd, mean−2sd,
 mean+sd, mean+2sd} → fair, cheap1, cheap2, rich1, rich2 (base = EPS or BVPS in nghìn đồng,
 the series' "base"). price and base are joined on timestamp; points whose price or base is
 null / non-finite are dropped, so all six arrays share one x-grid. If mean (or sd) is not
 finite the dependent level arrays are [].

 Known upstream inconsistency, deliberately NOT reconciled here: the series price is
 VnDirect DCHART adjusted close in nghìn đồng (FPT 65.2) while the overview row price_now
 is the unadjusted Vietcap close/last in đồng (FPT 72,900; see price_src / price_date).
 Label units and sources on screen.

3) history →   VNINDEX TOÀN SỬ 28/07/2000→ (hhp_vnindex_history.json checked and passed through; nothing computed)
{"meta": {"history_file": {"mtime": ISO local, "age_hours": float} | null   (null = no file),
          "keynotes_file": {"mtime", "n", "n_dropped"} | null   (as in the overview),
          "warnings": [str]},
 "history": {
   "meta": the file's meta verbatim {"schema": "hhp_vnindex_history/1", "generated", "engine_as_of": {"pe", "pb"},
            "inputs": {engine, static, vnstore, vietcap_cache, forecast, keynotes}, "method", "caveats",
            "warnings" (the builder's own notes, NOT copied into meta.warnings above), "sources"},
   "base": {"date", "value", "tier", "src", "conflict"} (verbatim),
   "price": {"points": [[ms, close]] (2–2.400 pairs), "n_daily", "first_date", "last_date",
             "src_spans": [{"from", "to", "src", "tier", "n"}], "level_x_base"} (verbatim after the shape check),
   "gaps": [{...}]   (verbatim; empty by design — any entry is also one meta warning),
   "pe": {"long_from": "2011-01-04" (the file's long.from, kept even when long is nulled below — titles and notes
                      read their dates from the payload),
          "long": {"from", "to", "n_weeks", "mean", "sd", "now", "sigma", "zone", "zone_key", "pct", "method", "tier",
                   "vendor_published"} | null,
          "eight": {"from", "mean", "sd", "sigma", "zone", "zone_key", "pct", "pct_method", "check"} | null,
          "windows_agree": bool | null   (null unless both windows are shown and it matches their zone_key),
          "seam": {"date", "grid_date", "rule", "overlap_n", "median", "p10", "p90", "by_year", "jump_pct",
                   "vendor_own_move_pct", "excess_pp"} | null (verbatim),
          "chart": {"fair", "cheap1", "cheap2", "rich1", "rich2": [[ms, v]]}   (index points, long-window bands),
          "points": [◇ {"id", "date", "date_note"?, "ms", "v", "value_kind": "point" | "approx" | "lower_bound",
                        "period": {"from", "to"} | null, "basis", "definition", "tier",
                        "src": {"org", "title", "date", "url"?, "file"?, "loc"?}, "note", "close" (marker y),
                        "vs_long_mean": "above" | "below" | null (colour only; null for lower_bound),
                        "also": [{"v", "value_kind", "basis", "tier", "src", "date"}]}]   (never a σ),
          "forecast": {"x0", "source_generated", "points": {five levels: [[ms, v]]}, "milestones", "method",
                       "caveats"} | null,
          ...any other key of the file's block verbatim, except "keynote_readings" (merged into keynotes below)
         } | null   (null = no long band: block missing, long.from missing, or a chart shape error — warned),
   "pb": same shape | null,
   "keynotes": [the overview keynotes whose scopes include VNINDEX, with
                "numbers": only scope VNINDEX / unscoped numbers (the VNINDEX card shows no other), each WITHOUT
                           "sigma" (pe/pb there carry the engine 12/2017→ or Vietcap 2009→ scale; value and method
                           kept; a k "sigma" number is dropped), then history.<m>.keynote_readings[id] appended:
                           {"k": m, "scope": "VNINDEX", "v", "unit", "asof", "tier", "src_org",
                            "src_date" (a source date, or the builder's run stamp "YYYY-MM-DD HH:MM ICT"),
                            "sigma"? (the long window's, readings dated on/after long.from only), "method"?}
                           — so every σ on the full-history chart is on the long scale,
                "priority_full": 1..3 (the raw file's priority_full, else priority) — label priority on this chart]
 } | null
   history is null (one meta warning, exit 0, never an error envelope) when the file is missing ("Chưa có
   hhp_vnindex_history.json — chạy bước 1d orchestrator_hhp.sh (python3 hhp_vnindex_history.py)"), unreadable, not
   schema hhp_vnindex_history/1, built without the static file (meta.inputs.static not {file, …}), or when
   price.points is not 2–2.400 [ms, close] pairs with integral ms strictly ascending and close finite > 0.
   hhp_vn100_valuation.json missing → the NO_DATA envelope, as for the other commands.
   Checks per metric (warned; the rest of the payload is kept):
   * shape → metric null: long.from a YYYY-MM-DD date; the five chart arrays 2–2.300 pairs each, integral ms strictly
     ascending, v finite ≥ 0, one x-grid, first x ≥ long.from.
   * long needs finite mean / sd > 0 / now / sigma, eight finite mean / sd > 0 / sigma — else that window is null.
   * anchor → long, eight, windows_agree and forecast null (bands kept — history hardly moves): meta.engine_as_of.<m>
     == hhp_vn100_valuation.json index.<m>.as_of, eight.mean / eight.sd == index.<m>.mean / sd and long.now ==
     index.<m>.now exactly (verbatim copies made in the same orchestrator run). Warning "Toàn sử P/E lệch neo engine
     (dd/mm vs dd/mm) — chờ lượt orchestrator kế".
   * forecast → null + warning unless it sits on the current hhp_forecast.json: its scopes.VNINDEX.anchor passes the
     overview's VNINDEX anchor check (as_of, mean, sd, last fair) and anchor.ms == the engine chart's last x; x0 ==
     anchor.ms; source_generated == its meta.generated; five level arrays of 2–60 pairs on one x-grid == its
     scopes.VNINDEX.<m>.base_path x-grid; each level's first point == chart.<level>[-1] verbatim.
   * points[] (◇) → a member is dropped alone (one warning) when it lacks a YYYY-MM-DD date before long.from, a finite
     v, a tier other than UNVERIFIED, a src with org + date, a known value_kind or a close > 0; bad also[] members
     likewise. σ is never passed.
   * keynote_readings → an entry is dropped (one warning) without k == the metric, scope VNINDEX, a finite v, a tier
     other than UNVERIFIED, src_org and src_date; σ on a reading dated before long.from is stripped; ≤ 8 per event;
     readings for ids absent from hhp_keynotes.json are warned.
   A file older than 30 h is warned only.
"""

import json
import math
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

ICT = timezone(timedelta(hours=7), "ICT")
DEFAULT_DATA_DIR = os.path.join(os.path.expanduser("~"), "SECOND BRAIN-OBSIDIAN", "_System", "knowledge_os")
WEB_URL = "http://localhost:9000/sys/knowledge_os/hhp_vn100_valuation.html"

CORE_FILE = "hhp_vn100_valuation.json"
BASKETS_FILE = "hhp_baskets.json"
MEMBERS_FILE = "hhp_basket_members.json"
VERDICT_FILE = "hhp_hdcv_verdict.json"
SERIES_DIR = "hhp_vn100_series"

UNIVERSES = ("VN30", "VN100")
METRICS = ("pe", "pb")
ZONE_KEYS = ("cheap", "neutral", "rich")
STALE_HOURS = 30.0
STALE_SERIES_DAYS = 30  # a ticker ratio this far behind the index as_of is not "current"
TICKER_RE = re.compile(r"[A-Z0-9]{2,6}")
ROW_PRICE_KEYS = ("price_date", "price_time", "price_src", "eps_src", "capiq")  # always present in a row
VIETCAP_PRICE_SRCS = ("vietcap_board", "vietcap_history")  # any other price_src is a fallback
MAX_LISTED = 12  # tickers named in one warning line

RUN_CORE = "Chạy: python3 hhp_vn100_valuation.py (thư mục knowledge_os)"
RUN_SERIES = "Chạy: python3 hhp_vn100_series.py (thư mục knowledge_os)"
RUN_BASKETS = "Chạy: python3 hhp_index_baskets.py (thư mục knowledge_os)"
RUN_FORECAST = "Chạy: python3 hhp_forecast_bridge.py (thư mục knowledge_os)"
RUN_KEYNOTES = "Kiểm: python3 hhp_keynotes_check.py (thư mục knowledge_os)"
USAGE = "Dùng: hhp_valuation.py overview | hhp_valuation.py ticker <MÃ> | hhp_valuation.py history"

KEYNOTES_FILE = "hhp_keynotes.json"
FORECAST_FILE = "hhp_forecast.json"
FORECAST_SCHEMA = "hhp_forecast/1"
KEYNOTE_SCOPES = ("VNINDEX", "VN30", "VN100")
TIERS = ("FACT-T1", "FACT-T2", "SS-T3", "EST", "NEWS", "UNVERIFIED")  # best → worst
TARGET_TIERS = ("FACT-T1", "FACT-T2", "SS-T3")
KEYNOTE_ID_RE = re.compile(r"[a-z0-9-]{1,40}")
DAY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
SOURCE_DATE_RE = re.compile(r"\d{4}(?:-\d{2}(?:-\d{2})?)?")  # sources may be dated to the month or year
READING_DATE_RE = re.compile(r"\d{4}(?:-\d{2}(?:-\d{2}(?: \d{2}:\d{2}(?: ICT)?)?)?)?")  # + a run stamp "… 10:20 ICT"
MAX_KEYNOTES = 60
KEYNOTE_TEXT = (("nhan_phu", 22), ("title", 140), ("boi_canh", 700), ("nguyen_nhan", 700), ("sau_do", 400))
MAX_FACTORS, FACTOR_LEN = 6, 200
MAX_NUMBERS, MAX_EVENT_SOURCES, SOURCE_TEXT_LEN, SHORT_LEN = 24, 12, 300, 60
MAX_RAW_WARNINGS = 8  # an event's own warnings[] strings carried into the payload (each ≤ SOURCE_TEXT_LEN)
FC_LEVELS = ("fair", "cheap1", "cheap2", "rich1", "rich2")
FC_FLAT = ("mean", "p1", "p2", "m1", "m2")
FC_MIN_POINTS, FC_MAX_POINTS = 2, 60
FC_FAIR_TOLERANCE = 0.2  # index points between anchor.last.fair and the engine chart's last fair
METRIC_LABEL = {"pe": "P/E", "pb": "P/B"}

TICKER_FC_DIR = "hhp_forecast_tickers"
TICKER_FC_INDEX = "_index.json"
TICKER_FC_SCHEMA = "hhp_forecast_ticker/1"
TICKER_KN_DIR = "hhp_keynotes_tickers"
TICKER_FC_POINTS = 37              # 36 monthly steps + the anchor point
TICKER_FAIR_TOLERANCE = 0.011      # nghìn đồng: both fair values are rounded to 2 decimals
TARGET_SCALE_TOLERANCE = 0.01      # |value − value_vnd/1000·scale| ≤ 1% of value (catches đồng vs nghìn mix-ups)
TICKER_TARGET_KEYS = ("id", "org", "date", "horizon", "ms", "value", "value_vnd", "scale", "rating", "n_analysts",
                      "url", "file", "tier", "label", "note")
RUN_FORECAST_TICKERS = "Chạy: bước 1b orchestrator_hhp.sh (dự phóng từng mã, thư mục knowledge_os)"
RUN_KEYNOTES_TICKERS = "Chạy: python3 hhp_keynotes_tickers.py --tickers %s (thư mục knowledge_os)"

HISTORY_FILE = "hhp_vnindex_history.json"
HISTORY_SCHEMA = "hhp_vnindex_history/1"
RUN_HISTORY = "chạy bước 1d orchestrator_hhp.sh (python3 hhp_vnindex_history.py)"
HIST_MIN_POINTS, HIST_PRICE_MAX, HIST_CHART_MAX = 2, 2400, 2300
HIST_POINT_KINDS = ("point", "approx", "lower_bound")
HIST_VS_MEAN = ("above", "below")
HIST_TEXT_LEN = 700          # definition / note of a ◇ point
MAX_READINGS = 8             # history readings appended to one keynote, per metric
# D7 in the keynote free text: a signed σ ("+0,9σ", "−2,4σ") is an engine 12/2017→ / Vietcap 2009→ reading, not the
# long window's. history → its direction vs that scale's mean; the "thang …" qualifier stays (added when absent).
HIST_SIGMA_RE = re.compile(r"(?<![\w.,+−\-±])([+−\-±]?)(\d+(?:[.,]\d+)?)\s?σ(?!\w)")
HIST_SCALE_NEXT = re.compile(r"\s*[,;(]?\s*thang\b")
HIST_SIGMA_LABEL_RE = re.compile(HIST_SIGMA_RE.pattern + r"(?:\s*\(\s*thang[^()]*\)|,\s*thang[^,;()]*)?")
HIST_TEXT_SCALE = "thang engine 12/2017→"   # the VNINDEX text convention (fcview: "trừ khi ghi khác")

_ZONE_LABELS = {
    "RẺ (<−1σ)": "cheap",
    "TRUNG TÍNH": "neutral",
    "ĐẮT (>+1σ)": "rich",
}


class HhpError(Exception):
    """A user-facing failure, emitted as {"error": message, "error_code": code}."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# ── Generic helpers ──────────────────────────────────────────────────────────


def finite(v):
    """Number → float if finite, else None (bools are not numbers here)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def clean(obj):
    """Deep copy with every non-finite float replaced by None (strict JSON)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    return obj


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_optional(path, what, warnings):
    """Optional input: None (+ a warning) when missing or unreadable."""
    if not os.path.isfile(path):
        warnings.append("Thiếu %s — %s" % (what, RUN_BASKETS))
        return None
    try:
        return load_json(path)
    except (OSError, ValueError) as exc:
        warnings.append("Không đọc được %s (%s) — %s" % (what, exc, RUN_BASKETS))
        return None


def data_dir():
    env = os.environ.get("HHP_DATA_DIR", "").strip()
    return os.path.expanduser(env) if env else DEFAULT_DATA_DIR


def zone_key(label, sigma=None):
    """Upstream Vietnamese zone label → cheap | neutral | rich (sigma fallback, else None)."""
    if isinstance(label, str):
        norm = unicodedata.normalize("NFC", label).strip()
        if norm in _ZONE_LABELS:
            return _ZONE_LABELS[norm]
        up = norm.upper()
        if up.startswith("RẺ"):
            return "cheap"
        if up.startswith(("ĐẮT", "MẮC")):
            return "rich"
        if up.startswith("TRUNG"):
            return "neutral"
    s = finite(sigma)
    if s is None:
        return None
    if s < -1:
        return "cheap"
    if s > 1:
        return "rich"
    return "neutral"


def with_zone_key(block):
    """Copy of a metric block with "zone_key" added; non-dict → None."""
    if not isinstance(block, dict):
        return None
    return {**block, "zone_key": zone_key(block.get("zone"), block.get("sigma"))}


def ts_value(pair):
    """[epoch_ms, value] → (int ms, float value) or None when either part is unusable."""
    if not isinstance(pair, (list, tuple)) or len(pair) < 2:
        return None
    ts, v = finite(pair[0]), finite(pair[1])
    if ts is None or v is None:
        return None
    return int(ts), v


# ── Loading ──────────────────────────────────────────────────────────────────


def load_core(ddir):
    if not os.path.isdir(ddir):
        raise HhpError("NO_DATA", "Không tìm thấy thư mục dữ liệu HHP: %s (đặt HHP_DATA_DIR nếu dữ liệu nằm chỗ "
                                  "khác). %s" % (ddir, RUN_CORE))
    path = os.path.join(ddir, CORE_FILE)
    if not os.path.isfile(path):
        raise HhpError("NO_DATA", "Chưa có %s trong %s. %s" % (CORE_FILE, ddir, RUN_CORE))
    try:
        core = load_json(path)
    except (OSError, ValueError) as exc:
        raise HhpError("NO_DATA", "Không đọc được %s (%s). %s" % (CORE_FILE, exc, RUN_CORE))
    if not isinstance(core, dict):
        raise HhpError("NO_DATA", "%s sai định dạng (không phải JSON object). %s" % (CORE_FILE, RUN_CORE))
    return core, path


def load_members(ddir, warnings):
    raw = load_optional(os.path.join(ddir, MEMBERS_FILE), MEMBERS_FILE, warnings)
    src = raw.get("members") if isinstance(raw, dict) else None
    if not isinstance(src, dict):
        src = None
    members = {}
    for u in UNIVERSES:
        seen, out = set(), []
        lst = (src or {}).get(u)
        for tk in lst if isinstance(lst, list) else []:
            if isinstance(tk, str):
                t = tk.strip().upper()
                if t and t not in seen:
                    seen.add(t)
                    out.append(t)
        members[u] = out
    if isinstance(raw, dict) and src is not None:
        for u in UNIVERSES:
            if not members[u]:
                warnings.append("%s không có danh sách rổ %s — %s" % (MEMBERS_FILE, u, RUN_BASKETS))
    generated = (raw.get("meta") or {}).get("generated") if isinstance(raw, dict) else None
    return members, generated


def load_baskets(ddir, warnings):
    raw = load_optional(os.path.join(ddir, BASKETS_FILE), BASKETS_FILE, warnings)
    if not isinstance(raw, dict):
        return None, None
    by_code = {}
    for b in raw.get("baskets") or []:
        if isinstance(b, dict) and isinstance(b.get("code"), str):
            by_code[b["code"].strip().upper()] = b
    out = {}
    for u in UNIVERSES:
        b = by_code.get(u)
        if b is None:
            warnings.append("%s không có rổ %s — %s" % (BASKETS_FILE, u, RUN_BASKETS))
            out[u] = None
            continue
        out[u] = {**b, "pe": with_zone_key(b.get("pe")), "pb": with_zone_key(b.get("pb"))}
    generated = (raw.get("meta") or {}).get("generated")
    return out, generated


def load_verdict(core, ddir):
    v = core.get("hdcv_verdict")
    if isinstance(v, dict) and v:
        return v
    path = os.path.join(ddir, VERDICT_FILE)
    if os.path.isfile(path):
        try:
            v = load_json(path)
        except (OSError, ValueError):
            return None
        return v if isinstance(v, dict) and v else None
    return None


# ── Overview ─────────────────────────────────────────────────────────────────


def parse_day(value):
    """"2026-09-18…" → date, else None."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def reference_day(core):
    """The market's "today" for staleness: latest index as_of, else the core file's generated date."""
    index_src = core.get("index") if isinstance(core.get("index"), dict) else {}
    days = [parse_day((index_src.get(m) or {}).get("as_of")) for m in METRICS if isinstance(index_src.get(m), dict)]
    days = [d for d in days if d is not None]
    if days:
        return max(days)
    meta = core.get("meta") if isinstance(core.get("meta"), dict) else {}
    return parse_day(meta.get("generated"))


def series_as_of(series):
    """{metric: as_of str} from a parsed hhp_vn100_series/<TK>.json (metrics without a date omitted)."""
    out = {}
    if isinstance(series, dict):
        for m in METRICS:
            blk = series.get(m)
            if isinstance(blk, dict) and parse_day(blk.get("as_of")) is not None:
                out[m] = blk["as_of"]
    return out


def read_series_as_of(ddir, tk):
    try:
        return series_as_of(load_json(os.path.join(ddir, SERIES_DIR, tk + ".json")))
    except (OSError, ValueError):
        return {}


def build_row(tk, entry, vn30, vn100, as_of_by_metric, ref_day):
    row = {"tk": tk, "in_vn30": tk in vn30, "in_vn100": tk in vn100}
    for k, v in entry.items():
        if k in ("sector", "tk", "in_vn30", "in_vn100"):
            continue
        row[k] = v
    for k in ROW_PRICE_KEYS:
        row.setdefault(k, None)
    for m in METRICS:
        blk = with_zone_key(entry.get(m))
        if blk is not None:
            as_of = as_of_by_metric.get(m) or (blk.get("as_of") if parse_day(blk.get("as_of")) else None)
            day = parse_day(as_of)
            blk["as_of"] = as_of
            blk["stale"] = bool(day and ref_day and (ref_day - day).days > STALE_SERIES_DAYS)
        row[m] = blk
    return row


def universe_order(members):
    order, seen = [], set()
    for u in ("VN100", "VN30"):
        for tk in members[u]:
            if tk not in seen:
                seen.add(tk)
                order.append(tk)
    return order


def zone_counts(rows):
    out = {}
    for u in UNIVERSES:
        flag = "in_" + u.lower()
        per_metric = {}
        for m in METRICS:
            c = {k: 0 for k in ZONE_KEYS}
            stale = total = 0
            for r in rows:
                blk = r.get(m)
                if not r.get(flag) or not isinstance(blk, dict):
                    continue
                total += 1
                if blk.get("stale"):
                    stale += 1
                elif blk.get("zone_key") in c:
                    c[blk["zone_key"]] += 1
            c["stale"] = stale
            c["total"] = total
            per_metric[m] = c
        out[u] = per_metric
    return out


def file_meta(path):
    mtime = os.path.getmtime(path)
    age = max(0.0, (time.time() - mtime) / 3600.0)
    return {
        "file_mtime": datetime.fromtimestamp(mtime, tz=ICT).isoformat(timespec="seconds"),
        "age_hours": round(age, 1),
        "stale": age > STALE_HOURS,
    }


def build_overview(ddir):
    core, core_path = load_core(ddir)
    warnings = []
    by_ticker = core.get("by_ticker")
    if not isinstance(by_ticker, dict):
        by_ticker = {}
        warnings.append("%s không có by_ticker — %s" % (CORE_FILE, RUN_CORE))
    members, members_generated = load_members(ddir, warnings)
    baskets, baskets_generated = load_baskets(ddir, warnings)

    vn30, vn100 = set(members["VN30"]), set(members["VN100"])
    ref_day = reference_day(core)
    rows = [build_row(tk, by_ticker[tk], vn30, vn100, read_series_as_of(ddir, tk), ref_day)
            for tk in universe_order(members) if isinstance(by_ticker.get(tk), dict)]
    missing = {u: [tk for tk in members[u] if not isinstance(by_ticker.get(tk), dict)] for u in UNIVERSES}
    fallback = ["%s (%s)" % (r["tk"], r["price_src"]) for r in rows
                if isinstance(r["price_src"], str) and r["price_src"] not in VIETCAP_PRICE_SRCS]
    if fallback:
        listed = ", ".join(fallback[:MAX_LISTED]) + (", …" if len(fallback) > MAX_LISTED else "")
        warnings.append("Giá hiện tại của %d mã không lấy được từ Vietcap, đang dùng nguồn dự phòng: %s — %s"
                        % (len(fallback), listed, RUN_CORE))

    src_meta = core.get("meta") if isinstance(core.get("meta"), dict) else {}
    meta = {
        **src_meta,
        "generated": src_meta.get("generated"),
        "expert": src_meta.get("expert") or "Huỳnh Hoàng Phương",
        "method": src_meta.get("method"),
        "disclaimer": src_meta.get("disclaimer"),
        "sources": src_meta.get("sources") or [],
        "n_tickers": src_meta.get("n_tickers", len(by_ticker)),
        "prices": src_meta.get("prices") if isinstance(src_meta.get("prices"), dict) else None,
        "capiq": src_meta.get("capiq") if isinstance(src_meta.get("capiq"), dict) else None,
        "data_dir": ddir,
        **file_meta(core_path),
        "baskets_generated": baskets_generated,
        "members_generated": members_generated,
        "web_url": WEB_URL,
        "warnings": warnings,
    }

    index_src = core.get("index") if isinstance(core.get("index"), dict) else {}
    index = {m: with_zone_key(index_src.get(m)) for m in METRICS}
    ex = core.get("exvic3")
    exvic3 = None
    if isinstance(ex, dict):
        exvic3 = {**ex, "exv3_pe_zone_key": zone_key(ex.get("exv3_pe_zone"), ex.get("exv3_pe_sigma"))}
    keynotes, meta["keynotes_file"] = load_keynotes(ddir, warnings)
    forecast, meta["forecast_file"] = load_forecast(ddir, index, baskets, warnings)
    meta["history_file"] = history_file_meta(ddir)

    return {
        "meta": meta,
        "verdict": load_verdict(core, ddir),
        "index": index,
        "exvic3": exvic3,
        "baskets": baskets,
        "members": members,
        "missing": missing,
        "zone_counts": zone_counts(rows),
        "rows": rows,
        "keynotes": keynotes,
        "forecast": forecast,
    }


# ── Keynotes (hhp_keynotes.json, hand-curated) ───────────────────────────────


def as_list(value):
    return value if isinstance(value, list) else []


def text(value, limit, field=None, cut=None):
    """Stripped string cut to `limit` chars with "…" (field name appended to `cut`); non-str → ""."""
    if not isinstance(value, str):
        return ""
    s = value.strip()
    if len(s) > limit:
        if cut is not None and field:
            cut.append(field)
        s = s[: limit - 1].rstrip() + "…"
    return s


def norm_tier(value):
    t = value.strip().upper() if isinstance(value, str) else None
    return t if t in TIERS else None


def lowest_tier(tiers):
    ranks = [TIERS.index(t) for t in tiers if t in TIERS]
    return TIERS[max(ranks)] if ranks else "UNVERIFIED"


def url_domain(url):
    """"https://www.cafef.vn/x" → "cafef.vn"; None when there is no usable host."""
    try:
        host = urlsplit(url).hostname if isinstance(url, str) else None
    except ValueError:
        return None
    if not host:
        return None
    host = host.lower()
    return host[4:] if host.startswith("www.") else host


def keynote_source(raw):
    """Raw source → {org, title, date, url, type, tier, domain}; None without an org and a date."""
    if not isinstance(raw, dict):
        return None
    org, date = text(raw.get("org"), SOURCE_TEXT_LEN), raw.get("date")
    if not org or not isinstance(date, str) or not SOURCE_DATE_RE.fullmatch(date.strip()):
        return None
    url = raw.get("url").strip() if isinstance(raw.get("url"), str) and raw.get("url").strip() else None
    kind = raw.get("type").strip().lower() if isinstance(raw.get("type"), str) and raw.get("type").strip() else None
    return {"org": org, "title": text(raw.get("title"), SOURCE_TEXT_LEN), "date": date.strip(), "url": url,
            "type": kind, "tier": norm_tier(raw.get("tier")) or "UNVERIFIED", "domain": url_domain(url)}


def source_table(raw):
    """Global sources[] → {id: normalized source} (entries without id / org / date are skipped)."""
    table = {}
    for s in as_list(raw):
        src = keynote_source(s)
        if src is not None and isinstance(s.get("id"), str) and s["id"].strip():
            table.setdefault(s["id"].strip(), src)
    return table


class _SourceRefs:
    """Resolves one event's source references (ids into the global table, or inline objects)."""

    def __init__(self, table):
        self.table, self.ordered, self.unknown = table, [], []

    def one(self, ref):
        if isinstance(ref, dict) and isinstance(ref.get("id"), str) and ref["id"].strip() in self.table:
            ref = ref["id"]
        sid = ref.strip() if isinstance(ref, str) else None
        if sid is not None:
            src = self.table.get(sid)
        else:  # inline object; an id that is neither in the table nor a full source is "unknown"
            src = keynote_source(ref)
            if src is None and isinstance(ref, dict) and isinstance(ref.get("id"), str):
                sid = ref["id"].strip()
        if src is None and sid and sid not in self.unknown:
            self.unknown.append(sid)
        if src is not None and src not in self.ordered:
            self.ordered.append(src)
        return src

    def many(self, refs):
        refs = refs if isinstance(refs, list) else [refs]
        return [s for s in (self.one(r) for r in refs if r is not None) if s is not None]


def is_news(src):
    return src["type"] == "news" or src["tier"] == "NEWS"


def corroborated(sources):
    """True when two of `sources` differ in BOTH org and web domain."""
    for i, a in enumerate(sources):
        for b in sources[i + 1:]:
            if (a["domain"] and b["domain"] and a["domain"] != b["domain"]
                    and a["org"].casefold() != b["org"].casefold()):
                return True
    return False


def news_rule_ok(claims, narrative):
    """DESIGN §1.1 news rule. claims = [(sources, rests_on_news)], each checked on its own; with no claims
    the event's own non-"data" sources are the one load-bearing set."""
    if claims:
        return all(corroborated(srcs) for srcs, on_news in claims if on_news)
    srcs = [s for s in narrative if s["type"] != "data"]
    return not any(is_news(s) for s in srcs) or corroborated(srcs)


def keynote_number(raw, refs, scopes=KEYNOTE_SCOPES):
    """One numbers[] entry → output dict, or None without k / finite v / known tier / resolvable src."""
    if not isinstance(raw, dict) or not isinstance(raw.get("k"), str) or not raw["k"].strip():
        return None
    v, tier = finite(raw.get("v")), norm_tier(raw.get("tier"))
    src = refs.one(raw.get("src")) if raw.get("src") is not None else None
    scope = raw.get("scope").strip().upper() if isinstance(raw.get("scope"), str) else None
    if v is None or tier is None or src is None or (scope is not None and scope not in scopes):
        return None
    out = {"k": text(raw["k"], SHORT_LEN), "scope": scope, "v": v, "unit": text(raw.get("unit"), SHORT_LEN) or None,
           "asof": raw.get("asof") if parse_day(raw.get("asof")) else None, "tier": tier,
           "src_org": src["org"], "src_date": src["date"]}
    if finite(raw.get("sigma")) is not None:
        out["sigma"] = finite(raw.get("sigma"))
    if text(raw.get("method"), SOURCE_TEXT_LEN):
        out["method"] = text(raw.get("method"), SOURCE_TEXT_LEN)
    return out


def keynote_head(raw, today, allowed=KEYNOTE_SCOPES):
    """Required fields → (id, day, kind, scopes) or a Vietnamese reason string."""
    if not isinstance(raw, dict):
        return "không phải object"
    kid = raw.get("id")
    if not isinstance(kid, str) or not KEYNOTE_ID_RE.fullmatch(kid):
        return "id sai"
    day = parse_day(raw.get("date")) if isinstance(raw.get("date"), str) and DAY_RE.fullmatch(raw["date"]) else None
    if day is None:
        return "ngày sai"
    if day > today:
        return "ngày trong tương lai"
    if raw.get("kind") not in ("dinh", "day"):
        return "kind sai"
    scopes = []
    for s in as_list(raw.get("scopes")):
        s = s.strip().upper() if isinstance(s, str) else None
        if s in allowed and s not in scopes:
            scopes.append(s)
    if not scopes:
        return "scopes rỗng/sai"
    if not text(raw.get("title"), 140):
        return "thiếu title"
    return kid, day, raw["kind"], scopes


def keynote_tiers(raw, refs, claims, narrative, warns):
    """→ (tier, tier_effective): declared tier (else the lowest source tier), UNVERIFIED when no narrative
    source resolves (event sources / claims) or on a news-rule miss."""
    tier = norm_tier(raw.get("tier"))
    if tier is None:
        tier = lowest_tier([s["tier"] for s in refs.ordered])
        warns.append("Thiếu bậc keynote — lấy bậc thấp nhất của nguồn (%s)" % tier)
    if tier != "UNVERIFIED" and not narrative and not any(srcs for srcs, _ in claims):
        warns.append("UNVERIFIED — không dùng cho quyết định: bối cảnh/nguyên nhân không có nguồn truy được "
                     "(sources/claims không khớp bảng sources)")
        return tier, "UNVERIFIED"
    if tier != "UNVERIFIED" and not news_rule_ok(claims, narrative):
        warns.append("UNVERIFIED — không dùng cho quyết định: tin báo cần ≥2 nguồn khác tổ chức và khác tên miền")
        return tier, "UNVERIFIED"
    return tier, tier


def parse_keynote(raw, table, today, allowed=KEYNOTE_SCOPES):
    """One raw event → (keynote dict, None) or (None, reason). keynote["_score"] is popped by the caller.
    allowed = the scopes this file may name (the three index scopes, + TK for a ticker file)."""
    head = keynote_head(raw, today, allowed)
    if isinstance(head, str):
        return None, head
    kid, day, kind, scopes = head
    refs, cut = _SourceRefs(table), []
    warns = [text(w, SOURCE_TEXT_LEN) for w in as_list(raw.get("warnings")) if text(w, SOURCE_TEXT_LEN)][:MAX_RAW_WARNINGS]
    odd = [str(s)[:SHORT_LEN] for s in raw["scopes"] if not (isinstance(s, str) and s.strip().upper() in allowed)]
    if odd:
        warns.append("Bỏ phạm vi không hỗ trợ: " + ", ".join(odd))
    narrative = refs.many(raw.get("sources"))
    claims = []
    for c in as_list(raw.get("claims")):
        if isinstance(c, dict):
            srcs = refs.many(c.get("src"))
            claims.append((srcs, norm_tier(c.get("tier")) == "NEWS" or any(is_news(s) for s in srcs)))
    raw_numbers = as_list(raw.get("numbers"))
    numbers = [n for n in (keynote_number(n, refs, allowed) for n in raw_numbers) if n is not None][:MAX_NUMBERS]
    if not refs.ordered:
        return None, "không có nguồn hợp lệ (cần org + date)"
    if refs.unknown:
        warns.append("Nguồn không có trong bảng sources: " + ", ".join(refs.unknown[:MAX_LISTED]))
    if len(numbers) < len(raw_numbers):
        warns.append("Bỏ %d số thiếu nguồn/bậc/giá trị" % (len(raw_numbers) - len(numbers)))
    est_bare = [n["k"] for n in numbers if n["tier"] == "EST" and "method" not in n]
    if est_bare:
        warns.append("Số EST thiếu phương pháp: " + ", ".join(est_bare))
    tier, tier_eff = keynote_tiers(raw, refs, claims, narrative, warns)

    factors = [text(f, FACTOR_LEN, "key_factors", cut) for f in as_list(raw.get("key_factors")) if text(f, FACTOR_LEN)]
    if len(factors) > MAX_FACTORS:
        factors = factors[:MAX_FACTORS]
        cut.append("key_factors")
    detect = raw.get("detect") if isinstance(raw.get("detect"), dict) else {}
    provisional = raw.get("provisional") if isinstance(raw.get("provisional"), bool) else detect.get("provisional")
    priority = raw.get("priority")
    if isinstance(priority, bool) or not isinstance(priority, int) or not 1 <= priority <= 3:
        priority = None  # derived from detect.score by assign_priorities()
    ev = {"id": kid, "date": day.isoformat(), "ms": day_ms(day), "kind": kind,
          "provisional": provisional if isinstance(provisional, bool) else False, "scopes": scopes,
          "priority": priority}
    for field, limit in KEYNOTE_TEXT:
        ev[field] = text(raw.get(field), limit, field, cut)
    if cut:
        warns.append("Cắt ngắn: " + ", ".join(sorted(set(cut))))
    ev.update(key_factors=factors, numbers=numbers, sources=[dict(s) for s in refs.ordered[:MAX_EVENT_SOURCES]],
              tier=tier, tier_effective=tier_eff, warnings=warns, _score=finite(detect.get("score")))
    return ev, None


def day_ms(day):
    """date → epoch ms at UTC midnight (the x-grid of every HHP chart)."""
    return int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp() * 1000)


def assign_priorities(events):
    """Missing priority → terciles of detect.score over all events (top third = 1); no score → 2."""
    scores = sorted((e["_score"] for e in events if e["_score"] is not None), reverse=True)
    for e in events:
        s = e.pop("_score")
        if e["priority"] is None:
            e["priority"] = 2 if s is None else 1 + min(2, 3 * sum(1 for x in scores if x > s) // len(scores))


def load_keynotes(ddir, warnings, today=None):
    """→ (keynotes sorted by date, meta.keynotes_file | None). Never raises on bad content."""
    return read_keynotes(os.path.join(ddir, KEYNOTES_FILE), KEYNOTES_FILE, RUN_KEYNOTES, KEYNOTE_SCOPES,
                         warnings, today)


def read_keynotes(path, name, run, allowed, warnings, today=None, warn_missing=True):
    """One hhp_keynotes/1 file → (keynotes sorted by date, {mtime, n, n_dropped} | None). name / run = the file
    name and the fix hint quoted in warnings; allowed = the scopes its events may name."""
    if not os.path.isfile(path):
        if warn_missing:
            warnings.append("Chưa có %s — keynote đỉnh/đáy tắt. %s" % (name, run))
        return [], None
    info = {"mtime": file_meta(path)["file_mtime"], "n": 0, "n_dropped": 0}
    try:
        raw = load_json(path)
    except (OSError, ValueError) as exc:
        warnings.append("Không đọc được %s (%s) — keynote tắt. %s" % (name, exc, run))
        return [], info
    if not isinstance(raw, dict) or not isinstance(raw.get("events"), list):
        warnings.append("%s sai định dạng (thiếu events[]) — keynote tắt. %s" % (name, run))
        return [], info

    table, today = source_table(raw.get("sources")), today or datetime.now(ICT).date()
    kept, dropped, seen = [], [], set()
    for i, item in enumerate(raw["events"]):
        ev, why = parse_keynote(item, table, today, allowed)
        if ev is not None and ev["id"] in seen:
            ev, why = None, "trùng id"
        if ev is None:
            name = item.get("id") if isinstance(item, dict) and isinstance(item.get("id"), str) else "#%d" % i
            dropped.append("%s (%s)" % (name[:40], why))
            continue
        seen.add(ev["id"])
        kept.append(ev)
    assign_priorities(kept)
    if len(kept) > MAX_KEYNOTES:
        kept.sort(key=lambda e: (e["priority"], -e["ms"]))
        dropped += ["%s (vượt trần %d)" % (e["id"], MAX_KEYNOTES) for e in kept[MAX_KEYNOTES:]]
        kept = kept[:MAX_KEYNOTES]
    kept.sort(key=lambda e: (e["ms"], e["id"]))
    if dropped:
        warnings.append("Bỏ %d keynote sai định dạng: %s — %s" % (
            len(dropped), ", ".join(dropped[:MAX_LISTED]) + (", …" if len(dropped) > MAX_LISTED else ""), run))
    cut = [e["id"] for e in kept if any(w.startswith("Cắt ngắn") for w in e["warnings"])]
    if cut:
        warnings.append("Keynote có chuỗi quá dài, đã cắt: %s" % ", ".join(cut[:MAX_LISTED]))
    info["n"], info["n_dropped"] = len(kept), len(dropped)
    return kept, info


# ── Forecast (hhp_forecast.json, written by hhp_forecast_bridge.py) ─────────


def ddmm(value):
    d = parse_day(value)
    return d.strftime("%d/%m") if d else "?"


def vn_num(value):
    """2176.9 → "2.176,9" (Vietnamese separators) for warning text; non-number → "?"."""
    v = finite(value)
    if v is None:
        return "?"
    return format(v, ",.2f").rstrip("0").rstrip(".").translate(str.maketrans(",.", ".,"))


def fc_series(arr, x0):
    """[[ms, v], ...] → (list, None) when 2–60 finite pairs, integral x strictly ascending, first x == x0;
    else (None, reason)."""
    if not isinstance(arr, list):
        return None, "thiếu"
    if not FC_MIN_POINTS <= len(arr) <= FC_MAX_POINTS:
        return None, "%d điểm (cần %d–%d)" % (len(arr), FC_MIN_POINTS, FC_MAX_POINTS)
    out = []
    for p in arr:
        tv = ts_value(p) if isinstance(p, (list, tuple)) and len(p) == 2 else None
        if tv is None or finite(p[0]) != tv[0]:
            return None, "có điểm không hữu hạn/sai dạng"
        if out and tv[0] <= out[-1][0]:
            return None, "trục thời gian không tăng dần"
        out.append([tv[0], tv[1]])
    if x0 is None or out[0][0] != x0:
        return None, "điểm đầu không trùng anchor.ms"
    return out, None


def fc_growth(raw):
    """growth[] → (entries with int year, finite g and a tier, sorted by year; None, reason when empty)."""
    out = [clean(g) for g in as_list(raw) if isinstance(g, dict) and isinstance(g.get("year"), int)
           and not isinstance(g.get("year"), bool) and finite(g.get("g")) is not None
           and isinstance(g.get("tier"), str) and g["tier"].strip()]
    if not out:
        return None, "growth[] không có năm hợp lệ (year, g, tier)"
    return sorted(out, key=lambda g: g["year"]), None


def fc_common(blk):
    """Pass-through fields shared by index and basket blocks."""
    return {"milestones": sorted((clean(m) for m in as_list(blk.get("milestones"))
                                  if isinstance(m, dict) and finite(m.get("ms")) is not None),
                                 key=lambda m: m["ms"]),
            "method": blk.get("method") if isinstance(blk.get("method"), str) else None,
            "caveats": [c for c in as_list(blk.get("caveats")) if isinstance(c, str)]}


def anchor_ms(anchor):
    ms = finite(anchor.get("ms"))
    return int(ms) if ms is not None and ms == int(ms) else None


def last_finite(arr):
    for p in reversed(as_list(arr)):
        tv = ts_value(p)
        if tv is not None:
            return tv[1]
    return None


def index_anchor_problem(anchor, m, idx, tolerance=FC_FAIR_TOLERANCE):
    """VNINDEX anchor vs the overview's own index.<m> block → reason string, or None when it matches.
    Also used for a ticker: idx = build_ticker's own <m> block (same as_of / mean / sd / chart.fair keys)."""
    if anchor.get("as_of") != idx.get("as_of"):
        return "neo %s · dữ liệu %s" % (ddmm(anchor.get("as_of")), ddmm(idx.get("as_of")))
    am = anchor.get(m) if isinstance(anchor.get(m), dict) else {}
    mean, sd = finite(am.get("mean")), finite(am.get("sd"))
    if mean is None or sd is None or mean != finite(idx.get("mean")) or sd != finite(idx.get("sd")):
        return "neo μ %s σ %s · dữ liệu μ %s σ %s" % (vn_num(am.get("mean")), vn_num(am.get("sd")),
                                                      vn_num(idx.get("mean")), vn_num(idx.get("sd")))
    last = am.get("last") if isinstance(am.get("last"), dict) else {}
    chart = idx.get("chart") if isinstance(idx.get("chart"), dict) else {}
    fair, chart_fair = finite(last.get("fair")), last_finite(chart.get("fair"))
    if fair is None or chart_fair is None or abs(fair - chart_fair) > tolerance:
        return "neo TB %s · dữ liệu TB %s" % (vn_num(fair), vn_num(chart_fair))
    return None


def index_block(blk, anchor, m, warnings, scope="VNINDEX"):
    """VNINDEX (or ticker) forecast block → (payload block, None) or (None, reason). Anchor already checked."""
    x0 = anchor_ms(anchor)
    pts = blk.get("points") if isinstance(blk.get("points"), dict) else {}
    last = anchor[m]["last"]
    points = {}
    for k in FC_LEVELS:
        series, why = fc_series(pts.get(k), x0)
        if why:
            return None, "points.%s %s" % (k, why)
        if series[0][1] != finite(last.get(k)):
            return None, "points.%s điểm đầu khác anchor.%s.last.%s" % (k, m, k)
        points[k] = series
    grid = [p[0] for p in points["fair"]]
    if any([p[0] for p in points[k]] != grid for k in FC_LEVELS):
        return None, "5 đường không cùng lưới thời gian"
    growth, why = fc_growth(blk.get("growth"))
    if why:
        return None, why
    base_path = None
    if blk.get("base_path") is not None:
        base_path, why = fc_series(blk.get("base_path"), x0)
        if why:
            warnings.append("Dự phóng %s %s: base_path %s — bỏ base_path" % (scope, METRIC_LABEL[m], why))
    out = {"x0": x0, "points": points, "base_path": base_path, "growth": growth,
           "eps_pins": [clean(p) for p in as_list(blk.get("eps_pins")) if isinstance(p, dict)], **fc_common(blk)}
    if m == "pb" and isinstance(blk.get("retention"), dict):
        out["retention"] = clean(blk["retention"])
    return out, None


def basket_anchor_problem(anchor, m, bb):
    """Basket anchor vs the hhp_baskets.json block → reason string, or None when it matches."""
    if anchor.get("as_of") != bb.get("as_of"):
        return "neo %s · dữ liệu %s" % (ddmm(anchor.get("as_of")), ddmm(bb.get("as_of")))
    am = anchor.get(m) if isinstance(anchor.get(m), dict) else {}
    bad = [k for k in FC_FLAT if finite(am.get(k)) is None or finite(am.get(k)) != finite(bb.get(k))]
    if bad:
        return "neo %s %s · dữ liệu %s" % (bad[0], vn_num(am.get(bad[0])), vn_num(bb.get(bad[0])))
    return None


def basket_block(blk, anchor, bb):
    """VN30/VN100 forecast block → (payload block, None) or (None, reason). Anchor already checked."""
    x0 = anchor_ms(anchor)
    path, why = fc_series(blk.get("ratio_path"), x0)
    if why:
        return None, "ratio_path " + why
    flat = blk.get("flat") if isinstance(blk.get("flat"), dict) else {}
    if any(finite(flat.get(k)) is None or finite(flat.get(k)) != finite(bb.get(k)) for k in FC_FLAT):
        return None, "flat khác mức μ/±σ của rổ"
    growth, why = fc_growth(blk.get("growth"))
    if why:
        return None, why
    return {"x0": x0, "ratio_path": path, "flat": {k: finite(flat[k]) for k in FC_FLAT}, "growth": growth,
            **fc_common(blk)}, None


def target_member_ok(mb):
    return (isinstance(mb, dict) and bool(text(mb.get("org"), SOURCE_TEXT_LEN)) and isinstance(mb.get("date"), str)
            and bool(SOURCE_DATE_RE.fullmatch(mb["date"])) and finite(mb.get("value")) is not None
            and bool(text(mb.get("url"), 2000)) and norm_tier(mb.get("tier")) in TARGET_TIERS)


def target_label(members, ms):
    """Same wording as the bridge: "<org> MM/YY" for one member, "<n> nguồn MM/YY" otherwise."""
    mmyy = datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%m/%y")
    return "%s %s" % (text(members[0]["org"], SHORT_LEN), mmyy) if len(members) == 1 else "%d nguồn %s" % (len(members), mmyy)


def fc_targets(raw, warnings):
    """scopes.VNINDEX.targets → markers. A member lacking org, date, value, url or a sell-side tier is dropped
    (warned); the marker's value (the bucket median) and label are then re-taken from the members that remain,
    so the value always traces to every member shown. No valid member / no ms / no label → target dropped."""
    out, dropped, trimmed = [], 0, []
    for t in as_list(raw):
        t = t if isinstance(t, dict) else {}
        members = as_list(t.get("members"))
        good = [mb for mb in members if target_member_ok(mb)]
        ms, value, label = finite(t.get("ms")), finite(t.get("value")), text(t.get("label"), SHORT_LEN)
        if ms is None or value is None or not good or not label:
            dropped += 1
            continue
        if len(good) < len(members):
            vals = sorted(finite(mb["value"]) for mb in good)
            mid = len(vals) // 2
            value = round(vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2, 1)
            label = target_label(good, ms)
            trimmed.append("%s bỏ %d/%d" % (text(t.get("id"), SHORT_LEN) or label, len(members) - len(good), len(members)))
        out.append({"id": text(t.get("id"), SHORT_LEN), "horizon": text(t.get("horizon"), SHORT_LEN), "ms": int(ms),
                    "value": value, "label": label, "members": clean(good)})
    if trimmed:
        warnings.append("Mục tiêu VN-Index: bỏ thành viên thiếu org/ngày/url/bậc, tính lại trung vị (%s) — %s"
                        % ("; ".join(trimmed[:MAX_LISTED]), FORECAST_FILE))
    if dropped:
        warnings.append("Bỏ %d mục tiêu VN-Index không còn thành viên hợp lệ (%s)" % (dropped, FORECAST_FILE))
    return sorted(out, key=lambda t: t["ms"])


def fc_sources(raw, warnings, name=FORECAST_FILE):
    out, dropped = [], 0
    for s in as_list(raw):
        ok = isinstance(s, dict) and all(text(s.get(k), SOURCE_TEXT_LEN) for k in ("id", "org", "tier")) \
            and isinstance(s.get("date"), str) and SOURCE_DATE_RE.fullmatch(s["date"]) \
            and (text(s.get("url"), 2000) or text(s.get("file"), SOURCE_TEXT_LEN))
        if not ok:
            dropped += 1
            continue
        out.append({k: s[k] for k in ("id", "org", "title", "date", "url", "file", "tier", "definition") if k in s})
    if dropped:
        warnings.append("Bỏ %d nguồn dự phóng thiếu id/org/ngày/bậc/url (%s)" % (dropped, name))
    return clean(out)


def scope_forecast(scope, raw, charts, warnings):
    """One scope → {pe, pb}: anchor check, then shape check. charts[m] = the overview's block for that
    chart, None when that chart has no such metric, False when there is no chart at all (already warned)."""
    raw = raw if isinstance(raw, dict) else {}
    anchor = raw.get("anchor") if isinstance(raw.get("anchor"), dict) else {}
    is_index = scope == "VNINDEX"
    out = {}
    for m in METRICS:
        blk, chart = raw.get(m), charts[m]
        out[m] = None
        if not isinstance(blk, dict) or chart is False:
            continue
        name = "Dự phóng %s %s" % (scope, METRIC_LABEL[m])
        if chart is None:
            warnings.append("%s bỏ: dữ liệu hiện tại không có khối %s để neo" % (name, METRIC_LABEL[m]))
            continue
        why = (index_anchor_problem if is_index else basket_anchor_problem)(anchor, m, chart)
        if why:
            warnings.append("%s lệch neo (%s) — chờ lượt orchestrator kế" % (name, why))
            continue
        out[m], why = index_block(blk, anchor, m, warnings) if is_index else basket_block(blk, anchor, chart)
        if why:
            warnings.append("%s bỏ: %s (%s sai định dạng) — %s" % (name, why, FORECAST_FILE, RUN_FORECAST))
    return out


def load_forecast(ddir, index, baskets, warnings):
    """→ (forecast payload | None, meta.forecast_file | None). index / baskets = the overview's own blocks."""
    path = os.path.join(ddir, FORECAST_FILE)
    if not os.path.isfile(path):
        warnings.append("Chưa có %s — dự phóng 3 năm tắt. %s" % (FORECAST_FILE, RUN_FORECAST))
        return None, None
    fm = file_meta(path)
    info = {"mtime": fm["file_mtime"], "age_hours": fm["age_hours"]}
    try:
        raw = load_json(path)
    except (OSError, ValueError) as exc:
        warnings.append("Không đọc được %s (%s) — dự phóng tắt. %s" % (FORECAST_FILE, exc, RUN_FORECAST))
        return None, info
    meta = raw.get("meta") if isinstance(raw, dict) else None
    if not isinstance(meta, dict) or meta.get("schema") != FORECAST_SCHEMA or not isinstance(raw.get("scopes"), dict):
        warnings.append("%s sai định dạng (cần meta.schema = %s và scopes{}) — dự phóng tắt. %s"
                        % (FORECAST_FILE, FORECAST_SCHEMA, RUN_FORECAST))
        return None, info
    if fm["stale"]:
        warnings.append("%s đã %.0f giờ chưa làm mới (> %.0f h) — %s"
                        % (FORECAST_FILE, fm["age_hours"], STALE_HOURS, RUN_FORECAST))
    scopes = raw["scopes"]
    horizon = meta.get("horizon_months")
    out = {"meta": {"generated": meta.get("generated") if isinstance(meta.get("generated"), str) else None,
                    "age_hours": fm["age_hours"],
                    "horizon_months": horizon if isinstance(horizon, int) and not isinstance(horizon, bool) else None,
                    "method": meta.get("method") if isinstance(meta.get("method"), str) else None,
                    "caveats": [c for c in as_list(meta.get("caveats")) if isinstance(c, str)],
                    "warnings": [w for w in as_list(meta.get("warnings")) if isinstance(w, str)],
                    "sources": fc_sources(raw.get("sources"), warnings)}}
    charts = {m: index[m] if isinstance(index.get(m), dict) else False for m in METRICS}
    out["VNINDEX"] = scope_forecast("VNINDEX", scopes.get("VNINDEX"), charts, warnings)
    vni = scopes.get("VNINDEX") if isinstance(scopes.get("VNINDEX"), dict) else {}
    out["VNINDEX"]["targets"] = fc_targets(vni.get("targets"), warnings)
    for u in UNIVERSES:
        b = (baskets or {}).get(u)
        charts = {m: (b[m] if isinstance(b.get(m), dict) else None) if isinstance(b, dict) else False
                  for m in METRICS}
        out[u] = scope_forecast(u, scopes.get(u), charts, warnings)
    return out, info


# ── Ticker ───────────────────────────────────────────────────────────────────


def band_levels(mean, sd):
    """(name, multiplier or None) for the five band levels."""
    m, s = finite(mean), finite(sd)
    return (
        ("fair", m),
        ("cheap1", m - s if m is not None and s is not None else None),
        ("cheap2", m - 2 * s if m is not None and s is not None else None),
        ("rich1", m + s if m is not None and s is not None else None),
        ("rich2", m + 2 * s if m is not None and s is not None else None),
    )


def ticker_metric(block):
    """Series metric block {price, base, mean, sd, ...} → stats + chart on a shared x-grid."""
    if not isinstance(block, dict):
        return None
    base_by_ts = {}
    for p in block.get("base") or []:
        tv = ts_value(p)
        if tv is not None:
            base_by_ts[tv[0]] = tv[1]
    grid = {}
    for p in block.get("price") or []:
        tv = ts_value(p)
        if tv is not None and tv[0] in base_by_ts:
            grid[tv[0]] = (tv[1], base_by_ts[tv[0]])
    points = sorted(grid.items())

    chart = {"price": [[ts, px] for ts, (px, _) in points]}
    for name, k in band_levels(block.get("mean"), block.get("sd")):
        chart[name] = [] if k is None else [[ts, max(0.0, round(base * k, 2))] for ts, (_, base) in points]

    out = {k: v for k, v in block.items() if k not in ("price", "base")}
    out["zone_key"] = zone_key(block.get("zone"), block.get("sigma"))
    out["chart"] = chart
    return out


# ── Ticker forecast (hhp_forecast_tickers/<TK>.json, written by the bridge's per-ticker step) ─


def ticker_fc_block(blk, anchor, m, tk, warnings):
    """Ticker forecast block → (payload block, None) or (None, reason): the VNINDEX shape rules with exactly
    TICKER_FC_POINTS points, plus the bridge's `reliable` flag. Anchor already checked."""
    fair = blk["points"].get("fair") if isinstance(blk.get("points"), dict) else None
    if isinstance(fair, list) and len(fair) != TICKER_FC_POINTS:
        return None, "points.fair %d điểm (cần %d)" % (len(fair), TICKER_FC_POINTS)
    out, why = index_block(blk, anchor, m, warnings, tk)
    if why:
        return None, why
    out["reliable"] = blk["reliable"] if isinstance(blk.get("reliable"), bool) else None
    return out, None


def ticker_metric_forecast(tk, m, blk, anchor, chart, warnings, name):
    """One metric → (payload block | None, reason | None). chart = build_ticker's own <m> block (None when the
    series lacks that metric). Every reason is also one meta warning; a null block in the file is silent.
    anchor.<m>.as_of / .ms, when the bridge writes them (the P/E and P/B series may end on different days),
    override the file-level anchor.as_of / anchor.ms for that metric."""
    label = "Dự phóng %s %s" % (tk, METRIC_LABEL[m])
    if not isinstance(blk, dict):
        return None, None
    own = anchor.get(m) if isinstance(anchor.get(m), dict) else {}
    anchor = dict(anchor, **{k: own[k] for k in ("as_of", "ms") if k in own})
    if chart is None:
        why = "%s/%s.json không có khối %s để neo" % (SERIES_DIR, tk, METRIC_LABEL[m])
        warnings.append("%s bỏ: %s" % (label, why))
        return None, why
    why = index_anchor_problem(anchor, m, chart, TICKER_FAIR_TOLERANCE)
    if why:
        warnings.append("%s lệch neo (%s) — chờ lượt orchestrator kế" % (label, why))
        return None, "lệch neo (%s)" % why
    out, why = ticker_fc_block(blk, anchor, m, tk, warnings)
    if why:
        warnings.append("%s bỏ: %s (%s sai định dạng) — %s" % (label, why, name, RUN_FORECAST_TICKERS))
    return out, why


def ticker_target_problem(t, x0):
    """→ why one ◆ target cannot be shown (Vietnamese), or None. x0 = anchor.ms (None when unknown)."""
    if not isinstance(t, dict):
        return "không phải object"
    if not text(t.get("org"), SOURCE_TEXT_LEN) or not (isinstance(t.get("date"), str)
                                                       and SOURCE_DATE_RE.fullmatch(t["date"])):
        return "thiếu org/ngày"
    if not (text(t.get("url"), 2000) or text(t.get("file"), SOURCE_TEXT_LEN)):
        return "thiếu url/tệp nguồn"
    if norm_tier(t.get("tier")) not in TARGET_TIERS:
        return "bậc không phải %s" % "/".join(TARGET_TIERS)
    ms, value, vnd, scale = (finite(t.get(k)) for k in ("ms", "value", "value_vnd", "scale"))
    if ms is None or ms != int(ms) or not (value and value > 0) or not (vnd and vnd > 0) or not (scale and scale > 0):
        return "thiếu ms/value/value_vnd/scale hợp lệ"
    if abs(value - vnd / 1000.0 * scale) > TARGET_SCALE_TOLERANCE * value:
        return "value %s lệch value_vnd/1000 × scale = %s" % (vn_num(value), vn_num(vnd / 1000.0 * scale))
    if x0 is not None and ms <= x0:
        return "hết hạn (không sau ngày neo)"
    return None


def ticker_targets(raw, x0, warnings, name):
    """targets[] → the valid ◆ markers sorted by ms; each bad target is dropped alone (one warning names them)."""
    out, bad = [], []
    for i, t in enumerate(as_list(raw)):
        why = ticker_target_problem(t, x0)
        if why:
            tid = text(t.get("id"), SHORT_LEN) if isinstance(t, dict) else ""
            bad.append("%s (%s)" % (tid or "#%d" % i, why))
            continue
        keep = {k: t[k] for k in TICKER_TARGET_KEYS if k in t}
        out.append(clean(dict(keep, ms=int(t["ms"]), tier=norm_tier(t["tier"]))))
    if bad:
        warnings.append("Bỏ %d mục tiêu giá của mã: %s (%s)"
                        % (len(bad), "; ".join(bad[:MAX_LISTED]) + ("; …" if len(bad) > MAX_LISTED else ""), name))
    return sorted(out, key=lambda t: t["ms"])


def ticker_fc_skipped(ddir, tk):
    """The bridge's reason for leaving tk out (hhp_forecast_tickers/_index.json skipped{}), else None."""
    try:
        idx = load_json(os.path.join(ddir, TICKER_FC_DIR, TICKER_FC_INDEX))
    except (OSError, ValueError):
        return None
    skipped = idx.get("skipped") if isinstance(idx, dict) else None
    if not isinstance(skipped, dict):
        return None
    return text(skipped.get(tk), SOURCE_TEXT_LEN) or None


def load_ticker_forecast(ddir, tk, charts, warnings):
    """→ (forecast payload | None, meta.forecast_file | None). charts[m] = build_ticker's own <m> block."""
    name = "%s/%s.json" % (TICKER_FC_DIR, tk)
    path = os.path.join(ddir, TICKER_FC_DIR, tk + ".json")
    if not os.path.isfile(path):
        why = ticker_fc_skipped(ddir, tk)
        warnings.append("Chưa có %s — dự phóng 3 năm của mã tắt%s. %s"
                        % (name, " (bridge bỏ mã: %s)" % why if why else "", RUN_FORECAST_TICKERS))
        return None, None
    fm = file_meta(path)
    info = {"mtime": fm["file_mtime"], "age_hours": fm["age_hours"]}
    try:
        raw = load_json(path)
    except (OSError, ValueError) as exc:
        warnings.append("Không đọc được %s (%s) — dự phóng tắt. %s" % (name, exc, RUN_FORECAST_TICKERS))
        return None, info
    meta = raw.get("meta") if isinstance(raw, dict) else None
    if not isinstance(meta, dict) or meta.get("schema") != TICKER_FC_SCHEMA or meta.get("ticker") != tk:
        warnings.append("%s sai định dạng (cần meta.schema = %s, meta.ticker = %s) — dự phóng tắt. %s"
                        % (name, TICKER_FC_SCHEMA, tk, RUN_FORECAST_TICKERS))
        return None, info
    if fm["stale"]:
        warnings.append("%s đã %.0f giờ chưa làm mới (> %.0f h) — %s"
                        % (name, fm["age_hours"], STALE_HOURS, RUN_FORECAST_TICKERS))

    def meta_str(key):
        return meta[key] if isinstance(meta.get(key), str) else None

    horizon = meta.get("horizon_months")
    scale = meta.get("price_scale") if isinstance(meta.get("price_scale"), dict) else {}
    out = {"meta": {"generated": meta_str("generated"), "age_hours": fm["age_hours"],
                    "horizon_months": horizon if isinstance(horizon, int) and not isinstance(horizon, bool) else None,
                    "unit": meta_str("unit"), "method": meta_str("method"),
                    "caveats": [c for c in as_list(meta.get("caveats")) if isinstance(c, str)],
                    "warnings": [w for w in as_list(meta.get("warnings")) if isinstance(w, str)],
                    "price_scale": clean(scale) if (finite(scale.get("scale")) or 0) > 0 else None,
                    "sources": fc_sources(raw.get("sources"), warnings, name)}}
    anchor = raw.get("anchor") if isinstance(raw.get("anchor"), dict) else {}
    skip_raw = raw.get("skip") if isinstance(raw.get("skip"), dict) else {}
    skip = {m: text(skip_raw.get(m), SOURCE_TEXT_LEN) or None for m in METRICS}
    for m in METRICS:
        out[m], why = ticker_metric_forecast(tk, m, raw.get(m), anchor, charts[m], warnings, name)
        if why:
            skip[m] = why
    out["skip"] = skip
    out["targets"] = ticker_targets(raw.get("targets"), anchor_ms(anchor), warnings, name)
    return out, info


def build_ticker(ddir, tk):
    core, _ = load_core(ddir)
    path = os.path.join(ddir, SERIES_DIR, tk + ".json")
    if not os.path.isfile(path):
        raise HhpError("NO_SERIES", "Chưa có dữ liệu chart cho %s (%s/%s.json). %s" % (tk, SERIES_DIR, tk, RUN_SERIES))
    try:
        series = load_json(path)
    except (OSError, ValueError) as exc:
        raise HhpError("NO_SERIES", "Không đọc được %s/%s.json (%s). %s" % (SERIES_DIR, tk, exc, RUN_SERIES))
    if not isinstance(series, dict):
        raise HhpError("NO_SERIES", "%s/%s.json sai định dạng. %s" % (SERIES_DIR, tk, RUN_SERIES))

    by_ticker = core.get("by_ticker") if isinstance(core.get("by_ticker"), dict) else {}
    entry = by_ticker.get(tk)
    row = None
    if isinstance(entry, dict):
        members, _ = load_members(ddir, [])
        row = build_row(tk, entry, set(members["VN30"]), set(members["VN100"]), series_as_of(series),
                        reference_day(core))

    forward = dict(series["forward"]) if isinstance(series.get("forward"), dict) else None
    capiq = row.get("capiq") if row is not None else None
    if forward is not None:
        forward["capiq"] = capiq
    elif isinstance(capiq, dict):
        forward = {"capiq": capiq}
    meta = series.get("meta") if isinstance(series.get("meta"), dict) else {}
    pe, pb = ticker_metric(series.get("pe")), ticker_metric(series.get("pb"))
    warnings = []
    forecast, forecast_file = load_ticker_forecast(ddir, tk, {"pe": pe, "pb": pb}, warnings)
    kn_name = "%s/%s.json" % (TICKER_KN_DIR, tk)
    keynotes, keynotes_file = read_keynotes(os.path.join(ddir, kn_name), kn_name,
                                            RUN_KEYNOTES_TICKERS % tk, KEYNOTE_SCOPES + (tk,),
                                            warnings, warn_missing=False)
    return {
        "ticker": tk,
        "generated": meta.get("generated"),
        "unit": "nghìn đồng",
        "pe": pe,
        "pb": pb,
        "forward": forward,
        "row": row,
        "forecast": forecast,
        "keynotes": keynotes,
        "meta": {"forecast_file": forecast_file, "keynotes_file": keynotes_file, "warnings": warnings},
    }


# ── VNINDEX full history (hhp_vnindex_history.json, orchestrator step 1d) ────


def history_file_meta(ddir):
    """{mtime, age_hours} of hhp_vnindex_history.json, None without the file. One stat, the file is not parsed —
    the overview carries it so the panel knows when to re-fetch `history`."""
    path = os.path.join(ddir, HISTORY_FILE)
    try:
        if not os.path.isfile(path):
            return None
        fm = file_meta(path)
    except OSError:
        return None
    return {"mtime": fm["file_mtime"], "age_hours": fm["age_hours"]}


def hist_series(arr, max_n, positive):
    """[[ms, v], ...] → (list, None) when 2–max_n pairs, integral ms strictly ascending, v finite and ≥ 0 (> 0 when
    positive); else (None, reason)."""
    if not isinstance(arr, list):
        return None, "thiếu"
    if not HIST_MIN_POINTS <= len(arr) <= max_n:
        return None, "%d điểm (cần %d–%d)" % (len(arr), HIST_MIN_POINTS, max_n)
    out = []
    for p in arr:
        tv = ts_value(p) if isinstance(p, (list, tuple)) and len(p) == 2 else None
        if tv is None or finite(p[0]) != tv[0]:
            return None, "có điểm không hữu hạn/sai dạng"
        if tv[1] < 0 or (positive and tv[1] == 0):
            return None, "có giá trị %s" % ("≤ 0" if positive else "âm")
        if out and tv[0] <= out[-1][0]:
            return None, "trục thời gian không tăng dần"
        out.append([tv[0], tv[1]])
    return out, None


def hist_day(value):
    """"YYYY-MM-DD" (exactly) → date, else None."""
    return parse_day(value) if isinstance(value, str) and DAY_RE.fullmatch(value) else None


def hist_chart(raw, from_ms):
    """chart{five levels} → (dict, None) on one x-grid starting at or after long.from; else (None, reason)."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for k in FC_LEVELS:
        out[k], why = hist_series(raw.get(k), HIST_CHART_MAX, False)
        if why:
            return None, "chart.%s %s" % (k, why)
    grid = [p[0] for p in out["fair"]]
    if any([p[0] for p in out[k]] != grid for k in FC_LEVELS):
        return None, "5 đường chart không cùng lưới thời gian"
    if grid[0] < from_ms:
        first = datetime.fromtimestamp(grid[0] / 1000, timezone.utc).strftime("%d/%m/%Y")
        return None, "chart bắt đầu %s, trước long.from" % first
    return out, None


def hist_window(raw, keys):
    """long / eight block → copy + zone_key when every `keys` value is finite (sd > 0), else None."""
    if not isinstance(raw, dict) or any(finite(raw.get(k)) is None for k in keys) or not finite(raw["sd"]) > 0:
        return None
    return with_zone_key(clean(raw))


def hist_anchor_problem(engine_as_of, idx, lng, eight):
    """History metric vs the engine's own index.<m> → reason string, or None. The long reading and the 8-year
    window are copies of the engine (now; mean, sd) made in the same orchestrator run."""
    if not isinstance(idx, dict):
        return "engine không có khối index"
    if engine_as_of != idx.get("as_of"):
        return "%s vs %s" % (ddmm(engine_as_of), ddmm(idx.get("as_of")))
    pairs = []
    if isinstance(eight, dict):
        pairs += [("μ 8 năm", eight.get("mean"), idx.get("mean")), ("σ 8 năm", eight.get("sd"), idx.get("sd"))]
    if isinstance(lng, dict):
        pairs.append(("hiện tại", lng.get("now"), idx.get("now")))
    for label, mine, eng in pairs:
        if finite(mine) is None or finite(mine) != finite(eng):
            return "%s %s · engine %s" % (label, vn_num(mine), vn_num(eng))
    return None


def hist_agree(raw, lng, eight):
    """windows_agree → the file's bool when both windows are shown and it matches their zone keys, else None."""
    if lng is None or eight is None or not isinstance(raw, bool):
        return None
    if lng.get("zone_key") is None or eight.get("zone_key") is None:
        return None
    return raw if raw == (lng["zone_key"] == eight["zone_key"]) else None


def hist_src(raw):
    """◇ source → {org, title, date, url?, file?, loc?}; None without an org and a date."""
    if not isinstance(raw, dict):
        return None
    org, date = text(raw.get("org"), SOURCE_TEXT_LEN), raw.get("date")
    if not org or not (isinstance(date, str) and SOURCE_DATE_RE.fullmatch(date.strip())):
        return None
    out = {"org": org, "title": text(raw.get("title"), SOURCE_TEXT_LEN), "date": date.strip()}
    for k in ("url", "file", "loc"):
        if text(raw.get(k), 2000):
            out[k] = text(raw.get(k), 2000)
    return out


def hist_drawable(raw):
    """(v, tier, src, value_kind) of a ◇ or an `also` member, or a reason string. UNVERIFIED is never shown."""
    v, tier, src = finite(raw.get("v")), norm_tier(raw.get("tier")), hist_src(raw.get("src"))
    if v is None:
        return "v không hữu hạn"
    if tier is None or tier == "UNVERIFIED":
        return "bậc %s" % (tier or "không rõ")
    if src is None:
        return "nguồn thiếu org/ngày"
    if raw.get("value_kind") not in HIST_POINT_KINDS:
        return "value_kind sai"
    return v, tier, src, raw["value_kind"]


def hist_point(raw, from_ms):
    """One ◇ (sparse sourced ratio before long.from) → (point, number of `also` members dropped) or (None, reason).
    No σ is ever carried (the output is whitelisted)."""
    if not isinstance(raw, dict):
        return None, "không phải object"
    day = hist_day(raw.get("date"))
    if day is None:
        return None, "ngày sai"
    if day_ms(day) >= from_ms:
        return None, "không trước long.from"
    got = hist_drawable(raw)
    if isinstance(got, str):
        return None, got
    v, tier, src, kind = got
    close, ms = finite(raw.get("close")), finite(raw.get("ms"))
    if close is None or close <= 0:
        return None, "thiếu close"
    if raw.get("ms") is not None and (ms is None or ms != int(ms)):
        return None, "ms sai"
    period = raw.get("period") if isinstance(raw.get("period"), dict) else None
    if period is not None:
        period = {"from": period.get("from"), "to": period.get("to")}
        if hist_day(period["from"]) is None or hist_day(period["to"]) is None:
            period = None
    also, n_bad = [], 0
    for a in as_list(raw.get("also")):
        got = hist_drawable(a) if isinstance(a, dict) else "không phải object"
        if isinstance(got, str):
            n_bad += 1
            continue
        also.append({"v": got[0], "value_kind": got[3], "basis": text(a.get("basis"), SHORT_LEN) or None,
                     "tier": got[1], "src": got[2], "date": a["date"] if hist_day(a.get("date")) else None})
    pt = {"id": text(raw.get("id"), SHORT_LEN) or None, "date": day.isoformat(),
          "ms": int(ms) if ms is not None else day_ms(day), "v": v, "value_kind": kind, "period": period,
          "basis": text(raw.get("basis"), SHORT_LEN) or None, "definition": text(raw.get("definition"), HIST_TEXT_LEN),
          "tier": tier, "src": src, "note": text(raw.get("note"), HIST_TEXT_LEN), "close": close,
          "vs_long_mean": raw.get("vs_long_mean") if raw.get("vs_long_mean") in HIST_VS_MEAN and kind != "lower_bound"
          else None, "also": also}
    if text(raw.get("date_note"), SOURCE_TEXT_LEN):
        pt["date_note"] = text(raw.get("date_note"), SOURCE_TEXT_LEN)
    return pt, n_bad


def hist_points(raw, from_ms, name, warnings):
    """points[] → the valid ◇ sorted by ms; each bad one (or bad `also` member) is dropped alone, one warning."""
    out, bad, n_also = [], [], 0
    for i, p in enumerate(as_list(raw)):
        pt, res = hist_point(p, from_ms)
        if pt is None:
            pid = text(p.get("id"), SHORT_LEN) if isinstance(p, dict) else ""
            bad.append("%s (%s)" % (pid or "#%d" % i, res))
            continue
        n_also += res
        out.append(pt)
    if bad or n_also:
        warnings.append("%s: bỏ %d điểm ◇%s — %s" % (
            name, len(bad), (" + %d mục also" % n_also) if n_also else "",
            "; ".join(bad[:MAX_LISTED]) + ("; …" if len(bad) > MAX_LISTED else "") if bad else "thiếu v/bậc/nguồn"))
    return sorted(out, key=lambda p: p["ms"])


def history_fc_context(ddir):
    """hhp_forecast.json → (anchor, meta.generated, {m: base_path x-grid | None}) or a reason string."""
    path = os.path.join(ddir, FORECAST_FILE)
    if not os.path.isfile(path):
        return "chưa có %s" % FORECAST_FILE
    try:
        raw = load_json(path)
    except (OSError, ValueError):
        return "không đọc được %s" % FORECAST_FILE
    meta = raw.get("meta") if isinstance(raw, dict) else None
    if not isinstance(meta, dict) or meta.get("schema") != FORECAST_SCHEMA or not isinstance(raw.get("scopes"), dict):
        return "%s sai định dạng" % FORECAST_FILE
    vni = raw["scopes"].get("VNINDEX") if isinstance(raw["scopes"].get("VNINDEX"), dict) else {}
    grids = {}
    for m in METRICS:
        path_ = (vni.get(m) or {}).get("base_path") if isinstance(vni.get(m), dict) else None
        pairs = [ts_value(p) for p in as_list(path_)]
        grids[m] = [p[0] for p in pairs] if pairs and all(pairs) else None
    anchor = vni.get("anchor") if isinstance(vni.get("anchor"), dict) else {}
    return anchor, meta.get("generated"), grids


def hist_forecast(raw, m, chart, idx, fc):
    """history.<m>.forecast → (payload, None) or (None, reason). Valid only on the current hhp_forecast.json anchor,
    which must itself sit on the engine (anchor.as_of / mean / sd / last fair, anchor.ms = the engine chart's last x):
    x0 = anchor.ms, source_generated = its meta.generated, its base_path x-grid, each level's first point = the
    long band's last point verbatim."""
    if not isinstance(raw, dict):
        return None, "sai định dạng"
    if isinstance(fc, str):
        return None, fc
    anchor, generated, grids = fc
    why = index_anchor_problem(anchor, m, idx)
    if why:
        return None, "neo %s lệch engine (%s)" % (FORECAST_FILE, why)
    x0 = anchor_ms(anchor)
    engine_x = [tv[0] for tv in (ts_value(p) for p in as_list((idx.get("chart") or {}).get("fair"))) if tv]
    if x0 is None or not engine_x or x0 != engine_x[-1]:
        return None, "anchor.ms của %s không phải điểm chart engine cuối" % FORECAST_FILE
    if finite(raw.get("x0")) != x0:
        return None, "x0 khác anchor.ms của %s" % FORECAST_FILE
    if raw.get("source_generated") != generated:
        return None, "source_generated %s ≠ %s %s" % (raw.get("source_generated"), FORECAST_FILE, generated)
    pts = raw.get("points") if isinstance(raw.get("points"), dict) else {}
    points = {}
    for k in FC_LEVELS:
        points[k], why = fc_series(pts.get(k), x0)
        if why:
            return None, "points.%s %s" % (k, why)
        if points[k][0] != chart[k][-1]:
            return None, "points.%s điểm đầu khác điểm cuối chart.%s" % (k, k)
    grid = [p[0] for p in points["fair"]]
    if any([p[0] for p in points[k]] != grid for k in FC_LEVELS):
        return None, "5 đường không cùng lưới thời gian"
    if grids.get(m) != grid:
        return None, "lưới thời gian khác base_path của %s" % FORECAST_FILE
    return {"x0": x0, "source_generated": generated, "points": points, **fc_common(raw)}, None


def hist_reading(raw, m, from_ms):
    """One keynote_readings entry → (number in the keynote numbers[] shape, sigma_dropped) or (None, reason).
    Only a reading dated on/after long.from can carry σ (the long window's); a ◇ reading never does."""
    if not isinstance(raw, dict) or raw.get("k") != m:
        return None, "k sai"
    scope = raw.get("scope").strip().upper() if isinstance(raw.get("scope"), str) else None
    v, tier = finite(raw.get("v")), norm_tier(raw.get("tier"))
    org, date = text(raw.get("src_org"), SOURCE_TEXT_LEN), raw.get("src_date")
    if scope != "VNINDEX" or v is None or tier in (None, "UNVERIFIED") or not org \
            or not (isinstance(date, str) and READING_DATE_RE.fullmatch(date.strip())):
        return None, "thiếu scope/v/bậc/nguồn"
    asof = hist_day(raw.get("asof"))
    out = {"k": m, "scope": scope, "v": v, "unit": text(raw.get("unit"), SHORT_LEN) or None,
           "asof": asof.isoformat() if asof else None, "tier": tier, "src_org": org, "src_date": date.strip()}
    sigma = finite(raw.get("sigma"))
    long_scale = sigma is not None and asof is not None and day_ms(asof) >= from_ms
    if long_scale:
        out["sigma"] = sigma
    if text(raw.get("method"), SOURCE_TEXT_LEN):
        out["method"] = text(raw.get("method"), SOURCE_TEXT_LEN)
    return out, sigma is not None and not long_scale


def hist_readings(raw, m, from_ms, name, warnings):
    """keynote_readings{id: [..]} → {id: [numbers]} (≤ MAX_READINGS each); bad entries dropped, one warning."""
    out, n_bad, n_sigma, n_cut = {}, 0, 0, 0
    for kid, lst in (raw.items() if isinstance(raw, dict) else ()):
        good = []
        for r in as_list(lst):
            num, flag = hist_reading(r, m, from_ms)
            if num is None:
                n_bad += 1
                continue
            n_sigma += flag
            good.append(num)
        if len(good) > MAX_READINGS:
            n_cut += len(good) - MAX_READINGS
            good = good[:MAX_READINGS]
        if good and isinstance(kid, str):
            out[kid] = good
    notes = [s for s in ("%d số sai" % n_bad if n_bad else "", "bỏ σ của %d số trước long.from" % n_sigma
                         if n_sigma else "", "cắt %d số vượt %d/sự kiện" % (n_cut, MAX_READINGS) if n_cut else "") if s]
    if notes:
        warnings.append("%s: số đọc keynote — %s" % (name, "; ".join(notes)))
    return out


def history_metric(m, raw, idx, engine_as_of, fc, warnings):
    """One metric block → (payload | None, readings {event id: [numbers]}). None = no long band at all."""
    name = "Toàn sử %s" % METRIC_LABEL[m]
    if not isinstance(raw, dict):
        warnings.append("%s: %s không có khối %s — không có dải dài hạn" % (name, HISTORY_FILE, m))
        return None, {}
    lng = raw.get("long") if isinstance(raw.get("long"), dict) else {}
    start = hist_day(lng.get("from"))
    chart, why = (None, "thiếu long.from") if start is None else hist_chart(raw.get("chart"), day_ms(start))
    if why:
        warnings.append("%s bỏ: %s (%s sai định dạng) — %s" % (name, why, HISTORY_FILE, RUN_HISTORY))
        return None, {}
    from_ms = day_ms(start)
    skip = ("long", "eight", "windows_agree", "chart", "points", "forecast", "keynote_readings", "seam")
    out = {k: clean(v) for k, v in raw.items() if k not in skip}
    long_blk = hist_window(raw.get("long"), ("mean", "sd", "now", "sigma"))
    if long_blk is None:
        warnings.append("%s: khối long thiếu μ/σ/hiện tại hữu hạn — σ dài hạn [CẦN DATA] (%s)" % (name, HISTORY_FILE))
    eight_blk = hist_window(raw.get("eight"), ("mean", "sd", "sigma"))
    why = hist_anchor_problem(engine_as_of, idx, long_blk, eight_blk)
    if why:
        warnings.append("%s lệch neo engine (%s) — chờ lượt orchestrator kế" % (name, why))
        long_blk = eight_blk = None
    out.update(long_from=start.isoformat(), long=long_blk, eight=eight_blk,
               windows_agree=hist_agree(raw.get("windows_agree"), long_blk, eight_blk),
               seam=clean(raw["seam"]) if isinstance(raw.get("seam"), dict) else None, chart=chart,
               points=hist_points(raw.get("points"), from_ms, name, warnings), forecast=None)
    if long_blk is not None and eight_blk is not None and out["windows_agree"] is None:
        warnings.append("%s: windows_agree thiếu/không khớp vùng hai cửa sổ — ẩn chip HAI CỬA SỔ" % name)
    if raw.get("forecast") is not None and not why:
        out["forecast"], fwhy = hist_forecast(raw["forecast"], m, chart, idx, fc)
        if fwhy:
            warnings.append("%s: dự phóng dài hạn bỏ — %s" % (name, fwhy))
    return out, hist_readings(raw.get("keynote_readings"), m, from_ms, name, warnings)


def raw_priority_full(path):
    """{event id: priority_full 1..3} straight from the keynote file, + ids whose priority_full is present but bad."""
    try:
        raw = load_json(path)
    except (OSError, ValueError):
        return {}, []
    good, bad = {}, []
    for e in as_list(raw.get("events")) if isinstance(raw, dict) else []:
        if not isinstance(e, dict) or not isinstance(e.get("id"), str) or "priority_full" not in e:
            continue
        pf = e["priority_full"]
        if isinstance(pf, int) and not isinstance(pf, bool) and 1 <= pf <= 3:
            good[e["id"]] = pf
        elif pf is not None:
            bad.append(e["id"])
    return good, bad


def hist_sigma_word(sign, value):
    """Direction of one σ reading vs its own scale's mean — no σ figure."""
    if float(value.replace(",", ".")) == 0:
        return "quanh trung bình"
    return {"+": "trên trung bình", "−": "dưới trung bình", "-": "dưới trung bình"}.get(sign, "lệch trung bình")


def hist_desigma(value, limit):
    """D7 on a keynote text field of the full-history card: "(−2,4σ, thang engine 12/2017→)" → "(dưới trung bình,
    thang engine 12/2017→)", "P/E +3σ (thang …)" → "P/E trên trung bình (thang …)"; a σ with no "thang …" right
    after it gets " (thang engine 12/2017→)". Text without a signed-number σ is returned as is."""
    if not isinstance(value, str) or "σ" not in value:
        return value

    def sub(m):
        word = hist_sigma_word(m.group(1), m.group(2))
        return word if HIST_SCALE_NEXT.match(m.string, m.end()) else "%s (%s)" % (word, HIST_TEXT_SCALE)

    return text(HIST_SIGMA_RE.sub(sub, value), limit)


def hist_desigma_label(value, limit):
    """nhan_phu is a chart label: its σ figure and the scale qualifier are dropped ("cực trị P/E +2,1σ" → "cực trị
    P/E"), not reworded."""
    if not isinstance(value, str) or "σ" not in value:
        return value
    s = re.sub(r"\(\s*\)", "", HIST_SIGMA_LABEL_RE.sub("", value))
    return text(re.sub(r"\s{2,}", " ", s).strip(" ,;·—-"), limit)


def history_keynotes(ddir, readings, warnings):
    """Overview keynotes on the VNINDEX chart, re-cut for the full-history view (D7: every σ on screen is on the
    long scale) → (keynotes, meta.keynotes_file). Their numbers keep scope VNINDEX / unscoped only (the VNINDEX card
    shows no other) and lose "sigma" (pe/pb carry the engine 12/2017→ or Vietcap 2009→ scale; value and method
    kept); a k "sigma" number is dropped. Then the builder's readings are appended — the only σ left is theirs.
    The free text loses its σ figures too (hist_desigma: direction + scale kept; nhan_phu: dropped).
    + priority_full (raw file, else priority)."""
    kept, info = load_keynotes(ddir, warnings)
    prio_full, bad = raw_priority_full(os.path.join(ddir, KEYNOTES_FILE)) if info is not None else ({}, [])
    if bad:
        warnings.append("priority_full ngoài 1..3 → dùng priority: %s (%s)"
                        % (", ".join(bad[:MAX_LISTED]), KEYNOTES_FILE))
    known = {e["id"] for e in kept}
    orphans = sorted({kid for m in METRICS for kid in readings[m] if kid not in known})
    if orphans:
        warnings.append("%d số đọc toàn sử cho keynote không có trong %s: %s" % (
            len(orphans), KEYNOTES_FILE, ", ".join(orphans[:MAX_LISTED])))
    out = []
    for ev in kept:
        if "VNINDEX" not in ev["scopes"]:
            continue
        nums = []
        for n in ev["numbers"]:
            if n["scope"] not in (None, "VNINDEX") or n["k"] == "sigma":
                continue
            nums.append({k: v for k, v in n.items() if k != "sigma"})
        for m in METRICS:
            nums += readings[m].get(ev["id"], [])
        texts = {f: hist_desigma_label(ev[f], lim) if f == "nhan_phu" else hist_desigma(ev[f], lim)
                 for f, lim in KEYNOTE_TEXT}
        out.append(dict(ev, numbers=nums, priority_full=prio_full.get(ev["id"], ev["priority"]),
                        key_factors=[hist_desigma(f, FACTOR_LEN) for f in ev["key_factors"]], **texts))
    return out, info


def build_history(ddir):
    """`history` command: hhp_vnindex_history.json checked and passed through; history None when unusable."""
    core, _ = load_core(ddir)
    warnings = []
    info = history_file_meta(ddir)
    payload = {"meta": {"history_file": info, "keynotes_file": None, "warnings": warnings}, "history": None}
    if info is None:
        warnings.append("Chưa có %s — %s" % (HISTORY_FILE, RUN_HISTORY))
        return payload
    try:
        raw = load_json(os.path.join(ddir, HISTORY_FILE))
    except (OSError, ValueError) as exc:
        warnings.append("Không đọc được %s (%s) — %s" % (HISTORY_FILE, exc, RUN_HISTORY))
        return payload
    meta = raw.get("meta") if isinstance(raw, dict) else None
    if not isinstance(meta, dict) or meta.get("schema") != HISTORY_SCHEMA:
        warnings.append("%s sai định dạng (cần meta.schema = %s) — %s" % (HISTORY_FILE, HISTORY_SCHEMA, RUN_HISTORY))
        return payload
    inputs = meta.get("inputs") if isinstance(meta.get("inputs"), dict) else {}
    if not isinstance(inputs.get("static"), dict) or not text(inputs["static"].get("file"), SOURCE_TEXT_LEN):
        warnings.append("%s dựng khi thiếu tệp tĩnh hhp_vnindex_history_static.json (meta.inputs.static) — lỗi cài "
                        "đặt, toàn sử tắt. %s" % (HISTORY_FILE, RUN_HISTORY))
        return payload
    if info["age_hours"] > STALE_HOURS:
        warnings.append("%s đã %.0f giờ chưa làm mới (> %.0f h) — %s"
                        % (HISTORY_FILE, info["age_hours"], STALE_HOURS, RUN_HISTORY))
    price = raw.get("price") if isinstance(raw.get("price"), dict) else {}
    points, why = hist_series(price.get("points"), HIST_PRICE_MAX, True)
    if why:
        warnings.append("%s bỏ: price.points %s — %s" % (HISTORY_FILE, why, RUN_HISTORY))
        return payload

    hist = {k: clean(v) for k, v in raw.items() if k not in ("price", "gaps", "keynotes") + METRICS}
    hist["price"] = dict(clean(price), points=points)
    hist["gaps"] = [clean(g) for g in as_list(raw.get("gaps")) if isinstance(g, dict)]
    if hist["gaps"]:
        spans = ["%s→%s" % (g.get("from"), g.get("to")) for g in hist["gaps"][:MAX_LISTED]]
        warnings.append("Toàn sử có %d lỗ dữ liệu > 21 ngày: %s (%s gaps[])" % (len(hist["gaps"]), ", ".join(spans),
                                                                            HISTORY_FILE))
    index_src = core.get("index") if isinstance(core.get("index"), dict) else {}
    engine_as_of = meta.get("engine_as_of") if isinstance(meta.get("engine_as_of"), dict) else {}
    fc, readings = history_fc_context(ddir), {}
    for m in METRICS:
        hist[m], readings[m] = history_metric(m, raw.get(m), index_src.get(m), engine_as_of.get(m), fc, warnings)
    hist["keynotes"], payload["meta"]["keynotes_file"] = history_keynotes(ddir, readings, warnings)
    payload["history"] = hist
    return payload


# ── CLI ──────────────────────────────────────────────────────────────────────


def run(argv):
    if len(argv) < 2:
        raise HhpError("BAD_ARGS", "Thiếu lệnh. " + USAGE)
    cmd = argv[1].strip().lower()
    if cmd == "overview":
        return build_overview(data_dir())
    if cmd == "ticker":
        if len(argv) < 3:
            raise HhpError("BAD_ARGS", "Thiếu mã cổ phiếu. " + USAGE)
        tk = argv[2].strip().upper()
        if not TICKER_RE.fullmatch(tk):
            raise HhpError("BAD_ARGS", "Mã không hợp lệ: %r (chỉ 2–6 ký tự A–Z, 0–9). %s" % (argv[2], USAGE))
        return build_ticker(data_dir(), tk)
    if cmd == "history":
        return build_history(data_dir())
    raise HhpError("BAD_ARGS", "Lệnh không hỗ trợ: %r. %s" % (argv[1], USAGE))


def emit(obj):
    text = json.dumps(clean(obj), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    buf = getattr(sys.stdout, "buffer", None)
    if buf is not None:
        buf.write(text.encode("utf-8") + b"\n")
        buf.flush()
    else:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()


def main(argv=None):
    argv = sys.argv if argv is None else argv
    try:
        out = run(argv)
    except HhpError as exc:
        out = {"error": exc.message, "error_code": exc.code}
    except Exception as exc:  # never let a traceback replace the JSON envelope
        out = {"error": "Lỗi nội bộ hhp_valuation.py: %s: %s" % (type(exc).__name__, exc), "error_code": "INTERNAL"}
    emit(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
