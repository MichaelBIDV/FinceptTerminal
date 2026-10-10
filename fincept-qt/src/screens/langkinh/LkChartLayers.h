// src/screens/langkinh/LkChartLayers.h
// Lăng Kính FFT — lớp phủ cho LkLineChart (CONTRACT_DELTA v3):
//   LkBandSet    : series style "band" (V3.2) — vùng tô giữa y_lo và y_hi (QAreaSeries, viền trong suốt), luôn
//                  nằm dưới mọi line, có ô legend. lo_min/hi_max = đáy/đỉnh trục. null = đứt dải.
//   LkChartAnnot : khoá "annotations" (V3.3) — point (marker + nhãn), vline, xband, hband (V4.3: dải ngang y0–y1
//                  trên trục chỉ định, toàn bề rộng plot, dưới mọi series, nhãn nhỏ sát mép trái trong dải). Vẽ bằng
//                  QGraphicsItem con của QChart, đặt lại khi plotAreaChanged; nhãn đặt theo uu_tien vào chỗ trống GẦN
//                  marker nhất (ưu tiên hướng `pos`, rồi hướng ngược, rồi hai bên; lệch dọc tối đa 3 nấc), vẫn đè thì
//                  ẩn (marker + tooltip giữ nguyên); nhãn luôn kẹp trong plot area. Rê chuột → tooltip `tip`.
//                  box (hộp của engine): chữ nhật x0–x1 × y0–y1 (axis tuỳ chọn), viền đứt + nền alpha (mặc định 0,06),
//                  nhãn trong hộp góc trên trái khi vừa, không thì ngay trên/dưới hộp; trục giá trị chứa đủ y0–y1.
//                  Cỡ chữ V4.5: nhãn chính ≤ 10px đậm, dòng phụ 8px, đệm hộp −20%, marker ~10px.
#pragma once

#include <QColor>
#include <QJsonArray>
#include <QJsonObject>
#include <QObject>
#include <QPointF>
#include <QRectF>
#include <QString>
#include <QStringList>
#include <QVector>

#include <functional>

class QAbstractAxis;
class QAbstractSeries;
class QAreaSeries;
class QChart;
class QGraphicsLineItem;
class QGraphicsPathItem;
class QGraphicsRectItem;
class QValueAxis;

namespace fincept::screens::langkinh {

namespace lkannot {
class Label;
}

class LkBandSet {
  public:
    /// Tạo QAreaSeries (chưa có điểm) và addSeries NGAY — gọi trước khi thêm line để dải nằm dưới.
    /// `grow` nhận mọi giá trị y_lo/y_hi hữu hạn đang dùng (để trục chứa đủ dải).
    void add(QChart* chart, const QJsonObject& so, const QVector<qint64>& x, const QVector<int>& order,
             const QColor& color, const QString& name, bool right, const std::function<void(double)>& grow);
    /// Khi đã có trục: điền điểm (lo_min → min trục, hi_max → max trục), gắn trục, ô legend đậm hơn vùng tô.
    void finish(QChart* chart, QAbstractAxis* ax, QValueAxis* left, QValueAxis* right);
    /// Các dòng "<br>Tên: ≤ 0,143%" cho tooltip dữ liệu tại chỉ số gốc idx.
    QString tooltip(int idx, const std::function<QString(double)>& fmt) const;
    bool empty() const { return bands_.isEmpty(); }

  private:
    struct Band {
        QString name;
        QVector<double> lo, hi; // NaN = không có số
        bool lo_min = false;
        bool hi_max = false;
        bool right = false;
        QColor color;
        double alpha = 0.14;
        QVector<QAreaSeries*> segs;   // mỗi đoạn liền một QAreaSeries; chỉ đoạn đầu có ô legend
        QVector<QVector<int>> seg_idx; // chỉ số gốc của từng đoạn
    };
    QVector<Band> bands_;
    QVector<qint64> x_;
};

class LkChartAnnot : public QObject {
  public:
    /// left/right: một series bất kỳ đã gắn trục trái/phải (để đổi giá trị → toạ độ); right có thể null.
    LkChartAnnot(QChart* chart, const QJsonArray& items, QAbstractSeries* left, QAbstractSeries* right,
                 QObject* parent);

    /// Gọi `add(y, right)` cho y0/y1 hữu hạn của mọi hband và box — để trục giá trị chứa đủ dải trước khi dựng trục.
    static void grow(const QJsonArray& items, const std::function<void(double, bool)>& add);

    void relayout();
    /// Tooltip (HTML) của chú thích dưới điểm p (toạ độ QChart); rỗng nếu không trúng chú thích nào.
    QString tip_at(const QPointF& p) const;
    /// Tên các xband chứa x (epoch ms), các hband chứa tung độ chart_y (toạ độ QChart) và các box chứa cả hai —
    /// ghép vào tooltip dữ liệu.
    QStringList bands_at(double x, double chart_y) const;

    struct Shown {
        QString text;
        QRectF rect; // toạ độ QChart
    };
    /// Nhãn đang hiện — để harness kiểm đè nhau / tràn plot area.
    QVector<Shown> shown_labels() const;
    int size() const { return static_cast<int>(anns_.size()); }

  private:
    enum class Kind { Point, VLine, XBand, HBand, Box };
    struct Ann {
        Kind kind = Kind::Point;
        double x = 0.0;
        double x1 = 0.0; // xband, box
        double y = 0.0;  // point; hband, box: y0
        double y1 = 0.0; // hband, box
        bool right = false;
        int prio = 2;
        QString marker;
        QString text;
        QString sub;
        QString tip;
        QString pos;
        QColor color;
        QGraphicsPathItem* mk = nullptr;
        lkannot::Label* label = nullptr;
        QGraphicsLineItem* lead = nullptr;
        QGraphicsLineItem* lead_bg = nullptr; // viền tối dưới nét nối — vẫn thấy khi chạy qua cột/line cùng màu
        QGraphicsLineItem* vl = nullptr;
        QGraphicsRectItem* band = nullptr; // xband, hband, box (box: viền đứt)
        QGraphicsPathItem* edge = nullptr; // hband: nét mảnh ở mép trên/dưới dải
        QPointF at;   // toạ độ marker/vạch (QChart) sau relayout
        QRectF hit;   // vùng marker (point) hoặc dải (xband, hband) / hộp (box), đã kẹp trong plot area
        bool on = false; // nằm trong plot area
    };

    QPointF to_pos(double x, double y, bool right) const;
    QVector<QPointF> candidates(const Ann& a, const QSizeF& sz, const QRectF& pa) const;

    QChart* chart_ = nullptr;
    QAbstractSeries* left_ = nullptr;
    QAbstractSeries* right_ = nullptr;
    QVector<Ann> anns_;
};

} // namespace fincept::screens::langkinh
