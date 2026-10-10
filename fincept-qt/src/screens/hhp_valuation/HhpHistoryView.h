// src/screens/hhp_valuation/HhpHistoryView.h
// VNINDEX TOÀN SỬ (28/07/2000→) view helpers of ĐỊNH GIÁ HHP — header-only, included by HhpValuationPanel.cpp only.
// Input = the `history` block of `hhp_valuation.py history` (schema hhp_vnindex_history/1): the daily price line 2000→,
// P/E·P/B bands of the LONG window (from long.from), sparse sourced ratio points ◇ before long.from (another basket or
// definition — never given a σ), the long-window forecast and the per-event readings merged into `keynotes`.
// Nothing here computes a number: every value, date and tier is read from the payload and HTML-escaped.
#pragma once

#include "screens/hhp_valuation/HhpChart.h"
#include "screens/hhp_valuation/HhpCommon.h"
#include "screens/hhp_valuation/HhpForecastView.h"

#include <QDate>
#include <QDateTime>
#include <QJsonArray>
#include <QJsonObject>
#include <QStringList>
#include <QTimeZone>

#include <algorithm>
#include <cmath>

namespace fincept::screens::hhp::hist {

constexpr double kYearMs = 365.25 * 86400000.0;

using fcview::date_vn;
using fcview::esc;
using fcview::span;
using fcview::tier_chip;

/// "2011-01-04" → "01/2011"; unparsable → as is.
inline QString month_vn(const QString& iso) {
    const QDate d = QDate::fromString(iso.left(10), Qt::ISODate);
    return d.isValid() ? d.toString(QStringLiteral("MM/yyyy")) : iso;
}

/// epoch ms → "MM/yyyy" (UTC).
inline QString month_of(qreal ms) {
    return QDateTime::fromMSecsSinceEpoch(static_cast<qint64>(ms), QTimeZone::UTC).toString(QStringLiteral("MM/yyyy"));
}

/// "+0.06" / "-3.84" (plain, like the other ratio figures); NaN → "—".
inline QString signed_num(double v, int decimals) {
    if (!has(v))
        return QStringLiteral("—");
    return (v > 0 ? QStringLiteral("+") : QString()) + fmt_ratio(v, decimals);
}

/// A share 0…1 (the contract: "tỷ lệ số tuần ≤ now") → "18.5%"; a value > 1 is taken as already in percent.
inline QString pct_text(double share) {
    if (!has(share))
        return QStringLiteral("—");
    return fmt_ratio(share > 1.0 ? share : share * 100.0, 1) + QStringLiteral("%");
}

/// First date of the long band: long.from, else the first chart point (long null = anchor mismatch, bands kept).
inline QString band_from_iso(const QJsonObject& hm) {
    const QString from = hm.value(QStringLiteral("long")).toObject().value(QStringLiteral("from")).toString();
    if (!from.isEmpty())
        return from;
    const QVector<QPointF> fair =
        to_points(hm.value(QStringLiteral("chart")).toObject().value(QStringLiteral("fair")).toArray());
    return fair.isEmpty() ? QString()
                          : QDateTime::fromMSecsSinceEpoch(static_cast<qint64>(fair.first().x()), QTimeZone::UTC)
                                .date()
                                .toString(Qt::ISODate);
}

// ── Series ───────────────────────────────────────────────────────────────────

/// Long-window price bands (one x-grid from long.from): cheap −2σ…−1σ, rich +1σ…+2σ, mean. Empty when an edge is missing.
inline QVector<HhpChartSeries> band_series(const QJsonObject& chart) {
    const auto pts = [&chart](const char* key) { return to_points(chart.value(QLatin1String(key)).toArray()); };
    const QVector<QPointF> fair = pts("fair"), c1 = pts("cheap1"), c2 = pts("cheap2"), r1 = pts("rich1"),
                           r2 = pts("rich2");
    if (fair.isEmpty() || c1.isEmpty() || c2.isEmpty() || r1.isEmpty() || r2.isEmpty())
        return {};
    const auto make = [](HhpChartSeries::Kind kind, const QString& name, const QColor& color, double width,
                         double opacity, const QVector<QPointF>& upper, const QVector<QPointF>& lower) {
        HhpChartSeries s;
        s.kind = kind;
        s.name = name;
        s.color = color;
        s.width = width;
        s.opacity = opacity;
        s.points = upper;
        s.lower = lower;
        return s;
    };
    return {make(HhpChartSeries::Kind::Band, QStringLiteral("Vùng rẻ dài hạn (−2σ…−1σ)"), c_cheap(), 1.6, 0.30, c1, c2),
            make(HhpChartSeries::Kind::Band, QStringLiteral("Vùng mắc dài hạn (+1σ…+2σ)"), c_rich(), 1.6, 0.26, r2, r1),
            make(HhpChartSeries::Kind::Dashed, QStringLiteral("TB dài hạn"), c_fair(), 1.2, 1.0, fair, {})};
}

// ── Sparse ratio points ◇ (before long.from) ─────────────────────────────────

/// Vietnamese caption of a point's `basis` (unknown keys shown as they are).
inline QString basis_text(const QString& basis) {
    if (basis == QLatin1String("market_trailing"))
        return QStringLiteral("P/E bình quân toàn thị trường, trailing");
    if (basis == QLatin1String("top30_hcm_hn"))
        return QStringLiteral("Bình quân 30 công ty niêm yết lớn nhất HCM + HN");
    if (basis == QLatin1String("hose_avg_chart"))
        return QStringLiteral("P/E bình quân HOSE — đọc từ biểu đồ");
    if (basis == QLatin1String("aggregate_eps2008"))
        return QStringLiteral("Tổng vốn hoá / tổng lợi nhuận năm 2008");
    if (basis == QLatin1String("unknown") || basis.isEmpty())
        return QStringLiteral("Nguồn không nêu cơ sở tính");
    return basis;
}

/// "≈36x" (approx), "≥40x" (lower bound), "53.6x" (point).
inline QString point_value_text(const QJsonObject& p) {
    const QString kind = p.value(QStringLiteral("value_kind")).toString();
    const QString prefix = kind == QLatin1String("approx")        ? QStringLiteral("≈")
                           : kind == QLatin1String("lower_bound") ? QStringLiteral("≥")
                                                                  : QString();
    return prefix + fmt_ratio(num(p.value(QStringLiteral("v"))), 2) + QStringLiteral("x");
}

/// "org — title — dd/MM/yyyy — domain · loc" (plain text).
inline QString source_text(const QJsonObject& s) {
    QStringList parts;
    for (const char* key : {"org", "title"}) {
        const QString t = s.value(QLatin1String(key)).toString().trimmed();
        if (!t.isEmpty())
            parts << t;
    }
    const QString date = s.value(QStringLiteral("date")).toString();
    if (!date.isEmpty())
        parts << date_vn(date);
    const QString url = s.value(QStringLiteral("url")).toString();
    const QString where = url.isEmpty() ? s.value(QStringLiteral("file")).toString() : fcview::domain(url);
    if (!where.isEmpty())
        parts << where;
    QString t = parts.join(QStringLiteral(" — "));
    const QString loc = s.value(QStringLiteral("loc")).toString().trimmed();
    if (!loc.isEmpty())
        t += QStringLiteral(" · ") + loc;
    return t;
}

/// Card of one ◇ point (Qt rich text, same dark frame as the keynote cards). No σ anywhere: the point measures another
/// basket or definition than the long band, so only the long-window μ is quoted, as a reference.
inline QString ratio_point_html(const QJsonObject& p, const QString& metric, const QJsonObject& long_block) {
    const QString m = metric == QLatin1String("pb") ? QStringLiteral("P/B") : QStringLiteral("P/E");
    const QString vs = p.value(QStringLiteral("vs_long_mean")).toString();
    const QColor head_c = vs == QLatin1String("above") ? c_rich() : vs == QLatin1String("below") ? c_cheap() : c_gold();
    QString head = QStringLiteral("◇ ĐIỂM ĐỊNH GIÁ RỜI · ") + date_vn(p.value(QStringLiteral("date")).toString());
    const double close = num(p.value(QStringLiteral("close")));
    if (has(close))
        head += QStringLiteral(" · VNINDEX ") + fcview::level(close);

    QString h = fcview::card_open();
    h += QStringLiteral("<div style=\"color:%1; font-weight:bold; font-size:12px;\">%2</div>").arg(css(head_c), esc(head));
    const QString tier = p.value(QStringLiteral("tier")).toString();
    h += QStringLiteral("<div style=\"color:%1; font-weight:bold; font-size:14px; margin-top:3px;\">%2 %3</div>")
             .arg(css(c_text()), esc(m + QStringLiteral(" ") + point_value_text(p)), tier_chip(tier));
    const QJsonObject period = p.value(QStringLiteral("period")).toObject();
    const QString p_from = period.value(QStringLiteral("from")).toString();
    const QString p_to = period.value(QStringLiteral("to")).toString();
    if (!p_from.isEmpty() && !p_to.isEmpty())
        h += QStringLiteral("<div style=\"color:%1;\">%2</div>")
                 .arg(css(c_text()), esc(QStringLiteral("Bình quân kỳ %1–%2").arg(date_vn(p_from), date_vn(p_to))));

    QString basis = basis_text(p.value(QStringLiteral("basis")).toString());
    const QString def = p.value(QStringLiteral("definition")).toString().trimmed();
    h += fcview::section(QStringLiteral("CƠ SỞ TÍNH"),
                         span(esc(basis) + (def.isEmpty() ? QString() : QStringLiteral("<br>") + esc(def)), c_text()));
    const QJsonObject src = p.value(QStringLiteral("src")).toObject();
    h += fcview::section(QStringLiteral("NGUỒN"), span(esc(source_text(src)), c_text()) + QStringLiteral(" ") +
                                                       tier_chip(src.value(QStringLiteral("tier")).toString(tier)));

    QStringList also;
    for (const QJsonValue& av : p.value(QStringLiteral("also")).toArray()) {
        const QJsonObject a = av.toObject();
        QString line = m + QStringLiteral(" ") + point_value_text(a) + QStringLiteral(" · ") +
                       basis_text(a.value(QStringLiteral("basis")).toString());
        const QString ad = a.value(QStringLiteral("date")).toString();
        if (!ad.isEmpty())
            line += QStringLiteral(" · ") + date_vn(ad);
        const QString as = source_text(a.value(QStringLiteral("src")).toObject());
        if (!as.isEmpty())
            line += QStringLiteral(" · ") + as;
        also << span(esc(line), c_text()) + QStringLiteral(" ") + tier_chip(a.value(QStringLiteral("tier")).toString());
    }
    if (!also.isEmpty())
        h += fcview::section(QStringLiteral("CÁC SỐ KHÁC ±7 NGÀY"), also.join(QStringLiteral("<br>")));
    const QString note = p.value(QStringLiteral("note")).toString().trimmed();
    if (!note.isEmpty())
        h += fcview::section(QStringLiteral("GHI CHÚ"), span(esc(note), c_muted()));

    const double mean = num(long_block.value(QStringLiteral("mean")));
    if (has(mean))
        h += QStringLiteral("<div style=\"margin-top:6px; color:%1;\">%2</div>")
                 .arg(css(c_muted()),
                      esc(QStringLiteral("μ dài hạn %1→: %2 — khác rổ/định nghĩa, chỉ tham khảo")
                              .arg(month_vn(long_block.value(QStringLiteral("from")).toString()), fmt_ratio(mean, 2))));
    h += QStringLiteral("<div style=\"margin-top:6px; color:%1; font-size:10px;\">Điểm rời có nguồn — không nội suy, không "
                        "dùng để tính dải. Tham khảo, không khuyến nghị.</div>")
             .arg(css(c_muted()));
    return h + fcview::card_close();
}

/// ◇ markers at the day's close: ExtremeHigh above the long mean, ExtremeLow below, ExtremeHigh when unknown (lower
/// bound). Always hollow (dotted outline), never labelled, priority 3. Points without a date or close are skipped.
inline QVector<HhpChartNote> ratio_point_notes(const QJsonArray& points, const QString& metric,
                                               const QJsonObject& long_block) {
    QVector<HhpChartNote> out;
    for (const QJsonValue& v : points) {
        const QJsonObject p = v.toObject();
        const double ms = fcview::ms_of(p, "ms", "date");
        const double close = num(p.value(QStringLiteral("close")));
        if (!has(ms) || !has(close))
            continue;
        HhpChartNote n;
        n.id = p.value(QStringLiteral("id")).toString();
        if (n.id.isEmpty())
            n.id = QStringLiteral("rp-") + p.value(QStringLiteral("date")).toString();
        n.kind = p.value(QStringLiteral("vs_long_mean")).toString() == QLatin1String("below")
                     ? HhpChartNote::Kind::ExtremeLow
                     : HhpChartNote::Kind::ExtremeHigh;
        n.x_ms = ms;
        n.y = close; // label stays empty: a ◇ is never labelled on the chart (its card carries everything)
        n.detail_html = ratio_point_html(p, metric, long_block);
        n.priority = 3;
        n.hollow = true;
        out.append(n);
    }
    return out;
}

// ── Label density ────────────────────────────────────────────────────────────

/// Years on screen: YTD → the elapsed part of this year; nY → n; ALL → (last − first x) / 365,25 d.
inline double years_visible(const QString& range, qreal first_ms, qreal last_ms) {
    if (range == QLatin1String("ALL"))
        return (has(first_ms) && has(last_ms) && last_ms > first_ms) ? (last_ms - first_ms) / kYearMs : 0.0;
    const qreal now = static_cast<qreal>(QDateTime::currentMSecsSinceEpoch());
    const qreal cut = range_cutoff(range, now);
    return cut > 0 ? (now - cut) / kYearMs : 0.0;
}

/// R4 §5.5 on keynote markers (priority = priority_full already): ≤ 6 years every label + sub; 6–12 years P3 without sub;
/// > 12 years P2 without sub, P3 marker only. ◆ targets keep their label; ◇ never have one. Markers always stay.
inline QVector<HhpChartNote> thin_labels(QVector<HhpChartNote> notes, double years) {
    for (HhpChartNote& n : notes) {
        if (n.kind != HhpChartNote::Kind::Peak && n.kind != HhpChartNote::Kind::Trough)
            continue;
        const int pr = std::clamp(n.priority, 1, 3);
        if (years > 12.0) {
            if (pr == 2)
                n.sub.clear();
            else if (pr == 3) {
                n.label.clear();
                n.sub.clear();
            }
        } else if (years > 6.0 && pr == 3) {
            n.sub.clear();
        }
    }
    return notes;
}

// ── Stat tooltip + note lines ────────────────────────────────────────────────

/// One window of the stat tooltip ("σ 8 NĂM" / "σ DÀI HẠN"): from→to, n, μ, σ, method, tier.
inline QString window_lines(const QString& caption, const QJsonObject& w) {
    if (w.isEmpty())
        return QStringLiteral("<b>%1</b>: %2").arg(esc(caption), esc(QStringLiteral("[CẦN DATA]")));
    QStringList parts;
    const QString from = w.value(QStringLiteral("from")).toString();
    const QString to = w.value(QStringLiteral("to")).toString();
    if (!from.isEmpty())
        parts << date_vn(from) + QStringLiteral("→") + (to.isEmpty() ? QString() : date_vn(to));
    const double nw = num(w.value(QStringLiteral("n_weeks")));
    if (has(nw))
        parts << QStringLiteral("%1 tuần").arg(qRound(nw));
    parts << QStringLiteral("μ %1 · σ %2").arg(fmt_ratio(num(w.value(QStringLiteral("mean"))), 2),
                                             fmt_ratio(num(w.value(QStringLiteral("sd"))), 2));
    parts << QStringLiteral("hiện tại %1σ").arg(fmt_sigma(num(w.value(QStringLiteral("sigma")))));
    const double pct = num(w.value(QStringLiteral("pct")));
    if (has(pct))
        parts << QStringLiteral("phân vị %1").arg(pct_text(pct));
    QString h = QStringLiteral("<b>%1</b>: %2").arg(esc(caption), esc(parts.join(QStringLiteral(" · "))));
    const QString tier = w.value(QStringLiteral("tier")).toString();
    if (!tier.isEmpty())
        h += QStringLiteral(" ") + tier_chip(tier);
    for (const char* key : {"method", "pct_method"}) {
        const QString t = w.value(QLatin1String(key)).toString().trimmed();
        if (!t.isEmpty())
            h += QStringLiteral("<br>&nbsp;&nbsp;") + span(esc(t), c_muted());
    }
    const QJsonObject check = w.value(QStringLiteral("check")).toObject();
    if (!check.isEmpty())
        h += QStringLiteral("<br>&nbsp;&nbsp;") +
             span(esc(QStringLiteral("tự kiểm theo tuần: μ %1 · σ %2 · %3")
                          .arg(fmt_ratio(num(check.value(QStringLiteral("mean_w"))), 2),
                               fmt_ratio(num(check.value(QStringLiteral("sd_w"))), 2),
                               check.value(QStringLiteral("ok")).toBool() ? QStringLiteral("khớp engine")
                                                                          : QStringLiteral("LỆCH engine"))),
                  c_muted());
    return h;
}

/// Stat tooltip in TOÀN SỬ: both windows, the seam, the vendor's own published μ/σ and the warnings (escaped).
inline QString windows_tooltip_html(const QJsonObject& hm, const QStringList& warnings) {
    QStringList rows;
    const QJsonObject eight = hm.value(QStringLiteral("eight")).toObject();
    const QJsonObject lng = hm.value(QStringLiteral("long")).toObject();
    rows << window_lines(QStringLiteral("σ 8 NĂM (engine)"), eight);
    rows << window_lines(QStringLiteral("σ DÀI HẠN"), lng);
    const QJsonObject seam = hm.value(QStringLiteral("seam")).toObject();
    if (!seam.isEmpty()) {
        QStringList s;
        s << QStringLiteral("nối %1").arg(date_vn(seam.value(QStringLiteral("date")).toString()));
        const QString grid = seam.value(QStringLiteral("grid_date")).toString();
        if (!grid.isEmpty())
            s << QStringLiteral("điểm lưới %1").arg(date_vn(grid));
        const double n = num(seam.value(QStringLiteral("overlap_n")));
        if (has(n))
            s << QStringLiteral("chồng lấn %1 phiên, trung vị %2 (P10 %3 · P90 %4)")
                     .arg(QString::number(qRound(n)), fmt_ratio(num(seam.value(QStringLiteral("median"))), 4),
                          fmt_ratio(num(seam.value(QStringLiteral("p10"))), 4),
                          fmt_ratio(num(seam.value(QStringLiteral("p90"))), 4));
        s << QStringLiteral("bước nối %1% (nhà cung cấp tự đi %2%, thừa %3 điểm %)")
                 .arg(signed_num(num(seam.value(QStringLiteral("jump_pct"))), 2),
                      signed_num(num(seam.value(QStringLiteral("vendor_own_move_pct"))), 2),
                      signed_num(num(seam.value(QStringLiteral("excess_pp"))), 2));
        QString line = QStringLiteral("<b>%1</b>: %2").arg(esc(QStringLiteral("Mối nối")), esc(s.join(QStringLiteral(" · "))));
        const QString rule = seam.value(QStringLiteral("rule")).toString().trimmed();
        if (!rule.isEmpty())
            line += QStringLiteral("<br>&nbsp;&nbsp;") + span(esc(rule), c_muted());
        rows << line;
    }
    const QJsonObject vp = lng.value(QStringLiteral("vendor_published")).toObject();
    if (!vp.isEmpty()) {
        QString line = esc(QStringLiteral("%1 tự công bố: μ %2 · σ %3")
                               .arg(vp.value(QStringLiteral("org")).toString(QStringLiteral("[CẦN DATA]")),
                                    fmt_ratio(num(vp.value(QStringLiteral("mean"))), 2),
                                    fmt_ratio(num(vp.value(QStringLiteral("sd"))), 2)));
        const QString vd = vp.value(QStringLiteral("date")).toString();
        if (!vd.isEmpty())
            line += esc(QStringLiteral(" (%1)").arg(date_vn(vd)));
        line += QStringLiteral(" ") + tier_chip(vp.value(QStringLiteral("tier")).toString());
        const QString vn = vp.value(QStringLiteral("note")).toString().trimmed();
        line += span(esc(QStringLiteral(" — ") + (vn.isEmpty() ? QStringLiteral("không winsorize") : vn)), c_muted());
        rows << line;
    }
    if (!warnings.isEmpty()) {
        QStringList w;
        for (const QString& t : warnings)
            w << esc(QStringLiteral("⚠ ") + t);
        rows << span(w.join(QStringLiteral("<br>")), c_rich());
    }
    return rows.join(QStringLiteral("<br>"));
}

/// Note line 1 from price.src_spans (run-length or one span per source): "28/07/2000–31/12/2003 CafeF (đối chiếu
/// SSI·DNSE) · 05/01/2004→ Vietcap (vá n phiên theo CafeF) · đuôi vnstore [FACT-T2]". Plain text.
inline QString price_spans_text(const QJsonArray& spans) {
    struct Sp {
        QString from, to, src, tier;
        int n = 0;
    };
    QVector<Sp> v;
    for (const QJsonValue& sv : spans) {
        const QJsonObject o = sv.toObject();
        const QString src = o.value(QStringLiteral("src")).toString();
        if (src.isEmpty())
            continue;
        v.append({o.value(QStringLiteral("from")).toString(), o.value(QStringLiteral("to")).toString(), src,
                  o.value(QStringLiteral("tier")).toString(), o.value(QStringLiteral("n")).toInt(0)});
    }
    if (v.isEmpty())
        return {};
    std::stable_sort(v.begin(), v.end(), [](const Sp& a, const Sp& b) { return a.from < b.from; });
    QStringList parts;
    QStringList tiers;
    for (const Sp& s : std::as_const(v))
        if (!s.tier.isEmpty() && !tiers.contains(s.tier))
            tiers << s.tier;
    // Leading CafeF run (2000–2003), then the Vietcap body with every later CafeF run counted as a patch, then the tails.
    qsizetype i = 0;
    if (v.first().src == QLatin1String("cf")) {
        QString to = v.first().to;
        while (i < v.size() && v.at(i).src == QLatin1String("cf"))
            to = v.at(i++).to;
        parts << QStringLiteral("%1–%2 CafeF (đối chiếu SSI·DNSE)").arg(date_vn(v.first().from), date_vn(to));
    }
    const auto first_of = [&](const char* src) -> qsizetype {
        for (qsizetype k = i; k < v.size(); ++k)
            if (v.at(k).src == QLatin1String(src))
                return k;
        return -1;
    };
    const qsizetype vc = first_of("vc");
    if (vc >= 0) {
        int patched = 0;
        for (qsizetype k = vc; k < v.size(); ++k)
            patched += v.at(k).src == QLatin1String("cf") ? std::max(1, v.at(k).n) : 0;
        parts << QStringLiteral("%1→ Vietcap").arg(date_vn(v.at(vc).from)) +
                     (patched > 0 ? QStringLiteral(" (vá %1 phiên theo CafeF)").arg(patched) : QString());
    }
    const qsizetype vs = first_of("vs");
    if (vs >= 0)
        parts << QStringLiteral("đuôi vnstore %1→").arg(date_vn(v.at(vs).from));
    const qsizetype en = first_of("en");
    if (en >= 0)
        parts << QStringLiteral("đuôi engine %1→ (vnstore trễ)").arg(date_vn(v.at(en).from));
    QString t = QStringLiteral("Giá: ") + parts.join(QStringLiteral(" · "));
    if (!tiers.isEmpty())
        t += QStringLiteral(" [") + tiers.join(QStringLiteral("/")) + QStringLiteral("]");
    return t;
}

/// Note line 2: "Dải σ dài hạn: Vietcap IQ <long.from>→<last pre-seam point> nối VnDirect finfo <seam.date>→ tại ngày hai
/// nguồn khớp (bước thừa <excess_pp> điểm %) · μ/σ winsorize P5–P95 trên chuỗi tuần [EST]". Plain text; dates from the
/// payload (the last pre-seam date = the band's last x before the seam).
inline QString band_note_text(const QJsonObject& hm) {
    const QJsonObject seam = hm.value(QStringLiteral("seam")).toObject();
    const QString from = band_from_iso(hm);
    const QString seam_iso = seam.value(QStringLiteral("date")).toString();
    const double seam_ms = fcview::iso_ms(seam_iso);
    QString before;
    if (has(seam_ms)) {
        const QVector<QPointF> fair =
            to_points(hm.value(QStringLiteral("chart")).toObject().value(QStringLiteral("fair")).toArray());
        for (const QPointF& p : fair) {
            if (p.x() >= seam_ms)
                break;
            before = fmt_date(p.x());
        }
    }
    QString t = QStringLiteral("Dải σ dài hạn: Vietcap IQ %1→%2").arg(date_vn(from), before);
    if (!seam_iso.isEmpty())
        t += QStringLiteral(" nối VnDirect finfo %1→ tại ngày hai nguồn khớp (bước thừa %2 điểm %)")
                 .arg(date_vn(seam_iso), signed_num(num(seam.value(QStringLiteral("excess_pp"))), 2));
    t += QStringLiteral(" · μ/σ winsorize P5–P95 trên chuỗi tuần");
    const QString tier = hm.value(QStringLiteral("long")).toObject().value(QStringLiteral("tier")).toString();
    t += QStringLiteral(" [%1]").arg(tier.isEmpty() ? QStringLiteral("EST") : tier);
    return t;
}

/// Note line 3: why there is no band before long.from and what ◇ is. Plain text.
inline QString pre_band_note_text(const QJsonObject& hm, const QString& metric) {
    const bool book = metric == QLatin1String("pb");
    return QStringLiteral("Trước %1 không có chuỗi %2 liên tục đạt chuẩn (%3) — ◇ = điểm định giá rời có nguồn, khác "
                          "định nghĩa; rê chuột để xem.")
        .arg(date_vn(band_from_iso(hm)), book ? QStringLiteral("P/B") : QStringLiteral("P/E"),
             book ? QStringLiteral("Vietcap 2009 nhiễu BVPS") : QStringLiteral("Vietcap 2009–2010 dùng EPS cũ/nhiễu"));
}

} // namespace fincept::screens::hhp::hist
