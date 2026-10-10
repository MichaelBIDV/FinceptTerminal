// src/screens/hhp_valuation/HhpForecastView.h
// Pure JSON → view helpers for the keynotes and the 3-year forecast of ĐỊNH GIÁ HHP (header-only, included by
// HhpValuationPanel.cpp and HhpTickerDialog.cpp). Input = the `keynotes` / `forecast` blocks of
// `hhp_valuation.py overview` (index/baskets) and `… ticker <TK>` (per ticker: pe/pb blocks of the same shape as
// the index, growth always in decimals → the `decimal` overloads; targets one per source → ticker_target_notes).
// Nothing here computes a number: every value is read from the payload and shown with the source, date and tier it
// arrived with. Every data string is HTML-escaped before it reaches rich text.
#pragma once

#include "screens/hhp_valuation/HhpChart.h"
#include "screens/hhp_valuation/HhpCommon.h"

#include <QDate>
#include <QDateTime>
#include <QHash>
#include <QJsonArray>
#include <QJsonObject>
#include <QRegularExpression>
#include <QStringList>
#include <QTimeZone>
#include <QUrl>

#include <algorithm>
#include <cmath>

namespace fincept::screens::hhp {

namespace fcview {

inline QString esc(const QString& s) {
    return s.toHtmlEscaped();
}

/// `html` in a colour span (caller escapes data inside `html`).
inline QString span(const QString& html, const QColor& c) {
    return QStringLiteral("<span style=\"color:%1;\">%2</span>").arg(css(c), html);
}

/// Index level like the panel's fmt_level(): Vietnamese grouping, no trailing ",0".
inline QString level(double v) {
    QString s = fmt_vi(v, 1);
    if (s.endsWith(QStringLiteral(",0")))
        s.chop(2);
    return s;
}

/// "2018-04-09" → "09/04/2018"; unparsable → as is.
inline QString date_vn(const QString& iso) {
    const QDate d = QDate::fromString(iso.left(10), Qt::ISODate);
    return d.isValid() ? d.toString(QStringLiteral("dd/MM/yyyy")) : iso;
}

/// UTC midnight of an ISO date in epoch ms; NaN when unparsable.
inline double iso_ms(const QString& iso) {
    const QDate d = QDate::fromString(iso.left(10), Qt::ISODate);
    if (!d.isValid())
        return kNaN;
    return static_cast<double>(QDateTime(d, QTime(0, 0), QTimeZone::UTC).toMSecsSinceEpoch());
}

/// o[ms_key] when numeric, else o[date_key] parsed as an ISO date.
inline double ms_of(const QJsonObject& o, const char* ms_key, const char* date_key) {
    const double ms = num(o.value(QLatin1String(ms_key)));
    return has(ms) ? ms : iso_ms(o.value(QLatin1String(date_key)).toString());
}

/// Growth fields arrive as decimals ("g": 0.2516); source values/min/max may be percents (25.16) — a
/// market-level growth above 150% does not occur, so |v| > 1.5 is read as already in percent.
inline double as_pct(double v) {
    return !has(v) ? kNaN : (std::abs(v) > 1.5 ? v : v * 100.0);
}

/// Growth → percent. `decimal`: the payload is known to hold decimals (per-ticker forecast — a turnaround can grow
/// > 150%, so as_pct()'s market-level heuristic would misread +180% as +1.8%). Otherwise as_pct().
inline double growth_pct(double v, bool decimal) {
    return !decimal ? as_pct(v) : (has(v) ? v * 100.0 : kNaN);
}

/// Index or basket scope (the keynote file of the index page); anything else is a ticker (per-ticker keynote file).
inline bool index_scope(const QString& scope) {
    return scope == QLatin1String("VNINDEX") || scope == QLatin1String("VN30") || scope == QLatin1String("VN100");
}

inline QColor tier_color(const QString& tier) {
    if (tier.startsWith(QLatin1String("FACT")))
        return c_cheap();
    if (tier.startsWith(QLatin1String("SS")))
        return c_gold();
    if (tier == QLatin1String("UNVERIFIED"))
        return c_rich();
    if (tier == QLatin1String("NEWS"))
        return c_blue();
    return c_muted();
}

inline QString tier_chip(const QString& tier) {
    return span(QStringLiteral("[") + esc(tier.isEmpty() ? QStringLiteral("?") : tier) + QStringLiteral("]"),
                tier_color(tier));
}

/// "https://www.cafef.vn/…" → "cafef.vn".
inline QString domain(const QString& url) {
    QString host = QUrl(url).host();
    if (host.startsWith(QLatin1String("www.")))
        host = host.mid(4);
    return host;
}

inline QString number_label(const QString& k) {
    if (k == QLatin1String("close") || k == QLatin1String("level"))
        return QStringLiteral("Điểm");
    if (k == QLatin1String("pe"))
        return QStringLiteral("P/E");
    if (k == QLatin1String("pb"))
        return QStringLiteral("P/B");
    if (k == QLatin1String("move_in_pct"))
        return QStringLiteral("Nhịp vào");
    if (k == QLatin1String("move_out_pct"))
        return QStringLiteral("Nhịp ra");
    if (k == QLatin1String("sigma"))
        return QStringLiteral("σ");
    return k;
}

/// Same, for a number of `scope`: a ticker's close is a price ("Giá"), not index points.
inline QString number_label(const QString& k, const QString& scope) {
    if (!scope.isEmpty() && !index_scope(scope) && (k == QLatin1String("close") || k == QLatin1String("level")))
        return QStringLiteral("Giá");
    return number_label(k);
}

/// Value of one keynote number with its unit ("1.204,3", "17.2x (+2.1σ)", "+44.9%"). Plain text.
inline QString number_value(const QJsonObject& n) {
    const QString k = n.value(QStringLiteral("k")).toString();
    const QString unit = n.value(QStringLiteral("unit")).toString();
    const double v = num(n.value(QStringLiteral("v")));
    QString t;
    if (unit == QLatin1String("điểm") || k == QLatin1String("close") || k == QLatin1String("level"))
        t = level(v) + (unit.isEmpty() || unit == QStringLiteral("điểm") ? QString() : QStringLiteral(" ") + unit);
    else if (unit == QLatin1String("x") || k == QLatin1String("pe") || k == QLatin1String("pb"))
        t = fmt_ratio(v, 2) + QStringLiteral("x");
    else if (unit == QLatin1String("%") || k.endsWith(QLatin1String("_pct")))
        t = fmt_pct(v, 1);
    else if (unit == QStringLiteral("σ") || k == QLatin1String("sigma"))
        t = fmt_sigma(v) + QStringLiteral("σ");
    else
        t = fmt_ratio(v, 2) + (unit.isEmpty() ? QString() : QStringLiteral(" ") + unit);
    const double sigma = num(n.value(QStringLiteral("sigma")));
    if (has(sigma))
        t += QStringLiteral(" (") + fmt_sigma(sigma) + QStringLiteral("σ)");
    return t;
}

/// Header value of a keynote on `scope`'s chart: VNINDEX level (a ticker: its own price), or the basket's own ratio
/// for `metric`.
inline QString headline_value(const QJsonArray& numbers, const QString& scope, const QString& metric) {
    QString fallback;
    const bool level_head = scope == QLatin1String("VNINDEX") || !index_scope(scope);
    for (const QJsonValue& nv : numbers) {
        const QJsonObject n = nv.toObject();
        const QString k = n.value(QStringLiteral("k")).toString();
        const QString sc = n.value(QStringLiteral("scope")).toString();
        if (!has(num(n.value(QStringLiteral("v")))))
            continue;
        if (sc == scope && level_head && (k == QLatin1String("close") || k == QLatin1String("level")))
            return scope + QStringLiteral(" ") + number_value(n);
        if (sc == scope && k == metric)
            return scope + QStringLiteral(" ") + number_label(k) + QStringLiteral(" ") + number_value(n);
        if (fallback.isEmpty() && sc == QLatin1String("VNINDEX") &&
            (k == QLatin1String("close") || k == QLatin1String("level")))
            fallback = sc + QStringLiteral(" ") + number_value(n);
    }
    return fallback;
}

/// Tooltip card frame: fixed width, dark box (the HHP palette must read in any app theme), 11 px body.
inline QString card_open() {
    return QStringLiteral("<table width=\"520\" cellspacing=\"0\" cellpadding=\"8\" bgcolor=\"%1\"><tr><td>"
                          "<div style=\"font-size:11px;\">")
        .arg(css(c_card()));
}
inline QString card_close() {
    return QStringLiteral("</div></td></tr></table>");
}

inline QString section(const QString& caption, const QString& body_html) {
    if (body_html.isEmpty())
        return {};
    return QStringLiteral("<div style=\"margin-top:6px;\"><span style=\"color:%1; font-size:10px;\">%2</span><br>%3</div>")
        .arg(css(c_muted()), esc(caption), body_html);
}

/// Free text carries a valuation figure: a digit together with P/E, P/B, σ or a multiple ("10,3x").
inline bool has_figure(const QString& s) {
    static const QRegularExpression digit(QStringLiteral("\\d"));
    static const QRegularExpression multiple(QStringLiteral("\\d\\s*[x×](?!\\p{L})"));
    if (!s.contains(digit))
        return false;
    return s.contains(QLatin1String("P/E"), Qt::CaseInsensitive) || s.contains(QLatin1String("P/B"), Qt::CaseInsensitive) ||
           s.contains(QStringLiteral("σ")) || s.contains(multiple);
}

/// A figure in free text is the curator's VNINDEX reading (engine σ scale) — or, in a per-ticker keynote file, that
/// ticker's own reading: it may label only the VNINDEX (ticker) chart of the metric it names, never a basket chart.
/// Text without a figure is scope-neutral.
inline bool text_fits_chart(const QString& s, const QString& scope, const QString& metric) {
    if (!has_figure(s))
        return true;
    if (scope != QLatin1String("VNINDEX") && index_scope(scope))
        return false;
    return (metric == QLatin1String("pe") && s.contains(QLatin1String("P/E"), Qt::CaseInsensitive)) ||
           (metric == QLatin1String("pb") && s.contains(QLatin1String("P/B"), Qt::CaseInsensitive));
}

/// Plain text of a warnings[] item: a string, or an object's text/msg/note (other shapes → empty).
inline QString warning_text(const QJsonValue& w) {
    if (w.isString())
        return w.toString().trimmed();
    const QJsonObject o = w.toObject();
    for (const char* key : {"text", "msg", "message", "note"}) {
        const QString t = o.value(QLatin1String(key)).toString().trimmed();
        if (!t.isEmpty())
            return t;
    }
    return {};
}

/// A valuation extreme (P/E far from its mean, found by σ — not a price pivot), as the per-ticker keynote builder
/// titles it: "Cực trị định giá MM/yyyy · …" / nhan_phu "cực trị P/E ±x,xσ".
inline bool valuation_extreme(const QJsonObject& ev) {
    return ev.value(QStringLiteral("title")).toString().trimmed().startsWith(QStringLiteral("Cực trị định giá"),
                                                                             Qt::CaseInsensitive) ||
           ev.value(QStringLiteral("nhan_phu")).toString().trimmed().startsWith(QStringLiteral("cực trị P/E"),
                                                                                Qt::CaseInsensitive);
}

/// The event's own close of `scope` (numbers[] k == "close", the unit of a ticker chart's price line); NaN if absent.
inline double event_close(const QJsonObject& ev, const QString& scope) {
    for (const QJsonValue& nv : ev.value(QStringLiteral("numbers")).toArray()) {
        const QJsonObject n = nv.toObject();
        if (n.value(QStringLiteral("k")).toString() == QLatin1String("close") &&
            n.value(QStringLiteral("scope")).toString() == scope)
            return num(n.value(QStringLiteral("v")));
    }
    return kNaN;
}

} // namespace fcview

// ── Keynotes ─────────────────────────────────────────────────────────────────

/// Tooltip card of one keynote (Qt rich text, 520 px wide, dark box so the HHP palette reads in any theme).
inline QString keynote_html(const QJsonObject& ev, const QString& scope, const QString& metric = {}) {
    using namespace fcview;
    const bool peak = ev.value(QStringLiteral("kind")).toString() == QLatin1String("dinh");
    const bool provisional = ev.value(QStringLiteral("provisional")).toBool();
    const QString tier = ev.value(QStringLiteral("tier")).toString();
    QString tier_eff = ev.value(QStringLiteral("tier_effective")).toString();
    if (tier_eff.isEmpty())
        tier_eff = tier;
    const QJsonArray numbers = ev.value(QStringLiteral("numbers")).toArray();

    const QString what = !valuation_extreme(ev) ? (peak ? QStringLiteral("▲ ĐỈNH") : QStringLiteral("▼ ĐÁY"))
                         : peak                  ? QStringLiteral("◇ CỰC TRỊ P/E CAO")
                                                 : QStringLiteral("◇ CỰC TRỊ P/E THẤP");
    QString head = what + (provisional ? QStringLiteral(" (TẠM)") : QString()) + QStringLiteral(" · ") +
                   date_vn(ev.value(QStringLiteral("date")).toString());
    const QString hv = headline_value(numbers, scope, metric);
    if (!hv.isEmpty())
        head += QStringLiteral(" · ") + hv;

    QString h = card_open();
    if (tier_eff == QLatin1String("UNVERIFIED"))
        h += QStringLiteral("<div style=\"color:%1; font-weight:bold;\">UNVERIFIED — không dùng cho quyết định</div>")
                 .arg(css(c_rich()));
    h += QStringLiteral("<div style=\"color:%1; font-weight:bold; font-size:12px;\">%2</div>")
             .arg(css(peak ? c_rich() : c_cheap()), esc(head));
    h += QStringLiteral("<div style=\"color:%1; font-weight:bold; font-size:12px; margin-top:3px;\">%2</div>")
             .arg(css(c_text()), esc(ev.value(QStringLiteral("title")).toString()));
    QString chip = QStringLiteral("Bậc ") + tier_chip(tier_eff);
    if (!tier.isEmpty() && tier != tier_eff)
        chip += span(esc(QStringLiteral(" (gốc %1)").arg(tier)), c_muted());
    h += QStringLiteral("<div style=\"font-size:10px; margin-top:2px;\">%1</div>").arg(chip);

    const auto para = [](const QJsonValue& v) {
        const QString s = v.toString().trimmed();
        return s.isEmpty() ? QString() : span(esc(s), c_text());
    };
    h += section(QStringLiteral("BỐI CẢNH"), para(ev.value(QStringLiteral("boi_canh"))));
    h += section(QStringLiteral("NGUYÊN NHÂN"), para(ev.value(QStringLiteral("nguyen_nhan"))));
    QString factors;
    for (const QJsonValue& f : ev.value(QStringLiteral("key_factors")).toArray()) {
        if (!f.toString().trimmed().isEmpty())
            factors += QStringLiteral("<li>") + span(esc(f.toString().trimmed()), c_text()) + QStringLiteral("</li>");
    }
    if (!factors.isEmpty())
        h += section(QStringLiteral("YẾU TỐ THEN CHỐT"),
                     QStringLiteral("<ul style=\"margin-top:0px; margin-bottom:0px; margin-left:-18px;\">") + factors +
                         QStringLiteral("</ul>"));
    h += section(QStringLiteral("SAU ĐÓ"), para(ev.value(QStringLiteral("sau_do"))));

    QStringList nums;
    QStringList methods; // EST methods, each shown once under the numbers (they repeat across numbers)
    const auto circled = [](qsizetype i) { return QStringLiteral("(%1)").arg(i + 1); };
    // Only this chart's scope (plus the VN-Index level on a basket chart) — the card must fit a screen — and the
    // chart's own scope/metric first: its ratio, then its level, then the rest of the scope, then the VN-Index level.
    QVector<QPair<int, QJsonObject>> shown;
    for (const QJsonValue& nv : numbers) {
        const QJsonObject n = nv.toObject();
        if (!has(num(n.value(QStringLiteral("v")))))
            continue;
        const QString sc = n.value(QStringLiteral("scope")).toString();
        const QString nk = n.value(QStringLiteral("k")).toString();
        const bool is_level = nk == QLatin1String("close") || nk == QLatin1String("level");
        if (!sc.isEmpty() && sc != scope && !(sc == QLatin1String("VNINDEX") && is_level))
            continue;
        const int rank = sc == scope ? (!metric.isEmpty() && nk == metric ? 0 : is_level ? 1 : 2) : sc.isEmpty() ? 2 : 3;
        shown.append({rank, n});
    }
    std::stable_sort(shown.begin(), shown.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
    for (const auto& ranked : std::as_const(shown)) {
        const QJsonObject& n = ranked.second;
        const QString sc = n.value(QStringLiteral("scope")).toString();
        QString line = esc((sc.isEmpty() ? QString() : sc + QStringLiteral(" ")) +
                           number_label(n.value(QStringLiteral("k")).toString(), sc.isEmpty() ? scope : sc) +
                           QStringLiteral(" ") +
                           number_value(n));
        QStringList meta;
        const QString org = n.value(QStringLiteral("src_org")).toString();
        const QString asof = n.value(QStringLiteral("asof")).toString();
        if (!org.isEmpty())
            meta << esc(org);
        if (!asof.isEmpty())
            meta << esc(date_vn(asof));
        line += QStringLiteral(" ") + tier_chip(n.value(QStringLiteral("tier")).toString());
        if (!meta.isEmpty())
            line += span(QStringLiteral(" ") + meta.join(QStringLiteral(" · ")), c_muted());
        const QString method = n.value(QStringLiteral("method")).toString().trimmed();
        if (!method.isEmpty()) {
            if (!methods.contains(method))
                methods << method;
            line += span(QStringLiteral(" ") + circled(methods.indexOf(method)), c_muted());
        }
        nums << span(line, c_text());
    }
    QString num_html = nums.join(QStringLiteral("<br>"));
    for (int m = 0; m < methods.size(); ++m)
        num_html += QStringLiteral("<br>") +
                    QStringLiteral("<span style=\"color:%1; font-size:10px;\">%2 %3</span>")
                        .arg(css(c_muted()), circled(m), esc(methods.at(m)));
    h += section(QStringLiteral("SỐ LIỆU"), num_html);

    QStringList srcs;
    int i = 0;
    for (const QJsonValue& sv : ev.value(QStringLiteral("sources")).toArray()) {
        const QJsonObject s = sv.toObject();
        QStringList parts;
        for (const char* key : {"org", "title"}) {
            const QString t = s.value(QLatin1String(key)).toString().trimmed();
            if (!t.isEmpty())
                parts << t;
        }
        const QString date = s.value(QStringLiteral("date")).toString();
        if (!date.isEmpty())
            parts << date_vn(date);
        const QString dom = domain(s.value(QStringLiteral("url")).toString());
        QString line = QStringLiteral("[%1] ").arg(++i) + esc(parts.join(QStringLiteral(" — "))) + QStringLiteral(" ") +
                       tier_chip(s.value(QStringLiteral("tier")).toString());
        if (!dom.isEmpty())
            line += span(QStringLiteral(" ") + esc(dom), c_muted());
        srcs << span(line, c_text());
    }
    h += section(QStringLiteral("NGUỒN"), srcs.join(QStringLiteral("<br>")));

    // Caveats of the event itself (strings, or objects with a text) — capped so the card still fits a screen.
    constexpr int kMaxWarn = 6;
    constexpr int kMaxWarnChars = 220;
    QStringList warns;
    int n_warn = 0;
    for (const QJsonValue& w : ev.value(QStringLiteral("warnings")).toArray()) {
        QString t = warning_text(w);
        if (t.isEmpty())
            continue;
        if (++n_warn > kMaxWarn)
            continue;
        if (t.size() > kMaxWarnChars)
            t = t.left(kMaxWarnChars - 1) + QStringLiteral("…");
        warns << esc(QStringLiteral("⚠ ") + t);
    }
    if (n_warn > kMaxWarn)
        warns << esc(QStringLiteral("⚠ … và %1 lưu ý khác").arg(n_warn - kMaxWarn));
    if (!warns.isEmpty())
        h += QStringLiteral("<div style=\"margin-top:6px; color:%1; font-size:10px;\">%2</div>")
                 .arg(css(c_rich()), warns.join(QStringLiteral("<br>")));
    // σ quoted in the free text is the curator's VNINDEX engine reading, not this chart's σ (numbers above are).
    bool sigma_in_text = false;
    for (const char* key : {"title", "nhan_phu", "boi_canh", "nguyen_nhan", "sau_do"})
        sigma_in_text = sigma_in_text || ev.value(QLatin1String(key)).toString().contains(QStringLiteral("σ"));
    for (const QJsonValue& f : ev.value(QStringLiteral("key_factors")).toArray())
        sigma_in_text = sigma_in_text || f.toString().contains(QStringLiteral("σ"));
    if (sigma_in_text)
        h += QStringLiteral("<div style=\"margin-top:6px; color:%1; font-size:10px;\">%2</div>")
                 .arg(css(c_muted()),
                      esc(index_scope(scope)
                              ? QStringLiteral("σ trong phần chữ: thang engine VNINDEX 12/2017→ trừ khi ghi khác.")
                              : QStringLiteral("σ trong phần chữ: thang do người tuyển ghi — có thể khác σ của chart "
                                               "này; số có nguồn ở mục SỐ LIỆU.")));
    h += QStringLiteral("<div style=\"margin-top:6px; color:%1; font-size:10px;\">Bối cảnh/nguyên nhân là diễn giải; "
                        "số có nguồn + bậc. Tham khảo, không khuyến nghị.</div>")
             .arg(css(c_muted()));
    return h + card_close();
}

/// Markers for the keynotes whose `scopes` contain `scope`. Index / basket chart: y = NaN, so HhpChart snaps them onto
/// its main line. Ticker chart (`scope` = a ticker): y = the event's own close (numbers[] k "close" of that ticker,
/// the unit of the chart's price line) — each metric's price line only has the points where that ratio exists and
/// bridges its gaps, so a snapped marker could sit far off the real price; no close → snapped as before.
/// A valuation extreme (fcview::valuation_extreme) is a P/E reading: ◇ "Cực trị P/E MM/yyyy", on the P/E chart only.
/// any_scope: every event qualifies (a per-ticker keynote file belongs to that ticker whatever its `scopes` say).
inline QVector<HhpChartNote> keynote_notes(const QJsonArray& keynotes, const QString& scope, const QString& metric,
                                           bool any_scope) {
    QVector<HhpChartNote> out;
    const bool ticker = !scope.isEmpty() && !fcview::index_scope(scope);
    for (const QJsonValue& v : keynotes) {
        const QJsonObject ev = v.toObject();
        if (!any_scope && !ev.value(QStringLiteral("scopes")).toArray().contains(QJsonValue(scope)))
            continue;
        const QString kind = ev.value(QStringLiteral("kind")).toString();
        if (kind != QLatin1String("dinh") && kind != QLatin1String("day"))
            continue;
        const bool extreme = fcview::valuation_extreme(ev);
        if (extreme && metric != QLatin1String("pe"))
            continue;
        const double ms = fcview::ms_of(ev, "ms", "date");
        if (!has(ms))
            continue;
        const bool peak = kind == QLatin1String("dinh");
        const bool provisional = ev.value(QStringLiteral("provisional")).toBool();
        const QDate d = QDateTime::fromMSecsSinceEpoch(static_cast<qint64>(ms), QTimeZone::UTC).date();
        HhpChartNote n;
        n.id = ev.value(QStringLiteral("id")).toString();
        if (extreme)
            n.kind = peak ? HhpChartNote::Kind::ExtremeHigh : HhpChartNote::Kind::ExtremeLow;
        else
            n.kind = peak ? HhpChartNote::Kind::Peak : HhpChartNote::Kind::Trough;
        n.x_ms = ms;
        if (ticker)
            n.y = fcview::event_close(ev, scope);
        const QString what = extreme ? QStringLiteral("Cực trị P/E ")
                             : peak  ? QStringLiteral("Đỉnh ")
                                     : QStringLiteral("Đáy ");
        n.label = what + d.toString(QStringLiteral("MM/yyyy")) + (provisional ? QStringLiteral(" (tạm)") : QString());
        // "P/E 10,3x (−2,4σ)" is a VNINDEX P/E reading: never pinned on a basket or a P/B chart.
        const QString sub = ev.value(QStringLiteral("nhan_phu")).toString();
        if (fcview::text_fits_chart(sub, scope, metric))
            n.sub = sub;
        n.detail_html = keynote_html(ev, scope, metric);
        n.priority = std::clamp(ev.value(QStringLiteral("priority")).toInt(2), 1, 3);
        n.hollow = provisional || ev.value(QStringLiteral("tier_effective")).toString() == QLatin1String("UNVERIFIED");
        out.append(n);
    }
    return out;
}

inline QVector<HhpChartNote> keynote_notes(const QJsonArray& keynotes, const QString& scope, const QString& metric) {
    return keynote_notes(keynotes, scope, metric, false);
}

// ── Sell-side index targets (◆, one per horizon bucket) ──────────────────────

inline QString target_html(const QJsonObject& t) {
    using namespace fcview;
    const QJsonArray members = t.value(QStringLiteral("members")).toArray();
    const double ms = ms_of(t, "ms", "horizon");
    const QString horizon = has(ms) ? fmt_date(ms) : esc(t.value(QStringLiteral("horizon")).toString());
    QString h = card_open();
    h += QStringLiteral("<div style=\"color:%1; font-weight:bold; font-size:12px;\">◆ MỤC TIÊU VN-INDEX CỦA CTCK · kỳ %2</div>")
             .arg(css(c_gold()), horizon);
    // Members flagged weight0 (e.g. a fund's "possible" scenario) are listed but not part of the median.
    int n_used = 0;
    for (const QJsonValue& mv : members)
        n_used += mv.toObject().value(QStringLiteral("weight0")).toBool() ? 0 : 1;
    QString count = QStringLiteral("%1 mức").arg(n_used);
    if (n_used < members.size())
        count += QStringLiteral(" (+%1 chỉ liệt kê)").arg(members.size() - n_used);
    h += QStringLiteral("<div style=\"color:%1; font-size:12px; margin-top:3px;\">Trung vị <b>%2</b> điểm · %3</div>")
             .arg(css(c_text()), esc(level(num(t.value(QStringLiteral("value"))))), esc(count));
    QStringList rows;
    for (const QJsonValue& mv : members) {
        const QJsonObject m = mv.toObject();
        const bool w0 = m.value(QStringLiteral("weight0")).toBool();
        QStringList parts;
        parts << m.value(QStringLiteral("org")).toString();
        const QString date = m.value(QStringLiteral("date")).toString();
        if (!date.isEmpty())
            parts << date_vn(date);
        const double mval = num(m.value(QStringLiteral("value")));
        parts << (has(mval) ? level(mval) : QStringLiteral("[CẦN DATA]"));
        static const QHash<QString, QString> scenario_vi = {
            {QStringLiteral("co_so"), QStringLiteral("cơ sở")},       {QStringLiteral("base"), QStringLiteral("cơ sở")},
            {QStringLiteral("tich_cuc"), QStringLiteral("tích cực")}, {QStringLiteral("tieu_cuc"), QStringLiteral("tiêu cực")},
            {QStringLiteral("lac_quan"), QStringLiteral("lạc quan")}, {QStringLiteral("bi_quan"), QStringLiteral("bi quan")},
            {QStringLiteral("co_the"), QStringLiteral("kịch bản có thể")},
        };
        const QString scenario = m.value(QStringLiteral("scenario")).toString();
        if (!scenario.isEmpty())
            parts << scenario_vi.value(scenario, scenario);
        for (const char* key : {"note", "scenario_note"}) {
            const QString note = m.value(QLatin1String(key)).toString().trimmed();
            if (!note.isEmpty() && !parts.contains(note))
                parts << note;
        }
        if (w0) {
            QString why;
            for (const char* key : {"weight0_note", "weight0_ly_do", "ly_do"})
                if (why.isEmpty())
                    why = m.value(QLatin1String(key)).toString().trimmed();
            parts << QStringLiteral("không tính vào trung vị") + (why.isEmpty() ? QString() : QStringLiteral(": ") + why);
        }
        QString line = esc(parts.join(QStringLiteral(" — "))) + QStringLiteral(" ") +
                       tier_chip(m.value(QStringLiteral("tier")).toString());
        const QString dom = domain(m.value(QStringLiteral("url")).toString());
        if (!dom.isEmpty())
            line += span(QStringLiteral(" ") + esc(dom), c_muted());
        rows << span(line, w0 ? c_muted() : c_text());
    }
    h += section(QStringLiteral("CÁC MỨC CÙNG KỲ HẠN"), rows.join(QStringLiteral("<br>")));
    h += QStringLiteral("<div style=\"margin-top:6px; color:%1; font-size:10px;\">Mục tiêu của các CTCK (không phải dự "
                        "phóng HHP); kỳ hạn làm tròn về 30/06 hoặc 31/12. Tham khảo, không khuyến nghị.</div>")
             .arg(css(c_muted()));
    return h + card_close();
}

/// ◆ markers at (horizon, median target) — y is the index level, so they sit in the forecast region.
inline QVector<HhpChartNote> target_notes(const QJsonArray& targets) {
    QVector<HhpChartNote> out;
    for (const QJsonValue& v : targets) {
        const QJsonObject t = v.toObject();
        const double ms = fcview::ms_of(t, "ms", "horizon");
        const double value = num(t.value(QStringLiteral("value")));
        if (!has(ms) || !has(value))
            continue;
        HhpChartNote n;
        n.id = t.value(QStringLiteral("id")).toString();
        n.kind = HhpChartNote::Kind::Target;
        n.x_ms = ms;
        n.y = value;
        n.label = t.value(QStringLiteral("label")).toString();
        if (n.label.isEmpty())
            n.label = QStringLiteral("MT ") +
                      QDateTime::fromMSecsSinceEpoch(static_cast<qint64>(ms), QTimeZone::UTC).toString(QStringLiteral("MM/yy"));
        n.sub = QStringLiteral("trung vị ") + fcview::level(value);
        n.detail_html = target_html(t);
        n.priority = 3; // keynotes label first; a target keeps its ◆ + card when space runs out
        out.append(n);
    }
    return out;
}

// ── Per-ticker price targets (◆, one per source) ─────────────────────────────

/// Card of one ticker target: org, published date, horizon, the target in đồng as published, where the ◆ sits on
/// the chart's adjusted-price scale (`value`, `unit`; `scale` = adjusted ÷ actual price on the same day, upstream),
/// the source's own rating, tier, url or file.
inline QString ticker_target_html(const QJsonObject& t, const QString& unit) {
    using namespace fcview;
    const QString org = t.value(QStringLiteral("org")).toString();
    const double hz = ms_of(t, "ms", "horizon");
    const double vnd = num(t.value(QStringLiteral("value_vnd")));
    const double v = num(t.value(QStringLiteral("value")));
    const double scale = num(t.value(QStringLiteral("scale")));
    QString h = card_open();
    h += QStringLiteral("<div style=\"color:%1; font-weight:bold; font-size:12px;\">◆ GIÁ MỤC TIÊU · %2</div>")
             .arg(css(c_gold()), esc(org.isEmpty() ? QStringLiteral("[CẦN DATA]") : org));
    QStringList when;
    const QString date = t.value(QStringLiteral("date")).toString();
    when << QStringLiteral("công bố ") + (date.isEmpty() ? QStringLiteral("[CẦN DATA]") : date_vn(date));
    if (has(hz))
        when << QStringLiteral("kỳ hạn ") + fmt_date(hz);
    h += QStringLiteral("<div style=\"color:%1; font-size:12px; margin-top:3px;\">Mục tiêu <b>%2</b> · %3</div>")
             .arg(css(c_text()), esc(has(vnd) ? fmt_vi(vnd) + QStringLiteral(" đ") : QStringLiteral("[CẦN DATA]")),
                  esc(when.join(QStringLiteral(" · "))));
    const QString rating = t.value(QStringLiteral("rating")).toString().trimmed();
    const int n_an = t.value(QStringLiteral("n_analysts")).toInt(0);
    if (!rating.isEmpty() || n_an > 0)
        h += QStringLiteral("<div style=\"color:%1; margin-top:2px;\">%2</div>")
                 .arg(css(c_text()), esc(QStringLiteral("Xếp hạng của nguồn: ") +
                                         (rating.isEmpty() ? QStringLiteral("—") : rec_display(rating)) +
                                         (n_an > 0 ? QStringLiteral(" · %1 chuyên viên").arg(n_an) : QString())));
    QString where = QStringLiteral("Trên chart: ") +
                    (has(v) ? level(v) + QStringLiteral(" ") + unit : QStringLiteral("—"));
    if (has(scale) && std::abs(scale - 1.0) > 1e-9)
        where += QStringLiteral(" = %1 đ ÷ 1000 × %2 (hệ số giá điều chỉnh ÷ giá thực tế cùng ngày)")
                     .arg(has(vnd) ? fmt_vi(vnd) : QStringLiteral("?"), fmt_ratio(scale, 4));
    else if (has(scale))
        where += QStringLiteral(" (giá điều chỉnh = giá thực tế, hệ số 1)");
    h += section(QStringLiteral("VỊ TRÍ ◆"), span(esc(where), c_text()));
    QString src = QStringLiteral("Bậc ") + tier_chip(t.value(QStringLiteral("tier")).toString());
    const QString url = t.value(QStringLiteral("url")).toString();
    const QString file = t.value(QStringLiteral("file")).toString();
    if (!url.isEmpty() || !file.isEmpty())
        src += span(QStringLiteral(" ") + esc(url.isEmpty() ? file : url), c_muted());
    h += section(QStringLiteral("NGUỒN"), src);
    h += QStringLiteral("<div style=\"margin-top:6px; color:%1; font-size:10px;\">Giá mục tiêu của nguồn nêu trên "
                        "— không phải dự phóng HHP. Tham khảo, không khuyến nghị.</div>")
             .arg(css(c_muted()));
    return h + card_close();
}

/// ◆ at (horizon, target on the chart's price scale) — one per source, not bucketed. Members without a finite
/// horizon or chart value are skipped (the script already drops malformed ones).
inline QVector<HhpChartNote> ticker_target_notes(const QJsonArray& targets, const QString& unit) {
    QVector<HhpChartNote> out;
    for (const QJsonValue& v : targets) {
        const QJsonObject t = v.toObject();
        const double ms = fcview::ms_of(t, "ms", "horizon");
        const double value = num(t.value(QStringLiteral("value")));
        if (!has(ms) || !has(value))
            continue;
        const double vnd = num(t.value(QStringLiteral("value_vnd")));
        HhpChartNote n;
        n.id = t.value(QStringLiteral("id")).toString();
        if (n.id.isEmpty())
            n.id = QStringLiteral("tg-%1").arg(out.size());
        n.kind = HhpChartNote::Kind::Target;
        n.x_ms = ms;
        n.y = value;
        n.label = t.value(QStringLiteral("label")).toString();
        if (n.label.isEmpty())
            n.label = t.value(QStringLiteral("org")).toString().section(QLatin1Char(' '), 0, 0) + QStringLiteral(" ") +
                      QDateTime::fromMSecsSinceEpoch(static_cast<qint64>(ms), QTimeZone::UTC).toString(QStringLiteral("MM/yy"));
        n.sub = has(vnd) ? fmt_vi(vnd) + QStringLiteral(" đ") : fcview::level(value);
        n.detail_html = ticker_target_html(t, unit);
        n.priority = 3;
        out.append(n);
    }
    return out;
}

// ── Forecast series ──────────────────────────────────────────────────────────

/// VNINDEX: the P/E (P/B) price bands moved along the forecast EPS (BVPS) path — same colours, dashed.
/// Empty when any of the five level arrays is missing.
inline QVector<HhpChartSeries> index_forecast_series(const QJsonObject& fc) {
    const QJsonObject p = fc.value(QStringLiteral("points")).toObject();
    const auto pts = [&p](const char* key) { return to_points(p.value(QLatin1String(key)).toArray()); };
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
        s.forecast = true;
        return s;
    };
    return {make(HhpChartSeries::Kind::Band, QStringLiteral("Vùng rẻ DP"), c_cheap(), 1.6, 0.30, c1, c2),
            make(HhpChartSeries::Kind::Band, QStringLiteral("Vùng mắc DP"), c_rich(), 1.6, 0.26, r2, r1),
            make(HhpChartSeries::Kind::Dashed, QStringLiteral("TB DP"), c_fair(), 1.2, 1.0, fair, {})};
}

/// Basket: flat ±1σ/±2σ bands and mean extended over the forecast months, plus the ratio the basket would
/// have if its price stayed where it is ("… nếu giá đứng yên", same colour as the ratio line, dashed).
inline QVector<HhpChartSeries> basket_forecast_series(const QJsonObject& fc, const QString& metric_label) {
    const QVector<QPointF> path = to_points(fc.value(QStringLiteral("ratio_path")).toArray());
    if (path.isEmpty())
        return {};
    const QJsonObject flat = fc.value(QStringLiteral("flat")).toObject();
    const double mean = num(flat.value(QStringLiteral("mean")));
    const double p1 = num(flat.value(QStringLiteral("p1")));
    const double p2 = num(flat.value(QStringLiteral("p2")));
    const double m1 = num(flat.value(QStringLiteral("m1")));
    const double m2 = num(flat.value(QStringLiteral("m2")));
    QVector<HhpChartSeries> out;
    const auto add = [&](HhpChartSeries::Kind kind, const QString& name, const QColor& color, double width,
                         double opacity, const QVector<QPointF>& upper, const QVector<QPointF>& lower) {
        HhpChartSeries s;
        s.kind = kind;
        s.name = name;
        s.color = color;
        s.width = width;
        s.opacity = opacity;
        s.points = upper;
        s.lower = lower;
        s.forecast = true;
        out.append(s);
    };
    if (has(m1) && has(m2))
        add(HhpChartSeries::Kind::Band, QStringLiteral("Vùng rẻ DP"), c_cheap(), 1.6, 0.30, flat_like(path, m1),
            flat_like(path, m2));
    if (has(p1) && has(p2))
        add(HhpChartSeries::Kind::Band, QStringLiteral("Vùng mắc DP"), c_rich(), 1.6, 0.26, flat_like(path, p2),
            flat_like(path, p1));
    if (has(mean))
        add(HhpChartSeries::Kind::Dashed, QStringLiteral("TB DP"), c_fair(), 1.2, 1.0, flat_like(path, mean), {});
    add(HhpChartSeries::Kind::Line, QStringLiteral("%1 nếu giá đứng yên").arg(metric_label), c_idx(), 2.0, 1.0, path,
        {});
    return out;
}

// ── Forecast basis (per-year growth + where it comes from) ───────────────────

/// "+25.2%" (+ "*" when the year is an estimate: thin sources or the long-run rule).
/// decimal: the payload holds decimals for sure (per-ticker forecast) — see fcview::growth_pct().
inline QString growth_text(const QJsonObject& g, bool decimal) {
    const double pct = fcview::growth_pct(num(g.value(QStringLiteral("g"))), decimal);
    return fmt_pct(pct, 1) + (g.value(QStringLiteral("est")).toBool() ? QStringLiteral("*") : QString());
}
inline QString growth_text(const QJsonObject& g) {
    return growth_text(g, false);
}

/// "8 nguồn, trung vị có trọng số (W 6.5; 11–29.5%)" or "quy tắc dài hạn" — plain text.
/// book: BV growth is derived from that year's EPS → "suy từ EPS (…)" with the EPS source count/weight: eps_n/eps_W
/// when the bridge writes them, else n/W (older bridge files copied the EPS values there).
inline QString growth_basis(const QJsonObject& g, bool book, bool decimal) {
    const bool eps_keys = book && g.contains(QStringLiteral("eps_n"));
    const int n = g.value(eps_keys ? QStringLiteral("eps_n") : QStringLiteral("n")).toInt(0);
    const double w = num(g.value(eps_keys ? QStringLiteral("eps_W") : QStringLiteral("W")));
    if (n <= 0 || !has(w) || w <= 0)
        return book ? QStringLiteral("suy từ EPS theo quy tắc dài hạn (không nguồn)")
                    : QStringLiteral("quy tắc dài hạn (không nguồn)");
    QString t = QStringLiteral("%1 nguồn, W %2").arg(n).arg(fmt_ratio(w, 2));
    const double lo = fcview::growth_pct(num(g.value(QStringLiteral("min"))), decimal);
    const double hi = fcview::growth_pct(num(g.value(QStringLiteral("max"))), decimal);
    if (has(lo) && has(hi))
        t += QStringLiteral("; %1…%2%").arg(fmt_ratio(lo, 1), fmt_ratio(hi, 1));
    return book ? QStringLiteral("suy từ EPS (%1)").arg(t) : t;
}
inline QString growth_basis(const QJsonObject& g, bool book = false) {
    return growth_basis(g, book, false);
}

/// Hover text per forecast year: [1/1/Y, 1/1/Y+1) ∩ [x0, ∞) → "EPS 2027 +12.0% · 6 nguồn, W 4.75 [tier]".
inline QVector<HhpChartSpan> forecast_basis_spans(const QJsonObject& fc, bool book, bool decimal) {
    QVector<HhpChartSpan> out;
    const double x0 = num(fc.value(QStringLiteral("x0")));
    for (const QJsonValue& v : fc.value(QStringLiteral("growth")).toArray()) {
        const QJsonObject g = v.toObject();
        const int year = g.value(QStringLiteral("year")).toInt(0);
        if (year <= 0)
            continue;
        HhpChartSpan s;
        s.x0_ms = fcview::iso_ms(QStringLiteral("%1-01-01").arg(year));
        s.x1_ms = fcview::iso_ms(QStringLiteral("%1-01-01").arg(year + 1));
        if (has(x0))
            s.x0_ms = std::max<qreal>(s.x0_ms, x0);
        s.text = fcview::esc(QStringLiteral("%1 %2 %3 · %4 ")
                                 .arg(book ? QStringLiteral("BVPS") : QStringLiteral("EPS"))
                                 .arg(year)
                                 .arg(growth_text(g, decimal), growth_basis(g, book, decimal))) +
                 fcview::tier_chip(g.value(QStringLiteral("tier")).toString());
        out.append(s);
    }
    return out;
}
inline QVector<HhpChartSpan> forecast_basis_spans(const QJsonObject& fc, bool book) {
    return forecast_basis_spans(fc, book, false);
}

/// One line under the chart: per-year growth + basis + tier, then caveats and the not-advice statement.
/// r_fallback: retention ratio to quote when `fc` has none (basket P/B reuses the VNINDEX BV growth and its r).
inline QString forecast_basis_html(const QJsonObject& fc, bool book, double r_fallback, bool decimal) {
    using namespace fcview;
    QStringList years;
    bool any_est = false;
    for (const QJsonValue& v : fc.value(QStringLiteral("growth")).toArray()) {
        const QJsonObject g = v.toObject();
        const int year = g.value(QStringLiteral("year")).toInt(0);
        if (year <= 0)
            continue;
        any_est = any_est || g.value(QStringLiteral("est")).toBool();
        years << QStringLiteral("<b>%1</b> %2 — %3 %4")
                     .arg(QString::number(year), esc(growth_text(g, decimal)), esc(growth_basis(g, book, decimal)),
                          tier_chip(g.value(QStringLiteral("tier")).toString()));
    }
    if (years.isEmpty())
        return {};
    QString h = esc(book ? QStringLiteral("BVPS dự phóng (tăng trưởng giá trị sổ sách): ")
                         : QStringLiteral("EPS dự phóng (đồng thuận có trọng số): ")) +
                years.join(QStringLiteral(" · "));
    const QJsonObject ret = fc.value(QStringLiteral("retention")).toObject();
    double r = num(ret.value(QStringLiteral("r")));
    if (!has(r))
        r = r_fallback;
    if (book && has(r))
        h += esc(QStringLiteral(" · BVPS += %1 × EPS mỗi năm (tỷ lệ giữ lại, EST)").arg(fmt_ratio(r, 2)));
    if (any_est && book)
        h += esc(QStringLiteral(" · * = EST (BVPS suy từ EPS đồng thuận theo tỷ lệ giữ lại r = %1)")
                     .arg(has(r) ? fmt_ratio(r, 2) : QStringLiteral("[CẦN DATA]")));
    else if (any_est)
        h += esc(QStringLiteral(" · * = EST (nguồn mỏng hoặc quy tắc dài hạn)"));
    QStringList cav;
    for (const QJsonValue& c : fc.value(QStringLiteral("caveats")).toArray()) {
        if (!c.toString().isEmpty())
            cav << esc(c.toString());
    }
    if (!cav.isEmpty())
        h += QStringLiteral("<br>") + span(cav.join(QStringLiteral(" · ")), c_muted());
    return h;
}
inline QString forecast_basis_html(const QJsonObject& fc, bool book, double r_fallback = kNaN) {
    return forecast_basis_html(fc, book, r_fallback, false);
}

/// Tooltip for that line: every source behind every year (org, value, weight, date, tier, coverage).
inline QString forecast_sources_html(const QJsonObject& fc, bool book, bool decimal) {
    using namespace fcview;
    QString h;
    for (const QJsonValue& v : fc.value(QStringLiteral("growth")).toArray()) {
        const QJsonObject g = v.toObject();
        const int year = g.value(QStringLiteral("year")).toInt(0);
        if (year <= 0)
            continue;
        h += QStringLiteral("<b>%1 %2 %3</b> %4").arg(book ? QStringLiteral("BVPS") : QStringLiteral("EPS"))
                 .arg(year)
                 .arg(esc(growth_text(g, decimal)), tier_chip(g.value(QStringLiteral("tier")).toString()));
        const QString flag = g.value(QStringLiteral("flag")).toString();
        if (!flag.isEmpty())
            h += QStringLiteral("<br>") + span(esc(flag), c_muted());
        QStringList listed_only; // weight 0 (superseded / UNVERIFIED / lower bound …): named, not detailed
        for (const QJsonValue& sv : g.value(QStringLiteral("sources")).toArray()) {
            const QJsonObject s = sv.toObject();
            const QString org = s.value(QStringLiteral("org")).toString(s.value(QStringLiteral("id")).toString());
            const QString date = s.value(QStringLiteral("date")).toString();
            const double w = num(s.value(QStringLiteral("weight")));
            if (has(w) && w <= 0) {
                listed_only << org + (date.isEmpty() ? QString() : QStringLiteral(" ") + date_vn(date));
                continue;
            }
            QStringList parts;
            parts << org;
            parts << fmt_pct(growth_pct(num(s.value(QStringLiteral("value"))), decimal), 1);
            if (has(w))
                parts << QStringLiteral("w %1").arg(fmt_ratio(w, 2));
            if (!date.isEmpty())
                parts << date_vn(date);
            const double cov = num(s.value(QStringLiteral("coverage_mcap_pct")));
            const double nt = num(s.value(QStringLiteral("n_tickers")));
            if (has(nt) || has(cov))
                parts << QStringLiteral("%1 mã, %2% vốn hoá")
                             .arg(has(nt) ? QString::number(qRound(nt)) : QStringLiteral("?"),
                                  has(cov) ? fmt_ratio(cov, 1) : QStringLiteral("?"));
            const QString note = s.value(QStringLiteral("note")).toString();
            if (!note.isEmpty())
                parts << note;
            QString where = s.value(QStringLiteral("url")).toString();
            where = where.isEmpty() ? s.value(QStringLiteral("file")).toString() : domain(where);
            h += QStringLiteral("<br>&nbsp;&nbsp;• ") + esc(parts.join(QStringLiteral(" · "))) + QStringLiteral(" ") +
                 tier_chip(s.value(QStringLiteral("tier")).toString()) +
                 (where.isEmpty() ? QString() : span(QStringLiteral(" ") + esc(where), c_muted()));
        }
        if (!listed_only.isEmpty())
            h += QStringLiteral("<br>&nbsp;&nbsp;") +
                 span(esc(QStringLiteral("trọng số 0 (bản cũ / UNVERIFIED — chỉ liệt kê): ") +
                          listed_only.join(QStringLiteral(", "))),
                      c_muted());
        h += QStringLiteral("<br>");
    }
    const QString method = fc.value(QStringLiteral("method")).toString();
    if (!method.isEmpty())
        h += span(esc(QStringLiteral("Phương pháp: ") + method), c_muted());
    return h;
}
inline QString forecast_sources_html(const QJsonObject& fc, bool book) {
    return forecast_sources_html(fc, book, false);
}

} // namespace fincept::screens::hhp
