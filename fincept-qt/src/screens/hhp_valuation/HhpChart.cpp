// src/screens/hhp_valuation/HhpChart.cpp
#include "screens/hhp_valuation/HhpChart.h"

#include "screens/hhp_valuation/HhpChartNotes.h"
#include "screens/hhp_valuation/HhpCommon.h"

#include <QAbstractAxis>
#include <QAbstractSeries>
#include <QApplication>
#include <QAreaSeries>
#include <QBrush>
#include <QCategoryAxis>
#include <QChart>
#include <QChartView>
#include <QDateTime>
#include <QDateTimeAxis>
#include <QEvent>
#include <QFont>
#include <QGraphicsLayout>
#include <QGraphicsLineItem>
#include <QGraphicsRectItem>
#include <QGraphicsSimpleTextItem>
#include <QHBoxLayout>
#include <QKeyEvent>
#include <QLabel>
#include <QLegend>
#include <QLegendMarker>
#include <QLineSeries>
#include <QMouseEvent>
#include <QPainter>
#include <QPen>
#include <QPushButton>
#include <QResizeEvent>
#include <QStringList>
#include <QTimer>
#include <QVBoxLayout>
#include <QValueAxis>

#include <algorithm>
#include <cmath>
#include <functional>
#include <limits>

namespace fincept::screens::hhp {

namespace {

constexpr qreal kDayMs = 86400000.0;
constexpr int kDefaultPlotMinHeight = 320;
constexpr int kPillHeight = 22;
constexpr double kPadFraction = 0.05;
constexpr qreal kInf = std::numeric_limits<qreal>::infinity();
constexpr double kForecastFillFactor = 0.45; ///< forecast band alpha = opacity × this
constexpr double kForecastEdgeWidth = 1.2;   ///< dashed upper/lower edge of a forecast band
constexpr int kCardDwellMs = 120;            ///< on one marker/label this long → its sticky card opens (or swaps in)
constexpr int kCardLeaveMs = 700;            ///< cursor outside both chart view and card this long → card hides

/// QChartView that reports mouse move / enter / leave / left press / resize through callbacks (no moc needed).
class HoverChartView : public QChartView {
  public:
    HoverChartView(QChart* chart, QWidget* parent) : QChartView(chart, parent) {}

    std::function<void(const QPointF&)> on_move;
    std::function<void()> on_enter;
    std::function<void()> on_leave;
    std::function<void(const QPointF&)> on_press; ///< left button
    std::function<void()> on_resize;

  protected:
    void mouseMoveEvent(QMouseEvent* event) override {
        if (on_move)
            on_move(event->position());
        QChartView::mouseMoveEvent(event);
    }

    void enterEvent(QEnterEvent* event) override {
        if (on_enter)
            on_enter();
        QChartView::enterEvent(event);
    }

    void leaveEvent(QEvent* event) override {
        if (on_leave)
            on_leave();
        QChartView::leaveEvent(event);
    }

    void mousePressEvent(QMouseEvent* event) override {
        if (on_press && event->button() == Qt::LeftButton)
            on_press(event->position());
        QChartView::mousePressEvent(event);
    }

    void resizeEvent(QResizeEvent* event) override {
        QChartView::resizeEvent(event);
        if (on_resize)
            on_resize();
    }
};

/// Event filter forwarding to a callback (no moc needed).
class FnFilter : public QObject {
  public:
    FnFilter(std::function<bool(QObject*, QEvent*)> fn, QObject* parent) : QObject(parent), fn_(std::move(fn)) {}

  protected:
    bool eventFilter(QObject* watched, QEvent* event) override { return fn_ && fn_(watched, event); }

  private:
    std::function<bool(QObject*, QEvent*)> fn_;
};

/// Charts whose sticky card is up. Each has its own app-wide filter, and the first one to see Esc consumes it
/// (so the dialog behind stays open) — it closes every card on the list, not only its own.
QVector<HhpChart*>& open_cards() {
    static QVector<HhpChart*> charts;
    return charts;
}

bool x_less(const QPointF& a, const QPointF& b) { return a.x() < b.x(); }
bool x_below(const QPointF& p, qreal v) { return p.x() < v; }

/// Drop non-finite points and sort by x (stable) when the input is not already ascending.
QVector<QPointF> clean_points(const QVector<QPointF>& in) {
    QVector<QPointF> out;
    out.reserve(in.size());
    for (const QPointF& p : in) {
        if (has(p.x()) && has(p.y()))
            out.append(p);
    }
    if (!std::is_sorted(out.cbegin(), out.cend(), x_less))
        std::stable_sort(out.begin(), out.end(), x_less);
    return out;
}

bool x_above(qreal v, const QPointF& p) { return v < p.x(); }

/// Index of the first point with x >= lo (points sorted by x); size() when none.
qsizetype first_visible(const QVector<QPointF>& pts, qreal lo) {
    return std::lower_bound(pts.cbegin(), pts.cend(), lo, x_below) - pts.cbegin();
}

/// Index of the last point with x <= hi; -1 when none. hi = +inf → size() - 1.
qsizetype last_visible(const QVector<QPointF>& pts, qreal hi) {
    return (std::upper_bound(pts.cbegin(), pts.cend(), hi, x_above) - pts.cbegin()) - 1;
}

/// Points with lo <= x <= hi. History series pass hi = +inf (unchanged behaviour); only forecast series are
/// clipped at the forecast tail of the range.
QVector<QPointF> visible_span(const QVector<QPointF>& pts, qreal lo, qreal hi) {
    const qsizetype first = first_visible(pts, lo);
    const qsizetype last = last_visible(pts, hi);
    return first > last ? QVector<QPointF>() : pts.mid(first, last - first + 1);
}

/// Nearest visible point (lo <= x <= hi) to x, or -1 when the series has no visible point or x lies more
/// than one average step outside the series' visible span (series of different lengths).
qsizetype nearest_in(const QVector<QPointF>& pts, qreal lo, qreal hi, qreal x) {
    const qsizetype first = first_visible(pts, lo);
    const qsizetype last = last_visible(pts, hi);
    if (first > last)
        return -1;
    const qreal x0 = pts.at(first).x();
    const qreal x1 = pts.at(last).x();
    const qreal tol = last > first ? (x1 - x0) / static_cast<qreal>(last - first) : 3 * kDayMs;
    if (x < x0 - tol || x > x1 + tol)
        return -1;
    const auto begin = pts.cbegin() + first;
    const auto end = pts.cbegin() + last + 1;
    const auto it = std::lower_bound(begin, end, x, x_below);
    if (it == end)
        return last;
    if (it == begin)
        return first;
    const auto prev = it - 1;
    return (x - prev->x() <= it->x() - x) ? (prev - pts.cbegin()) : (it - pts.cbegin());
}

/// Band/Area first, then dashed (mean), then solid lines — so the main line is drawn on top.
int draw_pass(HhpChartSeries::Kind kind) {
    switch (kind) {
        case HhpChartSeries::Kind::Band:
        case HhpChartSeries::Kind::Area:
            return 0;
        case HhpChartSeries::Kind::Dashed:
            return 1;
        case HhpChartSeries::Kind::Line:
            return 2;
    }
    return 2;
}

QColor with_alpha(QColor c, double opacity) {
    c.setAlphaF(static_cast<float>(std::clamp(opacity, 0.0, 1.0)));
    return c;
}

QAbstractSeries* add_band(QChart* chart, const HhpChartSeries& s, const QVector<QPointF>& upper,
                          const QVector<QPointF>& lower) {
    auto* up = new QLineSeries();
    up->replace(upper);
    auto* lo = new QLineSeries();
    lo->replace(lower);
    auto* area = new QAreaSeries(up, lo); // parents the area to `up` for now
    area->setName(s.name);
    chart->addSeries(area); // reparents the area into the chart
    // Only now hand the edges to the area (freed with it by removeAllSeries()); doing it before
    // addSeries would briefly make up ↔ area each other's parent.
    up->setParent(area);
    lo->setParent(area);
    area->setPen(QPen(Qt::NoPen));
    area->setBrush(QBrush(with_alpha(s.color, s.opacity)));
    return area;
}

QAbstractSeries* add_area(QChart* chart, const HhpChartSeries& s, const QVector<QPointF>& upper) {
    auto* up = new QLineSeries();
    up->replace(upper);
    auto* area = new QAreaSeries(up, nullptr);
    area->setName(s.name);
    chart->addSeries(area);
    up->setParent(area); // after addSeries — see add_band
    area->setPen(QPen(s.color, s.width));
    area->setBrush(QBrush(with_alpha(s.color, s.opacity)));
    return area;
}

QAbstractSeries* add_line(QChart* chart, const HhpChartSeries& s, const QVector<QPointF>& pts, bool dashed) {
    auto* line = new QLineSeries();
    line->setName(s.name);
    line->replace(pts);
    chart->addSeries(line);
    line->setPen(QPen(s.color, s.width, dashed ? Qt::DashLine : Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
    return line;
}

/// Long dash {6,4} (in pen widths) — visibly longer than the historical mean's Qt::DashLine.
QPen forecast_pen(const QColor& color, double width) {
    QPen pen(color, width, Qt::CustomDashLine, Qt::FlatCap, Qt::RoundJoin);
    pen.setDashPattern({6.0, 4.0});
    return pen;
}

/// One forecast series → chart series (all appended to `out`): long-dash line, or faint band/area fill whose
/// edges are separate dashed lines (a QAreaSeries pen would also stroke the closing vertical sides).
void add_forecast(QChart* chart, const HhpChartSeries& s, const QVector<QPointF>& upper,
                  const QVector<QPointF>& lower, QList<QAbstractSeries*>& out) {
    if (s.kind == HhpChartSeries::Kind::Line || s.kind == HhpChartSeries::Kind::Dashed) {
        auto* line = static_cast<QLineSeries*>(add_line(chart, s, upper, false));
        line->setPen(forecast_pen(s.color, s.width));
        out.append(line);
        return;
    }
    HhpChartSeries faint = s;
    faint.opacity = s.opacity * kForecastFillFactor;
    const bool band = s.kind == HhpChartSeries::Kind::Band;
    QAbstractSeries* fill = band ? add_band(chart, faint, upper, lower) : add_area(chart, faint, upper);
    if (!band)
        static_cast<QAreaSeries*>(fill)->setPen(QPen(Qt::NoPen));
    out.append(fill);
    const QPen pen = forecast_pen(s.color, kForecastEdgeWidth);
    for (const QVector<QPointF>* edge : {&upper, &lower}) {
        if (edge->isEmpty())
            continue;
        auto* line = new QLineSeries();
        line->setName(s.name);
        line->replace(*edge);
        chart->addSeries(line);
        line->setPen(pen);
        out.append(line);
    }
}

void style_axis(QAbstractAxis* axis) {
    QFont f = axis->labelsFont();
    f.setPixelSize(10);
    axis->setLabelsFont(f);
    axis->setLabelsColor(c_muted());
    axis->setGridLineColor(c_grid());
    axis->setLinePenColor(c_line());
    axis->setMinorGridLineVisible(false);
    axis->setShadesVisible(false);
}

// ── log-y axis (set_log_y) ──
constexpr int kMaxLogLabels = 10;

/// Same points with y → log10(y) (drawn copy under a log axis; the caller guarantees y > 0).
QVector<QPointF> log_points(const QVector<QPointF>& pts) {
    QVector<QPointF> out;
    out.reserve(pts.size());
    for (const QPointF& p : pts)
        out.append(QPointF(p.x(), std::log10(p.y())));
    return out;
}

/// v = m × 10^k for m in `mults` with lo ≤ log10(v) ≤ hi (log10 units), ascending.
QVector<double> decade_values(double lo, double hi, const QVector<double>& mults) {
    QVector<double> out;
    for (int k = static_cast<int>(std::floor(lo)) - 1; k <= static_cast<int>(std::ceil(hi)); ++k) {
        for (double m : mults) {
            const double v = m * std::pow(10.0, k);
            const double lv = std::log10(v);
            if (lv >= lo - 1e-9 && lv <= hi + 1e-9)
                out.append(v);
        }
    }
    return out;
}

/// Round tick values for a log axis over [lo, hi] (log10 units): the finest round set that gives 2…kMaxLogLabels values;
/// a range too short for any of them → ~5 nice linear steps (1/2/2,5/5 × 10^k) inside it; one wider than
/// kMaxLogLabels decades → every n-th power of ten.
QVector<double> log_ticks(double lo, double hi) {
    static const QVector<QVector<double>> kSets = {{1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8}, {1, 1.5, 2, 3, 5, 7},
                                                   {1, 2, 5}, {1, 3}, {1}};
    bool too_few = false;
    for (const QVector<double>& set : kSets) {
        const QVector<double> v = decade_values(lo, hi, set);
        if (v.size() > kMaxLogLabels)
            continue;
        if (v.size() >= 2)
            return v;
        too_few = true;
        break;
    }
    if (!too_few) { // > kMaxLogLabels powers of ten: thin them
        const QVector<double> v = decade_values(lo, hi, {1});
        const qsizetype stride = (v.size() + kMaxLogLabels - 1) / kMaxLogLabels;
        QVector<double> out;
        for (qsizetype i = 0; i < v.size(); i += stride)
            out.append(v.at(i));
        return out;
    }
    const double vlo = std::pow(10.0, lo);
    const double vhi = std::pow(10.0, hi);
    const double raw = std::max(1e-12, (vhi - vlo) / 5.0);
    const double mag = std::pow(10.0, std::floor(std::log10(raw)));
    double step = 10.0 * mag;
    for (double m : {1.0, 2.0, 2.5, 5.0, 10.0})
        if (raw <= m * mag) {
            step = m * mag;
            break;
        }
    QVector<double> out;
    for (double v = std::ceil(vlo / step) * step; v <= vhi * (1.0 + 1e-12); v += step)
        if (v > 0)
            out.append(v);
    return out;
}

/// Category axis over [lo, hi] (log10 units) with one label per value at log10(value) + shift; duplicate label strings
/// (a rounding collision) are skipped — QCategoryAxis keys categories by label.
void fill_log_axis(QCategoryAxis* axis, double lo, double hi, const QVector<double>& values, double shift,
                   const std::function<QString(double)>& label) {
    axis->setLabelsPosition(QCategoryAxis::AxisLabelsPositionOnValue);
    axis->setRange(lo, hi);
    axis->setStartValue(lo);
    QStringList seen;
    for (double v : values) {
        const QString text = label(v);
        const double at = std::log10(v) + shift;
        if (text.isEmpty() || seen.contains(text) || at < lo - 1e-9 || at > hi + 1e-9)
            continue;
        seen << text;
        axis->append(text, at);
    }
}

/// Muted 10 px axis title (hidden when empty) — as the linear axes of rebuild_chart().
void set_axis_title(QAbstractAxis* axis, const QString& title) {
    if (title.isEmpty()) {
        axis->setTitleVisible(false);
        return;
    }
    axis->setTitleText(title);
    QFont tf = axis->titleFont();
    tf.setPixelSize(10);
    tf.setBold(false);
    axis->setTitleFont(tf);
    axis->setTitleBrush(QBrush(c_muted()));
    axis->setTitleVisible(true);
}

/// What the log axes take from the chart's settings.
struct LogAxisSpec {
    QString y_title;
    int y_decimals = 0;
    bool y_floor_zero = false; ///< index levels / prices: "1.000" labels (Vietnamese grouping)
    double right_divisor = 0;  ///< > 0: right axis = left ÷ this (ratio labels), else it mirrors the left one
    QString right_title;
    int right_decimals = 1;
};

/// Left + right log axes over the visible raw range [y_lo, y_hi] (every value > 0), padded 5% of the log span, and every
/// series attached to x + left (+ the right axis when it mirrors the left one, like the linear path).
void add_log_axes(QChart* chart, QAbstractAxis* x_axis, const QList<QAbstractSeries*>& added, double y_lo, double y_hi,
                  const LogAxisSpec& spec) {
    const double l0 = std::log10(y_lo);
    const double l1 = std::log10(y_hi);
    const double span = l1 - l0;
    const double pad = span > 1e-9 ? span * kPadFraction : 0.02;
    const double lo = l0 - pad;
    const double hi = l1 + pad;
    const auto left_label = [&spec](double v) {
        return spec.y_floor_zero ? fmt_vi(v, 0) : fmt_ratio(v, spec.y_decimals);
    };
    auto* y_axis = new QCategoryAxis();
    chart->addAxis(y_axis, Qt::AlignLeft);
    fill_log_axis(y_axis, lo, hi, log_ticks(lo, hi), 0.0, left_label);
    style_axis(y_axis);
    set_axis_title(y_axis, spec.y_title);

    const bool scaled = spec.right_divisor > 0;
    auto* y_axis_r = new QCategoryAxis();
    chart->addAxis(y_axis_r, Qt::AlignRight);
    if (scaled) {
        const double shift = std::log10(spec.right_divisor); // log10(v ÷ d) = log10(v) − log10(d)
        const int dec = spec.right_decimals;
        fill_log_axis(y_axis_r, lo, hi, log_ticks(lo - shift, hi - shift), shift,
                      [dec](double r) { return QString::asprintf("%.*fx", dec, r); });
    } else {
        fill_log_axis(y_axis_r, lo, hi, log_ticks(lo, hi), 0.0, left_label);
    }
    style_axis(y_axis_r);
    y_axis_r->setGridLineVisible(false);
    set_axis_title(y_axis_r, scaled ? spec.right_title : spec.y_title);

    for (QAbstractSeries* s : added) {
        s->attachAxis(x_axis);
        s->attachAxis(y_axis);
        if (!scaled)
            s->attachAxis(y_axis_r);
    }
}

QString pill_style(bool active) {
    if (active) {
        return QStringLiteral("QPushButton { background: %1; color: #1a1208; font-weight: 700; border: 1px solid %1;"
                              " border-radius: 6px; padding: 0 8px; font-size: 11px; }")
            .arg(css(c_gold()));
    }
    return QStringLiteral("QPushButton { background: %1; color: %2; border: 1px solid %3; border-radius: 6px;"
                          " padding: 0 8px; font-size: 11px; }"
                          "QPushButton:hover { color: %4; border-color: %5; }")
        .arg(css(c_card()), css(c_muted()), css(c_line()), css(c_text()), css(c_gold()));
}

/// "DỰ PHÓNG" toggle: dashed border like the lines it controls; gold while the forecast is shown. The left
/// margin only takes space while the pill is visible (hidden widgets are skipped by the layout).
QString fc_pill_style(bool on) {
    return QStringLiteral("QPushButton { background: transparent; color: %1; font-weight: %2; border: 1px dashed %3;"
                          " border-radius: 6px; padding: 0 8px; margin-left: 6px; font-size: 11px; }"
                          "QPushButton:hover { color: %4; border-color: %5; }")
        .arg(css(on ? c_gold() : c_muted()), on ? QStringLiteral("700") : QStringLiteral("400"),
             css(on ? c_gold() : c_line()), css(c_text()), css(c_gold()));
}

} // namespace

HhpChart::HhpChart(bool show_ranges, QWidget* parent) : QWidget(parent) {
    build_ui(show_ranges);
}

HhpChart::~HhpChart() {
    // The chart outlives this body (QWidget deletes it later): stop its signals reaching a half-destroyed
    // HhpChart, then let notes_layer_ delete its items while the chart still exists.
    if (view_ && view_->chart())
        disconnect(view_->chart(), nullptr, this, nullptr);
    // Same for the view's callbacks and the sticky card (a top-level child: gone before its enter/leave can fire).
    if (auto* v = static_cast<HoverChartView*>(view_)) {
        v->on_move = nullptr;
        v->on_enter = nullptr;
        v->on_leave = nullptr;
        v->on_press = nullptr;
    }
    if (card_) {
        hide_card();
        card_->on_enter = nullptr;
        card_->on_leave = nullptr;
        card_->on_close = nullptr;
        delete card_;
        card_ = nullptr;
    }
}

void HhpChart::build_ui(bool show_ranges) {
    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(4);

    // ── Top row: range pills (left) + hover read-out (right) ─────────────────
    auto* top = new QHBoxLayout;
    top->setContentsMargins(0, 0, 0, 0);
    top->setSpacing(8);
    if (show_ranges) {
        range_bar_ = new QWidget(this);
        auto* rl = new QHBoxLayout(range_bar_);
        rl->setContentsMargins(0, 0, 0, 0);
        rl->setSpacing(4);
        for (const QString& key : range_keys()) {
            auto* btn = new QPushButton(key, range_bar_);
            btn->setFixedHeight(kPillHeight);
            btn->setCursor(Qt::PointingHandCursor);
            btn->setFocusPolicy(Qt::NoFocus);
            connect(btn, &QPushButton::clicked, this, [this, key]() { set_range(key); });
            rl->addWidget(btn);
            range_btns_.append(btn);
        }
        fc_btn_ = new QPushButton(QStringLiteral("DỰ PHÓNG"), range_bar_);
        fc_btn_->setFixedHeight(kPillHeight);
        fc_btn_->setCursor(Qt::PointingHandCursor);
        fc_btn_->setFocusPolicy(Qt::NoFocus);
        fc_btn_->setCheckable(true);
        fc_btn_->setToolTip(QStringLiteral("Bật/tắt dự phóng 3 năm (nét đứt)"));
        fc_btn_->hide();
        connect(fc_btn_, &QPushButton::clicked, this, [this]() { set_forecast_visible(!forecast_visible_); });
        rl->addWidget(fc_btn_);
        top->addWidget(range_bar_);
    }
    hover_lbl_ = new QLabel(this);
    hover_lbl_->setTextFormat(Qt::RichText);
    hover_lbl_->setWordWrap(false);
    hover_lbl_->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    hover_lbl_->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Fixed);
    hover_lbl_->setFixedHeight(kPillHeight);
    hover_lbl_->setStyleSheet(
        QStringLiteral("color: %1; font-size: 11px; background: transparent;").arg(css(c_muted())));
    top->addWidget(hover_lbl_, 1);
    root->addLayout(top);

    // ── Chart ─────────────────────────────────────────────────────────────────
    auto* chart = new QChart();
    chart->setBackgroundBrush(QBrush(c_card()));
    chart->setBackgroundPen(QPen(Qt::NoPen));
    chart->setBackgroundRoundness(0);
    chart->setPlotAreaBackgroundVisible(false);
    chart->setMargins(QMargins(6, 6, 6, 6));
    chart->setAnimationOptions(QChart::NoAnimation);
    if (chart->layout())
        chart->layout()->setContentsMargins(0, 0, 0, 0);

    QLegend* legend = chart->legend();
    legend->setVisible(true);
    legend->setAlignment(Qt::AlignBottom);
    legend->setBackgroundVisible(false);
    legend->setLabelColor(c_text());
    legend->setMarkerShape(QLegend::MarkerShapeRectangle);
    QFont lf = legend->font();
    lf.setPixelSize(10);
    legend->setFont(lf);

    crosshair_ = new QGraphicsLineItem(chart);
    QPen cross_pen(c_muted(), 1.0, Qt::DashLine);
    cross_pen.setCosmetic(true);
    crosshair_->setPen(cross_pen);
    crosshair_->setZValue(1000);
    crosshair_->setAcceptedMouseButtons(Qt::NoButton);
    crosshair_->setAcceptHoverEvents(false);
    crosshair_->hide();

    // Forecast region: shade (above the grid, below axes/series), dotted divider + caption (above the
    // crosshair plane). Placed by relayout_overlays(); hidden unless forecast series are drawn.
    fc_shade_ = new QGraphicsRectItem(chart);
    fc_shade_->setPen(QPen(Qt::NoPen));
    fc_shade_->setBrush(QBrush(with_alpha(c_grid(), 0.35)));
    fc_shade_->setZValue(2.5);
    fc_shade_->setAcceptedMouseButtons(Qt::NoButton);
    fc_shade_->hide();
    today_line_ = new QGraphicsLineItem(chart);
    QPen today_pen(c_muted(), 1.0, Qt::DotLine);
    today_pen.setCosmetic(true);
    today_line_->setPen(today_pen);
    today_line_->setZValue(1001);
    today_line_->setAcceptedMouseButtons(Qt::NoButton);
    today_line_->hide();
    today_lbl_ = new QGraphicsSimpleTextItem(chart);
    QFont today_font = today_lbl_->font();
    today_font.setPixelSize(9);
    today_lbl_->setFont(today_font);
    today_lbl_->setBrush(QBrush(c_muted()));
    today_lbl_->setZValue(1001);
    today_lbl_->setAcceptedMouseButtons(Qt::NoButton);
    today_lbl_->hide();
    notes_layer_ = std::make_unique<detail::HhpNoteLayer>(chart);
    // Resize, legend reflow and axis-label width changes all move the plot area.
    connect(chart, &QChart::plotAreaChanged, this, [this](const QRectF&) { relayout_overlays(); });

    auto* view = new HoverChartView(chart, this); // the view takes ownership of the chart
    view_ = view;
    view->setRenderHint(QPainter::Antialiasing, true);
    view->setFrameShape(QFrame::NoFrame);
    view->setBackgroundBrush(QBrush(c_card()));
    view->setMinimumHeight(kDefaultPlotMinHeight);
    view->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    view->setMouseTracking(true);
    view->viewport()->setMouseTracking(true);

    // "Empty" overlay: child of the view, kept full-size (text centred) on every resize.
    empty_lbl_ = new QLabel(view);
    empty_lbl_->setAlignment(Qt::AlignCenter);
    empty_lbl_->setWordWrap(true);
    empty_lbl_->setAttribute(Qt::WA_TransparentForMouseEvents);
    empty_lbl_->setStyleSheet(
        QStringLiteral("color: %1; font-size: 12px; background: transparent;").arg(css(c_muted())));
    empty_lbl_->setGeometry(view->rect());
    empty_lbl_->hide();

    view->on_move = [this](const QPointF& pos) {
        in_view_ = true;
        if (leave_timer_)
            leave_timer_->stop();
        QChart* ch = view_->chart();
        if (!ch || ch->series().isEmpty()) {
            on_leave();
            return;
        }
        const QPointF cp = ch->mapFromScene(view_->mapToScene(pos.toPoint()));
        // Note marker/label under the cursor for kCardDwellMs → its sticky card (or swap to it). Nothing hides the
        // card here: it stays while the cursor is anywhere over the view (or the card). A pinned card is not
        // swapped by hovering — only by clicking another marker.
        QRectF hit;
        const int ni = note_at(cp, &hit);
        hover_note_ = ni;
        hover_rect_ = ni >= 0 ? hit : QRectF();
        if (ni < 0 || ni == card_note_ || (card_ && card_->pinned())) {
            dwell_note_ = -1;
            if (dwell_timer_)
                dwell_timer_->stop();
        } else if (ni != dwell_note_) {
            ensure_card();
            dwell_note_ = ni;
            dwell_timer_->start(kCardDwellMs);
        }
        const QRectF plot = ch->plotArea();
        if (!plot.contains(cp)) {
            if (ni >= 0) { // on a marker just outside the plot: keep its dwell/card, drop the crosshair
                crosshair_->hide();
                hover_lbl_->clear();
            } else {
                on_leave();
            }
            return;
        }
        crosshair_->setLine(cp.x(), plot.top(), cp.x(), plot.bottom());
        crosshair_->show();
        on_hover(ch->mapToValue(cp).x());
    };
    view->on_enter = [this]() {
        in_view_ = true;
        if (leave_timer_)
            leave_timer_->stop();
    };
    view->on_leave = [this]() {
        in_view_ = false;
        on_leave();
        arm_card_leave();
    };
    view->on_press = [this](const QPointF& pos) { on_press(pos); };
    view->on_resize = [this]() {
        if (empty_lbl_)
            empty_lbl_->setGeometry(view_->rect());
    };

    root->addWidget(view, 1);

    update_range_buttons();
}

void HhpChart::set_series(const QVector<HhpChartSeries>& series, const QString& y_title, int y_decimals,
                          bool y_floor_zero) {
    hide_card();
    series_.clear();
    series_.reserve(series.size());
    bool any_points = false;
    for (const HhpChartSeries& s : series) {
        HhpChartSeries c = s;
        c.points = clean_points(s.points);
        c.lower = clean_points(s.lower);
        any_points = any_points || !c.points.isEmpty() || !c.lower.isEmpty();
        series_.append(std::move(c));
    }
    y_title_ = y_title;
    y_decimals_ = std::clamp(y_decimals, 0, 6);
    y_floor_zero_ = y_floor_zero;
    empty_msg_ = any_points ? QString() : QStringLiteral("Không có dữ liệu.");
    rebuild_chart();
}

void HhpChart::set_right_scale(double divisor, const QString& title, int decimals) {
    right_divisor_ = (std::isfinite(divisor) && divisor > 0) ? divisor : 0.0;
    right_title_ = title;
    right_decimals_ = std::clamp(decimals, 0, 6);
}

void HhpChart::set_range(const QString& key) {
    const QString k = range_keys().contains(key) ? key : QStringLiteral("ALL");
    if (k == range_) {
        update_range_buttons();
        return;
    }
    range_ = k;
    hide_card();
    update_range_buttons();
    rebuild_chart();
    emit range_changed(range_);
}

void HhpChart::clear(const QString& message) {
    hide_card();
    series_.clear();
    empty_msg_ = message;
    notes_.clear();
    notes_layer_->set_notes(notes_);
    fc_start_ms_ = 0;
    fc_label_.clear();
    fc_basis_.clear();
    rebuild_chart();
}

void HhpChart::set_notes(const QVector<HhpChartNote>& notes) {
    hide_card(); // indices change: drop the card (and any pending dwell) of the old note set
    hover_note_ = -1;
    hover_rect_ = QRectF();
    notes_ = notes;
    notes_layer_->set_notes(notes_);
    relayout_overlays();
}

void HhpChart::set_forecast(qreal start_ms, const QString& legend_label, const QVector<HhpChartSpan>& basis) {
    fc_start_ms_ = (std::isfinite(start_ms) && start_ms > 0) ? start_ms : 0;
    fc_label_ = legend_label;
    fc_basis_ = basis;
}

void HhpChart::set_forecast_visible(bool on) {
    if (on == forecast_visible_) {
        update_forecast_button();
        return;
    }
    forecast_visible_ = on;
    rebuild_chart();
}

void HhpChart::set_log_y(bool on) {
    if (on == log_y_)
        return;
    log_y_ = on;
    hide_card(); // every marker moves
    if (!series_.isEmpty()) // not plotted yet (or cleared): nothing to redraw, the next set_series() applies it
        rebuild_chart();
}

double HhpChart::plot_y(double y) const {
    if (!log_active_)
        return y;
    return y > 0 ? std::log10(y) : kNaN;
}

void HhpChart::update_forecast_button() {
    if (!fc_btn_)
        return;
    const bool any = std::any_of(series_.cbegin(), series_.cend(),
                                 [](const HhpChartSeries& s) { return s.forecast && !s.points.isEmpty(); });
    fc_btn_->setChecked(forecast_visible_);
    fc_btn_->setStyleSheet(fc_pill_style(forecast_visible_));
    fc_btn_->setVisible(any);
}

QVector<HhpChartNoteGeom> HhpChart::note_geometry() const {
    QVector<HhpChartNoteGeom> out;
    if (!notes_layer_)
        return out;
    QChart* ch = view_->chart();
    const QTransform vt = view_->viewportTransform();
    const auto to_view = [&](const QRectF& r) { return r.isEmpty() ? QRectF() : vt.mapRect(ch->mapRectToScene(r)); };
    const auto line_to_view = [&](const QLineF& l) {
        return l.isNull() ? QLineF() : QLineF(vt.map(ch->mapToScene(l.p1())), vt.map(ch->mapToScene(l.p2())));
    };
    for (const detail::HhpNoteLayer::Geom& g : notes_layer_->geometry())
        out.append({g.id, to_view(g.marker), to_view(g.label), line_to_view(g.lead)});
    return out;
}

int HhpChart::note_at(const QPointF& chart_pos, QRectF* hit_chart) const {
    return notes_layer_ ? notes_layer_->hit(chart_pos, hit_chart) : -1;
}

qreal HhpChart::forecast_hi_ms(qreal now_ms) const {
    // ALL → the whole tail; any other range → as far forward as it looks back (history keeps ≥ 50% of the width).
    const qreal cut = range_cutoff(range_, now_ms);
    return cut > 0 ? now_ms + (now_ms - cut) : kInf;
}

const HhpChartSeries* HhpChart::main_line() const {
    const HhpChartSeries* main = nullptr;
    for (const HhpChartSeries& s : series_) {
        if (!s.forecast && s.kind == HhpChartSeries::Kind::Line && !s.points.isEmpty())
            main = &s;
    }
    return main;
}

double HhpChart::main_line_y(qreal x_ms) const {
    const HhpChartSeries* main = main_line();
    if (!main)
        return kNaN;
    const QVector<QPointF>& pts = main->points;
    if (x_ms < std::max(cut_ms_, pts.first().x()) || x_ms > pts.last().x())
        return kNaN;
    const auto it = std::lower_bound(pts.cbegin(), pts.cend(), x_ms, x_below);
    if (it == pts.cend())
        return kNaN;
    if (it == pts.cbegin() || it->x() == x_ms)
        return it->y();
    const auto prev = it - 1;
    const qreal dx = it->x() - prev->x();
    return dx > 0 ? prev->y() + (it->y() - prev->y()) * (x_ms - prev->x()) / dx : it->y();
}

void HhpChart::relayout_overlays() {
    if (!notes_layer_ || !view_)
        return;
    QChart* ch = view_->chart();
    const QRectF pa = ch->plotArea();
    const bool live = anchor_ && pa.width() > 1.0 && pa.height() > 1.0;

    // Divider "hôm nay" + shaded forecast region.
    QVector<QRectF> reserved;
    bool divider = false;
    if (live && fc_drawn_ && forecast_visible_ && fc_start_ms_ > 0 && fc_start_ms_ >= x_min_ms_ &&
        fc_start_ms_ <= x_max_ms_) {
        const qreal x = ch->mapToPosition(QPointF(fc_start_ms_, 0.0), anchor_).x();
        if (x >= pa.left() - 0.5 && x <= pa.right() + 0.5) {
            divider = true;
            today_line_->setLine(x, pa.top(), x, pa.bottom());
            fc_shade_->setRect(QRectF(QPointF(x, pa.top()), QPointF(pa.right(), pa.bottom())));
            today_lbl_->setText(QStringLiteral("Hôm nay · dữ liệu tới %1").arg(fmt_date(fc_start_ms_)));
            const QSizeF sz = today_lbl_->boundingRect().size();
            qreal lx = x + 4.0;
            if (lx + sz.width() > pa.right() - 2.0)
                lx = x - 4.0 - sz.width(); // flips left near the right edge
            today_lbl_->setPos(lx, pa.top() + 2.0);
            reserved.append(QRectF(QPointF(lx, pa.top() + 2.0), sz));
        }
    }
    today_line_->setVisible(divider);
    today_lbl_->setVisible(divider);
    fc_shade_->setVisible(divider);

    detail::NoteLayoutInput in;
    if (live) {
        in.plot = pa;
        in.x_min = x_min_ms_;
        in.x_max = x_max_ms_;
        QAbstractSeries* anchor = anchor_;
        in.map = [this, ch, anchor](qreal x, double y) { return ch->mapToPosition(QPointF(x, plot_y(y)), anchor); };
        in.snap_y = [this](qreal x) { return main_line_y(x); };
        // Labels (and their leads) may not cover the main line nor its dashed continuation (forecast Line series,
        // e.g. the basket's "… nếu giá đứng yên"); band edges and mean lines (history and forecast) are soft
        // obstacles — labels move off them when there is room.
        const auto add_poly = [&](QVector<QVector<QPointF>>& to, const QVector<QPointF>& vis) {
            QVector<QPointF> poly;
            poly.reserve(vis.size());
            for (const QPointF& p : vis)
                poly.append(ch->mapToPosition(QPointF(p.x(), plot_y(p.y())), anchor_));
            if (!poly.isEmpty())
                to.append(poly);
        };
        const bool any_notes = !notes_.isEmpty(); // no notes (DeepFA, ticker dialog) → nothing to map
        const HhpChartSeries* main = any_notes ? main_line() : nullptr;
        if (main)
            add_poly(in.lines, visible_span(main->points, std::max(cut_ms_, x_min_ms_), x_max_ms_));
        const bool fc_on = fc_drawn_ && forecast_visible_;
        for (const HhpChartSeries& s : std::as_const(series_)) {
            if (!any_notes || &s == main || (s.forecast && !fc_on))
                continue;
            const qreal hi = s.forecast ? std::min(hi_ms_, x_max_ms_) : x_max_ms_;
            if (s.forecast && s.kind == HhpChartSeries::Kind::Line) {
                add_poly(in.lines, visible_span(s.points, cut_ms_, hi));
            } else if (s.kind == HhpChartSeries::Kind::Band) {
                add_poly(in.soft, visible_span(s.points, cut_ms_, hi));
                add_poly(in.soft, visible_span(s.lower, cut_ms_, hi));
            } else if (s.kind == HhpChartSeries::Kind::Dashed) {
                add_poly(in.soft, visible_span(s.points, cut_ms_, hi));
            }
        }
        in.reserved = reserved;
    }
    notes_layer_->relayout(in); // empty plot → every note hidden
    if (live && card_note_ >= 0)
        place_card(); // resize / forecast toggle: follow the marker (or hide when it is gone)
}

void HhpChart::set_plot_min_height(int px) {
    view_->setMinimumHeight(std::max(0, px));
}

void HhpChart::update_range_buttons() {
    for (QPushButton* btn : range_btns_)
        btn->setStyleSheet(pill_style(btn->text() == range_));
}

void HhpChart::set_overlay(const QString& text) {
    empty_lbl_->setText(text);
    if (text.isEmpty()) {
        empty_lbl_->hide();
        return;
    }
    empty_lbl_->setGeometry(view_->rect());
    empty_lbl_->raise();
    empty_lbl_->show();
}

void HhpChart::rebuild_chart() {
    // set_log_active_listener(): report a switch of log_active_ on whichever path this rebuild returns by.
    struct LogSwitchNotice {
        HhpChart* self;
        bool before;
        ~LogSwitchNotice() {
            if (self->log_active_ != before && self->log_listener_)
                self->log_listener_(self->log_active_);
        }
    } log_notice{this, log_active_};
    QChart* chart = view_->chart();
    anchor_ = nullptr; // removeAllSeries() deletes it
    fc_drawn_ = false;
    log_active_ = false; // set_log_y(): decided below once the visible values are known
    chart->removeAllSeries(); // deletes the series (and the edge QLineSeries parented to each area)
    const QList<QAbstractAxis*> old_axes = chart->axes();
    for (QAbstractAxis* axis : old_axes) {
        chart->removeAxis(axis);
        delete axis;
    }
    on_leave();
    update_forecast_button();

    qreal last_x = -kInf;
    for (const HhpChartSeries& s : series_) {
        if (!s.points.isEmpty())
            last_x = std::max(last_x, s.points.last().x());
        if (!s.lower.isEmpty())
            last_x = std::max(last_x, s.lower.last().x());
    }
    if (!has(last_x)) {
        cut_ms_ = 0;
        set_overlay(empty_msg_);
        relayout_overlays(); // hides notes + divider
        return;
    }
    // Ranges count back from today (like the page's _cut()), not from the last point: a series that
    // stopped updating must come up empty under "YTD"/"1Y" instead of showing an old window.
    const qreal now = static_cast<qreal>(QDateTime::currentMSecsSinceEpoch());
    cut_ms_ = range_cutoff(range_, now);
    hi_ms_ = forecast_hi_ms(now);

    qreal x_lo = kInf, x_hi = -kInf;
    double y_lo = kInf, y_hi = -kInf;
    bool include_zero = false;
    const auto extend = [&](const QVector<QPointF>& pts) {
        for (const QPointF& p : pts) {
            x_lo = std::min(x_lo, p.x());
            x_hi = std::max(x_hi, p.x());
            y_lo = std::min(y_lo, p.y());
            y_hi = std::max(y_hi, p.y());
        }
    };

    // Log-y (set_log_y): decided on every visible raw value before anything is drawn — log10 needs y > 0, and an Area
    // series fills down to y = 0. Series get log10 copies; series_ (hover, snapping) keeps the raw values.
    if (log_y_) {
        bool positive = true;
        bool any = false;
        for (const HhpChartSeries& s : series_) {
            if (s.forecast && !forecast_visible_)
                continue;
            const qreal hi = s.forecast ? hi_ms_ : kInf;
            const QVector<QPointF> up = visible_span(s.points, cut_ms_, hi);
            const QVector<QPointF> low =
                s.kind == HhpChartSeries::Kind::Band ? visible_span(s.lower, cut_ms_, hi) : QVector<QPointF>();
            if (up.isEmpty() || (s.kind == HhpChartSeries::Kind::Band && low.isEmpty()))
                continue;
            any = true;
            positive = positive && s.kind != HhpChartSeries::Kind::Area;
            for (const QVector<QPointF>* pts : {&up, &low})
                for (const QPointF& p : *pts)
                    positive = positive && p.y() > 0;
        }
        log_active_ = any && positive;
    }
    const auto drawn = [this](const QVector<QPointF>& pts) { return log_active_ ? log_points(pts) : pts; };

    QList<QAbstractSeries*> added;
    QList<QAbstractSeries*> fc_added; // forecast chart series (edges included): no legend marker of their own
    for (int pass = 0; pass < 3; ++pass) {
        for (const HhpChartSeries& s : series_) {
            if (draw_pass(s.kind) != pass)
                continue;
            if (s.forecast && !forecast_visible_)
                continue;
            const qreal hi = s.forecast ? hi_ms_ : kInf;
            const QVector<QPointF> upper = visible_span(s.points, cut_ms_, hi);
            if (upper.isEmpty())
                continue;
            QVector<QPointF> lower;
            if (s.kind == HhpChartSeries::Kind::Band) {
                lower = visible_span(s.lower, cut_ms_, hi);
                if (lower.isEmpty())
                    continue;
                extend(lower);
            }
            if (s.kind == HhpChartSeries::Kind::Area)
                include_zero = true;
            if (s.forecast) {
                const qsizetype before = fc_added.size();
                add_forecast(chart, s, drawn(upper), drawn(lower), fc_added);
                added.append(fc_added.mid(before));
            } else if (s.kind == HhpChartSeries::Kind::Band) {
                added.append(add_band(chart, s, drawn(upper), drawn(lower)));
            } else if (s.kind == HhpChartSeries::Kind::Area) {
                added.append(add_area(chart, s, upper));
            } else {
                added.append(add_line(chart, s, drawn(upper), s.kind == HhpChartSeries::Kind::Dashed));
            }
            extend(upper);
        }
    }

    if (added.isEmpty()) {
        set_overlay(QStringLiteral("Không có dữ liệu trong khoảng %1 — chuỗi dừng ở %2.")
                        .arg(range_, fmt_date(last_x)));
        relayout_overlays();
        return;
    }
    set_overlay(QString());

    // One legend entry for every forecast series: an empty dashed line named after set_forecast()'s label.
    fc_drawn_ = !fc_added.isEmpty();
    if (fc_drawn_) {
        auto* legend_line = new QLineSeries();
        legend_line->setName(fc_label_.isEmpty() ? QStringLiteral("Dự phóng (nét đứt)") : fc_label_);
        chart->addSeries(legend_line);
        legend_line->setPen(forecast_pen(c_muted(), 1.4));
        added.append(legend_line);
        for (QAbstractSeries* s : std::as_const(fc_added))
            for (QLegendMarker* mk : chart->legend()->markers(s))
                mk->setVisible(false);
        for (QLegendMarker* mk : chart->legend()->markers(legend_line))
            mk->setShape(QLegend::MarkerShapeFromSeries);
    }

    // ── X axis (datetime) ────────────────────────────────────────────────────
    if (x_hi - x_lo < 1.0) {
        x_lo -= kDayMs;
        x_hi += kDayMs;
    }
    const qreal x_span = x_hi - x_lo;
    auto* x_axis = new QDateTimeAxis();
    chart->addAxis(x_axis, Qt::AlignBottom);
    x_axis->setTickCount(7);
    // Ticks are evenly spaced, not on calendar boundaries, so a bare "yyyy" repeats a year (5Y showed
    // 2025 twice) and sits mid-year; month/year stays unambiguous at every span.
    x_axis->setFormat(x_span > 180 * kDayMs ? QStringLiteral("MM/yyyy") : QStringLiteral("dd/MM"));
    x_axis->setRange(QDateTime::fromMSecsSinceEpoch(static_cast<qint64>(x_lo)),
                     QDateTime::fromMSecsSinceEpoch(static_cast<qint64>(x_hi)));
    style_axis(x_axis);

    if (log_active_) { // set_log_y(): log10 plot units, round labels (the linear block below stays untouched)
        add_log_axes(chart, x_axis, added, y_lo, y_hi, {y_title_, y_decimals_, y_floor_zero_, right_divisor_,
                                                         right_title_, right_decimals_});
        anchor_ = added.first();
        x_min_ms_ = x_lo;
        x_max_ms_ = x_hi;
        relayout_overlays();
        return;
    }

    // ── Y axis (value): every visible value, padded 5%, optional 0 floor, nice ticks ──
    if (include_zero) {
        y_lo = std::min(y_lo, 0.0);
        y_hi = std::max(y_hi, 0.0);
    }
    const double y_span = y_hi - y_lo;
    const double pad = y_span > 1e-12 ? y_span * kPadFraction : std::max(std::abs(y_hi) * kPadFraction, 1e-3);
    double lo = y_lo - pad;
    double hi = y_hi + pad;
    if (y_floor_zero_)
        lo = std::max(0.0, lo);
    if (hi <= lo)
        hi = lo + 1.0;
    auto* y_axis = new QValueAxis();
    chart->addAxis(y_axis, Qt::AlignLeft);
    y_axis->setRange(lo, hi);
    y_axis->applyNiceNumbers();
    y_axis->setLabelFormat(QStringLiteral("%.%1f").arg(y_decimals_));
    style_axis(y_axis);
    if (y_title_.isEmpty()) {
        y_axis->setTitleVisible(false);
    } else {
        y_axis->setTitleText(y_title_);
        QFont tf = y_axis->titleFont();
        tf.setPixelSize(10);
        tf.setBold(false);
        y_axis->setTitleFont(tf);
        y_axis->setTitleBrush(QBrush(c_muted()));
        y_axis->setTitleVisible(true);
    }

    // Trục bên phải (Qt::AlignRight) hiển thị đầy đủ đơn vị và nhãn định dạng. With set_right_scale()
    // it is a second unit over the same plot (e.g. P/E = index ÷ EPS now): its range is the left range
    // divided exactly — no nice-number rounding, which would shift the mapping — with ticks on round
    // values, and no series attached to it.
    const bool scaled = right_divisor_ > 0;
    const QString r_title = scaled ? right_title_ : y_title_;
    auto* y_axis_r = new QValueAxis();
    chart->addAxis(y_axis_r, Qt::AlignRight);
    if (scaled) {
        const double r_lo = y_axis->min() / right_divisor_;
        const double r_hi = y_axis->max() / right_divisor_;
        y_axis_r->setRange(r_lo, r_hi);
        // ~6 ticks on a 1/2/2.5/5 × 10^k step anchored at 0.
        const double raw = std::max(1e-9, (r_hi - r_lo) / 6.0);
        const double mag = std::pow(10.0, std::floor(std::log10(raw)));
        double step = mag;
        for (double m : {1.0, 2.0, 2.5, 5.0, 10.0})
            if (raw <= m * mag) {
                step = m * mag;
                break;
            }
        y_axis_r->setTickType(QValueAxis::TicksDynamic);
        y_axis_r->setTickAnchor(0.0);
        y_axis_r->setTickInterval(step);
        y_axis_r->setLabelFormat(QStringLiteral("%.%1fx").arg(right_decimals_));
    } else {
        y_axis_r->setRange(lo, hi);
        y_axis_r->applyNiceNumbers();
        y_axis_r->setLabelFormat(QStringLiteral("%.%1f").arg(y_decimals_));
    }
    style_axis(y_axis_r);
    y_axis_r->setGridLineVisible(false);
    if (r_title.isEmpty()) {
        y_axis_r->setTitleVisible(false);
    } else {
        y_axis_r->setTitleText(r_title);
        QFont tf = y_axis_r->titleFont();
        tf.setPixelSize(10);
        tf.setBold(false);
        y_axis_r->setTitleFont(tf);
        y_axis_r->setTitleBrush(QBrush(c_muted()));
        y_axis_r->setTitleVisible(true);
    }

    for (QAbstractSeries* s : added) {
        s->attachAxis(x_axis);
        s->attachAxis(y_axis);
        if (!scaled)
            s->attachAxis(y_axis_r);
    }

    anchor_ = added.first(); // on x + LEFT y: notes and the divider map through it
    x_min_ms_ = x_lo;
    x_max_ms_ = x_hi;
    relayout_overlays(); // again on plotAreaChanged once the new axes are laid out
}

void HhpChart::on_hover(qreal x_ms) {
    const auto value_text = [this](double v) {
        return y_floor_zero_ ? fmt_vi(v, y_decimals_) : fmt_ratio(v, y_decimals_);
    };
    const auto span = [](const QColor& color, const QString& text) {
        return QStringLiteral("<span style=\"color:%1\">%2</span>").arg(css(color), text);
    };

    // Date shown = x of the data point closest to the cursor (all series share one grid in practice).
    qreal snap_x = x_ms;
    qreal best_dx = kInf;
    const auto note_x = [&](qreal px) {
        const qreal dx = std::abs(px - x_ms);
        if (dx < best_dx) {
            best_dx = dx;
            snap_x = px;
        }
    };

    QStringList line_parts;
    QStringList band_parts;
    for (const HhpChartSeries& s : series_) {
        if (s.forecast && !forecast_visible_)
            continue;
        const qreal hi = s.forecast ? hi_ms_ : kInf; // history ends before now; only forecasts are clipped
        const qsizetype i = nearest_in(s.points, cut_ms_, hi, x_ms);
        if (i < 0)
            continue;
        const QPointF& p = s.points.at(i);
        const QString name = span(s.color, s.name.toHtmlEscaped());
        if (s.kind == HhpChartSeries::Kind::Band) {
            const qsizetype j = nearest_in(s.lower, cut_ms_, hi, x_ms);
            if (j < 0)
                continue;
            note_x(p.x());
            const QString range_txt =
                value_text(s.lower.at(j).y()) + QStringLiteral("–") + value_text(p.y());
            band_parts << name + QLatin1Char(' ') + span(c_text(), range_txt);
        } else {
            note_x(p.x());
            line_parts << name + QLatin1Char(' ') + span(c_text(), value_text(p.y()));
        }
    }

    if (line_parts.isEmpty() && band_parts.isEmpty()) {
        hover_lbl_->clear();
        return;
    }
    const QString sep = QStringLiteral(" · ");
    QString date_txt = fmt_date(snap_x);
    QString basis;
    if (fc_drawn_ && fc_start_ms_ > 0 && snap_x > fc_start_ms_) {
        date_txt += sep + span(c_gold(), QStringLiteral("dự phóng"));
        for (const HhpChartSpan& b : fc_basis_) {
            if (snap_x >= b.x0_ms && snap_x < b.x1_ms && !b.text.isEmpty()) {
                basis = sep + b.text; // caller-escaped rich text (e.g. the EPS basis of that year)
                break;
            }
        }
    }
    hover_lbl_->setText(date_txt + sep + (line_parts + band_parts).join(sep) + basis);
}

void HhpChart::on_leave() {
    if (crosshair_)
        crosshair_->hide();
    if (hover_lbl_)
        hover_lbl_->clear();
    hover_note_ = -1;
    hover_rect_ = QRectF();
    dwell_note_ = -1; // the sticky card itself stays (see arm_card_leave)
    if (dwell_timer_)
        dwell_timer_->stop();
}

// ── sticky note card ────────────────────────────────────────────────────────

QWidget* HhpChart::note_card() const {
    return card_ && card_note_ >= 0 && card_->isVisible() ? card_ : nullptr;
}

QString HhpChart::note_card_id() const {
    return note_card() ? card_->note_id() : QString();
}

bool HhpChart::note_card_pinned() const {
    return note_card() && card_->pinned();
}

void HhpChart::ensure_card() {
    if (card_)
        return;
    card_ = new detail::HhpNoteCard(this);
    card_->on_enter = [this]() {
        in_card_ = true;
        leave_timer_->stop();
    };
    card_->on_leave = [this]() {
        in_card_ = false;
        arm_card_leave();
    };
    card_->on_close = [this]() { hide_card(); };
    dwell_timer_ = new QTimer(this);
    dwell_timer_->setSingleShot(true);
    connect(dwell_timer_, &QTimer::timeout, this, [this]() {
        const int ni = dwell_note_;
        dwell_note_ = -1;
        if (ni >= 0 && ni == hover_note_ && in_view_ && !card_->pinned())
            show_card(ni, false);
    });
    leave_timer_ = new QTimer(this);
    leave_timer_->setSingleShot(true);
    connect(leave_timer_, &QTimer::timeout, this, [this]() {
        if (card_note_ >= 0 && !card_->pinned() && !in_view_ && !in_card_)
            hide_card();
    });
    // Installed on qApp only while the card shows. Esc anywhere closes it and every other chart's open card (and is
    // consumed); this chart hidden (tab switch, dialog closed) or its window deactivated → hide; this chart or any
    // ancestor moved (window dragged, page scrolled by wheel / scrollbar / keys, relayout) → follow the marker.
    card_filter_ = new FnFilter(
        [this](QObject* o, QEvent* e) {
            if (card_note_ < 0)
                return false;
            const auto follow = [this]() {
                QTimer::singleShot(0, this, [this]() {
                    if (card_note_ >= 0)
                        place_card();
                });
            };
            switch (e->type()) {
                case QEvent::ShortcutOverride:
                case QEvent::KeyPress:
                    if (static_cast<QKeyEvent*>(e)->key() != Qt::Key_Escape)
                        return false;
                    if (e->type() == QEvent::ShortcutOverride) { // deliver Esc as a key press, not a shortcut
                        e->accept();
                        return true;
                    }
                    for (HhpChart* c : QVector<HhpChart*>(open_cards())) // copy: hide_card() edits the list
                        c->hide_card();
                    return true;
                case QEvent::Hide:
                    if (o == this)
                        hide_card();
                    return false;
                case QEvent::WindowDeactivate:
                    if (o == this && QApplication::activeWindow() != card_)
                        hide_card();
                    return false;
                case QEvent::Move:
                    if (o == this || (o->isWidgetType() && static_cast<QWidget*>(o)->isAncestorOf(this)))
                        follow();
                    return false;
                default:
                    return false;
            }
        },
        this);
}

void HhpChart::show_card(int note, bool pin) {
    if (note < 0 || note >= notes_.size())
        return;
    ensure_card();
    dwell_note_ = -1;
    dwell_timer_->stop();
    leave_timer_->stop();
    const bool same = card_note_ == note && card_->isVisible();
    card_note_ = note;
    if (!same)
        card_->set_note(notes_.at(note));
    card_->set_pinned(pin || (same && card_->pinned()));
    place_card(); // hides the card again when the marker is not drawn
    if (card_note_ < 0)
        return;
    qApp->installEventFilter(card_filter_); // Qt keeps one entry per filter: a swap does not stack it
    if (!open_cards().contains(this))
        open_cards().append(this);
    if (!card_->isVisible())
        card_->show();
}

void HhpChart::hide_card() {
    if (!card_)
        return;
    dwell_timer_->stop();
    leave_timer_->stop();
    dwell_note_ = -1;
    card_note_ = -1;
    in_card_ = false;
    open_cards().removeAll(this);
    if (qApp)
        qApp->removeEventFilter(card_filter_);
    card_->set_pinned(false);
    if (card_->isVisible())
        card_->hide();
}

void HhpChart::place_card() {
    if (!card_ || card_note_ < 0)
        return;
    const QVector<detail::HhpNoteLayer::Geom> g = notes_layer_->geometry();
    if (card_note_ >= g.size() || g.at(card_note_).marker.isEmpty()) {
        hide_card();
        return;
    }
    // The marker's hover area (global coords) is what the card may never cover.
    constexpr double pad = detail::notes::kHitPad;
    const QRectF mk = g.at(card_note_).marker.adjusted(-pad, -pad, pad, pad);
    const QRect vr = view_->viewportTransform().mapRect(view_->chart()->mapRectToScene(mk)).toAlignedRect();
    card_->place_beside(QRect(view_->viewport()->mapToGlobal(vr.topLeft()), vr.size()));
}

void HhpChart::arm_card_leave() {
    if (card_ && card_note_ >= 0 && !card_->pinned() && !in_view_ && !in_card_)
        leave_timer_->start(kCardLeaveMs);
}

void HhpChart::on_press(const QPointF& pos) {
    QChart* ch = view_->chart();
    if (!ch)
        return;
    const QPointF cp = ch->mapFromScene(view_->mapToScene(pos.toPoint()));
    const int ni = note_at(cp, nullptr);
    if (ni >= 0)
        show_card(ni, true); // pin (another marker: swap + pin)
    else if (card_note_ >= 0 && ch->plotArea().contains(cp))
        hide_card(); // click on empty plot
}

} // namespace fincept::screens::hhp
