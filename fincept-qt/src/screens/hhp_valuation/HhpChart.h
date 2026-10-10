// src/screens/hhp_valuation/HhpChart.h
// Reusable dark QtCharts time-series widget for the HHP valuation module.
// Draws any mix of lines, dashed lines, filled bands (between two edges) and filled areas
// over a datetime x-axis, with an optional YTD/1Y/2Y/3Y/5Y/10Y/ALL range bar and a hover
// read-out (date + value of every series at the nearest x).
//
// Used for: VNINDEX band chart (price + ±1σ/±2σ price bands), VN30/VN100 basket ratio chart
// (flat bands), Non-VIC3 comparison lines, Vin-weight area, and the per-ticker band chart.
//
// Optional layers (unused → the chart draws exactly as without them):
//   · forecast series (HhpChartSeries::forecast) — long-dash lines / faint dashed-edge bands in the same
//     colours, a dotted "hôm nay" divider + shaded forecast region, one legend entry, a "DỰ PHÓNG" pill;
//   · notes (set_notes) — ▲ peak / ▼ trough / ◆ target / ◇ valuation-extreme markers with small non-overlapping
//     pill labels that never cover the main line; hovering a marker or label (≥ 120 ms) opens the note's sticky
//     rich-text card beside it (HhpChartNotes.h HhpNoteCard). The card stays while the cursor is over the chart view or the
//     card, swaps to another hovered marker, hides 700 ms after the cursor left both (or Esc / ✕ / a click on
//     empty plot / new series · range · notes / chart hidden / window deactivated); a click on a marker pins it.
#pragma once

#include <QColor>
#include <QLineF>
#include <QPointF>
#include <QRectF>
#include <QString>
#include <QStringList>
#include <QVector>
#include <QWidget>

#include <functional>
#include <limits>
#include <memory>
#include <utility>

class QAbstractSeries;
class QChart;
class QChartView;
class QGraphicsLineItem;
class QGraphicsRectItem;
class QGraphicsSimpleTextItem;
class QLabel;
class QPushButton;
class QHBoxLayout;
class QTimer;

namespace fincept::screens::hhp {

namespace detail {
class HhpNoteLayer; // HhpChartNotes.h (header-only, included by HhpChart.cpp only)
class HhpNoteCard;  // HhpChartNotes.h: sticky note card (top-level Qt::Tool panel)
} // namespace detail

struct HhpChartSeries {
    enum class Kind {
        Line,   ///< solid line (points)
        Dashed, ///< dashed line (points) — used for the historical mean
        Band,   ///< filled region between `points` (upper edge) and `lower` (lower edge)
        Area,   ///< filled region between `points` and the x-axis baseline (y = 0)
    };
    Kind kind = Kind::Line;
    QString name;             ///< legend + hover label
    QColor color;             ///< line colour, or fill colour for Band/Area
    double width = 1.6;       ///< pen width (Line/Dashed; edge pen for Area)
    double opacity = 1.0;     ///< fill alpha for Band/Area (0..1); ignored for lines
    QVector<QPointF> points;  ///< x = epoch ms, y = value. For Band: the UPPER edge.
    QVector<QPointF> lower;   ///< Band only: the LOWER edge, same x-grid as `points`.
    /// Projection segment. Line/Dashed → long-dash pen {6,4} in `color`; Band → faint fill
    /// (alpha = opacity × 0.45) + dashed upper/lower edges in `color`. Never gets its own legend marker
    /// (one shared entry, see set_forecast). Clipped to the forecast tail of the current range; hidden
    /// while forecast_visible() is false.
    bool forecast = false;
};

/// Keynote / target marker drawn over the plot.
struct HhpChartNote {
    enum class Kind {
        Peak,
        Trough,
        Target,
        ExtremeHigh, ///< valuation extreme (P/E far above its mean), not a price pivot: hollow ◇ in the peak colour
        ExtremeLow,  ///< valuation extreme (P/E far below its mean): hollow ◇ in the trough colour
    };
    QString id;                    ///< stable key (hover, tests)
    Kind kind = Kind::Peak;
    qreal x_ms = 0;                ///< event day, epoch ms UTC
    double y = std::numeric_limits<double>::quiet_NaN(); ///< left-axis value; NaN → snapped onto the main line
    QString label;                 ///< line 1, bold 10 px, ≤ ~16 chars ("Đỉnh 04/2018")
    QString sub;                   ///< optional line 2, 8 px muted, elided to ≤ 140 px
    QString detail_html;           ///< tooltip card (Qt rich text); CALLER escapes data
    int priority = 2;              ///< 1 labelled first … 3 last; markers are always drawn
    bool hollow = false;           ///< outline-only marker: provisional pivot or UNVERIFIED keynote
};

/// Hover text for x in [x0_ms, x1_ms) inside the forecast region (e.g. EPS basis of that year).
struct HhpChartSpan {
    qreal x0_ms = 0;
    qreal x1_ms = 0;
    QString text;                  ///< rich text; caller escapes
};

/// Geometry of one note, viewport coordinates (tests / offscreen harness). Empty rect = hidden.
struct HhpChartNoteGeom {
    QString id;
    QRectF marker;
    QRectF label;
    QLineF lead; ///< null = no lead line
};

class HhpChart : public QWidget {
    Q_OBJECT
  public:
    /// @param show_ranges  show the YTD…ALL button row above the plot.
    explicit HhpChart(bool show_ranges = true, QWidget* parent = nullptr);
    ~HhpChart() override; // out-of-line: unique_ptr<detail::HhpNoteLayer>

    /// Replace everything that is drawn. Keeps the current range selection.
    /// @param y_title       y-axis title, e.g. "Điểm số", "P/E (lần)", "Giá (nghìn đồng)"
    /// @param y_decimals    decimals for y-axis labels and hover values
    /// @param y_floor_zero  never let the y-axis go below 0 (prices, index levels)
    void set_series(const QVector<HhpChartSeries>& series, const QString& y_title, int y_decimals,
                    bool y_floor_zero);

    /// Right axis in another unit: right = left ÷ `divisor` (index points or price ÷ current EPS = P/E,
    /// ÷ current BVPS = P/B). It is a second scale over the same plot — no series is attached to it.
    /// `divisor` ≤ 0 / not finite → the right axis mirrors the left one (the default). Call before
    /// set_series(), or it applies from the next redraw.
    void set_right_scale(double divisor, const QString& title, int decimals);

    /// Select a range key from hhp::range_keys(); unknown keys fall back to "ALL".
    void set_range(const QString& key);
    QString range() const { return range_; }

    /// Remove all series and show `message` centred in the plot area (empty = blank plot).
    /// Also forgets the notes and the forecast region (not the DỰ PHÓNG on/off choice).
    void clear(const QString& message = {});

    /// Minimum plot height in px (the widget grows with the layout above this).
    void set_plot_min_height(int px);

    /// Replace the note set ({} clears). Survives set_series()/set_range(); re-laid out on every rebuild and
    /// plot-area change. Notes outside the visible x-range are hidden (marker + label).
    void set_notes(const QVector<HhpChartNote>& notes);
    /// Forecast region. start_ms = last actual point → dotted "hôm nay" divider + caption; ≤ 0 → none.
    /// legend_label = the one legend entry for all forecast series ("" → "Dự phóng (nét đứt)").
    /// Like set_right_scale(): call before set_series(); applies from the next redraw.
    void set_forecast(qreal start_ms, const QString& legend_label, const QVector<HhpChartSpan>& basis = {});
    /// Show/hide every forecast series + divider + shade (same as the "DỰ PHÓNG" pill). Rebuilds.
    void set_forecast_visible(bool on);
    bool forecast_visible() const { return forecast_visible_; }
    /// Current note geometry (viewport coords) — for tests/harness only.
    QVector<HhpChartNoteGeom> note_geometry() const;

    /// Log-scale left axis (27/09, VNINDEX TOÀN SỬ). Series are drawn as log10 copies (series data, the hover read-out and
    /// snapping stay raw); the left axis is a QCategoryAxis with round labels (1 · 1,5 · 2 · 3 · 5 · 7 × 10^k, finer or
    /// coarser to keep 2…10 labels); a scaled right axis (set_right_scale) gets round ratio labels "%.1fx" on the same log
    /// range. Falls back to linear (log_active() == false) when a visible value is ≤ 0 or an Area series is visible.
    /// Rebuilds (a chart without series yet has nothing to redraw: the next set_series() applies it). Default off (every
    /// other chart keeps its linear path unchanged).
    void set_log_y(bool on);
    bool log_y() const { return log_y_; }
    bool log_active() const { return log_active_; }
    /// Called with log_active() after a rebuild switched it, whatever triggered the rebuild (range pill, DỰ PHÓNG pill,
    /// set_series, set_log_y), so the owner's LOG control can show the axis actually drawn. Default: none.
    void set_log_active_listener(std::function<void(bool)> fn) { log_listener_ = std::move(fn); }

  signals:
    void range_changed(const QString& key);

  private:
    void build_ui(bool show_ranges);
    void rebuild_chart();                 ///< re-create QChart content for series_ within range_
    void update_range_buttons();
    void update_forecast_button();        ///< "DỰ PHÓNG" pill: style + visible only with forecast series
    void on_hover(qreal x_ms);            ///< nearest-x read-out into hover_lbl_
    void on_leave();
    void set_overlay(const QString& text); ///< centred message over the plot; empty hides it
    void relayout_overlays();             ///< notes + divider + shade; on plotAreaChanged, rebuild, set_notes
    int note_at(const QPointF& chart_pos, QRectF* hit_chart) const; ///< index into notes_ or -1
    qreal forecast_hi_ms(qreal now_ms) const; ///< x upper bound for forecast series under range_
    double main_line_y(qreal x_ms) const;     ///< linear interp on the last non-forecast Line series; NaN outside
    const HhpChartSeries* main_line() const;  ///< last non-forecast Line series with points, or nullptr

    QVector<HhpChartSeries> series_;
    QString y_title_;
    int y_decimals_ = 2;
    bool y_floor_zero_ = false;
    double right_divisor_ = 0;  ///< > 0 → right axis = left ÷ this (set_right_scale)
    QString right_title_;
    int right_decimals_ = 1;
    QString range_ = QStringLiteral("ALL");
    QString empty_msg_;

    QChartView* view_ = nullptr;
    QLabel* hover_lbl_ = nullptr;
    QLabel* empty_lbl_ = nullptr;
    QWidget* range_bar_ = nullptr;
    QVector<QPushButton*> range_btns_;
    QGraphicsLineItem* crosshair_ = nullptr; ///< vertical hover line, child item of the chart
    qreal cut_ms_ = 0;                       ///< x lower bound of the current range (0 = none)

    // ── notes + forecast layers ──
    QVector<HhpChartNote> notes_;
    std::unique_ptr<detail::HhpNoteLayer> notes_layer_;
    qreal fc_start_ms_ = 0;
    QString fc_label_;
    QVector<HhpChartSpan> fc_basis_;
    bool forecast_visible_ = true;
    bool fc_drawn_ = false;                    ///< ≥ 1 forecast series drawn by the current rebuild
    qreal hi_ms_ = 0;                          ///< forecast x upper bound of the current rebuild (inf = none)
    qreal x_min_ms_ = 0;                       ///< x-axis range of the current rebuild
    qreal x_max_ms_ = 0;
    QAbstractSeries* anchor_ = nullptr;        ///< a series on x + LEFT y (mapToPosition); reset each rebuild
    QPushButton* fc_btn_ = nullptr;            ///< "DỰ PHÓNG" pill (range bar only; hidden without forecast series)
    QGraphicsLineItem* today_line_ = nullptr;
    QGraphicsSimpleTextItem* today_lbl_ = nullptr;
    QGraphicsRectItem* fc_shade_ = nullptr;
    int hover_note_ = -1;
    QRectF hover_rect_;                        ///< hit rect (chart coords) the note card is bound to
    bool tip_alt_ = false;                     ///< retired with the QToolTip card (unused)

    // ── sticky note card (26/09: replaces the QToolTip card) ──
  public:
    /// Tests/harness: the card while it shows a note (nullptr when hidden), that note's id ("" = none) and
    /// whether it is pinned.
    QWidget* note_card() const;
    QString note_card_id() const;
    bool note_card_pinned() const;

  private:
    void ensure_card();                   ///< lazily: card + timers + event filter (never without notes)
    void show_card(int note, bool pin);   ///< card of notes_[note] beside its marker; pin → survives leaving
    void hide_card();                     ///< hide + unpin, stop the timers, drop the app-wide filter
    void place_card();                    ///< beside the marker of card_note_; hides the card if that marker is gone
    void arm_card_leave();                ///< cursor over neither view nor card (unpinned) → 700 ms hide timer
    void on_press(const QPointF& pos);    ///< left click: marker/label → pin its card; empty plot → hide it

    detail::HhpNoteCard* card_ = nullptr; ///< child top-level window; created on the first note hover/click
    QObject* card_filter_ = nullptr;      ///< app-wide while shown: Esc, hide/deactivate of this chart, move/wheel
    QTimer* dwell_timer_ = nullptr;       ///< 120 ms on one marker/label before its card opens or swaps in
    QTimer* leave_timer_ = nullptr;       ///< 700 ms outside both view and card → hide (unpinned only)
    int card_note_ = -1;                  ///< index into notes_ the card shows; -1 = hidden
    int dwell_note_ = -1;                 ///< note the dwell timer waits on; -1 = none
    bool in_view_ = false;                ///< cursor over the chart view (enter/move … leave)
    bool in_card_ = false;                ///< cursor over the card (enter … leave)

    // ── log-y axis (27/09, set_log_y) ──
    double plot_y(double y) const;        ///< log10(y) while log_active_ (NaN for y ≤ 0), else y: every data → plot mapping
    bool log_y_ = false;                  ///< requested (set_log_y)
    bool log_active_ = false;             ///< in effect for the current rebuild (every visible value > 0, no Area series)
    std::function<void(bool)> log_listener_; ///< set_log_active_listener(): told when a rebuild switches log_active_
};

} // namespace fincept::screens::hhp
