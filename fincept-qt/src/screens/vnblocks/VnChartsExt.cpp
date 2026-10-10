// src/screens/vnblocks/VnChartsExt.cpp
// Self-painted categorical-bar and numeric-XY charts for vnblocks "bieu_do" cards (contract in VnChartsExt.h).
// No QtCharts: plain QPainter so bars can carry per-bar colours, value labels and reference lines, and XY
// points can carry text labels with simple anti-overlap. Colours are read from the theme at paint time.
// Private helpers live in an anonymous namespace with a "vce_" prefix (unity-build safety).
#include "screens/vnblocks/VnChartsExt.h"

#include "screens/sgi_fa/SgiCommon.h"
#include "screens/vnblocks/VnBlocks.h"

#include <QFontMetrics>
#include <QHelpEvent>
#include <QJsonArray>
#include <QJsonValue>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPen>
#include <QToolTip>

#include <algorithm>
#include <cmath>
#include <limits>

namespace fincept::screens::vnblocks {

namespace {

using namespace fincept::screens::sgi;
namespace lkv = fincept::screens::langkinh::lkview;

constexpr double kVceNaN = std::numeric_limits<double>::quiet_NaN();
constexpr int kVceLegendH = 18;
constexpr int kVceHoverPx = 14;

bool vce_num(const QJsonValue& v, double* out) {
    if (!v.isDouble())
        return false;
    const double d = v.toDouble();
    if (!std::isfinite(d))
        return false;
    *out = d;
    return true;
}

QColor vce_palette(int idx) {
    static const Role roles[] = {Role::Blue, Role::Amber, Role::Up, Role::Violet, Role::Down, Role::Grey};
    return col(roles[((idx % 6) + 6) % 6]);
}

QColor vce_color(const QString& mau, int idx) {
    const QString m = mau.trimmed();
    if (m.startsWith(QLatin1Char('#'))) {
        const QColor c(m);
        if (c.isValid())
            return c;
    }
    static const QStringList keys = {QStringLiteral("xanh"), QStringLiteral("vang"), QStringLiteral("do"),
                                      QStringLiteral("xam"), QStringLiteral("lam"), QStringLiteral("tim")};
    if (keys.contains(m))
        return colour(m);
    return vce_palette(idx);
}

/// Vietnamese number: decimal comma, thousands dot, U+2212 minus.
QString vce_fmt(double v, int dec, bool sign = false, const QString& unit = {}) {
    if (!std::isfinite(v))
        return QStringLiteral("n/a");
    QString s = QString::number(std::abs(v), 'f', std::max(0, dec));
    const int dot = static_cast<int>(s.indexOf(QLatin1Char('.')));
    QString ip = dot >= 0 ? s.left(dot) : s;
    const QString fp = dot >= 0 ? s.mid(dot + 1) : QString();
    for (int i = static_cast<int>(ip.size()) - 3; i > 0; i -= 3)
        ip.insert(i, QLatin1Char('.'));
    s = fp.isEmpty() ? ip : ip + QLatin1Char(',') + fp;
    const bool zero = std::abs(v) < 0.5 * std::pow(10.0, -std::max(0, dec));
    if (v < 0 && !zero)
        s.prepend(QChar(0x2212));
    else if (sign && v > 0 && !zero)
        s.prepend(QLatin1Char('+'));
    return s + unit;
}

/// ~n "nice" ticks covering [lo, hi].
QVector<double> vce_ticks(double lo, double hi, int n = 5) {
    QVector<double> t;
    if (!(hi > lo))
        return t;
    const double raw = (hi - lo) / std::max(1, n);
    const double mag = std::pow(10.0, std::floor(std::log10(raw)));
    const double f = raw / mag;
    const double step = (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * mag;
    for (double v = std::ceil(lo / step) * step; v <= hi + step * 1e-9; v += step)
        t.append(std::abs(v) < step * 1e-9 ? 0.0 : v);
    return t;
}

int vce_tick_dec(const QVector<double>& t) {
    if (t.size() < 2)
        return 1;
    const double step = std::abs(t[1] - t[0]);
    return step >= 1 ? 0 : step >= 0.1 ? 1 : 2;
}

struct VceRef {
    double v = kVceNaN;
    QString text;
    QColor color;
};

QVector<VceRef> vce_refs(const QJsonArray& arr) {
    QVector<VceRef> out;
    for (const QJsonValue& x : arr) {
        const QJsonObject o = x.toObject();
        VceRef r;
        if (!vce_num(o.value(QStringLiteral("v")), &r.v))
            continue;
        r.text = o.value(QStringLiteral("text")).toString();
        r.color = vce_color(o.value(QStringLiteral("mau")).toString(QStringLiteral("xam")), 5);
        out.append(r);
    }
    return out;
}

void vce_legend(QPainter& p, const QRect& area, const QVector<QPair<QString, QColor>>& items) {
    if (items.size() < 2)
        return;
    p.setFont(lkv::lk_font_sans(11));
    const QFontMetrics fm(p.font());
    int x = area.left();
    for (const auto& [name, c] : items) {
        p.fillRect(QRect(x, area.top() + 5, 10, 10), c);
        p.setPen(col(Role::Ink2));
        p.drawText(x + 14, area.top() + 14, name);
        x += 14 + fm.horizontalAdvance(name) + 16;
    }
}

void vce_dashed(QPainter& p, const QColor& c, const QPointF& a, const QPointF& b) {
    QPen pen(c, 1.0, Qt::DashLine);
    p.setPen(pen);
    p.drawLine(a, b);
}

// ═════════════════════════════════════════════════════════════════════════════
// Bars
// ═════════════════════════════════════════════════════════════════════════════

class VceBarChart : public QWidget {
  public:
    explicit VceBarChart(const QJsonObject& b, QWidget* parent) : QWidget(parent) {
        setMouseTracking(true);
        setMinimumHeight(160);
        horizontal_ = b.value(QStringLiteral("huong")).toString() != QLatin1String("doc");
        for (const QJsonValue& v : b.value(QStringLiteral("nhan")).toArray())
            cats_.append(v.toString());
        for (const QJsonValue& v : b.value(QStringLiteral("nhan_phu")).toArray())
            cats2_.append(v.toString());
        const QJsonArray ser = b.value(QStringLiteral("series")).toArray();
        for (int si = 0; si < ser.size(); ++si) {
            const QJsonObject so = ser.at(si).toObject();
            Ser s;
            s.name = so.value(QStringLiteral("name")).toString();
            s.mau = so.value(QStringLiteral("mau")).toString();
            s.idx = si;
            const QJsonArray ys = so.value(QStringLiteral("y")).toArray();
            const QJsonArray per = so.value(QStringLiteral("mau_tung")).toArray();
            for (int i = 0; i < cats_.size(); ++i) {
                double d = kVceNaN;
                if (i < ys.size())
                    vce_num(ys.at(i), &d);
                s.y.append(d);
                s.per.append(i < per.size() ? per.at(i).toString() : QString());
                if (std::isfinite(d))
                    has_ = true;
            }
            series_.append(s);
        }
        show_values_ = b.value(QStringLiteral("gia_tri")).toBool(true);
        unit_ = b.value(QStringLiteral("dv")).toString();
        dec_ = b.value(QStringLiteral("so_le")).toInt(1);
        sign_ = b.value(QStringLiteral("dau")).toBool(false);
        refs_ = vce_refs(b.value(QStringLiteral("vach")).toArray());
        const QJsonObject ax = b.value(QStringLiteral("truc")).toObject();
        axis_label_ = ax.value(QStringLiteral("label")).toString();
        vce_num(ax.value(QStringLiteral("min")), &fix_lo_);
        vce_num(ax.value(QStringLiteral("max")), &fix_hi_);
    }
    bool has_data() const { return has_; }

  protected:
    void paintEvent(QPaintEvent*) override {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);
        hits_.clear();
        const QRect full = rect().adjusted(2, 2, -2, -2);
        int top = full.top();
        QVector<QPair<QString, QColor>> leg;
        for (const Ser& s : series_)
            leg.append({s.name, vce_color(s.mau, s.idx)});
        if (series_.size() > 1) {
            vce_legend(p, QRect(full.left(), top, full.width(), kVceLegendH), leg);
            top += kVceLegendH + 4;
        }
        // value range (always include 0 and the reference lines)
        double lo = 0.0, hi = 0.0;
        for (const Ser& s : series_)
            for (double v : s.y)
                if (std::isfinite(v)) {
                    lo = std::min(lo, v);
                    hi = std::max(hi, v);
                }
        for (const VceRef& r : refs_) {
            lo = std::min(lo, r.v);
            hi = std::max(hi, r.v);
        }
        if (std::isfinite(fix_lo_))
            lo = fix_lo_;
        if (std::isfinite(fix_hi_))
            hi = fix_hi_;
        if (!(hi > lo))
            hi = lo + 1.0;
        const double pad = (hi - lo) * 0.06;
        if (!std::isfinite(fix_lo_) && lo < 0)
            lo -= pad;
        if (!std::isfinite(fix_hi_))
            hi += pad;
        const QVector<double> ticks = vce_ticks(lo, hi, horizontal_ ? 6 : 5);
        const int tdec = vce_tick_dec(ticks);

        p.setFont(lkv::lk_font_sans(11));
        const QFontMetrics fm(p.font());
        const QFont mono = lkv::lk_font_mono(11);
        const QFontMetrics fmm(mono);
        const int n = static_cast<int>(cats_.size());
        if (n == 0)
            return;
        const int ns = std::max(1, static_cast<int>(series_.size()));
        // bars start at 0 when 0 is on the axis, else at the axis edge nearest to 0; values clamp to the axis
        const double base = std::clamp(0.0, lo, hi);
        const auto clampv = [&](double v) { return std::clamp(v, lo, hi); };

        if (horizontal_) {
            int lw = 0;
            for (const QString& c : cats_)
                lw = std::max(lw, fm.horizontalAdvance(c));
            lw = std::min(lw + 10, full.width() / 3);
            int vw_pos = 0, vw_neg = 0; // value-label room right of positive bars / left of negative bars
            if (show_values_)
                for (const Ser& s : series_)
                    for (int i = 0; i < n; ++i) {
                        if (!std::isfinite(s.y[i]))
                            continue;
                        QString t = vce_fmt(s.y[i], dec_, sign_, unit_);
                        if (i < cats2_.size() && !cats2_[i].isEmpty())
                            t += QStringLiteral("  ") + cats2_[i];
                        int& w = s.y[i] >= 0 ? vw_pos : vw_neg;
                        w = std::max(w, fmm.horizontalAdvance(t) + 6);
                    }
            const QRect plot(full.left() + lw + vw_neg, top, std::max(40, full.width() - lw - vw_neg - vw_pos - 8),
                             full.bottom() - top - 30);
            const auto X = [&](double v) { return plot.left() + (v - lo) / (hi - lo) * plot.width(); };
            // grid + ticks
            for (double t : ticks) {
                const double x = X(t);
                p.setPen(QPen(col(Role::Line), 1.0));
                p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()));
                p.setPen(col(Role::Muted));
                p.setFont(mono);
                const QString lab = vce_fmt(t, tdec);
                p.drawText(QPointF(x - fmm.horizontalAdvance(lab) / 2.0, plot.bottom() + 14), lab);
            }
            if (!axis_label_.isEmpty()) {
                p.setFont(lkv::lk_font_sans(11));
                p.drawText(QRect(plot.left(), plot.bottom() + 16, plot.width(), 14), Qt::AlignHCenter, axis_label_);
            }
            p.setPen(QPen(col(Role::Ink2), 1.2));
            p.drawLine(QPointF(X(base), plot.top()), QPointF(X(base), plot.bottom()));
            const double band = static_cast<double>(plot.height()) / n;
            const double th = std::max(3.0, band * 0.72 / ns);
            for (int i = 0; i < n; ++i) {
                const double cy = plot.top() + band * (i + 0.5);
                p.setFont(lkv::lk_font_sans(11));
                p.setPen(col(Role::Ink2));
                p.drawText(QRect(full.left(), static_cast<int>(cy - 8), lw - 8, 16), Qt::AlignRight | Qt::AlignVCenter,
                           fm.elidedText(cats_[i], Qt::ElideRight, lw - 8));
                for (int si = 0; si < ns; ++si) {
                    const Ser& s = series_[si];
                    const double v = s.y[i];
                    if (!std::isfinite(v))
                        continue;
                    const double y0 = cy - th * ns / 2.0 + th * si;
                    const double x0 = X(base), x1 = X(clampv(v));
                    const QRectF r(std::min(x0, x1), y0, std::max(1.0, std::abs(x1 - x0)), th - 1);
                    const QColor c = vce_color(s.per[i].isEmpty() ? s.mau : s.per[i], s.idx);
                    p.fillRect(r, c);
                    hits_.append({r, cats_[i], s.name, v});
                    if (show_values_) {
                        QString t = vce_fmt(v, dec_, sign_, unit_);
                        if (si == 0 && i < cats2_.size() && !cats2_[i].isEmpty())
                            t += QStringLiteral("  ") + cats2_[i];
                        p.setFont(mono);
                        p.setPen(c);
                        const double tw = fmm.horizontalAdvance(t);
                        const double tx = v >= 0 ? r.right() + 4 : r.left() - 4 - tw;
                        p.drawText(QPointF(tx, r.center().y() + 4), t);
                    }
                }
            }
            for (const VceRef& r : refs_) {
                if (r.v < lo || r.v > hi)
                    continue;
                vce_dashed(p, r.color, QPointF(X(r.v), plot.top()), QPointF(X(r.v), plot.bottom()));
                p.setFont(lkv::lk_font_sans(10));
                p.setPen(r.color);
                p.drawText(QPointF(X(r.v) + 3, plot.top() + 10), r.text);
            }
        } else {
            const int lw = 52;
            const bool two = !cats2_.isEmpty();
            const QRect plot(full.left() + lw, top + (show_values_ ? 14 : 4), full.width() - lw - 8,
                             full.bottom() - top - (two ? 44 : 30) - (show_values_ ? 14 : 4) - (axis_label_.isEmpty() ? 0 : 0));
            const auto Y = [&](double v) { return plot.bottom() - (v - lo) / (hi - lo) * plot.height(); };
            for (double t : ticks) {
                const double y = Y(t);
                p.setPen(QPen(col(Role::Line), 1.0));
                p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y));
                p.setPen(col(Role::Muted));
                p.setFont(mono);
                const QString lab = vce_fmt(t, tdec);
                p.drawText(QRect(full.left(), static_cast<int>(y - 7), lw - 6, 14), Qt::AlignRight | Qt::AlignVCenter, lab);
            }
            if (!axis_label_.isEmpty()) {
                p.save();
                p.setFont(lkv::lk_font_sans(10));
                p.setPen(col(Role::Muted));
                p.translate(full.left() + 9, plot.center().y());
                p.rotate(-90);
                p.drawText(QRect(-plot.height() / 2, -8, plot.height(), 14), Qt::AlignCenter, axis_label_);
                p.restore();
            }
            p.setPen(QPen(col(Role::Ink2), 1.2));
            p.drawLine(QPointF(plot.left(), Y(base)), QPointF(plot.right(), Y(base)));
            const double band = static_cast<double>(plot.width()) / n;
            const double tw = std::max(3.0, band * 0.7 / ns);
            // crowded axis: label every k-th category so the text stays readable (tooltips still name every bar)
            int cat_w = 0;
            for (int i = 0; i < n; ++i) {
                cat_w = std::max(cat_w, fm.horizontalAdvance(cats_[i]));
                if (two && i < cats2_.size())
                    cat_w = std::max(cat_w, fm.horizontalAdvance(cats2_[i]));
            }
            const int step = std::max(1, static_cast<int>(std::ceil((cat_w + 6) / std::max(1.0, band))));
            QVector<QRectF> placed_vals; // value labels drawn so far; a label that would overlap one is skipped
            for (int i = 0; i < n; ++i) {
                const double cx = plot.left() + band * (i + 0.5);
                const bool show_cat = (i % step) == 0;
                const int cw = static_cast<int>(band * step);
                p.setFont(lkv::lk_font_sans(11));
                p.setPen(col(Role::Ink2));
                if (show_cat)
                    p.drawText(QRect(static_cast<int>(cx - cw / 2.0), plot.bottom() + 4, cw, 14), Qt::AlignHCenter,
                               fm.elidedText(cats_[i], Qt::ElideRight, cw));
                if (two && show_cat && i < cats2_.size()) {
                    p.setPen(col(Role::Muted));
                    p.drawText(QRect(static_cast<int>(cx - cw / 2.0), plot.bottom() + 18, cw, 14), Qt::AlignHCenter,
                               fm.elidedText(cats2_[i], Qt::ElideRight, cw));
                }
                for (int si = 0; si < ns; ++si) {
                    const Ser& s = series_[si];
                    const double v = s.y[i];
                    if (!std::isfinite(v))
                        continue;
                    const double x0 = cx - tw * ns / 2.0 + tw * si;
                    const double y0 = Y(base), y1 = Y(clampv(v));
                    const QRectF r(x0, std::min(y0, y1), tw - 1, std::max(1.0, std::abs(y1 - y0)));
                    const QColor c = vce_color(s.per[i].isEmpty() ? s.mau : s.per[i], s.idx);
                    p.fillRect(r, c);
                    hits_.append({r, cats_[i], s.name, v});
                    if (show_values_) {
                        const QString t = vce_fmt(v, dec_, sign_, unit_);
                        const double w = fmm.horizontalAdvance(t);
                        const QRectF lr(r.center().x() - w / 2, v >= 0 ? r.top() - 14 : r.bottom() + 1, w, 13);
                        bool clash = false;
                        for (const QRectF& q : std::as_const(placed_vals))
                            if (q.adjusted(-2, 0, 2, 0).intersects(lr)) {
                                clash = true;
                                break;
                            }
                        if (!clash) {
                            placed_vals.append(lr);
                            p.setFont(mono);
                            p.setPen(c);
                            p.drawText(QPointF(lr.left(), lr.bottom() - 2), t);
                        }
                    }
                }
            }
            for (const VceRef& r : refs_) {
                if (r.v < lo || r.v > hi)
                    continue;
                vce_dashed(p, r.color, QPointF(plot.left(), Y(r.v)), QPointF(plot.right(), Y(r.v)));
                p.setFont(lkv::lk_font_sans(10));
                const QFontMetrics fr(p.font());
                const QRectF tr(plot.left() + 4, Y(r.v) - 15, fr.horizontalAdvance(r.text) + 6, 13);
                QColor bg = col(Role::Surface);
                bg.setAlphaF(0.8f);
                p.fillRect(tr, bg); // label sits on the left, over a soft backdrop, so bars never hide it
                p.setPen(r.color);
                p.drawText(tr, Qt::AlignCenter, r.text);
            }
        }
    }

    bool event(QEvent* e) override {
        if (e->type() == QEvent::ToolTip) {
            const QPoint pos = static_cast<QHelpEvent*>(e)->pos();
            for (const Hit& h : std::as_const(hits_)) {
                if (h.r.adjusted(-2, -2, 2, 2).contains(pos)) {
                    QString t = h.cat + QStringLiteral(": ") + vce_fmt(h.v, dec_, sign_, unit_);
                    if (!h.ser.isEmpty())
                        t = h.ser + QStringLiteral(" · ") + t;
                    QToolTip::showText(static_cast<QHelpEvent*>(e)->globalPos(), t, this);
                    return true;
                }
            }
            QToolTip::hideText();
            e->ignore();
            return true;
        }
        return QWidget::event(e);
    }

  private:
    struct Ser {
        QString name, mau;
        int idx = 0;
        QVector<double> y;
        QVector<QString> per;
    };
    struct Hit {
        QRectF r;
        QString cat, ser;
        double v;
    };
    bool horizontal_ = true, has_ = false, show_values_ = true, sign_ = false;
    QVector<QString> cats_, cats2_;
    QVector<Ser> series_;
    QVector<VceRef> refs_;
    QVector<Hit> hits_;
    QString unit_, axis_label_;
    int dec_ = 1;
    double fix_lo_ = kVceNaN, fix_hi_ = kVceNaN;
};

// ═════════════════════════════════════════════════════════════════════════════
// XY
// ═════════════════════════════════════════════════════════════════════════════

struct VceAxis {
    QString label;
    double lo = kVceNaN, hi = kVceNaN;
    int dec = -1;
    QString unit;
};

VceAxis vce_axis(const QJsonObject& o) {
    VceAxis a;
    a.label = o.value(QStringLiteral("label")).toString();
    vce_num(o.value(QStringLiteral("min")), &a.lo);
    vce_num(o.value(QStringLiteral("max")), &a.hi);
    if (o.contains(QStringLiteral("so_le")))
        a.dec = o.value(QStringLiteral("so_le")).toInt(1);
    a.unit = o.value(QStringLiteral("dv")).toString();
    return a;
}

struct VceZone {
    double a = kVceNaN, b = kVceNaN;
    QColor color;
    double alpha = 0.10;
    QString text;
};

QVector<VceZone> vce_zones(const QJsonArray& arr, const char* k0, const char* k1) {
    QVector<VceZone> out;
    for (const QJsonValue& v : arr) {
        const QJsonObject o = v.toObject();
        VceZone z;
        if (!vce_num(o.value(QLatin1String(k0)), &z.a) || !vce_num(o.value(QLatin1String(k1)), &z.b))
            continue;
        z.color = vce_color(o.value(QStringLiteral("mau")).toString(), 0);
        double al = 0.10;
        if (vce_num(o.value(QStringLiteral("alpha")), &al) && al > 0 && al <= 1)
            z.alpha = al;
        z.text = o.value(QStringLiteral("text")).toString();
        out.append(z);
    }
    return out;
}

class VceXyChart : public QWidget {
  public:
    explicit VceXyChart(const QJsonObject& b, QWidget* parent) : QWidget(parent) {
        setMouseTracking(true);
        setMinimumHeight(180);
        ax_ = vce_axis(b.value(QStringLiteral("truc_x")).toObject());
        ay_ = vce_axis(b.value(QStringLiteral("truc_y")).toObject());
        const QJsonArray ser = b.value(QStringLiteral("series")).toArray();
        for (int si = 0; si < ser.size(); ++si) {
            const QJsonObject so = ser.at(si).toObject();
            Ser s;
            s.name = so.value(QStringLiteral("name")).toString();
            s.kind = so.value(QStringLiteral("kieu")).toString(QStringLiteral("duong"));
            s.color = vce_color(so.value(QStringLiteral("mau")).toString(), si);
            s.size = so.value(QStringLiteral("co")).toDouble(6.0);
            const QJsonArray xs = so.value(QStringLiteral("x")).toArray();
            const QJsonArray ys = so.value(QStringLiteral("y")).toArray();
            const QJsonArray ls = so.value(QStringLiteral("nhan")).toArray();
            const int m = static_cast<int>(std::min(xs.size(), ys.size()));
            for (int i = 0; i < m; ++i) {
                double x = kVceNaN, y = kVceNaN;
                vce_num(xs.at(i), &x);
                vce_num(ys.at(i), &y);
                s.x.append(x);
                s.y.append(y);
                s.lab.append(i < ls.size() ? ls.at(i).toString() : QString());
                if (std::isfinite(x) && std::isfinite(y))
                    has_ = true;
            }
            series_.append(s);
        }
        rx_ = vce_refs(b.value(QStringLiteral("vach_x")).toArray());
        ry_ = vce_refs(b.value(QStringLiteral("vach_y")).toArray());
        zx_ = vce_zones(b.value(QStringLiteral("vung_x")).toArray(), "x0", "x1");
        zy_ = vce_zones(b.value(QStringLiteral("vung_y")).toArray(), "y0", "y1");
    }
    bool has_data() const { return has_; }

  protected:
    void paintEvent(QPaintEvent*) override {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);
        pts_.clear();
        const QRect full = rect().adjusted(2, 2, -2, -2);
        int top = full.top();
        QVector<QPair<QString, QColor>> leg;
        for (const Ser& s : series_)
            if (!s.name.isEmpty())
                leg.append({s.name, s.color});
        if (leg.size() > 1) {
            vce_legend(p, QRect(full.left(), top, full.width(), kVceLegendH), leg);
            top += kVceLegendH + 4;
        }
        double xl = std::numeric_limits<double>::max(), xh = -xl, yl = xl, yh = -xl;
        for (const Ser& s : series_)
            for (int i = 0; i < s.x.size(); ++i)
                if (std::isfinite(s.x[i]) && std::isfinite(s.y[i])) {
                    xl = std::min(xl, s.x[i]);
                    xh = std::max(xh, s.x[i]);
                    yl = std::min(yl, s.y[i]);
                    yh = std::max(yh, s.y[i]);
                }
        for (const VceRef& r : ry_) {
            yl = std::min(yl, r.v);
            yh = std::max(yh, r.v);
        }
        if (!(xh >= xl)) {
            xl = 0;
            xh = 1;
        }
        if (!(yh >= yl)) {
            yl = 0;
            yh = 1;
        }
        const double xp = (xh - xl) * 0.04, yp = (yh - yl) * 0.08;
        double x0 = std::isfinite(ax_.lo) ? ax_.lo : xl - xp, x1 = std::isfinite(ax_.hi) ? ax_.hi : xh + xp;
        double y0 = std::isfinite(ay_.lo) ? ay_.lo : yl - yp, y1 = std::isfinite(ay_.hi) ? ay_.hi : yh + yp;
        if (!(x1 > x0))
            x1 = x0 + 1;
        if (!(y1 > y0))
            y1 = y0 + 1;
        const QRect plot(full.left() + 54, top + 4, full.width() - 54 - 10, full.bottom() - top - 4 - 34);
        const auto X = [&](double v) { return plot.left() + (v - x0) / (x1 - x0) * plot.width(); };
        const auto Y = [&](double v) { return plot.bottom() - (v - y0) / (y1 - y0) * plot.height(); };
        p.save();
        p.setClipRect(plot);
        for (const VceZone& z : zx_) {
            QColor c = z.color;
            c.setAlphaF(static_cast<float>(z.alpha));
            const QRectF r(QPointF(X(std::max(z.a, x0)), plot.top()), QPointF(X(std::min(z.b, x1)), plot.bottom()));
            p.fillRect(r.normalized(), c);
            if (!z.text.isEmpty()) {
                p.setFont(lkv::lk_font_sans(10));
                QColor tc = z.color;
                p.setPen(tc);
                p.drawText(r.normalized().adjusted(4, 0, -2, -4), Qt::AlignHCenter | Qt::AlignBottom, z.text);
            }
        }
        for (const VceZone& z : zy_) {
            QColor c = z.color;
            c.setAlphaF(static_cast<float>(z.alpha));
            const QRectF r(QPointF(plot.left(), Y(std::min(z.b, y1))), QPointF(plot.right(), Y(std::max(z.a, y0))));
            p.fillRect(r.normalized(), c);
            if (!z.text.isEmpty()) {
                p.setFont(lkv::lk_font_sans(10));
                p.setPen(z.color);
                p.drawText(r.normalized().adjusted(4, 2, -4, 0), Qt::AlignLeft | Qt::AlignTop, z.text);
            }
        }
        p.restore();
        const QFont mono = lkv::lk_font_mono(11);
        const QFontMetrics fmm(mono);
        const QVector<double> tx = vce_ticks(x0, x1, 6), ty = vce_ticks(y0, y1, 5);
        const int dx = ax_.dec >= 0 ? ax_.dec : vce_tick_dec(tx), dy = ay_.dec >= 0 ? ay_.dec : vce_tick_dec(ty);
        for (double t : tx) {
            p.setPen(QPen(col(Role::Line), 1.0));
            p.drawLine(QPointF(X(t), plot.top()), QPointF(X(t), plot.bottom()));
            p.setPen(col(Role::Muted));
            p.setFont(mono);
            const QString lab = vce_fmt(t, dx, false, ax_.unit);
            p.drawText(QPointF(X(t) - fmm.horizontalAdvance(lab) / 2.0, plot.bottom() + 14), lab);
        }
        for (double t : ty) {
            p.setPen(QPen(col(Role::Line), 1.0));
            p.drawLine(QPointF(plot.left(), Y(t)), QPointF(plot.right(), Y(t)));
            p.setPen(col(Role::Muted));
            p.setFont(mono);
            p.drawText(QRect(full.left(), static_cast<int>(Y(t) - 7), 48, 14), Qt::AlignRight | Qt::AlignVCenter,
                       vce_fmt(t, dy, false, ay_.unit));
        }
        p.setFont(lkv::lk_font_sans(11));
        p.setPen(col(Role::Muted));
        if (!ax_.label.isEmpty())
            p.drawText(QRect(plot.left(), plot.bottom() + 17, plot.width(), 14), Qt::AlignHCenter, ax_.label);
        if (!ay_.label.isEmpty()) {
            p.save();
            p.setFont(lkv::lk_font_sans(10));
            p.translate(full.left() + 6, plot.center().y());
            p.rotate(-90);
            p.drawText(QRect(-plot.height() / 2, -8, plot.height(), 14), Qt::AlignCenter, ay_.label);
            p.restore();
        }
        for (const VceRef& r : rx_) {
            if (r.v < x0 || r.v > x1)
                continue;
            vce_dashed(p, r.color, QPointF(X(r.v), plot.top()), QPointF(X(r.v), plot.bottom()));
            p.setFont(lkv::lk_font_sans(10));
            p.setPen(r.color);
            p.drawText(QPointF(X(r.v) + 3, plot.top() + 10), r.text);
        }
        for (const VceRef& r : ry_) {
            if (r.v < y0 || r.v > y1)
                continue;
            vce_dashed(p, r.color, QPointF(plot.left(), Y(r.v)), QPointF(plot.right(), Y(r.v)));
            p.setFont(lkv::lk_font_sans(10));
            p.setPen(r.color);
            const QFontMetrics fm(p.font());
            p.drawText(QPointF(plot.right() - fm.horizontalAdvance(r.text) - 2, Y(r.v) - 3), r.text);
        }
        // series
        QVector<QRectF> placed;
        p.save();
        p.setClipRect(plot.adjusted(-4, -4, 4, 4));
        for (const Ser& s : series_) {
            const bool dots = s.kind == QLatin1String("diem");
            if (!dots) {
                QPen pen(s.color, 2.0);
                if (s.kind == QLatin1String("net"))
                    pen.setStyle(Qt::DashLine);
                p.setPen(pen);
                QPainterPath path;
                bool open = false;
                for (int i = 0; i < s.x.size(); ++i) {
                    if (!std::isfinite(s.x[i]) || !std::isfinite(s.y[i])) {
                        open = false;
                        continue;
                    }
                    const QPointF q(X(s.x[i]), Y(s.y[i]));
                    if (!open) {
                        path.moveTo(q);
                        open = true;
                    } else {
                        path.lineTo(q);
                    }
                }
                p.drawPath(path);
            }
            for (int i = 0; i < s.x.size(); ++i) {
                if (!std::isfinite(s.x[i]) || !std::isfinite(s.y[i]))
                    continue;
                const QPointF q(X(s.x[i]), Y(s.y[i]));
                pts_.append({q, s.name, s.x[i], s.y[i], s.lab[i]});
                if (dots) {
                    QColor f = s.color;
                    f.setAlphaF(0.55f);
                    p.setPen(QPen(s.color, 1.0));
                    p.setBrush(f);
                    p.drawEllipse(q, s.size / 2.0, s.size / 2.0);
                    p.setBrush(Qt::NoBrush);
                }
            }
        }
        p.restore();
        // point labels with simple anti-overlap (try 4 offsets, skip when all collide)
        p.setFont(lkv::lk_font_sans(10));
        const QFontMetrics fl(p.font());
        // later series are the highlighted ones (e.g. portfolio over "all tickers"): label them first so they win collisions
        for (auto it = series_.crbegin(); it != series_.crend(); ++it) {
            const Ser& s = *it;
            for (int i = 0; i < s.x.size(); ++i) {
                if (s.lab[i].isEmpty() || !std::isfinite(s.x[i]) || !std::isfinite(s.y[i]))
                    continue;
                const QPointF q(X(s.x[i]), Y(s.y[i]));
                const int w = fl.horizontalAdvance(s.lab[i]) + 6, h = 14;
                const QPointF offs[] = {{6, -h - 2.0}, {6, 2}, {-w - 6.0, -h - 2.0}, {-w - 6.0, 2}};
                for (const QPointF& o : offs) {
                    const QRectF r(q + o, QSizeF(w, h));
                    if (!plot.contains(r.toRect()))
                        continue;
                    bool clash = false;
                    for (const QRectF& pr : std::as_const(placed))
                        if (pr.intersects(r)) {
                            clash = true;
                            break;
                        }
                    if (clash)
                        continue;
                    placed.append(r);
                    QColor bg = col(Role::Surface);
                    bg.setAlphaF(0.85f);
                    p.fillRect(r, bg);
                    p.setPen(s.color);
                    p.drawText(r, Qt::AlignCenter, s.lab[i]);
                    break;
                }
            }
        }
    }

    bool event(QEvent* e) override {
        if (e->type() == QEvent::ToolTip) {
            const QPoint pos = static_cast<QHelpEvent*>(e)->pos();
            const Pt* best = nullptr;
            double bd = kVceHoverPx;
            for (const Pt& pt : std::as_const(pts_)) {
                const double d = std::hypot(pt.q.x() - pos.x(), pt.q.y() - pos.y());
                if (d < bd) {
                    bd = d;
                    best = &pt;
                }
            }
            if (best) {
                QString t = (best->lab.isEmpty() ? QString() : best->lab + QStringLiteral(" · ")) +
                            (best->ser.isEmpty() ? QString() : best->ser + QStringLiteral(": ")) +
                            (ax_.label.isEmpty() ? QStringLiteral("x") : ax_.label) + QStringLiteral(" ") +
                            vce_fmt(best->x, ax_.dec >= 0 ? ax_.dec : 2, false, ax_.unit) + QStringLiteral(" · ") +
                            (ay_.label.isEmpty() ? QStringLiteral("y") : ay_.label) + QStringLiteral(" ") +
                            vce_fmt(best->y, ay_.dec >= 0 ? ay_.dec : 2, false, ay_.unit);
                QToolTip::showText(static_cast<QHelpEvent*>(e)->globalPos(), t, this);
                return true;
            }
            QToolTip::hideText();
            e->ignore();
            return true;
        }
        return QWidget::event(e);
    }

  private:
    struct Ser {
        QString name, kind;
        QColor color;
        double size = 6.0;
        QVector<double> x, y;
        QVector<QString> lab;
    };
    struct Pt {
        QPointF q;
        QString ser;
        double x, y;
        QString lab;
    };
    VceAxis ax_, ay_;
    QVector<Ser> series_;
    QVector<VceRef> rx_, ry_;
    QVector<VceZone> zx_, zy_;
    QVector<Pt> pts_;
    bool has_ = false;
};

} // namespace

bool is_ext_chart(const QJsonObject& block) {
    const QString l = block.value(QStringLiteral("loai")).toString();
    return l == QLatin1String("cot") || l == QLatin1String("xy");
}

QWidget* make_ext_chart(const QJsonObject& block, QWidget* parent) {
    if (block.value(QStringLiteral("loai")).toString() == QLatin1String("cot"))
        return new VceBarChart(block, parent);
    return new VceXyChart(block, parent);
}

bool has_ext_chart_data(const QWidget* chart) {
    if (const auto* b = dynamic_cast<const VceBarChart*>(chart))
        return b->has_data();
    if (const auto* x = dynamic_cast<const VceXyChart*>(chart))
        return x->has_data();
    return false;
}

} // namespace fincept::screens::vnblocks
