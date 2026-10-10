// src/screens/hdcv_launchpad/HlpFontFallback.cpp
// Launchpad text engine — the fallback font Chrome picks for characters the primary font lacks, where
// Qt's own cascade picks a different font (✕ → Zapf Dingbats, ◤ ═ → .CJK Symbols Fallback, ≫ → Apple
// Symbols…). Chrome resolves them through CTFontCreateForString after the CSS family list; Qt walks
// CTFontCopyDefaultCascadeListForLanguages — same fonts for most characters, not for these.
//
// The table is MEASURED, not guessed (27/09/2026, Chrome 153 / macOS 27): every code point of
// U+2010–205F, 20A0–20CF, 2100–214F, 2190–23FF, 2460–27BF, 2B00–2BFF missing from SF Pro (sans context,
// CSS list -apple-system…sans-serif) or Menlo (mono context, ui-monospace…monospace) was measured in
// Chrome (canvas advance + ink box at 100px) and matched to the candidate font with identical metrics
// (harness/hdcv_launchpad/engine_test/probes: fallback_cps.json → chrome_cps.json, cands.jsonl → match.json;
// see engine_test/REPORT.md). Only code points where Chrome's
// font differs from Qt's cascade are listed; everything else keeps Qt's cascade (verified equal).
#include "screens/hdcv_launchpad/HlpFont_p.h"

#include <QFont>
#include <QGlyphRun>
#include <QTextLayout>

#include <algorithm>

namespace fincept::screens::hlp::detail {

namespace {

struct hlpfb_Range {
    char32_t from, to;
    quint8 font; // FallbackFont
};

// sans context: primary SF Pro (108 ranges)
const hlpfb_Range hlpfb_sans[] = {
    {0x2015, 0x2015, 4}, {0x2017, 0x2017, 4}, {0x201B, 0x201B, 4}, {0x201F, 0x201F, 4},
    {0x2024, 0x2025, 4}, {0x2027, 0x2027, 4}, {0x202A, 0x202E, 2}, {0x2035, 0x2037, 4},
    {0x203B, 0x203C, 4}, {0x203E, 0x203E, 4}, {0x2040, 0x2040, 4}, {0x2045, 0x2051, 4},
    {0x2052, 0x2052, 2}, {0x2055, 0x205E, 4}, {0x20A0, 0x20A0, 4}, {0x20B6, 0x20B6, 6},
    {0x2102, 0x2102, 4}, {0x210D, 0x210D, 4}, {0x2119, 0x211A, 4}, {0x2121, 0x2121, 4},
    {0x2127, 0x2127, 4}, {0x2129, 0x2129, 4}, {0x2132, 0x2132, 4}, {0x213A, 0x213B, 4},
    {0x2141, 0x2143, 4}, {0x214B, 0x214B, 4}, {0x214D, 0x214E, 4}, {0x21B8, 0x21B9, 3},
    {0x21E6, 0x21E6, 3}, {0x21E8, 0x21E9, 3}, {0x2200, 0x2201, 2}, {0x2203, 0x2205, 2},
    {0x2208, 0x220D, 2}, {0x2210, 0x2210, 4}, {0x2213, 0x2213, 2}, {0x2216, 0x2216, 2},
    {0x221C, 0x221D, 2}, {0x221F, 0x2220, 2}, {0x2222, 0x2222, 2}, {0x2225, 0x222A, 2},
    {0x222C, 0x222E, 2}, {0x2234, 0x223B, 2}, {0x223D, 0x223D, 2}, {0x2240, 0x2240, 2},
    {0x2242, 0x2247, 2}, {0x224A, 0x225F, 2}, {0x2263, 0x2263, 2}, {0x2266, 0x226B, 2},
    {0x226D, 0x226D, 2}, {0x2272, 0x228B, 2}, {0x228F, 0x2292, 2}, {0x2298, 0x229B, 2},
    {0x229E, 0x22A5, 2}, {0x22BB, 0x22BC, 2}, {0x22BF, 0x22BF, 2}, {0x22C4, 0x22C4, 2},
    {0x22C6, 0x22C6, 2}, {0x22CD, 0x22CF, 2}, {0x22DA, 0x22E9, 2}, {0x22EE, 0x22EE, 2},
    {0x2312, 0x2312, 3}, {0x23DA, 0x23DB, 3}, {0x2474, 0x24B5, 3}, {0x24D0, 0x24E9, 3},
    {0x24F5, 0x24FE, 3}, {0x2500, 0x2501, 4}, {0x2503, 0x2503, 4}, {0x2504, 0x250B, 3},
    {0x250C, 0x250C, 4}, {0x250D, 0x250E, 3}, {0x250F, 0x2510, 4}, {0x2511, 0x2512, 3},
    {0x2513, 0x2514, 4}, {0x2515, 0x2516, 3}, {0x2517, 0x2518, 4}, {0x2519, 0x251A, 3},
    {0x251B, 0x251B, 4}, {0x251C, 0x254B, 3}, {0x2550, 0x2574, 3}, {0x2581, 0x2587, 3},
    {0x2588, 0x2588, 4}, {0x2589, 0x258F, 3}, {0x2593, 0x2595, 3}, {0x25C6, 0x25C7, 3},
    {0x25CE, 0x25CE, 3}, {0x25E2, 0x25E5, 3}, {0x2609, 0x2609, 3}, {0x2610, 0x2610, 2},
    {0x2639, 0x263B, 4}, {0x2640, 0x2640, 3}, {0x2642, 0x2642, 3}, {0x266A, 0x266A, 4},
    {0x2701, 0x2704, 1}, {0x270E, 0x2712, 1}, {0x2714, 0x2716, 1}, {0x2718, 0x2727, 1},
    {0x2729, 0x274B, 1}, {0x274D, 0x274D, 1}, {0x274F, 0x2752, 1}, {0x2756, 0x2756, 1},
    {0x2758, 0x275A, 1}, {0x2761, 0x2775, 1}, {0x277F, 0x277F, 1}, {0x2789, 0x2789, 1},
    {0x2793, 0x2794, 1}, {0x2798, 0x27A3, 1}, {0x27A5, 0x27AF, 1}, {0x27B1, 0x27BE, 1},
};

// mono context: primary Menlo (18 ranges)
const hlpfb_Range hlpfb_mono[] = {
    {0x202A, 0x202E, 2}, {0x20B6, 0x20B6, 6}, {0x20B8, 0x20BA, 4}, {0x20BE, 0x20BE, 4},
    {0x2104, 0x2104, 4}, {0x214D, 0x214E, 4}, {0x2222, 0x2222, 2}, {0x2225, 0x2226, 2},
    {0x222E, 0x222E, 2}, {0x226A, 0x226B, 2}, {0x22A2, 0x22A5, 2}, {0x22BB, 0x22BC, 2},
    {0x22BF, 0x22BF, 2}, {0x22C4, 0x22C4, 2}, {0x22CE, 0x22CF, 2}, {0x22EE, 0x22EE, 2},
    {0x2776, 0x2793, 1}, {0x2B90, 0x2B91, 5},
};

template <size_t N>
int hlpfb_find(const hlpfb_Range (&tbl)[N], char32_t cp) {
    const hlpfb_Range* e = tbl + N;
    const hlpfb_Range* it = std::upper_bound(tbl, e, cp, [](char32_t v, const hlpfb_Range& r) { return v < r.from; });
    if (it == tbl)
        return FbNone;
    --it;
    return cp <= it->to ? int(it->font) : int(FbNone);
}

QRawFont hlpfb_load(int id) {
    auto byName = [](const char* fam) {
        QFont f(QString::fromLatin1(fam));
        f.setPixelSize(32);
        f.setStyleStrategy(QFont::NoFontMerging);
        QRawFont r = QRawFont::fromFont(f);
        return r.familyName().compare(QLatin1String(fam), Qt::CaseInsensitive) == 0 ? r : QRawFont();
    };
    // a hidden cascade font: take it from Qt's own fallback for a character that lands there
    auto viaCascade = [](const QString& probe) {
        QFont f(QStringLiteral(".AppleSystemUIFont"));
        f.setPixelSize(32);
        QTextLayout l(probe, f);
        l.beginLayout();
        l.createLine();
        l.endLayout();
        const auto runs = l.glyphRuns();
        return runs.isEmpty() ? QRawFont() : runs.first().rawFont();
    };
    switch (id) {
    case FbZapfDingbats: return byName("Zapf Dingbats");
    case FbAppleSymbols: return byName("Apple Symbols");
    case FbCjkSymbols: return QRawFont(QStringLiteral("/System/Library/Fonts/CJKSymbolsFallback.ttc"), 32);
    case FbJapanese: return viaCascade(QString(QChar(0x25D0))); // ◐ → .AppleJapaneseFont
    case FbHelveticaNeue: return byName("Helvetica Neue");
    case FbGeneva: return byName("Geneva");
    default: return QRawFont();
    }
}

} // namespace

int chromeFallbackFont(char32_t cp, bool mono) {
    return mono ? hlpfb_find(hlpfb_mono, cp) : hlpfb_find(hlpfb_sans, cp);
}

float fallbackScale(int id, float px) {
    // .CJK Symbols Fallback comes out of the SF cascade 3.48% larger at text sizes (SF Text, < 20px)
    // and at its nominal size from 20px on (SF Display); Chrome interpolates between 19 and 20px.
    // Measured on ◤ ═ at 8–24px: advance/ink ratios 1.0348 (≤ 19px), 1.0174 (19.5px), 1.000 (≥ 20px).
    if (id != FbCjkSymbols)
        return 1.0f;
    constexpr float kText = 1.0348f;
    if (px <= 19.0f)
        return kText;
    if (px >= 20.0f)
        return 1.0f;
    return kText + (1.0f - kText) * (px - 19.0f);
}

float hmtxAdvance(const QRawFont& f, quint32 glyph) {
    if (!f.isValid())
        return -1.0f;
    const QByteArray head = f.fontTable("head"), hhea = f.fontTable("hhea"), hmtx = f.fontTable("hmtx");
    if (head.size() < 20 || hhea.size() < 36 || !f.fontTable("trak").isEmpty())
        return -1.0f;
    const auto u16 = [](const QByteArray& t, int o) { return int((uchar(t[o]) << 8) | uchar(t[o + 1])); };
    const int upem = u16(head, 18), nLong = u16(hhea, 34);
    const int g = std::min(int(glyph), nLong - 1);
    if (upem <= 0 || nLong <= 0 || 4 * g + 2 > hmtx.size())
        return -1.0f;
    return float(double(u16(hmtx, 4 * g)) * f.pixelSize() / double(upem));
}

const QRawFont& fallbackRawFont(int id) {
    static QRawFont fonts[FbCount];
    static bool loaded[FbCount] = {};
    if (id <= FbNone || id >= FbCount) {
        static const QRawFont none;
        return none;
    }
    if (!loaded[id]) {
        fonts[id] = hlpfb_load(id);
        loaded[id] = true;
    }
    return fonts[id];
}

} // namespace fincept::screens::hlp::detail
