// src/screens/langkinh/LkChart.cpp
// Lăng Kính FFT — biểu đồ đường thời gian và scatter cho LkBlockView (CONTRACT §3.1, §4).
// Hợp đồng block v2: khoá nội bộ "_hoso" (LkBlockView gắn khi payload có layout "hoso") → kiểu thẻ .fig (nền
// surface, chữ trục mono); series "alpha" cho line/bar; "legend" riêng → ẩn chú giải QtCharts (LkPage vẽ dưới thẻ).
#include "screens/langkinh/LkChart.h"

#include "screens/langkinh/LkBlockView.h"
#include "screens/langkinh/LkChartLayers.h"
#include "screens/langkinh/LkChartUtil.h"
#include "ui/theme/Theme.h"
#include "ui/theme/ThemeManager.h"

#include <QAreaSeries>
#include <QBrush>
#include <QChart>
#include <QCursor>
#include <QDate>
#include <QDateTime>
#include <QDateTimeAxis>
#include <QFont>
#include <QGraphicsLayout>
#include <QGraphicsSimpleTextItem>
#include <QJsonArray>
#include <QKeyEvent>
#include <QLabel>
#include <QLegend>
#include <QLegendMarker>
#include <QLineSeries>
#include <QLocale>
#include <QMouseEvent>
#include <QPen>
#include <QScatterSeries>
#include <QStringList>
#include <QTimeZone>
#include <QToolTip>
#include <QValueAxis>
#include <QWheelEvent>

#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>

namespace fincept::screens::langkinh {

// Helper tự do (lkchart::…) ở LkChartUtil.cpp.

// ═════════════════════════════════════════════════════════════════════════════
// LkLineChart
// ═════════════════════════════════════════════════════════════════════════════

LkLineChart::LkLineChart(const QJsonObject& block, QWidget* parent) : QChartView(new QChart(), parent) {
    using namespace lkchart;
    const bool hoso = block.value(QStringLiteral("_hoso")).toBool(false);
    QChart* ch = chart();
    style_chart(ch, hoso);
    style_view(this, hoso);

    // 1) Trục thời gian — giữ chỉ số gốc để y[i] khớp x[i] kể cả khi có x hỏng.
    const QJsonArray xs = block.value(QStringLiteral("x")).toArray();
    const int n = static_cast<int>(xs.size());
    x_.fill(0, n);
    for (int i = 0; i < n; ++i) {
        qint64 ms = 0;
        if (parse_x(xs.at(i), &ms)) {
            x_[i] = ms;
            order_.append(i);
        }
    }
    std::stable_sort(order_.begin(), order_.end(), [this](int a, int b) { return x_[a] < x_[b]; });
    if (order_.isEmpty())
        return;

    // 2) Chuỗi số
    const QJsonObject left_cfg = block.value(QStringLiteral("left")).toObject();
    const QJsonObject right_cfg = block.value(QStringLiteral("right")).toObject();
    const QJsonArray sers = block.value(QStringLiteral("series")).toArray();
    bool want_right = block.value(QStringLiteral("right")).isObject();
    for (const auto& sv : sers)
        if (sv.toObject().value(QStringLiteral("axis")).toString() == QLatin1String("right"))
            want_right = true;

    struct Placed {
        QAbstractSeries* s;
        bool right;
        bool in_legend;
    };
    QVector<Placed> placed;
    Range rl;
    Range rr;
    qint64 pad_ms = 0; // nửa bề rộng cột lớn nhất — nới trục X để cột ở mép không bị cắt
    const double span_x = static_cast<double>(x_[order_.last()] - x_[order_.first()]); // độ dài trục (ms)

    // Dải (style "band") thêm TRƯỚC mọi series khác → luôn nằm dưới line (V3.2); điểm điền khi đã có trục.
    for (int si = 0; si < sers.size(); ++si) {
        const QJsonObject so = sers.at(si).toObject();
        if (so.value(QStringLiteral("style")).toString() != QLatin1String("band"))
            continue;
        const bool right = want_right && so.value(QStringLiteral("axis")).toString() == QLatin1String("right");
        const QString name = so.value(QStringLiteral("name")).toString().trimmed();
        bands_.add(ch, so, x_, order_, series_color(so.value(QStringLiteral("mau")).toString(), si, hoso),
                   name.isEmpty() ? tr("Dải %1").arg(si + 1) : name, right, [&](double v) { (right ? rr : rl).add(v); });
    }

    for (int si = 0; si < sers.size(); ++si) {
        const QJsonObject so = sers.at(si).toObject();
        if (so.isEmpty() || so.value(QStringLiteral("style")).toString() == QLatin1String("band"))
            continue;
        Line line;
        line.name = so.value(QStringLiteral("name")).toString().trimmed();
        if (line.name.isEmpty())
            line.name = tr("Chuỗi %1").arg(si + 1);
        const bool right = want_right && so.value(QStringLiteral("axis")).toString() == QLatin1String("right");
        const QString style = so.value(QStringLiteral("style")).toString(QStringLiteral("line"));
        const QColor color = series_color(so.value(QStringLiteral("mau")).toString(), si, hoso);
        double alpha = nan_value(); // hợp đồng v2: độ đục riêng của series (line/bar)
        if (finite_num(so.value(QStringLiteral("alpha")), &alpha))
            alpha = std::clamp(alpha, 0.05, 1.0);
        const QJsonArray ys = so.value(QStringLiteral("y")).toArray();
        line.y.fill(nan_value(), n);
        const int m = std::min(n, static_cast<int>(ys.size()));
        for (int i = 0; i < m; ++i) {
            double d = 0.0;
            if (finite_num(ys.at(i), &d))
                line.y[i] = d;
        }
        Range& rg = right ? rr : rl;

        if (style == QLatin1String("bar")) {
            // Cột cho chuỗi thưa (mốc cổ đông): vùng tô bậc thang đi từ 0.
            QVector<QPointF> pts;
            for (int idx : std::as_const(order_))
                if (std::isfinite(line.y[idx]))
                    pts.append(QPointF(static_cast<double>(x_[idx]), line.y[idx]));
            if (!pts.isEmpty()) {
                double gap = 0.0;
                for (int k = 1; k < pts.size(); ++k) {
                    const double g = pts[k].x() - pts[k - 1].x();
                    if (g > 0.0 && (gap <= 0.0 || g < gap))
                        gap = g;
                }
                double hw = gap > 0.0 ? gap * 0.35 : 10.0 * kDayMs;
                if (hoso) // hồ sơ: nửa bề rộng cột theo độ dài trục (≤ 4,5%), không chặn cứng 20 ngày → cột đọc được
                    hw = std::min(gap > 0.0 ? gap * 0.30 : 10.0 * kDayMs, std::max(10.0 * kDayMs, 0.045 * span_x));
                else
                    hw = std::min(hw, 20.0 * kDayMs);
                pad_ms = std::max(pad_ms, static_cast<qint64>(hw));

                auto* area = new QAreaSeries(ch);
                auto* upper = new QLineSeries(area);
                auto* lower = new QLineSeries(area);
                for (const QPointF& p : std::as_const(pts)) {
                    upper->append(p.x() - hw, 0.0);
                    upper->append(p.x() - hw, p.y());
                    upper->append(p.x() + hw, p.y());
                    upper->append(p.x() + hw, 0.0);
                    rg.add(p.y());
                }
                lower->append(pts.first().x() - hw, 0.0);
                lower->append(pts.last().x() + hw, 0.0);
                area->setUpperSeries(upper);
                area->setLowerSeries(lower);
                area->setName(line.name);
                QColor edge = color;
                QColor fill = color;
                fill.setAlpha(150);
                if (std::isfinite(alpha)) {
                    edge.setAlphaF(static_cast<float>(edge.alphaF() * alpha));
                    fill.setAlphaF(static_cast<float>(fill.alphaF() * alpha));
                }
                QPen pen(edge);
                pen.setWidthF(1.0);
                pen.setCosmetic(true);
                area->setPen(pen);
                area->setBrush(fill);
                ch->addSeries(area);
                placed.append({area, right, true});
                rg.bar = true;
                has_data_ = true;
            }
        } else {
            // null → đứt đoạn: mỗi đoạn liền là một QLineSeries; chỉ đoạn đầu hiện ở chú giải.
            const QPen pen = pen_for(style, color, hoso, alpha);
            QList<QPointF> seg;
            bool first = true;
            auto flush = [&]() {
                if (seg.isEmpty())
                    return;
                auto* ls = new QLineSeries();
                ls->setName(line.name);
                ls->setPen(pen);
                if (seg.size() == 1) {
                    ls->setPointsVisible(true);
                    ls->setMarkerSize(4.0);
                }
                ls->append(seg);
                ch->addSeries(ls);
                placed.append({ls, right, first});
                first = false;
                seg.clear();
            };
            for (int idx : std::as_const(order_)) {
                const double y = line.y[idx];
                if (std::isfinite(y)) {
                    seg.append(QPointF(static_cast<double>(x_[idx]), y));
                    rg.add(y);
                } else {
                    flush();
                }
            }
            flush();
            if (!first)
                has_data_ = true;
        }
        lines_.append(line);
    }
    if (!has_data_)
        return;
    // hband (V4.3, vd vùng gom trên trục giá) phải nằm trong khung trục.
    LkChartAnnot::grow(block.value(QStringLiteral("annotations")).toArray(),
                       [&](double v, bool r) { if (!r || want_right) (r ? rr : rl).add(v); });

    // 3) Trục
    qint64 x0 = x_[order_.first()] - pad_ms;
    qint64 x1 = x_[order_.last()] + pad_ms;
    if (hoso) { // hồ sơ: chừa mép 1,5% (2,5% khi có cột) — cột/điểm/nhãn cuối không bị cắt nửa ở mép vùng vẽ
        const qint64 edge = std::max<qint64>(kDayMs, static_cast<qint64>(span_x * (pad_ms > 0 ? 0.025 : 0.015)));
        x0 -= edge;
        x1 += edge;
    }
    if (x1 <= x0) {
        x0 -= 15 * kDayMs;
        x1 += 15 * kDayMs;
    }
    auto* ax = new QDateTimeAxis;
    ax->setFormat(QStringLiteral("MM/yy"));
    ax->setTickCount(8);
    if (hoso) { // trục ngắn: dd/MM (< 4 tháng), vạch cách ≥ 45 ngày (< 2 năm) → không lặp nhãn tháng "07/26 07/26"
        const double days = static_cast<double>(x1 - x0) / kDayMs;
        if (days < 124.0) {
            ax->setFormat(QStringLiteral("dd/MM"));
            ax->setTickCount(std::clamp(static_cast<int>(days / 14.0) + 1, 3, 7));
        } else if (days < 730.0) {
            ax->setTickCount(std::clamp(static_cast<int>(days / 45.0) + 1, 3, 8));
        }
    }
    ax->setRange(QDateTime::fromMSecsSinceEpoch(x0, QTimeZone::UTC), QDateTime::fromMSecsSinceEpoch(x1, QTimeZone::UTC));
    style_axis(ax, true, hoso);
    ch->addAxis(ax, Qt::AlignBottom);

    QValueAxis* ayl = make_value_axis(rl, left_cfg, true, hoso);
    ch->addAxis(ayl, Qt::AlignLeft);
    QValueAxis* ayr = nullptr;
    if (want_right && rr.ok()) {
        ayr = make_value_axis(rr, right_cfg, false, hoso);
        ch->addAxis(ayr, Qt::AlignRight);
    }

    QAbstractSeries* left_anchor = nullptr;
    QAbstractSeries* right_anchor = nullptr;
    for (const Placed& p : std::as_const(placed)) {
        p.s->attachAxis(ax);
        p.s->attachAxis(p.right && ayr ? ayr : ayl);
        if (!p.in_legend)
            hide_legend(ch, p.s);
        QAbstractSeries*& a = p.right && ayr ? right_anchor : left_anchor;
        if (!a)
            a = p.s;
    }
    bands_.finish(ch, ax, ayl, ayr);
    anchor_ = placed.first().s;
    // Có "legend" riêng (hợp đồng v2) → chú giải vẽ dưới thẻ bằng nét 18px; ẩn ô vuông của QtCharts.
    ch->legend()->setVisible(block.value(QStringLiteral("legend")).toArray().isEmpty());

    // Chú thích (V3.3): đặt lại vị trí mỗi khi vùng vẽ đổi (resize, legend xuống dòng…).
    const QJsonArray anns = block.value(QStringLiteral("annotations")).toArray();
    if (!anns.isEmpty()) {
        annot_ = new LkChartAnnot(ch, anns, left_anchor ? left_anchor : right_anchor, right_anchor, this);
        connect(ch, &QChart::plotAreaChanged, this, [this](const QRectF&) { annot_->relayout(); });
        annot_->relayout();
    }
}

namespace {
constexpr int kAnnotStickyPx = 56;     // tooltip chú thích giữ nguyên khi con trỏ còn trong bán kính này
constexpr int kAnnotTipMs = 10 * 60000; // và không tự tắt theo giờ (Qt mặc định ~10 s + độ dài chữ)
constexpr int kPinMaxW = 460;
} // namespace

void LkLineChart::mouseMoveEvent(QMouseEvent* event) {
    QChartView::mouseMoveEvent(event);
    if (!anchor_ || order_.isEmpty())
        return;
    const QPoint gpos = event->globalPosition().toPoint();
    const QPointF cp = chart()->mapFromScene(mapToScene(event->position().toPoint()));
    if (!chart()->plotArea().contains(cp)) {
        if (hover_idx_ >= 0 || hover_idx_ == -2) {
            QToolTip::hideText();
            hover_idx_ = -1;
        }
        return;
    }
    if (annot_) { // rê lên marker / nhãn / vạch dọc → tooltip `tip` của chú thích
        const QString at = annot_->tip_at(cp);
        if (!at.isEmpty()) {
            if (hover_idx_ != -2 || at != hover_tip_ || !QToolTip::isVisible()) {
                if (!pin_ || !pin_->isVisible() || pin_->text() != at)
                    QToolTip::showText(gpos, at, this, QRect(), kAnnotTipMs);
                tip_anchor_ = gpos;
            }
            hover_idx_ = -2;
            hover_tip_ = at;
            return;
        }
        // Vừa rời marker vài pixel (tay run, đang đọc): giữ tooltip chú thích, không thay bằng tooltip ngày/giá.
        if (hover_idx_ == -2 && (gpos - tip_anchor_).manhattanLength() <= kAnnotStickyPx)
            return;
    }
    const double xv = chart()->mapToValue(cp, anchor_).x();
    auto it = std::lower_bound(order_.begin(), order_.end(), xv,
                               [this](int idx, double v) { return static_cast<double>(x_[idx]) < v; });
    int pos = static_cast<int>(it - order_.begin());
    if (pos >= order_.size())
        pos = static_cast<int>(order_.size()) - 1;
    if (pos > 0 && (xv - static_cast<double>(x_[order_[pos - 1]])) <= (static_cast<double>(x_[order_[pos]]) - xv))
        --pos;
    const int idx = order_[pos];
    if (idx == hover_idx_)
        return;
    hover_idx_ = idx;

    QString tip = QStringLiteral("<b>%1</b>")
                      .arg(QDateTime::fromMSecsSinceEpoch(x_[idx], QTimeZone::UTC).toString(QStringLiteral("dd/MM/yyyy")));
    int shown = 0;
    for (const Line& l : std::as_const(lines_)) {
        const double y = idx < l.y.size() ? l.y[idx] : lkchart::nan_value();
        if (!std::isfinite(y))
            continue;
        tip += QStringLiteral("<br>%1: %2").arg(l.name.toHtmlEscaped(), lkchart::fmt_vn(y));
        ++shown;
    }
    tip += bands_.tooltip(idx, [](double v) { return lkchart::fmt_vn(v); });
    if (annot_)
        for (const QString& b : annot_->bands_at(static_cast<double>(x_[idx]), cp.y()))
            tip += QStringLiteral("<br><i>%1</i>").arg(b.toHtmlEscaped());
    if (shown == 0)
        tip += QStringLiteral("<br>—");
    QToolTip::showText(gpos, tip, this);
}

void LkLineChart::mousePressEvent(QMouseEvent* event) {
    if (event->button() == Qt::LeftButton && annot_) {
        const QPointF cp = chart()->mapFromScene(mapToScene(event->position().toPoint()));
        const QString at = chart()->plotArea().contains(cp) ? annot_->tip_at(cp) : QString();
        if (!at.isEmpty()) {
            show_pin(at, event->position().toPoint());
            event->accept();
            return;
        }
    }
    hide_pin();
    QChartView::mousePressEvent(event);
}

void LkLineChart::keyPressEvent(QKeyEvent* event) {
    if (event->key() == Qt::Key_Escape && pin_ && pin_->isVisible()) {
        hide_pin();
        event->accept();
        return;
    }
    QChartView::keyPressEvent(event);
}

void LkLineChart::show_pin(const QString& html, const QPoint& view_pos) {
    using namespace ui::colors;
    if (!pin_) {
        pin_ = new QLabel(viewport());
        pin_->setTextFormat(Qt::RichText);
        pin_->setWordWrap(true);
        pin_->setAttribute(Qt::WA_TransparentForMouseEvents); // bấm lên bảng = bấm xuống chart → đóng / ghim mốc khác
    }
    pin_->setStyleSheet(QStringLiteral("QLabel { background:%1; color:%2; border:1px solid %3; border-radius:4px; padding:8px 10px; }")
                            .arg(QColor(BG_RAISED()).name(), QColor(TEXT_PRIMARY()).name(), QColor(BORDER_BRIGHT()).name()));
    pin_->setText(html + QStringLiteral("<br><span style='color:%1'><i>đã ghim · bấm chỗ khác hoặc Esc để đóng</i></span>")
                             .arg(QColor(TEXT_TERTIARY()).name()));
    pin_->setFixedWidth(std::min(kPinMaxW, std::max(220, viewport()->width() / 2)));
    pin_->adjustSize();
    // đặt cạnh điểm bấm, lật trái/lên khi chạm mép để bảng luôn nằm trọn trong chart
    const QSize sz = pin_->size();
    int x = view_pos.x() + 14, y = view_pos.y() + 14;
    if (x + sz.width() > viewport()->width() - 4)
        x = std::max(4, view_pos.x() - 14 - sz.width());
    if (y + sz.height() > viewport()->height() - 4)
        y = std::max(4, view_pos.y() - 14 - sz.height());
    pin_->move(x, y);
    pin_->raise();
    pin_->show();
    QToolTip::hideText();
    if (focusPolicy() == Qt::NoFocus)
        setFocusPolicy(Qt::ClickFocus);
    setFocus(Qt::MouseFocusReason); // để Esc tới được keyPressEvent
}

void LkLineChart::hide_pin() {
    if (pin_)
        pin_->hide();
}

void LkLineChart::resizeEvent(QResizeEvent* event) {
    hide_pin(); // vị trí ghim tính theo khung cũ: đóng thay vì để bảng lơ lửng sai chỗ
    QChartView::resizeEvent(event);
}

void LkLineChart::hideEvent(QHideEvent* event) {
    hide_pin(); // đổi tab / ẩn màn: không để bảng ghim hiện lại khi quay về
    QToolTip::hideText();
    hover_idx_ = -1;
    QChartView::hideEvent(event);
}

void LkLineChart::leaveEvent(QEvent* event) {
    QToolTip::hideText(); // bảng ghim (nếu có) vẫn ở lại tới khi người dùng đóng
    hover_idx_ = -1;
    QChartView::leaveEvent(event);
}

void LkLineChart::wheelEvent(QWheelEvent* event) {
    // Không zoom; để bánh xe cuộn trang ngoài.
    event->ignore();
}

// ═════════════════════════════════════════════════════════════════════════════
// LkScatterChart
// ═════════════════════════════════════════════════════════════════════════════

LkScatterChart::LkScatterChart(const QJsonObject& block, QWidget* parent) : QChartView(new QChart(), parent) {
    using namespace lkchart;
    using namespace ui::colors;
    const bool hoso = block.value(QStringLiteral("_hoso")).toBool(false);
    QChart* ch = chart();
    style_chart(ch, hoso);
    style_view(this, hoso);
    ch->legend()->setVisible(false);

    x_label_ = block.value(QStringLiteral("x_label")).toString();
    y_label_ = block.value(QStringLiteral("y_label")).toString();

    // 1) Điểm (giá trị thật giữ trong pts_ cho tooltip).
    QStringList mau_order;
    QVector<QString> mau_of;
    const QJsonArray arr = block.value(QStringLiteral("points")).toArray();
    for (const auto& v : arr) {
        const QJsonObject o = v.toObject();
        double x = 0.0;
        double y = 0.0;
        if (!finite_num(o.value(QStringLiteral("x")), &x) || !finite_num(o.value(QStringLiteral("y")), &y))
            continue;
        const QString mau = o.value(QStringLiteral("mau")).toString();
        pts_.append({QPointF(x, y), QPointF(x, y), o.value(QStringLiteral("label")).toString().trimmed(), false});
        mau_of.append(mau);
        if (!mau_order.contains(mau))
            mau_order.append(mau);
    }
    if (pts_.isEmpty())
        return;

    // 2) Khung trục luôn chứa gốc 0/0 để thấy 4 ô; vài điểm cực đoan không được ép cụm chính.
    QVector<double> xs;
    QVector<double> ys;
    for (const Pt& p : std::as_const(pts_)) {
        xs.append(p.p.x());
        ys.append(p.p.y());
    }
    const auto axis_range = [](const QVector<double>& v, double* lo, double* hi) {
        if (robust_range(v, lo, hi))
            return;
        *lo = std::min(0.0, *std::min_element(v.begin(), v.end()));
        *hi = std::max(0.0, *std::max_element(v.begin(), v.end()));
    };
    double xmin = 0.0;
    double xmax = 0.0;
    double ymin = 0.0;
    double ymax = 0.0;
    axis_range(xs, &xmin, &xmax);
    axis_range(ys, &ymin, &ymax);
    const double sx = xmax - xmin > 0.0 ? xmax - xmin : 1.0;
    const double sy = ymax - ymin > 0.0 ? ymax - ymin : 1.0;
    xmin -= sx * 0.08;
    xmax += sx * 0.08;
    ymin -= sy * 0.08;
    ymax += sy * 0.08;

    auto* ax = new QValueAxis;
    ax->setTitleText(x_label_);
    ax->setRange(xmin, xmax);
    ax->applyNiceNumbers();
    ax->setLabelFormat(ax->max() - ax->min() >= 20.0 ? QStringLiteral("%.0f") : QStringLiteral("%.1f"));
    style_axis(ax, true, hoso);
    auto* ay = new QValueAxis;
    ay->setTitleText(y_label_);
    ay->setRange(ymin, ymax);
    ay->applyNiceNumbers();
    ay->setLabelFormat(ay->max() - ay->min() >= 20.0 ? QStringLiteral("%.0f") : QStringLiteral("%.1f"));
    style_axis(ay, true, hoso);
    ch->addAxis(ax, Qt::AlignBottom);
    ch->addAxis(ay, Qt::AlignLeft);
    span_x_ = ax->max() - ax->min() > 0.0 ? ax->max() - ax->min() : 1.0;
    span_y_ = ay->max() - ay->min() > 0.0 ? ay->max() - ay->min() : 1.0;

    // Điểm ngoài khung: vẽ ở mép (thụt 1,5%), hình tam giác, luôn có nhãn mã; tooltip giữ số thật.
    int n_out = 0;
    for (Pt& p : pts_) {
        const double cx = std::clamp(p.p.x(), ax->min() + span_x_ * 0.015, ax->max() - span_x_ * 0.015);
        const double cy = std::clamp(p.p.y(), ay->min() + span_y_ * 0.015, ay->max() - span_y_ * 0.015);
        p.out = (cx != p.p.x() && (p.p.x() < ax->min() || p.p.x() > ax->max())) ||
                (cy != p.p.y() && (p.p.y() < ay->min() || p.p.y() > ay->max()));
        if (p.out) {
            p.shown = QPointF(cx, cy);
            ++n_out;
        }
    }

    // Đường 0 ngang/dọc (thêm trước để điểm nằm trên).
    QPen zpen{QColor(BORDER_BRIGHT())};
    zpen.setWidthF(1.0);
    zpen.setCosmetic(true);
    zpen.setStyle(Qt::DashLine);
    auto* hz = new QLineSeries();
    hz->append(ax->min(), 0.0);
    hz->append(ax->max(), 0.0);
    hz->setPen(zpen);
    auto* vz = new QLineSeries();
    vz->append(0.0, ay->min());
    vz->append(0.0, ay->max());
    vz->setPen(zpen);
    for (QLineSeries* z : {hz, vz}) {
        ch->addSeries(z);
        z->attachAxis(ax);
        z->attachAxis(ay);
    }

    // Mỗi (mau, trong/ngoài khung) một QScatterSeries; điểm ngoài khung vẽ sau (nằm trên).
    QVector<std::pair<QString, bool>> groups;
    for (const bool outside : {false, true})
        for (const QString& mau : std::as_const(mau_order))
            groups.append({mau, outside});
    for (const auto& [mau, outside] : std::as_const(groups)) {
        QVector<QPointF> pts;
        for (int i = 0; i < pts_.size(); ++i)
            if (mau_of[i] == mau && pts_[i].out == outside)
                pts.append(pts_[i].shown);
        if (pts.isEmpty())
            continue;
        auto* s = new QScatterSeries();
        s->setName(mau.isEmpty() ? QStringLiteral("—") : mau);
        s->setMarkerShape(outside ? QScatterSeries::MarkerShapeTriangle : QScatterSeries::MarkerShapeCircle);
        s->setMarkerSize(outside ? 11.0 : 9.0);
        const QColor c = mau.isEmpty() ? QColor(TEXT_SECONDARY()) : lk_color(mau);
        s->setColor(c);
        s->setBorderColor(QColor(BG_SURFACE()));
        s->append(pts);
        ch->addSeries(s);
        s->attachAxis(ax);
        s->attachAxis(ay);
        if (!anchor_)
            anchor_ = s;
        connect(s, &QXYSeries::hovered, this, [this](const QPointF& p, bool state) {
            if (!state) {
                QToolTip::hideText();
                unsetCursor();
                return;
            }
            const int i = nearest(p);
            if (i < 0)
                return;
            setCursor(pts_[i].label.isEmpty() ? Qt::ArrowCursor : Qt::PointingHandCursor);
            QToolTip::showText(QCursor::pos(), tooltip_for(i), this);
        });
        connect(s, &QXYSeries::clicked, this, [this](const QPointF& p) {
            const int i = nearest(p);
            if (i >= 0 && !pts_[i].label.isEmpty())
                emit ticker_activated(pts_[i].label);
        });
    }

    // 3) Nhãn 4 góc + nhãn mã.
    const QJsonObject q = block.value(QStringLiteral("quadrants")).toObject();
    const char* keys[4] = {"tl", "tr", "bl", "br"};
    for (int k = 0; k < 4; ++k) {
        const QString t = q.value(QLatin1String(keys[k])).toString().trimmed();
        if (t.isEmpty())
            continue;
        auto* item = new QGraphicsSimpleTextItem(t, ch);
        item->setFont(px_font(10, true));
        // tl = giá ↑ · FFT ↓ (bo cung) tô xanh; br = giá ↓ · FFT ↑ (xả hàng) tô đỏ — như artifact gốc.
        const QColor qc = k == 0 ? QColor(POSITIVE()) : (k == 3 ? QColor(NEGATIVE()) : QColor(TEXT_TERTIARY()));
        item->setBrush(qc);
        item->setZValue(10);
        quad_[k] = item;
    }
    // Nhãn mã: mọi điểm khi ít điểm; nhiều điểm thì chỉ điểm ngoài khung (còn lại xem tooltip).
    const bool label_all = pts_.size() <= kMaxPointLabels;
    labels_.fill(nullptr, pts_.size());
    for (int i = 0; i < pts_.size(); ++i) {
        if (!label_all && !pts_[i].out)
            continue;
        const Pt& p = pts_[i];
        auto* item = new QGraphicsSimpleTextItem(p.out ? p.label + QStringLiteral(" ") + fmt_pair(p.p) : p.label, ch);
        item->setFont(px_font(9));
        item->setBrush(QColor(p.out ? TEXT_PRIMARY() : TEXT_SECONDARY()));
        item->setZValue(11);
        labels_[i] = item;
    }
    if (n_out > 0) {
        outlier_note_ = new QGraphicsSimpleTextItem(
            tr("▲ %1 điểm ngoài khung — vẽ ở mép, số thật trong nhãn/tooltip").arg(n_out), ch);
        outlier_note_->setFont(px_font(9));
        outlier_note_->setBrush(QColor(TEXT_TERTIARY()));
        outlier_note_->setZValue(10);
    }
    connect(ch, &QChart::plotAreaChanged, this, [this](const QRectF&) { layout_overlays(); });
    layout_overlays();
}

int LkScatterChart::nearest(const QPointF& value) const {
    int best = -1;
    double best_d = std::numeric_limits<double>::infinity();
    for (int i = 0; i < pts_.size(); ++i) {
        const double dx = (pts_[i].shown.x() - value.x()) / span_x_;
        const double dy = (pts_[i].shown.y() - value.y()) / span_y_;
        const double d = dx * dx + dy * dy;
        if (d < best_d) {
            best_d = d;
            best = i;
        }
    }
    return best;
}

QString LkScatterChart::tooltip_for(int i) const {
    const Pt& p = pts_[i];
    QString t = QStringLiteral("<b>%1</b>").arg(p.label.isEmpty() ? QStringLiteral("—") : p.label.toHtmlEscaped());
    t += QStringLiteral("<br>%1: %2").arg(x_label_.isEmpty() ? QStringLiteral("x") : x_label_.toHtmlEscaped(),
                                           lkchart::fmt_vn(p.p.x()));
    t += QStringLiteral("<br>%1: %2").arg(y_label_.isEmpty() ? QStringLiteral("y") : y_label_.toHtmlEscaped(),
                                           lkchart::fmt_vn(p.p.y()));
    if (p.out)
        t += QStringLiteral("<br><i>%1</i>").arg(tr("ngoài khung — vẽ ở mép"));
    if (!p.label.isEmpty())
        t += QStringLiteral("<br><i>%1</i>").arg(tr("Bấm để mở chuỗi FFT × Giá"));
    return t;
}

void LkScatterChart::layout_overlays() {
    QChart* ch = chart();
    if (!ch)
        return;
    const QRectF pa = ch->plotArea();
    if (pa.width() <= 0.0 || pa.height() <= 0.0)
        return;
    const qreal m = 6.0;
    if (quad_[0])
        quad_[0]->setPos(pa.left() + m, pa.top() + 4.0);
    if (quad_[1])
        quad_[1]->setPos(pa.right() - quad_[1]->boundingRect().width() - m, pa.top() + 4.0);
    if (quad_[2])
        quad_[2]->setPos(pa.left() + m, pa.bottom() - quad_[2]->boundingRect().height() - 4.0);
    if (quad_[3])
        quad_[3]->setPos(pa.right() - quad_[3]->boundingRect().width() - m,
                         pa.bottom() - quad_[3]->boundingRect().height() - 4.0);
    if (outlier_note_)
        outlier_note_->setPos(pa.center().x() - outlier_note_->boundingRect().width() / 2.0,
                              pa.bottom() - outlier_note_->boundingRect().height() - 4.0);
    if (!anchor_)
        return;
    for (int i = 0; i < labels_.size() && i < pts_.size(); ++i) {
        QGraphicsSimpleTextItem* item = labels_[i];
        if (!item)
            continue;
        const QPointF pos = ch->mapToPosition(pts_[i].shown, anchor_);
        // Nhãn ở mép phải/trên được lật vào trong để không tràn khỏi vùng vẽ.
        const QRectF br = item->boundingRect();
        const double lx = pos.x() + 5.0 + br.width() > pa.right() ? pos.x() - 5.0 - br.width() : pos.x() + 5.0;
        const double ly = pos.y() - 14.0 < pa.top() ? pos.y() + 4.0 : pos.y() - 14.0;
        item->setPos(lx, ly);
        item->setVisible(pa.contains(pos));
    }
}

void LkScatterChart::wheelEvent(QWheelEvent* event) {
    event->ignore();
}

} // namespace fincept::screens::langkinh
