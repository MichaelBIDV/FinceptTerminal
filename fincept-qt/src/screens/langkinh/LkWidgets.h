// src/screens/langkinh/LkWidgets.h
// Lăng Kính FFT — helper dùng chung + các block không phải bảng/biểu đồ của LkBlockView
// (CONTRACT §3.1, §4): banner CỔNG · note · tiles · matrix · lists · html.
//
// Nguyên tắc như LkBlockView: chỉ ĐỌC và VẼ; thiếu khoá/sai kiểu → "—" hoặc bỏ block (trả nullptr),
// không bao giờ crash. Màu lấy từ ui::colors tại lúc dựng (LkBlockView dựng lại trang khi đổi theme).
// Tách khỏi LkBlockView.cpp để mỗi tệp ≤ 800 dòng (DELTA B7).
#pragma once

#include <QColor>
#include <QJsonObject>
#include <QJsonValue>
#include <QString>
#include <Qt>

#include <functional>

class QLabel;
class QVBoxLayout;
class QWidget;

namespace fincept::screens::langkinh::lkview {

/// Người dùng chọn một mã (chip ma trận, nhấp đúp hàng bảng có _link).
using TickerFn = std::function<void(const QString&)>;

// ── Helper chữ/số ─────────────────────────────────────────────────────────────

/// Dịch theo ngữ cảnh của LkBlockView (các hàm tự do không có tr()).
QString lk_tr(const char* text);
/// "—" (không bao giờ suy thành "trung tính").
QString dash();
/// "rgba(r,g,b,a)" cho QSS.
QString rgba(const QColor& c, int alpha);
/// Số hữu hạn từ JSON; false khi thiếu/sai kiểu/NaN.
bool num_of(const QJsonValue& v, double* out);
/// Số kiểu Việt với số chữ số thập phân cố định: 1.234,5 · dấu âm "−" (U+2212); NaN → "—".
QString vn_num(double v, int decimals);
/// Giá trị ô/nhãn: chuỗi giữ nguyên (script đã định dạng), số → kiểu Việt, thiếu → "—".
QString text_of(const QJsonValue& v);
/// Như text_of nhưng thiếu → chuỗi rỗng (phần phụ như số trên chip).
QString text_opt(const QJsonValue& v);

// ── Widget nhỏ ────────────────────────────────────────────────────────────────

QLabel* make_label(const QString& text, const char* object_name, QWidget* parent,
                   Qt::TextFormat fmt = Qt::PlainText);
QLabel* make_chip(const QString& text, const QColor& c, QWidget* parent);
/// Tiêu đề + phụ đề (title/sub) của một block, nếu có.
void add_head(QVBoxLayout* vl, const QJsonObject& b, QWidget* parent);

// ── Block (nullptr = bỏ block) ────────────────────────────────────────────────

/// Banner CỔNG: nền nhạt theo muc (ok/canh_bao/dung); thiếu dòng CỔNG → coi là "dung".
QWidget* make_banner(const QJsonValue& cong, QWidget* parent);
/// Ghi chú; khoá nội bộ `_hoso` (LkBlockView gắn ở trang layout hoso) → thẻ kiểu .fig, cao dư dồn xuống đáy.
QWidget* make_note(const QJsonObject& b, QWidget* parent);
QWidget* make_tiles(const QJsonObject& b, QWidget* parent);
QWidget* make_matrix(const QJsonObject& b, QWidget* parent, const TickerFn& on_ticker);
QWidget* make_lists(const QJsonObject& b, QWidget* parent);
QWidget* make_html(const QJsonObject& b, QWidget* parent);

} // namespace fincept::screens::langkinh::lkview
