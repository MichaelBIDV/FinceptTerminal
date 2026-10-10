// src/screens/langkinh/LangKinhPanel.h
// Lăng Kính cấu trúc cổ đông & FFT (VN30 · VN100) — panel điều khiển + trang block.
//
// Luồng: EconomicsService.execute("langkinh", "fincept_langkinh.py", <view>, {<rổ|mã>}, "lk_<view>_<arg>#<seq>")
//   → JSON {success, title, sub, as_of, tuoi, cong, blocks, data, tickers} → LkBlockView vẽ.
// Script chỉ ĐỌC tệp bridge (fft_langkinh.json …); panel không tính lại công thức nào.
// Mọi lần nạp (FETCH, đổi rổ/chế độ xem/mã) đều bỏ qua cache của EconomicsService (DELTA I1).
// Đổi combo view hoặc nút rổ được gom (debounce ~250 ms); FETCH, bấm mã trên trang và Enter ở ô mã nạp ngay.
// Ô MÃ (DELTA v3 V3.1): QLineEdit + QCompleter trên `ds_ma` (vũ trụ VN100) — gõ "V" → popup mọi mã bắt đầu bằng V;
// Enter / chọn dòng → mở view chuoi của mã đó (ở các view họ hồ sơ hoso · matran5 · sigma · rrg: mở view hoso);
// mã ngoài danh sách → viền đỏ, không nạp. View theo mã (chuoi, hoso) nhận mã làm đối số, view khác nhận rổ.
#pragma once

#include "screens/economics/panels/EconPanelBase.h"

#include <QComboBox>
#include <QJsonArray>
#include <QLabel>
#include <QPushButton>
#include <QSet>
#include <QString>

class QCompleter;
class QLineEdit;
class QStandardItemModel;
class QTimer;

namespace fincept::screens {

namespace langkinh {
class LkBlockView;
}

class LangKinhPanel : public EconPanelBase {
    Q_OBJECT
  public:
    explicit LangKinhPanel(QWidget* parent = nullptr);

    /// Lần đầu (hoặc khi chưa có dữ liệu) thì nạp; các lần sau không tự nạp lại.
    void activate() override;

    QVariantMap save_panel_state() const override;
    void restore_panel_state(const QVariantMap& state) override;

  signals:
    /// Rổ / chế độ xem / mã vừa đổi — màn hình dùng để báo ScreenStateManager.
    void state_changed();

  protected:
    void build_controls(QHBoxLayout* thl) override;
    void on_fetch() override;
    void on_result(const QString& request_id, const services::EconomicsResult& result) override;
    void refresh_panel_theme() override;
    void retranslateUi() override;

  private:
    void fetch();
    void schedule_fetch();
    void fetch_if_changed();
    QString current_view() const;
    void set_scope(const QString& scope);
    void select_view(const QString& view);
    void fill_ds_ma(const QJsonArray& ds_ma, const QJsonArray& tickers);
    void on_view_changed(int index);
    void on_ma_entered(const QString& text);
    void on_ticker_activated(const QString& ma);
    void update_scope_btn_styles();
    void update_ma_text();
    void update_ma_style();
    void update_status_style();

    QPushButton* btn_vn30_ = nullptr;
    QPushButton* btn_vn100_ = nullptr;
    QPushButton* btn_vn200_ = nullptr;
    QLabel* view_lbl_ = nullptr;
    QComboBox* view_combo_ = nullptr;
    QLabel* ma_lbl_ = nullptr;
    QLineEdit* ma_edit_ = nullptr;
    QCompleter* ma_completer_ = nullptr;
    QStandardItemModel* ma_model_ = nullptr;
    QSet<QString> ds_ma_; // mã hợp lệ cho ô gõ (rỗng = chưa có kết quả nào → để script tự kiểm)
    bool ma_invalid_ = false;
    QLabel* status_lbl_ = nullptr;

    langkinh::LkBlockView* block_view_ = nullptr;
    int page_idx_ = -1;

    QString scope_ = QStringLiteral("VN30");
    QString ma_ = QStringLiteral("FPT");
    QString pending_req_; // request_id đang chờ; kết quả khác (cũ về muộn) bị bỏ qua
    quint64 req_seq_ = 0; // số thứ tự trong request_id: hai lần nạp cùng view+đối số vẫn khác id
    QTimer* fetch_timer_ = nullptr; // một phát, khởi động lại mỗi lần đổi combo/rổ (debounce)
    bool has_data_ = false;
    bool stale_ = false; // dữ liệu bridge cũ (tuoi chứa "CŨ")
    bool mh_theo_ma_ = false; // view mauhinh: true = trang mã (ma_) sau khi chọn mã; false = trang vũ trụ (scope_)
};

} // namespace fincept::screens
