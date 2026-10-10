// WdcTooltip.cpp, package F: hitTest, tooltip block, crosshair, hover state painting, controller.
// Sources and Highcharts line numbers: see WdcTooltip.h. Every SeriesGeom field (graph, area, columns, markers,
// plotPts) is in CHART coordinates (B_internal_api 1.1); Highcharts' plotX/plotY are those minus plotBox.topLeft().
#include "WdcTooltip.h"

#include "WdcHcMath.h"
#include "WdcHcText.h"
#include "WdcTheme_p.h"

#include <QImage>
#include <QPaintDevice>
#include <QPainter>

#include <algorithm>
#include <cmath>
#include <numeric>

namespace fincept::screens::wdc {

namespace hcint {
std::vector<double> dashArray(const QString& dashStyle, double strokeWidth);   // WdcHcPaint.cpp (package C)
}
namespace th = theme;

namespace {

constexpr double kSnap = 10;                                  // tooltip.snap, mouse (HS:6985)
constexpr double kHaloSize = 10, kHaloOpacity = 0.25;         // states.hover.halo (HS:30829)
constexpr double kRadiusPlus = 2, kMarkerLineWidthPlus = 1;   // marker.states.hover (HS:29917, 29928)
constexpr double kLineWidthPlus = 1;                          // states.hover.lineWidthPlus (HS:30791)
constexpr double kInactiveOpacity = 0.2;                      // states.inactive.opacity (HS:30887)
constexpr double kColumnBrightness = 0.1;                     // column states.hover.brightness (HS:42261)
constexpr double kTipPx = 12, kTipPadX = 12.8, kTipPadY = 8, kTipDot = 11.2, kTipRadius = 6;   // DESIGN §16 C5
constexpr double kXLabelPx = 11, kXLabelPad = 6, kXLabelRadius = 4;   // xAxis.crosshair.label (CAP)
constexpr double kArrow = 6, kArrowHalf = 6;                  // callout arrowLength, halfDistance (HS:12113)
const QColor kTipHeaderBg = QColor::fromRgbF(220 / 255.0, 220 / 255.0, 220 / 255.0, 0.7);
const QColor kTipRowBg = QColor::fromRgbF(10 / 255.0, 10 / 255.0, 10 / 255.0, 0.6);
const QColor kTipShadow = QColor::fromRgbF(166 / 255.0, 176 / 255.0, 195 / 255.0, 0.24);

bool wdcTip_refOk(const ChartInput& in, int r) { return r >= 0 && size_t(r) < in.refs.size() && in.refs[size_t(r)]; }
bool wdcTip_visible(const ChartInput& in, int r) { return size_t(r) >= in.visible.size() || in.visible[size_t(r)]; }
bool wdcTip_finite(QPointF p) { return std::isfinite(p.x()) && std::isfinite(p.y()); }
bool wdcTip_inside(QPointF p, QSizeF s) { return p.x() >= 0 && p.x() <= s.width() && p.y() >= 0 && p.y() <= s.height(); }

const SeriesGeom* wdcTip_geom(const ChartModel& m, int refIndex) {
    for (const SeriesGeom& g : m.series) if (g.refIndex == refIndex) return &g;
    return nullptr;
}

// Highcharts series.index: rank of (si, refIndex), as the builder of package C (hcIndex).
int wdcTip_hcIndex(const ChartInput& in, int r) {
    int rank = 0;
    const SeriesRef* self = in.refs[size_t(r)];
    for (size_t j = 0; j < in.refs.size(); ++j)
        if (in.refs[j] && (in.refs[j]->si < self->si || (in.refs[j]->si == self->si && int(j) < r))) ++rank;
    return rank;
}

// DOM order of the series groups: zIndex, then insertion (series index). true when a is drawn above b.
bool wdcTip_above(const ChartInput& in, int a, int b) {
    const int za = in.refs[size_t(a)]->zIndex, zb = in.refs[size_t(b)]->zIndex;
    return za != zb ? za > zb : wdcTip_hcIndex(in, a) > wdcTip_hcIndex(in, b);
}

// plotPts follow the data sorted by x (stable); the builder already sorts, this maps back when it did not.
int wdcTip_dataIndex(const SeriesData* d, int sorted) {
    if (!d || sorted < 0 || size_t(sorted) >= d->pts.size()) return -1;
    const auto lt = [](const QPointF& a, const QPointF& b) { return a.x() < b.x(); };
    if (std::is_sorted(d->pts.begin(), d->pts.end(), lt)) return sorted;
    std::vector<int> idx(d->pts.size());
    std::iota(idx.begin(), idx.end(), 0);
    std::stable_sort(idx.begin(), idx.end(), [d](int a, int b) { return d->pts[size_t(a)].x() < d->pts[size_t(b)].x(); });
    return idx[size_t(sorted)];
}

double wdcTip_segDist2(QPointF p, QPointF a, QPointF b) {
    const QPointF ab = b - a, ap = p - a;
    const double len2 = QPointF::dotProduct(ab, ab);
    const double t = len2 > 0 ? std::clamp(QPointF::dotProduct(ap, ab) / len2, 0.0, 1.0) : 0.0;
    const QPointF d = p - (a + t * ab);
    return QPointF::dotProduct(d, d);
}

// Is `p` within `r` of the stroke centre line? (= inside a stroke of width 2r with round caps and joins)
bool wdcTip_pathNear(const QPainterPath& path, QPointF p, double r) {
    const double r2 = r * r;
    QPointF cur;
    const int n = path.elementCount();
    for (int i = 0; i < n; ++i) {
        const QPainterPath::Element e = path.elementAt(i);
        if (e.isMoveTo() || e.isLineTo()) {
            if (e.isLineTo() && wdcTip_segDist2(p, cur, e) <= r2) return true;
            cur = e;
            continue;
        }
        if (e.type == QPainterPath::CurveToElement && i + 2 < n) {
            const QPointF c1 = e, c2 = path.elementAt(i + 1), end = path.elementAt(i + 2);
            i += 2;
            const double minX = std::min({cur.x(), c1.x(), c2.x(), end.x()}) - r, maxX = std::max({cur.x(), c1.x(), c2.x(), end.x()}) + r;
            const double minY = std::min({cur.y(), c1.y(), c2.y(), end.y()}) - r, maxY = std::max({cur.y(), c1.y(), c2.y(), end.y()}) + r;
            if (p.x() >= minX && p.x() <= maxX && p.y() >= minY && p.y() <= maxY) {
                const double chord = QLineF(cur, c1).length() + QLineF(c1, c2).length() + QLineF(c2, end).length();
                const int k = std::clamp(int(std::ceil(chord / 2)), 1, 64);
                QPointF prev = cur;
                for (int s = 1; s <= k; ++s) {
                    const double t = double(s) / k, u = 1 - t;
                    const QPointF q = u * u * u * cur + 3 * u * u * t * c1 + 3 * u * t * t * c2 + t * t * t * end;
                    if (wdcTip_segDist2(p, prev, q) <= r2) return true;
                    prev = q;
                }
            }
            cur = end;
        }
    }
    return false;
}

QPainterPath wdcTip_symbol(const QString& symbol, const QRectF& r) {   // SVGRenderer symbols (HS:12020-12112)
    QPainterPath p;
    const double x = r.x(), y = r.y(), w = r.width(), h = r.height();
    if (symbol == QLatin1String("square")) { p.addRect(r); return p; }
    if (symbol == QLatin1String("diamond")) {
        p.moveTo(x + w / 2, y); p.lineTo(x + w, y + h / 2); p.lineTo(x + w / 2, y + h); p.lineTo(x, y + h / 2);
    } else if (symbol == QLatin1String("triangle")) {
        p.moveTo(x + w / 2, y); p.lineTo(x + w, y + h); p.lineTo(x, y + h);
    } else if (symbol == QLatin1String("triangle-down")) {
        p.moveTo(x, y); p.lineTo(x + w, y); p.lineTo(x + w / 2, y + h);
    } else {
        p.addEllipse(r);
    }
    if (symbol != QLatin1String("circle")) p.closeSubpath();
    return p;
}

// SVG hit testing counts the boundary of a filled shape as inside.
bool wdcTip_inFill(const QPainterPath& path, QPointF p) {
    constexpr double e = 1e-6;
    return path.contains(p) || path.intersects(QRectF(p.x() - e, p.y() - e, 2 * e, 2 * e));
}

bool wdcTip_markerHit(const SeriesGeom& g, QPointF rel) {
    for (const QRectF& r : g.markers)
        if (!r.isNull() && r.adjusted(-1e-6, -1e-6, 1e-6, 1e-6).contains(rel) && wdcTip_inFill(wdcTip_symbol(g.symbol, r), rel))
            return true;
    return false;
}

// KD search with compareX (findNearestPointBy 'x'): smallest |clientX - x|, ties to the higher index (HS:33652).
// Valid points: not null and, for line-type series, inside the plot (getValidPoints insideOnly, HS:32788).
int wdcTip_nearestX(const SeriesGeom& g, double x, const QRectF& plot) {
    int best = -1;
    double bestD = 0;
    for (size_t i = 0; i < g.plotPts.size(); ++i) {
        const QPointF q = g.plotPts[i];
        if (!wdcTip_finite(q) || !wdcTip_inside(q - plot.topLeft(), plot.size())) continue;
        const double d = std::fabs(x - q.x());
        if (best < 0 || d <= bestD) { best = int(i); bestD = d; }
    }
    return best;
}

std::optional<Hit> wdcTip_makeHit(const ChartModel& m, const ChartInput& in, const SeriesGeom& g, int i) {
    if (i < 0 || size_t(i) >= g.plotPts.size() || !wdcTip_finite(g.plotPts[size_t(i)])) return std::nullopt;
    const SeriesData* d = size_t(g.refIndex) < in.data.size() ? in.data[size_t(g.refIndex)] : nullptr;
    const int di = wdcTip_dataIndex(d, i);
    if (di < 0) return std::nullopt;
    const QPointF tv = processedPoint(&m, g.refIndex, i, g.plotPts.size()).value_or(d->pts[size_t(di)]);   // C21 group
    return Hit{g.refIndex, i, g.plotPts[size_t(i)], qint64(std::llround(tv.x())), tv.y()};
}

// tooltipPos x of a column = plotX + pointXOffset + barW / 2 (HS:42860), a constant offset for the whole series. The
// shapes keep only crisp edges, round(plotX + o) and round(plotX + o + barW): intersect the intervals that every column
// of the series gives for o and o + barW. Falls back to the crisp centre when the series is inconsistent.
double wdcTip_columnCentre(const SeriesGeom& g, int i) {
    double oLo = -INFINITY, oHi = INFINITY, eLo = -INFINITY, eHi = INFINITY;
    for (size_t k = 0; k < g.columns.size() && k < g.plotPts.size(); ++k) {
        if (g.columns[k].isEmpty() || !std::isfinite(g.plotPts[k].x())) continue;
        const QRectF b = g.columns[k].boundingRect();
        const double px = g.plotPts[k].x();
        oLo = std::max(oLo, b.left() - 0.5 - px);
        oHi = std::min(oHi, b.left() + 0.5 - px);
        eLo = std::max(eLo, b.right() - 0.5 - px);
        eHi = std::min(eHi, b.right() + 0.5 - px);
    }
    const QRectF own = g.columns[size_t(i)].boundingRect();
    if (!(oLo <= oHi && eLo <= eHi)) return own.center().x();
    return g.plotPts[size_t(i)].x() + ((oLo + oHi) / 2 + (eLo + eHi) / 2) / 2;
}

QColor wdcTip_pointColor(const SeriesRef& ref, double v) {   // Point.getZone: zones [{value 0, negativeColor}, {}]
    return (ref.negativeColor && v < 0) ? *ref.negativeColor : ref.color;
}

// ---- text measuring as Blink lays out the HTML tooltip (LayoutUnit = 1/64 device px) ----------------------------
struct WdcTipText {
    double dpr, s;
    TextMetrics tm;
    WdcTipText(double dprIn, MetricsProfile p)
        : dpr(p == MetricsProfile::WidataDpr18 ? 1.8 : (dprIn > 0 ? dprIn : 1.0)), s(64.0 * dpr),
          tm(TextMetrics::native(dpr)) {}
    double lu(double css) const { return std::floor(css * s + 1e-9) / s; }
    // WiData serves Inter 400/500 as Google Fonts unicode-range subsets: one shaping run per subset, so no kerning
    // across latin / precomposed Vietnamese letters (theme::webSubset, package D finding); 600 is the variable face.
    double exact(const QString& t, int weight) const {
        if (t.isEmpty()) return 0;
        if (weight != 400 && weight != 500) return tm.exactWidth(t, kTipPx, weight);
        double w = 0;
        int start = 0, cur = -1;
        for (int i = 0; i < t.size(); ++i) {
            const int k = th::webSubset(char32_t(t.at(i).unicode()));
            if (cur >= 0 && k != cur) { w += tm.exactWidth(t.mid(start, i - start), kTipPx, weight); start = i; }
            cur = k;
        }
        return w + tm.exactWidth(t.mid(start), kTipPx, weight);
    }
    double ceilLu(double css) const { return std::ceil(css * s - 1e-7) / s; }     // text fragment, rounded up
    double run(const QString& t, int weight) const { return ceilLu(exact(t, weight)); }
};

QPainterPath wdcTip_callout(double x, double y, double w, double h, double r, std::optional<QPointF> anchorLocal) {
    // SVGRenderer.symbols.callout (HS:12113-12175); connectors that collapse to a zero-area spike are omitted.
    QPainterPath p;
    r = std::min({r, w, h});
    const double safe = r + kArrowHalf;
    enum { None, Top, Bottom, Left, Right } arrow = None;
    double ax = 0, ay = 0;
    if (anchorLocal) {
        ax = anchorLocal->x();
        ay = anchorLocal->y();
        const bool inside = ax < w && ax > 0 && ay < h && ay > 0;
        if (!inside) {
            if (x + ax > w - safe) { if (ay > y + safe && ay < y + h - safe) arrow = Right; }
            else if (x + ax < safe) { if (ay > y + safe && ay < y + h - safe) arrow = Left; }
            else if (ay > h && ax < w - safe) arrow = Bottom;
            else if (ay < 0 && ax > safe) arrow = Top;
        }
    }
    p.moveTo(x + r, y);
    if (arrow == Top) { p.lineTo(ax - kArrowHalf, y); p.lineTo(ax, y - kArrow); p.lineTo(ax + kArrowHalf, y); }
    p.lineTo(x + w - r, y);
    p.arcTo(QRectF(x + w - 2 * r, y, 2 * r, 2 * r), 90, -90);
    if (arrow == Right) { p.lineTo(x + w, ay - kArrowHalf); p.lineTo(x + w + kArrow, ay); p.lineTo(x + w, ay + kArrowHalf); }
    p.lineTo(x + w, y + h - r);
    p.arcTo(QRectF(x + w - 2 * r, y + h - 2 * r, 2 * r, 2 * r), 0, -90);
    if (arrow == Bottom) { p.lineTo(ax + kArrowHalf, y + h); p.lineTo(ax, y + h + kArrow); p.lineTo(ax - kArrowHalf, y + h); }
    p.lineTo(x + r, y + h);
    p.arcTo(QRectF(x, y + h - 2 * r, 2 * r, 2 * r), 270, -90);
    if (arrow == Left) { p.lineTo(x, ay + kArrowHalf); p.lineTo(x - kArrow, ay); p.lineTo(x, ay - kArrowHalf); }
    p.lineTo(x, y + r);
    p.arcTo(QRectF(x, y, 2 * r, 2 * r), 180, -90);
    p.closeSubpath();
    return p;
}

// CSS box-shadow 0 1px 2px 0 rgba(166,176,195,.24) of the ul (blur 2 => Gaussian sigma 1), outside the box only.
// One cached image (tooltips change size often; an unbounded cache would grow without limit).
void wdcTip_shadow(QPainter& p, const QRectF& box, double dpr) {
    constexpr double ext = 4, dy = 1, sigma = 1;
    thread_local QSizeF cachedSize;
    thread_local double cachedDpr = 0;
    thread_local QImage cached;
    if (cachedSize != box.size() || cachedDpr != dpr || cached.isNull()) {
        const int w = int(std::ceil((box.width() + 2 * ext) * dpr)), h = int(std::ceil((box.height() + 2 * ext) * dpr));
        QImage mask(w, h, QImage::Format_Grayscale8);
        mask.fill(0);
        QPainter mp(&mask);
        mp.setRenderHint(QPainter::Antialiasing, true);
        mp.scale(dpr, dpr);
        QPainterPath rr;
        rr.addRoundedRect(QRectF(ext, ext + dy, box.width(), box.height()), kTipRadius, kTipRadius);
        mp.fillPath(rr, Qt::white);
        mp.end();
        const double sd = sigma * dpr;
        const int rad = int(std::ceil(3 * sd));
        std::vector<double> k(size_t(2 * rad + 1)), a(size_t(w) * size_t(h)), t(a.size());
        for (int i = -rad; i <= rad; ++i) k[size_t(i + rad)] = std::exp(-(i * i) / (2 * sd * sd));
        const double norm = std::accumulate(k.begin(), k.end(), 0.0);
        for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) a[size_t(y * w + x)] = mask.constScanLine(y)[x] / 255.0;
        auto pass = [&](const std::vector<double>& src, std::vector<double>& dst, int dx, int dyy) {   // separable
            for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) {
                double s = 0;
                for (int j = -rad; j <= rad; ++j) {
                    const int xx = x + j * dx, yy = y + j * dyy;
                    if (xx >= 0 && xx < w && yy >= 0 && yy < h) s += k[size_t(j + rad)] * src[size_t(yy * w + xx)];
                }
                dst[size_t(y * w + x)] = s / norm;
            }
        };
        pass(a, t, 1, 0);
        pass(t, a, 0, 1);
        cached = QImage(w, h, QImage::Format_ARGB32_Premultiplied);
        for (int y = 0; y < h; ++y) {
            QRgb* row = reinterpret_cast<QRgb*>(cached.scanLine(y));
            for (int x = 0; x < w; ++x) {
                const int al = int(std::lround(std::clamp(a[size_t(y * w + x)], 0.0, 1.0) * kTipShadow.alphaF() * 255));
                row[x] = qPremultiply(qRgba(kTipShadow.red(), kTipShadow.green(), kTipShadow.blue(), al));
            }
        }
        cached.setDevicePixelRatio(dpr);
        cachedSize = box.size();
        cachedDpr = dpr;
    }
    QPainterPath outside;
    outside.addRect(box.adjusted(-ext, -ext, ext, ext + dy));
    outside.addRoundedRect(box, kTipRadius, kTipRadius);
    outside.setFillRule(Qt::OddEvenFill);
    p.save();
    p.setClipPath(outside, Qt::IntersectClip);
    p.drawImage(QPointF(box.x() - ext, box.y() - ext), cached);
    p.restore();
}

} // namespace

// ---- hitTest -----------------------------------------------------------------------------------------------------------

std::optional<Hit> hitTest(const ChartModel& m, const ChartInput& in, QPointF pos) {
    if (!in.spec || m.plotBox.isEmpty() || m.series.empty()) return std::nullopt;
    const bool inPlot = wdcTip_inside(pos - m.plotBox.topLeft(), m.plotBox.size());
    // Element under the pointer, as the browser picks it: column shapes (direct touch) and line trackers, clipped to
    // the plot; markers, not clipped; area fills of non-sticky series are painted elements that catch the pointer
    // without being trackers (pointer-events auto unless stickyTracking, HS:41291). The topmost series group wins.
    const SeriesGeom* top = nullptr;
    int topPoint = -1;
    bool topBlocks = false;   // the topmost element is an area fill
    for (const SeriesGeom& g : m.series) {
        const int r = g.refIndex;
        if (!wdcTip_refOk(in, r) || !wdcTip_visible(in, r)) continue;
        const SeriesRef& ref = *in.refs[size_t(r)];
        int point = -1;
        bool blocks = false;
        if (ref.type == SeriesType::Column) {
            if (!inPlot) continue;
            for (size_t i = g.columns.size(); i-- > 0 && point < 0;)   // later shapes paint on top (dense columns overlap)
                if (!g.columns[i].isEmpty() && wdcTip_inFill(g.columns[i], pos)) point = int(i);
            if (point < 0) continue;
        } else {
            const bool onLine = inPlot && !g.graph.isEmpty() && wdcTip_pathNear(g.graph, pos, (ref.lineWidth + 2 * kSnap) / 2);
            if (!onLine && !wdcTip_markerHit(g, pos)) {
                if (in.spec->sticky || !inPlot || g.area.isEmpty() || !wdcTip_inFill(g.area, pos)) continue;
                blocks = true;   // the tracker of this series is above its own area, so only a miss of both lands here
            }
        }
        if (!top || wdcTip_above(in, r, top->refIndex)) { top = &g; topPoint = point; topBlocks = blocks; }
    }
    if (topBlocks) return std::nullopt;   // an area fill on top: no tracker under the pointer (aio)
    if (top && topPoint >= 0) return wdcTip_makeHit(m, in, *top, topPoint);   // column: the point itself
    // k-d search on the event coordinates: Chromium MouseEvent pageX/Y are whole px (FACT probe 04/10: y 15.6 misses the
    // plot top 16), Pointer.normalize rounds again (HS:27194); trackers (DOM hit test) use the raw position
    const QPointF kd(std::floor(pos.x()), std::floor(pos.y()));
    if (!in.spec->sticky) return top ? wdcTip_makeHit(m, in, *top, wdcTip_nearestX(*top, kd.x(), m.plotBox)) : std::nullopt;
    if (!top && !wdcTip_inside(kd - m.plotBox.topLeft(), m.plotBox.size())) return std::nullopt;
    // stickyTracking: every visible line-type series, nearest in x each, the closest in 2D wins (HS:26840-26876)
    const SeriesGeom* best = nullptr;
    int bestI = -1;
    double bestD = 0;   // 2D distance (KD dist), HS:33671
    for (const SeriesGeom& g : m.series) {
        const int r = g.refIndex;
        if (!wdcTip_refOk(in, r) || !wdcTip_visible(in, r) || in.refs[size_t(r)]->type == SeriesType::Column) continue;
        const int i = wdcTip_nearestX(g, kd.x(), m.plotBox);
        if (i < 0) continue;
        const double d = QLineF(kd, g.plotPts[size_t(i)]).length();
        if (!best || d < bestD || (d == bestD && wdcTip_above(in, r, best->refIndex))) { best = &g; bestI = i; bestD = d; }
    }
    return best ? wdcTip_makeHit(m, in, *best, bestI) : std::nullopt;
}

std::optional<HoverAnchor> hoverAnchor(const ChartModel& m, const ChartInput& in, const Hit& h) {
    const SeriesGeom* g = wdcTip_geom(m, h.refIndex);
    if (!g || !wdcTip_refOk(in, h.refIndex) || h.pointIndex < 0 || size_t(h.pointIndex) >= g->plotPts.size()) return std::nullopt;
    const QPointF pp = g->plotPts[size_t(h.pointIndex)];
    if (!wdcTip_finite(pp)) return std::nullopt;
    const SeriesRef& ref = *in.refs[size_t(h.refIndex)];
    HoverAnchor a;
    a.column = ref.type == SeriesType::Column;
    a.negative = h.v < 0;                         // point.negative, threshold 0
    a.color = wdcTip_pointColor(ref, h.v);
    QPointF p = pp - m.plotBox.topLeft();   // plotX, plotY
    if (a.column && size_t(h.pointIndex) < g->columns.size() && !g->columns[size_t(h.pointIndex)].isEmpty()) {
        // tooltipPos = [barX + barW / 2, clamp(plotY, 0, len)] (HS:42860)
        p = QPointF(wdcTip_columnCentre(*g, h.pointIndex) - m.plotBox.left(), std::clamp(p.y(), 0.0, m.plotBox.height()));
    }
    a.anchor = QPointF(hcmath::jsRound(p.x()), hcmath::jsRound(p.y()));   // getAnchor: map(Math.round)
    return a;
}

// ---- tooltip block -----------------------------------------------------------------------------------------------------

TooltipContent tooltipContent(const ChartInput& in, const Hit& h, const QColor& dot) {
    TooltipContent c;
    if (!wdcTip_refOk(in, h.refIndex)) return c;
    const SeriesRef& ref = *in.refs[size_t(h.refIndex)];
    const SeriesData* d = size_t(h.refIndex) < in.data.size() ? in.data[size_t(h.refIndex)] : nullptr;
    const QString kind = ref.dateType.trimmed().toLower(), f = d ? d->freq.trimmed().toUpper() : QString();
    const double t = double(h.t);
    if (kind == QLatin1String("thang") || (kind.isEmpty() && (f == QLatin1String("M") || f == QLatin1String("YTD"))))
        c.header = hctime::dateFormat(QStringLiteral("%m/%Y"), t);
    else if (kind == QLatin1String("quy") || (kind.isEmpty() && f == QLatin1String("Q"))) {
        int y = 0, mo = 0, x = 0;   // toParts month is 0-based
        hctime::toParts(t, y, mo, x, x, x, x, x, x);
        c.header = QStringLiteral("Q%1/%2").arg(mo / 3 + 1).arg(y);
    } else if (kind == QLatin1String("nam") || (kind.isEmpty() && f == QLatin1String("Y")))
        c.header = hctime::dateFormat(QStringLiteral("%Y"), t);
    else
        c.header = hctime::dateFormat(QStringLiteral("%d/%m/%Y"), t);
    c.dot = dot;
    c.name = th::displayName(ref.nameRaw);
    c.value = hcfmt::numberFormat(h.v, 2);
    if (!ref.unit.isEmpty()) c.unit = QLatin1Char('(') + ref.unit + QLatin1Char(')');
    const QString tier = pointTier(d, h.t).trimmed().toUpper();   // tier_spans of the point (WdcRange.h)
    if (tier == QLatin1String("EST") || tier == QLatin1String("UNVERIFIED"))   // DESIGN §8.4
        c.unit += (c.unit.isEmpty() ? QString() : QStringLiteral(" ")) + QStringLiteral("· ") + tier;
    c.unit = compareTooltipUnit(c.unit, d, h.t);   // "So sánh biến động": + "(gốc <raw> <unit>)" (WdcRange.h)
    return c;
}

TooltipLayout layoutTooltip(const TooltipContent& c, double maxWidth, double dpr, MetricsProfile profile) {
    const WdcTipText tx(dpr, profile);
    TooltipLayout L;
    const double padX = tx.lu(kTipPadX), padY = tx.lu(kTipPadY), dotW = tx.lu(kTipDot);
    const double lineH = th::blinkNormalLineH(kTipPx, tx.dpr), asc = th::blinkAscent(kTipPx, tx.dpr);
    // Inline runs as Blink measures the capture HTML: "<b>MM/YYYY </b>", "&emsp; ", name, ": ", "<b>value </b>",
    // "<span>(unit) </span>"; a collapsible space that ends the line is not counted (b of the header, the unit span,
    // the value when there is no unit).
    const double headerW = tx.run(c.header, 600);
    const double gapW = tx.run(QString(QChar(0x2003)) + QLatin1Char(' '), 400);   // "&emsp;" + collapsed newline
    // Blink shapes consecutive text of one font as a single run across inline boxes: the name span and the ": " that
    // follows are kerned together (e.g. "Y:" -0.75 px), so the span is measured in that context.
    const double colonW = tx.run(QStringLiteral(": "), 400);
    const double nameW = tx.ceilLu(tx.exact(c.name + QStringLiteral(": "), 400) - tx.exact(QStringLiteral(": "), 400));
    const double valueW = tx.run(c.unit.isEmpty() ? c.value : c.value + QLatin1Char(' '), 600);
    const double unitW = c.unit.isEmpty() ? 0 : tx.run(c.unit, 400);
    const double fixedW = dotW + gapW + colonW + valueW + unitW;
    const double natural = std::max(headerW, fixedW + nameW) + 2 * padX;
    L.wrapped = maxWidth > 0 && hcmath::jsRound(natural) > maxWidth;   // offsetWidth > textWidth (HS:14907)
    const double W = L.wrapped ? maxWidth : natural;
    double nameCol = nameW;
    QStringList lines;
    if (!L.wrapped) {
        lines << c.name;
    } else {
        nameCol = std::max(0.0, W - 2 * padX - fixedW);
        QString line;
        for (const QString& word : c.name.split(QLatin1Char(' '), Qt::SkipEmptyParts)) {
            const QString cand = line.isEmpty() ? word : line + QLatin1Char(' ') + word;
            if (!line.isEmpty() && tx.run(cand, 400) > nameCol) { lines << line; line = word; }
            else line = cand;
        }
        if (!line.isEmpty() || lines.isEmpty()) lines << line;
    }
    L.headerH = 2 * padY + lineH;
    L.rowH = 2 * padY + lineH * lines.size();
    L.size = QSizeF(W, L.headerH + L.rowH);
    L.box = QSize(int(hcmath::jsRound(L.size.width())), int(hcmath::jsRound(L.size.height())));
    L.headerText = QPointF(padX, padY + asc);
    const double base = L.headerH + padY + asc;
    L.dot = QRectF(padX, base - dotW, dotW, dotW);   // empty inline-block: bottom on the baseline
    const double x0 = padX + dotW + gapW;
    for (int i = 0; i < lines.size(); ++i) L.nameLines.push_back({QPointF(x0, base + i * lineH), lines[i]});
    L.colon = QPointF(x0 + nameCol, base);
    L.value = QPointF(L.colon.x() + colonW, base);
    L.unit = QPointF(L.value.x() + valueW, base);
    return L;
}

QPointF tooltipPosition(QSize box, QPointF anchor, const QRectF& plotBox, QSizeF chartSize, bool negative,
                        double distance) {
    struct Dim { int which; double outer, inner, point, min, max; };   // which: 0 x, 1 y
    double ret[2] = {0, 0};
    const bool preferFarSide = negative;                     // !inverted === flipped (HS:24238)
    Dim first{1, chartSize.height(), double(box.height()), anchor.y() + plotBox.top(), plotBox.top(), plotBox.bottom()};
    Dim second{0, chartSize.width(), double(box.width()), anchor.x() + plotBox.left(), plotBox.left(), plotBox.right()};
    auto firstDimension = [&](const Dim& d) {
        const bool roomLeft = d.inner < d.point - distance, roomRight = d.point + distance + d.inner < d.outer;
        const double alignedLeft = d.point - distance - d.inner, alignedRight = d.point + distance;
        if (preferFarSide && roomRight) ret[d.which] = alignedRight;
        else if (!preferFarSide && roomLeft) ret[d.which] = alignedLeft;
        else if (roomLeft) ret[d.which] = std::min(d.max - d.inner, alignedLeft);
        else if (roomRight) ret[d.which] = std::max(d.min, alignedRight);
        else { ret[d.which] = 0; return false; }
        return true;
    };
    auto secondDimension = [&](const Dim& d) {
        if (d.point < distance || d.point > d.outer - distance) return false;
        if (d.point < d.inner / 2) ret[d.which] = 1;
        else if (d.point > d.outer - d.inner / 2) ret[d.which] = d.outer - d.inner - 2;
        else ret[d.which] = d.point - d.inner / 2;
        return true;
    };
    bool swapped = false;
    std::function<void()> run = [&] {
        if (firstDimension(first)) {
            if (!secondDimension(second) && !swapped) { std::swap(first, second); swapped = true; run(); }
        } else if (!swapped) { std::swap(first, second); swapped = true; run(); }
        else { ret[0] = ret[1] = 0; }
    };
    run();
    return QPointF(hcmath::jsRound(ret[0]), hcmath::jsRound(ret[1]));
}

QPainterPath tooltipCalloutPath(QSize box, QPointF topLeft, QPointF anchorChart) {
    const QPointF local(hcmath::jsRound(anchorChart.x()) - topLeft.x(), hcmath::jsRound(anchorChart.y()) - topLeft.y());
    return wdcTip_callout(0, 0, box.width(), box.height(), kTipRadius, local).translated(topLeft);
}

std::optional<TooltipFrame> tooltipFrame(const ChartModel& m, const ChartInput& in, const Hit& h, double dpr) {
    const std::optional<HoverAnchor> a = hoverAnchor(m, in, h);
    if (!a || !in.spec) return std::nullopt;
    TooltipFrame f;
    f.content = tooltipContent(in, h, a->color);
    const std::array<double, 4>& sp = in.spec->spacing;   // [top, right, bottom, left]
    f.layout = layoutTooltip(f.content, in.size.width() - sp[1] - sp[3], dpr, in.profile);
    // tooltip.distance: 16, columns 6 (plotOptions.column.tooltip.distance, HS:42305)
    f.topLeft = tooltipPosition(f.layout.box, a->anchor, m.plotBox, in.size, a->negative, a->column ? 6 : 16);
    return f;
}

void paintTooltip(QPainter& p, const TooltipFrame& f, double dpr) {
    const TooltipLayout& L = f.layout;
    const QRectF box(f.topLeft, L.size);
    p.save();
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    wdcTip_shadow(p, box, dpr);
    QPainterPath clip;
    clip.addRoundedRect(box, kTipRadius, kTipRadius);   // ul: border-radius 6, overflow hidden
    p.setClipPath(clip, Qt::IntersectClip);
    p.fillRect(QRectF(box.x(), box.y(), box.width(), L.headerH), kTipHeaderBg);
    p.fillRect(QRectF(box.x(), box.y() + L.headerH, box.width(), L.rowH), kTipRowBg);
    p.translate(f.topLeft);
    p.setPen(th::color(th::kTextPrimary));
    p.setFont(th::font(kTipPx, 600));
    p.drawText(L.headerText, f.content.header);
    p.setPen(Qt::NoPen);
    p.setBrush(f.content.dot);
    p.drawEllipse(L.dot);
    p.setPen(Qt::white);
    p.setFont(th::font(kTipPx, 400));
    for (const auto& line : L.nameLines) th::drawWebText(p, line.first, line.second, 400);
    p.drawText(L.colon, QStringLiteral(":"));
    if (!f.content.unit.isEmpty()) th::drawWebText(p, L.unit, f.content.unit, 400);
    p.setFont(th::font(kTipPx, 600));
    p.drawText(L.value, f.content.value);
    p.restore();
}

// ---- crosshair -----------------------------------------------------------------------------------------------------------

CrosshairGeom crosshairGeometry(const ChartModel& m, const ChartInput& in, const Hit& h, double dpr,
                                MetricsProfile profile, TextMetrics* labelCache) {
    CrosshairGeom c;
    const SeriesGeom* g = wdcTip_geom(m, h.refIndex);
    if (!g || h.pointIndex < 0 || size_t(h.pointIndex) >= g->plotPts.size() || !wdcTip_finite(g->plotPts[size_t(h.pointIndex)]))
        return c;
    const QPointF pp = g->plotPts[size_t(h.pointIndex)];
    const QRectF plot = m.plotBox;
    const double xc = pp.x(), yc = pp.y();   // getPlotLinePath: plotX + transB (plotLeft), plotTop + plotY
    const double xl = in.spec && in.spec->isStock ? hcmath::jsRound(xc) : xc;   // stock: rounded first (HS:55463)
    if (xl >= plot.left() && xl <= plot.right()) {
        const double x = hcmath::crisp(xl, 1);
        c.showX = true;
        c.xLine = QLineF(x, plot.top(), x, plot.bottom());
    }
    if (yc >= plot.top() && yc <= plot.bottom()) {
        const double y = hcmath::crisp(yc, 1);
        c.showY = true;
        c.yLine = QLineF(plot.left(), y, plot.right(), y);
    }
    // X label (Highstock onAxisAfterDrawCrosshair): centred on the point, kept inside [plotLeft, plotRight]
    TextMetrics fresh = profile == MetricsProfile::WidataDpr18 ? TextMetrics::widataDpr18() : TextMetrics::native(dpr);
    TextMetrics& tm = labelCache ? *labelCache : fresh;
    c.labelText = hctime::dateFormat(QStringLiteral("%d/%m/%Y"), double(h.t));
    const QSizeF bb = tm.bbox(c.labelText, kXLabelPx, 400);    // cached by digit pattern
    const double tw = bb.width(), th_ = bb.height();
    const double pw = tw + 2 * kXLabelPad;                  // getPaddedWidth, unrounded
    const double bw = hcmath::jsRound(pw), bh = hcmath::jsRound(th_ + 2 * kXLabelPad);
    const double posx = xc, posy = plot.bottom();
    const double tx0 = hcmath::jsRound(posx - pw / 2);
    double offset = 0;
    if (tx0 < plot.left()) offset = plot.left() - tx0;
    if (tx0 + pw >= plot.right()) offset = -(tx0 + pw - plot.right());
    const double tx = hcmath::jsRound(std::max(0.0, posx + offset) - pw / 2), ty = hcmath::jsRound(std::max(0.0, posy));
    c.labelBox = QRectF(tx, ty, bw, bh);
    const QPointF anchorLocal(hcmath::jsRound(posx) - tx, 0 - ty);   // anchorY = 0 (axis not opposite)
    c.labelArrow = anchorLocal.x() > kArrowHalf + kXLabelRadius && anchorLocal.x() <= bw - (kArrowHalf + kXLabelRadius);
    c.labelPath = wdcTip_callout(0, 0, bw, bh, kXLabelRadius, anchorLocal).translated(tx, ty);
    const double baselineOffset = kXLabelPad + std::min(tm.hc(kXLabelPx).b, th_);
    // text-anchor middle at x = paddedWidth / 2: the glyphs are centred on their own width, not on the cached one
    c.labelTextPos = QPointF(tx + pw / 2 - fresh.width(c.labelText, kXLabelPx, 400) / 2, ty + baselineOffset);
    c.showLabel = wdcTip_inside(pp - plot.topLeft(), plot.size());   // series.isPointInside(point)
    return c;
}

void paintCrosshairLines(QPainter& p, const CrosshairGeom& g) {
    if (!g.showX && !g.showY) return;
    QPen pen(th::color(th::kCrosshair), 1, Qt::CustomDashLine, Qt::FlatCap);
    pen.setDashPattern({8, 3, 1, 3});                       // LongDashDot x width 1 (HS:10516)
    p.save();
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setPen(pen);
    if (g.showX) p.drawLine(g.xLine);
    if (g.showY) p.drawLine(g.yLine);
    p.restore();
}

void paintCrosshairLabel(QPainter& p, const CrosshairGeom& g) {
    if (!g.showLabel) return;
    p.save();
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    p.fillPath(g.labelPath, th::color(th::kCrosshairLabel));
    p.setPen(Qt::white);
    p.setFont(th::font(kXLabelPx, 400));
    p.drawText(g.labelTextPos, g.labelText);
    p.restore();
}

// ---- painting with the hover state --------------------------------------------------------------------------------------
namespace {

// The hovered graph gets lineWidth + 1. Solid lines: paintChart with the wider ref (graph and shadow exact).
// Dashed lines: SVG keeps the dash array in px of the normal width, so paint normally and stroke the graph again.
void wdcTip_paintSeries(QPainter& p, const ChartModel& one, const ChartInput& in, const SeriesGeom& g, bool active) {
    const SeriesRef& ref = *in.refs[size_t(g.refIndex)];
    if (!active || ref.type == SeriesType::Column || !(ref.lineWidth > 0) || g.graph.isEmpty()) {
        paintChart(p, one, in);
        return;
    }
    const std::vector<double> dash = hcint::dashArray(ref.dashStyle, ref.lineWidth);
    if (dash.empty()) {
        SeriesRef wide = ref;
        wide.lineWidth = ref.lineWidth + kLineWidthPlus;
        ChartInput in2 = in;
        in2.refs[size_t(g.refIndex)] = &wide;
        paintChart(p, one, in2);
        return;
    }
    paintChart(p, one, in);
    const double w = ref.lineWidth + kLineWidthPlus;
    const QColor zone[2] = {ref.negativeColor.value_or(ref.color), ref.color};
    const int zones = g.zoneGraphs.size() == 2 ? 2 : 1;
    QList<qreal> pattern;
    for (double d : dash) pattern.push_back(d / w);
    p.save();
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setClipRect(one.plotBox, Qt::IntersectClip);
    for (int k = 0; k < zones; ++k) {
        QPen pen(zones == 2 ? zone[k] : ref.color, w, Qt::CustomDashLine, Qt::FlatCap, Qt::SvgMiterJoin);
        pen.setMiterLimit(4);
        pen.setDashPattern(pattern);
        p.save();
        if (zones == 2) p.setClipPath(g.zoneGraphs[size_t(k)], Qt::IntersectClip);
        p.strokePath(g.graph, pen);
        p.restore();
    }
    p.restore();
}

void wdcTip_paintHoverPoint(QPainter& p, const ChartModel& m, const ChartInput& in, const SeriesGeom& g, const Hit& h) {
    const SeriesRef& ref = *in.refs[size_t(g.refIndex)];
    const QPointF pp = g.plotPts[size_t(h.pointIndex)];
    const QColor color = wdcTip_pointColor(ref, h.v);
    p.save();
    p.setRenderHint(QPainter::Antialiasing, true);
    if (ref.type == SeriesType::Column) {   // pointAttribs(hover): fill brightened by 0.1 (Color.brighten, pInt)
        if (size_t(h.pointIndex) < g.columns.size() && !g.columns[size_t(h.pointIndex)].isEmpty()) {
            const int add = int(kColumnBrightness * 255);
            const QColor b(std::min(255, color.red() + add), std::min(255, color.green() + add),
                           std::min(255, color.blue() + add), color.alpha());
            p.setClipRect(m.plotBox, Qt::IntersectClip);
            p.fillPath(g.columns[size_t(h.pointIndex)], b);
        }
        p.restore();
        return;
    }
    const QPointF rel = pp - m.plotBox.topLeft();
    if (wdcTip_inside(rel, m.plotBox.size())) {   // stateMarkerGraphic shows only for an inside point
        const double cx = hcmath::crisp(rel.x(), 1) + m.plotBox.left();   // markerAttribs crisps plotX
        QColor halo = color;
        halo.setAlphaF(float(color.alphaF() * kHaloOpacity));
        QPainterPath haloPath;
        haloPath.addEllipse(QPointF(cx, pp.y()), kHaloSize, kHaloSize);
        p.fillPath(haloPath, halo);
        const double r = in.spec->markerRadius + kRadiusPlus;
        p.setPen(QPen(Qt::white, kMarkerLineWidthPlus));
        p.setBrush(color);
        p.drawPath(wdcTip_symbol(g.symbol, QRectF(cx - r, pp.y() - r, 2 * r, 2 * r)));
    }
    p.restore();
}

} // namespace

void paintChartHover(QPainter& p, const ChartModel& m, const ChartInput& in, const HoverFrame& f,
                     TextMetrics* labelCache) {
    const double dpr = p.device() ? p.device()->devicePixelRatioF() : 1.0;
    const SeriesGeom* hg = f.hit ? wdcTip_geom(m, f.hit->refIndex) : nullptr;
    const bool valid = in.spec && hg && wdcTip_refOk(in, f.hit->refIndex) && f.hit->pointIndex >= 0 &&
                       size_t(f.hit->pointIndex) < hg->plotPts.size() && wdcTip_finite(hg->plotPts[size_t(f.hit->pointIndex)]);
    if (!valid) {
        paintChart(p, m, in);
        if (f.tooltip) paintTooltip(p, *f.tooltip, dpr);
        return;
    }
    const Hit& h = *f.hit;
    ChartModel base = m;                                  // z1 grid and z7 axis labels (no overlap with the plot)
    base.series.clear();
    paintChart(p, base, in);
    const CrosshairGeom cg = crosshairGeometry(m, in, h, dpr, in.profile, labelCache);
    paintCrosshairLines(p, cg);                           // z2, under the series
    ChartModel one = m;
    one.x.ticks.clear();
    for (AxisModel& a : one.y) a.ticks.clear();
    std::vector<const SeriesGeom*> order;
    for (const SeriesGeom& g : m.series)
        if (wdcTip_refOk(in, g.refIndex) && wdcTip_visible(in, g.refIndex)) order.push_back(&g);
    std::stable_sort(order.begin(), order.end(), [&](const SeriesGeom* a, const SeriesGeom* b) {
        return in.refs[size_t(a->refIndex)]->zIndex < in.refs[size_t(b->refIndex)]->zIndex;
    });
    QImage layer;
    for (const SeriesGeom* g : order) {
        const bool active = g->refIndex == h.refIndex;
        one.series.assign(1, *g);
        if (in.spec->inactiveFade && !active) {           // group opacity: render alone, then composite at .2
            if (layer.isNull()) layer = QImage((in.size * dpr).toSize() + QSize(1, 1), QImage::Format_ARGB32_Premultiplied);
            layer.setDevicePixelRatio(dpr);
            layer.fill(Qt::transparent);
            QPainter lp(&layer);
            wdcTip_paintSeries(lp, one, in, *g, false);
            lp.end();
            p.save();
            p.setOpacity(p.opacity() * kInactiveOpacity);
            p.drawImage(QPointF(0, 0), layer);
            p.restore();
        } else {
            wdcTip_paintSeries(p, one, in, *g, active);
        }
        if (active) wdcTip_paintHoverPoint(p, m, in, *g, h);
    }
    paintCrosshairLabel(p, cg);                           // axis label group, above the tick labels
    if (f.tooltip) paintTooltip(p, *f.tooltip, dpr);       // z 8
}

// ---- controller ---------------------------------------------------------------------------------------------------------

WdcChartHover::WdcChartHover(QObject* parent) : QObject(parent) {
    hideTimer_.setSingleShot(true);
    hideTimer_.setInterval(kHideDelayMs);
    connect(&hideTimer_, &QTimer::timeout, this, [this] { frame_.tooltip.reset(); emit updateRequested(); });
}

void WdcChartHover::mouseMove(QPointF chartPos) {
    const auto src = source_ ? source_() : std::pair<const ChartModel*, const ChartInput*>{nullptr, nullptr};
    const std::optional<Hit> h = (src.first && src.second) ? hitTest(*src.first, *src.second, chartPos) : std::nullopt;
    if (!h) return hideNow();
    hideTimer_.stop();
    const bool same = frame_.hit && frame_.hit->refIndex == h->refIndex && frame_.hit->pointIndex == h->pointIndex &&
                      frame_.tooltip;
    if (same) return;                                     // refresh only on a new hover point (HS:27697)
    frame_.hit = h;
    frame_.tooltip = tooltipFrame(*src.first, *src.second, *h, dpr_);
    crosshairGeometry(*src.first, *src.second, *h, dpr_, src.second->profile, labelCache());   // seeds the box cache
    emit updateRequested();
}

void WdcChartHover::hideNow() {
    if (!frame_.hit) return;
    frame_.hit.reset();                                   // hover state and crosshair: at once
    if (frame_.tooltip) hideTimer_.start();               // tooltip: after hideDelay
    emit updateRequested();
}

void WdcChartHover::mouseLeave() { hideNow(); }

TextMetrics* WdcChartHover::labelCache() {
    if (!labelCache_) labelCache_ = std::make_unique<TextMetrics>(TextMetrics::native(dpr_));
    return labelCache_.get();
}

void WdcChartHover::reset() {
    hideTimer_.stop();
    const bool had = active();
    frame_ = HoverFrame{};
    if (had) emit updateRequested();
}

void WdcChartHover::paint(QPainter& p, const QRectF& chartRect) {
    const auto src = source_ ? source_() : std::pair<const ChartModel*, const ChartInput*>{nullptr, nullptr};
    if (!src.first || !src.second) return;
    HoverFrame f = frame_;
    if (f.hit) f.tooltip = tooltipFrame(*src.first, *src.second, *f.hit, dpr_);   // follow a relayout
    p.save();
    p.setClipRect(chartRect, Qt::IntersectClip);
    p.fillRect(chartRect, th::color(th::kBgSurface));     // the card background under the transparent chart
    p.translate(chartRect.topLeft());
    paintChartHover(p, *src.first, *src.second, f, labelCache());
    p.restore();
}

} // namespace fincept::screens::wdc
