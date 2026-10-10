// src/screens/langkinh/LkLayouts.h
// Lăng Kính FFT — các QLayout tự viết của trang hồ sơ (tách khỏi LkChips để mỗi tệp ≤ 800 dòng).
//
//   · LkWrapLayout     : bố cục chảy, xuống dòng, hiểu heightForWidth (chip dài tự gói chữ).
//   · LkAutoGridLayout : lưới auto-fit kiểu CSS repeat(auto-fit, minmax(min, 1fr)).
//   · LkColumnLayout   : cột có bề rộng tối đa (trang hồ sơ 1180px canh giữa; khổ đoạn văn canh trái). Chiều cao
//                        tính ở ĐÚNG bề rộng cột (QWidgetItem::heightForWidth không tự chặn theo maximumWidth, nên
//                        setMaximumWidth trên một QLabel xuống dòng sẽ cắt chữ — dùng lk_measure thay thế).
//   · LkRowLayout      : block "row" (hợp đồng block v2) — các mục đứng cạnh nhau, chia bề rộng theo `flex` (mặc
//                        định đều), mục có bề rộng tối đa nhận đúng mức đó, khe `gap`; hàng hẹp hơn `stack_below`
//                        thì xếp dọc. Mục trong một hàng cao bằng nhau (như CSS grid).
// Mọi layout quyết định từ đúng hình chữ nhật được cấp (setGeometry/heightForWidth), không dựa vào resizeEvent:
// trang dựng lúc đang ẩn trong QStackedWidget có thể không nhận resize nào.
#pragma once

#include <QLayout>
#include <QList>
#include <QRect>
#include <QSize>
#include <QVector>
#include <Qt>

#include <utility>

class QLayoutItem;
class QWidget;

namespace fincept::screens::langkinh::lkview {

/// Bố cục chảy: xếp mục theo sizeHint, hết chỗ thì xuống dòng; mục rộng hơn khung được cấp đúng bề rộng khung
/// và cao theo heightForWidth (chip dài tự gói chữ). center=true → canh giữa dọc trong mỗi dòng.
class LkWrapLayout : public QLayout {
  public:
    explicit LkWrapLayout(QWidget* parent, int hspace = 8, int vspace = 8, bool center = true);
    ~LkWrapLayout() override;

    void addItem(QLayoutItem* item) override { items_.append(item); }
    int count() const override { return static_cast<int>(items_.size()); }
    QLayoutItem* itemAt(int i) const override { return (i >= 0 && i < items_.size()) ? items_.at(i) : nullptr; }
    QLayoutItem* takeAt(int i) override { return (i >= 0 && i < items_.size()) ? items_.takeAt(i) : nullptr; }
    Qt::Orientations expandingDirections() const override { return {}; }
    bool hasHeightForWidth() const override { return true; }
    int heightForWidth(int w) const override { return do_layout(QRect(0, 0, w, 0), true); }
    void setGeometry(const QRect& r) override {
        QLayout::setGeometry(r);
        do_layout(r, false);
    }
    QSize sizeHint() const override;
    QSize minimumSize() const override;

  private:
    int do_layout(const QRect& rect, bool test_only) const;

    QList<QLayoutItem*> items_;
    int h_;
    int v_;
    bool center_;
};

/// Lưới auto-fit: số cột = số cột rộng ≥ min_col_w vừa khung (tối đa max_cols; ≤0 = không giới hạn; không quá
/// số mục), cột chia đều, hàng cao bằng mục cao nhất (mục trong hàng kéo cao bằng nhau như CSS grid).
/// minimumSize chặn bề rộng ở min_col_w (đánh đổi có chủ ý: khung hẹp hơn một cột thì mục bị co, trang không cuộn
/// ngang; mục có minimum lớn hơn — pill chữ dài — có thể bị cắt mép).
class LkAutoGridLayout : public QLayout {
  public:
    LkAutoGridLayout(QWidget* parent, int min_col_w, int max_cols, int gap);
    ~LkAutoGridLayout() override;

    void addItem(QLayoutItem* item) override { items_.append(item); }
    int count() const override { return static_cast<int>(items_.size()); }
    QLayoutItem* itemAt(int i) const override { return (i >= 0 && i < items_.size()) ? items_.at(i) : nullptr; }
    QLayoutItem* takeAt(int i) override { return (i >= 0 && i < items_.size()) ? items_.takeAt(i) : nullptr; }
    Qt::Orientations expandingDirections() const override { return Qt::Horizontal; }
    bool hasHeightForWidth() const override { return true; }
    int heightForWidth(int w) const override { return do_layout(QRect(0, 0, w, 0), true); }
    void setGeometry(const QRect& r) override {
        QLayout::setGeometry(r);
        do_layout(r, false);
    }
    QSize sizeHint() const override;
    QSize minimumSize() const override;
    int columns_for(int w) const;
    /// true → giữ cột trống như CSS auto-fill (ít mục thì mục không giãn hết bề rộng); mặc định auto-fit.
    void set_keep_tracks(bool on) { keep_tracks_ = on; }

  private:
    int do_layout(const QRect& rect, bool test_only) const;

    QList<QLayoutItem*> items_;
    int min_w_;
    int max_cols_;
    int gap_;
    bool keep_tracks_ = false;
};

/// Cột bề rộng tối đa max_w: các mục xếp dọc (không khe), mỗi mục rộng min(khung, max_w), canh theo `align`
/// (AlignHCenter: trang hồ sơ; AlignLeft: khổ đoạn văn). Mục cuối nhận phần cao còn lại của khung.
class LkColumnLayout : public QLayout {
  public:
    LkColumnLayout(QWidget* parent, int max_w, Qt::Alignment align = Qt::AlignHCenter);
    ~LkColumnLayout() override;

    void addItem(QLayoutItem* item) override { items_.append(item); }
    int count() const override { return static_cast<int>(items_.size()); }
    QLayoutItem* itemAt(int i) const override { return (i >= 0 && i < items_.size()) ? items_.at(i) : nullptr; }
    QLayoutItem* takeAt(int i) override { return (i >= 0 && i < items_.size()) ? items_.takeAt(i) : nullptr; }
    Qt::Orientations expandingDirections() const override { return Qt::Horizontal | Qt::Vertical; }
    bool hasHeightForWidth() const override { return true; }
    int heightForWidth(int w) const override { return do_layout(QRect(0, 0, w, 0), true); }
    void setGeometry(const QRect& r) override {
        QLayout::setGeometry(r);
        do_layout(r, false);
    }
    QSize sizeHint() const override;
    QSize minimumSize() const override;

  private:
    int do_layout(const QRect& rect, bool test_only) const;

    QList<QLayoutItem*> items_;
    int max_w_;
    Qt::Alignment align_;
};

/// Property (int px) một block đặt lên widget gốc để báo bề rộng hữu ích tối đa khi đứng trong "row" (vd sơ đồ
/// mẫu hình ≈280px/sơ đồ). Chỉ LkRowLayout đọc; ngoài "row" không có tác dụng.
inline constexpr char kRowMaxWProp[] = "lkRowMaxW";

/// Block "row": mục cạnh nhau, khe gap; bề rộng chia theo trọng số `flex` (mặc định chia đều). Mục có bề rộng tối
/// đa (maximumWidth đặt rõ, hoặc property kRowMaxWProp) nhận đúng mức đó, phần dư chia cho các mục còn lại. Hàng hẹp
/// hơn stack_below → xếp dọc, khe gap — trừ khi các mục có bề rộng tối đa vẫn chừa cho mục còn lại ≥ stack_below/2
/// mỗi mục (mục cố định hẹp không đẩy hàng xếp dọc).
class LkRowLayout : public QLayout {
  public:
    LkRowLayout(QWidget* parent, int gap, int stack_below);
    ~LkRowLayout() override;
    /// Trọng số bề rộng theo thứ tự mục (hợp đồng "flex":[1,2]); số lượng khác số mục hoặc có số ≤ 0 → chia đều.
    void set_flex(QVector<double> flex) { flex_ = std::move(flex); }

    void addItem(QLayoutItem* item) override { items_.append(item); }
    int count() const override { return static_cast<int>(items_.size()); }
    QLayoutItem* itemAt(int i) const override { return (i >= 0 && i < items_.size()) ? items_.at(i) : nullptr; }
    QLayoutItem* takeAt(int i) override { return (i >= 0 && i < items_.size()) ? items_.takeAt(i) : nullptr; }
    Qt::Orientations expandingDirections() const override { return Qt::Horizontal; }
    bool hasHeightForWidth() const override { return true; }
    int heightForWidth(int w) const override { return do_layout(QRect(0, 0, w, 0), true); }
    void setGeometry(const QRect& r) override {
        QLayout::setGeometry(r);
        do_layout(r, false);
    }
    QSize sizeHint() const override;
    QSize minimumSize() const override;

  private:
    int do_layout(const QRect& rect, bool test_only) const;
    /// Bề rộng từng mục khi đứng cạnh nhau (rỗng = phải xếp dọc).
    QVector<int> side_widths(const QList<QLayoutItem*>& vis, int width) const;

    QList<QLayoutItem*> items_;
    int gap_;
    int stack_below_;
    QVector<double> flex_;
};

/// Bề rộng cột kiểu bố cục bảng tự động của CSS (bảng "wrap"): Σmax ≤ khung → max, phần dư dồn cho cột `stretch`;
/// Σmin ≥ khung → min (người gọi cuộn ngang); ở giữa → min + (max − min)·t với t chung cho mọi cột, nên cột nhiều
/// chữ nhất nhận nhiều chỗ nhất và không cột nào hẹp dưới mức tối thiểu của nó.
QVector<int> lk_auto_col_widths(const QVector<int>& mn, const QVector<int>& mx, int avail, int stretch);

/// Bọc `child` trong một khung khổ chữ max_w canh trái (objectName "lkMeasure", nền trong suốt qua QSS trang):
/// đoạn văn dài không chạy hết bề rộng 1180px của trang (Artifact: p{max-width:74ch}).
QWidget* lk_measure(QWidget* child, int max_w, QWidget* parent);

} // namespace fincept::screens::langkinh::lkview
