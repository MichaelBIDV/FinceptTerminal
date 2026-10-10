// src/screens/langkinh/LkCotMoc.h
// Lăng Kính FFT — block "cotmoc" của hồ sơ: cột mốc rời (categorical), dựng theo holdChart của Artifact UgewJ.
//
//   {type:"cotmoc", title?, sub?, b?,
//    items:[{ky, v, b, kieu, cf, so_tron}],     // một cột cho mỗi mốc, theo thứ tự mảng
//    cap:[{i_tu, i_den, text}]}                 // Δ giữa hai mốc (chỉ số trong items)
//
//   · Cột cách đều theo khe (không theo trục thời gian), rộng min(46px, 46% khe), bo 3px, màu theo bậc `b`:
//     FACT-T2 blue · SS-T3 violet · EST amber · FACT-T1 up · UNVERIFIED/CẦN DATA down · lạ → grey.
//   · Mốc không phải quan sát sạch — cf, so_tron, hoặc kieu "chep" / "noi_suy" / "so_tron" — vẽ rỗng: nền alpha
//     0,35 + viền đứt 3-2 alpha 0,35 (như cột "số tròn" của Artifact). Chú thích dưới cột nói rõ lý do.
//   · Trên cột: số kiểu Việt (73.355); dưới cột: `ky` rồi dòng nguồn = bậc (+ " · CF" / " · số tròn" / " · nội suy").
//   · cap: đoạn đầu của `text` (trước " · " đầu tiên, vd "+136,6%") đặt giữa hai cột ở hàng dưới cùng; toàn văn
//     "ky_tu → ky_den: text" liệt kê dưới hình (kiểu .legend cột của Artifact).
//   · v null/không phải số → khung rỗng đứt nét màu down + "CẦN DATA" (không bao giờ vẽ thành 0).
// Như mọi block: chỉ ĐỌC và VẼ, không tính lại Δ hay k. Không có mốc nào → thẻ ghi "[CẦN DATA] — …".
// Màu đọc lại qua lk_col() trong paintEvent (quy ước LkTheme cho widget tự vẽ); phông từ LkTheme.
#pragma once

#include <QJsonObject>

class QWidget;

namespace fincept::screens::langkinh::lkview {

/// Block "cotmoc": thẻ .fig + đầu block (title/sub/b) + hình cột mốc + dòng Δ. Không phải object → nullptr.
QWidget* make_cotmoc(const QJsonObject& b, QWidget* parent);

} // namespace fincept::screens::langkinh::lkview
