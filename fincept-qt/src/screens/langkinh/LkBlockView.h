// src/screens/langkinh/LkBlockView.h
// Lăng Kính FFT — bộ vẽ "trang" do scripts/fincept_langkinh.py dựng (CONTRACT §3.1, §4).
//
// Một payload = banner CỔNG (luôn nằm trên cùng) + tiêu đề + dãy block:
//   note · tiles · table · matrix · lists · html · chart · scatter · story · timeline (DELTA v4)
//   kpis · pillars · numline · rrg · cards · chips · tkhead · row (hồ sơ — LK_HOSO_SPEC §6, hợp đồng block v2)
//   sodo · cotmoc (thấu kính NTH — lk_mauhinh/1)
// Hợp đồng block v2: payload "layout":"hoso" → cột trang 1180px, banner .gate, bảng/biểu đồ trong thẻ .fig;
// block bất kỳ có "eyebrow" → đầu phần .sec-head; "b" → tag bậc cạnh tiêu đề (xem LkPage.h). Vắng layout hoso
// và vắng khoá mới → trang cũ (tongquan, chuoi, …) vẽ y như trước.
// Bộ vẽ KHÔNG tính lại số nào: chỉ đọc JSON. Thiếu khoá hoặc sai kiểu → hiển thị "—" hoặc bỏ
// block đó, không bao giờ crash. Mỗi lần set_payload() toàn bộ widget cũ bị huỷ (deleteLater).
// Tệp con (DELTA B7): LkWidgets (banner CỔNG, note, tiles, matrix, lists, html + helper chung),
// LkTableBlock (bảng + delegate), LkChart/LkChartUtil (chart, scatter), LkStory/LkTimeline (story, timeline),
// LkPage (khung trang hồ sơ, row, đầu phần), LkLayouts (layout tự viết).
#pragma once

#include <QColor>
#include <QJsonObject>
#include <QScrollArea>
#include <QString>

namespace fincept::screens::langkinh {

/// Thẻ ngữ nghĩa "mau" (bull|bear|warn|info|amber|dim|cyan|"") → màu của theme ĐANG dùng.
/// bull→POSITIVE, bear→NEGATIVE, warn→WARNING, info→INFO, amber→AMBER, cyan→CYAN,
/// dim→TEXT_SECONDARY, ""/lạ→TEXT_PRIMARY.
QColor lk_color(const QString& mau);

class LkBlockView : public QScrollArea {
    Q_OBJECT
  public:
    explicit LkBlockView(QWidget* parent = nullptr);

    /// Vẽ lại toàn trang từ payload mới (kết quả thành công của fincept_langkinh.py).
    void set_payload(const QJsonObject& payload);
    /// Xoá trang (widget cũ huỷ bằng deleteLater).
    void clear();

  signals:
    /// Người dùng chọn một mã: nhấp đúp hàng bảng có _link, bấm chip ma trận, bấm điểm scatter, bấm thẻ story.
    void ticker_activated(const QString& ticker);

  private:
    void render(bool keep_scroll);
    void apply_frame_style();
    QString canvas_qss(bool hoso) const;
    QString table_qss() const;

    QWidget* make_header(QWidget* parent);
    /// Block bất kỳ: đầu phần (eyebrow) / "row" / block thường.
    QWidget* make_any(const QJsonObject& block, QWidget* parent);
    QWidget* make_block(const QJsonObject& block, QWidget* parent);
    QWidget* make_chart(const QJsonObject& block, QWidget* parent, bool scatter);

    QJsonObject payload_;
    bool hoso_ = false; ///< payload hiện tại có "layout":"hoso"
};

} // namespace fincept::screens::langkinh
