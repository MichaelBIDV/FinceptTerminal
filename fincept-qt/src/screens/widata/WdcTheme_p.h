#pragma once
// WdcTheme_p.h: design tokens of the WiData clone (tab VĨ MÔ), package D.
//
// Sources (widata_clone_spec): colours UI §5.1 (computed style of the capture), card/legend sizes UI §3,
// baseline rule UI §5.3, self-defined interaction tokens DESIGN §6.1 (hover, active, focus, popover, title
// tooltip, legend reset, scrollbar), missing-data tokens DESIGN §8.4. Every size is a Qt logical px, equal to
// one CSS px of WiData (DESIGN X10). Header only; every Wdc* file may include it (QtGui only).
#include <QColor>
#include <QFont>
#include <QFontDatabase>
#include <QFontMetricsF>
#include <QMutex>
#include <QMutexLocker>
#include <QString>
#include <QStringList>
#include <QTextBoundaryFinder>

#include <algorithm>
#include <cmath>
#include <vector>

namespace fincept::screens::wdc::theme {

// ---- colours, UI §5.1 -------------------------------------------------------------------------------------
inline constexpr QRgb kTextPrimary = 0xFF21232E;    // titles, legend text, selected tab, "Bố cục:"
inline constexpr QRgb kTextSecondary = 0xFF58667E;  // idle tab, header icons, "Thêm", crosshair
inline constexpr QRgb kIconMuted = 0xFFA6B0C3;      // legend info icon, resize marks
inline constexpr QRgb kBorder = 0xFFDEDEDE;         // card, tab, ">" and "Thêm biểu đồ" borders
inline constexpr QRgb kBgPage = 0xFFF8FAFD;         // body behind the panel
inline constexpr QRgb kBgSurface = 0xFFFFFFFF;      // panel, card, idle tab, expanded box
inline constexpr QRgb kBgSubtle = 0xFFF6F5F4;       // card button cluster, calendar box, action cluster
inline constexpr QRgb kBgTabActive = 0xFFF0F0F0;    // selected tab
inline constexpr QRgb kBgGreyBtn = 0xFFF9F9F9;
inline constexpr QRgb kIconGreyBtn = 0xFF5B5B5D;
inline constexpr QRgb kAccent = 0xFF3961F8;
inline constexpr QRgb kAccentReset = 0xFF6585FF;    // legend reset button
inline constexpr QRgb kOverlay = qRgba(0, 0, 0, 191); // rgba(0,0,0,.75), expanded backdrop
inline constexpr QRgb kCrosshair = 0xFF58667E;
inline constexpr QRgb kCrosshairLabel = 0xFF323546;
inline constexpr QRgb kScrollThumb = 0xFFC6CBD3;    // measured on images (UI §1.3), CHƯA XÁC MINH as CSS
inline constexpr QRgb kWhite = 0xFFFFFFFF;

// ---- interaction tokens, DESIGN §6.1 (ĐỀ XUẤT, Q20) --------------------------------------------------------
inline constexpr QRgb kHoverBg = kBgTabActive;      // hover of tab, card icon button, range button, legend item
inline constexpr QRgb kActiveBg = kBorder;          // pressed
inline constexpr QRgb kFocusRing = kTextSecondary;  // 1 px ring, radius 4
inline constexpr QRgb kPopoverBg = kBgSurface;
inline constexpr QRgb kPopoverBorder = kBorder;
inline constexpr QRgb kPopoverText = kTextPrimary;
inline constexpr QRgb kTitleTipBg = kCrosshairLabel;
inline constexpr QRgb kTitleTipFg = kWhite;
inline constexpr QRgb kMissingText = kIconMuted;    // DESIGN §8.4: legend text of a missing series
inline constexpr QRgb kNeedDataText = kTextSecondary; // "[CẦN DATA]" in an empty pane

inline QColor color(QRgb c) { return QColor::fromRgba(c); }

// ---- card, UI §3.1 to §3.3 ---------------------------------------------------------------------------------
inline constexpr qreal kCardPadding = 12;
inline constexpr qreal kCardRadius = 4;
inline constexpr qreal kHeaderH = 30;
inline constexpr qreal kTitleTop = 6;          // h2 sits 6 below the header top (30 - 18) / 2
inline constexpr qreal kTitleLineH = 18;
inline constexpr qreal kTitlePx = 12;
inline constexpr int kTitleWeight = 600;
inline constexpr qreal kClusterMarginLeft = 8; // between title and button cluster
inline constexpr qreal kClusterPad = 2;
inline constexpr qreal kClusterRadius = 4;
inline constexpr qreal kButtonSize = 26;
inline constexpr qreal kButtonRadius = 4;
inline constexpr qreal kIconSize = 16;         // icon inside a 26 button, inset 5
inline constexpr qreal kIconInset = 5;
inline constexpr qreal kSyncIconSize = 20;     // "Cached" icon of [macro] cards, inset 3
inline constexpr qreal kSyncIconInset = 3;
inline constexpr qreal kBodyPadTop = 12;       // body padding-top under the header
inline constexpr qreal kBodyReserve = 60;      // JS sets body height = card height - 60 (UI §3.3)
inline constexpr qreal kChartToLegend = 12;
inline constexpr qreal kLegendH = 36;
inline constexpr qreal kDividerTop = 12;       // pane divider margin 12 0 8
inline constexpr qreal kDividerBottom = 8;
inline constexpr qreal kNeedDataPx = 12;       // DESIGN §8.4
inline constexpr int kNeedDataWeight = 500;

// title tooltip (DESIGN §6.1)
inline constexpr qreal kTitleTipPx = 11;
inline constexpr qreal kTitleTipPad = 6;
inline constexpr qreal kTitleTipRadius = 4;
inline constexpr qreal kTitleTipGap = 4;       // below the title
inline constexpr int kTitleTipDelayMs = 500;

// popover (DESIGN §6.1)
inline constexpr qreal kPopoverPad = 8;
inline constexpr qreal kPopoverRadius = 4;
inline constexpr qreal kPopoverPx = 13;
inline constexpr qreal kPopoverLineH = 20.43;  // Inter 13 px normal line height used across WiData (UI §1.2)
inline constexpr qreal kPopoverMaxTextW = 320; // wrap width of the info popover (MẶC ĐỊNH)
inline constexpr qreal kMenuRowH = 30;         // gear menu row (MẶC ĐỊNH, same as header row)
inline constexpr qreal kMenuRowPadX = 8;

// ---- legend, UI §3.4, §3.5, §4.5 ---------------------------------------------------------------------------
inline constexpr qreal kLegendRowH = 18;
inline constexpr qreal kLegendPx = 12;
inline constexpr qreal kLegendPadAio = 8;
inline constexpr qreal kLegendPadExpanded = 40;
inline constexpr qreal kMacroItemFrac = 0.47;  // LegendCustom: item = W/cols - 3 % W, margin 1.5 % W
inline constexpr qreal kMacroMarginFrac = 0.015;
inline constexpr qreal kSingleExtraW = 5;      // chart-page legend: inner stack is 5 px wider than its box
inline constexpr qreal kSwatchW = 15;
inline constexpr qreal kSwatchOverhang = 1.5;  // content = itemW + 3, centred
inline constexpr qreal kTextBlockInset = 21.5; // swatch 15 + margin 8 - overhang 1.5
inline constexpr qreal kTextBlockReserve = 20; // text block = itemW - 20
inline constexpr qreal kTextReserve = 40;      // text max = itemW - 40
inline constexpr qreal kInfoBoxW = 20;
inline constexpr qreal kInfoBoxH = 16;
inline constexpr qreal kInfoIcon = 16;
inline constexpr qreal kInfoDy = 1;
inline constexpr qreal kScrollbarCss = 4;      // ::-webkit-scrollbar width, snapped to device px
inline constexpr qreal kScrollbarRadius = 2;
inline constexpr qreal kOffOpacity = 0.4;      // legend item toggled off (BEH §5.2)
inline constexpr qreal kMissingSwatchOpacity = 0.35;
inline constexpr qreal kAreaLowerOpacity = 0.5;
inline constexpr qreal kResetPad = 2;          // reset-legend-arrow; expanded "reset-legend-zoom" uses 4
inline constexpr qreal kResetPadExpanded = 4;
inline constexpr qreal kResetIcon = 18;
inline constexpr qreal kResetRadius = 4;
inline constexpr qreal kResetDy = -8;          // margin-top -8 (MẶC ĐỊNH position: top right of the legend)
inline constexpr qreal kResetRight = 4;        // HOVER_CSS.md: .reset-legend-arrow / -scroll {right: -4px}
inline constexpr qreal kResetScrollBottom = 18; // HOVER_CSS.md: .reset-legend-scroll {bottom: 18px} (macro legend)
inline constexpr qreal kLegendHoverPadR = 8;    // HOVER_CSS.md: hovered item name {padding-right: 0.5rem}

// swatch geometry relative to (item.x - 1.5, row.y), FACT DOM
inline constexpr qreal kLineY = 8, kLineH = 2;
inline constexpr qreal kBoxY = 4, kBoxH = 10;
inline constexpr qreal kAreaBarH = 3, kAreaBlockInset = 1.5, kAreaBlockW = 12, kAreaBlockH = 7;
inline constexpr qreal kDashShort = 15 * 0.2125, kDashGap = 15 * 0.075, kDashLong = 15 * 0.425; // 3.19, 1.12, 6.38
inline constexpr qreal kDotSize = 5, kDotDx = 5, kDotDy = -1.5;
inline constexpr qreal kSwatchRadius = 2;

// ---- border width: DESIGN §16 C16 (stylesheet .css-wphbxv "border: 1px solid", Chromium rounds DOWN to whole
// device pixels): device width = max(1, floor(css x dpr)). 1 CSS px is 1 device px at DPR 1.8 (capture) and 2 device
// px (= 1 CSS px) at DPR 2.
inline qreal borderPx(qreal css, qreal dpr) {
    if (dpr <= 0) return css;
    return std::max<qreal>(1, std::floor(css * dpr + 1e-6)) / dpr;
}
inline qreal hairline(qreal dpr) { return borderPx(1, dpr); }
// Scrollbar thickness as Chromium snaps it (4 CSS px at DPR 1.8 gives 7 device px = 3.889).
inline qreal scrollbarWidth(qreal dpr) { return dpr > 0 ? std::floor(kScrollbarCss * dpr + 0.5) / dpr : kScrollbarCss; }

// ---- typography, UI §5.2, §5.3 -----------------------------------------------------------------------------
// Inter 4.001 metrics: unitsPerEm 2048, hhea ascender 1984, descender -494, lineGap 0. Blink rounds ascent and
// descent to whole device pixels, then centres the content box in the line (half-leading).
inline qreal blinkAscent(qreal px, qreal dpr) { return std::round(1984.0 / 2048.0 * px * dpr) / dpr; }
inline qreal blinkDescent(qreal px, qreal dpr) { return std::round(494.0 / 2048.0 * px * dpr) / dpr; }
inline qreal blinkNormalLineH(qreal px, qreal dpr) { return blinkAscent(px, dpr) + blinkDescent(px, dpr); }
inline qreal blinkBaseline(qreal px, qreal lineH, qreal dpr) {
    const qreal a = blinkAscent(px, dpr), d = blinkDescent(px, dpr);
    return (lineH - (a + d)) / 2 + a;
}

// Family preference: the static instances of P0 (exact Chromium advances at every weight, H/fonts/README.md),
// then the variable font with wght/opsz axes. Families are registered by WdcFonts (package E) or by a harness, often
// from a worker thread; the lookup is repeated (under a mutex) until the static instances are found, then cached.
// Without any Inter the default application font is used: asking for a missing family name makes Qt populate its
// alias table (80 to 140 ms on the UI thread, measured 04/10), so no unregistered name is ever requested.
struct FontFamilies { QString static14, static16, variable; };
inline FontFamilies fontFamilies() {
    static QMutex mutex;
    static FontFamilies cached;
    static bool complete = false;
    QMutexLocker lock(&mutex);
    if (!complete) {
        auto have = [](QString& slot, const char* fam) {
            if (slot.isEmpty() && QFontDatabase::hasFamily(QString::fromLatin1(fam))) slot = QString::fromLatin1(fam);
        };
        have(cached.static14, "Inter Static opsz14");
        have(cached.static16, "Inter Static opsz16");
        have(cached.variable, "Inter Variable");
        complete = !cached.static14.isEmpty() && !cached.static16.isEmpty() && !cached.variable.isEmpty();
    }
    return cached;
}

inline QFont font(qreal px, int weight) {
    const FontFamilies fams = fontFamilies();
    QFont f;
    // Chromium opsz = px clamped to [14, 32]; only 16 px is used above 14. But WiData serves Inter 400 and 500 as
    // Google Fonts static subsets, which are opsz 14 instances: at 16 px those weights keep the opsz 14 outlines
    // (FACT of package F2, 04/10: chart-page h6 230.41 wide = opsz 14 at 16 px, opsz 16 gives 228.53). Weight 600
    // only matches the variable face, whose opsz follows the size.
    const bool web = weight == 400 || weight == 500;
    const bool big = px >= 15.5 && !web;
    const QString& st = big ? fams.static16 : fams.static14;
    if (!st.isEmpty()) {
        QStringList list{st};
        if (!fams.variable.isEmpty()) list << fams.variable;
        f.setFamilies(list);
        f.setWeight(QFont::Weight(weight)); // Regular / Medium / SemiBold files of the same family
    } else if (!fams.variable.isEmpty()) {
        // weight goes through the wght axis only: QFont::setWeight on the single variable face would let Qt
        // synthesise bold on top of it
        f.setFamilies({fams.variable});
        f.setVariableAxis(QFont::Tag("wght"), float(weight));
        f.setVariableAxis(QFont::Tag("opsz"), web ? 14.0f : float(std::clamp<qreal>(px, 14, 32)));
    } else {
        f.setWeight(QFont::Weight(weight)); // Inter not registered: application font, widths will drift (Q7)
    }
    f.setPixelSize(int(std::lround(px)));
    f.setKerning(true);
    f.setHintingPreference(QFont::PreferNoHinting);
    return f;
}

// WiData serves Inter 400 and 500 as Google Fonts unicode-range subsets (CAP meta.fonts: one variable face
// "1 999" for every code point, declared first, then static 400/500 faces "vietnamese", "latin-ext", "latin";
// the strings in the capture are cut at 60 chars, the full ranges below are the standard Google Fonts ones whose
// prefixes match). Chromium gives each character to the LAST declared face covering it, so latin letters and
// precomposed Vietnamese letters come from different files and are shaped as separate runs: no kerning across
// the boundary ("Tỷ", "Tổ", "Vố", "Tấ" are 0.6 to 1 px wider than the font's own kerning; FACT, 19/492 legend
// texts of CAP). Weight 600 matches only the variable face, so it keeps every kerning pair.
inline int webSubset(char32_t u) {
    auto in = [u](char32_t a, char32_t b) { return u >= a && u <= b; };
    if (u <= 0xFF || u == 0x131 || in(0x152, 0x153) || in(0x2BB, 0x2BC) || u == 0x2C6 || u == 0x2DA || u == 0x2DC ||
        u == 0x304 || u == 0x308 || u == 0x329 || in(0x2000, 0x206F) || u == 0x20AC || u == 0x2122 || u == 0x2191 ||
        u == 0x2193 || u == 0x2212 || u == 0x2215 || u == 0xFEFF || u == 0xFFFD)
        return 0; // latin
    if (in(0x100, 0x2BA) || in(0x2BD, 0x2C5) || in(0x2C7, 0x2CC) || in(0x2CE, 0x2D7) || in(0x2DD, 0x2FF) ||
        in(0x1D00, 0x1DBF) || in(0x1E00, 0x1E9F) || in(0x1EF2, 0x1EFF) || u == 0x2020 || in(0x20A0, 0x20AB) ||
        in(0x20AD, 0x20C0) || u == 0x2113 || in(0x2C60, 0x2C7F) || in(0xA720, 0xA7FF))
        return 1; // latin-ext
    if (in(0x300, 0x301) || in(0x303, 0x304) || in(0x308, 0x309) || u == 0x323 || in(0x1EA0, 0x1EF9) || u == 0x20AB)
        return 2; // vietnamese
    return 3;     // variable face
}

/// Width of `s` as Chromium lays it out on WiData: one shaping run per font subset for weights 400/500.
inline qreal textWidth(const QFontMetricsF& fm, const QString& s, int weight) {
    if (weight != 400 && weight != 500) return fm.horizontalAdvance(s);
    qreal w = 0;
    int start = 0, cur = -1;
    for (int i = 0; i < s.size();) {
        const char32_t u = s.at(i).isHighSurrogate() && i + 1 < s.size() ? QChar::surrogateToUcs4(s.at(i), s.at(i + 1))
                                                                         : char32_t(s.at(i).unicode());
        const int n = u > 0xFFFF ? 2 : 1;
        const int k = webSubset(u);
        if (cur >= 0 && k != cur) {
            w += fm.horizontalAdvance(s.mid(start, i - start));
            start = i;
        }
        cur = k;
        i += n;
    }
    return w + fm.horizontalAdvance(s.mid(start));
}

/// Draws `s` with the same run split as textWidth(), so glyph positions match Chromium's (baseline at `at`).
template <typename Painter>
inline void drawWebText(Painter& p, const QPointF& at, const QString& s, int weight) {
    if (weight != 400 && weight != 500) { p.drawText(at, s); return; }
    const QFontMetricsF fm(p.font());
    qreal x = at.x();
    int start = 0, cur = -1;
    auto flush = [&](int end) {
        const QString run = s.mid(start, end - start);
        p.drawText(QPointF(x, at.y()), run);
        x += fm.horizontalAdvance(run);
        start = end;
    };
    for (int i = 0; i < s.size();) {
        const char32_t u = s.at(i).isHighSurrogate() && i + 1 < s.size() ? QChar::surrogateToUcs4(s.at(i), s.at(i + 1))
                                                                         : char32_t(s.at(i).unicode());
        const int k = webSubset(u);
        if (cur >= 0 && k != cur) flush(i);
        cur = k;
        i += u > 0xFFFF ? 2 : 1;
    }
    flush(int(s.size()));
}

/// Advance of the first `n` UTF-16 units of `s` inside the shaping of the WHOLE text (same run split as textWidth), so
/// a kerning pair across the cut counts as in Blink's ShapeResult (QFontMetricsF::horizontalAdvance(text, length)
/// shapes the full string and measures its first `length` characters).
inline qreal textPrefixWidth(const QFontMetricsF& fm, const QString& s, int n, int weight) {
    if (n <= 0) return 0;
    if (weight != 400 && weight != 500) return fm.horizontalAdvance(s, n);
    qreal w = 0;
    int start = 0, cur = -1;
    for (int i = 0; i < s.size();) {
        const char32_t u = s.at(i).isHighSurrogate() && i + 1 < s.size() ? QChar::surrogateToUcs4(s.at(i), s.at(i + 1))
                                                                         : char32_t(s.at(i).unicode());
        const int k = webSubset(u);
        if (cur >= 0 && k != cur) {
            const QString run = s.mid(start, i - start);
            if (n <= i) return w + fm.horizontalAdvance(run, n - start);
            w += fm.horizontalAdvance(run);
            start = i;
        }
        cur = k;
        i += u > 0xFFFF ? 2 : 1;
    }
    return w + fm.horizontalAdvance(s.mid(start), n - start);
}

// Text-overflow ellipsis as Blink does it (LineTruncator: ShapeResult::OffsetToFit): the longest prefix, cut on a
// grapheme boundary, whose advance in the shaping of the whole text fits in maxW minus the width of "…"; a trailing
// space stays when it fits ("Tỷ giá Việt Nam" -> "Tỷ giá Việt …", UI §1.2). Measured against Chromium 1224 on 1 944
// legend cases (qt/tests/D/d_blink_elide.py, VERIFY_W3 V3): the prefix advance is the deciding quantity, so the
// former test "width of prefix + '…' shaped together" kept one character too many in ~4 % of the widths.
// elideCut is the cut alone (the caller knows the text overflows): prefix + "…", or "…" / "" when no prefix fits;
// ellW is the width of "…" in fm units. elideKeepSpace returns the text unchanged when it fits; exactElide (below)
// does the same with Chromium's exact widths.
inline QString elideCut(const QString& s, const QFontMetricsF& fm, qreal maxW, qreal ellW, int weight) {
    const QString ell = QString(QChar(0x2026));
    const qreal avail = maxW - ellW;
    std::vector<int> bounds;
    QTextBoundaryFinder bf(QTextBoundaryFinder::Grapheme, s);
    for (qsizetype pos = bf.toNextBoundary(); pos > 0; pos = bf.toNextBoundary()) bounds.push_back(int(pos));
    // prefix advances grow with the prefix (advance + kerning of a glyph is positive): binary search
    int lo = -1, hi = int(bounds.size());   // fits(lo) or lo == -1; !fits(hi) or hi == n
    while (hi - lo > 1) {
        const int mid = (lo + hi) / 2;
        (textPrefixWidth(fm, s, bounds[size_t(mid)], weight) <= avail + 1e-6 ? lo : hi) = mid;
    }
    if (lo >= 0) return s.left(bounds[size_t(lo)]) + ell;
    return ellW <= maxW + 1e-6 ? ell : QString();
}

inline QString elideKeepSpace(const QString& s, const QFontMetricsF& fm, qreal maxW, bool* elided = nullptr,
                              int weight = 400) {
    if (elided) *elided = false;
    if (textWidth(fm, s, weight) <= maxW + 1e-6) return s;
    if (elided) *elided = true;
    return elideCut(s, fm, maxW, textWidth(fm, QString(QChar(0x2026)), weight), weight);
}

// Exact widths (fonts/README.md, decision T00): Qt rounds every glyph advance to 1/64 px at the real size (up to
// 0.34 px off Chromium on a legend name); shaped at unitsPerEm (2048) and scaled, Inter matches Chromium, and Blink
// keeps inline sizes in LayoutUnit (1/64 px, rounded up).
inline constexpr qreal kExactPx = 2048;
inline qreal ceil64(qreal v) { return std::ceil(v * 64 - 1e-6) / 64; }
inline QFont exactFont(qreal px, int weight) {
    QFont f = font(px, weight);
    f.setPixelSize(int(kExactPx));
    return f;
}
inline qreal exactTextWidth(const QFontMetricsF& exactFm, const QString& s, qreal px, int weight) {
    return ceil64(textWidth(exactFm, s, weight) * px / kExactPx);
}
inline QString exactElide(const QFontMetricsF& exactFm, const QString& s, qreal px, qreal maxW, bool* elided = nullptr,
                          int weight = 400) {
    // the full width is compared as Blink's LayoutUnit inline size, the ellipsis as its SnappedWidth (both 1/64 up):
    // 1 944 of 1 944 Chromium cases, 1 943 with the unrounded "…" (d_blink_elide.py, 04/10)
    const bool cut = exactTextWidth(exactFm, s, px, weight) > maxW + 1e-9;
    if (elided) *elided = cut;
    if (!cut) return s;
    const qreal toFm = kExactPx / px;
    const qreal ell = ceil64(textWidth(exactFm, QString(QChar(0x2026)), weight) / toFm);
    return elideCut(s, exactFm, maxW * toFm, ell * toFm, weight);
}

// Legend / tooltip label: the raw WiData name keeps double spaces; HTML collapses them (BEH §8).
inline QString displayName(const QString& raw) { return raw.simplified(); }
// Card title: CSS uppercase of the collapsed detail_name (8 titles carry a trailing space, P0 report).
inline QString cardTitleText(const QString& raw) { return raw.simplified().toUpper(); }

} // namespace fincept::screens::wdc::theme
