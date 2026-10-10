// src/screens/hhp_valuation/HhpChartNotes.h
// Note layer of HhpChart — header-only, included by HhpChart.cpp only (no CMake entry needed).
//
// ▲ peak (c_rich) / ▼ trough (c_cheap) / ◆ target (c_gold) / ◇ valuation extreme (hollow, c_rich above the mean,
// c_cheap below — centred on its point) markers plus small translucent pill labels.
// Placement is a port of the Point branch of langkinh/LkChartAnnot (LkChartLayers.cpp): candidates around
// the marker, clamped into the plot area, sorted by distance + direction penalty, taken greedily by priority;
// a label that would overlap a marker, an earlier label, a reserved rect or a lead line is moved (≤ 3 notches)
// or dropped — the marker always stays. HHP adds: a label is never placed over the chart's main line or its
// dashed forecast continuation (no mapped vertex inside it, no segment crossing it), and its lead line never
// crosses them either, so the notes never cover the chart itself; band edges and mean lines are soft obstacles
// (a candidate touching one costs more), so labels prefer empty space.
// HhpNoteCard (bottom): the sticky note card that replaced the QToolTip card — a frameless, non-activating
// top-level panel placed beside the marker; HhpChart owns its show/hide rules.
#pragma once

#include "screens/hhp_valuation/HhpChart.h"
#include "screens/hhp_valuation/HhpCommon.h"

#include <QBrush>
#include <QEnterEvent>
#include <QFont>
#include <QFontMetricsF>
#include <QFrame>
#include <QGraphicsItem>
#include <QGraphicsLineItem>
#include <QGraphicsPathItem>
#include <QGuiApplication>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineF>
#include <QPainter>
#include <QPainterPath>
#include <QPen>
#include <QScreen>
#include <QScrollArea>
#include <QScrollBar>
#include <QToolButton>
#include <QVBoxLayout>

#include <algorithm>
#include <cmath>
#include <functional>
#include <iterator>

namespace fincept::screens::hhp::detail {

namespace notes {

constexpr int kLabelPx = 10;          ///< line 1, bold
constexpr int kSubPx = 8;             ///< line 2, muted
constexpr double kPadX = 4.0;
constexpr double kPadY = 1.6;
constexpr double kMaxTextW = 140.0;   ///< both lines elided to this width
constexpr int kMaxNotch = 3;          ///< vertical shifts tried before a label is dropped
constexpr double kTriW = 9.0;         ///< ▲▼ base
constexpr double kTriH = 8.0;         ///< ▲▼ height
constexpr double kDiamond = 4.8;      ///< ◆ half-diagonal
constexpr double kExtreme = 5.4;      ///< ◇ half-diagonal (outline only: the point inside stays visible)
constexpr double kPointGap = 1.5;     ///< data point ↔ flat side of ▲▼ (the extreme itself stays visible)
constexpr double kLabelGap = 3.0;     ///< marker ↔ label
constexpr double kHitPad = 4.0;       ///< hover tolerance around a marker
constexpr double kMinPlotW = 360.0;   ///< narrower plot → markers only
constexpr double kSoftCost = 1.25;    ///< per soft obstacle touched, in notches: > 1 → one notch further wins
constexpr double kZMarker = 12.0;     ///< same z plan as LkChartLayers: above series + legend
constexpr double kZLead = 12.5;
constexpr double kZLabel = 13.0;

inline QColor with_alpha(QColor c, double a) {
    c.setAlphaF(static_cast<float>(std::clamp(a, 0.0, 1.0)));
    return c;
}

inline QColor kind_color(HhpChartNote::Kind k) {
    switch (k) {
        case HhpChartNote::Kind::Peak:
        case HhpChartNote::Kind::ExtremeHigh:
            return c_rich();
        case HhpChartNote::Kind::Trough:
        case HhpChartNote::Kind::ExtremeLow:
            return c_cheap();
        case HhpChartNote::Kind::Target:
            return c_gold();
    }
    return c_gold();
}

inline bool is_extreme(HhpChartNote::Kind k) {
    return k == HhpChartNote::Kind::ExtremeHigh || k == HhpChartNote::Kind::ExtremeLow;
}

/// Card-header glyph: filled for a firm note, outline for a hollow one (◇ is always an outline).
inline QString glyph(HhpChartNote::Kind k, bool hollow) {
    switch (k) {
        case HhpChartNote::Kind::Peak:
            return hollow ? QStringLiteral("△") : QStringLiteral("▲");
        case HhpChartNote::Kind::Trough:
            return hollow ? QStringLiteral("▽") : QStringLiteral("▼");
        case HhpChartNote::Kind::Target:
            return hollow ? QStringLiteral("◇") : QStringLiteral("◆");
        case HhpChartNote::Kind::ExtremeHigh:
        case HhpChartNote::Kind::ExtremeLow:
            return QStringLiteral("◇");
    }
    return {};
}

/// Marker outline in item coordinates, (0,0) = the data point. ▲ stands on top of the point and ▼ hangs
/// under it (flat side on the point, apex pointing away from the line); ◆ and ◇ are centred on it.
inline QPainterPath marker_path(HhpChartNote::Kind k) {
    QPainterPath p;
    if (k == HhpChartNote::Kind::Target || is_extreme(k)) {
        const double r = is_extreme(k) ? kExtreme : kDiamond;
        p.moveTo(0.0, -r);
        p.lineTo(r, 0.0);
        p.lineTo(0.0, r);
        p.lineTo(-r, 0.0);
        p.closeSubpath();
        return p;
    }
    const double s = k == HhpChartNote::Kind::Peak ? -1.0 : 1.0; // screen y grows downwards
    p.moveTo(-kTriW / 2.0, s * kPointGap);
    p.lineTo(kTriW / 2.0, s * kPointGap);
    p.lineTo(0.0, s * (kPointGap + kTriH));
    p.closeSubpath();
    return p;
}

inline QRectF clamp_in(QRectF r, const QRectF& pa) {
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

/// Does segment s touch or cross rect r?
inline bool seg_hits(const QLineF& s, const QRectF& r) {
    if (std::max(s.y1(), s.y2()) < r.top() || std::min(s.y1(), s.y2()) > r.bottom() ||
        std::max(s.x1(), s.x2()) < r.left() || std::min(s.x1(), s.x2()) > r.right())
        return false; // bounding boxes apart (cheap: most segments of a long polyline)
    if (r.contains(s.p1()) || r.contains(s.p2()))
        return true;
    const QLineF edges[4] = {QLineF(r.topLeft(), r.topRight()), QLineF(r.topRight(), r.bottomRight()),
                             QLineF(r.bottomRight(), r.bottomLeft()), QLineF(r.bottomLeft(), r.topLeft())};
    return std::any_of(std::begin(edges), std::end(edges),
                       [&](const QLineF& e) { return s.intersects(e, nullptr) == QLineF::BoundedIntersection; });
}

/// Distance from p to rect r (0 inside).
inline double rect_dist(const QPointF& p, const QRectF& r) {
    const double dx = std::max({r.left() - p.x(), 0.0, p.x() - r.right()});
    const double dy = std::max({r.top() - p.y(), 0.0, p.y() - r.bottom()});
    return std::hypot(dx, dy);
}

/// Does the polyline (vertices ascending in x) have a vertex inside r or a segment crossing it?
inline bool poly_hits(const QVector<QPointF>& poly, const QRectF& r) {
    if (poly.isEmpty())
        return false;
    if (poly.size() == 1)
        return r.contains(poly.first());
    const auto it = std::lower_bound(poly.cbegin(), poly.cend(), r.left(),
                                     [](const QPointF& p, qreal x) { return p.x() < x; });
    qsizetype i = std::max<qsizetype>(0, (it - poly.cbegin()) - 1);
    for (; i + 1 < poly.size() && poly.at(i).x() <= r.right(); ++i) {
        if (seg_hits(QLineF(poly.at(i), poly.at(i + 1)), r))
            return true;
    }
    return false;
}

/// Does segment s cross the polyline (vertices ascending in x)?
inline bool poly_crosses(const QVector<QPointF>& poly, const QLineF& s) {
    if (poly.size() < 2)
        return false;
    const qreal lo = std::min(s.x1(), s.x2());
    const qreal hi = std::max(s.x1(), s.x2());
    const auto it = std::lower_bound(poly.cbegin(), poly.cend(), lo, [](const QPointF& p, qreal x) { return p.x() < x; });
    qsizetype i = std::max<qsizetype>(0, (it - poly.cbegin()) - 1);
    for (; i + 1 < poly.size() && poly.at(i).x() <= hi; ++i) {
        if (QLineF(poly.at(i), poly.at(i + 1)).intersects(s, nullptr) == QLineF::BoundedIntersection)
            return true;
    }
    return false;
}

/// Part of s (which starts inside r) after it leaves r; null when s ends inside r. The line through a marker's
/// data point also runs under the marker itself, so a lead is only checked outside the marker's bounds.
inline QLineF beyond(const QLineF& s, const QRectF& r) {
    const double dx = s.dx();
    const double dy = s.dy();
    double t = 1.0;
    if (dx > 0.0)
        t = std::min(t, (r.right() - s.x1()) / dx);
    else if (dx < 0.0)
        t = std::min(t, (r.left() - s.x1()) / dx);
    if (dy > 0.0)
        t = std::min(t, (r.bottom() - s.y1()) / dy);
    else if (dy < 0.0)
        t = std::min(t, (r.top() - s.y1()) / dy);
    t = std::max(t, 0.0);
    return t >= 1.0 ? QLineF() : QLineF(s.pointAt(t), s.p2());
}

/// Pill label: translucent dark box, 1 px edge in the kind colour, bold line + optional muted sub-line.
class Label : public QGraphicsItem {
  public:
    Label(const QString& text, const QString& sub, const QColor& edge, QGraphicsItem* parent)
        : QGraphicsItem(parent), edge_(edge) {
        f1_.setPixelSize(kLabelPx);
        f1_.setBold(true);
        f2_.setPixelSize(kSubPx);
        const QFontMetricsF m1(f1_);
        const QFontMetricsF m2(f2_);
        text_ = text.isEmpty() ? QString() : m1.elidedText(text, Qt::ElideRight, kMaxTextW);
        sub_ = sub.isEmpty() ? QString() : m2.elidedText(sub, Qt::ElideRight, kMaxTextW);
        h1_ = text_.isEmpty() ? 0.0 : m1.height();
        h2_ = sub_.isEmpty() ? 0.0 : m2.height();
        a1_ = m1.ascent();
        a2_ = m2.ascent();
        const double w = std::max(text_.isEmpty() ? 0.0 : m1.horizontalAdvance(text_),
                                  sub_.isEmpty() ? 0.0 : m2.horizontalAdvance(sub_));
        size_ = QSizeF(std::ceil(w) + 2.0 * kPadX, std::ceil(h1_ + h2_) + 2.0 * kPadY);
        setZValue(kZLabel);
        setAcceptedMouseButtons(Qt::NoButton);
        setAcceptHoverEvents(false);
    }
    QRectF boundingRect() const override { return QRectF(QPointF(0.0, 0.0), size_); }
    void paint(QPainter* p, const QStyleOptionGraphicsItem*, QWidget*) override {
        p->setRenderHint(QPainter::Antialiasing, true);
        p->setPen(QPen(edge_, 1.0));
        p->setBrush(with_alpha(c_bg(), 0.80));
        p->drawRoundedRect(boundingRect().adjusted(0.5, 0.5, -0.5, -0.5), 3.0, 3.0);
        double y = kPadY;
        if (!text_.isEmpty()) {
            p->setFont(f1_);
            p->setPen(c_text());
            p->drawText(QPointF(kPadX, y + a1_), text_);
            y += h1_;
        }
        if (!sub_.isEmpty()) {
            p->setFont(f2_);
            p->setPen(c_muted());
            p->drawText(QPointF(kPadX, y + a2_), sub_);
        }
    }

  private:
    QString text_;
    QString sub_;
    QColor edge_;
    QFont f1_;
    QFont f2_;
    double h1_ = 0.0;
    double h2_ = 0.0;
    double a1_ = 0.0;
    double a2_ = 0.0;
    QSizeF size_;
};

} // namespace notes

/// What HhpChart hands the layer on every relayout (chart = QChart item coordinates).
struct NoteLayoutInput {
    QRectF plot;                                  ///< chart->plotArea(); empty → hide everything
    qreal x_min = 0;                              ///< x-axis range (epoch ms)
    qreal x_max = 0;
    std::function<QPointF(qreal, double)> map;    ///< (x ms, left-axis y) → chart position
    std::function<double(qreal)> snap_y;          ///< main-line y at x; NaN outside the line
    QVector<QVector<QPointF>> lines;              ///< lines labels and leads may not cover/cross (main + forecast lines), mapped, ascending x
    QVector<QVector<QPointF>> soft;               ///< lines labels avoid when they can (band edges, mean), mapped, ascending x
    QVector<QRectF> reserved;                     ///< rects labels must avoid (e.g. the "hôm nay" caption)
};

class HhpNoteLayer {
  public:
    explicit HhpNoteLayer(QGraphicsItem* parent) : parent_(parent) {}
    ~HhpNoteLayer() { clear_items(); }
    HhpNoteLayer(const HhpNoteLayer&) = delete;
    HhpNoteLayer& operator=(const HhpNoteLayer&) = delete;

    /// One marker (+ label and lead line when the note has text) per note, in the same order as `notes`.
    void set_notes(const QVector<HhpChartNote>& notes) {
        using namespace notes;
        clear_items();
        items_.reserve(notes.size());
        for (const HhpChartNote& n : notes) {
            Item it;
            it.note = n;
            it.note.priority = std::clamp(n.priority, 1, 3);
            const QColor col = kind_color(n.kind);
            it.mk = new QGraphicsPathItem(marker_path(n.kind), parent_);
            if (is_extreme(n.kind)) { // always an outline (the point inside stays visible); tạm / UNVERIFIED → dotted
                it.mk->setBrush(Qt::NoBrush);
                it.mk->setPen(QPen(col, 1.6, n.hollow ? Qt::DotLine : Qt::SolidLine));
            } else if (n.hollow) {
                it.mk->setBrush(Qt::NoBrush);
                it.mk->setPen(QPen(col, 1.4));
            } else {
                it.mk->setBrush(col);
                it.mk->setPen(QPen(c_bg(), 1.4));
            }
            it.mk->setZValue(kZMarker + 0.1 * (3 - it.note.priority)); // priority 1 on top of a coincident 3
            it.mk->setAcceptedMouseButtons(Qt::NoButton);
            it.mk->setVisible(false);
            if (!n.label.isEmpty() || !n.sub.isEmpty()) {
                it.label = new Label(n.label, n.sub, with_alpha(col, 0.7), parent_);
                it.label->setVisible(false);
                QPen bp(with_alpha(c_bg(), 0.85), 3.0);
                bp.setCapStyle(Qt::RoundCap);
                it.lead_bg = new QGraphicsLineItem(parent_);
                it.lead_bg->setPen(bp);
                it.lead_bg->setZValue(kZLead - 0.1);
                it.lead_bg->setVisible(false);
                it.lead = new QGraphicsLineItem(parent_);
                it.lead->setPen(QPen(with_alpha(col, 0.6), 1.0));
                it.lead->setZValue(kZLead);
                it.lead->setVisible(false);
            }
            items_.append(it);
        }
    }

    void hide_all() {
        for (Item& it : items_) {
            it.on = false;
            it.mk->setVisible(false);
            hide_label(it);
        }
    }

    void relayout(const NoteLayoutInput& in) {
        using namespace notes;
        const QRectF pa = in.plot;
        if (pa.width() <= 1.0 || pa.height() <= 1.0 || !in.map) {
            hide_all();
            return;
        }
        QVector<QRectF> taken; // markers, placed labels, reserved: a later label may not overlap them
        for (const QRectF& r : in.reserved)
            taken.append(r.adjusted(-2.0, -2.0, 2.0, 2.0));
        for (Item& it : items_) {
            it.on = false;
            hide_label(it);
            const qreal x = it.note.x_ms;
            double y = it.note.y;
            if (x >= in.x_min && x <= in.x_max && !has(y) && in.snap_y)
                y = in.snap_y(x);
            if (!(x >= in.x_min && x <= in.x_max) || !has(y)) {
                it.mk->setVisible(false);
                continue;
            }
            it.at = in.map(x, y);
            if (!pa.adjusted(-1.0, -1.0, 1.0, 1.0).contains(it.at)) {
                it.mk->setVisible(false);
                continue;
            }
            it.mk->setPos(it.at);
            it.mk_rect = it.mk->mapRectToParent(it.mk->boundingRect());
            it.mk->setVisible(true);
            it.on = true;
            taken.append(it.mk_rect.adjusted(-2.0, -2.0, 2.0, 2.0));
        }
        if (pa.width() < kMinPlotW)
            return; // markers only: labels would crowd a narrow plot

        // Labels by priority (1 first); same priority → most recent first.
        QVector<int> order;
        for (int i = 0; i < items_.size(); ++i)
            if (items_.at(i).label && items_.at(i).on)
                order.append(i);
        std::stable_sort(order.begin(), order.end(), [this](int l, int r) {
            const HhpChartNote& a = items_.at(l).note;
            const HhpChartNote& b = items_.at(r).note;
            return a.priority != b.priority ? a.priority < b.priority : a.x_ms > b.x_ms;
        });
        // Band edges and mean lines are soft obstacles — but never at the cost of a label: while the soft-aware
        // layout shows fewer labels than the plain one, the first label (in order) placed differently goes back to
        // the plain ranking and the layout is redone (≤ one redo per label; usually none).
        QVector<bool> soft_on(items_.size(), !in.soft.isEmpty());
        QVector<Placed> best = place(order, taken, in, soft_on);
        const auto shown = [](const QVector<Placed>& v) {
            return std::count_if(v.cbegin(), v.cend(), [](const Placed& p) { return p.ok; });
        };
        if (!in.soft.isEmpty() && shown(best) < order.size()) {
            const QVector<Placed> plain = place(order, taken, in, QVector<bool>(items_.size(), false));
            while (shown(best) < shown(plain)) {
                int k = -1;
                for (int i : std::as_const(order))
                    if (soft_on.at(i) && (best.at(i).ok != plain.at(i).ok || best.at(i).r != plain.at(i).r)) {
                        k = i;
                        break;
                    }
                if (k < 0) {
                    best = plain;
                    break;
                }
                soft_on[k] = false;
                best = place(order, taken, in, soft_on);
            }
        }
        for (int i : std::as_const(order)) {
            const Placed& p = best.at(i);
            if (!p.ok)
                continue;
            Item& it = items_[i];
            it.label->setPos(p.r.topLeft());
            it.label->setVisible(true);
            if (!p.seg.isNull()) {
                it.lead->setLine(p.seg);
                it.lead->setVisible(true);
                it.lead_bg->setLine(p.seg);
                it.lead_bg->setVisible(true);
            }
        }
    }

    /// Index of the note under p (chart coords): nearest marker within kHitPad, else a visible label.
    int hit(const QPointF& p, QRectF* rect) const {
        int best = -1;
        double best_d = 0.0;
        for (int i = 0; i < items_.size(); ++i) {
            const Item& it = items_.at(i);
            const QRectF r = it.mk_rect.adjusted(-notes::kHitPad, -notes::kHitPad, notes::kHitPad, notes::kHitPad);
            if (!it.on || !r.contains(p))
                continue;
            const double d = QLineF(p, it.mk_rect.center()).length();
            if (best < 0 || d < best_d) {
                best = i;
                best_d = d;
            }
        }
        if (best >= 0) {
            if (rect)
                *rect = items_.at(best).mk_rect.adjusted(-notes::kHitPad, -notes::kHitPad, notes::kHitPad,
                                                         notes::kHitPad);
            return best;
        }
        for (int i = 0; i < items_.size(); ++i) {
            const Item& it = items_.at(i);
            if (!it.on || !it.label || !it.label->isVisible())
                continue;
            const QRectF r(it.label->pos(), it.label->boundingRect().size());
            if (r.contains(p)) {
                if (rect)
                    *rect = r;
                return i;
            }
        }
        return -1;
    }

    struct Geom {
        QString id;
        QRectF marker; ///< chart coords; empty = hidden
        QRectF label;  ///< chart coords; empty = hidden
        QLineF lead;   ///< chart coords; null = no lead line drawn
    };
    QVector<Geom> geometry() const {
        QVector<Geom> out;
        out.reserve(items_.size());
        for (const Item& it : items_) {
            Geom g;
            g.id = it.note.id;
            if (it.on)
                g.marker = it.mk_rect;
            if (it.on && it.label && it.label->isVisible())
                g.label = QRectF(it.label->pos(), it.label->boundingRect().size());
            if (it.on && it.lead && it.lead->isVisible())
                g.lead = it.lead->line();
            out.append(g);
        }
        return out;
    }

  private:
    struct Item {
        HhpChartNote note;
        QGraphicsPathItem* mk = nullptr;
        notes::Label* label = nullptr;
        QGraphicsLineItem* lead = nullptr;
        QGraphicsLineItem* lead_bg = nullptr; ///< dark underlay: the lead stays visible across same-colour fills
        QPointF at;                           ///< data point (chart coords) after relayout
        QRectF mk_rect;                       ///< marker bounds (chart coords) after relayout
        bool on = false;                      ///< marker inside the plot area
    };

    struct Placed {
        bool ok = false; ///< label shown
        QRectF r;        ///< label rect (chart coords)
        QLineF seg;      ///< lead line; null = none
    };

    /// Greedy label placement in `order` (indices into items_) around the markers already in `taken0`; soft
    /// obstacles count only for items with soft_on[i]. Pure: returns the result per item, touches no item.
    QVector<Placed> place(const QVector<int>& order, const QVector<QRectF>& taken0, const NoteLayoutInput& in,
                          const QVector<bool>& soft_on) const {
        using namespace notes;
        static const QVector<QVector<QPointF>> kNoSoft;
        const QRectF pa = in.plot;
        QVector<Placed> out(items_.size());
        QVector<QRectF> taken = taken0;
        QVector<QRectF> labels;
        QVector<QLineF> leads;
        for (int i : order) {
            const Item& it = items_.at(i);
            const QSizeF sz = it.label->boundingRect().size();
            if (sz.width() > pa.width() - 4.0 || sz.height() > pa.height() - 4.0)
                continue;
            for (const QPointF& c : candidates(it, sz, pa, soft_on.at(i) ? in.soft : kNoSoft)) {
                const QRectF r = clamp_in(QRectF(c, sz), pa);
                if (std::any_of(taken.cbegin(), taken.cend(), [&](const QRectF& t) { return t.intersects(r); }) ||
                    std::any_of(leads.cbegin(), leads.cend(), [&](const QLineF& l) { return seg_hits(l, r); }) ||
                    std::any_of(in.lines.cbegin(), in.lines.cend(), [&](const QVector<QPointF>& poly) {
                        return poly_hits(poly, r.adjusted(-1.0, -1.0, 1.0, 1.0));
                    }))
                    continue;
                // Label pushed away from its marker → thin lead line from the marker edge; it may not run
                // through another label (the label ↔ marker link would be lost) nor cross the main line or its
                // dashed continuation outside the marker (its dark underlay would cut a gap into the line).
                // No candidate left → marker only.
                QLineF seg;
                const QPointF mc = it.mk_rect.center();
                const QPointF q(std::clamp(mc.x(), r.left(), r.right()), std::clamp(mc.y(), r.top(), r.bottom()));
                const double rad = std::max(it.mk_rect.width(), it.mk_rect.height()) / 2.0;
                const QLineF ln(mc, q);
                if (ln.length() > rad + 9.0)
                    seg = QLineF(ln.pointAt(rad / ln.length()), q);
                if (!seg.isNull() &&
                    std::any_of(labels.cbegin(), labels.cend(), [&](const QRectF& t) { return seg_hits(seg, t); }))
                    continue;
                if (!seg.isNull()) {
                    const QLineF beyond_mk = beyond(ln, it.mk_rect);
                    if (!beyond_mk.isNull() &&
                        std::any_of(in.lines.cbegin(), in.lines.cend(),
                                    [&](const QVector<QPointF>& poly) { return poly_crosses(poly, beyond_mk); }))
                        continue;
                }
                out[i] = {true, r, seg};
                taken.append(r.adjusted(-2.0, -2.0, 2.0, 2.0));
                labels.append(r);
                if (!seg.isNull())
                    leads.append(seg);
                break;
            }
        }
        return out;
    }

    static void hide_label(Item& it) {
        if (it.label)
            it.label->setVisible(false);
        if (it.lead)
            it.lead->setVisible(false);
        if (it.lead_bg)
            it.lead_bg->setVisible(false);
    }

    void clear_items() {
        for (Item& it : items_) {
            delete it.mk;
            delete it.label;
            delete it.lead;
            delete it.lead_bg;
        }
        items_.clear();
    }

    /// LkChartAnnot::candidates (Point) with HHP directions: ▲ and a high ◇ prefer above (sides shifted up), ▼ and a
    /// low ◇ below (sides shifted down), ◆ right. Cost = distance label ↔ marker + direction penalty + kSoftCost
    /// notches per soft line (band edge, mean) the label would sit on; anything further than kMaxNotch notches
    /// (usually a clamp at the plot edge) is dropped, so a label never drifts off its marker.
    QVector<QPointF> candidates(const Item& it, const QSizeF& sz, const QRectF& pa,
                                const QVector<QVector<QPointF>>& soft) const {
        using namespace notes;
        enum Dir { Above, Below, Left, Right };
        const double w = sz.width();
        const double h = sz.height();
        const QRectF blob = it.mk_rect.united(QRectF(it.at - QPointF(1.0, 1.0), QSizeF(2.0, 2.0)));
        const QPointF c = blob.center();
        const double step = h + 3.0;
        const QPointF base[4] = {QPointF(c.x() - w / 2.0, blob.top() - kLabelGap - h),
                                 QPointF(c.x() - w / 2.0, blob.bottom() + kLabelGap),
                                 QPointF(blob.left() - kLabelGap - w, c.y() - h / 2.0),
                                 QPointF(blob.right() + kLabelGap, c.y() - h / 2.0)};
        Dir pref = Right;
        Dir opp = Left;
        double side_sign = 0.0; // 0 = sides shift both ways (◆)
        if (it.note.kind == HhpChartNote::Kind::Peak || it.note.kind == HhpChartNote::Kind::ExtremeHigh) {
            pref = Above;
            opp = Below;
            side_sign = -1.0;
        } else if (it.note.kind == HhpChartNote::Kind::Trough || it.note.kind == HhpChartNote::Kind::ExtremeLow) {
            pref = Below;
            opp = Above;
            side_sign = 1.0;
        }
        const double rad = std::max(blob.width(), blob.height()) / 2.0;
        const double max_dist = rad + kLabelGap + kMaxNotch * step + 1.0;
        struct Cand {
            QPointF p;
            double cost;
        };
        QVector<Cand> cs;
        const auto add = [&](Dir d, double dy) {
            const QRectF rr = clamp_in(QRectF(base[d] + QPointF(0.0, dy), sz), pa);
            const double dist = rect_dist(c, rr);
            if (dist > max_dist)
                return;
            double cost = dist + (d == pref ? 0.0 : (d == opp ? 2.0 : 4.0));
            for (const QVector<QPointF>& poly : soft)
                if (poly_hits(poly, rr))
                    cost += kSoftCost * step;
            cs.append({rr.topLeft(), cost});
        };
        for (const Dir d : {Above, Below, Left, Right}) {
            for (int k = 0; k <= kMaxNotch; ++k) {
                if (d == Above) {
                    add(d, -k * step);
                } else if (d == Below) {
                    add(d, k * step);
                } else if (side_sign != 0.0) {
                    add(d, side_sign * k * step);
                } else {
                    add(d, -k * step);
                    if (k > 0)
                        add(d, k * step);
                }
            }
        }
        std::stable_sort(cs.begin(), cs.end(), [](const Cand& l, const Cand& r) { return l.cost < r.cost; });
        QVector<QPointF> out;
        out.reserve(cs.size());
        for (const Cand& cd : std::as_const(cs))
            out.append(cd.p);
        return out;
    }

    QGraphicsItem* parent_ = nullptr;
    QVector<Item> items_;
};

/// Sticky note card: frameless, non-activating Qt::Tool panel — thin header (kind glyph + label · "📌 đã ghim" · ✕)
/// over a scrollable rich-text body (detail_html). Width = the body's size hint (as the old QToolTip, ~520–560 px),
/// height ≤ 85% of the screen's available height (the body scrolls). Reports enter/leave/✕; HhpChart decides WHEN.
class HhpNoteCard : public QFrame {
  public:
    static constexpr double kMaxScreenFrac = 0.85; ///< card height ≤ this × available screen height
    static constexpr int kGap = 8;                 ///< marker ↔ card (px)
    static constexpr int kScrollW = 8;             ///< styled vertical scrollbar width (px)

    explicit HhpNoteCard(QWidget* owner)
        : QFrame(owner, Qt::Tool | Qt::FramelessWindowHint | Qt::WindowDoesNotAcceptFocus) {
        setObjectName(QStringLiteral("hhpNoteCard"));
        setAttribute(Qt::WA_ShowWithoutActivating, true);
        setAttribute(Qt::WA_DeleteOnClose, false);
        auto* root = new QVBoxLayout(this);
        root->setContentsMargins(0, 0, 0, 0);
        root->setSpacing(0);
        header_ = new QWidget(this);
        header_->setObjectName(QStringLiteral("hhpNoteCardHeader"));
        header_->setAttribute(Qt::WA_StyledBackground, true);
        auto* hl = new QHBoxLayout(header_);
        hl->setContentsMargins(8, 2, 2, 2);
        hl->setSpacing(6);
        glyph_ = new QLabel(header_);
        title_ = new QLabel(header_);
        title_->setObjectName(QStringLiteral("hhpNoteCardTitle"));
        hint_ = new QLabel(header_);
        hint_->setObjectName(QStringLiteral("hhpNoteCardHint"));
        for (QLabel* l : {glyph_, title_, hint_})
            l->setTextFormat(Qt::PlainText);
        close_ = new QToolButton(header_);
        close_->setObjectName(QStringLiteral("hhpNoteCardClose"));
        close_->setText(QStringLiteral("✕"));
        close_->setToolTip(QStringLiteral("Đóng thẻ (Esc)"));
        close_->setFocusPolicy(Qt::NoFocus);
        close_->setCursor(Qt::PointingHandCursor);
        QObject::connect(close_, &QToolButton::clicked, this, [this]() {
            if (on_close)
                on_close();
        });
        hl->addWidget(glyph_);
        hl->addWidget(title_, 1);
        hl->addWidget(hint_);
        hl->addWidget(close_);
        root->addWidget(header_);
        scroll_ = new QScrollArea(this);
        scroll_->setObjectName(QStringLiteral("hhpNoteCardScroll"));
        scroll_->setFrameShape(QFrame::NoFrame);
        scroll_->setWidgetResizable(true);
        scroll_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        scroll_->setFocusPolicy(Qt::NoFocus);
        body_ = new QLabel;
        body_->setObjectName(QStringLiteral("hhpNoteCardBody"));
        body_->setTextFormat(Qt::RichText);
        body_->setWordWrap(true); // same size heuristic as QToolTip's label for rich text
        body_->setAlignment(Qt::AlignLeft | Qt::AlignTop);
        body_->setTextInteractionFlags(Qt::NoTextInteraction);
        scroll_->setWidget(body_);
        root->addWidget(scroll_, 1);
        restyle(c_gold());
    }

    std::function<void()> on_enter, on_leave, on_close; ///< cursor entered / left the card · ✕ clicked

    QString note_id() const { return id_; }
    bool pinned() const { return pinned_; }

    void set_note(const HhpChartNote& n) {
        id_ = n.id;
        glyph_->setText(notes::glyph(n.kind, n.hollow));
        const QString t = n.label.isEmpty() ? QStringLiteral("Ghi chú") : n.label;
        title_->setText(QFontMetrics(title_->font()).elidedText(t, Qt::ElideRight, 260));
        body_->setText(n.detail_html);
        restyle(notes::kind_color(n.kind));
        scroll_->verticalScrollBar()->setValue(0);
    }

    void set_pinned(bool on) {
        pinned_ = on;
        hint_->setText(on ? QStringLiteral("📌 đã ghim · Esc/✕ để đóng") : QStringLiteral("bấm ký hiệu để ghim"));
        hint_->setStyleSheet(on ? QStringLiteral("color: %1;").arg(css(c_gold())) : QString());
    }

    /// Size for the marker's screen, then move beside `mk` (global rect): right → left → above → below, the first
    /// side where the whole card stays on that screen. None fits → the roomier of right/left, clamped vertically
    /// only: the card never covers the marker.
    void place_beside(const QRect& mk) {
        QScreen* scr = QGuiApplication::screenAt(mk.center());
        if (!scr)
            scr = parentWidget() ? parentWidget()->screen() : QGuiApplication::primaryScreen();
        const QRect av = scr ? scr->availableGeometry() : QRect(mk.center() - QPoint(800, 500), QSize(1600, 1000));
        fit(av);
        const QSize s = size();
        const auto clamp_x = [&](int x) { return std::clamp(x, av.left(), std::max(av.left(), av.right() + 1 - s.width())); };
        const auto clamp_y = [&](int y) { return std::clamp(y, av.top(), std::max(av.top(), av.bottom() + 1 - s.height())); };
        const int y_side = clamp_y(mk.center().y() - 24);
        const int x_right = mk.right() + 1 + kGap;
        const int x_left = mk.left() - kGap - s.width();
        const int room_r = av.right() + 1 - x_right;
        const int room_l = mk.left() - kGap - av.left();
        QPoint p;
        if (room_r >= s.width())
            p = QPoint(x_right, y_side);
        else if (room_l >= s.width())
            p = QPoint(x_left, y_side);
        else if (mk.top() - kGap - av.top() >= s.height())
            p = QPoint(clamp_x(mk.center().x() - s.width() / 2), mk.top() - kGap - s.height());
        else if (av.bottom() + 1 - (mk.bottom() + 1 + kGap) >= s.height())
            p = QPoint(clamp_x(mk.center().x() - s.width() / 2), mk.bottom() + 1 + kGap);
        else
            p = QPoint(room_r >= room_l ? x_right : x_left, y_side);
        move(p);
    }

  protected:
    void enterEvent(QEnterEvent* e) override {
        QFrame::enterEvent(e);
        if (on_enter)
            on_enter();
    }
    void leaveEvent(QEvent* e) override {
        QFrame::leaveEvent(e);
        if (on_leave)
            on_leave();
    }

  private:
    /// Fixed size: body at its own width hint (capped by the screen), header on top; taller than
    /// kMaxScreenFrac × screen → capped, the body scrolls and the card widens by the scrollbar.
    void fit(const QRect& av) {
        ensurePolished(); // children too: stylesheet fonts before the size hints
        const int fw = frameWidth();
        const int bw = std::max(120, std::min(body_->sizeHint().width(), av.width() - 2 * kGap - 2 * fw - kScrollW));
        const int bh = std::max(0, body_->heightForWidth(bw));
        const int max_h = static_cast<int>(av.height() * kMaxScreenFrac);
        int w = bw + 2 * fw;
        int h = header_->sizeHint().height() + bh + 2 * fw + 2; // +2: no scrollbar from a rounding pixel
        if (h > max_h) {
            h = max_h;
            w += kScrollW;
        }
        setFixedSize(w, h);
    }

    void restyle(const QColor& edge) {
        setStyleSheet(QStringLiteral(
                          "QFrame#hhpNoteCard { background: %1; border: 1px solid %2; }"
                          "QWidget#hhpNoteCardHeader { background: %3; border: none; border-bottom: 1px solid %4; }"
                          "QLabel { background: transparent; color: %5; border: none; }"
                          "QLabel#hhpNoteCardTitle { font-size: 11px; font-weight: 700; }"
                          "QLabel#hhpNoteCardHint { color: %6; font-size: 10px; }"
                          "QToolButton#hhpNoteCardClose { background: transparent; color: %5; border: none;"
                          " font-size: 14px; padding: 0 6px; }"
                          "QToolButton#hhpNoteCardClose:hover { color: %1; background: %5; }"
                          "QScrollArea#hhpNoteCardScroll, QWidget#qt_scrollarea_viewport { background: %1; border: none; }"
                          "QScrollBar:vertical { background: %1; width: %7px; margin: 0; border: none; }"
                          "QScrollBar::handle:vertical { background: %4; min-height: 24px; border-radius: 3px; }"
                          "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
                          "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }")
                          .arg(css(c_card()),
                               QStringLiteral("rgba(%1, %2, %3, 0.85)").arg(edge.red()).arg(edge.green()).arg(edge.blue()),
                               css(c_bg()),
                               css(c_line()), css(c_text()), css(c_muted()))
                          .arg(kScrollW));
        glyph_->setStyleSheet(QStringLiteral("color: %1; font-size: 11px;").arg(css(edge)));
    }

    QWidget* header_ = nullptr;
    QLabel* glyph_ = nullptr;
    QLabel* title_ = nullptr;
    QLabel* hint_ = nullptr;
    QToolButton* close_ = nullptr;
    QScrollArea* scroll_ = nullptr;
    QLabel* body_ = nullptr;
    QString id_;
    bool pinned_ = false;
};

} // namespace fincept::screens::hhp::detail
