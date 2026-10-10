// src/screens/langkinh/LkPage.h
// Lăng Kính FFT — khung trang "hồ sơ" theo HỢP ĐỒNG BLOCK v2 (giữa views Python và Qt):
//
//   · payload "layout":"hoso" → cột trang canh giữa, rộng tối đa 1180px, lề 20px; banner CỔNG kiểu Artifact .gate
//     (nền amber-soft, viền amber-line 1px, bo 12, eyebrow "Dòng cổng", dòng mono 14 với <b> amber, đoạn ink-2 từ
//     cong.chi_tiet); đầu trang: khối đầu tiên là "tkhead" thì bỏ H1/sub, chỉ giữ dòng meta (mono 12 muted).
//   · block bất kỳ có "eyebrow" (trừ tkhead — eyebrow là trường riêng của nó) → đầu phần .sec-head (lk_section_head)
//     đặt TRÊN block, cách phần trước ~40px; title/sub/b của block chuyển lên đầu phần.
//   · {"type":"row","items":[block, block], "flex"?:[1,2]} → đứng cạnh nhau, khe 14px, bề rộng theo trọng số flex
//     (mặc định chia đều); block báo bề rộng tối đa (sơ đồ ≈280px/sơ đồ) chỉ nhận đúng mức đó, phần dư cho mục bên
//     cạnh; hàng hẹp hơn 880px thì xếp dọc, trừ khi mục cố định hẹp vẫn chừa ≥ 440px cho mỗi mục còn lại.
//   · layout hoso: bảng và biểu đồ nằm trong thẻ .fig (bo 10, viền line, đệm 14/14/10, tiêu đề sans 14/600, dòng
//     nguồn muted); chart có thể mang "legend":[{text, mau, dash?}] → vạch 18px (đứt khi dash) dưới biểu đồ.
// Như mọi block: chỉ ĐỌC và VẼ; thiếu khoá/sai kiểu → "—", "[CẦN DATA] …" hoặc bỏ block (nullptr), không crash.
// Container (lkCol, lkSec, lkRow, lkHead, lkMeasure) là QWidget trần → nền trong suốt nhờ luật theo objectName trong
// QSS của canvas (LkBlockView::canvas_qss), KHÔNG dùng lk_transparent (luật đó lan xuống mọi con).
#pragma once

#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QString>

#include <functional>

class QFrame;
class QVBoxLayout;
class QWidget;

namespace fincept::screens::langkinh::lkview {

constexpr int kHosoMaxW = 1180;       ///< bề rộng tối đa cột trang hồ sơ
constexpr int kHosoGutter = 20;       ///< lề trái/phải trang (Artifact .wrap padding-inline)
constexpr int kHosoGap = 14;          ///< khe giữa hai block trong một phần, và khe trong "row"
constexpr int kHosoSectionGap = 40;   ///< khoảng trên một phần có eyebrow
constexpr int kRowStackBelow = 880;   ///< "row" hẹp hơn → xếp dọc
constexpr int kFigChartH = 380;       ///< cao mặc định của chart trong thẻ .fig

/// Dựng một block (kể cả row / phần có eyebrow) — LkBlockView::make_any.
using BlockFn = std::function<QWidget*(const QJsonObject&, QWidget*)>;

/// payload["layout"] == "hoso".
bool is_hoso(const QJsonObject& payload);
/// Block có đầu phần: "eyebrow" không rỗng và type khác "tkhead".
bool has_section_head(const QJsonObject& b);

/// Banner CỔNG kiểu Artifact .gate. Thiếu dòng CỔNG → "[CẦN DATA]" (không bao giờ coi là "ok").
QWidget* make_gate(const QJsonValue& cong, QWidget* parent);
/// Đầu trang hồ sơ: H1 serif + sub (bỏ khi meta_only) + dòng meta mono 12 muted. Không còn gì → nullptr.
QWidget* make_hoso_header(const QJsonObject& payload, bool meta_only, QWidget* parent);

/// Thẻ .fig (objectName "lkFig"); *vl nhận layout dọc đệm 14/14/10, khe 6.
QFrame* make_fig(QWidget* parent, QVBoxLayout** vl);
/// QSS bảng trong trang hồ sơ: ô sans 13px, đệm ngang 12, vạch dưới màu line; tiêu đề mono 11/600 muted trên
/// surface-2 (chữ hoa do LkTableBlock đổi); nền surface trùng thẻ .fig.
QString hoso_table_qss();
/// Chú giải của chart: [{text, mau, dash?}] → vạch 18px + chữ sans 12 ink2, xếp chảy. Rỗng/hỏng → nullptr.
QWidget* make_legend(const QJsonArray& items, bool hoso, QWidget* parent);

/// Block "row" (+ đầu block title/sub/b nếu có, không eyebrow). Không còn mục nào → nullptr.
QWidget* make_row(const QJsonObject& b, QWidget* parent, const BlockFn& make);
/// Phần có eyebrow: đầu phần + block (bỏ eyebrow/title/sub/b khỏi block). Block rỗng → chỉ còn đầu phần.
QWidget* make_section(const QJsonObject& b, QWidget* parent, const BlockFn& make);

} // namespace fincept::screens::langkinh::lkview
