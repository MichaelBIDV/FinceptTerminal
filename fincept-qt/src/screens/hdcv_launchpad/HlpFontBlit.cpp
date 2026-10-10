// src/screens/hdcv_launchpad/HlpFontBlit.cpp
// Launchpad text engine — glyph coverage the way Chrome blits text on macOS (Skia
// SkScalerContext_mac_ct.cpp + SkTypeface_Mac::onFilterRec + SkMaskGamma, measured against the Chrome
// captures: the same text row comes out pixel-identical).
//
//  - Chrome asks CoreGraphics for SMOOTHED (dilated) glyphs drawn black on white, undoes CG's gamma-2.0
//    coverage encoding (linear = v²/255), maps the coverage through Skia's pre-blend table for the text
//    colour (contrast 0, sRGB, colour luminance halved) and blends in sRGB. Qt's CoreText engine hands
//    out the same CG glyphs — black on white, inverted (alpha = 255 − v) unless the colour scheme is
//    dark, then white on black (alpha = v) — and blends them linearly, i.e. ~25% lighter.
//  - Skia puts every glyph on a quarter device pixel (drawShaped rounds the pen x the same way) and has
//    CG rasterise it there (SkScalerContext_Mac: subpixel positioning on, quantisation off). Qt's
//    CoreText path renders quarter phases only up to 11px; above that CG snaps its glyphs to whole
//    pixels (Qt leaves CG subpixel positioning at its default) — up to 0.5px off on 12–21px text. So the
//    runs are drawn here with CoreText directly, Skia's way, black on white like Chrome; Qt's own glyph
//    images are the fallback when a face cannot be mapped to a CTFont. CoreText/CoreGraphics are loaded
//    in-process by QtGui; their entry points are looked up with dlsym so the module needs no extra
//    link flags.
#include "screens/hdcv_launchpad/HlpFont_p.h"

#include <QGlyphRun>
#include <QGuiApplication>
#include <QHash>
#include <QImage>
#include <QPainter>
#include <QStyleHints>

#include <CoreText/CoreText.h> // declarations only: every function is resolved at run time (dlsym)
#include <dlfcn.h>

#include <algorithm>
#include <cmath>

namespace fincept::screens::hlp::detail {

namespace {

int hlpbl_scale3(int b) {
    return (b << 5) | (b << 2) | (b >> 1); // sk_t_scale255<3>
}
int hlpbl_canon(int v) {
    return hlpbl_scale3(v >> 5); // SkTMaskGamma<3,3,3>::CanonicalColor, one channel
}
float hlpbl_toLuma(float v) {
    return v <= 0.04045f ? v / 12.92f : std::pow((v + 0.055f) / 1.055f, 2.4f);
}
float hlpbl_fromLuma(float l) {
    return l <= 0.0031308f ? l * 12.92f : 1.055f * std::pow(l, 1.0f / 2.4f) - 0.055f;
}

struct hlpbl_Tables {
    uint8_t lin[2][256]; ///< [dark colour scheme][Qt glyph alpha] → Chrome's linear coverage
    uint8_t pre[8][256]; ///< [luminance bucket][linear coverage] → blit alpha (Skia pre-blend)

    hlpbl_Tables() {
        for (int q = 0; q < 256; ++q) {
            const int v = 255 - q; // CG pixel of the black-on-white glyph Qt inverted
            lin[0][q] = uint8_t(255 - (v * v + 128) / 255);
            lin[1][q] = uint8_t((q * q + 128) / 255); // white on black: the CG pixel is the alpha
        }
        for (int b = 0; b < 8; ++b) {
            // SkTMaskGamma_build_correcting_lut(table, scale3(b), contrast 0, sRGB)
            const float src = float(hlpbl_scale3(b)) / 255.0f, dst = 1.0f - src;
            const float linSrc = hlpbl_toLuma(src), linDst = hlpbl_toLuma(dst);
            for (int i = 0; i < 256; ++i) {
                const float a = float(i) / 255.0f;
                float r = a;
                if (std::fabs(src - dst) >= 1.0f / 256.0f)
                    r = (hlpbl_fromLuma(linSrc * a + (1.0f - a) * linDst) - dst) / (src - dst);
                pre[b][i] = uint8_t(std::clamp(int(std::floor(255.0f * r + 0.5f)), 0, 255));
            }
        }
    }
};

const hlpbl_Tables& hlpbl_tables() {
    static const hlpbl_Tables t;
    return t;
}

/// Luminance bucket of the pre-blend table Chrome picks for a text colour (canonical colour, halved,
/// canonical again, SkComputeLuminance, 3 bits).
int hlpbl_lumBucket(const QColor& c) {
    const int r = hlpbl_canon(hlpbl_canon(c.red()) / 2);
    const int g = hlpbl_canon(hlpbl_canon(c.green()) / 2);
    const int b = hlpbl_canon(hlpbl_canon(c.blue()) / 2);
    return ((r * 54 + g * 183 + b * 19) >> 8) >> 5;
}

/// Qt glyph alpha → Chrome's linear coverage for the colour scheme Qt rasterises glyphs in.
const uint8_t* hlpbl_lin() {
    const bool darkScheme = QGuiApplication::styleHints()->colorScheme() == Qt::ColorScheme::Dark;
    return hlpbl_tables().lin[darkScheme ? 1 : 0];
}

/// In place: alpha (Qt glyph coverage) → pre-blend → premultiplied `color`.
void hlpbl_remap(QImage& img, const QColor& color, const uint8_t* lin) {
    const uint8_t* pre = hlpbl_tables().pre[hlpbl_lumBucket(color)];
    const int cr = color.red(), cg = color.green(), cb = color.blue(), ca = color.alpha();
    for (int y = 0; y < img.height(); ++y) {
        QRgb* row = reinterpret_cast<QRgb*>(img.scanLine(y));
        for (int x = 0; x < img.width(); ++x) {
            const int q = qAlpha(row[x]);
            if (!q)
                continue;
            const int a = (pre[lin[q]] * ca + 127) / 255;
            row[x] = qRgba((cr * a + 127) / 255, (cg * a + 127) / 255, (cb * a + 127) / 255, a);
        }
    }
}

} // namespace

namespace {

/// CoreText / CoreGraphics / CoreFoundation entry points (dlsym; decltype keeps the real signatures).
struct hlpbl_Api {
    bool ok = false;
#define HLPBL_FN(n) decltype(&::n) n = nullptr;
    HLPBL_FN(CTFontCreateWithName)
    HLPBL_FN(CTFontCreateUIFontForLanguage)
    HLPBL_FN(CTFontCreateCopyWithAttributes)
    HLPBL_FN(CTFontCreateCopyWithSymbolicTraits)
    HLPBL_FN(CTFontDescriptorCreateWithAttributes)
    HLPBL_FN(CTFontDrawGlyphs)
    HLPBL_FN(CGColorSpaceCreateWithName)
    HLPBL_FN(CGColorSpaceRelease)
    HLPBL_FN(CGBitmapContextCreate)
    HLPBL_FN(CGContextRelease)
    HLPBL_FN(CGContextSetShouldAntialias)
    HLPBL_FN(CGContextSetShouldSmoothFonts)
    HLPBL_FN(CGContextSetAllowsFontSubpixelQuantization)
    HLPBL_FN(CGContextSetShouldSubpixelQuantizeFonts)
    HLPBL_FN(CGContextSetAllowsFontSubpixelPositioning)
    HLPBL_FN(CGContextSetShouldSubpixelPositionFonts)
    HLPBL_FN(CGContextSetGrayFillColor)
    HLPBL_FN(CGContextSetTextDrawingMode)
    HLPBL_FN(CGContextSetTextMatrix)
    HLPBL_FN(CFStringCreateWithCharacters)
    HLPBL_FN(CFNumberCreate)
    HLPBL_FN(CFDictionaryCreate)
    HLPBL_FN(CFRelease)
#undef HLPBL_FN
    const CFStringRef* kVariation = nullptr;
    const CFStringRef* kSRGB = nullptr;
    const CFDictionaryKeyCallBacks* kKeyCb = nullptr;
    const CFDictionaryValueCallBacks* kValCb = nullptr;

    hlpbl_Api() {
        bool all = true;
        const auto get = [&all](auto& fn, const char* name) {
            fn = reinterpret_cast<std::remove_reference_t<decltype(fn)>>(dlsym(RTLD_DEFAULT, name));
            all = all && fn;
        };
#define HLPBL_GET(n) get(n, #n);
        HLPBL_GET(CTFontCreateWithName)
        HLPBL_GET(CTFontCreateUIFontForLanguage)
        HLPBL_GET(CTFontCreateCopyWithAttributes)
        HLPBL_GET(CTFontCreateCopyWithSymbolicTraits)
        HLPBL_GET(CTFontDescriptorCreateWithAttributes)
        HLPBL_GET(CTFontDrawGlyphs)
        HLPBL_GET(CGColorSpaceCreateWithName)
        HLPBL_GET(CGColorSpaceRelease)
        HLPBL_GET(CGBitmapContextCreate)
        HLPBL_GET(CGContextRelease)
        HLPBL_GET(CGContextSetShouldAntialias)
        HLPBL_GET(CGContextSetShouldSmoothFonts)
        HLPBL_GET(CGContextSetAllowsFontSubpixelQuantization)
        HLPBL_GET(CGContextSetShouldSubpixelQuantizeFonts)
        HLPBL_GET(CGContextSetAllowsFontSubpixelPositioning)
        HLPBL_GET(CGContextSetShouldSubpixelPositionFonts)
        HLPBL_GET(CGContextSetGrayFillColor)
        HLPBL_GET(CGContextSetTextDrawingMode)
        HLPBL_GET(CGContextSetTextMatrix)
        HLPBL_GET(CFStringCreateWithCharacters)
        HLPBL_GET(CFNumberCreate)
        HLPBL_GET(CFDictionaryCreate)
        HLPBL_GET(CFRelease)
#undef HLPBL_GET
        kVariation = static_cast<const CFStringRef*>(dlsym(RTLD_DEFAULT, "kCTFontVariationAttribute"));
        kSRGB = static_cast<const CFStringRef*>(dlsym(RTLD_DEFAULT, "kCGColorSpaceSRGB"));
        kKeyCb = static_cast<const CFDictionaryKeyCallBacks*>(dlsym(RTLD_DEFAULT, "kCFTypeDictionaryKeyCallBacks"));
        kValCb = static_cast<const CFDictionaryValueCallBacks*>(dlsym(RTLD_DEFAULT, "kCFTypeDictionaryValueCallBacks"));
        ok = all && kVariation && kSRGB && kKeyCb && kValCb;
    }
};

const hlpbl_Api& hlpbl_api() {
    static const hlpbl_Api a;
    return a;
}

/// PostScript name (name ID 6) of the face behind `raw`, from its `name` table.
QString hlpbl_psName(const QRawFont& raw) {
    const QByteArray t = raw.fontTable("name");
    const auto u16 = [&t](int o) { return o + 2 <= t.size() ? int((uchar(t[o]) << 8) | uchar(t[o + 1])) : 0; };
    const int count = u16(2), strOff = u16(4);
    QString mac;
    for (int i = 0; i < count; ++i) {
        const int r = 6 + i * 12;
        const int platform = u16(r), nameId = u16(r + 6), len = u16(r + 8), off = strOff + u16(r + 10);
        if (nameId != 6 || off + len > t.size())
            continue;
        if (platform == 3 || platform == 0) {
            QString s;
            for (int k = 0; k + 1 < len; k += 2)
                s.append(QChar(char16_t(u16(off + k))));
            return s;
        }
        if (platform == 1)
            mac = QString::fromLatin1(t.constData() + off, len);
    }
    return mac;
}

CFStringRef hlpbl_cfString(const hlpbl_Api& a, const QString& s) {
    return a.CFStringCreateWithCharacters(nullptr, reinterpret_cast<const UniChar*>(s.utf16()), s.size());
}

/// The CTFont Chrome draws `raw` with at `px` device pixels, cached; nullptr = no mapping (Qt draws).
/// SF (".AppleSystemUIFont") comes from the UI-font API with wght = CSS weight and opsz = px, the
/// variation Blink applies (the shaper's advances use the same coordinates); other faces by
/// PostScript name — except hidden "." faces, which CoreText will not open by name.
CTFontRef hlpbl_ctFont(const QRawFont& raw, double px) {
    static QHash<QString, CTFontRef> cache;
    const hlpbl_Api& a = hlpbl_api();
    // SF: Qt names it ".AppleSystemUIFont" (whole sizes) or ".SF NS" (fractional sizes)
    const bool system = raw.familyName() == QLatin1String(".AppleSystemUIFont") ||
                        raw.familyName() == QLatin1String(".SF NS");
    const bool italic = raw.style() != QFont::StyleNormal;
    const QString key = raw.familyName() + QLatin1Char('|') + raw.styleName() + QLatin1Char('|') +
                        QString::number(raw.weight()) + QLatin1Char('|') + QString::number(int(italic)) +
                        QLatin1Char('|') + QString::number(qRound(px * 64.0));
    auto it = cache.constFind(key);
    if (it != cache.constEnd())
        return *it;
    CTFontRef font = nullptr;
    if (system) {
        CTFontRef base = a.CTFontCreateUIFontForLanguage(kCTFontUIFontSystem, px, nullptr);
        if (base && italic) {
            CTFontRef it2 = a.CTFontCreateCopyWithSymbolicTraits(base, px, nullptr, kCTFontItalicTrait, kCTFontItalicTrait);
            if (it2) {
                a.CFRelease(base);
                base = it2;
            }
        }
        if (base) {
            const int wghtTag = 0x77676874, opszTag = 0x6f70737a;
            const double wght = double(raw.weight());
            CFNumberRef keys[2] = {a.CFNumberCreate(nullptr, kCFNumberIntType, &wghtTag),
                                   a.CFNumberCreate(nullptr, kCFNumberIntType, &opszTag)};
            CFNumberRef vals[2] = {a.CFNumberCreate(nullptr, kCFNumberDoubleType, &wght),
                                   a.CFNumberCreate(nullptr, kCFNumberDoubleType, &px)};
            CFDictionaryRef var = a.CFDictionaryCreate(nullptr, reinterpret_cast<const void**>(keys),
                                                       reinterpret_cast<const void**>(vals), 2, a.kKeyCb, a.kValCb);
            const void* ak[1] = {*a.kVariation};
            const void* av[1] = {var};
            CFDictionaryRef attrs = a.CFDictionaryCreate(nullptr, ak, av, 1, a.kKeyCb, a.kValCb);
            CTFontDescriptorRef desc = a.CTFontDescriptorCreateWithAttributes(attrs);
            font = a.CTFontCreateCopyWithAttributes(base, px, nullptr, desc);
            for (CFTypeRef r : {CFTypeRef(desc), CFTypeRef(attrs), CFTypeRef(var), CFTypeRef(keys[0]), CFTypeRef(keys[1]),
                                CFTypeRef(vals[0]), CFTypeRef(vals[1]), CFTypeRef(base)})
                if (r)
                    a.CFRelease(r);
        }
    } else {
        const QString ps = hlpbl_psName(raw);
        if (!ps.isEmpty() && !ps.startsWith(QLatin1Char('.'))) {
            CFStringRef name = hlpbl_cfString(a, ps);
            font = a.CTFontCreateWithName(name, px, nullptr);
            a.CFRelease(name);
        }
    }
    cache.insert(key, font);
    return font;
}

/// Skia's way: every glyph rasterised by CG at its exact (quarter-pixel) device position, black on
/// white in an sRGB bitmap with smoothing on, subpixel positioning on and quantisation off. Returns
/// the CG pixels of the device rect `dev` (white = no ink).
QImage hlpbl_cgRender(const QVector<QGlyphRun>& runs, const QVector<CTFontRef>& fonts, const QTransform& D,
                      const QRect& dev) {
    const hlpbl_Api& a = hlpbl_api();
    QImage img(dev.size(), QImage::Format_RGB32);
    img.fill(Qt::white);
    CGColorSpaceRef cs = a.CGColorSpaceCreateWithName(*a.kSRGB);
    CGContextRef ctx = a.CGBitmapContextCreate(img.bits(), size_t(img.width()), size_t(img.height()), 8,
                                               size_t(img.bytesPerLine()), cs,
                                               kCGImageAlphaNoneSkipFirst | kCGBitmapByteOrder32Host);
    a.CGColorSpaceRelease(cs);
    if (!ctx)
        return {};
    a.CGContextSetShouldAntialias(ctx, true);
    a.CGContextSetShouldSmoothFonts(ctx, true);
    a.CGContextSetAllowsFontSubpixelQuantization(ctx, false);
    a.CGContextSetShouldSubpixelQuantizeFonts(ctx, false);
    a.CGContextSetAllowsFontSubpixelPositioning(ctx, true);
    a.CGContextSetShouldSubpixelPositionFonts(ctx, true);
    a.CGContextSetTextDrawingMode(ctx, kCGTextFill);
    const CGAffineTransform ident = {1.0, 0.0, 0.0, 1.0, 0.0, 0.0};
    a.CGContextSetTextMatrix(ctx, ident);
    a.CGContextSetGrayFillColor(ctx, 0.0, 1.0);
    const double h = img.height();
    for (int i = 0; i < runs.size(); ++i) {
        const QVector<quint32> gi = runs[i].glyphIndexes();
        const QVector<QPointF> pos = runs[i].positions();
        QVector<CGGlyph> g(gi.size());
        QVector<CGPoint> pt(gi.size());
        for (int k = 0; k < gi.size(); ++k) {
            g[k] = CGGlyph(gi[k]);
            const QPointF d = D.map(pos[k]);
            // Skia keeps subpixel positions on x only: y goes to the nearest whole device pixel
            pt[k] = CGPointMake(d.x() - dev.x(), h - (std::floor(d.y() + 0.5) - dev.y()));
        }
        a.CTFontDrawGlyphs(fonts[i], g.constData(), pt.constData(), size_t(g.size()), ctx);
    }
    a.CGContextRelease(ctx);
    return img;
}

} // namespace

bool blitGlyphRuns(QPainter& p, const QVector<QGlyphRun>& runs, const QColor& color, const QRectF& box) {
    const QTransform D = p.deviceTransform();
    if (D.type() > QTransform::TxScale || !p.device() || std::abs(D.m11() - D.m22()) > 1e-6 || D.m11() <= 0.0)
        return false;
    QRect dev = D.mapRect(box).toAlignedRect();
    if (p.hasClipping())
        dev &= D.mapRect(p.clipBoundingRect()).toAlignedRect();
    if (dev.isEmpty())
        return true;
    // runs CoreText can draw Skia's way; the rest (hidden cascade faces) through Qt's glyph images
    QVector<QGlyphRun> cgRuns, qtRuns;
    QVector<CTFontRef> fonts;
    const bool useCg = hlpbl_api().ok && qEnvironmentVariableIntValue("HLP_QT_GLYPHS") != 1;
    for (const QGlyphRun& run : runs) {
        CTFontRef f = useCg ? hlpbl_ctFont(run.rawFont(), run.rawFont().pixelSize() * D.m11()) : nullptr;
        if (f) {
            cgRuns.push_back(run);
            fonts.push_back(f);
        } else {
            qtRuns.push_back(run);
        }
    }
    // blit 1:1 in device pixels: world W' with W'·(W⁻¹·D) = translate(dev.topLeft())
    const QTransform rest = p.worldTransform().inverted() * D;
    const auto blit = [&](QImage& img, const uint8_t* lin) {
        // linear coverage → Skia pre-blend for the colour → premultiplied colour, in place
        hlpbl_remap(img, color, lin);
        p.save();
        p.setWorldTransform(QTransform::fromTranslate(dev.x(), dev.y()) * rest.inverted());
        p.drawImage(QPointF(0, 0), img);
        p.restore();
    };
    if (!cgRuns.isEmpty()) {
        const QImage cgPix = hlpbl_cgRender(cgRuns, fonts, D, dev);
        if (cgPix.isNull()) {
            qtRuns += cgRuns;
        } else {
            // CG pixel v (black on white) → "glyph alpha" 255 − v, linearised like Qt's light scheme
            QImage tmp(dev.size(), QImage::Format_ARGB32_Premultiplied);
            for (int y = 0; y < tmp.height(); ++y) {
                const QRgb* src = reinterpret_cast<const QRgb*>(cgPix.constScanLine(y));
                QRgb* dst = reinterpret_cast<QRgb*>(tmp.scanLine(y));
                for (int x = 0; x < tmp.width(); ++x) {
                    const int q = 255 - qGreen(src[x]);
                    dst[x] = qRgba(q, q, q, q);
                }
            }
            blit(tmp, hlpbl_tables().lin[0]);
        }
    }
    if (!qtRuns.isEmpty()) {
        // Qt renders the runs white on transparent (its CG glyphs, quarter phases up to 11px)
        QImage tmp(dev.size(), QImage::Format_ARGB32_Premultiplied);
        tmp.fill(Qt::transparent);
        {
            QPainter tp(&tmp);
            tp.setRenderHints(p.renderHints());
            tp.setTransform(D * QTransform::fromTranslate(-dev.x(), -dev.y()));
            tp.setPen(Qt::white);
            for (const QGlyphRun& run : qtRuns)
                tp.drawGlyphRun(QPointF(0, 0), run);
        }
        blit(tmp, hlpbl_lin());
    }
    return true;
}

/// Emoji the way Skia draws them: CoreGraphics renders the sbix glyph at its whole-pixel origin (the
/// caller rounds x like Chrome) with the glyph's own fractional bearing inside. Qt's CoreText engine
/// instead aligns the glyph's bounding box to its image — 0.3px off at 11px, which moves the inner
/// edges of 📍 one column right of Chrome's (🇻🇳, filled to the box edge, does not show it).
bool blitColourGlyphRuns(QPainter& p, const QVector<QGlyphRun>& runs) {
    const hlpbl_Api& a = hlpbl_api();
    const QTransform D = p.deviceTransform();
    if (!a.ok || qEnvironmentVariableIntValue("HLP_QT_GLYPHS") == 1 || D.type() > QTransform::TxScale ||
        !p.device() || std::abs(D.m11() - D.m22()) > 1e-6 || D.m11() <= 0.0)
        return false;
    QVector<CTFontRef> fonts;
    QRectF bounds;
    for (const QGlyphRun& run : runs) {
        const double px = run.rawFont().pixelSize() * D.m11();
        CTFontRef f = hlpbl_ctFont(run.rawFont(), px);
        if (!f && run.rawFont().familyName().contains(QLatin1String("Apple Color Emoji"))) {
            // Qt's cascade hands out the hidden ".Apple Color Emoji UI" face (same glyph ids); Chrome
            // draws with Apple Color Emoji itself — 📍 of CHÍNH PHỦ lands one column left in Qt's face
            static QHash<int, CTFontRef> emoji;
            const int key = int(std::lround(px * 64.0));
            f = emoji.value(key);
            if (!f) {
                CFStringRef name = hlpbl_cfString(a, QStringLiteral("AppleColorEmoji"));
                f = a.CTFontCreateWithName(name, px, nullptr);
                a.CFRelease(name);
                emoji.insert(key, f);
            }
        }
        if (!f)
            return false;
        fonts.push_back(f);
        for (const QPointF& q : run.positions()) {
            const QPointF d = D.map(q);
            bounds |= QRectF(d.x() - px, d.y() - 1.6 * px - 2.0, 3.0 * px, 2.2 * px + 4.0);
        }
    }
    QRect dev = bounds.toAlignedRect();
    if (p.hasClipping())
        dev &= D.mapRect(p.clipBoundingRect()).toAlignedRect();
    if (dev.isEmpty())
        return true;
    QImage img(dev.size(), QImage::Format_ARGB32_Premultiplied);
    img.fill(Qt::transparent);
    CGColorSpaceRef cs = a.CGColorSpaceCreateWithName(*a.kSRGB);
    CGContextRef ctx = a.CGBitmapContextCreate(img.bits(), size_t(img.width()), size_t(img.height()), 8,
                                               size_t(img.bytesPerLine()), cs,
                                               kCGImageAlphaPremultipliedFirst | kCGBitmapByteOrder32Host);
    a.CGColorSpaceRelease(cs);
    if (!ctx)
        return false;
    a.CGContextSetShouldAntialias(ctx, true);
    a.CGContextSetTextDrawingMode(ctx, kCGTextFill);
    const CGAffineTransform ident = {1.0, 0.0, 0.0, 1.0, 0.0, 0.0};
    a.CGContextSetTextMatrix(ctx, ident);
    const double h = img.height();
    for (int i = 0; i < runs.size(); ++i) {
        const QVector<quint32> gi = runs[i].glyphIndexes();
        const QVector<QPointF> pos = runs[i].positions();
        QVector<CGGlyph> g(gi.size());
        QVector<CGPoint> pt(gi.size());
        for (int k = 0; k < gi.size(); ++k) {
            g[k] = CGGlyph(gi[k]);
            const QPointF d = D.map(pos[k]);
            pt[k] = CGPointMake(d.x() - dev.x(), h - (std::floor(d.y() + 0.5) - dev.y()));
        }
        a.CTFontDrawGlyphs(fonts[i], g.constData(), pt.constData(), size_t(g.size()), ctx);
    }
    a.CGContextRelease(ctx);
    const QTransform rest = p.worldTransform().inverted() * D;
    p.save();
    p.setWorldTransform(QTransform::fromTranslate(dev.x(), dev.y()) * rest.inverted());
    p.drawImage(QPointF(0, 0), img);
    p.restore();
    return true;
}

} // namespace fincept::screens::hlp::detail
