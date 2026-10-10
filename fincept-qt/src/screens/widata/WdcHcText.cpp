// WdcHcText.cpp, package B: TextMetrics (see WdcHcText.h for the two profiles and the T00 decision).
#include "WdcHcText.h"

#include "WdcHcMath.h"

#include <QDir>
#include <QFont>
#include <QFontDatabase>
#include <QFontMetricsF>
#include <QGuiApplication>
#include <QMutex>
#include <QStringList>
#include <QTextLayout>

#include <cmath>
#include <map>
#include <memory>

// Highcharts runs in JavaScript: no fused multiply-add. Clang contracts a*b+c into FMA by default
// (-ffp-contract=on), which flips spline clamps and tick comparisons by one ulp (ENG_w3 §2).
#if defined(__clang__)
#pragma clang fp contract(off)
#elif defined(__GNUC__)
#pragma GCC optimize("fp-contract=off")
#endif

namespace fincept::screens::wdc {

namespace {

constexpr double kWdcTextBig = 2048.0;   // Inter unitsPerEm: shaping at this size is exact in font units

// Static instance files P0 exported (fonts/README.md); weights 400/500/600 x opsz 14/16.
const char* const kWdcTextFiles[] = {"Inter-400-opsz14.ttf", "Inter-500-opsz14.ttf", "Inter-600-opsz14.ttf",
                                     "Inter-400-opsz16.ttf", "Inter-500-opsz16.ttf", "Inter-600-opsz16.ttf"};

int wdcText_clampWeight(int w) { return w <= 450 ? 400 : (w <= 550 ? 500 : 600); }

QFont wdcText_bigFont(double px, int weight) {
    QFont f(interStaticFamily(px));
    f.setWeight(QFont::Weight(wdcText_clampWeight(weight)));
    f.setPixelSize(int(kWdcTextBig));
    f.setKerning(true);
    f.setHintingPreference(QFont::PreferNoHinting);
    f.setStyleStrategy(QFont::NoFontMerging);
    return f;
}

// One QFontMetricsF at 2048 px per weight (one opsz family, see interStaticFamily); thread_local because layout may
// run off the UI thread.
const QFontMetricsF& wdcText_bigMetrics(double px, int weight) {
    thread_local std::map<std::pair<QString, int>, std::unique_ptr<QFontMetricsF>> cache;
    auto& slot = cache[{interStaticFamily(px), wdcText_clampWeight(weight)}];
    if (!slot) slot = std::make_unique<QFontMetricsF>(wdcText_bigFont(px, weight));
    return *slot;
}

} // namespace

// WiData loads Inter 400/500 from Google Fonts as static subsets, which are the opsz 14 instance at every size:
// the 16 px h6 of the single-chart page is 230.41 px wide = opsz 14 outlines (opsz 16 gives 228.53; F2_w3 §4,
// FACT). Every size measures and draws with opsz 14 (wave 4); the opsz 16 files stay registered, unused here.
QString interStaticFamily(double px) {
    Q_UNUSED(px);
    return QStringLiteral("Inter Static opsz14");
}

bool ensureInterFonts() {
    static QMutex mutex;
    QMutexLocker lock(&mutex);
    static int state = 0;   // 0 unknown, 1 available, 2 unavailable
    if (state) return state == 1;
    if (!QGuiApplication::instance()) return false;
    auto has = [] {
        const QStringList fams = QFontDatabase::families();
        return fams.contains(QStringLiteral("Inter Static opsz14"));
    };
    if (!has()) {
        const QString dir = qEnvironmentVariable("WDC_FONT_DIR");
        if (!dir.isEmpty()) {
            for (const char* f : kWdcTextFiles)
                QFontDatabase::addApplicationFont(QDir(dir).absoluteFilePath(QString::fromLatin1(f)));
        }
    }
    state = has() ? 1 : 2;
    return state == 1;
}

TextMetrics TextMetrics::widataDpr18() { return TextMetrics(MetricsProfile::WidataDpr18, 1.8); }
TextMetrics TextMetrics::native(double dpr) { return TextMetrics(MetricsProfile::Native, dpr > 0 ? dpr : 2.0); }
TextMetrics TextMetrics::forProfile(MetricsProfile p, double dpr) {
    return p == MetricsProfile::WidataDpr18 ? widataDpr18() : native(dpr);
}

bool TextMetrics::fontsAvailable() const { return ensureInterFonts(); }

TextMetrics::FontMetric TextMetrics::hc(double px) const {
    const double f = std::floor(px);   // pInt of the computed font-size
    const double h = f < 24 ? f + 3 : hcmath::jsRound(f * 1.2);
    return {h, hcmath::jsRound(h * 0.8)};
}

double TextMetrics::height(double px) const {
    if (profile_ == MetricsProfile::WidataDpr18)
        return (hcmath::jsRound(0.96875 * px * 1.8) + hcmath::jsRound(0.2412 * px * 1.8)) / 1.8;
    double asc = 0.96875, desc = 0.2412;   // Inter hhea 1984/2048, 494/2048
    if (ensureInterFonts()) {
        const QFontMetricsF& fm = wdcText_bigMetrics(px, 400);
        asc = fm.ascent() / kWdcTextBig;
        desc = fm.descent() / kWdcTextBig;
    }
    return (std::round(asc * px * dpr_) + std::round(desc * px * dpr_)) / dpr_;
}

double TextMetrics::exactWidth(const QString& text, double px, int weight) const {
    if (text.isEmpty()) return 0;
    if (!ensureInterFonts()) {   // degraded: generic metrics, still deterministic
        QFont f;
        f.setPixelSize(int(kWdcTextBig));
        return QFontMetricsF(f).horizontalAdvance(text) * px / kWdcTextBig;
    }
    return wdcText_bigMetrics(px, weight).horizontalAdvance(text) * px / kWdcTextBig;
}

double TextMetrics::roundWidth(double exact) const {
    if (profile_ == MetricsProfile::WidataDpr18) return std::round(exact * 1.8 * 64.0) / (1.8 * 64.0);
    return std::ceil(exact * 64.0 - 1e-7) / 64.0;
}

double TextMetrics::width(const QString& text, double px, int weight) const {
    return roundWidth(exactWidth(text, px, weight));
}

QString TextMetrics::cacheKey(const QString& text, double px, int weight, double textWidth, const QString& align,
                              int lineClamp) {
    QString k = text;
    if (!k.contains(QLatin1Char('<'))) {
        for (QChar& c : k)
            if (c.isDigit() && c.unicode() < 128) c = QLatin1Char('0');
    }
    return k + QStringLiteral(",%1,%2,%3,%4,%5")
                   .arg(px)
                   .arg(weight)
                   .arg(textWidth < 0 ? QString() : QString::number(textWidth), align,
                        lineClamp ? QString::number(lineClamp) : QString());
}

QSizeF TextMetrics::bbox(const QString& text, double px, int weight, double textWidth, const QString& align,
                         int lineClamp) {
    const QString key = cacheKey(text, px, weight, textWidth, align, lineClamp);
    const auto it = cache_.constFind(key);
    if (it != cache_.constEnd()) return *it;
    // A label with a CSS width shows TextBuilder's ellipsis text; the cache key keeps the original string.
    const QString shown = textWidth < 0 ? text : ellipsize(text, px, weight, textWidth);
    const QSizeF box = shown.isEmpty() ? QSizeF(0, 0) : QSizeF(width(shown, px, weight), height(px));
    cache_.insert(key, box);
    return box;
}

void TextMetrics::seed(const QString& text, double px, int weight, double w, const QString& align) {
    cache_.insert(cacheKey(text, px, weight, -1, align), QSizeF(w, text.isEmpty() ? 0 : height(px)));
}

std::vector<double> TextMetrics::prefixWidths(const QString& text, double px, int weight) const {
    std::vector<double> out(size_t(text.size()) + 1, 0.0);
    if (text.isEmpty()) return out;
    if (!ensureInterFonts()) {
        for (int i = 1; i <= text.size(); ++i) out[size_t(i)] = exactWidth(text.left(i), px, weight);
        return out;
    }
    QTextLayout layout(text, wdcText_bigFont(px, weight));
    layout.beginLayout();
    QTextLine line = layout.createLine();
    line.setLineWidth(1e9);
    layout.endLayout();
    for (int i = 1; i <= text.size(); ++i) out[size_t(i)] = line.cursorToX(i) * px / kWdcTextBig;
    return out;
}

void TextMetrics::resetCache() { cache_.clear(); }

QString TextMetrics::ellipsize(const QString& text, double px, int weight, double cssWidth) const {
    // TextBuilder: ellipsisWidth = width - 0.8 * lineHeight (fontMetrics h); single word, no wrapping.
    const double width = std::max(0.0, cssWidth - 0.8 * hc(px).h);
    const std::vector<double> prefix = prefixWidths(text, px, weight);
    auto sub = [&](int end) { return prefix[size_t(end)]; };
    if (sub(int(text.size())) <= width) return text;
    int minIndex = 0, maxIndex = int(text.size()), currentIndex = maxIndex;
    while (minIndex <= maxIndex) {
        currentIndex = int(std::ceil((minIndex + maxIndex) / 2.0));
        const double actual = sub(currentIndex);
        if (minIndex == maxIndex) minIndex = maxIndex + 1;
        else if (actual > width) maxIndex = currentIndex - 1;
        else minIndex = currentIndex;
    }
    if (maxIndex == 0) return QString();
    if (maxIndex == int(text.size()) - 1) return text;   // HS keeps the text when only the last char would go
    return text.left(currentIndex) + QChar(0x2026);
}

} // namespace fincept::screens::wdc
