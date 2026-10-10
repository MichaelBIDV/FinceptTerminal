// src/screens/langkinh/LkChart.h
// Lăng Kính FFT — hai biểu đồ Qt Charts cho block "chart" và "scatter" (CONTRACT §3.1).
//
// LkLineChart   : trục X QDateTimeAxis (epoch ms, "MM/yy"), trục trái/phải QValueAxis.
//                 style: line | thin | dash | dot | bar | band (DELTA v3 V3.2, LkBandSet). null trong y = đứt đoạn.
//                 Khoá "annotations" (V3.3) → LkChartAnnot (marker, nhãn, vline, xband).
//                 Rê chuột: tooltip chú thích nếu trúng, còn lại ngày + giá trị mọi chuỗi tại phiên/tuần gần nhất.
//                 Tooltip chú thích "dính": giữ nguyên tới khi con trỏ rời bán kính quanh điểm hiện (không tự tắt
//                 theo giờ, không bị tooltip ngày/giá thay ngay khi lệch vài pixel). Bấm vào marker = ghim bảng
//                 thông tin trong chart; bấm chỗ khác, Esc, đổi kích thước hoặc ẩn chart đều đóng bảng.
// LkScatterChart: điểm tô theo "mau", đường 0/0, nhãn 4 góc, tooltip mã; bấm điểm → ticker_activated.
//                 Vài điểm cực đoan (ngoài [P2, P98] nới 25%) vẽ ở mép khung bằng tam giác + nhãn số thật,
//                 để cụm chính không bị ép thành một chấm.
// Màu lấy từ ui::colors tại lúc dựng; LkBlockView dựng lại cả trang khi theme đổi.
#pragma once

#include "screens/langkinh/LkChartLayers.h"

#include <QChartView>
#include <QJsonObject>
#include <QPointF>
#include <QString>
#include <QVector>

class QAbstractSeries;
class QGraphicsSimpleTextItem;
class QLabel;

namespace fincept::screens::langkinh {

class LkLineChart : public QChartView {
    Q_OBJECT
  public:
    explicit LkLineChart(const QJsonObject& block, QWidget* parent = nullptr);

    /// false khi block không có điểm hợp lệ nào (khi đó người gọi hiện chữ thay biểu đồ).
    bool has_data() const { return has_data_; }
    /// Lớp chú thích (null khi block không có "annotations").
    const LkChartAnnot* annotations() const { return annot_; }

  protected:
    void mouseMoveEvent(QMouseEvent* event) override;
    void mousePressEvent(QMouseEvent* event) override;
    void keyPressEvent(QKeyEvent* event) override;
    void resizeEvent(QResizeEvent* event) override;
    void hideEvent(QHideEvent* event) override;
    void leaveEvent(QEvent* event) override;
    void wheelEvent(QWheelEvent* event) override;

  private:
    void show_pin(const QString& html, const QPoint& view_pos);
    void hide_pin();

    struct Line {
        QString name;
        QVector<double> y; // NaN = không có số
    };

    QVector<qint64> x_;   // epoch ms theo chỉ số gốc của block["x"]
    QVector<int> order_;  // chỉ số gốc có x hợp lệ, sắp tăng theo thời gian
    QVector<Line> lines_; // để dựng tooltip
    QAbstractSeries* anchor_ = nullptr;
    int hover_idx_ = -1; // -2 = đang hiện tooltip chú thích
    bool has_data_ = false;
    LkBandSet bands_;
    LkChartAnnot* annot_ = nullptr; // con QObject của view
    QString hover_tip_;
    QPoint tip_anchor_;      // toạ độ toàn cục nơi tooltip chú thích hiện (bán kính "dính" tính từ đây)
    QLabel* pin_ = nullptr;  // bảng thông tin ghim (con của viewport), null khi chưa ghim
};

class LkScatterChart : public QChartView {
    Q_OBJECT
  public:
    explicit LkScatterChart(const QJsonObject& block, QWidget* parent = nullptr);

    int point_count() const { return static_cast<int>(pts_.size()); }

  signals:
    void ticker_activated(const QString& ticker);

  protected:
    void wheelEvent(QWheelEvent* event) override;

  private:
    struct Pt {
        QPointF p;     // giá trị thật (tooltip, nhãn)
        QPointF shown; // vị trí vẽ (= p, hoặc kẹp vào mép khi ngoài khung trục)
        QString label;
        bool out = false; // ngoài khung trục → vẽ ở mép, hình tam giác
    };

    int nearest(const QPointF& value) const;
    QString tooltip_for(int i) const;
    void layout_overlays();

    QVector<Pt> pts_;
    QString x_label_;
    QString y_label_;
    double span_x_ = 1.0;
    double span_y_ = 1.0;
    QAbstractSeries* anchor_ = nullptr;
    QGraphicsSimpleTextItem* quad_[4] = {nullptr, nullptr, nullptr, nullptr}; // tl, tr, bl, br
    QVector<QGraphicsSimpleTextItem*> labels_; // song song với pts_; nullptr = điểm không có nhãn
    QGraphicsSimpleTextItem* outlier_note_ = nullptr; // chú thích "▲ n điểm ngoài khung" (nếu có)
};

} // namespace fincept::screens::langkinh
