// WdcHcSeries.cpp (package C): series geometry of the WiData chart engine, Highcharts 12.3.0 semantics.
//
//   spline control points      getPointSpline        HS:41576-41705
//   graph path                 Line.getGraphPath     HS:40574-40700, getValidPoints HS:32788
//   areaspline (+ stack)       Area.getGraphPath     HS:41304-41405, getStackPoints HS:41412-41520
//   point translation          Series.translate      HS:32628-32770
//   negative zones             setOptions zones      HS:31690-31712, applyZones HS:33218-33356, getZone HS:25621
//   markers                    drawPoints            HS:32948-32990, markerAttribs HS:33061-33092,
//                              getCyclic/getSymbol   HS:31736-31806 (symbol list HS:4584)
// Columns: WdcHcColumn.cpp. Painting: WdcHcPaint.cpp.
//
// Output conventions (see harness/widata_clone/reports/C.md):
//  * every coordinate is a CHART coordinate (B_internal_api 1.1): built relative to the plot box like the
//    Highcharts series group, then translated by plotBox.topLeft() at the end of buildSeriesGeometry;
//  * plotPts, markers and columns are indexed like PreparedSeries::x (the sorted data); NaN point,
//    null QRectF or empty path where Highcharts draws nothing;
//  * zoneGraphs[k] / zoneAreas[k] are the CLIP regions of zone k (k = 0 below the threshold, drawn with
//    negativeColor; k = 1 the rest, series color). The shape drawn inside each clip is `graph` / `area`.
#include "WdcHcInternal_p.h"

#include <QPainterPath>

#include <algorithm>
#include <array>
#include <cmath>
#include <optional>

// Highcharts runs in JavaScript: no fused multiply-add. Clang contracts a*b+c into FMA by default
// (-ffp-contract=on), which flips spline clamps and tick comparisons by one ulp (ENG_w3 §2).
#if defined(__clang__)
#pragma clang fp contract(off)
#elif defined(__GNUC__)
#pragma GCC optimize("fp-contract=off")
#endif

namespace fincept::screens::wdc::hcint {

// drawPoints globallyEnabled (HS:32950-32953): explicit marker.enabled wins, else the closest point
// distance in px must reach enabledThreshold * radius.
bool markerEnabled(std::optional<bool> enabled, double closestPointRangePx, double radius, double enabledThreshold) {
    if (enabled.has_value())
        return *enabled;
    return closestPointRangePx >= enabledThreshold * radius;
}

// getCyclic('symbol') (HS:31736-31760): chart.symbolCounter grows once per non-column series, whether or
// not its marker is enabled or its data is present; columns use a noop getSymbol. The ORDER depends on
// the WiData chart component:
// - chart (macro cards, isStock false, zIndex 10000 steps): WiData's order, not series.index; the
//   reference screenshots show the counter running over the series by zIndex descending (symbolIndex
//   kept through the React chart updates, DESIGN §16 C15). Checked on 4 cards whose two orders disagree:
//   "Cán cân thương mại - Mỹ" square, "Cấu phần PMI Sản xuất - Mỹ" and "Lao động phi nông nghiệp - Mỹ"
//   triangle (ref/widata/06), "VN_Giá trị xuất khẩu" square (ref/user/3.webp).
// - stockChart (isStock: chart page "Dữ liệu vĩ mô" and the 6 isStock cards, zIndex 0, 1, 2 = index):
//   plain Highcharts, the counter runs in series index order (initSeries over options.series). FACT:
//   capture vimo userOptions series index 0 "Tổng tín dụng" zIndex 0, hover marker a circle
//   (ref/widata/13_vimo_tooltip.jpg); zIndex descending would give it a square.
// Ties: si, then refIndex. A ChartInput without spec (unit tests) takes the macro rule.
QString markerSymbol(const ChartInput& in, int refIndex) {
    static const char* const kSymbols[] = {"circle", "diamond", "square", "triangle", "triangle-down"};
    const SeriesRef* self = in.refs[size_t(refIndex)];
    const bool byIndex = in.spec && in.spec->isStock;
    auto before = [&](const SeriesRef* r, int j) {
        if (!byIndex && r->zIndex != self->zIndex)
            return r->zIndex > self->zIndex;
        if (r->si != self->si)
            return r->si < self->si;
        return j < refIndex;
    };
    int counter = 0;
    for (size_t j = 0; j < in.refs.size(); ++j) {
        const SeriesRef* r = in.refs[j];
        if (r && r->type != SeriesType::Column && before(r, int(j)))
            ++counter;
    }
    return QString::fromLatin1(kSymbols[counter % 5]);
}

// Stack of a stacked series inside ctx.stacks[axis], keyed by stackKeyOf() ("-" prefix: negative stack).
const std::map<double, StackItem>* seriesStackOf(const LayoutContext& ctx, int axis, const SeriesRef& ref,
                                                 bool negative) {
    if (axis < 0 || size_t(axis) >= ctx.stacks.size())
        return nullptr;
    const QString key = (negative ? QStringLiteral("-") : QString()) + stackKeyOf(ref);
    const auto& stacks = ctx.stacks[size_t(axis)].stacks;
    const auto it = stacks.find(key);
    return it == stacks.end() ? nullptr : &it->second;
}

namespace {

constexpr double kRange = 1e9;   // limitedRange, HS:32647
double wdcSer_limited(double v) { return std::clamp(v, -kRange, kRange); }
bool wdcSer_num(double v) { return std::isfinite(v); }
double wdcSer_or0(double v) { return std::isfinite(v) ? v : 0.0; }       // `v || 0` for a number

// The Highcharts Point fields the path builders read and write.
struct WdcSerPt {
    double plotX = kNaN, plotY = kNaN, yBottom = kNaN;
    bool isNull = false, doCurve = true;
    double rcx = kNaN, rcy = kNaN;     // rightContX/Y written by getPointSpline, consumed by the next point
};

enum class WdcSerOp : char { M, L, C, Z };
struct WdcSerCmd { WdcSerOp op; std::array<double, 6> v; };
using WdcSerPath = std::vector<WdcSerCmd>;

WdcSerCmd wdcSer_cmd(WdcSerOp op, double a = 0, double b = 0) { return {op, {a, b, 0, 0, 0, 0}}; }

// getPointSpline (HS:41576-41705), smoothing 1.5.
WdcSerCmd wdcSer_pointSpline(std::vector<WdcSerPt*>& pts, size_t i) {
    constexpr double smoothing = 1.5, denom = smoothing + 1;
    WdcSerPt& p = *pts[i];
    const double plotX = wdcSer_or0(p.plotX), plotY = wdcSer_or0(p.plotY);
    WdcSerPt* last = pts[i - 1];
    WdcSerPt* next = i + 1 < pts.size() ? pts[i + 1] : nullptr;
    auto doCurve = [](const WdcSerPt* o) { return o && !o->isNull && o->doCurve; };   // isCliff never set
    double lcx = kNaN, lcy = kNaN;
    if (doCurve(last) && doCurve(next)) {
        const double lastX = wdcSer_or0(last->plotX), lastY = wdcSer_or0(last->plotY);
        const double nextX = wdcSer_or0(next->plotX), nextY = wdcSer_or0(next->plotY);
        double correction = 0;
        lcx = (smoothing * plotX + lastX) / denom;
        lcy = (smoothing * plotY + lastY) / denom;
        const double rcx = (smoothing * plotX + nextX) / denom;
        double rcy = (smoothing * plotY + nextY) / denom;
        if (rcx != lcx)
            correction = ((rcy - lcy) * (rcx - plotX)) / (rcx - lcx) + plotY - rcy;
        lcy += correction;
        rcy += correction;
        if (lcy > lastY && lcy > plotY) {
            lcy = std::max(lastY, plotY);
            rcy = 2 * plotY - lcy;
        } else if (lcy < lastY && lcy < plotY) {
            lcy = std::min(lastY, plotY);
            rcy = 2 * plotY - lcy;
        }
        if (rcy > nextY && rcy > plotY) {
            rcy = std::max(nextY, plotY);
            lcy = 2 * plotY - rcy;
        } else if (rcy < nextY && rcy < plotY) {
            rcy = std::min(nextY, plotY);
            lcy = 2 * plotY - rcy;
        }
        p.rcx = rcx;
        p.rcy = rcy;
    }
    auto pick = [](double a, double b) { return !std::isnan(a) ? a : (!std::isnan(b) ? b : 0.0); };
    WdcSerCmd c{WdcSerOp::C, {pick(last->rcx, last->plotX), pick(last->rcy, last->plotY), pick(lcx, plotX),
                              pick(lcy, plotY), plotX, plotY}};
    last->rcx = last->rcy = kNaN;
    return c;
}

// Line.getGraphPath (HS:40574-40700) with step = false, options.connectNulls = true (every WiData series).
// nullsAsZeroes: nullopt = JS undefined. Cliffs never occur because connectNulls is always true.
WdcSerPath wdcSer_graphPath(std::vector<WdcSerPt*> points, std::optional<bool> nullsAsZeroes,
                            bool connectCliffs, bool spline) {
    const bool connectNulls = true;
    const bool nAZ = nullsAsZeroes.value_or(false);
    const bool allowNull = !(connectNulls && !nAZ && !connectCliffs);
    std::vector<WdcSerPt*> pts;
    pts.reserve(points.size());
    for (WdcSerPt* p : points)
        if (allowNull || !(p->isNull || !wdcSer_num(p->plotY)))
            pts.push_back(p);
    WdcSerPath out;
    bool gap = false;
    for (size_t i = 0; i < pts.size(); ++i) {
        const WdcSerPt& p = *pts[i];
        const bool isNull = p.isNull || std::isnan(p.plotY);
        if (isNull && !nullsAsZeroes.has_value() && i > 0) {
            gap = !connectNulls;
        } else if (isNull && !nAZ) {
            gap = true;
        } else {
            if (i == 0 || gap)
                out.push_back(wdcSer_cmd(WdcSerOp::M, p.plotX, p.plotY));
            else if (spline)
                out.push_back(wdcSer_pointSpline(pts, i));
            else
                out.push_back(wdcSer_cmd(WdcSerOp::L, p.plotX, p.plotY));
            gap = false;
        }
    }
    return out;
}

QPainterPath wdcSer_toQt(const WdcSerPath& path) {
    QPainterPath qp;
    qp.setFillRule(Qt::WindingFill);   // SVG fill-rule / clip-rule nonzero
    for (const WdcSerCmd& c : path) {
        switch (c.op) {
        case WdcSerOp::M: qp.moveTo(c.v[0], c.v[1]); break;
        case WdcSerOp::L: qp.lineTo(c.v[0], c.v[1]); break;
        case WdcSerOp::C: qp.cubicTo(c.v[0], c.v[1], c.v[2], c.v[3], c.v[4], c.v[5]); break;
        case WdcSerOp::Z: qp.closeSubpath(); break;
        }
    }
    return qp;
}

struct WdcSerWork {                 // one series being built
    const LayoutContext* ctx = nullptr;
    const PreparedSeries* ps = nullptr;
    int axis = -1;
    double yLen = 0, xLen = 0;
    std::vector<WdcSerPt> pts;      // processed points [cropStart, cropEnd)
    double closestPx = kNaN;
};

// Series.translate (HS:32628-32770) for line-like series; area stacks have negStacks = false.
void wdcSer_translate(WdcSerWork& w) {
    const LayoutContext& ctx = *w.ctx;
    const PreparedSeries& ps = *w.ps;
    const bool stacked = ps.ref->stacking != Stacking::None;
    const std::map<double, StackItem>* stack = stacked && ps.visible ? seriesStackOf(ctx, w.axis, *ps.ref, false)
                                                                      : nullptr;
    double lastPlotX = kNaN, closest = std::numeric_limits<double>::max();
    w.pts.resize(size_t(std::max(0, ps.cropEnd - ps.cropStart)));
    for (int i = ps.cropStart; i < ps.cropEnd; ++i) {
        WdcSerPt& p = w.pts[size_t(i - ps.cropStart)];
        const double x = ps.x[size_t(i)];
        double yv = ps.y[size_t(i)], low = kNaN;
        p.isNull = !wdcSer_num(yv);
        p.plotX = hcmath::correctFloat(wdcSer_limited(ctx.xToPlot(x)));
        if (stack) {
            const auto it = stack->find(x);
            if (it != stack->end() && !p.isNull) {
                const auto sp = it->second.points.find(ps.hcIndex);
                if (sp != it->second.points.end()) {
                    low = sp->second.bottom;
                    yv = sp->second.top;
                }
            }
        }
        p.yBottom = wdcSer_num(low) ? wdcSer_limited(ctx.yToPlot(w.axis, low)) : kNaN;
        p.plotY = wdcSer_num(yv) && !p.isNull ? wdcSer_limited(ctx.yToPlot(w.axis, yv)) : kNaN;
        if (!p.isNull) {
            if (!std::isnan(lastPlotX))
                closest = std::min(closest, std::abs(p.plotX - lastPlotX));
            lastPlotX = p.plotX;
        }
    }
    w.closestPx = closest;
}

// getStackPoints (HS:41412-41520), reversedStacks = true. Real points keep their objects; x values
// that the stack has but this series lacks get a dummy null point sitting on the series below.
std::vector<WdcSerPt*> wdcSer_stackPoints(WdcSerWork& w, std::vector<WdcSerPt>& dummies) {
    const LayoutContext& ctx = *w.ctx;
    const PreparedSeries& ps = *w.ps;
    std::vector<WdcSerPt*> segment;
    const std::map<double, StackItem>* stack = seriesStackOf(ctx, w.axis, *ps.ref, false);
    if (!stack)
        return segment;
    std::vector<int> axisSeries;            // yAxis.series, Highcharts series order
    for (const PreparedSeries& s : ctx.series)
        if (s.present && s.yAxis == w.axis)
            axisSeries.push_back(s.refIndex);
    std::stable_sort(axisSeries.begin(), axisSeries.end(),
                     [&](int a, int b) { return ctx.series[size_t(a)].hcIndex < ctx.series[size_t(b)].hcIndex; });
    const int seriesIndex = int(std::find(axisSeries.begin(), axisSeries.end(), ps.refIndex) - axisSeries.begin());
    std::map<double, WdcSerPt*> pointMap;
    for (int i = ps.cropStart; i < ps.cropEnd; ++i)
        pointMap[ps.x[size_t(i)]] = &w.pts[size_t(i - ps.cropStart)];
    dummies.reserve(stack->size());
    for (const auto& [x, item] : *stack) {           // std::map keeps the keys sorted ascending
        const auto pm = pointMap.find(x);
        if (pm != pointMap.end() && !pm->second->isNull) {
            segment.push_back(pm->second);
            continue;
        }
        double y = 0;
        for (int i = seriesIndex; i >= 0 && i < int(axisSeries.size()); ++i) {
            const int hc = ctx.series[size_t(axisSeries[size_t(i)])].hcIndex;
            const auto sp = item.points.find(hc);
            if (sp != item.points.end()) {
                y = sp->second.top;
                break;
            }
        }
        WdcSerPt d;
        d.isNull = true;
        d.plotX = ctx.xToPlot(x);
        d.plotY = d.yBottom = ctx.yToPlot(w.axis, y);
        dummies.push_back(d);
        segment.push_back(&dummies.back());
    }
    return segment;
}

// Area.getGraphPath (HS:41304-41405) with connectNulls = true: returns the graph path, fills areaPath.
WdcSerPath wdcSer_areaPaths(WdcSerWork& w, WdcSerPath& areaPath) {
    const bool stacked = w.ps->ref->stacking != Stacking::None;
    const double translatedThreshold = w.ctx->yThresholdPixel(w.axis, 0);
    std::vector<WdcSerPt> dummies, bottom;
    std::vector<WdcSerPt*> points;
    if (stacked) {
        points = wdcSer_stackPoints(w, dummies);
    } else {
        for (WdcSerPt& p : w.pts)
            points.push_back(&p);
    }
    std::vector<WdcSerPt*> graphPoints;
    bottom.reserve(points.size());
    for (WdcSerPt* p : points) {
        const double yBottom = stacked && wdcSer_num(p->yBottom) ? p->yBottom : translatedThreshold;
        if (p->isNull && !stacked)
            continue;                                    // skip null point, no stacking, connectNulls
        graphPoints.push_back(p);
        WdcSerPt b;
        b.plotX = p->plotX;
        b.plotY = yBottom;
        bottom.push_back(b);
    }
    const WdcSerPath top = wdcSer_graphPath(graphPoints, true, true, true);
    std::vector<WdcSerPt*> bottomPts;
    for (auto it = bottom.rbegin(); it != bottom.rend(); ++it)
        bottomPts.push_back(&*it);
    WdcSerPath bottomPath = wdcSer_graphPath(bottomPts, true, true, true);
    if (!bottomPath.empty() && bottomPath.front().op == WdcSerOp::M)
        bottomPath.front().op = WdcSerOp::L;
    areaPath = top;
    areaPath.insert(areaPath.end(), bottomPath.begin(), bottomPath.end());
    if (!areaPath.empty())
        areaPath.push_back(wdcSer_cmd(WdcSerOp::Z));
    return wdcSer_graphPath(graphPoints, false, true, true);
}

// Negative zone clips (applyZones, HS:33218-33356), zoneAxis 'y', two zones: {value 0, negativeColor}
// and {rest}. Adaptive line clips avoid splitting the stroke near the threshold.
void wdcSer_zones(const WdcSerWork& w, double lineWidth, bool hasGraph, bool hasArea, SeriesGeom& g) {
    const LayoutContext& ctx = *w.ctx;
    const AxisModel& ya = (*ctx.y)[size_t(w.axis)];
    auto toPixels = [&](double v) {        // axis.toPixels(v, true): translate without the 1e9 clamp
        const double r = hcmath::correctFloat(-(v - ya.min) * ya.transA + w.yLen - ya.minPixelPadding);
        return std::isnan(r) ? 0.0 : r;
    };
    const double halfWidth = lineWidth / 2 + 1;
    std::array<double, 2> translated = {std::clamp(toPixels(0), 0.0, w.yLen),
                                        std::clamp(toPixels(ya.max), 0.0, w.yLen)};
    std::array<WdcSerPath, 2> lineClip;
    auto avoidClose = [&](int z, double plotX, double plotY) {
        const double distance = plotY - translated[size_t(z)];
        lineClip[size_t(z)].push_back(wdcSer_cmd(
            WdcSerOp::L, plotX,
            std::abs(distance) < halfWidth ? plotY - halfWidth * (distance <= 0 ? -1 : 1) : translated[size_t(z)]));
    };
    const PreparedSeries& ps = *w.ps;
    if (double(w.pts.size()) < w.xLen) {
        for (int i = ps.cropStart; i < ps.cropEnd; ++i) {
            const WdcSerPt& p = w.pts[size_t(i - ps.cropStart)];
            const double y = ps.y[size_t(i)];
            const int zone = (std::isnan(y) || y >= 0) ? 1 : 0;      // getZone: JS `null >= 0` is true
            const double plotY = std::isnan(p.plotY) ? 0.0 : p.plotY; // avoidClose default parameter
            avoidClose(zone, p.plotX, plotY);
            if (zone > 0)
                avoidClose(zone - 1, p.plotX, plotY);
        }
    }
    WdcSerPath lastLineClip;
    double lastTranslated = toPixels(ya.min);
    for (int z = 0; z < 2; ++z) {
        const double y1 = hcmath::jsRound(translated[size_t(z)]), y2 = lastTranslated, x2 = w.xLen;
        WdcSerPath simple = {wdcSer_cmd(WdcSerOp::M, 0, y1), wdcSer_cmd(WdcSerOp::L, x2, y1),
                             wdcSer_cmd(WdcSerOp::L, x2, y2), wdcSer_cmd(WdcSerOp::L, 0, y2),
                             wdcSer_cmd(WdcSerOp::Z)};
        WdcSerPath adaptive = {simple[0]};
        adaptive.insert(adaptive.end(), lineClip[size_t(z)].begin(), lineClip[size_t(z)].end());
        adaptive.push_back(simple[1]);
        adaptive.push_back(simple[2]);
        adaptive.insert(adaptive.end(), lastLineClip.begin(), lastLineClip.end());
        adaptive.push_back(simple[3]);
        adaptive.push_back(simple[4]);
        lastLineClip.assign(lineClip[size_t(z)].rbegin(), lineClip[size_t(z)].rend());
        lastTranslated = y1;
        if (hasGraph)
            g.zoneGraphs.push_back(wdcSer_toQt(adaptive));
        if (hasArea)
            g.zoneAreas.push_back(wdcSer_toQt(simple));
    }
}

// drawPoints + markerAttribs for line-like series (HS:32948-33092); options.crisp is true.
void wdcSer_markers(const WdcSerWork& w, SeriesGeom& g) {
    const ChartSpec& spec = *w.ctx->in->spec;
    const PreparedSeries& ps = *w.ps;
    const double r = spec.markerRadius;
    if (!markerEnabled(ps.ref->marker, w.closestPx, r) || !(r > 0))
        return;
    g.markers.assign(ps.x.size(), QRectF());
    for (int i = ps.cropStart; i < ps.cropEnd; ++i) {
        const WdcSerPt& p = w.pts[size_t(i - ps.cropStart)];
        if (p.isNull || !wdcSer_num(p.plotY))
            continue;
        const bool inside = p.plotY >= 0 && p.plotY <= w.yLen && p.plotX >= 0 && p.plotX <= w.xLen;
        if (!inside)
            continue;
        const double x = hcmath::crisp(p.plotX, 1) - r;   // symbol option is unset, so not 'rect'
        g.markers[size_t(i)] = QRectF(x, p.plotY - r, 2 * r, 2 * r);
    }
}

SeriesGeom wdcSer_buildLine(const LayoutContext& ctx, const PreparedSeries& ps) {
    SeriesGeom g;
    g.refIndex = ps.refIndex;
    WdcSerWork w;
    w.ctx = &ctx;
    w.ps = &ps;
    w.axis = ps.yAxis;
    w.yLen = ctx.plotBox.height();
    w.xLen = ctx.plotBox.width();
    wdcSer_translate(w);
    g.plotPts.assign(ps.x.size(), QPointF(kNaN, kNaN));
    for (int i = ps.cropStart; i < ps.cropEnd; ++i) {
        const WdcSerPt& p = w.pts[size_t(i - ps.cropStart)];
        if (!p.isNull && wdcSer_num(p.plotY))
            g.plotPts[size_t(i)] = QPointF(p.plotX, p.plotY);
    }
    const SeriesRef& ref = *ps.ref;
    const bool isArea = ref.type == SeriesType::AreaSpline;
    WdcSerPath graph, area;
    if (isArea) {
        graph = wdcSer_areaPaths(w, area);
    } else {
        std::vector<WdcSerPt*> pts;
        for (WdcSerPt& p : w.pts)
            pts.push_back(&p);
        graph = wdcSer_graphPath(pts, std::nullopt, false, true);
    }
    g.graph = wdcSer_toQt(graph);
    g.area = wdcSer_toQt(area);
    if (ref.negativeColor.has_value())
        wdcSer_zones(w, ref.lineWidth, true, isArea, g);
    g.symbol = markerSymbol(*ctx.in, ps.refIndex);
    wdcSer_markers(w, g);
    return g;
}

// Series group translate(plotLeft, plotTop): plot-relative geometry to chart coordinates.
void wdcSer_toChart(SeriesGeom& g, QPointF off) {
    g.graph.translate(off);
    g.area.translate(off);
    for (QPainterPath& p : g.zoneGraphs) p.translate(off);
    for (QPainterPath& p : g.zoneAreas) p.translate(off);
    for (QPainterPath& p : g.columns) p.translate(off);
    for (QRectF& r : g.markers)
        if (!r.isNull())
            r.translate(off);
    for (QPointF& p : g.plotPts)
        if (std::isfinite(p.x()) && std::isfinite(p.y()))
            p += off;
}

} // namespace

std::vector<SeriesGeom> buildSeriesGeometry(const LayoutContext& ctx) {
    std::vector<SeriesGeom> out;
    if (!ctx.in || !ctx.in->spec || !ctx.x || !ctx.y)
        return out;
    for (const PreparedSeries& ps : ctx.series) {
        if (!ps.present || !ps.ref)
            continue;
        const bool axisOk = ps.yAxis >= 0 && size_t(ps.yAxis) < ctx.y->size() && (*ctx.y)[size_t(ps.yAxis)].hasData;
        if (!ps.visible || !axisOk || ps.x.size() != ps.y.size()) {
            SeriesGeom empty;
            empty.refIndex = ps.refIndex;
            out.push_back(std::move(empty));
            continue;
        }
        SeriesGeom g;
        if (ps.ref->type == SeriesType::Column) {
            g.refIndex = ps.refIndex;
            buildColumnGeometry(ctx, ps.refIndex, g, nullptr);
        } else {
            g = wdcSer_buildLine(ctx, ps);
        }
        wdcSer_toChart(g, ctx.plotBox.topLeft());
        out.push_back(std::move(g));
    }
    return out;
}

// Moved from WdcHcPaint.cpp (ENG2 w4, line budget): path dashing for the painter.
namespace {

// ---- Dashing like Chromium/Skia (SkContourMeasure + SkDashPath), so dash phases along curves match:
// Skia measures a cubic by halving it until its control points sit within 0.5 / resScale px of the
// chord thirds, sums chord lengths, and maps a distance to t linearly inside each piece. Qt's dasher
// measures the true length, which drifts the dash phase by up to a dash on long curves (T19, 1x).
constexpr int kMaxT = 0x3FFFFFFF;

struct WdcDashSeg { double dist; int ptIndex; bool cubic; int tValue; };
struct WdcDashContour { std::vector<QPointF> pts; std::vector<WdcDashSeg> segs; };

QPointF wdcDash_lerp(QPointF a, QPointF b, double t) { return a + (b - a) * t; }

void wdcDash_chop(const QPointF* p, double t, QPointF* out7) {   // SkChopCubicAt, de Casteljau
    const QPointF ab = wdcDash_lerp(p[0], p[1], t), bc = wdcDash_lerp(p[1], p[2], t), cd = wdcDash_lerp(p[2], p[3], t);
    const QPointF abc = wdcDash_lerp(ab, bc, t), bcd = wdcDash_lerp(bc, cd, t), abcd = wdcDash_lerp(abc, bcd, t);
    out7[0] = p[0]; out7[1] = ab; out7[2] = abc; out7[3] = abcd; out7[4] = bcd; out7[5] = cd; out7[6] = p[3];
}

double wdcDash_cubicSegs(WdcDashContour& c, const QPointF* p, double distance, int mint, int maxt, int ptIndex,
                         double tol) {
    auto exceeded = [tol](QPointF pt, double x, double y) {
        return std::max(std::abs(x - pt.x()), std::abs(y - pt.y())) > tol;
    };
    const bool curvy = exceeded(p[1], p[0].x() + (p[3].x() - p[0].x()) / 3, p[0].y() + (p[3].y() - p[0].y()) / 3) ||
                       exceeded(p[2], p[0].x() + (p[3].x() - p[0].x()) * 2 / 3, p[0].y() + (p[3].y() - p[0].y()) * 2 / 3);
    if (((maxt - mint) >> 10) != 0 && curvy) {
        QPointF tmp[7];
        wdcDash_chop(p, 0.5, tmp);
        const int half = (mint + maxt) >> 1;
        distance = wdcDash_cubicSegs(c, tmp, distance, mint, half, ptIndex, tol);
        return wdcDash_cubicSegs(c, tmp + 3, distance, half, maxt, ptIndex, tol);
    }
    const double d = std::hypot(p[3].x() - p[0].x(), p[3].y() - p[0].y()), prev = distance;
    distance += d;
    if (distance > prev)
        c.segs.push_back({distance, ptIndex, true, maxt});
    return distance;
}

std::vector<WdcDashContour> wdcDash_measure(const QPainterPath& path, double tol) {
    std::vector<WdcDashContour> out;
    WdcDashContour cur;
    double dist = 0;
    auto flush = [&]() {
        if (!cur.segs.empty())
            out.push_back(std::move(cur));
        cur = WdcDashContour();
        dist = 0;
    };
    for (int i = 0; i < path.elementCount(); ++i) {
        const QPainterPath::Element e = path.elementAt(i);
        if (e.type == QPainterPath::MoveToElement) {
            flush();
            cur.pts.push_back(QPointF(e.x, e.y));
        } else if (e.type == QPainterPath::LineToElement) {
            const int idx = int(cur.pts.size()) - 1;
            const QPointF a = cur.pts.back(), b(e.x, e.y);
            cur.pts.push_back(b);
            const double prev = dist;
            dist += std::hypot(b.x() - a.x(), b.y() - a.y());
            if (dist > prev)
                cur.segs.push_back({dist, idx, false, kMaxT});
        } else if (e.type == QPainterPath::CurveToElement) {
            const int idx = int(cur.pts.size()) - 1;
            cur.pts.push_back(QPointF(e.x, e.y));
            cur.pts.push_back(QPointF(path.elementAt(i + 1).x, path.elementAt(i + 1).y));
            cur.pts.push_back(QPointF(path.elementAt(i + 2).x, path.elementAt(i + 2).y));
            i += 2;
            dist = wdcDash_cubicSegs(cur, &cur.pts[size_t(idx)], dist, 0, kMaxT, idx, tol);
        }
    }
    flush();
    return out;
}

const WdcDashSeg& wdcDash_seek(const WdcDashContour& c, double d, double& t) {   // distanceToSegment
    const auto it = std::lower_bound(c.segs.begin(), c.segs.end(), d,
                                     [](const WdcDashSeg& s, double v) { return s.dist < v; });
    const size_t index = std::min(size_t(it - c.segs.begin()), c.segs.size() - 1);
    const WdcDashSeg& seg = c.segs[index];
    double startT = 0, startD = 0;
    if (index > 0) {
        startD = c.segs[index - 1].dist;
        if (c.segs[index - 1].ptIndex == seg.ptIndex)
            startT = double(c.segs[index - 1].tValue) / kMaxT;
    }
    t = startT + (double(seg.tValue) / kMaxT - startT) * (d - startD) / (seg.dist - startD);
    return seg;
}

void wdcDash_segTo(const WdcDashContour& c, const WdcDashSeg& seg, double startT, double stopT, QPainterPath& dst) {
    const QPointF* p = &c.pts[size_t(seg.ptIndex)];
    if (startT == stopT) {
        if (!dst.isEmpty())
            dst.lineTo(dst.currentPosition());
        return;
    }
    if (!seg.cubic) {
        dst.lineTo(stopT == 1 ? p[1] : wdcDash_lerp(p[0], p[1], stopT));
        return;
    }
    QPointF a[7], b[7];
    if (startT == 0) {
        if (stopT == 1) {
            dst.cubicTo(p[1], p[2], p[3]);
        } else {
            wdcDash_chop(p, stopT, a);
            dst.cubicTo(a[1], a[2], a[3]);
        }
    } else {
        wdcDash_chop(p, startT, a);
        if (stopT == 1) {
            dst.cubicTo(a[4], a[5], a[6]);
        } else {
            wdcDash_chop(a + 3, (stopT - startT) / (1 - startT), b);
            dst.cubicTo(b[1], b[2], b[3]);
        }
    }
}

QPointF wdcDash_pos(const WdcDashContour& c, const WdcDashSeg& seg, double t) {
    const QPointF* p = &c.pts[size_t(seg.ptIndex)];
    if (!seg.cubic)
        return wdcDash_lerp(p[0], p[1], t);
    QPointF a[7];
    wdcDash_chop(p, t, a);
    return a[3];
}

void wdcDash_getSegment(const WdcDashContour& c, double startD, double stopD, QPainterPath& dst) {
    const double length = c.segs.back().dist;
    startD = std::max(startD, 0.0);
    stopD = std::min(stopD, length);
    if (!(startD <= stopD))
        return;
    double startT = 0, stopT = 0;
    const WdcDashSeg* seg = &wdcDash_seek(c, startD, startT);
    const WdcDashSeg* stopSeg = &wdcDash_seek(c, stopD, stopT);
    dst.moveTo(wdcDash_pos(c, *seg, startT));
    if (seg->ptIndex == stopSeg->ptIndex) {
        wdcDash_segTo(c, *seg, startT, stopT, dst);
        return;
    }
    do {
        wdcDash_segTo(c, *seg, startT, 1, dst);
        const int pi = seg->ptIndex;
        while (seg->ptIndex == pi)   // Segment::Next: first segment of the next curve
            ++seg;
        startT = 0;
    } while (seg->ptIndex < stopSeg->ptIndex);
    wdcDash_segTo(c, *seg, 0, stopT, dst);
}

} // namespace

// SkDashPath::InternalFilter with phase 0 on open contours: the "on" pieces as an open path.
QPainterPath dashPath(const QPainterPath& src, const std::vector<double>& intervals, double resScale) {
    QPainterPath dst;
    const double tol = 0.5 / (resScale > 0 ? resScale : 1.0);
    for (const WdcDashContour& c : wdcDash_measure(src, tol)) {
        const double length = c.segs.back().dist;
        double distance = 0, dlen = intervals[0];
        size_t index = 0;
        while (distance < length) {
            if (index % 2 == 0)
                wdcDash_getSegment(c, distance, distance + dlen, dst);
            distance += dlen;
            index = (index + 1) % intervals.size();
            dlen = intervals[index];
        }
    }
    return dst;
}

// Consecutive horizontal pieces (a line, or a cubic whose four points share one y with the control x inside the
// end points) merged into one line: the same geometry, a fraction of the elements. A step-like daily series (policy
// rates over 30 years) is mostly such pieces, and Qt's rasterizer cost grows faster than its element count.
// Used by WdcHcPaint.cpp (ENG2 w4) before Qt strokes a sparse series.
QPainterPath mergeFlat(const QPainterPath& src) {
    QPainterPath out;
    out.setFillRule(src.fillRule());
    QPointF cur, runEnd;
    bool run = false;
    auto flush = [&]() {
        if (run)
            out.lineTo(runEnd);
        run = false;
    };
    auto inside = [](double a, double lo, double hi) { return a >= std::min(lo, hi) && a <= std::max(lo, hi); };
    for (int i = 0; i < src.elementCount(); ++i) {
        const QPainterPath::Element e = src.elementAt(i);
        if (e.type == QPainterPath::MoveToElement) {
            flush();
            out.moveTo(e.x, e.y);
            cur = QPointF(e.x, e.y);
            continue;
        }
        QPointF end(e.x, e.y), c1, c2;
        const bool curve = e.type == QPainterPath::CurveToElement && i + 2 < src.elementCount();
        if (curve) {
            c1 = end;
            c2 = QPointF(src.elementAt(i + 1).x, src.elementAt(i + 1).y);
            end = QPointF(src.elementAt(i + 2).x, src.elementAt(i + 2).y);
            i += 2;
        }
        const bool flat = end.y() == cur.y() && (!curve || (c1.y() == cur.y() && c2.y() == cur.y() &&
                                                            inside(c1.x(), cur.x(), end.x()) && inside(c2.x(), cur.x(), end.x())));
        const bool sameDir = !run || ((end.x() - cur.x()) >= 0) == ((runEnd.x() - cur.x()) >= 0) || end.x() == cur.x();
        if (flat && run && sameDir) {
            runEnd = end;
        } else if (flat) {
            flush();
            run = true;
            runEnd = end;
        } else {
            flush();
            if (curve)
                out.cubicTo(c1, c2, end);
            else
                out.lineTo(end);
        }
        cur = end;
    }
    flush();
    return out;
}

} // namespace fincept::screens::wdc::hcint
