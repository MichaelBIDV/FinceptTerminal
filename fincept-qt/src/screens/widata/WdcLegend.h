#pragma once
// WdcLegend.h: legend of the WiData clone (package D): card legend "aio" (2 columns, padding 0 8, scrollbar on
// the left), "macro" (LegendCustom: 47 % items, bottom-aligned single row), expanded (4 columns, padding 0 40)
// and chart page (LegendCustom, 3 columns). Six swatch kinds, click toggles a series, reset button, info
// popover with OUR metadata (series[sid].meta, DESIGN §4.7, §7.1, §8.4).
//
// Geometry follows the capture DOM (UI §3.4, §3.5, §4.5): layoutLegend() is pure and is what the harness
// compares with the 492 legend items of CAP. WdcLegend is the widget; it also hosts WdcPopover, the popover
// frame of DESIGN §6.1 reused by the card (gear menu, "Thông tin nguồn").
#include "screens/widata/WdcData.h"
#include "screens/widata/WdcModel.h"

#include <QHash>
#include <QImage>
#include <QPointer>
#include <QStringList>
#include <QWidget>

#include <memory>
#include <vector>

class QTimer;

namespace fincept::screens::wdc {

// Per-series data (SeriesEntry: status, tier, points, meta...) and the dashboard table (DashData) come from
// WdcData.h (package E, DESIGN §4.7); the legend only reads them.

// ---- pure layout -------------------------------------------------------------------------------------------
enum class LegendStyle { Aio, Macro, Expanded, Single };
enum class SwatchKind { Line, Dash, LineMarker, Column, Area, Column2, Area2 };

SwatchKind swatchKindFor(const SeriesRef& ref);   // UI §3.4 table (2 colours = negativeColor present)
QString swatchKindName(SwatchKind k);
/// Display order of a pane: "zIndex_desc" (aio cards, stable) or series order (macro cards), BEH §5.1.
std::vector<int> legendOrder(const std::vector<SeriesRef>& refs, bool zIndexDesc);

struct LegendItemGeom {
    QRectF item;                       // DOM item box (css-1m3jp8y / LegendCustom item)
    QRectF row;                        // 18 px content row (inside item; differs only for the 1-row expanded case)
    std::vector<QRectF> swatchParts;   // DOM order: root first (Dash: root + 3 segments, Area: root + bar + block,
                                       // LineMarker: bar + dot, Line/Column: one box)
    QRectF textBlock, text, infoBox, infoIcon;
    QString shown;                     // text after ellipsis
    bool elided = false;
    // hovered item (A/HOVER_CSS.md, `.css-1m3jp8y:hover .LegendChartWidgetAIO-itemName {text-overflow: inherit;
    // padding-right: .5rem}`): no "…", the name is clipped at the span edge (overflow hidden, border-box: SUY LUẬN)
    // and the info icon sits after the 8 px padding
    qreal fullW = 0;                   // width of the whole name
    QRectF textHover;                  // clip of the name while hovered
    QRectF infoBoxHover, infoIconHover;
};
struct LegendGeom {
    QRectF container;
    qreal scrollbarW = 0;              // 0 when not scrollable
    qreal contentH = 0;                // rows * 18 (or 36 for a single expanded row)
    QRectF track;                      // scrollbar strip (left side)
    QRectF reset;                      // reset button (shown only when a series is off); card legends follow the stylesheet:
                                       // aio `.reset-legend-arrow {right:-4px; margin-top:-8px}`, macro
                                       // `.reset-legend-scroll {right:-4px; bottom:18px}` (HOVER_CSS.md)
    std::vector<LegendItemGeom> items; // display order
    bool scrollable() const { return scrollbarW > 0; }
};
struct LegendText { QString text; SwatchKind kind; };

/// Item geometry for `items` (already in display order, text already collapsed) inside `container`, scroll 0.
LegendGeom layoutLegend(LegendStyle style, const QRectF& container, const std::vector<LegendText>& items, qreal dpr);
/// Paints one swatch from its parts (see LegendItemGeom). `neg` is used by the 2-colour kinds.
void paintSwatch(QPainter& p, SwatchKind kind, const std::vector<QRectF>& parts, const QColor& c, const QColor& neg);

// ---- popover (DESIGN §6.1 frame) ---------------------------------------------------------------------------
class WdcPopover : public QWidget {
    Q_OBJECT
  public:
    // Tip: hover info (no focus); Panel: text, closes on outside click; Menu: clickable rows;
    // TitleTip: dark one-line tooltip of a card title (DESIGN §6.1: #323546, white 11 px, padding 6, radius 4)
    enum class Mode { Tip, Panel, Menu, TitleTip };
    struct Item { QString id, text; bool enabled = true; };

    WdcPopover(QWidget* owner, Mode mode);
    void setLines(const QStringList& lines);
    void setItems(const std::vector<Item>& items);
    /// Places the FRAME (not the shadow margin) with its top-left at `globalTopLeft`, kept on the owner's screen.
    void showAt(const QPoint& globalTopLeft);
    QSizeF frameSize() const;
    QStringList itemIds() const;
    void trigger(const QString& id); // harness hook: same as a click on the item

  signals:
    void triggered(const QString& id);

  protected:
    void paintEvent(QPaintEvent*) override;
    void mouseMoveEvent(QMouseEvent*) override;
    void mouseReleaseEvent(QMouseEvent*) override;
    void leaveEvent(QEvent*) override;
    void keyPressEvent(QKeyEvent*) override;

  private:
    void relayout();
    int itemAt(const QPointF& pos) const;

    Mode mode_;
    QStringList lines_;
    std::vector<Item> items_;
    QSizeF frame_;
    qreal margin_ = 0;
    int hover_ = -1;
};

// ---- widget ------------------------------------------------------------------------------------------------
struct LegendEntry {
    const SeriesRef* ref = nullptr;     // owned by the card spec
    const SeriesEntry* entry = nullptr; // null or status Missing = no number for this sid
    int refIndex = -1;                  // index of the ref in its pane (ChartInput order)
};

class WdcLegend : public QWidget {
    Q_OBJECT
  public:
    static constexpr qreal kOverhang = 10; // widget extends past the container: reset button, swatch overhang

    explicit WdcLegend(QWidget* parent = nullptr);
    ~WdcLegend() override;

    void setLegendStyle(LegendStyle style);
    LegendStyle legendStyle() const { return style_; }
    /// Entries in display order; `keepAlive` holds the dashboard data the entry pointers point into.
    void setEntries(std::vector<LegendEntry> entries, std::shared_ptr<const DashData> keepAlive);
    /// Visibility by refIndex (missing indices count as visible).
    void setVisibility(const std::vector<bool>& visibleByRefIndex);
    /// Container rect in parent coordinates (fractional allowed): moves and resizes the widget.
    void setContainerRect(const QRectF& rectInParent);
    QRectF containerRect() const { return container_; }

    int count() const { return int(entries_.size()); }
    LegendGeom geometryModel() const; // parent coordinates, scroll 0
    // harness hooks (widget coordinates)
    QRectF itemRectInWidget(int i) const;
    QRectF infoRectInWidget(int i) const;
    QRectF resetRectInWidget() const;
    bool resetVisible() const;
    bool infoVisible(int i) const;
    bool popoverVisible() const;
    qreal scrollOffset() const { return scrollY_; }

  signals:
    void toggled(int refIndex, bool visible);
    void resetRequested();

  protected:
    void paintEvent(QPaintEvent*) override;
    void mouseMoveEvent(QMouseEvent*) override;
    void mousePressEvent(QMouseEvent*) override;
    void mouseReleaseEvent(QMouseEvent*) override;
    void leaveEvent(QEvent*) override;
    void wheelEvent(QWheelEvent*) override;
    void changeEvent(QEvent*) override;

  private:
    void relayout();                   // marks the geometry dirty (computed on first use, not per setter)
    void repaintCached();              // the legend itself changed: redraw its cached image
    void paintContent(QPainter& p, qreal dpr);
    const LegendGeom& g() const;
    bool isVisibleEntry(int i) const;
    bool isMissing(int i) const;
    int hitItem(const QPointF& pos) const;
    QStringList infoLines(int i) const;
    void showInfo(int i);
    void hideInfo();
    QPointF scrolled(const QPointF& p) const { return p - QPointF(0, scrollY_); }

    LegendStyle style_ = LegendStyle::Aio;
    std::vector<LegendEntry> entries_;
    std::shared_ptr<const DashData> keep_;
    std::vector<bool> visible_;   // by refIndex
    QRectF container_;            // parent coordinates
    mutable LegendGeom geom_;     // widget coordinates, scroll 0
    mutable bool geomDirty_ = true;
    QImage cache_;                // last drawing (widget size x DPR), reused when only the card repaints
    bool cacheDirty_ = true;
    mutable qreal scrollY_ = 0;
    int hover_ = -1;
    int infoFor_ = -1;
    bool hoverReset_ = false;
    bool pressReset_ = false;
    int pressed_ = -1;
    QPointer<WdcPopover> pop_;
    QTimer* infoTimer_ = nullptr;
    int infoPending_ = -1;
};

} // namespace fincept::screens::wdc
