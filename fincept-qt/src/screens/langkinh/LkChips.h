// src/screens/langkinh/LkChips.h
// Lăng Kính FFT — phần dùng chung của các block "hồ sơ" (LK_HOSO_SPEC §6) + block "chips".
//
//   · lk_inline_html / lk_para_html : html-lite (<b> <strong> <i> <em> <code> <br> + <tag b="FACT-T2">…</tag>)
//     → rich text an toàn cho QLabel. Thẻ khác bị bỏ (giữ chữ bên trong), chữ được escape; <tag> thành span
//     mono màu bậc trên nền soft (màu đục, đã phủ lên surface).
//   · lk_label / lk_add_head        : nhãn chữ theo phông hồ sơ (phông qua QSS vì QSS toàn cục ghi đè setFont).
//     lk_add_head hiểu khoá `b` (hợp đồng block v2): tag bậc bên phải tiêu đề. lk_section_head = đầu phần kiểu
//     Artifact .sec-head (eyebrow mono amber · tiêu đề serif 28 · sub sans 14 · vạch 1px) cho block có `eyebrow`.
//   · lk_paint_pill / lk_paint_tag   : bộ vẽ pill (bo tròn hẳn) và tag bậc (bo 4px); LkPill / LkTag là widget
//     tự vẽ tương ứng; LkCapsLabel = nhãn mono chữ hoa giãn chữ (eyebrow, tiêu đề hộp).
//   · LkWrapLayout / LkAutoGridLayout: ở LkLayouts.h (include lại ở đây cho các tệp block cũ).
//   · make_chips                     : block {type:"chips", title?, sub?, items:[{b, text}]}.
//
// Như mọi block của LkBlockView: chỉ ĐỌC và VẼ, thiếu khoá/sai kiểu → "—" hoặc bỏ block (nullptr), không crash.
// Màu lấy qua lk_col() (LkTheme.h) — widget tự vẽ đọc lại màu trong paintEvent. Không lớp nào cần moc.
#pragma once

#include "screens/langkinh/LkLayouts.h"
#include "screens/langkinh/LkTheme.h"

#include <QColor>
#include <QFont>
#include <QJsonObject>
#include <QLayout>
#include <QList>
#include <QRect>
#include <QRectF>
#include <QSize>
#include <QSizeF>
#include <QString>
#include <QWidget>
#include <Qt>

class QEvent;
class QLabel;
class QLayoutItem;
class QPainter;
class QPaintEvent;
class QResizeEvent;
class QVBoxLayout;

namespace fincept::screens::langkinh::lkview {

// ── Rich text html-lite ───────────────────────────────────────────────────────

/// html-lite → rich text an toàn. `strong` hợp lệ → <b> in đậm 600 với màu đó (kiểu `.pl b{color:ink}`),
/// không thì giữ <b>. "\n" → <br>. <tag b="X">nhãn</tag> → span mono màu bậc X (nhãn rỗng → in X).
QString lk_inline_html(const QString& src, const QColor& strong = QColor());
/// Đoạn văn: lk_inline_html bọc <p> có line-height; "\n\n" (dòng trống) tách đoạn, cách nhau 8px.
/// line_height_pct là % của CHIỀU CAO DÒNG của phông (ascent+descent — cách Qt hiểu line-height %), không phải của
/// cỡ chữ như CSS: dùng lk_line_pct(font) để ra đúng nhịp CSS. Mặc định 158 giữ cho người gọi cũ.
QString lk_para_html(const QString& src, const QColor& strong = QColor(), int line_height_pct = 158);
/// % line-height cho rich text của Qt để nhịp dòng = em × cỡ chữ như CSS (Artifact .pl p: 1,62). Be Vietnam Pro
/// 14px cao dòng ≈18px → 1,62 em ≈ 126%, không phải 162% (162% của Qt ra ≈29px, thưa gấp rưỡi Artifact).
int lk_line_pct(const QFont& f, double em = 1.62);
/// Mô tả ngắn của bậc (cho tooltip): "FACT-T2 — data vendor …"; UNVERIFIED kèm "không dùng cho quyết định".
QString lk_tier_desc(const QString& b);

// ── Nhãn chữ ──────────────────────────────────────────────────────────────────

/// QLabel xuống dòng, chọn chữ bằng chuột, nền trong suốt, phông + màu qua QSS riêng của nhãn.
QLabel* lk_label(const QString& text, const QFont& f, const QColor& c, QWidget* parent,
                 Qt::TextFormat fmt = Qt::PlainText);
/// Kiểu đầu block: Block = sub 12px ink2 (mặc định) · Fig = sub là dòng nguồn `.src` 12px muted (thẻ .fig).
enum class LkHead { Block, Fig };
/// Tiêu đề (sans 14px 600, ink) + phụ đề (html-lite) của block — khoá `title`, `sub` — nếu có. Khoá `b` (bậc)
/// → tag bậc bên phải tiêu đề (không có tiêu đề thì tag đứng một mình bên trái).
void lk_add_head(QVBoxLayout* vl, const QJsonObject& b, QWidget* parent, LkHead style = LkHead::Block);
/// Đầu phần kiểu Artifact .sec-head cho block có `eyebrow`: eyebrow mono 11 amber giãn 0,14em · `title` serif 28
/// (+ tag `b` bên phải) · `sub` sans 14 ink2 (khổ ≤ 760px) · vạch 1px line · khe 18px dưới vạch.
void lk_section_head(QVBoxLayout* vl, const QJsonObject& b, QWidget* parent);
/// Nền trong suốt cho w và mọi con chưa có QSS riêng. Cần vì QSS toàn cục đặt `QWidget { background-color:
/// BG_BASE }` và Qt bật WA_StyledBackground cho QWidget trần lẫn lớp con không có Q_OBJECT → vẽ ô BG_BASE
/// dưới pill/nhãn tự vẽ (lộ rõ trên thẻ tô màu và theme sáng). Gọi trên gốc mỗi block và widget tự vẽ.
void lk_transparent(QWidget* w);

// ── Pill & tag ────────────────────────────────────────────────────────────────

/// "mau" của pill (pill_mau, pills[].mau) → vai: no|bad|down → Down · near|warn|amb → Amber ·
/// yes|good|up → Up · info → Blue · violet → Violet · neu|""|lạ → Grey.
LkRole lk_pill_role(const QString& mau);
/// Kích thước pill (mono `px` 600, đệm 2×9px). `tracked` = giãn chữ 0,08em (pill trạng thái đồng hồ).
QSizeF lk_pill_size(const QString& text, int px = 11, bool tracked = false);
/// Vẽ pill bo tròn hẳn trong `r`: nền = soft của màu vai, chữ = màu vai; chữ dài hơn khung → "…".
void lk_paint_pill(QPainter& p, const QRectF& r, const QString& text, LkRole role, int px = 11,
                   bool tracked = false);
/// Kích thước tag bậc (mono 10px 600, giãn 0,04em, đệm 1×5px, bo 4px).
QSizeF lk_tag_size(const QString& b);
/// Vẽ tag bậc `b` trong `r` (màu lk_tier(b) trên lk_tier_soft(b)); b rỗng → không vẽ.
void lk_paint_tag(QPainter& p, const QRectF& r, const QString& b);

/// Pill tự vẽ, kích thước cố định theo chữ (bố cục cấp khung hẹp hơn → chữ "…").
class LkPill : public QWidget {
  public:
    LkPill(const QString& text, LkRole role, QWidget* parent, int px = 11, bool tracked = false);
    QSize sizeHint() const override;
    QSize minimumSizeHint() const override { return sizeHint(); }

  protected:
    void paintEvent(QPaintEvent* e) override;

  private:
    QString text_;
    LkRole role_;
    int px_;
    bool tracked_;
};

/// Tag bậc bằng chứng tự vẽ; tooltip = lk_tier_desc(b).
class LkTag : public QWidget {
  public:
    LkTag(const QString& b, QWidget* parent);
    QSize sizeHint() const override;
    QSize minimumSizeHint() const override { return sizeHint(); }

  protected:
    void paintEvent(QPaintEvent* e) override;

  private:
    QString b_;
};

/// Nhãn chữ hoa giãn chữ tự vẽ (eyebrow amber, tiêu đề hộp muted). Mặc định một dòng, cắt "…" + tooltip;
/// wrap=true → xuống dòng theo bề rộng (heightForWidth).
class LkCapsLabel : public QWidget {
  public:
    LkCapsLabel(const QString& text, const QFont& f, LkRole role, QWidget* parent, double tracking_em = 0.08,
                bool wrap = false);
    QSize sizeHint() const override;
    QSize minimumSizeHint() const override;
    bool hasHeightForWidth() const override { return wrap_; }
    int heightForWidth(int w) const override;

  protected:
    void paintEvent(QPaintEvent* e) override;
    void resizeEvent(QResizeEvent* e) override;

  private:
    QString text_;
    QFont font_;
    LkRole role_;
    bool wrap_;
};

// ── Block ─────────────────────────────────────────────────────────────────────

/// Block "chips": {type:"chips", title?, sub?, items:[{b, text}]} — chip khai nguồn (viền mảnh, bo 6px) gồm tag
/// bậc màu + chữ, xếp chảy xuống dòng. Mục không có cả b lẫn text bị bỏ; không còn mục nào → nullptr.
/// Bậc UNVERIFIED luôn kèm "không dùng cho quyết định".
QWidget* make_chips(const QJsonObject& b, QWidget* parent);

} // namespace fincept::screens::langkinh::lkview
