// src/screens/hhp_valuation/HhpWeeklyWidgets.cpp
// Native redraw of the weekly issue's two SVG chart kinds (see HhpWeeklyWidgets.h):
//   HhpBandStrip — section 03 price band of one ticker (issue row + optional live row, one x-scale).
//   HhpSigmaDist — section 04 "Thước σ" (one tick per ticker on a −3,5σ…+4,5σ ruler, zone backgrounds).
// Everything is painted from numbers; the only strings drawn are tickers, row tags and fixed captions.
#include "screens/hhp_valuation/HhpWeeklyWidgets.h"

#include "screens/hhp_valuation/HhpWeeklyCommon.h"

#include <QEvent>
#include <QFont>
#include <QFontMetricsF>
#include <QMouseEvent>
#include <QPainter>
#include <QPen>
#include <QPolygonF>
#include <QSet>
#include <QToolTip>

#include <algorithm>
#include <cmath>
#include <functional>
#include <utility>

namespace fincept::screens::hhp::weekly {

namespace {

// ── Shared ───────────────────────────────────────────────────────────────────

QFont mono_font(int px, bool bold = false) {
    QFont f(QStringLiteral("Menlo"));
    f.setStyleHint(QFont::Monospace);
    f.setPixelSize(px);
    f.setBold(bold);
    return f;
}

/// Draws `text` centred on `x`, kept inside [lo, hi]; returns the rectangle used.
QRectF draw_centered(QPainter& p, const QString& text, qreal x, qreal y, qreal h, qreal lo, qreal hi) {
    const qreal w = QFontMetricsF(p.font()).horizontalAdvance(text) + 2;
    const qreal left = std::clamp(x - w / 2, lo, std::max(lo, hi - w));
    const QRectF r(left, y, w, h);
    p.drawText(r, Qt::AlignCenter, text);
    return r;
}

/// Calls `fn` after every resize of `target` — lets a widget whose height depends on its width refit
/// without a resizeEvent override in its public header.
class ResizeHook : public QObject {
  public:
    ResizeHook(QWidget* target, std::function<void()> fn) : QObject(target), fn_(std::move(fn)) {
        target->installEventFilter(this);
    }

    bool eventFilter(QObject* obj, QEvent* ev) override {
        if (ev->type() == QEvent::Resize)
            fn_();
        return QObject::eventFilter(obj, ev);
    }

  private:
    std::function<void()> fn_;
};

// ── HhpBandStrip geometry ────────────────────────────────────────────────────

constexpr int kBandGutter = 48;  // row tag column ("11/09")
constexpr int kBandPadR = 8;
constexpr int kBandTop = 4;
constexpr int kBandRowH = 52;    // fair caption · band · marker · price text
constexpr int kBandOneRowH = 64;
constexpr int kBandTwoRowH = 112;
// Offsets inside one row (from the row top).
constexpr qreal kFairTxtH = 12;
constexpr qreal kBarY = 14;
constexpr qreal kBarH = 15;
constexpr qreal kTriH = 8;
constexpr qreal kPriceTxtH = 13;
constexpr double kBandAlpha = 0.24;

struct XScale {
    double lo = 0, hi = 1;
    qreal left = 0, width = 1;
    qreal x(double v) const { return left + static_cast<qreal>((v - lo) / (hi - lo)) * width; }
};

QColor price_color(const BandLevels& b) {
    if (b.price < b.cheap1)
        return c_floor();
    if (b.price < b.fair)
        return c_cheap();
    if (b.price > b.rich2)
        return c_ceil();
    if (b.price > b.rich1)
        return c_rich();
    return c_muted();
}

QString band_text(const BandLevels& b) {
    return QStringLiteral("rẻ %1–%2 · hợp lý %3 · đắt %4–%5 · giá %6")
        .arg(fmt_vi(b.cheap2), fmt_vi(b.cheap1), fmt_vi(b.fair), fmt_vi(b.rich1), fmt_vi(b.rich2), fmt_vi(b.price));
}

void paint_band_row(QPainter& p, const BandLevels& b, const QString& tag, const QColor& tag_color, qreal y0,
                    const XScale& xs, qreal widget_w) {
    const qreal x2 = xs.x(b.cheap2), x1 = xs.x(b.cheap1), xf = xs.x(b.fair), xr1 = xs.x(b.rich1), xr2 = xs.x(b.rich2);
    const QRectF bar(x2, y0 + kBarY, xr2 - x2, kBarH);

    p.setFont(mono_font(10));
    p.setPen(tag_color);
    p.drawText(QRectF(0, bar.top() - 4, kBandGutter - 8, bar.height() + 8), Qt::AlignRight | Qt::AlignVCenter, tag);

    p.fillRect(bar, c_card2());
    const auto seg = [&](qreal a, qreal c, const QColor& col) {
        p.fillRect(QRectF(QPointF(a, bar.top()), QPointF(c, bar.bottom())), col);
    };
    seg(x2, x1, soft(c_floor(), kBandAlpha));
    seg(x1, xf, soft(c_cheap(), kBandAlpha));
    seg(xr1, xr2, soft(c_rich(), kBandAlpha));

    // End labels inside the band, dropped when they would run into the fair line.
    p.setFont(mono_font(9));
    p.setPen(c_muted());
    const QFontMetricsF fm9(p.font());
    const QString lo_txt = fmt_vi(b.cheap2), hi_txt = fmt_vi(b.rich2);
    const qreal lo_w = fm9.horizontalAdvance(lo_txt), hi_w = fm9.horizontalAdvance(hi_txt);
    if (bar.left() + 3 + lo_w < xf - 5)
        p.drawText(QRectF(bar.left() + 3, bar.top(), lo_w + 1, bar.height()), Qt::AlignLeft | Qt::AlignVCenter, lo_txt);
    if (bar.right() - 3 - hi_w > xf + 5)
        p.drawText(QRectF(bar.right() - 3 - hi_w - 1, bar.top(), hi_w + 1, bar.height()),
                   Qt::AlignRight | Qt::AlignVCenter, hi_txt);

    // Fair line + caption.
    p.setPen(QPen(c_gold(), 2.0, Qt::SolidLine, Qt::FlatCap));
    p.drawLine(QPointF(xf, bar.top() - 3), QPointF(xf, bar.bottom() + 3));
    p.setFont(mono_font(10, true));
    draw_centered(p, QStringLiteral("HỢP LÝ ") + fmt_vi(b.fair), xf, y0, kFairTxtH, kBandGutter, widget_w);

    // Price marker: triangle under the band + value.
    if (!has(b.price))
        return;
    const qreal px = xs.x(b.price);
    const QColor col = price_color(b);
    QPolygonF tri;
    tri << QPointF(px, bar.bottom() + 1) << QPointF(px - 5, bar.bottom() + 1 + kTriH)
        << QPointF(px + 5, bar.bottom() + 1 + kTriH);
    p.setPen(Qt::NoPen);
    p.setBrush(col);
    p.drawPolygon(tri);
    p.setBrush(Qt::NoBrush);
    p.setFont(mono_font(11, true));
    p.setPen(col);
    draw_centered(p, fmt_vi(b.price), px, bar.bottom() + 1 + kTriH, kPriceTxtH, 0, widget_w);
}

// ── HhpSigmaDist geometry ────────────────────────────────────────────────────

constexpr double kSigLo = -3.5;
constexpr double kSigHi = 4.5;
constexpr int kDistGutter = 48;
constexpr int kDistPadR = 10;
constexpr int kDistTop = 6;
constexpr int kZoneH = 42;       // zone band holding the ticks (+ kStripGap ≈ 46 px per series)
constexpr int kStripGap = 4;
constexpr int kLabelRowH = 13;
constexpr int kLabelGap = 4;     // min horizontal gap between two labels of one row
constexpr int kMaxLabelRows = 6; // beyond this, a label overlaps in the least crowded row
constexpr int kAxisH = 30;       // σ tick labels + zone legend
constexpr int kHoverPx = 4;
constexpr int kTipMax = 8;       // tooltip lines before "…"
constexpr int kDefaultDistW = 720;
constexpr double kZoneAlpha = 0.2;

struct PlacedLabel {
    QString tk;
    double s = 0;
    qreal x = 0;     // tick x
    QRectF rect;     // text box; top filled in at paint time from the strip
    int row = 0;
};

struct StripLayout {
    const QVector<DistPoint>* pts = nullptr;
    QString tag;
    qreal top = 0; // zone band top
    int rows = 0;  // label rows under the band
    QVector<PlacedLabel> labels;
    qreal bottom() const { return top + kZoneH + (rows > 0 ? 3 + rows * kLabelRowH : 0); }
};

struct DistLayout {
    qreal left = 0, width = 1;
    QVector<StripLayout> strips;
    qreal axis_top = 0;
    int height = 0;
    qreal x(double s) const {
        const double c = std::clamp(s, kSigLo, kSigHi);
        return left + static_cast<qreal>((c - kSigLo) / (kSigHi - kSigLo)) * width;
    }
};

QVector<PlacedLabel> place_labels(const QVector<DistPoint>& pts, const QSet<QString>& wanted, const DistLayout& lay,
                                  qreal right_edge, int& rows_out) {
    QVector<PlacedLabel> out;
    const QFontMetricsF fm(mono_font(10, true));
    for (const DistPoint& d : pts) {
        if (!has(d.s) || !wanted.contains(d.tk))
            continue;
        PlacedLabel l;
        l.tk = d.tk;
        l.s = d.s;
        l.x = lay.x(d.s);
        const qreal w = fm.horizontalAdvance(d.tk) + 2;
        l.rect = QRectF(std::clamp(l.x - w / 2, lay.left, std::max(lay.left, right_edge - w)), 0, w, kLabelRowH);
        out.append(l);
    }
    std::stable_sort(out.begin(), out.end(), [](const PlacedLabel& a, const PlacedLabel& b) { return a.x < b.x; });

    QVector<qreal> row_right; // right edge of the last label in each row
    for (PlacedLabel& l : out) {
        int row = -1;
        for (int r = 0; r < row_right.size(); ++r) {
            if (l.rect.left() >= row_right.at(r) + kLabelGap) {
                row = r;
                break;
            }
        }
        if (row < 0 && row_right.size() < kMaxLabelRows) {
            row_right.append(-1e9);
            row = static_cast<int>(row_right.size()) - 1;
        }
        if (row < 0) // every row taken: overlap in the one whose last label ends first
            row = static_cast<int>(std::min_element(row_right.begin(), row_right.end()) - row_right.begin());
        l.row = row;
        row_right[row] = std::max(row_right.at(row), l.rect.right());
    }
    rows_out = static_cast<int>(row_right.size());
    return out;
}

DistLayout dist_layout(int widget_w, const QVector<DistPoint>& issue, const QString& issue_tag,
                       const QVector<DistPoint>& live, const QString& live_tag, const QStringList& labels) {
    DistLayout lay;
    lay.left = kDistGutter;
    lay.width = std::max<qreal>(40, widget_w - kDistGutter - kDistPadR);
    const QSet<QString> wanted(labels.begin(), labels.end());
    const qreal right_edge = widget_w - 2;

    qreal y = kDistTop;
    const auto add = [&](const QVector<DistPoint>& pts, const QString& tag) {
        StripLayout s;
        s.pts = &pts;
        s.tag = tag;
        s.top = y;
        s.labels = place_labels(pts, wanted, lay, right_edge, s.rows);
        y = s.bottom() + kStripGap;
        lay.strips.append(s);
    };
    add(issue, issue_tag);
    if (!live.isEmpty())
        add(live, live_tag);
    lay.axis_top = y;
    lay.height = static_cast<int>(std::ceil(y + kAxisH));
    return lay;
}

struct Zone {
    double lo, hi;
    QColor color;
    const char* name; // UTF-8
};

QVector<Zone> zones() {
    return {{kSigLo, -2.0, soft(c_floor(), kZoneAlpha), "RẺ SÂU"},
            {-2.0, -1.0, soft(c_cheap(), kZoneAlpha), "RẺ"},
            {-1.0, 1.0, c_card2(), "TRUNG TÍNH"},
            {1.0, 2.0, soft(c_rich(), kZoneAlpha), "ĐẮT"},
            {2.0, kSigHi, soft(c_ceil(), kZoneAlpha), "RẤT ĐẮT"}};
}

/// Small arrow at the top of a clamped tick, pointing out of the ruler.
void draw_clamp_cap(QPainter& p, qreal x, qreal y, bool low, const QColor& col) {
    QPolygonF tri;
    if (low)
        tri << QPointF(x - 4, y) << QPointF(x + 1, y - 3.5) << QPointF(x + 1, y + 3.5);
    else
        tri << QPointF(x + 4, y) << QPointF(x - 1, y - 3.5) << QPointF(x - 1, y + 3.5);
    p.setPen(Qt::NoPen);
    p.setBrush(col);
    p.drawPolygon(tri);
    p.setBrush(Qt::NoBrush);
}

void paint_strip(QPainter& p, const StripLayout& st, const DistLayout& lay, bool is_live) {
    const QRectF band(lay.left, st.top, lay.width, kZoneH);
    for (const Zone& z : zones())
        p.fillRect(QRectF(QPointF(lay.x(z.lo), band.top()), QPointF(lay.x(z.hi), band.bottom())), z.color);

    QColor grid = c_neutral();
    grid.setAlphaF(0.7f);
    p.setPen(QPen(grid, 1.0));
    for (int k = -3; k <= 4; ++k) {
        if (k != 0)
            p.drawLine(QPointF(lay.x(k), band.top()), QPointF(lay.x(k), band.bottom()));
    }
    QPen zero(c_muted(), 1.0, Qt::DashLine);
    zero.setDashPattern({3, 3});
    p.setPen(zero);
    p.drawLine(QPointF(lay.x(0), band.top()), QPointF(lay.x(0), band.bottom()));

    // Row tag + count in the gutter.
    const QVector<DistPoint>& pts = *st.pts;
    p.setFont(mono_font(10, true));
    p.setPen(is_live ? c_ink2() : c_muted());
    p.drawText(QRectF(0, band.center().y() - 13, kDistGutter - 6, 13), Qt::AlignRight | Qt::AlignVCenter, st.tag);
    p.setFont(mono_font(9));
    p.setPen(c_muted());
    p.drawText(QRectF(0, band.center().y() + 1, kDistGutter - 6, 12), Qt::AlignRight | Qt::AlignVCenter,
               QStringLiteral("%1 mã").arg(pts.size()));

    if (pts.isEmpty()) {
        p.setFont(mono_font(11));
        p.setPen(c_muted());
        p.drawText(band, Qt::AlignCenter, QStringLiteral("— chưa có điểm σ"));
        return;
    }

    // Ticks: the crowd first, portfolio on top.
    const qreal x_min = band.left() + 1, x_max = band.right() - 1;
    QColor crowd = c_muted();
    crowd.setAlphaF(0.55f);
    for (int pass = 0; pass < 2; ++pass) {
        const bool mine_pass = pass == 1;
        for (const DistPoint& d : pts) {
            if (!has(d.s) || d.mine != mine_pass)
                continue;
            const qreal x = std::clamp(lay.x(d.s), x_min, x_max);
            const qreal top = band.top() + (mine_pass ? 5 : 14);
            const QColor col = mine_pass ? c_gold() : crowd;
            p.setPen(QPen(col, mine_pass ? 2.0 : 1.0, Qt::SolidLine, Qt::FlatCap));
            p.drawLine(QPointF(x, top), QPointF(x, band.bottom() - 4));
            if (d.s < kSigLo || d.s > kSigHi)
                draw_clamp_cap(p, x, top, d.s < kSigLo, col);
        }
    }

    // Labels under the band; a leader line joins a staggered label to its tick.
    const qreal label_top = band.bottom() + 3;
    QColor leader = c_neutral();
    leader.setAlphaF(0.8f);
    for (const PlacedLabel& l : st.labels) {
        if (l.row == 0)
            continue;
        const qreal x = std::clamp(l.x, x_min, x_max);
        p.setPen(QPen(leader, 1.0));
        p.drawLine(QPointF(x, band.bottom()), QPointF(x, label_top + l.row * kLabelRowH + 1));
    }
    p.setFont(mono_font(10, true));
    for (const PlacedLabel& l : st.labels) {
        p.setPen(sigma_color(l.s));
        p.drawText(l.rect.translated(0, label_top + l.row * kLabelRowH), Qt::AlignCenter, l.tk);
    }
}

} // namespace

// ── BandLevels ───────────────────────────────────────────────────────────────

bool BandLevels::valid() const {
    return has(cheap2) && has(cheap1) && has(fair) && has(rich1) && has(rich2) && cheap2 < cheap1 && cheap1 < fair &&
           fair < rich1 && rich1 < rich2;
}

// ── HhpBandStrip ─────────────────────────────────────────────────────────────

HhpBandStrip::HhpBandStrip(QWidget* parent) : QWidget(parent) {
    issue_.cheap2 = issue_.cheap1 = issue_.fair = issue_.rich1 = issue_.rich2 = issue_.price = kNaN;
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    setFixedHeight(kBandOneRowH);
}

void HhpBandStrip::set_bands(const BandLevels& issue, const QString& issue_tag, const BandLevels* live,
                             const QString& live_tag) {
    issue_ = issue;
    issue_tag_ = issue_tag;
    has_live_ = live != nullptr && live->valid();
    if (has_live_)
        live_ = *live;
    live_tag_ = live_tag;

    QStringList tip;
    if (issue_.valid())
        tip << issue_tag_ + QStringLiteral(": ") + band_text(issue_);
    if (has_live_)
        tip << live_tag_ + QStringLiteral(": ") + band_text(live_);
    setToolTip(tip.join(QLatin1Char('\n')));

    setFixedHeight(has_live_ ? kBandTwoRowH : kBandOneRowH);
    updateGeometry();
    update();
}

QSize HhpBandStrip::sizeHint() const {
    return {460, has_live_ ? kBandTwoRowH : kBandOneRowH};
}

QSize HhpBandStrip::minimumSizeHint() const {
    return {240, has_live_ ? kBandTwoRowH : kBandOneRowH};
}

void HhpBandStrip::paintEvent(QPaintEvent* /*event*/) {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);

    const bool issue_ok = issue_.valid();
    if (!issue_ok) {
        // The issue row keeps its place (tagged when a live row follows); the live row stays drawable.
        const qreal row_h = has_live_ ? kBandTop + kBandRowH : height();
        if (has_live_) {
            p.setFont(mono_font(10));
            p.setPen(c_muted());
            p.drawText(QRectF(0, 0, kBandGutter - 8, row_h), Qt::AlignRight | Qt::AlignVCenter, issue_tag_);
        }
        p.setFont(mono_font(11));
        p.setPen(c_muted());
        p.drawText(QRectF(kBandGutter, 0, width() - kBandGutter, row_h), Qt::AlignLeft | Qt::AlignVCenter,
                   QStringLiteral("— dải không hợp lệ"));
        if (!has_live_)
            return;
    }

    // One x-scale for both rows, padded 4% beyond the outermost band edge or price; a row whose band
    // is invalid takes no part (issue invalid → the scale comes from the live row alone).
    const BandLevels& base = issue_ok ? issue_ : live_;
    double lo = base.cheap2, hi = base.rich2;
    const auto widen = [&lo, &hi](double v) {
        if (has(v)) {
            lo = std::min(lo, v);
            hi = std::max(hi, v);
        }
    };
    widen(base.price);
    if (issue_ok && has_live_) {
        widen(live_.cheap2);
        widen(live_.rich2);
        widen(live_.price);
    }
    lo -= 0.04 * std::fabs(lo);
    hi += 0.04 * std::fabs(hi);
    const qreal plot_w = width() - kBandGutter - kBandPadR;
    if (plot_w < 40 || !(hi > lo))
        return;
    const XScale xs{lo, hi, static_cast<qreal>(kBandGutter), plot_w};

    if (issue_ok)
        paint_band_row(p, issue_, issue_tag_, c_muted(), kBandTop, xs, width());
    if (has_live_)
        paint_band_row(p, live_, live_tag_, c_ink2(), kBandTop + kBandRowH, xs, width());
}

// ── HhpSigmaDist ─────────────────────────────────────────────────────────────

HhpSigmaDist::HhpSigmaDist(QWidget* parent) : QWidget(parent) {
    setMouseTracking(true);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    setFixedHeight(dist_layout(kDefaultDistW, issue_, issue_tag_, live_, live_tag_, labels_).height);
    // Label rows depend on the width (anti-collision), so the fixed height follows resizes.
    new ResizeHook(this, [this]() {
        const int h = dist_layout(width(), issue_, issue_tag_, live_, live_tag_, labels_).height;
        if (h != height())
            setFixedHeight(h);
    });
}

void HhpSigmaDist::set_data(const QVector<DistPoint>& issue, const QString& issue_tag, const QVector<DistPoint>& live,
                            const QString& live_tag, const QStringList& labels) {
    issue_ = issue;
    issue_tag_ = issue_tag;
    live_ = live;
    live_tag_ = live_tag;
    labels_ = labels;
    const int w = width() > 100 ? width() : kDefaultDistW;
    setFixedHeight(dist_layout(w, issue_, issue_tag_, live_, live_tag_, labels_).height);
    updateGeometry();
    update();
}

QSize HhpSigmaDist::sizeHint() const {
    return {kDefaultDistW, height()};
}

QSize HhpSigmaDist::minimumSizeHint() const {
    return {320, height()};
}

void HhpSigmaDist::paintEvent(QPaintEvent* /*event*/) {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);

    const DistLayout lay = dist_layout(width(), issue_, issue_tag_, live_, live_tag_, labels_);
    for (int i = 0; i < lay.strips.size(); ++i)
        paint_strip(p, lay.strips.at(i), lay, i > 0);

    // σ axis labels and the zone legend under the last strip.
    p.setFont(mono_font(10));
    p.setPen(c_muted());
    for (int k = -3; k <= 4; ++k) {
        const QString t = k == 0 ? QStringLiteral("0σ")
                                 : (k > 0 ? QStringLiteral("+") : QStringLiteral("−")) + QString::number(std::abs(k)) +
                                       QStringLiteral("σ");
        draw_centered(p, t, lay.x(k), lay.axis_top, 14, lay.left, lay.left + lay.width);
    }
    QFont legend = mono_font(9);
    legend.setLetterSpacing(QFont::AbsoluteSpacing, 1.2);
    p.setFont(legend);
    for (const Zone& z : zones())
        draw_centered(p, QString::fromUtf8(z.name), (lay.x(z.lo) + lay.x(z.hi)) / 2, lay.axis_top + 15, 14, lay.left,
                      lay.left + lay.width);
}

void HhpSigmaDist::mouseMoveEvent(QMouseEvent* event) {
    const QPointF pos = event->position();
    const DistLayout lay = dist_layout(width(), issue_, issue_tag_, live_, live_tag_, labels_);
    QStringList lines;
    for (const StripLayout& st : lay.strips) {
        if (pos.y() < st.top || pos.y() > st.bottom())
            continue;
        QVector<std::pair<qreal, const DistPoint*>> near;
        for (const DistPoint& d : *st.pts) {
            if (!has(d.s))
                continue;
            const qreal x = std::clamp(lay.x(d.s), lay.left + 1, lay.left + lay.width - 1);
            const qreal dx = std::fabs(x - pos.x());
            if (dx <= kHoverPx)
                near.append({dx, &d});
        }
        std::stable_sort(near.begin(), near.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
        for (int i = 0; i < near.size() && i < kTipMax; ++i) {
            const DistPoint* d = near.at(i).second;
            lines << QStringLiteral("%1  %2σ (%3)").arg(d->tk, fmt_dec(d->s, 2, true), st.tag);
        }
        if (near.size() > kTipMax)
            lines << QStringLiteral("… +%1 mã").arg(near.size() - kTipMax);
        break;
    }
    if (lines.isEmpty())
        QToolTip::hideText();
    else
        QToolTip::showText(event->globalPosition().toPoint(), lines.join(QLatin1Char('\n')), this);
    QWidget::mouseMoveEvent(event);
}

} // namespace fincept::screens::hhp::weekly
