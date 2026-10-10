// src/screens/langkinh/LkNumberLineDraw.h
// Lăng Kính FFT — helper vẽ NỘI BỘ của block numline (LkNumberLine.cpp định nghĩa; LkNumberLineRuler.cpp dùng lại).
// Không phải API của module: chỉ hai tệp thước include. Số kiểu Việt (dấu "−" U+2212), phông mono của LkTheme.
#pragma once

#include <QColor>
#include <QFont>
#include <QJsonObject>
#include <QPointF>
#include <QRectF>
#include <QString>
#include <QVector>
#include <Qt>

class QFontMetricsF;
class QPainter;

namespace fincept::screens::langkinh::lknumline {

constexpr int kRulerH = 164;  ///< cao thước ruler với 3 hàng nhãn mỗi phía
constexpr double kEdge = 2.0; ///< nhãn được sát mép widget tới 2px
constexpr double kGap = 8.0;  ///< khe tối thiểu giữa hai nhãn cùng hàng
constexpr double kSpan = 3.0; ///< ruler: −3σ … +3σ

/// Một hàng nhãn: đỉnh hàng + các hộp chữ đã đặt.
struct Row {
    double top = 0.0;
    QVector<QRectF> taken;
};

double nan_v();
/// Số hữu hạn của khoá; thiếu/sai kiểu → NaN.
double num(const QJsonObject& o, const char* key);
/// Nền nhạt của một màu với alpha riêng từng mức vùng σ (tối / sáng).
QColor zone(const QColor& c, bool light, double dark_a, double light_a);
QString fmt_px(double v);
QString signed_num(double v, int decimals);
QString fmt_pct(double frac);
QString fmt_sigma(double z);
QString sigma_tick(int k);
QString vwap_name(int i);
QString vwap_short(int i);
QString sigma_name(int i);
QFont ax_font();
QFont axl_font();
QFont px_font();
/// Tổng bề ngang chồng lấn (kể cả khe kGap) của r với các nhãn đã đặt trong hàng.
double overlap(const QRectF& r, const Row& row);
/// Hộp chữ rộng w: canh giữa (mặc định) / trái / phải tại x, kẹp trong bề rộng widget.
QRectF text_rect(double x, double w, double top, double h, Qt::Alignment al, double width);
/// vwap: hàng đầu tiên (theo thứ tự ưu tiên) không chồng; không có → hàng chồng ít nhất.
int best_row(const QVector<Row>& rows, const QVector<int>& prefer, double x, double w, double h, double width,
             QRectF* out);
/// ruler: hàng TRỐNG đầu tiên (gần trục trước), thử canh giữa rồi lệch trái/phải quanh chấm; không có → −1.
int free_slot(const QVector<Row>& rows, double x, double w, double h, double width, QRectF* out);
/// Vạch dọc w px, canh pixel nguyên.
void vline(QPainter& p, double x, double y0, double y1, const QColor& c, int w = 1);
void diamond(QPainter& p, const QPointF& c, double r, const QColor& fill, const QColor& edge);
/// Chấm ruler: tròn (dir 0) hoặc tam giác chĩa ra mép khi ngoài ±3σ (dir −1 trái, +1 phải).
void marker(QPainter& p, const QPointF& c, int dir, const QColor& fill, const QColor& edge);
void text_at(QPainter& p, const QRectF& r, const QFont& f, const QFontMetricsF& fm, const QColor& c,
             const QString& s);

} // namespace fincept::screens::langkinh::lknumline
