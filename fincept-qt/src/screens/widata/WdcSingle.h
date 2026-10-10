#pragma once
// WdcSingle.h: chart page of the WiData clone (package F), DESIGN §16 C4: the chart area of the "Dữ liệu vĩ mô" page
// opened on MAI3.09 (capture widata_cap_vimo_20261003.json mainDom, layout_const single_charts[0].page), and the
// same page for any card ("Mở dạng biểu đồ đơn"). Not built in wave 1: indicator tree, data table, "Sửa đồ thị".
//
//   header 32: title 16/500 sentence case (opsz 14 outlines, webTextExactWidth); action cluster #F6F5F4 padding 4 with
//   "So sánh biến động" (Highstock compare percent, WdcPaneChart; tooltip: changed value in % + raw value in
//   brackets), "Sao chép liên kết" (wdc://chart/<id> | wdc://card/<dash>/<key> to the clipboard), "Tuỳ chỉnh"
//   (disabled, Đợt 2), "Tải về" (PNG), full screen (WdcExpanded over the page's parent, same window)
//   range row: calendar box 28 (inert), divider, 9 buttons 28 high gap 4 (default 3Y), margin-bottom 12; window of
//   the vimo page (windowForPage, WdcRange.h: x.max = refMax)
//   chart: full width; height follows the frame at the capture ratio 391.34 / 812.47 (391.34 at the capture width),
//   capped so every legend stays visible (MẶC ĐỊNH đợt 4); Highcharts floor x round; legend LegendStyle::Single in
//   (5 % W, chart bottom, 90 % W, 36); bottom padding 10; tooltip / crosshair / pan as on the cards
//   2-pane cards: both panes stacked (chart, legend, divider 12 + 1 device px + 8, chart, legend), one window, panes
//   aligned right when the card asks for it (DESIGN §4.6) (MẶC ĐỊNH đợt 4)
//   back: Esc (or a tab click through openSingleChart / openCardSingle) returns to the dashboard
#include "screens/widata/WdcData.h"
#include "screens/widata/WdcModel.h"
#include "screens/widata/WdcPaneChart.h"
#include "screens/widata/WdcRange.h"

#include <QImage>
#include <QPointer>
#include <QWidget>

#include <functional>
#include <memory>
#include <optional>
#include <vector>

class QTimer;

namespace fincept::screens::wdc {

class WdcChartHover;
class WdcLegend;
class WdcPopover;
class WdcView;

struct SingleGeom {   // page content coordinates: origin = top-left of the chart column (mainDom)
    struct Btn { QString id, text; QRectF rect, icon; double textX = 0; };
    QRectF frame, header, title, actions, row, calendarBox, calendarBtn, calendarIcon, divider, rangeGroup, chartBox,
        chart, legend;                       // chartBox, chart, legend: pane 0
    double titleBaseline = 0, actionBaseline = 0;
    std::vector<Btn> actionButtons;          // compare, copy_link, customize, download, fullscreen
    std::vector<RangeButtonGeom> buttons;    // YTD .. All, 28 high, gap 4
    std::vector<QRectF> paneBoxes, paneCharts, paneLegends, paneDividers;   // per pane (divider of pane 0 empty)
};
/// Pure. width: chart column width (812.47 in the capture); title: text of the h6 (its width sizes the box);
/// chartH: height of every pane's chart box; panes: 1 or 2.
SingleGeom layoutSingle(double width, double dpr, const QString& title, MetricsProfile profile = MetricsProfile::Native,
                        double chartH = 391.34, int panes = 1);
/// Pure. Chart height of each pane for a content box (page minus its padding): width x 391.34 / 812.47, at most what
/// leaves header, range row, legends and dividers visible, at least 120 (MẶC ĐỊNH đợt 4).
double singleChartHeight(QSizeF content, int panes, double dpr);

class WdcSingle : public QWidget {
    Q_OBJECT
  public:
    using OverlayPainter = std::function<void(QPainter&, int pane, const QRectF& chartRect)>;
    static constexpr double kInset = 16;   // page padding around the chart column (MẶC ĐỊNH)

    explicit WdcSingle(QWidget* parent = nullptr);
    ~WdcSingle() override;

    /// MAI3.09: spec = LayoutsDoc::single(id); data = dash_single.json (or single_<id>.json), may arrive later.
    void setChart(const SingleChartSpec& spec, std::shared_ptr<const DashData> data);
    /// Any card: every pane of the card (2-pane cards stacked), dashboard data.
    void setCard(const QString& dashId, const CardSpec& card, std::shared_ptr<const DashData> data);
    void setData(std::shared_ptr<const DashData> data);
    /// Follow the parent's size below `top` (the "Bố cục:" bar stays visible).
    void setFollowParent(int top);

    QString link() const { return link_; }
    QString title() const { return title_; }
    QString rangeButton() const { return button_; }
    QStringList dimmedButtons();
    bool pickRange(const QString& button);
    bool compare() const;
    void setCompare(bool on);
    bool trigger(const QString& actionId);   // compare | copy_link | customize (false) | download | fullscreen | range label
    SingleGeom geometryModel() const;        // page content coordinates
    QPointF contentOrigin() const { return {kInset, kInset}; }
    int paneCount() const { return int(panes_.size()); }
    const ChartModel* chartModel(int pane = 0);
    const ChartInput* chartInput(int pane = 0);
    QRectF chartRect(int pane = 0) const;    // widget coordinates
    WdcLegend* legend(int pane = 0) const;
    void setXWindow(std::optional<qint64> xMin, std::optional<qint64> xMax, bool padAuto);
    void setOverlayPainter(OverlayPainter fn) { overlay_ = std::move(fn); update(); }
    const std::vector<WdcChartHover*>& hovers() const { return hovers_; }
    QImage exportImage(qreal dpr = 2.0);     // every pane: chart + legend, names = nameExportPNG
    QPointer<QWidget> expandedOverlay() const { return expanded_; }

  signals:
    void backRequested();
    void linkCopied(const QString& link);
    void compareChanged(bool on);
    void rangePicked(const QString& button);
    void expandRequested();
    void exportPngRequested(const QImage& image, const QString& suggestedName);   // no receiver: save dialog
    void chartMouse(int pane, int eventType, const QPointF& posInChart, Qt::MouseButtons buttons);
    void chartLeft(int pane);

  protected:
    bool eventFilter(QObject* o, QEvent* e) override;
    void paintEvent(QPaintEvent*) override;
    void resizeEvent(QResizeEvent*) override;
    void mouseMoveEvent(QMouseEvent*) override;
    void mousePressEvent(QMouseEvent*) override;
    void mouseReleaseEvent(QMouseEvent*) override;
    void leaveEvent(QEvent*) override;
    void keyPressEvent(QKeyEvent*) override;

  private:
    enum class Part { None, Action, Calendar, Range, Chart };
    struct HitRes { Part part = Part::None; int index = -1; bool operator==(const HitRes&) const = default; };
    void reset(const QString& title, const std::vector<PaneSpec>& panes, std::shared_ptr<const DashData> data,
               const QString& button, bool zIndexDesc, bool allExact, bool alignRight);
    void applyWindow();
    void place();
    void alignPanes();
    void resetHovers();
    void rebuildHovers();
    void setPaneVisible(int pane, const std::vector<bool>& visible);
    std::optional<qint64> refMax() const;
    HitRes hitAt(const QPointF& pos) const;
    void activate(const HitRes& h);
    void openExpanded();
    void showTip(const QString& text, const QRectF& anchorInWidget, int hideAfterMs = 0);

    QString title_, link_, button_;
    bool zDesc_ = false, allExact_ = false, alignRight_ = false;
    int followTop_ = -1;
    std::optional<CardSpec> card_;           // setCard: the card itself (full screen opens all of its panes)
    std::vector<WdcPaneChart> panes_;        // sized once per reset(): pointers into it stay valid until the next
    std::vector<WdcLegend*> legends_;
    std::vector<WdcChartHover*> hovers_;
    OverlayPainter overlay_;
    HitRes hover_, press_;
    int hoverChart_ = -1;
    QPointer<WdcPopover> tip_;
    QTimer* tipTimer_ = nullptr;
    QPointer<QWidget> expanded_;
};

/// Host glue (no change to WdcView): the page becomes a child of `view` under its "Bố cục:" bar, no tab is
/// highlighted, a tab click or Esc closes it and restores the tab. openSingleChart loads dash_single.json (fallback
/// single_<id>.json) in QtConcurrent::run; openCardSingle uses view->dash_data(dash). nullptr when the spec is unknown.
WdcSingle* openSingleChart(WdcView* view, const QString& singleId);
WdcSingle* openCardSingle(WdcView* view, const QString& dashId, const QString& cardKey);

} // namespace fincept::screens::wdc
