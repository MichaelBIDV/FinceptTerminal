// src/screens/langkinh/LkNumberLine.h
// Lăng Kính FFT — block "numline" của hồ sơ Lăng Kính (LK_HOSO_SPEC §6): thước ngang vẽ bằng QPainter,
// dựng theo vwapChart / bandChart / rulerChart của Artifact. Ba chế độ:
//
//   vwap  : {px, v6, v12, v24, lo, hi, nhan?, kc6?, kc12?, kc24?}
//           Trục min(lo, px, VWAP)·0,985 … max(hi, VWAP, px)·1,01. Dải 52 tuần [lo, hi] (nền grey nhạt), quãng
//           giá còn phải đi tới cụm cao nhất (nền down nhạt), ba vạch VWAP 6T/12T/24T (violet) kèm nhãn
//           "6T 59,98  −1,8%", marker giá (thoi amber + "Giá 58,9"). Khoảng cách: kc6/kc12/kc24 (tỷ lệ, script
//           tính từ số chưa làm tròn) dùng NGUYÊN VĂN khi có (hợp đồng v2); thiếu thì mới tính px/VWAP − 1 từ số
//           đã làm tròn và tooltip ghi "(tính lại từ số làm tròn)". lo > hi → coi như thiếu dải 52 tuần.
//           `nhan` (kep_nong|kep_sau|thoat_6t|tren_cum — §4) hiện thành pill + diễn giải dưới thước.
//   sigma : {px, c2, c1, f, r1, r2, s?, m?}
//           Năm vùng rẻ₂ / rẻ₁ / giữa / đắt₁ / đắt₂ (xanh nhạt → xám → đỏ nhạt), mốc −2σ −1σ μ +1σ +2σ kèm giá,
//           marker giá + nhãn "58.900 · P/B 1,94× · −2,31σ" (m, s là chuỗi script đã định dạng).
//           Trục giá KHÔNG bao giờ xuống dưới 0: mốc ≤ 0 (σ lớn hơn μ/2 — P/E của năm lãi mỏng) không vẽ số, dồn
//           thành ô gạch chéo "không dùng được" ở đầu trái thước (tên mốc âm ghi trên ô, giá trị âm chỉ ở tooltip).
//           c2 (hoặc c2 + c1) null/vắng = script đã bỏ mức không dùng được → vẽ các mốc còn lại, mốc trống vào cùng
//           ô gạch chéo (hàng giá ghi "—", tooltip "trống"); f, r1, r2 vẫn bắt buộc.
//   ruler : {items:[[nhãn, z, mau?], …]} (hoặc [{lab, z, mau?}, …])
//           Một trục −3σ … +3σ, vạch mỗi 1σ, tô năm vùng; mỗi mục một chấm + nhãn "VCB P/B −2,31σ".
//           Ngoài ±3σ → tam giác chĩa ra mép, nhãn vẫn ghi số thật. Màu: `mau` (lk_role: up/down/amber/blue/
//           violet/grey/…), không có → theo từ đầu của nhãn (cùng mã cùng màu: blue, violet, amber, ink2, grey).
//           Nhãn xếp tham lam vào hàng TRỐNG gần trục nhất (trên/dưới xen kẽ; mỗi hàng thử canh giữa rồi lệch
//           trái/phải quanh chấm), nối chấm bằng đường dẫn; không còn chỗ → thử nhãn ngắn (chỉ mã), vẫn chồng → bỏ
//           chữ, giữ chấm, rê chuột lên chấm để xem nhãn. > 8 mục: 8 hàng; > 14 mục: 10 hàng (thước cao thêm).
//
// Nhãn tránh chồng: xếp tham lam vào các hàng trên/dưới thước (vwap, ruler); sigma chồng thì bỏ nhãn mốc
// (tooltip luôn đủ mọi số). Số kiểu Việt (vn_num, dấu "−" U+2212). Cao cố định 112–236px, rộng theo thẻ,
// vẽ lại khi đổi cỡ. Vạch 1–2px vẽ trên toạ độ nguyên (sắc nét ở HiDPI).
//
// Như mọi block: chỉ ĐỌC và VẼ — phép tính duy nhất là px/VWAP − 1 khi script không gửi kc. Thiếu số bắt buộc
// (giá, ít nhất một VWAP; f, r1, r2 và đơn điệu c2 ≤ c1 ≤ f ≤ r1 ≤ r2 trên các mốc có số; ít nhất một mục ruler) → thẻ ghi
// "[CẦN DATA] — …" thay cho thước. mode lạ/thiếu → nullptr (bỏ block).
// Màu đọc lại qua lk_col() mỗi lần vẽ (quy ước LkTheme cho widget tự vẽ); phông từ LkTheme.
// Tệp: LkNumberLine.cpp (vwap, sigma, helper vẽ) · LkNumberLineRuler.cpp (ruler) · LkNumberLineCard.cpp (thẻ);
// helper vẽ dùng chung khai trong LkNumberLineDraw.h (nội bộ).
#pragma once

#include "screens/langkinh/LkTheme.h"
#include "screens/langkinh/LkWidgets.h"

#include <QColor>
#include <QJsonObject>
#include <QPointF>
#include <QRectF>
#include <QString>
#include <QStringList>
#include <QVector>
#include <QWidget>

#include <array>
#include <utility>

class QEvent;
class QPainter;
class QPaintEvent;

namespace fincept::screens::langkinh::lkview {

class LkNumberLine : public QWidget {
  public:
    enum class Mode { None, Vwap, Sigma, Ruler };

    explicit LkNumberLine(const QJsonObject& b, QWidget* parent = nullptr);

    Mode mode() const { return mode_; }
    /// false → thiếu số bắt buộc của mode (hoặc mode lạ); người gọi hiện missing() thay cho thước.
    bool valid() const { return valid_; }
    /// Tên các số thiếu/sai (hiện sau "[CẦN DATA] — "), kể cả số tuỳ chọn như dải 52 tuần hay một cụm VWAP.
    const QStringList& missing() const { return missing_; }

    QSize sizeHint() const override;
    QSize minimumSizeHint() const override;

  protected:
    void paintEvent(QPaintEvent* e) override;
    bool event(QEvent* e) override; ///< ruler: tooltip riêng của chấm dưới chuột

  private:
    struct Pal {
        QColor surface, line2, ink2, muted, amber, up, down, violet, grey;
        bool light = false;
    };
    struct Item {
        QString label;
        double z = 0.0;
        LkRole role = LkRole::Ink;
    };

    void load_palette();
    void parse_vwap(const QJsonObject& b);
    void parse_sigma(const QJsonObject& b);
    void parse_ruler(const QJsonObject& b);
    void set_axis(double mn, double mx, double lo_frac, double hi_frac);
    double x_of(double v) const;
    /// sigma có mốc ≤ 0: bề rộng ô "không dùng được" ở đầu trái thước (0 nếu không có).
    double hatch_w() const;
    /// Khoảng cách giá so với cụm i: kc (script) nếu có, không thì px/VWAP − 1.
    double gap(int i) const;
    QString sigma_price_label() const;

    /// Vùng σ trong `bar`; `outline` (nếu hợp lệ) là khung bo góc chung (sigma có ô "không dùng được" bên trái).
    void paint_zones(QPainter& p, const QRectF& bar, const std::array<double, 6>& edges,
                     const QRectF& outline = QRectF()) const;
    void paint_vwap(QPainter& p) const;
    void paint_sigma(QPainter& p) const;
    void paint_ruler(QPainter& p) const;

    Mode mode_ = Mode::None;
    bool valid_ = false;
    QStringList missing_;
    QString tip_head_;
    QStringList tip_;
    int height_ = 120;
    double pad_ = 20.0; // lề trái/phải của trục
    double a0_ = 0.0;   // trục: giá trị ở mép trái
    double a1_ = 1.0;   // … và mép phải
    double px_ = 0.0;
    std::array<double, 3> v_{}; // VWAP 6T/12T/24T (NaN = thiếu)
    std::array<double, 3> kc_{}; // kc6/kc12/kc24 của script (NaN = không gửi)
    double lo_ = 0.0;           // dải 52 tuần (NaN = thiếu)
    double hi_ = 0.0;
    std::array<double, 5> b_{}; // c2 c1 f r1 r2
    QString s_;                 // nhãn z, vd "−2,31σ"
    QString m_;                 // nhãn chỉ số, vd "P/B 1,94×"
    QVector<Item> items_;       // ruler
    int half_rows_ = 3;         // ruler: số hàng nhãn mỗi phía trục
    bool neg_ = false;          // sigma: có mốc ≤ 0 (trục kẹp ở 0)
    mutable QVector<std::pair<QPointF, QString>> hits_; // ruler: chấm (toạ độ vẽ gần nhất) → nhãn tooltip
    Pal c_;
};

/// Block "numline" (LkNumberLineCard.cpp): thẻ bo 10px + title/sub/b (lk_add_head) + LkNumberLine (hoặc dòng
/// "[CẦN DATA] — …"), + pill `nhan` ở mode vwap. mode lạ/thiếu → nullptr.
QWidget* make_numline(const QJsonObject& b, QWidget* parent);

} // namespace fincept::screens::langkinh::lkview
