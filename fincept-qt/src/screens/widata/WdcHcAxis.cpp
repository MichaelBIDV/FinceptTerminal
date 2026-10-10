// WdcHcAxis.cpp, package B: LinearAxis (Y) and DateTimeAxis (X) of Highcharts 12.3.0 for one chart pane.
// Each block names the HS function it ports (HS = vendor/highcharts-12.3.0/highstock.src.js). Labels, offsets
// and the two layout runs live in WdcHcLayout.cpp.
#include "WdcHcInternal_p.h"

#include <algorithm>
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

constexpr double kWdcAxisXTickPixelInterval = 100;   // xAxis default (HS:16825)
constexpr double kWdcAxisXLabelPx = 12;              // 0.75rem, ENG §1.2
constexpr double kWdcAxisXLabelPadding = 3;          // horizontal labels.padding (HS setOptions sideSpecific)
constexpr double kWdcAxisAutoRotationLimit = 80;

bool wdcAxis_def(double v) { return !std::isnan(v); }
double wdcAxis_pick(double a, double b) { return wdcAxis_def(a) ? a : b; }
bool wdcAxis_isColumn(const PreparedSeries& s) { return s.ref->type == SeriesType::Column; }

// Series.getProcessedData (HS:32264-32310): crop to [min, max] with one shoulder point each side. forceCrop =
// Series.forceCropping (HS:55546): dataGrouping enabled, i.e. the non-column series of an isStock chart (C21).
void wdcAxis_processData(PreparedSeries& s, double min, double max, bool forceCrop) {
    const int n = int(s.x.size());
    const int cropThreshold = wdcAxis_isColumn(s) ? 50 : 300;
    s.cropStart = 0; s.cropEnd = n; s.cropped = false;
    if ((n > cropThreshold || forceCrop) && wdcAxis_def(min) && wdcAxis_def(max)) {
        if (s.x[size_t(n - 1)] < min || s.x[0] > max) {
            s.cropStart = s.cropEnd = 0;   // modified = empty table, cropped stays false
        } else if (s.x[0] < min || s.x[size_t(n - 1)] > max) {
            int i = 0, start = 0, end = n;
            for (; i < n; ++i)
                if (s.x[size_t(i)] >= min) { start = std::max(0, i - 1); break; }
            for (int j = i; j < n; ++j)
                if (s.x[size_t(j)] > max) { end = j + 1; break; }
            s.cropStart = start; s.cropEnd = end; s.cropped = true;
        }
    }
    const std::vector<double> xp(s.x.begin() + s.cropStart, s.x.begin() + s.cropEnd);
    s.closestPointRange = hcmath::getClosestDistance(xp);
}

// ---- dataGrouping (DESIGN §16 C21), Highstock's DataGrouping module (HS:58541-59306) as WiData leaves it: enabled
// by default on the isStock charts (pick(enabled, chart.options.isStock)), except columns (plotOptions.column.
// dataGrouping.enabled false); groupPixelWidth 2 (spline, areaspline) / 10 (column, still counted by
// getGroupPixelWidth); approximation 'average'; no anchors; xAxis.ordinal false.

double wdcAxis_groupPixelWidth(const LayoutWork& w) {   // Axis.getGroupPixelWidth (HS:58760-58784)
    double gpw = 0;
    bool doGrouping = false;
    for (int i = int(w.order.size()) - 1; i >= 0; --i) {   // axis.series, last first
        const PreparedSeries& s = w.series[size_t(w.order[size_t(i)])];
        if (!s.ref) continue;
        gpw = std::max(gpw, wdcAxis_isColumn(s) ? 10.0 : 2.0);
        const int dataLength = s.present ? s.cropEnd - s.cropStart : 0;   // modified table rowCount
        if (dataLength > w.plotWidth / gpw) doGrouping = true;
    }
    return doGrouping ? gpw : 0;
}

// Series.groupData with the 'average' approximation (HS:59176-59306, 58402, 58497): groups [pos, pos + 1) of
// groupPositions, a group of nulls only gives a null point, an empty group no point; sum runs last to first.
void wdcAxis_groupSeries(PreparedSeries& s, const std::vector<double>& pos, double totalRange) {
    std::vector<double> gx, gy;
    std::vector<int> gs;
    std::vector<double> values;
    bool hasNulls = false;
    size_t p = 0;
    int start = 0;
    const int n = s.cropEnd - s.cropStart;
    for (int i = 0; i <= n; ++i) {
        const double xi = i < n ? s.x[size_t(s.cropStart + i)] : 0;
        if (i < n && xi < pos[0]) continue;
        while ((p + 1 < pos.size() && i < n && xi >= pos[p + 1]) || i == n) {
            if (!values.empty() || hasNulls) {
                double y = kNaN;
                if (!values.empty()) {
                    double sum = 0;
                    for (size_t k = values.size(); k-- > 0;) sum += values[k];
                    y = hcmath::correctFloat(sum / double(values.size()));
                }
                gx.push_back(pos[p]);
                gy.push_back(y);
                gs.push_back(s.cropStart + start);
            }
            start = i;
            values.clear();
            hasNulls = false;
            ++p;
            if (i == n) break;
        }
        if (i == n) break;
        const double yi = s.y[size_t(s.cropStart + i)];
        if (std::isfinite(yi)) values.push_back(yi);
        else hasNulls = true;
    }
    s.rawX.swap(s.x);
    s.rawY.swap(s.y);
    s.x = std::move(gx);
    s.y = std::move(gy);
    s.groupStart = std::move(gs);
    s.grouped = true;
    s.cropStart = 0;                              // `cropped` keeps the processData verdict (Series.getExtremes)
    s.cropEnd = int(s.x.size());
    s.closestPointRange = totalRange;             // series.closestPointRange = groupPositions.info.totalRange
}

// Axis.applyGrouping + Series.applyGrouping (HS:58719-58736, 58983-59080) right after processData of every series.
void wdcAxis_applyGrouping(LayoutWork& w) {
    XAxisState& ax = w.x;
    if (!w.spec->isStock) return;
    const double gpw = wdcAxis_groupPixelWidth(w), plotSizeX = w.plotWidth;
    for (int r : w.order) {
        PreparedSeries& s = w.series[size_t(r)];
        if (!s.ref || !s.present || wdcAxis_isColumn(s)) continue;   // columns: dataGrouping.enabled false
        const int n = s.cropEnd - s.cropStart;
        if (!(gpw > 0) || n <= 0 || !(plotSizeX > 0) || !wdcAxis_def(ax.min)) continue;
        const double interval = gpw * (ax.max - ax.min) / plotSizeX;
        const hctime::TimeUnit u = hctime::normalizeTimeTickInterval(interval, true);
        const std::vector<double> pos = hctime::getTimeTicks(u, std::min(ax.min, s.x[size_t(s.cropStart)]),
                                                             std::max(ax.max, s.x[size_t(s.cropEnd - 1)]), 1);
        wdcAxis_groupSeries(s, pos, u.unitRange * u.count);
        if (s.legendOn && !s.x.empty() && wdcAxis_def(ax.dataMin) && s.x.front() < ax.min) {   // adjustExtremes
            if (ax.min <= ax.dataMin) ax.min = std::min(s.x.front(), ax.min);   // options.min never set (setExtremes)
            ax.dataMin = std::min(s.x.front(), ax.dataMin);
        }
        if (s.legendOn && !s.x.empty() && wdcAxis_def(ax.dataMax) && s.x.back() > ax.max) {
            if (ax.max >= ax.dataMax) ax.max = std::max(s.x.back(), ax.max);
            ax.dataMax = std::max(s.x.back(), ax.dataMax);
        }
    }
}

// Axis.getClosest (HS:19813-19842)
double wdcAxis_getClosest(const LayoutWork& w) {
    double closest = kNaN;
    std::vector<double> singleXs;
    for (const PreparedSeries& s : w.series) {
        if (!s.present) continue;
        if (s.dataCount() == 1) singleXs.push_back(s.grouped ? s.rawX[0] : s.x[0]);   // series.getColumn('x'): raw
        else if (s.visible && wdcAxis_def(s.closestPointRange))
            closest = wdcAxis_def(closest) ? std::min(closest, s.closestPointRange) : s.closestPointRange;
    }
    double single = kNaN;
    if (!singleXs.empty()) {
        std::sort(singleXs.begin(), singleXs.end());
        single = hcmath::getClosestDistance(singleXs);
    }
    if (wdcAxis_def(single) && wdcAxis_def(closest)) return std::min(single, closest);
    return wdcAxis_def(single) ? single : closest;
}

// Axis.adjustForMinRange (HS:19733-19800), X only, no options.min/max (WdcRange uses setExtremes).
void wdcAxis_adjustForMinRange(LayoutWork& w) {
    XAxisState& ax = w.x;
    if (!wdcAxis_def(ax.minRange)) {
        std::vector<double> all;
        double closestData = kNaN;
        for (const PreparedSeries& s : w.series) {
            if (!s.present) continue;
            const double c = hcmath::getClosestDistance(s.x);
            if (wdcAxis_def(c)) closestData = wdcAxis_def(closestData) ? std::min(closestData, c) : c;
        }
        ax.minRange = std::min(wdcAxis_def(closestData) ? closestData * 5 : 0.0, ax.dataMax - ax.dataMin);
    }
    double min = ax.min, max = ax.max;
    if (wdcAxis_def(max) && wdcAxis_def(min) && wdcAxis_def(ax.minRange) && max - min < ax.minRange) {
        const bool space = ax.dataMax - ax.dataMin >= ax.minRange;
        const double zoom = (ax.minRange - max + min) / 2;
        double lo = min - zoom;
        if (space) lo = std::max(lo, ax.dataMin);
        min = lo;
        double hi = min + ax.minRange;
        if (space) hi = std::min(hi, ax.dataMax);
        max = hi;
        if (max - min < ax.minRange) {
            lo = max - ax.minRange;
            if (space) lo = std::max(lo, ax.dataMin);
            min = lo;
        }
    }
    ax.min = min; ax.max = max;
}

// Axis.unsquish (HS:20925-20986), horizontal: returns the new tick interval, sets labelRotation.
double wdcAxis_unsquishX(LayoutWork& w) {
    XAxisState& ax = w.x;
    const double ti = ax.tickInterval;
    const double slotSize = ax.len / ((ax.max - ax.min) / ti);
    const double lineHeight = hcmath::correctFloat(w.tm->hc(kWdcAxisXLabelPx).h * 0.8);
    const double range = std::max(ax.max - ax.min, 0.0);
    double newTi = ti;
    int rotation = 0;
    if (slotSize < kWdcAxisAutoRotationLimit) {   // autoRotation [-45]
        const double space = std::fabs(lineHeight / std::sin(-45 * M_PI / 180));
        double step = (space + 2 * kWdcAxisXLabelPadding) / (slotSize ? slotSize : 1);
        step = step > 1 ? std::ceil(step) : 1;
        if (step * ti > range && std::isfinite(space) && std::isfinite(slotSize) && range) step = std::ceil(range / ti);
        newTi = hcmath::correctFloat(step * ti);
        rotation = -45;
    }
    ax.labelRotation = rotation;
    ax.autoRotation = slotSize < kWdcAxisAutoRotationLimit;
    return newTi;
}

// trimTicks (HS:20385-20416)
void wdcAxis_trim(std::vector<double>& t, double& min, double& max, bool startOnTick, bool endOnTick, double mpo) {
    if (t.empty()) return;
    const double roundedMin = t.front(), roundedMax = t.back();
    if (startOnTick && roundedMin != -INFINITY) min = roundedMin;
    else while (!t.empty() && min - mpo > t.front()) t.erase(t.begin());
    if (endOnTick) max = roundedMax;
    else while (!t.empty() && max + mpo < t.back()) t.pop_back();
    if (t.empty()) t.push_back((roundedMax + roundedMin) / 2);
}

std::vector<int> wdcAxis_axisSeries(const LayoutWork& w, int axis) {
    std::vector<int> out;
    for (int r : w.order)
        if (w.series[size_t(r)].present && w.series[size_t(r)].yAxis == axis) out.push_back(r);
    return out;
}

// Series.setStackedPoints (HS:40202-40308) for one series.
void wdcAxis_setStackedPoints(LayoutWork& w, int axis, PreparedSeries& s) {
    AxisStacks& st = w.stacks[size_t(axis)];
    const bool percent = s.ref->stacking == Stacking::Percent;
    const bool negStacks = wdcAxis_isColumn(s);
    const double threshold = 0, stackThreshold = 0;   // column startFromThreshold, area threshold 0
    const QString stackKey = stackKeyOf(*s.ref);
    const QString negKey = QStringLiteral("-") + stackKey;
    std::vector<double>& stackedY = w.stackedY[size_t(s.refIndex)];
    stackedY.assign(size_t(s.cropEnd - s.cropStart), kNaN);
    for (int i = s.cropStart; i < s.cropEnd; ++i) {
        const double x = s.x[size_t(i)], y = s.y[size_t(i)];
        const bool isNull = !std::isfinite(y);
        const double yNumber = isNull ? 0 : y;
        const bool isNegative = negStacks && yNumber < threshold;
        const QString& key = isNegative ? negKey : stackKey;
        StackItem& stack = st.stacks[key][x];
        stack.isNegative = isNegative;
        if (!isNull) stack.points[s.hcIndex] = StackPoint{wdcAxis_pick(stack.cumulative, stackThreshold), kNaN};
        else stack.points.erase(s.hcIndex);
        double total = stack.total;
        if (percent) {
            const QString& otherKey = isNegative ? stackKey : negKey;
            auto ot = st.stacks.find(otherKey);
            if (negStacks && ot != st.stacks.end() && ot->second.count(x)) {
                StackItem& other = ot->second[x];
                total = other.total = std::max(other.total, total) + std::fabs(yNumber);
            } else {
                total = hcmath::correctFloat(total + std::fabs(yNumber));
            }
        } else {
            total = hcmath::correctFloat(total + yNumber);
        }
        stack.cumulative = hcmath::correctFloat(wdcAxis_pick(stack.cumulative, stackThreshold) + yNumber);
        stack.total = total;
        if (!isNull) {
            stack.points[s.hcIndex].top = stack.cumulative;
            stackedY[size_t(i - s.cropStart)] = stack.cumulative;
            stack.hasValidPoints = true;
        }
    }
    if (percent) st.usePercentage = true;
}

// Series.modifyStacks + percentStacker (HS:40122-40160)
void wdcAxis_percentStacker(LayoutWork& w, int axis, PreparedSeries& s) {
    AxisStacks& st = w.stacks[size_t(axis)];
    const QString stackKey = stackKeyOf(*s.ref);
    for (const QString& key : {stackKey, QStringLiteral("-") + stackKey}) {
        auto sk = st.stacks.find(key);
        if (sk == st.stacks.end()) continue;
        for (int i = s.cropEnd - 1; i >= s.cropStart; --i) {
            auto it = sk->second.find(s.x[size_t(i)]);
            if (it == sk->second.end()) continue;
            auto pt = it->second.points.find(s.hcIndex);
            if (pt == it->second.points.end()) continue;
            const double f = it->second.total ? 100 / it->second.total : 0;
            pt->second.bottom = hcmath::correctFloat(pt->second.bottom * f);
            pt->second.top = hcmath::correctFloat(pt->second.top * f);
            w.stackedY[size_t(s.refIndex)][size_t(i - s.cropStart)] = pt->second.top;
        }
    }
}

} // namespace

// series.stackKey = [type, stack ?? '', xAxis.options.left, xAxis.options.width].join(',') (HS:40071-40080);
// the two x-axis options are undefined at WiData, hence the trailing ",,".
QString stackKeyOf(const SeriesRef& ref) {
    static const char* const kType[] = {"spline", "areaspline", "column"};
    return QLatin1String(kType[int(ref.type)]) + QStringLiteral(",") + ref.stack + QStringLiteral(",,");
}

// ------------------------------------------------------------------------------------------ X axis

void ungroupSeries(PreparedSeries& s) {
    if (!s.grouped) return;
    s.x.swap(s.rawX);
    s.y.swap(s.rawY);
    s.rawX.clear();
    s.rawY.clear();
    s.groupStart.clear();
    s.grouped = false;
    s.cropStart = 0;
    s.cropEnd = int(s.x.size());
}

void xSetScale(LayoutWork& w) {
    XAxisState& ax = w.x;
    for (PreparedSeries& s : w.series) ungroupSeries(s);   // processData starts from the series data again
    ax.len = std::max(0.0, std::round(w.plotWidth));   // setAxisSize
    ax.left = std::round(w.plotLeft);
    ax.dataMin = ax.dataMax = kNaN;
    ax.hasData = false;
    for (const PreparedSeries& s : w.series) {          // getSeriesExtremes, X branch (full data)
        if (!s.visible || s.x.empty()) continue;
        ax.hasData = true;
        ax.dataMin = wdcAxis_def(ax.dataMin) ? std::min(ax.dataMin, s.x.front()) : s.x.front();
        ax.dataMax = wdcAxis_def(ax.dataMax) ? std::max(ax.dataMax, s.x.back()) : s.x.back();
    }
    ax.minRange = kNaN;
    xSetTickInterval(w, false);
}

void xSetTickInterval(LayoutWork& w, bool secondPass) {
    XAxisState& ax = w.x;
    ax.min = wdcAxis_pick(ax.userMin, ax.dataMin);
    ax.max = wdcAxis_pick(ax.userMax, ax.dataMax);
    wdcAxis_adjustForMinRange(w);
    if (wdcAxis_def(ax.min) && wdcAxis_def(ax.max)) {
        const double range = ax.max - ax.min;
        if (range) {
            if (!wdcAxis_def(ax.userMin) && ax.minPadding) ax.min -= range * ax.minPadding;
            if (!wdcAxis_def(ax.userMax) && ax.maxPadding) ax.max += range * ax.maxPadding;
        }
    }
    const double range = ax.max - ax.min;
    if (ax.min == ax.max || !wdcAxis_def(ax.min) || !wdcAxis_def(ax.max)) ax.tickInterval = 1;
    else ax.tickInterval = range * kWdcAxisXTickPixelInterval / std::max(ax.len, kWdcAxisXTickPixelInterval);
    if (!secondPass) {
        for (PreparedSeries& s : w.series)
            if (s.present) wdcAxis_processData(s, ax.min, ax.max, w.spec->isStock && !wdcAxis_isColumn(s));
        wdcAxis_applyGrouping(w);   // fireEvent(axis, 'postProcessData') (HS:20209)
    }
    xSetAxisTranslation(w);
    if (ax.pointRange > 0) ax.tickInterval = std::max(ax.pointRange, ax.tickInterval);
    if (wdcAxis_def(ax.closestPointRange) && ax.closestPointRange && ax.tickInterval < ax.closestPointRange)
        ax.tickInterval = ax.closestPointRange;   // minTickInterval for sorted datetime data
    ax.tickInterval = wdcAxis_unsquishX(w);
    // setTickPositions (HS:20251-20368)
    ax.single = ax.min == ax.max && wdcAxis_def(ax.min);
    ax.ticks.clear();
    if (wdcAxis_def(ax.min) && wdcAxis_def(ax.max)) {
        if ((ax.max - ax.min) / ax.tickInterval > std::max(2 * ax.len, 200.0)) {
            ax.ticks = {ax.min, ax.max};
        } else {
            ax.unit = hctime::normalizeTimeTickInterval(ax.tickInterval);
            ax.ticks = hctime::getTimeTicks(ax.unit, ax.min, ax.max, 1);
        }
        if (double(ax.ticks.size()) > ax.len) {
            ax.ticks = {ax.ticks.front(), ax.ticks.back()};
            if (ax.ticks[0] == ax.ticks[1]) ax.ticks.resize(1);
        }
        wdcAxis_trim(ax.ticks, ax.min, ax.max, false, false, ax.minPointOffset);
        if (ax.single && ax.ticks.size() < 2) { ax.min -= 0.5; ax.max += 0.5; }
    }
}

// Axis.setAxisTranslation (HS:19953-20008), X branch.
void xSetAxisTranslation(LayoutWork& w) {
    XAxisState& ax = w.x;
    const double range = ax.max - ax.min;
    const double closest = wdcAxis_getClosest(w);
    double pointRange = 0, minPointOffset = 0, pointRangePadding = 0;
    for (const PreparedSeries& s : w.series) {   // axis.series: hidden and data-less series too (C14)
        if (!s.ref) continue;
        const double spr = wdcAxis_isColumn(s) ? (wdcAxis_def(closest) ? closest : 0) : 0;
        pointRange = std::max(pointRange, spr);
        minPointOffset = std::max(minPointOffset, spr / 2);
        pointRangePadding = std::max(pointRangePadding, spr);
    }
    ax.minPointOffset = minPointOffset;
    ax.pointRangePadding = pointRangePadding;
    ax.pointRange = std::isnan(range) ? kNaN : std::min(pointRange, range);
    ax.closestPointRange = closest;
    const double denom = range + pointRangePadding;
    ax.transA = ax.len / ((std::isnan(denom) || denom == 0) ? 1 : denom);
    ax.minPixelPadding = ax.transA * minPointOffset;
}

// ------------------------------------------------------------------------------------------ Y axes

void ySetScale(LayoutWork& w, int k) {
    YAxisState& ax = w.y[size_t(k)];
    ax.len = std::max(0.0, std::round(w.plotHeight));
    ax.top = std::round(w.plotTop);
    // buildStacks (HS:40340): reversedStacks, last series first
    w.stacks[size_t(k)] = AxisStacks{};
    const std::vector<int> axisSeries = wdcAxis_axisSeries(w, k);
    for (int i = int(axisSeries.size()) - 1; i >= 0; --i) {
        PreparedSeries& s = w.series[size_t(axisSeries[size_t(i)])];
        if (s.ref->stacking != Stacking::None && s.visible) wdcAxis_setStackedPoints(w, k, s);
    }
    for (int r : axisSeries) {
        PreparedSeries& s = w.series[size_t(r)];
        if (s.ref->stacking == Stacking::Percent && s.visible) wdcAxis_percentStacker(w, k, s);
    }
    ax.usePercentage = w.stacks[size_t(k)].usePercentage;
    // getSeriesExtremes (HS:19363-19442) + Series.getExtremes (HS:32524-32575)
    ax.dataMin = ax.dataMax = ax.threshold = kNaN;
    ax.softThreshold = true;
    ax.hasVisibleSeries = ax.seriesHasData = false;
    for (int r : w.order) {   // axis.series in series order; a `data: []` series still sets the threshold (C14)
        const PreparedSeries& s = w.series[size_t(r)];
        if (!s.ref || s.yAxis != k || !s.legendOn) continue;
        ax.hasVisibleSeries = true;
        if (s.ref->type != SeriesType::Spline) ax.threshold = 0;   // area/column threshold 0; spline undefined
        if (!s.visible) continue;
        ax.seriesHasData = true;
        const bool stacked = s.ref->stacking != Stacking::None;
        const int shoulder = wdcAxis_isColumn(s) ? 0 : 1;
        const int n = s.cropEnd - s.cropStart;
        for (int i = 0; i < n; ++i) {
            const double x = s.x[size_t(s.cropStart + i)];
            const double nx = i + shoulder < n ? s.x[size_t(s.cropStart + i + shoulder)] : 0;
            const double px = i - shoulder >= 0 ? s.x[size_t(s.cropStart + i - shoulder)] : 0;
            const bool inside = s.cropped || ((nx ? nx : x) >= w.x.min && (px ? px : x) <= w.x.max);
            if (!inside) continue;
            const double v = stacked ? w.stackedY[size_t(r)][size_t(i)] : s.y[size_t(s.cropStart + i)];
            if (!std::isfinite(v)) continue;
            ax.dataMin = wdcAxis_def(ax.dataMin) ? std::min(ax.dataMin, v) : v;
            ax.dataMax = wdcAxis_def(ax.dataMax) ? std::max(ax.dataMax, v) : v;
        }
    }
    ySetTickInterval(w, k);
}

void ySetTickInterval(LayoutWork& w, int k) {
    YAxisState& ax = w.y[size_t(k)];
    const YAxisSpec& sp = *ax.spec;
    // getTickAmount (HS:20512-20530) + alignToOthers (HS:20420-20470)
    int tickAmount = sp.tickAmount.value_or(0);
    ax.finalTickAmt = 0;
    if (!tickAmount && ax.len < ax.tickPixelInterval && sp.startOnTick && sp.endOnTick) tickAmount = 2;
    if (!tickAmount && sp.startOnTick && sp.endOnTick) {
        bool hasOther = false;
        for (size_t j = 0; j < w.y.size(); ++j) {
            if (int(j) == k) continue;
            for (const PreparedSeries& s : w.series)   // series.some(s => s.visible): data or not (C14)
                if (s.ref && s.legendOn && s.yAxis == int(j)) hasOther = true;
        }
        if (hasOther) tickAmount = int(std::ceil(ax.len / ax.tickPixelInterval)) + 1;
    }
    if (tickAmount && tickAmount < 4) { ax.finalTickAmt = tickAmount; tickAmount = 5; }
    ax.tickAmount = tickAmount;
    // extremes (HS:20031-20180)
    double minPadding = sp.minPadding, maxPadding = sp.maxPadding, thresholdMin = kNaN, thresholdMax = kNaN;
    if (ax.softThreshold && wdcAxis_def(ax.threshold) && wdcAxis_def(ax.dataMax) && wdcAxis_def(ax.dataMin)) {
        if (ax.dataMin >= ax.threshold) { thresholdMin = ax.threshold; minPadding = 0; }
        else if (ax.dataMax <= ax.threshold) { thresholdMax = ax.threshold; maxPadding = 0; }
    }
    ax.min = wdcAxis_pick(thresholdMin, ax.dataMin);
    ax.max = wdcAxis_pick(thresholdMax, ax.dataMax);
    if (wdcAxis_def(ax.min) && wdcAxis_def(ax.max)) {
        if (!ax.usePercentage) {
            const double range = ax.max - ax.min;
            if (range) {
                if (minPadding) ax.min -= range * minPadding;
                if (maxPadding) ax.max += range * maxPadding;
            }
        }
        if (ax.softThreshold && wdcAxis_def(ax.dataMin) && wdcAxis_def(ax.dataMax)) {
            const double t = wdcAxis_def(ax.threshold) ? ax.threshold : 0;
            if (ax.min < t && ax.dataMin >= t) ax.min = t;
            else if (ax.max > t && ax.dataMax <= t) ax.max = t;
        }
    }
    const double range = ax.max - ax.min;
    if (ax.min == ax.max || !wdcAxis_def(ax.min) || !wdcAxis_def(ax.max)) ax.tickInterval = 1;
    else ax.tickInterval = tickAmount ? range / std::max(tickAmount - 1, 1)
                                      : range * ax.tickPixelInterval / std::max(ax.len, ax.tickPixelInterval);
    ySetAxisTranslation(w, k);
    auto normalize = [&](double ti) {
        return hcmath::normalizeTickInterval(ti, nullptr, kNaN, (ti < 0.5 || tickAmount) ? 1 : 0, tickAmount != 0);
    };
    ax.tickInterval = normalize(ax.tickInterval);
    if (!tickAmount) {   // unsquish, vertical (HS:20981): getStep(lineHeight * 0.75)
        const double slotSize = ax.len / ((ax.max - ax.min) / ax.tickInterval);
        const double lineHeight = hcmath::correctFloat(w.tm->hc(ax.labelPx).h * 0.8);
        double step = (lineHeight * 0.75 + 2 * 1) / (slotSize ? slotSize : 1);   // vertical labels.padding 1
        step = step > 1 ? std::ceil(step) : 1;
        const double rng = std::max(ax.max - ax.min, 0.0);
        if (step * ax.tickInterval > rng && std::isfinite(slotSize) && rng) step = std::ceil(rng / ax.tickInterval);
        ax.tickInterval = hcmath::correctFloat(step * ax.tickInterval);
    }
    // setTickPositions (HS:20251-20368)
    ax.single = ax.min == ax.max && wdcAxis_def(ax.min) && !tickAmount;
    ax.ticks.clear();
    if (wdcAxis_def(ax.min) && wdcAxis_def(ax.max)) {
        if ((ax.max - ax.min) / ax.tickInterval > std::max(2 * ax.len, 200.0)) {
            ax.ticks = {ax.min, ax.max};
        } else if (ax.single) {
            ax.ticks = {ax.min};
        } else {
            const double start = ax.tickInterval;
            double adjusted = start;
            while (adjusted <= start * 2) {
                ax.ticks = hcmath::getLinearTickPositions(ax.tickInterval, ax.min, ax.max);
                if (tickAmount && int(ax.ticks.size()) > tickAmount) ax.tickInterval = normalize(adjusted *= 1.1);
                else break;
            }
        }
        if (double(ax.ticks.size()) > ax.len) {
            ax.ticks = {ax.ticks.front(), ax.ticks.back()};
            if (ax.ticks[0] == ax.ticks[1]) ax.ticks.resize(1);
        }
        wdcAxis_trim(ax.ticks, ax.min, ax.max, sp.startOnTick, sp.endOnTick, 0);
        if (ax.single && ax.ticks.size() < 2) { ax.min -= 0.5; ax.max += 0.5; }
        // adjustTickAmount (HS:20548-20650), thresholdAlignment undefined (no chart.alignThresholds)
        const double threshold = wdcAxis_def(ax.threshold) ? ax.threshold : (ax.softThreshold ? 0 : kNaN);
        const int current = int(ax.ticks.size());
        if (ax.hasData() && tickAmount && current < tickAmount) {
            const double min0 = ax.min, max0 = ax.max, ti = ax.tickInterval;
            while (int(ax.ticks.size()) < tickAmount) {
                if ((ax.ticks.size() % 2) || min0 == threshold) ax.ticks.push_back(hcmath::correctFloat(ax.ticks.back() + ti));
                else ax.ticks.insert(ax.ticks.begin(), hcmath::correctFloat(ax.ticks.front() - ti));
            }
            ax.transA *= double(current - 1) / double(tickAmount - 1);
            ax.min = sp.startOnTick ? ax.ticks.front() : std::min(min0, ax.ticks.front());
            ax.max = sp.endOnTick ? ax.ticks.back() : std::max(max0, ax.ticks.back());
        }
        if (ax.hasData() && ax.finalTickAmt) {
            const int len = int(ax.ticks.size());
            for (int i = len - 1; i >= 0; --i)
                if ((ax.finalTickAmt == 3 && i % 2 == 1) || (ax.finalTickAmt <= 2 && i > 0 && i < len - 1))
                    ax.ticks.erase(ax.ticks.begin() + i);
            ax.finalTickAmt = 0;
        }
    }
}

void ySetAxisTranslation(LayoutWork& w, int k) {
    YAxisState& ax = w.y[size_t(k)];
    const double range = ax.max - ax.min;
    ax.transA = ax.len / ((std::isnan(range) || range == 0) ? 1 : range);
}

} // namespace fincept::screens::wdc::hcint
