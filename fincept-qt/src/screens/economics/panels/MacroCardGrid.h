// src/screens/economics/panels/MacroCardGrid.h
// Bảng THẺ CHỈ TIÊU — dựng lại bằng widget gốc cái bảng HTML
// ~/Downloads/fincept_macro_dashboard.html, ngay trong tab VĨ MÔ.
//
// VÌ SAO KHÔNG NHÚNG THẲNG TRANG HTML
// -----------------------------------
// Hai lẽ, cả hai đều đo được:
//   1. Bản Qt trên máy này KHÔNG có QtWebEngine — build-v450/CMakeCache.txt ghi
//      `Qt6WebEngineWidgets_DIR-NOTFOUND`, và kit ~/Qt/6.8.3/macos không có thư viện lẫn
//      cmake config của WebEngine/WebView/WebChannel. Không có bộ máy trình duyệt thì không
//      có cách nào vẽ trang đó bên trong app.
//   2. Quan trọng hơn: tệp HTML đó là ẢNH CHỤP ĐÓNG BĂNG. Khối RAW_CARDS trong tệp đóng dấu
//      Việt Nam 05-09-2026, Trung Quốc 15-09, Mỹ và Châu Âu 17-09. Nhúng nguyên trạng là
//      treo số cũ 16 ngày lên terminal và gọi nó là dữ liệu. Thẻ ở đây đọc CÙNG luồng với
//      màn Leaderboard (fincept_macro.py → dulieukinhte, cache 2 giờ), nên số đổi theo nguồn.
//
// KHÔNG CÓ SPARKLINE — VÀ NÓI RÕ VÌ SAO
// -------------------------------------
// Trang HTML có đường sparkline trên mỗi thẻ vì nó đã nạp sẵn cả MAX_SERIES (6,3 MB). Vẽ lại
// 79 đường đó theo thời gian thực cần 79 lượt tải về dulieukinhte.com — một trang của bên thứ
// ba mà chủ hệ đã chốt ngày 20/09/2026 là chỉ đọc trang công khai, tiết chế số lượt. Kho chuỗi
// tại máy (superdash_v2/widata_series_store.json) là dữ liệu FRED, không khớp tên với 79 chỉ
// tiêu này nên ghép vào sẽ là ghép ẩu. Vì vậy thẻ không vẽ đường; bấm vào thẻ mở thẳng đồ thị
// lịch sử tối đa của chính chỉ tiêu đó — đúng một lượt tải, đúng lúc người dùng cần.
#pragma once

#include <QFrame>
#include <QJsonArray>
#include <QJsonObject>
#include <QLabel>
#include <QScrollArea>
#include <QVector>

class QGridLayout;

namespace fincept::screens {

/// Một thẻ chỉ tiêu. Bấm vào phát tín hiệu kèm MÃ BẢNG để mở dải lịch sử.
class MacroCard : public QFrame {
    Q_OBJECT
  public:
    MacroCard(const QJsonObject& card, const QString& country_code, QWidget* parent = nullptr);

    QString label() const { return label_; }
    QString country_code() const { return cc_; }
    int table_id() const { return table_id_; }

  signals:
    void activated(int table_id, const QString& indicator_name);

  protected:
    void mouseReleaseEvent(QMouseEvent* e) override;
    void enterEvent(QEnterEvent* e) override;
    void leaveEvent(QEvent* e) override;

  private:
    void apply_style(bool hover);

    QString label_;
    QString cc_;
    int table_id_ = 0;
};

/// Lưới thẻ cuộn được, gom nhóm theo nền kinh tế.
class MacroCardGrid : public QScrollArea {
    Q_OBJECT
  public:
    explicit MacroCardGrid(QWidget* parent = nullptr);

    /// Nạp thẻ của MỘT nền kinh tế. Gọi bốn lần cho bốn nền; lưới tự dựng lại.
    void set_country_cards(const QString& country_code, const QString& country_name,
                           const QJsonArray& cards);
    /// Chỉ hiện một nền kinh tế; chuỗi rỗng = hiện tất cả. Lọc tại chỗ, KHÔNG tải lại.
    void set_filter(const QString& country_code);
    void set_search(const QString& text);
    void clear_all();

    int total_cards() const;

  signals:
    void indicator_activated(int table_id, const QString& indicator_name);

  protected:
    void resizeEvent(QResizeEvent* e) override;

  private:
    void rebuild();
    int columns_for_width(int w) const;

    struct Nhom {
        QString code;
        QString name;
        QJsonArray cards;
    };
    QVector<Nhom> nhom_;
    QString filter_;
    QString search_;
    QWidget* canvas_ = nullptr;
    QGridLayout* grid_ = nullptr;
    int cols_ = 0;
};

} // namespace fincept::screens
