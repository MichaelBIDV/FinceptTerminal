#pragma once
// WdcRange.h: time range of a card of the WiData clone (tab VĨ MÔ), package F.
//
//   windowFor            BEH §3.1, §3.2 (ICT, start of the month of refMax minus N, max = 23:59:59 of refMax's day;
//                        All: aio padded by the axis (padAuto), all_exact cards fit the data)      DESIGN §7.2, §7.3
//   default button       Card.default_range.button (layout_const, BEH §3.1), overridden by the local choice
//   dimmed buttons       BEH §6.3 (ĐỀ XUẤT): dimmed <=> button length <= 2 x period of the finest visible series
//   local store          one button per (dash_id, card_key) (BEH §4.1), JSON; disk I/O only in worker threads
//   popover              9 buttons YTD..All, geometry of the expanded header (UI §4.3), tokens DESIGN §6.1
//   isStock pan          Pointer.drag HS:26673-26741, Chart.pan HS:38968-38994, Chart.transform HS:39013-39160
//                        (x only, scale 1, clamp floor/ceiling); not saved across sessions (DESIGN §7.1)
//
// Every function here is pure except WdcRangePopover (a QWidget) and the two file helpers of WdcRangeStore.
#include "WdcModel.h"

#include <QHash>
#include <QJsonObject>
#include <QPointF>
#include <QPointer>
#include <QRectF>
#include <QString>
#include <QStringList>
#include <QWidget>

class QPainter;

#include <memory>
#include <optional>
#include <utility>
#include <vector>

namespace fincept::screens::wdc {

struct DashData;   // WdcData.h

// ---- window ----------------------------------------------------------------------------------------------------

/// X window handed to the engine (ChartInput::xMin/xMax/padAuto). nullopt = let the axis use the data extremes.
struct XWindow {
    std::optional<qint64> xMin, xMax;
    bool padAuto = false;
};

/// "YTD", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "10Y", "All" (order of the expanded header and the popover).
const QStringList& rangeButtons();
bool isRangeButton(const QString& label);

/// BEH §3.2 windowFor. Times are UTC ms; the calendar arithmetic runs in ICT (UTC+7, no DST since 1975).
XWindow windowFor(const QString& button, qint64 refMaxMs, bool exactAll);
/// Card-level helper: no refMax (no series with data) gives the auto window of the axis.
XWindow windowForCard(const QString& button, std::optional<qint64> refMaxMs, bool exactAll);
/// Window of the chart page (capture vimo, MAI3.09 3Y: refMax 30/09/2026 00:00 UTC gives x.min 01/10/2023 00:00 ICT
/// = 1696093200000 and x.max = refMax = 1790726400000, FACT): max = refMax itself, min = 00:00 ICT of the day after
/// (refMax minus N years / months) (SUY LUẬN from the one capture: "start of the next month" gives the same there);
/// YTD = 01/01 of refMax's year; All as windowFor. No refMax: the auto window of the axis.
XWindow windowForPage(const QString& button, std::optional<qint64> refMaxMs, bool exactAll);
/// Local choice when valid, else the card default (layout_const default_range.button), else "3Y".
QString resolveRangeButton(const QString& stored, const QString& cardDefault);

// ---- dimmed buttons (BEH §6.3, ĐỀ XUẤT) ------------------------------------------------------------------------

/// Period in months of a frequency: D, W, TP = 0; M, YTD = 1; Q = 3; Y = 12. Falls back to SeriesRef::dateType
/// (ngay 0, thang 1, quy 3, nam 12) when `freq` is empty or unknown; -1 when both are unknown.
int freqPeriodMonths(const QString& freq, const QString& dateType = QString());
/// Finest (smallest) period over the visible series that have data, across every pane of a card. 0 when none.
int finestPeriodMonths(const std::vector<const ChartInput*>& panes);
/// Length of a button in months: 3M 3 ... 10Y 120, YTD = month of refMax in ICT (1..12), All = INT_MAX.
int rangeButtonMonths(const QString& button, std::optional<qint64> refMaxMs);
/// dimmed <=> months(button) <= 2 x finestMonths. A click on a dimmed button does nothing.
bool rangeButtonDimmed(const QString& button, int finestMonths, std::optional<qint64> refMaxMs);
/// The dimmed labels of the 9 buttons for a card.
QStringList dimmedRangeButtons(const std::vector<const ChartInput*>& panes, std::optional<qint64> refMaxMs);

// ---- local store per (dash_id, card_key) --------------------------------------------------------------------------

class WdcRangeStore {
  public:
    QString get(const QString& dashId, const QString& cardKey) const;   // empty when nothing saved
    void set(const QString& dashId, const QString& cardKey, const QString& button);
    void remove(const QString& dashId, const QString& cardKey);
    bool isEmpty() const { return map_.isEmpty(); }
    int size() const;

    /// {"schema": "wdc_range/1", "ranges": {"<dash_id>": {"<card_key>": "<button>"}}}
    QJsonObject toJson() const;
    /// Unknown labels and malformed entries are skipped. Returns false when the object is not a store.
    bool fromJson(const QJsonObject& o);

    // Blocking file helpers (atomic write with QSaveFile). Call them from a worker thread (QtConcurrent::run),
    // never from the UI thread (TASKS E: no disk I/O on the UI thread).
    bool loadFile(const QString& path, QString* error = nullptr);
    bool saveFile(const QString& path, QString* error = nullptr) const;

  private:
    QHash<QString, QHash<QString, QString>> map_;
};

// ---- popover of the card calendar button (DESIGN §6.1 tokens, UI §4.3 button geometry) ---------------------------

struct RangeButtonGeom {
    QString label;
    QRectF rect;          // `height` high, width max(height, text + 8), radius 4
    double textX = 0;     // left of the (centred) text
    double baseline = 0;  // Blink baseline of a 13 px line of height 20.43 centred in the box (flex, align center)
};
/// The 9 buttons laid out in one row from `origin` (top-left of the first button), margin-left `gap` between buttons.
/// Blink box model: every length is a LayoutUnit (1/64 device px, truncated), the text width is rounded up.
/// Native: the real DPR. WidataDpr18 reproduces the capture (1.8 device px per CSS px) for the tier A test.
/// Two sets of numbers (F_plan §2.2): expanded header and popover 24 high, gap 8 (EX[14..22]); chart page 28 high,
/// gap 4 (capture vimo mainDom range_row).
std::vector<RangeButtonGeom> layoutRangeButtons(QPointF origin, double dpr,
                                                MetricsProfile profile = MetricsProfile::Native,
                                                double height = 24, double gap = 8);
/// Width of the whole row (first left to last right) for the same arguments.
double rangeButtonsWidth(double dpr, MetricsProfile profile = MetricsProfile::Native, double height = 24,
                         double gap = 8);
/// Paints one button (BEH §6.2: selected #21232E white text; dimmed opacity .5, rgba(166,176,195,.16), #58667E; idle
/// transparent #21232E). hover/pressed: DESIGN §6.1 tokens (HOVER_CSS.md has no rule for these buttons). The painter
/// font is set here (Inter 13/400).
void paintRangeButton(QPainter& p, const RangeButtonGeom& b, bool selected, bool dimmed, bool hover, bool pressed);

class WdcRangePopover : public QWidget {
    Q_OBJECT
  public:
    explicit WdcRangePopover(QWidget* owner);
    /// current: highlighted button; dimmed: labels drawn dimmed and not clickable.
    void setState(const QString& current, const QStringList& dimmed);
    /// Places the FRAME below `anchorGlobal` (4 px gap, left-aligned, kept on the owner's screen) and shows it.
    void showBelow(const QRect& anchorGlobal);
    QSizeF frameSize() const;                 // padding 8 + row of buttons + 1 device px border
    QRectF frameRect() const;                 // frame inside the widget (the rest is the shadow margin)
    std::vector<RangeButtonGeom> buttons() const;
    QString current() const { return current_; }
    QStringList dimmed() const { return dimmed_; }
    /// Harness hook: same as a click on the button. Returns false (and emits nothing) for a dimmed label.
    bool pick(const QString& label);
    QImage renderImage(qreal dpr = 2.0);      // frame alone, for the harness

  signals:
    void picked(const QString& label);

  protected:
    void paintEvent(QPaintEvent*) override;
    void mouseMoveEvent(QMouseEvent*) override;
    void mousePressEvent(QMouseEvent*) override;
    void mouseReleaseEvent(QMouseEvent*) override;
    void leaveEvent(QEvent*) override;
    void keyPressEvent(QKeyEvent*) override;

  private:
    void paintFrame(QPainter& p, qreal dpr);
    int buttonAt(const QPointF& pos) const;
    QString current_;
    QStringList dimmed_;
    int hover_ = -1, press_ = -1, focus_ = -1;
    bool focusVisible_ = false;
    qreal margin_ = 0;
};

/// Dynamic property holding the current range button of a card widget (set by applyCardRange and WdcExpanded).
inline constexpr char kRangeButtonProperty[] = "wdcRangeButton";

// ---- glue for the card hook of the view (package E set_card_hook, package D WdcCard) --------------------------------
// Header-only templates so that this file does not depend on WdcCard.h. Card needs refMax(), setXWindow(), paneCount(),
// chartInput(k).

/// Applies the stored (else default) button of a card: X window of every pane (DESIGN §7.2, §7.3). Returns the button.
template <class Card>
QString applyCardRange(Card* card, const QString& dashId, const QString& cardKey, const QString& defaultButton,
                       bool allExact, const WdcRangeStore& store) {
    const QString b = resolveRangeButton(store.get(dashId, cardKey), defaultButton);
    const XWindow w = windowForCard(b, card->refMax(), allExact);
    card->setXWindow(w.xMin, w.xMax, w.padAuto);
    card->setProperty(kRangeButtonProperty, b);   // read by WdcExpanded (button of the card in this session)
    return b;
}

/// Opens the 9-button popover under the card calendar button (BEH §4.1): current button highlighted, dimmed buttons
/// from the visible series of every pane; a pick is stored per (dash_id, card_key), applied, then `persist` runs (the
/// owner writes the store from a worker thread). The popover deletes itself (deleteLater) when closed, so the
/// returned pointer is guarded: it becomes null once the popover is gone.
template <class Card, class Persist>
QPointer<WdcRangePopover> openCardRangePopover(Card* card, const QRect& anchorGlobal, const QString& dashId,
                                               const QString& cardKey, const QString& defaultButton, bool allExact,
                                               WdcRangeStore* store, Persist persist) {
    std::vector<const ChartInput*> panes;
    for (int k = 0; k < card->paneCount(); ++k) panes.push_back(card->chartInput(k));
    auto* pop = new WdcRangePopover(card);
    pop->setAttribute(Qt::WA_DeleteOnClose, true);
    pop->setState(resolveRangeButton(store->get(dashId, cardKey), defaultButton), dimmedRangeButtons(panes, card->refMax()));
    QObject::connect(pop, &WdcRangePopover::picked, card, [=](const QString& b) {
        store->set(dashId, cardKey, b);
        applyCardRange(card, dashId, cardKey, defaultButton, allExact, *store);
        persist();
    });
    pop->showBelow(anchorGlobal);
    return pop;
}

// ---- "So sánh biến động" of the chart page: the tooltip keeps the raw value (MẶC ĐỊNH đợt 4) ---------------------
// WdcPaneChart registers each compare copy it hands to the engine (y' = 100 y / base - 100) with its raw series and
// unit; tooltipContent (WdcTooltip.cpp) then shows "<b>y'</b> (%) (gốc <y> <unit>)". Calls are locked.

void registerCompareSource(const SeriesData* shown, const SeriesData* raw, const QString& rawUnit);
void unregisterCompareSource(const SeriesData* shown);
/// `unit` + " (gốc <raw y at t, 2 decimals> <raw unit>)" when `shown` is a registered compare copy, else `unit`.
QString compareTooltipUnit(const QString& unit, const SeriesData* shown, qint64 t);

// ---- tier of one point for the tooltip suffix " · EST" / " · UNVERIFIED" (DESIGN §8.4, §16 C19) -------------------
// SeriesData has one tier per series, dash_<id>.json adds tier_spans (EST months inside FACT series: 27 series of the
// frozen build, e.g. M2 from 10/2025). The holder of a DashData registers its entries while ChartInputs point into
// it (reference counted, locked): WdcPaneChart does it for the chart page and the expanded overlay, WdcCard::setData
// for the grid tooltips.
void registerDashTiers(const DashData& d);
void unregisterDashTiers(const DashData& d);
/// The tier_spans tier containing t (the last matching span, as formatters.js tierSuffix), else d->tier. A compare
/// copy uses the spans of its raw series.
QString pointTier(const SeriesData* d, qint64 t);

// ---- (t, v) behind the plotted points of grouped isStock series, for the hit test (DESIGN §16 C21) ------------------
// layoutChartAtDpr(in, dpr, &processed) (WdcHcApi.h) gives, for each plotPts index, the (t, v) Highstock holds: group
// start and average for a grouped series, the data otherwise. The owner of a ChartModel (WdcCard pane, WdcPaneChart)
// registers them under the model's address after each layout and unregisters before the model goes; hitTest (package
// F) reads t and v there instead of the first raw point of the group. Calls are locked.
using ProcessedPoints = std::vector<std::vector<QPointF>>;
void registerProcessedPoints(const ChartModel* m, std::shared_ptr<const ProcessedPoints> processed);
void unregisterProcessedPoints(const ChartModel* m);
/// processed[refIndex][index] of the model, when registered with `plotCount` entries for that series and finite there.
std::optional<QPointF> processedPoint(const ChartModel* m, int refIndex, int index, size_t plotCount);

// ---- horizontal pan of the 6 isStock cards --------------------------------------------------------------------------

/// X axis state the pan needs, chart coordinates (CSS px == Qt logical px).
struct PanAxis {
    double min = 0, max = 0, transA = 1, minPixelPadding = 0;   // AxisModel of the X axis
    double len = 0, pos = 0;                                    // plot width, plot left
    double dataMin = 0, dataMax = 0;                            // x extremes of the visible series (all points)
    double minPadding = 0, maxPadding = 0;                      // isStock: 0, 0
    std::optional<double> optMin, optMax;                       // xAxis.options.min/max (WiData: never set)
};
/// Built from the laid-out chart: min/max/transA/minPixelPadding of model.x, plot box, data extremes of the visible
/// present series, paddings of the spec. nullopt when the chart is not a pannable isStock chart or has no data.
std::optional<PanAxis> panAxisFrom(const ChartModel& m, const ChartInput& in);
/// Chart.transform for the X axis with scale 1 and `to.x = dx` (HS:39013-39160). Returns the new extremes, or
/// nullopt when Highcharts would not call setExtremes (unchanged, or blocked by floor/ceiling).
std::optional<std::pair<double, double>> panTransform(const PanAxis& a, double dx);

/// Mouse state machine of Pointer.dragStart/drag/drop for panning (no zoom, no selection marker).
class XPanState {
  public:
    void press(QPointF chartPos);
    /// One mousemove while the button is down. plot: plot box in chart coordinates.
    std::optional<std::pair<double, double>> move(QPointF chartPos, const QRectF& plot, const PanAxis& axis);
    void release();
    bool down() const { return down_; }
    bool cursorMove() const { return cursorMove_; }   // chart.container cursor 'move' after the first pan step
    double mouseDownX() const { return downX_; }
    double hasDragged() const { return hasDragged_; }

  private:
    bool down_ = false, cursorMove_ = false;
    double downX_ = 0, downY_ = 0, hasDragged_ = 0;
};

} // namespace fincept::screens::wdc
