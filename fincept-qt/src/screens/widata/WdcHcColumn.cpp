// WdcHcColumn.cpp (package C): column series geometry, Highcharts 12.3.0 semantics.
//
//   getColumnMetrics       HS:42613-42670   (columnCount over the chart, stack groups, pointWidth)
//   column translate       HS:42787-42887   (dense, barW ceil, yBottom, crispCol HS:42678-42691)
//   stacks in translate    HS:32651-32700   (negStacks: y < 0 lives in "-" + stackKey)
//   border radius          HS:46760-46913   (radius 2, scope 'stack', where 'end', roundedRect cuts)
//   point colour / zone    HS:25621-25640   (painted from the data sign, see WdcHcPaint.cpp)
//
// WiData constants not carried by ChartSpec: borderWidth 0 (plotOptions.column.borderWidth), crisp true,
// minPointLength 0, maxPointWidth unset, pointRange option unset, xAxis.reversedStacks false.
// Coordinates are relative to the plot box origin here (like shapeArgs); buildSeriesGeometry moves them to
// chart coordinates. columns[i] is indexed like PreparedSeries::x.
#include "WdcHcInternal_p.h"

#include <QPainterPath>

#include <algorithm>
#include <array>
#include <cmath>

// Highcharts runs in JavaScript: no fused multiply-add. Clang contracts a*b+c into FMA by default
// (-ffp-contract=on), which flips spline clamps and tick comparisons by one ulp (ENG_w3 §2).
#if defined(__clang__)
#pragma clang fp contract(off)
#elif defined(__GNUC__)
#pragma GCC optimize("fp-contract=off")
#endif

namespace fincept::screens::wdc::hcint {

namespace {

constexpr double kBorderWidth = 0;   // WiData plotOptions.column.borderWidth
constexpr double kRange = 1e9;

double wdcCol_or(double a, double b) { return (std::isfinite(a) && a != 0) ? a : b; }   // JS `a || b`

struct WdcColMetrics { double width = 0, offset = 0, paddedWidth = 0; int columnCount = 0; };

// getColumnMetrics (HS:42613-42670). Every Y axis of a pane shares len/pos, so the count spans the chart.
// otherSeries.reserveSpace() is the legend state: a column series without data (`data: []`, DESIGN §16 C14)
// still takes its slot.
WdcColMetrics wdcCol_metrics(const LayoutContext& ctx, int refIndex) {
    const ChartSpec& spec = *ctx.in->spec;
    std::vector<const PreparedSeries*> order;
    for (const PreparedSeries& s : ctx.series)
        if (s.ref)
            order.push_back(&s);
    std::stable_sort(order.begin(), order.end(),
                     [](const PreparedSeries* a, const PreparedSeries* b) { return a->hcIndex < b->hcIndex; });
    std::map<QString, int> stackGroups;
    int columnCount = 0, columnIndex = 0;
    for (const PreparedSeries* s : order) {
        if (s->ref->type != SeriesType::Column || !s->legendOn || s->yAxis < 0)
            continue;
        int idx;
        if (s->ref->stacking != Stacking::None) {
            const QString key = stackKeyOf(*s->ref);
            auto it = stackGroups.find(key);
            if (it == stackGroups.end())
                it = stackGroups.emplace(key, columnCount++).first;
            idx = it->second;
        } else {
            idx = columnCount++;
        }
        if (s->refIndex == refIndex)
            columnIndex = idx;
    }
    const AxisModel& x = *ctx.x;
    const double xLen = ctx.plotBox.width();
    const double range = wdcCol_or(ctx.xClosestPointRange, wdcCol_or(x.tickInterval, 1));
    const double categoryWidth = std::min(std::abs(x.transA) * range, xLen);
    const double groupPadding = categoryWidth * spec.groupPadding;
    const double groupWidth = categoryWidth - 2 * groupPadding;
    const double pointOffsetWidth = groupWidth / (columnCount ? columnCount : 1);
    const double pointWidth = std::min(xLen, pointOffsetWidth * (1 - 2 * spec.pointPadding));
    const double pointPadding = (pointOffsetWidth - pointWidth) / 2;
    WdcColMetrics m;
    m.width = pointWidth;
    m.offset = pointPadding + (groupPadding + columnIndex * pointOffsetWidth - categoryWidth / 2);
    m.paddedWidth = pointOffsetWidth;
    m.columnCount = columnCount;
    return m;
}

struct WdcColRect { double x, y, w, h; };

// crispCol (HS:42678-42691) with options.crisp true.
WdcColRect wdcCol_crisp(double x, double y, double w, double h) {
    const double bottom = hcmath::crisp(y + h, kBorderWidth);
    y = hcmath::crisp(y, kBorderWidth);
    h = bottom - y;
    const double right = hcmath::crisp(x + w, kBorderWidth);
    x = hcmath::crisp(x, kBorderWidth);
    w = right - x;
    return {x, y, w, h};
}

// SVG elliptical arc (implementation notes F.6.5) appended as cubic Beziers, rx == ry, x-axis-rotation 0.
void wdcCol_arcTo(QPainterPath& path, double r, bool largeArc, bool sweep, QPointF to) {
    const QPointF from = path.currentPosition();
    if (from == to)
        return;
    if (!(r > 0)) {
        path.lineTo(to);
        return;
    }
    const double dx2 = (from.x() - to.x()) / 2, dy2 = (from.y() - to.y()) / 2;
    const double lambda = (dx2 * dx2 + dy2 * dy2) / (r * r);
    if (lambda > 1)
        r *= std::sqrt(lambda);
    const double num = std::max(0.0, r * r * r * r - r * r * (dx2 * dx2 + dy2 * dy2));
    const double den = r * r * (dx2 * dx2 + dy2 * dy2);
    double coef = den > 0 ? std::sqrt(num / den) : 0;
    if (largeArc == sweep)
        coef = -coef;
    const double cxp = coef * (r * dy2 / r), cyp = coef * (-r * dx2 / r);
    const double cx = cxp + (from.x() + to.x()) / 2, cy = cyp + (from.y() + to.y()) / 2;
    const double a1 = std::atan2((from.y() - cy) / r, (from.x() - cx) / r);
    double da = std::atan2((to.y() - cy) / r, (to.x() - cx) / r) - a1;
    if (sweep && da < 0)
        da += 2 * M_PI;
    else if (!sweep && da > 0)
        da -= 2 * M_PI;
    const int segs = std::max(1, int(std::ceil(std::abs(da) / (M_PI / 2) - 1e-9)));
    const double step = da / segs, k = 4.0 / 3.0 * std::tan(step / 4);
    double a = a1;
    for (int i = 0; i < segs; ++i) {
        const double b = a + step;
        const QPointF p1(cx + r * std::cos(a), cy + r * std::sin(a));
        const QPointF p2(cx + r * std::cos(b), cy + r * std::sin(b));
        const QPointF c1(p1.x() - k * r * std::sin(a), p1.y() + k * r * std::cos(a));
        const QPointF c2(p2.x() + k * r * std::sin(b), p2.y() - k * r * std::cos(b));
        path.cubicTo(c1, c2, i + 1 == segs ? to : p2);
        a = b;
    }
}

// BorderRadius roundedRect (HS:46821-46913): corners cut by the border-radius box (brBoxY, brBoxHeight).
QPainterPath wdcCol_roundedRect(double x, double y, double width, double height, double r, double brBoxY,
                                double brBoxHeight) {
    const double brOffsetTop = y - brBoxY, brOffsetBtm = (brBoxY + brBoxHeight) - (y + height);
    const double rTop = (brOffsetTop - r) > -0.1 ? 0 : r, rBtm = (brOffsetBtm - r) > -0.1 ? 0 : r;
    const double cutTop = std::max(rTop != 0 ? brOffsetTop : 0.0, 0.0);
    const double cutBtm = std::max(rBtm != 0 ? brOffsetBtm : 0.0, 0.0);
    QPointF a(x + rTop, y), b(x + width - rTop, y), c(x + width, y + rTop), d(x + width, y + height - rBtm);
    QPointF e(x + width - rBtm, y + height), f(x + rBtm, y + height), g(x, y + height - rBtm), h(x, y + rTop);
    auto pyth = [](double rr, double alt) { return std::sqrt(rr * rr - alt * alt); };
    if (cutTop != 0) {
        const double base = pyth(rTop, rTop - cutTop);
        a.rx() -= base;
        b.rx() += base;
        c.ry() = h.ry() = y + rTop - cutTop;
    }
    if (height < rTop - cutTop) {
        const double base = pyth(rTop, rTop - cutTop - height);
        c.rx() = d.rx() = x + width - rTop + base;
        e.rx() = std::min(c.x(), e.x());
        f.rx() = std::max(d.x(), f.x());
        g.rx() = h.rx() = x + rTop - base;
        c.ry() = h.ry() = y + height;
    }
    if (cutBtm != 0) {
        const double base = pyth(rBtm, rBtm - cutBtm);
        e.rx() += base;
        f.rx() -= base;
        d.ry() = g.ry() = y + height - rBtm + cutBtm;
    }
    if (height < rBtm - cutBtm) {
        const double base = pyth(rBtm, rBtm - cutBtm - height);
        c.rx() = d.rx() = x + width - rBtm + base;
        b.rx() = std::min(c.x(), b.x());
        a.rx() = std::max(d.x(), a.x());
        g.rx() = h.rx() = x + rBtm - base;
        d.ry() = g.ry() = y;
    }
    QPainterPath p;
    p.setFillRule(Qt::WindingFill);
    p.moveTo(a);
    p.lineTo(b);
    wdcCol_arcTo(p, rTop, false, true, c);
    p.lineTo(d);
    wdcCol_arcTo(p, rBtm, false, true, e);
    p.lineTo(f);
    wdcCol_arcTo(p, rBtm, false, true, g);
    p.lineTo(h);
    wdcCol_arcTo(p, rTop, false, true, a);
    p.closeSubpath();
    return p;
}

} // namespace

void buildColumnGeometry(const LayoutContext& ctx, int refIndex, SeriesGeom& out,
                         std::vector<std::array<double, 8>>* shapes) {
    const PreparedSeries& ps = ctx.series[size_t(refIndex)];
    const ChartSpec& spec = *ctx.in->spec;
    const AxisModel& ya = (*ctx.y)[size_t(ps.yAxis)];
    const int axis = ps.yAxis;
    const double yLen = ctx.plotBox.height();
    const bool percent = ps.ref->stacking == Stacking::Percent;
    const bool stacked = ps.ref->stacking != Stacking::None;
    const std::map<double, StackItem>* posStack = stacked ? seriesStackOf(ctx, axis, *ps.ref, false) : nullptr;
    const std::map<double, StackItem>* negStack = stacked ? seriesStackOf(ctx, axis, *ps.ref, true) : nullptr;

    const WdcColMetrics metrics = wdcCol_metrics(ctx, refIndex);
    // getThreshold(0) without rounding (HS:20839-20855); yToPlot also applies the 1e9 clamp, inert here.
    auto yTranslate = [&](double v) { return ctx.yToPlot(axis, v); };
    const double translatedThreshold = yTranslate(std::clamp(0.0, ya.min, ya.max));
    double barW = std::max(metrics.width, 1 + 2 * kBorderWidth);
    if (spec.pointPadding != 0)
        barW = std::ceil(barW);                       // options.pointPadding && options.crisp

    out.columns.assign(ps.x.size(), QPainterPath());
    out.plotPts.assign(ps.x.size(), QPointF(kNaN, kNaN));
    for (int i = ps.cropStart; i < ps.cropEnd; ++i) {
        const double xv = ps.x[size_t(i)], yRaw = ps.y[size_t(i)];
        const bool isNull = !std::isfinite(yRaw);
        const double plotX = hcmath::correctFloat(std::clamp(ctx.xToPlot(xv), -kRange, kRange));
        double yValue = yRaw, low = kNaN, stackTotal = kNaN;
        const std::map<double, StackItem>* stack = (yRaw < 0) ? negStack : posStack;   // negStacks, threshold 0
        if (stack && !isNull) {
            const auto it = stack->find(xv);
            if (it != stack->end()) {
                const auto sp = it->second.points.find(ps.hcIndex);
                if (sp != it->second.points.end()) {
                    low = sp->second.bottom;
                    yValue = sp->second.top;
                    stackTotal = it->second.total;
                }
            }
        }
        const double yBottomPx = std::isfinite(low) ? std::clamp(yTranslate(low), -kRange, kRange) : kNaN;
        const double plotYRaw = (!isNull && std::isfinite(yValue)) ? std::clamp(yTranslate(yValue), -kRange, kRange)
                                                                   : kNaN;
        if (isNull || !std::isfinite(plotYRaw))
            continue;                                         // drawPoints: isNumber(plotY) && y !== null
        out.plotPts[size_t(i)] = QPointF(plotX, plotYRaw);
        const double yBottom = std::isfinite(yBottomPx) ? yBottomPx : translatedThreshold;
        const double safe = 999 + std::abs(yBottom);
        const double plotY = std::clamp(plotYRaw, -safe, yLen + safe);
        const double barY = std::min(plotY, yBottom), barH = std::max(plotY, yBottom) - barY;
        const WdcColRect s = wdcCol_crisp(plotX + metrics.offset, barY, barW, barH);

        // seriesOnAfterColumnTranslate (HS:46760-46820)
        double brBoxY = s.y, brBoxHeight = s.h;
        if (std::isfinite(stackTotal) && stackTotal != 0) {   // scope 'stack' && point.stackTotal
            const double stackEnd = yTranslate(percent ? 100 : stackTotal), stackThr = yTranslate(0);
            const WdcColRect box = wdcCol_crisp(0, std::min(stackEnd, stackThr), 0, std::abs(stackEnd - stackThr));
            brBoxY = box.y;
            brBoxHeight = box.h;
        }
        const bool flip = yRaw < 0;                           // point.negative, yAxis not reversed
        const double r = std::min(spec.columnRadius, s.w / 2);
        if (flip) {
            brBoxY -= r;
            brBoxHeight += r;
        } else {
            brBoxHeight += r;
        }
        out.columns[size_t(i)] = wdcCol_roundedRect(s.x, s.y, s.w, s.h, r, brBoxY, brBoxHeight);
        if (shapes)
            shapes->push_back({double(i), s.x, s.y, s.w, s.h, r, brBoxY, brBoxHeight});
    }
}

// Exposed for tests and dumps (T15, T16): {width, offset, paddedWidth, columnCount, barW, dense}.
std::array<double, 6> columnMetrics(const LayoutContext& ctx, int refIndex) {
    const WdcColMetrics m = wdcCol_metrics(ctx, refIndex);
    double barW = std::max(m.width, 1 + 2 * kBorderWidth);
    if (ctx.in->spec->pointPadding != 0)
        barW = std::ceil(barW);
    const double closest = ctx.series[size_t(refIndex)].closestPointRange;
    const bool dense = std::isfinite(closest) && closest * ctx.x->transA < 2;   // series.closestPointRange
    return {m.width, m.offset, m.paddedWidth, double(m.columnCount), barW, dense ? 1.0 : 0.0};
}

} // namespace fincept::screens::wdc::hcint
