// src/screens/langkinh/LkPillarBlock.h
// Lăng Kính FFT — block "pillars" của hồ sơ Lăng Kính (LK_HOSO_SPEC §6), dựng theo khối .pl của Artifact:
//
//   {type:"pillars", title?, sub?, items:[{lab, sub?, paras:[html-lite]}]}
//
//   · Mỗi mục là một hàng: cột nhãn 168px (LkCapsLabel mono chữ hoa giãn chữ màu amber, `sub` bên dưới mono
//     muted, không in hoa) + các đoạn văn (lk_para_html: sans 14px ink-2, nhịp 1,62em; <b> đậm màu ink;
//     <tag b="FACT-T2">…</tag> → chip bậc; "\n\n" tách đoạn). Vạch mảnh 1px giữa các hàng.
//   · Hàng hẹp hơn 760px: nhãn nằm trên đoạn văn. Đoạn văn tối đa ~780px bề ngang (≈74ch như Artifact).
//   · Bọc trong thẻ bo 10px; title/sub qua lk_add_head (LkChips — bản Artifact của add_head, sub là html-lite).
//
// Như mọi block: chỉ ĐỌC và VẼ. Mục thiếu cả lab lẫn paras → bỏ mục; không còn mục nào → nullptr (bỏ block).
// Mục có nhãn mà không có đoạn văn → "—". Màu/font đọc từ LkTheme lúc dựng (đổi theme → LkBlockView dựng lại).
#pragma once

#include "screens/langkinh/LkWidgets.h"

#include <QJsonObject>

class QWidget;

namespace fincept::screens::langkinh::lkview {

/// Block "pillars". Không có mục hợp lệ → nullptr.
QWidget* make_pillars(const QJsonObject& b, QWidget* parent);

} // namespace fincept::screens::langkinh::lkview
