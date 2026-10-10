// WdcHcPaint.cpp (package C): paintChart, the only place of the chart engine that touches QPainter.
//
// Layer order of the Highcharts SVG (ENG §4.1): grid z1, axis lines z2 (width 0, not drawn), series
// group z3 sorted by series zIndex (inside a series: area z0, graph z1, then points/markers), axis
// labels z7. Series are clipped to the plot box (HS clipPath rect plotWidth x plotHeight); markers are
// not clipped (only inside points have one). Not drawn: X grid, axis lines, lastVisiblePrice, credits,
// watermark (DESIGN §16 C7), crosshair (package F draws it on top).
//
// Pens follow SVG: a dashStyle is always set by WiData ('no-marker' = solid), so linecap butt and
// linejoin miter with miterlimit 4 (Qt::SvgMiterJoin keeps the SVG bevel fallback). Dash arrays are
// dashstyleSetter (HS:10502-10527) in px, handed to QPen in pen-width units.
// Line shadow (HS:11075-11084, 13194-13206): feDropShadow dx 1 dy 1, stdDeviation 1.25 CSS px,
// flood #000 opacity 0.5, under the stroke; blurred on an alpha image at the device pixel ratio.
// Cost (DESIGN §16 C18, ENG2 w4): a dense series is stroked through WdcMask (union coverage, Skia's supersampled
// model) instead of Qt's rasterizer; a sparse one through Qt in vertical strips when its path is long (same pixels);
// flat runs are merged first; the blur works on bytes. Every real card paints in < 60 ms at DPR 2 (was up to 1.9 s).
#include "WdcHcInternal_p.h"

#include <QFont>
#include <QFontDatabase>
#include <QFontMetricsF>
#include <QImage>
#include <QPaintDevice>
#include <QPainter>
#include <QPainterPath>

#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>
#include <numeric>

// Highcharts runs in JavaScript: no fused multiply-add. Clang contracts a*b+c into FMA by default
// (-ffp-contract=on), which flips spline clamps and tick comparisons by one ulp (ENG_w3 §2).
#if defined(__clang__)
#pragma clang fp contract(off)
#elif defined(__GNUC__)
#pragma GCC optimize("fp-contract=off")
#endif

namespace fincept::screens::wdc {

namespace {

const QColor kLabelColor(0x21, 0x23, 0x2E);   // xAxis/yAxis labels.style.color (ENG §1.2, §1.3)
constexpr double kXLabelPx = 12, kExpandedYLabelPx = 11;
constexpr double kShadowDx = 1, kShadowDy = 1, kShadowSigma = 1.25, kShadowOpacity = 0.5;
constexpr double kMiterLimit = 4;

// dashstyleSetter: px dash array, empty = solid ("none").
std::vector<double> wdcPaint_dashArray(const QString& style, double strokeWidth) {
    if (style.isEmpty())
        return {};
    QString v = style.toLower();
    auto first = [&v](const QString& from, const QString& to) {
        const int at = v.indexOf(from);
        if (at >= 0)
            v.replace(at, from.size(), to);
    };
    first(QStringLiteral("shortdashdotdot"), QStringLiteral("3,1,1,1,1,1,"));
    first(QStringLiteral("shortdashdot"), QStringLiteral("3,1,1,1"));
    first(QStringLiteral("shortdot"), QStringLiteral("1,1,"));
    first(QStringLiteral("shortdash"), QStringLiteral("3,1,"));
    first(QStringLiteral("longdash"), QStringLiteral("8,3,"));
    v.replace(QStringLiteral("dot"), QStringLiteral("1,3,"));
    first(QStringLiteral("dash"), QStringLiteral("4,3,"));
    if (v.endsWith(','))
        v.chop(1);
    std::vector<double> out;
    for (const QString& part : v.split(',')) {
        bool ok = false;
        const int n = part.trimmed().toInt(&ok);   // pInt; anything else is NaN => "none"
        if (!ok)
            return {};
        out.push_back(n * strokeWidth);
    }
    return out;
}

QPen wdcPaint_pen(const QColor& color, double width) {
    QPen pen(color, width, Qt::SolidLine, Qt::FlatCap, Qt::SvgMiterJoin);
    pen.setMiterLimit(kMiterLimit);
    return pen;
}

// The shape to stroke with a solid pen: the dashed pieces when the style has a dash array.
QPainterPath wdcPaint_strokeShape(const QPainter& p, const QPainterPath& path, double width, const QString& dashStyle) {
    std::vector<double> dash = wdcPaint_dashArray(dashStyle, width);
    if (dash.empty() || width <= 0)
        return path;
    if (dash.size() % 2) {                                 // SVG repeats an odd list
        const std::vector<double> once = dash;
        dash.insert(dash.end(), once.begin(), once.end());
    }
    const QTransform m = p.deviceTransform();
    const double res = std::max(std::hypot(m.m11(), m.m12()), std::hypot(m.m21(), m.m22()));
    return hcint::dashPath(path, dash, res);
}

QFont wdcPaint_font(double px) {
    static const QString family = [] {
        const QStringList fams = QFontDatabase::families();
        for (const char* f : {"Inter Static opsz14", "Inter Variable", "Inter"})
            if (fams.contains(QLatin1String(f)))
                return QString::fromLatin1(f);
        return QStringLiteral("Inter");
    }();
    QFont font(family);
    font.setPixelSize(int(std::lround(px)));
    font.setWeight(QFont::Normal);
    font.setKerning(true);
    font.setHintingPreference(QFont::PreferNoHinting);
    if (family == QLatin1String("Inter Variable")) {
        font.setVariableAxis(QFont::Tag("wght"), 400.f);
        font.setVariableAxis(QFont::Tag("opsz"), 14.f);   // WiData's static subsets are opsz 14 at every size
    }
    return font;
}

using Alpha = std::vector<uint8_t>;   // device alpha, row-major dev.width() x dev.height(), 0..255

// One box pass of size `d` with the SVG spec offsets (window [i - lead, i - lead + d)), (sum + d / 2) / d, on the rows
// (vertical == false) or the columns of a w x h alpha. Rows go through a prefix sum, columns through running sums
// over whole rows; the division is a multiply-shift, equal to (v + d / 2) / d for every v in 0..255 d when d <= 10
// (brute-forced for d 4..10, i.e. DPR 1.75..4), so both loops vectorize.
void wdcPaint_box(const uint8_t* src, uint8_t* dst, int w, int h, int d, int lead, bool vertical, std::vector<int>& sum) {
    const int half = d / 2;
    const quint32 mul = (65536u + quint32(d) - 1) / quint32(d);
    auto q = [half, mul](int v) { return uint8_t((quint32(v + half) * mul) >> 16); };
    if (!vertical) {
        sum.assign(size_t(w) + size_t(d) + 1, 0);   // prefix over the row padded with zeros: P[k] = sum src[< k - lead]
        for (int y = 0; y < h; ++y) {
            const uint8_t* sr = src + size_t(y) * size_t(w);
            uint8_t* o = dst + size_t(y) * size_t(w);
            int* P = sum.data();
            int acc = 0;
            for (int k = 0; k <= w + d; ++k) {
                P[k] = acc;
                const int i = k - lead;
                if (i >= 0 && i < w)
                    acc += sr[i];
            }
            for (int i = 0; i < w; ++i)                    // window [i - lead, i - lead + d) = P[i + d] - P[i]
                o[i] = q(P[i + d] - P[i]);
        }
        return;
    }
    sum.assign(size_t(w), 0);
    for (int j = std::max(0, -lead); j < std::min(h, d - lead); ++j)
        for (int x = 0; x < w; ++x)
            sum[size_t(x)] += src[size_t(j) * size_t(w) + size_t(x)];
    for (int y = 0; y < h; ++y) {
        uint8_t* o = dst + size_t(y) * size_t(w);
        int* sm = sum.data();
        for (int x = 0; x < w; ++x)
            o[x] = q(sm[x]);
        const int in = y - lead + d, out = y - lead;
        if (in < h) {
            const uint8_t* r = src + size_t(in) * size_t(w);
            for (int x = 0; x < w; ++x)
                sm[x] += r[x];
        }
        if (out >= 0) {
            const uint8_t* r = src + size_t(out) * size_t(w);
            for (int x = 0; x < w; ++x)
                sm[x] -= r[x];
        }
    }
}

// feGaussianBlur of a w x h alpha in place, rows then columns: three box blurs from sigma 2 (SVG 1.1 §15.17), a true
// Gaussian below (DPR 1), each pass rounded to an integer as before (ENG w3 results unchanged).
void wdcPaint_blur(Alpha& a, int w, int h, double sigma) {
    Alpha t(a.size());
    std::vector<int> sum;
    if (sigma >= 2.0) {
        const int d = int(std::floor(sigma * 3 * std::sqrt(2 * M_PI) / 4 + 0.5));
        for (const bool vertical : {false, true}) {
            if (d % 2) {
                wdcPaint_box(a.data(), t.data(), w, h, d, d / 2, vertical, sum);
                wdcPaint_box(t.data(), a.data(), w, h, d, d / 2, vertical, sum);
                wdcPaint_box(a.data(), t.data(), w, h, d, d / 2, vertical, sum);
            } else {
                wdcPaint_box(a.data(), t.data(), w, h, d, d / 2, vertical, sum);
                wdcPaint_box(t.data(), a.data(), w, h, d, d / 2 - 1, vertical, sum);
                wdcPaint_box(a.data(), t.data(), w, h, d + 1, d / 2, vertical, sum);
            }
            a.swap(t);
        }
        return;
    }
    const int rad = int(std::ceil(3 * sigma));
    std::vector<double> k(static_cast<size_t>(2 * rad + 1)), acc(static_cast<size_t>(w));
    for (int i = -rad; i <= rad; ++i)
        k[size_t(i + rad)] = std::exp(-(i * i) / (2 * sigma * sigma));
    const double norm = std::accumulate(k.begin(), k.end(), 0.0);
    for (int y = 0; y < h; ++y)                       // rows
        for (int i = 0; i < w; ++i) {
            double s = 0;
            for (int j = std::max(-rad, -i); j <= rad && i + j < w; ++j)
                s += k[size_t(j + rad)] * a[size_t(y) * size_t(w) + size_t(i + j)];
            t[size_t(y) * size_t(w) + size_t(i)] = uint8_t(std::lround(s / norm));
        }
    for (int y = 0; y < h; ++y) {                     // columns, same summation order per pixel
        std::fill(acc.begin(), acc.end(), 0.0);
        for (int j = std::max(-rad, -y); j <= rad && y + j < h; ++j)
            for (int x = 0; x < w; ++x)
                acc[size_t(x)] += k[size_t(j + rad)] * t[size_t(y + j) * size_t(w) + size_t(x)];
        for (int x = 0; x < w; ++x)
            a[size_t(y) * size_t(w) + size_t(x)] = uint8_t(std::lround(acc[size_t(x)] / norm));
    }
}

// ---- Stroke coverage for dense series, modelled on Skia's supersampled scan converter (SkScan_AntiPath, SHIFT 2),
// which Chromium uses for paths with many points for their size: the path is scaled by 4 and scan converted
// without AA (samples at the centres of a 4 x 4 grid per device pixel, edge rows round(y0) <= j < round(y1), span
// round(xl) <= i < round(xr)), alpha = 16 per sample (a full pixel 255). The nonzero fill of a stroke outline is
// the UNION of the stroke pieces, built here as one convex polygon per segment of the path flattened to 0.01
// device px (butt ends) plus a miter (limit 4, else bevel) at every vertex. Qt's AA instead adds the coverage of
// overlapping outline pieces, and its gray rasterizer re-walks the whole outline once per band when the cell pool
// overflows: seconds for a 5 000-point zigzag (ENG2 w4: 1.8 s for one card, now a few ms).
constexpr int kSS = 4;
constexpr double kFlattenTolSS = 0.01 * kSS;

struct WdcMask {                          // one bit per sample, 64 samples (16 device pixels) per word
    int w = 0, h = 0, words = 0;          // super-sample grid of the device rect
    std::vector<quint64> bits;
    int wy0, wy1 = 0, wk0, wk1 = 0;       // touched rows [wy0, wy1), words [wk0, wk1)
    WdcMask(int sw, int sh) : w(sw), h(sh), words((sw + 63) / 64), bits(size_t(words) * size_t(sh), 0), wy0(sh), wk0(words) {}

    void span(int j, int i0, int i1) {    // samples [i0, i1) of row j
        quint64* r = bits.data() + size_t(j) * size_t(words);
        const int k0 = i0 >> 6, k1 = (i1 - 1) >> 6;
        const quint64 m0 = ~0ull << (i0 & 63), m1 = ~0ull >> (63 - ((i1 - 1) & 63));
        if (k0 == k1) {
            r[k0] |= m0 & m1;
        } else {
            r[k0] |= m0;
            for (int k = k0 + 1; k < k1; ++k)
                r[k] = ~0ull;
            r[k1] |= m1;
        }
        wy0 = std::min(wy0, j); wy1 = std::max(wy1, j + 1); wk0 = std::min(wk0, k0); wk1 = std::max(wk1, k1 + 1);
    }

    void fillConvex(const QPointF* v, int n) {
        double ymin = v[0].y(), ymax = ymin, xmin = v[0].x(), xmax = xmin;
        for (int k = 1; k < n; ++k) {
            ymin = std::min(ymin, v[k].y()); ymax = std::max(ymax, v[k].y());
            xmin = std::min(xmin, v[k].x()); xmax = std::max(xmax, v[k].x());
        }
        if (!(ymax > -1 && ymin < h + 1 && xmax > -1 && xmin < w + 1))
            return;   // also rejects NaN
        const int j0 = int(std::floor(std::max(ymin, -1.0) + 0.5)), j1 = int(std::floor(std::min(ymax, h + 1.0) + 0.5));
        for (int j = std::max(0, j0); j < std::min(h, j1); ++j) {
            const double y = j + 0.5;
            double xl = std::numeric_limits<double>::infinity(), xr = -xl;
            for (int k = 0; k < n; ++k) {
                const QPointF& a = v[k];
                const QPointF& b = v[(k + 1) % n];
                if ((a.y() <= y) == (b.y() <= y))
                    continue;
                const double x = a.x() + (y - a.y()) * (b.x() - a.x()) / (b.y() - a.y());
                xl = std::min(xl, x);
                xr = std::max(xr, x);
            }
            if (!(xl <= xr))
                continue;
            const int i0 = std::max(0, int(std::floor(std::max(xl, -1.0) + 0.5)));
            const int i1 = std::min(w, int(std::floor(std::min(xr, w + 1.0) + 0.5)));
            if (i0 < i1)
                span(j, i0, i1);
        }
    }

    // Butt-ended stroke of one flattened subpath, half width `hw` (super-sample units).
    void strokePolyline(const std::vector<QPointF>& pts, double hw) {
        QPointF prevU, prevN;
        bool havePrev = false;
        for (size_t k = 0; k + 1 < pts.size(); ++k) {
            const QPointF a = pts[k], d = pts[k + 1] - a;
            const double len = std::hypot(d.x(), d.y());
            if (!(len > 0))
                continue;
            const QPointF u = d / len, nrm(-u.y() * hw, u.x() * hw);
            const QPointF quad[4] = {a + nrm, pts[k + 1] + nrm, pts[k + 1] - nrm, a - nrm};
            fillConvex(quad, 4);
            if (havePrev) {
                const double cross = prevU.x() * u.y() - prevU.y() * u.x(), dot = prevU.x() * u.x() + prevU.y() * u.y();
                if (cross != 0 || dot < 0) {
                    const double s = cross > 0 ? -1.0 : 1.0;   // outer side: away from the turn
                    const QPointF o0 = a + prevN * s, o1 = a + nrm * s;
                    const double cosHalf = std::sqrt(std::max(0.0, (1 + dot) / 2));
                    const QPointF bis = prevN + nrm;
                    const double bl = std::hypot(bis.x(), bis.y());
                    if (cosHalf > 0.25 && bl > 0) {             // SVG miterlimit 4: 1 / sin(theta / 2) <= 4
                        const QPointF tip = a + bis * (s * hw / (cosHalf * bl));
                        const QPointF miter[4] = {a, o0, tip, o1};
                        fillConvex(miter, 4);
                    } else {
                        const QPointF bevel[3] = {a, o0, o1};
                        fillConvex(bevel, 3);
                    }
                }
            }
            prevU = u;
            prevN = nrm;
            havePrev = true;
        }
    }

    // Device alpha (dw x dh): 16 per sample set, 255 when all 16 are. SWAR nibble counts, 16 device px per word.
    Alpha alpha(int dw, int dh) const {
        Alpha out(size_t(dw) * size_t(dh), 0);
        constexpr quint64 k55 = 0x5555555555555555ull, k33 = 0x3333333333333333ull, k0F = 0x0F0F0F0F0F0F0F0Full;
        for (int r = wy0 / kSS; r < (wy1 + kSS - 1) / kSS && r < dh; ++r) {
            uint8_t* o = out.data() + size_t(r) * size_t(dw);
            for (int k = wk0; k < wk1; ++k) {
                quint64 even = 0, odd = 0;
                for (int s = 0; s < kSS; ++s) {
                    const int j = r * kSS + s;
                    if (j >= h)
                        break;
                    quint64 x = bits[size_t(j) * size_t(words) + size_t(k)];
                    x = x - ((x >> 1) & k55);
                    x = (x & k33) + ((x >> 2) & k33);          // samples per nibble (= per device px), 0..4
                    even += x & k0F;
                    odd += (x >> 4) & k0F;
                }
                for (int b = 0; b < 8; ++b) {
                    const int c = k * 16 + 2 * b;
                    if (c < dw)
                        o[c] = uint8_t(std::min(255, int((even >> (8 * b)) & 0xFF) * 16));
                    if (c + 1 < dw)
                        o[c + 1] = uint8_t(std::min(255, int((odd >> (8 * b)) & 0xFF) * 16));
                }
            }
        }
        return out;
    }
};

WdcMask wdcPaint_unionMask(const QPainterPath& path, double width, const QRect& dev, qreal dpr) {
    WdcMask m(dev.width() * kSS, dev.height() * kSS);
    const double sc = dpr * kSS, ox = -dev.left() * double(kSS), oy = -dev.top() * double(kSS), hw = width * sc / 2;
    std::vector<QPointF> poly;
    for (int i = 0; i < path.elementCount(); ++i) {
        const QPainterPath::Element e = path.elementAt(i);
        const QPointF q(e.x * sc + ox, e.y * sc + oy);
        if (e.type == QPainterPath::MoveToElement) {
            m.strokePolyline(poly, hw);
            poly.assign(1, q);
        } else if (e.type == QPainterPath::LineToElement) {
            poly.push_back(q);
        } else if (e.type == QPainterPath::CurveToElement && i + 2 < path.elementCount() && !poly.empty()) {
            const QPointF p0 = poly.back(), p1 = q;
            const QPointF p2(path.elementAt(i + 1).x * sc + ox, path.elementAt(i + 1).y * sc + oy);
            const QPointF p3(path.elementAt(i + 2).x * sc + ox, path.elementAt(i + 2).y * sc + oy);
            i += 2;
            const QPointF d1 = p0 - p1 * 2 + p2, d2 = p1 - p2 * 2 + p3;   // Wang's formula
            const double dd = std::max(std::hypot(d1.x(), d1.y()), std::hypot(d2.x(), d2.y()));
            const int n = std::clamp(int(std::ceil(std::sqrt(0.75 * dd / kFlattenTolSS))), 1, 256);
            for (int k = 1; k <= n; ++k) {
                const double t = double(k) / n, mt = 1 - t;
                poly.push_back(p0 * (mt * mt * mt) + p1 * (3 * mt * mt * t) + p2 * (3 * mt * t * t) + p3 * (t * t * t));
            }
        }
    }
    m.strokePolyline(poly, hw);
    return m;
}

Alpha wdcPaint_unionAlpha(const QPainterPath& path, double width, const QRect& dev, qreal dpr) {
    return wdcPaint_unionMask(path, width, dev, dpr).alpha(dev.width(), dev.height());
}

// QPainter::strokePath in vertical strips of device pixels, each strip clipped to itself and stroked with the pieces
// that reach it (x extent within 2 x pen width + 2 device px: butt caps, miter limit 4). Inside a strip the outline
// edges, and the winding that crosses into it, are those of the whole stroke, so the AA result is the same; Qt's gray
// rasterizer, which re-walks the whole outline for every band once its cell pool overflows, stays fast (a 7 944-point
// policy rate over 30 years: 140 ms for one stroke at expanded size).
void wdcPaint_strokeStrips(QPainter& p, const QPainterPath& path, const QPen& pen) {
    constexpr int kPerStrip = 600;   // elements
    const QTransform t = p.deviceTransform();
    const int n = path.elementCount();
    if (n <= kPerStrip || t.type() > QTransform::TxScale || t.m11() <= 0) {
        p.strokePath(path, pen);
        return;
    }
    struct Piece { int first, last; double x0, x1; QPointF from; };   // elements [first, last], device x extent
    std::vector<Piece> pieces;
    QPointF cur;
    for (int i = 0; i < n; ++i) {
        const QPainterPath::Element e = path.elementAt(i);
        if (e.type == QPainterPath::MoveToElement) {
            cur = QPointF(e.x, e.y);
            continue;
        }
        const int last = e.type == QPainterPath::CurveToElement ? std::min(n - 1, i + 2) : i;
        double x0 = t.map(cur).x(), x1 = x0;
        for (int k = i; k <= last; ++k) {
            const double x = t.map(QPointF(path.elementAt(k).x, path.elementAt(k).y)).x();
            x0 = std::min(x0, x);
            x1 = std::max(x1, x);
        }
        pieces.push_back({i, last, x0, x1, cur});
        cur = QPointF(path.elementAt(last).x, path.elementAt(last).y);
        i = last;
    }
    const double reach = 2 * pen.widthF() * t.m11() + 2;
    const QTransform inv = t.inverted();
    auto painterX = [&inv](double devX) { return inv.map(QPointF(std::clamp(devX, -1e6, 1e6), 0)).x(); };
    double lo = -1e9;
    for (size_t a = 0; a < pieces.size();) {
        const size_t b = std::min(pieces.size(), a + kPerStrip / 3);
        const double hi = b == pieces.size() ? 1e9 : std::floor(pieces[b].x0);   // strip [lo, hi) of device x
        a = b;
        if (!(hi > lo))
            continue;
        QPainterPath sub;
        int prevLast = -2;
        for (const Piece& q : pieces) {
            if (q.x1 < lo - reach || q.x0 > hi + reach)
                continue;
            if (q.first != prevLast + 1)
                sub.moveTo(q.from);
            for (int k = q.first; k <= q.last; ++k) {
                const QPainterPath::Element e = path.elementAt(k);
                if (e.type == QPainterPath::CurveToElement && k + 2 <= q.last) {
                    sub.cubicTo(QPointF(e.x, e.y), path.elementAt(k + 1), path.elementAt(k + 2));
                    k += 2;
                } else {
                    sub.lineTo(e.x, e.y);
                }
            }
            prevLast = q.last;
        }
        p.save();
        p.setClipRect(QRectF(QPointF(painterX(lo), -1e6), QPointF(painterX(hi), 1e6)), Qt::IntersectClip);
        p.strokePath(sub, pen);
        p.restore();
        lo = hi;
    }
}

// Device-pixel alpha (0..255, row-major dev.width() x dev.height()) of `path` stroked with `pen` by Qt's own AA,
// the painter being a plain dpr scale (+ integer device translation). Sparse series: their stroke does not fold.
Alpha wdcPaint_strokeAlpha(const QPainterPath& path, const QPen& pen, const QRect& dev, qreal dpr) {
    QImage img(dev.size(), QImage::Format_ARGB32_Premultiplied);
    img.fill(Qt::transparent);
    {
        QPainter ip(&img);
        ip.setRenderHint(QPainter::Antialiasing, true);
        ip.translate(-dev.left(), -dev.top());
        ip.scale(dpr, dpr);
        QPen black = pen;
        black.setColor(Qt::black);
        wdcPaint_strokeStrips(ip, path, black);
    }
    const int w = dev.width(), h = dev.height();
    Alpha alpha(size_t(w) * size_t(h), 0);
    for (int y = 0; y < h; ++y) {
        const QRgb* row = reinterpret_cast<const QRgb*>(img.constScanLine(y));
        uint8_t* out = alpha.data() + size_t(y) * size_t(w);
        for (int x = 0; x < w; ++x)
            out[x] = uint8_t(qAlpha(row[x]));
    }
    return alpha;
}

// Drop shadow image from a device alpha over `dev` (feDropShadow: blur stdDeviation 1.25 CSS px, offset 1,1,
// flood #000 x 0.5); the caller draws it under the stroke at dev / dpr + (1, 1).
QImage wdcPaint_shadowImage(Alpha alpha, const QRect& dev, qreal dpr) {
    const int w = dev.width(), h = dev.height();
    wdcPaint_blur(alpha, w, h, kShadowSigma * dpr);
    QRgb lut[256];
    for (int v = 0; v < 256; ++v)
        lut[v] = qRgba(0, 0, 0, int(std::lround(v * kShadowOpacity)));   // black premultiplied
    QImage img(dev.size(), QImage::Format_ARGB32_Premultiplied);
    for (int y = 0; y < h; ++y) {
        QRgb* row = reinterpret_cast<QRgb*>(img.scanLine(y));
        const uint8_t* a = alpha.data() + size_t(y) * size_t(w);
        for (int x = 0; x < w; ++x)
            row[x] = lut[a[x]];
    }
    img.setDevicePixelRatio(dpr);
    return img;
}

void wdcPaint_drawShadow(QPainter& p, const QImage& img, const QRect& dev, qreal dpr) {
    p.save();
    p.setRenderHint(QPainter::SmoothPixmapTransform, true);
    p.drawImage(QPointF(dev.left() / dpr + kShadowDx, dev.top() / dpr + kShadowDy), img);
    p.restore();
}

// Device rect of the shadow of `path` (painter coordinates), empty when nothing can show in `area`.
QRect wdcPaint_shadowRect(const QPainterPath& path, const QPen& pen, const QRectF& area, qreal dpr) {
    const double margin = std::ceil(3 * kShadowSigma) + 2 + pen.widthF();
    const QRectF src = (path.boundingRect().adjusted(-margin, -margin, margin, margin))
                           .intersected(area.adjusted(-margin - kShadowDx, -margin - kShadowDy, margin, margin));
    if (src.isEmpty())
        return QRect();
    return QRect(int(std::floor(src.left() * dpr)), int(std::floor(src.top() * dpr)),
                 int(std::ceil(src.width() * dpr)) + 2, int(std::ceil(src.height() * dpr)) + 2);
}

// Stroke colour through a device alpha (dense series: union coverage, see WdcMask).
void wdcPaint_fillAlpha(QPainter& p, const Alpha& alpha, const QRect& dev, qreal dpr, const QColor& c) {
    QImage img(dev.size(), QImage::Format_ARGB32_Premultiplied);
    const QRgb rgb = c.rgb();
    const double ca = c.alphaF();
    QRgb lut[256];
    for (int v = 0; v < 256; ++v)
        lut[v] = qPremultiply(qRgba(qRed(rgb), qGreen(rgb), qBlue(rgb), int(std::lround(v * ca))));
    for (int y = 0; y < dev.height(); ++y) {
        QRgb* row = reinterpret_cast<QRgb*>(img.scanLine(y));
        const uint8_t* a = alpha.data() + size_t(y) * size_t(dev.width());
        for (int x = 0; x < dev.width(); ++x)
            row[x] = lut[a[x]];
    }
    img.setDevicePixelRatio(dpr);
    p.drawImage(QPointF(dev.left() / dpr, dev.top() / dpr), img);
}

// A dense jagged series: more than one point per two device pixels and mostly non-flat steps (daily FX, rates
// with noise). Its stroke outline folds over itself inside pixels, where Qt's AA adds the coverage of the
// overlapping pieces; the union coverage of a supersampled mask matches Chromium (ENG_w3 §3). Step-like
// series (>= half flat steps, e.g. policy rates, unless packed >= 8 points per pixel) and sparse ones keep Qt's
// own AA, which matches better there (measured on build A, ENG_w3 §3). The wave 3 cost guard (Qt AA for zigzags
// travelling > 20 x the plot width) is gone: the union mask costs milliseconds for those too (ENG2 w4).
bool wdcPaint_isDense(const SeriesGeom& g, const QRectF& plot, qreal dpr) {
    int n = 0, flat = 0;
    const QPointF* last = nullptr;
    for (const QPointF& q : g.plotPts) {
        if (!std::isfinite(q.x()) || !std::isfinite(q.y()) || q.x() < plot.left() || q.x() > plot.right())
            continue;
        ++n;
        if (last)
            flat += q.y() == last->y();
        last = &q;
    }
    const double devW = std::max(1.0, plot.width() * dpr), perPx = n / devW;
    // >= 8 points per pixel, or more than one non-flat step per pixel (a step-like daily rate over 30 years, 1.6
    // per pixel; every default-window series stays below 0.5): folds even with flat runs.
    return perPx > 0.5 && (2 * flat < n || perPx > 8 || std::max(0, n - 1 - flat) > devW);
}

QColor wdcPaint_alpha(QColor c, double opacity) {
    c.setAlphaF(float(c.alphaF() * opacity));
    return c;
}

// Data sign per sorted point (PreparedSeries order); the builder sorts already, keep a guard.
std::vector<double> wdcPaint_sortedY(const SeriesData* d) {
    std::vector<double> y;
    if (!d)
        return y;
    std::vector<size_t> idx(d->pts.size());
    std::iota(idx.begin(), idx.end(), size_t(0));
    std::stable_sort(idx.begin(), idx.end(), [d](size_t a, size_t b) { return d->pts[a].x() < d->pts[b].x(); });
    for (size_t i : idx)
        y.push_back(d->pts[i].y());
    return y;
}

QPainterPath wdcPaint_symbol(const QString& symbol, const QRectF& r) {
    QPainterPath p;
    const double x = r.x(), y = r.y(), w = r.width(), h = r.height();
    if (symbol == QLatin1String("diamond")) {
        p.moveTo(x + w / 2, y);
        p.lineTo(x + w, y + h / 2);
        p.lineTo(x + w / 2, y + h);
        p.lineTo(x, y + h / 2);
    } else if (symbol == QLatin1String("square")) {
        p.addRect(r);
        return p;
    } else if (symbol == QLatin1String("triangle")) {
        p.moveTo(x + w / 2, y);
        p.lineTo(x + w, y + h);
        p.lineTo(x, y + h);
    } else if (symbol == QLatin1String("triangle-down")) {
        p.moveTo(x, y);
        p.lineTo(x + w, y);
        p.lineTo(x + w / 2, y + h);
    } else {
        p.addEllipse(r);
        return p;
    }
    p.closeSubpath();
    return p;
}

QColor wdcPaint_pointColor(const SeriesRef& ref, const std::vector<double>& ys, size_t i) {
    return (ref.negativeColor.has_value() && i < ys.size() && ys[i] < 0) ? *ref.negativeColor : ref.color;
}

// Series group part (clipped to the plot box by the caller): area, graph (+ shadow), columns.
void wdcPaint_series(QPainter& p, const SeriesGeom& g, const ChartInput& in, const QRectF& plot,
                     const std::vector<double>& ys) {
    const SeriesRef& ref = *in.refs[size_t(g.refIndex)];
    const ChartSpec& spec = *in.spec;
    const QColor neg = ref.negativeColor.value_or(ref.color);
    const QColor zoneColor[2] = {neg, ref.color};
    const bool shadow = ref.type == SeriesType::Spline;           // area/areaspline: shadow false
    p.setPen(Qt::NoPen);
    if (!g.area.isEmpty()) {
        if (g.zoneAreas.size() == 2) {
            for (int k = 0; k < 2; ++k) {
                p.save();
                p.setClipPath(g.zoneAreas[size_t(k)], Qt::IntersectClip);
                p.fillPath(g.area, wdcPaint_alpha(zoneColor[k], spec.fillOpacity));
                p.restore();
            }
        } else {
            p.fillPath(g.area, wdcPaint_alpha(ref.color, spec.fillOpacity));
        }
    }
    if (!g.graph.isEmpty() && ref.lineWidth > 0) {
        const int zones = g.zoneGraphs.size() == 2 ? 2 : 1;
        const qreal dpr = p.device() ? p.device()->devicePixelRatioF() : 1.0;
        // Pens up to 1 device px go through Qt's cosmetic line stroker, whose AA is per segment: no merging there.
        const QPainterPath raw = wdcPaint_strokeShape(p, g.graph, ref.lineWidth, ref.dashStyle);
        const QPainterPath shape = ref.lineWidth * dpr > 1 ? hcint::mergeFlat(raw) : raw;
        const QPen basePen = wdcPaint_pen(ref.color, ref.lineWidth);
        const bool dense = wdcPaint_isDense(g, plot, dpr);
        // One device alpha serves the shadow (blurred) and, for a dense series, the stroke itself.
        QRect dev = shadow ? wdcPaint_shadowRect(shape, basePen, plot, dpr) : QRect();
        if (!shadow && dense) {
            const QRectF b = shape.boundingRect().adjusted(-ref.lineWidth * 4, -ref.lineWidth * 4, ref.lineWidth * 4,
                                                           ref.lineWidth * 4).intersected(plot.adjusted(-1, -1, 1, 1));
            if (!b.isEmpty())
                dev = QRect(int(std::floor(b.left() * dpr)), int(std::floor(b.top() * dpr)),
                            int(std::ceil(b.width() * dpr)) + 2, int(std::ceil(b.height() * dpr)) + 2);
        }
        Alpha alpha;
        if (!dev.isEmpty())
            alpha = dense ? wdcPaint_unionAlpha(shape, ref.lineWidth, dev, dpr) : wdcPaint_strokeAlpha(shape, basePen, dev, dpr);
        const QImage shadowImg = shadow && !alpha.empty() ? wdcPaint_shadowImage(alpha, dev, dpr) : QImage();
        for (int k = 0; k < zones; ++k) {
            const QColor c = zones == 2 ? zoneColor[k] : ref.color;
            const QPen pen = wdcPaint_pen(c, ref.lineWidth);
            p.save();
            if (zones == 2)
                p.setClipPath(g.zoneGraphs[size_t(k)], Qt::IntersectClip);
            if (!shadowImg.isNull())
                wdcPaint_drawShadow(p, shadowImg, dev, dpr);
            if (dense && !alpha.empty())
                wdcPaint_fillAlpha(p, alpha, dev, dpr, c);
            else
                wdcPaint_strokeStrips(p, shape, pen);
            p.restore();
        }
    }
    for (size_t i = 0; i < g.columns.size(); ++i)
        if (!g.columns[i].isEmpty())
            p.fillPath(g.columns[i], wdcPaint_pointColor(ref, ys, i));
}

// Marker group: same zIndex as the series group, drawn right after it, no clip-path (only points inside
// the plot have a marker). The caller's own clip (the card) still applies.
void wdcPaint_markers(QPainter& p, const SeriesGeom& g, const ChartInput& in, const std::vector<double>& ys) {
    const SeriesRef& ref = *in.refs[size_t(g.refIndex)];
    p.setPen(Qt::NoPen);
    for (size_t i = 0; i < g.markers.size(); ++i)
        if (!g.markers[i].isNull())
            p.fillPath(wdcPaint_symbol(g.symbol, g.markers[i]), wdcPaint_pointColor(ref, ys, i));
}

void wdcPaint_text(QPainter& p, const QFont& font, const QString& text, QPointF pos, bool middle) {
    if (text.isEmpty())
        return;
    double x = pos.x();
    if (middle)
        x -= QFontMetricsF(font).horizontalAdvance(text) / 2;
    p.drawText(QPointF(x, pos.y()), text);                        // SVG text y is the baseline
}

} // namespace

namespace hcint {
// Exposed for tests (T19): SVG stroke-dasharray in px of a Highcharts dashStyle, empty = solid.
std::vector<double> dashArray(const QString& dashStyle, double strokeWidth) {
    return wdcPaint_dashArray(dashStyle, strokeWidth);
}
} // namespace hcint

void paintChart(QPainter& p, const ChartModel& m, const ChartInput& in) {
    if (!in.spec || m.plotBox.isEmpty())
        return;
    const ChartSpec& spec = *in.spec;
    const QRectF plot = m.plotBox;
    p.save();
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    p.setBrush(Qt::NoBrush);

    // z1: Y grid lines, crispLine width 1 (HS:13405-13415), one set per axis with data.
    const double cHeight = in.size.height() > 0 ? in.size.height() : plot.bottom();
    const double transB = (cHeight - plot.height()) - plot.top();       // yAxis.bottom
    for (size_t k = 0; k < m.y.size() && k < spec.yAxes.size(); ++k) {
        const AxisModel& ax = m.y[k];
        if (!ax.hasData)
            continue;
        const YAxisSpec& ys = spec.yAxes[k];
        const QPen pen = wdcPaint_pen(ys.gridColor, 1);
        for (const Tick& t : ax.ticks) {
            if (!std::isfinite(t.value))
                continue;
            // getPlotLinePath (HS:19552-19600): y = cHeight - translate(v) - transB, then crispLine width 1
            const double tv = std::clamp(hcmath::correctFloat((t.value - ax.min) * ax.transA + ax.minPixelPadding),
                                         -1e9, 1e9);
            const double y = hcmath::crisp((cHeight - tv) - transB, 1);
            QPainterPath line;
            line.moveTo(plot.left(), y);
            line.lineTo(plot.right(), y);
            p.strokePath(wdcPaint_strokeShape(p, line, 1, ys.gridDash), pen);
        }
    }

    // z3: series group, clipped to the plot box, stable order by zIndex.
    std::vector<const SeriesGeom*> order;
    for (const SeriesGeom& g : m.series)
        if (g.refIndex >= 0 && size_t(g.refIndex) < in.refs.size() && in.refs[size_t(g.refIndex)] &&
            (size_t(g.refIndex) >= in.visible.size() || in.visible[size_t(g.refIndex)]))
            order.push_back(&g);
    std::stable_sort(order.begin(), order.end(), [&](const SeriesGeom* a, const SeriesGeom* b) {
        return in.refs[size_t(a->refIndex)]->zIndex < in.refs[size_t(b->refIndex)]->zIndex;
    });
    for (const SeriesGeom* g : order) {          // SeriesGeom is in chart coordinates (B_internal_api 1.1)
        const SeriesRef& ref = *in.refs[size_t(g->refIndex)];
        std::vector<double> ys;                   // point colour = zone of the data sign (getZone)
        if (ref.negativeColor.has_value() && (!g->columns.empty() || !g->markers.empty()))
            ys = wdcPaint_sortedY(in.data.size() > size_t(g->refIndex) ? in.data[size_t(g->refIndex)] : nullptr);
        p.save();
        p.setClipRect(plot, Qt::IntersectClip);   // keep the caller's clip
        wdcPaint_series(p, *g, in, plot, ys);
        p.restore();
        if (!g->markers.empty()) {
            p.save();
            wdcPaint_markers(p, *g, in, ys);
            p.restore();
        }
    }

    // z7: axis labels.
    p.setPen(kLabelColor);
    const QFont xFont = wdcPaint_font(kXLabelPx);
    p.setFont(xFont);
    for (const Tick& t : m.x.ticks)
        if (t.visible)
            wdcPaint_text(p, xFont, t.text, t.labelPos, true);
    for (size_t k = 0; k < m.y.size() && k < spec.yAxes.size(); ++k) {
        if (!m.y[k].hasData)
            continue;
        const QFont yFont = wdcPaint_font(in.expanded ? kExpandedYLabelPx : spec.yAxes[k].labelPx);
        p.setFont(yFont);
        for (const Tick& t : m.y[k].ticks)
            if (t.visible)
                wdcPaint_text(p, yFont, t.text, t.labelPos, false);
    }
    p.restore();
}

} // namespace fincept::screens::wdc
