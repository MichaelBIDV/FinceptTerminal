// src/screens/hdcv_launchpad/HlpFont_p.h
// PRIVATE to the Launchpad text engine (HlpFontTables.cpp / HlpFontShape.cpp): the OpenType tables
// Chrome's HarfBuzz reads on macOS (hmtx/HVAR/avar/fvar, GPOS kern + GDEF deltas, AAT trak) as plain
// structs. Nothing here is used by panel code.
#pragma once

#include "screens/hdcv_launchpad/HlpDomLayout_p.h"

#include <QByteArray>
#include <QColor>
#include <QFont>
#include <QHash>
#include <QRawFont>
#include <QRectF>
#include <QVector>

class QGlyphRun;
class QPainter;

namespace fincept::screens::hlp::detail {

// ---- big-endian table reader -------------------------------------------------------------
struct Tbl {
    QByteArray bytes;
    const uchar* d = nullptr;
    int n = 0;
    void set(const QByteArray& b) {
        bytes = b;
        d = reinterpret_cast<const uchar*>(bytes.constData());
        n = int(bytes.size());
    }
    bool ok(int o, int len) const { return o >= 0 && len >= 0 && o + len <= n; }
    quint16 u16(int o) const { return ok(o, 2) ? quint16((d[o] << 8) | d[o + 1]) : 0; }
    qint16 s16(int o) const { return qint16(u16(o)); }
    quint32 u32(int o) const {
        return ok(o, 4) ? (quint32(d[o]) << 24) | (quint32(d[o + 1]) << 16) | (quint32(d[o + 2]) << 8) | d[o + 3] : 0;
    }
    qint32 s32(int o) const { return qint32(u32(o)); }
    qint8 s8(int o) const { return ok(o, 1) ? qint8(d[o]) : 0; }
    float fixed(int o) const { return float(s32(o)) / 65536.0f; }
};

/// ItemVariationStore evaluator (OpenType 1.8; HarfBuzz region-scalar semantics).
struct VarStore {
    const Tbl* t = nullptr;
    int base = -1;
    bool valid() const { return t && base >= 0; }

    float regionScalar(int regionList, int axisCount, int region, const QVector<int>& coords) const;

    float delta(int outer, int inner, const QVector<int>& coords) const;
};

/// One font face (file) with the tables the engine needs.
struct Face {
    QRawFont raw;                // reference instance (glyph ids, fallback checks)
    Tbl hmtx, hhea, hvar, gpos, gdef, trak, fvar, avar;
    int upem = 2048;
    int numH = 0;
    float asc = 0, desc = 0, gap = 0;             // design units
    struct Axis {
        quint32 tag;
        float mn, def, mx;
    };
    QVector<Axis> axes;
    QVector<QVector<QPair<int, int>>> avarMaps;  // per axis (F2DOT14 from→to)
    VarStore hvarStore, gdefStore;
    int hvarMap = 0;                              // advance width mapping offset (0 = implicit)
    QVector<int> kernSubtables;                   // PairPos subtable offsets, grouped by lookup
    QVector<int> kernLookupStart;                 // start index into kernSubtables per lookup
    QVector<quint16> kernLookupFlag;
    int glyphClassDef = 0;
    QHash<quint32, quint32> cmap;

    quint32 glyph(quint32 cp);

    bool isMark(quint32 g) const;

    Tbl glyf, loca;
    int locaFormat = -1; ///< -1 = glyf/loca not read yet, -2 = the face has no glyf outlines
    /// Bounds of glyph g in design units, y up (glyf header: every point, off-curve included — what
    /// SkPath::getBounds of the CoreText outline gives Blink on macOS). False: no glyf table.
    bool glyphBounds(quint32 g, QRectF& out);
};

/// Read the tables of the face behind `qf` (glyph ids through QRawFont).
void initFace(Face& f, const QFont& qf);
/// Same for a face already loaded (fallback fonts that have no public family name).
void initFace(Face& f, const QRawFont& raw);

/// Fallback fonts Chrome uses where Qt's cascade differs (HlpFontFallback.cpp).
enum FallbackFont : int {
    FbNone = 0,
    FbZapfDingbats = 1,
    FbAppleSymbols = 2,
    FbCjkSymbols = 3,    ///< .CJK Symbols Fallback (CJKSymbolsFallback.ttc) — has a `trak` table
    FbJapanese = 4,      ///< .AppleJapaneseFont (Hiragino in the system cascade)
    FbHelveticaNeue = 5,
    FbGeneva = 6,
    FbCount = 7
};
/// Chrome's fallback font for `cp` when the primary font (SF Pro, or Menlo when `mono`) lacks it and
/// Chrome's choice differs from Qt's cascade; FbNone = Qt's cascade is what Chrome uses.
int chromeFallbackFont(char32_t cp, bool mono);
/// The face for a FallbackFont at 32px (invalid QRawFont if the font is not installed).
const QRawFont& fallbackRawFont(int id);
/// Size factor the system cascade applies to a FallbackFont at CSS size px (glyphs and advances).
float fallbackScale(int id, float px);
/// Advance of `glyph` straight from the face's hmtx, unrounded, at f.pixelSize() (CoreText hands Chrome
/// the design advance; QFontMetricsF rounds to 26.6 fixed point: ↳ of .AppleKoreanFont, 865/1000, at
/// 10px → 8.640625, not 8.65 — enough to move later glyphs of the XANH VỎ line across a quarter-pixel
/// phase). -1 when the face has a 'trak' table or no usable hmtx.
float hmtxAdvance(const QRawFont& f, quint32 glyph);

/// Paint monochrome glyph runs the way Chrome blits text on macOS (HlpFontBlit.cpp): CoreGraphics
/// coverage linearised, then Skia's pre-blend table for `color`. `box` = generous logical bounds of
/// the runs. Returns false when the painter cannot take the detour (non-affine device
/// transform); the caller then draws the runs itself.
bool blitGlyphRuns(QPainter& p, const QVector<QGlyphRun>& runs, const QColor& color, const QRectF& box);
/// Paint colour (emoji) glyph runs the way Chrome does: CoreGraphics draws each glyph at its (whole
/// pixel) device position into an sRGB RGBA layer. Returns false when CoreText cannot take the runs;
/// the caller then draws them with Qt.
bool blitColourGlyphRuns(QPainter& p, const QVector<QGlyphRun>& runs);

/// Face instance at one (opsz, wght): normalised coordinates + caches.
struct Inst {
    Face* face = nullptr;
    QVector<int> coords; // F2DOT14 after avar
    QHash<quint32, float> adv;
    QHash<quint64, float> kern; // (a<<32|b) → design-unit adjustment of a's advance (NaN = no pair)

    float advance(quint32 g);

    /// XAdvance (+ VariationIndex delta) of a ValueRecord; `base` = table its device offsets are relative to.
    float valueXAdvance(const Tbl& t, int base, int rec, int vf) const;

    /// Kerning of pair (a,b) in lookup `li`; NaN when no subtable matched.
    float pairInLookup(int li, quint32 a, quint32 b) const;

    /// Sum of kern adjustments for pair (a,b) over all kern lookups (design units).
    float pair(quint32 a, quint32 b);
};

} // namespace fincept::screens::hlp::detail
