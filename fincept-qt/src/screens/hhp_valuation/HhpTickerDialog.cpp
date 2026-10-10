// src/screens/hhp_valuation/HhpTickerDialog.cpp — port of the per-ticker modal in
// hhp_vn100_valuation.html (openBand / drawTickerBand / renderFwd). See HhpTickerDialog.h.
#include "screens/hhp_valuation/HhpTickerDialog.h"

#include "screens/hhp_valuation/HhpChart.h"
#include "screens/hhp_valuation/HhpCommon.h"
#include "screens/hhp_valuation/HhpForecastView.h"

#include <QDate>
#include <QDateTime>
#include <QGuiApplication>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QJsonArray>
#include <QLabel>
#include <QMap>
#include <QPalette>
#include <QPushButton>
#include <QRegularExpression>
#include <QScreen>
#include <QScrollArea>
#include <QTableWidget>
#include <QVBoxLayout>

#include <algorithm>
#include <cmath>

namespace fincept::screens::hhp {

namespace {

constexpr double kPriceMismatch = 0.05; // chart vs screener price gap worth flagging
constexpr int kFwdRowH = 26;
constexpr int kPlotMinH = 840;      // 2 × the former 420 px: the band chart read too flat
constexpr int kDialogW = 1040;
constexpr int kDialogMaxH = 1180;
constexpr int kScreenMargin = 60;   // dialog height = min(available height − this, kDialogMaxH)
constexpr int kMaxShownWarn = 3;    // forecast warnings printed on the dialog (all of them go in the tooltip)
constexpr int kFcYears = 4;         // growth years on the stat line (2026…2029)

QString metric_label(const QString& metric) {
    return metric == QLatin1String("pb") ? QStringLiteral("P/B") : QStringLiteral("P/E");
}

QString pill_style(bool on) {
    if (on)
        return QStringLiteral("QPushButton { background:%1; color:#1a1208; border:1px solid %1; border-radius:8px;"
                              " padding:5px 16px; font-size:12px; font-weight:700; }")
            .arg(css(c_gold()));
    return QStringLiteral("QPushButton { background:%1; color:%2; border:1px solid %3; border-radius:8px;"
                          " padding:5px 16px; font-size:12px; font-weight:700; }"
                          "QPushButton:hover { color:%4; border-color:%4; }")
        .arg(css(c_card()), css(c_muted()), css(c_line()), css(c_gold()));
}

QString muted_html(const QString& text) {
    return QStringLiteral("<span style='color:%1;'>%2</span>").arg(css(c_muted()), text.toHtmlEscaped());
}

/// One stat block of the page's .mbstat row: small muted caption over a bold value.
/// `value_html` must already be escaped.
QString stat_cell(const QString& caption, const QString& value_html, const QColor& color, int px = 18) {
    return QStringLiteral("<td style='padding-right:28px;'>"
                          "<div style='color:%1; font-size:11px;'>%2</div>"
                          "<div style='color:%3; font-size:%4px; font-weight:700;'>%5</div></td>")
        .arg(css(c_muted()), caption.toHtmlEscaped(), css(color), QString::number(px), value_html);
}

/// "2026-09-23" → "23/09/2026"; anything else unchanged.
QString vi_date(const QString& iso) {
    const QDate d = QDate::fromString(iso, Qt::ISODate);
    return d.isValid() ? d.toString(QStringLiteral("dd/MM/yyyy")) : iso;
}

/// Same grades as the screener: CapIQ's English out/under-perform, which rec_color() leaves grey.
QColor ciq_rec_color(const QString& rec) {
    const QString u = rec.toUpper();
    if (u.contains(QLatin1String("UNDERPERFORM")))
        return c_rich();
    if (u.contains(QLatin1String("OUTPERFORM")))
        return c_cheap();
    return rec_color(rec);
}

/// Line under "Giá hiện tại": the screener row's price (đồng) and where it comes from (price_src, fixed
/// upstream). Escaped html; "" when the row has no price source (older pipeline output).
QString price_source_html(const QJsonObject& row) {
    const QString src = row.value(QStringLiteral("price_src")).toString();
    if (src.isEmpty())
        return {};
    const QString px = fmt_vi(num(row.value(QStringLiteral("price_now")))) + QStringLiteral(" đ");
    if (src == QLatin1String("simplize_stale"))
        return QStringLiteral("<span style='color:%1;'>%2</span>")
            .arg(css(c_rich()), QStringLiteral("⚠ giá Simplize cũ %1 — không có dữ liệu Vietcap").arg(px).toHtmlEscaped());
    const QDateTime t = QDateTime::fromString(row.value(QStringLiteral("price_time")).toString(), Qt::ISODate);
    const QString when = t.isValid() ? t.toString(QStringLiteral("dd/MM/yyyy HH:mm"))
                                     : vi_date(row.value(QStringLiteral("price_date")).toString());
    QString text;
    if (src == QLatin1String("vietcap_board"))
        text = QStringLiteral("Vietcap %1 · %2 (bảng giá)").arg(px, when);
    else if (src == QLatin1String("vietcap_history"))
        text = QStringLiteral("Vietcap %1 · %2 (lịch sử)").arg(px, when);
    else if (src == QLatin1String("vnd_dchart"))
        text = QStringLiteral("VnDirect DCHART %1 · %2 (dự phòng)").arg(px, when);
    else
        text = QStringLiteral("%1 · %2").arg(src, px);
    return muted_html(text);
}

/// capiq.ttm.asof {screen slug: ISO day} → "22/09/2026: fundamental; 23/09/2026: estimates, key_stats" (plain).
QString ciq_asof_text(const QJsonObject& asof) {
    QMap<QString, QStringList> by_day; // ISO day → slugs; QMap keeps the days in order
    for (auto it = asof.begin(); it != asof.end(); ++it) {
        const QString day = it.value().toString();
        by_day[day.isEmpty() ? QStringLiteral("?") : day] << it.key();
    }
    QStringList parts;
    for (auto it = by_day.cbegin(); it != by_day.cend(); ++it)
        parts << vi_date(it.key()) + QStringLiteral(": ") + it.value().join(QStringLiteral(", "));
    return parts.join(QStringLiteral("; "));
}

/// "CIQ hiện tại" lines of the S&P CapIQ block, from capiq.ttm — the screener's CapIQ tooltip lines, the
/// CIQ and [EST] multiples on one line: CapIQ's own current P/E·P/B, the [EST] ratios derived upstream (not
/// CapIQ figures), LTM figures; each screen's export day in the heading. Escaped html; {} when ttm has no value.
QStringList ciq_now_html(const QJsonObject& t) {
    const auto val = [&t](const char* key) { return num(t.value(QLatin1String(key))); };
    const auto ratio = [&val](const char* key) { return has(val(key)) ? fmt_ratio(val(key)) : QString(); };
    const auto pct = [&val](const char* key) {
        return has(val(key)) ? fmt_ratio(val(key), 1) + QLatin1Char('%') : QString();
    };
    const auto dong = [&val](const char* key) {
        return has(val(key)) ? fmt_vi(val(key)) + QStringLiteral(" đ") : QString();
    };
    const auto part = [](const char* label, const QString& value) {
        return value.isEmpty() ? QString()
                               : QString::fromUtf8(label).toHtmlEscaped() + QStringLiteral(" <b>") +
                                     value.toHtmlEscaped() + QStringLiteral("</b>");
    };
    // Non-empty parts joined by " · ", then a muted `tag` ("(CIQ)" / "[EST]"); "" when every part is empty.
    const auto group = [](const QStringList& parts, const QString& tag = QString()) {
        QStringList kept;
        for (const QString& p : parts) {
            if (!p.isEmpty())
                kept << p;
        }
        if (kept.isEmpty())
            return QString();
        return kept.join(QStringLiteral(" · ")) + (tag.isEmpty() ? QString() : QStringLiteral(" ") + muted_html(tag));
    };
    const double mcap_b = val("mcap_b"); // tỷ đồng
    const QStringList candidates = {
        group({group({part("P/E", ratio("pe")), part("P/B", ratio("pb"))}, QStringLiteral("(CIQ)")),
               group({part("P/E TTM", ratio("pe_ttm_est")), part("P/B BV FY0", ratio("pb_fy0bv_est"))},
                     QStringLiteral("[EST]"))}),
        group({part("EPS LTM", dong("eps_ltm")), part("BVPS LTM", dong("bvps_ltm")), part("ROE FY0", pct("roe_fy0"))}),
        group({part("Cổ tức", pct("div_yield")),
               part("Vốn hoá", has(mcap_b) ? fmt_vi(mcap_b / 1000.0, 1) + QStringLiteral(" nghìn tỷ đ") : QString()),
               part("EV/EBITDA fwd", ratio("ev_ebitda_fwd"))}),
        group({part("Tăng trưởng DT LTM", has(val("rev_g_ltm")) ? fmt_pct(val("rev_g_ltm")) : QString()),
               part("biên LN ròng", pct("npm_ltm"))}),
    };
    QStringList lines;
    for (const QString& l : candidates) {
        if (!l.isEmpty())
            lines << l;
    }
    if (lines.isEmpty())
        return lines;
    QString head = QStringLiteral("<b>CIQ hiện tại</b>");
    const QString asof = ciq_asof_text(t.value(QStringLiteral("asof")).toObject());
    if (!asof.isEmpty())
        head += QStringLiteral(" ") + muted_html(QStringLiteral("· xuất ") + asof);
    lines.prepend(head);
    return lines;
}

/// "S&P CapIQ" block of the forward section, from row.capiq. Escaped html; "" when the row has no
/// "capiq" key at all (older script), a muted "no data" line when it is null (no export read, or the
/// ticker is not in it — the row alone cannot tell which).
QString capiq_html(const QJsonObject& row) {
    if (!row.contains(QStringLiteral("capiq")))
        return {};
    const QString title = QStringLiteral("<b style='color:%1;'>S&amp;P CapIQ</b>").arg(css(c_gold()));
    const QJsonValue qv = row.value(QStringLiteral("capiq"));
    if (!qv.isObject())
        return title + QStringLiteral(" ") + muted_html(QStringLiteral("— không có dữ liệu CapIQ cho mã này"));
    const QJsonObject q = qv.toObject();
    const auto val = [&q](const char* key) { return num(q.value(QLatin1String(key))); };
    const auto bold = [](const QString& text) { return QStringLiteral("<b>%1</b>").arg(text.toHtmlEscaped()); };

    QString head = title;
    const QString exported = q.value(QStringLiteral("exported")).toString();
    if (!exported.isEmpty())
        head += QStringLiteral(" ") + muted_html(QStringLiteral("· xuất ") + vi_date(exported));
    QStringList lines = {head};

    QStringList mult;
    if (has(val("pe")))
        mult << QStringLiteral("P/E 26F ") + bold(fmt_ratio(val("pe")));
    if (has(val("pb")))
        mult << QStringLiteral("P/B 26F ") + bold(fmt_ratio(val("pb")));
    if (has(val("roe_est")))
        mult << QStringLiteral("ROE dự phóng ") + bold(fmt_ratio(val("roe_est")) + QLatin1Char('%'));
    if (!mult.isEmpty())
        lines << mult.join(QStringLiteral(" · "));

    QStringList tp_line;
    const double tp = val("tp");
    if (has(tp))
        tp_line << QStringLiteral("TP <b style='color:%1;'>%2</b> đ").arg(css(c_gold()), fmt_vi(tp));
    const QString rec = q.value(QStringLiteral("rec")).toString();
    if (!rec.isEmpty())
        tp_line << QStringLiteral("<b style='color:%1;'>%2</b>").arg(css(ciq_rec_color(rec)), rec.toHtmlEscaped()) +
                       (has(val("n_rec")) ? QStringLiteral(" (%1 KN)").arg(qRound(val("n_rec"))) : QString());
    const double up = val("upside_pct");
    if (has(up))
        tp_line << QStringLiteral("upside <span style='color:%1;'>%2</span> so với giá %3")
                       .arg(css(up >= 0 ? c_cheap() : c_rich()), fmt_pct(up).toHtmlEscaped(),
                            row.value(QStringLiteral("price_src")).toString().startsWith(QLatin1String("vietcap"))
                                ? QStringLiteral("Vietcap")
                                : QStringLiteral("bảng lọc"));
    if (!tp_line.isEmpty())
        lines << tp_line.join(QStringLiteral(" · "));

    QStringList est;
    if (has(val("eps_est")))
        est << QStringLiteral("EPS dự phóng %1 đ").arg(fmt_vi(val("eps_est")));
    if (has(val("bvps_est")))
        est << QStringLiteral("BVPS dự phóng %1 đ").arg(fmt_vi(val("bvps_est")));
    if (!est.isEmpty())
        lines << est.join(QStringLiteral(" · ")).toHtmlEscaped();
    lines << ciq_now_html(q.value(QStringLiteral("ttm")).toObject());
    return lines.join(QStringLiteral("<br>"));
}

/// @param stale  the overview row flags this ratio as stopped updating upstream (hhp_valuation.py "stale")
/// @param row    the overview row (data.row): its price_now / price_src go under the chart price
QString stats_html(const QJsonObject& b, const QString& m, const QString& unit, bool stale, const QJsonObject& row) {
    const double mean = num(b.value(QStringLiteral("mean")));
    const double sigma = num(b.value(QStringLiteral("sigma")));
    const QString zone = b.value(QStringLiteral("zone")).toString();
    QString sig = fmt_sigma(sigma) + (has(sigma) ? QStringLiteral("σ") : QString());
    if (!zone.isEmpty())
        sig += QStringLiteral(" · ") + zone;

    QString cells;
    cells += stat_cell(m + QStringLiteral(" hiện tại"), fmt_ratio(num(b.value(QStringLiteral("now")))), c_text());
    cells += stat_cell(m + QStringLiteral(" trung bình"),
                       has(mean) ? QString::number(mean, 'f', 2) : QStringLiteral("—"), c_muted());
    cells += stat_cell(QStringLiteral("Vị thế σ"), sig.toHtmlEscaped(),
                       zone_color(b.value(QStringLiteral("zone_key")).toString()));
    const QString px_src = price_source_html(row);
    cells += stat_cell(QStringLiteral("Giá hiện tại"),
                       fmt_vi(num(b.value(QStringLiteral("price_now"))), 1) +
                           QStringLiteral(" <span style='font-size:12px; font-weight:400;'>%1</span>")
                               .arg(unit.toHtmlEscaped()) +
                           (px_src.isEmpty() ? QString()
                                             : QStringLiteral("<div style='font-size:11px; font-weight:400;'>%1</div>")
                                                   .arg(px_src)),
                       c_gold());
    const QString as_of = b.value(QStringLiteral("as_of")).toString();
    if (!as_of.isEmpty()) {
        const QDate d = QDate::fromString(as_of, Qt::ISODate);
        cells += stat_cell(stale ? QStringLiteral("Dữ liệu dừng ở") : QStringLiteral("Ngày dữ liệu"),
                           (d.isValid() ? d.toString(QStringLiteral("dd/MM/yyyy")) : as_of).toHtmlEscaped(),
                           stale ? c_rich() : c_muted(), 14);
    }
    return QStringLiteral("<table cellspacing='0' cellpadding='0'><tr>") + cells + QStringLiteral("</tr></table>");
}

QString note_text(const QJsonObject& data, const QJsonObject& b, const QString& m) {
    QString s = QStringLiteral("Band = giá × (%1 trung bình ±1–2σ của CHÍNH mã, winsorize P5–P95). "
                               "Giá VnDirect DCHART (nghìn đồng, điều chỉnh) · ratio VnDirect finfo. ")
                    .arg(m);
    const QString generated = data.value(QStringLiteral("generated")).toString();
    if (!generated.isEmpty())
        s += QStringLiteral("Cập nhật ") + generated + QStringLiteral(". ");
    s += QStringLiteral("Tham khảo, không khuyến nghị.");

    // Known upstream split: the chart uses adjusted DCHART prices (nghìn đồng), the screener row
    // another price feed (đồng). Say so rather than silently showing two different "current" prices.
    const double chart_px = num(b.value(QStringLiteral("price_now")));
    const double row_px = num(data.value(QStringLiteral("row")).toObject().value(QStringLiteral("price_now")));
    if (has(chart_px) && has(row_px) && row_px > 0) {
        const double diff = chart_px * 1000.0 / row_px - 1.0;
        if (std::abs(diff) > kPriceMismatch)
            s += QStringLiteral("\nGiá cuối chart %1 nghìn đồng lệch %2 so với giá ở bảng lọc %3 đ — "
                                "hai nguồn giá khác nhau trong pipeline HHP.")
                     .arg(fmt_vi(chart_px, 1), fmt_pct(diff * 100.0), fmt_vi(row_px));
    }
    return s;
}

HhpChartSeries make_series(HhpChartSeries::Kind kind, const QString& name, const QColor& color, double width,
                           double opacity, const QJsonValue& points, const QJsonValue& lower = QJsonValue()) {
    HhpChartSeries s;
    s.kind = kind;
    s.name = name;
    s.color = color;
    s.width = width;
    s.opacity = opacity;
    s.points = to_points(points.toArray());
    s.lower = to_points(lower.toArray());
    return s;
}

/// Forward cell: value plus a small muted source tag (V = Vietcap IQ, S = S&P CapIQ), like .fsrc.
void set_value_cell(QTableWidget* table, int row, int col, const QString& value, const QString& tag) {
    auto* lbl = qobject_cast<QLabel*>(table->cellWidget(row, col));
    if (!lbl) {
        lbl = new QLabel;
        lbl->setTextFormat(Qt::RichText);
        lbl->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
        lbl->setAttribute(Qt::WA_TransparentForMouseEvents);
        lbl->setStyleSheet(QStringLiteral("background:transparent; color:%1; padding:0 8px;").arg(css(c_text())));
        table->setCellWidget(row, col, lbl);
    }
    QString html = value.toHtmlEscaped();
    if (!tag.isEmpty())
        html += QStringLiteral("<span style='color:%1; font-size:9px;'>&nbsp;%2</span>").arg(css(c_muted()), tag);
    lbl->setText(html);
}

QString src_tag(const QString& src) {
    if (src.isEmpty())
        return {};
    return src == QLatin1String("vietcap") ? QStringLiteral("V") : QStringLiteral("S");
}

// ── 3-year forecast (payload `forecast`, per-ticker bridge file passed through by the script) ──

QString warn_html(const QString& text) {
    return QStringLiteral("<div style='color:%1; font-size:12px;'>%2</div>")
        .arg(css(c_rich()), (QStringLiteral("⚠ ") + text).toHtmlEscaped());
}

/// "2026-09-26 15:30 ICT" → "26/09/2026 15:30 ICT"; anything else as is.
QString generated_text(const QString& raw) {
    const QDateTime dt = QDateTime::fromString(raw.left(16), QStringLiteral("yyyy-MM-dd HH:mm"));
    return dt.isValid() ? dt.toString(QStringLiteral("dd/MM/yyyy HH:mm")) + raw.mid(16) : raw.trimmed();
}

/// Milestone at 31/12 of the year after `as_of`, else the last one — read from the payload, never interpolated.
QJsonObject next_milestone(const QJsonObject& fc, const QString& as_of) {
    const QJsonArray ms = fc.value(QStringLiteral("milestones")).toArray();
    if (ms.isEmpty())
        return {};
    const QDate d = QDate::fromString(as_of.left(10), Qt::ISODate);
    const QString want = d.isValid() ? QStringLiteral("%1-12-31").arg(d.year() + 1) : QString();
    for (const QJsonValue& v : ms) {
        if (!want.isEmpty() && v.toObject().value(QStringLiteral("date")).toString().startsWith(want))
            return v.toObject();
    }
    return ms.last().toObject();
}

/// Stat line above the chart: growth per year ('*' = EST year) and the forecast band at next year-end.
QString forecast_stat_html(const QJsonObject& fc, bool book, const QString& as_of, const QString& unit) {
    QStringList years, values;
    for (const QJsonValue& gv : fc.value(QStringLiteral("growth")).toArray()) {
        const QJsonObject g = gv.toObject();
        if (g.value(QStringLiteral("year")).toInt(0) <= 0 || years.size() >= kFcYears)
            continue;
        years << QString::number(g.value(QStringLiteral("year")).toInt());
        values << growth_text(g, true);
    }
    const QString what = book ? QStringLiteral("BVPS ") : QStringLiteral("EPS ");
    QString cells;
    if (!years.isEmpty())
        cells += stat_cell(what + years.join(QStringLiteral(" · ")), values.join(QStringLiteral(" · ")).toHtmlEscaped(),
                           c_text(), 14);
    const QJsonObject ms = next_milestone(fc, as_of);
    if (!ms.isEmpty()) {
        const QString when = fcview::date_vn(ms.value(QStringLiteral("date")).toString());
        const QString band = QStringLiteral("TB %1 · đắt %2")
                                 .arg(fcview::level(num(ms.value(QStringLiteral("fair")))),
                                      fcview::level(num(ms.value(QStringLiteral("rich1")))));
        cells += stat_cell(QStringLiteral("Dải DP %1 (%2)").arg(when, unit), band.toHtmlEscaped(), c_muted(), 14);
    }
    return cells.isEmpty() ? QString()
                           : QStringLiteral("<table cellspacing='0' cellpadding='0'><tr>") + cells +
                                 QStringLiteral("</tr></table>");
}

/// EPS (BVPS) pins the bands are drawn from, in the chart's price unit, with the anchor's method.
QString pins_html(const QJsonObject& fc, bool book, const QString& unit) {
    const QJsonArray pins = fc.value(QStringLiteral("eps_pins")).toArray();
    if (pins.isEmpty())
        return {};
    QStringList parts;
    for (const QJsonValue& pv : pins) {
        const QJsonObject p = pv.toObject();
        parts << QStringLiteral("FY%1 %2")
                     .arg(p.value(QStringLiteral("year")).toInt())
                     .arg(fcview::level(num(p.value(QStringLiteral("value")))));
    }
    const QJsonObject first = pins.first().toObject();
    const QString anchor = QStringLiteral("Neo: ") + first.value(QStringLiteral("method")).toString();
    return QStringLiteral("<br><b>%1</b> %2<br>%3")
        .arg(fcview::esc(QStringLiteral("Mốc %1 dùng vẽ dải (%2/cp, thang giá chart)")
                             .arg(book ? QStringLiteral("BVPS") : QStringLiteral("EPS"), unit)),
             fcview::esc(parts.join(QStringLiteral(" · "))) + QStringLiteral(" ") +
                 fcview::tier_chip(first.value(QStringLiteral("tier")).toString()),
             fcview::span(fcview::esc(anchor), c_muted()));
}

/// Key under a chart with markers; "" when it has none. `extremes`: ◇ valuation extremes on this (P/E) chart.
QString notes_key_html(bool keynotes, bool targets, bool extremes) {
    QStringList parts;
    if (targets)
        parts << QStringLiteral("◆ giá mục tiêu (mỗi nguồn một ◆, quy về thang giá điều chỉnh)");
    if (keynotes)
        parts << QStringLiteral("▲ đỉnh · ▼ đáy (ký hiệu rỗng = tạm hoặc UNVERIFIED; đặt tại giá đóng cửa ngày đó)");
    if (extremes)
        parts << QStringLiteral("◇ cực trị P/E theo σ (không phải đỉnh/đáy giá)");
    if (parts.isEmpty())
        return {};
    return muted_html(parts.join(QStringLiteral(" · ")) + QStringLiteral(" — rê chuột vào ký hiệu để xem nguồn"));
}

/// The script's warnings (anchor check, missing / old file …) first, then the bridge's for this ticker; no repeats.
QStringList forecast_warnings(const QJsonObject& data) {
    const QJsonArray script = data.value(QStringLiteral("meta")).toObject().value(QStringLiteral("warnings")).toArray();
    const QJsonArray bridge = data.value(QStringLiteral("forecast"))
                                  .toObject()
                                  .value(QStringLiteral("meta"))
                                  .toObject()
                                  .value(QStringLiteral("warnings"))
                                  .toArray();
    QStringList out;
    for (const QJsonArray& arr : {script, bridge}) {
        for (const QJsonValue& w : arr) {
            const QString t = fcview::warning_text(w);
            if (!t.isEmpty() && !out.contains(t))
                out << t;
        }
    }
    return out;
}

/// Lines under the chart: per-year basis, retention fallback, caveats (always incl. "not a price forecast"), run time.
QStringList basis_note_parts(const QJsonObject& fc, const QJsonObject& fmeta, bool book, int n_warn) {
    QStringList out = {forecast_basis_html(fc, book, kNaN, true)};
    if (book && fc.value(QStringLiteral("retention")).toObject().value(QStringLiteral("fallback")).toBool())
        out << muted_html(QStringLiteral("Tỷ lệ giữ lại r lấy theo VNINDEX (mã thiếu lịch sử BV) — EST."));
    QStringList cav;
    for (const QJsonValue& c : fmeta.value(QStringLiteral("caveats")).toArray()) {
        if (!c.toString().trimmed().isEmpty())
            cav << c.toString().trimmed();
    }
    const auto says_no_price = [](const QString& c) { return c.contains(QStringLiteral("KHÔNG dự báo giá")); };
    if (std::none_of(cav.cbegin(), cav.cend(), says_no_price))
        cav << QStringLiteral("Chỉ dải định giá dịch theo %1 dự phóng — KHÔNG dự báo giá. "
                              "Tham khảo, không khuyến nghị.")
                   .arg(book ? QStringLiteral("BVPS") : QStringLiteral("EPS"));
    out << muted_html(cav.join(QStringLiteral(" · ")));
    const QString gen = generated_text(fmeta.value(QStringLiteral("generated")).toString());
    QString run = QStringLiteral("Dự phóng cập nhật %1").arg(gen.isEmpty() ? QStringLiteral("[CẦN DATA]") : gen);
    if (n_warn > 0)
        run += QStringLiteral(" · %1 cảnh báo — rê chuột để xem").arg(n_warn);
    out << muted_html(run);
    return out;
}

/// Hover card of the basis note: every source per year, the EPS/BVPS pins, then every warning.
QString sources_tip(const QJsonObject& fc, bool book, const QString& unit, const QStringList& warns) {
    QString tip = forecast_sources_html(fc, book, true) + pins_html(fc, book, unit);
    if (!warns.isEmpty())
        tip += QStringLiteral("<br><br><b>Cảnh báo</b><br>") +
               fcview::span(fcview::esc(QStringLiteral("⚠ ") + warns.join(QStringLiteral("\n⚠ ")))
                                .replace(QLatin1Char('\n'), QStringLiteral("<br>")),
                            c_rich());
    return tip;
}

} // namespace

HhpTickerDialog::HhpTickerDialog(const QString& ticker, const QString& metric, QWidget* parent)
    : QDialog(parent), ticker_(ticker),
      metric_(metric == QLatin1String("pb") ? QStringLiteral("pb") : QStringLiteral("pe")) {
    setWindowFlags(Qt::Window | Qt::WindowMinMaxButtonsHint | Qt::WindowCloseButtonHint);
    setWindowTitle(QStringLiteral("%1 — Vùng định giá P/E · P/B (lịch sử + forward)").arg(ticker_));
    // Tall plot (840 px) + table: as high as the screen allows (content scrolls), never above kDialogMaxH.
    const QScreen* scr = screen() ? screen() : QGuiApplication::primaryScreen();
    const QRect avail = scr ? scr->availableGeometry() : QRect();
    resize(avail.isValid() ? std::min(kDialogW, avail.width()) : kDialogW,
           avail.isValid() ? std::min(kDialogMaxH, avail.height() - kScreenMargin) : kDialogMaxH);
    build_ui();
    set_loading();
}

void HhpTickerDialog::build_ui() {
    QPalette pal = palette();
    pal.setColor(QPalette::Window, c_bg());
    pal.setColor(QPalette::WindowText, c_text());
    pal.setColor(QPalette::Base, c_bg());
    pal.setColor(QPalette::Text, c_text());
    setPalette(pal);
    setAutoFillBackground(true);

    // Everything scrolls: the plot alone is kPlotMinH tall, more than some screens leave for a dialog.
    auto* outer = new QVBoxLayout(this);
    outer->setContentsMargins(0, 0, 0, 0);
    auto* scroll = new QScrollArea(this);
    scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame);
    auto* content = new QWidget(scroll);
    content->setObjectName(QStringLiteral("hhpTickerContent"));
    content->setAutoFillBackground(true);
    scroll->setWidget(content);
    outer->addWidget(scroll);

    auto* root = new QVBoxLayout(content);
    root->setContentsMargins(20, 16, 20, 14);
    root->setSpacing(8);

    auto* title = new QLabel(windowTitle(), content);
    title->setStyleSheet(QStringLiteral("color:%1; font-size:16px; font-weight:700;").arg(css(c_text())));
    root->addWidget(title);

    auto* mrow = new QHBoxLayout;
    mrow->setSpacing(6);
    btn_pe_ = new QPushButton(QStringLiteral("P/E"), content);
    btn_pb_ = new QPushButton(QStringLiteral("P/B"), content);
    for (QPushButton* b : {btn_pe_, btn_pb_}) {
        b->setCursor(Qt::PointingHandCursor);
        b->setAutoDefault(false); // Enter must not flip the metric
        mrow->addWidget(b);
    }
    mrow->addStretch(1);
    root->addLayout(mrow);
    connect(btn_pe_, &QPushButton::clicked, this, [this]() { set_metric(QStringLiteral("pe")); });
    connect(btn_pb_, &QPushButton::clicked, this, [this]() { set_metric(QStringLiteral("pb")); });

    stats_lbl_ = new QLabel(content);
    stats_lbl_->setTextFormat(Qt::RichText);
    stats_lbl_->setMinimumHeight(44);
    stats_lbl_->setStyleSheet(QStringLiteral("color:%1;").arg(css(c_text())));
    root->addWidget(stats_lbl_);

    fc_lbl_ = new QLabel(content);
    fc_lbl_->setObjectName(QStringLiteral("hhpFcStat"));
    fc_lbl_->setTextFormat(Qt::RichText);
    fc_lbl_->setWordWrap(true);
    fc_lbl_->setStyleSheet(QStringLiteral("color:%1;").arg(css(c_text())));
    fc_lbl_->hide();
    root->addWidget(fc_lbl_);

    chart_ = new HhpChart(true, content);
    chart_->set_plot_min_height(kPlotMinH);
    root->addWidget(chart_, 1);

    fc_note_lbl_ = new QLabel(content);
    fc_note_lbl_->setObjectName(QStringLiteral("hhpFcNote"));
    fc_note_lbl_->setTextFormat(Qt::RichText);
    fc_note_lbl_->setWordWrap(true);
    fc_note_lbl_->setStyleSheet(QStringLiteral("color:%1; font-size:11px;").arg(css(c_text())));
    fc_note_lbl_->hide();
    root->addWidget(fc_note_lbl_);

    fwd_table_ = new QTableWidget(3, 3, content);
    fwd_table_->setHorizontalHeaderLabels(
        {QStringLiteral("FORWARD"), QStringLiteral("2026F"), QStringLiteral("2027F")});
    fwd_table_->horizontalHeaderItem(0)->setTextAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    for (int c = 1; c < 3; ++c)
        fwd_table_->horizontalHeaderItem(c)->setTextAlignment(Qt::AlignRight | Qt::AlignVCenter);
    const QStringList row_names = {QStringLiteral("P/E"), QStringLiteral("P/B"), QStringLiteral("ROE %")};
    for (int r = 0; r < 3; ++r) {
        auto* it = new QTableWidgetItem(row_names.at(r));
        it->setFlags(Qt::ItemIsEnabled);
        it->setForeground(c_muted());
        it->setTextAlignment(Qt::AlignLeft | Qt::AlignVCenter);
        fwd_table_->setItem(r, 0, it);
    }
    fwd_table_->verticalHeader()->setVisible(false);
    fwd_table_->verticalHeader()->setSectionResizeMode(QHeaderView::Fixed);
    fwd_table_->verticalHeader()->setDefaultSectionSize(kFwdRowH);
    fwd_table_->horizontalHeader()->setSectionResizeMode(QHeaderView::Stretch);
    fwd_table_->horizontalHeader()->setHighlightSections(false);
    fwd_table_->horizontalHeader()->setSectionsClickable(false);
    fwd_table_->horizontalHeader()->setFixedHeight(kFwdRowH);
    fwd_table_->setShowGrid(false);
    fwd_table_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    fwd_table_->setSelectionMode(QAbstractItemView::NoSelection);
    fwd_table_->setFocusPolicy(Qt::NoFocus);
    fwd_table_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    fwd_table_->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    fwd_table_->setFixedHeight(kFwdRowH * 4 + 2);
    fwd_table_->setStyleSheet(QStringLiteral("QTableWidget { background:%1; color:%2; border:none; font-size:12px; }"
                                             "QTableWidget::item { border-bottom:1px solid %3; padding:0 8px; }"
                                             "QHeaderView { background:%1; border:none; }"
                                             "QHeaderView::section { background:%1; color:%4; font-size:11px;"
                                             " font-weight:700; border:none; border-bottom:1px solid %3;"
                                             " padding:0 8px; }")
                                  .arg(css(c_bg()), css(c_text()), css(c_line()), css(c_muted())));

    fwd_info_lbl_ = new QLabel(content);
    fwd_info_lbl_->setTextFormat(Qt::RichText);
    fwd_info_lbl_->setWordWrap(true);
    fwd_info_lbl_->setAlignment(Qt::AlignLeft | Qt::AlignTop);
    fwd_info_lbl_->setStyleSheet(QStringLiteral("color:%1; font-size:12px;").arg(css(c_text())));

    auto* fwd_row = new QHBoxLayout;
    fwd_row->setSpacing(14);
    fwd_row->addWidget(fwd_table_, 1, Qt::AlignTop);
    fwd_row->addWidget(fwd_info_lbl_, 1, Qt::AlignTop);
    root->addLayout(fwd_row);

    note_lbl_ = new QLabel(content);
    note_lbl_->setTextFormat(Qt::PlainText);
    note_lbl_->setWordWrap(true);
    note_lbl_->setStyleSheet(QStringLiteral("color:%1; font-size:11px;").arg(css(c_muted())));
    root->addWidget(note_lbl_);

    update_metric_buttons();
}

void HhpTickerDialog::set_loading() {
    has_data_ = false;
    stats_lbl_->clear();
    clear_forecast();
    note_lbl_->clear();
    fwd_table_->hide();
    fwd_info_lbl_->clear();
    chart_->clear(QStringLiteral("Đang tải dữ liệu %1…").arg(ticker_));
}

void HhpTickerDialog::set_error(const QString& message) {
    has_data_ = false;
    // The script's message is already Vietnamese and says what to run (e.g. "Chạy: python3
    // hhp_vn100_series.py"). PythonRunner passes it through bare; drop a "[CODE] " prefix in case a
    // future path adds one. Short title above, the message itself once, in the chart area.
    static const QRegularExpression code_prefix(QStringLiteral("^\\[[A-Z_]+\\]\\s*"));
    QString shown = message;
    shown.remove(code_prefix);
    if (shown.isEmpty())
        shown = QStringLiteral("không rõ nguyên nhân");
    stats_lbl_->setText(QStringLiteral("<span style='color:%1; font-size:13px;'>%2</span>")
                            .arg(css(c_rich()),
                                 QStringLiteral("Không tải được vùng định giá %1.").arg(ticker_).toHtmlEscaped()));
    clear_forecast();
    note_lbl_->clear();
    fwd_table_->hide();
    fwd_info_lbl_->clear();
    chart_->clear(shown);
}

void HhpTickerDialog::set_data(const QJsonObject& data) {
    data_ = data;
    has_data_ = true;
    render();
    render_forward();
}

void HhpTickerDialog::set_metric(const QString& metric) {
    const QString m = metric == QLatin1String("pb") ? QStringLiteral("pb") : QStringLiteral("pe");
    if (m == metric_)
        return;
    metric_ = m;
    update_metric_buttons();
    if (has_data_)
        render(); // HhpChart keeps the selected YTD…ALL range across set_series
}

void HhpTickerDialog::update_metric_buttons() {
    btn_pe_->setStyleSheet(pill_style(metric_ == QLatin1String("pe")));
    btn_pb_->setStyleSheet(pill_style(metric_ == QLatin1String("pb")));
}

void HhpTickerDialog::render() {
    const QString m = metric_label(metric_);
    // The chart is reused across P/E↔P/B: forget the previous metric's forecast region and notes first.
    chart_->set_forecast(0, {}, {});
    chart_->set_notes({});
    clear_forecast();
    const QJsonValue bv = data_.value(metric_);
    if (!bv.isObject()) {
        stats_lbl_->clear();
        note_lbl_->clear();
        chart_->clear(QStringLiteral("Mã này không có band %1 (lợi nhuận/sổ sách âm → ratio bị loại). Thử %2.")
                          .arg(m, metric_ == QLatin1String("pe") ? QStringLiteral("P/B") : QStringLiteral("P/E")));
        return;
    }
    const QJsonObject b = bv.toObject();
    const QString unit = data_.value(QStringLiteral("unit")).toString(QStringLiteral("nghìn đồng"));
    const QJsonObject row = data_.value(QStringLiteral("row")).toObject();
    const bool stale = row.value(metric_).toObject().value(QStringLiteral("stale")).toBool();
    stats_lbl_->setText(stats_html(b, m, unit, stale, row));
    note_lbl_->setText(note_text(data_, b, m));

    const QJsonObject ch = b.value(QStringLiteral("chart")).toObject();
    if (ch.value(QStringLiteral("price")).toArray().isEmpty()) {
        chart_->clear(QStringLiteral("Chưa có chuỗi giá cho %1.").arg(ticker_));
        return;
    }
    using Kind = HhpChartSeries::Kind;
    QVector<HhpChartSeries> series = {
        make_series(Kind::Band, QStringLiteral("Vùng rẻ %1 (−2σ…−1σ)").arg(m), c_cheap(), 0.0, 0.30,
                    ch.value(QStringLiteral("cheap1")), ch.value(QStringLiteral("cheap2"))),
        make_series(Kind::Band, QStringLiteral("Vùng mắc %1 (+1σ…+2σ)").arg(m), c_rich(), 0.0, 0.26,
                    ch.value(QStringLiteral("rich2")), ch.value(QStringLiteral("rich1"))),
        make_series(Kind::Dashed, QStringLiteral("%1 trung bình").arg(m), c_fair(), 1.2, 1.0,
                    ch.value(QStringLiteral("fair"))),
    };
    // 3-year forecast of this metric: the same bands moved along the forecast EPS (BVPS) path, dashed. Null block
    // (skipped, off-anchor, no file) → no dashed series; render_forecast() says why. Forecast series go before the
    // price line: HhpChart snaps keynotes onto the last non-forecast line.
    const QVector<HhpChartSeries> fc_series =
        index_forecast_series(data_.value(QStringLiteral("forecast")).toObject().value(metric_).toObject());
    series += fc_series;
    series << make_series(Kind::Line, ticker_, c_idx(), 2.4, 1.0, ch.value(QStringLiteral("price")));
    render_forecast(b, !fc_series.isEmpty());
    // Right axis in the ratio itself: price ÷ current EPS (BVPS), base = fair ÷ μ at the last point.
    const QJsonArray fair = ch.value(QStringLiteral("fair")).toArray();
    const double mean = num(b.value(QStringLiteral("mean")));
    double base = kNaN;
    if (!fair.isEmpty() && has(mean) && mean > 0) {
        const QJsonArray last = fair.last().toArray();
        if (last.size() >= 2)
            base = num(last.at(1)) / mean;
    }
    chart_->set_right_scale(has(base) ? base : 0.0,
                            metric_ == QLatin1String("pb") ? QStringLiteral("P/B (lần) · theo BVPS hiện tại")
                                                           : QStringLiteral("P/E (lần) · theo EPS hiện tại"),
                            1);
    chart_->set_series(series, QStringLiteral("Giá (%1)").arg(unit), 1, true);
}

void HhpTickerDialog::clear_forecast() {
    fc_lbl_->clear();
    fc_lbl_->hide();
    fc_note_lbl_->clear();
    fc_note_lbl_->setToolTip(QString());
    fc_note_lbl_->hide();
}

void HhpTickerDialog::render_forecast(const QJsonObject& band, bool has_fc) {
    const bool book = metric_ == QLatin1String("pb");
    const QString m = metric_label(metric_);
    const QString unit = data_.value(QStringLiteral("unit")).toString(QStringLiteral("nghìn đồng"));
    const QJsonObject froot = data_.value(QStringLiteral("forecast")).toObject();
    const QJsonObject fc = froot.value(metric_).toObject();
    const QStringList warns = forecast_warnings(data_);

    // Markers: ticker keynotes always; ◆ targets only with the forecast (they sit in the forecast region).
    QVector<HhpChartNote> notes =
        keynote_notes(data_.value(QStringLiteral("keynotes")).toArray(), ticker_, metric_, true);
    const auto extreme = [](const HhpChartNote& n) {
        return n.kind == HhpChartNote::Kind::ExtremeHigh || n.kind == HhpChartNote::Kind::ExtremeLow;
    };
    const bool has_ext = std::any_of(notes.cbegin(), notes.cend(), extreme);
    const bool has_kn = !std::all_of(notes.cbegin(), notes.cend(), extreme);
    const QVector<HhpChartNote> targets =
        has_fc ? ticker_target_notes(froot.value(QStringLiteral("targets")).toArray(), unit) : QVector<HhpChartNote>{};
    notes += targets;
    chart_->set_notes(notes);

    QString top;
    QStringList below;
    if (has_fc) {
        const QJsonArray fair = fc.value(QStringLiteral("points")).toObject().value(QStringLiteral("fair")).toArray();
        const double x0 = has(num(fc.value(QStringLiteral("x0")))) ? num(fc.value(QStringLiteral("x0")))
                                                                     : to_points(fair).first().x();
        chart_->set_forecast(x0, QStringLiteral("Dự phóng 3 năm (nét đứt)"), forecast_basis_spans(fc, book, true));
        top = forecast_stat_html(fc, book, band.value(QStringLiteral("as_of")).toString(), unit);
        if (!fc.value(QStringLiteral("reliable")).toBool(true))
            top += warn_html(QStringLiteral("%1 dao động lớn (σ/μ ≥ 0,6) — dự phóng chỉ tham khảo").arg(m));
        below = basis_note_parts(fc, froot.value(QStringLiteral("meta")).toObject(), book, int(warns.size()));
        fc_note_lbl_->setToolTip(sources_tip(fc, book, unit, warns));
    } else {
        // No dashed series: say why — the bridge's skip reason, else whatever the script warned, else "no file".
        const QString skip = froot.value(QStringLiteral("skip")).toObject().value(metric_).toString().trimmed();
        if (!skip.isEmpty())
            top = warn_html(QStringLiteral("Không dự phóng %1: %2").arg(m, skip));
        else
            top = muted_html(froot.isEmpty() ? QStringLiteral("Chưa có dự phóng 3 năm cho %1.").arg(ticker_)
                                             : QStringLiteral("Không có dự phóng %1 cho %2.").arg(m, ticker_));
        for (int i = 0; i < std::min<int>(kMaxShownWarn, warns.size()); ++i)
            top += warn_html(warns.at(i));
    }
    const QString key = notes_key_html(has_kn, !targets.isEmpty(), has_ext);
    if (!key.isEmpty())
        below << key;
    fc_lbl_->setText(top);
    fc_lbl_->setVisible(!top.isEmpty());
    fc_note_lbl_->setText(below.join(QStringLiteral("<br>")));
    fc_note_lbl_->setVisible(!below.isEmpty());
}

void HhpTickerDialog::render_forward() {
    // CapIQ comes from the overview row, independent of the forward block: shown in both branches.
    const QString capiq = capiq_html(data_.value(QStringLiteral("row")).toObject());
    const QJsonValue fv = data_.value(QStringLiteral("forward"));
    if (!fv.isObject()) {
        fwd_table_->hide();
        fwd_info_lbl_->setText(muted_html(QStringLiteral("Chưa có dữ liệu forward cho mã này.")) +
                               (capiq.isEmpty() ? QString() : QStringLiteral("<br><br>") + capiq));
        return;
    }
    const QJsonObject f = fv.toObject();
    const QJsonObject src = f.value(QStringLiteral("src")).toObject();

    // P/E and P/B carry a per-cell source (src.pe2026 …); ROE has none, like the page.
    const QStringList keys = {QStringLiteral("pe"), QStringLiteral("pb"), QStringLiteral("roe")};
    const QStringList years = {QStringLiteral("2026F"), QStringLiteral("2027F")};
    for (int r = 0; r < keys.size(); ++r) {
        const QJsonObject vals = f.value(keys.at(r)).toObject();
        const bool is_roe = keys.at(r) == QLatin1String("roe");
        for (int c = 0; c < years.size(); ++c) {
            const double v = num(vals.value(years.at(c)));
            if (!has(v)) {
                set_value_cell(fwd_table_, r, c + 1, QStringLiteral("—"), QString());
                continue;
            }
            const QString src_key = keys.at(r) + years.at(c).left(4); // "pe2026"
            set_value_cell(fwd_table_, r, c + 1, fmt_ratio(v) + (is_roe ? QStringLiteral("%") : QString()),
                           is_roe ? QString() : src_tag(src.value(src_key).toString()));
        }
    }
    fwd_table_->show();

    QStringList lines;
    const QString rating = f.value(QStringLiteral("rating")).toString();
    const QString analyst = f.value(QStringLiteral("analyst")).toString();
    if (!rating.isEmpty())
        lines << QStringLiteral("Khuyến nghị: <b style='color:%1;'>%2</b>%3")
                     .arg(css(rec_color(rating)), rating.toHtmlEscaped(),
                          analyst.isEmpty() ? QString() : QStringLiteral(" · ") + analyst.toHtmlEscaped());
    const double tp = num(f.value(QStringLiteral("tp")));
    if (has(tp))
        lines << QStringLiteral("Target Price: <b style='color:%1;'>%2</b> đ").arg(css(c_gold()), fmt_vi(tp));
    lines << muted_html(QStringLiteral("V = Vietcap IQ (live) · S = S&P CapIQ snapshot"));
    const QString note = f.value(QStringLiteral("note")).toString();
    if (!note.isEmpty())
        lines << QStringLiteral("<span style='color:%1;'>⚠ %2</span>").arg(css(c_rich()), note.toHtmlEscaped());
    if (!capiq.isEmpty())
        lines << QStringLiteral("<br>") + capiq; // blank line, then the S&P CapIQ block
    fwd_info_lbl_->setText(lines.join(QStringLiteral("<br>")));
}

} // namespace fincept::screens::hhp
