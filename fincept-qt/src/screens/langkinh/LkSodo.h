// src/screens/langkinh/LkSodo.h
// Lăng Kính FFT — block "sodo": lưới sơ đồ nhỏ minh hoạ HÌNH LÝ TƯỞNG của các mẫu hình (thấu kính NTH).
//
//   {type:"sodo", title?, sub?, b?,
//    items:[{id, ten, trang_thai, diem:[[x,y],…], nhan:[{i, text}], hop:[{x0,x1,y0,y1,text}], ghi_chu}]}
//
//   · Toạ độ chuẩn hoá 0..1: x trái → phải, y DƯỚI → TRÊN (y = 1 là đỉnh khung, như trục giá). Điểm ngoài 0..1
//     bị kẹp vào khung. `diem` là hình lý tưởng do view dựng — KHÔNG phải chuỗi giá thật, bộ vẽ không suy số nào.
//   · Mỗi mục một thẻ (bo 10px, viền line) trong lưới cột ≥ 240px giữ cột trống (repeat(auto-fill, minmax())):
//     tên (sans 13/600, html-lite) + pill trạng thái · khung vẽ ≈220×130 (cao theo bề rộng, 120–170px) · ghi_chu
//     (sans 12 muted, html-lite).
//   · Khung vẽ: hộp `hop` viền đứt 3-3 màu line-2 nền grey-soft nhạt + nhãn mono 9 muted ở góc trên trái (hộp dẹt
//     y0 = y1 → vạch ngang đứt kèm nhãn trên vạch, vd "gãy: đáy nền −7%"; x0 = x1 → vạch dọc đứt); đường
//     amber 2px nối `diem`; `nhan[i]` = chấm amber viền surface tại diem[i] + nhãn mono 10 ink-2 (trên đỉnh cục bộ,
//     dưới đáy cục bộ; chồng nhãn trước → thử phía kia, vẫn chồng → bỏ chữ, giữ chấm, tooltip đủ mọi nhãn).
//   · trang_thai → pill: dang_hinh_thanh "đang hình thành" amber · xac_nhan "xác nhận" up · gay "gãy" down ·
//     het_hieu_luc "hết hiệu lực" grey (đường vẽ nhạt đi) · lạ → nguyên văn, grey.
// Như mọi block: chỉ ĐỌC và VẼ. Mục thiếu cả ten lẫn diem bị bỏ; mục có ít hơn 2 điểm hợp lệ → thẻ ghi
// "[CẦN DATA] — …" thay khung vẽ. Không còn mục nào → nullptr (bỏ block).
// Màu đọc lại qua lk_col() trong paintEvent (quy ước LkTheme cho widget tự vẽ); phông từ LkTheme.
#pragma once

#include <QJsonObject>

class QWidget;

namespace fincept::screens::langkinh::lkview {

QWidget* make_sodo(const QJsonObject& b, QWidget* parent);

} // namespace fincept::screens::langkinh::lkview
