// src/screens/hdcv_launchpad/HlpTheme.cpp
// Launchpad design tokens (SPEC §1), QFont factories and the public text helpers of HlpTheme.h.
//
// Tokens: the palette is the web Launchpad AFTER /sys/design_system.css (oklch values converted to
// sRGB exactly as Chrome paints them). Light theme = index.html's :root[data-theme="light"] block,
// which outranks design_system.css by specificity.
//
// Text engine (HlpFontTables.cpp + HlpFontShape.cpp, interface in HlpDomLayout_p.h): Chrome on macOS
// shapes -apple-system (SF Pro, variable) with HarfBuzz: glyph advances = hmtx + HVAR at
// opsz = clamp(font-size,17,96) and wght = CSS weight, + AAT `trak` track 0 at ptem = font-size,
// + GPOS `kern` (with GDEF item-variation deltas). Those files read the tables straight from the font
// (QRawFont::fontTable) and reproduce that arithmetic, so layout widths match Chrome to ~0.01px.
#include "screens/hdcv_launchpad/HlpDomLayout_p.h"
#include "screens/hdcv_launchpad/HlpTheme.h"

#include <QGuiApplication>
#include <QImage>
#include <QPainter>
#include <QPainterPath>
#include <QPolygonF>
#include <QScreen>

#include <algorithm>
#include <cmath>

namespace fincept::screens::hlp {

// ============================================================================================
// Palette
// ============================================================================================
namespace {

Palette hlpth_make(const char* bg, const char* bg2, const char* panel, const char* panelHd, const char* line,
                   const char* line2, const char* ink, const char* ink2, const char* ink3, const char* amber,
                   const char* amberDim, const char* up, const char* down, const char* flat, const char* cyan,
                   const char* violet, const char* cheap, const char* rich, const char* neutral) {
    Palette p;
    p.bg = QColor(bg);
    p.bg2 = QColor(bg2);
    p.panel = QColor(panel);
    p.panelHd = QColor(panelHd);
    p.line = QColor(line);
    p.line2 = QColor(line2);
    p.ink = QColor(ink);
    p.ink2 = QColor(ink2);
    p.ink3 = QColor(ink3);
    p.amber = QColor(amber);
    p.amberDim = QColor(amberDim);
    p.up = QColor(up);
    p.down = QColor(down);
    p.flat = QColor(flat);
    p.cyan = QColor(cyan);
    p.violet = QColor(violet);
    p.cheap = QColor(cheap);
    p.rich = QColor(rich);
    p.neutral = QColor(neutral);
    return p;
}

const Palette& hlpth_dark() {
    static const Palette p = hlpth_make("#080a0e", "#15181f", "#0f1217", "#1b2130", "#2b2e34", "#30394d", "#e6eaf2",
                                        "#98a3b8", "#5d6880", "#f2af48", "#8a6000", "#4dbf74", "#f14445", "#98a3b8",
                                        "#2ac4cc", "#9d7cff", "#4dbf74", "#f0505a", "#7b8496");
    return p;
}

const Palette& hlpth_light() {
    static const Palette p = hlpth_make("#eef1f6", "#e3e8f0", "#ffffff", "#f3f6fa", "#d6dce6", "#c2cad8", "#131822",
                                        "#4d5668", "#818b9e", "#a86800", "#d9a54a", "#0f8f5b", "#cc2b38", "#98a3b8",
                                        "#0a7ea4", "#6b43d6", "#0f8f5b", "#cc2b38", "#5d6880");
    return p;
}

bool hlpth_isDark = true;

} // namespace

bool is_dark() {
    return hlpth_isDark;
}

void set_dark(bool dark) {
    hlpth_isDark = dark;
}

const Palette& pal() {
    return hlpth_isDark ? hlpth_dark() : hlpth_light();
}

QColor mixT(const QColor& c, float pct) {
    QColor r = c;
    r.setAlphaF(float(c.alphaF()) * std::clamp(pct, 0.0f, 100.0f) / 100.0f);
    return r;
}

QString css(const QColor& c) {
    return QStringLiteral("rgba(%1,%2,%3,%4)")
        .arg(c.red())
        .arg(c.green())
        .arg(c.blue())
        .arg(QString::number(c.alphaF(), 'f', 3));
}

// ============================================================================================
// Rounded boxes (Skia analytic coverage)
// ============================================================================================
namespace {

/// A rounded box in device pixels.
struct hlpth_RR {
    double l = 0, t = 0, r = 0, b = 0;
    double rx[4] = {0, 0, 0, 0}, ry[4] = {0, 0, 0, 0};
    bool empty() const { return r <= l || b <= t; }
};

/// Overlap of the pixel [c − ½, c + ½] (c = pixel centre) with [lo, hi].
double hlpth_cov1(double c, double lo, double hi) {
    return std::clamp(std::min(c + 0.5, hi) - std::max(c - 0.5, lo), 0.0, 1.0);
}

/// Coverage of the pixel centred at (x, y): straight edges exact, corners clamp(0.5 − d) with d the
/// distance to the circle (exact) or to the ellipse (first-order f/|∇f|, as Skia's ellipse effects).
double hlpth_cov(const hlpth_RR& R, double x, double y) {
    if (R.empty())
        return 0.0;
    const double xc = hlpth_cov1(x, R.l, R.r), yc = hlpth_cov1(y, R.t, R.b);
    double cov = xc * yc;
    if (cov <= 0.0)
        return 0.0;
    if (xc < 1.0 && yc < 1.0) {
        // a pixel on a SQUARE corner of a box rounded elsewhere (Skia's rrect op): the two edge
        // coverages combine by min, not product — measured on #tick (r 0 0 r) and #go (0 r r 0): the
        // half-pixel corners (1697,4) and (1697,5) show 50%, not 25%
        const int i = x < (R.l + R.r) / 2.0 ? (y < (R.t + R.b) / 2.0 ? 0 : 3) : (y < (R.t + R.b) / 2.0 ? 1 : 2);
        bool anyRound = false;
        for (int k = 0; k < 4; ++k)
            anyRound = anyRound || (R.rx[k] > 0.0 && R.ry[k] > 0.0);
        if (anyRound && (R.rx[i] <= 0.0 || R.ry[i] <= 0.0))
            return std::min(xc, yc);
    }
    const double cx[4] = {R.l + R.rx[0], R.r - R.rx[1], R.r - R.rx[2], R.l + R.rx[3]};
    const double cy[4] = {R.t + R.ry[0], R.t + R.ry[1], R.b - R.ry[2], R.b - R.ry[3]};
    for (int i = 0; i < 4; ++i) {
        const double a = R.rx[i], b = R.ry[i];
        if (a <= 0.0 || b <= 0.0)
            continue;
        const double dx = (i == 0 || i == 3) ? cx[i] - x : x - cx[i];
        const double dy = (i < 2) ? cy[i] - y : y - cy[i];
        if (dx <= 0.0 || dy <= 0.0)
            continue;
        double d;
        if (std::abs(a - b) < 1e-9) {
            d = std::hypot(dx, dy) - a;
        } else {
            const double u = dx / a, v = dy / b;
            const double gx = dx / (a * a), gy = dy / (b * b);
            d = (u * u + v * v - 1.0) / (2.0 * std::sqrt(gx * gx + gy * gy));
        }
        cov = std::min(cov, std::clamp(0.5 - d, 0.0, 1.0));
    }
    return cov;
}

hlpth_RR hlpth_dev(const QTransform& D, const QRectF& r, const Radii4& rad) {
    const QRectF m = D.mapRect(r);
    hlpth_RR R;
    R.l = m.left();
    R.t = m.top();
    R.r = m.right();
    R.b = m.bottom();
    for (int i = 0; i < 4; ++i) {
        R.rx[i] = std::max(0.0, rad.c[i].x() * D.m11());
        R.ry[i] = std::max(0.0, rad.c[i].y() * D.m22());
    }
    return R;
}

QPainterPath hlpth_path(const QRectF& r, const Radii4& k) {
    QPainterPath p;
    const QPointF* c = k.c;
    p.moveTo(r.left() + c[0].x(), r.top());
    p.lineTo(r.right() - c[1].x(), r.top());
    p.arcTo(QRectF(r.right() - 2 * c[1].x(), r.top(), 2 * c[1].x(), 2 * c[1].y()), 90, -90);
    p.lineTo(r.right(), r.bottom() - c[2].y());
    p.arcTo(QRectF(r.right() - 2 * c[2].x(), r.bottom() - 2 * c[2].y(), 2 * c[2].x(), 2 * c[2].y()), 0, -90);
    p.lineTo(r.left() + c[3].x(), r.bottom());
    p.arcTo(QRectF(r.left(), r.bottom() - 2 * c[3].y(), 2 * c[3].x(), 2 * c[3].y()), 270, -90);
    p.lineTo(r.left(), r.top() + c[0].y());
    p.arcTo(QRectF(r.left(), r.top(), 2 * c[0].x(), 2 * c[0].y()), 180, -90);
    p.closeSubpath();
    return p;
}

} // namespace

void fillRRect(QPainter& p, const QRectF& r, const Radii4& rad, const QColor& color, const QRectF* hole,
               const Radii4* holeRad) {
    if (!color.isValid() || color.alpha() == 0 || r.width() <= 0 || r.height() <= 0)
        return;
    const QTransform D = p.deviceTransform();
    if (D.type() > QTransform::TxScale || std::abs(D.m11() - D.m22()) > 1e-9 || D.m11() <= 0.0) {
        QPainterPath path = hlpth_path(r, rad);
        if (hole)
            path = path.subtracted(hlpth_path(*hole, holeRad ? *holeRad : Radii4{}));
        p.save();
        p.setRenderHint(QPainter::Antialiasing, true);
        p.fillPath(path, color);
        p.restore();
        return;
    }
    const hlpth_RR O = hlpth_dev(D, r, rad);
    const hlpth_RR H = hole ? hlpth_dev(D, *hole, holeRad ? *holeRad : Radii4{}) : hlpth_RR{};
    QRect B(int(std::floor(O.l)), int(std::floor(O.t)), 0, 0);
    B.setRight(int(std::ceil(O.r)) - 1);
    B.setBottom(int(std::ceil(O.b)) - 1);
    if (p.hasClipping())
        B &= D.mapRect(p.clipBoundingRect()).toAlignedRect();
    if (B.isEmpty())
        return;
    const auto alphaOf = [&](int x, int y) {
        const double px = x + 0.5, py = y + 0.5;
        const double c = hlpth_cov(O, px, py);
        return c <= 0.0 ? 0.0 : c * (1.0 - hlpth_cov(H, px, py));
    };
    // integer bands outside the corner boxes of both shapes: there coverage is separable (1-D)
    const auto mx = [](const hlpth_RR& R, int a, int b) { return std::max(R.rx[a], R.rx[b]); };
    const auto my = [](const hlpth_RR& R, int a, int b) { return std::max(R.ry[a], R.ry[b]); };
    int xL = int(std::ceil(O.l + mx(O, 0, 3))), xR = int(std::floor(O.r - mx(O, 1, 2)));
    int yT = int(std::ceil(O.t + my(O, 0, 1))), yB = int(std::floor(O.b - my(O, 2, 3)));
    if (!H.empty()) {
        xL = std::max(xL, int(std::ceil(H.l + mx(H, 0, 3))));
        xR = std::min(xR, int(std::floor(H.r - mx(H, 1, 2))));
        yT = std::max(yT, int(std::ceil(H.t + my(H, 0, 1))));
        yB = std::min(yB, int(std::floor(H.b - my(H, 2, 3))));
    }
    xL = std::clamp(xL, B.left(), B.right() + 1);
    xR = std::clamp(xR, xL, B.right() + 1);
    yT = std::clamp(yT, B.top(), B.bottom() + 1);
    yB = std::clamp(yB, yT, B.bottom() + 1);
    const QTransform rest = p.worldTransform().inverted() * D;
    p.save();
    p.setWorldTransform(rest.inverted()); // painter units = device pixels
    p.setRenderHint(QPainter::Antialiasing, false);
    p.setPen(Qt::NoPen);
    const auto fill = [&](const QRect& q, double a) {
        if (a <= 0.0 || q.isEmpty())
            return;
        QColor c = color;
        c.setAlphaF(float(color.alphaF() * a));
        p.fillRect(q, c);
    };
    // per-pixel patch (corners, or the whole box when the bands degenerate)
    const auto patch = [&](const QRect& q) {
        const QRect z = q & B;
        if (z.isEmpty())
            return;
        QImage img(z.size(), QImage::Format_ARGB32_Premultiplied);
        const double ca = color.alphaF();
        for (int y = 0; y < z.height(); ++y) {
            QRgb* row = reinterpret_cast<QRgb*>(img.scanLine(y));
            for (int x = 0; x < z.width(); ++x) {
                const double a = alphaOf(z.x() + x, z.y() + y) * ca;
                const int ai = int(std::lround(a * 255.0));
                row[x] = qRgba((color.red() * ai + 127) / 255, (color.green() * ai + 127) / 255,
                               (color.blue() * ai + 127) / 255, ai);
            }
        }
        p.drawImage(z.topLeft(), img);
    };
    if (xL >= xR || yT >= yB || B.width() * B.height() <= 4096) {
        patch(B);
        p.restore();
        return;
    }
    const int L = B.left(), T = B.top(), Rt = B.right() + 1, Bt = B.bottom() + 1;
    patch(QRect(L, T, xL - L, yT - T));
    patch(QRect(xR, T, Rt - xR, yT - T));
    patch(QRect(xR, yB, Rt - xR, Bt - yB));
    patch(QRect(L, yB, xL - L, Bt - yB));
    // top / bottom strips: one alpha per row (x inside both shapes there)
    for (int y = T; y < yT; ++y)
        fill(QRect(xL, y, xR - xL, 1), alphaOf(xL, y));
    for (int y = yB; y < Bt; ++y)
        fill(QRect(xL, y, xR - xL, 1), alphaOf(xL, y));
    // middle band: one alpha per column, runs merged
    for (int x = L; x < Rt;) {
        const double a = alphaOf(x, yT);
        int e = x + 1;
        while (e < Rt && std::abs(alphaOf(e, yT) - a) < 1e-9)
            ++e;
        fill(QRect(x, yT, e - x, yB - yT), a);
        x = e;
    }
    p.restore();
}

// ============================================================================================
// QFont factories
// ============================================================================================
namespace {

/// CSS px → QFont size. Integral sizes use setPixelSize (DPI-independent). Fractional sizes go
/// through setPointSizeF with the DPI Qt uses to resolve point sizes for screen painting.
void hlpth_setPx(QFont& f, float px) {
    if (std::abs(px - std::round(px)) < 1e-4f) {
        f.setPixelSize(int(std::lround(px)));
        return;
    }
    double dpi = 72.0;
    if (auto* s = QGuiApplication::primaryScreen())
        dpi = s->logicalDotsPerInchY();
    f.setPointSizeF(double(px) * 72.0 / dpi);
}

QFont hlpth_font(const QString& family, float px, int weight, float ls, bool italic) {
    QFont f(family);
    hlpth_setPx(f, px);
    f.setWeight(QFont::Weight(std::clamp(weight, 100, 900)));
    f.setItalic(italic);
    f.setKerning(true);
    f.setHintingPreference(QFont::PreferNoHinting);
    if (ls != 0.0f)
        f.setLetterSpacing(QFont::AbsoluteSpacing, ls);
    return f;
}

} // namespace

QFont sans(float px, int weight, float ls_px, bool italic) {
    return hlpth_font(QStringLiteral(".AppleSystemUIFont"), px, weight, ls_px, italic);
}

QFont mono(float px, int weight, float ls_px, bool italic) {
    return hlpth_font(QStringLiteral("Menlo"), px, weight, ls_px, italic);
}

QFont arial(float px, int weight) {
    return hlpth_font(QStringLiteral("Arial"), px, weight, 0.0f, false);
}

// ============================================================================================
// Text engine (detail)
// ============================================================================================
namespace detail {

size_t qHash(const FontKey& k, size_t seed) noexcept {
    return ::qHashMulti(seed, int(k.fam), int(std::lround(k.px * 64.0f)), k.weight, k.italic);
}

QFont qfontFor(const FontKey& k) {
    switch (k.fam) {
    case Fam::Mono:
        return mono(k.px, k.weight, 0.0f, k.italic);
    case Fam::Arial:
        return arial(k.px, k.weight);
    case Fam::Sans:
    default:
        return sans(k.px, k.weight, 0.0f, k.italic);
    }
}

} // namespace detail

// ---- public text helpers (HlpTheme.h) ----
namespace {
detail::FontKey hlpth_key(bool monoFamily, float px, int weight, bool italic) {
    detail::FontKey k;
    k.fam = monoFamily ? detail::Fam::Mono : detail::Fam::Sans;
    k.px = px;
    k.weight = weight;
    k.italic = italic;
    return k;
}
} // namespace

float textWidth(const QString& text, bool monoFamily, float px, int weight, float lsPx, bool italic) {
    auto s = detail::shape(hlpth_key(monoFamily, px, weight, italic), text);
    return s->width(0, int(s->text.size()), lsPx);
}

void drawText(QPainter& p, QPointF baseline, const QString& text, bool monoFamily, float px, int weight,
              const QColor& color, float lsPx, bool italic) {
    const detail::FontKey k = hlpth_key(monoFamily, px, weight, italic);
    auto s = detail::shape(k, text);
    detail::drawShaped(p, k, *s, 0, int(s->text.size()), baseline, lsPx, color);
}

TextVMetrics textVMetrics(bool monoFamily, float px, int weight) {
    const detail::VMetrics m = detail::vmetrics(hlpth_key(monoFamily, px, weight, false));
    return {m.ascent, m.descent};
}

float textWidthArial(const QString& text, float px, int weight) {
    detail::FontKey k = hlpth_key(false, px, weight, false);
    k.fam = detail::Fam::Arial;
    auto s = detail::shape(k, text);
    return s->width(0, int(s->text.size()), 0.0f);
}

void drawTextArial(QPainter& p, QPointF baseline, const QString& text, float px, int weight, const QColor& color) {
    detail::FontKey k = hlpth_key(false, px, weight, false);
    k.fam = detail::Fam::Arial;
    auto s = detail::shape(k, text);
    detail::drawShaped(p, k, *s, 0, int(s->text.size()), baseline, 0.0f, color);
}

TextVMetrics textVMetricsArial(float px, int weight) {
    detail::FontKey k = hlpth_key(false, px, weight, false);
    k.fam = detail::Fam::Arial;
    const detail::VMetrics m = detail::vmetrics(k);
    return {m.ascent, m.descent};
}

namespace {

/// Inside the quarter-ellipse fan (a, b) at (dx, dy) ≥ 0 from its centre, the arc being the conic
/// (weight √2/2) Skia uses for a rrect corner, flattened into 8 chords of equal parameter step — the
/// inner clip of the .tile crescent (fitted on 36 sub-pixel offsets, 27/09: 15 px off by > 24/255
/// against 143 for the true ellipse; the chords sit inside the arc, so Chrome shows more border).
bool hlpth_inCorner(double a, double b, double dx, double dy) {
    constexpr int kN = 8;
    constexpr double kW = 0.70710678118654752;
    double pu = a, pv = 0.0; // t = 0: the side point; t = 1: (0, b)
    for (int j = 1; j <= kN; ++j) {
        const double t = double(j) / kN, s = 1.0 - t;
        const double d = s * s + 2.0 * kW * t * s + t * t;
        const double u = (s * s * a + 2.0 * kW * t * s * a) / d, v = (2.0 * kW * t * s * b + t * t * b) / d;
        if (dy >= pv && dy <= v) // the chord spanning this height: inside when nearer the centre
            return dx <= pu + (dy - pv) * (u - pu) / (v - pv);
        pu = u;
        pv = v;
    }
    return false;
}

/// Inside the rounded rect `r` (radii per corner, elliptical allowed; corner arcs as hlpth_inCorner)?
bool hlpth_inRRect(const QRectF& r, const Radii4& k, double x, double y) {
    if (x < r.left() || x >= r.right() || y < r.top() || y >= r.bottom())
        return false;
    const double cx[4] = {r.left() + k.c[0].x(), r.right() - k.c[1].x(), r.right() - k.c[2].x(), r.left() + k.c[3].x()};
    const double cy[4] = {r.top() + k.c[0].y(), r.top() + k.c[1].y(), r.bottom() - k.c[2].y(), r.bottom() - k.c[3].y()};
    for (int i = 0; i < 4; ++i) {
        const double a = k.c[i].x(), b = k.c[i].y();
        if (a <= 0.0 || b <= 0.0)
            continue;
        const double dx = (i == 0 || i == 3) ? cx[i] - x : x - cx[i];
        const double dy = i < 2 ? cy[i] - y : y - cy[i];
        if (dx > 0.0 && dy > 0.0 && !hlpth_inCorner(a, b, dx, dy))
            return false;
    }
    return true;
}

} // namespace

namespace {

/// Outer rrect (analytic AA) minus the inner rrect sampled 4× MSAA; leftQuad: the left side's hard
/// quad clip too (see fillLeftBorderRRect).
bool hlpth_msaaHole(QPainter& p, const QRectF& sr, const Radii4& ok, const QRectF& inner, const Radii4& ik,
                    const QColor& c, bool leftQuad) {
    const QTransform dt = p.deviceTransform();
    if (dt.type() > QTransform::TxTranslate)
        return false;
    const QRectF in = dt.mapRect(inner);
    const QRect dev = dt.mapRect(sr).toAlignedRect();
    if (dev.isEmpty())
        return true;
    QImage layer(dev.size(), QImage::Format_ARGB32_Premultiplied);
    layer.fill(Qt::transparent);
    {
        QPainter lp(&layer);
        lp.translate(dt.dx() - dev.x(), dt.dy() - dev.y());
        fillRRect(lp, sr, ok, c); // outer, analytic
    }
    // BoxBorderPainter::ClipBorderSidePolygon (hard clip, pixel centres): the left side's quad runs
    // from the outer edge (−0.1) to where the inner corner radii end, which cuts the product seam the
    // two clips leave along the border-less top and bottom edges
    const QRectF o = dt.mapRect(sr);
    const double qx0 = leftQuad ? o.left() - 0.1 : -1e9;
    const double qx1 = leftQuad ? std::max(in.left() + ik.c[0].x(), in.left() + ik.c[3].x()) : 1e9;
    static const double kS[4][2] = {{0.375, 0.125}, {0.875, 0.375}, {0.125, 0.625}, {0.625, 0.875}};
    for (int y = 0; y < layer.height(); ++y) {
        QRgb* row = reinterpret_cast<QRgb*>(layer.scanLine(y));
        for (int x = 0; x < layer.width(); ++x) {
            if (!qAlpha(row[x]))
                continue;
            const double pcx = dev.x() + x + 0.5, pcy = dev.y() + y + 0.5;
            // right and bottom edges included: a centre ON the bottom edge (tile at 71.7+63.02 → 134.5
            // unshifted) keeps the tapered tail of the arc in row 134 (tien VN-INDEX tiles, 27/09)
            if (leftQuad && (pcx < qx0 || pcx > qx1 || pcy < o.top() || pcy > o.bottom())) {
                row[x] = 0;
                continue;
            }
            int n = 0;
            for (const auto& sp : kS)
                n += hlpth_inRRect(in, ik, dev.x() + x + sp[0], dev.y() + y + sp[1]) ? 1 : 0;
            const double f = 1.0 - n / 4.0;
            const auto m = [f](int v) { return int(std::lround(v * f)); };
            row[x] = qRgba(m(qRed(row[x])), m(qGreen(row[x])), m(qBlue(row[x])), m(qAlpha(row[x])));
        }
    }
    p.drawImage(QPointF(dev.x() - dt.dx(), dev.y() - dt.dy()), layer);
    return true;
}

} // namespace

bool fillLeftBorderRRect(QPainter& p, const QRectF& outer, const Radii4& outerRad, const QRectF& inner,
                         const Radii4& innerRad, const QColor& color) {
    return hlpth_msaaHole(p, outer, outerRad, inner, innerRad, color, true);
}


QImage softenLayer(const QImage& in, double ax, double ay) {
    const int w = in.width(), h = in.height();
    QImage mid(in.size(), QImage::Format_ARGB32_Premultiplied), out(in.size(), QImage::Format_ARGB32_Premultiplied);
    const auto mix = [](QRgb a, QRgb b, QRgb c, double k, bool hasA, bool hasC) {
        const auto ch = [&](int (*f)(QRgb)) {
            const double v = (1.0 - 2.0 * k) * f(b) + (hasA ? k * f(a) : 0.0) + (hasC ? k * f(c) : 0.0);
            return std::clamp(int(std::lround(v)), 0, 255);
        };
        return qRgba(ch(qRed), ch(qGreen), ch(qBlue), ch(qAlpha));
    };
    for (int y = 0; y < h; ++y) {
        const QRgb* r = reinterpret_cast<const QRgb*>(in.constScanLine(y));
        QRgb* o = reinterpret_cast<QRgb*>(mid.scanLine(y));
        for (int x = 0; x < w; ++x)
            o[x] = mix(x > 0 ? r[x - 1] : 0, r[x], x + 1 < w ? r[x + 1] : 0, ax, x > 0, x + 1 < w);
    }
    for (int y = 0; y < h; ++y) {
        const QRgb* up = reinterpret_cast<const QRgb*>(mid.constScanLine(std::max(0, y - 1)));
        const QRgb* md = reinterpret_cast<const QRgb*>(mid.constScanLine(y));
        const QRgb* dn = reinterpret_cast<const QRgb*>(mid.constScanLine(std::min(h - 1, y + 1)));
        QRgb* o = reinterpret_cast<QRgb*>(out.scanLine(y));
        for (int x = 0; x < w; ++x)
            o[x] = mix(up[x], md[x], dn[x], ay, y > 0, y + 1 < h);
    }
    return out;
}

/// Outline of an open polyline stroked like Skia's SkStroke with SVG defaults: butt caps, miter joins
/// that turn into BEVELS past the miter limit (SVG ratio miter/width ≤ 4). QPainterPathStroker measures
/// its limit from the centre line (twice as long) and clips the miter instead — a spike on every sharp
/// peak of the P/E spark. One polygon per segment and per join, all counter-clockwise, winding fill.
QPainterPath svgMiterStroke(const QPainterPath& path, double width) {
    QVector<QPointF> pts;
    for (int i = 0; i < path.elementCount(); ++i) {
        const QPointF q = path.elementAt(i);
        if (pts.isEmpty() || QLineF(pts.last(), q).length() > 1e-9) // Skia drops degenerate segments
            pts.push_back(q);
    }
    QPainterPath out;
    out.setFillRule(Qt::WindingFill);
    const auto add = [&out](QVector<QPointF> poly) {
        double a = 0.0;
        for (int i = 0; i < poly.size(); ++i)
            a += poly[i].x() * poly[(i + 1) % poly.size()].y() - poly[(i + 1) % poly.size()].x() * poly[i].y();
        if (a < 0.0)
            std::reverse(poly.begin(), poly.end());
        out.addPolygon(QPolygonF(poly));
        out.closeSubpath();
    };
    const double h = width / 2.0;
    const auto unit = [](QPointF v) { return v / std::hypot(v.x(), v.y()); };
    for (int i = 0; i + 1 < pts.size(); ++i) {
        const QPointF d = unit(pts[i + 1] - pts[i]), n(-d.y() * h, d.x() * h);
        add({pts[i] + n, pts[i + 1] + n, pts[i + 1] - n, pts[i] - n});
        if (i + 2 >= pts.size())
            continue;
        const QPointF d1 = unit(pts[i + 2] - pts[i + 1]);
        const double cross = d.x() * d1.y() - d.y() * d1.x(), dot = d.x() * d1.x() + d.y() * d1.y();
        if (std::abs(cross) < 1e-9 && dot > 0.0)
            continue; // straight on
        const double s = cross > 0.0 ? -1.0 : 1.0; // outer side
        const QPointF u0(-d.y(), d.x()), u1(-d1.y(), d1.x());
        const QPointF a = pts[i + 1] + s * h * u0, b = pts[i + 1] + s * h * u1;
        if ((1.0 + dot) / 2.0 >= 1.0 / 16.0 && 1.0 + dot > 1e-9) // sin(½ angle) ≥ 1/limit(4): miter
            add({pts[i + 1], a, pts[i + 1] + s * h * (u0 + u1) / (1.0 + dot), b});
        else
            add({pts[i + 1], a, b});
    }
    return out;
}

} // namespace fincept::screens::hlp
