// src/screens/langkinh/LkChartLayers.cpp
// Lăng Kính FFT — dải màu (band) và chú thích (annotations) cho LkLineChart — xem LkChartLayers.h.
#include "screens/langkinh/LkChartLayers.h"

#include "screens/langkinh/LkBlockView.h"
#include "ui/theme/Theme.h"

#include <QAreaSeries>
#include <QBrush>
#include <QChart>
#include <QFont>
#include <QFontMetricsF>
#include <QGraphicsItem>
#include <QGraphicsLineItem>
#include <QGraphicsPathItem>
#include <QGraphicsRectItem>
#include <QLegend>
#include <QLegendMarker>
#include <QLineF>
#include <QLineSeries>
#include <QPainter>
#include <QPainterPath>
#include <QPen>
#include <QValueAxis>

#include <algorithm>
#include <cmath>
#include <limits>

namespace fincept::screens::langkinh {

// Helper tự do: namespace có tên riêng, không đụng tên tệp khác (SKIP_UNITY vẫn giữ quy ước).
namespace lkannot {

constexpr qint64 kDayMs = 24LL * 60 * 60 * 1000;
// V4.5 — chữ chú thích nhỏ hơn: nhãn chính 11 → 10px (vline 10, xband/hband 9), dòng phụ 9 → 8px,
// đệm hộp nhãn −20% (5/2 → 4/1,6), marker 11 → 10px (hình vẽ nhân 10/11).
constexpr int kPointPx = 10;
constexpr int kVLinePx = 10;
constexpr int kBandPx = 9;
constexpr int kSubPx = 8;
constexpr double kPadX = 4.0;
constexpr double kPadY = 1.6;
constexpr double kMk = 10.0 / 11.0;
constexpr int kMaxNotch = 3;      // V3.3 — lệch dọc tối đa 3 nấc rồi mới ẩn nhãn
constexpr int kLongTip = 90;      // tooltip dài hơn → xuống dòng ở " · "
constexpr double kZBand = 2.5;    // trên lưới (2), dưới trục (3) và series (4) của QtCharts
constexpr double kZVLine = 2.6;
constexpr double kZMarker = 12.0; // trên series + legend
constexpr double kZLead = 12.5;
constexpr double kZLabel = 13.0;

double nan_value() {
    return std::numeric_limits<double>::quiet_NaN();
}

bool finite_num(const QJsonValue& v, double* out) {
    if (!v.isDouble() || !std::isfinite(v.toDouble()))
        return false;
    *out = v.toDouble();
    return true;
}

QColor with_alpha(QColor c, double a) {
    c.setAlphaF(std::clamp(a, 0.0, 1.0));
    return c;
}

/// Hộp nhãn: nền tối bán trong suốt bo góc, dòng chính đậm + dòng `sub` nhỏ màu phụ.
class Label : public QGraphicsItem {
  public:
    Label(const QString& text, const QString& sub, const QColor& fg, const QColor& edge, int px, QGraphicsItem* parent)
        : QGraphicsItem(parent), text_(text), sub_(sub), fg_(fg), edge_(edge) {
        f1_.setPixelSize(px);
        f1_.setBold(true);
        f2_.setPixelSize(kSubPx);
        const QFontMetricsF m1(f1_);
        const QFontMetricsF m2(f2_);
        h1_ = text_.isEmpty() ? 0.0 : m1.height();
        h2_ = sub_.isEmpty() ? 0.0 : m2.height();
        a1_ = m1.ascent();
        a2_ = m2.ascent();
        const double w = std::max(text_.isEmpty() ? 0.0 : m1.horizontalAdvance(text_),
                                  sub_.isEmpty() ? 0.0 : m2.horizontalAdvance(sub_));
        size_ = QSizeF(std::ceil(w) + 2.0 * kPadX, std::ceil(h1_ + h2_) + 2.0 * kPadY);
        bg_ = with_alpha(QColor(ui::colors::BG_BASE()), 0.88);
        sub_color_ = QColor(ui::colors::TEXT_SECONDARY());
        setZValue(kZLabel);
    }
    QRectF boundingRect() const override { return QRectF(QPointF(0.0, 0.0), size_); }
    void paint(QPainter* p, const QStyleOptionGraphicsItem*, QWidget*) override {
        p->setRenderHint(QPainter::Antialiasing, true);
        p->setPen(QPen(edge_, 1.0));
        p->setBrush(bg_);
        p->drawRoundedRect(boundingRect().adjusted(0.5, 0.5, -0.5, -0.5), 3.0, 3.0);
        double y = kPadY;
        if (!text_.isEmpty()) {
            p->setFont(f1_);
            p->setPen(fg_);
            p->drawText(QPointF(kPadX, y + a1_), text_);
            y += h1_;
        }
        if (!sub_.isEmpty()) {
            p->setFont(f2_);
            p->setPen(sub_color_);
            p->drawText(QPointF(kPadX, y + a2_), sub_);
        }
    }

  private:
    QString text_;
    QString sub_;
    QColor fg_;
    QColor edge_;
    QColor bg_;
    QColor sub_color_;
    QFont f1_;
    QFont f2_;
    double h1_ = 0.0;
    double h2_ = 0.0;
    double a1_ = 0.0;
    double a2_ = 0.0;
    QSizeF size_;
};

QPainterPath marker_path(const QString& m) {
    QPainterPath p;
    if (m == QLatin1String("tri_up") || m == QLatin1String("tri_down")) {
        const double s = m == QLatin1String("tri_up") ? 1.0 : -1.0;
        p.moveTo(0.0, -6.5 * kMk * s);
        p.lineTo(6.5 * kMk, 5.0 * kMk * s);
        p.lineTo(-6.5 * kMk, 5.0 * kMk * s);
        p.closeSubpath();
    } else if (m == QLatin1String("diamond")) {
        const double d = 7.5 * kMk;
        p.moveTo(0.0, -d);
        p.lineTo(d, 0.0);
        p.lineTo(0.0, d);
        p.lineTo(-d, 0.0);
        p.closeSubpath();
    } else {
        p.addEllipse(QPointF(0.0, 0.0), 4.2 * kMk, 4.2 * kMk);
    }
    return p;
}

QRectF clamp_in(QRectF r, const QRectF& pa) {
    constexpr double m = 2.0;
    if (r.right() > pa.right() - m)
        r.moveRight(pa.right() - m);
    if (r.left() < pa.left() + m)
        r.moveLeft(pa.left() + m);
    if (r.bottom() > pa.bottom() - m)
        r.moveBottom(pa.bottom() - m);
    if (r.top() < pa.top() + m)
        r.moveTop(pa.top() + m);
    return r;
}

/// Đoạn s chạm/cắt hộp r?
bool seg_hits(const QLineF& s, const QRectF& r) {
    if (r.contains(s.p1()) || r.contains(s.p2()))
        return true;
    const QLineF edges[4] = {QLineF(r.topLeft(), r.topRight()), QLineF(r.topRight(), r.bottomRight()),
                             QLineF(r.bottomRight(), r.bottomLeft()), QLineF(r.bottomLeft(), r.topLeft())};
    return std::any_of(std::begin(edges), std::end(edges),
                       [&](const QLineF& e) { return s.intersects(e, nullptr) == QLineF::BoundedIntersection; });
}

/// Khoảng cách từ điểm p tới hộp r (0 nếu p nằm trong hộp).
double rect_dist(const QPointF& p, const QRectF& r) {
    const double dx = std::max({r.left() - p.x(), 0.0, p.x() - r.right()});
    const double dy = std::max({r.top() - p.y(), 0.0, p.y() - r.bottom()});
    return std::hypot(dx, dy);
}

QString tip_html(const QString& text, const QString& sub, const QString& tip) {
    QString t = QStringLiteral("<b>%1</b>").arg(text.toHtmlEscaped());
    if (!sub.isEmpty())
        t += QStringLiteral(" · ") + sub.toHtmlEscaped();
    if (!tip.isEmpty()) {
        QString body = tip.toHtmlEscaped();
        body.replace(QStringLiteral(" | "), QStringLiteral("<br>"));
        if (tip.size() > kLongTip)
            body.replace(QStringLiteral(" · "), QStringLiteral("<br>"));
        t += QStringLiteral("<br>") + body;
    }
    return t;
}

} // namespace lkannot

// ═════════════════════════════════════════════════════════════════════════════
// LkBandSet
// ═════════════════════════════════════════════════════════════════════════════

void LkBandSet::add(QChart* chart, const QJsonObject& so, const QVector<qint64>& x, const QVector<int>& order,
                    const QColor& color, const QString& name, bool right, const std::function<void(double)>& grow) {
    using namespace lkannot;
    x_ = x;
    Band b;
    b.name = name;
    b.color = color;
    b.right = right;
    b.lo_min = so.value(QStringLiteral("lo_min")).toBool(false);
    b.hi_max = so.value(QStringLiteral("hi_max")).toBool(false);
    double a = 0.0;
    if (finite_num(so.value(QStringLiteral("alpha")), &a) && a > 0.0 && a <= 1.0)
        b.alpha = a;
    const int n = static_cast<int>(x.size());
    const auto read = [&](const char* key, QVector<double>& out) {
        out.fill(nan_value(), n);
        const QJsonArray arr = so.value(QLatin1String(key)).toArray();
        const int m = std::min(n, static_cast<int>(arr.size()));
        for (int i = 0; i < m; ++i) {
            double d = 0.0;
            if (finite_num(arr.at(i), &d))
                out[i] = d;
        }
    };
    read("y_lo", b.lo);
    read("y_hi", b.hi);
    // null ở mảng đang dùng → đứt dải; lo > hi (dữ liệu hỏng) cũng không tô.
    const auto ok = [&](int i) {
        const bool lo = b.lo_min || std::isfinite(b.lo[i]);
        const bool hi = b.hi_max || std::isfinite(b.hi[i]);
        return lo && hi && (b.lo_min || b.hi_max || b.lo[i] <= b.hi[i]);
    };
    QVector<int> seg;
    for (int idx : order) {
        if (ok(idx)) {
            seg.append(idx);
        } else if (!seg.isEmpty()) {
            b.seg_idx.append(seg);
            seg.clear();
        }
    }
    if (!seg.isEmpty())
        b.seg_idx.append(seg);
    for (const QVector<int>& s : std::as_const(b.seg_idx)) {
        for (int idx : s) {
            if (!b.lo_min)
                grow(b.lo[idx]);
            if (!b.hi_max)
                grow(b.hi[idx]);
        }
        auto* area = new QAreaSeries(chart);
        area->setUpperSeries(new QLineSeries(area));
        area->setLowerSeries(new QLineSeries(area));
        area->setName(name);
        area->setPen(Qt::NoPen); // viền trong suốt — không vẽ nét đè lên line
        area->setBrush(with_alpha(color, b.alpha));
        chart->addSeries(area);
        b.segs.append(area);
    }
    if (!b.segs.isEmpty())
        bands_.append(b);
}

void LkBandSet::finish(QChart* chart, QAbstractAxis* ax, QValueAxis* left, QValueAxis* right) {
    using namespace lkannot;
    for (const Band& b : std::as_const(bands_)) {
        QValueAxis* ay = b.right && right ? right : left;
        if (!ay)
            continue;
        const auto val = [&](int i, bool upper) {
            return upper ? (b.hi_max ? ay->max() : b.hi[i]) : (b.lo_min ? ay->min() : b.lo[i]);
        };
        for (int s = 0; s < b.segs.size(); ++s) {
            const QVector<int>& idx = b.seg_idx[s];
            QList<QPointF> up;
            QList<QPointF> dn;
            if (idx.size() == 1) { // một tuần lẻ loi: nới ±3,5 ngày để còn thấy
                const double xc = static_cast<double>(x_[idx.first()]);
                for (const double dx : {-3.5 * kDayMs, 3.5 * kDayMs}) {
                    up.append(QPointF(xc + dx, val(idx.first(), true)));
                    dn.append(QPointF(xc + dx, val(idx.first(), false)));
                }
            } else {
                for (int i : idx) {
                    up.append(QPointF(static_cast<double>(x_[i]), val(i, true)));
                    dn.append(QPointF(static_cast<double>(x_[i]), val(i, false)));
                }
            }
            b.segs[s]->upperSeries()->replace(up);
            b.segs[s]->lowerSeries()->replace(dn);
            b.segs[s]->attachAxis(ax);
            b.segs[s]->attachAxis(ay);
            const QList<QLegendMarker*> ms = chart->legend()->markers(b.segs[s]);
            for (QLegendMarker* m : ms) {
                if (s > 0) {
                    m->setVisible(false); // chỉ đoạn đầu có mục chú giải
                } else {
                    m->setBrush(with_alpha(b.color, std::max(0.5, b.alpha * 3.0))); // ô legend đậm hơn vùng tô
                    m->setPen(QPen(b.color, 1.0));
                }
            }
        }
    }
}

QString LkBandSet::tooltip(int idx, const std::function<QString(double)>& fmt) const {
    QString out;
    for (const Band& b : std::as_const(bands_)) {
        if (idx < 0 || idx >= b.lo.size())
            continue;
        const double lo = b.lo[idx];
        const double hi = b.hi[idx];
        QString v;
        if (b.lo_min && !b.hi_max && std::isfinite(hi))
            v = QStringLiteral("≤ ") + fmt(hi);
        else if (b.hi_max && !b.lo_min && std::isfinite(lo))
            v = QStringLiteral("≥ ") + fmt(lo);
        else if (!b.lo_min && !b.hi_max && std::isfinite(lo) && std::isfinite(hi))
            v = fmt(lo) + QStringLiteral(" – ") + fmt(hi);
        if (!v.isEmpty())
            out += QStringLiteral("<br><span style='color:%1'>■</span> %2: %3")
                       .arg(b.color.name(), b.name.toHtmlEscaped(), v);
    }
    return out;
}

// ═════════════════════════════════════════════════════════════════════════════
// LkChartAnnot
// ═════════════════════════════════════════════════════════════════════════════

LkChartAnnot::LkChartAnnot(QChart* chart, const QJsonArray& items, QAbstractSeries* left, QAbstractSeries* right,
                           QObject* parent)
    : QObject(parent), chart_(chart), left_(left), right_(right) {
    using namespace lkannot;
    using namespace ui::colors;
    for (const auto& v : items) {
        const QJsonObject o = v.toObject();
        const QString kind = o.value(QStringLiteral("kind")).toString();
        const QString mau = o.value(QStringLiteral("mau")).toString();
        Ann a;
        a.text = o.value(QStringLiteral("text")).toString().trimmed();
        a.sub = o.value(QStringLiteral("sub")).toString().trimmed();
        a.tip = o.value(QStringLiteral("tip")).toString().trimmed();
        a.color = lk_color(mau);
        a.prio = std::clamp(o.value(QStringLiteral("uu_tien")).toInt(2), 1, 3);
        int label_px = kPointPx;
        if (kind == QLatin1String("point")) {
            a.kind = Kind::Point;
            a.right = o.value(QStringLiteral("axis")).toString() == QLatin1String("right");
            if (!finite_num(o.value(QStringLiteral("x")), &a.x) || !finite_num(o.value(QStringLiteral("y")), &a.y) ||
                (a.right && !right_))
                continue;
            a.marker = o.value(QStringLiteral("marker")).toString(QStringLiteral("dot"));
            a.pos = o.value(QStringLiteral("pos")).toString(QStringLiteral("above"));
            if (a.marker != QLatin1String("none")) {
                a.mk = new QGraphicsPathItem(marker_path(a.marker), chart_);
                a.mk->setBrush(a.color);
                a.mk->setPen(QPen(QColor(BG_BASE()), 1.6)); // viền tối (nền) để nổi trên line
                // Trùng chỗ (vd "Rời vùng" đúng tuần hiện tại): marker ưu tiên cao nằm trên chấm ưu tiên 3.
                a.mk->setZValue(kZMarker + 0.1 * (3 - a.prio));
            }
        } else if (kind == QLatin1String("vline")) {
            a.kind = Kind::VLine;
            if (!finite_num(o.value(QStringLiteral("x")), &a.x))
                continue;
            QPen pen(with_alpha(a.color, 0.6), 1.2);
            pen.setCosmetic(true);
            pen.setStyle(o.value(QStringLiteral("style")).toString() == QLatin1String("dot") ? Qt::DotLine
                                                                                             : Qt::DashLine);
            a.vl = new QGraphicsLineItem(chart_);
            a.vl->setPen(pen);
            a.vl->setZValue(kZVLine);
            label_px = kVLinePx;
        } else if (kind == QLatin1String("xband")) {
            a.kind = Kind::XBand;
            if (!finite_num(o.value(QStringLiteral("x0")), &a.x) || !finite_num(o.value(QStringLiteral("x1")), &a.x1))
                continue;
            if (a.x1 < a.x)
                std::swap(a.x, a.x1);
            double alpha = 0.07;
            finite_num(o.value(QStringLiteral("alpha")), &alpha);
            a.band = new QGraphicsRectItem(chart_);
            a.band->setPen(Qt::NoPen);
            a.band->setBrush(with_alpha(a.color, alpha));
            a.band->setZValue(kZBand);
            label_px = kBandPx;
        } else if (kind == QLatin1String("hband")) {
            // V4.3 — dải ngang y0–y1 trên trục chỉ định (vd vùng gom ước tính trên trục giá), dưới mọi series.
            a.kind = Kind::HBand;
            a.right = o.value(QStringLiteral("axis")).toString() == QLatin1String("right");
            if (!finite_num(o.value(QStringLiteral("y0")), &a.y) || !finite_num(o.value(QStringLiteral("y1")), &a.y1) ||
                (a.right && !right_))
                continue;
            if (a.y1 < a.y)
                std::swap(a.y, a.y1);
            double alpha = 0.14;
            if (!finite_num(o.value(QStringLiteral("alpha")), &alpha) || alpha <= 0.0 || alpha > 1.0)
                alpha = 0.14;
            a.band = new QGraphicsRectItem(chart_);
            a.band->setPen(Qt::NoPen);
            a.band->setBrush(with_alpha(a.color, alpha));
            a.band->setZValue(kZBand);
            QPen ep(with_alpha(a.color, std::min(1.0, alpha * 3.0 + 0.2)), 1.0, Qt::DashLine);
            ep.setCosmetic(true);
            a.edge = new QGraphicsPathItem(chart_);
            a.edge->setPen(ep);
            a.edge->setZValue(kZBand);
            label_px = kBandPx;
        } else if (kind == QLatin1String("box")) {
            // Hộp của engine: chữ nhật x0–x1 × y0–y1, viền đứt + nền rất nhạt, nhãn trong hộp (góc trên trái).
            a.kind = Kind::Box;
            a.right = o.value(QStringLiteral("axis")).toString() == QLatin1String("right");
            if (!finite_num(o.value(QStringLiteral("x0")), &a.x) || !finite_num(o.value(QStringLiteral("x1")), &a.x1) ||
                !finite_num(o.value(QStringLiteral("y0")), &a.y) || !finite_num(o.value(QStringLiteral("y1")), &a.y1) ||
                (a.right && !right_))
                continue;
            if (a.x1 < a.x)
                std::swap(a.x, a.x1);
            if (a.y1 < a.y)
                std::swap(a.y, a.y1);
            double alpha = 0.06;
            if (!finite_num(o.value(QStringLiteral("alpha")), &alpha) || alpha < 0.0 || alpha > 1.0)
                alpha = 0.06;
            QPen bp(with_alpha(a.color, 0.8), 1.0, Qt::DashLine);
            bp.setCosmetic(true);
            a.band = new QGraphicsRectItem(chart_);
            a.band->setPen(bp);
            a.band->setBrush(with_alpha(a.color, alpha));
            a.band->setZValue(kZBand);
            label_px = kBandPx;
        } else {
            continue;
        }
        // uu_tien 3 = chỉ marker/vạch, chữ nằm trong tooltip.
        if ((!a.text.isEmpty() || !a.sub.isEmpty()) && a.prio < 3) {
            const bool neutral = mau.isEmpty() || mau == QLatin1String("dim");
            a.label = new Label(a.text, a.sub, neutral ? QColor(TEXT_PRIMARY()) : a.color,
                                with_alpha(neutral ? QColor(BORDER_BRIGHT()) : a.color, 0.7), label_px, chart_);
            a.label->setVisible(false);
            if (a.kind == Kind::Point) {
                QPen bp(with_alpha(QColor(BG_BASE()), 0.85), 3.0);
                bp.setCosmetic(true);
                bp.setCapStyle(Qt::RoundCap);
                a.lead_bg = new QGraphicsLineItem(chart_);
                a.lead_bg->setPen(bp);
                a.lead_bg->setZValue(kZLead - 0.1);
                a.lead_bg->setVisible(false);
                QPen lp(with_alpha(a.color, 0.9), 1.0);
                lp.setCosmetic(true);
                a.lead = new QGraphicsLineItem(chart_);
                a.lead->setPen(lp);
                a.lead->setZValue(kZLead);
                a.lead->setVisible(false);
            }
        }
        anns_.append(a);
    }
}

void LkChartAnnot::grow(const QJsonArray& items, const std::function<void(double, bool)>& add) {
    for (const auto& v : items) {
        const QJsonObject o = v.toObject();
        double y0 = 0.0;
        double y1 = 0.0;
        const QString kind = o.value(QStringLiteral("kind")).toString();
        if ((kind != QLatin1String("hband") && kind != QLatin1String("box")) ||
            !lkannot::finite_num(o.value(QStringLiteral("y0")), &y0) ||
            !lkannot::finite_num(o.value(QStringLiteral("y1")), &y1))
            continue;
        const bool right = o.value(QStringLiteral("axis")).toString() == QLatin1String("right");
        add(y0, right);
        add(y1, right);
    }
}

QPointF LkChartAnnot::to_pos(double x, double y, bool right) const {
    return chart_->mapToPosition(QPointF(x, y), right && right_ ? right_ : left_);
}

QVector<QPointF> LkChartAnnot::candidates(const Ann& a, const QSizeF& sz, const QRectF& pa) const {
    QVector<QPointF> out;
    const double w = sz.width();
    const double h = sz.height();
    if (a.kind == Kind::Box) { // trong hộp (trên trái, dưới trái) khi vừa, rồi ngay trên / dưới hộp, canh mép trái
        if (a.hit.width() >= w + 6.0 && a.hit.height() >= h + 4.0) {
            out.append(QPointF(a.hit.left() + 3.0, a.hit.top() + 2.0));
            out.append(QPointF(a.hit.left() + 3.0, a.hit.bottom() - 2.0 - h));
        }
        out.append(QPointF(a.hit.left(), a.hit.top() - 2.0 - h));
        out.append(QPointF(a.hit.left(), a.hit.bottom() + 2.0));
        out.append(QPointF(a.hit.right() - w, a.hit.top() - 2.0 - h));
        out.append(QPointF(a.hit.right() - w, a.hit.bottom() + 2.0));
        return out;
    }
    if (a.kind == Kind::HBand) { // sát mép trái: trong dải (trên, giữa, dưới), rồi ngay trên/dưới dải
        const double x = pa.left() + 4.0;
        if (a.hit.height() >= h + 4.0) {
            out.append(QPointF(x, a.hit.top() + 2.0));
            out.append(QPointF(x, a.hit.bottom() - 2.0 - h));
        }
        out.append(QPointF(x, a.hit.center().y() - h / 2.0));
        out.append(QPointF(x, a.hit.top() - 2.0 - h));
        out.append(QPointF(x, a.hit.bottom() + 2.0));
        return out;
    }
    if (a.kind != Kind::Point) { // vline/xband: sát mép trên, so le tối đa 3 hàng
        for (int row = 0; row < lkannot::kMaxNotch; ++row) {
            const double y = pa.top() + 2.0 + row * (h + 2.0);
            if (a.kind == Kind::VLine) {
                out.append(QPointF(a.at.x() + 3.0, y));
                out.append(QPointF(a.at.x() - 3.0 - w, y));
            } else {
                out.append(QPointF(a.hit.left() + 3.0, y));
            }
        }
        return out;
    }
    // Point: bốn hướng (trên/dưới lệch dọc xa dần; trái/phải lệch lên/xuống), mỗi ứng viên đã kẹp vào plot area.
    // Xếp theo khoảng cách hộp nhãn ↔ marker (+ phạt nhẹ khi khác hướng `pos`): nhãn luôn vào chỗ trống GẦN
    // marker nhất; ứng viên xa hơn 3 nấc (thường do bị kẹp ở mép) bị bỏ → nhãn ẩn thay vì trôi xa marker.
    enum Dir { Above, Below, Left, Right };
    const double r = a.mk ? a.mk->boundingRect().width() / 2.0 : 3.0;
    const double gap = r + 4.0;
    const double step = h + 3.0;
    const double px = a.at.x();
    const double py = a.at.y();
    const QPointF base[4] = {QPointF(px - w / 2.0, py - gap - h), QPointF(px - w / 2.0, py + gap),
                             QPointF(px - gap - w, py - h / 2.0), QPointF(px + gap, py - h / 2.0)};
    const Dir pref = a.pos == QLatin1String("below")   ? Below
                     : a.pos == QLatin1String("left")  ? Left
                     : a.pos == QLatin1String("right") ? Right
                                                        : Above;
    const Dir opp = pref == Above ? Below : (pref == Below ? Above : (pref == Left ? Right : Left));
    const double max_dist = gap + lkannot::kMaxNotch * step + 1.0;
    struct Cand {
        QPointF p;
        double cost;
    };
    QVector<Cand> cs;
    const auto add = [&](Dir d, double dy) {
        const QRectF rr = lkannot::clamp_in(QRectF(base[d] + QPointF(0.0, dy), sz), pa);
        const double dist = lkannot::rect_dist(a.at, rr);
        if (dist <= max_dist)
            cs.append({rr.topLeft(), dist + (d == pref ? 0.0 : (d == opp ? 2.0 : 4.0))});
    };
    for (const Dir d : {Above, Below, Left, Right}) {
        for (int k = 0; k <= lkannot::kMaxNotch; ++k) {
            if (d == Above || d == Below) {
                add(d, (d == Above ? -1.0 : 1.0) * k * step);
            } else {
                add(d, -k * step);
                if (k > 0)
                    add(d, k * step);
            }
        }
    }
    std::stable_sort(cs.begin(), cs.end(), [](const Cand& l, const Cand& rr) { return l.cost < rr.cost; });
    for (const Cand& c : std::as_const(cs))
        out.append(c.p);
    return out;
}

void LkChartAnnot::relayout() {
    using namespace lkannot;
    if (!chart_ || !left_)
        return;
    const QRectF pa = chart_->plotArea();
    if (pa.width() <= 1.0 || pa.height() <= 1.0)
        return;
    QVector<QRectF> taken;  // marker + nhãn đã đặt: nhãn sau không được đè lên
    QVector<QRectF> labels; // chỉ nhãn — nét nối của nhãn sau không được chạy qua
    QVector<QLineF> leads;  // nét nối đã vẽ — nhãn sau không được che
    for (Ann& a : anns_) {
        if (a.kind == Kind::XBand) {
            double p0 = to_pos(a.x, 0.0, false).x();
            double p1 = to_pos(a.x1, 0.0, false).x();
            p0 = std::max(p0, pa.left());
            p1 = std::min(p1, pa.right());
            a.on = p1 - p0 >= 1.0;
            a.hit = QRectF(p0, pa.top(), std::max(0.0, p1 - p0), pa.height());
            a.band->setRect(a.hit);
            a.band->setVisible(a.on);
        } else if (a.kind == Kind::HBand) {
            const double q0 = to_pos(0.0, a.y, a.right).y();
            const double q1 = to_pos(0.0, a.y1, a.right).y();
            double top = std::min(q0, q1);
            double bot = std::max(q0, q1);
            if (bot - top < 2.0) { // một mức giá (y0 = y1): vẫn thấy một vạch 2px
                const double c = (top + bot) / 2.0;
                top = c - 1.0;
                bot = c + 1.0;
            }
            a.on = bot >= pa.top() && top <= pa.bottom();
            QPainterPath ep;
            for (const double ey : {top, bot})
                if (ey >= pa.top() && ey <= pa.bottom()) {
                    ep.moveTo(pa.left(), ey);
                    ep.lineTo(pa.right(), ey);
                }
            top = std::max(top, pa.top());
            bot = std::min(bot, pa.bottom());
            a.hit = QRectF(pa.left(), top, pa.width(), std::max(0.0, bot - top));
            a.band->setRect(a.hit);
            a.band->setVisible(a.on);
            a.edge->setPath(ep);
            a.edge->setVisible(a.on);
        } else if (a.kind == Kind::Box) {
            const QRectF br = QRectF(to_pos(a.x, a.y1, a.right), to_pos(a.x1, a.y, a.right)).normalized();
            const QRectF cl = br.intersected(pa);
            a.on = cl.width() >= 1.0 && cl.height() >= 1.0;
            a.hit = a.on ? cl : QRectF();
            a.band->setRect(a.hit);
            a.band->setVisible(a.on);
        } else if (a.kind == Kind::VLine) {
            const double px = to_pos(a.x, 0.0, false).x();
            a.on = px >= pa.left() - 0.5 && px <= pa.right() + 0.5;
            a.at = QPointF(px, pa.top());
            a.hit = QRectF(px - 3.0, pa.top(), 6.0, pa.height());
            a.vl->setLine(px, pa.top(), px, pa.bottom());
            a.vl->setVisible(a.on);
        } else {
            a.at = to_pos(a.x, a.y, a.right);
            a.on = pa.adjusted(-1.0, -1.0, 1.0, 1.0).contains(a.at);
            const double r = a.mk ? a.mk->boundingRect().width() / 2.0 : 3.0;
            a.hit = QRectF(a.at.x() - r, a.at.y() - r, 2.0 * r, 2.0 * r);
            if (a.mk) {
                a.mk->setPos(a.at);
                a.mk->setVisible(a.on);
                if (a.on)
                    taken.append(a.hit);
            }
        }
    }
    // Nhãn theo uu_tien (1 trước); cùng mức: xband, vline (chỗ đặt cố định ở mép trên) rồi mới tới point.
    QVector<int> order;
    for (int i = 0; i < anns_.size(); ++i)
        if (anns_[i].label)
            order.append(i);
    const auto rank = [](Kind k) {
        return k == Kind::XBand || k == Kind::HBand || k == Kind::Box ? 0 : (k == Kind::VLine ? 1 : 2);
    };
    std::stable_sort(order.begin(), order.end(), [&](int l, int r) {
        const Ann& a = anns_[l];
        const Ann& b = anns_[r];
        return a.prio != b.prio ? a.prio < b.prio : rank(a.kind) < rank(b.kind);
    });
    for (int i : std::as_const(order)) {
        Ann& a = anns_[i];
        a.label->setVisible(false);
        if (a.lead)
            a.lead->setVisible(false);
        if (a.lead_bg)
            a.lead_bg->setVisible(false);
        if (!a.on)
            continue;
        const QSizeF sz = a.label->boundingRect().size();
        if (sz.width() > pa.width() - 4.0 || sz.height() > pa.height() - 4.0)
            continue; // không bao giờ tràn plot area
        for (const QPointF& c : candidates(a, sz, pa)) {
            const QRectF r = clamp_in(QRectF(c, sz), pa);
            if (std::any_of(taken.cbegin(), taken.cend(), [&](const QRectF& t) { return t.intersects(r); }) ||
                std::any_of(leads.cbegin(), leads.cend(), [&](const QLineF& l) { return seg_hits(l, r); }))
                continue; // đè marker/nhãn đã đặt, hoặc che nét nối của nhãn khác
            // Nhãn bị đẩy xa marker → nối bằng một nét mảnh (từ mép marker, có viền tối); nét nối không được
            // chạy qua nhãn khác (bị che → mất liên kết nhãn ↔ marker).
            QLineF seg;
            if (a.lead) {
                const QPointF q(std::clamp(a.at.x(), r.left(), r.right()), std::clamp(a.at.y(), r.top(), r.bottom()));
                const double rad = a.hit.width() / 2.0;
                const QLineF ln(a.at, q);
                if (ln.length() > rad + 9.0)
                    seg = QLineF(ln.pointAt(rad / ln.length()), q);
            }
            if (!seg.isNull() &&
                std::any_of(labels.cbegin(), labels.cend(), [&](const QRectF& t) { return seg_hits(seg, t); }))
                continue;
            a.label->setPos(r.topLeft());
            a.label->setVisible(true);
            taken.append(r.adjusted(-2.0, -2.0, 2.0, 2.0));
            labels.append(r);
            if (!seg.isNull()) {
                a.lead->setLine(seg);
                a.lead->setVisible(true);
                a.lead_bg->setLine(seg);
                a.lead_bg->setVisible(true);
                leads.append(seg);
            }
            break;
        }
    }
}

QString LkChartAnnot::tip_at(const QPointF& p) const {
    using namespace lkannot;
    const auto label_hit = [&](const Ann& a) {
        return a.label && a.label->isVisible() && QRectF(a.label->pos(), a.label->boundingRect().size()).contains(p);
    };
    for (const Ann& a : anns_) // marker/nhãn điểm trước
        if (a.kind == Kind::Point && a.on && (a.hit.adjusted(-3.0, -3.0, 3.0, 3.0).contains(p) || label_hit(a)))
            return tip_html(a.text, a.sub, a.tip);
    for (const Ann& a : anns_)
        if (a.kind != Kind::Point && a.on && label_hit(a))
            return tip_html(a.text, a.sub, a.tip);
    for (const Ann& a : anns_)
        if (a.kind == Kind::VLine && a.on && a.hit.contains(p))
            return tip_html(a.text, a.sub, a.tip);
    return {};
}

QStringList LkChartAnnot::bands_at(double x, double chart_y) const {
    QStringList out;
    for (const Ann& a : anns_) {
        if (a.text.isEmpty())
            continue;
        if (a.kind == Kind::XBand && x >= a.x && x <= a.x1)
            out << a.text;
        else if (a.kind == Kind::HBand && a.on && chart_y >= a.hit.top() - 1.0 && chart_y <= a.hit.bottom() + 1.0)
            out << a.text;
        else if (a.kind == Kind::Box && a.on && x >= a.x && x <= a.x1 && chart_y >= a.hit.top() - 1.0 &&
                 chart_y <= a.hit.bottom() + 1.0)
            out << a.text;
    }
    return out;
}

QVector<LkChartAnnot::Shown> LkChartAnnot::shown_labels() const {
    QVector<Shown> out;
    for (const Ann& a : anns_)
        if (a.label && a.label->isVisible())
            out.append({a.text, QRectF(a.label->pos(), a.label->boundingRect().size())});
    return out;
}

} // namespace fincept::screens::langkinh
