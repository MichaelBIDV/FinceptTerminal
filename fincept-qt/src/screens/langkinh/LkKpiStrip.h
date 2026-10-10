// src/screens/langkinh/LkKpiStrip.h
// Lăng Kính FFT — block "kpis" của hồ sơ (LK_HOSO_SPEC §6): dải ô số nối liền kiểu Artifact `.kpis`
// (lưới 1px hairline trong khung bo 10px, cột auto-fit tối thiểu 142px, tự xuống hàng khi hẹp; bớt cột để hàng
// cuối không còn một ô mồ côi).
//
//   {type:"kpis", title?, sub?, items:[{k, v, s, b?, mau?, tip?}]}
//     k   nhãn nhỏ (sans 11px, muted, gói dòng)
//     v   giá trị (mono 16px 600, tabular) — màu theo mau: "good"→up · "bad"→down · "amb"→amber · ""→ink
//     s   dòng phụ (mono 11px, ink2)
//     b   bậc bằng chứng → tag màu bên phải dòng giá trị (không vừa → bên phải nhãn k); FACT-T1/FACT-T2/SS-T3/
//         NEWS/EST/UNVERIFIED/CẦN DATA
//     tip chú thích thêm cho tooltip (tuỳ chọn)
// v thiếu → "—"; v = null tường minh và không có b → tag "CẦN DATA" (luật §0.1: không điền số).
// Bậc UNVERIFIED → dòng s kèm "không dùng cho quyết định". Mục thiếu cả k, v, s bị bỏ; không còn mục → nullptr.
// Tự vẽ bằng QPainter (antialias, hairline canh pixel), cao theo heightForWidth, vẽ lại khi đổi cỡ.
#pragma once

#include <QJsonObject>

class QWidget;

namespace fincept::screens::langkinh::lkview {

QWidget* make_kpis(const QJsonObject& b, QWidget* parent);

} // namespace fincept::screens::langkinh::lkview
