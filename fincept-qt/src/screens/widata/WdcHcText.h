#pragma once
// WdcHcText.h, text measurement for the Highcharts port (package B).
//
// Font: static Inter instance "Inter Static opsz14" at every size (16 px included: WiData's Google Fonts subsets are
// opsz 14, F2_w3 §4), weights 400/500/600 (harness/widata_clone/fonts, decision T00 in fonts/README.md). Exact advance = width shaped at 2048 px
// (= unitsPerEm) scaled to px; Qt's own per-glyph 1/64 px rounding at small sizes is avoided that way.
//
// Profiles (DESIGN §5.2):
//   Native      : width = ceil(exact * 64) / 64 (Blink LayoutUnit, T00: 120/120 identical to Chromium 1224);
//                 bbox height = (round(ascent*f*dpr) + round(descent*f*dpr)) / dpr with the font's hhea metrics.
//   WidataDpr18 : the WiData capture (page zoom 0.9 on a 2x screen). width = round(exact * 115.2) / 115.2,
//                 height H(f) = (round(0.96875 f 1.8) + round(0.2412 f 1.8)) / 1.8. Test profile (tier A).
//
// Cache (HS:10680-10701): key = text with every digit replaced by '0' + font size + weight + textWidth + align;
// first measured string of a pattern wins inside one chart (one TextMetrics per layoutChart call). `align` is
// empty for a label just created (Tick.createLabel measures before renderUnsquish sets the alignment).
#include "WdcModel.h"

#include <QHash>
#include <QSizeF>
#include <QString>

#include <vector>

namespace fincept::screens::wdc {

class TextMetrics {
  public:
    struct FontMetric { double h; double b; };   // SVGRenderer.fontMetrics (HS:14047): h = f<24 ? f+3 : round(1.2f)

    static TextMetrics widataDpr18();
    static TextMetrics native(double dpr = 2.0);
    static TextMetrics forProfile(MetricsProfile p, double dpr = 2.0);   // dpr: Native only (C13)

    FontMetric hc(double px) const;
    double height(double px) const;                                   // bbox height of a one-line label
    double exactWidth(const QString& text, double px, int weight = 400) const;   // unrounded advance sum
    double width(const QString& text, double px, int weight = 400) const;        // profile-rounded, uncached
    // getBBox through the per-chart cache. textWidth < 0: no CSS width set on the label.
    // lineClamp: styles.lineClamp of the label (0 = never set). Part of the HS cache key (HS:10697): a label that
    // handleOverflow / renderUnsquish once clamped keeps it after its width goes back to 'auto'.
    QSizeF bbox(const QString& text, double px, int weight = 400, double textWidth = -1, const QString& align = QString(),
                int lineClamp = 0);
    // SVG getSubStringLength(0, end) for end = 0..size: advances inside the shaped full text (a kern pair that
    // straddles `end` counts on the left glyph, as in Blink).
    std::vector<double> prefixWidths(const QString& text, double px, int weight = 400) const;
    // TextBuilder.truncate with textOverflow ellipsis (HS:12617-12700) for a label of CSS width `cssWidth`.
    QString ellipsize(const QString& text, double px, int weight, double cssWidth) const;
    void resetCache();
    // Test hook (tier A only): pre-seed the cache like an earlier render of the same chart would have.
    void seed(const QString& text, double px, int weight, double width, const QString& align = QString());
    bool fontsAvailable() const;
    MetricsProfile profile() const { return profile_; }

    static QString cacheKey(const QString& text, double px, int weight, double textWidth, const QString& align,
                            int lineClamp = 0);

  private:
    explicit TextMetrics(MetricsProfile p, double dpr) : profile_(p), dpr_(dpr) {}
    double roundWidth(double exact) const;
    MetricsProfile profile_;
    double dpr_;
    QHash<QString, QSizeF> cache_;
};

// Font families used for measurement; ensureInterFonts() loads the static TTFs from $WDC_FONT_DIR when the
// application has not done it yet (package E's WdcFonts is the normal loader). Returns true when available.
bool ensureInterFonts();
QString interStaticFamily(double px);

} // namespace fincept::screens::wdc
