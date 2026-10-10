// src/screens/langkinh/LkChartUtil.cpp
// Lăng Kính FFT — helper dùng chung của LkLineChart / LkScatterChart (tách khỏi LkChart.cpp để mỗi tệp ≤ 800 dòng).
// Xem LkChartUtil.h. Ngoài trang hồ sơ (hoso=false) mọi hàm giữ nguyên hành vi cũ.
#include "screens/langkinh/LkChartUtil.h"

#include "screens/langkinh/LkBlockView.h"
#include "screens/langkinh/LkTheme.h"
#include "ui/theme/Theme.h"
#include "ui/theme/ThemeManager.h"

#include <QAbstractAxis>
#include <QBrush>
#include <QChart>
#include <QChartView>
#include <QDate>
#include <QDateTime>
#include <QFont>
#include <QFrame>
#include <QGraphicsLayout>
#include <QLegend>
#include <QLegendMarker>
#include <QLocale>
#include <QPainter>
#include <QTimeZone>
#include <QValueAxis>

#include <algorithm>
#include <cmath>
#include <iterator>
#include <limits>

namespace fincept::screens::langkinh {

namespace lkchart {

double nan_value() {
    return std::numeric_limits<double>::quiet_NaN();
}

bool finite_num(const QJsonValue& v, double* out) {
    if (!v.isDouble())
        return false;
    const double d = v.toDouble();
    if (!std::isfinite(d))
        return false;
    if (out)
        *out = d;
    return true;
}

/// x của block: epoch ms (UTC 00:00). Chấp nhận thêm chuỗi ISO "YYYY-MM-DD" cho chắc.
bool parse_x(const QJsonValue& v, qint64* out) {
    double d = 0.0;
    if (finite_num(v, &d)) {
        *out = static_cast<qint64>(std::llround(d));
        return true;
    }
    if (v.isString()) {
        const QDate dt = QDate::fromString(v.toString().left(10), Qt::ISODate);
        if (dt.isValid()) {
            *out = dt.startOfDay(QTimeZone::UTC).toMSecsSinceEpoch();
            return true;
        }
    }
    return false;
}

/// Số kiểu Việt cho tooltip: 1.234 · 12,34 · 0,357; dấu âm "−".
QString fmt_vn(double v) {
    if (!std::isfinite(v))
        return QStringLiteral("—");
    const double a = std::abs(v);
    const int dec = a >= 1000.0 ? 0 : (a >= 10.0 ? 2 : 3);
    const QLocale loc(QLocale::Vietnamese, QLocale::Vietnam);
    QString s = loc.toString(a, 'f', dec);
    if (v < 0.0 && std::round(a * std::pow(10.0, dec)) > 0.0)
        s.prepend(QChar(0x2212));
    return s;
}

/// "(x; y)" kiểu Việt cho nhãn điểm ngoài khung.
QString fmt_pair(const QPointF& p) {
    return QStringLiteral("(%1; %2)").arg(fmt_vn(p.x()), fmt_vn(p.y()));
}

/// Tên màu cũ của block chart (CONTRACT §3.1) — ngoài trang hồ sơ vẫn đi qua lk_color() như trước.
bool legacy_mau(const QString& m) {
    static const char* const kOld[] = {"bull", "bear", "warn", "info", "amber", "cyan", "dim"};
    return std::any_of(std::begin(kOld), std::end(kOld), [&m](const char* k) { return m == QLatin1String(k); });
}

QColor series_color(const QString& mau, int idx, bool hoso) {
    if (!mau.isEmpty()) {
        const QString m = mau.trimmed();
        if (m.startsWith(QLatin1Char('#')) && QColor::isValidColorName(m))
            return QColor(m);
        if (!hoso && legacy_mau(m))
            return lk_color(mau);
        const lkview::LkRole r = lkview::lk_role(m, lkview::LkRole::Bg); // vai hồ sơ: amber up down blue violet …
        if (r != lkview::LkRole::Bg)
            return lkview::lk_col(r);
        return lk_color(mau); // cyan, tên lạ → như trước
    }
    const auto& pal = ui::ThemeManager::instance().tokens().chart_colors;
    return QColor(pal[static_cast<size_t>(idx) % pal.size()]);
}

QPen pen_for(const QString& style, const QColor& base, bool hoso, double alpha) {
    QPen p(base);
    p.setCosmetic(true);
    if (style == QLatin1String("thin")) {
        QColor c = base;
        c.setAlpha(170);
        p.setColor(c);
        p.setWidthF(1.0);
    } else if (style == QLatin1String("dash")) {
        if (hoso) { // Artifact: nét 1,3px, dash 3-3 (đơn vị dash của QPen = bề rộng nét)
            constexpr double kW = 1.3;
            p.setWidthF(kW);
            p.setDashPattern({3.0 / kW, 3.0 / kW});
        } else {
            p.setWidthF(1.5);
            p.setStyle(Qt::DashLine);
        }
    } else if (style == QLatin1String("dot")) {
        p.setWidthF(1.6);
        p.setStyle(Qt::DotLine);
    } else {
        p.setWidthF(2.0);
    }
    if (std::isfinite(alpha)) { // "alpha" của series (hợp đồng v2) nhân vào độ đục sẵn có của nét
        QColor c = p.color();
        c.setAlphaF(static_cast<float>(c.alphaF() * std::clamp(alpha, 0.05, 1.0)));
        p.setColor(c);
    }
    return p;
}

QFont px_font(int px, bool bold, bool hoso) {
    if (hoso)
        return lkview::lk_font_mono(px, bold ? 600 : 400);
    QFont f;
    f.setPixelSize(px);
    f.setBold(bold);
    return f;
}

void style_chart(QChart* chart, bool hoso) {
    using namespace ui::colors;
    chart->setBackgroundBrush(hoso ? lkview::lk_col(lkview::LkRole::Surface) : QColor(BG_SURFACE()));
    chart->setBackgroundPen(Qt::NoPen);
    chart->setBackgroundRoundness(0);
    chart->setPlotAreaBackgroundVisible(false);
    chart->setMargins(QMargins(4, 4, 4, 4));
    chart->setAnimationOptions(QChart::NoAnimation);
    // Nhãn trục số kiểu Việt (100.000 · 0,50) thay vì printf "100000" / "0.50".
    chart->setLocalizeNumbers(true);
    chart->setLocale(QLocale(QLocale::Vietnamese, QLocale::Vietnam));
    if (chart->layout())
        chart->layout()->setContentsMargins(0, 0, 0, 0);
    QLegend* lg = chart->legend();
    lg->setAlignment(Qt::AlignBottom);
    lg->setLabelColor(QColor(TEXT_SECONDARY()));
    lg->setFont(px_font(10));
    lg->setBackgroundVisible(false);
    if (hoso) { // ô chú giải theo nét của series, chữ sans ink2 (khi block không có "legend" riêng)
        lg->setMarkerShape(QLegend::MarkerShapeFromSeries);
        lg->setLabelColor(lkview::lk_col(lkview::LkRole::Ink2));
        lg->setFont(lkview::lk_font_sans(11));
    }
}

void style_view(QChartView* v, bool hoso) {
    v->setRenderHint(QPainter::Antialiasing, true);
    v->setFrameShape(QFrame::NoFrame);
    v->setBackgroundBrush(hoso ? lkview::lk_col(lkview::LkRole::Surface) : QColor(ui::colors::BG_SURFACE()));
    v->setMouseTracking(true);
    v->setMinimumHeight(160);
}

void style_axis(QAbstractAxis* a, bool grid, bool hoso) {
    using namespace ui::colors;
    a->setLabelsFont(px_font(10, false, hoso));
    a->setLabelsColor(hoso ? lkview::lk_col(lkview::LkRole::Muted) : QColor(TEXT_SECONDARY()));
    a->setLinePenColor(hoso ? lkview::lk_col(lkview::LkRole::Line) : QColor(BORDER_MED()));
    a->setGridLineColor(hoso ? lkview::lk_col(lkview::LkRole::Line) : QColor(BORDER_DIM()));
    a->setGridLineVisible(grid);
    a->setMinorGridLineVisible(false);
    a->setTitleFont(px_font(10, false, hoso));
    a->setTitleBrush(QBrush(hoso ? lkview::lk_col(lkview::LkRole::Muted) : QColor(TEXT_SECONDARY())));
}

/// Số chữ số thập phân ít nhất (0…3) biểu diễn đúng bước vạch: 5 → 0 · 0,1 → 1 · 0,25 → 2 · 0,002 → 3.
int step_decimals(double step) {
    if (!(step > 0.0) || !std::isfinite(step))
        return 2;
    for (int d = 0; d <= 3; ++d) {
        const double k = step * std::pow(10.0, d);
        if (std::abs(k - std::round(k)) < 1e-6 * std::max(1.0, k))
            return d;
    }
    return 3;
}

/// Trục giá trị: min/max của block thắng số liệu; còn lại đệm nhẹ rồi làm tròn "đẹp".
QValueAxis* make_value_axis(const Range& r, const QJsonObject& cfg, bool grid, bool hoso) {
    auto* a = new QValueAxis;
    a->setTitleText(cfg.value(QStringLiteral("label")).toString());
    double lo = r.ok() ? r.lo : 0.0;
    double hi = r.ok() ? r.hi : 1.0;
    if (r.bar) {
        lo = std::min(lo, 0.0);
        hi = std::max(hi, 0.0);
    }
    double fmin = 0.0;
    double fmax = 0.0;
    const bool has_min = finite_num(cfg.value(QStringLiteral("min")), &fmin);
    const bool has_max = finite_num(cfg.value(QStringLiteral("max")), &fmax);
    if (has_min)
        lo = fmin;
    if (has_max)
        hi = fmax;
    double span = hi - lo;
    if (!(span > 0.0)) {
        span = std::abs(hi) > 0.0 ? std::abs(hi) * 0.2 : 1.0;
        if (!has_min)
            lo -= span / 2.0;
        hi = lo + span;
    }
    if (!has_max)
        hi += span * 0.06;
    if (!has_min) {
        const double nlo = lo - span * 0.04;
        lo = (lo >= 0.0 && nlo < 0.0) ? 0.0 : nlo;
    }
    if (hoso && !has_min && !has_max && hi - lo < 0.01) { // chuỗi phẳng (vd sở hữu ngoại 0,0002%): khung ≥ 0,01 để
        const double mid = (lo + hi) / 2.0;                    // nhãn 3 chữ số còn phân biệt, không in 6 lần "0,000"
        const bool nonneg = lo >= 0.0;
        lo = mid - 0.005;
        hi = mid + 0.005;
        if (nonneg && lo < 0.0) {
            hi -= lo;
            lo = 0.0;
        }
    }
    a->setRange(lo, hi);
    a->applyNiceNumbers();
    if (has_min && a->min() < fmin)
        a->setMin(fmin);
    if (has_max && a->max() > fmax)
        a->setMax(fmax);
    const double s = a->max() - a->min();
    if (hoso) // hồ sơ: số chữ số thập phân theo BƯỚC vạch (0,1 → 1 chữ số) — không in "20,300" (dễ đọc thành nghìn)
        a->setLabelFormat(QStringLiteral("%.%1f").arg(step_decimals(s / std::max(1, a->tickCount() - 1))));
    else
        a->setLabelFormat(s >= 50.0 ? QStringLiteral("%.0f")
                                    : (s >= 5.0 ? QStringLiteral("%.1f")
                                                : (s >= 0.5 ? QStringLiteral("%.2f") : QStringLiteral("%.3f"))));
    style_axis(a, grid, hoso);
    return a;
}

/// Khung trục "bền" cho scatter: vài điểm cực đoan (ngoài [P2, P98] nới 25%) không được ép cụm chính thành
/// một chấm. Luôn chứa 0. false = không cần (ít điểm, hoặc dải đầy đủ chưa rộng gấp đôi dải bền).
bool robust_range(QVector<double> v, double* lo, double* hi) {
    const int n = static_cast<int>(v.size());
    if (n < 12)
        return false;
    std::sort(v.begin(), v.end());
    const auto q = [&](double p) {
        const double idx = p * (n - 1);
        const int i = static_cast<int>(std::floor(idx));
        const double f = idx - i;
        return i + 1 < n ? v[i] * (1.0 - f) + v[i + 1] * f : v[i];
    };
    const double a = q(0.02);
    const double b = q(0.98);
    const double pad = (b - a) * 0.25;
    const double full_lo = std::min(v.front(), 0.0);
    const double full_hi = std::max(v.back(), 0.0);
    const double rlo = std::max(full_lo, std::min(0.0, a - pad));
    const double rhi = std::min(full_hi, std::max(0.0, b + pad));
    if (!(rhi > rlo) || !(full_hi - full_lo > 2.0 * (rhi - rlo)))
        return false;
    *lo = rlo;
    *hi = rhi;
    return true;
}

void hide_legend(QChart* chart, QAbstractSeries* s) {
    const QList<QLegendMarker*> ms = chart->legend()->markers(s);
    for (QLegendMarker* m : ms)
        m->setVisible(false);
}

} // namespace lkchart

} // namespace fincept::screens::langkinh
