// src/screens/hhp_valuation/HhpCommon.h
// Shared helpers for the HHP valuation module — phương pháp Huỳnh Hoàng Phương:
//   P = E × P/E  và  P = BVPS × P/B ; vùng rẻ/đắt = μ ± 1σ / ± 2σ của CHÍNH ratio lịch sử
//   (của chỉ số, của rổ, của từng mã — không so với ngành hay thị trường).
//
// Data comes from scripts/hhp_valuation.py, which reads the JSON files the HHP pipeline
// rebuilds 3×/day in ~/SECOND BRAIN-OBSIDIAN/_System/knowledge_os/ (the same files behind
// the Cowork page hhp_vn100_valuation.html). Palette = that page's :root variables, so the
// terminal module and the web page read the same at a glance.
#pragma once

#include <QColor>
#include <QDateTime>
#include <QHash>
#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QLocale>
#include <QPointF>
#include <QRegularExpression>
#include <QString>
#include <QTimeZone>
#include <QVector>

#include <cmath>
#include <limits>

namespace fincept::screens::hhp {

// ── Palette (hex identical to hhp_vn100_valuation.html :root) ────────────────
inline QColor c_bg() { return QColor(0x0a, 0x0b, 0x0d); }      // --bg
inline QColor c_card() { return QColor(0x14, 0x17, 0x1c); }    // --card
inline QColor c_line() { return QColor(0x26, 0x2b, 0x33); }    // --line (borders)
inline QColor c_grid() { return QColor(0x20, 0x24, 0x2b); }    // chart grid
inline QColor c_text() { return QColor(0xec, 0xe9, 0xe3); }    // --txt
inline QColor c_muted() { return QColor(0x8b, 0x90, 0x99); }   // --mut
inline QColor c_gold() { return QColor(0xe8, 0xc8, 0x78); }    // --gold (accent)
inline QColor c_cheap() { return QColor(0x3f, 0xae, 0x73); }   // --cheap
inline QColor c_cheap2() { return QColor(0x1f, 0x6b, 0x46); }  // --cheap2
inline QColor c_rich() { return QColor(0xd8, 0x50, 0x4f); }    // --rich
inline QColor c_rich2() { return QColor(0x7e, 0x2b, 0x2b); }   // --rich2
inline QColor c_neutral() { return QColor(0x3a, 0x41, 0x50); } // --neu
inline QColor c_idx() { return QColor(0xf2, 0xc4, 0x3d); }     // --idx (main line)
inline QColor c_fair() { return QColor(0x9a, 0xa4, 0xb2); }    // mean line
inline QColor c_blue() { return QColor(0x7a, 0xa7, 0xe0); }    // P/B Non-VIC3 line

inline QString css(const QColor& c) { return c.name(QColor::HexRgb); }

// ── JSON number helpers ──────────────────────────────────────────────────────
inline constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();

/// JSON number → double; null / missing / non-number → NaN.
inline double num(const QJsonValue& v) { return v.isDouble() ? v.toDouble() : kNaN; }
inline bool has(double v) { return !std::isnan(v) && !std::isinf(v); }

/// [[epoch_ms, value], ...] → points (x = epoch ms as qreal). Pairs with a null value are skipped.
inline QVector<QPointF> to_points(const QJsonArray& arr) {
    QVector<QPointF> out;
    out.reserve(arr.size());
    for (const QJsonValue& p : arr) {
        const QJsonArray pair = p.toArray();
        if (pair.size() < 2 || !pair.at(0).isDouble() || !pair.at(1).isDouble())
            continue;
        out.append(QPointF(pair.at(0).toDouble(), pair.at(1).toDouble()));
    }
    return out;
}

/// Same x-grid as `grid`, constant y = level (flat band edge for basket charts).
inline QVector<QPointF> flat_like(const QVector<QPointF>& grid, double level) {
    QVector<QPointF> out;
    out.reserve(grid.size());
    for (const QPointF& p : grid)
        out.append(QPointF(p.x(), level));
    return out;
}

// ── Zones ────────────────────────────────────────────────────────────────────
// Script normalises the Vietnamese zone labels to keys:
//   "RẺ (<−1σ)" → "cheap", "TRUNG TÍNH" → "neutral", "ĐẮT (>+1σ)" → "rich".
inline QColor zone_color(const QString& key) {
    if (key == QLatin1String("cheap"))
        return c_cheap();
    if (key == QLatin1String("rich"))
        return c_rich();
    return c_muted();
}

inline QString zone_short(const QString& key) {
    if (key == QLatin1String("cheap"))
        return QStringLiteral("RẺ");
    if (key == QLatin1String("rich"))
        return QStringLiteral("ĐẮT");
    if (key == QLatin1String("neutral"))
        return QStringLiteral("TRUNG TÍNH");
    return QStringLiteral("—");
}

/// Broker recommendation colour — same regexes as the Cowork page's recCls().
inline QColor rec_color(const QString& rec) {
    const QString u = rec.toUpper();
    static const QRegularExpression buy(QStringLiteral("MUA|KHẢ|KHA|BUY|ADD"));
    static const QRegularExpression sell(QStringLiteral("BÁN|BAN|SELL|REDUCE"));
    if (u.contains(buy))
        return c_cheap();
    if (u.contains(sell))
        return c_rich();
    return c_muted();
}

/// Display form of a broker label. Upstream mixes "KHA QUAN" and "KHẢ QUAN" in one column, so the
/// unaccented spellings get their diacritics back. Display only: sort on and rec_color() the raw value.
inline QString rec_display(const QString& rec) {
    static const QHash<QString, QString> accented = {
        {QStringLiteral("KHA QUAN"), QStringLiteral("KHẢ QUAN")},
        {QStringLiteral("TRUNG LAP"), QStringLiteral("TRUNG LẬP")},
        {QStringLiteral("NAM GIU"), QStringLiteral("NẮM GIỮ")},
        {QStringLiteral("BAN"), QStringLiteral("BÁN")},
        {QStringLiteral("MUA MANH"), QStringLiteral("MUA MẠNH")},
    };
    return accented.value(rec.trimmed().toUpper(), rec);
}

// ── Formatting ───────────────────────────────────────────────────────────────
// Matches the Cowork page: index levels and prices use Vietnamese grouping
// ("1.815,7", "65.800"); ratios and σ stay plain ("12.53", "-1.29").

/// Vietnamese locale number: grouping "." and decimal ",". NaN → "—".
inline QString fmt_vi(double v, int decimals = 0) {
    if (!has(v))
        return QStringLiteral("—");
    static const QLocale vi(QLocale::Vietnamese, QLocale::Vietnam);
    return vi.toString(v, 'f', decimals);
}

/// Plain ratio, trailing zeros trimmed like JS number→string ("12.5", "2.04"). NaN → "—".
inline QString fmt_ratio(double v, int max_decimals = 2) {
    if (!has(v))
        return QStringLiteral("—");
    QString s = QString::number(v, 'f', max_decimals);
    if (s.contains(QLatin1Char('.'))) {
        while (s.endsWith(QLatin1Char('0')))
            s.chop(1);
        if (s.endsWith(QLatin1Char('.')))
            s.chop(1);
    }
    return s;
}

/// σ with explicit sign: "+0.5", "-1.29". NaN → "—". (Append "σ" at the call site if wanted.)
inline QString fmt_sigma(double v) {
    if (!has(v))
        return QStringLiteral("—");
    return (v > 0 ? QStringLiteral("+") : QString()) + fmt_ratio(v, 2);
}

/// Percentage with explicit sign: "+36.3%". NaN → "—".
inline QString fmt_pct(double v, int decimals = 1) {
    if (!has(v))
        return QStringLiteral("—");
    return (v >= 0 ? QStringLiteral("+") : QString()) + QString::number(v, 'f', decimals) + QLatin1Char('%');
}

/// epoch ms → "dd/MM/yyyy" (UTC, like the page's tooltip format).
inline QString fmt_date(qreal ms) {
    return QDateTime::fromMSecsSinceEpoch(static_cast<qint64>(ms), QTimeZone::UTC).toString(QStringLiteral("dd/MM/yyyy"));
}

// ── Range filter (YTD / 1Y / 2Y / 3Y / 5Y / 10Y / ALL) ───────────────────────
inline const QStringList& range_keys() {
    static const QStringList keys = {QStringLiteral("YTD"), QStringLiteral("1Y"), QStringLiteral("2Y"),
                                     QStringLiteral("3Y"),  QStringLiteral("5Y"), QStringLiteral("10Y"),
                                     QStringLiteral("ALL")};
    return keys;
}

/// Lower x-bound (epoch ms) for a range key counted back from `anchor_ms`. HhpChart anchors on the
/// current time, like the Cowork page's _cut(): a series that stopped updating (KOS P/E ends in 2021)
/// must not show its last year under a "1Y" label. 0 = no cut (ALL / unknown key).
inline qreal range_cutoff(const QString& key, qreal anchor_ms) {
    if (key == QLatin1String("ALL") || anchor_ms <= 0)
        return 0;
    const QDateTime a = QDateTime::fromMSecsSinceEpoch(static_cast<qint64>(anchor_ms), QTimeZone::UTC);
    if (key == QLatin1String("YTD"))
        return static_cast<qreal>(QDateTime(QDate(a.date().year(), 1, 1), QTime(0, 0), QTimeZone::UTC).toMSecsSinceEpoch());
    int years = 0;
    if (key == QLatin1String("1Y"))
        years = 1;
    else if (key == QLatin1String("2Y"))
        years = 2;
    else if (key == QLatin1String("3Y"))
        years = 3;
    else if (key == QLatin1String("5Y"))
        years = 5;
    else if (key == QLatin1String("10Y"))
        years = 10;
    if (years == 0)
        return 0;
    return static_cast<qreal>(a.addYears(-years).toMSecsSinceEpoch());
}

} // namespace fincept::screens::hhp
