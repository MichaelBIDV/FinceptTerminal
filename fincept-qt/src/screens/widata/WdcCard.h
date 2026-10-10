#pragma once
// WdcCard.h: one dashboard card of the WiData clone (package D): frame, header (uppercase 12/600 title cut with
// "…", 3 or 4 icon buttons), 1 or 2 chart panes with divider, one legend per pane, "[CẦN DATA]" state, title
// tooltip, gear menu (DESIGN §6, §6.1, §7.1, §8.4, §16 C4; UI §3; BEH §4).
//
// The card does not compute axes or paths: it builds a ChartInput per pane and calls layoutChart / paintChart of
// WdcModel.h (packages B and C). With align_panes_right it calls layoutChart twice so that the right edges of
// the two plot areas line up (DESIGN §4.6 "Lề canh hàng"). The X window comes from WdcRange (package F) through
// setXWindow(). Tooltip and crosshair (package F) hook in through chartMouse() and setOverlayPainter().
// No resize handle and no watermark are drawn (DESIGN §6.1, §16 C7).
//
// Đợt 3 (DESIGN §16 C18): the charts are laid out and painted off the UI thread by WdcRenderService (WdcRender.h)
// into images keyed by (card, data, window, visible series, size, DPR); paintEvent only blits them. Until the
// images arrive a pane is blank ("đang nạp"), never "[CẦN DATA]"; the previous image stays while a new window or
// size is rendered. chartModel()/chartInput() still lay out synchronously when asked before the images arrive
// (hover, range popover). Header buttons and legend items follow the real stylesheet (A/HOVER_CSS.md, C16).
#include "screens/widata/WdcData.h"
#include "screens/widata/WdcIcons_p.h"
#include "screens/widata/WdcLegend.h"
#include "screens/widata/WdcModel.h"
#include "screens/widata/WdcRender.h"

#include <QImage>
#include <QPointer>
#include <QStringList>
#include <QWidget>

#include <functional>
#include <memory>
#include <optional>
#include <vector>

class QTimer;

namespace fincept::screens::wdc {

// The layout spec of a card (CardSpec, PaneSpec) and the dashboard data (DashData) are the types of WdcData.h
// (package E, DESIGN §4.6, §4.7). The view's card factory builds a card with:
//     auto* w = new WdcCard(parent); w->setSpec(*ctx.card, ctx.dashId); w->setData(ctx.data);

// ---- pure geometry (CSS px == Qt logical px), compared with the capture DOM by the harness -------------------
struct CardButtonGeom { QString id; Icon icon; QRectF button, iconRect; };
struct CardPaneGeom {
    QRectF pane;    // css-xuy27p (fractional height)
    QRectF chart;   // Highcharts container: x0, pane top, floor(cw), round(paneH) (Highcharts getChartSize)
    QRectF legend;  // legend container (x0, pane bottom + 12, cw, 36)
    QRectF divider; // line above this pane (empty for pane 0)
};
struct CardGeom {
    QRectF frame, content, header, title, cluster;
    std::vector<CardButtonGeom> buttons;
    std::vector<CardPaneGeom> panes;
    qreal border = 1;
};
CardGeom layoutCard(const CardSpec& spec, const QRectF& rect, qreal dpr);
Icon cardButtonIcon(const QString& id);

class WdcCard : public QWidget {
    Q_OBJECT
  public:
    using OverlayPainter = std::function<void(QPainter&, int pane, const QRectF& chartRectInCard)>;

    explicit WdcCard(QWidget* parent = nullptr);
    ~WdcCard() override;

    /// Copies the spec (the view's LayoutsDoc may be replaced later). dashId keys the render cache.
    void setSpec(const CardSpec& spec, const QString& dashId = QString());
    const CardSpec& spec() const { return *spec_; }
    QString dashId() const { return dashId_; }
    /// Data of the card's dashboard; null = loading or no build (every pane shows "[CẦN DATA]").
    void setData(std::shared_ptr<const DashData> data);
    /// Data still loading: panes stay blank instead of "[CẦN DATA]" while there is no data (DESIGN §16 C18).
    void setLoading(bool loading);
    bool loading() const { return loading_; }
    /// X window of every pane (from WdcRange). nullopt min/max = let the engine use the data extremes.
    void setXWindow(std::optional<qint64> xMin, std::optional<qint64> xMax, bool padAuto);
    /// Last t of OUR data over ok/partial series of every pane (DESIGN §7.2); nullopt when nothing has data.
    std::optional<qint64> refMax() const;

    int paneCount() const { return int(spec_->panes.size()); }
    QRectF chartRect(int pane) const;
    bool paneAllMissing(int pane) const;
    const ChartModel* chartModel(int pane);  // lays out on demand
    const ChartInput* chartInput(int pane);
    std::vector<bool> seriesVisible(int pane) const;
    void setSeriesVisible(int pane, const std::vector<bool>& visible);
    void setOverlayPainter(OverlayPainter fn);
    CardGeom geometryModel() const;
    WdcLegend* legend(int pane) const;
    /// Card rendered alone (frame, header, panes, legends) at the given device pixel ratio (charts rendered now).
    QImage renderImage(qreal dpr = 2.0);
    /// Renders the chart images of the current parameters on the calling (UI) thread if they are not shown yet.
    void renderNow();
    /// Every pane shows the chart of the current parameters, or has nothing to draw ("[CẦN DATA]").
    bool rendered() const;
    /// Priority of this card's render jobs (higher first); the view gives the cards nearer the top more.
    void setRenderPriority(int p) { renderPriority_ = p; }
    /// Identity of the data build (view: build dir + generated). Non-empty enables the disk cache (WdcCache.h).
    void setCacheTag(const QByteArray& tag) { cacheTag_ = tag; }
    /// What painting the charts shown now cost on a render thread (ms); the view keeps hover cheap above a budget.
    double lastPaintMs() const { return lastPaintMs_; }

    // harness hooks
    bool titleElided() const;
    bool titleTipVisible() const;
    bool menuVisible() const;
    QStringList menuItemIds() const;
    void openMenu();
    void triggerMenu(const QString& id);
    bool sourceInfoVisible() const;

  signals:
    void calendarRequested(const QString& key, const QRect& anchorGlobal);
    void expandRequested(const QString& key);
    void syncRequested(const QString& key);         // [macro] "Cached" button: reload this card's data
    void refreshRequested(const QString& key);      // gear "Làm mới dữ liệu"
    void exportPngRequested(const QString& key);    // gear "Tải ảnh PNG" (file dialog belongs to the view)
    void openSingleRequested(const QString& key);   // gear "Mở dạng biểu đồ đơn" (DESIGN §16 C4)
    void seriesVisibilityChanged(const QString& key, int pane);
    void chartMouse(int pane, int eventType, const QPointF& posInChart, Qt::MouseButtons buttons);
    void chartLeft(int pane);
    void renderReady();          // the chart images of the current parameters are shown
    void chartModelChanged();    // parameters changed: models/inputs handed out before are stale (reset hovers)

  protected:
    void paintEvent(QPaintEvent*) override;
    void resizeEvent(QResizeEvent*) override;
    void mouseMoveEvent(QMouseEvent*) override;
    void mousePressEvent(QMouseEvent*) override;
    void mouseReleaseEvent(QMouseEvent*) override;
    void leaveEvent(QEvent*) override;
    void keyPressEvent(QKeyEvent*) override;
    void focusInEvent(QFocusEvent*) override;
    void focusOutEvent(QFocusEvent*) override;
    bool focusNextPrevChild(bool next) override;
    void changeEvent(QEvent*) override;

  private:
    struct PaneState {
        ChartSpec effSpec;              // spec used for layout (margin[1] set by the pane alignment)
        ChartInput input{};
        ChartModel model{};
        std::vector<bool> visible;
        bool allMissing = true;         // from the data alone (cheap scan), drives "[CẦN DATA]"
        WdcLegend* legend = nullptr;
        QImage image;                   // chart pixmap from the render service (may be stale while re-rendering)
        QPointF imageOrigin;            // where the image is blitted (card coordinates, device-pixel aligned)
    };

    void rebuildLegends();
    void refreshLegendEntries();
    void placeChildren();
    void invalidate();
    void ensureLayout();
    void refreshGeom();
    CardRenderParams currentParams() const;
    void refreshMissing();
    void scheduleRender();
    void startRender();
    void adopt(const std::shared_ptr<const CardRender>& r, const QByteArray& key, const CardRenderParams& p);
    void setLayouts(const std::vector<PaneLayout>& panes, const CardRenderParams& p);
    void withdrawPending();
    void paintHeader(QPainter& p);
    void paintPane(QPainter& p, int k);
    int buttonAt(const QPointF& pos) const;
    int chartAt(const QPointF& pos) const;
    void activateButton(int i);
    void showTitleTip();
    void hideTitleTip();
    void showSourceInfo();
    const SeriesData* dataFor(const QString& sid) const;

    std::shared_ptr<const CardSpec> spec_;
    QString dashId_;
    std::shared_ptr<const DashData> table_;
    std::optional<qint64> xMin_, xMax_;
    bool padAuto_ = true;
    bool loading_ = false;
    std::vector<PaneState> panes_;
    CardGeom geom_;
    bool dirty_ = true;                 // models/inputs do not match the current parameters
    bool renderQueued_ = false;
    bool directPaint_ = false;          // renderImage(): paint the charts directly at the export DPR
    QByteArray shownKey_, pendingKey_;  // render key on screen / in flight
    quint64 waiter_ = 0;
    int renderPriority_ = 0;
    QByteArray cacheTag_;
    double lastPaintMs_ = 0;
    QString titleShown_;                // title after the ellipsis, for titleShownW_
    qreal titleShownW_ = -1;
    int hoverBtn_ = -1, pressBtn_ = -1, focusBtn_ = -1;
    int hoverChart_ = -1;
    bool titleHover_ = false;
    OverlayPainter overlay_;
    QTimer* tipTimer_ = nullptr;
    QPointer<WdcPopover> tip_, menu_, info_;
};

} // namespace fincept::screens::wdc
