// src/screens/langkinh/LkStory.h
// Lăng Kính FFT — lớp "Câu chuyện chủ thể" của LkBlockView (CONTRACT_DELTA v4, V4.3):
//
//   story    : thẻ infographic một mã — cột "Chủ thể" (chip tên · vai trò · sở hữu · bậc), cột "Động cơ"
//              (đoạn chữ + khung "Điểm gãy" viền warn + câu hỏi mở), cột "Thước vùng giá" (dải [lo, hi],
//              vạch VWAP, tam giác "giá nay" + nhãn). vung_gia null/thiếu số → ô "[CẦN DATA] vùng giá".
//              Thẻ ≥ ~900px: 3 cột ngang; hẹp hơn: xếp dọc. Bấm thẻ (hoặc nút "Mở FFT × Giá") → on_ticker(link).
//   timeline : dòng thời gian dọc — cột ngày ("~" khi ngày ước) · chấm màu `mau` nối bằng vạch dọc (chấm rỗng
//              khi ngày ước) · khối chữ (chủ thể + hành động đậm, mô tả, giá) · chip bậc; rê chuột → tooltip `tip`.
//
// Như các block khác: chỉ ĐỌC và VẼ (không tính lại số), thiếu khoá/sai kiểu → "—" hoặc bỏ phần đó, không crash.
// Bậc UNVERIFIED luôn kèm dòng "không dùng cho quyết định". Màu lấy từ ui::colors lúc dựng (đổi theme → dựng lại).
#pragma once

#include "screens/langkinh/LkWidgets.h"

#include <QColor>
#include <QFrame>
#include <QJsonObject>
#include <QString>
#include <QStringList>
#include <Qt>

class QEvent;
class QLabel;
class QMouseEvent;
class QWidget;

namespace fincept::screens::langkinh::lkview {

/// Block "story" (V4.3). Không có tiêu đề lẫn nội dung nào → nullptr (bỏ block).
QWidget* make_story(const QJsonObject& b, QWidget* parent, const TickerFn& on_ticker);
/// Block "timeline" (V4.3). Không có mục hợp lệ → thẻ ghi "— chưa có sự kiện —". Mục có `link` (dòng thời gian
/// gộp của rổ) bấm được → on_ticker(link).
QWidget* make_timeline(const QJsonObject& b, QWidget* parent, const TickerFn& on_ticker);

} // namespace fincept::screens::langkinh::lkview

namespace fincept::screens::langkinh::lkstory {

// Helper dùng chung của story (LkStory.cpp, nơi định nghĩa) và timeline (LkTimeline.cpp).

/// Giá trị chuỗi/số của khoá (số → kiểu Việt); thiếu → "".
QString str_of(const QJsonObject& o, const char* key);
/// Bậc bằng chứng → màu chip: FACT-T1 info · FACT-T2 cyan · SS-T3 amber · UNVERIFIED warn · EST/lạ dim.
QColor tier_color(const QString& bac);
bool is_unverified(const QString& bac);
/// "UNVERIFIED — không dùng cho quyết định" (V4.0).
QString no_decision();
/// true khi bậc UNVERIFIED mà chưa chữ hiển thị nào đã mang "không dùng cho quyết định" (app script có thể đã ghép sẵn).
bool needs_no_decision(const QString& bac, const QStringList& shown);
/// Tooltip rich text từ các đoạn chữ thô (tự escape, " | " = xuống dòng); rỗng khi không có đoạn nào.
QString tip_html(const QStringList& plain_parts, const QString& head = {});
/// Nhãn xuống dòng, KHÔNG bắt chuột (bấm xuyên xuống thẻ story để mở mã).
QLabel* text_label(const QString& text, int px, const QColor& c, bool bold, QWidget* parent,
                   Qt::TextFormat fmt = Qt::PlainText);

/// Khung bấm được (thẻ story, mục timeline có `link`): nhả chuột trái trên khung hoặc con bất kỳ (trừ nút) → fn(link).
/// link rỗng → khung thường. Không có tín hiệu riêng (không cần moc).
class LinkFrame : public QFrame {
  public:
    LinkFrame(const QString& link, const lkview::TickerFn& fn, QWidget* parent);
    /// Gọi SAU khi dựng xong mọi con: gắn lọc sự kiện cho con, con trỏ bàn tay, gợi ý "Bấm để mở…" vào tooltip.
    void wire_clicks();

  protected:
    bool eventFilter(QObject* o, QEvent* e) override;
    void mousePressEvent(QMouseEvent* e) override;
    void mouseReleaseEvent(QMouseEvent* e) override;

  private:
    bool fire();
    QString link_;
    lkview::TickerFn fn_;
};

} // namespace fincept::screens::langkinh::lkstory
