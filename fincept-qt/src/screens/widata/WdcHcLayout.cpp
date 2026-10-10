// WdcHcLayout.cpp, package B: layoutChart = Highcharts 12.3.0 Chart.render for one pane (HS:38091-38166):
// render over the full data then redraw with the window, Axis.getOffset (HS:21236-21343), tick label positions (Tick.getPosition,
// getLabelPosition, handleOverflow HS:18495-18671), then package C's buildSeriesGeometry.
#include "WdcHcApi.h"
#include "WdcHcInternal_p.h"

#include <algorithm>
#include <cmath>
#include <functional>
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

using namespace hcint;

constexpr double kWdcLayXLabelPx = 12;      // xAxis labels 0.75rem (ENG §1.2)
constexpr double kWdcLayXDistance = 15;     // labels.distance
constexpr double kWdcLayXTickLength = 10;   // xAxis tickLength (tickWidth 1, colour transparent)
constexpr double kWdcLayXPadding = 3;       // horizontal labels.padding
constexpr int kWdcLayWeight = 400;

// ---------------------------------------------------------------- preparation

void wdcLay_prepareSeries(LayoutWork& w) {
    const ChartInput& in = *w.in;
    const size_t n = in.refs.size();
    w.series.assign(n, PreparedSeries{});
    w.stackedY.assign(n, {});
    for (size_t i = 0; i < n; ++i) {
        PreparedSeries& s = w.series[i];
        s.refIndex = int(i);
        s.ref = in.refs[i];
        s.data = i < in.data.size() ? in.data[i] : nullptr;
        if (!s.ref) continue;
        if (s.data && s.data->status != Status::Missing) {
            std::vector<QPointF> pts = s.data->pts;
            std::stable_sort(pts.begin(), pts.end(), [](const QPointF& a, const QPointF& b) { return a.x() < b.x(); });
            bool finite = false;
            for (const QPointF& p : pts) {
                if (!std::isfinite(p.x())) continue;
                s.x.push_back(p.x());
                s.y.push_back(std::isfinite(p.y()) ? p.y() : kNaN);
                finite = finite || std::isfinite(p.y());
            }
            s.present = finite;   // T25: a series without a single number does not exist for the axes
        }
        if (!s.present) { s.x.clear(); s.y.clear(); }   // C14: a series without a number is `data: []`
        s.legendOn = i >= in.visible.size() || in.visible[i];
        s.visible = s.present && s.legendOn;
        s.cropEnd = int(s.x.size());
        for (size_t k = 0; k < w.spec->yAxes.size(); ++k)
            if (w.spec->yAxes[k].slot == s.ref->slot) s.yAxis = int(k);
        // WiData's X label formatter tests chart.series.some(type === 'column'): hidden or data-less too (C14)
        if (s.ref->type == SeriesType::Column) w.hasColumn = true;
    }
    w.order.resize(n);
    std::iota(w.order.begin(), w.order.end(), 0);
    std::stable_sort(w.order.begin(), w.order.end(), [&](int a, int b) {
        const int sa = in.refs[size_t(a)] ? in.refs[size_t(a)]->si : a;
        const int sb = in.refs[size_t(b)] ? in.refs[size_t(b)]->si : b;
        return sa < sb;
    });
    for (size_t r = 0; r < n; ++r) w.series[size_t(w.order[r])].hcIndex = int(r);
}

void wdcLay_prepareAxes(LayoutWork& w) {
    const ChartInput& in = *w.in;
    w.y.assign(w.spec->yAxes.size(), YAxisState{});
    w.stacks.assign(w.spec->yAxes.size(), AxisStacks{});
    w.yLabels.assign(w.spec->yAxes.size(), {});
    for (size_t k = 0; k < w.y.size(); ++k) {
        w.y[k].spec = &w.spec->yAxes[k];
        w.y[k].tickPixelInterval = w.spec->isStock ? 72 : 80;   // DESIGN §5.1: 80 on aio axes, HS default 72 else
        w.y[k].labelPx = in.expanded ? 11 : w.spec->yAxes[k].labelPx;
    }
    w.x.userMin = in.xMin ? double(*in.xMin) : kNaN;
    w.x.userMax = in.xMax ? double(*in.xMax) : kNaN;
    w.x.minPadding = in.padAuto ? w.spec->xMinPadding : 0;
    w.x.maxPadding = in.padAuto ? w.spec->xMaxPadding : 0;
}

bool wdcLay_hasCartesian(const LayoutWork& w) {
    return std::any_of(w.series.begin(), w.series.end(), [](const PreparedSeries& s) { return s.present; });
}

// ---------------------------------------------------------------- margins (HS:37525-37880)

void wdcLay_resetMargins(LayoutWork& w) {
    const auto& sp = w.spec->spacing;
    const auto& m = w.spec->margin;
    w.plotTop = m[0].value_or(sp[0]);
    w.marginRight = m[1].value_or(sp[1]);
    w.marginBottom = m[2].value_or(sp[2]);
    w.plotLeft = m[3].value_or(sp[3]);
    std::fill(std::begin(w.axisOffset), std::end(w.axisOffset), 0.0);
}

void wdcLay_setChartSize(LayoutWork& w) {
    w.plotLeft = std::round(w.plotLeft);
    w.plotTop = std::round(w.plotTop);
    w.plotWidth = std::max(0.0, std::round(w.chartW - w.plotLeft - w.marginRight));
    w.plotHeight = std::max(0.0, std::round(w.chartH - w.plotTop - w.marginBottom));
    w.x.len = std::max(0.0, std::round(w.plotWidth));
    w.x.left = std::round(w.plotLeft);
    xSetAxisTranslation(w);
    for (size_t k = 0; k < w.y.size(); ++k) {
        w.y[k].len = std::max(0.0, std::round(w.plotHeight));
        w.y[k].top = std::round(w.plotTop);
        ySetAxisTranslation(w, int(k));
    }
}

// X tick label text: WiData formatter, 1 ms back for the month/year formats when the chart has a column.
QString wdcLay_xText(const LayoutWork& w, double tick) {
    const QHash<QString, QString>& f = w.spec->dtFormats;
    const QString fmt = f.value(hctime::unitName(w.x.unit.name), f.value(QStringLiteral("day")));
    const bool shift = w.spec->shiftLabelWhenColumn && w.hasColumn &&
                       (fmt == f.value(QStringLiteral("month")) || fmt == f.value(QStringLiteral("year")));
    return hctime::dateFormat(fmt, shift ? tick - 1 : tick);
}

// Axis.generateTick + Tick.addLabel / createLabel (HS:21204, 18380-18460) for one axis: a new label is measured
// before it has an alignment, a reused label whose text changes is measured with its current state.
void wdcLay_generateTicks(LayoutWork& w, std::map<double, LabelState>& labels, const std::vector<double>& ticks,
                          const std::function<QString(double)>& textOf, double px, const QString& align) {
    for (double pos : ticks) {
        const QString str = textOf(pos);
        auto it = labels.find(pos);
        if (it == labels.end()) {
            LabelState l;
            l.text = str;
            l.textPxLength = w.tm->bbox(str, px, kWdcLayWeight).width();
            labels.emplace(pos, l);
        } else if (it->second.text != str) {
            LabelState& l = it->second;
            l.text = str;   // a width set through css() stays (label.styles.width is set)
            l.textPxLength = w.tm->bbox(str, px, kWdcLayWeight, l.cssWidth, l.aligned ? align : QString(), l.lineClamp).width();
        }
    }
}

// Axis.render removes the labels of positions that are no longer ticks (HS: Axis.render, inactive ticks).
void wdcLay_prune(std::map<double, LabelState>& labels, const std::vector<double>& ticks) {
    for (auto it = labels.begin(); it != labels.end();)
        it = std::find(ticks.begin(), ticks.end(), it->first) == ticks.end() ? labels.erase(it) : std::next(it);
}

QString wdcLay_yText(const YAxisState& ya, double tick) { return hcfmt::yLabel(ya.spec->format, tick, ya.tickInterval); }

// Axis.getOffset for X: generateTick, renderUnsquish (HS:21035-21118), getLabelSize. Returns labelOffset.
double wdcLay_xOffsetLabels(LayoutWork& w) {
    const XAxisState& ax = w.x;
    if (!ax.hasData) { w.xLabels.clear(); return 0; }
    wdcLay_generateTicks(w, w.xLabels, ax.ticks, [&](double t) { return wdcLay_xText(w, t); }, kWdcLayXLabelPx,
                         QStringLiteral("center"));
    const double slotWidth = ax.len / std::max(double(ax.ticks.size()) - 1, 1.0);
    const double innerWidth = std::max(1.0, std::round(slotWidth - 2 * kWdcLayXPadding));
    // renderUnsquish lineClamp (HS:21040): floor(len / (tickPositions.length * labelMetrics.h)) || 1
    const int clamp = std::max(1, int(std::floor(ax.len / (double(ax.ticks.size()) * w.tm->hc(kWdcLayXLabelPx).h))));
    double labelOffset = 0;
    for (double pos : ax.ticks) {
        LabelState& l = w.xLabels[pos];
        l.aligned = true;
        if (ax.labelRotation == 0 && slotWidth && innerWidth < l.textPxLength) {
            l.cssWidth = innerWidth;
            l.lineClamp = clamp;
            l.styledWidth = true;
        } else if (l.cssWidth >= 0) {
            l.cssWidth = -1;   // css({width: 'auto'}); styles.width = 'auto', styles.lineClamp stay
        }
    }
    for (double pos : ax.ticks) {
        const LabelState& l = w.xLabels[pos];
        labelOffset = std::max(labelOffset, w.tm->bbox(l.text, kWdcLayXLabelPx, kWdcLayWeight, l.cssWidth,
                                                       QStringLiteral("center"), l.lineClamp).height());
    }
    return labelOffset;
}

// Axis.getOffset for one Y axis (labels nowrap: renderUnsquish only sets the alignment). Returns labelOffset.
double wdcLay_yOffsetLabels(LayoutWork& w, size_t k) {
    const YAxisState& ya = w.y[k];
    std::map<double, LabelState>& labels = w.yLabels[k];
    if (!ya.hasData()) { labels.clear(); return 0; }
    wdcLay_generateTicks(w, labels, ya.ticks, [&](double t) { return wdcLay_yText(ya, t); }, ya.labelPx, QStringLiteral("left"));
    double lo = 0;
    for (double pos : ya.ticks) labels[pos].aligned = true;
    for (double pos : ya.ticks)
        lo = std::max(lo, w.tm->bbox(labels[pos].text, ya.labelPx, kWdcLayWeight, -1, QStringLiteral("left")).width());
    return lo;
}

// Chart.getAxisMargins: Axis.getOffset for X (side 2) then every Y axis (side 1, opposite).
void wdcLay_getAxisMargins(LayoutWork& w) {
    std::fill(std::begin(w.axisOffset), std::end(w.axisOffset), 0.0);
    if (wdcLay_hasCartesian(w)) {
        const double labelOffset = wdcLay_xOffsetLabels(w);
        // labelOffsetPadded = H - rotCorr.y + (rotCorr.y + distance)
        const double padded = labelOffset ? labelOffset + kWdcLayXDistance : 0;
        w.axisOffset[2] = std::max({w.axisOffset[2], padded, w.x.ticks.empty() ? 0.0 : kWdcLayXTickLength});
        for (size_t k = 0; k < w.y.size(); ++k) {
            YAxisState& ya = w.y[k];
            const double lo = wdcLay_yOffsetLabels(w, k);
            ya.offset = w.axisOffset[1] ? w.axisOffset[1] + ya.spec->margin : 0;
            const double yPadded = lo ? lo + ya.spec->distance : 0;   // labels.x undefined -> distance
            w.axisOffset[1] = std::max({w.axisOffset[1], yPadded + ya.offset, yPadded});
        }
    }
    const auto& m = w.spec->margin;
    if (!m[0]) w.plotTop += w.axisOffset[0];
    if (!m[1]) w.marginRight += w.axisOffset[1];
    if (!m[2]) w.marginBottom += w.axisOffset[2];
    if (!m[3]) w.plotLeft += w.axisOffset[3];
    wdcLay_setChartSize(w);
}

void wdcLay_pruneAll(LayoutWork& w) {
    wdcLay_prune(w.xLabels, w.x.ticks);
    for (size_t k = 0; k < w.y.size(); ++k) wdcLay_prune(w.yLabels[k], w.y[k].ticks);
}

// ---------------------------------------------------------------- render: tick and label positions

// Axis.render for X: Tick.renderLabel + handleOverflow (CSS width on overflow stays on the label for the next
// pass). Fills `m` when given (final pass), else only updates the label state (end of the first render).
void wdcLay_renderXLabels(LayoutWork& w, AxisModel* m) {
    const XAxisState& ax = w.x;
    if (!ax.hasData) return;
    const auto& sp = w.spec->spacing;
    const double leftBound = std::min(ax.left, sp[3]);
    const double rightBound = std::max(ax.left + ax.len, w.chartW - sp[1]);
    const double slot = ax.len / std::max(double(ax.ticks.size()) - 1, 1.0);
    const double y = hcmath::jsRound(w.plotTop + w.plotHeight + w.tm->hc(kWdcLayXLabelPx).b + kWdcLayXDistance);
    for (double t : ax.ticks) {
        const double px = hcmath::correctFloat(hcmath::correctFloat((t - ax.min) * ax.transA + ax.minPixelPadding) + ax.left);
        LabelState& l = w.xLabels[t];
        const double lw = w.tm->bbox(l.text, kWdcLayXLabelPx, kWdcLayWeight, l.cssWidth, QStringLiteral("center"),
                                     l.lineClamp).width();
        double x = px, mod = slot, goRight = 1;   // Tick.handleOverflow, overflow 'justify', align center
        if (px - 0.5 * lw < leftBound) mod = px + slot * 0.5 - leftBound;
        else if (px + 0.5 * lw > rightBound) { mod = rightBound - px + slot * 0.5; goRight = -1; }
        mod = std::min(slot, mod);
        if (mod < slot) x += goRight * (slot - mod - 0.5 * (slot - std::min(lw, mod)));
        // textWidth when the label overflows, or (axis.autoRotation set: slot < 80 px) when the label has a
        // styles.width already, 'auto' included; then css({width: floor(textWidth) + 'px', lineClamp: 1}).
        if (lw > mod || (ax.autoRotation && l.styledWidth)) {
            l.cssWidth = std::floor(mod);
            l.lineClamp = 1;
            l.styledWidth = true;
        }
        if (!m) continue;
        const QString shown = l.cssWidth < 0 ? l.text : w.tm->ellipsize(l.text, kWdcLayXLabelPx, kWdcLayWeight, l.cssWidth);
        m->ticks.push_back(Tick{t, px, shown, QPointF(x, y), !shown.isEmpty()});
    }
}

AxisModel wdcLay_xModel(LayoutWork& w) {
    const XAxisState& ax = w.x;
    AxisModel m{-1, ax.hasData, ax.min, ax.max, ax.tickInterval, ax.transA, 0, ax.minPixelPadding, {}};
    wdcLay_renderXLabels(w, &m);
    return m;
}

AxisModel wdcLay_yModel(LayoutWork& w, int k) {
    const YAxisState& ya = w.y[size_t(k)];
    AxisModel m{ya.spec->slot, ya.hasData(), ya.min, ya.max, ya.tickInterval, ya.transA, ya.offset, 0, {}};
    if (!ya.hasData()) return m;
    const double bottom = w.chartH - ya.len - ya.top;
    const double lx = w.x.left + w.x.len + ya.offset + ya.spec->distance;
    for (double t : ya.ticks) {
        const double py = hcmath::correctFloat(w.chartH - hcmath::correctFloat((t - ya.min) * ya.transA) - bottom);
        const QString text = w.yLabels[size_t(k)][t].text;
        const double h = w.tm->bbox(text, ya.labelPx, kWdcLayWeight, -1, QStringLiteral("left")).height();
        const double yOff = ya.spec->labelY ? *ya.spec->labelY : w.tm->hc(ya.labelPx).b - h / 2;
        m.ticks.push_back(Tick{t, py, text, QPointF(lx, hcmath::jsRound(py + yOff)), !text.isEmpty()});
    }
    return m;
}

// Chart.render (HS:38091-38166): getMargins(true), expected X label space, two axis layout runs.
void wdcLay_render(LayoutWork& w, bool cartesian) {
    wdcLay_resetMargins(w);
    wdcLay_setChartSize(w);
    if (cartesian)   // expected space for X labels from a mock label 'x' (HS:38113-38140)
        w.plotHeight = std::max(w.plotHeight - (w.tm->bbox(QStringLiteral("x"), kWdcLayXLabelPx, kWdcLayWeight).height() +
                                                kWdcLayXDistance), 0.0);
    bool redoH = true, redoV = false;
    for (int run = 0; run < 2; ++run) {   // axisLayoutRuns 2: the loop condition reduces to run < 2
        const double tempW = w.plotWidth, tempH = w.plotHeight;
        if (run == 0) {
            xSetScale(w);
            for (size_t k = 0; k < w.y.size(); ++k) ySetScale(w, int(k));
            wdcLay_getAxisMargins(w);
        } else {
            if (redoH) xSetTickInterval(w, true);
            if (redoV)
                for (size_t k = 0; k < w.y.size(); ++k) ySetTickInterval(w, int(k));
            wdcLay_resetMargins(w);   // getMargins()
            wdcLay_getAxisMargins(w);
        }
        redoH = tempW / w.plotWidth > (run ? 1 : 1.1);
        redoV = tempH / w.plotHeight > (run ? 1 : 1.05);
    }
    if (cartesian) wdcLay_renderXLabels(w, nullptr);   // the axes render (HS:38168): label overflow, then
    wdcLay_pruneAll(w);                                   // labels of vanished positions are destroyed
}

} // namespace

// ---------------------------------------------------------------- public

namespace hcint {

ChartModel layoutChartWith(const ChartInput& in, TextMetrics& tm, std::vector<std::vector<QPointF>>* processed) {
    ChartModel out;
    out.allMissing = true;
    if (!in.spec) return out;
    LayoutWork w;
    w.in = &in;
    w.spec = in.spec;
    w.tm = &tm;
    w.chartW = in.size.width();
    w.chartH = in.size.height();
    wdcLay_prepareSeries(w);
    wdcLay_prepareAxes(w);
    const bool cartesian = wdcLay_hasCartesian(w);

    // Highcharts sequence of a WiData card: Chart.render over the FULL data (no window), then setExtremes(window)
    // -> Chart.redraw. Both share the renderer's bbox cache, so label widths measured during the full-range
    // render persist (tier A: 14/14 unexplained Y widths of CAP are same-pattern texts of an earlier tick set),
    // and the redraw computes X ticks with the plot width of that render (ENG §2.1: 37/108 CAP charts).
    const double userMin = w.x.userMin, userMax = w.x.userMax, minPad = w.x.minPadding, maxPad = w.x.maxPadding;
    w.x.userMin = w.x.userMax = kNaN;
    w.x.minPadding = w.spec->xMinPadding;
    w.x.maxPadding = w.spec->xMaxPadding;
    wdcLay_render(w, cartesian);
    w.x.userMin = userMin;
    w.x.userMax = userMax;
    w.x.minPadding = minPad;
    w.x.maxPadding = maxPad;
    if (cartesian) {   // Chart.redraw (HS:36866-36975): setScale on every axis with the current size, getMargins
        xSetScale(w);
        for (size_t k = 0; k < w.y.size(); ++k) ySetScale(w, int(k));
        wdcLay_resetMargins(w);
        wdcLay_getAxisMargins(w);
    }

    out.plotBox = QRectF(w.plotLeft, w.plotTop, w.plotWidth, w.plotHeight);
    out.allMissing = !cartesian;
    out.x = wdcLay_xModel(w);
    for (size_t k = 0; k < w.y.size(); ++k) out.y.push_back(wdcLay_yModel(w, int(k)));

    LayoutContext ctx;
    ctx.in = &in;
    ctx.plotBox = out.plotBox;
    ctx.x = &out.x;
    ctx.y = &out.y;
    ctx.xPointRange = w.x.pointRange;
    ctx.xClosestPointRange = w.x.closestPointRange;
    ctx.series = w.series;
    ctx.stacks = w.stacks;
    for (const YAxisState& ya : w.y) {
        ctx.yThreshold.push_back(ya.threshold);
        ctx.ySoftThreshold.push_back(ya.softThreshold);
    }
    if (cartesian) out.series = buildSeriesGeometry(ctx);
    // Grouped series (C21): plotPts / markers stay indexed like the series data, the point of a group at the index
    // of its first raw point (WdcHcApi.h groupedPoint gives its time and value), every other index NaN / null.
    for (SeriesGeom& g : out.series) {
        const PreparedSeries& s = w.series[size_t(g.refIndex)];
        if (!s.grouped) continue;
        std::vector<QPointF> pts(s.rawX.size(), QPointF(kNaN, kNaN));
        std::vector<QRectF> mk(g.markers.empty() ? 0 : s.rawX.size());
        for (size_t k = 0; k < s.groupStart.size(); ++k) {
            const size_t at = size_t(s.groupStart[k]);
            if (k < g.plotPts.size()) pts[at] = g.plotPts[k];
            if (!mk.empty() && k < g.markers.size()) mk[at] = g.markers[k];
        }
        g.plotPts = std::move(pts);
        g.markers = std::move(mk);
    }
    if (processed) {   // (t, v) behind every plotPts index: the groups, or the sorted data of an ungrouped series
        processed->assign(in.refs.size(), {});
        for (const PreparedSeries& s : w.series) {
            if (s.refIndex < 0) continue;
            std::vector<QPointF>& o = (*processed)[size_t(s.refIndex)];
            o.assign(s.dataCount(), QPointF(kNaN, kNaN));
            for (size_t k = 0; k < (s.grouped ? s.groupStart.size() : s.x.size()); ++k)
                o[s.grouped ? size_t(s.groupStart[k]) : k] = QPointF(s.x[k], s.y[k]);
        }
    }
    return out;
}

double LayoutContext::xToPlot(double t) const {
    return hcmath::correctFloat((t - x->min) * x->transA + x->minPixelPadding);
}

double LayoutContext::yToPlot(int axis, double v) const {
    const AxisModel& a = (*y)[size_t(axis)];
    const double p = hcmath::correctFloat(plotBox.height() - (v - a.min) * a.transA);
    return std::clamp(p, -1e9, 1e9);
}

double LayoutContext::yThresholdPixel(int axis, double threshold) const {
    const AxisModel& a = (*y)[size_t(axis)];
    double t = threshold;
    if (std::isnan(t) || t == -INFINITY || a.min > t) t = a.min;
    else if (t == INFINITY || a.max < t) t = a.max;
    return hcmath::jsRound(yToPlot(axis, t));
}

} // namespace hcint

ChartModel layoutChart(const ChartInput& in) { return layoutChartAtDpr(in, 2.0); }

ChartModel layoutChartAtDpr(const ChartInput& in, double dpr) { return layoutChartAtDpr(in, dpr, nullptr); }

ChartModel layoutChartAtDpr(const ChartInput& in, double dpr, std::vector<std::vector<QPointF>>* processed) {
    TextMetrics tm = TextMetrics::forProfile(in.profile, dpr);
    return hcint::layoutChartWith(in, tm, processed);
}

} // namespace fincept::screens::wdc
