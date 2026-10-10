// src/screens/langkinh/LkRrgChart.h
// Lăng Kính FFT — block "rrg" (LK_HOSO_SPEC §6): đồ thị xoay vòng tương đối (RRG xấp xỉ, EST), vẽ bằng QPainter.
//
// JSON: {type:"rrg", title?, sub?, b? (bậc cả block, vd "EST"), t_cuoi? ("YYYY-MM-DD" tuần mới nhất),
//        x_range?[min,max], y_range?[min,max],
//        series:[{ma, mau? ("blue"|"violet"|"amber"|"up"|"down"|"grey"|"#rrggbb"), duoi:[[ratio,momentum],...]
//                 (cũ → mới, tối đa 8 — thừa thì giữ 8 điểm MỚI nhất), goc?, ghi?}]}
//  · Bốn góc tách tại 100/100, tô nhạt: CẢI THIỆN · Improving (trên-trái, blue) · DẪN ĐẦU · Leading (trên-phải, up)
//    · TỤT HẬU · Lagging (dưới-trái, down) · SUY YẾU · Weakening (dưới-phải, amber).
//  · Mỗi chuỗi: đuôi nhạt dần về quá khứ, mũi tên theo hướng tuần cuối + nhãn mã ở điểm mới nhất.
//  · Khung trục: x_range/y_range là cửa sổ TỐI THIỂU (điểm nằm ngoài → nới trục, không bỏ số); thiếu → tự tính
//    từ các điểm + mốc 100 (phía hẹp của 100 ≥ 30% phía rộng, để góc nào cũng đủ chỗ), đệm 10% mỗi phía.
//  · Rê chuột: tooltip mã, RS-Ratio, RS-Momentum, góc. Bấm mũi tên/nhãn mã của điểm mới nhất → on_ticker(ma).
// Thiếu khoá/sai kiểu → bỏ điểm/chuỗi, không crash; chuỗi có mã mà không còn điểm hợp lệ → chú giải "[CẦN DATA]".
// Màu đọc lúc dựng từ LkTheme (LkBlockView dựng lại cả trang khi đổi theme).
#pragma once

#include "screens/langkinh/LkWidgets.h"

#include <QColor>
#include <QFont>
#include <QJsonObject>
#include <QPointF>
#include <QRectF>
#include <QSize>
#include <QString>
#include <QStringList>
#include <QVector>
#include <QWidget>

class QMouseEvent;
class QPainter;
class QPaintEvent;

namespace fincept::screens::langkinh::lkview {

/// Thẻ block "rrg": tiêu đề (+ chip bậc) · biểu đồ · chú giải màu · dòng chú thích. Không có điểm hợp lệ nào →
/// thẻ chỉ còn tiêu đề + dòng "—" (không trả nullptr, như block chart).
QWidget* make_rrg(const QJsonObject& b, QWidget* parent, const TickerFn& on_ticker);

class LkRrgChart : public QWidget {
    Q_OBJECT
  public:
    struct Series {
        QString ma;
        QColor color;
        QVector<QPointF> tail; // (RS-Ratio, RS-Momentum), cũ → mới
        QString goc;           // nhãn góc script ghi sẵn (có thể rỗng)
        QString ghi;           // chú thích thêm cho chú giải (có thể rỗng)
    };

    LkRrgChart(const QJsonObject& block, const TickerFn& on_ticker, QWidget* parent = nullptr);

    bool has_data() const { return !series_.isEmpty(); }
    const QVector<Series>& series() const { return series_; }
    /// Mã có trong JSON nhưng không còn điểm đuôi hợp lệ nào.
    const QStringList& missing() const { return missing_; }
    /// Ngày tuần mới nhất đã định dạng dd/MM/yyyy (rỗng nếu block không có t_cuoi).
    const QString& t_cuoi() const { return t_cuoi_; }
    int max_tail() const;

    bool hasHeightForWidth() const override { return true; }
    int heightForWidth(int w) const override;
    QSize sizeHint() const override;
    QSize minimumSizeHint() const override;

  protected:
    void paintEvent(QPaintEvent* event) override;
    void mouseMoveEvent(QMouseEvent* event) override;
    void mousePressEvent(QMouseEvent* event) override;
    void mouseReleaseEvent(QMouseEvent* event) override;
    void leaveEvent(QEvent* event) override;

  private:
    struct Head {
        QVector<QPointF> pts; // toạ độ widget của đuôi
        QPointF dir;          // hướng đoạn cuối (vector đơn vị); (0,0) → vẽ chấm tròn thay mũi tên
        QRectF label;         // hộp nhãn mã
    };

    void ensure_layout() const;
    double px(double x) const;
    double py(double y) const;
    /// Điểm dưới pos: ưu tiên mũi tên/nhãn mã (điểm mới nhất) của chuỗi nào đó, rồi điểm gần nhất trong bán kính
    /// rê. Trả chỉ số chuỗi (hoặc -1), *pi = chỉ số điểm trong đuôi. heads_only → chỉ xét điểm mới nhất (bấm).
    int hit(const QPointF& pos, int* pi, bool heads_only) const;
    QString tooltip_for(int si, int pi) const;

    /// Nền 4 góc (tô nhạt + tên góc), lưới, khung, hai nét tâm 100/100.
    void paint_frame(QPainter& p) const;
    void paint_axes(QPainter& p) const;
    /// Đuôi (cắt trong vùng vẽ) rồi mũi tên + nhãn mã; chuỗi đang rê vẽ sau cùng, chuỗi khác mờ đi.
    void paint_series(QPainter& p) const;

    QVector<Series> series_;
    QStringList missing_;
    QString t_cuoi_;
    TickerFn on_ticker_;
    double x0_ = 90.0, x1_ = 110.0, y0_ = 95.0, y1_ = 105.0;

    // Màu + font chụp lúc dựng.
    QColor surface_, line_, line2_, ink2_, muted_;
    QColor quad_[4]; // 0 Cải thiện (trên-trái) · 1 Dẫn đầu (trên-phải) · 2 Tụt hậu (dưới-trái) · 3 Suy yếu (dưới-phải)
    double soft_ = 0.12;
    QFont f_tick_, f_quad_, f_quad_en_, f_label_;

    // Hình học theo kích thước hiện tại (tính lười).
    mutable QSize geo_size_;
    mutable QRectF plot_;
    mutable QVector<double> xt_, yt_;
    mutable int xdec_ = 0, ydec_ = 0;
    mutable QVector<Head> heads_;

    int hover_s_ = -1;
    int hover_p_ = -1;
    int press_s_ = -1;
};

} // namespace fincept::screens::langkinh::lkview
