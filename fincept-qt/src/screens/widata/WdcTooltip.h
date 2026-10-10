#pragma once
// WdcTooltip.h: hover of a chart of the WiData clone (tab VĨ MÔ), package F. Highcharts 12.3.0 semantics:
//
//   hitTest (WdcModel.h)  aio (stickyTracking false): topmost series whose tracker is under the pointer (line band
//                         lineWidth + 2 x snap 10 with round caps, clipped to the plot; marker shapes; column shapes,
//                         direct touch), then its point nearest in x (KD distX, ties to the higher index)
//                         macro (stickyTracking true): column under the pointer, else over every line-type series the
//                         nearest-in-x point, the closest in 2D wins (ties: zIndex, then series index)
//                         HS:26840-26876 findNearestKDPoint, 26998-27066 getHoverData, 33581-33711 KD, 33734-33793 tracker
//   tooltip block         DESIGN §16 C5, capture vimo tooltip.htmlDom: ul radius 6, 12 px, header li rgba(220,220,220,.7)
//                         #21232E bold date, row li rgba(10,10,10,.6) white, padding 8 x 12.8, dot 11.2 px, U+2003,
//                         ": " + bold value (2 decimals) + " (unit)"; box-shadow rgba(166,176,195,.24) 0 1px 2px
//   tooltip position      Tooltip.getPosition HS:24193-24321 (distance 16, columns 6 HS:42305; above, below when
//                         negative, swap sides),
//                         anchor HS:23984-24035 (columns: tooltipPos HS:42860)
//   crosshair             Axis.drawCrosshair HS:21758-21861 + getPlotLinePath HS:19552-19611: 1 px #58667E 8,3,1,3,
//                         x through the point (snap) and y on the hovered axis, z 2 (under the series);
//                         X label HS:55190-55300: #323546, r 4, padding 6, white 11 px %d/%m/%Y, callout arrow 6 px up
//   hover state           lineWidthPlus 1 on the hovered graph (HS:34300-34350), marker radius 4 + 2 with a 1 px white
//                         line and a halo of radius 10 at opacity .25 (HS:26190-26330), column brightness .1; macro:
//                         inactive series at opacity .2 (states.inactive, HS:30887)
//   hide                  hover state and crosshair at once, tooltip after hideDelay 50 ms (no fade animation)
//   click on a point      does nothing (DESIGN §7.1, deliberate)
#include "WdcHcText.h"
#include "WdcModel.h"
#include "WdcRange.h"

#include <QColor>
#include <QEvent>
#include <QLineF>
#include <QObject>
#include <QPainterPath>
#include <QPointer>
#include <QSize>
#include <QString>
#include <QTimer>

#include <cmath>
#include <functional>
#include <memory>
#include <optional>
#include <utility>
#include <vector>

namespace fincept::screens::wdc {

// hitTest() is declared in WdcModel.h and implemented in WdcTooltip.cpp. Its Hit carries:
//   refIndex   index into ChartInput::refs
//   pointIndex index into SeriesGeom::plotPts (the data sorted by x, same order as SeriesData::pts from the builder)
//   pt         plotPts[pointIndex]: CHART coordinates, like every SeriesGeom field (B_internal_api 1.1)
//   t, v       x (UTC ms) and the raw y of the data point (not the stacked top)

/// Highcharts-side facts of a hit: tooltip anchor (plot coordinates, rounded like getAnchor), point.negative.
struct HoverAnchor {
    QPointF anchor;
    bool negative = false;
    bool column = false;
    QColor color;          // point colour: negativeColor below 0 when the series has one, else the series colour
};
std::optional<HoverAnchor> hoverAnchor(const ChartModel& m, const ChartInput& in, const Hit& h);

// ---- tooltip block ----------------------------------------------------------------------------------------------

struct TooltipContent {
    QString header;   // MM/YYYY (thang, ytd), DD/MM/YYYY (ngay, weekly, third party), Qn/YYYY (quy), YYYY (nam)
    QColor dot;
    QString name;     // nameRaw with HTML white-space collapsing
    QString value;    // numberFormat(v, 2): '.' decimal, ',' thousands
    QString unit;     // "(unit)" or empty; DESIGN §8.4 tier suffix " · EST" / " · UNVERIFIED"
};
TooltipContent tooltipContent(const ChartInput& in, const Hit& h, const QColor& dot);

struct TooltipLayout {
    QSizeF size;                  // ul border box (CSS px, LayoutUnit-snapped)
    QSize box;                    // offsetWidth x offsetHeight, used for the placement
    double headerH = 0, rowH = 0; // li heights
    QPointF headerText;           // baseline start of the bold date
    QRectF dot;
    std::vector<std::pair<QPointF, QString>> nameLines;   // baseline starts
    QPointF colon, value, unit;   // baseline starts
    bool wrapped = false;         // the nowrap width exceeded the spacing box: name wraps in its own column
};
/// maxWidth: the chart spacing box width (Tooltip.refresh sets the label CSS width, HS:24575).
TooltipLayout layoutTooltip(const TooltipContent& c, double maxWidth, double dpr,
                            MetricsProfile profile = MetricsProfile::Native);
/// Tooltip.getPosition + updatePosition (rounded). box: offset size; anchor: plot coordinates. Returns the chart
/// coordinates of the top-left corner of the label.
QPointF tooltipPosition(QSize box, QPointF anchor, const QRectF& plotBox, QSizeF chartSize, bool negative,
                        double distance = 16);
/// The SVG label box of the tooltip (callout, radius 6, arrow 6 px toward the anchor). WiData fills it with
/// "transparent" and stroke-width 0, so it is never painted; exposed for the capture checks.
QPainterPath tooltipCalloutPath(QSize box, QPointF topLeft, QPointF anchorChart);

struct TooltipFrame {
    TooltipContent content;
    TooltipLayout layout;
    QPointF topLeft;              // chart coordinates
};
std::optional<TooltipFrame> tooltipFrame(const ChartModel& m, const ChartInput& in, const Hit& h, double dpr);
void paintTooltip(QPainter& p, const TooltipFrame& f, double dpr);

// ---- crosshair ------------------------------------------------------------------------------------------------------

struct CrosshairGeom {
    bool showX = false, showY = false;
    QLineF xLine, yLine;          // chart coordinates, crisp for a 1 px pen
    bool showLabel = false;       // point inside the plot (series.isPointInside)
    QRectF labelBox;              // translateX/Y and the rounded box size
    QPainterPath labelPath;       // rounded box + the 6 px arrow when the anchor is at least 10 px from both ends
    bool labelArrow = false;
    QString labelText;
    QPointF labelTextPos;         // baseline start of the (centred) text
};
/// labelCache: the chart's bounding-box cache (SVGElement.getBBox, HS:10676-10792): the key replaces every digit by
/// '0', so the box of the X label keeps the width of the FIRST date measured in that chart. Without a cache the
/// text is measured fresh.
CrosshairGeom crosshairGeometry(const ChartModel& m, const ChartInput& in, const Hit& h, double dpr,
                                MetricsProfile profile = MetricsProfile::Native, TextMetrics* labelCache = nullptr);
void paintCrosshairLines(QPainter& p, const CrosshairGeom& g);
void paintCrosshairLabel(QPainter& p, const CrosshairGeom& g);

// ---- painting with the hover state -------------------------------------------------------------------------------------

struct HoverFrame {
    std::optional<Hit> hit;                   // hover marker, crosshair, series hover/inactive state
    std::optional<TooltipFrame> tooltip;      // may outlive `hit` by hideDelay
};
/// Paints the whole chart (p in chart coordinates, background already cleared) in Highcharts z order: grid,
/// crosshair lines, series (hover/inactive states, hover marker + halo or brightened column inside the hovered
/// series slot), axis labels, crosshair label, tooltip. Without a hit it is paintChart() + the lingering tooltip.
void paintChartHover(QPainter& p, const ChartModel& m, const ChartInput& in, const HoverFrame& f,
                     TextMetrics* labelCache = nullptr);

// ---- controller of one chart ---------------------------------------------------------------------------------------

class WdcChartHover : public QObject {
    Q_OBJECT
  public:
    static constexpr int kHideDelayMs = 50;   // tooltip.hideDelay (BEH §1.1)
    using Source = std::function<std::pair<const ChartModel*, const ChartInput*>()>;

    explicit WdcChartHover(QObject* parent = nullptr);
    void setSource(Source s) { source_ = std::move(s); }
    void setDevicePixelRatio(double dpr) { dpr_ = dpr > 0 ? dpr : 1; }
    /// Pointer in chart coordinates (the card's chartMouse position).
    void mouseMove(QPointF chartPos);
    void mouseLeave();
    /// Model or window changed: drop everything at once (no delay).
    void reset();
    bool active() const { return frame_.hit.has_value() || frame_.tooltip.has_value(); }
    const HoverFrame& frame() const { return frame_; }
    /// Erases `chartRect` (card coordinates) with the card background and repaints the chart with the hover state.
    void paint(QPainter& p, const QRectF& chartRect);

  signals:
    void updateRequested();

  private:
    void hideNow();
    TextMetrics* labelCache();
    Source source_;
    std::unique_ptr<TextMetrics> labelCache_;   // lives as long as the chart (renderer cache of Highcharts)
    HoverFrame frame_;
    QTimer hideTimer_;
    double dpr_ = 2.0;
};

/// Glue for a card widget with the hooks of WdcCard (package D): signals chartMouse(int pane, int eventType,
/// const QPointF& posInChart, Qt::MouseButtons) and chartLeft(int pane); paneCount(), chartModel(k), chartInput(k),
/// setOverlayPainter(fn), setXWindow(min, max, padAuto). Adds one WdcChartHover per pane and, on isStock charts, the
/// horizontal pan of WdcRange.h (the panned window is not saved; a range button simply sets a new window).
/// Header-only template so that this file does not depend on WdcCard.h.
template <class Card>
std::vector<WdcChartHover*> attachChartHover(Card* card) {
    std::vector<WdcChartHover*> hovers;
    for (int k = 0; k < card->paneCount(); ++k) {
        auto* h = new WdcChartHover(card);
        h->setSource([card, k] { return std::make_pair(card->chartModel(k), card->chartInput(k)); });
        QObject::connect(h, &WdcChartHover::updateRequested, card, [card] { card->update(); });
        hovers.push_back(h);
    }
    auto pan = std::make_shared<XPanState>();
    QObject::connect(card, &Card::chartMouse, card,
                     [card, hovers, pan](int pane, int type, const QPointF& pos, Qt::MouseButtons buttons) {
                         if (pane < 0 || pane >= int(hovers.size())) return;
                         WdcChartHover* h = hovers[size_t(pane)];
                         h->setDevicePixelRatio(card->devicePixelRatioF());
                         if (type == int(QEvent::MouseButtonPress) && (buttons & Qt::LeftButton)) {
                             pan->press(pos);
                         } else if (type == int(QEvent::MouseButtonRelease)) {
                             if (pan->cursorMove()) card->unsetCursor();
                             pan->release();
                         } else if (type == int(QEvent::MouseMove)) {
                             const ChartModel* m = card->chartModel(pane);
                             const ChartInput* in = card->chartInput(pane);
                             if (pan->down() && m && in) {
                                 if (const std::optional<PanAxis> ax = panAxisFrom(*m, *in)) {
                                     if (const auto w = pan->move(pos, m->plotBox, *ax)) {
                                         card->setXWindow(qint64(std::llround(w->first)),
                                                          qint64(std::llround(w->second)), false);
                                         for (WdcChartHover* other : hovers) other->reset();
                                     }
                                     if (pan->cursorMove()) card->setCursor(Qt::SizeAllCursor);   // CSS 'move'
                                 }
                             }
                             h->mouseMove(pos);
                         }
                     });
    QObject::connect(card, &Card::chartLeft, card, [hovers](int pane) {
        if (pane >= 0 && pane < int(hovers.size())) hovers[size_t(pane)]->mouseLeave();
    });
    card->setOverlayPainter([hovers](QPainter& p, int pane, const QRectF& chartRect) {
        if (pane >= 0 && pane < int(hovers.size()) && hovers[size_t(pane)]->active())
            hovers[size_t(pane)]->paint(p, chartRect);
    });
    return hovers;
}

} // namespace fincept::screens::wdc
