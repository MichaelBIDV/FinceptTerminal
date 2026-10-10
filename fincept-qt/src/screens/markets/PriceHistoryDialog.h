// src/screens/markets/PriceHistoryDialog.h
// Cửa sổ biểu đồ mở ra khi bấm một dòng ở tab MARKETS — chỉ số, trái phiếu, hàng hoá, FX,
// crypto, cổ phiếu Việt Nam, đều cùng một đường.
//
// VÌ SAO KHÔNG DÙNG KLineChartWidget
// ---------------------------------
// ui/charts/KLineChartWidget là widget nến dùng chung của app nhưng nó chạy trên QWebEngineView,
// mà kit Qt 6.8.3 trên máy này KHÔNG có QtWebEngine (CMakeCache: Qt6WebEngineWidgets_DIR-NOTFOUND).
// Vẽ bằng QPainter thì không phụ thuộc bộ máy trình duyệt nào.
//
// DỮ LIỆU
// -------
// Cùng một đường với ô nến trên dashboard: DataHub topic
// `market:history:<mã>:<period>:<interval>` do MarketDataService sản xuất qua yfinance_data.py.
// Mã Việt Nam (^VNINDEX, FPT…) được yfinance_data.py tự định tuyến sang kho vnstock/VNDirect;
// lợi suất TPCP Việt Nam cũng đi qua đúng đường đó, nên cửa sổ này không có trường hợp đặc biệt.
//
// KỲ ĐO — chỉ dùng những kỳ mà CẢ HAI nhánh (yfinance và nhánh VN) cùng hiểu. Nhánh VN không có
// "3y": gửi "3y" sẽ rơi âm thầm về mặc định 183 ngày và vẽ ra một biểu đồ sai nhãn.
#pragma once

#include "services/markets/MarketDataService.h"

#include <QDialog>
#include <QPixmap>
#include <QVector>

class QLabel;
class QPushButton;
class QStackedWidget;
class QTimer;

namespace fincept::screens {

namespace widgets {
class CandleCanvas;
}

/// Đường giá + vùng tô, trục giá bên phải, trục thời gian bên dưới, rê chuột để đọc từng điểm.
class HistoryLineCanvas : public QWidget {
    Q_OBJECT
  public:
    explicit HistoryLineCanvas(QWidget* parent = nullptr);
    void set_points(const QVector<services::HistoryPoint>& pts, bool is_yield);
    void clear();

  protected:
    void paintEvent(QPaintEvent*) override;
    void resizeEvent(QResizeEvent*) override;
    void mouseMoveEvent(QMouseEvent*) override;
    void leaveEvent(QEvent*) override;

  private:
    void rebuild_cache();
    QRect plot_rect() const;
    QString fmt(double v) const;

    QVector<services::HistoryPoint> pts_;
    bool is_yield_ = false;
    QPixmap cache_;
    bool dirty_ = true;
    int hover_ = -1;
    double lo_ = 0, hi_ = 0;

    static constexpr int kAxisW = 70;
    static constexpr int kAxisH = 22;
};

class PriceHistoryDialog : public QDialog {
    Q_OBJECT
  public:
    PriceHistoryDialog(const QString& symbol, const QString& display_name, QWidget* parent = nullptr);
    ~PriceHistoryDialog() override;

    /// Lợi suất (trái phiếu) vẽ và đọc theo "%" và "điểm %", không theo tiền.
    static bool is_yield_symbol(const QString& symbol);

  protected:
    void showEvent(QShowEvent*) override;
    void hideEvent(QHideEvent*) override;

  private:
    void build_ui();
    void select_range(int idx);
    void subscribe();
    void on_points(const QVector<services::HistoryPoint>& pts);
    void update_stats();
    QString topic() const;

    QString symbol_;
    QString name_;
    bool is_yield_ = false;
    int range_idx_ = 4; // mặc định 1 năm
    QVector<services::HistoryPoint> pts_;

    QLabel* title_ = nullptr;
    QLabel* last_ = nullptr;
    QLabel* chg_ = nullptr;
    QLabel* hilo_ = nullptr;
    QLabel* note_ = nullptr;
    QVector<QPushButton*> range_btns_;
    QPushButton* kind_btn_ = nullptr;
    QStackedWidget* stack_ = nullptr;
    HistoryLineCanvas* line_ = nullptr;
    widgets::CandleCanvas* candle_ = nullptr;
    QTimer* timeout_ = nullptr;
    bool hub_active_ = false;
};

} // namespace fincept::screens
