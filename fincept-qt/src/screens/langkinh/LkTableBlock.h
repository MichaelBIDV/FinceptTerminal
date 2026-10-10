// src/screens/langkinh/LkTableBlock.h
// Lăng Kính FFT — block "table" của LkBlockView (CONTRACT §3.1, §4; tách ra theo DELTA B7).
//
// Thẻ gồm tiêu đề/sub + QTableWidget + caption:
//   · kind: text | bar (thanh ngang frac 0..1 + chữ) | tag (chip) · _tag (nhãn nhỏ sau chữ)
//   · _mau (màu chữ ô) · _vien (vạch 3px bên trái hàng) · _sort (khoá số khi bấm tiêu đề)
//   · _link + row_link → nhấp đúp hàng = on_link(mã)
//   · _tip[key] (tuỳ chọn): chú thích thêm của ô, hiện trong tooltip
//   · _nhom (true | "nhãn"): hàng đầu nhóm gộp mọi cột — nhãn màu nhóm (_vien / _mau của cột 1, mặc định amber)
//     + dòng phụ từ chữ các cột còn lại; không chọn được; bấm tiêu đề cột thì sắp TRONG từng nhóm (LkTableParts.h)
// Khoá block "max_rows": N > 0 → chỉ N hàng đầu (theo thứ tự sắp hiện tại) + nút "Hiện thêm M dòng" / "Thu gọn".
// Ô chữ dài bị cắt "…" theo bề rộng cột; rê chuột → tooltip nguyên văn đầy đủ (xuống dòng).
// Bảng cao vừa đủ số hàng (không cuộn dọc riêng); bánh xe dọc nhường cho trang ngoài.
#pragma once

#include "screens/langkinh/LkWidgets.h"

#include <QJsonObject>

class QWidget;

namespace fincept::screens::langkinh::lkview {

/// Dựng block "table". Không có cột hoặc không có hàng → thẻ ghi "— không có dòng nào —".
QWidget* make_table_block(const QJsonObject& b, QWidget* parent, const TickerFn& on_link);

} // namespace fincept::screens::langkinh::lkview
