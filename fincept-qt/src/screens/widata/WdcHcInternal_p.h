#pragma once
// WdcHcInternal_p.h, internal contract between package B (axes, layout) and package C (series geometry).
// Owner: package B. Not part of the frozen WdcModel.h; C reads it, B changes it only with a note in
// harness/widata_clone/reports/B_internal_api.md.
//
// Flow inside layoutChart (WdcHcLayout.cpp, package B), mirroring how a WiData card is drawn by Highcharts 12.3.0:
//   1. prepare series: sort x, `present` / `visible`, hcIndex.
//   2. Chart.render over the FULL data (no window): two layout runs (HS:38091-38166), X axis then Y axes (stacks
//      built per Y axis, HS:20657), offsets, plot box; then the axes render (label overflow, stale labels pruned).
//   3. setExtremes(window) -> Chart.redraw (HS:36866-36975): setScale on every axis, getMargins. The bbox cache
//      and the tick labels survive from step 2, as in Highcharts (verified 160/160 against the real library).
//   4. buildSeriesGeometry(ctx) (package C, WdcHcSeries.cpp / WdcHcColumn.cpp) fills ChartModel::series, using
//      the crop and stacks of step 3.
#include "WdcHcMath.h"
#include "WdcHcText.h"
#include "WdcModel.h"

#include <QString>

#include <array>
#include <cmath>
#include <limits>
#include <map>
#include <optional>
#include <vector>

namespace fincept::screens::wdc::hcint {

inline constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();

// One chart series, index aligned with ChartInput::refs (refIndex == position in refs).
struct PreparedSeries {
    int refIndex = -1;
    int hcIndex = -1;                  // Highcharts series.index: rank of (ref->si, refIndex); use it for every
                                       // "series order" rule (stack build order, columnIndex, symbolCounter).
    const SeriesRef* ref = nullptr;
    const SeriesData* data = nullptr;
    bool present = false;              // status != Missing and >= 1 finite y. A series without a number is a
                                       // Highcharts series with `data: []` (DESIGN §16 C14): no extremes, no
                                       // SeriesGeom, but it still exists for the rules that read chart.series /
                                       // axis.series (legendOn below).
    bool legendOn = false;             // Highcharts series.visible = reserveSpace(): legend on, data or not (C14).
                                       // Drives column slots, axis threshold, alignToOthers, X pointRange.
    bool visible = false;              // present && legendOn: the series takes part in extremes and geometry
    int yAxis = -1;                    // index into ChartModel::y (spec yAxes entry with slot == ref->slot), -1 if none
    std::vector<double> x;             // all points sorted by x (stable), t in ms
    std::vector<double> y;             // NaN = null
    int cropStart = 0;                 // processed (cropped) range [cropStart, cropEnd) as HS getProcessedData:
    int cropEnd = 0;                   //   cropThreshold 300 (column 50), one shoulder point each side
    bool cropped = false;
    double closestPointRange = kNaN;   // getClosestDistance over processed x (NaN when < 2 points)
    // dataGrouping of isStock charts (DESIGN §16 C21, WdcHcAxis.cpp): while `grouped`, x / y hold the groups (x =
    // group start, y = approximation, NaN = a group of nulls) with crop [0, groups), rawX / rawY the prepared data,
    // groupStart[k] the rawX index of the first point of group k (SeriesGeom::plotPts / markers index).
    bool grouped = false;
    std::vector<double> rawX, rawY;
    std::vector<int> groupStart;
    size_t dataCount() const { return grouped ? rawX.size() : x.size(); }
};

// Highcharts StackItem (HS:40202-40308) reduced to what geometry needs.
struct StackPoint { double bottom = kNaN; double top = kNaN; };   // stack.points[series] = [bottom, top]
struct StackItem {
    double total = 0;                  // sum (normal) or sum |y| (percent) of the stack at x
    double cumulative = kNaN;          // running top after the last series added
    bool isNegative = false;           // lives in the '-'+key stack (column negStacks)
    bool hasValidPoints = false;
    std::map<int, StackPoint> points;  // key = hcIndex; values already scaled by percentStacker
};
struct AxisStacks {
    // key = stackKey ("<type>,<stack>,<xLeft>,<xWidth>" as HS:40071) or "-" + stackKey for the negative stack
    std::map<QString, std::map<double, StackItem>> stacks;
    bool usePercentage = false;
};

struct LayoutContext {
    const ChartInput* in = nullptr;
    QRectF plotBox;                          // final plot box (chart coordinates, CSS px)
    const AxisModel* x = nullptr;            // final X axis (min, max, transA, minPixelPadding)
    const std::vector<AxisModel>* y = nullptr;   // final Y axes, same order as spec yAxes (slot ascending)
    double xPointRange = 0;                  // xAxis.pointRange after setAxisTranslation (0 without columns)
    double xClosestPointRange = kNaN;        // xAxis.closestPointRange (getClosest), NaN if undefined
    std::vector<PreparedSeries> series;      // index = refIndex
    std::vector<AxisStacks> stacks;          // index = Y axis index
    std::vector<double> yThreshold;          // per Y axis: axis.threshold (NaN = undefined)
    std::vector<bool> ySoftThreshold;        // per Y axis

    // Axis.translate (HS:19451) relative to the plot box origin: plotX in [0, plotWidth], plotY in [0, plotHeight].
    double xToPlot(double t) const;
    double yToPlot(int axis, double v) const;       // clamped to [-1e9, 1e9] like HS:32647
    // round(yAxis.getThreshold(threshold)) (HS:20839-20855): threshold clamped into [min, max], then translated.
    double yThresholdPixel(int axis, double threshold) const;
};

// Package C. One SeriesGeom per present series, in ref order; refIndex set. Must be pure (no QPainter).
std::vector<SeriesGeom> buildSeriesGeometry(const LayoutContext& ctx);

// series.stackKey (HS:40071-40080): "<type>,<stack>,<xAxis.left>,<xAxis.width>"; the two x-axis options are
// undefined at WiData, hence "<type>,<stack>,,". The negative column stack is "-" + stackKeyOf(). WdcHcAxis.cpp.
QString stackKeyOf(const SeriesRef& ref);

// Secondary entry points of the series code (WdcHcSeries.cpp, WdcHcColumn.cpp, WdcHcPaint.cpp), shared with
// the tests and the dump. Coordinates of `shapes` are plot-box relative like Highcharts shapeArgs:
// {dataIndex, x, y, w, h, r, brBoxY, brBoxHeight}.
void buildColumnGeometry(const LayoutContext& ctx, int refIndex, SeriesGeom& out,
                         std::vector<std::array<double, 8>>* shapes);
// {width, offset, paddedWidth, columnCount, barW, dense}
std::array<double, 6> columnMetrics(const LayoutContext& ctx, int refIndex);
// ctx.stacks[axis] entry of a stacked series (exact stackKeyOf match), nullptr when absent.
const std::map<double, StackItem>* seriesStackOf(const LayoutContext& ctx, int axis, const SeriesRef& ref,
                                                 bool negative);
bool markerEnabled(std::optional<bool> enabled, double closestPointRangePx, double radius,
                   double enabledThreshold = 2.0);
// Marker symbol of WiData: chart.symbolCounter over the non-column series, by zIndex descending (DESIGN §16 C15)
// for macro charts, by series index for isStock (stockChart, chart page MAI3.09).
QString markerSymbol(const ChartInput& in, int refIndex);
std::vector<double> dashArray(const QString& dashStyle, double strokeWidth);
// SkDashPath with phase 0 on the open contours of `src` (SkContourMeasure lengths: a cubic is halved until its
// control points sit within 0.5 / resScale px of the chord thirds). WdcHcSeries.cpp, used by WdcHcPaint.cpp.
QPainterPath dashPath(const QPainterPath& src, const std::vector<double>& intervals, double resScale);
// Runs of horizontal pieces (lines, flat cubics inside their end points) merged into one line each. WdcHcSeries.cpp.
QPainterPath mergeFlat(const QPainterPath& src);

// ---- B internals shared between WdcHcAxis.cpp and WdcHcLayout.cpp (package C does not use these) ----

struct XAxisState {            // DateTimeAxis state across the two layout runs
    double len = 0, left = 0;
    double min = kNaN, max = kNaN, dataMin = kNaN, dataMax = kNaN;
    double userMin = kNaN, userMax = kNaN;         // hard extremes from WdcRange (NaN = auto)
    double minPadding = 0, maxPadding = 0;          // effective padding (0 when ChartInput::padAuto is false)
    double minRange = kNaN;                         // HS adjustForMinRange
    double tickInterval = 1, closestPointRange = kNaN, pointRange = 0, pointRangePadding = 0;
    double minPointOffset = 0, transA = 1, minPixelPadding = 0;
    hctime::TimeUnit unit;
    std::vector<double> ticks;
    bool hasData = false, single = false;
    int labelRotation = 0;                          // unsquish result; rotated labels are not drawn (never met)
    bool autoRotation = false;                      // axis.autoRotation: unsquish slot < autoRotationLimit (HS:20957)
};

struct YAxisState {            // LinearAxis state
    const YAxisSpec* spec = nullptr;
    double len = 0, top = 0;
    double min = kNaN, max = kNaN, dataMin = kNaN, dataMax = kNaN;
    double threshold = kNaN;
    bool softThreshold = true, hasVisibleSeries = false, seriesHasData = false, usePercentage = false, single = false;
    double tickInterval = 1, transA = 1, tickPixelInterval = 80;
    double offset = 0;                              // Axis.offset from getOffset (HS:21300)
    int tickAmount = 0, finalTickAmt = 0;           // 0 = undefined
    std::vector<double> ticks;
    double labelPx = 9;
    bool hasData() const { return seriesHasData; }  // HS Axis.hasData (showEmpty false)
};

// One tick label as Highcharts keeps it in axis.ticks[pos] across layout runs and the redraw (HS:18380-18460).
struct LabelState {
    QString text;
    bool aligned = false;       // renderUnsquish has set align (center / left); part of the bbox cache key
    double cssWidth = -1;       // CSS width set by renderUnsquish or handleOverflow (textWidth), -1 = none
    double textPxLength = 0;    // width read at creation / text change
    bool styledWidth = false;   // styles.width defined (a px width, or 'auto' after a reset): handleOverflow then
                                // re-applies the slot width while axis.autoRotation is set (HS:18645)
    int lineClamp = 0;          // styles.lineClamp: set with every css({width}) (renderUnsquish: floor(len / (n h)),
                                // handleOverflow: 1), never cleared by css({width: 'auto'}); in the bbox cache key
};

struct LayoutWork {
    const ChartInput* in = nullptr;
    const ChartSpec* spec = nullptr;
    TextMetrics* tm = nullptr;
    std::vector<PreparedSeries> series;             // index = refIndex
    std::vector<int> order;                         // refIndex sorted by hcIndex
    std::vector<std::vector<double>> stackedY;      // per refIndex, per processed point (NaN = none)
    XAxisState x;
    std::vector<YAxisState> y;
    std::vector<AxisStacks> stacks;
    double chartW = 0, chartH = 0;
    double plotLeft = 0, plotTop = 0, plotWidth = 0, plotHeight = 0, marginRight = 0, marginBottom = 0;
    double axisOffset[4] = {0, 0, 0, 0};
    bool hasColumn = false;
    std::map<double, LabelState> xLabels;                  // axis.ticks of X
    std::vector<std::map<double, LabelState>> yLabels;     // axis.ticks of every Y axis
};

// WdcHcAxis.cpp
void ungroupSeries(PreparedSeries& s);              // back to the prepared data (start of Axis.setScale for X)
void xSetScale(LayoutWork& w);                      // getSeriesExtremes + setTickInterval (run 0)
void xSetTickInterval(LayoutWork& w, bool secondPass);
void xSetAxisTranslation(LayoutWork& w);
void ySetScale(LayoutWork& w, int axis);            // buildStacks + getSeriesExtremes + setTickInterval
void ySetTickInterval(LayoutWork& w, int axis);
void ySetAxisTranslation(LayoutWork& w, int axis);
// WdcHcLayout.cpp: layoutChart with a caller-owned TextMetrics (tier A tests pre-seed its cache).
ChartModel layoutChartWith(const ChartInput& in, TextMetrics& tm,
                           std::vector<std::vector<QPointF>>* processed = nullptr);   // see WdcHcApi.h

} // namespace fincept::screens::wdc::hcint
