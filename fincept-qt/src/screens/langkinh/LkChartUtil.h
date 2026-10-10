// src/screens/langkinh/LkChartUtil.h
// Lăng Kính FFT — helper dùng chung của LkLineChart / LkScatterChart và chú giải hồ sơ (LkPage::make_legend).
// Tách khỏi LkChart.cpp (DELTA B7: mỗi tệp ≤ 800 dòng). hoso=false → hành vi cũ nguyên vẹn.
//
// Hợp đồng block v2 (layout "hoso" hoặc khoá mới):
//   · series "mau": tên vai hồ sơ amber · up · down · blue · violet · grey · ink2 · dim (qua lk_role/lk_col) và mọi
//     "#rrggbb". Tên cũ bull/bear/warn/info/amber/cyan/dim ngoài trang hồ sơ vẫn đi qua lk_color() như trước.
//   · series "alpha" (0..1): nhân vào độ đục của nét (line/thin/dash/dot) và của cột (bar).
//   · hoso: nền = lk_col(Surface) (trùng thẻ .fig), chữ trục mono muted, lưới màu line, dash 1,3px 3-3.
#pragma once

#include <QColor>
#include <QFont>
#include <QJsonObject>
#include <QJsonValue>
#include <QPen>
#include <QPointF>
#include <QString>
#include <QVector>

#include <algorithm>
#include <limits>

class QAbstractAxis;
class QAbstractSeries;
class QChart;
class QChartView;
class QValueAxis;

namespace fincept::screens::langkinh::lkchart {

constexpr qint64 kDayMs = 24LL * 60 * 60 * 1000;
constexpr int kMaxPointLabels = 40; // nhiều hơn thì chỉ còn tooltip, tránh rối chữ

double nan_value();
bool finite_num(const QJsonValue& v, double* out);
/// x của block: epoch ms (UTC 00:00). Chấp nhận thêm chuỗi ISO "YYYY-MM-DD" cho chắc.
bool parse_x(const QJsonValue& v, qint64* out);
/// Số kiểu Việt cho tooltip: 1.234 · 12,34 · 0,357; dấu âm "−".
QString fmt_vn(double v);
/// "(x; y)" kiểu Việt cho nhãn điểm ngoài khung.
QString fmt_pair(const QPointF& p);

/// Màu series theo "mau" (xem đầu tệp); rỗng → bảng chart_colors của theme theo thứ tự idx.
QColor series_color(const QString& mau, int idx, bool hoso = false);
/// Nét theo style (line | thin | dash | dot); alpha NaN = không đổi độ đục.
QPen pen_for(const QString& style, const QColor& base, bool hoso = false,
             double alpha = std::numeric_limits<double>::quiet_NaN());
QFont px_font(int px, bool bold = false, bool hoso = false);
void style_chart(QChart* chart, bool hoso = false);
void style_view(QChartView* v, bool hoso = false);
void style_axis(QAbstractAxis* a, bool grid, bool hoso = false);

struct Range {
    double lo = std::numeric_limits<double>::infinity();
    double hi = -std::numeric_limits<double>::infinity();
    bool bar = false;
    void add(double v) {
        lo = std::min(lo, v);
        hi = std::max(hi, v);
    }
    bool ok() const { return lo <= hi; }
};

/// Trục giá trị: min/max của block thắng số liệu; còn lại đệm nhẹ rồi làm tròn "đẹp".
QValueAxis* make_value_axis(const Range& r, const QJsonObject& cfg, bool grid, bool hoso = false);
/// Khung trục "bền" cho scatter (xem LkChartUtil.cpp).
bool robust_range(QVector<double> v, double* lo, double* hi);
void hide_legend(QChart* chart, QAbstractSeries* s);

} // namespace fincept::screens::langkinh::lkchart
