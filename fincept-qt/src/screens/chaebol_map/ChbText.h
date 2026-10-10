#pragma once
// ChbText.h — text measurement/painting for the chaebol_map engine.
//
// Precision: Qt stores glyph advances as 26.6 fixed point (1/64 px) — IBM Plex Mono 12 px '0' comes out
// 7.1875 instead of Chrome's 7.2, which drifts ≥1 px per 100 characters and flips line breaks. We therefore
// shape at kShapeScale× the size and divide (error < 1/8000 px per glyph: Chrome snaps every text item's width
// UP to 1/64 px, so a 1/2000 px drift over ten glyphs already flipped widths across a LayoutUnit), except bitmap
// (emoji) glyphs whose advance is size-dependent (Chrome's whole-pixel emoji advance, ChbText.cpp). Kerning deltas
// of variable fonts, which Qt's shaper drops, are added back (ChbKernVar_p.h). Letter-spacing is added per
// grapheme cluster (Chrome: after every typographic character unit, trailing one included, but not after BMP
// default-ignorables such as U+200B or after U+FFFC), ligatures are
// disabled when it is non-zero (like Blink). Runs are split so that characters outside the Google subsets
// of the web fonts skip those families (ChbFonts::web_family_covers).
// Vertical metrics follow Blink/macOS: round(ascent), round(descent), round(lineGap), +15 % ascent hack for
// Times/Helvetica/Courier.
#include "screens/chaebol_map/ChbFonts.h"

#include <QColor>
#include <QFont>
#include <QPainter>
#include <QPointF>
#include <QRawFont>
#include <QString>

#include <memory>
#include <vector>

namespace fincept::screens::chb {

constexpr float kShapeScale = 128.0f;

/// Chrome-rounded font metrics (integers, px).
struct LineMetrics {
    float asc = 0, desc = 0, gap = 0;
    float height() const { return asc + desc; }
    float normalLineHeight() const { return asc + desc + gap; }
};
LineMetrics chrome_line_metrics(const QRawFont& rf);

/// One (family list, size, weight, style) combination.
struct FontEntry {
    FontSpec spec;
    float px = 16;
    QFont font;          ///< real size
    QRawFont raw;        ///< primary face, real size
    LineMetrics m;       ///< primary face, Chrome-rounded
    float ascRaw = 0, descRaw = 0;
    float xHeight = 0;
    float underlinePos = 0, underlineThickness = 1, strikePos = 0;
};
const FontEntry& font_entry(const QStringList& cssFamilies, float px, int weight, bool italic);

/// Shaped text (one string, one font, one letter-spacing). Positions are relative to the text start.
class ShapedText {
  public:
    struct Glyph {
        quint32 id = 0;
        float x = 0, y = 0; ///< y relative to the baseline
        int str = 0;        ///< string index of the glyph's cluster
        int run = 0;        ///< index into runs
    };
    struct Run {
        QRawFont raw;       ///< real-size face actually used
        LineMetrics lm;
        bool bitmap = false;
        bool primary = false;
    };

    QString text;
    const FontEntry* font = nullptr;
    float letterSpacing = 0;
    float width = 0;
    std::vector<float> caret; ///< size text.size()+1; exact at grapheme boundaries
    std::vector<Glyph> glyphs;
    std::vector<Run> runs;
    std::vector<unsigned char> graphemeStart; ///< 1 where a grapheme cluster starts
    bool multiFont = false;

    float x(int pos) const { return caret.empty() ? 0.0f : caret[size_t(std::clamp(pos, 0, int(caret.size()) - 1))]; }
    float width_of(int from, int to) const { return x(to) - x(from); }
    /// Union of fallback metrics used by characters [from, to) (only meaningful when multiFont).
    void metrics_in_range(int from, int to, float* maxAscWithHalfGap, float* maxDescWithHalfGap) const;
    /// Draw glyphs of [from, to) with the painter's current pen colour; `origin` = position of char `from`
    /// on the baseline.
    void paint(QPainter& p, QPointF origin, int from, int to, const QColor& color) const;
};

const ShapedText& shape_text(const FontEntry& fe, const QString& text, float letterSpacing);
/// Drop measurement caches (call when memory matters; entries are otherwise kept for the process).
void clear_text_caches();
/// Number of cached shaped strings (diagnostics).
int text_cache_size();

} // namespace fincept::screens::chb
