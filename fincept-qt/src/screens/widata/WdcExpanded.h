#pragma once
// WdcExpanded.h: expanded overlay of a dashboard card (package F). DESIGN §6 ("Màn phóng to"), §6.2, §7.1, §16 C4,
// C7, C16; UI §4; BEH §6; capture meta.expanded (EX[0..54], viewport 1593.33 x 1052.22, DPR 1.8); plan
// reports/F_plan_expanded_single.md §1; API reports/F2_api.md.
//
//   backdrop rgba(0,0,0,.75) over the whole view; box 90 % x 90 % centred, white, radius 4, padding 16, no shadow
//   header 32: title 16/500 uppercase (margin-left 8, ellipsis), calendar box 28 (Đợt 2: drawn, inert), divider,
//   9 range buttons (24 high, gap 8), divider, action cluster "Chia sẻ" (PNG to the clipboard) + "Tải về" (PNG
//   file), close button: circle 24 centred on the top-right corner of the box
//   body: chart (BW-32) x (BH-124), Highcharts size floor x round, Y labels 11 px (ChartInput.expanded); legend
//   4 columns padding 0 40 (LegendStyle::Expanded of package D); no watermark (C7)
//   closes on X, Esc, click on the backdrop; range buttons and legend toggles act on the source card for the
//   session only (BEH §6.2 ĐỀ XUẤT); a dimmed button does nothing; isStock charts pan (WdcRange XPanState)
// Every CSS length is a Blink LayoutUnit (1/64 device px, truncated); flex centring is not truncated.
#include "screens/widata/WdcData.h"
#include "screens/widata/WdcModel.h"
#include "screens/widata/WdcPaneChart.h"
#include "screens/widata/WdcRange.h"

#include <QImage>
#include <QPointer>
#include <QWidget>

#include <functional>
#include <memory>
#include <vector>

class QTimer;

namespace fincept::screens::wdc {

struct CardContext;
class WdcChartHover;
class WdcLegend;
class WdcPopover;

struct ExpandedGeom {   // widget coordinates (= view coordinates), CSS px == Qt logical px
    QRectF backdrop, box, header, title, cluster, rangeCluster, calendarBox, calendarBtn, calendarIcon, divider1,
        rangeGroup, divider2, actions, share, shareIcon, download, downloadIconBox, downloadIcon, close, body;
    double titleBaseline = 0, actionBaseline = 0, shareTextX = 0, downloadTextX = 0;
    std::vector<RangeButtonGeom> buttons;   // YTD .. All
    std::vector<QRectF> paneBoxes;          // DOM chart box per pane (1402 x 823.01 in the capture)
    std::vector<QRectF> paneCharts;         // Highcharts container per pane (floor width, rounded height)
    std::vector<QRectF> paneLegends;        // legend container per pane
    std::vector<QRectF> paneDividers;       // line above pane k (empty for pane 0), MẶC ĐỊNH for 2 panes
};
/// Pure. `view`: size of the overlay; `panes`: 1 or 2 (2: chart height split like the card, MẶC ĐỊNH).
ExpandedGeom layoutExpanded(QSizeF view, double dpr, int panes = 1, MetricsProfile profile = MetricsProfile::Native);

class WdcExpanded : public QWidget {
    Q_OBJECT
  public:
    using OverlayPainter = std::function<void(QPainter&, int pane, const QRectF& chartRect)>;

    /// OverlayFactory for WdcView::set_expand_factory(&WdcExpanded::create): finds the grid card of ctx among the
    /// WdcCard children of `view` and copies its session state.
    static QWidget* create(const CardContext& ctx, QWidget* view);

    /// Dashboard card. `source` (optional WdcCard): button (property kRangeButtonProperty), X window (pan included)
    /// and legend visibility are copied, and changes made here are applied back to it for the session.
    WdcExpanded(const CardSpec& card, std::shared_ptr<const DashData> data, QWidget* parent, QWidget* source = nullptr);
    /// One pane with a free title (chart page "phóng to"): title shown uppercase like every expanded header.
    WdcExpanded(const QString& title, const PaneSpec& pane, std::shared_ptr<const DashData> data, const QString& button,
                bool allExact, QWidget* parent);
    ~WdcExpanded() override;

    QString rangeButton() const { return button_; }
    QStringList dimmedButtons();
    bool pickRange(const QString& button);   // a click on the button; false for a dimmed or unknown label
    void closeOverlay();                     // a click on X: closed(), then WdcView::close_expanded() or deleteLater()
    ExpandedGeom geometryModel() const;
    int paneCount() const { return int(panes_.size()); }
    const ChartModel* chartModel(int pane);
    const ChartInput* chartInput(int pane);
    QRectF chartRect(int pane) const;
    WdcLegend* legend(int pane) const;
    std::vector<bool> seriesVisible(int pane) const;
    void setSeriesVisible(int pane, const std::vector<bool>& visible);
    /// X window of every pane (range button or pan); also applied to the source card.
    void setXWindow(std::optional<qint64> xMin, std::optional<qint64> xMax, bool padAuto);
    void setOverlayPainter(OverlayPainter fn) { overlay_ = std::move(fn); update(); }
    const std::vector<WdcChartHover*>& hovers() const { return hovers_; }

    QImage exportImage(qreal dpr = 2.0);     // white: every pane's chart + legend, names = nameExportPNG
    QString exportFileName() const;          // "<title>.png"
    void copyImageToClipboard();             // "Chia sẻ"
    bool saveImage(const QString& path);     // "Tải về" target (call from a worker thread when possible)
    bool trigger(const QString& part);       // harness: "share", "download", "close", "calendar", range label

  signals:
    void closed();
    void rangePicked(const QString& button);
    void seriesVisibilityChanged(int pane);
    void imageCopied();
    /// "Tải về". With no receiver the overlay asks for a path and writes the PNG in QtConcurrent::run.
    void exportPngRequested(const QImage& image, const QString& suggestedName);
    // hooks of attachChartHover() (WdcTooltip.h), same signatures as WdcCard
    void chartMouse(int pane, int eventType, const QPointF& posInChart, Qt::MouseButtons buttons);
    void chartLeft(int pane);

  protected:
    void paintEvent(QPaintEvent*) override;
    void resizeEvent(QResizeEvent*) override;
    void mouseMoveEvent(QMouseEvent*) override;
    void mousePressEvent(QMouseEvent*) override;
    void mouseReleaseEvent(QMouseEvent*) override;
    void leaveEvent(QEvent*) override;
    void keyPressEvent(QKeyEvent*) override;

  private:
    enum class Part { None, Backdrop, Box, Close, Calendar, Range, Share, Download, Chart };
    struct HitRes { Part part = Part::None; int index = -1; bool operator==(const HitRes&) const = default; };
    void init(std::shared_ptr<const DashData> data);
    void placeLegends();
    void alignPanes();
    void resetHovers();
    void syncSourceVisible(int pane);
    HitRes hitAt(const QPointF& pos) const;
    void activate(const HitRes& h);
    void paintHeader(QPainter& p, const ExpandedGeom& g, qreal dpr);
    void showTip(const QString& text, const QRectF& anchor);

    QString title_;
    bool upper_ = true, zDesc_ = true, allExact_ = false, alignRight_ = false;
    QString legendStyle_;
    QString button_;
    std::vector<WdcPaneChart> panes_;
    std::vector<WdcLegend*> legends_;
    std::vector<WdcChartHover*> hovers_;
    QPointer<QWidget> source_;
    OverlayPainter overlay_;
    HitRes hover_, press_;
    int hoverChart_ = -1;
    QPointer<WdcPopover> tip_;
    QTimer* tipTimer_ = nullptr;
};

} // namespace fincept::screens::wdc
