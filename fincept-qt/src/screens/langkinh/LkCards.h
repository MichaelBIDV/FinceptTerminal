// src/screens/langkinh/LkCards.h
// Lăng Kính FFT — block "cards" và "tkhead" của hồ sơ (LK_HOSO_SPEC §6), theo ngôn ngữ thiết kế Artifact.
//
// cards: {type:"cards", variant, title?, sub?, items:[{pill?, pill_mau?, id?, tieu_de, noi_dung, inv?}]}
//   variant "clock"     thẻ (bo 10px, viền mảnh) = pill trạng thái giãn chữ + h3 + đoạn văn; lưới auto-fit ≥ 250px
//                       (kiểu .clocks của Artifact — ba chiếc đồng hồ thời gian · định giá · dòng tiền).
//   variant "box"       hộp hai cột (≥ 300px mỗi cột, hẹp thì một cột): nhãn mono chữ hoa muted (+ pill tuỳ chọn) +
//                       đoạn văn; inv:true → nền phủ down-soft, viền ngả đỏ (kiểu "Nghịch đảo · Munger").
//                       Biến thể lạ/thiếu → "box".
//   variant "keynote"   hàng: cột trái id serif amber lớn (mặc định K1, K2…) + h3 serif + đoạn văn; hàng cách
//                       nhau bằng hairline.
//   variant "premortem" hàng: số serif đỏ (mặc định 1, 2…) + h3 sans + đoạn văn.
//   pill_mau: no|bad → down · near|warn → amber · yes|good → up · info → blue · neu|"" → grey.
//   tieu_de/noi_dung là html-lite: <b> <i> <code> <br> + <tag b="FACT-T2">…</tag> (xem lk_inline_html);
//   noi_dung có thể là mảng đoạn; "\n\n" tách đoạn. Mục thiếu cả tieu_de, noi_dung, pill bị bỏ; hết mục → nullptr.
//
// tkhead: {type:"tkhead", ma, eyebrow, tieu_de, px, b?, chg, chg_mau?, pills:[{text, mau}], cong_ma}
//   mã serif lớn (64px) · eyebrow mono amber chữ hoa · tiêu đề serif · giá mono + biến động màu + tag bậc `b` của
//   giá (vd FACT-T2; chỉ khi có giá/biến động) · pills;
//   hẹp (< mã + 22 + 300px) thì mã xếp trên cột phải. Dưới cùng: dòng CỔNG mono có vạch amber bên trái.
//   chg_mau "up"|"down"|"" (có khoá: "" = trung tính); vắng khoá → màu theo dấu đầu chuỗi đã định dạng (+ / −).
//   cong_ma thiếu → "CỔNG: [CẦN DATA] …" với vạch đỏ (không mặc định kết luận nào). Không có ma, eyebrow lẫn
//   tieu_de → nullptr.
#pragma once

#include <QJsonObject>

class QWidget;

namespace fincept::screens::langkinh::lkview {

QWidget* make_cards(const QJsonObject& b, QWidget* parent);
QWidget* make_tkhead(const QJsonObject& b, QWidget* parent);

} // namespace fincept::screens::langkinh::lkview
