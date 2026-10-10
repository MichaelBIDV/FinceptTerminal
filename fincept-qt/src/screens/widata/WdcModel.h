#pragma once
// WdcModel.h, frozen C++ contract between the packages of the WiData clone (tab VĨ MÔ).
//
// Verbatim from DESIGN.md §5.4 (widata_clone_spec, v1.2). Owner: package B. Any change goes through
// DESIGN §13 and must be announced to every package (C, D, E, F, G, H) before it lands.
// Every Wdc* file uses only QtCore/QtGui/QtWidgets so the offscreen harness can build the module alone.
#include <QColor>
#include <QHash>
#include <QJsonObject>
#include <QPainterPath>
#include <QPointF>
#include <QRectF>
#include <QSizeF>
#include <QString>

#include <array>
#include <optional>
#include <utility>
#include <vector>

class QPainter;

namespace fincept::screens::wdc {

enum class SeriesType { Spline, AreaSpline, Column };
enum class Stacking   { None, Normal, Percent };
enum class Status     { Ok, Partial, Missing };
enum class MetricsProfile { Native, WidataDpr18 };

struct YAxisSpec  { int slot; QString format; std::optional<int> tickAmount; bool startOnTick, endOnTick;
                    double minPadding, maxPadding; double labelPx; std::optional<double> labelY;
                    double distance, margin; QColor gridColor; QString gridDash; };
struct ChartSpec  { bool isStock; std::array<double,4> spacing; std::array<std::optional<double>,4> margin;
                    QHash<QString,QString> dtFormats; bool shiftLabelWhenColumn; double xMinPadding, xMaxPadding;
                    std::vector<YAxisSpec> yAxes; double columnRadius, pointPadding, groupPadding, fillOpacity;
                    double markerRadius; bool sticky, inactiveFade; };
struct SeriesRef  { QString sid; int si; QString nameRaw; SeriesType type; Stacking stacking; QString stack;
                    int slot; QColor color; std::optional<QColor> negativeColor; double lineWidth;
                    QString dashStyle; bool marker; int zIndex; QString unit; QString dateType; QString kind; };
struct SeriesData { Status status; QString tier; QString freq; std::vector<QPointF> pts; /* x = t_ms, y = NaN cho null */
                    std::vector<std::pair<qint64,QString>> breaks; };

struct ChartInput { const ChartSpec* spec; std::vector<const SeriesRef*> refs; std::vector<const SeriesData*> data;
                    std::vector<bool> visible;                    // legend bật/tắt
                    std::optional<qint64> xMin, xMax; bool padAuto; // từ WdcRange
                    QSizeF size; MetricsProfile profile; bool expanded /* nhãn Y 11 px, lineWidth giữ theo spec */; };

struct Tick       { double value; double pixel; QString text; QPointF labelPos; bool visible; };
struct AxisModel  { int slot; bool hasData; double min, max, tickInterval, transA, offset, minPixelPadding;
                    std::vector<Tick> ticks; };
struct SeriesGeom { int refIndex; QPainterPath graph, area; std::vector<QPainterPath> zoneGraphs, zoneAreas;
                    std::vector<QPainterPath> columns; std::vector<QRectF> markers; QString symbol;
                    std::vector<QPointF> plotPts; /* toạ độ pixel từng điểm, cho hitTest */ };
struct ChartModel { QRectF plotBox; AxisModel x; std::vector<AxisModel> y; std::vector<SeriesGeom> series;
                    bool allMissing; };

ChartModel  layoutChart(const ChartInput&);                       // gói B (+ builder của gói C), thuần
void        paintChart(QPainter&, const ChartModel&, const ChartInput&);   // gói C
struct Hit  { int refIndex; int pointIndex; QPointF pt; qint64 t; double v; };
std::optional<Hit> hitTest(const ChartModel&, const ChartInput&, QPointF pos);  // gói F, theo BEH §1.3
QJsonObject dumpChart(const ChartModel&);                        // gói B, khoá trùng dump oracle (gói G)

} // namespace fincept::screens::wdc
